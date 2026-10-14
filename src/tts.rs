//! Supervised CPU speech, bounded PCM, virtual playback; no host audio endpoint.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    io,
    path::PathBuf,
    process::Stdio,
    time::{Duration, Instant},
};
use tokio::io::{AsyncWriteExt, BufReader};
#[derive(Clone, Debug)]
pub struct Config {
    pub python: PathBuf,
    pub manifest: PathBuf,
}
#[derive(Clone, Debug, Serialize)]
pub struct Job {
    pub session_id: u64,
    pub text: String,
}
#[derive(Clone, Debug, Serialize)]
pub struct Summary {
    pub session_id: u64,
    pub sample_rate: u32,
    pub samples: usize,
    pub chunks: usize,
    pub pcm_sha256: String,
    pub peak: f32,
    pub rms: f64,
    pub first_pcm_ms: u64,
    pub elapsed_ms: u64,
    pub sink: &'static str,
}
#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
enum Packet {
    Ready { session_id: u64 },
    Pcm { session_id: u64, samples: Vec<f32> },
    Done { session_id: u64 },
}
pub struct VirtualSpeaker {
    hash: Sha256,
    samples: usize,
    chunks: usize,
    peak: f32,
    power: f64,
}
impl Default for VirtualSpeaker {
    fn default() -> Self {
        Self {
            hash: Sha256::new(),
            samples: 0,
            chunks: 0,
            peak: 0.,
            power: 0.,
        }
    }
}
impl VirtualSpeaker {
    pub fn accept(&mut self, samples: &[f32]) -> io::Result<()> {
        if samples.is_empty()
            || samples.len() > 1920
            || self.samples + samples.len() > 240000
            || samples.iter().any(|s| !s.is_finite() || s.abs() > 1.)
        {
            return Err(io::Error::other("invalid/bounded PCM"));
        }
        for s in samples {
            self.hash.update(s.to_le_bytes());
            self.peak = self.peak.max(s.abs());
            self.power += f64::from(*s).powi(2);
        }
        self.samples += samples.len();
        self.chunks += 1;
        Ok(())
    }
    fn finish(self, id: u64, first: u64, elapsed: u64) -> io::Result<Summary> {
        if self.samples == 0 || self.peak <= 0. {
            return Err(io::Error::other("empty/silent speech"));
        }
        Ok(Summary {
            session_id: id,
            sample_rate: 24000,
            samples: self.samples,
            chunks: self.chunks,
            pcm_sha256: format!("{:x}", self.hash.finalize()),
            peak: self.peak,
            rms: (self.power / self.samples as f64).sqrt(),
            first_pcm_ms: first,
            elapsed_ms: elapsed,
            sink: "virtual",
        })
    }
}
pub fn feedback(outcome: &crate::commands::Outcome) -> String {
    use crate::commands::Command;
    if outcome.code == "command_success" {
        if let Some(r) = outcome
            .receipt
            .as_ref()
            .filter(|r| r.verified && r.scope == "sandbox")
        {
            return match r.job.command {
                Command::OpenApp { .. } => "Sandbox application completed.".into(),
                Command::Volume { .. } | Command::Mute => "Simulated audio updated.".into(),
                Command::Time | Command::Date => r.result.clone(),
                _ => "Sandbox ready.".into(),
            };
        }
    }
    if outcome.code == "unsupported" {
        "Command not understood.".into()
    } else {
        "Command failed.".into()
    }
}
pub async fn speak(
    config: Config,
    job: Job,
    progress: tokio::sync::mpsc::Sender<(u64, usize)>,
) -> io::Result<Summary> {
    if job.text.is_empty() || job.text.len() > 256 {
        return Err(io::Error::other("invalid speech job"));
    }
    let started = Instant::now();
    let profile: serde_json::Value = serde_json::from_slice(&std::fs::read(&config.manifest)?)?;
    let root = PathBuf::from(
        profile["root"]
            .as_str()
            .ok_or_else(|| io::Error::other("TTS assets"))?,
    );
    let mut command = crate::transport::namespace_command(
        &config.python,
        "scripts/tts_worker.py",
        &[config.manifest.display().to_string()],
        &[root, config.manifest.clone()],
    )?;
    command
        .env_clear()
        .env("PATH", "/usr/bin:/bin")
        .env("OMP_NUM_THREADS", "2")
        .env("OPENBLAS_NUM_THREADS", "1")
        .env("HF_HUB_OFFLINE", "1")
        .env("HF_HUB_DISABLE_TELEMETRY", "1")
        .stdin(Stdio::piped());
    let mut child = command.spawn()?;
    let result = tokio::time::timeout(Duration::from_secs(20), async {
        let mut input = child
            .stdin
            .take()
            .ok_or_else(|| io::Error::other("stdin"))?;
        input.write_all(&serde_json::to_vec(&job)?).await?;
        input.write_all(b"\n").await?;
        drop(input);
        let mut reader = BufReader::new(
            child
                .stdout
                .take()
                .ok_or_else(|| io::Error::other("stdout"))?,
        );
        let mut sink = VirtualSpeaker::default();
        let mut ready = false;
        let mut done = false;
        let mut first = 0;
        loop {
            let wait = if ready { 3 } else { 20 };
            let line = tokio::time::timeout(
                Duration::from_secs(wait),
                crate::transport::bounded_frame(&mut reader, 65536),
            )
            .await
            .map_err(io::Error::other)??;
            let Some(line) = line else {
                break;
            };
            match serde_json::from_slice::<Packet>(&line)? {
                Packet::Ready { session_id } if session_id == job.session_id && !ready && !done => {
                    ready = true;
                }
                Packet::Pcm {
                    session_id,
                    samples,
                } if session_id == job.session_id && ready && !done => {
                    if first == 0 {
                        first = started.elapsed().as_millis() as u64;
                    }
                    sink.accept(&samples)?;
                    let _ = progress.try_send((job.session_id, sink.samples));
                    // Pace the virtual endpoint; Tokio sleeps leave Core/IPC/cancel responsive.
                    tokio::time::sleep(Duration::from_secs_f64(samples.len() as f64 / 24000.))
                        .await;
                }
                Packet::Done { session_id } if session_id == job.session_id && ready && !done => {
                    done = true;
                }
                _ => return Err(io::Error::other("uncorrelated speech packet")),
            }
        }
        if !done || !child.wait().await?.success() {
            return Err(io::Error::other("speech worker failed"));
        }
        sink.finish(job.session_id, first, started.elapsed().as_millis() as u64)
    })
    .await
    .map_err(io::Error::other)
    .and_then(|result| result);
    if result.is_err() {
        let _ = child.kill().await;
        let _ = child.wait().await;
    }
    result
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn sink_validates_before_accepting_and_bounds_without_retaining_pcm() {
        let mut sink = VirtualSpeaker::default();
        for samples in [vec![], vec![f32::NAN], vec![1.1], vec![0.; 1921]] {
            assert!(sink.accept(&samples).is_err());
        }
        for _ in 0..125 {
            sink.accept(&vec![0.1; 1920]).unwrap();
        }
        assert!(sink.accept(&[0.1]).is_err());
        let r = sink.finish(1, 1, 10000).unwrap();
        assert_eq!(r.samples, 240000);
        assert_eq!(r.chunks, 125);
        assert!(r.rms > 0.09);
        assert!(VirtualSpeaker::default().finish(1, 0, 0).is_err());
        let mut silence = VirtualSpeaker::default();
        silence.accept(&[0.]).unwrap();
        assert!(silence.finish(1, 1, 1).is_err());
    }
    #[test]
    fn feedback_cannot_claim_success_without_receipt() {
        let outcome = crate::commands::Outcome {
            session_id: 1,
            code: "command_success",
            receipt: None,
        };
        assert_eq!(feedback(&outcome), "Command failed.");
    }
}
