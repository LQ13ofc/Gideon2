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

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PreviousPreferences {
    pub audible_feedback: bool,
    pub session_timeout_ms: u64,
}
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub version: u16,
    pub session_timeout_ms: u64,
    #[serde(default)]
    pub wake_phrase: Option<String>,
    #[serde(default)]
    pub revision: u64,
    #[serde(default = "enabled")]
    pub audible_feedback: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub previous_preferences: Option<PreviousPreferences>,
}
fn enabled() -> bool {
    true
}
impl Default for Config {
    fn default() -> Self {
        Self {
            version: 1,
            session_timeout_ms: 30000,
            wake_phrase: None,
            revision: 0,
            audible_feedback: true,
            previous_preferences: None,
        }
    }
}
impl Config {
    pub fn validate(&self) -> io::Result<()> {
        if self.version != 1
            || !(50..=60000).contains(&self.session_timeout_ms)
            || self
                .previous_preferences
                .as_ref()
                .is_some_and(|p| !(50..=60000).contains(&p.session_timeout_ms))
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
    /// Same-directory atomic replacement; no client paths or retained speech data.
    fn replace(&self, name: &str, config: &Config) -> io::Result<()> {
        config.validate()?;
        let path = self.root.join(name);
        if fs::symlink_metadata(&path).is_ok() {
            private_metadata(&path, false)?;
        }
        let temporary = self.root.join(format!(".{name}.pending"));
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&temporary)?;
        let result = (|| {
            file.write_all(&serde_json::to_vec(config)?)?;
            file.sync_all()?;
            fs::rename(&temporary, &path)
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temporary);
        }
        result
    }
    pub fn update_preferences(
        &mut self,
        revision: u64,
        audible: bool,
        timeout_ms: u64,
    ) -> io::Result<()> {
        if revision != self.config.revision {
            return Err(io::Error::other("stale revision"));
        }
        let mut next = self.config.clone();
        next.revision = revision
            .checked_add(1)
            .ok_or_else(|| io::Error::other("revision exhausted"))?;
        next.audible_feedback = audible;
        next.session_timeout_ms = timeout_ms;
        next.validate()?;
        next.previous_preferences = Some(PreviousPreferences {
            audible_feedback: self.config.audible_feedback,
            session_timeout_ms: self.config.session_timeout_ms,
        });
        self.replace("config.json", &next)?;
        // Reflect the committed rename even if directory durability reporting fails.
        self.config = next;
        File::open(&self.root)?.sync_all()
    }
    pub fn rollback_preferences(&mut self, revision: u64) -> io::Result<()> {
        if revision != self.config.revision {
            return Err(io::Error::other("stale revision"));
        }
        let previous = self
            .config
            .previous_preferences
            .clone()
            .ok_or_else(|| io::Error::other("no previous preferences"))?;
        self.update_preferences(
            revision,
            previous.audible_feedback,
            previous.session_timeout_ms,
        )
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
