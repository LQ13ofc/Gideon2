use gideon_base::hub;
use ring::signature::{Ed25519KeyPair, KeyPair};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{fs, os::unix::fs::symlink};

const PUBLISHER: &str = "Gideon local test fixture";

fn key(seed: u8) -> Ed25519KeyPair {
    Ed25519KeyPair::from_seed_unchecked(&[seed; 32]).unwrap()
}

fn hex(bytes: &[u8]) -> String {
    bytes
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<Vec<_>>()
        .concat()
}

fn pinned(kp: &Ed25519KeyPair, key_id: &str, publisher: &str) -> hub::PublisherKey {
    hub::PublisherKey {
        key_id: key_id.to_owned(),
        publisher: publisher.to_owned(),
        public_key_hex: hex(kp.public_key().as_ref()),
    }
}

/// The signing message, written from the spec: SHA-256 of the compact sorted-key JSON of the
/// plugin with `signature` set to null.
fn signing_message(plugin: &Value) -> String {
    let mut unsigned = plugin.clone();
    unsigned["signature"] = Value::Null;
    format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&unsigned).unwrap())
    )
}

/// Signs every plugin of the fixture with `kp` under `key_id`.
fn sign_all(kp: &Ed25519KeyPair, key_id: &str) -> Value {
    let mut source: Value = serde_json::from_str(FIXTURE).unwrap();
    for index in 0..source["plugins"].as_array().unwrap().len() {
        let message = signing_message(&source["plugins"][index]);
        source["plugins"][index]["signature"] = json!({
            "key_id": key_id,
            "algorithm": "ed25519",
            "signature": hex(kp.sign(message.as_bytes()).as_ref()),
        });
    }
    source
}

fn load_trusted(bytes: &[u8], trust: &[hub::PublisherKey]) -> std::io::Result<hub::Snapshot> {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("catalog.json");
    fs::write(&path, bytes).unwrap();
    hub::load_trusted(&path, &format!("{:x}", Sha256::digest(bytes)), trust)
}

#[test]
fn no_key_is_pinned_until_the_owner_adds_one() {
    assert!(hub::pinned_publisher_keys().is_empty());
    let snap = load(FIXTURE.as_bytes()).unwrap();
    assert!(!snap.publisher_verified);
}

#[test]
fn every_plugin_signed_by_a_pinned_key_verifies_the_catalog() {
    let kp = key(7);
    let trust = [pinned(&kp, "pub-1", PUBLISHER)];
    let bytes = serde_json::to_vec(&sign_all(&kp, "pub-1")).unwrap();
    let snap = load_trusted(&bytes, &trust).unwrap();
    assert_eq!(snap.status, "verified");
    assert!(snap.publisher_verified);
    // The aggregate is an AND: one unsigned plugin keeps the catalog unverified.
    let mut partly: Value = serde_json::from_slice(&bytes).unwrap();
    partly["plugins"][0]["signature"] = Value::Null;
    let partly_bytes = serde_json::to_vec(&partly).unwrap();
    assert!(
        !load_trusted(&partly_bytes, &trust)
            .unwrap()
            .publisher_verified
    );
}

#[test]
fn unsigned_catalog_stays_unverified_and_loads() {
    let kp = key(7);
    let trust = [pinned(&kp, "pub-1", PUBLISHER)];
    let snap = load_trusted(FIXTURE.as_bytes(), &trust).unwrap();
    assert!(!snap.publisher_verified);
    assert_eq!(snap.status, "verified");
}

#[test]
fn signature_from_an_unpinned_key_is_unverified_not_trusted() {
    let pinned_kp = key(7);
    let other = key(9);
    let trust = [pinned(&pinned_kp, "pub-1", PUBLISHER)];
    // The key id is unknown to this Core: the signature proves nothing, the catalog still loads.
    let stranger = sign_all(&other, "pub-unknown");
    let snap = load_trusted(&serde_json::to_vec(&stranger).unwrap(), &trust).unwrap();
    assert!(!snap.publisher_verified);
}

#[test]
fn forged_signature_under_a_pinned_key_fails_the_whole_catalog() {
    let kp = key(7);
    let trust = [pinned(&kp, "pub-1", PUBLISHER)];
    // Signed by a different private key but claiming the pinned key id.
    let forged = sign_all(&key(9), "pub-1");
    let bytes = serde_json::to_vec(&forged).unwrap();
    assert!(load_trusted(&bytes, &trust).is_err());
}

#[test]
fn tampered_manifest_after_signing_fails_the_catalog() {
    let kp = key(7);
    let trust = [pinned(&kp, "pub-1", PUBLISHER)];
    let mut source = sign_all(&kp, "pub-1");
    // The signed content changes; the signature is stale.
    source["plugins"][0]["semver"] = json!("1.0.1");
    assert!(load_trusted(&serde_json::to_vec(&source).unwrap(), &trust).is_err());
}

#[test]
fn tampered_signature_bytes_fail_the_catalog() {
    let kp = key(7);
    let trust = [pinned(&kp, "pub-1", PUBLISHER)];
    let mut source = sign_all(&kp, "pub-1");
    let signature = source["plugins"][1]["signature"]["signature"]
        .as_str()
        .unwrap()
        .to_owned();
    let flipped = format!(
        "{}{}",
        &signature[..127],
        if signature.ends_with('0') { "1" } else { "0" }
    );
    source["plugins"][1]["signature"]["signature"] = json!(flipped);
    assert!(load_trusted(&serde_json::to_vec(&source).unwrap(), &trust).is_err());
}

#[test]
fn key_pinned_to_another_publisher_is_refused() {
    let kp = key(7);
    let trust = [pinned(&kp, "pub-1", "Someone else")];
    let bytes = serde_json::to_vec(&sign_all(&kp, "pub-1")).unwrap();
    assert!(load_trusted(&bytes, &trust).is_err());
}

#[test]
fn malformed_signature_fields_fail_closed() {
    let kp = key(7);
    let trust = [pinned(&kp, "pub-1", PUBLISHER)];
    let good = sign_all(&kp, "pub-1");
    let mut wrong_algorithm = good.clone();
    wrong_algorithm["plugins"][0]["signature"]["algorithm"] = json!("rsa");
    let mut short = good.clone();
    short["plugins"][0]["signature"]["signature"] = json!("abcd");
    let mut extra = good.clone();
    extra["plugins"][0]["signature"]["note"] = json!("x");
    for source in [wrong_algorithm, short, extra] {
        assert!(load_trusted(&serde_json::to_vec(&source).unwrap(), &trust).is_err());
    }
}

#[test]
fn publisher_trust_reports_each_state_directly() {
    let kp = key(7);
    let trust = [pinned(&kp, "pub-1", PUBLISHER)];
    let message = "a".repeat(64);
    let sig = hub::PublisherSignature {
        key_id: "pub-1".to_owned(),
        algorithm: "ed25519".to_owned(),
        signature: hex(kp.sign(message.as_bytes()).as_ref()),
    };
    assert_eq!(
        hub::publisher_trust(&message, None, PUBLISHER, &trust),
        Ok(hub::Trust::Unsigned)
    );
    assert_eq!(
        hub::publisher_trust(&message, Some(&sig), PUBLISHER, &trust),
        Ok(hub::Trust::Verified)
    );
    assert_eq!(
        hub::publisher_trust(&"b".repeat(64), Some(&sig), PUBLISHER, &trust),
        Err("bad_signature")
    );
    let unknown = hub::PublisherSignature {
        key_id: "nobody".to_owned(),
        ..sig.clone()
    };
    assert_eq!(
        hub::publisher_trust(&message, Some(&unknown), PUBLISHER, &trust),
        Ok(hub::Trust::Unverified)
    );
    assert_eq!(hub::decode_hex("0g"), None);
    assert_eq!(hub::decode_hex("0a1"), None);
    assert_eq!(hub::decode_hex("0aFf"), Some(vec![0x0a, 0xff]));
}
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
    // The grant date survives a restart and is a real Unix time (ms), never a guess.
    assert!(current.entries[0]
        .approved_at_ms
        .is_some_and(|ms| ms > 1_600_000_000_000));
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
    assert_eq!(changed.entries[0].approved_at_ms, None);
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

const PLUGIN: &str = "benign_fixture";
fn versioned(semver: &str) -> Vec<u8> {
    let mut value: serde_json::Value = serde_json::from_str(FIXTURE).unwrap();
    value["plugins"][0]["semver"] = serde_json::json!(semver);
    serde_json::to_vec(&value).unwrap()
}
fn stage(storage: &mut gideon_base::storage::Storage, snap: &hub::Snapshot, id: &str) {
    begin(storage, snap, id);
    hub::chunk_import(storage, id, 0, PAYLOAD_HEX).unwrap();
    hub::finish_import(storage, snap, id).unwrap();
}
/// Approves then stages entry 0 of `bytes`; returns the refreshed snapshot.
fn approve_and_stage(
    storage: &mut gideon_base::storage::Storage,
    bytes: &[u8],
    id: &str,
) -> hub::Snapshot {
    let snap = load(bytes).unwrap().with_approvals(storage);
    let e = &snap.entries[0];
    hub::approve(
        storage,
        &snap,
        snap.approval_revision,
        &e.plugin_id,
        &e.manifest_sha256,
        &e.permissions,
        true,
    )
    .unwrap();
    let snap = load(bytes).unwrap().with_approvals(storage);
    stage(storage, &snap, id);
    load(bytes).unwrap().with_approvals(storage)
}
fn installed_v1(storage: &mut gideon_base::storage::Storage) -> hub::Snapshot {
    let snap = approve_and_stage(storage, FIXTURE.as_bytes(), "v1");
    let manifest = snap.entries[0].manifest_sha256.clone();
    assert_eq!(
        hub::install(storage, &snap, 0, PLUGIN, &manifest),
        Ok("hub_plugin_installed")
    );
    load(FIXTURE.as_bytes()).unwrap().with_approvals(storage)
}
fn updated_to(storage: &mut gideon_base::storage::Storage, semver: &str) -> hub::Snapshot {
    let bytes = versioned(semver);
    let snap = approve_and_stage(storage, &bytes, &format!("up{}", semver.replace('.', "_")));
    let manifest = snap.entries[0].manifest_sha256.clone();
    assert_eq!(
        hub::install(storage, &snap, snap.install_revision, PLUGIN, &manifest),
        Ok("hub_plugin_updated")
    );
    load(&bytes).unwrap().with_approvals(storage)
}
fn namespace_file(storage: &gideon_base::storage::Storage, manifest: &str) -> std::path::PathBuf {
    storage
        .root
        .join("hub-plugins")
        .join(format!("{PLUGIN}-{manifest}.payload"))
}

#[test]
fn install_promotes_verified_payload_privately_and_survives_restart() {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};
    let (dir, mut storage, snap) = approved_import();
    stage(&mut storage, &snap, "upload");
    let snap = snap.with_approvals(&storage);
    let manifest = snap.entries[0].manifest_sha256.clone();
    assert_eq!(
        hub::install(&storage, &snap, 0, PLUGIN, &manifest),
        Ok("hub_plugin_installed")
    );
    let path = namespace_file(&storage, &manifest);
    assert_eq!(fs::read(&path).unwrap(), b"benign fixture\n");
    let meta = fs::metadata(&path).unwrap();
    assert_eq!(meta.permissions().mode() & 0o777, 0o600);
    assert_eq!(meta.nlink(), 1);
    assert!(!storage
        .root
        .join(format!("hub-{manifest}.payload"))
        .exists());
    let snap = snap.with_approvals(&storage);
    assert_eq!(snap.install_revision, 1);
    assert_eq!(snap.entries[0].status, "installed");
    assert!(!snap.entries[0].payload_staged);
    assert_eq!(snap.installed.len(), 1);
    assert_eq!(snap.installed[0].state, "installed");
    assert_eq!(snap.installed[0].runtime, "disabled");
    assert!(snap.installed[0].previous.is_none());
    drop(storage);
    let storage = gideon_base::storage::Storage::open(&dir.path().join("core")).unwrap();
    let restarted = load(FIXTURE.as_bytes()).unwrap().with_approvals(&storage);
    assert_eq!(restarted.install_revision, 1);
    assert_eq!(restarted.entries[0].status, "installed");
    assert_eq!(restarted.installed[0].state, "installed");
    assert_eq!(restarted.installed[0].runtime, "disabled");
}

#[test]
fn install_refuses_unsafe_preconditions_before_any_file_moves() {
    let (dir, mut storage, snap) = approved_import();
    let manifest = snap.entries[0].manifest_sha256.clone();
    assert_eq!(
        hub::install(&storage, &snap, 0, PLUGIN, &manifest),
        Err("payload_not_staged")
    );
    assert_eq!(
        hub::install(&storage, &snap, 9, PLUGIN, &manifest),
        Err("stale_install_revision")
    );
    assert_eq!(
        hub::install(&storage, &snap, 0, "absent", &manifest),
        Err("unknown_plugin")
    );
    assert_eq!(
        hub::install(&storage, &snap, 0, PLUGIN, &"0".repeat(64)),
        Err("manifest_mismatch")
    );
    assert_eq!(
        hub::install(
            &storage,
            &snap,
            0,
            "future_api",
            &snap.entries[1].manifest_sha256
        ),
        Err("plugin_incompatible")
    );
    begin(&mut storage, &snap, "busy");
    assert_eq!(
        hub::install(&storage, &snap, 0, PLUGIN, &manifest),
        Err("hub_import_busy")
    );
    hub::abort_import(&mut storage, "busy").unwrap();
    stage(&mut storage, &snap, "upload");
    let snap = snap.with_approvals(&storage);
    assert_eq!(
        hub::install(&storage, &snap, 0, PLUGIN, &manifest),
        Ok("hub_plugin_installed")
    );
    assert_eq!(
        hub::install(&storage, &snap, 0, PLUGIN, &manifest),
        Err("stale_install_revision")
    );
    let snap = snap.with_approvals(&storage);
    assert_eq!(
        hub::install(&storage, &snap, 1, PLUGIN, &manifest),
        Err("already_installed")
    );
    // Unapproved catalog entry on a fresh root never reaches the payload check.
    let other = tempfile::tempdir().unwrap();
    let fresh_storage = gideon_base::storage::Storage::open(&other.path().join("core")).unwrap();
    let fresh = load(FIXTURE.as_bytes())
        .unwrap()
        .with_approvals(&fresh_storage);
    assert_eq!(
        hub::install(&fresh_storage, &fresh, 0, PLUGIN, &manifest),
        Err("permissions_not_approved")
    );
    drop(dir);
}

#[test]
fn update_keeps_one_previous_and_rollback_swaps_only_ledger() {
    let dir = tempfile::tempdir().unwrap();
    let mut storage = gideon_base::storage::Storage::open(&dir.path().join("core")).unwrap();
    let v1 = installed_v1(&mut storage);
    let v1_manifest = v1.installed[0].manifest_sha256.clone();
    let v2_bytes = versioned("1.1.0");
    let v2 = updated_to(&mut storage, "1.1.0");
    assert_eq!(v2.install_revision, 2);
    assert_eq!(v2.installed[0].semver, "1.1.0");
    assert_eq!(v2.installed[0].state, "installed");
    assert_eq!(v2.entries[0].status, "installed");
    let previous = v2.installed[0].previous.clone().unwrap();
    assert_eq!(previous.semver, "1.0.0");
    assert_eq!(previous.manifest_sha256, v1_manifest);
    assert!(namespace_file(&storage, &v1_manifest).exists());

    assert_eq!(
        hub::rollback(&storage, &v2, 2, PLUGIN),
        Ok("hub_plugin_rolled_back")
    );
    let back = load(&v2_bytes).unwrap().with_approvals(&storage);
    assert_eq!(back.installed[0].semver, "1.0.0");
    assert_eq!(back.installed[0].previous.clone().unwrap().semver, "1.1.0");
    assert_eq!(back.entries[0].status, "update_available");
    assert_eq!(
        hub::rollback(&storage, &back, 3, PLUGIN),
        Ok("hub_plugin_rolled_back")
    );
    let again = load(&v2_bytes).unwrap().with_approvals(&storage);
    assert_eq!(again.installed[0].semver, "1.1.0");
    assert_eq!(again.installed[0].previous.clone().unwrap().semver, "1.0.0");
    assert_eq!(
        hub::rollback(&storage, &again, 99, PLUGIN),
        Err("stale_install_revision")
    );

    // A third version drops the oldest previous file after its commit.
    let v3 = updated_to(&mut storage, "1.2.0");
    assert_eq!(v3.installed[0].semver, "1.2.0");
    assert_eq!(v3.installed[0].previous.clone().unwrap().semver, "1.1.0");
    assert!(!namespace_file(&storage, &v1_manifest).exists());
}

#[test]
fn remove_deletes_active_and_previous_files_and_ledger_record() {
    let dir = tempfile::tempdir().unwrap();
    let mut storage = gideon_base::storage::Storage::open(&dir.path().join("core")).unwrap();
    installed_v1(&mut storage);
    let v2 = updated_to(&mut storage, "1.1.0");
    let active = v2.installed[0].manifest_sha256.clone();
    let previous = v2.installed[0].previous.clone().unwrap().manifest_sha256;
    assert!(namespace_file(&storage, &active).exists());
    assert!(namespace_file(&storage, &previous).exists());
    assert_eq!(
        hub::remove(&storage, &v2, v2.install_revision, PLUGIN),
        Ok("hub_plugin_removed")
    );
    assert!(!namespace_file(&storage, &active).exists());
    assert!(!namespace_file(&storage, &previous).exists());
    let after = load(&versioned("1.1.0")).unwrap().with_approvals(&storage);
    assert!(after.installed.is_empty());
    assert_eq!(after.install_revision, 3);
    assert_eq!(after.entries[0].status, "not_installed");
    assert_eq!(
        hub::remove(&storage, &after, 3, PLUGIN),
        Err("not_installed")
    );
}

fn quarantined_after_tamper(tamper: fn(&std::path::Path, &std::path::Path)) {
    let dir = tempfile::tempdir().unwrap();
    let mut storage = gideon_base::storage::Storage::open(&dir.path().join("core")).unwrap();
    let snap = installed_v1(&mut storage);
    let path = namespace_file(&storage, &snap.installed[0].manifest_sha256);
    tamper(&path, &dir.path().join("sentinel"));
    let snap = load(FIXTURE.as_bytes()).unwrap().with_approvals(&storage);
    assert_eq!(snap.status, "verified");
    assert_eq!(snap.installed[0].state, "quarantined");
    assert_eq!(snap.entries[0].status, "installed");
    assert_eq!(
        hub::rollback(&storage, &snap, snap.install_revision, PLUGIN),
        Err("plugin_quarantined")
    );
    assert_eq!(
        hub::remove(&storage, &snap, snap.install_revision, PLUGIN),
        Ok("hub_plugin_removed")
    );
    assert!(fs::symlink_metadata(&path).is_err());
}

#[test]
fn tampered_installed_payload_quarantines_only_that_plugin() {
    use std::io::Write;
    use std::os::unix::fs::PermissionsExt;
    quarantined_after_tamper(|path, _| {
        fs::OpenOptions::new()
            .append(true)
            .open(path)
            .unwrap()
            .write_all(b"!")
            .unwrap();
    });
    quarantined_after_tamper(|path, _| {
        fs::set_permissions(path, fs::Permissions::from_mode(0o644)).unwrap();
    });
    quarantined_after_tamper(|path, sentinel| {
        fs::write(sentinel, b"outside").unwrap();
        fs::remove_file(path).unwrap();
        symlink(sentinel, path).unwrap();
        assert_eq!(fs::read(sentinel).unwrap(), b"outside");
    });
}

#[test]
fn corrupt_install_ledger_quarantines_hub_without_stopping_base() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempfile::tempdir().unwrap();
    let mut storage = gideon_base::storage::Storage::open(&dir.path().join("core")).unwrap();
    installed_v1(&mut storage);
    let path = storage.root.join("hub-installed.json");
    for (bytes, mode) in [
        (b"{".to_vec(), 0o600),
        (
            b"{\"version\":1,\"revision\":1,\"records\":[],\"extra\":1}".to_vec(),
            0o600,
        ),
        (
            b"{\"version\":1,\"revision\":1,\"records\":[]}".to_vec(),
            0o644,
        ),
    ] {
        fs::write(&path, bytes).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(mode)).unwrap();
        assert_eq!(
            load(FIXTURE.as_bytes())
                .unwrap()
                .with_approvals(&storage)
                .status,
            "quarantined"
        );
    }
    assert_eq!(
        storage.configuration_status,
        gideon_base::storage::ConfigurationStatus::Ready
    );
}

#[test]
fn install_collision_fails_closed_and_keeps_foreign_file_and_staged_payload() {
    use std::os::unix::fs::{DirBuilderExt, PermissionsExt};
    let (_dir, mut storage, snap) = approved_import();
    stage(&mut storage, &snap, "upload");
    let snap = snap.with_approvals(&storage);
    let manifest = snap.entries[0].manifest_sha256.clone();
    let namespace = storage.root.join("hub-plugins");
    fs::DirBuilder::new()
        .mode(0o700)
        .create(&namespace)
        .unwrap();
    let foreign = namespace_file(&storage, &manifest);
    fs::write(&foreign, b"foreign").unwrap();
    fs::set_permissions(&foreign, fs::Permissions::from_mode(0o600)).unwrap();
    assert_eq!(
        hub::install(&storage, &snap, 0, PLUGIN, &manifest),
        Err("hub_storage_error")
    );
    assert_eq!(fs::read(&foreign).unwrap(), b"foreign");
    let after = snap.with_approvals(&storage);
    assert!(after.entries[0].payload_staged);
    assert_eq!(after.entries[0].status, "not_installed");
    assert_eq!(after.install_revision, 0);
}

#[test]
fn retained_previous_version_cannot_reinstall_via_install() {
    let dir = tempfile::tempdir().unwrap();
    let mut storage = gideon_base::storage::Storage::open(&dir.path().join("core")).unwrap();
    installed_v1(&mut storage);
    let v2_bytes = versioned("1.1.0");
    let v2 = updated_to(&mut storage, "1.1.0");
    let v2_manifest = v2.installed[0].manifest_sha256.clone();
    let v1_manifest = v2.installed[0].previous.clone().unwrap().manifest_sha256;
    assert_eq!(
        hub::rollback(&storage, &v2, 2, PLUGIN),
        Ok("hub_plugin_rolled_back")
    );
    let back = load(&v2_bytes).unwrap().with_approvals(&storage);
    assert_eq!(back.install_revision, 3);
    assert_eq!(back.installed[0].semver, "1.0.0");
    assert_eq!(back.installed[0].previous.clone().unwrap().semver, "1.1.0");
    assert_eq!(back.entries[0].status, "update_available");
    // A retained previous version is refused before staging (P8): nothing is staged or installed.
    let refused = hub::begin_import(
        &mut storage,
        &back,
        back.approval_revision,
        PLUGIN,
        &v2_manifest,
        "again",
        std::time::Instant::now(),
    );
    assert_eq!(refused, Err("version_retained_use_rollback"));
    let staged = load(&v2_bytes).unwrap().with_approvals(&storage);
    assert!(!staged.entries[0].payload_staged);
    assert_eq!(staged.entries[0].manifest_sha256, v2_manifest);
    assert_eq!(
        hub::install(&storage, &staged, 3, PLUGIN, &v2_manifest),
        Err("payload_not_staged")
    );
    let after = load(&v2_bytes).unwrap().with_approvals(&storage);
    assert_eq!(after.install_revision, 3);
    assert_eq!(after.installed[0].semver, "1.0.0");
    assert_eq!(after.entries[0].status, "update_available");
    assert!(!after.entries[0].payload_staged);
    assert_eq!(
        fs::read(namespace_file(&storage, &v1_manifest)).unwrap(),
        b"benign fixture\n"
    );
    assert_eq!(
        fs::read(namespace_file(&storage, &v2_manifest)).unwrap(),
        b"benign fixture\n"
    );
    // Refused staging leaves no staged payload behind.
    assert!(!storage
        .root
        .join(format!("hub-{v2_manifest}.payload"))
        .exists());
}

/// Approves then stages entry 0 of `bytes`, chaining the cached snapshot like Core does.
fn approve_stage_chain(
    storage: &mut gideon_base::storage::Storage,
    bytes: &[u8],
    id: &str,
) -> hub::Snapshot {
    let s = load(bytes).unwrap().with_approvals(storage);
    let e = &s.entries[0];
    hub::approve(
        storage,
        &s,
        s.approval_revision,
        &e.plugin_id,
        &e.manifest_sha256,
        &e.permissions,
        true,
    )
    .unwrap();
    let s = s.with_approvals(storage);
    stage(storage, &s, id);
    s.with_approvals(storage)
}

#[test]
fn chained_snapshots_reset_installed_status_after_remove() {
    let dir = tempfile::tempdir().unwrap();
    let mut storage = gideon_base::storage::Storage::open(&dir.path().join("core")).unwrap();
    let s0 = load(FIXTURE.as_bytes()).unwrap().with_approvals(&storage);
    let manifest = s0.entries[0].manifest_sha256.clone();
    hub::approve(
        &storage,
        &s0,
        0,
        PLUGIN,
        &manifest,
        &s0.entries[0].permissions,
        true,
    )
    .unwrap();
    let mut cached = s0.with_approvals(&storage);
    stage(&mut storage, &cached, "upload");
    cached = cached.with_approvals(&storage);
    assert_eq!(
        hub::install(
            &storage,
            &cached,
            cached.install_revision,
            PLUGIN,
            &manifest
        ),
        Ok("hub_plugin_installed")
    );
    cached = cached.with_approvals(&storage);
    assert_eq!(cached.entries[0].status, "installed");
    assert_eq!(cached.install_revision, 1);
    assert_eq!(
        hub::remove(&storage, &cached, cached.install_revision, PLUGIN),
        Ok("hub_plugin_removed")
    );
    cached = cached.with_approvals(&storage);
    assert_eq!(cached.entries[0].status, "not_installed");
    assert!(cached.installed.is_empty());
}

#[test]
fn chained_snapshots_track_update_and_rollback_statuses() {
    let dir = tempfile::tempdir().unwrap();
    let mut storage = gideon_base::storage::Storage::open(&dir.path().join("core")).unwrap();
    let v1 = approve_stage_chain(&mut storage, FIXTURE.as_bytes(), "v1");
    let v1_manifest = v1.entries[0].manifest_sha256.clone();
    assert_eq!(
        hub::install(&storage, &v1, v1.install_revision, PLUGIN, &v1_manifest),
        Ok("hub_plugin_installed")
    );
    let mut v2 = approve_stage_chain(&mut storage, &versioned("1.1.0"), "v2");
    let v2_manifest = v2.entries[0].manifest_sha256.clone();
    assert_eq!(
        hub::install(&storage, &v2, v2.install_revision, PLUGIN, &v2_manifest),
        Ok("hub_plugin_updated")
    );
    v2 = v2.with_approvals(&storage);
    assert_eq!(v2.entries[0].status, "installed");
    assert_eq!(v2.installed[0].semver, "1.1.0");

    assert_eq!(
        hub::rollback(&storage, &v2, v2.install_revision, PLUGIN),
        Ok("hub_plugin_rolled_back")
    );
    v2 = v2.with_approvals(&storage);
    assert_eq!(v2.entries[0].status, "update_available");
    assert_eq!(v2.installed[0].semver, "1.0.0");

    assert_eq!(
        hub::rollback(&storage, &v2, v2.install_revision, PLUGIN),
        Ok("hub_plugin_rolled_back")
    );
    v2 = v2.with_approvals(&storage);
    assert_eq!(v2.entries[0].status, "installed");
    assert_eq!(v2.installed[0].semver, "1.1.0");
}

#[test]
fn remove_never_unlinks_through_replaced_namespace_symlink() {
    let dir = tempfile::tempdir().unwrap();
    let mut storage = gideon_base::storage::Storage::open(&dir.path().join("core")).unwrap();
    let snap = installed_v1(&mut storage);
    let manifest = snap.installed[0].manifest_sha256.clone();
    let elsewhere = tempfile::tempdir().unwrap();
    let target = elsewhere
        .path()
        .join(format!("{PLUGIN}-{manifest}.payload"));
    fs::write(&target, b"outside").unwrap();
    let namespace = storage.root.join("hub-plugins");
    fs::remove_dir_all(&namespace).unwrap();
    symlink(elsewhere.path(), &namespace).unwrap();
    let snap = load(FIXTURE.as_bytes()).unwrap().with_approvals(&storage);
    assert_eq!(
        hub::remove(&storage, &snap, snap.install_revision, PLUGIN),
        Ok("hub_plugin_removed")
    );
    let after = load(FIXTURE.as_bytes()).unwrap().with_approvals(&storage);
    assert!(after.installed.is_empty());
    assert_eq!(after.install_revision, 2);
    assert_eq!(fs::read(&target).unwrap(), b"outside");
}

/// P9: a deleted approvals ledger that was written before is a loss, never an empty Hub.
#[test]
fn deleted_ledger_is_quarantined_not_reset_to_revision_zero() {
    let (_dir, storage, _snap) = approved_import();
    fs::remove_file(storage.root.join("hub-approvals.json")).unwrap();
    let hub = load(FIXTURE.as_bytes()).unwrap().with_approvals(&storage);
    assert_eq!(hub.status, "quarantined");
    assert_eq!(hub.reason, Some("ledger_missing"));
}

/// P8: an unreadable staged payload hides only its entry; discard_staged removes it under CAS.
#[test]
fn unreadable_staged_payload_is_per_entry_and_discardable() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempfile::tempdir().unwrap();
    let mut storage = gideon_base::storage::Storage::open(&dir.path().join("core")).unwrap();
    let snap = approve_and_stage(&mut storage, FIXTURE.as_bytes(), "discard-1");
    let plugin = snap.entries[0].plugin_id.clone();
    assert!(snap.entries[0].payload_staged);
    let staged = storage
        .root
        .join(format!("hub-{}.payload", snap.entries[0].manifest_sha256));
    fs::set_permissions(&staged, fs::Permissions::from_mode(0o644)).unwrap();
    let hub = load(FIXTURE.as_bytes()).unwrap().with_approvals(&storage);
    assert_eq!(hub.status, "verified");
    assert!(!hub.entries[0].payload_staged);
    assert_eq!(hub.entries[0].staged_error, Some("staged_payload_invalid"));
    assert_eq!(
        hub::discard_staged(&storage, &hub, hub.approval_revision + 1, &plugin),
        Err("stale_hub_revision")
    );
    assert!(staged.exists());
    assert_eq!(
        hub::discard_staged(&storage, &hub, hub.approval_revision, &plugin),
        Ok("hub_staged_discarded")
    );
    assert!(!staged.exists());
    let after = load(FIXTURE.as_bytes()).unwrap().with_approvals(&storage);
    assert_eq!(after.entries[0].staged_error, None);
    assert_eq!(
        hub::discard_staged(&storage, &after, after.approval_revision, &plugin),
        Err("not_staged")
    );
}

/// P7: a same-size replacement with its old mtime restored is re-hashed, not served from cache.
#[test]
fn verification_cache_rehashes_same_size_same_mtime_replacement() {
    let dir = tempfile::tempdir().unwrap();
    let mut storage = gideon_base::storage::Storage::open(&dir.path().join("core")).unwrap();
    installed_v1(&mut storage);
    let first = load(FIXTURE.as_bytes()).unwrap().with_approvals(&storage);
    assert_eq!(first.installed[0].state, "installed");
    // A second refresh is a cache hit and must still agree.
    let cached = load(FIXTURE.as_bytes()).unwrap().with_approvals(&storage);
    assert_eq!(cached.installed[0].state, "installed");
    let file = namespace_file(&storage, &first.installed[0].manifest_sha256);
    let bytes = fs::read(&file).unwrap();
    let before = fs::metadata(&file).unwrap().modified().unwrap();
    let mut flipped = bytes.clone();
    flipped[0] ^= 0x01;
    fs::write(&file, &flipped).unwrap();
    fs::File::open(&file).unwrap().set_modified(before).unwrap();
    assert_eq!(fs::metadata(&file).unwrap().len(), bytes.len() as u64);
    let tampered = load(FIXTURE.as_bytes()).unwrap().with_approvals(&storage);
    assert_eq!(tampered.installed[0].state, "quarantined");
}

// ---------------------------------------------------------------------------
// EXT-03 (WP15): update channel. Positive and negative cases; every refusal is a code.
// ---------------------------------------------------------------------------

fn sha_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn plugin0_id() -> String {
    let source: Value = serde_json::from_str(FIXTURE).unwrap();
    source["plugins"][0]["plugin_id"]
        .as_str()
        .unwrap()
        .to_owned()
}

/// The fixture with `edit` applied, every plugin signed by `kp` under `key_id` (after the edit, so
/// the signatures cover what is written).
fn signed_catalog(kp: &Ed25519KeyPair, key_id: &str, edit: impl FnOnce(&mut Value)) -> Vec<u8> {
    let mut source: Value = serde_json::from_str(FIXTURE).unwrap();
    edit(&mut source);
    for index in 0..source["plugins"].as_array().unwrap().len() {
        let message = signing_message(&source["plugins"][index]);
        source["plugins"][index]["signature"] = json!({
            "key_id": key_id,
            "algorithm": "ed25519",
            "signature": hex(kp.sign(message.as_bytes()).as_ref()),
        });
    }
    serde_json::to_vec(&source).unwrap()
}

fn set_semver(source: &mut Value, semver: &str) {
    source["plugins"][0]["semver"] = json!(semver);
}

fn place_bytes(dir: &std::path::Path, name: &str, bytes: &[u8]) -> std::path::PathBuf {
    let path = dir.join(name);
    fs::write(&path, bytes).unwrap();
    path
}

fn update_key() -> (Ed25519KeyPair, Vec<hub::PublisherKey>) {
    let kp = key(7);
    let trust = vec![pinned(&kp, "pub-1", PUBLISHER)];
    (kp, trust)
}

#[test]
fn update_check_apply_and_rollback_on_a_signed_catalog() {
    let (kp, trust) = update_key();
    let dir = tempfile::tempdir().unwrap();
    let current_bytes = FIXTURE.as_bytes().to_vec();
    let current = place_bytes(dir.path(), "active.json", &current_bytes);
    let current_sha = sha_hex(&current_bytes);
    let candidate_bytes = signed_catalog(&kp, "pub-1", |s| set_semver(s, "1.1.0"));
    let candidate = place_bytes(dir.path(), "candidate.json", &candidate_bytes);

    let check = hub::check_update(&current, &current_sha, &candidate, &trust).unwrap();
    assert_eq!(check.candidate_sha256, sha_hex(&candidate_bytes));
    assert_eq!(check.changes.len(), 1);
    assert_eq!(check.changes[0].plugin_id, plugin0_id());
    assert_eq!(check.changes[0].to, "1.1.0");

    let store = dir.path().join("store");
    let state = hub::apply_update(&store, &current, &current_sha, &candidate, &trust).unwrap();
    assert_eq!(state.active, check.candidate_sha256);
    assert_eq!(state.previous.as_deref(), Some(current_sha.as_str()));
    let (active_path, active_sha) = hub::active_catalog(&store).unwrap().unwrap();
    assert_eq!(active_sha, state.active);
    let active = hub::load_trusted(&active_path, &active_sha, &trust).unwrap();
    assert!(active.publisher_verified);
    assert_eq!(active.entries[0].semver, "1.1.0");

    // Rollback swaps the digests back and the previous bytes are the original catalog again.
    let back = hub::rollback_update(&store, &trust).unwrap();
    assert_eq!(back.active, current_sha);
    assert_eq!(back.previous.as_deref(), Some(state.active.as_str()));
    let (_, now) = hub::active_catalog(&store).unwrap().unwrap();
    assert_eq!(now, current_sha);
    assert_eq!(
        fs::read(store.join(format!("catalog-{current_sha}.json"))).unwrap(),
        current_bytes
    );
    // The state file is private (0600).
    let mode = fs::metadata(store.join("hub-update.json"))
        .unwrap()
        .permissions();
    assert_eq!(
        std::os::unix::fs::PermissionsExt::mode(&mode) & 0o777,
        0o600
    );
}

#[test]
fn an_unsigned_candidate_is_refused_as_unverified_and_nothing_is_written() {
    let (_kp, trust) = update_key();
    let dir = tempfile::tempdir().unwrap();
    let current_bytes = FIXTURE.as_bytes().to_vec();
    let current = place_bytes(dir.path(), "active.json", &current_bytes);
    let mut unsigned: Value = serde_json::from_str(FIXTURE).unwrap();
    set_semver(&mut unsigned, "1.1.0");
    let candidate = place_bytes(
        dir.path(),
        "candidate.json",
        &serde_json::to_vec(&unsigned).unwrap(),
    );
    let sha = sha_hex(&current_bytes);
    assert_eq!(
        hub::check_update(&current, &sha, &candidate, &trust).unwrap_err(),
        "update_unverified"
    );
    let store = dir.path().join("store");
    assert_eq!(
        hub::apply_update(&store, &current, &sha, &candidate, &trust).unwrap_err(),
        "update_unverified"
    );
    assert!(!store.join("hub-update.json").exists());
}

#[test]
fn a_signature_under_an_unpinned_key_is_unverified_not_trusted() {
    let (kp, _) = update_key();
    let dir = tempfile::tempdir().unwrap();
    let current_bytes = FIXTURE.as_bytes().to_vec();
    let current = place_bytes(dir.path(), "active.json", &current_bytes);
    let candidate = place_bytes(
        dir.path(),
        "candidate.json",
        &signed_catalog(&kp, "pub-1", |s| set_semver(s, "1.1.0")),
    );
    let sha = sha_hex(&current_bytes);
    // Empty trust list: the key is not pinned, so the candidate loads but never counts as verified.
    assert_eq!(
        hub::check_update(&current, &sha, &candidate, &[]).unwrap_err(),
        "update_unverified"
    );
}

#[test]
fn a_forged_candidate_is_refused_as_invalid() {
    let (_kp, trust) = update_key();
    let forger = key(9);
    let dir = tempfile::tempdir().unwrap();
    let current_bytes = FIXTURE.as_bytes().to_vec();
    let current = place_bytes(dir.path(), "active.json", &current_bytes);
    // Signed by another key under the pinned key id: the whole catalog fails closed.
    let candidate = place_bytes(
        dir.path(),
        "candidate.json",
        &signed_catalog(&forger, "pub-1", |s| set_semver(s, "1.1.0")),
    );
    assert_eq!(
        hub::check_update(&current, &sha_hex(&current_bytes), &candidate, &trust).unwrap_err(),
        "update_invalid"
    );
}

#[test]
fn a_tampered_signed_candidate_is_refused_as_invalid() {
    let (kp, trust) = update_key();
    let dir = tempfile::tempdir().unwrap();
    let current_bytes = FIXTURE.as_bytes().to_vec();
    let current = place_bytes(dir.path(), "active.json", &current_bytes);
    let mut tampered: Value =
        serde_json::from_slice(&signed_catalog(&kp, "pub-1", |s| set_semver(s, "1.1.0"))).unwrap();
    // A signed field changed after signing: the manifest no longer matches its signature.
    tampered["plugins"][0]["license"] = json!("GPL-3.0-only");
    let candidate = place_bytes(
        dir.path(),
        "candidate.json",
        &serde_json::to_vec(&tampered).unwrap(),
    );
    assert_eq!(
        hub::check_update(&current, &sha_hex(&current_bytes), &candidate, &trust).unwrap_err(),
        "update_invalid"
    );
}

#[test]
fn a_candidate_that_lowers_a_plugin_version_is_refused_as_a_downgrade() {
    let (kp, trust) = update_key();
    let dir = tempfile::tempdir().unwrap();
    let current_bytes = signed_catalog(&kp, "pub-1", |s| set_semver(s, "1.1.0"));
    let current = place_bytes(dir.path(), "active.json", &current_bytes);
    let candidate = place_bytes(
        dir.path(),
        "candidate.json",
        &signed_catalog(&kp, "pub-1", |s| set_semver(s, "1.0.0")),
    );
    assert_eq!(
        hub::check_update(&current, &sha_hex(&current_bytes), &candidate, &trust).unwrap_err(),
        "update_downgrade"
    );
}

#[test]
fn the_same_bytes_are_unchanged_and_another_repository_is_refused() {
    let (kp, trust) = update_key();
    let dir = tempfile::tempdir().unwrap();
    let current_bytes = signed_catalog(&kp, "pub-1", |s| set_semver(s, "1.1.0"));
    let current = place_bytes(dir.path(), "active.json", &current_bytes);
    let sha = sha_hex(&current_bytes);
    assert_eq!(
        hub::check_update(&current, &sha, &current, &trust).unwrap_err(),
        "update_unchanged"
    );
    let moved = place_bytes(
        dir.path(),
        "moved.json",
        &signed_catalog(&kp, "pub-1", |s| {
            set_semver(s, "1.2.0");
            s["repository"] = json!("https://github.com/other-owner/other-repo");
        }),
    );
    assert_eq!(
        hub::check_update(&current, &sha, &moved, &trust).unwrap_err(),
        "update_repository"
    );
}

#[test]
fn a_damaged_active_catalog_blocks_the_check() {
    let (kp, trust) = update_key();
    let dir = tempfile::tempdir().unwrap();
    let mut current_bytes = FIXTURE.as_bytes().to_vec();
    let recorded = sha_hex(&current_bytes);
    current_bytes.push(b' ');
    let current = place_bytes(dir.path(), "active.json", &current_bytes);
    let candidate = place_bytes(
        dir.path(),
        "candidate.json",
        &signed_catalog(&kp, "pub-1", |s| set_semver(s, "1.1.0")),
    );
    assert_eq!(
        hub::check_update(&current, &recorded, &candidate, &trust).unwrap_err(),
        "update_current_invalid"
    );
}

#[test]
fn rollback_without_an_applied_update_and_a_damaged_state_are_refused() {
    let (_kp, trust) = update_key();
    let dir = tempfile::tempdir().unwrap();
    let store = dir.path().join("store");
    assert_eq!(
        hub::rollback_update(&store, &trust).unwrap_err(),
        "update_no_previous"
    );
    assert!(hub::update_state(&store).unwrap().is_none());
    fs::create_dir_all(&store).unwrap();
    fs::write(store.join("hub-update.json"), br#"{"active":"nothex"}"#).unwrap();
    assert_eq!(
        hub::update_state(&store).unwrap_err(),
        "update_storage_error"
    );
    assert_eq!(
        hub::rollback_update(&store, &trust).unwrap_err(),
        "update_storage_error"
    );
}

#[test]
fn rollback_reverifies_the_previous_catalog_before_switching() {
    let (kp, trust) = update_key();
    let dir = tempfile::tempdir().unwrap();
    let current_bytes = FIXTURE.as_bytes().to_vec();
    let current = place_bytes(dir.path(), "active.json", &current_bytes);
    let current_sha = sha_hex(&current_bytes);
    let candidate = place_bytes(
        dir.path(),
        "candidate.json",
        &signed_catalog(&kp, "pub-1", |s| set_semver(s, "1.1.0")),
    );
    let store = dir.path().join("store");
    let state = hub::apply_update(&store, &current, &current_sha, &candidate, &trust).unwrap();
    // The stored previous catalog is damaged on disk: the rollback is refused and the state stays.
    fs::write(store.join(format!("catalog-{current_sha}.json")), b"{}").unwrap();
    assert_eq!(
        hub::rollback_update(&store, &trust).unwrap_err(),
        "update_storage_error"
    );
    assert_eq!(hub::update_state(&store).unwrap().unwrap(), state);
}
