//! WP-10a Souls: a communication profile (style, priorities) with visible provenance.
//!
//! A Soul never authenticates anyone and never changes the assistant's identity or safety rules. Its
//! `mode` is explicit: `influence` (suggests a style) or `simulation` (labelled as an imitation of the
//! user's own style). Provenance is fixed at creation: `declared` (typed by the user), `inferred_from_chat`
//! (confidence capped at 0.8) or `user_documents` (requires `consent_documents: true`). Only the active
//! Soul is handed to the LLM plugin, as a hint (`active_hint`); with no LLM plugin it changes no answer.

use crate::personal;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

pub const FILE: &str = "souls.json";
const LIMIT: u64 = 64 * 1024;
const SOULS_MAX: usize = 12;
const NAME_MAX: usize = 40;
const TEXT_MAX: usize = 280;
const PRIORITIES_MAX: usize = 5;
const PRIORITY_MAX: usize = 40;
const EVIDENCE_MAX: usize = 5;
const EVIDENCE_TEXT_MAX: usize = 120;
const INFERRED_CONFIDENCE_CAP: f32 = 0.8;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    Influence,
    Simulation,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProvenanceKind {
    Declared,
    InferredFromChat,
    UserDocuments,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Provenance {
    pub kind: ProvenanceKind,
    pub evidence: Vec<String>,
    pub confidence: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Soul {
    pub id: String,
    pub name: String,
    pub description: String,
    pub style: String,
    pub priorities: Vec<String>,
    pub mode: Mode,
    pub provenance: Provenance,
    pub created_ms: u64,
    pub updated_ms: u64,
    /// Bumped on every edit of this Soul.
    pub version: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Ledger {
    version: u16,
    revision: u64,
    next_seq: u64,
    active: Option<String>,
    souls: Vec<Soul>,
}

impl Default for Ledger {
    fn default() -> Self {
        Self {
            version: 1,
            revision: 0,
            next_seq: 0,
            active: None,
            souls: Vec::new(),
        }
    }
}

impl Ledger {
    fn validate(&self) -> Result<(), &'static str> {
        let mut ids = std::collections::HashSet::new();
        let ok = self.version == 1
            && self.souls.len() <= SOULS_MAX
            && self.souls.iter().all(|s| {
                ids.insert(s.id.as_str())
                    && s.name.chars().count() <= NAME_MAX
                    && s.description.chars().count() <= TEXT_MAX
                    && s.style.chars().count() <= TEXT_MAX
                    && s.priorities.len() <= PRIORITIES_MAX
                    && s.provenance.evidence.len() <= EVIDENCE_MAX
                    && (0.0..=1.0).contains(&s.provenance.confidence)
            })
            && self
                .active
                .as_ref()
                .is_none_or(|a| self.souls.iter().any(|s| &s.id == a));
        if ok {
            Ok(())
        } else {
            Err("ledger_invalid")
        }
    }
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum Op {
    Create {
        revision: u64,
        name: String,
        description: String,
        style: String,
        priorities: Vec<String>,
        mode: Mode,
        provenance: ProvenanceInput,
        #[serde(default)]
        consent_documents: bool,
    },
    /// Provenance is not editable: a different origin is a new Soul.
    Update {
        revision: u64,
        id: String,
        #[serde(default)]
        name: Option<String>,
        #[serde(default)]
        description: Option<String>,
        #[serde(default)]
        style: Option<String>,
        #[serde(default)]
        priorities: Option<Vec<String>>,
        #[serde(default)]
        mode: Option<Mode>,
    },
    Activate {
        revision: u64,
        id: String,
    },
    Deactivate {
        revision: u64,
    },
    Delete {
        revision: u64,
        id: String,
    },
    ForgetAll {
        revision: u64,
        confirm: bool,
    },
    /// Read-only: the text the Soul would send as a hint, labelled as a preview.
    Preview {
        id: String,
    },
    Export {},
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProvenanceInput {
    pub kind: ProvenanceKind,
    #[serde(default)]
    pub evidence: Vec<String>,
    pub confidence: f32,
}

pub fn parse(value: Value) -> Result<Op, &'static str> {
    personal::parse(value)
}

pub struct Souls {
    path: PathBuf,
    ledger: Ledger,
}

impl Souls {
    pub fn open(dir: &Path) -> Result<Self, &'static str> {
        let path = dir.join(FILE);
        let ledger: Ledger = personal::load_ledger(&path, LIMIT)?;
        ledger.validate()?;
        Ok(Self { path, ledger })
    }

    pub fn apply(&mut self, op: Op, now_ms: u64) -> Result<Value, &'static str> {
        let mut next = self.ledger.clone();
        let (reply, mutated) = run(&mut next, op, now_ms)?;
        if mutated {
            personal::save_ledger(&self.path, &next, LIMIT)?;
            self.ledger = next;
        }
        Ok(reply)
    }

    pub fn snapshot(&self) -> Value {
        let souls: Vec<Value> = self
            .ledger
            .souls
            .iter()
            .map(|s| view(s, self.ledger.active.as_deref()))
            .collect();
        json!({
            "revision": self.ledger.revision,
            "active": self.ledger.active,
            "capacity": SOULS_MAX,
            "souls": souls,
        })
    }

    /// The hint the LLM plugin may read: style and priorities of the active Soul. `None` when no Soul is active.
    pub fn active_hint(&self) -> Option<String> {
        let id = self.ledger.active.as_ref()?;
        let soul = self.ledger.souls.iter().find(|s| &s.id == id)?;
        let mode = match soul.mode {
            Mode::Influence => "influência",
            Mode::Simulation => "simulação do estilo do usuário",
        };
        Some(format!(
            "Estilo ({mode}): {}. Prioridades: {}. Não substitui autenticação, segurança nem as regras do assistente.",
            soul.style,
            soul.priorities.join(", ")
        ))
    }

    pub fn export(&self) -> Value {
        json!({ "revision": self.ledger.revision, "active": self.ledger.active, "souls": self.ledger.souls })
    }
}

fn view(soul: &Soul, active: Option<&str>) -> Value {
    json!({
        "id": soul.id,
        "name": soul.name,
        "description": soul.description,
        "style": soul.style,
        "priorities": soul.priorities,
        "mode": soul.mode,
        "mode_label": match soul.mode {
            Mode::Influence => "Influência: sugere estilo",
            Mode::Simulation => "Simulação: imita o estilo do usuário",
        },
        "provenance": soul.provenance,
        "version": soul.version,
        "active": active == Some(soul.id.as_str()),
    })
}

fn run(ledger: &mut Ledger, op: Op, now_ms: u64) -> Result<(Value, bool), &'static str> {
    match op {
        Op::Create {
            revision,
            name,
            description,
            style,
            priorities,
            mode,
            provenance,
            consent_documents,
        } => {
            cas(ledger, revision)?;
            if ledger.souls.len() >= SOULS_MAX {
                return Err("soul_capacity");
            }
            let provenance = checked_provenance(provenance, consent_documents)?;
            let soul = Soul {
                id: personal::next_id("soul", &mut ledger.next_seq),
                name: personal::line(&name, NAME_MAX)?,
                description: personal::line(&description, TEXT_MAX)?,
                style: personal::line(&style, TEXT_MAX)?,
                priorities: priorities_ok(priorities)?,
                mode,
                provenance,
                created_ms: now_ms,
                updated_ms: now_ms,
                version: 1,
            };
            let id = soul.id.clone();
            ledger.souls.push(soul);
            ledger.revision += 1;
            Ok((json!({ "id": id, "revision": ledger.revision }), true))
        }
        Op::Update {
            revision,
            id,
            name,
            description,
            style,
            priorities,
            mode,
        } => {
            cas(ledger, revision)?;
            let soul = ledger
                .souls
                .iter_mut()
                .find(|s| s.id == id)
                .ok_or("unknown_soul")?;
            if let Some(name) = name {
                soul.name = personal::line(&name, NAME_MAX)?;
            }
            if let Some(description) = description {
                soul.description = personal::line(&description, TEXT_MAX)?;
            }
            if let Some(style) = style {
                soul.style = personal::line(&style, TEXT_MAX)?;
            }
            if let Some(priorities) = priorities {
                soul.priorities = priorities_ok(priorities)?;
            }
            if let Some(mode) = mode {
                soul.mode = mode;
            }
            soul.version += 1;
            soul.updated_ms = now_ms;
            ledger.revision += 1;
            Ok((
                json!({ "revision": ledger.revision, "version": soul.version }),
                true,
            ))
        }
        Op::Activate { revision, id } => {
            cas(ledger, revision)?;
            if !ledger.souls.iter().any(|s| s.id == id) {
                return Err("unknown_soul");
            }
            ledger.active = Some(id);
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::Deactivate { revision } => {
            cas(ledger, revision)?;
            ledger.active = None;
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::Delete { revision, id } => {
            cas(ledger, revision)?;
            let before = ledger.souls.len();
            ledger.souls.retain(|s| s.id != id);
            if ledger.souls.len() == before {
                return Err("unknown_soul");
            }
            if ledger.active.as_deref() == Some(id.as_str()) {
                ledger.active = None;
            }
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::ForgetAll { revision, confirm } => {
            cas(ledger, revision)?;
            if !confirm {
                return Err("confirmation_required");
            }
            ledger.souls.clear();
            ledger.active = None;
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::Preview { id } => {
            let soul = ledger
                .souls
                .iter()
                .find(|s| s.id == id)
                .ok_or("unknown_soul")?;
            let reply = json!({
                "label": "Prévia de estilo",
                "mode_label": view(soul, None)["mode_label"].clone(),
                "guidance": format!("Estilo: {}. Prioridades: {}.", soul.style, soul.priorities.join(", ")),
                "note": "Prévia: nenhuma resposta é gerada e a identidade do assistente não muda.",
            });
            Ok((reply, false))
        }
        Op::Export {} => Ok((
            json!({ "revision": ledger.revision, "active": ledger.active, "souls": ledger.souls }),
            false,
        )),
    }
}

fn checked_provenance(
    input: ProvenanceInput,
    consent_documents: bool,
) -> Result<Provenance, &'static str> {
    if !(0.0..=1.0).contains(&input.confidence) {
        return Err("invalid_confidence");
    }
    if input.evidence.len() > EVIDENCE_MAX {
        return Err("invalid_evidence");
    }
    let evidence = input
        .evidence
        .iter()
        .map(|e| personal::line(e, EVIDENCE_TEXT_MAX))
        .collect::<Result<Vec<_>, _>>()?;
    let confidence = match input.kind {
        ProvenanceKind::Declared => {
            if input.confidence != 1.0 {
                return Err("invalid_confidence");
            }
            1.0
        }
        ProvenanceKind::InferredFromChat => {
            if evidence.is_empty() || input.confidence > INFERRED_CONFIDENCE_CAP {
                return Err("invalid_provenance");
            }
            input.confidence
        }
        ProvenanceKind::UserDocuments => {
            if !consent_documents || evidence.is_empty() {
                return Err("consent_required");
            }
            input.confidence.min(INFERRED_CONFIDENCE_CAP)
        }
    };
    Ok(Provenance {
        kind: input.kind,
        evidence,
        confidence,
    })
}

fn priorities_ok(priorities: Vec<String>) -> Result<Vec<String>, &'static str> {
    if priorities.len() > PRIORITIES_MAX {
        return Err("invalid_text");
    }
    priorities
        .iter()
        .map(|p| personal::line(p, PRIORITY_MAX))
        .collect()
}

fn cas(ledger: &Ledger, revision: u64) -> Result<(), &'static str> {
    if revision == ledger.revision {
        Ok(())
    } else {
        Err("stale_revision")
    }
}
