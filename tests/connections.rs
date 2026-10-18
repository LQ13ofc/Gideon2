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
        "last_access": None, "last_refresh": None,
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
        return 404, {"error": "not_found"}, {}
    def handle_method(self, method):
        # Sleeps happen outside the lock so other requests are not held up.
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
        let mut child = Command::new(PYTHON)
            .arg("-I")
            .arg(&script)
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
    assert_eq!(core.snap()["connections"]["fake_backends"], json!([]));
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
    assert_eq!(snap["connections"]["fake_backends"], json!(["github"]));
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

#[test]
fn idempotent_retry_reuses_the_key_and_creates_one_issue() {
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
    assert_eq!(done["state"], "executed", "{done}");
    let state = stub.state();
    assert_eq!(
        state["posts"]["/api/repos/demo/private-repo/issues"], 2,
        "one retry after 500"
    );
    assert_eq!(
        state["issues"]["demo/private-repo"],
        json!([1]),
        "the replay did not create a second issue"
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
