//! A5 opt-in live audio (`--live-audio`, never on by default). Three pieces:
//! - input: `pw-record` (or `parecord`) runs in a bwrap sandbox that binds only the PipeWire/Pulse
//!   sockets it needs. Its raw s16 mono 16 kHz stdout is cut into 20 ms frames and written to a
//!   wake worker over stdin. The worker's packets enter the same `WakeInput` / pre-roll / capture
//!   path as the replay and virtual sources. Restarts: at most 3 per 60 s, with backoff.
//! - output: TTS PCM is written to `pw-play` (or `paplay`) in a sandbox, per speech job.
//! - state: `LiveState` feeds the `audio.live` snapshot; `mic_active` is true only while the
//!   recorder process runs.
//!
//! Nothing here is verified on real microphones or speakers. Tests use fake tools (tests/fixtures).
use crate::{
    devices::Devices,
    levels::{self, FrameStats, Level, Summary, Verdict},
    storage::{valid_audio_device, Config},
    wake::{Packet, WorkerMode},
};
use serde::Serialize;
use std::{
    collections::VecDeque,
    ffi::OsStr,
    io,
    path::{Path, PathBuf},
    process::Stdio,
    time::{Duration, Instant},
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt, BufReader},
    process::{Child, ChildStdin, Command},
    sync::{mpsc, watch},
};

/// 20 ms at 16 kHz, mono, s16le.
pub const FRAME_SAMPLES: usize = 320;
pub const FRAME_BYTES: usize = FRAME_SAMPLES * 2;
pub const FRAME_US: u64 = 20_000;
/// Speech PCM rate of the TTS worker.
pub const PLAYBACK_RATE: u32 = 24_000;
/// At most this many recorder/worker restarts in one window.
pub const RESTART_LIMIT: usize = 3;
pub const RESTART_WINDOW: Duration = Duration::from_secs(60);
const BACKOFF_BASE: Duration = Duration::from_millis(200);
const WRITE_TIMEOUT: Duration = Duration::from_secs(2);
const PLAYER_EXIT: Duration = Duration::from_secs(5);
const BWRAP: &str = "/usr/bin/bwrap";
/// The level block is recomputed at most this often (5 times a second).
pub const PUBLISH_INTERVAL: Duration = Duration::from_millis(200);
/// Length of one `audio_probe` recording.
pub const PROBE_DURATION: Duration = Duration::from_secs(3);

/// Preference-derived settings the live input follows. A change restarts the pipeline at the next
/// session boundary (the Core only publishes changes while no voice session is active).
#[derive(Clone, Debug, PartialEq)]
pub struct Settings {
    pub input_device: String,
    pub keywords_threshold: f32,
    pub input_conditioning: crate::storage::InputConditioning,
    /// Identity of the stored phrase list with its sensitivities (A13). A change restarts the worker, which
    /// loads the keyword file staged for the new list (`phrases::stage`). Published only while the
    /// configuration is ready (transport), so a worker never starts on a list the Core has not started with.
    pub keyword_key: u64,
}
impl Settings {
    pub fn from_config(config: &Config) -> Self {
        Self {
            input_device: config.audio_input_device.clone(),
            keywords_threshold: crate::wake::keywords_threshold(config.wake_sensitivity),
            input_conditioning: config.input_conditioning,
            keyword_key: keyword_key(config),
        }
    }
}

/// Stable hash of the stored wake phrase list: ids, active switches and per-phrase sensitivities.
fn keyword_key(config: &Config) -> u64 {
    use std::hash::{Hash, Hasher};
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    for phrase in &config.wake_phrases {
        phrase.id.hash(&mut hasher);
        phrase.active.hash(&mut hasher);
        phrase.sensitivity.map(f32::to_bits).hash(&mut hasher);
    }
    hasher.finish()
}

/// Content-free reason of a failed live input (`audio.live.last_error`). The closed vocabulary is fixed.
pub const WORKER_CRASHED: &str = "worker_crashed";
pub const WORKER_IMPORT_ERROR: &str = "worker_import_error";
pub const DEVICE_UNAVAILABLE: &str = "device_unavailable";
pub const RECORDER_EXITED: &str = "recorder_exited";
pub const MODEL_MISSING: &str = "model_missing";
/// Bytes of worker stderr kept for diagnostics (the last ones).
pub const STDERR_TAIL: usize = 2048;
/// File in the Core data dir with the last worker stderr tail (0600). Never part of the snapshot.
pub const LAST_ERROR_FILE: &str = "live-last-error.txt";

/// Maps a supervisor failure to its reason. Worker failures are classified from the stderr tail: a Python
/// traceback names its exception class, and the tail itself never leaves the Core except in the 0600 file.
pub fn reason_for(step_code: &str, tail: &[u8]) -> &'static str {
    match step_code {
        "recorder_exited" => RECORDER_EXITED,
        "recorder_unavailable" | "sandbox_unavailable" | "invalid_device" => DEVICE_UNAVAILABLE,
        _ => {
            let text = String::from_utf8_lossy(tail);
            if text.contains("ModuleNotFoundError") || text.contains("ImportError") {
                WORKER_IMPORT_ERROR
            } else if text.contains("FileNotFoundError")
                || text.contains("No such file or directory")
                || text.contains("artifact hash")
            {
                MODEL_MISSING
            } else {
                WORKER_CRASHED
            }
        }
    }
}

/// Writes the diagnostic tail to `root/live-last-error.txt` with mode 0600, never following a link.
pub fn write_last_error(root: &Path, tail: &[u8]) -> io::Result<()> {
    write_private_file(&root.join(LAST_ERROR_FILE), tail)
}

/// Replaces `path` with `bytes` at mode 0600 (no-follow). Used for worker stderr tails only.
pub fn write_private_file(path: &Path, bytes: &[u8]) -> io::Result<()> {
    use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)?;
    file.set_permissions(std::fs::Permissions::from_mode(0o600))?;
    io::Write::write_all(&mut file, bytes)?;
    file.sync_all()
}

/// The wake worker that consumes the live stream (same manifest as the replay profile).
#[derive(Clone, Debug)]
pub struct WakeSpec {
    pub python: PathBuf,
    pub manifest: PathBuf,
    pub active_phrase: Option<String>,
}

/// Status transitions reported by the supervisors. Vocabulary is closed.
#[derive(Clone, Debug, PartialEq)]
pub enum LiveEvent {
    Input {
        state: &'static str,
        error: Option<&'static str>,
    },
    Output {
        state: &'static str,
        error: Option<&'static str>,
    },
    /// One measured 20 ms recorder frame (A9 level meter). Numbers only.
    Frame { stats: FrameStats, at: Instant },
    /// The last worker stderr of a failed worker (A13). Goes to `LAST_ERROR_FILE` only; never into the snapshot.
    WorkerTail { tail: Vec<u8> },
}

/// The last wake detection, as the snapshot shows it (`audio.live.last_detection`).
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct LastDetection {
    /// Unix milliseconds of the detection.
    pub at_ms: u64,
    pub phrase_id: String,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct LiveView {
    /// The live pipeline runs in this process (`--live-audio` or the ledger preference at start).
    pub enabled: bool,
    pub input_state: &'static str,
    pub output_state: &'static str,
    pub mic_active: bool,
    /// The ledger preference differs from what this process started with: a Core restart applies it.
    pub restart_required: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_error: Option<&'static str>,
    /// Input level (A9): numbers only, refreshed at most 5 times a second; all silent when not capturing.
    pub level: Level,
    /// null, or one of `no_frames`, `clipping`, `very_noisy`, `very_quiet` (derived in the Core).
    pub silence_warning: Option<&'static str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_detection: Option<LastDetection>,
}

/// One `audio_probe` (A9): `running` while the 3 s recording lasts, then `done` with the measurements.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct ProbeView {
    pub id: u64,
    pub device: String,
    pub state: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub frames: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rms_dbfs: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub peak_dbfs: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub floor_dbfs: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub verdict: Option<&'static str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hint: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<&'static str>,
}

impl ProbeView {
    pub fn running(id: u64, device: String) -> Self {
        Self {
            id,
            device,
            state: "running",
            frames: None,
            rms_dbfs: None,
            peak_dbfs: None,
            floor_dbfs: None,
            verdict: None,
            hint: None,
            reason: None,
        }
    }
    pub fn finished(id: u64, device: String, outcome: &ProbeOutcome) -> Self {
        Self {
            id,
            device,
            state: "done",
            frames: Some(outcome.summary.frames),
            rms_dbfs: Some(outcome.summary.rms_dbfs),
            peak_dbfs: Some(outcome.summary.peak_dbfs),
            floor_dbfs: Some(outcome.summary.floor_dbfs),
            verdict: Some(outcome.verdict.as_str()),
            hint: Some(outcome.hint.clone()),
            reason: outcome.reason,
        }
    }
}

/// Snapshot block `audio`: `devices` only after an `audio_devices` op, `live` always, `probe` after an `audio_probe`.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct AudioView {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub devices: Option<Devices>,
    pub live: LiveView,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub probe: Option<ProbeView>,
    /// A13 microphone assistant: `idle` until `audio_recommend_input` runs.
    pub recommendation: crate::mic_assist::View,
}

#[derive(Clone, Debug)]
pub struct LiveState {
    enabled: bool,
    /// The ledger preference that was in effect when this process started the pipeline.
    started_with_preference: bool,
    input: &'static str,
    output: &'static str,
    error: Option<&'static str>,
    meter: levels::Meter,
    /// The level block as last published, with the time it was computed (at most every PUBLISH_INTERVAL).
    published: Option<(Instant, Level)>,
    last_detection: Option<LastDetection>,
}
impl Default for LiveState {
    fn default() -> Self {
        Self {
            enabled: false,
            started_with_preference: false,
            input: "idle",
            output: "idle",
            error: None,
            meter: levels::Meter::default(),
            published: None,
            last_detection: None,
        }
    }
}
impl LiveState {
    /// Called once at start: `enabled` is the pipeline switch of this process (flag or preference),
    /// `from_preference` says whether the ledger alone turned it on.
    pub fn configure(&mut self, enabled: bool, from_preference: bool) {
        self.enabled = enabled;
        self.started_with_preference = from_preference;
    }
    pub fn apply(&mut self, event: LiveEvent) {
        match event {
            LiveEvent::Input { state, error } => {
                self.input = state;
                if state == "capturing" {
                    self.error = None;
                    // A new capture starts a new measurement: the floor and the history are not carried over.
                    self.meter.reset(Instant::now());
                    self.published = None;
                }
                self.error = error.or(self.error);
            }
            LiveEvent::Output { state, error } => {
                self.output = state;
                self.error = error.or(self.error);
            }
            LiveEvent::Frame { stats, at } => {
                self.meter.push(stats, at);
                let due = self
                    .published
                    .as_ref()
                    .is_none_or(|(t, _)| at.saturating_duration_since(*t) >= PUBLISH_INTERVAL);
                if due {
                    self.published = Some((at, self.meter.level(at)));
                }
            }
            LiveEvent::WorkerTail { .. } => {}
        }
    }
    /// True when this process runs the live pipeline (flag or ledger at start).
    pub fn pipeline_enabled(&self) -> bool {
        self.enabled
    }
    /// A wake phrase was recognised: feeds `last_detection` and the "heard, not recognised" state.
    pub fn detected(&mut self, phrase_id: &str, now: Instant) {
        self.meter.note_detection(now);
        if crate::protocol::valid_id(phrase_id) {
            self.last_detection = Some(LastDetection {
                at_ms: crate::protocol::unix_ms(),
                phrase_id: phrase_id.to_string(),
            });
        }
    }
    /// `preference` is the current ledger value (`Config::live_audio`); `now` times the age and the warnings.
    pub fn view(&self, preference: bool, now: Instant) -> LiveView {
        let capturing = self.input == "capturing";
        let level = match (&self.published, capturing) {
            (Some((_, level)), true) => Level {
                last_frame_age_ms: self.meter.age_ms(now),
                ..*level
            },
            _ => Level::silent(),
        };
        LiveView {
            enabled: self.enabled,
            input_state: self.input,
            output_state: self.output,
            mic_active: capturing,
            restart_required: preference != self.started_with_preference,
            last_error: self.error,
            level,
            silence_warning: self.meter.warning(capturing, now),
            last_detection: self.last_detection.clone(),
        }
    }
}

/// Finds the first existing executable among `names` in `path` (absolute entries only).
pub fn find_tool(path: &OsStr, names: &[&'static str]) -> Option<(PathBuf, &'static str)> {
    use std::os::unix::fs::PermissionsExt;
    for name in names {
        for dir in std::env::split_paths(path) {
            if !dir.is_absolute() {
                continue;
            }
            let candidate = dir.join(name);
            let executable = std::fs::metadata(&candidate)
                .is_ok_and(|m| m.is_file() && m.permissions().mode() & 0o111 != 0);
            if executable {
                return Some((candidate, name));
            }
        }
    }
    None
}

/// `default` means no target argument (the system default device).
pub fn device_ok(device: &str) -> bool {
    device == "default" || valid_audio_device(device)
}

/// Arguments of the recorder: raw s16le mono 16 kHz on stdout. `--raw` is required for pw-record:
/// without it, writing to `-` produces an AU container (24-byte header, big-endian samples), which
/// the worker would read as little-endian PCM (byte-swapped noise, no wake).
pub fn recorder_args(tool: &str, device: &str) -> Vec<String> {
    let mut args: Vec<String> = Vec::new();
    if tool == "pw-record" {
        args.extend(
            [
                "--raw",
                "--rate",
                "16000",
                "--channels",
                "1",
                "--format",
                "s16",
            ]
            .map(String::from),
        );
        if device != "default" {
            args.extend(["--target".into(), device.into()]);
        }
        args.push("-".into());
    } else {
        args.extend(["--raw", "--rate=16000", "--channels=1", "--format=s16le"].map(String::from));
        if device != "default" {
            args.push(format!("--device={device}"));
        }
    }
    args
}

/// Arguments of the player: raw s16le mono 24 kHz from stdin.
/// `--raw` is required for pw-play as well: without it stdin is parsed as a sound file, the open fails
/// ("Format not recognised") and the player exits before the first speech chunk.
pub fn player_args(tool: &str, device: &str) -> Vec<String> {
    let mut args: Vec<String> = Vec::new();
    if tool == "pw-play" {
        args.extend(
            [
                "--raw",
                "--rate",
                "24000",
                "--channels",
                "1",
                "--format",
                "s16",
            ]
            .map(String::from),
        );
        if device != "default" {
            args.extend(["--target".into(), device.into()]);
        }
        args.push("-".into());
    } else {
        args.extend(["--raw", "--rate=24000", "--channels=1", "--format=s16le"].map(String::from));
        if device != "default" {
            args.push(format!("--device={device}"));
        }
    }
    args
}

/// bwrap command for one audio tool: `/usr` read-only, no network, no IPC namespace sharing, a private
/// `/tmp`, and only the audio endpoints that exist under `XDG_RUNTIME_DIR` (`pipewire-0`, `pulse`)
/// plus the Pulse cookie (read-only). The program's own directory is bound read-only when it lives
/// outside `/usr`. The environment is cleared; stdio and kill-on-drop are set by the caller.
pub fn sandboxed(program: &Path, args: &[String]) -> io::Result<Command> {
    if !Path::new(BWRAP).is_file() {
        return Err(io::Error::other("bwrap missing"));
    }
    let mut cmd = Command::new(BWRAP);
    cmd.env_clear().env("PATH", "/usr/bin:/bin");
    cmd.args([
        "--unshare-all",
        "--die-with-parent",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib",
        "/lib64",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
    ]);
    if !program.starts_with("/usr/") {
        let dir = program
            .parent()
            .ok_or_else(|| io::Error::other("program directory missing"))?;
        cmd.arg("--ro-bind").arg(dir).arg(dir);
    }
    if let Some(runtime) = std::env::var_os("XDG_RUNTIME_DIR")
        .map(PathBuf::from)
        .filter(|p| p.is_absolute())
    {
        for name in ["pipewire-0", "pulse"] {
            let socket = runtime.join(name);
            if socket.exists() {
                cmd.arg("--bind").arg(&socket).arg(&socket);
            }
        }
        cmd.arg("--setenv").arg("XDG_RUNTIME_DIR").arg(&runtime);
    }
    if let Some(cookie) = std::env::var_os("HOME")
        .map(|home| PathBuf::from(home).join(".config/pulse/cookie"))
        .filter(|p| p.is_file())
    {
        cmd.arg("--ro-bind")
            .arg(&cookie)
            .arg("/tmp/pulse-cookie")
            .args(["--setenv", "PULSE_COOKIE", "/tmp/pulse-cookie"]);
    }
    cmd.args(["--setenv", "HOME", "/tmp", "--chdir", "/tmp", "--"])
        .arg(program)
        .args(args)
        .kill_on_drop(true);
    Ok(cmd)
}

fn spawn_recorder(device: &str) -> Result<Child, &'static str> {
    spawn_recorder_in(&std::env::var_os("PATH").unwrap_or_default(), device)
}

/// Same recorder pattern with an explicit tool `PATH` (the probe and its tests use it).
pub fn spawn_recorder_in(path: &OsStr, device: &str) -> Result<Child, &'static str> {
    if !device_ok(device) {
        return Err("invalid_device");
    }
    let (program, tool) =
        find_tool(path, &["pw-record", "parecord"]).ok_or("recorder_unavailable")?;
    let mut command =
        sandboxed(&program, &recorder_args(tool, device)).map_err(|_| "sandbox_unavailable")?;
    command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    command.spawn().map_err(|_| "recorder_unavailable")
}

/// Paths the live worker must read, bound read-only in its namespace next to the manifest: the asset
/// root and the VAD model's directory when the manifest names them (the replay profile binds the
/// same paths). Without them the worker cannot load its model and exits at start.
pub fn worker_mounts(manifest: &Path) -> io::Result<Vec<PathBuf>> {
    let bytes = std::fs::read(manifest)?;
    if bytes.len() > 1_048_576 {
        return Err(io::Error::other("wake manifest too large"));
    }
    let value: serde_json::Value = serde_json::from_slice(&bytes)?;
    let mut mounts = vec![manifest.to_path_buf()];
    if let Some(root) = value["asset_root"].as_str() {
        mounts.push(PathBuf::from(root));
    }
    if let Some(vad) = value["vad"]["path"].as_str() {
        if let Some(dir) = Path::new(vad).parent() {
            mounts.push(dir.to_path_buf());
        }
    }
    // A Core keyword set (src/phrases.rs) keeps its keyword file beside the manifest in its own directory.
    if let Some(dir) = keyword_dir_of(&value) {
        mounts.push(dir);
    }
    if mounts.iter().any(|p| !p.is_absolute()) {
        return Err(io::Error::other("absolute mount required"));
    }
    Ok(mounts)
}

/// Directory of the keyword file named by a runtime manifest (`keywords_file`), when there is one.
pub fn keyword_dir(manifest: &Path) -> io::Result<Option<PathBuf>> {
    let value: serde_json::Value = serde_json::from_slice(&std::fs::read(manifest)?)?;
    Ok(keyword_dir_of(&value))
}

fn keyword_dir_of(value: &serde_json::Value) -> Option<PathBuf> {
    value["keywords_file"]
        .as_str()
        .and_then(|file| Path::new(file).parent())
        .map(Path::to_path_buf)
}

fn spawn_worker(wake: &WakeSpec, settings: &Settings, start_us: u64) -> io::Result<Child> {
    let manifest = wake
        .manifest
        .to_str()
        .ok_or_else(|| io::Error::other("manifest path"))?;
    let args = crate::wake::worker_args(
        manifest,
        WorkerMode::Live { start_us },
        wake.active_phrase.as_deref(),
        settings.keywords_threshold,
        Some(settings.input_conditioning.as_str()),
    );
    let mounts = worker_mounts(&wake.manifest)?;
    let mut command = crate::transport::namespace_command(
        &wake.python,
        "scripts/wake_worker.py",
        &args,
        &mounts,
    )?;
    // A13: stderr is kept (tail only) so a failed start says why; see `read_tail`.
    command.stdin(Stdio::piped()).stderr(Stdio::piped());
    command.spawn()
}

enum Step {
    Reconfigure,
    Closed,
    Failed(&'static str),
}

/// Input supervisor. Runs until the packet receiver closes (shutdown) or the restart budget is spent;
/// the latter sends `Err(())` so the Core marks the wake pipeline failed.
pub async fn run_input(
    wake: WakeSpec,
    mut settings: watch::Receiver<Settings>,
    packets: mpsc::Sender<Result<Packet, ()>>,
    events: mpsc::UnboundedSender<LiveEvent>,
) {
    // Global clock: cumulative frames delivered. Every worker starts at the clock it was given, so
    // packet timestamps stay contiguous across restarts.
    let mut clock_us = 0u64;
    let mut failures: VecDeque<Instant> = VecDeque::new();
    loop {
        let current = settings.borrow_and_update().clone();
        let mut tail = Vec::new();
        let step = run_once(
            &wake,
            &current,
            &mut settings,
            &packets,
            &events,
            &mut clock_us,
            &mut tail,
        )
        .await;
        match step {
            Step::Reconfigure => {}
            Step::Closed => return,
            Step::Failed(code) => {
                // A13: the cause is a content-free code. The stderr tail is only handed to the Core, which keeps it
                // in the 0600 diagnostics file.
                let reason = reason_for(code, &tail);
                let _ = events.send(LiveEvent::WorkerTail { tail });
                let now = Instant::now();
                while failures
                    .front()
                    .is_some_and(|t| now.duration_since(*t) >= RESTART_WINDOW)
                {
                    failures.pop_front();
                }
                if failures.len() >= RESTART_LIMIT {
                    // The budget is spent: the state reports the cause that kept failing, not only the limit.
                    let _ = events.send(LiveEvent::Input {
                        state: "error",
                        error: Some(reason),
                    });
                    let _ = packets.send(Err(())).await;
                    return;
                }
                failures.push_back(now);
                let _ = events.send(LiveEvent::Input {
                    state: "error",
                    error: Some(reason),
                });
                let delay = BACKOFF_BASE * 2u32.pow(failures.len() as u32 - 1);
                tokio::select! {
                    _ = tokio::time::sleep(delay) => {}
                    changed = settings.changed() => {
                        if changed.is_err() {
                            return;
                        }
                    }
                }
            }
        }
    }
}

/// Keeps the last `STDERR_TAIL` bytes of a worker's stderr until it closes. Output is never written anywhere else.
pub(crate) async fn read_tail(mut stderr: tokio::process::ChildStderr) -> Vec<u8> {
    let mut tail: VecDeque<u8> = VecDeque::with_capacity(STDERR_TAIL);
    let mut chunk = [0u8; 512];
    loop {
        match stderr.read(&mut chunk).await {
            Ok(0) | Err(_) => break,
            Ok(n) => {
                for byte in &chunk[..n] {
                    if tail.len() == STDERR_TAIL {
                        tail.pop_front();
                    }
                    tail.push_back(*byte);
                }
            }
        }
    }
    tail.into()
}

/// One worker + recorder run. `tail_out` receives the worker's stderr tail when the run ends after the worker started.
async fn run_once(
    wake: &WakeSpec,
    current: &Settings,
    settings: &mut watch::Receiver<Settings>,
    packets: &mpsc::Sender<Result<Packet, ()>>,
    events: &mpsc::UnboundedSender<LiveEvent>,
    clock_us: &mut u64,
    tail_out: &mut Vec<u8>,
) -> Step {
    let mut worker = match spawn_worker(wake, current, *clock_us) {
        Ok(child) => child,
        Err(_) => return Step::Failed("wake_worker_unavailable"),
    };
    let tail_task = worker
        .stderr
        .take()
        .map(|stderr| tokio::spawn(read_tail(stderr)));
    let (Some(mut worker_in), Some(worker_out)) = (worker.stdin.take(), worker.stdout.take())
    else {
        let _ = worker.start_kill();
        return Step::Failed("wake_worker_unavailable");
    };
    let mut recorder = match spawn_recorder(&current.input_device) {
        Ok(child) => child,
        Err(code) => {
            let _ = worker.start_kill();
            return Step::Failed(code);
        }
    };
    let Some(mut recorder_out) = recorder.stdout.take() else {
        let _ = recorder.start_kill();
        let _ = worker.start_kill();
        return Step::Failed("recorder_unavailable");
    };
    // Worker lines are read by their own task, so a stalled select never blocks worker output.
    let (line_tx, mut lines) = mpsc::channel::<Result<Vec<u8>, ()>>(4);
    let reader = tokio::spawn(async move {
        let mut out = BufReader::new(worker_out);
        loop {
            match crate::transport::bounded_frame(&mut out, 65536).await {
                Ok(Some(line)) => {
                    if line_tx.send(Ok(line)).await.is_err() {
                        return;
                    }
                }
                _ => {
                    let _ = line_tx.send(Err(())).await;
                    return;
                }
            }
        }
    });
    let _ = events.send(LiveEvent::Input {
        state: "capturing",
        error: None,
    });
    let mut buf = [0u8; FRAME_BYTES];
    let mut filled = 0usize;
    let step = loop {
        tokio::select! {
            changed = settings.changed() => {
                break if changed.is_ok() { Step::Reconfigure } else { Step::Closed };
            }
            _ = packets.closed() => break Step::Closed,
            // `read` is cancel-safe; `read_exact` would lose a partial frame if this branch lost.
            read = recorder_out.read(&mut buf[filled..]) => {
                match read {
                    Ok(0) | Err(_) => break Step::Failed("recorder_exited"),
                    Ok(n) => filled += n,
                }
                if filled == FRAME_BYTES {
                    filled = 0;
                    // A9 level meter: the recorder's own frame, before the worker (numbers only are kept).
                    let _ = events.send(LiveEvent::Frame {
                        stats: levels::frame_stats(&buf),
                        at: Instant::now(),
                    });
                    match tokio::time::timeout(WRITE_TIMEOUT, worker_in.write_all(&buf)).await {
                        Ok(Ok(())) => *clock_us += FRAME_US,
                        _ => break Step::Failed("wake_worker_failed"),
                    }
                }
            }
            line = lines.recv() => {
                match line {
                    Some(Ok(bytes)) => match serde_json::from_slice::<Packet>(&bytes) {
                        Ok(packet) => {
                            if packets.send(Ok(packet)).await.is_err() {
                                break Step::Closed;
                            }
                        }
                        Err(_) => break Step::Failed("wake_worker_failed"),
                    },
                    _ => break Step::Failed("wake_worker_failed"),
                }
            }
        }
    };
    reader.abort();
    let _ = recorder.start_kill();
    let _ = worker.start_kill();
    let _ = recorder.wait().await;
    let _ = worker.wait().await;
    // The worker is gone, so its stderr reaches EOF; the bound only protects against a stray descendant holding it.
    if let Some(task) = tail_task {
        if let Ok(Ok(tail)) = tokio::time::timeout(Duration::from_millis(500), task).await {
            *tail_out = tail;
        }
    }
    if matches!(step, Step::Reconfigure | Step::Closed) {
        let _ = events.send(LiveEvent::Input {
            state: "idle",
            error: None,
        });
    }
    step
}

/// Result of one `audio_probe`: the summary of the recording, its verdict and the reason when it failed.
#[derive(Clone, Debug, PartialEq)]
pub struct ProbeOutcome {
    pub summary: Summary,
    pub verdict: Verdict,
    pub hint: String,
    pub reason: Option<&'static str>,
}

impl ProbeOutcome {
    pub fn failed(reason: &'static str) -> Self {
        let (verdict, hint) = levels::failed(reason);
        Self {
            summary: Summary {
                frames: 0,
                rms_dbfs: levels::DBFS_MIN,
                peak_dbfs: levels::DBFS_MIN,
                floor_dbfs: levels::DBFS_MIN,
            },
            verdict,
            hint,
            reason: Some(reason),
        }
    }
}

/// Records `PROBE_DURATION` from one device with the same sandboxed recorder as the live input, in
/// its own short-lived process. Nothing is written anywhere; only the summary leaves this function.
pub async fn probe(device: String) -> ProbeOutcome {
    probe_in(&std::env::var_os("PATH").unwrap_or_default(), &device).await
}

/// `probe` with an explicit tool `PATH` (tests put the fake recorder first).
pub async fn probe_in(path: &OsStr, device: &str) -> ProbeOutcome {
    let mut child = match spawn_recorder_in(path, device) {
        Ok(child) => child,
        Err(code) => return ProbeOutcome::failed(code),
    };
    let Some(mut out) = child.stdout.take() else {
        let _ = child.start_kill();
        return ProbeOutcome::failed("recorder_unavailable");
    };
    let deadline = tokio::time::Instant::now() + PROBE_DURATION;
    let mut frames = Vec::new();
    let mut buf = [0u8; FRAME_BYTES];
    let mut ended = false;
    loop {
        match tokio::time::timeout_at(deadline, out.read_exact(&mut buf)).await {
            Ok(Ok(_)) => frames.push(levels::frame_stats(&buf)),
            Ok(Err(_)) => {
                ended = true;
                break;
            }
            // The 3 s are spent: a partial frame at the end is dropped on purpose.
            Err(_) => break,
        }
    }
    let _ = child.start_kill();
    let _ = child.wait().await;
    if ended && frames.is_empty() {
        return ProbeOutcome::failed("recorder_exited");
    }
    let summary = levels::summarize(&frames);
    let (verdict, hint) = levels::judge(&summary);
    ProbeOutcome {
        summary,
        verdict,
        hint,
        reason: None,
    }
}

/// Records `duration` from one device with the probe's sandboxed recorder and returns the samples (16 kHz mono
/// s16). Used by the microphone assistant (src/mic_assist.rs); nothing is written anywhere. A recorder that
/// ends before its first frame is `recorder_exited`; a partial frame at the end is dropped.
pub async fn record_in(
    path: &OsStr,
    device: &str,
    duration: Duration,
) -> Result<Vec<i16>, &'static str> {
    let mut child = spawn_recorder_in(path, device)?;
    let Some(mut out) = child.stdout.take() else {
        let _ = child.start_kill();
        return Err("recorder_unavailable");
    };
    let deadline = tokio::time::Instant::now() + duration;
    let mut samples = Vec::new();
    let mut buf = [0u8; FRAME_BYTES];
    let mut ended = false;
    loop {
        match tokio::time::timeout_at(deadline, out.read_exact(&mut buf)).await {
            Ok(Ok(_)) => samples.extend(
                buf.chunks_exact(2)
                    .map(|pair| i16::from_le_bytes([pair[0], pair[1]])),
            ),
            Ok(Err(_)) => {
                ended = true;
                break;
            }
            Err(_) => break,
        }
    }
    let _ = child.start_kill();
    let _ = child.wait().await;
    if ended && samples.is_empty() {
        return Err("recorder_exited");
    }
    Ok(samples)
}

/// Where speech PCM goes when `--live-audio` is on, and where its state is reported.
#[derive(Clone)]
pub struct Playback {
    pub device: String,
    pub events: mpsc::UnboundedSender<LiveEvent>,
}

/// One supervised player process (stdin carries raw s16le PCM at 24 kHz).
pub struct Player {
    child: Child,
    stdin: Option<ChildStdin>,
}

impl Player {
    pub fn start(device: &str) -> Result<Self, &'static str> {
        Self::start_in(&std::env::var_os("PATH").unwrap_or_default(), device)
    }

    /// Same as `start` with an explicit tool `PATH` (tests put fake tools first).
    pub fn start_in(path: &OsStr, device: &str) -> Result<Self, &'static str> {
        if !device_ok(device) {
            return Err("invalid_device");
        }
        let (program, tool) =
            find_tool(path, &["pw-play", "paplay"]).ok_or("player_unavailable")?;
        let mut command =
            sandboxed(&program, &player_args(tool, device)).map_err(|_| "sandbox_unavailable")?;
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        let mut child = command.spawn().map_err(|_| "player_unavailable")?;
        let stdin = child.stdin.take().ok_or("player_unavailable")?;
        Ok(Self {
            child,
            stdin: Some(stdin),
        })
    }

    pub async fn write(&mut self, bytes: &[u8]) -> Result<(), &'static str> {
        let stdin = self.stdin.as_mut().ok_or("player_write_failed")?;
        match tokio::time::timeout(WRITE_TIMEOUT, stdin.write_all(bytes)).await {
            Ok(Ok(())) => Ok(()),
            _ => Err("player_write_failed"),
        }
    }

    /// Closes the input and waits for a clean exit; a late player is killed.
    pub async fn finish(mut self) -> Result<(), &'static str> {
        drop(self.stdin.take());
        match tokio::time::timeout(PLAYER_EXIT, self.child.wait()).await {
            Ok(Ok(status)) if status.success() => Ok(()),
            Ok(_) => Err("player_failed"),
            Err(_) => {
                let _ = self.child.start_kill();
                Err("player_timeout")
            }
        }
    }
}

/// Speech output for one job. Failure never stops the speech job (the virtual sink still runs).
pub struct LiveOutput {
    playback: Option<Playback>,
    player: Option<Player>,
}

impl LiveOutput {
    pub fn new(playback: Option<Playback>) -> Self {
        Self {
            playback,
            player: None,
        }
    }

    fn emit(&self, state: &'static str, error: Option<&'static str>) {
        if let Some(playback) = self.playback.as_ref() {
            let _ = playback.events.send(LiveEvent::Output { state, error });
        }
    }

    pub fn start(&mut self) {
        let Some(device) = self.playback.as_ref().map(|p| p.device.clone()) else {
            return;
        };
        match Player::start(&device) {
            Ok(player) => {
                self.player = Some(player);
                self.emit("playing", None);
            }
            Err(code) => self.emit("error", Some(code)),
        }
    }

    pub async fn write(&mut self, samples: &[f32], volume: u8) {
        let Some(player) = self.player.as_mut() else {
            return;
        };
        if let Err(code) = player.write(&pcm_s16le(samples, volume)).await {
            // Dropping the player kills the process.
            self.player = None;
            self.emit("error", Some(code));
        }
    }

    /// `ok`: the speech job completed, so close the input and wait. Otherwise the player is killed.
    pub async fn finish(&mut self, ok: bool) {
        let Some(player) = self.player.take() else {
            return;
        };
        if !ok {
            drop(player);
            self.emit("idle", None);
            return;
        }
        match player.finish().await {
            Ok(()) => self.emit("idle", None),
            Err(code) => self.emit("error", Some(code)),
        }
    }
}

impl Drop for LiveOutput {
    fn drop(&mut self) {
        // A cancelled or aborted speech job still owned a player: report it stopped.
        if self.player.is_some() {
            self.emit("idle", None);
        }
    }
}

/// Speech samples as s16le at the job's output gain (same gain as the virtual sink).
pub fn pcm_s16le(samples: &[f32], volume: u8) -> Vec<u8> {
    let gain = f32::from(volume) / 100.0;
    samples
        .iter()
        .flat_map(|sample| {
            let value = (sample * gain).clamp(-1.0, 1.0);
            ((value * 32767.0).round() as i16).to_le_bytes()
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn device_argument_is_passed_only_when_named() {
        assert_eq!(
            recorder_args("pw-record", "alsa_input.x"),
            [
                "--raw",
                "--rate",
                "16000",
                "--channels",
                "1",
                "--format",
                "s16",
                "--target",
                "alsa_input.x",
                "-"
            ]
        );
        assert!(!recorder_args("pw-record", "default")
            .iter()
            .any(|a| a == "--target"));
        assert_eq!(
            recorder_args("parecord", "alsa_input.x").last().unwrap(),
            "--device=alsa_input.x"
        );
        assert_eq!(player_args("pw-play", "default").last().unwrap(), "-");
        assert_eq!(player_args("pw-play", "default")[0], "--raw");
        assert!(player_args("paplay", "default")
            .iter()
            .all(|a| !a.starts_with("--device")));
    }

    #[test]
    fn view_reports_mic_only_while_capturing() {
        let mut state = LiveState::default();
        let now = Instant::now();
        assert!(!state.view(false, now).mic_active);
        state.apply(LiveEvent::Input {
            state: "capturing",
            error: None,
        });
        assert!(state.view(false, now).mic_active);
        state.apply(LiveEvent::Input {
            state: "error",
            error: Some("recorder_exited"),
        });
        let view = state.view(false, now);
        assert!(!view.mic_active);
        assert_eq!(view.last_error, Some("recorder_exited"));
    }

    #[test]
    fn restart_is_required_only_when_the_ledger_differs_from_the_start() {
        let mut state = LiveState::default();
        // Off at start, consent given: the next start applies it.
        state.configure(false, false);
        let now = Instant::now();
        assert!(state.view(true, now).restart_required);
        assert!(!state.view(false, now).restart_required);
        // On from the ledger at start, consent withdrawn: the running pipeline stops at the next start.
        state.configure(true, true);
        assert!(!state.view(true, now).restart_required);
        assert!(state.view(false, now).restart_required);
        // On by the flag only: the ledger (off) is what it was at start, so nothing is pending.
        state.configure(true, false);
        assert!(!state.view(false, now).restart_required);
    }

    #[test]
    fn worker_mounts_include_assets_and_vad_directory() {
        let dir = tempfile::tempdir().unwrap();
        let manifest = dir.path().join("manifest.json");
        std::fs::write(
            &manifest,
            r#"{"asset_root":"/opt/assets/wake","vad":{"path":"/opt/assets/vad/silero.onnx"}}"#,
        )
        .unwrap();
        assert_eq!(
            worker_mounts(&manifest).unwrap(),
            [
                manifest.clone(),
                PathBuf::from("/opt/assets/wake"),
                PathBuf::from("/opt/assets/vad"),
            ]
        );
        // The test-only energy manifest names no assets: only the manifest itself is mounted.
        std::fs::write(&manifest, r#"{"test_only":true}"#).unwrap();
        assert_eq!(worker_mounts(&manifest).unwrap(), [manifest.clone()]);
        std::fs::write(&manifest, r#"{"asset_root":"relative/assets"}"#).unwrap();
        assert!(worker_mounts(&manifest).is_err());
    }

    #[test]
    fn worker_failures_map_to_content_free_reasons() {
        let traceback = b"Traceback (most recent call last):\n  import sherpa_onnx\nModuleNotFoundError: No module named 'sherpa_onnx'\n";
        assert_eq!(
            reason_for("wake_worker_failed", traceback),
            WORKER_IMPORT_ERROR
        );
        let missing = b"FileNotFoundError: [Errno 2] No such file or directory: '/x/encoder.onnx'";
        assert_eq!(reason_for("wake_worker_failed", missing), MODEL_MISSING);
        let hashes = b"ValueError: missing or unexpected artifact hashes";
        assert_eq!(reason_for("wake_worker_failed", hashes), MODEL_MISSING);
        let manifest = b"json.decoder.JSONDecodeError: Expecting value";
        assert_eq!(reason_for("wake_worker_failed", manifest), WORKER_CRASHED);
        assert_eq!(reason_for("wake_worker_unavailable", b""), WORKER_CRASHED);
        assert_eq!(reason_for("recorder_exited", b""), RECORDER_EXITED);
        assert_eq!(reason_for("recorder_unavailable", b""), DEVICE_UNAVAILABLE);
        assert_eq!(reason_for("invalid_device", b""), DEVICE_UNAVAILABLE);
    }

    #[test]
    fn last_error_file_is_private_and_replaced_on_each_failure() {
        use std::os::unix::fs::PermissionsExt;
        let root = tempfile::tempdir().unwrap();
        write_last_error(root.path(), b"first").unwrap();
        write_last_error(root.path(), b"second").unwrap();
        let path = root.path().join(LAST_ERROR_FILE);
        assert_eq!(std::fs::read(&path).unwrap(), b"second");
        let mode = std::fs::metadata(&path).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o600);
    }

    #[test]
    fn keyword_key_follows_sensitivity_and_the_active_list() {
        let mut config = Config::default();
        let base = Settings::from_config(&config).keyword_key;
        config.wake_phrases = vec![crate::phrases::Setting {
            id: "hey_gideon".into(),
            active: true,
            sensitivity: Some(0.8),
        }];
        let with_sensitivity = Settings::from_config(&config).keyword_key;
        assert_ne!(base, with_sensitivity);
        config.wake_sensitivity = 1.4;
        assert_eq!(Settings::from_config(&config).keyword_key, with_sensitivity);
    }

    #[test]
    fn pcm_is_scaled_by_gain_and_clamped() {
        assert_eq!(
            pcm_s16le(&[1.0, -1.0, 2.0], 100),
            [0xff, 0x7f, 0x01, 0x80, 0xff, 0x7f]
        );
        assert_eq!(pcm_s16le(&[1.0], 50), [0x00, 0x40]);
    }
}
