#!/usr/bin/env python3
"""Adversarial SDK callbacks; native streaming remains covered by verify_a3/a5."""
import io,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stt_worker as worker
BASE=Path(__file__).resolve().parents[1]
class Stream:
    previous=None
    error=False
    def add_listener(self,listener):self.listener=listener
    def start(self):pass
    def close(self):Stream.previous=self.listener
    def add_audio(self,*args):
        if Stream.previous:Stream.previous(SimpleNamespace(line=SimpleNamespace(line_id=88,text='open brave'),error=None))
        self.listener(SimpleNamespace(line=SimpleNamespace(line_id=1,text='status'),error='fault' if Stream.error else None))
    def stop(self):return SimpleNamespace(lines=[SimpleNamespace(text='status')])
class Transcriber:
    def __init__(self,*args,**kwargs):pass
    def create_stream(self,**kwargs):return Stream()
    def close(self):pass
class Tests(unittest.TestCase):
    def execute(self,error=False):
        Stream.previous=None;Stream.error=error
        requests=[]
        for sid in (1,2):requests += [{'op':'start','session_id':sid},{'op':'frame','session_id':sid,'end_us':80000,'samples':[.1]*1280},{'op':'finish','session_id':sid}]
        fake_input=SimpleNamespace(buffer=io.BytesIO(('\n'.join(map(json.dumps,requests))+'\n').encode()));out=io.StringIO()
        with patch.object(worker,'Transcriber',Transcriber),patch.object(worker.sys,'stdin',fake_input),patch.object(worker.sys,'stdout',out):worker.run(json.loads((BASE/'target/a3-assets/manifest.json').read_text()))
        return [json.loads(line) for line in out.getvalue().splitlines()]
    def test_callback_from_closed_stream_cannot_borrow_new_session(self):
        replies=self.execute();self.assertEqual([r['raw'] for r in replies if r['op']=='partial'],['status','status']);self.assertEqual([r['session_id'] for r in replies if r['op']=='final'],[1,2])
    def test_native_callback_error_is_visible_to_strict_owner_protocol(self):
        self.assertTrue(any(r['op']=='error' for r in self.execute(error=True)))
if __name__=='__main__':unittest.main()
