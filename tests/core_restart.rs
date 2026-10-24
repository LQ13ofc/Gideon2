//! `core_restart` against the real Core binary. The reply is `ok` and carries the request id; then the
//! process exits with status 75 (`RESTART_EXIT_CODE`) after its ledgers are flushed, and a new Core on
//! the same root starts again. Unknown fields are refused at the wire. Busy refusals (voice, agent,
//! skill, plugin) are covered by the unit tests in `src/core.rs`.
use serde_json::{json, Value};
use std::{
    fs,
    io::{BufRead, BufReader, Write},
    os::unix::net::UnixStream,
    path::Path,
    process::{Child, Command, ExitStatus, Stdio},
    thread,
    time::{Duration, Instant},
};

fn spawn(dir: &Path) -> Child {
    Command::new(env!("CARGO_BIN_EXE_gideon-base"))
        .arg("--root")
        .arg(dir.join("core"))
        .arg("--home")
        .arg(dir.join("home"))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("spawn Core")
}

fn call(root: &Path, mut op: Value) -> Value {
    op["version"] = json!(1);
    let mut stream = UnixStream::connect(root.join("core.sock")).expect("connect Core");
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

fn wait_ready(root: &Path) {
    let deadline = Instant::now() + Duration::from_secs(10);
    while Instant::now() < deadline {
        let up = UnixStream::connect(root.join("core.sock")).is_ok()
            && call(root, json!({"op": "snapshot", "request_id": "ready"}))["code"] == "ok";
        if up {
            return;
        }
        thread::sleep(Duration::from_millis(20));
    }
    panic!("Core did not start");
}

fn wait_exit(child: &mut Child) -> ExitStatus {
    let deadline = Instant::now() + Duration::from_secs(15);
    loop {
        if let Some(status) = child.try_wait().unwrap() {
            return status;
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            panic!("Core did not exit after core_restart");
        }
        thread::sleep(Duration::from_millis(20));
    }
}

#[test]
fn core_restart_replies_ok_exits_75_and_the_same_root_starts_again() {
    let dir = std::env::temp_dir().join(format!("gideon-core-restart-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("home")).unwrap();
    let root = dir.join("core");

    let mut child = spawn(&dir);
    wait_ready(&root);
    let reply = call(&root, json!({"op": "core_restart", "request_id": "rs1"}));
    assert_eq!(reply["code"], "ok", "{reply}");
    assert_eq!(reply["request_id"], "rs1");
    assert!(reply["events"]
        .as_array()
        .unwrap()
        .iter()
        .any(|e| e["kind"] == "core_restart_requested"));
    let status = wait_exit(&mut child);
    assert_eq!(status.code(), Some(75), "{status:?}");
    assert!(!root.join("core.sock").exists(), "socket removed on exit");

    // A new Core on the same root starts: the restart kept the ledgers usable.
    let mut again = spawn(&dir);
    wait_ready(&root);
    let snap = call(&root, json!({"op": "snapshot", "request_id": "s2"}));
    assert_eq!(snap["code"], "ok");
    // Unknown fields are refused on the wire; the Core stays up.
    let refused = call(
        &root,
        json!({"op": "core_restart", "request_id": "rs3", "force": true}),
    );
    assert_eq!(refused["code"], "invalid_message", "{refused}");
    assert!(child_alive(&mut again));
    again.kill().unwrap();
    let _ = again.wait();
    let _ = fs::remove_dir_all(&dir);
}

fn child_alive(child: &mut Child) -> bool {
    child.try_wait().unwrap().is_none()
}
