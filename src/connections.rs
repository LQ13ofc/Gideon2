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
    collections::{BTreeMap, BTreeSet, VecDeque},
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
    /// Fixed MCP registration (test only): the profile of the fake server the Core launches under the
    /// plugin sandbox. `None` is production: `mcp` connect answers `real_backend_unsupported`.
    pub fake_mcp: Option<String>,
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

/// Profile of the fixed fake MCP registration, if any.
pub fn mcp_profile() -> Option<&'static str> {
    options().fake_mcp.as_deref()
}

/// Whether the provider has a test backend: an HTTP fake, or the fixed fake MCP server.
pub fn has_fake(provider: &str) -> bool {
    if provider == "mcp" {
        mcp_profile().is_some()
    } else {
        fake_base(provider).is_some()
    }
}

/// `--connections-fake-mcp` value: one of the fixture profiles.
pub fn parse_fake_mcp(raw: &str) -> Result<String, &'static str> {
    if crate::mcp::PROFILES.contains(&raw) {
        Ok(raw.to_owned())
    } else {
        Err("invalid_connections_fake_mcp")
    }
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
    /// Opaque provider id: `[A-Za-z0-9_-]`, 1..=64 bytes (no path separators).
    Id,
    /// One e-mail address, at most 254 bytes, no whitespace, `<`, `>` or a second `@`.
    Email,
    /// RFC 3339 date-time with seconds: `YYYY-MM-DDTHH:MM:SS[.frac](Z|±HH:MM)`.
    Rfc3339,
    /// File name for a drive: 1..=128 bytes, no `/` or `\`, never `.` or `..`.
    FileName,
    /// Home Assistant entity id: `domain.object`, lowercase `[a-z0-9_]` parts, at most 64 bytes each.
    EntityId,
    /// Home Assistant domain or service name: 1..=64 bytes of `[a-z_]`.
    Slug,
    /// Integer 0..=255 (light brightness).
    Byte,
    /// MCP tool arguments: a JSON object of scalars up to 4 KiB (checked again against the tool schema).
    Args,
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
        // The real GitHub API ignores Idempotency-Key: a failed create is never retried (no retry on 5xx).
        // scripts/verify_e1_connections.py still expects the retry; the coordinator updates that gate.
        idempotent: false,
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

const ID: Field = Field {
    name: "id",
    kind: Kind::Id,
    required: true,
};
const EMAIL_TO: Field = Field {
    name: "to",
    kind: Kind::Email,
    required: true,
};
const MAIL_SUBJECT: Field = Field {
    name: "subject",
    kind: Kind::Text(256),
    required: true,
};
const MAIL_BODY: Field = Field {
    name: "body",
    kind: Kind::Text(4096),
    required: true,
};
const EVENT_START: Field = Field {
    name: "start",
    kind: Kind::Rfc3339,
    required: true,
};
const EVENT_END: Field = Field {
    name: "end",
    kind: Kind::Rfc3339,
    required: true,
};
const FILE_NAME: Field = Field {
    name: "name",
    kind: Kind::FileName,
    required: true,
};
const FILE_CONTENT: Field = Field {
    name: "content",
    kind: Kind::Text(8192),
    required: false,
};

/// Google scopes (docs/S5.md E2.2). Read, send and delete are separate scopes; the device flow
/// asks for all of them and the user grants each one.
const GOOGLE_SCOPES: [ScopeDef; 7] = [
    ScopeDef {
        id: "gmail.read",
        label: "Ler lista de e-mails (id, remetente, assunto)",
        access: Access::Read,
    },
    ScopeDef {
        id: "gmail.send",
        label: "Enviar e-mail em seu nome",
        access: Access::Public,
    },
    ScopeDef {
        id: "gmail.delete",
        label: "Apagar e-mail",
        access: Access::Destructive,
    },
    ScopeDef {
        id: "calendar.read",
        label: "Ler eventos da agenda",
        access: Access::Read,
    },
    ScopeDef {
        id: "calendar.write",
        label: "Criar eventos na agenda",
        access: Access::Write,
    },
    ScopeDef {
        id: "drive.read",
        label: "Listar arquivos do Drive",
        access: Access::Read,
    },
    ScopeDef {
        id: "drive.write",
        label: "Criar arquivos no Drive",
        access: Access::Write,
    },
];

/// Projections list ids and headers only: message bodies and file contents never leave the fake.
const MAIL_FIELDS: &[&str] = &["id", "from", "subject"];
const SENT_FIELDS: &[&str] = &["id", "to", "subject"];
const DELETED_FIELDS: &[&str] = &["id", "deleted"];
const EVENT_FIELDS: &[&str] = &["id", "title", "start", "end"];
const FILE_FIELDS: &[&str] = &["id", "name"];

const GOOGLE_OPERATIONS: [OpDef; 7] = [
    OpDef {
        name: "gmail.messages.list",
        scope: "gmail.read",
        risk: Access::Read,
        method: "GET",
        path: "/api/gmail/messages",
        params: &[],
        body: &[],
        idempotent: true,
        project: MAIL_FIELDS,
    },
    OpDef {
        name: "gmail.send",
        scope: "gmail.send",
        // Sending is always public: the user approves it explicitly, never by default.
        risk: Access::Public,
        method: "POST",
        path: "/api/gmail/send",
        params: &[],
        body: &[EMAIL_TO, MAIL_SUBJECT, MAIL_BODY],
        // No natural key: a failed send is never retried (no Idempotency-Key).
        idempotent: false,
        project: SENT_FIELDS,
    },
    OpDef {
        name: "gmail.messages.delete",
        scope: "gmail.delete",
        risk: Access::Destructive,
        method: "DELETE",
        path: "/api/gmail/messages/{id}",
        params: &[ID],
        body: &[],
        idempotent: false,
        project: DELETED_FIELDS,
    },
    OpDef {
        name: "calendar.events.list",
        scope: "calendar.read",
        risk: Access::Read,
        method: "GET",
        path: "/api/calendar/events",
        params: &[],
        body: &[],
        idempotent: true,
        project: EVENT_FIELDS,
    },
    OpDef {
        name: "calendar.events.create",
        scope: "calendar.write",
        risk: Access::Write,
        method: "POST",
        path: "/api/calendar/events",
        params: &[],
        body: &[TITLE, EVENT_START, EVENT_END],
        // Idempotency-Key is sent: a retry after a 5xx or a timeout replays the same event.
        idempotent: true,
        project: EVENT_FIELDS,
    },
    OpDef {
        name: "drive.files.list",
        scope: "drive.read",
        risk: Access::Read,
        method: "GET",
        path: "/api/drive/files",
        params: &[],
        body: &[],
        idempotent: true,
        project: FILE_FIELDS,
    },
    OpDef {
        name: "drive.files.create",
        scope: "drive.write",
        risk: Access::Write,
        method: "POST",
        path: "/api/drive/files",
        params: &[],
        body: &[FILE_NAME, FILE_CONTENT],
        // The Drive route has no Idempotency-Key: a failed create is never retried.
        idempotent: false,
        project: FILE_FIELDS,
    },
];

const ENTITY_ID: Field = Field {
    name: "entity_id",
    kind: Kind::EntityId,
    required: true,
};
const DOMAIN: Field = Field {
    name: "domain",
    kind: Kind::Slug,
    required: true,
};
const SERVICE: Field = Field {
    name: "service",
    kind: Kind::Slug,
    required: true,
};
const BRIGHTNESS: Field = Field {
    name: "brightness",
    kind: Kind::Byte,
    required: false,
};

/// Home Assistant scopes (docs/S5.md E2.3). The token is one long-lived bearer, not OAuth: the user
/// consents per scope, then pastes the token (`connection_set_token`). Dangerous services need the third scope.
const HA_SCOPES: [ScopeDef; 3] = [
    ScopeDef {
        id: "states.read",
        label: "Ler estados das entidades",
        access: Access::Read,
    },
    ScopeDef {
        id: "services.call",
        label: "Chamar serviços (ligar, desligar, ajustar)",
        access: Access::Write,
    },
    ScopeDef {
        id: "services.dangerous",
        label: "Serviços perigosos (fechaduras, alarme, portões)",
        access: Access::Destructive,
    },
];

/// States list only the entity id, the state and the friendly name: the other attributes never leave.
const HA_FIELDS: &[&str] = &["entity_id", "state", "attributes.friendly_name"];

const HA_OPERATIONS: [OpDef; 3] = [
    OpDef {
        name: "states.list",
        scope: "states.read",
        risk: Access::Read,
        method: "GET",
        path: "/api/states",
        params: &[],
        body: &[],
        idempotent: true,
        project: HA_FIELDS,
    },
    OpDef {
        name: "state.get",
        scope: "states.read",
        risk: Access::Read,
        method: "GET",
        path: "/api/states/{entity_id}",
        params: &[ENTITY_ID],
        body: &[],
        idempotent: true,
        project: HA_FIELDS,
    },
    OpDef {
        name: "service.call",
        scope: "services.call",
        // Write by default; `effective_risk` makes a dangerous service destructive (needs services.dangerous).
        risk: Access::Write,
        method: "POST",
        path: "/api/services/{domain}/{service}",
        params: &[DOMAIN, SERVICE],
        body: &[ENTITY_ID, BRIGHTNESS],
        // A service call has no natural key: a failed call is never retried (no Idempotency-Key).
        idempotent: false,
        project: HA_FIELDS,
    },
];

const MCP_TOOL: Field = Field {
    name: "tool",
    kind: Kind::Id,
    required: true,
};
const MCP_ARGS: Field = Field {
    name: "args",
    kind: Kind::Args,
    required: false,
};

/// MCP scopes (docs/S5.md E2.4). Discover lists tools; each call still needs its own approval.
const MCP_SCOPES: [ScopeDef; 3] = [
    ScopeDef {
        id: "mcp.discover",
        label: "Listar as ferramentas do servidor MCP",
        access: Access::Read,
    },
    ScopeDef {
        id: "mcp.call",
        label: "Chamar ferramentas MCP (aprovação a cada chamada)",
        access: Access::Write,
    },
    ScopeDef {
        id: "mcp.call_destructive",
        label: "Ferramentas que apagam (aprovação a cada chamada)",
        access: Access::Destructive,
    },
];

/// No HTTP here: the Core talks to the sandboxed server over stdio (`mcp.rs`), so `method` and `path` are unused.
const MCP_OPERATIONS: [OpDef; 2] = [
    OpDef {
        name: "mcp.discover",
        scope: "mcp.discover",
        risk: Access::Read,
        method: "MCP",
        path: "",
        params: &[],
        body: &[],
        idempotent: false,
        project: &[],
    },
    OpDef {
        name: "mcp.call",
        scope: "mcp.call",
        // Write by default; `effective_risk` makes a tool that deletes or removes destructive.
        risk: Access::Write,
        method: "MCP",
        path: "",
        params: &[MCP_TOOL],
        body: &[MCP_ARGS],
        idempotent: false,
        project: &[],
    },
];

/// Providers whose account takes one token pasted by the user (`connection_set_token`), not a device login.
const TOKEN_PROVIDERS: &[&str] = &["homeassistant"];

/// The provider whose server is a Core-managed sandboxed process: connect starts it, consent grants scopes.
fn uses_process(provider: &str) -> bool {
    provider == "mcp"
}

fn uses_token(provider: &str) -> bool {
    TOKEN_PROVIDERS.contains(&provider)
}

/// Services that open, unlock or disarm something physical (docs/S5.md E2.3). Calling one is destructive.
fn dangerous_service(domain: &str, service: &str) -> bool {
    matches!(
        (domain, service),
        ("lock", "unlock" | "open") | ("cover", "open_cover" | "close_cover")
    ) || domain == "alarm_control_panel"
        || domain == "garage_door"
}

fn is_dangerous_call(op: &OpDef, shape: &Shape) -> bool {
    op.name == "service.call"
        && matches!(
            (shape.input.get("domain"), shape.input.get("service")),
            (Some(Value::String(domain)), Some(Value::String(service)))
                if dangerous_service(domain, service)
        )
}

/// Every scope one call needs: its operation scope, plus `services.dangerous` for a dangerous service.
fn required_scopes(op: &OpDef, shape: &Shape) -> Vec<&'static str> {
    let mut needed = vec![op.scope];
    if is_dangerous_call(op, shape) {
        needed.push("services.dangerous");
    }
    if op.name == "mcp.call" && shape.mcp_destructive {
        needed.push("mcp.call_destructive");
    }
    needed
}

/// Home Assistant long-lived token: printable ASCII without spaces, 16..=256 bytes.
fn ha_token_ok(token: &str) -> bool {
    (16..=256).contains(&token.len()) && token.bytes().all(|b| b.is_ascii_graphic())
}

/// Fixed registry.
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
        scopes: &GOOGLE_SCOPES,
        operations: &GOOGLE_OPERATIONS,
    },
    Provider {
        id: "homeassistant",
        label: "Home Assistant",
        scopes: &HA_SCOPES,
        operations: &HA_OPERATIONS,
    },
    Provider {
        id: "mcp",
        label: "MCP",
        scopes: &MCP_SCOPES,
        operations: &MCP_OPERATIONS,
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

const AGENT_TOOLS: [AgentTool; 8] = [
    AgentTool {
        name: "mcp_call",
        provider: "mcp",
        operation: "mcp.call",
    },
    AgentTool {
        name: "ha_get_state",
        provider: "homeassistant",
        operation: "state.get",
    },
    AgentTool {
        name: "ha_call_service",
        provider: "homeassistant",
        operation: "service.call",
    },
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
    AgentTool {
        name: "calendar_list_events",
        provider: "google",
        operation: "calendar.events.list",
    },
    AgentTool {
        name: "gmail_list_messages",
        provider: "google",
        operation: "gmail.messages.list",
    },
    AgentTool {
        name: "calendar_create_event",
        provider: "google",
        operation: "calendar.events.create",
    },
];

pub fn agent_tool(name: &str) -> Option<&'static AgentTool> {
    AGENT_TOOLS
        .iter()
        .find(|tool| tool.name == name && has_fake(tool.provider))
}

/// Prompt lines for the agent, only for tools whose provider has a fake. Argument names are exact.
pub fn agent_prompt() -> String {
    let mut text = String::new();
    for tool in AGENT_TOOLS.iter().filter(|t| has_fake(t.provider)) {
        match tool.name {
            "github_list_repos" => text.push_str("\n- github_list_repos {}"),
            "github_create_issue" => text.push_str(
                "\n- github_create_issue {\"repo\": \"owner/name\", \"title\": string up to 256 chars, \"body\": string up to 4096 chars, optional}",
            ),
            "calendar_list_events" => text.push_str("\n- calendar_list_events {}"),
            "gmail_list_messages" => text.push_str("\n- gmail_list_messages {}"),
            "calendar_create_event" => text.push_str(
                "\n- calendar_create_event {\"title\": string up to 256 chars, \"start\": RFC 3339 date-time with seconds, \"end\": RFC 3339 date-time not before start}",
            ),
            "ha_get_state" => text.push_str(
                "\n- ha_get_state {\"entity_id\": \"domain.object\"}",
            ),
            "ha_call_service" => text.push_str(
                "\n- ha_call_service {\"domain\": string, \"service\": string, \"entity_id\": \"domain.object\", \"brightness\": integer 0..255, optional}",
            ),
            "mcp_call" => text.push_str(
                "\n- mcp_call {\"tool\": tool name, plus that tool's own arguments as flat string, number or boolean fields} (output arrives as data prefixed [mcp_output:NAME])",
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
    // MCP operations carry the provider in their own name (`mcp.call`), so `conn:mcp.call` is the full name.
    let prefixed = format!("{}.", provider.id);
    let op = operation(provider, rest)
        .or_else(|| operation(provider, name).filter(|op| !op.name.starts_with(&prefixed)))?;
    Some((provider, op))
}

/// `mcp_call {"tool": name, field: scalar, ...}` (the only shape a model can send, tool calls are flat)
/// becomes the operation form `{"tool": name, "args": {field: scalar, ...}}`.
pub fn mcp_nest(flat: &Value) -> Result<Value, &'static str> {
    let object = flat.as_object().ok_or("invalid_args")?;
    let tool = object.get("tool").ok_or("invalid_args")?;
    let rest: Map<String, Value> = object
        .iter()
        .filter(|(key, _)| key.as_str() != "tool")
        .map(|(key, value)| (key.clone(), value.clone()))
        .collect();
    Ok(json!({"tool": tool, "args": Value::Object(rest)}))
}

/// The `conn:` form of an operation, the tool name of its proposal cards (`conn:github.repos.list`, `conn:mcp.call`).
pub fn call_name(provider: &Provider, op: &OpDef) -> String {
    match op.name.strip_prefix(provider.id) {
        Some(rest) if rest.starts_with('.') => format!("conn:{}", op.name),
        _ => format!("conn:{}.{}", provider.id, op.name),
    }
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
        Kind::Id => value.as_str().filter(|s| id_ok(s)).map(Value::from),
        Kind::Email => value.as_str().filter(|s| email_ok(s)).map(Value::from),
        Kind::Rfc3339 => value.as_str().filter(|s| rfc3339_ok(s)).map(Value::from),
        Kind::FileName => value.as_str().filter(|s| file_name_ok(s)).map(Value::from),
        Kind::EntityId => value.as_str().filter(|s| entity_ok(s)).map(Value::from),
        Kind::Slug => value.as_str().filter(|s| slug_ok(s)).map(Value::from),
        Kind::Byte => value.as_u64().filter(|n| *n <= 255).map(Value::from),
        Kind::Args => value
            .as_object()
            .filter(|object| mcp_args_ok(object))
            .map(|object| Value::Object(object.clone())),
    }
}

/// MCP arguments before the tool schema is known: scalar values only, names as in the schema subset.
fn mcp_args_ok(object: &Map<String, Value>) -> bool {
    object.len() <= 16
        && serde_json::to_vec(object).is_ok_and(|b| b.len() <= crate::mcp::ARGS_MAX)
        && object.iter().all(|(key, value)| {
            crate::mcp::name_ok(key)
                && matches!(value, Value::String(_) | Value::Number(_) | Value::Bool(_))
        })
}

/// `domain.object`: both parts 1..=64 bytes of lowercase letters, digits and `_` (the domain has no digits).
fn entity_ok(text: &str) -> bool {
    text.len() <= 129
        && text.split_once('.').is_some_and(|(domain, object)| {
            slug_ok(domain)
                && (1..=64).contains(&object.len())
                && object
                    .bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
        })
}

fn slug_ok(text: &str) -> bool {
    (1..=64).contains(&text.len()) && text.bytes().all(|b| b.is_ascii_lowercase() || b == b'_')
}

fn id_ok(text: &str) -> bool {
    (1..=64).contains(&text.len())
        && text
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
}

fn email_ok(text: &str) -> bool {
    let Some((local, domain)) = text.split_once('@') else {
        return false;
    };
    text.len() <= 254
        && (1..=64).contains(&local.len())
        && (1..=253).contains(&domain.len())
        && !domain.contains('@')
        && !text
            .chars()
            .any(|c| c.is_whitespace() || c.is_control() || c == '<' || c == '>')
}

fn file_name_ok(text: &str) -> bool {
    (1..=128).contains(&text.len())
        && text != "."
        && text != ".."
        && !text.contains('/')
        && !text.contains('\\')
        && !text.chars().any(char::is_control)
}

/// Strict RFC 3339 subset: seconds are required, fraction 1..=9 digits, offset `Z` or `±HH:MM`.
fn rfc3339_ok(text: &str) -> bool {
    let Some((date, time)) = text.split_once('T') else {
        return false;
    };
    let d = date.as_bytes();
    let date_ok = d.len() == 10
        && d[4] == b'-'
        && d[7] == b'-'
        && digits(&d[0..4])
        && digits(&d[5..7])
        && digits(&d[8..10])
        && (1..=12).contains(&num(&d[5..7]))
        && (1..=31).contains(&num(&d[8..10]));
    let t = time.as_bytes();
    if !date_ok
        || t.len() < 8
        || t[2] != b':'
        || t[5] != b':'
        || !digits(&t[0..2])
        || !digits(&t[3..5])
        || !digits(&t[6..8])
    {
        return false;
    }
    if num(&t[0..2]) > 23 || num(&t[3..5]) > 59 || num(&t[6..8]) > 60 {
        return false;
    }
    let mut rest = &t[8..];
    if let Some(after_dot) = rest.strip_prefix(b".") {
        let frac = after_dot.iter().take_while(|b| b.is_ascii_digit()).count();
        if !(1..=9).contains(&frac) {
            return false;
        }
        rest = &after_dot[frac..];
    }
    match rest {
        b"Z" => true,
        [sign @ (b'+' | b'-'), h1, h2, b':', m1, m2] => {
            digits(&[*h1, *h2])
                && digits(&[*m1, *m2])
                && num(&[*h1, *h2]) <= 23
                && num(&[*m1, *m2]) <= 59
                && (*sign == b'+' || *sign == b'-')
        }
        _ => false,
    }
}

fn digits(bytes: &[u8]) -> bool {
    !bytes.is_empty() && bytes.iter().all(u8::is_ascii_digit)
}

fn num(bytes: &[u8]) -> u32 {
    bytes
        .iter()
        .fold(0u32, |acc, b| acc * 10 + u32::from(b - b'0'))
}

/// Validated call: exact keys, typed values, then the path and body the broker will send.
pub struct Shape {
    pub input: Map<String, Value>,
    pub path: String,
    pub body: Option<Value>,
    pub repo: Option<String>,
    /// `mcp.call` of a tool classed destructive (set by the planner from the stored catalog).
    pub mcp_destructive: bool,
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
    // Every path parameter is a validated value without braces or slashes (see the Kind rules above).
    let mut path = op.path.to_owned();
    for (key, value) in &input {
        let text = match value {
            Value::String(text) => text.clone(),
            Value::Number(number) => number.to_string(),
            _ => continue,
        };
        path = path.replace(&format!("{{{key}}}"), &text);
    }
    // Only GET and DELETE carry no body; every write sends a JSON object (possibly empty).
    let body = if matches!(op.method, "GET" | "DELETE") {
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
        mcp_destructive: false,
    })
}

/// Projection keeps scalar fields listed by the descriptor; nested values never leave. A listed
/// `outer.inner` keeps one scalar inside an object (`attributes.friendly_name`) and nothing else of it.
fn project_object(value: &Value, fields: &[&str]) -> Value {
    let mut out = Map::new();
    if let Some(object) = value.as_object() {
        for field in fields {
            match field.split_once('.') {
                None => {
                    if let Some(scalar) = object.get(*field).filter(|v| is_scalar(v)) {
                        out.insert((*field).to_owned(), scalar.clone());
                    }
                }
                Some((outer, inner)) => {
                    if let Some(scalar) = object
                        .get(outer)
                        .and_then(|v| v.get(inner))
                        .filter(|v| is_scalar(v))
                    {
                        let entry = out
                            .entry(outer.to_owned())
                            .or_insert_with(|| Value::Object(Map::new()));
                        if let Value::Object(nested) = entry {
                            nested.insert(inner.to_owned(), scalar.clone());
                        }
                    }
                }
            }
        }
    }
    Value::Object(out)
}

fn is_scalar(value: &Value) -> bool {
    !value.is_object() && !value.is_array()
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
    /// When the account's current `granted_scopes` were granted (Unix ms). Absent in older ledgers.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub granted_at_ms: Option<u64>,
    /// MCP: tools of the last accepted `tools/list`, with their trust state.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub tools: Vec<crate::mcp::ToolRec>,
    /// MCP: a catalog was accepted once (later changes need re-approval).
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub catalog: bool,
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
                && account.tools.len() <= crate::mcp::MAX_TOOLS
                && (account.tools.is_empty() || uses_process(&account.provider))
                && account.tools.iter().all(crate::mcp::ToolRec::valid)
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
        /// Read from the vault when the job starts (`take_job`); `None` when no refresh token is stored.
        refresh: Option<String>,
        /// Access token stored when the job was queued. Another one stored at start means the tokens
        /// already rotated: the job skips the network and its call retries with the new access token.
        seen_access: Option<String>,
        then: Option<Box<Call>>,
    },
    Revoke {
        base: String,
        token: String,
    },
    Call(Box<Call>),
    /// Home Assistant: one `GET /api/states` with the pasted token (never stored before it is validated).
    Probe {
        account: String,
        base: String,
        token: String,
    },
    /// MCP: start the sandboxed server, list its tools, or call one tool.
    Mcp(Box<McpJob>),
}

/// What an MCP job does. Debug never prints arguments.
pub enum McpWork {
    Start,
    Discover {
        /// Queued by a skill step: a first catalog is not trusted automatically (every tool needs approval).
        from_skill: bool,
    },
    Call {
        tool: String,
        args: Map<String, Value>,
        /// Access class for the audit line (`write` or `destructive`).
        risk: &'static str,
    },
}

/// One MCP job. The command is fixed (`script`, `profile` come from the Core options).
pub struct McpJob {
    account: String,
    proposal: Option<String>,
    script: PathBuf,
    profile: String,
    work: McpWork,
}

/// Result of an MCP job before the Core applies it.
pub enum McpDone {
    Started(String),
    Listed(Value),
    Output(String),
}

/// The job that holds the network slot: its account and proposal (for audit and for settling it when
/// the job is abandoned), and whether the account was disconnected, revoked or removed while it ran.
struct Holder {
    account: Option<String>,
    proposal: Option<String>,
    operation: &'static str,
    risk: &'static str,
    cancelled: bool,
}

fn holder_of(job: &Job) -> Holder {
    let mut holder = Holder {
        account: job_account(job).map(str::to_owned),
        proposal: None,
        operation: "none",
        risk: "none",
        cancelled: false,
    };
    let call = match job {
        Job::Call(call) => Some(call.as_ref()),
        Job::Refresh { then, .. } => then.as_deref(),
        _ => None,
    };
    if let Some(call) = call {
        holder.proposal = call.proposal.clone();
        holder.operation = call.op.name;
        holder.risk = call.op.risk.name();
    }
    if let Job::Mcp(job) = job {
        holder.proposal = job.proposal.clone();
        match &job.work {
            McpWork::Start => {}
            McpWork::Discover { .. } => {
                holder.operation = "mcp.discover";
                holder.risk = "read";
            }
            McpWork::Call { risk, .. } => {
                holder.operation = "mcp.call";
                holder.risk = risk;
            }
        }
    }
    holder
}

impl std::fmt::Debug for Job {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Job::Device { .. } => "Job::Device",
            Job::Poll { .. } => "Job::Poll",
            Job::Refresh { .. } => "Job::Refresh",
            Job::Revoke { .. } => "Job::Revoke",
            Job::Call(_) => "Job::Call",
            Job::Probe { .. } => "Job::Probe",
            Job::Mcp(_) => "Job::Mcp",
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
        outcome: Result<Refreshed, Failure>,
    },
    Revoke {
        outcome: Result<bool, Failure>,
    },
    Call {
        call: Box<Call>,
        outcome: Result<(Value, Option<(String, bool)>), Failure>,
    },
    /// `account_ref` (the instance name) on success. The token comes back only to be stored or dropped.
    Probe {
        account: String,
        token: String,
        outcome: Result<String, Failure>,
    },
    Mcp {
        job: Box<McpJob>,
        outcome: Result<McpDone, Failure>,
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

/// A refresh answer: new access token, rotated refresh token, account name and the scopes the provider
/// now grants (`None` when the answer has no `scope` field; an empty list means every scope went away).
pub struct Refreshed {
    access: String,
    rotated: Option<String>,
    account: Option<String>,
    scope: Option<Vec<String>>,
}

async fn run_refresh(ex: &Exchange<'_>, base: &str, refresh: &str) -> Result<Refreshed, Failure> {
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
    let scope = object
        .get("scope")
        .and_then(Value::as_str)
        .map(|s| s.split_whitespace().map(str::to_owned).collect());
    Ok(Refreshed {
        access,
        rotated,
        account: response.meta.account.clone(),
        scope,
    })
}

/// One `GET /api/states` with the pasted token. The instance name comes back as `X-Instance`, which the
/// broker reports as the account; a body that is not a JSON list is a provider error.
async fn run_probe(ex: &Exchange<'_>, base: &str, token: &str) -> Result<String, Failure> {
    let headers = [("Accept", "application/json".to_owned())];
    let response = ex
        .send(base, "GET", "/api/states", &headers, None, Some(token))
        .await?;
    if !matches!(
        serde_json::from_slice::<Value>(&response.body),
        Ok(Value::Array(_))
    ) {
        return Err(Failure::new("provider_error"));
    }
    response
        .meta
        .account
        .filter(|name| !name.is_empty())
        .ok_or(Failure::new("provider_error"))
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
            ..
        } => Reply::Refresh {
            // No stored refresh token: refused like a rejected one, without a request.
            outcome: match refresh {
                Some(refresh) => run_refresh(&ex, &base, &refresh).await,
                None => Err(Failure::new("unauthorized")),
            },
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
        Job::Probe {
            account,
            base,
            token,
        } => {
            let outcome = run_probe(&ex, &base, &token).await;
            Reply::Probe {
                account,
                token,
                outcome,
            }
        }
        Job::Mcp(job) => {
            let outcome = run_mcp(&job, &python).await;
            Reply::Mcp { job, outcome }
        }
    };
    Done { id, reply }
}

/// Runs one MCP job on the sandboxed server (`mcp.rs`). Output is projected here, before the Core sees it.
async fn run_mcp(job: &McpJob, python: &Path) -> Result<McpDone, Failure> {
    mcp_work(job, python).await.map_err(Failure::new)
}

async fn mcp_work(job: &McpJob, python: &Path) -> Result<McpDone, &'static str> {
    use crate::mcp;
    match &job.work {
        McpWork::Start => mcp::start(&job.account, python, &job.script, &job.profile)
            .await
            .map(McpDone::Started),
        McpWork::Discover { .. } => mcp::request(&job.account, "tools/list", json!({}))
            .await
            .map(McpDone::Listed),
        McpWork::Call { tool, args, .. } => {
            let params = json!({"name": tool, "arguments": args});
            let result = mcp::request(&job.account, "tools/call", params).await?;
            mcp::project_output(&result).map(McpDone::Output)
        }
    }
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
    /// Fixed marker: `true` when the call returned MCP output, which is data and never an instruction.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub untrusted: Option<bool>,
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
    /// Started by a skill step (see `McpWork::Discover`).
    origin_skill: bool,
}

impl Plan {
    /// Marks the plan as coming from a skill step, so an MCP discover never trusts a first catalog.
    pub fn from_skill(mut self) -> Self {
        self.origin_skill = true;
        self
    }

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
    /// When `granted_scopes` were granted (Unix ms); absent when nothing is granted.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub granted_at_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pending_scopes: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_code: Option<String>,
    pub fake: bool,
    /// MCP accounts: discovered tools. Descriptions are server text for the user to read as PlainText.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tools: Option<Vec<ToolView>>,
}

/// One discovered MCP tool: its risk class and trust state, never its schema.
#[derive(Debug, Serialize)]
pub struct ToolView {
    pub name: String,
    pub risk: &'static str,
    pub state: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    pub description: String,
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
    /// Token accounts (`uses_token`) in `connecting`: the scopes the user consented to, awaiting the token.
    token_wait: BTreeMap<String, Vec<String>>,
    /// MCP accounts in `connecting` whose server answered `initialize` (the server name), awaiting consent.
    mcp_ready: BTreeMap<String, String>,
    /// Server starts per MCP account in this Core lifetime (restart limit).
    mcp_starts: BTreeMap<String, u32>,
    /// MCP accounts whose tools were listed by a successful discover in this process (never persisted).
    /// A reconnect, a failure or a restart clears it: `mcp.call` waits for a fresh discover.
    discovered: BTreeSet<String>,
    /// The job holding the network slot (set with `running`).
    holder: Option<Holder>,
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
    /// Ring events for the snapshot: (kind, closed outcome).
    events: VecDeque<(&'static str, &'static str)>,
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

/// Status and scope gate of one account for one operation, before any approval or network work. A
/// `reauth_required` account that no longer grants the scope answers `scope_not_granted`, like any
/// account without the scope; one that still grants it answers `reauth_required`.
fn account_gate(found: &Account, scope: &str) -> Result<(), &'static str> {
    let granted = found.granted_scopes.iter().any(|s| s == scope);
    if found.status == Status::ReauthRequired && !granted {
        return Err("scope_not_granted");
    }
    status_code(found.status)?;
    if !granted {
        return Err("scope_not_granted");
    }
    Ok(())
}

/// How usable a provider is for one scope, as seen by the CapabilityRegistry (S5 E3). It reads the ledger only.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Standing {
    /// No backend in this build or run (no fake configured): the API does not exist here.
    NoBackend,
    /// No account of the provider at all.
    NoAccount,
    /// Accounts exist and every one is disconnected (the user disconnected or revoked).
    Disconnected,
    /// A connected account grants the scope.
    Usable,
    /// A credential problem: an expired token.
    Expired,
    /// A credential problem: the account must authenticate again and still holds the scope.
    Reauth,
    /// The account exists but the scope is not granted.
    ScopeNotGranted,
    /// Connecting, offline or in error: not usable now, not a reason to leave the API.
    Unavailable,
}

impl Standing {
    /// Only a missing connection lets the visual route stand in. A credential problem never does.
    pub fn fallback_eligible(self) -> bool {
        matches!(self, Self::NoBackend | Self::NoAccount | Self::Disconnected)
    }
    /// Closed code of the standing, the reason of `route_unavailable`.
    pub fn code(self) -> &'static str {
        match self {
            Self::NoBackend => "no_api",
            Self::NoAccount | Self::Disconnected => "not_connected",
            Self::Usable => "available",
            Self::Expired => "expired",
            Self::Reauth => "reauth_required",
            Self::ScopeNotGranted => "scope_not_granted",
            Self::Unavailable => "unavailable",
        }
    }
}

fn job_account(job: &Job) -> Option<&str> {
    match job {
        Job::Device { account, .. } | Job::Poll { account, .. } | Job::Refresh { account, .. } => {
            Some(account)
        }
        Job::Call(call) => Some(&call.account),
        Job::Probe { account, .. } => Some(account),
        Job::Mcp(job) => Some(&job.account),
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
            // The sandboxed MCP server does not survive a Core restart: the account must connect again.
            if uses_process(&account.provider) && account.status != Status::Disconnected {
                account.status = Status::Disconnected;
                account.granted_scopes.clear();
            }
        }
    }

    pub fn view(&self) -> View {
        let items = self
            .ledger
            .accounts
            .iter()
            .map(|account| {
                let connecting = account.status == Status::Connecting;
                let device = self.devices.get(&account.id).filter(|_| connecting);
                // A token account waits for its consent and token: every scope of the provider is pending.
                // An MCP account asks for consent only once its server answered `initialize`.
                let token_pending = (connecting
                    && (uses_token(&account.provider)
                        || (uses_process(&account.provider)
                            && self.mcp_ready.contains_key(&account.id))))
                .then(|| {
                    provider_by_id(&account.provider)
                        .map(|p| p.scopes.iter().map(|s| s.id.to_owned()).collect())
                        .unwrap_or_default()
                });
                let tools =
                    (uses_process(&account.provider) && !account.tools.is_empty()).then(|| {
                        account
                            .tools
                            .iter()
                            .map(|t| ToolView {
                                name: t.name.clone(),
                                risk: if t.destructive {
                                    "destructive"
                                } else {
                                    "write"
                                },
                                state: t.state.name(),
                                reason: t.reason.clone(),
                                description: t.description.clone(),
                            })
                            .collect()
                    });
                ItemView {
                    id: account.id.clone(),
                    provider: account.provider.clone(),
                    label: account.label.clone(),
                    account_ref: account.account_ref.clone(),
                    status: account.status,
                    granted_scopes: account.granted_scopes.clone(),
                    granted_at_ms: account.granted_at_ms,
                    pending_scopes: token_pending.or_else(|| device.map(|d| d.requested.clone())),
                    user_code: device.map(|d| d.user_code.clone()),
                    fake: has_fake(&account.provider),
                    tools,
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
        // `reauth_required` keeps the scopes the user granted (only the token must be renewed); every
        // other state that is not connected forgets them.
        if !matches!(status, Status::Connected | Status::ReauthRequired) {
            next.accounts[index].granted_scopes.clear();
            next.accounts[index].granted_at_ms = None;
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
        self.events
            .push_back((kind, crate::protocol::code_outcome(outcome)));
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

    pub fn take_events(&mut self) -> Vec<(&'static str, &'static str)> {
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

    /// The single network slot: one job at a time, never while another is running. A refresh reads its
    /// refresh token now (not when it was queued). If the access token changed since it was queued, the
    /// tokens already rotated: the refresh is skipped and its call (if any) runs with the stored token.
    pub fn take_job(&mut self, vault: &LlmState) -> Option<(u64, Job)> {
        if self.running.is_some() {
            return None;
        }
        loop {
            let (id, job) = self.queue.pop_front()?;
            let job = match job {
                Job::Refresh {
                    account,
                    base,
                    seen_access,
                    then,
                    ..
                } => {
                    let access = vault.connection_token(&account, "access");
                    if access != seen_access {
                        match (then, access) {
                            (Some(mut call), Some(access)) => {
                                call.token = access;
                                call.retried = true;
                                Job::Call(call)
                            }
                            (Some(call), None) => {
                                let settled = self.fail_proposal(call, "reauth_required");
                                self.settled.extend(settled);
                                continue;
                            }
                            (None, _) => continue,
                        }
                    } else {
                        Job::Refresh {
                            refresh: vault.connection_token(&account, "refresh"),
                            account,
                            base,
                            seen_access,
                            then,
                        }
                    }
                }
                other => other,
            };
            self.holder = Some(holder_of(&job));
            self.running = Some(id);
            return Some((id, job));
        }
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
            tools: Vec::new(),
            catalog: false,
            granted_at_ms: None,
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
        if uses_process(provider.id) {
            return self.connect_process(storage, id);
        }
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
        if uses_token(provider.id) {
            // No device to poll: the account waits for consent and then for the pasted token.
            self.token_wait.remove(id);
            return "ok";
        }
        let scopes = provider.scopes.iter().map(|s| s.id.to_owned()).collect();
        self.push(Job::Device {
            account: id.to_owned(),
            base: base.to_owned(),
            scopes,
        });
        "ok"
    }

    /// MCP: connect starts the fixed fake server in the sandbox and runs `initialize`; consent follows.
    /// Without the fake registration nothing is started (`real_backend_unsupported`). Restarts are limited.
    fn connect_process(&mut self, storage: &Storage, id: &str) -> &'static str {
        let Some(profile) = mcp_profile() else {
            return "real_backend_unsupported";
        };
        match self.status_of(id) {
            Some(Status::Connecting) => return "already_connecting",
            Some(Status::Connected) => return "already_connected",
            _ => {}
        }
        if self.mcp_starts.get(id).copied().unwrap_or(0) >= crate::mcp::START_LIMIT {
            return "mcp_restart_limit";
        }
        if self.busy() {
            return "busy";
        }
        if let Err(code) = self.set_status(storage, id, Status::Connecting, None) {
            return code;
        }
        *self.mcp_starts.entry(id.to_owned()).or_insert(0) += 1;
        self.mcp_ready.remove(id);
        self.discovered.remove(id);
        self.push(Job::Mcp(Box::new(McpJob {
            account: id.to_owned(),
            proposal: None,
            script: crate::transport::fixtures_dir().join(crate::mcp::FAKE_SCRIPT),
            profile: profile.to_owned(),
            work: McpWork::Start,
        })));
        "ok"
    }

    /// MCP consent: the server already answered `initialize`; the chosen scopes are granted at once and
    /// the account is connected. No scope is granted before the user chooses it.
    fn consent_process(
        &mut self,
        storage: &Storage,
        id: &str,
        scopes: Vec<String>,
    ) -> &'static str {
        let Some(name) = self.mcp_ready.get(id).cloned() else {
            return "invalid_state";
        };
        let Some(provider) = provider_by_id(self.provider_of(id)) else {
            return "invalid_state";
        };
        if scopes.is_empty() {
            return "invalid_args";
        }
        if scopes
            .iter()
            .any(|scope| !provider.scopes.iter().any(|s| s.id == scope))
        {
            return "scope_not_requested";
        }
        let granted: Vec<String> = provider
            .scopes
            .iter()
            .filter(|s| scopes.iter().any(|c| c == s.id))
            .map(|s| s.id.to_owned())
            .collect();
        let Some(index) = self.index(id) else {
            return "unknown_connection";
        };
        let mut next = self.ledger.clone();
        {
            let account = &mut next.accounts[index];
            account.status = Status::Connected;
            account.account_ref = Some(name);
            account.granted_scopes = granted;
            account.granted_at_ms = Some(crate::protocol::unix_ms());
            account.last_ok = Some(unix_now());
        }
        if let Err(code) = self.commit(storage, next) {
            return code;
        }
        self.mcp_ready.remove(id);
        self.errors.remove(id);
        self.log("connection_consented", "none", "none", "ok");
        self.log("connection_connected", "none", "none", "ok");
        "ok"
    }

    /// Re-approval of discovered tools by the user: `needs_reapproval` tools named here become `trusted`.
    /// A rejected tool can never be trusted; an unknown name refuses the whole request.
    pub fn trust_tools(
        &mut self,
        storage: &Storage,
        id: &str,
        tools: &[String],
        revision: Option<u64>,
    ) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        let Some(index) = self.index(id) else {
            return "unknown_connection";
        };
        if !uses_process(&self.ledger.accounts[index].provider) {
            return "invalid_state";
        }
        if tools.is_empty() || tools.len() > crate::mcp::MAX_TOOLS {
            return "invalid_args";
        }
        let mut next = self.ledger.clone();
        for name in tools {
            let Some(tool) = next.accounts[index]
                .tools
                .iter_mut()
                .find(|t| &t.name == name)
            else {
                return "unknown_tool";
            };
            match tool.state {
                crate::mcp::ToolState::Rejected => return "tool_rejected",
                _ => tool.state = crate::mcp::ToolState::Trusted,
            }
        }
        if let Err(code) = self.commit(storage, next) {
            return code;
        }
        self.log("connection_trusted", "mcp.call", "write", "ok");
        "ok"
    }

    /// Consent per scope: a non-empty subset of the scopes the device login requested.
    pub fn consent(
        &mut self,
        storage: &Storage,
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
        if uses_token(self.provider_of(id)) {
            return self.consent_token(id, scopes);
        }
        if uses_process(self.provider_of(id)) {
            return self.consent_process(storage, id, scopes);
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

    /// Token accounts: consent is stored in memory only (no network) until the token is validated.
    fn consent_token(&mut self, id: &str, scopes: Vec<String>) -> &'static str {
        let Some(provider) = provider_by_id(self.provider_of(id)) else {
            return "invalid_state";
        };
        if scopes.is_empty() {
            return "invalid_args";
        }
        let mut chosen: Vec<String> = Vec::new();
        for scope in scopes {
            if !provider.scopes.iter().any(|s| s.id == scope) {
                return "scope_not_requested";
            }
            if !chosen.contains(&scope) {
                chosen.push(scope);
            }
        }
        self.token_wait.insert(id.to_owned(), chosen);
        "ok"
    }

    /// Starts the one-probe validation of the token of a consented `connecting` token account. The token is
    /// held in memory until the probe answers; it is never written before that.
    pub fn set_token(&mut self, id: &str, token: &str, revision: Option<u64>) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        let Some(index) = self.index(id) else {
            return "unknown_connection";
        };
        let account = &self.ledger.accounts[index];
        if !uses_token(&account.provider) || account.status != Status::Connecting {
            return "invalid_state";
        }
        if !self.token_wait.contains_key(id) {
            return "consent_required";
        }
        if !ha_token_ok(token) {
            return "invalid_token";
        }
        let Some(base) = fake_base(&account.provider) else {
            return "real_backend_unsupported";
        };
        if self.busy() {
            return "busy";
        }
        self.push(Job::Probe {
            account: id.to_owned(),
            base: base.to_owned(),
            token: token.to_owned(),
        });
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
        if vault.connection_token(id, "refresh").is_none() {
            let _ = self.set_status(storage, id, Status::ReauthRequired, Some("reauth_required"));
            return "reauth_required";
        }
        if self.busy() {
            return "busy";
        }
        self.push(Job::Refresh {
            account: id.to_owned(),
            base: base.to_owned(),
            refresh: None,
            seen_access: vault.connection_token(id, "access"),
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
        // A token account has no revoke endpoint: its token is only wiped locally (the user revokes it in the service).
        if revoke && !uses_token(self.provider_of(id)) {
            if let (Some(base), Some(token)) = (base.clone(), access.clone().or(refresh)) {
                self.push(Job::Revoke { base, token });
            }
        }
        // A job already running for this account is cancelled: its reply fails the proposal it carries and
        // stores nothing (see `settle`).
        if let Some(holder) = self
            .holder
            .as_mut()
            .filter(|h| h.account.as_deref() == Some(id))
        {
            holder.cancelled = true;
        }
        // Calls waiting for this account can no longer run: their proposals fail now.
        let mut kept = VecDeque::new();
        for (job_id, job) in self.queue.drain(..) {
            if job_account(&job) == Some(id) {
                let proposal = match job {
                    Job::Call(call) => call.proposal,
                    Job::Mcp(job) => job.proposal,
                    Job::Refresh { then, .. } => then.and_then(|call| call.proposal),
                    _ => None,
                };
                if let Some(proposal) = proposal {
                    self.settled.push(Settled {
                        proposal,
                        state: tools::State::Failed,
                        reason: Some("not_connected"),
                        result: None,
                    });
                }
            } else {
                kept.push_back((job_id, job));
            }
        }
        self.queue = kept;
        self.devices.remove(id);
        self.token_wait.remove(id);
        self.mcp_ready.remove(id);
        self.discovered.remove(id);
        // The sandboxed server dies with the account's access, whether or not a job is using it.
        crate::mcp::stop(id);
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
        // Revoking also forgets what the user trusted: tools must be discovered and trusted again.
        if let Some(index) = self.index(id).filter(|i| {
            let a = &self.ledger.accounts[*i];
            a.catalog || !a.tools.is_empty()
        }) {
            let mut next = self.ledger.clone();
            next.accounts[index].tools.clear();
            next.accounts[index].catalog = false;
            if let Err(code) = self.commit(storage, next) {
                return code;
            }
        }
        self.log("connection_revoked", "none", "none", "ok");
        "ok"
    }

    /// Revokes one granted scope of an account. The token stays in the vault; calls that need the
    /// scope answer `scope_not_granted` from then on. The audit event carries no content.
    pub fn revoke_scope(
        &mut self,
        storage: &Storage,
        id: &str,
        scope: &str,
        revision: Option<u64>,
    ) -> &'static str {
        if let Err(code) = self.check_revision(revision) {
            return code;
        }
        let Some(index) = self.index(id) else {
            return "unknown_connection";
        };
        let Some(provider) = provider_by_id(&self.ledger.accounts[index].provider) else {
            return "invalid_state";
        };
        if !provider.scopes.iter().any(|s| s.id == scope) {
            return "scope_not_requested";
        }
        if !self.ledger.accounts[index]
            .granted_scopes
            .iter()
            .any(|s| s == scope)
        {
            return "scope_not_granted";
        }
        let mut next = self.ledger.clone();
        {
            let account = &mut next.accounts[index];
            account.granted_scopes.retain(|s| s != scope);
            if account.granted_scopes.is_empty() {
                account.granted_at_ms = None;
            }
        }
        if let Err(code) = self.commit(storage, next) {
            return code;
        }
        self.log("connection_scope_revoked", "none", "none", "ok");
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
        self.mcp_starts.remove(id);
        self.log("connection_removed", "none", "none", "ok");
        "ok"
    }

    /// Standing of a provider for a scope (S5 E3). A credential problem on any account outranks a plain
    /// disconnected one, so the registry never reads "the user has no connection" when a token went bad.
    pub fn standing(&self, provider: &str, scope: &str) -> Standing {
        if !has_fake(provider) {
            return Standing::NoBackend;
        }
        let accounts: Vec<&Account> = self
            .ledger
            .accounts
            .iter()
            .filter(|a| a.provider == provider)
            .collect();
        if accounts.is_empty() {
            return Standing::NoAccount;
        }
        let grants = |a: &&Account| a.granted_scopes.iter().any(|s| s == scope);
        if accounts
            .iter()
            .any(|a| a.status == Status::Connected && grants(a))
        {
            return Standing::Usable;
        }
        if accounts.iter().any(|a| a.status == Status::Connected) {
            return Standing::ScopeNotGranted;
        }
        if accounts.iter().any(|a| a.status == Status::Expired) {
            return Standing::Expired;
        }
        if accounts.iter().any(|a| a.status == Status::ReauthRequired) {
            return if accounts
                .iter()
                .any(|a| a.status == Status::ReauthRequired && grants(a))
            {
                Standing::Reauth
            } else {
                Standing::ScopeNotGranted
            };
        }
        if accounts.iter().all(|a| a.status == Status::Disconnected) {
            Standing::Disconnected
        } else {
            Standing::Unavailable
        }
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
            untrusted: None,
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
        if uses_process(provider.id) {
            return self.plan_process(provider, op, account, shape);
        }
        let needed = required_scopes(op, &shape);
        let account = match account {
            Some(id) => {
                let found = self.account(id).ok_or("unknown_connection")?;
                if found.provider != provider.id {
                    return Err("unknown_connection");
                }
                for scope in &needed {
                    account_gate(found, scope)?;
                }
                id.to_owned()
            }
            None => self.resolve(provider, &needed)?,
        };
        let risk = self.effective_risk(&account, op, &shape);
        Ok(Plan {
            provider,
            op,
            account,
            shape,
            risk,
            origin_skill: false,
        })
    }

    /// MCP plan. Gates in order: account status and operation scope, the tool (known, not rejected,
    /// trusted), its arguments against the stored schema, then the destructive scope when the tool
    /// deletes or removes. A tool that is new or changed since the user last looked is not callable.
    fn plan_process(
        &self,
        provider: &'static Provider,
        op: &'static OpDef,
        account: Option<&str>,
        mut shape: Shape,
    ) -> Result<Plan, &'static str> {
        let id = match account {
            Some(id) => id.to_owned(),
            None => self.resolve(provider, &[op.scope])?,
        };
        let found = self.account(&id).ok_or("unknown_connection")?;
        if found.provider != provider.id {
            return Err("unknown_connection");
        }
        account_gate(found, op.scope)?;
        if op.name == "mcp.call" {
            // Trust from an earlier process or connection is not enough: the tools must be listed again first.
            if !self.discovered.contains(&id) {
                return Err("tool_not_verified");
            }
            let name = shape
                .input
                .get("tool")
                .and_then(Value::as_str)
                .ok_or("invalid_args")?;
            let tool = found
                .tools
                .iter()
                .find(|t| t.name == name)
                .ok_or("unknown_tool")?;
            match tool.state {
                crate::mcp::ToolState::Rejected => return Err("tool_rejected"),
                crate::mcp::ToolState::NeedsReapproval => return Err("tool_not_trusted"),
                crate::mcp::ToolState::Trusted => {}
            }
            let empty = Map::new();
            let args = match shape.input.get("args") {
                Some(Value::Object(args)) => args,
                _ => &empty,
            };
            crate::mcp::check_args(tool, args)?;
            shape.mcp_destructive = tool.destructive;
            for scope in required_scopes(op, &shape) {
                account_gate(found, scope)?;
            }
        }
        let risk = self.effective_risk(&id, op, &shape);
        Ok(Plan {
            provider,
            op,
            account: id,
            shape,
            risk,
            origin_skill: false,
        })
    }

    /// Account for a tool that names no account: the first connected one granting the scope.
    fn resolve(
        &self,
        provider: &'static Provider,
        needed: &[&str],
    ) -> Result<String, &'static str> {
        let grants_all = |a: &Account| {
            needed
                .iter()
                .all(|scope| a.granted_scopes.iter().any(|s| s == scope))
        };
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
            // Same answer as `plan` for an explicit account that lost its scope after a reauth.
            if candidates
                .iter()
                .all(|a| a.status == Status::ReauthRequired && !grants_all(a))
            {
                return Err("scope_not_granted");
            }
            return Err(status_code(candidates[0].status)
                .err()
                .unwrap_or("not_connected"));
        }
        connected
            .iter()
            .find(|a| grants_all(a))
            .map(|a| a.id.clone())
            .ok_or("scope_not_granted")
    }

    /// Public when a write targets a repo not known to be private. Unknown visibility is public.
    fn effective_risk(&self, account: &str, op: &OpDef, shape: &Shape) -> Access {
        if op.name == "service.call" && is_dangerous_call(op, shape) {
            return Access::Destructive;
        }
        if op.name == "mcp.call" && shape.mcp_destructive {
            return Access::Destructive;
        }
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
                untrusted: None,
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
        if uses_process(plan.provider.id) {
            return self.start_process(plan, proposal, now);
        }
        let base = fake_base(plan.provider.id).ok_or("real_backend_unsupported")?;
        let found = self.account(&plan.account).ok_or("unknown_connection")?;
        for scope in required_scopes(plan.op, &plan.shape) {
            account_gate(found, scope)?;
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
            untrusted: None,
        });
        self.push(Job::Call(Box::new(call)));
        Ok(())
    }

    /// Queues an MCP discover or call on the account's running server.
    fn start_process(
        &mut self,
        plan: &Plan,
        proposal: Option<String>,
        now: Instant,
    ) -> Result<(), &'static str> {
        let profile = mcp_profile().ok_or("real_backend_unsupported")?;
        let found = self.account(&plan.account).ok_or("unknown_connection")?;
        for scope in required_scopes(plan.op, &plan.shape) {
            account_gate(found, scope)?;
        }
        if !crate::mcp::running(&plan.account) {
            return Err("mcp_not_running");
        }
        if self.busy() {
            return Err("busy");
        }
        self.spend(&plan.account, now).map_err(|wait| {
            self.last_wait = wait;
            "rate_limited"
        })?;
        let work = if plan.op.name == "mcp.call" {
            let tool = plan
                .shape
                .input
                .get("tool")
                .and_then(Value::as_str)
                .ok_or("invalid_args")?
                .to_owned();
            let args = match plan.shape.input.get("args") {
                Some(Value::Object(args)) => args.clone(),
                _ => Map::new(),
            };
            McpWork::Call {
                tool,
                args,
                risk: plan.risk.name(),
            }
        } else {
            McpWork::Discover {
                from_skill: plan.origin_skill,
            }
        };
        self.last_call = Some(LastCall {
            operation: plan.op.name,
            outcome: "queued",
            code: None,
            retry_after: None,
            proposal_id: proposal.clone(),
            untrusted: None,
        });
        self.push(Job::Mcp(Box::new(McpJob {
            account: plan.account.clone(),
            proposal,
            script: crate::transport::fixtures_dir().join(crate::mcp::FAKE_SCRIPT),
            profile: profile.to_owned(),
            work,
        })));
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
                // A skill may depend on `conn:mcp.call` only once the user trusts at least one tool.
                && (op.name != "mcp.call"
                    || a.tools
                        .iter()
                        .any(|t| t.state == crate::mcp::ToolState::Trusted))
        })
    }

    /// A job task ended without a reply: the single slot is released and the call is marked lost. The
    /// proposal the job carried fails now (audited), so it never stays authorized forever.
    pub fn abandon(&mut self, id: u64) {
        if self.running == Some(id) {
            self.running = None;
            let holder = self.holder.take();
            let proposal = holder.as_ref().and_then(|h| h.proposal.clone());
            self.last_call = Some(LastCall {
                operation: "none",
                outcome: "failed",
                code: Some("provider_unreachable"),
                retry_after: None,
                proposal_id: proposal.clone(),
                untrusted: None,
            });
            if let Some(holder) = holder {
                self.log(
                    "connection_call",
                    holder.operation,
                    holder.risk,
                    "provider_unreachable",
                );
            }
            let settled = proposal.map(|proposal| Settled {
                proposal,
                state: tools::State::Failed,
                reason: Some("provider_unreachable"),
                result: None,
            });
            self.settled.extend(settled);
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
        if self.holder.take().is_some_and(|h| h.cancelled) {
            return self.cancelled_reply(done.reply);
        }
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
            Reply::Probe {
                account,
                token,
                outcome,
            } => {
                self.settle_probe(storage, vault, &account, token, outcome);
                None
            }
            Reply::Mcp { job, outcome } => self.settle_mcp(storage, *job, outcome),
        }
    }

    /// Reply of a job whose account was disconnected, revoked or removed while it ran: nothing is stored
    /// or marked connected, and the proposal it carried fails (a sandboxed server it started is stopped).
    fn cancelled_reply(&mut self, reply: Reply) -> Option<Settled> {
        match reply {
            Reply::Refresh { then, .. } => {
                then.and_then(|call| self.fail_proposal(call, "not_connected"))
            }
            Reply::Call { call, .. } => self.fail_proposal(call, "not_connected"),
            Reply::Mcp { job, .. } => match job.work {
                McpWork::Start => {
                    crate::mcp::stop(&job.account);
                    None
                }
                McpWork::Discover { .. } => {
                    self.mcp_fail_call("mcp.discover", "read", job.proposal, "not_connected")
                }
                McpWork::Call { risk, .. } => {
                    self.mcp_fail_call("mcp.call", risk, job.proposal, "not_connected")
                }
            },
            // Device, poll, probe and revoke replies find their account gone and change nothing.
            _ => None,
        }
    }

    /// Process-level MCP failure: the server is gone or unusable, so the account goes to `error`
    /// (a timeout, a crash, a protocol break or an oversized line). Core keeps running.
    fn mcp_failed(&mut self, storage: &Storage, id: &str, code: &'static str) {
        if crate::mcp::fatal(code) {
            crate::mcp::stop(id);
            self.mcp_ready.remove(id);
            self.discovered.remove(id);
            let _ = self.set_status(storage, id, Status::Error, Some(code));
        }
    }

    fn mcp_fail_call(
        &mut self,
        operation: &'static str,
        risk: &'static str,
        proposal: Option<String>,
        code: &'static str,
    ) -> Option<Settled> {
        self.log("connection_call", operation, risk, code);
        self.last_call = Some(LastCall {
            operation,
            outcome: "failed",
            code: Some(code),
            retry_after: None,
            proposal_id: proposal.clone(),
            untrusted: None,
        });
        proposal.map(|proposal| Settled {
            proposal,
            state: tools::State::Failed,
            reason: Some(code),
            result: None,
        })
    }

    fn settle_mcp(
        &mut self,
        storage: &Storage,
        job: McpJob,
        outcome: Result<McpDone, Failure>,
    ) -> Option<Settled> {
        let id = job.account.clone();
        match job.work {
            McpWork::Start => {
                if self.status_of(&id) != Some(Status::Connecting) {
                    crate::mcp::stop(&id);
                    return None;
                }
                match outcome {
                    Ok(McpDone::Started(name)) => {
                        self.mcp_ready.insert(id, name);
                    }
                    Ok(_) => {}
                    Err(failure) => {
                        crate::mcp::stop(&id);
                        let _ = self.set_status(storage, &id, Status::Error, Some(failure.code));
                    }
                }
                None
            }
            McpWork::Discover { from_skill } => {
                let operation = "mcp.discover";
                if self.status_of(&id) != Some(Status::Connected) {
                    return self.mcp_fail_call(operation, "read", job.proposal, "not_connected");
                }
                let listed = match outcome {
                    Ok(McpDone::Listed(value)) => value,
                    Ok(_) => return self.mcp_fail_call(operation, "read", None, "mcp_protocol"),
                    Err(failure) => {
                        self.mcp_failed(storage, &id, failure.code);
                        return self.mcp_fail_call(operation, "read", job.proposal, failure.code);
                    }
                };
                let index = self.index(&id)?;
                let account = &self.ledger.accounts[index];
                // Only a user's own discover trusts a first catalog; a skill's discover asks for approval.
                let trust_first = !account.catalog && !from_skill;
                let catalog = match crate::mcp::build_catalog(&listed, &account.tools, trust_first)
                {
                    Ok(catalog) => catalog,
                    Err(code) => {
                        if code == "mcp_protocol" {
                            self.mcp_failed(storage, &id, code);
                        }
                        return self.mcp_fail_call(operation, "read", job.proposal, code);
                    }
                };
                // An identical catalog writes nothing: the ledger revision (a CAS for the UI) stays put.
                if account.tools != catalog || !account.catalog {
                    let mut next = self.ledger.clone();
                    next.accounts[index].tools = catalog;
                    next.accounts[index].catalog = true;
                    if let Err(code) = self.commit(storage, next) {
                        return self.mcp_fail_call(operation, "read", job.proposal, code);
                    }
                }
                self.discovered.insert(id.clone());
                self.last_call = Some(LastCall {
                    operation,
                    outcome: "ok",
                    code: None,
                    retry_after: None,
                    proposal_id: job.proposal.clone(),
                    untrusted: None,
                });
                self.log("connection_call", operation, "read", "ok");
                job.proposal.map(|proposal| Settled {
                    proposal,
                    state: tools::State::Executed,
                    reason: None,
                    result: Some(json!({"tools": self.tool_count(&id)}).to_string()),
                })
            }
            McpWork::Call { tool, risk, .. } => {
                let operation = "mcp.call";
                if self.status_of(&id) != Some(Status::Connected) {
                    return self.mcp_fail_call(operation, risk, job.proposal, "not_connected");
                }
                match outcome {
                    Ok(McpDone::Output(text)) => {
                        let value = crate::mcp::wrap_output(&tool, &text);
                        self.last_call = Some(LastCall {
                            operation,
                            outcome: "ok",
                            code: None,
                            retry_after: None,
                            proposal_id: job.proposal.clone(),
                            untrusted: Some(true),
                        });
                        self.log("connection_call", operation, risk, "ok");
                        job.proposal.map(|proposal| Settled {
                            proposal,
                            state: tools::State::Executed,
                            reason: None,
                            result: Some(value.to_string()),
                        })
                    }
                    Ok(_) => self.mcp_fail_call(operation, risk, job.proposal, "mcp_protocol"),
                    Err(failure) => {
                        self.mcp_failed(storage, &id, failure.code);
                        self.mcp_fail_call(operation, risk, job.proposal, failure.code)
                    }
                }
            }
        }
    }

    fn tool_count(&self, id: &str) -> usize {
        self.account(id).map_or(0, |a| a.tools.len())
    }

    /// Token account probe answered. Success stores the token in the vault and connects with the consented
    /// scopes; the instance name becomes `account_ref`. A 401 is `reauth_required` and stores nothing. The
    /// token never reaches the ledger, the snapshot, the audit or the log.
    fn settle_probe(
        &mut self,
        storage: &Storage,
        vault: &mut LlmState,
        id: &str,
        token: String,
        outcome: Result<String, Failure>,
    ) {
        if self.status_of(id) != Some(Status::Connecting) {
            return;
        }
        let granted = self.token_wait.remove(id).unwrap_or_default();
        match outcome {
            Ok(name) => {
                if self
                    .account(id)
                    .and_then(|a| a.account_ref.as_deref())
                    .is_some_and(|known| known != name)
                {
                    let _ = self.set_status(storage, id, Status::Error, Some("account_mismatch"));
                    return;
                }
                if granted.is_empty() {
                    let _ = self.set_status(storage, id, Status::Error, Some("scope_not_granted"));
                    return;
                }
                if vault
                    .set_connection_tokens(storage, id, Some(token), None)
                    .is_err()
                {
                    let _ =
                        self.set_status(storage, id, Status::Error, Some("secrets_storage_error"));
                    return;
                }
                let Some(index) = self.index(id) else {
                    return;
                };
                let mut next = self.ledger.clone();
                {
                    let account = &mut next.accounts[index];
                    account.status = Status::Connected;
                    account.account_ref = Some(name);
                    account.granted_scopes = granted;
                    account.granted_at_ms = Some(crate::protocol::unix_ms());
                    account.last_ok = Some(unix_now());
                }
                if self.commit(storage, next).is_ok() {
                    self.errors.remove(id);
                    self.log("connection_consented", "none", "none", "ok");
                    self.log("connection_connected", "none", "none", "ok");
                }
            }
            Err(failure) => {
                if failure.code == "unauthorized" {
                    let _ = self.set_status(
                        storage,
                        id,
                        Status::ReauthRequired,
                        Some("reauth_required"),
                    );
                    self.log("connection_expired", "none", "none", "reauth_required");
                } else {
                    let status = failure_status(failure.code);
                    let _ = self.set_status(storage, id, status, Some(failure.code));
                }
            }
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
            account.granted_at_ms = Some(crate::protocol::unix_ms());
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
        outcome: Result<Refreshed, Failure>,
    ) -> Option<Settled> {
        // The account was disconnected or removed while the refresh ran: nothing is stored or resurrected.
        if !self
            .account(id)
            .is_some_and(|a| a.status != Status::Disconnected)
        {
            return then.and_then(|call| self.fail_proposal(call, "not_connected"));
        }
        match outcome {
            Ok(Refreshed {
                access,
                rotated,
                account: name,
                scope,
            }) => {
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
                let granted = self
                    .account(id)
                    .map(|a| a.granted_scopes.clone())
                    .unwrap_or_default();
                let still: Vec<String> = match &scope {
                    Some(offered) => granted
                        .iter()
                        .filter(|s| offered.contains(s))
                        .cloned()
                        .collect(),
                    None => granted.clone(),
                };
                if still.len() < granted.len() {
                    return self.scope_lost(storage, id, still, then);
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

    /// The provider stopped granting a scope the account held: the account needs the user again and keeps
    /// only the scopes still granted. The call that triggered the refresh fails with the code of its own
    /// scope (`reauth_required` while its scope is still granted, `scope_not_granted` once it is gone).
    fn scope_lost(
        &mut self,
        storage: &Storage,
        id: &str,
        still: Vec<String>,
        then: Option<Box<Call>>,
    ) -> Option<Settled> {
        if let Some(index) = self.index(id) {
            let mut next = self.ledger.clone();
            next.accounts[index].status = Status::ReauthRequired;
            next.accounts[index].granted_scopes = still.clone();
            if self.commit(storage, next).is_ok() {
                self.errors.insert(id.to_owned(), "reauth_required");
            }
        }
        self.log("connection_expired", "none", "none", "reauth_required");
        then.and_then(|call| {
            let code = if still.iter().any(|s| s == call.op.scope) {
                "reauth_required"
            } else {
                "scope_not_granted"
            };
            self.fail_proposal(call, code)
        })
    }

    fn fail_proposal(&mut self, call: Box<Call>, code: &'static str) -> Option<Settled> {
        self.last_call = Some(LastCall {
            operation: call.op.name,
            outcome: "failed",
            code: Some(code),
            retry_after: None,
            proposal_id: call.proposal.clone(),
            untrusted: None,
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
                    untrusted: None,
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
                    if let (Some(base), Some(_)) =
                        (base, vault.connection_token(&account, "refresh"))
                    {
                        self.push(Job::Refresh {
                            seen_access: vault.connection_token(&account, "access"),
                            account,
                            base,
                            refresh: None,
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
                    untrusted: None,
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
        let mcp = provider_by_id("mcp").unwrap();
        assert_eq!(mcp.scopes.len(), 3);
        let names: Vec<&str> = mcp.operations.iter().map(|o| o.name).collect();
        assert_eq!(names, ["mcp.discover", "mcp.call"]);
        assert!(mcp
            .operations
            .iter()
            .all(|o| mcp.scopes.iter().any(|s| s.id == o.scope)));
        let ha = provider_by_id("homeassistant").unwrap();
        assert_eq!(ha.scopes.len(), 3);
        assert_eq!(ha.operations.len(), 3);
        assert!(ha
            .operations
            .iter()
            .all(|o| ha.scopes.iter().any(|s| s.id == o.scope)));
        assert_eq!(
            operation(ha, "service.call").unwrap().risk,
            Access::Write,
            "the base risk; a dangerous service is destructive by `effective_risk`"
        );
        let google = provider_by_id("google").unwrap();
        assert_eq!(google.scopes.len(), 7);
        assert_eq!(google.operations.len(), 7);
        for op in google.operations {
            assert!(
                google.scopes.iter().any(|s| s.id == op.scope),
                "{}",
                op.name
            );
        }
        let risks: Vec<(&str, Access)> =
            google.operations.iter().map(|o| (o.name, o.risk)).collect();
        assert!(risks.contains(&("gmail.send", Access::Public)));
        assert!(risks.contains(&("gmail.messages.delete", Access::Destructive)));
        assert!(risks.contains(&("calendar.events.create", Access::Write)));
        assert!(risks.contains(&("gmail.messages.list", Access::Read)));
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
    fn google_lists_never_project_bodies_or_contents() {
        let google = provider_by_id("google").unwrap();
        let mail = operation(google, "gmail.messages.list").unwrap();
        let raw = json!([{"id": "m1", "from": "a@example.test", "subject": "Oi",
                          "body": "CORPO-SECRETO", "labels": ["x"]}]);
        assert_eq!(
            project(&raw, mail).unwrap(),
            json!([{"id": "m1", "from": "a@example.test", "subject": "Oi"}])
        );
        let files = operation(google, "drive.files.list").unwrap();
        let raw = json!([{"id": "f1", "name": "seed.txt", "content": "CONTEUDO-SECRETO"}]);
        assert_eq!(
            project(&raw, files).unwrap(),
            json!([{"id": "f1", "name": "seed.txt"}])
        );
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

    #[test]
    fn google_values_are_strict_and_bound_to_the_path() {
        let del = operation(provider_by_id("google").unwrap(), "gmail.messages.delete").unwrap();
        let shape = validate(del, &json!({"id": "m1"})).unwrap();
        assert_eq!(shape.path, "/api/gmail/messages/m1");
        assert_eq!(shape.body, None, "DELETE carries no body");
        let long = "x".repeat(65);
        for bad in ["../m1", "m1/x", "", "m 1", long.as_str()] {
            assert!(validate(del, &json!({ "id": bad })).is_err(), "{bad}");
        }
        let create =
            operation(provider_by_id("google").unwrap(), "calendar.events.create").unwrap();
        let ok = json!({"title": "Reunião", "start": "2026-10-20T09:00:00Z", "end": "2026-10-20T10:30:00-03:00"});
        assert!(validate(create, &ok).is_ok());
        for bad in [
            "2026-10-20 09:00:00",
            "2026-10-20T09:00Z",
            "2026-13-20T09:00:00Z",
            "2026-10-20T25:00:00Z",
            "2026-10-20T09:00:00",
            "2026-10-20T09:00:00.Z",
        ] {
            let args = json!({"title": "t", "start": bad, "end": "2026-10-20T10:00:00Z"});
            assert!(validate(create, &args).is_err(), "{bad}");
        }
        let send = operation(provider_by_id("google").unwrap(), "gmail.send").unwrap();
        assert!(validate(
            send,
            &json!({"to": "a@b.test", "subject": "s", "body": "b"})
        )
        .is_ok());
        for bad in [
            "sem-arroba",
            "a@b@c.test",
            "a b@c.test",
            "<a>@b.test",
            "@b.test",
        ] {
            let args = json!({"to": bad, "subject": "s", "body": "b"});
            assert!(validate(send, &args).is_err(), "{bad}");
        }
        let files = operation(provider_by_id("google").unwrap(), "drive.files.create").unwrap();
        assert!(validate(files, &json!({"name": "a.txt"})).is_ok());
        for bad in ["a/b", "a\\b", ".", "..", ""] {
            assert!(validate(files, &json!({ "name": bad })).is_err(), "{bad}");
        }
    }

    fn homeassistant() -> &'static Provider {
        provider_by_id("homeassistant").unwrap()
    }

    #[test]
    fn ha_states_project_entity_state_and_friendly_name_only() {
        let op = operation(homeassistant(), "states.list").unwrap();
        let raw = json!([{"entity_id": "light.kitchen", "state": "on",
                          "attributes": {"friendly_name": "Cozinha", "brightness": 128, "token": "x"},
                          "context": {"id": "c"}}]);
        assert_eq!(
            project(&raw, op).unwrap(),
            json!([{"entity_id": "light.kitchen", "state": "on", "attributes": {"friendly_name": "Cozinha"}}])
        );
        let bare = json!({"entity_id": "lock.front_door", "state": "locked", "attributes": {"brightness": 1}});
        let one = operation(homeassistant(), "state.get").unwrap();
        assert_eq!(
            project(&bare, one).unwrap(),
            json!({"entity_id": "lock.front_door", "state": "locked"})
        );
    }

    #[test]
    fn ha_paths_and_arguments_are_strict() {
        let get = operation(homeassistant(), "state.get").unwrap();
        let shape = validate(get, &json!({"entity_id": "light.kitchen"})).unwrap();
        assert_eq!(shape.path, "/api/states/light.kitchen");
        for bad in [
            "Light.kitchen",
            "light",
            "light.",
            "light.a/b",
            "../x.y",
            "light.x?y",
        ] {
            assert!(
                validate(get, &json!({ "entity_id": bad })).is_err(),
                "{bad}"
            );
        }
        let call = operation(homeassistant(), "service.call").unwrap();
        let shape = validate(
            call,
            &json!({"domain": "light", "service": "turn_on", "entity_id": "light.kitchen", "brightness": 255}),
        )
        .unwrap();
        assert_eq!(shape.path, "/api/services/light/turn_on");
        assert_eq!(
            shape.body,
            Some(json!({"entity_id": "light.kitchen", "brightness": 255}))
        );
        assert!(validate(
            call,
            &json!({"domain": "light", "service": "turn_on", "entity_id": "light.kitchen", "brightness": 256})
        )
        .is_err());
        assert!(validate(
            call,
            &json!({"domain": "light/x", "service": "turn_on", "entity_id": "light.kitchen"})
        )
        .is_err());
        assert!(validate(
            call,
            &json!({"domain": "light", "service": "turn_on", "code": "1"})
        )
        .is_err());
    }

    #[test]
    fn dangerous_services_are_destructive_and_need_their_scope() {
        let call = operation(homeassistant(), "service.call").unwrap();
        let risk = |domain: &str, service: &str| {
            let shape = validate(
                call,
                &json!({"domain": domain, "service": service, "entity_id": "x.y"}),
            )
            .unwrap();
            (
                Manager::default().effective_risk("conta", call, &shape),
                required_scopes(call, &shape),
            )
        };
        for (domain, service) in [
            ("lock", "unlock"),
            ("lock", "open"),
            ("cover", "open_cover"),
            ("cover", "close_cover"),
            ("alarm_control_panel", "alarm_disarm"),
            ("garage_door", "open"),
        ] {
            let (access, scopes) = risk(domain, service);
            assert_eq!(access, Access::Destructive, "{domain}.{service}");
            assert_eq!(scopes, vec!["services.call", "services.dangerous"]);
        }
        for (domain, service) in [
            ("light", "turn_on"),
            ("switch", "turn_off"),
            ("lock", "lock"),
        ] {
            let (access, scopes) = risk(domain, service);
            assert_eq!(access, Access::Write, "{domain}.{service}");
            assert_eq!(scopes, vec!["services.call"]);
        }
    }

    #[test]
    fn ha_tokens_are_16_to_256_printable_bytes_without_spaces() {
        assert!(ha_token_ok(&"a".repeat(16)));
        assert!(ha_token_ok(&"a".repeat(256)));
        assert!(!ha_token_ok(&"a".repeat(15)));
        assert!(!ha_token_ok(&"a".repeat(257)));
        assert!(!ha_token_ok("token com espaco 0123456789"));
        assert!(!ha_token_ok("token\ncom-controle-0123456"));
        assert!(!ha_token_ok("token-ação-0123456789abc"));
    }

    fn mcp_manager(scopes: &[&str]) -> Manager {
        let listed = json!({"tools": [
            {"name": "echo_note", "description": "Return the note.", "inputSchema": {
                "type": "object", "properties": {"text": {"type": "string", "maxLength": 32}},
                "required": ["text"], "additionalProperties": false}},
            {"name": "delete_note", "description": "Delete a note.",
             "annotations": {"destructiveHint": true}, "inputSchema": {
                "type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
            {"name": "nested", "description": "x", "inputSchema": {
                "type": "object", "properties": {"i": {"$ref": "#/d"}}}},
        ]});
        let mut tools = crate::mcp::build_catalog(&listed, &[], true).unwrap();
        tools.push(
            crate::mcp::build_catalog(
                &json!({"tools": [{"name": "late", "description": "new", "inputSchema":
                    {"type": "object"}}]}),
                &[],
                false,
            )
            .unwrap()
            .remove(0),
        );
        let mut manager = Manager::default();
        manager.ledger.accounts.push(Account {
            id: "conn_m".into(),
            provider: "mcp".into(),
            label: "m".into(),
            account_ref: Some("fake-mcp".into()),
            status: Status::Connected,
            granted_scopes: scopes.iter().map(|s| (*s).to_owned()).collect(),
            created: 0,
            last_ok: None,
            tools,
            catalog: true,
            granted_at_ms: None,
        });
        // The helper stands for a process that already discovered the tools (the normal path).
        manager.discovered.insert("conn_m".into());
        manager
    }

    #[test]
    fn mcp_calls_wait_for_a_discover_in_this_process() {
        let mcp = provider_by_id("mcp").unwrap();
        let call = operation(mcp, "mcp.call").unwrap();
        let args = json!({"tool": "echo_note", "args": {"text": "oi"}});
        let mut manager = mcp_manager(&["mcp.discover", "mcp.call"]);
        // The trust sits in the ledger, but this process has not listed the tools yet.
        manager.discovered.remove("conn_m");
        assert_eq!(
            manager.plan(mcp, call, Some("conn_m"), &args).err(),
            Some("tool_not_verified")
        );
        manager.discovered.insert("conn_m".into());
        assert!(manager.plan(mcp, call, Some("conn_m"), &args).is_ok());
    }

    #[test]
    fn abandoned_job_fails_its_carried_proposal_and_audits_it() {
        let github = github();
        let op = operation(github, "repo.get").unwrap();
        let shape = validate(op, &json!({"repo": "demo/private-repo"})).unwrap();
        let carried = Call {
            proposal: Some("prop_1".into()),
            account: "conn_x".into(),
            provider: github.id,
            op,
            shape,
            base: String::new(),
            token: String::new(),
            account_ref: None,
            idempotency: String::new(),
            retried: false,
        };
        let job = Job::Call(Box::new(carried));
        let mut manager = Manager {
            running: Some(9),
            holder: Some(holder_of(&job)),
            ..Manager::default()
        };
        manager.abandon(9);
        assert!(manager.running.is_none() && manager.holder.is_none());
        let settled = manager.take_settled();
        assert_eq!(settled.len(), 1);
        assert_eq!(settled[0].proposal, "prop_1");
        assert_eq!(settled[0].state, tools::State::Failed);
        assert_eq!(settled[0].reason, Some("provider_unreachable"));
        let audit = manager.take_audit();
        assert_eq!(audit.len(), 1);
        assert_eq!(audit[0].operation, "repo.get");
        assert_eq!(audit[0].outcome, "provider_unreachable");
    }

    #[test]
    fn revoke_scope_drops_one_scope_keeps_the_rest_and_gates_its_calls() {
        let root = std::env::temp_dir().join(format!("gideon-conn-scope-{}", random_hex(6)));
        let storage = Storage::open(&root).unwrap();
        let mut manager = Manager::default();
        manager.ledger.accounts.push(Account {
            id: "conn_s".into(),
            provider: "github".into(),
            label: "s".into(),
            account_ref: None,
            status: Status::Connected,
            granted_scopes: vec!["repo:read".into(), "issues:write".into()],
            created: 0,
            last_ok: None,
            tools: Vec::new(),
            catalog: false,
            granted_at_ms: Some(42),
        });
        storage.save_connections_ledger(&manager.ledger).unwrap();
        assert_eq!(
            manager.revoke_scope(&storage, "conn_s", "not_a_scope", None),
            "scope_not_requested"
        );
        assert_eq!(
            manager.revoke_scope(&storage, "conn_s", "repo:read", Some(7)),
            "stale_connection_revision"
        );
        assert_eq!(
            manager.revoke_scope(&storage, "missing", "repo:read", None),
            "unknown_connection"
        );
        assert_eq!(
            manager.revoke_scope(&storage, "conn_s", "repo:read", None),
            "ok"
        );
        let account = manager.ledger.accounts[0].clone();
        assert_eq!(account.granted_scopes, vec!["issues:write".to_owned()]);
        assert_eq!(account.granted_at_ms, Some(42));
        assert_eq!(account.status, Status::Connected);
        assert_eq!(
            account_gate(&account, "repo:read"),
            Err("scope_not_granted")
        );
        assert_eq!(account_gate(&account, "issues:write"), Ok(()));
        assert_eq!(
            manager.revoke_scope(&storage, "conn_s", "repo:read", None),
            "scope_not_granted"
        );
        assert!(manager
            .events
            .iter()
            .any(|e| e.0 == "connection_scope_revoked"));
        assert_eq!(manager.view().items[0].granted_at_ms, Some(42));
        // Ledgers written before granted_at_ms existed load with no date.
        let mut json = serde_json::to_value(&account).unwrap();
        assert_eq!(json["granted_at_ms"], 42);
        json.as_object_mut().unwrap().remove("granted_at_ms");
        let older: Account = serde_json::from_value(json).unwrap();
        assert_eq!(older.granted_at_ms, None);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn refresh_reads_its_token_at_start_and_skips_when_the_tokens_rotated() {
        let root = std::env::temp_dir().join(format!("gideon-conn-refresh-{}", random_hex(6)));
        let storage = Storage::open(&root).unwrap();
        let mut manager = Manager::default();
        manager.ledger.accounts.push(Account {
            id: "conn_r".into(),
            provider: "github".into(),
            label: "r".into(),
            account_ref: None,
            status: Status::Connected,
            granted_scopes: vec!["repo:read".into()],
            created: 0,
            last_ok: None,
            tools: Vec::new(),
            catalog: false,
            granted_at_ms: None,
        });
        storage.save_connections_ledger(&manager.ledger).unwrap();
        let mut vault = LlmState::load(&storage, false);
        vault
            .set_connection_tokens(
                &storage,
                "conn_r",
                Some("access-token-0000000000".into()),
                Some("refresh-token-000000000".into()),
            )
            .unwrap();
        let refresh = |seen: &str| Job::Refresh {
            account: "conn_r".into(),
            base: String::new(),
            refresh: None,
            seen_access: Some(seen.into()),
            then: None,
        };
        // Queued with A0; another job rotates the tokens before this one starts: no network job.
        manager
            .queue
            .push_back((1, refresh("access-token-0000000000")));
        vault
            .set_connection_tokens(
                &storage,
                "conn_r",
                Some("access-token-1111111111".into()),
                Some("refresh-token-111111111".into()),
            )
            .unwrap();
        assert!(manager.take_job(&vault).is_none());
        // Still the same access token: the job runs with the refresh token stored now (R1, not R0).
        manager
            .queue
            .push_back((2, refresh("access-token-1111111111")));
        let (id, job) = manager.take_job(&vault).unwrap();
        assert_eq!(id, 2);
        match job {
            Job::Refresh { refresh, .. } => {
                assert_eq!(refresh.as_deref(), Some("refresh-token-111111111"))
            }
            other => panic!("expected a refresh, got {other:?}"),
        }
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn a_skill_discover_never_trusts_a_first_catalog() {
        let root = std::env::temp_dir().join(format!("gideon-conn-skilldisc-{}", random_hex(6)));
        let storage = Storage::open(&root).unwrap();
        let listed = json!({"tools": [{"name": "echo_note", "description": "Return the note.",
            "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}},
            "required": ["text"], "additionalProperties": false}}]});
        for (from_skill, expected) in [
            (true, crate::mcp::ToolState::NeedsReapproval),
            (false, crate::mcp::ToolState::Trusted),
        ] {
            let mut manager = Manager::default();
            manager.ledger.accounts.push(Account {
                id: "conn_m".into(),
                provider: "mcp".into(),
                label: "m".into(),
                account_ref: Some("fake-mcp".into()),
                status: Status::Connected,
                granted_scopes: vec!["mcp.discover".into()],
                created: 0,
                last_ok: None,
                tools: Vec::new(),
                catalog: false,
                granted_at_ms: None,
            });
            storage.save_connections_ledger(&manager.ledger).unwrap();
            let mut vault = LlmState::load(&storage, false);
            manager.running = Some(7);
            let job = McpJob {
                account: "conn_m".into(),
                proposal: None,
                script: PathBuf::new(),
                profile: "good".into(),
                work: McpWork::Discover { from_skill },
            };
            let done = Done {
                id: 7,
                reply: Reply::Mcp {
                    job: Box::new(job),
                    outcome: Ok(McpDone::Listed(listed.clone())),
                },
            };
            manager.settle(&storage, &mut vault, done, Instant::now());
            let tools = &manager.ledger.accounts[0].tools;
            assert_eq!(tools.len(), 1, "from_skill={from_skill}");
            assert_eq!(tools[0].state, expected, "from_skill={from_skill}");
        }
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn mcp_calls_are_gated_by_tool_state_arguments_and_destructive_scope() {
        let mcp = provider_by_id("mcp").unwrap();
        let call = operation(mcp, "mcp.call").unwrap();
        let manager = mcp_manager(&["mcp.discover", "mcp.call"]);
        let plan = |tool: &str, args: Value| {
            manager.plan(
                mcp,
                call,
                Some("conn_m"),
                &json!({"tool": tool, "args": args}),
            )
        };
        let ok = plan("echo_note", json!({"text": "oi"})).unwrap();
        assert_eq!(ok.risk, Access::Write);
        assert_eq!(plan("echo_note", json!({})).err(), Some("invalid_args"));
        assert_eq!(
            plan("echo_note", json!({"text": "x".repeat(33)})).err(),
            Some("invalid_args")
        );
        assert_eq!(plan("nope", json!({})).err(), Some("unknown_tool"));
        assert_eq!(plan("nested", json!({})).err(), Some("tool_rejected"));
        assert_eq!(plan("late", json!({})).err(), Some("tool_not_trusted"));
        assert_eq!(
            plan("delete_note", json!({"id": "n1"})).err(),
            Some("scope_not_granted"),
            "a destructive tool needs the destructive scope"
        );
        let both = mcp_manager(&["mcp.discover", "mcp.call", "mcp.call_destructive"]);
        let destructive = both
            .plan(
                mcp,
                call,
                None,
                &json!({"tool": "delete_note", "args": {"id": "n1"}}),
            )
            .unwrap();
        assert_eq!(destructive.risk, Access::Destructive);
        assert_eq!(destructive.tool_risk(), tools::Risk::Destructive);
        // Arguments the schema does not know, or nested values, never reach the server.
        for bad in [
            json!({"tool": "echo_note", "args": {"text": "a", "x": 1}}),
            json!({"tool": "echo_note", "args": {"text": {"a": 1}}}),
            json!({"tool": "echo_note", "args": [1]}),
            json!({"tool": "echo/note", "args": {}}),
        ] {
            assert!(
                manager.plan(mcp, call, Some("conn_m"), &bad).is_err(),
                "{bad}"
            );
        }
        assert!(both.dependency_ready("mcp", "mcp.call"));
        assert!(!mcp_manager(&["mcp.discover"]).dependency_ready("mcp", "mcp.call"));
    }

    #[test]
    fn mcp_call_forms_names_and_flat_model_arguments() {
        let (provider, op) = parse_call("conn:mcp.call").unwrap();
        assert_eq!((provider.id, op.name), ("mcp", "mcp.call"));
        assert_eq!(
            parse_call("conn:mcp.discover").unwrap().1.name,
            "mcp.discover"
        );
        assert!(parse_call("conn:mcp.delete").is_none());
        assert!(parse_call("conn:mcp.mcp.call").is_none());
        assert_eq!(call_name(provider, op), "conn:mcp.call");
        let github = github();
        assert_eq!(
            call_name(github, operation(github, "repos.list").unwrap()),
            "conn:github.repos.list"
        );
        let nested = mcp_nest(&json!({"tool": "echo_note", "text": "oi", "n": 2})).unwrap();
        assert_eq!(
            nested,
            json!({"tool": "echo_note", "args": {"text": "oi", "n": 2}})
        );
        assert_eq!(
            mcp_nest(&json!({"text": "oi"})),
            Err("invalid_args"),
            "a call without a tool name is refused"
        );
        assert_eq!(mcp_nest(&json!(["x"])), Err("invalid_args"));
    }

    #[test]
    fn every_scope_label_fits_the_ui_limit_of_64_bytes() {
        for provider in PROVIDERS.iter() {
            for scope in provider.scopes {
                assert!(
                    (1..=LABEL_MAX).contains(&scope.label.len()),
                    "{}.{} label is {} bytes",
                    provider.id,
                    scope.id,
                    scope.label.len()
                );
            }
        }
    }

    #[test]
    fn mcp_agent_tool_and_fake_registration_are_strict() {
        assert!(agent_tool("mcp_call").is_some() == mcp_profile().is_some());
        assert_eq!(parse_fake_mcp("good").as_deref(), Ok("good"));
        assert_eq!(parse_fake_mcp("evil").as_deref(), Ok("evil"));
        assert_eq!(
            parse_fake_mcp("changed_tools").as_deref(),
            Ok("changed_tools")
        );
        for bad in ["", "Good", "good ", "sh -c id", "../mcp_server.py", "ultra"] {
            assert!(parse_fake_mcp(bad).is_err(), "{bad:?}");
        }
        // The prompt line names no tool and carries no server text.
        assert!(!agent_prompt().contains("IGNORE"));
    }

    #[test]
    fn ha_agent_tools_are_fixed_and_listed_only_with_a_fake() {
        assert!(agent_tool("ha_get_state").is_some() == fake_base("homeassistant").is_some());
        assert!(agent_tool("ha_call_service").is_some() == fake_base("homeassistant").is_some());
        assert_eq!(
            parse_call("conn:homeassistant.service.call")
                .unwrap()
                .1
                .risk,
            Access::Write
        );
        assert!(parse_call("conn:homeassistant.nope").is_none());
    }
}
