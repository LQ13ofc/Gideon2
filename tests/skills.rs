//! S4 skill engine (D1 validator, D2 executor) against the real Core binary. Inline Python stubs
//! only: `skillfix` forwards its capabilities to the synthetic world (`audio.*`), `slowfix` sleeps.
//! Every effect lands in `<home>/synthetic/world.json`; no real hardware, no network.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{BufRead, BufReader, Write},
    os::unix::{fs::PermissionsExt, net::UnixStream},
    path::{Path, PathBuf},
    process::{Child, Command as Process, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

static SERIAL: Mutex<()> = Mutex::new(());
const PYTHON: &str = "/usr/bin/python3";

/// Stub plugin. Capabilities: `*.read` (world audio state), `*.process` (flips the route),
/// `*.write` (sets the route), `*.fail` (reports `verified:false`), `*.slow` (sleeps).
const STUB: &str = r#"#!/usr/bin/env python3
import json, sys, time
PLUGIN_ID = "@PLUGIN_ID@"
CAPS = @CAPS@
def send(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()
def host(number, service, args):
    send({"v": 1, "op": "host_call", "id": number, "service": "synthetic." + service, "args": args})
    return json.loads(sys.stdin.readline())
while True:
    line = sys.stdin.readline()
    if not line:
        break
    msg = json.loads(line)
    op = msg.get("op")
    if op == "hello":
        send({"v": 1, "id": msg["id"], "ok": True, "plugin_id": PLUGIN_ID, "api": 1, "capabilities": CAPS})
    elif op == "invoke":
        capability = msg.get("capability", "")
        inp = msg.get("input") or {}
        action = capability.split(".")[1]
        if action == "read" or action == "write":
            if action == "read":
                reply = host(msg["id"] * 100 + 1, "audio.state", {})
            else:
                reply = host(msg["id"] * 100 + 1, "audio.set_route", {"route": inp.get("route")})
            if "error" in reply:
                send({"v": 1, "id": msg["id"], "ok": False, "error": "invalid_input"})
            else:
                send({"v": 1, "id": msg["id"], "ok": True, "output": reply.get("data")})
        elif action == "process":
            route = "headphones" if inp.get("value") == "speakers" else "speakers"
            send({"v": 1, "id": msg["id"], "ok": True, "output": {"route": route}})
        elif action == "fail":
            send({"v": 1, "id": msg["id"], "ok": True, "output": {"verified": False}})
        else:
            time.sleep(20)
            send({"v": 1, "id": msg["id"], "ok": True, "output": {"done": True}})
    elif op == "shutdown":
        break
"#;

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

fn stub(id: &'static str, caps: &[&'static str], perms: &[&'static str]) -> Spec {
    let payload = STUB
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
    home: PathBuf,
    catalog: (PathBuf, String),
    child: Option<Child>,
    counter: u64,
}

impl Core {
    fn boot(dir: &Path, specs: &[Spec]) -> Core {
        let catalog = catalog(dir, specs);
        let mut core = Core {
            root: dir.join("core"),
            home: dir.join("home"),
            catalog,
            child: None,
            counter: 0,
        };
        core.spawn();
        core
    }

    fn spawn(&mut self) {
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
            .arg("--commands-sandbox")
            .arg("--agent-synthetic")
            .arg("--home")
            .arg(&self.home)
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

    fn plugin_revision(&mut self) -> u64 {
        self.snap()["plugins"]["revision"].as_u64().unwrap()
    }

    fn skills_revision(&mut self) -> u64 {
        self.snap()["skills"]["revision"].as_u64().unwrap()
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
        let revision = self.plugin_revision();
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
        let revision = self.plugin_revision();
        ok(&self.call(json!({"op": "plugin_revoke", "revision": revision, "plugin_id": plugin})));
    }

    fn world(&self) -> Value {
        let path = self.home.join("synthetic/world.json");
        serde_json::from_slice(&fs::read(path).expect("world.json")).expect("world JSON")
    }

    /// Current synthetic route. Before the first write the world file does not exist yet, and the
    /// default route (`speakers`) applies.
    fn route(&self) -> String {
        if !self.home.join("synthetic/world.json").exists() {
            return "speakers".to_owned();
        }
        self.world()["audio"]["route"].as_str().unwrap().to_owned()
    }

    fn skill_block(&mut self) -> Value {
        self.snap()["skills"].clone()
    }

    fn run_block(&mut self) -> Value {
        self.skill_block()["run"].clone()
    }

    fn history(&mut self) -> Vec<Value> {
        self.skill_block()["history"].as_array().unwrap().clone()
    }

    fn save(&mut self, manifest: Value) -> String {
        self.call(json!({"op": "skill_save_draft", "manifest": manifest}))["code"]
            .as_str()
            .unwrap()
            .to_owned()
    }

    /// Authorizes every decision the run asks for, until `done` holds for the run block (or the
    /// run has ended, which `done` may also accept). Returns the run block.
    fn authorize_until(&mut self, what: &str, done: impl Fn(&Value) -> bool) -> Value {
        let deadline = Instant::now() + Duration::from_secs(15);
        loop {
            let run = self.run_block();
            if done(&run) {
                return run;
            }
            assert!(
                Instant::now() < deadline,
                "timed out before {what}: {}",
                self.snap()["skills"]
            );
            if run["state"] == "awaiting_approval" {
                let step = run["steps"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .rev()
                    .find(|s| s["state"] == "awaiting_approval")
                    .unwrap()["id"]
                    .as_str()
                    .unwrap()
                    .to_owned();
                let run_id = run["run_id"].as_str().unwrap().to_owned();
                assert_eq!(self.decide(&run_id, &step, "authorize"), "ok");
            }
            thread::sleep(Duration::from_millis(30));
        }
    }

    fn validate(&mut self, manifest: Value) -> String {
        self.call(json!({"op": "skill_validate", "manifest": manifest}))["code"]
            .as_str()
            .unwrap()
            .to_owned()
    }

    fn dry_run(&mut self, id: &str, version: &str, inputs: Value) -> String {
        self.call(
            json!({"op": "skill_dry_run", "id": id, "skill_version": version, "inputs": inputs}),
        )["code"]
            .as_str()
            .unwrap()
            .to_owned()
    }

    fn approve(&mut self, id: &str, version: &str) -> String {
        let revision = self.skills_revision();
        self.call(json!({"op": "skill_approve", "id": id, "skill_version": version, "revision": revision}))
            ["code"]
            .as_str()
            .unwrap()
            .to_owned()
    }

    fn enable_skill(&mut self, id: &str) -> String {
        let revision = self.skills_revision();
        self.call(json!({"op": "skill_enable", "id": id, "revision": revision}))["code"]
            .as_str()
            .unwrap()
            .to_owned()
    }

    fn run_skill(&mut self, id: &str, inputs: Value) -> String {
        self.call(json!({"op": "skill_run", "id": id, "inputs": inputs}))["code"]
            .as_str()
            .unwrap()
            .to_owned()
    }

    fn decide(&mut self, run_id: &str, step: &str, decision: &str) -> String {
        self.call(
            json!({"op": "skill_decide", "run_id": run_id, "step": step, "decision": decision}),
        )["code"]
            .as_str()
            .unwrap()
            .to_owned()
    }

    /// Saves, dry-runs, approves and enables a skill, returning its id.
    fn promote(&mut self, manifest: Value) {
        let id = manifest["id"].as_str().unwrap().to_owned();
        let version = manifest["version"].as_str().unwrap().to_owned();
        assert_eq!(self.save(manifest), "ok");
        assert_eq!(self.dry_run(&id, &version, json!({})), "ok");
        assert_eq!(self.approve(&id, &version), "ok");
        assert_eq!(self.enable_skill(&id), "ok");
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

fn setup(name: &str) -> PathBuf {
    let base = std::env::temp_dir().join(format!("gideon-skills-{}-{name}", std::process::id()));
    let _ = fs::remove_dir_all(&base);
    fs::create_dir_all(base.join("home")).unwrap();
    base
}

fn specs() -> Vec<Spec> {
    vec![
        stub(
            "skillfix",
            &[
                "skillfix.read",
                "skillfix.process",
                "skillfix.write",
                "skillfix.fail",
            ],
            &["audio_route"],
        ),
        stub("slowfix", &["slowfix.slow"], &[]),
    ]
}

/// Manifest with the shared envelope; `steps` and `deps` vary per test.
fn manifest(id: &str, deps: &[&str], steps: Value) -> Value {
    json!({
        "schema_version": 1,
        "id": id,
        "name": "Skill de teste",
        "version": "1.0.0",
        "publisher": {"id": "gideon-test", "name": "Gideon test"},
        "description": "Skill sintetica de teste",
        "license": "MIT",
        "min_runtime": "0.1.0",
        "inputs": {},
        "outputs": {"route": {"type": "string"}},
        "dependency_capabilities": deps,
        "steps": steps,
    })
}

const SKILLFIX_DEPS: [&str; 4] = [
    "skillfix.read",
    "skillfix.process",
    "skillfix.write",
    "skillfix.fail",
];

/// read -> process -> write (state changing, undo restores the original route).
fn route_skill(id: &str) -> Value {
    manifest(
        id,
        &SKILLFIX_DEPS,
        json!([
            {"id": "read", "call": "skillfix.read", "args": {}, "save": {"route": "route"}},
            {"id": "next", "call": "skillfix.process", "args": {"value": "${steps.read.route}"}, "save": {"route": "route"}},
            {
                "id": "write",
                "call": "skillfix.write",
                "args": {"route": "${steps.next.route}"},
                "undo": {"call": "skillfix.write", "args": {"route": "${steps.read.route}"}},
                "verify": {"ref": "steps.write.verified", "op": "eq", "value": true},
                "save": {"route": "route"}
            }
        ]),
    )
}

/// write (undo to the original route), then a check that reports `verified:false`.
fn failing_skill(id: &str) -> Value {
    manifest(
        id,
        &SKILLFIX_DEPS,
        json!([
            {"id": "read", "call": "skillfix.read", "args": {}, "save": {"route": "route"}},
            {
                "id": "write",
                "call": "skillfix.write",
                "args": {"route": "headphones"},
                "undo": {"call": "skillfix.write", "args": {"route": "${steps.read.route}"}},
                "verify": {"ref": "steps.write.verified", "op": "eq", "value": true}
            },
            {"id": "check", "call": "skillfix.fail", "args": {}, "verify": {"ref": "steps.check.verified", "op": "eq", "value": true}}
        ]),
    )
}

// ---------------------------------------------------------------------------
// D1: validator
// ---------------------------------------------------------------------------

#[test]
fn validator_refuses_each_documented_defect() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("validator");
    let mut core = Core::boot(&dir, &specs());
    let base = route_skill("skill_base");
    assert_eq!(core.validate(base.clone()), "ok");

    let set = |path: &str, value: Value| {
        let mut m = base.clone();
        let mut node = &mut m;
        let mut parts: Vec<&str> = path.split('/').collect();
        let last = parts.pop().unwrap();
        for part in parts {
            node = if let Ok(index) = part.parse::<usize>() {
                &mut node[index]
            } else {
                &mut node[part]
            };
        }
        if let Ok(index) = last.parse::<usize>() {
            node[index] = value;
        } else {
            node[last] = value;
        }
        m
    };
    let step = |index: usize, key: &str, value: Value| set(&format!("steps/{index}/{key}"), value);
    let cases: Vec<(&str, Value, &str)> = vec![
        (
            "schema_version",
            set("schema_version", json!(2)),
            "skill_invalid:schema_version",
        ),
        (
            "min_runtime",
            set("min_runtime", json!("9.0.0")),
            "skill_invalid:min_runtime",
        ),
        (
            "unknown top key",
            set("bogus", json!(1)),
            "skill_invalid:unknown_key",
        ),
        (
            "unknown step key",
            step(0, "retry", json!(1)),
            "skill_invalid:unknown_key",
        ),
        (
            "grant field",
            step(0, "grant", json!(true)),
            "skill_invalid:grant_field",
        ),
        (
            "out of scope call",
            step(0, "call", json!("skillfix.unlisted")),
            "skill_invalid:out_of_scope",
        ),
        (
            "duplicate step",
            set("steps/1/id", json!("read")),
            "skill_invalid:duplicate_step",
        ),
        (
            "future reference",
            step(0, "args", json!({"route": "${steps.write.route}"})),
            "skill_invalid:forward_ref",
        ),
        (
            "exfiltration path",
            step(1, "args", json!({"value": "../../etc/passwd"})),
            "skill_invalid:exfiltration",
        ),
        (
            "exfiltration url",
            step(1, "args", json!({"value": "https://example.test/x"})),
            "skill_invalid:exfiltration",
        ),
        (
            "exfiltration shell",
            step(1, "args", json!({"value": "a; rm -rf x"})),
            "skill_invalid:exfiltration",
        ),
        (
            "secret-like key",
            step(1, "args", json!({"api_token": "x"})),
            "skill_invalid:exfiltration",
        ),
        (
            "reserved capability",
            step(0, "call", json!("base.read")),
            "skill_invalid:reserved_capability",
        ),
        (
            "invalid template",
            step(1, "args", json!({"value": "${env.HOME}"})),
            "skill_invalid:bad_template",
        ),
        (
            "args too deep",
            step(1, "args", json!({"a": {"b": {"c": {"d": 1}}}})),
            "skill_invalid:args_depth",
        ),
        (
            "retries without idempotent",
            step(0, "retries", json!(1)),
            "skill_invalid:retries_need_idempotent",
        ),
        (
            "bad condition op",
            step(
                1,
                "when",
                json!({"ref": "input.x", "op": "like", "value": 1}),
            ),
            "skill_invalid:bad_template",
        ),
        (
            "unknown tool",
            step(0, "call", json!("tool:shell")),
            "skill_invalid:unknown_tool",
        ),
    ];
    let mut failures = Vec::new();
    for (name, manifest, expected) in cases {
        let got = core.validate(manifest);
        if got != expected {
            failures.push(format!("{name}: expected {expected}, got {got}"));
        }
    }
    assert!(failures.is_empty(), "{failures:#?}");
}

#[test]
fn validator_refuses_oversize_and_unknown_cycles_and_depth() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("chains");
    let mut core = Core::boot(&dir, &specs());

    let mut big = route_skill("skill_big");
    big["extra_padding"] = json!("x".repeat(17 * 1024));
    assert_eq!(core.validate(big), "skill_invalid:oversize");

    let mut big_args = route_skill("skill_args");
    big_args["steps"][1]["args"] = json!({"value": "a".repeat(2100)});
    assert_eq!(core.validate(big_args), "skill_invalid:oversize");

    // Two-skill cycle: B refers to A (not installed yet), then A refers to B.
    let b_cycle = manifest(
        "skill_cyc_b",
        &["skill:skill_cyc_a"],
        json!([
            {"id": "nested", "call": "skill:skill_cyc_a", "args": {}}
        ]),
    );
    assert_eq!(core.save(b_cycle), "ok");
    let a_cycle = manifest(
        "skill_cyc_a",
        &["skill:skill_cyc_b"],
        json!([
            {"id": "nested", "call": "skill:skill_cyc_b", "args": {}}
        ]),
    );
    assert_eq!(core.validate(a_cycle), "skill_invalid:cycle");
    // Self reference.
    let me = manifest(
        "skill_self",
        &["skill:skill_self"],
        json!([
            {"id": "nested", "call": "skill:skill_self", "args": {}}
        ]),
    );
    assert_eq!(core.validate(me), "skill_invalid:cycle");

    // Chain of four: C <- B <- A <- T. Validating T needs the depth limit (two nested levels).
    let leaf_deps = manifest(
        "skill_chain_c",
        &["tool:get_time"],
        json!([{"id": "noop", "call": "tool:get_time", "args": {}}]),
    );
    assert_eq!(core.save(leaf_deps), "ok");
    let b = manifest(
        "skill_chain_b",
        &["skill:skill_chain_c"],
        json!([{"id": "down", "call": "skill:skill_chain_c", "args": {}}]),
    );
    assert_eq!(core.save(b), "ok");
    let a = manifest(
        "skill_chain_a",
        &["skill:skill_chain_b"],
        json!([{"id": "down", "call": "skill:skill_chain_b", "args": {}}]),
    );
    assert_eq!(core.save(a), "ok");
    let top = manifest(
        "skill_chain_t",
        &["skill:skill_chain_a"],
        json!([{"id": "down", "call": "skill:skill_chain_a", "args": {}}]),
    );
    assert_eq!(core.validate(top), "skill_invalid:depth");
}

#[test]
fn ledgers_are_private_and_manifests_live_under_skills() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("private");
    let mut core = Core::boot(&dir, &specs());
    assert_eq!(core.save(route_skill("skill_priv")), "ok");
    let root = dir.join("core");
    let mode = |path: PathBuf| fs::metadata(path).unwrap().permissions().mode() & 0o777;
    assert_eq!(mode(root.join("skills.json")), 0o600);
    let manifest_path = root.join("skills/skill_priv/1.0.0/skill.json");
    assert_eq!(mode(manifest_path.clone()), 0o600);
    assert!(fs::read_to_string(manifest_path)
        .unwrap()
        .contains("skill_priv"));
    let skills = core.skill_block();
    assert_eq!(skills["items"][0]["state"], "validated");
    assert_eq!(skills["items"][0]["source"], "created");
}

#[test]
fn size_caps_and_limits_hold() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("caps");
    let mut core = Core::boot(&dir, &specs());
    for index in 0..16 {
        let id = format!("skill_cap_{index:02}");
        assert_eq!(
            core.save(manifest(
                &id,
                &["tool:get_time"],
                json!([{"id": "noop", "call": "tool:get_time", "args": {}}])
            )),
            "ok",
            "{index}"
        );
    }
    assert_eq!(
        core.save(manifest(
            "skill_cap_extra",
            &["tool:get_time"],
            json!([{"id": "noop", "call": "tool:get_time", "args": {}}])
        )),
        "skill_invalid:skill_limit"
    );
    let mut versioned = manifest(
        "skill_cap_00",
        &["tool:get_time"],
        json!([{"id": "noop", "call": "tool:get_time", "args": {}}]),
    );
    for version in ["1.0.1", "1.0.2"] {
        versioned["version"] = json!(version);
        assert_eq!(core.save(versioned.clone()), "ok", "{version}");
    }
    versioned["version"] = json!("1.0.3");
    assert_eq!(core.save(versioned), "skill_invalid:version_limit");
}

// ---------------------------------------------------------------------------
// D2: executor
// ---------------------------------------------------------------------------

#[test]
fn dry_run_makes_zero_capability_calls() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("dryrun");
    let mut core = Core::boot(&dir, &specs());
    core.install("skillfix", &specs()[0].payload);
    core.enable("skillfix");
    assert_eq!(core.save(route_skill("skill_dry")), "ok");
    let before = core.snap()["sequence"].as_u64().unwrap();
    assert_eq!(core.dry_run("skill_dry", "1.0.0", json!({})), "ok");
    let snap = core.snap();
    let fresh: Vec<&str> = snap["events"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|e| e["sequence"].as_u64().unwrap() > before)
        .map(|e| e["kind"].as_str().unwrap())
        .collect();
    assert!(!fresh.contains(&"capability_invoked"), "{fresh:?}");
    assert!(!fresh.contains(&"skill_step"), "{fresh:?}");
    assert!(snap["capability_result"].is_null());
    assert_eq!(core.route(), "speakers");
    assert_eq!(snap["skills"]["items"][0]["state"], "tested");
    assert!(snap["skills"]["run"].is_null());
}

#[test]
fn happy_run_reads_processes_and_writes_the_synthetic_world() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("happy");
    let mut core = Core::boot(&dir, &specs());
    core.install("skillfix", &specs()[0].payload);
    core.enable("skillfix");
    core.promote(route_skill("skill_happy"));
    assert_eq!(core.run_skill("skill_happy", json!({})), "ok");
    // Every plugin capability outside the bridge registry is state-changing: each step waits.
    let waiting_write = core.authorize_until("the write waits", |r| {
        r["state"] == "awaiting_approval"
            && r["steps"].as_array().unwrap().last().unwrap()["id"] == "write"
    });
    assert_eq!(
        core.route(),
        "speakers",
        "the state change waits for the user"
    );
    // The snapshot lists steps with state and risk only: no arguments, no outputs.
    let text = waiting_write.to_string();
    assert!(
        !text.contains("headphones") && !text.contains("\"args\""),
        "{text}"
    );
    // A decision step carries its call's risk class (tool-proposal vocabulary); no registry effect here.
    let decision_step = waiting_write["steps"]
        .as_array()
        .unwrap()
        .last()
        .unwrap()
        .clone();
    assert_eq!(decision_step["risk"], "state_changing", "{text}");
    assert!(decision_step.get("effect_id").is_none(), "{text}");
    // skills.paths: absolute display folders; items list the manifest's permissions_required.
    let block = core.skill_block();
    assert!(block["paths"]["imports"]
        .as_str()
        .unwrap()
        .ends_with("skill-imports"));
    assert!(block["paths"]["exports"]
        .as_str()
        .unwrap()
        .ends_with("skill-exports"));
    assert!(block["paths"]["imports"].as_str().unwrap().starts_with('/'));
    assert!(
        block["items"][0]["permissions_required"].is_array(),
        "{block}"
    );
    let run_id = waiting_write["run_id"].as_str().unwrap().to_owned();
    assert_eq!(core.decide(&run_id, "write", "authorize"), "ok");
    core.authorize_until("the run ends", |r| r.is_null());
    let last = core.history().last().unwrap().clone();
    assert_eq!(last["state"], "done", "{last}");
    assert_eq!(core.route(), "headphones");
    let runs = fs::read_to_string(dir.join("core/skill-runs.json")).unwrap();
    assert!(!runs.contains("headphones"), "no content in run history");
    assert!(runs.contains("skill_happy"));
}

#[test]
fn error_in_step_two_rolls_back_step_one_in_reverse() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("rollback");
    let mut core = Core::boot(&dir, &specs());
    core.install("skillfix", &specs()[0].payload);
    core.enable("skillfix");
    core.promote(failing_skill("skill_fails"));
    assert_eq!(core.run_skill("skill_fails", json!({})), "ok");
    core.authorize_until("the run ends", |r| r.is_null());
    let last = core.history().last().unwrap().clone();
    assert_eq!(last["state"], "failed", "{last}");
    assert!(
        last["codes"]
            .as_array()
            .unwrap()
            .iter()
            .any(|c| c == "verify_failed"),
        "{last}"
    );
    assert_eq!(last["step"], "check");
    assert_eq!(
        core.route(),
        "speakers",
        "undo of step one restored the route"
    );
    assert_eq!(core.run_block(), Value::Null);
}

#[test]
fn cancel_rolls_back_and_ends_cancelled() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("cancel");
    let mut core = Core::boot(&dir, &specs());
    core.install("skillfix", &specs()[0].payload);
    core.install("slowfix", &specs()[1].payload);
    core.enable("skillfix");
    core.enable("slowfix");
    let slow = manifest(
        "skill_slow",
        &["skillfix.read", "slowfix.slow"],
        json!([
            {"id": "read", "call": "skillfix.read", "args": {}, "save": {"route": "route"}},
            {"id": "wait", "call": "slowfix.slow", "args": {}, "timeout_ms": 10000}
        ]),
    );
    core.promote(slow);
    assert_eq!(core.run_skill("skill_slow", json!({})), "ok");
    let running = core.authorize_until("the slow step runs", |r| {
        r["state"] == "running" && r["steps"].as_array().unwrap().last().unwrap()["id"] == "wait"
    });
    let run_id = running["run_id"].as_str().unwrap().to_owned();
    assert_eq!(
        core.call(json!({"op": "skill_cancel", "run_id": run_id}))["code"],
        "ok"
    );
    core.authorize_until("the run ends", |r| r.is_null());
    let last = core.history().last().unwrap().clone();
    assert_eq!(last["state"], "cancelled", "{last}");
    assert_eq!(core.route(), "speakers");
}

#[test]
fn lost_dependency_fails_the_run_and_rolls_back() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("lost");
    let mut core = Core::boot(&dir, &specs());
    core.install("skillfix", &specs()[0].payload);
    core.install("slowfix", &specs()[1].payload);
    core.enable("skillfix");
    core.enable("slowfix");
    let skill = manifest(
        "skill_lost",
        &["skillfix.write", "slowfix.slow"],
        json!([
            {
                "id": "write",
                "call": "skillfix.write",
                "args": {"route": "headphones"},
                "undo": {"call": "skillfix.write", "args": {"route": "speakers"}}
            },
            {"id": "wait", "call": "slowfix.slow", "args": {}, "timeout_ms": 10000}
        ]),
    );
    core.promote(skill);
    assert_eq!(core.run_skill("skill_lost", json!({})), "ok");
    core.authorize_until("the slow step runs", |r| {
        r["state"] == "running" && r["steps"].as_array().unwrap().last().unwrap()["id"] == "wait"
    });
    assert_eq!(
        core.route(),
        "headphones",
        "the completed write is in effect"
    );
    core.revoke("slowfix");
    core.authorize_until("the run ends", |r| r.is_null());
    let last = core.history().last().unwrap().clone();
    assert_eq!(last["state"], "failed", "{last}");
    assert!(
        last["codes"]
            .as_array()
            .unwrap()
            .iter()
            .any(|c| c == "missing_dependency"),
        "{last}"
    );
    assert_eq!(
        core.route(),
        "speakers",
        "rollback ran the undo of the completed step"
    );
}

#[test]
fn missing_dependency_blocks_the_run_before_it_starts() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("missing");
    let mut core = Core::boot(&dir, &specs());
    core.install("skillfix", &specs()[0].payload);
    core.enable("skillfix");
    core.promote(route_skill("skill_blocked"));
    let revision = core.plugin_revision();
    ok(&core.call(json!({"op": "plugin_disable", "revision": revision, "plugin_id": "skillfix"})));
    assert_eq!(
        core.run_skill("skill_blocked", json!({})),
        "missing_dependency"
    );
    assert!(core.run_block().is_null());
    assert_eq!(core.route(), "speakers");
}

#[test]
fn no_elevation_only_the_user_path_moves_states() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("states");
    let mut core = Core::boot(&dir, &specs());
    core.install("skillfix", &specs()[0].payload);
    core.enable("skillfix");
    assert_eq!(core.save(route_skill("skill_states")), "ok");
    assert_eq!(
        core.run_skill("skill_states", json!({})),
        "skill_not_enabled"
    );
    let revision = core.skills_revision();
    assert_eq!(
        core.call(json!({"op": "skill_enable", "id": "skill_states", "revision": revision}))
            ["code"],
        "skill_not_approved"
    );
    assert_eq!(core.approve("skill_states", "1.0.0"), "skill_not_tested");
    assert_eq!(core.dry_run("skill_states", "1.0.0", json!({})), "ok");
    assert_eq!(core.approve("skill_states", "1.0.0"), "ok");
    assert_eq!(core.approve("skill_states", "1.0.0"), "skill_not_tested");
    assert_eq!(
        core.decide("skill_missing_run", "write", "authorize"),
        "unknown_skill_run"
    );
    assert_eq!(
        core.call(json!({"op": "skill_cancel", "run_id": "skill_missing"}))["code"],
        "unknown_skill_run"
    );
    assert_eq!(core.enable_skill("skill_states"), "ok");
    assert_eq!(core.enable_skill("skill_states"), "already_enabled");
    assert_eq!(core.route(), "speakers");
    assert!(core.run_block().is_null());
}

#[test]
fn ledger_is_cas_and_revision_moves_once_per_write() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("cas");
    let mut core = Core::boot(&dir, &specs());
    let start = core.skills_revision();
    let skill = manifest(
        "skill_cas",
        &["tool:get_time"],
        json!([{"id": "now", "call": "tool:get_time", "args": {}}]),
    );
    assert_eq!(core.save(skill), "ok");
    assert_eq!(core.skills_revision(), start + 1);
    assert_eq!(core.dry_run("skill_cas", "1.0.0", json!({})), "ok");
    assert_eq!(
        core.skills_revision(),
        start + 2,
        "dry run marks tested: one write"
    );
    let stale = core.call(json!({"op": "skill_approve", "id": "skill_cas", "skill_version": "1.0.0", "revision": start}));
    assert_eq!(stale["code"], "stale_skill_revision");
    assert_eq!(
        core.skills_revision(),
        start + 2,
        "a refused write changes nothing"
    );
    assert_eq!(core.approve("skill_cas", "1.0.0"), "ok");
    assert_eq!(core.skills_revision(), start + 3);
}

#[test]
fn run_inputs_are_bounded_and_destructive_never_runs_in_development() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("inputs");
    let mut core = Core::boot(&dir, &specs());
    let mut skill = manifest(
        "skill_inputs",
        &["tool:synth_publish"],
        json!([{"id": "publish", "call": "tool:synth_publish", "args": {}}]),
    );
    skill["inputs"] = json!({"label": {"type": "string", "required": false, "max": 16}});
    assert_eq!(core.save(skill), "ok");
    assert_eq!(
        core.dry_run("skill_inputs", "1.0.0", json!({"label": "x".repeat(40)})),
        "invalid_skill_input"
    );
    assert_eq!(
        core.dry_run("skill_inputs", "1.0.0", json!({"other": 1})),
        "invalid_skill_input"
    );
    assert_eq!(
        core.dry_run("skill_inputs", "1.0.0", json!({"label": "x".repeat(2100)})),
        "invalid_skill_input"
    );
    assert_eq!(
        core.dry_run("skill_inputs", "1.0.0", json!({})),
        "destructive_disabled"
    );
}

#[test]
fn nested_skill_runs_inside_the_parent_with_conditions_and_tools() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("nested");
    let mut core = Core::boot(&dir, &specs());
    core.install("skillfix", &specs()[0].payload);
    core.enable("skillfix");
    let mut child = manifest(
        "skill_child",
        &["skillfix.write"],
        json!([{
            "id": "set",
            "call": "skillfix.write",
            "args": {"route": "${input.target}"},
            "undo": {"call": "skillfix.write", "args": {"route": "speakers"}},
            "verify": {"ref": "steps.set.verified", "op": "eq", "value": true},
            "save": {"route": "route"}
        }]),
    );
    child["inputs"] =
        json!({"target": {"type": "string", "required": false, "default": "speakers", "max": 32}});
    core.promote(child);
    let mut parent = manifest(
        "skill_parent",
        &[
            "skill:skill_child",
            "tool:synth_screen_read",
            "skillfix.write",
        ],
        json!([
            {"id": "look", "call": "tool:synth_screen_read", "args": {}},
            {"id": "skipped", "call": "tool:synth_screen_read", "args": {}, "when": {"ref": "input.go", "op": "eq", "value": false}},
            {"id": "child", "call": "skill:skill_child", "args": {"target": "headphones"}, "save": {"route": "route"}}
        ]),
    );
    parent["inputs"] = json!({"go": {"type": "bool", "required": false, "default": true}});
    core.promote(parent);
    assert_eq!(core.run_skill("skill_parent", json!({})), "ok");
    let waiting = core.authorize_until("the nested write waits", |r| {
        r["state"] == "awaiting_approval"
            && r["steps"].as_array().unwrap().last().unwrap()["id"] == "child"
    });
    let steps = waiting["steps"].as_array().unwrap().clone();
    assert!(
        steps.iter().all(|s| s["id"] != "skipped"),
        "a skipped step is not reported: {steps:?}"
    );
    assert_eq!(core.route(), "speakers");
    let run_id = waiting["run_id"].as_str().unwrap().to_owned();
    assert_eq!(core.decide(&run_id, "child", "authorize"), "ok");
    core.authorize_until("the run ends", |r| r.is_null());
    let last = core.history().last().unwrap().clone();
    assert_eq!(last["state"], "done", "{last}");
    assert_eq!(core.route(), "headphones");
}

#[test]
fn versions_roll_back_disable_and_remove_through_ops() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("versions");
    let mut core = Core::boot(&dir, &specs());
    core.install("skillfix", &specs()[0].payload);
    core.enable("skillfix");
    core.promote(route_skill("skill_ver"));
    let mut second = route_skill("skill_ver");
    second["version"] = json!("1.0.1");
    core.promote(second);
    let item = core.skill_block()["items"][0].clone();
    assert_eq!(item["version"], "1.0.1");
    assert_eq!(item["active"], true);
    let revision = core.skills_revision();
    assert_eq!(
        core.call(json!({"op": "skill_rollback", "id": "skill_ver", "revision": revision}))["code"],
        "ok"
    );
    let item = core.skill_block()["items"][0].clone();
    assert_eq!(item["version"], "1.0.0");
    assert_eq!(item["state"], "enabled");
    let revision = core.skills_revision();
    assert_eq!(
        core.call(json!({"op": "skill_disable", "id": "skill_ver", "revision": revision}))["code"],
        "ok"
    );
    assert_eq!(core.run_skill("skill_ver", json!({})), "skill_not_enabled");
    let revision = core.skills_revision();
    assert_eq!(
        core.call(json!({"op": "skill_remove", "id": "skill_ver", "revision": revision}))["code"],
        "ok"
    );
    assert!(core.skill_block()["items"].as_array().unwrap().is_empty());
    assert!(!dir.join("core/skills/skill_ver").exists());
    let events: Vec<String> = core.snap()["events"]
        .as_array()
        .unwrap()
        .iter()
        .map(|e| e["kind"].as_str().unwrap().to_owned())
        .collect();
    assert!(events.iter().any(|k| k == "skill_enabled"), "{events:?}");
}

#[test]
fn a_denied_decision_fails_the_step_and_rolls_back() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("deny");
    let mut core = Core::boot(&dir, &specs());
    core.install("skillfix", &specs()[0].payload);
    core.enable("skillfix");
    core.promote(route_skill("skill_deny"));
    assert_eq!(core.run_skill("skill_deny", json!({})), "ok");
    let waiting = core.authorize_until("the first decision", |r| r["state"] == "awaiting_approval");
    let run_id = waiting["run_id"].as_str().unwrap().to_owned();
    assert_eq!(core.decide(&run_id, "read", "deny"), "ok");
    core.authorize_until("the run ends", |r| r.is_null());
    let last = core.history().last().unwrap().clone();
    assert_eq!(last["state"], "failed", "{last}");
    assert!(
        last["codes"]
            .as_array()
            .unwrap()
            .iter()
            .any(|c| c == "user_denied"),
        "{last}"
    );
    assert_eq!(core.route(), "speakers");
    let events: Vec<String> = core.snap()["events"]
        .as_array()
        .unwrap()
        .iter()
        .map(|e| e["kind"].as_str().unwrap().to_owned())
        .collect();
    for kind in ["skill_run_started", "skill_run_failed", "skill_validated"] {
        assert!(
            events.iter().any(|k| k == kind),
            "missing {kind}: {events:?}"
        );
    }
}

// ---------------------------------------------------------------------------
// Review fixes: embedded dry-run references, oversize answers, validator precedence
// ---------------------------------------------------------------------------

#[test]
fn dry_run_shows_embedded_step_refs_and_the_run_completes() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("embedded_refs");
    let mut core = Core::boot(&dir, &specs());
    core.install("skillfix", &specs()[0].payload);
    core.enable("skillfix");
    let embedded = manifest(
        "skill_embed",
        &SKILLFIX_DEPS,
        json!([
            {"id": "read", "call": "skillfix.read", "args": {}, "save": {"route": "route"}},
            {"id": "echo", "call": "skillfix.process", "args": {"value": "ab-${steps.read.route}"}}
        ]),
    );
    assert_eq!(core.save(embedded), "ok");
    assert_eq!(core.dry_run("skill_embed", "1.0.0", json!({})), "ok");
    assert_eq!(core.approve("skill_embed", "1.0.0"), "ok");
    assert_eq!(core.enable_skill("skill_embed"), "ok");
    assert_eq!(core.run_skill("skill_embed", json!({})), "ok");
    core.authorize_until("the run ends", |r| r.is_null());
    let last = core.history().last().unwrap().clone();
    assert_eq!(last["state"], "done", "{last}");
}

#[test]
fn oversize_skill_manifest_is_answered_and_other_oversize_lines_still_close() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("oversize_line");
    let mut core = Core::boot(&dir, &specs());
    let mut big = manifest(
        "skill_big",
        &SKILLFIX_DEPS,
        json!([{"id": "read", "call": "skillfix.read", "args": {}}]),
    );
    big["padding"] = json!("x".repeat(30_000));
    assert_eq!(core.validate(big.clone()), "skill_invalid:oversize");
    assert_eq!(core.save(big), "skill_invalid:oversize");
    assert_eq!(
        core.snap()["code"],
        "ok",
        "the socket still answers after the refusal"
    );

    let mut stream = UnixStream::connect(core.root.join("core.sock")).unwrap();
    stream
        .set_read_timeout(Some(Duration::from_secs(10)))
        .unwrap();
    let line = format!(
        "{{\"version\":1,\"request_id\":\"big\",\"op\":\"snapshot\",\"padding\":\"{}\"}}\n",
        "x".repeat(30_000)
    );
    let _ = stream.write_all(line.as_bytes());
    let mut reply = String::new();
    let _ = BufReader::new(stream).read_line(&mut reply);
    assert!(
        reply.is_empty(),
        "other operations keep their frame limit: {reply}"
    );
}

#[test]
fn grant_fields_in_steps_are_reported_before_unknown_keys() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("grant_first");
    let mut core = Core::boot(&dir, &specs());
    let mut with_unknown_top = manifest(
        "skill_grant_a",
        &SKILLFIX_DEPS,
        json!([{"id": "read", "call": "skillfix.read", "args": {}, "grant": "audio_route"}]),
    );
    with_unknown_top["bogus"] = json!(1);
    assert_eq!(core.validate(with_unknown_top), "skill_invalid:grant_field");
    let with_permissions = manifest(
        "skill_grant_b",
        &SKILLFIX_DEPS,
        json!([{"id": "read", "call": "skillfix.read", "args": {}, "permissions": ["audio_route"], "extra": 1}]),
    );
    assert_eq!(core.validate(with_permissions), "skill_invalid:grant_field");
    let unknown_only = manifest(
        "skill_grant_c",
        &SKILLFIX_DEPS,
        json!([{"id": "read", "call": "skillfix.read", "args": {}, "extra": 1}]),
    );
    assert_eq!(core.validate(unknown_only), "skill_invalid:unknown_key");
}

/// A connection write is retried only when its descriptor is idempotent (the GitHub issue create is not:
/// the real API ignores the key). Reads may keep retries. Validated without any network call.
#[test]
fn connection_writes_are_never_retried_unless_the_descriptor_is_idempotent() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("conn_retry");
    let mut core = Core::boot(&dir, &specs());
    let args = json!({"repo": "demo/private-repo", "title": "x"});
    let with = |id: &str, call: &str, retries: u64, idempotent: bool| {
        manifest(
            id,
            &[call],
            json!([{"id": "open", "call": call, "args": args, "retries": retries, "idempotent": idempotent}]),
        )
    };
    let issue = "conn:github.issues.create";
    assert_eq!(
        core.validate(with("skill_conn_a", issue, 1, true)),
        "skill_invalid:retries_need_idempotent"
    );
    assert_eq!(
        core.validate(with("skill_conn_b", issue, 1, false)),
        "skill_invalid:retries_need_idempotent"
    );
    assert_eq!(
        core.validate(with("skill_conn_c", issue, 0, true)),
        "ok",
        "no retries is always fine"
    );
    assert_eq!(
        core.validate(with("skill_conn_d", "conn:github.repo.get", 1, true)),
        "ok",
        "an idempotent read may retry"
    );
}
