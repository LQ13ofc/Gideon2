#!/usr/bin/env python3
"""Real private Core/IPC/Qt/native S1 catalog gate; no remote or plugin runtime."""
import hashlib,json,os,socket,subprocess,tempfile,time
from pathlib import Path
from ui_fixture import offscreen_command
BASE=Path(__file__).resolve().parents[1];BIN=BASE/'target/release/gideon-base'
fixture=(BASE/'tests/fixtures/hub.json').read_bytes();digest=hashlib.sha256(fixture).hexdigest();checks=[];rows=[]
def check(name,value):
    assert value,name
    checks.append(name)
for mode in ('verified','checksum','malformed','symlink','fifo','oversized','native','native_quarantine'):
    with tempfile.TemporaryDirectory(prefix='gideon-b3-catalog-') as td:
        root=Path(td)/'core';catalog=Path(td)/'catalog.json';catalog.write_bytes(fixture);expected=digest
        if mode in ('checksum','native_quarantine'):expected='0'*64
        if mode=='malformed':catalog.write_bytes(b'{}');expected=hashlib.sha256(catalog.read_bytes()).hexdigest()
        if mode=='symlink':alias=Path(td)/'alias';alias.symlink_to(catalog);catalog=alias
        if mode=='fifo':catalog.unlink();os.mkfifo(catalog)
        if mode=='oversized':catalog.write_bytes(b' '*65537);expected=hashlib.sha256(catalog.read_bytes()).hexdigest()
        args=[str(BIN),'--root',str(root),'--commands-sandbox','--hub-catalog',str(catalog),expected]
        if mode.startswith('native'):
            manifest=BASE/'target/a3-assets/replay-manifest.json';index=next(i for i,r in enumerate(json.loads(manifest.read_text())['fixtures']) if r['id']=='wake-hey-brave__bf_emma__clean')
            args+=['--base-pack',str(BASE/'target/base-pack-dev.json'),'--tts-virtual',str(BASE/'target/tts-venv/bin/python'),str(BASE/'target/a5-assets/manifest.json'),'--wake-replay',str(BASE/'target/a1-venv/bin/python'),str(manifest),str(index)]
        else:args+=['--virtual-input']
        env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td,'XDG_RUNTIME_DIR':td}
        core=subprocess.Popen(args,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);counter=0
        def request(op='snapshot',**kw):
            global counter
            counter+=1
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(3);s.connect(str(root/'core.sock'));s.sendall((json.dumps({'version':1,'request_id':f'hub_{counter}','op':op,**kw})+'\n').encode());data=b''
                while not data.endswith(b'\n'):data+=s.recv(65536)
            return json.loads(data)
        try:
            until=time.monotonic()+5
            while not (root/'core.sock').exists():
                if core.poll() is not None:raise RuntimeError(core.stderr.read().decode())
                if time.monotonic()>until:raise TimeoutError('startup')
                time.sleep(.01)
            snap=request();hub=snap['hub'];verified=mode in ('verified','native')
            check(mode+' catalog state is truthful',hub['status']==('verified' if verified else 'quarantined') and not hub['publisher_verified'])
            check(mode+' catalog has no private paths',td not in json.dumps(hub) and 'entrypoint' not in hub)
            check(mode+' catalog does not grant plugin authority',request('hub_install',plugin_id='benign_fixture',grant=True)['code']=='invalid_message')
            if mode.startswith('native'):
                artifacts=Path(td)/'artifacts';artifacts.mkdir();phase='hub' if verified else 'hub_quarantine'
                ui=subprocess.run(offscreen_command(root,artifacts,phase),env={'PATH':'/usr/bin:/bin'},capture_output=True,timeout=55)
                if ui.returncode:raise RuntimeError(ui.stderr.decode()+ui.stdout.decode())
                row=json.loads(ui.stdout);checks.extend(row['checks']);rows.append(row)
                (BASE/'target/evidence'/('b3-'+phase+'.png')).write_bytes((artifacts/'ui.png').read_bytes())
            else:
                check(mode+' Base remains ready',snap['configuration_status']=='ready')
                request('text',raw='open brave');until=time.monotonic()+5
                while True:
                    snap=request()
                    if snap['state']=='idle' and snap['command'] is not None:break
                    if time.monotonic()>until:raise TimeoutError(snap)
                    time.sleep(.015)
                check(mode+' real command effect survives Hub failure',snap['command']['receipt']['verified'])
                check(mode+' uninstalled catalog is not executable',not (root/'plugins').exists())
            core.terminate();check(mode+' clean shutdown',core.wait(timeout=3)==0)
        finally:
            if core.poll() is None:core.terminate();core.wait(timeout=3)
            core.stderr.close()
result={'gate':'B3_1_CATALOG','passed':len(checks),'failed':0,'ignored':0,'checks':checks,'rows':rows,'binary_sha256':hashlib.sha256(BIN.read_bytes()).hexdigest(),'fixture_sha256':digest,'scope':'offline catalog discovery, real Core and native S1/Qt; no installation, network or plugin execution','physical_validation':'NOT_PERFORMED'}
(BASE/'target/evidence/b3-catalog.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
