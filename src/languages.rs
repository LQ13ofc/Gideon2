//! Idiomas de fala (TTS) e de transcrição (STT) por motor, com estado honesto por idioma.
//!
//! O catálogo é dado versionado (`languages_catalog.json`) validado ao carregar. Só entrada `bundled` é
//! selecionável; `available_not_installed` aparece na UI com motivo e `unsupported` nunca é aceito.
//! Português e francês ficam `available_not_installed` (sem arquivos baixados) até o dono aprovar downloads.
use crate::storage::Config;
use serde::{Deserialize, Serialize};
use std::io;

pub const CATALOG_JSON: &str = include_str!("languages_catalog.json");
pub const MAX_STT_LANGUAGES: usize = 3;
pub const MAX_ENTRIES: usize = 64;
pub const DEFAULT_STT_LANGUAGE: &str = "en";
pub const DEFAULT_TTS_LANGUAGE: &str = "en";
pub const DEFAULT_TTS_VOICE: &str = "alba";
/// Shown on every not-installed language and on the install control, until the owner approves downloads.
pub const INSTALL_REASON: &str = "Aguardando aprovação do download pelo dono";
const KINDS: [&str; 3] = ["stt", "tts", "wake"];

/// Refusal codes of `validate_selection`; they map to Portuguese messages in app/bridge.py.
pub const CODE_INVALID: &str = "invalid_languages";
pub const CODE_NOT_INSTALLED: &str = "language_not_installed";
pub const CODE_UNSUPPORTED: &str = "language_unsupported";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum State {
    Bundled,
    AvailableNotInstalled,
    Unsupported,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Entry {
    pub kind: String,
    pub language: String,
    pub label: String,
    pub state: State,
    pub engine: Option<String>,
    pub size_bytes: Option<u64>,
    pub size_partial: bool,
    pub size_note: Option<String>,
    pub license: Option<String>,
    pub sha256: Option<String>,
    pub quality: String,
    pub evidence: Option<String>,
    pub voices: Vec<String>,
    pub reason: Option<String>,
    pub source: String,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
struct Document {
    version: u16,
    entries: Vec<Entry>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct LanguageCatalog {
    entries: Vec<Entry>,
}

/// The languages the Core will run with. Stored in `Config`; the same values are the restart baseline.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Selection {
    pub stt: Vec<String>,
    pub tts_language: String,
    pub tts_voice: String,
}

impl Selection {
    pub fn from_config(config: &Config) -> Self {
        Self {
            stt: config.stt_languages.clone(),
            tts_language: config.tts_language.clone(),
            tts_voice: config.tts_voice.clone(),
        }
    }
}

fn invalid(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

/// Language tags are short BCP-47-like ASCII labels: `en`, `pt-BR`, `fr`.
pub fn valid_tag(tag: &str) -> bool {
    (2..=8).contains(&tag.len()) && tag.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')
}

fn text_ok(value: &str, limit: usize) -> bool {
    !value.trim().is_empty() && value.len() <= limit && !value.chars().any(char::is_control)
}

fn optional_text_ok(value: &Option<String>, limit: usize) -> bool {
    value.as_deref().is_none_or(|v| text_ok(v, limit))
}

fn sha256_ok(value: &Option<String>) -> bool {
    value
        .as_deref()
        .is_none_or(|h| h.len() == 64 && h.bytes().all(|b| b.is_ascii_hexdigit()))
}

impl LanguageCatalog {
    /// Parses and validates the catalog. Every rule is checked here so the Core never sees a half-valid table.
    pub fn parse(bytes: &[u8]) -> io::Result<Self> {
        let document: Document =
            serde_json::from_slice(bytes).map_err(|_| invalid("catálogo de idiomas inválido"))?;
        if document.version != 1
            || document.entries.is_empty()
            || document.entries.len() > MAX_ENTRIES
        {
            return Err(invalid("catálogo de idiomas inválido"));
        }
        let mut seen: Vec<(&str, &str)> = Vec::new();
        for entry in &document.entries {
            if !KINDS.contains(&entry.kind.as_str())
                || !valid_tag(&entry.language)
                || seen.contains(&(entry.kind.as_str(), entry.language.as_str()))
                || !text_ok(&entry.label, 40)
                || !text_ok(&entry.quality, 120)
                || !text_ok(&entry.source, 200)
                || !optional_text_ok(&entry.engine, 160)
                || !optional_text_ok(&entry.size_note, 200)
                || !optional_text_ok(&entry.license, 200)
                || !optional_text_ok(&entry.evidence, 200)
                || !optional_text_ok(&entry.reason, 200)
                || !sha256_ok(&entry.sha256)
                || entry.voices.len() > 8
                || entry.voices.iter().any(|v| !crate::protocol::valid_id(v))
            {
                return Err(invalid("catálogo de idiomas inválido"));
            }
            seen.push((entry.kind.as_str(), entry.language.as_str()));
            let installable = matches!(entry.state, State::Bundled | State::AvailableNotInstalled);
            // An installable language names its engine and license; an unsupported one says why.
            if installable
                && (entry.engine.is_none() || entry.license.is_none() || entry.reason.is_some())
            {
                return Err(invalid("catálogo de idiomas inválido"));
            }
            if !installable && (entry.reason.is_none() || entry.engine.is_some()) {
                return Err(invalid("catálogo de idiomas inválido"));
            }
            // Only speech output has voices; a bundled speech output needs at least one.
            if entry.kind != "tts" && !entry.voices.is_empty() {
                return Err(invalid("catálogo de idiomas inválido"));
            }
            if entry.kind == "tts" && entry.state == State::Bundled && entry.voices.is_empty() {
                return Err(invalid("catálogo de idiomas inválido"));
            }
        }
        // English is bundled for every engine kind and is the default.
        for kind in KINDS {
            let english = document
                .entries
                .iter()
                .find(|e| e.kind == kind && e.language == "en")
                .ok_or_else(|| invalid("catálogo de idiomas inválido"))?;
            if english.state != State::Bundled {
                return Err(invalid("catálogo de idiomas inválido"));
            }
        }
        let english_voice = document
            .entries
            .iter()
            .find(|e| e.kind == "tts" && e.language == DEFAULT_TTS_LANGUAGE)
            .is_some_and(|e| e.voices.iter().any(|v| v == DEFAULT_TTS_VOICE));
        if !english_voice {
            return Err(invalid("catálogo de idiomas inválido"));
        }
        Ok(Self {
            entries: document.entries,
        })
    }

    /// The catalog compiled into the binary; validated by the unit tests and at Core start.
    pub fn builtin() -> io::Result<Self> {
        Self::parse(CATALOG_JSON.as_bytes())
    }

    pub fn entry(&self, kind: &str, language: &str) -> Option<&Entry> {
        self.entries
            .iter()
            .find(|e| e.kind == kind && e.language == language)
    }

    /// Checks one language of one kind; `voice` is required for `tts`.
    fn check(&self, kind: &str, language: &str, voice: Option<&str>) -> Result<(), &'static str> {
        let entry = self.entry(kind, language).ok_or(CODE_INVALID)?;
        match entry.state {
            State::Bundled => {}
            State::AvailableNotInstalled => return Err(CODE_NOT_INSTALLED),
            State::Unsupported => return Err(CODE_UNSUPPORTED),
        }
        if let Some(voice) = voice {
            if !entry.voices.iter().any(|v| v == voice) {
                return Err(CODE_INVALID);
            }
        }
        Ok(())
    }

    /// Accepts only installed (`bundled`) languages: 1..=3 distinct for STT, one voice for TTS.
    pub fn validate_selection(
        &self,
        stt: &[String],
        tts_language: &str,
        tts_voice: &str,
    ) -> Result<(), &'static str> {
        if stt.is_empty() || stt.len() > MAX_STT_LANGUAGES {
            return Err(CODE_INVALID);
        }
        for (index, language) in stt.iter().enumerate() {
            if stt[..index].contains(language) {
                return Err(CODE_INVALID);
            }
            self.check("stt", language, None)?;
        }
        self.check("tts", tts_language, Some(tts_voice))
    }

    pub fn selection_installed(&self, selection: &Selection) -> bool {
        self.validate_selection(
            &selection.stt,
            &selection.tts_language,
            &selection.tts_voice,
        )
        .is_ok()
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct ItemView {
    pub id: String,
    pub kind: String,
    pub label: String,
    pub state: State,
    pub engine: Option<String>,
    pub size_bytes: Option<u64>,
    pub size_partial: bool,
    pub size_note: Option<String>,
    pub license: Option<String>,
    pub sha256: Option<String>,
    pub quality: String,
    pub evidence: Option<String>,
    pub voices: Vec<String>,
    pub reason: Option<String>,
    pub selected: bool,
    pub selectable: bool,
    pub source: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Engines {
    pub stt: Vec<ItemView>,
    pub tts: Vec<ItemView>,
    pub wake: Vec<ItemView>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Restart {
    pub stt: bool,
    pub tts: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct Install {
    pub available: bool,
    pub reason: &'static str,
}

/// The snapshot block `languages`. It carries no audio or user content.
#[derive(Debug, Clone, Serialize)]
pub struct View {
    pub version: u16,
    pub engines: Engines,
    pub stt_selected: Vec<String>,
    pub tts_selected: String,
    pub tts_voice: String,
    pub restart_required: Restart,
    pub install: Install,
}

fn item(entry: &Entry, selected: bool) -> ItemView {
    let reason = match entry.state {
        State::AvailableNotInstalled => Some(format!("Não instalado: {INSTALL_REASON}")),
        _ => entry.reason.clone(),
    };
    ItemView {
        id: entry.language.clone(),
        kind: entry.kind.clone(),
        label: entry.label.clone(),
        state: entry.state,
        engine: entry.engine.clone(),
        size_bytes: entry.size_bytes,
        size_partial: entry.size_partial,
        size_note: entry.size_note.clone(),
        license: entry.license.clone(),
        sha256: entry.sha256.clone(),
        quality: entry.quality.clone(),
        evidence: entry.evidence.clone(),
        voices: entry.voices.clone(),
        reason,
        selected,
        selectable: entry.state == State::Bundled,
        source: entry.source.clone(),
    }
}

/// Builds the snapshot block. `applied` is the selection the running workers were started with; any
/// difference means the stored choice takes effect only after a Core restart.
pub fn view(catalog: &LanguageCatalog, config: &Config, applied: Option<&Selection>) -> View {
    let stored = Selection::from_config(config);
    let items = |kind: &str, selected: &dyn Fn(&str) -> bool| -> Vec<ItemView> {
        catalog
            .entries
            .iter()
            .filter(|e| e.kind == kind)
            .map(|e| item(e, selected(&e.language)))
            .collect()
    };
    View {
        version: 1,
        engines: Engines {
            stt: items("stt", &|id: &str| stored.stt.iter().any(|s| s == id)),
            tts: items("tts", &|id: &str| stored.tts_language == id),
            wake: items("wake", &|_: &str| false),
        },
        stt_selected: stored.stt.clone(),
        tts_selected: stored.tts_language.clone(),
        tts_voice: stored.tts_voice.clone(),
        restart_required: Restart {
            stt: applied.is_some_and(|a| a.stt != stored.stt),
            tts: applied.is_some_and(|a| {
                a.tts_language != stored.tts_language || a.tts_voice != stored.tts_voice
            }),
        },
        install: Install {
            available: false,
            reason: INSTALL_REASON,
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const EN_BUNDLED: &str = r#"
        {"kind":"stt","language":"en","label":"Inglês","state":"bundled","engine":"m","size_bytes":null,"size_partial":false,"size_note":null,"license":"MIT","sha256":null,"quality":"medido","evidence":null,"voices":[],"reason":null,"source":"s"},
        {"kind":"tts","language":"en","label":"Inglês","state":"bundled","engine":"p","size_bytes":null,"size_partial":false,"size_note":null,"license":"CC","sha256":null,"quality":"medido","evidence":null,"voices":["alba"],"reason":null,"source":"s"},
        {"kind":"wake","language":"en","label":"Inglês","state":"bundled","engine":"k","size_bytes":null,"size_partial":false,"size_note":null,"license":"x","sha256":null,"quality":"medido","evidence":null,"voices":[],"reason":null,"source":"s"}
    "#;

    fn document(extra: &str) -> String {
        format!(r#"{{"version":1,"entries":[{EN_BUNDLED}{extra}]}}"#)
    }

    fn parse(extra: &str) -> io::Result<LanguageCatalog> {
        LanguageCatalog::parse(document(extra).as_bytes())
    }

    fn fr_stt_not_installed() -> &'static str {
        r#",{"kind":"stt","language":"fr","label":"Francês","state":"available_not_installed","engine":"v","size_bytes":1,"size_partial":true,"size_note":null,"license":"Apache","sha256":null,"quality":"não medido","evidence":null,"voices":[],"reason":null,"source":"s"}"#
    }

    fn selection(stt: &[&str], tts: &str, voice: &str) -> (Vec<String>, String, String) {
        (
            stt.iter().map(|s| s.to_string()).collect(),
            tts.into(),
            voice.into(),
        )
    }

    #[test]
    fn builtin_catalog_parses_and_keeps_pt_and_fr_uninstalled() {
        let catalog = LanguageCatalog::builtin().expect("catálogo embutido válido");
        assert_eq!(catalog.entry("stt", "en").unwrap().state, State::Bundled);
        assert_eq!(
            catalog.entry("tts", "en").unwrap().voices,
            vec!["alba".to_string()]
        );
        for (kind, lang) in [
            ("stt", "fr"),
            ("stt", "pt-BR"),
            ("tts", "fr"),
            ("tts", "pt-BR"),
        ] {
            assert_eq!(
                catalog.entry(kind, lang).unwrap().state,
                State::AvailableNotInstalled,
                "{kind} {lang}"
            );
        }
        for lang in ["fr", "pt-BR"] {
            assert_eq!(
                catalog.entry("wake", lang).unwrap().state,
                State::Unsupported
            );
        }
    }

    #[test]
    fn rejects_structural_errors() {
        assert!(LanguageCatalog::parse(br#"{"version":2,"entries":[]}"#).is_err());
        assert!(LanguageCatalog::parse(b"not json").is_err());
        // Duplicate (kind, language).
        assert!(parse(fr_stt_not_installed()).is_ok());
        assert!(parse(&format!(
            "{}{}",
            fr_stt_not_installed(),
            fr_stt_not_installed()
        ))
        .is_err());
        // Unknown field, unknown kind, bad tag, bad sha256.
        assert!(parse(r#",{"kind":"stt","language":"fr","label":"x","state":"unsupported","engine":null,"size_bytes":null,"size_partial":false,"size_note":null,"license":null,"sha256":null,"quality":"q","evidence":null,"voices":[],"reason":"r","source":"s","extra":1}"#).is_err());
        assert!(parse(r#",{"kind":"llm","language":"fr","label":"x","state":"unsupported","engine":null,"size_bytes":null,"size_partial":false,"size_note":null,"license":null,"sha256":null,"quality":"q","evidence":null,"voices":[],"reason":"r","source":"s"}"#).is_err());
        assert!(parse(r#",{"kind":"stt","language":"f r","label":"x","state":"unsupported","engine":null,"size_bytes":null,"size_partial":false,"size_note":null,"license":null,"sha256":null,"quality":"q","evidence":null,"voices":[],"reason":"r","source":"s"}"#).is_err());
        assert!(parse(r#",{"kind":"stt","language":"fr","label":"x","state":"available_not_installed","engine":"v","size_bytes":null,"size_partial":false,"size_note":null,"license":"A","sha256":"zz","quality":"q","evidence":null,"voices":[],"reason":null,"source":"s"}"#).is_err());
    }

    #[test]
    fn rejects_state_and_voice_contract_violations() {
        // Installable without engine/license; unsupported without reason.
        assert!(parse(r#",{"kind":"stt","language":"fr","label":"x","state":"available_not_installed","engine":null,"size_bytes":null,"size_partial":false,"size_note":null,"license":"A","sha256":null,"quality":"q","evidence":null,"voices":[],"reason":null,"source":"s"}"#).is_err());
        assert!(parse(r#",{"kind":"wake","language":"fr","label":"x","state":"unsupported","engine":null,"size_bytes":null,"size_partial":false,"size_note":null,"license":null,"sha256":null,"quality":"q","evidence":null,"voices":[],"reason":null,"source":"s"}"#).is_err());
        // Voices on STT; bundled TTS without voice.
        assert!(parse(r#",{"kind":"stt","language":"fr","label":"x","state":"unsupported","engine":null,"size_bytes":null,"size_partial":false,"size_note":null,"license":null,"sha256":null,"quality":"q","evidence":null,"voices":["x"],"reason":"r","source":"s"}"#).is_err());
        assert!(parse(r#",{"kind":"tts","language":"fr","label":"x","state":"bundled","engine":"p","size_bytes":null,"size_partial":false,"size_note":null,"license":"A","sha256":null,"quality":"q","evidence":null,"voices":[],"reason":null,"source":"s"}"#).is_err());
        // English missing, or English not bundled, or default voice missing.
        let no_en_wake = EN_BUNDLED.replace(
            r#"{"kind":"wake","language":"en""#,
            r#"{"kind":"wake","language":"xx""#,
        );
        assert!(LanguageCatalog::parse(
            format!(r#"{{"version":1,"entries":[{no_en_wake}]}}"#).as_bytes()
        )
        .is_err());
        let alba_missing = EN_BUNDLED.replace(r#""voices":["alba"]"#, r#""voices":["bob"]"#);
        assert!(LanguageCatalog::parse(
            format!(r#"{{"version":1,"entries":[{alba_missing}]}}"#).as_bytes()
        )
        .is_err());
    }

    #[test]
    fn selection_accepts_only_installed_languages_with_stable_codes() {
        let pt_tts = r#",{"kind":"tts","language":"pt-BR","label":"Português (Brasil)","state":"available_not_installed","engine":"p","size_bytes":null,"size_partial":false,"size_note":null,"license":"CC","sha256":null,"quality":"não medido","evidence":null,"voices":[],"reason":null,"source":"s"}"#;
        let catalog = parse(&format!("{}{}", fr_stt_not_installed(), pt_tts)).unwrap();
        let (stt, tts, voice) = selection(&["en"], "en", "alba");
        assert_eq!(catalog.validate_selection(&stt, &tts, &voice), Ok(()));
        let (stt, tts, voice) = selection(&["fr"], "en", "alba");
        assert_eq!(
            catalog.validate_selection(&stt, &tts, &voice),
            Err(CODE_NOT_INSTALLED)
        );
        let (stt, tts, voice) = selection(&["en"], "pt-BR", "alba");
        assert_eq!(
            catalog.validate_selection(&stt, &tts, &voice),
            Err(CODE_NOT_INSTALLED)
        );
        let (stt, tts, voice) = selection(&["de"], "en", "alba");
        assert_eq!(
            catalog.validate_selection(&stt, &tts, &voice),
            Err(CODE_INVALID)
        );
        let (stt, tts, voice) = selection(&["en"], "en", "bob");
        assert_eq!(
            catalog.validate_selection(&stt, &tts, &voice),
            Err(CODE_INVALID)
        );
        let (stt, tts, voice) = selection(&[], "en", "alba");
        assert_eq!(
            catalog.validate_selection(&stt, &tts, &voice),
            Err(CODE_INVALID)
        );
        let (stt, tts, voice) = selection(&["en", "en"], "en", "alba");
        assert_eq!(
            catalog.validate_selection(&stt, &tts, &voice),
            Err(CODE_INVALID)
        );
        let (stt, tts, voice) = selection(&["en", "en", "en", "en"], "en", "alba");
        assert_eq!(
            catalog.validate_selection(&stt, &tts, &voice),
            Err(CODE_INVALID)
        );
        // Wake is never a language choice.
        let (stt, tts, voice) = selection(&["en"], "wake", "alba");
        assert_eq!(
            catalog.validate_selection(&stt, &tts, &voice),
            Err(CODE_INVALID)
        );
    }

    #[test]
    fn unsupported_state_is_refused_with_its_own_code() {
        let catalog = parse(r#",{"kind":"stt","language":"de","label":"Alemão","state":"unsupported","engine":null,"size_bytes":null,"size_partial":false,"size_note":null,"license":null,"sha256":null,"quality":"não medido","evidence":null,"voices":[],"reason":"fora do escopo","source":"s"}"#).unwrap();
        let (stt, tts, voice) = selection(&["de"], "en", "alba");
        assert_eq!(
            catalog.validate_selection(&stt, &tts, &voice),
            Err(CODE_UNSUPPORTED)
        );
    }

    #[test]
    fn view_reports_selection_restart_and_honest_reasons() {
        let catalog = LanguageCatalog::builtin().unwrap();
        let config = Config::default();
        let applied = Selection::from_config(&config);
        let shown = view(&catalog, &config, Some(&applied));
        assert!(!shown.restart_required.stt && !shown.restart_required.tts);
        assert_eq!(shown.stt_selected, vec!["en".to_string()]);
        assert!(!shown.install.available);
        assert_eq!(shown.install.reason, INSTALL_REASON);
        let stt_fr = shown.engines.stt.iter().find(|i| i.id == "fr").unwrap();
        assert!(!stt_fr.selectable && !stt_fr.selected);
        assert_eq!(
            stt_fr.reason.as_deref(),
            Some("Não instalado: Aguardando aprovação do download pelo dono")
        );
        assert!(shown.engines.wake.iter().all(|i| !i.selected));

        // A stored change that the running workers did not start with asks for a restart.
        let mut changed = config.clone();
        changed.stt_languages = vec!["en".into(), "fr".into()];
        let pending = view(&catalog, &changed, Some(&applied));
        assert!(pending.restart_required.stt && !pending.restart_required.tts);
        assert!(!view(&catalog, &changed, None).restart_required.stt);
    }
}
