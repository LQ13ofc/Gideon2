//! Private worker protocol. Transcript data conveys no capability or grant.
//!
//! `Pipe` owns the STT worker: one worker at a time, a bounded queue in front of it, and a supervisor that
//! restarts a failed worker with backoff. Audio is never dropped: a transient backlog waits in the queue
//! (live frames are merged first), and only a backlog longer than `MAX_BACKLOG_SAMPLES` counts as a real
//! failure of the worker.
use crate::live;
use serde::{Deserialize, Serialize};
use std::{
    collections::VecDeque,
    io,
    path::PathBuf,
    process::Stdio,
    time::{Duration, Instant},
};
use tokio::{
    io::{AsyncWriteExt, BufReader},
    process::Child,
    sync::mpsc,
    task::JoinHandle,
};

/// Live frames are merged into messages of up to 160 ms (the worker accepts up to this many samples).
pub const LIVE_CHUNK_SAMPLES: usize = 2560;
/// Messages the owner may have queued for the worker writer before it waits (about 2.5 s of merged live audio).
pub const CHANNEL_CAPACITY: usize = 16;
/// Audio that may wait for the worker before the worker is treated as stuck (10 s).
pub const MAX_BACKLOG_SAMPLES: usize = 16_000 * 10;
/// A trailing live frame is held at most this long while it waits for the next frame to merge with.
const HOLD: Duration = Duration::from_millis(100);
/// Restarts of the worker allowed in one window; the next failure is permanent (`failed`).
pub const RESTART_LIMIT: usize = 3;
pub const RESTART_WINDOW: Duration = Duration::from_secs(60);
const RESTART_BACKOFF: Duration = Duration::from_millis(500);
/// Content-free reasons of an STT failure (`stt_last_error` in the snapshot). Closed vocabulary.
pub const WORKER_UNAVAILABLE: &str = "worker_unavailable";
pub const WORKER_TIMEOUT: &str = "worker_timeout";
pub const WORKER_BACKLOG: &str = "worker_backlog";
/// Diagnostic file with the last worker stderr tail (0600, Core data dir). Never part of the snapshot.
pub const LAST_ERROR_FILE: &str = "stt-last-error.txt";

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
/// A worker that ended: its content-free reason and the last stderr bytes (for the 0600 diagnostics file only).
#[derive(Debug)]
pub struct Failure {
    pub reason: &'static str,
    pub tail: Vec<u8>,
}
#[derive(Clone, Debug, Serialize)]
pub struct Transcript {
    pub source: &'static str,
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

/// Runs the worker until it fails; always ends by sending one `Failure` on `replies` (unless the owner is gone).
pub async fn worker(
    config: SttConfig,
    requests: mpsc::Receiver<SttRequest>,
    replies: mpsc::Sender<Result<SttReply, Failure>>,
) {
    let failure = serve(&config, requests, &replies).await;
    let _ = replies.send(Err(failure)).await;
}

async fn serve(
    config: &SttConfig,
    requests: mpsc::Receiver<SttRequest>,
    replies: &mpsc::Sender<Result<SttReply, Failure>>,
) -> Failure {
    let spawned = crate::transport::namespace_command(
        &config.python,
        "scripts/stt_worker.py",
        &[config.manifest.to_string_lossy().into_owned()],
        &[config.manifest.clone()],
    )
    .and_then(|mut command| {
        // stderr is kept (tail only) so a failed worker can say why; it never reaches the snapshot.
        command.stdin(Stdio::piped()).stderr(Stdio::piped());
        command.spawn()
    });
    let Ok(mut child) = spawned else {
        return Failure {
            reason: WORKER_UNAVAILABLE,
            tail: Vec::new(),
        };
    };
    let stderr_task = child
        .stderr
        .take()
        .map(|stderr| tokio::spawn(live::read_tail(stderr)));
    let outcome = exchange(&mut child, requests, replies).await;
    let _ = child.kill().await;
    let _ = child.wait().await;
    let tail = match stderr_task {
        Some(task) => tokio::time::timeout(Duration::from_secs(1), task)
            .await
            .ok()
            .and_then(Result::ok)
            .unwrap_or_default(),
        None => Vec::new(),
    };
    let reason = match outcome {
        Err(error) if error.kind() == io::ErrorKind::TimedOut => WORKER_TIMEOUT,
        _ => live::reason_for("stt", &tail),
    };
    Failure { reason, tail }
}

/// Startup handshake, then request writer and reply reader until one of them fails.
async fn exchange(
    child: &mut Child,
    requests: mpsc::Receiver<SttRequest>,
    replies: &mpsc::Sender<Result<SttReply, Failure>>,
) -> io::Result<()> {
    let mut stdin = child
        .stdin
        .take()
        .ok_or_else(|| io::Error::other("STT input"))?;
    let mut stdout = BufReader::new(
        child
            .stdout
            .take()
            .ok_or_else(|| io::Error::other("STT output"))?,
    );
    let mut requests = requests;
    let mut writer = tokio::spawn(async move {
        while let Some(request) = requests.recv().await {
            let mut bytes = serde_json::to_vec(&request)?;
            bytes.push(b'\n');
            if bytes.len() > 65536 {
                return Err(io::Error::other("STT message too large"));
            }
            tokio::time::timeout(Duration::from_secs(2), stdin.write_all(&bytes)).await??;
        }
        Ok::<_, io::Error>(())
    });
    let _writer_guard = AbortWriter(writer.abort_handle());
    let reader = async {
        let initial = tokio::time::timeout(
            Duration::from_secs(20),
            crate::transport::bounded_frame(&mut stdout, 65536),
        )
        .await??
        .ok_or_else(|| io::Error::other("STT startup EOF"))?;
        let ready: SttReply = serde_json::from_slice(&initial)?;
        if !matches!(ready, SttReply::Ready { .. }) {
            return Err(io::Error::other("STT not ready"));
        }
        replies
            .send(Ok(ready))
            .await
            .map_err(|_| io::Error::other("owner stopped"))?;
        while let Some(line) = crate::transport::bounded_frame(&mut stdout, 65536).await? {
            let reply = serde_json::from_slice(&line)?;
            replies
                .send(Ok(reply))
                .await
                .map_err(|_| io::Error::other("owner stopped"))?;
        }
        Err(io::Error::other("STT exited"))
    };
    tokio::select! {
        r = reader => { writer.abort(); let _ = writer.await; r }
        r = &mut writer => match r {
            Ok(Err(e)) => Err(e),
            _ => Err(io::Error::other("STT writer stopped")),
        },
    }
}

struct Run {
    task: JoinHandle<()>,
    requests: mpsc::Sender<SttRequest>,
    replies: mpsc::Receiver<Result<SttReply, Failure>>,
}
struct Queued {
    request: SttRequest,
    /// When this queued message started (a merged live message keeps the time of its first frame).
    since: Instant,
}

/// Owner side of the STT worker: queue, supervision and restart budget. Stays inert without a configuration.
pub struct Pipe {
    config: Option<SttConfig>,
    /// Live audio only: consecutive frames of one session are merged into `LIVE_CHUNK_SAMPLES` messages.
    /// The replay path sends its frames as they come (its behaviour is unchanged).
    coalesce: bool,
    run: Option<Run>,
    backlog: VecDeque<Queued>,
    backlog_samples: usize,
    restarts: VecDeque<Instant>,
    restart_at: Option<Instant>,
}

fn frame_samples(request: &SttRequest) -> usize {
    match request {
        SttRequest::Frame { samples, .. } => samples.len(),
        _ => 0,
    }
}

/// Appends `next` to `back` when both are frames of one session and the result fits one message.
fn try_merge(back: &mut SttRequest, next: &SttRequest) -> bool {
    match (back, next) {
        (
            SttRequest::Frame {
                session_id: a,
                end_us: end,
                samples,
            },
            SttRequest::Frame {
                session_id: b,
                end_us,
                samples: more,
            },
        ) if a == b && samples.len() + more.len() <= LIVE_CHUNK_SAMPLES => {
            samples.extend_from_slice(more);
            *end = *end_us;
            true
        }
        _ => false,
    }
}

impl Pipe {
    pub fn new(config: Option<SttConfig>, coalesce: bool) -> Self {
        Self {
            config,
            coalesce,
            run: None,
            backlog: VecDeque::new(),
            backlog_samples: 0,
            restarts: VecDeque::new(),
            restart_at: None,
        }
    }
    /// The Core configured an STT engine for this run (the worker is started at boot, or restarted after a failure).
    pub fn configured(&self) -> bool {
        self.config.is_some()
    }
    /// True while a worker task exists (it may be failing; its failure arrives on `next_reply`).
    pub fn running(&self) -> bool {
        self.run.is_some()
    }
    /// Start (or restart) the worker with fresh channels. No-op without a configuration.
    pub fn start(&mut self) {
        let Some(config) = self.config.clone() else {
            return;
        };
        if self.run.is_some() {
            return;
        }
        let (requests, receiver) = mpsc::channel(CHANNEL_CAPACITY);
        let (replies_tx, replies) = mpsc::channel(2);
        let task = tokio::spawn(worker(config, receiver, replies_tx));
        self.run = Some(Run {
            task,
            requests,
            replies,
        });
        self.restart_at = None;
    }
    /// The next worker message: a reply, or its failure. `None` when the worker ended without a failure.
    pub async fn next_reply(&mut self) -> Option<Result<SttReply, Failure>> {
        match self.run.as_mut() {
            Some(run) => run.replies.recv().await,
            None => std::future::pending().await,
        }
    }
    /// Queues a request without losing audio. Frames merge into the newest queued frame of the same session.
    /// `Err` only when the backlog exceeds `MAX_BACKLOG_SAMPLES`: the worker is stuck, not merely busy.
    pub fn enqueue(&mut self, request: SttRequest, now: Instant) -> Result<(), &'static str> {
        if self.run.is_none() {
            // No worker reads this: the request belongs to a session that the failure already ended.
            return Ok(());
        }
        let added = frame_samples(&request);
        if self.backlog_samples + added > MAX_BACKLOG_SAMPLES {
            return Err(WORKER_BACKLOG);
        }
        let merged = self.coalesce
            && self
                .backlog
                .back_mut()
                .is_some_and(|back| try_merge(&mut back.request, &request));
        if !merged {
            self.backlog.push_back(Queued {
                request,
                since: now,
            });
        }
        self.backlog_samples += added;
        Ok(())
    }
    /// Sends queued requests in order without waiting. A full channel keeps the rest for the next call.
    /// A closed channel means the worker ended: its failure is the next reply.
    pub fn flush(&mut self, now: Instant) {
        let Some(run) = self.run.as_mut() else {
            return;
        };
        while let Some(front) = self.backlog.front() {
            // A lone live frame waits briefly so that the next frames merge into one message.
            let held = self.coalesce
                && self.backlog.len() == 1
                && frame_samples(&front.request) > 0
                && frame_samples(&front.request) < LIVE_CHUNK_SAMPLES
                && now.duration_since(front.since) < HOLD;
            if held {
                break;
            }
            let Some(item) = self.backlog.pop_front() else {
                break;
            };
            let samples = frame_samples(&item.request);
            match run.requests.try_send(item.request) {
                Ok(()) => self.backlog_samples = self.backlog_samples.saturating_sub(samples),
                Err(mpsc::error::TrySendError::Full(request)) => {
                    self.backlog.push_front(Queued {
                        request,
                        since: item.since,
                    });
                    break;
                }
                Err(mpsc::error::TrySendError::Closed(_)) => break,
            }
        }
    }
    /// True while requests wait for the worker (the owner polls them again soon).
    pub fn pending(&self) -> bool {
        !self.backlog.is_empty()
    }
    /// When a scheduled restart is due.
    pub fn restart_at(&self) -> Option<Instant> {
        self.restart_at
    }
    /// Books a restart after a failure. False when the budget (`RESTART_LIMIT` in `RESTART_WINDOW`) is spent.
    pub fn schedule_restart(&mut self, now: Instant) -> bool {
        while self
            .restarts
            .front()
            .is_some_and(|t| now.duration_since(*t) >= RESTART_WINDOW)
        {
            self.restarts.pop_front();
        }
        if self.restarts.len() >= RESTART_LIMIT {
            self.restart_at = None;
            return false;
        }
        let delay = RESTART_BACKOFF * 2u32.pow(self.restarts.len() as u32);
        self.restarts.push_back(now);
        self.restart_at = Some(now + delay);
        true
    }
    /// Drops the worker and its queue after a failure (the task is aborted; its child dies with it).
    pub fn abort(&mut self) {
        if let Some(run) = self.run.take() {
            run.task.abort();
        }
        self.backlog.clear();
        self.backlog_samples = 0;
    }
    /// CFG-07: stops the worker and starts it again with another engine configuration. Only called between
    /// voice sessions (the queue is empty then); the restart budget is not spent by a deliberate change.
    pub async fn reconfigure(&mut self, config: Option<SttConfig>) {
        self.stop().await;
        self.config = config;
        self.start();
    }
    /// Shutdown: aborts and reaps the worker.
    pub async fn stop(&mut self) {
        if let Some(run) = self.run.take() {
            run.task.abort();
            let _ = run.task.await;
        }
        self.backlog.clear();
        self.backlog_samples = 0;
        self.restart_at = None;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A pipe whose worker is a parked task: only the queue and the restart budget are under test.
    fn parked(coalesce: bool, capacity: usize) -> (Pipe, mpsc::Receiver<SttRequest>) {
        let (requests, receiver) = mpsc::channel(capacity);
        let (_replies_tx, replies) = mpsc::channel(2);
        let task = tokio::spawn(std::future::pending::<()>());
        let mut pipe = Pipe::new(None, coalesce);
        pipe.run = Some(Run {
            task,
            requests,
            replies,
        });
        (pipe, receiver)
    }
    fn frame(session: u64, index: u64, samples: usize) -> SttRequest {
        SttRequest::Frame {
            session_id: session,
            end_us: (index + 1) * 20_000,
            samples: vec![0.0; samples],
        }
    }
    fn end_of(request: &SttRequest) -> u64 {
        match request {
            SttRequest::Frame { end_us, .. } => *end_us,
            _ => 0,
        }
    }

    #[tokio::test]
    async fn live_frames_merge_into_one_160ms_message_in_order() {
        let (mut pipe, mut rx) = parked(true, 16);
        let now = Instant::now();
        for i in 0..8 {
            pipe.enqueue(frame(1, i, 320), now).unwrap();
        }
        pipe.flush(now);
        let message = rx.try_recv().expect("one merged message");
        assert!(rx.try_recv().is_err());
        match &message {
            SttRequest::Frame {
                samples, end_us, ..
            } => {
                assert_eq!(samples.len(), LIVE_CHUNK_SAMPLES);
                assert_eq!(*end_us, 8 * 20_000);
            }
            _ => panic!("frame expected"),
        }
        assert!(!pipe.pending());
    }

    #[tokio::test]
    async fn a_lone_live_frame_is_held_briefly_then_sent() {
        let (mut pipe, mut rx) = parked(true, 16);
        let start = Instant::now();
        pipe.enqueue(frame(1, 0, 320), start).unwrap();
        pipe.flush(start);
        assert!(
            rx.try_recv().is_err(),
            "a lone frame waits for its merge partner"
        );
        assert!(pipe.pending());
        pipe.flush(start + HOLD);
        assert_eq!(end_of(&rx.try_recv().unwrap()), 20_000);
        assert!(!pipe.pending());
    }

    #[tokio::test]
    async fn other_session_or_control_breaks_a_merge() {
        let (mut pipe, mut rx) = parked(true, 16);
        let now = Instant::now();
        pipe.enqueue(frame(1, 0, 320), now).unwrap();
        pipe.enqueue(frame(2, 1, 320), now).unwrap();
        pipe.enqueue(SttRequest::Finish { session_id: 2 }, now)
            .unwrap();
        pipe.flush(now);
        assert_eq!(end_of(&rx.try_recv().unwrap()), 20_000);
        assert_eq!(end_of(&rx.try_recv().unwrap()), 40_000);
        assert!(matches!(rx.try_recv().unwrap(), SttRequest::Finish { .. }));
    }

    #[tokio::test]
    async fn replay_frames_are_not_merged() {
        let (mut pipe, mut rx) = parked(false, 16);
        let now = Instant::now();
        for i in 0..8 {
            pipe.enqueue(frame(1, i, 320), now).unwrap();
        }
        pipe.flush(now);
        for i in 0..8 {
            match rx.try_recv().unwrap() {
                SttRequest::Frame { samples, .. } => assert_eq!(samples.len(), 320, "frame {i}"),
                _ => panic!("frame expected"),
            }
        }
    }

    #[tokio::test]
    async fn a_full_channel_keeps_audio_queued_and_loses_nothing() {
        let (mut pipe, mut rx) = parked(false, 2);
        let now = Instant::now();
        for i in 0..10 {
            pipe.enqueue(frame(1, i, 320), now).unwrap();
        }
        pipe.flush(now);
        assert!(pipe.pending());
        let mut seen = Vec::new();
        while seen.len() < 10 {
            while let Ok(request) = rx.try_recv() {
                seen.push(end_of(&request));
            }
            pipe.flush(now);
        }
        let expected: Vec<u64> = (1..=10).map(|i| i * 20_000).collect();
        assert_eq!(seen, expected);
        assert!(!pipe.pending());
    }

    #[tokio::test]
    async fn only_a_backlog_beyond_the_limit_is_a_failure() {
        let (mut pipe, _rx) = parked(false, 2);
        let now = Instant::now();
        let chunk = 2560;
        let fit = MAX_BACKLOG_SAMPLES / chunk;
        for i in 0..fit as u64 {
            pipe.enqueue(frame(1, i, chunk), now).unwrap();
        }
        assert_eq!(
            pipe.enqueue(frame(1, fit as u64, chunk), now),
            Err(WORKER_BACKLOG)
        );
    }

    #[tokio::test]
    async fn restarts_back_off_and_are_bounded_per_window() {
        let (mut pipe, _rx) = parked(false, 2);
        let t0 = Instant::now();
        assert!(pipe.schedule_restart(t0));
        assert_eq!(pipe.restart_at(), Some(t0 + Duration::from_millis(500)));
        assert!(pipe.schedule_restart(t0));
        assert_eq!(pipe.restart_at(), Some(t0 + Duration::from_secs(1)));
        assert!(pipe.schedule_restart(t0));
        assert_eq!(pipe.restart_at(), Some(t0 + Duration::from_secs(2)));
        assert!(
            !pipe.schedule_restart(t0),
            "the fourth failure in the window is permanent"
        );
        assert_eq!(pipe.restart_at(), None);
        assert!(pipe.schedule_restart(t0 + RESTART_WINDOW));
    }
}
