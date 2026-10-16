//! C0 plugin runtime: manifest declarations, enabled ledger rules, Core-side capability
//! registry (`PluginView`) and the transport-owned sandboxed Python host (`Host`).
//! Declarations never grant authority: approval, install and enable are all re-checked.
use crate::{
    broker::{self, Reply, DEADLINE as BROKER_DEADLINE, MAX_RESPONSE},
    hub::{self, Snapshot},
    llmcfg::{HostAuth, LlmState, NETWORK_PERMISSION},
    storage::{PluginState, Storage},
    transport::bounded_frame,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::{BTreeMap, HashMap, HashSet, VecDeque},
    fs, io,
    os::unix::fs::MetadataExt,
    path::{Path, PathBuf},
    process::Stdio,
    time::{Duration, Instant},
};
use tokio::{
    io::{AsyncWriteExt, BufReader},
    process::{Child, ChildStdin, ChildStdout, Command},
    sync::mpsc,
    task::JoinHandle,
};

pub const RUNTIME: &str = "python3_script";
const RESERVED: [&str; 11] = [
    "base", "core", "system", "safety", "llm", "screen", "computer", "audio", "mic", "camera",
    "display",
];
const MAX_PLUGINS: usize = 8;
const MAX_CAPABILITIES: usize = 8;
const MAX_CAPABILITY_LEN: usize = 64;
const MAX_INPUT: usize = 8192;
const MAX_OUTPUT: usize = 8192;
const MAX_DEPTH: usize = 4;
const MAX_LINE: usize = 65536;
const MAX_LOG_TEXT: usize = 200;
const LOG_PER_SECOND: u32 = 10;
const LOG_PER_MINUTE: usize = 20;
const HELLO_DEADLINE: Duration = Duration::from_secs(3);
const GRACE: Duration = Duration::from_secs(1);
const WRITE_DEADLINE: Duration = Duration::from_secs(2);
/// Partial text accumulated per invocation (C1); larger overflow is dropped, never queued.
const MAX_PARTIAL: usize = 16384;
const MAX_PARTIAL_CHUNK: usize = 2048;
const PARTIAL_EVENTS_PER_SECOND: usize = 10;
const MAX_HEADERS: usize = 8;
const MAX_HEADER_VALUE: usize = 256;
pub(crate) const PRLIMIT: &str = "/usr/bin/prlimit";
pub(crate) const BWRAP: &str = "/usr/bin/bwrap";
pub(crate) const MAX_ADDRESS_SPACE: u64 = 512 * 1024 * 1024;
pub(crate) const MAX_CPU_SECONDS: u64 = 30;
pub(crate) const MAX_OPEN_FILES: u64 = 32;
/// RLIMIT_NPROC counts every task of the real uid, so the cap is the current count plus this.
const PROCESS_HEADROOM: u64 = 16;

/// Exact reserved words only (docs/C0.md): `llm_engine` is a legal plugin id, `llm` is not.
/// Callers pass a whole plugin id, or the first dot-separated segment of a capability.
fn reserved(name: &str) -> bool {
    RESERVED.contains(&name)
}
fn capability_shape(c: &str) -> bool {
    let parts: Vec<_> = c.split('.').collect();
    parts.len() >= 2
        && parts.iter().all(|p| {
            !p.is_empty()
                && p.bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
        })
}
/// Catalog-level rules for `runtime` and `capabilities`; any violation quarantines the catalog.
pub(crate) fn valid_declaration(
    plugin_id: &str,
    runtime: Option<&str>,
    capabilities: &[String],
) -> bool {
    if runtime.is_some_and(|r| r != RUNTIME) || reserved(plugin_id) {
        return false;
    }
    if capabilities.is_empty() {
        return true;
    }
    if runtime.is_none() || capabilities.len() > MAX_CAPABILITIES {
        return false;
    }
    let mut seen = HashSet::new();
    capabilities.iter().all(|c| {
        c.len() <= MAX_CAPABILITY_LEN
            && capability_shape(c)
            && c.strip_prefix(plugin_id)
                .and_then(|rest| rest.strip_prefix('.'))
                .is_some()
            && !reserved(c.split('.').next().unwrap_or_default())
            && seen.insert(c)
    })
}
fn depth_ok(value: &Value, depth: usize) -> bool {
    match value {
        Value::Array(items) => depth < MAX_DEPTH && items.iter().all(|v| depth_ok(v, depth + 1)),
        Value::Object(map) => depth < MAX_DEPTH && map.values().all(|v| depth_ok(v, depth + 1)),
        _ => true,
    }
}

/// Immutable launch data for one enabled manifest; all of it is re-verified before spawn.
#[derive(Debug, Clone)]
pub struct Spec {
    pub plugin_id: String,
    pub manifest_sha256: String,
    pub payload_sha256: String,
    pub size: u64,
    pub capabilities: Vec<String>,
}
#[derive(Debug, Clone, Serialize)]
pub struct CapabilityResult {
    pub capability: String,
    pub plugin_id: String,
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<&'static str>,
    pub elapsed_ms: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub partial: Option<String>,
}
#[derive(Debug, Clone, Serialize)]
pub struct PluginItem {
    pub plugin_id: String,
    pub semver: String,
    pub capabilities: Vec<String>,
    pub state: &'static str,
    pub enabled: bool,
    pub restarts: u8,
    pub last_error: Option<&'static str>,
}
#[derive(Debug, Clone, Serialize)]
pub struct PluginSnapshot {
    pub revision: u64,
    pub status: &'static str,
    pub items: Vec<PluginItem>,
}
#[derive(Debug, Clone)]
pub enum Intent {
    Start(Spec),
    Stop {
        plugin_id: String,
    },
    Invoke {
        plugin_id: String,
        invocation: u64,
        capability: String,
        input: Value,
        deadline_ms: u64,
        auth: HostAuth,
    },
    Cancel {
        plugin_id: String,
        invocation: u64,
    },
}
/// Facts reported by the host back to the Core.
#[derive(Debug, Clone)]
pub enum Ev {
    State {
        plugin_id: String,
        state: &'static str,
        restarts: u8,
        error: Option<&'static str>,
    },
    Result {
        plugin_id: String,
        invocation: u64,
        outcome: Result<Value, &'static str>,
        elapsed_ms: u64,
    },
    Partial {
        plugin_id: String,
        invocation: u64,
        text: String,
    },
    Log {
        plugin_id: String,
    },
}
/// Event tagged with the actor generation that produced it; stale generations are dropped.
#[derive(Debug)]
pub struct Wire {
    epoch: u64,
    ev: Ev,
}

#[derive(Debug, Clone)]
struct Runtime {
    state: &'static str,
    restarts: u8,
    last_error: Option<&'static str>,
}
#[derive(Debug, Clone)]
struct Active {
    invocation: u64,
    plugin_id: String,
    capability: String,
    partial: String,
}

/// Core-side authority view. Holds no process handles and never trusts plugin output.
#[derive(Default)]
pub(crate) struct PluginView {
    ledger: PluginState,
    quarantined: bool,
    runtime_available: bool,
    runtimes: BTreeMap<String, Runtime>,
    active: Option<Active>,
    last: Option<CapabilityResult>,
    intents: VecDeque<Intent>,
    events: Vec<&'static str>,
    next_invocation: u64,
    logs: VecDeque<Instant>,
    partial_events: VecDeque<Instant>,
}

fn spec_for(storage: &Storage, hub: &Snapshot, plugin_id: &str) -> Result<Spec, &'static str> {
    let identity = hub::installed_identity(storage, plugin_id)
        .map_err(|_| "plugin_quarantined")?
        .ok_or("not_installed")?;
    let entry = hub
        .entries
        .iter()
        .find(|e| e.plugin_id == plugin_id)
        .ok_or("unknown_plugin")?;
    Ok(Spec {
        plugin_id: plugin_id.to_owned(),
        manifest_sha256: identity.manifest_sha256,
        payload_sha256: identity.payload_sha256,
        size: identity.size,
        capabilities: entry.capabilities.clone(),
    })
}

impl PluginView {
    /// Loads the ledger once at boot. A broken ledger quarantines plugins only.
    pub(crate) fn configure(&mut self, storage: &Storage, runtime_available: bool) {
        self.runtime_available = runtime_available;
        match storage.plugin_state() {
            Ok(ledger) => {
                self.ledger = ledger;
                self.quarantined = false;
            }
            Err(_) => {
                self.ledger = PluginState::default();
                self.quarantined = true;
            }
        }
    }
    pub(crate) fn has_enabled(&self) -> bool {
        !self.ledger.enabled.is_empty()
    }
    fn ready(&self) -> Result<(), &'static str> {
        if self.quarantined {
            Err("plugin_quarantined")
        } else {
            Ok(())
        }
    }
    fn save(&mut self, storage: &Storage, next: PluginState) -> Result<(), &'static str> {
        storage
            .save_plugin_state(&next)
            .map_err(|_| "plugin_storage_error")?;
        self.ledger = next;
        Ok(())
    }
    /// Stops the host task and drops every Core-side claim on `plugin_id`.
    fn stop(&mut self, plugin_id: &str) {
        self.intents.push_back(Intent::Stop {
            plugin_id: plugin_id.to_owned(),
        });
        self.runtimes.remove(plugin_id);
        if self
            .active
            .as_ref()
            .is_some_and(|a| a.plugin_id == plugin_id)
        {
            self.active = None;
        }
        if self.last.as_ref().is_some_and(|l| l.plugin_id == plugin_id) {
            self.last = None;
        }
    }
    fn approved(storage: &Storage, hub: &Snapshot, entry: &crate::hub::Entry) -> bool {
        hub::approval_exact(
            storage,
            hub,
            &entry.plugin_id,
            &entry.manifest_sha256,
            &entry.permissions,
        )
    }
    /// Keeps only enabled plugins whose installed payload, active manifest, runtime and
    /// exact approval still hold. Anything else is stopped and removed from the ledger.
    pub(crate) fn refresh(&mut self, storage: &Storage, hub: Option<&Snapshot>) {
        if self.quarantined || self.ledger.enabled.is_empty() {
            return;
        }
        let mut dropped = vec![];
        for id in &self.ledger.enabled {
            let kept = hub.is_some_and(|hub| {
                hub.status == "verified"
                    && hub.installed.iter().any(|s| {
                        s.plugin_id == *id
                            && s.state == "installed"
                            && hub.entries.iter().any(|e| {
                                e.plugin_id == *id
                                    && e.manifest_sha256 == s.manifest_sha256
                                    && e.runtime.as_deref() == Some(RUNTIME)
                                    && Self::approved(storage, hub, e)
                            })
                    })
            });
            if !kept {
                dropped.push(id.clone());
            }
        }
        if dropped.is_empty() {
            return;
        }
        let mut next = self.ledger.clone();
        next.enabled.retain(|id| !dropped.contains(id));
        next.revision = next.revision.saturating_add(1);
        for id in &dropped {
            self.stop(id);
            self.events.push("plugin_disabled");
        }
        if self.save(storage, next).is_err() {
            // Fail closed: nothing stays enabled if the ledger cannot be written.
            self.quarantined = true;
        }
    }
    /// Boot: refresh, then ask the host to start every enabled plugin without blocking.
    pub(crate) fn boot(&mut self, storage: &Storage, hub: Option<&Snapshot>) {
        self.refresh(storage, hub);
        let Some(hub) = hub.filter(|h| h.status == "verified") else {
            return;
        };
        for id in self.ledger.enabled.clone() {
            match spec_for(storage, hub, &id) {
                Ok(spec) => {
                    self.runtimes.insert(
                        id.clone(),
                        Runtime {
                            state: "starting",
                            restarts: 0,
                            last_error: None,
                        },
                    );
                    self.intents.push_back(Intent::Start(spec));
                }
                Err(code) => {
                    self.runtimes.insert(
                        id.clone(),
                        Runtime {
                            state: "failed",
                            restarts: 0,
                            last_error: Some(code),
                        },
                    );
                }
            }
        }
    }
    pub(crate) fn enable(
        &mut self,
        storage: &Storage,
        hub: &Snapshot,
        revision: u64,
        plugin_id: &str,
    ) -> Result<(), &'static str> {
        self.ready()?;
        if hub.status != "verified" {
            return Err("hub_unavailable");
        }
        if revision != self.ledger.revision {
            return Err("stale_plugin_revision");
        }
        let entry = hub
            .entries
            .iter()
            .find(|e| e.plugin_id == plugin_id)
            .ok_or("unknown_plugin")?;
        let installed = hub
            .installed
            .iter()
            .find(|s| s.plugin_id == plugin_id)
            .ok_or("not_installed")?;
        if installed.state != "installed" {
            return Err("plugin_quarantined");
        }
        if entry.manifest_sha256 != installed.manifest_sha256 {
            return Err("manifest_mismatch");
        }
        if entry.runtime.as_deref() != Some(RUNTIME) {
            return Err("plugin_not_runnable");
        }
        if self.ledger.enabled.iter().any(|id| id == plugin_id) {
            return Err("already_enabled");
        }
        if !self.runtime_available {
            return Err("plugin_not_runnable");
        }
        if !Self::approved(storage, hub, entry) {
            return Err("permissions_not_approved");
        }
        if self.ledger.enabled.len() >= MAX_PLUGINS {
            return Err("plugin_limit_reached");
        }
        let spec = spec_for(storage, hub, plugin_id)?;
        let mut next = self.ledger.clone();
        next.enabled.push(plugin_id.to_owned());
        next.revision = revision.checked_add(1).ok_or("plugin_revision_exhausted")?;
        self.save(storage, next)?;
        self.runtimes.insert(
            plugin_id.to_owned(),
            Runtime {
                state: "starting",
                restarts: 0,
                last_error: None,
            },
        );
        self.intents.push_back(Intent::Start(spec));
        self.events.push("plugin_enabled");
        Ok(())
    }
    pub(crate) fn disable(
        &mut self,
        storage: &Storage,
        revision: u64,
        plugin_id: &str,
    ) -> Result<(), &'static str> {
        self.ready()?;
        if revision != self.ledger.revision {
            return Err("stale_plugin_revision");
        }
        if !self.ledger.enabled.iter().any(|id| id == plugin_id) {
            return Err("not_enabled");
        }
        let mut next = self.ledger.clone();
        next.enabled.retain(|id| id != plugin_id);
        next.revision = revision.checked_add(1).ok_or("plugin_revision_exhausted")?;
        self.save(storage, next)?;
        self.stop(plugin_id);
        self.events.push("plugin_disabled");
        Ok(())
    }
    pub(crate) fn revoke(
        &mut self,
        storage: &Storage,
        hub: &Snapshot,
        revision: u64,
        plugin_id: &str,
    ) -> Result<(), &'static str> {
        self.ready()?;
        if revision != self.ledger.revision {
            return Err("stale_plugin_revision");
        }
        let enabled = self.ledger.enabled.iter().any(|id| id == plugin_id);
        let known = hub.entries.iter().any(|e| e.plugin_id == plugin_id);
        if !enabled && !known {
            return Err("unknown_plugin");
        }
        let removed = hub::revoke_approval(storage, plugin_id)?;
        if !removed && !enabled {
            return Err("permissions_not_approved");
        }
        let mut next = self.ledger.clone();
        next.enabled.retain(|id| id != plugin_id);
        next.revision = revision.checked_add(1).ok_or("plugin_revision_exhausted")?;
        self.save(storage, next)?;
        self.stop(plugin_id);
        self.events.push("plugin_revoked");
        Ok(())
    }
    /// Hub install, rollback or remove changed the active manifest: explicit re-enable needed.
    pub(crate) fn forget(&mut self, storage: &Storage, plugin_id: &str) {
        if !self.ledger.enabled.iter().any(|id| id == plugin_id) {
            return;
        }
        let mut next = self.ledger.clone();
        next.enabled.retain(|id| id != plugin_id);
        next.revision = next.revision.saturating_add(1);
        self.stop(plugin_id);
        self.events.push("plugin_disabled");
        if self.save(storage, next).is_err() {
            self.quarantined = true;
        }
    }
    pub(crate) fn invoke(
        &mut self,
        hub: Option<&Snapshot>,
        capability: &str,
        input: Value,
        deadline_ms: u64,
        llm: &LlmState,
    ) -> Result<(), &'static str> {
        let hub = hub
            .filter(|h| h.status == "verified")
            .ok_or("unknown_capability")?;
        let owner = hub
            .entries
            .iter()
            .find(|e| e.capabilities.iter().any(|c| c == capability))
            .ok_or("unknown_capability")?;
        if self.quarantined
            || !self.ledger.enabled.iter().any(|id| *id == owner.plugin_id)
            || self
                .runtimes
                .get(&owner.plugin_id)
                .is_none_or(|r| r.state != "running")
        {
            return Err("capability_unavailable");
        }
        let object_ok = input.is_object();
        let size_ok = serde_json::to_vec(&input).is_ok_and(|b| b.len() <= MAX_INPUT);
        if !object_ok || !size_ok || !depth_ok(&input, 0) || !(1..=10000).contains(&deadline_ms) {
            return Err("invalid_input");
        }
        if self.active.is_some() {
            return Err("busy");
        }
        self.next_invocation = self.next_invocation.saturating_add(1);
        let invocation = self.next_invocation;
        // Authority for brokered HTTP is fixed per invocation: approved grant plus Core config.
        let permission =
            owner.permissions_approved && owner.permissions.iter().any(|p| p == NETWORK_PERMISSION);
        let auth = llm.host_auth(permission);
        self.active = Some(Active {
            invocation,
            plugin_id: owner.plugin_id.clone(),
            capability: capability.to_owned(),
            partial: String::new(),
        });
        self.last = None;
        self.intents.push_back(Intent::Invoke {
            plugin_id: owner.plugin_id.clone(),
            invocation,
            capability: capability.to_owned(),
            input,
            deadline_ms,
            auth,
        });
        self.events.push("capability_invoked");
        Ok(())
    }
    pub(crate) fn cancel(&mut self, capability: &str) -> Result<(), &'static str> {
        let active = self
            .active
            .as_ref()
            .filter(|a| a.capability == capability)
            .ok_or("stale_invocation")?;
        self.intents.push_back(Intent::Cancel {
            plugin_id: active.plugin_id.clone(),
            invocation: active.invocation,
        });
        Ok(())
    }
    pub(crate) fn event(&mut self, ev: Ev, now: Instant) {
        match ev {
            Ev::State {
                plugin_id,
                state,
                restarts,
                error,
            } => {
                if !self.ledger.enabled.iter().any(|id| *id == plugin_id) {
                    return;
                }
                if matches!(state, "failed" | "stopped")
                    && self
                        .active
                        .as_ref()
                        .is_some_and(|a| a.plugin_id == plugin_id)
                {
                    self.active = None;
                }
                self.runtimes.insert(
                    plugin_id,
                    Runtime {
                        state,
                        restarts,
                        last_error: error,
                    },
                );
                match state {
                    "running" => self.events.push("plugin_started"),
                    "failed" => self.events.push("plugin_failed"),
                    "stopped" => self.events.push("plugin_stopped"),
                    _ => {}
                }
            }
            Ev::Result {
                plugin_id,
                invocation,
                outcome,
                elapsed_ms,
            } => {
                let Some(active) = self
                    .active
                    .as_ref()
                    .filter(|a| a.invocation == invocation && a.plugin_id == plugin_id)
                else {
                    return;
                };
                let capability = active.capability.clone();
                let partial = (!active.partial.is_empty()).then(|| active.partial.clone());
                self.active = None;
                if !self.ledger.enabled.iter().any(|id| *id == plugin_id) {
                    return;
                }
                self.last = Some(match outcome {
                    Ok(output) => CapabilityResult {
                        capability,
                        plugin_id,
                        ok: true,
                        output: Some(output),
                        error: None,
                        elapsed_ms,
                        partial,
                    },
                    Err(code) => CapabilityResult {
                        capability,
                        plugin_id,
                        ok: false,
                        output: None,
                        error: Some(code),
                        elapsed_ms,
                        partial,
                    },
                });
            }
            Ev::Partial {
                plugin_id,
                invocation,
                text,
            } => {
                let Some(active) = self
                    .active
                    .as_mut()
                    .filter(|a| a.invocation == invocation && a.plugin_id == plugin_id)
                else {
                    return;
                };
                if active.partial.len() + text.len() > MAX_PARTIAL {
                    return;
                }
                active.partial.push_str(&text);
                // Event rate is bounded; the accumulated text is not, within the 16 KiB cap.
                while self
                    .partial_events
                    .front()
                    .is_some_and(|t| now.duration_since(*t) >= Duration::from_secs(1))
                {
                    self.partial_events.pop_front();
                }
                if self.partial_events.len() < PARTIAL_EVENTS_PER_SECOND {
                    self.partial_events.push_back(now);
                    self.events.push("capability_partial");
                }
            }
            Ev::Log { .. } => {
                while self
                    .logs
                    .front()
                    .is_some_and(|t| now.duration_since(*t) >= Duration::from_secs(60))
                {
                    self.logs.pop_front();
                }
                if self.logs.len() < LOG_PER_MINUTE {
                    self.logs.push_back(now);
                    self.events.push("plugin_log");
                }
            }
        }
    }
    pub(crate) fn take_events(&mut self) -> Vec<&'static str> {
        std::mem::take(&mut self.events)
    }
    pub(crate) fn take_intents(&mut self) -> Vec<Intent> {
        self.intents.drain(..).collect()
    }
    pub(crate) fn last(&self) -> Option<&CapabilityResult> {
        self.last.as_ref()
    }
    /// Live text of the running invocation, present only while it has produced partials.
    pub(crate) fn partial(&self) -> Option<String> {
        self.active
            .as_ref()
            .filter(|a| !a.partial.is_empty())
            .map(|a| a.partial.clone())
    }
    pub(crate) fn snapshot(&self, hub: Option<&Snapshot>) -> PluginSnapshot {
        let items = hub
            .filter(|h| h.status == "verified")
            .map(|hub| {
                hub.installed
                    .iter()
                    .map(|s| {
                        let enabled = self.ledger.enabled.iter().any(|id| *id == s.plugin_id);
                        let runtime = self.runtimes.get(&s.plugin_id);
                        let state = if s.state != "installed" {
                            "quarantined"
                        } else if enabled {
                            runtime.map_or("starting", |r| r.state)
                        } else {
                            "disabled"
                        };
                        PluginItem {
                            plugin_id: s.plugin_id.clone(),
                            semver: s.semver.clone(),
                            capabilities: hub
                                .entries
                                .iter()
                                .find(|e| e.plugin_id == s.plugin_id)
                                .map(|e| e.capabilities.clone())
                                .unwrap_or_default(),
                            state,
                            enabled,
                            restarts: runtime.map_or(0, |r| r.restarts),
                            last_error: runtime.and_then(|r| r.last_error),
                        }
                    })
                    .collect()
            })
            .unwrap_or_default();
        PluginSnapshot {
            revision: self.ledger.revision,
            status: if self.quarantined {
                "quarantined"
            } else {
                "ok"
            },
            items,
        }
    }
}

// ---------------------------------------------------------------------------
// Transport-owned host: one supervising task per enabled plugin.
// ---------------------------------------------------------------------------

#[derive(Debug)]
enum Cmd {
    Invoke {
        invocation: u64,
        capability: String,
        input: Value,
        deadline_ms: u64,
        auth: HostAuth,
    },
    Cancel {
        invocation: u64,
    },
    Stop,
}
struct Actor {
    epoch: u64,
    commands: mpsc::UnboundedSender<Cmd>,
    task: JoinHandle<()>,
}
pub struct Host {
    python: Option<PathBuf>,
    broker: PathBuf,
    sender: mpsc::UnboundedSender<Wire>,
    actors: HashMap<String, Actor>,
    retired: Vec<JoinHandle<()>>,
    epoch: u64,
}

impl Host {
    pub fn new(
        python: Option<PathBuf>,
        broker: PathBuf,
        sender: mpsc::UnboundedSender<Wire>,
    ) -> Self {
        Self {
            python,
            broker,
            sender,
            actors: HashMap::new(),
            retired: vec![],
            epoch: 0,
        }
    }
    /// Applies a Core intent. Returns events the Core must see immediately.
    pub fn apply(&mut self, intent: Intent, root: &Path) -> Vec<Ev> {
        self.retired.retain(|t| !t.is_finished());
        match intent {
            Intent::Start(spec) => {
                if self.actors.contains_key(&spec.plugin_id) {
                    return vec![];
                }
                let Some(python) = self.python.clone() else {
                    return vec![Ev::State {
                        plugin_id: spec.plugin_id,
                        state: "failed",
                        restarts: 0,
                        error: Some("plugin_not_runnable"),
                    }];
                };
                self.epoch += 1;
                let epoch = self.epoch;
                let (commands, rx) = mpsc::unbounded_channel();
                let ctx = Ctx {
                    root: root.to_path_buf(),
                    python,
                    broker: self.broker.clone(),
                    plugin_id: spec.plugin_id.clone(),
                    manifest_sha256: spec.manifest_sha256,
                    payload_sha256: spec.payload_sha256,
                    size: spec.size,
                    capabilities: spec.capabilities,
                    epoch,
                };
                let task = tokio::spawn(run(ctx, rx, self.sender.clone()));
                self.actors.insert(
                    spec.plugin_id,
                    Actor {
                        epoch,
                        commands,
                        task,
                    },
                );
                vec![]
            }
            Intent::Stop { plugin_id } => {
                if let Some(actor) = self.actors.remove(&plugin_id) {
                    let _ = actor.commands.send(Cmd::Stop);
                    self.retired.push(actor.task);
                }
                vec![]
            }
            Intent::Invoke {
                plugin_id,
                invocation,
                capability,
                input,
                deadline_ms,
                auth,
            } => {
                let sent = self.actors.get(&plugin_id).is_some_and(|a| {
                    a.commands
                        .send(Cmd::Invoke {
                            invocation,
                            capability,
                            input,
                            deadline_ms,
                            auth,
                        })
                        .is_ok()
                });
                if sent {
                    vec![]
                } else {
                    vec![Ev::Result {
                        plugin_id,
                        invocation,
                        outcome: Err("capability_unavailable"),
                        elapsed_ms: 0,
                    }]
                }
            }
            Intent::Cancel {
                plugin_id,
                invocation,
            } => {
                if let Some(actor) = self.actors.get(&plugin_id) {
                    let _ = actor.commands.send(Cmd::Cancel { invocation });
                }
                vec![]
            }
        }
    }
    /// Drops events from retired generations; a terminal state retires its actor.
    pub fn accept(&mut self, wire: Wire) -> Option<Ev> {
        let id = match &wire.ev {
            Ev::State { plugin_id, .. }
            | Ev::Result { plugin_id, .. }
            | Ev::Partial { plugin_id, .. }
            | Ev::Log { plugin_id } => plugin_id.clone(),
        };
        if self.actors.get(&id).is_none_or(|a| a.epoch != wire.epoch) {
            return None;
        }
        if let Ev::State { state, .. } = &wire.ev {
            if matches!(*state, "failed" | "stopped") {
                if let Some(actor) = self.actors.remove(&id) {
                    self.retired.push(actor.task);
                }
            }
        }
        Some(wire.ev)
    }
    /// Shutdown: ask every plugin to stop, then wait at most 5 s per task before aborting.
    pub async fn shutdown(&mut self) {
        for (_, actor) in self.actors.drain() {
            let _ = actor.commands.send(Cmd::Stop);
            self.retired.push(actor.task);
        }
        for task in self.retired.drain(..) {
            let abort = task.abort_handle();
            if tokio::time::timeout(Duration::from_secs(5), task)
                .await
                .is_err()
            {
                abort.abort();
            }
        }
    }
}

struct Ctx {
    root: PathBuf,
    python: PathBuf,
    broker: PathBuf,
    plugin_id: String,
    manifest_sha256: String,
    payload_sha256: String,
    size: u64,
    capabilities: Vec<String>,
    epoch: u64,
}
#[derive(Clone)]
struct Out {
    epoch: u64,
    sender: mpsc::UnboundedSender<Wire>,
    plugin_id: String,
}
impl Out {
    fn send(&self, ev: Ev) {
        let _ = self.sender.send(Wire {
            epoch: self.epoch,
            ev,
        });
    }
    fn state(&self, state: &'static str, restarts: u8, error: Option<&'static str>) {
        self.send(Ev::State {
            plugin_id: self.plugin_id.clone(),
            state,
            restarts,
            error,
        });
    }
    fn partial(&self, invocation: u64, text: String) {
        self.send(Ev::Partial {
            plugin_id: self.plugin_id.clone(),
            invocation,
            text,
        });
    }
    fn result(&self, invocation: u64, outcome: Result<Value, &'static str>, started: Instant) {
        self.send(Ev::Result {
            plugin_id: self.plugin_id.clone(),
            invocation,
            outcome,
            elapsed_ms: started.elapsed().as_millis() as u64,
        });
    }
}

async fn run(
    ctx: Ctx,
    mut commands: mpsc::UnboundedReceiver<Cmd>,
    sender: mpsc::UnboundedSender<Wire>,
) {
    let out = Out {
        epoch: ctx.epoch,
        sender,
        plugin_id: ctx.plugin_id.clone(),
    };
    let mut restarts = 0u8;
    loop {
        let mut session = match Session::start(&ctx).await {
            Ok(session) => session,
            Err(code) => {
                out.state("failed", restarts, Some(code));
                return;
            }
        };
        out.state("running", restarts, None);
        match session.drive(&mut commands, &out).await {
            Exit::Stopped => {
                session.shutdown().await;
                out.state("stopped", restarts, None);
                return;
            }
            Exit::Crashed => {
                session.kill().await;
                if restarts == 0 {
                    restarts = 1;
                    out.state("starting", restarts, Some("plugin_crashed"));
                    continue;
                }
                out.state("failed", restarts, Some("plugin_crashed"));
                return;
            }
            Exit::Violation(code) => {
                session.kill().await;
                out.state("failed", restarts, Some(code));
                return;
            }
        }
    }
}

enum Line {
    Frame(Vec<u8>),
    Closed,
    Invalid,
}
enum Exit {
    Stopped,
    Crashed,
    Violation(&'static str),
}
struct Pending {
    wire_id: u64,
    invocation: u64,
    started: Instant,
    deadline: Instant,
    grace: Option<Instant>,
    partial: String,
}
/// One brokered `llm.http` call. The broker process is killed on every exit path.
struct HostCall {
    id: u64,
    child: Child,
    replies: mpsc::UnboundedReceiver<Reply>,
    reader: JoinHandle<()>,
    deadline: Instant,
    received: usize,
}
impl HostCall {
    fn abandon(self) {
        self.reader.abort();
        retire(self.child);
    }
}
/// Kills a child that Core no longer needs and reaps it in the background (no zombies).
fn retire(mut child: Child) {
    let _ = child.start_kill();
    tokio::spawn(async move {
        let _ = child.wait().await;
    });
}
struct Session {
    child: Child,
    stdin: ChildStdin,
    lines: mpsc::UnboundedReceiver<Line>,
    reader: JoinHandle<()>,
    next_id: u64,
    pending: Option<Pending>,
    log_window: (Instant, u32),
    python: PathBuf,
    broker: PathBuf,
    auth: HostAuth,
    host: Option<HostCall>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct HelloReply {
    v: u16,
    id: u64,
    ok: bool,
    plugin_id: String,
    api: u16,
    capabilities: Vec<String>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReplyLine {
    #[serde(default)]
    v: Option<u16>,
    id: u64,
    ok: bool,
    #[serde(default)]
    output: Option<Value>,
    #[serde(default)]
    error: Option<String>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct LogLine {
    event: String,
    level: String,
    text: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PartialLine {
    event: String,
    id: u64,
    text: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct HostCallLine {
    op: String,
    #[serde(default)]
    v: Option<u16>,
    id: u64,
    service: String,
    args: HostArgs,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct HostArgs {
    path: String,
    body: Value,
    stream: bool,
    /// Accepted for compatibility and always dropped: Core sets every broker header itself.
    #[serde(default)]
    headers: Option<BTreeMap<String, String>>,
}
fn host_error_frame(id: u64, code: &str, status: Option<u16>) -> Value {
    let mut frame = serde_json::json!({"v": 1, "op": "host_reply", "id": id, "error": code});
    if let Some(status) = status {
        frame["status"] = serde_json::json!(status);
    }
    frame
}
/// Resolves the next broker line; a dropped broker reads as `Closed`.
async fn next_reply(host: &mut Option<HostCall>) -> Reply {
    match host.as_mut() {
        Some(call) => call.replies.recv().await.unwrap_or(Reply::Closed),
        None => std::future::pending().await,
    }
}

async fn read_lines(stdout: ChildStdout, tx: mpsc::UnboundedSender<Line>) {
    let mut reader = BufReader::new(stdout);
    loop {
        let line = match bounded_frame(&mut reader, MAX_LINE).await {
            Ok(Some(mut bytes)) => {
                if bytes.last() == Some(&b'\n') {
                    bytes.pop();
                }
                Line::Frame(bytes)
            }
            // Oversize lines are protocol violations; EOF or I/O errors mean the plugin closed.
            Err(error) if error.kind() == io::ErrorKind::InvalidData => Line::Invalid,
            Ok(None) | Err(_) => Line::Closed,
        };
        let terminal = !matches!(line, Line::Frame(_));
        if tx.send(line).is_err() || terminal {
            return;
        }
    }
}

pub(crate) fn resolve_interpreter(python: &Path) -> PathBuf {
    match fs::read_link(python) {
        Ok(target) if target.is_relative() => {
            python.parent().unwrap_or(Path::new("/")).join(target)
        }
        Ok(target) => target,
        Err(_) => python.to_path_buf(),
    }
}

/// Process count of the real uid (threads included, as RLIMIT_NPROC counts them) plus headroom.
fn process_budget() -> u64 {
    // SAFETY: getuid has no preconditions and does not change process state.
    let uid = unsafe { libc::getuid() };
    let mut tasks = 0u64;
    if let Ok(entries) = fs::read_dir("/proc") {
        for entry in entries.flatten() {
            let name = entry.file_name();
            if !name.to_string_lossy().bytes().all(|b| b.is_ascii_digit()) {
                continue;
            }
            let path = entry.path();
            if fs::metadata(&path).is_ok_and(|m| m.uid() == uid) {
                tasks += fs::read_dir(path.join("task")).map_or(0, |t| t.count() as u64);
            }
        }
    }
    tasks + PROCESS_HEADROOM
}

/// Sandboxed command: prlimit sets the rlimits, then bwrap runs `python -I /plugin/main.py`
/// with no network, no user home, no repo, a private /tmp and a read-only payload.
pub(crate) fn sandbox_command(
    python: &Path,
    payload: &Path,
    processes: u64,
) -> io::Result<Command> {
    if !python.is_absolute() || !payload.is_absolute() {
        return Err(io::Error::other("absolute paths required"));
    }
    let interpreter = resolve_interpreter(python);
    let runtime = interpreter
        .parent()
        .and_then(Path::parent)
        .ok_or_else(|| io::Error::other("python runtime missing"))?;
    let canonical = fs::canonicalize(runtime)?;
    let mut command = Command::new(PRLIMIT);
    command
        .env_clear()
        .arg(format!("--as={MAX_ADDRESS_SPACE}"))
        .arg(format!("--cpu={MAX_CPU_SECONDS}"))
        .arg(format!("--nofile={MAX_OPEN_FILES}"))
        .arg(format!("--nproc={processes}"))
        .arg("--")
        .arg(BWRAP)
        .args([
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--clearenv",
            "--ro-bind",
            "/usr",
            "/usr",
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib",
            "/lib64",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
        ])
        .arg("--ro-bind")
        .arg(&canonical)
        .arg(&canonical)
        .arg("--ro-bind")
        .arg(runtime)
        .arg(runtime)
        .arg("--ro-bind")
        .arg(payload)
        .arg("/plugin/main.py")
        // bwrap's root is a writable tmpfs; make it read-only after all mount points exist.
        .args(["--remount-ro", "/", "--chdir", "/tmp", "--"])
        .arg(&interpreter)
        .args(["-I", "/plugin/main.py"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .kill_on_drop(true);
    Ok(command)
}

impl Session {
    async fn start(ctx: &Ctx) -> Result<Session, &'static str> {
        let payload = hub::verified_payload_path(
            &ctx.root,
            &ctx.plugin_id,
            &ctx.manifest_sha256,
            ctx.size,
            &ctx.payload_sha256,
        )
        .map_err(|_| "plugin_quarantined")?;
        let mut command = sandbox_command(&ctx.python, &payload, process_budget())
            .map_err(|_| "plugin_not_runnable")?;
        let mut child = command.spawn().map_err(|_| "plugin_start_failed")?;
        let (Some(stdin), Some(stdout)) = (child.stdin.take(), child.stdout.take()) else {
            let _ = child.kill().await;
            return Err("plugin_start_failed");
        };
        let (tx, lines) = mpsc::unbounded_channel();
        let reader = tokio::spawn(read_lines(stdout, tx));
        let mut session = Session {
            child,
            stdin,
            lines,
            reader,
            next_id: 2,
            pending: None,
            log_window: (Instant::now(), 0),
            python: ctx.python.clone(),
            broker: ctx.broker.clone(),
            auth: HostAuth::default(),
            host: None,
        };
        let hello = serde_json::json!({"v": 1, "id": 1, "op": "hello", "plugin_id": ctx.plugin_id});
        let verdict = async {
            session
                .write(&hello)
                .await
                .map_err(|_| "plugin_start_failed")?;
            match tokio::time::timeout(HELLO_DEADLINE, session.lines.recv()).await {
                Err(_) => Err("handshake_timeout"),
                Ok(None) | Ok(Some(Line::Closed)) => Err("plugin_start_failed"),
                Ok(Some(Line::Invalid)) => Err("plugin_output_invalid"),
                Ok(Some(Line::Frame(bytes))) => check_hello(&bytes, ctx),
            }
        }
        .await;
        match verdict {
            Ok(()) => Ok(session),
            Err(code) => {
                session.kill().await;
                Err(code)
            }
        }
    }
    async fn write(&mut self, value: &Value) -> io::Result<()> {
        let mut bytes = serde_json::to_vec(value)?;
        bytes.push(b'\n');
        tokio::time::timeout(WRITE_DEADLINE, async {
            self.stdin.write_all(&bytes).await?;
            self.stdin.flush().await
        })
        .await
        .map_err(io::Error::other)?
    }
    async fn drive(&mut self, commands: &mut mpsc::UnboundedReceiver<Cmd>, out: &Out) -> Exit {
        loop {
            let wake = self.pending.as_ref().map(|p| p.grace.unwrap_or(p.deadline));
            let host_deadline = self.host.as_ref().map(|h| h.deadline);
            tokio::select! {
                line = self.lines.recv() => match line {
                    Some(Line::Frame(bytes)) => {
                        if let Err(exit) = self.frame(&bytes, out).await {
                            return exit;
                        }
                    }
                    Some(Line::Invalid) => return self.violation(out, "plugin_output_invalid"),
                    Some(Line::Closed) | None => {
                        self.fail_pending(out, "plugin_error");
                        return Exit::Crashed;
                    }
                },
                command = commands.recv() => match command {
                    Some(Cmd::Invoke { invocation, capability, input, deadline_ms, auth }) => {
                        if let Err(exit) = self.invoke(out, invocation, &capability, input, deadline_ms, auth).await {
                            return exit;
                        }
                    }
                    Some(Cmd::Cancel { invocation }) => {
                        if let Err(exit) = self.cancel(out, invocation).await {
                            return exit;
                        }
                    }
                    Some(Cmd::Stop) | None => return Exit::Stopped,
                },
                reply = next_reply(&mut self.host), if self.host.is_some() => {
                    if let Err(exit) = self.broker_reply(reply).await {
                        return exit;
                    }
                },
                _ = sleep_until(host_deadline), if host_deadline.is_some() => {
                    if let Some(call) = self.host.take() {
                        let id = call.id;
                        call.abandon();
                        if let Err(exit) = self.host_error(id, "timeout", None).await {
                            return exit;
                        }
                    }
                },
                _ = sleep_until(wake) => {
                    let Some(pending) = self.pending.as_mut() else { continue };
                    if pending.grace.is_some() {
                        // The plugin ignored cancellation past the grace period: treat as a crash.
                        return Exit::Crashed;
                    }
                    pending.grace = Some(Instant::now() + GRACE);
                    let (wire_id, invocation, started) = (pending.wire_id, pending.invocation, pending.started);
                    self.stop_host();
                    out.result(invocation, Err("capability_timeout"), started);
                    let cancel = serde_json::json!({"v": 1, "op": "cancel", "id": wire_id});
                    if self.write(&cancel).await.is_err() {
                        return Exit::Crashed;
                    }
                }
            }
        }
    }
    fn fail_pending(&mut self, out: &Out, code: &'static str) {
        if let Some(p) = self.pending.take() {
            if p.grace.is_none() {
                out.result(p.invocation, Err(code), p.started);
            }
        }
    }
    fn violation(&mut self, out: &Out, code: &'static str) -> Exit {
        self.fail_pending(out, code);
        Exit::Violation(code)
    }
    async fn invoke(
        &mut self,
        out: &Out,
        invocation: u64,
        capability: &str,
        input: Value,
        deadline_ms: u64,
        auth: HostAuth,
    ) -> Result<(), Exit> {
        let started = Instant::now();
        if self.pending.is_some() {
            out.result(invocation, Err("busy"), started);
            return Ok(());
        }
        let wire_id = self.next_id;
        self.next_id += 1;
        let mut message = serde_json::json!({
            "v": 1,
            "id": wire_id,
            "op": "invoke",
            "capability": capability,
            "input": input,
            "deadline_ms": deadline_ms,
        });
        // Config is visible to plugins as context only; the key and URL never are.
        if let Some(provider) = auth.provider {
            message["ctx"] = serde_json::json!({"llm": {
                "provider": provider.as_str(),
                "model": auth.model.clone().unwrap_or_default(),
            }});
        }
        self.auth = auth;
        if self.write(&message).await.is_err() {
            out.result(invocation, Err("plugin_error"), started);
            return Err(Exit::Crashed);
        }
        self.pending = Some(Pending {
            wire_id,
            invocation,
            started,
            deadline: started + Duration::from_millis(deadline_ms),
            grace: None,
            partial: String::new(),
        });
        Ok(())
    }
    async fn cancel(&mut self, out: &Out, invocation: u64) -> Result<(), Exit> {
        let Some(pending) = self.pending.as_mut() else {
            return Ok(());
        };
        if pending.invocation != invocation || pending.grace.is_some() {
            return Ok(());
        }
        pending.grace = Some(Instant::now() + GRACE);
        let (wire_id, started) = (pending.wire_id, pending.started);
        self.stop_host();
        out.result(invocation, Err("invoke_cancelled"), started);
        let cancel = serde_json::json!({"v": 1, "op": "cancel", "id": wire_id});
        if self.write(&cancel).await.is_err() {
            return Err(Exit::Crashed);
        }
        Ok(())
    }
    async fn frame(&mut self, bytes: &[u8], out: &Out) -> Result<(), Exit> {
        let Ok(value) = serde_json::from_slice::<Value>(bytes) else {
            return Err(self.violation(out, "plugin_output_invalid"));
        };
        if value.get("event").and_then(Value::as_str) == Some("partial") {
            return self.on_partial(value, out);
        }
        if value.get("op").is_some() {
            return self.host_call(value, out).await;
        }
        if value.get("event").is_some() {
            let Ok(log) = serde_json::from_value::<LogLine>(value) else {
                return Err(self.violation(out, "plugin_output_invalid"));
            };
            if log.event != "log"
                || !matches!(log.level.as_str(), "info" | "warn" | "error")
                || log.text.len() > MAX_LOG_TEXT
                || log.text.chars().any(char::is_control)
            {
                return Err(self.violation(out, "plugin_output_invalid"));
            }
            let now = Instant::now();
            if now.duration_since(self.log_window.0) >= Duration::from_secs(1) {
                self.log_window = (now, 0);
            }
            // Over the per-second budget logs are dropped silently, never queued.
            if self.log_window.1 < LOG_PER_SECOND {
                self.log_window.1 += 1;
                out.send(Ev::Log {
                    plugin_id: out.plugin_id.clone(),
                });
            }
            return Ok(());
        }
        let Ok(reply) = serde_json::from_value::<ReplyLine>(value) else {
            return Err(self.violation(out, "plugin_output_invalid"));
        };
        let matches_pending = self.pending.as_ref().is_some_and(|p| p.wire_id == reply.id);
        if !matches_pending || reply.v.is_some_and(|v| v != 1) {
            // Unsolicited, duplicate or foreign ids are protocol violations.
            return Err(self.violation(out, "plugin_output_invalid"));
        }
        let outcome = if reply.ok {
            match reply
                .output
                .filter(|_| reply.error.is_none())
                .and_then(bounded_object)
            {
                Some(output) => Ok(output),
                None => return Err(self.violation(out, "plugin_output_invalid")),
            }
        } else {
            match (&reply.output, &reply.error) {
                (None, Some(code)) if valid_code(code) => Err("plugin_error"),
                _ => return Err(self.violation(out, "plugin_output_invalid")),
            }
        };
        let Some(pending) = self.pending.take() else {
            return Ok(());
        };
        self.stop_host();
        // A reply after cancel or timeout was already reported; it is dropped.
        if pending.grace.is_none() {
            out.result(pending.invocation, outcome, pending.started);
        }
        Ok(())
    }
    async fn shutdown(mut self) {
        self.stop_host();
        let id = self.next_id;
        let _ = self
            .write(&serde_json::json!({"v": 1, "id": id, "op": "shutdown"}))
            .await;
        if tokio::time::timeout(Duration::from_secs(1), self.child.wait())
            .await
            .is_err()
        {
            let _ = self.child.kill().await;
        }
        self.reader.abort();
    }
    async fn kill(mut self) {
        self.stop_host();
        let _ = self.child.kill().await;
        self.reader.abort();
    }
    fn stop_host(&mut self) {
        if let Some(call) = self.host.take() {
            call.abandon();
        }
    }
    /// Partial text from a running invocation: bounded per line and in total, never queued.
    fn on_partial(&mut self, value: Value, out: &Out) -> Result<(), Exit> {
        let Ok(line) = serde_json::from_value::<PartialLine>(value) else {
            return Err(self.violation(out, "plugin_output_invalid"));
        };
        let current = self
            .pending
            .as_ref()
            .map(|p| (p.wire_id, p.invocation, p.grace.is_some()));
        let Some((wire_id, invocation, cancelled)) = current else {
            return Err(self.violation(out, "plugin_output_invalid"));
        };
        if line.event != "partial" || line.id != wire_id || line.text.len() > MAX_PARTIAL_CHUNK {
            return Err(self.violation(out, "plugin_output_invalid"));
        }
        if cancelled {
            return Ok(());
        }
        if let Some(pending) = self.pending.as_mut() {
            if pending.partial.len() + line.text.len() <= MAX_PARTIAL {
                pending.partial.push_str(&line.text);
                out.partial(invocation, line.text);
            }
        }
        Ok(())
    }
    /// The Core-side gate for `llm.http`, evaluated against this invocation's snapshot.
    fn authorize(&self) -> Result<broker::Target, &'static str> {
        let auth = &self.auth;
        if !auth.permission {
            return Err("permission_denied");
        }
        if auth.provider.is_none() {
            return Err("provider_not_configured");
        }
        if auth.key.is_none() {
            return Err("key_missing");
        }
        let target = broker::target(auth)?;
        // Loopback is exempt from cloud consent only in the explicit test mode.
        let exempt = target.loopback && auth.allow_loopback;
        if !auth.cloud_consent && !exempt {
            return Err("cloud_not_authorized");
        }
        Ok(target)
    }
    async fn host_error(
        &mut self,
        id: u64,
        code: &'static str,
        status: Option<u16>,
    ) -> Result<(), Exit> {
        self.write(&host_error_frame(id, code, status))
            .await
            .map_err(|_| Exit::Crashed)
    }
    /// Plugin `host_call`: strict shape, one active call, Core gate, then the sandboxed broker.
    async fn host_call(&mut self, value: Value, out: &Out) -> Result<(), Exit> {
        let Ok(line) = serde_json::from_value::<HostCallLine>(value) else {
            return Err(self.violation(out, "plugin_output_invalid"));
        };
        let cancelled = match self.pending.as_ref() {
            Some(pending) => pending.grace.is_some(),
            None => return Err(self.violation(out, "plugin_output_invalid")),
        };
        let oversized_headers = line.args.headers.as_ref().is_some_and(|h| {
            h.len() > MAX_HEADERS || h.values().any(|v| v.len() > MAX_HEADER_VALUE)
        });
        if line.op != "host_call" || line.v.is_some_and(|v| v != 1) || oversized_headers {
            return Err(self.violation(out, "plugin_output_invalid"));
        }
        let id = line.id;
        let gate = if cancelled {
            Err("cancelled")
        } else if self.host.is_some() {
            Err("busy")
        } else if line.service != "llm.http"
            || line.args.path != broker::CHAT_PATH
            || !line.args.stream
            || !line.args.body.is_object()
        {
            Err("invalid_host_call")
        } else {
            self.authorize()
        };
        let opened = match gate {
            Ok(target) => self.open_broker(id, line.args.body, &target).await,
            Err(code) => Err(code),
        };
        match opened {
            Ok(call) => {
                self.host = Some(call);
                Ok(())
            }
            Err(code) => self.host_error(id, code, None).await,
        }
    }
    async fn open_broker(
        &self,
        id: u64,
        mut body: Value,
        target: &broker::Target,
    ) -> Result<HostCall, &'static str> {
        // The Core, not the plugin, chooses the model and forces streaming.
        body["model"] = serde_json::json!(self.auth.model.clone().unwrap_or_default());
        body["stream"] = serde_json::json!(true);
        let payload = broker::payload(target, &body, &self.auth)?;
        let mut command = broker::command(&self.python, &self.broker, process_budget())
            .map_err(|_| "network_unavailable")?;
        let mut child = command.spawn().map_err(|_| "network_unavailable")?;
        let (Some(mut stdin), Some(stdout)) = (child.stdin.take(), child.stdout.take()) else {
            retire(child);
            return Err("network_unavailable");
        };
        let (tx, replies) = mpsc::unbounded_channel();
        let reader = tokio::spawn(broker::read_replies(stdout, tx));
        let written =
            tokio::time::timeout(WRITE_DEADLINE, broker::write_payload(&mut stdin, &payload)).await;
        drop(stdin);
        if !matches!(written, Ok(Ok(()))) {
            reader.abort();
            retire(child);
            return Err("network_unavailable");
        }
        Ok(HostCall {
            id,
            child,
            replies,
            reader,
            deadline: Instant::now() + BROKER_DEADLINE,
            received: 0,
        })
    }
    /// Forwards one broker line to the plugin; any terminal line also retires the broker.
    async fn broker_reply(&mut self, reply: Reply) -> Result<(), Exit> {
        let Some(call) = self.host.as_mut() else {
            return Ok(());
        };
        let id = call.id;
        let frame = match reply {
            Reply::Chunk(text) => {
                call.received = call.received.saturating_add(text.len());
                if call.received > MAX_RESPONSE {
                    self.stop_host();
                    return self.host_error(id, "response_too_large", None).await;
                }
                serde_json::json!({"v": 1, "op": "host_reply", "id": id, "chunk": text})
            }
            Reply::Done(status) => {
                self.stop_host();
                serde_json::json!({"v": 1, "op": "host_reply", "id": id, "done": true, "status": status})
            }
            Reply::Error(code, status) => {
                self.stop_host();
                host_error_frame(id, code, status)
            }
            Reply::Closed => {
                self.stop_host();
                host_error_frame(id, "network_unavailable", None)
            }
        };
        self.write(&frame).await.map_err(|_| Exit::Crashed)
    }
}
/// Plugin output must be a JSON object within the 8 KiB and depth-4 contract.
fn bounded_object(output: Value) -> Option<Value> {
    let fits = output.is_object()
        && depth_ok(&output, 0)
        && serde_json::to_vec(&output).is_ok_and(|b| b.len() <= MAX_OUTPUT);
    fits.then_some(output)
}
fn valid_code(code: &str) -> bool {
    !code.is_empty()
        && code.len() <= 64
        && code.bytes().all(|b| b.is_ascii_lowercase() || b == b'_')
}
fn check_hello(bytes: &[u8], ctx: &Ctx) -> Result<(), &'static str> {
    let reply: HelloReply = serde_json::from_slice(bytes).map_err(|_| "plugin_output_invalid")?;
    if reply.v != 1
        || reply.id != 1
        || !reply.ok
        || reply.plugin_id != ctx.plugin_id
        || reply.api != 1
        || !reply
            .capabilities
            .iter()
            .all(|c| ctx.capabilities.contains(c))
    {
        return Err("handshake_mismatch");
    }
    Ok(())
}
async fn sleep_until(instant: Option<Instant>) {
    match instant {
        Some(at) => tokio::time::sleep_until(tokio::time::Instant::from_std(at)).await,
        None => std::future::pending().await,
    }
}
