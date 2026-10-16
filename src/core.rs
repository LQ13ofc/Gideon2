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
    audio_end_us: u64,
}

/// Single owner for sessions, events and authority; no detached action tasks.
pub struct Core {
    base_pack: Option<crate::pack::Snapshot>,
    hub: Option<crate::hub::Snapshot>,
    configuration_status: crate::storage::ConfigurationStatus,
    configuration_recovery_available: bool,
    preferences: crate::storage::Config,
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
    plugins: crate::plugins::PluginView,
}
impl Core {
    pub fn new(timeout: Duration, virtual_input: bool) -> Self {
        Self {
            base_pack: None,
            hub: None,
            configuration_status: crate::storage::ConfigurationStatus::Ready,
            configuration_recovery_available: false,
            preferences: crate::storage::Config {
                session_timeout_ms: timeout.as_millis() as u64,
                ..Default::default()
            },
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
            plugins: Default::default(),
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
            audio_end_us: 0,
        });
        self.emit(request_id, Some(id), "session_started");
    }
    pub fn audio_wake(&mut self, now: Instant) {
        self.expire(now);
        if self.session.is_none()
            && self.configuration_status == crate::storage::ConfigurationStatus::Ready
        {
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
                            s.audio_end_us = frame.end_us();
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
                let previous_len = c.samples.len();
                let begin = frame.timestamp_us;
                let frame_end = frame.end_us();
                let endpoint = c.push(frame, speech);
                // Only accepted PCM goes to STT; valid 100ms capture frames are split
                // into the worker's <=80ms packets without dropping samples.
                if endpoint.is_ok() && c.samples.len() > previous_len {
                    s.audio_end_us = frame_end;
                    if self.stt_status == "ready" {
                        for (i, chunk) in c.samples[previous_len..].chunks(1280).enumerate() {
                            self.stt_requests.push_back(SttRequest::Frame {
                                session_id: s.id,
                                end_us: begin + (i * 1280 + chunk.len()) as u64 * 1_000_000 / 16000,
                                samples: chunk.to_vec(),
                            });
                        }
                    }
                }
                match endpoint {
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
            || end > s.audio_end_us
            || (final_result && end != s.audio_end_us)
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
        s.deadline = s.overall_deadline.min(now + Duration::from_secs(2));
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
        if !self.tts_enabled
            || !self.preferences.audible_feedback
            || self.preferences.output_volume_percent == 0
        {
            if self.tts_enabled {
                self.speech_status = if self.preferences.output_volume_percent == 0 {
                    "muted"
                } else {
                    "disabled"
                };
            }
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
            output_volume_percent: self.preferences.output_volume_percent,
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
            s.output_volume_percent == self.preferences.output_volume_percent
                && s.session_id == id
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
            if kind == "timed_out"
                && self.tts_enabled
                && self
                    .session
                    .as_ref()
                    .is_some_and(|s| s.stage == State::Executing && now < s.overall_deadline)
            {
                let id = self.session.as_ref().unwrap().id;
                self.command_outcome = Some(Outcome {
                    session_id: id,
                    code: "timed_out",
                    receipt: None,
                });
                self.command_terminal("command_failed", now);
            } else {
                self.finish(kind);
            }
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
            base_pack: self.base_pack.clone(),
            hub: self.hub.clone(),
            plugins: self.plugins.snapshot(self.hub.as_ref()),
            capability_result: self.plugins.last().cloned(),
            configuration_status: self.configuration_status,
            configuration_recovery_available: self.configuration_recovery_available,
            preferences: self.preferences.clone(),
            command: self.command_outcome.clone(),
            speech_status: self.speech_status,
            speech_samples: self.speech_samples,
            text_input_available: self.configuration_status
                == crate::storage::ConfigurationStatus::Ready
                && self.virtual_input
                && self.command_wake.is_some(),
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
    pub fn configure_preferences(&mut self, config: &crate::storage::Config) {
        self.preferences = config.clone();
        self.timeout = Duration::from_millis(config.session_timeout_ms);
    }
    pub fn hub_import_expired(&mut self, storage: &crate::storage::Storage) {
        if let Some(hub) = self.hub.take() {
            self.hub = Some(crate::hub::import_progress(hub, storage));
        }
        self.emit(String::new(), None, "hub_import_timeout");
    }
    pub fn configure_hub(&mut self, hub: crate::hub::Snapshot) {
        self.hub = Some(hub);
    }
    /// Loads the C0 plugin ledger; enabled plugins start only in Ready configuration.
    pub fn configure_plugins(
        &mut self,
        storage: &crate::storage::Storage,
        runtime_available: bool,
    ) {
        self.plugins.configure(storage, runtime_available);
        if self.configuration_status != crate::storage::ConfigurationStatus::Ready {
            return;
        }
        let hub = self.hub.clone().map(|h| h.with_approvals(storage));
        self.plugins.boot(storage, hub.as_ref());
        if hub.is_some() {
            self.hub = hub;
        }
        self.flush_plugin_events("");
    }
    /// Host facts: the Core never blocks on plugin processes.
    pub fn plugin_event(&mut self, ev: crate::plugins::Ev, now: Instant) {
        self.plugins.event(ev, now);
        self.flush_plugin_events("");
    }
    pub fn take_plugin_intents(&mut self) -> Vec<crate::plugins::Intent> {
        self.plugins.take_intents()
    }
    fn flush_plugin_events(&mut self, request_id: &str) {
        for kind in self.plugins.take_events() {
            self.emit(request_id.to_owned(), None, kind);
        }
    }
    fn plugin_result(
        &mut self,
        request_id: &str,
        result: Result<(), &'static str>,
    ) -> &'static str {
        self.flush_plugin_events(request_id);
        match result {
            Ok(()) => "ok",
            Err(code) => code,
        }
    }
    /// Pruning runs at every request so a changed catalog, approval or payload disables plugins.
    fn refresh_plugins(&mut self, storage: &crate::storage::Storage) {
        if !self.plugins.has_enabled() {
            return;
        }
        let hub = self.hub.clone().map(|h| h.with_approvals(storage));
        self.plugins.refresh(storage, hub.as_ref());
        if hub.is_some() {
            self.hub = hub;
        }
        self.flush_plugin_events("");
    }
    pub fn configure_pack(&mut self, pack: crate::pack::Snapshot) {
        self.base_pack = Some(pack);
    }
    pub fn configure_storage(&mut self, storage: &crate::storage::Storage) {
        self.configure_preferences(&storage.config);
        self.configuration_status = storage.configuration_status;
        self.configuration_recovery_available = storage.recovery_available();
    }
    pub fn handle(&mut self, req: Request, now: Instant) -> Response {
        self.handle_with_storage(req, now, None)
    }
    pub fn handle_with_storage(
        &mut self,
        req: Request,
        now: Instant,
        mut storage: Option<&mut crate::storage::Storage>,
    ) -> Response {
        self.expire(now);
        if let Some(storage) = storage.as_deref_mut() {
            if crate::hub::expire_import(storage, now) {
                self.hub_import_expired(storage);
            }
            self.refresh_plugins(storage);
        }
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
            Operation::RecoverConfiguration { revision }
                if revision != self.preferences.revision =>
            {
                "stale_preferences"
            }
            Operation::RecoverConfiguration { .. }
                if self.configuration_status != crate::storage::ConfigurationStatus::SafeMode =>
            {
                "recovery_unavailable"
            }
            Operation::RecoverConfiguration { revision } => {
                if let Some(storage) = storage {
                    let result = storage.recover_configuration(revision);
                    self.configure_storage(storage);
                    if result.is_ok() {
                        self.emit(req.request_id.clone(), None, "configuration_recovered");
                        "ok"
                    } else {
                        "configuration_recovery_error"
                    }
                } else {
                    "recovery_unavailable"
                }
            }
            Operation::HubAbort { import_id } => {
                if let (Some(storage), Some(hub)) = (storage, self.hub.as_ref()) {
                    let result = crate::hub::abort_import(storage, &import_id);
                    self.hub = Some(crate::hub::import_progress(hub.clone(), storage));
                    match result {
                        Ok(()) => {
                            self.emit(req.request_id.clone(), None, "hub_import_cancelled");
                            "ok"
                        }
                        Err(code) => code,
                    }
                } else {
                    "hub_unavailable"
                }
            }
            _ if self.configuration_status != crate::storage::ConfigurationStatus::Ready => {
                "configuration_not_ready"
            }
            Operation::PluginEnable { .. }
            | Operation::PluginDisable { .. }
            | Operation::PluginRevoke { .. }
            | Operation::CapabilityInvoke { .. }
            | Operation::CapabilityCancel { .. }
                if self.session.is_some() =>
            {
                "busy"
            }
            Operation::PluginEnable {
                revision,
                plugin_id,
            } => match (storage.as_deref_mut(), self.hub.clone()) {
                (Some(storage), Some(hub)) => {
                    let hub = hub.with_approvals(storage);
                    let result = self.plugins.enable(storage, &hub, revision, &plugin_id);
                    self.hub = Some(hub);
                    self.plugin_result(&req.request_id, result)
                }
                _ => "hub_unavailable",
            },
            Operation::PluginDisable {
                revision,
                plugin_id,
            } => match storage.as_deref_mut() {
                Some(storage) => {
                    let result = self.plugins.disable(storage, revision, &plugin_id);
                    self.plugin_result(&req.request_id, result)
                }
                None => "plugin_unavailable",
            },
            Operation::PluginRevoke {
                revision,
                plugin_id,
            } => match (storage.as_deref_mut(), self.hub.clone()) {
                (Some(storage), Some(hub)) => {
                    let hub = hub.with_approvals(storage);
                    let result = self.plugins.revoke(storage, &hub, revision, &plugin_id);
                    self.hub = Some(hub.with_approvals(storage));
                    self.plugin_result(&req.request_id, result)
                }
                _ => "hub_unavailable",
            },
            Operation::CapabilityInvoke {
                capability,
                input,
                deadline_ms,
            } => {
                let result =
                    self.plugins
                        .invoke(self.hub.as_ref(), &capability, input, deadline_ms);
                self.plugin_result(&req.request_id, result)
            }
            Operation::CapabilityCancel { capability } => {
                let result = self.plugins.cancel(&capability);
                self.plugin_result(&req.request_id, result)
            }

            Operation::HubBegin { .. }
            | Operation::HubChunk { .. }
            | Operation::HubFinish { .. }
                if self.session.is_some() =>
            {
                "busy"
            }
            Operation::HubApprove { .. }
                if storage.as_ref().is_some_and(|s| s.hub_import.is_some()) =>
            {
                "hub_import_busy"
            }
            Operation::HubBegin {
                revision,
                plugin_id,
                manifest_sha256,
            } => {
                if let (Some(storage), Some(hub)) = (storage, self.hub.as_ref()) {
                    let result = crate::hub::begin_import(
                        storage,
                        hub,
                        revision,
                        &plugin_id,
                        &manifest_sha256,
                        &format!("hub_{}_{}", self.next_session, self.sequence),
                        now,
                    );
                    self.hub = Some(hub.clone().with_approvals(storage));
                    match result {
                        Ok(()) => {
                            self.emit(req.request_id.clone(), None, "hub_import_started");
                            "ok"
                        }
                        Err(code) => code,
                    }
                } else {
                    "hub_unavailable"
                }
            }
            Operation::HubChunk {
                import_id,
                offset,
                hex,
            } => {
                if let (Some(storage), Some(hub)) = (storage, self.hub.as_ref()) {
                    let result = crate::hub::chunk_import(storage, &import_id, offset, &hex);
                    // Progress must not rehash all staged payloads on every small chunk.
                    self.hub = Some(crate::hub::import_progress(hub.clone(), storage));
                    match result {
                        Ok(()) => "ok",
                        Err(code) => code,
                    }
                } else {
                    "hub_unavailable"
                }
            }
            Operation::HubFinish { import_id } => {
                if let (Some(storage), Some(hub)) = (storage, self.hub.as_ref()) {
                    let result = crate::hub::finish_import(storage, hub, &import_id);
                    self.hub = Some(hub.clone().with_approvals(storage));
                    match result {
                        Ok(()) => {
                            self.emit(req.request_id.clone(), None, "hub_payload_staged");
                            "ok"
                        }
                        Err(code) => code,
                    }
                } else {
                    "hub_unavailable"
                }
            }
            Operation::HubApprove { .. } if self.session.is_some() => "busy",
            Operation::HubApprove {
                revision,
                plugin_id,
                manifest_sha256,
                permissions,
                publisher_unverified_ack,
            } => {
                if let (Some(storage), Some(hub)) = (storage, self.hub.as_ref()) {
                    let result = crate::hub::approve(
                        storage,
                        hub,
                        revision,
                        &plugin_id,
                        &manifest_sha256,
                        &permissions,
                        publisher_unverified_ack,
                    );
                    self.hub = Some(hub.clone().with_approvals(storage));
                    match result {
                        Ok(()) => {
                            self.emit(req.request_id.clone(), None, "hub_permissions_approved");
                            "ok"
                        }
                        Err(code) => code,
                    }
                } else {
                    "hub_unavailable"
                }
            }
            Operation::HubInstall { .. }
            | Operation::HubRollback { .. }
            | Operation::HubRemove { .. }
                if self.session.is_some() =>
            {
                "busy"
            }
            Operation::HubInstall {
                revision,
                plugin_id,
                manifest_sha256,
            } => {
                if let (Some(storage), Some(hub)) = (storage, self.hub.as_ref()) {
                    let result =
                        crate::hub::install(storage, hub, revision, &plugin_id, &manifest_sha256);
                    self.hub = Some(hub.clone().with_approvals(storage));
                    match result {
                        Ok(event) => {
                            self.plugins.forget(storage, &plugin_id);
                            self.flush_plugin_events(&req.request_id);
                            self.emit(req.request_id.clone(), None, event);
                            "ok"
                        }
                        Err(code) => code,
                    }
                } else {
                    "hub_unavailable"
                }
            }
            Operation::HubRollback {
                revision,
                plugin_id,
            } => {
                if let (Some(storage), Some(hub)) = (storage, self.hub.as_ref()) {
                    let result = crate::hub::rollback(storage, hub, revision, &plugin_id);
                    self.hub = Some(hub.clone().with_approvals(storage));
                    match result {
                        Ok(event) => {
                            self.plugins.forget(storage, &plugin_id);
                            self.flush_plugin_events(&req.request_id);
                            self.emit(req.request_id.clone(), None, event);
                            "ok"
                        }
                        Err(code) => code,
                    }
                } else {
                    "hub_unavailable"
                }
            }
            Operation::HubRemove {
                revision,
                plugin_id,
            } => {
                if let (Some(storage), Some(hub)) = (storage, self.hub.as_ref()) {
                    let result = crate::hub::remove(storage, hub, revision, &plugin_id);
                    self.hub = Some(hub.clone().with_approvals(storage));
                    match result {
                        Ok(event) => {
                            self.plugins.forget(storage, &plugin_id);
                            self.flush_plugin_events(&req.request_id);
                            self.emit(req.request_id.clone(), None, event);
                            "ok"
                        }
                        Err(code) => code,
                    }
                } else {
                    "hub_unavailable"
                }
            }
            Operation::FeedbackPreferences { revision, .. }
                if revision != self.preferences.revision =>
            {
                "stale_preferences"
            }
            Operation::FeedbackPreferences { .. } if self.session.is_some() => "busy",
            Operation::FeedbackPreferences {
                output_volume_percent,
                ..
            } if output_volume_percent > 100 => "invalid_preferences",
            Operation::FeedbackPreferences {
                revision,
                visual_feedback,
                output_volume_percent,
            } => {
                if let Some(storage) = storage {
                    let result =
                        storage.update_feedback(revision, visual_feedback, output_volume_percent);
                    self.configure_storage(storage);
                    if result.is_ok() {
                        self.emit(req.request_id.clone(), None, "preferences_updated");
                        "ok"
                    } else {
                        "preferences_storage_error"
                    }
                } else {
                    "preferences_unavailable"
                }
            }
            Operation::SelectWake { revision, .. } if revision != self.preferences.revision => {
                "stale_preferences"
            }
            Operation::SelectWake { .. } if self.session.is_some() => "busy",
            Operation::SelectWake {
                revision,
                phrase_id,
            } => {
                if !self
                    .base_pack
                    .as_ref()
                    .is_some_and(|p| p.selectable(&phrase_id))
                {
                    "wake_not_qualified"
                } else if let Some(storage) = storage {
                    let result = storage.select_wake(revision, phrase_id);
                    self.configure_storage(storage);
                    if result.is_ok() {
                        self.emit(req.request_id.clone(), None, "preferences_updated");
                        "ok"
                    } else {
                        "preferences_storage_error"
                    }
                } else {
                    "preferences_unavailable"
                }
            }
            Operation::Preferences { revision, .. }
            | Operation::RollbackPreferences { revision }
                if revision != self.preferences.revision =>
            {
                "stale_preferences"
            }
            Operation::Preferences { .. } | Operation::RollbackPreferences { .. }
                if self.session.is_some() =>
            {
                "busy"
            }
            Operation::RollbackPreferences { .. }
                if self.base_pack.as_ref().is_some_and(|p| {
                    self.preferences
                        .previous_preferences
                        .as_ref()
                        .and_then(|prev| prev.wake_phrase.as_deref())
                        .is_some_and(|id| !p.selectable(id))
                }) =>
            {
                "wake_not_qualified"
            }
            Operation::Preferences {
                session_timeout_ms, ..
            } if !(50..=60000).contains(&session_timeout_ms) => "invalid_preferences",
            operation @ (Operation::Preferences { .. } | Operation::RollbackPreferences { .. }) => {
                if let Some(storage) = storage {
                    let result = match operation {
                        Operation::Preferences {
                            revision,
                            audible_feedback,
                            session_timeout_ms,
                        } => storage.update_preferences(
                            revision,
                            audible_feedback,
                            session_timeout_ms,
                        ),
                        Operation::RollbackPreferences { revision } => {
                            storage.rollback_preferences(revision)
                        }
                        _ => unreachable!(),
                    };
                    self.configure_storage(storage);
                    if result.is_ok() {
                        self.emit(req.request_id.clone(), None, "preferences_updated");
                        "ok"
                    } else {
                        "preferences_storage_error"
                    }
                } else {
                    "preferences_unavailable"
                }
            }

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
    fn safe_configuration_fences_native_wake_and_public_actions() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("root");
        drop(crate::storage::Storage::open(&root).unwrap());
        std::fs::write(root.join("config.json"), b"invalid").unwrap();
        let mut storage = crate::storage::Storage::open_for_runtime(&root).unwrap();
        storage.set_safe_epoch(99);
        let mut core = Core::new(Duration::from_secs(30), true);
        core.configure_storage(&storage);
        core.configure_commands("custom wake".into());
        let now = Instant::now();
        core.audio_wake(now);
        let snapshot = core.handle(request("snapshot", Operation::Snapshot), now);
        assert!(snapshot.session_id.is_none());
        assert!(!snapshot.text_input_available);
        assert_eq!(
            core.handle(request("wake", Operation::VirtualWake), now)
                .code,
            "configuration_not_ready"
        );
        let recovered = core.handle_with_storage(
            request("recover", Operation::RecoverConfiguration { revision: 99 }),
            now,
            Some(&mut storage),
        );
        assert_eq!(
            recovered.configuration_status,
            crate::storage::ConfigurationStatus::RestartRequired
        );
        core.audio_wake(now);
        assert!(core.response("next".into(), "ok").session_id.is_none());
    }
    #[test]
    fn pack_text_and_selection_are_independent_of_phrase_ids_and_native_labels() {
        let pack = crate::pack::Snapshot {
            version: 1,
            id: "test-pack".into(),
            scope: "dev_virtual_en",
            preflight: "verified",
            engines: Default::default(),
            wake_phrases: vec![
                crate::pack::WakeChoice {
                    id: "opaque_7".into(),
                    text: "Activate Atlas".into(),
                    qualification: "dev_qualified",
                },
                crate::pack::WakeChoice {
                    id: "opaque_8".into(),
                    text: "Other phrase".into(),
                    qualification: "poc_required",
                },
            ],
            active_phrase: Some("opaque_7".into()),
            default_phrase: "opaque_7".into(),
            voice: "Alba",
            language: "en".into(),
            audio_input: "virtual_pcm",
            audio_output: "virtual",
        };
        let mut core = Core::new(Duration::from_secs(30), true);
        core.configure_commands(pack.text("opaque_7").unwrap().into());
        core.configure_pack(pack);
        let now = Instant::now();
        core.handle(
            request(
                "command",
                Operation::Text {
                    raw: "Activate Atlas, open Brave.".into(),
                },
            ),
            now,
        );
        assert!(matches!(
            core.take_command_job().unwrap().command,
            Command::OpenApp { .. }
        ));
        core.shutdown();
        let temp = tempfile::tempdir().unwrap();
        let mut storage = crate::storage::Storage::open(&temp.path().join("root")).unwrap();
        core.configure_storage(&storage);
        assert_eq!(
            core.handle_with_storage(
                request(
                    "poc",
                    Operation::SelectWake {
                        revision: 0,
                        phrase_id: "opaque_8".into()
                    }
                ),
                now,
                Some(&mut storage)
            )
            .code,
            "wake_not_qualified"
        );
        let selected = core.handle_with_storage(
            request(
                "select",
                Operation::SelectWake {
                    revision: 0,
                    phrase_id: "opaque_7".into(),
                },
            ),
            now,
            Some(&mut storage),
        );
        assert_eq!(
            selected.configuration_status,
            crate::storage::ConfigurationStatus::RestartRequired
        );
        assert_eq!(
            selected.preferences.wake_phrase.as_deref(),
            Some("opaque_7")
        );
        assert!(core
            .handle(request("blocked", Operation::VirtualWake), now)
            .session_id
            .is_none());
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
        c.session.as_mut().unwrap().audio_end_us = 1;
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
    #[test]
    fn capture_100ms_frames_are_split_and_invalid_pcm_never_reaches_stt() {
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
        let frame = |ts| AudioFrame {
            timestamp_us: ts,
            sample_rate: 16000,
            channels: 1,
            samples: vec![0.1; 1600],
        };
        c.capture_packet(frame(0), Some(true), vec![0.1; 1600], true, now);
        c.take_stt_requests();
        c.capture_packet(frame(100000), Some(true), Vec::new(), false, now);
        let requests = c.take_stt_requests();
        let mut received = Vec::new();
        let mut ends = Vec::new();
        for r in requests {
            if let SttRequest::Frame {
                samples, end_us, ..
            } = r
            {
                assert!(samples.len() <= 1280);
                received.extend(samples);
                ends.push(end_us);
            }
        }
        assert_eq!(received, vec![0.1; 1600]);
        assert_eq!(ends, vec![180000, 200000]);
        c.stt_reply(
            SttReply::Partial {
                engine: "test".into(),
                session_id: 1,
                revision: 1,
                audio_end_us: 300000,
                raw: "open brave".into(),
            },
            now,
        );
        assert!(c.transcript.is_none());
        c.capture_packet(frame(400000), Some(true), Vec::new(), false, now);
        assert!(c
            .take_stt_requests()
            .iter()
            .all(|r| !matches!(r, SttRequest::Frame { .. })));
        assert!(c.session.is_none());
    }
    #[test]
    fn executor_gets_its_own_budget_and_deadline_failure_feedback_is_correlated() {
        let (mut c, now) = command_session("open brave");
        c.enable_tts();
        c.session.as_mut().unwrap().deadline = now + Duration::from_secs(2);
        let job = c.take_command_job().unwrap();
        c.expire(now + Duration::from_secs(3));
        assert!(c.speech_is_active(1));
        assert_eq!(c.command_outcome.as_ref().unwrap().code, "timed_out");
        assert_eq!(c.take_speech_job().unwrap().text, "Command failed.");
        c.command_reply(job, None, now + Duration::from_secs(3));
        assert!(c.speech_is_active(1));
        let (mut c, now) = command_session("open brave");
        c.session.as_mut().unwrap().deadline = now + Duration::from_millis(1);
        c.dispatch_command(now);
        assert_eq!(c.deadline(), Some(now + Duration::from_secs(2)));
    }
}
