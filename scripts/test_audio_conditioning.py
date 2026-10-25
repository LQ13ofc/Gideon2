#!/usr/bin/env python3
"""Offline numeric tests of the wake input conditioning (scripts/audio_conditioning.py). Synthetic signals only."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audio_conditioning import AUTO_CHAIN, FRAME, OFF, Conditioner, Config, named  # noqa: E402

RATE = 16000


def tone(hz, seconds, amplitude, offset=0.0):
    t = np.arange(int(seconds * RATE)) / RATE
    return (offset + amplitude * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def run(config, samples):
    conditioner = Conditioner(config)
    out = [conditioner.process(samples[i:i + FRAME]) for i in range(0, len(samples) - FRAME + 1, FRAME)]
    return np.concatenate(out)


def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-12)


class ConditioningTests(unittest.TestCase):
    def test_off_is_the_identity(self):
        x = tone(440, 0.5, 0.2)
        np.testing.assert_array_equal(run(OFF, x), x)

    def test_frames_must_be_twenty_milliseconds(self):
        with self.assertRaises(ValueError):
            Conditioner(AUTO_CHAIN).process(np.zeros(FRAME - 1, dtype=np.float32))

    def test_auto_chain_is_the_high_pass_only_winner(self):
        self.assertEqual(AUTO_CHAIN, Config(hpf=True))
        self.assertEqual(named('hpf'), AUTO_CHAIN)

    def test_high_pass_removes_dc_and_rumble_and_keeps_speech_band(self):
        x = tone(30, 2.0, 0.3, offset=0.2) + tone(1000, 2.0, 0.3)[: 2 * RATE]
        y = run(AUTO_CHAIN, x)
        settled = y[RATE:]
        rumble_only = run(AUTO_CHAIN, tone(30, 2.0, 0.3, offset=0.2))[RATE:]
        self.assertLess(rms_db(rumble_only), -25.0)  # 30 Hz and DC: more than 25 dB down
        speech = run(AUTO_CHAIN, tone(1000, 2.0, 0.3))[RATE:]
        self.assertLess(abs(rms_db(speech) - rms_db(tone(1000, 1.0, 0.3))), 1.0)
        self.assertLess(abs(float(settled.mean())), 1e-3)

    def test_high_pass_group_delay_is_eight_milliseconds_or_less(self):
        # A click at sample 0 should peak near the 128-sample centre of the linear-phase FIR.
        x = np.zeros(4 * FRAME, dtype=np.float32)
        x[FRAME] = 0.5
        y = run(Config(hpf=True), x)
        self.assertLessEqual(abs(int(np.argmax(np.abs(y))) - FRAME - 128), 2)

    def test_agc_reaches_the_target_and_caps_the_gain(self):
        quiet = tone(1000, 4.0, 0.01)  # about -43 dBFS RMS
        y = run(Config(agc=True), quiet)
        self.assertLess(abs(rms_db(y[3 * RATE:]) - (-23.0)), 1.5)
        very_quiet = tone(1000, 4.0, 0.0001)  # -83 dBFS: +24 dB cap, the output stays well below the target
        z = run(Config(agc=True), very_quiet)
        self.assertLessEqual(rms_db(z[3 * RATE:]) - rms_db(very_quiet[3 * RATE:]), 24.5)

    def test_gate_attenuates_the_floor_and_passes_speech(self):
        floor = (np.random.default_rng(3).standard_normal(3 * RATE) * 0.003).astype(np.float32)  # about -50 dBFS
        loud = (np.random.default_rng(4).standard_normal(RATE) * 0.1).astype(np.float32)  # about -20 dBFS
        x = np.concatenate([floor, loud])
        y = run(Config(gate=True), x)
        floor_gain = rms_db(y[2 * RATE:3 * RATE]) - rms_db(x[2 * RATE:3 * RATE])
        speech_gain = rms_db(y[3 * RATE + 2000:]) - rms_db(x[3 * RATE + 2000:])
        self.assertLessEqual(floor_gain, -5.0)
        self.assertGreater(speech_gain, -1.0)

    def test_noise_suppression_lowers_stationary_noise(self):
        noise = (np.random.default_rng(5).standard_normal(6 * RATE) * 0.03).astype(np.float32)
        y = run(Config(ns=True), noise)
        self.assertLessEqual(rms_db(y[3 * RATE:]) - rms_db(noise[3 * RATE:]), -3.0)

    def test_pre_emphasis_passes_a_step_as_a_short_pulse(self):
        x = np.full(2 * FRAME, 0.5, dtype=np.float32)
        y = run(Config(preemph=True), x)
        self.assertAlmostEqual(float(y[0]), 0.5, places=5)
        self.assertLess(abs(float(y[FRAME + 10]) - 0.5 * (1 - 0.97)), 1e-4)

    def test_every_chain_stays_finite_and_bounded(self):
        rng = np.random.default_rng(9)
        x = np.clip(rng.standard_normal(4 * RATE) * 0.5, -1, 1).astype(np.float32)
        for name in ('hpf', 'hpf_agc', 'hpf_agc_gate', 'hpf_ns_agc_gate', 'hpf_agc_gate_preemph'):
            with self.subTest(chain=name):
                y = run(named(name), x)
                self.assertTrue(np.isfinite(y).all())
                self.assertLessEqual(float(np.max(np.abs(y))), 1.0)


if __name__ == '__main__':
    unittest.main()
