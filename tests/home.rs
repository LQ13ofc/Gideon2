use gideon_base::transport::{home, validate_home};
use std::path::Path;

#[test]
fn default_home_is_manifest_dir() {
    assert_eq!(home(), Path::new(env!("CARGO_MANIFEST_DIR")));
}

#[test]
fn validation_accepts_absolute_real_directory() {
    let dir = tempfile::tempdir().unwrap();
    let accepted = validate_home(dir.path()).unwrap();
    assert_eq!(accepted, dir.path());
}

#[test]
fn validation_rejects_relative_file_symlink_and_missing_paths() {
    let dir = tempfile::tempdir().unwrap();
    let file = dir.path().join("regular");
    std::fs::write(&file, b"x").unwrap();
    let link = dir.path().join("link");
    std::os::unix::fs::symlink(dir.path(), &link).unwrap();

    for rejected in [
        Path::new("relative/dir").to_path_buf(),
        Path::new(".").to_path_buf(),
        file,
        link,
        dir.path().join("missing"),
    ] {
        let error = validate_home(&rejected).unwrap_err();
        assert_eq!(error.to_string(), "invalid --home", "{rejected:?}");
    }
}
