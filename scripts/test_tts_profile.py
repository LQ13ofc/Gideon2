#!/usr/bin/env python3
"""Artifact preflight contracts; actual Pocket PCM tested by verify_a5."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tts_worker import load_profile
BASE=Path(__file__).resolve().parents[1]
class Tests(unittest.TestCase):
    def test_real_pinned_profile(self):self.assertEqual(load_profile(BASE/'target/a5-assets/manifest.json')['engine'],'pocket-tts-3.3.0/english_2026-09/cpu')
    def test_missing_duplicate_traversal_wrong_engine_and_unpinned_path(self):
        original=json.loads((BASE/'target/a5-assets/manifest.json').read_text())
        mutants=[]
        for name in ('empty','duplicate','traversal','engine','config','voice'):
            cfg=copy.deepcopy(original)
            if name=='empty':cfg['artifacts']=[]
            elif name=='duplicate':cfg['artifacts'][0]=cfg['artifacts'][1]
            elif name=='traversal':cfg['artifacts'][0]['name']='../model.safetensors'
            elif name=='engine':cfg['engine']='unknown'
            elif name=='config':cfg['config']='https://example.invalid/config.yaml'
            else:cfg['voice']='/tmp/unpinned.safetensors'
            mutants.append((name,cfg))
        with tempfile.TemporaryDirectory() as td:
            for name,cfg in mutants:
                path=Path(td)/'profile.json';path.write_text(json.dumps(cfg))
                with self.subTest(name=name),self.assertRaises(ValueError):load_profile(path)
if __name__=='__main__':unittest.main()
