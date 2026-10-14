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
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Catalog {
    version: u16,
    repository: String,
    plugins: Vec<Manifest>,
}
#[derive(Debug, Deserialize)]
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
#[derive(Debug, Deserialize)]
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
    pub version: u16,
    pub status: &'static str,
    pub repository: Option<String>,
    pub catalog_sha256: Option<String>,
    pub publisher_verified: bool,
    pub entries: Vec<Entry>,
}
impl Snapshot {
    pub fn quarantined() -> Self {
        Self {
            version: 1,
            status: "quarantined",
            repository: None,
            catalog_sha256: None,
            publisher_verified: false,
            entries: vec![],
        }
    }
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
fn digest(s: &str) -> bool {
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
        version: 1,
        status: "verified",
        repository: Some(catalog.repository),
        catalog_sha256: Some(expected.to_owned()),
        publisher_verified: false,
        entries,
    })
}
