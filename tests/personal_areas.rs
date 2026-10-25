//! WP-10a integration tests for the personal-data areas (Memory, Souls, Habits, Automations, Conversations).
//! The modules are compiled from src/ by path, so these tests run before src/lib.rs exports them (see docs/WP10a.md).
#![allow(dead_code)]

#[path = "../src/automations.rs"]
mod automations;
#[path = "../src/conversations.rs"]
mod conversations;
#[path = "../src/habits.rs"]
mod habits;
#[path = "../src/memory.rs"]
mod memory;
#[path = "../src/personal.rs"]
mod personal;
#[path = "../src/souls.rs"]
mod souls;

use personal::{Personal, SkillEngine, DAY_MS};
use serde_json::{json, Value};
use std::{collections::HashMap, fs, os::unix::fs::PermissionsExt, path::Path};

/// Fake skills engine: enabled versions by id, one canned answer for every start, and a log of starts.
#[derive(Default)]
struct Fake {
    enabled: HashMap<String, String>,
    answer: Option<&'static str>,
    runs: Vec<(String, Value)>,
}

impl SkillEngine for Fake {
    fn enabled_version(&self, skill_id: &str) -> Option<String> {
        self.enabled.get(skill_id).cloned()
    }
    fn run_skill(&mut self, skill_id: &str, inputs: Value) -> &'static str {
        self.runs.push((skill_id.to_owned(), inputs));
        self.answer.unwrap_or("ok")
    }
}

fn skill(version: &str) -> Fake {
    let mut fake = Fake::default();
    fake.enabled.insert("notas".into(), version.into());
    fake
}

fn open(root: &Path) -> Personal {
    Personal::open(&root.join("personal")).unwrap()
}

fn call(
    p: &mut Personal,
    area: &str,
    payload: Value,
    now: u64,
    ret: Option<u64>,
    e: &mut Fake,
) -> Result<Value, &'static str> {
    p.apply(area, payload, now, ret, e)
}

const WINDOW: Option<u64> = Some(30 * DAY_MS);

// ----------------------------------------------------------------------------- Memory

#[test]
fn memory_needs_consent_checks_cas_and_edits() {
    let tmp = tempfile::tempdir().unwrap();
    let mut p = open(tmp.path());
    let mut e = Fake::default();
    let now = 1_000;
    assert_eq!(
        call(
            &mut p,
            "memory",
            json!({"version":1,"op":"add","revision":0,"text":"Gosto de café","kind":"preference","source":"user_typed"}),
            now,
            WINDOW,
            &mut e
        ),
        Err("consent_required")
    );
    let r = call(
        &mut p,
        "memory",
        json!({"version":1,"op":"consent","revision":0,"source":"user_typed","granted":true}),
        now,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert_eq!(r["revision"], 1);
    let added = call(&mut p, "memory", json!({"version":1,"op":"add","revision":1,"text":"Gosto de café","kind":"preference","source":"user_typed"}), now, WINDOW, &mut e).unwrap();
    assert_eq!(added["id"], "fact_1");
    assert_eq!(
        call(
            &mut p,
            "memory",
            json!({"version":1,"op":"add","revision":1,"text":"outro","kind":"fact","source":"user_typed"}),
            now,
            WINDOW,
            &mut e
        ),
        Err("stale_revision")
    );
    assert_eq!(
        call(
            &mut p,
            "memory",
            json!({"version":1,"op":"edit","revision":2,"id":"fact_1","text":"   "}),
            now,
            WINDOW,
            &mut e
        ),
        Err("invalid_text")
    );
    call(
        &mut p,
        "memory",
        json!({"version":1,"op":"edit","revision":2,"id":"fact_1","text":"Prefiro chá"}),
        now,
        WINDOW,
        &mut e,
    )
    .unwrap();
    let hits = call(
        &mut p,
        "memory",
        json!({"version":1,"op":"search","query":"CHÁ"}),
        now,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert_eq!(hits["hits"].as_array().unwrap().len(), 1);
    let snap = p.memory.snapshot(now, WINDOW);
    assert_eq!(snap["count"], 1);
    assert_eq!(snap["facts"][0]["text"], "Prefiro chá");
}

#[test]
fn memory_conversation_facts_follow_retention_and_ttl() {
    let tmp = tempfile::tempdir().unwrap();
    let mut p = open(tmp.path());
    let mut e = Fake::default();
    let t0 = 5 * DAY_MS;
    call(
        &mut p,
        "memory",
        json!({"version":1,"op":"consent","revision":0,"source":"conversation","granted":true}),
        t0,
        WINDOW,
        &mut e,
    )
    .unwrap();
    let add = json!({"version":1,"op":"add","revision":1,"text":"Reunião sexta","kind":"context","source":"conversation"});
    assert_eq!(
        call(&mut p, "memory", add.clone(), t0, None, &mut e),
        Err("retention_never")
    );
    call(&mut p, "memory", add, t0, WINDOW, &mut e).unwrap();
    // Outside the 30-day window the conversation fact is gone.
    assert_eq!(p.memory.snapshot(t0 + 31 * DAY_MS, WINDOW)["count"], 0);
    // A TTL drops a user fact at its time; the conversation fact stays until its own window ends.
    call(
        &mut p,
        "memory",
        json!({"version":1,"op":"consent","revision":2,"source":"user_typed","granted":true}),
        t0,
        WINDOW,
        &mut e,
    )
    .unwrap();
    call(&mut p, "memory", json!({"version":1,"op":"add","revision":3,"text":"Temporário","kind":"fact","source":"user_typed","ttl_days":1}), t0, WINDOW, &mut e).unwrap();
    assert_eq!(p.memory.snapshot(t0 + DAY_MS / 2, WINDOW)["count"], 2);
    assert_eq!(p.memory.snapshot(t0 + DAY_MS + 1, WINDOW)["count"], 1);
    assert_eq!(
        call(
            &mut p,
            "memory",
            json!({"version":1,"op":"add","revision":4,"text":"x","kind":"fact","source":"user_typed","ttl_days":0}),
            t0,
            WINDOW,
            &mut e
        ),
        Err("invalid_ttl")
    );
}

#[test]
fn memory_revoking_consent_and_forget_all_erase_facts() {
    let tmp = tempfile::tempdir().unwrap();
    let mut p = open(tmp.path());
    let mut e = Fake::default();
    let now = 10;
    call(
        &mut p,
        "memory",
        json!({"version":1,"op":"consent","revision":0,"source":"import","granted":true}),
        now,
        WINDOW,
        &mut e,
    )
    .unwrap();
    call(&mut p, "memory", json!({"version":1,"op":"add","revision":1,"text":"Importado","kind":"fact","source":"import"}), now, WINDOW, &mut e).unwrap();
    call(
        &mut p,
        "memory",
        json!({"version":1,"op":"consent","revision":2,"source":"import","granted":false}),
        now,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert_eq!(p.memory.snapshot(now, WINDOW)["count"], 0);
    assert_eq!(
        call(
            &mut p,
            "memory",
            json!({"version":1,"op":"forget_all","revision":3,"confirm":false}),
            now,
            WINDOW,
            &mut e
        ),
        Err("confirmation_required")
    );
    let exported = call(
        &mut p,
        "memory",
        json!({"version":1,"op":"export"}),
        now,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert!(exported["facts"].is_array());
    call(
        &mut p,
        "memory",
        json!({"version":1,"op":"forget_all","revision":3,"confirm":true}),
        now,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert_eq!(p.memory.snapshot(now, WINDOW)["consent"]["import"], false);
}

// ----------------------------------------------------------------------------- Souls

#[test]
fn souls_provenance_rules_and_active_hint() {
    let tmp = tempfile::tempdir().unwrap();
    let mut p = open(tmp.path());
    let mut e = Fake::default();
    let now = 1;
    let bad_inferred = json!({"version":1,"op":"create","revision":0,"name":"Eu","description":"d","style":"Direto","priorities":["clareza"],"mode":"influence","provenance":{"kind":"inferred_from_chat","evidence":["msg 3"],"confidence":0.95}});
    assert_eq!(
        call(&mut p, "souls", bad_inferred, now, WINDOW, &mut e),
        Err("invalid_provenance")
    );
    let docs_no_consent = json!({"version":1,"op":"create","revision":0,"name":"Eu","description":"d","style":"Direto","priorities":[],"mode":"simulation","provenance":{"kind":"user_documents","evidence":["doc A"],"confidence":0.9}});
    assert_eq!(
        call(&mut p, "souls", docs_no_consent, now, WINDOW, &mut e),
        Err("consent_required")
    );
    let declared = json!({"version":1,"op":"create","revision":0,"name":"Calmo","description":"Tom sereno","style":"Frases curtas","priorities":["segurança","clareza"],"mode":"influence","provenance":{"kind":"declared","evidence":[],"confidence":1.0}});
    let made = call(&mut p, "souls", declared, now, WINDOW, &mut e).unwrap();
    let id = made["id"].as_str().unwrap().to_owned();
    assert_eq!(p.souls.active_hint(), None);
    call(
        &mut p,
        "souls",
        json!({"version":1,"op":"activate","revision":1,"id":id}),
        now,
        WINDOW,
        &mut e,
    )
    .unwrap();
    let hint = p.souls.active_hint().unwrap();
    assert!(hint.contains("Frases curtas") && hint.contains("Não substitui autenticação"));
    let preview = call(
        &mut p,
        "souls",
        json!({"version":1,"op":"preview","id":id}),
        now,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert!(preview["note"].as_str().unwrap().contains("não muda"));
    // Provenance is not editable through update.
    assert_eq!(
        call(
            &mut p,
            "souls",
            json!({"version":1,"op":"update","revision":2,"id":id,"provenance":{}}),
            now,
            WINDOW,
            &mut e
        ),
        Err("invalid_request")
    );
    call(
        &mut p,
        "souls",
        json!({"version":1,"op":"update","revision":2,"id":id,"style":"Formal"}),
        now,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert_eq!(p.souls.snapshot()["souls"][0]["version"], 2);
    call(
        &mut p,
        "souls",
        json!({"version":1,"op":"delete","revision":3,"id":id}),
        now,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert!(p.souls.snapshot()["active"].is_null());
}

// ----------------------------------------------------------------------------- Habits

#[test]
fn habits_pin_skill_version_run_roll_back_and_refuse_drift() {
    let tmp = tempfile::tempdir().unwrap();
    let mut p = open(tmp.path());
    let mut e = skill("1.0.0");
    let now = 100;
    let create = |rev: u64| json!({"version":1,"op":"create","revision":rev,"name":"Anotar","phrases":["anota isso"],"skill_id":"notas","inputs":{"pasta":"diario"}});
    assert_eq!(
        call(
            &mut p,
            "habits",
            create(0),
            now,
            WINDOW,
            &mut Fake::default()
        ),
        Err("skill_not_enabled")
    );
    assert_eq!(
        call(
            &mut p,
            "habits",
            json!({"version":1,"op":"create","revision":0,"name":"x","skill_id":"notas","inputs":"texto"}),
            now,
            WINDOW,
            &mut e
        ),
        Err("invalid_inputs")
    );
    let made = call(&mut p, "habits", create(0), now, WINDOW, &mut e).unwrap();
    let id = made["id"].as_str().unwrap().to_owned();
    let run = call(
        &mut p,
        "habits",
        json!({"version":1,"op":"run","id":id}),
        now,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert_eq!(run["started"], true);
    assert_eq!(e.runs[0].1, json!({"pasta":"diario"}));
    // The skill changed version: the habit refuses to run until the user reviews it.
    e.enabled.insert("notas".into(), "1.1.0".into());
    assert_eq!(
        call(
            &mut p,
            "habits",
            json!({"version":1,"op":"run","id":id}),
            now,
            WINDOW,
            &mut e
        ),
        Err("skill_version_changed")
    );
    // Editing re-pins to 1.1.0; rollback to 1.0.0 is refused while 1.1.0 is the enabled one.
    call(
        &mut p,
        "habits",
        json!({"version":1,"op":"edit","revision":1,"id":id,"inputs":{"pasta":"trabalho"}}),
        now,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert_eq!(
        call(
            &mut p,
            "habits",
            json!({"version":1,"op":"rollback","revision":2,"id":id}),
            now,
            WINDOW,
            &mut e
        ),
        Err("skill_version_changed")
    );
    e.enabled.insert("notas".into(), "1.0.0".into());
    call(
        &mut p,
        "habits",
        json!({"version":1,"op":"rollback","revision":2,"id":id}),
        now,
        WINDOW,
        &mut e,
    )
    .unwrap();
    call(
        &mut p,
        "habits",
        json!({"version":1,"op":"set_status","revision":3,"id":id,"status":"paused"}),
        now,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert_eq!(
        call(
            &mut p,
            "habits",
            json!({"version":1,"op":"run","id":id}),
            now,
            WINDOW,
            &mut e
        ),
        Err("habit_paused")
    );
}

#[test]
fn habit_outcomes_are_history_under_retention() {
    let tmp = tempfile::tempdir().unwrap();
    let mut p = open(tmp.path());
    let mut e = skill("1.0.0");
    let op = json!({"version":1,"op":"create","revision":0,"name":"Anotar","skill_id":"notas","inputs":{}});
    let id = call(&mut p, "habits", op, 0, None, &mut e).unwrap()["id"]
        .as_str()
        .unwrap()
        .to_owned();
    call(
        &mut p,
        "habits",
        json!({"version":1,"op":"run","id":id}),
        0,
        None,
        &mut e,
    )
    .unwrap();
    assert!(p.habits.snapshot(0, None)["habits"][0]["outcomes"]
        .as_array()
        .unwrap()
        .is_empty());
    call(
        &mut p,
        "habits",
        json!({"version":1,"op":"run","id":id}),
        0,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert_eq!(
        p.habits.snapshot(0, WINDOW)["habits"][0]["outcomes"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    // After the window, the outcome is dropped.
    assert!(
        p.habits.snapshot(31 * DAY_MS, WINDOW)["habits"][0]["outcomes"]
            .as_array()
            .unwrap()
            .is_empty()
    );
}

// ----------------------------------------------------------------------------- Automations

fn create_auto(
    p: &mut Personal,
    e: &mut Fake,
    rev: u64,
    now: u64,
    schedule: Value,
) -> Result<String, &'static str> {
    let payload = json!({"version":1,"op":"create","revision":rev,"name":"Relatório","skill_id":"notas","inputs":{"formato":"curto"},"schedule":schedule});
    call(p, "automations", payload, now, WINDOW, e).map(|v| v["id"].as_str().unwrap().to_owned())
}

#[test]
fn once_automation_runs_one_time_through_the_engine() {
    let tmp = tempfile::tempdir().unwrap();
    let mut p = open(tmp.path());
    let mut e = skill("1.0.0");
    let now = 0;
    let id = create_auto(&mut p, &mut e, 0, now, json!({"kind":"once","at_ms":1000})).unwrap();
    assert!(p.tick(500, WINDOW, &mut e).is_empty());
    let events = p.tick(1000, WINDOW, &mut e);
    assert_eq!(events, vec![json!({"id": id, "code": "ok"})]);
    assert_eq!(e.runs.len(), 1);
    assert_eq!(e.runs[0].1, json!({"formato":"curto"}));
    assert!(p.tick(5000, WINDOW, &mut e).is_empty());
    let snap = p.automations.snapshot(5000, WINDOW);
    assert_eq!(snap["automations"][0]["status"], "done");
    assert_eq!(snap["automations"][0]["runs"], 1);
}

#[test]
fn every_automation_skips_missed_slots_without_a_burst() {
    let tmp = tempfile::tempdir().unwrap();
    let mut p = open(tmp.path());
    let mut e = skill("1.0.0");
    let minute = 60_000;
    let id = create_auto(
        &mut p,
        &mut e,
        0,
        0,
        json!({"kind":"every","start_ms":minute,"every_ms":minute}),
    )
    .unwrap();
    // Ten slots were missed: one run now, next slot strictly in the future.
    let events = p.tick(10 * minute + 1, WINDOW, &mut e);
    assert_eq!(events.len(), 1);
    assert_eq!(e.runs.len(), 1);
    let snap = p.automations.snapshot(10 * minute + 1, WINDOW);
    assert_eq!(snap["automations"][0]["next_run_ms"], 11 * minute);
    assert!(p.tick(10 * minute + 2, WINDOW, &mut e).is_empty());
    assert!(!id.is_empty());
}

#[test]
fn busy_engine_defers_and_drift_or_refusal_pauses() {
    let tmp = tempfile::tempdir().unwrap();
    let mut p = open(tmp.path());
    let mut e = skill("1.0.0");
    let id = create_auto(&mut p, &mut e, 0, 0, json!({"kind":"once","at_ms":100})).unwrap();
    e.answer = Some("skill_busy");
    assert_eq!(
        p.tick(100, WINDOW, &mut e),
        vec![json!({"id": id, "code": "deferred"})]
    );
    assert_eq!(
        p.automations.snapshot(100, WINDOW)["automations"][0]["status"],
        "active"
    );
    e.answer = None;
    p.tick(100, WINDOW, &mut e);
    assert_eq!(
        e.runs.len(),
        2,
        "the deferred attempt reached the engine once, then the retry ran"
    );

    // Drift: the skill changes version after the user approved 1.0.0.
    let mut e2 = skill("1.0.0");
    let id2 = create_auto(&mut p, &mut e2, 1, 0, json!({"kind":"once","at_ms":200})).unwrap();
    e2.enabled.insert("notas".into(), "2.0.0".into());
    assert_eq!(
        p.tick(200, WINDOW, &mut e2),
        vec![json!({"id": id2, "code": "skill_version_changed"})]
    );
    assert!(e2.runs.is_empty());
    assert_eq!(
        p.automations.snapshot(200, WINDOW)["automations"][1]["status"],
        "paused"
    );

    // Refusal by the engine pauses the automation and records the code.
    let mut e3 = skill("2.0.0");
    let id3 = create_auto(
        &mut p,
        &mut e3,
        2,
        0,
        json!({"kind":"every","start_ms":300,"every_ms":60000}),
    )
    .unwrap();
    e3.answer = Some("destructive_disabled");
    p.tick(300, WINDOW, &mut e3);
    let snap = p.automations.snapshot(300, WINDOW);
    let auto = snap["automations"]
        .as_array()
        .unwrap()
        .iter()
        .find(|a| a["id"] == id3)
        .unwrap();
    assert_eq!(auto["status"], "paused");
    assert_eq!(auto["last_code"], "destructive_disabled");
    assert_eq!(
        call(
            &mut p,
            "automations",
            json!({"version":1,"op":"run_now","id":id3}),
            300,
            WINDOW,
            &mut e3
        ),
        Err("automation_paused")
    );
}

#[test]
fn automation_schedule_validation_and_history_retention() {
    let tmp = tempfile::tempdir().unwrap();
    let mut p = open(tmp.path());
    let mut e = skill("1.0.0");
    assert_eq!(
        create_auto(&mut p, &mut e, 0, 500, json!({"kind":"once","at_ms":100})),
        Err("schedule_in_past")
    );
    assert_eq!(
        create_auto(
            &mut p,
            &mut e,
            0,
            0,
            json!({"kind":"every","start_ms":0,"every_ms":1000})
        ),
        Err("invalid_schedule")
    );
    assert_eq!(
        create_auto(&mut p, &mut e, 9, 0, json!({"kind":"once","at_ms":10})),
        Err("stale_revision")
    );
    let id = create_auto(
        &mut p,
        &mut e,
        0,
        0,
        json!({"kind":"every","start_ms":60000,"every_ms":60000}),
    )
    .unwrap();
    let manual = json!({"version":1,"op":"run_now","id":id});
    call(&mut p, "automations", manual.clone(), 0, None, &mut e).unwrap();
    assert!(p.automations.snapshot(0, None)["automations"][0]["history"]
        .as_array()
        .unwrap()
        .is_empty());
    call(&mut p, "automations", manual, 0, WINDOW, &mut e).unwrap();
    assert_eq!(
        p.automations.snapshot(0, WINDOW)["automations"][0]["history"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    call(
        &mut p,
        "automations",
        json!({"version":1,"op":"delete","revision":1,"id":id}),
        0,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert_eq!(p.automations.snapshot(0, WINDOW)["count"], 0);
}

// ----------------------------------------------------------------------------- Conversations

#[test]
fn conversations_append_title_rename_delete_and_never_retention() {
    let tmp = tempfile::tempdir().unwrap();
    let mut p = open(tmp.path());
    let mut e = Fake::default();
    let turn =
        json!({"version":1,"op":"append","revision":0,"role":"user","text":"Que horas são?"});
    assert_eq!(
        call(&mut p, "conversations", turn.clone(), 1, None, &mut e),
        Err("retention_never")
    );
    assert!(!tmp.path().join("personal/conversations.json").exists());
    let made = call(&mut p, "conversations", turn, 1, WINDOW, &mut e).unwrap();
    let sid = made["session_id"].as_str().unwrap().to_owned();
    assert_eq!(
        p.conversations.snapshot(1, WINDOW)["sessions"][0]["title"],
        "Que horas são?"
    );
    call(&mut p, "conversations", json!({"version":1,"op":"append","revision":1,"session_id":sid,"role":"assistant","text":"São 10h."}), 2, WINDOW, &mut e).unwrap();
    let got = call(
        &mut p,
        "conversations",
        json!({"version":1,"op":"get","session_id":sid}),
        2,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert_eq!(got["session"]["turns"].as_array().unwrap().len(), 2);
    assert_eq!(
        call(
            &mut p,
            "conversations",
            json!({"version":1,"op":"append","revision":2,"session_id":sid,"role":"user","text":"a\u{7}b"}),
            3,
            WINDOW,
            &mut e
        ),
        Err("invalid_text")
    );
    call(
        &mut p,
        "conversations",
        json!({"version":1,"op":"rename","revision":2,"session_id":sid,"title":"Horário"}),
        3,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert_eq!(
        call(
            &mut p,
            "conversations",
            json!({"version":1,"op":"forget_all","revision":3,"confirm":false}),
            3,
            WINDOW,
            &mut e
        ),
        Err("confirmation_required")
    );
    call(
        &mut p,
        "conversations",
        json!({"version":1,"op":"delete","revision":3,"session_id":sid}),
        3,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert_eq!(p.conversations.snapshot(3, WINDOW)["count"], 0);
}

#[test]
fn conversations_leave_the_window_when_older_than_retention() {
    let tmp = tempfile::tempdir().unwrap();
    let mut p = open(tmp.path());
    let mut e = Fake::default();
    let dir = tmp.path().join("personal");
    call(
        &mut p,
        "conversations",
        json!({"version":1,"op":"append","revision":0,"role":"user","text":"oi"}),
        0,
        WINDOW,
        &mut e,
    )
    .unwrap();
    assert_eq!(p.conversations.snapshot(31 * DAY_MS, WINDOW)["count"], 0);
    // Under `never` a refused append still erases the stored history, and the erasure is on disk.
    assert_eq!(
        call(
            &mut p,
            "conversations",
            json!({"version":1,"op":"append","revision":1,"role":"user","text":"outra"}),
            0,
            None,
            &mut e
        ),
        Err("retention_never")
    );
    let reopened = Personal::open(&dir).unwrap();
    assert_eq!(reopened.conversations.snapshot(0, WINDOW)["count"], 0);
}

// ----------------------------------------------------------------------------- Aggregate

#[test]
fn requests_are_strict_and_versioned() {
    let tmp = tempfile::tempdir().unwrap();
    let mut p = open(tmp.path());
    let mut e = Fake::default();
    assert_eq!(
        call(&mut p, "memory", json!({"op":"export"}), 0, WINDOW, &mut e),
        Err("unsupported_version")
    );
    assert_eq!(
        call(
            &mut p,
            "memory",
            json!({"version":2,"op":"export"}),
            0,
            WINDOW,
            &mut e
        ),
        Err("unsupported_version")
    );
    assert_eq!(
        call(
            &mut p,
            "memory",
            json!({"version":1,"op":"export","extra":1}),
            0,
            WINDOW,
            &mut e
        ),
        Err("invalid_request")
    );
    assert_eq!(
        call(&mut p, "nope", json!({"version":1}), 0, WINDOW, &mut e),
        Err("unknown_area")
    );
}

#[test]
fn ledgers_are_private_and_survive_reopen() {
    let tmp = tempfile::tempdir().unwrap();
    let dir = tmp.path().join("personal");
    let mut e = Fake::default();
    {
        let mut p = Personal::open(&dir).unwrap();
        call(
            &mut p,
            "memory",
            json!({"version":1,"op":"consent","revision":0,"source":"user_typed","granted":true}),
            0,
            WINDOW,
            &mut e,
        )
        .unwrap();
        call(&mut p, "memory", json!({"version":1,"op":"add","revision":1,"text":"Persistente","kind":"fact","source":"user_typed"}), 0, WINDOW, &mut e).unwrap();
    }
    let mode = fs::metadata(dir.join("memory.json"))
        .unwrap()
        .permissions()
        .mode()
        & 0o777;
    assert_eq!(mode, 0o600);
    assert_eq!(fs::metadata(&dir).unwrap().permissions().mode() & 0o077, 0);
    let p = Personal::open(&dir).unwrap();
    assert_eq!(
        p.memory.snapshot(0, WINDOW)["facts"][0]["text"],
        "Persistente"
    );
}

#[test]
fn corrupt_or_linked_ledgers_fail_closed() {
    let tmp = tempfile::tempdir().unwrap();
    let dir = tmp.path().join("personal");
    fs::create_dir_all(&dir).unwrap();
    let file = dir.join("memory.json");
    fs::write(&file, b"{not json").unwrap();
    fs::set_permissions(&file, fs::Permissions::from_mode(0o600)).unwrap();
    assert!(Personal::open(&dir).is_err());
    fs::remove_file(&file).unwrap();
    let elsewhere = tmp.path().join("elsewhere.json");
    fs::write(&elsewhere, b"{}").unwrap();
    std::os::unix::fs::symlink(&elsewhere, &file).unwrap();
    assert_eq!(Personal::open(&dir).err(), Some("ledger_unreadable"));
}

#[test]
fn export_all_then_erase_all_leaves_nothing_on_disk() {
    let tmp = tempfile::tempdir().unwrap();
    let dir = tmp.path().join("personal");
    let mut e = skill("1.0.0");
    let mut p = Personal::open(&dir).unwrap();
    call(
        &mut p,
        "memory",
        json!({"version":1,"op":"consent","revision":0,"source":"user_typed","granted":true}),
        0,
        WINDOW,
        &mut e,
    )
    .unwrap();
    call(&mut p, "memory", json!({"version":1,"op":"add","revision":1,"text":"Apagar","kind":"fact","source":"user_typed"}), 0, WINDOW, &mut e).unwrap();
    call(
        &mut p,
        "conversations",
        json!({"version":1,"op":"append","revision":0,"role":"user","text":"oi"}),
        0,
        WINDOW,
        &mut e,
    )
    .unwrap();
    let export = p.export_all(0, WINDOW);
    assert_eq!(export["memory"]["facts"].as_array().unwrap().len(), 1);
    assert_eq!(
        export["conversations"]["sessions"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    p.erase_all().unwrap();
    for name in [
        "memory.json",
        "souls.json",
        "habits.json",
        "automations.json",
        "conversations.json",
    ] {
        assert!(!dir.join(name).exists(), "{name} survived erase_all");
    }
    assert_eq!(p.snapshot(0, WINDOW)["memory"]["count"], 0);
}

#[test]
fn tick_with_nothing_due_is_silent_and_snapshot_has_every_area() {
    let tmp = tempfile::tempdir().unwrap();
    let mut p = open(tmp.path());
    let mut e = Fake::default();
    assert!(p.tick(0, WINDOW, &mut e).is_empty());
    let snap = p.snapshot(0, WINDOW);
    for area in ["memory", "souls", "habits", "automations", "conversations"] {
        assert!(snap[area].is_object(), "missing {area}");
    }
    assert_eq!(snap["retention"], "on");
}
