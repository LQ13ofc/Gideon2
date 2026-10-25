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
/// Owner name of Connection Manager proposals in the ledger (the Core, never a plugin).
const CONNECTION_OWNER: &str = "connections";

pub struct Core {
    base_pack: Option<crate::pack::Snapshot>,
    pub(crate) hub: Option<crate::hub::Snapshot>,
    configuration_status: crate::storage::ConfigurationStatus,
    configuration_recovery_available: bool,
    preferences: crate::storage::Config,
    /// Installed-language catalog (`languages.rs`); only `bundled` entries are selectable.
    languages: crate::languages::LanguageCatalog,
    /// Languages the running workers were started with (first configuration seen at boot).
    applied_languages: Option<crate::languages::Selection>,
    session: Option<Session>,
    next_session: u64,
    sequence: u64,
    events: VecDeque<Event>,
    recent_requests: VecDeque<String>,
    timeout: Duration,
    virtual_input: bool,
    wake_status: &'static str,
    capture_enabled: bool,
    /// WP-7b: end of the last frame the VAD flagged as speech (any state), for the wake grace window.
    last_speech_us: Option<u64>,
    completed_audio: Option<Capture>,
    capture_summary: Option<CaptureSummary>,
    stt_engine: Option<String>,
    stt_status: &'static str,
    /// Content-free reason of the last STT failure (`stt_last_error`); kept after a successful restart.
    stt_reason: Option<&'static str>,
    stt_requests: VecDeque<SttRequest>,
    transcript: Option<Transcript>,
    /// Wake phrase texts that open a command (one per active phrase). `None` = commands not configured.
    command_wake: Option<Vec<String>>,
    /// Wake phrase catalog: packaged defaults (from the pack) and the private custom store (src/phrases.rs).
    phrase_defaults: Vec<crate::phrases::Entry>,
    phrase_custom: crate::phrases::CustomFile,
    phrase_root: Option<std::path::PathBuf>,
    phrase_runtime: Option<crate::phrases::Runtime>,
    /// Synthetic test waiting for transport, and the state `wake_phrases.test` reports.
    phrase_job: Option<crate::phrases::TestJob>,
    phrase_test: Option<crate::phrases::TestView>,
    /// Outcome of the last validation or refused add (`phrase_check` in the response).
    phrase_check: Option<crate::phrases::Check>,
    command_job: Option<Job>,
    expected_command: Option<Job>,
    command_outcome: Option<Outcome>,
    /// Last host action (A11), content-free. Not persisted: a restart shows none.
    last_real_action: Option<crate::commands::LastAction>,
    tts_enabled: bool,
    speech_job: Option<crate::tts::Job>,
    speech_status: &'static str,
    speech_summary: Option<crate::tts::Summary>,
    speech_samples: usize,
    pub(crate) plugins: crate::plugins::PluginView,
    pub(crate) llm: crate::llmcfg::LlmState,
    pub(crate) tools: crate::tools::Ledger,
    /// Set by an accepted capability_invoke; cleared only when its matching result lands.
    tool_source: bool,
    /// C3 agent run (at most one); idle and inert unless a `*.chat` plugin runs.
    pub(crate) agent: crate::agent::Agent,
    /// S4 skill engine: ledgers, at most one run, idle until a skill is saved and enabled.
    pub(crate) skills: crate::skills::Engine,
    /// S5 Connection Manager: accounts, device logins and the single network slot.
    pub(crate) connections: crate::connections::Manager,
    /// S5 E3 CapabilityRegistry: the user's visual permission and the last result of each route.
    pub(crate) registry: crate::registry::Registry,
    /// Set by an accepted `core_restart`; `transport::serve` stops and the process exits 75.
    restart_requested: bool,
    /// A4: last `audio_devices` result (absent until the op runs).
    audio_devices: Option<crate::devices::Devices>,
    /// A5: `--live-audio` state (off unless the flag is set).
    live: crate::live::LiveState,
    /// A9: the last `audio_probe` (running or done); its queued job (id, device) and the id counter.
    audio_probe: Option<crate::live::ProbeView>,
    audio_probe_job: Option<(u64, String)>,
    audio_probe_seq: u64,
    /// A13: the microphone assistant. The view (`audio.recommendation`), the queued run (id, current
    /// preference), the id of the run in progress and the id counter.
    audio_recommend: crate::mic_assist::View,
    audio_recommend_job: Option<(u64, String)>,
    audio_recommend_running: Option<u64>,
    audio_recommend_seq: u64,
    /// CFG-04: unix ms of the last audit purge (`None` until the first one).
    history_purged_at: Option<u64>,
    /// WP-10a personal areas (memory, souls, habits, automations, conversations). `None` when the private
    /// store could not be opened; the snapshot then says `unavailable` and personal requests are refused.
    personal: Option<crate::personal::Personal>,
    /// Reply of the personal operation handled by the current request (taken into its response only).
    personal_result: Option<serde_json::Value>,
    /// N-5: one chat turn or agent goal sent during a voice session, run when the session ends.
    queued_chat: Option<QueuedChat>,
}

/// N-5: a chat request waiting for the voice session to end. Only one may wait; a second one is `busy`.
enum QueuedChat {
    Text {
        request_id: String,
        raw: String,
    },
    Agent {
        request_id: String,
        goal: String,
        capability: Option<String>,
    },
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
            languages: crate::languages::LanguageCatalog::builtin()
                .expect("catálogo de idiomas embutido válido"),
            applied_languages: None,
            session: None,
            next_session: 1,
            sequence: 0,
            events: VecDeque::new(),
            recent_requests: VecDeque::new(),
            timeout,
            virtual_input,
            wake_status: "unavailable",
            capture_enabled: false,
            last_speech_us: None,
            completed_audio: None,
            capture_summary: None,
            stt_engine: None,
            stt_status: "unavailable",
            stt_reason: None,
            stt_requests: VecDeque::new(),
            transcript: None,
            command_wake: None,
            phrase_defaults: Vec::new(),
            phrase_custom: Default::default(),
            phrase_root: None,
            phrase_runtime: None,
            phrase_job: None,
            phrase_test: None,
            phrase_check: None,
            command_job: None,
            expected_command: None,
            command_outcome: None,
            last_real_action: None,
            tts_enabled: false,
            speech_job: None,
            speech_status: "unavailable",
            speech_summary: None,
            speech_samples: 0,
            plugins: Default::default(),
            llm: Default::default(),
            tools: Default::default(),
            tool_source: false,
            agent: crate::agent::Agent::new(crate::agent::options()),
            skills: Default::default(),
            connections: Default::default(),
            registry: Default::default(),
            restart_requested: false,
            audio_devices: None,
            live: Default::default(),
            audio_probe: None,
            audio_probe_job: None,
            audio_probe_seq: 0,
            audio_recommend: crate::mic_assist::View::default(),
            audio_recommend_job: None,
            audio_recommend_running: None,
            audio_recommend_seq: 0,
            history_purged_at: None,
            personal: None,
            personal_result: None,
            queued_chat: None,
        }
    }
    /// A9: a wake phrase was recognised by the live input (feeds `audio.live.last_detection`).
    pub fn live_detected(&mut self, phrase_id: &str) {
        self.live.detected(phrase_id, Instant::now());
    }
    /// A9: the queued probe for the transport task to run (id, device). Taken once.
    pub fn take_audio_probe_job(&mut self) -> Option<(u64, String)> {
        self.audio_probe_job.take()
    }
    /// A9: the probe finished (or failed); the snapshot shows `done` with its numbers.
    pub fn audio_probe_reply(&mut self, id: u64, outcome: crate::live::ProbeOutcome) {
        if let Some(probe) = self.audio_probe.as_mut().filter(|p| p.id == id) {
            *probe = crate::live::ProbeView::finished(id, probe.device.clone(), &outcome);
        }
    }
    /// A13: the queued microphone assistant run for the transport task (id, current preference). Taken once.
    pub fn take_recommend_job(&mut self) -> Option<(u64, String)> {
        self.audio_recommend_job.take()
    }
    /// A13: the run finished. Stores its view and the device list it enumerated. A stale id is ignored.
    pub fn audio_recommend_reply(&mut self, id: u64, done: crate::mic_assist::Done) {
        if self.audio_recommend_running == Some(id) {
            self.audio_recommend_running = None;
            self.audio_devices = Some(done.devices);
            self.audio_recommend = done.view;
        }
    }
    /// A13: the run task ended without a result (it panicked or was cancelled).
    pub fn audio_recommend_failed(&mut self, id: u64) {
        if self.audio_recommend_running == Some(id) {
            self.audio_recommend_running = None;
            self.audio_recommend = crate::mic_assist::View::failed("audio_tool_failed");
        }
    }
    /// A4: lists the inputs once. `transport::serve` calls it at start when the live pipeline is on, so the
    /// device list is ready before the Dispositivos page opens (bounded by the enumeration budget).
    pub fn refresh_audio_devices(&mut self) {
        self.audio_devices = Some(crate::devices::enumerate());
    }
    /// A13 `audio_recommend_input`: refused during a voice session or while another probe or run is active.
    fn audio_recommend_start(&mut self, current: String) -> &'static str {
        let probing = self
            .audio_probe
            .as_ref()
            .is_some_and(|p| p.state == "running");
        if self.voice_active()
            || probing
            || self.audio_probe_job.is_some()
            || self.audio_recommend_running.is_some()
        {
            return "busy";
        }
        self.audio_recommend_seq += 1;
        let id = self.audio_recommend_seq;
        self.audio_recommend_running = Some(id);
        self.audio_recommend = crate::mic_assist::View::running();
        self.audio_recommend_job = Some((id, current));
        "ok"
    }
    /// A9 `audio_probe`: refused while a voice session runs or another probe is still recording. The
    /// device must be `default` or an input the last `audio_devices` listed.
    fn audio_probe_start(&mut self, device: String) -> &'static str {
        let running = self
            .audio_probe
            .as_ref()
            .is_some_and(|p| p.state == "running");
        if self.voice_active() || running || self.audio_probe_job.is_some() {
            return "busy";
        }
        let listed = self
            .audio_devices
            .as_ref()
            .is_some_and(|d| d.inputs.iter().any(|input| input.id == device));
        if !(device == "default" || (listed && crate::storage::valid_audio_device(&device))) {
            return "invalid_device";
        }
        self.audio_probe_seq += 1;
        let id = self.audio_probe_seq;
        self.audio_probe = Some(crate::live::ProbeView::running(id, device.clone()));
        self.audio_probe_job = Some((id, device));
        "ok"
    }
    /// A5/A6: called once by `transport::serve`. `enabled` is the pipeline switch of this process (flag or
    /// ledger); `from_preference` is true when the ledger alone turned it on.
    pub(crate) fn configure_live(&mut self, enabled: bool, from_preference: bool) {
        self.live.configure(enabled, from_preference);
    }
    /// A5: status from the live input or output supervisors.
    pub fn live_event(&mut self, event: crate::live::LiveEvent) {
        self.live.apply(event);
    }
    pub fn set_boot_seed(&mut self, seed: u64) {
        self.next_session = seed;
        self.tools.set_epoch(seed);
        self.agent.set_boot_seed(seed);
        self.skills.set_boot_seed(seed);
    }
    /// True while a voice session holds the Core (agent actions and wake sessions exclude each other).
    pub(crate) fn voice_active(&self) -> bool {
        self.session.is_some()
    }
    /// True once an accepted `core_restart` asked the serve loop to stop with `RESTART_EXIT_CODE`.
    pub(crate) fn restart_requested(&self) -> bool {
        self.restart_requested
    }
    /// `core_restart` is refused while any of these owns the Core: a voice session, an agent run,
    /// a skill run, or a plugin capability invocation. Each would be cut off by the exit.
    fn restart_busy(&self) -> bool {
        self.session.is_some()
            || self.agent.is_active()
            || self.skills.is_active()
            || self.plugins.invoking()
    }
    /// Enables the tool executor (same sandbox as Base commands) and sets the proposal TTL.
    pub fn configure_tools(&mut self, ttl: Duration, executor: bool) {
        self.tools.configure(ttl, executor);
    }
    /// Earliest wake-up for proposal expiry or the agent run deadline.
    pub fn tool_deadline(&self) -> Option<Instant> {
        [
            self.tools.deadline(),
            self.agent.deadline(),
            self.skills.deadline(),
            self.connections.deadline(),
        ]
        .into_iter()
        .flatten()
        .min()
    }
    pub fn expire_tools(&mut self, now: Instant) {
        self.tools.expire(now);
        self.agent_expire(now);
        self.skill_expire(now);
    }
    pub fn take_tool_job(&mut self) -> Option<crate::commands::Job> {
        self.tools.start()
    }
    /// Executor result for the single running tool job; a stale or mismatched job is ignored.
    pub fn tool_reply(&mut self, job: Job, receipt: Option<Receipt>, now: Instant) {
        self.expire_tools(now);
        let Some(id) = self.tools.finish(&job) else {
            return;
        };
        let receipt = receipt.filter(|r| commands::verify(&job, r));
        self.record_host(&job, None, receipt.as_ref());
        match receipt {
            Some(receipt) => {
                self.tools.set(
                    &id,
                    crate::tools::State::Executed,
                    None,
                    Some(receipt.result),
                );
                self.emit(String::new(), None, "tool_executed");
            }
            None => self.tool_failed(String::new(), &id, "executor_failed"),
        }
        self.agent_settle(&id, None);
        self.skill_tool_settled(&id);
    }
    pub(crate) fn tool_denied(&mut self, request_id: String, id: &str, code: &'static str) {
        self.tools
            .set(id, crate::tools::State::Denied, Some(code), None);
        self.emit(request_id, None, "tool_denied");
    }
    fn tool_failed(&mut self, request_id: String, id: &str, code: &'static str) {
        self.tools
            .set(id, crate::tools::State::Failed, Some(code), None);
        self.emit(request_id, None, "tool_failed");
    }
    /// Converts one accepted plugin result into proposals. Malformed or extra items are bounded.
    fn propose_tool(
        &mut self,
        plugin_id: &str,
        call_id: String,
        tool: String,
        args: serde_json::Value,
        shape_ok: bool,
        now: Instant,
    ) {
        let id = self
            .tools
            .propose(plugin_id, call_id, tool.clone(), args.clone(), now);
        self.emit(String::new(), None, "tool_proposed");
        let verdict = if shape_ok {
            crate::tools::command(&tool, &args)
        } else {
            Err("invalid_args")
        };
        let verdict = match verdict {
            Ok(_) if !self.tools.enabled() => Err("executor_unavailable"),
            other => other,
        };
        match verdict {
            Err(code) => self.tool_denied(String::new(), &id, code),
            Ok((command, risk)) => {
                // Read-only runs at once unless a voice session is active; state changes wait.
                if risk == crate::tools::Risk::ReadOnly && self.session.is_none() {
                    if self.tools.queue(&id, command) {
                        self.emit(String::new(), None, "tool_authorized");
                    } else {
                        self.tool_failed(String::new(), &id, "busy");
                    }
                }
            }
        }
    }
    fn ingest_result(&mut self, plugin_id: &str, now: Instant) {
        if !self.tool_source {
            return;
        }
        // The plugin view clears `last` at invoke and sets it only for the matching result.
        let Some(result) = self.plugins.last().cloned() else {
            return;
        };
        self.tool_source = false;
        if result.plugin_id != plugin_id || !result.ok {
            return;
        }
        let Some(calls) = result
            .output
            .as_ref()
            .and_then(|o| o.get("tool_calls"))
            .and_then(|c| c.as_array())
        else {
            return;
        };
        for item in calls.iter().take(crate::tools::MAX_CALLS) {
            let (call_id, tool, args, shape_ok) = crate::tools::read_call(item);
            self.propose_tool(plugin_id, call_id, tool, args, shape_ok, now);
        }
    }
    /// Revoked, disabled or failed plugins lose their pending proposals.
    fn sweep_tools(&mut self) {
        self.agent_guard();
        self.skill_guard();
        if !self.tools.has_pending() {
            return;
        }
        let running: std::collections::HashSet<String> = self
            .plugins
            .snapshot(self.hub.as_ref())
            .items
            .iter()
            .filter(|i| i.enabled && i.state == "running")
            .map(|i| i.plugin_id.clone())
            .collect();
        self.tools.cancel_unavailable(&running);
        self.agent_settle_awaited();
    }
    fn tool_decide(
        &mut self,
        request_id: String,
        proposal_id: &str,
        decision: ToolDecision,
    ) -> &'static str {
        use crate::tools::State;
        let Some(view) = self.tools.view(proposal_id).cloned() else {
            return "unknown_proposal";
        };
        if view.kind == Some("connection") && view.state == State::Pending {
            if decision == ToolDecision::Deny {
                self.tools
                    .set(proposal_id, State::Denied, Some("user_denied"), None);
                self.emit(request_id, None, "tool_denied");
                self.agent_settle(proposal_id, None);
                return "ok";
            }
            if self.tools.busy() {
                return "busy";
            }
            return self.connection_authorize(request_id, proposal_id, &view);
        }
        match view.state {
            State::Pending => {}
            State::Expired => return "proposal_expired",
            State::Cancelled => return "unknown_proposal",
            State::Denied if decision == ToolDecision::Authorize => return "proposal_denied",
            _ => return "already_decided",
        }
        match decision {
            ToolDecision::Deny => {
                self.tools
                    .set(proposal_id, State::Denied, Some("user_denied"), None);
                self.emit(request_id, None, "tool_denied");
                self.agent_settle(proposal_id, None);
                "ok"
            }
            ToolDecision::Authorize => {
                if self.tools.busy() {
                    return "busy";
                }
                if self.agent_owns(&view) {
                    return self.agent_authorize(request_id, proposal_id, &view);
                }
                // Arguments are validated again at authorize time, not only at proposal time.
                match crate::tools::command(&view.tool, &view.args) {
                    Ok((command, _)) => {
                        if self.tools.queue(proposal_id, command) {
                            self.emit(request_id, None, "tool_authorized");
                        } else {
                            return "busy";
                        }
                    }
                    Err(code) => self.tool_denied(request_id, proposal_id, code),
                }
                "ok"
            }
        }
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
        if speech == Some(true) {
            self.last_speech_us = Some(frame.end_us());
        }
        if !self.capture_enabled {
            if detected {
                self.audio_wake(now);
            }
            return;
        }
        self.expire(now);
        // No count limit here: the transport owns the STT queue (merging and a bounded backlog, src/stt.rs).
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
                let grace = self.last_speech_us;
                match Capture::new(pre_roll, frame.end_us()).map(|c| c.speech_before_wake(grace)) {
                    Ok(c) => {
                        if self.stt_status == "ready" {
                            // audio_wake starts no session while a restart is pending (configuration not Ready, for
                            // example after a wake phrase or sensitivity change): drop the detection, never panic.
                            let Some(sid) = self.session.as_ref().map(|s| s.id) else {
                                return;
                            };
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
        self.stt_reason = None;
    }
    pub fn take_stt_requests(&mut self) -> VecDeque<SttRequest> {
        std::mem::take(&mut self.stt_requests)
    }
    /// Permanent STT failure (no restart left): status `failed` until the Core restarts.
    pub fn stt_failed(&mut self) {
        self.stt_status = "failed";
        self.transcript = None;
        self.finish("stt_failed");
    }
    /// Permanent failure with its content-free reason.
    pub fn stt_failed_with(&mut self, reason: &'static str) {
        self.stt_reason = Some(reason);
        self.stt_failed();
    }
    /// A worker failed and a restart is scheduled: the session ends, the transcript is revoked, and the status
    /// reads `starting` until the new worker reports ready (detections meanwhile end as `stt_unavailable`).
    pub fn stt_restarting(&mut self, reason: &'static str) {
        self.stt_reason = Some(reason);
        self.stt_status = "starting";
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
        self.command_wake = Some(vec![wake_text]);
    }
    pub fn configure_command_wakes(&mut self, wake_texts: Vec<String>) {
        self.command_wake = Some(wake_texts);
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
        // WP-10a: a habit's trigger phrase runs that habit (its own Skill, pinned version and every engine check)
        // before the command grammar is tried. The session ends with the run's answer.
        let raw = transcript.raw.clone();
        if let Some(habit_id) = self
            .personal
            .as_ref()
            .and_then(|p| p.habits.id_for_phrase(&raw))
        {
            let code = self.run_habit(&habit_id);
            let kind = if code == "ok" {
                "command_success"
            } else {
                "command_failed"
            };
            self.command_outcome = Some(Outcome {
                session_id: id,
                code: kind,
                receipt: None,
            });
            self.command_terminal(kind, now);
            return;
        }
        // Any active wake phrase may open a command; the first grammar match wins.
        let parsed = match self.command_wake.as_deref() {
            Some(wakes) if !wakes.is_empty() => wakes
                .iter()
                .find_map(|wake| commands::parse(&transcript.raw, wake)),
            _ => commands::parse(&transcript.raw, ""),
        };
        // A11: real-only steps (unmute, volume up/down) exist only while host actions are consented; otherwise
        // they are not understood, exactly like any other unrecognized phrase.
        let real = self.preferences.real_actions;
        let parsed = parsed.filter(|command| real || !command.real_only());
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
        let allowed = if real {
            commands::authorize_host(&command)
        } else {
            commands::authorize(&command)
        };
        if let Err(code) = allowed {
            self.command_outcome = Some(Outcome {
                session_id: id,
                code,
                receipt: None,
            });
            self.command_terminal("command_denied", now);
            return;
        }
        // A host launch waits up to 5 s for the launcher and 5 s for the process; the sandbox keeps 2 s.
        let budget = if real && command.host_action() {
            Duration::from_secs(12)
        } else {
            Duration::from_secs(2)
        };
        let s = self.session.as_mut().expect("live final session");
        s.stage = State::Executing;
        s.deadline = s.overall_deadline.min(now + budget);
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
        self.record_host(&job, Some(job.session_id), receipt.as_ref());
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
    /// Failure of the session's own job with a fixed code (A11 host codes such as `app_not_installed`).
    /// The event stays `command_failed`; the outcome code tells the user why.
    pub fn command_error(&mut self, job: Job, code: &'static str, now: Instant) {
        self.expire(now);
        if !self.command_is_active(job.session_id) || self.expected_command.as_ref() != Some(&job) {
            return;
        }
        self.record_host(&job, Some(job.session_id), None);
        self.command_outcome = Some(Outcome {
            session_id: job.session_id,
            code,
            receipt: None,
        });
        self.command_terminal("command_failed", now);
    }
    /// Keeps the last host action of the real-actions mode and emits its content-free audit event (A11).
    /// Sandbox jobs and the time of day are not host actions and record nothing.
    fn record_host(&mut self, job: &Job, session: Option<u64>, receipt: Option<&Receipt>) {
        if !self.preferences.real_actions || !job.command.host_action() {
            return;
        }
        let ok = receipt.is_some();
        let app = match &job.command {
            Command::OpenApp { desktop_id } => Some(commands::app_label(desktop_id)),
            _ => None,
        };
        self.last_real_action = Some(crate::commands::LastAction {
            kind: job.command.kind(),
            app,
            ok,
            verified: receipt.is_some_and(|r| r.verified),
            at_ms: crate::protocol::unix_ms(),
        });
        self.emit_with(
            String::new(),
            session,
            "host_action",
            if ok { "ok" } else { "failed" },
        );
    }
    /// Whether the fixed table runs on the host now (`preferences.real_actions`).
    pub fn real_actions(&self) -> bool {
        self.preferences.real_actions
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
        self.expire_tools(now);
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
        self.run_queued_chat(now);
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
    pub(crate) fn emit(&mut self, request_id: String, session_id: Option<u64>, kind: &'static str) {
        let outcome = crate::protocol::outcome_of(kind);
        self.emit_with(request_id, session_id, kind, outcome);
    }
    /// Event with an explicit outcome (closed vocabulary, see `protocol::outcome_of`).
    pub(crate) fn emit_with(
        &mut self,
        request_id: String,
        session_id: Option<u64>,
        kind: &'static str,
        outcome: &'static str,
    ) {
        self.sequence += 1;
        // CFG-04: `never` keeps no timeline; `days_*` drop events older than the window before adding one.
        if self.preferences.history_retention == crate::storage::HistoryRetention::Never {
            self.events.clear();
            return;
        }
        self.prune_events(crate::protocol::unix_ms());
        if self.events.len() == 64 {
            self.events.pop_front();
        }
        // Wall clock may step back; the ring keeps timestamps non-decreasing.
        let previous = self.events.back().map_or(0, |e| e.at_ms);
        self.events.push_back(Event {
            sequence: self.sequence,
            at_ms: crate::protocol::unix_ms().max(previous),
            request_id,
            session_id,
            kind,
            origin: crate::protocol::origin_of(kind),
            outcome,
        });
    }
    /// CFG-04: drops timeline events outside the retention window (all of them for `never`).
    pub(crate) fn prune_events(&mut self, now: u64) {
        let Some(window) = self.preferences.history_retention.window_ms() else {
            self.events.clear();
            return;
        };
        let cutoff = now.saturating_sub(window);
        while self.events.front().is_some_and(|e| e.at_ms < cutoff) {
            self.events.pop_front();
        }
    }
    /// CFG-04: runs the persisted-audit purge at most once a minute while requests arrive.
    pub(crate) fn purge_history_due(&mut self, storage: &crate::storage::Storage, now: u64) {
        const EVERY_MS: u64 = 60_000;
        if self
            .history_purged_at
            .is_some_and(|last| now.saturating_sub(last) < EVERY_MS)
        {
            return;
        }
        self.purge_history_now(storage, now);
    }
    /// CFG-04: purge now (boot and every preference commit). Best effort: a failure is retried at the next due
    /// time and never reaches the client.
    fn purge_history_now(&mut self, storage: &crate::storage::Storage, now: u64) {
        self.history_purged_at = Some(now);
        let _ = storage.purge_history(now);
        // WP15 / CFG-04: the skill run ledger follows the same retention preference.
        let days = match self.preferences.history_retention {
            crate::storage::HistoryRetention::Days7 => Some(7),
            crate::storage::HistoryRetention::Days30 => Some(30),
            crate::storage::HistoryRetention::Days90 => Some(90),
            crate::storage::HistoryRetention::Never => None,
        };
        self.skills.purge_runs(days, now);
        // WP-10a: the personal areas follow the same window; under `never` stored history is erased now.
        let retention = self.preferences.history_retention.window_ms();
        if let Some(personal) = self.personal.as_mut() {
            let _ = personal.purge_now(now, retention);
        }
    }
    /// WP-10a: one versioned personal request. The reply is served in `personal_reply` of this response.
    fn personal_op(&mut self, area: &str, payload: serde_json::Value) -> &'static str {
        let now = crate::protocol::unix_ms();
        let retention = self.preferences.history_retention.window_ms();
        let Some(mut personal) = self.personal.take() else {
            return "personal_unavailable";
        };
        // The Core is the skill engine of Habits and Automations; the store is taken out while it runs.
        let result = personal.apply(area, payload, now, retention, self);
        self.personal = Some(personal);
        match result {
            // One IPC reply carries at most 64 KiB, and the bridge drops the Core on a longer line. Replies stay
            // well under that; a bigger one (a long conversation) is refused and the user is told to export it.
            Ok(reply) => {
                const REPLY_MAX: usize = 32 * 1024;
                let fits = serde_json::to_vec(&reply).is_ok_and(|b| b.len() <= REPLY_MAX);
                if !fits {
                    return "reply_too_large";
                }
                self.personal_result = Some(serde_json::json!({"area": area, "reply": reply}));
                "ok"
            }
            Err(code) => code,
        }
    }
    /// WP-10a: runs one habit through its personal area; the Skill engine checks grants, pin and busy state.
    fn run_habit(&mut self, habit_id: &str) -> &'static str {
        let now = crate::protocol::unix_ms();
        let retention = self.preferences.history_retention.window_ms();
        let Some(mut personal) = self.personal.take() else {
            return "personal_unavailable";
        };
        let request = serde_json::json!({"version": 1, "op": "run", "id": habit_id});
        let result = personal.apply("habits", request, now, retention, self);
        self.personal = Some(personal);
        match result {
            Ok(_) => "ok",
            Err(code) => code,
        }
    }
    /// WP-10a: everything stored goes to one private file (0600, in `<personal>/exports`), because a full export
    /// can be far larger than one IPC reply. The reply names the file and its size (`personal_reply.reply`).
    fn personal_export(&mut self) -> &'static str {
        let now = crate::protocol::unix_ms();
        let retention = self.preferences.history_retention.window_ms();
        let Some(personal) = self.personal.as_ref() else {
            return "personal_unavailable";
        };
        let document = personal.export_all(now, retention);
        let exports = personal.dir().join("exports");
        let Ok(bytes) = serde_json::to_vec_pretty(&document) else {
            return "personal_export_failed";
        };
        let path = exports.join(format!("personal-export-{now}.json"));
        let written = crate::personal::private_dir(&exports)
            .and_then(|()| crate::personal::write_private_atomic(&path, &bytes));
        match written {
            Ok(()) => {
                self.personal_result = Some(serde_json::json!({
                    "area": "export",
                    "reply": {"path": path.to_string_lossy(), "bytes": bytes.len()},
                }));
                "ok"
            }
            Err(_) => "personal_export_failed",
        }
    }
    /// WP-10a: erases every personal area. Refused unless `confirm` is true.
    fn personal_erase_all(&mut self, request_id: &str, confirm: bool) -> &'static str {
        if !confirm {
            return "confirmation_required";
        }
        let Some(personal) = self.personal.as_mut() else {
            return "personal_unavailable";
        };
        match personal.erase_all() {
            Ok(()) => {
                self.emit(request_id.to_string(), None, "personal_erased");
                "ok"
            }
            Err(code) => code,
        }
    }
    /// HUD-03: the client (Ctrl+M) asks for a listening session. It is the same session a wake opens, and it
    /// needs the live microphone on (consent stored in preferences) and a running capture; each missing piece
    /// has its own refusal code.
    fn listen_start(&mut self, request_id: String, now: Instant) -> &'static str {
        if !self.preferences.live_audio {
            return "live_audio_disabled";
        }
        if !self.capture_enabled {
            return "capture_unavailable";
        }
        if self.configuration_status != crate::storage::ConfigurationStatus::Ready {
            return "configuration_not_ready";
        }
        if self.session.is_some() || self.voice_active() {
            return "busy";
        }
        if self.stt_status != "ready" {
            return "stt_unavailable";
        }
        self.start_session(request_id, now);
        "ok"
    }
    /// N-5: one typed turn: a transcript from text, then the command path. Shared by a direct request and by
    /// the queue that runs after a voice session.
    fn text_turn(&mut self, request_id: String, raw: String, now: Instant) -> &'static str {
        self.start_session(request_id.clone(), now);
        let Some(session_id) = self.session.as_mut().map(|s| {
            s.stage = State::Transcribing;
            s.id
        }) else {
            return "busy";
        };
        self.transcript = Some(Transcript {
            source: "user_text",
            session_id,
            revision: 1,
            audio_end_us: 0,
            normalized: raw.split_whitespace().collect::<Vec<_>>().join(" "),
            raw,
            is_final: true,
            confidence: None,
        });
        self.emit(request_id, Some(session_id), "transcript_final");
        self.dispatch_command(now);
        "ok"
    }
    /// WP-10a timer: starts the automations that are due (one engine request per due automation). Each attempt is
    /// one content-free event: `automation_started` when the engine accepted it, `automation_failed` otherwise.
    pub fn personal_tick(&mut self) {
        let now = crate::protocol::unix_ms();
        let retention = self.preferences.history_retention.window_ms();
        let Some(mut personal) = self.personal.take() else {
            return;
        };
        let attempts = personal.tick(now, retention, self);
        self.personal = Some(personal);
        for attempt in attempts {
            let accepted = attempt.get("code").and_then(|c| c.as_str()) == Some("ok");
            let kind = if accepted {
                "automation_started"
            } else {
                "automation_failed"
            };
            self.emit(String::new(), None, kind);
        }
    }
    /// N-5: a chat turn or agent goal sent during a voice session waits here (one slot; a second one is `busy`).
    fn queue_chat(&mut self, chat: QueuedChat) -> &'static str {
        if let QueuedChat::Agent { goal, .. } = &chat {
            if goal.is_empty()
                // Same bound as `agent::GOAL_MAX` (private there).
                || goal.len() > 1024
                || goal.chars().any(char::is_control)
            {
                return "invalid_input";
            }
        }
        if self.queued_chat.is_some() {
            return "busy";
        }
        self.queued_chat = Some(chat);
        "queued"
    }
    /// N-5: runs the waiting chat once no voice session is active. A refusal is reported as `chat_failed`.
    fn run_queued_chat(&mut self, now: Instant) {
        if self.session.is_some() || self.voice_active() {
            return;
        }
        let (request_id, code) = match self.queued_chat.take() {
            None => return,
            Some(QueuedChat::Text { request_id, raw }) => {
                let code = self.text_turn(request_id.clone(), raw, now);
                (request_id, code)
            }
            Some(QueuedChat::Agent {
                request_id,
                goal,
                capability,
            }) => {
                let code = self.agent_start(request_id.clone(), &goal, capability, now);
                (request_id, code)
            }
        };
        if code != "ok" {
            self.emit(request_id, None, "chat_failed");
        }
    }

    pub fn response(&self, request_id: String, code: &'static str) -> Response {
        Response {
            base_pack: self.base_pack.clone(),
            hub: self.hub.clone().map(|hub| self.plugins.annotate(hub)),
            plugins: self.plugins.snapshot(self.hub.as_ref()),
            capability_result: self.plugins.last().cloned(),
            partial: self.plugins.partial(),
            llm: self.llm.snapshot(),
            configuration_status: self.configuration_status,
            configuration_recovery_available: self.configuration_recovery_available,
            preferences: self.preferences.clone(),
            actions: crate::commands::ActionsView {
                real: crate::commands::RealView {
                    enabled: self.preferences.real_actions,
                    last_action: self.last_real_action.clone(),
                },
            },
            languages: crate::languages::view(
                &self.languages,
                &self.preferences,
                self.applied_languages.as_ref(),
            ),
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
            stt_last_error: self.stt_reason,
            transcript: self.transcript.clone(),
            capture: self.capture_summary.clone(),
            wake_status: self.wake_status,
            audio: crate::live::AudioView {
                devices: self.audio_devices.clone(),
                live: self.live.view(self.preferences.live_audio, Instant::now()),
                probe: self.audio_probe.clone(),
                recommendation: self.audio_recommend.clone(),
            },
            wake_phrases: crate::phrases::View::build(
                &self.phrase_defaults,
                &self.phrase_custom,
                &self.phrase_settings(),
                self.phrase_lexicon().is_some(),
                self.phrase_test.clone(),
            ),
            phrase_check: self.phrase_check.clone(),
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
            tool_proposals: self.tools.snapshot(),
            agent: self.agent.view(),
            skills: self.skills_view(),
            connections: self.connections.view(),
            registry: self.registry_view(),
            personal: match self.personal.as_ref() {
                Some(p) => p.snapshot(
                    crate::protocol::unix_ms(),
                    self.preferences.history_retention.window_ms(),
                ),
                None => serde_json::json!({"status": "unavailable"}),
            },
            personal_reply: None,
        }
    }
    /// CFG-07: the engines of the stored selection are running now (after a hot swap between sessions).
    pub fn languages_applied(&mut self, selection: crate::languages::Selection) {
        self.applied_languages = Some(selection);
    }
    pub fn configure_preferences(&mut self, config: &crate::storage::Config) {
        // The first configuration is what the workers start with; later commits only change the stored choice.
        if self.applied_languages.is_none() {
            self.applied_languages = Some(crate::languages::Selection::from_config(config));
        }
        self.preferences = config.clone();
        self.prune_events(crate::protocol::unix_ms());
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
        if let crate::plugins::Ev::Service {
            plugin_id,
            service,
            args,
            reply,
        } = ev
        {
            // Skill services answer the waiting host at once; a dropped waiter is not an error.
            let _ = reply.send(self.skill_service(&plugin_id, &service, args));
            self.flush_plugin_events("");
            return;
        }
        let result_of = match &ev {
            crate::plugins::Ev::Result { plugin_id, .. } => Some(plugin_id.clone()),
            _ => None,
        };
        self.plugins.event(ev, now);
        // A `*.chat` result that reports `used_fallback` is noted (a bool and a time, never content).
        if let Some(used_fallback) = self.plugins.take_chat_note() {
            self.llm
                .note_chat(used_fallback, crate::protocol::unix_ms());
        }
        if let Some(plugin_id) = result_of {
            self.ingest_result(&plugin_id, now);
            self.agent_on_result();
            self.skill_on_result();
        }
        self.sweep_tools();
        self.flush_plugin_events("");
    }
    /// Loads the C1 ledgers (LLM config and vault presence); `allow_loopback` is test-only.
    pub fn configure_llm(&mut self, storage: &crate::storage::Storage, allow_loopback: bool) {
        self.llm = crate::llmcfg::LlmState::load(storage, allow_loopback);
    }
    /// Loads the S4 skill ledgers from the private root; a damaged ledger quarantines skills only.
    pub fn configure_skills(&mut self, storage: &crate::storage::Storage) {
        self.skills.configure(&storage.root);
    }
    /// Loads `connections.json`; a damaged ledger disables account writes, nothing else.
    pub fn configure_connections(&mut self, storage: &crate::storage::Storage) {
        self.connections.configure(storage);
    }
    /// Loads `registry.json`; a damaged file keeps the visual fallback off.
    pub fn configure_registry(&mut self, storage: &crate::storage::Storage) {
        self.registry.configure(storage);
    }
    /// Next network job for the single slot; transport runs it and returns the reply.
    pub fn take_connection_job(&mut self) -> Option<(u64, crate::connections::Job)> {
        let job = self.connections.take_job(&self.llm);
        // Refreshes that were skipped at start may have failed their proposals: flush them now.
        let settled = self.connections.take_settled();
        self.connection_flush(settled);
        job
    }
    /// Settles a finished network job: tokens, statuses, and the proposal it was serving.
    pub fn connection_reply(
        &mut self,
        storage: &crate::storage::Storage,
        done: crate::connections::Done,
        now: Instant,
    ) {
        let first = self.connections.settle(storage, &mut self.llm, done, now);
        let mut settled: Vec<crate::connections::Settled> = first.into_iter().collect();
        settled.extend(self.connections.take_settled());
        self.connection_flush(settled);
    }
    /// Timer step of the Connection Manager: expiries and due device polls.
    pub fn connections_tick(&mut self, storage: &crate::storage::Storage, now: Instant) {
        self.connections.tick(storage, now);
        let settled = self.connections.take_settled();
        self.connection_flush(settled);
    }
    /// Transport reports a connection task that ended without a reply.
    pub fn connection_abandoned(&mut self, id: u64) {
        self.connections.abandon(id);
        let settled = self.connections.take_settled();
        self.connection_flush(settled);
    }
    /// Audit records of connection work since the last drain (closed vocabulary only).
    pub fn take_connection_audit(&mut self) -> Vec<crate::connections::Audit> {
        self.connections.take_audit()
    }
    fn connection_flush(&mut self, settled: Vec<crate::connections::Settled>) {
        for (kind, outcome) in self.connections.take_events() {
            self.emit_with(String::new(), None, kind, outcome);
        }
        for outcome in settled {
            let kind = if outcome.state == crate::tools::State::Executed {
                "tool_executed"
            } else {
                "tool_failed"
            };
            self.registry.settled(
                &outcome.proposal,
                outcome.state == crate::tools::State::Executed,
            );
            self.tools.set(
                &outcome.proposal,
                outcome.state,
                outcome.reason,
                outcome.result,
            );
            self.emit(String::new(), None, kind);
            self.agent_settle(&outcome.proposal, None);
            self.skill_tool_settled(&outcome.proposal);
        }
    }
    /// Runs one connection operation with the storage it needs, then flushes its events.
    fn connection_op(
        &mut self,
        storage: Option<&crate::storage::Storage>,
        op: impl FnOnce(
            &mut crate::connections::Manager,
            &mut crate::llmcfg::LlmState,
            &crate::storage::Storage,
        ) -> &'static str,
    ) -> &'static str {
        let Some(storage) = storage else {
            return "connections_unavailable";
        };
        let code = op(&mut self.connections, &mut self.llm, storage);
        let settled = self.connections.take_settled();
        self.connection_flush(settled);
        code
    }
    /// Operation call from the UI or a test: reads run now; writes and public calls wait for the
    /// user's approval card in the proposal ledger (kind `connection`).
    fn connection_call(
        &mut self,
        request_id: String,
        id: &str,
        operation: &str,
        args: &serde_json::Value,
        revision: Option<u64>,
        now: Instant,
    ) -> &'static str {
        use crate::connections::Access;
        if let Err(code) = self.connections.check_revision(revision) {
            return code;
        }
        let (provider, op) = match self.connections.op_for(id, operation) {
            Ok(found) => found,
            Err(code) => return code,
        };
        let plan = match self.connections.plan(provider, op, Some(id), args) {
            Ok(plan) => plan,
            Err(code) => return code,
        };
        if plan.risk == Access::Read {
            return match self.connections.start(&self.llm, plan, None, now) {
                Ok(()) => "ok",
                Err(code) => code,
            };
        }
        let name = crate::connections::call_name(provider, op);
        let proposal = self
            .tools
            .propose(CONNECTION_OWNER, String::new(), name, plan.wrap(), now);
        self.tools
            .set_connection(&proposal, id, op.name, plan.risk.name());
        self.connections.pending_approval(op.name, proposal.clone());
        self.emit(request_id, None, "tool_proposed");
        "pending_approval"
    }
    /// Authorize of a connection proposal (user card, agent, or the same flow for both).
    /// A refusal that the user can retry (`busy`, `public_disabled`, `rate_limited`) keeps the
    /// proposal pending; anything else denies it.
    fn connection_authorize(
        &mut self,
        request_id: String,
        proposal_id: &str,
        view: &crate::tools::View,
    ) -> &'static str {
        let owned = self.agent_owns(view);
        // The agent never runs a destructive or public action without the switch: same answer as for every
        // other registry tool, whether or not the run still waits for this proposal.
        if owned
            && matches!(view.risk, Some("destructive" | "public"))
            && !crate::agent::options().allow_destructive
        {
            return "destructive_disabled";
        }
        if owned && !self.agent_awaits(proposal_id) {
            return "unknown_proposal";
        }
        if self.session.is_some() {
            return "busy";
        }
        let plan = match self.connections.plan_proposal(&view.args) {
            Ok(plan) => plan,
            Err(code) => {
                self.tool_denied(request_id, proposal_id, code);
                if owned {
                    self.agent_settle(proposal_id, None);
                }
                return "ok";
            }
        };
        let destructive = plan.tool_risk() == crate::tools::Risk::Destructive;
        if owned && destructive && !crate::agent::options().allow_destructive {
            return "destructive_disabled";
        }
        match self.connections.start(
            &self.llm,
            plan,
            Some(proposal_id.to_owned()),
            Instant::now(),
        ) {
            Ok(()) => {
                self.tools
                    .set(proposal_id, crate::tools::State::Authorized, None, None);
                self.emit(request_id, None, "tool_authorized");
                "ok"
            }
            Err(code @ ("public_disabled" | "busy" | "rate_limited")) => code,
            Err(code) => {
                self.tool_denied(request_id, proposal_id, code);
                if owned {
                    self.agent_settle(proposal_id, None);
                }
                "ok"
            }
        }
    }
    /// Validated plan of a fixed agent tool name (`github_*`), for the current account rules.
    pub(crate) fn connections_plan(
        &self,
        name: &str,
        args: &serde_json::Value,
    ) -> Result<crate::connections::Plan, &'static str> {
        let tool = crate::connections::agent_tool(name).ok_or("unknown_tool")?;
        let provider = crate::connections::provider_by_id(tool.provider).ok_or("unknown_tool")?;
        let op = crate::connections::operation(provider, tool.operation).ok_or("unknown_tool")?;
        // Model tool calls are flat objects: `mcp_call {"tool": name, <the tool's own scalar arguments>}`.
        let nested;
        let args = if tool.name == "mcp_call" {
            nested = crate::connections::mcp_nest(args)?;
            &nested
        } else {
            args
        };
        self.connections.plan(provider, op, None, args)
    }
    /// Starts a plan that a proposal (agent or skill) is waiting for.
    pub(crate) fn connections_start(
        &mut self,
        plan: crate::connections::Plan,
        proposal: String,
    ) -> Result<(), &'static str> {
        self.connections
            .start(&self.llm, plan, Some(proposal), Instant::now())
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
        self.phrase_defaults = crate::phrases::defaults(&pack.wake_phrases);
        self.base_pack = Some(pack);
    }
    pub fn configure_storage(&mut self, storage: &crate::storage::Storage) {
        self.configure_preferences(&storage.config);
        self.configuration_status = storage.configuration_status;
        self.configuration_recovery_available = storage.recovery_available();
        // WP-10a: the personal store lives under the same data root; a corrupt ledger leaves it unavailable.
        self.personal = crate::personal::Personal::open(&storage.root.join("personal")).ok();
        self.purge_history_now(storage, crate::protocol::unix_ms());
        self.phrase_root = Some(storage.root.clone());
        // An unreadable custom store is empty for the views; add, remove and test re-read it and refuse.
        self.phrase_custom = crate::phrases::read_custom(&storage.root).unwrap_or_default();
    }
    /// Runtime of the wake phrase setup (worker interpreter, lexicon, TTS). Set once by transport.
    pub fn configure_phrases(&mut self, runtime: crate::phrases::Runtime) {
        self.phrase_runtime = Some(runtime);
    }
    pub fn take_phrase_job(&mut self) -> Option<crate::phrases::TestJob> {
        self.phrase_job.take()
    }
    /// Closes the synthetic test: `ok` when a measurement was stored, otherwise `failed`.
    pub fn phrase_test_finished(&mut self, id: &str, ok: bool) {
        if let Some(test) = self.phrase_test.as_mut().filter(|t| t.id == id) {
            test.state = if ok { "done" } else { "failed" };
            test.code = (!ok).then_some(crate::phrases::code::TEST_FAILED);
        }
        self.emit(
            String::new(),
            None,
            if ok {
                "phrase_tested"
            } else {
                "phrase_test_failed"
            },
        );
    }
    fn phrase_lexicon(&self) -> Option<&crate::phrases::Lexicon> {
        self.phrase_runtime
            .as_ref()
            .and_then(|r| r.lexicon.as_deref())
    }
    fn phrase_entries(&self) -> Vec<crate::phrases::Entry> {
        crate::phrases::entries(&self.phrase_defaults, &self.phrase_custom)
    }
    /// The stored list, migrated from the legacy single phrase when the list is still empty.
    fn phrase_settings(&self) -> Vec<crate::phrases::Setting> {
        let default = self
            .base_pack
            .as_ref()
            .map_or("hey_gideon", |p| p.default_phrase.as_str());
        crate::phrases::migrated(
            &self.preferences.wake_phrases,
            self.preferences.wake_phrase.as_deref(),
            default,
        )
    }
    fn select_wake_phrases(
        &mut self,
        request_id: &str,
        revision: u64,
        phrases: Vec<crate::phrases::Setting>,
        acknowledge_untested: bool,
        storage: Option<&mut crate::storage::Storage>,
    ) -> &'static str {
        use crate::phrases::code;
        if revision != self.preferences.revision {
            return "stale_preferences";
        }
        if self.session.is_some() {
            return "busy";
        }
        let active = phrases.iter().filter(|p| p.active).count();
        if active > crate::phrases::MAX_ACTIVE {
            return code::TOO_MANY_ACTIVE;
        }
        if active == 0 || !crate::phrases::valid_settings(&phrases) {
            return code::INVALID_SELECTION;
        }
        let catalog = self.phrase_entries();
        for setting in phrases.iter().filter(|p| p.active) {
            let Some(entry) = catalog.iter().find(|e| e.id == setting.id) else {
                return code::INVALID_SELECTION;
            };
            if entry.custom {
                match &entry.measurement {
                    None => return code::UNMEASURED,
                    Some(m) if !m.passed && !acknowledge_untested => {
                        return code::MEASUREMENT_FAILED
                    }
                    Some(_) => {}
                }
            } else if entry.qualification != "dev_qualified" {
                return code::NOT_QUALIFIED;
            }
        }
        let (Some(storage), Some(runtime)) = (storage, self.phrase_runtime.clone()) else {
            return "preferences_unavailable";
        };
        if storage.configuration_status == crate::storage::ConfigurationStatus::SafeMode {
            return "configuration_not_ready";
        }
        let root = storage.root.clone();
        // Keyword set and worker preflight first; the running set changes only after both pass.
        if crate::phrases::stage(
            &root,
            &runtime.python,
            &runtime.home,
            &runtime.base_manifest,
            &catalog,
            &phrases,
            self.preferences.wake_sensitivity,
        )
        .is_err()
        {
            return code::START_FAILED;
        }
        match storage.update_wake_phrases(revision, phrases) {
            Ok(()) => {
                self.configure_storage(storage);
                self.emit(request_id.to_string(), None, "preferences_updated");
                "ok"
            }
            Err(_) => {
                let _ = crate::phrases::undo_switch(&root);
                "preferences_storage_error"
            }
        }
    }
    fn wake_phrase_add(
        &mut self,
        request_id: &str,
        revision: u64,
        text: &str,
        storage: Option<&mut crate::storage::Storage>,
    ) -> &'static str {
        use crate::phrases::code;
        let Some(storage) = storage else {
            return "preferences_unavailable";
        };
        let check = crate::phrases::check(text, self.phrase_lexicon());
        if !check.ok {
            let refused = check.code;
            self.phrase_check = Some(check);
            return refused;
        }
        let (Some(shown), Some(tokens)) = (check.text.clone(), check.tokens.clone()) else {
            return code::STORE_ERROR;
        };
        self.phrase_check = Some(check);
        let Ok(mut file) = crate::phrases::read_custom(&storage.root) else {
            return code::STORE_ERROR;
        };
        if revision != file.revision {
            return code::STALE_STORE;
        }
        if self.phrase_defaults.iter().any(|e| e.tokens == tokens)
            || file.phrases.iter().any(|p| p.tokens == tokens)
        {
            return code::DUPLICATE;
        }
        if file.phrases.len() >= crate::phrases::MAX_CUSTOM {
            return code::STORE_FULL;
        }
        let Some(next) = file.revision.checked_add(1) else {
            return code::STORE_ERROR;
        };
        file.phrases.push(crate::phrases::Stored {
            id: crate::phrases::custom_id(&tokens),
            sha256: crate::phrases::digest(&shown, &tokens),
            text: shown,
            tokens,
            measurement: None,
        });
        file.revision = next;
        if crate::phrases::write_custom(&storage.root, &file).is_err() {
            return code::STORE_ERROR;
        }
        self.phrase_custom = file;
        self.emit(request_id.to_string(), None, "phrase_added");
        code::OK
    }
    fn wake_phrase_remove(
        &mut self,
        request_id: &str,
        revision: u64,
        id: &str,
        storage: Option<&mut crate::storage::Storage>,
    ) -> &'static str {
        use crate::phrases::code;
        let Some(storage) = storage else {
            return "preferences_unavailable";
        };
        let Ok(mut file) = crate::phrases::read_custom(&storage.root) else {
            return code::STORE_ERROR;
        };
        if revision != file.revision {
            return code::STALE_STORE;
        }
        let Some(index) = file.phrases.iter().position(|p| p.id == id) else {
            return code::NOT_FOUND;
        };
        let referenced = self.preferences.wake_phrases.iter().any(|s| s.id == id)
            || self.preferences.wake_phrase.as_deref() == Some(id);
        if referenced {
            return code::IN_USE;
        }
        let Some(next) = file.revision.checked_add(1) else {
            return code::STORE_ERROR;
        };
        file.phrases.remove(index);
        file.revision = next;
        if crate::phrases::write_custom(&storage.root, &file).is_err() {
            return code::STORE_ERROR;
        }
        self.phrase_custom = file;
        self.emit(request_id.to_string(), None, "phrase_removed");
        code::OK
    }
    fn wake_phrase_test(&mut self, id: &str) -> &'static str {
        use crate::phrases::code;
        let (Some(runtime), Some(root)) = (self.phrase_runtime.clone(), self.phrase_root.clone())
        else {
            return code::TEST_UNAVAILABLE;
        };
        let (Some(tts), true) = (runtime.tts.clone(), runtime.lexicon.is_some()) else {
            return code::TEST_UNAVAILABLE;
        };
        if self.phrase_job.is_some()
            || self
                .phrase_test
                .as_ref()
                .is_some_and(|t| t.state == "running")
        {
            return code::TEST_RUNNING;
        }
        let Some(entry) = self
            .phrase_custom
            .phrases
            .iter()
            .find(|p| p.id == id)
            .cloned()
        else {
            return code::NOT_FOUND;
        };
        self.phrase_job = Some(crate::phrases::TestJob {
            id: entry.id.clone(),
            text: entry.text.clone(),
            tokens: entry.tokens.clone(),
            root,
            python: runtime.python.clone(),
            home: runtime.home.clone(),
            base_manifest: runtime.base_manifest.clone(),
            tts,
            catalog: self.phrase_entries(),
        });
        self.phrase_test = Some(crate::phrases::TestView {
            id: entry.id,
            state: "running",
            code: None,
        });
        code::OK
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
        self.prune_events(crate::protocol::unix_ms());
        if let Some(storage) = storage.as_deref_mut() {
            if crate::hub::expire_import(storage, now) {
                self.hub_import_expired(storage);
            }
            self.refresh_plugins(storage);
            self.purge_history_due(storage, crate::protocol::unix_ms());
        }
        self.sweep_tools();
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
        // U1: while a restart is pending, preference writes stay open (the latest write wins and applies at the
        // next start, or live for a sensitivity change). Every other operation still waits for the restart.
        let writes_while_restart_pending = matches!(
            req.operation,
            Operation::Preferences { .. }
                | Operation::RollbackPreferences { .. }
                | Operation::PreferencesRestoreDefaults { .. }
                | Operation::FeedbackPreferences { .. }
                | Operation::SelectWake { .. }
                | Operation::SelectWakePhrases { .. }
                | Operation::WakePhraseValidate { .. }
                | Operation::WakePhraseAdd { .. }
                | Operation::WakePhraseRemove { .. }
                | Operation::WakePhraseTest { .. }
                | Operation::LanguagePreference { .. }
                | Operation::LiveAudioPreference { .. }
                | Operation::RealActionsPreference { .. }
                | Operation::HistoryRetentionPreference { .. }
                | Operation::DeveloperModePreference { .. }
                | Operation::AudioDevices
                | Operation::AudioProbe { .. }
                | Operation::AudioRecommendInput
        );
        if let Some(storage) = storage.as_deref_mut() {
            storage.live_pipeline = self.live.pipeline_enabled();
        }
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
            Operation::CoreRestart if self.restart_busy() => "busy",
            Operation::CoreRestart => {
                // Accepted: the reply is `ok`; the serve loop flushes and exits with 75 right after it.
                self.restart_requested = true;
                self.emit(req.request_id.clone(), None, "core_restart_requested");
                "ok"
            }
            _ if self.configuration_status == crate::storage::ConfigurationStatus::SafeMode
                || (self.configuration_status
                    == crate::storage::ConfigurationStatus::RestartRequired
                    && !writes_while_restart_pending) =>
            {
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
            Operation::CapabilityInvoke { .. } | Operation::CapabilityCancel { .. }
                if self.agent.is_active() =>
            {
                "agent_busy"
            }
            Operation::CapabilityInvoke { .. } | Operation::CapabilityCancel { .. }
                if self.skills.is_active() =>
            {
                "skill_busy"
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
                approval_revision,
            } => match (storage.as_deref_mut(), self.hub.clone()) {
                (Some(storage), Some(hub)) => {
                    let hub = hub.with_approvals(storage);
                    // Optional CAS: a caller that saw an older approval state must re-read first.
                    if approval_revision.is_some_and(|seen| seen != hub.approval_revision) {
                        self.hub = Some(hub);
                        "stale_hub_revision"
                    } else {
                        let result = self.plugins.revoke(storage, &hub, revision, &plugin_id);
                        self.hub = Some(hub.with_approvals(storage));
                        self.plugin_result(&req.request_id, result)
                    }
                }
                _ => "hub_unavailable",
            },
            Operation::CapabilityInvoke {
                capability,
                input,
                deadline_ms,
            } => {
                let result = self.plugins.invoke(
                    self.hub.as_ref(),
                    &capability,
                    input,
                    deadline_ms,
                    &self.llm,
                );
                if result.is_ok() {
                    self.tool_source = true;
                }
                self.plugin_result(&req.request_id, result)
            }
            Operation::CapabilityCancel { capability } => {
                let result = self.plugins.cancel(&capability);
                self.plugin_result(&req.request_id, result)
            }
            Operation::SecretSet { .. }
            | Operation::SecretClear { .. }
            | Operation::LlmConfigure { .. }
            | Operation::LlmMarkGood { .. }
            | Operation::LlmRollback { .. }
            | Operation::PluginSettingsClear { .. }
                if self.session.is_some() =>
            {
                "busy"
            }
            Operation::SecretSet { provider, key } => match storage.as_deref() {
                Some(storage) => match self.llm.set_secret(storage, &provider, key.expose()) {
                    Ok(()) => {
                        self.emit(req.request_id.clone(), None, "secret_set");
                        "ok"
                    }
                    Err(code) => code,
                },
                None => "secrets_unavailable",
            },
            Operation::SecretClear { provider } => match storage.as_deref() {
                Some(storage) => match self.llm.clear_secret(storage, &provider) {
                    Ok(()) => {
                        self.emit(req.request_id.clone(), None, "secret_cleared");
                        "ok"
                    }
                    Err(code) => code,
                },
                None => "secrets_unavailable",
            },
            Operation::LlmConfigure {
                revision,
                provider,
                model,
                custom_url,
                local_port,
                fallback,
                cloud_consent,
            } => match storage.as_deref() {
                Some(storage) => {
                    let input = crate::llmcfg::ConfigInput {
                        provider,
                        model,
                        custom_url,
                        local_port,
                        fallback,
                        cloud_consent,
                    };
                    match self.llm.configure(storage, revision, input) {
                        Ok(()) => {
                            self.emit(req.request_id.clone(), None, "llm_configured");
                            // A changed chat configuration revokes the run that depends on it.
                            self.agent_abort_revoked();
                            "ok"
                        }
                        Err(code) => code,
                    }
                }
                None => "llm_unavailable",
            },
            Operation::LlmMarkGood { revision } => match storage.as_deref() {
                Some(storage) => match self.llm.mark_good(storage, revision) {
                    Ok(()) => {
                        self.emit(req.request_id.clone(), None, "llm_marked_good");
                        "ok"
                    }
                    Err(code) => code,
                },
                None => "llm_unavailable",
            },
            Operation::LlmRollback { revision } => match storage.as_deref() {
                Some(storage) => match self.llm.rollback(storage, revision) {
                    Ok(()) => {
                        self.emit(req.request_id.clone(), None, "llm_rolled_back");
                        "ok"
                    }
                    Err(code) => code,
                },
                None => "llm_unavailable",
            },
            Operation::PluginSettingsClear { plugin_id } => {
                if !crate::protocol::valid_id(&plugin_id) {
                    "invalid_id"
                } else {
                    match storage.as_deref() {
                        Some(storage) => {
                            match crate::storage::plugin_settings_clear(&storage.root, &plugin_id) {
                                Ok(()) => {
                                    self.emit(
                                        req.request_id.clone(),
                                        None,
                                        "plugin_settings_cleared",
                                    );
                                    "ok"
                                }
                                Err(_) => "settings_unavailable",
                            }
                        }
                        None => "settings_unavailable",
                    }
                }
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
            | Operation::HubDiscardStaged { .. }
                if self.session.is_some() =>
            {
                "busy"
            }
            Operation::HubDiscardStaged {
                revision,
                plugin_id,
            } => {
                if let (Some(storage), Some(hub)) = (storage, self.hub.as_ref()) {
                    let result = crate::hub::discard_staged(storage, hub, revision, &plugin_id);
                    self.hub = Some(hub.clone().with_approvals(storage));
                    match result {
                        Ok(event) => {
                            self.emit(req.request_id.clone(), None, event);
                            "ok"
                        }
                        Err(code) => code,
                    }
                } else {
                    "hub_unavailable"
                }
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
            Operation::LiveAudioPreference { revision, .. }
                if revision != self.preferences.revision =>
            {
                "stale_preferences"
            }
            Operation::LiveAudioPreference { .. } if self.session.is_some() => "busy",
            // Turning the microphone on needs the client's confirmation; turning it off never does.
            Operation::LiveAudioPreference {
                enabled: true,
                confirmed: false,
                ..
            } if !self.preferences.live_audio => "consent_required",
            // Same value: nothing is written and no event is emitted.
            Operation::LiveAudioPreference { enabled, .. }
                if enabled == self.preferences.live_audio =>
            {
                "ok"
            }
            Operation::LiveAudioPreference {
                revision, enabled, ..
            } => {
                if let Some(storage) = storage {
                    let result = storage.update_live_audio(revision, enabled);
                    self.configure_storage(storage);
                    if result.is_ok() {
                        // Content-free: the kind alone says whether the microphone consent went on or off.
                        let kind = if enabled {
                            "live_audio_enabled"
                        } else {
                            "live_audio_disabled"
                        };
                        self.emit(req.request_id.clone(), None, kind);
                        "ok"
                    } else {
                        "preferences_storage_error"
                    }
                } else {
                    "preferences_unavailable"
                }
            }
            // A11 consent for host actions. Same rules as the microphone consent; also refused while a command or tool
            // job is queued or running, so one job never changes its executor mid-flight.
            Operation::RealActionsPreference { revision, .. }
                if revision != self.preferences.revision =>
            {
                "stale_preferences"
            }
            Operation::RealActionsPreference { .. }
                if self.session.is_some() || self.command_job.is_some() || self.tools.busy() =>
            {
                "busy"
            }
            Operation::RealActionsPreference {
                enabled: true,
                confirmed: false,
                ..
            } if !self.preferences.real_actions => "consent_required",
            Operation::RealActionsPreference { enabled, .. }
                if enabled == self.preferences.real_actions =>
            {
                "ok"
            }
            Operation::RealActionsPreference {
                revision, enabled, ..
            } => {
                if let Some(storage) = storage {
                    let result = storage.update_real_actions(revision, enabled);
                    self.configure_storage(storage);
                    if result.is_ok() {
                        // Content-free: the kind alone says whether host actions were consented or withdrawn.
                        let kind = if enabled {
                            "real_actions_enabled"
                        } else {
                            "real_actions_disabled"
                        };
                        self.emit(req.request_id.clone(), None, kind);
                        "ok"
                    } else {
                        "preferences_storage_error"
                    }
                } else {
                    "preferences_unavailable"
                }
            }
            // CFG-04: the purge runs inside `configure_storage`; `never` also keeps this change out of the timeline.
            Operation::HistoryRetentionPreference { revision, .. }
                if revision != self.preferences.revision =>
            {
                "stale_preferences"
            }
            Operation::HistoryRetentionPreference { retention, .. }
                if retention == self.preferences.history_retention =>
            {
                "ok"
            }
            Operation::HistoryRetentionPreference {
                revision,
                retention,
            } => {
                if let Some(storage) = storage {
                    let result = storage.update_history_retention(revision, retention);
                    self.configure_storage(storage);
                    if result.is_ok() {
                        self.emit(req.request_id.clone(), None, "history_retention_changed");
                        "ok"
                    } else {
                        "preferences_storage_error"
                    }
                } else {
                    "preferences_unavailable"
                }
            }
            // DIAG-02 developer mode. Content-free event; no consent and no effect on authority.
            Operation::DeveloperModePreference { revision, .. }
                if revision != self.preferences.revision =>
            {
                "stale_preferences"
            }
            Operation::DeveloperModePreference { enabled, .. }
                if enabled == self.preferences.developer_mode =>
            {
                "ok"
            }
            Operation::DeveloperModePreference { revision, enabled } => {
                if let Some(storage) = storage {
                    let result = storage.update_developer_mode(revision, enabled);
                    self.configure_storage(storage);
                    if result.is_ok() {
                        let kind = if enabled {
                            "developer_mode_enabled"
                        } else {
                            "developer_mode_disabled"
                        };
                        self.emit(req.request_id.clone(), None, kind);
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
            Operation::LanguagePreference { revision, .. }
                if revision != self.preferences.revision =>
            {
                "stale_preferences"
            }
            Operation::LanguagePreference { .. } if self.session.is_some() => "busy",
            Operation::LanguagePreference {
                revision,
                stt_languages,
                tts_language,
                tts_voice,
            } => {
                let unchanged = stt_languages == self.preferences.stt_languages
                    && tts_language == self.preferences.tts_language
                    && tts_voice == self.preferences.tts_voice;
                if let Err(code) =
                    self.languages
                        .validate_selection(&stt_languages, &tts_language, &tts_voice)
                {
                    code
                } else if unchanged {
                    "ok"
                } else if let Some(storage) = storage {
                    let result =
                        storage.update_languages(revision, stt_languages, tts_language, tts_voice);
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
                if self
                    .preferences
                    .previous_preferences
                    .as_ref()
                    .is_some_and(|prev| {
                        !self
                            .languages
                            .selection_installed(&crate::languages::Selection {
                                stt: prev.stt_languages.clone(),
                                tts_language: prev.tts_language.clone(),
                                tts_voice: prev.tts_voice.clone(),
                            })
                    }) =>
            {
                "language_not_installed"
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
                session_timeout_ms,
                wake_sensitivity,
                audio_input_device,
                audio_output_device,
                ..
            } if !(50..=60000).contains(&session_timeout_ms)
                || wake_sensitivity
                    .is_some_and(|value| !crate::storage::valid_wake_sensitivity(value))
                || audio_input_device
                    .as_deref()
                    .is_some_and(|name| !crate::storage::valid_audio_device(name))
                || audio_output_device
                    .as_deref()
                    .is_some_and(|name| !crate::storage::valid_audio_device(name)) =>
            {
                "invalid_preferences"
            }
            Operation::PreferencesRestoreDefaults { revision }
                if revision != self.preferences.revision =>
            {
                "stale_preferences"
            }
            Operation::PreferencesRestoreDefaults { .. } if self.session.is_some() => "busy",
            Operation::PreferencesRestoreDefaults { revision } => {
                if let Some(storage) = storage {
                    let result = storage.restore_preferences_defaults(revision);
                    self.configure_storage(storage);
                    if result.is_ok() {
                        // Content-free: the kind alone says what happened.
                        self.emit(req.request_id.clone(), None, "preferences_restored");
                        "ok"
                    } else {
                        "preferences_storage_error"
                    }
                } else {
                    "preferences_unavailable"
                }
            }
            operation @ (Operation::Preferences { .. } | Operation::RollbackPreferences { .. }) => {
                if let Some(storage) = storage {
                    let result = match operation {
                        Operation::Preferences {
                            revision,
                            audible_feedback,
                            session_timeout_ms,
                            wake_sensitivity,
                            input_conditioning,
                            audio_input_device,
                            audio_output_device,
                        } => storage.update_preferences_with(
                            revision,
                            audible_feedback,
                            session_timeout_ms,
                            crate::storage::OptionalPreferences {
                                wake_sensitivity,
                                input_conditioning,
                                audio_input_device,
                                audio_output_device,
                            },
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

            Operation::SelectWakePhrases {
                revision,
                phrases,
                acknowledge_untested,
            } => self.select_wake_phrases(
                &req.request_id,
                revision,
                phrases,
                acknowledge_untested,
                storage,
            ),
            Operation::WakePhraseValidate { text } => {
                let check = crate::phrases::check(&text, self.phrase_lexicon());
                let code = check.code;
                self.phrase_check = Some(check);
                code
            }
            Operation::WakePhraseAdd { revision, text } => {
                self.wake_phrase_add(&req.request_id, revision, &text, storage)
            }
            Operation::WakePhraseRemove { revision, id } => {
                self.wake_phrase_remove(&req.request_id, revision, &id, storage)
            }
            Operation::WakePhraseTest { id } => self.wake_phrase_test(&id),
            Operation::Text { raw } => {
                if !self.virtual_input || self.command_wake.is_none() {
                    "input_disabled"
                } else if raw.trim().is_empty()
                    || raw.len() > 512
                    || raw.chars().any(char::is_control)
                {
                    "invalid_text"
                } else if self.session.is_some() {
                    // N-5: during a voice session the typed turn waits (one at a time) and runs when it ends.
                    self.queue_chat(QueuedChat::Text {
                        request_id: req.request_id.clone(),
                        raw,
                    })
                } else {
                    self.text_turn(req.request_id.clone(), raw, now)
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
            Operation::ToolDecide { .. } if self.session.is_some() => "busy",
            Operation::ToolDecide {
                proposal_id,
                decision,
            } => self.tool_decide(req.request_id.clone(), &proposal_id, decision),
            // N-5: an agent goal during a voice session waits in the same single slot as a typed turn.
            Operation::AgentStart { goal, capability } if self.voice_active() => {
                self.queue_chat(QueuedChat::Agent {
                    request_id: req.request_id.clone(),
                    goal,
                    capability,
                })
            }
            Operation::AgentStart { goal, capability } => {
                self.agent_start(req.request_id.clone(), &goal, capability, now)
            }
            Operation::AgentAbort { run_id } => self.agent_abort(&run_id),
            Operation::AgentTestBump => self.agent_test_bump(),
            Operation::SkillValidate { manifest } => {
                crate::skills::wire_op(self.skill_validate(manifest))
            }
            Operation::SkillSaveDraft { manifest } => {
                crate::skills::wire_op(self.skill_save_draft(manifest))
            }
            Operation::SkillDryRun {
                id,
                version,
                inputs,
            } => crate::skills::wire_op(self.skill_dry_run(&id, &version, inputs)),
            Operation::SkillApprove {
                id,
                version,
                revision,
            } => crate::skills::wire_op(self.skill_approve(&id, &version, revision)),
            Operation::SkillEnable { id, revision } => {
                crate::skills::wire_op(self.skill_enable(&id, revision))
            }
            Operation::SkillDisable { id, revision } => {
                crate::skills::wire_op(self.skill_disable(&id, revision))
            }
            Operation::SkillRollback { id, revision } => {
                crate::skills::wire_op(self.skill_rollback_version(&id, revision))
            }
            Operation::SkillRemove { id, revision } => {
                crate::skills::wire_op(self.skill_remove(&id, revision))
            }
            Operation::SkillRun { id, inputs } => {
                crate::skills::wire_op(self.skill_run(&id, inputs))
            }
            Operation::SkillDecide {
                run_id,
                step,
                decision,
            } => crate::skills::wire_op(self.skill_decide(&run_id, &step, decision)),
            Operation::SkillCancel { run_id } => crate::skills::wire_op(self.skill_cancel(&run_id)),
            Operation::SkillExport { id, version } => {
                crate::skills::wire_op(self.skill_export(&id, &version))
            }
            Operation::Refused { code } => code,
            Operation::Personal { area, payload } => self.personal_op(&area, payload),
            Operation::PersonalExport => self.personal_export(),
            Operation::PersonalEraseAll { confirm } => {
                self.personal_erase_all(&req.request_id, confirm)
            }
            Operation::ListenStart => self.listen_start(req.request_id.clone(), now),
            Operation::SkillImport { name } => crate::skills::wire_op(self.skill_import(&name)),
            Operation::ConnectionCall { .. } if self.session.is_some() => "busy",
            Operation::ConnectionCall {
                id,
                operation,
                args,
                revision,
            } => self.connection_call(
                req.request_id.clone(),
                &id,
                &operation,
                &args,
                revision,
                now,
            ),
            Operation::ConnectionAdd {
                provider,
                label,
                revision,
            } => self.connection_op(storage.as_deref(), |c, _, st| {
                c.add(st, &provider, &label, revision)
            }),
            Operation::ConnectionConnect { id, revision } => {
                self.connection_op(storage.as_deref(), |c, _, st| c.connect(st, &id, revision))
            }
            Operation::ConnectionConsent {
                id,
                scopes,
                revision,
            } => self.connection_op(storage.as_deref(), |c, _, st| {
                c.consent(st, &id, scopes, revision)
            }),
            Operation::ConnectionTrustTools {
                id,
                tools,
                revision,
            } => self.connection_op(storage.as_deref(), |c, _, st| {
                c.trust_tools(st, &id, &tools, revision)
            }),
            Operation::ConnectionRefresh { id, revision } => self
                .connection_op(storage.as_deref(), |c, l, st| {
                    c.refresh(st, l, &id, revision)
                }),
            Operation::ConnectionDisconnect { id, revision } => self
                .connection_op(storage.as_deref(), |c, l, st| {
                    c.disconnect(st, l, &id, revision)
                }),
            Operation::ConnectionRevoke { id, revision } => self
                .connection_op(storage.as_deref(), |c, l, st| {
                    c.revoke(st, l, &id, revision)
                }),
            Operation::ConnectionRevokeScope {
                id,
                scope,
                revision,
            } => self.connection_op(storage.as_deref(), |c, _, st| {
                c.revoke_scope(st, &id, &scope, revision)
            }),
            Operation::ConnectionRemove { id, revision } => self
                .connection_op(storage.as_deref(), |c, l, st| {
                    c.remove(st, l, &id, revision)
                }),
            Operation::ConnectionSetToken {
                id,
                token,
                revision,
            } => self.connection_op(storage.as_deref(), |c, _, _| {
                c.set_token(&id, token.expose(), revision)
            }),
            Operation::SkillImportConfirm { name, revision } => {
                crate::skills::wire_op(self.skill_import_confirm(&name, revision))
            }
            Operation::RegistryPlan { purpose } => self.registry_plan_op(&purpose),
            Operation::RegistryAllowVisual {
                purpose,
                enabled,
                revision,
            } => self.registry_allow_op(
                req.request_id.clone(),
                storage.as_deref(),
                &purpose,
                enabled,
                revision,
            ),
            Operation::Snapshot => unreachable!(),
            // A4: bounded, read-only enumeration; the result is served by the next snapshot.
            Operation::AudioDevices => {
                self.audio_devices = Some(crate::devices::enumerate());
                "ok"
            }
            // A9: starts a 3 s recording in the transport task; the result is served by the next snapshot.
            Operation::AudioProbe { device } => self.audio_probe_start(device),
            // A13: starts the assistant run in the transport task; the result is served by the next snapshot.
            Operation::AudioRecommendInput => {
                let current = self.preferences.audio_input_device.clone();
                self.audio_recommend_start(current)
            }
        };
        self.sweep_tools();
        let mut response = self.response(req.request_id, code);
        response.personal_reply = self.personal_result.take();
        response
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
            pack_sha256: String::new(),
            scope: "dev_virtual_en",
            preflight: "verified",
            engines: Default::default(),
            wake_phrases: vec![
                crate::pack::WakeChoice {
                    id: "opaque_7".into(),
                    text: "Activate Atlas".into(),
                    qualification: "dev_qualified",
                    label: "OPAQUE_7".into(),
                    tokens: "AE1 K T IH0 V EY1 T".into(),
                    language: "en".into(),
                    boost: 1.2,
                    threshold: 0.22,
                },
                crate::pack::WakeChoice {
                    id: "opaque_8".into(),
                    text: "Other phrase".into(),
                    qualification: "poc_required",
                    label: "OPAQUE_8".into(),
                    tokens: "AH1 DH ER0 F R EY1 Z".into(),
                    language: "en".into(),
                    boost: 1.2,
                    threshold: 0.22,
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
    fn stt_queue_backlog_never_fails_the_session_or_drops_audio() {
        // A backlog is the transport's to absorb (src/stt.rs `Pipe`): the Core keeps every request in order
        // and the status stays ready. Only a stuck worker fails it, and that is reported by the supervisor.
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
        assert_eq!(c.stt_status, "ready");
        assert!(c.session.is_some());
        let queued: usize = c
            .stt_requests
            .iter()
            .map(|r| match r {
                SttRequest::Frame { samples, .. } => samples.len(),
                _ => 0,
            })
            .sum();
        // The detection packet opens the capture (pre-roll), and the 49 packets after it are queued: none dropped.
        assert_eq!(queued, 50 * 1600);
        assert!(c.stt_requests.len() > 32);
    }
    #[test]
    fn restart_moves_status_through_starting_to_ready_and_keeps_the_reason() {
        let now = Instant::now();
        let mut c = Core::new(Duration::from_secs(30), false);
        c.configure_stt("test".into());
        c.stt_reply(
            SttReply::Ready {
                engine: "test".into(),
            },
            now,
        );
        c.stt_restarting("worker_crashed");
        assert_eq!(c.stt_status, "starting");
        assert_eq!(
            c.response(String::new(), "ok").stt_last_error,
            Some("worker_crashed")
        );
        c.stt_reply(
            SttReply::Ready {
                engine: "test".into(),
            },
            now,
        );
        assert_eq!(c.stt_status, "ready");
        assert_eq!(
            c.response(String::new(), "ok").stt_last_error,
            Some("worker_crashed")
        );
        c.stt_failed_with("worker_backlog");
        assert_eq!(c.stt_status, "failed");
        assert_eq!(
            c.response(String::new(), "ok").stt_last_error,
            Some("worker_backlog")
        );
    }
    #[test]
    fn detection_while_restart_is_pending_is_dropped_without_panic() {
        // A wake phrase or sensitivity change sets RestartRequired; a detection then starts no session. It must be
        // dropped (the Core used to unwrap a missing session here and exit).
        let now = Instant::now();
        let mut c = Core::new(Duration::from_secs(30), false);
        c.stt_status = "ready";
        c.configuration_status = crate::storage::ConfigurationStatus::RestartRequired;
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
        assert!(c.session.is_none());
        assert!(c.stt_requests.is_empty());
    }
    fn wake_setting(id: &str, sensitivity: Option<f32>) -> crate::phrases::Setting {
        crate::phrases::Setting {
            id: id.into(),
            active: true,
            sensitivity,
        }
    }
    fn preferences(revision: u64, wake_sensitivity: Option<f32>) -> Operation {
        Operation::Preferences {
            revision,
            audible_feedback: false,
            session_timeout_ms: 30000,
            wake_sensitivity,
            input_conditioning: None,
            audio_input_device: None,
            audio_output_device: None,
        }
    }
    #[test]
    fn preference_writes_stay_open_while_a_restart_is_pending() {
        // U1: one wake change used to refuse every later change with configuration_not_ready until restart.
        // Now preference writes are accepted (the latest write wins); other operations still wait.
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("root");
        let mut storage = crate::storage::Storage::open(&root).unwrap();
        let revision = storage.config.revision;
        storage
            .update_wake_phrases(revision, vec![wake_setting("hey_gideon", None)])
            .unwrap();
        assert_eq!(
            storage.configuration_status,
            crate::storage::ConfigurationStatus::RestartRequired
        );
        let mut core = Core::new(Duration::from_secs(30), false);
        core.configure_storage(&storage);
        let now = Instant::now();
        let first = core.handle_with_storage(
            request("pref-1", preferences(storage.config.revision, Some(1.2))),
            now,
            Some(&mut storage),
        );
        assert_eq!(first.code, "ok");
        let second = core.handle_with_storage(
            request("pref-2", preferences(storage.config.revision, Some(0.8))),
            now,
            Some(&mut storage),
        );
        assert_eq!(second.code, "ok");
        assert_eq!(storage.config.wake_sensitivity, 0.8);
        assert_eq!(
            core.handle_with_storage(
                request("wake", Operation::VirtualWake),
                now,
                Some(&mut storage)
            )
            .code,
            "configuration_not_ready"
        );
        assert_eq!(
            storage.configuration_status,
            crate::storage::ConfigurationStatus::RestartRequired
        );
    }
    #[test]
    fn sensitivity_change_restarts_only_without_the_live_pipeline() {
        // A13: with the live pipeline running, a sensitivity-only change reaches the worker by its restart between
        // sessions (transport publishes the new keyword set), so the Core does not ask for a restart.
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("root");
        {
            let mut storage = crate::storage::Storage::open(&root).unwrap();
            let revision = storage.config.revision;
            storage
                .update_wake_phrases(revision, vec![wake_setting("hey_gideon", None)])
                .unwrap();
        }
        let mut storage = crate::storage::Storage::open(&root).unwrap();
        assert_eq!(
            storage.configuration_status,
            crate::storage::ConfigurationStatus::Ready
        );
        storage.live_pipeline = true;
        let revision = storage.config.revision;
        storage
            .update_wake_phrases(revision, vec![wake_setting("hey_gideon", Some(0.8))])
            .unwrap();
        assert_eq!(
            storage.configuration_status,
            crate::storage::ConfigurationStatus::Ready
        );
        assert_eq!(storage.config.wake_phrases[0].sensitivity, Some(0.8));
        // Without the live pipeline the same change needs the restart (the replay worker loads its keyword set once).
        storage.live_pipeline = false;
        let revision = storage.config.revision;
        storage
            .update_wake_phrases(revision, vec![wake_setting("hey_gideon", Some(1.2))])
            .unwrap();
        assert_eq!(
            storage.configuration_status,
            crate::storage::ConfigurationStatus::RestartRequired
        );
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
    fn events_carry_unix_ms_that_never_decreases_and_closed_origin_outcome() {
        let mut c = Core::new(Duration::from_secs(1), false);
        c.emit(String::new(), None, "tool_proposed");
        c.emit(String::new(), None, "tool_denied");
        c.emit_with(
            String::new(),
            None,
            "connection_call",
            crate::protocol::code_outcome("reauth_required"),
        );
        c.emit(String::new(), None, "hub_import_timeout");
        let shape: Vec<_> = c.events.iter().map(|e| (e.origin, e.outcome)).collect();
        assert_eq!(
            shape,
            vec![
                ("tool", "pending"),
                ("tool", "denied"),
                ("connection", "failed"),
                ("hub", "failed"),
            ]
        );
        assert!(c.events.iter().all(|e| e.at_ms > 1_600_000_000_000));
        // A clock that steps back cannot make the ring go backwards.
        let last = c.events.back().unwrap().at_ms;
        c.events.back_mut().unwrap().at_ms = last + 60_000;
        c.emit(String::new(), None, "session_started");
        assert!(c.events.back().unwrap().at_ms >= last + 60_000);
        for _ in 0..70 {
            c.emit(String::new(), None, "transcript_partial");
        }
        assert_eq!(c.events.len(), 64);
        assert!(c
            .events
            .iter()
            .zip(c.events.iter().skip(1))
            .all(|(a, b)| a.at_ms <= b.at_ms && a.sequence < b.sequence));
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
    #[test]
    fn history_retention_bounds_the_timeline_and_developer_mode_is_a_plain_cas() {
        use crate::storage::HistoryRetention;
        let now = Instant::now();
        let mut c = Core::new(Duration::from_secs(30), true);
        c.emit(String::new(), None, "wake_failed");
        assert_eq!(c.events.len(), 1);
        // `never`: the change itself and later events stay out of the timeline.
        c.preferences.history_retention = HistoryRetention::Never;
        c.emit(String::new(), None, "wake_failed");
        assert!(c.events.is_empty());
        assert!(c.response(String::new(), "ok").events.is_empty());
        // `days_7`: an event older than the window is pruned, a fresh one is kept.
        c.preferences.history_retention = HistoryRetention::Days7;
        let fresh = crate::protocol::unix_ms();
        let event = |at_ms: u64| Event {
            sequence: 0,
            at_ms,
            request_id: String::new(),
            session_id: None,
            kind: "wake_failed",
            origin: "speech",
            outcome: "failed",
        };
        c.events.push_back(event(1));
        c.events.push_back(event(fresh));
        c.prune_events(fresh);
        assert_eq!(c.events.len(), 1);
        assert_eq!(c.events[0].at_ms, fresh);
        // Developer mode: CAS on the revision, strict on the value, no consent, and the same value is a no-op.
        let stale = c.handle(
            request(
                "dev-stale",
                Operation::DeveloperModePreference {
                    revision: 7,
                    enabled: true,
                },
            ),
            now,
        );
        assert_eq!(stale.code, "stale_preferences");
        let same = c.handle(
            request(
                "dev-same",
                Operation::DeveloperModePreference {
                    revision: 0,
                    enabled: false,
                },
            ),
            now,
        );
        assert_eq!(same.code, "ok");
        let no_storage = c.handle(
            request(
                "dev-on",
                Operation::DeveloperModePreference {
                    revision: 0,
                    enabled: true,
                },
            ),
            now,
        );
        assert_eq!(no_storage.code, "preferences_unavailable");
        assert!(!c.preferences.developer_mode);
    }

    #[test]
    fn configure_storage_runs_the_audit_purge_for_the_stored_retention() {
        use crate::storage::HistoryRetention;
        use std::io::Write;
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("root");
        let mut store = crate::storage::Storage::open(&root).unwrap();
        store.audit(1).unwrap();
        let log = root.join("audit.log");
        std::fs::OpenOptions::new()
            .append(true)
            .open(&log)
            .unwrap()
            .write_all(b"{\"version\":1,\"sequence\":0,\"at_ms\":1}\n")
            .unwrap();
        store
            .update_history_retention(0, HistoryRetention::Days7)
            .unwrap();
        let mut c = Core::new(Duration::from_secs(30), true);
        c.configure_storage(&store);
        let text = std::fs::read_to_string(&log).unwrap();
        assert!(!text.contains("\"sequence\":0"), "old line purged: {text}");
        assert!(text.contains("\"sequence\":1"));
        // `never` through the same path removes the trail on the next configuration.
        store
            .update_history_retention(1, HistoryRetention::Never)
            .unwrap();
        c.configure_storage(&store);
        assert!(!log.exists());
    }

    #[test]
    fn real_actions_switch_grammar_authority_and_receipts() {
        let now = Instant::now();
        let mut c = Core::new(Duration::from_secs(30), true);
        c.configure_command_wakes(Vec::new());
        let outcome = |c: &Core| c.response(String::new(), "ok").command.unwrap().code;
        // Consent off: real-only steps are not understood, and a catalog app outside the sandbox is refused.
        c.handle(
            request(
                "off-1",
                Operation::Text {
                    raw: "unmute".into(),
                },
            ),
            now,
        );
        assert_eq!(outcome(&c), "unsupported");
        assert!(c.take_command_job().is_none());
        c.handle(
            request(
                "off-2",
                Operation::Text {
                    raw: "open kcalc".into(),
                },
            ),
            now,
        );
        assert_eq!(outcome(&c), "app_unavailable");
        assert!(c.take_command_job().is_none());
        assert!(c
            .response(String::new(), "ok")
            .actions
            .real
            .last_action
            .is_none());
        // Consent on: the same phrases become host jobs; a host failure reports its fixed code.
        c.preferences.real_actions = true;
        c.handle(
            request(
                "on-1",
                Operation::Text {
                    raw: "open kcalc".into(),
                },
            ),
            now,
        );
        let job = c.take_command_job().expect("host job");
        assert_eq!(
            job.command,
            Command::OpenApp {
                desktop_id: commands::KCALC.into()
            }
        );
        let busy = c.handle(
            request(
                "busy",
                Operation::RealActionsPreference {
                    revision: 0,
                    enabled: false,
                    confirmed: false,
                },
            ),
            now,
        );
        assert_eq!(busy.code, "busy");
        c.command_error(job, "app_not_installed", now);
        assert_eq!(outcome(&c), "app_not_installed");
        let failed = c
            .response(String::new(), "ok")
            .actions
            .real
            .last_action
            .unwrap();
        assert_eq!(
            (failed.kind, failed.app, failed.ok, failed.verified),
            ("open_app", Some("kcalc"), false, false)
        );
        // A verified host receipt is recorded as a verified action; the audit event carries no app name.
        c.handle(
            request(
                "on-2",
                Operation::Text {
                    raw: "unmute".into(),
                },
            ),
            now,
        );
        let job = c.take_command_job().expect("unmute job");
        let receipt = Receipt {
            job: job.clone(),
            verified: true,
            scope: "host".into(),
            result: "Som ativado · verificado com wpctl".into(),
        };
        c.command_reply(job, Some(receipt), now);
        assert_eq!(outcome(&c), "command_success");
        let done = c.response(String::new(), "ok");
        let last = done.actions.real.last_action.unwrap();
        assert_eq!(
            (last.kind, last.app, last.ok, last.verified),
            ("unmute", None, true, true)
        );
        assert!(done.actions.real.enabled);
        let audit: Vec<_> = done
            .events
            .iter()
            .filter(|e| e.kind == "host_action")
            .collect();
        assert_eq!(audit.len(), 2);
        assert!(audit
            .iter()
            .all(|e| e.kind == "host_action" && matches!(e.outcome, "ok" | "failed")));
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
        // N-5: a typed turn during the session waits in the queue (one slot); a second one is refused.
        assert_eq!(
            c.handle(request("t5", Operation::Text { raw: "mute".into() }), now)
                .code,
            "queued"
        );
        assert_eq!(
            c.handle(request("t6", Operation::Text { raw: "mute".into() }), now)
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

    #[test]
    fn core_restart_is_busy_during_a_voice_session_and_accepted_when_idle() {
        let now = Instant::now();
        let mut c = Core::new(Duration::from_secs(1), true);
        assert_eq!(
            c.handle(request("w", Operation::VirtualWake), now)
                .session_id,
            Some(1)
        );
        let busy = c.handle(request("r1", Operation::CoreRestart), now);
        assert_eq!(busy.code, "busy");
        assert!(!c.restart_requested());
        c.handle(request("c", Operation::Cancel { session_id: 1 }), now);
        let accepted = c.handle(request("r2", Operation::CoreRestart), now);
        assert_eq!(accepted.code, "ok");
        assert!(c.restart_requested());
        assert!(accepted
            .events
            .iter()
            .any(|e| e.kind == "core_restart_requested" && e.outcome == "ok"));
        // The same request id is never replayed as a second restart.
        assert_eq!(
            c.handle(request("r2", Operation::CoreRestart), now).code,
            "duplicate"
        );
    }
}
