//! Internal PCM replay adapter. No detection operation is exposed to IPC clients.
use crate::audio::{AudioError, AudioFrame};
use serde::Deserialize;
use std::collections::VecDeque;

pub const ENGINE: &str = "sherpa-onnx-1.13.8/zipformer-zh-en-3M-2025-12-20-int8-chunk8";

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
}

#[derive(Default)]
pub struct WakeInput {
    last_end: u64,
    last_wake: Option<u64>,
    pre_roll: VecDeque<f32>,
}
impl WakeInput {
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
                d.phrase_id != "hey_gideon"
                    || d.engine != ENGINE
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
    pub fn buffered_samples(&self) -> usize {
        self.pre_roll.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn packet(ts: u64, phrase: Option<&str>) -> Packet {
        Packet {
            timestamp_us: ts,
            samples: vec![0.; 1600],
            detections: phrase
                .map(|p| Detection {
                    phrase_id: p.into(),
                    confidence: None,
                    start_us: ts,
                    end_us: ts + 100000,
                    engine: ENGINE.into(),
                })
                .into_iter()
                .collect(),
        }
    }
    #[test]
    fn bounded_pre_roll_cooldown_and_invalid_frames() {
        let mut input = WakeInput::default();
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
        let mut input = WakeInput::default();
        let mut bad = packet(0, Some("hey_gideon"));
        bad.detections[0].confidence = Some(f32::NAN);
        assert!(input.accept(bad).is_err());
        let mut bad = packet(0, Some("hey_gideon"));
        bad.detections[0].end_us = u64::MAX;
        assert!(input.accept(bad).is_err());
        assert_eq!(input.buffered_samples(), 0);
        assert!(input.accept(packet(0, None)).is_ok());
    }
}
