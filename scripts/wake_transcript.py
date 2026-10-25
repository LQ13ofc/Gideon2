"""Transcript wake for Portuguese and French (WP-7c). Offline, CPU, no network, no client authority.

Two stages, both local:
1. Gate: silero VAD v5 (the same model the package uses) cuts the 16 kHz live stream into speech segments.
   Nothing is decoded while the room is silent.
2. Decode: each closed segment is decoded by the shipped Parakeet-TDT v3 int8 model (scripts/stt_worker.py
   `nemo_transducer` assets, target/stt-pt-fr-assets) in a few windows: the whole segment and its first 1.6 s
   and 2.4 s. A window matches when one of its words is the wake name.

Name rule (`name_word`, measured in docs/WP7c.md):
- strong: a word of at least 4 letters within Levenshtein distance 2 of "gideon" or "gidon" after folding
  (accents removed, j/c/k -> g, v/p -> b, t -> d), e.g. "Gidon", "Gedon", "Gidéon", "Jidon", "Bidon";
- weak: a word of at least 3 letters within distance 3 right after a greeting ("olá", "oi", "ei", "bonjour",
  "salut", "hey", "hé"), e.g. "Oi, Dedon" or "Olá, Dom". Without a greeting, short variants such as "Deu" or
  "Dom" never match (they are common words).

The engine emits the same packet detections as the keyword engine in scripts/wake_worker.py, so the Rust
owner (src/wake.rs) is unchanged: one detection per matched segment, at the frame that closed it.

Selected only by a manifest whose `engine` is ENGINE (scripts/wake_worker.py `make_engine`). The Core never
writes such a manifest today: see docs/WP7c.md (Core changes needed before it can be enabled).
"""
import sys
import unicodedata
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ENGINE = 'transcript-parakeet-tdt-0.6b-v3-int8/silero-v5/sherpa-onnx-1.13.8'
STT_ENGINE = 'sherpa-onnx-1.13.8/nemo-parakeet-tdt-0.6b-v3-int8'
RATE = 16000
FRAME_SAMPLES = 320
GREETINGS = frozenset({'ola', 'oi', 'ei', 'bonjour', 'salut', 'hey', 'he'})
CANONICAL = ('gideon', 'gidon')
STRONG_MAX_DISTANCE = 2
STRONG_MIN_LETTERS = 4
GREETING_MAX_DISTANCE = 3
GREETING_MIN_LETTERS = 3
PAD_S = 0.5
PRE_ROLL_S = 0.6
PRE_ROLL_SAMPLES = int(PRE_ROLL_S * RATE)
HISTORY_SAMPLES = 2 * RATE
# Head windows (seconds from the segment onset, zero pad) decoded in addition to the whole segment (pad 0.5 s).
HEAD_WINDOWS_S = ((1.6, 0.1), (2.4, 0.5))
VAD_THRESHOLD = 0.5
VAD_MIN_SILENCE_S = 0.3
VAD_MAX_SPEECH_S = 8.0
MIN_SEGMENT_S = 0.2
VAD_BUFFER_S = 60


def fold(text):
    """Lower case, no accents, and the consonant pairs Parakeet confuses for this name (j/c/k, v/p, t)."""
    text = unicodedata.normalize('NFKD', text.lower())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = text.replace('j', 'g').replace('c', 'g').replace('k', 'g').replace('v', 'b').replace('p', 'b').replace('t', 'd')
    return ''.join(c for c in text if c.isalpha())


def levenshtein(a, b):
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(current[j - 1] + 1, previous[j] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def words(text):
    text = unicodedata.normalize('NFKD', text.lower())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = text.replace('’', "'").replace("'", ' ').replace('-', ' ')
    return [''.join(c for c in w if c.isalpha()) for w in text.split()]


def name_word(text):
    """Returns (word, distance, rule) for the first wake-name word in `text`, or None."""
    ws = [w for w in words(text) if w]
    for i, word in enumerate(ws):
        folded = fold(word)
        distance = min(levenshtein(folded, fold(name)) for name in CANONICAL)
        if len(folded) >= STRONG_MIN_LETTERS and distance <= STRONG_MAX_DISTANCE:
            return word, distance, 'strong'
        after_greeting = i > 0 and ws[i - 1] in GREETINGS
        if after_greeting and len(folded) >= GREETING_MIN_LETTERS and distance <= GREETING_MAX_DISTANCE:
            return word, distance, 'greeting'
    return None


def check_hash(path, digest):
    import hashlib
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
        raise ValueError('artifact hash mismatch')


class TranscriptEngine:
    """Frame engine with the `WakeEngine` interface used by wake_worker.live(): accept, speech, last_end."""

    owns_vad = True

    def __init__(self, manifest, *, start_us=0, recognizer=None, vad=None):
        if manifest.get('engine') != ENGINE:
            raise ValueError('engine version mismatch')
        phrases = manifest['supported_phrases']
        if not isinstance(phrases, dict) or not 1 <= len(phrases) <= 8:
            raise ValueError('invalid phrase catalog')
        active = manifest.get('active_phrases') or [manifest['active_phrase']]
        if not isinstance(active, list) or len(active) != 1 or active[0] not in phrases:
            raise ValueError('unsupported active phrase')
        self.active_phrase = active[0]
        self.active_phrases = (self.active_phrase,)
        self.start_us = start_us
        self.last_end = start_us
        self.last_speech = False
        self.recognizer = recognizer if recognizer is not None else self._recognizer(manifest)
        self.vad = vad if vad is not None else self._vad(manifest)
        self.decodes = 0
        self.segments = 0
        self.history = np.zeros(0, np.float32)
        self.fed = 0

    @staticmethod
    def _recognizer(manifest):
        import sherpa_onnx
        if sherpa_onnx.__version__ != '1.13.8':
            raise ValueError('engine version mismatch')
        root = Path(manifest['model_root'])
        names = {manifest['encoder'], manifest['decoder'], manifest['joiner'], manifest['tokens']}
        if set(manifest['hashes']) != names:
            raise ValueError('missing model hashes')
        for name, digest in manifest['hashes'].items():
            if Path(name).name != name:
                raise ValueError('unsafe asset path')
            check_hash(root / name, digest)
        return sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(root / manifest['encoder']), decoder=str(root / manifest['decoder']),
            joiner=str(root / manifest['joiner']), tokens=str(root / manifest['tokens']),
            num_threads=2, provider='cpu', model_type='nemo_transducer', decoding_method='greedy_search')

    @staticmethod
    def _vad(manifest):
        import sherpa_onnx
        vad_manifest = manifest['vad']
        if vad_manifest.get('engine') != 'silero-vad-v5.0/sherpa-onnx-1.13.8':
            raise ValueError('unsupported VAD')
        check_hash(Path(vad_manifest['path']), vad_manifest['sha256'])
        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = vad_manifest['path']
        config.silero_vad.threshold = VAD_THRESHOLD
        config.silero_vad.min_speech_duration = 0.1
        config.silero_vad.min_silence_duration = VAD_MIN_SILENCE_S
        config.silero_vad.max_speech_duration = VAD_MAX_SPEECH_S
        config.silero_vad.window_size = 512
        config.sample_rate = RATE
        config.num_threads = 1
        config.provider = 'cpu'
        return sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=VAD_BUFFER_S)

    def frame_samples(self, raw):
        return np.frombuffer(raw, dtype='<i2').astype(np.float32) / np.float32(32768)

    def decode(self, samples):
        stream = self.recognizer.create_stream()
        stream.accept_waveform(RATE, samples.astype(np.float32))
        self.recognizer.decode_stream(stream)
        self.decodes += 1
        return ' '.join(stream.result.text.split())

    def match_segment(self, samples, pre_roll=None):
        """Decodes the windows of one closed segment; returns the first name match (word, distance, rule) or None.

        `pre_roll` is the audio just before the VAD onset: the VAD opens a segment on the first voiced frame, so the
        first consonant of the name is otherwise clipped ("Gideon" heard as "Deu" or "idon").
        """
        if pre_roll is not None and len(pre_roll):
            samples = np.concatenate([pre_roll, samples])
        pad = np.zeros(int(RATE * PAD_S), np.float32)
        windows = [np.concatenate([pad, samples, pad])]
        for seconds, head_pad in HEAD_WINDOWS_S:
            head = samples[: int(RATE * seconds)]
            edge = np.zeros(int(RATE * head_pad), np.float32)
            windows.append(np.concatenate([edge, head, edge]))
        for window in windows:
            found = name_word(self.decode(window))
            if found:
                return found
        return None

    def accept(self, samples, timestamp_us):
        if timestamp_us != self.last_end or not 0 < len(samples) <= 1280 or not np.isfinite(samples).all() or np.max(np.abs(samples)) > 1:
            raise ValueError('invalid audio frame')
        end_us = timestamp_us + len(samples) * 1_000_000 // RATE
        self.history = np.concatenate([self.history, samples])[-HISTORY_SAMPLES:]
        self.fed += len(samples)
        self.vad.accept_waveform(samples)
        self.last_speech = bool(self.vad.is_speech_detected())
        events = []
        while not self.vad.empty():
            segment = self.vad.front
            audio = np.asarray(segment.samples, dtype=np.float32)
            start_us = self.start_us + segment.start * 1_000_000 // RATE
            # Index of the onset inside `history` (its first sample is absolute sample self.fed - len(history)).
            onset = segment.start - (self.fed - len(self.history))
            pre_roll = self.history[max(0, onset - PRE_ROLL_SAMPLES):onset] if onset > 0 else None
            self.vad.pop()
            if len(audio) < MIN_SEGMENT_S * RATE or start_us >= end_us:
                continue
            self.segments += 1
            found = self.match_segment(audio, pre_roll)
            if found:
                events.append({'phrase_id': self.active_phrase, 'confidence': None, 'start_us': start_us,
                               'end_us': end_us, 'engine': ENGINE})
                # The Core keeps one wake per cooldown; a later segment in this run is not reported.
                while not self.vad.empty():
                    self.vad.pop()
                break
        self.last_end = end_us
        return events

    def speech(self, samples):
        return self.last_speech
