//! S4 D3 host services (`skills.validate`, `skills.draft_put`, `skills.dry_run`, `skills.list`)
//! against the real Core binary. The plugins are inline Python proxies: each capability forwards
//! one `host_call` and returns the Core's reply, so every assertion goes through the wire.
//! Nothing here touches hardware, network or a provider.
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
const AUTHOR: &str = "skillauthor";
const PLAIN: &str = "skillplain";

/// Proxy plugin: `input.service` and `input.args` become one `host_call`; the reply is returned as
/// `host` (data) or `host_error` (code), tagged with the caller's `nonce`.
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
        args = json.loads(request["args_json"])
        send({"v": 1, "op": "host_call", "id": msg["id"] * 100 + 1, "service": request["service"], "args": args})
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

fn specs() -> Vec<Spec> {
    vec![
        proxy(AUTHOR, &["skillauthor.call"], &["skills_author"]),
        proxy(PLAIN, &["skillplain.call"], &[]),
    ]
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
    nonce: u64,
}

impl Core {
    fn boot(dir: &Path) -> Core {
        let mut core = Core {
            root: dir.join("core"),
            home: dir.join("home"),
            catalog: catalog(dir, &specs()),
            child: None,
            counter: 0,
            nonce: 0,
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

    /// Approves the catalog permissions of `plugin` and installs it through the hub path.
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
        let revision = self.snap()["plugins"]["revision"].as_u64().unwrap();
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

    /// Boots the two plugins: `skillauthor` with the approved `skills_author`, `skillplain` without.
    fn with_plugins(dir: &Path) -> Core {
        let mut core = Core::boot(dir);
        let payloads: Vec<(&str, Vec<u8>)> =
            specs().into_iter().map(|s| (s.id, s.payload)).collect();
        for (id, payload) in &payloads {
            core.install(id, payload);
            core.enable(id);
        }
        core
    }

    /// Calls one host service through `plugin`'s proxy capability and returns the proxy output.
    fn service(&mut self, plugin: &str, service: &str, args: Value) -> Value {
        self.nonce += 1;
        let nonce = self.nonce;
        let capability = format!("{plugin}.call");
        ok(&self.call(json!({
            "op": "capability_invoke",
            "capability": capability,
            // Arguments travel as one JSON string: capability input is capped at depth 4.
            "input": {"service": service, "args_json": args.to_string(), "nonce": nonce},
            "deadline_ms": 5000,
        })));
        let snap = self.wait_for("capability result", move |s| {
            s["capability_result"]["output"]["nonce"] == nonce
        });
        snap["capability_result"]["output"].clone()
    }

    /// Successful host reply data; a panic with the host error otherwise.
    fn data(&mut self, plugin: &str, service: &str, args: Value) -> Value {
        let out = self.service(plugin, service, args);
        assert!(out["host_error"].is_null(), "unexpected host error: {out}");
        out["host"].clone()
    }

    /// Host error code of a service call; a panic when the call succeeded.
    fn refused(&mut self, plugin: &str, service: &str, args: Value) -> String {
        let out = self.service(plugin, service, args);
        out["host_error"]
            .as_str()
            .unwrap_or_else(|| panic!("expected a host error: {out}"))
            .to_owned()
    }

    fn skills(&mut self) -> Value {
        self.snap()["skills"].clone()
    }

    fn items(&mut self) -> Vec<Value> {
        self.skills()["items"].as_array().unwrap().clone()
    }

    fn revision(&mut self) -> u64 {
        self.skills()["revision"].as_u64().unwrap()
    }

    /// User path: validates, dry-runs, approves and enables one version.
    fn promote(&mut self, manifest: Value) {
        let id = manifest["id"].as_str().unwrap().to_owned();
        let version = manifest["version"].as_str().unwrap().to_owned();
        ok(&self.call(json!({"op": "skill_save_draft", "manifest": manifest})));
        ok(&self.call(
            json!({"op": "skill_dry_run", "id": id, "skill_version": version, "inputs": {}}),
        ));
        let revision = self.revision();
        ok(&self.call(json!({"op": "skill_approve", "id": id, "skill_version": version, "revision": revision})));
        let revision = self.revision();
        ok(&self.call(json!({"op": "skill_enable", "id": id, "revision": revision})));
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
    let base = std::env::temp_dir().join(format!("gideon-skills-d3-{}-{name}", std::process::id()));
    let _ = fs::remove_dir_all(&base);
    fs::create_dir_all(base.join("home")).unwrap();
    base
}

/// Manifest with the shared envelope. The one step calls the author proxy, so dependencies hold.
fn manifest(id: &str, version: &str, perms: &[&str]) -> Value {
    json!({
        "schema_version": 1,
        "id": id,
        "name": "Skill de teste",
        "version": version,
        "publisher": {"id": "gideon-test", "name": "Gideon test"},
        "description": "Skill sintetica de teste",
        "license": "MIT",
        "min_runtime": "0.1.0",
        "inputs": {},
        "outputs": {},
        "dependency_capabilities": [format!("{AUTHOR}.call")],
        "permissions_required": perms,
        "steps": [{
            "id": "list",
            "call": format!("{AUTHOR}.call"),
            "args": {"service": "skills.list", "args": {}},
        }],
    })
}

/// One version row. The snapshot shows one row per skill, so every version is read through the
/// author plugin's `skills.list`, which lists all of them.
fn item(core: &mut Core, id: &str, version: &str) -> Value {
    core.data(AUTHOR, "skills.list", json!({}))["items"]
        .as_array()
        .unwrap()
        .iter()
        .find(|i| i["id"] == id && i["version"] == version)
        .cloned()
        .unwrap_or_else(|| panic!("no item {id} {version}"))
}

// ---------------------------------------------------------------------------
// D3: positive path and the draft-only rules
// ---------------------------------------------------------------------------

#[test]
fn draft_put_creates_a_draft_and_never_replaces_the_active_version() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("draft_put");
    let mut core = Core::with_plugins(&dir);
    core.promote(manifest("skill_base", "1.0.0", &[]));
    assert_eq!(item(&mut core, "skill_base", "1.0.0")["state"], "enabled");

    let draft = core.data(
        AUTHOR,
        "skills.draft_put",
        json!({"manifest": manifest("skill_base", "1.1.0", &[])}),
    );
    assert_eq!(draft["state"], "revised", "{draft}");
    assert_eq!(draft["version"], "1.1.0");
    assert_eq!(draft["draft_id"], "skill_base@1.1.0");

    let base = item(&mut core, "skill_base", "1.0.0");
    assert_eq!(base["state"], "enabled");
    assert_eq!(base["active"], true);
    let created = item(&mut core, "skill_base", "1.1.0");
    assert_eq!(created["state"], "draft");
    assert_eq!(created["source"], "llm_draft");
    assert_eq!(created["active"], false);

    let fresh = core.data(
        AUTHOR,
        "skills.draft_put",
        json!({"manifest": manifest("skill_new", "1.0.0", &[])}),
    );
    assert_eq!(fresh["state"], "draft", "{fresh}");
    assert_eq!(item(&mut core, "skill_new", "1.0.0")["source"], "llm_draft");
}

#[test]
fn draft_put_refuses_a_version_that_already_exists() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("draft_exists");
    let mut core = Core::with_plugins(&dir);
    core.promote(manifest("skill_base", "1.0.0", &[]));
    let code = core.refused(
        AUTHOR,
        "skills.draft_put",
        json!({"manifest": manifest("skill_base", "1.0.0", &["audio_route"])}),
    );
    assert_eq!(code, "skill_invalid");
    assert_eq!(item(&mut core, "skill_base", "1.0.0")["state"], "enabled");
    assert_eq!(core.items().len(), 1);
}

#[test]
fn validate_and_dry_run_write_nothing_and_move_no_state() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("validate_dry");
    let mut core = Core::with_plugins(&dir);
    let valid = manifest("skill_check", "1.0.0", &[]);
    assert_eq!(
        core.data(
            AUTHOR,
            "skills.validate",
            json!({"manifest": valid.clone()})
        )["ok"],
        true
    );
    assert!(core.items().is_empty(), "validate must not write");

    core.data(AUTHOR, "skills.draft_put", json!({"manifest": valid}));
    assert_eq!(item(&mut core, "skill_check", "1.0.0")["state"], "draft");
    let simulated = core.data(
        AUTHOR,
        "skills.dry_run",
        json!({"id": "skill_check", "version": "1.0.0", "inputs": {}}),
    );
    assert_eq!(simulated["ok"], true);
    assert_eq!(simulated["steps"], 1);
    assert_eq!(
        item(&mut core, "skill_check", "1.0.0")["state"],
        "draft",
        "plugin dry run must not mark tested"
    );

    let mut broken = manifest("skill_bad", "1.0.0", &[]);
    broken["unexpected"] = json!(true);
    assert_eq!(
        core.data(AUTHOR, "skills.validate", json!({"manifest": broken}))["ok"],
        false
    );
    assert_eq!(core.items().len(), 1);
    assert_eq!(
        core.refused(
            AUTHOR,
            "skills.dry_run",
            json!({"id": "skill_check", "version": "9.9.9", "inputs": {}})
        ),
        "unknown_version"
    );
}

#[test]
fn list_shows_metadata_only() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("list");
    let mut core = Core::with_plugins(&dir);
    core.promote(manifest("skill_base", "1.0.0", &[]));
    core.data(
        AUTHOR,
        "skills.draft_put",
        json!({"manifest": manifest("skill_base", "1.1.0", &[])}),
    );
    let listed = core.data(AUTHOR, "skills.list", json!({}));
    let rows = listed["items"].as_array().unwrap();
    assert_eq!(rows.len(), 2, "{listed}");
    for row in rows {
        let mut keys: Vec<&str> = row
            .as_object()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect();
        keys.sort_unstable();
        assert_eq!(keys, ["active", "id", "source", "state", "version"]);
    }
    let active: Vec<&Value> = rows.iter().filter(|r| r["active"] == true).collect();
    assert_eq!(active.len(), 1);
    assert_eq!(active[0]["state"], "enabled");
    assert_eq!(
        core.refused(AUTHOR, "skills.list", json!({"all": true})),
        "invalid_host_call"
    );
}

#[test]
fn draft_put_writes_one_audit_kind_without_content() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("audit");
    let mut core = Core::with_plugins(&dir);
    core.data(
        AUTHOR,
        "skills.draft_put",
        json!({"manifest": manifest("skill_audit", "1.0.0", &[])}),
    );
    let snap = core.snap();
    let kinds: Vec<&str> = snap["events"]
        .as_array()
        .unwrap()
        .iter()
        .map(|e| e["kind"].as_str().unwrap())
        .collect();
    assert!(kinds.contains(&"skill_draft_put"), "{kinds:?}");
    for event in snap["events"].as_array().unwrap() {
        assert!(event.get("content").is_none());
        assert!(!event["kind"].as_str().unwrap().contains("skill_invalid"));
    }
}

// ---------------------------------------------------------------------------
// D3: a malicious plugin cannot approve, enable, export, run, publish or change any state
// ---------------------------------------------------------------------------

#[test]
fn a_plugin_cannot_reach_any_user_only_service() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("unknown_services");
    let mut core = Core::with_plugins(&dir);
    core.promote(manifest("skill_base", "1.0.0", &[]));
    core.data(
        AUTHOR,
        "skills.draft_put",
        json!({"manifest": manifest("skill_base", "1.1.0", &[])}),
    );
    let before = core.skills();
    let revision = before["revision"].clone();
    let world_before = core.home.join("synthetic/world.json").exists();

    let attempts = [
        "skills.approve",
        "skills.enable",
        "skills.disable",
        "skills.rollback",
        "skills.remove",
        "skills.export",
        "skills.import",
        "skills.import_confirm",
        "skills.run",
        "skills.decide",
        "skills.cancel",
        "skills.publish",
        "skills.save_draft",
        "skills.tested",
        "skills.",
        "skills.Approve",
    ];
    for service in attempts {
        let args = json!({"id": "skill_base", "version": "1.1.0", "revision": revision, "skill_version": "1.1.0", "name": "x", "run_id": "x", "inputs": {}, "manifest": {}});
        assert_eq!(
            core.refused(AUTHOR, service, args),
            "unknown_service",
            "{service}"
        );
    }
    let after = core.skills();
    assert_eq!(after["revision"], revision, "no ledger write");
    assert_eq!(item(&mut core, "skill_base", "1.0.0")["state"], "enabled");
    assert_eq!(item(&mut core, "skill_base", "1.0.0")["active"], true);
    assert_eq!(item(&mut core, "skill_base", "1.1.0")["state"], "draft");
    assert_eq!(
        core.home.join("synthetic/world.json").exists(),
        world_before
    );
    assert!(
        !core.home.join("skill-exports").exists(),
        "no export written"
    );
    assert!(after["run"].is_null());
}

#[test]
fn a_plugin_without_skills_author_is_refused_everywhere() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("no_permission");
    let mut core = Core::with_plugins(&dir);
    let revision = core.revision();
    let manifest_value = manifest("skill_plain", "1.0.0", &[]);
    assert_eq!(
        core.refused(
            PLAIN,
            "skills.validate",
            json!({"manifest": manifest_value.clone()})
        ),
        "permission_denied"
    );
    assert_eq!(
        core.refused(
            PLAIN,
            "skills.draft_put",
            json!({"manifest": manifest_value})
        ),
        "permission_denied"
    );
    assert_eq!(
        core.refused(
            PLAIN,
            "skills.dry_run",
            json!({"id": "skill_plain", "version": "1.0.0", "inputs": {}})
        ),
        "permission_denied"
    );
    assert_eq!(
        core.refused(PLAIN, "skills.list", json!({})),
        "permission_denied"
    );
    assert_eq!(
        core.refused(PLAIN, "skills.approve", json!({})),
        "unknown_service"
    );
    assert_eq!(core.revision(), revision);
    assert!(core.items().is_empty());
    let snap = core.snap();
    assert!(snap["events"]
        .as_array()
        .unwrap()
        .iter()
        .any(|e| e["kind"] == "skill_service_denied"));
}

#[test]
fn host_arguments_are_strict() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("strict_args");
    let mut core = Core::with_plugins(&dir);
    assert_eq!(
        core.refused(
            AUTHOR,
            "skills.draft_put",
            json!({"manifest": manifest("skill_x", "1.0.0", &[]), "extra": 1})
        ),
        "invalid_host_call"
    );
    assert_eq!(
        core.refused(AUTHOR, "skills.draft_put", json!({})),
        "invalid_host_call"
    );
    assert_eq!(
        core.refused(
            AUTHOR,
            "skills.dry_run",
            json!({"id": "skill_x", "version": "1.0.0"})
        ),
        "invalid_host_call"
    );
    assert_eq!(
        core.data(AUTHOR, "skills.validate", json!({"manifest": "text"}))["ok"],
        false
    );
    assert!(core.items().is_empty());
}

#[test]
fn an_invalid_manifest_is_refused_with_its_reason_and_nothing_is_stored() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("invalid_manifest");
    let mut core = Core::with_plugins(&dir);
    let mut leaky = manifest("skill_leaky", "1.0.0", &[]);
    leaky["steps"][0]["args"] =
        json!({"service": "skills.list", "args": {}, "path": "/etc/passwd"});
    assert_eq!(
        core.refused(AUTHOR, "skills.draft_put", json!({"manifest": leaky})),
        "skill_invalid"
    );
    assert!(core.items().is_empty());
    let mut grant = manifest("skill_grant", "1.0.0", &[]);
    grant["steps"][0]["permissions"] = json!(["skills_author"]);
    assert_eq!(
        core.refused(AUTHOR, "skills.draft_put", json!({"manifest": grant})),
        "skill_invalid"
    );
    assert!(core.items().is_empty());
}
