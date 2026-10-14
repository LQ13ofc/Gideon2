use std::collections::VecDeque;

#[derive(Debug, PartialEq, Eq)]
pub enum AudioError {
    InvalidFormat,
    InvalidFrame,
    NonMonotonic,
    Backpressure,
    Unavailable,
}

pub struct AudioFrame {
    pub timestamp_us: u64,
    pub sample_rate: u32,
    pub channels: u16,
    pub samples: Vec<f32>,
}
impl AudioFrame {
    pub fn validate(&self) -> Result<(), AudioError> {
        if self.sample_rate != 16000 || self.channels != 1 {
            return Err(AudioError::InvalidFormat);
        }
        if self.samples.is_empty()
            || self.samples.len() > 1600
            || self.samples.iter().any(|s| !s.is_finite() || s.abs() > 1.)
        {
            return Err(AudioError::InvalidFrame);
        }
        if self
            .timestamp_us
            .checked_add(self.samples.len() as u64 * 1_000_000 / self.sample_rate as u64)
            .is_none()
        {
            return Err(AudioError::InvalidFrame);
        }
        Ok(())
    }
    pub fn end_us(&self) -> u64 {
        self.timestamp_us
            .saturating_add(self.samples.len() as u64 * 1_000_000 / self.sample_rate as u64)
    }
}
pub trait AudioSource {
    fn next_frame(&mut self) -> Result<Option<AudioFrame>, AudioError>;
}
pub trait AudioSink {
    fn write(&mut self, frame: AudioFrame) -> Result<(), AudioError>;
}
/// Virtual source/sink only. Device adapters are deliberately unavailable in A0.
pub struct VirtualAudio {
    queue: VecDeque<AudioFrame>,
    capacity: usize,
    last_end: Option<u64>,
}
impl VirtualAudio {
    pub fn new(capacity: usize) -> Result<Self, AudioError> {
        if capacity == 0 || capacity > 100 {
            return Err(AudioError::InvalidFormat);
        }
        Ok(Self {
            queue: VecDeque::new(),
            capacity,
            last_end: None,
        })
    }
}
impl AudioSink for VirtualAudio {
    fn write(&mut self, frame: AudioFrame) -> Result<(), AudioError> {
        frame.validate()?;
        if self.last_end.is_some_and(|end| frame.timestamp_us < end) {
            return Err(AudioError::NonMonotonic);
        }
        if self.queue.len() == self.capacity {
            return Err(AudioError::Backpressure);
        }
        self.last_end = Some(frame.end_us());
        self.queue.push_back(frame);
        Ok(())
    }
}
impl AudioSource for VirtualAudio {
    fn next_frame(&mut self) -> Result<Option<AudioFrame>, AudioError> {
        Ok(self.queue.pop_front())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn frame(ts: u64) -> AudioFrame {
        AudioFrame {
            timestamp_us: ts,
            sample_rate: 16000,
            channels: 1,
            samples: vec![0.; 160],
        }
    }
    #[test]
    fn bounded_audio_rejects_without_consuming_timestamp() {
        let mut audio = VirtualAudio::new(1).unwrap();
        audio.write(frame(0)).unwrap();
        assert_eq!(audio.write(frame(10000)), Err(AudioError::Backpressure));
        audio.next_frame().unwrap();
        audio.write(frame(10000)).unwrap();
        audio.next_frame().unwrap();
        assert_eq!(audio.write(frame(0)), Err(AudioError::NonMonotonic));
        let mut bad = frame(20000);
        bad.samples[0] = f32::NAN;
        assert_eq!(audio.write(bad), Err(AudioError::InvalidFrame));
        audio.write(frame(20000)).unwrap();
        assert_eq!(frame(u64::MAX).validate(), Err(AudioError::InvalidFrame));
    }
}
