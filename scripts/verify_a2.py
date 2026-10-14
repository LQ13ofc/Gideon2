#!/usr/bin/env python3
"""Real KWS→Silero→Core capture and independent PCM byte comparison."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wake_worker import read_fixture, np

BASE=Path(__file__).resolve().parents[1]
BINARY=BASE/'target/release/gideon-base'
PYTHON=BASE/'target/a1-venv/bin/python'
MANIFEST=BASE/'target/a2-assets/replay-manifest.json'


def run():
    manifest=json.loads(MANIFEST.read_text());checks=[];max_rss=0
    def check(name,value):
        if not value:raise AssertionError(name)
        checks.append(name)
    def scenario(cancel=False,bad_vad=False,kill_producer=False):
        nonlocal max_rss
        index=next(i for i,r in enumerate(manifest['fixtures']) if r['id']=='wake-hey-brave__bf_emma__clean')
        row=manifest['fixtures'][index]
        source=np.concatenate([read_fixture(row),np.zeros(16000,dtype=np.float32)])
        with tempfile.TemporaryDirectory(prefix='gideon-a2-') as td:
            root=Path(td)/'core';env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td,'XDG_RUNTIME_DIR':td,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
            path=MANIFEST
            if bad_vad:
                m=dict(manifest);m['vad']=dict(m['vad']);m['vad']['sha256']='0'*64
                path=Path(td)/'invalid-vad.json';path.write_text(json.dumps(m))
            process=subprocess.Popen([str(BINARY),'--root',str(root),'--wake-replay',str(PYTHON),str(path),str(index)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            s=None
            try:
                until=time.monotonic()+3
                while not (root/'core.sock').exists():
                    if process.poll() is not None:raise RuntimeError(process.stderr.read().decode())
                    if time.monotonic()>until:raise TimeoutError('startup')
                    time.sleep(.01)
                s=socket.socket(socket.AF_UNIX);s.settimeout(2);s.connect(str(root/'core.sock'));file=s.makefile('rb');counter=0
                def req(op='snapshot',**kwargs):
                    nonlocal counter
                    counter+=1;s.sendall((json.dumps({'version':1,'request_id':f'q{counter}','op':op,**kwargs})+'\n').encode());return json.loads(file.readline())
                wake=None;summary=None;until=time.monotonic()+10
                while time.monotonic()<until:
                    snap=req();max_rss=max(max_rss,int(Path(f'/proc/{process.pid}/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE'))
                    started=[e for e in snap['events'] if e['kind']=='session_started']
                    if started and wake is None:
                        wake=started[0];sid=wake['session_id']
                        check('capture action remains denied',req('action',session_id=sid,capability='open_app')['code']=='denied')
                        if kill_producer:
                            children=Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()
                            check('capture producer owned by Core',bool(children));os.kill(int(children[0]),9)
                        if cancel:
                            check('cancel live capture',req('cancel',session_id=sid)['code']=='ok')
                    if snap['capture']:summary=snap['capture']
                    if snap['wake_status'] in ('failed','replay_finished'):break
                    time.sleep(.02)
                if bad_vad:
                    check('VAD integrity failure produces no wake/capture',snap['wake_status']=='failed' and not started and summary is None)
                else:
                    check('one real wake correlated capture',len(started)==1 and summary['session_id']==wake['session_id'])
                    check('cancel or endpoint terminal',summary['reason']==('cancelled' if cancel or kill_producer else 'capture_completed') and snap['state']=='idle')
                    first=summary['start_us']*16000//1_000_000
                    last=first+summary['samples']
                    expected=hashlib.sha256(source[first:last].astype('<f4').tobytes()).hexdigest()
                    check('pre-roll and all capture PCM preserved byte for byte',expected==summary['pcm_sha256'])
                    check('pre-roll precedes wake handoff',summary['start_us']<1_280_000 and summary['samples']>=16000)
                    check('capture bounded to thirty seconds',summary['samples']<=480000)
                    check('late action fenced',req('action',session_id=summary['session_id'],capability='open_app')['code']=='stale_session')
                check('no raw voice files persisted',set(p.name for p in root.iterdir())=={'core.sock','core.lock','config.json','audit.log'})
                process.terminate();check('capture shutdown and socket cleanup',process.wait(timeout=3)==0 and not (root/'core.sock').exists())
            finally:
                if s:s.close()
                if process.poll() is None:process.terminate();process.wait(timeout=3)
                process.stderr.close()
    scenario();scenario(cancel=True);scenario(bad_vad=True);scenario(kill_producer=True)
    check('capture Core RSS below 32MiB',max_rss<32*1024*1024)
    return {'gate':'A2','passed':len(checks),'failed':0,'ignored':0,'checks':checks,'max_core_rss_bytes':max_rss,'binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest(),'manifest_sha256':hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),'physical_validation':'NOT_PERFORMED','scope':'real native KWS/Silero inference in namespace; authorized PCM→Core capture SHA256 exact; no devices/actions'}

if __name__=='__main__':
    result=run();(BASE/'target/evidence/a2.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
