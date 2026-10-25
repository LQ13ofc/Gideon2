"""Synthetic wake measurement of one custom phrase (src/phrases.rs run_test). Offline: no devices, no network.

argv: RUNTIME_MANIFEST CLIPS_JSON. CLIPS_JSON lists raw 24 kHz s16le clips synthesized by the TTS worker,
each {"file", "positive", "text"}. Each clip runs through the same engine as the live worker: 3 s warm-up,
320-sample frames, 1 s of tail silence. Prints one JSON line on stdout:
{"positives", "hits", "negatives", "false_wakes", "latency_ms_median"}.
A hit is any detection of the candidate in a positive clip; any detection in a negative clip is a false wake.
These numbers are SYNTHETIC (TTS audio); they never certify a phrase for real speech.
"""
import json
from pathlib import Path
import statistics
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wake_worker import FRAME_SAMPLES, WakeEngine  # noqa: E402

MAX_CLIPS = 32
MAX_CLIP_BYTES = 16000 * 2 * 20  # 20 s of 16 kHz s16 is far above any synthetic phrase


def resample(raw):
    samples = np.frombuffer(raw, dtype='<i2').astype(np.float32) / np.float32(32768)
    # 24 kHz -> 16 kHz by linear interpolation; the same DEV-only approximation as pcm_fixture.
    return np.interp(np.arange(0, len(samples), 24000 / 16000), np.arange(len(samples)), samples).astype(np.float32)


def run(manifest_path, clips_path):
    manifest = json.loads(Path(manifest_path).read_text())
    clips = json.loads(Path(clips_path).read_text())['clips']
    if not 1 <= len(clips) <= MAX_CLIPS:
        raise ValueError('invalid clip count')
    engine = WakeEngine(manifest)
    target = set(engine.active_phrases)
    positives = negatives = hits = false_wakes = 0
    latencies = []
    for clip in clips:
        raw = Path(clip['file']).read_bytes()
        if len(raw) > MAX_CLIP_BYTES:
            raise ValueError('clip too large')
        samples = resample(raw)
        audio = np.concatenate([samples, np.zeros(16000, dtype=np.float32)])
        engine.reset()
        engine.warm_up()
        detections = []
        for offset in range(0, len(audio), FRAME_SAMPLES):
            frame = audio[offset:offset + FRAME_SAMPLES]
            detections += [d for d in engine.accept(frame, engine.last_end) if d['phrase_id'] in target]
        if clip['positive']:
            positives += 1
            if detections:
                hits += 1
                latencies.append(detections[0]['end_us'] // 1000)
        else:
            negatives += 1
            if detections:
                false_wakes += 1
    return {
        'positives': positives,
        'hits': hits,
        'negatives': negatives,
        'false_wakes': false_wakes,
        'latency_ms_median': int(statistics.median(latencies)) if latencies else None,
    }


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('usage: wake_phrase_test.py RUNTIME_MANIFEST CLIPS_JSON')
    print(json.dumps(run(sys.argv[1], sys.argv[2])), flush=True)
