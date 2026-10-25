//! DIAG-01 (WP15): the pack digest is the SHA-256 of the definition file that `pack::load` reads, and the
//! snapshot carries it as `pack_sha256`.
use gideon_base::pack;
use sha2::{Digest, Sha256};
use std::{fs, os::unix::fs::symlink, path::Path};

fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[test]
fn definition_digest_is_the_sha256_of_the_file_bytes() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("pack.json");
    let bytes = br#"{"version":1,"id":"demo"}"#;
    fs::write(&path, bytes).unwrap();
    let digest = pack::definition_sha256(&path).unwrap();
    assert_eq!(digest, sha(bytes));
    assert_eq!(digest.len(), 64);
    assert!(digest
        .bytes()
        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)));
}

#[test]
fn a_changed_definition_has_a_different_digest() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("pack.json");
    fs::write(&path, br#"{"version":1,"id":"demo"}"#).unwrap();
    let before = pack::definition_sha256(&path).unwrap();
    // Whitespace alone is a different file: the digest pins bytes, not meaning.
    fs::write(&path, br#"{"version":1,"id":"demo"} "#).unwrap();
    assert_ne!(pack::definition_sha256(&path).unwrap(), before);
}

#[test]
fn relative_missing_symlinked_and_oversize_definitions_are_refused() {
    let dir = tempfile::tempdir().unwrap();
    let real = dir.path().join("pack.json");
    fs::write(&real, b"{}").unwrap();
    // Relative path: refused before any read.
    assert!(pack::definition_sha256(Path::new("pack.json")).is_err());
    // Missing file.
    assert!(pack::definition_sha256(&dir.path().join("missing.json")).is_err());
    // Symlink: never followed (O_NOFOLLOW).
    let link = dir.path().join("link.json");
    symlink(&real, &link).unwrap();
    assert!(pack::definition_sha256(&link).is_err());
    // Over the 1 MiB cap.
    let big = dir.path().join("big.json");
    fs::write(&big, vec![b' '; 1_048_577]).unwrap();
    assert!(pack::definition_sha256(&big).is_err());
}

#[test]
fn the_snapshot_serializes_the_pack_digest() {
    let snapshot = pack::Snapshot {
        version: 1,
        id: "demo-pack".into(),
        pack_sha256: sha(b"pack"),
        scope: "dev_virtual_en",
        preflight: "verified",
        engines: Default::default(),
        wake_phrases: Vec::new(),
        active_phrase: None,
        default_phrase: String::new(),
        voice: "Alba",
        language: "en".into(),
        audio_input: "virtual_pcm",
        audio_output: "virtual",
    };
    let value = serde_json::to_value(&snapshot).unwrap();
    assert_eq!(value["pack_sha256"], sha(b"pack").as_str());
}
