//! C3 agent runtime. The real Core binary runs with an inline scripted chat plugin: each chat
//! call consumes one step of the script (text, tool_calls, usage, delay or error). The synthetic
//! app and destructive switches are only passed to the binary in the tests that need them.
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
const PLUGIN: &str = "fakellm";
const CHAT: &str = "fakellm.chat";

/// Scripted chat plugin. The script is embedded at install time; one step per chat invoke.
const STUB: &str = r#"#!/usr/bin/env python3
import json, sys, time
PLUGIN_ID = "@PLUGIN_ID@"
CAPS = @CAPS@
STEPS = json.loads(r'''@STEPS@''')
calls = 0
def send(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()
for line in sys.stdin:
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
        if step.get("usage") is not None:
            output["usage"] = step["usage"]
        send({"v": 1, "id": msg["id"], "ok": True, "output": output})
    elif op == "shutdown":
        break
"#;

fn target() -> String {
    format!("{}_{}", std::env::consts::OS, std::env::consts::ARCH)
}
fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

/// Builds the chat plugin payload for one scripted conversation.
fn chat_plugin(steps: &Value) -> Vec<u8> {
    STUB.replace("@PLUGIN_ID@", PLUGIN)
        .replace("@CAPS@", &serde_json::to_string(&[CHAT]).unwrap())
        .replace("@STEPS@", &serde_json::to_string(steps).unwrap())
        .into_bytes()
}

fn catalog(dir: &Path, payload: &[u8]) -> (PathBuf, String) {
    let bytes = serde_json::to_vec(&json!({
        "version": 1,
        "repository": "https://github.com/acme/plugins",
        "plugins": [{
            "plugin_id": PLUGIN,
            "api_version": 1,
            "publisher": "Gideon test fixture",
            "semver": "1.0.0",
            "targets": [target()],
            "binaries": [{
                "target": target(),
                "url": format!("https://github.com/acme/plugins/releases/download/v1/{PLUGIN}.py"),
                "sha256": sha(payload),
                "size": payload.len(),
            }],
            "license": "MIT",
            "permissions": ["plugin_access"],
            "dependencies": [],
            "conflicts": [],
            "entrypoint": format!("bin/{PLUGIN}.py"),
            "build_source": "https://github.com/acme/plugins/tree/main",
            "support_policy": "test fixture",
            "signature": null,
            "runtime": "python3_script",
            "capabilities": [CHAT],
        }],
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
    log: PathBuf,
}
impl Core {
    fn boot(dir: &Path, catalog: (PathBuf, String), flags: &[&str]) -> Core {
        fs::create_dir_all(dir).unwrap();
        let mut core = Core {
            root: dir.join("core"),
            catalog,
            child: None,
            counter: 0,
            log: dir.join("core.log"),
        };
        core.spawn(flags);
        core
    }
    fn spawn(&mut self, flags: &[&str]) {
        let log = fs::File::create(&self.log).unwrap();
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
            // A stale socket left by a killed Core refuses connections until the new one binds.
            let ready = UnixStream::connect(self.root.join("core.sock")).is_ok()
                && self.call(json!({"op": "snapshot"}))["code"] == "ok";
            if ready {
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
    fn install(&mut self, payload: &[u8]) {
        let snap = self.snap();
        let entry = snap["hub"]["entries"]
            .as_array()
            .unwrap()
            .iter()
            .find(|e| e["plugin_id"] == PLUGIN)
            .unwrap()
            .clone();
        let manifest_sha = entry["manifest_sha256"].as_str().unwrap().to_owned();
        let approval = snap["hub"]["approval_revision"].as_u64().unwrap();
        ok(&self.call(json!({
            "op": "hub_approve", "revision": approval, "plugin_id": PLUGIN,
            "manifest_sha256": manifest_sha, "permissions": entry["permissions"],
            "publisher_unverified_ack": true,
        })));
        let approval = self.snap()["hub"]["approval_revision"].as_u64().unwrap();
        ok(&self.call(json!({
            "op": "hub_begin", "revision": approval, "plugin_id": PLUGIN,
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
            "op": "hub_install", "revision": install_revision, "plugin_id": PLUGIN,
            "manifest_sha256": manifest_sha,
        })));
    }
    fn enable_running(&mut self) {
        let revision = self.revision();
        let reply =
            self.call(json!({"op": "plugin_enable", "revision": revision, "plugin_id": PLUGIN}));
        assert!(
            reply["code"] == "ok" || reply["code"] == "already_enabled",
            "{reply}"
        );
        self.wait_for("running chat plugin", |s| {
            s["plugins"]["items"]
                .as_array()
                .unwrap()
                .iter()
                .any(|i| i["plugin_id"] == PLUGIN && i["state"] == "running")
        });
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
    fn app(&self) -> Value {
        let path = self.root.parent().unwrap().join("home/synthetic/app.json");
        serde_json::from_slice(&fs::read(path).unwrap_or_else(|_| b"{}".to_vec()))
            .unwrap_or(json!({}))
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
    let dir = std::env::temp_dir().join(format!("gideon-agent-{name}-{}", std::process::id()));
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

fn with_core(dir: &Path, steps: Value, flags: &[&str]) -> Core {
    let payload = chat_plugin(&steps);
    let cat = catalog(dir, &payload);
    let mut core = Core::boot(dir, cat, flags);
    core.install(&payload);
    core.enable_running();
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

fn step_states(agent: &Value) -> Vec<String> {
    agent["steps"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| {
            format!(
                "{}:{}",
                s["kind"].as_str().unwrap(),
                s["state"].as_str().unwrap()
            )
        })
        .collect()
}

#[test]
fn start_without_a_chat_plugin_is_llm_unavailable() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("unavailable");
    let cat = catalog(&dir, b"unused");
    let mut core = Core::boot(&dir, cat, &[]);
    assert_eq!(core.start("hello")["code"], "llm_unavailable");
    assert!(core.snap()["agent"].is_null());
}

#[test]
fn start_inputs_are_strict_and_checked_before_any_chat() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("inputs");
    let cat = catalog(&dir, b"unused");
    let mut core = Core::boot(&dir, cat, &[]);
    assert_eq!(core.start("")["code"], "invalid_input");
    assert_eq!(core.start(&"x".repeat(1025))["code"], "invalid_input");
    assert_eq!(core.start("bad\u{7}control")["code"], "invalid_input");
    let reply = core.call(json!({"op": "agent_start", "goal": "hi", "grant": true}));
    assert_ne!(reply["code"], "ok", "unknown field accepted: {reply}");
    assert_eq!(
        core.call(json!({"op": "agent_test_bump"}))["code"],
        "unknown_operation"
    );
    assert_eq!(
        core.call(json!({"op": "agent_abort", "run_id": "run_x"}))["code"],
        "unknown_run"
    );
}

#[test]
fn read_then_approved_increment_verifies_and_answers() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("happy");
    let flags = synthetic_flags(&dir);
    let flags: Vec<&str> = flags.iter().map(String::as_str).collect();
    let steps = json!([
        turn_tools(vec![tool("synth_screen_read", json!({}))]),
        turn_tools(vec![tool("synth_counter_inc", json!({"epoch": 1}))]),
        {"text": "counter is now 1"},
    ]);
    let mut core = with_core(&dir, steps, &flags);
    assert_eq!(core.start("GOAL-MARKER-7f3 bump the counter")["code"], "ok");
    let agent = core.wait_state("awaiting_approval");
    assert_eq!(tool_step(&agent, 0)["tool"], "synth_screen_read");
    let proposal = core.proposal_for("synth_counter_inc");
    assert_eq!(proposal["state"], "pending");
    assert_eq!(proposal["run_id"], agent["run_id"]);
    assert_eq!(proposal["step"], 2);
    // The snapshot never carries the goal text or observation content.
    assert!(!core.agent().to_string().contains("GOAL-MARKER"));
    ok(&core.decide(proposal["proposal_id"].as_str().unwrap(), "authorize"));
    let agent = core.wait_state("done");
    assert_eq!(agent["answer"], "counter is now 1");
    assert_eq!(core.app()["counter"], 1);
    assert_eq!(core.app()["published"], false);
    let ids: Vec<u64> = agent["steps"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| s["invocation_id"].as_u64().unwrap())
        .collect();
    assert!(
        ids.windows(2).all(|w| w[0] < w[1]),
        "ids not increasing: {ids:?}"
    );
    assert_eq!(
        step_states(&agent),
        [
            "chat:done",
            "tool:done",
            "chat:done",
            "tool:done",
            "chat:done"
        ]
    );
    let events: Vec<String> = core.snap()["events"]
        .as_array()
        .unwrap()
        .iter()
        .map(|e| e["kind"].as_str().unwrap().to_owned())
        .collect();
    assert!(events.contains(&"agent_started".to_owned()));
    assert!(events.contains(&"agent_done".to_owned()));
}

#[test]
fn denial_leaves_the_app_unchanged_and_reaches_the_model() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("deny");
    let flags = synthetic_flags(&dir);
    let flags: Vec<&str> = flags.iter().map(String::as_str).collect();
    let steps = json!([
        turn_tools(vec![tool("synth_counter_inc", json!({"epoch": 1}))]),
        {"text": "understood, not changed"},
    ]);
    let mut core = with_core(&dir, steps, &flags);
    core.start("try it");
    core.wait_state("awaiting_approval");
    let proposal = core.proposal_for("synth_counter_inc");
    ok(&core.decide(proposal["proposal_id"].as_str().unwrap(), "deny"));
    assert_eq!(core.proposal_for("synth_counter_inc")["state"], "denied");
    assert_eq!(
        core.proposal_for("synth_counter_inc")["reason"],
        "user_denied"
    );
    let agent = core.wait_state("done");
    assert_eq!(agent["answer"], "understood, not changed");
    assert!(core.app()["counter"].is_null() || core.app()["counter"] == 0);
}

#[test]
fn abort_during_approval_cancels_the_proposal_without_effect() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("abort");
    let flags = synthetic_flags(&dir);
    let flags: Vec<&str> = flags.iter().map(String::as_str).collect();
    let steps = json!([turn_tools(vec![tool(
        "synth_counter_inc",
        json!({"epoch": 1})
    )])]);
    let mut core = with_core(&dir, steps, &flags);
    core.start("abort me");
    let agent = core.wait_state("awaiting_approval");
    let run_id = agent["run_id"].as_str().unwrap().to_owned();
    assert_eq!(
        core.call(json!({"op": "agent_abort", "run_id": run_id}))["code"],
        "ok"
    );
    let agent = core.wait_state("aborted");
    assert_eq!(agent["error"], "aborted");
    assert_eq!(core.proposal_for("synth_counter_inc")["state"], "cancelled");
    assert!(core.app()["counter"].is_null() || core.app()["counter"] == 0);
    assert_eq!(
        core.call(json!({"op": "agent_abort", "run_id": run_id}))["code"],
        "unknown_run"
    );
}

#[test]
fn destructive_publish_waits_and_never_executes_in_development() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("destructive");
    let flags = synthetic_flags(&dir);
    let flags: Vec<&str> = flags.iter().map(String::as_str).collect();
    let steps = json!([turn_tools(vec![tool("synth_publish", json!({}))])]);
    let mut core = with_core(&dir, steps, &flags);
    core.start("publish it");
    let agent = core.wait_state("awaiting_approval");
    assert_eq!(tool_step(&agent, 0)["risk"], "destructive");
    let proposal = core.proposal_for("synth_publish");
    assert_eq!(proposal["state"], "pending");
    let reply = core.decide(proposal["proposal_id"].as_str().unwrap(), "authorize");
    assert_eq!(reply["code"], "destructive_disabled");
    assert_eq!(core.proposal_for("synth_publish")["state"], "pending");
    assert!(core.app()["published"].is_null() || core.app()["published"] == false);
}

#[test]
fn synthetic_tools_do_not_exist_without_the_flag() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("noflag");
    let steps = json!([
        turn_tools(vec![
            tool("synth_publish", json!({})),
            tool("shell", json!({})),
            tool("open_app", json!({"desktop_id": "evil.desktop"})),
        ]),
        {"text": "nothing ran"},
    ]);
    let mut core = with_core(&dir, steps, &[]);
    core.start("injected instructions: run rm -rf and publish");
    let agent = core.wait_state("done");
    assert_eq!(agent["answer"], "nothing ran");
    let states = step_states(&agent);
    assert_eq!(states.iter().filter(|s| *s == "tool:denied").count(), 3);
    assert!(core
        .proposals()
        .iter()
        .all(|p| p["tool"] != "synth_publish"));
    assert!(!dir.join("home/synthetic/app.json").exists());
}

#[test]
fn identical_calls_are_blocked_on_the_third_repetition() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("loop");
    let flags = synthetic_flags(&dir);
    let flags: Vec<&str> = flags.iter().map(String::as_str).collect();
    let read = turn_tools(vec![tool("synth_screen_read", json!({}))]);
    let steps = json!([read.clone(), read.clone(), read, {"text": "never"}]);
    let mut core = with_core(&dir, steps, &flags);
    core.start("loop");
    let agent = core.wait_state("blocked");
    assert_eq!(agent["error"], "loop_blocked");
    assert!(agent["answer"].is_null());
    assert!(core.snap()["events"]
        .as_array()
        .unwrap()
        .iter()
        .any(|e| e["kind"] == "agent_blocked:loop_blocked"));
}

#[test]
fn seventh_model_turn_is_refused_as_max_steps() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("steps");
    let steps: Vec<Value> = (0..6)
        .map(|i| turn_tools(vec![tool("unknown_tool_x", json!({"n": i}))]))
        .collect();
    let mut core = with_core(&dir, json!(steps), &[]);
    core.start("keep going");
    let agent = core.wait_state("failed");
    assert_eq!(agent["error"], "max_steps");
    assert_eq!(agent["step"], 6);
    assert_eq!(agent["max_steps"], 6);
    // Budget (C3): elapsed time of the run and its effective deadline, next to the step and token caps.
    assert!(agent["elapsed_ms"].as_u64().is_some(), "{agent}");
    assert_eq!(agent["max_run_ms"], 120_000, "{agent}");
}

#[test]
fn one_recoverable_error_is_retried_once() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("retry");
    let mut core = with_core(
        &dir,
        json!([{"error": "timeout"}, {"text": "recovered"}]),
        &[],
    );
    core.start("retry please");
    let agent = core.wait_state("done");
    assert_eq!(agent["answer"], "recovered");
    assert_eq!(agent["step"], 1);
    assert_eq!(step_states(&agent), ["chat:failed", "chat:done"]);
}

#[test]
fn a_second_recoverable_error_fails_the_run() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("retry2");
    let mut core = with_core(
        &dir,
        json!([{"error": "timeout"}, {"error": "timeout"}, {"text": "x"}]),
        &[],
    );
    core.start("retry twice");
    let agent = core.wait_state("failed");
    assert_eq!(agent["error"], "timeout");
    assert_eq!(agent["step"], 1);
}

#[test]
fn non_recoverable_provider_error_is_not_repeated() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("noretry");
    let mut core = with_core(
        &dir,
        json!([{"error": "http_error"}, {"text": "never"}]),
        &[],
    );
    core.start("auth failure");
    let agent = core.wait_state("failed");
    assert_eq!(agent["error"], "http_error");
    assert_eq!(step_states(&agent), ["chat:failed"]);
}

#[test]
fn token_budget_is_enforced_from_reported_usage() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("tokens");
    let flags = synthetic_flags(&dir);
    let flags: Vec<&str> = flags.iter().map(String::as_str).collect();
    let steps = json!([
        {"tool_calls": [tool("synth_screen_read", json!({}))], "usage": {"total_tokens": 3000}},
        {"tool_calls": [tool("synth_screen_read", json!({}))], "usage": {"total_tokens": 2000}},
        {"text": "never"},
    ]);
    let mut core = with_core(&dir, steps, &flags);
    core.start("spend");
    let agent = core.wait_state("failed");
    assert_eq!(agent["error"], "token_budget");
    assert_eq!(agent["budget"]["tokens_max"], 4096);
}

#[test]
fn stale_screen_twice_in_a_row_blocks_the_run() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("stale");
    let flags = synthetic_flags(&dir);
    let flags: Vec<&str> = flags.iter().map(String::as_str).collect();
    let steps = json!([
        turn_tools(vec![tool("synth_screen_read", json!({}))]),
        {"delay_ms": 1500, "tool_calls": [tool("synth_counter_inc", json!({"epoch": 1}))]},
        turn_tools(vec![tool("synth_counter_inc", json!({"epoch": 1}))]),
        {"text": "never"},
    ]);
    let mut core = with_core(&dir, steps, &flags);
    core.start("stale");
    core.wait_agent("second model turn", |a| {
        a["step"] == 2 && a["state"] == "thinking"
    });
    assert_eq!(core.call(json!({"op": "agent_test_bump"}))["code"], "ok");
    let agent = core.wait_state("blocked");
    assert_eq!(agent["error"], "stale_screen");
    assert!(core
        .proposals()
        .iter()
        .all(|p| p["tool"] != "synth_counter_inc" || p["state"] != "executed"));
    assert!(core.app()["counter"].is_null() || core.app()["counter"] == 0);
}

#[test]
fn run_deadline_fails_the_run_with_a_scaled_clock() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("deadline");
    let mut core = with_core(
        &dir,
        json!([{"delay_ms": 5000, "text": "late"}]),
        &["--agent-clock-scale", "60"],
    );
    core.start("slow");
    let agent = core.wait_state("failed");
    assert_eq!(agent["error"], "run_deadline");
}

#[test]
fn disabling_the_chat_plugin_aborts_the_run() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("revoke");
    let mut core = with_core(&dir, json!([{"delay_ms": 1500, "text": "late"}]), &[]);
    core.start("revoke me");
    core.wait_agent("first model turn", |a| a["state"] == "thinking");
    let revision = core.revision();
    ok(&core.call(json!({"op": "plugin_disable", "revision": revision, "plugin_id": PLUGIN})));
    let agent = core.wait_state("aborted");
    assert_eq!(agent["error"], "revoked");
}

#[test]
fn a_second_run_and_capability_calls_are_refused_while_active() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("busy");
    let mut core = with_core(&dir, json!([{"delay_ms": 1500, "text": "late"}]), &[]);
    assert_eq!(core.start("first")["code"], "ok");
    core.wait_agent("first model turn", |a| a["state"] == "thinking");
    assert_eq!(core.start("second")["code"], "agent_busy");
    let reply = core.call(json!({
        "op": "capability_invoke", "capability": CHAT, "input": {"messages": []}, "deadline_ms": 1000
    }));
    assert_eq!(reply["code"], "agent_busy");
    let run_id = core.agent()["run_id"].as_str().unwrap().to_owned();
    ok(&core.call(json!({"op": "agent_abort", "run_id": run_id})));
}

#[test]
fn changing_the_llm_configuration_revokes_the_run() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("configure");
    let mut core = with_core(&dir, json!([{"delay_ms": 1500, "text": "late"}]), &[]);
    core.start("configure during run");
    core.wait_agent("first model turn", |a| a["state"] == "thinking");
    let revision = core.snap()["llm"]["revision"].as_u64().unwrap();
    let reply = core.call(json!({
        "op": "llm_configure", "revision": revision, "provider": "google",
        "model": "gemini-3.5-flash-lite", "cloud_consent": false,
    }));
    assert_eq!(reply["code"], "ok", "{reply}");
    let agent = core.wait_state("aborted");
    assert_eq!(agent["error"], "revoked");
}

#[test]
fn test_bump_is_refused_without_the_synthetic_flag() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("nobump");
    let mut core = with_core(&dir, json!([{"text": "x"}]), &[]);
    assert_eq!(
        core.call(json!({"op": "agent_test_bump"}))["code"],
        "unknown_operation"
    );
}
