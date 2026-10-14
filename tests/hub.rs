use gideon_base::hub;
use sha2::{Digest, Sha256};
use std::{fs, os::unix::fs::symlink};
const FIXTURE: &str = include_str!("fixtures/hub.json");
fn load(bytes: &[u8]) -> std::io::Result<hub::Snapshot> {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("catalog.json");
    fs::write(&path, bytes).unwrap();
    hub::load(&path, &format!("{:x}", Sha256::digest(bytes)))
}
#[test]
fn actual_catalog_distinguishes_checksum_compatibility_and_authority() {
    let snap = load(FIXTURE.as_bytes()).unwrap();
    assert_eq!(snap.status, "verified");
    assert!(!snap.publisher_verified);
    assert_eq!(snap.entries[0].status, "not_installed");
    assert_eq!(snap.entries[1].reason, "api_version");
    assert_eq!(snap.entries[2].reason, "dependencies_unresolved");
    assert_eq!(snap.entries[0].permissions, ["notifications"]);
    assert!(!serde_json::to_string(&snap).unwrap().contains("entrypoint"));
}
#[test]
fn strict_metadata_rejects_traversal_secrets_and_ambiguous_contracts() {
    let source: serde_json::Value = serde_json::from_str(FIXTURE).unwrap();
    for (key, value) in [
        ("plugin_id", serde_json::json!("../outside")),
        ("semver", serde_json::json!("01.0.0")),
        ("publisher", serde_json::json!("unsafe\nline")),
        ("entrypoint", serde_json::json!("../escape")),
        ("entrypoint", serde_json::json!("/absolute")),
        ("entrypoint", serde_json::json!("bin\\escape")),
        ("entrypoint", serde_json::json!("bin//escape")),
        ("permissions", serde_json::json!(["notify", "notify"])),
        ("conflicts", serde_json::json!(["benign_fixture"])),
        (
            "dependencies",
            serde_json::json!([{"plugin_id":"benign_fixture","semver":"1.0.0"}]),
        ),
        (
            "build_source",
            serde_json::json!("https://github.com.evil.test/a/b"),
        ),
        ("signature", serde_json::json!("")),
        ("secret", serde_json::json!("never allowed")),
    ] {
        let mut changed = source.clone();
        changed["plugins"][0][key] = value;
        assert!(
            load(&serde_json::to_vec(&changed).unwrap()).is_err(),
            "{key}"
        );
    }
}
#[test]
fn binary_metadata_is_bounded_and_pinned_not_executed() {
    let source: serde_json::Value = serde_json::from_str(FIXTURE).unwrap();
    for (key, value) in [
        ("sha256", serde_json::json!("not a hash")),
        ("size", serde_json::json!(0)),
        ("size", serde_json::json!(67108865u64)),
        ("url", serde_json::json!("http://github.com/a/b")),
        ("url", serde_json::json!("https://github.com/a/../escape")),
        ("target", serde_json::json!("foreign")),
    ] {
        let mut changed = source.clone();
        changed["plugins"][0]["binaries"][0][key] = value;
        assert!(
            load(&serde_json::to_vec(&changed).unwrap()).is_err(),
            "{key}"
        );
    }
    let mut changed = source.clone();
    changed["plugins"][0]["targets"] = serde_json::json!(["windows_x86_64"]);
    changed["plugins"][0]["binaries"][0]["target"] = serde_json::json!("windows_x86_64");
    assert_eq!(
        load(&serde_json::to_vec(&changed).unwrap())
            .unwrap()
            .entries[0]
            .reason,
        "target"
    );
}
#[test]
fn file_hash_size_and_links_are_guarded() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("catalog");
    fs::write(&path, FIXTURE).unwrap();
    let digest = format!("{:x}", Sha256::digest(FIXTURE));
    assert!(hub::load(&path, &"0".repeat(64)).is_err());
    let alias = dir.path().join("alias");
    symlink(&path, &alias).unwrap();
    assert!(hub::load(&alias, &digest).is_err());
    assert!(hub::load(std::path::Path::new("relative"), &digest).is_err());
    assert!(hub::load(dir.path(), &digest).is_err());
    fs::write(&path, vec![b' '; 65537]).unwrap();
    assert!(hub::load(&path, &digest).is_err());
}
#[test]
fn catalog_duplicates_versions_and_limits_fail_closed() {
    let source: serde_json::Value = serde_json::from_str(FIXTURE).unwrap();
    let mut changed = source.clone();
    changed["version"] = serde_json::json!(2);
    assert!(load(&serde_json::to_vec(&changed).unwrap()).is_err());
    let mut changed = source.clone();
    changed["plugins"] = serde_json::json!(vec![source["plugins"][0].clone(); 9]);
    assert!(load(&serde_json::to_vec(&changed).unwrap()).is_err());
    let mut changed = source.clone();
    changed["plugins"][1] = changed["plugins"][0].clone();
    assert!(load(&serde_json::to_vec(&changed).unwrap()).is_err());
    assert!(load(b"{}").is_err());
    assert!(load(
        b"{\"version\":1,\"version\":1,\"repository\":\"https://github.com/a/b\",\"plugins\":[]}"
    )
    .is_err());
}
