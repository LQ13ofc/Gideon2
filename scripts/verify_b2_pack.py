#!/usr/bin/env python3
"""One trusted local pack, real Core selection and Qt/native replay; no peripherals."""
import hashlib,json,os,signal,socket,subprocess,tempfile,time
from pathlib import Path
from build_base_pack import build
from ui_fixture import offscreen_command
BASE=Path(__file__).resolve().parents[1];BIN=BASE/'target/release/gideon-base';checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
with tempfile.TemporaryDirectory(prefix='gideon-b2-pack-') as td:
    env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_RUNTIME_DIR':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td}
    pack=Path(td)/'base-pack.json';definition=build(pack);root=Path(td)/'core';artifacts=Path(td)/'artifacts';artifacts.mkdir();process=None;ui=None;counter=0
    manifest=BASE/'target/a3-assets/replay-manifest.json';m=json.loads(manifest.read_text());index=next(i for i,r in enumerate(m['fixtures']) if r['id']=='wake-hey-brave__bf_emma__clean')
    args=[str(BIN),'--root',str(root),'--virtual-input','--commands-sandbox','--tts-virtual',str(BASE/'target/tts-venv/bin/python'),str(BASE/'target/a5-assets/manifest.json'),'--wake-replay',str(BASE/'target/a1-venv/bin/python'),str(manifest),str(index),'--base-pack',str(pack)]
    def start():
        p=subprocess.Popen(args,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);until=time.monotonic()+6
        while not (root/'core.sock').exists():
            if p.poll() is not None:raise RuntimeError(p.stderr.read().decode())
            if time.monotonic()>until:p.terminate();p.wait();raise TimeoutError('pack startup')
            time.sleep(.01)
        return p
    def stop():
        process.terminate();check('clean pack shutdown',process.wait(timeout=3)==0);process.stderr.close()
    def request(op='snapshot',ident=None,**kw):
        global counter
        counter+=1
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(3);s.connect(str(root/'core.sock'));s.sendall((json.dumps({'version':1,'request_id':ident or f'pack_{counter}','op':op,**kw})+'\n').encode());data=b''
            while not data.endswith(b'\n'):
                chunk=s.recv(65536)
                if not chunk:raise RuntimeError('IPC EOF')
                data+=chunk
        return json.loads(data)
    def wait_marker(marker):
        until=time.monotonic()+55
        while not (artifacts/marker).exists():
            if ui.poll() is not None:raise RuntimeError(ui.stderr.read().decode()+ui.stdout.read().decode())
            if time.monotonic()>until:raise TimeoutError(marker)
            time.sleep(.02)
    try:
        # Refuse pack/profile/evidence tampering before binding any endpoint.
        for field,value in [('version',99),('wake_profile_sha256','0'*64),('stt_profile_sha256','0'*64),('tts_profile_sha256','0'*64)]:
            payload={**definition,field:value};pack.write_text(json.dumps(payload));p=subprocess.run(args,env=env,capture_output=True,timeout=8)
            check('pack rejects '+field,p.returncode!=0 and not (root/'core.sock').exists())
        broken=json.loads(json.dumps(definition));broken['phrases']['hey_gideon']['evidence']['sha256']='0'*64;pack.write_text(json.dumps(broken));p=subprocess.run(args,env=env,capture_output=True,timeout=8)
        check('qualification evidence hash guarded',p.returncode!=0 and not (root/'core.sock').exists())
        replay=json.loads(manifest.read_text());profile_path=Path(replay['stt']['manifest']);profile=json.loads(profile_path.read_text());profile['hashes']['encoder.ort']='0'*64
        bad_profile=Path(td)/'bad-stt.json';bad_profile.write_text(json.dumps(profile));replay['stt']['manifest']=str(bad_profile)
        bad_replay=Path(td)/'bad-replay.json';bad_replay.write_text(json.dumps(replay));modified={**definition,'wake_profile_sha256':hashlib.sha256(bad_replay.read_bytes()).hexdigest(),'stt_profile_sha256':hashlib.sha256(bad_profile.read_bytes()).hexdigest()}
        pack.write_text(json.dumps(modified));bad_args=args.copy();bad_args[bad_args.index(str(manifest))]=str(bad_replay)
        failed=subprocess.run(bad_args,env=env,capture_output=True,timeout=8)
        check('model hash preflight happens before workers',failed.returncode!=0 and not (root/'core.sock').exists())
        pack.write_text(json.dumps(definition));pack_checksum=hashlib.sha256(pack.read_bytes()).hexdigest()
        process=start();snap=request();catalog=snap['base_pack']
        check('catalog verified and bounded',catalog['preflight']=='verified' and len(catalog['wake_phrases'])==2)
        check('qualification distinct from support',[(p['id'],p['qualification']) for p in catalog['wake_phrases']]==[('hey_gideon','dev_qualified'),('okay_gideon','poc_required')])
        check('no paths in discovery',str(BASE) not in json.dumps(catalog))
        check('reject caller qualification injection',request('select_wake',revision=0,phrase_id='okay_gideon',qualified=True)['code']=='invalid_message')
        check('unknown phrase denied',request('select_wake',revision=0,phrase_id='anything')['code']=='wake_not_qualified')
        check('POC phrase denied',request('select_wake',revision=0,phrase_id='okay_gideon')['code']=='wake_not_qualified')
        until=time.monotonic()+8
        while not request()['session_id']:
            if time.monotonic()>until:raise TimeoutError('wake session')
            time.sleep(.01)
        check('busy selection denied',request('select_wake',revision=0,phrase_id='hey_gideon')['code']=='busy')
        stop();process=None
        # Compatible schema but unqualified phrase must enter content safe mode.
        cfg=root/'config.json';cfg.write_text(json.dumps({'version':1,'session_timeout_ms':30000,'wake_phrase':'okay_gideon'}));cfg.chmod(0o600)
        process=start();snap=request()
        check('incompatible stored phrase enters safe mode',snap['configuration_status']=='safe_mode' and snap['base_pack']['active_phrase'] is None)
        check('incompatible config starts no workers',not Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split())
        recovered=request('recover_configuration',revision=snap['preferences']['revision']);check('compatible defaults recover with restart',recovered['code']=='ok' and recovered['configuration_status']=='restart_required')
        stop();process=None
        # Fresh root: drive actual Qt controls, restart, then native S1 and rollback.
        root=Path(td)/'ui-core';args[2]=str(root);process=start()
        ui=subprocess.Popen(offscreen_command(root,artifacts,'pack'),env={'PATH':'/usr/bin:/bin'},stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        wait_marker('selected');stop();process=None;wait_marker('offline');process=start();wait_marker('rolled_back')
        out,err=ui.communicate(timeout=3)
        if ui.returncode:raise RuntimeError(err.decode()+out.decode())
        checks.extend(json.loads(out)['checks']);check('selection rollback persisted',json.loads((root/'config.json').read_text())['wake_phrase'] is None)
        stop();process=None;process=start();snapshot=request();check('rollback accepted by pack on restart',snapshot['configuration_status']=='ready' and snapshot['base_pack']['active_phrase']=='hey_gideon')
        check('healthy recovery operation refused',request('recover_configuration',revision=2)['code']=='recovery_unavailable')
        check('stale config fenced',request('select_wake',revision=0,phrase_id='hey_gideon')['code']=='stale_preferences')
        stop();process=None
        (BASE/'target/evidence/b2-pack.png').write_bytes((artifacts/'pack.png').read_bytes())
    finally:
        if ui is not None and ui.poll() is None:ui.kill();ui.wait(timeout=3)
        if process is not None and process.poll() is None:process.send_signal(signal.SIGCONT);process.terminate();process.wait(timeout=3);process.stderr.close()
report={'gate':'B2_2B_BASE_PACK','passed':len(checks),'failed':0,'ignored':0,'checks':checks,'binary_sha256':hashlib.sha256(BIN.read_bytes()).hexdigest(),'pack_sha256':pack_checksum,'physical_validation':'NOT_PERFORMED'}
(BASE/'target/evidence/b2-pack.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
