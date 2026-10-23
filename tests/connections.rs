//! S5 E1 Connection Manager against the real Core binary and the Core-brokered broker, with an
//! inline loopback GitHub-like stub (python3 stdlib). Every test owns a tempdir root and runs under
//! one lock so process counts and the stub's timing cannot interfere.
use serde_json::{json, Value};
use std::{
    fs,
    io::{BufRead, BufReader, Read, Write},
    net::{TcpStream, ToSocketAddrs},
    os::unix::{fs::PermissionsExt, net::UnixStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

static SERIAL: Mutex<()> = Mutex::new(());
const PYTHON: &str = "/usr/bin/python3";

/// Loopback stub that follows the S5 github contract (OAuth device flow, rotating refresh tokens,
/// Bearer scopes, Idempotency-Key replay, 429 with Retry-After, X-Account on every response).
/// `/__control/*` exists only for these tests; state reports tokens to the test, never to the Core.
const STUB: &str = r##"#!/usr/bin/env python3
import json, secrets, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
ST = {}

def reset():
    ST.clear()
    ST.update({
        "device": {}, "access": {}, "refresh": {}, "issues": {}, "idem": {},
        "next_issue": {}, "comments": [], "requests": [], "posts": {},
        "account": "demo-user", "refresh_mode": "ok", "fail_after_create": 0,
        "rate_left": 0, "rate_after": 1, "revoked_calls": 0, "last_device": None,
        "last_access": None, "last_refresh": None, "delay": [0, 0],
    })

REPOS = {
    "demo/public-repo": {"private": False, "default_branch": "main"},
    "demo/private-repo": {"private": True, "default_branch": "main"},
    "demo/sleep-repo": {"private": True, "default_branch": "main"},
}

def record(method, path, status):
    ST["requests"].append({"method": method, "path": path, "status": status})
    if method == "POST" and path.startswith("/api/"):
        ST["posts"][path] = ST["posts"].get(path, 0) + 1

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *args):
        pass
    def send_json(self, status, obj, headers=None):
        raw = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Account", ST["account"])
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)
    def body(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            return None
    def bearer(self):
        auth = self.headers.get("Authorization") or ""
        return auth[7:] if auth.startswith("Bearer ") else None
    def api(self, method, path, body):
        token = self.bearer()
        rec = ST["access"].get(token) if token else None
        if rec is None or not rec["active"]:
            return 401, {"error": "bad_credentials"}, {}
        def need(scope):
            return None if scope in rec["scopes"] else (403, {"error": "insufficient_scope"}, {})
        if ST["rate_left"] > 0:
            ST["rate_left"] -= 1
            return 429, {"error": "rate_limited"}, {"Retry-After": str(ST["rate_after"])}
        parts = path.split("/")
        # /api/repos[/owner/name[/...]]
        if path == "/api/repos":
            denied = need("repo:read")
            if denied: return denied
            return 200, [{"name": r.split("/")[1], "private": v["private"], "default_branch": v["default_branch"]}
                         for r, v in REPOS.items()], {}
        if len(parts) >= 5 and parts[1] == "api" and parts[2] == "repos":
            repo = parts[3] + "/" + parts[4]
            tail = parts[5:]
            if repo not in REPOS:
                return 404, {"error": "not_found"}, {}
            if method == "GET" and not tail:
                denied = need("repo:read")
                if denied: return denied
                v = REPOS[repo]
                return 200, {"name": parts[4], "private": v["private"], "default_branch": v["default_branch"]}, {}
            if method == "GET" and tail == ["actions"]:
                denied = need("repo:read")
                if denied: return denied
                return 200, [{"id": 1, "name": "ci", "status": "success", "log": "SECRET-LOG"}], {}
            if method == "POST" and tail == ["issues"]:
                denied = need("issues:write")
                if denied: return denied
                key = self.headers.get("Idempotency-Key")
                if key and (repo, key) in ST["idem"]:
                    return 201, ST["idem"][(repo, key)], {"X-Idempotent-Replay": "true"}
                data = body or {}
                number = ST["next_issue"].get(repo, 0) + 1
                ST["next_issue"][repo] = number
                issue = {"number": number, "title": str(data.get("title", "")), "url": "https://example.invalid/%s/issues/%d" % (repo, number), "state": "open", "public": not REPOS[repo]["private"], "internal_note": "SECRET-NOTE"}
                ST["issues"].setdefault(repo, []).append(issue)
                if key:
                    ST["idem"][(repo, key)] = issue
                if ST["fail_after_create"] > 0:
                    ST["fail_after_create"] -= 1
                    return 500, {"error": "server_error"}, {}
                return 201, issue, {}
            if method == "POST" and len(tail) == 3 and tail[0] == "pulls" and tail[2] == "comments":
                denied = need("pulls:write")
                if denied: return denied
                comment = {"id": len(ST["comments"]) + 1, "body": str((body or {}).get("body", "")), "url": "https://example.invalid/c", "internal": "SECRET-COMMENT"}
                ST["comments"].append(comment)
                if ST["fail_after_create"] > 0:
                    ST["fail_after_create"] -= 1
                    return 500, {"error": "server_error"}, {}
                return 201, comment, {}
            if method == "GET" and len(tail) == 2 and tail[0] == "pulls":
                denied = need("repo:read")
                if denied: return denied
                return 200, {"number": int(tail[1]), "title": "pr", "state": "open", "url": "https://example.invalid/pr", "head": {"sha": "abc"}}, {}
        return 404, {"error": "not_found"}, {}
    def route(self, method):
        path = self.path.split("?")[0]
        data = self.body()
        if data is None:
            return 400, {"error": "invalid_json"}, {}
        with LOCK:
            if path.startswith("/__control/"):
                return self.control(method, path, data)
            if path == "/login/device/code" and method == "POST":
                device_code = secrets.token_urlsafe(24)
                user_code = "ABCD-" + secrets.token_hex(2).upper()
                ST["device"][device_code] = {"user_code": user_code, "approved": False, "used": False, "scopes": []}
                ST["last_device"] = device_code
                return 200, {"device_code": device_code, "user_code": user_code, "verification_uri": "http://127.0.0.1/login/device", "expires_in": 600, "interval": 1}, {}
            if path == "/login/oauth/access_token" and method == "POST":
                dev = ST["device"].get(data.get("device_code"))
                if not isinstance(data.get("grant_type"), str) or not data.get("grant_type"):
                    return 400, {"error": "invalid_request"}, {}
                if dev is None or dev["used"]:
                    return 400, {"error": "invalid_grant"}, {}
                if not dev["approved"]:
                    return 400, {"error": "authorization_pending"}, {}
                dev["used"] = True
                return 200, self.issue(dev["scopes"]), {}
            if path == "/login/oauth/refresh" and method == "POST":
                rec = ST["refresh"].get(data.get("refresh_token")) if isinstance(data.get("refresh_token"), str) else None
                if rec is None or rec["revoked"]:
                    return 400, {"error": "invalid_grant"}, {}
                if ST["refresh_mode"] == "503":
                    return 503, {"error": "unavailable"}, {}
                rec["revoked"] = True
                return 200, self.issue(rec["scopes"]), {}
            if path == "/login/oauth/revoke" and method == "POST":
                token = data.get("token")
                hit = False
                for table in (ST["access"], ST["refresh"]):
                    rec = table.get(token)
                    if rec is not None and not rec.get("revoked"):
                        rec["revoked"] = True
                        rec["active"] = False
                        hit = True
                ST["revoked_calls"] += 1
                return 200, {"revoked": hit}, {}
            if path.startswith("/api/"):
                return self.api(method, path, data)
            return 404, {"error": "not_found"}, {}
    def issue(self, scopes):
        access = secrets.token_urlsafe(24)
        refresh = secrets.token_urlsafe(24)
        ST["access"][access] = {"scopes": set(scopes), "active": True}
        ST["refresh"][refresh] = {"scopes": list(scopes), "revoked": False}
        ST["last_access"] = access
        ST["last_refresh"] = refresh
        return {"access_token": access, "refresh_token": refresh, "expires_in": 3600, "scope": " ".join(scopes), "account": ST["account"]}
    def control(self, method, path, data):
        name = path[len("/__control/"):]
        if name == "state":
            return 200, {"requests": ST["requests"], "posts": ST["posts"],
                         "issues": {r: [i["number"] for i in v] for r, v in ST["issues"].items()},
                         "comments": len(ST["comments"]), "revoked_calls": ST["revoked_calls"],
                         "last_device_code": ST["last_device"], "last_access_token": ST["last_access"],
                         "last_refresh_token": ST["last_refresh"], "account": ST["account"]}, {}
        if name == "approve":
            dev = ST["device"].get(data.get("device_code"))
            if dev is None:
                return 404, {"error": "unknown_device_code"}, {}
            dev["approved"] = True
            dev["scopes"] = list(data.get("scopes", []))
            return 200, {"ok": True}, {}
        if name == "expire_access":
            for rec in ST["access"].values():
                rec["active"] = False
            return 200, {"ok": True}, {}
        if name == "invalidate_refresh":
            for rec in ST["refresh"].values():
                rec["revoked"] = True
            return 200, {"ok": True}, {}
        if name == "refresh_mode":
            ST["refresh_mode"] = data.get("mode", "ok")
            return 200, {"ok": True}, {}
        if name == "rate_limit":
            ST["rate_left"] = int(data.get("n", 0))
            ST["rate_after"] = int(data.get("retry_after", 1))
            return 200, {"ok": True}, {}
        if name == "set_account":
            ST["account"] = str(data.get("name"))
            return 200, {"ok": True}, {}
        if name == "fail_after_create":
            ST["fail_after_create"] = int(data.get("n", 0))
            return 200, {"ok": True}, {}
        if name == "delay":
            # The next n provider requests answer after `seconds` (races between queued jobs).
            ST["delay"] = [int(data.get("n", 0)), float(data.get("seconds", 0))]
            return 200, {"ok": True}, {}
        return 404, {"error": "not_found"}, {}
    def handle_method(self, method):
        # Sleeps happen outside the lock so other requests are not held up.
        if not self.path.startswith("/__control/") and ST["delay"][0] > 0:
            with LOCK:
                ST["delay"][0] -= 1
                pause = ST["delay"][1]
            time.sleep(pause)
        if method == "GET" and self.path.startswith("/api/repos/demo/sleep-repo"):
            time.sleep(12)
        status, obj, headers = self.route(method)
        with LOCK:
            record(method, self.path.split("?")[0], status)
        self.send_json(status, obj, headers)
    def do_GET(self):
        self.handle_method("GET")
    def do_POST(self):
        self.handle_method("POST")
    def do_PATCH(self):
        self.handle_method("PATCH")

class Server(ThreadingHTTPServer):
    daemon_threads = True

with LOCK:
    reset()
server = Server(("127.0.0.1", 0), Handler)
print("PORT=%d" % server.server_address[1], flush=True)
server.serve_forever()
"##;

fn unique_dir(tag: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir = std::env::temp_dir().join(format!("gideon-conn-{tag}-{nanos}"));
    fs::create_dir_all(&dir).unwrap();
    dir
}

/// Loopback stub process; killed on drop.
struct Stub {
    child: Child,
    port: u16,
}

impl Stub {
    fn start(dir: &Path) -> Stub {
        let script = dir.join("stub.py");
        fs::write(&script, STUB).unwrap();
        Stub::spawn(&script, &[])
    }
    /// Runs one loopback fake (the inline GitHub stub, or a fixture under tests/fixtures) and reads its PORT line.
    fn spawn(script: &Path, args: &[&str]) -> Stub {
        let mut child = Command::new(PYTHON)
            .arg("-I")
            .arg(script)
            .args(args)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .expect("spawn stub");
        let mut line = String::new();
        BufReader::new(child.stdout.take().unwrap())
            .read_line(&mut line)
            .unwrap();
        let port = line
            .trim()
            .strip_prefix("PORT=")
            .and_then(|p| p.parse().ok())
            .unwrap_or_else(|| panic!("stub did not announce a port: {line:?}"));
        Stub { child, port }
    }
    /// Minimal HTTP/1.1 client: one request, one response (the stub closes each connection).
    fn http(
        &self,
        method: &str,
        path: &str,
        token: Option<&str>,
        extra: &[(&str, &str)],
        body: Option<&Value>,
    ) -> (u16, Value) {
        let addr = ("127.0.0.1", self.port)
            .to_socket_addrs()
            .unwrap()
            .next()
            .unwrap();
        let mut stream = TcpStream::connect(addr).unwrap();
        stream
            .set_read_timeout(Some(Duration::from_secs(30)))
            .unwrap();
        let raw = body.map(|b| b.to_string()).unwrap_or_default();
        let mut request = format!("{method} {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\nContent-Length: {}\r\nContent-Type: application/json\r\n", raw.len());
        if let Some(token) = token {
            request.push_str(&format!("Authorization: Bearer {token}\r\n"));
        }
        for (name, value) in extra {
            request.push_str(&format!("{name}: {value}\r\n"));
        }
        request.push_str("\r\n");
        request.push_str(&raw);
        stream.write_all(request.as_bytes()).unwrap();
        let mut text = String::new();
        stream.read_to_string(&mut text).unwrap();
        let status: u16 = text
            .split_whitespace()
            .nth(1)
            .and_then(|s| s.parse().ok())
            .unwrap_or(0);
        let body_text = text.split("\r\n\r\n").nth(1).unwrap_or("");
        (
            status,
            serde_json::from_str(body_text).unwrap_or(Value::Null),
        )
    }
    fn control(&self, name: &str, body: Value) -> Value {
        let (status, reply) = self.http(
            "POST",
            &format!("/__control/{name}"),
            None,
            &[],
            Some(&body),
        );
        assert_eq!(status, 200, "control {name}: {reply}");
        reply
    }
    fn state(&self) -> Value {
        self.http("GET", "/__control/state", None, &[], None).1
    }
    fn posts(&self, path: &str) -> u64 {
        self.state()["posts"][path].as_u64().unwrap_or(0)
    }
}

impl Drop for Stub {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

/// One Core process on a private root, killed on drop.
struct Core {
    root: PathBuf,
    child: Option<Child>,
    counter: u64,
    log: PathBuf,
}

impl Core {
    fn new(dir: &Path) -> Core {
        Core {
            root: dir.join("core"),
            child: None,
            counter: 0,
            log: dir.join("core.log"),
        }
    }
    fn start(&mut self, fakes: &[String], allow_public: bool) {
        self.start_with(fakes, allow_public, &[]);
    }
    fn start_with(&mut self, fakes: &[String], allow_public: bool, extra: &[&str]) {
        let log = fs::File::create(&self.log).unwrap();
        let mut command = Command::new(env!("CARGO_BIN_EXE_gideon-base"));
        command
            .arg("--root")
            .arg(&self.root)
            .arg("--plugin-python")
            .arg(PYTHON);
        for fake in fakes {
            command.arg("--connections-fake").arg(fake);
        }
        if allow_public {
            command.arg("--connections-allow-public");
        }
        command.args(extra);
        let child = command
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(log)
            .spawn()
            .expect("spawn Core");
        self.child = Some(child);
        let deadline = Instant::now() + Duration::from_secs(10);
        while Instant::now() < deadline {
            if self.root.join("core.sock").exists() && self.try_snap().is_some() {
                return;
            }
            thread::sleep(Duration::from_millis(20));
        }
        panic!(
            "Core did not start: {}",
            fs::read_to_string(&self.log).unwrap_or_default()
        );
    }
    fn call(&mut self, mut op: Value) -> Value {
        self.counter += 1;
        op["version"] = json!(1);
        op["request_id"] = json!(format!("c{}", self.counter));
        let mut stream = UnixStream::connect(self.root.join("core.sock")).expect("connect Core");
        stream
            .set_read_timeout(Some(Duration::from_secs(30)))
            .unwrap();
        let mut bytes = serde_json::to_vec(&op).unwrap();
        bytes.push(b'\n');
        stream.write_all(&bytes).unwrap();
        let mut line = String::new();
        BufReader::new(stream).read_line(&mut line).unwrap();
        serde_json::from_str(&line).unwrap_or_else(|_| panic!("bad response: {line}"))
    }
    fn snap(&mut self) -> Value {
        self.call(json!({"op": "snapshot"}))
    }
    fn try_snap(&mut self) -> Option<Value> {
        let stream = UnixStream::connect(self.root.join("core.sock")).ok()?;
        drop(stream);
        let snap = self.snap();
        (snap["code"] == "ok").then_some(snap)
    }
    fn revision(&mut self) -> u64 {
        self.snap()["connections"]["revision"].as_u64().unwrap()
    }
    fn add(&mut self, provider: &str, label: &str) -> String {
        let response =
            self.call(json!({"op": "connection_add", "provider": provider, "label": label}));
        assert_eq!(response["code"], "ok", "{response}");
        let snap = self.snap();
        snap["connections"]["items"]
            .as_array()
            .unwrap()
            .iter()
            .find(|item| item["label"] == label)
            .unwrap()["id"]
            .as_str()
            .unwrap()
            .to_owned()
    }
    fn item(&mut self, id: &str) -> Value {
        let snap = self.snap();
        snap["connections"]["items"]
            .as_array()
            .unwrap()
            .iter()
            .find(|item| item["id"] == id)
            .cloned()
            .unwrap_or(Value::Null)
    }
    fn wait_status(&mut self, id: &str, status: &str) -> Value {
        wait_until(&format!("status {status}"), || {
            self.item(id)["status"] == status
        });
        self.item(id)
    }
    /// Device login: connect, wait for the code, approve on the stub, consent to `consent`.
    fn login(&mut self, stub: &Stub, id: &str, consent: &[&str]) -> Value {
        let response = self.call(json!({"op": "connection_connect", "id": id}));
        assert_eq!(response["code"], "ok", "{response}");
        let pending = wait_until_value("device code", || {
            let item = self.item(id);
            (item["user_code"].is_string()).then_some(item)
        });
        assert_eq!(pending["status"], "connecting");
        let device = stub.state()["last_device_code"]
            .as_str()
            .unwrap()
            .to_owned();
        let requested: Vec<String> = pending["pending_scopes"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| s.as_str().unwrap().to_owned())
            .collect();
        stub.control(
            "approve",
            json!({"device_code": device, "scopes": requested}),
        );
        let response = self.call(json!({"op": "connection_consent", "id": id, "scopes": consent}));
        assert_eq!(response["code"], "ok", "{response}");
        self.wait_status(id, "connected")
    }
    /// Read or write call; returns the Core response.
    fn op(&mut self, id: &str, operation: &str, args: Value) -> Value {
        self.call(json!({"op": "connection_call", "id": id, "operation": operation, "args": args}))
    }
    fn last_call(&mut self) -> Value {
        self.snap()["connections"]["last_call"].clone()
    }
    fn proposal(&mut self, proposal_id: &str) -> Value {
        let snap = self.snap();
        snap["tool_proposals"]
            .as_array()
            .unwrap()
            .iter()
            .find(|p| p["proposal_id"] == proposal_id)
            .cloned()
            .unwrap_or(Value::Null)
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

fn wait_until(what: &str, mut check: impl FnMut() -> bool) {
    let deadline = Instant::now() + Duration::from_secs(15);
    while !check() {
        assert!(Instant::now() < deadline, "timed out waiting for {what}");
        thread::sleep(Duration::from_millis(40));
    }
}

fn wait_until_value<T>(what: &str, mut check: impl FnMut() -> Option<T>) -> T {
    let deadline = Instant::now() + Duration::from_secs(15);
    loop {
        if let Some(value) = check() {
            return value;
        }
        assert!(Instant::now() < deadline, "timed out waiting for {what}");
        thread::sleep(Duration::from_millis(40));
    }
}

/// Requests the Core made to the stub (control endpoints excluded).
fn api_requests(stub: &Stub) -> usize {
    stub.state()["requests"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| !r["path"].as_str().unwrap_or("").starts_with("/__control"))
        .count()
}

/// Reads the repo once so its visibility is known: a write to a private repo needs no public approval.
fn learn_private(core: &mut Core, id: &str) {
    assert_eq!(
        core.op(id, "repo.get", json!({"repo": "demo/private-repo"}))["code"],
        "ok"
    );
    wait_until("visibility learned", || core.last_call()["outcome"] == "ok");
}

fn fake_arg(stub: &Stub) -> String {
    format!("github=http://127.0.0.1:{}", stub.port)
}

fn start_core(dir: &Path, stub: &Stub, allow_public: bool) -> Core {
    let mut core = Core::new(dir);
    core.start(&[fake_arg(stub)], allow_public);
    core
}

/// Private temp directory removed when the test ends (after its Core and stub are killed).
struct Scratch(PathBuf);

impl std::ops::Deref for Scratch {
    type Target = PathBuf;
    fn deref(&self) -> &PathBuf {
        &self.0
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn fresh() -> (std::sync::MutexGuard<'static, ()>, Scratch) {
    let guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    (guard, Scratch(unique_dir("e1")))
}

#[test]
fn real_backend_is_refused_without_a_fake_and_fakes_need_the_broker_python() {
    let (_guard, dir) = fresh();
    let mut core = Core::new(&dir);
    core.start(&[], false);
    let id = core.add("github", "sem fake");
    let response = core.call(json!({"op": "connection_connect", "id": id}));
    assert_eq!(response["code"], "real_backend_unsupported");
    assert_eq!(core.item(&id)["status"], "disconnected");
    assert_eq!(core.item(&id)["fake"], json!(false));
    let refused = Command::new(env!("CARGO_BIN_EXE_gideon-base"))
        .arg("--root")
        .arg(dir.join("other"))
        .arg("--connections-fake")
        .arg("github=http://127.0.0.1:9")
        .output()
        .unwrap();
    assert!(
        !refused.status.success(),
        "fake without --plugin-python must refuse"
    );
    let bad = Command::new(env!("CARGO_BIN_EXE_gideon-base"))
        .arg("--root")
        .arg(dir.join("other2"))
        .arg("--plugin-python")
        .arg(PYTHON)
        .arg("--connections-fake")
        .arg("github=http://example.com")
        .output()
        .unwrap();
    assert!(!bad.status.success(), "non-loopback fake must refuse");
}

#[test]
fn connect_flow_consents_per_scope_and_keeps_only_granted_scopes() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "pessoal");
    assert_eq!(core.item(&id)["status"], "disconnected");
    let response =
        core.call(json!({"op": "connection_consent", "id": id, "scopes": ["repo:read"]}));
    assert_eq!(response["code"], "invalid_state");
    let snap = core.snap();
    assert_eq!(core.item(&id)["fake"], json!(true));
    let provider = snap["connections"]["providers"]
        .as_array()
        .unwrap()
        .iter()
        .find(|p| p["id"] == "github")
        .unwrap()
        .clone();
    assert_eq!(provider["scopes"].as_array().unwrap().len(), 3);
    assert!(provider["operations"]
        .as_array()
        .unwrap()
        .iter()
        .any(|o| o["name"] == "issues.create" && o["risk"] == "write"));
    assert!(provider["operations"]
        .as_array()
        .unwrap()
        .iter()
        .any(|o| o["name"] == "pulls.comment" && o["risk"] == "public"));

    let connected = core.login(&stub, &id, &["repo:read", "issues:write"]);
    assert_eq!(
        connected["granted_scopes"],
        json!(["repo:read", "issues:write"])
    );
    assert_eq!(connected["account_ref"], "demo-user");
    assert!(
        connected.get("user_code").is_none(),
        "code is cleared once connected"
    );

    let response =
        core.call(json!({"op": "connection_consent", "id": id, "scopes": ["pulls:write"]}));
    assert_eq!(response["code"], "invalid_state");
    let _ = core.call(json!({"op": "connection_disconnect", "id": id}));
    assert_eq!(core.item(&id)["status"], "disconnected");
}

#[test]
fn consent_rejects_scopes_the_device_did_not_request() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "consent");
    assert_eq!(
        core.call(json!({"op": "connection_connect", "id": id}))["code"],
        "ok"
    );
    wait_until("device code", || core.item(&id)["user_code"].is_string());
    assert_eq!(
        core.call(json!({"op": "connection_consent", "id": id, "scopes": ["admin:org"]}))["code"],
        "scope_not_requested"
    );
    assert_eq!(
        core.call(json!({"op": "connection_consent", "id": id, "scopes": []}))["code"],
        "invalid_args"
    );
    assert_eq!(
        core.call(json!({"op": "connection_connect", "id": id}))["code"],
        "already_connecting"
    );
}

#[test]
fn scope_not_granted_is_refused_without_any_network_request() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "so leitura");
    core.login(&stub, &id, &["repo:read"]);
    let before = api_requests(&stub);
    let response = core.op(
        &id,
        "issues.create",
        json!({"repo": "demo/private-repo", "title": "x"}),
    );
    assert_eq!(response["code"], "scope_not_granted");
    let read = core.op(&id, "repo.get", json!({"repo": "demo/private-repo"}));
    assert_eq!(read["code"], "ok");
    wait_until("read settled", || core.last_call()["outcome"] == "ok");
    let after = api_requests(&stub);
    assert_eq!(after, before + 1, "only the read reached the stub");
    assert_eq!(stub.posts("/api/repos/demo/private-repo/issues"), 0);
}

#[test]
fn reads_run_now_and_writes_wait_for_the_approval_card() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "trabalho");
    core.login(&stub, &id, &["repo:read", "issues:write"]);

    let read = core.op(&id, "repo.get", json!({"repo": "demo/private-repo"}));
    assert_eq!(read["code"], "ok");
    wait_until("read finished", || core.last_call()["outcome"] == "ok");
    assert_eq!(core.last_call()["operation"], "repo.get");

    let pending = core.op(
        &id,
        "issues.create",
        json!({"repo": "demo/private-repo", "title": "Bug de voz", "body": "passos"}),
    );
    assert_eq!(pending["code"], "pending_approval", "{pending}");
    let proposal_id = core.last_call()["proposal_id"].as_str().unwrap().to_owned();
    let card = core.proposal(&proposal_id);
    assert_eq!(card["state"], "pending");
    assert_eq!(card["kind"], "connection");
    assert_eq!(card["tool"], "conn:github.issues.create");
    assert_eq!(
        stub.posts("/api/repos/demo/private-repo/issues"),
        0,
        "nothing sent before approval"
    );

    let decided = core
        .call(json!({"op": "tool_decide", "proposal_id": proposal_id, "decision": "authorize"}));
    assert_eq!(decided["code"], "ok", "{decided}");
    let done = core.wait_proposal_done(&proposal_id);
    assert_eq!(done["state"], "executed", "{done}");
    assert_eq!(stub.posts("/api/repos/demo/private-repo/issues"), 1);
    assert_eq!(core.last_call()["outcome"], "ok");
}

impl Core {
    fn wait_proposal_done(&mut self, proposal_id: &str) -> Value {
        wait_until("proposal settled", || {
            !matches!(
                self.proposal(proposal_id)["state"].as_str(),
                Some("pending" | "authorized") | None
            )
        });
        self.proposal(proposal_id)
    }
}

#[test]
fn results_are_projected_to_the_descriptor_fields() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "projecao");
    core.login(&stub, &id, &["repo:read", "issues:write"]);
    learn_private(&mut core, &id);
    let pending = core.op(
        &id,
        "issues.create",
        json!({"repo": "demo/private-repo", "title": "p"}),
    );
    assert_eq!(pending["code"], "pending_approval");
    let proposal_id = core.last_call()["proposal_id"].as_str().unwrap().to_owned();
    core.call(json!({"op": "tool_decide", "proposal_id": proposal_id, "decision": "authorize"}));
    let done = core.wait_proposal_done(&proposal_id);
    assert_eq!(done["state"], "executed");
    let result: Value = serde_json::from_str(done["result"].as_str().unwrap()).unwrap();
    let mut keys: Vec<&str> = result
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    keys.sort_unstable();
    assert_eq!(keys, ["number", "public", "state", "title", "url"]);
    assert!(
        !done.to_string().contains("SECRET-NOTE"),
        "unlisted field leaked"
    );
}

#[test]
fn public_operations_wait_and_never_run_without_allow_public() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "publico");
    core.login(&stub, &id, &["repo:read", "pulls:write", "issues:write"]);

    let pending = core.op(
        &id,
        "pulls.comment",
        json!({"repo": "demo/private-repo", "number": 1, "body": "oi"}),
    );
    assert_eq!(pending["code"], "pending_approval");
    let comment_id = core.last_call()["proposal_id"].as_str().unwrap().to_owned();
    let refused =
        core.call(json!({"op": "tool_decide", "proposal_id": comment_id, "decision": "authorize"}));
    assert_eq!(refused["code"], "public_disabled");
    assert_eq!(
        core.proposal(&comment_id)["state"],
        "pending",
        "refusal keeps the proposal pending"
    );
    assert_eq!(stub.state()["comments"], 0);

    // Unknown visibility counts as public: a repo never read is refused the same way.
    let unknown = core.op(
        &id,
        "issues.create",
        json!({"repo": "demo/public-repo", "title": "t"}),
    );
    assert_eq!(unknown["code"], "pending_approval");
    let issue_id = core.last_call()["proposal_id"].as_str().unwrap().to_owned();
    assert_eq!(
        core.proposal(&issue_id)["tool"],
        "conn:github.issues.create"
    );
    assert_eq!(
        core.call(json!({"op": "tool_decide", "proposal_id": issue_id, "decision": "authorize"}))
            ["code"],
        "public_disabled"
    );
    assert_eq!(stub.posts("/api/repos/demo/public-repo/issues"), 0);
    let denied =
        core.call(json!({"op": "tool_decide", "proposal_id": comment_id, "decision": "deny"}));
    assert_eq!(denied["code"], "ok");
    assert_eq!(core.proposal(&comment_id)["state"], "denied");
}

#[test]
fn public_operation_executes_after_approval_when_allowed_for_tests() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, true);
    let id = core.add("github", "publico liberado");
    core.login(&stub, &id, &["repo:read", "pulls:write"]);
    let pending = core.op(
        &id,
        "pulls.comment",
        json!({"repo": "demo/private-repo", "number": 1, "body": "oi"}),
    );
    assert_eq!(pending["code"], "pending_approval");
    let proposal_id = core.last_call()["proposal_id"].as_str().unwrap().to_owned();
    assert_eq!(
        core.call(
            json!({"op": "tool_decide", "proposal_id": proposal_id, "decision": "authorize"})
        )["code"],
        "ok"
    );
    assert_eq!(core.wait_proposal_done(&proposal_id)["state"], "executed");
    assert_eq!(stub.state()["comments"], 1);
}

#[test]
fn expired_token_is_refreshed_once_and_the_call_succeeds() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "expira");
    core.login(&stub, &id, &["repo:read"]);
    stub.control("expire_access", json!({}));
    let response = core.op(&id, "repo.get", json!({"repo": "demo/private-repo"}));
    assert_eq!(response["code"], "ok");
    wait_until("call after refresh", || core.last_call()["outcome"] == "ok");
    assert_eq!(core.item(&id)["status"], "connected");
    let posts = stub.state()["requests"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["path"] == "/login/oauth/refresh")
        .count();
    assert_eq!(posts, 1, "exactly one refresh");
}

#[test]
fn rejected_refresh_moves_the_account_to_reauth_required() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "reauth");
    core.login(&stub, &id, &["repo:read"]);
    stub.control("expire_access", json!({}));
    stub.control("invalidate_refresh", json!({}));
    assert_eq!(
        core.op(&id, "repo.get", json!({"repo": "demo/private-repo"}))["code"],
        "ok"
    );
    wait_until("reauth", || core.item(&id)["status"] == "reauth_required");
    wait_until("failed call", || {
        core.last_call()["code"] == "reauth_required"
    });
    assert_eq!(
        core.op(&id, "repo.get", json!({"repo": "demo/private-repo"}))["code"],
        "reauth_required"
    );
}

#[test]
fn provider_failure_during_refresh_marks_the_account_expired() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "expirado");
    core.login(&stub, &id, &["repo:read"]);
    stub.control("expire_access", json!({}));
    stub.control("refresh_mode", json!({"mode": "503"}));
    assert_eq!(
        core.op(&id, "repo.get", json!({"repo": "demo/private-repo"}))["code"],
        "ok"
    );
    wait_until("expired", || core.item(&id)["status"] == "expired");
    assert_eq!(core.last_call()["code"], "expired");
    stub.control("refresh_mode", json!({"mode": "ok"}));
    assert_eq!(
        core.op(&id, "repo.get", json!({"repo": "demo/private-repo"}))["code"],
        "expired"
    );
}

#[test]
fn revoke_clears_local_secrets_and_stops_calls() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "revoga");
    core.login(&stub, &id, &["repo:read"]);
    assert_eq!(
        core.call(json!({"op": "connection_revoke", "id": id}))["code"],
        "ok"
    );
    assert_eq!(core.item(&id)["status"], "disconnected");
    wait_until("revoke sent", || stub.state()["revoked_calls"] == 1);
    assert_eq!(
        core.op(&id, "repo.get", json!({"repo": "demo/private-repo"}))["code"],
        "not_connected"
    );
    assert_eq!(
        core.call(json!({"op": "connection_remove", "id": id}))["code"],
        "ok"
    );
    assert_eq!(core.snap()["connections"]["items"], json!([]));
}

#[test]
fn rate_limit_reports_retry_after_and_keeps_the_account_connected() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "limite");
    core.login(&stub, &id, &["repo:read"]);
    stub.control("rate_limit", json!({"n": 1, "retry_after": 7}));
    assert_eq!(
        core.op(&id, "repo.get", json!({"repo": "demo/private-repo"}))["code"],
        "ok"
    );
    wait_until("rate limited", || {
        core.last_call()["code"] == "rate_limited"
    });
    assert_eq!(core.last_call()["retry_after"], 7);
    assert_eq!(core.item(&id)["status"], "connected");
}

#[test]
fn account_mismatch_marks_the_account_as_error() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "conta");
    core.login(&stub, &id, &["repo:read"]);
    stub.control("set_account", json!({"name": "outra-conta"}));
    assert_eq!(
        core.op(&id, "repo.get", json!({"repo": "demo/private-repo"}))["code"],
        "ok"
    );
    wait_until("mismatch", || {
        core.last_call()["code"] == "account_mismatch"
    });
    assert_eq!(core.item(&id)["status"], "error");
}

#[test]
fn timeouts_are_reported_within_the_call_budget() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "lento");
    core.login(&stub, &id, &["repo:read"]);
    let started = Instant::now();
    assert_eq!(
        core.op(&id, "repo.get", json!({"repo": "demo/sleep-repo"}))["code"],
        "ok"
    );
    wait_until("timeout", || core.last_call()["code"] == "timeout");
    assert!(
        started.elapsed() < Duration::from_secs(12),
        "budget is 8 s per call"
    );
}

/// `issues.create` has no natural key and the real GitHub API ignores `Idempotency-Key`: a 500 after the
/// create is never retried, so the failure is reported once and no second issue is posted.
/// (scripts/verify_e1_connections.py still expects the old retry; the coordinator updates that gate.)
#[test]
fn issues_create_is_not_retried_after_a_server_error() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "retry");
    core.login(&stub, &id, &["repo:read", "issues:write"]);
    learn_private(&mut core, &id);
    stub.control("fail_after_create", json!({"n": 1}));
    let pending = core.op(
        &id,
        "issues.create",
        json!({"repo": "demo/private-repo", "title": "uma vez"}),
    );
    assert_eq!(pending["code"], "pending_approval");
    let proposal_id = core.last_call()["proposal_id"].as_str().unwrap().to_owned();
    core.call(json!({"op": "tool_decide", "proposal_id": proposal_id, "decision": "authorize"}));
    let done = core.wait_proposal_done(&proposal_id);
    assert_eq!(done["state"], "failed", "{done}");
    assert_eq!(done["reason"], "provider_error");
    let state = stub.state();
    assert_eq!(
        state["posts"]["/api/repos/demo/private-repo/issues"], 1,
        "no retry: the descriptor is not idempotent"
    );
}

#[test]
fn non_idempotent_failures_are_not_retried() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, true);
    let id = core.add("github", "sem retry");
    core.login(&stub, &id, &["repo:read", "pulls:write"]);
    stub.control("fail_after_create", json!({"n": 1}));
    let pending = core.op(
        &id,
        "pulls.comment",
        json!({"repo": "demo/private-repo", "number": 1, "body": "x"}),
    );
    assert_eq!(pending["code"], "pending_approval");
    let proposal_id = core.last_call()["proposal_id"].as_str().unwrap().to_owned();
    core.call(json!({"op": "tool_decide", "proposal_id": proposal_id, "decision": "authorize"}));
    let done = core.wait_proposal_done(&proposal_id);
    assert_eq!(done["state"], "failed");
    assert_eq!(done["reason"], "provider_error");
    assert_eq!(
        stub.posts("/api/repos/demo/private-repo/pulls/1/comments"),
        1,
        "no retry without a key"
    );
}

#[test]
fn network_budget_refuses_the_31st_call_in_a_minute_without_a_request() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "orcamento");
    core.login(&stub, &id, &["repo:read"]);
    for _ in 0..30 {
        assert_eq!(
            core.op(&id, "repo.get", json!({"repo": "demo/private-repo"}))["code"],
            "ok"
        );
        wait_until("call settled", || core.last_call()["outcome"] == "ok");
    }
    let before = api_requests(&stub);
    assert_eq!(
        core.op(&id, "repo.get", json!({"repo": "demo/private-repo"}))["code"],
        "rate_limited"
    );
    assert!(core.last_call()["retry_after"].as_u64().unwrap() >= 1);
    thread::sleep(Duration::from_millis(200));
    assert_eq!(api_requests(&stub), before);
}

fn refreshes(stub: &Stub) -> usize {
    stub.state()["requests"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["path"] == "/login/oauth/refresh")
        .count()
}

/// The account is disconnected while its refresh is in flight: the refresh reply stores nothing, the
/// proposal it carries fails as `not_connected`, and the account stays disconnected.
#[test]
fn disconnect_during_a_refresh_fails_the_carried_call_and_resurrects_nothing() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "desliga");
    core.login(&stub, &id, &["repo:read", "issues:write"]);
    learn_private(&mut core, &id);
    stub.control("expire_access", json!({}));
    // The call's 401 answers after 3 s; the refresh that follows runs from 3 s to 6 s.
    stub.control("delay", json!({"n": 2, "seconds": 3}));
    let pending = core.op(
        &id,
        "issues.create",
        json!({"repo": "demo/private-repo", "title": "tarde"}),
    );
    assert_eq!(pending["code"], "pending_approval");
    let pid = core.last_call()["proposal_id"].as_str().unwrap().to_owned();
    core.call(json!({"op": "tool_decide", "proposal_id": pid, "decision": "authorize"}));
    thread::sleep(Duration::from_millis(4500));
    assert_eq!(
        core.call(json!({"op": "connection_disconnect", "id": id}))["code"],
        "ok"
    );
    let done = core.wait_proposal_done(&pid);
    assert_eq!(done["state"], "failed", "{done}");
    assert_eq!(done["reason"], "not_connected");
    wait_until("refresh reply arrived", || refreshes(&stub) == 1);
    thread::sleep(Duration::from_millis(300));
    assert_eq!(core.item(&id)["status"], "disconnected");
    assert_eq!(
        core.op(&id, "repo.get", json!({"repo": "demo/private-repo"}))["code"],
        "not_connected"
    );
    assert!(
        stub.state()["issues"]["demo/private-repo"].is_null(),
        "no issue was created: the call never ran after the disconnect"
    );
}

/// Trust of the tools is not a live discover: after a reconnect `mcp.call` waits for a new `mcp.discover`.
#[test]
fn mcp_calls_wait_for_a_discover_after_a_reconnect() {
    let (_guard, dir) = fresh();
    let mut core = mcp_core(&dir, "good", false);
    let id = core.add("mcp", "reconecta");
    mcp_login(&mut core, &id, &["mcp.discover", "mcp.call"]);
    mcp_discover(&mut core, &id);
    assert_eq!(
        core.call(json!({"op": "connection_disconnect", "id": id}))["code"],
        "ok"
    );
    wait_until("server gone after disconnect", || mcp_servers().is_empty());
    mcp_login(&mut core, &id, &["mcp.discover", "mcp.call"]);
    let args = json!({"tool": "echo_note", "args": {"text": "oi"}});
    assert_eq!(
        core.op(&id, "mcp.call", args.clone())["code"],
        "tool_not_verified"
    );
    mcp_discover(&mut core, &id);
    let pid = mcp_call_card(&mut core, &id, "echo_note", json!({"text": "oi"}), "write");
    assert!(core.proposal(&pid)["result"].is_null());
}

#[test]
fn snapshot_ledger_audit_and_logs_never_hold_tokens() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "segredo");
    core.login(&stub, &id, &["repo:read", "issues:write"]);
    assert_eq!(
        core.op(&id, "repo.get", json!({"repo": "demo/private-repo"}))["code"],
        "ok"
    );
    wait_until("read", || core.last_call()["outcome"] == "ok");
    let state = stub.state();
    let access = state["last_access_token"].as_str().unwrap().to_owned();
    let refresh = state["last_refresh_token"].as_str().unwrap().to_owned();
    let device = state["last_device_code"].as_str().unwrap().to_owned();
    let snapshot = core.snap().to_string();
    assert!(
        !snapshot.contains(&access) && !snapshot.contains(&refresh) && !snapshot.contains(&device)
    );
    assert!(!snapshot.contains("SECRET-NOTE"));

    let root = core.root.clone();
    let ledger = fs::read_to_string(root.join("connections.json")).unwrap();
    assert!(!ledger.contains(&access) && !ledger.contains(&refresh) && !ledger.contains(&device));
    let secrets = fs::read_to_string(root.join("secrets.json")).unwrap();
    assert!(
        secrets.contains(&access),
        "the vault holds the access token"
    );
    assert!(secrets.contains(&format!("conn:{id}:access")));
    let audit = fs::read_to_string(root.join("audit.log")).unwrap();
    assert!(audit.contains("connection_call"));
    assert!(!audit.contains(&access) && !audit.contains(&refresh) && !audit.contains(&id));
    let log = fs::read_to_string(&core.log).unwrap();
    assert!(!log.contains(&access) && !log.contains(&refresh));
    for name in ["connections.json", "secrets.json"] {
        let mode = fs::metadata(root.join(name)).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o600, "{name} must be private");
    }
}

#[test]
fn disconnect_leaves_the_core_and_its_snapshot_working() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "desligar");
    core.login(&stub, &id, &["repo:read"]);
    let before = core.snap();
    assert_eq!(
        core.call(json!({"op": "connection_disconnect", "id": id}))["code"],
        "ok"
    );
    let after = core.snap();
    assert_eq!(after["code"], "ok");
    assert_eq!(after["llm"], before["llm"]);
    assert_eq!(
        after["configuration_status"],
        before["configuration_status"]
    );
    assert_eq!(after["connections"]["items"][0]["status"], "disconnected");
    assert_eq!(
        core.op(&id, "repo.get", json!({"repo": "demo/private-repo"}))["code"],
        "not_connected"
    );
    assert_eq!(core.call(json!({"op": "snapshot"}))["code"], "ok");
}

#[test]
fn ledger_revision_is_a_cas_on_mutations() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let revision = core.revision();
    let response = core.call(
        json!({"op": "connection_add", "provider": "github", "label": "a", "revision": revision}),
    );
    assert_eq!(response["code"], "ok");
    let stale = core.call(
        json!({"op": "connection_add", "provider": "github", "label": "b", "revision": revision}),
    );
    assert_eq!(stale["code"], "stale_connection_revision");
    assert_eq!(
        core.call(json!({"op": "connection_add", "provider": "nope", "label": "b"}))["code"],
        "invalid_provider"
    );
    assert_eq!(
        core.call(json!({"op": "connection_add", "provider": "github", "label": ""}))["code"],
        "invalid_label"
    );
    for n in 0..7 {
        assert_eq!(
            core.call(
                json!({"op": "connection_add", "provider": "github", "label": format!("c{n}")})
            )["code"],
            "ok"
        );
    }
    assert_eq!(
        core.call(json!({"op": "connection_add", "provider": "github", "label": "nono"}))["code"],
        "connection_limit"
    );
}

#[test]
fn unknown_operations_and_bad_arguments_never_reach_the_network() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let id = core.add("github", "validacao");
    core.login(&stub, &id, &["repo:read", "issues:write"]);
    let before = api_requests(&stub);
    assert_eq!(
        core.op(&id, "repos.delete", json!({}))["code"],
        "unknown_operation"
    );
    assert_eq!(
        core.op(&id, "repo.get", json!({"repo": "../etc"}))["code"],
        "invalid_args"
    );
    assert_eq!(
        core.op(
            &id,
            "repo.get",
            json!({"repo": "demo/private-repo", "extra": 1})
        )["code"],
        "invalid_args"
    );
    assert_eq!(
        core.op(
            &id,
            "pulls.get",
            json!({"repo": "demo/private-repo", "number": 0})
        )["code"],
        "invalid_args"
    );
    assert_eq!(
        core.op(
            "conn_missing",
            "repo.get",
            json!({"repo": "demo/private-repo"})
        )["code"],
        "unknown_connection"
    );
    thread::sleep(Duration::from_millis(100));
    assert_eq!(api_requests(&stub), before);
}

// ---- S5 E2.2 google (fixture tests/fixtures/connections/google_server.py) ----

/// Loopback Google fake (Gmail, Calendar, Drive). Its request counter ignores control calls.
fn google_stub() -> Stub {
    let script =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/connections/google_server.py");
    Stub::spawn(&script, &["--port", "0"])
}

fn google_core(dir: &Path, stub: &Stub, allow_public: bool) -> Core {
    let mut core = Core::new(dir);
    core.start(
        &[format!("google=http://127.0.0.1:{}", stub.port)],
        allow_public,
    );
    core
}

fn google_requests(stub: &Stub) -> u64 {
    stub.state()["requests"].as_u64().unwrap()
}

/// Device login against the Google fake: approval by user code, then consent to `consent`.
fn google_login(core: &mut Core, stub: &Stub, id: &str, consent: &[&str]) -> Value {
    assert_eq!(
        core.call(json!({"op": "connection_connect", "id": id}))["code"],
        "ok"
    );
    let pending = wait_until_value("google device code", || {
        let item = core.item(id);
        (item["user_code"].is_string()).then_some(item)
    });
    assert_eq!(pending["pending_scopes"].as_array().unwrap().len(), 7);
    stub.control(
        "approve",
        json!({"user_code": pending["user_code"], "scopes": pending["pending_scopes"]}),
    );
    wait_until("consent accepted", || {
        core.call(json!({"op": "connection_consent", "id": id, "scopes": consent}))["code"] == "ok"
    });
    core.wait_status(id, "connected")
}

/// A write or public call waits for its approval card; returns the proposal id of that card.
fn google_card(core: &mut Core, id: &str, operation: &str, args: Value) -> String {
    let code = core.op(id, operation, args)["code"].clone();
    assert_eq!(code, "pending_approval", "{operation}");
    let pid = core.last_call()["proposal_id"].as_str().unwrap().to_owned();
    let card = core.proposal(&pid);
    assert_eq!(card["kind"], "connection");
    assert_eq!(card["tool"], format!("conn:google.{operation}"));
    pid
}

#[test]
fn google_descriptor_is_fixed_in_the_snapshot_and_marked_fake() {
    let (_guard, dir) = fresh();
    let stub = google_stub();
    let mut core = google_core(&dir, &stub, false);
    let id = core.add("google", "descricao");
    assert_eq!(core.item(&id)["fake"], json!(true));
    let snap = core.snap();
    let provider = snap["connections"]["providers"]
        .as_array()
        .unwrap()
        .iter()
        .find(|p| p["id"] == "google")
        .unwrap()
        .clone();
    let scopes: Vec<&str> = provider["scopes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| s["id"].as_str().unwrap())
        .collect();
    assert_eq!(
        scopes,
        [
            "gmail.read",
            "gmail.send",
            "gmail.delete",
            "calendar.read",
            "calendar.write",
            "drive.read",
            "drive.write"
        ]
    );
    let risk = |name: &str| -> String {
        provider["operations"]
            .as_array()
            .unwrap()
            .iter()
            .find(|o| o["name"] == name)
            .unwrap()["risk"]
            .as_str()
            .unwrap()
            .to_owned()
    };
    assert_eq!(risk("gmail.messages.list"), "read");
    assert_eq!(risk("gmail.send"), "public");
    assert_eq!(risk("gmail.messages.delete"), "destructive");
    assert_eq!(risk("calendar.events.create"), "write");
    assert_eq!(risk("drive.files.create"), "write");
    assert_eq!(provider["operations"].as_array().unwrap().len(), 7);
}

#[test]
fn google_partial_consent_keeps_only_the_ticked_scopes_and_refuses_unrequested_ones() {
    let (_guard, dir) = fresh();
    let stub = google_stub();
    let mut core = google_core(&dir, &stub, false);
    let id = core.add("google", "parcial");
    assert_eq!(
        core.call(json!({"op": "connection_connect", "id": id}))["code"],
        "ok"
    );
    let pending = wait_until_value("google device code", || {
        let item = core.item(&id);
        (item["user_code"].is_string()).then_some(item)
    });
    stub.control(
        "approve",
        json!({"user_code": pending["user_code"], "scopes": pending["pending_scopes"]}),
    );
    assert_eq!(
        core.call(json!({"op": "connection_consent", "id": id, "scopes": ["admin:everything"]}))
            ["code"],
        "scope_not_requested"
    );
    assert_eq!(
        core.call(json!({"op": "connection_consent", "id": id, "scopes": []}))["code"],
        "invalid_args"
    );
    let consent = ["gmail.read", "calendar.read"];
    wait_until("consent accepted", || {
        core.call(json!({"op": "connection_consent", "id": id, "scopes": consent}))["code"] == "ok"
    });
    let connected = core.wait_status(&id, "connected");
    let mut granted: Vec<String> = connected["granted_scopes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| s.as_str().unwrap().to_owned())
        .collect();
    granted.sort();
    assert_eq!(granted, ["calendar.read", "gmail.read"]);
    assert_eq!(connected["account_ref"], "demo-user");
}

#[test]
fn google_read_write_and_delete_scopes_are_separate_and_refused_before_the_network() {
    let (_guard, dir) = fresh();
    let stub = google_stub();
    let mut core = google_core(&dir, &stub, false);
    let id = core.add("google", "so leitura");
    google_login(&mut core, &stub, &id, &["gmail.read", "calendar.read"]);
    let before = google_requests(&stub);
    assert_eq!(
        core.op(
            &id,
            "gmail.send",
            json!({"to": "bob@example.test", "subject": "s", "body": "b"})
        )["code"],
        "scope_not_granted"
    );
    assert_eq!(
        core.op(&id, "gmail.messages.delete", json!({"id": "m1"}))["code"],
        "scope_not_granted"
    );
    assert_eq!(
        core.op(&id, "drive.files.create", json!({"name": "a.txt"}))["code"],
        "scope_not_granted"
    );
    assert_eq!(
        core.op(
            &id,
            "calendar.events.create",
            json!({"title": "t", "start": "2026-10-20T09:00:00Z", "end": "2026-10-20T10:00:00Z"})
        )["code"],
        "scope_not_granted"
    );
    assert_eq!(
        google_requests(&stub),
        before,
        "refused calls reach no server"
    );
    assert_eq!(stub.state()["messages"].as_array().unwrap().len(), 2);
    assert_eq!(core.op(&id, "gmail.messages.list", json!({}))["code"], "ok");
    wait_until("list finished", || core.last_call()["outcome"] == "ok");
    assert_eq!(google_requests(&stub), before + 1);
}

#[test]
fn google_send_waits_for_approval_and_is_refused_without_the_public_switch() {
    let (_guard, dir) = fresh();
    let stub = google_stub();
    let mut core = google_core(&dir, &stub, false);
    let id = core.add("google", "envio");
    google_login(&mut core, &stub, &id, &["gmail.send"]);
    let pid = google_card(
        &mut core,
        &id,
        "gmail.send",
        json!({"to": "bob@example.test", "subject": "oi", "body": "corpo"}),
    );
    assert_eq!(core.proposal(&pid)["risk"], "public");
    let refused =
        core.call(json!({"op": "tool_decide", "proposal_id": pid, "decision": "authorize"}));
    assert_eq!(refused["code"], "public_disabled", "{refused}");
    assert_eq!(core.proposal(&pid)["state"], "pending");
    assert!(stub.state()["sent"].as_array().unwrap().is_empty());
    let denied = core.call(json!({"op": "tool_decide", "proposal_id": pid, "decision": "deny"}));
    assert_eq!(denied["code"], "ok");
    assert!(stub.state()["sent"].as_array().unwrap().is_empty());
}

#[test]
fn google_delete_is_destructive_and_never_runs_without_the_public_switch() {
    let (_guard, dir) = fresh();
    let stub = google_stub();
    let mut core = google_core(&dir, &stub, false);
    let id = core.add("google", "apagar");
    google_login(&mut core, &stub, &id, &["gmail.read", "gmail.delete"]);
    let pid = google_card(&mut core, &id, "gmail.messages.delete", json!({"id": "m1"}));
    assert_eq!(core.proposal(&pid)["risk"], "destructive");
    let refused =
        core.call(json!({"op": "tool_decide", "proposal_id": pid, "decision": "authorize"}));
    assert_eq!(refused["code"], "public_disabled", "{refused}");
    thread::sleep(Duration::from_millis(100));
    assert_eq!(
        stub.state()["messages"].as_array().unwrap().len(),
        2,
        "m1 still there"
    );
    core.call(json!({"op": "tool_decide", "proposal_id": pid, "decision": "deny"}));
}

#[test]
fn google_destructive_and_send_run_only_after_approval_with_the_switch() {
    let (_guard, dir) = fresh();
    let stub = google_stub();
    let mut core = google_core(&dir, &stub, true);
    let id = core.add("google", "apagar liberado");
    google_login(
        &mut core,
        &stub,
        &id,
        &["gmail.read", "gmail.delete", "gmail.send"],
    );
    let pid = google_card(&mut core, &id, "gmail.messages.delete", json!({"id": "m1"}));
    assert_eq!(
        core.call(json!({"op": "tool_decide", "proposal_id": pid, "decision": "authorize"}))
            ["code"],
        "ok"
    );
    let done = core.wait_proposal_done(&pid);
    assert_eq!(done["state"], "executed", "{done}");
    assert_eq!(
        serde_json::from_str::<Value>(done["result"].as_str().unwrap()).unwrap(),
        json!({"id": "m1", "deleted": true})
    );
    let messages = stub.state()["messages"].clone();
    assert_eq!(
        messages.as_array().unwrap().len(),
        1,
        "m1 removed on the fake"
    );
    let sid = google_card(
        &mut core,
        &id,
        "gmail.send",
        json!({"to": "bob@example.test", "subject": "oi", "body": "corpo"}),
    );
    assert!(
        stub.state()["sent"].as_array().unwrap().is_empty(),
        "nothing sent before approval"
    );
    core.call(json!({"op": "tool_decide", "proposal_id": sid, "decision": "authorize"}));
    let sent = core.wait_proposal_done(&sid);
    assert_eq!(sent["state"], "executed", "{sent}");
    let result: Value = serde_json::from_str(sent["result"].as_str().unwrap()).unwrap();
    let mut keys: Vec<&str> = result
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    keys.sort_unstable();
    assert_eq!(
        keys,
        ["id", "subject", "to"],
        "no body in the sent projection"
    );
    assert_eq!(stub.state()["sent"].as_array().unwrap().len(), 1);
}

#[test]
fn google_calendar_create_retries_with_the_same_key_and_creates_one_event() {
    let (_guard, dir) = fresh();
    let stub = google_stub();
    let mut core = google_core(&dir, &stub, false);
    let id = core.add("google", "agenda");
    google_login(&mut core, &stub, &id, &["calendar.read", "calendar.write"]);
    stub.control("fail_after_create", json!({"n": 1}));
    let pid = google_card(
        &mut core,
        &id,
        "calendar.events.create",
        json!({"title": "Reunião de teste", "start": "2026-10-20T09:00:00Z", "end": "2026-10-20T10:00:00Z"}),
    );
    assert_eq!(
        core.call(json!({"op": "tool_decide", "proposal_id": pid, "decision": "authorize"}))
            ["code"],
        "ok"
    );
    let done = core.wait_proposal_done(&pid);
    assert_eq!(done["state"], "executed", "{done}");
    let state = stub.state();
    let copies = state["events"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|e| e["title"] == "Reunião de teste")
        .count();
    assert_eq!(copies, 1, "one event after a 500 and a retry");
    let keys = state["last_idempotency_keys"].as_array().unwrap();
    assert_eq!(keys.len(), 2, "create then the replayed retry");
    assert_eq!(keys[0], keys[1], "the retry reuses the key");
}

#[test]
fn google_quota_is_rate_limited_with_retry_after_and_keeps_the_account() {
    let (_guard, dir) = fresh();
    let stub = google_stub();
    let mut core = google_core(&dir, &stub, false);
    let id = core.add("google", "cota");
    google_login(&mut core, &stub, &id, &["calendar.read"]);
    stub.control("quota", json!({"n": 1, "retry_after": 9}));
    assert_eq!(
        core.op(&id, "calendar.events.list", json!({}))["code"],
        "ok"
    );
    wait_until("quota reported", || {
        core.last_call()["code"] == "rate_limited"
    });
    assert_eq!(core.last_call()["retry_after"], 9);
    assert_eq!(core.item(&id)["status"], "connected");
}

#[test]
fn google_expired_token_is_refreshed_once_and_the_call_succeeds() {
    let (_guard, dir) = fresh();
    let stub = google_stub();
    let mut core = google_core(&dir, &stub, false);
    let id = core.add("google", "expira");
    google_login(&mut core, &stub, &id, &["gmail.read"]);
    let issued = stub.state()["tokens"]["issued"].as_u64().unwrap();
    stub.control("expire_token", json!({}));
    assert_eq!(core.op(&id, "gmail.messages.list", json!({}))["code"], "ok");
    wait_until("refreshed call", || core.last_call()["outcome"] == "ok");
    assert_eq!(
        stub.state()["tokens"]["issued"].as_u64().unwrap(),
        issued + 1
    );
    assert_eq!(core.item(&id)["status"], "connected");
}

#[test]
fn google_scope_loss_at_refresh_moves_the_account_to_reauth_required() {
    let (_guard, dir) = fresh();
    let stub = google_stub();
    let mut core = google_core(&dir, &stub, false);
    let id = core.add("google", "escopo perdido");
    google_login(&mut core, &stub, &id, &["gmail.read", "calendar.read"]);
    stub.control("change_scopes", json!({"scopes": ["gmail.read"]}));
    stub.control("expire_token", json!({}));
    assert_eq!(core.op(&id, "gmail.messages.list", json!({}))["code"], "ok");
    wait_until("reauth after scope loss", || {
        core.item(&id)["status"] == "reauth_required"
    });
    let item = core.item(&id);
    assert_eq!(
        item["granted_scopes"],
        json!(["gmail.read"]),
        "reduced, not cleared"
    );
    wait_until("triggering call reports reauth", || {
        core.last_call()["code"] == "reauth_required"
    });
    assert_eq!(
        core.op(&id, "calendar.events.list", json!({}))["code"],
        "scope_not_granted",
        "the lost scope is refused before the network"
    );
    assert_eq!(
        core.op(&id, "gmail.messages.list", json!({}))["code"],
        "reauth_required",
        "a scope still granted waits for the user"
    );
}

#[test]
fn google_revoke_stops_calls_and_the_server_sees_it() {
    let (_guard, dir) = fresh();
    let stub = google_stub();
    let mut core = google_core(&dir, &stub, false);
    let id = core.add("google", "revogar");
    google_login(&mut core, &stub, &id, &["gmail.read"]);
    let revoked = stub.state()["tokens"]["revoked"].as_u64().unwrap();
    assert_eq!(
        core.call(json!({"op": "connection_revoke", "id": id}))["code"],
        "ok"
    );
    wait_until("revoke reached the fake", || {
        stub.state()["tokens"]["revoked"].as_u64().unwrap() > revoked
    });
    assert_eq!(core.item(&id)["status"], "disconnected");
    assert_eq!(
        core.op(&id, "gmail.messages.list", json!({}))["code"],
        "not_connected"
    );
}

#[test]
fn google_account_mismatch_marks_the_account_as_error() {
    let (_guard, dir) = fresh();
    let stub = google_stub();
    let mut core = google_core(&dir, &stub, false);
    let id = core.add("google", "conta trocada");
    google_login(&mut core, &stub, &id, &["gmail.read"]);
    stub.control("set_account", json!({"name": "outra-conta"}));
    assert_eq!(core.op(&id, "gmail.messages.list", json!({}))["code"], "ok");
    wait_until("account mismatch", || {
        core.last_call()["code"] == "account_mismatch"
    });
    assert_eq!(core.item(&id)["status"], "error");
}

// ---- S5 E2.3 homeassistant (tests/fixtures/connections/homeassistant_server.py) --------------

const HA_TOKEN: &str = "ha-test-token-0123456789abcdef";
const HA_BAD_TOKEN: &str = "ha-wrong-token-0123456789abcdef";

fn ha_stub() -> Stub {
    let script = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/connections/homeassistant_server.py");
    Stub::spawn(&script, &["--port", "0"])
}

fn ha_core(dir: &Path, stub: &Stub, allow_public: bool) -> Core {
    let mut core = Core::new(dir);
    core.start(
        &[format!("homeassistant=http://127.0.0.1:{}", stub.port)],
        allow_public,
    );
    core
}

/// Connect, consent to `consent`, then paste `token` (the fake must hold `server_token` for the probe).
fn ha_login(core: &mut Core, id: &str, consent: &[&str], token: &str) -> Value {
    assert_eq!(
        core.call(json!({"op": "connection_connect", "id": id}))["code"],
        "ok"
    );
    wait_until("ha connecting", || core.item(id)["status"] == "connecting");
    assert_eq!(
        core.call(json!({"op": "connection_consent", "id": id, "scopes": consent}))["code"],
        "ok"
    );
    assert_eq!(
        core.call(json!({"op": "connection_set_token", "id": id, "token": token}))["code"],
        "ok"
    );
    core.wait_status(id, "connected")
}

fn ha_card(core: &mut Core, id: &str, operation: &str, args: Value) -> String {
    let code = core.op(id, operation, args)["code"].clone();
    assert_eq!(code, "pending_approval", "{operation}");
    let pid = core.last_call()["proposal_id"].as_str().unwrap().to_owned();
    let card = core.proposal(&pid);
    assert_eq!(card["kind"], "connection");
    assert_eq!(card["tool"], format!("conn:homeassistant.{operation}"));
    pid
}

#[test]
fn ha_connect_waits_for_consent_and_token_without_touching_the_network() {
    let (_guard, dir) = fresh();
    let stub = ha_stub();
    let mut core = ha_core(&dir, &stub, false);
    let id = core.add("homeassistant", "casa");
    assert_eq!(core.item(&id)["fake"], json!(true));
    assert_eq!(
        core.call(json!({"op": "connection_connect", "id": id}))["code"],
        "ok"
    );
    let item = wait_until_value("ha connecting with every scope pending", || {
        let item = core.item(&id);
        (item["status"] == "connecting").then_some(item)
    });
    assert_eq!(
        item["pending_scopes"],
        json!(["states.read", "services.call", "services.dangerous"])
    );
    assert!(item.get("user_code").is_none(), "{item}");
    assert_eq!(
        stub.state()["requests"],
        json!(0),
        "no request before the token"
    );
}

#[test]
fn ha_token_is_validated_by_one_probe_and_connects_with_the_consented_scopes() {
    let (_guard, dir) = fresh();
    let stub = ha_stub();
    stub.control("set_token", json!({"token": HA_TOKEN}));
    let mut core = ha_core(&dir, &stub, false);
    let id = core.add("homeassistant", "casa");
    let item = ha_login(&mut core, &id, &["states.read", "services.call"], HA_TOKEN);
    assert_eq!(item["account_ref"], "demo-home");
    assert_eq!(
        item["granted_scopes"],
        json!(["states.read", "services.call"])
    );
    assert_eq!(stub.state()["requests"], json!(1), "exactly one probe");
    let text = core.snap().to_string();
    assert!(!text.contains(HA_TOKEN), "token never in the snapshot");
}

#[test]
fn ha_consent_comes_before_the_token_and_only_for_requested_scopes() {
    let (_guard, dir) = fresh();
    let stub = ha_stub();
    stub.control("set_token", json!({"token": HA_TOKEN}));
    let mut core = ha_core(&dir, &stub, false);
    let id = core.add("homeassistant", "casa");
    core.call(json!({"op": "connection_connect", "id": id}));
    wait_until("ha connecting", || core.item(&id)["status"] == "connecting");
    assert_eq!(
        core.call(json!({"op": "connection_set_token", "id": id, "token": HA_TOKEN}))["code"],
        "consent_required"
    );
    assert_eq!(
        core.call(json!({"op": "connection_consent", "id": id, "scopes": ["admin:all"]}))["code"],
        "scope_not_requested"
    );
    assert_eq!(
        core.call(json!({"op": "connection_consent", "id": id, "scopes": []}))["code"],
        "invalid_args"
    );
    assert_eq!(
        core.call(json!({"op": "connection_set_token", "id": id, "token": "curto"}))["code"],
        "consent_required",
        "consent is checked before the token format"
    );
    core.call(json!({"op": "connection_consent", "id": id, "scopes": ["states.read"]}));
    assert_eq!(
        core.call(json!({"op": "connection_set_token", "id": id, "token": "curto"}))["code"],
        "invalid_token"
    );
    assert_eq!(
        stub.state()["requests"],
        json!(0),
        "nothing reached the fake"
    );
}

#[test]
fn ha_wrong_token_is_reauth_required_and_nothing_is_stored() {
    let (_guard, dir) = fresh();
    let stub = ha_stub();
    stub.control("set_token", json!({"token": HA_TOKEN}));
    let mut core = ha_core(&dir, &stub, false);
    let id = core.add("homeassistant", "casa");
    core.call(json!({"op": "connection_connect", "id": id}));
    wait_until("ha connecting", || core.item(&id)["status"] == "connecting");
    core.call(json!({"op": "connection_consent", "id": id, "scopes": ["states.read"]}));
    assert_eq!(
        core.call(json!({"op": "connection_set_token", "id": id, "token": HA_BAD_TOKEN}))["code"],
        "ok"
    );
    wait_until("reauth after the rejected token", || {
        core.item(&id)["status"] == "reauth_required"
    });
    assert!(core.item(&id)["granted_scopes"]
        .as_array()
        .unwrap()
        .is_empty());
    assert!(!core.snap().to_string().contains(HA_BAD_TOKEN));
    assert_eq!(
        core.op(&id, "states.list", json!({}))["code"],
        "scope_not_granted",
        "the reauth account granted nothing: no request, connect again"
    );
}

#[test]
fn ha_read_needs_the_scope_and_never_reaches_the_network_without_it() {
    let (_guard, dir) = fresh();
    let stub = ha_stub();
    stub.control("set_token", json!({"token": HA_TOKEN}));
    let mut core = ha_core(&dir, &stub, false);
    let id = core.add("homeassistant", "casa");
    ha_login(&mut core, &id, &["services.call"], HA_TOKEN);
    let before = stub.state()["requests"].as_u64().unwrap();
    assert_eq!(
        core.op(&id, "states.list", json!({}))["code"],
        "scope_not_granted"
    );
    assert_eq!(
        core.op(&id, "state.get", json!({"entity_id": "light.kitchen"}))["code"],
        "scope_not_granted"
    );
    assert_eq!(stub.state()["requests"].as_u64().unwrap(), before);
}

#[test]
fn ha_service_call_waits_for_approval_then_changes_the_state_on_the_fake() {
    let (_guard, dir) = fresh();
    let stub = ha_stub();
    stub.control("set_token", json!({"token": HA_TOKEN}));
    let mut core = ha_core(&dir, &stub, false);
    let id = core.add("homeassistant", "casa");
    ha_login(&mut core, &id, &["states.read", "services.call"], HA_TOKEN);
    let pid = ha_card(
        &mut core,
        &id,
        "service.call",
        json!({"domain": "light", "service": "turn_on", "entity_id": "light.kitchen", "brightness": 128}),
    );
    assert_eq!(core.proposal(&pid)["risk"], "write");
    assert_eq!(
        core.call(json!({"op": "tool_decide", "proposal_id": pid, "decision": "authorize"}))
            ["code"],
        "ok"
    );
    let done = core.wait_proposal_done(&pid);
    assert_eq!(done["state"], "executed", "{done}");
    let entity = &stub.state()["entities"]["light.kitchen"];
    assert_eq!(entity["state"], "on");
    assert_eq!(entity["attributes"]["brightness"], json!(128));
}

#[test]
fn ha_dangerous_service_needs_the_dangerous_scope_and_never_runs_without_the_switch() {
    let (_guard, dir) = fresh();
    let stub = ha_stub();
    stub.control("set_token", json!({"token": HA_TOKEN}));
    let mut core = ha_core(&dir, &stub, false);
    let plain = core.add("homeassistant", "sem perigosos");
    ha_login(
        &mut core,
        &plain,
        &["states.read", "services.call"],
        HA_TOKEN,
    );
    let before = stub.state()["requests"].as_u64().unwrap();
    assert_eq!(
        core.op(
            &plain,
            "service.call",
            json!({"domain": "lock", "service": "unlock", "entity_id": "lock.front_door"})
        )["code"],
        "scope_not_granted"
    );
    assert_eq!(stub.state()["requests"].as_u64().unwrap(), before);

    let strong = core.add("homeassistant", "com perigosos");
    ha_login(
        &mut core,
        &strong,
        &["states.read", "services.call", "services.dangerous"],
        HA_TOKEN,
    );
    let pid = ha_card(
        &mut core,
        &strong,
        "service.call",
        json!({"domain": "lock", "service": "unlock", "entity_id": "lock.front_door"}),
    );
    assert_eq!(core.proposal(&pid)["risk"], "destructive");
    let refused =
        core.call(json!({"op": "tool_decide", "proposal_id": pid, "decision": "authorize"}));
    assert_eq!(refused["code"], "public_disabled", "{refused}");
    assert_eq!(
        stub.state()["entities"]["lock.front_door"]["state"],
        "locked"
    );
    core.call(json!({"op": "tool_decide", "proposal_id": pid, "decision": "deny"}));
}

#[test]
fn ha_dangerous_service_runs_only_after_approval_with_the_switch() {
    let (_guard, dir) = fresh();
    let stub = ha_stub();
    stub.control("set_token", json!({"token": HA_TOKEN}));
    let mut core = ha_core(&dir, &stub, true);
    let id = core.add("homeassistant", "casa perigosa");
    ha_login(
        &mut core,
        &id,
        &["states.read", "services.call", "services.dangerous"],
        HA_TOKEN,
    );
    let pid = ha_card(
        &mut core,
        &id,
        "service.call",
        json!({"domain": "lock", "service": "unlock", "entity_id": "lock.front_door"}),
    );
    assert_eq!(core.proposal(&pid)["state"], "pending");
    assert_eq!(
        stub.state()["entities"]["lock.front_door"]["state"],
        "locked"
    );
    assert_eq!(
        core.call(json!({"op": "tool_decide", "proposal_id": pid, "decision": "authorize"}))
            ["code"],
        "ok"
    );
    let done = core.wait_proposal_done(&pid);
    assert_eq!(done["state"], "executed", "{done}");
    assert_eq!(
        stub.state()["entities"]["lock.front_door"]["state"],
        "unlocked"
    );
    let text = core.snap().to_string();
    assert!(!text.contains(HA_TOKEN));
}

#[test]
fn ha_switch_turn_off_is_an_ordinary_write_not_a_dangerous_service() {
    let (_guard, dir) = fresh();
    let stub = ha_stub();
    stub.control("set_token", json!({"token": HA_TOKEN}));
    let mut core = ha_core(&dir, &stub, false);
    let id = core.add("homeassistant", "tomada");
    ha_login(&mut core, &id, &["services.call"], HA_TOKEN);
    let pid = ha_card(
        &mut core,
        &id,
        "service.call",
        json!({"domain": "switch", "service": "turn_off", "entity_id": "switch.coffee"}),
    );
    assert_eq!(core.proposal(&pid)["risk"], "write");
    core.call(json!({"op": "tool_decide", "proposal_id": pid, "decision": "deny"}));
}

#[test]
fn ha_token_rejected_on_a_call_is_reauth_required_without_a_refresh() {
    let (_guard, dir) = fresh();
    let stub = ha_stub();
    stub.control("set_token", json!({"token": HA_TOKEN}));
    let mut core = ha_core(&dir, &stub, false);
    let id = core.add("homeassistant", "casa");
    ha_login(&mut core, &id, &["states.read"], HA_TOKEN);
    stub.control("set_token", json!({"token": null}));
    assert_eq!(core.op(&id, "states.list", json!({}))["code"], "ok");
    wait_until("reauth after the rejected token", || {
        core.last_call()["code"] == "reauth_required"
    });
    assert_eq!(core.item(&id)["status"], "reauth_required");
}

#[test]
fn ha_revoke_wipes_the_token_locally_and_calls_stop() {
    let (_guard, dir) = fresh();
    let stub = ha_stub();
    stub.control("set_token", json!({"token": HA_TOKEN}));
    let mut core = ha_core(&dir, &stub, false);
    let id = core.add("homeassistant", "casa");
    ha_login(&mut core, &id, &["states.read"], HA_TOKEN);
    let before = stub.state()["requests"].as_u64().unwrap();
    assert_eq!(
        core.call(json!({"op": "connection_revoke", "id": id}))["code"],
        "ok"
    );
    assert_eq!(core.item(&id)["status"], "disconnected");
    assert_eq!(
        stub.state()["requests"].as_u64().unwrap(),
        before,
        "no revoke request: HA has none"
    );
    assert_eq!(
        core.op(&id, "states.list", json!({}))["code"],
        "not_connected"
    );
    assert_eq!(
        core.call(json!({"op": "connection_set_token", "id": id, "token": HA_TOKEN}))["code"],
        "invalid_state"
    );
}

// ---- S5 E2.4 mcp: the Core launches the fake stdio server itself, inside the plugin sandbox ----

fn mcp_core(dir: &Path, profile: &str, allow_public: bool) -> Core {
    let mut core = Core::new(dir);
    core.start_with(&[], allow_public, &["--connections-fake-mcp", profile]);
    core
}

/// Server processes of the MCP fixture (the sandboxed interpreter), found by their command line.
fn mcp_servers() -> Vec<u32> {
    let mut found = Vec::new();
    for entry in fs::read_dir("/proc").unwrap().flatten() {
        let Some(pid) = entry
            .file_name()
            .to_str()
            .and_then(|name| name.parse::<u32>().ok())
        else {
            continue;
        };
        let Ok(raw) = fs::read(entry.path().join("cmdline")) else {
            continue;
        };
        let argv: Vec<&[u8]> = raw.split(|b| *b == 0).filter(|a| !a.is_empty()).collect();
        let has = |needle: &[u8]| argv.iter().any(|a| *a == needle);
        let interpreter = argv
            .first()
            .is_some_and(|a| a.windows(6).any(|w| w == b"python"));
        if interpreter && has(b"-I") && has(b"/plugin/main.py") && has(b"--profile") {
            found.push(pid);
        }
    }
    found
}

fn mcp_login(core: &mut Core, id: &str, consent: &[&str]) -> Value {
    assert_eq!(
        core.call(json!({"op": "connection_connect", "id": id}))["code"],
        "ok"
    );
    wait_until("mcp server answered initialize", || {
        core.item(id)["pending_scopes"].is_array()
    });
    assert_eq!(
        core.call(json!({"op": "connection_consent", "id": id, "scopes": consent}))["code"],
        "ok"
    );
    core.wait_status(id, "connected")
}

fn mcp_discover(core: &mut Core, id: &str) -> Value {
    assert_eq!(core.op(id, "mcp.discover", json!({}))["code"], "ok");
    wait_until("discover finished", || {
        core.last_call()["operation"] == "mcp.discover" && core.last_call()["outcome"] == "ok"
    });
    core.item(id)["tools"].clone()
}

fn mcp_tool<'a>(tools: &'a Value, name: &str) -> &'a Value {
    tools
        .as_array()
        .unwrap()
        .iter()
        .find(|t| t["name"] == name)
        .unwrap_or_else(|| panic!("tool {name} not listed: {tools}"))
}

fn mcp_call_card(core: &mut Core, id: &str, tool: &str, args: Value, risk: &str) -> String {
    let code = core.op(id, "mcp.call", json!({"tool": tool, "args": args}))["code"].clone();
    assert_eq!(code, "pending_approval", "{tool}");
    let pid = core.last_call()["proposal_id"].as_str().unwrap().to_owned();
    let card = core.proposal(&pid);
    assert_eq!(card["kind"], "connection");
    assert_eq!(card["tool"], "conn:mcp.call");
    assert_eq!(card["risk"], risk);
    pid
}

fn settled(core: &mut Core, pid: &str) -> Value {
    wait_until_value("proposal settled", || {
        let card = core.proposal(pid);
        (card["state"] != "pending" && card["state"] != "authorized").then_some(card)
    })
}

#[test]
fn mcp_without_the_fixed_registration_starts_nothing_and_the_flag_is_strict() {
    let (_guard, dir) = fresh();
    let mut core = Core::new(&dir);
    core.start(&[], false);
    let id = core.add("mcp", "sem registro");
    assert_eq!(
        core.call(json!({"op": "connection_connect", "id": id}))["code"],
        "real_backend_unsupported"
    );
    assert_eq!(core.item(&id)["status"], "disconnected");
    assert_eq!(core.item(&id)["fake"], false);
    assert!(mcp_servers().is_empty());
    drop(core);
    for args in [
        vec![
            "--connections-fake-mcp",
            "sh -c id",
            "--plugin-python",
            PYTHON,
        ],
        vec!["--connections-fake-mcp", "good"],
        vec![
            "--connections-fake-mcp",
            "good",
            "--connections-fake-mcp",
            "evil",
            "--plugin-python",
            PYTHON,
        ],
    ] {
        let status = Command::new(env!("CARGO_BIN_EXE_gideon-base"))
            .arg("--root")
            .arg(dir.join("flags"))
            .args(&args)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .unwrap();
        assert!(!status.success(), "{args:?}");
    }
}

#[test]
fn mcp_connect_consents_per_scope_and_discover_lists_validated_tools() {
    let (_guard, dir) = fresh();
    let mut core = mcp_core(&dir, "good", false);
    let id = core.add("mcp", "bom");
    assert_eq!(
        core.call(json!({"op": "connection_connect", "id": id}))["code"],
        "ok"
    );
    wait_until("pending scopes", || {
        core.item(&id)["pending_scopes"].is_array()
    });
    let item = core.item(&id);
    assert_eq!(item["fake"], true);
    assert_eq!(item["pending_scopes"].as_array().unwrap().len(), 3);
    assert_eq!(
        mcp_servers().len(),
        1,
        "one sandboxed server for the account"
    );
    assert_eq!(
        core.call(json!({"op": "connection_consent", "id": id, "scopes": ["admin"]}))["code"],
        "scope_not_requested"
    );
    assert_eq!(
        core.call(
            json!({"op": "connection_consent", "id": id, "scopes": ["mcp.discover", "mcp.call"]})
        )["code"],
        "ok"
    );
    let item = core.wait_status(&id, "connected");
    assert_eq!(item["granted_scopes"], json!(["mcp.discover", "mcp.call"]));
    assert_eq!(item["account_ref"], "fake-mcp");
    let tools = mcp_discover(&mut core, &id);
    assert_eq!(tools.as_array().unwrap().len(), 3);
    assert_eq!(mcp_tool(&tools, "echo_note")["state"], "trusted");
    assert_eq!(mcp_tool(&tools, "delete_note")["risk"], "destructive");
    assert_eq!(mcp_tool(&tools, "echo_note")["risk"], "write");
    let text = tools.to_string();
    assert!(!text.contains("inputSchema") && !text.contains("sha256"));
}

#[test]
fn mcp_call_waits_for_approval_and_returns_prefixed_untrusted_data() {
    let (_guard, dir) = fresh();
    let mut core = mcp_core(&dir, "good", false);
    let id = core.add("mcp", "bom");
    mcp_login(&mut core, &id, &["mcp.discover", "mcp.call"]);
    mcp_discover(&mut core, &id);
    let pid = mcp_call_card(&mut core, &id, "echo_note", json!({"text": "oi"}), "write");
    assert_eq!(core.last_call()["outcome"], "pending_approval");
    assert!(core.proposal(&pid)["result"].is_null(), "nothing ran yet");
    assert_eq!(
        core.call(json!({"op": "tool_decide", "proposal_id": pid, "decision": "authorize"}))
            ["code"],
        "ok"
    );
    let card = settled(&mut core, &pid);
    assert_eq!(card["state"], "executed", "{card}");
    let result: Value = serde_json::from_str(card["result"].as_str().unwrap()).unwrap();
    assert_eq!(result["output"], "[mcp_output:echo_note] oi");
    assert_eq!(result["untrusted"], true);
    assert_eq!(core.last_call()["untrusted"], true);
    // Arguments the schema does not allow never become a proposal.
    for (tool, args) in [
        ("echo_note", json!({})),
        ("echo_note", json!({"text": 1})),
        ("echo_note", json!({"text": "a", "x": 1})),
        ("add_numbers", json!({"a": 1.5, "b": 2})),
        ("nope", json!({})),
    ] {
        let code = core.op(&id, "mcp.call", json!({"tool": tool, "args": args}))["code"].clone();
        assert!(
            code == "invalid_args" || code == "unknown_tool",
            "{tool} {args}: {code}"
        );
    }
    let nested = core.op(
        &id,
        "mcp.call",
        json!({"tool": "echo_note", "args": {"text": {"a": 1}}}),
    );
    assert_eq!(nested["code"], "invalid_args");
}

#[test]
fn mcp_destructive_tool_needs_its_scope_and_never_runs_without_the_switch() {
    let (_guard, dir) = fresh();
    let mut core = mcp_core(&dir, "good", false);
    let basic = core.add("mcp", "basico");
    mcp_login(&mut core, &basic, &["mcp.discover", "mcp.call"]);
    mcp_discover(&mut core, &basic);
    assert_eq!(
        core.op(
            &basic,
            "mcp.call",
            json!({"tool": "delete_note", "args": {"id": "n1"}})
        )["code"],
        "scope_not_granted"
    );
    let full = core.add("mcp", "completo");
    mcp_login(
        &mut core,
        &full,
        &["mcp.discover", "mcp.call", "mcp.call_destructive"],
    );
    mcp_discover(&mut core, &full);
    let pid = mcp_call_card(
        &mut core,
        &full,
        "delete_note",
        json!({"id": "n1"}),
        "destructive",
    );
    assert_eq!(
        core.call(json!({"op": "tool_decide", "proposal_id": pid, "decision": "authorize"}))
            ["code"],
        "public_disabled"
    );
    assert_eq!(core.proposal(&pid)["state"], "pending");
}

#[test]
fn mcp_changed_tools_need_reapproval_until_the_user_trusts_them() {
    let (_guard, dir) = fresh();
    let mut core = mcp_core(&dir, "changed_tools", false);
    let id = core.add("mcp", "mutante");
    mcp_login(&mut core, &id, &["mcp.discover", "mcp.call"]);
    let first = mcp_discover(&mut core, &id);
    assert!(first
        .as_array()
        .unwrap()
        .iter()
        .all(|t| t["state"] == "trusted"));
    let second = mcp_discover(&mut core, &id);
    assert_eq!(
        mcp_tool(&second, "export_notes")["state"],
        "needs_reapproval"
    );
    assert_eq!(mcp_tool(&second, "echo_note")["state"], "trusted");
    assert_eq!(
        core.op(&id, "mcp.call", json!({"tool": "export_notes", "args": {}}))["code"],
        "tool_not_trusted"
    );
    assert_eq!(
        core.call(json!({"op": "connection_trust_tools", "id": id, "tools": ["nope"]}))["code"],
        "unknown_tool"
    );
    assert_eq!(
        core.call(json!({"op": "connection_trust_tools", "id": id, "tools": ["export_notes"]}))
            ["code"],
        "ok"
    );
    let pid = mcp_call_card(&mut core, &id, "export_notes", json!({}), "write");
    assert_eq!(
        core.call(json!({"op": "tool_decide", "proposal_id": pid, "decision": "authorize"}))
            ["code"],
        "ok"
    );
    let card = settled(&mut core, &pid);
    let result: Value = serde_json::from_str(card["result"].as_str().unwrap()).unwrap();
    assert_eq!(
        result["output"],
        "[mcp_output:export_notes] exported 2 notes"
    );
}

#[test]
fn mcp_evil_profile_rejects_big_and_nested_schemas_and_keeps_text_as_data() {
    let (_guard, dir) = fresh();
    let mut core = mcp_core(&dir, "evil", false);
    let id = core.add("mcp", "malicioso");
    mcp_login(&mut core, &id, &["mcp.discover", "mcp.call"]);
    let tools = mcp_discover(&mut core, &id);
    assert_eq!(tools.as_array().unwrap().len(), 6);
    let big = mcp_tool(&tools, "oversized_schema");
    assert_eq!(
        (big["state"].as_str(), big["reason"].as_str()),
        (Some("rejected"), Some("tool_too_large"))
    );
    let nested = mcp_tool(&tools, "nested_ref");
    assert_eq!(
        (nested["state"].as_str(), nested["reason"].as_str()),
        (Some("rejected"), Some("schema_not_simple"))
    );
    assert!(mcp_tool(&tools, "lookup_note")["description"]
        .as_str()
        .unwrap()
        .contains("IGNORE PREVIOUS INSTRUCTIONS"));
    for name in ["oversized_schema", "nested_ref"] {
        assert_eq!(
            core.op(&id, "mcp.call", json!({"tool": name, "args": {}}))["code"],
            "tool_rejected"
        );
        assert_eq!(
            core.call(json!({"op": "connection_trust_tools", "id": id, "tools": [name]}))["code"],
            "tool_rejected"
        );
    }
    // The description text did not grant anything or start anything.
    assert_eq!(
        core.item(&id)["granted_scopes"],
        json!(["mcp.discover", "mcp.call"])
    );
    assert!(core.snap()["tool_proposals"].as_array().unwrap().is_empty());
}

#[test]
fn mcp_disconnect_kills_the_server_a_crash_is_an_error_and_revoke_forgets_the_trust() {
    let (_guard, dir) = fresh();
    let mut core = mcp_core(&dir, "good", false);
    let id = core.add("mcp", "ciclo");
    mcp_login(&mut core, &id, &["mcp.discover", "mcp.call"]);
    mcp_discover(&mut core, &id);
    let running = mcp_servers();
    assert_eq!(running.len(), 1);
    assert_eq!(
        core.call(json!({"op": "connection_disconnect", "id": id}))["code"],
        "ok"
    );
    wait_until("server gone after disconnect", || mcp_servers().is_empty());
    assert_eq!(
        core.op(&id, "mcp.discover", json!({}))["code"],
        "not_connected"
    );
    assert!(
        core.item(&id)["tools"].is_array(),
        "trust is kept on disconnect"
    );
    // crash
    mcp_login(&mut core, &id, &["mcp.discover", "mcp.call"]);
    // A reconnect clears the discover of this process: the tools are listed again before any call.
    mcp_discover(&mut core, &id);
    let pid_server = mcp_servers()[0];
    // SAFETY: SIGKILL to the sandboxed interpreter this test just started.
    unsafe { libc_kill(pid_server as i32, 9) };
    wait_until("server gone after the kill", || mcp_servers().is_empty());
    let card = mcp_call_card(&mut core, &id, "echo_note", json!({"text": "x"}), "write");
    assert_eq!(
        core.call(json!({"op": "tool_decide", "proposal_id": card, "decision": "authorize"}))
            ["code"],
        "ok"
    );
    let done = settled(&mut core, &card);
    assert_eq!(done["state"], "failed");
    assert_eq!(done["reason"], "mcp_crashed");
    assert_eq!(core.item(&id)["status"], "error");
    assert!(
        core.snap()["connections"].is_object(),
        "the Core keeps serving"
    );
    // reconnect, then revoke forgets the tools
    mcp_login(&mut core, &id, &["mcp.discover"]);
    assert_eq!(
        core.call(json!({"op": "connection_revoke", "id": id}))["code"],
        "ok"
    );
    wait_until("server gone after revoke", || mcp_servers().is_empty());
    assert!(core.item(&id)["tools"].is_null());
}

extern "C" {
    #[link_name = "kill"]
    fn libc_kill(pid: i32, sig: i32) -> i32;
}

// ---------------------------------------------------------------------------------------------
// S5 E3 CapabilityRegistry
// ---------------------------------------------------------------------------------------------

fn purpose<'a>(snap: &'a Value, id: &str) -> &'a Value {
    snap["registry"]["purposes"]
        .as_array()
        .unwrap()
        .iter()
        .find(|p| p["id"] == id)
        .unwrap()
}

fn candidate<'a>(snap: &'a Value, id: &str, route: &str) -> &'a Value {
    purpose(snap, id)["candidates"]
        .as_array()
        .unwrap()
        .iter()
        .find(|c| c["route"] == route)
        .unwrap()
}

#[test]
fn registry_plan_follows_the_connection_standing_and_sends_no_request() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    let mut core = start_core(&dir, &stub, false);
    let snap = core.snap();
    assert_eq!(snap["registry"]["revision"], 0);
    assert_eq!(snap["registry"]["visual_allowed"], json!([]));
    let names: Vec<&str> = snap["registry"]["purposes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|p| p["id"].as_str().unwrap())
        .collect();
    assert_eq!(names, ["create_issue", "list_events", "read_state"]);
    // No account: the connection is not connected, the visual route is off by default.
    assert_eq!(
        candidate(&snap, "create_issue", "connection")["status"],
        "not_connected"
    );
    assert_eq!(
        candidate(&snap, "create_issue", "visual")["status"],
        "visual_not_allowed"
    );
    assert!(purpose(&snap, "create_issue")["route_chosen"].is_null());
    // The google and homeassistant providers have no fake in this run.
    assert_eq!(
        candidate(&snap, "list_events", "connection")["status"],
        "no_api"
    );
    for id in ["create_issue", "list_events", "read_state"] {
        for c in purpose(&snap, id)["candidates"].as_array().unwrap() {
            assert!(!c["reason"].as_str().unwrap().is_empty(), "{id}");
        }
    }
    let before = api_requests(&stub);
    let reply = core.call(json!({"op": "registry_plan", "purpose": "create_issue"}));
    assert_eq!(reply["code"], "route_unavailable");
    assert_eq!(
        core.call(json!({"op": "registry_plan", "purpose": "nope"}))["code"],
        "unknown_purpose"
    );
    let id = core.add("github", "conta registro");
    let snap = core.snap();
    assert_eq!(
        candidate(&snap, "create_issue", "connection")["status"],
        "not_connected"
    );
    core.login(&stub, &id, &["repo:read", "issues:write"]);
    let reply = core.call(json!({"op": "registry_plan", "purpose": "create_issue"}));
    assert_eq!(reply["code"], "ok");
    let snap = core.snap();
    assert_eq!(purpose(&snap, "create_issue")["route_chosen"], "connection");
    assert_eq!(
        candidate(&snap, "create_issue", "connection")["status"],
        "available"
    );
    assert_eq!(
        candidate(&snap, "create_issue", "visual")["status"],
        "visual_not_allowed"
    );
    let after_login = api_requests(&stub);
    for _ in 0..3 {
        core.call(json!({"op": "registry_plan", "purpose": "create_issue"}));
    }
    assert_eq!(api_requests(&stub), after_login, "plan sends nothing");
    assert!(after_login >= before);
    // Consent to fewer scopes elsewhere: a connected account without the scope is scope_not_granted.
    let other = core.add("github", "sem escopo");
    core.login(&stub, &other, &["repo:read"]);
    core.call(json!({"op": "connection_disconnect", "id": id}));
    let snap = core.snap();
    assert_eq!(
        candidate(&snap, "create_issue", "connection")["status"],
        "scope_not_granted"
    );
    core.call(json!({"op": "connection_remove", "id": other}));
    let snap = core.snap();
    assert_eq!(
        candidate(&snap, "create_issue", "connection")["status"],
        "not_connected"
    );
    let plan = core.call(json!({"op": "registry_plan", "purpose": "create_issue"}));
    assert_eq!(plan["code"], "route_unavailable");
}

#[test]
fn registry_visual_permission_is_user_only_cas_persisted_and_revocable() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    {
        let mut core = start_core(&dir, &stub, false);
        let call = |core: &mut Core, op: Value| core.call(op)["code"].as_str().unwrap().to_owned();
        assert_eq!(
            call(
                &mut core,
                json!({"op": "registry_allow_visual", "purpose": "nope", "enabled": true})
            ),
            "unknown_purpose"
        );
        assert_eq!(
            call(
                &mut core,
                json!({"op": "registry_allow_visual", "purpose": "read_state", "enabled": true})
            ),
            "no_visual_route"
        );
        assert_eq!(
            call(
                &mut core,
                json!({"op": "registry_allow_visual", "purpose": "create_issue", "enabled": true, "revision": 9})
            ),
            "stale_registry_revision"
        );
        assert_eq!(core.snap()["registry"]["visual_allowed"], json!([]));
        assert_eq!(
            call(
                &mut core,
                json!({"op": "registry_allow_visual", "purpose": "create_issue", "enabled": true, "revision": 0})
            ),
            "ok"
        );
        let snap = core.snap();
        assert_eq!(snap["registry"]["revision"], 1);
        assert_eq!(snap["registry"]["visual_allowed"], json!(["create_issue"]));
        // Allowed but the synthetic world is off in this run: the route stays disabled, never chosen.
        let visual = candidate(&snap, "create_issue", "visual");
        assert_eq!(visual["status"], "disabled");
        assert!(purpose(&snap, "create_issue")["route_chosen"].is_null());
        let mode = fs::metadata(core.root.join("registry.json"))
            .unwrap()
            .permissions()
            .mode();
        assert_eq!(mode & 0o777, 0o600);
        // A bad request shape is refused by the wire.
        let junk = core.call(json!({"op": "registry_allow_visual", "purpose": "create_issue"}));
        assert_ne!(junk["code"], "ok");
        let junk = core.call(
            json!({"op": "registry_allow_visual", "purpose": "create_issue", "enabled": true, "route": "visual"}),
        );
        assert_ne!(junk["code"], "ok");
    }
    let mut core = start_core(&dir, &stub, false);
    assert_eq!(
        core.snap()["registry"]["visual_allowed"],
        json!(["create_issue"]),
        "the permission survives a restart"
    );
    assert_eq!(
        core.call(json!({"op": "registry_allow_visual", "purpose": "create_issue", "enabled": false, "revision": 1}))
            ["code"],
        "ok"
    );
    let snap = core.snap();
    assert_eq!(snap["registry"]["visual_allowed"], json!([]));
    assert_eq!(snap["registry"]["revision"], 2);
    let text = fs::read_to_string(core.root.join("registry.json")).unwrap();
    assert!(text.contains("\"visual_allowed\":[]"), "{text}");
}

#[test]
fn a_damaged_registry_file_keeps_the_fallback_off_and_refuses_changes() {
    let (_guard, dir) = fresh();
    let stub = Stub::start(&dir);
    {
        let mut core = start_core(&dir, &stub, false);
        core.call(
            json!({"op": "registry_allow_visual", "purpose": "create_issue", "enabled": true}),
        );
    }
    let path = dir.join("core").join("registry.json");
    fs::write(
        &path,
        br#"{"version":1,"revision":4,"visual_allowed":["create_issue"],"x":1}"#,
    )
    .unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
    let mut core = start_core(&dir, &stub, false);
    let snap = core.snap();
    assert_eq!(snap["registry"]["visual_allowed"], json!([]));
    assert_eq!(
        core.call(
            json!({"op": "registry_allow_visual", "purpose": "create_issue", "enabled": true})
        )["code"],
        "registry_storage_error"
    );
    assert_eq!(core.snap()["code"], "ok", "the Core keeps running");
}
