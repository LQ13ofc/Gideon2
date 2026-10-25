use gideon_base::storage::{Config, Storage};
use std::{
    fs,
    os::unix::fs::{symlink, PermissionsExt},
};
#[test]
fn storage_lock_permissions_and_corruption() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("private");
    let store = Storage::open(&root).unwrap();
    assert!(Storage::open(&root).is_err());
    assert_eq!(
        fs::metadata(&root).unwrap().permissions().mode() & 0o777,
        0o700
    );
    store.audit(1).unwrap();
    assert!(!fs::read_to_string(root.join("audit.log"))
        .unwrap()
        .contains("request_id"));
    drop(store);
    fs::write(root.join("config.json"), "broken").unwrap();
    assert!(Storage::open(&root).is_err());
    assert_eq!(
        fs::read_to_string(root.join("config.json")).unwrap(),
        "broken"
    );
}
#[test]
fn rejects_unsafe_root_and_config_symlinks() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    fs::create_dir(&root).unwrap();
    fs::set_permissions(&root, fs::Permissions::from_mode(0o755)).unwrap();
    assert!(Storage::open(&root).is_err());
    fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
    let secret = temp.path().join("sentinel");
    fs::write(&secret, "private").unwrap();
    symlink(&secret, root.join("config.json")).unwrap();
    assert!(Storage::open(&root).is_err());
    assert_eq!(fs::read_to_string(secret).unwrap(), "private");
}
#[test]
fn bounded_logging_and_config_validation() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    let store = Storage::open(&root).unwrap();
    for n in 0..10000 {
        store.audit(n).unwrap();
    }
    assert!(fs::metadata(root.join("audit.log")).unwrap().len() <= 65580);
    // Rotation keeps one private previous generation instead of truncating in place.
    assert_eq!(
        fs::metadata(root.join("audit.log.1"))
            .unwrap()
            .permissions()
            .mode()
            & 0o777,
        0o600
    );
    assert!(Config {
        version: 2,
        wake_phrase: None,
        session_timeout_ms: 100,
        ..Default::default()
    }
    .validate()
    .is_err());
    assert!(Config {
        version: 1,
        wake_phrase: None,
        session_timeout_ms: 0,
        ..Default::default()
    }
    .validate()
    .is_err());
}

#[test]
fn private_hardlinks_are_rejected_without_modifying_the_other_file() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    let store = Storage::open(&root).unwrap();
    let sentinel = temp.path().join("sentinel");
    let data = vec![b'x'; 70000];
    fs::write(&sentinel, &data).unwrap();
    fs::set_permissions(&sentinel, fs::Permissions::from_mode(0o600)).unwrap();
    fs::hard_link(&sentinel, root.join("audit.log")).unwrap();
    assert!(store.audit(1).is_err());
    assert_eq!(fs::read(&sentinel).unwrap(), data);
    drop(store);
    fs::remove_file(root.join("core.lock")).unwrap();
    fs::hard_link(&sentinel, root.join("core.lock")).unwrap();
    assert!(Storage::open(&root).is_err());
    assert_eq!(fs::read(&sentinel).unwrap(), data);
}

#[test]
fn atomic_preferences_restart_rollback_and_failed_update() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    let mut store = Storage::open(&root).unwrap();
    assert!(store.update_preferences(0, false, 0).is_err());
    assert!(store.config.previous_preferences.is_none());
    store.update_preferences(0, false, 9000).unwrap();
    assert!(store.update_preferences(0, true, 10000).is_err());
    drop(store);
    let mut store = Storage::open(&root).unwrap();
    assert!(!store.config.audible_feedback);
    assert_eq!(store.config.revision, 1);
    store.rollback_preferences(1).unwrap();
    assert!(store.config.audible_feedback);
    assert_eq!(store.config.session_timeout_ms, 30000);
    assert_eq!(store.config.revision, 2);
    let before = fs::read(root.join("config.json")).unwrap();
    let sentinel = temp.path().join("sentinel");
    fs::write(&sentinel, "unchanged").unwrap();
    symlink(&sentinel, root.join(".config.json.pending")).unwrap();
    assert!(store.update_preferences(2, false, 10000).is_err());
    assert_eq!(fs::read(root.join("config.json")).unwrap(), before);
    assert_eq!(fs::read_to_string(sentinel).unwrap(), "unchanged");
    assert_eq!(store.config.revision, 2);
    fs::remove_file(root.join(".config.json.pending")).unwrap();
    store.rollback_preferences(2).unwrap();
    assert!(!store.config.audible_feedback);
    assert_eq!(store.config.session_timeout_ms, 9000);
    assert_eq!(store.config.revision, 3);
}

#[test]
fn safe_mode_preserves_invalid_bytes_and_requires_restart_after_recovery() {
    use gideon_base::storage::ConfigurationStatus;
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    drop(Storage::open(&root).unwrap());
    let bytes = b"{broken private marker}";
    fs::write(root.join("config.json"), bytes).unwrap();
    let mut store = Storage::open_for_runtime(&root).unwrap();
    assert_eq!(store.configuration_status, ConfigurationStatus::SafeMode);
    store.set_safe_epoch(1701);
    assert!(store.update_preferences(1701, false, 9000).is_err());
    assert!(store.recover_configuration(0).is_err());
    fs::write(root.join("config.json"), b"changed").unwrap();
    assert!(store.recover_configuration(1701).is_err());
    fs::write(root.join("config.json"), bytes).unwrap();
    store.recover_configuration(1701).unwrap();
    assert_eq!(fs::read(root.join("config.invalid.json")).unwrap(), bytes);
    assert_eq!(
        store.configuration_status,
        ConfigurationStatus::RestartRequired
    );
    assert_eq!(store.config.revision, 1702);
    assert!(!store.recovery_available());
    // A13/U1: the restart is still required, but preference writes are accepted while it is pending (latest wins).
    store.update_preferences(1702, false, 9000).unwrap();
    assert_eq!(store.config.revision, 1703);
    assert_eq!(
        store.configuration_status,
        ConfigurationStatus::RestartRequired
    );
    drop(store);
    let store = Storage::open_for_runtime(&root).unwrap();
    assert_eq!(store.configuration_status, ConfigurationStatus::Ready);
    assert_eq!(store.config.revision, 1703);
}

#[test]
fn safe_mode_never_weakens_file_guards_or_recovers_oversized_content() {
    use gideon_base::storage::ConfigurationStatus;
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    drop(Storage::open(&root).unwrap());
    fs::write(root.join("config.json"), vec![b'x'; 4097]).unwrap();
    let mut store = Storage::open_for_runtime(&root).unwrap();
    assert_eq!(store.configuration_status, ConfigurationStatus::SafeMode);
    assert!(!store.recovery_available());
    assert!(store.recover_configuration(0).is_err());
    drop(store);
    fs::set_permissions(root.join("config.json"), fs::Permissions::from_mode(0o644)).unwrap();
    assert!(Storage::open_for_runtime(&root).is_err());
    fs::remove_file(root.join("config.json")).unwrap();
    let sentinel = temp.path().join("sentinel");
    fs::write(&sentinel, "unchanged").unwrap();
    fs::set_permissions(&sentinel, fs::Permissions::from_mode(0o600)).unwrap();
    fs::hard_link(&sentinel, root.join("config.json")).unwrap();
    assert!(Storage::open_for_runtime(&root).is_err());
    assert_eq!(fs::read_to_string(sentinel).unwrap(), "unchanged");
}

#[test]
fn feedback_preferences_are_bounded_atomic_and_survive_restart_rollback() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    let mut store = Storage::open(&root).unwrap();
    assert!(store.update_feedback(0, false, 101).is_err());
    store.update_feedback(0, false, 50).unwrap();
    drop(store);
    let mut store = Storage::open(&root).unwrap();
    assert!(!store.config.visual_feedback);
    assert_eq!(store.config.output_volume_percent, 50);
    store.rollback_preferences(1).unwrap();
    assert!(store.config.visual_feedback);
    assert_eq!(store.config.output_volume_percent, 100);
    assert_eq!(store.config.revision, 2);
}

#[test]
fn startup_sweep_quarantines_leftovers_and_orphans_without_deleting() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    drop(Storage::open(&root).unwrap());
    let leftover = root.join(".hub-deadbeef.pending");
    fs::write(&leftover, b"partial").unwrap();
    fs::set_permissions(&leftover, fs::Permissions::from_mode(0o600)).unwrap();
    let namespace = root.join("hub-plugins");
    {
        use std::os::unix::fs::DirBuilderExt;
        fs::DirBuilder::new()
            .mode(0o700)
            .create(&namespace)
            .unwrap();
    }
    let orphan = namespace.join("ghost-0000.payload");
    fs::write(&orphan, b"orphan").unwrap();
    fs::set_permissions(&orphan, fs::Permissions::from_mode(0o600)).unwrap();
    // Held for the lock; the sweep ran inside open().
    let _store = Storage::open(&root).unwrap();
    assert!(!leftover.exists() && !orphan.exists());
    let mut names: Vec<String> = fs::read_dir(root.join("quarantine"))
        .unwrap()
        .map(|e| e.unwrap().file_name().to_string_lossy().into_owned())
        .collect();
    names.sort();
    assert_eq!(names.len(), 2, "{names:?}");
    assert!(names
        .iter()
        .any(|n| n.starts_with(".hub-deadbeef.pending.")));
    assert!(names.iter().any(|n| n.starts_with("ghost-0000.payload.")));
    assert_eq!(
        fs::metadata(root.join("quarantine"))
            .unwrap()
            .permissions()
            .mode()
            & 0o777,
        0o700
    );
}

#[test]
fn input_conditioning_defaults_to_auto_is_strict_and_rolls_back() {
    use gideon_base::storage::{InputConditioning, OptionalPreferences};
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    let mut store = Storage::open(&root).unwrap();
    assert_eq!(store.config.input_conditioning, InputConditioning::Auto);
    store
        .update_preferences_with(
            0,
            false,
            9000,
            OptionalPreferences {
                input_conditioning: Some(InputConditioning::Off),
                ..Default::default()
            },
        )
        .unwrap();
    assert_eq!(store.config.input_conditioning, InputConditioning::Off);
    // The preference is saved as the snake_case word and the rollback target keeps the previous value.
    let saved = std::fs::read_to_string(root.join("config.json")).unwrap();
    let saved: serde_json::Value = serde_json::from_str(&saved).unwrap();
    assert_eq!(saved["input_conditioning"], "off");
    assert_eq!(
        store
            .config
            .previous_preferences
            .as_ref()
            .unwrap()
            .input_conditioning,
        InputConditioning::Auto
    );
    store.rollback_preferences(1).unwrap();
    assert_eq!(store.config.input_conditioning, InputConditioning::Auto);
    // Strict word: any other value is refused by the parser (no silent fallback to auto).
    assert!(serde_json::from_str::<InputConditioning>("\"maybe\"").is_err());
    assert_eq!(
        serde_json::from_str::<InputConditioning>("\"off\"").unwrap(),
        InputConditioning::Off
    );
}

#[test]
fn legacy_ledgers_load_with_wake_sensitivity_and_device_defaults() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    drop(Storage::open(&root).unwrap());
    // A ledger written before A1-A3: no wake_sensitivity, no device names, legacy previous block.
    fs::write(
        root.join("config.json"),
        br#"{"version":1,"session_timeout_ms":9000,"revision":4,"audible_feedback":false,"visual_feedback":true,"output_volume_percent":80,"previous_preferences":{"audible_feedback":true,"session_timeout_ms":30000}}"#,
    )
    .unwrap();
    fs::set_permissions(root.join("config.json"), fs::Permissions::from_mode(0o600)).unwrap();
    let store = Storage::open(&root).unwrap();
    assert_eq!(
        store.configuration_status,
        gideon_base::storage::ConfigurationStatus::Ready
    );
    assert_eq!(store.config.revision, 4);
    assert_eq!(store.config.wake_sensitivity, 1.0);
    assert_eq!(store.config.audio_input_device, "default");
    assert_eq!(store.config.audio_output_device, "default");
    let previous = store.config.previous_preferences.as_ref().unwrap();
    assert_eq!(previous.wake_sensitivity, 1.0);
    assert_eq!(previous.audio_output_device, "default");
}

#[test]
fn wake_sensitivity_and_device_bounds_are_strict() {
    use gideon_base::storage::{valid_audio_device, valid_wake_sensitivity};
    for ok in [0.5_f32, 1.0, 1.5] {
        assert!(valid_wake_sensitivity(ok));
    }
    for bad in [0.4999_f32, 1.5001, -1.0, f32::NAN, f32::INFINITY] {
        assert!(!valid_wake_sensitivity(bad));
    }
    for ok in [
        "default",
        "alsa_input.usb-Logitech_C920-00.analog-stereo",
        "bluez_output.AA:BB:CC+dd/x",
        "Built In Audio",
        &"x".repeat(128),
    ] {
        assert!(valid_audio_device(ok), "{ok}");
    }
    for bad in [
        "",
        &"x".repeat(129),
        "a;b",
        "$(id)",
        "tab\tname",
        "é",
        "a,b",
        "a\0",
    ] {
        assert!(!valid_audio_device(bad), "{bad:?}");
    }
    // The same bounds apply on load: a hand-edited bad device makes the ledger invalid (safe mode).
    let config = Config {
        audio_input_device: "a;b".into(),
        ..Default::default()
    };
    assert!(config.validate().is_err());
    let config = Config {
        wake_sensitivity: 1.6,
        ..Default::default()
    };
    assert!(config.validate().is_err());
}

#[test]
fn restore_defaults_refuses_stale_revision_and_keeps_one_backup_generation() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    let mut store = Storage::open(&root).unwrap();
    store
        .update_preferences_with(
            0,
            false,
            9000,
            gideon_base::storage::OptionalPreferences {
                wake_sensitivity: Some(0.5),
                input_conditioning: None,
                audio_input_device: Some("mic-a".into()),
                audio_output_device: None,
            },
        )
        .unwrap();
    assert!(store.restore_preferences_defaults(0).is_err());
    assert_eq!(store.config.revision, 1);
    store.restore_preferences_defaults(1).unwrap();
    assert_eq!(store.config.revision, 2);
    assert_eq!(store.config.wake_sensitivity, 1.0);
    let first = fs::read(root.join("config.json.bak")).unwrap();
    // A second restore replaces the single backup generation with the newer pre-reset bytes.
    store
        .update_preferences_with(
            2,
            true,
            9000,
            gideon_base::storage::OptionalPreferences {
                wake_sensitivity: Some(1.5),
                ..Default::default()
            },
        )
        .unwrap();
    let newer = fs::read(root.join("config.json")).unwrap();
    store.restore_preferences_defaults(3).unwrap();
    assert_eq!(fs::read(root.join("config.json.bak")).unwrap(), newer);
    assert_ne!(first, newer);
    assert_eq!(
        fs::metadata(root.join("config.json.bak"))
            .unwrap()
            .permissions()
            .mode()
            & 0o777,
        0o600
    );
    assert!(!root.join(".config.json.bak.pending").exists());
}
