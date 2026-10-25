//! S4 D4 sharing against the real Core binary: `skill_export` writes `<home>/skill-exports`, and
//! `skill_import` / `skill_import_confirm` read only `<home>/skill-imports`. Every package is a
//! file the test writes or copies; nothing leaves the temporary directory. Imports never grant
//! permissions: a confirmed package is a `draft` that must be approved again.
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
const AUTHOR: &str = "skillauthor";

/// Proxy plugin: forwards `args_json` as one `host_call` and returns the reply in the output.
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

fn specs() -> Vec<Spec> {
    let caps = ["skillauthor.call"];
    let payload = PROXY_STUB
        .replace("@PLUGIN_ID@", AUTHOR)
        .replace("@CAPS@", &serde_json::to_string(&caps).unwrap())
        .into_bytes();
    vec![Spec {
        id: AUTHOR,
        caps: caps.to_vec(),
        perms: vec!["skills_author"],
        payload,
    }]
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

/// One Core process. `root` is private to this Core; `home` is shared by Cores of one test.
struct Core {
    root: PathBuf,
    home: PathBuf,
    catalog: (PathBuf, String),
    child: Option<Child>,
    counter: u64,
}

impl Core {
    /// Fresh Core with its own root, on the shared home of `dir`, with the author plugin running.
    fn start(dir: &Path, root: &str) -> Core {
        let mut core = Core::open(dir, root);
        for spec in specs() {
            core.install(spec.id, &spec.payload);
            core.enable(spec.id);
        }
        core
    }

    /// Starts a Core on an existing root: the plugin was installed and enabled before, so it runs
    /// again from the ledgers alone.
    fn reopen(dir: &Path, root: &str) -> Core {
        let mut core = Core::open(dir, root);
        core.wait_for("restored plugin", |s| {
            s["plugins"]["items"]
                .as_array()
                .unwrap()
                .iter()
                .any(|i| i["plugin_id"] == AUTHOR && i["state"] == "running")
        });
        core
    }

    fn open(dir: &Path, root: &str) -> Core {
        let mut core = Core {
            root: dir.join(root),
            home: dir.join("home"),
            catalog: catalog(dir, &specs()),
            child: None,
            counter: 0,
        };
        core.spawn();
        core
    }

    fn spawn(&mut self) {
        let log = fs::File::create(self.root.parent().unwrap().join(format!(
            "{}.log",
            self.root.file_name().unwrap().to_string_lossy()
        )))
        .unwrap();
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

    /// Response code of one op.
    fn code(&mut self, op: Value) -> String {
        self.call(op)["code"].as_str().unwrap().to_owned()
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

    fn revision(&mut self) -> u64 {
        self.snap()["skills"]["revision"].as_u64().unwrap()
    }

    /// Every version row of the ledger, read through the author plugin's `skills.list`.
    fn versions(&mut self) -> Vec<Value> {
        let nonce = self.counter + 1000;
        ok(&self.call(json!({
            "op": "capability_invoke",
            "capability": "skillauthor.call",
            "input": {"service": "skills.list", "args_json": "{}", "nonce": nonce},
            "deadline_ms": 5000,
        })));
        let snap = self.wait_for("list", move |s| {
            s["capability_result"]["output"]["nonce"] == nonce
        });
        snap["capability_result"]["output"]["host"]["items"]
            .as_array()
            .unwrap()
            .clone()
    }

    /// Saves a manifest as `validated` (user path).
    fn save(&mut self, manifest: Value) {
        ok(&self.call(json!({"op": "skill_save_draft", "manifest": manifest})));
    }

    /// Saves, simulates, approves and enables one version (user path).
    fn promote(&mut self, manifest: Value) {
        let id = manifest["id"].as_str().unwrap().to_owned();
        let version = manifest["version"].as_str().unwrap().to_owned();
        self.save(manifest);
        ok(&self.call(
            json!({"op": "skill_dry_run", "id": id, "skill_version": version, "inputs": {}}),
        ));
        let revision = self.revision();
        ok(&self.call(json!({"op": "skill_approve", "id": id, "skill_version": version, "revision": revision})));
        let revision = self.revision();
        ok(&self.call(json!({"op": "skill_enable", "id": id, "revision": revision})));
    }

    fn export(&mut self, id: &str, version: &str) -> PathBuf {
        ok(&self.call(json!({"op": "skill_export", "id": id, "skill_version": version})));
        self.home
            .join("skill-exports")
            .join(format!("{id}-{version}.gskill"))
    }

    fn import(&mut self, name: &str) -> String {
        self.code(json!({"op": "skill_import", "name": name}))
    }

    fn confirm(&mut self, name: &str) -> String {
        let revision = self.revision();
        self.code(json!({"op": "skill_import_confirm", "name": name, "revision": revision}))
    }

    fn preview(&mut self) -> Value {
        self.snap()["skills"]["import"].clone()
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
    let base = std::env::temp_dir().join(format!("gideon-skills-d4-{}-{name}", std::process::id()));
    let _ = fs::remove_dir_all(&base);
    fs::create_dir_all(base.join("home")).unwrap();
    base
}

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
        "dependency_capabilities": ["skillauthor.call"],
        "permissions_required": perms,
        "steps": [{
            "id": "list",
            "call": "skillauthor.call",
            "args": {"service": "skills.list", "args": {}},
        }],
    })
}

/// Places a file in `<home>/skill-imports` (0600), creating the directory like the Core would.
fn place(home: &Path, name: &str, bytes: &[u8]) -> PathBuf {
    let dir = home.join("skill-imports");
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join(format!("{name}.gskill"));
    fs::write(&path, bytes).unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
    path
}

fn read_json(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

/// Exports `id` `version` from a fresh Core and returns the package bytes, then drops that Core.
fn package_from(dir: &Path, root: &str, id: &str, version: &str, perms: &[&str]) -> Vec<u8> {
    let mut core = Core::start(dir, root);
    core.promote(manifest(id, version, perms));
    let path = core.export(id, version);
    fs::read(path).unwrap()
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

#[test]
fn export_is_private_and_carries_only_the_package_fields() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("export");
    let mut core = Core::start(&dir, "core");
    core.promote(manifest("skill_share", "1.0.0", &[]));
    let path = core.export("skill_share", "1.0.0");
    assert_eq!(
        fs::metadata(&path).unwrap().permissions().mode() & 0o777,
        0o600
    );
    let text = fs::read_to_string(&path).unwrap();
    assert!(
        !text.contains(dir.to_str().unwrap()),
        "no user path in the package"
    );
    for banned in [
        "revision",
        "history",
        "\"run\"",
        "approved_at_rev",
        "\"state\"",
    ] {
        assert!(!text.contains(banned), "{banned} must not travel");
    }
    let package = read_json(&path);
    let mut keys: Vec<&str> = package
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    keys.sort_unstable();
    assert_eq!(
        keys,
        [
            "author",
            "files",
            "format",
            "license",
            "manifest",
            "package_sha256",
            "publisher_id",
            "readme",
            "signature",
            "version"
        ]
    );
    assert_eq!(package["format"], 1);
    assert!(package["signature"].is_null());
    assert_eq!(package["version"], "1.0.0");
    assert_eq!(package["publisher_id"], "gideon-test");
    assert_eq!(package["files"][0]["path"], "skill.json");
    assert_eq!(package["files"].as_array().unwrap().len(), 1);
    assert_eq!(package["manifest"]["id"], "skill_share");
    let manifest_bytes = serde_json::to_vec(&package["manifest"]).unwrap();
    assert_eq!(package["files"][0]["sha256"], sha(&manifest_bytes).as_str());
}

#[test]
fn export_refuses_an_unknown_version() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("export_unknown");
    let mut core = Core::start(&dir, "core");
    assert_eq!(
        core.code(json!({"op": "skill_export", "id": "skill_none", "skill_version": "1.0.0"})),
        "unknown_version"
    );
    assert!(!core.home.join("skill-exports").exists());
}

// ---------------------------------------------------------------------------
// Import: round trip, preview shape and confirm
// ---------------------------------------------------------------------------

#[test]
fn import_round_trip_previews_then_installs_a_draft_that_grants_nothing() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("roundtrip");
    let mut core = Core::start(&dir, "core");
    core.promote(manifest("skill_share", "1.0.0", &[]));
    let exported = core.export("skill_share", "1.0.0");
    let bytes = fs::read(&exported).unwrap();
    let revision = core.revision();
    assert_eq!(
        core.code(json!({"op": "skill_remove", "id": "skill_share", "revision": revision})),
        "ok"
    );
    place(&core.home, "roundtrip", &bytes);

    assert_eq!(core.import("roundtrip"), "ok");
    let preview = core.preview();
    let mut keys: Vec<&str> = preview
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    keys.sort_unstable();
    assert_eq!(
        keys,
        [
            "duplicate",
            "findings",
            "id",
            "missing_deps",
            "name",
            "permission_delta",
            "permissions_escalated",
            "permissions_required",
            "publisher",
            "unverified",
            "version"
        ]
    );
    assert_eq!(preview["name"], "roundtrip");
    assert_eq!(preview["id"], "skill_share");
    assert_eq!(preview["unverified"], true);
    assert_eq!(preview["duplicate"], false);
    assert_eq!(preview["permissions_escalated"], false);
    assert!(
        preview["findings"].as_array().unwrap().is_empty(),
        "{preview}"
    );

    assert_eq!(core.confirm("roundtrip"), "ok");
    assert!(core.preview().is_null(), "a confirmed preview is cleared");
    let rows = core.versions();
    let row = rows.iter().find(|r| r["id"] == "skill_share").unwrap();
    assert_eq!(row["state"], "draft");
    assert_eq!(row["source"], "imported");
    assert_eq!(row["active"], false);
    let revision = core.revision();
    assert_eq!(
        core.code(json!({"op": "skill_enable", "id": "skill_share", "revision": revision})),
        "skill_not_approved"
    );
}

#[test]
fn an_update_shows_the_permission_delta_and_marks_escalation() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("escalation");
    let newer = package_from(&dir, "source", "skill_upd", "2.0.0", &["audio_route"]);
    let mut core = Core::start(&dir, "target");
    core.promote(manifest("skill_upd", "1.0.0", &[]));
    place(&core.home, "upd", &newer);

    assert_eq!(core.import("upd"), "ok");
    let preview = core.preview();
    assert_eq!(preview["permission_delta"], json!(["audio_route"]));
    assert_eq!(preview["permissions_escalated"], true);
    assert_eq!(preview["duplicate"], false);
    let codes: Vec<&str> = preview["findings"]
        .as_array()
        .unwrap()
        .iter()
        .map(|f| f["code"].as_str().unwrap())
        .collect();
    assert_eq!(
        codes,
        ["skill_invalid:permissions_escalated"],
        "escalation is a warning, not a block"
    );

    assert_eq!(core.confirm("upd"), "ok");
    let rows = core.versions();
    let updated = rows
        .iter()
        .find(|r| r["id"] == "skill_upd" && r["version"] == "2.0.0")
        .unwrap();
    assert_eq!(updated["state"], "draft");
    assert_eq!(updated["active"], false);
    let previous = rows
        .iter()
        .find(|r| r["id"] == "skill_upd" && r["version"] == "1.0.0")
        .unwrap();
    assert_eq!(
        previous["state"], "enabled",
        "the enabled version keeps running"
    );
    assert_eq!(previous["active"], true);
}

#[test]
fn rollback_works_after_an_imported_update_is_approved_and_enabled() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("rollback");
    let newer = package_from(&dir, "source", "skill_roll", "2.0.0", &[]);
    let mut core = Core::start(&dir, "target");
    core.promote(manifest("skill_roll", "1.0.0", &[]));
    place(&core.home, "roll", &newer);
    assert_eq!(core.import("roll"), "ok");
    assert_eq!(core.confirm("roll"), "ok");

    ok(&core.call(
        json!({"op": "skill_dry_run", "id": "skill_roll", "skill_version": "2.0.0", "inputs": {}}),
    ));
    let revision = core.revision();
    ok(&core.call(json!({"op": "skill_approve", "id": "skill_roll", "skill_version": "2.0.0", "revision": revision})));
    let revision = core.revision();
    ok(&core.call(json!({"op": "skill_enable", "id": "skill_roll", "revision": revision})));
    let snap = core.snap();
    assert_eq!(snap["skills"]["items"][0]["version"], "2.0.0");
    let revision = core.revision();
    ok(&core.call(json!({"op": "skill_rollback", "id": "skill_roll", "revision": revision})));
    let rows = core.versions();
    let back = rows.iter().find(|r| r["version"] == "1.0.0").unwrap();
    assert_eq!(back["state"], "enabled");
    assert_eq!(back["active"], true);
    let forward = rows.iter().find(|r| r["version"] == "2.0.0").unwrap();
    assert_eq!(forward["state"], "revised");
}

#[test]
fn versions_stay_at_most_three_and_the_fourth_import_is_refused() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("limit");
    let fourth = package_from(&dir, "source", "skill_lim", "4.0.0", &[]);
    let mut core = Core::start(&dir, "target");
    for version in ["1.0.0", "2.0.0", "3.0.0"] {
        core.save(manifest("skill_lim", version, &[]));
    }
    place(&core.home, "lim", &fourth);
    assert_eq!(core.import("lim"), "ok");
    assert_eq!(core.confirm("lim"), "skill_invalid:version_limit");
    assert_eq!(
        core.versions()
            .iter()
            .filter(|r| r["id"] == "skill_lim")
            .count(),
        3
    );
}

// ---------------------------------------------------------------------------
// Import negatives
// ---------------------------------------------------------------------------

#[test]
fn bad_names_are_refused_before_any_file_is_opened() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("names");
    let mut core = Core::start(&dir, "core");
    let long = "a".repeat(65);
    for name in [
        "../escape",
        "sub/x",
        ".hidden",
        "..",
        "",
        "a b",
        "a\\b",
        long.as_str(),
    ] {
        assert_eq!(core.import(name), "invalid_import", "{name:?}");
    }
    assert!(core.preview().is_null());
}

#[test]
fn a_symlink_in_the_import_folder_is_refused() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("symlink");
    let bytes = package_from(&dir, "source", "skill_link", "1.0.0", &[]);
    let mut core = Core::start(&dir, "core");
    let real = place(&core.home, "real", &bytes);
    fs::remove_file(&real).unwrap();
    let target = dir.join("elsewhere.gskill");
    fs::write(&target, &bytes).unwrap();
    std::os::unix::fs::symlink(
        &target,
        core.home.join("skill-imports").join("linked.gskill"),
    )
    .unwrap();
    assert_eq!(core.import("linked"), "skill_invalid:symlink");
    assert!(core.preview().is_null());
}

#[test]
fn an_oversize_package_is_refused() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("oversize");
    let mut core = Core::start(&dir, "core");
    place(&core.home, "big", &vec![b' '; 70 * 1024]);
    assert_eq!(core.import("big"), "skill_invalid:file_too_large");
}

#[test]
fn a_tampered_manifest_is_flagged_and_cannot_be_confirmed() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("tampered");
    let bytes = package_from(&dir, "source", "skill_tamper", "1.0.0", &[]);
    let mut core = Core::start(&dir, "core");
    let mut package: Value = serde_json::from_slice(&bytes).unwrap();
    package["manifest"]["description"] = json!("Descricao trocada depois da exportacao");
    place(
        &core.home,
        "tampered",
        &serde_json::to_vec(&package).unwrap(),
    );

    assert_eq!(core.import("tampered"), "ok");
    let codes: Vec<String> = core.preview()["findings"]
        .as_array()
        .unwrap()
        .iter()
        .map(|f| f["code"].as_str().unwrap().to_owned())
        .collect();
    assert!(
        codes.contains(&"skill_invalid:hash_mismatch".to_owned()),
        "{codes:?}"
    );
    let before = core.versions().len();
    assert_eq!(core.confirm("tampered"), "skill_invalid:hash_mismatch");
    assert_eq!(core.versions().len(), before, "nothing installed");
}

#[test]
fn a_corrupted_package_is_refused() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("corrupt");
    let bytes = package_from(&dir, "source", "skill_cut", "1.0.0", &[]);
    let mut core = Core::start(&dir, "core");
    place(&core.home, "cut", &bytes[..bytes.len() / 2]);
    assert_eq!(core.import("cut"), "invalid_import");
    place(&core.home, "wrong_format", br#"{"format": 2}"#);
    assert_eq!(core.import("wrong_format"), "invalid_import");
    assert!(core.preview().is_null());
}

#[test]
fn a_package_outside_the_import_folder_is_never_read() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("wrong_dir");
    let bytes = package_from(&dir, "source", "skill_away", "1.0.0", &[]);
    let mut core = Core::start(&dir, "core");
    fs::create_dir_all(core.home.join("skill-exports")).unwrap();
    fs::write(core.home.join("skill-exports").join("away.gskill"), &bytes).unwrap();
    fs::write(core.home.join("away.gskill"), &bytes).unwrap();
    assert_eq!(core.import("away"), "import_not_found");
    assert!(core.preview().is_null());
}

#[test]
fn a_duplicate_id_and_version_is_refused() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("duplicate");
    let mut core = Core::start(&dir, "core");
    core.promote(manifest("skill_same", "1.0.0", &[]));
    let bytes = fs::read(core.export("skill_same", "1.0.0")).unwrap();
    place(&core.home, "same", &bytes);
    assert_eq!(core.import("same"), "ok");
    let preview = core.preview();
    assert_eq!(preview["duplicate"], true);
    assert_eq!(preview["findings"][0]["code"], "skill_invalid:duplicate_id");
    assert_eq!(core.confirm("same"), "skill_invalid:duplicate_id");
    assert_eq!(
        core.versions()
            .iter()
            .filter(|r| r["id"] == "skill_same")
            .count(),
        1
    );
}

#[test]
fn confirm_needs_the_same_file_and_the_current_revision() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("confirm");
    let bytes = package_from(&dir, "source", "skill_cfm", "1.0.0", &[]);
    let mut core = Core::start(&dir, "core");
    let revision = core.revision();
    assert_eq!(
        core.code(json!({"op": "skill_import_confirm", "name": "cfm", "revision": revision})),
        "stale_import"
    );

    let path = place(&core.home, "cfm", &bytes);
    assert_eq!(core.import("cfm"), "ok");
    let stale = core.revision();
    let mut edited: Value = serde_json::from_slice(&bytes).unwrap();
    edited["readme"] = json!("Leia antes");
    fs::write(&path, serde_json::to_vec(&edited).unwrap()).unwrap();
    assert_eq!(
        core.code(json!({"op": "skill_import_confirm", "name": "cfm", "revision": stale})),
        "stale_import"
    );

    fs::write(&path, &bytes).unwrap();
    assert_eq!(core.import("cfm"), "ok");
    assert_eq!(
        core.code(json!({"op": "skill_import_confirm", "name": "cfm", "revision": stale + 1000})),
        "stale_skill_revision"
    );
    assert_eq!(core.confirm("cfm"), "ok");
}

#[test]
fn an_import_never_survives_a_restart_as_a_grant() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("restart");
    let bytes = package_from(&dir, "source", "skill_rst", "1.0.0", &["audio_route"]);
    let mut core = Core::start(&dir, "core");
    place(&core.home, "rst", &bytes);
    assert_eq!(core.import("rst"), "ok");
    assert_eq!(core.confirm("rst"), "ok");
    drop(core);
    let mut core = Core::reopen(&dir, "core");
    let rows = core.versions();
    let row = rows.iter().find(|r| r["id"] == "skill_rst").unwrap();
    assert_eq!(row["state"], "draft");
    assert_eq!(row["active"], false);
    assert!(core.snap()["skills"]["import"].is_null());
}

// ---------------------------------------------------------------------------
// WP15 (docs/WP15.md): export path in the snapshot, disable event, step target, index listing and
// the run-history retention. Each feature has a positive and a negative case.
// ---------------------------------------------------------------------------

#[test]
fn export_returns_its_path_in_the_snapshot_and_a_refused_export_changes_nothing() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("wp15_export");
    let mut core = Core::start(&dir, "core");
    assert!(core.snap()["skills"]["last_export"].is_null());
    core.promote(manifest("skill_exp", "1.0.0", &[]));
    let path = core.export("skill_exp", "1.0.0");
    let snap = core.snap();
    assert_eq!(snap["skills"]["last_export"]["id"], "skill_exp");
    assert_eq!(snap["skills"]["last_export"]["version"], "1.0.0");
    assert_eq!(
        snap["skills"]["last_export"]["path"].as_str().unwrap(),
        path.to_str().unwrap()
    );
    assert!(path.is_file());
    // A refused export keeps the last successful one.
    assert_eq!(
        core.code(json!({"op": "skill_export", "id": "skill_exp", "skill_version": "9.9.9"})),
        "unknown_version"
    );
    assert_eq!(core.snap()["skills"]["last_export"]["version"], "1.0.0");
}

#[test]
fn disabling_a_skill_emits_skill_disabled_even_without_an_active_run() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("wp15_disable");
    let mut core = Core::start(&dir, "core");
    core.promote(manifest("skill_off", "1.0.0", &[]));
    let revision = core.revision();
    ok(&core.call(json!({"op": "skill_disable", "id": "skill_off", "revision": revision})));
    let kinds = |snap: &Value| -> usize {
        snap["events"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|e| e["kind"] == "skill_disabled")
            .count()
    };
    assert_eq!(kinds(&core.snap()), 1);
    // Negative: a disable that is refused (not enabled any more) emits nothing.
    let revision = core.revision();
    assert_eq!(
        core.code(json!({"op": "skill_disable", "id": "skill_off", "revision": revision})),
        "skill_not_enabled"
    );
    assert_eq!(kinds(&core.snap()), 1);
}

#[test]
fn a_step_target_must_name_the_call_and_a_capability_or_tool() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("wp15_target");
    let mut core = Core::start(&dir, "core");
    let mut matching = manifest("skill_tgt", "1.0.0", &[]);
    matching["steps"][0]["target"] = json!("skillauthor.call");
    assert_eq!(
        core.code(json!({"op": "skill_save_draft", "manifest": matching})),
        "ok"
    );
    let mut other = manifest("skill_tgt", "1.1.0", &[]);
    other["steps"][0]["target"] = json!("skillauthor.other");
    assert_eq!(
        core.code(json!({"op": "skill_save_draft", "manifest": other})),
        "skill_invalid:target_mismatch"
    );
    // A target on a step whose call is a skill is refused too (a skill runs its own steps).
    let mut skill_call = manifest("skill_tgt", "1.2.0", &[]);
    skill_call["steps"][0]["call"] = json!("skill:skill_tgt");
    skill_call["steps"][0]["args"] = json!({});
    skill_call["steps"][0]["target"] = json!("skill:skill_tgt");
    assert_ne!(
        core.code(json!({"op": "skill_save_draft", "manifest": skill_call})),
        "ok"
    );
}

#[test]
fn the_github_index_is_listed_with_presence_and_a_malformed_index_is_reported() {
    let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let dir = setup("wp15_index");
    let mut core = Core::start(&dir, "core");
    let folder = core.home.join("skill-imports");
    fs::create_dir_all(&folder).unwrap();
    let index = |entries: Value| {
        json!({
            "format": 1,
            "repository": "https://github.com/owner/repo",
            "skills": entries,
        })
    };
    let entry = json!({
        "name": "fixture-note",
        "version": "1.0.0",
        "sha256": "a".repeat(64),
        "url": "https://github.com/owner/repo/releases/download/v1/fixture-note.gskill",
        "signature": null,
    });
    fs::write(
        folder.join("index.json"),
        serde_json::to_vec(&index(json!([entry.clone()]))).unwrap(),
    )
    .unwrap();
    let listed = core.snap()["skills"]["index"].clone();
    assert_eq!(listed["repository"], "https://github.com/owner/repo");
    assert_eq!(listed["entries"][0]["name"], "fixture-note");
    assert_eq!(listed["entries"][0]["url"], entry["url"]);
    assert_eq!(listed["entries"][0]["signed"], false);
    assert_eq!(listed["entries"][0]["present"], false);
    assert!(listed["error"].is_null());
    // The package appears in the folder: the entry reads as present. Nothing was fetched.
    fs::write(folder.join("fixture-note.gskill"), b"not fetched").unwrap();
    assert_eq!(
        core.snap()["skills"]["index"]["entries"][0]["present"],
        true
    );
    // A duplicate name refuses the whole index and the snapshot says why.
    fs::write(
        folder.join("index.json"),
        serde_json::to_vec(&index(json!([entry.clone(), entry]))).unwrap(),
    )
    .unwrap();
    let refused = core.snap()["skills"]["index"].clone();
    assert_eq!(refused["error"], "invalid_import");
    assert!(refused["entries"].as_array().unwrap().is_empty());
}

#[test]
fn retention_keeps_only_runs_inside_the_window_and_never_clears_nothing_silently() {
    use gideon_base::skills::{retain_runs, RunRecord};
    let day = 86_400_000u64;
    let now = 100 * day;
    let run = |id: &str, at_ms: Option<u64>| -> RunRecord {
        let mut value = json!({
            "run_id": id,
            "skill": "skill_ret",
            "version": "1.0.0",
            "state": "done",
            "step": null,
            "codes": [],
        });
        if let Some(at) = at_ms {
            value["at_ms"] = json!(at);
        }
        serde_json::from_value(value).unwrap()
    };
    let mut runs = vec![
        run("recent", Some(now - day)),
        run("old", Some(now - 40 * day)),
        run("legacy", None),
    ];
    // 30-day window: the old and the time-less records go.
    assert!(retain_runs(&mut runs, Some(30), now));
    let kept: Vec<String> = runs
        .iter()
        .map(|r| {
            serde_json::to_value(r).unwrap()["run_id"]
                .as_str()
                .unwrap()
                .to_owned()
        })
        .collect();
    assert_eq!(kept, ["recent"]);
    // Nothing left to drop: no change reported.
    assert!(!retain_runs(&mut runs, Some(30), now));
    // `never` keeps nothing.
    assert!(retain_runs(&mut runs, None, now));
    assert!(runs.is_empty());
    assert!(!retain_runs(&mut runs, None, now));
}
