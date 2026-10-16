//! Hub hardening: exact refusal reasons and tamper/mode guards through the public Hub API.
//! Each test names the mutation it kills in its comment. No network; tempdir roots only.
use gideon_base::{hub, storage::Storage};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    fs,
    os::unix::fs::{symlink, PermissionsExt},
    path::{Path, PathBuf},
};

const FIXTURE: &str = include_str!("fixtures/hub.json");
const PLUGIN: &str = "benign_fixture";
/// Hex of the 14-byte fixture payload "benign fixture\n".
const PAYLOAD_HEX: &str = "62656e69676e20666978747572650a";
/// Same length as the payload, different bytes.
const TAMPERED_HEX: &str = "62656e69676e20666978747572650b";

fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn load(bytes: &[u8]) -> std::io::Result<hub::Snapshot> {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("catalog.json");
    fs::write(&path, bytes).unwrap();
    hub::load(&path, &sha(bytes))
}

fn fixture() -> hub::Snapshot {
    load(FIXTURE.as_bytes()).unwrap()
}

fn open(dir: &Path) -> Storage {
    Storage::open(&dir.join("core")).unwrap()
}

fn root(dir: &Path) -> PathBuf {
    dir.join("core")
}

/// Approves entry 0 of the fixture with the real API; returns the refreshed snapshot.
fn approve_fixture(storage: &Storage) -> hub::Snapshot {
    let snap = fixture().with_approvals(storage);
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
    fixture().with_approvals(storage)
}

fn begin(storage: &mut Storage, snap: &hub::Snapshot, import_id: &str) -> Result<(), &'static str> {
    let e = &snap.entries[0];
    hub::begin_import(
        storage,
        snap,
        snap.approval_revision,
        &e.plugin_id,
        &e.manifest_sha256,
        import_id,
        std::time::Instant::now(),
    )
}

/// Approves, then stages the fixture payload through the real import path.
fn approve_and_stage(storage: &mut Storage) -> hub::Snapshot {
    let snap = approve_fixture(storage);
    begin(storage, &snap, "upload").unwrap();
    hub::chunk_import(storage, "upload", 0, PAYLOAD_HEX).unwrap();
    hub::finish_import(storage, &snap, "upload").unwrap();
    fixture().with_approvals(storage)
}

fn payload_path(storage: &Storage, manifest: &str) -> PathBuf {
    storage.root.join(format!("hub-{manifest}.payload"))
}

fn namespace_file(storage: &Storage, manifest: &str) -> PathBuf {
    storage
        .root
        .join("hub-plugins")
        .join(format!("{PLUGIN}-{manifest}.payload"))
}

fn mode_of(path: &Path) -> u32 {
    fs::metadata(path).unwrap().permissions().mode() & 0o777
}

fn set_mode(path: &Path, mode: u32) {
    fs::set_permissions(path, fs::Permissions::from_mode(mode)).unwrap();
}

#[test]
fn approve_refuses_permission_mismatch_and_leaves_approvals_bytes_unchanged() {
    // Kills M03: a mutant that skips or reorders the `permissions_mismatch` check would write
    // an approval record (or reach `already_approved`) instead of refusing.
    let dir = tempfile::tempdir().unwrap();
    let storage = open(dir.path());
    let snap = fixture().with_approvals(&storage);
    let e = snap.entries[0].clone();
    let extra = vec!["notifications".to_owned(), "extra".to_owned()];
    assert_eq!(
        hub::approve(
            &storage,
            &snap,
            0,
            &e.plugin_id,
            &e.manifest_sha256,
            &extra,
            true
        ),
        Err("permissions_mismatch")
    );
    assert_eq!(
        hub::approve(
            &storage,
            &snap,
            0,
            &e.plugin_id,
            &e.manifest_sha256,
            &[],
            true
        ),
        Err("permissions_mismatch")
    );
    assert!(
        !root(dir.path()).join("hub-approvals.json").exists(),
        "a refused approval must not create the approvals file"
    );
    // With a real approval on disk, a mismatched second approval must not rewrite it either.
    approve_fixture(&storage);
    let path = root(dir.path()).join("hub-approvals.json");
    let before = fs::read(&path).unwrap();
    let current = fixture().with_approvals(&storage);
    assert_eq!(current.approval_revision, 1);
    assert_eq!(
        hub::approve(
            &storage,
            &current,
            1,
            &e.plugin_id,
            &e.manifest_sha256,
            &extra,
            true
        ),
        Err("permissions_mismatch")
    );
    assert_eq!(
        hub::approve(
            &storage,
            &current,
            1,
            &e.plugin_id,
            &e.manifest_sha256,
            &[],
            true
        ),
        Err("permissions_mismatch")
    );
    assert_eq!(fs::read(&path).unwrap(), before, "approvals bytes changed");
}

#[test]
fn stale_approval_revision_is_checked_before_plugin_and_manifest() {
    // Kills M04: reordering the revision check after `unknown_plugin` or `manifest_mismatch`
    // turns these exact reasons into something else.
    let dir = tempfile::tempdir().unwrap();
    let storage = open(dir.path());
    let snap = fixture().with_approvals(&storage);
    let e = snap.entries[0].clone();
    let stale = snap.approval_revision + 5;
    assert_eq!(
        hub::approve(&storage, &snap, stale, "no_such_plugin", "bogus", &[], true),
        Err("stale_hub_revision")
    );
    assert_eq!(
        hub::approve(
            &storage,
            &snap,
            stale,
            &e.plugin_id,
            "bogus",
            &e.permissions,
            true
        ),
        Err("stale_hub_revision")
    );
    // Control: with the current revision the same bogus manifest is a manifest mismatch.
    assert_eq!(
        hub::approve(
            &storage,
            &snap,
            snap.approval_revision,
            &e.plugin_id,
            "bogus",
            &e.permissions,
            true
        ),
        Err("manifest_mismatch")
    );
    assert!(!root(dir.path()).join("hub-approvals.json").exists());
}

#[test]
fn staged_payload_with_loose_mode_is_not_staged_and_blocks_install() {
    // Kills M08 (staged): dropping the exact-0600 check in open_verified would report the loose
    // or owner-only payload as staged and let install promote it.
    // Current behaviour (hub.rs staged handling): only this entry is unusable. The Hub stays
    // verified, payload_staged is false, staged_error is "staged_payload_invalid", and install
    // refuses with payload_not_staged. The file itself is never touched.
    let dir = tempfile::tempdir().unwrap();
    let mut storage = open(dir.path());
    let snap = approve_and_stage(&mut storage);
    assert!(snap.entries[0].payload_staged);
    let manifest = snap.entries[0].manifest_sha256.clone();
    let path = payload_path(&storage, &manifest);
    for mode in [0o644, 0o640, 0o604, 0o400, 0o700] {
        set_mode(&path, mode);
        let before = fs::read(&path).unwrap();
        let current = fixture().with_approvals(&storage);
        assert_eq!(current.status, "verified", "mode {mode:o}");
        assert!(!current.entries[0].payload_staged, "mode {mode:o}");
        assert_eq!(
            current.entries[0].staged_error,
            Some("staged_payload_invalid"),
            "mode {mode:o}"
        );
        assert_eq!(
            hub::install(
                &storage,
                &current,
                current.install_revision,
                PLUGIN,
                &manifest
            ),
            Err("payload_not_staged"),
            "mode {mode:o}"
        );
        assert_eq!(fs::read(&path).unwrap(), before, "mode {mode:o}");
        assert_eq!(mode_of(&path), mode, "refusal must not chmod the file");
    }
    set_mode(&path, 0o600);
    let restored = fixture().with_approvals(&storage);
    assert!(restored.entries[0].payload_staged);
    assert_eq!(restored.entries[0].staged_error, None);
}

#[test]
fn installed_payload_with_loose_mode_quarantines_only_that_plugin() {
    // Kills M08 (installed): dropping the 0600 check in installed_summary/verified_payload_path
    // would report the installed plugin as "installed" while the file is group/other writable.
    let dir = tempfile::tempdir().unwrap();
    let mut storage = open(dir.path());
    let snap = approve_and_stage(&mut storage);
    let manifest = snap.entries[0].manifest_sha256.clone();
    assert_eq!(
        hub::install(&storage, &snap, snap.install_revision, PLUGIN, &manifest),
        Ok("hub_plugin_installed")
    );
    let path = namespace_file(&storage, &manifest);
    assert_eq!(
        fixture().with_approvals(&storage).installed[0].state,
        "installed"
    );
    for mode in [0o644, 0o640, 0o604, 0o400, 0o700] {
        set_mode(&path, mode);
        let before = fs::read(&path).unwrap();
        let current = fixture().with_approvals(&storage);
        assert_eq!(current.installed.len(), 1);
        assert_eq!(current.installed[0].state, "quarantined", "mode {mode:o}");
        // Only the installed record is quarantined; the Hub itself keeps its verified status.
        assert_eq!(current.status, "verified", "mode {mode:o}");
        assert_eq!(fs::read(&path).unwrap(), before, "mode {mode:o}");
        assert_eq!(mode_of(&path), mode);
    }
}

#[test]
fn duplicate_plugin_approval_records_quarantine_the_hub() {
    // Kills M21: removing the unique-plugin_id rule in Approvals::validate lets a hand-edited
    // file with two records for one plugin keep the Hub verified.
    let dir = tempfile::tempdir().unwrap();
    let storage = open(dir.path());
    approve_fixture(&storage);
    let path = root(dir.path()).join("hub-approvals.json");
    assert_eq!(fixture().with_approvals(&storage).status, "verified");
    let mut value: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    let first = value["records"][0].clone();
    assert!(first.is_object(), "approval record shape: {value}");
    value["records"].as_array_mut().unwrap().push(first);
    fs::write(&path, serde_json::to_vec(&value).unwrap()).unwrap();
    set_mode(&path, 0o600);
    let snap = fixture().with_approvals(&storage);
    assert_eq!(snap.status, "quarantined");
}

#[test]
fn pending_import_loosened_mid_import_refuses_finish() {
    // Kills M22: removing the descriptor mode check inside finish_import publishes a payload
    // from a pending file another user could have written during the import.
    let dir = tempfile::tempdir().unwrap();
    let mut storage = open(dir.path());
    let snap = approve_fixture(&storage);
    let manifest = snap.entries[0].manifest_sha256.clone();
    // 0644/0640 are refused by validate_opened_private; 0400 only by the exact-0600 check.
    for (round, mode) in [0o644, 0o400].into_iter().enumerate() {
        let id = format!("upload{round}");
        begin(&mut storage, &snap, &id).unwrap();
        hub::chunk_import(&mut storage, &id, 0, PAYLOAD_HEX).unwrap();
        let pending = storage.root.join(format!(".hub-{manifest}.pending"));
        assert_eq!(mode_of(&pending), 0o600);
        set_mode(&pending, mode);
        assert_eq!(
            hub::finish_import(&mut storage, &snap, &id),
            Err("hub_storage_error"),
            "mode {mode:o}"
        );
        assert!(!payload_path(&storage, &manifest).exists(), "mode {mode:o}");
        assert!(!fixture().with_approvals(&storage).entries[0].payload_staged);
    }
}

#[test]
fn begin_and_chunk_refusals_report_exact_reasons() {
    // Exact-reason negatives (storage/hub). Each mutant that reorders or drops a guard turns one
    // of these reasons into a different one or into Ok.
    let dir = tempfile::tempdir().unwrap();
    let mut storage = open(dir.path());
    // Not approved yet: begin refuses before creating any pending file.
    let unapproved = fixture().with_approvals(&storage);
    assert_eq!(
        begin(&mut storage, &unapproved, "upload"),
        Err("permissions_not_approved")
    );
    let snap = approve_fixture(&storage);
    let e = snap.entries[0].clone();
    assert_eq!(
        hub::begin_import(
            &mut storage,
            &snap,
            snap.approval_revision + 1,
            &e.plugin_id,
            &e.manifest_sha256,
            "upload",
            std::time::Instant::now()
        ),
        Err("stale_hub_revision")
    );
    assert_eq!(
        hub::begin_import(
            &mut storage,
            &snap,
            snap.approval_revision,
            &e.plugin_id,
            &"0".repeat(64),
            "upload",
            std::time::Instant::now()
        ),
        Err("manifest_mismatch")
    );
    assert_eq!(
        begin(&mut storage, &snap, "bad/id"),
        Err("invalid_import_id")
    );
    assert_eq!(begin(&mut storage, &snap, "upload"), Ok(()));
    assert_eq!(begin(&mut storage, &snap, "second"), Err("hub_import_busy"));
    assert_eq!(
        hub::chunk_import(&mut storage, "upload", 1, PAYLOAD_HEX),
        Err("stale_import_offset")
    );
    assert_eq!(
        hub::chunk_import(&mut storage, "upload", 0, "abc"),
        Err("invalid_import_chunk")
    );
    assert_eq!(
        hub::chunk_import(&mut storage, "other", 0, PAYLOAD_HEX),
        Err("stale_import")
    );
    // One byte more than the catalog size: the import is dropped, nothing is published.
    let oversized = format!("{PAYLOAD_HEX}00");
    assert_eq!(
        hub::chunk_import(&mut storage, "upload", 0, &oversized),
        Err("payload_size_mismatch")
    );
    assert!(hub::import_deadline(&storage).is_none());
    assert!(!payload_path(&storage, &e.manifest_sha256).exists());
}

#[test]
fn finish_and_install_refusals_report_exact_reasons() {
    // Exact-reason negatives for finish/install. Hash-mismatch uses same-length bytes so only
    // the digest check can refuse it.
    let dir = tempfile::tempdir().unwrap();
    let mut storage = open(dir.path());
    let snap = approve_fixture(&storage);
    let manifest = snap.entries[0].manifest_sha256.clone();
    // Install before any payload is staged.
    assert_eq!(
        hub::install(
            &storage,
            &fixture().with_approvals(&storage),
            0,
            PLUGIN,
            &manifest
        ),
        Err("payload_not_staged")
    );
    begin(&mut storage, &snap, "upload").unwrap();
    assert_eq!(
        hub::finish_import(&mut storage, &snap, "other"),
        Err("stale_import")
    );
    hub::chunk_import(&mut storage, "upload", 0, TAMPERED_HEX).unwrap();
    assert_eq!(
        hub::finish_import(&mut storage, &snap, "upload"),
        Err("payload_hash_mismatch")
    );
    assert!(!payload_path(&storage, &manifest).exists());
    // Stage the real bytes, then check install's exact refusals.
    begin(&mut storage, &snap, "again").unwrap();
    hub::chunk_import(&mut storage, "again", 0, PAYLOAD_HEX).unwrap();
    hub::finish_import(&mut storage, &snap, "again").unwrap();
    let staged = fixture().with_approvals(&storage);
    assert_eq!(
        hub::install(
            &storage,
            &staged,
            staged.install_revision + 3,
            PLUGIN,
            &manifest
        ),
        Err("stale_install_revision")
    );
    assert_eq!(
        hub::install(&storage, &staged, 0, PLUGIN, &"0".repeat(64)),
        Err("manifest_mismatch")
    );
    assert_eq!(
        hub::install(&storage, &staged, 0, "no_such_plugin", &manifest),
        Err("unknown_plugin")
    );
    assert!(!namespace_file(&storage, &manifest).exists());
}

#[test]
fn approval_exact_reasons_for_unknown_and_repeated_plugins() {
    // Exact reasons for approve: unknown plugin and a second approval of the same manifest.
    let dir = tempfile::tempdir().unwrap();
    let storage = open(dir.path());
    let snap = fixture().with_approvals(&storage);
    let e = snap.entries[0].clone();
    assert_eq!(
        hub::approve(
            &storage,
            &snap,
            0,
            "no_such_plugin",
            &e.manifest_sha256,
            &e.permissions,
            true
        ),
        Err("unknown_plugin")
    );
    assert_eq!(
        hub::approve(
            &storage,
            &snap,
            0,
            &e.plugin_id,
            &e.manifest_sha256,
            &e.permissions,
            false
        ),
        Err("publisher_ack_required")
    );
    approve_fixture(&storage);
    let now = fixture().with_approvals(&storage);
    assert_eq!(
        hub::approve(
            &storage,
            &now,
            now.approval_revision,
            &e.plugin_id,
            &e.manifest_sha256,
            &e.permissions,
            true
        ),
        Err("already_approved")
    );
    // Storage negative: a symlinked approvals file is refused and never followed.
    let target = dir.path().join("target");
    fs::write(&target, b"untouched").unwrap();
    fs::remove_file(root(dir.path()).join("hub-approvals.json")).unwrap();
    symlink(&target, root(dir.path()).join("hub-approvals.json")).unwrap();
    assert_eq!(fs::read(&target).unwrap(), b"untouched");
    assert_eq!(fixture().with_approvals(&storage).status, "quarantined");
}
