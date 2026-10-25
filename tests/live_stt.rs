//! A14 STT of the live pipeline against the real Core binary with FAKE tools only: the fake recorder
//! (tests/fixtures/fake_audio_tools/pw-record: 1 s silence, 1 s tone, repeated), the test-only energy detector of
//! scripts/wake_worker.py, and a fake STT worker (tests/fixtures/live_audio/fake_stt_worker.py) that stalls or
//! crashes on demand. Proves: a backlog longer than the old queue limit does not fail the session and the final
//! transcript still arrives; a crashed STT worker is restarted (`starting` -> `ready`) with a content-free reason
//! and a private stderr tail, and the next session transcribes. No model, microphone or speaker is involved.
use serde_json::{json, Value};
use std::{
    fs,
    io::{BufRead, BufReader, Write},
    os::unix::{fs::PermissionsExt, net::UnixStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::atomic::{AtomicU64, Ordering},
    thread,
    time::{Duration, Instant},
};

static COUNTER: AtomicU64 = AtomicU64::new(0);

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn fakes_path() -> String {
    format!(
        "{}:/usr/bin:/bin",
        repo().join("tests/fixtures/fake_audio_tools").display()
    )
}

/// A private home whose `scripts/` holds the real workers, with the STT worker replaced by the fake one.
fn lab(name: &str, stt: Value) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("gideon-live-stt-{name}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("data")).unwrap();
    let scripts = dir.join("home/scripts");
    fs::create_dir_all(&scripts).unwrap();
    for entry in fs::read_dir(repo().join("scripts")).unwrap() {
        let path = entry.unwrap().path();
        if path.extension().is_some_and(|e| e == "py") {
            fs::copy(&path, scripts.join(path.file_name().unwrap())).unwrap();
        }
    }
    fs::copy(
        repo().join("tests/fixtures/live_audio/fake_stt_worker.py"),
        scripts.join("stt_worker.py"),
    )
    .unwrap();
    let stt_manifest = dir.join("stt.json");
    fs::write(&stt_manifest, serde_json::to_vec(&stt).unwrap()).unwrap();
    let mut replay: Value = serde_json::from_slice(
        &fs::read(repo().join("tests/fixtures/live_audio/manifest.json")).unwrap(),
    )
    .unwrap();
    replay["stt"] = json!({"python": "/usr/bin/python3", "manifest": stt_manifest});
    // The Core captures only when the wake profile names a `vad` block; the test-only detector needs no model.
    replay["vad"] = json!({});
    fs::write(
        dir.join("replay.json"),
        serde_json::to_vec(&replay).unwrap(),
    )
    .unwrap();
    dir
}

fn spawn(dir: &Path) -> Child {
    let log = fs::File::create(dir.join("core-stderr.log")).unwrap();
    let child = Command::new(env!("CARGO_BIN_EXE_gideon-base"))
        .arg("--root")
        .arg(dir.join("core"))
        .arg("--home")
        .arg(dir.join("home"))
        .arg("--data-dir")
        .arg(dir.join("data"))
        .arg("--wake-replay")
        .arg("/usr/bin/python3")
        .arg(dir.join("replay.json"))
        .arg("0")
        .arg("--live-audio")
        .env("PATH", fakes_path())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(log)
        .spawn()
        .expect("spawn Core");
    let until = Instant::now() + Duration::from_secs(15);
    while !dir.join("core/core.sock").exists() && Instant::now() < until {
        thread::sleep(Duration::from_millis(20));
    }
    child
}

fn call(root: &Path, mut op: Value) -> Value {
    op["version"] = json!(1);
    op["request_id"] = json!(format!("s{}", COUNTER.fetch_add(1, Ordering::Relaxed)));
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

fn snapshot(root: &Path) -> Value {
    call(root, json!({"op": "snapshot"}))
}

fn has_event(snap: &Value, kind: &str) -> bool {
    snap["events"]
        .as_array()
        .is_some_and(|events| events.iter().any(|e| e["kind"] == kind))
}

/// Polls until `done` holds; `seen` records every STT status the snapshots showed, in order.
fn poll(
    root: &Path,
    seconds: u64,
    label: &str,
    seen: &mut Vec<String>,
    done: impl Fn(&Value) -> bool,
) -> Value {
    let deadline = Instant::now() + Duration::from_secs(seconds);
    loop {
        let snap = snapshot(root);
        let status = snap["stt_status"].as_str().unwrap_or_default().to_string();
        if seen.last() != Some(&status) {
            seen.push(status);
        }
        if done(&snap) {
            return snap;
        }
        assert!(
            Instant::now() < deadline,
            "timed out waiting for {label}: {snap}"
        );
        thread::sleep(Duration::from_millis(50));
    }
}

fn kill_quietly(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}

#[test]
fn a_backlog_longer_than_the_old_queue_limit_does_not_fail_the_session() {
    // 3 messages of 160 ms each stall the worker for 0.8 s: about 2.4 s of audio waits, well past the old
    // 16-message limit of 20 ms frames (0.32 s). The session must still end with its final transcript.
    let dir = lab(
        "backlog",
        json!({"engine": "fake-stt", "stall_messages": 3, "stall_s": 0.8}),
    );
    let root = dir.join("core");
    let mut child = spawn(&dir);
    let mut seen = Vec::new();
    poll(&root, 30, "STT ready", &mut seen, |s| {
        s["stt_status"] == "ready"
    });
    let snap = poll(&root, 60, "final transcript", &mut seen, |s| {
        has_event(s, "transcript_final")
    });
    assert!(
        !has_event(&snap, "stt_failed"),
        "a backlog failed the session: {snap}"
    );
    assert_eq!(snap["stt_status"], "ready");
    assert!(snap.get("stt_last_error").is_none());
    assert!(!root.join("stt-last-error.txt").exists());
    kill_quietly(&mut child);
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn a_crashed_stt_worker_restarts_and_the_next_session_transcribes() {
    // The first worker exits after 4 frame messages (once). The Core ends that session, restarts the worker with
    // backoff (status starting -> ready), keeps the content-free reason, and writes the stderr tail privately.
    let dir = lab("crash", json!({"engine": "fake-stt", "crash_after": 4}));
    let root = dir.join("core");
    let mut child = spawn(&dir);
    let mut seen = Vec::new();
    poll(&root, 30, "STT ready", &mut seen, |s| {
        s["stt_status"] == "ready"
    });
    poll(&root, 60, "the crash", &mut seen, |s| {
        has_event(s, "stt_failed")
    });
    // Only the first worker crashes: the sandbox /tmp is private, so the manifest itself switches the crash off
    // before the restart (the restart waits 500 ms after the failure).
    fs::write(
        dir.join("stt.json"),
        json!({"engine": "fake-stt"}).to_string(),
    )
    .unwrap();
    let snap = poll(
        &root,
        60,
        "restart and a final transcript",
        &mut seen,
        |s| s["stt_status"] == "ready" && has_event(s, "transcript_final"),
    );
    assert!(
        seen.iter().any(|s| s == "starting"),
        "no restart seen: {seen:?}"
    );
    assert_eq!(snap["stt_last_error"], "worker_crashed");
    let tail_file = root.join("stt-last-error.txt");
    let meta = fs::metadata(&tail_file).expect("stderr tail file");
    assert_eq!(meta.permissions().mode() & 0o777, 0o600);
    let tail = fs::read_to_string(&tail_file).unwrap();
    assert!(tail.contains("fake stt crash"), "tail: {tail}");
    kill_quietly(&mut child);
    let _ = fs::remove_dir_all(&dir);
}
