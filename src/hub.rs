//! Bounded offline GitHub catalog discovery. Declarations never grant authority.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::HashSet,
    fs::OpenOptions,
    io::{self, Read},
    os::unix::fs::OpenOptionsExt,
    path::{Component, Path},
};

const MAX_CATALOG: u64 = 65536;
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Catalog {
    version: u16,
    repository: String,
    plugins: Vec<Manifest>,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    plugin_id: String,
    api_version: u16,
    publisher: String,
    semver: String,
    targets: Vec<String>,
    binaries: Vec<Binary>,
    license: String,
    permissions: Vec<String>,
    dependencies: Vec<Dependency>,
    conflicts: Vec<String>,
    entrypoint: String,
    build_source: String,
    support_policy: String,
    #[serde(default)]
    signature: Option<String>,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Binary {
    target: String,
    url: String,
    sha256: String,
    size: u64,
}
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Dependency {
    pub plugin_id: String,
    pub semver: String,
}
#[derive(Debug, Clone, Serialize)]
pub struct Entry {
    pub manifest_sha256: String,
    pub permissions_approved: bool,
    pub payload_staged: bool,
    #[serde(skip)]
    pub(crate) payload_sha256: String,
    pub plugin_id: String,
    pub semver: String,
    pub publisher: String,
    pub api_version: u16,
    pub targets: Vec<String>,
    pub license: String,
    pub permissions: Vec<String>,
    pub dependencies: Vec<Dependency>,
    pub conflicts: Vec<String>,
    pub download_size: u64,
    pub support_policy: String,
    pub status: &'static str,
    pub reason: &'static str,
}
#[derive(Debug, Clone, Serialize)]
pub struct Snapshot {
    pub approval_revision: u64,
    pub import: Option<ImportSummary>,
    pub version: u16,
    pub status: &'static str,
    pub repository: Option<String>,
    pub catalog_sha256: Option<String>,
    pub publisher_verified: bool,
    pub entries: Vec<Entry>,
}
impl Snapshot {
    pub fn with_approvals(mut self, storage: &crate::storage::Storage) -> Self {
        if self.status != "verified" {
            return self;
        }
        let Ok(state) = storage.hub_approvals() else {
            return Self::quarantined();
        };
        self.approval_revision = state.revision;
        for entry in &mut self.entries {
            entry.permissions_approved = state.records.iter().any(|r| {
                Some(&r.catalog_sha256) == self.catalog_sha256.as_ref()
                    && r.plugin_id == entry.plugin_id
                    && r.manifest_sha256 == entry.manifest_sha256
                    && r.permissions == entry.permissions
                    && entry.status == "not_installed"
            });
        }
        for entry in &mut self.entries {
            match staged(storage, entry) {
                Ok(present) => entry.payload_staged = present,
                Err(_) => return Self::quarantined(),
            }
        }
        self.import = storage.hub_import.as_ref().map(Import::summary);
        self
    }
    pub fn quarantined() -> Self {
        Self {
            approval_revision: 0,
            import: None,
            version: 1,
            status: "quarantined",
            repository: None,
            catalog_sha256: None,
            publisher_verified: false,
            entries: vec![],
        }
    }
}
#[derive(Debug, Default, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Approval {
    plugin_id: String,
    catalog_sha256: String,
    manifest_sha256: String,
    permissions: Vec<String>,
    publisher_unverified_ack: bool,
}
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Approvals {
    version: u16,
    pub revision: u64,
    records: Vec<Approval>,
}
impl Default for Approvals {
    fn default() -> Self {
        Self {
            version: 1,
            revision: 0,
            records: vec![],
        }
    }
}
impl Approvals {
    pub(crate) fn validate(&self) -> io::Result<()> {
        if self.version != 1
            || self.records.len() > 8
            || self
                .records
                .iter()
                .map(|r| &r.plugin_id)
                .collect::<HashSet<_>>()
                .len()
                != self.records.len()
            || self.records.iter().any(|r| {
                !crate::protocol::valid_id(&r.plugin_id)
                    || !digest(&r.catalog_sha256)
                    || !digest(&r.manifest_sha256)
                    || !ids(&r.permissions)
                    || !r.publisher_unverified_ack
            })
        {
            return Err(fail());
        }
        Ok(())
    }
}
pub fn approve(
    storage: &crate::storage::Storage,
    hub: &Snapshot,
    revision: u64,
    plugin_id: &str,
    manifest_sha256: &str,
    permissions: &[String],
    acknowledged: bool,
) -> Result<(), &'static str> {
    if storage.configuration_status != crate::storage::ConfigurationStatus::Ready {
        return Err("configuration_not_ready");
    }
    if hub.status != "verified" {
        return Err("hub_unavailable");
    }
    if revision != hub.approval_revision {
        return Err("stale_hub_revision");
    }
    let entry = hub
        .entries
        .iter()
        .find(|e| e.plugin_id == plugin_id)
        .ok_or("unknown_plugin")?;
    if entry.status != "not_installed" {
        return Err("plugin_incompatible");
    }
    if entry.manifest_sha256 != manifest_sha256 {
        return Err("manifest_mismatch");
    }
    if entry.permissions != permissions {
        return Err("permissions_mismatch");
    }
    if !acknowledged {
        return Err("publisher_ack_required");
    }
    if entry.permissions_approved {
        return Err("already_approved");
    }
    let mut state = storage.hub_approvals().map_err(|_| "hub_storage_error")?;
    if state.revision != revision {
        return Err("stale_hub_revision");
    }
    // Keep only records for this pinned catalog; a catalog change never inherits approval.
    state.records.retain(|r| {
        Some(&r.catalog_sha256) == hub.catalog_sha256.as_ref() && r.plugin_id != plugin_id
    });
    state.records.push(Approval {
        plugin_id: plugin_id.to_owned(),
        catalog_sha256: hub.catalog_sha256.clone().ok_or("hub_unavailable")?,
        manifest_sha256: manifest_sha256.to_owned(),
        permissions: permissions.to_vec(),
        publisher_unverified_ack: acknowledged,
    });
    state.revision = revision.checked_add(1).ok_or("hub_revision_exhausted")?;
    storage
        .save_hub_approvals(&state)
        .map_err(|_| "hub_storage_error")
}
fn fail() -> io::Error {
    io::Error::other("invalid Hub catalog")
}
fn text(s: &str, limit: usize) -> bool {
    !s.is_empty() && s.len() <= limit && !s.chars().any(char::is_control)
}
fn semver(s: &str) -> bool {
    let parts: Vec<_> = s.split('.').collect();
    s.len() <= 24
        && parts.len() == 3
        && parts.iter().all(|p| {
            !p.is_empty()
                && p.bytes().all(|b| b.is_ascii_digit())
                && (p.len() == 1 || !p.starts_with('0'))
                && p.parse::<u32>().is_ok()
        })
}
fn github(s: &str) -> bool {
    let Some(rest) = s.strip_prefix("https://github.com/") else {
        return false;
    };
    s.len() <= 256
        && rest.split('/').count() >= 2
        && rest.split('/').all(|p| {
            !p.is_empty()
                && p != "."
                && p != ".."
                && p.bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
        })
}
pub(crate) fn digest(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn ids(items: &[String]) -> bool {
    items.len() <= 8
        && items.iter().all(|s| crate::protocol::valid_id(s))
        && items.iter().collect::<HashSet<_>>().len() == items.len()
}
fn relative(s: &str) -> bool {
    text(s, 128)
        && !s.contains('\\')
        && !s.contains(':')
        && s.split('/').all(|p| !p.is_empty() && p != "." && p != "..")
        && Path::new(s)
            .components()
            .all(|c| matches!(c, Component::Normal(_)))
}
pub fn load(path: &Path, expected: &str) -> io::Result<Snapshot> {
    if !path.is_absolute() || !digest(expected) {
        return Err(fail());
    }
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)?;
    let meta = file.metadata()?;
    if !meta.is_file() || meta.len() > MAX_CATALOG {
        return Err(fail());
    }
    let mut bytes = Vec::new();
    Read::by_ref(&mut file)
        .take(MAX_CATALOG + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_CATALOG || format!("{:x}", Sha256::digest(&bytes)) != expected {
        return Err(fail());
    }
    let catalog: Catalog = serde_json::from_slice(&bytes).map_err(|_| fail())?;
    if catalog.version != 1 || !github(&catalog.repository) || catalog.plugins.len() > 8 {
        return Err(fail());
    }
    let mut plugin_ids = HashSet::new();
    for m in &catalog.plugins {
        if !crate::protocol::valid_id(&m.plugin_id)
            || !plugin_ids.insert(&m.plugin_id)
            || !semver(&m.semver)
            || !text(&m.publisher, 64)
            || !text(&m.license, 64)
            || !text(&m.support_policy, 128)
            || !github(&m.build_source)
            || !relative(&m.entrypoint)
            || !ids(&m.targets)
            || m.targets.is_empty()
            || !ids(&m.permissions)
            || !ids(&m.conflicts)
            || m.conflicts.contains(&m.plugin_id)
            || m.dependencies.len() > 8
            || m.dependencies.iter().any(|d| {
                !crate::protocol::valid_id(&d.plugin_id)
                    || !semver(&d.semver)
                    || d.plugin_id == m.plugin_id
                    || m.conflicts.contains(&d.plugin_id)
            })
            || m.dependencies
                .iter()
                .map(|d| &d.plugin_id)
                .collect::<HashSet<_>>()
                .len()
                != m.dependencies.len()
            || m.signature.as_ref().is_some_and(|s| !text(s, 256))
            || m.binaries.is_empty()
            || m.binaries.len() > 8
        {
            return Err(fail());
        }
        let mut targets = HashSet::new();
        for b in &m.binaries {
            if !m.targets.contains(&b.target)
                || !targets.insert(&b.target)
                || !github(&b.url)
                || !digest(&b.sha256)
                || !(1..=67108864).contains(&b.size)
            {
                return Err(fail());
            }
        }
        if targets.len() != m.targets.len() {
            return Err(fail());
        }
    }
    let target = format!("{}_{}", std::env::consts::OS, std::env::consts::ARCH);
    let entries = catalog
        .plugins
        .iter()
        .map(|m| {
            let reason = if m.api_version != 1 {
                "api_version"
            } else if !m.targets.contains(&target) {
                "target"
            } else if !m.dependencies.is_empty() {
                "dependencies_unresolved"
            } else {
                "none"
            };
            Entry {
                manifest_sha256: format!(
                    "{:x}",
                    Sha256::digest(serde_json::to_vec(m).expect("serializable manifest"))
                ),
                permissions_approved: false,
                payload_staged: false,
                payload_sha256: m
                    .binaries
                    .iter()
                    .find(|b| b.target == target)
                    .map_or_else(String::new, |b| b.sha256.clone()),
                plugin_id: m.plugin_id.clone(),
                semver: m.semver.clone(),
                publisher: m.publisher.clone(),
                api_version: m.api_version,
                targets: m.targets.clone(),
                license: m.license.clone(),
                permissions: m.permissions.clone(),
                dependencies: m.dependencies.clone(),
                conflicts: m.conflicts.clone(),
                download_size: m
                    .binaries
                    .iter()
                    .find(|b| b.target == target)
                    .map_or(0, |b| b.size),
                support_policy: m.support_policy.clone(),
                status: if reason == "none" {
                    "not_installed"
                } else {
                    "incompatible"
                },
                reason,
            }
        })
        .collect();
    Ok(Snapshot {
        approval_revision: 0,
        import: None,
        version: 1,
        status: "verified",
        repository: Some(catalog.repository),
        catalog_sha256: Some(expected.to_owned()),
        publisher_verified: false,
        entries,
    })
}

/// Opaque verified payload only; never extracted, executable, or installed.
#[derive(Debug, Clone, Serialize)]
pub struct ImportSummary {
    pub import_id: String,
    pub plugin_id: String,
    pub received: u64,
    pub expected: u64,
}
pub(crate) struct Import {
    summary: ImportSummary,
    file: std::fs::File,
    pending: Option<std::path::PathBuf>,
    destination: std::path::PathBuf,
    hash: Sha256,
    expected_hash: String,
    pub deadline: std::time::Instant,
}
impl Import {
    fn summary(&self) -> ImportSummary {
        self.summary.clone()
    }
}
impl Drop for Import {
    fn drop(&mut self) {
        if let Some(path) = self.pending.take() {
            use std::os::unix::fs::MetadataExt;
            if let (Ok(m), Ok(fd)) = (std::fs::symlink_metadata(&path), self.file.metadata()) {
                if m.dev() == fd.dev() && m.ino() == fd.ino() {
                    let _ = std::fs::remove_file(path);
                }
            }
        }
    }
}
fn payload_path(storage: &crate::storage::Storage, entry: &Entry) -> std::path::PathBuf {
    storage
        .root
        .join(format!("hub-{}.payload", entry.manifest_sha256))
}
fn staged(storage: &crate::storage::Storage, entry: &Entry) -> io::Result<bool> {
    let mut file = match OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(payload_path(storage, entry))
    {
        Ok(file) => file,
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(false),
        Err(e) => return Err(e),
    };
    crate::storage::validate_opened_private(&file)?;
    use std::os::unix::fs::MetadataExt;
    if file.metadata()?.mode() & 0o777 != 0o600 || file.metadata()?.len() != entry.download_size {
        return Err(fail());
    }
    let mut hash = Sha256::new();
    let mut remaining = entry.download_size;
    let mut buffer = [0; 8192];
    while remaining > 0 {
        let n = file.read(&mut buffer[..remaining.min(8192) as usize])?;
        if n == 0 {
            return Err(fail());
        }
        hash.update(&buffer[..n]);
        remaining -= n as u64;
    }
    if file.read(&mut buffer[..1])? != 0 || format!("{:x}", hash.finalize()) != entry.payload_sha256
    {
        return Err(fail());
    }
    Ok(true)
}
pub fn begin_import(
    storage: &mut crate::storage::Storage,
    hub: &Snapshot,
    revision: u64,
    plugin_id: &str,
    manifest: &str,
    import_id: &str,
    now: std::time::Instant,
) -> Result<(), &'static str> {
    if storage.configuration_status != crate::storage::ConfigurationStatus::Ready {
        return Err("configuration_not_ready");
    }
    if hub.status != "verified" {
        return Err("hub_unavailable");
    }
    if storage.hub_import.is_some() {
        return Err("hub_import_busy");
    }
    if revision != hub.approval_revision {
        return Err("stale_hub_revision");
    }
    if !crate::protocol::valid_id(import_id) {
        return Err("invalid_import_id");
    }
    let entry = hub
        .entries
        .iter()
        .find(|e| e.plugin_id == plugin_id)
        .ok_or("unknown_plugin")?;
    if entry.status != "not_installed" {
        return Err("plugin_incompatible");
    }
    if entry.manifest_sha256 != manifest {
        return Err("manifest_mismatch");
    }
    let refreshed = hub.clone().with_approvals(storage);
    if refreshed.status != "verified" {
        return Err("hub_unavailable");
    }
    if refreshed.approval_revision != revision {
        return Err("stale_hub_revision");
    }
    let current = refreshed
        .entries
        .iter()
        .find(|e| e.plugin_id == plugin_id)
        .ok_or("unknown_plugin")?;
    if !current.permissions_approved {
        return Err("permissions_not_approved");
    }
    if current.payload_staged {
        return Err("already_staged");
    }
    let destination = payload_path(storage, entry);
    let pending = storage.root.join(format!(".hub-{manifest}.pending"));
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(&pending)
        .map_err(|_| "hub_storage_error")?;
    storage.hub_import = Some(Import {
        summary: ImportSummary {
            import_id: import_id.to_owned(),
            plugin_id: plugin_id.to_owned(),
            received: 0,
            expected: entry.download_size,
        },
        file,
        pending: Some(pending),
        destination,
        hash: Sha256::new(),
        expected_hash: entry.payload_sha256.clone(),
        deadline: now + std::time::Duration::from_secs(120),
    });
    Ok(())
}
pub fn import_deadline(storage: &crate::storage::Storage) -> Option<std::time::Instant> {
    storage.hub_import.as_ref().map(|s| s.deadline)
}
pub fn expire_import(storage: &mut crate::storage::Storage, now: std::time::Instant) -> bool {
    if import_deadline(storage).is_some_and(|d| now >= d) {
        storage.hub_import.take();
        return true;
    }
    false
}
pub fn abort_import(storage: &mut crate::storage::Storage, id: &str) -> Result<(), &'static str> {
    if storage
        .hub_import
        .as_ref()
        .is_none_or(|s| s.summary.import_id != id)
    {
        return Err("stale_import");
    }
    storage.hub_import.take();
    Ok(())
}
pub fn chunk_import(
    storage: &mut crate::storage::Storage,
    id: &str,
    offset: u64,
    hex: &str,
) -> Result<(), &'static str> {
    use std::io::Write;
    let s = storage
        .hub_import
        .as_mut()
        .filter(|s| s.summary.import_id == id)
        .ok_or("stale_import")?;
    // Reject without consuming bytes; caller can retry the same offset or abort.
    if offset != s.summary.received {
        return Err("stale_import_offset");
    }
    if hex.is_empty()
        || hex.len() > 2048
        || hex.len() % 2 != 0
        || !hex
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err("invalid_import_chunk");
    }
    let bytes: Vec<u8> = hex
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let digit = |b: u8| if b <= b'9' { b - b'0' } else { b - b'a' + 10 };
            digit(pair[0]) * 16 + digit(pair[1])
        })
        .collect();
    if s.summary.received + bytes.len() as u64 > s.summary.expected {
        storage.hub_import.take();
        return Err("payload_size_mismatch");
    }
    if s.file.write_all(&bytes).is_err() {
        storage.hub_import.take();
        return Err("hub_storage_error");
    }
    s.hash.update(&bytes);
    s.summary.received += bytes.len() as u64;
    Ok(())
}
pub fn finish_import(
    storage: &mut crate::storage::Storage,
    hub: &Snapshot,
    id: &str,
) -> Result<(), &'static str> {
    use std::os::unix::fs::MetadataExt;
    if storage
        .hub_import
        .as_ref()
        .is_none_or(|s| s.summary.import_id != id)
    {
        return Err("stale_import");
    }
    let mut s = storage.hub_import.take().expect("checked import");
    let current = hub.clone().with_approvals(storage);
    if current.status != "verified"
        || !current.entries.iter().any(|e| {
            e.plugin_id == s.summary.plugin_id
                && e.permissions_approved
                && payload_path(storage, e) == s.destination
        })
    {
        return Err("permissions_not_approved");
    }
    if s.summary.received != s.summary.expected {
        return Err("payload_size_mismatch");
    }
    if format!("{:x}", s.hash.clone().finalize()) != s.expected_hash {
        return Err("payload_hash_mismatch");
    }
    let result = (|| {
        crate::storage::validate_opened_private(&s.file)?;
        let pending = s.pending.as_ref().expect("owned pending");
        let path_meta = std::fs::symlink_metadata(pending)?;
        let fd_meta = s.file.metadata()?;
        if fd_meta.mode() & 0o777 != 0o600 {
            return Err(fail());
        }
        if path_meta.dev() != fd_meta.dev() || path_meta.ino() != fd_meta.ino() {
            return Err(fail());
        }
        s.file.sync_all()?;
        // Hash the actual descriptor again: observed progress is not a file integrity proof.
        use std::io::{Seek, SeekFrom};
        s.file.seek(SeekFrom::Start(0))?;
        let mut hash = Sha256::new();
        let mut buffer = [0u8; 8192];
        let mut total = 0u64;
        loop {
            let n = s.file.read(&mut buffer)?;
            if n == 0 {
                break;
            }
            total += n as u64;
            if total > s.summary.expected {
                return Err(fail());
            }
            hash.update(&buffer[..n]);
        }
        if total != s.summary.expected || format!("{:x}", hash.finalize()) != s.expected_hash {
            return Err(fail());
        }
        // No replacement of an existing destination; atomic no-clobber publication.
        publish_no_replace(pending, &s.destination)?;
        s.pending = None;
        std::fs::File::open(&storage.root)?.sync_all()
    })();
    result.map_err(|_| "hub_storage_error")
}

pub(crate) fn import_progress(mut hub: Snapshot, storage: &crate::storage::Storage) -> Snapshot {
    hub.import = storage.hub_import.as_ref().map(Import::summary);
    hub
}

#[cfg(target_os = "linux")]
fn publish_no_replace(source: &Path, destination: &Path) -> io::Result<()> {
    use std::{ffi::CString, os::unix::ffi::OsStrExt};
    let source = CString::new(source.as_os_str().as_bytes()).map_err(|_| fail())?;
    let destination = CString::new(destination.as_os_str().as_bytes()).map_err(|_| fail())?;
    // SAFETY: NUL-terminated valid paths; atomic same-directory no-clobber rename.
    let result = unsafe {
        libc::syscall(
            libc::SYS_renameat2,
            libc::AT_FDCWD,
            source.as_ptr(),
            libc::AT_FDCWD,
            destination.as_ptr(),
            libc::RENAME_NOREPLACE,
        )
    };
    if result == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}
#[cfg(not(target_os = "linux"))]
fn publish_no_replace(source: &Path, destination: &Path) -> io::Result<()> {
    std::fs::hard_link(source, destination)?;
    std::fs::remove_file(source)
}
