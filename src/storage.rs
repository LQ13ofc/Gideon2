use serde::{Deserialize, Serialize};
use std::{
    fs::{self, File, OpenOptions},
    io::{self, Write},
    os::unix::{
        fs::{FileTypeExt, MetadataExt, OpenOptionsExt, PermissionsExt},
        io::AsRawFd,
    },
    path::{Path, PathBuf},
};

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub version: u16,
    pub session_timeout_ms: u64,
    #[serde(default)]
    pub wake_phrase: Option<String>,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            version: 1,
            session_timeout_ms: 30000,
            wake_phrase: None,
        }
    }
}
impl Config {
    pub fn validate(&self) -> io::Result<()> {
        if self.version != 1
            || !(50..=60000).contains(&self.session_timeout_ms)
            || self
                .wake_phrase
                .as_deref()
                .is_some_and(|id| !crate::protocol::valid_id(id))
        {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "invalid config"));
        }
        Ok(())
    }
}
pub struct Storage {
    pub root: PathBuf,
    pub config: Config,
    _lock: File,
}
fn private_metadata(path: &Path, directory: bool) -> io::Result<()> {
    let m = fs::symlink_metadata(path)?;
    // SAFETY: getuid has no preconditions and does not alter host state.
    let uid = unsafe { libc::getuid() };
    if m.file_type().is_symlink()
        || m.uid() != uid
        || m.mode() & 0o077 != 0
        || (directory && !m.is_dir())
        || (!directory && (!m.is_file() || m.nlink() != 1))
    {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "unsafe private path",
        ));
    }
    Ok(())
}
fn open_private(path: &Path) -> io::Result<File> {
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)?;
    let m = file.metadata()?;
    // Validate the opened inode, not just a potentially replaced directory entry.
    // SAFETY: getuid is a read-only process identity query.
    if !m.is_file()
        || m.nlink() != 1
        || m.uid() != unsafe { libc::getuid() }
        || m.mode() & 0o077 != 0
    {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "unsafe opened private file",
        ));
    }
    Ok(file)
}
impl Storage {
    pub fn open(root: &Path) -> io::Result<Self> {
        if !root.is_absolute() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "absolute isolated root required",
            ));
        }
        if !root.exists() {
            fs::DirBuilder::new().create(root)?;
            fs::set_permissions(root, fs::Permissions::from_mode(0o700))?;
        }
        private_metadata(root, true)?;
        let root = root.canonicalize()?;
        let lock = open_private(&root.join("core.lock"))?;
        private_metadata(&root.join("core.lock"), false)?;
        // SAFETY: lock remains alive for the lifetime of Storage.
        if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(io::Error::new(
                io::ErrorKind::AddrInUse,
                "core already running",
            ));
        }
        let path = root.join("config.json");
        let config = if path.exists() {
            private_metadata(&path, false)?;
            if fs::metadata(&path)?.len() > 4096 {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "config too large",
                ));
            }
            serde_json::from_slice::<Config>(&fs::read(path)?)?
        } else {
            let cfg = Config::default();
            let mut f = OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o600)
                .open(path)?;
            f.write_all(&serde_json::to_vec(&cfg)?)?;
            f.sync_all()?;
            cfg
        };
        config.validate()?;
        Ok(Self {
            root,
            config,
            _lock: lock,
        })
    }
    pub fn socket_path(&self) -> PathBuf {
        self.root.join("core.sock")
    }
    pub fn clear_stale_socket(&self) -> io::Result<()> {
        let path = self.socket_path();
        if let Ok(m) = fs::symlink_metadata(&path) {
            if !m.file_type().is_socket() {
                return Err(io::Error::new(
                    io::ErrorKind::PermissionDenied,
                    "unexpected socket path",
                ));
            }
            fs::remove_file(path)?;
        }
        Ok(())
    }
    /// Metadata only: no PCM, transcript, arbitrary client ID or arguments in logs.
    pub fn audit(&self, sequence: u64) -> io::Result<()> {
        let path = self.root.join("audit.log");
        let mut f = open_private(&path)?;
        private_metadata(&path, false)?;
        if f.metadata()?.len() >= 65536 {
            f.set_len(0)?;
        }
        use std::io::{Seek, SeekFrom};
        f.seek(SeekFrom::End(0))?;
        writeln!(f, "{{\"version\":1,\"sequence\":{sequence}}}")
    }
}
