//! A9 `audio_probe` and the input level block, with FAKE tools only: `pw-record` from
//! tests/fixtures/fake_audio_tools (inside the real bwrap sandbox, first on PATH). The fake writes
//! 1 s of silence and 1 s of a 440 Hz tone at -13.5 dBFS RMS, repeatedly; `--target fake-crash*`
//! exits at once. Nothing here is a microphone, so the verdicts prove the arithmetic and the wire
//! path only, not what a real device hears.
use gideon_base::{
    core::Core,
    levels,
    live::{self, LiveEvent},
    protocol::{Operation, Request},
};
use serde_json::Value;
use std::{
    ffi::OsStr,
    path::PathBuf,
    time::{Duration, Instant},
};

fn fakes_path() -> String {
    let fakes = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/fake_audio_tools");
    format!("{}:/usr/bin:/bin", fakes.display())
}

fn request(json: &str) -> Request {
    serde_json::from_str(json).expect("request parses")
}

#[tokio::test]
async fn probe_records_three_seconds_through_the_sandboxed_fake_and_judges_it() {
    let started = Instant::now();
    let outcome = live::probe_in(OsStr::new(&fakes_path()), "default").await;
    let elapsed = started.elapsed();
    assert!(
        elapsed >= Duration::from_millis(2_900) && elapsed < Duration::from_secs(8),
        "3 s budget: {elapsed:?}"
    );
    // 20 ms frames: about 150 in 3 s (generous lower bound for a loaded machine).
    assert!(outcome.summary.frames >= 60, "frames {:?}", outcome.summary);
    assert!(
        outcome.summary.peak_dbfs > -20.0,
        "tone peak: {:?}",
        outcome.summary
    );
    // Half the window is digital silence, so the floor sits at the bottom.
    assert_eq!(outcome.summary.floor_dbfs, levels::DBFS_MIN);
    assert_eq!(outcome.verdict.as_str(), "ok", "{outcome:?}");
    assert_eq!(outcome.reason, None);
}

#[tokio::test]
async fn probe_reports_a_recorder_that_exits_without_audio() {
    let outcome = live::probe_in(OsStr::new(&fakes_path()), "fake-crash-device").await;
    assert_eq!(outcome.verdict.as_str(), "error");
    assert_eq!(outcome.reason, Some("recorder_exited"));
    assert_eq!(outcome.summary.frames, 0);
}

#[tokio::test]
async fn probe_reports_a_missing_recorder_and_an_unsafe_device() {
    let missing = live::probe_in(OsStr::new("/nonexistent-gideon-probe-dir"), "default").await;
    assert_eq!(
        (missing.verdict.as_str(), missing.reason),
        ("error", Some("recorder_unavailable"))
    );
    let unsafe_device = live::probe_in(OsStr::new(&fakes_path()), "bad;name").await;
    assert_eq!(unsafe_device.reason, Some("invalid_device"));
}

#[test]
fn the_wire_operation_is_strict() {
    let ok = request(r#"{"version":1,"request_id":"p1","op":"audio_probe","device":"default"}"#);
    assert!(matches!(ok.operation, Operation::AudioProbe { ref device } if device == "default"));
    // Missing device and unknown fields are refused.
    assert!(serde_json::from_str::<Request>(
        r#"{"version":1,"request_id":"p2","op":"audio_probe"}"#
    )
    .is_err());
    assert!(serde_json::from_str::<Request>(
        r#"{"version":1,"request_id":"p3","op":"audio_probe","device":"default","extra":1}"#
    )
    .is_err());
}

#[test]
fn probe_is_refused_for_unlisted_devices_and_while_busy_then_served_by_the_snapshot() {
    let mut core = Core::new(Duration::from_secs(10), false);
    let now = Instant::now();
    // A device the last listing did not name is refused before any recording.
    let reply = core.handle(
        request(r#"{"version":1,"request_id":"p4","op":"audio_probe","device":"usb-mic.9"}"#),
        now,
    );
    assert_eq!(reply.code, "invalid_device");
    assert!(reply.audio.probe.is_none());

    // `default` is always allowed: the request is accepted and the snapshot shows it running.
    let reply = core.handle(
        request(r#"{"version":1,"request_id":"p5","op":"audio_probe","device":"default"}"#),
        now,
    );
    assert_eq!(reply.code, "ok");
    let json = serde_json::to_value(&reply).unwrap();
    assert_eq!(json["audio"]["probe"]["state"], "running");
    assert_eq!(json["audio"]["probe"]["device"], "default");
    assert!(json["audio"]["probe"].get("verdict").is_none());

    // A second request while one records is busy; the job is handed to the transport once.
    let busy = core.handle(
        request(r#"{"version":1,"request_id":"p6","op":"audio_probe","device":"default"}"#),
        now,
    );
    assert_eq!(busy.code, "busy");
    let (id, device) = core.take_audio_probe_job().expect("queued job");
    assert_eq!(device, "default");
    assert!(core.take_audio_probe_job().is_none());

    let outcome = live::ProbeOutcome::failed("recorder_unavailable");
    core.audio_probe_reply(id, outcome);
    let json = serde_json::to_value(core.response("p7".into(), "ok")).unwrap();
    let probe = &json["audio"]["probe"];
    assert_eq!(probe["state"], "done");
    assert_eq!(probe["verdict"], "error");
    assert_eq!(probe["reason"], "recorder_unavailable");
    assert_eq!(probe["frames"], 0);
    assert!(probe["hint"].as_str().unwrap().contains("pipewire-pulse"));
    // A finished probe frees the slot for the next one.
    let again = core.handle(
        request(r#"{"version":1,"request_id":"p8","op":"audio_probe","device":"default"}"#),
        now,
    );
    assert_eq!(again.code, "ok");
}

#[test]
fn live_level_block_is_numbers_only_and_silent_when_not_capturing() {
    let mut core = Core::new(Duration::from_secs(10), false);
    let json: Value = serde_json::to_value(core.response("l1".into(), "ok")).unwrap();
    let level = &json["audio"]["live"]["level"];
    assert_eq!(level["frames"], 0);
    assert_eq!(level["rms_dbfs"], -90.0);
    assert_eq!(level["speech_active"], false);
    assert_eq!(json["audio"]["live"]["silence_warning"], Value::Null);
    assert!(json["audio"]["live"].get("last_detection").is_none());

    // Frames while the recorder is "capturing": counted, the level follows, and the age is reported.
    core.live_event(LiveEvent::Input {
        state: "capturing",
        error: None,
    });
    let tone = {
        let mut pcm = Vec::new();
        for i in 0..320 {
            let v = ((i as f32 / 320.0 * std::f32::consts::TAU).sin() * 0.3 * 32767.0) as i16;
            pcm.extend_from_slice(&v.to_le_bytes());
        }
        levels::frame_stats(&pcm)
    };
    let t0 = Instant::now();
    for i in 0..30u32 {
        core.live_event(LiveEvent::Frame {
            stats: tone,
            at: t0 + Duration::from_millis(u64::from(i) * 20),
        });
    }
    core.live_detected("hey_gideon");
    let json: Value = serde_json::to_value(core.response("l2".into(), "ok")).unwrap();
    let live = &json["audio"]["live"];
    assert_eq!(live["mic_active"], true);
    // The level block is published at most every 200 ms, so 600 ms of frames shows a count that lags by up to 200 ms.
    let frames = live["level"]["frames"].as_u64().unwrap();
    assert!((20..=30).contains(&frames), "published count {frames}");
    let rms = live["level"]["rms_dbfs"].as_f64().unwrap();
    assert!((-14.0..-11.0).contains(&rms), "sine at 0.3 peak: {rms}");
    assert_eq!(live["last_detection"]["phrase_id"], "hey_gideon");
    assert!(live["last_detection"]["at_ms"].as_u64().unwrap() > 0);
    // Only numbers and flags in the level block: no sample data can hide there.
    let keys: Vec<&str> = live["level"]
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    for key in keys {
        assert!(
            [
                "rms_dbfs",
                "peak_dbfs",
                "floor_dbfs",
                "speech_active",
                "speech_ms",
                "speech_unmatched",
                "frames",
                "last_frame_age_ms",
                "clipping"
            ]
            .contains(&key),
            "unexpected key {key}"
        );
    }
    // A stopped recorder reads silent again.
    core.live_event(LiveEvent::Input {
        state: "idle",
        error: None,
    });
    let json: Value = serde_json::to_value(core.response("l3".into(), "ok")).unwrap();
    assert_eq!(json["audio"]["live"]["level"]["frames"], 0);
    assert_eq!(json["audio"]["live"]["silence_warning"], Value::Null);
}
