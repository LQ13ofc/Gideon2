//! A1-A3 through the real Core operation path: restore defaults, CAS, busy, validation, wire shape.
use gideon_base::{
    core::Core,
    protocol::{Operation, Request, Response},
    storage::Storage,
};
use std::{
    fs,
    os::unix::fs::PermissionsExt,
    time::{Duration, Instant},
};

fn request(id: &str, operation: Operation) -> Request {
    Request {
        version: 1,
        request_id: id.into(),
        operation,
    }
}

fn set_all(revision: u64, wake_sensitivity: Option<f32>, input: &str, output: &str) -> Operation {
    Operation::Preferences {
        revision,
        audible_feedback: false,
        session_timeout_ms: 9000,
        wake_sensitivity,
        audio_input_device: Some(input.into()),
        audio_output_device: Some(output.into()),
    }
}

fn open(root: &std::path::Path) -> (Storage, Core) {
    let storage = Storage::open(root).unwrap();
    let mut core = Core::new(Duration::from_secs(30), true);
    core.configure_storage(&storage);
    (storage, core)
}

#[test]
fn restore_defaults_is_cas_busy_guarded_backed_up_and_rollbackable() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    let (mut storage, mut core) = open(&root);
    let now = Instant::now();
    let set = core.handle_with_storage(
        request(
            "p1",
            set_all(0, Some(1.5), "alsa_input.usb-mic_1", "bt:headset@1+x"),
        ),
        now,
        Some(&mut storage),
    );
    assert_eq!(set.code, "ok");
    let before = fs::read(root.join("config.json")).unwrap();

    // Stale CAS is refused before anything else.
    let stale = core.handle_with_storage(
        request("r0", Operation::PreferencesRestoreDefaults { revision: 0 }),
        now,
        Some(&mut storage),
    );
    assert_eq!(stale.code, "stale_preferences");

    // A voice session owns the Core: restore is busy and touches nothing.
    assert_eq!(
        core.handle(request("w", Operation::VirtualWake), now)
            .session_id,
        Some(1)
    );
    let busy = core.handle_with_storage(
        request("rb", Operation::PreferencesRestoreDefaults { revision: 1 }),
        now,
        Some(&mut storage),
    );
    assert_eq!(busy.code, "busy");
    assert_eq!(fs::read(root.join("config.json")).unwrap(), before);
    assert!(!root.join("config.json.bak").exists());
    core.handle(request("c", Operation::Cancel { session_id: 1 }), now);

    let restored: Response = core.handle_with_storage(
        request("r", Operation::PreferencesRestoreDefaults { revision: 1 }),
        now,
        Some(&mut storage),
    );
    assert_eq!(restored.code, "ok");
    assert!(restored
        .events
        .iter()
        .any(|e| e.kind == "preferences_restored" && e.outcome == "ok"));
    // The event is content-free: no device names or values appear in the serialized event.
    let event = restored
        .events
        .iter()
        .find(|e| e.kind == "preferences_restored")
        .unwrap();
    let serialized = serde_json::to_string(event).unwrap();
    assert!(!serialized.contains("alsa_input") && !serialized.contains("headset"));

    // Backup holds the exact bytes replaced, 0600.
    assert_eq!(fs::read(root.join("config.json.bak")).unwrap(), before);
    assert_eq!(
        fs::metadata(root.join("config.json.bak"))
            .unwrap()
            .permissions()
            .mode()
            & 0o777,
        0o600
    );
    let p = &restored.preferences;
    assert_eq!(p.revision, 2);
    assert!(p.audible_feedback && p.visual_feedback);
    assert_eq!(p.session_timeout_ms, 30000);
    assert_eq!(p.output_volume_percent, 100);
    assert_eq!(p.wake_sensitivity, 1.0);
    assert_eq!(p.audio_input_device, "default");
    assert_eq!(p.audio_output_device, "default");
    assert!(p.wake_phrase.is_none());
    assert_eq!(
        p.previous_preferences.as_ref().unwrap().audio_input_device,
        "alsa_input.usb-mic_1"
    );

    // Persisted across restart, and the reset itself is rollbackable.
    drop(storage);
    let (mut storage, mut core) = open(&root);
    assert_eq!(storage.config.revision, 2);
    assert_eq!(storage.config.wake_sensitivity, 1.0);
    let rollback = core.handle_with_storage(
        request("rb2", Operation::RollbackPreferences { revision: 2 }),
        now,
        Some(&mut storage),
    );
    assert_eq!(rollback.code, "ok");
    assert_eq!(rollback.preferences.revision, 3);
    assert_eq!(rollback.preferences.wake_sensitivity, 1.5);
    assert_eq!(
        rollback.preferences.audio_input_device,
        "alsa_input.usb-mic_1"
    );
    assert_eq!(rollback.preferences.audio_output_device, "bt:headset@1+x");
    assert!(!rollback.preferences.audible_feedback);
}

#[test]
fn preferences_op_validates_new_fields_and_keeps_absent_fields() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    let (mut storage, mut core) = open(&root);
    let now = Instant::now();
    let mut revision = 0;
    // Each request needs a fresh id: the Core answers a replayed id with `duplicate`.
    let sequence = std::cell::Cell::new(0_u32);
    let run = |storage: &mut Storage, core: &mut Core, op: Operation| {
        sequence.set(sequence.get() + 1);
        let id = format!("x{}", sequence.get());
        core.handle_with_storage(request(&id, op), now, Some(storage))
    };

    // Out-of-range sensitivity and unsafe device names are refused without a revision change.
    for bad in [0.49_f32, 1.51, f32::NAN] {
        let r = run(
            &mut storage,
            &mut core,
            set_all(revision, Some(bad), "default", "default"),
        );
        assert_eq!(r.code, "invalid_preferences", "sensitivity {bad}");
    }
    let long = "a".repeat(129);
    let accent = "é".to_string();
    for bad in [
        "",
        "a;rm -rf",
        "x\ny",
        long.as_str(),
        accent.as_str(),
        "a,b",
    ] {
        let r = run(
            &mut storage,
            &mut core,
            set_all(revision, None, bad, "default"),
        );
        assert_eq!(r.code, "invalid_preferences", "input {bad:?}");
        let r = run(
            &mut storage,
            &mut core,
            set_all(revision, None, "default", bad),
        );
        assert_eq!(r.code, "invalid_preferences", "output {bad:?}");
    }
    assert_eq!(storage.config.revision, 0);

    // Boundary values are accepted: 0.5, 1.5, 128 bytes, the full charset.
    let max = "A".repeat(120) + "._:@/+ -";
    assert_eq!(max.len(), 128);
    let ok = run(
        &mut storage,
        &mut core,
        set_all(revision, Some(0.5), &max, "default"),
    );
    assert_eq!(ok.code, "ok");
    revision += 1;
    let ok = run(
        &mut storage,
        &mut core,
        set_all(revision, Some(1.5), "usb-mic_1", "hdmi:0"),
    );
    assert_eq!(ok.code, "ok");
    revision += 1;
    assert_eq!(ok.preferences.wake_sensitivity, 1.5);

    // Absent optional fields keep the stored values (old clients never reset them).
    let keep = run(
        &mut storage,
        &mut core,
        Operation::Preferences {
            revision,
            audible_feedback: true,
            session_timeout_ms: 30000,
            wake_sensitivity: None,
            audio_input_device: None,
            audio_output_device: None,
        },
    );
    assert_eq!(keep.code, "ok");
    assert_eq!(keep.preferences.wake_sensitivity, 1.5);
    assert_eq!(keep.preferences.audio_input_device, "usb-mic_1");
    assert_eq!(keep.preferences.audio_output_device, "hdmi:0");
    revision += 1;

    // Persisted: a restart reads the same values back.
    drop(storage);
    let (storage, _core) = open(&root);
    assert_eq!(storage.config.revision, revision);
    assert_eq!(storage.config.wake_sensitivity, 1.5);
    assert_eq!(storage.config.audio_input_device, "usb-mic_1");
    assert_eq!(storage.config.audio_output_device, "hdmi:0");
}

#[test]
fn legacy_preferences_wire_shape_still_parses_and_keeps_new_fields() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    let (mut storage, mut core) = open(&root);
    let now = Instant::now();
    let legacy: Request = serde_json::from_str(
        r#"{"version":1,"request_id":"legacy","op":"preferences","revision":0,"audible_feedback":false,"session_timeout_ms":9000}"#,
    )
    .unwrap();
    let r = core.handle_with_storage(legacy, now, Some(&mut storage));
    assert_eq!(r.code, "ok");
    assert_eq!(r.preferences.wake_sensitivity, 1.0);
    assert_eq!(r.preferences.audio_input_device, "default");

    // New keys parse on the same op; unknown keys are still rejected by the strict wire parser.
    let extended: Request = serde_json::from_str(
        r#"{"version":1,"request_id":"ext","op":"preferences","revision":1,"audible_feedback":false,"session_timeout_ms":9000,"wake_sensitivity":0.5,"audio_input_device":"default","audio_output_device":"default"}"#,
    )
    .unwrap();
    assert_eq!(
        core.handle_with_storage(extended, now, Some(&mut storage))
            .preferences
            .wake_sensitivity,
        0.5
    );
    assert!(serde_json::from_str::<Request>(
        r#"{"version":1,"request_id":"bad","op":"preferences_restore_defaults","revision":2,"force":true}"#,
    )
    .is_err());
    let restore: Request = serde_json::from_str(
        r#"{"version":1,"request_id":"rd","op":"preferences_restore_defaults","revision":2}"#,
    )
    .unwrap();
    let r = core.handle_with_storage(restore, now, Some(&mut storage));
    assert_eq!(r.code, "ok");
    assert_eq!(r.preferences.revision, 3);
    assert_eq!(r.preferences.wake_sensitivity, 1.0);
}

#[test]
fn restore_without_storage_is_unavailable_and_never_writes() {
    let now = Instant::now();
    let mut core = Core::new(Duration::from_secs(30), true);
    let r = core.handle(
        request("n", Operation::PreferencesRestoreDefaults { revision: 0 }),
        now,
    );
    assert_eq!(r.code, "preferences_unavailable");
}

#[test]
fn live_audio_consent_is_strict_off_by_default_and_rollback_keeps_it() {
    use gideon_base::{protocol::Request, storage::Config};
    // Default and missing field: consent is off.
    assert!(!Config::default().live_audio);
    let legacy = r#"{"version":1,"session_timeout_ms":30000}"#;
    assert!(!serde_json::from_str::<Config>(legacy).unwrap().live_audio);
    // Strict wire: a bool only, no extra fields, and `confirmed` is required.
    for bad in [
        r#"{"version":1,"request_id":"x","op":"live_audio_preference","revision":0,"enabled":"yes","confirmed":true}"#,
        r#"{"version":1,"request_id":"x","op":"live_audio_preference","revision":0,"enabled":true}"#,
        r#"{"version":1,"request_id":"x","op":"live_audio_preference","revision":0,"enabled":true,"confirmed":true,"device":"x"}"#,
    ] {
        assert!(serde_json::from_str::<Request>(bad).is_err(), "{bad}");
    }

    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    let (mut storage, mut core) = open(&root);
    let now = Instant::now();
    let grant = |revision: u64, enabled: bool, confirmed: bool| Operation::LiveAudioPreference {
        revision,
        enabled,
        confirmed,
    };
    // Turning on without the confirmation changes nothing.
    let refused = core.handle_with_storage(
        request("c0", grant(0, true, false)),
        now,
        Some(&mut storage),
    );
    assert_eq!(refused.code, "consent_required");
    assert!(!storage.config.live_audio);
    assert_eq!(storage.config.revision, 0);

    let granted =
        core.handle_with_storage(request("c1", grant(0, true, true)), now, Some(&mut storage));
    assert_eq!(granted.code, "ok");
    assert!(storage.config.live_audio);
    assert_eq!(storage.config.revision, 1);
    assert!(granted
        .events
        .iter()
        .any(|e| e.kind == "live_audio_enabled"));
    assert!(granted.preferences.live_audio);
    assert!(granted.audio.live.restart_required);
    assert!(!granted.audio.live.enabled);

    // Stale revision and same-value no-op.
    let stale = core.handle_with_storage(
        request("c2", grant(0, false, false)),
        now,
        Some(&mut storage),
    );
    assert_eq!(stale.code, "stale_preferences");
    let same = core.handle_with_storage(
        request("c3", grant(1, true, false)),
        now,
        Some(&mut storage),
    );
    assert_eq!(same.code, "ok");
    assert_eq!(storage.config.revision, 1);

    // Other preferences keep it; rollback keeps the current consent (an older record never re-grants it).
    let keep = core.handle_with_storage(
        request("c4", set_all(1, Some(1.2), "usb-mic.1", "default")),
        now,
        Some(&mut storage),
    );
    assert_eq!(keep.code, "ok");
    assert!(storage.config.live_audio);
    let rolled = core.handle_with_storage(
        request("c5", Operation::RollbackPreferences { revision: 2 }),
        now,
        Some(&mut storage),
    );
    assert_eq!(rolled.code, "ok");
    assert!(storage.config.live_audio);
    assert_eq!(storage.config.audio_input_device, "default");

    // Withdrawing needs no confirmation; restoring the Core defaults turns it off as well.
    let off = core.handle_with_storage(
        request("c6", grant(storage.config.revision, false, false)),
        now,
        Some(&mut storage),
    );
    assert_eq!(off.code, "ok");
    assert!(!storage.config.live_audio);
    assert!(off.events.iter().any(|e| e.kind == "live_audio_disabled"));
    let on_again = core.handle_with_storage(
        request("c7", grant(storage.config.revision, true, true)),
        now,
        Some(&mut storage),
    );
    assert_eq!(on_again.code, "ok");
    let restored = core.handle_with_storage(
        request(
            "c8",
            Operation::PreferencesRestoreDefaults {
                revision: storage.config.revision,
            },
        ),
        now,
        Some(&mut storage),
    );
    assert_eq!(restored.code, "ok");
    assert!(!storage.config.live_audio);
}

#[test]
fn languages_are_installed_only_cas_checked_and_rollback_refuses_uninstalled_previous() {
    use gideon_base::storage::Config;
    // An old ledger without language keys loads with English defaults.
    let legacy: Config =
        serde_json::from_str(r#"{"version":1,"session_timeout_ms":30000}"#).unwrap();
    assert_eq!(legacy.stt_languages, vec!["en".to_string()]);
    assert_eq!(legacy.tts_language, "en");
    assert_eq!(legacy.tts_voice, "alba");

    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    let (mut storage, mut core) = open(&root);
    let now = Instant::now();
    let language =
        |revision: u64, stt: &[&str], tts: &str, voice: &str| Operation::LanguagePreference {
            revision,
            stt_languages: stt.iter().map(|s| s.to_string()).collect(),
            tts_language: tts.into(),
            tts_voice: voice.into(),
        };
    // Not installed in this build: refused, nothing written.
    let refused = core.handle_with_storage(
        request("l0", language(0, &["fr"], "en", "alba")),
        now,
        Some(&mut storage),
    );
    assert_eq!(refused.code, "language_not_installed");
    assert_eq!(storage.config.revision, 0);
    let unknown = core.handle_with_storage(
        request("l1", language(0, &["de"], "en", "alba")),
        now,
        Some(&mut storage),
    );
    assert_eq!(unknown.code, "invalid_languages");
    let stale = core.handle_with_storage(
        request("l2", language(9, &["en"], "en", "alba")),
        now,
        Some(&mut storage),
    );
    assert_eq!(stale.code, "stale_preferences");
    // Same values: ok, and no revision is written.
    let same = core.handle_with_storage(
        request("l3", language(0, &["en"], "en", "alba")),
        now,
        Some(&mut storage),
    );
    assert_eq!(same.code, "ok");
    assert_eq!(storage.config.revision, 0);

    // A previous choice that is no longer installed cannot be restored by rollback.
    storage
        .update_languages(0, vec!["fr".into()], "en".into(), "alba".into())
        .unwrap();
    storage
        .update_languages(1, vec!["en".into()], "en".into(), "alba".into())
        .unwrap();
    core.configure_storage(&storage);
    let before = storage.config.clone();
    let rollback = core.handle_with_storage(
        request("l4", Operation::RollbackPreferences { revision: 2 }),
        now,
        Some(&mut storage),
    );
    assert_eq!(rollback.code, "language_not_installed");
    assert_eq!(storage.config, before);
    assert_eq!(rollback.languages.stt_selected, vec!["en".to_string()]);
    assert!(!rollback.languages.restart_required.stt);
}
