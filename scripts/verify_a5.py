#!/usr/bin/env python3
"""Offline native wake→STT→verified sandbox action→Pocket PCM→paced virtual sink."""
import hashlib,json,os,socket,subprocess,tempfile,time
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];BIN=BASE/'target/release/gideon-base';WAKE=BASE/'target/a1-venv/bin/python';TTS=BASE/'target/tts-venv/bin/python';MANIFEST=BASE/'target/a3-assets/replay-manifest.json';PROFILE=BASE/'target/a5-assets/manifest.json'
BINARY_ID=hashlib.sha256(BIN.read_bytes()).hexdigest()
def run():
    checks=[];rows=[];manifest=json.loads(MANIFEST.read_text())
    def check(name,passed):
        if not passed:raise AssertionError(name)
        checks.append(name)
    def scenario(voice='bf_emma',mode='normal',fixture=None):
        name=fixture or f'wake-hey-brave__{voice}__clean';index=next(i for i,r in enumerate(manifest['fixtures']) if r['id']==name)
        with tempfile.TemporaryDirectory(prefix='gideon-a5-') as td:
            root=Path(td)/'core';profile=PROFILE
            if mode=='bad_hash':
                cfg=json.loads(PROFILE.read_text());cfg['artifacts'][0]['sha256']='0'*64;profile=Path(td)/'bad-profile.json';profile.write_text(json.dumps(cfg))
            env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td,'XDG_RUNTIME_DIR':td,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
            p=subprocess.Popen([str(BIN),'--root',str(root),'--commands-sandbox','--tts-virtual',str(TTS),str(profile),'--wake-replay',str(WAKE),str(MANIFEST),str(index)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);s=None
            try:
                until=time.monotonic()+3
                while not (root/'core.sock').exists():
                    if p.poll() is not None:raise RuntimeError(p.stderr.read().decode())
                    if time.monotonic()>until:raise TimeoutError('startup')
                    time.sleep(.01)
                s=socket.socket(socket.AF_UNIX);s.settimeout(2);s.connect(str(root/'core.sock'));f=s.makefile('rb');counter=0
                def req(op='snapshot',**kw):
                    nonlocal counter
                    counter+=1;s.sendall((json.dumps({'version':1,'request_id':f's{counter}','op':op,**kw})+'\n').encode());return json.loads(f.readline())
                until=time.monotonic()+40;interrupted=False;seen_speaking=False;start=time.monotonic();peak_rss=0;sid=None
                while time.monotonic()<until:
                    snap=req();sid=snap['session_id'] or sid
                    children=Path(f'/proc/{p.pid}/task/{p.pid}/children').read_text().split();rss=0
                    owned={p.pid};pending=[p.pid]
                    while pending:
                        current=pending.pop()
                        try:descendants=Path(f'/proc/{current}/task/{current}/children').read_text().split()
                        except FileNotFoundError:continue
                        for item in descendants:
                            pid=int(item)
                            if pid not in owned:owned.add(pid);pending.append(pid)
                    for pid in owned:
                        try:rss+=int(Path(f'/proc/{pid}/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
                        except FileNotFoundError:pass
                    peak_rss=max(peak_rss,rss)
                    if mode=='executor_failure' and snap['state']=='executing' and not interrupted:
                        targets=[int(x) for x in children if b'command_worker.py' in Path(f'/proc/{x}/cmdline').read_bytes()]
                        if targets:os.kill(targets[0],9);interrupted=True
                    if snap['state']=='speaking':
                        seen_speaking=True
                        if snap['command'] is None:raise AssertionError('missing speech result')
                        if mode in ('cancel','kill','shutdown') and not interrupted:
                            # Wait for warmup/inference to exercise an actual running speech process.
                            targets=[int(x) for x in children if b'tts_worker.py' in Path(f'/proc/{x}/cmdline').read_bytes()]
                            if targets and snap['speech_samples']>0:
                                if mode=='shutdown':
                                    p.terminate();check('shutdown during actual PCM',p.wait(timeout=3)==0)
                                    time.sleep(.1)
                                    check('owned speech descendants stopped',all(not Path(f'/proc/{pid}/cmdline').exists() or not Path(f'/proc/{pid}/cmdline').read_bytes() for pid in owned))
                                    rows.append({'fixture_id':name,'mode':mode,'speech_samples_before_shutdown':snap['speech_samples'],'peak_recursive_owned_rss_bytes':peak_rss})
                                    return
                                if mode=='cancel':check('cancel active speech',req('cancel',session_id=sid)['code']=='ok')
                                else:os.kill(targets[0],9)
                                interrupted=True
                    if snap['wake_status']=='replay_finished' and snap['state']=='idle' and snap['command']:break
                    time.sleep(.005)
                check('session finished and EOF observable',snap['state']=='idle' and snap['wake_status']=='replay_finished')
                check('entered integrated speech stage',seen_speaking)
                check('no detached speech process after endpoint',not any(b'tts_worker.py' in Path(f'/proc/{pid}/cmdline').read_bytes() for pid in owned if Path(f'/proc/{pid}/cmdline').exists()))
                if mode in ('cancel','kill'):check('live speech interruption exercised',interrupted)
                if mode in ('normal','executor_failure'):
                    speech=snap['speech'];check('Pocket PCM completed',snap['speech_status']=='completed' and speech is not None)
                    check('bounded nonzero virtual PCM with identity',speech['session_id']==sid and speech['sink']=='virtual' and speech['sample_rate']==24000 and 0<speech['samples']<=240000 and speech['chunks']>1 and speech['peak']>0 and speech['rms']>0 and len(speech['pcm_sha256'])==64)
                    check('virtual playback paced',speech['elapsed_ms']>=speech['samples']/24)
                    events=snap['events'];begin=next(e['sequence'] for e in events if e['kind']=='speech_started')
                    if mode=='executor_failure':
                        check('Failed feedback without false receipt',interrupted and snap['command']['code']=='command_failed' and snap['command']['receipt'] is None)
                    elif fixture:
                        check('NotUnderstood has no effect',snap['command']['code']=='unsupported' and snap['command']['receipt'] is None)
                    else:
                        effect=next(e['sequence'] for e in events if e['kind']=='command_success');check('speech follows verified effect',effect<begin and snap['command']['receipt']['verified'])
                else:check('failed/cancelled speech has no completed output',snap['speech'] is None and snap['speech_status'] in ('failed','cancelled'))
                check('effect result remains truthful if speech fails',bool(fixture) or mode=='executor_failure' or snap['command']['code']=='command_success')
                check('no voice or command artifacts persisted',set(x.name for x in root.iterdir())=={'core.sock','core.lock','config.json','audit.log'})
                check('Core remains alive after terminal speech',req()['code']=='ok')
                rows.append({'fixture_id':name,'mode':mode,'command':snap['command'],'speech_status':snap['speech_status'],'speech':snap['speech'],'peak_recursive_owned_rss_bytes':peak_rss})
                p.terminate();check('workers supervised on shutdown',p.wait(timeout=3)==0)
            finally:
                if s:s.close()
                if p.poll() is None:p.terminate();p.wait(timeout=3)
                p.stderr.close()
    case=os.environ.get('GIDEON_A5_CASE')
    if case:scenario(mode=case)
    else:scenario()
    if not case and os.environ.get('GIDEON_A5_SMOKE')!='1':
        for voice in ('bm_george','af_bella','am_michael'):scenario(voice)
        scenario(mode='executor_failure')
        scenario(fixture='wake-hey-yapyap__bf_emma__clean')
        for mode in ('cancel','kill','bad_hash'):scenario(mode=mode)
    result={'gate':'A5_INTEGRATION','passed':len(checks),'failed':0,'ignored':0,'checks':checks,'rows':rows,'binary_sha256':BINARY_ID,'physical_validation':'NOT_PERFORMED'}
    (BASE/('target/evidence/a5-'+case+'.json' if case else 'target/evidence/a5-integration.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'passed':len(checks),'rows':rows},indent=2))
if __name__=='__main__':run()
