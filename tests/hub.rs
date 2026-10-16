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

fn approved_import() -> (
    tempfile::TempDir,
    gideon_base::storage::Storage,
    hub::Snapshot,
) {
    let dir = tempfile::tempdir().unwrap();
    let storage = gideon_base::storage::Storage::open(&dir.path().join("core")).unwrap();
    let snap = load(FIXTURE.as_bytes()).unwrap();
    let e = &snap.entries[0];
    hub::approve(
        &storage,
        &snap,
        0,
        &e.plugin_id,
        &e.manifest_sha256,
        &e.permissions,
        true,
    )
    .unwrap();
    let snap = snap.with_approvals(&storage);
    (dir, storage, snap)
}
fn begin(storage: &mut gideon_base::storage::Storage, snap: &hub::Snapshot, id: &str) {
    let e = &snap.entries[0];
    hub::begin_import(
        storage,
        snap,
        snap.approval_revision,
        &e.plugin_id,
        &e.manifest_sha256,
        id,
        std::time::Instant::now(),
    )
    .unwrap();
}
const PAYLOAD_HEX: &str = "62656e69676e20666978747572650a";
#[test]
fn actual_payload_is_verified_private_atomic_and_restartable() {
    let (dir, mut storage, snap) = approved_import();
    begin(&mut storage, &snap, "upload");
    assert_eq!(
        hub::chunk_import(&mut storage, "upload", 1, PAYLOAD_HEX),
        Err("stale_import_offset")
    );
    assert_eq!(
        hub::chunk_import(&mut storage, "upload", 0, "XX"),
        Err("invalid_import_chunk")
    );
    hub::chunk_import(&mut storage, "upload", 0, PAYLOAD_HEX).unwrap();
    hub::finish_import(&mut storage, &snap, "upload").unwrap();
    let present = snap.clone().with_approvals(&storage);
    assert!(present.entries[0].payload_staged);
    assert_eq!(present.entries[0].status, "not_installed");
    let path = storage
        .root
        .join(format!("hub-{}.payload", snap.entries[0].manifest_sha256));
    use std::os::unix::fs::{MetadataExt, PermissionsExt};
    assert_eq!(fs::read(&path).unwrap(), b"benign fixture\n");
    assert_eq!(
        fs::metadata(&path).unwrap().permissions().mode() & 0o777,
        0o600
    );
    assert_eq!(fs::metadata(&path).unwrap().nlink(), 1);
    drop(storage);
    let storage = gideon_base::storage::Storage::open(&dir.path().join("core")).unwrap();
    assert!(snap.with_approvals(&storage).entries[0].payload_staged);
}
#[test]
fn import_failures_cancel_timeout_and_shutdown_remove_only_owned_pending() {
    let (_dir, mut storage, snap) = approved_import();
    let pending = storage
        .root
        .join(format!(".hub-{}.pending", snap.entries[0].manifest_sha256));
    begin(&mut storage, &snap, "first");
    assert_eq!(
        hub::chunk_import(&mut storage, "wrong", 0, PAYLOAD_HEX),
        Err("stale_import")
    );
    assert_eq!(
        hub::finish_import(&mut storage, &snap, "first"),
        Err("payload_size_mismatch")
    );
    assert!(!pending.exists());
    begin(&mut storage, &snap, "hash");
    hub::chunk_import(&mut storage, "hash", 0, &"00".repeat(15)).unwrap();
    assert_eq!(
        hub::finish_import(&mut storage, &snap, "hash"),
        Err("payload_hash_mismatch")
    );
    assert!(!pending.exists());
    begin(&mut storage, &snap, "cancel");
    hub::abort_import(&mut storage, "cancel").unwrap();
    assert!(!pending.exists());
    begin(&mut storage, &snap, "timeout");
    assert!(hub::expire_import(
        &mut storage,
        std::time::Instant::now() + std::time::Duration::from_secs(121)
    ));
    assert!(!pending.exists());
    begin(&mut storage, &snap, "shutdown");
    drop(storage);
    assert!(!pending.exists());
}
#[test]
fn import_guard_preserves_foreign_pending_and_existing_payload() {
    let (_dir, mut storage, snap) = approved_import();
    let e = &snap.entries[0];
    let pending = storage
        .root
        .join(format!(".hub-{}.pending", e.manifest_sha256));
    let sentinel = storage.root.join("sentinel");
    fs::write(&sentinel, b"preserved").unwrap();
    symlink(&sentinel, &pending).unwrap();
    assert_eq!(
        hub::begin_import(
            &mut storage,
            &snap,
            1,
            &e.plugin_id,
            &e.manifest_sha256,
            "bad",
            std::time::Instant::now()
        ),
        Err("hub_storage_error")
    );
    assert_eq!(fs::read(&sentinel).unwrap(), b"preserved");
    fs::remove_file(&pending).unwrap();
    begin(&mut storage, &snap, "replacement");
    fs::remove_file(&pending).unwrap();
    fs::write(&pending, b"foreign").unwrap();
    hub::abort_import(&mut storage, "replacement").unwrap();
    assert_eq!(fs::read(&pending).unwrap(), b"foreign");
    fs::remove_file(&pending).unwrap();
    begin(&mut storage, &snap, "clobber");
    hub::chunk_import(&mut storage, "clobber", 0, PAYLOAD_HEX).unwrap();
    let destination = storage
        .root
        .join(format!("hub-{}.payload", e.manifest_sha256));
    fs::write(&destination, b"foreign").unwrap();
    assert!(hub::finish_import(&mut storage, &snap, "clobber").is_err());
    assert_eq!(fs::read(&destination).unwrap(), b"foreign");
    assert!(!pending.exists());
}
#[test]
fn import_rechecks_approval_and_descriptor_bytes_before_publish() {
    let (_dir, mut storage, snap) = approved_import();
    let e = &snap.entries[0];
    let pending = storage
        .root
        .join(format!(".hub-{}.pending", e.manifest_sha256));
    begin(&mut storage, &snap, "tamper");
    hub::chunk_import(&mut storage, "tamper", 0, PAYLOAD_HEX).unwrap();
    fs::write(&pending, b"corrupt bytes!\n!").unwrap();
    assert!(hub::finish_import(&mut storage, &snap, "tamper").is_err());
    assert!(!pending.exists());
    begin(&mut storage, &snap, "revoked");
    hub::chunk_import(&mut storage, "revoked", 0, PAYLOAD_HEX).unwrap();
    fs::write(
        storage.root.join("hub-approvals.json"),
        br#"{"version":1,"revision":2,"records":[]}"#,
    )
    .unwrap();
    assert_eq!(
        hub::finish_import(&mut storage, &snap, "revoked"),
        Err("permissions_not_approved")
    );
    assert!(!pending.exists());
}

#[test]
fn real_core_can_cancel_import_when_configuration_requires_restart() {
    use gideon_base::{
        core::Core,
        protocol::{Operation, Request, VERSION},
        storage::ConfigurationStatus,
    };
    let (_dir, mut storage, snap) = approved_import();
    let mut core = Core::new(std::time::Duration::from_secs(10), false);
    core.configure_storage(&storage);
    core.configure_hub(snap.clone());
    let entry = &snap.entries[0];
    let started = core.handle_with_storage(
        Request {
            version: VERSION,
            request_id: "begin".into(),
            operation: Operation::HubBegin {
                revision: 1,
                plugin_id: entry.plugin_id.clone(),
                manifest_sha256: entry.manifest_sha256.clone(),
            },
        },
        std::time::Instant::now(),
        Some(&mut storage),
    );
    assert_eq!(started.code, "ok");
    let id = started.hub.unwrap().import.unwrap().import_id;
    storage.configuration_status = ConfigurationStatus::RestartRequired;
    core.configure_storage(&storage);
    let cancelled = core.handle_with_storage(
        Request {
            version: VERSION,
            request_id: "cancel".into(),
            operation: Operation::HubAbort { import_id: id },
        },
        std::time::Instant::now(),
        Some(&mut storage),
    );
    assert_eq!(cancelled.code, "ok");
    assert!(cancelled.hub.unwrap().import.is_none());
    assert!(!storage
        .root
        .join(format!(".hub-{}.pending", entry.manifest_sha256))
        .exists());
}
