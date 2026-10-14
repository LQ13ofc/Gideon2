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
    Snapshot,
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
    Snapshot {
        version: u16,
        request_id: String,
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
            WireRequest::Snapshot {
                version,
                request_id,
            } => (version, request_id, Operation::Snapshot),
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
