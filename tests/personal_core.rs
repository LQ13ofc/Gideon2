//! WP-10a through the real Core operation path: personal requests, export to a private file, erase confirmation,
//! HUD-03 listen refusal, N-5 queued chat during a voice session, and the habit trigger normal form.
use gideon_base::{
    core::Core,
    habits::normalize_phrase,
    protocol::{Operation, Request},
    storage::Storage,
};
use serde_json::json;
use std::{
    os::unix::fs::PermissionsExt,
    time::{Duration, Instant},
};

fn request(id: &str, operation: Operation) -> Request {
    Request {
        version: 1,
        request_id: id.into(),
        operation,
    }
}

fn personal(area: &str, payload: serde_json::Value) -> Operation {
    Operation::Personal {
        area: area.into(),
        payload,
    }
}

fn open(root: &std::path::Path) -> (Storage, Core) {
    let storage = Storage::open(root).unwrap();
    let mut core = Core::new(Duration::from_secs(30), true);
    core.configure_storage(&storage);
    (storage, core)
}

#[test]
fn personal_requests_are_versioned_cas_checked_and_exported_to_a_private_file() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    let (mut storage, mut core) = open(&root);
    let now = Instant::now();
    let mut send = |core: &mut Core, id: &str, op: Operation| {
        core.handle_with_storage(request(id, op), now, Some(&mut storage))
    };

    // Consent first (revision 0), then a fact on the next revision.
    let consent = send(
        &mut core,
        "c1",
        personal(
            "memory",
            json!({"version": 1, "op": "consent", "revision": 0, "source": "user_typed", "granted": true}),
        ),
    );
    assert_eq!(consent.code, "ok");
    assert_eq!(consent.personal_reply.as_ref().unwrap()["area"], "memory");
    let snapshot = send(&mut core, "s1", Operation::Snapshot);
    assert_eq!(snapshot.personal["memory"]["revision"], 1);

    let add = |revision: u64, text: &str| json!({"version": 1, "op": "add", "revision": revision, "text": text, "kind": "preference", "source": "user_typed"});
    assert_eq!(
        send(&mut core, "a0", personal("memory", add(0, "velho"))).code,
        "stale_revision"
    );
    assert_eq!(
        send(&mut core, "a1", personal("memory", add(1, "Gosto de café"))).code,
        "ok"
    );
    // Unknown field, missing version and unknown area are refused and change nothing.
    let mut extra = add(2, "x");
    extra["surprise"] = json!(1);
    assert_eq!(
        send(&mut core, "a2", personal("memory", extra)).code,
        "invalid_request"
    );
    assert_eq!(
        send(&mut core, "a3", personal("memory", json!({"op": "list"}))).code,
        "unsupported_version"
    );
    assert_eq!(
        send(&mut core, "a4", personal("nope", json!({"version": 1}))).code,
        "unknown_area"
    );
    assert_eq!(
        send(&mut core, "s2", Operation::Snapshot).personal["memory"]["count"],
        1
    );

    // Export: one file, private (0600), in the personal folder; the reply names it.
    let exported = send(&mut core, "e1", Operation::PersonalExport);
    assert_eq!(exported.code, "ok");
    let path = std::path::PathBuf::from(
        exported.personal_reply.unwrap()["reply"]["path"]
            .as_str()
            .unwrap()
            .to_string(),
    );
    assert!(path.starts_with(root.join("personal").join("exports")));
    assert_eq!(
        std::fs::metadata(&path).unwrap().permissions().mode() & 0o077,
        0
    );
    assert!(std::fs::read_to_string(&path)
        .unwrap()
        .contains("Gosto de café"));
    // A later request does not carry the old reply.
    assert!(send(&mut core, "s3", Operation::Snapshot)
        .personal_reply
        .is_none());

    // Erase needs confirm; with it, every area is empty again.
    assert_eq!(
        send(
            &mut core,
            "x1",
            Operation::PersonalEraseAll { confirm: false }
        )
        .code,
        "confirmation_required"
    );
    assert_eq!(
        send(&mut core, "s4", Operation::Snapshot).personal["memory"]["count"],
        1
    );
    assert_eq!(
        send(
            &mut core,
            "x2",
            Operation::PersonalEraseAll { confirm: true }
        )
        .code,
        "ok"
    );
    let after = send(&mut core, "s5", Operation::Snapshot);
    assert_eq!(after.personal["memory"]["count"], 0);
    assert_eq!(after.personal["memory"]["revision"], 0);
    // The export file holds the same data, so the erase removes it as well.
    assert!(!path.exists(), "erase left the export file behind");
}

#[test]
fn listen_start_is_refused_with_the_reason_when_live_audio_is_off() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    let (mut storage, mut core) = open(&root);
    let reply = core.handle_with_storage(
        request("l1", Operation::ListenStart),
        Instant::now(),
        Some(&mut storage),
    );
    assert_eq!(reply.code, "live_audio_disabled");
    assert_eq!(reply.state, gideon_base::protocol::State::Idle);
    assert!(reply.events.iter().all(|e| e.kind != "session_started"));
}

#[test]
fn a_typed_turn_during_a_voice_session_is_queued_once_and_runs_when_it_ends() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    let (mut storage, mut core) = open(&root);
    core.configure_command_wakes(vec!["hey gideon".into()]);
    let now = Instant::now();
    let mut send = |core: &mut Core, id: &str, op: Operation| {
        core.handle_with_storage(request(id, op), now, Some(&mut storage))
    };

    assert_eq!(send(&mut core, "w1", Operation::VirtualWake).code, "ok");
    assert!(send(&mut core, "s1", Operation::Snapshot)
        .session_id
        .is_some());
    let queued = send(
        &mut core,
        "t1",
        Operation::Text {
            raw: "que horas são".into(),
        },
    );
    assert_eq!(queued.code, "queued");
    // One waiting turn at a time: a second one is refused, not dropped silently.
    assert_eq!(
        send(
            &mut core,
            "t2",
            Operation::Text {
                raw: "outra coisa".into()
            }
        )
        .code,
        "busy"
    );
    // Blank text is refused the same way during a session.
    assert_eq!(
        send(&mut core, "t3", Operation::Text { raw: "   ".into() }).code,
        "invalid_text"
    );

    // Ending the voice session lets the queued turn run on the next request.
    let session = send(&mut core, "s2", Operation::Snapshot)
        .session_id
        .unwrap();
    assert_eq!(
        send(
            &mut core,
            "c1",
            Operation::Cancel {
                session_id: session,
            },
        )
        .code,
        "ok"
    );
    let after = send(&mut core, "s3", Operation::Snapshot);
    let transcript = after.transcript.expect("queued turn ran");
    assert_eq!(transcript.raw, "que horas são");
    assert_eq!(transcript.source, "user_text");
}

#[test]
fn habit_trigger_phrases_compare_in_one_normal_form() {
    assert_eq!(normalize_phrase("  Anotar o Dia!  "), "anotar o dia");
    assert_eq!(normalize_phrase("anotar   o dia?"), "anotar o dia");
    assert_eq!(normalize_phrase("   "), "");
    assert_ne!(
        normalize_phrase("anotar o dia"),
        normalize_phrase("anotar o mês")
    );
}
