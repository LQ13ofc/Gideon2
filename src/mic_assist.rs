//! Microphone assistant (A13). `audio_recommend_input` records 2 s from every listed input, one at a
//! time, with the same sandboxed recorder as the live input and the probe (`live::record_in`), and scores
//! each recording on the numbers it can measure: clipping, rumble (energy below 100 Hz), speech-band energy
//! (300 to 3400 Hz), peak headroom and the noise floor. Only numbers and reason ids leave this module; no
//! audio is kept. The spectrum is a Welch estimate with a small radix-2 FFT written here (no new crates).
//!
//! Camera sources (name contains webcam or camera) are probed and labelled but never recommended. The
//! recommendation never changes the system default: it is a preference Gideon offers and the user accepts.
use crate::{
    devices::{self, Devices},
    levels::{self, FrameStats, Summary},
};
use serde::Serialize;
use std::{f64::consts::PI, time::Duration};

/// Recording length of one candidate.
pub const RECORD_DURATION: Duration = Duration::from_secs(2);
/// Samples at full scale (within 1 % of it) that count as clipping.
const NEAR_FULL_SCALE: i32 = 32440;
/// Clipped samples in one recording that count as clipping (about 0.01 % of 2 s at 16 kHz).
const CLIP_COUNT: u32 = 3;
/// Rumble share of the energy (below 100 Hz) from which the device is rumbling. Set to 0.75 after the first real run:
/// the owner's fifine measured 0.34 to 0.50 (a clean device) and the webcam 0.88 to 0.98; 0.5 excluded the fifine.
const RUMBLE_SHARE: f32 = 0.75;
/// Welch segment length (7.8 Hz bins at 16 kHz) and hop.
const SEGMENT: usize = 2048;
const HOP: usize = 1024;
const RATE: f64 = 16_000.0;
/// Frame length of the level statistics (20 ms).
const FRAME: usize = 320;

/// Numbers of one recording. Fractions are of the total energy above DC.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Measure {
    pub summary: Summary,
    pub clipped: u32,
    pub clip_fraction: f32,
    pub rumble: f32,
    pub speech: f32,
}

fn frame_of(chunk: &[i16]) -> FrameStats {
    let mut power = 0f64;
    let mut peak = 0i32;
    for sample in chunk {
        let value = i32::from(*sample);
        power += f64::from(value * value);
        peak = peak.max(value.abs());
    }
    let count = chunk.len().max(1) as f64;
    FrameStats {
        rms_dbfs: levels::to_dbfs((power / count).sqrt() / 32768.0),
        peak_dbfs: levels::to_dbfs(f64::from(peak) / 32768.0),
        saturated: 0,
    }
}

/// In-place iterative radix-2 FFT. `re.len()` must be a power of two and equal `im.len()`.
fn fft(re: &mut [f64], im: &mut [f64]) {
    let n = re.len();
    let mut j = 0usize;
    for i in 1..n {
        let mut bit = n >> 1;
        while j & bit != 0 {
            j ^= bit;
            bit >>= 1;
        }
        j |= bit;
        if i < j {
            re.swap(i, j);
            im.swap(i, j);
        }
    }
    let mut len = 2;
    while len <= n {
        let angle = -2.0 * PI / len as f64;
        let (wr, wi) = (angle.cos(), angle.sin());
        for start in (0..n).step_by(len) {
            let (mut cr, mut ci) = (1.0f64, 0.0f64);
            for k in 0..len / 2 {
                let a = start + k;
                let b = a + len / 2;
                let tr = re[b] * cr - im[b] * ci;
                let ti = re[b] * ci + im[b] * cr;
                re[b] = re[a] - tr;
                im[b] = im[a] - ti;
                re[a] += tr;
                im[a] += ti;
                let next = cr * wr - ci * wi;
                ci = cr * wi + ci * wr;
                cr = next;
            }
        }
        len <<= 1;
    }
}

/// Shares of the energy below 100 Hz (rumble) and between 300 and 3400 Hz (speech), Welch estimate.
/// Returns `(0, 0)` when the recording is shorter than one segment or has no energy.
pub fn band_shares(samples: &[i16]) -> (f32, f32) {
    if samples.len() < SEGMENT {
        return (0.0, 0.0);
    }
    let window: Vec<f64> = (0..SEGMENT)
        .map(|i| 0.5 - 0.5 * (2.0 * PI * i as f64 / (SEGMENT - 1) as f64).cos())
        .collect();
    let half = SEGMENT / 2;
    let mut power = vec![0f64; half + 1];
    let mut start = 0usize;
    while start + SEGMENT <= samples.len() {
        let segment = &samples[start..start + SEGMENT];
        let mean = segment.iter().map(|s| f64::from(*s)).sum::<f64>() / SEGMENT as f64;
        let mut re: Vec<f64> = segment
            .iter()
            .zip(&window)
            .map(|(s, w)| (f64::from(*s) - mean) * w)
            .collect();
        let mut im = vec![0f64; SEGMENT];
        fft(&mut re, &mut im);
        for (k, p) in power.iter_mut().enumerate() {
            *p += re[k] * re[k] + im[k] * im[k];
        }
        start += HOP;
    }
    let bin_hz = RATE / SEGMENT as f64;
    let total: f64 = power[1..].iter().sum();
    if total <= 0.0 {
        return (0.0, 0.0);
    }
    let mut rumble = 0f64;
    let mut speech = 0f64;
    for (k, p) in power.iter().enumerate().skip(1) {
        let hz = k as f64 * bin_hz;
        if hz < 100.0 {
            rumble += p;
        }
        if (300.0..=3400.0).contains(&hz) {
            speech += p;
        }
    }
    ((rumble / total) as f32, (speech / total) as f32)
}

/// Measures one recording of 16 kHz mono s16 samples.
pub fn measure(samples: &[i16]) -> Measure {
    let frames: Vec<FrameStats> = samples.chunks(FRAME).map(frame_of).collect();
    let clipped = samples
        .iter()
        .filter(|s| i32::from(**s).abs() >= NEAR_FULL_SCALE)
        .count() as u32;
    let (rumble, speech) = band_shares(samples);
    Measure {
        summary: levels::summarize(&frames),
        clipped,
        clip_fraction: if samples.is_empty() {
            0.0
        } else {
            clipped as f32 / samples.len() as f32
        },
        rumble,
        speech,
    }
}

/// Problems of one recording, in priority order. Empty means the device is usable.
pub fn problems(m: &Measure) -> Vec<&'static str> {
    let mut out = Vec::new();
    if m.clipped >= CLIP_COUNT {
        out.push("clipping");
    }
    if m.rumble >= RUMBLE_SHARE {
        out.push("rumble");
    }
    if m.summary.floor_dbfs > levels::VERY_NOISY_DBFS {
        out.push("too_noisy");
    }
    if m.summary.peak_dbfs < levels::VERY_QUIET_DBFS {
        out.push("too_quiet");
    }
    out
}

/// Score in 0..=1 (higher is better): speech share, times the share of energy that is not rumble, times
/// the peak headroom (full credit from -6 dBFS down), times a clipping penalty. Problems do not zero the
/// score by themselves; the recommendation only excludes devices that have a problem.
pub fn score(m: &Measure) -> f32 {
    let headroom = (-m.summary.peak_dbfs / 6.0).clamp(0.0, 1.0);
    let clip = 1.0 - (m.clip_fraction * 100.0).min(1.0);
    (m.speech * (1.0 - m.rumble) * headroom * clip).clamp(0.0, 1.0)
}

/// A source whose name says it is a camera: probed and labelled, never recommended.
pub fn is_camera(id: &str, label: &str) -> bool {
    let text = format!("{id} {label}").to_lowercase();
    text.contains("webcam") || text.contains("camera")
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Entry {
    pub id: String,
    pub label: String,
    pub camera: bool,
    /// The device the current preference resolves to.
    pub current: bool,
    /// `best` or the first problem; absent when the device could not be recorded.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<&'static str>,
    pub problems: Vec<&'static str>,
    pub score: f32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rms_dbfs: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub peak_dbfs: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub floor_dbfs: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub clip: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rumble: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub speech: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<&'static str>,
}

/// Snapshot block `audio.recommendation`. `state` is `idle` until the first run, then `running`, `done` or
/// `failed` (with `error`). `current_is_bad` and `reason` describe the current preference.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct View {
    pub state: &'static str,
    pub ranked: Vec<Entry>,
    pub recommended: Option<String>,
    pub current: Option<String>,
    pub current_is_bad: Option<bool>,
    pub reason: Option<&'static str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<&'static str>,
}

impl Default for View {
    fn default() -> Self {
        Self {
            state: "idle",
            ranked: Vec::new(),
            recommended: None,
            current: None,
            current_is_bad: None,
            reason: None,
            error: None,
        }
    }
}

impl View {
    pub fn running() -> Self {
        Self {
            state: "running",
            ..Self::default()
        }
    }
    pub fn failed(error: &'static str) -> Self {
        Self {
            state: "failed",
            error: Some(error),
            ..Self::default()
        }
    }
}

/// Result of one run: the new view and the device list it enumerated (the Core keeps both).
pub struct Done {
    pub devices: Devices,
    pub view: View,
}

fn entry(id: &str, label: &str, current: bool, recorded: Result<Vec<i16>, &'static str>) -> Entry {
    let camera = is_camera(id, label);
    match recorded {
        Ok(samples) => {
            let m = measure(&samples);
            let problems = problems(&m);
            Entry {
                id: id.to_string(),
                label: label.to_string(),
                camera,
                current,
                reason: Some(problems.first().copied().unwrap_or("best")),
                problems,
                score: (score(&m) * 1000.0).round() / 1000.0,
                rms_dbfs: Some(m.summary.rms_dbfs),
                peak_dbfs: Some(m.summary.peak_dbfs),
                floor_dbfs: Some(m.summary.floor_dbfs),
                clip: Some((m.clip_fraction * 100_000.0).round() / 100_000.0),
                rumble: Some((m.rumble * 1000.0).round() / 1000.0),
                speech: Some((m.speech * 1000.0).round() / 1000.0),
                error: None,
            }
        }
        Err(error) => Entry {
            id: id.to_string(),
            label: label.to_string(),
            camera,
            current,
            reason: None,
            problems: Vec::new(),
            score: 0.0,
            rms_dbfs: None,
            peak_dbfs: None,
            floor_dbfs: None,
            clip: None,
            rumble: None,
            speech: None,
            error: Some(error),
        },
    }
}

/// Builds the ranked view from the per-device results. `resolved` is the device id the saved preference points at
/// (`default` is resolved to the device the system marks). Pure: the tests drive it with synthetic samples.
pub fn rank(resolved: &str, mut entries: Vec<Entry>) -> View {
    // Failed entries last, then by score (ties keep the enumeration order).
    entries.sort_by(|a, b| {
        a.error
            .is_some()
            .cmp(&b.error.is_some())
            .then(b.score.total_cmp(&a.score))
    });
    let recommended = entries
        .iter()
        .find(|e| e.error.is_none() && e.problems.is_empty() && !e.camera && e.id != "default")
        .map(|e| e.id.clone());
    let own = entries.iter().find(|e| e.current);
    let (current_is_bad, reason) = match own {
        Some(e) if e.error.is_none() => (
            Some(!e.problems.is_empty()),
            Some(e.reason.unwrap_or("best")),
        ),
        _ => (None, None),
    };
    View {
        state: "done",
        ranked: entries,
        recommended,
        current: Some(resolved.to_string()),
        current_is_bad,
        reason,
        error: None,
    }
}

/// Resolves the preference to the device id whose recording judges it. `default` means the device the
/// system marks as default; when none is marked, the pseudo entry `default` stands for it.
fn current_id(current: &str, devices: &Devices) -> String {
    if current == "default" {
        devices
            .inputs
            .iter()
            .find(|d| d.default)
            .map(|d| d.id.clone())
            .unwrap_or_else(|| "default".to_string())
    } else {
        current.to_string()
    }
}

/// Runs the assistant for the given preference: enumerate, record every input for 2 s (sequentially),
/// rank. Refusals (busy) are the Core's job; this only records. The `default` pseudo entry is probed only
/// when the system marks no input as default.
pub async fn run(current: String) -> Done {
    let devices = match tokio::task::spawn_blocking(devices::enumerate).await {
        Ok(devices) => devices,
        Err(_) => Devices {
            inputs: Vec::new(),
            outputs: Vec::new(),
            source: "none",
            reason: Some("audio_tool_failed"),
        },
    };
    if devices.source == "none" {
        let error = devices.reason.unwrap_or("audio_tool_failed");
        return Done {
            devices,
            view: View::failed(error),
        };
    }
    let mut candidates: Vec<(String, String)> = devices
        .inputs
        .iter()
        .map(|d| (d.id.clone(), d.label.clone()))
        .collect();
    let resolved = current_id(&current, &devices);
    if current == "default" && !devices.inputs.iter().any(|d| d.default) {
        candidates.push(("default".into(), "Padrão do sistema".into()));
    }
    let path = std::env::var_os("PATH").unwrap_or_default();
    let mut entries = Vec::with_capacity(candidates.len());
    for (id, label) in &candidates {
        let recorded = crate::live::record_in(&path, id, RECORD_DURATION).await;
        let is_current = *id == resolved;
        entries.push(entry(id, label, is_current, recorded));
    }
    // The view names the device the preference resolves to (the id the banner compares with), not the word `default`.
    Done {
        devices,
        view: rank(&resolved, entries),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tone(hz: f64, amplitude: f64, seconds: f64) -> Vec<i16> {
        let n = (RATE * seconds) as usize;
        (0..n)
            .map(|i| {
                let t = i as f64 / RATE;
                (amplitude * (2.0 * PI * hz * t).sin() * 32767.0) as i16
            })
            .collect()
    }

    /// Deterministic white-ish noise (LCG), scaled to `amplitude` of full scale.
    fn noise(amplitude: f64, seconds: f64) -> Vec<i16> {
        let mut state = 0x2545_f491_4f6c_dd1du64;
        (0..(RATE * seconds) as usize)
            .map(|_| {
                state = state
                    .wrapping_mul(6_364_136_223_846_793_005)
                    .wrapping_add(1_442_695_040_888_963_407);
                let unit = (state >> 11) as f64 / (1u64 << 53) as f64 * 2.0 - 1.0;
                (unit * amplitude * 32767.0) as i16
            })
            .collect()
    }

    /// Low-frequency rumble (12.6 Hz, the webcam case) with a small speech-band component, saturating.
    fn rumble_clip(seconds: f64) -> Vec<i16> {
        let n = (RATE * seconds) as usize;
        (0..n)
            .map(|i| {
                let t = i as f64 / RATE;
                let v = 1.6 * (2.0 * PI * 12.6 * t).sin() + 0.02 * (2.0 * PI * 1000.0 * t).sin();
                (v.clamp(-1.0, 1.0) * 32767.0) as i16
            })
            .collect()
    }

    #[test]
    fn fft_matches_a_direct_dft_on_a_short_signal() {
        let input: Vec<f64> = (0..8).map(|i| ((i * 3) % 5) as f64 - 2.0).collect();
        let mut re = input.clone();
        let mut im = vec![0.0; 8];
        fft(&mut re, &mut im);
        for k in 0..8 {
            let (mut sr, mut si) = (0.0, 0.0);
            for (n, x) in input.iter().enumerate() {
                let a = -2.0 * PI * (k * n) as f64 / 8.0;
                sr += x * a.cos();
                si += x * a.sin();
            }
            assert!(
                (re[k] - sr).abs() < 1e-9 && (im[k] - si).abs() < 1e-9,
                "bin {k}"
            );
        }
    }

    #[test]
    fn rumble_is_measured_below_100_hz_and_speech_band_above_300() {
        let (rumble, speech) = band_shares(&tone(12.6, 0.5, 2.0));
        assert!(
            rumble > 0.9 && speech < 0.05,
            "rumble {rumble} speech {speech}"
        );
        let (rumble, speech) = band_shares(&tone(1000.0, 0.5, 2.0));
        assert!(
            rumble < 0.01 && speech > 0.9,
            "rumble {rumble} speech {speech}"
        );
        assert_eq!(band_shares(&[0; 4096]), (0.0, 0.0));
        assert_eq!(band_shares(&[1; 100]), (0.0, 0.0));
    }

    #[test]
    fn webcam_like_recording_has_rumble_and_clipping_and_scores_zero() {
        let m = measure(&rumble_clip(2.0));
        assert!(m.clipped >= CLIP_COUNT);
        assert!(m.rumble > 0.5);
        // Saturated rumble is also loud: the noise floor check flags it too.
        let found = problems(&m);
        assert_eq!(&found[..2], &["clipping", "rumble"]);
        assert_eq!(score(&m), 0.0);
    }

    #[test]
    fn clean_ambient_noise_is_usable_and_scores_above_a_webcam() {
        let clean = measure(&noise(0.02, 2.0));
        assert!(problems(&clean).is_empty(), "{:?}", problems(&clean));
        let webcam = measure(&rumble_clip(2.0));
        assert!(score(&clean) > score(&webcam));
    }

    #[test]
    fn quiet_and_noisy_recordings_get_their_reason_ids() {
        assert_eq!(problems(&measure(&noise(0.0005, 2.0))), vec!["too_quiet"]);
        assert_eq!(problems(&measure(&noise(0.5, 2.0))), vec!["too_noisy"]);
    }

    #[test]
    fn camera_names_are_detected_in_id_or_label() {
        assert!(is_camera(
            "alsa_input.usb-ASD_650_Camera_Full_HD_webcam-02",
            "x"
        ));
        assert!(is_camera("alsa_input.usb-fifine", "Webcam mic"));
        assert!(!is_camera("alsa_input.usb-MV-SILICON_fifine", "Fifine"));
    }

    fn fake(
        id: &str,
        label: &str,
        current: bool,
        problems: Vec<&'static str>,
        score: f32,
    ) -> Entry {
        Entry {
            reason: Some(problems.first().copied().unwrap_or("best")),
            camera: is_camera(id, label),
            current,
            problems,
            score,
            error: None,
            ..entry(id, label, current, Err("recorder_exited"))
        }
    }

    #[test]
    fn rank_recommends_the_best_clean_non_camera_device_and_reports_the_current_one() {
        let view = rank(
            "default",
            vec![
                fake("cam", "Webcam", true, vec!["clipping", "rumble"], 0.0),
                fake("fifine", "Fifine", false, vec![], 0.4),
                fake("internal", "Internal", false, vec![], 0.2),
            ],
        );
        assert_eq!(view.state, "done");
        assert_eq!(view.recommended.as_deref(), Some("fifine"));
        assert_eq!(view.current_is_bad, Some(true));
        assert_eq!(view.reason, Some("clipping"));
        assert_eq!(view.ranked[0].id, "fifine");
        assert_eq!(view.ranked.last().unwrap().id, "cam");
    }

    #[test]
    fn a_camera_or_a_problem_is_never_recommended() {
        let view = rank(
            "default",
            vec![
                fake("webcam", "Webcam", false, vec![], 0.9),
                fake("fifine", "Fifine", true, vec!["too_noisy"], 0.3),
            ],
        );
        assert_eq!(view.recommended, None);
        assert_eq!(view.current_is_bad, Some(true));
        assert_eq!(view.reason, Some("too_noisy"));
    }

    #[test]
    fn a_good_current_device_reports_best() {
        let view = rank("fifine", vec![fake("fifine", "Fifine", true, vec![], 0.4)]);
        assert_eq!(view.current_is_bad, Some(false));
        assert_eq!(view.reason, Some("best"));
        assert_eq!(view.recommended.as_deref(), Some("fifine"));
    }

    #[test]
    fn the_view_names_the_resolved_device_so_the_banner_can_match_it() {
        let view = rank(
            "alsa_input.webcam",
            vec![fake(
                "alsa_input.webcam",
                "Webcam",
                true,
                vec!["rumble"],
                0.0,
            )],
        );
        assert_eq!(view.current.as_deref(), Some("alsa_input.webcam"));
        assert_eq!(view.current_is_bad, Some(true));
    }

    #[test]
    fn default_pseudo_entry_is_never_recommended() {
        let view = rank(
            "default",
            vec![fake("default", "Padrão do sistema", true, vec![], 0.5)],
        );
        assert_eq!(view.recommended, None);
    }

    #[test]
    fn current_id_resolves_default_to_the_marked_input() {
        let devices = Devices {
            inputs: vec![
                devices::Device {
                    id: "a".into(),
                    label: "A".into(),
                    default: false,
                },
                devices::Device {
                    id: "b".into(),
                    label: "B".into(),
                    default: true,
                },
            ],
            outputs: Vec::new(),
            source: "pactl",
            reason: None,
        };
        assert_eq!(current_id("default", &devices), "b");
        assert_eq!(current_id("a", &devices), "a");
    }
}
