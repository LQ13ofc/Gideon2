//! S5 E1 Connection Manager. Fixed provider descriptors, a private account ledger
//! (`connections.json`, CAS revision), tokens only in the vault (`secrets.json`, `conn:<id>:*`),
//! device-code login against loopback fakes, and one network job at a time through the
//! Core-brokered HTTP (`scripts/net_broker.py`). Operations are the only way to reach a service;
//! responses are projected to the descriptor's fields before anything leaves this module.
//! Test/dev only: every provider is served by a `--connections-fake` loopback URL. Without one,
//! connect and calls are refused with `real_backend_unsupported` and no socket is opened.
use crate::{
    broker,
    llmcfg::{self, LlmState},
    protocol::valid_id,
    storage::Storage,
    tools,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::{
    collections::{BTreeMap, VecDeque},
    path::{Path, PathBuf},
    sync::OnceLock,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tokio::{
    io::{AsyncBufRead, BufReader},
    time::timeout_at,
};

pub const MAX_ACCOUNTS: usize = 8;
pub const CALL_TIMEOUT: Duration = Duration::from_secs(8);
pub const CALLS_PER_MINUTE: usize = 30;
pub const MAX_RESPONSE: usize = 64 * 1024;
pub const MAX_PROJECTED: usize = 4096;
pub const MAX_RETRIES: u32 = 2;
const RETRY_AFTER_MAX: u64 = 60;
const BUDGET_WINDOW: Duration = Duration::from_secs(60);
const QUEUE_LIMIT: usize = 8;
const POLL_INTERVAL_MAX: u64 = 5;
const DEVICE_LIFETIME_MAX: u64 = 300;
const MAX_POLLS: u32 = 120;
const LABEL_MAX: usize = 64;
const AUDIT_MAX: usize = 64;
const PROJECTED_ITEMS_MAX: usize = 50;
const DEVICE_GRANT: &str = "urn:ietf:params:oauth:grant-type:device_code";
const TOKEN_MAX: usize = 1024;

/// Test/dev switches, set once by `main`. Empty `fakes` is production: nothing reaches a network.
#[derive(Clone, Debug, Default)]
pub struct Options {
    /// Provider id to loopback base URL (`http://127.0.0.1:<port>`).
    pub fakes: BTreeMap<String, String>,
    /// Lets public and destructive operations execute after approval (test only).
    pub allow_public: bool,
}

static OPTIONS: OnceLock<Options> = OnceLock::new();

pub fn configure(options: Options) -> Result<(), Options> {
    OPTIONS.set(options)
}

pub fn options() -> &'static Options {
    OPTIONS.get_or_init(Options::default)
}

fn fake_base(provider: &str) -> Option<&'static str> {
    options().fakes.get(provider).map(String::as_str)
}

/// `provider=http://127.0.0.1:<port>` with a known provider and a loopback IP literal, no path.
pub fn parse_fake(raw: &str) -> Result<(String, String), &'static str> {
    let (provider, url) = raw.split_once('=').ok_or("invalid_connections_fake")?;
    if provider_by_id(provider).is_none() {
        return Err("invalid_connections_fake");
    }
    let endpoint = llmcfg::parse_endpoint(url, true).map_err(|_| "invalid_connections_fake")?;
    if endpoint.https
        || !endpoint.loopback
        || !endpoint.path.is_empty()
        || !is_ip_literal(&endpoint.host)
    {
        return Err("invalid_connections_fake");
    }
    Ok((provider.to_owned(), url.to_owned()))
}

fn is_ip_literal(host: &str) -> bool {
    host.parse::<std::net::IpAddr>().is_ok()
}

/// Access class of a scope or operation. Public and destructive always need explicit approval.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Access {
    Read,
    Write,
    Destructive,
    Public,
}

impl Access {
    /// The access class as the snapshot and the proposal card spell it (`read`, `write`, ...).
    pub fn name(self) -> &'static str {
        match self {
            Access::Read => "read",
            Access::Write => "write",
            Access::Destructive => "destructive",
            Access::Public => "public",
        }
    }
    /// Registry risk used by the proposal ledger, the agent and the skill engine.
    pub fn tool_risk(self) -> tools::Risk {
        match self {
            Access::Read => tools::Risk::ReadOnly,
            Access::Write => tools::Risk::StateChanging,
            Access::Destructive | Access::Public => tools::Risk::Destructive,
        }
    }
}

pub struct ScopeDef {
    pub id: &'static str,
    pub label: &'static str,
    pub access: Access,
}

#[derive(Clone, Copy)]
pub enum Kind {
    /// `owner/name`, each part 1..=100 of `[A-Za-z0-9._-]`, never `.` or `..`.
    Repo,
    /// Positive integer up to 1_000_000_000.
    Number,
    /// Text up to this many bytes; control characters refused except newline and tab.
    Text(usize),
    /// One of these exact strings.
    Choice(&'static [&'static str]),
}

#[derive(Clone, Copy)]
pub struct Field {
    pub name: &'static str,
    pub kind: Kind,
    pub required: bool,
}

pub struct OpDef {
    pub name: &'static str,
    pub scope: &'static str,
    pub risk: Access,
    pub method: &'static str,
    /// Path template; `{repo}` and `{number}` are filled from validated params.
    pub path: &'static str,
    pub params: &'static [Field],
    pub body: &'static [Field],
    pub idempotent: bool,
    /// Fields of the response that may leave the Core (scalars only).
    pub project: &'static [&'static str],
}

pub struct Provider {
    pub id: &'static str,
    pub label: &'static str,
    pub scopes: &'static [ScopeDef],
    pub operations: &'static [OpDef],
}

const REPO: Field = Field {
    name: "repo",
    kind: Kind::Repo,
    required: true,
};
const NUMBER: Field = Field {
    name: "number",
    kind: Kind::Number,
    required: true,
};
const TITLE: Field = Field {
    name: "title",
    kind: Kind::Text(256),
    required: true,
};
const BODY: Field = Field {
    name: "body",
    kind: Kind::Text(4096),
    required: false,
};
const STATES: &[&str] = &["open", "closed"];
const ISSUE_STATE: Field = Field {
    name: "state",
    kind: Kind::Choice(STATES),
    required: false,
};
const ISSUE_TITLE_OPT: Field = Field {
    name: "title",
    kind: Kind::Text(256),
    required: false,
};
const COMMENT_BODY: Field = Field {
    name: "body",
    kind: Kind::Text(4096),
    required: true,
};

const GITHUB_SCOPES: [ScopeDef; 3] = [
    ScopeDef {
        id: "repo:read",
        label: "Ler repositórios e actions",
        access: Access::Read,
    },
    ScopeDef {
        id: "issues:write",
        label: "Criar e editar issues",
        access: Access::Write,
    },
    ScopeDef {
        id: "pulls:write",
        label: "Comentar pull requests",
        access: Access::Write,
    },
];

const ISSUE_FIELDS: &[&str] = &["number", "title", "url", "state", "public"];

const GITHUB_OPERATIONS: [OpDef; 7] = [
    OpDef {
        name: "repos.list",
        scope: "repo:read",
        risk: Access::Read,
        method: "GET",
        path: "/api/repos",
        params: &[],
        body: &[],
        idempotent: true,
        project: &["name", "private", "default_branch"],
    },
    OpDef {
        name: "repo.get",
        scope: "repo:read",
        risk: Access::Read,
        method: "GET",
        path: "/api/repos/{repo}",
        params: &[REPO],
        body: &[],
        idempotent: true,
        project: &["name", "private", "default_branch"],
    },
    OpDef {
        name: "issues.create",
        scope: "issues:write",
        // Public when the repo is public. Unknown visibility counts as public (see `effective_risk`).
        risk: Access::Write,
        method: "POST",
        path: "/api/repos/{repo}/issues",
        params: &[REPO],
        body: &[TITLE, BODY],
        idempotent: true,
        project: ISSUE_FIELDS,
    },
    OpDef {
        name: "issues.update",
        scope: "issues:write",
        risk: Access::Write,
        method: "PATCH",
        path: "/api/repos/{repo}/issues/{number}",
        params: &[REPO, NUMBER],
        body: &[ISSUE_TITLE_OPT, BODY, ISSUE_STATE],
        idempotent: true,
        project: ISSUE_FIELDS,
    },
    OpDef {
        name: "pulls.get",
        scope: "repo:read",
        risk: Access::Read,
        method: "GET",
        path: "/api/repos/{repo}/pulls/{number}",
        params: &[REPO, NUMBER],
        body: &[],
        idempotent: true,
        project: &["number", "title", "state", "url"],
    },
    OpDef {
        name: "pulls.comment",
        scope: "pulls:write",
        risk: Access::Public,
        method: "POST",
        path: "/api/repos/{repo}/pulls/{number}/comments",
        params: &[REPO, NUMBER],
        body: &[COMMENT_BODY],
        // A comment has no natural key: a failed POST is never retried (no Idempotency-Key).
        idempotent: false,
        project: &["id", "url"],
    },
    OpDef {
        name: "actions.list",
        scope: "repo:read",
        risk: Access::Read,
        method: "GET",
        path: "/api/repos/{repo}/actions",
        params: &[REPO],
        body: &[],
        idempotent: true,
        project: &["id", "name", "status"],
    },
];

const NO_SCOPES: [ScopeDef; 0] = [];
const NO_OPERATIONS: [OpDef; 0] = [];

/// Fixed registry. Empty entries are valid descriptors that await their E2 connector.
const PROVIDERS: [Provider; 4] = [
    Provider {
        id: "github",
        label: "GitHub",
        scopes: &GITHUB_SCOPES,
        operations: &GITHUB_OPERATIONS,
    },
    Provider {
        id: "google",
        label: "Google",
        scopes: &NO_SCOPES,
        operations: &NO_OPERATIONS,
    },
    Provider {
        id: "homeassistant",
        label: "Home Assistant",
        scopes: &NO_SCOPES,
        operations: &NO_OPERATIONS,
    },
    Provider {
        id: "mcp",
        label: "MCP",
        scopes: &NO_SCOPES,
        operations: &NO_OPERATIONS,
    },
];

pub fn provider_by_id(id: &str) -> Option<&'static Provider> {
    PROVIDERS.iter().find(|p| p.id == id)
}

pub fn operation(provider: &'static Provider, name: &str) -> Option<&'static OpDef> {
    operation_of(provider, name)
}

fn operation_of(provider: &'static Provider, name: &str) -> Option<&'static OpDef> {
    provider.operations.iter().find(|op| op.name == name)
}

/// Agent tools (fixed names) that exist only while their provider has a test fake.
pub struct AgentTool {
    pub name: &'static str,
    pub provider: &'static str,
    pub operation: &'static str,
}

const AGENT_TOOLS: [AgentTool; 2] = [
    AgentTool {
        name: "github_list_repos",
        provider: "github",
        operation: "repos.list",
    },
    AgentTool {
        name: "github_create_issue",
        provider: "github",
        operation: "issues.create",
    },
];

pub fn agent_tool(name: &str) -> Option<&'static AgentTool> {
    AGENT_TOOLS
        .iter()
        .find(|tool| tool.name == name && fake_base(tool.provider).is_some())
}

/// Prompt lines for the agent, only for tools whose provider has a fake. Argument names are exact.
pub fn agent_prompt() -> String {
    let mut text = String::new();
    for tool in AGENT_TOOLS
        .iter()
        .filter(|t| fake_base(t.provider).is_some())
    {
        match tool.name {
            "github_list_repos" => text.push_str("\n- github_list_repos {}"),
            "github_create_issue" => text.push_str(
                "\n- github_create_issue {\"repo\": \"owner/name\", \"title\": string up to 256 chars, \"body\": string up to 4096 chars, optional}",
            ),
            _ => {}
        }
    }
    text
}

/// Resolves `conn:<provider>.<operation>` (D1 call form) to its static descriptor entries.
pub fn parse_call(call: &str) -> Option<(&'static Provider, &'static OpDef)> {
    let rest = call.strip_prefix("conn:")?;
    let (provider, name) = rest.split_once('.')?;
    let provider = provider_by_id(provider)?;
    let op = operation(provider, name)?;
    Some((provider, op))
}

fn random_hex(bytes: usize) -> String {
    let mut buffer = vec![0u8; bytes];
    // SAFETY: writable buffer of exactly `bytes` length; kernel randomness, no ambient state.
    let read = unsafe { libc::getrandom(buffer.as_mut_ptr().cast(), buffer.len(), 0) };
    if read != buffer.len() as isize {
        // Never reached on Linux with a valid buffer; fall back to time-derived bytes.
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_or(0, |d| d.as_nanos());
        return format!("{nanos:032x}");
    }
    buffer
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<Vec<String>>()
        .concat()
}

fn unix_now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |d| d.as_secs())
}

fn label_ok(label: &str) -> bool {
    !label.is_empty() && label.len() <= LABEL_MAX && label.chars().all(|c| !c.is_control())
}

fn repo_ok(text: &str) -> bool {
    let mut parts = text.split('/');
    let (Some(owner), Some(name), None) = (parts.next(), parts.next(), parts.next()) else {
        return false;
    };
    [owner, name].iter().all(|part| {
        !part.is_empty()
            && part.len() <= 100
            && *part != "."
            && *part != ".."
            && part
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
    })
}

fn text_ok(text: &str, max: usize) -> bool {
    text.len() <= max
        && text
            .chars()
            .all(|c| !c.is_control() || c == '\n' || c == '\t')
}

fn kind_value(kind: Kind, value: &Value) -> Option<Value> {
    match kind {
        Kind::Repo => value.as_str().filter(|s| repo_ok(s)).map(Value::from),
        Kind::Number => value
            .as_u64()
            .filter(|n| (1..=1_000_000_000).contains(n))
            .map(Value::from),
        Kind::Text(max) => value.as_str().filter(|s| text_ok(s, max)).map(Value::from),
        Kind::Choice(options) => value
            .as_str()
            .filter(|s| options.contains(s))
            .map(Value::from),
    }
}

/// Validated call: exact keys, typed values, then the path and body the broker will send.
pub struct Shape {
    pub input: Map<String, Value>,
    pub path: String,
    pub body: Option<Value>,
    pub repo: Option<String>,
}

pub fn validate(op: &OpDef, args: &Value) -> Result<Shape, &'static str> {
    let object = args.as_object().ok_or("invalid_args")?;
    let fields: Vec<Field> = op.params.iter().chain(op.body.iter()).copied().collect();
    if object
        .keys()
        .any(|key| !fields.iter().any(|f| f.name == key))
    {
        return Err("invalid_args");
    }
    let mut input = Map::new();
    for field in &fields {
        match object.get(field.name) {
            None if field.required => return Err("invalid_args"),
            None => {}
            Some(value) => {
                let normalized = kind_value(field.kind, value).ok_or("invalid_args")?;
                input.insert(field.name.to_owned(), normalized);
            }
        }
    }
    let repo = input.get("repo").and_then(Value::as_str).map(str::to_owned);
    let mut path = op.path.to_owned();
    if let Some(repo) = repo.as_deref() {
        path = path.replace("{repo}", repo);
    }
    if let Some(number) = input.get("number").and_then(Value::as_u64) {
        path = path.replace("{number}", &number.to_string());
    }
    let body = if op.method == "GET" {
        None
    } else {
        let mut body = Map::new();
        for field in op.body {
            if let Some(value) = input.get(field.name) {
                body.insert(field.name.to_owned(), value.clone());
            }
        }
        Some(Value::Object(body))
    };
    Ok(Shape {
        input,
        path,
        body,
        repo,
    })
}

/// Projection keeps scalar fields listed by the descriptor; nested values never leave.
fn project_object(value: &Value, fields: &[&str]) -> Value {
    let mut out = Map::new();
    if let Some(object) = value.as_object() {
        for field in fields {
            if let Some(scalar) = object.get(*field) {
                if !scalar.is_object() && !scalar.is_array() {
                    out.insert((*field).to_owned(), scalar.clone());
                }
            }
        }
    }
    Value::Object(out)
}

fn project(value: &Value, op: &OpDef) -> Result<Value, &'static str> {
    let projected = match value {
        Value::Array(items) => Value::Array(
            items
                .iter()
                .take(PROJECTED_ITEMS_MAX)
                .map(|item| project_object(item, op.project))
                .collect(),
        ),
        Value::Object(_) => project_object(value, op.project),
        _ => return Err("provider_error"),
    };
    if serde_json::to_vec(&projected).map_or(true, |b| b.len() > MAX_PROJECTED) {
        return Err("response_too_large");
    }
    Ok(projected)
}

/// Repo visibility learned from `repo.get` results: `private` booleans keyed by `owner/name`.
fn visibility_of(op: &OpDef, value: &Value, repo: Option<&str>) -> Option<(String, bool)> {
    if op.name != "repo.get" {
        return None;
    }
    let private = value.get("private")?.as_bool()?;
    Some((repo?.to_owned(), private))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Disconnected,
    Connecting,
    Connected,
    Expired,
    Offline,
    Error,
    ReauthRequired,
}

/// One account row. Secrets live only in the vault; this row never carries them.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Account {
    pub id: String,
    pub provider: String,
    pub label: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub account_ref: Option<String>,
    pub status: Status,
    #[serde(default)]
    pub granted_scopes: Vec<String>,
    pub created: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_ok: Option<u64>,
}

/// `connections.json`: version 1, strict, CAS on `revision`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Ledger {
    pub version: u16,
    pub revision: u64,
    #[serde(default)]
    pub accounts: Vec<Account>,
}

impl Default for Ledger {
    fn default() -> Self {
        Self {
            version: 1,
            revision: 0,
            accounts: Vec::new(),
        }
    }
}

impl Ledger {
    fn validate(&self) -> bool {
        if self.version != 1 || self.accounts.len() > MAX_ACCOUNTS {
            return false;
        }
        self.accounts.iter().enumerate().all(|(index, account)| {
            let Some(provider) = provider_by_id(&account.provider) else {
                return false;
            };
            valid_id(&account.id)
                && label_ok(&account.label)
                && self.accounts[..index]
                    .iter()
                    .all(|other| other.id != account.id)
                && account
                    .granted_scopes
                    .iter()
                    .all(|scope| provider.scopes.iter().any(|s| s.id == scope))
        })
    }
}

/// Failure of one broker exchange, already mapped to a stable code.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Failure {
    pub code: &'static str,
    pub status: Option<u16>,
    pub retry_after: Option<u64>,
    /// Provider `error` token of a small JSON body (closed snake_case vocabulary).
    pub detail: Option<String>,
}

impl Failure {
    fn new(code: &'static str) -> Self {
        Self {
            code,
            status: None,
            retry_after: None,
            detail: None,
        }
    }
}

/// Maps a broker error line to the S5 code vocabulary.
fn broker_failure(code: &str, status: Option<u16>, meta: &broker::Meta) -> Failure {
    let mapped = match code {
        "timeout" => Failure::new("timeout"),
        "http_error" => http_failure(status.unwrap_or(0), meta),
        "response_too_large" => Failure::new("response_too_large"),
        "redirect_refused" => Failure::new("provider_error"),
        _ => Failure::new("provider_unreachable"),
    };
    Failure {
        status,
        detail: meta.provider_error.clone(),
        ..mapped
    }
}

fn http_failure(status: u16, meta: &broker::Meta) -> Failure {
    let code = match status {
        401 => "unauthorized",
        403 => "forbidden_scope",
        404 => "not_found",
        429 => "rate_limited",
        _ => "provider_error",
    };
    Failure {
        code,
        status: Some(status),
        retry_after: (code == "rate_limited")
            .then(|| meta.retry_after.unwrap_or(1).clamp(1, RETRY_AFTER_MAX)),
        detail: meta.provider_error.clone(),
    }
}

/// One outgoing operation call. Holds the access token only in memory; never serialized.
pub struct Call {
    proposal: Option<String>,
    account: String,
    provider: &'static str,
    op: &'static OpDef,
    shape: Shape,
    base: String,
    token: String,
    account_ref: Option<String>,
    idempotency: String,
    retried: bool,
}

/// Work for the single network slot. Debug never prints tokens.
pub enum Job {
    Device {
        account: String,
        base: String,
        scopes: Vec<String>,
    },
    Poll {
        account: String,
        base: String,
        device_code: String,
        consented: Vec<String>,
    },
    Refresh {
        account: String,
        base: String,
        refresh: String,
        then: Option<Box<Call>>,
    },
    Revoke {
        base: String,
        token: String,
    },
    Call(Box<Call>),
}

impl std::fmt::Debug for Job {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Job::Device { .. } => "Job::Device",
            Job::Poll { .. } => "Job::Poll",
            Job::Refresh { .. } => "Job::Refresh",
            Job::Revoke { .. } => "Job::Revoke",
            Job::Call(_) => "Job::Call",
        })
    }
}

/// Outcome of one polling step of the device flow.
pub enum Poll {
    Pending,
    Token {
        access: String,
        refresh: Option<String>,
        scope: Vec<String>,
        account: Option<String>,
    },
}

/// Finished job, handed back to the Core by its id.
pub struct Done {
    pub id: u64,
    pub reply: Reply,
}

pub enum Reply {
    Device {
        account: String,
        outcome: Result<DeviceGrant, Failure>,
    },
    Poll {
        account: String,
        outcome: Result<Poll, Failure>,
    },
    Refresh {
        account: String,
        then: Option<Box<Call>>,
        outcome: Result<(String, Option<String>, Option<String>), Failure>,
    },
    Revoke {
        outcome: Result<bool, Failure>,
    },
    Call {
        call: Box<Call>,
        outcome: Result<(Value, Option<(String, bool)>), Failure>,
    },
}

/// One broker exchange with a deadline shared by all attempts of one job. A `Done` line is 2xx.
struct Response {
    body: Vec<u8>,
    meta: broker::Meta,
}

fn target(base: &str, path: &str) -> Result<broker::Target, Failure> {
    let endpoint =
        llmcfg::parse_endpoint(base, true).map_err(|_| Failure::new("provider_unreachable"))?;
    let scheme = if endpoint.https { "https" } else { "http" };
    let authority = if endpoint.host.contains(':') {
        format!("[{}]:{}", endpoint.host, endpoint.port)
    } else {
        format!("{}:{}", endpoint.host, endpoint.port)
    };
    Ok(broker::Target {
        url: format!("{scheme}://{authority}{}{path}", endpoint.path),
        host: endpoint.host,
        https: endpoint.https,
        loopback: endpoint.loopback,
        keyless: false,
    })
}

struct Exchange<'a> {
    python: &'a Path,
    script: &'a Path,
    deadline: tokio::time::Instant,
}

impl Exchange<'_> {
    async fn send(
        &self,
        base: &str,
        method: &str,
        path: &str,
        headers: &[(&str, String)],
        body: Option<&Value>,
        key: Option<&str>,
    ) -> Result<Response, Failure> {
        let remaining = self
            .deadline
            .checked_duration_since(tokio::time::Instant::now())
            .ok_or_else(|| Failure::new("timeout"))?;
        let timeout_s = remaining.as_secs().clamp(1, CALL_TIMEOUT.as_secs());
        let target = target(base, path)?;
        let body_text = body.map(Value::to_string).unwrap_or_default();
        let payload = broker::request_payload(&target, method, headers, &body_text, key, timeout_s)
            .map_err(|_| Failure::new("provider_unreachable"))?;
        let processes = tokio::task::spawn_blocking(crate::plugins::process_budget)
            .await
            .map_err(|_| Failure::new("provider_unreachable"))?;
        let mut command = broker::command(self.python, self.script, processes)
            .map_err(|_| Failure::new("provider_unreachable"))?;
        let mut child = command
            .spawn()
            .map_err(|_| Failure::new("provider_unreachable"))?;
        let (Some(mut stdin), Some(stdout)) = (child.stdin.take(), child.stdout.take()) else {
            return Err(Failure::new("provider_unreachable"));
        };
        let mut reader = BufReader::new(stdout);
        let written = timeout_at(self.deadline, broker::write_payload(&mut stdin, &payload)).await;
        drop(stdin);
        if !matches!(written, Ok(Ok(()))) {
            return Err(Failure::new("provider_unreachable"));
        }
        read_response(&mut reader, self.deadline).await
    }
}

async fn read_response<R: AsyncBufRead + Unpin>(
    reader: &mut R,
    deadline: tokio::time::Instant,
) -> Result<Response, Failure> {
    let mut body = Vec::new();
    loop {
        let parsed = match timeout_at(deadline, broker::read_parsed(reader)).await {
            Ok(parsed) => parsed,
            Err(_) => return Err(Failure::new("timeout")),
        };
        match parsed.reply {
            broker::Reply::Chunk(text) => {
                if body.len() + text.len() > MAX_RESPONSE {
                    return Err(Failure::new("response_too_large"));
                }
                body.extend_from_slice(text.as_bytes());
            }
            broker::Reply::Done(_) => {
                return Ok(Response {
                    body,
                    meta: parsed.meta,
                })
            }
            broker::Reply::Error(code, status) => {
                return Err(broker_failure(code, status, &parsed.meta))
            }
            broker::Reply::Closed => return Err(Failure::new("provider_unreachable")),
        }
    }
}

fn json_object(body: &[u8]) -> Result<Map<String, Value>, Failure> {
    match serde_json::from_slice::<Value>(body) {
        Ok(Value::Object(object)) => Ok(object),
        _ => Err(Failure::new("provider_error")),
    }
}

fn short_string(object: &Map<String, Value>, key: &str, max: usize) -> Option<String> {
    object
        .get(key)
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty() && s.len() <= max && s.bytes().all(|b| b.is_ascii_graphic()))
        .map(str::to_owned)
}

/// Device grant as issued by the provider; the account is bound by the Core, not by this value.
pub struct DeviceGrant {
    device_code: String,
    user_code: String,
    interval: u64,
    expires_in: u64,
}

async fn run_device(
    ex: &Exchange<'_>,
    base: &str,
    scopes: &[String],
) -> Result<DeviceGrant, Failure> {
    // Device requests carry no credential; the fake and the real flow both accept a scope list.
    let body = json!({ "scopes": scopes });
    let headers = [
        ("Content-Type", "application/json".to_owned()),
        ("Accept", "application/json".to_owned()),
    ];
    let response = ex
        .send(
            base,
            "POST",
            "/login/device/code",
            &headers,
            Some(&body),
            None,
        )
        .await?;
    let object = json_object(&response.body)?;
    let device_code =
        short_string(&object, "device_code", 512).ok_or(Failure::new("provider_error"))?;
    let user_code = short_string(&object, "user_code", 64).ok_or(Failure::new("provider_error"))?;
    // Required by the device flow (the user visits it); not kept, so it never reaches the snapshot.
    short_string(&object, "verification_uri", 512).ok_or(Failure::new("provider_error"))?;
    let interval = object
        .get("interval")
        .and_then(Value::as_u64)
        .unwrap_or(POLL_INTERVAL_MAX);
    let expires_in = object
        .get("expires_in")
        .and_then(Value::as_u64)
        .unwrap_or(DEVICE_LIFETIME_MAX)
        .min(DEVICE_LIFETIME_MAX);
    Ok(DeviceGrant {
        device_code,
        user_code,
        interval,
        expires_in,
    })
}

async fn run_poll(ex: &Exchange<'_>, base: &str, device_code: &str) -> Result<Poll, Failure> {
    let body = json!({ "device_code": device_code, "grant_type": DEVICE_GRANT });
    let headers = [
        ("Content-Type", "application/json".to_owned()),
        ("Accept", "application/json".to_owned()),
    ];
    let response = match ex
        .send(
            base,
            "POST",
            "/login/oauth/access_token",
            &headers,
            Some(&body),
            None,
        )
        .await
    {
        Ok(response) => response,
        // A pending or slow device answers 400 with an `error` token; that is not a failure.
        Err(failure) => {
            return match failure.detail.as_deref() {
                Some("authorization_pending" | "slow_down") => Ok(Poll::Pending),
                Some("expired_token") => Err(Failure::new("device_expired")),
                Some("access_denied") => Err(Failure::new("consent_denied")),
                _ => Err(failure),
            }
        }
    };
    let object = json_object(&response.body)?;
    if let Some(error) = object.get("error").and_then(Value::as_str) {
        return match error {
            "authorization_pending" | "slow_down" => Ok(Poll::Pending),
            "expired_token" => Err(Failure::new("device_expired")),
            "access_denied" => Err(Failure::new("consent_denied")),
            _ => Err(Failure::new("provider_error")),
        };
    }
    let access =
        short_string(&object, "access_token", TOKEN_MAX).ok_or(Failure::new("provider_error"))?;
    let refresh = short_string(&object, "refresh_token", TOKEN_MAX);
    let scope = object
        .get("scope")
        .and_then(Value::as_str)
        .map(|s| s.split_whitespace().map(str::to_owned).collect())
        .unwrap_or_default();
    let account = object
        .get("account")
        .and_then(Value::as_str)
        .map(str::to_owned)
        .or_else(|| response.meta.account.clone());
    Ok(Poll::Token {
        access,
        refresh,
        scope,
        account,
    })
}

async fn run_refresh(
    ex: &Exchange<'_>,
    base: &str,
    refresh: &str,
) -> Result<(String, Option<String>, Option<String>), Failure> {
    let body = json!({ "refresh_token": refresh });
    let headers = [
        ("Content-Type", "application/json".to_owned()),
        ("Accept", "application/json".to_owned()),
    ];
    let response = ex
        .send(
            base,
            "POST",
            "/login/oauth/refresh",
            &headers,
            Some(&body),
            None,
        )
        .await?;
    let object = json_object(&response.body)?;
    let access =
        short_string(&object, "access_token", TOKEN_MAX).ok_or(Failure::new("provider_error"))?;
    let rotated = short_string(&object, "refresh_token", TOKEN_MAX);
    let account = response.meta.account.clone();
    Ok((access, rotated, account))
}

async fn run_call(
    ex: &Exchange<'_>,
    call: &Call,
) -> Result<(Value, Option<(String, bool)>), Failure> {
    let mut headers: Vec<(&str, String)> = vec![("Accept", "application/json".to_owned())];
    if call.shape.body.is_some() {
        headers.push(("Content-Type", "application/json".to_owned()));
    }
    if call.op.idempotent {
        headers.push(("Idempotency-Key", call.idempotency.clone()));
    }
    let response = ex
        .send(
            &call.base,
            call.op.method,
            &call.shape.path,
            &headers,
            call.shape.body.as_ref(),
            Some(&call.token),
        )
        .await?;
    if let (Some(expected), Some(seen)) = (
        call.account_ref.as_deref(),
        response.meta.account.as_deref(),
    ) {
        if expected != seen {
            return Err(Failure::new("account_mismatch"));
        }
    }
    let value: Value =
        serde_json::from_slice(&response.body).map_err(|_| Failure::new("provider_error"))?;
    let visibility = visibility_of(call.op, &value, call.shape.repo.as_deref());
    let projected = project(&value, call.op).map_err(Failure::new)?;
    Ok((projected, visibility))
}

/// Calls are retried only for idempotent operations (the key is sent), at most `MAX_RETRIES` times,
/// and only on transient failures. 401 and 429 are never retried here.
fn transient(failure: &Failure) -> bool {
    matches!(failure.code, "timeout" | "provider_unreachable")
        || (failure.code == "provider_error" && failure.status.is_some_and(|s| s >= 500))
}

async fn run_call_with_retries(
    ex: &Exchange<'_>,
    call: &Call,
) -> Result<(Value, Option<(String, bool)>), Failure> {
    let attempts = if call.op.idempotent {
        1 + MAX_RETRIES
    } else {
        1
    };
    let mut last = Failure::new("provider_error");
    for attempt in 0..attempts {
        if attempt > 0 {
            tokio::time::sleep(Duration::from_millis(100 * u64::from(attempt))).await;
        }
        match run_call(ex, call).await {
            Ok(done) => return Ok(done),
            Err(failure) if transient(&failure) && attempt + 1 < attempts => last = failure,
            Err(failure) => return Err(failure),
        }
    }
    Err(last)
}

/// Runs one job against the broker. Every path ends in a `Done`, never a panic or a raw body.
pub async fn execute(id: u64, job: Job, python: PathBuf, script: PathBuf) -> Done {
    let ex = Exchange {
        python: &python,
        script: &script,
        deadline: tokio::time::Instant::now() + CALL_TIMEOUT,
    };
    let reply = match job {
        Job::Device {
            account,
            base,
            scopes,
        } => {
            let outcome = run_device(&ex, &base, &scopes).await;
            Reply::Device { account, outcome }
        }
        Job::Poll {
            account,
            base,
            device_code,
            ..
        } => Reply::Poll {
            outcome: run_poll(&ex, &base, &device_code).await,
            account,
        },
        Job::Refresh {
            account,
            base,
            refresh,
            then,
        } => Reply::Refresh {
            outcome: run_refresh(&ex, &base, &refresh).await,
            account,
            then,
        },
        Job::Revoke { base, token } => {
            let body = json!({ "token": token });
            let headers = [
                ("Content-Type", "application/json".to_owned()),
                ("Accept", "application/json".to_owned()),
            ];
            let outcome = match ex
                .send(
                    &base,
                    "POST",
                    "/login/oauth/revoke",
                    &headers,
                    Some(&body),
                    None,
                )
                .await
            {
                Ok(response) => json_object(&response.body)
                    .map(|o| o.get("revoked").and_then(Value::as_bool).unwrap_or(false)),
                Err(failure) => Err(failure),
            };
            Reply::Revoke { outcome }
        }
        Job::Call(call) => {
            let outcome = run_call_with_retries(&ex, &call).await;
            Reply::Call { call, outcome }
        }
    };
    Done { id, reply }
}

/// Device login state of one account while it is `connecting`. The device code stays in memory.
struct Device {
    device_code: String,
    user_code: String,
    interval: u64,
    expires_at: Instant,
    next_poll: Option<Instant>,
    polls: u32,
    requested: Vec<String>,
    consented: Option<Vec<String>>,
}

/// Result of a call that a proposal (agent, skill or user card) was waiting for.
pub struct Settled {
    pub proposal: String,
    pub state: tools::State,
    pub reason: Option<&'static str>,
    pub result: Option<String>,
}

/// Last operation call, for the snapshot. Operation names and codes only, never content.
#[derive(Debug, Clone, Serialize)]
pub struct LastCall {
    pub operation: &'static str,
    pub outcome: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code: Option<&'static str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub retry_after: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub proposal_id: Option<String>,
}

/// One audit record: a closed vocabulary, no account id, arguments, tokens or content.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Audit {
    pub kind: &'static str,
    pub operation: &'static str,
    pub risk: &'static str,
    pub outcome: &'static str,
}

/// A validated, not yet started operation call.
pub struct Plan {
    pub provider: &'static Provider,
    pub op: &'static OpDef,
    pub account: String,
    shape: Shape,
    pub risk: Access,
}

impl Plan {
    /// Proposal arguments: the Core re-validates these on authorize, not the model.
    pub fn wrap(&self) -> Value {
        json!({
            "provider": self.provider.id,
            "operation": self.op.name,
            "account": self.account,
            "input": Value::Object(self.shape.input.clone()),
        })
    }
    pub fn tool_risk(&self) -> tools::Risk {
        self.risk.tool_risk()
    }
}

#[derive(Debug, Serialize)]
pub struct ScopeView {
    pub id: &'static str,
    pub label: &'static str,
    pub access: Access,
}

#[derive(Debug, Serialize)]
pub struct OperationView {
    pub name: &'static str,
    pub scope: &'static str,
    pub risk: Access,
}

#[derive(Debug, Serialize)]
pub struct ProviderView {
    pub id: &'static str,
    pub scopes: Vec<ScopeView>,
    pub operations: Vec<OperationView>,
}

/// One account, exactly the S5 snapshot fields (docs/S5.md E1) plus `fake`: true when the provider is served
/// by a loopback test fake (the UI shows SERVIDOR FALSO for it). Never a token, device code or last error.
#[derive(Debug, Serialize)]
pub struct ItemView {
    pub id: String,
    pub provider: String,
    pub label: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub account_ref: Option<String>,
    pub status: Status,
    pub granted_scopes: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pending_scopes: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_code: Option<String>,
    pub fake: bool,
}

/// Snapshot block `connections`. No tokens, device codes, arguments or response content.
#[derive(Debug, Serialize)]
pub struct View {
    pub revision: u64,
    pub storage_error: bool,
    pub items: Vec<ItemView>,
    pub providers: Vec<ProviderView>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_call: Option<LastCall>,
}

/// Connection Manager state owned by the Core. Network work is queued here and run by transport.
#[derive(Default)]
pub struct Manager {
    ledger: Ledger,
    storage_error: bool,
    devices: BTreeMap<String, Device>,
    errors: BTreeMap<String, &'static str>,
    /// Account to repo (`owner/name`) to `private`, learned from `repo.get` results only.
    visibility: BTreeMap<String, BTreeMap<String, bool>>,
    budget: BTreeMap<String, VecDeque<Instant>>,
    queue: VecDeque<(u64, Job)>,
    running: Option<u64>,
    next_job: u64,
    last_call: Option<LastCall>,
    settled: Vec<Settled>,
    /// Seconds to wait when the budget refused the last call (for `retry_after`).
    last_wait: u64,
    events: VecDeque<&'static str>,
    audit: VecDeque<Audit>,
}

fn status_code(status: Status) -> Result<(), &'static str> {
    match status {
        Status::Connected => Ok(()),
        Status::Expired => Err("expired"),
        Status::ReauthRequired => Err("reauth_required"),
        _ => Err("not_connected"),
    }
}

fn job_account(job: &Job) -> Option<&str> {
    match job {
        Job::Device { account, .. } | Job::Poll { account, .. } | Job::Refresh { account, .. } => {
            Some(account)
        }
        Job::Call(call) => Some(&call.account),
        Job::Revoke { .. } => None,
    }
}

impl Manager {
    /// Loads `connections.json`. A damaged ledger disables account writes only; Core keeps running.
    pub fn configure(&mut self, storage: &Storage) {
        match storage.connections_ledger() {
            Ok(ledger) if ledger.validate() => self.ledger = ledger,
            _ => self.storage_error = true,
        }
        // A connect pending across a restart has no device to poll any more.
        for account in &mut self.ledger.accounts {
            if account.status == Status::Connecting {
                account.status = Status::Disconnected;
            }
        }
    }

    pub fn view(&self) -> View {
        let items = self
            .ledger
            .accounts
            .iter()
            .map(|account| {
                let device = self
                    .devices
                    .get(&account.id)
                    .filter(|_| account.status == Status::Connecting);
                ItemView {
                    id: account.id.clone(),
                    provider: account.provider.clone(),
                    label: account.label.clone(),
                    account_ref: account.account_ref.clone(),
                    status: account.status,
                    granted_scopes: account.granted_scopes.clone(),
                    pending_scopes: device.map(|d| d.requested.clone()),
                    user_code: device.map(|d| d.user_code.clone()),
                    fake: fake_base(&account.provider).is_some(),
                }
            })
            .collect();
        View {
            revision: self.ledger.revision,
            storage_error: self.storage_error,
            items,
            providers: PROVIDERS
                .iter()
                .map(|p| ProviderView {
                    id: p.id,
                    scopes: p
                        .scopes
                        .iter()
                        .map(|s| ScopeView {
                            id: s.id,
                            label: s.label,
                            access: s.access,
                        })
                        .collect(),
                    operations: p
                        .operations
                        .iter()
                        .map(|o| OperationView {
                            name: o.name,
                            scope: o.scope,
                            risk: o.risk,
                        })
                        .collect(),
                })
                .collect(),
            last_call: self.last_call.clone(),
        }
    }

    fn index(&self, id: &str) -> Option<usize> {
        self.ledger.accounts.iter().position(|a| a.id == id)
    }

    fn account(&self, id: &str) -> Option<&Account> {
        self.ledger.accounts.iter().find(|a| a.id == id)
    }

    fn status_of(&self, id: &str) -> Option<Status> {
        self.account(id).map(|a| a.status)
    }

    pub fn check_revision(&self, revision: Option<u64>) -> Result<(), &'static str> {
        if self.storage_error {
            return Err("connections_storage_error");
        }
        match revision {
            Some(seen) if seen != self.ledger.revision => Err("stale_connection_revision"),
            _ => Ok(()),
        }
    }

    /// Persists `next` (CAS revision + 1) and only then makes it the in-memory ledger.
    fn commit(&mut self, storage: &Storage, mut next: Ledger) -> Result<(), &'static str> {
        next.revision = self
            .ledger
            .revision
            .checked_add(1)
            .ok_or("connections_revision_exhausted")?;
        if !next.validate() {
            return Err("invalid_connections_state");
        }
        storage
            .save_connections_ledger(&next)
            .map_err(|_| "connections_storage_error")?;
        self.ledger = next;
        Ok(())
    }

    fn set_status(
        &mut self,
        storage: &Storage,
        id: &str,
        status: Status,
        error: Option<&'static str>,
    ) -> Result<(), &'static str> {
        let Some(index) = self.index(id) else {
            return Err("unknown_connection");
        };
        let mut next = self.ledger.clone();
        next.accounts[index].status = status;
        if status != Status::Connected {
            next.accounts[index].granted_scopes.clear();
        }
        self.commit(storage, next)?;
        match error {
            Some(code) => self.errors.insert(id.to_owned(), code),
            None => self.errors.remove(id),
        };
        Ok(())
    }

    fn log(
        &mut self,
        kind: &'static str,
        operation: &'static str,
        risk: &'static str,
        outcome: &'static str,
    ) {
        if self.events.len() == AUDIT_MAX {
            self.events.pop_front();
        }
        self.events.push_back(kind);
        if self.audit.len() == AUDIT_MAX {
            self.audit.pop_front();
        }
        self.audit.push_back(Audit {
            kind,
            operation,
            risk,
            outcome,
        });
    }

    pub fn take_events(&mut self) -> Vec<&'static str> {
        self.events.drain(..).collect()
    }

    pub fn take_audit(&mut self) -> Vec<Audit> {
        self.audit.drain(..).collect()
    }

    pub fn take_settled(&mut self) -> Vec<Settled> {
        std::mem::take(&mut self.settled)
    }

    fn push(&mut self, job: Job) {
        self.next_job += 1;
        self.queue.push_back((self.next_job, job));
    }

    /// The single network slot: one job at a time, never while another is running.
    pub fn take_job(&mut self) -> Option<(u64, Job)> {
        if self.running.is_some() {
            return None;
        }
        let (id, job) = self.queue.pop_front()?;
        self.running = Some(id);
        Some((id, job))
    }

    pub fn busy(&self) -> bool {
        self.running.is_some() || self.queue.len() >= QUEUE_LIMIT
    }

    /// Earliest timer: a due device poll or a device expiry.
    pub fn deadline(&self) -> Option<Instant> {
        self.devices
            .values()
            .flat_map(|d| {
                let poll = d.consented.as_ref().and(d.next_poll);
                [poll, Some(d.expires_at)]
            })
            .flatten()
            .min()
    }

    /// Timer step: expire devices that ran out, and queue polls that are due.
    pub fn tick(&mut self, storage: &Storage, now: Instant) {
        let expired: Vec<String> = self
            .devices
            .iter()
            .filter(|(_, d)| now >= d.expires_at)
            .map(|(id, _)| id.clone())
            .collect();
        for id in expired {
            self.devices.remove(&id);
            if self
                .set_status(storage, &id, Status::Error, Some("device_expired"))
                .is_ok()
            {
                self.log("connection_expired", "none", "none", "device_expired");
            }
        }
        let due: Vec<String> = self
            .devices
            .iter()
            .filter(|(_, d)| d.consented.is_some() && d.next_poll.is_some_and(|t| t <= now))
            .map(|(id, _)| id.clone())
            .collect();
        for id in due {
            let base = fake_base(self.provider_of(&id))
                .unwrap_or_default()
                .to_owned();
            let Some(device) = self.devices.get_mut(&id) else {
                continue;
            };
            device.next_poll = None;
            let job = Job::Poll {
                account: id.clone(),
                base,
                device_code: device.device_code.clone(),
                consented: device.consented.clone().unwrap_or_default(),
            };
            self.push(job);
        }
    }

    fn provider_of(&self, id: &str) -> &str {
        self.account(id).map_or("", |a| a.provider.as_str())
    }

    pub fn add(
        &mut self,
        storage: &Storage,
        provider: &str,
        label: &str,
        revision: Option<u64>,
    ) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        if provider_by_id(provider).is_none() {
            return "invalid_provider";
        }
        if !label_ok(label) {
            return "invalid_label";
        }
        if self.ledger.accounts.len() >= MAX_ACCOUNTS {
            return "connection_limit";
        }
        let mut next = self.ledger.clone();
        next.accounts.push(Account {
            id: format!("conn_{}", random_hex(8)),
            provider: provider.to_owned(),
            label: label.to_owned(),
            account_ref: None,
            status: Status::Disconnected,
            granted_scopes: Vec::new(),
            created: unix_now(),
            last_ok: None,
        });
        match self.commit(storage, next) {
            Ok(()) => {
                self.log("connection_added", "none", "none", "ok");
                "ok"
            }
            Err(code) => code,
        }
    }

    pub fn connect(&mut self, storage: &Storage, id: &str, revision: Option<u64>) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        let Some(index) = self.index(id) else {
            return "unknown_connection";
        };
        let provider = provider_by_id(&self.ledger.accounts[index].provider).expect("validated");
        let Some(base) = fake_base(provider.id) else {
            return "real_backend_unsupported";
        };
        match self.ledger.accounts[index].status {
            Status::Connecting => return "already_connecting",
            Status::Connected => return "already_connected",
            _ => {}
        }
        if self.busy() {
            return "busy";
        }
        if let Err(code) = self.set_status(storage, id, Status::Connecting, None) {
            return code;
        }
        let scopes = provider.scopes.iter().map(|s| s.id.to_owned()).collect();
        self.push(Job::Device {
            account: id.to_owned(),
            base: base.to_owned(),
            scopes,
        });
        "ok"
    }

    /// Consent per scope: a non-empty subset of the scopes the device login requested.
    pub fn consent(
        &mut self,
        id: &str,
        scopes: Vec<String>,
        revision: Option<u64>,
    ) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        if self.status_of(id) != Some(Status::Connecting) {
            return "invalid_state";
        }
        let Some(device) = self.devices.get(id) else {
            return "invalid_state";
        };
        if scopes.is_empty() {
            return "invalid_args";
        }
        let mut chosen: Vec<String> = Vec::new();
        for scope in &scopes {
            if !device.requested.contains(scope) {
                return "scope_not_requested";
            }
            if !chosen.contains(scope) {
                chosen.push(scope.clone());
            }
        }
        if self.busy() {
            return "busy";
        }
        let job = Job::Poll {
            account: id.to_owned(),
            base: fake_base(self.provider_of(id))
                .unwrap_or_default()
                .to_owned(),
            device_code: device.device_code.clone(),
            consented: chosen.clone(),
        };
        if let Some(device) = self.devices.get_mut(id) {
            device.consented = Some(chosen);
            device.next_poll = None;
        }
        self.push(job);
        "ok"
    }

    pub fn refresh(
        &mut self,
        storage: &Storage,
        vault: &LlmState,
        id: &str,
        revision: Option<u64>,
    ) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        let Some(status) = self.status_of(id) else {
            return "unknown_connection";
        };
        if matches!(status, Status::Disconnected | Status::Connecting) {
            return "not_connected";
        }
        let provider = self.provider_of(id).to_owned();
        let Some(base) = provider_by_id(&provider).and_then(|p| fake_base(p.id)) else {
            return "real_backend_unsupported";
        };
        let Some(refresh) = vault.connection_token(id, "refresh") else {
            let _ = self.set_status(storage, id, Status::ReauthRequired, Some("reauth_required"));
            return "reauth_required";
        };
        if self.busy() {
            return "busy";
        }
        self.push(Job::Refresh {
            account: id.to_owned(),
            base: base.to_owned(),
            refresh,
            then: None,
        });
        "ok"
    }

    /// Drops local secrets and queued work of the account. A `revoke` also asks the provider
    /// (the job runs only when a fake exists; without one no socket is opened).
    fn drop_account_secrets(
        &mut self,
        storage: &Storage,
        vault: &mut LlmState,
        id: &str,
        revoke: bool,
    ) -> Result<(), &'static str> {
        let access = vault.connection_token(id, "access");
        let refresh = vault.connection_token(id, "refresh");
        let base = fake_base(self.provider_of(id)).map(str::to_owned);
        if revoke {
            if let (Some(base), Some(token)) = (base.clone(), access.clone().or(refresh)) {
                self.push(Job::Revoke { base, token });
            }
        }
        // Calls waiting for this account can no longer run: their proposals fail now.
        let mut kept = VecDeque::new();
        for (job_id, job) in self.queue.drain(..) {
            if job_account(&job) == Some(id) {
                if let Job::Call(call) = job {
                    if let Some(proposal) = call.proposal {
                        self.settled.push(Settled {
                            proposal,
                            state: tools::State::Failed,
                            reason: Some("not_connected"),
                            result: None,
                        });
                    }
                }
            } else {
                kept.push_back((job_id, job));
            }
        }
        self.queue = kept;
        self.devices.remove(id);
        vault.clear_connection(storage, id)?;
        Ok(())
    }

    pub fn disconnect(
        &mut self,
        storage: &Storage,
        vault: &mut LlmState,
        id: &str,
        revision: Option<u64>,
    ) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        if self.index(id).is_none() {
            return "unknown_connection";
        }
        if let Err(code) = self.drop_account_secrets(storage, vault, id, false) {
            return code;
        }
        if let Err(code) = self.set_status(storage, id, Status::Disconnected, None) {
            return code;
        }
        self.log("connection_disconnected", "none", "none", "ok");
        "ok"
    }

    pub fn revoke(
        &mut self,
        storage: &Storage,
        vault: &mut LlmState,
        id: &str,
        revision: Option<u64>,
    ) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        if self.index(id).is_none() {
            return "unknown_connection";
        }
        if let Err(code) = self.drop_account_secrets(storage, vault, id, true) {
            return code;
        }
        if let Err(code) = self.set_status(storage, id, Status::Disconnected, None) {
            return code;
        }
        self.log("connection_revoked", "none", "none", "ok");
        "ok"
    }

    pub fn remove(
        &mut self,
        storage: &Storage,
        vault: &mut LlmState,
        id: &str,
        revision: Option<u64>,
    ) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        let Some(index) = self.index(id) else {
            return "unknown_connection";
        };
        let mut next = self.ledger.clone();
        next.accounts.remove(index);
        if let Err(code) = self.drop_account_secrets(storage, vault, id, true) {
            return code;
        }
        if let Err(code) = self.commit(storage, next) {
            return code;
        }
        self.errors.remove(id);
        self.visibility.remove(id);
        self.budget.remove(id);
        self.log("connection_removed", "none", "none", "ok");
        "ok"
    }

    /// Operation of an account's provider, by name. Unknown accounts and names are refused.
    pub fn op_for(
        &self,
        id: &str,
        operation: &str,
    ) -> Result<(&'static Provider, &'static OpDef), &'static str> {
        let account = self.account(id).ok_or("unknown_connection")?;
        let provider = provider_by_id(&account.provider).ok_or("unknown_connection")?;
        let op = operation_of(provider, operation).ok_or("unknown_operation")?;
        Ok((provider, op))
    }

    /// Records that a write waits for the user's approval card (no network yet).
    pub fn pending_approval(&mut self, operation: &'static str, proposal: String) {
        self.last_call = Some(LastCall {
            operation,
            outcome: "pending_approval",
            code: None,
            retry_after: None,
            proposal_id: Some(proposal),
        });
    }

    /// Validates one operation call for an account (explicit or resolved for a tool). Nothing is
    /// sent here. Scope, status, arguments and risk are all decided before any approval or queue.
    pub fn plan(
        &self,
        provider: &'static Provider,
        op: &'static OpDef,
        account: Option<&str>,
        args: &Value,
    ) -> Result<Plan, &'static str> {
        let shape = validate(op, args)?;
        let account = match account {
            Some(id) => {
                let found = self.account(id).ok_or("unknown_connection")?;
                if found.provider != provider.id {
                    return Err("unknown_connection");
                }
                status_code(found.status)?;
                if !found.granted_scopes.iter().any(|s| s == op.scope) {
                    return Err("scope_not_granted");
                }
                id.to_owned()
            }
            None => self.resolve(provider, op)?,
        };
        let risk = self.effective_risk(&account, op, &shape);
        Ok(Plan {
            provider,
            op,
            account,
            shape,
            risk,
        })
    }

    /// Account for a tool that names no account: the first connected one granting the scope.
    fn resolve(&self, provider: &'static Provider, op: &OpDef) -> Result<String, &'static str> {
        let candidates: Vec<&Account> = self
            .ledger
            .accounts
            .iter()
            .filter(|a| a.provider == provider.id)
            .collect();
        if candidates.is_empty() {
            return Err("not_connected");
        }
        let connected: Vec<&&Account> = candidates
            .iter()
            .filter(|a| a.status == Status::Connected)
            .collect();
        if connected.is_empty() {
            return Err(status_code(candidates[0].status)
                .err()
                .unwrap_or("not_connected"));
        }
        connected
            .iter()
            .find(|a| a.granted_scopes.iter().any(|s| s == op.scope))
            .map(|a| a.id.clone())
            .ok_or("scope_not_granted")
    }

    /// Public when a write targets a repo not known to be private. Unknown visibility is public.
    fn effective_risk(&self, account: &str, op: &OpDef, shape: &Shape) -> Access {
        if op.name == "issues.create" {
            let private = shape
                .repo
                .as_deref()
                .and_then(|repo| self.visibility.get(account)?.get(repo).copied());
            return if private == Some(true) {
                Access::Write
            } else {
                Access::Public
            };
        }
        op.risk
    }

    fn spend(&mut self, account: &str, now: Instant) -> Result<(), u64> {
        let window = self.budget.entry(account.to_owned()).or_default();
        while window
            .front()
            .is_some_and(|t| now.duration_since(*t) >= BUDGET_WINDOW)
        {
            window.pop_front();
        }
        if window.len() >= CALLS_PER_MINUTE {
            let oldest = window.front().copied().unwrap_or(now);
            let wait = BUDGET_WINDOW
                .saturating_sub(now.duration_since(oldest))
                .as_secs()
                .clamp(1, RETRY_AFTER_MAX);
            return Err(wait);
        }
        window.push_back(now);
        Ok(())
    }

    /// Starts an approved (or read-only) plan. Refusals leave the proposal as the caller decides.
    pub fn start(
        &mut self,
        vault: &LlmState,
        plan: Plan,
        proposal: Option<String>,
        now: Instant,
    ) -> Result<(), &'static str> {
        let op_name = plan.op.name;
        let result = self.start_inner(vault, &plan, proposal.clone(), now);
        if let Err(code) = result {
            let retry_after = (code == "rate_limited").then_some(self.last_wait);
            self.last_call = Some(LastCall {
                operation: op_name,
                outcome: "failed",
                code: Some(code),
                retry_after,
                proposal_id: proposal,
            });
            return Err(code);
        }
        Ok(())
    }

    fn start_inner(
        &mut self,
        vault: &LlmState,
        plan: &Plan,
        proposal: Option<String>,
        now: Instant,
    ) -> Result<(), &'static str> {
        if matches!(plan.risk, Access::Public | Access::Destructive) && !options().allow_public {
            return Err("public_disabled");
        }
        let base = fake_base(plan.provider.id).ok_or("real_backend_unsupported")?;
        let found = self.account(&plan.account).ok_or("unknown_connection")?;
        status_code(found.status)?;
        if !found.granted_scopes.iter().any(|s| s == plan.op.scope) {
            return Err("scope_not_granted");
        }
        let token = vault
            .connection_token(&plan.account, "access")
            .ok_or("reauth_required")?;
        let account_ref = found.account_ref.clone();
        if self.busy() {
            return Err("busy");
        }
        self.spend(&plan.account, now).map_err(|wait| {
            self.last_wait = wait;
            "rate_limited"
        })?;
        let shape = validate(plan.op, &Value::Object(plan.shape.input.clone()))?;
        let call = Call {
            proposal: proposal.clone(),
            account: plan.account.clone(),
            provider: plan.provider.id,
            op: plan.op,
            shape,
            base: base.to_owned(),
            token,
            account_ref,
            idempotency: random_hex(16),
            retried: false,
        };
        self.last_call = Some(LastCall {
            operation: plan.op.name,
            outcome: "queued",
            code: None,
            retry_after: None,
            proposal_id: proposal,
        });
        self.push(Job::Call(Box::new(call)));
        Ok(())
    }

    /// Re-validates an approved proposal from its stored wrapper (never from model text).
    pub fn plan_proposal(&self, args: &Value) -> Result<Plan, &'static str> {
        let provider = args
            .get("provider")
            .and_then(Value::as_str)
            .and_then(provider_by_id)
            .ok_or("invalid_args")?;
        let op = args
            .get("operation")
            .and_then(Value::as_str)
            .and_then(|name| operation(provider, name))
            .ok_or("invalid_args")?;
        let account = args
            .get("account")
            .and_then(Value::as_str)
            .ok_or("invalid_args")?;
        let input = args.get("input").ok_or("invalid_args")?;
        self.plan(provider, op, Some(account), input)
    }

    /// Whether a skill dependency `conn:<provider>.<op>` can run now (a connected grant exists).
    pub fn dependency_ready(&self, provider: &str, op: &str) -> bool {
        let Some(provider) = provider_by_id(provider) else {
            return false;
        };
        let Some(op) = operation(provider, op) else {
            return false;
        };
        self.ledger.accounts.iter().any(|a| {
            a.provider == provider.id
                && a.status == Status::Connected
                && a.granted_scopes.iter().any(|s| s == op.scope)
        })
    }

    /// A job task ended without a reply: the single slot is released and the call is marked lost.
    pub fn abandon(&mut self, id: u64) {
        if self.running == Some(id) {
            self.running = None;
            self.last_call = Some(LastCall {
                operation: "none",
                outcome: "failed",
                code: Some("provider_unreachable"),
                retry_after: None,
                proposal_id: None,
            });
        }
    }

    /// Settles a finished job: applies tokens, statuses and projected results. Returns the proposal
    /// outcome for the Core, if any. Stale replies (job no longer running) change nothing.
    pub fn settle(
        &mut self,
        storage: &Storage,
        vault: &mut LlmState,
        done: Done,
        now: Instant,
    ) -> Option<Settled> {
        if self.running != Some(done.id) {
            return None;
        }
        self.running = None;
        match done.reply {
            Reply::Device { account, outcome } => {
                if self.status_of(&account) != Some(Status::Connecting) {
                    return None;
                }
                match outcome {
                    Ok(grant) => {
                        let requested = provider_by_id(self.provider_of(&account))
                            .map(|p| p.scopes.iter().map(|s| s.id.to_owned()).collect())
                            .unwrap_or_default();
                        self.devices.insert(
                            account,
                            Device {
                                device_code: grant.device_code,
                                user_code: grant.user_code,
                                interval: grant.interval.clamp(1, POLL_INTERVAL_MAX),
                                expires_at: now + Duration::from_secs(grant.expires_in),
                                next_poll: None,
                                polls: 0,
                                requested,
                                consented: None,
                            },
                        );
                    }
                    Err(failure) => {
                        let status = failure_status(failure.code);
                        let _ = self.set_status(storage, &account, status, Some(failure.code));
                    }
                }
                None
            }
            Reply::Poll { account, outcome } => {
                if self.status_of(&account) != Some(Status::Connecting) {
                    return None;
                }
                match outcome {
                    Ok(Poll::Pending) => {
                        let device = self.devices.get_mut(&account)?;
                        device.polls += 1;
                        if device.polls >= MAX_POLLS {
                            self.devices.remove(&account);
                            let _ = self.set_status(
                                storage,
                                &account,
                                Status::Error,
                                Some("device_expired"),
                            );
                        } else {
                            device.next_poll = Some(now + Duration::from_secs(device.interval));
                        }
                    }
                    Ok(Poll::Token {
                        access,
                        refresh,
                        scope,
                        account: name,
                    }) => self.grant(storage, vault, &account, access, refresh, scope, name),
                    Err(failure) => {
                        self.devices.remove(&account);
                        let status = failure_status(failure.code);
                        let _ = self.set_status(storage, &account, status, Some(failure.code));
                    }
                }
                None
            }
            Reply::Refresh {
                account,
                then,
                outcome,
            } => self.settle_refresh(storage, vault, &account, then, outcome),
            Reply::Revoke { outcome } => {
                let _ = outcome;
                None
            }
            Reply::Call { call, outcome } => self.settle_call(storage, vault, call, outcome),
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn grant(
        &mut self,
        storage: &Storage,
        vault: &mut LlmState,
        id: &str,
        access: String,
        refresh: Option<String>,
        scope: Vec<String>,
        name: Option<String>,
    ) {
        let Some(device) = self.devices.remove(id) else {
            return;
        };
        let Some(account_ref) = name.filter(|n| !n.is_empty()) else {
            let _ = self.set_status(storage, id, Status::Error, Some("provider_error"));
            return;
        };
        if self
            .account(id)
            .and_then(|a| a.account_ref.as_deref())
            .is_some_and(|known| known != account_ref)
        {
            let _ = self.set_status(storage, id, Status::Error, Some("account_mismatch"));
            return;
        }
        let consented = device.consented.unwrap_or_default();
        let granted: Vec<String> = consented
            .into_iter()
            .filter(|s| scope.is_empty() || scope.contains(s))
            .collect();
        if granted.is_empty() {
            let _ = self.set_status(storage, id, Status::Error, Some("scope_not_granted"));
            return;
        }
        if vault
            .set_connection_tokens(storage, id, Some(access), refresh)
            .is_err()
        {
            let _ = self.set_status(storage, id, Status::Error, Some("secrets_storage_error"));
            return;
        }
        let Some(index) = self.index(id) else {
            return;
        };
        let mut next = self.ledger.clone();
        {
            let account = &mut next.accounts[index];
            account.status = Status::Connected;
            account.account_ref = Some(account_ref);
            account.granted_scopes = granted;
            account.last_ok = Some(unix_now());
        }
        if self.commit(storage, next).is_ok() {
            self.errors.remove(id);
            self.log("connection_consented", "none", "none", "ok");
            self.log("connection_connected", "none", "none", "ok");
        }
    }

    fn settle_refresh(
        &mut self,
        storage: &Storage,
        vault: &mut LlmState,
        id: &str,
        then: Option<Box<Call>>,
        outcome: Result<(String, Option<String>, Option<String>), Failure>,
    ) -> Option<Settled> {
        match outcome {
            Ok((access, rotated, name)) => {
                let known = self.account(id).and_then(|a| a.account_ref.clone());
                if name.is_some() && known.is_some() && name != known {
                    let _ = self.set_status(storage, id, Status::Error, Some("account_mismatch"));
                    return then.and_then(|call| self.fail_proposal(call, "account_mismatch"));
                }
                // The provider rotates refresh tokens: the new one replaces the spent one.
                let refresh = rotated.or_else(|| vault.connection_token(id, "refresh"));
                if vault
                    .set_connection_tokens(storage, id, Some(access.clone()), refresh)
                    .is_err()
                {
                    return then.and_then(|call| self.fail_proposal(call, "secrets_storage_error"));
                }
                if self
                    .set_status(storage, id, Status::Connected, None)
                    .is_ok()
                {
                    self.log("connection_refreshed", "none", "none", "ok");
                }
                if let Some(mut call) = then {
                    call.token = access;
                    call.retried = true;
                    self.push(Job::Call(call));
                }
                None
            }
            Err(failure) => {
                let rejected = failure.code == "unauthorized"
                    || failure.detail.as_deref() == Some("invalid_grant");
                let (status, code) = if rejected {
                    let _ = vault.clear_connection(storage, id);
                    (Status::ReauthRequired, "reauth_required")
                } else {
                    (Status::Expired, "expired")
                };
                let _ = self.set_status(storage, id, status, Some(code));
                self.log("connection_expired", "none", "none", code);
                then.and_then(|call| self.fail_proposal(call, code))
            }
        }
    }

    fn fail_proposal(&mut self, call: Box<Call>, code: &'static str) -> Option<Settled> {
        self.last_call = Some(LastCall {
            operation: call.op.name,
            outcome: "failed",
            code: Some(code),
            retry_after: None,
            proposal_id: call.proposal.clone(),
        });
        call.proposal.map(|proposal| Settled {
            proposal,
            state: tools::State::Failed,
            reason: Some(code),
            result: None,
        })
    }

    fn settle_call(
        &mut self,
        storage: &Storage,
        vault: &mut LlmState,
        call: Box<Call>,
        outcome: Result<(Value, Option<(String, bool)>), Failure>,
    ) -> Option<Settled> {
        let op = call.op.name;
        let risk = call.op.risk.name();
        let account = call.account.clone();
        match outcome {
            Ok((value, visibility)) => {
                if let Some((repo, private)) = visibility {
                    self.visibility
                        .entry(account.clone())
                        .or_default()
                        .insert(repo, private);
                }
                if self.status_of(&account) != Some(Status::Connected) {
                    self.log("connection_call", op, risk, "not_connected");
                    return self.fail_proposal(call, "not_connected");
                }
                self.last_call = Some(LastCall {
                    operation: op,
                    outcome: "ok",
                    code: None,
                    retry_after: None,
                    proposal_id: call.proposal.clone(),
                });
                self.log("connection_call", op, risk, "ok");
                call.proposal.map(|proposal| Settled {
                    proposal,
                    state: tools::State::Executed,
                    reason: None,
                    result: Some(value.to_string()),
                })
            }
            Err(failure) => {
                if failure.code == "unauthorized" && !call.retried {
                    let base = fake_base(call.provider).map(str::to_owned);
                    if let (Some(base), Some(refresh)) =
                        (base, vault.connection_token(&account, "refresh"))
                    {
                        self.push(Job::Refresh {
                            account,
                            base,
                            refresh,
                            then: Some(call),
                        });
                        return None;
                    }
                    let _ = self.set_status(
                        storage,
                        &account,
                        Status::ReauthRequired,
                        Some("reauth_required"),
                    );
                    self.log("connection_call", op, risk, "reauth_required");
                    return self.fail_proposal(call, "reauth_required");
                }
                let code = match failure.code {
                    "unauthorized" => {
                        let _ =
                            self.set_status(storage, &account, Status::Expired, Some("expired"));
                        "expired"
                    }
                    "account_mismatch" => {
                        let _ = self.set_status(
                            storage,
                            &account,
                            Status::Error,
                            Some("account_mismatch"),
                        );
                        "account_mismatch"
                    }
                    other => other,
                };
                self.log("connection_call", op, risk, code);
                self.last_call = Some(LastCall {
                    operation: op,
                    outcome: "failed",
                    code: Some(code),
                    retry_after: failure.retry_after,
                    proposal_id: call.proposal.clone(),
                });
                call.proposal.map(|proposal| Settled {
                    proposal,
                    state: tools::State::Failed,
                    reason: Some(code),
                    result: None,
                })
            }
        }
    }
}

/// Status an account takes after a connect or login step fails.
fn failure_status(code: &str) -> Status {
    match code {
        "timeout" | "provider_unreachable" => Status::Offline,
        _ => Status::Error,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn github() -> &'static Provider {
        provider_by_id("github").unwrap()
    }

    #[test]
    fn descriptors_are_fixed_and_empty_providers_are_valid() {
        let ids: Vec<&str> = PROVIDERS.iter().map(|p| p.id).collect();
        assert_eq!(ids, ["github", "google", "homeassistant", "mcp"]);
        assert!(PROVIDERS[1..]
            .iter()
            .all(|p| p.scopes.is_empty() && p.operations.is_empty()));
        let github = github();
        assert_eq!(github.scopes.len(), 3);
        // Every operation names a declared scope and a method the broker allows.
        for op in github.operations {
            assert!(
                github.scopes.iter().any(|s| s.id == op.scope),
                "{}",
                op.name
            );
            assert!(matches!(op.method, "GET" | "POST" | "PATCH"));
        }
        assert_eq!(
            operation(github, "pulls.comment").unwrap().risk,
            Access::Public
        );
    }

    #[test]
    fn call_form_resolves_only_declared_operations() {
        assert!(parse_call("conn:github.issues.create").is_some());
        assert!(parse_call("conn:github.repos.list").is_some());
        assert!(parse_call("conn:github.delete_everything").is_none());
        assert!(parse_call("conn:nope.repos.list").is_none());
        assert!(parse_call("github.repos.list").is_none());
    }

    #[test]
    fn arguments_are_exact_typed_and_path_bound() {
        let op = operation(github(), "issues.update").unwrap();
        let shape = validate(
            op,
            &json!({"repo": "demo/private-repo", "number": 3, "state": "closed"}),
        )
        .unwrap();
        assert_eq!(shape.path, "/api/repos/demo/private-repo/issues/3");
        assert_eq!(shape.body, Some(json!({"state": "closed"})));
        assert!(validate(
            op,
            &json!({"repo": "demo/private-repo", "number": 3, "state": "merged"})
        )
        .is_err());
        assert!(validate(op, &json!({"repo": "demo/private-repo", "number": 0})).is_err());
        assert!(validate(
            op,
            &json!({"repo": "demo/private-repo", "number": 1, "x": true})
        )
        .is_err());
        assert!(validate(op, &json!({"repo": "../x/y", "number": 1})).is_err());
        assert!(validate(op, &json!({"repo": "a/b/c", "number": 1})).is_err());
        let get = operation(github(), "repo.get").unwrap();
        assert_eq!(
            validate(get, &json!({"repo": "demo/public-repo"}))
                .unwrap()
                .body,
            None
        );
    }

    #[test]
    fn projection_keeps_listed_scalars_only() {
        let op = operation(github(), "issues.create").unwrap();
        let raw = json!({"number": 7, "title": "t", "url": "u", "state": "open", "public": false,
                         "internal_note": "secret", "labels": [{"name": "x"}]});
        let projected = project(&raw, op).unwrap();
        assert_eq!(
            projected,
            json!({"number": 7, "title": "t", "url": "u", "state": "open", "public": false})
        );
        assert_eq!(project(&json!("text"), op), Err("provider_error"));
    }

    #[test]
    fn fake_targets_must_be_loopback_ip_literals_without_a_path() {
        assert!(parse_fake("github=http://127.0.0.1:8080").is_ok());
        assert!(parse_fake("github=http://[::1]:8080").is_ok());
        assert!(parse_fake("github=http://localhost:8080").is_err());
        assert!(parse_fake("github=http://127.0.0.1:8080/api").is_err());
        assert!(parse_fake("github=https://127.0.0.1:8080").is_err());
        assert!(parse_fake("github=http://93.184.216.34:80").is_err());
        assert!(parse_fake("unknown=http://127.0.0.1:8080").is_err());
    }

    #[test]
    fn labels_and_repo_names_are_strict() {
        assert!(label_ok("pessoal"));
        assert!(!label_ok(""));
        assert!(!label_ok("a\nb"));
        assert!(!label_ok(&"x".repeat(LABEL_MAX + 1)));
        assert!(repo_ok("demo/repo.name-1"));
        assert!(!repo_ok("demo"));
        assert!(!repo_ok("demo/../x"));
        assert!(!repo_ok("demo/a b"));
    }
}
