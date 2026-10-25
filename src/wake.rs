//! Internal PCM replay adapter. No detection operation is exposed to IPC clients.
use crate::audio::{AudioError, AudioFrame};
use serde::Deserialize;
use std::collections::VecDeque;

/// Backend-provided catalog, independent of the Core and selected phrase text.
#[derive(Clone, Debug, Deserialize)]
pub struct WakeDescriptor {
    pub engine: String,
    pub supported_phrases: std::collections::BTreeMap<String, String>,
    pub active_phrase: String,
    /// Several phrases at once (Core runtime keyword sets). Empty = only `active_phrase`.
    #[serde(default)]
    pub active_phrases: Vec<String>,
}
impl WakeDescriptor {
    pub fn validate(&self) -> Result<(), AudioError> {
        if self.engine.is_empty()
            || self.engine.len() > 160
            || self.supported_phrases.is_empty()
            || self.supported_phrases.len() > 8
            || !self.supported_phrases.contains_key(&self.active_phrase)
            || self.supported_phrases.iter().any(|(id, label)| {
                !crate::protocol::valid_id(id) || !crate::protocol::valid_id(label)
            })
            || self.active_ids().len() > crate::phrases::MAX_ACTIVE
            || self
                .active_ids()
                .iter()
                .any(|id| !self.supported_phrases.contains_key(id))
        {
            return Err(AudioError::InvalidFormat);
        }
        Ok(())
    }
    /// Phrases that may wake the session: the list when given, otherwise the single active phrase.
    pub fn active_ids(&self) -> Vec<String> {
        if self.active_phrases.is_empty() {
            vec![self.active_phrase.clone()]
        } else {
            self.active_phrases.clone()
        }
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Detection {
    pub phrase_id: String,
    pub confidence: Option<f32>,
    pub start_us: u64,
    pub end_us: u64,
    pub engine: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Packet {
    pub timestamp_us: u64,
    pub samples: Vec<f32>,
    pub detections: Vec<Detection>,
    #[serde(default)]
    pub speech: Option<bool>,
}

/// Acceptance threshold of a scored detection at sensitivity 1.0.
pub const BASE_ACCEPT_CONFIDENCE: f32 = 0.6;
/// Effective acceptance threshold: `BASE_ACCEPT_CONFIDENCE * factor`, with `factor = 2 - sensitivity`.
/// Sensitivity 0.5 gives factor 1.5 (threshold 0.9: stricter); 1.0 gives 0.6; 1.5 gives factor 0.5
/// (threshold 0.3: more sensitive). A higher sensitivity therefore lowers the threshold.
pub fn accept_threshold(sensitivity: f32) -> f32 {
    BASE_ACCEPT_CONFIDENCE * (2.0 - sensitivity)
}
/// Decision for one detection. A detection without a score was already decided by the engine and
/// passes unchanged; a scored one must reach `accept_threshold(sensitivity)`.
pub fn accepts(confidence: Option<f32>, sensitivity: f32) -> bool {
    confidence.is_none_or(|c| c >= accept_threshold(sensitivity))
}

/// Keyword-spotter threshold at sensitivity 1.0 (the engine default, unchanged).
pub const BASE_KEYWORDS_THRESHOLD: f32 = 0.25;
/// Safe bounds of the spotter threshold handed to the worker (`wake_worker.py` refuses others).
pub const KEYWORDS_THRESHOLD_MIN: f32 = 0.1;
pub const KEYWORDS_THRESHOLD_MAX: f32 = 0.5;
/// Maps the preference to the spotter threshold: `BASE * (2 - sensitivity)`, clamped to the safe
/// bounds. Sensitivity 0.5 gives 0.375 (stricter), 1.0 gives 0.25 (unchanged), 1.5 gives 0.125
/// (more sensitive). Higher sensitivity lowers the threshold, as `accept_threshold` does for scores.
pub fn keywords_threshold(sensitivity: f32) -> f32 {
    (BASE_KEYWORDS_THRESHOLD * (2.0 - sensitivity))
        .clamp(KEYWORDS_THRESHOLD_MIN, KEYWORDS_THRESHOLD_MAX)
}

/// How a `wake_worker.py` process is driven: a fixture replay (finite) or a live PCM stream on stdin.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WorkerMode {
    Replay { fixture: usize },
    Live { start_us: u64 },
}

/// Argument vector of `scripts/wake_worker.py`. Threshold is always explicit (4 decimals). `conditioning`
/// (`auto` or `off`, live only) is passed when given: the replay path never conditions its fixtures.
pub fn worker_args(
    manifest: &str,
    mode: WorkerMode,
    active_phrase: Option<&str>,
    threshold: f32,
    conditioning: Option<&str>,
) -> Vec<String> {
    let mut args = vec![manifest.to_string()];
    match mode {
        WorkerMode::Replay { fixture } => args.push(fixture.to_string()),
        WorkerMode::Live { start_us } => {
            args.push("--live".into());
            args.push("--start-us".into());
            args.push(start_us.to_string());
        }
    }
    if let Some(phrase) = active_phrase {
        args.extend(["--active-phrase".into(), phrase.to_string()]);
    }
    args.push("--keywords-threshold".into());
    args.push(format!("{threshold:.4}"));
    if let Some(mode) = conditioning {
        args.extend(["--conditioning".into(), mode.to_string()]);
    }
    args
}

pub struct WakeInput {
    descriptor: WakeDescriptor,
    /// Ids that may wake the session, fixed at construction (see `WakeDescriptor::active_ids`).
    active: Vec<String>,
    last_end: u64,
    last_wake: Option<u64>,
    pre_roll: VecDeque<f32>,
    sensitivity: f32,
}
impl WakeInput {
    pub fn new(descriptor: WakeDescriptor) -> Result<Self, AudioError> {
        descriptor.validate()?;
        let active = descriptor.active_ids();
        Ok(Self {
            descriptor,
            active,
            last_end: 0,
            last_wake: None,
            pre_roll: VecDeque::new(),
            sensitivity: crate::storage::Config::default().wake_sensitivity,
        })
    }
    /// Live preference: applies to the following packets. Out-of-range values are refused.
    pub fn set_sensitivity(&mut self, sensitivity: f32) -> Result<(), AudioError> {
        if !crate::storage::valid_wake_sensitivity(sensitivity) {
            return Err(AudioError::InvalidFormat);
        }
        self.sensitivity = sensitivity;
        Ok(())
    }
    pub fn sensitivity(&self) -> f32 {
        self.sensitivity
    }
    pub fn accept(&mut self, packet: Packet) -> Result<Option<Detection>, AudioError> {
        let frame = AudioFrame {
            timestamp_us: packet.timestamp_us,
            samples: packet.samples,
            sample_rate: 16000,
            channels: 1,
        };
        frame.validate()?;
        if frame.timestamp_us != self.last_end {
            return Err(AudioError::NonMonotonic);
        }
        if packet.detections.len() > 1
            || packet.detections.iter().any(|d| {
                !self.active.contains(&d.phrase_id)
                    || d.engine != self.descriptor.engine
                    || d.start_us >= d.end_us
                    || d.end_us != frame.end_us()
                    || d.confidence
                        .is_some_and(|c| !c.is_finite() || !(0.0..=1.0).contains(&c))
            })
        {
            return Err(AudioError::InvalidFrame);
        }
        self.last_end = frame.end_us();
        for sample in frame.samples {
            if self.pre_roll.len() == 16000 {
                self.pre_roll.pop_front();
            }
            self.pre_roll.push_back(sample);
        }
        let detection = packet.detections.into_iter().next();
        if let Some(d) = detection {
            // Below-threshold scores are dropped before the cooldown, which only tracks accepted wakes.
            if !accepts(d.confidence, self.sensitivity) {
                return Ok(None);
            }
            if self
                .last_wake
                .is_some_and(|t| d.end_us.saturating_sub(t) < 2_000_000)
            {
                return Ok(None);
            }
            self.last_wake = Some(d.end_us);
            return Ok(Some(d));
        }
        Ok(None)
    }
    pub fn pre_roll(&self) -> Vec<f32> {
        self.pre_roll.iter().copied().collect()
    }
    pub fn buffered_samples(&self) -> usize {
        self.pre_roll.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn input(active: &str) -> WakeInput {
        WakeInput::new(WakeDescriptor {
            engine: "test-engine".into(),
            supported_phrases: [
                ("hey_gideon".into(), "HEY".into()),
                ("okay_gideon".into(), "OKAY".into()),
            ]
            .into(),
            active_phrase: active.into(),
            active_phrases: vec![],
        })
        .unwrap()
    }
    #[test]
    fn selection_is_catalog_driven_and_unknown_selection_fails() {
        let mut selected = input("okay_gideon");
        assert!(selected.accept(packet(0, Some("hey_gideon"))).is_err());
        assert!(selected
            .accept(packet(0, Some("okay_gideon")))
            .unwrap()
            .is_some());
        let descriptor = WakeDescriptor {
            engine: "other-backend".into(),
            supported_phrases: [("custom_phrase".into(), "CUSTOM".into())].into(),
            active_phrase: "unknown".into(),
            active_phrases: vec![],
        };
        assert!(WakeInput::new(descriptor).is_err());
    }
    fn packet(ts: u64, phrase: Option<&str>) -> Packet {
        Packet {
            timestamp_us: ts,
            samples: vec![0.; 1600],
            speech: None,
            detections: phrase
                .map(|p| Detection {
                    phrase_id: p.into(),
                    confidence: None,
                    start_us: ts,
                    end_us: ts + 100000,
                    engine: "test-engine".into(),
                })
                .into_iter()
                .collect(),
        }
    }
    #[test]
    fn bounded_pre_roll_cooldown_and_invalid_frames() {
        let mut input = input("hey_gideon");
        assert!(input.accept(packet(0, Some("okay_gideon"))).is_err());
        assert!(input
            .accept(packet(0, Some("hey_gideon")))
            .unwrap()
            .is_some());
        assert!(input
            .accept(packet(100000, Some("hey_gideon")))
            .unwrap()
            .is_none());
        assert!(input.accept(packet(0, None)).is_err());
        for n in 2..30 {
            input.accept(packet(n * 100000, None)).unwrap();
        }
        assert_eq!(input.buffered_samples(), 16000);
        assert!(input
            .accept(packet(3000000, Some("hey_gideon")))
            .unwrap()
            .is_some());
    }
    #[test]
    fn rejects_scores_and_spans_before_mutating_state() {
        let mut input = input("hey_gideon");
        let mut bad = packet(0, Some("hey_gideon"));
        bad.detections[0].confidence = Some(f32::NAN);
        assert!(input.accept(bad).is_err());
        let mut bad = packet(0, Some("hey_gideon"));
        bad.detections[0].end_us = u64::MAX;
        assert!(input.accept(bad).is_err());
        assert_eq!(input.buffered_samples(), 0);
        assert!(input.accept(packet(0, None)).is_ok());
    }
    #[test]
    fn sensitivity_scales_the_acceptance_threshold() {
        // Higher sensitivity lowers the threshold: 0.5 -> 0.9, 1.0 -> 0.6, 1.5 -> 0.3.
        assert!(accept_threshold(0.5) > accept_threshold(1.0));
        assert!(accept_threshold(1.0) > accept_threshold(1.5));
        assert!(!accepts(Some(0.7), 0.5));
        assert!(accepts(Some(0.7), 1.0));
        assert!(!accepts(Some(0.35), 1.0));
        assert!(accepts(Some(0.35), 1.5));
        assert!(!accepts(Some(0.29), 1.5));
        // Unscored detections were decided by the engine and are never re-gated.
        assert!(accepts(None, 0.5));
    }
    #[test]
    fn set_sensitivity_refuses_out_of_range_values() {
        let mut input = input("hey_gideon");
        assert_eq!(input.sensitivity(), 1.0);
        for bad in [0.49, 1.51, f32::NAN, f32::INFINITY] {
            assert!(input.set_sensitivity(bad).is_err());
        }
        assert_eq!(input.sensitivity(), 1.0);
        input.set_sensitivity(1.5).unwrap();
        assert_eq!(input.sensitivity(), 1.5);
    }
}
