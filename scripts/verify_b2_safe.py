#!/usr/bin/env python3
"""Bounded private config recovery, actual daemon and Qt/native S1 after restart."""
import hashlib,json,os,signal,socket,subprocess,tempfile,time
from pathlib import Path
from ui_fixture import offscreen_command
BASE=Path(__file__).resolve().parents[1];BIN=BASE/'target/release/gideon-base';checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
with tempfile.TemporaryDirectory(prefix='gideon-b2-safe-') as td:
    env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_RUNTIME_DIR':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td}
    process=None;ui=None;counter=0;root=Path(td)/'core';root.mkdir(mode=0o700)
    cfg=root/'config.json'
    def write_config(raw):cfg.write_bytes(raw);cfg.chmod(0o600)
    # Invalid paths deliberately prove safe mode never reads/launches engines.
    disabled_args=['--virtual-input','--commands-sandbox','--tts-virtual','/not-a-runtime','/not-a-tts-pack','--wake-replay','/not-a-runtime','/not-a-wake-pack','0']
    def start(extra=disabled_args):
        p=subprocess.Popen([str(BIN),'--root',str(root),*extra],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        until=time.monotonic()+3
        while not (root/'core.sock').exists():
            if p.poll() is not None:raise RuntimeError(p.stderr.read().decode())
            if time.monotonic()>until:p.terminate();p.wait();raise TimeoutError('start')
            time.sleep(.01)
        return p
    def stop():
        process.terminate();check('clean safe shutdown',process.wait(timeout=3)==0);process.stderr.close()
    def req(op='snapshot',ident=None,**kw):
        global counter
        counter+=1
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(3);s.connect(str(root/'core.sock'));s.sendall((json.dumps({'version':1,'request_id':ident or f'safe_{counter}','op':op,**kw})+'\n').encode());data=b''
            while not data.endswith(b'\n'):
                chunk=s.recv(65536)
                if not chunk:raise RuntimeError('unexpected IPC EOF')
                data+=chunk
        return json.loads(data)
    def children():return Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()
    def wait_marker(marker):
        until=time.monotonic()+12
        while not (artifacts/marker).exists():
            if ui.poll() is not None:raise RuntimeError(ui.stderr.read().decode())
            if time.monotonic()>until:raise TimeoutError(marker)
            time.sleep(.02)
    try:
        for invalid in (b'{private-config-marker}',b'{"version":99,"session_timeout_ms":30000}',b'{"version":1,"session_timeout_ms":0}',b'{"version":1,"session_timeout_ms":30000,"unexpected":true}',b'x'*4097):
            write_config(invalid);process=start();snapshot=req();rev=snapshot['preferences']['revision']
            check('invalid content opens safe IPC '+str(counter),snapshot['configuration_status']=='safe_mode' and snapshot['state']=='idle')
            check('invalid bytes never leave config '+str(counter),cfg.read_bytes()==invalid and 'private-config-marker' not in json.dumps(snapshot))
            check('recovery availability is bounded '+str(counter),snapshot['configuration_recovery_available']==(len(invalid)<=4096))
            check('safe epoch is nonzero',rev>0)
            for op,kw in [('virtual_wake',{}),('text',{'raw':'open brave'}),('action',{'session_id':1,'capability':'open_app'}),('cancel',{'session_id':1}),('preferences',{'revision':rev,'audible_feedback':True,'session_timeout_ms':30000}),('rollback_preferences',{'revision':rev})]:
                check('safe mode blocks '+op,req(op,**kw)['code']=='configuration_not_ready')
            check('safe mode starts no engines or executors',not children())
            stop();process=None
        invalid=b'{private-config-marker}';write_config(invalid);process=start();rev=req()['preferences']['revision']
        check('unknown recovery grant rejected',req('recover_configuration',revision=rev,grant=True)['code']=='invalid_message')
        check('stale recovery fenced',req('recover_configuration',revision=rev-1)['code']=='stale_preferences')
        write_config(b'changed-invalid')
        check('changed invalid file is not overwritten',req('recover_configuration',revision=rev)['code']=='configuration_recovery_error' and cfg.read_bytes()==b'changed-invalid')
        write_config(invalid);sentinel=Path(td)/'sentinel';sentinel.write_text('untouched')
        (root/'config.invalid.json').symlink_to(sentinel)
        check('unsafe preservation file rejected',req('recover_configuration',revision=rev)['code']=='configuration_recovery_error' and sentinel.read_text()=='untouched')
        (root/'config.invalid.json').unlink();(root/'.config.json.pending').symlink_to(sentinel)
        failed=req('recover_configuration',revision=rev)
        check('failed write cannot activate config',failed['code']=='configuration_recovery_error' and failed['configuration_status']=='safe_mode' and cfg.read_bytes()==invalid)
        check('failed write preserves original privately',(root/'config.invalid.json').read_bytes()==invalid and (root/'config.invalid.json').stat().st_mode&0o777==0o600)
        (root/'.config.json.pending').unlink()
        recovered=req('recover_configuration',ident='recover_once',revision=rev)
        check('recovery commits defaults with new revision',recovered['code']=='ok' and recovered['preferences']['revision']==rev+1 and json.loads(cfg.read_bytes())['revision']==rev+1)
        check('recovery requires restart',recovered['configuration_status']=='restart_required' and not recovered['configuration_recovery_available'])
        check('duplicate recovery fenced',req('recover_configuration',ident='recover_once',revision=rev)['code']=='duplicate')
        check('recovered daemon still cannot start session',req('virtual_wake')['code']=='configuration_not_ready' and not children())
        check('audit does not retain invalid payload',b'private-config-marker' not in (root/'audit.log').read_bytes())
        stop();process=None
        process=start(['--virtual-input','--commands-sandbox'])
        check('actual restart activates valid config',req()['configuration_status']=='ready')
        check('healthy recovery operation refused',req('recover_configuration',revision=rev+1)['code']=='recovery_unavailable')
        req('text',raw='open brave');until=time.monotonic()+4
        while time.monotonic()<until:
            snapshot=req()
            if snapshot['state']=='idle' and snapshot['command']:break
            time.sleep(.01)
        check('shared executor works after recovery',snapshot['command']['receipt']['verified'])
        stop();process=None
        # Unsafe file metadata must never be reclassified as content safe mode.
        for mode in ('symlink','hardlink','permissions'):
            cfg.unlink();sentinel.chmod(0o600)
            if mode=='symlink':cfg.symlink_to(sentinel)
            elif mode=='hardlink':os.link(sentinel,cfg)
            else:write_config(invalid);cfg.chmod(0o644)
            denied=subprocess.run([str(BIN),'--root',str(root)],env=env,capture_output=True,timeout=3)
            check('unsafe '+mode+' fails closed',denied.returncode!=0 and not (root/'core.sock').exists() and sentinel.read_text()=='untouched')
        root=Path(td)/'ui-core';root.mkdir(mode=0o700);cfg=root/'config.json';write_config(invalid);artifacts=Path(td)/'artifacts';artifacts.mkdir()
        manifest=BASE/'target/a3-assets/replay-manifest.json';profile=json.loads(manifest.read_text());index=next(i for i,r in enumerate(profile['fixtures']) if r['id']=='wake-hey-brave__bf_emma__clean')
        real_args=['--commands-sandbox','--tts-virtual',str(BASE/'target/tts-venv/bin/python'),str(BASE/'target/a5-assets/manifest.json'),'--wake-replay',str(BASE/'target/a1-venv/bin/python'),str(manifest),str(index)]
        process=start(real_args);ui=subprocess.Popen(offscreen_command(root,artifacts,'safe_mode'),env={'PATH':'/usr/bin:/bin'},stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        wait_marker('recovered');stop();process=None;wait_marker('offline');process=start(real_args)
        out,err=ui.communicate(timeout=50)
        if ui.returncode:raise RuntimeError(err.decode()+out.decode())
        checks.extend(json.loads(out)['checks']);(BASE/'target/evidence/b2-safe-mode.png').write_bytes((artifacts/'safe-mode.png').read_bytes())
        check('Qt recovery preserves original file',(root/'config.invalid.json').read_bytes()==invalid)
        stop();process=None
    finally:
        if ui is not None and ui.poll() is None:ui.kill();ui.wait(timeout=3)
        if process is not None and process.poll() is None:process.send_signal(signal.SIGCONT);process.terminate();process.wait(timeout=3);process.stderr.close()
report={'gate':'B2_2A_SAFE_MODE','passed':len(checks),'failed':0,'ignored':0,'checks':checks,'binary_sha256':hashlib.sha256(BIN.read_bytes()).hexdigest(),'physical_validation':'NOT_PERFORMED'}
(BASE/'target/evidence/b2-safe-mode.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
