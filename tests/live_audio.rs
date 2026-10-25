//! A5 `--live-audio` against the real Core binary with FAKE tools only: `pw-record` / `pw-play` from
//! tests/fixtures/fake_audio_tools (first on PATH, run inside the real bwrap sandbox) and the
//! test-only energy detector of scripts/wake_worker.py (tests/fixtures/live_audio/manifest.json).
//! Proves: frames from the recorder reach the wake detector; mic state follows the recorder; device
//! and sensitivity changes restart the pipeline with new arguments; shutdown kills the recorder; the
//! restart budget stops a crashing recorder; the player delivers exact PCM. No real microphone or
//! speaker is involved, so nothing here validates acoustic behaviour.
use gideon_base::live::{self, Player};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{BufRead, BufReader, Write},
    os::unix::net::UnixStream,
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

fn spawn(dir: &Path) -> Child {
    // `--data-dir` must already exist (it is validated like `--home`).
    fs::create_dir_all(dir.join("data")).unwrap();
    Command::new(env!("CARGO_BIN_EXE_gideon-base"))
        .arg("--root")
        .arg(dir.join("core"))
        .arg("--home")
        .arg(repo())
        .arg("--data-dir")
        .arg(dir.join("data"))
        .arg("--wake-replay")
        .arg("/usr/bin/python3")
        .arg(repo().join("tests/fixtures/live_audio/manifest.json"))
        .arg("0")
        .arg("--live-audio")
        .env("PATH", fakes_path())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("spawn Core")
}

fn call(root: &Path, mut op: Value) -> Value {
    op["version"] = json!(1);
    if op.get("request_id").is_none() {
        op["request_id"] = json!(format!("t{}", COUNTER.fetch_add(1, Ordering::Relaxed)));
    }
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

fn wait_ready(root: &Path) {
    let deadline = Instant::now() + Duration::from_secs(15);
    while Instant::now() < deadline {
        if UnixStream::connect(root.join("core.sock")).is_ok() && snapshot(root)["code"] == "ok" {
            return;
        }
        thread::sleep(Duration::from_millis(20));
    }
    panic!("Core did not start");
}

/// Polls snapshots until `done` holds; panics with the last snapshot on timeout.
fn wait_snapshot(root: &Path, seconds: u64, label: &str, done: impl Fn(&Value) -> bool) -> Value {
    let deadline = Instant::now() + Duration::from_secs(seconds);
    loop {
        let snap = snapshot(root);
        if done(&snap) {
            return snap;
        }
        if Instant::now() >= deadline {
            panic!(
                "timed out: {label}; last audio={} events={}",
                snap["audio"], snap["events"]
            );
        }
        thread::sleep(Duration::from_millis(50));
    }
}

/// Process ids whose argv contains `first` immediately followed by `second` (both exact arguments).
fn pids_with_pair(first: &str, second: &str) -> Vec<u32> {
    let mut found = Vec::new();
    let Ok(entries) = fs::read_dir("/proc") else {
        return found;
    };
    for entry in entries.flatten() {
        let Some(pid) = entry
            .file_name()
            .to_str()
            .and_then(|s| s.parse::<u32>().ok())
        else {
            continue;
        };
        let Ok(raw) = fs::read(entry.path().join("cmdline")) else {
            continue;
        };
        let args: Vec<&[u8]> = raw.split(|b| *b == 0).collect();
        if args
            .windows(2)
            .any(|w| w[0] == first.as_bytes() && w[1] == second.as_bytes())
        {
            found.push(pid);
        }
    }
    found
}

fn wait_pair(first: &str, second: &str, seconds: u64) -> bool {
    let deadline = Instant::now() + Duration::from_secs(seconds);
    while Instant::now() < deadline {
        if !pids_with_pair(first, second).is_empty() {
            return true;
        }
        thread::sleep(Duration::from_millis(50));
    }
    false
}

fn set_preferences(root: &Path, device: &str, sensitivity: f64) -> Value {
    let snap = snapshot(root);
    let revision = snap["preferences"]["revision"].as_u64().unwrap();
    call(
        root,
        json!({
            "op": "preferences",
            "revision": revision,
            "audible_feedback": true,
            "session_timeout_ms": 9000,
            "wake_sensitivity": sensitivity,
            "audio_input_device": device,
            "audio_output_device": "default",
        }),
    )
}

fn kill_quietly(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}

/// The replay profile WITHOUT `--live-audio`: the start-up mode comes from the ledger alone (A6). The wake
/// python is the fake of tests/fixtures/live_audio: the replay run ends at once (`replay_finished`), and the
/// live run hands over to the real test-energy worker.
fn spawn_ledger(dir: &Path) -> Child {
    fs::create_dir_all(dir.join("data")).unwrap();
    let assets = repo().join("tests/fixtures/live_audio");
    let manifest = dir.join("replay-manifest.json");
    let body = json!({
        "engine": "test-energy-detector",
        "test_only": true,
        "supported_phrases": {"hey_gideon": "HEY"},
        "active_phrase": "hey_gideon",
        "asset_root": assets.display().to_string(),
        "fixtures": [{"id": "fixture-0", "path": assets.join("manifest.json").display().to_string()}],
    });
    fs::write(&manifest, body.to_string()).unwrap();
    Command::new(env!("CARGO_BIN_EXE_gideon-base"))
        .arg("--root")
        .arg(dir.join("core"))
        .arg("--home")
        .arg(repo())
        .arg("--data-dir")
        .arg(dir.join("data"))
        .arg("--wake-replay")
        .arg(assets.join("fake_replay_worker.py"))
        .arg(&manifest)
        .arg("0")
        .env("PATH", fakes_path())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("spawn Core")
}

fn manifest_of(dir: &Path) -> String {
    dir.join("replay-manifest.json").display().to_string()
}

fn revision(root: &Path) -> u64 {
    snapshot(root)["preferences"]["revision"].as_u64().unwrap()
}

/// Waits for the Core process to exit and returns its status code (75 after an accepted core_restart).
fn exit_code(child: &mut Child) -> Option<i32> {
    let deadline = Instant::now() + Duration::from_secs(15);
    loop {
        if let Some(status) = child.try_wait().unwrap() {
            return status.code();
        }
        assert!(Instant::now() < deadline, "Core did not exit");
        thread::sleep(Duration::from_millis(20));
    }
}

#[test]
fn ledger_consent_starts_live_after_restart_and_the_boot_replay_stops() {
    let dir = std::env::temp_dir().join(format!("gideon-live-e-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    let root = dir.join("core");
    let manifest = manifest_of(&dir);
    let mut child = spawn_ledger(&dir);
    wait_ready(&root);

    // Consent off (the default): the boot replay runs as before and no live worker or recorder exists.
    let replayed = wait_snapshot(&root, 15, "boot replay finished", |s| {
        s["wake_status"] == "replay_finished"
    });
    assert_eq!(replayed["preferences"]["live_audio"], false);
    assert_eq!(replayed["audio"]["live"]["enabled"], false);
    assert_eq!(replayed["audio"]["live"]["restart_required"], false);
    assert!(pids_with_pair(&manifest, "--live").is_empty());
    assert_eq!(set_preferences(&root, "fake-tone-e1", 1.0)["code"], "ok");

    // Consent needs the client's confirmation: without it nothing changes.
    let refused = call(
        &root,
        json!({"op": "live_audio_preference", "revision": revision(&root), "enabled": true, "confirmed": false}),
    );
    assert_eq!(refused["code"], "consent_required");
    assert_eq!(snapshot(&root)["preferences"]["live_audio"], false);

    // Confirmed: the ledger records it, the event is content-free, and the running Core is unchanged.
    let granted = call(
        &root,
        json!({"op": "live_audio_preference", "revision": revision(&root), "enabled": true, "confirmed": true}),
    );
    assert_eq!(granted["code"], "ok");
    let pending = snapshot(&root);
    assert_eq!(pending["preferences"]["live_audio"], true);
    assert_eq!(pending["audio"]["live"]["restart_required"], true);
    assert_eq!(pending["audio"]["live"]["enabled"], false);
    assert!(pending["events"]
        .as_array()
        .unwrap()
        .iter()
        .any(|e| e["kind"] == "live_audio_enabled"));

    // A Core restart applies it: the same root starts the live pipeline with the chosen device and no replay.
    assert_eq!(call(&root, json!({"op": "core_restart"}))["code"], "ok");
    assert_eq!(exit_code(&mut child), Some(75));
    let mut child = spawn_ledger(&dir);
    wait_ready(&root);
    let live = wait_snapshot(&root, 20, "live mic after restart", |s| {
        s["audio"]["live"]["mic_active"] == true
    });
    assert_eq!(live["audio"]["live"]["enabled"], true);
    assert_eq!(live["audio"]["live"]["restart_required"], false);
    assert_ne!(live["wake_status"], "replay_finished");
    assert!(wait_pair("--target", "fake-tone-e1", 15), "recorder device");
    assert!(wait_pair(&manifest, "--live", 15), "live wake worker");

    // Withdrawing consent is applied the same way: the running Core asks for a restart, then replays again.
    assert_eq!(
        call(
            &root,
            json!({"op": "live_audio_preference", "revision": revision(&root), "enabled": false, "confirmed": false}),
        )["code"],
        "ok"
    );
    assert_eq!(snapshot(&root)["audio"]["live"]["restart_required"], true);
    assert_eq!(call(&root, json!({"op": "core_restart"}))["code"], "ok");
    assert_eq!(exit_code(&mut child), Some(75));
    let mut child = spawn_ledger(&dir);
    wait_ready(&root);
    wait_snapshot(&root, 15, "replay again after consent withdrawn", |s| {
        s["wake_status"] == "replay_finished"
    });
    let off = snapshot(&root);
    assert_eq!(off["audio"]["live"]["enabled"], false);
    assert_eq!(off["audio"]["live"]["mic_active"], false);
    assert_eq!(off["audio"]["live"]["restart_required"], false);
    assert!(pids_with_pair("--target", "fake-tone-e1").is_empty());
    kill_quietly(&mut child);
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn unreadable_ledger_keeps_the_microphone_off() {
    use std::os::unix::fs::{DirBuilderExt, PermissionsExt};
    let dir = std::env::temp_dir().join(format!("gideon-live-f-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    let root = dir.join("core");
    // A ledger that names the microphone and asks for live audio, but is invalid (version 2): safe mode.
    fs::DirBuilder::new()
        .mode(0o700)
        .recursive(true)
        .create(&root)
        .unwrap();
    let ledger = root.join("config.json");
    fs::write(
        &ledger,
        r#"{"version":2,"session_timeout_ms":30000,"audio_input_device":"fake-tone-f1","live_audio":true}"#,
    )
    .unwrap();
    fs::set_permissions(&ledger, fs::Permissions::from_mode(0o600)).unwrap();
    let mut child = spawn_ledger(&dir);
    wait_ready(&root);
    let snap = snapshot(&root);
    assert_eq!(snap["configuration_status"], "safe_mode");
    assert_eq!(snap["audio"]["live"]["enabled"], false);
    assert_eq!(snap["audio"]["live"]["restart_required"], false);
    thread::sleep(Duration::from_millis(500));
    assert!(pids_with_pair("--target", "fake-tone-f1").is_empty());
    assert!(pids_with_pair(&manifest_of(&dir), "--live").is_empty());
    kill_quietly(&mut child);
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn recorder_frames_reach_the_wake_detector_and_mic_follows_the_recorder() {
    let dir = std::env::temp_dir().join(format!("gideon-live-a-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("home")).unwrap();
    let root = dir.join("core");
    let mut child = spawn(&dir);
    wait_ready(&root);

    // The recorder runs from start-up; the test tone starts after 1 s of silence.
    let live = wait_snapshot(&root, 15, "mic active", |s| {
        s["audio"]["live"]["mic_active"] == true
    });
    assert_eq!(live["audio"]["live"]["enabled"], true);
    assert_eq!(live["audio"]["live"]["input_state"], "capturing");
    assert!(live["audio"]["live"].get("last_error").is_none());

    // A wake session can only start if the detector saw the tone in the recorder frames.
    let woke = wait_snapshot(&root, 20, "wake from recorder frames", |s| {
        s["events"]
            .as_array()
            .unwrap()
            .iter()
            .any(|e| e["kind"] == "session_started")
    });
    assert_eq!(woke["audio"]["live"]["mic_active"], true);
    kill_quietly(&mut child);
}

#[test]
fn device_and_sensitivity_changes_restart_the_pipeline_with_new_arguments() {
    let dir = std::env::temp_dir().join(format!("gideon-live-b-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("home")).unwrap();
    let root = dir.join("core");
    let mut child = spawn(&dir);
    wait_ready(&root);
    wait_snapshot(&root, 15, "mic active", |s| {
        s["audio"]["live"]["mic_active"] == true
    });
    assert_eq!(set_preferences(&root, "fake-tone-b1", 0.5)["code"], "ok");

    // Recorder argv carries the device preference; the worker argv carries the derived threshold
    // (0.5 sensitivity -> 0.375), so both reached their processes through the restart.
    assert!(wait_pair("--target", "fake-tone-b1", 15), "recorder target");
    assert!(
        wait_pair("--keywords-threshold", "0.3750", 15),
        "worker threshold"
    );
    let snap = wait_snapshot(&root, 15, "mic active after restart", |s| {
        s["audio"]["live"]["mic_active"] == true
    });
    assert_eq!(snap["preferences"]["wake_sensitivity"], 0.5);
    kill_quietly(&mut child);
}

#[test]
fn shutdown_kills_the_recorder() {
    let dir = std::env::temp_dir().join(format!("gideon-live-c-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("home")).unwrap();
    let root = dir.join("core");
    let mut child = spawn(&dir);
    wait_ready(&root);
    assert_eq!(set_preferences(&root, "fake-tone-c1", 1.0)["code"], "ok");
    assert!(
        wait_pair("--target", "fake-tone-c1", 15),
        "recorder running"
    );

    // SIGTERM is the Core's normal shutdown path; the live pipeline is aborted with its children.
    // SAFETY: plain kill(2) on a child pid this test owns.
    unsafe {
        libc::kill(child.id() as i32, libc::SIGTERM);
    }
    let deadline = Instant::now() + Duration::from_secs(15);
    while child.try_wait().unwrap().is_none() {
        assert!(Instant::now() < deadline, "Core did not exit");
        thread::sleep(Duration::from_millis(20));
    }
    let gone = Instant::now() + Duration::from_secs(10);
    while !pids_with_pair("--target", "fake-tone-c1").is_empty() {
        assert!(Instant::now() < gone, "recorder survived shutdown");
        thread::sleep(Duration::from_millis(50));
    }
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn restart_budget_stops_a_crashing_recorder() {
    let dir = std::env::temp_dir().join(format!("gideon-live-d-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("home")).unwrap();
    let root = dir.join("core");
    let mut child = spawn(&dir);
    wait_ready(&root);
    wait_snapshot(&root, 15, "mic active", |s| {
        s["audio"]["live"]["mic_active"] == true
    });
    let started = Instant::now();
    assert_eq!(set_preferences(&root, "fake-crash-d1", 1.0)["code"], "ok");
    // The recorder exits at once each time: the mic is never active, the error is reported and,
    // after 3 restarts inside the window, the budget stops the pipeline. A13: last_error is the cause
    // that kept failing (content-free reason), not the generic limit.
    let snap = wait_snapshot(&root, 30, "restart limit", |s| {
        s["wake_status"] == "failed" && s["audio"]["live"]["last_error"] == "recorder_exited"
    });
    assert_eq!(snap["audio"]["live"]["input_state"], "error");
    assert_eq!(snap["audio"]["live"]["mic_active"], false);
    assert_eq!(snap["wake_status"], "failed");
    // Backoff (200 ms, 400 ms, 800 ms) makes the give-up take measurable time, not a busy loop.
    assert!(started.elapsed() >= Duration::from_millis(1400));
    assert!(pids_with_pair("--target", "fake-crash-d1").is_empty());
    kill_quietly(&mut child);
    let _ = fs::remove_dir_all(&dir);
}

#[tokio::test(flavor = "current_thread")]
async fn player_delivers_exact_pcm_to_the_sandboxed_player() {
    let samples: Vec<f32> = (0..2400).map(|i| (i as f32 * 0.01).sin() * 0.5).collect();
    let bytes = live::pcm_s16le(&samples, 100);
    let digest = format!("{:x}", Sha256::digest(&bytes));
    let path = std::ffi::OsString::from(fakes_path());

    // The fake checks the sha256 of everything it received and exits 0 only on a match.
    let mut player = Player::start_in(&path, &format!("fake-sha-{digest}")).expect("player");
    let (first, rest) = bytes.split_at(bytes.len() / 2);
    player.write(first).await.expect("first half");
    player.write(rest).await.expect("second half");
    player.finish().await.expect("exact PCM accepted");

    // A wrong digest and a failing tool both surface as errors.
    let mut wrong = Player::start_in(&path, "fake-sha-00").expect("player");
    wrong.write(&bytes).await.expect("write");
    assert_eq!(wrong.finish().await, Err("player_failed"));
    let mut failing = Player::start_in(&path, "fake-fail-now").expect("player");
    let _ = failing.write(&bytes).await;
    assert_eq!(failing.finish().await, Err("player_failed"));
}
