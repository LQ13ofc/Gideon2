//! Private worker protocol. Transcript data conveys no capability or grant.
use serde::{Deserialize, Serialize};
use std::{io, path::PathBuf, process::Stdio, time::Duration};
use tokio::{
    io::{AsyncWriteExt, BufReader},
    sync::mpsc,
};

#[derive(Clone, Deserialize)]
pub struct SttConfig {
    pub python: PathBuf,
    pub manifest: PathBuf,
}
#[derive(Serialize)]
#[serde(tag = "op", rename_all = "snake_case")]
pub enum SttRequest {
    Start {
        session_id: u64,
    },
    Frame {
        session_id: u64,
        end_us: u64,
        samples: Vec<f32>,
    },
    Finish {
        session_id: u64,
    },
    Cancel {
        session_id: u64,
    },
}
#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum SttReply {
    Ready {
        engine: String,
    },
    Partial {
        engine: String,
        session_id: u64,
        revision: u32,
        audio_end_us: u64,
        raw: String,
    },
    Final {
        engine: String,
        session_id: u64,
        revision: u32,
        audio_end_us: u64,
        raw: String,
    },
}
#[derive(Clone, Debug, Serialize)]
pub struct Transcript {
    pub session_id: u64,
    pub revision: u32,
    pub audio_end_us: u64,
    pub raw: String,
    pub normalized: String,
    pub is_final: bool,
    pub confidence: Option<f32>,
}
struct AbortWriter(tokio::task::AbortHandle);
impl Drop for AbortWriter {
    fn drop(&mut self) {
        self.0.abort();
    }
}
pub async fn worker(
    config: SttConfig,
    mut requests: mpsc::Receiver<SttRequest>,
    replies: mpsc::Sender<Result<SttReply, ()>>,
) {
    let result=async {
        let mut child=crate::transport::namespace_command(&config.python,"scripts/stt_worker.py",&[config.manifest.to_string_lossy().into_owned()],&[config.manifest.clone()])?.stdin(Stdio::piped()).spawn()?;
        let mut stdin=child.stdin.take().ok_or_else(||io::Error::other("STT input"))?;
        let mut stdout=BufReader::new(child.stdout.take().ok_or_else(||io::Error::other("STT output"))?);
        let mut writer=tokio::spawn(async move {
            while let Some(request)=requests.recv().await {
                let mut bytes=serde_json::to_vec(&request)?;bytes.push(b'\n');
                if bytes.len()>65536 { return Err(io::Error::other("STT message too large")); }
                tokio::time::timeout(Duration::from_secs(2),stdin.write_all(&bytes)).await??;
            }
            Ok::<_,io::Error>(())
        });
        let _writer_guard=AbortWriter(writer.abort_handle());
        let reader=async {
            let initial=tokio::time::timeout(Duration::from_secs(20),crate::transport::bounded_frame(&mut stdout,65536)).await??.ok_or_else(||io::Error::other("STT startup EOF"))?;
            let ready:SttReply=serde_json::from_slice(&initial)?;
            if !matches!(ready,SttReply::Ready{..}) { return Err(io::Error::other("STT not ready")); }
            replies.send(Ok(ready)).await.map_err(|_|io::Error::other("owner stopped"))?;
            while let Some(line)=crate::transport::bounded_frame(&mut stdout,65536).await? {
                let reply=serde_json::from_slice(&line)?;
                replies.send(Ok(reply)).await.map_err(|_|io::Error::other("owner stopped"))?;
            }
            Err(io::Error::other("STT exited"))
        };
        let outcome:io::Result<()>=tokio::select! {
            r=reader => { writer.abort();let _=writer.await;r },
            r=&mut writer => match r { Ok(Err(e))=>Err(e), _=>Err(io::Error::other("STT writer stopped")) },
        };
        let _=child.kill().await;let _=child.wait().await;
        outcome
    }.await;
    if result.is_err() {
        let _ = replies.send(Err(())).await;
    }
}
