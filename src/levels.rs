//! Input level meter for the live microphone (A9). Pure math over the raw s16le frames the recorder
//! delivers (20 ms, 320 samples): per-frame RMS and peak in dBFS, a 200 ms smoothed level, a noise
//! floor (10th percentile of the last 10 s), a speech decision (level above floor + 12 dB for at
//! least 120 ms) and the warnings the Core derives from them. Only numbers leave this module: no
//! sample, and no frame, is kept beyond the 10 s history.
use serde::Serialize;
use std::{
    collections::VecDeque,
    time::{Duration, Instant},
};

/// Silence floor of every dBFS value (digital silence reads as this).
pub const DBFS_MIN: f32 = -90.0;
/// Frames in the 200 ms smoothing window (20 ms each).
pub const SMOOTH_FRAMES: usize = 10;
/// Frames in the 10 s history used for the floor and the quiet warning.
pub const HISTORY_FRAMES: usize = 500;
/// The floor is not trusted before this many frames (1 s); until then it reads `DBFS_MIN`.
pub const FLOOR_MIN_FRAMES: usize = 50;
/// Speech starts when the smoothed level stays above `floor + SPEECH_MARGIN_DB` for `SPEECH_FRAMES`.
pub const SPEECH_MARGIN_DB: f32 = 12.0;
/// 120 ms of frames, both to start and to end a speech run.
pub const SPEECH_FRAMES: u32 = 6;
/// Speech without a recognised phrase for this long shows the "heard, not recognised" state.
pub const UNMATCHED_AFTER: Duration = Duration::from_secs(2);
/// A recorder that delivers nothing for this long while it is "capturing" is reported.
pub const NO_FRAMES_AFTER: Duration = Duration::from_secs(3);
/// Saturated samples inside the smoothing window that count as clipping.
pub const CLIP_SAMPLES: u32 = 3;
pub const VERY_QUIET_DBFS: f32 = -60.0;
pub const VERY_NOISY_DBFS: f32 = -35.0;

/// Per-frame measurement of one 20 ms frame.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct FrameStats {
    pub rms_dbfs: f32,
    pub peak_dbfs: f32,
    /// Samples at full scale (or below), used for the clipping flag.
    pub saturated: u32,
}

/// dBFS of a linear amplitude (1.0 = full scale), clamped to `DBFS_MIN..=0`.
pub fn to_dbfs(amplitude: f64) -> f32 {
    if !amplitude.is_finite() || amplitude <= 0.0 {
        return DBFS_MIN;
    }
    (20.0 * amplitude.log10()).clamp(f64::from(DBFS_MIN), 0.0) as f32
}

/// Measures one frame of raw s16le mono PCM. An odd trailing byte is ignored.
pub fn frame_stats(pcm: &[u8]) -> FrameStats {
    let mut power = 0f64;
    let mut peak = 0i32;
    let mut saturated = 0u32;
    let mut count = 0u32;
    for pair in pcm.chunks_exact(2) {
        let sample = i32::from(i16::from_le_bytes([pair[0], pair[1]]));
        count += 1;
        power += f64::from(sample * sample);
        peak = peak.max(sample.abs());
        if sample >= i32::from(i16::MAX) || sample <= i32::from(i16::MIN) {
            saturated += 1;
        }
    }
    if count == 0 {
        return FrameStats {
            rms_dbfs: DBFS_MIN,
            peak_dbfs: DBFS_MIN,
            saturated: 0,
        };
    }
    FrameStats {
        rms_dbfs: to_dbfs((power / f64::from(count)).sqrt() / 32768.0),
        peak_dbfs: to_dbfs(f64::from(peak) / 32768.0),
        saturated,
    }
}

/// Mean power of a set of frames expressed back in dBFS (energy average, not dB average).
fn energy_db(frames: impl Iterator<Item = f32>) -> f32 {
    let mut total = 0f64;
    let mut count = 0u32;
    for db in frames {
        total += 10f64.powf(f64::from(db) / 10.0);
        count += 1;
    }
    if count == 0 || total <= 0.0 {
        return DBFS_MIN;
    }
    (10.0 * (total / f64::from(count)).log10()).clamp(f64::from(DBFS_MIN), 0.0) as f32
}

/// Tenth percentile of frame RMS values (the noise floor). Empty input reads `DBFS_MIN`.
pub fn percentile_floor(values: &[f32]) -> f32 {
    if values.is_empty() {
        return DBFS_MIN;
    }
    let mut sorted = values.to_vec();
    sorted.sort_by(|a, b| a.total_cmp(b));
    sorted[(sorted.len() - 1) * 10 / 100]
}

/// One decimal place, as shown to the user and sent on the wire.
fn round1(value: f32) -> f32 {
    (value * 10.0).round() / 10.0
}

/// The numbers of the level block (`audio.live.level`). Everything is a number; no audio.
#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
pub struct Level {
    pub rms_dbfs: f32,
    pub peak_dbfs: f32,
    pub floor_dbfs: f32,
    pub speech_active: bool,
    pub speech_ms: u64,
    /// Speech has lasted `UNMATCHED_AFTER` and no wake phrase was recognised since it began.
    pub speech_unmatched: bool,
    pub frames: u64,
    pub last_frame_age_ms: Option<u64>,
    pub clipping: bool,
}

impl Level {
    pub fn silent() -> Self {
        Self {
            rms_dbfs: DBFS_MIN,
            peak_dbfs: DBFS_MIN,
            floor_dbfs: DBFS_MIN,
            speech_active: false,
            speech_ms: 0,
            speech_unmatched: false,
            frames: 0,
            last_frame_age_ms: None,
            clipping: false,
        }
    }
}

/// Streaming meter. Feed it every frame with its arrival time; read it with `level` or `warning`.
#[derive(Clone, Debug)]
pub struct Meter {
    frames: u64,
    history: VecDeque<FrameStats>,
    last_frame_at: Option<Instant>,
    /// When the current capture began (the no-frames timer starts here).
    started_at: Option<Instant>,
    above_run: u32,
    below_run: u32,
    speech_active: bool,
    speech_since: Option<Instant>,
    last_detection_at: Option<Instant>,
}

impl Default for Meter {
    fn default() -> Self {
        Self {
            frames: 0,
            history: VecDeque::with_capacity(HISTORY_FRAMES),
            last_frame_at: None,
            started_at: None,
            above_run: 0,
            below_run: 0,
            speech_active: false,
            speech_since: None,
            last_detection_at: None,
        }
    }
}

impl Meter {
    /// Starts a new capture: everything measured before is forgotten.
    pub fn reset(&mut self, now: Instant) {
        *self = Self {
            started_at: Some(now),
            ..Self::default()
        };
    }

    /// A wake phrase was recognised at `at`: it ends the "speech without recognition" state.
    pub fn note_detection(&mut self, at: Instant) {
        self.last_detection_at = Some(at);
    }

    pub fn push(&mut self, stats: FrameStats, at: Instant) {
        self.frames += 1;
        self.last_frame_at = Some(at);
        self.started_at.get_or_insert(at);
        if self.history.len() == HISTORY_FRAMES {
            self.history.pop_front();
        }
        self.history.push_back(stats);
        if self.frames < FLOOR_MIN_FRAMES as u64 {
            return;
        }
        // Runs are counted per 20 ms frame: smoothing first would stretch one burst over 200 ms.
        let floor = self.floor_db();
        if stats.rms_dbfs > floor + SPEECH_MARGIN_DB {
            self.above_run += 1;
            self.below_run = 0;
        } else {
            self.below_run += 1;
            self.above_run = 0;
        }
        if !self.speech_active && self.above_run >= SPEECH_FRAMES {
            self.speech_active = true;
            self.speech_since = Some(at);
        } else if self.speech_active && self.below_run >= SPEECH_FRAMES {
            self.speech_active = false;
            self.speech_since = None;
        }
    }

    /// RMS of the last `SMOOTH_FRAMES` frames (energy average).
    fn smoothed_db(&self) -> f32 {
        energy_db(
            self.history
                .iter()
                .rev()
                .take(SMOOTH_FRAMES)
                .map(|f| f.rms_dbfs),
        )
    }

    fn floor_db(&self) -> f32 {
        if self.history.len() < FLOOR_MIN_FRAMES {
            return DBFS_MIN;
        }
        let values: Vec<f32> = self.history.iter().map(|f| f.rms_dbfs).collect();
        percentile_floor(&values)
    }

    fn recent_peak_db(&self) -> f32 {
        self.history
            .iter()
            .rev()
            .take(SMOOTH_FRAMES)
            .map(|f| f.peak_dbfs)
            .fold(DBFS_MIN, f32::max)
    }

    /// Milliseconds since the last frame, read at `now` (None before the first frame).
    pub fn age_ms(&self, now: Instant) -> Option<u64> {
        self.last_frame_at
            .map(|at| millis(now.saturating_duration_since(at)))
    }

    /// The level block at `now`. `last_frame_age_ms` and the speech timers are read at `now`.
    pub fn level(&self, now: Instant) -> Level {
        let speech_ms = self
            .speech_since
            .filter(|_| self.speech_active)
            .map_or(0, |since| millis(now.saturating_duration_since(since)));
        let unmatched = self.speech_active
            && speech_ms >= millis(UNMATCHED_AFTER)
            && self
                .speech_since
                .is_some_and(|since| self.last_detection_at.is_none_or(|d| d < since));
        let clipping = self
            .history
            .iter()
            .rev()
            .take(SMOOTH_FRAMES)
            .map(|f| f.saturated)
            .sum::<u32>()
            >= CLIP_SAMPLES;
        Level {
            rms_dbfs: round1(self.smoothed_db()),
            peak_dbfs: round1(self.recent_peak_db()),
            floor_dbfs: round1(self.floor_db()),
            speech_active: self.speech_active,
            speech_ms,
            speech_unmatched: unmatched,
            frames: self.frames,
            last_frame_age_ms: self
                .last_frame_at
                .map(|at| millis(now.saturating_duration_since(at))),
            clipping,
        }
    }

    /// The warning for the live input, or `None`. `capturing` is true while the recorder runs; the
    /// no-frames check only applies then. Priority: no_frames, clipping, very_noisy, very_quiet.
    pub fn warning(&self, capturing: bool, now: Instant) -> Option<&'static str> {
        if !capturing {
            return None;
        }
        let last = self.last_frame_at.or(self.started_at);
        if last.is_some_and(|at| now.saturating_duration_since(at) >= NO_FRAMES_AFTER) {
            return Some("no_frames");
        }
        if self.level(now).clipping {
            return Some("clipping");
        }
        if self.history.len() >= FLOOR_MIN_FRAMES && self.floor_db() > VERY_NOISY_DBFS {
            return Some("very_noisy");
        }
        // Ten seconds of history, all below the quiet line.
        if self.history.len() == HISTORY_FRAMES
            && self.history.iter().all(|f| f.peak_dbfs < VERY_QUIET_DBFS)
        {
            return Some("very_quiet");
        }
        None
    }
}

fn millis(duration: Duration) -> u64 {
    u64::try_from(duration.as_millis()).unwrap_or(u64::MAX)
}

/// Result of one probe (`audio_probe`): 3 s of frames from one device, summarized.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Summary {
    pub frames: u64,
    pub rms_dbfs: f32,
    pub peak_dbfs: f32,
    pub floor_dbfs: f32,
}

pub fn summarize(frames: &[FrameStats]) -> Summary {
    let rms: Vec<f32> = frames.iter().map(|f| f.rms_dbfs).collect();
    Summary {
        frames: frames.len() as u64,
        rms_dbfs: round1(energy_db(rms.iter().copied())),
        peak_dbfs: round1(frames.iter().map(|f| f.peak_dbfs).fold(DBFS_MIN, f32::max)),
        floor_dbfs: round1(percentile_floor(&rms)),
    }
}

/// Verdicts of a probe. The wire strings are fixed.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Verdict {
    Ok,
    Quiet,
    Noisy,
    Silent,
    Error,
}

impl Verdict {
    pub fn as_str(self) -> &'static str {
        match self {
            Verdict::Ok => "ok",
            Verdict::Quiet => "quiet",
            Verdict::Noisy => "noisy",
            Verdict::Silent => "silent",
            Verdict::Error => "error",
        }
    }
}

/// Verdict and Portuguese hint of a finished probe. Silence beats noise, noise beats quietness.
pub fn judge(summary: &Summary) -> (Verdict, String) {
    if summary.frames == 0 || summary.peak_dbfs <= -80.0 {
        return (
            Verdict::Silent,
            "Nenhum áudio chegando do microfone. Confira se ele está conectado e sem mudo no sistema."
                .into(),
        );
    }
    if summary.floor_dbfs > VERY_NOISY_DBFS {
        return (
            Verdict::Noisy,
            format!(
                "Este microfone tem muito ruído de fundo ({:.0} dBFS). Teste outro dispositivo.",
                summary.floor_dbfs
            ),
        );
    }
    if summary.peak_dbfs < VERY_QUIET_DBFS {
        return (
            Verdict::Quiet,
            "Sinal muito baixo: aproxime-se ou aumente o ganho do microfone no sistema.".into(),
        );
    }
    (Verdict::Ok, "Microfone captando normalmente.".into())
}

/// Verdict of a probe that could not record: `reason` is the closed Core vocabulary of `live`.
pub fn failed(reason: &'static str) -> (Verdict, String) {
    let hint = match reason {
        "recorder_unavailable" => {
            "Gravador de áudio indisponível: instale pipewire-pulse (pw-record ou parecord)."
        }
        "sandbox_unavailable" => "Isolamento do gravador indisponível (bwrap ausente).",
        "invalid_device" => "Dispositivo inválido; escolha outro da lista.",
        _ => "O gravador parou antes de receber áudio. Tente de novo.",
    };
    (Verdict::Error, hint.into())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Synthetic frame of constant amplitude (fraction of full scale), 320 samples.
    /// Frame RMS equals the amplitude in dBFS for a constant-level frame, so 0.01 reads -40 dBFS.
    fn frame(amplitude: f64) -> FrameStats {
        let value = (amplitude * 32767.0).round() as i16;
        let mut pcm = Vec::with_capacity(640);
        for _ in 0..320 {
            pcm.extend_from_slice(&value.to_le_bytes());
        }
        frame_stats(&pcm)
    }

    fn at(ms: u64, base: Instant) -> Instant {
        base + Duration::from_millis(ms)
    }

    #[test]
    fn dbfs_math_matches_full_scale_and_silence() {
        assert_eq!(to_dbfs(1.0), 0.0);
        assert!((to_dbfs(0.1) + 20.0).abs() < 1e-4);
        assert_eq!(to_dbfs(0.0), DBFS_MIN);
        assert_eq!(to_dbfs(1e-9), DBFS_MIN);
        let silent = frame_stats(&[0u8; 640]);
        assert_eq!(
            (silent.rms_dbfs, silent.peak_dbfs, silent.saturated),
            (DBFS_MIN, DBFS_MIN, 0)
        );
        // A full-scale square wave: RMS and peak both at 0 dBFS, and every sample saturated.
        let mut pcm = Vec::new();
        for i in 0..320 {
            let v: i16 = if i % 2 == 0 { i16::MAX } else { i16::MIN };
            pcm.extend_from_slice(&v.to_le_bytes());
        }
        let full = frame_stats(&pcm);
        assert!(full.rms_dbfs > -0.01 && full.peak_dbfs.abs() < 0.01);
        assert_eq!(full.saturated, 320);
        // A sine at half amplitude: RMS about -9 dBFS, peak -6 dBFS.
        let half = frame(0.5);
        assert!((half.peak_dbfs + 6.02).abs() < 0.05);
    }

    #[test]
    fn floor_is_the_tenth_percentile_and_needs_one_second() {
        let values: Vec<f32> = (0..10).map(|i| -50.0 + i as f32).collect();
        assert_eq!(percentile_floor(&values), -50.0);
        assert_eq!(percentile_floor(&[]), DBFS_MIN);
        let base = Instant::now();
        let mut meter = Meter::default();
        meter.reset(base);
        for i in 0..(FLOOR_MIN_FRAMES as u64 - 1) {
            meter.push(frame(0.01), at(i * 20, base));
        }
        assert_eq!(
            meter.level(at(1000, base)).floor_dbfs,
            DBFS_MIN,
            "not trusted before 1 s"
        );
        meter.push(frame(0.01), at(1000, base));
        let level = meter.level(at(1000, base));
        assert!(
            (level.floor_dbfs + 40.0).abs() < 0.2,
            "quiet room at -40 dBFS: {level:?}"
        );
    }

    #[test]
    fn history_is_bounded_to_ten_seconds_so_the_floor_follows_the_room() {
        let base = Instant::now();
        let mut meter = Meter::default();
        meter.reset(base);
        for i in 0..HISTORY_FRAMES as u64 {
            meter.push(frame(0.05), at(i * 20, base));
        }
        let loud_room = meter.level(at(10_000, base)).floor_dbfs;
        for i in 0..HISTORY_FRAMES as u64 {
            meter.push(frame(0.001), at(10_000 + i * 20, base));
        }
        let quiet_room = meter.level(at(20_000, base)).floor_dbfs;
        assert!(
            loud_room > quiet_room + 20.0,
            "old frames left the window: {loud_room} {quiet_room}"
        );
        assert_eq!(meter.history.len(), HISTORY_FRAMES);
    }

    #[test]
    fn speech_needs_twelve_db_over_floor_for_120_ms_and_ends_the_same_way() {
        let base = Instant::now();
        let mut meter = Meter::default();
        meter.reset(base);
        let mut t = 0u64;
        // 2 s of room noise at -40 dBFS RMS (amplitude 0.01 gives about -43 dBFS: floor sits there).
        for _ in 0..100 {
            meter.push(frame(0.01), at(t, base));
            t += 20;
        }
        assert!(!meter.level(at(t, base)).speech_active);
        // Loud frames: the smoothed level crosses the margin after a few frames, and speech starts.
        let mut started_at = None;
        for _ in 0..20 {
            meter.push(frame(0.3), at(t, base));
            t += 20;
            if started_at.is_none() && meter.speech_active {
                started_at = Some(t);
            }
        }
        assert!(started_at.is_some(), "speech detected");
        assert!(meter.level(at(t, base)).speech_active);
        // Back to room noise: speech ends after 120 ms of quiet (the smoothing takes a few frames too).
        for _ in 0..40 {
            meter.push(frame(0.01), at(t, base));
            t += 20;
        }
        assert!(!meter.level(at(t, base)).speech_active);
    }

    #[test]
    fn a_single_loud_frame_is_not_speech() {
        let base = Instant::now();
        let mut meter = Meter::default();
        meter.reset(base);
        for i in 0..60u64 {
            meter.push(frame(0.01), at(i * 20, base));
        }
        meter.push(frame(0.9), at(1200, base));
        for i in 0..10u64 {
            meter.push(frame(0.01), at(1220 + i * 20, base));
        }
        assert!(!meter.speech_active, "one 20 ms burst never reaches 120 ms");
    }

    #[test]
    fn unmatched_speech_is_reported_after_two_seconds_without_detection() {
        let base = Instant::now();
        let mut meter = Meter::default();
        meter.reset(base);
        for i in 0..60u64 {
            meter.push(frame(0.01), at(i * 20, base));
        }
        // Speech of 2.5 s, no detection.
        for i in 0..125u64 {
            meter.push(frame(0.3), at(1200 + i * 20, base));
        }
        let level = meter.level(at(1200 + 125 * 20, base));
        assert!(level.speech_active && level.speech_unmatched, "{level:?}");
        // A detection inside the speech run clears it.
        meter.note_detection(at(2000, base));
        assert!(!meter.level(at(3700, base)).speech_unmatched);
    }

    #[test]
    fn no_frames_warning_needs_capture_and_three_seconds_of_silence() {
        let base = Instant::now();
        let mut meter = Meter::default();
        assert_eq!(
            meter.warning(false, at(10_000, base)),
            None,
            "not capturing: no warning"
        );
        meter.reset(base);
        assert_eq!(meter.warning(true, at(2_999, base)), None);
        assert_eq!(meter.warning(true, at(3_000, base)), Some("no_frames"));
        meter.push(frame(0.01), at(3_000, base));
        assert_eq!(meter.warning(true, at(3_500, base)), None);
        assert_eq!(meter.warning(true, at(6_000, base)), Some("no_frames"));
    }

    #[test]
    fn very_noisy_and_very_quiet_follow_the_floor_and_peak_lines() {
        let base = Instant::now();
        let mut noisy = Meter::default();
        noisy.reset(base);
        // Webcam at about -23 dBFS RMS of ambient noise.
        for i in 0..100u64 {
            noisy.push(frame(0.07), at(i * 20, base));
        }
        assert_eq!(noisy.warning(true, at(2000, base)), Some("very_noisy"));

        let mut quiet = Meter::default();
        quiet.reset(base);
        assert_eq!(
            quiet.warning(true, at(10, base)),
            None,
            "no warning before 10 s of history"
        );
        for i in 0..HISTORY_FRAMES as u64 {
            quiet.push(frame(0.0003), at(i * 20, base));
        }
        assert_eq!(quiet.warning(true, at(10_000, base)), Some("very_quiet"));
        // One loud frame in the window clears the quiet state.
        quiet.push(frame(0.2), at(10_000, base));
        assert_eq!(quiet.warning(true, at(10_000, base)), None);
    }

    #[test]
    fn clipping_is_flagged_from_saturated_samples_in_the_window() {
        let base = Instant::now();
        let mut meter = Meter::default();
        meter.reset(base);
        meter.push(frame(0.01), at(0, base));
        assert!(!meter.level(at(0, base)).clipping);
        let mut hot = Vec::new();
        for _ in 0..320 {
            hot.extend_from_slice(&i16::MAX.to_le_bytes());
        }
        meter.push(frame_stats(&hot), at(20, base));
        assert!(meter.level(at(20, base)).clipping);
        assert_eq!(meter.warning(true, at(20, base)), Some("clipping"));
    }

    #[test]
    fn level_block_numbers_are_rounded_and_bounded() {
        let base = Instant::now();
        let mut meter = Meter::default();
        meter.reset(base);
        meter.push(frame(0.1), at(0, base));
        let level = meter.level(at(45, base));
        assert_eq!(level.last_frame_age_ms, Some(45));
        assert_eq!(level.frames, 1);
        assert!((-90.0..=0.0).contains(&level.rms_dbfs));
        assert_eq!(level.rms_dbfs, (level.rms_dbfs * 10.0).round() / 10.0);
        assert_eq!(Level::silent().last_frame_age_ms, None);
    }

    #[test]
    fn probe_summary_and_verdicts_cover_every_branch() {
        let base_frames = |amp: f64| vec![frame(amp); 150];
        let ok = summarize(&base_frames(0.01));
        assert_eq!(judge(&ok).0, Verdict::Ok);
        // The webcam case from the field: about -23 dBFS floor.
        let noisy = summarize(&base_frames(0.07));
        let (verdict, hint) = judge(&noisy);
        assert_eq!(verdict, Verdict::Noisy);
        assert_eq!(
            hint,
            "Este microfone tem muito ruído de fundo (-23 dBFS). Teste outro dispositivo."
        );
        // Quiet: peak below -60 dBFS but not digital silence.
        let quiet = summarize(&base_frames(0.0005));
        assert_eq!(judge(&quiet).0, Verdict::Quiet);
        // Silent: no frames, or digital zero.
        assert_eq!(judge(&summarize(&[])).0, Verdict::Silent);
        assert_eq!(judge(&summarize(&base_frames(0.0))).0, Verdict::Silent);
        assert_eq!(failed("sandbox_unavailable").0.as_str(), "error");
        assert!(failed("recorder_exited").1.contains("parou"));
    }
}
