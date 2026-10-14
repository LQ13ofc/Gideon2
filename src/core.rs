use crate::{
    audio::AudioFrame,
    capture::{Capture, CaptureSummary},
    protocol::*,
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
        }
    }
    pub fn set_boot_seed(&mut self, seed: u64) {
        self.next_session = seed;
    }
    fn start_session(&mut self, request_id: String, now: Instant) {
        self.completed_audio = None;
        self.capture_summary = None;
        let id = self.next_session;
        self.next_session += 1;
        self.session = Some(Session {
            id,
            request_id: request_id.clone(),
            deadline: now + self.timeout,
            capture: None,
            audio_deadline: None,
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
        let Some(speech) = speech else {
            self.wake_health("failed");
            return;
        };
        if self.session.is_none() {
            if detected {
                self.audio_wake(now);
                match Capture::new(pre_roll, frame.end_us()) {
                    Ok(c) => {
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
                match c.push(frame, speech) {
                    Ok(Some(reason)) => self.finish(reason),
                    Err(_) => self.finish("audio_error"),
                    Ok(None) => {}
                }
            }
        }
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
                if kind == "capture_completed" {
                    self.completed_audio = Some(capture);
                }
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
            version: VERSION,
            capture: self.capture_summary.clone(),
            wake_status: self.wake_status,
            request_id,
            code,
            state: if self.session.is_some() {
                State::Capturing
            } else {
                State::Idle
            },
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
            // No execution is available at A0; caller-supplied capability is never a grant.
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
}
