use serde::{Deserialize, Serialize};
use std::{
    cell::{Cell, RefCell},
    fs::{self, File, OpenOptions},
    io::{self, Read, Write},
    os::unix::{
        fs::{FileTypeExt, MetadataExt, OpenOptionsExt},
        io::AsRawFd,
    },
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

/// `PartialEq` only: `wake_sensitivity` is a float, so there is no `Eq`.
#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PreviousPreferences {
    #[serde(default)]
    pub wake_phrase: Option<String>,
    /// Wake phrase list before the last change (rollback target). Empty for older ledgers.
    #[serde(default)]
    pub wake_phrases: Vec<crate::phrases::Setting>,
    pub audible_feedback: bool,
    #[serde(default = "enabled")]
    pub visual_feedback: bool,
    #[serde(default = "full_volume")]
    pub output_volume_percent: u8,
    pub session_timeout_ms: u64,
    #[serde(default = "default_wake_sensitivity")]
    pub wake_sensitivity: f32,
    #[serde(default)]
    pub input_conditioning: InputConditioning,
    #[serde(default = "default_audio_device")]
    pub audio_input_device: String,
    #[serde(default = "default_audio_device")]
    pub audio_output_device: String,
    #[serde(default = "default_stt_languages")]
    pub stt_languages: Vec<String>,
    #[serde(default = "default_tts_language")]
    pub tts_language: String,
    #[serde(default = "default_tts_voice")]
    pub tts_voice: String,
}
#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
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
    /// Wake phrase list (`wake_phrases: [{id, active, sensitivity?}]`, at most 5 active). Empty = legacy:
    /// the single `wake_phrase` (or the packaged default) is the list. Written together with `wake_phrase`.
    #[serde(default)]
    pub wake_phrases: Vec<crate::phrases::Setting>,
    /// Wake threshold scale in `WAKE_SENSITIVITY_MIN..=WAKE_SENSITIVITY_MAX`; see `wake::accept_threshold`.
    #[serde(default = "default_wake_sensitivity")]
    pub wake_sensitivity: f32,
    /// Input conditioning of the wake spotter (`auto` default, `off`). Strict: other values fail to load.
    #[serde(default)]
    pub input_conditioning: InputConditioning,
    /// Preferred capture device name (`default` = system default). Bounded by `valid_audio_device`.
    #[serde(default = "default_audio_device")]
    pub audio_input_device: String,
    /// Preferred playback device name (`default` = system default). Bounded by `valid_audio_device`.
    #[serde(default = "default_audio_device")]
    pub audio_output_device: String,
    /// Consent to listen to the microphone continuously (A6). Off by default. A Core that starts with
    /// it on runs the live recorder and wake worker instead of the boot replay; a change applies at the
    /// next start (`restart_required` in `audio.live`). Rollback keeps the current value: an older
    /// record never re-grants consent. Restoring defaults turns it off.
    #[serde(default)]
    pub live_audio: bool,
    /// Consent to run the fixed command table on the host (A11, docs/A11-real-actions-test.md): open listed
    /// applications and change the default audio sink. Off by default; strict bool; applies at once (no restart).
    /// Sessions and queued jobs block the change (`busy`). Off keeps the sandbox executor.
    #[serde(default)]
    pub real_actions: bool,
    /// Languages the STT worker transcribes (1..=3, installed languages only). Old ledgers load as English.
    #[serde(default = "default_stt_languages")]
    pub stt_languages: Vec<String>,
    /// Language the TTS worker speaks, and its voice. Changes apply at the next Core start.
    #[serde(default = "default_tts_language")]
    pub tts_language: String,
    #[serde(default = "default_tts_voice")]
    pub tts_voice: String,
    /// CFG-04 retention of the timeline and of the persisted audit trail. Applies at once (`purge_history`).
    #[serde(default)]
    pub history_retention: HistoryRetention,
    /// DIAG-02 developer mode of the diagnostics. Strict bool; no consent and no authority is attached to it.
    #[serde(default)]
    pub developer_mode: bool,
}
fn default_stt_languages() -> Vec<String> {
    vec![crate::languages::DEFAULT_STT_LANGUAGE.into()]
}
fn default_tts_language() -> String {
    crate::languages::DEFAULT_TTS_LANGUAGE.into()
}
fn default_tts_voice() -> String {
    crate::languages::DEFAULT_TTS_VOICE.into()
}
/// Format only (ledger validity): tags are short ASCII labels, 1..=3 distinct STT tags, a bounded voice id.
/// Whether a language is installed is decided by `languages::LanguageCatalog`, not here.
pub fn valid_languages(stt: &[String], tts_language: &str, tts_voice: &str) -> bool {
    (1..=crate::languages::MAX_STT_LANGUAGES).contains(&stt.len())
        && stt
            .iter()
            .enumerate()
            .all(|(i, tag)| crate::languages::valid_tag(tag) && !stt[..i].contains(tag))
        && crate::languages::valid_tag(tts_language)
        && crate::protocol::valid_id(tts_voice)
}
fn full_volume() -> u8 {
    100
}
fn enabled() -> bool {
    true
}
pub const WAKE_SENSITIVITY_MIN: f32 = 0.5;
pub const WAKE_SENSITIVITY_MAX: f32 = 1.5;
pub const AUDIO_DEVICE_MAX: usize = 128;
pub const DEFAULT_AUDIO_DEVICE: &str = "default";
fn default_wake_sensitivity() -> f32 {
    1.0
}
fn default_audio_device() -> String {
    DEFAULT_AUDIO_DEVICE.into()
}
/// Preference `input_conditioning`: `auto` shapes the frames the wake spotter hears (DC and 100 Hz high-pass,
/// `scripts/audio_conditioning.py`); `off` passes them through. Capture, STT and VAD always get the raw frames.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum InputConditioning {
    #[default]
    Auto,
    Off,
}
impl InputConditioning {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Auto => "auto",
            Self::Off => "off",
        }
    }
}
/// Preference `history_retention` (CFG-04): how long the timeline events and the persisted audit trail are kept.
/// `never` keeps neither: no timeline ring is filled and no audit line is written, and the purge removes the
/// existing audit files. Wire values are exactly these four strings; anything else fails to parse.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Deserialize, Serialize)]
pub enum HistoryRetention {
    #[serde(rename = "days_7")]
    Days7,
    #[default]
    #[serde(rename = "days_30")]
    Days30,
    #[serde(rename = "days_90")]
    Days90,
    #[serde(rename = "never")]
    Never,
}
impl HistoryRetention {
    pub const DAY_MS: u64 = 86_400_000;
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Days7 => "days_7",
            Self::Days30 => "days_30",
            Self::Days90 => "days_90",
            Self::Never => "never",
        }
    }
    /// Retention window in milliseconds; `None` for `never`.
    pub fn window_ms(self) -> Option<u64> {
        match self {
            Self::Days7 => Some(7 * Self::DAY_MS),
            Self::Days30 => Some(30 * Self::DAY_MS),
            Self::Days90 => Some(90 * Self::DAY_MS),
            Self::Never => None,
        }
    }
}
/// Strict range check; NaN and infinities are outside every range and therefore rejected.
pub fn valid_wake_sensitivity(value: f32) -> bool {
    (WAKE_SENSITIVITY_MIN..=WAKE_SENSITIVITY_MAX).contains(&value)
}
/// 1..=128 bytes from `[A-Za-z0-9._:@/+ -]`. Names are labels only: no shell, control or non-ASCII bytes.
pub fn valid_audio_device(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= AUDIO_DEVICE_MAX
        && name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._:@/+ -".contains(&b))
}
/// Optional fields of the `preferences` op: `None` keeps the stored value.
#[derive(Debug, Default, Clone, PartialEq)]
pub struct OptionalPreferences {
    pub wake_sensitivity: Option<f32>,
    pub input_conditioning: Option<InputConditioning>,
    pub audio_input_device: Option<String>,
    pub audio_output_device: Option<String>,
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
            wake_sensitivity: default_wake_sensitivity(),
            input_conditioning: InputConditioning::default(),
            audio_input_device: default_audio_device(),
            audio_output_device: default_audio_device(),
            live_audio: false,
            real_actions: false,
            wake_phrases: Vec::new(),
            stt_languages: default_stt_languages(),
            tts_language: default_tts_language(),
            tts_voice: default_tts_voice(),
            history_retention: HistoryRetention::default(),
            developer_mode: false,
        }
    }
}
impl Config {
    pub fn validate(&self) -> io::Result<()> {
        if self.version != 1
            || self.output_volume_percent > 100
            || !(50..=60000).contains(&self.session_timeout_ms)
            || !valid_wake_sensitivity(self.wake_sensitivity)
            || !valid_audio_device(&self.audio_input_device)
            || !valid_audio_device(&self.audio_output_device)
            || !valid_languages(&self.stt_languages, &self.tts_language, &self.tts_voice)
            || !crate::phrases::valid_settings(&self.wake_phrases)
            || self.previous_preferences.as_ref().is_some_and(|p| {
                !crate::phrases::valid_settings(&p.wake_phrases)
                    || p.output_volume_percent > 100
                    || !(50..=60000).contains(&p.session_timeout_ms)
                    || !valid_wake_sensitivity(p.wake_sensitivity)
                    || !valid_audio_device(&p.audio_input_device)
                    || !valid_audio_device(&p.audio_output_device)
                    || !valid_languages(&p.stt_languages, &p.tts_language, &p.tts_voice)
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
/// Write counters of the ledgers, kept in `hub-generation`. A ledger whose counter is non-zero
/// must still exist: a missing file then means loss or tampering, never a fresh empty ledger
/// with revision 0. Deleting `hub-generation` by hand is the explicit operator reset.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Generations {
    version: u16,
    approvals: u64,
    installed: u64,
    plugin_state: u64,
}
impl Default for Generations {
    fn default() -> Self {
        Self {
            version: 1,
            approvals: 0,
            installed: 0,
            plugin_state: 0,
        }
    }
}
/// Size caps of the private ledgers. `secrets.json` also holds S5 connection tokens (<= 8 accounts).
const SECRETS_LIMIT: u64 = 16384;
/// Audit generations: rotation starts at 64 KiB, so one line can pass the rotation check by a little.
const AUDIT_LIMIT: u64 = 131_072;
const CONNECTIONS_LIMIT: u64 = 131_072;
const REGISTRY_LIMIT: u64 = 4096;
/// Private C1 ledgers: bounded, strict and 0600, read through the same guards as plugin state.
fn read_private_bounded(root: &Path, name: &str, limit: u64) -> io::Result<Option<Vec<u8>>> {
    let path = root.join(name);
    let file = match OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(&path)
    {
        Ok(file) => file,
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(e),
    };
    validate_opened_private(&file)?;
    let mut bytes = Vec::new();
    file.take(limit + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit {
        return Err(io::Error::other("private ledger too large"));
    }
    Ok(Some(bytes))
}
pub struct Storage {
    pub root: PathBuf,
    pub config: Config,
    pub configuration_status: ConfigurationStatus,
    invalid_config: Option<Vec<u8>>,
    _lock: File,
    pub(crate) hub_import: Option<crate::hub::Import>,
    /// Ledger write counters; see `Generations`.
    generations: Cell<Generations>,
    /// Stat-keyed cache of verified Hub payloads; a miss always re-hashes.
    pub(crate) verified: RefCell<crate::hub::VerifiedCache>,
    /// Unreferenced Hub payloads and crashed pending writes moved to quarantine by the startup sweep.
    pub(crate) orphans: u64,
    /// Set by the Core before each control call: the live microphone pipeline runs in this process. A
    /// per-phrase sensitivity change then reaches the wake worker by a restart between sessions (see
    /// `commit_preferences`), so it does not need a Core restart.
    pub live_pipeline: bool,
}
/// `hub-generation` is written after every ledger rename; a damaged marker fails closed.
fn read_generations(root: &Path) -> Generations {
    match read_private_bounded(root, "hub-generation", 512) {
        Ok(None) => Generations::default(),
        Ok(Some(bytes)) => serde_json::from_slice(&bytes)
            .ok()
            .filter(|g: &Generations| g.version == 1)
            .unwrap_or(Generations {
                version: 1,
                approvals: 1,
                installed: 1,
                plugin_state: 1,
            }),
        Err(_) => Generations {
            version: 1,
            approvals: 1,
            installed: 1,
            plugin_state: 1,
        },
    }
}
/// A leftover writer file: regular, single link, owned by us and private.
fn private_leftover(path: &Path) -> bool {
    // SAFETY: getuid is a read-only process identity query.
    let uid = unsafe { libc::getuid() };
    fs::symlink_metadata(path)
        .is_ok_and(|m| m.is_file() && m.nlink() == 1 && m.uid() == uid && m.mode() & 0o777 == 0o600)
}
fn missing_ledger(name: &str) -> io::Error {
    io::Error::new(io::ErrorKind::NotFound, format!("{name} ledger missing"))
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
            // Created 0700 at once: there is no window with the default umask mode.
            use std::os::unix::fs::DirBuilderExt;
            fs::DirBuilder::new().mode(0o700).create(root)?;
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
        // Read before any ledger access, under the lock, so a deleted ledger is detected.
        let generations = Cell::new(read_generations(&root));
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
        let mut storage = Self {
            root,
            config,
            configuration_status,
            invalid_config,
            _lock: lock,
            hub_import: None,
            generations,
            verified: RefCell::new(Default::default()),
            orphans: 0,
            live_pipeline: false,
        };
        storage.sweep();
        Ok(storage)
    }
    /// Startup sweep under the core lock. Crashed `.*.pending` writers and Hub payloads that the
    /// installed ledger does not name are MOVED to `quarantine/` (0700, timestamp suffix), never
    /// deleted. Skipped when the installed ledger cannot be read: no file is guessed to be garbage.
    fn sweep(&mut self) {
        let mut leftovers = vec![];
        if let Ok(entries) = fs::read_dir(&self.root) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().into_owned();
                if name.starts_with('.') && name.ends_with(".pending") {
                    let path = entry.path();
                    if private_leftover(&path) {
                        leftovers.push(path);
                    }
                }
            }
        }
        let mut orphans = 0;
        if let Ok(ledger) = self.hub_installed() {
            let namespace = self.root.join("hub-plugins");
            let referenced = crate::hub::referenced_payload_names(&ledger);
            if let Ok(entries) = fs::read_dir(&namespace) {
                for entry in entries.flatten() {
                    let name = entry.file_name().to_string_lossy().into_owned();
                    if !referenced.contains(&name) && self.quarantine(&entry.path()) {
                        orphans += 1;
                    }
                }
            }
        }
        // Crashed pending writes are orphans too: they count once they are moved, never when they stay.
        for path in leftovers {
            if self.quarantine(&path) {
                orphans += 1;
            }
        }
        self.orphans = orphans;
    }
    /// Moves `path` into `quarantine/` under a timestamped name. Returns true when moved.
    fn quarantine(&self, path: &Path) -> bool {
        use std::os::unix::fs::DirBuilderExt;
        let dir = self.root.join("quarantine");
        if fs::symlink_metadata(&dir).is_err()
            && fs::DirBuilder::new().mode(0o700).create(&dir).is_err()
        {
            return false;
        }
        if private_metadata(&dir, true).is_err() {
            return false;
        }
        let Some(name) = path.file_name().map(|n| n.to_string_lossy().into_owned()) else {
            return false;
        };
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_or(0, |d| d.as_millis());
        for index in 0..1000 {
            let destination = dir.join(format!("{name}.{stamp}.{index}"));
            if fs::symlink_metadata(&destination).is_ok() {
                continue;
            }
            return fs::rename(path, &destination).is_ok();
        }
        false
    }
    /// Advances one ledger counter after its rename, then fsyncs the marker and the root.
    fn bump(&self, field: fn(&mut Generations) -> &mut u64) -> io::Result<()> {
        let mut next = self.generations.get();
        let counter = field(&mut next);
        *counter = counter.saturating_add(1);
        self.replace_json("hub-generation", &serde_json::to_vec(&next)?)?;
        File::open(&self.root)?.sync_all()?;
        self.generations.set(next);
        Ok(())
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
            Err(e) if e.kind() == io::ErrorKind::NotFound => {
                if self.generations.get().approvals > 0 {
                    return Err(missing_ledger("approvals"));
                }
                return Ok(Default::default());
            }
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
        File::open(&self.root)?.sync_all()?;
        self.bump(|g| &mut g.approvals)
    }
    pub(crate) fn hub_installed(&self) -> io::Result<crate::hub::InstalledLedger> {
        let path = self.root.join("hub-installed.json");
        let file = match OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(&path)
        {
            Ok(file) => file,
            Err(e) if e.kind() == io::ErrorKind::NotFound => {
                if self.generations.get().installed > 0 {
                    return Err(missing_ledger("installed"));
                }
                return Ok(Default::default());
            }
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
        File::open(&self.root)?.sync_all()?;
        self.bump(|g| &mut g.installed)
    }
    pub(crate) fn plugin_state(&self) -> io::Result<PluginState> {
        let path = self.root.join("plugin-state.json");
        let file = match OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(&path)
        {
            Ok(file) => file,
            Err(e) if e.kind() == io::ErrorKind::NotFound => {
                if self.generations.get().plugin_state > 0 {
                    return Err(missing_ledger("plugin state"));
                }
                return Ok(Default::default());
            }
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
        File::open(&self.root)?.sync_all()?;
        self.bump(|g| &mut g.plugin_state)
    }
    pub(crate) fn llm_ledger(&self) -> io::Result<crate::llmcfg::LlmLedger> {
        match read_private_bounded(&self.root, "llm-config.json", 4096)? {
            Some(bytes) => Ok(serde_json::from_slice(&bytes)?),
            None => Ok(Default::default()),
        }
    }
    pub(crate) fn save_llm_ledger(&self, ledger: &crate::llmcfg::LlmLedger) -> io::Result<()> {
        self.replace_json("llm-config.json", &serde_json::to_vec(ledger)?)?;
        File::open(&self.root)?.sync_all()
    }
    pub(crate) fn connections_ledger(&self) -> io::Result<crate::connections::Ledger> {
        match read_private_bounded(&self.root, "connections.json", CONNECTIONS_LIMIT)? {
            Some(bytes) => Ok(serde_json::from_slice(&bytes)?),
            None => Ok(Default::default()),
        }
    }
    pub(crate) fn save_connections_ledger(
        &self,
        ledger: &crate::connections::Ledger,
    ) -> io::Result<()> {
        let bytes = serde_json::to_vec(ledger)?;
        if bytes.len() as u64 > CONNECTIONS_LIMIT {
            return Err(io::Error::other("connections ledger too large"));
        }
        self.replace_json("connections.json", &bytes)?;
        File::open(&self.root)?.sync_all()
    }
    /// `registry.json` (S5 E3): the purposes for which the user allowed the visual fallback. Missing means default off.
    pub(crate) fn registry_ledger(&self) -> io::Result<crate::registry::Ledger> {
        match read_private_bounded(&self.root, "registry.json", REGISTRY_LIMIT)? {
            Some(bytes) => Ok(serde_json::from_slice(&bytes)?),
            None => Ok(Default::default()),
        }
    }
    pub(crate) fn save_registry_ledger(&self, ledger: &crate::registry::Ledger) -> io::Result<()> {
        let bytes = serde_json::to_vec(ledger)?;
        if bytes.len() as u64 > REGISTRY_LIMIT {
            return Err(io::Error::other("registry ledger too large"));
        }
        self.replace_json("registry.json", &bytes)?;
        File::open(&self.root)?.sync_all()
    }
    pub(crate) fn llm_secrets(&self) -> io::Result<crate::secrets::Secrets> {
        match read_private_bounded(&self.root, "secrets.json", SECRETS_LIMIT)? {
            Some(bytes) => Ok(serde_json::from_slice(&bytes)?),
            None => Ok(Default::default()),
        }
    }
    pub(crate) fn save_llm_secrets(&self, secrets: &crate::secrets::Secrets) -> io::Result<()> {
        let bytes = serde_json::to_vec(secrets)?;
        if bytes.len() as u64 > SECRETS_LIMIT {
            return Err(io::Error::other("secrets too large"));
        }
        self.replace_json("secrets.json", &bytes)?;
        File::open(&self.root)?.sync_all()
    }
    pub fn update_preferences(
        &mut self,
        revision: u64,
        audible: bool,
        timeout_ms: u64,
    ) -> io::Result<()> {
        self.update_preferences_with(
            revision,
            audible,
            timeout_ms,
            OptionalPreferences::default(),
        )
    }
    pub fn update_preferences_with(
        &mut self,
        revision: u64,
        audible: bool,
        timeout_ms: u64,
        optional: OptionalPreferences,
    ) -> io::Result<()> {
        if !self.writes_open() {
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
        if let Some(sensitivity) = optional.wake_sensitivity {
            next.wake_sensitivity = sensitivity;
        }
        if let Some(conditioning) = optional.input_conditioning {
            next.input_conditioning = conditioning;
        }
        if let Some(device) = optional.audio_input_device {
            next.audio_input_device = device;
        }
        if let Some(device) = optional.audio_output_device {
            next.audio_output_device = device;
        }
        self.commit_preferences(next)
    }
    /// `config.json.bak` keeps the bytes of the file replaced by a restore (one generation, 0600,
    /// atomic). The reset itself is a normal commit: revision + 1, and `previous_preferences` holds
    /// the pre-reset values, so `rollback_preferences` can still undo it.
    pub fn restore_preferences_defaults(&mut self, revision: u64) -> io::Result<()> {
        if !self.writes_open() || revision != self.config.revision {
            return Err(io::Error::other("configuration not ready"));
        }
        let current = read_config_bytes(&self.root.join("config.json"))?;
        self.replace_json("config.json.bak", &current)?;
        File::open(&self.root)?.sync_all()?;
        let next = Config {
            revision: revision
                .checked_add(1)
                .ok_or_else(|| io::Error::other("revision exhausted"))?,
            ..Config::default()
        };
        self.commit_preferences(next)
    }
    fn commit_preferences(&mut self, mut next: Config) -> io::Result<()> {
        next.validate()?;
        next.previous_preferences = Some(PreviousPreferences {
            wake_phrase: self.config.wake_phrase.clone(),
            wake_phrases: self.config.wake_phrases.clone(),
            audible_feedback: self.config.audible_feedback,
            visual_feedback: self.config.visual_feedback,
            output_volume_percent: self.config.output_volume_percent,
            session_timeout_ms: self.config.session_timeout_ms,
            wake_sensitivity: self.config.wake_sensitivity,
            input_conditioning: self.config.input_conditioning,
            audio_input_device: self.config.audio_input_device.clone(),
            audio_output_device: self.config.audio_output_device.clone(),
            stt_languages: self.config.stt_languages.clone(),
            tts_language: self.config.tts_language.clone(),
            tts_voice: self.config.tts_voice.clone(),
        });
        // A change of the active list (ids or active switches) always needs a restart: the worker and the
        // Core's command phrases are fixed at start. A sensitivity-only change needs one too, unless the live
        // pipeline runs: the Core then publishes the new keyword set and the live worker restarts between sessions.
        let active_list = |c: &Config| {
            (
                c.wake_phrase.clone(),
                c.wake_phrases
                    .iter()
                    .map(|p| (p.id.clone(), p.active))
                    .collect::<Vec<_>>(),
            )
        };
        let list_changed = active_list(&next) != active_list(&self.config);
        let sensitivity_changed = next.wake_phrases != self.config.wake_phrases;
        let needs_restart = list_changed || (sensitivity_changed && !self.live_pipeline);
        self.replace("config.json", &next)?;
        // Durable before the in-memory commit: a failed fsync leaves the old state visible.
        File::open(&self.root)?.sync_all()?;
        self.config = next;
        if needs_restart {
            self.configuration_status = ConfigurationStatus::RestartRequired;
        }
        Ok(())
    }
    /// Preference writes are accepted while the configuration is `ready` and while a restart is pending
    /// (`restart_required`): the latest write wins and takes effect at the next start. Safe mode refuses them.
    fn writes_open(&self) -> bool {
        matches!(
            self.configuration_status,
            ConfigurationStatus::Ready | ConfigurationStatus::RestartRequired
        )
    }
    pub fn update_feedback(&mut self, revision: u64, visual: bool, volume: u8) -> io::Result<()> {
        if !self.writes_open() || revision != self.config.revision {
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
    /// Wake phrase list (CAS on `revision`). The legacy `wake_phrase` keeps the first active id so readers of
    /// the old field agree. Catalog and keyword checks happen in the Core (src/phrases.rs) before this call.
    pub fn update_wake_phrases(
        &mut self,
        revision: u64,
        phrases: Vec<crate::phrases::Setting>,
    ) -> io::Result<()> {
        if !self.writes_open()
            || revision != self.config.revision
            || !crate::phrases::valid_settings(&phrases)
        {
            return Err(io::Error::other("configuration not ready"));
        }
        let mut next = self.config.clone();
        next.wake_phrase = phrases.iter().find(|p| p.active).map(|p| p.id.clone());
        next.wake_phrases = phrases;
        next.revision = revision
            .checked_add(1)
            .ok_or_else(|| io::Error::other("revision exhausted"))?;
        self.commit_preferences(next)
    }
    pub fn select_wake(&mut self, revision: u64, phrase_id: String) -> io::Result<()> {
        if !self.writes_open() || revision != self.config.revision {
            return Err(io::Error::other("configuration not ready"));
        }
        let mut next = self.config.clone();
        // The legacy single selection is the whole list now: one active phrase, no sensitivity override.
        next.wake_phrases = vec![crate::phrases::Setting {
            id: phrase_id.clone(),
            active: true,
            sensitivity: None,
        }];
        next.wake_phrase = Some(phrase_id);
        next.revision = revision
            .checked_add(1)
            .ok_or_else(|| io::Error::other("revision exhausted"))?;
        self.commit_preferences(next)
    }
    /// A6 consent switch. CAS on `revision` like every preference; only `live_audio` changes.
    pub fn update_live_audio(&mut self, revision: u64, enabled: bool) -> io::Result<()> {
        if !self.writes_open() || revision != self.config.revision {
            return Err(io::Error::other("configuration not ready"));
        }
        let mut next = self.config.clone();
        next.live_audio = enabled;
        next.revision = revision
            .checked_add(1)
            .ok_or_else(|| io::Error::other("revision exhausted"))?;
        self.commit_preferences(next)
    }
    /// A11 consent switch for host actions. CAS on `revision` like every preference; only `real_actions` changes.
    pub fn update_real_actions(&mut self, revision: u64, enabled: bool) -> io::Result<()> {
        if !self.writes_open() || revision != self.config.revision {
            return Err(io::Error::other("configuration not ready"));
        }
        let mut next = self.config.clone();
        next.real_actions = enabled;
        next.revision = revision
            .checked_add(1)
            .ok_or_else(|| io::Error::other("revision exhausted"))?;
        self.commit_preferences(next)
    }
    /// CFG-04 retention switch (CAS on `revision`); only `history_retention` changes. A purge runs on commit.
    pub fn update_history_retention(
        &mut self,
        revision: u64,
        retention: HistoryRetention,
    ) -> io::Result<()> {
        if !self.writes_open() || revision != self.config.revision {
            return Err(io::Error::other("configuration not ready"));
        }
        let mut next = self.config.clone();
        next.history_retention = retention;
        next.revision = revision
            .checked_add(1)
            .ok_or_else(|| io::Error::other("revision exhausted"))?;
        self.commit_preferences(next)
    }
    /// DIAG-02 developer mode switch (CAS on `revision`); only `developer_mode` changes.
    pub fn update_developer_mode(&mut self, revision: u64, enabled: bool) -> io::Result<()> {
        if !self.writes_open() || revision != self.config.revision {
            return Err(io::Error::other("configuration not ready"));
        }
        let mut next = self.config.clone();
        next.developer_mode = enabled;
        next.revision = revision
            .checked_add(1)
            .ok_or_else(|| io::Error::other("revision exhausted"))?;
        self.commit_preferences(next)
    }
    /// Language switch (CAS on `revision`). Only the three language fields change; the choice takes
    /// effect at the next Core start (the view reports `restart_required` per engine kind).
    pub fn update_languages(
        &mut self,
        revision: u64,
        stt: Vec<String>,
        tts_language: String,
        tts_voice: String,
    ) -> io::Result<()> {
        if !self.writes_open() || revision != self.config.revision {
            return Err(io::Error::other("configuration not ready"));
        }
        let mut next = self.config.clone();
        next.stt_languages = stt;
        next.tts_language = tts_language;
        next.tts_voice = tts_voice;
        next.revision = revision
            .checked_add(1)
            .ok_or_else(|| io::Error::other("revision exhausted"))?;
        self.commit_preferences(next)
    }
    pub fn rollback_preferences(&mut self, revision: u64) -> io::Result<()> {
        if !self.writes_open() || revision != self.config.revision {
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
            wake_phrases: previous.wake_phrases,
            audible_feedback: previous.audible_feedback,
            visual_feedback: previous.visual_feedback,
            output_volume_percent: previous.output_volume_percent,
            session_timeout_ms: previous.session_timeout_ms,
            wake_sensitivity: previous.wake_sensitivity,
            input_conditioning: previous.input_conditioning,
            audio_input_device: previous.audio_input_device,
            audio_output_device: previous.audio_output_device,
            stt_languages: previous.stt_languages,
            tts_language: previous.tts_language,
            tts_voice: previous.tts_voice,
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
        File::open(&self.root)?.sync_all()?;
        self.config = next;
        self.configuration_status = ConfigurationStatus::RestartRequired;
        self.invalid_config = None;
        Ok(())
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
    /// Connection audit: a closed vocabulary only (kind, operation, risk, outcome). No account ids,
    /// arguments, tokens or response content can reach this line.
    pub fn audit_connection(
        &self,
        sequence: u64,
        kind: &str,
        operation: &str,
        risk: &str,
        outcome: &str,
    ) -> io::Result<()> {
        let closed = |text: &str| {
            !text.is_empty()
                && text.len() <= 64
                && text
                    .bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b"_.".contains(&b))
        };
        if ![kind, operation, risk, outcome].iter().all(|t| closed(t)) {
            return Err(io::Error::other("audit vocabulary"));
        }
        self.append_audit(&format!(
            "{{\"version\":1,\"sequence\":{sequence},\"event\":\"{kind}\",\"operation\":\"{operation}\",\"risk\":\"{risk}\",\"outcome\":\"{outcome}\",\"at_ms\":{}}}",
            crate::protocol::unix_ms()
        ))
    }
    /// Metadata only: no PCM, transcript, arbitrary client ID or arguments in logs.
    pub fn audit(&self, sequence: u64) -> io::Result<()> {
        self.append_audit(&format!(
            "{{\"version\":1,\"sequence\":{sequence},\"at_ms\":{}}}",
            crate::protocol::unix_ms()
        ))
    }
    /// CFG-04 purge of the persisted audit trail. Keeps only lines whose `at_ms` is inside the retention window;
    /// lines without a timestamp (older format) are dropped. `never` removes both generations. Each rewrite is
    /// a private temporary file renamed over the original. Returns the number of lines removed.
    pub fn purge_history(&self, now_ms: u64) -> io::Result<usize> {
        let mut removed = 0;
        for name in ["audit.log", "audit.log.1"] {
            removed += self.purge_audit_file(name, now_ms)?;
        }
        Ok(removed)
    }
    fn purge_audit_file(&self, name: &str, now_ms: u64) -> io::Result<usize> {
        let retention = self.config.history_retention;
        let Some(bytes) = read_private_bounded(&self.root, name, AUDIT_LIMIT)? else {
            return Ok(0);
        };
        let cutoff = retention
            .window_ms()
            .map(|window| now_ms.saturating_sub(window));
        let text = String::from_utf8_lossy(&bytes);
        let mut kept = String::new();
        let mut removed = 0;
        for line in text.lines() {
            let at = serde_json::from_str::<serde_json::Value>(line)
                .ok()
                .and_then(|value| value["at_ms"].as_u64());
            let inside = match (cutoff, at) {
                (Some(cutoff), Some(at)) => at >= cutoff,
                _ => false,
            };
            if inside {
                kept.push_str(line);
                kept.push('\n');
            } else {
                removed += 1;
            }
        }
        let path = self.root.join(name);
        if removed == 0 {
            return Ok(0);
        }
        if kept.is_empty() {
            return match fs::remove_file(&path) {
                Ok(()) => Ok(removed),
                Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(removed),
                Err(error) => Err(error),
            };
        }
        // Same-directory temporary name: a crash leaves a `.pending` file that the startup sweep quarantines.
        let temporary = self.root.join(format!(".{name}.pending"));
        let _ = fs::remove_file(&temporary);
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&temporary)?;
        file.write_all(kept.as_bytes())?;
        file.sync_all()?;
        drop(file);
        fs::rename(&temporary, &path)?;
        File::open(&self.root)?.sync_all()?;
        Ok(removed)
    }
    fn append_audit(&self, line: &str) -> io::Result<()> {
        // CFG-04 `never`: nothing is written to the audit trail.
        if self.config.history_retention == HistoryRetention::Never {
            return Ok(());
        }
        let path = self.root.join("audit.log");
        let mut f = open_private(&path)?;
        private_metadata(&path, false)?;
        if f.metadata()?.len() >= 65536 {
            // Keep exactly one previous generation: atomic rename replaces it, nothing is truncated.
            drop(f);
            fs::rename(&path, self.root.join("audit.log.1"))?;
            f = open_private(&path)?;
            private_metadata(&path, false)?;
        }
        use std::io::{Seek, SeekFrom};
        f.seek(SeekFrom::End(0))?;
        writeln!(f, "{line}")
    }
}

/// Per-plugin settings directory under the private root. Survives plugin removal and reinstall;
/// only `plugin_settings_clear` (a user operation) deletes a file.
const SETTINGS_DIR: &str = "plugin-settings";
/// Hard cap of one settings file (envelope included); the Core also caps the data at 8 KiB.
pub const SETTINGS_FILE_LIMIT: u64 = 16 * 1024;

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct SettingsFile {
    version: u16,
    data: serde_json::Value,
}

fn settings_paths(root: &Path, plugin_id: &str) -> io::Result<(PathBuf, PathBuf, PathBuf)> {
    if !crate::protocol::valid_id(plugin_id) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "invalid plugin id",
        ));
    }
    let dir = root.join(SETTINGS_DIR);
    let path = dir.join(format!("{plugin_id}.json"));
    let temporary = dir.join(format!(".{plugin_id}.json.pending"));
    Ok((dir, path, temporary))
}

/// Settings object of `plugin_id`, or `None` when nothing was ever stored. Unsafe or malformed
/// files are errors, never silently replaced.
pub fn plugin_settings_read(root: &Path, plugin_id: &str) -> io::Result<Option<serde_json::Value>> {
    let (dir, path, _) = settings_paths(root, plugin_id)?;
    match fs::symlink_metadata(&dir) {
        Ok(_) => private_metadata(&dir, true)?,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
    }
    let file = match OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(&path)
    {
        Ok(file) => file,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
    };
    validate_opened_private(&file)?;
    let mut bytes = Vec::new();
    file.take(SETTINGS_FILE_LIMIT + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > SETTINGS_FILE_LIMIT {
        return Err(io::Error::other("plugin settings too large"));
    }
    let stored: SettingsFile = serde_json::from_slice(&bytes)?;
    if stored.version != 1 || !stored.data.is_object() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid plugin settings",
        ));
    }
    Ok(Some(stored.data))
}

/// Atomic, fsynced replacement of the settings of `plugin_id` (0600 in a 0700 directory).
pub fn plugin_settings_write(
    root: &Path,
    plugin_id: &str,
    data: &serde_json::Value,
) -> io::Result<()> {
    use std::os::unix::fs::DirBuilderExt;
    let (dir, path, temporary) = settings_paths(root, plugin_id)?;
    let bytes = serde_json::to_vec(&SettingsFile {
        version: 1,
        data: data.clone(),
    })?;
    if bytes.len() as u64 > SETTINGS_FILE_LIMIT {
        return Err(io::Error::other("plugin settings too large"));
    }
    if fs::symlink_metadata(&dir).is_err() {
        fs::DirBuilder::new().mode(0o700).create(&dir)?;
    }
    private_metadata(&dir, true)?;
    if fs::symlink_metadata(&path).is_ok() {
        private_metadata(&path, false)?;
    }
    // A crashed earlier writer leaves only its own temporary; a link there is removed, not followed.
    let _ = fs::remove_file(&temporary);
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(&temporary)?;
    let result = (|| {
        file.write_all(&bytes)?;
        file.sync_all()?;
        fs::rename(&temporary, &path)?;
        File::open(&dir)?.sync_all()
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

/// Deletes the stored settings of `plugin_id`; absent settings are already cleared.
pub fn plugin_settings_clear(root: &Path, plugin_id: &str) -> io::Result<()> {
    let (dir, path, temporary) = settings_paths(root, plugin_id)?;
    if fs::symlink_metadata(&dir).is_err() {
        return Ok(());
    }
    private_metadata(&dir, true)?;
    let _ = fs::remove_file(&temporary);
    match fs::symlink_metadata(&path) {
        Ok(_) => {
            private_metadata(&path, false)?;
            fs::remove_file(&path)?;
            File::open(&dir)?.sync_all()
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error),
    }
}

impl Drop for Storage {
    fn drop(&mut self) {
        self.hub_import.take();
    }
}
