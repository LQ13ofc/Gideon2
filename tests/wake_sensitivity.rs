//! A1 replay: synthetic 100 ms packet timelines through the public detector. No borderline
//! engine asset with scores exists in this repository, so the scores here are synthetic and
//! the claim is only about the threshold scale, not about any real wake engine.
use gideon_base::wake::{Detection, Packet, WakeDescriptor, WakeInput};
use std::collections::BTreeMap;

const PACKET_US: u64 = 100_000;

fn descriptor() -> WakeDescriptor {
    WakeDescriptor {
        engine: "replay-engine".into(),
        supported_phrases: BTreeMap::from([("hey_gideon".into(), "HEY".into())]),
        active_phrase: "hey_gideon".into(),
    }
}

/// Replays `packets` 100 ms frames; a detection with `confidence` ends at the packet `at`.
/// Returns the end timestamps (microseconds) of accepted wakes.
fn replay(
    sensitivity: f32,
    at: Option<usize>,
    confidence: Option<f32>,
    packets: usize,
) -> Vec<u64> {
    let mut input = WakeInput::new(descriptor()).unwrap();
    input.set_sensitivity(sensitivity).unwrap();
    let mut accepted = vec![];
    for n in 0..packets {
        let ts = n as u64 * PACKET_US;
        let detections = if at == Some(n) {
            vec![Detection {
                phrase_id: "hey_gideon".into(),
                confidence,
                start_us: ts,
                end_us: ts + PACKET_US,
                engine: "replay-engine".into(),
            }]
        } else {
            vec![]
        };
        let packet = Packet {
            timestamp_us: ts,
            samples: vec![0.0; 1600],
            detections,
            speech: None,
        };
        if let Some(detection) = input.accept(packet).unwrap() {
            accepted.push(detection.end_us);
        }
    }
    accepted
}

#[test]
fn borderline_wake_is_rejected_at_0_5_and_accepted_at_1_5() {
    // 0.6 is the sensitivity-1.0 threshold: a borderline score for the default.
    let borderline = Some(0.6);
    assert!(replay(0.5, Some(5), borderline, 12).is_empty());
    assert_eq!(replay(1.0, Some(5), borderline, 12), vec![6 * PACKET_US]);
    assert_eq!(replay(1.5, Some(5), borderline, 12), vec![6 * PACKET_US]);
}

#[test]
fn higher_sensitivity_admits_weaker_scores_monotonically() {
    // 0.35 is below the default threshold and above the 1.5 threshold (0.3).
    let weak = Some(0.35);
    assert!(replay(0.5, Some(5), weak, 12).is_empty());
    assert!(replay(1.0, Some(5), weak, 12).is_empty());
    assert_eq!(replay(1.5, Some(5), weak, 12), vec![6 * PACKET_US]);
    // An unscored detection was decided by the engine and is never re-gated.
    for s in [0.5_f32, 1.0, 1.5] {
        assert_eq!(replay(s, Some(5), None, 12), vec![6 * PACKET_US]);
    }
}

#[test]
fn rejected_score_does_not_start_the_cooldown() {
    // Rejected at 0.5 (score 0.7), then a strong detection 4 packets later must still be accepted:
    // the cooldown only tracks accepted wakes.
    let mut input = WakeInput::new(descriptor()).unwrap();
    input.set_sensitivity(0.5).unwrap();
    let mut accepted = vec![];
    for n in 0..12usize {
        let ts = n as u64 * PACKET_US;
        let detections = match n {
            2 => vec![Detection {
                phrase_id: "hey_gideon".into(),
                confidence: Some(0.7),
                start_us: ts,
                end_us: ts + PACKET_US,
                engine: "replay-engine".into(),
            }],
            6 => vec![Detection {
                phrase_id: "hey_gideon".into(),
                confidence: Some(0.95),
                start_us: ts,
                end_us: ts + PACKET_US,
                engine: "replay-engine".into(),
            }],
            _ => vec![],
        };
        let packet = Packet {
            timestamp_us: ts,
            samples: vec![0.0; 1600],
            detections,
            speech: None,
        };
        if let Some(d) = input.accept(packet).unwrap() {
            accepted.push(d.end_us);
        }
    }
    assert_eq!(accepted, vec![7 * PACKET_US]);
}

#[test]
fn live_sensitivity_change_applies_to_the_following_packets() {
    // Same timeline, sensitivity raised before the detection: the borderline wake now passes.
    let mut input = WakeInput::new(descriptor()).unwrap();
    input.set_sensitivity(0.5).unwrap();
    let mut seen = vec![];
    for n in 0..12usize {
        if n == 3 {
            input.set_sensitivity(1.5).unwrap();
        }
        let ts = n as u64 * PACKET_US;
        let detections = if n == 5 {
            vec![Detection {
                phrase_id: "hey_gideon".into(),
                confidence: Some(0.6),
                start_us: ts,
                end_us: ts + PACKET_US,
                engine: "replay-engine".into(),
            }]
        } else {
            vec![]
        };
        let packet = Packet {
            timestamp_us: ts,
            samples: vec![0.0; 1600],
            detections,
            speech: None,
        };
        if let Some(d) = input.accept(packet).unwrap() {
            seen.push(d.end_us);
        }
    }
    assert_eq!(seen, vec![6 * PACKET_US]);
    assert!(input.set_sensitivity(1.51).is_err());
    assert_eq!(input.sensitivity(), 1.5);
}
