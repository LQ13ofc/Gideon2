#!/usr/bin/env python3
"""A5 worker unit tests that need no sherpa and no numpy: argument parsing, threshold bounds and the live frame
loop, driven through the test-only energy detector. Real detector behaviour is covered by test_wake_worker.py."""
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wake_worker as w  # noqa: E402

MANIFEST = {'engine': w.TEST_ENGINE, 'test_only': True, 'supported_phrases': {'hey_gideon': 'HEY'}, 'active_phrase': 'hey_gideon'}


def frame(value):
    return b''.join(int(value).to_bytes(2, 'little', signed=True) for _ in range(w.FRAME_SAMPLES))


class LiveWorkerTests(unittest.TestCase):
    def test_threshold_argument_is_bounded_and_defaults_unchanged(self):
        self.assertEqual(w.parse(['m.json', '0']).keywords_threshold, 0.25)
        self.assertEqual(w.parse(['m.json', '--live', '--keywords-threshold', '0.375']).keywords_threshold, 0.375)
        for bad in ('0.05', '0.6', '1.0'):
            with self.subTest(threshold=bad), self.assertRaises(ValueError):
                w.parse(['m.json', '--live', '--keywords-threshold', bad])

    def test_live_and_replay_arguments_are_exclusive(self):
        with self.assertRaises(ValueError):
            w.parse(['m.json'])
        with self.assertRaises(ValueError):
            w.parse(['m.json', '0', '--live'])
        with self.assertRaises(ValueError):
            w.parse(['m.json', '--live', '--start-us', '-1'])

    def test_frames_produce_one_packet_each_with_continuous_clock(self):
        engine = w.make_engine(MANIFEST, 0.25, start_us=40_000)
        raw = frame(0) + frame(12000) + frame(12000) + frame(0)
        stdin, stdout = io.BytesIO(raw), io.StringIO()
        w.live(engine, None, stdin, stdout)
        packets = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([p['timestamp_us'] for p in packets], [40_000, 60_000, 80_000, 100_000])
        self.assertEqual(len(packets[0]['samples']), w.FRAME_SAMPLES)
        # One onset: the second loud frame continues the same loud run.
        self.assertEqual([len(p['detections']) for p in packets], [0, 1, 0, 0])
        self.assertEqual(packets[1]['detections'][0]['start_us'], 60_000)
        self.assertEqual(packets[1]['detections'][0]['end_us'], 80_000)

    def test_partial_frame_at_eof_is_not_processed(self):
        engine = w.make_engine(MANIFEST, 0.25)
        stdin, stdout = io.BytesIO(frame(12000)[:100]), io.StringIO()
        w.live(engine, None, stdin, stdout)
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual(engine.last_end, 0)


if __name__ == '__main__':
    unittest.main()
