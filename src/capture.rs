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
/// WP-7b grace window: speech that ended up to this long before the wake fired belongs to the wake phrase
/// itself (the wake detector fires after the phrase ends; measured on the lab clips, `hey_plain`, 0.1 to 0.5 s).
pub const WAKE_GRACE_US: u64 = 1_500_000;
/// Silence after the last speech that ends a capture (unchanged).
pub const END_SILENCE_US: u64 = 600_000;
impl Capture {
    /// Counts the wake as speech when the last speech flag seen before the wake is inside the grace window.
    /// The phrase then ends the capture after `END_SILENCE_US` of silence (command_rejected for a bare
    /// "Hey Gideon") instead of `no_speech` after 3 s. Speech older than the window changes nothing.
    pub fn speech_before_wake(mut self, last_speech_us: Option<u64>) -> Self {
        if let Some(t) = last_speech_us {
            if t <= self.wake_end_us && self.wake_end_us - t <= WAKE_GRACE_US {
                self.last_speech_us = Some(self.wake_end_us);
            }
        }
        self
    }
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
            .is_some_and(|t| self.end_us - t >= END_SILENCE_US)
        {
            return Ok(Some("capture_completed"));
        }
        if self.last_speech_us.is_none() && self.end_us - self.wake_end_us >= 3_000_000 {
            return Ok(Some("no_speech"));
        }
        Ok(None)
    }
    /// Test-only accessor: the end of the last speech the capture counted.
    #[cfg(test)]
    pub fn last_speech(&self) -> Option<u64> {
        self.last_speech_us
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
    fn wake_grace_window_turns_a_bare_wake_phrase_into_a_short_capture() {
        // Speech ended 200 ms before the wake fired (the hey_plain case): the wake counts as speech.
        let mut c = Capture::new(vec![0.; 16000], 1_500_000)
            .unwrap()
            .speech_before_wake(Some(1_300_000));
        assert_eq!(c.last_speech(), Some(1_500_000));
        assert_eq!(c.push(frame(1_500_000, 0.), false).unwrap(), None);
        // 600 ms of silence after the wake ends the capture; no_speech is not reached.
        let mut ended = None;
        for i in 1..=6 {
            ended = c
                .push(frame(1_500_000 + i * 100_000, 0.), false)
                .unwrap()
                .or(ended);
        }
        assert_eq!(ended, Some("capture_completed"));
        // Speech older than the grace window changes nothing: the 3 s no_speech rule still applies.
        let mut stale = Capture::new(vec![0.; 16000], 2_000_000)
            .unwrap()
            .speech_before_wake(Some(0));
        assert_eq!(stale.last_speech(), None);
        let mut last = None;
        for i in 1..=30 {
            last = stale
                .push(frame(2_000_000 + (i - 1) * 100_000, 0.), false)
                .unwrap();
            if last.is_some() {
                break;
            }
        }
        assert_eq!(last, Some("no_speech"));
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
