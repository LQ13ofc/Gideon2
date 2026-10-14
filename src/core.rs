use crate::{
    audio::AudioFrame,
    capture::{Capture, CaptureSummary},
    commands::{self, Command, Job, Outcome, Receipt},
    protocol::*,
    stt::{SttReply, SttRequest, Transcript},
};
use std::{
    collections::VecDeque,
    time::{Duration, Instant},
};

struct Session {
    id: u64,
    request_id: String,
    deadline: Instant,
    capture: Option<Capture>,
    audio_deadline: Option<Instant>,
    stage: State,
    revision: u32,
    overall_deadline: Instant,
}

/// Single owner for sessions, events and authority; no detached action tasks.
pub struct Core {
    session: Option<Session>,
    next_session: u64,
    sequence: u64,
    events: VecDeque<Event>,
    recent_requests: VecDeque<String>,
    timeout: Duration,
    virtual_input: bool,
    wake_status: &'static str,
    capture_enabled: bool,
    completed_audio: Option<Capture>,
    capture_summary: Option<CaptureSummary>,
    stt_engine: Option<String>,
    stt_status: &'static str,
    stt_requests: VecDeque<SttRequest>,
    transcript: Option<Transcript>,
    command_wake: Option<String>,
    command_job: Option<Job>,
    expected_command: Option<Job>,
    command_outcome: Option<Outcome>,
    tts_enabled: bool,
    speech_job: Option<crate::tts::Job>,
    speech_status: &'static str,
    speech_summary: Option<crate::tts::Summary>,
    speech_samples: usize,
}
impl Core {
    pub fn new(timeout: Duration, virtual_input: bool) -> Self {
        Self {
            session: None,
            next_session: 1,
            sequence: 0,
            events: VecDeque::new(),
            recent_requests: VecDeque::new(),
            timeout,
            virtual_input,
            wake_status: "unavailable",
            capture_enabled: false,
            completed_audio: None,
            capture_summary: None,
            stt_engine: None,
            stt_status: "unavailable",
            stt_requests: VecDeque::new(),
            transcript: None,
            command_wake: None,
            command_job: None,
            expected_command: None,
            command_outcome: None,
            tts_enabled: false,
            speech_job: None,
            speech_status: "unavailable",
            speech_summary: None,
            speech_samples: 0,
        }
    }
    pub fn set_boot_seed(&mut self, seed: u64) {
        self.next_session = seed;
    }
    fn start_session(&mut self, request_id: String, now: Instant) {
        self.completed_audio = None;
        self.capture_summary = None;
        self.transcript = None;
        self.command_outcome = None;
        self.speech_summary = None;
        self.speech_samples = 0;
        if self.tts_enabled {
            self.speech_status = "idle";
        }
        let id = self.next_session;
        self.next_session += 1;
        self.session = Some(Session {
            id,
            request_id: request_id.clone(),
            deadline: now + self.timeout,
            capture: None,
            audio_deadline: None,
            stage: State::Capturing,
            revision: 0,
            overall_deadline: now + self.timeout,
        });
        self.emit(request_id, Some(id), "session_started");
    }
    pub fn audio_wake(&mut self, now: Instant) {
        self.expire(now);
        if self.session.is_none() {
            self.start_session(format!("wake_{}", self.sequence + 1), now);
        }
    }
    pub fn enable_capture(&mut self) {
        self.capture_enabled = true;
    }
    pub fn capture_packet(
        &mut self,
        frame: AudioFrame,
        speech: Option<bool>,
        pre_roll: Vec<f32>,
        detected: bool,
        now: Instant,
    ) {
        if frame.validate().is_err() {
            self.finish("audio_error");
            return;
        }
        if !self.capture_enabled {
            if detected {
                self.audio_wake(now);
            }
            return;
        }
        self.expire(now);
        if self.stt_requests.len() >= 32 {
            self.stt_requests.clear();
            self.stt_failed();
            return;
        }
        if self.stt_engine.is_some() && self.stt_status != "ready" {
            if detected {
                self.audio_wake(now);
                self.finish("stt_unavailable");
            }
            return;
        }
        let Some(speech) = speech else {
            self.wake_health("failed");
            return;
        };
        if self.session.is_none() {
            if detected {
                self.audio_wake(now);
                match Capture::new(pre_roll, frame.end_us()) {
                    Ok(c) => {
                        if self.stt_status == "ready" {
                            let sid = self.session.as_ref().unwrap().id;
                            self.stt_requests
                                .push_back(SttRequest::Start { session_id: sid });
                            let begin = frame.end_us() - c.samples.len() as u64 * 1_000_000 / 16000;
                            for (i, chunk) in c.samples.chunks(1280).enumerate() {
                                self.stt_requests.push_back(SttRequest::Frame {
                                    session_id: sid,
                                    end_us: begin
                                        + (i * 1280 + chunk.len()) as u64 * 1_000_000 / 16000,
                                    samples: chunk.to_vec(),
                                });
                            }
                        }
                        if let Some(s) = self.session.as_mut() {
                            s.capture = Some(c);
                            s.audio_deadline = Some(now + Duration::from_secs(1));
                        }
                    }
                    Err(_) => self.finish("audio_error"),
                }
            }
            return;
        }
        if let Some(s) = self.session.as_mut() {
            if let Some(c) = s.capture.as_mut() {
                s.audio_deadline = Some(now + Duration::from_secs(1));
                if self.stt_status == "ready" {
                    self.stt_requests.push_back(SttRequest::Frame {
                        session_id: s.id,
                        end_us: frame.end_us(),
                        samples: frame.samples.clone(),
                    });
                }
                match c.push(frame, speech) {
                    Ok(Some(reason)) => self.finish(reason),
                    Err(_) => self.finish("audio_error"),
                    Ok(None) => {}
                }
            }
        }
    }
    pub fn configure_stt(&mut self, engine: String) {
        self.stt_engine = Some(engine);
        self.stt_status = "starting";
    }
    pub fn take_stt_requests(&mut self) -> VecDeque<SttRequest> {
        std::mem::take(&mut self.stt_requests)
    }
    pub fn stt_failed(&mut self) {
        self.stt_status = "failed";
        self.transcript = None;
        self.finish("stt_failed");
    }
    pub fn stt_reply(&mut self, reply: SttReply, now: Instant) {
        self.expire(now);
        let (engine, id, revision, end, raw, final_result) = match reply {
            SttReply::Ready { engine } => {
                if self.stt_status != "starting" {
                    return;
                }
                if self.stt_engine.as_ref() == Some(&engine) {
                    self.stt_status = "ready";
                } else {
                    self.stt_failed();
                }
                return;
            }
            SttReply::Partial {
                engine,
                session_id,
                revision,
                audio_end_us,
                raw,
            } => (engine, session_id, revision, audio_end_us, raw, false),
            SttReply::Final {
                engine,
                session_id,
                revision,
                audio_end_us,
                raw,
            } => (engine, session_id, revision, audio_end_us, raw, true),
        };
        let Some(s) = self.session.as_mut() else {
            return;
        };
        if s.id != id
            || self.stt_status != "ready"
            || self.stt_engine.as_ref() != Some(&engine)
            || matches!(s.stage, State::Executing | State::Speaking)
            || revision <= s.revision
            || revision > 256
            || raw.len() > 4096
            || (final_result && s.stage != State::Transcribing)
        {
            return;
        }
        s.revision = revision;
        self.transcript = Some(Transcript {
            source: "voice",
            session_id: id,
            revision,
            audio_end_us: end,
            normalized: raw.split_whitespace().collect::<Vec<_>>().join(" "),
            raw,
            is_final: final_result,
            confidence: None,
        });
        let request_id = s.request_id.clone();
        if final_result {
            if self.command_wake.is_some() {
                self.emit(request_id, Some(id), "transcript_final");
                self.dispatch_command(now);
            } else {
                self.finish("transcript_final");
            }
        } else {
            self.emit(request_id, Some(id), "transcript_partial");
        }
    }
    pub fn configure_commands(&mut self, wake_text: String) {
        self.command_wake = Some(wake_text);
    }
    pub fn take_command_job(&mut self) -> Option<Job> {
        self.command_job.take()
    }
    pub fn command_is_active(&self, id: u64) -> bool {
        self.session
            .as_ref()
            .is_some_and(|s| s.id == id && s.stage == State::Executing)
    }
    fn dispatch_command(&mut self, now: Instant) {
        let transcript = self.transcript.as_ref().expect("final transcript");
        let id = transcript.session_id;
        let parsed = commands::parse(&transcript.raw, self.command_wake.as_deref().unwrap_or(""));
        let command = match parsed {
            Some(Command::Cancel) => {
                self.finish("cancelled");
                return;
            }
            Some(command) => command,
            None => {
                self.command_outcome = Some(Outcome {
                    session_id: id,
                    code: "unsupported",
                    receipt: None,
                });
                self.command_terminal("command_rejected", now);
                return;
            }
        };
        if let Err(code) = commands::authorize(&command) {
            self.command_outcome = Some(Outcome {
                session_id: id,
                code,
                receipt: None,
            });
            self.command_terminal("command_denied", now);
            return;
        }
        let s = self.session.as_mut().expect("live final session");
        s.stage = State::Executing;
        s.deadline = s.deadline.min(now + Duration::from_secs(2));
        self.command_job = Some(Job {
            session_id: id,
            command,
        });
        self.expected_command = self.command_job.clone();
        let request_id = s.request_id.clone();
        self.emit(request_id, Some(id), "command_authorized");
    }
    pub fn command_reply(&mut self, job: Job, receipt: Option<Receipt>, now: Instant) {
        self.expire(now);
        if !self.command_is_active(job.session_id) || self.expected_command.as_ref() != Some(&job) {
            return;
        }
        let receipt = receipt.filter(|r| commands::verify(&job, r));
        let kind = if receipt.is_some() {
            "command_success"
        } else {
            "command_failed"
        };
        self.command_outcome = Some(Outcome {
            session_id: job.session_id,
            code: kind,
            receipt,
        });
        self.command_terminal(kind, now);
    }
    pub fn enable_tts(&mut self) {
        self.tts_enabled = true;
        self.speech_status = "idle";
    }
    pub fn take_speech_job(&mut self) -> Option<crate::tts::Job> {
        self.speech_job.take()
    }
    pub fn speech_is_active(&self, id: u64) -> bool {
        self.session
            .as_ref()
            .is_some_and(|s| s.id == id && s.stage == State::Speaking)
    }
    fn command_terminal(&mut self, kind: &'static str, now: Instant) {
        if !self.tts_enabled {
            self.finish(kind);
            return;
        }
        let outcome = self
            .command_outcome
            .as_ref()
            .expect("determined command result");
        let text = crate::tts::feedback(outcome);
        let s = self.session.as_mut().expect("live command session");
        s.stage = State::Speaking;
        s.deadline = s.overall_deadline.min(now + Duration::from_secs(20));
        self.speech_status = "speaking";
        self.speech_job = Some(crate::tts::Job {
            session_id: s.id,
            text,
        });
        let (id, request_id) = (s.id, s.request_id.clone());
        self.emit(request_id.clone(), Some(id), kind);
        self.emit(request_id, Some(id), "speech_started");
    }
    pub fn speech_progress(&mut self, id: u64, samples: usize) {
        if self.speech_is_active(id) && samples <= 240000 && samples > self.speech_samples {
            self.speech_samples = samples;
        }
    }
    pub fn speech_reply(&mut self, id: u64, summary: Option<crate::tts::Summary>, now: Instant) {
        self.expire(now);
        if !self.speech_is_active(id) {
            return;
        }
        self.speech_summary = summary.filter(|s| {
            s.session_id == id
                && s.sink == "virtual"
                && s.sample_rate == 24000
                && s.samples > 0
                && s.samples <= 240000
                && s.chunks > 0
                && s.peak.is_finite()
                && s.peak > 0.
                && s.peak <= 1.
                && s.rms.is_finite()
                && s.rms > 0.
                && s.pcm_sha256.len() == 64
                && s.pcm_sha256.bytes().all(|b| b.is_ascii_hexdigit())
        });
        let kind = if self.speech_summary.is_some() {
            self.speech_status = "completed";
            "speech_completed"
        } else {
            self.speech_status = "failed";
            "tts_failed"
        };
        self.finish(kind);
    }
    pub fn audio_eof(&mut self) {
        if self.session.as_ref().is_some_and(|s| s.capture.is_some()) {
            self.finish("capture_completed");
        }
    }
    pub fn wake_health(&mut self, status: &'static str) {
        self.wake_status = status;
        if status == "failed" {
            self.completed_audio = None;
            self.finish("cancelled");
            self.emit("wake_worker".into(), None, "wake_failed");
        }
    }
    pub fn deadline(&self) -> Option<Instant> {
        self.session
            .as_ref()
            .map(|s| s.audio_deadline.map_or(s.deadline, |a| a.min(s.deadline)))
    }
    pub fn expire(&mut self, now: Instant) {
        if self.deadline().is_some_and(|d| now >= d) {
            let kind = if self
                .session
                .as_ref()
                .is_some_and(|s| s.audio_deadline.is_some_and(|d| now >= d))
            {
                "audio_error"
            } else {
                "timed_out"
            };
            self.finish(kind);
        }
    }
    pub fn shutdown(&mut self) {
        self.completed_audio = None;
        if self.session.is_some() {
            self.finish("cancelled");
        }
    }
    fn finish(&mut self, kind: &'static str) {
        if let Some(mut s) = self.session.take() {
            if let Some(capture) = s.capture.take() {
                self.capture_summary = Some(capture.summary(s.id, kind));
                if kind == "capture_completed" && self.stt_status == "ready" {
                    self.stt_requests
                        .push_back(SttRequest::Finish { session_id: s.id });
                    s.stage = State::Transcribing;
                    s.deadline = s.deadline.min(
                        s.audio_deadline.unwrap_or_else(Instant::now) + Duration::from_secs(4),
                    );
                    s.audio_deadline = None;
                    self.emit(s.request_id.clone(), Some(s.id), kind);
                    self.session = Some(s);
                    return;
                }
                if kind == "capture_completed" {
                    self.completed_audio = Some(capture);
                }
            }
            self.speech_job = None;
            if s.stage == State::Speaking && self.speech_status == "speaking" {
                self.speech_status = kind;
            }
            self.command_job = None;
            self.expected_command = None;
            if s.stage == State::Executing && self.command_outcome.is_none() {
                self.command_outcome = Some(Outcome {
                    session_id: s.id,
                    code: kind,
                    receipt: None,
                });
            }
            if kind != "transcript_final"
                && !kind.starts_with("command_")
                && !matches!(kind, "speech_completed" | "tts_failed")
            {
                self.transcript = None;
            }
            if self.stt_engine.is_some() && kind != "transcript_final" {
                self.stt_requests
                    .push_back(SttRequest::Cancel { session_id: s.id });
            }
            self.emit(s.request_id, Some(s.id), kind);
        }
    }
    fn emit(&mut self, request_id: String, session_id: Option<u64>, kind: &'static str) {
        self.sequence += 1;
        if self.events.len() == 64 {
            self.events.pop_front();
        }
        self.events.push_back(Event {
            sequence: self.sequence,
            request_id,
            session_id,
            kind,
        });
    }
    pub fn response(&self, request_id: String, code: &'static str) -> Response {
        Response {
            command: self.command_outcome.clone(),
            speech_status: self.speech_status,
            speech_samples: self.speech_samples,
            text_input_available: self.virtual_input && self.command_wake.is_some(),
            speech: self.speech_summary.clone(),
            version: VERSION,
            stt_status: self.stt_status,
            transcript: self.transcript.clone(),
            capture: self.capture_summary.clone(),
            wake_status: self.wake_status,
            request_id,
            code,
            state: self
                .session
                .as_ref()
                .map(|s| s.stage.clone())
                .unwrap_or(State::Idle),
            session_id: self.session.as_ref().map(|s| s.id),
            sequence: self.sequence,
            events: self.events.iter().cloned().collect(),
        }
    }
    pub fn handle(&mut self, req: Request, now: Instant) -> Response {
        self.expire(now);
        if req.version != VERSION {
            return self.response(req.request_id, "version_mismatch");
        }
        if !valid_id(&req.request_id) {
            return self.response(String::new(), "invalid_id");
        }
        if matches!(req.operation, Operation::Snapshot) {
            return self.response(req.request_id, "ok");
        }
        if self.recent_requests.contains(&req.request_id) {
            return self.response(req.request_id, "duplicate");
        }
        if self.recent_requests.len() == 128 {
            self.recent_requests.pop_front();
        }
        self.recent_requests.push_back(req.request_id.clone());
        let code = match req.operation {
            Operation::Text { raw } => {
                if !self.virtual_input || self.command_wake.is_none() {
                    "input_disabled"
                } else if self.session.is_some() {
                    "busy"
                } else if raw.trim().is_empty()
                    || raw.len() > 512
                    || raw.chars().any(char::is_control)
                {
                    "invalid_text"
                } else {
                    self.start_session(req.request_id.clone(), now);
                    let s = self.session.as_mut().expect("text session");
                    s.stage = State::Transcribing;
                    self.transcript = Some(Transcript {
                        source: "user_text",
                        session_id: s.id,
                        revision: 1,
                        audio_end_us: 0,
                        normalized: raw.split_whitespace().collect::<Vec<_>>().join(" "),
                        raw,
                        is_final: true,
                        confidence: None,
                    });
                    self.emit(
                        req.request_id.clone(),
                        self.session.as_ref().map(|s| s.id),
                        "transcript_final",
                    );
                    self.dispatch_command(now);
                    "ok"
                }
            }
            Operation::VirtualWake if !self.virtual_input => "virtual_input_disabled",
            Operation::VirtualWake if self.session.is_some() => "busy",
            Operation::VirtualWake => {
                self.start_session(req.request_id.clone(), now);
                "ok"
            }
            Operation::Cancel { session_id }
                if self.session.as_ref().is_some_and(|s| s.id == session_id) =>
            {
                self.finish("cancelled");
                "ok"
            }
            Operation::Cancel { .. } => "stale_session",
            // Caller-supplied capability is never an internal grant.
            Operation::Action {
                session_id,
                capability: _,
            } => {
                if self.session.as_ref().is_some_and(|s| s.id == session_id) {
                    "denied"
                } else {
                    "stale_session"
                }
            }
            Operation::Snapshot => unreachable!(),
        };
        self.response(req.request_id, code)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request(id: &str, operation: Operation) -> Request {
        Request {
            version: VERSION,
            request_id: id.into(),
            operation,
        }
    }
    #[test]
    fn lifecycle_and_deadline_fence() {
        let now = Instant::now();
        let mut c = Core::new(Duration::from_secs(1), true);
        let wake = c.handle(request("w", Operation::VirtualWake), now);
        assert_eq!(wake.events[0].request_id, "w");
        assert_eq!(wake.session_id, Some(1));
        assert_eq!(
            c.handle(request("x", Operation::VirtualWake), now).code,
            "busy"
        );
        assert_eq!(
            c.handle(
                request(
                    "a",
                    Operation::Action {
                        session_id: 1,
                        capability: Capability::OpenApp
                    }
                ),
                now
            )
            .code,
            "denied"
        );
        assert_eq!(
            c.handle(
                request(
                    "b",
                    Operation::Action {
                        session_id: 1,
                        capability: Capability::Status
                    }
                ),
                now + Duration::from_secs(1)
            )
            .code,
            "stale_session"
        );
        assert!(c.deadline().is_none());
        assert_eq!(c.events.back().unwrap().kind, "timed_out");
    }
    #[test]
    fn duplicate_cancel_and_late_requests() {
        let mut c = Core::new(Duration::from_secs(1), true);
        let now = Instant::now();
        c.handle(request("w", Operation::VirtualWake), now);
        assert_eq!(
            c.handle(request("w", Operation::VirtualWake), now).code,
            "duplicate"
        );
        c.handle(request("c", Operation::Cancel { session_id: 1 }), now);
        c.handle(request("w2", Operation::VirtualWake), now);
        assert_eq!(
            c.handle(request("late", Operation::Cancel { session_id: 1 }), now)
                .code,
            "stale_session"
        );
        assert_eq!(c.session.as_ref().unwrap().id, 2);
        c.shutdown();
        assert!(c.session.is_none());
    }
    #[test]
    fn streaming_fences_revision_identity_and_premature_final() {
        let now = Instant::now();
        let mut c = Core::new(Duration::from_secs(30), false);
        c.enable_capture();
        c.configure_stt("test".into());
        c.stt_reply(
            SttReply::Ready {
                engine: "test".into(),
            },
            now,
        );
        c.capture_packet(
            AudioFrame {
                timestamp_us: 0,
                sample_rate: 16000,
                channels: 1,
                samples: vec![0.; 1600],
            },
            Some(true),
            vec![0.; 1600],
            true,
            now,
        );
        let partial = |id, revision| SttReply::Partial {
            engine: "test".into(),
            session_id: id,
            revision,
            audio_end_us: 100000,
            raw: " open   Brave ".into(),
        };
        c.stt_reply(partial(2, 1), now);
        assert!(c.transcript.is_none());
        c.stt_reply(partial(1, 1), now);
        assert_eq!(c.transcript.as_ref().unwrap().normalized, "open Brave");
        let sequence = c.sequence;
        c.stt_reply(partial(1, 1), now);
        assert_eq!(c.sequence, sequence);
        let final_reply = || SttReply::Final {
            engine: "test".into(),
            session_id: 1,
            revision: 2,
            audio_end_us: 100000,
            raw: "open Brave".into(),
        };
        c.stt_reply(final_reply(), now);
        assert!(!c.transcript.as_ref().unwrap().is_final);
        assert_eq!(
            c.handle(
                request(
                    "partial_action",
                    Operation::Action {
                        session_id: 1,
                        capability: Capability::OpenApp
                    }
                ),
                now
            )
            .code,
            "denied"
        );
        c.audio_eof();
        assert_eq!(c.session.as_ref().unwrap().stage, State::Transcribing);
        c.stt_reply(final_reply(), now);
        assert!(c.transcript.as_ref().unwrap().is_final && c.session.is_none());
        let sequence = c.sequence;
        c.stt_reply(final_reply(), now);
        assert_eq!(c.sequence, sequence);
    }
    #[test]
    fn streaming_backpressure_is_terminal_and_drops_pending_audio() {
        let now = Instant::now();
        let mut c = Core::new(Duration::from_secs(30), false);
        c.enable_capture();
        c.configure_stt("test".into());
        c.stt_reply(
            SttReply::Ready {
                engine: "test".into(),
            },
            now,
        );
        for i in 0..50 {
            c.capture_packet(
                AudioFrame {
                    timestamp_us: i * 100000,
                    sample_rate: 16000,
                    channels: 1,
                    samples: vec![0.1; 1600],
                },
                Some(true),
                if i == 0 { vec![0.1; 1600] } else { vec![] },
                i == 0,
                now + Duration::from_millis(i * 100),
            );
        }
        assert_eq!(c.stt_status, "failed");
        assert!(c.session.is_none() && c.completed_audio.is_none());
        assert!(c.stt_requests.len() <= 1);
    }
    #[test]
    fn capture_no_speech_cancel_and_stalled_producer_release_pcm() {
        fn frame(ts: u64) -> AudioFrame {
            AudioFrame {
                timestamp_us: ts,
                sample_rate: 16000,
                channels: 1,
                samples: vec![0.; 1600],
            }
        }
        let now = Instant::now();
        let mut c = Core::new(Duration::from_secs(30), false);
        c.enable_capture();
        c.capture_packet(frame(0), Some(false), vec![0.; 1600], true, now);
        for i in 1..=30 {
            c.capture_packet(
                frame(i * 100000),
                Some(false),
                vec![],
                false,
                now + Duration::from_millis(i * 100),
            );
        }
        assert_eq!(c.capture_summary.as_ref().unwrap().reason, "no_speech");
        assert!(c.session.is_none() && c.completed_audio.is_none());
        c.capture_packet(
            frame(4000000),
            Some(true),
            vec![0.; 1600],
            true,
            now + Duration::from_secs(4),
        );
        let sid = c.session.as_ref().unwrap().id;
        c.handle(
            request("cancel_capture", Operation::Cancel { session_id: sid }),
            now + Duration::from_secs(4),
        );
        assert_eq!(c.capture_summary.as_ref().unwrap().reason, "cancelled");
        assert!(c.session.is_none() && c.completed_audio.is_none());
        c.capture_packet(
            frame(5000000),
            Some(true),
            vec![0.; 1600],
            true,
            now + Duration::from_secs(5),
        );
        c.expire(now + Duration::from_secs(6));
        assert_eq!(c.capture_summary.as_ref().unwrap().reason, "audio_error");
        assert!(c.session.is_none() && c.completed_audio.is_none());
        c.capture_packet(
            frame(6000000),
            Some(false),
            vec![],
            false,
            now + Duration::from_secs(6),
        );
        assert!(c.session.is_none());
    }
    #[test]
    fn eof_retains_one_bounded_audio_until_next_session_or_shutdown() {
        let now = Instant::now();
        let mut c = Core::new(Duration::from_secs(30), false);
        c.enable_capture();
        c.capture_packet(
            AudioFrame {
                timestamp_us: 0,
                sample_rate: 16000,
                channels: 1,
                samples: vec![0.; 1600],
            },
            Some(true),
            vec![0.; 1600],
            true,
            now,
        );
        c.audio_eof();
        assert!(c.completed_audio.is_some());
        assert_eq!(
            c.capture_summary.as_ref().unwrap().reason,
            "capture_completed"
        );
        c.shutdown();
        assert!(c.completed_audio.is_none());
    }
    #[test]
    fn native_wake_reuses_session_authority_and_failure_cancels() {
        let now = Instant::now();
        let mut c = Core::new(Duration::from_secs(1), false);
        c.wake_health("replaying");
        c.audio_wake(now);
        c.audio_wake(now);
        assert_eq!(c.events.len(), 1);
        assert_eq!(c.session.as_ref().unwrap().id, 1);
        assert_eq!(c.response("s".into(), "ok").wake_status, "replaying");
        assert_eq!(
            c.handle(
                request(
                    "a",
                    Operation::Action {
                        session_id: 1,
                        capability: Capability::OpenApp
                    }
                ),
                now
            )
            .code,
            "denied"
        );
        c.wake_health("failed");
        assert!(c.session.is_none());
        assert_eq!(c.events.back().unwrap().kind, "wake_failed");
        assert_eq!(
            c.handle(request("late", Operation::Cancel { session_id: 1 }), now)
                .code,
            "stale_session"
        );
    }
    #[test]
    fn bounds_and_production_denial() {
        let now = Instant::now();
        let mut c = Core::new(Duration::from_secs(1), false);
        assert_eq!(
            c.handle(request("w", Operation::VirtualWake), now).code,
            "virtual_input_disabled"
        );
        c.virtual_input = true;
        for n in 0..200 {
            c.handle(request(&format!("w{n}"), Operation::VirtualWake), now);
            c.shutdown();
        }
        assert_eq!(c.events.len(), 64);
        assert_eq!(c.recent_requests.len(), 128);
        assert_eq!(
            c.handle(request("../private", Operation::VirtualWake), now)
                .code,
            "invalid_id"
        );
    }
    fn command_session(text: &str) -> (Core, Instant) {
        let now = Instant::now();
        let mut c = Core::new(Duration::from_secs(30), true);
        c.configure_commands("Hey Gideon".into());
        c.configure_stt("test".into());
        c.stt_reply(
            SttReply::Ready {
                engine: "test".into(),
            },
            now,
        );
        c.audio_wake(now);
        c.session.as_mut().unwrap().stage = State::Transcribing;
        c.stt_reply(
            SttReply::Final {
                engine: "test".into(),
                session_id: 1,
                revision: 1,
                audio_end_us: 1,
                raw: text.into(),
            },
            now,
        );
        (c, now)
    }
    #[test]
    fn command_fences_result_cancel_timeout_duplicate_and_busy() {
        let (mut c, now) = command_session("Hey Gideon, open Brave.");
        let job = c.take_command_job().unwrap();
        assert!(c.command_is_active(1));
        assert_eq!(
            c.handle(request("busy", Operation::VirtualWake), now).code,
            "busy"
        );
        let receipt = Receipt {
            job: job.clone(),
            verified: true,
            scope: "sandbox".into(),
            result: "verified".into(),
        };
        let wrong = Job {
            session_id: 1,
            command: Command::Mute,
        };
        c.command_reply(
            wrong.clone(),
            Some(Receipt {
                job: wrong,
                ..receipt.clone()
            }),
            now,
        );
        assert!(c.command_is_active(1));
        c.command_reply(job.clone(), Some(receipt.clone()), now);
        assert_eq!(c.command_outcome.as_ref().unwrap().code, "command_success");
        let seq = c.sequence;
        c.command_reply(job.clone(), Some(receipt.clone()), now);
        assert_eq!(c.sequence, seq);
        let (mut c, now) = command_session("open brave");
        assert_eq!(
            c.handle(request("cancel", Operation::Cancel { session_id: 1 }), now)
                .code,
            "ok"
        );
        assert_eq!(
            c.handle(request("cancel", Operation::Cancel { session_id: 1 }), now)
                .code,
            "duplicate"
        );
        c.command_reply(job.clone(), Some(receipt.clone()), now);
        assert_eq!(c.command_outcome.as_ref().unwrap().code, "cancelled");
        assert!(c.take_command_job().is_none());
        let (mut c, now) = command_session("open brave");
        c.command_reply(job, Some(receipt), now + Duration::from_secs(3));
        assert_eq!(c.command_outcome.as_ref().unwrap().code, "timed_out");
    }
    #[test]
    fn command_safety_denial_failure_and_final_only() {
        for (text, code) in [
            ("do not open brave", "unsupported"),
            ("open steam", "app_unavailable"),
        ] {
            let (mut c, _) = command_session(text);
            assert!(c.take_command_job().is_none());
            assert_eq!(c.command_outcome.as_ref().unwrap().code, code);
        }
        let (mut c, now) = command_session("open brave");
        let job = c.take_command_job().unwrap();
        c.stt_reply(
            SttReply::Partial {
                engine: "test".into(),
                session_id: 1,
                revision: 2,
                audio_end_us: 1,
                raw: "mute".into(),
            },
            now,
        );
        assert!(c.transcript.as_ref().unwrap().is_final);
        c.command_reply(job, None, now);
        assert_eq!(c.command_outcome.as_ref().unwrap().code, "command_failed");
        let (mut c, _) = command_session("cancel");
        assert!(c.take_command_job().is_none());
        assert!(c.session.is_none());
    }
    #[test]
    fn speech_preserves_effect_and_fences_cancel_failure_late_and_timeout() {
        let (mut c, now) = command_session("open brave");
        c.enable_tts();
        let job = c.take_command_job().unwrap();
        let receipt = Receipt {
            job: job.clone(),
            verified: true,
            scope: "sandbox".into(),
            result: "verified".into(),
        };
        c.command_reply(job.clone(), Some(receipt.clone()), now);
        assert!(c.speech_is_active(1));
        c.speech_progress(2, 1920);
        assert_eq!(c.speech_samples, 0);
        c.speech_progress(1, 1920);
        c.speech_progress(1, 1);
        assert_eq!(c.speech_samples, 1920);
        assert_eq!(
            c.take_speech_job().unwrap().text,
            "Sandbox application completed."
        );
        c.speech_reply(2, None, now);
        assert!(c.speech_is_active(1));
        c.handle(
            request("speech_cancel", Operation::Cancel { session_id: 1 }),
            now,
        );
        c.speech_reply(1, None, now);
        assert_eq!(c.speech_status, "cancelled");
        assert_eq!(c.command_outcome.as_ref().unwrap().code, "command_success");
        let (mut c, now) = command_session("open brave");
        c.enable_tts();
        c.command_reply(job.clone(), Some(receipt.clone()), now);
        c.speech_reply(1, None, now);
        assert_eq!(c.speech_status, "failed");
        assert!(c.session.is_none());
        assert_eq!(c.command_outcome.as_ref().unwrap().code, "command_success");
        let (mut c, now) = command_session("open brave");
        c.enable_tts();
        c.command_reply(job, Some(receipt), now);
        c.speech_reply(1, None, now + Duration::from_secs(21));
        assert_eq!(c.speech_status, "timed_out");
    }
    #[test]
    fn explicit_text_input_shares_command_policy_but_cannot_inject_native_finals() {
        let now = Instant::now();
        let mut c = Core::new(Duration::from_secs(30), false);
        c.configure_commands("custom phrase".into());
        assert_eq!(
            c.handle(
                request(
                    "t1",
                    Operation::Text {
                        raw: "open brave".into()
                    }
                ),
                now
            )
            .code,
            "input_disabled"
        );
        c.virtual_input = true;
        assert_eq!(
            c.handle(
                request(
                    "t2",
                    Operation::Text {
                        raw: "open brave\nreboot".into()
                    }
                ),
                now
            )
            .code,
            "invalid_text"
        );
        c.handle(
            request(
                "t3",
                Operation::Text {
                    raw: "don't open brave".into(),
                },
            ),
            now,
        );
        assert!(c.take_command_job().is_none());
        assert_eq!(c.command_outcome.as_ref().unwrap().code, "unsupported");
        c.handle(
            request(
                "t4",
                Operation::Text {
                    raw: "open brave".into(),
                },
            ),
            now,
        );
        assert_eq!(c.transcript.as_ref().unwrap().source, "user_text");
        assert!(c.take_command_job().is_some());
        assert_eq!(
            c.handle(request("t5", Operation::Text { raw: "mute".into() }), now)
                .code,
            "busy"
        );
        assert_eq!(
            c.handle(request("t4", Operation::Text { raw: "mute".into() }), now)
                .code,
            "duplicate"
        );
    }
}
