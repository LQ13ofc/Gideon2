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
        session_timeout_ms: 100
    }
    .validate()
    .is_err());
    assert!(Config {
        version: 1,
        wake_phrase: None,
        session_timeout_ms: 0
    }
    .validate()
    .is_err());
}
