//! WP-10a Automations: scheduled runs of one enabled Skill with fixed inputs.
//!
//! Permissions: an automation pins the Skill version the user approved when it was created. Before every run the
//! pin is compared with the engine's enabled version; a drift (edited, disabled, dependency or permission lost)
//! pauses the automation with `skill_version_changed` instead of running. The run itself goes through
//! `SkillEngine::run_skill`, so every grant and dependency check of the Skills engine still applies. A refusal by
//! the engine also pauses the automation (`needs_review`), and no run is retried automatically.
//!
//! Timing: `now_ms` is supplied by the caller (virtual clock in tests). Each due slot starts at most once
//! (at-most-once: the next slot is written before the run is requested). A busy engine defers the run to the next
//! tick without counting it. Missed slots are not replayed in a burst.
//!
//! History (run records) follows the Core `history_retention`; `never` records none.

use crate::personal::{self, SkillEngine};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

pub const FILE: &str = "automations.json";
const LIMIT: u64 = 128 * 1024;
const AUTOMATIONS_MAX: usize = 16;
const NAME_MAX: usize = 60;
const SKILL_ID_MAX: usize = 64;
const INPUTS_MAX_BYTES: usize = 2048;
const HISTORY_MAX: usize = 20;
const EVERY_MIN_MS: u64 = 60_000;
const EVERY_MAX_MS: u64 = 30 * personal::DAY_MS;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Active,
    Paused,
    Done,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Schedule {
    Once { at_ms: u64 },
    Every { start_ms: u64, every_ms: u64 },
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RunRecord {
    pub at_ms: u64,
    pub code: String,
    pub started: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Automation {
    pub id: String,
    pub name: String,
    pub skill_id: String,
    /// The Skill version the user approved; a run needs this exact version to be enabled.
    pub skill_version: String,
    pub inputs: Value,
    pub schedule: Schedule,
    pub status: Status,
    pub next_run_ms: Option<u64>,
    pub runs: u32,
    pub last_code: Option<String>,
    pub history: Vec<RunRecord>,
    pub created_ms: u64,
    pub updated_ms: u64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Ledger {
    version: u16,
    revision: u64,
    next_seq: u64,
    automations: Vec<Automation>,
}

impl Default for Ledger {
    fn default() -> Self {
        Self {
            version: 1,
            revision: 0,
            next_seq: 0,
            automations: Vec::new(),
        }
    }
}

impl Ledger {
    fn validate(&self) -> Result<(), &'static str> {
        let mut ids = std::collections::HashSet::new();
        let ok = self.version == 1
            && self.automations.len() <= AUTOMATIONS_MAX
            && self.automations.iter().all(|a| {
                ids.insert(a.id.as_str())
                    && a.skill_id.len() <= SKILL_ID_MAX
                    && a.history.len() <= HISTORY_MAX
                    && schedule_ok(&a.schedule).is_ok()
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
        for automation in &mut self.automations {
            let before = automation.history.len();
            match start {
                None => automation.history.clear(),
                Some(start) => automation.history.retain(|r| r.at_ms >= start),
            }
            changed |= automation.history.len() != before;
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
        skill_id: String,
        #[serde(default)]
        inputs: Option<Value>,
        schedule: Schedule,
    },
    /// Pause or resume. Resuming recomputes the next slot from the clock; a past `once` cannot be resumed.
    SetStatus {
        revision: u64,
        id: String,
        status: Status,
    },
    Delete {
        revision: u64,
        id: String,
    },
    ForgetAll {
        revision: u64,
        confirm: bool,
    },
    /// Runs now through the same checks; the schedule is not advanced.
    RunNow {
        id: String,
    },
    Export {},
}

pub fn parse(value: Value) -> Result<Op, &'static str> {
    personal::parse(value)
}

fn schedule_ok(schedule: &Schedule) -> Result<(), &'static str> {
    match schedule {
        Schedule::Once { .. } => Ok(()),
        Schedule::Every { every_ms, .. } if (EVERY_MIN_MS..=EVERY_MAX_MS).contains(every_ms) => {
            Ok(())
        }
        Schedule::Every { .. } => Err("invalid_schedule"),
    }
}

/// First slot strictly after `now_ms` for a schedule; `None` when a `once` slot has passed.
fn next_slot(schedule: &Schedule, now_ms: u64) -> Option<u64> {
    match *schedule {
        Schedule::Once { at_ms } => (at_ms > now_ms).then_some(at_ms),
        Schedule::Every { start_ms, every_ms } => {
            if start_ms > now_ms {
                Some(start_ms)
            } else {
                let steps = (now_ms - start_ms) / every_ms + 1;
                Some(start_ms + steps * every_ms)
            }
        }
    }
}

pub struct Automations {
    path: PathBuf,
    ledger: Ledger,
}

impl Automations {
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

    /// Starts the due automations, at most one per call to the engine. Returns one event per attempt (no content).
    pub fn run_due(
        &mut self,
        now_ms: u64,
        retention: Option<u64>,
        engine: &mut dyn SkillEngine,
    ) -> Vec<Value> {
        let mut next = self.ledger.clone();
        let mut events = Vec::new();
        let mut changed = next.purge(now_ms, retention);
        let due: Vec<String> = next
            .automations
            .iter()
            .filter(|a| a.status == Status::Active && a.next_run_ms.is_some_and(|t| t <= now_ms))
            .map(|a| a.id.clone())
            .collect();
        for id in due {
            let outcome = run_scheduled(&mut next, &id, now_ms, retention, engine);
            changed = true;
            let deferred = outcome == "deferred";
            events.push(json!({ "id": id, "code": outcome }));
            if deferred {
                // The engine is busy: nothing else can start in this tick either.
                break;
            }
        }
        if changed {
            match personal::save_ledger(&self.path, &next, LIMIT) {
                Ok(()) => self.ledger = next,
                Err(code) => events.push(json!({ "code": code })),
            }
        }
        events
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
            "count": view.automations.len(),
            "capacity": AUTOMATIONS_MAX,
            "automations": view.automations,
        })
    }

    pub fn export(&self) -> Value {
        json!({ "revision": self.ledger.revision, "automations": self.ledger.automations })
    }
}

fn find<'a>(ledger: &'a mut Ledger, id: &str) -> Result<&'a mut Automation, &'static str> {
    ledger
        .automations
        .iter_mut()
        .find(|a| a.id == id)
        .ok_or("unknown_automation")
}

fn cas(ledger: &Ledger, revision: u64) -> Result<(), &'static str> {
    if revision == ledger.revision {
        Ok(())
    } else {
        Err("stale_revision")
    }
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
            skill_id,
            inputs,
            schedule,
        } => {
            cas(ledger, revision)?;
            if ledger.automations.len() >= AUTOMATIONS_MAX {
                return Err("automation_capacity");
            }
            schedule_ok(&schedule)?;
            let next = next_slot(&schedule, now_ms).ok_or("schedule_in_past")?;
            if skill_id.is_empty() || skill_id.len() > SKILL_ID_MAX {
                return Err("invalid_skill_id");
            }
            let skill_version = engine
                .enabled_version(&skill_id)
                .ok_or("skill_not_enabled")?;
            let inputs =
                personal::bounded_object(&inputs.unwrap_or_else(|| json!({})), INPUTS_MAX_BYTES)?;
            let automation = Automation {
                id: personal::next_id("auto", &mut ledger.next_seq),
                name: personal::line(&name, NAME_MAX)?,
                skill_id,
                skill_version,
                inputs,
                schedule,
                status: Status::Active,
                next_run_ms: Some(next),
                runs: 0,
                last_code: None,
                history: Vec::new(),
                created_ms: now_ms,
                updated_ms: now_ms,
            };
            let id = automation.id.clone();
            ledger.automations.push(automation);
            ledger.revision += 1;
            Ok((
                json!({ "id": id, "revision": ledger.revision, "next_run_ms": next }),
                true,
            ))
        }
        Op::SetStatus {
            revision,
            id,
            status,
        } => {
            cas(ledger, revision)?;
            if status == Status::Done {
                return Err("invalid_status");
            }
            let automation = find(ledger, &id)?;
            if automation.status == Status::Done {
                return Err("automation_done");
            }
            if status == Status::Active {
                let next = next_slot(&automation.schedule, now_ms).ok_or("schedule_in_past")?;
                automation.next_run_ms = Some(next);
            }
            automation.status = status;
            automation.updated_ms = now_ms;
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::Delete { revision, id } => {
            cas(ledger, revision)?;
            let before = ledger.automations.len();
            ledger.automations.retain(|a| a.id != id);
            if ledger.automations.len() == before {
                return Err("unknown_automation");
            }
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::ForgetAll { revision, confirm } => {
            cas(ledger, revision)?;
            if !confirm {
                return Err("confirmation_required");
            }
            ledger.automations.clear();
            ledger.revision += 1;
            Ok((json!({ "revision": ledger.revision }), true))
        }
        Op::RunNow { id } => {
            let automation = find(ledger, &id)?;
            if automation.status != Status::Active {
                return Err("automation_paused");
            }
            let code = check_and_start(automation, now_ms, retention, engine, false);
            let started = code == "ok";
            Ok((json!({ "code": code, "started": started }), true))
        }
        Op::Export {} => Ok((
            json!({ "revision": ledger.revision, "automations": ledger.automations }),
            false,
        )),
    }
}

/// Scheduled attempt for one automation. Returns the code; `"deferred"` leaves the slot for the next tick.
fn run_scheduled(
    ledger: &mut Ledger,
    id: &str,
    now_ms: u64,
    retention: Option<u64>,
    engine: &mut dyn SkillEngine,
) -> &'static str {
    let Some(automation) = ledger.automations.iter_mut().find(|a| a.id == id) else {
        return "unknown_automation";
    };
    // At-most-once: the slot is consumed before the run is requested. A deferral gives it back.
    let prior = (automation.status, automation.next_run_ms);
    let following = next_slot(&automation.schedule, now_ms);
    automation.next_run_ms = following;
    if following.is_none() {
        automation.status = Status::Done;
    }
    let code = check_and_start(automation, now_ms, retention, engine, true);
    if code == "deferred" {
        automation.status = prior.0;
        automation.next_run_ms = prior.1;
    }
    code
}

/// Drift check, engine start, and bookkeeping shared by scheduled and manual runs.
fn check_and_start(
    automation: &mut Automation,
    now_ms: u64,
    retention: Option<u64>,
    engine: &mut dyn SkillEngine,
    scheduled: bool,
) -> &'static str {
    if engine.enabled_version(&automation.skill_id).as_deref()
        != Some(automation.skill_version.as_str())
    {
        automation.status = Status::Paused;
        automation.last_code = Some("skill_version_changed".to_owned());
        automation.updated_ms = now_ms;
        return "skill_version_changed";
    }
    let code = engine.run_skill(&automation.skill_id, automation.inputs.clone());
    if code == "skill_busy" || code == "agent_busy" || code == "busy" {
        if scheduled {
            return "deferred";
        }
        return code;
    }
    let started = code == "ok";
    automation.runs += 1;
    automation.last_code = Some(code.to_owned());
    automation.updated_ms = now_ms;
    if retention.is_some() {
        automation.history.push(RunRecord {
            at_ms: now_ms,
            code: code.to_owned(),
            started,
        });
        if automation.history.len() > HISTORY_MAX {
            automation.history.remove(0);
        }
    }
    if !started {
        // The engine refused: the user reviews it before anything else runs.
        automation.status = Status::Paused;
    }
    code
}
