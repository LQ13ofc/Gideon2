//! C2 infrastructure against the real Core binary and the real bwrap broker: keyless `local` and
//! `ollama` providers, last-known-good ledger, authorised fallback routes and per-plugin settings.
//! Inline plugin and inline llama.cpp-like loopback server (stdlib Python); every test owns a
//! tempdir root and runs under one lock so process counts cannot interfere.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{BufRead, BufReader, Read, Write},
    net::TcpStream,
    os::unix::{fs::PermissionsExt, net::UnixStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

static SERIAL: Mutex<()> = Mutex::new(());
const PYTHON: &str = "/usr/bin/python3";

/// Inline plugin. `llm2.chat` makes one `llm.http` call (optional `target`), `llm2.chain` tries
/// the fallback only after a recoverable primary error, `llm2.raw` relays one host_call of any
/// service (`args` verbatim, or built for `settings.put` from `fill` / `nest`).
const PLUGIN: &str = r#"#!/usr/bin/env python3
import json, queue, sys, threading
PLUGIN_ID = "@PLUGIN_ID@"
HELLO = @HELLO@
Q = queue.Queue()
def _reader():
    for line in sys.stdin:
        Q.put(line)
    Q.put(None)
threading.Thread(target=_reader, daemon=True).start()
def send(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()
def next_msg():
    line = Q.get()
    return None if line is None else json.loads(line)
def host_request(hid, service, args):
    send({"op": "host_call", "id": hid, "service": service, "args": args})
    text = []
    while True:
        m = next_msg()
        if m is None:
            return "".join(text), {"error": "eof"}
        if m.get("op") != "host_reply" or m.get("id") != hid:
            continue
        if "chunk" in m:
            text.append(m["chunk"])
            continue
        return "".join(text), m
def sse_text(raw):
    out = []
    for line in raw.split("\n"):
        if line.startswith("data: ") and line[6:].strip() != "[DONE]":
            try:
                delta = json.loads(line[6:])["choices"][0]["delta"].get("content")
            except Exception:
                delta = None
            if isinstance(delta, str):
                out.append(delta)
    return "".join(out)
def llm_args(inp, target=None):
    args = {"path": "/chat/completions",
            "body": {"messages": [{"role": "user", "content": inp.get("text", "hi")}]},
            "stream": True}
    if target is not None:
        args["target"] = target
    return args
def send_output(rid, output):
    send({"v": 1, "id": rid, "ok": True, "output": output})
def invoke_chat(rid, msg, inp):
    args = llm_args(inp, inp["target"]) if "target" in inp else llm_args(inp)
    text, terminal = host_request(2, "llm.http", args)
    send_output(rid, {"text": sse_text(text), "terminal": terminal, "ctx": msg.get("ctx")})
RECOVERABLE_STATUS = (429, 500, 502, 503, 504)
def recoverable(terminal):
    if terminal is None or "error" not in terminal:
        return False
    if terminal["error"] == "http_error":
        return terminal.get("status") in RECOVERABLE_STATUS
    return terminal["error"] in ("network_unavailable", "timeout")
def invoke_chain(rid, msg, inp):
    text, primary = host_request(2, "llm.http", llm_args(inp, "primary"))
    output = {"text": sse_text(text), "terminal": primary, "attempted": False, "used_fallback": False,
              "ctx": msg.get("ctx")}
    if recoverable(primary):
        fb_text, fallback = host_request(3, "llm.http", llm_args(inp, "fallback"))
        output.update({"attempted": True, "primary": primary, "terminal": fallback,
                       "text": sse_text(fb_text), "used_fallback": bool(fallback and fallback.get("done"))})
    send_output(rid, output)
def build_args(inp):
    if "args" in inp:
        return inp["args"]
    if inp["service"] == "settings.put":
        if "fill" in inp:
            return {"data": {"blob": "a" * inp["fill"]}}
        if "nest" in inp:
            root = {}
            node = root
            for _ in range(inp["nest"] - 1):
                node["x"] = {}
                node = node["x"]
            return {"data": root}
        return {"data": {}}
    return {}
def invoke_raw(rid, inp):
    _, terminal = host_request(2, inp["service"], build_args(inp))
    send_output(rid, {"terminal": terminal})
def dispatch(msg):
    rid = msg["id"]
    cap = msg.get("capability", "")
    inp = msg.get("input") or {}
    kind = cap.split(".", 1)[1] if "." in cap else ""
    if kind == "chat":
        invoke_chat(rid, msg, inp)
    elif kind == "chain":
        invoke_chain(rid, msg, inp)
    elif kind == "raw":
        invoke_raw(rid, inp)
    else:
        send({"v": 1, "id": rid, "ok": False, "error": "unknown_capability"})
def main():
    while True:
        msg = next_msg()
        if msg is None:
            return 0
        op = msg.get("op")
        if op == "hello":
            send({"v": 1, "id": msg["id"], "ok": True, "plugin_id": PLUGIN_ID, "api": 1, "capabilities": HELLO})
        elif op == "invoke":
            dispatch(msg)
        elif op == "shutdown":
            return 0
if __name__ == "__main__":
    sys.exit(main())
"#;

/// Loopback llama.cpp-like fake (OpenAI-compatible SSE). The request `model` selects behaviour;
/// every request is recorded with its Authorization header (None when absent).
const SERVER: &str = r#"#!/usr/bin/env python3
import json, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
STATE = {"requests": []}
LOCK = threading.Lock()
def sse(text):
    return ("data: " + json.dumps({"choices": [{"delta": {"content": text}}]}) + "\n\n").encode()
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def reply_json(self, status, obj):
        raw = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        if self.path == "/__state":
            with LOCK:
                self.reply_json(200, json.loads(json.dumps(STATE)))
        elif self.path == "/health":
            self.reply_json(200, {"status": "ok"})
        else:
            self.reply_json(404, {})
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = {}
        model = str(body.get("model", ""))
        with LOCK:
            STATE["requests"].append({"path": self.path, "auth": self.headers.get("Authorization"),
                                      "model": model, "stream": body.get("stream")})
        if model in ("mode-401", "mode-429", "mode-500", "mode-503"):
            payload = b'{"error":"SECRET-PROVIDER-BODY"}'
            self.send_response(int(model.split("-")[1]))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        for piece in ["Hel", "lo ", "wor", "ld"]:
            self.wfile.write(sse(piece))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
class Server(ThreadingHTTPServer):
    daemon_threads = True
server = Server(("127.0.0.1", 0), Handler)
print("PORT %d" % server.server_address[1], flush=True)
server.serve_forever()
"#;

fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn target() -> String {
    format!("{}_{}", std::env::consts::OS, std::env::consts::ARCH)
}
fn expect_ok(response: &Value) -> &Value {
    assert_eq!(response["code"], "ok", "unexpected response: {response}");
    response
}
/// Fresh, unguessable test key; never written outside secrets.json.
fn fake_key(tag: &str) -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    format!("fake-{tag}-{:x}-{}", nanos, std::process::id())
}
fn contains(haystack: &[u8], needle: &str) -> bool {
    !needle.is_empty()
        && haystack
            .windows(needle.len())
            .any(|window| window == needle.as_bytes())
}
/// Every file under `dir`, recursively; symlinks are reported, never followed.
fn files_under(dir: &Path, out: &mut Vec<PathBuf>) {
    for entry in fs::read_dir(dir).unwrap().flatten() {
        let path = entry.path();
        let meta = fs::symlink_metadata(&path).unwrap();
        if meta.is_dir() {
            files_under(&path, out);
        } else {
            out.push(path);
        }
    }
}
/// Processes whose cmdline contains `needle`, excluding `skip`.
fn processes_with(needle: &str, skip: Option<u32>) -> Vec<u32> {
    let Ok(entries) = fs::read_dir("/proc") else {
        return vec![];
    };
    entries
        .flatten()
        .filter_map(|e| {
            let pid: u32 = e.file_name().to_str()?.parse().ok()?;
            let cmdline = fs::read(e.path().join("cmdline")).ok()?;
            let text = String::from_utf8_lossy(&cmdline);
            (Some(pid) != skip && text.contains(needle)).then_some(pid)
        })
        .collect()
}
fn wait_until(what: &str, check: impl Fn() -> bool) {
    let deadline = Instant::now() + Duration::from_secs(10);
    while Instant::now() < deadline {
        if check() {
            return;
        }
        thread::sleep(Duration::from_millis(30));
    }
    panic!("timed out waiting for {what}");
}
fn http_get(port: u16, path: &str) -> Value {
    let mut stream = TcpStream::connect(("127.0.0.1", port)).expect("connect fake server");
    stream
        .write_all(format!("GET {path} HTTP/1.0\r\nHost: test\r\n\r\n").as_bytes())
        .unwrap();
    let mut raw = String::new();
    stream.read_to_string(&mut raw).unwrap();
    let body = raw.split("\r\n\r\n").nth(1).unwrap_or("");
    serde_json::from_str(body).unwrap_or_else(|_| panic!("bad state body: {raw}"))
}
fn requests_seen(port: u16) -> Vec<Value> {
    http_get(port, "/__state")["requests"]
        .as_array()
        .unwrap()
        .clone()
}

/// Loopback llama.cpp-like fake; killed on drop.
struct Server {
    child: Child,
    port: u16,
}
impl Server {
    fn start(dir: &Path) -> Server {
        let script = dir.join("fake_llama_server.py");
        fs::write(&script, SERVER).unwrap();
        let mut child = Command::new(PYTHON)
            .arg("-I")
            .arg(&script)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .expect("spawn fake server");
        let mut line = String::new();
        BufReader::new(child.stdout.take().unwrap())
            .read_line(&mut line)
            .unwrap();
        let port = line
            .trim()
            .strip_prefix("PORT ")
            .and_then(|p| p.parse().ok())
            .expect("fake server port");
        Server { child, port }
    }
    fn requests(&self) -> usize {
        requests_seen(self.port).len()
    }
}
impl Drop for Server {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

/// One Core process bound to a private root; killed on drop. No `--net-allow-loopback`: the
/// local providers must work without the test-only flag.
struct Core {
    root: PathBuf,
    catalog: (PathBuf, String),
    child: Option<Child>,
    counter: u64,
    log: PathBuf,
    secret: Option<String>,
}
impl Core {
    fn new(dir: &Path, catalog: (PathBuf, String)) -> Core {
        Core {
            root: dir.join("core"),
            catalog,
            child: None,
            counter: 0,
            log: dir.join("core.log"),
            secret: None,
        }
    }
    fn start(&mut self) {
        let log = fs::File::create(&self.log).unwrap();
        let child = Command::new(env!("CARGO_BIN_EXE_gideon-base"))
            .arg("--root")
            .arg(&self.root)
            .arg("--hub-catalog")
            .arg(&self.catalog.0)
            .arg(&self.catalog.1)
            .arg("--plugin-python")
            .arg(PYTHON)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(log)
            .spawn()
            .expect("spawn Core");
        self.child = Some(child);
        let deadline = Instant::now() + Duration::from_secs(10);
        while Instant::now() < deadline {
            if self.root.join("core.sock").exists() && self.try_snapshot().is_some() {
                return;
            }
            thread::sleep(Duration::from_millis(20));
        }
        panic!(
            "Core did not start; log: {}",
            fs::read_to_string(&self.log).unwrap_or_default()
        );
    }
    fn try_snapshot(&mut self) -> Option<Value> {
        let response = self.call(json!({"op": "snapshot"}));
        (response["code"] == "ok").then_some(response)
    }
    fn call(&mut self, mut op: Value) -> Value {
        self.counter += 1;
        op["version"] = json!(1);
        op["request_id"] = json!(format!("t{}", self.counter));
        let mut stream = UnixStream::connect(self.root.join("core.sock")).expect("connect Core");
        stream
            .set_read_timeout(Some(Duration::from_secs(30)))
            .unwrap();
        let mut bytes = serde_json::to_vec(&op).unwrap();
        bytes.push(b'\n');
        stream.write_all(&bytes).unwrap();
        let mut line = String::new();
        BufReader::new(stream).read_line(&mut line).unwrap();
        // The key must never come back in any Core response, whatever the operation.
        if let Some(secret) = &self.secret {
            assert!(
                !line.contains(secret.as_str()),
                "key echoed in response: {line}"
            );
        }
        serde_json::from_str(&line).unwrap_or_else(|_| panic!("bad response: {line}"))
    }
    fn snap(&mut self) -> Value {
        self.call(json!({"op": "snapshot"}))
    }
    fn wait_for(&mut self, what: &str, check: impl Fn(&Value) -> bool) -> Value {
        let deadline = Instant::now() + Duration::from_secs(10);
        loop {
            let snap = self.snap();
            if check(&snap) {
                return snap;
            }
            assert!(
                Instant::now() < deadline,
                "timed out waiting for {what}: {snap}"
            );
            thread::sleep(Duration::from_millis(30));
        }
    }
    fn plugin_revision(&mut self) -> u64 {
        self.snap()["plugins"]["revision"].as_u64().unwrap()
    }
    fn llm_revision(&mut self) -> u64 {
        self.snap()["llm"]["revision"].as_u64().unwrap()
    }
    fn enable(&mut self, plugin_id: &str) -> Value {
        let revision = self.plugin_revision();
        self.call(json!({"op": "plugin_enable", "revision": revision, "plugin_id": plugin_id}))
    }
    fn disable(&mut self, plugin_id: &str) -> Value {
        let revision = self.plugin_revision();
        self.call(json!({"op": "plugin_disable", "revision": revision, "plugin_id": plugin_id}))
    }
    fn invoke(&mut self, capability: &str, input: Value, deadline_ms: u64) -> Value {
        self.call(json!({
            "op": "capability_invoke",
            "capability": capability,
            "input": input,
            "deadline_ms": deadline_ms,
        }))
    }
    /// `llm_configure` with the current CAS revision; `body` carries the other fields.
    fn configure(&mut self, mut body: Value) -> Value {
        let revision = self.llm_revision();
        body["op"] = json!("llm_configure");
        body["revision"] = json!(revision);
        self.call(body)
    }
    fn configure_local(&mut self, provider: &str, model: &str, port: u16) -> Value {
        self.configure(json!({
            "provider": provider, "model": model, "custom_url": null,
            "local_port": port, "cloud_consent": false,
        }))
    }
    fn set_secret(&mut self, provider: &str, key: &str) -> Value {
        self.secret = Some(key.to_owned());
        self.call(json!({"op": "secret_set", "provider": provider, "key": key}))
    }
    /// Installs `payload` through the real Hub path: approve, stage in chunks, finish, install.
    fn install(&mut self, plugin_id: &str, payload: &[u8]) {
        let snap = self.snap();
        let entry = entry_of(&snap, plugin_id);
        let manifest_sha = entry["manifest_sha256"].as_str().unwrap().to_owned();
        if entry["permissions_approved"] != true {
            let approval = snap["hub"]["approval_revision"].as_u64().unwrap();
            expect_ok(&self.call(json!({
                "op": "hub_approve",
                "revision": approval,
                "plugin_id": plugin_id,
                "manifest_sha256": manifest_sha,
                "permissions": entry["permissions"],
                "publisher_unverified_ack": true,
            })));
        }
        let approval = self.snap()["hub"]["approval_revision"].as_u64().unwrap();
        expect_ok(&self.call(json!({
            "op": "hub_begin",
            "revision": approval,
            "plugin_id": plugin_id,
            "manifest_sha256": manifest_sha,
        })));
        let import_id = self.snap()["hub"]["import"]["import_id"]
            .as_str()
            .unwrap()
            .to_owned();
        for (index, chunk) in payload.chunks(512).enumerate() {
            let hex = chunk.iter().fold(String::new(), |mut hex, b| {
                use std::fmt::Write;
                let _ = write!(hex, "{b:02x}");
                hex
            });
            expect_ok(&self.call(json!({
                "op": "hub_chunk",
                "import_id": import_id,
                "offset": index * 512,
                "hex": hex,
            })));
        }
        expect_ok(&self.call(json!({"op": "hub_finish", "import_id": import_id})));
        let install_revision = self.snap()["hub"]["install_revision"].as_u64().unwrap();
        expect_ok(&self.call(json!({
            "op": "hub_install",
            "revision": install_revision,
            "plugin_id": plugin_id,
            "manifest_sha256": manifest_sha,
        })));
    }
    fn stop(&mut self) {
        if let Some(mut child) = self.child.take() {
            // SAFETY: signalling a child process we spawned; the pid is still ours until wait.
            unsafe { libc::kill(child.id() as i32, libc::SIGTERM) };
            let deadline = Instant::now() + Duration::from_secs(10);
            while Instant::now() < deadline {
                if child.try_wait().ok().flatten().is_some() {
                    return;
                }
                thread::sleep(Duration::from_millis(20));
            }
            let _ = child.kill();
            let _ = child.wait();
            panic!("Core ignored SIGTERM");
        }
    }
    /// Every file of the private root except the vault and the Core log must hold no key bytes.
    fn assert_no_key_on_disk(&self) {
        let Some(secret) = self.secret.as_deref() else {
            return;
        };
        let mut files = vec![];
        files_under(&self.root, &mut files);
        for file in files {
            if file.file_name().is_some_and(|n| n == "secrets.json") {
                continue;
            }
            let bytes = fs::read(&file).unwrap_or_default();
            assert!(!contains(&bytes, secret), "key found in {}", file.display());
        }
        let log = fs::read(&self.log).unwrap_or_default();
        assert!(!contains(&log, secret), "key found in Core stderr log");
    }
    /// Every C2 file (LLM ledger and plugin settings) is 0600 and its directory 0700.
    fn assert_private_c2_files(&self) {
        let mut files = vec![];
        files_under(&self.root, &mut files);
        let mut checked = 0;
        for file in files {
            let name = file.file_name().unwrap().to_string_lossy().into_owned();
            let settings = file.parent().unwrap().ends_with("plugin-settings");
            if name == "llm-config.json" || settings {
                let mode = fs::metadata(&file).unwrap().permissions().mode() & 0o777;
                assert_eq!(mode, 0o600, "{}", file.display());
                assert!(fs::metadata(&file).unwrap().len() <= 16 * 1024);
                checked += 1;
            }
        }
        assert!(checked >= 1, "no C2 file was written");
        let dir = self.root.join("plugin-settings");
        if dir.exists() {
            let mode = fs::metadata(&dir).unwrap().permissions().mode() & 0o777;
            assert_eq!(mode, 0o700);
        }
    }
}
impl Drop for Core {
    fn drop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}
fn item_of(snap: &Value, plugin_id: &str) -> Value {
    snap["plugins"]["items"]
        .as_array()
        .unwrap()
        .iter()
        .find(|i| i["plugin_id"] == plugin_id)
        .cloned()
        .unwrap_or(Value::Null)
}
fn entry_of(snap: &Value, plugin_id: &str) -> Value {
    snap["hub"]["entries"]
        .as_array()
        .unwrap()
        .iter()
        .find(|e| e["plugin_id"] == plugin_id)
        .cloned()
        .unwrap_or_else(|| panic!("no catalog entry {plugin_id}"))
}

fn plugin_payload(id: &str, capabilities: &[&str]) -> Vec<u8> {
    PLUGIN
        .replace("@PLUGIN_ID@", id)
        .replace("@HELLO@", &serde_json::to_string(capabilities).unwrap())
        .into_bytes()
}
fn manifest(id: &str, permissions: &[&str], capabilities: &[&str], payload: &[u8]) -> Value {
    json!({
        "plugin_id": id,
        "api_version": 1,
        "publisher": "Gideon test fixture",
        "semver": "1.0.0",
        "targets": [target()],
        "binaries": [{
            "target": target(),
            "url": format!("https://github.com/acme/plugins/releases/download/v1/{id}.py"),
            "sha256": sha(payload),
            "size": payload.len(),
        }],
        "license": "MIT",
        "permissions": permissions,
        "dependencies": [],
        "conflicts": [],
        "entrypoint": format!("bin/{id}.py"),
        "build_source": "https://github.com/acme/plugins/tree/main",
        "support_policy": "test fixture",
        "signature": null,
        "runtime": "python3_script",
        "capabilities": capabilities,
    })
}

const LLM2_CAPS: [&str; 3] = ["llm2.chat", "llm2.chain", "llm2.raw"];
const NOSET_CAPS: [&str; 2] = ["nosettings.chat", "nosettings.raw"];

/// A Core with `llm2` (network_llm + storage_settings) and `nosettings` (network_llm only) running,
/// plus a loopback llama.cpp-like fake and a fresh random key.
struct Lab {
    _dir: tempfile::TempDir,
    core: Core,
    server: Server,
    key: String,
    llm2: Vec<u8>,
}
fn lab(name: &str) -> Lab {
    let dir = tempfile::tempdir().unwrap();
    let llm2 = plugin_payload("llm2", &LLM2_CAPS);
    let noset = plugin_payload("nosettings", &NOSET_CAPS);
    let catalog = json!({
        "version": 1,
        "repository": "https://github.com/acme/plugins",
        "plugins": [
            manifest("llm2", &["network_llm", "storage_settings"], &LLM2_CAPS, &llm2),
            manifest("nosettings", &["network_llm"], &NOSET_CAPS, &noset),
        ],
    });
    let bytes = serde_json::to_vec(&catalog).unwrap();
    let path = dir.path().join(format!("{name}.json"));
    fs::write(&path, &bytes).unwrap();
    let server = Server::start(dir.path());
    let mut core = Core::new(dir.path(), (path, sha(&bytes)));
    core.start();
    core.install("llm2", &llm2);
    core.install("nosettings", &noset);
    expect_ok(&core.enable("llm2"));
    expect_ok(&core.enable("nosettings"));
    core.wait_for("plugins running", |s| {
        item_of(s, "llm2")["state"] == "running" && item_of(s, "nosettings")["state"] == "running"
    });
    Lab {
        _dir: dir,
        core,
        server,
        key: fake_key(name),
        llm2,
    }
}
/// Waits for the invocation result and checks which capability produced it.
fn settled(core: &mut Core, capability: &str) -> Value {
    let snap = core.wait_for("capability result", |s| !s["capability_result"].is_null());
    assert_eq!(snap["capability_result"]["capability"], capability);
    snap["capability_result"].clone()
}
/// One `llm2.raw` relay: the host_call terminal reply, or the failure.
fn raw(core: &mut Core, service: &str, extra: Value) -> Value {
    let mut input = json!({"service": service});
    if let Value::Object(map) = extra {
        for (key, value) in map {
            input[key] = value;
        }
    }
    expect_ok(&core.invoke("llm2.raw", input.clone(), 8000));
    let result = settled(core, "llm2.raw");
    result["output"]["terminal"].clone()
}
fn brokers() -> Vec<u32> {
    processes_with("net_broker.py", None)
}
fn wait_no_brokers() {
    wait_until("broker processes gone", || brokers().is_empty());
}

#[test]
fn local_and_ollama_stream_without_key_consent_or_authorization_header() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("local");
    let port = lab.server.port;
    expect_ok(&lab.core.configure_local("local", "mode-sse", port));
    let snap = lab.core.snap();
    assert_eq!(snap["llm"]["config"]["local_port"], port);
    assert_eq!(snap["llm"]["config"]["cloud_consent"], false);
    assert_eq!(
        snap["llm"]["secrets"],
        json!({"openrouter": false, "opencode": false, "google": false, "anthropic": false, "custom": false})
    );
    expect_ok(&lab.core.invoke("llm2.chat", json!({"text": "hi"}), 8000));
    let first = settled(&mut lab.core, "llm2.chat");
    assert_eq!(first["output"]["text"], "Hello world", "{first}");
    assert_eq!(first["output"]["terminal"]["status"], 200, "{first}");
    assert_eq!(
        first["output"]["ctx"],
        json!({"llm": {"provider": "local", "model": "mode-sse"}})
    );
    expect_ok(&lab.core.configure_local("ollama", "mode-sse", port));
    expect_ok(&lab.core.invoke("llm2.chat", json!({"text": "hi"}), 8000));
    let second = settled(&mut lab.core, "llm2.chat");
    assert_eq!(second["output"]["text"], "Hello world", "{second}");
    assert_eq!(
        second["output"]["ctx"],
        json!({"llm": {"provider": "ollama", "model": "mode-sse"}})
    );
    let seen = requests_seen(port);
    assert_eq!(seen.len(), 2, "{seen:?}");
    for request in seen {
        assert!(
            request["auth"].is_null(),
            "keyless target sent a header: {request}"
        );
        assert_eq!(request["path"], "/v1/chat/completions");
    }
    wait_no_brokers();
    lab.core.assert_private_c2_files();
}

#[test]
fn local_routes_refuse_bad_ports_urls_names_and_keys() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("ports");
    let port = lab.server.port;
    let refused = [
        json!({"provider": "local", "model": "m", "local_port": 1023}),
        json!({"provider": "ollama", "model": "m", "local_port": 80}),
        json!({"provider": "local", "model": "m", "local_port": 0}),
        json!({"provider": "local", "model": "m"}),
        json!({"provider": "local", "model": "m", "custom_url": "http://127.0.0.1:8080/v1", "local_port": 8080}),
        json!({"provider": "ollama", "model": "m", "custom_url": "http://localhost:8080/v1", "local_port": 8080}),
        json!({"provider": "custom", "model": "m", "custom_url": format!("http://localhost:{port}/v1")}),
        json!({"provider": "custom", "model": "m", "custom_url": format!("http://127.0.0.1:{port}/v1")}),
        json!({"provider": "custom", "model": "m", "custom_url": "http://example.com/v1"}),
    ];
    for body in refused {
        let mut body = body;
        body["custom_url"] = body.get("custom_url").cloned().unwrap_or(Value::Null);
        body["cloud_consent"] = json!(false);
        let response = lab.core.configure(body.clone());
        assert_eq!(response["code"], "invalid_config", "{body}: {response}");
    }
    // A port above 65535 cannot even be parsed as a request.
    let revision = lab.core.llm_revision();
    let parse = lab.core.call(json!({
        "op": "llm_configure", "revision": revision, "provider": "local", "model": "m",
        "custom_url": null, "local_port": 70000, "cloud_consent": false,
    }));
    assert_eq!(parse["code"], "invalid_message", "{parse}");
    assert_eq!(
        lab.core.snap()["llm"]["revision"],
        0,
        "rejections must not advance the CAS"
    );
    // A cloud route ignores a port instead of storing it.
    expect_ok(&lab.core.configure(json!({
        "provider": "google", "model": "gemini-3.5-flash-lite", "custom_url": null,
        "local_port": 8080, "cloud_consent": false,
    })));
    let snap = lab.core.snap();
    assert!(snap["llm"]["config"].get("local_port").is_none(), "{snap}");
    // Local providers have no vault slot.
    let key = lab.key.clone();
    assert_eq!(
        lab.core.set_secret("local", &key)["code"],
        "invalid_provider"
    );
    assert_eq!(
        lab.core.set_secret("ollama", &key)["code"],
        "invalid_provider"
    );
    lab.core.assert_no_key_on_disk();
    assert_eq!(lab.server.requests(), 0);
}

#[test]
fn last_known_good_marks_rolls_back_and_survives_restart() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("lkg");
    let port = lab.server.port;
    assert_eq!(
        lab.core.call(json!({"op": "llm_mark_good", "revision": 0}))["code"],
        "no_config"
    );
    assert_eq!(
        lab.core.call(json!({"op": "llm_rollback", "revision": 0}))["code"],
        "no_lkg"
    );
    expect_ok(&lab.core.configure_local("local", "mode-sse", port));
    assert_eq!(
        lab.core.call(json!({"op": "llm_rollback", "revision": 1}))["code"],
        "no_lkg"
    );
    assert_eq!(
        lab.core.call(json!({"op": "llm_mark_good", "revision": 0}))["code"],
        "stale_llm_revision"
    );
    expect_ok(&lab.core.call(json!({"op": "llm_mark_good", "revision": 1})));
    let snap = lab.core.snap();
    assert_eq!(snap["llm"]["revision"], 2);
    assert_eq!(
        snap["llm"]["config"]["lkg"],
        json!({"provider": "local", "model": "mode-sse", "custom_url": null,
               "local_port": port, "cloud_consent": false})
    );
    expect_ok(&lab.core.configure_local("ollama", "mode-401", port));
    assert_eq!(
        lab.core.call(json!({"op": "llm_rollback", "revision": 0}))["code"],
        "stale_llm_revision"
    );
    expect_ok(&lab.core.call(json!({"op": "llm_rollback", "revision": 3})));
    let snap = lab.core.snap();
    assert_eq!(snap["llm"]["revision"], 4);
    assert_eq!(snap["llm"]["config"]["provider"], "local");
    assert_eq!(snap["llm"]["config"]["model"], "mode-sse");
    lab.core.stop();
    lab.core.start();
    let snap = lab
        .core
        .wait_for("restarted", |s| item_of(s, "llm2")["state"] == "running");
    assert_eq!(snap["llm"]["revision"], 4);
    assert_eq!(snap["llm"]["config"]["lkg"]["model"], "mode-sse");
    expect_ok(&lab.core.invoke("llm2.chat", json!({"text": "hi"}), 8000));
    let result = settled(&mut lab.core, "llm2.chat");
    assert_eq!(result["output"]["text"], "Hello world", "{result}");
    expect_ok(&lab.core.call(json!({"op": "llm_rollback", "revision": 4})));
    assert_eq!(lab.core.snap()["llm"]["revision"], 5);
    lab.core.assert_private_c2_files();
}

#[test]
fn fallback_config_is_validated_like_the_primary_route() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("fbconfig");
    let port = lab.server.port;
    let primary = json!({"provider": "local", "model": "mode-sse", "local_port": port,
                         "custom_url": null, "cloud_consent": false});
    let bad_fallbacks = [
        json!({"provider": "local", "model": "m", "local_port": 80}),
        json!({"provider": "local", "model": "m"}),
        json!({"provider": "nope", "model": "m"}),
        json!({"provider": "custom", "model": "m"}),
        json!({"provider": "google", "model": "bad model"}),
        json!({"provider": "ollama", "model": "m", "local_port": port, "custom_url": "http://example.com"}),
    ];
    for fallback in bad_fallbacks {
        let mut body = primary.clone();
        body["fallback"] = fallback.clone();
        let response = lab.core.configure(body);
        assert_eq!(response["code"], "invalid_config", "{fallback}: {response}");
    }
    // Unknown fields are a malformed request, not a configuration error.
    let mut unknown = primary.clone();
    unknown["fallback"] = json!({"provider": "google", "model": "m", "zzz": 1});
    assert_eq!(lab.core.configure(unknown)["code"], "invalid_message");
    assert_eq!(lab.core.snap()["llm"]["revision"], 0);
    let mut body = primary.clone();
    body["fallback"] = json!({"provider": "ollama", "model": "mode-sse", "local_port": port});
    expect_ok(&lab.core.configure(body));
    let snap = lab.core.snap();
    assert_eq!(
        snap["llm"]["config"]["fallback"],
        json!({"provider": "ollama", "model": "mode-sse", "custom_url": null, "local_port": port})
    );
}

#[test]
fn cloud_fallback_without_consent_or_key_sends_nothing() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("fbcloud");
    let port = lab.server.port;
    let key = lab.key.clone();
    expect_ok(&lab.core.set_secret("google", &key));
    let primary = json!({"provider": "local", "model": "mode-503", "local_port": port,
                         "custom_url": null, "cloud_consent": false});
    let mut body = primary.clone();
    body["fallback"] = json!({"provider": "google", "model": "gemini-3.5-flash-lite"});
    expect_ok(&lab.core.configure(body));
    // Key stored, consent off: the fallback is refused before any request exists.
    expect_ok(&lab.core.invoke("llm2.chain", json!({"text": "hi"}), 8000));
    let result = settled(&mut lab.core, "llm2.chain");
    assert_eq!(result["output"]["attempted"], true, "{result}");
    assert_eq!(
        result["output"]["primary"]["error"], "http_error",
        "{result}"
    );
    assert_eq!(result["output"]["primary"]["status"], 503, "{result}");
    assert_eq!(
        result["output"]["terminal"]["error"], "cloud_not_authorized",
        "{result}"
    );
    assert_eq!(result["output"]["used_fallback"], false);
    assert_eq!(
        result["output"]["ctx"],
        json!({"llm": {"provider": "local", "model": "mode-503",
                       "fallback": {"provider": "google", "model": "gemini-3.5-flash-lite"}}})
    );
    assert_eq!(
        lab.server.requests(),
        1,
        "only the primary may reach a server"
    );
    wait_no_brokers();
    // Consent on but no key: key_missing, still no request anywhere.
    let mut consent = primary.clone();
    consent["cloud_consent"] = json!(true);
    consent["fallback"] = json!({"provider": "google", "model": "gemini-3.5-flash-lite"});
    expect_ok(&lab.core.configure(consent));
    expect_ok(
        &lab.core
            .call(json!({"op": "secret_clear", "provider": "google"})),
    );
    expect_ok(&lab.core.invoke("llm2.chain", json!({"text": "hi"}), 8000));
    let keyless = settled(&mut lab.core, "llm2.chain");
    assert_eq!(
        keyless["output"]["terminal"]["error"], "key_missing",
        "{keyless}"
    );
    assert_eq!(
        lab.server.requests(),
        2,
        "the second primary call is the only new request"
    );
    wait_no_brokers();
    lab.core.assert_no_key_on_disk();
}

#[test]
fn local_fallback_runs_only_after_a_recoverable_error_and_is_announced() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("fblocal");
    let port = lab.server.port;
    expect_ok(&lab.core.configure(json!({
        "provider": "local", "model": "mode-503", "local_port": port, "custom_url": null,
        "cloud_consent": false,
        "fallback": {"provider": "ollama", "model": "mode-sse", "local_port": port},
    })));
    expect_ok(&lab.core.invoke("llm2.chain", json!({"text": "hi"}), 8000));
    let result = settled(&mut lab.core, "llm2.chain");
    assert_eq!(result["output"]["attempted"], true, "{result}");
    assert_eq!(result["output"]["used_fallback"], true, "{result}");
    assert_eq!(result["output"]["text"], "Hello world", "{result}");
    let seen = requests_seen(port);
    assert_eq!(seen.len(), 2, "{seen:?}");
    assert_eq!(seen[0]["model"], "mode-503");
    assert_eq!(seen[1]["model"], "mode-sse");
    assert!(seen.iter().all(|r| r["auth"].is_null()));
    let snap = lab.core.snap();
    // NF-10: the snapshot says the fallback answered the last chat, with a time and no content.
    assert_eq!(snap["llm"]["last_chat"]["used_fallback"], true, "{snap}");
    assert!(snap["llm"]["last_chat"]["at_ms"].as_u64().unwrap_or(0) > 0);
    assert!(!snap["llm"]["last_chat"].to_string().contains("Hello"));
    let events = snap["events"].as_array().unwrap();
    assert!(
        events.iter().any(|e| e["kind"] == "llm_fallback_used"),
        "{snap}"
    );
    assert!(
        !snap["events"].to_string().contains("Hello"),
        "event leaked content"
    );
    wait_no_brokers();
}

#[test]
fn fallback_is_used_only_when_the_plugin_asks_and_never_after_a_hard_error() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("fbask");
    let port = lab.server.port;
    expect_ok(&lab.core.configure(json!({
        "provider": "local", "model": "mode-401", "local_port": port, "custom_url": null,
        "cloud_consent": false,
        "fallback": {"provider": "ollama", "model": "mode-sse", "local_port": port},
    })));
    // Plain chat without `target` is the primary route only.
    expect_ok(&lab.core.invoke("llm2.chat", json!({"text": "hi"}), 8000));
    let plain = settled(&mut lab.core, "llm2.chat");
    assert_eq!(
        plain["output"]["terminal"]["error"], "http_error",
        "{plain}"
    );
    assert_eq!(plain["output"]["terminal"]["status"], 401, "{plain}");
    assert_eq!(lab.server.requests(), 1);
    // The chain never falls back after a non-recoverable (401) primary error.
    expect_ok(&lab.core.invoke("llm2.chain", json!({"text": "hi"}), 8000));
    let chain = settled(&mut lab.core, "llm2.chain");
    assert_eq!(chain["output"]["attempted"], false, "{chain}");
    assert_eq!(lab.server.requests(), 2);
    // Asking for the fallback explicitly reaches the fallback route.
    expect_ok(&lab.core.invoke(
        "llm2.chat",
        json!({"text": "hi", "target": "fallback"}),
        8000,
    ));
    let explicit = settled(&mut lab.core, "llm2.chat");
    assert_eq!(explicit["output"]["text"], "Hello world", "{explicit}");
    let seen = requests_seen(port);
    assert_eq!(seen.len(), 3, "{seen:?}");
    assert_eq!(seen[2]["model"], "mode-sse");
    // An unknown target is a protocol refusal, not a silent primary call.
    expect_ok(
        &lab.core
            .invoke("llm2.chat", json!({"text": "hi", "target": "other"}), 8000),
    );
    let unknown = settled(&mut lab.core, "llm2.chat");
    assert_eq!(
        unknown["output"]["terminal"]["error"], "invalid_host_call",
        "{unknown}"
    );
    assert_eq!(lab.server.requests(), 3);
    // Without a configured fallback, asking for it fails closed.
    expect_ok(&lab.core.configure_local("local", "mode-sse", port));
    expect_ok(&lab.core.invoke(
        "llm2.chat",
        json!({"text": "hi", "target": "fallback"}),
        8000,
    ));
    let missing = settled(&mut lab.core, "llm2.chat");
    assert_eq!(
        missing["output"]["terminal"]["error"], "provider_not_configured",
        "{missing}"
    );
    assert_eq!(lab.server.requests(), 3);
    wait_no_brokers();
}

#[test]
fn settings_get_put_enforce_limits_and_strict_shape() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("settings");
    let core = &mut lab.core;
    let root = core.root.clone();
    let got = raw(core, "settings.get", json!({"args": {}}));
    assert_eq!(got["done"], true, "{got}");
    assert!(got["data"].is_null(), "{got}");
    let put = raw(core, "settings.put", json!({"args": {"data": {"a": 1}}}));
    assert_eq!(put["done"], true, "{put}");
    assert_eq!(
        raw(core, "settings.get", json!({"args": {}}))["data"],
        json!({"a": 1})
    );
    // Shape: data must be an object; the args accept nothing extra; unknown services are refused.
    assert_eq!(
        raw(core, "settings.put", json!({"args": {"data": [1]}}))["error"],
        "invalid_input"
    );
    assert_eq!(
        raw(core, "settings.get", json!({"args": {"x": 1}}))["error"],
        "invalid_host_call"
    );
    assert_eq!(
        raw(core, "settings.put", json!({"args": {"data": {}, "x": 1}}))["error"],
        "invalid_host_call"
    );
    assert_eq!(
        raw(core, "settings.delete", json!({"args": {}}))["error"],
        "invalid_host_call"
    );
    // Size: `{"blob":"<n a's>"}` serializes to n + 11 bytes, so n = 8181 is exactly the 8 KiB limit.
    assert_eq!(
        raw(core, "settings.put", json!({"fill": 8181}))["done"],
        true
    );
    assert_eq!(
        raw(core, "settings.put", json!({"fill": 8182}))["error"],
        "invalid_input"
    );
    // Depth: four nested objects are allowed, five are not.
    assert_eq!(raw(core, "settings.put", json!({"nest": 4}))["done"], true);
    assert_eq!(
        raw(core, "settings.put", json!({"nest": 5}))["error"],
        "invalid_input"
    );
    let stored = fs::metadata(root.join("plugin-settings/llm2.json")).unwrap();
    assert!(stored.len() <= 16 * 1024);
    assert_eq!(stored.permissions().mode() & 0o777, 0o600);
    assert_eq!(
        fs::metadata(root.join("plugin-settings"))
            .unwrap()
            .permissions()
            .mode()
            & 0o777,
        0o700
    );
    // A corrupt file is reported, never silently replaced by an empty object.
    fs::write(root.join("plugin-settings/llm2.json"), b"not json").unwrap();
    fs::set_permissions(
        root.join("plugin-settings/llm2.json"),
        fs::Permissions::from_mode(0o600),
    )
    .unwrap();
    assert_eq!(
        raw(core, "settings.get", json!({"args": {}}))["error"],
        "settings_unavailable"
    );
    assert_eq!(
        raw(core, "settings.put", json!({"args": {"data": {"a": 2}}}))["done"],
        true
    );
    assert_eq!(
        raw(core, "settings.get", json!({"args": {}}))["data"],
        json!({"a": 2})
    );
    core.assert_no_key_on_disk();
    core.assert_private_c2_files();
}

#[test]
fn settings_need_the_approved_storage_settings_grant() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("grant");
    let got = {
        expect_ok(&lab.core.invoke(
            "nosettings.raw",
            json!({"service": "settings.get", "args": {}}),
            8000,
        ));
        settled(&mut lab.core, "nosettings.raw")["output"]["terminal"].clone()
    };
    assert_eq!(got["error"], "permission_denied", "{got}");
    expect_ok(&lab.core.invoke(
        "nosettings.raw",
        json!({"service": "settings.put", "fill": 10}),
        8000,
    ));
    let put = settled(&mut lab.core, "nosettings.raw")["output"]["terminal"].clone();
    assert_eq!(put["error"], "permission_denied", "{put}");
    assert!(!lab
        .core
        .root
        .join("plugin-settings/nosettings.json")
        .exists());
    // The granted plugin is unaffected by the refusal.
    assert_eq!(
        raw(
            &mut lab.core,
            "settings.put",
            json!({"args": {"data": {"ok": true}}})
        )["done"],
        true
    );
}

#[test]
fn settings_survive_remove_reinstall_and_restart_until_explicitly_cleared() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("persist");
    assert_eq!(
        raw(
            &mut lab.core,
            "settings.put",
            json!({"args": {"data": {"kept": true}}})
        )["done"],
        true
    );
    expect_ok(&lab.core.disable("llm2"));
    let remove_revision = lab.core.snap()["hub"]["install_revision"].as_u64().unwrap();
    expect_ok(&lab.core.call(json!({
        "op": "hub_remove", "revision": remove_revision, "plugin_id": "llm2",
    })));
    assert!(item_of(&lab.core.snap(), "llm2")["state"] != "running");
    let payload = lab.llm2.clone();
    lab.core.install("llm2", &payload);
    expect_ok(&lab.core.enable("llm2"));
    lab.core
        .wait_for("reinstalled", |s| item_of(s, "llm2")["state"] == "running");
    assert_eq!(
        raw(&mut lab.core, "settings.get", json!({"args": {}}))["data"],
        json!({"kept": true})
    );
    lab.core.stop();
    lab.core.start();
    lab.core
        .wait_for("restarted", |s| item_of(s, "llm2")["state"] == "running");
    assert_eq!(
        raw(&mut lab.core, "settings.get", json!({"args": {}}))["data"],
        json!({"kept": true})
    );
    // Clearing is an explicit user operation; the plugin cannot reach it.
    assert_eq!(
        raw(
            &mut lab.core,
            "plugin_settings_clear",
            json!({"args": {"plugin_id": "llm2"}})
        )["error"],
        "invalid_host_call"
    );
    expect_ok(
        &lab.core
            .call(json!({"op": "plugin_settings_clear", "plugin_id": "llm2"})),
    );
    assert!(!lab.core.root.join("plugin-settings/llm2.json").exists());
    assert!(raw(&mut lab.core, "settings.get", json!({"args": {}}))["data"].is_null());
    expect_ok(
        &lab.core
            .call(json!({"op": "plugin_settings_clear", "plugin_id": "llm2"})),
    );
    assert_eq!(
        lab.core
            .call(json!({"op": "plugin_settings_clear", "plugin_id": "bad/id"}))["code"],
        "invalid_id"
    );
    wait_no_brokers();
}

#[test]
fn keyless_broker_requests_are_loopback_literals_only() {
    // Broker processes are counted by other tests, so this one takes the same lock.
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let script = Path::new(env!("CARGO_MANIFEST_DIR")).join("scripts/net_broker.py");
    let run = |request: Value, key_line: &str| -> String {
        let mut child = Command::new(PYTHON)
            .arg("-I")
            .arg(&script)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        {
            let mut stdin = child.stdin.take().unwrap();
            writeln!(stdin, "{request}").unwrap();
            writeln!(stdin, "{key_line}").unwrap();
        }
        let output = child.wait_with_output().unwrap();
        String::from_utf8(output.stdout).unwrap()
    };
    let request = |url: &str, expected: &str| {
        json!({
            "url": url, "method": "POST", "headers": {"Content-Type": "application/json"},
            "body": "{}", "timeout_s": 5, "expected_host": expected,
            "allow_http": true, "allow_loopback": true,
            "auth": "bearer", "dialect": "openai",
        })
    };
    // A closed loopback port: the request reaches the network layer and is refused there.
    let refused = run(
        request("http://127.0.0.1:1/x", "127.0.0.1"),
        r#"{"key":null}"#,
    );
    assert!(refused.contains("network_unavailable"), "{refused}");
    // Name resolution is never used for keyless targets.
    let name = run(
        request("http://localhost:9/x", "localhost"),
        r#"{"key":null}"#,
    );
    assert!(name.contains("host_not_allowed"), "{name}");
    // Keyless never reaches a foreign host, even a loopback-looking one.
    let foreign = run(
        request("http://example.com/x", "example.com"),
        r#"{"key":null}"#,
    );
    assert!(foreign.contains("host_not_allowed"), "{foreign}");
    // The key line keeps its strict shape: null is the only non-key value accepted.
    let odd = run(request("http://127.0.0.1:1/x", "127.0.0.1"), r#"{"key":1}"#);
    assert!(odd.contains("invalid_request"), "{odd}");
    let extra = run(
        request("http://127.0.0.1:1/x", "127.0.0.1"),
        r#"{"key":null,"x":1}"#,
    );
    assert!(extra.contains("invalid_request"), "{extra}");
}
