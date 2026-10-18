//! C1.2 tool proposals: fixed registry, strict argument validation and the Core-owned ledger.
//! Model or plugin text never grants authority. Only `REGISTRY` maps a tool name to a
//! `commands::Command`; `commands::authorize` and the sandbox executor still apply.
use crate::commands::{self, Command, Job};
use serde::Serialize;
use serde_json::{Map, Value};
use std::{
    collections::{HashSet, VecDeque},
    time::{Duration, Instant},
};

/// At most this many tool calls are read from one plugin output.
pub const MAX_CALLS: usize = 4;
/// At most this many proposals may wait for a user decision at the same time.
pub const PENDING_LIMIT: usize = 4;
/// Terminal proposals kept for display; the oldest terminal entry is dropped first.
const HISTORY_LIMIT: usize = 8;
/// Production expiry of a pending proposal.
pub const DEFAULT_TTL: Duration = Duration::from_millis(120_000);
const MAX_CALL_ID: usize = 64;
const MAX_TOOL_NAME: usize = 64;
const MAX_DESKTOP_ID: usize = 128;
const DESKTOP_SUFFIX: &str = ".desktop";

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Risk {
    /// Serialized as `read` in agent snapshots (the bridge and the Qt labels use that name).
    #[serde(rename = "read")]
    ReadOnly,
    StateChanging,
    /// Publication or otherwise irreversible effects: always needs explicit approval.
    Destructive,
}

/// The only tools a model or plugin can ever reach. Adding a row is a Core change.
pub const REGISTRY: [(&str, Risk); 6] = [
    ("open_app", Risk::StateChanging),
    ("set_volume", Risk::StateChanging),
    ("mute", Risk::StateChanging),
    ("get_status", Risk::ReadOnly),
    ("get_time", Risk::ReadOnly),
    ("get_date", Risk::ReadOnly),
];

/// Agent test tools, reachable only under `--agent-synthetic`. They act on the synthetic app.
pub const SYNTHETIC_REGISTRY: [(&str, Risk); 4] = [
    ("synth_screen_read", Risk::ReadOnly),
    ("synth_counter_inc", Risk::StateChanging),
    ("synth_set_text", Risk::StateChanging),
    ("synth_publish", Risk::Destructive),
];

/// C4 bridge: a model tool that maps onto a plugin capability and a synthetic world service.
/// Exists only under `--agent-synthetic`. The owner plugin must run and hold the permission.
pub struct Bridge {
    pub name: &'static str,
    pub risk: Risk,
    pub capability: &'static str,
    pub permission: &'static str,
    pub service: &'static str,
}

/// Argument names of each bridge tool equal the service's exact argument names.
pub const BRIDGE_REGISTRY: [Bridge; 6] = [
    Bridge {
        name: "screen_capture",
        risk: Risk::ReadOnly,
        capability: "screen_observe.capture",
        permission: "screen_observe",
        service: "screen.capture",
    },
    Bridge {
        name: "ui_tree",
        risk: Risk::ReadOnly,
        capability: "computer_control.tree",
        permission: "input_control",
        service: "input.a11y_tree",
    },
    Bridge {
        name: "ui_click",
        risk: Risk::StateChanging,
        capability: "computer_control.act",
        permission: "input_control",
        service: "input.click",
    },
    Bridge {
        name: "ui_type",
        risk: Risk::StateChanging,
        capability: "computer_control.act",
        permission: "input_control",
        service: "input.type",
    },
    Bridge {
        name: "audio_set_route",
        risk: Risk::StateChanging,
        capability: "audio_advanced.act",
        permission: "audio_route",
        service: "audio.set_route",
    },
    Bridge {
        name: "audio_app_volume",
        risk: Risk::StateChanging,
        capability: "audio_advanced.act",
        permission: "audio_route",
        service: "audio.app_volume",
    },
];

/// Bridge entry for a tool name, reachable only when the caller enabled the synthetic registry.
pub fn bridge(name: &str) -> Option<&'static Bridge> {
    BRIDGE_REGISTRY.iter().find(|entry| entry.name == name)
}

pub fn risk(name: &str) -> Option<Risk> {
    REGISTRY
        .iter()
        .find(|(known, _)| *known == name)
        .map(|(_, risk)| *risk)
}

/// Risk of a synthetic tool; `None` unless the synthetic registry is enabled by the caller.
pub fn synthetic_risk(name: &str) -> Option<Risk> {
    SYNTHETIC_REGISTRY
        .iter()
        .find(|(known, _)| *known == name)
        .map(|(_, risk)| *risk)
}

fn exact_keys(args: &Map<String, Value>, keys: &[&str]) -> Result<(), &'static str> {
    if args.len() == keys.len() && keys.iter().all(|key| args.contains_key(*key)) {
        Ok(())
    } else {
        Err("invalid_args")
    }
}

/// `^[A-Za-z0-9][A-Za-z0-9._-]*\.desktop$`, 9..=128 bytes. No path separators.
fn desktop_id_ok(id: &str) -> bool {
    let bytes = id.as_bytes();
    bytes.len() > DESKTOP_SUFFIX.len()
        && bytes.len() <= MAX_DESKTOP_ID
        && id.ends_with(DESKTOP_SUFFIX)
        && bytes[0].is_ascii_alphanumeric()
        && bytes
            .iter()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'))
}

/// Maps a model tool call to a Command. Exact name, exact keys, typed and ranged values,
/// then the same `commands::authorize` used by Base commands. Errors are snake_case codes.
pub fn command(name: &str, args: &Value) -> Result<(Command, Risk), &'static str> {
    let risk = risk(name).ok_or("unknown_tool")?;
    let object = args.as_object().ok_or("invalid_args")?;
    let command = match name {
        "open_app" => {
            exact_keys(object, &["desktop_id"])?;
            let id = object["desktop_id"]
                .as_str()
                .filter(|id| desktop_id_ok(id))
                .ok_or("invalid_args")?;
            Command::OpenApp {
                desktop_id: id.to_owned(),
            }
        }
        "set_volume" => {
            exact_keys(object, &["level"])?;
            let level = object["level"]
                .as_u64()
                .filter(|level| *level <= 100)
                .ok_or("invalid_args")?;
            Command::Volume { level: level as u8 }
        }
        "mute" => {
            exact_keys(object, &[])?;
            Command::Mute
        }
        "get_status" => {
            exact_keys(object, &[])?;
            Command::Status
        }
        "get_time" => {
            exact_keys(object, &[])?;
            Command::Time
        }
        "get_date" => {
            exact_keys(object, &[])?;
            Command::Date
        }
        _ => return Err("unknown_tool"),
    };
    commands::authorize(&command)?;
    Ok((command, risk))
}

/// Strict JSON for a raw argument string: a duplicate key anywhere is an error.
/// serde_json's `Value` keeps the last duplicate, so raw text must be checked first.
pub fn parse_strict_args(raw: &str) -> Result<Value, &'static str> {
    struct Strict(Value);
    impl<'de> serde::Deserialize<'de> for Strict {
        fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
            struct V;
            impl<'de> serde::de::Visitor<'de> for V {
                type Value = Value;
                fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
                    f.write_str("strict JSON")
                }
                fn visit_bool<E>(self, v: bool) -> Result<Value, E> {
                    Ok(Value::Bool(v))
                }
                fn visit_i64<E>(self, v: i64) -> Result<Value, E> {
                    Ok(Value::from(v))
                }
                fn visit_u64<E>(self, v: u64) -> Result<Value, E> {
                    Ok(Value::from(v))
                }
                fn visit_f64<E>(self, v: f64) -> Result<Value, E> {
                    Ok(Value::from(v))
                }
                fn visit_str<E>(self, v: &str) -> Result<Value, E> {
                    Ok(Value::from(v))
                }
                fn visit_unit<E>(self) -> Result<Value, E> {
                    Ok(Value::Null)
                }
                fn visit_seq<A: serde::de::SeqAccess<'de>>(
                    self,
                    mut seq: A,
                ) -> Result<Value, A::Error> {
                    let mut items = Vec::new();
                    while let Some(Strict(item)) = seq.next_element()? {
                        items.push(item);
                    }
                    Ok(Value::Array(items))
                }
                fn visit_map<A: serde::de::MapAccess<'de>>(
                    self,
                    mut map: A,
                ) -> Result<Value, A::Error> {
                    let mut object = Map::new();
                    while let Some(key) = map.next_key::<String>()? {
                        if object.contains_key(&key) {
                            return Err(serde::de::Error::custom("duplicate key"));
                        }
                        let Strict(value) = map.next_value()?;
                        object.insert(key, value);
                    }
                    Ok(Value::Object(object))
                }
            }
            d.deserialize_any(V).map(Strict)
        }
    }
    serde_json::from_str::<Strict>(raw)
        .map(|Strict(value)| value)
        .map_err(|_| "invalid_args")
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum State {
    Pending,
    Denied,
    Authorized,
    Executed,
    Failed,
    Expired,
    Cancelled,
}

impl State {
    fn terminal(self) -> bool {
        !matches!(self, State::Pending | State::Authorized)
    }
}

/// Public proposal view. Contains model-chosen arguments, never job ids, receipts or secrets.
#[derive(Clone, Debug, Serialize)]
pub struct View {
    pub proposal_id: String,
    pub plugin_id: String,
    pub call_id: String,
    pub tool: String,
    pub args: Value,
    pub state: State,
    pub reason: Option<&'static str>,
    pub result: Option<String>,
    /// Set only for proposals created by an agent run (C3).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub run_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub step: Option<u32>,
    /// `connection` for S5 operation proposals; their owner is the Core, not a plugin.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub kind: Option<&'static str>,
}

struct Entry {
    view: View,
    created: Instant,
    seq: u64,
}

/// Core-owned proposal state. Plugins reach it only through Core ingestion methods.
pub struct Ledger {
    epoch: u64,
    sequence: u64,
    ttl: Duration,
    enabled: bool,
    entries: VecDeque<Entry>,
    queued: Option<(String, Job)>,
    running: Option<(String, Job)>,
}

impl Default for Ledger {
    fn default() -> Self {
        Self {
            epoch: 0,
            sequence: 0,
            ttl: DEFAULT_TTL,
            enabled: false,
            entries: VecDeque::new(),
            queued: None,
            running: None,
        }
    }
}

impl Ledger {
    pub fn set_epoch(&mut self, epoch: u64) {
        self.epoch = epoch;
    }
    pub fn configure(&mut self, ttl: Duration, enabled: bool) {
        self.ttl = ttl;
        self.enabled = enabled;
    }
    pub fn enabled(&self) -> bool {
        self.enabled
    }
    /// One execution at a time: a queued or running job blocks new ones.
    pub fn busy(&self) -> bool {
        self.queued.is_some() || self.running.is_some()
    }
    pub fn view(&self, proposal_id: &str) -> Option<&View> {
        self.entries
            .iter()
            .find(|e| e.view.proposal_id == proposal_id)
            .map(|e| &e.view)
    }
    pub fn snapshot(&self) -> Vec<View> {
        self.entries.iter().map(|e| e.view.clone()).collect()
    }
    /// Expiry deadline of the oldest pending proposal; the transport sleeps until then.
    pub fn deadline(&self) -> Option<Instant> {
        self.entries
            .iter()
            .filter(|e| e.view.state == State::Pending)
            .map(|e| e.created + self.ttl)
            .min()
    }
    pub fn has_pending(&self) -> bool {
        self.entries.iter().any(|e| e.view.state == State::Pending)
    }
    /// Creates a pending entry with a Core-generated, boot-epoch-scoped id.
    pub fn propose(
        &mut self,
        plugin_id: &str,
        call_id: String,
        tool: String,
        args: Value,
        now: Instant,
    ) -> String {
        if self
            .entries
            .iter()
            .filter(|e| e.view.state == State::Pending)
            .count()
            >= PENDING_LIMIT
        {
            if let Some(oldest) = self
                .entries
                .iter_mut()
                .find(|e| e.view.state == State::Pending)
            {
                oldest.view.state = State::Cancelled;
                oldest.view.reason = Some("superseded");
            }
        }
        self.sequence += 1;
        let proposal_id = format!("tool_{:x}_{}", self.epoch, self.sequence);
        self.entries.push_back(Entry {
            view: View {
                proposal_id: proposal_id.clone(),
                plugin_id: plugin_id.to_owned(),
                call_id,
                tool,
                args,
                state: State::Pending,
                reason: None,
                result: None,
                run_id: None,
                step: None,
                kind: None,
            },
            created: now,
            seq: self.sequence,
        });
        while self.entries.len() > HISTORY_LIMIT {
            match self.entries.iter().position(|e| e.view.state.terminal()) {
                Some(index) => {
                    self.entries.remove(index);
                }
                None => break,
            }
        }
        proposal_id
    }
    /// Marks a proposal as a Connection Manager operation (S5). Unknown ids are ignored.
    pub fn set_kind(&mut self, proposal_id: &str, kind: &'static str) {
        if let Some(entry) = self
            .entries
            .iter_mut()
            .find(|e| e.view.proposal_id == proposal_id)
        {
            entry.view.kind = Some(kind);
        }
    }
    /// Marks a proposal as owned by an agent run and step (C3). Unknown ids are ignored.
    pub fn tag(&mut self, proposal_id: &str, run_id: &str, step: u32) {
        if let Some(entry) = self
            .entries
            .iter_mut()
            .find(|e| e.view.proposal_id == proposal_id)
        {
            entry.view.run_id = Some(run_id.to_owned());
            entry.view.step = Some(step);
        }
    }
    pub fn set(
        &mut self,
        proposal_id: &str,
        state: State,
        reason: Option<&'static str>,
        result: Option<String>,
    ) {
        if let Some(entry) = self
            .entries
            .iter_mut()
            .find(|e| e.view.proposal_id == proposal_id)
        {
            entry.view.state = state;
            entry.view.reason = reason;
            entry.view.result = result;
        }
    }
    /// Moves a proposal to the single queue slot; returns false when the slot is taken.
    pub fn queue(&mut self, proposal_id: &str, command: Command) -> bool {
        if self.busy() {
            return false;
        }
        let Some(seq) = self
            .entries
            .iter()
            .find(|e| e.view.proposal_id == proposal_id)
            .map(|e| e.seq)
        else {
            return false;
        };
        self.set(proposal_id, State::Authorized, None, None);
        self.queued = Some((
            proposal_id.to_owned(),
            Job {
                session_id: seq,
                command,
            },
        ));
        true
    }
    /// Moves the queued job into the running slot for the transport to execute.
    pub fn start(&mut self) -> Option<Job> {
        let (id, job) = self.queued.take()?;
        self.running = Some((id, job.clone()));
        Some(job)
    }
    /// Returns the proposal id only if `job` is exactly the running job.
    pub fn finish(&mut self, job: &Job) -> Option<String> {
        match self.running.take() {
            Some((id, running)) if running == *job => Some(id),
            other => {
                self.running = other;
                None
            }
        }
    }
    pub fn expire(&mut self, now: Instant) {
        let ttl = self.ttl;
        for entry in self.entries.iter_mut() {
            if entry.view.state == State::Pending && now >= entry.created + ttl {
                entry.view.state = State::Expired;
                entry.view.reason = Some("expired");
            }
        }
    }
    /// Cancels pending proposals whose plugin is not enabled and running. Connection proposals
    /// have no plugin owner and are kept (their owner is the Core).
    pub fn cancel_unavailable(&mut self, running: &HashSet<String>) {
        for entry in self.entries.iter_mut() {
            if entry.view.kind == Some("connection") {
                continue;
            }
            if entry.view.state == State::Pending && !running.contains(&entry.view.plugin_id) {
                entry.view.state = State::Cancelled;
                entry.view.reason = Some("plugin_unavailable");
            }
        }
    }
}

/// Plugin-side shape check: exactly `id`, `name`, `arguments`. Returns `(call_id, name, args,
/// shape_ok)`; a malformed item becomes a denied proposal, never a silent drop.
pub fn read_call(item: &Value) -> (String, String, Value, bool) {
    let Some(object) = item.as_object() else {
        return (String::new(), String::new(), Value::Null, false);
    };
    let call_id = object
        .get("id")
        .and_then(Value::as_str)
        .filter(|id| {
            !id.is_empty()
                && id.len() <= MAX_CALL_ID
                && id
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
        })
        .unwrap_or("")
        .to_owned();
    let name = object
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or("")
        .chars()
        .take(MAX_TOOL_NAME)
        .collect::<String>();
    let args = object.get("arguments").cloned().unwrap_or(Value::Null);
    let shape_ok = object.len() == 3
        && object.contains_key("id")
        && object.contains_key("name")
        && object.contains_key("arguments");
    (call_id, name, args, shape_ok)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn registry_is_fixed_and_risk_classes_match_the_contract() {
        assert_eq!(risk("get_status"), Some(Risk::ReadOnly));
        assert_eq!(risk("get_time"), Some(Risk::ReadOnly));
        assert_eq!(risk("get_date"), Some(Risk::ReadOnly));
        assert_eq!(risk("open_app"), Some(Risk::StateChanging));
        assert_eq!(risk("set_volume"), Some(Risk::StateChanging));
        assert_eq!(risk("mute"), Some(Risk::StateChanging));
        assert_eq!(risk("shell"), None);
        assert_eq!(risk("delete_everything"), None);
    }
    #[test]
    fn strict_args_reject_duplicates_at_any_depth() {
        assert!(parse_strict_args(r#"{"level":5,"level":6}"#).is_err());
        assert!(parse_strict_args(r#"{"a":{"b":1,"b":2}}"#).is_err());
        assert!(parse_strict_args(r#"{"a":[{"b":1,"b":2}]}"#).is_err());
        assert_eq!(
            parse_strict_args(r#"{"level":5}"#).unwrap(),
            serde_json::json!({"level": 5})
        );
    }
    #[test]
    fn unknown_tool_is_checked_before_arguments() {
        assert_eq!(command("shell", &Value::Null).unwrap_err(), "unknown_tool");
        assert_eq!(
            command("open_app ", &serde_json::json!({})).unwrap_err(),
            "unknown_tool"
        );
    }
    #[test]
    fn ledger_ids_are_epoch_scoped_and_unique() {
        let mut ledger = Ledger::default();
        ledger.set_epoch(0xabc);
        let now = Instant::now();
        let a = ledger.propose("p", "c".into(), "mute".into(), Value::Null, now);
        let b = ledger.propose("p", "c".into(), "mute".into(), Value::Null, now);
        assert_eq!(a, "tool_abc_1");
        assert_ne!(a, b);
    }
    #[test]
    fn read_call_marks_extra_keys_and_bad_ids() {
        let (id, name, _, ok) =
            read_call(&serde_json::json!({"id":"c1","name":"mute","arguments":{},"x":1}));
        assert_eq!((id.as_str(), name.as_str(), ok), ("c1", "mute", false));
        let (id, _, _, ok) =
            read_call(&serde_json::json!({"id":"c 1","name":"mute","arguments":{}}));
        assert_eq!((id.as_str(), ok), ("", true));
    }
}
