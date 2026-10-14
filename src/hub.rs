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
        self
    }
    pub fn quarantined() -> Self {
        Self {
            approval_revision: 0,
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
        version: 1,
        status: "verified",
        repository: Some(catalog.repository),
        catalog_sha256: Some(expected.to_owned()),
        publisher_verified: false,
        entries,
    })
}
