//! Wake phrase catalog: packaged defaults, private custom phrases, the user's active list and the keyword
//! file the wake worker reads. Pure logic plus file helpers. The Core owns ordering and CAS, storage owns
//! the ledgers, and transport runs the synthetic measurement (`run_test`).
//!
//! Keyword lines use the KWS format `PHONES :boost #threshold @LABEL`. Boost and threshold are per phrase;
//! the defaults (boost 1.2, threshold 0.22) are the ones measured in docs/evidence/wake-phrases.json.
use crate::protocol::valid_id;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{HashMap, HashSet},
    fs::{self, OpenOptions},
    io::{self, Read, Write},
    os::unix::fs::{DirBuilderExt, OpenOptionsExt},
    path::{Path, PathBuf},
    sync::Arc,
    time::{Duration, Instant},
};

pub const MAX_ACTIVE: usize = 5;
pub const MAX_CUSTOM: usize = 8;
pub const MAX_SETTINGS: usize = 16;
pub const DEFAULT_BOOST: f32 = 1.2;
pub const DEFAULT_THRESHOLD: f32 = 0.22;
pub const MIN_PHONES: usize = 6;
pub const MAX_TEXT_CHARS: usize = 40;
/// Synthetic acceptance: at least this share of positives and zero false wakes on negatives.
pub const TEST_MIN_HIT_PERCENT: u32 = 70;
const LEXICON_LIMIT: u64 = 8 * 1024 * 1024;
const CUSTOM_LIMIT: u64 = 65536;
const CHECK_TIMEOUT: Duration = Duration::from_secs(60);
const TEST_TIMEOUT: Duration = Duration::from_secs(600);
/// Words that alone make a phrase too generic (every word must be in this list to reject).
const GENERIC: &[&str] = &[
    "hey", "hi", "hello", "ok", "okay", "computer", "yes", "no", "please", "the", "a", "and", "um",
    "uh", "you", "there",
];

/// Stable rejection vocabulary of `check` (shown in Portuguese by the bridge).
pub mod code {
    pub const EMPTY: &str = "phrase_empty";
    pub const TOO_LONG: &str = "phrase_too_long";
    pub const INVALID_CHARACTERS: &str = "phrase_invalid_characters";
    pub const TOO_FEW_WORDS: &str = "phrase_needs_two_words";
    pub const TOO_MANY_WORDS: &str = "phrase_too_many_words";
    pub const TOO_GENERIC: &str = "phrase_too_generic";
    pub const TOO_FEW_TOKENS: &str = "phrase_too_few_tokens";
    pub const WORD_NOT_IN_LEXICON: &str = "word_not_in_lexicon";
    pub const TOKEN_NOT_IN_VOCABULARY: &str = "token_not_in_vocabulary";
    pub const LEXICON_UNAVAILABLE: &str = "lexicon_unavailable";
    pub const DUPLICATE: &str = "phrase_duplicate";
    pub const STORE_FULL: &str = "phrase_store_full";
    pub const NOT_FOUND: &str = "phrase_not_found";
    pub const IN_USE: &str = "phrase_in_use";
    pub const UNMEASURED: &str = "phrase_unmeasured";
    pub const MEASUREMENT_FAILED: &str = "phrase_measurement_failed";
    pub const TEST_RUNNING: &str = "phrase_test_running";
    pub const TEST_UNAVAILABLE: &str = "phrase_test_unavailable";
    pub const TEST_FAILED: &str = "phrase_test_failed";
    pub const TOO_MANY_ACTIVE: &str = "too_many_active_phrases";
    pub const INVALID_SELECTION: &str = "invalid_wake_phrases";
    pub const NOT_QUALIFIED: &str = "wake_not_qualified";
    pub const START_FAILED: &str = "wake_start_failed";
    pub const STALE_STORE: &str = "stale_phrase_store";
    pub const STORE_ERROR: &str = "phrase_store_error";
    pub const OK: &str = "ok";
}

/// One stored preference: `wake_phrases: [{id, active, sensitivity?}]` in the private ledger.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Setting {
    pub id: String,
    pub active: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sensitivity: Option<f32>,
}

/// Shape check of a stored or requested list: bounded, unique valid ids, sensitivities in range, at most
/// `MAX_ACTIVE` active entries. Whether an id exists in the catalog is decided by the Core.
pub fn valid_settings(list: &[Setting]) -> bool {
    list.len() <= MAX_SETTINGS
        && list.iter().enumerate().all(|(i, s)| {
            valid_id(&s.id)
                && !list[..i].iter().any(|o| o.id == s.id)
                && s.sensitivity
                    .is_none_or(crate::storage::valid_wake_sensitivity)
        })
        && list.iter().filter(|s| s.active).count() <= MAX_ACTIVE
}

/// Settings the Core runs. An empty list is the ledger of an older Core: its single `wake_phrase` (or the
/// packaged default) becomes one active entry. Unknown ids are dropped later, against the catalog.
pub fn migrated(list: &[Setting], legacy: Option<&str>, default_id: &str) -> Vec<Setting> {
    if !list.is_empty() {
        return list.to_vec();
    }
    vec![Setting {
        id: legacy.unwrap_or(default_id).to_string(),
        active: true,
        sensitivity: None,
    }]
}

/// Keyword label of a catalog id (`hey_gideon` -> `HEY_GIDEON`; custom ids get their own stable label).
pub fn label_of(id: &str) -> String {
    id.to_ascii_uppercase()
}

/// One catalog entry as the Core sees it: a packaged default or a custom phrase.
#[derive(Clone, Debug, PartialEq)]
pub struct Entry {
    pub id: String,
    pub text: String,
    pub tokens: String,
    pub label: String,
    pub language: String,
    pub boost: f32,
    pub threshold: f32,
    pub qualification: &'static str,
    pub custom: bool,
    pub measurement: Option<Measurement>,
}

impl Entry {
    /// Activation rule: packaged defaults only when dev-qualified; custom phrases only with a measurement
    /// (a failing measurement needs the explicit acknowledgement in the request).
    pub fn selectable(&self) -> bool {
        if self.custom {
            self.measurement.is_some()
        } else {
            self.qualification == "dev_qualified"
        }
    }
}

/// Result of the synthetic measurement, stored with the phrase. `passed` is computed here, never trusted
/// from the measuring process.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Measurement {
    pub source: String,
    pub positives: u32,
    pub hits: u32,
    pub negatives: u32,
    pub false_wakes: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub latency_ms: Option<u32>,
    pub passed: bool,
}

impl Measurement {
    pub fn new(
        positives: u32,
        hits: u32,
        negatives: u32,
        false_wakes: u32,
        latency_ms: Option<u32>,
    ) -> io::Result<Self> {
        if positives == 0
            || negatives == 0
            || hits > positives
            || false_wakes > negatives
            || positives > 64
            || negatives > 64
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "invalid measurement",
            ));
        }
        let passed = hits * 100 >= positives * TEST_MIN_HIT_PERCENT && false_wakes == 0;
        Ok(Self {
            source: "synthetic".into(),
            positives,
            hits,
            negatives,
            false_wakes,
            latency_ms,
            passed,
        })
    }
}

/// A custom phrase in the private store. `sha256` covers text and tokens (integrity of the file).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Stored {
    pub id: String,
    pub text: String,
    pub tokens: String,
    pub sha256: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub measurement: Option<Measurement>,
}

/// `wake-phrases.json` (0600, same-directory atomic replace). `revision` is the CAS of add and remove.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CustomFile {
    pub version: u16,
    pub revision: u64,
    pub phrases: Vec<Stored>,
}

impl Default for CustomFile {
    fn default() -> Self {
        Self {
            version: 1,
            revision: 0,
            phrases: Vec::new(),
        }
    }
}

impl CustomFile {
    pub fn validate(&self) -> io::Result<()> {
        let invalid = || io::Error::new(io::ErrorKind::InvalidData, "invalid custom phrases");
        if self.version != 1 || self.phrases.len() > MAX_CUSTOM {
            return Err(invalid());
        }
        for (i, p) in self.phrases.iter().enumerate() {
            let shaped = valid_id(&p.id)
                && p.id.starts_with("custom_")
                && !p.tokens.is_empty()
                && p.tokens.len() <= 200
                && p.tokens
                    .bytes()
                    .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b' ')
                && p.text.len() <= 160
                && p.text
                    .bytes()
                    .all(|b| b.is_ascii_alphabetic() || b == b' ' || b == b'\'');
            if !shaped
                || p.sha256 != digest(&p.text, &p.tokens)
                || self.phrases[..i]
                    .iter()
                    .any(|o| o.id == p.id || o.tokens == p.tokens)
            {
                return Err(invalid());
            }
            if let Some(m) = &p.measurement {
                if Measurement::new(
                    m.positives,
                    m.hits,
                    m.negatives,
                    m.false_wakes,
                    m.latency_ms,
                )?
                .passed
                    != m.passed
                {
                    return Err(invalid());
                }
            }
        }
        Ok(())
    }
}

/// Integrity digest of a custom phrase: `sha256(text NUL tokens)`, hex.
pub fn digest(text: &str, tokens: &str) -> String {
    let mut hash = Sha256::new();
    hash.update(text.as_bytes());
    hash.update([0u8]);
    hash.update(tokens.as_bytes());
    format!("{:x}", hash.finalize())
}

/// Stable id and label of a custom phrase derived from its tokens.
pub fn custom_id(tokens: &str) -> String {
    let hex = format!("{:x}", Sha256::digest(tokens.as_bytes()));
    format!("custom_{}", &hex[..12])
}
pub fn custom_label(id: &str) -> String {
    label_of(id)
}

/// Pronunciation lexicon of the KWS asset (`en.phone`: `WORD PHONE PHONE ...`) and the model vocabulary
/// (`tokens.txt`). Custom phrases are tokenized here; a word missing from the lexicon is refused.
#[derive(Debug, Default)]
pub struct Lexicon {
    words: HashMap<String, String>,
    vocab: HashSet<String>,
}

impl Lexicon {
    pub fn parse(lexicon: &str, tokens: &str) -> Self {
        let vocab = tokens
            .lines()
            .filter_map(|line| line.split_whitespace().next())
            .map(str::to_string)
            .collect();
        let mut words = HashMap::new();
        for line in lexicon.lines() {
            let mut parts = line.split_whitespace();
            if let Some(word) = parts.next() {
                let phones: Vec<&str> = parts.collect();
                if !phones.is_empty() {
                    words
                        .entry(word.to_string())
                        .or_insert_with(|| phones.join(" "));
                }
            }
        }
        Self { words, vocab }
    }

    /// Reads both files (bounded) and checks the lexicon bytes against the pinned digest of the pack.
    pub fn load(lexicon: &Path, lexicon_sha256: &str, tokens: &Path) -> io::Result<Self> {
        let bytes = read_bounded(lexicon, LEXICON_LIMIT)?;
        if format!("{:x}", Sha256::digest(&bytes)) != lexicon_sha256 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "lexicon digest mismatch",
            ));
        }
        let vocab = read_bounded(tokens, LEXICON_LIMIT)?;
        let lexicon = String::from_utf8(bytes).map_err(|_| io::Error::other("lexicon utf-8"))?;
        let vocab = String::from_utf8(vocab).map_err(|_| io::Error::other("vocabulary utf-8"))?;
        Ok(Self::parse(&lexicon, &vocab))
    }
}

/// Outcome of a validation request. `ok` is the only flag the UI trusts for enabling "Adicionar".
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Check {
    pub ok: bool,
    pub code: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub text: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tokens: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub word: Option<String>,
}

impl Check {
    fn refuse(code: &'static str, word: Option<String>) -> Self {
        Self {
            ok: false,
            code,
            text: None,
            tokens: None,
            word,
        }
    }
}

/// Validates a candidate phrase: shape, words, generic phrases, lexicon and vocabulary, length in phones.
/// Returns the normalized text and its KWS tokens when accepted.
pub fn check(text: &str, lexicon: Option<&Lexicon>) -> Check {
    if text.len() > 160 {
        return Check::refuse(code::TOO_LONG, None);
    }
    let normalized = text.split_whitespace().collect::<Vec<_>>().join(" ");
    if normalized.is_empty() {
        return Check::refuse(code::EMPTY, None);
    }
    if normalized.chars().count() > MAX_TEXT_CHARS {
        return Check::refuse(code::TOO_LONG, None);
    }
    if !normalized
        .bytes()
        .all(|b| b.is_ascii_alphabetic() || b == b' ' || b == b'\'')
    {
        return Check::refuse(code::INVALID_CHARACTERS, None);
    }
    let words: Vec<String> = normalized.split(' ').map(str::to_ascii_lowercase).collect();
    if words.len() < 2 {
        return Check::refuse(code::TOO_FEW_WORDS, None);
    }
    if words.len() > 4 {
        return Check::refuse(code::TOO_MANY_WORDS, None);
    }
    if words.iter().all(|w| GENERIC.contains(&w.as_str())) {
        return Check::refuse(code::TOO_GENERIC, None);
    }
    let Some(lexicon) = lexicon else {
        return Check::refuse(code::LEXICON_UNAVAILABLE, None);
    };
    let mut phones: Vec<String> = Vec::new();
    for word in normalized.split(' ') {
        let Some(entry) = lexicon.words.get(&word.to_ascii_uppercase()) else {
            let shown: String = word.chars().take(20).collect();
            return Check::refuse(code::WORD_NOT_IN_LEXICON, Some(shown));
        };
        for phone in entry.split(' ') {
            if !lexicon.vocab.contains(phone) {
                return Check::refuse(code::TOKEN_NOT_IN_VOCABULARY, Some(phone.to_string()));
            }
            phones.push(phone.to_string());
        }
    }
    if phones.len() < MIN_PHONES {
        return Check::refuse(code::TOO_FEW_TOKENS, None);
    }
    Check {
        ok: true,
        code: code::OK,
        text: Some(normalized),
        tokens: Some(phones.join(" ")),
        word: None,
    }
}

/// Maps a sensitivity to a phrase threshold: `base * (2 - sensitivity)`, same scale as `wake::keywords_threshold`.
pub fn phrase_threshold(base: f32, sensitivity: f32) -> f32 {
    (base * (2.0 - sensitivity)).clamp(0.1, 0.5)
}

/// Four decimals without float noise (0.22 * 1.5 is 0.32999998 in f32; the keyword file says 0.33).
fn fixed(value: f32) -> f32 {
    (value * 10_000.0).round() / 10_000.0
}

/// The active catalog entries with their sensitivity, in list order. Unknown or inactive ids are skipped.
pub fn active<'a>(catalog: &'a [Entry], settings: &[Setting]) -> Vec<(&'a Entry, Option<f32>)> {
    settings
        .iter()
        .filter(|s| s.active)
        .filter_map(|s| {
            catalog
                .iter()
                .find(|e| e.id == s.id)
                .map(|e| (e, s.sensitivity))
        })
        .take(MAX_ACTIVE)
        .collect()
}

/// Keyword file: base lines (packaged, one per label) with the active defaults boosted and thresholded, the
/// other base lines kept as competitors, and the active custom phrases appended. `global` is the Core's
/// `wake_sensitivity`, used for phrases without their own sensitivity.
pub fn keywords_text(
    base: &str,
    catalog: &[Entry],
    settings: &[Setting],
    global: f32,
) -> io::Result<String> {
    let invalid = || io::Error::new(io::ErrorKind::InvalidData, "invalid keyword set");
    let chosen = active(catalog, settings);
    let mut lines = Vec::new();
    let mut used = HashSet::new();
    for line in base.lines().map(str::trim).filter(|l| !l.is_empty()) {
        let parts: Vec<&str> = line.split_whitespace().collect();
        let label = parts
            .last()
            .and_then(|l| l.strip_prefix('@'))
            .ok_or_else(invalid)?;
        match chosen.iter().find(|(e, _)| !e.custom && e.label == label) {
            Some((entry, sensitivity)) => {
                let threshold = phrase_threshold(entry.threshold, sensitivity.unwrap_or(global));
                lines.push(format!(
                    "{} :{} #{} @{}",
                    parts[..parts.len() - 1].join(" "),
                    entry.boost,
                    fixed(threshold),
                    label
                ));
                used.insert(label.to_string());
            }
            None => lines.push(line.to_string()),
        }
    }
    if chosen
        .iter()
        .any(|(e, _)| !e.custom && !used.contains(&e.label))
    {
        return Err(invalid());
    }
    for (entry, sensitivity) in chosen.iter().filter(|(e, _)| e.custom) {
        let threshold = phrase_threshold(entry.threshold, sensitivity.unwrap_or(global));
        lines.push(format!(
            "{} :{} #{} @{}",
            entry.tokens,
            entry.boost,
            fixed(threshold),
            entry.label
        ));
    }
    Ok(lines.join("\n") + "\n")
}

/// Worker manifest of a keyword set: the packaged manifest with the active list, the keyword file and its hash.
pub fn manifest_value(
    base: &serde_json::Value,
    keywords: &Path,
    keywords_sha256: &str,
    catalog: &[Entry],
    settings: &[Setting],
) -> io::Result<serde_json::Value> {
    let invalid = || io::Error::new(io::ErrorKind::InvalidData, "invalid base manifest");
    let mut value = base.clone();
    let mut phrases = base["supported_phrases"]
        .as_object()
        .cloned()
        .ok_or_else(invalid)?;
    let chosen = active(catalog, settings);
    for (entry, _) in chosen.iter().filter(|(e, _)| e.custom) {
        phrases.insert(
            entry.id.clone(),
            serde_json::Value::String(entry.label.clone()),
        );
    }
    let ids: Vec<String> = chosen.iter().map(|(e, _)| e.id.clone()).collect();
    if ids.is_empty() {
        return Err(invalid());
    }
    let mut hashes = base["hashes"].as_object().cloned().ok_or_else(invalid)?;
    hashes.insert(
        "keywords.txt".into(),
        serde_json::Value::String(keywords_sha256.into()),
    );
    let object = value.as_object_mut().ok_or_else(invalid)?;
    object.insert(
        "supported_phrases".into(),
        serde_json::Value::Object(phrases),
    );
    object.insert("active_phrase".into(), serde_json::json!(ids[0]));
    object.insert("active_phrases".into(), serde_json::json!(ids));
    object.insert("hashes".into(), serde_json::Value::Object(hashes));
    object.insert(
        "keywords_file".into(),
        serde_json::json!(keywords.to_string_lossy()),
    );
    object.remove("test_only");
    Ok(value)
}

/// Packaged base keyword file of a wake manifest (`asset_root/keywords.txt`, read only).
fn base_keywords(base_manifest: &Path) -> io::Result<(serde_json::Value, String)> {
    let base: serde_json::Value = serde_json::from_slice(&read_bounded(base_manifest, 1_048_576)?)?;
    let asset_root = base["asset_root"]
        .as_str()
        .map(PathBuf::from)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "asset root"))?;
    let keywords = String::from_utf8(read_bounded(&asset_root.join("keywords.txt"), 65536)?)
        .map_err(|_| io::Error::other("keywords utf-8"))?;
    Ok((base, keywords))
}

/// Writes a keyword set into `dir` (0700): `keywords.txt` and `manifest.json` (0600), each by temp file and
/// rename. Returns the manifest path. The packaged base files are only read.
pub fn materialize(
    dir: &Path,
    base_manifest: &Path,
    catalog: &[Entry],
    settings: &[Setting],
    global: f32,
) -> io::Result<PathBuf> {
    let (base, base_text) = base_keywords(base_manifest)?;
    let text = keywords_text(&base_text, catalog, settings, global)?;
    let keywords = dir.join("keywords.txt");
    let manifest = dir.join("manifest.json");
    let value = manifest_value(
        &base,
        &keywords,
        &format!("{:x}", Sha256::digest(text.as_bytes())),
        catalog,
        settings,
    )?;
    fs::DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(dir)?;
    write_private(&keywords, text.as_bytes())?;
    write_private(&manifest, &serde_json::to_vec(&value)?)?;
    Ok(manifest)
}

fn write_private(path: &Path, bytes: &[u8]) -> io::Result<()> {
    let temporary = path.with_extension("pending");
    let _ = fs::remove_file(&temporary);
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(&temporary)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    fs::rename(&temporary, path)
}

fn read_bounded(path: &Path, limit: u64) -> io::Result<Vec<u8>> {
    // Packaged assets may be aliases (symlinks); like pack::digest, open the canonical file without following links.
    let canonical = path.canonicalize()?;
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(&canonical)?;
    if !file.metadata()?.is_file() || file.metadata()?.len() > limit {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "bounded read refused",
        ));
    }
    let mut bytes = Vec::new();
    file.take(limit + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "bounded read refused",
        ));
    }
    Ok(bytes)
}

/// Runs a keyword set through the real worker preflight (`wake_worker.py --check`): models, hashes and the
/// keyword file must load. Blocking with a deadline; the Core only calls it on preference changes and boot.
pub fn preflight(python: &Path, home: &Path, manifest: &Path) -> io::Result<()> {
    let args = vec![manifest.to_string_lossy().into_owned(), "--check".into()];
    let mut mounts = crate::live::worker_mounts(manifest)?;
    mounts.push(manifest.parent().unwrap_or(Path::new("/")).to_path_buf());
    let command = crate::transport::namespace_command_in(
        home,
        python,
        "scripts/wake_worker.py",
        &args,
        &mounts,
    )?;
    let mut child = command
        .into_std()
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .stdin(std::process::Stdio::null())
        .spawn()?;
    let started = Instant::now();
    loop {
        if let Some(status) = child.try_wait()? {
            let mut out = String::new();
            if let Some(mut stdout) = child.stdout.take() {
                let _ = stdout.read_to_string(&mut out);
            }
            if status.success()
                && out
                    .lines()
                    .any(|l| l.contains("\"check\": \"ok\"") || l.contains("\"check\":\"ok\""))
            {
                return Ok(());
            }
            return Err(io::Error::other("wake preflight failed"));
        }
        if started.elapsed() > CHECK_TIMEOUT {
            let _ = child.kill();
            let _ = child.wait();
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "wake preflight timeout",
            ));
        }
        std::thread::sleep(Duration::from_millis(20));
    }
}

/// Keyword set kept by the Core: `current` runs at the next start; `previous` is the rollback target.
pub fn runtime_dir(root: &Path) -> PathBuf {
    root.join("wake-runtime")
}

/// Switch to a new keyword set: the running `current` moves to `previous`, the new set is materialized in
/// `current` (its manifest names those final paths) and preflighted there. A failed preflight restores the
/// previous set. The caller commits the ledger next and calls `undo_switch` when that commit fails.
pub fn stage(
    root: &Path,
    python: &Path,
    home: &Path,
    base_manifest: &Path,
    catalog: &[Entry],
    settings: &[Setting],
    global: f32,
) -> io::Result<()> {
    let runtime = runtime_dir(root);
    let current = runtime.join("current");
    let previous = runtime.join("previous");
    let had_current = current.exists();
    if had_current {
        let _ = fs::remove_dir_all(&previous);
        fs::rename(&current, &previous)?;
    }
    let checked = materialize(&current, base_manifest, catalog, settings, global)
        .and_then(|manifest| preflight(python, home, &manifest));
    if let Err(error) = checked {
        let _ = fs::remove_dir_all(&current);
        if had_current {
            let _ = fs::rename(&previous, &current);
            let _ = rebase(&current);
        }
        return Err(error);
    }
    Ok(())
}

/// Points a moved keyword set at its own directory: the manifest names `keywords.txt` next to itself.
fn rebase(dir: &Path) -> io::Result<()> {
    let manifest = dir.join("manifest.json");
    let mut value: serde_json::Value =
        serde_json::from_slice(&read_bounded(&manifest, 1_048_576)?)?;
    value["keywords_file"] = serde_json::json!(dir.join("keywords.txt").to_string_lossy());
    write_private(&manifest, &serde_json::to_vec(&value)?)
}

/// Boot: keeps the stored list in force. `current` is reused when its keyword file already matches the stored
/// list and passes preflight (rollback targets are not rotated on every start). Otherwise the stored list is
/// staged; when that fails, the previous or current set that still passes preflight takes over.
pub fn ensure_boot(
    root: &Path,
    python: &Path,
    home: &Path,
    base_manifest: &Path,
    catalog: &[Entry],
    settings: &[Setting],
    global: f32,
) -> io::Result<PathBuf> {
    let (_, base_text) = base_keywords(base_manifest)?;
    let expected = keywords_text(&base_text, catalog, settings, global)?;
    let current = runtime_dir(root).join("current");
    let manifest = current.join("manifest.json");
    if manifest.is_file()
        && fs::read_to_string(current.join("keywords.txt"))
            .ok()
            .as_deref()
            == Some(expected.as_str())
        && preflight(python, home, &manifest).is_ok()
    {
        return Ok(manifest);
    }
    match stage(root, python, home, base_manifest, catalog, settings, global) {
        Ok(()) => Ok(manifest),
        Err(_) => boot_manifest(root, python, home)
            .ok_or_else(|| io::Error::other("no wake keyword set passes preflight")),
    }
}

/// Keeps the effective list small and valid: known ids only, and at least one active (the default otherwise).
pub fn effective(catalog: &[Entry], settings: &[Setting], default_id: &str) -> Vec<Setting> {
    let known: Vec<Setting> = settings
        .iter()
        .filter(|s| catalog.iter().any(|e| e.id == s.id))
        .cloned()
        .collect();
    if known.iter().any(|s| s.active) {
        known
    } else {
        vec![Setting {
            id: default_id.to_string(),
            active: true,
            sensitivity: None,
        }]
    }
}

/// Packaged wake phrases as catalog entries (the pack is validated before this runs).
pub fn defaults(choices: &[crate::pack::WakeChoice]) -> Vec<Entry> {
    choices
        .iter()
        .map(|choice| Entry {
            id: choice.id.clone(),
            text: choice.text.clone(),
            tokens: choice.tokens.clone(),
            label: choice.label.clone(),
            language: choice.language.clone(),
            boost: choice.boost,
            threshold: choice.threshold,
            qualification: choice.qualification,
            custom: false,
            measurement: None,
        })
        .collect()
}

/// Lexicon named by the pack, read and digest-checked. `None` when the pack declares none or it fails.
pub fn load_lexicon(pack: &Path, base_manifest: &Path) -> Option<Lexicon> {
    let (lexicon, digest) = crate::pack::lexicon_reference(pack).ok()??;
    let (base, _) = base_keywords(base_manifest).ok()?;
    let asset_root = PathBuf::from(base["asset_root"].as_str()?);
    Lexicon::load(&lexicon, &digest, &asset_root.join("tokens.txt")).ok()
}

/// Puts the previous set back as `current` (the commit that followed `stage` failed).
pub fn undo_switch(root: &Path) -> io::Result<()> {
    let runtime = runtime_dir(root);
    let current = runtime.join("current");
    let previous = runtime.join("previous");
    let failed = runtime.join("failed");
    let _ = fs::remove_dir_all(&failed);
    if current.exists() {
        fs::rename(&current, &failed)?;
    }
    if previous.exists() {
        fs::rename(&previous, &current)?;
        rebase(&current)?;
    }
    let _ = fs::remove_dir_all(&failed);
    Ok(())
}

/// Boot: the current set, or the previous one when the current fails its preflight (rollback). Returns the
/// manifest to run, or `None` when neither passes, in which case the packaged manifest stays in charge.
pub fn boot_manifest(root: &Path, python: &Path, home: &Path) -> Option<PathBuf> {
    let runtime = runtime_dir(root);
    for name in ["current", "previous"] {
        let manifest = runtime.join(name).join("manifest.json");
        if manifest.is_file() && preflight(python, home, &manifest).is_ok() {
            return Some(manifest);
        }
    }
    None
}

/// Ready-to-run description of the Core's wake phrase setup.
#[derive(Clone)]
pub struct Runtime {
    pub python: PathBuf,
    pub home: PathBuf,
    pub base_manifest: PathBuf,
    pub lexicon: Option<Arc<Lexicon>>,
    pub tts: Option<crate::tts::Config>,
}

/// Parameters of the synthetic measurement of one custom phrase.
#[derive(Clone, Debug)]
pub struct TestJob {
    pub id: String,
    pub text: String,
    pub tokens: String,
    pub root: PathBuf,
    pub python: PathBuf,
    pub home: PathBuf,
    pub base_manifest: PathBuf,
    pub tts: crate::tts::Config,
    pub catalog: Vec<Entry>,
}

/// Fixed negatives of the synthetic test: sentences that sound like the phrase, and ordinary speech.
pub fn test_negatives(text: &str) -> Vec<String> {
    let words: Vec<&str> = text.split(' ').collect();
    let mut negatives = vec![
        words[1..].join(" "),
        format!("hi {}", words[1..].join(" ")),
        "The weather is nice for a walk today.".to_string(),
        "Please add eggs and milk to the list.".to_string(),
        "I think the music is a little too loud.".to_string(),
        "Open Chrome.".to_string(),
    ];
    negatives.retain(|n| !n.trim().is_empty());
    negatives
}

/// Synthetic positives: the phrase alone, lowercase, and followed by a command (the usual use).
pub fn test_positives(text: &str) -> Vec<String> {
    vec![
        text.to_string(),
        text.to_ascii_lowercase(),
        format!("{text}, what time is it"),
        format!("{text}, open Brave"),
    ]
}

/// Synthetic measurement of one custom phrase: TTS clips of the phrase and of confusable negatives, fed to
/// the KWS in the same keyword environment the phrase would run in. Only `wake_phrase_test` reaches here,
/// after the Core checked that no other measurement runs. Reported as `source: synthetic`.
pub async fn run_test(job: TestJob) -> io::Result<Measurement> {
    let scratch = job.root.join("wake-test").join(&job.id);
    let _ = fs::remove_dir_all(&scratch);
    fs::DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(&scratch)?;
    let setting = Setting {
        id: job.id.clone(),
        active: true,
        sensitivity: None,
    };
    let manifest = materialize(
        &scratch.join("keywords"),
        &job.base_manifest,
        &job.catalog,
        &[setting],
        1.0,
    )?;
    let tts = job.tts.clone();
    let positives = test_positives(&job.text);
    let negatives = test_negatives(&job.text);
    let mut clips = Vec::new();
    for (index, (text, positive)) in positives
        .iter()
        .map(|t| (t, true))
        .chain(negatives.iter().map(|t| (t, false)))
        .enumerate()
    {
        let samples = crate::tts::synthesize_in(&job.home, &tts, text).await?;
        let mut raw = Vec::with_capacity(samples.len() * 2);
        for s in samples {
            raw.extend_from_slice(&((s.clamp(-1.0, 1.0) * 32767.0) as i16).to_le_bytes());
        }
        let file = scratch.join(format!("clip-{index}.s16"));
        write_private(&file, &raw)?;
        clips.push(serde_json::json!({"file": file, "positive": positive, "text": text}));
    }
    let clips_path = scratch.join("clips.json");
    write_private(
        &clips_path,
        &serde_json::to_vec(&serde_json::json!({"clips": clips}))?,
    )?;
    let args = vec![
        manifest.to_string_lossy().into_owned(),
        clips_path.to_string_lossy().into_owned(),
    ];
    let mut mounts = crate::live::worker_mounts(&manifest)?;
    mounts.push(scratch.clone());
    let mut command = crate::transport::namespace_command_in(
        &job.home,
        &job.python,
        "scripts/wake_phrase_test.py",
        &args,
        &mounts,
    )?;
    command
        .kill_on_drop(true)
        .stdin(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    let output = tokio::time::timeout(TEST_TIMEOUT, command.output())
        .await
        .map_err(io::Error::other)??;
    let _ = fs::remove_dir_all(&scratch);
    if !output.status.success() {
        return Err(io::Error::other("wake test failed"));
    }
    let line = output
        .stdout
        .split(|b| *b == b'\n')
        .filter(|l| !l.is_empty())
        .next_back()
        .ok_or_else(|| io::Error::other("wake test silent"))?;
    let result: serde_json::Value = serde_json::from_slice(line)?;
    let count = |key: &str| {
        result[key]
            .as_u64()
            .and_then(|n| u32::try_from(n).ok())
            .ok_or_else(|| io::Error::other("wake test result"))
    };
    let latency = result["latency_ms_median"]
        .as_u64()
        .and_then(|n| u32::try_from(n).ok());
    Measurement::new(
        count("positives")?,
        count("hits")?,
        count("negatives")?,
        count("false_wakes")?,
        latency,
    )
}

/// Reads the custom store (missing file = empty store). Errors refuse the store, never guess content.
pub fn read_custom(root: &Path) -> io::Result<CustomFile> {
    match read_bounded(&root.join("wake-phrases.json"), CUSTOM_LIMIT) {
        Ok(bytes) => {
            let file: CustomFile = serde_json::from_slice(&bytes)?;
            file.validate()?;
            Ok(file)
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(CustomFile::default()),
        Err(error) => Err(error),
    }
}

/// Writes the custom store (0600, temp file, rename, fsync of the directory).
pub fn write_custom(root: &Path, file: &CustomFile) -> io::Result<()> {
    file.validate()?;
    let bytes = serde_json::to_vec(file)?;
    if bytes.len() as u64 > CUSTOM_LIMIT {
        return Err(io::Error::other("custom phrases too large"));
    }
    write_private(&root.join("wake-phrases.json"), &bytes)?;
    fs::File::open(root)?.sync_all()
}

/// Stores the synthetic measurement with its phrase. The store revision advances so open views re-read it.
pub fn record_measurement(root: &Path, id: &str, measurement: Measurement) -> io::Result<()> {
    let mut file = read_custom(root)?;
    let phrase = file
        .phrases
        .iter_mut()
        .find(|p| p.id == id)
        .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "unknown custom phrase"))?;
    phrase.measurement = Some(measurement);
    file.revision = file
        .revision
        .checked_add(1)
        .ok_or_else(|| io::Error::other("store revision exhausted"))?;
    write_custom(root, &file)
}

/// Catalog entries: packaged defaults (from the pack) followed by the custom phrases.
pub fn entries(defaults: &[Entry], custom: &CustomFile) -> Vec<Entry> {
    let mut all = defaults.to_vec();
    for p in &custom.phrases {
        all.push(Entry {
            id: p.id.clone(),
            text: p.text.clone(),
            tokens: p.tokens.clone(),
            label: custom_label(&p.id),
            language: "en".into(),
            boost: DEFAULT_BOOST,
            threshold: DEFAULT_THRESHOLD,
            qualification: "custom",
            custom: true,
            measurement: p.measurement.clone(),
        });
    }
    all
}

/// Snapshot block `wake_phrases` (the bridge validates this shape).
#[derive(Clone, Debug, Serialize)]
pub struct View {
    pub max_active: usize,
    pub max_custom: usize,
    pub custom_revision: u64,
    pub lexicon: bool,
    pub settings: Vec<Setting>,
    pub active: Vec<String>,
    pub phrases: Vec<EntryView>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub test: Option<TestView>,
}

#[derive(Clone, Debug, Serialize)]
pub struct EntryView {
    pub id: String,
    pub text: String,
    pub tokens: String,
    pub label: String,
    pub language: String,
    pub qualification: &'static str,
    pub custom: bool,
    pub selectable: bool,
    pub boost: f32,
    pub threshold: f32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub measurement: Option<Measurement>,
}

#[derive(Clone, Debug, Serialize)]
pub struct TestView {
    pub id: String,
    pub state: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code: Option<&'static str>,
}

impl View {
    pub fn build(
        defaults: &[Entry],
        custom: &CustomFile,
        settings: &[Setting],
        lexicon: bool,
        test: Option<TestView>,
    ) -> Self {
        let all = entries(defaults, custom);
        let active_ids: Vec<String> = active(&all, settings)
            .into_iter()
            .map(|(e, _)| e.id.clone())
            .collect();
        Self {
            max_active: MAX_ACTIVE,
            max_custom: MAX_CUSTOM,
            custom_revision: custom.revision,
            lexicon,
            settings: settings.to_vec(),
            active: active_ids,
            phrases: all
                .iter()
                .map(|e| EntryView {
                    id: e.id.clone(),
                    text: e.text.clone(),
                    tokens: e.tokens.clone(),
                    label: e.label.clone(),
                    language: e.language.clone(),
                    qualification: e.qualification,
                    custom: e.custom,
                    selectable: e.selectable(),
                    boost: e.boost,
                    threshold: e.threshold,
                    measurement: e.measurement.clone(),
                })
                .collect(),
            test,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lexicon() -> Lexicon {
        Lexicon::parse(
            "HEY HH EY1\nGIDEON G IH1 D IY0 AH0 N\nCOMPUTER K AH0 M P Y UW1 T ER0\nOPEN OW1 P AH0 N\nLIGHT L AY1 T\nHI HH AY1\nBRAVE B R EY1 V\nHELLO HH AH0 L OW1\nTHE DH AH0\nWEATHER W EH1 DH ER0\nIS IH1 Z\nNICE N AY1 S\n",
            "HH\nEY1\nG\nIH1\nD\nIY0\nAH0\nN\nK\nM\nP\nY\nUW1\nT\nER0\nOW1\nL\nAY1\nB\nR\nEY1\nV\nW\nDH\nZ\nS\nN\n",
        )
    }

    #[test]
    fn check_rejects_generic_short_and_unknown_phrases_with_codes() {
        let lex = lexicon();
        assert_eq!(check("hey", Some(&lex)).code, code::TOO_FEW_WORDS);
        assert_eq!(check("computer", Some(&lex)).code, code::TOO_FEW_WORDS);
        assert_eq!(check("hey you", Some(&lex)).code, code::TOO_GENERIC);
        assert_eq!(
            check("hey gideon 2", Some(&lex)).code,
            code::INVALID_CHARACTERS
        );
        assert_eq!(check("", Some(&lex)).code, code::EMPTY);
        assert_eq!(check("ok you", Some(&lex)).code, code::TOO_GENERIC);
        assert_eq!(check("hey gideon", None).code, code::LEXICON_UNAVAILABLE);
        assert_eq!(
            check("hey blorf", Some(&lex)).code,
            code::WORD_NOT_IN_LEXICON
        );
        assert_eq!(
            check("hey blorf", Some(&lex)).word.as_deref(),
            Some("blorf")
        );
        // HI (2 phones) + LIGHT (3 phones) is five phones: below the minimum of six.
        assert_eq!(check("hi light", Some(&lex)).code, code::TOO_FEW_TOKENS);
        assert_eq!(
            check("one two three four five", Some(&lex)).code,
            code::TOO_MANY_WORDS
        );
    }

    #[test]
    fn check_accepts_known_phrase_and_normalizes_spaces() {
        let lex = lexicon();
        let ok = check("  hey   gideon ", Some(&lex));
        assert!(ok.ok, "{ok:?}");
        assert_eq!(ok.text.as_deref(), Some("hey gideon"));
        assert_eq!(ok.tokens.as_deref(), Some("HH EY1 G IH1 D IY0 AH0 N"));
        assert!(check("open light", Some(&lex)).ok);
    }

    #[test]
    fn keywords_match_the_measured_default_configuration() {
        // The golden text is the keyword file of docs/evidence/wake-phrases.json (boost 1.2, threshold 0.22).
        let base = "HH EY1 G IH1 D IY0 AH0 N @HEY_GIDEON\nOW2 K EY1 G IH1 D IY0 AH0 N @OKAY_GIDEON\nHH AY1 G IH1 D IY0 AH0 N @REJECT_HI\n";
        let catalog = vec![default_entry("hey_gideon", "HEY_GIDEON", "dev_qualified")];
        let settings = vec![Setting {
            id: "hey_gideon".into(),
            active: true,
            sensitivity: None,
        }];
        let text = keywords_text(base, &catalog, &settings, 1.0).unwrap();
        assert_eq!(
            text,
            "HH EY1 G IH1 D IY0 AH0 N :1.2 #0.22 @HEY_GIDEON\nOW2 K EY1 G IH1 D IY0 AH0 N @OKAY_GIDEON\nHH AY1 G IH1 D IY0 AH0 N @REJECT_HI\n"
        );
        // Sensitivity per phrase moves only its own threshold, on the same scale as the global one.
        let strict = vec![Setting {
            id: "hey_gideon".into(),
            active: true,
            sensitivity: Some(0.5),
        }];
        assert!(keywords_text(base, &catalog, &strict, 1.0)
            .unwrap()
            .contains("#0.33 @HEY_GIDEON"));
    }

    #[test]
    fn keywords_add_custom_phrases_and_refuse_unknown_defaults() {
        let base = "HH EY1 G IH1 D IY0 AH0 N @HEY_GIDEON\nHH AY1 G IH1 D IY0 AH0 N @REJECT_HI\n";
        let mut custom = default_entry("custom_0123456789ab", "CUSTOM_0123456789AB", "custom");
        custom.custom = true;
        custom.tokens = "HH EY1 K AH0 M P Y UW1 T ER0".into();
        let catalog = vec![
            default_entry("hey_gideon", "HEY_GIDEON", "dev_qualified"),
            custom,
        ];
        let settings = vec![
            Setting {
                id: "custom_0123456789ab".into(),
                active: true,
                sensitivity: None,
            },
            Setting {
                id: "hey_gideon".into(),
                active: true,
                sensitivity: None,
            },
        ];
        let text = keywords_text(base, &catalog, &settings, 1.0).unwrap();
        assert!(text.ends_with("HH EY1 K AH0 M P Y UW1 T ER0 :1.2 #0.22 @CUSTOM_0123456789AB\n"));
        assert!(text.contains("@HEY_GIDEON\n"));
        // A default whose base line is missing cannot be turned into a keyword set.
        assert!(keywords_text(
            "HH AY1 G IH1 D IY0 AH0 N @REJECT_HI\n",
            &catalog,
            &settings,
            1.0
        )
        .is_err());
    }

    #[test]
    fn measurement_pass_is_computed_and_settings_are_bounded() {
        assert!(Measurement::new(4, 3, 6, 0, Some(900)).unwrap().passed);
        assert!(!Measurement::new(4, 2, 6, 0, None).unwrap().passed);
        assert!(!Measurement::new(4, 4, 6, 1, None).unwrap().passed);
        assert!(Measurement::new(0, 0, 6, 0, None).is_err());
        let many: Vec<Setting> = (0..6)
            .map(|i| Setting {
                id: format!("p{i}"),
                active: true,
                sensitivity: None,
            })
            .collect();
        assert!(!valid_settings(&many));
        assert!(!valid_settings(&[Setting {
            id: "x y".into(),
            active: true,
            sensitivity: None
        }]));
        assert!(!valid_settings(&[Setting {
            id: "a".into(),
            active: true,
            sensitivity: Some(2.0)
        }]));
    }

    #[test]
    fn legacy_single_phrase_migrates_to_one_active_entry() {
        let legacy = migrated(&[], Some("okay_gideon"), "hey_gideon");
        assert_eq!(
            legacy,
            vec![Setting {
                id: "okay_gideon".into(),
                active: true,
                sensitivity: None
            }]
        );
        let fresh = migrated(&[], None, "hey_gideon");
        assert_eq!(fresh[0].id, "hey_gideon");
        // A stored list always wins over the legacy field.
        let stored = [Setting {
            id: "hey_gideon".into(),
            active: false,
            sensitivity: Some(1.2),
        }];
        assert_eq!(
            migrated(&stored, Some("okay_gideon"), "hey_gideon"),
            stored.to_vec()
        );
    }

    fn default_entry(id: &str, label: &str, qualification: &'static str) -> Entry {
        Entry {
            id: id.into(),
            text: "Hey Gideon".into(),
            tokens: "HH EY1 G IH1 D IY0 AH0 N".into(),
            label: label.into(),
            language: "en".into(),
            boost: DEFAULT_BOOST,
            threshold: DEFAULT_THRESHOLD,
            qualification,
            custom: false,
            measurement: None,
        }
    }
}
