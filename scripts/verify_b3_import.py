#!/usr/bin/env python3
"""Private real Core opaque staging, actual CLI upload and Qt cancel/native regressions."""
import hashlib,json,os,socket,subprocess,tempfile,time
from pathlib import Path
from ui_fixture import offscreen_command
BASE=Path(__file__).resolve().parents[1];BIN=BASE/'target/release/gideon-base';CAT=BASE/'tests/fixtures/hub.json';checks=[]
def check(name,value):
    assert value,name
    checks.append(name)
with tempfile.TemporaryDirectory(prefix='gideon-b3-import-') as td:
    root=Path(td)/'core';core=None;counter=0
    env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td,'XDG_RUNTIME_DIR':td}
    args=[str(BIN),'--root',str(root),'--virtual-input','--commands-sandbox','--hub-catalog',str(CAT),hashlib.sha256(CAT.read_bytes()).hexdigest()]
    def start():
        p=subprocess.Popen(args,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);until=time.monotonic()+5
        while True:
            try:
                with socket.socket(socket.AF_UNIX) as probe:probe.connect(str(root/'core.sock'))
                break
            except (FileNotFoundError,ConnectionRefusedError):pass
            if p.poll() is not None:raise RuntimeError(p.stderr.read().decode())
            if time.monotonic()>until:p.terminate();p.wait();raise TimeoutError('startup')
            time.sleep(.01)
        return p
    def stop():
        core.terminate();check('clean shutdown',core.wait(timeout=3)==0);core.stderr.close()
    def request(op='snapshot',ident=None,**kw):
        global counter
        counter+=1
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(5);s.connect(str(root/'core.sock'));s.sendall((json.dumps({'version':1,'request_id':ident or f'stage_{counter}','op':op,**kw})+'\n').encode());data=b''
            while not data.endswith(b'\n'):data+=s.recv(65536)
        return json.loads(data)
    def setup():
        hub=request()['hub'];entry=hub['entries'][0]
        return {'revision':hub['approval_revision'],'plugin_id':entry['plugin_id'],'manifest_sha256':entry['manifest_sha256']},entry
    def approve():
        fields,entry=setup();check('explicit manifest approval',request('hub_approve',**fields,permissions=entry['permissions'],publisher_unverified_ack=True)['code']=='ok')
    def begin(**kw):
        fields,_=setup();return request('hub_begin',**{**fields,**kw})
    def effect():
        request('text',raw='open brave');until=time.monotonic()+5
        while True:
            snap=request()
            if snap['state']=='idle' and snap['command'] is not None:break
            if time.monotonic()>until:raise TimeoutError(snap)
            time.sleep(.015)
        check('Base effect remains verified',snap['command']['receipt']['verified'])
    source=Path(td)/'fixture.bin';source.write_bytes(b'benign fixture\n')
    def upload():
        run=subprocess.run(['python3',str(BASE/'scripts/hub_import.py'),'--root',str(root),'--plugin','benign_fixture','--source',str(source)],env=env,capture_output=True,text=True,timeout=10)
        if run.returncode:raise RuntimeError(run.stderr)
        return json.loads(run.stdout)
    try:
        core=start();fields,entry=setup();pending=root/('.hub-'+entry['manifest_sha256']+'.pending');destination=root/('hub-'+entry['manifest_sha256']+'.payload')
        check('unapproved bytes cannot begin',begin()['code']=='permissions_not_approved');approve()
        for kw,code in [({'revision':0},'stale_hub_revision'),({'plugin_id':'unknown'},'unknown_plugin'),({'plugin_id':'future_api'},'plugin_incompatible'),({'manifest_sha256':'0'*64},'manifest_mismatch'),({'source':'/etc/passwd'},'invalid_message')]:
            check('begin rejects '+code,begin(**kw)['code']==code)
        sentinel=Path(td)/'sentinel';sentinel.write_bytes(b'preserved');pending.symlink_to(sentinel)
        check('unsafe pending refuses creation',begin()['code']=='hub_storage_error' and sentinel.read_bytes()==b'preserved');pending.unlink()
        for op in ['hub_chunk','hub_finish','hub_abort']:
            kw={'offset':0,'hex':'00'} if op=='hub_chunk' else {}
            check(op+' fences unknown transaction',request(op,import_id='stale',**kw)['code']=='stale_import')
        sid=request('virtual_wake')['session_id'];check('begin while voice busy refused',begin()['code']=='busy');request('cancel',session_id=sid)
        first=begin(ident='first');active=first['hub']['import']['import_id'];check('begin advertises bounded zero progress',first['code']=='ok' and first['hub']['import']['received']==0 and first['hub']['import']['expected']==15)
        check('duplicate begin fenced',begin(ident='first')['code']=='duplicate');check('second import refused',begin()['code']=='hub_import_busy')
        check('approval cannot change during import',request('hub_approve',**setup()[0],permissions=entry['permissions'],publisher_unverified_ack=True)['code']=='hub_import_busy')
        for offset,hexvalue,code in [(1,'00','stale_import_offset'),(0,'','invalid_import_chunk'),(0,'x1','invalid_import_chunk'),(0,'A0','invalid_import_chunk'),(0,'0','invalid_import_chunk'),(0,'00'*1025,'invalid_import_chunk')]:
            check('chunk rejects '+code,request('hub_chunk',import_id=active,offset=offset,hex=hexvalue)['code']==code)
        check('normal first chunk',request('hub_chunk',ident='chunk_duplicate',import_id=active,offset=0,hex=b'benign '.hex())['hub']['import']['received']==7)
        check('duplicate chunk never appends twice',request('hub_chunk',ident='chunk_duplicate',import_id=active,offset=0,hex=b'benign '.hex())['code']=='duplicate' and request()['hub']['import']['received']==7)
        sid=request('virtual_wake')['session_id'];check('finish while voice busy refused',request('hub_finish',import_id=active)['code']=='busy')
        check('abort remains available during voice',request('hub_abort',import_id=active)['code']=='ok');request('cancel',session_id=sid);check('abort removes owned pending',not pending.exists() and not destination.exists())
        active=begin()['hub']['import']['import_id'];check('short payload refuses publication',request('hub_finish',import_id=active)['code']=='payload_size_mismatch' and not pending.exists())
        active=begin()['hub']['import']['import_id'];check('oversize aborts bounded import',request('hub_chunk',import_id=active,offset=0,hex='00'*16)['code']=='payload_size_mismatch' and not pending.exists())
        active=begin()['hub']['import']['import_id'];request('hub_chunk',import_id=active,offset=0,hex='00'*15);check('hash mismatch never published',request('hub_finish',import_id=active)['code']=='payload_hash_mismatch' and not destination.exists())
        active=begin(ident='reused_begin')['hub']['import']['import_id'];stop();core=None;check('shutdown cleans pending',not pending.exists());core=start()
        next_id=begin(ident='reused_begin')['hub']['import']['import_id'];check('boot epoch fences reused request IDs',next_id!=active and request('hub_chunk',import_id=active,offset=0,hex='00')['code']=='stale_import');request('hub_abort',import_id=next_id)
        # P9 contract: the startup sweep MOVES a crash-orphan pending file into quarantine/ (0700); it is never deleted or edited,
        # so the root no longer blocks a fresh import of the same payload.
        active=begin()['hub']['import']['import_id'];orphan_bytes=pending.read_bytes();core.kill();check('forced crash leaves owned orphan unmodified',core.wait(timeout=3)==-9 and pending.exists());core.stderr.close();core=None;core=start()
        quarantined=sorted((root/'quarantine').glob('.hub-'+entry['manifest_sha256']+'.pending.*'))
        check('crash orphan left the root after restart',not pending.exists())
        check('crash orphan quarantined with intact bytes',len(quarantined)==1 and quarantined[0].read_bytes()==orphan_bytes)
        check('quarantine directory is private 0700',(root/'quarantine').stat().st_mode&0o777==0o700)
        check('snapshot hub.orphans reflects the swept orphan',request()['hub']['orphans']==1)
        check('crash orphan never resumes as an import',request()['hub']['import'] is None)
        fresh=begin()
        check('fresh begin of the same payload succeeds after the sweep',fresh['code']=='ok' and fresh['hub']['import']['received']==0)
        request('hub_abort',import_id=fresh['hub']['import']['import_id']);check('abort of the fresh import leaves no pending file',not pending.exists())
        effect();stop();core=None;core=start()
        final=upload();check('real local CLI imports verified opaque bytes',final['hub']['entries'][0]['payload_staged'] and destination.read_bytes()==source.read_bytes());check('private nonexecutable payload',destination.stat().st_mode&0o777==0o600 and destination.stat().st_nlink==1)
        check('staging never installs or authenticates',final['hub']['entries'][0]['status']=='not_installed' and not final['hub']['publisher_verified']);check('repeat cannot overwrite payload',begin()['code']=='already_staged');effect();stop();core=None;core=start();check('restart validates actual bytes',request()['hub']['entries'][0]['payload_staged']);stop();core=None
        original=destination.read_bytes()
        for mode in ['corrupt','permissions','executable','symlink','hardlink','fifo']:
            destination.unlink()
            if mode=='symlink':destination.symlink_to(sentinel)
            elif mode=='hardlink':os.link(sentinel,destination)
            elif mode=='fifo':os.mkfifo(destination,0o600)
            else:destination.write_bytes(b'corrupt' if mode=='corrupt' else original);destination.chmod(0o644 if mode=='permissions' else 0o700 if mode=='executable' else 0o600)
            core=start();snap=request()
            # P10 contract (src/hub.rs with_approvals): an unusable staged payload is refused per entry only, never the whole Hub.
            staged=[e for e in snap['hub']['entries'] if e.get('staged_error')]
            check(mode+' payload refused per entry: staged_error only, Hub verified, Base ready',snap['hub']['status']=='verified' and [e['plugin_id'] for e in staged]==['benign_fixture'] and staged[0]['staged_error']=='staged_payload_invalid' and staged[0]['payload_staged'] is False and snap['configuration_status']=='ready');effect();stop();core=None
        destination.unlink();destination.write_bytes(original);destination.chmod(0o600)
        # Actual Qt cancellation and opaque CLI stage, full native S1 before/after restart.
        root=Path(td)/'native';args=[str(BIN),'--root',str(root),'--commands-sandbox','--hub-catalog',str(CAT),hashlib.sha256(CAT.read_bytes()).hexdigest(),'--base-pack',str(BASE/'target/base-pack-dev.json'),'--tts-virtual',str(BASE/'target/tts-venv/bin/python'),str(BASE/'target/a5-assets/manifest.json')]
        manifest=BASE/'target/a3-assets/replay-manifest.json';index=next(i for i,r in enumerate(json.loads(manifest.read_text())['fixtures']) if r['id']=='wake-hey-brave__bf_emma__clean');args+=['--wake-replay',str(BASE/'target/a1-venv/bin/python'),str(manifest),str(index)];core=start()
        artifacts=Path(td)/'artifacts';artifacts.mkdir();ui=subprocess.Popen(offscreen_command(root,artifacts,'staging'),env={'PATH':'/usr/bin:/bin'},stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        def marker(name):
            until=time.monotonic()+55
            while not (artifacts/name).exists():
                if ui.poll() is not None:raise RuntimeError(ui.stderr.read().decode()+ui.stdout.read().decode())
                if time.monotonic()>until:raise TimeoutError(name)
                time.sleep(.02)
        try:
            marker('ready');approve();active=begin()['hub']['import']['import_id'];marker('cancelled');check('Qt cancel reflected at actual daemon',request()['hub']['import'] is None);upload();marker('staged');stop();core=None;marker('offline');core=start();out,err=ui.communicate(timeout=55)
            if ui.returncode:raise RuntimeError(err.decode()+out.decode())
            row=json.loads(out);checks.extend(row['checks']);(BASE/'target/evidence/b3-import.png').write_bytes((artifacts/'ui.png').read_bytes());stop();core=None
        finally:
            if ui.poll() is None:ui.kill();ui.wait(timeout=3)
    finally:
        if core is not None and core.poll() is None:core.terminate();core.wait(timeout=3);core.stderr.close()
result={'gate':'B3_2B_STAGING','passed':len(checks),'failed':0,'ignored':0,'checks':checks,'ui':row,'binary_sha256':hashlib.sha256(BIN.read_bytes()).hexdigest(),'scope':'opaque local staging only; no install/extraction/network/plugin execution','physical_validation':'NOT_PERFORMED'}
(BASE/'target/evidence/b3-import.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
