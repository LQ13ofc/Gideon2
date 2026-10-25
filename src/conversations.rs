//! WP-10a Conversations: text history of dialogue sessions (user and assistant turns, no audio).
//!
//! Retention: the Core `history_retention` governs everything here. Under `never` nothing is appended and existing
//! sessions are erased; under a window, sessions whose last turn is older than the window are dropped. The user can
//! delete one session, rename it, erase all of them (`confirm: true`), and export them.

use crate::personal;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

pub const FILE: &str = "conversations.json";
const LIMIT: u64 = 1024 * 1024;
const SESSIONS_MAX: usize = 100;
const TURNS_MAX: usize = 200;
const TURN_TEXT_MAX: usize = 2000;
const TITLE_MAX: usize = 80;
const SNAPSHOT_SESSIONS: usize = 50;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Role {
    User,
    Assistant,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Turn {
    pub role: Role,
    pub text: String,
    pub at_ms: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Session {
    pub id: String,
    pub title: String,
    pub created_ms: u64,
    pub updated_ms: u64,
    pub turns: Vec<Turn>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Ledger {
    version: u16,
    revision: u64,
    next_seq: u64,
    sessions: Vec<Session>,
}

impl Default for Ledger {
    fn default() -> Self {
        Self {
            version: 1,
            revision: 0,
            next_seq: 0,
            sessions: Vec::new(),
        }
    }
}

impl Ledger {
    fn validate(&self) -> Result<(), &'static str> {
        let mut ids = std::collections::HashSet::new();
        let ok = self.version == 1
            && self.sessions.len() <= SESSIONS_MAX
            && self.sessions.iter().all(|s| {
                ids.insert(s.id.as_str())
                    && s.turns.len() <= TURNS_MAX
                    && s.title.chars().count() <= TITLE_MAX
            });
        if ok {
            Ok(())
        } else {
            Err("ledger_invalid")
        }
    }

    /// Drops sessions older than the window (all of them under `never`). Returns true when anything was removed.
    fn purge(&mut self, now_ms: u64, retention: Option<u64>) -> bool {
        let before = self.sessions.len();
        match personal::window_start(now_ms, retention) {
            None => self.sessions.clear(),
            Some(start) => self.sessions.retain(|s| s.updated_ms >= start),
        }
        self.sessions.len() != before
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum Op {
    /// Adds a turn. Without `session_id` a new session starts; its title is the first user line.
    Append {
        revision: u64,
        #[serde(default)]
        session_id: Option<String>,
        role: Role,
        text: String,
    },
    Rename {
        revision: u64,
        session_id: String,
        title: String,
    },
    Delete {
        revision: u64,
        session_id: String,
    },
    ForgetAll {
        revision: u64,
        confirm: bool,
    },
    List {},
    Get {
        session_id: String,
    },
    Export {},
}

pub fn parse(value: Value) -> Result<Op, &'static str> {
    personal::parse(value)
}

pub struct Conversations {
    path: PathBuf,
    ledger: Ledger,
}

impl Conversations {
    pub fn open(dir: &Path) -> Result<Self, &'static str> {
        let path = dir.join(FILE);
        let ledger: Ledger = personal::load_ledger(&path, LIMIT)?;
        ledger.validate()?;
        Ok(Self { path, ledger })
    }

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
                // A refused request still applies the retention purge (under `never`, existing history is erased).
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
        let sessions: Vec<Value> = view
            .sessions
            .iter()
            .rev()
            .take(SNAPSHOT_SESSIONS)
            .map(summary)
            .collect();
        json!({
            "revision": view.revision,
            "recording": retention.is_some(),
            "count": view.sessions.len(),
            "capacity": SESSIONS_MAX,
            "sessions": sessions,
        })
    }

    pub fn export(&self, now_ms: u64, retention: Option<u64>) -> Value {
        let mut view = self.ledger.clone();
        view.purge(now_ms, retention);
        json!({ "revision": view.revision, "sessions": view.sessions })
    }
}

fn summary(session: &Session) -> Value {
    json!({
        "id": session.id,
        "title": session.title,
        "turns": session.turns.len(),
        "created_ms": session.created_ms,
        "updated_ms": session.updated_ms,
    })
}

fn run(
    ledger: &mut Ledger,
    op: Op,
    now_ms: u64,
    retention: Option<u64>,
) -> Result<(Value, bool), &'static str> {
    match op {
        Op::Append {
            revision,
            session_id,
            role,
            text,
        } => {
            cas(ledger, revision)?;
            if retention.is_none() {
                return Err("retention_never");
            }
            let text = personal::multiline(&text, TURN_TEXT_MAX)?;
            let index = match session_id {
                Some(id) => ledger
                    .sessions
                    .iter()
                    .position(|s| s.id == id)
                    .ok_or("unknown_session")?,
                None => {
                    if ledger.sessions.len() >= SESSIONS_MAX {
                        return Err("conversation_capacity");
                    }
                    let id = personal::next_id("conv", &mut ledger.next_seq);
                    let title = title_from(&text);
                    ledger.sessions.push(Session {
                        id,
                        title,
                        created_ms: now_ms,
                        updated_ms: now_ms,
                        turns: Vec::new(),
                    });
                    ledger.sessions.len() - 1
                }
            };
            let session = &mut ledger.sessions[index];
            session.turns.push(Turn {
                role,
                text,
                at_ms: now_ms,
            });
            if session.turns.len() > TURNS_MAX {
                session.turns.remove(0);
            }
            session.updated_ms = now_ms;
            let session_id = session.id.clone();
            let turns = session.turns.len();
            ledger.revision += 1;
            Ok((
                json!({ "session_id": session_id, "turns": turns, "revision": ledger.revision }),
                true,
            ))
        }
        Op::Rename {
            revision,
            session_id,
            title,
        } => {
            cas(ledger, revision)?;
            let title = personal::line(&title, TITLE_MAX)?;
            let session = ledger
                .sessions
                .iter_mut()
                .find(|s| s.id == session_id)
                .ok_or("unknown_session")?;
            session.title = title;
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::Delete {
            revision,
            session_id,
        } => {
            cas(ledger, revision)?;
            let before = ledger.sessions.len();
            ledger.sessions.retain(|s| s.id != session_id);
            if ledger.sessions.len() == before {
                return Err("unknown_session");
            }
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::ForgetAll { revision, confirm } => {
            cas(ledger, revision)?;
            if !confirm {
                return Err("confirmation_required");
            }
            ledger.sessions.clear();
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::List {} => {
            let sessions: Vec<Value> = ledger.sessions.iter().rev().map(summary).collect();
            Ok((json!({ "sessions": sessions }), false))
        }
        Op::Get { session_id } => {
            let session = ledger
                .sessions
                .iter()
                .find(|s| s.id == session_id)
                .ok_or("unknown_session")?;
            Ok((json!({ "session": session }), false))
        }
        Op::Export {} => Ok((
            json!({ "revision": ledger.revision, "sessions": ledger.sessions }),
            false,
        )),
    }
}

/// Title from the first user line: first 60 characters, on one line.
fn title_from(text: &str) -> String {
    let line: String = text.lines().next().unwrap_or("").chars().take(60).collect();
    if line.trim().is_empty() {
        "Conversa".to_owned()
    } else {
        line.trim().to_owned()
    }
}

fn cas(ledger: &Ledger, revision: u64) -> Result<(), &'static str> {
    if revision == ledger.revision {
        Ok(())
    } else {
        Err("stale_revision")
    }
}
