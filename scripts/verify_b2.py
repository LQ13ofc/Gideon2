#!/usr/bin/env python3
"""B2.1 actual daemon persistence/CAS/failure and native offscreen preference flow."""
import hashlib,json,os,signal,socket,subprocess,tempfile,time
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];BIN=BASE/'target/release/gideon-base';checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
with tempfile.TemporaryDirectory(prefix='gideon-b2-') as td:
    root=Path(td)/'core';artifacts=Path(td)/'artifacts';artifacts.mkdir()
    env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_RUNTIME_DIR':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td}
    args=[str(BIN),'--root',str(root),'--virtual-input','--commands-sandbox','--tts-virtual',str(BASE/'target/tts-venv/bin/python'),str(BASE/'target/a5-assets/manifest.json')]
    core=None;counter=0
    def start():
        p=subprocess.Popen(args,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        until=time.monotonic()+5
        while not (root/'core.sock').exists():
            if p.poll() is not None:raise RuntimeError(p.stderr.read().decode())
            if time.monotonic()>until:p.terminate();p.wait();raise TimeoutError('Core startup')
            time.sleep(.01)
        return p
    def stop():
        core.terminate();check('clean shutdown',core.wait(timeout=3)==0);core.stderr.close()
    def request(op,ident=None,**kw):
        global counter
        counter+=1
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(3);s.connect(str(root/'core.sock'))
            s.sendall((json.dumps({'version':1,'request_id':ident or f'b2_{counter}','op':op,**kw})+'\n').encode())
            data=b''
            while not data.endswith(b'\n'):data+=s.recv(65536)
        return json.loads(data)
    def update(rev,audible=False,timeout=20000,**kw):return request('preferences',revision=rev,audible_feedback=audible,session_timeout_ms=timeout,**kw)
    try:
        core=start()
        check('default backwards compatible',request('snapshot')['preferences']=={'version':1,'wake_phrase':None,'revision':0,'audible_feedback':True,'session_timeout_ms':30000})
        check('invalid timeout rejected',update(0,timeout=0)['code']=='invalid_preferences')
        check('invalid request does not create rollback state','previous_preferences' not in request('snapshot')['preferences'])
        check('rollback absent fails safely',request('rollback_preferences',revision=0)['code']=='preferences_storage_error')
        check('caller grant rejected',update(0,grant=True)['code']=='invalid_message')
        wake=request('virtual_wake');check('busy refuses config',update(0)['code']=='busy')
        check('cancel still works',request('cancel',session_id=wake['session_id'])['code']=='ok')
        changed=update(0,ident='write1');check('update acknowledges effective state',changed['code']=='ok' and not changed['preferences']['audible_feedback'])
        check('duplicate fenced',update(1,ident='write1')['code']=='duplicate')
        check('stale revision fenced',update(0)['code']=='stale_preferences')
        check('private configuration files',all((root/name).stat().st_mode&0o777==0o600 for name in ('config.json',)))
        stop();core=start();snap=request('snapshot')['preferences'];check('persisted across actual restart',snap['revision']==1 and not snap['audible_feedback'] and snap['session_timeout_ms']==20000)
        rb=request('rollback_preferences',revision=1);check('rollback restores with new revision',rb['code']=='ok' and rb['preferences']['revision']==2 and rb['preferences']['audible_feedback'])
        before=(root/'config.json').read_bytes();sentinel=Path(td)/'sentinel';sentinel.write_text('private')
        (root/'.config.json.pending').symlink_to(sentinel)
        failed=update(2);check('unsafe temporary path is refused',failed['code']=='preferences_storage_error' and failed['preferences']['revision']==2)
        check('failure preserves committed file and sentinel',(root/'config.json').read_bytes()==before and sentinel.read_text()=='private')
        (root/'.config.json.pending').unlink()
        restored=request('rollback_preferences',revision=2)
        check('failed write preserves prior rollback',restored['code']=='ok' and not restored['preferences']['audible_feedback'] and restored['preferences']['session_timeout_ms']==20000)
        check('no speech persisted',all(b'raw' not in (root/n).read_bytes() for n in ('config.json','audit.log')))
        stop();core=None
        # Fresh private root for the GUI/native feedback integration.
        root=Path(td)/'ui-core';args[2]=str(root);core=start()
        py=BASE/'target/ui-venv/bin/python';runtime=py.resolve().parents[1];alias=py.readlink().parents[1]
        cmd=['/usr/bin/bwrap','--unshare-all','--die-with-parent','--ro-bind','/usr','/usr','--symlink','usr/lib','/lib','--symlink','usr/lib','/lib64','--ro-bind','/etc/fonts','/etc/fonts','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--ro-bind',str(runtime),str(runtime),'--ro-bind',str(runtime),str(alias),'--ro-bind',str(BASE),str(BASE),'--bind',td,td,'--setenv','HOME','/tmp','--setenv','XDG_CACHE_HOME','/tmp/cache','--setenv','XDG_CONFIG_HOME','/tmp/config','--setenv','XDG_RUNTIME_DIR','/tmp/runtime','--setenv','QT_QPA_PLATFORM','offscreen','--setenv','QT_QUICK_BACKEND','software','--setenv','QT_SCALE_FACTOR','2','--chdir','/tmp','--',str(py),'-I',str(BASE/'scripts/test_ui_offscreen.py'),'--root',str(root),'--artifacts',str(artifacts),'--phase','preferences']
        ui=subprocess.run(cmd,env={'PATH':'/usr/bin:/bin'},capture_output=True,timeout=55)
        if ui.returncode:raise RuntimeError(ui.stderr.decode()+ui.stdout.decode())
        row=json.loads(ui.stdout);checks.extend(row['checks']);(BASE/'target/evidence/b2-preferences.png').write_bytes((artifacts/'ui.png').read_bytes())
        stop();core=None
    finally:
        if core is not None and core.poll() is None:core.send_signal(signal.SIGCONT);core.terminate();core.wait(timeout=3);core.stderr.close()
result={'gate':'B2_1_PREFERENCES','passed':len(checks),'failed':0,'ignored':0,'checks':checks,'binary_sha256':hashlib.sha256(BIN.read_bytes()).hexdigest(),'physical_validation':'NOT_PERFORMED'}
(BASE/'target/evidence/b2-preferences.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
