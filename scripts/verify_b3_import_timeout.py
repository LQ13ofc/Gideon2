#!/usr/bin/env python3
"""Exercise the actual 120s daemon import deadline without shortening product limits."""
import hashlib,json,os,socket,subprocess,tempfile,time
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];BIN=BASE/'target/release/gideon-base';CAT=BASE/'tests/fixtures/hub.json';checks=[]
def check(name,value):
    assert value,name
    checks.append(name)
with tempfile.TemporaryDirectory(prefix='gideon-import-deadline-') as td:
    root=Path(td)/'core';env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td,'XDG_RUNTIME_DIR':td}
    core=subprocess.Popen([str(BIN),'--root',str(root),'--hub-catalog',str(CAT),hashlib.sha256(CAT.read_bytes()).hexdigest()],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);counter=0
    def call(op='snapshot',**kw):
        global counter
        counter+=1
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(3);s.connect(str(root/'core.sock'));s.sendall((json.dumps({'version':1,'request_id':f'deadline_{counter}','op':op,**kw})+'\n').encode());data=b''
            while not data.endswith(b'\n'):data+=s.recv(65536)
        return json.loads(data)
    try:
        until=time.monotonic()+5
        while not (root/'core.sock').exists():
            if core.poll() is not None:raise RuntimeError(core.stderr.read().decode())
            if time.monotonic()>until:raise TimeoutError('startup')
            time.sleep(.01)
        entry=call()['hub']['entries'][0];fields={'plugin_id':entry['plugin_id'],'manifest_sha256':entry['manifest_sha256']}
        check('deadline fixture explicitly approved',call('hub_approve',revision=0,**fields,permissions=entry['permissions'],publisher_unverified_ack=True)['code']=='ok')
        snap=call('hub_begin',revision=1,**fields);active=snap['hub']['import']['import_id'];check('actual bounded import begins',snap['code']=='ok')
        pending=root/('.hub-'+entry['manifest_sha256']+'.pending');started=time.monotonic();stat=Path('/proc')/str(core.pid)/'stat';ticks0=sum(map(int,stat.read_text().split()[13:15]))
        # No snapshot request drives expiry: kernel/Tokio deadline is responsible.
        while pending.exists():
            if time.monotonic()-started>124:raise TimeoutError('actual import deadline')
            time.sleep(.1)
        elapsed=time.monotonic()-started;ticks1=sum(map(int,stat.read_text().split()[13:15]));snap=call()
        check('real daemon timer expires without client polling',119<=elapsed<=124 and snap['hub']['import'] is None)
        check('deadline retains Base readiness and metadata-only event',snap['configuration_status']=='ready' and any(e['kind']=='hub_import_timeout' for e in snap['events']))
        check('late chunk cannot resurrect expired transaction',call('hub_chunk',import_id=active,offset=0,hex='00')['code']=='stale_import')
        check('deadline never publishes incomplete payload',not list(root.glob('*.payload')))
        core.terminate();check('deadline daemon clean shutdown',core.wait(timeout=3)==0)
    finally:
        if core.poll() is None:core.terminate();core.wait(timeout=3)
        core.stderr.close()
result={'gate':'B3_2B_REAL_DEADLINE','passed':len(checks),'failed':0,'ignored':0,'checks':checks,'elapsed_seconds':elapsed,'daemon_cpu_ticks':ticks1-ticks0,'clock_ticks_per_second':os.sysconf('SC_CLK_TCK'),'binary_sha256':hashlib.sha256(BIN.read_bytes()).hexdigest()}
(BASE/'target/evidence/b3-import-timeout.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
