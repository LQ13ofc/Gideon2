use crate::{
    core::Core,
    protocol::{Request, MAX_MESSAGE},
    storage::Storage,
};
use std::{fs, io, os::unix::fs::PermissionsExt, sync::Arc, time::Duration};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    net::{UnixListener, UnixStream},
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
        if bytes.len() + size > MAX_MESSAGE {
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
pub async fn serve(storage: Storage, virtual_input: bool) -> io::Result<()> {
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
            accepted = listener.accept() => {
                let (stream, _) = accepted?;
                if let Ok(permit) = slots.clone().try_acquire_owned() {
                    let tx = tx.clone(); peers.spawn(async move { let _permit = permit; let _ = peer(stream, tx).await; });
                }
            },
            Some(_) = peers.join_next(), if !peers.is_empty() => {},
        }
    }
    core.shutdown();
    storage.audit(core.response(String::new(), "ok").sequence)?;
    peers.abort_all();
    while peers.join_next().await.is_some() {}
    fs::remove_file(path)?;
    Ok(())
}
