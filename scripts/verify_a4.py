#!/usr/bin/env python3
"""Native S1 pipeline with actual namespace app process and receipt, never host effects."""
import hashlib,json,os,socket,subprocess,tempfile,time
from pathlib import Path
from process_fixture import command_line
BASE=Path(__file__).resolve().parents[1]
BINARY=BASE/'target/release/gideon-base';PYTHON=BASE/'target/a1-venv/bin/python';MANIFEST=BASE/'target/a3-assets/replay-manifest.json'
BINARY_ID=hashlib.sha256(BINARY.read_bytes()).hexdigest()

def run():
    m=json.loads(MANIFEST.read_text());checks=[];rows=[]
    def check(name,value):
        if not value:raise AssertionError(name)
        checks.append(name)
    def scenario(name,cancel=False,expected='command_success',phrase=None,cancel_execution=False,kill_executor=False):
        index=next(i for i,r in enumerate(m['fixtures']) if r['id']==name)
        with tempfile.TemporaryDirectory(prefix='gideon-a4-') as td:
            root=Path(td)/'core';root.mkdir(mode=0o700)
            cfg={'version':1,'session_timeout_ms':30000,'wake_phrase':phrase};(root/'config.json').write_text(json.dumps(cfg));(root/'config.json').chmod(0o600)
            env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td,'XDG_RUNTIME_DIR':td,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
            p=subprocess.Popen([str(BINARY),'--root',str(root),'--commands-sandbox','--wake-replay',str(PYTHON),str(MANIFEST),str(index)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);s=None
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
                until=time.monotonic()+25;partials=[];sid=None;cancelled=False;interrupted=False
                while time.monotonic()<until:
                    snap=req();started=[e for e in snap['events'] if e['kind']=='session_started']
                    if started:sid=started[0]['session_id']
                    t=snap['transcript']
                    if t and not t['is_final'] and not any(x['revision']==t['revision'] for x in partials):
                        partials.append(t)
                        check('partial never executes',snap['command'] is None and not any(e['kind']=='command_authorized' for e in snap['events']))
                        check('caller capability cannot grant',req('action',session_id=sid,capability='open_app')['code']=='denied')
                        if cancel and not cancelled:
                            check('cancel accepted during streaming',req('cancel',session_id=sid)['code']=='ok');cancelled=True
                    if snap['state']=='executing' and not interrupted and (cancel_execution or kill_executor):
                        if cancel_execution:
                            check('cancel executing task accepted',req('cancel',session_id=sid)['code']=='ok')
                        else:
                            children=Path(f'/proc/{p.pid}/task/{p.pid}/children').read_text().split()
                            targets=[int(x) for x in children if b'command_worker.py' in command_line(x)]
                            check('executor process owned and identifiable',len(targets)==1)
                            os.kill(targets[0],9)
                        interrupted=True
                    if snap['wake_status']=='replay_finished'  and snap['state']=='idle' and (cancelled or snap['command']):break
                    time.sleep(.005)
                check('producer EOF and terminal session',snap['wake_status']=='replay_finished' and snap['state']=='idle')
                if cancel:
                    check('cancel leaves no receipt or authorization',cancelled and snap['command'] is None and not any(e['kind']=='command_authorized' for e in snap['events']))
                else:
                    check('final native transcript present or revoked on cancel',cancel_execution or (bool(snap['transcript']) and snap['transcript']['is_final']))
                    outcome=snap['command'];check('expected deterministic result '+json.dumps({'transcript':snap['transcript'],'command':outcome}),bool(outcome) and outcome['code']==expected)
                    if cancel_execution or kill_executor:check('execution interrupted at live boundary',interrupted)
                    if expected=='command_success':
                        r=outcome['receipt'];check('sandbox effect verified with exact session',r['verified'] and r['scope']=='sandbox' and r['job']['session_id']==sid)
                        check('authorization and success emitted once',sum(e['kind']=='command_authorized' for e in snap['events'])==1 and sum(e['kind']=='command_success' for e in snap['events'])==1)
                        check('actual app proof reported',r['job']['command']=={'kind':'open_app','desktop_id':'com.brave.Browser.desktop'} and 'process verified' in r['result'])
                    else:
                        check('no success or receipt on rejection/failure',outcome['receipt'] is None and not any(e['kind']=='command_success' for e in snap['events']))
                        if not (cancel_execution or kill_executor):check('no authorization on safety rejection',not any(e['kind']=='command_authorized' for e in snap['events']))
                    seq=snap['sequence'];time.sleep(.1);check('terminal result stable without duplicate effect',req()['sequence']==seq)
                check('late IPC action fenced',req('action',session_id=sid,capability='open_app')['code']=='stale_session')
                check('private root contains no voice or command artifacts',set(x.name for x in root.iterdir())=={'core.sock','core.lock','config.json','audit.log'})
                rows.append({'fixture_id':name,'cancel':cancel,'wake_phrase':phrase,'transcript':snap['transcript'],'command':snap['command']})
                p.terminate();check('supervised shutdown',p.wait(timeout=3)==0)
            finally:
                if s:s.close()
                if p.poll() is None:p.terminate();p.wait(timeout=3)
                p.stderr.close()
    for voice in ('bf_emma','bm_george','af_bella','am_michael'):
        scenario(f'wake-hey-brave__{voice}__clean')
    scenario('wake-hey-brave__bf_emma__clean',cancel=True)
    scenario('wake-hey-brave__bf_emma__clean',cancel_execution=True,expected='cancelled')
    scenario('wake-hey-brave__bf_emma__clean',kill_executor=True,expected='command_failed')
    scenario('wake-hey-yapyap__bf_emma__clean',expected='unsupported')
    scenario('wake-okay-steam__bf_emma__clean',expected='unsupported',phrase='okay_gideon')
    return {'gate':'A4_INTEGRATION','passed':len(checks),'failed':0,'ignored':0,'checks':checks,'rows':rows,'binary_sha256':BINARY_ID,'physical_validation':'NOT_PERFORMED'}
if __name__=='__main__':
    result=run();(BASE/'target/evidence/a4-integration.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'gate':result['gate'],'passed':result['passed'],'rows':result['rows']},indent=2))
