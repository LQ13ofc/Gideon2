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
    def test_core_keyword_set_boosts_one_phrase_and_names_several_active(self):
        # src/phrases.rs writes the keyword file (boost/threshold per line) and a runtime manifest with `keywords_file`.
        import tempfile,hashlib
        with tempfile.TemporaryDirectory() as td:
            keywords=Path(td)/'keywords.txt'
            text=('HH EY1 G IH1 D IY0 AH0 N :1.2 #0.22 @HEY_GIDEON\n'
                  'OW2 K EY1 G IH1 D IY0 AH0 N @OKAY_GIDEON\nHH AY1 G IH1 D IY0 AH0 N @REJECT_HI\n')
            keywords.write_text(text)
            manifest=dict(self.manifest);manifest['keywords_file']=str(keywords)
            manifest['hashes']=dict(self.manifest['hashes'],**{'keywords.txt':hashlib.sha256(text.encode()).hexdigest()})
            manifest['active_phrases']=['hey_gideon'];manifest['active_phrase']='hey_gideon'
            engine=WakeEngine(manifest)
            self.assertEqual(engine.active_phrases,('hey_gideon',))
            row=next(r for r in manifest['fixtures'] if r['id']=='wake-hey__bf_emma__clean')
            samples=np.concatenate([read_fixture(row),np.zeros(16000,dtype=np.float32)])
            events=[]
            for offset in range(0,len(samples),1280):events+=engine.accept(samples[offset:offset+1280],offset*1000000//16000)
            self.assertEqual([e['phrase_id'] for e in events],['hey_gideon'])
            # A keyword line whose label is not declared, or a malformed option, stops the worker before any frame.
            def rewrite(body):
                # Same hash discipline as the Core: the manifest digests the keyword file it names.
                keywords.write_text(body);manifest['hashes']=dict(self.manifest['hashes'],**{'keywords.txt':hashlib.sha256(body.encode()).hexdigest()})
            rewrite(text.replace('@REJECT_HI','@OTHER'))
            with self.assertRaises(ValueError):WakeEngine(manifest)
            rewrite(text.replace(':1.2',':99'))
            with self.assertRaises(ValueError):WakeEngine(manifest)
            rewrite(text.replace('#0.22','#2'))
            with self.assertRaises(ValueError):WakeEngine(manifest)
            manifest['active_phrases']=['hey_gideon','okay_gideon'];rewrite(text)
            self.assertEqual(WakeEngine(manifest).active_phrases,('hey_gideon','okay_gideon'))
            manifest['active_phrases']=['hey_gideon','not_supported']
            with self.assertRaises(ValueError):WakeEngine(manifest)


class ConditionedLiveTests(unittest.TestCase):
    """The live loop hands the spotter conditioned frames; the Core packets keep the raw frames."""
    class Spy:
        def __init__(self):
            self.last_end=0;self.heard=[]
        def accept(self,samples,timestamp):
            self.heard.append(np.array(samples,copy=True));self.last_end+=len(samples)*1000000//16000
            return []
        frame_samples=WakeEngine.frame_samples

    def run_live(self,conditioner):
        import io
        from wake_worker import live
        engine=self.Spy()
        raw=b''.join(int(v).to_bytes(2,'little',signed=True) for v in np.full(320*60,6553,dtype=np.int64))  # DC 0.2
        out=io.StringIO()
        live(engine,None,io.BytesIO(raw),out,conditioner)
        packets=[json.loads(line) for line in out.getvalue().splitlines()]
        return engine,packets

    def test_spotter_hears_conditioned_frames_and_packets_keep_raw_samples(self):
        from audio_conditioning import AUTO_CHAIN,Conditioner
        engine,packets=self.run_live(Conditioner(AUTO_CHAIN))
        self.assertAlmostEqual(float(np.mean(packets[-1]['samples'])),0.2,places=3)  # Core keeps the raw DC
        self.assertLess(abs(float(np.mean(engine.heard[-1]))),1e-3)  # the spotter sees it high-passed
        self.assertEqual(len(engine.heard),60)
    def test_conditioning_off_passes_the_raw_frames(self):
        engine,packets=self.run_live(None)
        self.assertAlmostEqual(float(np.mean(engine.heard[-1])),0.2,places=3)
        self.assertEqual(packets[-1]['timestamp_us'],59*20000)


if __name__=='__main__':unittest.main()
