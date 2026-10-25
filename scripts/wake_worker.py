"""Offline CPU inference. No devices/network and no client authority.

Two drivers share one engine:
- replay: `wake_worker.py MANIFEST FIXTURE_INDEX` streams a fixture at real cadence (finite).
- live: `wake_worker.py MANIFEST --live --start-us N` reads raw s16le mono 16 kHz PCM on stdin in
  320-sample (20 ms) frames and writes one JSON packet per frame on stdout. Timestamps continue from
  --start-us, so the Core's audio clock never restarts when the worker is restarted.

`--keywords-threshold T` is the keyword-spotter threshold. The Core derives it from the preference
`wake_sensitivity` (src/wake.rs `keywords_threshold`): sensitivity 0.5 -> 0.375 (stricter),
1.0 -> 0.25 (the default, unchanged), 1.5 -> 0.125 (more sensitive). Accepted range: 0.1..0.5.
Lower thresholds admit more detections; the engine reports no score, so this is the only lever.

A manifest with `"test_only": true` and engine `test-energy-detector` selects a pure-Python energy
onset detector for the Rust integration tests (no sherpa, no numpy). Production manifests never
carry it. Heavy imports (sherpa_onnx, soundfile through pcm_fixture) happen only on the real path.
"""
from collections import deque
import argparse
import json
import math
from pathlib import Path
import sys
import time

try:
    import numpy as np
except ImportError:  # only the test-only detector runs without numpy
    np = None
sys.path.insert(0, str(Path(__file__).resolve().parent))

ENGINE = 'sherpa-onnx-1.13.8/zipformer-zh-en-3M-2025-12-20-int8-chunk8/competitive-v2'
TEST_ENGINE = 'test-energy-detector'
FRAME_SAMPLES = 320  # 20 ms at 16 kHz; live frames are exactly this many s16 samples
WARM_UP_SAMPLES = 3 * 16000  # live only: silence that primes a fresh keyword stream (see warm_up)
THRESHOLD_MIN = 0.1
THRESHOLD_MAX = 0.5


def check_threshold(value):
    if not THRESHOLD_MIN <= value <= THRESHOLD_MAX: raise ValueError('invalid keyword threshold')
    return value


def read_fixture(row):
    from pcm_fixture import read_fixture as _read_fixture
    return _read_fixture(row)


class WakeEngine:
    def __init__(self, manifest, *, dev_threshold=0.25, start_us=0):
        check_threshold(dev_threshold)
        import sherpa_onnx
        from pcm_fixture import check_hash
        if manifest['engine'] != ENGINE or sherpa_onnx.__version__ != '1.13.8':
            raise ValueError('engine version mismatch')
        phrases = manifest['supported_phrases']
        if not isinstance(phrases, dict) or not 1 <= len(phrases) <= 8:
            raise ValueError('invalid phrase catalog')
        labels = list(phrases.values()) + manifest['rejection_labels']
        if len(set(labels)) != len(labels) or any(not isinstance(x,str) or not x.isascii() or not x.replace('_','').isalnum() or len(x)>64 for x in [*phrases, *labels]):
            raise ValueError('invalid phrase IDs or labels')
        self.supported_phrases = tuple(phrases)
        # `active_phrases` (Core runtime, several at once) or the single `active_phrase` (packaged profile).
        active = manifest.get('active_phrases') or [manifest['active_phrase']]
        if not isinstance(active, list) or not active or len(set(active)) != len(active) or any(p not in phrases for p in active) or len(active) > 5:
            raise ValueError('unsupported active phrase')
        self.active_phrases = tuple(active)
        self.active_phrase = active[0]
        self.active_labels = {phrases[p]: p for p in active}
        self.active_label = phrases[self.active_phrase]
        self.labels = frozenset(labels)
        assets = Path(manifest['asset_root'])
        # Core runtime manifests point the keyword file at a generated copy (src/phrases.rs); the packaged one stays in assets.
        keywords = Path(manifest['keywords_file']) if 'keywords_file' in manifest else assets/'keywords.txt'
        if not keywords.is_absolute(): raise ValueError('unsafe keywords path')
        required = {manifest['encoder'], manifest['decoder'], manifest['joiner'], 'tokens.txt', 'keywords.txt'}
        if set(manifest['hashes']) != required:
            raise ValueError('missing or unexpected artifact hashes')
        for name, digest in manifest['hashes'].items():
            if Path(name).name != name: raise ValueError('unsafe asset path')
            check_hash(keywords if name == 'keywords.txt' else assets/name, digest)
        declared = []
        vocab = {line.split()[0] for line in (assets/'tokens.txt').read_text().splitlines() if line.split()}
        for line in keywords.read_text().splitlines():
            tokens = line.split()
            # Optional per-phrase `:boost` and `#threshold` fields sit between the phones and `@LABEL`.
            options = [t for t in tokens[:-1] if t[:1] in (':', '#')]
            phones = [t for t in tokens[:-1] if t[:1] not in (':', '#')]
            if len(tokens)<2 or not tokens[-1].startswith('@') or any(t not in vocab for t in phones) or not phones or len(options) > 2:
                raise ValueError('invalid keyword tokens')
            for option in options:
                if not (0.0 <= float(option[1:]) <= 10.0 if option[0] == ':' else 0.0 < float(option[1:]) < 1.0):
                    raise ValueError('invalid keyword option')
            declared.append(tokens[-1][1:])
        # Several lines may carry one label (spelling variants); every label must be declared and nothing else.
        if set(declared) != self.labels:
            raise ValueError('keyword catalog mismatch')
        self.start_us = start_us
        self.kws = sherpa_onnx.KeywordSpotter(tokens=str(assets/'tokens.txt'), encoder=str(assets/manifest['encoder']), decoder=str(assets/manifest['decoder']), joiner=str(assets/manifest['joiner']), keywords_file=str(keywords), num_threads=1, provider='cpu', keywords_threshold=dev_threshold, keywords_score=1.0)
        self.reset()

    def reset(self):
        self.stream = self.kws.create_stream()
        self.last_end = self.start_us
        self.stream_start_us = self.start_us
        self.recent = deque()

    def warm_up(self, samples=WARM_UP_SAMPLES):
        """Primes a fresh keyword stream with silence before the first Core frame (live only).

        A cold stream misses speech that starts within its first seconds (A7 probe: 28/51 positives
        with 1 s of lead, 47/51 with 4 s). Detections during priming are discarded. The stream origin
        moves back by the priming length, so detection times still map onto the Core clock.
        """
        self.stream.accept_waveform(16000, np.zeros(samples, dtype=np.float32))
        self.decode()
        self.stream_start_us -= samples * 1_000_000 // 16000

    def frame_samples(self, raw):
        return np.frombuffer(raw, dtype='<i2').astype(np.float32) / np.float32(32768)

    def decode(self):
        events = []
        while self.kws.is_ready(self.stream):
            self.kws.decode_stream(self.stream)
            result = self.kws.get_result(self.stream)
            if result:
                if result not in self.labels: raise ValueError('unsupported detection')
                if result not in self.active_labels:
                    self.kws.reset_stream(self.stream)
                    continue
                native = self.kws.keyword_spotter.get_result(self.stream)
                times = native.timestamps
                start = self.stream_start_us + int((native.start_time + min(times))*1e6) if times else self.last_end-80000
                events.append({'phrase_id':self.active_labels[result],'confidence':None,'start_us':start,'end_us':self.last_end,'engine':ENGINE})
                self.kws.reset_stream(self.stream)
        return events

    def accept(self, samples, timestamp_us):
        if timestamp_us != self.last_end or not 0<len(samples)<=1280 or not np.isfinite(samples).all() or np.max(np.abs(samples))>1:
            raise ValueError('invalid audio frame')
        # Native feature history can grow indefinitely on a never-ending silence stream.
        # Bound each stream to 10s and prime its replacement with 2s of PCM overlap.
        if timestamp_us - self.stream_start_us >= 10_000_000:
            self.stream = self.kws.create_stream()
            self.stream_start_us = self.recent[0][0] if self.recent else timestamp_us
            for _, old in self.recent:
                self.stream.accept_waveform(16000, old)
                self.decode()  # Already consumed overlap never emits a second wake.
        self.last_end += len(samples)*1_000_000//16000
        self.stream.accept_waveform(16000, samples)
        events = self.decode()
        self.recent.append((timestamp_us, samples.copy()))
        while self.recent and self.recent[0][0] < self.last_end - 2_000_000:
            self.recent.popleft()
        return events


class EnergyOnsetEngine:
    """Test-only onset detector: one detection per loud run (RMS >= 0.05). Never selected by production."""

    def __init__(self, manifest, *, dev_threshold=0.25, start_us=0):
        check_threshold(dev_threshold)
        phrases = manifest['supported_phrases']
        self.supported_phrases = tuple(phrases)
        self.active_phrase = manifest['active_phrase']
        if self.active_phrase not in phrases:
            raise ValueError('unsupported active phrase')
        self.start_us = start_us
        self.reset()

    def reset(self):
        self.last_end = self.start_us
        self.loud = False

    def frame_samples(self, raw):
        return [int.from_bytes(raw[i:i+2], 'little', signed=True) / 32768.0 for i in range(0, len(raw), 2)]

    def accept(self, samples, timestamp_us):
        count = len(samples)
        if timestamp_us != self.last_end or not 0 < count <= 1280 or any(not math.isfinite(x) or abs(x) > 1 for x in samples):
            raise ValueError('invalid audio frame')
        end = timestamp_us + count*1_000_000//16000
        loud = math.sqrt(sum(x*x for x in samples)/count) >= 0.05
        events = []
        if loud and not self.loud:
            events.append({'phrase_id':self.active_phrase,'confidence':None,'start_us':timestamp_us,'end_us':end,'engine':TEST_ENGINE})
        self.loud = loud
        self.last_end = end
        return events

    def speech(self, samples):
        # Test-only speech flag (the Core captures and endpoints on it): the same RMS rule as the onset.
        return math.sqrt(sum(x*x for x in samples)/len(samples)) >= 0.05


class VadEngine:
    def __init__(self, manifest):
        import sherpa_onnx
        from pcm_fixture import check_hash
        if manifest['engine']!='silero-vad-v5.0/sherpa-onnx-1.13.8':raise ValueError('unsupported VAD')
        check_hash(Path(manifest['path']),manifest['sha256'])
        config=sherpa_onnx.VadModelConfig()
        config.silero_vad.model=manifest['path'];config.silero_vad.threshold=0.5
        config.silero_vad.min_speech_duration=0.1;config.silero_vad.min_silence_duration=0.1
        config.silero_vad.max_speech_duration=30.;config.silero_vad.window_size=512
        config.sample_rate=16000;config.num_threads=1;config.provider='cpu'
        self.vad=sherpa_onnx.VoiceActivityDetector(config,buffer_size_in_seconds=1.)
    def accept(self, samples):
        self.vad.accept_waveform(samples)
        result=self.vad.is_speech_detected()
        while not self.vad.empty():self.vad.pop()
        return bool(result)


def make_engine(manifest, threshold, start_us=0):
    if manifest.get('test_only') is True and manifest.get('engine') == TEST_ENGINE:
        return EnergyOnsetEngine(manifest, dev_threshold=threshold, start_us=start_us)
    return WakeEngine(manifest, dev_threshold=threshold, start_us=start_us)


def plain(samples):
    return samples.tolist() if hasattr(samples, 'tolist') else list(samples)


def replay(manifest, row, emit=None):
    engine = WakeEngine(manifest)
    samples = read_fixture(row)
    samples = np.concatenate([samples,np.zeros(16000,dtype=np.float32)])
    detections = []
    started = time.monotonic()
    for offset in range(0,len(samples),1280):
        chunk = samples[offset:offset+1280]
        events = engine.accept(chunk, offset*1_000_000//16000)
        detections += events
        if emit:
            for event in events: emit(event)
    return {'detections': detections, 'wall_s': time.monotonic()-started, 'audio_s': len(samples)/16000}


def stream_fixture(engine, vad, manifest, row):
    samples = np.concatenate([read_fixture(row), np.zeros(16000, dtype=np.float32)])
    for offset in range(0, len(samples), 1280):
        chunk = samples[offset:offset+1280]
        timestamp = offset*1_000_000//16000
        events = engine.accept(chunk, timestamp)
        print(json.dumps({'timestamp_us': timestamp, 'samples': chunk.tolist(), 'detections': events, 'speech':vad.accept(chunk) if vad else None}), flush=True)
        # Replay at real cadence; the Rust owner remains responsive to IPC/cancel.
        time.sleep(len(chunk)/16000)


def read_exact(stream, count):
    data = bytearray()
    while len(data) < count:
        chunk = stream.read(count - len(data))
        if not chunk:
            return None
        data += chunk
    return bytes(data)


def live(engine, vad, stdin, stdout, conditioner=None):
    """Frame loop for the Core's live path: one packet per 20 ms frame, bounded by the stdin pipe.

    `conditioner` (scripts/audio_conditioning.py, preference `input_conditioning` = auto) shapes the frames
    the spotter hears only. The packets and the VAD keep the raw frames, so capture and STT are unchanged.
    """
    if hasattr(engine, 'warm_up'):
        engine.warm_up()
    while True:
        raw = read_exact(stdin, FRAME_SAMPLES * 2)
        if raw is None:
            return
        timestamp = engine.last_end
        samples = engine.frame_samples(raw)
        heard = conditioner.process(samples) if conditioner is not None else samples
        events = engine.accept(heard, timestamp)
        speech = vad.accept(samples) if vad else (engine.speech(samples) if hasattr(engine, 'speech') else None)
        stdout.write(json.dumps({'timestamp_us': timestamp, 'samples': plain(samples), 'detections': events, 'speech': speech}) + '\n')
        stdout.flush()


def parse(argv):
    parser = argparse.ArgumentParser(description='wake worker (replay fixture or live PCM)')
    parser.add_argument('manifest')
    parser.add_argument('fixture', nargs='?', type=int)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--start-us', type=int, default=0)
    parser.add_argument('--active-phrase')
    parser.add_argument('--keywords-threshold', type=float, default=0.25)
    # Live only: `auto` shapes the frames the spotter hears (scripts/audio_conditioning.py AUTO_CHAIN).
    parser.add_argument('--conditioning', choices=('auto', 'off'), default='off')
    # Preflight only: builds the engine (models, hashes, keyword file) and exits 0. Used before a switch.
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    if args.check:
        if args.live or args.fixture is not None: raise ValueError('invalid arguments')
    elif args.live == (args.fixture is not None): raise ValueError('invalid arguments')
    if args.conditioning != 'off' and not args.live: raise ValueError('invalid arguments')
    if args.start_us < 0: raise ValueError('invalid start')
    check_threshold(args.keywords_threshold)
    return args


if __name__ == '__main__':
    arguments = parse(sys.argv[1:])
    manifest = json.loads(Path(arguments.manifest).read_text())
    # A Core runtime manifest names its active list; the single-phrase override only applies to packaged profiles.
    if arguments.active_phrase and 'active_phrases' not in manifest:
        manifest['active_phrase'] = arguments.active_phrase
    engine = make_engine(manifest, arguments.keywords_threshold, arguments.start_us)
    if arguments.check:
        print(json.dumps({'check': 'ok', 'engine': manifest['engine'], 'active_phrases': list(getattr(engine, 'active_phrases', ()))}), flush=True)
        sys.exit(0)
    # The test-only detector names a `vad` block so the Core captures, but it has no VAD model: it sets speech itself.
    vad = VadEngine(manifest['vad']) if 'vad' in manifest and manifest.get('test_only') is not True else None
    if arguments.live:
        conditioner = None
        # The test-only detector stays numpy-free (no conditioning there); production manifests never carry test_only.
        if arguments.conditioning == 'auto' and manifest.get('test_only') is not True:
            from audio_conditioning import AUTO_CHAIN, Conditioner
            conditioner = Conditioner(AUTO_CHAIN)
        live(engine, vad, sys.stdin.buffer, sys.stdout, conditioner)
    else:
        stream_fixture(engine, vad, manifest, manifest['fixtures'][arguments.fixture])
