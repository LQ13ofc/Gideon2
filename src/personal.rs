//! WP-10a: personal-data areas (Memory, Souls, Habits, Automations, Conversations).
//!
//! Shared rules for every area:
//! - each area is one private JSON ledger (0600, directory 0700), written atomically (temp + fsync + rename),
//!   read with a size bound, and refused when the inode is not a private regular file owned by this user;
//! - every change is a compare-and-set on `revision`: a stale revision is refused with `stale_revision`;
//! - requests are strict and versioned: `"version": 1` is required, unknown fields fail with `invalid_request`;
//! - history (conversation turns, automation run records, conversation-sourced memory) follows the Core
//!   preference `history_retention`: the caller passes `Some(window_ms)` or `None` for `never`;
//! - privacy: `erase_all` removes every ledger, `export_all` returns everything the user stored.
//!
//! The Core integrates this module through `Personal` (one object, one dispatch call, one snapshot call).

use crate::{automations, conversations, habits, memory, souls};
use serde::{de::DeserializeOwned, Serialize};
use serde_json::{json, Value};
use std::{
    fs::{self, File, OpenOptions},
    io::{self, Read, Write},
    os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt},
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

pub const OP_VERSION: u64 = 1;
pub const DAY_MS: u64 = 86_400_000;

/// Skill engine view used by Habits and Automations. Implemented by the Core adapter
/// (`src/personal_engine.rs`) over `skills_view()` and `skill_run()`, and by fakes in tests.
pub trait SkillEngine {
    /// Version of the skill that is active, enabled, with dependencies and permissions satisfied; `None` otherwise.
    fn enabled_version(&self, skill_id: &str) -> Option<String>;
    /// Starts a run through the engine's own checks. `"ok"` means started; any other code is the engine's refusal.
    fn run_skill(&mut self, skill_id: &str, inputs: Value) -> &'static str;
}

/// Parses a versioned request: `version` must be 1, the rest must match the enum exactly.
pub fn parse<T: DeserializeOwned>(mut value: Value) -> Result<T, &'static str> {
    let object = value.as_object_mut().ok_or("invalid_request")?;
    match object.remove("version") {
        Some(version) if version.as_u64() == Some(OP_VERSION) => {}
        _ => return Err("unsupported_version"),
    }
    serde_json::from_value(value).map_err(|_| "invalid_request")
}

/// One line of user text: trimmed, non-empty, at most `max` characters, no control characters.
pub fn line(value: &str, max: usize) -> Result<String, &'static str> {
    let trimmed = value.trim();
    if trimmed.is_empty() || trimmed.chars().count() > max || trimmed.chars().any(char::is_control)
    {
        return Err("invalid_text");
    }
    Ok(trimmed.to_owned())
}

/// Multi-line text (conversation turns): newlines and tabs allowed, other control characters refused.
pub fn multiline(value: &str, max: usize) -> Result<String, &'static str> {
    let trimmed = value.trim();
    let bad = trimmed
        .chars()
        .any(|c| c.is_control() && c != '\n' && c != '\t');
    if trimmed.is_empty() || trimmed.chars().count() > max || bad {
        return Err("invalid_text");
    }
    Ok(trimmed.to_owned())
}

/// Start of the history window at `now_ms`; `None` when retention is `never` (nothing is kept).
pub fn window_start(now_ms: u64, retention: Option<u64>) -> Option<u64> {
    retention.map(|window| now_ms.saturating_sub(window))
}

/// Identifier from the ledger's own sequence: unique for the life of the ledger.
pub fn next_id(prefix: &str, seq: &mut u64) -> String {
    *seq += 1;
    format!("{prefix}_{:x}", *seq)
}

/// Strict `object` check for JSON payloads stored in a ledger (inputs of skills, etc.), bounded in bytes.
pub fn bounded_object(value: &Value, max_bytes: usize) -> Result<Value, &'static str> {
    if !value.is_object() {
        return Err("invalid_inputs");
    }
    let size = serde_json::to_vec(value)
        .map_err(|_| "invalid_inputs")?
        .len();
    if size > max_bytes {
        return Err("invalid_inputs");
    }
    Ok(value.clone())
}

// ---------------------------------------------------------------------------------------------
// Private files
// ---------------------------------------------------------------------------------------------

static TEMP_SEQ: AtomicU64 = AtomicU64::new(0);

/// Creates `dir` with mode 0700 when missing.
pub fn private_dir(dir: &Path) -> io::Result<()> {
    if !dir.exists() {
        fs::DirBuilder::new()
            .recursive(true)
            .mode(0o700)
            .create(dir)?;
    }
    Ok(())
}

/// Reads a private ledger. `Ok(None)` when absent. Refuses symlinks, hard links, foreign owners, group or
/// other access, and files over `limit` bytes.
pub fn read_private(path: &Path, limit: u64) -> io::Result<Option<Vec<u8>>> {
    let file = match OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
    {
        Ok(file) => file,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
    };
    let meta = file.metadata()?;
    // SAFETY: getuid is a read-only identity query with no preconditions.
    let uid = unsafe { libc::getuid() };
    if !meta.is_file() || meta.nlink() != 1 || meta.uid() != uid || meta.mode() & 0o077 != 0 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "unsafe private file",
        ));
    }
    if meta.len() > limit {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "ledger too large",
        ));
    }
    let mut bytes = Vec::new();
    file.take(limit + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "ledger too large",
        ));
    }
    Ok(Some(bytes))
}

/// Writes `bytes` as a 0600 file: temp file in the same directory, fsync, rename, fsync of the directory.
pub fn write_private_atomic(path: &Path, bytes: &[u8]) -> io::Result<()> {
    let dir = path
        .parent()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "ledger without directory"))?;
    private_dir(dir)?;
    let name = path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("ledger");
    let temp: PathBuf = dir.join(format!(
        ".{name}.{}.{}.tmp",
        std::process::id(),
        TEMP_SEQ.fetch_add(1, Ordering::Relaxed)
    ));
    let result = (|| -> io::Result<()> {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&temp)?;
        file.write_all(bytes)?;
        file.sync_all()?;
        fs::rename(&temp, path)?;
        File::open(dir)?.sync_all()
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result
}

/// Loads a ledger, or its default when the file is absent. Corrupt or unsafe files fail closed.
pub fn load_ledger<T: DeserializeOwned + Default>(
    path: &Path,
    limit: u64,
) -> Result<T, &'static str> {
    match read_private(path, limit) {
        Ok(None) => Ok(T::default()),
        Ok(Some(bytes)) => serde_json::from_slice(&bytes).map_err(|_| "ledger_invalid"),
        Err(_) => Err("ledger_unreadable"),
    }
}

/// Saves a ledger atomically. A ledger over `limit` bytes is refused before anything is written.
pub fn save_ledger<T: Serialize>(path: &Path, value: &T, limit: u64) -> Result<(), &'static str> {
    let bytes = serde_json::to_vec(value).map_err(|_| "ledger_invalid")?;
    if bytes.len() as u64 > limit {
        return Err("ledger_full");
    }
    write_private_atomic(path, &bytes).map_err(|_| "ledger_write_failed")
}

/// Removes one ledger file; absent is fine.
pub fn remove_ledger(path: &Path) -> Result<(), &'static str> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(_) => Err("ledger_write_failed"),
    }
}

// ---------------------------------------------------------------------------------------------
// Aggregate used by the Core
// ---------------------------------------------------------------------------------------------

/// The five areas. Area names on the wire: `memory`, `souls`, `habits`, `automations`, `conversations`.
pub struct Personal {
    dir: PathBuf,
    pub memory: memory::Memory,
    pub souls: souls::Souls,
    pub habits: habits::Habits,
    pub automations: automations::Automations,
    pub conversations: conversations::Conversations,
}

impl Personal {
    /// Opens (creating the directory when needed) every area. A corrupt ledger fails the whole open.
    pub fn open(dir: &Path) -> Result<Self, &'static str> {
        private_dir(dir).map_err(|_| "personal_dir_unavailable")?;
        Ok(Self {
            dir: dir.to_path_buf(),
            memory: memory::Memory::open(dir)?,
            souls: souls::Souls::open(dir)?,
            habits: habits::Habits::open(dir)?,
            automations: automations::Automations::open(dir)?,
            conversations: conversations::Conversations::open(dir)?,
        })
    }

    /// Applies one request to `area`. Unknown areas fail with `unknown_area`.
    pub fn apply(
        &mut self,
        area: &str,
        payload: Value,
        now_ms: u64,
        retention: Option<u64>,
        engine: &mut dyn SkillEngine,
    ) -> Result<Value, &'static str> {
        match area {
            "memory" => {
                let op = memory::parse(payload)?;
                self.memory.apply(op, now_ms, retention)
            }
            "souls" => {
                let op = souls::parse(payload)?;
                self.souls.apply(op, now_ms)
            }
            "habits" => {
                let op = habits::parse(payload)?;
                self.habits.apply(op, now_ms, retention, engine)
            }
            "automations" => {
                let op = automations::parse(payload)?;
                self.automations.apply(op, now_ms, retention, engine)
            }
            "conversations" => {
                let op = conversations::parse(payload)?;
                self.conversations.apply(op, now_ms, retention)
            }
            _ => Err("unknown_area"),
        }
    }

    /// Runs the automations that are due. Called by the Core timer; each call starts at most one run per due automation.
    pub fn tick(
        &mut self,
        now_ms: u64,
        retention: Option<u64>,
        engine: &mut dyn SkillEngine,
    ) -> Vec<Value> {
        self.automations.run_due(now_ms, retention, engine)
    }

    /// Snapshot block `personal`: every area's summary, no full history.
    pub fn snapshot(&self, now_ms: u64, retention: Option<u64>) -> Value {
        json!({
            "retention": match retention { Some(_) => "on", None => "never" },
            "memory": self.memory.snapshot(now_ms, retention),
            "souls": self.souls.snapshot(),
            "habits": self.habits.snapshot(now_ms, retention),
            "automations": self.automations.snapshot(now_ms, retention),
            "conversations": self.conversations.snapshot(now_ms, retention),
        })
    }

    /// Everything stored, for the user to take away (`export` in every area, one document).
    pub fn export_all(&self, now_ms: u64, retention: Option<u64>) -> Value {
        json!({
            "version": OP_VERSION,
            "exported_ms": now_ms,
            "memory": self.memory.export(),
            "souls": self.souls.export(),
            "habits": self.habits.export(),
            "automations": self.automations.export(),
            "conversations": self.conversations.export(now_ms, retention),
        })
    }

    /// Erases every area on disk and resets the in-memory state. Used by "delete all personal data".
    pub fn erase_all(&mut self) -> Result<(), &'static str> {
        for name in [
            memory::FILE,
            souls::FILE,
            habits::FILE,
            automations::FILE,
            conversations::FILE,
        ] {
            remove_ledger(&self.dir.join(name))?;
        }
        // Export files hold the same data: erasing everything removes them too (the Core writes them under here).
        let exports = self.dir.join("exports");
        match fs::remove_dir_all(&exports) {
            Ok(()) => {}
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(_) => return Err("ledger_write_failed"),
        }
        *self = Self::open(&self.dir)?;
        Ok(())
    }

    /// Persists the retention purge of every area (the Core calls it at boot, on a retention change and on its
    /// timer). Under `never` this erases stored history at once; the first error stops and is reported.
    pub fn purge_now(&mut self, now_ms: u64, retention: Option<u64>) -> Result<(), &'static str> {
        self.memory.purge_now(now_ms, retention)?;
        self.habits.purge_now(now_ms, retention)?;
        self.automations.purge_now(now_ms, retention)?;
        self.conversations.purge_now(now_ms, retention)
    }

    pub fn dir(&self) -> &Path {
        &self.dir
    }
}
