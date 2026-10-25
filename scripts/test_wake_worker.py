#!/usr/bin/env python3
"""Real native worker regressions on authorized PCM; no mocked inference."""
import hashlib
import json
from pathlib import Path
import unittest
import numpy as np
from wake_worker import WakeEngine, read_fixture

BASE=Path(__file__).resolve().parents[1]
MANIFEST=BASE/'target/a1-competitive/manifest.json'


class NativeWakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads(MANIFEST.read_text())
        cls.row=next(r for r in cls.manifest['fixtures'] if r['id']=='wake-hey__bf_emma__clean')
    def test_warm_up_keeps_the_core_clock_and_emits_nothing(self):
        # Live priming is silence on the stream only: packet clock and detection mapping stay on the Core clock.
        engine=WakeEngine(self.manifest,start_us=7_000_000)
        engine.warm_up()
        self.assertEqual(engine.last_end,7_000_000)
        self.assertEqual(engine.stream_start_us,7_000_000-3_000_000)
        self.assertEqual(len(engine.recent),0)
        events=engine.accept(np.zeros(320,dtype=np.float32),7_000_000)
        self.assertEqual(events,[])
        self.assertEqual(engine.last_end,7_020_000)
    def test_pcm_crosses_stream_rotation_boundary(self):
        engine=WakeEngine(self.manifest)
        samples=np.concatenate([np.zeros(9*16000,dtype=np.float32),read_fixture(self.row),np.zeros(16000,dtype=np.float32)])
        events=[]
        for offset in range(0,len(samples),1280):
            events+=engine.accept(samples[offset:offset+1280],offset*1000000//16000)
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['phrase_id'],'hey_gideon')
        self.assertGreater(events[0]['start_us'],9_000_000)
        self.assertLess(events[0]['start_us'],events[0]['end_us'])
        self.assertLessEqual(sum(len(a) for _,a in engine.recent),32000)
    def test_rejection_classes_never_emit_wake(self):
        engine=WakeEngine(self.manifest)
        for name in ('wake-okay__bf_emma__clean','negative-hi-gideon__bf_emma__clean'):
            engine.reset()
            row=next(r for r in self.manifest['fixtures'] if r['id']==name)
            samples=np.concatenate([read_fixture(row),np.zeros(16000,dtype=np.float32)])
            events=[]
            for offset in range(0,len(samples),1280):
                events+=engine.accept(samples[offset:offset+1280],offset*1000000//16000)
            self.assertEqual(events,[],name)
        self.assertEqual(engine.supported_phrases,('hey_gideon','okay_gideon'))
    def test_phrase_selection_uses_catalog(self):
        manifest=dict(self.manifest);manifest['active_phrase']='okay_gideon'
        engine=WakeEngine(manifest)
        row=next(r for r in manifest['fixtures'] if r['id']=='wake-okay__bf_emma__clean')
        samples=np.concatenate([read_fixture(row),np.zeros(16000,dtype=np.float32)])
        events=[]
        for offset in range(0,len(samples),1280):
            events+=engine.accept(samples[offset:offset+1280],offset*1000000//16000)
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['phrase_id'],'okay_gideon')
        manifest['active_phrase']='not_supported'
        with self.assertRaises(ValueError):WakeEngine(manifest)
    def test_hashes_required_before_inference(self):
        bad=dict(self.manifest);bad['hashes']=dict(bad['hashes']);bad['hashes'].pop('tokens.txt')
        with self.assertRaises(ValueError):WakeEngine(bad)
        bad['hashes']=dict(self.manifest['hashes']);bad['hashes']['tokens.txt']='0'*64
        with self.assertRaises(ValueError):WakeEngine(bad)
    def test_invalid_pcm_cannot_advance_clock(self):
        engine=WakeEngine(self.manifest)
        for samples,stamp in [(np.array([np.nan]),0),(np.zeros(1281),0),(np.zeros(1280),1)]:
            with self.assertRaises(ValueError):engine.accept(samples,stamp)
        self.assertEqual(engine.last_end,0)
        self.assertEqual(engine.accept(np.zeros(1280),0),[])


if __name__=='__main__':unittest.main()
