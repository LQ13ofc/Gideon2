#!/usr/bin/env python3
"""Unit tests of scripts/wake_live_regression.py: keyword texts (the golden texts of src/phrases.rs and of
docs/evidence/wake-phrases.json), the sensitivity mapping, the 2 s cooldown, stream rotation and attribution.
A fake engine with the attributes `run_stream` reads stands in for the spotter, so no model and no clip is needed."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wake_live_regression as r  # noqa: E402

GOLDEN_DEFAULT = (
    'HH EY1 G IH1 D IY0 AH0 N :1.2 #0.22 @HEY_GIDEON\n'
    'OW2 K EY1 G IH1 D IY0 AH0 N @OKAY_GIDEON\n'
    'HH AY1 G IH1 D IY0 AH0 N @REJECT_HI\n'
)
GOLDEN_PACKAGED = (
    'HH EY1 G IH1 D IY0 AH0 N @HEY_GIDEON\n'
    'OW2 K EY1 G IH1 D IY0 AH0 N @OKAY_GIDEON\n'
    'HH AY1 G IH1 D IY0 AH0 N @REJECT_HI\n'
)


class FakeEngine:
    """One frame = 320 samples = 20 ms. Fires at the given frame indices; rotates at the given frame indices."""

    def __init__(self, fire_frames=(), rotate_frames=()):
        self.fire = set(fire_frames)
        self.rotate = set(rotate_frames)
        self.last_end = 0
        self.stream_start_us = 0
        self.frame = 0

    def warm_up(self, samples=0):
        self.stream_start_us -= samples * 1_000_000 // 16000

    def accept(self, samples, timestamp_us):
        assert timestamp_us == self.last_end
        self.last_end += len(samples) * 1_000_000 // 16000
        events = []
        if self.frame in self.fire:
            events.append({'phrase_id': 'hey_gideon', 'end_us': self.last_end})
        if self.frame in self.rotate:
            self.stream_start_us = self.last_end
        self.frame += 1
        return events


class KeywordTextTests(unittest.TestCase):
    def test_default_is_the_golden_text_of_the_core_default(self):
        text, global_threshold = r.keyword_text('default', 1.0)
        self.assertEqual(text, GOLDEN_DEFAULT)
        self.assertEqual(global_threshold, 0.25)

    def test_packaged_is_the_golden_text_without_options(self):
        text, global_threshold = r.keyword_text('packaged', 1.0)
        self.assertEqual(text, GOLDEN_PACKAGED)
        self.assertEqual(global_threshold, 0.25)

    def test_sensitivity_moves_the_phrase_and_the_global_threshold_on_the_same_scale(self):
        text, global_threshold = r.keyword_text('default', 0.5)
        self.assertIn('HH EY1 G IH1 D IY0 AH0 N :1.2 #0.33 @HEY_GIDEON', text)
        self.assertEqual(global_threshold, 0.375)
        text, global_threshold = r.keyword_text('default', 1.5)
        self.assertIn(':1.2 #0.11 @HEY_GIDEON', text)
        self.assertEqual(global_threshold, 0.125)

    def test_phrase_line_variants(self):
        hey_only, _ = r.keyword_text('hey-only', 1.0)
        self.assertEqual(hey_only.count('@'), 1)
        variant, _ = r.keyword_text('variant', 1.0)
        self.assertEqual(variant.count('@HEY_GIDEON'), 2)
        self.assertIn('HH EY1 G IH1 D IY0 N :1.2 #0.22 @HEY_GIDEON', variant)

    def test_threshold_override_targets_the_phrase_line_or_the_global_one(self):
        text, global_threshold = r.keyword_text('default', 1.0, threshold_override=0.18)
        self.assertIn('#0.18 @HEY_GIDEON', text)
        self.assertEqual(global_threshold, 0.25)
        _, global_threshold = r.keyword_text('packaged', 1.0, threshold_override=0.18)
        self.assertEqual(global_threshold, 0.18)


class StreamTests(unittest.TestCase):
    def test_second_detection_within_two_seconds_is_dropped_by_the_cooldown(self):
        engine = FakeEngine(fire_frames=(10, 60, 200))
        cell = r.Cell(warm_up_s=0.0)
        detections, dropped, rotations = r.run_stream(engine, np.zeros(201 * 320, dtype=np.int16), cell, False)
        self.assertEqual(detections, [220_000 * 16000 // 1_000_000, 4_020_000 * 16000 // 1_000_000])
        self.assertEqual(dropped, [1_220_000 * 16000 // 1_000_000])
        self.assertEqual(rotations, [])

    def test_rotation_and_warm_up_are_reported_on_the_core_clock(self):
        engine = FakeEngine(rotate_frames=(5,))
        cell = r.Cell(warm_up_s=3.0)
        _, _, rotations = r.run_stream(engine, np.zeros(10 * 320, dtype=np.int16), cell, False)
        self.assertEqual(rotations, [6 * 20_000 * 16000 // 1_000_000])
        self.assertEqual(engine.stream_start_us, 6 * 20_000 - 0)

    def test_attribution_separates_hits_gaps_and_negatives(self):
        windows = [
            {'id': 'p', 'expect': True, 'start': 1000, 'end': 2000},
            {'id': 'n', 'expect': False, 'start': 50_000, 'end': 52_000},
        ]
        tail = int(r.TAIL_S * r.RATE)
        detections = [1500, 2000 + tail - 1, 2000 + tail + 500, 51_000]
        rows, gap = r.attribute(windows, detections)
        self.assertTrue(rows[0]['triggered'])
        self.assertEqual(rows[0]['latency_ms'], round(500 * 1000 / r.RATE))
        self.assertTrue(rows[1]['triggered'])
        self.assertEqual(gap, [2000 + tail + 500])


class BuildStreamTests(unittest.TestCase):
    def test_clip_windows_follow_the_live_spacing(self):
        clips = [{'id': 'a', 'expect_wake': True}, {'id': 'b', 'expect_wake': False}]
        samples = {'a': np.ones(16000, dtype=np.int16), 'b': np.ones(8000, dtype=np.int16)}
        stream, windows = r.build_stream(clips, samples, repeat=0)
        lead = int(r.LEAD_S * r.RATE)
        self.assertEqual(windows[0]['start'], lead)
        self.assertEqual(windows[1]['start'], lead + 16000 + int((r.TAIL_S + r.GAP_S) * r.RATE))
        self.assertEqual(len(stream), windows[1]['end'] + int((r.TAIL_S + r.GAP_S) * r.RATE))


if __name__ == '__main__':
    unittest.main()
