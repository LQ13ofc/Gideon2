//! WP-10a Memory: facts the user chose to keep, with source, per-source consent, TTL and deletion.
//!
//! Rules: nothing is stored from a source the user has not granted (`consent`, off by default); revoking a
//! source deletes its facts; conversation-sourced facts follow the Core `history_retention` (never = refused,
//! window = dropped when older than the window); deletion is immediate and `forget_all` needs `confirm: true`.

use crate::personal;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

pub const FILE: &str = "memory.json";
const LIMIT: u64 = 256 * 1024;
pub const FACTS_MAX: usize = 300;
const TEXT_MAX: usize = 400;
const REF_MAX: usize = 64;
const TTL_MAX_DAYS: u64 = 365;
const SNAPSHOT_MAX: usize = 50;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Kind {
    Fact,
    Decision,
    Preference,
    Context,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Source {
    /// Typed or confirmed by the user in the app.
    UserTyped,
    /// Taken from a conversation turn; follows `history_retention`.
    Conversation,
    /// Imported from a file the user chose.
    Import,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Consent {
    pub user_typed: bool,
    pub conversation: bool,
    pub import: bool,
}

impl Consent {
    fn get(&self, source: Source) -> bool {
        match source {
            Source::UserTyped => self.user_typed,
            Source::Conversation => self.conversation,
            Source::Import => self.import,
        }
    }
    fn set(&mut self, source: Source, granted: bool) {
        match source {
            Source::UserTyped => self.user_typed = granted,
            Source::Conversation => self.conversation = granted,
            Source::Import => self.import = granted,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Fact {
    pub id: String,
    pub text: String,
    pub kind: Kind,
    pub source: Source,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_ref: Option<String>,
    pub created_ms: u64,
    pub updated_ms: u64,
    /// TTL: the fact is dropped at this time. `None` keeps it until the user deletes it.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expires_ms: Option<u64>,
}

/// `memory.json`: private, 0600, CAS on `revision`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Ledger {
    version: u16,
    revision: u64,
    next_seq: u64,
    consent: Consent,
    facts: Vec<Fact>,
}

impl Default for Ledger {
    fn default() -> Self {
        Self {
            version: 1,
            revision: 0,
            next_seq: 0,
            consent: Consent::default(),
            facts: Vec::new(),
        }
    }
}

impl Ledger {
    fn validate(&self) -> Result<(), &'static str> {
        let mut ids = std::collections::HashSet::new();
        let ok = self.version == 1
            && self.facts.len() <= FACTS_MAX
            && self.facts.iter().all(|f| {
                ids.insert(f.id.as_str())
                    && f.text.chars().count() <= TEXT_MAX
                    && !f.text.chars().any(char::is_control)
                    && f.source_ref.as_ref().is_none_or(|r| r.len() <= REF_MAX)
            });
        if ok {
            Ok(())
        } else {
            Err("ledger_invalid")
        }
    }

    /// Drops facts whose TTL passed, facts from a source without consent, and conversation facts outside the
    /// history window (all of them under `never`). Returns true when anything was removed.
    fn purge(&mut self, now_ms: u64, retention: Option<u64>) -> bool {
        let before = self.facts.len();
        let start = personal::window_start(now_ms, retention);
        let consent = self.consent;
        self.facts.retain(|f| {
            let ttl_ok = f.expires_ms.is_none_or(|t| t > now_ms);
            let consent_ok = consent.get(f.source);
            let history_ok = match (f.source, start) {
                (Source::Conversation, None) => false,
                (Source::Conversation, Some(start)) => f.created_ms >= start,
                _ => true,
            };
            ttl_ok && consent_ok && history_ok
        });
        self.facts.len() != before
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum Op {
    Add {
        revision: u64,
        text: String,
        kind: Kind,
        source: Source,
        #[serde(default)]
        source_ref: Option<String>,
        #[serde(default)]
        ttl_days: Option<u64>,
    },
    Edit {
        revision: u64,
        id: String,
        text: String,
    },
    Forget {
        revision: u64,
        id: String,
    },
    /// Grants or revokes one source. Revoking deletes that source's facts.
    Consent {
        revision: u64,
        source: Source,
        granted: bool,
    },
    ForgetSource {
        revision: u64,
        source: Source,
    },
    ForgetAll {
        revision: u64,
        confirm: bool,
    },
    Search {
        query: String,
    },
    Export {},
}

pub fn parse(value: Value) -> Result<Op, &'static str> {
    personal::parse(value)
}

pub struct Memory {
    path: PathBuf,
    ledger: Ledger,
}

impl Memory {
    pub fn open(dir: &Path) -> Result<Self, &'static str> {
        let path = dir.join(FILE);
        let ledger: Ledger = personal::load_ledger(&path, LIMIT)?;
        ledger.validate()?;
        Ok(Self { path, ledger })
    }

    pub fn revision(&self) -> u64 {
        self.ledger.revision
    }

    /// Applies one operation. Mutations run on a copy and are saved before they become visible.
    pub fn apply(
        &mut self,
        op: Op,
        now_ms: u64,
        retention: Option<u64>,
    ) -> Result<Value, &'static str> {
        let mut next = self.ledger.clone();
        let purged = next.purge(now_ms, retention);
        match run(&mut next, op, now_ms, retention) {
            Ok((reply, mutated)) => {
                if purged || mutated {
                    personal::save_ledger(&self.path, &next, LIMIT)?;
                }
                self.ledger = next;
                Ok(reply)
            }
            Err(code) => {
                // A refused request still applies the retention purge: expired data is not kept on disk.
                if purged {
                    let mut kept = self.ledger.clone();
                    kept.purge(now_ms, retention);
                    personal::save_ledger(&self.path, &kept, LIMIT)?;
                    self.ledger = kept;
                }
                Err(code)
            }
        }
    }

    /// Persists the retention purge without an operation (Core timer and `history_retention` changes).
    pub fn purge_now(&mut self, now_ms: u64, retention: Option<u64>) -> Result<(), &'static str> {
        let mut next = self.ledger.clone();
        if next.purge(now_ms, retention) {
            personal::save_ledger(&self.path, &next, LIMIT)?;
            self.ledger = next;
        }
        Ok(())
    }

    pub fn snapshot(&self, now_ms: u64, retention: Option<u64>) -> Value {
        let mut view = self.ledger.clone();
        view.purge(now_ms, retention);
        let facts: Vec<Value> = view
            .facts
            .iter()
            .rev()
            .take(SNAPSHOT_MAX)
            .map(|f| {
                json!({
                    "id": f.id,
                    "text": f.text,
                    "kind": f.kind,
                    "source": f.source,
                    "created_ms": f.created_ms,
                    "expires_ms": f.expires_ms,
                })
            })
            .collect();
        json!({
            "revision": view.revision,
            "count": view.facts.len(),
            "capacity": FACTS_MAX,
            "consent": view.consent,
            "facts": facts,
        })
    }

    pub fn export(&self) -> Value {
        json!({ "revision": self.ledger.revision, "consent": self.ledger.consent, "facts": self.ledger.facts })
    }
}

/// Applies a mutation or read to `ledger`. Returns the reply and whether the ledger changed.
fn run(
    ledger: &mut Ledger,
    op: Op,
    now_ms: u64,
    retention: Option<u64>,
) -> Result<(Value, bool), &'static str> {
    match op {
        Op::Add {
            revision,
            text,
            kind,
            source,
            source_ref,
            ttl_days,
        } => {
            cas(ledger, revision)?;
            if !ledger.consent.get(source) {
                return Err("consent_required");
            }
            if source == Source::Conversation && retention.is_none() {
                return Err("retention_never");
            }
            let text = personal::line(&text, TEXT_MAX)?;
            let source_ref = match source_ref {
                Some(r) => Some(personal::line(&r, REF_MAX)?),
                None => None,
            };
            let expires_ms = match ttl_days {
                None => None,
                Some(days) if (1..=TTL_MAX_DAYS).contains(&days) => {
                    Some(now_ms + days * personal::DAY_MS)
                }
                Some(_) => return Err("invalid_ttl"),
            };
            if ledger.facts.len() >= FACTS_MAX {
                return Err("memory_full");
            }
            let id = personal::next_id("fact", &mut ledger.next_seq);
            ledger.facts.push(Fact {
                id: id.clone(),
                text,
                kind,
                source,
                source_ref,
                created_ms: now_ms,
                updated_ms: now_ms,
                expires_ms,
            });
            ledger.revision += 1;
            Ok((json!({ "id": id, "revision": ledger.revision }), true))
        }
        Op::Edit { revision, id, text } => {
            cas(ledger, revision)?;
            let text = personal::line(&text, TEXT_MAX)?;
            let fact = ledger
                .facts
                .iter_mut()
                .find(|f| f.id == id)
                .ok_or("unknown_fact")?;
            fact.text = text;
            fact.updated_ms = now_ms;
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::Forget { revision, id } => {
            cas(ledger, revision)?;
            let before = ledger.facts.len();
            ledger.facts.retain(|f| f.id != id);
            if ledger.facts.len() == before {
                return Err("unknown_fact");
            }
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::Consent {
            revision,
            source,
            granted,
        } => {
            cas(ledger, revision)?;
            ledger.consent.set(source, granted);
            if !granted {
                ledger.facts.retain(|f| f.source != source);
            }
            ledger.revision += 1;
            Ok((
                json!({ "revision": ledger.revision, "consent": ledger.consent }),
                true,
            ))
        }
        Op::ForgetSource { revision, source } => {
            cas(ledger, revision)?;
            ledger.facts.retain(|f| f.source != source);
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::ForgetAll { revision, confirm } => {
            cas(ledger, revision)?;
            if !confirm {
                return Err("confirmation_required");
            }
            ledger.facts.clear();
            ledger.consent = Consent::default();
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::Search { query } => {
            let needle = query.trim().to_lowercase();
            if needle.chars().count() > TEXT_MAX {
                return Err("invalid_text");
            }
            let hits: Vec<Value> = ledger
                .facts
                .iter()
                .filter(|f| needle.is_empty() || f.text.to_lowercase().contains(&needle))
                .take(SNAPSHOT_MAX)
                .map(|f| json!({ "id": f.id, "text": f.text, "source": f.source, "kind": f.kind }))
                .collect();
            Ok((json!({ "hits": hits }), false))
        }
        Op::Export {} => Ok((
            json!({ "revision": ledger.revision, "consent": ledger.consent, "facts": ledger.facts }),
            false,
        )),
    }
}

fn cas(ledger: &Ledger, revision: u64) -> Result<(), &'static str> {
    if revision == ledger.revision {
        Ok(())
    } else {
        Err("stale_revision")
    }
}
