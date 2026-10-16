//! Plugin hardening against the real Core binary: real bwrap sandbox, real Python plugin
//! processes, one tempdir root per test, all tests under one lock (like tests/plugins.rs).
use gideon_base::{hub, storage::Storage};
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
const PYTHON: &str = "/usr/bin/python3";
const MAX_ADDRESS_SPACE: &str = "536870912";
/// Lifetime RLIMIT_CPU backstop; must equal MAX_CPU_SECONDS in src/plugins.rs.
const MAX_CPU: &str = "3600";
const MAX_FILES: &str = "32";
/// Plugin built from one template. `@BUILD@` is a same-length marker the tamper test flips;
/// `@CRASH@` makes the plugin exit on its own N seconds after the handshake (0 = never).
const PLUGIN_TEMPLATE: &str = r#"#!/usr/bin/env python3
# build @BUILD@
import json, os, sys, threading
PLUGIN_ID = "@ID@"
CRASH_AFTER = @CRASH@
CAPS = @CAPS@
if CRASH_AFTER > 0:
    threading.Timer(CRASH_AFTER, os._exit, (3,)).start()
def send(obj):
    obj.setdefault("v", 1)
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()
def invoke(msg):
    rid = msg["id"]
    cap = msg["capability"]
    inp = msg.get("input") or {}
    if cap.endswith(".echo"):
        send({"id": rid, "ok": True, "output": {"text": str(inp.get("text", "")).upper()}})
    elif cap.endswith(".append"):
        # Opening for append or read-write must fail on the read-only payload mount.
        modes = {}
        for mode in ("a", "r+"):
            try:
                open("/plugin/main.py", mode).close()
                modes[mode] = "allowed"
            except Exception:
                modes[mode] = "denied"
        send({"id": rid, "ok": True, "output": {"modes": modes}})
    elif cap.endswith(".noline"):
        sys.stdout.write("x" * 131072)
        sys.stdout.flush()
    elif cap.endswith(".flood"):
        for index in range(200):
            # Log frames carry no "v" and use compact separators: the Core's log prefix check
            # matches the exact bytes {"event":"log" before parsing.
            sys.stdout.write(json.dumps({"event": "log", "level": "info", "text": "flood " + str(index)}, separators=(",", ":")) + "\n")
        sys.stdout.flush()
        send({"id": rid, "ok": True, "output": {"flood": 200}})
    else:
        send({"id": rid, "ok": False, "error": "unknown_capability"})
def main():
    for line in sys.stdin:
        msg = json.loads(line)
        op = msg.get("op")
        if op == "hello":
            send({"v": 1, "id": msg["id"], "ok": True, "plugin_id": PLUGIN_ID, "api": 1, "capabilities": CAPS})
        elif op == "invoke":
            invoke(msg)
        elif op == "shutdown":
            break
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
fn script(id: &str, build: &str, crash_after: f32) -> Vec<u8> {
    let caps = capabilities(id);
    PLUGIN_TEMPLATE
        .replace("@ID@", id)
        .replace("@BUILD@", build)
        .replace("@CRASH@", &format!("{crash_after:.1}"))
        .replace("@CAPS@", &serde_json::to_string(&caps).unwrap())
        .into_bytes()
}
fn capabilities(id: &str) -> Vec<String> {
    ["echo", "append", "noline", "flood"]
        .iter()
        .map(|c| format!("{id}.{c}"))
        .collect()
}

struct Plugin {
    id: &'static str,
    payload: Vec<u8>,
    semver: &'static str,
    capabilities: Vec<String>,
}
fn manifest(p: &Plugin) -> Value {
    json!({
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
        "runtime": "python3_script",
        "capabilities": p.capabilities,
    })
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
fn hardening(build: &str, semver: &'static str) -> Plugin {
    hardening_as("hardening", build, semver, 0.0)
}
fn hardening_as(id: &'static str, build: &str, semver: &'static str, crash: f32) -> Plugin {
    Plugin {
        id,
        payload: script(id, build, crash),
        semver,
        capabilities: capabilities(id),
    }
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
        op["request_id"] = json!(format!("h{}", self.counter));
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
    /// Approves then stages then installs `payload` through the real Hub path.
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
            let hex: String = chunk.iter().fold(String::new(), |mut hex, b| {
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
/// Event kinds currently held by the Core snapshot (bounded ring; newest last).
fn event_kinds(snap: &Value) -> Vec<String> {
    snap["events"]
        .as_array()
        .unwrap()
        .iter()
        .map(|e| e["kind"].as_str().unwrap_or_default().to_owned())
        .collect()
}
/// Process cmdline split on NUL bytes.
fn argv(pid: u32) -> Vec<String> {
    fs::read(format!("/proc/{pid}/cmdline"))
        .unwrap_or_default()
        .split(|b| *b == 0)
        .map(|s| String::from_utf8_lossy(s).into_owned())
        .collect()
}
/// Soft value of one `/proc/<pid>/limits` row (second-to-last column is the soft limit).
fn soft_limit(pid: u32, name: &str) -> String {
    let limits = fs::read_to_string(format!("/proc/{pid}/limits")).unwrap();
    limits
        .lines()
        .find(|l| l.starts_with(name))
        .and_then(|l| l.split_whitespace().rev().nth(2).map(str::to_owned))
        .unwrap_or_else(|| panic!("no limit line {name}: {limits}"))
}

#[test]
fn sandbox_argv_and_rlimits_keep_the_hardened_profile() {
    // Kills M10/M11/M12/M14 when the matching bwrap flag is removed from sandbox_command:
    // --unshare-all, --die-with-parent, --new-session, --clearenv, --remount-ro, plus the
    // read-only payload bind. Verified against the live bwrap argv of a running plugin.
    // Note: prlimit execs bwrap, so its --as/--cpu/--nofile/--nproc flags are gone from argv;
    // the rlimits they set are checked on /proc/<pid>/limits instead (rlimits survive exec).
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, manifests) = setup("argv", &[hardening("A", "1.0.0")]);
    assert_eq!(core.enable("hardening")["code"], "ok");
    core.wait_state("hardening", "running");
    let pids = core.sandboxes();
    assert!(!pids.is_empty(), "plugin sandbox must exist");
    let payload = core
        .root
        .join("hub-plugins")
        .join(format!("hardening-{}.payload", manifests[0]));
    let payload = payload.to_string_lossy().into_owned();
    for pid in &pids {
        let args = argv(*pid);
        assert!(args[0].ends_with("bwrap"), "pid {pid}: {args:?}");
        for flag in [
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--clearenv",
            "--remount-ro",
        ] {
            assert!(
                args.iter().any(|a| a == flag),
                "pid {pid} lacks {flag}: {args:?}"
            );
        }
        let bind = args
            .windows(3)
            .any(|w| w[0] == "--ro-bind" && w[1] == payload && w[2] == "/plugin/main.py");
        assert!(
            bind,
            "payload must be a read-only bind at /plugin/main.py: {args:?}"
        );
        assert!(
            !args.iter().any(|a| a == "--bind"),
            "writable bind found: {args:?}"
        );
        assert_eq!(soft_limit(*pid, "Max address space"), MAX_ADDRESS_SPACE);
        assert_eq!(soft_limit(*pid, "Max cpu time"), MAX_CPU);
        assert_eq!(soft_limit(*pid, "Max open files"), MAX_FILES);
        let processes = soft_limit(*pid, "Max processes");
        assert!(
            processes != "unlimited" && processes.parse::<u64>().unwrap() >= 16,
            "nproc budget: {processes}"
        );
    }
}

#[test]
fn payload_mount_is_read_only_inside_the_sandbox() {
    // Kills M13: a writable payload bind (`--bind` instead of `--ro-bind`) lets the plugin open
    // /plugin/main.py for append or read-write; the plugin reports the result.
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, manifests) = setup("append", &[hardening("A", "1.0.0")]);
    let payload = core
        .root
        .join("hub-plugins")
        .join(format!("hardening-{}.payload", manifests[0]));
    let before = fs::read(&payload).unwrap();
    assert_eq!(core.enable("hardening")["code"], "ok");
    core.wait_state("hardening", "running");
    assert_eq!(
        core.invoke("hardening.append", json!({}), 3000)["code"],
        "ok"
    );
    let result = core.result_of("hardening.append");
    assert_eq!(result["ok"], true, "{result}");
    assert_eq!(result["output"]["modes"]["a"], "denied", "{result}");
    assert_eq!(result["output"]["modes"]["r+"], "denied", "{result}");
    assert_eq!(fs::read(&payload).unwrap(), before, "payload bytes changed");
    core.wait_state("hardening", "running");
}

#[test]
fn oversize_line_without_newline_is_invalid_output_with_no_restart() {
    // Kills M19: an unbounded line reader waits forever for the newline; the Core must instead
    // fail the plugin as plugin_output_invalid, never restart it, and stay responsive.
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, _) = setup("noline", &[hardening("A", "1.0.0")]);
    assert_eq!(core.enable("hardening")["code"], "ok");
    core.wait_state("hardening", "running");
    let started = Instant::now();
    assert_eq!(
        core.invoke("hardening.noline", json!({}), 5000)["code"],
        "ok"
    );
    let failed = core.wait_state("hardening", "failed");
    assert!(
        started.elapsed() < Duration::from_secs(5),
        "violation took {:?}",
        started.elapsed()
    );
    assert_eq!(failed["last_error"], "plugin_output_invalid");
    assert_eq!(failed["restarts"], 0);
    let probe = Instant::now();
    assert_eq!(core.snap()["code"], "ok");
    assert!(probe.elapsed() < Duration::from_secs(2), "Core blocked");
    core.wait_no_sandboxes();
    assert_eq!(
        core.invoke("hardening.echo", json!({}), 1000)["code"],
        "capability_unavailable"
    );
}

#[test]
fn log_flood_is_capped_per_minute_across_bursts() {
    // Kills M25 (per-minute cap): removing `self.logs.len() < LOG_PER_MINUTE` lets every
    // one-second burst of 10 logs through, so three bursts give 30 plugin_log events.
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, _) = setup("flood", &[hardening("A", "1.0.0")]);
    assert_eq!(core.enable("hardening")["code"], "ok");
    core.wait_state("hardening", "running");
    for _ in 0..3 {
        assert_eq!(
            core.invoke("hardening.flood", json!({}), 5000)["code"],
            "ok"
        );
        assert_eq!(core.result_of("hardening.flood")["output"]["flood"], 200);
        // Stay inside one minute while letting the one-second log window roll over.
        thread::sleep(Duration::from_millis(1100));
    }
    let snap = core.snap();
    let logs = event_kinds(&snap)
        .iter()
        .filter(|k| *k == "plugin_log")
        .count();
    assert!(logs >= 1, "no plugin_log events observed");
    assert!(logs <= 20, "plugin_log events in one minute: {logs}");
    assert_eq!(core.item("hardening")["state"], "running");
}

#[test]
fn single_burst_inside_one_second_yields_ten_log_events() {
    // Kills M25 (per-second budget): removing `self.log_window.1 < LOG_PER_SECOND` lets all 200
    // lines of one burst through (capped only by the minute budget at 20). The burst is sent
    // right after the handshake, well inside the first one-second window of this session.
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let (_dir, mut core, _) = setup("burst", &[hardening("A", "1.0.0")]);
    assert_eq!(core.enable("hardening")["code"], "ok");
    core.wait_state("hardening", "running");
    assert_eq!(
        core.invoke("hardening.flood", json!({}), 5000)["code"],
        "ok"
    );
    assert_eq!(core.result_of("hardening.flood")["output"]["flood"], 200);
    let logs = event_kinds(&core.snap())
        .iter()
        .filter(|k| *k == "plugin_log")
        .count();
    assert_eq!(
        logs, 10,
        "per-second budget must admit exactly 10 of 200 lines"
    );
}

#[test]
fn respawn_after_same_length_tamper_is_refused_and_never_runs() {
    // Kills M09: the respawn path (Session::start) must re-verify the payload. Without that check
    // the plugin restarts from the tampered bytes. Flow: the plugin crashes on its own 2 s after
    // the handshake; the test flips one same-length byte in the installed payload (mode stays
    // 0600) right after `running`, before the crash, and sends no requests until the crash
    // has happened. Correct: one start, one failure with plugin_quarantined, no second start.
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let plugin = hardening_as("tamper", "A", "1.0.0", 2.0);
    let (_dir, mut core, manifests) = setup("tamper", &[plugin]);
    let payload = core
        .root
        .join("hub-plugins")
        .join(format!("tamper-{}.payload", manifests[0]));
    assert_eq!(core.enable("tamper")["code"], "ok");
    core.wait_state("tamper", "running");
    let original = fs::read(&payload).unwrap();
    let marker = b"# build A";
    let at = original
        .windows(marker.len())
        .position(|w| w == marker)
        .expect("build marker in payload");
    let mut changed = original.clone();
    changed[at + marker.len() - 1] = b'B';
    assert_eq!(changed.len(), original.len());
    fs::write(&payload, &changed).unwrap();
    let mode = fs::metadata(&payload).unwrap();
    use std::os::unix::fs::PermissionsExt;
    assert_eq!(mode.permissions().mode() & 0o777, 0o600);
    // No requests while the crash and respawn happen.
    thread::sleep(Duration::from_millis(4000));
    core.wait_no_sandboxes();
    let snap = core.snap();
    let kinds = event_kinds(&snap);
    assert_eq!(
        kinds.iter().filter(|k| *k == "plugin_started").count(),
        1,
        "tampered payload must not start a second time: {kinds:?}"
    );
    assert_eq!(
        kinds.iter().filter(|k| *k == "plugin_failed").count(),
        1,
        "respawn must fail once: {kinds:?}"
    );
    assert_eq!(item_of(&snap, "tamper")["enabled"], false);
    assert_eq!(fs::read(&payload).unwrap(), changed);
}

#[test]
fn catalog_move_to_approved_v2_does_not_restart_installed_v1() {
    // Kills M16: refresh must compare the installed manifest with the catalog manifest, not only
    // the plugin id. v2 is approved on disk before the Core boots with the v2 catalog.
    let _lock = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = tempfile::tempdir().unwrap();
    let v1 = [hardening("A", "1.0.0")];
    let cat = catalog(dir.path(), "v1.json", &v1);
    let v1_manifest = hub::load(&cat.0, &cat.1).unwrap().entries[0]
        .manifest_sha256
        .clone();
    let mut core = Core::new(dir.path(), cat);
    core.start();
    core.install("hardening", &v1[0].payload);
    assert_eq!(core.enable("hardening")["code"], "ok");
    core.wait_state("hardening", "running");
    core.stop();
    // Newer manifest with a new payload: same id, semver 2.0.0.
    let v2 = [hardening("B", "2.0.0")];
    let cat2 = catalog(dir.path(), "v2.json", &v2);
    let storage = Storage::open(&core.root).unwrap();
    let snap = hub::load(&cat2.0, &cat2.1).unwrap();
    let entry = snap.entries[0].clone();
    assert_eq!(entry.plugin_id, "hardening");
    assert_ne!(
        entry.manifest_sha256, v1_manifest,
        "v2 must be a new manifest"
    );
    let snap = snap.with_approvals(&storage);
    hub::approve(
        &storage,
        &snap,
        snap.approval_revision,
        &entry.plugin_id,
        &entry.manifest_sha256,
        &entry.permissions,
        true,
    )
    .expect("approve v2 on disk");
    drop(storage);
    core.catalog = cat2;
    core.start();
    let snap = core.snap();
    let item = item_of(&snap, "hardening");
    assert_eq!(item["enabled"], false, "{item}");
    assert_ne!(item["state"], "running", "{item}");
    core.wait_no_sandboxes();
    assert_eq!(
        core.invoke("hardening.echo", json!({}), 1000)["code"],
        "capability_unavailable"
    );
    assert_eq!(core.enable("hardening")["code"], "manifest_mismatch");
}
