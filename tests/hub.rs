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

#[test]
fn approval_persists_exact_manifest_and_never_inherits_changed_catalog() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path().join("core");
    let storage = gideon_base::storage::Storage::open(&root).unwrap();
    let hub = load(FIXTURE.as_bytes()).unwrap().with_approvals(&storage);
    let entry = &hub.entries[0];
    assert_eq!(
        gideon_base::hub::approve(
            &storage,
            &hub,
            0,
            &entry.plugin_id,
            &entry.manifest_sha256,
            &entry.permissions,
            false
        ),
        Err("publisher_ack_required")
    );
    gideon_base::hub::approve(
        &storage,
        &hub,
        0,
        &entry.plugin_id,
        &entry.manifest_sha256,
        &entry.permissions,
        true,
    )
    .unwrap();
    drop(storage);
    let storage = gideon_base::storage::Storage::open(&root).unwrap();
    let current = load(FIXTURE.as_bytes()).unwrap().with_approvals(&storage);
    assert_eq!(current.approval_revision, 1);
    assert!(current.entries[0].permissions_approved);
    assert_eq!(current.entries[0].status, "not_installed");
    assert!(!current.publisher_verified);
    let mut changed: serde_json::Value = serde_json::from_str(FIXTURE).unwrap();
    changed["plugins"][0]["permissions"] = serde_json::json!(["network"]);
    let changed = load(&serde_json::to_vec(&changed).unwrap())
        .unwrap()
        .with_approvals(&storage);
    assert_ne!(
        current.entries[0].manifest_sha256,
        changed.entries[0].manifest_sha256
    );
    assert!(!changed.entries[0].permissions_approved);
    assert_eq!(changed.approval_revision, 1);
    assert!(!root.join("plugins").exists());
}
#[test]
fn failed_approval_write_preserves_existing_files_and_state() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path().join("core");
    let storage = gideon_base::storage::Storage::open(&root).unwrap();
    let hub = load(FIXTURE.as_bytes()).unwrap();
    let entry = &hub.entries[0];
    let sentinel = dir.path().join("sentinel");
    fs::write(&sentinel, b"untouched").unwrap();
    symlink(&sentinel, root.join(".hub-approvals.json.pending")).unwrap();
    assert_eq!(
        gideon_base::hub::approve(
            &storage,
            &hub,
            0,
            &entry.plugin_id,
            &entry.manifest_sha256,
            &entry.permissions,
            true
        ),
        Err("hub_storage_error")
    );
    assert_eq!(fs::read(&sentinel).unwrap(), b"untouched");
    assert!(!root.join("hub-approvals.json").exists());
    assert!(!hub.with_approvals(&storage).entries[0].permissions_approved);
}
#[test]
fn unsafe_or_invalid_approval_content_quarantines_only_hub() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path().join("core");
    let storage = gideon_base::storage::Storage::open(&root).unwrap();
    let path = root.join("hub-approvals.json");
    fs::write(&path, b"{}").unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
    assert_eq!(
        load(FIXTURE.as_bytes())
            .unwrap()
            .with_approvals(&storage)
            .status,
        "quarantined"
    );
    assert_eq!(
        storage.configuration_status,
        gideon_base::storage::ConfigurationStatus::Ready
    );
    fs::write(&path, b"{\"version\":1,\"revision\":0,\"records\":[]}").unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
    assert_eq!(
        load(FIXTURE.as_bytes())
            .unwrap()
            .with_approvals(&storage)
            .status,
        "quarantined"
    );
    fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
    fs::hard_link(&path, dir.path().join("alias")).unwrap();
    assert_eq!(
        load(FIXTURE.as_bytes())
            .unwrap()
            .with_approvals(&storage)
            .status,
        "quarantined"
    );
}
