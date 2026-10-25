use serde::{Deserialize, Serialize};

pub const VERSION: u16 = 1;
pub const MAX_MESSAGE: usize = 4096;
pub const MAX_ID: usize = 64;

#[derive(Debug)]
pub struct Request {
    pub version: u16,
    pub request_id: String,
    pub operation: Operation,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum Operation {
    HubBegin {
        revision: u64,
        plugin_id: String,
        manifest_sha256: String,
    },
    HubChunk {
        import_id: String,
        offset: u64,
        hex: String,
    },
    HubFinish {
        import_id: String,
    },
    HubAbort {
        import_id: String,
    },

    HubApprove {
        revision: u64,
        plugin_id: String,
        manifest_sha256: String,
        permissions: Vec<String>,
        publisher_unverified_ack: bool,
    },
    HubInstall {
        revision: u64,
        plugin_id: String,
        manifest_sha256: String,
    },
    HubRollback {
        revision: u64,
        plugin_id: String,
    },
    HubRemove {
        revision: u64,
        plugin_id: String,
    },
    /// Drops only the staged (not yet installed) payload; CAS on the approval revision.
    HubDiscardStaged {
        revision: u64,
        plugin_id: String,
    },
    Snapshot,
    /// A4: read-only enumeration of audio devices; the result is the snapshot block `audio.devices`.
    AudioDevices,
    /// Replies `ok`, then the Core exits with `transport::RESTART_EXIT_CODE` after flushing. Refused
    /// with `busy` while a voice session, agent run, skill run or plugin invocation is active.
    CoreRestart,
    FeedbackPreferences {
        revision: u64,
        visual_feedback: bool,
        output_volume_percent: u8,
    },
    SelectWake {
        revision: u64,
        phrase_id: String,
    },
    /// Wake phrase list (`wake_phrases` preference, at most 5 active). CAS on `revision`. An active custom
    /// phrase whose synthetic test failed needs `acknowledge_untested`.
    SelectWakePhrases {
        revision: u64,
        phrases: Vec<crate::phrases::Setting>,
        acknowledge_untested: bool,
    },
    /// Checks a candidate custom phrase without storing it (live preview of the add dialog).
    WakePhraseValidate {
        text: String,
    },
    /// Stores a checked custom phrase. CAS on the custom store revision (`wake_phrases.custom_revision`).
    WakePhraseAdd {
        revision: u64,
        text: String,
    },
    /// Removes a custom phrase that is not active. CAS on the custom store revision.
    WakePhraseRemove {
        revision: u64,
        id: String,
    },
    /// Starts the synthetic measurement of a custom phrase (`wake_phrases.test` shows the progress).
    WakePhraseTest {
        id: String,
    },
    /// Idiomas de fala (`tts_language` + `tts_voice`) e de transcrição (`stt_languages`, 1..=3). CAS on
    /// `revision`; only installed languages are accepted (`languages::LanguageCatalog`). Applies at next start.
    LanguagePreference {
        revision: u64,
        stt_languages: Vec<String>,
        tts_language: String,
        tts_voice: String,
    },
    /// A6 consent for the live microphone. `confirmed` must be true to turn it on: the client asserts that
    /// the user accepted the consent text. Takes effect at the next Core start (`restart_required`).
    LiveAudioPreference {
        revision: u64,
        enabled: bool,
        confirmed: bool,
    },
    RecoverConfiguration {
        revision: u64,
    },
    /// Optional fields (`wake_sensitivity`, device names) keep the stored value when absent.
    Preferences {
        revision: u64,
        audible_feedback: bool,
        session_timeout_ms: u64,
        wake_sensitivity: Option<f32>,
        audio_input_device: Option<String>,
        audio_output_device: Option<String>,
    },
    RollbackPreferences {
        revision: u64,
    },
    /// Backs up `config.json` to `config.json.bak`, then resets every preference to its default.
    /// CAS on `revision`; refused with `busy` during a voice session.
    PreferencesRestoreDefaults {
        revision: u64,
    },
    Text {
        raw: String,
    },
    VirtualWake,
    Cancel {
        session_id: u64,
    },
    Action {
        session_id: u64,
        capability: Capability,
    },
    PluginEnable {
        revision: u64,
        plugin_id: String,
    },
    PluginDisable {
        revision: u64,
        plugin_id: String,
    },
    PluginRevoke {
        revision: u64,
        plugin_id: String,
        /// Optional CAS on the Hub approval revision the caller saw; absent means unchecked.
        approval_revision: Option<u64>,
    },
    CapabilityInvoke {
        capability: String,
        input: serde_json::Value,
        deadline_ms: u64,
    },
    CapabilityCancel {
        capability: String,
    },
    SecretSet {
        provider: String,
        key: crate::secrets::SecretKey,
    },
    SecretClear {
        provider: String,
    },
    LlmConfigure {
        revision: u64,
        provider: String,
        model: String,
        custom_url: Option<String>,
        local_port: Option<u16>,
        fallback: Option<crate::llmcfg::FallbackInput>,
        cloud_consent: bool,
    },
    LlmMarkGood {
        revision: u64,
    },
    LlmRollback {
        revision: u64,
    },
    /// Wire: `{"op":"plugin_settings_clear","version":1,"request_id":ID,"plugin_id":PLUGIN}`.
    /// No revision: removes only that plugin's settings file; unknown fields are refused.
    PluginSettingsClear {
        plugin_id: String,
    },
    ToolDecide {
        proposal_id: String,
        decision: ToolDecision,
    },
    AgentStart {
        goal: String,
        capability: Option<String>,
    },
    AgentAbort {
        run_id: String,
    },
    /// Test-only: exists solely under `--agent-synthetic`; otherwise refused.
    AgentTestBump,
    /// S4 skill ops. Manifests travel inline (at most 16 KiB); see `transport` for the frame bound.
    SkillValidate {
        manifest: serde_json::Value,
    },
    SkillSaveDraft {
        manifest: serde_json::Value,
    },
    SkillDryRun {
        id: String,
        version: String,
        inputs: serde_json::Value,
    },
    SkillApprove {
        id: String,
        version: String,
        revision: u64,
    },
    SkillEnable {
        id: String,
        revision: u64,
    },
    SkillDisable {
        id: String,
        revision: u64,
    },
    SkillRollback {
        id: String,
        revision: u64,
    },
    SkillRemove {
        id: String,
        revision: u64,
    },
    SkillRun {
        id: String,
        inputs: serde_json::Value,
    },
    SkillDecide {
        run_id: String,
        step: String,
        decision: ToolDecision,
    },
    SkillCancel {
        run_id: String,
    },
    /// D4: writes `<home>/skill-exports/<id>-<version>.gskill`.
    SkillExport {
        id: String,
        version: String,
    },
    /// D4: reads `<home>/skill-imports/<name>.gskill` and stores a preview only.
    SkillImport {
        name: String,
    },
    /// D4: installs the previewed package as `draft`; grants nothing.
    SkillImportConfirm {
        name: String,
        revision: u64,
    },
    /// S5 connections. `revision` is an optional CAS on the connections ledger.
    ConnectionAdd {
        provider: String,
        label: String,
        revision: Option<u64>,
    },
    ConnectionConnect {
        id: String,
        revision: Option<u64>,
    },
    ConnectionConsent {
        id: String,
        scopes: Vec<String>,
        revision: Option<u64>,
    },
    ConnectionRefresh {
        id: String,
        revision: Option<u64>,
    },
    ConnectionDisconnect {
        id: String,
        revision: Option<u64>,
    },
    ConnectionRevoke {
        id: String,
        revision: Option<u64>,
    },
    /// Revokes one granted scope of an account. The token stays; calls needing the scope then
    /// answer `scope_not_granted`. Wire: `connection_revoke_scope {id, scope, revision?}`.
    ConnectionRevokeScope {
        id: String,
        scope: String,
        revision: Option<u64>,
    },
    ConnectionRemove {
        id: String,
        revision: Option<u64>,
    },
    /// S5 E2.4: the user trusts (re-approves) discovered MCP tools by name.
    ConnectionTrustTools {
        id: String,
        tools: Vec<String>,
        revision: Option<u64>,
    },
    ConnectionCall {
        id: String,
        operation: String,
        args: serde_json::Value,
        revision: Option<u64>,
    },
    /// S5 Home Assistant: the long-lived token, validated by one probe. Debug redacts it.
    ConnectionSetToken {
        id: String,
        token: crate::secrets::SecretKey,
        revision: Option<u64>,
    },
    /// S5 E3: plans a purpose (which route would run); executes nothing.
    RegistryPlan {
        purpose: String,
    },
    /// S5 E3: the user's switch for the visual fallback of one purpose. `revision` is an optional CAS.
    RegistryAllowVisual {
        purpose: String,
        enabled: bool,
        revision: Option<u64>,
    },
    /// Transport-only: a skill manifest line over the frame bound is answered with `code`.
    Refused {
        code: &'static str,
    },
}

/// User decision on a tool proposal. Only a client request can carry it; plugins cannot.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ToolDecision {
    Authorize,
    Deny,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Capability {
    Status,
    OpenApp,
    Volume,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum State {
    Idle,
    Capturing,
    Transcribing,
    Executing,
    Speaking,
}

#[derive(Debug, Clone, Serialize)]
pub struct Event {
    pub sequence: u64,
    /// Unix epoch milliseconds, never earlier than the previous event in the ring.
    pub at_ms: u64,
    pub request_id: String,
    pub session_id: Option<u64>,
    pub kind: &'static str,
    /// Closed vocabulary derived from `kind` (see `origin_of`).
    pub origin: &'static str,
    /// Closed vocabulary (see `outcome_of` and `code_outcome`).
    pub outcome: &'static str,
}

/// Unix epoch milliseconds from the wall clock; 0 when the clock is before 1970.
pub fn unix_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0, |d| u64::try_from(d.as_millis()).unwrap_or(u64::MAX))
}

/// Origin of an event kind. Closed set: core, plugin, hub, skill, connection, tool, agent, llm,
/// speech, config, registry.
pub fn origin_of(kind: &str) -> &'static str {
    const PREFIXES: [(&str, &str); 15] = [
        ("live_audio_", "config"),
        ("connection_", "connection"),
        ("tool_", "tool"),
        ("agent_", "agent"),
        ("skill_", "skill"),
        ("hub_", "hub"),
        ("plugin_", "plugin"),
        ("llm_", "llm"),
        ("transcript_", "speech"),
        ("speech_", "speech"),
        ("wake_", "speech"),
        ("secret_", "config"),
        ("preferences_", "config"),
        ("configuration_", "config"),
        ("registry_", "registry"),
    ];
    PREFIXES
        .iter()
        .find(|(prefix, _)| kind.starts_with(prefix))
        .map_or("core", |(_, origin)| origin)
}

/// Outcome of an event kind. Closed set: ok, pending, denied, failed, expired, cancelled.
pub fn outcome_of(kind: &str) -> &'static str {
    if kind.ends_with("_proposed") || kind.ends_with("_previewed") || kind.ends_with("_staged") {
        "pending"
    } else if kind.ends_with("_denied") {
        "denied"
    } else if kind.ends_with("_failed") || kind.ends_with("_timeout") || kind.ends_with("_error") {
        "failed"
    } else if kind.ends_with("_expired") {
        "expired"
    } else if kind.ends_with("_cancelled") {
        "cancelled"
    } else {
        "ok"
    }
}

/// Outcome of a connection audit code (`ok` or a failure code such as `reauth_required`).
pub fn code_outcome(code: &str) -> &'static str {
    if code == "ok" {
        "ok"
    } else if code.contains("expired") {
        "expired"
    } else if code.contains("denied") {
        "denied"
    } else if code.contains("cancel") {
        "cancelled"
    } else {
        "failed"
    }
}

#[derive(Debug, Serialize)]
pub struct Response {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hub: Option<crate::hub::Snapshot>,
    pub plugins: crate::plugins::PluginSnapshot,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub capability_result: Option<crate::plugins::CapabilityResult>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub partial: Option<String>,
    pub llm: crate::llmcfg::Snapshot,
    pub base_pack: Option<crate::pack::Snapshot>,
    pub configuration_status: crate::storage::ConfigurationStatus,
    pub configuration_recovery_available: bool,
    pub preferences: crate::storage::Config,
    pub languages: crate::languages::View,
    pub command: Option<crate::commands::Outcome>,
    pub tool_proposals: Vec<crate::tools::View>,
    pub agent: Option<crate::agent::View>,
    pub skills: Option<crate::skills::View>,
    pub connections: crate::connections::View,
    pub registry: crate::registry::View,
    pub text_input_available: bool,
    pub speech_samples: usize,
    pub speech_status: &'static str,
    pub speech: Option<crate::tts::Summary>,
    pub stt_status: &'static str,
    pub transcript: Option<crate::stt::Transcript>,
    pub capture: Option<crate::capture::CaptureSummary>,
    pub wake_status: &'static str,
    pub audio: crate::live::AudioView,
    /// Wake phrase catalog, active list and synthetic measurements (src/phrases.rs `View`).
    pub wake_phrases: crate::phrases::View,
    /// Result of `wake_phrase_validate` (also attached to a refused `wake_phrase_add`).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub phrase_check: Option<crate::phrases::Check>,
    pub version: u16,
    pub request_id: String,
    pub code: &'static str,
    pub state: State,
    pub session_id: Option<u64>,
    pub sequence: u64,
    pub events: Vec<Event>,
}

pub fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= MAX_ID
        && id
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"_-".contains(&c))
}

// Full struct variants reject unknown fields, including unit operations.
#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
enum WireRequest {
    HubBegin {
        version: u16,
        request_id: String,
        revision: u64,
        plugin_id: String,
        manifest_sha256: String,
    },
    HubChunk {
        version: u16,
        request_id: String,
        import_id: String,
        offset: u64,
        hex: String,
    },
    HubFinish {
        version: u16,
        request_id: String,
        import_id: String,
    },
    HubAbort {
        version: u16,
        request_id: String,
        import_id: String,
    },

    HubApprove {
        version: u16,
        request_id: String,
        revision: u64,
        plugin_id: String,
        manifest_sha256: String,
        permissions: Vec<String>,
        publisher_unverified_ack: bool,
    },
    HubInstall {
        version: u16,
        request_id: String,
        revision: u64,
        plugin_id: String,
        manifest_sha256: String,
    },
    HubRollback {
        version: u16,
        request_id: String,
        revision: u64,
        plugin_id: String,
    },
    HubRemove {
        version: u16,
        request_id: String,
        revision: u64,
        plugin_id: String,
    },
    HubDiscardStaged {
        version: u16,
        request_id: String,
        revision: u64,
        plugin_id: String,
    },
    FeedbackPreferences {
        version: u16,
        request_id: String,
        revision: u64,
        visual_feedback: bool,
        output_volume_percent: u8,
    },
    SelectWake {
        version: u16,
        request_id: String,
        revision: u64,
        phrase_id: String,
    },
    SelectWakePhrases {
        version: u16,
        request_id: String,
        revision: u64,
        phrases: Vec<crate::phrases::Setting>,
        #[serde(default)]
        acknowledge_untested: bool,
    },
    WakePhraseValidate {
        version: u16,
        request_id: String,
        text: String,
    },
    WakePhraseAdd {
        version: u16,
        request_id: String,
        revision: u64,
        text: String,
    },
    WakePhraseRemove {
        version: u16,
        request_id: String,
        revision: u64,
        id: String,
    },
    WakePhraseTest {
        version: u16,
        request_id: String,
        id: String,
    },
    LanguagePreference {
        version: u16,
        request_id: String,
        revision: u64,
        stt_languages: Vec<String>,
        tts_language: String,
        tts_voice: String,
    },
    LiveAudioPreference {
        version: u16,
        request_id: String,
        revision: u64,
        enabled: bool,
        confirmed: bool,
    },
    RecoverConfiguration {
        version: u16,
        request_id: String,
        revision: u64,
    },
    Preferences {
        version: u16,
        request_id: String,
        revision: u64,
        audible_feedback: bool,
        session_timeout_ms: u64,
        #[serde(default)]
        wake_sensitivity: Option<f32>,
        #[serde(default)]
        audio_input_device: Option<String>,
        #[serde(default)]
        audio_output_device: Option<String>,
    },
    RollbackPreferences {
        version: u16,
        request_id: String,
        revision: u64,
    },
    PreferencesRestoreDefaults {
        version: u16,
        request_id: String,
        revision: u64,
    },
    Snapshot {
        version: u16,
        request_id: String,
    },
    AudioDevices {
        version: u16,
        request_id: String,
    },
    CoreRestart {
        version: u16,
        request_id: String,
    },
    Text {
        version: u16,
        request_id: String,
        raw: String,
    },
    VirtualWake {
        version: u16,
        request_id: String,
    },
    Cancel {
        version: u16,
        request_id: String,
        session_id: u64,
    },
    Action {
        version: u16,
        request_id: String,
        session_id: u64,
        capability: Capability,
    },
    PluginEnable {
        version: u16,
        request_id: String,
        revision: u64,
        plugin_id: String,
    },
    PluginDisable {
        version: u16,
        request_id: String,
        revision: u64,
        plugin_id: String,
    },
    PluginRevoke {
        version: u16,
        request_id: String,
        revision: u64,
        plugin_id: String,
        #[serde(default)]
        approval_revision: Option<u64>,
    },
    CapabilityInvoke {
        version: u16,
        request_id: String,
        capability: String,
        input: serde_json::Value,
        deadline_ms: u64,
    },
    CapabilityCancel {
        version: u16,
        request_id: String,
        capability: String,
    },
    SecretSet {
        version: u16,
        request_id: String,
        provider: String,
        key: crate::secrets::SecretKey,
    },
    SecretClear {
        version: u16,
        request_id: String,
        provider: String,
    },
    LlmConfigure {
        version: u16,
        request_id: String,
        revision: u64,
        provider: String,
        model: String,
        #[serde(default)]
        custom_url: Option<String>,
        #[serde(default)]
        local_port: Option<u16>,
        #[serde(default)]
        fallback: Option<crate::llmcfg::FallbackInput>,
        cloud_consent: bool,
    },
    LlmMarkGood {
        version: u16,
        request_id: String,
        revision: u64,
    },
    LlmRollback {
        version: u16,
        request_id: String,
        revision: u64,
    },
    PluginSettingsClear {
        version: u16,
        request_id: String,
        plugin_id: String,
    },
    ToolDecide {
        version: u16,
        request_id: String,
        proposal_id: String,
        decision: ToolDecision,
    },
    AgentStart {
        version: u16,
        request_id: String,
        goal: String,
        #[serde(default)]
        capability: Option<String>,
    },
    AgentAbort {
        version: u16,
        request_id: String,
        run_id: String,
    },
    AgentTestBump {
        version: u16,
        request_id: String,
    },
    SkillValidate {
        version: u16,
        request_id: String,
        manifest: serde_json::Value,
    },
    SkillSaveDraft {
        version: u16,
        request_id: String,
        manifest: serde_json::Value,
    },
    SkillDryRun {
        version: u16,
        request_id: String,
        id: String,
        skill_version: String,
        inputs: serde_json::Value,
    },
    SkillApprove {
        version: u16,
        request_id: String,
        id: String,
        skill_version: String,
        revision: u64,
    },
    SkillEnable {
        version: u16,
        request_id: String,
        id: String,
        revision: u64,
    },
    SkillDisable {
        version: u16,
        request_id: String,
        id: String,
        revision: u64,
    },
    SkillRollback {
        version: u16,
        request_id: String,
        id: String,
        revision: u64,
    },
    SkillRemove {
        version: u16,
        request_id: String,
        id: String,
        revision: u64,
    },
    SkillRun {
        version: u16,
        request_id: String,
        id: String,
        inputs: serde_json::Value,
    },
    SkillDecide {
        version: u16,
        request_id: String,
        run_id: String,
        step: String,
        decision: ToolDecision,
    },
    SkillCancel {
        version: u16,
        request_id: String,
        run_id: String,
    },
    SkillExport {
        version: u16,
        request_id: String,
        id: String,
        skill_version: String,
    },
    SkillImport {
        version: u16,
        request_id: String,
        name: String,
    },
    SkillImportConfirm {
        version: u16,
        request_id: String,
        name: String,
        revision: u64,
    },
    ConnectionAdd {
        version: u16,
        request_id: String,
        provider: String,
        label: String,
        #[serde(default)]
        revision: Option<u64>,
    },
    ConnectionConnect {
        version: u16,
        request_id: String,
        id: String,
        #[serde(default)]
        revision: Option<u64>,
    },
    ConnectionConsent {
        version: u16,
        request_id: String,
        id: String,
        scopes: Vec<String>,
        #[serde(default)]
        revision: Option<u64>,
    },
    ConnectionRefresh {
        version: u16,
        request_id: String,
        id: String,
        #[serde(default)]
        revision: Option<u64>,
    },
    ConnectionDisconnect {
        version: u16,
        request_id: String,
        id: String,
        #[serde(default)]
        revision: Option<u64>,
    },
    ConnectionRevoke {
        version: u16,
        request_id: String,
        id: String,
        #[serde(default)]
        revision: Option<u64>,
    },
    ConnectionRevokeScope {
        version: u16,
        request_id: String,
        id: String,
        scope: String,
        #[serde(default)]
        revision: Option<u64>,
    },
    ConnectionRemove {
        version: u16,
        request_id: String,
        id: String,
        #[serde(default)]
        revision: Option<u64>,
    },
    ConnectionTrustTools {
        version: u16,
        request_id: String,
        id: String,
        tools: Vec<String>,
        #[serde(default)]
        revision: Option<u64>,
    },
    ConnectionCall {
        version: u16,
        request_id: String,
        id: String,
        operation: String,
        args: serde_json::Value,
        #[serde(default)]
        revision: Option<u64>,
    },
    ConnectionSetToken {
        version: u16,
        request_id: String,
        id: String,
        token: crate::secrets::SecretKey,
        #[serde(default)]
        revision: Option<u64>,
    },
    RegistryPlan {
        version: u16,
        request_id: String,
        purpose: String,
    },
    RegistryAllowVisual {
        version: u16,
        request_id: String,
        purpose: String,
        enabled: bool,
        #[serde(default)]
        revision: Option<u64>,
    },
}
impl<'de> Deserialize<'de> for Request {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let (version, request_id, operation) = match WireRequest::deserialize(d)? {
            WireRequest::HubBegin {
                version,
                request_id,
                revision,
                plugin_id,
                manifest_sha256,
            } => (
                version,
                request_id,
                Operation::HubBegin {
                    revision,
                    plugin_id,
                    manifest_sha256,
                },
            ),
            WireRequest::HubChunk {
                version,
                request_id,
                import_id,
                offset,
                hex,
            } => (
                version,
                request_id,
                Operation::HubChunk {
                    import_id,
                    offset,
                    hex,
                },
            ),
            WireRequest::HubFinish {
                version,
                request_id,
                import_id,
            } => (version, request_id, Operation::HubFinish { import_id }),
            WireRequest::HubAbort {
                version,
                request_id,
                import_id,
            } => (version, request_id, Operation::HubAbort { import_id }),
            WireRequest::HubApprove {
                version,
                request_id,
                revision,
                plugin_id,
                manifest_sha256,
                permissions,
                publisher_unverified_ack,
            } => (
                version,
                request_id,
                Operation::HubApprove {
                    revision,
                    plugin_id,
                    manifest_sha256,
                    permissions,
                    publisher_unverified_ack,
                },
            ),
            WireRequest::HubInstall {
                version,
                request_id,
                revision,
                plugin_id,
                manifest_sha256,
            } => (
                version,
                request_id,
                Operation::HubInstall {
                    revision,
                    plugin_id,
                    manifest_sha256,
                },
            ),
            WireRequest::HubRollback {
                version,
                request_id,
                revision,
                plugin_id,
            } => (
                version,
                request_id,
                Operation::HubRollback {
                    revision,
                    plugin_id,
                },
            ),
            WireRequest::HubRemove {
                version,
                request_id,
                revision,
                plugin_id,
            } => (
                version,
                request_id,
                Operation::HubRemove {
                    revision,
                    plugin_id,
                },
            ),
            WireRequest::HubDiscardStaged {
                version,
                request_id,
                revision,
                plugin_id,
            } => (
                version,
                request_id,
                Operation::HubDiscardStaged {
                    revision,
                    plugin_id,
                },
            ),
            WireRequest::FeedbackPreferences {
                version,
                request_id,
                revision,
                visual_feedback,
                output_volume_percent,
            } => (
                version,
                request_id,
                Operation::FeedbackPreferences {
                    revision,
                    visual_feedback,
                    output_volume_percent,
                },
            ),
            WireRequest::SelectWake {
                version,
                request_id,
                revision,
                phrase_id,
            } => (
                version,
                request_id,
                Operation::SelectWake {
                    revision,
                    phrase_id,
                },
            ),
            WireRequest::SelectWakePhrases {
                version,
                request_id,
                revision,
                phrases,
                acknowledge_untested,
            } => (
                version,
                request_id,
                Operation::SelectWakePhrases {
                    revision,
                    phrases,
                    acknowledge_untested,
                },
            ),
            WireRequest::WakePhraseValidate {
                version,
                request_id,
                text,
            } => (version, request_id, Operation::WakePhraseValidate { text }),
            WireRequest::WakePhraseAdd {
                version,
                request_id,
                revision,
                text,
            } => (
                version,
                request_id,
                Operation::WakePhraseAdd { revision, text },
            ),
            WireRequest::WakePhraseRemove {
                version,
                request_id,
                revision,
                id,
            } => (
                version,
                request_id,
                Operation::WakePhraseRemove { revision, id },
            ),
            WireRequest::WakePhraseTest {
                version,
                request_id,
                id,
            } => (version, request_id, Operation::WakePhraseTest { id }),
            WireRequest::LanguagePreference {
                version,
                request_id,
                revision,
                stt_languages,
                tts_language,
                tts_voice,
            } => (
                version,
                request_id,
                Operation::LanguagePreference {
                    revision,
                    stt_languages,
                    tts_language,
                    tts_voice,
                },
            ),
            WireRequest::LiveAudioPreference {
                version,
                request_id,
                revision,
                enabled,
                confirmed,
            } => (
                version,
                request_id,
                Operation::LiveAudioPreference {
                    revision,
                    enabled,
                    confirmed,
                },
            ),
            WireRequest::RecoverConfiguration {
                version,
                request_id,
                revision,
            } => (
                version,
                request_id,
                Operation::RecoverConfiguration { revision },
            ),
            WireRequest::Preferences {
                version,
                request_id,
                revision,
                audible_feedback,
                session_timeout_ms,
                wake_sensitivity,
                audio_input_device,
                audio_output_device,
            } => (
                version,
                request_id,
                Operation::Preferences {
                    revision,
                    audible_feedback,
                    session_timeout_ms,
                    wake_sensitivity,
                    audio_input_device,
                    audio_output_device,
                },
            ),
            WireRequest::RollbackPreferences {
                version,
                request_id,
                revision,
            } => (
                version,
                request_id,
                Operation::RollbackPreferences { revision },
            ),
            WireRequest::PreferencesRestoreDefaults {
                version,
                request_id,
                revision,
            } => (
                version,
                request_id,
                Operation::PreferencesRestoreDefaults { revision },
            ),
            WireRequest::Snapshot {
                version,
                request_id,
            } => (version, request_id, Operation::Snapshot),
            WireRequest::AudioDevices {
                version,
                request_id,
            } => (version, request_id, Operation::AudioDevices),
            WireRequest::CoreRestart {
                version,
                request_id,
            } => (version, request_id, Operation::CoreRestart),
            WireRequest::Text {
                version,
                request_id,
                raw,
            } => (version, request_id, Operation::Text { raw }),
            WireRequest::VirtualWake {
                version,
                request_id,
            } => (version, request_id, Operation::VirtualWake),
            WireRequest::Cancel {
                version,
                request_id,
                session_id,
            } => (version, request_id, Operation::Cancel { session_id }),
            WireRequest::Action {
                version,
                request_id,
                session_id,
                capability,
            } => (
                version,
                request_id,
                Operation::Action {
                    session_id,
                    capability,
                },
            ),
            WireRequest::PluginEnable {
                version,
                request_id,
                revision,
                plugin_id,
            } => (
                version,
                request_id,
                Operation::PluginEnable {
                    revision,
                    plugin_id,
                },
            ),
            WireRequest::PluginDisable {
                version,
                request_id,
                revision,
                plugin_id,
            } => (
                version,
                request_id,
                Operation::PluginDisable {
                    revision,
                    plugin_id,
                },
            ),
            WireRequest::PluginRevoke {
                version,
                request_id,
                revision,
                plugin_id,
                approval_revision,
            } => (
                version,
                request_id,
                Operation::PluginRevoke {
                    revision,
                    plugin_id,
                    approval_revision,
                },
            ),
            WireRequest::CapabilityInvoke {
                version,
                request_id,
                capability,
                input,
                deadline_ms,
            } => (
                version,
                request_id,
                Operation::CapabilityInvoke {
                    capability,
                    input,
                    deadline_ms,
                },
            ),
            WireRequest::CapabilityCancel {
                version,
                request_id,
                capability,
            } => (
                version,
                request_id,
                Operation::CapabilityCancel { capability },
            ),
            WireRequest::SecretSet {
                version,
                request_id,
                provider,
                key,
            } => (version, request_id, Operation::SecretSet { provider, key }),
            WireRequest::SecretClear {
                version,
                request_id,
                provider,
            } => (version, request_id, Operation::SecretClear { provider }),
            WireRequest::LlmConfigure {
                version,
                request_id,
                revision,
                provider,
                model,
                custom_url,
                local_port,
                fallback,
                cloud_consent,
            } => (
                version,
                request_id,
                Operation::LlmConfigure {
                    revision,
                    provider,
                    model,
                    custom_url,
                    local_port,
                    fallback,
                    cloud_consent,
                },
            ),
            WireRequest::LlmMarkGood {
                version,
                request_id,
                revision,
            } => (version, request_id, Operation::LlmMarkGood { revision }),
            WireRequest::LlmRollback {
                version,
                request_id,
                revision,
            } => (version, request_id, Operation::LlmRollback { revision }),
            WireRequest::PluginSettingsClear {
                version,
                request_id,
                plugin_id,
            } => (
                version,
                request_id,
                Operation::PluginSettingsClear { plugin_id },
            ),
            WireRequest::ToolDecide {
                version,
                request_id,
                proposal_id,
                decision,
            } => (
                version,
                request_id,
                Operation::ToolDecide {
                    proposal_id,
                    decision,
                },
            ),
            WireRequest::AgentStart {
                version,
                request_id,
                goal,
                capability,
            } => (
                version,
                request_id,
                Operation::AgentStart { goal, capability },
            ),
            WireRequest::AgentAbort {
                version,
                request_id,
                run_id,
            } => (version, request_id, Operation::AgentAbort { run_id }),
            WireRequest::AgentTestBump {
                version,
                request_id,
            } => (version, request_id, Operation::AgentTestBump),
            WireRequest::SkillValidate {
                version,
                request_id,
                manifest,
            } => (version, request_id, Operation::SkillValidate { manifest }),
            WireRequest::SkillSaveDraft {
                version,
                request_id,
                manifest,
            } => (version, request_id, Operation::SkillSaveDraft { manifest }),
            WireRequest::SkillDryRun {
                version,
                request_id,
                id,
                skill_version,
                inputs,
            } => (
                version,
                request_id,
                Operation::SkillDryRun {
                    id,
                    version: skill_version,
                    inputs,
                },
            ),
            WireRequest::SkillApprove {
                version,
                request_id,
                id,
                skill_version,
                revision,
            } => (
                version,
                request_id,
                Operation::SkillApprove {
                    id,
                    version: skill_version,
                    revision,
                },
            ),
            WireRequest::SkillEnable {
                version,
                request_id,
                id,
                revision,
            } => (version, request_id, Operation::SkillEnable { id, revision }),
            WireRequest::SkillDisable {
                version,
                request_id,
                id,
                revision,
            } => (
                version,
                request_id,
                Operation::SkillDisable { id, revision },
            ),
            WireRequest::SkillRollback {
                version,
                request_id,
                id,
                revision,
            } => (
                version,
                request_id,
                Operation::SkillRollback { id, revision },
            ),
            WireRequest::SkillRemove {
                version,
                request_id,
                id,
                revision,
            } => (version, request_id, Operation::SkillRemove { id, revision }),
            WireRequest::SkillRun {
                version,
                request_id,
                id,
                inputs,
            } => (version, request_id, Operation::SkillRun { id, inputs }),
            WireRequest::SkillDecide {
                version,
                request_id,
                run_id,
                step,
                decision,
            } => (
                version,
                request_id,
                Operation::SkillDecide {
                    run_id,
                    step,
                    decision,
                },
            ),
            WireRequest::SkillCancel {
                version,
                request_id,
                run_id,
            } => (version, request_id, Operation::SkillCancel { run_id }),
            WireRequest::SkillExport {
                version,
                request_id,
                id,
                skill_version,
            } => (
                version,
                request_id,
                Operation::SkillExport {
                    id,
                    version: skill_version,
                },
            ),
            WireRequest::SkillImport {
                version,
                request_id,
                name,
            } => (version, request_id, Operation::SkillImport { name }),
            WireRequest::SkillImportConfirm {
                version,
                request_id,
                name,
                revision,
            } => (
                version,
                request_id,
                Operation::SkillImportConfirm { name, revision },
            ),
            WireRequest::ConnectionAdd {
                version,
                request_id,
                provider,
                label,
                revision,
            } => (
                version,
                request_id,
                Operation::ConnectionAdd {
                    provider,
                    label,
                    revision,
                },
            ),
            WireRequest::ConnectionConnect {
                version,
                request_id,
                id,
                revision,
            } => (
                version,
                request_id,
                Operation::ConnectionConnect { id, revision },
            ),
            WireRequest::ConnectionConsent {
                version,
                request_id,
                id,
                scopes,
                revision,
            } => (
                version,
                request_id,
                Operation::ConnectionConsent {
                    id,
                    scopes,
                    revision,
                },
            ),
            WireRequest::ConnectionRefresh {
                version,
                request_id,
                id,
                revision,
            } => (
                version,
                request_id,
                Operation::ConnectionRefresh { id, revision },
            ),
            WireRequest::ConnectionDisconnect {
                version,
                request_id,
                id,
                revision,
            } => (
                version,
                request_id,
                Operation::ConnectionDisconnect { id, revision },
            ),
            WireRequest::ConnectionRevoke {
                version,
                request_id,
                id,
                revision,
            } => (
                version,
                request_id,
                Operation::ConnectionRevoke { id, revision },
            ),
            WireRequest::ConnectionRevokeScope {
                version,
                request_id,
                id,
                scope,
                revision,
            } => (
                version,
                request_id,
                Operation::ConnectionRevokeScope {
                    id,
                    scope,
                    revision,
                },
            ),
            WireRequest::ConnectionRemove {
                version,
                request_id,
                id,
                revision,
            } => (
                version,
                request_id,
                Operation::ConnectionRemove { id, revision },
            ),
            WireRequest::ConnectionTrustTools {
                version,
                request_id,
                id,
                tools,
                revision,
            } => (
                version,
                request_id,
                Operation::ConnectionTrustTools {
                    id,
                    tools,
                    revision,
                },
            ),
            WireRequest::ConnectionCall {
                version,
                request_id,
                id,
                operation,
                args,
                revision,
            } => (
                version,
                request_id,
                Operation::ConnectionCall {
                    id,
                    operation,
                    args,
                    revision,
                },
            ),
            WireRequest::ConnectionSetToken {
                version,
                request_id,
                id,
                token,
                revision,
            } => (
                version,
                request_id,
                Operation::ConnectionSetToken {
                    id,
                    token,
                    revision,
                },
            ),
            WireRequest::RegistryPlan {
                version,
                request_id,
                purpose,
            } => (version, request_id, Operation::RegistryPlan { purpose }),
            WireRequest::RegistryAllowVisual {
                version,
                request_id,
                purpose,
                enabled,
                revision,
            } => (
                version,
                request_id,
                Operation::RegistryAllowVisual {
                    purpose,
                    enabled,
                    revision,
                },
            ),
        };
        Ok(Self {
            version,
            request_id,
            operation,
        })
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn schema_rejects_grants_shell_and_unknown_fields() {
        for op in ["snapshot", "virtual_wake"] {
            let json = format!(r#"{{"version":1,"request_id":"a","op":"{op}","grant":true}}"#);
            assert!(serde_json::from_str::<Request>(&json).is_err());
        }
        assert!(
            serde_json::from_str::<Request>(r#"{"version":1,"request_id":"a","op":"shell"}"#)
                .is_err()
        );
    }

    #[test]
    fn core_restart_is_a_bare_strict_operation() {
        let ok = r#"{"version":1,"request_id":"r1","op":"core_restart"}"#;
        let req = serde_json::from_str::<Request>(ok).expect("core_restart parses");
        assert!(matches!(req.operation, Operation::CoreRestart));
        for extra in [r#","force":true"#, r#","revision":1"#] {
            let json = format!(r#"{{"version":1,"request_id":"r1","op":"core_restart"{extra}}}"#);
            assert!(serde_json::from_str::<Request>(&json).is_err(), "{json}");
        }
    }

    #[test]
    fn plugin_settings_clear_wire_format_is_plugin_id_only() {
        let json = r#"{"version":1,"request_id":"p1","op":"plugin_settings_clear","plugin_id":"gideon.calendar"}"#;
        let req = serde_json::from_str::<Request>(json).expect("parses");
        assert!(matches!(
            req.operation,
            Operation::PluginSettingsClear { ref plugin_id } if plugin_id == "gideon.calendar"
        ));
        let with_revision = r#"{"version":1,"request_id":"p1","op":"plugin_settings_clear","plugin_id":"x","revision":1}"#;
        assert!(serde_json::from_str::<Request>(with_revision).is_err());
    }

    #[test]
    fn connection_revoke_scope_wire_format_is_strict() {
        let json = r#"{"version":1,"request_id":"c1","op":"connection_revoke_scope","id":"acc1","scope":"repo:read"}"#;
        let req = serde_json::from_str::<Request>(json).expect("parses without revision");
        assert!(matches!(
            req.operation,
            Operation::ConnectionRevokeScope { ref id, ref scope, revision: None }
                if id == "acc1" && scope == "repo:read"
        ));
        let with_rev = r#"{"version":1,"request_id":"c2","op":"connection_revoke_scope","id":"acc1","scope":"repo:read","revision":3}"#;
        let req = serde_json::from_str::<Request>(with_rev).expect("parses with revision");
        assert!(matches!(
            req.operation,
            Operation::ConnectionRevokeScope {
                revision: Some(3),
                ..
            }
        ));
        let missing_scope =
            r#"{"version":1,"request_id":"c3","op":"connection_revoke_scope","id":"acc1"}"#;
        assert!(serde_json::from_str::<Request>(missing_scope).is_err());
        let extra = r#"{"version":1,"request_id":"c4","op":"connection_revoke_scope","id":"a","scope":"s","token":"x"}"#;
        assert!(serde_json::from_str::<Request>(extra).is_err());
    }
}
