#!/usr/bin/env python3
"""Offline regression of the PT/FR transcript wake (WP-7c) on the pinned WP-7 clips and the A9 real noise.

Runs scripts/wake_transcript.py `TranscriptEngine` (the production engine, same frame contract as
scripts/wake_worker.py `live()`) on continuous 16 kHz streams. No Core, no audio devices, no network.

Conditions:
- clean: the 14 positive ("Gideon") and 18 negative lab clips, one stream: 1.0 s lead, each clip, 1.5 s tail, 0.8 s gap.
- mix: the same clips over real microphone noise (A9 beds, 90 s per microphone, `{mic}-16k-mono-s16.raw`),
  SNR 5, 10 and 20 dB (speech RMS over its non-silent samples, as docs/A9). A random offset per clip (seeded).
- noise: pure real noise (A9 long recordings, `long-{mic}-16k-mono-s16.raw`), `--noise-seconds` per microphone.

A detection inside a positive clip window (clip + tail) is a hit (one per clip). A detection in a negative clip
window, in a gap, or in pure noise is a false trigger. The 2 s cooldown of src/wake.rs is applied.

Floor (documented, WP-7c): hits >= 0.80 of the 14 clean positives AND 0 false triggers in every condition.
The mix hit rate is reported; the floor applies to the clean hits and to the false triggers of all conditions.

Sets: `lab` (the WP-7 sentences, used to choose parameters) and `heldout` (sentences written later, never used to
choose parameters; scripts/measure_pt_fr.py `heldout`). Each set has its own pins file in docs/evidence.

Usage:
  wake_pt_fr_regression.py pins {lab,heldout}
  wake_pt_fr_regression.py check {lab,heldout} [--floor 0.80] [--snr 5,10,20] [--mics fifine,webcam,onboard]
                                 [--noise-seconds 180] [--noise-dir DIR] [--skip-mix] [--skip-noise]
Exit: 0 floor met and no false trigger; 1 floor not met or false trigger; 2 pinned clips or assets missing/changed.
"""
import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))
import wake_transcript as wt  # noqa: E402

SETS = {
    # lab: the WP-7 sentences (scripts/wp7_sentences.json rendered to target/wp7-lab-clips). Used to pick parameters.
    'lab': (BASE / 'target/wp7-lab-clips', BASE / 'docs/evidence/wake-pt-fr-pins.json'),
    # heldout: scripts/measure_pt_fr.py HELDOUT_SENTENCES (target/wp7c-heldout). Never used to pick parameters.
    'heldout': (BASE / 'target/wp7c-heldout', BASE / 'docs/evidence/wake-pt-fr-heldout-pins.json'),
}
STT_MANIFEST = BASE / 'target/stt-pt-fr-assets/manifest.json'
VAD_MANIFEST = BASE / 'target/a2-assets/manifest.json'
DEFAULT_NOISE_DIR = Path('/tmp/gideon-wake-lab/real-noise')
MICS = ('fifine', 'webcam', 'onboard')
RATE = 16000
FRAME = 320
LEAD_S = 1.0
TAIL_S = 1.5
GAP_S = 0.8
COOLDOWN_US = 2_000_000
ORDER_SEED = 20261025
MIX_SEED = 20261026
FLOOR = 0.80
BED_S = 90


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clip_list(root):
    """The pinned clips of one set, sorted: (lang, label, path). label 1 = positive (contains the name)."""
    rows = []
    for lang in ('pt', 'fr'):
        for label, folder in ((1, 'positive'), (0, 'negative')):
            for path in sorted((root / lang / folder).glob('*.wav')):
                rows.append((lang, label, path))
    return rows


def read_clip(path):
    import wave
    with wave.open(str(path), 'rb') as w:
        rate, channels = w.getframerate(), w.getnchannels()
        raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    if rate != RATE:
        x = np.interp(np.arange(0, len(x), rate / RATE), np.arange(len(x)), x).astype(np.float32)
    return x.astype(np.float32)


def read_raw(path, seconds=None):
    count = -1 if seconds is None else int(seconds * RATE)
    return np.fromfile(path, dtype='<i2', count=count).astype(np.float32) / 32768.0


def rms(x):
    active = x[np.abs(x) > 1e-4]
    return float(np.sqrt(np.mean(active ** 2))) if active.size else 0.0


def manifest():
    stt = json.loads(STT_MANIFEST.read_text())
    vad = json.loads(VAD_MANIFEST.read_text())
    return {
        'engine': wt.ENGINE,
        'supported_phrases': {'wake_name': 'WAKE_NAME'},
        'active_phrase': 'wake_name',
        'model_root': stt['model_root'],
        'encoder': stt['encoder'], 'decoder': stt['decoder'], 'joiner': stt['joiner'], 'tokens': stt['tokens'],
        'hashes': stt['hashes'],
        'vad': {'engine': vad['engine'], 'path': vad['path'], 'sha256': vad['sha256']},
    }


class Harness:
    def __init__(self):
        from wake_transcript import TranscriptEngine
        self.engine_cls = TranscriptEngine
        self.manifest = manifest()
        self.recognizer = TranscriptEngine._recognizer(self.manifest)

    def run(self, samples):
        """Streams samples as 20 ms frames through a fresh engine (fresh VAD), returns detection end times (us)."""
        engine = self.engine_cls(self.manifest, recognizer=self.recognizer)
        events = []
        last_wake = None
        usable = len(samples) - len(samples) % FRAME
        for offset in range(0, usable, FRAME):
            timestamp = engine.last_end
            for event in engine.accept(samples[offset:offset + FRAME], timestamp):
                end = event['end_us']
                if last_wake is None or end - last_wake >= COOLDOWN_US:
                    events.append(end)
                    last_wake = end
        return events, engine


def us(samples_count):
    return samples_count * 1_000_000 // RATE


def score_stream(harness, stream, windows):
    """windows: list of (start_us, end_us, label) where label 1 = positive clip window, 0 = negative, None = gap."""
    events, engine = harness.run(stream)
    hits = {}
    false = []
    for end in events:
        inside = [w for w in windows if w[0] <= end < w[1]]
        if not inside:
            false.append(end)
            continue
        start, stop, label, index = inside[0]
        if label == 1:
            hits.setdefault(index, end)
        else:
            false.append(end)
    return hits, false, engine


def clean_stream(clips, order):
    parts = [np.zeros(int(LEAD_S * RATE), np.float32)]
    windows = []
    cursor = int(LEAD_S * RATE)
    for index in order:
        lang, label, x = clips[index]
        start = cursor
        parts.append(x)
        cursor += len(x)
        tail = np.zeros(int(TAIL_S * RATE), np.float32)
        parts.append(tail)
        cursor += len(tail)
        windows.append((us(start), us(cursor), label, index))
        gap = np.zeros(int(GAP_S * RATE), np.float32)
        parts.append(gap)
        cursor += len(gap)
    return np.concatenate(parts), windows


def mix_stream(clips, order, bed, snr_db, rng):
    """Each clip scaled to snr_db above the bed RMS and laid over a random bed slice (lead, tail and gap are bed)."""
    bed_rms = rms(bed)
    parts = []
    windows = []
    cursor = 0
    for index in order:
        lang, label, x = clips[index]
        span = len(x) + int((LEAD_S + TAIL_S + GAP_S) * RATE)
        offset = rng.randrange(0, len(bed) - span)
        chunk = bed[offset:offset + span].copy()
        gain = bed_rms * 10 ** (snr_db / 20) / max(rms(x), 1e-6)
        at = int(LEAD_S * RATE)
        chunk[at:at + len(x)] += x * gain
        parts.append(chunk)
        windows.append((us(cursor + at), us(cursor + at + len(x) + int(TAIL_S * RATE)), label, index))
        cursor += span
    # Full scale is +-1.0 (the live path is s16): a mix that exceeds it clips, as a real microphone would.
    return np.clip(np.concatenate(parts), -1.0, 1.0).astype(np.float32), windows


def cmd_pins(args):
    root, pins_path = SETS[args.set]
    clips = clip_list(root)
    if not clips:
        print('no clips under', root, file=sys.stderr)
        return 2
    pins = {'set': args.set,
            'clips': [{'lang': lang, 'label': label, 'file': str(path.relative_to(root)), 'sha256': sha256_file(path)}
                      for lang, label, path in clips],
            'positives': sum(1 for c in clips if c[1] == 1), 'negatives': sum(1 for c in clips if c[1] == 0),
            'stt_manifest_sha256': sha256_file(STT_MANIFEST), 'vad_manifest_sha256': sha256_file(VAD_MANIFEST)}
    pins_path.write_text(json.dumps(pins, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'set': args.set, 'positives': pins['positives'], 'negatives': pins['negatives'], 'out': str(pins_path)}))
    return 0


def verify_pins(root, pins_path, clips):
    if not pins_path.exists():
        print('missing pins file', pins_path, file=sys.stderr)
        return False
    pins = json.loads(pins_path.read_text())
    expected = {entry['file']: entry['sha256'] for entry in pins['clips']}
    for lang, label, path in clips:
        key = str(path.relative_to(root))
        if expected.get(key) != sha256_file(path):
            print('clip changed or unpinned:', key, file=sys.stderr)
            return False
    return len(expected) == len(clips)


def cmd_check(args):
    root, pins_path = SETS[args.set]
    clips_list = clip_list(root)
    if not verify_pins(root, pins_path, clips_list):
        return 2
    clips = [(lang, label, read_clip(path)) for lang, label, path in clips_list]
    positives = [i for i, c in enumerate(clips) if c[1] == 1]
    negatives = [i for i, c in enumerate(clips) if c[1] == 0]
    harness = Harness()
    result = {'floor': args.floor, 'positives': len(positives), 'negatives': len(negatives), 'conditions': {}}
    started = time.monotonic()

    order = list(range(len(clips)))
    random.Random(ORDER_SEED).shuffle(order)
    stream, windows = clean_stream(clips, order)
    hits, false, _ = score_stream(harness, stream, windows)
    result['conditions']['clean'] = {'hits': sum(1 for i in positives if i in hits), 'false': len(false),
                                     'audio_s': round(len(stream) / RATE, 1)}

    if not args.skip_mix:
        for mic in args.mics:
            bed_path = args.noise_dir / f'{mic}-16k-mono-s16.raw'
            bed = read_raw(bed_path)
            for snr in args.snr:
                rng = random.Random(MIX_SEED + snr * 7 + len(mic))
                stream, windows = mix_stream(clips, order, bed, snr, rng)
                hits, false, _ = score_stream(harness, stream, windows)
                result['conditions'][f'mix-{mic}-{snr}dB'] = {'hits': sum(1 for i in positives if i in hits),
                                                              'false': len(false), 'audio_s': round(len(stream) / RATE, 1)}
                print('mix', mic, snr, result['conditions'][f'mix-{mic}-{snr}dB'], file=sys.stderr, flush=True)

    if not args.skip_noise:
        for mic in args.mics:
            raw = read_raw(args.noise_dir / f'long-{mic}-16k-mono-s16.raw', seconds=args.noise_seconds)
            events, _ = harness.run(raw)
            result['conditions'][f'noise-{mic}'] = {'false': len(events), 'audio_s': round(len(raw) / RATE, 1)}
            print('noise', mic, result['conditions'][f'noise-{mic}'], file=sys.stderr, flush=True)

    clean = result['conditions']['clean']
    false_total = sum(c['false'] for c in result['conditions'].values())
    hit_rate = clean['hits'] / max(len(positives), 1)
    mixes = [c for k, c in result['conditions'].items() if k.startswith('mix-')]
    result['summary'] = {
        'clean_hit_rate': round(hit_rate, 4),
        'mix_hit_rate': round(sum(c['hits'] for c in mixes) / (len(positives) * len(mixes)), 4) if mixes else None,
        'false_triggers_total': false_total,
        'floor_met': hit_rate >= args.floor and false_total == 0,
        'wall_s': round(time.monotonic() - started, 1),
    }
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if result['summary']['floor_met'] else 1


def build_parser():
    parser = argparse.ArgumentParser(description='PT/FR transcript wake regression (WP-7c).')
    sub = parser.add_subparsers(dest='command', required=True)
    pins = sub.add_parser('pins')
    pins.add_argument('set', choices=sorted(SETS))
    check = sub.add_parser('check')
    check.add_argument('set', choices=sorted(SETS))
    check.add_argument('--floor', type=float, default=FLOOR)
    check.add_argument('--snr', type=lambda s: [int(v) for v in s.split(',')], default=[5, 10, 20])
    check.add_argument('--mics', type=lambda s: [v for v in s.split(',') if v], default=list(MICS))
    check.add_argument('--noise-seconds', type=float, default=180.0)
    check.add_argument('--noise-dir', type=Path, default=DEFAULT_NOISE_DIR)
    check.add_argument('--skip-mix', action='store_true')
    check.add_argument('--skip-noise', action='store_true')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == 'pins':
        return cmd_pins(args)
    return cmd_check(args)


if __name__ == '__main__':
    sys.exit(main())
