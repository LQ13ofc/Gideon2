#!/usr/bin/env python3
"""Offline wake regression and factorial matrix on a pinned clip set. No Core, no audio devices.

The clips go through the production keyword engine (scripts/wake_worker.py `WakeEngine`, the same frame
loop as `live()`, and scripts/audio_conditioning.py when the cell conditions) as ONE continuous 16 kHz stream,
the way the live worker sees the lab run: a lead of silence, then each clip followed by 1.5 s of tail and
0.8 s of gap (the spacing of docs/A7 and of the live matrix). The 2 s cooldown of src/wake.rs is applied to
the detections. A detection inside a clip window (clip + tail) is a hit; a detection in a negative window
or in a gap is a false trigger. Repeats change only the lead and the gaps (seeded), which moves the stream's
state (keyword stream rotation, frame phase, cooldown phase) between runs.

Private audio is not versioned. `pins` writes the clip identities (sha256) to docs/evidence; `check` refuses
to run when the clips on disk do not match the pins (exit 2).

Usage:
  wake_live_regression.py pins CLIPS_JSON OUT_PINS
  wake_live_regression.py check CLIPS_JSON PINS [--floor F] [--repeats N] [--noise-dir DIR] [--manifest M]
  wake_live_regression.py matrix CLIPS_JSON OUT_JSON [--repeats N] [--noise-dir DIR] [--manifest M] [--jobs J]
Exit: `check` 0 = floor met and no false trigger; 1 = regression; 2 = pinned clips missing or changed.
Recommended floor: 0.82 (42 of 51, one hit under the shipped configuration's worst repeat, 43; see
docs/A7-wake-live-test.md, section "Regressão"). The packaged line without warm-up or conditioning fails it.
"""
import argparse
import concurrent.futures as futures
import copy
import hashlib
import json
import os
import random
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))
from audio_conditioning import AUTO_CHAIN, Conditioner  # noqa: E402
from wake_worker import WakeEngine  # noqa: E402

RATE = 16000
FRAME = 320
LEAD_S = 1.0
TAIL_S = 1.5
GAP_S = 0.8
COOLDOWN_US = 2_000_000
ORDER_SEED = 20261024  # the order of the live lab run (/tmp/gideon-wake-lab/matrix.py)
DEFAULT_MANIFEST = BASE / 'target/a1-competitive/manifest.json'
TRACE_GRID = (0.35, 0.30, 0.25, 0.22, 0.20, 0.18, 0.15, 0.12, 0.10)

# Keyword lines (KWS format PHONES :boost #threshold @LABEL), the same phones as the packaged keywords.txt.
HEY = 'HH EY1 G IH1 D IY0 AH0 N'
OKAY = 'OW2 K EY1 G IH1 D IY0 AH0 N'
REJECT = 'HH AY1 G IH1 D IY0 AH0 N'
HEY_VARIANT = 'HH EY1 G IH1 D IY0 N'  # the extra spelling variant of docs/evidence/wake-phrases.json
BASE_THRESHOLD = 0.25  # src/wake.rs BASE_KEYWORDS_THRESHOLD (global; sensitivity 1.0)
PHRASE_BASE_THRESHOLD = 0.22  # src/phrases.rs DEFAULT_THRESHOLD
PHRASE_BOOST = 1.2  # src/phrases.rs DEFAULT_BOOST
THRESHOLD_MIN = 0.1
THRESHOLD_MAX = 0.5
VARIANTS = ('packaged', 'default', 'hey-only', 'variant')


def clamp(value):
    return min(max(value, THRESHOLD_MIN), THRESHOLD_MAX)


def fmt(value):
    return f'{round(value, 4):g}'


@dataclass(frozen=True)
class Cell:
    """One configuration. `packaged` is the A7 keyword line (no options, global threshold); `default` is the
    Core default (hey line boosted and thresholded, competitors kept); `hey-only` drops the competitors;
    `variant` adds the extra hey spelling line. `boost` and `phrase_base` apply to the hey line of the
    non-packaged variants (the Core default is 1.2 and 0.22)."""
    variant: str = 'default'
    conditioning: str = 'auto'  # worker `--conditioning`: auto or off
    warm_up_s: float = 3.0      # silence that primes a fresh keyword stream before the first frame
    sensitivity: float = 1.0
    boost: float = PHRASE_BOOST
    phrase_base: float = PHRASE_BASE_THRESHOLD

    def name(self):
        name = f'{self.variant}|cond-{self.conditioning}|warm{self.warm_up_s:g}|s{self.sensitivity:g}'
        if (self.boost, self.phrase_base) != (PHRASE_BOOST, PHRASE_BASE_THRESHOLD):
            name += f'|b{self.boost:g}t{self.phrase_base:g}'
        return name


def keyword_text(variant, sensitivity=1.0, threshold_override=None, boost=PHRASE_BOOST,
                 phrase_base=PHRASE_BASE_THRESHOLD):
    """Keyword file text and the global threshold the worker gets, as src/phrases.rs `keywords_text` writes them."""
    global_t = clamp(BASE_THRESHOLD * (2.0 - sensitivity))
    hey_t = clamp(phrase_base * (2.0 - sensitivity))
    if threshold_override is not None:
        if variant == 'packaged':
            global_t = threshold_override
        else:
            hey_t = threshold_override
    if variant == 'packaged':
        lines = [f'{HEY} @HEY_GIDEON']
    else:
        option = f' :{fmt(boost)} #{fmt(round(hey_t, 4))}'
        lines = [f'{HEY}{option} @HEY_GIDEON']
        if variant == 'variant':
            lines.append(f'{HEY_VARIANT}{option} @HEY_GIDEON')
    if variant != 'hey-only':
        lines += [f'{OKAY} @OKAY_GIDEON', f'{REJECT} @REJECT_HI']
    return '\n'.join(lines) + '\n', global_t


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def load_base(manifest_path):
    return json.loads(Path(manifest_path).read_text())


def open_engine(base, cell, work, threshold_override=None):
    text, global_t = keyword_text(cell.variant, cell.sensitivity, threshold_override, cell.boost, cell.phrase_base)
    # One file per engine: parallel workers must never share a keyword file (a reader can see a half write).
    with tempfile.NamedTemporaryFile('w', dir=work, prefix='keywords-', suffix='.txt', delete=False) as handle:
        handle.write(text)
        keywords = Path(handle.name)
    manifest = copy.deepcopy(base)
    manifest['keywords_file'] = str(keywords)
    manifest['hashes'] = dict(base['hashes'], **{'keywords.txt': sha256_bytes(text.encode())})
    manifest['active_phrase'] = 'hey_gideon'
    if cell.variant == 'hey-only':
        manifest['supported_phrases'] = {'hey_gideon': 'HEY_GIDEON'}
        manifest['rejection_labels'] = []
    return WakeEngine(manifest, dev_threshold=global_t)


def run_stream(engine, samples, cell, conditioning_on):
    """The live frame loop without VAD or packets: returns (detections, cooldown_dropped, rotations) in samples."""
    if cell.warm_up_s > 0:
        engine.warm_up(int(round(cell.warm_up_s * RATE)))
    conditioner = Conditioner(AUTO_CHAIN) if conditioning_on else None
    detections, dropped, rotations = [], [], []
    last_accepted = None
    stream_start = engine.stream_start_us
    for offset in range(0, len(samples) - FRAME + 1, FRAME):
        raw = samples[offset:offset + FRAME]
        heard = raw.astype(np.float32) / np.float32(32768)
        if conditioner is not None:
            heard = conditioner.process(heard)
        timestamp = engine.last_end
        for event in engine.accept(heard, timestamp):
            end = event['end_us']
            if last_accepted is not None and end - last_accepted < COOLDOWN_US:
                dropped.append(end * RATE // 1_000_000)
                continue
            last_accepted = end
            detections.append(end * RATE // 1_000_000)
        if engine.stream_start_us != stream_start:
            stream_start = engine.stream_start_us
            rotations.append(engine.last_end * RATE // 1_000_000)
    return detections, dropped, rotations


def build_stream(clips, samples, repeat):
    rng = random.Random(7000 + repeat)
    lead = LEAD_S + (rng.uniform(0.0, 0.5) if repeat else 0.0)
    parts = [np.zeros(int(lead * RATE), dtype=np.int16)]
    pos = len(parts[0])
    windows = []
    for clip in clips:
        data = samples[clip['id']]
        windows.append({'id': clip['id'], 'expect': clip['expect_wake'], 'start': pos, 'end': pos + len(data),
                        'condition': clip.get('condition'), 'voice': clip.get('voice'), 'phrase': clip.get('phrase'),
                        'class': clip.get('class')})
        parts.append(data)
        pos += len(data)
        gap = TAIL_S + GAP_S + (rng.uniform(0.0, 0.4) if repeat else 0.0)
        silence = np.zeros(int(gap * RATE), dtype=np.int16)
        parts.append(silence)
        pos += len(silence)
    return np.concatenate(parts), windows


def attribute(windows, detections):
    """Per clip window: first detection (sample index) inside [start, end + tail). Others are gap triggers."""
    claimed = set()
    rows = []
    for w in windows:
        limit = w['end'] + int(TAIL_S * RATE)
        hits = [t for t in detections if w['start'] <= t < limit]
        claimed.update(hits)
        row = dict(w, triggered=bool(hits))
        if hits:
            row['latency_ms'] = round((hits[0] - w['start']) * 1000 / RATE)
        rows.append(row)
    gap = [t for t in detections if t not in claimed]
    return rows, gap


def load_clips(clips_json):
    clips = json.loads(Path(clips_json).read_text())
    import soundfile as sf
    samples = {}
    for clip in clips:
        data, rate = sf.read(clip['path'], dtype='int16')
        if rate != RATE or data.ndim != 1:
            raise ValueError(f'clip {clip["id"]}: expected 16 kHz mono')
        samples[clip['id']] = data
    return clips, samples


def evaluate(base, cell, clips, samples, repeat, work):
    engine = open_engine(base, cell, work)
    stream, windows = build_stream(clips, samples, repeat)
    detections, dropped, rotations = run_stream(engine, stream, cell, cell.conditioning == 'auto')
    rows, gap = attribute(windows, detections)
    misses = [r for r in rows if r['expect'] and not r['triggered']]
    rotated = []
    for r in misses:
        r['rotation_in_clip'] = any(r['start'] <= t <= r['end'] for t in rotations)
        rotated.append(r['rotation_in_clip'])
    for r in rows:
        r['rotation_in_clip'] = any(r['start'] <= t <= r['end'] for t in rotations)
    positives = [r for r in rows if r['expect']]
    negatives = [r for r in rows if not r['expect']]
    return {
        'cell': cell.name(), 'repeat': repeat,
        'positives': len(positives), 'positive_hits': sum(r['triggered'] for r in positives),
        'negatives': len(negatives), 'negative_false': sum(r['triggered'] for r in negatives),
        'gap_false': len(gap), 'cooldown_dropped': len(dropped), 'rotations': len(rotations),
        'misses_in_rotation': sum(rotated),
        'clips': [{k: v for k, v in r.items() if k not in ('start', 'end')} for r in rows],
    }


def trace_misses(base, cell, misses, samples, work):
    """Highest threshold (grid order) that still fires each missed positive, alone with the cell's lead and tail.
    A proxy for the spotter score: a clip that fires only at a lax threshold is an acoustic or competitor miss."""
    traces = {}
    lead = np.zeros(int(LEAD_S * RATE), dtype=np.int16)
    tail = np.zeros(int(TAIL_S * RATE), dtype=np.int16)
    for row in misses:
        data = samples[row['id']]
        fires = []
        for threshold in TRACE_GRID:
            engine = open_engine(base, cell, work, threshold_override=threshold)
            hits, _, _ = run_stream(engine, np.concatenate([lead, data, tail]), cell, cell.conditioning == 'auto')
            if hits:
                fires.append(threshold)
        traces[row['id']] = {'highest_firing_threshold': max(fires) if fires else None,
                             'clip_seconds': round(len(data) / RATE, 2)}
    return traces


def noise_run(base, cell, raw_path, work):
    data = np.fromfile(raw_path, dtype='<i2')
    engine = open_engine(base, cell, work)
    detections, dropped, rotations = run_stream(engine, data, cell, cell.conditioning == 'auto')
    return {'file': Path(raw_path).name, 'seconds': round(len(data) / RATE, 1), 'false_triggers': len(detections),
            'cooldown_dropped': len(dropped), 'rotations': len(rotations)}


def noise_files(noise_dir):
    return sorted(Path(noise_dir).glob('long-*-16k-mono-s16.raw'))


def write_pins(clips_json, out):
    clips = json.loads(Path(clips_json).read_text())
    rows = [{'id': c['id'], 'sha256': sha256_file(c['path']), 'expect': bool(c['expect_wake']), 'class': c['class'],
             'condition': c.get('condition'), 'voice': c.get('voice'), 'phrase': c.get('phrase')} for c in clips]
    pins = {'version': 1, 'clips': rows, 'positives': sum(r['expect'] for r in rows),
            'negatives': sum(not r['expect'] for r in rows),
            'protocol': 'live lab order (seed 20261024), lead 1.0 s, tail 1.5 s, gap 0.8 s; 16 kHz mono s16 clips',
            'scope': 'private TTS clips (Kokoro, Pocket); audio not versioned'}
    Path(out).write_text(json.dumps(pins, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({'clips': len(rows), 'positives': pins['positives'], 'negatives': pins['negatives']}))


def verify_pins(clips_json, pins_path):
    pins = json.loads(Path(pins_path).read_text())
    clips = json.loads(Path(clips_json).read_text())
    by_id = {c['id']: c for c in clips}
    problems = []
    if sorted(by_id) != sorted(p['id'] for p in pins['clips']):
        problems.append('clip id set differs from the pins')
    for pin in pins['clips']:
        clip = by_id.get(pin['id'])
        if clip is None:
            continue
        if not Path(clip['path']).is_file() or sha256_file(clip['path']) != pin['sha256']:
            problems.append(f'clip changed or missing: {pin["id"]}')
    return pins, problems


def all_cells():
    return [Cell(variant=v, conditioning=c, warm_up_s=w) for v in VARIANTS for c in ('auto', 'off') for w in (3.0, 0.0)]


def run_matrix(base, clips, samples, repeats, noise, work, jobs, cells=None):
    cells = cells or all_cells()
    with futures.ProcessPoolExecutor(max_workers=jobs) as pool:
        pending = [pool.submit(evaluate, base, cell, clips, samples, repeat, work)
                   for cell in cells for repeat in range(repeats)]
        results = [job.result() for job in pending]
    noise_results = {}
    if noise:
        with futures.ProcessPoolExecutor(max_workers=jobs) as pool:
            pending = [(cell.name(), pool.submit(noise_run, base, cell, f, work))
                       for cell in cells for f in noise_files(noise)]
            for name, job in pending:
                noise_results.setdefault(name, []).append(job.result())
    return results, noise_results


def summarize(results, cell_name):
    rows = [r for r in results if r['cell'] == cell_name]
    hits = [r['positive_hits'] for r in rows]
    return {'cell': cell_name, 'repeats': len(rows), 'hits': hits, 'of': rows[0]['positives'] if rows else None,
            'negative_false': [r['negative_false'] for r in rows], 'gap_false': [r['gap_false'] for r in rows],
            'cooldown_dropped': [r['cooldown_dropped'] for r in rows], 'rotations': [r['rotations'] for r in rows],
            'misses_in_rotation': [r['misses_in_rotation'] for r in rows]}


def cmd_check(args):
    pins, problems = verify_pins(args.clips_json, args.pins)
    if problems:
        print(json.dumps({'status': 'PINS_MISMATCH', 'problems': problems[:10]}, indent=1))
        return 2
    clips, samples = load_clips(args.clips_json)
    base = load_base(args.manifest)
    cell = Cell(variant=args.variant, conditioning=args.conditioning, warm_up_s=args.warm_up)
    with tempfile.TemporaryDirectory(prefix='wake-regression-') as work:
        results = [evaluate(base, cell, clips, samples, repeat, work) for repeat in range(args.repeats)]
        noise = []
        if args.noise_dir:
            noise = [noise_run(base, cell, f, work) for f in noise_files(args.noise_dir)]
    hits = [r['positive_hits'] for r in results]
    false = sum(r['negative_false'] + r['gap_false'] for r in results)
    noise_false = sum(n['false_triggers'] for n in noise)
    rate = min(hits) / pins['positives']
    ok = rate >= args.floor and false == 0 and noise_false == 0
    report = {'status': 'PASS' if ok else 'FAIL', 'cell': cell.name(), 'floor': args.floor,
              'min_hit_rate': round(rate, 4), 'hits': hits, 'of': pins['positives'], 'false_on_negatives': false,
              'noise_false_triggers': noise_false, 'noise_seconds': sum(n['seconds'] for n in noise)}
    print(json.dumps(report, indent=1))
    return 0 if ok else 1


def cmd_matrix(args):
    pins, problems = verify_pins(args.clips_json, args.pins) if args.pins else ({'positives': None}, [])
    if problems:
        print(json.dumps({'status': 'PINS_MISMATCH', 'problems': problems[:10]}, indent=1))
        return 2
    clips, samples = load_clips(args.clips_json)
    base = load_base(args.manifest)
    with tempfile.TemporaryDirectory(prefix='wake-matrix-') as work:
        results, noise = run_matrix(base, clips, samples, args.repeats, args.noise_dir, work, args.jobs)
        cells = sorted({r['cell'] for r in results})
        table = [summarize(results, c) for c in cells]
        traces = {}
        by_name = {cell.name(): cell for cell in all_cells()}
        for name in args.trace or []:
            first = next(r for r in results if r['cell'] == name and r['repeat'] == 0)
            misses = [c for c in first['clips'] if c['expect'] and not c['triggered']]
            traces[name] = trace_misses(base, by_name[name], misses, samples, work)
    out = {'table': table, 'results': results, 'noise': noise, 'traces': traces,
           'positives': sum(1 for c in clips if c['expect_wake']), 'repeats': args.repeats}
    Path(args.out_json).write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
    for row in table:
        print(json.dumps(row))


def cmd_grid(args):
    """Boost x hey-threshold grid of the default variant (auto conditioning, warm-up 3 s, sensitivity 1.0)."""
    clips, samples = load_clips(args.clips_json)
    base = load_base(args.manifest)
    cells = [Cell(boost=b, phrase_base=t) for b in args.boosts for t in args.bases]
    with tempfile.TemporaryDirectory(prefix='wake-grid-') as work:
        results, noise = run_matrix(base, clips, samples, args.repeats, args.noise_dir, work, args.jobs, cells)
    table = [summarize(results, c) for c in sorted({r['cell'] for r in results})]
    for row in table:
        row['noise_false'] = sum(n['false_triggers'] for n in noise.get(row['cell'], []))
        row['noise_seconds'] = sum(n['seconds'] for n in noise.get(row['cell'], []))
    Path(args.out_json).write_text(json.dumps({'table': table, 'noise': noise}, indent=1) + '\n')
    for row in table:
        print(json.dumps({k: row[k] for k in ('cell', 'hits', 'negative_false', 'gap_false', 'noise_false')}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('pins')
    p.add_argument('clips_json')
    p.add_argument('out')
    c = sub.add_parser('check')
    c.add_argument('clips_json')
    c.add_argument('pins')
    c.add_argument('--floor', type=float, required=True)
    c.add_argument('--repeats', type=int, default=3)
    c.add_argument('--noise-dir')
    c.add_argument('--manifest', default=str(DEFAULT_MANIFEST))
    # The default is the shipped configuration; the other values exist for the negative control (docs/A7).
    c.add_argument('--variant', choices=VARIANTS, default='default')
    c.add_argument('--conditioning', choices=('auto', 'off'), default='auto')
    c.add_argument('--warm-up', type=float, default=3.0)
    m = sub.add_parser('matrix')
    m.add_argument('clips_json')
    m.add_argument('out_json')
    m.add_argument('--pins')
    m.add_argument('--repeats', type=int, default=3)
    m.add_argument('--noise-dir')
    m.add_argument('--manifest', default=str(DEFAULT_MANIFEST))
    m.add_argument('--jobs', type=int, default=max(1, min(8, os.cpu_count() or 1)))
    m.add_argument('--trace', nargs='*')
    g = sub.add_parser('grid')
    g.add_argument('clips_json')
    g.add_argument('out_json')
    g.add_argument('--boosts', type=float, nargs='+', default=[PHRASE_BOOST])
    g.add_argument('--bases', type=float, nargs='+', default=[PHRASE_BASE_THRESHOLD])
    g.add_argument('--repeats', type=int, default=3)
    g.add_argument('--noise-dir')
    g.add_argument('--manifest', default=str(DEFAULT_MANIFEST))
    g.add_argument('--jobs', type=int, default=max(1, min(8, os.cpu_count() or 1)))
    args = parser.parse_args(argv)
    if args.command == 'pins':
        write_pins(args.clips_json, args.out)
        return 0
    if args.command == 'check':
        return cmd_check(args)
    if args.command == 'grid':
        cmd_grid(args)
        return 0
    cmd_matrix(args)
    return 0


if __name__ == '__main__':
    sys.exit(main())
