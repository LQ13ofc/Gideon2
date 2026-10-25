//! WP-10a Habits: a private, named procedure that runs one enabled Skill with fixed inputs.
//!
//! A Habit never grants permissions: it pins the Skill version the user approved (set when created or edited),
//! refuses to run when that version is no longer the enabled one, and runs through the engine's own checks
//! (`SkillEngine::run_skill`). Edits keep the previous version so `rollback` can restore it. Run outcomes are
//! history: they follow the Core `history_retention` (`never` records none). Trigger phrases are stored and shown;
//! matching them against voice commands is not wired in this package (see docs/WP10a.md).

use crate::personal::{self, SkillEngine};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

pub const FILE: &str = "habits.json";
const LIMIT: u64 = 128 * 1024;
const HABITS_MAX: usize = 24;
const NAME_MAX: usize = 60;
const PHRASES_MAX: usize = 4;
const PHRASE_MAX: usize = 80;
const SKILL_ID_MAX: usize = 64;
const INPUTS_MAX_BYTES: usize = 2048;
const OUTCOMES_MAX: usize = 5;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Active,
    Paused,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Pinned {
    pub version: u32,
    pub skill_id: String,
    pub skill_version: String,
    pub inputs: Value,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Outcome {
    pub at_ms: u64,
    pub code: String,
    pub started: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Habit {
    pub id: String,
    pub name: String,
    pub phrases: Vec<String>,
    pub status: Status,
    pub current: Pinned,
    /// The version before the last edit or rollback, restored by `rollback`.
    pub previous: Option<Pinned>,
    pub outcomes: Vec<Outcome>,
    pub created_ms: u64,
    pub updated_ms: u64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Ledger {
    version: u16,
    revision: u64,
    next_seq: u64,
    habits: Vec<Habit>,
}

impl Default for Ledger {
    fn default() -> Self {
        Self {
            version: 1,
            revision: 0,
            next_seq: 0,
            habits: Vec::new(),
        }
    }
}

impl Ledger {
    fn validate(&self) -> Result<(), &'static str> {
        let mut ids = std::collections::HashSet::new();
        let ok = self.version == 1
            && self.habits.len() <= HABITS_MAX
            && self.habits.iter().all(|h| {
                ids.insert(h.id.as_str())
                    && h.phrases.len() <= PHRASES_MAX
                    && h.outcomes.len() <= OUTCOMES_MAX
                    && h.current.skill_id.len() <= SKILL_ID_MAX
            });
        if ok {
            Ok(())
        } else {
            Err("ledger_invalid")
        }
    }

    fn purge(&mut self, now_ms: u64, retention: Option<u64>) -> bool {
        let start = personal::window_start(now_ms, retention);
        let mut changed = false;
        for habit in &mut self.habits {
            let before = habit.outcomes.len();
            match start {
                None => habit.outcomes.clear(),
                Some(start) => habit.outcomes.retain(|o| o.at_ms >= start),
            }
            changed |= habit.outcomes.len() != before;
        }
        changed
    }
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum Op {
    Create {
        revision: u64,
        name: String,
        #[serde(default)]
        phrases: Vec<String>,
        skill_id: String,
        inputs: Value,
    },
    /// Editing re-pins the Skill version to the one enabled now; the previous pin is kept for rollback.
    Edit {
        revision: u64,
        id: String,
        #[serde(default)]
        name: Option<String>,
        #[serde(default)]
        phrases: Option<Vec<String>>,
        #[serde(default)]
        inputs: Option<Value>,
    },
    SetStatus {
        revision: u64,
        id: String,
        status: Status,
    },
    Rollback {
        revision: u64,
        id: String,
    },
    Delete {
        revision: u64,
        id: String,
    },
    ForgetAll {
        revision: u64,
        confirm: bool,
    },
    /// Runs the Habit once through the Skill engine. Not a CAS operation: it changes outcomes only.
    Run {
        id: String,
    },
    Export {},
}

pub fn parse(value: Value) -> Result<Op, &'static str> {
    personal::parse(value)
}

/// Trigger phrase normal form: trimmed, lowercase, single spaces, no final punctuation.
pub fn normalize_phrase(text: &str) -> String {
    text.trim()
        .trim_end_matches(|c: char| c.is_ascii_punctuation())
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

pub struct Habits {
    path: PathBuf,
    ledger: Ledger,
}

impl Habits {
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
        engine: &mut dyn SkillEngine,
    ) -> Result<Value, &'static str> {
        let mut next = self.ledger.clone();
        let purged = next.purge(now_ms, retention);
        match run(&mut next, op, now_ms, retention, engine) {
            Ok((reply, mutated)) => {
                if purged || mutated {
                    personal::save_ledger(&self.path, &next, LIMIT)?;
                }
                self.ledger = next;
                Ok(reply)
            }
            Err(code) => {
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

    /// The active habit whose trigger phrase is `phrase` (both normalized as in `normalize_phrase`). Used by the
    /// voice path: a transcript equal to a trigger runs the habit, and the Core answers through `run`.
    pub fn id_for_phrase(&self, phrase: &str) -> Option<String> {
        let wanted = normalize_phrase(phrase);
        if wanted.is_empty() {
            return None;
        }
        self.ledger
            .habits
            .iter()
            .find(|h| {
                h.status == Status::Active
                    && h.phrases.iter().any(|p| normalize_phrase(p) == wanted)
            })
            .map(|h| h.id.clone())
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
        json!({
            "revision": view.revision,
            "count": view.habits.len(),
            "capacity": HABITS_MAX,
            "habits": view.habits,
        })
    }

    pub fn export(&self) -> Value {
        json!({ "revision": self.ledger.revision, "habits": self.ledger.habits })
    }
}

fn find<'a>(ledger: &'a mut Ledger, id: &str) -> Result<&'a mut Habit, &'static str> {
    ledger
        .habits
        .iter_mut()
        .find(|h| h.id == id)
        .ok_or("unknown_habit")
}

fn phrases_ok(phrases: Vec<String>) -> Result<Vec<String>, &'static str> {
    if phrases.len() > PHRASES_MAX {
        return Err("invalid_text");
    }
    phrases
        .iter()
        .map(|p| personal::line(p, PHRASE_MAX))
        .collect()
}

fn skill_ok(skill_id: &str) -> Result<(), &'static str> {
    let ok = !skill_id.is_empty()
        && skill_id.len() <= SKILL_ID_MAX
        && skill_id.chars().all(|c| {
            c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_' || c == '-' || c == '.'
        });
    if ok {
        Ok(())
    } else {
        Err("invalid_skill_id")
    }
}

/// Pins `skill_id` to the version enabled now, or refuses.
fn pin(
    engine: &dyn SkillEngine,
    skill_id: &str,
    inputs: Value,
    version: u32,
) -> Result<Pinned, &'static str> {
    skill_ok(skill_id)?;
    let skill_version = engine
        .enabled_version(skill_id)
        .ok_or("skill_not_enabled")?;
    Ok(Pinned {
        version,
        skill_id: skill_id.to_owned(),
        skill_version,
        inputs: personal::bounded_object(&inputs, INPUTS_MAX_BYTES)?,
    })
}

fn run(
    ledger: &mut Ledger,
    op: Op,
    now_ms: u64,
    retention: Option<u64>,
    engine: &mut dyn SkillEngine,
) -> Result<(Value, bool), &'static str> {
    match op {
        Op::Create {
            revision,
            name,
            phrases,
            skill_id,
            inputs,
        } => {
            cas(ledger, revision)?;
            if ledger.habits.len() >= HABITS_MAX {
                return Err("habit_capacity");
            }
            let current = pin(engine, &skill_id, inputs, 1)?;
            let habit = Habit {
                id: personal::next_id("habit", &mut ledger.next_seq),
                name: personal::line(&name, NAME_MAX)?,
                phrases: phrases_ok(phrases)?,
                status: Status::Active,
                current,
                previous: None,
                outcomes: Vec::new(),
                created_ms: now_ms,
                updated_ms: now_ms,
            };
            let id = habit.id.clone();
            ledger.habits.push(habit);
            ledger.revision += 1;
            Ok((json!({ "id": id, "revision": ledger.revision }), true))
        }
        Op::Edit {
            revision,
            id,
            name,
            phrases,
            inputs,
        } => {
            cas(ledger, revision)?;
            let habit = find(ledger, &id)?;
            let name = match name {
                Some(n) => Some(personal::line(&n, NAME_MAX)?),
                None => None,
            };
            let phrases = match phrases {
                Some(p) => Some(phrases_ok(p)?),
                None => None,
            };
            let inputs = inputs.unwrap_or_else(|| habit.current.inputs.clone());
            let next_version = habit.current.version + 1;
            let pinned = pin(
                engine,
                &habit.current.skill_id.clone(),
                inputs,
                next_version,
            )?;
            let old = std::mem::replace(&mut habit.current, pinned);
            habit.previous = Some(old);
            if let Some(name) = name {
                habit.name = name;
            }
            if let Some(phrases) = phrases {
                habit.phrases = phrases;
            }
            habit.updated_ms = now_ms;
            let version = habit.current.version;
            ledger.revision += 1;
            Ok((
                json!({ "revision": ledger.revision, "version": version }),
                true,
            ))
        }
        Op::SetStatus {
            revision,
            id,
            status,
        } => {
            cas(ledger, revision)?;
            find(ledger, &id)?.status = status;
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::Rollback { revision, id } => {
            cas(ledger, revision)?;
            let habit = find(ledger, &id)?;
            let previous = habit.previous.clone().ok_or("no_previous_version")?;
            // The restored pin must still be the enabled version; otherwise the user reviews it again.
            if engine.enabled_version(&previous.skill_id).as_deref()
                != Some(previous.skill_version.as_str())
            {
                return Err("skill_version_changed");
            }
            let current = std::mem::replace(&mut habit.current, previous);
            habit.current.version = current.version + 1;
            habit.previous = Some(current);
            habit.updated_ms = now_ms;
            let version = habit.current.version;
            ledger.revision += 1;
            Ok((
                json!({ "revision": ledger.revision, "version": version }),
                true,
            ))
        }
        Op::Delete { revision, id } => {
            cas(ledger, revision)?;
            let before = ledger.habits.len();
            ledger.habits.retain(|h| h.id != id);
            if ledger.habits.len() == before {
                return Err("unknown_habit");
            }
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::ForgetAll { revision, confirm } => {
            cas(ledger, revision)?;
            if !confirm {
                return Err("confirmation_required");
            }
            ledger.habits.clear();
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::Run { id } => {
            let habit = find(ledger, &id)?;
            if habit.status != Status::Active {
                return Err("habit_paused");
            }
            if engine.enabled_version(&habit.current.skill_id).as_deref()
                != Some(habit.current.skill_version.as_str())
            {
                return Err("skill_version_changed");
            }
            let code = engine.run_skill(&habit.current.skill_id, habit.current.inputs.clone());
            let started = code == "ok";
            let mut mutated = false;
            if retention.is_some() {
                habit.outcomes.push(Outcome {
                    at_ms: now_ms,
                    code: code.to_owned(),
                    started,
                });
                if habit.outcomes.len() > OUTCOMES_MAX {
                    habit.outcomes.remove(0);
                }
                mutated = true;
            }
            Ok((json!({ "code": code, "started": started }), mutated))
        }
        Op::Export {} => Ok((
            json!({ "revision": ledger.revision, "habits": ledger.habits }),
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
