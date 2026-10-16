//! C0 plugin runtime against the real Core binary: Unix socket protocol, real bwrap sandbox,
//! real Python plugin processes. Every test owns a tempdir root and runs under one lock so
//! process counts and /proc scans cannot interfere across tests.
use gideon_base::hub;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{BufRead, BufReader, Write},
    os::unix::net::UnixStream,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

static SERIAL: Mutex<()> = Mutex::new(());
const ECHO_FIXTURE: &[u8] = include_bytes!("fixtures/dummy_echo.py");
const EVIL_FIXTURE: &[u8] = include_bytes!("fixtures/dummy_evil.py");
const FIXTURE_CATALOG: &str = include_str!("fixtures/hub.json");
const PYTHON: &str = "/usr/bin/python3";

/// Behaviour selected by capability suffix; the handshake list and plugin id are per manifest.
const MISBEHAVE: &str = r#"#!/usr/bin/env python3
import json, os, queue, sys, threading, time
PLUGIN_ID = "@PLUGIN_ID@"
HELLO_CAPS = @HELLO_CAPS@
Q = queue.Queue()
CANCELLED = set()
def _reader():
    for line in sys.stdin:
        Q.put(line)
    Q.put(None)
threading.Thread(target=_reader, daemon=True).start()
def send(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()
def pump(wait):
    try:
        line = Q.get(timeout=wait)
    except queue.Empty:
        return True
    if line is None:
        return False
    msg = json.loads(line)
    if msg.get("op") == "shutdown":
        return False
    if msg.get("op") == "cancel":
        CANCELLED.add(msg.get("id"))
    return True
def invoke(msg):
    rid = msg["id"]
    cap = msg["capability"]
    inp = msg.get("input") or {}
    if cap.endswith(".echo"):
        send({"id": rid, "ok": True, "output": {"text": str(inp.get("text", "")).upper()}})
    elif cap.endswith(".sleep"):
        end = time.monotonic() + inp.get("sleep_ms", 5000) / 1000
        while time.monotonic() < end:
            if rid in CANCELLED:
                send({"id": rid, "ok": False, "error": "cancelled"})
                return True
            if not pump(0.02):
                return False
        send({"id": rid, "ok": True, "output": {"slept": True}})
    elif cap.endswith(".stubborn"):
        time.sleep(2.5)
        send({"id": rid, "ok": True, "output": {"late": True}})
    elif cap.endswith(".garbage"):
        sys.stdout.write("not json at all\n")
        sys.stdout.flush()
    elif cap.endswith(".oversize"):
        sys.stdout.write("x" * 100000 + "\n")
        sys.stdout.flush()
    elif cap.endswith(".dup"):
        reply = {"id": rid, "ok": True, "output": {"dup": True}}
        send(reply)
        send(reply)
    elif cap.endswith(".crash"):
        os._exit(3)
    elif cap.endswith(".flood"):
        for index in range(200):
            send({"event": "log", "level": "info", "text": "flood " + str(index)})
        send({"id": rid, "ok": True, "output": {"flood": 200}})
    elif cap.endswith(".bigout"):
        send({"id": rid, "ok": True, "output": {"blob": "y" * 9000}})
    elif cap.endswith(".limits"):
        send({"id": rid, "ok": True, "output": {"limits": open("/proc/self/limits").read()}})
    elif cap.endswith(".paths"):
        readable = []
        for path in inp.get("paths", []):
            try:
                open(path, "rb").read(1)
                readable.append(True)
            except Exception:
                readable.append(False)
        writes = []
        for path in ("/etc/gideon_probe", "/usr/gideon_probe"):
            try:
                open(path, "w").write("x")
                writes.append(True)
            except Exception:
                writes.append(False)
        send({"id": rid, "ok": True, "output": {"readable": readable, "writes": writes}})
    else:
        send({"id": rid, "ok": False, "error": "unknown_capability"})
    return True
def main():
    while True:
        line = Q.get()
        if line is None:
            return 0
        msg = json.loads(line)
        op = msg.get("op")
        if op == "hello":
            send({"v": 1, "id": msg["id"], "ok": True, "plugin_id": PLUGIN_ID, "api": 1, "capabilities": HELLO_CAPS})
        elif op == "invoke":
            if not invoke(msg):
                return 0
        elif op == "cancel":
            CANCELLED.add(msg.get("id"))
        elif op == "shutdown":
            return 0
if __name__ == "__main__":
    sys.exit(main())
"#;

fn target() -> String {
    format!("{}_{}", std::env::consts::OS, std::env::consts::ARCH)
}
fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn misbehave(plugin_id: &str, hello: &[&str]) -> Vec<u8> {
    MISBEHAVE
        .replace("@PLUGIN_ID@", plugin_id)
        .replace("@HELLO_CAPS@", &serde_json::to_string(hello).unwrap())
        .into_bytes()
}

struct Plugin {
    id: &'static str,
    payload: Vec<u8>,
    semver: &'static str,
    capabilities: Vec<&'static str>,
    runtime: bool,
}
fn manifest(p: &Plugin) -> Value {
    let mut m = json!({
        "plugin_id": p.id,
        "api_version": 1,
        "publisher": "Gideon test fixture",
        "semver": p.semver,
        "targets": [target()],
        "binaries": [{
            "target": target(),
            "url": format!("https://github.com/acme/plugins/releases/download/v{}/{}.py", p.semver, p.id),
            "sha256": sha(&p.payload),
            "size": p.payload.len(),
        }],
        "license": "MIT",
        "permissions": ["plugin_access"],
        "dependencies": [],
        "conflicts": [],
        "entrypoint": format!("bin/{}.py", p.id),
        "build_source": "https://github.com/acme/plugins/tree/main",
        "support_policy": "test fixture",
        "signature": null,
    });
    if p.runtime {
        m["runtime"] = json!("python3_script");
        m["capabilities"] = json!(p.capabilities);
    }
    m
}
/// Writes a catalog file in `dir` and returns (path, catalog digest).
fn catalog(dir: &Path, name: &str, plugins: &[Plugin]) -> (PathBuf, String) {
    let value = json!({
        "version": 1,
        "repository": "https://github.com/acme/plugins",
        "plugins": plugins.iter().map(manifest).collect::<Vec<_>>(),
    });
    let bytes = serde_json::to_vec(&value).unwrap();
    let path = dir.join(name);
    fs::write(&path, &bytes).unwrap();
    (path, sha(&bytes))
}
fn misbehave_plugins() -> Vec<Plugin> {
    vec![
        Plugin {
            id: "misbehave",
            payload: misbehave(
                "misbehave",
                &[
                    "misbehave.echo",
                    "misbehave.sleep",
                    "misbehave.stubborn",
                    "misbehave.garbage",
                    "misbehave.oversize",
                    "misbehave.dup",
                    "misbehave.crash",
                    "misbehave.dummy",
                ],
            ),
            semver: "1.0.0",
            capabilities: vec![
                "misbehave.echo",
                "misbehave.sleep",
                "misbehave.stubborn",
                "misbehave.garbage",
                "misbehave.oversize",
                "misbehave.dup",
                "misbehave.crash",
                "misbehave.dummy",
            ],
            runtime: true,
        },
        Plugin {
            id: "probe",
            payload: misbehave(
                "probe",
                &["probe.flood", "probe.bigout", "probe.limits", "probe.paths"],
            ),
            semver: "1.0.0",
            capabilities: vec!["probe.flood", "probe.bigout", "probe.limits", "probe.paths"],
            runtime: true,
        },
    ]
}

fn expect_ok(response: &Value) -> &Value {
    assert_eq!(response["code"], "ok", "unexpected response: {response}");
    response
}

/// One Core process bound to a private root; killed on drop.
struct Core {
    root: PathBuf,
    catalog: (PathBuf, String),
    child: Option<Child>,
    counter: u64,
    log: PathBuf,
}
impl Core {
    fn new(dir: &Path, catalog: (PathBuf, String)) -> Core {
        Core {
            root: dir.join("core"),
            catalog,
            child: None,
            counter: 0,
            log: dir.join("core.log"),
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
            .set_read_timeout(Some(Duration::from_secs(20)))
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
    fn revision(&mut self) -> u64 {
        self.snap()["plugins"]["revision"].as_u64().unwrap()
    }
    fn enable(&mut self, plugin_id: &str) -> Value {
        let revision = self.revision();
        self.call(json!({"op": "plugin_enable", "revision": revision, "plugin_id": plugin_id}))
    }
    fn disable(&mut self, plugin_id: &str) -> Value {
        let revision = self.revision();
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
    fn result_of(&mut self, capability: &str) -> Value {
        let snap = self.wait_for("capability result", |s| !s["capability_result"].is_null());
        assert_eq!(snap["capability_result"]["capability"], capability);
        snap["capability_result"].clone()
    }
    fn item(&mut self, plugin_id: &str) -> Value {
        let snap = self.snap();
        item_of(&snap, plugin_id)
    }
    fn wait_state(&mut self, plugin_id: &str, state: &str) -> Value {
        let id = plugin_id.to_owned();
        let state = state.to_owned();
        let snap = self.wait_for(&format!("{id} state {state}"), move |s| {
            item_of(s, &id)["state"] == state.as_str()
        });
        item_of(&snap, plugin_id)
    }
    /// Installs `payload` through the real Hub path: approve, stage in chunks, finish, install.
    fn install(&mut self, plugin_id: &str, payload: &[u8]) -> String {
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
            let hex: String = chunk
                .iter()
                .flat_map(|b| {
                    const DIGITS: &[u8; 16] = b"0123456789abcdef";
                    [
                        DIGITS[usize::from(b >> 4)] as char,
                        DIGITS[usize::from(b & 15)] as char,
                    ]
                })
                .collect();
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
        manifest_sha
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
    /// Processes whose cmdline mentions this test's root (bwrap plugin sandboxes), excluding Core.
    fn sandboxes(&self) -> Vec<u32> {
        let core_pid = self.child.as_ref().map(Child::id);
        let needle = self.root.to_string_lossy().into_owned();
        let Ok(entries) = fs::read_dir("/proc") else {
            return vec![];
        };
        entries
            .flatten()
            .filter_map(|e| {
                let pid: u32 = e.file_name().to_str()?.parse().ok()?;
                let cmdline = fs::read(e.path().join("cmdline")).ok()?;
                let text = String::from_utf8_lossy(&cmdline);
                (Some(pid) != core_pid && text.contains(&needle)).then_some(pid)
            })
            .collect()
    }
    fn wait_no_sandboxes(&self) {
        let deadline = Instant::now() + Duration::from_secs(5);
        while Instant::now() < deadline {
            if self.sandboxes().is_empty() {
                return;
            }
            thread::sleep(Duration::from_millis(30));
        }
        panic!("sandbox processes survived: {:?}", self.sandboxes());
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
fn setup(name: &str, plugins: &[Plugin]) -> (tempfile::TempDir, Core, Vec<String>) {
    let dir = tempfile::tempdir().unwrap();
    let cat = catalog(dir.path(), &format!("{name}.json"), plugins);
    let mut core = Core::new(dir.path(), cat);
    core.start();
    let mut manifests = vec![];
    for plugin in plugins {
        manifests.push(core.install(plugin.id, &plugin.payload));
    }
    (dir, core, manifests)
}

#[test]
fn manifest_hashes_are_pinned_and_declarations_are_strict() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let snap = load_bytes(FIXTURE_CATALOG.as_bytes()).unwrap();
    // Pinned before C0: adding optional fields must not change existing manifest digests.
    assert_eq!(
        snap.entries[0].manifest_sha256,
        "3d07e212c7bbd28a00baf99ca8b1f6397744d89c8efa3ef2c448efd91bf1f4a3"
    );
    assert_eq!(
        snap.entries[1].manifest_sha256,
        "decae4b1cab9679469601652a2d3f0e0e8dccb14f51569ee397bb81e49449e09"
    );
    assert_eq!(
        snap.entries[2].manifest_sha256,
        "dab4449ea0e4a8f6851859003d05d61358683685cc17b976f0af9f247b6724ed"
    );
    assert!(!serde_json::to_string(&snap)
        .unwrap()
        .contains("capabilities"));
    let base: Value = serde_json::from_str(FIXTURE_CATALOG).unwrap();
    let declared = |edit: fn(&mut Value)| {
        let mut value = base.clone();
        let mut plugin = json!({
            "plugin_id": "dummy_echo",
            "api_version": 1,
            "publisher": "Gideon test fixture",
            "semver": "1.0.0",
            "targets": [target()],
            "binaries": [{"target": target(), "url": "https://github.com/acme/plugins/releases/download/v1/a.py", "sha256": sha(b"x"), "size": 1}],
            "license": "MIT",
            "permissions": ["p"],
            "dependencies": [],
            "conflicts": [],
            "entrypoint": "bin/a.py",
            "build_source": "https://github.com/acme/plugins/tree/main",
            "support_policy": "t",
            "signature": null,
            "runtime": "python3_script",
            "capabilities": ["dummy_echo.echo"],
        });
        edit(&mut plugin);
        value["plugins"] = json!([plugin]);
        load_bytes(&serde_json::to_vec(&value).unwrap())
    };
    assert!(declared(|_| {}).is_ok());
    assert!(declared(|p| p["runtime"] = json!("node")).is_err());
    assert!(declared(|p| {
        p.as_object_mut().unwrap().remove("runtime");
    })
    .is_err());
    assert!(declared(|p| p["capabilities"] = json!(["other.echo"])).is_err());
    assert!(declared(|p| p["capabilities"] = json!(["dummy_echo.Echo"])).is_err());
    assert!(
        declared(|p| p["capabilities"] = json!(["dummy_echo.echo", "dummy_echo.echo"])).is_err()
    );
    assert!(declared(|p| p["capabilities"] = json!(["dummy_echo"])).is_err());
    assert!(
        declared(|p| p["capabilities"] = json!([format!("dummy_echo.{}", "x".repeat(60))]))
            .is_err()
    );
    assert!(declared(|p| p["capabilities"] = json!((0..9)
        .map(|i| format!("dummy_echo.c{i}"))
        .collect::<Vec<_>>()))
    .is_err());
    assert!(declared(|p| p["capabilities"] = json!(["core.echo"])).is_err());
    assert!(declared(|p| p["plugin_id"] = json!("core")).is_err());
    assert!(declared(|p| p["plugin_id"] = json!("audio_probe")).is_err());
    assert!(declared(|p| p["runtime"] = json!(null)).is_err());
    assert!(declared(|p| p["capabilities"] = json!(["dummy_echo.echo"])).is_ok());
}
/// Loads catalog bytes from a throwaway directory with their own digest.
fn load_bytes(bytes: &[u8]) -> std::io::Result<hub::Snapshot> {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("catalog.json");
    fs::write(&path, bytes).unwrap();
    hub::load(&path, &sha(bytes))
}

#[test]
fn fixture_plugin_enable_invoke_and_revocation_gates() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let plugins = [Plugin {
        id: "dummy_echo",
        payload: ECHO_FIXTURE.to_vec(),
        semver: "1.0.0",
        capabilities: vec!["dummy_echo.echo"],
        runtime: true,
    }];
    let (_dir, mut core, _) = setup("echo", &plugins);
    let snap = core.snap();
    assert_eq!(snap["plugins"]["status"], "ok");
    assert_eq!(item_of(&snap, "dummy_echo")["state"], "disabled");
    assert!(snap.get("capability_result").is_none());
    // Stale revision and enabling an unknown or unapproved plugin are refused.
    let stale =
        core.call(json!({"op": "plugin_enable", "revision": 999, "plugin_id": "dummy_echo"}));
    assert_eq!(stale["code"], "stale_plugin_revision");
    assert_eq!(core.enable("nope")["code"], "unknown_plugin");
    // Happy path: enable, real invocation through the sandbox, result in the snapshot.
    assert_eq!(expect_ok(&core.enable("dummy_echo"))["code"], "ok");
    assert_eq!(core.wait_state("dummy_echo", "running")["enabled"], true);
    assert_eq!(
        expect_ok(&core.invoke("dummy_echo.echo", json!({"text": "gideon"}), 3000))["code"],
        "ok"
    );
    let result = core.result_of("dummy_echo.echo");
    assert_eq!(result["ok"], true);
    assert_eq!(result["output"]["text"], "GIDEON");
    assert_eq!(result["output"]["count"], 1);
    // Capability must belong to the active manifest; invalid input never reaches the plugin.
    assert_eq!(
        core.invoke("dummy_echo.missing", json!({}), 1000)["code"],
        "unknown_capability"
    );
    assert_eq!(
        core.invoke("base.echo", json!({}), 1000)["code"],
        "unknown_capability"
    );
    assert_eq!(
        core.invoke("dummy_echo.echo", json!("text"), 1000)["code"],
        "invalid_input"
    );
    assert_eq!(
        core.invoke("dummy_echo.echo", json!({"text": "x"}), 0)["code"],
        "invalid_input"
    );
    assert_eq!(
        core.invoke("dummy_echo.echo", json!({"text": "x"}), 10001)["code"],
        "invalid_input"
    );
    assert_eq!(
        core.invoke("dummy_echo.echo", json!({"text": "x".repeat(9000)}), 1000)["code"],
        "invalid_input"
    );
    assert_eq!(
        core.invoke(
            "dummy_echo.echo",
            json!({"a": {"b": {"c": {"d": {"e": 1}}}}}),
            1000
        )["code"],
        "invalid_input"
    );
    // Disable kills the process and the capability disappears.
    assert_eq!(core.disable("dummy_echo")["code"], "ok");
    core.wait_no_sandboxes();
    assert_eq!(
        core.invoke("dummy_echo.echo", json!({"text": "x"}), 1000)["code"],
        "capability_unavailable"
    );
    assert_eq!(core.disable("dummy_echo")["code"], "not_enabled");
    // Revoke removes approval; re-enable then needs a new approval.
    assert_eq!(core.enable("dummy_echo")["code"], "ok");
    core.wait_state("dummy_echo", "running");
    let revoke_revision = core.revision();
    let approval_before = core.snap()["hub"]["approval_revision"].as_u64().unwrap();
    assert_eq!(
        core.call(
            json!({"op": "plugin_revoke", "revision": revoke_revision, "plugin_id": "dummy_echo"})
        )["code"],
        "ok"
    );
    core.wait_no_sandboxes();
    let snap = core.snap();
    assert_eq!(
        snap["hub"]["approval_revision"].as_u64().unwrap(),
        approval_before + 1
    );
    assert_eq!(entry_of(&snap, "dummy_echo")["permissions_approved"], false);
    assert_eq!(
        core.invoke("dummy_echo.echo", json!({"text": "x"}), 1000)["code"],
        "capability_unavailable"
    );
    assert_eq!(
        core.enable("dummy_echo")["code"],
        "permissions_not_approved"
    );
}

#[test]
fn revoked_installed_plugin_is_reapproved_then_reenabled_without_reinstall() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let plugins = [Plugin {
        id: "dummy_echo",
        payload: ECHO_FIXTURE.to_vec(),
        semver: "1.0.0",
        capabilities: vec!["dummy_echo.echo"],
        runtime: true,
    }];
    let (_dir, mut core, _) = setup("reapprove", &plugins);
    assert_eq!(core.enable("dummy_echo")["code"], "ok");
    core.wait_state("dummy_echo", "running");
    let revoke_revision = core.revision();
    assert_eq!(
        core.call(
            json!({"op": "plugin_revoke", "revision": revoke_revision, "plugin_id": "dummy_echo"})
        )["code"],
        "ok"
    );
    core.wait_no_sandboxes();
    let snap = core.snap();
    let entry = entry_of(&snap, "dummy_echo");
    assert_eq!(entry["status"], "installed");
    assert_eq!(entry["permissions_approved"], false);
    assert_eq!(item_of(&snap, "dummy_echo")["enabled"], false);
    assert_eq!(
        core.enable("dummy_echo")["code"],
        "permissions_not_approved"
    );
    // Re-approval of the installed, unchanged manifest and permissions is accepted.
    let manifest_sha = entry["manifest_sha256"].as_str().unwrap().to_owned();
    let approval = snap["hub"]["approval_revision"].as_u64().unwrap();
    let before = approval;
    expect_ok(&core.call(json!({
        "op": "hub_approve",
        "revision": approval,
        "plugin_id": "dummy_echo",
        "manifest_sha256": manifest_sha,
        "permissions": entry["permissions"],
        "publisher_unverified_ack": true,
    })));
    let snap = core.snap();
    assert_eq!(
        snap["hub"]["approval_revision"].as_u64().unwrap(),
        before + 1
    );
    let entry = entry_of(&snap, "dummy_echo");
    assert_eq!(entry["status"], "installed");
    assert_eq!(entry["permissions_approved"], true);
    // Approving again while already approved is refused.
    assert_eq!(
        core.call(json!({
            "op": "hub_approve",
            "revision": before + 1,
            "plugin_id": "dummy_echo",
            "manifest_sha256": manifest_sha,
            "permissions": entry["permissions"],
            "publisher_unverified_ack": true,
        }))["code"],
        "already_approved"
    );
    // Re-enable works and the capability runs through the sandbox again.
    assert_eq!(expect_ok(&core.enable("dummy_echo"))["code"], "ok");
    core.wait_state("dummy_echo", "running");
    assert_eq!(
        expect_ok(&core.invoke("dummy_echo.echo", json!({"text": "again"}), 3000))["code"],
        "ok"
    );
    let result = core.result_of("dummy_echo.echo");
    assert_eq!(result["output"]["text"], "AGAIN");
}

#[test]
fn handshake_mismatch_fails_without_restart() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let plugins = [Plugin {
        id: "misbehave",
        payload: misbehave("misbehave", &["misbehave.other"]),
        semver: "1.0.0",
        capabilities: vec!["misbehave.echo"],
        runtime: true,
    }];
    let (_dir, mut core, _) = setup("handshake", &plugins);
    assert_eq!(core.enable("misbehave")["code"], "ok");
    let item = core.wait_state("misbehave", "failed");
    assert_eq!(item["last_error"], "handshake_mismatch");
    assert_eq!(item["restarts"], 0);
    assert_eq!(
        core.invoke("misbehave.echo", json!({}), 1000)["code"],
        "capability_unavailable"
    );
    core.wait_no_sandboxes();
}

#[test]
fn invoke_timeout_reports_and_plugin_keeps_running() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, _) = setup("timeout", &misbehave_plugins());
    assert_eq!(core.enable("misbehave")["code"], "ok");
    core.wait_state("misbehave", "running");
    assert_eq!(
        core.invoke("misbehave.sleep", json!({"sleep_ms": 5000}), 300)["code"],
        "ok"
    );
    let result = core.result_of("misbehave.sleep");
    assert_eq!(result["error"], "capability_timeout");
    thread::sleep(Duration::from_millis(300));
    assert_eq!(core.item("misbehave")["state"], "running");
    assert_eq!(
        core.invoke("misbehave.echo", json!({"text": "ok"}), 2000)["code"],
        "ok"
    );
    assert_eq!(core.result_of("misbehave.echo")["output"]["text"], "OK");
}

#[test]
fn cancel_is_honored_and_ignored_cancel_is_killed_and_restarted_once() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, _) = setup("cancel", &misbehave_plugins());
    assert_eq!(core.enable("misbehave")["code"], "ok");
    core.wait_state("misbehave", "running");
    // Honored: the plugin answers the cancel, Core already reported invoke_cancelled.
    assert_eq!(
        core.invoke("misbehave.sleep", json!({"sleep_ms": 5000}), 5000)["code"],
        "ok"
    );
    thread::sleep(Duration::from_millis(100));
    assert_eq!(
        core.call(json!({"op": "capability_cancel", "capability": "misbehave.sleep"}))["code"],
        "ok"
    );
    assert_eq!(
        core.result_of("misbehave.sleep")["error"],
        "invoke_cancelled"
    );
    thread::sleep(Duration::from_millis(300));
    assert_eq!(
        core.invoke("misbehave.echo", json!({"text": "after"}), 2000)["code"],
        "ok"
    );
    assert_eq!(core.result_of("misbehave.echo")["output"]["text"], "AFTER");
    // Ignored: the plugin keeps sleeping; after the 1 s grace it is killed and restarted once.
    assert_eq!(
        core.invoke("misbehave.stubborn", json!({}), 5000)["code"],
        "ok"
    );
    thread::sleep(Duration::from_millis(100));
    assert_eq!(
        core.call(json!({"op": "capability_cancel", "capability": "misbehave.stubborn"}))["code"],
        "ok"
    );
    assert_eq!(
        core.result_of("misbehave.stubborn")["error"],
        "invoke_cancelled"
    );
    let item = core.wait_for("restart after ignored cancel", |s| {
        item_of(s, "misbehave")["restarts"] == 1 && item_of(s, "misbehave")["state"] == "running"
    });
    assert_eq!(item["plugins"]["items"].as_array().unwrap().len(), 2);
    assert_eq!(
        core.invoke("misbehave.echo", json!({"text": "again"}), 2000)["code"],
        "ok"
    );
    assert_eq!(core.result_of("misbehave.echo")["output"]["text"], "AGAIN");
    assert_eq!(
        core.call(json!({"op": "capability_cancel", "capability": "misbehave.echo"}))["code"],
        "stale_invocation"
    );
}

#[test]
fn output_violations_fail_plugin_and_are_never_trusted() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, _) = setup("violations", &misbehave_plugins());
    for (capability, error_expected) in [
        ("misbehave.garbage", "plugin_output_invalid"),
        ("misbehave.oversize", "plugin_output_invalid"),
        ("misbehave.dup", "plugin_output_invalid"),
    ] {
        assert_eq!(core.enable("misbehave")["code"], "ok", "{capability}");
        core.wait_state("misbehave", "running");
        assert_eq!(core.invoke(capability, json!({}), 2000)["code"], "ok");
        let failed = core.wait_state("misbehave", "failed");
        assert_eq!(failed["last_error"], error_expected, "{capability}");
        assert_eq!(failed["restarts"], 0, "{capability}");
        assert_eq!(
            core.invoke("misbehave.echo", json!({}), 1000)["code"],
            "capability_unavailable"
        );
        core.wait_no_sandboxes();
        assert_eq!(core.disable("misbehave")["code"], "ok");
    }
    // Oversized plugin output (over 8 KiB) is an output violation too.
    let (_dir2, mut core2, _) = setup("bigout", &misbehave_plugins()[1..]);
    assert_eq!(core2.enable("probe")["code"], "ok");
    core2.wait_state("probe", "running");
    assert_eq!(core2.invoke("probe.bigout", json!({}), 2000)["code"], "ok");
    assert_eq!(
        core2.wait_state("probe", "failed")["last_error"],
        "plugin_output_invalid"
    );
}

#[test]
fn crash_restarts_once_then_fails() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, _) = setup("crash", &misbehave_plugins());
    assert_eq!(core.enable("misbehave")["code"], "ok");
    core.wait_state("misbehave", "running");
    assert_eq!(
        core.invoke("misbehave.crash", json!({}), 2000)["code"],
        "ok"
    );
    assert_eq!(core.result_of("misbehave.crash")["error"], "plugin_error");
    let restarted = core.wait_for("first restart", |s| {
        item_of(s, "misbehave")["restarts"] == 1 && item_of(s, "misbehave")["state"] == "running"
    });
    assert_eq!(item_of(&restarted, "misbehave")["enabled"], true);
    assert_eq!(
        core.invoke("misbehave.crash", json!({}), 2000)["code"],
        "ok"
    );
    let failed = core.wait_state("misbehave", "failed");
    assert_eq!(failed["last_error"], "plugin_crashed");
    assert_eq!(failed["restarts"], 1);
    core.wait_no_sandboxes();
    assert_eq!(
        core.invoke("misbehave.echo", json!({}), 1000)["code"],
        "capability_unavailable"
    );
}

#[test]
fn log_flood_is_rate_limited_into_few_core_events() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, _) = setup("flood", &misbehave_plugins()[1..]);
    assert_eq!(core.enable("probe")["code"], "ok");
    core.wait_state("probe", "running");
    assert_eq!(core.invoke("probe.flood", json!({}), 5000)["code"], "ok");
    assert_eq!(core.result_of("probe.flood")["output"]["flood"], 200);
    let snap = core.snap();
    let logs = snap["events"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|e| e["kind"] == "plugin_log")
        .count();
    assert!((1..=20).contains(&logs), "plugin_log events: {logs}");
    assert_eq!(core.item("probe")["state"], "running");
}

#[test]
fn disable_and_revoke_kill_processes_and_manifest_without_runtime_is_not_runnable() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let mut plugins = misbehave_plugins();
    plugins.push(Plugin {
        id: "opaque",
        payload: b"opaque payload, never executed\n".to_vec(),
        semver: "1.0.0",
        capabilities: vec![],
        runtime: false,
    });
    let (_dir, mut core, _) = setup("runtime", &plugins);
    assert_eq!(core.enable("opaque")["code"], "plugin_not_runnable");
    assert_eq!(core.enable("misbehave")["code"], "ok");
    core.wait_state("misbehave", "running");
    assert!(
        !core.sandboxes().is_empty(),
        "plugin process must exist while enabled"
    );
    assert_eq!(core.disable("misbehave")["code"], "ok");
    core.wait_no_sandboxes();
    assert_eq!(core.enable("misbehave")["code"], "ok");
    core.wait_state("misbehave", "running");
    let revision = core.revision();
    assert_eq!(
        core.call(json!({"op": "plugin_revoke", "revision": revision, "plugin_id": "misbehave"}))
            ["code"],
        "ok"
    );
    core.wait_no_sandboxes();
    assert_eq!(core.item("misbehave")["state"], "disabled");
    assert_eq!(
        core.invoke("misbehave.echo", json!({}), 1000)["code"],
        "capability_unavailable"
    );
    assert_eq!(core.enable("misbehave")["code"], "permissions_not_approved");
}

#[test]
fn tampered_payload_is_refused_before_spawn() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, manifests) = setup("tamper", &misbehave_plugins());
    let path = core
        .root
        .join("hub-plugins")
        .join(format!("probe-{}.payload", manifests[1]));
    let original = fs::read(&path).unwrap();
    let mut changed = original.clone();
    changed[0] ^= 1;
    fs::write(&path, &changed).unwrap();
    assert_eq!(core.enable("probe")["code"], "plugin_quarantined");
    assert_eq!(core.item("probe")["state"], "quarantined");
    core.wait_no_sandboxes();
    fs::write(&path, &original).unwrap();
    assert_eq!(core.enable("probe")["code"], "ok");
    core.wait_state("probe", "running");
    // Tampering after enable: the next request prunes the plugin and stops its process.
    fs::write(&path, &changed).unwrap();
    let snap = core.wait_for("prune after tamper", |s| {
        !item_of(s, "probe")["enabled"].as_bool().unwrap_or(true)
    });
    assert_eq!(item_of(&snap, "probe")["state"], "quarantined");
    core.wait_no_sandboxes();
}

#[test]
fn catalog_update_prunes_enabled_plugin_and_reenable_needs_new_approval() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = tempfile::tempdir().unwrap();
    let plugins = [Plugin {
        id: "dummy_echo",
        payload: ECHO_FIXTURE.to_vec(),
        semver: "1.0.0",
        capabilities: vec!["dummy_echo.echo"],
        runtime: true,
    }];
    let cat = catalog(dir.path(), "v1.json", &plugins);
    let mut core = Core::new(dir.path(), cat);
    core.start();
    core.install("dummy_echo", ECHO_FIXTURE);
    assert_eq!(core.enable("dummy_echo")["code"], "ok");
    core.wait_state("dummy_echo", "running");
    core.stop();
    // Catalog v1.1.0 with the same payload: a different manifest digest is an update.
    let updated = [Plugin {
        id: "dummy_echo",
        payload: ECHO_FIXTURE.to_vec(),
        semver: "1.1.0",
        capabilities: vec!["dummy_echo.echo"],
        runtime: true,
    }];
    core.catalog = catalog(dir.path(), "v11.json", &updated);
    core.start();
    let snap = core.snap();
    assert_eq!(item_of(&snap, "dummy_echo")["enabled"], false);
    assert_eq!(core.enable("dummy_echo")["code"], "manifest_mismatch");
    core.install("dummy_echo", ECHO_FIXTURE);
    assert_eq!(core.item("dummy_echo")["semver"], "1.1.0");
    assert_eq!(core.item("dummy_echo")["enabled"], false);
    assert_eq!(core.enable("dummy_echo")["code"], "ok");
    core.wait_state("dummy_echo", "running");
}

#[test]
fn enabled_plugin_survives_core_restart_and_restarts_without_blocking_boot() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, _) = setup("restart", &misbehave_plugins()[1..]);
    assert_eq!(core.enable("probe")["code"], "ok");
    core.wait_state("probe", "running");
    core.stop();
    core.wait_no_sandboxes();
    core.start();
    let item = core.wait_state("probe", "running");
    assert_eq!(item["enabled"], true);
    assert_eq!(core.invoke("probe.limits", json!({}), 2000)["code"], "ok");
    assert_eq!(core.result_of("probe.limits")["ok"], true);
}

#[test]
fn corrupt_plugin_ledger_quarantines_plugins_without_stopping_core() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, _) = setup("ledger", &misbehave_plugins()[1..]);
    assert_eq!(core.enable("probe")["code"], "ok");
    core.wait_state("probe", "running");
    core.stop();
    core.wait_no_sandboxes();
    fs::write(
        core.root.join("plugin-state.json"),
        b"{\"version\":1,\"revision\":0,\"enabled\":[],\"extra\":1}",
    )
    .unwrap();
    core.start();
    let snap = core.snap();
    assert_eq!(snap["plugins"]["status"], "quarantined");
    assert_eq!(core.enable("probe")["code"], "plugin_quarantined");
    assert_eq!(snap["code"], "ok");
    assert_eq!(core.call(json!({"op": "snapshot"}))["code"], "ok");
}

#[test]
fn sandbox_denies_network_filesystem_writes_and_fork_bombs() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let plugins = [Plugin {
        id: "dummy_evil",
        payload: EVIL_FIXTURE.to_vec(),
        semver: "1.0.0",
        capabilities: vec!["dummy_evil.probe"],
        runtime: true,
    }];
    let (_dir, mut core, _) = setup("evil", &plugins);
    assert_eq!(core.enable("dummy_evil")["code"], "ok");
    core.wait_state("dummy_evil", "running");
    for probe in [
        "network",
        "read_home",
        "read_repo",
        "write_root",
        "env",
        "mem",
        "fork_bomb_limited",
    ] {
        assert_eq!(
            core.invoke("dummy_evil.probe", json!({"probe": probe}), 10000)["code"],
            "ok",
            "{probe}"
        );
        let result = core.result_of("dummy_evil.probe");
        assert_eq!(result["ok"], true, "{probe}: {result}");
        assert_eq!(result["output"]["result"], "denied", "{probe}: {result}");
        // Each probe ends with the plugin still alive; a crash here would fail the gate.
        core.wait_state("dummy_evil", "running");
    }
    assert_eq!(
        core.invoke("dummy_evil.probe", json!({"probe": "exec"}), 10000)["code"],
        "ok"
    );
    // exec runs /usr/bin/id inside the read-only runtime; it has no network or host path access.
    let exec = core.result_of("dummy_evil.probe");
    assert!(exec["output"]["result"] == "allowed" || exec["output"]["result"] == "denied");
    core.wait_state("dummy_evil", "running");
}

#[test]
fn sandbox_hides_home_repo_and_other_payloads_and_blocks_writes() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, manifests) = setup("paths", &misbehave_plugins());
    assert_eq!(core.enable("probe")["code"], "ok");
    core.wait_state("probe", "running");
    let home = std::env::var("HOME").unwrap_or_else(|_| "/root".into());
    let repo = concat!(env!("CARGO_MANIFEST_DIR"), "/Cargo.toml").to_owned();
    let other = core
        .root
        .join("hub-plugins")
        .join(format!("misbehave-{}.payload", manifests[0]));
    let paths = vec![
        home,
        "/home".to_owned(),
        repo,
        core.root.to_string_lossy().into_owned(),
        other.to_string_lossy().into_owned(),
        "/etc/passwd".to_owned(),
    ];
    assert_eq!(
        core.invoke("probe.paths", json!({"paths": paths}), 3000)["code"],
        "ok"
    );
    let result = core.result_of("probe.paths");
    assert_eq!(
        result["output"]["readable"],
        json!([false, false, false, false, false, false]),
        "{result}"
    );
    assert_eq!(result["output"]["writes"], json!([false, false]));
}

#[test]
fn sandbox_limits_are_applied_to_the_real_child() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, _) = setup("limits", &misbehave_plugins()[1..]);
    assert_eq!(core.enable("probe")["code"], "ok");
    core.wait_state("probe", "running");
    let pids = core.sandboxes();
    // bwrap keeps a monitor process with the same argv; every match shares the same limits.
    assert!(!pids.is_empty(), "plugin sandbox must exist");
    let host = fs::read_to_string(format!("/proc/{}/limits", pids[0])).unwrap();
    let soft = |name: &str| -> String {
        host.lines()
            .find(|l| l.starts_with(name))
            .and_then(|l| l.split_whitespace().rev().nth(2).map(str::to_owned))
            .unwrap_or_else(|| panic!("no limit line {name}: {host}"))
    };
    assert_eq!(soft("Max address space"), "536870912");
    assert_eq!(soft("Max cpu time"), "30");
    assert_eq!(soft("Max open files"), "32");
    assert_ne!(soft("Max processes"), "unlimited");
    // The plugin itself reports the limits it runs under; they match the host view.
    assert_eq!(core.invoke("probe.limits", json!({}), 2000)["code"], "ok");
    let limits = core.result_of("probe.limits")["output"]["limits"]
        .as_str()
        .unwrap()
        .to_owned();
    assert!(
        limits
            .lines()
            .any(|l| l.starts_with("Max address space") && l.contains("536870912")),
        "{limits}"
    );
    assert!(
        limits
            .lines()
            .any(|l| l.starts_with("Max open files") && l.contains(" 32 ")),
        "{limits}"
    );
}

#[test]
fn core_shutdown_leaves_no_child_processes() {
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, _) = setup("shutdown", &misbehave_plugins());
    assert_eq!(core.enable("misbehave")["code"], "ok");
    assert_eq!(core.enable("misbehave")["code"], "already_enabled");
    core.wait_state("misbehave", "running");
    assert!(!core.sandboxes().is_empty());
    core.stop();
    core.wait_no_sandboxes();
}

#[test]
fn shipped_c0_catalog_loads_with_runtime_declarations() {
    let _serial = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/hub-c0.json");
    let digest = format!("{:x}", Sha256::digest(fs::read(&path).unwrap()));
    let snapshot = hub::load(&path, &digest).expect("hub-c0.json must parse");
    assert_eq!(snapshot.status, "verified");
    let ids: Vec<_> = snapshot
        .entries
        .iter()
        .map(|e| e.plugin_id.as_str())
        .collect();
    assert_eq!(ids, ["dummy_echo", "dummy_evil", "plain_opaque"]);
    assert!(snapshot.entries.iter().all(|e| e.status == "not_installed"));
}

#[test]
fn only_capability_invoke_lines_may_exceed_the_four_kib_request_bound() {
    use std::io::Read;
    let _serial = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = tempfile::tempdir().unwrap();
    let cat = catalog(dir.path(), "bound.json", &[]);
    let mut core = Core::new(dir.path(), cat);
    core.start();
    // Garbage without a newline must be cut at the ordinary bound, not wait for 16 KiB.
    let mut stream = UnixStream::connect(core.root.join("core.sock")).unwrap();
    stream
        .set_read_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    stream.write_all(&[b'x'; 5000]).unwrap();
    let mut buf = [0u8; 10];
    match stream.read(&mut buf) {
        Ok(0) => {}
        Err(e) if e.kind() == std::io::ErrorKind::ConnectionReset => {}
        other => panic!("oversize line was not closed promptly: {other:?}"),
    }
    // A long line that does not name capability_invoke is also refused at 4 KiB.
    let mut other = UnixStream::connect(core.root.join("core.sock")).unwrap();
    other
        .set_read_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    let filler = "a".repeat(6000);
    let line = format!(
        "{{\"version\":1,\"request_id\":\"long\",\"op\":\"snapshot\",\"x\":\"{filler}\"}}\n"
    );
    let _ = other.write_all(line.as_bytes());
    match other.read(&mut buf) {
        Ok(0) => {}
        Err(e) if e.kind() == std::io::ErrorKind::ConnectionReset => {}
        other => panic!("long non-invoke line was not closed: {other:?}"),
    }
    assert!(
        core.try_snapshot().is_some(),
        "Core must survive both peers"
    );
}
