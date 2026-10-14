#!/usr/bin/env python3
"""Manifest-bound permission gate; private daemon/files and native Qt/S1 only."""
import hashlib,json,os,socket,subprocess,tempfile,time
from pathlib import Path
from ui_fixture import offscreen_command
BASE=Path(__file__).resolve().parents[1];BIN=BASE/'target/release/gideon-base';catalog=BASE/'tests/fixtures/hub.json';checks=[];rows=[]
def check(name,value):
    assert value,name
    checks.append(name)
with tempfile.TemporaryDirectory(prefix='gideon-b3-permissions-') as td:
    root=Path(td)/'core';counter=0;core=None
    env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td,'XDG_RUNTIME_DIR':td}
    args=[str(BIN),'--root',str(root),'--virtual-input','--commands-sandbox','--hub-catalog',str(catalog),hashlib.sha256(catalog.read_bytes()).hexdigest()]
    def start():
        p=subprocess.Popen(args,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);until=time.monotonic()+5
        while not (root/'core.sock').exists():
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
            s.settimeout(3);s.connect(str(root/'core.sock'));s.sendall((json.dumps({'version':1,'request_id':ident or f'approve_{counter}','op':op,**kw})+'\n').encode());data=b''
            while not data.endswith(b'\n'):data+=s.recv(65536)
        return json.loads(data)
    def approve(revision=0,**kw):return request('hub_approve',**{**valid,'revision':revision,**kw})
    def effect():
        request('text',raw='open brave');until=time.monotonic()+5
        while True:
            snap=request()
            if snap['state']=='idle' and snap['command'] is not None:break
            if time.monotonic()>until:raise TimeoutError(snap)
            time.sleep(.015)
        check('Base real effect still verified',snap['command']['receipt']['verified'])
    try:
        core=start();hub=request()['hub'];entry=hub['entries'][0]
        valid={'plugin_id':entry['plugin_id'],'manifest_sha256':entry['manifest_sha256'],'permissions':entry['permissions'],'publisher_unverified_ack':True}
        check('discovery does not create approval file',not (root/'hub-approvals.json').exists() and not entry['permissions_approved'])
        for fields,code in [({'publisher_unverified_ack':False},'publisher_ack_required'),({'plugin_id':'unknown'},'unknown_plugin'),({'plugin_id':'future_api'},'plugin_incompatible'),({'manifest_sha256':'0'*64},'manifest_mismatch'),({'permissions':['computer_control']},'permissions_mismatch'),({'permissions':[]},'permissions_mismatch'),({'grant':True},'invalid_message'),({'revision':1},'stale_hub_revision')]:
            check('reject '+code,approve(**fields)['code']==code)
        session=request('virtual_wake')['session_id'];check('busy approval refused',approve()['code']=='busy');check('cancel remains available',request('cancel',session_id=session)['code']=='ok')
        sentinel=Path(td)/'sentinel';sentinel.write_text('untouched');pending=root/'.hub-approvals.json.pending';pending.symlink_to(sentinel)
        failed=approve();check('unsafe pending file leaves effective state',failed['code']=='hub_storage_error' and failed['hub']['approval_revision']==0 and not failed['hub']['entries'][0]['permissions_approved'])
        check('sentinel preserved',sentinel.read_text()=='untouched');pending.unlink()
        before=(root/'config.json').read_bytes();approved=approve(ident='commit1')
        check('approval ack reflects persisted exact manifest',approved['code']=='ok' and approved['hub']['approval_revision']==1 and approved['hub']['entries'][0]['permissions_approved'])
        check('duplicate request fenced',approve(1,ident='commit1')['code']=='duplicate')
        check('already approved cannot widen',approve(1)['code']=='already_approved')
        check('private bounded approval file',(root/'hub-approvals.json').stat().st_mode&0o777==0o600 and (root/'hub-approvals.json').stat().st_size<=16384)
        check('approval does not install or authenticate publisher',not (root/'plugins').exists() and approved['hub']['entries'][0]['status']=='not_installed' and not approved['hub']['publisher_verified'])
        check('Base config intact',(root/'config.json').read_bytes()==before);effect();stop();core=start()
        check('actual restart keeps approval',request()['hub']['entries'][0]['permissions_approved'])
        stop();core=None
        changed=Path(td)/'changed-catalog.json';raw=json.loads(catalog.read_text());raw['plugins'][0]['permissions']=['network'];changed.write_text(json.dumps(raw));args[-2:]=[str(changed),hashlib.sha256(changed.read_bytes()).hexdigest()];core=start()
        check('new catalog cannot inherit approval',not request()['hub']['entries'][0]['permissions_approved'] and request()['hub']['approval_revision']==1);stop();core=None
        args[-2:]=[str(catalog),hashlib.sha256(catalog.read_bytes()).hexdigest()]
        state=root/'hub-approvals.json';original=state.read_bytes()
        for mode in ('invalid','unsafe_permissions','symlink','hardlink','oversized','fifo'):
            state.unlink();alias=None
            if mode=='symlink':state.symlink_to(sentinel)
            elif mode=='fifo':os.mkfifo(state,0o600)
            else:
                state.write_bytes(b'{}' if mode=='invalid' else b' '*16385 if mode=='oversized' else original);state.chmod(0o644 if mode=='unsafe_permissions' else 0o600)
                if mode=='hardlink':alias=Path(td)/'hard-alias';os.link(state,alias)
            core=start();snap=request();check(mode+' quarantines only Hub',snap['hub']['status']=='quarantined' and snap['configuration_status']=='ready')
            check(mode+' cannot approve',approve()['code']=='hub_unavailable');effect();stop();core=None
            if alias:alias.unlink()
        # Native Qt approval and real Core restart followed by full S1.
        root=Path(td)/'ui-core';args=[str(BIN),'--root',str(root),'--commands-sandbox','--hub-catalog',str(catalog),hashlib.sha256(catalog.read_bytes()).hexdigest(),'--base-pack',str(BASE/'target/base-pack-dev.json'),'--tts-virtual',str(BASE/'target/tts-venv/bin/python'),str(BASE/'target/a5-assets/manifest.json')]
        manifest=BASE/'target/a3-assets/replay-manifest.json';index=next(i for i,r in enumerate(json.loads(manifest.read_text())['fixtures']) if r['id']=='wake-hey-brave__bf_emma__clean');args+=['--wake-replay',str(BASE/'target/a1-venv/bin/python'),str(manifest),str(index)];core=start()
        artifacts=Path(td)/'artifacts';artifacts.mkdir();ui=subprocess.Popen(offscreen_command(root,artifacts,'permissions'),env={'PATH':'/usr/bin:/bin'},stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        def marker(name):
            until=time.monotonic()+55
            while not (artifacts/name).exists():
                if ui.poll() is not None:raise RuntimeError(ui.stderr.read().decode()+ui.stdout.read().decode())
                if time.monotonic()>until:raise TimeoutError(name)
                time.sleep(.02)
        try:
            marker('approved');stop();core=None;marker('offline');core=start()
            out,err=ui.communicate(timeout=55)
            if ui.returncode:raise RuntimeError(err.decode()+out.decode())
            row=json.loads(out);checks.extend(row['checks']);rows.append(row)
            (BASE/'target/evidence/b3-permissions.png').write_bytes((artifacts/'ui.png').read_bytes());stop();core=None
        finally:
            if ui.poll() is None:ui.kill();ui.wait(timeout=3)
    finally:
        if core is not None and core.poll() is None:core.terminate();core.wait(timeout=3);core.stderr.close()
result={'gate':'B3_2A_PERMISSIONS','passed':len(checks),'failed':0,'ignored':0,'checks':checks,'rows':rows,'binary_sha256':hashlib.sha256(BIN.read_bytes()).hexdigest(),'scope':'manifest-bound approval only; no installation/execution/publisher authentication','physical_validation':'NOT_PERFORMED'}
(BASE/'target/evidence/b3-permissions.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
