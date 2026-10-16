//! C4.0 generic infrastructure against the real Core binary. Inline Python stubs only:
//! a scripted chat plugin (as in tests/agent.rs) and a proxy plugin per area that forwards
//! `input.service` / `input.args` to `host_call` and returns the reply as `host` or `host_error`.
//! No real screen, input, audio, microphone or camera is touched: every effect is in world.json.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{BufRead, BufReader, Write},
    os::unix::net::UnixStream,
    path::{Path, PathBuf},
    process::{Child, Command as Process, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

static SERIAL: Mutex<()> = Mutex::new(());
const PYTHON: &str = "/usr/bin/python3";
const CHAT: &str = "fakellm.chat";
const CHAT_PLUGIN: &str = "fakellm";

/// Scripted chat plugin. One step per chat invoke: text, tool_calls, usage, delay or error.
const CHAT_STUB: &str = r#"#!/usr/bin/env python3
import json, sys, time
PLUGIN_ID = "fakellm"
CAPS = ["fakellm.chat"]
STEPS = json.loads(r'''@STEPS@''')
calls = 0
def send(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()
while True:
    line = sys.stdin.readline()
    if not line:
        break
    msg = json.loads(line)
    op = msg.get("op")
    if op == "hello":
        send({"v": 1, "id": msg["id"], "ok": True, "plugin_id": PLUGIN_ID, "api": 1, "capabilities": CAPS})
    elif op == "invoke":
        step = STEPS[min(calls, len(STEPS) - 1)]
        calls += 1
        if step.get("delay_ms"):
            time.sleep(step["delay_ms"] / 1000.0)
        if step.get("error"):
            send({"v": 1, "id": msg["id"], "ok": False, "error": step["error"]})
            continue
        output = {"text": step.get("text", ""), "finish_reason": "stop", "tool_calls": step.get("tool_calls", [])}
        if output["tool_calls"]:
            output["finish_reason"] = "tool_calls"
        send({"v": 1, "id": msg["id"], "ok": True, "output": output})
    elif op == "shutdown":
        break
"#;

/// Proxy plugin for one area. Every capability forwards one synthetic service call.
const PROXY_STUB: &str = r#"#!/usr/bin/env python3
import json, sys
PLUGIN_ID = "@PLUGIN_ID@"
CAPS = @CAPS@
def send(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()
while True:
    line = sys.stdin.readline()
    if not line:
        break
    msg = json.loads(line)
    op = msg.get("op")
    if op == "hello":
        send({"v": 1, "id": msg["id"], "ok": True, "plugin_id": PLUGIN_ID, "api": 1, "capabilities": CAPS})
    elif op == "invoke":
        request = msg["input"]
        send({"v": 1, "op": "host_call", "id": msg["id"] * 100 + 1, "service": "synthetic." + request["service"], "args": request["args"]})
        reply = json.loads(sys.stdin.readline())
        output = {"nonce": request.get("nonce")}
        if "error" in reply:
            output["host_error"] = reply["error"]
        else:
            output["host"] = reply.get("data")
        send({"v": 1, "id": msg["id"], "ok": True, "output": output})
    elif op == "shutdown":
        break
"#;

/// One plugin of a test: payload, capabilities and the permissions its manifest declares.
struct Spec {
    id: &'static str,
    caps: Vec<&'static str>,
    perms: Vec<&'static str>,
    payload: Vec<u8>,
}

fn target() -> String {
    format!("{}_{}", std::env::consts::OS, std::env::consts::ARCH)
}

fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn proxy(id: &'static str, caps: &[&'static str], perms: &[&'static str]) -> Spec {
    let payload = PROXY_STUB
        .replace("@PLUGIN_ID@", id)
        .replace("@CAPS@", &serde_json::to_string(caps).unwrap())
        .into_bytes();
    Spec {
        id,
        caps: caps.to_vec(),
        perms: perms.to_vec(),
        payload,
    }
}

fn chat(steps: &Value) -> Spec {
    let payload = CHAT_STUB
        .replace("@STEPS@", &serde_json::to_string(steps).unwrap())
        .into_bytes();
    Spec {
        id: CHAT_PLUGIN,
        caps: vec![CHAT],
        perms: vec!["plugin_access"],
        payload,
    }
}

fn catalog(dir: &Path, specs: &[Spec]) -> (PathBuf, String) {
    let plugins: Vec<Value> = specs
        .iter()
        .map(|spec| {
            json!({
                "plugin_id": spec.id,
                "api_version": 1,
                "publisher": "Gideon test fixture",
                "semver": "1.0.0",
                "targets": [target()],
                "binaries": [{
                    "target": target(),
                    "url": format!("https://github.com/acme/plugins/releases/download/v1/{}.py", spec.id),
                    "sha256": sha(&spec.payload),
                    "size": spec.payload.len(),
                }],
                "license": "MIT",
                "permissions": spec.perms,
                "dependencies": [],
                "conflicts": [],
                "entrypoint": format!("bin/{}.py", spec.id),
                "build_source": "https://github.com/acme/plugins/tree/main",
                "support_policy": "test fixture",
                "signature": null,
                "runtime": "python3_script",
                "capabilities": spec.caps,
            })
        })
        .collect();
    let bytes = serde_json::to_vec(&json!({
        "version": 1,
        "repository": "https://github.com/acme/plugins",
        "plugins": plugins,
    }))
    .unwrap();
    let path = dir.join("catalog.json");
    fs::write(&path, &bytes).unwrap();
    (path, sha(&bytes))
}

struct Core {
    root: PathBuf,
    catalog: (PathBuf, String),
    child: Option<Child>,
    counter: u64,
    nonce: u64,
}

impl Core {
    fn boot(dir: &Path, catalog: (PathBuf, String), flags: &[String]) -> Core {
        let mut core = Core {
            root: dir.join("core"),
            catalog,
            child: None,
            counter: 0,
            nonce: 0,
        };
        let flags: Vec<&str> = flags.iter().map(String::as_str).collect();
        core.spawn(&flags);
        core
    }

    fn spawn(&mut self, flags: &[&str]) {
        let log = fs::File::create(self.root.parent().unwrap().join("core.log")).unwrap();
        let mut command = Process::new(env!("CARGO_BIN_EXE_gideon-base"));
        command
            .arg("--root")
            .arg(&self.root)
            .arg("--hub-catalog")
            .arg(&self.catalog.0)
            .arg(&self.catalog.1)
            .arg("--plugin-python")
            .arg(PYTHON)
            .arg("--virtual-input")
            .arg("--commands-sandbox")
            .args(flags)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(log);
        self.child = Some(command.spawn().expect("spawn Core"));
        let deadline = Instant::now() + Duration::from_secs(10);
        while Instant::now() < deadline {
            let ready = UnixStream::connect(self.root.join("core.sock")).is_ok()
                && self.call(json!({"op": "snapshot"}))["code"] == "ok";
            if ready {
                return;
            }
            thread::sleep(Duration::from_millis(20));
        }
        panic!("Core did not start");
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

    fn revision(&mut self) -> u64 {
        self.snap()["plugins"]["revision"].as_u64().unwrap()
    }

    fn wait_for(&mut self, what: &str, check: impl Fn(&Value) -> bool) -> Value {
        let deadline = Instant::now() + Duration::from_secs(15);
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

    fn install(&mut self, plugin: &str, payload: &[u8]) {
        let snap = self.snap();
        let entry = snap["hub"]["entries"]
            .as_array()
            .unwrap()
            .iter()
            .find(|e| e["plugin_id"] == plugin)
            .unwrap()
            .clone();
        let manifest_sha = entry["manifest_sha256"].as_str().unwrap().to_owned();
        let approval = snap["hub"]["approval_revision"].as_u64().unwrap();
        ok(&self.call(json!({
            "op": "hub_approve", "revision": approval, "plugin_id": plugin,
            "manifest_sha256": manifest_sha, "permissions": entry["permissions"],
            "publisher_unverified_ack": true,
        })));
        let approval = self.snap()["hub"]["approval_revision"].as_u64().unwrap();
        ok(&self.call(json!({
            "op": "hub_begin", "revision": approval, "plugin_id": plugin,
            "manifest_sha256": manifest_sha,
        })));
        let import_id = self.snap()["hub"]["import"]["import_id"]
            .as_str()
            .unwrap()
            .to_owned();
        for (index, chunk) in payload.chunks(512).enumerate() {
            let hex: String = chunk.iter().fold(String::new(), |mut hex, b| {
                use std::fmt::Write as _;
                let _ = write!(hex, "{b:02x}");
                hex
            });
            ok(&self.call(json!({
                "op": "hub_chunk", "import_id": import_id, "offset": index * 512, "hex": hex,
            })));
        }
        ok(&self.call(json!({"op": "hub_finish", "import_id": import_id})));
        let install_revision = self.snap()["hub"]["install_revision"].as_u64().unwrap();
        ok(&self.call(json!({
            "op": "hub_install", "revision": install_revision, "plugin_id": plugin,
            "manifest_sha256": manifest_sha,
        })));
    }

    fn enable(&mut self, plugin: &str) {
        let revision = self.revision();
        let reply =
            self.call(json!({"op": "plugin_enable", "revision": revision, "plugin_id": plugin}));
        assert!(
            reply["code"] == "ok" || reply["code"] == "already_enabled",
            "{reply}"
        );
        let id = plugin.to_owned();
        self.wait_for(&format!("running {plugin}"), move |s| {
            s["plugins"]["items"]
                .as_array()
                .unwrap()
                .iter()
                .any(|i| i["plugin_id"] == id.as_str() && i["state"] == "running")
        });
    }

    fn revoke(&mut self, plugin: &str) {
        let revision = self.revision();
        ok(&self.call(json!({"op": "plugin_revoke", "revision": revision, "plugin_id": plugin})));
    }

    /// Invokes one capability whose plugin forwards `service`, and waits for its result.
    /// Returns the proxy output: `{nonce, host}` or `{nonce, host_error}`.
    fn service(&mut self, capability: &str, service: &str, args: Value) -> Value {
        self.nonce += 1;
        let nonce = self.nonce;
        let reply = self.call(json!({
            "op": "capability_invoke",
            "capability": capability,
            "input": {"service": service, "args": args, "nonce": nonce},
            "deadline_ms": 5000,
        }));
        ok(&reply);
        let snap = self.wait_for("capability result", move |s| {
            s["capability_result"]["output"]["nonce"] == nonce
        });
        snap["capability_result"]["output"].clone()
    }

    /// Successful reply of a service call (`host`), or a panic with the host error.
    fn host(&mut self, capability: &str, service: &str, args: Value) -> Value {
        let out = self.service(capability, service, args);
        assert!(out["host_error"].is_null(), "unexpected host error: {out}");
        out["host"].clone()
    }

    fn host_error(&mut self, capability: &str, service: &str, args: Value) -> String {
        let out = self.service(capability, service, args);
        out["host_error"]
            .as_str()
            .unwrap_or_else(|| panic!("expected host_error for {service}: {out}"))
            .to_owned()
    }

    fn world(&self) -> Value {
        let path = self
            .root
            .parent()
            .unwrap()
            .join("home/synthetic/world.json");
        serde_json::from_slice(&fs::read(path).expect("world.json")).expect("world JSON")
    }

    fn agent(&mut self) -> Value {
        self.snap()["agent"].clone()
    }

    /// Polls the agent block until `check` holds; the poll itself never changes state.
    fn wait_agent(&mut self, what: &str, check: impl Fn(&Value) -> bool) -> Value {
        let deadline = Instant::now() + Duration::from_secs(15);
        loop {
            let agent = self.agent();
            if check(&agent) {
                return agent;
            }
            assert!(
                Instant::now() < deadline,
                "timed out waiting for {what}: {agent}"
            );
            thread::sleep(Duration::from_millis(30));
        }
    }

    fn wait_state(&mut self, state: &str) -> Value {
        let state = state.to_owned();
        self.wait_agent(&state.clone(), move |a| a["state"] == state.as_str())
    }

    fn proposals(&mut self) -> Vec<Value> {
        self.snap()["tool_proposals"].as_array().unwrap().clone()
    }

    fn proposal_for(&mut self, tool: &str) -> Value {
        self.proposals()
            .into_iter()
            .rev()
            .find(|p| p["tool"] == tool)
            .unwrap_or_else(|| panic!("no proposal for {tool}"))
    }

    fn decide(&mut self, proposal_id: &str, decision: &str) -> Value {
        self.call(json!({"op": "tool_decide", "proposal_id": proposal_id, "decision": decision}))
    }

    fn start(&mut self, goal: &str) -> Value {
        self.call(json!({"op": "agent_start", "goal": goal}))
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

fn ok(response: &Value) -> &Value {
    assert_eq!(response["code"], "ok", "unexpected response: {response}");
    response
}

/// Fresh directory per test; the synthetic home lives beside the private root.
fn setup(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("gideon-c4-{name}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("home")).unwrap();
    dir
}

fn synthetic_flags(dir: &Path) -> Vec<String> {
    vec![
        "--agent-synthetic".into(),
        "--home".into(),
        dir.join("home").display().to_string(),
    ]
}

/// Boots the Core, installs every spec and enables the listed plugins.
fn start(dir: &Path, flags: &[String], specs: &[Spec], enable: &[&str]) -> Core {
    let cat = catalog(dir, specs);
    let mut core = Core::boot(dir, cat, flags);
    for spec in specs {
        core.install(spec.id, &spec.payload);
    }
    for id in enable {
        core.enable(id);
    }
    core
}

fn tool(name: &str, args: Value) -> Value {
    json!({"id": format!("c_{name}"), "name": name, "arguments": args})
}

fn turn_tools(calls: Vec<Value>) -> Value {
    json!({"tool_calls": calls})
}

/// The n-th tool entry of the snapshot's steps (chat entries are skipped).
fn tool_step(agent: &Value, index: usize) -> Value {
    agent["steps"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|s| s["kind"] == "tool")
        .nth(index)
        .cloned()
        .unwrap_or(Value::Null)
}

fn event_kinds(core: &mut Core) -> Vec<String> {
    core.snap()["events"]
        .as_array()
        .unwrap()
        .iter()
        .map(|e| e["kind"].as_str().unwrap().to_owned())
        .collect()
}

#[test]
fn services_do_not_exist_without_the_flag() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("noflag");
    let specs = [proxy(
        "screen_observe",
        &["screen_observe.capture"],
        &["screen_observe"],
    )];
    let mut core = start(&dir, &[], &specs, &["screen_observe"]);
    assert_eq!(
        core.host_error("screen_observe.capture", "screen.capture", json!({})),
        "unknown_service"
    );
    assert_eq!(
        core.host_error(
            "screen_observe.capture",
            "input.click",
            json!({"epoch": 1, "element": "apply"})
        ),
        "unknown_service"
    );
    assert!(
        !dir.join("home/synthetic").exists(),
        "world written without the flag"
    );
}

#[test]
fn permission_is_checked_per_area_and_unknown_names_are_refused() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("perms");
    let flags = synthetic_flags(&dir);
    let specs = [
        proxy("screen_observe", &["screen_observe.capture"], &[]),
        proxy(
            "computer_control",
            &["computer_control.act"],
            &["input_control"],
        ),
    ];
    let mut core = start(
        &dir,
        &flags,
        &specs,
        &["screen_observe", "computer_control"],
    );
    assert_eq!(
        core.host_error("screen_observe.capture", "screen.capture", json!({})),
        "permission_denied"
    );
    assert_eq!(
        core.host_error("computer_control.act", "screen.capture", json!({})),
        "permission_denied"
    );
    assert_eq!(
        core.host_error("computer_control.act", "audio.routes", json!({})),
        "permission_denied"
    );
    assert_eq!(
        core.host_error("computer_control.act", "synthetic.nope", json!({})),
        "unknown_service"
    );
    let reply = core.host("computer_control.act", "input.a11y_tree", json!({}));
    assert_eq!(reply["epoch"], 1);
    assert_eq!(reply["backend"], "synthetic");
}

#[test]
fn screen_capture_is_evidence_with_a_bounded_reply() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("capture");
    let flags = synthetic_flags(&dir);
    let specs = [proxy(
        "screen_observe",
        &["screen_observe.capture"],
        &["screen_observe"],
    )];
    let mut core = start(&dir, &flags, &specs, &["screen_observe"]);
    let out = core.service("screen_observe.capture", "screen.capture", json!({}));
    assert!(out["host_error"].is_null(), "{out}");
    let reply = &out["host"];
    assert_eq!(reply["backend"], "synthetic");
    assert_eq!(reply["epoch"], 1);
    assert_eq!(
        (reply["width"].as_u64(), reply["height"].as_u64()),
        (Some(1280), Some(720))
    );
    assert_eq!(reply["sha256"].as_str().unwrap().len(), 64);
    assert_eq!(reply["regions"].as_array().unwrap().len(), 3);
    assert!(reply["regions"][0].get("role").is_some());
    assert!(serde_json::to_vec(reply).unwrap().len() <= 4096);
    assert!(event_kinds(&mut core).contains(&"screen_capture".to_owned()));
}

#[test]
fn stale_epoch_has_no_effect_and_relread_shows_the_new_epoch() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("stale");
    let flags = synthetic_flags(&dir);
    let specs = [proxy(
        "computer_control",
        &["computer_control.tree", "computer_control.act"],
        &["input_control"],
    )];
    let mut core = start(&dir, &flags, &specs, &["computer_control"]);
    let cap = "computer_control.act";
    let click = core.host(cap, "input.click", json!({"epoch": 1, "element": "apply"}));
    assert_eq!(
        (click["verified"].as_bool(), click["epoch"].as_u64()),
        (Some(true), Some(2))
    );
    assert_eq!(
        core.host_error(cap, "input.click", json!({"epoch": 1, "element": "cancel"})),
        "stale_screen"
    );
    let world = core.world();
    assert_eq!(world["screen"]["last_click"], "apply");
    assert_eq!(world["screen"]["epoch"], 2);
    // Relread of the tree gives the epoch the next action must carry.
    let tree = core.host("computer_control.tree", "input.a11y_tree", json!({}));
    assert_eq!(tree["epoch"], 2);
    assert_eq!(tree["elements"].as_array().unwrap().len(), 3);
    core.host(cap, "input.focus", json!({"epoch": 2, "element": "field"}));
    core.host(cap, "input.type", json!({"epoch": 3, "text": "ola"}));
    assert_eq!(core.world()["screen"]["text"], "ola");
    core.host(cap, "input.focus", json!({"epoch": 4, "element": "apply"}));
    assert_eq!(
        core.host_error(cap, "input.type", json!({"epoch": 5, "text": "x"})),
        "no_focus"
    );
    core.host(cap, "input.key", json!({"epoch": 5, "key": "enter"}));
    assert_eq!(
        core.host_error(cap, "input.key", json!({"epoch": 5, "key": "tab"})),
        "stale_screen"
    );
    assert_eq!(core.world()["screen"]["last_key"], "enter");
    assert_eq!(core.world()["screen"]["epoch"], 6);
}

#[test]
fn camera_needs_opt_in_and_the_indicator_follows_it() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("camera");
    let flags = synthetic_flags(&dir);
    let specs = [proxy(
        "camera_gesture",
        &[
            "camera_gesture.state",
            "camera_gesture.optin",
            "camera_gesture.capture",
            "camera_gesture.gestures",
        ],
        &["camera_capture"],
    )];
    let mut core = start(&dir, &flags, &specs, &["camera_gesture"]);
    let cap = "camera_gesture.capture";
    assert_eq!(
        core.host_error(cap, "camera.capture", json!({})),
        "opt_in_required"
    );
    assert_eq!(
        core.host_error(cap, "camera.gestures", json!({})),
        "opt_in_required"
    );
    assert_eq!(
        core.host("camera_gesture.state", "camera.state", json!({}))["indicator"],
        false
    );
    core.host(cap, "camera.optin", json!({"enabled": true}));
    assert_eq!(core.world()["camera"]["indicator"], true);
    let frame = core.host(cap, "camera.capture", json!({}));
    assert_eq!(frame["frame_seq"], 1);
    let gestures = core.host(cap, "camera.gestures", json!({}));
    assert_eq!(gestures["supported"], json!(["wave", "thumbs_up"]));
    core.host(cap, "camera.optin", json!({"enabled": false}));
    let camera = core.world()["camera"].clone();
    assert_eq!(
        (camera["opt_in"].as_bool(), camera["indicator"].as_bool()),
        (Some(false), Some(false))
    );
    assert_eq!(camera["frame_seq"], 0);
}

#[test]
fn recording_needs_the_indicator_and_an_explicit_start() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("mic");
    let flags = synthetic_flags(&dir);
    let specs = [proxy(
        "mic_advanced",
        &[
            "mic_advanced.state",
            "mic_advanced.configure",
            "mic_advanced.monitor",
            "mic_advanced.record",
        ],
        &["mic_config"],
    )];
    let mut core = start(&dir, &flags, &specs, &["mic_advanced"]);
    let cap = "mic_advanced.record";
    assert_eq!(
        core.host_error(cap, "mic.record_start", json!({})),
        "indicator_off"
    );
    assert_eq!(
        core.host_error(cap, "mic.record_stop", json!({})),
        "not_recording"
    );
    core.host(cap, "mic.monitor", json!({"enabled": true}));
    assert_eq!(core.world()["mic"]["indicator"], true);
    core.host(cap, "mic.record_start", json!({}));
    let configured = core.host(cap, "mic.configure", json!({"gain": 70, "filter": "voice"}));
    assert_eq!(
        (configured["gain"].as_u64(), configured["filter"].as_str()),
        (Some(70), Some("voice"))
    );
    assert_eq!(
        core.host_error(cap, "mic.record_start", json!({})),
        "already_recording"
    );
    // Leaving monitor while recording keeps the indicator on; stopping the recording then clears it.
    core.host(cap, "mic.monitor", json!({"enabled": false}));
    assert_eq!(core.world()["mic"]["indicator"], true);
    core.host(cap, "mic.record_stop", json!({}));
    let mic = core.world()["mic"].clone();
    assert_eq!(
        (mic["recording"].as_bool(), mic["indicator"].as_bool()),
        (Some(false), Some(false))
    );
}

#[test]
fn audio_is_typed_ranged_and_never_touches_the_base_sentinel() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("audio");
    let flags = synthetic_flags(&dir);
    let specs = [proxy(
        "audio_advanced",
        &["audio_advanced.state", "audio_advanced.act"],
        &["audio_route"],
    )];
    let mut core = start(&dir, &flags, &specs, &["audio_advanced"]);
    let cap = "audio_advanced.act";
    let routes = core.host(cap, "audio.routes", json!({}));
    assert_eq!(routes["route"], "speakers");
    core.host(cap, "audio.set_route", json!({"route": "bluetooth"}));
    assert_eq!(
        core.host_error(cap, "audio.set_route", json!({"route": "nowhere"})),
        "unknown_route"
    );
    assert_eq!(
        core.host_error(cap, "audio.set_route", json!({"route": "Bad Route"})),
        "invalid_host_call"
    );
    core.host(
        cap,
        "audio.app_volume",
        json!({"app": "player", "volume": 80}),
    );
    assert_eq!(
        core.host_error(
            cap,
            "audio.app_volume",
            json!({"app": "player", "volume": 101})
        ),
        "invalid_host_call"
    );
    assert_eq!(
        core.host_error(
            cap,
            "audio.app_volume",
            json!({"app": "ghost", "volume": 5})
        ),
        "unknown_app"
    );
    assert_eq!(
        core.host_error(cap, "audio.eq", json!({"preset": "rock"})),
        "invalid_host_call"
    );
    core.host(cap, "audio.eq", json!({"preset": "bass"}));
    core.host(cap, "audio.denoise", json!({"enabled": true}));
    let world = core.world();
    assert_eq!(world["audio"]["route"], "bluetooth");
    assert_eq!(world["audio"]["apps"][0]["volume"], 80);
    assert_eq!(
        (
            world["audio"]["eq"].as_str(),
            world["audio"]["denoise"].as_bool()
        ),
        (Some("bass"), Some(true))
    );
    // Sentinel: C4 audio, mic and camera work never write the Base devices.
    assert_eq!(
        world["base"],
        json!({"mic_state": "base-idle", "speaker_state": "base-idle"})
    );
    assert_eq!(world["mic"]["recording"], false);
    assert_eq!(world["camera"]["opt_in"], false);
}

#[test]
fn arguments_are_strict_and_replies_are_capped() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("args");
    let flags = synthetic_flags(&dir);
    let specs = [proxy(
        "computer_control",
        &["computer_control.tree", "computer_control.act"],
        &["input_control"],
    )];
    let mut core = start(&dir, &flags, &specs, &["computer_control"]);
    let cap = "computer_control.act";
    assert_eq!(
        core.host_error(
            cap,
            "input.click",
            json!({"epoch": 1, "element": "apply", "extra": 1})
        ),
        "invalid_host_call"
    );
    assert_eq!(
        core.host_error(cap, "input.click", json!({"element": "apply"})),
        "invalid_host_call"
    );
    assert_eq!(
        core.host_error(
            cap,
            "input.type",
            json!({"epoch": 1, "text": "x".repeat(65)})
        ),
        "invalid_host_call"
    );
    assert_eq!(
        core.host_error(cap, "input.type", json!({"epoch": 1, "text": "a\u{7}"})),
        "invalid_host_call"
    );
    // 64 bytes is the limit; the request is valid and fails only for lack of focus.
    assert_eq!(
        core.host_error(
            cap,
            "input.type",
            json!({"epoch": 1, "text": "x".repeat(64)})
        ),
        "no_focus"
    );
    assert_eq!(
        core.host_error(cap, "input.a11y_tree", json!({"pad": "y".repeat(2000)})),
        "invalid_host_call"
    );
}

#[test]
fn large_worlds_are_capped_in_replies_and_files() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("limits");
    let flags = synthetic_flags(&dir);
    let specs = [
        proxy(
            "screen_observe",
            &["screen_observe.capture"],
            &["screen_observe"],
        ),
        proxy(
            "computer_control",
            &["computer_control.act"],
            &["input_control"],
        ),
    ];
    let mut core = start(
        &dir,
        &flags,
        &specs,
        &["screen_observe", "computer_control"],
    );
    // One write creates world.json (focus on the textbox); then 60 long elements replace the list.
    core.host(
        "computer_control.act",
        "input.focus",
        json!({"epoch": 1, "element": "field"}),
    );
    let mut world = core.world();
    let mut elements =
        vec![json!({"id": "field", "role": "textbox", "name": "Campo", "x": 40, "y": 40})];
    elements.extend((0..59).map(|i| {
        json!({"id": format!("e{i}"), "role": "button", "name": "n".repeat(60), "x": i, "y": i})
    }));
    world["screen"]["elements"] = json!(elements);
    fs::write(
        dir.join("home/synthetic/world.json"),
        serde_json::to_vec(&world).unwrap(),
    )
    .unwrap();
    let out = core.service("screen_observe.capture", "screen.capture", json!({}));
    let reply = &out["host"];
    assert_eq!(reply["regions"].as_array().unwrap().len(), 16);
    assert_eq!(reply["truncated"], true);
    assert!(serde_json::to_vec(reply).unwrap().len() <= 4096);
    // A world file over 64 KiB is refused, not read.
    fs::write(dir.join("home/synthetic/world.json"), vec![b' '; 70 * 1024]).unwrap();
    assert_eq!(
        core.host_error("screen_observe.capture", "screen.capture", json!({})),
        "world_unavailable"
    );
}

#[test]
fn c3_app_state_migrates_into_the_world_and_the_mirror_follows() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("migrate");
    let flags = synthetic_flags(&dir);
    fs::create_dir_all(dir.join("home/synthetic")).unwrap();
    fs::write(
        dir.join("home/synthetic/app.json"),
        br#"{"epoch":1,"counter":5,"text":"old","published":false}"#,
    )
    .unwrap();
    let specs = [proxy(
        "audio_advanced",
        &["audio_advanced.act"],
        &["audio_route"],
    )];
    let mut core = start(&dir, &flags, &specs, &["audio_advanced"]);
    core.host(
        "audio_advanced.act",
        "audio.set_route",
        json!({"route": "headphones"}),
    );
    let world = core.world();
    assert_eq!(
        (
            world["app"]["counter"].as_u64(),
            world["app"]["text"].as_str()
        ),
        (Some(5), Some("old"))
    );
    assert_eq!(world["audio"]["route"], "headphones");
    let mirror: Value =
        serde_json::from_slice(&fs::read(dir.join("home/synthetic/app.json")).unwrap()).unwrap();
    assert_eq!(mirror["counter"], 5);
}

#[test]
fn agent_bridge_reads_then_an_approved_click_verifies() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("bridge-happy");
    let flags = synthetic_flags(&dir);
    let steps = json!([
        turn_tools(vec![tool("screen_capture", json!({}))]),
        turn_tools(vec![tool("ui_click", json!({"epoch": 1, "element": "apply"}))]),
        {"text": "clicked"},
    ]);
    let specs = [
        chat(&steps),
        proxy(
            "screen_observe",
            &["screen_observe.capture"],
            &["screen_observe"],
        ),
        proxy(
            "computer_control",
            &["computer_control.tree", "computer_control.act"],
            &["input_control"],
        ),
    ];
    let mut core = start(
        &dir,
        &flags,
        &specs,
        &[CHAT_PLUGIN, "screen_observe", "computer_control"],
    );
    assert_eq!(core.start("click the apply button")["code"], "ok");
    let agent = core.wait_state("awaiting_approval");
    assert_eq!(tool_step(&agent, 0)["tool"], "screen_capture");
    assert_eq!(tool_step(&agent, 0)["state"], "done");
    let proposal = core.proposal_for("ui_click");
    assert_eq!(proposal["state"], "pending");
    assert_eq!(proposal["plugin_id"], CHAT_PLUGIN);
    ok(&core.decide(proposal["proposal_id"].as_str().unwrap(), "authorize"));
    let agent = core.wait_state("done");
    assert_eq!(agent["answer"], "clicked");
    assert_eq!(core.world()["screen"]["last_click"], "apply");
    assert_eq!(core.world()["screen"]["epoch"], 2);
    let kinds = event_kinds(&mut core);
    assert!(kinds.contains(&"screen_capture".to_owned()), "{kinds:?}");
    assert!(kinds.contains(&"input_action".to_owned()), "{kinds:?}");
}

#[test]
fn agent_bridge_reports_capability_unavailable_for_a_stopped_owner() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("bridge-stopped");
    let flags = synthetic_flags(&dir);
    let steps = json!([
        turn_tools(vec![tool("ui_tree", json!({}))]),
        {"text": "no tree"},
    ]);
    let specs = [
        chat(&steps),
        proxy(
            "computer_control",
            &["computer_control.tree"],
            &["input_control"],
        ),
    ];
    // The owner is installed and approved but never enabled: its capability is not running.
    let mut core = start(&dir, &flags, &specs, &[CHAT_PLUGIN]);
    core.start("read the tree");
    let agent = core.wait_state("done");
    let step = tool_step(&agent, 0);
    assert_eq!(step["code"], "capability_unavailable");
    assert_eq!(step["state"], "denied");
    assert!(!dir.join("home/synthetic/world.json").exists());
}

#[test]
fn agent_bridge_reports_permission_revoked_after_a_mid_run_revoke() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("bridge-revoke");
    let flags = synthetic_flags(&dir);
    let steps = json!([
        turn_tools(vec![tool("ui_click", json!({"epoch": 1, "element": "apply"}))]),
        {"text": "stopped"},
    ]);
    let specs = [
        chat(&steps),
        proxy(
            "computer_control",
            &["computer_control.act"],
            &["input_control"],
        ),
    ];
    let mut core = start(&dir, &flags, &specs, &[CHAT_PLUGIN, "computer_control"]);
    core.start("click apply");
    let agent = core.wait_state("awaiting_approval");
    assert_eq!(tool_step(&agent, 0)["tool"], "ui_click");
    // The owner loses its permission while the proposal waits for the user.
    core.revoke("computer_control");
    let proposal = core.proposal_for("ui_click");
    ok(&core.decide(proposal["proposal_id"].as_str().unwrap(), "authorize"));
    let agent = core.wait_state("done");
    assert_eq!(agent["answer"], "stopped");
    assert_eq!(tool_step(&agent, 0)["code"], "permission_revoked");
    let proposal = core.proposal_for("ui_click");
    assert_eq!(proposal["reason"], "permission_revoked");
    assert_eq!(proposal["state"], "failed");
    // Refused before any write: no world file exists, so the click never happened.
    assert!(!dir.join("home/synthetic/world.json").exists());
}

#[test]
fn agent_bridge_stale_screen_is_reported_before_any_proposal() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("bridge-stale");
    let flags = synthetic_flags(&dir);
    let steps = json!([
        turn_tools(vec![tool("ui_click", json!({"epoch": 99, "element": "apply"}))]),
        {"text": "retry later"},
    ]);
    let specs = [
        chat(&steps),
        proxy(
            "computer_control",
            &["computer_control.act"],
            &["input_control"],
        ),
    ];
    let mut core = start(&dir, &flags, &specs, &[CHAT_PLUGIN, "computer_control"]);
    core.start("click apply");
    let agent = core.wait_state("done");
    let step = tool_step(&agent, 0);
    assert_eq!(step["state"], "stale");
    assert_eq!(step["code"], "stale_screen");
    assert!(core.proposals().iter().all(|p| p["tool"] != "ui_click"));
}

#[test]
fn agent_bridge_tools_do_not_exist_without_the_flag() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("bridge-noflag");
    let steps = json!([
        turn_tools(vec![tool("screen_capture", json!({}))]),
        {"text": "done"},
    ]);
    let specs = [
        chat(&steps),
        proxy(
            "screen_observe",
            &["screen_observe.capture"],
            &["screen_observe"],
        ),
    ];
    let mut core = start(&dir, &[], &specs, &[CHAT_PLUGIN, "screen_observe"]);
    core.start("capture");
    let agent = core.wait_state("done");
    assert_eq!(tool_step(&agent, 0)["code"], "unknown_tool");
    assert!(!dir.join("home/synthetic").exists());
}
