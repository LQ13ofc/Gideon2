#!/usr/bin/env python3
"""Real wake→capture→Moonshine streaming into Core; no partial effects."""
from process_fixture import resident_bytes
import hashlib,json,os,socket,subprocess,tempfile,time
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
BINARY=BASE/'target/release/gideon-base';PYTHON=BASE/'target/a1-venv/bin/python';MANIFEST=BASE/'target/a3-assets/replay-manifest.json'
BINARY_ID=hashlib.sha256(BINARY.read_bytes()).hexdigest()

def run():
    m=json.loads(MANIFEST.read_text());checks=[];rows=[]
    def check(name,value):
        if not value:raise AssertionError(name)
        checks.append(name)
    def scenario(cancel=False,bad_model=False,kill_worker=False,name="wake-hey-brave__bf_emma__clean"):
        index=next(i for i,r in enumerate(m['fixtures']) if r['id']==name)
        with tempfile.TemporaryDirectory(prefix='gideon-a3-') as td:
            root=Path(td)/'core';env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td,'XDG_RUNTIME_DIR':td,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
            path=MANIFEST
            if bad_model:
                model=json.loads(Path(m['stt']['manifest']).read_text());model['hashes']=dict(model['hashes']);model['hashes']['encoder.ort']='0'*64
                modelpath=Path(td)/'invalid-model.json';modelpath.write_text(json.dumps(model))
                cfg=dict(m);cfg['stt']=dict(cfg['stt']);cfg['stt']['manifest']=str(modelpath)
                path=Path(td)/'replay.json';path.write_text(json.dumps(cfg))
            p=subprocess.Popen([str(BINARY),'--root',str(root),'--wake-replay',str(PYTHON),str(path),str(index)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);s=None
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
                until=time.monotonic()+25;partials=[];final=None;sid=None;cancelled=False
                while time.monotonic()<until:
                    snap=req()
                    if snap['stt_status']=='failed':
                        if bad_model or kill_worker:break
                        raise RuntimeError('native STT worker failed')
                    started=[e for e in snap['events'] if e['kind']=='session_started']
                    if started:sid=started[0]['session_id']
                    t=snap['transcript']
                    if t and not t['is_final'] and not any(x['revision']==t['revision'] for x in partials):
                        partials.append(dict(t,source_finished=snap['wake_status']=='replay_finished'))
                        check('partial cannot authorize action',req('action',session_id=sid,capability='open_app')['code']=='denied')
                        if kill_worker:
                            children=Path(f'/proc/{p.pid}/task/{p.pid}/children').read_text().split()
                            check('STT child owned and distinguishable',len(children)>=1)
                            os.kill(int(children[0]),9)
                        if cancel:
                            check('cancel streaming recognized session',req('cancel',session_id=sid)['code']=='ok');cancelled=True
                    if t and t['is_final']:final=t
                    if snap['wake_status']=='replay_finished' and (cancelled or final):break
                    time.sleep(.02)
                if not bad_model and not kill_worker:check('audio EOF remains observable with STT',snap['wake_status']=='replay_finished')
                if bad_model:
                    check('model integrity failure before any capture',snap['stt_status']=='failed' and not partials and not started and snap['transcript'] is None)
                elif kill_worker:
                    check('worker failure revokes transcript and session',snap['stt_status']=='failed' and snap['transcript'] is None and snap['session_id'] is None)
                elif cancel:
                    check('late native final fenced after cancel',cancelled and final is None and snap['transcript'] is None and snap['state']=='idle')
                else:
                    check('native partial before source EOF',bool(partials) and not partials[0]['source_finished'])
                    check('correlated final contains initial command and entity',final is not None and final['session_id']==sid and 'open' in final['raw'].lower() and 'brave' in final['raw'].lower())
                    check('raw normalization separate and confidence unknown',final['normalized']==' '.join(final['raw'].split()) and final['confidence'] is None)
                    check('revisions monotonic',all(b['revision']>a['revision'] for a,b in zip(partials,partials[1:])) and final['revision']>partials[-1]['revision'])
                    check('no command executed by STT final',req('action',session_id=sid,capability='open_app')['code']=='stale_session')
                check('no voice/text files persisted',set(x.name for x in root.iterdir())=={'core.sock','core.lock','config.json','audit.log'})
                resource=None
                if final:
                    def owned_pids():
                        found={p.pid};pending=[p.pid]
                        while pending:
                            current=pending.pop()
                            try:children=Path(f'/proc/{current}/task/{current}/children').read_text().split()
                            except (FileNotFoundError,ProcessLookupError):continue
                            for child in children:
                                child=int(child)
                                if child not in found:found.add(child);pending.append(child)
                        return found
                    def stats(pids):
                        ticks=0;rss=0
                        for pid in pids:
                            try:
                                stat=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split();ticks+=int(stat[11])+int(stat[12])
                                rss+=resident_bytes(pid)
                            except (FileNotFoundError,ProcessLookupError):continue
                        return ticks,rss
                    pids=owned_pids();ticks0,rss0=stats(pids);start=time.monotonic();time.sleep(2);ticks1,rss1=stats(pids)
                    idle=100*(ticks1-ticks0)/os.sysconf('SC_CLK_TCK')/(time.monotonic()-start)
                    resource={'idle_cpu_percent_one_core':idle,'sum_rss_bytes':max(rss0,rss1),'scope':'owned process tree after fixture EOF; STT loaded, wake fixture worker exited; RSS sums shared pages'}
                    check('loaded STT idle CPU below one percent',idle<1.)
                    check('loaded STT process RSS below one GiB',resource['sum_rss_bytes']<1024**3)
                rows.append({'fixture_id':name,'cancel':cancel,'partials':partials,'final':final,'resource':resource})
                p.terminate();check('both workers shutdown',p.wait(timeout=3)==0)
            finally:
                if s:s.close()
                if p.poll() is None:p.terminate();p.wait(timeout=3)
                p.stderr.close()
    for voice in ('bf_emma','bm_george','af_bella','am_michael'):
        scenario(name=f'wake-hey-brave__{voice}__clean')
    scenario(cancel=True);scenario(bad_model=True);scenario(kill_worker=True)
    return {'gate':'A3_INTEGRATION','passed':len(checks),'failed':0,'ignored':0,'checks':checks,'rows':rows,'binary_sha256':BINARY_ID,'physical_validation':'NOT_PERFORMED'}
if __name__=='__main__':
    result=run();(BASE/'target/evidence/a3-integration.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
