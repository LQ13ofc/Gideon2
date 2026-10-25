//! One internal Base pack, preflight and presentation metadata; no model manager.
use crate::wake::WakeDescriptor;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    io::{self, Read},
    os::unix::fs::OpenOptionsExt,
    path::{Path, PathBuf},
};
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Reference {
    path: PathBuf,
    sha256: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Phrase {
    text: String,
    evidence: Reference,
    /// KWS phone transcription (`HH EY1 G ...`). Required: custom phrases are tokenized the same way.
    tokens: String,
    #[serde(default)]
    language: Option<String>,
    /// Keyword boost and base threshold of the phrase; the evidence file must measure the same values.
    #[serde(default)]
    boost: Option<f32>,
    #[serde(default)]
    threshold: Option<f32>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Definition {
    version: u16,
    id: String,
    wake_profile_sha256: String,
    stt_profile_sha256: String,
    tts_profile_sha256: String,
    qualification_profile: Reference,
    /// Pronunciation lexicon pinned by digest; needed to tokenize custom phrases (absent = no custom phrases).
    #[serde(default)]
    lexicon: Option<Reference>,
    phrases: BTreeMap<String, Phrase>,
}
#[derive(Clone, Debug, Serialize)]
pub struct WakeChoice {
    pub id: String,
    pub text: String,
    pub qualification: &'static str,
    /// Keyword label (`HEY_GIDEON`), KWS phones, language and tuned boost/threshold of the phrase.
    pub label: String,
    pub tokens: String,
    pub language: String,
    pub boost: f32,
    pub threshold: f32,
}
#[derive(Clone, Debug, Serialize)]
pub struct Snapshot {
    pub version: u16,
    pub id: String,
    /// DIAG-01: SHA-256 (lowercase hex) of the pack definition file this snapshot was loaded from.
    pub pack_sha256: String,
    pub scope: &'static str,
    pub preflight: &'static str,
    pub engines: BTreeMap<String, String>,
    pub wake_phrases: Vec<WakeChoice>,
    pub active_phrase: Option<String>,
    pub default_phrase: String,
    pub voice: &'static str,
    pub language: String,
    pub audio_input: &'static str,
    pub audio_output: &'static str,
}
impl Snapshot {
    pub fn selectable(&self, id: &str) -> bool {
        self.wake_phrases
            .iter()
            .any(|p| p.id == id && p.qualification == "dev_qualified")
    }
    pub fn text(&self, id: &str) -> Option<&str> {
        self.wake_phrases
            .iter()
            .find(|p| p.id == id)
            .map(|p| p.text.as_str())
    }
}
fn invalid() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, "incompatible Base pack")
}
fn digest(path: &Path) -> io::Result<String> {
    if !path.is_absolute() {
        return Err(invalid());
    }
    // Existing public engine assets use local aliases. Pin opened canonical bytes.
    let path = path.canonicalize()?;
    if !std::fs::symlink_metadata(&path)?.is_file() {
        return Err(invalid());
    }
    let mut file = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(&path)?;
    if !file.metadata()?.is_file() {
        return Err(invalid());
    }
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 65536];
    loop {
        let n = file.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        hash.update(&buffer[..n]);
    }
    Ok(format!("{:x}", hash.finalize()))
}
fn verified(path: &Path, expected: &str) -> io::Result<()> {
    if expected.len() != 64
        || !expected.bytes().all(|b| b.is_ascii_hexdigit())
        || digest(path)? != expected
    {
        return Err(invalid());
    }
    Ok(())
}
/// Raw bytes of a JSON pack file: absolute, regular, never a symlink, at most 1 MiB.
fn json_bytes(path: &Path) -> io::Result<Vec<u8>> {
    let file = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)?;
    if !path.is_absolute() || !file.metadata()?.is_file() || file.metadata()?.len() > 1_048_576 {
        return Err(invalid());
    }
    let mut data = Vec::new();
    file.take(1_048_577).read_to_end(&mut data)?;
    if data.len() > 1_048_576 {
        return Err(invalid());
    }
    Ok(data)
}
fn json(path: &Path) -> io::Result<serde_json::Value> {
    serde_json::from_slice(&json_bytes(path)?).map_err(|_| invalid())
}
/// DIAG-01: SHA-256 (lowercase hex) of the pack definition file, over the same bytes `load` reads.
pub fn definition_sha256(path: &Path) -> io::Result<String> {
    Ok(format!("{:x}", Sha256::digest(json_bytes(path)?)))
}
fn text(value: &serde_json::Value) -> io::Result<&str> {
    value.as_str().ok_or_else(invalid)
}
/// KWS phone transcription: 1..=200 bytes of upper-case phones (with stress digits) separated by spaces.
fn valid_tokens(tokens: &str) -> bool {
    !tokens.is_empty()
        && tokens.len() <= 200
        && tokens.split(' ').all(|p| {
            !p.is_empty()
                && p.bytes()
                    .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit())
        })
}
/// Path and digest of the pronunciation lexicon of a pack, when the pack declares one.
pub fn lexicon_reference(path: &Path) -> io::Result<Option<(PathBuf, String)>> {
    let def: Definition = serde_json::from_value(json(path)?).map_err(|_| invalid())?;
    Ok(def.lexicon.map(|l| (l.path, l.sha256)))
}
fn artifacts(root: &str, hashes: &serde_json::Value) -> io::Result<()> {
    let root = Path::new(root);
    let map = hashes.as_object().ok_or_else(invalid)?;
    if !root.is_absolute() || map.is_empty() || map.len() > 16 {
        return Err(invalid());
    }
    for (name, hash) in map {
        if name.is_empty()
            || name.len() > 128
            || !name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
            || name == ".."
        {
            return Err(invalid());
        }
        verified(&root.join(name), text(hash)?)?;
    }
    Ok(())
}
pub fn load(path: &Path, wake_path: &Path, tts_path: &Path) -> io::Result<Snapshot> {
    let raw_bytes = json_bytes(path)?;
    let pack_sha256 = format!("{:x}", Sha256::digest(&raw_bytes));
    let raw: serde_json::Value = serde_json::from_slice(&raw_bytes).map_err(|_| invalid())?;
    let def: Definition = serde_json::from_value(raw).map_err(|_| invalid())?;
    if def.version != 1
        || !crate::protocol::valid_id(&def.id)
        || def.phrases.is_empty()
        || def.phrases.len() > 8
    {
        return Err(invalid());
    }
    verified(wake_path, &def.wake_profile_sha256)?;
    verified(tts_path, &def.tts_profile_sha256)?;
    let wake = json(wake_path)?;
    let descriptor: WakeDescriptor = serde_json::from_value(wake.clone()).map_err(|_| invalid())?;
    descriptor.validate().map_err(|_| invalid())?;
    let stt_path = PathBuf::from(text(&wake["stt"]["manifest"])?);
    verified(&stt_path, &def.stt_profile_sha256)?;
    let stt = json(&stt_path)?;
    let tts = json(tts_path)?;
    verified(
        &def.qualification_profile.path,
        &def.qualification_profile.sha256,
    )?;
    let qualification = json(&def.qualification_profile.path)?;
    for field in [
        "engine",
        "supported_phrases",
        "rejection_labels",
        "hashes",
        "encoder",
        "decoder",
        "joiner",
        "asset_root",
    ] {
        if qualification[field].is_null() || qualification[field] != wake[field] {
            return Err(invalid());
        }
    }
    if descriptor.supported_phrases.keys().ne(def.phrases.keys()) {
        return Err(invalid());
    }
    let required_wake = [
        text(&wake["encoder"])?,
        text(&wake["decoder"])?,
        text(&wake["joiner"])?,
        "tokens.txt",
        "keywords.txt",
    ];
    let wake_hashes = wake["hashes"].as_object().ok_or_else(invalid)?;
    if wake_hashes.len() != required_wake.len()
        || required_wake
            .iter()
            .any(|name| !wake_hashes.contains_key(*name))
    {
        return Err(invalid());
    }
    let required_stt = [
        "adapter.ort",
        "cross_kv.ort",
        "decoder_kv.ort",
        "encoder.ort",
        "frontend.model.ort",
        "frontend.weights.ort",
        "streaming_config.json",
        "tokenizer.bin",
    ];
    let stt_hashes = stt["hashes"].as_object().ok_or_else(invalid)?;
    if stt_hashes.len() != required_stt.len()
        || required_stt
            .iter()
            .any(|name| !stt_hashes.contains_key(*name))
        || stt["provider"] != "CPU"
    {
        return Err(invalid());
    }
    artifacts(text(&wake["asset_root"])?, &wake["hashes"])?;
    verified(
        Path::new(text(&wake["vad"]["path"])?),
        text(&wake["vad"]["sha256"])?,
    )?;
    artifacts(text(&stt["model_root"])?, &stt["hashes"])?;
    let tts_root = Path::new(text(&tts["root"])?);
    let items = tts["artifacts"].as_array().ok_or_else(invalid)?;
    let mut hashes = serde_json::Map::new();
    for item in items {
        if hashes
            .insert(text(&item["name"])?.into(), item["sha256"].clone())
            .is_some()
        {
            return Err(invalid());
        }
    }
    if hashes.len() != 4
        || [
            "model.safetensors",
            "tokenizer.json",
            "alba.safetensors",
            "config.yaml",
        ]
        .iter()
        .any(|name| !hashes.contains_key(*name))
    {
        return Err(invalid());
    }
    if text(&tts["config"])? != tts_root.join("config.yaml").to_str().ok_or_else(invalid)? {
        return Err(invalid());
    }
    artifacts(text(&tts["root"])?, &serde_json::Value::Object(hashes))?;
    if text(&stt["language"])? != "en"
        || text(&tts["voice"])?
            != tts_root
                .join("alba.safetensors")
                .to_str()
                .ok_or_else(invalid)?
    {
        return Err(invalid());
    }
    let mut choices = Vec::new();
    if let Some(lexicon) = &def.lexicon {
        verified(&lexicon.path, &lexicon.sha256)?;
    }
    for (id, phrase) in def.phrases {
        if phrase.text.trim() != phrase.text
            || phrase.text.is_empty()
            || phrase.text.len() > 128
            || phrase.text.chars().any(char::is_control)
        {
            return Err(invalid());
        }
        verified(&phrase.evidence.path, &phrase.evidence.sha256)?;
        let evidence = json(&phrase.evidence.path)?;
        if evidence["engine"] != wake["engine"]
            || text(&evidence["active_phrase"])? != id
            || text(&evidence["manifest_sha256"])? != def.qualification_profile.sha256
        {
            return Err(invalid());
        }
        let boost = phrase.boost.unwrap_or(crate::phrases::DEFAULT_BOOST);
        let base_threshold = phrase
            .threshold
            .unwrap_or(crate::phrases::DEFAULT_THRESHOLD);
        // Boost 0 is the unboosted measurement (the packaged Okay phrase); it stays in the keyword file.
        let well_formed = (0.0..=10.0).contains(&boost)
            && base_threshold > 0.0
            && base_threshold < 1.0
            && valid_tokens(&phrase.tokens);
        if !well_formed {
            return Err(invalid());
        }
        // The evidence measured exactly this boost and threshold (the keyword line it describes).
        let measured = |value: &serde_json::Value, expected: f32| {
            value
                .as_f64()
                .is_some_and(|v| (v - f64::from(expected)).abs() < 1e-6)
        };
        if !measured(&evidence["threshold"], base_threshold)
            || !measured(&evidence["boost"], boost)
            || evidence["score"].as_f64() != Some(1.)
            || evidence["threads"].as_u64() != Some(1)
            || evidence["provider"] != "cpu"
        {
            return Err(invalid());
        }
        let positives = evidence["positive_count"]
            .as_u64()
            .filter(|n| *n > 0)
            .ok_or_else(invalid)?;
        let detected = evidence["detected_positive"]
            .as_u64()
            .filter(|n| *n <= positives)
            .ok_or_else(invalid)?;
        let recall = evidence["recall"].as_f64().ok_or_else(invalid)?;
        if (recall - detected as f64 / positives as f64).abs() > 1e-12
            || evidence["negative_count"].as_u64().unwrap_or(0) == 0
        {
            return Err(invalid());
        }
        let qualified = evidence["quality"] == "PASS_DEV_ONLY"
            && (0.95..=1.).contains(&recall)
            && evidence["false_wakes"].as_u64() == Some(0)
            && evidence["procedural_silence"]["seconds"]
                .as_f64()
                .is_some_and(|n| n >= 3600.);
        choices.push(WakeChoice {
            label: crate::phrases::label_of(&id),
            id,
            text: phrase.text,
            qualification: if qualified {
                "dev_qualified"
            } else {
                "poc_required"
            },
            tokens: phrase.tokens,
            language: phrase.language.unwrap_or_else(|| "en".into()),
            boost,
            threshold: base_threshold,
        });
    }
    let snapshot = Snapshot {
        version: 1,
        id: def.id,
        pack_sha256,
        scope: "dev_virtual_en",
        preflight: "verified",
        engines: BTreeMap::from([
            ("wake".into(), descriptor.engine),
            ("stt".into(), text(&stt["engine"])?.into()),
            ("tts".into(), text(&tts["engine"])?.into()),
        ]),
        wake_phrases: choices,
        active_phrase: Some(descriptor.active_phrase.clone()),
        default_phrase: descriptor.active_phrase,
        voice: "Alba",
        language: "en".into(),
        audio_input: "virtual_pcm",
        audio_output: "virtual",
    };
    if snapshot
        .engines
        .values()
        .any(|id| id.is_empty() || id.len() > 160 || id.chars().any(char::is_control))
        || !snapshot.selectable(&snapshot.default_phrase)
    {
        return Err(invalid());
    }
    Ok(snapshot)
}
