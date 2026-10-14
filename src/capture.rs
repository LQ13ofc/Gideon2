//! Bounded ephemeral PCM, endpointing owned by Core; no device or file writes.
use crate::audio::{AudioError, AudioFrame};
use serde::Serialize;
use sha2::{Digest, Sha256};

#[derive(Clone, Debug, Serialize)]
pub struct CaptureSummary {
    pub session_id: u64,
    pub start_us: u64,
    pub end_us: u64,
    pub samples: usize,
    pub pcm_sha256: String,
    pub reason: &'static str,
}
pub struct Capture {
    pub samples: Vec<f32>,
    start_us: u64,
    wake_end_us: u64,
    end_us: u64,
    last_speech_us: Option<u64>,
}
impl Capture {
    pub fn new(pre_roll: Vec<f32>, end_us: u64) -> Result<Self, AudioError> {
        let duration = pre_roll.len() as u64 * 1_000_000 / 16000;
        if pre_roll.is_empty()
            || pre_roll.len() > 16000
            || end_us < duration
            || pre_roll.iter().any(|x| !x.is_finite() || x.abs() > 1.)
        {
            return Err(AudioError::InvalidFrame);
        }
        Ok(Self {
            samples: pre_roll,
            start_us: end_us - duration,
            wake_end_us: end_us,
            end_us,
            last_speech_us: None,
        })
    }
    pub fn push(
        &mut self,
        frame: AudioFrame,
        speech: bool,
    ) -> Result<Option<&'static str>, AudioError> {
        frame.validate()?;
        if frame.timestamp_us != self.end_us {
            return Err(AudioError::NonMonotonic);
        }
        if self.samples.len() + frame.samples.len() > 16000 * 30 {
            return Ok(Some("capture_too_long"));
        }
        self.end_us = frame.end_us();
        self.samples.extend(frame.samples);
        if speech {
            self.last_speech_us = Some(self.end_us);
        }
        if self
            .last_speech_us
            .is_some_and(|t| self.end_us - t >= 600_000)
        {
            return Ok(Some("capture_completed"));
        }
        if self.last_speech_us.is_none() && self.end_us - self.wake_end_us >= 3_000_000 {
            return Ok(Some("no_speech"));
        }
        Ok(None)
    }
    pub fn summary(&self, session_id: u64, reason: &'static str) -> CaptureSummary {
        let mut digest = Sha256::new();
        for sample in &self.samples {
            digest.update(sample.to_le_bytes());
        }
        CaptureSummary {
            session_id,
            start_us: self.start_us,
            end_us: self.end_us,
            samples: self.samples.len(),
            pcm_sha256: format!("{:x}", digest.finalize()),
            reason,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn frame(ts: u64, value: f32) -> AudioFrame {
        AudioFrame {
            timestamp_us: ts,
            sample_rate: 16000,
            channels: 1,
            samples: vec![value; 1600],
        }
    }
    #[test]
    fn pre_roll_sequence_silence_and_no_speech() {
        let mut c = Capture::new(vec![0.25; 16000], 1_000_000).unwrap();
        assert!(c.push(frame(0, 0.), true).is_err());
        assert_eq!(c.push(frame(1_000_000, 0.5), true).unwrap(), None);
        for i in 1..6 {
            assert_eq!(
                c.push(frame(1_000_000 + i * 100000, 0.), false).unwrap(),
                None
            );
        }
        assert_eq!(
            c.push(frame(1_600_000, 0.), false).unwrap(),
            Some("capture_completed")
        );
        assert_eq!(&c.samples[..16000], &vec![0.25; 16000]);
        assert_eq!(&c.samples[16000..17600], &vec![0.5; 1600]);
        assert_eq!(c.summary(3, "capture_completed").samples, 27200);
        let mut silent = Capture::new(vec![0.; 1600], 100000).unwrap();
        for i in 1..30 {
            assert_eq!(silent.push(frame(i * 100000, 0.), false).unwrap(), None);
        }
        assert_eq!(
            silent.push(frame(3000000, 0.), false).unwrap(),
            Some("no_speech")
        );
    }
    #[test]
    fn long_speech_is_bounded_and_invalid_pcm_does_not_advance() {
        let mut c = Capture::new(vec![0.; 16000], 1_000_000).unwrap();
        for i in 10..300 {
            assert_eq!(c.push(frame(i * 100000, 0.1), true).unwrap(), None);
        }
        assert_eq!(
            c.push(frame(30_000_000, 0.1), true).unwrap(),
            Some("capture_too_long")
        );
        assert_eq!(c.samples.len(), 480000);
        let mut bad = frame(30_000_000, 0.);
        bad.samples[0] = f32::NAN;
        assert!(c.push(bad, true).is_err());
        assert_eq!(c.samples.len(), 480000);
    }
}
