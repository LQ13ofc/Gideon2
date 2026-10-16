#!/usr/bin/env python3
"""Maximum supported opaque payload through real CLI/IPC/Core; private synthetic zeros."""
import hashlib,json,os,socket,subprocess,tempfile,time
from pathlib import Path
from process_fixture import resident_bytes
BASE=Path(__file__).resolve().parents[1];BIN=BASE/'target/release/gideon-base';checks=[]
def check(name,value):
    assert value,name
    checks.append(name)
with tempfile.TemporaryDirectory(prefix='gideon-import-capacity-') as td:
    td=Path(td);root=td/'core';source=td/'synthetic.bin';size=67108864;block=bytes(1048576);digest=hashlib.sha256()
    with source.open('wb') as file:
        for _ in range(64):file.write(block);digest.update(block)
    expected=digest.hexdigest();catalog=json.loads((BASE/'tests/fixtures/hub.json').read_text());catalog['plugins'][0]['binaries'][0].update(size=size,sha256=expected);path=td/'catalog.json';path.write_text(json.dumps(catalog))
    env={'PATH':'/usr/bin:/bin','HOME':str(td),'XDG_CONFIG_HOME':str(td),'XDG_DATA_HOME':str(td),'XDG_CACHE_HOME':str(td),'XDG_RUNTIME_DIR':str(td)}
    core=subprocess.Popen([str(BIN),'--root',str(root),'--hub-catalog',str(path),hashlib.sha256(path.read_bytes()).hexdigest()],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);counter=0;client=None
    def call(op='snapshot',**kw):
        global counter
        counter+=1
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(5);s.connect(str(root/'core.sock'));s.sendall((json.dumps({'version':1,'request_id':f'capacity_{counter}','op':op,**kw})+'\n').encode());data=b''
            while not data.endswith(b'\n'):data+=s.recv(65536)
        return json.loads(data)
    try:
        until=time.monotonic()+5
        while not (root/'core.sock').exists():
            if core.poll() is not None:raise RuntimeError(core.stderr.read().decode())
            if time.monotonic()>until:raise TimeoutError('startup')
            time.sleep(.01)
        e=call()['hub']['entries'][0];check('upper boundary catalog accepted',e['download_size']==size and e['status']=='not_installed')
        check('explicit synthetic payload approval',call('hub_approve',revision=0,plugin_id=e['plugin_id'],manifest_sha256=e['manifest_sha256'],permissions=e['permissions'],publisher_unverified_ack=True)['code']=='ok')
        started=time.monotonic();peak=resident_bytes(core.pid);client=subprocess.Popen(['python3',str(BASE/'scripts/hub_import.py'),'--root',str(root),'--plugin',e['plugin_id'],'--source',str(source)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        while client.poll() is None:
            peak=max(peak,resident_bytes(core.pid))
            if time.monotonic()-started>125:raise TimeoutError('capacity upload')
            time.sleep(.01)
        out,err=client.communicate();elapsed=time.monotonic()-started
        check('real CLI maximum upload completed',client.returncode==0);final=json.loads(out)
        check('maximum payload staged before absolute deadline',elapsed<120 and final['hub']['entries'][0]['payload_staged'] and final['hub']['import'] is None)
        payload=root/('hub-'+e['manifest_sha256']+'.payload');observed=hashlib.sha256()
        with payload.open('rb') as file:
            while chunk:=file.read(8192):observed.update(chunk)
        check('actual stored maximum bytes match pinned digest',payload.stat().st_size==size and observed.hexdigest()==expected)
        check('Core maximum import RSS bounded below 32MiB',peak<33554432)
        check('maximum payload remains opaque uninstalled nonexecutable',final['hub']['entries'][0]['status']=='not_installed' and payload.stat().st_mode&0o777==0o600 and not final['hub']['publisher_verified'])
        core.terminate();check('capacity daemon clean shutdown',core.wait(timeout=3)==0)
    finally:
        if client is not None and client.poll() is None:client.kill();client.wait(timeout=3)
        if core.poll() is None:core.terminate();core.wait(timeout=3)
        core.stderr.close()
result={'gate':'B3_2B_CAPACITY','passed':len(checks),'failed':0,'ignored':0,'checks':checks,'bytes':size,'upload_seconds':elapsed,'peak_core_rss_bytes':peak,'scope':'synthetic opaque zeros, isolated Core/CLI; no native inference or physical audio','binary_sha256':hashlib.sha256(BIN.read_bytes()).hexdigest()}
(BASE/'target/evidence/b3-import-capacity.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
