#!/usr/bin/env python3
"""Private real Core B3.3 install/update/rollback/remove/quarantine gate with Qt and native S1 regressions."""
import hashlib,json,os,socket,stat,subprocess,tempfile,time
from pathlib import Path
from hub_import import upload as stage_upload
from ui_fixture import offscreen_command
BASE=Path(__file__).resolve().parents[1];BIN=BASE/'target/release/gideon-base';CAT1=BASE/'tests/fixtures/hub.json';CAT2=BASE/'tests/fixtures/hub-v2.json';BENIGN='benign_fixture';checks=[];FAILURES=[];IGNORED=[]
B3_UI_REQUIRED = ["actual Core connection", "accessible cancel name", "minimum layout size respected", "Core ledger shows fixture installed with runtime disabled", "status label shows installed and disabled", "install control unavailable once installed", "rollback unavailable without previous version", "remove control available for installed plugin", "restart preserves installed disabled record", "restarted UI keeps disabled status", "remove requires confirmation and does not act yet", "cancelled removal keeps installed record", "Qt removal confirmed reaches Core ledger", "hub result label shows Plugin removido"]
def check(name,value):
    if not value:
        FAILURES.append(name);raise AssertionError(name)
    checks.append(name)
def accept_ui_row(row):
    names=(row or {}).get('checks') or []
    missing=sorted(set(B3_UI_REQUIRED)-set(names))
    ok=bool(row) and row.get('failed')==0 and row.get('passed')==len(names) and bool(names) and not missing
    check('B3 UI self-report accepted (zero failures, passed equals listed, every required check present; missing '+str(missing)+')',ok)
    checks.extend(names)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def base_args(root,catalog,extra=()):return [str(BIN),'--root',str(root),*extra,'--commands-sandbox','--hub-catalog',str(catalog),sha(catalog)]
def entry_of(h,pid=BENIGN):return next(e for e in h['entries'] if e['plugin_id']==pid)
def record(h,pid=BENIGN):return next((r for r in h['installed'] if r['plugin_id']==pid),None)
def kinds(s):return [e['kind'] for e in s.get('events',[])]
counter=[0]
def req(root,op='snapshot',**fields):
    counter[0]+=1
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(5);s.connect(str(Path(root)/'core.sock'));s.sendall((json.dumps({'version':1,'request_id':f'life_{counter[0]}','op':op,**fields})+'\n').encode());data=b''
        while not data.endswith(b'\n'):
            chunk=s.recv(65536)
            if not chunk:raise RuntimeError('Core disconnected')
            data+=chunk
    return json.loads(data)
def hub(root):return req(root)['hub']
def approve(root,pid=BENIGN):
    h=hub(root);e=entry_of(h,pid)
    return req(root,'hub_approve',revision=h['approval_revision'],plugin_id=pid,manifest_sha256=e['manifest_sha256'],permissions=e['permissions'],publisher_unverified_ack=True)
def op(root,name,pid=BENIGN,revision=None,**fields):
    rev=hub(root)['install_revision'] if revision is None else revision
    return req(root,name,revision=rev,plugin_id=pid,**fields)
def install(root,manifest=None,revision=None,pid=BENIGN):
    m=entry_of(hub(root),pid)['manifest_sha256'] if manifest is None else manifest
    return op(root,'hub_install',pid,revision,manifest_sha256=m)
def start(args,root,env):
    p=subprocess.Popen(args,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);until=time.monotonic()+5
    while True:
        try:
            with socket.socket(socket.AF_UNIX) as probe:probe.connect(str(Path(root)/'core.sock'))
            break
        except (FileNotFoundError,ConnectionRefusedError):pass
        if p.poll() is not None:raise RuntimeError(p.stderr.read().decode())
        if time.monotonic()>until:p.terminate();p.wait();raise TimeoutError('startup')
        time.sleep(.01)
    return p
def stop(p):
    p.terminate();check('clean shutdown',p.wait(timeout=3)==0);p.stderr.close()
def effect(root,name):
    before=req(root)['command'];req(root,'text',raw='open brave');until=time.monotonic()+5
    while True:
        s=req(root)
        if s['state']=='idle' and s['command'] is not None and s['command']!=before:break
        if time.monotonic()>until:raise TimeoutError(s)
        time.sleep(.015)
    check(name,s['command']['receipt']['verified'])
def native_effect(root,name):
    until=time.monotonic()+30
    while True:
        s=req(root)
        if s['state']=='idle' and s['command'] is not None and s['command'].get('code')=='command_success' and s.get('wake_status')=='replay_finished':break
        if time.monotonic()>until:raise TimeoutError(s)
        time.sleep(.015)
    check(name,s['command']['receipt']['verified'])
with tempfile.TemporaryDirectory(prefix='gideon-b3-lifecycle-') as td:
    env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td,'XDG_RUNTIME_DIR':td}
    source=Path(td)/'fixture.bin';source.write_bytes(b'benign fixture\n');sentinel=Path(td)/'sentinel';sentinel.write_bytes(b'preserved')
    root=Path(td)/'core';ns=root/'hub-plugins';core=None
    try:
        # Scenario 1: catalog v1 install lifecycle, preconditions first.
        core=start(base_args(root,CAT1,('--virtual-input',)),root,env)
        h=hub(root);e1=entry_of(h);m1=e1['manifest_sha256']
        check('catalog v1 benign not installed before lifecycle',e1['status']=='not_installed' and h['installed']==[])
        check('explicit manifest approval accepted',approve(root)['code']=='ok')
        stage_upload(str(root),BENIGN,str(source))
        h=hub(root);check('payload staged before install',entry_of(h)['payload_staged'] and h['installed']==[])
        check('install rejects stale revision',install(root,revision=h['install_revision']+1)['code']=='stale_install_revision')
        check('install rejects wrong manifest',install(root,manifest='0'*64)['code']=='manifest_mismatch')
        check('install rejects unknown plugin',install(root,pid='unknown',manifest=m1)['code']=='unknown_plugin')
        check('install ok',install(root)['code']=='ok')
        s=req(root);h=s['hub'];check('event hub_plugin_installed emitted','hub_plugin_installed' in kinds(s))
        dest=ns/f'{BENIGN}-{m1}.payload';staged=root/f'hub-{m1}.payload';rec=record(h)
        check('hub-plugins namespace private dir',stat.S_IMODE(ns.stat().st_mode)==0o700 and not ns.is_symlink())
        check('installed payload 0600 nlink 1 with exact bytes',stat.S_IMODE(dest.stat().st_mode)==0o600 and dest.stat().st_nlink==1 and dest.read_bytes()==source.read_bytes())
        check('staged payload consumed by install',not staged.exists())
        check('entry status installed',entry_of(h)['status']=='installed')
        check('installed record runtime disabled, previous null',rec['state']=='installed' and rec['runtime']=='disabled' and rec['semver']=='1.0.0' and rec['previous'] is None)
        check('second install already_installed',install(root)['code']=='already_installed')
        check('rollback without previous refused',op(root,'hub_rollback')['code']=='no_previous_version')
        effect(root,'Base effect verified after install')
        # Scenario 3: restart with same root preserves installed state.
        stop(core);core=start(base_args(root,CAT1,('--virtual-input',)),root,env)
        rec=record(hub(root));check('restart preserves installed v1',rec is not None and rec['semver']=='1.0.0' and rec['state']=='installed' and dest.exists())
        # Scenario 4: catalog v2 pinned at restart; update, rollback, rollback again.
        stop(core);core=start(base_args(root,CAT2,('--virtual-input',)),root,env)
        h=hub(root);e2=entry_of(h);m2=e2['manifest_sha256']
        check('catalog v2 entry update_available',e2['status']=='update_available' and e2['semver']=='1.1.0' and m2!=m1)
        check('v2 approval accepted',approve(root)['code']=='ok')
        imp=req(root,'hub_begin',revision=hub(root)['approval_revision'],plugin_id=BENIGN,manifest_sha256=m2)
        check('v2 import begins',imp['code']=='ok')
        check('active import makes install hub_import_busy',install(root)['code']=='hub_import_busy')
        check('abort v2 import',req(root,'hub_abort',import_id=imp['hub']['import']['import_id'])['code']=='ok')
        stage_upload(str(root),BENIGN,str(source))
        check('v2 payload staged',entry_of(hub(root))['payload_staged'])
        check('update install ok',install(root)['code']=='ok')
        s=req(root);rec=record(s['hub']);check('event hub_plugin_updated emitted','hub_plugin_updated' in kinds(s))
        check('update active 1.1.0 previous 1.0.0',rec['semver']=='1.1.0' and rec['manifest_sha256']==m2 and rec['previous']['semver']=='1.0.0' and rec['previous']['manifest_sha256']==m1)
        check('previous v1 payload kept',(ns/f'{BENIGN}-{m1}.payload').exists())
        check('rollback ok',op(root,'hub_rollback')['code']=='ok')
        s=req(root);rec=record(s['hub']);check('rollback active 1.0.0 previous 1.1.0','hub_plugin_rolled_back' in kinds(s) and rec['semver']=='1.0.0' and rec['previous']['semver']=='1.1.0')
        check('rollback again ok',op(root,'hub_rollback')['code']=='ok')
        rec=record(hub(root));check('second rollback back to 1.1.0',rec['semver']=='1.1.0' and rec['previous']['semver']=='1.0.0')
        stop(core);core=start(base_args(root,CAT2,('--virtual-input',)),root,env)
        rec=record(hub(root));check('restart preserves rolled state',rec['semver']=='1.1.0' and rec['state']=='installed')
        # Scenario 5: tamper active file, quarantine only Hub plugin, remove recovers.
        stop(core);dest2=ns/f'{BENIGN}-{m2}.payload'
        with dest2.open('ab') as f:f.write(b'!')
        core=start(base_args(root,CAT2,('--virtual-input',)),root,env)
        h=hub(root);rec=record(h);check('tampered active quarantines plugin only',rec['state']=='quarantined' and h['status']=='verified')
        check('Base snapshot answers after quarantine',req(root)['code']=='ok')
        effect(root,'Base effect verified after quarantine')
        check('rollback refused on quarantined plugin',op(root,'hub_rollback')['code']=='plugin_quarantined')
        check('remove works on quarantined plugin',op(root,'hub_remove')['code']=='ok')
        s=req(root);check('remove leaves installed empty and emits event','hub_plugin_removed' in kinds(s) and s['hub']['installed']==[])
        check('remove unlinks both recorded payloads',not dest2.exists() and not (ns/f'{BENIGN}-{m1}.payload').exists())
        stop(core);core=None
        # Scenario 6: symlink, hardlink, permission tamper variants on fresh roots.
        for mode in ['symlink','hardlink','permissions']:
            vroot=Path(td)/('variant-'+mode);core=start(base_args(vroot,CAT1,('--virtual-input',)),vroot,env)
            check(mode+' variant approved',approve(vroot)['code']=='ok');stage_upload(str(vroot),BENIGN,str(source));check(mode+' variant installed',install(vroot)['code']=='ok')
            stop(core);vd=vroot/'hub-plugins'/f'{BENIGN}-{m1}.payload';vd.unlink()
            if mode=='symlink':vd.symlink_to(sentinel)
            elif mode=='hardlink':os.link(sentinel,vd)
            else:vd.write_bytes(source.read_bytes());os.chmod(vd,0o644)
            core=start(base_args(vroot,CAT1,('--virtual-input',)),vroot,env)
            h=hub(vroot);rec=record(h);check(mode+' tamper quarantines only that plugin',rec['state']=='quarantined' and h['status']=='verified' and len(h['installed'])==1)
            effect(vroot,mode+' variant Base still verified')
            stop(core);core=None
        # Scenario 7: ledger corruption quarantines Hub, Base keeps answering.
        lroot=Path(td)/'ledger';core=start(base_args(lroot,CAT1,('--virtual-input',)),lroot,env)
        approve(lroot);stage_upload(str(lroot),BENIGN,str(source));install(lroot)
        stop(core);ledger=lroot/'hub-installed.json';orig=ledger.read_bytes()
        for name,data,mode_bits in [('invalid json',b'{"version":',0o600),('unknown field',json.dumps({**json.loads(orig),'unexpected':True}).encode(),0o600),('mode 0644',orig,0o644)]:
            ledger.write_bytes(data);ledger.chmod(mode_bits);core=start(base_args(lroot,CAT1,('--virtual-input',)),lroot,env)
            check('ledger '+name+' quarantines Hub',hub(lroot)['status']=='quarantined' and core.poll() is None)
            check('ledger '+name+' Base snapshot answers',req(lroot)['code']=='ok')
            effect(lroot,'ledger '+name+' Base effect verified')
            stop(core);ledger.write_bytes(orig);ledger.chmod(0o600);core=None
        # Scenario 8: pre-existing foreign destination fails closed.
        croot=Path(td)/'collision';core=start(base_args(croot,CAT1,('--virtual-input',)),croot,env)
        approve(croot);stage_upload(str(croot),BENIGN,str(source))
        cns=croot/'hub-plugins';cns.mkdir(mode=0o700,exist_ok=True);foreign=cns/f'{BENIGN}-{m1}.payload';foreign.write_bytes(b'foreign');os.chmod(foreign,0o600)
        check('namespace collision fails closed',install(croot)['code']=='hub_storage_error')
        check('foreign collision bytes unchanged',foreign.read_bytes()==b'foreign' and core.poll() is None)
        stop(core);core=None
        # Scenario 9: native S1 before/after plus Qt lifecycle.
        native=Path(td)/'native';manifest=BASE/'target/a3-assets/replay-manifest.json';index=next(i for i,r in enumerate(json.loads(manifest.read_text())['fixtures']) if r['id']=='wake-hey-brave__bf_emma__clean')
        nargs=base_args(native,CAT1)+['--base-pack',str(BASE/'target/base-pack-dev.json'),'--tts-virtual',str(BASE/'target/tts-venv/bin/python'),str(BASE/'target/a5-assets/manifest.json'),'--wake-replay',str(BASE/'target/a1-venv/bin/python'),str(manifest),str(index)]
        core=start(nargs,native,env);native_effect(native,'native S1 before lifecycle')
        artifacts=Path(td)/'artifacts';artifacts.mkdir();ui=subprocess.Popen(offscreen_command(native,artifacts,'lifecycle'),env={'PATH':'/usr/bin:/bin'},stdout=subprocess.PIPE,stderr=subprocess.PIPE);row=None
        def marker(name):
            until=time.monotonic()+55
            while not (artifacts/name).exists():
                if ui.poll() is not None:raise RuntimeError(ui.stderr.read().decode()+ui.stdout.read().decode())
                if time.monotonic()>until:raise TimeoutError(name)
                time.sleep(.02)
        try:
            marker('ready');approve(native);stage_upload(str(native),BENIGN,str(source));check('native lifecycle install ok',install(native)['code']=='ok');marker('installed')
            stop(core);marker('offline');core=start(nargs,native,env);out,err=ui.communicate(timeout=55)
            if ui.returncode:raise RuntimeError(err.decode()+out.decode())
            row=json.loads(out);accept_ui_row(row);(BASE/'target/evidence/b3-lifecycle.png').write_bytes((artifacts/'ui.png').read_bytes())
            check('Qt removal persisted at daemon',record(hub(native)) is None)
            check('Qt removal unlinked namespace payload',not any((native/'hub-plugins').glob(f'{BENIGN}-*.payload')))
            native_effect(native,'native S1 after lifecycle and restart');stop(core);core=None
        finally:
            if ui.poll() is None:ui.kill();ui.wait(timeout=3)
    finally:
        if core is not None and core.poll() is None:core.terminate();core.wait(timeout=3);core.stderr.close()
result={'gate':'B3_3_LIFECYCLE','passed':len(checks),'failed':len(FAILURES),'ignored':len(IGNORED),'checks':checks,'ui':row,'binary_sha256':sha(BIN),'scope':'local opaque install/update/rollback/remove only; no extraction, loading, execution, network or plugin runtime; runtime disabled','physical_validation':'NOT_PERFORMED'}
(BASE/'target/evidence/b3-lifecycle.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
