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
    HubApprove {
        revision: u64,
        plugin_id: String,
        manifest_sha256: String,
        permissions: Vec<String>,
        publisher_unverified_ack: bool,
    },
    Snapshot,
    FeedbackPreferences {
        revision: u64,
        visual_feedback: bool,
        output_volume_percent: u8,
    },
    SelectWake {
        revision: u64,
        phrase_id: String,
    },
    RecoverConfiguration {
        revision: u64,
    },
    Preferences {
        revision: u64,
        audible_feedback: bool,
        session_timeout_ms: u64,
    },
    RollbackPreferences {
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
    pub request_id: String,
    pub session_id: Option<u64>,
    pub kind: &'static str,
}

#[derive(Debug, Serialize)]
pub struct Response {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hub: Option<crate::hub::Snapshot>,
    pub base_pack: Option<crate::pack::Snapshot>,
    pub configuration_status: crate::storage::ConfigurationStatus,
    pub configuration_recovery_available: bool,
    pub preferences: crate::storage::Config,
    pub command: Option<crate::commands::Outcome>,
    pub text_input_available: bool,
    pub speech_samples: usize,
    pub speech_status: &'static str,
    pub speech: Option<crate::tts::Summary>,
    pub stt_status: &'static str,
    pub transcript: Option<crate::stt::Transcript>,
    pub capture: Option<crate::capture::CaptureSummary>,
    pub wake_status: &'static str,
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
    HubApprove {
        version: u16,
        request_id: String,
        revision: u64,
        plugin_id: String,
        manifest_sha256: String,
        permissions: Vec<String>,
        publisher_unverified_ack: bool,
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
    },
    RollbackPreferences {
        version: u16,
        request_id: String,
        revision: u64,
    },
    Snapshot {
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
}
impl<'de> Deserialize<'de> for Request {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let (version, request_id, operation) = match WireRequest::deserialize(d)? {
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
            } => (
                version,
                request_id,
                Operation::Preferences {
                    revision,
                    audible_feedback,
                    session_timeout_ms,
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
            WireRequest::Snapshot {
                version,
                request_id,
            } => (version, request_id, Operation::Snapshot),
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
}
