//! S5 E2.4 MCP. A Core-managed fake MCP server speaks JSON-RPC 2.0 over stdio inside the plugin
//! sandbox (bwrap: no network, `--unshare-all`, cleared environment, read-only root, capabilities
//! dropped, prlimit limits, size-capped tmpfs). The command is fixed by `--connections-fake-mcp`; it
//! is never taken from the UI, a skill or the service. Every tool schema is validated to a simple
//! subset before it is stored; tool output is text, bounded and wrapped as untrusted data.
use crate::{plugins, transport::bounded_frame};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, path::Path, sync::Mutex, time::Duration};
use tokio::{
    io::{AsyncWriteExt, BufReader},
    process::{Child, ChildStdin, ChildStdout},
    time::timeout_at,
};

pub const MAX_TOOLS: usize = 16;
/// Serialized size of one tool as the server lists it (name, description, schema, annotations).
pub const TOOL_MAX: usize = 2048;
pub const OUTPUT_MAX: usize = 2048;
pub const DESCRIPTION_MAX: usize = 256;
pub const ARGS_MAX: usize = 4096;
/// One protocol line, and so one whole response, is at most this long.
pub const LINE_MAX: usize = 64 * 1024;
pub const CALL_TIMEOUT: Duration = Duration::from_secs(8);
/// Starts of one account per Core lifetime (connect after a crash counts as a restart).
pub const START_LIMIT: u32 = 4;
const PROPERTIES_MAX: usize = 16;
const STRING_DEFAULT: u32 = 1024;
const STRING_CAP: u64 = 4096;
const SKIPPED_LINES: usize = 8;
pub const PROFILES: [&str; 3] = ["good", "evil", "changed_tools"];
/// Script of the fixed fake registration, relative to the Core home.
pub const FAKE_SCRIPT: &str = "tests/fixtures/connections/mcp_server.py";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ToolState {
    Trusted,
    NeedsReapproval,
    Rejected,
}

impl ToolState {
    pub fn name(self) -> &'static str {
        match self {
            ToolState::Trusted => "trusted",
            ToolState::NeedsReapproval => "needs_reapproval",
            ToolState::Rejected => "rejected",
        }
    }
}

/// One argument of a simple tool schema.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FieldRec {
    pub name: String,
    /// `string`, `integer`, `number` or `boolean`.
    pub kind: String,
    pub required: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_len: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub min: Option<i64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max: Option<i64>,
}

/// One discovered tool, as stored in the connection record.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ToolRec {
    pub name: String,
    /// SHA-256 of the whole tool as the server listed it (any change makes the tool new).
    pub sha256: String,
    /// Plain text for the user only; never part of a prompt.
    pub description: String,
    pub state: ToolState,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    /// Annotated destructive, or the name or description suggests delete, remove or drop.
    pub destructive: bool,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub fields: Vec<FieldRec>,
}

impl ToolRec {
    /// Whether the record is internally consistent (checked when the ledger is loaded).
    pub fn valid(&self) -> bool {
        name_ok(&self.name)
            && self.sha256.len() == 64
            && self.sha256.bytes().all(|b| b.is_ascii_hexdigit())
            && self.description.len() <= DESCRIPTION_MAX * 4
            && self.fields.len() <= PROPERTIES_MAX
            && self
                .fields
                .iter()
                .all(|f| name_ok(&f.name) && kind_ok(&f.kind))
    }
}

fn kind_ok(kind: &str) -> bool {
    matches!(kind, "string" | "integer" | "number" | "boolean")
}

/// Tool and field names: 1..=64 bytes of `[A-Za-z0-9_-]`.
pub fn name_ok(name: &str) -> bool {
    (1..=64).contains(&name.len())
        && name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
}

fn plain(text: &str, max: usize) -> String {
    let mut out = String::new();
    for c in text.chars() {
        let c = if c.is_control() { ' ' } else { c };
        if out.len() + c.len_utf8() > max {
            break;
        }
        out.push(c);
    }
    out.trim().to_owned()
}

/// Validates `inputSchema` against the simple subset: an object with scalar properties
/// (string, integer, number, boolean) and a `required` list. `$ref`, nested objects, arrays and
/// every unknown keyword refuse the whole tool.
fn simple_schema(schema: &Value) -> Option<Vec<FieldRec>> {
    let object = schema.as_object()?;
    const TOP: [&str; 6] = [
        "type",
        "properties",
        "required",
        "additionalProperties",
        "title",
        "description",
    ];
    if object.keys().any(|k| !TOP.contains(&k.as_str()))
        || object.get("type")?.as_str()? != "object"
    {
        return None;
    }
    if object
        .get("additionalProperties")
        .is_some_and(|v| !v.is_boolean())
    {
        return None;
    }
    let empty = Map::new();
    let properties = match object.get("properties") {
        None => &empty,
        Some(value) => value.as_object()?,
    };
    if properties.len() > PROPERTIES_MAX {
        return None;
    }
    let required: Vec<&str> = match object.get("required") {
        None => Vec::new(),
        Some(value) => value
            .as_array()?
            .iter()
            .map(Value::as_str)
            .collect::<Option<Vec<&str>>>()?,
    };
    if required.iter().any(|name| !properties.contains_key(*name)) {
        return None;
    }
    let mut fields = Vec::new();
    for (name, spec) in properties {
        let spec = spec.as_object()?;
        const KEYS: [&str; 5] = ["type", "description", "maxLength", "minimum", "maximum"];
        if !name_ok(name) || spec.keys().any(|k| !KEYS.contains(&k.as_str())) {
            return None;
        }
        let kind = spec.get("type")?.as_str()?;
        if !kind_ok(kind) {
            return None;
        }
        if spec.get("description").is_some_and(|d| !d.is_string()) {
            return None;
        }
        let max_len = match spec.get("maxLength") {
            None => (kind == "string").then_some(STRING_DEFAULT),
            Some(value) if kind == "string" => {
                Some(u32::try_from(value.as_u64().filter(|n| (1..=STRING_CAP).contains(n))?).ok()?)
            }
            Some(_) => return None,
        };
        let bound = |key: &str| -> Option<Option<i64>> {
            match spec.get(key) {
                None => Some(None),
                Some(value) if matches!(kind, "integer" | "number") => value.as_i64().map(Some),
                Some(_) => None,
            }
        };
        fields.push(FieldRec {
            name: name.clone(),
            kind: kind.to_owned(),
            required: required.contains(&name.as_str()),
            max_len,
            min: bound("minimum")?,
            max: bound("maximum")?,
        });
    }
    Some(fields)
}

fn suggests_destructive(raw: &Map<String, Value>) -> bool {
    let hint = raw
        .get("annotations")
        .and_then(|a| a.get("destructiveHint"))
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let text = format!(
        "{} {}",
        raw.get("name").and_then(Value::as_str).unwrap_or(""),
        raw.get("description").and_then(Value::as_str).unwrap_or("")
    )
    .to_lowercase();
    // Word stems, matched at the start of each word: "remove", "removed" and "removal" all count, while
    // "information" does not count as "format". Tools with no annotation and no such word stay write.
    hint || text
        .split(|c: char| !c.is_alphanumeric())
        .any(|word| DESTRUCTIVE_STEMS.iter().any(|stem| word.starts_with(stem)))
}

const DESTRUCTIVE_STEMS: [&str; 13] = [
    "delet", "remov", "drop", "purg", "wip", "eras", "truncat", "destroy", "kill", "format",
    "reset", "revok", "unlock",
];

fn digest(raw: &Value) -> String {
    // serde_json maps are ordered, so the text is canonical for equal content.
    let mut hasher = Sha256::new();
    hasher.update(raw.to_string().as_bytes());
    format!("{:x}", hasher.finalize())
}

/// Builds the stored catalog from a `tools/list` result. `first` is true while no catalog was ever
/// accepted for the account: those tools start trusted (the user chose to discover them). Later, a
/// changed or new tool is `needs_reapproval` and cannot be called until the user trusts it.
pub fn build_catalog(
    result: &Value,
    previous: &[ToolRec],
    first: bool,
) -> Result<Vec<ToolRec>, &'static str> {
    let list = result
        .get("tools")
        .and_then(Value::as_array)
        .ok_or("mcp_protocol")?;
    if list.len() > MAX_TOOLS {
        return Err("mcp_too_many_tools");
    }
    let mut catalog: Vec<ToolRec> = Vec::new();
    for (index, raw) in list.iter().enumerate() {
        let object = raw.as_object().ok_or("mcp_protocol")?;
        let listed = object.get("name").and_then(Value::as_str).unwrap_or("");
        let named = name_ok(listed) && !catalog.iter().any(|t| t.name == listed);
        let name = if named {
            listed.to_owned()
        } else {
            format!("rejected_{index}")
        };
        let description = plain(
            object
                .get("description")
                .and_then(Value::as_str)
                .unwrap_or(""),
            DESCRIPTION_MAX,
        );
        let sha256 = digest(raw);
        let verdict: Result<Vec<FieldRec>, &'static str> = if !named {
            Err("bad_name")
        } else if raw.to_string().len() > TOOL_MAX {
            Err("tool_too_large")
        } else {
            object
                .get("inputSchema")
                .and_then(simple_schema)
                .ok_or("schema_not_simple")
        };
        let mut record = ToolRec {
            name,
            sha256,
            description,
            state: ToolState::Rejected,
            reason: None,
            destructive: suggests_destructive(object),
            fields: Vec::new(),
        };
        match verdict {
            Err(reason) => record.reason = Some(reason.to_owned()),
            Ok(fields) => {
                record.fields = fields;
                let unchanged = previous
                    .iter()
                    .find(|t| t.name == record.name && t.sha256 == record.sha256);
                record.state = match unchanged {
                    Some(old) if old.state != ToolState::Rejected => old.state,
                    _ if first => ToolState::Trusted,
                    _ => ToolState::NeedsReapproval,
                };
            }
        }
        catalog.push(record);
    }
    Ok(catalog)
}

fn text_arg_ok(text: &str, max: u32) -> bool {
    text.len() <= max as usize
        && text
            .chars()
            .all(|c| !c.is_control() || c == '\n' || c == '\t')
}

/// Arguments against the stored schema: exact keys, required present, simple types and bounds.
pub fn check_args(tool: &ToolRec, args: &Map<String, Value>) -> Result<(), &'static str> {
    if serde_json::to_vec(args).map_or(true, |b| b.len() > ARGS_MAX) {
        return Err("invalid_args");
    }
    if args
        .keys()
        .any(|k| !tool.fields.iter().any(|f| &f.name == k))
    {
        return Err("invalid_args");
    }
    for field in &tool.fields {
        let Some(value) = args.get(&field.name) else {
            if field.required {
                return Err("invalid_args");
            }
            continue;
        };
        let ok = match field.kind.as_str() {
            "string" => value
                .as_str()
                .is_some_and(|s| text_arg_ok(s, field.max_len.unwrap_or(STRING_DEFAULT))),
            "integer" => value.as_i64().is_some_and(|n| in_bounds(n, field)),
            "number" => value.as_f64().is_some_and(|n| {
                n.is_finite()
                    && field.min.is_none_or(|m| n >= m as f64)
                    && field.max.is_none_or(|m| n <= m as f64)
            }),
            "boolean" => value.is_boolean(),
            _ => false,
        };
        if !ok {
            return Err("invalid_args");
        }
    }
    Ok(())
}

fn in_bounds(n: i64, field: &FieldRec) -> bool {
    field.min.is_none_or(|m| n >= m) && field.max.is_none_or(|m| n <= m)
}

/// Text content of a `tools/call` result, projected: only `type: text` items, control characters
/// removed, at most `OUTPUT_MAX` bytes.
pub fn project_output(result: &Value) -> Result<String, &'static str> {
    if result.get("isError").and_then(Value::as_bool) == Some(true) {
        return Err("mcp_tool_error");
    }
    let items = result
        .get("content")
        .and_then(Value::as_array)
        .ok_or("mcp_protocol")?;
    let joined = items
        .iter()
        .filter(|item| item.get("type").and_then(Value::as_str) == Some("text"))
        .filter_map(|item| item.get("text").and_then(Value::as_str))
        .collect::<Vec<&str>>()
        .join("\n");
    let mut out = String::new();
    for c in joined.chars() {
        let c = if c.is_control() && c != '\n' && c != '\t' {
            ' '
        } else {
            c
        };
        if out.len() + c.len_utf8() > OUTPUT_MAX {
            break;
        }
        out.push(c);
    }
    Ok(out)
}

/// The data the Core hands out for a finished call: always marked untrusted, always prefixed.
pub fn wrap_output(tool: &str, text: &str) -> Value {
    json!({
        "untrusted": true,
        "tool": tool,
        "output": format!("[mcp_output:{tool}] {text}"),
    })
}

struct Proc {
    /// Held so the process dies (kill_on_drop) when the account stops.
    #[allow(dead_code)]
    child: Child,
    stdin: ChildStdin,
    out: BufReader<ChildStdout>,
    next_id: u64,
}

struct Entry {
    pid: u32,
    /// `None` while a job holds the process.
    proc: Option<Proc>,
}

static PROCS: Mutex<BTreeMap<String, Entry>> = Mutex::new(BTreeMap::new());

fn procs() -> std::sync::MutexGuard<'static, BTreeMap<String, Entry>> {
    PROCS.lock().unwrap_or_else(|e| e.into_inner())
}

fn kill_pid(pid: u32) {
    if let Ok(pid) = i32::try_from(pid) {
        // SAFETY: plain signal to a pid this module spawned; no memory is touched.
        unsafe {
            libc::kill(pid, libc::SIGKILL);
        }
    }
}

/// Kills the account's server (disconnect, revoke, remove, crash). Safe when none is running; a
/// job still holding the process finds the entry gone and drops (kills) it.
pub fn stop(account: &str) {
    let entry = procs().remove(account);
    if let Some(entry) = entry {
        kill_pid(entry.pid);
    }
}

/// Core shutdown: every server dies with the Core.
pub fn stop_all() {
    let all = std::mem::take(&mut *procs());
    for entry in all.into_values() {
        kill_pid(entry.pid);
    }
}

pub fn running(account: &str) -> bool {
    procs().contains_key(account)
}

pub fn pid_of(account: &str) -> Option<u32> {
    procs().get(account).map(|e| e.pid)
}

fn give_back(account: &str, pid: u32, proc: Proc) {
    let mut map = procs();
    match map.get_mut(account) {
        Some(entry) if entry.pid == pid => entry.proc = Some(proc),
        // Stopped meanwhile: dropping the process kills it (kill_on_drop).
        _ => {}
    }
}

enum Fail {
    /// The process is unusable and gets killed.
    Fatal(&'static str),
    /// A JSON-RPC error answer: the process is fine.
    Rpc,
}

async fn exchange(proc: &mut Proc, method: &str, params: Value) -> Result<Value, Fail> {
    let id = proc.next_id;
    proc.next_id += 1;
    let mut line = serde_json::to_vec(&json!({
        "jsonrpc": "2.0", "id": id, "method": method, "params": params
    }))
    .map_err(|_| Fail::Fatal("mcp_protocol"))?;
    line.push(b'\n');
    let deadline = tokio::time::Instant::now() + CALL_TIMEOUT;
    let written = timeout_at(deadline, async {
        proc.stdin.write_all(&line).await?;
        proc.stdin.flush().await
    })
    .await;
    match written {
        Err(_) => return Err(Fail::Fatal("timeout")),
        Ok(Err(_)) => return Err(Fail::Fatal("mcp_crashed")),
        Ok(Ok(())) => {}
    }
    for _ in 0..SKIPPED_LINES {
        let frame = match timeout_at(deadline, bounded_frame(&mut proc.out, LINE_MAX)).await {
            Err(_) => return Err(Fail::Fatal("timeout")),
            Ok(Err(error)) if error.kind() == std::io::ErrorKind::InvalidData => {
                return Err(Fail::Fatal("mcp_too_large"))
            }
            Ok(Err(_)) | Ok(Ok(None)) => return Err(Fail::Fatal("mcp_crashed")),
            Ok(Ok(Some(bytes))) => bytes,
        };
        let Ok(Value::Object(message)) = serde_json::from_slice::<Value>(&frame) else {
            return Err(Fail::Fatal("mcp_protocol"));
        };
        // Server notifications carry no id and are ignored.
        let Some(seen) = message.get("id") else {
            continue;
        };
        if seen != &json!(id) {
            return Err(Fail::Fatal("mcp_protocol"));
        }
        if message.contains_key("error") {
            return Err(Fail::Rpc);
        }
        return message
            .get("result")
            .cloned()
            .ok_or(Fail::Fatal("mcp_protocol"));
    }
    Err(Fail::Fatal("mcp_protocol"))
}

/// Starts the sandboxed server and runs `initialize`. Returns the server name (`serverInfo.name`).
pub async fn start(
    account: &str,
    python: &Path,
    script: &Path,
    profile: &str,
) -> Result<String, &'static str> {
    if !PROFILES.contains(&profile) {
        return Err("mcp_start_failed");
    }
    stop(account);
    let mut spawned = None;
    for attempt in 0..2 {
        let budget = tokio::task::spawn_blocking(plugins::process_budget)
            .await
            .map_err(|_| "mcp_start_failed")?;
        let mut command =
            plugins::sandbox_command_with(python, script, budget, &["--profile", profile])
                .map_err(|_| "mcp_start_failed")?;
        match command.spawn() {
            Ok(child) => {
                spawned = Some(child);
                break;
            }
            Err(error) if attempt == 0 && error.raw_os_error() == Some(libc::EAGAIN) => continue,
            Err(_) => return Err("mcp_start_failed"),
        }
    }
    let mut child = spawned.ok_or("mcp_start_failed")?;
    let pid = child.id().ok_or("mcp_start_failed")?;
    let (Some(stdin), Some(stdout)) = (child.stdin.take(), child.stdout.take()) else {
        kill_pid(pid);
        return Err("mcp_start_failed");
    };
    procs().insert(account.to_owned(), Entry { pid, proc: None });
    let mut proc = Proc {
        child,
        stdin,
        out: BufReader::new(stdout),
        next_id: 1,
    };
    let params = json!({
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "gideon", "version": "1"},
    });
    let result = match exchange(&mut proc, "initialize", params).await {
        Ok(result) => result,
        Err(fail) => {
            stop(account);
            return Err(match fail {
                Fail::Fatal(code) => code,
                Fail::Rpc => "mcp_rpc_error",
            });
        }
    };
    let name = result
        .get("serverInfo")
        .and_then(|i| i.get("name"))
        .and_then(Value::as_str)
        .map(|n| plain(n, 64))
        .filter(|n| !n.is_empty());
    let Some(name) = name else {
        stop(account);
        return Err("mcp_protocol");
    };
    let note = b"{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}\n";
    let sent = timeout_at(tokio::time::Instant::now() + CALL_TIMEOUT, async {
        proc.stdin.write_all(note).await?;
        proc.stdin.flush().await
    })
    .await;
    if !matches!(sent, Ok(Ok(()))) {
        stop(account);
        return Err("mcp_crashed");
    }
    give_back(account, pid, proc);
    Ok(name)
}

/// One request on the running server. A fatal failure kills it; an RPC error leaves it running.
pub async fn request(account: &str, method: &str, params: Value) -> Result<Value, &'static str> {
    let taken = {
        let mut map = procs();
        map.get_mut(account)
            .and_then(|entry| entry.proc.take().map(|proc| (entry.pid, proc)))
    };
    let Some((pid, mut proc)) = taken else {
        return Err("mcp_not_running");
    };
    let outcome = exchange(&mut proc, method, params).await;
    match outcome {
        Ok(value) => {
            give_back(account, pid, proc);
            Ok(value)
        }
        Err(Fail::Rpc) => {
            give_back(account, pid, proc);
            Err("mcp_rpc_error")
        }
        Err(Fail::Fatal(code)) => {
            stop(account);
            drop(proc);
            Err(code)
        }
    }
}

/// Process-level failures: the server is gone or unusable, so the account goes to `error`.
pub fn fatal(code: &str) -> bool {
    matches!(
        code,
        "timeout" | "mcp_crashed" | "mcp_protocol" | "mcp_too_large" | "mcp_start_failed"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tool(name: &str, schema: Value) -> Value {
        json!({"name": name, "description": "d", "inputSchema": schema})
    }

    fn simple() -> Value {
        json!({"type": "object", "properties": {"text": {"type": "string", "maxLength": 64}},
               "required": ["text"], "additionalProperties": false})
    }

    #[test]
    fn simple_schemas_pass_and_complex_ones_are_refused() {
        let fields = simple_schema(&simple()).unwrap();
        assert_eq!(fields.len(), 1);
        assert!(fields[0].required);
        assert_eq!(fields[0].max_len, Some(64));
        let refused = [
            json!({"type": "object", "properties": {"i": {"$ref": "#/d"}}}),
            json!({"type": "object", "properties": {"o": {"type": "object"}}}),
            json!({"type": "object", "properties": {"a": {"type": "array"}}}),
            json!({"type": "object", "properties": {"s": {"type": "string", "enum": ["a"]}}}),
            json!({"type": "object", "required": ["missing"]}),
            json!({"type": "object", "$defs": {}}),
            json!({"type": "array"}),
            json!("x"),
        ];
        for schema in refused {
            assert!(simple_schema(&schema).is_none(), "{schema}");
        }
    }

    #[test]
    fn catalog_rejects_oversized_nested_and_badly_named_tools() {
        let big = json!({"type": "object", "properties": {"a": {"type": "string",
                         "description": "x".repeat(TOOL_MAX)}}});
        let list = json!({"tools": [
            tool("ok_tool", simple()),
            tool("big", big),
            tool("nested", json!({"type": "object", "properties": {"i": {"$ref": "#/x"}}})),
            tool("bad name", simple()),
        ]});
        let catalog = build_catalog(&list, &[], true).unwrap();
        let states: Vec<(&str, ToolState, Option<&str>)> = catalog
            .iter()
            .map(|t| (t.name.as_str(), t.state, t.reason.as_deref()))
            .collect();
        assert_eq!(
            states,
            vec![
                ("ok_tool", ToolState::Trusted, None),
                ("big", ToolState::Rejected, Some("tool_too_large")),
                ("nested", ToolState::Rejected, Some("schema_not_simple")),
                ("rejected_3", ToolState::Rejected, Some("bad_name")),
            ]
        );
        let many =
            json!({"tools": (0..17).map(|i| tool(&format!("t{i}"), simple())).collect::<Vec<_>>()});
        assert_eq!(build_catalog(&many, &[], true), Err("mcp_too_many_tools"));
    }

    #[test]
    fn changed_and_new_tools_need_reapproval_unchanged_ones_keep_their_state() {
        let first = build_catalog(
            &json!({"tools": [tool("a", simple()), tool("b", simple())]}),
            &[],
            true,
        )
        .unwrap();
        assert!(first.iter().all(|t| t.state == ToolState::Trusted));
        let mut changed = tool("b", simple());
        changed["description"] = json!("new words");
        let next = build_catalog(
            &json!({"tools": [tool("a", simple()), changed, tool("c", simple())]}),
            &first,
            false,
        )
        .unwrap();
        let states: Vec<ToolState> = next.iter().map(|t| t.state).collect();
        assert_eq!(
            states,
            vec![
                ToolState::Trusted,
                ToolState::NeedsReapproval,
                ToolState::NeedsReapproval
            ]
        );
    }

    #[test]
    fn destructive_hint_name_and_description_are_detected() {
        let hint = json!({"name": "x", "annotations": {"destructiveHint": true}});
        let name = json!({"name": "delete_note"});
        let words = json!({"name": "x", "description": "Will Remove things"});
        let drop = json!({"name": "x", "description": "drop table"});
        let plain_tool = json!({"name": "echo_note", "description": "Return the note."});
        for raw in [&hint, &name, &words, &drop] {
            assert!(suggests_destructive(raw.as_object().unwrap()));
        }
        assert!(!suggests_destructive(plain_tool.as_object().unwrap()));
    }

    #[test]
    fn destructive_widened_words_count_but_plain_intent_stays_write() {
        for raw in [
            json!({"name": "wipe_inbox"}),
            json!({"name": "x", "description": "Purge the cache"}),
            json!({"name": "x", "description": "Erased every row"}),
            json!({"name": "truncate_log"}),
            json!({"name": "destroy_board"}),
            json!({"name": "kill_job"}),
            json!({"name": "format_disk"}),
            json!({"name": "reset_counter"}),
            json!({"name": "revoke_key"}),
            json!({"name": "unlock_door"}),
            json!({"name": "x", "description": "Removal of the note"}),
        ] {
            assert!(suggests_destructive(raw.as_object().unwrap()), "{raw}");
        }
        for raw in [
            json!({"name": "export_notes", "description": "Export as information JSON."}),
            json!({"name": "add_numbers", "description": "Add two numbers."}),
            json!({"name": "lock_door", "description": "Lock the door."}),
        ] {
            assert!(!suggests_destructive(raw.as_object().unwrap()), "{raw}");
        }
    }

    #[test]
    fn arguments_follow_the_stored_schema() {
        let catalog = build_catalog(
            &json!({"tools": [tool("add", json!({"type": "object", "properties": {
                "a": {"type": "integer", "minimum": 0, "maximum": 10},
                "t": {"type": "string", "maxLength": 3},
                "f": {"type": "boolean"}}, "required": ["a"]}))]}),
            &[],
            true,
        )
        .unwrap();
        let rec = &catalog[0];
        let ok = |v: Value| check_args(rec, v.as_object().unwrap());
        assert!(ok(json!({"a": 3})).is_ok());
        assert!(ok(json!({"a": 3, "t": "abc", "f": true})).is_ok());
        for bad in [
            json!({}),
            json!({"a": 11}),
            json!({"a": 1.5}),
            json!({"a": "3"}),
            json!({"a": 1, "t": "abcd"}),
            json!({"a": 1, "extra": 1}),
            json!({"a": 1, "f": "yes"}),
            json!({"a": 1, "t": {"x": 1}}),
        ] {
            assert_eq!(ok(bad.clone()), Err("invalid_args"), "{bad}");
        }
    }

    /// A throwaway local process standing in for a server (not the sandbox): `script` is its whole behavior.
    fn local_proc(script: &str) -> Proc {
        let mut child = tokio::process::Command::new("/usr/bin/python3")
            .args(["-I", "-c", script])
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::null())
            .kill_on_drop(true)
            .spawn()
            .unwrap();
        let stdin = child.stdin.take().unwrap();
        let out = BufReader::new(child.stdout.take().unwrap());
        Proc {
            child,
            stdin,
            out,
            next_id: 1,
        }
    }

    async fn outcome(script: &str) -> Result<Value, &'static str> {
        let mut proc = local_proc(script);
        match exchange(&mut proc, "ping", json!({})).await {
            Ok(value) => Ok(value),
            Err(Fail::Rpc) => Err("rpc"),
            Err(Fail::Fatal(code)) => Err(code),
        }
    }

    #[tokio::test]
    async fn protocol_lines_are_capped_and_misbehaving_servers_are_fatal() {
        let reply = "import sys,json\nline=sys.stdin.readline()\nreq=json.loads(line)\n";
        assert_eq!(
            outcome(&format!(
                "{reply}print(json.dumps({{'jsonrpc':'2.0','id':req['id'],'result':{{'ok':1}}}}))"
            ))
            .await,
            Ok(json!({"ok": 1}))
        );
        // One answer line over 64 KiB (the response cap) kills the server.
        assert_eq!(
            outcome(&format!(
                "{reply}sys.stdout.write('x'*70000+'\\n');sys.stdout.flush()"
            ))
            .await,
            Err("mcp_too_large")
        );
        // Closing without an answer is a crash; garbage and an answer for another id break the protocol.
        assert_eq!(
            outcome(&format!("{reply}sys.exit(3)")).await,
            Err("mcp_crashed")
        );
        assert_eq!(
            outcome(&format!("{reply}print('not json')")).await,
            Err("mcp_protocol")
        );
        assert_eq!(
            outcome(&format!(
                "{reply}print(json.dumps({{'jsonrpc':'2.0','id':99,'result':{{}}}}))"
            ))
            .await,
            Err("mcp_protocol")
        );
        // Notifications (no id) before the answer are skipped; an error answer keeps the server alive.
        assert_eq!(
            outcome(&format!(
                "{reply}print(json.dumps({{'jsonrpc':'2.0','method':'notifications/x'}}))\nprint(json.dumps({{'jsonrpc':'2.0','id':req['id'],'result':{{'n':1}}}}))"
            ))
            .await,
            Ok(json!({"n": 1}))
        );
        assert_eq!(
            outcome(&format!(
                "{reply}print(json.dumps({{'jsonrpc':'2.0','id':req['id'],'error':{{'code':-32602,'message':'m'}}}}))"
            ))
            .await,
            Err("rpc")
        );
        // More silent notifications than the skip budget is a protocol break, not a hang.
        assert_eq!(
            outcome(&format!(
                "{reply}for _ in range(20): print(json.dumps({{'jsonrpc':'2.0','method':'n'}}))"
            ))
            .await,
            Err("mcp_protocol")
        );
    }

    #[test]
    fn output_is_text_only_bounded_and_wrapped_as_untrusted_data() {
        let result = json!({"content": [
            {"type": "text", "text": "hello\u{7}"},
            {"type": "image", "data": "AAAA"},
            {"type": "text", "text": "x".repeat(OUTPUT_MAX * 2)},
        ], "isError": false});
        let text = project_output(&result).unwrap();
        assert!(text.len() <= OUTPUT_MAX);
        assert!(text.starts_with("hello \n"));
        let wrapped = wrap_output("echo_note", "hi");
        assert_eq!(wrapped["untrusted"], json!(true));
        assert_eq!(wrapped["output"], json!("[mcp_output:echo_note] hi"));
        assert_eq!(
            project_output(&json!({"content": [], "isError": true})),
            Err("mcp_tool_error")
        );
    }
}
