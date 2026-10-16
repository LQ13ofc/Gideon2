use crate::{
    audio::AudioFrame,
    core::Core,
    protocol::{Operation, Request, MAX_MESSAGE},
    storage::Storage,
    stt::{SttConfig, SttReply, SttRequest},
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
    sync::{mpsc, oneshot, Semaphore},
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
        let line = tokio::time::timeout(Duration::from_secs(5), request_frame(&mut read)).await??;
        let Some(line) = line else {
            return Ok(());
        };
        let parsed = serde_json::from_slice::<Request>(&line);
        // Only capability_invoke may carry the larger 8 KiB input contract.
        if line.len() > MAX_MESSAGE
            && !matches!(
                parsed.as_ref().map(|r| &r.operation),
                Ok(Operation::CapabilityInvoke { .. })
            )
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "message too large",
            ));
        }
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
/// Client request line: bounded by MAX_MESSAGE unless it looks like a JSON object (`{"`), in which
/// case it may reach MAX_INVOKE_MESSAGE; the parsed operation is checked afterwards, and only
/// capability_invoke may actually exceed MAX_MESSAGE. Garbage without a newline closes at 4 KiB.
async fn request_frame<R: tokio::io::AsyncBufRead + Unpin>(
    read: &mut R,
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
        if total > MAX_INVOKE_MESSAGE || (total > MAX_MESSAGE && !object_like) {
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
async fn replay_worker(replay: WakeReplay, tx: mpsc::Sender<Result<Packet, ()>>) {
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
        let mut args = vec![
            replay.manifest.to_string_lossy().into_owned(),
            replay.fixture.to_string(),
        ];
        if let Some(phrase) = replay.active_phrase {
            args.extend(["--active-phrase".into(), phrase]);
        }
        let mut command = namespace_command(
            &replay.python,
            "scripts/wake_worker.py",
            &args,
            &[
                fixture_root.to_path_buf(),
                asset_root.into(),
                replay.manifest.clone(),
            ],
        )?;
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
) -> io::Result<()> {
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
    if let Some((path, digest)) = hub_catalog {
        core.configure_hub(
            crate::hub::load(&path, &digest)
                .unwrap_or_else(|_| crate::hub::Snapshot::quarantined())
                .with_approvals(&storage),
        );
    }
    let (plugin_events_tx, mut plugin_events) = mpsc::unbounded_channel();
    let mut plugins = crate::plugins::Host::new(plugin_python.clone(), plugin_events_tx);
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

    let (stt_tx, stt_requests) = mpsc::channel::<SttRequest>(16);
    let (stt_replies, mut stt_rx) = mpsc::channel::<Result<SttReply, ()>>(2);
    let mut stt_task = None;
    if let Some(r) = replay.as_ref() {
        let manifest: serde_json::Value = serde_json::from_slice(&fs::read(&r.manifest)?)?;
        if !manifest["stt"].is_null() {
            let config: SttConfig = serde_json::from_value(manifest["stt"].clone())?;
            let profile: serde_json::Value = serde_json::from_slice(&fs::read(&config.manifest)?)?;
            let engine = profile["engine"]
                .as_str()
                .ok_or_else(|| io::Error::other("STT engine missing"))?;
            core.configure_stt(engine.into());
            stt_task = Some(tokio::spawn(crate::stt::worker(
                config,
                stt_requests,
                stt_replies,
            )));
        }
    }
    let (wake_sender, mut wake_rx) = mpsc::channel(2);
    let mut wake_tx = Some(wake_sender);
    let mut command_wake_text = String::new();
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
            if let Some(phrase) = storage.config.wake_phrase.as_ref() {
                descriptor.active_phrase = phrase.clone();
            }
            if let Some(pack) = base_pack.as_mut() {
                pack.active_phrase = Some(descriptor.active_phrase.clone());
                command_wake_text = pack
                    .text(&descriptor.active_phrase)
                    .ok_or_else(|| io::Error::other("wake phrase missing"))?
                    .into();
            } else {
                command_wake_text = descriptor
                    .supported_phrases
                    .get(&descriptor.active_phrase)
                    .map(|label| label.replace('_', " "))
                    .unwrap_or_default();
            }
            r.active_phrase = Some(descriptor.active_phrase.clone());
            Some(WakeInput::new(descriptor).map_err(|_| io::Error::other("invalid wake catalog"))?)
        }
        None => None,
    };
    if let Some(pack) = base_pack {
        core.configure_pack(pack);
    }
    if commands_sandbox {
        core.configure_commands(command_wake_text);
    }
    let mut command_task: Option<(
        crate::commands::Job,
        tokio::task::JoinHandle<io::Result<crate::commands::Receipt>>,
    )> = None;
    if tts.is_some() {
        core.enable_tts();
    }
    let mut speech_task: Option<(
        u64,
        tokio::task::JoinHandle<io::Result<crate::tts::Summary>>,
    )> = None;
    let (speech_progress, mut speech_progress_rx) = mpsc::channel(2);
    let mut pending_replay = if stt_task.is_some() {
        replay.take()
    } else {
        None
    };
    let mut wake_task = if pending_replay.is_some() {
        None
    } else {
        replay.map(|r| {
            tokio::spawn(replay_worker(
                r,
                wake_tx.take().expect("single audio producer"),
            ))
        })
    };
    if wake_task.is_some() || pending_replay.is_some() {
        core.wake_health("starting");
    }
    let (tx, mut rx) = mpsc::channel::<Call>(16);
    let slots = Arc::new(Semaphore::new(8));
    let mut peers = JoinSet::new();
    let mut shutdown = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    loop {
        let deadline = core.deadline();
        let import_deadline = crate::hub::import_deadline(&storage);
        tokio::select! {
            _ = shutdown.recv() => break,
            _ = async { match import_deadline { Some(d) => tokio::time::sleep_until(d.into()).await, None => std::future::pending::<()>().await } } => {
                if crate::hub::expire_import(&mut storage, std::time::Instant::now()) { core.hub_import_expired(&storage); storage.audit(core.response(String::new(), "ok").sequence)?; }
            },
            _ = tokio::signal::ctrl_c() => break,
            _ = async { match deadline { Some(d) => tokio::time::sleep_until(d.into()).await, None => std::future::pending::<()>().await } } => { core.expire(std::time::Instant::now()); storage.audit(core.response(String::new(), "ok").sequence)?; },
            result = async { (&mut command_task.as_mut().expect("active task").1).await }, if command_task.is_some() => {
                let (job, _) = command_task.take().expect("active task");
                core.command_reply(job,result.ok().and_then(Result::ok),std::time::Instant::now());
                storage.audit(core.response(String::new(), "ok").sequence)?;
            },
            result = async { (&mut speech_task.as_mut().expect("active speech task").1).await }, if speech_task.is_some() => {
                let (id,_) = speech_task.take().expect("active speech task");
                core.speech_reply(id,result.ok().and_then(Result::ok),std::time::Instant::now());
                storage.audit(core.response(String::new(), "ok").sequence)?;
            },
            Some((id,samples))=speech_progress_rx.recv() => {core.speech_progress(id,samples);},
            Some(wire) = plugin_events.recv() => {
                if let Some(event) = plugins.accept(wire) {
                    core.plugin_event(event, std::time::Instant::now());
                    storage.audit(core.response(String::new(), "ok").sequence)?;
                }
            },
            Some(call) = rx.recv() => {
                let response = core.handle_with_storage(call.request, std::time::Instant::now(), Some(&mut storage)); storage.audit(response.sequence)?;
                let _ = call.reply.send(serde_json::to_vec(&response)?);
            },
            reply=stt_rx.recv(), if stt_task.is_some() => {
                match reply {
                    Some(Ok(r)) => {
                        let ready=matches!(r,SttReply::Ready{..});
                        core.stt_reply(r,std::time::Instant::now());
                        if ready && core.response(String::new(),"ok").stt_status=="ready" {
                            if let Some(replay)=pending_replay.take() { wake_task=Some(tokio::spawn(replay_worker(replay,wake_tx.take().expect("single audio producer")))); }
                        }
                    },
                    Some(Err(())) | None => {
                        core.stt_failed();
                        if pending_replay.take().is_some() { core.wake_health("unavailable");wake_tx.take(); }
                        if let Some(task)=stt_task.take() { task.abort(); let _=task.await; }
                    }
                }
            },
            packet = wake_rx.recv(), if wake_task.is_some() => {
                match packet {
                    Some(Ok(p)) => {
                        let frame=AudioFrame {timestamp_us:p.timestamp_us,sample_rate:16000,channels:1,samples:p.samples.clone()};
                        let speech=p.speech;
                        match wake_input.as_mut().expect("configured wake input").accept(p) {
                        Ok(detection) => {
                            core.wake_health("replaying");
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
        if let Some(job) = core.take_command_job() {
            let pending = job.clone();
            command_task = Some((job, tokio::spawn(crate::commands::execute(pending))));
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
        if let Some(job) = core.take_speech_job() {
            let config = tts.as_ref().expect("configured TTS").clone();
            speech_task = Some((
                job.session_id,
                tokio::spawn(crate::tts::speak(config, job, speech_progress.clone())),
            ));
        }
        pump_plugins(
            &mut core,
            &mut plugins,
            &storage.root,
            std::time::Instant::now(),
        );
        for request in core.take_stt_requests() {
            if stt_tx.try_send(request).is_err() {
                core.stt_failed();
                if let Some(task) = stt_task.take() {
                    task.abort();
                    let _ = task.await;
                }
                break;
            }
        }
    }
    if let Some((_, task)) = speech_task.take() {
        task.abort();
        let _ = task.await;
    }
    if let Some((_, task)) = command_task.take() {
        task.abort();
        let _ = task.await;
    }
    if let Some(task) = wake_task.take() {
        task.abort();
        let _ = task.await;
    }
    if let Some(task) = stt_task.take() {
        task.abort();
        let _ = task.await;
    }
    plugins.shutdown().await;
    core.shutdown();
    storage.audit(core.response(String::new(), "ok").sequence)?;
    peers.abort_all();
    while peers.join_next().await.is_some() {}
    fs::remove_file(path)?;
    Ok(())
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
