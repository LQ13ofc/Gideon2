"""Unit tests of the PT/FR transcript wake (WP-7c). Run as a script: target/a1-venv/bin/python scripts/test_wake_transcript.py

No models are loaded: the recognizer and the VAD are fakes with the same methods as sherpa-onnx.
"""
import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wake_transcript as wt  # noqa: E402
import wake_worker  # noqa: E402


class FakeResult:
    def __init__(self, text):
        self.text = text


class FakeStream:
    def __init__(self, recognizer):
        self.recognizer = recognizer
        self.result = FakeResult('')

    def accept_waveform(self, rate, samples):
        assert rate == 16000
        self.recognizer.calls.append(len(samples))
        self.result = FakeResult(self.recognizer.answer)


class FakeRecognizer:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def create_stream(self):
        return FakeStream(self)

    def decode_stream(self, stream):
        pass


class FakeSegment:
    def __init__(self, start, samples):
        self.start = start
        self.samples = samples


class FakeVad:
    """Emits one closed segment at the call number given in `closes` (samples fed so far)."""

    def __init__(self, closes):
        self.fed = 0
        self.closes = list(closes)
        self.queue = []

    def accept_waveform(self, samples):
        self.fed += len(samples)
        if self.closes and self.fed >= self.closes[0][0]:
            _, start = self.closes.pop(0)
            self.queue.append(FakeSegment(start, np.ones(16000, np.float32) * 0.1))

    def is_speech_detected(self):
        return bool(self.queue) or self.fed % 2 == 0

    def empty(self):
        return not self.queue

    @property
    def front(self):
        return self.queue[0]

    def pop(self):
        self.queue.pop(0)


def manifest():
    return {
        'engine': wt.ENGINE,
        'supported_phrases': {'wake_name': 'WAKE_NAME'},
        'active_phrase': 'wake_name',
        'model_root': '/nonexistent',
        'encoder': 'e', 'decoder': 'd', 'joiner': 'j', 'tokens': 't',
        'hashes': {},
        'vad': {'engine': 'silero-vad-v5.0/sherpa-onnx-1.13.8', 'path': '/nonexistent', 'sha256': ''},
    }


def frames(count):
    return [np.zeros(320, np.float32) for _ in range(count)]


class NameRuleTests(unittest.TestCase):
    def test_fold_and_distance(self):
        self.assertEqual(wt.fold('Gidéon'), 'gideon')
        self.assertEqual(wt.fold('Jidon'), 'gidon')
        self.assertEqual(wt.levenshtein('gidon', 'gideon'), 1)
        self.assertEqual(wt.levenshtein('', 'abc'), 3)

    def test_strong_name_variants_match_without_greeting(self):
        for text in ('Gidon.', 'Gedon, abra', 'Gidéon', 'Gédéon', 'Jidon.', 'Bidon, coupe-son.', 'Gideon,'):
            self.assertIsNotNone(wt.name_word(text), text)

    def test_short_variants_need_a_greeting(self):
        self.assertIsNone(wt.name_word('Deu. Aumente o volume.'))
        self.assertIsNone(wt.name_word('Dom Pedro foi o primeiro imperador.'))
        self.assertIsNone(wt.name_word('Olá, deu.'))
        self.assertEqual(wt.name_word('Oi, Dom'), ('dom', 3, 'greeting'))
        self.assertEqual(wt.name_word('Oi, Dedon, que horas são?')[2], 'strong')

    def test_common_sentences_do_not_match(self):
        for text in ('Eu gosto de café com leite pela manhã.', 'Posso ajudar você com alguma coisa hoje?',
                     'Bonjour, quelle heure est-il ?', 'Il fait beau et le ciel est bleu.', 'Dis donc'):
            self.assertIsNone(wt.name_word(text), text)

    def test_strong_match_has_no_greeting_requirement_and_records_rule(self):
        word, distance, rule = wt.name_word('Gidon, coupe o som')
        self.assertEqual((word, distance, rule), ('gidon', 0, 'strong'))


class EngineContractTests(unittest.TestCase):
    def engine(self, answer, closes, **overrides):
        man = manifest()
        man.update(overrides)
        recognizer = FakeRecognizer(answer)
        return wt.TranscriptEngine(man, recognizer=recognizer, vad=FakeVad(closes)), recognizer

    def run_frames(self, engine, count):
        events = []
        for frame in frames(count):
            events += engine.accept(frame, engine.last_end)
        return events

    def test_match_emits_one_detection_on_the_closing_frame(self):
        engine, recognizer = self.engine('Oi Gedon, tudo bem', closes=[(16000, 0)])
        events = self.run_frames(engine, 60)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event['phrase_id'], 'wake_name')
        self.assertEqual(event['engine'], wt.ENGINE)
        self.assertLess(event['start_us'], event['end_us'])
        self.assertEqual(event['end_us'] % 20000, 0)
        self.assertGreater(recognizer.calls[0], 16000)  # whole segment window (with pre-roll and pad)

    def test_no_name_no_detection(self):
        engine, _ = self.engine('Eu gosto de café', closes=[(16000, 0)])
        self.assertEqual(self.run_frames(engine, 60), [])

    def test_frame_contract_is_enforced(self):
        engine, _ = self.engine('', closes=[])
        with self.assertRaises(ValueError):
            engine.accept(np.zeros(320, np.float32), 5)
        with self.assertRaises(ValueError):
            engine.accept(np.zeros(2000, np.float32), 0)
        with self.assertRaises(ValueError):
            engine.accept(np.full(320, 2.0, np.float32), 0)

    def test_manifest_is_validated_before_any_model_load(self):
        with self.assertRaises(ValueError):
            wt.TranscriptEngine({**manifest(), 'engine': 'other'}, recognizer=FakeRecognizer(''), vad=FakeVad([]))
        with self.assertRaises(ValueError):
            wt.TranscriptEngine({**manifest(), 'active_phrase': 'missing'}, recognizer=FakeRecognizer(''), vad=FakeVad([]))
        with self.assertRaises(ValueError):
            wt.TranscriptEngine({**manifest(), 'active_phrases': ['wake_name', 'wake_name']}, recognizer=FakeRecognizer(''),
                                vad=FakeVad([]))

    def test_worker_dispatch_selects_transcript_engine_by_manifest(self):
        original = (wt.TranscriptEngine.__dict__['_recognizer'], wt.TranscriptEngine.__dict__['_vad'])
        wt.TranscriptEngine._recognizer = staticmethod(lambda m: FakeRecognizer(''))
        wt.TranscriptEngine._vad = staticmethod(lambda m: FakeVad([]))
        try:
            engine = wake_worker.make_engine(manifest(), 0.25)
            self.assertIsInstance(engine, wt.TranscriptEngine)
            self.assertTrue(engine.owns_vad)
        finally:
            wt.TranscriptEngine._recognizer, wt.TranscriptEngine._vad = original


if __name__ == '__main__':
    unittest.main()
