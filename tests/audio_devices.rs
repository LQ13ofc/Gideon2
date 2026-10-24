//! A4 `audio_devices`: enumeration through fake `pactl` / `pw-dump` placed first on PATH
//! (tests/fixtures/fake_audio_tools), the 3 s budget and 64 KiB cap, and the wire shape through the
//! real Core operation. Monitors, unsafe names, label sanitization and the 16-device cap are covered.
use gideon_base::{
    core::Core,
    devices::{self, Devices},
    protocol::{Operation, Request},
};
use std::{ffi::OsStr, path::PathBuf, time::Instant};

fn fakes() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/fake_audio_tools")
}

/// PATH with the fake tool directory first, then the system directories.
fn path_with(dir: &str) -> String {
    format!("{}:/usr/bin:/bin", fakes().join(dir).display())
}

fn ids(list: &[devices::Device]) -> Vec<&str> {
    list.iter().map(|d| d.id.as_str()).collect()
}

#[test]
fn pactl_json_lists_inputs_outputs_defaults_and_sanitized_labels() {
    let path = format!("{}:/usr/bin:/bin", fakes().display());
    let found = devices::enumerate_in(OsStr::new(&path));
    assert_eq!(found.source, "pactl");
    assert_eq!(found.reason, None);
    // Monitors and names outside the preference charset are never offered.
    assert_eq!(
        ids(&found.inputs),
        ["alsa_input.pci-0000_00_1f.3.analog-stereo", "usb-mic.1"]
    );
    assert_eq!(found.inputs[0].label, "Mic _Built-in_ a____o");
    assert!(!found.inputs[0].default);
    assert!(found.inputs[1].default, "usb-mic.1 is the default source");
    assert_eq!(
        ids(&found.outputs),
        [
            "alsa_output.pci-0000_00_1f.3.analog-stereo",
            "bluez_output.AA_BB.1"
        ]
    );
    assert!(found.outputs[0].default);
    assert!(!found.outputs[1].default);
    assert_eq!(found.outputs[1].label, "Headset");
}

#[test]
fn pactl_without_json_falls_back_to_the_short_listing() {
    let found = devices::enumerate_in(OsStr::new(&path_with("variants/nojson")));
    assert_eq!(found.source, "pactl");
    assert_eq!(
        ids(&found.inputs),
        ["alsa_input.pci-0000_00_1f.3.analog-stereo", "usb-mic.1"]
    );
    // The short listing has no description: the label is the id, and the default still comes from info.
    assert_eq!(found.inputs[1].label, "usb-mic.1");
    assert!(found.inputs[1].default);
    assert_eq!(ids(&found.outputs).len(), 2);
}

#[test]
fn pw_dump_is_used_when_pactl_is_absent() {
    // Only the variant directory on PATH: the system pactl must not be found.
    let only = fakes().join("variants/pwdump");
    let found = devices::enumerate_in(only.as_os_str());
    assert_eq!(found.source, "pw-dump");
    assert_eq!(found.reason, None);
    assert_eq!(ids(&found.inputs), ["pw-mic.2"]);
    assert_eq!(ids(&found.outputs), ["pw-spk.1"]);
    assert_eq!(
        found.outputs[0].label, "Spk",
        "node.nick when no description"
    );
    assert!(found
        .inputs
        .iter()
        .chain(&found.outputs)
        .all(|d| !d.default));
}

#[test]
fn no_tool_gives_empty_lists_and_the_reason() {
    let found = devices::enumerate_in(OsStr::new("/nonexistent-gideon-audio-dir"));
    assert_eq!(
        found,
        Devices {
            inputs: vec![],
            outputs: vec![],
            source: "none",
            reason: Some("no_audio_tool"),
        }
    );
}

#[test]
fn a_tool_that_never_answers_is_cut_off_at_the_budget() {
    let started = Instant::now();
    let found = devices::enumerate_in(OsStr::new(&path_with("variants/hang")));
    let elapsed = started.elapsed();
    assert_eq!(found.source, "none");
    assert_eq!(found.reason, Some("audio_tool_failed"));
    assert!(
        elapsed < devices::BUDGET + std::time::Duration::from_secs(2),
        "{elapsed:?}"
    );
}

#[test]
fn oversized_output_is_refused() {
    let found = devices::enumerate_in(OsStr::new(&path_with("variants/big")));
    assert_eq!(found.source, "none");
    assert_eq!(found.reason, Some("audio_tool_failed"));
}

#[test]
fn the_wire_operation_is_strict_and_the_snapshot_carries_audio() {
    // Unknown fields are refused; the bare operation parses.
    let strict = r#"{"version":1,"request_id":"d0","op":"audio_devices","device":"x"}"#;
    assert!(serde_json::from_str::<Request>(strict).is_err());
    let bare = r#"{"version":1,"request_id":"d1","op":"audio_devices"}"#;
    let request = serde_json::from_str::<Request>(bare).expect("parses");
    assert!(matches!(request.operation, Operation::AudioDevices));

    // Through the real Core: reply ok, and the snapshot block exists with live state off by default.
    let mut core = Core::new(std::time::Duration::from_secs(10), false);
    let now = Instant::now();
    let reply = core.handle(request, now);
    assert_eq!(reply.code, "ok");
    let json = serde_json::to_value(&reply).unwrap();
    assert_eq!(json["audio"]["live"]["enabled"], false);
    assert_eq!(json["audio"]["live"]["mic_active"], false);
    assert_eq!(json["audio"]["live"]["input_state"], "idle");
    let devices = &json["audio"]["devices"];
    assert!(["pactl", "pw-dump", "none"].contains(&devices["source"].as_str().unwrap()));
    for side in ["inputs", "outputs"] {
        let list = devices[side].as_array().unwrap();
        assert!(list.len() <= devices::MAX_DEVICES);
        for item in list {
            assert!(gideon_base::storage::valid_audio_device(
                item["id"].as_str().unwrap()
            ));
            assert!(item["label"].as_str().unwrap().len() <= 128);
        }
    }
    // Before the op, the snapshot has no devices key at all.
    let before = Core::new(std::time::Duration::from_secs(10), false);
    let blank = serde_json::to_value(before.response("s".into(), "ok")).unwrap();
    assert!(blank["audio"].get("devices").is_none());
}
