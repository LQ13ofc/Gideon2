//! C1 LLM plumbing against the real Core binary: vault and config ledgers, Core-brokered HTTP
//! through the real bwrap broker, and an inline loopback HTTP server (stdlib Python). Every
//! test owns a tempdir root and runs under one lock so process counts cannot interfere.
use gideon_base::hub;
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
const LLM_CATALOG: &str = include_str!("fixtures/hub-c1.json");

/// Inline plugin: `stubllm.chat` streams through `llm.http`, `stubllm.double` sends two calls at
/// once, `stubllm.direct` tries a raw socket. `noperm.chat` is the same code without the grant.
const STUB: &str = r#"#!/usr/bin/env python3
import json, queue, socket, sys, threading
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
def sse_pieces(buffer, text):
    buffer += text
    pieces = []
    while "\n\n" in buffer:
        event, buffer = buffer.split("\n\n", 1)
        for line in event.split("\n"):
            if line.startswith("data: ") and line[6:].strip() != "[DONE]":
                try:
                    delta = json.loads(line[6:])["choices"][0]["delta"].get("content")
                except Exception:
                    delta = None
                if isinstance(delta, str) and delta:
                    pieces.append(delta)
    return buffer, pieces
def chat_args(inp):
    if inp.get("raw_args") is not None:
        return inp["raw_args"]
    args = {
        "path": inp.get("path", "/chat/completions"),
        "body": {"messages": [{"role": "user", "content": inp.get("text", "hi")}]},
        "stream": inp.get("stream", True),
    }
    if inp.get("headers") is not None:
        args["headers"] = inp["headers"]
    return args
def chat(rid, inp, msg):
    parts = []
    send_args = chat_args(inp)
    send({"op": "host_call", "id": 1, "service": "llm.http", "args": send_args})
    buffer = ""
    while True:
        m = next_msg()
        if m is None:
            return
        if m.get("op") == "cancel" and m.get("id") == rid:
            send({"v": 1, "id": rid, "ok": False, "error": "cancelled"})
            return
        if m.get("op") != "host_reply" or m.get("id") != 1:
            continue
        if "chunk" in m:
            buffer, pieces = sse_pieces(buffer, m["chunk"])
            for piece in pieces:
                parts.append(piece)
                send({"event": "partial", "id": rid, "text": piece})
            continue
        # P12: `as_error` makes the plugin report the broker error as its own error code.
        if inp.get("as_error") and m.get("error"):
            send({"v": 1, "id": rid, "ok": False, "error": m["error"]})
            return
        send({"v": 1, "id": rid, "ok": True, "output": {
            "text": "".join(parts), "done": bool(m.get("done")),
            "status": m.get("status"), "host_error": m.get("error"),
            "host_status": m.get("status") if m.get("error") else None,
            "ctx": msg.get("ctx")}})
        return
def double(rid, msg):
    args = chat_args({})
    send({"op": "host_call", "id": 1, "service": "llm.http", "args": args})
    send({"op": "host_call", "id": 2, "service": "llm.http", "args": args})
    done = {}
    while len(done) < 2:
        m = next_msg()
        if m is None:
            break
        if m.get("op") == "host_reply" and "chunk" not in m and m.get("id") in (1, 2):
            done[m["id"]] = m
    first = done.get(1, {})
    second = done.get(2, {})
    send({"v": 1, "id": rid, "ok": True, "output": {
        "first_status": first.get("status"), "first_error": first.get("error"),
        "second_error": second.get("error")}})
def direct(rid, inp):
    try:
        s = socket.create_connection(("127.0.0.1", int(inp["port"])), timeout=1)
        s.close()
        send({"v": 1, "id": rid, "ok": True, "output": {"connected": True}})
    except Exception as error:
        send({"v": 1, "id": rid, "ok": True, "output": {"connected": False, "error": type(error).__name__}})
def dispatch(msg):
    rid = msg["id"]
    cap = msg.get("capability", "")
    inp = msg.get("input") or {}
    kind = cap.split(".", 1)[1] if "." in cap else ""
    if kind == "chat":
        chat(rid, inp, msg)
    elif kind == "double":
        double(rid, msg)
    elif kind == "direct":
        direct(rid, inp)
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

/// Loopback OpenAI-compatible fake. The request `model` selects the behaviour.
const SERVER: &str = r#"#!/usr/bin/env python3
import json, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
STATE = {"requests": [], "closed": 0}
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
            STATE["requests"].append({"path": self.path, "auth": self.headers.get("Authorization"), "model": model})
        if model in ("mode-401", "mode-429", "mode-500"):
            payload = b'{"error":"SECRET-PROVIDER-BODY"}'
            self.send_response(int(model.split("-")[1]))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if model == "mode-redirect":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/elsewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            if model == "mode-sse":
                for piece in ["Hel", "lo ", "wor", "ld"]:
                    self.wfile.write(sse(piece))
                    self.wfile.flush()
                    time.sleep(0.15)
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            elif model == "mode-big":
                block = b"data: " + b"a" * 65536 + b"\n\n"
                for _ in range(80):
                    self.wfile.write(block)
                self.wfile.flush()
            elif model == "mode-slow":
                time.sleep(30)
                self.wfile.write(b"data: [DONE]\n\n")
            elif model == "mode-endless":
                while True:
                    self.wfile.write(sse("x"))
                    self.wfile.flush()
                    time.sleep(0.05)
        except OSError:
            with LOCK:
                STATE["closed"] += 1
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
/// Fresh, unguessable test key; printable ASCII, 8..=256 bytes, never written outside secrets.json.
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
/// Every regular file under `dir`, recursively; symlinks are reported, never followed.
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

/// Loopback fake provider; killed on drop.
struct Server {
    child: Child,
    port: u16,
}
impl Server {
    fn start(dir: &Path) -> Server {
        let script = dir.join("fake_server.py");
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
    fn state(&self) -> Value {
        http_get(self.port, "/__state")
    }
    fn requests(&self) -> usize {
        self.state()["requests"].as_array().unwrap().len()
    }
    fn url(&self, path: &str) -> String {
        format!("http://127.0.0.1:{}{path}", self.port)
    }
}
impl Drop for Server {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

/// One Core process bound to a private root; killed on drop.
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
    fn pid(&self) -> Option<u32> {
        self.child.as_ref().map(Child::id)
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
            .arg("--net-allow-loopback")
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
    fn revoke(&mut self, plugin_id: &str) -> Value {
        let revision = self.plugin_revision();
        self.call(json!({"op": "plugin_revoke", "revision": revision, "plugin_id": plugin_id}))
    }
    fn invoke(&mut self, capability: &str, input: Value, deadline_ms: u64) -> Value {
        self.call(json!({
            "op": "capability_invoke",
            "capability": capability,
            "input": input,
            "deadline_ms": deadline_ms,
        }))
    }
    fn set_secret(&mut self, provider: &str, key: &str) -> Value {
        self.secret = Some(key.to_owned());
        self.call(json!({"op": "secret_set", "provider": provider, "key": key}))
    }
    fn configure(
        &mut self,
        provider: &str,
        model: &str,
        custom_url: Option<&str>,
        consent: bool,
    ) -> Value {
        let revision = self.llm_revision();
        self.call(json!({
            "op": "llm_configure",
            "revision": revision,
            "provider": provider,
            "model": model,
            "custom_url": custom_url,
            "cloud_consent": consent,
        }))
    }
    /// Installs `payload` through the real Hub path: approve, stage in chunks, finish, install.
    fn install(&mut self, plugin_id: &str, payload: &[u8]) {
        let snap = self.snap();
        let entry = entry_of(&snap, plugin_id);
        let manifest_sha = entry["manifest_sha256"].as_str().unwrap().to_owned();
        let approval = snap["hub"]["approval_revision"].as_u64().unwrap();
        expect_ok(&self.call(json!({
            "op": "hub_approve",
            "revision": approval,
            "plugin_id": plugin_id,
            "manifest_sha256": manifest_sha,
            "permissions": entry["permissions"],
            "publisher_unverified_ack": true,
        })));
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
    /// Sandbox of `stubllm` only; `noperm` keeps running in the same root.
    fn wait_no_stub_sandbox(&self) {
        wait_until("stubllm sandbox gone", || {
            processes_with("hub-plugins/stubllm-", self.pid()).is_empty()
        });
    }
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

fn stub_payload(id: &str, capabilities: &[&str]) -> Vec<u8> {
    STUB.replace("@PLUGIN_ID@", id)
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

/// A Core with an installed, running `stubllm` (network_llm granted) and `noperm` (no grant),
/// plus a loopback fake provider and a fresh random key.
struct Lab {
    _dir: tempfile::TempDir,
    core: Core,
    server: Server,
    key: String,
}
fn lab(name: &str) -> Lab {
    let dir = tempfile::tempdir().unwrap();
    let stub_llm = stub_payload(
        "stubllm",
        &["stubllm.chat", "stubllm.double", "stubllm.direct"],
    );
    let noperm = stub_payload("noperm", &["noperm.chat"]);
    let catalog = json!({
        "version": 1,
        "repository": "https://github.com/acme/plugins",
        "plugins": [
            manifest("stubllm", &["network_llm"], &["stubllm.chat", "stubllm.double", "stubllm.direct"], &stub_llm),
            manifest("noperm", &["plugin_access"], &["noperm.chat"], &noperm),
        ],
    });
    let bytes = serde_json::to_vec(&catalog).unwrap();
    let path = dir.path().join(format!("{name}.json"));
    fs::write(&path, &bytes).unwrap();
    let server = Server::start(dir.path());
    let mut core = Core::new(dir.path(), (path, sha(&bytes)));
    core.start();
    core.install("stubllm", &stub_llm);
    core.install("noperm", &noperm);
    expect_ok(&core.enable("stubllm"));
    expect_ok(&core.enable("noperm"));
    core.wait_for("plugins running", |s| {
        item_of(s, "stubllm")["state"] == "running" && item_of(s, "noperm")["state"] == "running"
    });
    Lab {
        _dir: dir,
        core,
        server,
        key: fake_key(name),
    }
}
/// Waits for the invocation result and checks which capability produced it.
fn settled(core: &mut Core, capability: &str) -> Value {
    let snap = core.wait_for("capability result", |s| !s["capability_result"].is_null());
    assert_eq!(snap["capability_result"]["capability"], capability);
    snap["capability_result"].clone()
}
fn brokers() -> Vec<u32> {
    processes_with("net_broker.py", None)
}
fn wait_no_brokers() {
    wait_until("broker processes gone", || brokers().is_empty());
}
fn closed_streams(port: u16) -> u64 {
    http_get(port, "/__state")["closed"].as_u64().unwrap()
}
fn requests_seen(port: u16) -> Vec<Value> {
    http_get(port, "/__state")["requests"]
        .as_array()
        .unwrap()
        .clone()
}

#[test]
fn vault_is_write_only_private_and_strictly_validated() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("vault");
    let key = lab.key.clone();
    assert_eq!(
        lab.core.snap()["llm"]["secrets"],
        json!({"openrouter": false, "opencode": false, "google": false, "custom": false})
    );
    assert_eq!(lab.core.set_secret("custom", &key)["code"], "ok");
    assert_eq!(lab.core.snap()["llm"]["secrets"]["custom"], true);
    let mode = fs::metadata(lab.core.root.join("secrets.json"))
        .unwrap()
        .permissions()
        .mode()
        & 0o777;
    assert_eq!(mode, 0o600);
    let stored = fs::read(lab.core.root.join("secrets.json")).unwrap();
    assert!(contains(&stored, &key), "vault must hold the key");
    // Refusals are coded and never echo the candidate bytes.
    let bad = [
        ("custom", "short".to_owned(), "invalid_secret"),
        ("custom", "has space in key".to_owned(), "invalid_secret"),
        ("custom", "ctl\u{1}chars-here".to_owned(), "invalid_secret"),
        ("custom", "x".repeat(257), "invalid_secret"),
        ("custom", format!("{key}\n"), "invalid_secret"),
        ("nope", key.clone(), "invalid_provider"),
    ];
    for (provider, candidate, code) in bad {
        let response = lab
            .core
            .call(json!({"op": "secret_set", "provider": provider, "key": candidate}));
        assert_eq!(response["code"], code, "{response}");
    }
    assert_eq!(
        lab.core
            .call(json!({"op": "secret_clear", "provider": "custom"}))["code"],
        "ok"
    );
    assert_eq!(lab.core.snap()["llm"]["secrets"]["custom"], false);
    assert_eq!(lab.core.set_secret("custom", &key)["code"], "ok");
    lab.core.assert_no_key_on_disk();
}

#[test]
fn llm_config_is_cas_checked_and_strictly_validated() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("config");
    let url = lab.server.url("/v1");
    assert_eq!(lab.core.snap()["llm"]["config"], Value::Null);
    let stale = lab.core.call(json!({
        "op": "llm_configure", "revision": 7, "provider": "google", "model": "m",
        "custom_url": null, "cloud_consent": false,
    }));
    assert_eq!(stale["code"], "stale_llm_revision");
    let rejected: Vec<(&str, String, Option<String>)> = vec![
        ("nope", "m".into(), None),
        ("google", "bad model".into(), None),
        ("google", "m".repeat(129), None),
        ("google", String::new(), None),
        ("google", "m".into(), Some("https://example.com/v1".into())),
        ("custom", "m".into(), None),
        ("custom", "m".into(), Some("http://example.com/v1".into())),
        (
            "custom",
            "m".into(),
            Some("https://93.184.216.34/v1".into()),
        ),
        (
            "custom",
            "m".into(),
            Some("https://user:pw@example.com/v1".into()),
        ),
        (
            "custom",
            "m".into(),
            Some("https://example.com/v1?x=1".into()),
        ),
        (
            "custom",
            "m".into(),
            Some("https://example.com/v1#frag".into()),
        ),
        ("custom", "m".into(), Some("ftp://example.com/v1".into())),
    ];
    for (provider, model, custom_url) in rejected {
        let revision = lab.core.llm_revision();
        let response = lab.core.call(json!({
            "op": "llm_configure", "revision": revision, "provider": provider,
            "model": model, "custom_url": custom_url, "cloud_consent": false,
        }));
        assert_eq!(
            response["code"], "invalid_config",
            "{provider} {custom_url:?}: {response}"
        );
    }
    assert_eq!(
        lab.core.snap()["llm"]["revision"],
        0,
        "rejections must not advance the CAS"
    );
    assert_eq!(
        lab.core
            .configure("google", "gemini-3.5-flash-lite", None, false)["code"],
        "ok"
    );
    let snap = lab.core.snap();
    assert_eq!(snap["llm"]["revision"], 1);
    assert_eq!(
        snap["llm"]["config"],
        json!({"provider": "google", "model": "gemini-3.5-flash-lite", "custom_url": null, "cloud_consent": false})
    );
    let stale_again = lab.core.call(json!({
        "op": "llm_configure", "revision": 0, "provider": "google", "model": "m",
        "custom_url": null, "cloud_consent": true,
    }));
    assert_eq!(stale_again["code"], "stale_llm_revision");
    // Loopback http is accepted only because this Core runs with --net-allow-loopback.
    assert_eq!(
        lab.core.configure("custom", "mode-sse", Some(&url), false)["code"],
        "ok"
    );
    assert_eq!(lab.core.snap()["llm"]["config"]["custom_url"], url.as_str());
    let mode = fs::metadata(lab.core.root.join("llm-config.json"))
        .unwrap()
        .permissions()
        .mode()
        & 0o777;
    assert_eq!(mode, 0o600);
}

#[test]
fn host_call_gates_return_their_codes_and_never_reach_the_provider() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("gates");
    let url = lab.server.url("/v1");
    let key = lab.key.clone();
    // Nothing configured: the grant exists but there is no provider.
    expect_ok(&lab.core.invoke("stubllm.chat", json!({"text": "hi"}), 5000));
    assert_eq!(
        settled(&mut lab.core, "stubllm.chat")["output"]["host_error"],
        "provider_not_configured"
    );
    // Cloud provider, key stored, consent off: refused before any connection.
    expect_ok(&lab.core.set_secret("openrouter", &key));
    expect_ok(&lab.core.configure("openrouter", "some-model", None, false));
    expect_ok(&lab.core.invoke("stubllm.chat", json!({"text": "hi"}), 5000));
    assert_eq!(
        settled(&mut lab.core, "stubllm.chat")["output"]["host_error"],
        "cloud_not_authorized"
    );
    // Consent given but the key removed: key_missing.
    expect_ok(
        &lab.core
            .call(json!({"op": "secret_clear", "provider": "openrouter"})),
    );
    expect_ok(&lab.core.configure("openrouter", "some-model", None, true));
    expect_ok(&lab.core.invoke("stubllm.chat", json!({"text": "hi"}), 5000));
    assert_eq!(
        settled(&mut lab.core, "stubllm.chat")["output"]["host_error"],
        "key_missing"
    );
    // Loopback custom (test mode): no consent needed, but a plugin without the grant is refused.
    expect_ok(&lab.core.set_secret("custom", &key));
    expect_ok(&lab.core.configure("custom", "mode-sse", Some(&url), false));
    expect_ok(&lab.core.invoke("noperm.chat", json!({"text": "hi"}), 5000));
    assert_eq!(
        settled(&mut lab.core, "noperm.chat")["output"]["host_error"],
        "permission_denied"
    );
    assert_eq!(lab.server.requests(), 0, "no gate may reach the provider");
    lab.core.assert_no_key_on_disk();
}

#[test]
fn partials_grow_and_final_arrives_with_core_held_authorization() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("happy");
    let url = lab.server.url("/v1");
    let key = lab.key.clone();
    expect_ok(&lab.core.set_secret("custom", &key));
    expect_ok(&lab.core.configure("custom", "mode-sse", Some(&url), false));
    // A plugin raw socket cannot reach the loopback provider (its sandbox has no network).
    expect_ok(
        &lab.core
            .invoke("stubllm.direct", json!({"port": lab.server.port}), 3000),
    );
    let direct = settled(&mut lab.core, "stubllm.direct");
    assert_eq!(direct["output"]["connected"], false);
    assert_eq!(lab.server.requests(), 0);
    // The plugin supplies its own Authorization and Host headers: Core must drop both.
    expect_ok(&lab.core.invoke(
        "stubllm.chat",
        json!({"text": "hi", "headers": {"Authorization": "Bearer PLUGIN-FAKE", "Host": "evil.example"}}),
        8000,
    ));
    let mut seen: Vec<String> = vec![];
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        let snap = lab.core.snap();
        if let Some(text) = snap["partial"].as_str() {
            if seen.last().map(String::as_str) != Some(text) {
                seen.push(text.to_owned());
            }
        }
        if !snap["capability_result"].is_null() {
            break;
        }
        assert!(Instant::now() < deadline, "invocation did not finish");
        thread::sleep(Duration::from_millis(20));
    }
    assert!(seen.len() >= 2, "partials did not grow: {seen:?}");
    for pair in seen.windows(2) {
        assert!(
            pair[1].len() > pair[0].len() && pair[1].starts_with(&pair[0]),
            "{seen:?}"
        );
    }
    let result = settled(&mut lab.core, "stubllm.chat");
    assert_eq!(result["ok"], true, "{result}");
    assert_eq!(result["output"]["text"], "Hello world");
    assert_eq!(result["output"]["status"], 200);
    assert_eq!(result["partial"], "Hello world");
    assert_eq!(
        result["output"]["ctx"],
        json!({"llm": {"provider": "custom", "model": "mode-sse"}})
    );
    let seen_by_provider = requests_seen(lab.server.port);
    assert_eq!(seen_by_provider.len(), 1);
    assert_eq!(seen_by_provider[0]["auth"], format!("Bearer {key}"));
    assert_eq!(seen_by_provider[0]["path"], "/v1/chat/completions");
    assert_eq!(seen_by_provider[0]["model"], "mode-sse");
    let snap = lab.core.snap();
    assert!(snap["events"]
        .as_array()
        .unwrap()
        .iter()
        .any(|e| e["kind"] == "capability_partial"));
    lab.core.assert_no_key_on_disk();
}

#[test]
fn provider_errors_surface_status_only_and_bodies_never_leave_the_broker() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("errors");
    let url = lab.server.url("/v1");
    let key = lab.key.clone();
    expect_ok(&lab.core.set_secret("custom", &key));
    for (model, status) in [("mode-401", 401), ("mode-429", 429), ("mode-500", 500)] {
        expect_ok(&lab.core.configure("custom", model, Some(&url), false));
        expect_ok(&lab.core.invoke("stubllm.chat", json!({"text": "hi"}), 5000));
        let result = settled(&mut lab.core, "stubllm.chat");
        assert_eq!(
            result["output"]["host_error"], "http_error",
            "{model}: {result}"
        );
        assert_eq!(result["output"]["status"], status);
        assert!(!result.to_string().contains("SECRET-PROVIDER-BODY"));
        assert!(!lab.core.snap().to_string().contains("SECRET-PROVIDER-BODY"));
    }
    lab.core.assert_no_key_on_disk();
}

#[test]
fn redirects_are_refused_and_oversize_responses_are_bounded() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("bounds");
    let url = lab.server.url("/v1");
    let key = lab.key.clone();
    expect_ok(&lab.core.set_secret("custom", &key));
    expect_ok(
        &lab.core
            .configure("custom", "mode-redirect", Some(&url), false),
    );
    expect_ok(&lab.core.invoke("stubllm.chat", json!({"text": "hi"}), 5000));
    let redirected = settled(&mut lab.core, "stubllm.chat");
    assert_eq!(
        redirected["output"]["host_error"], "redirect_refused",
        "{redirected}"
    );
    assert_eq!(
        lab.server.requests(),
        1,
        "the redirect target must not be followed"
    );
    expect_ok(&lab.core.configure("custom", "mode-big", Some(&url), false));
    expect_ok(&lab.core.invoke("stubllm.chat", json!({"text": "hi"}), 8000));
    let big = settled(&mut lab.core, "stubllm.chat");
    assert_eq!(big["output"]["host_error"], "response_too_large", "{big}");
    wait_no_brokers();
    lab.core.assert_no_key_on_disk();
}

#[test]
fn invocation_deadline_kills_a_slow_broker_and_keeps_the_key_out_of_its_argv_and_env() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("slow");
    let url = lab.server.url("/v1");
    let key = lab.key.clone();
    expect_ok(&lab.core.set_secret("custom", &key));
    expect_ok(&lab.core.configure("custom", "mode-slow", Some(&url), false));
    expect_ok(&lab.core.invoke("stubllm.chat", json!({"text": "hi"}), 1000));
    wait_until("broker running", || !brokers().is_empty());
    for pid in brokers() {
        for file in ["cmdline", "environ"] {
            let bytes = fs::read(format!("/proc/{pid}/{file}")).unwrap_or_default();
            assert!(!contains(&bytes, &key), "key visible in broker {file}");
        }
    }
    let result = settled(&mut lab.core, "stubllm.chat");
    assert_eq!(result["error"], "capability_timeout", "{result}");
    wait_no_brokers();
    // A timed-out invocation stops its broker; the plugin itself stays up (C0 semantics).
    assert_eq!(item_of(&lab.core.snap(), "stubllm")["state"], "running");
    lab.core.assert_no_key_on_disk();
}

#[test]
fn cancel_mid_stream_closes_the_provider_connection() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("cancel");
    let url = lab.server.url("/v1");
    let key = lab.key.clone();
    let port = lab.server.port;
    expect_ok(&lab.core.set_secret("custom", &key));
    expect_ok(
        &lab.core
            .configure("custom", "mode-endless", Some(&url), false),
    );
    expect_ok(
        &lab.core
            .invoke("stubllm.chat", json!({"text": "hi"}), 10000),
    );
    lab.core.wait_for("streaming", |s| s["partial"].is_string());
    let cancelled = lab
        .core
        .call(json!({"op": "capability_cancel", "capability": "stubllm.chat"}));
    expect_ok(&cancelled);
    let result = settled(&mut lab.core, "stubllm.chat");
    assert_eq!(result["error"], "invoke_cancelled");
    wait_until("provider sees the closed stream", || {
        closed_streams(port) >= 1
    });
    wait_no_brokers();
}

#[test]
fn disable_and_revoke_mid_stream_kill_the_broker_and_the_plugin() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("stops");
    let url = lab.server.url("/v1");
    let key = lab.key.clone();
    let port = lab.server.port;
    expect_ok(&lab.core.set_secret("custom", &key));
    expect_ok(
        &lab.core
            .configure("custom", "mode-endless", Some(&url), false),
    );
    expect_ok(
        &lab.core
            .invoke("stubllm.chat", json!({"text": "hi"}), 10000),
    );
    lab.core.wait_for("streaming", |s| s["partial"].is_string());
    expect_ok(&lab.core.disable("stubllm"));
    wait_no_brokers();
    lab.core.wait_no_stub_sandbox();
    wait_until("provider sees the closed stream", || {
        closed_streams(port) >= 1
    });
    assert_eq!(item_of(&lab.core.snap(), "stubllm")["state"], "disabled");

    expect_ok(&lab.core.enable("stubllm"));
    lab.core.wait_for("running again", |s| {
        item_of(s, "stubllm")["state"] == "running"
    });
    let closed_before = closed_streams(port);
    expect_ok(
        &lab.core
            .invoke("stubllm.chat", json!({"text": "hi"}), 10000),
    );
    lab.core
        .wait_for("streaming again", |s| s["partial"].is_string());
    expect_ok(&lab.core.revoke("stubllm"));
    wait_no_brokers();
    lab.core.wait_no_stub_sandbox();
    wait_until("second stream closed", || {
        closed_streams(port) > closed_before
    });
    assert_eq!(
        lab.core.invoke("stubllm.chat", json!({"text": "hi"}), 1000)["code"],
        "capability_unavailable"
    );
    lab.core.assert_no_key_on_disk();
}

#[test]
fn core_shutdown_leaves_no_broker_or_plugin_process() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("shutdown");
    let url = lab.server.url("/v1");
    let key = lab.key.clone();
    expect_ok(&lab.core.set_secret("custom", &key));
    expect_ok(
        &lab.core
            .configure("custom", "mode-endless", Some(&url), false),
    );
    expect_ok(
        &lab.core
            .invoke("stubllm.chat", json!({"text": "hi"}), 10000),
    );
    lab.core.wait_for("streaming", |s| s["partial"].is_string());
    assert!(!brokers().is_empty());
    lab.core.stop();
    wait_no_brokers();
    wait_until("plugin sandboxes gone", || {
        processes_with(&lab.core.root.to_string_lossy(), None).is_empty()
    });
}

#[test]
fn a_second_host_call_while_one_is_active_is_refused_busy() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("double");
    let url = lab.server.url("/v1");
    let key = lab.key.clone();
    expect_ok(&lab.core.set_secret("custom", &key));
    expect_ok(&lab.core.configure("custom", "mode-sse", Some(&url), false));
    expect_ok(&lab.core.invoke("stubllm.double", json!({}), 8000));
    let result = settled(&mut lab.core, "stubllm.double");
    assert_eq!(result["output"]["first_status"], 200, "{result}");
    assert_eq!(result["output"]["second_error"], "busy", "{result}");
    assert_eq!(lab.server.requests(), 1);
    wait_no_brokers();
}

#[test]
fn configuration_and_vault_survive_restart_without_being_re_entered() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("restart");
    let url = lab.server.url("/v1");
    let key = lab.key.clone();
    expect_ok(&lab.core.set_secret("custom", &key));
    expect_ok(&lab.core.configure("custom", "mode-sse", Some(&url), false));
    lab.core.stop();
    lab.core.start();
    let snap = lab.core.wait_for("restarted plugin running", |s| {
        item_of(s, "stubllm")["state"] == "running"
    });
    assert_eq!(snap["llm"]["revision"], 1);
    assert_eq!(snap["llm"]["config"]["provider"], "custom");
    assert_eq!(snap["llm"]["secrets"]["custom"], true);
    expect_ok(&lab.core.invoke("stubllm.chat", json!({"text": "hi"}), 8000));
    let result = settled(&mut lab.core, "stubllm.chat");
    assert_eq!(result["output"]["text"], "Hello world", "{result}");
    lab.core.assert_no_key_on_disk();
}

#[test]
fn broker_script_refuses_bad_requests_without_touching_the_network() {
    let script = Path::new(env!("CARGO_MANIFEST_DIR")).join("scripts/net_broker.py");
    let key = fake_key("script");
    let run = |first: &str, second: &str| -> String {
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
            writeln!(stdin, "{first}").unwrap();
            writeln!(stdin, "{second}").unwrap();
        }
        let output = child.wait_with_output().unwrap();
        String::from_utf8(output.stdout).unwrap()
    };
    let request = |url: &str, expected: &str, allow_http: bool| {
        json!({
            "url": url, "method": "POST", "headers": {"Content-Type": "application/json"},
            "body": "{}", "timeout_s": 5, "expected_host": expected,
            "allow_http": allow_http, "allow_loopback": false,
        })
        .to_string()
    };
    let key_line = json!({"key": key}).to_string();
    let garbage = run("not json", &key_line);
    assert!(garbage.contains("invalid_request"), "{garbage}");
    let short = run(
        &request("https://openrouter.ai/x", "openrouter.ai", false),
        r#"{"key":"short"}"#,
    );
    assert!(short.contains("invalid_request"), "{short}");
    let mismatch = run(
        &request("https://other.example/x", "openrouter.ai", false),
        &key_line,
    );
    assert!(mismatch.contains("host_not_allowed"), "{mismatch}");
    let plain = run(
        &request("http://example.com/x", "example.com", false),
        &key_line,
    );
    assert!(plain.contains("host_not_allowed"), "{plain}");
    let loopback = run(
        &request("https://127.0.0.1:9/x", "127.0.0.1", false),
        &key_line,
    );
    assert!(loopback.contains("host_not_allowed"), "{loopback}");
    for output in [garbage, short, mismatch, plain, loopback] {
        assert!(!output.contains(&key), "broker echoed the key: {output}");
    }
}

#[test]
fn shipped_llm_fixture_catalog_loads_with_the_network_llm_grant() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("hub-c1.json");
    fs::write(&path, LLM_CATALOG).unwrap();
    let digest = sha(LLM_CATALOG.as_bytes());
    let snapshot = hub::load(&path, &digest).expect("C1 catalog loads with its own digest");
    let value = serde_json::to_value(&snapshot).unwrap();
    assert_eq!(value["status"], "verified", "{value}");
    let entry = value["entries"]
        .as_array()
        .unwrap()
        .iter()
        .find(|e| e["plugin_id"] == "llm_engine")
        .cloned()
        .expect("llm_engine entry");
    assert_eq!(
        entry["permissions"],
        json!(["network_llm", "storage_settings"])
    );
    assert_eq!(entry["runtime"], "python3_script");
    let capabilities = entry["capabilities"].as_array().unwrap();
    assert!(capabilities.contains(&json!("llm_engine.chat")));
    assert!(capabilities.contains(&json!("llm_engine.models")));
}

/// P12: an upstream error arrives as `http_error` with the Core-side `http_status`; the body and
/// headers never appear in the client view.
#[test]
fn http_error_code_and_status_reach_clients_without_provider_body() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut lab = lab("httpcode");
    let url = lab.server.url("/v1");
    let key = lab.key.clone();
    expect_ok(&lab.core.set_secret("custom", &key));
    expect_ok(&lab.core.configure("custom", "mode-401", Some(&url), false));
    expect_ok(&lab.core.invoke(
        "stubllm.chat",
        json!({"text": "hi", "as_error": true}),
        5000,
    ));
    let result = settled(&mut lab.core, "stubllm.chat");
    assert_eq!(result["ok"], false, "{result}");
    assert_eq!(result["error"], "http_error", "{result}");
    assert_eq!(result["http_status"], 401, "{result}");
    assert!(!result.to_string().contains("SECRET-PROVIDER-BODY"));
    assert!(!lab.core.snap().to_string().contains("SECRET-PROVIDER-BODY"));
    lab.core.assert_no_key_on_disk();
}
