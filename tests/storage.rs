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
