#!/usr/bin/env python3
"""Integration through a real native KWS worker and Rust owner; no device adapters."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

BASE = Path(__file__).resolve().parents[1]
BINARY = BASE/'target/release/gideon-base'
PYTHON = BASE/'target/a1-venv/bin/python'
MANIFEST = BASE/'target/a1-competitive/manifest.json'


def run():
    checks = []
    def check(name, value, context=None):
        if not value: raise AssertionError(name + (" " + json.dumps(context) if context is not None else ""))
        checks.append(name)
    m = json.loads(MANIFEST.read_text())
    positive = next(i for i,r in enumerate(m['fixtures']) if r['id']=='wake-hey__bf_emma__clean')
    confusables = [next(i for i,r in enumerate(m['fixtures']) if r['id']==name) for name in ('wake-okay__bf_emma__clean','negative-hi-gideon__bf_emma__clean')]
    negative = next(i for i,r in enumerate(m['fixtures']) if r['id']=='ordinary-unrelated__bf_emma__clean')
    def scenario(index, bad=False, early=False, active_phrase=None):
        with tempfile.TemporaryDirectory(prefix='gideon-a1-') as td:
            home = Path(td); root = home/'core'; home.chmod(0o700)
            if active_phrase:
                root.mkdir(mode=0o700)
                config=root/'config.json';config.write_text(json.dumps({'version':1,'session_timeout_ms':30000,'wake_phrase':active_phrase}));config.chmod(0o600)
            env = {'PATH' :'/usr/bin:/bin','HOME':td,'XDG_CONFIG_HOME':str(home/'config'),'XDG_DATA_HOME':str(home/'data'),'XDG_CACHE_HOME':str(home/'cache'),'XDG_RUNTIME_DIR':td,'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
            manifest = MANIFEST
            if bad:
                altered = dict(m); altered['hashes'] = dict(m['hashes']); altered['hashes']['tokens.txt'] = '0'*64
                manifest=home/'bad.json';manifest.write_text(json.dumps(altered))
            p = subprocess.Popen([str(BINARY),'--root',str(root),'--wake-replay',str(PYTHON),str(manifest),str(index)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            s = None
            try:
                deadline=time.monotonic()+3
                while not (root/'core.sock').exists():
                    if p.poll() is not None: raise RuntimeError(p.stderr.read().decode())
                    if time.monotonic()>deadline: raise TimeoutError('startup')
                    time.sleep(.01)
                s=socket.socket(socket.AF_UNIX);s.settimeout(2);s.connect(str(root/'core.sock'))
                f=s.makefile('rb');counter=0
                def request(op='snapshot',**kwargs):
                    nonlocal counter
                    counter+=1
                    s.sendall((json.dumps({'version':1,'request_id':f'r{counter}','op':op,**kwargs})+'\n').encode())
                    return json.loads(f.readline())
                if early:
                    child = None; until = time.monotonic()+3
                    while time.monotonic()<until:
                        children=Path(f'/proc/{p.pid}/task/{p.pid}/children').read_text().split()
                        if children: child=int(children[0]);break
                        time.sleep(.01)
                    check('worker spawned as owned child',child is not None)
                    os.kill(child,9)
                until=time.monotonic()+15;wake=None;last=None;max_rss=0
                while time.monotonic()<until:
                    last=request()
                    max_rss=max(max_rss,int(Path(f'/proc/{p.pid}/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE'))
                    started=[e for e in last['events'] if e['kind']=='session_started']
                    if started and wake is None:
                        wake=started[0];sid=last['session_id']
                        check('real PCM wake correlated session',wake['session_id']==sid and wake['request_id'].startswith('wake_'))
                        check('real wake action denied',request('action',session_id=sid,capability='open_app')['code']=='denied')
                        check('cancel native-wake session',request('cancel',session_id=sid)['code']=='ok')
                        check('late result fenced',request('action',session_id=sid,capability='open_app')['code']=='stale_session')
                    if last['wake_status'] in ('failed','replay_finished'):break
                    time.sleep(.03)
                if bad or early:
                    check('hash or worker exit fail closed',last['wake_status']=='failed' and not started and last['state']=='idle',{'bad':bad,'early':early,'wake_status':last['wake_status'],'state':last['state'],'events':last['events']})
                    check('worker failure observable',any(e['kind']=='wake_failed' for e in last['events']))
                elif m['fixtures'][index]['positive'] or active_phrase=='okay_gideon':
                    check('one session per wake PCM',len(started)==1 and wake is not None)
                    check('replay completed honestly',last['wake_status']=='replay_finished')
                    check('cancel remains terminal after late frames',last['state']=='idle')
                else:
                    check('negative PCM creates no session',not started and last['wake_status']=='replay_finished')
                check('owner responsive and bounded',max_rss<32*1024*1024)
                p.terminate();check('shutdown joins worker',p.wait(timeout=3)==0)
                check('private socket cleanup',not (root/'core.sock').exists())
                return max_rss
            finally:
                if s:s.close()
                if p.poll() is None:p.terminate();p.wait(timeout=3)
                p.stderr.close()
    with tempfile.TemporaryDirectory(prefix='gideon-a1-unknown-') as td:
        root=Path(td)/'core';root.mkdir(mode=0o700)
        config=root/'config.json';config.write_text(json.dumps({'version':1,'session_timeout_ms':30000,'wake_phrase':'unknown_phrase'}));config.chmod(0o600)
        result=subprocess.run([str(BINARY),'--root',str(root),'--wake-replay',str(PYTHON),str(MANIFEST),str(positive)],env={'HOME':td,'PATH':'/usr/bin:/bin'},capture_output=True,timeout=3)
        check('unsupported configured phrase fails startup without altering config',result.returncode!=0 and json.loads(config.read_text())['wake_phrase']=='unknown_phrase')
    rss=[scenario(positive),scenario(negative),*[scenario(i) for i in confusables],scenario(positive,bad=True),scenario(positive,early=True),scenario(confusables[0],active_phrase="okay_gideon")]
    return {'gate':'A1_INTEGRATION_ONLY','passed':len(checks),'checks':checks,'failed':0,'ignored':0,'max_core_rss_bytes':max(rss),'binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest(),'manifest_sha256':hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),'scope':'real CPU inference PCM replay into Rust Core; isolated HOME/XDG; no physical audio; corpus quality gate separate'}

if __name__=='__main__':
    result=run();(BASE/'target/evidence/a1-integration.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
