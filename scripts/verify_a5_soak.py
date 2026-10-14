#!/usr/bin/env python3
"""Bounded continuous PCM replay: two voice cycles and idle CPU in one owner process."""
from process_fixture import resident_bytes
import hashlib,json,os,socket,subprocess,tempfile,time
from pathlib import Path
import numpy as np,soundfile as sf
from pcm_fixture import read_fixture
BASE=Path(__file__).resolve().parents[1]
BIN=BASE/'target/release/gideon-base';MANIFEST=BASE/'target/a3-assets/replay-manifest.json'
m=json.loads(MANIFEST.read_text());row=next(r for r in m['fixtures'] if r['id']=='wake-hey-brave__bf_emma__clean')
audio=read_fixture(row);source=np.concatenate([audio,np.zeros(16000*20,dtype=np.float32),audio,np.zeros(16000*14,dtype=np.float32)])
asset=BASE/'target/a5-assets/soak.wav';sf.write(asset,source,16000,subtype='FLOAT')
fixture={'id':'a5-two-cycles-emma','path':str(asset),'sha256':hashlib.sha256(asset.read_bytes()).hexdigest(),'positive':True,'expected_wake_phrase':'hey_gideon'}
m['fixtures']=[fixture];path=BASE/'target/a5-assets/soak-replay.json';path.write_text(json.dumps(m))
checks=[]
def check(name,value):
    if not value:raise AssertionError(name)
    checks.append(name)
with tempfile.TemporaryDirectory(prefix='gideon-a5-soak-') as td:
    root=Path(td)/'core';env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td,'XDG_RUNTIME_DIR':td,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
    p=subprocess.Popen([str(BIN),'--root',str(root),'--commands-sandbox','--tts-virtual',str(BASE/'target/tts-venv/bin/python'),str(BASE/'target/a5-assets/manifest.json'),'--wake-replay',str(BASE/'target/a1-venv/bin/python'),str(path),'0'],env=env,stderr=subprocess.PIPE);s=None
    try:
        until=time.monotonic()+3
        while not (root/'core.sock').exists():
            if p.poll() is not None:raise RuntimeError(p.stderr.read().decode())
            if time.monotonic()>until:raise TimeoutError('startup')
            time.sleep(.01)
        s=socket.socket(socket.AF_UNIX);s.settimeout(2);s.connect(str(root/'core.sock'));f=s.makefile('rb');counter=0
        def req():
            global counter
            counter+=1;s.sendall((json.dumps({'version':1,'request_id':f's{counter}','op':'snapshot'})+'\n').encode());return json.loads(f.readline())
        until=time.monotonic()+70;completed={}
        while time.monotonic()<until:
            snap=req()
            if snap['speech']:completed[snap['speech']['session_id']]=snap['speech']
            if snap['wake_status']=='replay_finished' and snap['state']=='idle':break
            time.sleep(.02)
        check('two sessions completed through PCM sink',len(completed)==2)
        check('one effect and speech per session',sum(e['kind']=='command_success' for e in snap['events'])==2 and sum(e['kind']=='speech_completed' for e in snap['events'])==2)
        check('source EOF, no failed or timed-out cycle',snap['wake_status']=='replay_finished' and not any(e['kind'] in ('tts_failed','command_failed','timed_out','audio_error') for e in snap['events']))
        check('session IDs distinct and PCM identity bounded',all(0<r['samples']<=240000 for r in completed.values()))
        def stats():
            owned={p.pid};pending=[p.pid];ticks=0;rss=0
            while pending:
                current=pending.pop()
                try:children=Path(f'/proc/{current}/task/{current}/children').read_text().split()
                except (FileNotFoundError,ProcessLookupError):continue
                for x in children:
                    child=int(x)
                    if child not in owned:owned.add(child);pending.append(child)
            for pid in owned:
                try:
                    fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split();ticks+=int(fields[11])+int(fields[12]);rss+=resident_bytes(pid)
                except (FileNotFoundError,ProcessLookupError):pass
            return ticks,rss
        ticks0,rss0=stats();start=time.monotonic();time.sleep(2);ticks1,rss1=stats();cpu=100*(ticks1-ticks0)/os.sysconf('SC_CLK_TCK')/(time.monotonic()-start)
        check('post EOF idle CPU below one percent',cpu<1.)
        check('loaded STT after speech unload below one GiB',max(rss0,rss1)<1024**3)
        check('no runtime speech artifacts',set(x.name for x in root.iterdir())=={'core.sock','core.lock','config.json','audit.log'})
        p.terminate();check('continuous pipeline shuts down',p.wait(timeout=3)==0)
        result={'gate':'A5_BOUNDED_SOAK','passed':len(checks),'failed':0,'ignored':0,'checks':checks,'fixture':fixture,'source_fixture_sha256':row['sha256'],'transformation':'two authorized PCM clips, 20s inter-cycle and 14s trailing silence; DEV interpolation from pcm_fixture helper','source_samples':len(source),'cycles':list(completed.values()),'idle_cpu_percent_one_core':cpu,'idle_sum_rss_bytes':max(rss0,rss1),'resource_scope':'recursive owned process RSS sums shared pages, post fixture EOF, STT loaded and TTS workers exited','binary_sha256':hashlib.sha256(BIN.read_bytes()).hexdigest(),'physical_validation':'NOT_PERFORMED'}
        (BASE/'target/evidence/a5-soak.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    finally:
        if s:s.close()
        if p.poll() is None:p.terminate();p.wait(timeout=3)
        p.stderr.close()
