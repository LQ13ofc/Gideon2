//! C0 plugin runtime: manifest declarations, enabled ledger rules, Core-side capability
//! registry (`PluginView`) and the transport-owned sandboxed Python host (`Host`).
//! Declarations never grant authority: approval, install and enable are all re-checked.
use crate::{
    broker::{self, Reply, DEADLINE as BROKER_DEADLINE, MAX_RESPONSE},
    hub::{self, Snapshot},
    llmcfg::{Access, HostAuth, LlmState, NETWORK_PERMISSION, SETTINGS_PERMISSION},
    storage::{self, PluginState, Storage},
    transport::bounded_frame,
    world,
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
/// Serialized size of one `settings.put` object (C2); the stored file adds its own envelope.
const MAX_SETTINGS: usize = 8192;
pub(crate) const PRLIMIT: &str = "/usr/bin/prlimit";
pub(crate) const BWRAP: &str = "/usr/bin/bwrap";
pub(crate) const MAX_ADDRESS_SPACE: u64 = 512 * 1024 * 1024;
/// Lifetime RLIMIT_CPU backstop only. A long-lived plugin accumulates CPU across invocations,
/// so the per-invocation budget (`CPU_BUDGET_MS`, enforced by the host) is the real limit.
pub(crate) const MAX_CPU_SECONDS: u64 = 3600;
pub(crate) const MAX_OPEN_FILES: u64 = 32;
/// Per-invocation CPU of the sandbox process tree; test-only override GIDEON_PLUGIN_CPU_BUDGET_MS.
const CPU_BUDGET_MS: u64 = 30_000;
const CPU_SAMPLE: Duration = Duration::from_millis(200);
/// /tmp is a tmpfs of this size inside the sandbox (bwrap `--size`, or RLIMIT_FSIZE per file).
pub(crate) const MAX_TMP_BYTES: u64 = 64 * 1024 * 1024;
/// RLIMIT_NPROC counts every task of the real uid, and other processes of that uid (other
/// sessions, test runners) change the count at any time. The cap is the count observed at spawn
/// plus this generous headroom: it still stops a fork bomb, but never starves bwrap's own forks.
const PROCESS_HEADROOM: u64 = 256;
/// Plugin lines queued for the Core. Overflow kills the plugin; floods are dropped before this.
const LINE_QUEUE: usize = 64;
/// Obvious log-line prefix checked before any JSON parse, so floods cost one comparison.
const LOG_PREFIX: &[u8] = b"{\"event\":\"log\"";

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
    /// Upstream HTTP status (100..=599), only with `error == "http_error"`. Never body or headers.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub http_status: Option<u16>,
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
        /// Approved C4 synthetic permissions of the owner (empty unless approved).
        grants: Vec<String>,
    },
    Cancel {
        plugin_id: String,
        invocation: u64,
    },
}
/// Facts reported by the host back to the Core.
#[derive(Debug)]
pub enum Ev {
    /// A `skills.*` host service of a plugin. The Core answers on `reply` inside the same loop turn.
    Service {
        plugin_id: String,
        service: String,
        args: Value,
        reply: tokio::sync::oneshot::Sender<Result<Value, &'static str>>,
    },
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
        http_status: Option<u16>,
    },
    Partial {
        plugin_id: String,
        invocation: u64,
        text: String,
    },
    Log {
        plugin_id: String,
    },
    /// A fallback `llm.http` attempt reached the broker (no content, no provider data).
    FallbackUsed {
        plugin_id: String,
        invocation: u64,
    },
    /// A C4 synthetic service reached the world (audit kind only, never content).
    Audit {
        plugin_id: String,
        kind: &'static str,
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
    /// `used_fallback` of the last accepted LLM result (any capability whose output has it), taken once by the Core.
    chat_note: Option<bool>,
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
        if let Err(code) = self.save(storage, next) {
            // The approval is already gone: stop the host and drop the claim now, then fail closed.
            self.ledger.enabled.retain(|id| id != plugin_id);
            self.stop(plugin_id);
            self.quarantined = true;
            return Err(code);
        }
        self.stop(plugin_id);
        self.events.push("plugin_revoked");
        Ok(())
    }
    /// Runtime state of an enabled plugin for the Hub snapshot; `disabled` otherwise.
    fn runtime_of(&self, plugin_id: &str) -> &'static str {
        if !self.ledger.enabled.iter().any(|id| id == plugin_id) {
            return "disabled";
        }
        self.runtimes.get(plugin_id).map_or("starting", |r| r.state)
    }
    /// The Hub snapshot's per-plugin `runtime` reports the host state, not a constant.
    pub(crate) fn annotate(&self, mut hub: Snapshot) -> Snapshot {
        for item in &mut hub.installed {
            item.runtime = self.runtime_of(&item.plugin_id);
        }
        hub
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
        if !object_ok || !size_ok || !depth_ok(&input, 0) || !(1..=30000).contains(&deadline_ms) {
            return Err("invalid_input");
        }
        if self.active.is_some() {
            return Err("busy");
        }
        self.next_invocation = self.next_invocation.saturating_add(1);
        let invocation = self.next_invocation;
        // Authority for brokered HTTP and settings is fixed per invocation: approved grants plus Core config.
        let granted =
            |name: &str| owner.permissions_approved && owner.permissions.iter().any(|p| p == name);
        let auth = llm.host_auth(granted(NETWORK_PERMISSION), granted(SETTINGS_PERMISSION));
        let grants: Vec<String> = world::PERMISSIONS
            .iter()
            .filter(|name| granted(name))
            .map(|name| name.to_string())
            .collect();
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
            grants,
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
                http_status,
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
                // The LLM broker's output carries `used_fallback`; only that bool is kept, never content.
                if let Some(used) = outcome
                    .as_ref()
                    .ok()
                    .and_then(|output| output.get("used_fallback"))
                    .and_then(Value::as_bool)
                {
                    self.chat_note = Some(used);
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
                        http_status: None,
                    },
                    Err(code) => CapabilityResult {
                        capability,
                        plugin_id,
                        ok: false,
                        output: None,
                        error: Some(code),
                        elapsed_ms,
                        partial,
                        http_status: http_status.filter(|_| code == "http_error"),
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
            Ev::FallbackUsed {
                plugin_id,
                invocation,
            } => {
                let current = self
                    .active
                    .as_ref()
                    .is_some_and(|a| a.invocation == invocation && a.plugin_id == plugin_id);
                if current && self.ledger.enabled.iter().any(|id| *id == plugin_id) {
                    self.events.push("llm_fallback_used");
                }
            }
            Ev::Audit { plugin_id, kind } => {
                if self.ledger.enabled.iter().any(|id| *id == plugin_id) {
                    self.events.push(kind);
                }
            }
            // Answered by the Core before it reaches the plugin registry (Core::plugin_event).
            Ev::Service { .. } => {}
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
    /// Drops the published result once an internal consumer (a skill run) has taken it, so step
    /// output never reaches the client snapshot.
    pub(crate) fn clear_last(&mut self) {
        self.last = None;
    }
    /// A capability invocation is running (the Core refuses a restart meanwhile).
    pub(crate) fn invoking(&self) -> bool {
        self.active.is_some()
    }
    /// Takes the fallback flag of the last accepted `*.chat` result, if any.
    pub(crate) fn take_chat_note(&mut self) -> Option<bool> {
        self.chat_note.take()
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
/// Authority of one invocation: brokered-HTTP/settings grants and the C4 synthetic grants.
struct Scope {
    auth: HostAuth,
    grants: Vec<String>,
}
enum Cmd {
    Invoke {
        invocation: u64,
        capability: String,
        input: Value,
        deadline_ms: u64,
        scope: Box<Scope>,
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
    cpu_budget_ms: u64,
}

impl Host {
    pub fn new(
        python: Option<PathBuf>,
        broker: PathBuf,
        sender: mpsc::UnboundedSender<Wire>,
    ) -> Self {
        // Test-only override (validated range); production always uses CPU_BUDGET_MS.
        let cpu_budget_ms = std::env::var("GIDEON_PLUGIN_CPU_BUDGET_MS")
            .ok()
            .and_then(|raw| raw.parse::<u64>().ok())
            .filter(|ms| (50..=60000).contains(ms))
            .unwrap_or(CPU_BUDGET_MS);
        Self {
            python,
            broker,
            sender,
            actors: HashMap::new(),
            retired: vec![],
            epoch: 0,
            cpu_budget_ms,
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
                    cpu_budget_ms: self.cpu_budget_ms,
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
                grants,
            } => {
                let sent = self.actors.get(&plugin_id).is_some_and(|a| {
                    a.commands
                        .send(Cmd::Invoke {
                            invocation,
                            capability,
                            input,
                            deadline_ms,
                            scope: Box::new(Scope { auth, grants }),
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
                        http_status: None,
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
            | Ev::FallbackUsed { plugin_id, .. }
            | Ev::Audit { plugin_id, .. }
            | Ev::Service { plugin_id, .. }
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
    cpu_budget_ms: u64,
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
        self.result_status(invocation, outcome, started, None);
    }
    fn result_status(
        &self,
        invocation: u64,
        outcome: Result<Value, &'static str>,
        started: Instant,
        http_status: Option<u16>,
    ) {
        self.send(Ev::Result {
            plugin_id: self.plugin_id.clone(),
            invocation,
            outcome,
            elapsed_ms: started.elapsed().as_millis() as u64,
            http_status,
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
        // Stop must interrupt the handshake; the child is killed when the start future drops.
        let started = tokio::select! {
            started = Session::start(&ctx) => started,
            command = commands.recv() => {
                if let Some(Cmd::Invoke { invocation, .. }) = command {
                    out.result(invocation, Err("capability_unavailable"), Instant::now());
                }
                out.state("stopped", restarts, None);
                return;
            }
        };
        let mut session = match started {
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
    /// Sandbox CPU ticks when the invocation started, and the next per-invocation sample.
    cpu_base: u64,
    next_sample: Instant,
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
    /// Sandbox root pid (bwrap); its descendants are the plugin process tree.
    pid: u32,
    cpu_budget_ms: u64,
    stdin: ChildStdin,
    lines: mpsc::Receiver<Line>,
    reader: JoinHandle<()>,
    next_id: u64,
    pending: Option<Pending>,
    log_window: (Instant, u32),
    python: PathBuf,
    broker: PathBuf,
    /// Private Core root (settings live under it) and the plugin whose settings these are.
    root: PathBuf,
    plugin_id: String,
    auth: HostAuth,
    /// Approved C4 synthetic permissions for the active invocation (fixed at invoke time).
    grants: Vec<String>,
    host: Option<HostCall>,
    /// Last upstream status the broker reported for the active invocation (Core-side only).
    http_status: Option<u16>,
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
/// Arguments are parsed per service, so each service has its own strict shape.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct HostCallLine {
    op: String,
    #[serde(default)]
    v: Option<u16>,
    id: u64,
    service: String,
    args: Value,
}
/// `llm.http` arguments. `target` picks the route; absent means `primary`.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct HttpArgs {
    path: String,
    body: Value,
    stream: bool,
    /// Accepted for compatibility and always dropped: Core sets every broker header itself.
    #[serde(default)]
    headers: Option<BTreeMap<String, String>>,
    #[serde(default)]
    target: Option<String>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PutArgs {
    data: Value,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct NoArgs {}
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

/// Reads plugin lines into a bounded queue. Log lines over the per-second budget are dropped
/// here, before queueing and before any JSON parse. A full queue ends the reader: the drive loop
/// sees the queue end without a terminal line and treats it as a protocol violation (kill).
async fn read_lines(stdout: ChildStdout, tx: mpsc::Sender<Line>) {
    let mut reader = BufReader::new(stdout);
    let mut logs = (Instant::now(), 0u32);
    loop {
        let line = match bounded_frame(&mut reader, MAX_LINE).await {
            Ok(Some(mut bytes)) => {
                if bytes.last() == Some(&b'\n') {
                    bytes.pop();
                }
                if bytes.starts_with(LOG_PREFIX) {
                    let now = Instant::now();
                    if now.duration_since(logs.0) >= Duration::from_secs(1) {
                        logs = (now, 0);
                    }
                    if logs.1 >= LOG_PER_SECOND {
                        continue;
                    }
                    logs.1 += 1;
                }
                Line::Frame(bytes)
            }
            // Oversize lines are protocol violations; EOF or I/O errors mean the plugin closed.
            Err(error) if error.kind() == io::ErrorKind::InvalidData => Line::Invalid,
            Ok(None) | Err(_) => Line::Closed,
        };
        let terminal = !matches!(line, Line::Frame(_));
        match tx.try_send(line) {
            Ok(()) if !terminal => {}
            // Terminal line queued, or the Session is gone: nothing more to read.
            Ok(()) => return,
            Err(_) => return,
        }
    }
}

/// CPU ticks (utime + stime) of `root` and its live descendants, read from /proc.
fn tree_cpu_ticks(root: u32) -> Option<u64> {
    let mut children: HashMap<u32, Vec<u32>> = HashMap::new();
    let mut ticks: HashMap<u32, u64> = HashMap::new();
    for entry in fs::read_dir("/proc").ok()?.flatten() {
        let Some(pid) = entry
            .file_name()
            .to_str()
            .and_then(|n| n.parse::<u32>().ok())
        else {
            continue;
        };
        let Ok(stat) = fs::read_to_string(entry.path().join("stat")) else {
            continue;
        };
        // comm may contain spaces or parentheses; fields start after the last ')'.
        let Some((_, rest)) = stat.rsplit_once(')') else {
            continue;
        };
        let fields: Vec<&str> = rest.split_whitespace().collect();
        let parsed = (
            fields.get(1).and_then(|v| v.parse::<u32>().ok()),
            fields.get(11).and_then(|v| v.parse::<u64>().ok()),
            fields.get(12).and_then(|v| v.parse::<u64>().ok()),
        );
        if let (Some(ppid), Some(user), Some(system)) = parsed {
            children.entry(ppid).or_default().push(pid);
            ticks.insert(pid, user.saturating_add(system));
        }
    }
    if !ticks.contains_key(&root) {
        return None;
    }
    let mut total = 0u64;
    let mut stack = vec![root];
    let mut seen = HashSet::new();
    while let Some(pid) = stack.pop() {
        if !seen.insert(pid) {
            continue;
        }
        total = total.saturating_add(ticks.get(&pid).copied().unwrap_or(0));
        stack.extend(children.get(&pid).into_iter().flatten().copied());
    }
    Some(total)
}
/// Clock ticks per second for /proc stat accounting (fallback 100 if the query fails).
fn clock_ticks() -> u64 {
    // SAFETY: sysconf with a constant name has no preconditions.
    let ticks = unsafe { libc::sysconf(libc::_SC_CLK_TCK) };
    if ticks > 0 {
        ticks as u64
    } else {
        100
    }
}
/// Whether the installed bwrap accepts `--size` for `--tmpfs` (probed once).
fn bwrap_supports_size() -> bool {
    static SUPPORTED: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
    *SUPPORTED.get_or_init(|| {
        std::process::Command::new(BWRAP)
            .arg("--help")
            .output()
            .is_ok_and(|out| {
                let text = [out.stdout, out.stderr].concat();
                String::from_utf8_lossy(&text).contains("--size")
            })
    })
}
/// Interpreter gate for `--plugin-python`. Returns the canonical runtime directory when the
/// interpreter may run. Rules, in order:
/// 1. A runtime inside the package prefix is accepted regardless of HOME, unless the prefix is
///    `/` or an ancestor-or-equal of HOME (a package prefix that covers HOME is not usable).
/// 2. A runtime that equals or contains HOME is `plugin_python_forbidden_root`.
/// 3. An interpreter or runtime under HOME (outside the package prefix) is
///    `plugin_python_under_home`.
/// 4. A runtime at `/`, `/home` is `plugin_python_forbidden_root`.
/// 5. Otherwise the runtime must sit under `/usr`, `/usr/local` or `/opt`, else
///    `plugin_python_not_allowed`.
pub fn plugin_runtime_check(
    python: &Path,
    package_home: &Path,
    user_home: Option<&Path>,
) -> Result<PathBuf, &'static str> {
    let refused = "plugin_not_runnable";
    if !python.is_absolute() {
        return Err(refused);
    }
    let real = fs::canonicalize(python).map_err(|_| refused)?;
    let interpreter = resolve_interpreter(python);
    let runtime = interpreter.parent().and_then(Path::parent).ok_or(refused)?;
    let runtime = fs::canonicalize(runtime).map_err(|_| refused)?;
    let package = fs::canonicalize(package_home).map_err(|_| refused)?;
    // A HOME that cannot be canonicalized keeps its raw path: the HOME checks never switch off silently.
    let home = user_home.map(|h| fs::canonicalize(h).unwrap_or_else(|_| h.to_path_buf()));
    let home = home.as_deref();
    let package_usable = package != Path::new("/") && home.is_none_or(|h| !h.starts_with(&package));
    if package_usable && runtime.starts_with(&package) {
        return Ok(runtime);
    }
    if let Some(home) = home {
        if home.starts_with(&runtime) {
            return Err("plugin_python_forbidden_root");
        }
        if real.starts_with(home) || runtime.starts_with(home) {
            return Err("plugin_python_under_home");
        }
    }
    if runtime == Path::new("/") || runtime == Path::new("/home") {
        return Err("plugin_python_forbidden_root");
    }
    let allowed = [
        Path::new("/usr"),
        Path::new("/usr/local"),
        Path::new("/opt"),
    ];
    if allowed.iter().any(|prefix| runtime.starts_with(prefix)) {
        return Ok(runtime);
    }
    Err("plugin_python_not_allowed")
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
pub(crate) fn process_budget() -> u64 {
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
/// with no network, no capabilities, no user home, no repo, a private size-capped /tmp and a
/// read-only payload. Without bwrap `--size`, /tmp is bounded per file by RLIMIT_FSIZE instead.
pub(crate) fn sandbox_command(
    python: &Path,
    payload: &Path,
    processes: u64,
) -> io::Result<Command> {
    sandbox_command_with(python, payload, processes, &[])
}

/// Same sandbox with fixed extra arguments after the script (S5 MCP: `--profile <name>`). The
/// arguments come from Core constants, never from the UI, a skill or the service.
pub(crate) fn sandbox_command_with(
    python: &Path,
    payload: &Path,
    processes: u64,
    extra: &[&str],
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
    let sized = bwrap_supports_size();
    let mut limits = vec![
        format!("--as={MAX_ADDRESS_SPACE}"),
        format!("--cpu={MAX_CPU_SECONDS}"),
        format!("--nofile={MAX_OPEN_FILES}"),
        format!("--nproc={processes}"),
    ];
    if !sized {
        limits.push(format!("--fsize={MAX_TMP_BYTES}"));
    }
    let mut command = Command::new(PRLIMIT);
    command.env_clear().args(limits).arg("--").arg(BWRAP).args([
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
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
    ]);
    if sized {
        command.args(["--size", &MAX_TMP_BYTES.to_string()]);
    }
    command
        .args(["--tmpfs", "/tmp"])
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
        .args(extra)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .kill_on_drop(true);
    Ok(command)
}

/// Spawns the sandbox. EAGAIN (the uid hit RLIMIT_NPROC) gets exactly one retry with a freshly
/// computed budget; any other failure is plugin_start_failed.
async fn spawn_sandboxed(ctx: &Ctx, payload: &Path) -> Result<Child, &'static str> {
    for attempt in 0..2 {
        let budget = tokio::task::spawn_blocking(process_budget)
            .await
            .map_err(|_| "plugin_start_failed")?;
        let mut command =
            sandbox_command(&ctx.python, payload, budget).map_err(|_| "plugin_not_runnable")?;
        match command.spawn() {
            Ok(child) => return Ok(child),
            Err(error) if attempt == 0 && error.raw_os_error() == Some(libc::EAGAIN) => continue,
            Err(_) => return Err("plugin_start_failed"),
        }
    }
    Err("plugin_start_failed")
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
        let mut child = spawn_sandboxed(ctx, &payload).await?;
        let pid = child.id().ok_or("plugin_start_failed")?;
        let (Some(stdin), Some(stdout)) = (child.stdin.take(), child.stdout.take()) else {
            let _ = child.kill().await;
            return Err("plugin_start_failed");
        };
        let (tx, lines) = mpsc::channel(LINE_QUEUE);
        let reader = tokio::spawn(read_lines(stdout, tx));
        let mut session = Session {
            child,
            pid,
            cpu_budget_ms: ctx.cpu_budget_ms,
            stdin,
            lines,
            reader,
            next_id: 2,
            pending: None,
            log_window: (Instant::now(), 0),
            python: ctx.python.clone(),
            broker: ctx.broker.clone(),
            root: ctx.root.clone(),
            plugin_id: ctx.plugin_id.clone(),
            auth: HostAuth::default(),
            grants: Vec::new(),
            host: None,
            http_status: None,
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
            let sample = self.pending.as_ref().map(|p| p.next_sample);
            tokio::select! {
                line = self.lines.recv() => match line {
                    Some(Line::Frame(bytes)) => {
                        if let Err(exit) = self.frame(&bytes, out).await {
                            return exit;
                        }
                    }
                    Some(Line::Invalid) => return self.violation(out, "plugin_output_invalid"),
                    Some(Line::Closed) => {
                        self.fail_pending(out, "plugin_error");
                        return Exit::Crashed;
                    }
                    // The reader stopped without a terminal line: the queue overflowed.
                    None => return self.violation(out, "plugin_output_invalid"),
                },
                _ = sleep_until(sample), if sample.is_some() => {
                    if let Err(exit) = self.sample_cpu(out) {
                        return exit;
                    }
                },
                command = commands.recv() => match command {
                    Some(Cmd::Invoke { invocation, capability, input, deadline_ms, scope }) => {
                        if let Err(exit) = self.invoke(out, invocation, &capability, input, deadline_ms, *scope).await {
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
    /// Per-invocation CPU budget: the sandbox tree's CPU since the invocation began.
    fn sample_cpu(&mut self, out: &Out) -> Result<(), Exit> {
        let Some(pending) = self.pending.as_mut() else {
            return Ok(());
        };
        pending.next_sample = Instant::now() + CPU_SAMPLE;
        let base = pending.cpu_base;
        let Some(now) = tree_cpu_ticks(self.pid) else {
            return Ok(());
        };
        let used_ms = now.saturating_sub(base).saturating_mul(1000) / clock_ticks();
        if used_ms > self.cpu_budget_ms {
            return Err(self.violation(out, "plugin_cpu_exceeded"));
        }
        Ok(())
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
        scope: Scope,
    ) -> Result<(), Exit> {
        let Scope { auth, grants } = scope;
        let started = Instant::now();
        if self.pending.is_some() {
            out.result(invocation, Err("busy"), started);
            return Ok(());
        }
        let wire_id = self.next_id;
        self.next_id += 1;
        self.http_status = None;
        let mut message = serde_json::json!({
            "v": 1,
            "id": wire_id,
            "op": "invoke",
            "capability": capability,
            "input": input,
            "deadline_ms": deadline_ms,
        });
        // Config is visible to plugins as context only; keys and URLs never are.
        if let Some(primary) = auth.primary.as_ref() {
            let mut llm = serde_json::json!({
                "provider": primary.route.provider.as_str(),
                "model": primary.route.model,
            });
            if let Some(fallback) = auth.fallback.as_ref() {
                llm["fallback"] = serde_json::json!({
                    "provider": fallback.route.provider.as_str(),
                    "model": fallback.route.model,
                });
            }
            message["ctx"] = serde_json::json!({ "llm": llm });
        }
        self.auth = auth;
        self.grants = grants;
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
            cpu_base: tree_cpu_ticks(self.pid).unwrap_or(0),
            next_sample: started + CPU_SAMPLE,
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
        // Every log event is budgeted here; the reader already capped prefixed lines before queueing.
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
                (None, Some(code)) if valid_code(code) => Err(pass_through(code)),
                _ => return Err(self.violation(out, "plugin_output_invalid")),
            }
        };
        let Some(pending) = self.pending.take() else {
            return Ok(());
        };
        self.stop_host();
        // A reply after cancel or timeout was already reported; it is dropped.
        if pending.grace.is_none() {
            out.result_status(
                pending.invocation,
                outcome,
                pending.started,
                self.http_status,
            );
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
    /// Core-side gate for one route. Local routes need neither a key nor consent; cloud routes need
    /// both, the key checked first. Loopback is exempt from cloud consent only in test mode.
    fn authorize(&self, access: Option<&Access>) -> Result<broker::Target, &'static str> {
        let auth = &self.auth;
        if !auth.permission {
            return Err("permission_denied");
        }
        let access = access.ok_or("provider_not_configured")?;
        if access.route.provider.is_local() {
            return broker::target(&access.route, auth.allow_loopback);
        }
        if access.key.is_none() {
            return Err("key_missing");
        }
        let target = broker::target(&access.route, auth.allow_loopback)?;
        let exempt = target.loopback && auth.allow_loopback;
        if !auth.cloud_consent && !exempt {
            return Err("cloud_not_authorized");
        }
        Ok(target)
    }
    /// Gate for one `llm.http` host_call, in a fixed order: cancel, busy, shape, route, authority.
    /// Returns the route, its target, and whether this call is the fallback attempt.
    fn http_gate(
        &self,
        cancelled: bool,
        args: &HttpArgs,
    ) -> Result<(Access, broker::Target, bool), &'static str> {
        if cancelled {
            return Err("cancelled");
        }
        if self.host.is_some() {
            return Err("busy");
        }
        if args.path != broker::CHAT_PATH || !args.stream || !args.body.is_object() {
            return Err("invalid_host_call");
        }
        let fallback = match args.target.as_deref() {
            None | Some("primary") => false,
            Some("fallback") => true,
            Some(_) => return Err("invalid_host_call"),
        };
        let access = if fallback {
            self.auth.fallback.as_ref()
        } else {
            self.auth.primary.as_ref()
        };
        let target = self.authorize(access)?;
        let access = access.cloned().ok_or("provider_not_configured")?;
        Ok((access, target, fallback))
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
    /// C4 synthetic service: flag first (`unknown_service` without it), then the approved permission
    /// fixed at invoke time, then the world (strict args, epoch, verification, reply cap).
    fn synthetic(&mut self, service: &str, args: Value, out: &Out) -> Result<Value, &'static str> {
        let name = service.strip_prefix("synthetic.").unwrap_or(service);
        if !crate::agent::options().synthetic {
            return Err("unknown_service");
        }
        let permission = world::permission(name).ok_or("unknown_service")?;
        if !self.grants.iter().any(|grant| grant == permission) {
            return Err("permission_denied");
        }
        out.send(Ev::Audit {
            plugin_id: out.plugin_id.clone(),
            kind: world::audit_kind(name),
        });
        world::serve(&world::dir(), name, &args).map_err(|code| match code {
            "invalid_args" => "invalid_host_call",
            other => other,
        })
    }
    /// Core-side settings store of this plugin (C2). The Core never interprets the object.
    fn settings(&self, service: &str, args: Value) -> Result<Value, &'static str> {
        if service == "settings.get" {
            serde_json::from_value::<NoArgs>(args).map_err(|_| "invalid_host_call")?;
            return storage::plugin_settings_read(&self.root, &self.plugin_id)
                .map(|data| data.unwrap_or(Value::Null))
                .map_err(|_| "settings_unavailable");
        }
        let PutArgs { data } = serde_json::from_value(args).map_err(|_| "invalid_host_call")?;
        let size = serde_json::to_vec(&data).map_or(usize::MAX, |bytes| bytes.len());
        if !data.is_object() || size > MAX_SETTINGS || !depth_ok(&data, 0) {
            return Err("invalid_input");
        }
        storage::plugin_settings_write(&self.root, &self.plugin_id, &data)
            .map_err(|_| "settings_unavailable")?;
        Ok(Value::Null)
    }
    /// Plugin `host_call`: strict shape, one active call, Core gates, then either the sandboxed
    /// broker (`llm.http`) or the plugin's own settings (`settings.get` / `settings.put`).
    async fn host_call(&mut self, value: Value, out: &Out) -> Result<(), Exit> {
        let Ok(line) = serde_json::from_value::<HostCallLine>(value) else {
            return Err(self.violation(out, "plugin_output_invalid"));
        };
        let (cancelled, invocation) = match self.pending.as_ref() {
            Some(pending) => (pending.grace.is_some(), pending.invocation),
            None => return Err(self.violation(out, "plugin_output_invalid")),
        };
        if line.op != "host_call" || line.v.is_some_and(|v| v != 1) {
            return Err(self.violation(out, "plugin_output_invalid"));
        }
        let id = line.id;
        match line.service.as_str() {
            "llm.http" => {
                let Ok(args) = serde_json::from_value::<HttpArgs>(line.args) else {
                    return Err(self.violation(out, "plugin_output_invalid"));
                };
                let oversized_headers = args.headers.as_ref().is_some_and(|h| {
                    h.len() > MAX_HEADERS || h.values().any(|v| v.len() > MAX_HEADER_VALUE)
                });
                if oversized_headers {
                    return Err(self.violation(out, "plugin_output_invalid"));
                }
                let opened = match self.http_gate(cancelled, &args) {
                    Ok((access, target, fallback)) => self
                        .open_broker(id, args.body, &access, &target)
                        .await
                        .map(|call| (call, fallback)),
                    Err(code) => Err(code),
                };
                match opened {
                    Ok((call, fallback)) => {
                        self.host = Some(call);
                        if fallback {
                            out.send(Ev::FallbackUsed {
                                plugin_id: out.plugin_id.clone(),
                                invocation,
                            });
                        }
                        Ok(())
                    }
                    Err(code) => self.host_error(id, code, None).await,
                }
            }
            service @ ("settings.get" | "settings.put") => {
                let outcome = if cancelled {
                    Err("cancelled")
                } else if self.host.is_some() {
                    Err("busy")
                } else if !self.auth.settings {
                    Err("permission_denied")
                } else {
                    self.settings(service, line.args)
                };
                match outcome {
                    Ok(data) => self
                        .write(&serde_json::json!({"v": 1, "op": "host_reply", "id": id, "done": true, "data": data}))
                        .await
                        .map_err(|_| Exit::Crashed),
                    Err(code) => self.host_error(id, code, None).await,
                }
            }
            name if name.starts_with("synthetic.") => {
                let outcome = if cancelled {
                    Err("cancelled")
                } else if self.host.is_some() {
                    Err("busy")
                } else {
                    self.synthetic(name, line.args, out)
                };
                match outcome {
                    Ok(data) => self
                        .write(&serde_json::json!({"v": 1, "op": "host_reply", "id": id, "done": true, "data": data}))
                        .await
                        .map_err(|_| Exit::Crashed),
                    Err(code) => self.host_error(id, code, None).await,
                }
            }
            name if name.starts_with("skills.") => {
                let outcome = if cancelled {
                    Err("cancelled")
                } else if self.host.is_some() {
                    Err("busy")
                } else {
                    skill_service(name, line.args, out).await
                };
                match outcome {
                    Ok(data) => self
                        .write(&serde_json::json!({"v": 1, "op": "host_reply", "id": id, "done": true, "data": data}))
                        .await
                        .map_err(|_| Exit::Crashed),
                    Err(code) => self.host_error(id, code, None).await,
                }
            }
            _ => {
                let code = if cancelled {
                    "cancelled"
                } else if self.host.is_some() {
                    "busy"
                } else {
                    "invalid_host_call"
                };
                self.host_error(id, code, None).await
            }
        }
    }
    async fn open_broker(
        &self,
        id: u64,
        mut body: Value,
        access: &Access,
        target: &broker::Target,
    ) -> Result<HostCall, &'static str> {
        // The Core, not the plugin, chooses the model and forces streaming.
        body["model"] = serde_json::json!(access.route.model);
        body["stream"] = serde_json::json!(true);
        let payload = broker::payload(target, &body, access.key.as_deref())?;
        let budget = tokio::task::spawn_blocking(process_budget)
            .await
            .map_err(|_| "network_unavailable")?;
        let mut command = broker::command(&self.python, &self.broker, budget)
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
                self.http_status = status.filter(|s| (100..=599).contains(s));
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
/// Plugin error codes that reach clients unchanged (C1, C4 host codes of docs/C4.md). Any other plugin code reads `plugin_error`.
const PASS_THROUGH_ERRORS: [&str; 31] = [
    "key_missing",
    "cloud_not_authorized",
    "provider_not_configured",
    "permission_denied",
    "http_error",
    "timeout",
    "response_too_large",
    "network_unavailable",
    "cancelled",
    "invalid_input",
    "host_not_allowed",
    "redirect_refused",
    "busy",
    "invalid_host_call",
    "model_unsupported_feature",
    "model_not_found",
    "model_selftest_failed",
    "settings_unavailable",
    "stale_screen",
    "opt_in_required",
    "unknown_service",
    "unknown_element",
    "no_focus",
    "unknown_route",
    "unknown_app",
    "indicator_off",
    "already_recording",
    "not_recording",
    "world_unavailable",
    "skill_invalid",
    "model_output_invalid",
];
/// Skill host services the Core answers for an approved `skills_author` plugin (docs/S4.md D3).
/// Every other `skills.*` name, including approve, enable, export, import, run and publish, is
/// `unknown_service` and never leaves the transport.
const SKILL_SERVICES: [&str; 4] = [
    "skills.validate",
    "skills.draft_put",
    "skills.dry_run",
    "skills.list",
];
/// Longest wait for the Core's answer. The Core answers in the same loop turn, so this only bounds
/// a Core that stopped answering.
const SERVICE_DEADLINE: Duration = Duration::from_secs(2);
/// Plugin-side skill service. Unknown names fail here; known names go to the Core and back.
async fn skill_service(service: &str, args: Value, out: &Out) -> Result<Value, &'static str> {
    if !SKILL_SERVICES.contains(&service) {
        return Err("unknown_service");
    }
    let (reply, answer) = tokio::sync::oneshot::channel();
    out.send(Ev::Service {
        plugin_id: out.plugin_id.clone(),
        service: service.to_owned(),
        args,
        reply,
    });
    match tokio::time::timeout(SERVICE_DEADLINE, answer).await {
        Ok(Ok(outcome)) => outcome,
        _ => Err("skills_unavailable"),
    }
}
fn pass_through(code: &str) -> &'static str {
    PASS_THROUGH_ERRORS
        .iter()
        .copied()
        .find(|allowed| *allowed == code)
        .unwrap_or("plugin_error")
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
