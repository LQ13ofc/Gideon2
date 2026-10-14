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
    assert!(store.update_preferences(1702, false, 9000).is_err());
    drop(store);
    let store = Storage::open_for_runtime(&root).unwrap();
    assert_eq!(store.configuration_status, ConfigurationStatus::Ready);
    assert_eq!(store.config.revision, 1702);
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
