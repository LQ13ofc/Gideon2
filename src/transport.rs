use crate::{
    audio::AudioFrame,
    core::Core,
    protocol::{Operation, Request, MAX_MESSAGE},
    storage::Storage,
    stt::{SttConfig, SttReply},
    wake::{Packet, WakeDescriptor, WakeInput},
};
use std::{
    fs, io,
    os::unix::fs::PermissionsExt,
    path::PathBuf,
    process::Stdio,
    sync::{Arc, OnceLock},
    time::Duration,
};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    net::{UnixListener, UnixStream},
    process::Command,
    sync::{mpsc, oneshot, watch, Semaphore},
    task::JoinSet,
};

struct Call {
    request: Request,
    reply: oneshot::Sender<Vec<u8>>,
}
fn authenticate(stream: &UnixStream, owner: u32) -> io::Result<()> {
    if stream.peer_cred()?.uid() != owner {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "IPC owner mismatch",
        ));
    }
    Ok(())
}
async fn peer(stream: UnixStream, tx: mpsc::Sender<Call>) -> io::Result<()> {
    // SAFETY: getuid has no arguments or mutable state; authenticate the kernel peer.
    authenticate(&stream, unsafe { libc::getuid() })?;
    let (read, mut write) = stream.into_split();
    let mut read = BufReader::new(read);
    loop {
        let frame =
            tokio::time::timeout(Duration::from_secs(5), request_frame(&mut read)).await??;
        let Some((line, oversized)) = frame else {
            return Ok(());
        };
        let parsed = serde_json::from_slice::<Request>(&line);
        let parsed = if oversized {
            // Only a skill manifest gets an answer; its line was read and discarded in full.
            match parsed {
                Ok(Request {
                    version,
                    request_id,
                    operation: Operation::SkillValidate { .. } | Operation::SkillSaveDraft { .. },
                }) => Ok(Request {
                    version,
                    request_id,
                    operation: Operation::Refused {
                        code: "skill_invalid:oversize",
                    },
                }),
                _ => {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        "message too large",
                    ))
                }
            }
        } else {
            // Only capability_invoke (8 KiB input contract) and skill manifests (16 KiB) may be larger.
            let allowed = match parsed.as_ref().map(|r| &r.operation) {
                Ok(Operation::CapabilityInvoke { .. }) => line.len() <= MAX_INVOKE_MESSAGE,
                Ok(Operation::SkillValidate { .. } | Operation::SkillSaveDraft { .. }) => {
                    line.len() <= MAX_SKILL_MESSAGE
                }
                _ => line.len() <= MAX_MESSAGE,
            };
            if !allowed {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "message too large",
                ));
            }
            parsed
        };
        let response = match parsed {
            Ok(request) => {
                let (reply, rx) = oneshot::channel();
                tx.send(Call { request, reply })
                    .await
                    .map_err(|_| io::Error::other("core stopped"))?;
                rx.await.map_err(|_| io::Error::other("core stopped"))?
            }
            Err(_) => b"{\"version\":1,\"code\":\"invalid_message\"}".to_vec(),
        };
        tokio::time::timeout(Duration::from_secs(2), async {
            write.write_all(&response).await?;
            write.write_all(b"\n").await
        })
        .await??;
    }
}
/// Raw line bound: 8 KiB capability input plus envelope; other operations stay at MAX_MESSAGE.
const MAX_INVOKE_MESSAGE: usize = 16384;
/// Raw line bound for skill manifests: 16 KiB manifest plus envelope. Checked per operation in `peer`.
const MAX_SKILL_MESSAGE: usize = 24576;
/// Largest object line read in full. Past MAX_SKILL_MESSAGE the line is only read and discarded,
/// so `peer` can answer a skill manifest with `skill_invalid:oversize`; anything else closes.
const MAX_DISCARD_MESSAGE: usize = 65536;
/// Exit status of a Core that accepted `core_restart`. `gideon-launch` restarts the Core on it.
pub const RESTART_EXIT_CODE: i32 = 75;
/// Time the restarting Core gives the peer task to write the `ok` line before it shuts down.
const RESTART_REPLY_GRACE: Duration = Duration::from_millis(200);
/// Client request line: bounded by MAX_MESSAGE unless it looks like a JSON object (`{"`), in which
/// case it may reach MAX_INVOKE_MESSAGE; the parsed operation is checked afterwards, and only
/// capability_invoke may actually exceed MAX_MESSAGE. Garbage without a newline closes at 4 KiB.
/// Returns the line and whether it was over MAX_SKILL_MESSAGE (read in full, discarded by `peer`).
async fn request_frame<R: tokio::io::AsyncBufRead + Unpin>(
    read: &mut R,
) -> io::Result<Option<(Vec<u8>, bool)>> {
    let mut bytes = Vec::new();
    loop {
        let chunk = read.fill_buf().await?;
        if chunk.is_empty() {
            return if bytes.is_empty() {
                Ok(None)
            } else {
                Err(io::Error::new(
                    io::ErrorKind::UnexpectedEof,
                    "partial message",
                ))
            };
        }
        let size = chunk
            .iter()
            .position(|c| *c == b'\n')
            .map(|i| i + 1)
            .unwrap_or(chunk.len());
        let total = bytes.len() + size;
        let first = bytes.first().or_else(|| chunk.first());
        let second = bytes.get(1).or_else(|| {
            if bytes.is_empty() {
                chunk.get(1)
            } else {
                chunk.first()
            }
        });
        let object_like = first == Some(&b'{') && second == Some(&b'"');
        if total > MAX_DISCARD_MESSAGE || (total > MAX_MESSAGE && !object_like) {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "message too large",
            ));
        }
        let done = chunk[size - 1] == b'\n';
        bytes.extend_from_slice(&chunk[..size]);
        read.consume(size);
        if done {
            let oversized = bytes.len() > MAX_SKILL_MESSAGE;
            return Ok(Some((bytes, oversized)));
        }
    }
}
pub(crate) async fn bounded_frame<R: tokio::io::AsyncBufRead + Unpin>(
    read: &mut R,
    limit: usize,
) -> io::Result<Option<Vec<u8>>> {
    let mut bytes = Vec::new();
    loop {
        let chunk = read.fill_buf().await?;
        if chunk.is_empty() {
            return if bytes.is_empty() {
                Ok(None)
            } else {
                Err(io::Error::new(
                    io::ErrorKind::UnexpectedEof,
                    "partial message",
                ))
            };
        }
        let size = chunk
            .iter()
            .position(|c| *c == b'\n')
            .map(|i| i + 1)
            .unwrap_or(chunk.len());
        if bytes.len() + size > limit {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "message too large",
            ));
        }
        let done = chunk[size - 1] == b'\n';
        bytes.extend_from_slice(&chunk[..size]);
        read.consume(size);
        if done {
            return Ok(Some(bytes));
        }
    }
}
pub struct WakeReplay {
    pub python: PathBuf,
    pub manifest: PathBuf,
    pub fixture: usize,
    pub active_phrase: Option<String>,
}
static HOME: OnceLock<PathBuf> = OnceLock::new();

/// Accepts only an absolute, existing, non-symlink directory for `--home`.
pub fn validate_home(path: &std::path::Path) -> io::Result<PathBuf> {
    let invalid = || io::Error::new(io::ErrorKind::InvalidInput, "invalid --home");
    if !path.is_absolute() {
        return Err(invalid());
    }
    let metadata = fs::symlink_metadata(path).map_err(|_| invalid())?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(invalid());
    }
    Ok(path.to_path_buf())
}

/// Sets the Core home once at startup; unset means the development default.
pub fn set_home(path: PathBuf) -> io::Result<()> {
    let validated = validate_home(&path)?;
    HOME.set(validated)
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "invalid --home"))
}

pub fn home() -> &'static std::path::Path {
    HOME.get().map_or(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")),
        PathBuf::as_path,
    )
}

static DATA_DIR: OnceLock<PathBuf> = OnceLock::new();
static FIXTURES_DIR: OnceLock<PathBuf> = OnceLock::new();

/// Sets the user data directory once at startup (`--data-dir`). Same validation as `--home`.
pub fn set_data_dir(path: PathBuf) -> io::Result<()> {
    let invalid = || io::Error::new(io::ErrorKind::InvalidInput, "invalid --data-dir");
    let validated = validate_home(&path).map_err(|_| invalid())?;
    DATA_DIR.set(validated).map_err(|_| invalid())
}

/// Where user-visible data lives: skill exports and imports and the synthetic world. A package
/// keeps `--home` read-only and hash-verified, so it passes a private `--data-dir`; without the
/// option the data lives under `home()` (development layout).
pub fn data_dir() -> &'static std::path::Path {
    DATA_DIR.get().map_or_else(home, PathBuf::as_path)
}

/// Test only (`--test-fixtures-dir`): directory that holds `tests/fixtures/...` for the fake MCP
/// server. Production packages never set it and carry no fixtures.
pub fn set_fixtures_dir(path: PathBuf) -> io::Result<()> {
    let invalid = || io::Error::new(io::ErrorKind::InvalidInput, "invalid --test-fixtures-dir");
    let validated = validate_home(&path).map_err(|_| invalid())?;
    FIXTURES_DIR.set(validated).map_err(|_| invalid())
}

pub fn fixtures_dir() -> &'static std::path::Path {
    FIXTURES_DIR.get().map_or_else(home, PathBuf::as_path)
}

pub(crate) fn namespace_command(
    python: &std::path::Path,
    script: &str,
    args: &[String],
    mounts: &[PathBuf],
) -> io::Result<Command> {
    namespace_command_in(home(), python, script, args, mounts)
}

pub(crate) fn namespace_command_in(
    home: &std::path::Path,
    python: &std::path::Path,
    script: &str,
    args: &[String],
    mounts: &[PathBuf],
) -> io::Result<Command> {
    let interpreter = match fs::read_link(python) {
        Ok(target) if target.is_relative() => python
            .parent()
            .unwrap_or(std::path::Path::new("/"))
            .join(target),
        Ok(target) => target,
        Err(_) => python.to_path_buf(),
    };
    let runtime = interpreter
        .parent()
        .and_then(|p| p.parent())
        .ok_or_else(|| io::Error::other("python runtime missing"))?;
    let canonical = fs::canonicalize(runtime)?;
    let mut cmd = Command::new("/usr/bin/bwrap");
    // Workers inherit only explicitly required settings, never ambient credentials.
    cmd.env_clear()
        .env("PATH", "/usr/bin:/bin")
        .env("OMP_NUM_THREADS", "1")
        .env("OPENBLAS_NUM_THREADS", "1");
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
    ])
    .arg("--ro-bind")
    .arg(&canonical)
    .arg(&canonical)
    .arg("--ro-bind")
    .arg(&canonical)
    .arg(runtime)
    .arg("--ro-bind")
    .arg(home)
    .arg(home);
    for path in mounts {
        if !path.is_absolute() {
            return Err(io::Error::other("absolute mount required"));
        }
        cmd.arg("--ro-bind").arg(path).arg(path);
    }
    cmd.args(["--setenv", "HOME", "/tmp", "--chdir", "/tmp", "--"])
        .arg(python)
        .arg("-I")
        .arg(home.join(script))
        .args(args)
        .env_remove("DBUS_SESSION_BUS_ADDRESS")
        .env_remove("PULSE_SERVER")
        .stderr(Stdio::null())
        .stdout(Stdio::piped())
        .kill_on_drop(true);
    Ok(cmd)
}
/// Live wiring handed to the wake pipeline when `--live-audio` is on (settings follow the ledger).
type LiveWiring = (
    watch::Receiver<crate::live::Settings>,
    mpsc::UnboundedSender<crate::live::LiveEvent>,
);

/// Starts the single wake producer: the live input supervisor when wiring is present (A5), otherwise
/// the fixture replay worker, which takes its threshold at spawn time.
fn start_wake(
    replay: WakeReplay,
    tx: mpsc::Sender<Result<Packet, ()>>,
    live: &mut Option<LiveWiring>,
    threshold: f32,
) -> tokio::task::JoinHandle<()> {
    match live.take() {
        Some((settings, events)) => {
            let wake = crate::live::WakeSpec {
                python: replay.python,
                manifest: replay.manifest,
                active_phrase: replay.active_phrase,
            };
            tokio::spawn(crate::live::run_input(wake, settings, tx, events))
        }
        None => tokio::spawn(replay_worker(replay, tx, threshold)),
    }
}

async fn replay_worker(replay: WakeReplay, tx: mpsc::Sender<Result<Packet, ()>>, threshold: f32) {
    let outcome = async {
        let manifest: serde_json::Value = serde_json::from_slice(&fs::read(&replay.manifest)?)?;
        let fixture = manifest["fixtures"]
            .get(replay.fixture)
            .and_then(|r| r["path"].as_str())
            .ok_or_else(|| io::Error::other("fixture missing"))?;
        let fixture_root = std::path::Path::new(fixture)
            .parent()
            .ok_or_else(|| io::Error::other("fixture root missing"))?;
        let asset_root = manifest["asset_root"]
            .as_str()
            .ok_or_else(|| io::Error::other("assets missing"))?;
        if !fixture_root.is_absolute() || !std::path::Path::new(asset_root).is_absolute() {
            return Err(io::Error::other("absolute assets required"));
        }
        let args = crate::wake::worker_args(
            &replay.manifest.to_string_lossy(),
            crate::wake::WorkerMode::Replay {
                fixture: replay.fixture,
            },
            replay.active_phrase.as_deref(),
            threshold,
            None,
        );
        let mut mounts = vec![
            fixture_root.to_path_buf(),
            asset_root.into(),
            replay.manifest.clone(),
        ];
        mounts.extend(crate::live::keyword_dir(&replay.manifest)?);
        let mut command =
            namespace_command(&replay.python, "scripts/wake_worker.py", &args, &mounts)?;
        let mut child = command
            .env_remove("DBUS_SESSION_BUS_ADDRESS")
            .env_remove("PULSE_SERVER")
            .stdin(Stdio::null())
            .stderr(Stdio::null())
            .stdout(Stdio::piped())
            .kill_on_drop(true)
            .spawn()?;
        let mut output = BufReader::new(
            child
                .stdout
                .take()
                .ok_or_else(|| io::Error::other("worker stdout"))?,
        );
        loop {
            let line =
                tokio::time::timeout(Duration::from_secs(10), bounded_frame(&mut output, 65536))
                    .await??;
            let Some(line) = line else {
                break;
            };
            let packet: Packet = serde_json::from_slice(&line)?;
            tx.send(Ok(packet))
                .await
                .map_err(|_| io::Error::other("owner stopped"))?;
        }
        if !child.wait().await?.success() {
            return Err(io::Error::other("worker failed"));
        }
        Ok::<_, io::Error>(())
    }
    .await;
    if outcome.is_err() {
        let _ = tx.send(Err(())).await;
    }
}
/// Applies Core plugin intents and feeds immediate host results back to the Core.
fn pump_plugins(
    core: &mut Core,
    plugins: &mut crate::plugins::Host,
    root: &std::path::Path,
    now: std::time::Instant,
) {
    for intent in core.take_plugin_intents() {
        for event in plugins.apply(intent, root) {
            core.plugin_event(event, now);
        }
    }
}
/// The STT worker failed (or its backlog overflowed): the session ends, the stderr tail goes to the 0600 diagnostics
/// file, and a restart is booked while the budget lasts. Returns whether a restart was booked (`starting`); when it
/// was not, the status is `failed` for the rest of the run.
fn stt_down(
    core: &mut Core,
    stt: &mut crate::stt::Pipe,
    root: &std::path::Path,
    reason: &'static str,
    tail: &[u8],
) -> bool {
    if !tail.is_empty() {
        let _ = crate::live::write_private_file(&root.join(crate::stt::LAST_ERROR_FILE), tail);
    }
    stt.abort();
    // A missing import or a model that fails its hashes fails the same way on every start: no restart.
    let deterministic = matches!(
        reason,
        crate::live::WORKER_IMPORT_ERROR | crate::live::MODEL_MISSING
    );
    if !deterministic && stt.schedule_restart(std::time::Instant::now()) {
        core.stt_restarting(reason);
        true
    } else {
        core.stt_failed_with(reason);
        false
    }
}

/// Connection audit lines: a closed vocabulary written with the current response sequence.
fn write_connection_audit(core: &mut Core, storage: &Storage) {
    let audits = core.take_connection_audit();
    if audits.is_empty() {
        return;
    }
    let sequence = core.response(String::new(), "ok").sequence;
    for audit in audits {
        // Vocabulary is static and closed; a failed append never stops the Core.
        let _ = storage.audit_connection(
            sequence,
            audit.kind,
            audit.operation,
            audit.risk,
            audit.outcome,
        );
    }
}
#[allow(clippy::too_many_arguments)]
pub async fn serve(
    mut storage: Storage,
    virtual_input: bool,
    mut replay: Option<WakeReplay>,
    mut commands_sandbox: bool,
    mut tts: Option<crate::tts::Config>,
    base_pack_path: Option<std::path::PathBuf>,
    hub_catalog: Option<(std::path::PathBuf, String)>,
    plugin_python: Option<std::path::PathBuf>,
    net_allow_loopback: bool,
    live_flag: bool,
) -> io::Result<bool> {
    let mut base_pack =
        if storage.configuration_status == crate::storage::ConfigurationStatus::Ready {
            if let Some(path) = base_pack_path.as_ref() {
                let replay = replay
                    .as_ref()
                    .ok_or_else(|| io::Error::other("Base pack requires wake profile"))?;
                let tts = tts
                    .as_ref()
                    .ok_or_else(|| io::Error::other("Base pack requires TTS profile"))?;
                let pack = crate::pack::load(path, &replay.manifest, &tts.manifest)?;
                if storage
                    .config
                    .wake_phrase
                    .as_ref()
                    .is_some_and(|id| !pack.selectable(id))
                {
                    storage.incompatible_configuration()?;
                }
                Some(pack)
            } else {
                None
            }
        } else {
            None
        };
    // Wake phrases (src/phrases.rs). With a pack, the stored list becomes a keyword set in the Core data dir,
    // preflighted before this start; the worker runs that manifest. The packaged manifest stays the base.
    let phrase_setup = match (base_pack.as_ref(), replay.as_ref()) {
        (Some(pack), Some(r))
            if storage.configuration_status == crate::storage::ConfigurationStatus::Ready =>
        {
            let base = r.manifest.clone();
            let lexicon = base_pack_path
                .as_deref()
                .and_then(|p| crate::phrases::load_lexicon(p, &base))
                .map(std::sync::Arc::new);
            let catalog = crate::phrases::entries(
                &crate::phrases::defaults(&pack.wake_phrases),
                &crate::phrases::read_custom(&storage.root).unwrap_or_default(),
            );
            let stored = crate::phrases::migrated(
                &storage.config.wake_phrases,
                storage.config.wake_phrase.as_deref(),
                &pack.default_phrase,
            );
            let settings = crate::phrases::effective(&catalog, &stored, &pack.default_phrase);
            let manifest = crate::phrases::ensure_boot(
                &storage.root,
                &r.python,
                home(),
                &base,
                &catalog,
                &settings,
                storage.config.wake_sensitivity,
            )
            .ok();
            Some((base, lexicon, manifest))
        }
        _ => None,
    };
    let phrase_runtime = phrase_setup.as_ref().and_then(|(base, lexicon, _)| {
        replay.as_ref().map(|r| crate::phrases::Runtime {
            python: r.python.clone(),
            home: home().to_path_buf(),
            base_manifest: base.clone(),
            lexicon: lexicon.clone(),
            tts: tts.clone(),
        })
    });
    if let Some(manifest) = phrase_setup.and_then(|(_, _, manifest)| manifest) {
        if let Some(r) = replay.as_mut() {
            r.manifest = manifest;
        }
    }
    storage.clear_stale_socket()?;
    let path = storage.socket_path();
    let listener = UnixListener::bind(&path)?;
    fs::set_permissions(&path, fs::Permissions::from_mode(0o600))?;
    let mut core = Core::new(
        Duration::from_millis(storage.config.session_timeout_ms),
        virtual_input,
    );
    let mut seed = [0u8; 8];
    // SAFETY: writable 8-byte buffer; kernel randomness, no personal audio device.
    if unsafe { libc::getrandom(seed.as_mut_ptr().cast(), seed.len(), 0) } != seed.len() as isize {
        return Err(io::Error::last_os_error());
    }
    let epoch = (u64::from_ne_bytes(seed) & (u64::MAX / 2)) | 1;
    core.set_boot_seed(epoch);
    storage.set_safe_epoch(epoch);
    core.configure_storage(&storage);
    core.configure_llm(&storage, net_allow_loopback);
    core.configure_connections(&storage);
    core.configure_registry(&storage);
    if let Some(runtime) = phrase_runtime {
        core.configure_phrases(runtime);
    }
    core.configure_skills(&storage);
    // A6: the ledger's consent starts the same live pipeline as `--live-audio`, and only with a Ready ledger
    // and the wake profile (the live path replaces the boot replay). Safe mode carries the defaults: off.
    let live_from_ledger = storage.configuration_status
        == crate::storage::ConfigurationStatus::Ready
        && storage.config.live_audio
        && replay.is_some();
    let live_audio = live_flag || live_from_ledger;
    core.configure_live(live_audio, live_from_ledger);
    // A13: the device list is ready before the Dispositivos page opens when the live pipeline runs.
    if live_audio {
        core.refresh_audio_devices();
    }
    // A5: live settings (input device, spotter threshold) and live status. Settings are published
    // only between voice sessions, so a running utterance is never cut by a preference change.
    let (live_settings_tx, live_settings_rx) =
        watch::channel(crate::live::Settings::from_config(&storage.config));
    let (live_events_tx, mut live_events_rx) = mpsc::unbounded_channel::<crate::live::LiveEvent>();
    let mut live_wiring: Option<LiveWiring> =
        live_audio.then(|| (live_settings_rx, live_events_tx.clone()));
    if let Some((path, digest)) = hub_catalog {
        core.configure_hub(
            crate::hub::load(&path, &digest)
                .unwrap_or_else(|_| crate::hub::Snapshot::quarantined())
                .with_approvals(&storage),
        );
    }
    let (plugin_events_tx, mut plugin_events) = mpsc::unbounded_channel();
    let broker_script = home().join("scripts/net_broker.py");
    let mut plugins = crate::plugins::Host::new(
        plugin_python.clone(),
        broker_script.clone(),
        plugin_events_tx,
    );
    core.configure_plugins(&storage, plugin_python.is_some());
    pump_plugins(
        &mut core,
        &mut plugins,
        &storage.root,
        std::time::Instant::now(),
    );
    if storage.configuration_status != crate::storage::ConfigurationStatus::Ready {
        replay = None;
        tts = None;
        commands_sandbox = false;
        if let Some(pack) = base_pack.as_mut() {
            pack.active_phrase = None;
        }
    }

    // STT worker owner (src/stt.rs): live audio merges frames into 160 ms messages; the replay path does not.
    let mut stt_config: Option<SttConfig> = None;
    if let Some(r) = replay.as_ref() {
        let manifest: serde_json::Value = serde_json::from_slice(&fs::read(&r.manifest)?)?;
        if !manifest["stt"].is_null() {
            let config: SttConfig = serde_json::from_value(manifest["stt"].clone())?;
            let profile: serde_json::Value = serde_json::from_slice(&fs::read(&config.manifest)?)?;
            let engine = profile["engine"]
                .as_str()
                .ok_or_else(|| io::Error::other("STT engine missing"))?;
            core.configure_stt(engine.into());
            stt_config = Some(config);
        }
    }
    let mut stt = crate::stt::Pipe::new(stt_config, live_audio);
    stt.start();
    let (wake_sender, mut wake_rx) = mpsc::channel(2);
    let mut wake_tx = Some(wake_sender);
    let mut command_wake_texts: Vec<String> = Vec::new();
    let mut wake_input = match replay.as_mut() {
        Some(r) => {
            let bytes = fs::read(&r.manifest)?;
            if bytes.len() > 1_048_576 {
                return Err(io::Error::other("wake manifest too large"));
            }
            if serde_json::from_slice::<serde_json::Value>(&bytes)?["vad"].is_object() {
                core.enable_capture();
            }
            let mut descriptor: WakeDescriptor = serde_json::from_slice(&bytes)?;
            // A Core keyword set names its own active list. Without one, the packaged manifest runs the stored
            // legacy phrase only when it is one of its own. Any other stored phrase fails closed (A1 contract:
            // the active phrase must exist in the catalog); the config is left unchanged and nothing is started.
            if descriptor.active_phrases.is_empty() {
                if let Some(phrase) = storage.config.wake_phrase.as_ref() {
                    if !descriptor.supported_phrases.contains_key(phrase.as_str()) {
                        return Err(io::Error::other("configured wake phrase is not supported"));
                    }
                    descriptor.active_phrase = phrase.clone();
                }
            }
            let custom = crate::phrases::read_custom(&storage.root).unwrap_or_default();
            if let Some(pack) = base_pack.as_mut() {
                pack.active_phrase = Some(descriptor.active_phrase.clone());
                command_wake_texts = descriptor
                    .active_ids()
                    .iter()
                    .map(|id| {
                        pack.text(id)
                            .map(str::to_string)
                            .or_else(|| {
                                custom
                                    .phrases
                                    .iter()
                                    .find(|p| &p.id == id)
                                    .map(|p| p.text.clone())
                            })
                            .ok_or_else(|| io::Error::other("wake phrase missing"))
                    })
                    .collect::<io::Result<Vec<String>>>()?;
            } else {
                command_wake_texts = descriptor
                    .active_ids()
                    .iter()
                    .filter_map(|id| descriptor.supported_phrases.get(id))
                    .map(|label| label.replace('_', " "))
                    .collect();
            }
            r.active_phrase = Some(descriptor.active_phrase.clone());
            let mut input =
                WakeInput::new(descriptor).map_err(|_| io::Error::other("invalid wake catalog"))?;
            input
                .set_sensitivity(storage.config.wake_sensitivity)
                .map_err(|_| io::Error::other("invalid wake sensitivity"))?;
            Some(input)
        }
        None => None,
    };
    if let Some(pack) = base_pack {
        core.configure_pack(pack);
    }
    if commands_sandbox {
        core.configure_command_wakes(command_wake_texts);
    }
    // Test/dev only: shortens the 120 s proposal TTL (100..=120000 ms). Unset means production.
    let tool_ttl = match std::env::var("GIDEON_TOOL_PROPOSAL_TTL_MS") {
        Ok(raw) => Duration::from_millis(
            raw.parse::<u64>()
                .ok()
                .filter(|ms| (100..=120_000).contains(ms))
                .ok_or_else(|| io::Error::other("invalid tool proposal ttl"))?,
        ),
        Err(_) => crate::tools::DEFAULT_TTL,
    };
    core.configure_tools(tool_ttl, commands_sandbox);
    let mut command_task: Option<(
        crate::commands::Job,
        tokio::task::JoinHandle<Result<crate::commands::Receipt, &'static str>>,
    )> = None;
    let mut tool_task: Option<(
        crate::commands::Job,
        tokio::task::JoinHandle<Result<crate::commands::Receipt, &'static str>>,
    )> = None;
    if tts.is_some() {
        core.enable_tts();
    }
    // S5 connection job: at most one network job at a time (the Manager enforces it).
    let mut connection_task: Option<(u64, tokio::task::JoinHandle<crate::connections::Done>)> =
        None;
    let mut speech_task: Option<(
        u64,
        tokio::task::JoinHandle<io::Result<crate::tts::Summary>>,
    )> = None;
    // Synthetic wake measurement of one custom phrase (src/phrases.rs run_test); at most one at a time.
    let mut phrase_task: Option<(
        String,
        tokio::task::JoinHandle<io::Result<crate::phrases::Measurement>>,
    )> = None;
    // A9 `audio_probe`: one 3 s recording at a time, in its own task (the Core loop never blocks on it).
    let mut probe_task: Option<(u64, tokio::task::JoinHandle<crate::live::ProbeOutcome>)> = None;
    // A13 microphone assistant: one run at a time (the Core refuses a second one while it runs).
    let mut recommend_task: Option<(u64, tokio::task::JoinHandle<crate::mic_assist::Done>)> = None;
    let (speech_progress, mut speech_progress_rx) = mpsc::channel(2);
    let mut pending_replay = if stt.configured() {
        replay.take()
    } else {
        None
    };
    let startup_threshold = crate::wake::keywords_threshold(storage.config.wake_sensitivity);
    let mut wake_task = if pending_replay.is_some() {
        None
    } else {
        replay.map(|r| {
            start_wake(
                r,
                wake_tx.take().expect("single audio producer"),
                &mut live_wiring,
                startup_threshold,
            )
        })
    };
    if wake_task.is_some() || pending_replay.is_some() {
        core.wake_health("starting");
    }
    let (tx, mut rx) = mpsc::channel::<Call>(16);
    let slots = Arc::new(Semaphore::new(8));
    let mut peers = JoinSet::new();
    let mut restart = false;
    let mut shutdown = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    loop {
        let deadline = core.deadline();
        let tool_deadline = core.tool_deadline();
        let import_deadline = crate::hub::import_deadline(&storage);
        let stt_restart = stt.restart_at();
        let stt_backlogged = stt.pending();
        tokio::select! {
            _ = shutdown.recv() => break,
            _ = async { match import_deadline { Some(d) => tokio::time::sleep_until(d.into()).await, None => std::future::pending::<()>().await } } => {
                if crate::hub::expire_import(&mut storage, std::time::Instant::now()) { core.hub_import_expired(&storage); storage.audit(core.response(String::new(), "ok").sequence)?; }
            },
            _ = tokio::signal::ctrl_c() => break,
            _ = async { match deadline { Some(d) => tokio::time::sleep_until(d.into()).await, None => std::future::pending::<()>().await } } => { core.expire(std::time::Instant::now()); storage.audit(core.response(String::new(), "ok").sequence)?; },
            result = async { (&mut command_task.as_mut().expect("active task").1).await }, if command_task.is_some() => {
                let (job, _) = command_task.take().expect("active task");
                match result {
                    Ok(Ok(receipt)) => core.command_reply(job, Some(receipt), std::time::Instant::now()),
                    // A11: host codes (app_not_installed, volume_unverified, ...) reach the user; a crashed task is generic.
                    Ok(Err(code)) => core.command_error(job, code, std::time::Instant::now()),
                    Err(_) => core.command_error(job, "command_failed", std::time::Instant::now()),
                }
                storage.audit(core.response(String::new(), "ok").sequence)?;
            },
            _ = async { match tool_deadline { Some(d) => tokio::time::sleep_until(d.into()).await, None => std::future::pending::<()>().await } } => {
                core.expire_tools(std::time::Instant::now());
                core.connections_tick(&storage, std::time::Instant::now());
                storage.audit(core.response(String::new(), "ok").sequence)?;
            },
            result = async { (&mut connection_task.as_mut().expect("active connection task").1).await }, if connection_task.is_some() => {
                let (id, _) = connection_task.take().expect("active connection task");
                match result {
                    Ok(done) => core.connection_reply(&storage, done, std::time::Instant::now()),
                    // A job that ended without a reply must not hold the single network slot.
                    Err(_) => core.connection_abandoned(id),
                }
                storage.audit(core.response(String::new(), "ok").sequence)?;
            },
            result = async { (&mut tool_task.as_mut().expect("active tool task").1).await }, if tool_task.is_some() => {
                let (job, _) = tool_task.take().expect("active tool task");
                core.tool_reply(job, result.ok().and_then(Result::ok), std::time::Instant::now());
                storage.audit(core.response(String::new(), "ok").sequence)?;
            },
            result = async { (&mut speech_task.as_mut().expect("active speech task").1).await }, if speech_task.is_some() => {
                let (id,_) = speech_task.take().expect("active speech task");
                core.speech_reply(id,result.ok().and_then(Result::ok),std::time::Instant::now());
                storage.audit(core.response(String::new(), "ok").sequence)?;
            },
            Some((id,samples))=speech_progress_rx.recv() => {core.speech_progress(id,samples);},
            result = async { (&mut probe_task.as_mut().expect("active probe").1).await }, if probe_task.is_some() => {
                let (id, _) = probe_task.take().expect("active probe");
                // A task that ended without an outcome is reported as a recorder that gave no audio.
                let outcome = result.unwrap_or_else(|_| crate::live::ProbeOutcome::failed("recorder_exited"));
                core.audio_probe_reply(id, outcome);
                storage.audit(core.response(String::new(), "ok").sequence)?;
            },
            result = async { (&mut phrase_task.as_mut().expect("active phrase test").1).await }, if phrase_task.is_some() => {
                let (id, _) = phrase_task.take().expect("active phrase test");
                let measured = result.ok().and_then(Result::ok);
                let ok = measured.is_some();
                if let Some(measurement) = measured {
                    let _ = crate::phrases::record_measurement(&storage.root, &id, measurement);
                }
                core.phrase_test_finished(&id, ok);
                core.configure_storage(&storage);
                storage.audit(core.response(String::new(), "ok").sequence)?;
            },
            Some(event)=live_events_rx.recv() => {
                // A13: the last worker stderr tail goes to the 0600 diagnostics file only (never to the snapshot).
                if let crate::live::LiveEvent::WorkerTail { tail } = &event {
                    let _ = crate::live::write_last_error(&storage.root, tail);
                }
                core.live_event(event);
            },
            result = async { (&mut recommend_task.as_mut().expect("active recommendation").1).await }, if recommend_task.is_some() => {
                let (id, _) = recommend_task.take().expect("active recommendation");
                match result {
                    Ok(done) => core.audio_recommend_reply(id, done),
                    Err(_) => core.audio_recommend_failed(id),
                }
                storage.audit(core.response(String::new(), "ok").sequence)?;
            },
            Some(wire) = plugin_events.recv() => {
                if let Some(event) = plugins.accept(wire) {
                    // Plugin logs and partial text are high-rate and never audited (no amplification).
                    let audited = !matches!(event, crate::plugins::Ev::Log { .. } | crate::plugins::Ev::Partial { .. });
                    core.plugin_event(event, std::time::Instant::now());
                    if audited {
                        storage.audit(core.response(String::new(), "ok").sequence)?;
                    }
                }
            },
            Some(call) = rx.recv() => {
                let response = core.handle_with_storage(call.request, std::time::Instant::now(), Some(&mut storage));
                // Live wake sensitivity: the detector follows the ledger after every control call.
                if let Some(input) = wake_input.as_mut() { let _ = input.set_sensitivity(storage.config.wake_sensitivity); }
                storage.audit(response.sequence)?;
                let _ = call.reply.send(serde_json::to_vec(&response)?);
                if core.restart_requested() {
                    // The peer task writes the `ok` line after this turn; give it time before the
                    // shutdown below aborts the peers. Bounded and local: the socket is a Unix pipe.
                    tokio::time::sleep(RESTART_REPLY_GRACE).await;
                    restart = true;
                    break;
                }
            },
            reply = stt.next_reply(), if stt.running() => {
                let failure = match reply {
                    Some(Ok(r)) => {
                        let ready=matches!(r,SttReply::Ready{..});
                        core.stt_reply(r,std::time::Instant::now());
                        if ready && core.response(String::new(),"ok").stt_status=="ready" {
                            if let Some(replay)=pending_replay.take() { let threshold=crate::wake::keywords_threshold(storage.config.wake_sensitivity); wake_task=Some(start_wake(replay,wake_tx.take().expect("single audio producer"),&mut live_wiring,threshold)); }
                        }
                        None
                    },
                    Some(Err(failure)) => Some(failure),
                    None => Some(crate::stt::Failure { reason: crate::live::WORKER_CRASHED, tail: Vec::new() }),
                };
                if let Some(failure) = failure {
                    let restarting = stt_down(&mut core, &mut stt, &storage.root, failure.reason, &failure.tail);
                    if !restarting && pending_replay.take().is_some() { core.wake_health("unavailable"); wake_tx.take(); }
                }
            },
            // STT supervisor: a booked restart starts a new worker with fresh channels (status `starting` until ready).
            _ = async { match stt_restart { Some(d) => tokio::time::sleep_until(d.into()).await, None => std::future::pending::<()>().await } }, if stt_restart.is_some() => {
                stt.start();
            },
            // Requests waiting for a free slot in the worker queue are offered again shortly.
            _ = tokio::time::sleep(std::time::Duration::from_millis(10)), if stt_backlogged => {},
            packet = wake_rx.recv(), if wake_task.is_some() => {
                match packet {
                    Some(Ok(p)) => {
                        let frame=AudioFrame {timestamp_us:p.timestamp_us,sample_rate:16000,channels:1,samples:p.samples.clone()};
                        let speech=p.speech;
                        match wake_input.as_mut().expect("configured wake input").accept(p) {
                        Ok(detection) => {
                            core.wake_health("replaying");
                            if let Some(found) = detection.as_ref() { core.live_detected(&found.phrase_id); }
                            let pre_roll=if detection.is_some() { wake_input.as_ref().expect("configured wake input").pre_roll() } else { Vec::new() };
                            core.capture_packet(frame,speech,pre_roll,detection.is_some(),std::time::Instant::now());
                        },
                        Err(_) => {
                            core.wake_health("failed");
                            if let Some(task) = wake_task.take() { task.abort(); let _ = task.await; }
                        }
                    }
                    },
                    Some(Err(())) => {
                        core.wake_health("failed");
                        if let Some(task) = wake_task.take() { task.abort(); let _ = task.await; }
                    },
                    None => {
                        core.audio_eof();
                        core.wake_health("replay_finished");
                        if let Some(task) = wake_task.take() { let _ = task.await; }
                    }
                }
                storage.audit(core.response(String::new(), "ok").sequence)?;
            },
            accepted = listener.accept() => {
                let (stream, _) = accepted?;
                if let Ok(permit) = slots.clone().try_acquire_owned() {
                    let tx = tx.clone(); peers.spawn(async move { let _permit = permit; let _ = peer(stream, tx).await; });
                }
            },
            Some(_) = peers.join_next(), if !peers.is_empty() => {},
        }
        if command_task
            .as_ref()
            .is_some_and(|(job, _)| !core.command_is_active(job.session_id))
        {
            if let Some((_, task)) = command_task.take() {
                task.abort();
                let _ = task.await;
            }
        }
        // A11: the executor is chosen when the job starts; the Core refuses to change the mode while a job is queued.
        if let Some(job) = core.take_command_job() {
            let pending = job.clone();
            let host = core.real_actions();
            command_task = Some((
                job,
                tokio::spawn(crate::commands::execute_for(pending, host)),
            ));
        }
        if let Some(job) = core.take_tool_job() {
            let pending = job.clone();
            let host = core.real_actions();
            tool_task = Some((
                job,
                tokio::spawn(crate::commands::execute_for(pending, host)),
            ));
        }
        if connection_task.is_none() {
            if let Some((id, job)) = core.take_connection_job() {
                let python = plugin_python.clone().unwrap_or_default();
                connection_task = Some((
                    id,
                    tokio::spawn(crate::connections::execute(
                        id,
                        job,
                        python,
                        broker_script.clone(),
                    )),
                ));
            }
        }
        if speech_task
            .as_ref()
            .is_some_and(|(id, _)| !core.speech_is_active(*id))
        {
            if let Some((_, task)) = speech_task.take() {
                task.abort();
                let _ = task.await;
            }
        }
        if probe_task.is_none() {
            if let Some((id, device)) = core.take_audio_probe_job() {
                probe_task = Some((id, tokio::spawn(crate::live::probe(device))));
            }
        }
        if recommend_task.is_none() {
            if let Some((id, current)) = core.take_recommend_job() {
                recommend_task = Some((id, tokio::spawn(crate::mic_assist::run(current))));
            }
        }
        if phrase_task.is_none() {
            if let Some(job) = core.take_phrase_job() {
                let id = job.id.clone();
                phrase_task = Some((id, tokio::spawn(crate::phrases::run_test(job))));
            }
        }
        if let Some(job) = core.take_speech_job() {
            let config = tts.as_ref().expect("configured TTS").clone();
            let playback = live_audio.then(|| crate::live::Playback {
                device: storage.config.audio_output_device.clone(),
                events: live_events_tx.clone(),
            });
            speech_task = Some((
                job.session_id,
                tokio::spawn(crate::tts::speak(
                    config,
                    job,
                    speech_progress.clone(),
                    playback,
                )),
            ));
        }
        // A5: a changed device or sensitivity reaches the live input only between voice sessions. A13: and only
        // while the configuration is ready: a pending restart keeps the worker on the list it started with.
        if live_audio
            && !core.voice_active()
            && storage.configuration_status == crate::storage::ConfigurationStatus::Ready
        {
            let desired = crate::live::Settings::from_config(&storage.config);
            if *live_settings_tx.borrow() != desired {
                live_settings_tx.send_replace(desired);
            }
        }
        pump_plugins(
            &mut core,
            &mut plugins,
            &storage.root,
            std::time::Instant::now(),
        );
        write_connection_audit(&mut core, &storage);
        let now = std::time::Instant::now();
        for request in core.take_stt_requests() {
            if let Err(reason) = stt.enqueue(request, now) {
                // Only a stuck worker overflows the bounded backlog; the supervisor restarts it.
                let restarting = stt_down(&mut core, &mut stt, &storage.root, reason, &[]);
                if !restarting && pending_replay.take().is_some() {
                    core.wake_health("unavailable");
                    wake_tx.take();
                }
                break;
            }
        }
        stt.flush(now);
    }
    if let Some((_, task)) = speech_task.take() {
        task.abort();
        let _ = task.await;
    }
    if let Some((_, task)) = phrase_task.take() {
        task.abort();
        let _ = task.await;
    }
    if let Some((_, task)) = probe_task.take() {
        task.abort();
        let _ = task.await;
    }
    if let Some((_, task)) = command_task.take() {
        task.abort();
        let _ = task.await;
    }
    if let Some((_, task)) = tool_task.take() {
        task.abort();
        let _ = task.await;
    }
    if let Some((_, task)) = connection_task.take() {
        task.abort();
        let _ = task.await;
    }
    if let Some(task) = wake_task.take() {
        task.abort();
        let _ = task.await;
    }
    stt.stop().await;
    plugins.shutdown().await;
    // Sandboxed MCP servers die with the Core.
    crate::mcp::stop_all();
    core.shutdown();
    storage.audit(core.response(String::new(), "ok").sequence)?;
    peers.abort_all();
    while peers.join_next().await.is_some() {}
    fs::remove_file(path)?;
    Ok(restart)
}

#[cfg(test)]
mod tests {
    #[tokio::test]
    async fn actual_socket_credentials_match_owner_and_reject_other_uid() {
        let (socket, _) = tokio::net::UnixStream::pair().unwrap();
        let actual = socket.peer_cred().unwrap().uid();
        assert!(super::authenticate(&socket, actual).is_ok());
        assert_eq!(
            super::authenticate(&socket, actual.wrapping_add(1))
                .unwrap_err()
                .kind(),
            std::io::ErrorKind::PermissionDenied
        );
    }
    #[tokio::test]
    async fn namespace_has_private_home_and_no_ambient_fixture_secret() {
        let output = super::namespace_command(
            std::path::Path::new("/usr/bin/python3"),
            "scripts/namespace_probe.py",
            &[],
            &[],
        )
        .unwrap()
        .output()
        .await
        .unwrap();
        assert!(output.status.success());
        let value: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
        assert_eq!(value["secret_present"], false);
        assert_eq!(value["private_home"], true);
    }
    #[test]
    fn namespace_command_uses_given_home_for_bind_and_script() {
        let home = tempfile::tempdir().unwrap();
        let home_str = home.path().to_string_lossy().into_owned();
        let command = super::namespace_command_in(
            home.path(),
            std::path::Path::new("/usr/bin/python3"),
            "scripts/wake_worker.py",
            &[],
            &[],
        )
        .unwrap();
        let args: Vec<String> = command
            .as_std()
            .get_args()
            .map(|a| a.to_string_lossy().into_owned())
            .collect();
        assert!(args
            .windows(3)
            .any(|w| w[0] == "--ro-bind" && w[1] == home_str && w[2] == home_str));
        let script = format!("{home_str}/scripts/wake_worker.py");
        assert!(args.contains(&script));
        assert!(!args.iter().any(|a| a.contains(env!("CARGO_MANIFEST_DIR"))));
    }
}
