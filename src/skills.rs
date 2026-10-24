//! S4 skill engine. D1: strict manifest (`skill.json`) and validator. D2: Core executor, ledgers
//! and ops. A skill is a declarative procedure over capabilities that are already installed. It
//! grants nothing, runs no shell or code, and every state change waits for the user
//! (`skill_decide`). Effects go through the same paths as the agent: `PluginView::invoke` for
//! plugin capabilities, the C1 tool ledger for registry tools, and the synthetic world for bridge
//! and test tools.
use crate::{
    core::Core,
    protocol::ToolDecision,
    tools::{self, Risk},
    world,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, HashSet},
    fs::{self, OpenOptions},
    io::{self, Read, Write},
    os::unix::fs::{DirBuilderExt, OpenOptionsExt},
    path::{Path, PathBuf},
    sync::Arc,
    time::{Duration, Instant},
};

pub const SCHEMA_VERSION: u64 = 1;
/// Largest manifest accepted by the validator (canonical JSON bytes).
pub const MANIFEST_MAX: usize = 16 * 1024;
const LEDGER_MAX: usize = 32 * 1024;
const RUNS_MAX: usize = 32;
const SKILLS_MAX: usize = 16;
const VERSIONS_MAX: usize = 3;
const STEPS_MAX: usize = 16;
const LIST_MAX: usize = 8;
const UNDO_MAX: usize = 8;
const ARGS_MAX: usize = 2048;
const ARGS_DEPTH_MAX: usize = 3;
/// Longest chain of skills (top skill included): top, one nested, two nested levels at most.
const CHAIN_MAX: usize = 3;
const RETRY_MAX: u8 = 2;
const TIMEOUT_MAX: u64 = 10_000;
const TEXT_DEFAULT_MAX: i64 = 256;
const RUN_DEADLINE: Duration = Duration::from_secs(60);
const STEP_TIMEOUT_MS: u64 = 10_000;
const OUTPUT_MAX: usize = 1024;
const ENGINE_OWNER: &str = "skill_engine";
const GRANT_KEYS: [&str; 10] = [
    "grant",
    "grants",
    "granted",
    "permission",
    "permissions",
    "permissions_approved",
    "approve",
    "approved",
    "allow",
    "allowed",
];
const SECRET_KEYS: [&str; 4] = ["key", "token", "secret", "password"];
/// Approved plugin permission that allows the D3 host services (`skills.*`). Never a grant itself.
const SKILLS_AUTHOR: &str = "skills_author";
/// D4 package format and its size limit (import reads at most this many bytes).
const PACKAGE_FORMAT: u64 = 1;
const PACKAGE_MAX: u64 = 64 * 1024;
const EXPORT_DIR: &str = "skill-exports";
const IMPORT_DIR: &str = "skill-imports";
const MANIFEST_FILE: &str = "skill.json";

// Validator reasons. Each one is a complete static code, so responses never allocate.
const E_SCHEMA: &str = "skill_invalid:schema_version";
const E_MIN_RUNTIME: &str = "skill_invalid:min_runtime";
const E_UNKNOWN_KEY: &str = "skill_invalid:unknown_key";
const E_OUT_OF_SCOPE: &str = "skill_invalid:out_of_scope";
const E_DUP_STEP: &str = "skill_invalid:duplicate_step";
const E_FUTURE_REF: &str = "skill_invalid:forward_ref";
const E_CYCLE: &str = "skill_invalid:cycle";
const E_DEPTH: &str = "skill_invalid:depth";
const E_EXFIL: &str = "skill_invalid:exfiltration";
const E_OVERSIZE: &str = "skill_invalid:oversize";
const E_GRANT: &str = "skill_invalid:grant_field";
const E_RESERVED: &str = "skill_invalid:reserved_capability";
const E_UNKNOWN_TOOL: &str = "skill_invalid:unknown_tool";
const E_FIELD: &str = "skill_invalid:bad_manifest";
const E_ID: &str = "skill_invalid:bad_id";
const E_VERSION: &str = "skill_invalid:bad_version";
const E_TEMPLATE: &str = "skill_invalid:bad_template";
const E_TOO_MANY_STEPS: &str = "skill_invalid:too_many_steps";
const E_TOO_MANY_DEPS: &str = "skill_invalid:too_many_deps";
const E_PUBLISHER: &str = "skill_invalid:bad_publisher";
const E_TOO_LONG: &str = "skill_invalid:bad_manifest";
const E_ARGS_DEPTH: &str = "skill_invalid:args_depth";
const E_UNDO_LIMIT: &str = "skill_invalid:undo_limit";
const E_RETRIES: &str = "skill_invalid:retries_need_idempotent";
const E_COND: &str = "skill_invalid:invalid_cond";
const E_SAVE: &str = "skill_invalid:invalid_save";
const E_SKILL_LIMIT: &str = "skill_invalid:skill_limit";
const E_VERSION_LIMIT: &str = "skill_invalid:version_limit";
const E_LOCKED: &str = "skill_invalid:version_locked";
const E_DUPLICATE: &str = "skill_invalid:duplicate_id";
// Package scan findings (D4). Each one is a bridge validator reason.
const F_HASH: &str = "skill_invalid:hash_mismatch";
const F_CORRUPT: &str = "skill_invalid:corrupt_package";
const F_SYMLINK: &str = "skill_invalid:symlink";
const F_TOO_LARGE: &str = "skill_invalid:file_too_large";
const F_PATH: &str = "skill_invalid:path_not_allowed";
const F_ESCALATED: &str = "skill_invalid:permissions_escalated";
/// Operation reasons of the import path (bridge messages: invalid_import, import_not_found).
const E_IMPORT_INVALID: &str = "invalid_import";
const E_IMPORT_NOT_FOUND: &str = "import_not_found";
const E_STALE_IMPORT: &str = "stale_import";

/// Lifecycle of one version. `draft` is reserved for drafts created outside the Core (D3).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum State {
    Draft,
    Validated,
    Tested,
    Approved,
    Enabled,
    Disabled,
    Revised,
}

impl State {
    /// Content of a locked version can never change in place; a new version is needed.
    fn locked(self) -> bool {
        matches!(
            self,
            State::Approved | State::Enabled | State::Disabled | State::Revised
        )
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Source {
    Created,
    Imported,
    LlmDraft,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct VersionEntry {
    version: String,
    manifest_sha256: String,
    state: State,
    source: Source,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    approved_at_rev: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct SkillEntry {
    id: String,
    versions: Vec<VersionEntry>,
    active: Option<String>,
}

/// `skills.json`: private, 0600, CAS on `revision`, at most 32 KiB.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Ledger {
    version: u16,
    revision: u64,
    skills: Vec<SkillEntry>,
}

impl Default for Ledger {
    fn default() -> Self {
        Self {
            version: 1,
            revision: 0,
            skills: Vec::new(),
        }
    }
}

impl Ledger {
    fn validate(&self) -> Result<(), &'static str> {
        if self.version != 1 || self.skills.len() > SKILLS_MAX {
            return Err("skills_ledger_invalid");
        }
        let mut ids = HashSet::new();
        for entry in &self.skills {
            if !skill_id_ok(&entry.id) || !ids.insert(entry.id.as_str()) {
                return Err("skills_ledger_invalid");
            }
            if entry.versions.len() > VERSIONS_MAX {
                return Err("skills_ledger_invalid");
            }
            let mut versions = HashSet::new();
            for version in &entry.versions {
                if !semver_ok(&version.version)
                    || !versions.insert(version.version.as_str())
                    || !sha_ok(&version.manifest_sha256)
                {
                    return Err("skills_ledger_invalid");
                }
            }
            let enabled: Vec<&VersionEntry> = entry
                .versions
                .iter()
                .filter(|v| v.state == State::Enabled)
                .collect();
            let consistent = match (&entry.active, enabled.as_slice()) {
                (None, []) => true,
                (Some(active), [only]) => *active == only.version,
                _ => false,
            };
            if !consistent {
                return Err("skills_ledger_invalid");
            }
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RunRecord {
    run_id: String,
    skill: String,
    version: String,
    state: String,
    step: Option<String>,
    codes: Vec<String>,
}

/// `skill-runs.json`: outcome of the last 32 runs. No content, no arguments, no outputs.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct RunLedger {
    version: u16,
    revision: u64,
    runs: Vec<RunRecord>,
}

impl Default for RunLedger {
    fn default() -> Self {
        Self {
            version: 1,
            revision: 0,
            runs: Vec::new(),
        }
    }
}

impl RunLedger {
    fn validate(&self) -> Result<(), &'static str> {
        let ok = self.version == 1
            && self.runs.len() <= RUNS_MAX
            && self.runs.iter().all(|r| {
                matches!(r.state.as_str(), "done" | "failed" | "cancelled")
                    && r.codes.len() <= 4
                    && r.codes.iter().all(|c| c.len() <= 64)
                    && r.run_id.len() <= 64
                    && skill_id_ok(&r.skill)
            });
        if ok {
            Ok(())
        } else {
            Err("skill_runs_invalid")
        }
    }
}

// ---------------------------------------------------------------------------
// D1: manifest and validator
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Publisher {
    pub id: String,
    pub name: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Input {
    #[serde(rename = "type")]
    pub kind: String,
    #[serde(default)]
    pub required: bool,
    #[serde(default)]
    pub default: Option<Value>,
    #[serde(default)]
    pub max: Option<i64>,
    #[serde(default)]
    pub min: Option<i64>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Output {
    #[serde(rename = "type")]
    pub kind: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Cond {
    #[serde(rename = "ref")]
    pub reference: String,
    pub op: String,
    #[serde(default)]
    pub value: Option<Value>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Undo {
    pub call: String,
    #[serde(default)]
    pub args: Option<Value>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Step {
    pub id: String,
    pub call: String,
    #[serde(default)]
    pub args: Option<Value>,
    #[serde(default)]
    pub when: Option<Cond>,
    #[serde(default)]
    pub unless: Option<Cond>,
    #[serde(default)]
    pub retries: Option<u8>,
    #[serde(default)]
    pub timeout_ms: Option<u64>,
    #[serde(default)]
    pub idempotent: Option<bool>,
    #[serde(default)]
    pub verify: Option<Cond>,
    #[serde(default)]
    pub undo: Option<Undo>,
    #[serde(default)]
    pub save: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Attestation {
    pub kind: String,
    pub text: String,
}

/// `skill.json`, schema version 1. Every field is strict; unknown keys are refused.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub schema_version: u64,
    pub id: String,
    pub name: String,
    pub version: String,
    pub publisher: Publisher,
    pub description: String,
    pub license: String,
    pub min_runtime: String,
    #[serde(default)]
    pub triggers: Vec<String>,
    #[serde(default)]
    pub inputs: BTreeMap<String, Input>,
    #[serde(default)]
    pub outputs: BTreeMap<String, Output>,
    #[serde(default)]
    pub dependency_capabilities: Vec<String>,
    #[serde(default)]
    pub permissions_required: Vec<String>,
    #[serde(default)]
    pub prerequisites: Vec<String>,
    pub steps: Vec<Step>,
    #[serde(default)]
    pub attestations: Vec<Attestation>,
    #[serde(default)]
    pub readme: Option<String>,
}

/// What the validator needs from the Core: test-mode switch and the latest installed manifest of
/// a skill id (for cycle and depth detection through `skill:` steps).
pub struct Env<'a> {
    pub synthetic: bool,
    pub lookup: &'a dyn Fn(&str) -> Option<Manifest>,
}

pub struct Checked {
    pub manifest: Manifest,
    pub bytes: Vec<u8>,
    pub sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum Target {
    Capability(String),
    Tool(String),
    Skill(String),
    /// S5 operation `conn:<provider>.<operation>`, resolved by the Connection Manager.
    Connection(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum Ref {
    Input(String),
    Step(String, String),
}

fn slug(value: &str, min: usize, max: usize, dash: bool) -> bool {
    let bytes = value.as_bytes();
    (min..=max).contains(&bytes.len())
        && bytes[0].is_ascii_lowercase()
        && bytes.iter().all(|b| {
            b.is_ascii_lowercase() || b.is_ascii_digit() || *b == b'_' || (dash && *b == b'-')
        })
}

fn skill_id_ok(id: &str) -> bool {
    slug(id, 3, 41, false)
}

/// `x.y.z` with each part 0 or up to 5 digits without a leading zero: the same rule as the bridge
/// (app/bridge.py SKILL_SEMVER), so every version the Core stores can be shown in the snapshot.
fn semver_ok(value: &str) -> bool {
    let parts: Vec<&str> = value.split('.').collect();
    parts.len() == 3
        && parts.iter().all(|p| {
            !p.is_empty()
                && p.len() <= 5
                && p.bytes().all(|b| b.is_ascii_digit())
                && (*p == "0" || !p.starts_with('0'))
        })
}

fn sha_ok(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn text_ok(value: &str, max: usize) -> bool {
    !value.is_empty() && value.len() <= max && !value.chars().any(char::is_control)
}

fn semver_tuple(value: &str) -> Option<(u64, u64, u64)> {
    let mut parts = value.split('.').map(|p| p.parse::<u64>().ok());
    let tuple = (parts.next()??, parts.next()??, parts.next()??);
    parts.next().is_none().then_some(tuple)
}

/// Runtime version of this build. A manifest whose `min_runtime` is newer is refused.
pub fn runtime_version() -> (u64, u64, u64) {
    semver_tuple(env!("CARGO_PKG_VERSION")).unwrap_or((0, 0, 0))
}

fn parse_target(call: &str) -> Result<Target, &'static str> {
    if call.starts_with("conn:") {
        return if crate::connections::parse_call(call).is_some() {
            Ok(Target::Connection(call.to_owned()))
        } else {
            Err(E_FIELD)
        };
    }
    if let Some(name) = call.strip_prefix("tool:") {
        return if slug(name, 2, 41, false) {
            Ok(Target::Tool(name.to_owned()))
        } else {
            Err(E_FIELD)
        };
    }
    if let Some(id) = call.strip_prefix("skill:") {
        return if skill_id_ok(id) {
            Ok(Target::Skill(id.to_owned()))
        } else {
            Err(E_ID)
        };
    }
    let (plugin, action) = call.split_once('.').ok_or(E_FIELD)?;
    if action.contains('.') || !slug(plugin, 2, 32, false) || !slug(action, 2, 32, false) {
        return Err(E_FIELD);
    }
    if matches!(plugin, "base" | "core" | "system" | "safety") {
        return Err(E_RESERVED);
    }
    Ok(Target::Capability(call.to_owned()))
}

/// Risk of a registry tool under the given test switch. `None` for unknown names.
fn tool_risk(name: &str, synthetic: bool) -> Option<Risk> {
    tools::risk(name).or_else(|| {
        synthetic
            .then(|| {
                tools::synthetic_risk(name).or_else(|| tools::bridge(name).map(|entry| entry.risk))
            })
            .flatten()
    })
}

/// Risk of a plugin capability. Known bridge capabilities use their registry risk; anything else
/// is treated as state-changing, the conservative default.
fn capability_risk(capability: &str) -> Risk {
    let risks: Vec<Risk> = tools::BRIDGE_REGISTRY
        .iter()
        .filter(|entry| entry.capability == capability)
        .map(|entry| entry.risk)
        .collect();
    if risks.is_empty() {
        Risk::StateChanging
    } else if risks.contains(&Risk::Destructive) {
        Risk::Destructive
    } else if risks.contains(&Risk::StateChanging) {
        Risk::StateChanging
    } else {
        Risk::ReadOnly
    }
}

/// Permission a bridge capability needs from its owner (first registry entry).
fn bridge_permission(capability: &str) -> Option<&'static str> {
    tools::BRIDGE_REGISTRY
        .iter()
        .find(|entry| entry.capability == capability)
        .map(|entry| entry.permission)
}

fn parse_ref(text: &str) -> Result<Ref, &'static str> {
    if let Some(name) = text.strip_prefix("input.") {
        return if slug(name, 1, 32, false) {
            Ok(Ref::Input(name.to_owned()))
        } else {
            Err(E_TEMPLATE)
        };
    }
    if let Some(rest) = text.strip_prefix("steps.") {
        let (id, field) = rest.split_once('.').ok_or(E_TEMPLATE)?;
        return if slug(id, 1, 24, false) && slug(field, 1, 32, false) {
            Ok(Ref::Step(id.to_owned(), field.to_owned()))
        } else {
            Err(E_TEMPLATE)
        };
    }
    Err(E_TEMPLATE)
}

/// Every `${...}` template of one string, in order. Anything else is literal text.
fn template_refs(text: &str) -> Result<Vec<Ref>, &'static str> {
    let mut refs = Vec::new();
    let mut rest = text;
    while let Some(start) = rest.find("${") {
        let after = &rest[start + 2..];
        let end = after.find('}').ok_or(E_TEMPLATE)?;
        refs.push(parse_ref(&after[..end])?);
        rest = &after[end + 1..];
    }
    Ok(refs)
}

/// Strings that look like a path, a URL, or shell syntax are exfiltration attempts.
fn exfiltration_text(text: &str) -> bool {
    text.starts_with('/')
        || text.starts_with('~')
        || text.contains("..")
        || text.contains("://")
        || text.contains("$(")
        || text.contains([';', '|', '`'])
}

fn secret_key(key: &str) -> bool {
    let lower = key.to_ascii_lowercase();
    SECRET_KEYS.iter().any(|needle| lower.contains(needle))
}

fn json_depth(value: &Value) -> usize {
    match value {
        Value::Object(map) => 1 + map.values().map(json_depth).max().unwrap_or(0),
        Value::Array(items) => 1 + items.iter().map(json_depth).max().unwrap_or(0),
        _ => 0,
    }
}

/// A key names a grant when it is listed or merely mentions `grant`/`permission`.
fn grant_key(key: &str) -> bool {
    let lower = key.to_ascii_lowercase();
    GRANT_KEYS.contains(&lower.as_str()) || lower.contains("grant") || lower.contains("permission")
}

fn grant_key_inside(value: &Value) -> bool {
    match value {
        Value::Object(map) => map
            .iter()
            .any(|(key, inner)| grant_key(key) || grant_key_inside(inner)),
        Value::Array(items) => items.iter().any(grant_key_inside),
        _ => false,
    }
}

/// Serde error text to a validator reason. Unknown keys get their own code.
fn classify(error: &serde_json::Error) -> &'static str {
    if error.to_string().contains("unknown field") {
        E_UNKNOWN_KEY
    } else {
        E_FIELD
    }
}

fn scalar(value: &Value) -> bool {
    value.is_string() || value.is_boolean() || value.is_i64() || value.is_u64()
}

/// Full validation of one manifest value. Returns the canonical bytes and their digest.
pub fn check(value: &Value, env: &Env) -> Result<Checked, &'static str> {
    let bytes = serde_json::to_vec(value).map_err(|_| E_FIELD)?;
    if bytes.len() > MANIFEST_MAX {
        return Err(E_OVERSIZE);
    }
    let object = value.as_object().ok_or(E_FIELD)?;
    if object.get("schema_version").and_then(Value::as_u64) != Some(SCHEMA_VERSION) {
        return Err(E_SCHEMA);
    }
    if let Some(steps) = object.get("steps") {
        if grant_key_inside(steps) {
            return Err(E_GRANT);
        }
    }
    let manifest: Manifest = serde_json::from_value(value.clone()).map_err(|e| classify(&e))?;
    fields(&manifest, env)?;
    steps(&manifest, env)?;
    chain(&manifest, env)?;
    let sha256 = sha256_hex(&bytes);
    Ok(Checked {
        manifest,
        bytes,
        sha256,
    })
}

fn fields(m: &Manifest, env: &Env) -> Result<(), &'static str> {
    if !skill_id_ok(&m.id) {
        return Err(E_ID);
    }
    if !text_ok(&m.name, 64) || !text_ok(&m.description, 512) || !text_ok(&m.license, 32) {
        return Err(E_FIELD);
    }
    if !semver_ok(&m.version) {
        return Err(E_VERSION);
    }
    let minimum = semver_tuple(&m.min_runtime).ok_or(E_VERSION)?;
    if minimum > runtime_version() {
        return Err(E_MIN_RUNTIME);
    }
    if !slug(&m.publisher.id, 3, 41, true) {
        return Err(E_PUBLISHER);
    }
    if !text_ok(&m.publisher.name, 64) {
        return Err(E_PUBLISHER);
    }
    if let Some(readme) = &m.readme {
        if readme.len() > 2048 {
            return Err(E_TOO_LONG);
        }
    }
    if m.triggers.len() > 5 {
        return Err(E_FIELD);
    }
    if m.triggers.iter().any(|t| !text_ok(t, 64)) {
        return Err(E_TOO_LONG);
    }
    if m.inputs.len() > LIST_MAX || m.outputs.len() > LIST_MAX {
        return Err(E_FIELD);
    }
    for (name, input) in &m.inputs {
        if !slug(name, 1, 32, false) {
            return Err(E_FIELD);
        }
        match input.kind.as_str() {
            "string" => {
                if input.min.is_some() || input.max.is_some_and(|max| !(1..=512).contains(&max)) {
                    return Err(E_FIELD);
                }
                if let Some(default) = &input.default {
                    if !default.is_string() {
                        return Err(E_FIELD);
                    }
                }
            }
            "int" => {
                if input.min.zip(input.max).is_some_and(|(min, max)| min > max) {
                    return Err(E_FIELD);
                }
                if let Some(default) = &input.default {
                    if !default.is_i64() {
                        return Err(E_FIELD);
                    }
                }
            }
            "bool" => {
                if input.min.is_some() || input.max.is_some() {
                    return Err(E_FIELD);
                }
                if let Some(default) = &input.default {
                    if !default.is_boolean() {
                        return Err(E_FIELD);
                    }
                }
            }
            _ => return Err(E_FIELD),
        }
    }
    for output in m.outputs.values() {
        if !matches!(output.kind.as_str(), "string" | "int" | "bool") {
            return Err(E_FIELD);
        }
    }
    if m.dependency_capabilities.len() > LIST_MAX {
        return Err(E_TOO_MANY_DEPS);
    }
    let mut seen = HashSet::new();
    for dependency in &m.dependency_capabilities {
        if !seen.insert(dependency.as_str()) {
            return Err(E_FIELD);
        }
        match parse_target(dependency)? {
            Target::Tool(name) => {
                if tool_risk(&name, env.synthetic).is_none() {
                    return Err(E_UNKNOWN_TOOL);
                }
            }
            Target::Skill(id) => {
                if id == m.id {
                    return Err(E_CYCLE);
                }
            }
            Target::Capability(_) | Target::Connection(_) => {}
        }
    }
    if m.permissions_required.len() > LIST_MAX
        || m.permissions_required
            .iter()
            .any(|p| !slug(p, 1, 32, false))
    {
        return Err(E_FIELD);
    }
    if m.prerequisites.len() > 4 || m.prerequisites.iter().any(|p| !text_ok(p, 128)) {
        return Err(E_FIELD);
    }
    if m.attestations.len() > 4 {
        return Err(E_FIELD);
    }
    if m.attestations
        .iter()
        .any(|a| !text_ok(&a.kind, 32) || !text_ok(&a.text, 128))
    {
        return Err(E_TOO_LONG);
    }
    Ok(())
}

/// Declared call target: in `dependency_capabilities`, known to the registry, never a cycle.
fn call_target(call: &str, m: &Manifest, env: &Env) -> Result<Target, &'static str> {
    let target = parse_target(call)?;
    match &target {
        Target::Tool(name) => {
            if tool_risk(name, env.synthetic).is_none() {
                return Err(E_UNKNOWN_TOOL);
            }
        }
        Target::Skill(id) => {
            if *id == m.id {
                return Err(E_CYCLE);
            }
        }
        Target::Capability(_) | Target::Connection(_) => {}
    }
    if !m.dependency_capabilities.iter().any(|d| d == call) {
        return Err(E_OUT_OF_SCOPE);
    }
    Ok(target)
}

/// Arguments: object, depth and size caps, no secret-like keys, no exfiltration-like strings, and
/// templates that point only at declared inputs or at `allowed` steps.
fn args_ok(args: &Value, m: &Manifest, allowed: &[String]) -> Result<(), &'static str> {
    if !args.is_object() {
        return Err(E_FIELD);
    }
    if serde_json::to_vec(args).map_err(|_| E_FIELD)?.len() > ARGS_MAX {
        return Err(E_OVERSIZE);
    }
    if json_depth(args) > ARGS_DEPTH_MAX {
        return Err(E_ARGS_DEPTH);
    }
    fn walk(value: &Value, m: &Manifest, allowed: &[String]) -> Result<(), &'static str> {
        match value {
            Value::Object(map) => {
                for (key, inner) in map {
                    if secret_key(key) {
                        return Err(E_EXFIL);
                    }
                    walk(inner, m, allowed)?;
                }
                Ok(())
            }
            Value::Array(items) => items.iter().try_for_each(|v| walk(v, m, allowed)),
            Value::String(text) => {
                if exfiltration_text(text) {
                    return Err(E_EXFIL);
                }
                for reference in template_refs(text)? {
                    match reference {
                        Ref::Input(name) => {
                            if !m.inputs.contains_key(&name) {
                                return Err(E_TEMPLATE);
                            }
                        }
                        Ref::Step(id, _) => {
                            if !allowed.contains(&id) {
                                return Err(E_FUTURE_REF);
                            }
                        }
                    }
                }
                Ok(())
            }
            _ => Ok(()),
        }
    }
    walk(args, m, allowed)
}

fn cond_ok(cond: &Cond, m: &Manifest, allowed: &[String]) -> Result<(), &'static str> {
    match parse_ref(&cond.reference)? {
        Ref::Input(name) => {
            if !m.inputs.contains_key(&name) {
                return Err(E_TEMPLATE);
            }
        }
        Ref::Step(id, _) => {
            if !allowed.contains(&id) {
                return Err(E_FUTURE_REF);
            }
        }
    }
    let valid = match cond.op.as_str() {
        "exists" => cond.value.is_none(),
        "eq" | "ne" => cond.value.as_ref().is_some_and(scalar),
        "gt" | "lt" => cond.value.as_ref().is_some_and(Value::is_i64),
        _ => false,
    };
    if valid {
        Ok(())
    } else {
        Err(E_COND)
    }
}

fn steps(m: &Manifest, env: &Env) -> Result<(), &'static str> {
    if m.steps.is_empty() || m.steps.len() > STEPS_MAX {
        return Err(E_TOO_MANY_STEPS);
    }
    let mut seen = HashSet::new();
    let mut earlier: Vec<String> = Vec::new();
    let mut undo_steps = 0usize;
    for step in &m.steps {
        if !slug(&step.id, 1, 24, false) {
            return Err(E_FIELD);
        }
        if !seen.insert(step.id.as_str()) {
            return Err(E_DUP_STEP);
        }
        let target = call_target(&step.call, m, env)?;
        let args = step.args.clone().unwrap_or_else(|| json!({}));
        args_ok(&args, m, &earlier)?;
        for cond in [&step.when, &step.unless].into_iter().flatten() {
            cond_ok(cond, m, &earlier)?;
        }
        if let Some(cond) = &step.verify {
            let mut allowed = earlier.clone();
            allowed.push(step.id.clone());
            cond_ok(cond, m, &allowed)?;
        }
        if let Some(retries) = step.retries {
            if retries > RETRY_MAX {
                return Err(E_FIELD);
            }
            // A connection write (any class but read) is retried only when its descriptor is idempotent.
            let unsafe_write = match &target {
                Target::Connection(call) => {
                    crate::connections::parse_call(call).is_some_and(|(_, op)| {
                        !op.idempotent && op.risk != crate::connections::Access::Read
                    })
                }
                _ => false,
            };
            if retries > 0 && (step.idempotent != Some(true) || unsafe_write) {
                return Err(E_RETRIES);
            }
        }
        if let Some(timeout) = step.timeout_ms {
            if timeout == 0 || timeout > TIMEOUT_MAX {
                return Err(E_FIELD);
            }
        }
        if let Some(undo) = &step.undo {
            if matches!(target, Target::Skill(_)) {
                return Err(E_FIELD);
            }
            match parse_target(&undo.call)? {
                Target::Skill(_) => return Err(E_FIELD),
                Target::Tool(name) => {
                    if tool_risk(&name, env.synthetic) == Some(Risk::Destructive) {
                        return Err(E_FIELD);
                    }
                    call_target(&undo.call, m, env)?;
                }
                Target::Capability(_) => {
                    call_target(&undo.call, m, env)?;
                }
                // Connection operations are never undone: a write has no automatic inverse.
                Target::Connection(_) => return Err(E_FIELD),
            }
            let mut allowed = earlier.clone();
            allowed.push(step.id.clone());
            args_ok(&undo.args.clone().unwrap_or_else(|| json!({})), m, &allowed)?;
            undo_steps += 1;
        }
        for (output, field) in &step.save {
            if !m.outputs.contains_key(output) || !slug(field, 1, 32, false) {
                return Err(E_SAVE);
            }
        }
        earlier.push(step.id.clone());
    }
    if undo_steps > UNDO_MAX {
        return Err(E_UNDO_LIMIT);
    }
    Ok(())
}

/// Cycle and depth through `skill:` steps, following the latest installed manifest of each child.
fn chain(m: &Manifest, env: &Env) -> Result<(), &'static str> {
    let mut path = vec![m.id.clone()];
    descend(env, &mut path, skill_refs(&m.steps))
}

fn skill_refs(steps: &[Step]) -> Vec<String> {
    steps
        .iter()
        .filter_map(|step| match parse_target(&step.call) {
            Ok(Target::Skill(id)) => Some(id),
            _ => None,
        })
        .collect()
}

fn descend(env: &Env, path: &mut Vec<String>, children: Vec<String>) -> Result<(), &'static str> {
    for child in children {
        if path.contains(&child) {
            return Err(E_CYCLE);
        }
        if path.len() + 1 > CHAIN_MAX {
            return Err(E_DEPTH);
        }
        if let Some(installed) = (env.lookup)(&child) {
            path.push(child);
            let next = skill_refs(&installed.steps);
            let result = descend(env, path, next);
            path.pop();
            result?;
        }
    }
    Ok(())
}

fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

// ---------------------------------------------------------------------------
// Templates and conditions (run time). Only `${input.x}` and `${steps.<id>.<field>}` exist.
// ---------------------------------------------------------------------------

/// Inputs and results visible to one frame. Results are the step outputs of that frame only.
struct Frame {
    skill: String,
    inputs: Map<String, Value>,
    next: usize,
    results: BTreeMap<String, Value>,
    outputs: Map<String, Value>,
    /// Step of the parent frame that waits for this frame, with its view index.
    parent: Option<(String, usize)>,
    /// View of the top-level step this frame belongs to (None for the top frame).
    root_view: Option<usize>,
}

fn lookup(reference: &Ref, frame: &Frame) -> Option<Value> {
    match reference {
        Ref::Input(name) => frame.inputs.get(name).cloned(),
        Ref::Step(id, field) => frame.results.get(id)?.get(field).cloned(),
    }
}

/// Renders one string. A string that is exactly one template keeps the referenced value's type.
fn render(
    text: &str,
    lenient: bool,
    value_of: &dyn Fn(&Ref) -> Result<Value, &'static str>,
) -> Result<Value, &'static str> {
    if let Some(inner) = text
        .strip_prefix("${")
        .and_then(|rest| rest.strip_suffix('}'))
        .filter(|inner| !inner.contains("${") && !inner.contains('}'))
    {
        return value_of(&parse_ref(inner)?);
    }
    let mut out = String::new();
    let mut rest = text;
    while let Some(start) = rest.find("${") {
        out.push_str(&rest[..start]);
        let after = &rest[start + 2..];
        let end = after.find('}').ok_or(E_TEMPLATE)?;
        match value_of(&parse_ref(&after[..end])?)? {
            Value::String(s) => out.push_str(&s),
            Value::Number(n) => out.push_str(&n.to_string()),
            Value::Bool(b) => out.push_str(if b { "true" } else { "false" }),
            // Dry run only: a result that does not exist yet shows as a visible placeholder.
            Value::Null if lenient => out.push_str(&format!("<{}>", &after[..end])),
            _ => return Err("invalid_template"),
        }
        rest = &after[end + 1..];
    }
    out.push_str(rest);
    Ok(Value::String(out))
}

/// Resolves a step argument. `lenient` (dry run) leaves step references as null, because there
/// are no results yet; input references must still exist.
fn resolve(value: &Value, frame: &Frame, lenient: bool) -> Result<Value, &'static str> {
    match value {
        Value::String(text) => {
            let rendered = if text.contains("${") {
                render(
                    text,
                    lenient,
                    &|reference: &Ref| match lookup(reference, frame) {
                        Some(found) => Ok(found),
                        None if lenient && matches!(reference, Ref::Step(..)) => Ok(Value::Null),
                        None => Err("unresolved_ref"),
                    },
                )?
            } else {
                value.clone()
            };
            if let Value::String(out) = &rendered {
                if exfiltration_text(out) {
                    return Err("exfiltration");
                }
            }
            Ok(rendered)
        }
        Value::Array(items) => items
            .iter()
            .map(|item| resolve(item, frame, lenient))
            .collect::<Result<Vec<_>, _>>()
            .map(Value::Array),
        Value::Object(map) => {
            let mut out = Map::new();
            for (key, inner) in map {
                out.insert(key.clone(), resolve(inner, frame, lenient)?);
            }
            Ok(Value::Object(out))
        }
        other => Ok(other.clone()),
    }
}

fn cond_holds(cond: &Cond, frame: &Frame) -> bool {
    let Ok(reference) = parse_ref(&cond.reference) else {
        return false;
    };
    let found = lookup(&reference, frame);
    match (cond.op.as_str(), found, cond.value.as_ref()) {
        ("exists", found, _) => found.is_some(),
        ("eq", Some(found), Some(value)) => found == *value,
        ("ne", Some(found), Some(value)) => found != *value,
        ("ne", None, Some(_)) => true,
        ("gt", Some(found), Some(value)) => match (found.as_i64(), value.as_i64()) {
            (Some(a), Some(b)) => a > b,
            _ => false,
        },
        ("lt", Some(found), Some(value)) => match (found.as_i64(), value.as_i64()) {
            (Some(a), Some(b)) => a < b,
            _ => false,
        },
        _ => false,
    }
}

/// Typed, bounded inputs: unknown names are refused, defaults fill absent optional values.
fn resolve_inputs(
    spec: &BTreeMap<String, Input>,
    given: &Value,
) -> Result<Map<String, Value>, &'static str> {
    if serde_json::to_vec(given)
        .map_err(|_| "invalid_input")?
        .len()
        > ARGS_MAX
    {
        return Err("oversize");
    }
    let object = given.as_object().ok_or("invalid_input")?;
    if object.keys().any(|key| !spec.contains_key(key)) {
        return Err("invalid_input");
    }
    let mut out = Map::new();
    for (name, input) in spec {
        let value = match object.get(name) {
            Some(value) => value.clone(),
            None => match &input.default {
                Some(default) => default.clone(),
                None if input.required => return Err("invalid_input"),
                None => continue,
            },
        };
        let valid = match input.kind.as_str() {
            "string" => value.as_str().is_some_and(|text| {
                text.len() as i64 <= input.max.unwrap_or(TEXT_DEFAULT_MAX)
                    && !text.chars().any(char::is_control)
            }),
            "int" => value.as_i64().is_some_and(|n| {
                input.min.is_none_or(|min| n >= min) && input.max.is_none_or(|max| n <= max)
            }),
            "bool" => value.is_boolean(),
            _ => false,
        };
        if !valid {
            return Err("invalid_input");
        }
        out.insert(name.clone(), value);
    }
    Ok(out)
}

fn retriable(code: &str) -> bool {
    matches!(
        code,
        "timeout" | "busy" | "capability_unavailable" | "executor_failed" | "http_error"
    )
}

// ---------------------------------------------------------------------------
// Runtime state
// ---------------------------------------------------------------------------

/// Public step entry: id (`child/step` when nested), state, code and risk. No args, no content.
/// `risk` and `effect_id` are set on steps that asked for a decision: the step call's risk class
/// (`read`, `state_changing`, `destructive`, as in tool proposals) and, for a registry tool, the
/// closed effect template id (`open_app`, `set_volume`, `mute`, ...).
#[derive(Debug, Clone, Serialize)]
pub struct StepView {
    pub id: String,
    pub state: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code: Option<&'static str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub risk: Option<&'static str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub effect_id: Option<&'static str>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum Await {
    None,
    /// The step at `view` waits for `skill_decide`.
    Decision {
        view: usize,
    },
    /// A plugin capability runs. `view` is None while an undo runs.
    Capability {
        plugin_id: String,
        capability: String,
        view: Option<usize>,
    },
    /// A queued registry tool runs. `view` is None while an undo runs.
    Tool {
        proposal: String,
        view: Option<usize>,
    },
}

struct UndoEntry {
    view: Option<usize>,
    call: String,
    args: Value,
}

struct Run {
    id: String,
    skill: String,
    version: String,
    /// Manifests of the top skill and every nested skill, validated at start.
    nested: BTreeMap<String, Arc<Manifest>>,
    frames: Vec<Frame>,
    steps: Vec<StepView>,
    awaiting: Await,
    /// Decision given for the step at (frame depth, next step, view).
    authorized: Option<(usize, usize, usize)>,
    undo: Vec<UndoEntry>,
    /// Rollback reason once a rollback has started.
    rolling: Option<&'static str>,
    code: Option<&'static str>,
    failed_step: Option<String>,
    codes: Vec<&'static str>,
    attempts: u8,
    deadline: Instant,
    outputs: Option<Value>,
}

/// Snapshot `skills.run`. Outputs are included only when they fit in 1 KiB.
#[derive(Debug, Clone, Serialize)]
pub struct RunView {
    pub run_id: String,
    pub skill: String,
    pub state: &'static str,
    pub step: Option<String>,
    pub steps: Vec<StepView>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub outputs: Option<Value>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Item {
    pub id: String,
    pub name: String,
    pub version: String,
    pub state: State,
    pub source: Source,
    pub active: bool,
    pub deps_ok: bool,
    pub permissions_ok: bool,
    pub missing: Vec<String>,
    /// Permissions the manifest declares (`permissions_required`); empty when the manifest is unreadable.
    pub permissions_required: Vec<String>,
}

/// Display paths of the user's skill folders (absolute, under the data dir). Shown, never read by the UI.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Paths {
    pub imports: String,
    pub exports: String,
}

/// Snapshot `skills`: items, the active run (or null) and the outcome history.
#[derive(Debug, Clone, Serialize)]
pub struct View {
    pub revision: u64,
    pub items: Vec<Item>,
    pub run: Option<RunView>,
    pub history: Vec<RunRecord>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub import: Option<ImportView>,
    pub paths: Paths,
}

/// One scan finding: a validator reason (`skill_invalid:<reason>`) and the part it refers to.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Finding {
    pub code: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub field: Option<&'static str>,
}

/// Snapshot `skills.import` (D4): an unverified preview of a package. Never grants anything.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ImportView {
    pub name: String,
    pub id: String,
    pub version: String,
    pub publisher: String,
    pub unverified: bool,
    pub permissions_required: Vec<String>,
    pub missing_deps: Vec<String>,
    pub permission_delta: Vec<String>,
    pub permissions_escalated: bool,
    pub duplicate: bool,
    pub findings: Vec<Finding>,
}

#[derive(Debug, Clone)]
struct ImportState {
    name: String,
    package_sha256: String,
    view: ImportView,
}

/// Core-owned skill state. Idle and inert until a skill is created.
#[derive(Default)]
pub(crate) struct Engine {
    root: Option<PathBuf>,
    status: &'static str,
    ledger: Ledger,
    runs: RunLedger,
    run: Option<Run>,
    started: u64,
    epoch: u64,
    /// Last import preview (D4). Memory only: a restart drops it, and confirm rescans the file.
    import: Option<ImportState>,
}

impl Engine {
    pub(crate) fn set_boot_seed(&mut self, seed: u64) {
        self.epoch = seed;
    }
    pub(crate) fn is_active(&self) -> bool {
        self.run.is_some()
    }
    pub(crate) fn deadline(&self) -> Option<Instant> {
        self.run.as_ref().map(|run| run.deadline)
    }
    /// Loads both ledgers. A broken ledger quarantines the skill engine only.
    pub(crate) fn configure(&mut self, root: &Path) {
        self.root = Some(root.to_path_buf());
        let ledger = load_json::<Ledger>(root, "skills.json", LEDGER_MAX, Ledger::validate);
        let runs = load_json::<RunLedger>(root, "skill-runs.json", LEDGER_MAX, RunLedger::validate);
        match (ledger, runs) {
            (Ok(ledger), Ok(runs)) => {
                self.ledger = ledger;
                self.runs = runs;
                self.status = "ok";
            }
            _ => self.status = "quarantined",
        }
    }
    /// Newest installed version of a skill, read and hash-checked; used for chain validation.
    fn latest_manifest(&self, id: &str) -> Option<Manifest> {
        let entry = self.ledger.skills.iter().find(|s| s.id == id)?;
        let version = entry.versions.last()?;
        self.read_checked(id, &version.version, &version.manifest_sha256)
            .ok()
            .and_then(|bytes| serde_json::from_slice::<Manifest>(&bytes).ok())
    }
    fn read_checked(&self, id: &str, version: &str, sha: &str) -> Result<Vec<u8>, &'static str> {
        let root = self.root.as_ref().ok_or("skills_unavailable")?;
        let bytes = read_private(&manifest_path(root, id, version), MANIFEST_MAX as u64)
            .map_err(|_| "manifest_unavailable")?
            .ok_or("manifest_unavailable")?;
        if sha256_hex(&bytes) != sha {
            return Err("manifest_mismatch");
        }
        Ok(bytes)
    }
    fn entry(&self, id: &str) -> Option<&SkillEntry> {
        self.ledger.skills.iter().find(|s| s.id == id)
    }
}

fn manifest_path(root: &Path, id: &str, version: &str) -> PathBuf {
    root.join("skills")
        .join(id)
        .join(version)
        .join("skill.json")
}

/// Private read: no symlinks, regular single-link 0600 file owned by us, bounded size.
fn read_private(path: &Path, limit: u64) -> io::Result<Option<Vec<u8>>> {
    let file = match OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)
    {
        Ok(file) => file,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
    };
    crate::storage::validate_opened_private(&file)?;
    let mut bytes = Vec::new();
    file.take(limit + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit {
        return Err(io::Error::other("private file too large"));
    }
    Ok(Some(bytes))
}

/// Atomic private write: pending file (0600, O_NOFOLLOW) then rename, same directory.
fn write_private(path: &Path, bytes: &[u8]) -> io::Result<()> {
    let dir = path.parent().ok_or_else(|| io::Error::other("no parent"))?;
    fs::DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(dir)?;
    let name = path
        .file_name()
        .and_then(|n| n.to_str())
        .ok_or_else(|| io::Error::other("bad name"))?;
    let pending = dir.join(format!(".{name}.pending"));
    let _ = fs::remove_file(&pending);
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(&pending)?;
    let result = (|| {
        file.write_all(bytes)?;
        file.sync_all()?;
        fs::rename(&pending, path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&pending);
    }
    result
}

fn load_json<T: serde::de::DeserializeOwned + Default>(
    root: &Path,
    name: &str,
    limit: usize,
    validate: fn(&T) -> Result<(), &'static str>,
) -> Result<T, &'static str> {
    match read_private(&root.join(name), limit as u64) {
        // A missing ledger is an empty one; a damaged one quarantines the engine.
        Ok(None) => Ok(T::default()),
        Ok(Some(bytes)) => {
            let value: T = serde_json::from_slice(&bytes).map_err(|_| "skills_ledger_invalid")?;
            validate(&value)?;
            Ok(value)
        }
        Err(_) => Err("skills_ledger_invalid"),
    }
}

// ---------------------------------------------------------------------------
// D2: ops. Ledger writes are CAS on the revision and atomic; manifests are private files.
// ---------------------------------------------------------------------------

fn version_mut<'a>(entry: &'a mut SkillEntry, version: &str) -> Option<&'a mut VersionEntry> {
    entry.versions.iter_mut().find(|v| v.version == version)
}

fn entry_mut<'a>(ledger: &'a mut Ledger, id: &str) -> Option<&'a mut SkillEntry> {
    ledger.skills.iter_mut().find(|s| s.id == id)
}

/// Result of dispatching one call: it either waits for a plugin or a queued tool, or it is done.
enum Dispatch {
    Waiting,
    Done(Result<Value, &'static str>),
}

impl Core {
    fn skills_ready(&self) -> Result<(), &'static str> {
        if self.skills.status == "ok" && self.skills.root.is_some() {
            Ok(())
        } else {
            Err("skills_unavailable")
        }
    }

    fn check_revision(&self, revision: u64) -> Result<(), &'static str> {
        self.skills_ready()?;
        if revision == self.skills.ledger.revision {
            Ok(())
        } else {
            Err("stale_skill_revision")
        }
    }

    /// Persists `next` with the next revision, then makes it the in-memory state.
    fn skills_commit(&mut self, mut next: Ledger) -> Result<(), &'static str> {
        next.revision = self
            .skills
            .ledger
            .revision
            .checked_add(1)
            .ok_or("skills_revision_exhausted")?;
        next.validate()?;
        let bytes = serde_json::to_vec(&next).map_err(|_| "skills_storage_error")?;
        if bytes.len() > LEDGER_MAX {
            return Err("skills_ledger_too_large");
        }
        let root = self.skills.root.clone().ok_or("skills_unavailable")?;
        write_private(&root.join("skills.json"), &bytes).map_err(|_| "skills_storage_error")?;
        self.skills.ledger = next;
        Ok(())
    }

    /// Appends one run outcome (no content). Failure to write keeps the in-memory history as it was.
    fn skills_record_run(&mut self, record: RunRecord) {
        let Some(root) = self.skills.root.clone() else {
            return;
        };
        let mut next = self.skills.runs.clone();
        next.runs.push(record);
        while next.runs.len() > RUNS_MAX {
            next.runs.remove(0);
        }
        next.revision = next.revision.saturating_add(1);
        let Ok(bytes) = serde_json::to_vec(&next) else {
            return;
        };
        if bytes.len() <= LEDGER_MAX && write_private(&root.join("skill-runs.json"), &bytes).is_ok()
        {
            self.skills.runs = next;
        }
    }

    fn skill_checked(&self, value: &Value) -> Result<Checked, &'static str> {
        let synthetic = crate::agent::options().synthetic;
        let lookup = |id: &str| self.skills.latest_manifest(id);
        let env = Env {
            synthetic,
            lookup: &lookup,
        };
        check(value, &env)
    }

    /// Owner of a capability: running now, approved permissions, and the bridge permission if any.
    fn capability_owner(&self, capability: &str) -> Result<String, &'static str> {
        let hub = self
            .hub
            .as_ref()
            .filter(|h| h.status == "verified")
            .ok_or("missing_dependency")?;
        let owner = hub
            .entries
            .iter()
            .find(|e| e.capabilities.iter().any(|c| c == capability))
            .ok_or("missing_dependency")?;
        let running = self
            .plugins
            .snapshot(self.hub.as_ref())
            .items
            .iter()
            .any(|item| {
                item.plugin_id == owner.plugin_id && item.enabled && item.state == "running"
            });
        if !running {
            return Err("missing_dependency");
        }
        if !owner.permissions_approved {
            return Err("permission_revoked");
        }
        if bridge_permission(capability).is_some_and(|p| !owner.permissions.iter().any(|x| x == p))
        {
            return Err("permission_revoked");
        }
        Ok(owner.plugin_id.clone())
    }

    fn tool_known(&self, name: &str) -> bool {
        tool_risk(name, crate::agent::options().synthetic).is_some()
    }

    /// Dependencies that are missing now (capabilities, tools, nested skills).
    fn missing_for(&self, manifest: &Manifest) -> Vec<String> {
        manifest
            .dependency_capabilities
            .iter()
            .filter(|dep| match parse_target(dep) {
                Ok(Target::Capability(name)) => self.capability_owner(&name).is_err(),
                Ok(Target::Tool(name)) => !self.tool_known(&name),
                Ok(Target::Connection(call)) => !self.connection_ready(&call),
                Ok(Target::Skill(id)) => self
                    .skills
                    .entry(&id)
                    .and_then(|e| e.active.as_ref())
                    .is_none(),
                Err(_) => true,
            })
            .cloned()
            .collect()
    }

    /// RESOLVE_DEPS: every declared dependency exists now. Nothing is granted here.
    fn deps_ready(&self, manifest: &Manifest) -> Result<(), &'static str> {
        for dependency in &manifest.dependency_capabilities {
            match parse_target(dependency).map_err(|_| "missing_dependency")? {
                Target::Capability(name) => {
                    self.capability_owner(&name)?;
                }
                Target::Tool(name) => {
                    if !self.tool_known(&name) {
                        return Err("missing_dependency");
                    }
                }
                Target::Connection(call) => {
                    if !self.connection_ready(&call) {
                        return Err("missing_dependency");
                    }
                }
                Target::Skill(id) => {
                    if self
                        .skills
                        .entry(&id)
                        .and_then(|e| e.active.as_ref())
                        .is_none()
                    {
                        return Err("missing_dependency");
                    }
                }
            }
        }
        Ok(())
    }

    fn call_risk(&self, call: &str) -> Result<Risk, &'static str> {
        match parse_target(call)? {
            Target::Tool(name) => {
                tool_risk(&name, crate::agent::options().synthetic).ok_or("unknown_tool")
            }
            Target::Capability(name) => Ok(capability_risk(&name)),
            Target::Connection(call) => crate::connections::parse_call(&call)
                .map(|(_, op)| op.risk.tool_risk())
                .ok_or("invalid_call"),
            Target::Skill(_) => Ok(Risk::ReadOnly),
        }
    }

    /// Risk of one step with its resolved arguments. A connection operation is classed from the validated
    /// plan (a `service.call` to `lock.unlock`, an MCP tool that deletes, a public issue), the same way the
    /// agent path classes it at authorize time. Other targets use their static class.
    fn step_risk(&self, call: &str, args: &Value) -> Result<Risk, &'static str> {
        match parse_target(call)? {
            Target::Connection(call) => {
                let (provider, op) = crate::connections::parse_call(&call).ok_or("invalid_call")?;
                self.connections
                    .plan(provider, op, None, args)
                    .map(|plan| plan.tool_risk())
            }
            _ => self.call_risk(call),
        }
    }

    fn destructive_blocked(&self, manifest: &Manifest) -> bool {
        !crate::agent::options().allow_destructive
            && manifest
                .steps
                .iter()
                .any(|step| self.call_risk(&step.call) == Ok(Risk::Destructive))
    }

    fn load_manifest(&self, id: &str, record: &VersionEntry) -> Result<Manifest, &'static str> {
        let bytes = self
            .skills
            .read_checked(id, &record.version, &record.manifest_sha256)?;
        let value: Value = serde_json::from_slice(&bytes).map_err(|_| "manifest_unavailable")?;
        self.skill_checked(&value).map(|checked| checked.manifest)
    }

    /// Active record of an installed skill, or None.
    fn active_record(&self, id: &str) -> Option<VersionEntry> {
        let entry = self.skills.entry(id)?;
        let active = entry.active.as_ref()?;
        entry
            .versions
            .iter()
            .find(|v| &v.version == active)
            .cloned()
    }

    /// Top skill plus every nested skill (active versions), each re-validated. Depth and cycles
    /// are refused here too, so a run never starts from a tree the validator would reject.
    fn load_tree(
        &self,
        id: &str,
        record: &VersionEntry,
    ) -> Result<BTreeMap<String, Arc<Manifest>>, &'static str> {
        let top = self.load_manifest(id, record)?;
        let mut nested = BTreeMap::new();
        let mut path = vec![id.to_owned()];
        self.collect_nested(&top, &mut path, &mut nested)?;
        nested.insert(id.to_owned(), Arc::new(top));
        Ok(nested)
    }

    fn collect_nested(
        &self,
        manifest: &Manifest,
        path: &mut Vec<String>,
        out: &mut BTreeMap<String, Arc<Manifest>>,
    ) -> Result<(), &'static str> {
        for child in skill_refs(&manifest.steps) {
            if path.contains(&child) {
                return Err("cycle");
            }
            if path.len() + 1 > CHAIN_MAX {
                return Err("depth");
            }
            if out.contains_key(&child) {
                continue;
            }
            let record = self.active_record(&child).ok_or("missing_dependency")?;
            let loaded = self.load_manifest(&child, &record)?;
            path.push(child.clone());
            self.collect_nested(&loaded, path, out)?;
            path.pop();
            out.insert(child, Arc::new(loaded));
        }
        Ok(())
    }

    // ----- ops ---------------------------------------------------------------

    pub(crate) fn skill_validate(&mut self, value: Value) -> &'static str {
        if let Err(code) = self.skills_ready() {
            return code;
        }
        match self.skill_checked(&value) {
            Ok(_) => {
                self.emit(String::new(), None, "skill_validated");
                "ok"
            }
            Err(code) => code,
        }
    }

    /// Validates, then stores the manifest as `validated`. A locked version is never replaced.
    pub(crate) fn skill_save_draft(&mut self, value: Value) -> &'static str {
        if let Err(code) = self.skills_ready() {
            return code;
        }
        let checked = match self.skill_checked(&value) {
            Ok(checked) => checked,
            Err(code) => return code,
        };
        let Some(root) = self.skills.root.clone() else {
            return "skills_unavailable";
        };
        let id = checked.manifest.id.clone();
        let version = checked.manifest.version.clone();
        let mut next = self.skills.ledger.clone();
        if next.skills.iter().all(|s| s.id != id) {
            if next.skills.len() >= SKILLS_MAX {
                return E_SKILL_LIMIT;
            }
            next.skills.push(SkillEntry {
                id: id.clone(),
                versions: Vec::new(),
                active: None,
            });
        }
        let Some(entry) = entry_mut(&mut next, &id) else {
            return "skills_storage_error";
        };
        match version_mut(entry, &version) {
            Some(existing) => {
                if existing.state.locked() {
                    return E_LOCKED;
                }
                existing.manifest_sha256 = checked.sha256.clone();
                existing.state = State::Validated;
                existing.source = Source::Created;
                existing.approved_at_rev = None;
            }
            None => {
                if entry.versions.len() >= VERSIONS_MAX {
                    return E_VERSION_LIMIT;
                }
                entry.versions.push(VersionEntry {
                    version: version.clone(),
                    manifest_sha256: checked.sha256.clone(),
                    state: State::Validated,
                    source: Source::Created,
                    approved_at_rev: None,
                });
            }
        }
        if write_private(&manifest_path(&root, &id, &version), &checked.bytes).is_err() {
            return "skills_storage_error";
        }
        match self.skills_commit(next) {
            Ok(()) => {
                self.emit(String::new(), None, "skill_validated");
                "ok"
            }
            Err(code) => code,
        }
    }

    /// Simulation checks: dependencies, the destructive switch, the inputs, and every template that
    /// does not depend on a previous result. Makes zero capability calls and writes nothing.
    /// Returns the version state and the number of steps.
    fn dry_run_check(
        &self,
        id: &str,
        version: &str,
        inputs: Value,
    ) -> Result<(State, usize), &'static str> {
        self.skills_ready()?;
        let record = self
            .skills
            .entry(id)
            .and_then(|e| e.versions.iter().find(|v| v.version == version))
            .cloned()
            .ok_or("unknown_version")?;
        let manifest = self.load_manifest(id, &record)?;
        let inputs = resolve_inputs(&manifest.inputs, &inputs)?;
        self.deps_ready(&manifest)?;
        if self.destructive_blocked(&manifest) {
            return Err("destructive_disabled");
        }
        let frame = Frame {
            skill: id.to_owned(),
            inputs,
            next: 0,
            results: BTreeMap::new(),
            outputs: Map::new(),
            parent: None,
            root_view: None,
        };
        for step in &manifest.steps {
            let args = step.args.clone().unwrap_or_else(|| json!({}));
            resolve(&args, &frame, true)?;
        }
        Ok((record.state, manifest.steps.len()))
    }

    /// User simulation (`skill_dry_run`). A passing run marks a draft or validated version `tested`.
    pub(crate) fn skill_dry_run(&mut self, id: &str, version: &str, inputs: Value) -> &'static str {
        let (state, _) = match self.dry_run_check(id, version, inputs) {
            Ok(checked) => checked,
            Err(code) => return code,
        };
        if matches!(state, State::Draft | State::Validated) {
            let mut next = self.skills.ledger.clone();
            if let Some(v) = entry_mut(&mut next, id).and_then(|e| version_mut(e, version)) {
                v.state = State::Tested;
            }
            if let Err(code) = self.skills_commit(next) {
                return code;
            }
        }
        "ok"
    }

    pub(crate) fn skill_approve(&mut self, id: &str, version: &str, revision: u64) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        let approved_at = self.skills.ledger.revision.saturating_add(1);
        let mut next = self.skills.ledger.clone();
        let Some(record) = entry_mut(&mut next, id).and_then(|e| version_mut(e, version)) else {
            return "unknown_version";
        };
        if record.state != State::Tested {
            return "skill_not_tested";
        }
        record.state = State::Approved;
        record.approved_at_rev = Some(approved_at);
        match self.skills_commit(next) {
            Ok(()) => {
                self.emit(String::new(), None, "skill_approved");
                "ok"
            }
            Err(code) => code,
        }
    }

    /// Enables the newest approved (or previously disabled) version. The previous active version
    /// becomes `revised`, which is the rollback target.
    pub(crate) fn skill_enable(&mut self, id: &str, revision: u64) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        let mut next = self.skills.ledger.clone();
        let Some(entry) = entry_mut(&mut next, id) else {
            return "unknown_skill";
        };
        let candidate = entry
            .versions
            .iter()
            .filter(|v| matches!(v.state, State::Approved | State::Disabled))
            .max_by_key(|v| v.approved_at_rev.unwrap_or(0))
            .map(|v| v.version.clone());
        let Some(candidate) = candidate else {
            return if entry.active.is_some() {
                "already_enabled"
            } else {
                "skill_not_approved"
            };
        };
        if let Some(previous) = entry.active.take() {
            if let Some(v) = version_mut(entry, &previous) {
                v.state = State::Revised;
            }
        }
        if let Some(v) = version_mut(entry, &candidate) {
            v.state = State::Enabled;
        }
        entry.active = Some(candidate);
        match self.skills_commit(next) {
            Ok(()) => {
                self.emit(String::new(), None, "skill_enabled");
                "ok"
            }
            Err(code) => code,
        }
    }

    pub(crate) fn skill_disable(&mut self, id: &str, revision: u64) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        let mut next = self.skills.ledger.clone();
        let Some(entry) = entry_mut(&mut next, id) else {
            return "unknown_skill";
        };
        let Some(active) = entry.active.take() else {
            return "skill_not_enabled";
        };
        if let Some(v) = version_mut(entry, &active) {
            v.state = State::Disabled;
        }
        if let Err(code) = self.skills_commit(next) {
            return code;
        }
        if self.skills.run.as_ref().is_some_and(|r| r.skill == id) {
            self.skill_start_rollback("skill_disabled");
        }
        "ok"
    }

    /// Switches back to the previous version (the nearest earlier approved, disabled or revised one).
    pub(crate) fn skill_rollback_version(&mut self, id: &str, revision: u64) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        let mut next = self.skills.ledger.clone();
        let Some(entry) = entry_mut(&mut next, id) else {
            return "unknown_skill";
        };
        let Some(active) = entry.active.clone() else {
            return "skill_not_enabled";
        };
        let Some(index) = entry.versions.iter().position(|v| v.version == active) else {
            return "skills_ledger_invalid";
        };
        let previous = entry.versions[..index]
            .iter()
            .rev()
            .find(|v| matches!(v.state, State::Approved | State::Disabled | State::Revised))
            .map(|v| v.version.clone());
        let Some(previous) = previous else {
            return "no_previous_version";
        };
        if let Some(v) = version_mut(entry, &active) {
            v.state = State::Revised;
        }
        if let Some(v) = version_mut(entry, &previous) {
            v.state = State::Enabled;
        }
        entry.active = Some(previous);
        if let Err(code) = self.skills_commit(next) {
            return code;
        }
        if self.skills.run.as_ref().is_some_and(|r| r.skill == id) {
            self.skill_start_rollback("skill_version_changed");
        }
        "ok"
    }

    pub(crate) fn skill_remove(&mut self, id: &str, revision: u64) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        if self.skills.run.as_ref().is_some_and(|r| r.skill == id) {
            return "skill_busy";
        }
        if self.skills.entry(id).is_none() {
            return "unknown_skill";
        }
        let mut next = self.skills.ledger.clone();
        next.skills.retain(|s| s.id != id);
        if let Err(code) = self.skills_commit(next) {
            return code;
        }
        if let Some(root) = self.skills.root.clone() {
            let _ = fs::remove_dir_all(root.join("skills").join(id));
        }
        "ok"
    }

    /// `skill_run`: only an enabled skill whose dependencies hold may start. One run at a time.
    pub(crate) fn skill_run(&mut self, id: &str, inputs: Value) -> &'static str {
        if let Err(code) = self.skills_ready() {
            return code;
        }
        if self.voice_active() {
            return "busy";
        }
        if self.agent.is_active() {
            return "agent_busy";
        }
        if self.skills.run.is_some() {
            return "skill_busy";
        }
        if self.skills.entry(id).is_none() {
            return "unknown_skill";
        }
        let Some(record) = self.active_record(id) else {
            return "skill_not_enabled";
        };
        if record.state != State::Enabled {
            return "skill_not_enabled";
        }
        let nested = match self.load_tree(id, &record) {
            Ok(nested) => nested,
            Err(code) => return code,
        };
        let Some(top) = nested.get(id).cloned() else {
            return "manifest_unavailable";
        };
        let inputs = match resolve_inputs(&top.inputs, &inputs) {
            Ok(inputs) => inputs,
            Err(code) => return code,
        };
        for manifest in nested.values() {
            if let Err(code) = self.deps_ready(manifest) {
                return code;
            }
            if self.destructive_blocked(manifest) {
                return "destructive_disabled";
            }
        }
        self.skills.started += 1;
        let run_id = format!("skill_{:x}_{}", self.skills.epoch, self.skills.started);
        self.skills.run = Some(Run {
            id: run_id.clone(),
            skill: id.to_owned(),
            version: record.version.clone(),
            nested,
            frames: vec![Frame {
                skill: id.to_owned(),
                inputs,
                next: 0,
                results: BTreeMap::new(),
                outputs: Map::new(),
                parent: None,
                root_view: None,
            }],
            steps: Vec::new(),
            awaiting: Await::None,
            authorized: None,
            undo: Vec::new(),
            rolling: None,
            code: None,
            failed_step: None,
            codes: Vec::new(),
            attempts: 0,
            deadline: Instant::now() + RUN_DEADLINE,
            outputs: None,
        });
        self.emit(String::new(), None, "skill_run_started");
        self.skill_drive();
        "ok"
    }

    /// `skill_decide`: the user's answer for a step that changes state. Only that step may move.
    pub(crate) fn skill_decide(
        &mut self,
        run_id: &str,
        step: &str,
        decision: ToolDecision,
    ) -> &'static str {
        let Some(run) = self.skills.run.as_ref().filter(|r| r.id == run_id) else {
            return "unknown_run";
        };
        let Await::Decision { view } = run.awaiting else {
            return "not_awaiting";
        };
        if run.steps.get(view).map(|s| s.id.as_str()) != Some(step) {
            return "unknown_step";
        }
        let depth = run.frames.len();
        let next = run.frames.last().map_or(0, |f| f.next);
        if let Some(run) = self.skills.run.as_mut() {
            run.awaiting = Await::None;
            match decision {
                ToolDecision::Authorize => {
                    run.authorized = Some((depth, next, view));
                    run.steps[view].state = "running";
                }
                ToolDecision::Deny => {}
            }
        }
        match decision {
            ToolDecision::Authorize => self.skill_drive(),
            ToolDecision::Deny => {
                self.skill_fail(view, "denied_by_user");
                self.skill_drive();
            }
        }
        "ok"
    }

    pub(crate) fn skill_cancel(&mut self, run_id: &str) -> &'static str {
        match self.skills.run.as_ref() {
            Some(run) if run.id == run_id => {}
            _ => return "unknown_run",
        }
        self.skill_start_rollback("cancelled");
        "ok"
    }

    // ----- executor -----------------------------------------------------------

    fn set_awaiting(&mut self, awaiting: Await) {
        if let Some(run) = self.skills.run.as_mut() {
            run.awaiting = awaiting;
        }
    }

    fn push_view(&mut self, id: String, state: &'static str) -> usize {
        let Some(run) = self.skills.run.as_mut() else {
            return 0;
        };
        run.steps.push(StepView {
            id,
            state,
            code: None,
            risk: None,
            effect_id: None,
        });
        run.steps.len() - 1
    }

    /// Records the risk class and effect id of a step that waits for a decision (public fields only).
    fn set_decision_meta(
        &mut self,
        view: usize,
        risk: &'static str,
        effect_id: Option<&'static str>,
    ) {
        if let Some(step) = self
            .skills
            .run
            .as_mut()
            .and_then(|run| run.steps.get_mut(view))
        {
            step.risk = Some(risk);
            step.effect_id = effect_id;
        }
    }

    fn set_view(&mut self, view: usize, state: &'static str, code: Option<&'static str>) {
        if let Some(step) = self
            .skills
            .run
            .as_mut()
            .and_then(|run| run.steps.get_mut(view))
        {
            step.state = state;
            step.code = code;
        }
    }

    /// The step the top frame is at, from the validated manifest.
    fn current_step(&self) -> Option<Step> {
        let run = self.skills.run.as_ref()?;
        let frame = run.frames.last()?;
        run.nested.get(&frame.skill)?.steps.get(frame.next).cloned()
    }

    /// Runs steps of the top frame until something has to wait, or the run ends. Nested steps
    /// report through the view of their top-level step, so snapshot ids stay unique and valid.
    fn skill_drive(&mut self) {
        loop {
            let Some(run) = self.skills.run.as_ref() else {
                return;
            };
            if run.rolling.is_some() {
                self.skill_rollback();
                return;
            }
            if run.awaiting != Await::None {
                return;
            }
            let Some(frame) = run.frames.last() else {
                return;
            };
            let depth = run.frames.len();
            let Some(manifest) = run.nested.get(&frame.skill).cloned() else {
                self.skill_start_rollback("missing_dependency");
                return;
            };
            if frame.next >= manifest.steps.len() {
                self.skill_frame_done();
                continue;
            }
            let next = frame.next;
            let root = frame.root_view;
            let step = manifest.steps[next].clone();
            if skip_step(&step, frame) {
                self.advance_frame();
                continue;
            }
            let args = resolve(
                &step.args.clone().unwrap_or_else(|| json!({})),
                frame,
                false,
            );
            let args = match args {
                Ok(args) => args,
                Err(code) => {
                    let view = self.view_for(root, &step.id, "failed");
                    self.skill_fail(view, code);
                    continue;
                }
            };
            let undo_full = self
                .skills
                .run
                .as_ref()
                .is_some_and(|run| run.undo.len() >= UNDO_MAX);
            if step.undo.is_some() && undo_full {
                let view = self.view_for(root, &step.id, "failed");
                self.skill_fail(view, "undo_limit");
                continue;
            }
            if let Ok(Target::Skill(child)) = parse_target(&step.call) {
                let view = self.view_for(root, &step.id, "running");
                match self.enter_nested(&child, depth, &args) {
                    Ok(mut frame) => {
                        frame.parent = Some((step.id.clone(), view));
                        frame.root_view = Some(root.unwrap_or(view));
                        if let Some(run) = self.skills.run.as_mut() {
                            run.frames.push(frame);
                        }
                    }
                    Err(code) => self.skill_fail(view, code),
                }
                continue;
            }
            let risk = match self.step_risk(&step.call, &args) {
                Ok(risk) => risk,
                Err(code) => {
                    let view = self.view_for(root, &step.id, "failed");
                    self.skill_fail(view, code);
                    continue;
                }
            };
            if risk == Risk::Destructive && !crate::agent::options().allow_destructive {
                let view = self.view_for(root, &step.id, "failed");
                self.skill_fail(view, "destructive_disabled");
                continue;
            }
            let view = if risk == Risk::ReadOnly {
                self.view_for(root, &step.id, "running")
            } else if let Some(view) = self.take_authorization(depth, next) {
                self.set_view(view, "running", None);
                view
            } else {
                let view = self.view_for(root, &step.id, "awaiting_decision");
                // Same vocabulary as tool proposals: the call's risk class and, for a registry tool, its effect.
                let effect_id = match parse_target(&step.call) {
                    Ok(Target::Tool(name)) => {
                        crate::tools::effect(&name, &args).map(|effect| effect.id)
                    }
                    _ => None,
                };
                self.set_decision_meta(view, risk.name(), effect_id);
                self.set_awaiting(Await::Decision { view });
                return;
            };
            let timeout = step.timeout_ms.unwrap_or(STEP_TIMEOUT_MS);
            match self.exec_call(&step.call, args, timeout, Some(view)) {
                Dispatch::Waiting => return,
                Dispatch::Done(Ok(result)) => self.skill_complete(view, result, false),
                Dispatch::Done(Err(code)) => self.skill_fail(view, code),
            }
        }
    }

    /// View a step reports through: its top-level step's view for nested steps, otherwise the
    /// newest view with that id if it is being retried, otherwise a new one. Sets its state.
    fn view_for(&mut self, root: Option<usize>, id: &str, state: &'static str) -> usize {
        if let Some(root) = root {
            self.set_view(root, state, None);
            return root;
        }
        let retrying = self.skills.run.as_ref().and_then(|run| {
            run.steps
                .iter()
                .rposition(|s| s.id == id && s.state == "retrying")
        });
        match retrying {
            Some(index) => {
                self.set_view(index, state, None);
                index
            }
            None => self.push_view(id.to_owned(), state),
        }
    }

    fn take_authorization(&mut self, depth: usize, next: usize) -> Option<usize> {
        let run = self.skills.run.as_mut()?;
        match run.authorized {
            Some((d, n, view)) if d == depth && n == next => {
                run.authorized = None;
                Some(view)
            }
            _ => None,
        }
    }

    fn advance_frame(&mut self) {
        if let Some(frame) = self.skills.run.as_mut().and_then(|r| r.frames.last_mut()) {
            frame.next += 1;
        }
        if let Some(run) = self.skills.run.as_mut() {
            run.attempts = 0;
        }
    }

    /// Frame of a nested skill: inputs typed and bounded, depth checked again at run time.
    fn enter_nested(&self, child: &str, depth: usize, args: &Value) -> Result<Frame, &'static str> {
        if depth + 1 > CHAIN_MAX {
            return Err("depth");
        }
        let run = self.skills.run.as_ref().ok_or("skills_unavailable")?;
        let manifest = run.nested.get(child).ok_or("missing_dependency")?;
        let inputs = resolve_inputs(&manifest.inputs, args)?;
        Ok(Frame {
            skill: child.to_owned(),
            inputs,
            next: 0,
            results: BTreeMap::new(),
            outputs: Map::new(),
            parent: None,
            root_view: None,
        })
    }

    /// The top frame has no step left: a nested frame returns its outputs, the top one commits.
    fn skill_frame_done(&mut self) {
        let Some(run) = self.skills.run.as_mut() else {
            return;
        };
        if run.frames.len() <= 1 {
            if let Some(frame) = run.frames.pop() {
                run.outputs = Some(Value::Object(frame.outputs));
            }
            self.skill_finish();
            return;
        }
        let Some(child) = run.frames.pop() else {
            return;
        };
        let Some((_, view)) = child.parent else {
            return;
        };
        self.skill_complete(view, Value::Object(child.outputs), false);
    }

    /// Output of a step is accepted: undo is registered first, then verify and save. Only a
    /// top-level step moves its view to `done`; nested steps move their frame.
    fn skill_complete(&mut self, view: usize, result: Value, rolling: bool) {
        let Some(step) = self.current_step() else {
            return;
        };
        let Some(scratch) = self.skills.run.as_ref().and_then(|run| {
            let frame = run.frames.last()?;
            let mut results = frame.results.clone();
            results.insert(step.id.clone(), result.clone());
            Some(Frame {
                skill: frame.skill.clone(),
                inputs: frame.inputs.clone(),
                next: frame.next,
                results,
                outputs: Map::new(),
                parent: None,
                root_view: None,
            })
        }) else {
            return;
        };
        if let Some(undo) = &step.undo {
            match resolve(
                &undo.args.clone().unwrap_or_else(|| json!({})),
                &scratch,
                false,
            ) {
                Ok(args) => {
                    if let Some(run) = self.skills.run.as_mut() {
                        run.undo.push(UndoEntry {
                            view: Some(view),
                            call: undo.call.clone(),
                            args,
                        });
                    }
                }
                Err(code) => {
                    if !rolling {
                        self.skill_fail(view, code);
                    }
                    return;
                }
            }
        }
        if rolling {
            return;
        }
        if let Some(cond) = &step.verify {
            if !cond_holds(cond, &scratch) {
                self.skill_fail(view, "verify_failed");
                return;
            }
        }
        let mut saved = Vec::new();
        for (output, field) in &step.save {
            match result.get(field) {
                Some(value) if scalar(value) => saved.push((output.clone(), value.clone())),
                _ => {
                    self.skill_fail(view, "invalid_output");
                    return;
                }
            }
        }
        let top = match self.skills.run.as_mut() {
            Some(run) => {
                if let Some(frame) = run.frames.last_mut() {
                    frame.results.insert(step.id.clone(), result);
                    frame.outputs.extend(saved);
                }
                run.frames.len() == 1
            }
            None => return,
        };
        self.advance_frame();
        if top {
            self.set_view(view, "done", None);
        }
        self.emit(String::new(), None, "skill_step");
    }

    /// A failed step is retried when the code is transient and retries remain (same view, and the
    /// same authorization for state changes). Otherwise the run starts its rollback.
    fn skill_fail(&mut self, view: usize, code: &'static str) {
        let Some(step) = self.current_step() else {
            return;
        };
        let risk = self.call_risk(&step.call).unwrap_or(Risk::ReadOnly);
        let Some(run) = self.skills.run.as_mut() else {
            return;
        };
        if run.rolling.is_some() {
            return;
        }
        if retriable(code) && step.retries.unwrap_or(0) > run.attempts {
            run.attempts += 1;
            run.awaiting = Await::None;
            if risk != Risk::ReadOnly {
                let depth = run.frames.len();
                let next = run.frames.last().map_or(0, |f| f.next);
                run.authorized = Some((depth, next, view));
            }
            self.set_view(view, "retrying", Some(code));
            return;
        }
        run.codes.push(code);
        run.failed_step = run.steps.get(view).map(|s| s.id.clone());
        run.awaiting = Await::None;
        self.set_view(view, "failed", Some(code));
        self.skill_start_rollback(code);
    }

    /// Executes one call without any user decision (decisions are taken before this).
    fn exec_call(
        &mut self,
        call: &str,
        args: Value,
        timeout: u64,
        view: Option<usize>,
    ) -> Dispatch {
        match parse_target(call) {
            Ok(Target::Capability(capability)) => {
                let plugin_id = match self.capability_owner(&capability) {
                    Ok(plugin_id) => plugin_id,
                    Err(code) => return Dispatch::Done(Err(code)),
                };
                match self
                    .plugins
                    .invoke(self.hub.as_ref(), &capability, args, timeout, &self.llm)
                {
                    Ok(()) => {
                        self.set_awaiting(Await::Capability {
                            plugin_id,
                            capability,
                            view,
                        });
                        Dispatch::Waiting
                    }
                    Err(code) => Dispatch::Done(Err(code)),
                }
            }
            Ok(Target::Tool(name)) => self.exec_tool(&name, args, view),
            Ok(Target::Connection(call)) => self.exec_connection(&call, args, view),
            _ => Dispatch::Done(Err("invalid_call")),
        }
    }

    /// Whether a `conn:` dependency has a connected grant for its scope right now.
    fn connection_ready(&self, call: &str) -> bool {
        crate::connections::parse_call(call)
            .is_some_and(|(provider, op)| self.connections.dependency_ready(provider.id, op.name))
    }

    /// S5 operation from a skill step. The skill's own decision already approved the step, so the
    /// call starts now; its proposal settles through `skill_tool_settled` like a registry tool.
    fn exec_connection(&mut self, call: &str, args: Value, view: Option<usize>) -> Dispatch {
        let Some((provider, op)) = crate::connections::parse_call(call) else {
            return Dispatch::Done(Err("invalid_call"));
        };
        let plan = match self.connections.plan(provider, op, None, &args) {
            Ok(plan) => plan.from_skill(),
            Err(code) => return Dispatch::Done(Err(code)),
        };
        // Destructive and public operations never run from a skill step unless destructive runs are enabled
        // (the agent path answers the same way). `start` adds the public switch on top.
        if plan.tool_risk() == Risk::Destructive && !crate::agent::options().allow_destructive {
            return Dispatch::Done(Err("destructive_disabled"));
        }
        let proposal = self.tools.propose(
            ENGINE_OWNER,
            String::new(),
            call.to_owned(),
            plan.wrap(),
            Instant::now(),
        );
        self.tools
            .set_connection(&proposal, &plan.account, op.name, plan.risk.name());
        match self
            .connections
            .start(&self.llm, plan, Some(proposal.clone()), Instant::now())
        {
            Ok(()) => {
                self.tools
                    .set(&proposal, tools::State::Authorized, None, None);
                self.set_awaiting(Await::Tool { proposal, view });
                Dispatch::Waiting
            }
            Err(code) => {
                self.tools
                    .set(&proposal, tools::State::Failed, Some(code), None);
                Dispatch::Done(Err(code))
            }
        }
    }

    /// Registry tools: bridge and synthetic tools run here (owner checked); C1 tools queue on the
    /// tool ledger and finish through `skill_tool_settled`.
    fn exec_tool(&mut self, name: &str, args: Value, view: Option<usize>) -> Dispatch {
        let options = crate::agent::options();
        if let Some(bridge) = tools::bridge(name).filter(|_| options.synthetic) {
            if let Err(code) = self.bridge_owner(bridge) {
                return Dispatch::Done(Err(code));
            }
            self.emit(String::new(), None, world::audit_kind(bridge.service));
            return Dispatch::Done(world::serve(&world::dir(), bridge.service, &args));
        }
        if tools::synthetic_risk(name).is_some() && options.synthetic {
            return match crate::agent::synth_validate(name, &args) {
                Ok((op, _)) => {
                    let outcome =
                        crate::agent::synth_exec(&op, &world::dir(), options.allow_destructive);
                    if outcome.state == tools::State::Executed {
                        Dispatch::Done(Ok(outcome
                            .observation
                            .get("result")
                            .cloned()
                            .unwrap_or(Value::Null)))
                    } else {
                        Dispatch::Done(Err(outcome.reason.unwrap_or("failed")))
                    }
                }
                Err(code) => Dispatch::Done(Err(code)),
            };
        }
        if tools::risk(name).is_some() {
            let (command, _) = match tools::command(name, &args) {
                Ok(verdict) => verdict,
                Err(code) => return Dispatch::Done(Err(code)),
            };
            if !self.tools.enabled() {
                return Dispatch::Done(Err("executor_unavailable"));
            }
            if self.voice_active() {
                return Dispatch::Done(Err("busy"));
            }
            let proposal = self.tools.propose(
                ENGINE_OWNER,
                String::new(),
                name.to_owned(),
                args,
                Instant::now(),
            );
            if self.tools.queue(&proposal, command) {
                self.set_awaiting(Await::Tool { proposal, view });
                return Dispatch::Waiting;
            }
            self.tools
                .set(&proposal, tools::State::Failed, Some("busy"), None);
            return Dispatch::Done(Err("busy"));
        }
        Dispatch::Done(Err("unknown_tool"))
    }

    /// Outcome of the awaited call. During a rollback it only advances the undo sequence.
    fn skill_settle(&mut self, view: Option<usize>, outcome: Result<Value, &'static str>) {
        let rolling = match self.skills.run.as_mut() {
            Some(run) => {
                run.awaiting = Await::None;
                run.rolling.is_some()
            }
            None => return,
        };
        if rolling {
            match (view, outcome) {
                (Some(view), Ok(result)) => self.skill_complete(view, result, true),
                (None, Err(_)) => {
                    if let Some(run) = self.skills.run.as_mut() {
                        run.codes.push("undo_failed");
                    }
                }
                _ => {}
            }
            self.skill_rollback();
            return;
        }
        match (view, outcome) {
            (Some(view), Ok(result)) => self.skill_complete(view, result, false),
            (Some(view), Err(code)) => self.skill_fail(view, code),
            (None, _) => {}
        }
        self.skill_drive();
    }

    /// Host hook: a capability result for the awaited invocation.
    pub(crate) fn skill_on_result(&mut self) {
        let Some(run) = self.skills.run.as_ref() else {
            return;
        };
        let Await::Capability {
            plugin_id,
            capability,
            view,
        } = run.awaiting.clone()
        else {
            return;
        };
        let Some(last) = self.plugins.last().cloned() else {
            return;
        };
        if last.plugin_id != plugin_id || last.capability != capability {
            return;
        }
        self.plugins.clear_last();
        let outcome = if last.ok {
            last.output.ok_or("invalid_output")
        } else {
            Err(last.error.unwrap_or("capability_unavailable"))
        };
        self.skill_settle(view, outcome);
    }

    /// Host hook: a queued registry tool finished (the C1 executor replied).
    pub(crate) fn skill_tool_settled(&mut self, proposal: &str) {
        let Some(run) = self.skills.run.as_ref() else {
            return;
        };
        let Await::Tool {
            proposal: awaited,
            view,
        } = run.awaiting.clone()
        else {
            return;
        };
        if awaited != proposal {
            return;
        }
        let Some(record) = self.tools.view(proposal).cloned() else {
            return;
        };
        let outcome = match record.state {
            tools::State::Executed => Ok(json!({"result": record.result.unwrap_or_default()})),
            tools::State::Pending | tools::State::Authorized => return,
            _ => Err(record.reason.unwrap_or("failed")),
        };
        self.skill_settle(view, outcome);
    }

    /// Begins the rollback once. An awaited capability is cancelled; its result still arrives.
    fn skill_start_rollback(&mut self, reason: &'static str) {
        let awaiting = match self.skills.run.as_mut() {
            Some(run) if run.rolling.is_none() => {
                run.rolling = Some(reason);
                run.code.get_or_insert(reason);
                for step in run
                    .steps
                    .iter_mut()
                    .filter(|s| matches!(s.state, "running" | "awaiting_decision" | "retrying"))
                {
                    step.state = "cancelled";
                    step.code = Some(reason);
                }
                run.awaiting.clone()
            }
            _ => return,
        };
        match awaiting {
            Await::None | Await::Tool { .. } => {}
            Await::Decision { .. } => self.set_awaiting(Await::None),
            Await::Capability { capability, .. } => {
                if self.plugins.cancel(&capability).is_err() {
                    self.set_awaiting(Await::None);
                }
            }
        }
        self.skill_rollback();
    }

    /// Undo in reverse order (at most the stored entries). Waits while an undo or a restarting
    /// plugin is pending; ends the run when nothing is left.
    fn skill_rollback(&mut self) {
        loop {
            let awaiting = match self.skills.run.as_ref() {
                Some(run) if run.rolling.is_some() => run.awaiting.clone(),
                _ => return,
            };
            match awaiting {
                Await::None => {}
                Await::Decision { .. } => self.set_awaiting(Await::None),
                Await::Tool { .. } => return,
                Await::Capability { plugin_id, .. } => {
                    let alive = self
                        .plugins
                        .snapshot(self.hub.as_ref())
                        .items
                        .iter()
                        .any(|i| {
                            i.plugin_id == plugin_id
                                && i.enabled
                                && matches!(i.state, "running" | "starting")
                        });
                    if alive {
                        return;
                    }
                    self.set_awaiting(Await::None);
                }
            }
            let Some(undo) = self.skills.run.as_mut().and_then(|run| run.undo.pop()) else {
                self.skill_finish();
                return;
            };
            match self.exec_call(&undo.call, undo.args, STEP_TIMEOUT_MS, None) {
                Dispatch::Waiting => return,
                Dispatch::Done(Ok(_)) => self.mark_undone(undo.view),
                Dispatch::Done(Err(_)) => {
                    if let Some(run) = self.skills.run.as_mut() {
                        run.codes.push("undo_failed");
                    }
                }
            }
        }
    }

    fn mark_undone(&mut self, view: Option<usize>) {
        let Some(view) = view else {
            return;
        };
        if let Some(step) = self
            .skills
            .run
            .as_mut()
            .and_then(|run| run.steps.get_mut(view))
        {
            if step.state == "done" {
                step.state = "undone";
            }
        }
    }

    /// Ends the run and records its outcome. Emits rollback, then the terminal event.
    fn skill_finish(&mut self) {
        let Some(run) = self.skills.run.take() else {
            return;
        };
        let state = if run.rolling.is_none() {
            "done"
        } else if run.code == Some("cancelled") {
            "cancelled"
        } else {
            "failed"
        };
        if run.rolling.is_some() {
            self.emit(String::new(), None, "skill_rolled_back");
        }
        let kind = if state == "done" {
            "skill_run_done"
        } else {
            "skill_run_failed"
        };
        self.emit(String::new(), None, kind);
        let mut codes: Vec<&'static str> = run.codes.clone();
        if let Some(code) = run.code {
            if !codes.contains(&code) {
                codes.insert(0, code);
            }
        }
        codes.truncate(4);
        self.skills_record_run(RunRecord {
            run_id: run.id,
            skill: run.skill,
            version: run.version,
            state: state.to_owned(),
            step: run.failed_step,
            codes: codes.into_iter().map(|c| wire_code(c).to_owned()).collect(),
        });
    }

    /// Lost dependency (plugin revoked, disabled or failed, or permission gone): fail with
    /// `missing_dependency` and roll back. Also wakes a rollback that waits for a restarting plugin.
    pub(crate) fn skill_guard(&mut self) {
        let Some(run) = self.skills.run.as_ref() else {
            return;
        };
        if run.rolling.is_some() {
            self.skill_rollback();
            return;
        }
        let mut lost = None;
        for manifest in run.nested.values() {
            for dependency in &manifest.dependency_capabilities {
                if let Ok(Target::Capability(name)) = parse_target(dependency) {
                    if let Err(code) = self.capability_owner(&name) {
                        lost = Some(code);
                    }
                }
            }
        }
        if let Some(code) = lost {
            self.skill_start_rollback(code);
        }
    }

    /// Run deadline. A pending capability is cancelled and its result still closes the run.
    pub(crate) fn skill_expire(&mut self, now: Instant) {
        if self
            .skills
            .run
            .as_ref()
            .is_some_and(|run| now >= run.deadline && run.rolling.is_none())
        {
            self.skill_start_rollback("run_deadline");
        }
    }

    // ----- snapshot -------------------------------------------------------------

    /// Snapshot block. `None` (null on the wire) while the engine is unconfigured or quarantined.
    pub(crate) fn skills_view(&self) -> Option<View> {
        if self.skills.status != "ok" {
            return None;
        }
        let items = self
            .skills
            .ledger
            .skills
            .iter()
            .filter_map(|entry| {
                let record = entry
                    .active
                    .as_ref()
                    .and_then(|active| entry.versions.iter().find(|v| &v.version == active))
                    .or_else(|| entry.versions.last())?;
                let manifest = self.skills.root.as_ref().and_then(|root| {
                    read_private(
                        &manifest_path(root, &entry.id, &record.version),
                        MANIFEST_MAX as u64,
                    )
                    .ok()
                    .flatten()
                    .and_then(|bytes| serde_json::from_slice::<Manifest>(&bytes).ok())
                });
                let missing = manifest
                    .as_ref()
                    .map(|m| self.missing_for(m))
                    .unwrap_or_else(|| vec!["manifest_unavailable".to_owned()]);
                let permissions_ok = manifest.as_ref().is_some_and(|m| {
                    m.dependency_capabilities
                        .iter()
                        .all(|dep| match parse_target(dep) {
                            Ok(Target::Capability(name)) => self.owner_approved(&name),
                            _ => true,
                        })
                });
                let permissions_required = manifest
                    .as_ref()
                    .map(|m| m.permissions_required.clone())
                    .unwrap_or_default();
                Some(Item {
                    id: entry.id.clone(),
                    name: manifest.map(|m| m.name).unwrap_or_default(),
                    version: record.version.clone(),
                    state: record.state,
                    source: record.source,
                    active: entry.active.as_deref() == Some(record.version.as_str()),
                    deps_ok: missing.is_empty(),
                    permissions_ok,
                    missing,
                    permissions_required,
                })
            })
            .collect();
        let run = self.skills.run.as_ref().map(|run| {
            let awaited = match run.awaiting {
                Await::Decision { view } => Some(view),
                _ => None,
            };
            let state = if run.rolling.is_some() {
                if run.code == Some("cancelled") {
                    "cancelled"
                } else {
                    "failed"
                }
            } else if awaited.is_some() {
                "awaiting_approval"
            } else {
                "running"
            };
            let current = awaited.or_else(|| {
                run.steps
                    .iter()
                    .rposition(|s| matches!(s.state, "running" | "retrying"))
            });
            RunView {
                run_id: run.id.clone(),
                skill: run.skill.clone(),
                state,
                step: current
                    .and_then(|index| run.steps.get(index))
                    .map(|s| s.id.clone()),
                steps: run
                    .steps
                    .iter()
                    .map(|s| StepView {
                        id: s.id.clone(),
                        state: wire_step(s.state, s.code),
                        code: s.code.map(wire_code),
                        risk: s.risk,
                        effect_id: s.effect_id,
                    })
                    .collect(),
                outputs: run
                    .outputs
                    .clone()
                    .filter(|v| v.to_string().len() <= OUTPUT_MAX),
            }
        });
        Some(View {
            revision: self.skills.ledger.revision,
            items,
            run,
            history: self.skills.runs.runs.clone(),
            import: self.skills.import.as_ref().map(|p| p.view.clone()),
            paths: Paths {
                imports: crate::transport::data_dir()
                    .join(IMPORT_DIR)
                    .to_string_lossy()
                    .into_owned(),
                exports: crate::transport::data_dir()
                    .join(EXPORT_DIR)
                    .to_string_lossy()
                    .into_owned(),
            },
        })
    }

    /// Approved permissions of a capability's owner, including the bridge permission.
    fn owner_approved(&self, capability: &str) -> bool {
        self.hub
            .as_ref()
            .filter(|h| h.status == "verified")
            .and_then(|h| {
                h.entries
                    .iter()
                    .find(|e| e.capabilities.iter().any(|c| c == capability))
            })
            .is_some_and(|owner| {
                owner.permissions_approved
                    && bridge_permission(capability)
                        .is_none_or(|p| owner.permissions.iter().any(|x| x == p))
            })
    }
}

/// `when` and `unless` for one step, against the top frame.
fn skip_step(step: &Step, frame: &Frame) -> bool {
    let when_ok = step.when.as_ref().is_none_or(|c| cond_holds(c, frame));
    let unless_ok = step.unless.as_ref().is_none_or(|c| !cond_holds(c, frame));
    !(when_ok && unless_ok)
}

/// Internal step state to the snapshot vocabulary (docs/S4.md; app/bridge.py).
fn wire_step(state: &'static str, code: Option<&'static str>) -> &'static str {
    match state {
        "running" | "retrying" => "running",
        "awaiting_decision" => "awaiting_approval",
        "done" => "done",
        "failed" if code == Some("denied_by_user") => "denied",
        "failed" => "failed",
        "cancelled" => "cancelled",
        "undone" => "undone",
        _ => "pending",
    }
}

/// Internal reason to the snapshot and history allowlist. Unknown reasons read as `plugin_error`.
pub(crate) fn wire_code(code: &'static str) -> &'static str {
    match code {
        "permission_revoked" => "permission_denied",
        "denied_by_user" => "user_denied",
        "unresolved_ref" | "oversize" | "invalid_input" | "invalid_args" => "invalid_skill_input",
        "manifest_mismatch" | "manifest_unavailable" | "undo_limit" | "args_depth" => {
            "invalid_manifest"
        }
        "exfiltration" => "skill_invalid:exfiltration",
        "cycle" => "skill_invalid:cycle",
        "depth" => "skill_invalid:depth",
        "skill_disabled" | "skill_version_changed" => "aborted",
        "busy" => "executor_unavailable",
        "invalid_call" => "unknown_tool",
        "http_error" => "plugin_error",
        "missing_dependency"
        | "permission_denied"
        | "verify_failed"
        | "capability_unavailable"
        | "capability_timeout"
        | "timeout"
        | "run_deadline"
        | "cancelled"
        | "denied"
        | "user_denied"
        | "destructive_disabled"
        | "plugin_error"
        | "invalid_output"
        | "max_steps"
        | "executor_unavailable"
        | "executor_failed"
        | "unknown_tool"
        | "unknown_service"
        | "aborted"
        | "awaiting_approval"
        | "undo_failed"
        | "invalid_skill_input"
        | "invalid_manifest" => code,
        _ => "plugin_error",
    }
}

/// Operation reason to the bridge vocabulary, where the bridge names the same condition.
pub(crate) fn wire_op(code: &'static str) -> &'static str {
    match code {
        "unknown_run" => "unknown_skill_run",
        "not_awaiting" => "not_pending",
        "invalid_input" | "oversize" => "invalid_skill_input",
        "permission_revoked" => "permission_denied",
        other => other,
    }
}

// ---------------------------------------------------------------------------
// D3: host services for an approved `skills_author` plugin (docs/S4.md D3). Only drafts are
// created; nothing here approves, enables, exports, runs or publishes, and a plugin dry run only
// reads state. Plugin errors are the plugin codes of `plugin_code`.
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ManifestArgs {
    manifest: Value,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DryRunArgs {
    id: String,
    version: String,
    inputs: Value,
}

/// Core reason to the code a plugin sees. Validator reasons all read `skill_invalid`.
pub(crate) fn plugin_code(code: &'static str) -> &'static str {
    match code {
        "permission_revoked" | "permission_denied" => "permission_denied",
        "unknown_service" => "unknown_service",
        "invalid_host_call" => "invalid_host_call",
        "skills_unavailable" | "skills_storage_error" => "skills_unavailable",
        "missing_dependency" => "missing_dependency",
        "unknown_skill" => "unknown_skill",
        "unknown_version" => "unknown_version",
        "skill_busy" | "busy" => "busy",
        "invalid_input" | "oversize" | "invalid_skill_input" => "invalid_input",
        _ => "skill_invalid",
    }
}

impl Core {
    /// Approved `skills_author` permission of a plugin, read from the verified hub at call time.
    fn plugin_holds_skills_author(&self, plugin_id: &str) -> bool {
        self.hub
            .as_ref()
            .filter(|h| h.status == "verified")
            .is_some_and(|hub| {
                hub.entries.iter().any(|e| {
                    e.plugin_id == plugin_id
                        && e.permissions_approved
                        && e.permissions.iter().any(|p| p == SKILLS_AUTHOR)
                })
            })
    }

    /// Core side of one `skills.*` host service. Only the four D3 names reach this point.
    pub(crate) fn skill_service(
        &mut self,
        plugin_id: &str,
        service: &str,
        args: Value,
    ) -> Result<Value, &'static str> {
        if !self.plugin_holds_skills_author(plugin_id) {
            self.emit(String::new(), None, "skill_service_denied");
            return Err("permission_denied");
        }
        let outcome = match service {
            "skills.validate" => self.plugin_validate(args),
            "skills.draft_put" => self.plugin_draft_put(args),
            "skills.dry_run" => self.plugin_dry_run(args),
            "skills.list" => self.plugin_list(args),
            _ => Err("unknown_service"),
        };
        outcome.map_err(plugin_code)
    }

    /// `skills.validate {manifest}` => `{ok}`. Validation only; nothing is written.
    fn plugin_validate(&mut self, args: Value) -> Result<Value, &'static str> {
        let ManifestArgs { manifest } =
            serde_json::from_value(args).map_err(|_| "invalid_host_call")?;
        self.skills_ready()?;
        let ok = match self.skill_checked(&manifest) {
            Ok(_) => true,
            Err(code) if code.starts_with("skill_invalid:") => false,
            Err(code) => return Err(code),
        };
        self.emit(String::new(), None, "skill_plugin_validate");
        Ok(json!({ "ok": ok }))
    }

    /// `skills.draft_put {manifest}` => `{draft_id, version, state}`. Creates one new `draft`
    /// version from `llm_draft`; `state` is `revised` when the skill already has versions. An
    /// existing version, approved, enabled or not, is never replaced.
    fn plugin_draft_put(&mut self, args: Value) -> Result<Value, &'static str> {
        let ManifestArgs { manifest } =
            serde_json::from_value(args).map_err(|_| "invalid_host_call")?;
        self.skills_ready()?;
        let checked = self.skill_checked(&manifest)?;
        let id = checked.manifest.id.clone();
        let version = checked.manifest.version.clone();
        let revised = self.install(checked, Source::LlmDraft, State::Draft)?;
        self.emit(String::new(), None, "skill_draft_put");
        Ok(json!({
            "draft_id": format!("{id}@{version}"),
            "version": version,
            "state": if revised { "revised" } else { "draft" },
        }))
    }

    /// `skills.dry_run {id, version, inputs}` => `{ok, steps}`. Same checks as the user dry run,
    /// but a plugin never moves a version to `tested`.
    fn plugin_dry_run(&mut self, args: Value) -> Result<Value, &'static str> {
        let DryRunArgs {
            id,
            version,
            inputs,
        } = serde_json::from_value(args).map_err(|_| "invalid_host_call")?;
        let (_, steps) = self.dry_run_check(&id, &version, inputs)?;
        self.emit(String::new(), None, "skill_plugin_dry_run");
        Ok(json!({ "ok": true, "steps": steps }))
    }

    /// `skills.list {}` => `{items:[{id, version, state, source, active}]}`. No content, no paths.
    fn plugin_list(&mut self, args: Value) -> Result<Value, &'static str> {
        if !args.as_object().is_some_and(Map::is_empty) {
            return Err("invalid_host_call");
        }
        self.skills_ready()?;
        let items: Vec<Value> = self
            .skills
            .ledger
            .skills
            .iter()
            .flat_map(|entry| {
                let active = entry.active.clone();
                entry.versions.iter().map(move |v| {
                    json!({
                        "id": entry.id,
                        "version": v.version,
                        "state": v.state,
                        "source": v.source,
                        "active": active.as_deref() == Some(v.version.as_str()),
                    })
                })
            })
            .collect();
        self.emit(String::new(), None, "skill_plugin_list");
        Ok(json!({ "items": items }))
    }

    /// Stores one new version as `state` from `source`. Never touches `active` or another version.
    /// Returns true when the skill already existed, which makes this version a revision of it.
    fn install(
        &mut self,
        checked: Checked,
        source: Source,
        state: State,
    ) -> Result<bool, &'static str> {
        let root = self.skills.root.clone().ok_or("skills_unavailable")?;
        let id = checked.manifest.id.clone();
        let version = checked.manifest.version.clone();
        let mut next = self.skills.ledger.clone();
        let revised = next.skills.iter().any(|s| s.id == id);
        if !revised {
            if next.skills.len() >= SKILLS_MAX {
                return Err(E_SKILL_LIMIT);
            }
            next.skills.push(SkillEntry {
                id: id.clone(),
                versions: Vec::new(),
                active: None,
            });
        }
        let entry = entry_mut(&mut next, &id).ok_or("skills_storage_error")?;
        if entry.versions.iter().any(|v| v.version == version) {
            return Err(E_DUPLICATE);
        }
        if entry.versions.len() >= VERSIONS_MAX {
            return Err(E_VERSION_LIMIT);
        }
        entry.versions.push(VersionEntry {
            version: version.clone(),
            manifest_sha256: checked.sha256.clone(),
            state,
            source,
            approved_at_rev: None,
        });
        write_private(&manifest_path(&root, &id, &version), &checked.bytes)
            .map_err(|_| "skills_storage_error")?;
        self.skills_commit(next)?;
        Ok(revised)
    }
}

// ---------------------------------------------------------------------------
// D4: `.gskill` packages. Export writes under `<data>/skill-exports`; import reads only
// `<data>/skill-imports/<name>.gskill`, previews it, and installs a confirmed preview as `draft`.
// ---------------------------------------------------------------------------

/// The package file. `package_sha256` covers the whole package with that field set to "".
/// `signature` must stay null: publisher signatures are not implemented.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Package {
    format: u64,
    manifest: Value,
    readme: Option<String>,
    license: String,
    author: String,
    version: String,
    files: Vec<PackageFile>,
    package_sha256: String,
    publisher_id: String,
    signature: Option<Value>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct PackageFile {
    path: String,
    sha256: String,
}

fn package_digest(package: &Package) -> String {
    let mut copy = package.clone();
    copy.package_sha256 = String::new();
    serde_json::to_vec(&copy).map_or_else(|_| String::new(), |bytes| sha256_hex(&bytes))
}

/// Private directory for packages: created 0700 when missing; a symlink or non-directory is refused.
fn private_dir(path: &Path) -> Result<(), &'static str> {
    match fs::symlink_metadata(path) {
        Ok(meta) if meta.file_type().is_symlink() || !meta.is_dir() => Err(F_PATH),
        Ok(_) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => fs::DirBuilder::new()
            .recursive(true)
            .mode(0o700)
            .create(path)
            .map_err(|_| "skills_storage_error"),
        Err(_) => Err("skills_storage_error"),
    }
}

/// Import name: 1 to 64 bytes of letters, digits, `.`, `_` or `-`, starting with a letter or digit.
fn import_name_ok(name: &str) -> bool {
    (1..=64).contains(&name.len())
        && name.as_bytes()[0].is_ascii_alphanumeric()
        && name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'))
}

/// Reads `<data>/skill-imports/<name>.gskill`: a regular file, never through a symlink, at most
/// 64 KiB. Any other path, file type or size is refused before its content is parsed.
fn read_package(name: &str) -> Result<Vec<u8>, &'static str> {
    let dir = crate::transport::data_dir().join(IMPORT_DIR);
    match fs::symlink_metadata(&dir) {
        Ok(meta) if meta.file_type().is_symlink() || !meta.is_dir() => return Err(F_PATH),
        Ok(_) => {}
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Err(E_IMPORT_NOT_FOUND),
        Err(_) => return Err(E_IMPORT_INVALID),
    }
    let path = dir.join(format!("{name}.gskill"));
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(&path)
        .map_err(|error| match (error.kind(), error.raw_os_error()) {
            (_, Some(libc::ELOOP)) => F_SYMLINK,
            (io::ErrorKind::NotFound, _) => E_IMPORT_NOT_FOUND,
            _ => E_IMPORT_INVALID,
        })?;
    let meta = file.metadata().map_err(|_| E_IMPORT_INVALID)?;
    if !meta.is_file() {
        return Err(F_PATH);
    }
    if meta.len() > PACKAGE_MAX {
        return Err(F_TOO_LARGE);
    }
    let mut bytes = Vec::new();
    file.take(PACKAGE_MAX + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| E_IMPORT_INVALID)?;
    if bytes.len() as u64 > PACKAGE_MAX {
        return Err(F_TOO_LARGE);
    }
    Ok(bytes)
}

/// Prose fields (description, readme, triggers, prerequisites, attestations) must not carry a
/// path, a URL, a key or a secret. Narrower than the args rule, since prose may contain `;`.
fn prose_leak(text: &str) -> bool {
    let lower = text.to_ascii_lowercase();
    [
        "://",
        "/home/",
        "/etc/",
        "/root/",
        "~/",
        "private key",
        "api_key",
        "apikey",
        "token=",
        "password=",
        "secret=",
        "sk-proj-",
        "sk-ant-",
    ]
    .iter()
    .any(|needle| lower.contains(needle))
}

/// Result of one package scan. `view` is exactly what the snapshot shows.
struct Scan {
    package_sha256: String,
    view: ImportView,
    checked: Checked,
}

impl Core {
    /// Export of one installed version. Writes `<data>/skill-exports/<id>-<version>.gskill` (0600).
    pub(crate) fn skill_export(&mut self, id: &str, version: &str) -> &'static str {
        if let Err(code) = self.skills_ready() {
            return code;
        }
        let Some(record) = self
            .skills
            .entry(id)
            .and_then(|e| e.versions.iter().find(|v| v.version == version))
            .cloned()
        else {
            return "unknown_version";
        };
        let bytes = match self
            .skills
            .read_checked(id, &record.version, &record.manifest_sha256)
        {
            Ok(bytes) => bytes,
            Err(code) => return code,
        };
        let (Ok(value), Ok(typed)) = (
            serde_json::from_slice::<Value>(&bytes),
            serde_json::from_slice::<Manifest>(&bytes),
        ) else {
            return "manifest_unavailable";
        };
        let mut package = Package {
            format: PACKAGE_FORMAT,
            manifest: value,
            readme: typed.readme.clone(),
            license: typed.license.clone(),
            author: typed.publisher.name.clone(),
            version: typed.version.clone(),
            files: vec![PackageFile {
                path: MANIFEST_FILE.to_owned(),
                sha256: record.manifest_sha256.clone(),
            }],
            package_sha256: String::new(),
            publisher_id: typed.publisher.id.clone(),
            signature: None,
        };
        package.package_sha256 = package_digest(&package);
        let Ok(out) = serde_json::to_vec(&package) else {
            return "skills_storage_error";
        };
        if out.len() as u64 > PACKAGE_MAX {
            return F_TOO_LARGE;
        }
        let dir = crate::transport::data_dir().join(EXPORT_DIR);
        if let Err(code) = private_dir(&dir) {
            return code;
        }
        let path = dir.join(format!("{id}-{version}.gskill"));
        if write_private(&path, &out).is_err() {
            return "skills_storage_error";
        }
        self.emit(String::new(), None, "skill_exported");
        "ok"
    }

    /// Reads and scans one package. Malformed packages are refused; findings are returned in the
    /// view so the user sees every problem with a package that parses.
    fn scan_package(&self, name: &str) -> Result<Scan, &'static str> {
        let bytes = read_package(name)?;
        let package: Package = serde_json::from_slice(&bytes).map_err(|_| E_IMPORT_INVALID)?;
        if package.format != PACKAGE_FORMAT || package.signature.is_some() {
            return Err(E_IMPORT_INVALID);
        }
        let checked = self.skill_checked(&package.manifest)?;
        let manifest = &checked.manifest;
        let mut findings: Vec<Finding> = Vec::new();
        if package.package_sha256 != package_digest(&package) {
            findings.push(Finding {
                code: F_HASH,
                field: Some("package_sha256"),
            });
        }
        let expected = [PackageFile {
            path: MANIFEST_FILE.to_owned(),
            sha256: checked.sha256.clone(),
        }];
        if package.files != expected {
            findings.push(Finding {
                code: F_HASH,
                field: Some("files"),
            });
        }
        if package.version != manifest.version
            || package.publisher_id != manifest.publisher.id
            || package.license != manifest.license
            || package.readme != manifest.readme
            || package.author != manifest.publisher.name
        {
            findings.push(Finding {
                code: F_CORRUPT,
                field: Some("envelope"),
            });
        }
        let mut prose: Vec<&str> = vec![
            manifest.description.as_str(),
            manifest.publisher.name.as_str(),
        ];
        prose.extend(manifest.readme.as_deref());
        prose.extend(manifest.triggers.iter().map(String::as_str));
        prose.extend(manifest.prerequisites.iter().map(String::as_str));
        prose.extend(manifest.attestations.iter().map(|a| a.text.as_str()));
        if prose.iter().any(|text| prose_leak(text)) {
            findings.push(Finding {
                code: E_EXFIL,
                field: Some("text"),
            });
        }
        let existing = self.skills.entry(&manifest.id);
        let duplicate =
            existing.is_some_and(|e| e.versions.iter().any(|v| v.version == manifest.version));
        if duplicate {
            findings.push(Finding {
                code: E_DUPLICATE,
                field: Some("version"),
            });
        }
        // Permissions compare with the version the skill would replace: the active one, else the last.
        let previous = existing.and_then(|e| {
            e.active
                .as_ref()
                .and_then(|active| e.versions.iter().find(|v| &v.version == active))
                .or_else(|| e.versions.last())
        });
        let before: Vec<String> = previous
            .and_then(|v| {
                self.skills
                    .read_checked(&manifest.id, &v.version, &v.manifest_sha256)
                    .ok()
            })
            .and_then(|bytes| serde_json::from_slice::<Manifest>(&bytes).ok())
            .map(|m| m.permissions_required)
            .unwrap_or_default();
        let permission_delta: Vec<String> = manifest
            .permissions_required
            .iter()
            .filter(|p| !before.contains(p))
            .cloned()
            .collect();
        let escalated = existing.is_some() && !permission_delta.is_empty();
        if escalated {
            findings.push(Finding {
                code: F_ESCALATED,
                field: Some("permissions_required"),
            });
        }
        let view = ImportView {
            name: name.to_owned(),
            id: manifest.id.clone(),
            version: manifest.version.clone(),
            publisher: manifest.publisher.name.clone(),
            unverified: true,
            permissions_required: manifest.permissions_required.clone(),
            missing_deps: self.missing_for(manifest),
            permission_delta,
            permissions_escalated: escalated,
            duplicate,
            findings,
        };
        Ok(Scan {
            package_sha256: sha256_hex(&bytes),
            view,
            checked,
        })
    }

    /// `skill_import{name}`: scans the package and stores the preview. Installs nothing.
    pub(crate) fn skill_import(&mut self, name: &str) -> &'static str {
        if let Err(code) = self.skills_ready() {
            return code;
        }
        if !import_name_ok(name) {
            self.skills.import = None;
            return E_IMPORT_INVALID;
        }
        match self.scan_package(name) {
            Ok(scan) => {
                self.skills.import = Some(ImportState {
                    name: name.to_owned(),
                    package_sha256: scan.package_sha256,
                    view: scan.view,
                });
                self.emit(String::new(), None, "skill_import_previewed");
                "ok"
            }
            Err(code) => {
                self.skills.import = None;
                code
            }
        }
    }

    /// `skill_import_confirm{name, revision}`: rescans the file and installs it as `draft` only if
    /// it still matches the preview and has no blocking finding. Permissions are never granted.
    pub(crate) fn skill_import_confirm(&mut self, name: &str, revision: u64) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        let Some(pending) = self.skills.import.clone().filter(|p| p.name == name) else {
            return E_STALE_IMPORT;
        };
        let scan = match self.scan_package(name) {
            Ok(scan) => scan,
            Err(code) => return code,
        };
        if scan.package_sha256 != pending.package_sha256 || scan.view != pending.view {
            self.skills.import = None;
            return E_STALE_IMPORT;
        }
        if let Some(code) = scan
            .view
            .findings
            .iter()
            .find(|f| f.code != F_ESCALATED)
            .map(|f| f.code)
        {
            return code;
        }
        match self.install(scan.checked, Source::Imported, State::Draft) {
            Ok(_) => {
                self.skills.import = None;
                self.emit(String::new(), None, "skill_imported");
                "ok"
            }
            Err(code) => code,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exfiltration_text_catches_paths_urls_and_shell() {
        for bad in [
            "/etc/passwd",
            "~/x",
            "a/../b",
            "https://x.test",
            "a; b",
            "a | b",
            "`id`",
            "$(id)",
        ] {
            assert!(exfiltration_text(bad), "{bad}");
        }
        for good in ["speakers", "headphones", "${input.route}", "a-b_c.d"] {
            assert!(!exfiltration_text(good), "{good}");
        }
    }

    #[test]
    fn templates_keep_the_type_of_a_single_reference_and_interpolate_inside_text() {
        let mut frame = Frame {
            skill: "skill_t".into(),
            inputs: Map::new(),
            next: 0,
            results: BTreeMap::new(),
            outputs: Map::new(),
            parent: None,
            root_view: None,
        };
        frame.inputs.insert("count".into(), json!(3));
        frame.inputs.insert("name".into(), json!("ana"));
        frame
            .results
            .insert("read".into(), json!({"route": "speakers"}));
        assert_eq!(
            resolve(&json!("${input.count}"), &frame, false).unwrap(),
            json!(3)
        );
        assert_eq!(
            resolve(
                &json!("hi ${input.name} on ${steps.read.route}"),
                &frame,
                false
            )
            .unwrap(),
            json!("hi ana on speakers")
        );
        assert_eq!(
            resolve(&json!("${steps.later.route}"), &frame, false),
            Err("unresolved_ref")
        );
        assert_eq!(
            resolve(&json!("${steps.later.route}"), &frame, true).unwrap(),
            Value::Null
        );
        assert_eq!(
            resolve(&json!("${input.name}/../x"), &frame, false),
            Err("exfiltration")
        );
    }

    #[test]
    fn embedded_refs_are_real_values_at_run_time_and_placeholders_in_dry_run() {
        let mut frame = Frame {
            skill: "skill_t".into(),
            inputs: Map::new(),
            next: 0,
            results: BTreeMap::new(),
            outputs: Map::new(),
            parent: None,
            root_view: None,
        };
        frame.results.insert("read".into(), json!({"text": "hi"}));
        assert_eq!(
            resolve(&json!("ab-${steps.read.text}"), &frame, false).unwrap(),
            json!("ab-hi")
        );
        assert_eq!(
            resolve(&json!("ab-${steps.later.text}"), &frame, true).unwrap(),
            json!("ab-<steps.later.text>")
        );
        assert_eq!(
            resolve(&json!("ab-${steps.later.text}"), &frame, false),
            Err("unresolved_ref")
        );
        assert_eq!(
            resolve(&json!("${steps.later.text}"), &frame, true).unwrap(),
            Value::Null
        );
    }

    #[test]
    fn semver_and_runtime_comparison() {
        assert!(semver_ok("1.2.3"));
        assert!(!semver_ok("1.2"));
        assert!(!semver_ok("1.2.3-rc1"));
        assert!(!semver_ok("01.2.3"));
        assert!(!semver_ok("100000.0.0"));
        assert!(semver_ok("99999.0.0"));
        assert_eq!(semver_tuple("0.1.0"), Some((0, 1, 0)));
        assert!(semver_tuple("0.2.0") > Some(runtime_version()));
    }

    #[test]
    fn every_wire_code_is_in_the_snapshot_vocabulary() {
        for code in [
            "permission_revoked",
            "denied_by_user",
            "busy",
            "unresolved_ref",
            "stale_screen",
        ] {
            let wire = wire_code(code);
            assert!(
                wire.starts_with("skill_invalid:")
                    || !wire.contains(' ')
                        && wire.bytes().all(|b| b.is_ascii_lowercase() || b == b'_'),
                "{code} -> {wire}"
            );
        }
        assert_eq!(wire_code("stale_screen"), "plugin_error");
        assert_eq!(wire_op("unknown_run"), "unknown_skill_run");
    }
}
