use crate::{
    audio::AudioFrame,
    core::Core,
    protocol::{Request, MAX_MESSAGE},
    storage::Storage,
    stt::{SttConfig, SttReply, SttRequest},
    wake::{Packet, WakeDescriptor, WakeInput},
};
use std::{
    fs, io, os::unix::fs::PermissionsExt, path::PathBuf, process::Stdio, sync::Arc, time::Duration,
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
async fn peer(stream: UnixStream, tx: mpsc::Sender<Call>) -> io::Result<()> {
    let (read, mut write) = stream.into_split();
    let mut read = BufReader::new(read);
    loop {
        let line = tokio::time::timeout(Duration::from_secs(5), frame(&mut read)).await??;
        let Some(line) = line else {
            return Ok(());
        };
        let response = match serde_json::from_slice::<Request>(&line) {
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
async fn frame<R: tokio::io::AsyncBufRead + Unpin>(read: &mut R) -> io::Result<Option<Vec<u8>>> {
    bounded_frame(read, MAX_MESSAGE).await
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
pub(crate) fn namespace_command(
    python: &std::path::Path,
    script: &str,
    args: &[String],
    mounts: &[PathBuf],
) -> io::Result<Command> {
    let interpreter = fs::read_link(python).unwrap_or_else(|_| python.to_path_buf());
    let runtime = interpreter
        .parent()
        .and_then(|p| p.parent())
        .ok_or_else(|| io::Error::other("python runtime missing"))?;
    let canonical = fs::canonicalize(runtime)?;
    let mut cmd = Command::new("/usr/bin/bwrap");
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
    .arg(env!("CARGO_MANIFEST_DIR"))
    .arg(env!("CARGO_MANIFEST_DIR"));
    for path in mounts {
        if !path.is_absolute() {
            return Err(io::Error::other("absolute mount required"));
        }
        cmd.arg("--ro-bind").arg(path).arg(path);
    }
    cmd.args(["--setenv", "HOME", "/tmp", "--chdir", "/tmp", "--"])
        .arg(python)
        .arg("-I")
        .arg(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(script))
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
pub async fn serve(
    storage: Storage,
    virtual_input: bool,
    mut replay: Option<WakeReplay>,
) -> io::Result<()> {
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
    core.set_boot_seed(u64::from_ne_bytes(seed) & (u64::MAX / 2));
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
            r.active_phrase = Some(descriptor.active_phrase.clone());
            Some(WakeInput::new(descriptor).map_err(|_| io::Error::other("invalid wake catalog"))?)
        }
        None => None,
    };
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
        tokio::select! {
            _ = shutdown.recv() => break,
            _ = tokio::signal::ctrl_c() => break,
            _ = async { match deadline { Some(d) => tokio::time::sleep_until(d.into()).await, None => std::future::pending::<()>().await } } => { core.expire(std::time::Instant::now()); storage.audit(core.response(String::new(), "ok").sequence)?; },
            Some(call) = rx.recv() => {
                let response = core.handle(call.request, std::time::Instant::now()); storage.audit(response.sequence)?;
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
    if let Some(task) = wake_task.take() {
        task.abort();
        let _ = task.await;
    }
    if let Some(task) = stt_task.take() {
        task.abort();
        let _ = task.await;
    }
    core.shutdown();
    storage.audit(core.response(String::new(), "ok").sequence)?;
    peers.abort_all();
    while peers.join_next().await.is_some() {}
    fs::remove_file(path)?;
    Ok(())
}
