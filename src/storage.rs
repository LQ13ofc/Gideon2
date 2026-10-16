use serde::{Deserialize, Serialize};
use std::{
    fs::{self, File, OpenOptions},
    io::{self, Read, Write},
    os::unix::{
        fs::{FileTypeExt, MetadataExt, OpenOptionsExt, PermissionsExt},
        io::AsRawFd,
    },
    path::{Path, PathBuf},
};

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PreviousPreferences {
    #[serde(default)]
    pub wake_phrase: Option<String>,
    pub audible_feedback: bool,
    #[serde(default = "enabled")]
    pub visual_feedback: bool,
    #[serde(default = "full_volume")]
    pub output_volume_percent: u8,
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
    #[serde(default = "enabled")]
    pub visual_feedback: bool,
    #[serde(default = "full_volume")]
    pub output_volume_percent: u8,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub previous_preferences: Option<PreviousPreferences>,
}
fn full_volume() -> u8 {
    100
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
            visual_feedback: true,
            output_volume_percent: 100,
            previous_preferences: None,
        }
    }
}
impl Config {
    pub fn validate(&self) -> io::Result<()> {
        if self.version != 1
            || self.output_volume_percent > 100
            || !(50..=60000).contains(&self.session_timeout_ms)
            || self.previous_preferences.as_ref().is_some_and(|p| {
                p.output_volume_percent > 100
                    || !(50..=60000).contains(&p.session_timeout_ms)
                    || p.wake_phrase
                        .as_deref()
                        .is_some_and(|id| !crate::protocol::valid_id(id))
            })
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
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ConfigurationStatus {
    Ready,
    SafeMode,
    RestartRequired,
}
/// Private C0 plugin ledger: enabled ids only; authority still comes from Hub approvals.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PluginState {
    pub version: u16,
    pub revision: u64,
    pub enabled: Vec<String>,
}
impl Default for PluginState {
    fn default() -> Self {
        Self {
            version: 1,
            revision: 0,
            enabled: vec![],
        }
    }
}
impl PluginState {
    pub fn validate(&self) -> io::Result<()> {
        let unique: std::collections::HashSet<_> = self.enabled.iter().collect();
        if self.version != 1
            || self.enabled.len() > 8
            || unique.len() != self.enabled.len()
            || self.enabled.iter().any(|id| !crate::protocol::valid_id(id))
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "invalid plugin state",
            ));
        }
        Ok(())
    }
}
pub struct Storage {
    pub root: PathBuf,
    pub config: Config,
    pub configuration_status: ConfigurationStatus,
    invalid_config: Option<Vec<u8>>,
    _lock: File,
    pub(crate) hub_import: Option<crate::hub::Import>,
}
pub(crate) fn private_metadata(path: &Path, directory: bool) -> io::Result<()> {
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
    validate_opened_private(&file)?;
    Ok(file)
}
pub(crate) fn validate_opened_private(file: &File) -> io::Result<()> {
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
    Ok(())
}
fn read_config_bytes(path: &Path) -> io::Result<Vec<u8>> {
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)?;
    validate_opened_private(&file)?;
    if file.metadata()?.len() > 4096 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "config too large",
        ));
    }
    let mut bytes = Vec::new();
    file.take(4097).read_to_end(&mut bytes)?;
    if bytes.len() > 4096 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "config too large",
        ));
    }
    Ok(bytes)
}
impl Storage {
    pub fn open(root: &Path) -> io::Result<Self> {
        Self::open_mode(root, false)
    }
    pub fn open_for_runtime(root: &Path) -> io::Result<Self> {
        Self::open_mode(root, true)
    }
    fn open_mode(root: &Path, allow_safe: bool) -> io::Result<Self> {
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
        let mut invalid_config = None;
        let mut configuration_status = ConfigurationStatus::Ready;
        let config = match fs::symlink_metadata(&path) {
            Ok(_) => {
                private_metadata(&path, false)?;
                // Unsafe files and I/O errors never become content recovery.
                let bytes = match read_config_bytes(&path) {
                    Ok(bytes) => Some(bytes),
                    Err(error) if allow_safe && error.kind() == io::ErrorKind::InvalidData => None,
                    Err(error) => return Err(error),
                };
                let parsed = bytes
                    .as_ref()
                    .and_then(|bytes| serde_json::from_slice::<Config>(bytes).ok())
                    .filter(|config| config.validate().is_ok());
                match parsed {
                    Some(config) => config,
                    None if allow_safe => {
                        configuration_status = ConfigurationStatus::SafeMode;
                        invalid_config = bytes;
                        Config::default()
                    }
                    None => {
                        return Err(io::Error::new(io::ErrorKind::InvalidData, "invalid config"))
                    }
                }
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                let config = Config::default();
                let mut file = OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .mode(0o600)
                    .custom_flags(libc::O_NOFOLLOW)
                    .open(path)?;
                file.write_all(&serde_json::to_vec(&config)?)?;
                file.sync_all()?;
                File::open(&root)?.sync_all()?;
                config
            }
            Err(error) => return Err(error),
        };
        Ok(Self {
            root,
            config,
            configuration_status,
            invalid_config,
            _lock: lock,
            hub_import: None,
        })
    }
    /// Same-directory atomic replacement; no client paths or retained speech data.
    fn replace(&self, name: &str, config: &Config) -> io::Result<()> {
        config.validate()?;
        self.replace_json(name, &serde_json::to_vec(config)?)
    }
    fn replace_json(&self, name: &str, bytes: &[u8]) -> io::Result<()> {
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
            file.write_all(bytes)?;
            file.sync_all()?;
            fs::rename(&temporary, &path)
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temporary);
        }
        result
    }
    pub(crate) fn hub_approvals(&self) -> io::Result<crate::hub::Approvals> {
        let path = self.root.join("hub-approvals.json");
        let file = match OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(&path)
        {
            Ok(file) => file,
            Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(Default::default()),
            Err(e) => return Err(e),
        };
        validate_opened_private(&file)?;
        let mut bytes = Vec::new();
        file.take(16385).read_to_end(&mut bytes)?;
        if bytes.len() > 16384 {
            return Err(io::Error::other("Hub approvals too large"));
        }
        let state: crate::hub::Approvals = serde_json::from_slice(&bytes)?;
        state.validate()?;
        Ok(state)
    }
    pub(crate) fn save_hub_approvals(&self, state: &crate::hub::Approvals) -> io::Result<()> {
        state.validate()?;
        self.replace_json("hub-approvals.json", &serde_json::to_vec(state)?)?;
        File::open(&self.root)?.sync_all()
    }
    pub(crate) fn hub_installed(&self) -> io::Result<crate::hub::InstalledLedger> {
        let path = self.root.join("hub-installed.json");
        let file = match OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(&path)
        {
            Ok(file) => file,
            Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(Default::default()),
            Err(e) => return Err(e),
        };
        validate_opened_private(&file)?;
        let mut bytes = Vec::new();
        file.take(16385).read_to_end(&mut bytes)?;
        if bytes.len() > 16384 {
            return Err(io::Error::other("Hub installed ledger too large"));
        }
        let ledger: crate::hub::InstalledLedger = serde_json::from_slice(&bytes)?;
        ledger.validate()?;
        Ok(ledger)
    }
    pub(crate) fn save_hub_installed(
        &self,
        ledger: &crate::hub::InstalledLedger,
    ) -> io::Result<()> {
        ledger.validate()?;
        self.replace_json("hub-installed.json", &serde_json::to_vec(ledger)?)?;
        File::open(&self.root)?.sync_all()
    }
    pub(crate) fn plugin_state(&self) -> io::Result<PluginState> {
        let path = self.root.join("plugin-state.json");
        let file = match OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(&path)
        {
            Ok(file) => file,
            Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(Default::default()),
            Err(e) => return Err(e),
        };
        validate_opened_private(&file)?;
        let mut bytes = Vec::new();
        file.take(16385).read_to_end(&mut bytes)?;
        if bytes.len() > 16384 {
            return Err(io::Error::other("plugin state too large"));
        }
        let state: PluginState = serde_json::from_slice(&bytes)?;
        state.validate()?;
        Ok(state)
    }
    pub(crate) fn save_plugin_state(&self, state: &PluginState) -> io::Result<()> {
        state.validate()?;
        self.replace_json("plugin-state.json", &serde_json::to_vec(state)?)?;
        File::open(&self.root)?.sync_all()
    }
    pub fn update_preferences(
        &mut self,
        revision: u64,
        audible: bool,
        timeout_ms: u64,
    ) -> io::Result<()> {
        if self.configuration_status != ConfigurationStatus::Ready {
            return Err(io::Error::other("configuration not ready"));
        }
        if revision != self.config.revision {
            return Err(io::Error::other("stale revision"));
        }
        let mut next = self.config.clone();
        next.revision = revision
            .checked_add(1)
            .ok_or_else(|| io::Error::other("revision exhausted"))?;
        next.audible_feedback = audible;
        next.session_timeout_ms = timeout_ms;
        self.commit_preferences(next)
    }
    fn commit_preferences(&mut self, mut next: Config) -> io::Result<()> {
        next.validate()?;
        next.previous_preferences = Some(PreviousPreferences {
            wake_phrase: self.config.wake_phrase.clone(),
            audible_feedback: self.config.audible_feedback,
            visual_feedback: self.config.visual_feedback,
            output_volume_percent: self.config.output_volume_percent,
            session_timeout_ms: self.config.session_timeout_ms,
        });
        let changed_wake = next.wake_phrase != self.config.wake_phrase;
        self.replace("config.json", &next)?;
        self.config = next;
        if changed_wake {
            self.configuration_status = ConfigurationStatus::RestartRequired;
        }
        File::open(&self.root)?.sync_all()
    }
    pub fn update_feedback(&mut self, revision: u64, visual: bool, volume: u8) -> io::Result<()> {
        if self.configuration_status != ConfigurationStatus::Ready
            || revision != self.config.revision
        {
            return Err(io::Error::other("configuration not ready"));
        }
        let mut next = self.config.clone();
        next.visual_feedback = visual;
        next.output_volume_percent = volume;
        next.revision = revision
            .checked_add(1)
            .ok_or_else(|| io::Error::other("revision exhausted"))?;
        self.commit_preferences(next)
    }
    pub fn select_wake(&mut self, revision: u64, phrase_id: String) -> io::Result<()> {
        if self.configuration_status != ConfigurationStatus::Ready
            || revision != self.config.revision
        {
            return Err(io::Error::other("configuration not ready"));
        }
        let mut next = self.config.clone();
        next.wake_phrase = Some(phrase_id);
        next.revision = revision
            .checked_add(1)
            .ok_or_else(|| io::Error::other("revision exhausted"))?;
        self.commit_preferences(next)
    }
    pub fn rollback_preferences(&mut self, revision: u64) -> io::Result<()> {
        if self.configuration_status != ConfigurationStatus::Ready
            || revision != self.config.revision
        {
            return Err(io::Error::other("configuration not ready"));
        }
        let previous = self
            .config
            .previous_preferences
            .clone()
            .ok_or_else(|| io::Error::other("no previous preferences"))?;
        let next = Config {
            revision: revision
                .checked_add(1)
                .ok_or_else(|| io::Error::other("revision exhausted"))?,
            wake_phrase: previous.wake_phrase,
            audible_feedback: previous.audible_feedback,
            visual_feedback: previous.visual_feedback,
            output_volume_percent: previous.output_volume_percent,
            session_timeout_ms: previous.session_timeout_ms,
            ..self.config.clone()
        };
        self.commit_preferences(next)
    }
    pub fn incompatible_configuration(&mut self) -> io::Result<()> {
        self.invalid_config = Some(read_config_bytes(&self.root.join("config.json"))?);
        self.config = Config::default();
        self.configuration_status = ConfigurationStatus::SafeMode;
        Ok(())
    }
    pub fn recovery_available(&self) -> bool {
        self.configuration_status == ConfigurationStatus::SafeMode && self.invalid_config.is_some()
    }
    pub fn set_safe_epoch(&mut self, epoch: u64) {
        if self.configuration_status == ConfigurationStatus::SafeMode {
            self.config.revision = epoch;
        }
    }
    pub fn recover_configuration(&mut self, revision: u64) -> io::Result<()> {
        if revision != self.config.revision || !self.recovery_available() {
            return Err(io::Error::other("recovery unavailable"));
        }
        let invalid = self
            .invalid_config
            .as_ref()
            .expect("bounded invalid configuration");
        if read_config_bytes(&self.root.join("config.json"))? != *invalid {
            return Err(io::Error::other("configuration changed"));
        }
        let next = Config {
            revision: revision
                .checked_add(1)
                .ok_or_else(|| io::Error::other("revision exhausted"))?,
            ..Config::default()
        };
        // Do not overwrite an existing recovery artifact or a hostile link.
        let preserved = self.root.join("config.invalid.json");
        match fs::symlink_metadata(&preserved) {
            Ok(_) => {
                if read_config_bytes(&preserved)? != *invalid {
                    return Err(io::Error::other("recovery artifact conflict"));
                }
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                let mut file = OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .mode(0o600)
                    .custom_flags(libc::O_NOFOLLOW)
                    .open(&preserved)?;
                let result = file.write_all(invalid).and_then(|()| file.sync_all());
                if let Err(error) = result {
                    // This create_new succeeded here; leave the original config untouched.
                    let _ = fs::remove_file(&preserved);
                    return Err(error);
                }
            }
            Err(error) => return Err(error),
        }
        // Make preservation durable before replacing the invalid config.
        File::open(&self.root)?.sync_all()?;
        self.replace("config.json", &next)?;
        self.config = next;
        self.configuration_status = ConfigurationStatus::RestartRequired;
        self.invalid_config = None;
        File::open(&self.root)?.sync_all()
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

impl Drop for Storage {
    fn drop(&mut self) {
        self.hub_import.take();
    }
}
