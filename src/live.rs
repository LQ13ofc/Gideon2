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

/// Preference-derived settings the live input follows. A change restarts the pipeline at the next
/// session boundary (the Core only publishes changes while no voice session is active).
#[derive(Clone, Debug, PartialEq)]
pub struct Settings {
    pub input_device: String,
    pub keywords_threshold: f32,
}
impl Settings {
    pub fn from_config(config: &Config) -> Self {
        Self {
            input_device: config.audio_input_device.clone(),
            keywords_threshold: crate::wake::keywords_threshold(config.wake_sensitivity),
        }
    }
}

/// The wake worker that consumes the live stream (same manifest as the replay profile).
#[derive(Clone, Debug)]
pub struct WakeSpec {
    pub python: PathBuf,
    pub manifest: PathBuf,
    pub active_phrase: Option<String>,
}

/// Status transitions reported by the supervisors. Vocabulary is closed.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum LiveEvent {
    Input {
        state: &'static str,
        error: Option<&'static str>,
    },
    Output {
        state: &'static str,
        error: Option<&'static str>,
    },
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct LiveView {
    pub enabled: bool,
    pub input_state: &'static str,
    pub output_state: &'static str,
    pub mic_active: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_error: Option<&'static str>,
}

/// Snapshot block `audio`: `devices` only after an `audio_devices` op, `live` always.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct AudioView {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub devices: Option<Devices>,
    pub live: LiveView,
}

#[derive(Clone, Debug)]
pub struct LiveState {
    enabled: bool,
    input: &'static str,
    output: &'static str,
    error: Option<&'static str>,
}
impl Default for LiveState {
    fn default() -> Self {
        Self {
            enabled: false,
            input: "idle",
            output: "idle",
            error: None,
        }
    }
}
impl LiveState {
    pub fn set_enabled(&mut self, enabled: bool) {
        self.enabled = enabled;
    }
    pub fn apply(&mut self, event: LiveEvent) {
        match event {
            LiveEvent::Input { state, error } => {
                self.input = state;
                if state == "capturing" {
                    self.error = None;
                }
                self.error = error.or(self.error);
            }
            LiveEvent::Output { state, error } => {
                self.output = state;
                self.error = error.or(self.error);
            }
        }
    }
    pub fn view(&self) -> LiveView {
        LiveView {
            enabled: self.enabled,
            input_state: self.input,
            output_state: self.output,
            mic_active: self.input == "capturing",
            last_error: self.error,
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

/// Arguments of the recorder: raw s16le mono 16 kHz on stdout.
pub fn recorder_args(tool: &str, device: &str) -> Vec<String> {
    let mut args: Vec<String> = Vec::new();
    if tool == "pw-record" {
        args.extend(["--rate", "16000", "--channels", "1", "--format", "s16"].map(String::from));
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
pub fn player_args(tool: &str, device: &str) -> Vec<String> {
    let mut args: Vec<String> = Vec::new();
    if tool == "pw-play" {
        args.extend(["--rate", "24000", "--channels", "1", "--format", "s16"].map(String::from));
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
    if !device_ok(device) {
        return Err("invalid_device");
    }
    let path = std::env::var_os("PATH").unwrap_or_default();
    let (program, tool) =
        find_tool(&path, &["pw-record", "parecord"]).ok_or("recorder_unavailable")?;
    let mut command =
        sandboxed(&program, &recorder_args(tool, device)).map_err(|_| "sandbox_unavailable")?;
    command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    command.spawn().map_err(|_| "recorder_unavailable")
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
    );
    let mut command = crate::transport::namespace_command(
        &wake.python,
        "scripts/wake_worker.py",
        &args,
        std::slice::from_ref(&wake.manifest),
    )?;
    command.stdin(Stdio::piped());
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
        match run_once(
            &wake,
            &current,
            &mut settings,
            &packets,
            &events,
            &mut clock_us,
        )
        .await
        {
            Step::Reconfigure => {}
            Step::Closed => return,
            Step::Failed(code) => {
                let now = Instant::now();
                while failures
                    .front()
                    .is_some_and(|t| now.duration_since(*t) >= RESTART_WINDOW)
                {
                    failures.pop_front();
                }
                if failures.len() >= RESTART_LIMIT {
                    let _ = events.send(LiveEvent::Input {
                        state: "error",
                        error: Some("restart_limit"),
                    });
                    let _ = packets.send(Err(())).await;
                    return;
                }
                failures.push_back(now);
                let _ = events.send(LiveEvent::Input {
                    state: "error",
                    error: Some(code),
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

async fn run_once(
    wake: &WakeSpec,
    current: &Settings,
    settings: &mut watch::Receiver<Settings>,
    packets: &mpsc::Sender<Result<Packet, ()>>,
    events: &mpsc::UnboundedSender<LiveEvent>,
    clock_us: &mut u64,
) -> Step {
    let mut worker = match spawn_worker(wake, current, *clock_us) {
        Ok(child) => child,
        Err(_) => return Step::Failed("wake_worker_unavailable"),
    };
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
    if matches!(step, Step::Reconfigure | Step::Closed) {
        let _ = events.send(LiveEvent::Input {
            state: "idle",
            error: None,
        });
    }
    step
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
        assert!(player_args("paplay", "default")
            .iter()
            .all(|a| !a.starts_with("--device")));
    }

    #[test]
    fn view_reports_mic_only_while_capturing() {
        let mut state = LiveState::default();
        assert!(!state.view().mic_active);
        state.apply(LiveEvent::Input {
            state: "capturing",
            error: None,
        });
        assert!(state.view().mic_active);
        state.apply(LiveEvent::Input {
            state: "error",
            error: Some("recorder_exited"),
        });
        let view = state.view();
        assert!(!view.mic_active);
        assert_eq!(view.last_error, Some("recorder_exited"));
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
