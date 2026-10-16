#!/usr/bin/env python3
"""Private real Core C0 plugin runtime gate: dummy_echo/dummy_evil in bwrap, Qt plugins phase, native S1 regressions."""
import hashlib,json,os,socket,stat,subprocess,sys,tempfile,time,traceback
from pathlib import Path
from hub_import import upload as stage_upload
from ui_fixture import offscreen_command
BASE=Path(__file__).resolve().parents[1];BIN=BASE/'target/release/gideon-base';CATALOG=BASE/'tests/fixtures/hub-c0.json'
ECHO_SRC=BASE/'tests/fixtures/dummy_echo.py';EVIL_SRC=BASE/'tests/fixtures/dummy_evil.py';EVIDENCE=BASE/'target/evidence'
ECHO='dummy_echo';EVIL='dummy_evil';OPAQUE='plain_opaque';ECHO_CAP='dummy_echo.echo';EVIL_CAP='dummy_evil.probe'
PYTHON='/usr/bin/python3';OPAQUE_PAYLOAD=b'benign fixture\n';PLUGIN_MARK=b'/plugin/main.py';CLK=os.sysconf('SC_CLK_TCK')
PROBE_EXPECT={'network':'denied','read_home':'denied','read_repo':'denied','write_root':'denied','fork_bomb_limited':'denied','env':'denied','mem':'denied'}
ARGV_MODES=['ignore_cancel','crash','bad_json','oversize','dup_id','log_flood']
checks=[];ignored=[];details={};counter=[0];live=[]
def check(name,value):
    assert value,name
    checks.append(name)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def base_args(root,catalog,extra=()):return [str(BIN),'--root',str(root),*extra,'--commands-sandbox','--hub-catalog',str(catalog),sha(catalog)]
def core_args(root):
    manifest=BASE/'target/a3-assets/replay-manifest.json';index=next(i for i,r in enumerate(json.loads(manifest.read_text())['fixtures']) if r['id']=='wake-hey-brave__bf_emma__clean')
    return base_args(root,CATALOG)+['--plugin-python',PYTHON,'--base-pack',str(BASE/'target/base-pack-dev.json'),'--tts-virtual',str(BASE/'target/tts-venv/bin/python'),str(BASE/'target/a5-assets/manifest.json'),'--wake-replay',str(BASE/'target/a1-venv/bin/python'),str(manifest),str(index)]
def entry_of(h,pid):return next(e for e in h['entries'] if e['plugin_id']==pid)
def record(h,pid):return next((r for r in h['installed'] if r['plugin_id']==pid),None)
def req(root,op='snapshot',**fields):
    counter[0]+=1
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(5);s.connect(str(Path(root)/'core.sock'));s.sendall((json.dumps({'version':1,'request_id':f'c0_{counter[0]}','op':op,**fields})+'\n').encode());data=b''
        while not data.endswith(b'\n'):
            chunk=s.recv(65536)
            if not chunk:raise RuntimeError('Core disconnected')
            data+=chunk
    return json.loads(data)
def hub(root):return req(root)['hub']
def approve(root,pid):
    h=hub(root);e=entry_of(h,pid)
    return req(root,'hub_approve',revision=h['approval_revision'],plugin_id=pid,manifest_sha256=e['manifest_sha256'],permissions=e['permissions'],publisher_unverified_ack=True)
def op(root,name,pid,revision=None,**fields):
    rev=hub(root)['install_revision'] if revision is None else revision
    return req(root,name,revision=rev,plugin_id=pid,**fields)
def install(root,pid):
    return op(root,'hub_install',pid,manifest_sha256=entry_of(hub(root),pid)['manifest_sha256'])
def plugin_op(root,name,pid):
    return req(root,name,revision=req(root)['plugins']['revision'],plugin_id=pid)
def plugin_item(s,pid):return next((i for i in s['plugins']['items'] if i['plugin_id']==pid),None)
def wait_snapshot(root,predicate,seconds,label):
    until=time.monotonic()+seconds
    while True:
        s=req(root)
        if predicate(s):return s
        if time.monotonic()>until:raise TimeoutError(label)
        time.sleep(.02)
def wait_state(root,pid,state,seconds=10):
    return wait_snapshot(root,lambda s:plugin_item(s,pid) is not None and plugin_item(s,pid)['state']==state,seconds,f'{pid} state {state}')
def submit(root,capability,input_value,deadline_ms):
    return req(root,'capability_invoke',capability=capability,input=input_value,deadline_ms=deadline_ms)['code']
def result(root,seconds=20):
    return wait_snapshot(root,lambda s:s.get('capability_result') is not None,seconds,'capability_result')['capability_result']
def invoke(root,capability,input_value,deadline_ms=2000):
    code=submit(root,capability,input_value,deadline_ms)
    return (code,result(root) if code=='ok' else None)
def ledger(root,name):
    path=Path(root)/name
    return json.loads(path.read_text()) if path.exists() else None
def table():
    out={}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():continue
        try:
            fields=(entry/'stat').read_text().rsplit(')',1)[1].split()
            out[int(entry.name)]=(int(fields[1]),fields[0],(entry/'cmdline').read_bytes().split(b'\0'))
        except OSError:continue
    return out
def descendants(root_pid):
    t=table();children={}
    for pid,(ppid,_,_) in t.items():children.setdefault(ppid,[]).append(pid)
    found=[];todo=[root_pid]
    while todo:
        for child in children.get(todo.pop(),[]):found.append(child);todo.append(child)
    return {pid:t[pid] for pid in found if pid in t and t[pid][1]!='Z'}
def plugin_refs(core_pid):return [pid for pid,(_,_,argv) in descendants(core_pid).items() if any(PLUGIN_MARK in a for a in argv)]
def plugin_workers(core_pid):return [pid for pid,(_,_,argv) in descendants(core_pid).items() if len(argv)==4 and argv[1]==b'-I' and argv[2]==PLUGIN_MARK]
def alive_plugin(pid):
    try:
        fields=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split();argv=(Path('/proc')/str(pid)/'cmdline').read_bytes()
        return fields[0]!='Z' and PLUGIN_MARK in argv
    except OSError:return False
def plugin_refs_in(pids):return [p for p in pids if alive_plugin(p)]
def wait_plugins_gone(pids,label,seconds=8):
    until=time.monotonic()+seconds
    while any(alive_plugin(p) for p in pids):
        if time.monotonic()>until:raise TimeoutError(label)
        time.sleep(.05)
def ticks(pid):
    try:fields=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split();return int(fields[11])+int(fields[12])
    except OSError:return 0
def start(args,root,env):
    p=subprocess.Popen(args,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);live.append(p);until=time.monotonic()+5
    while True:
        try:
            with socket.socket(socket.AF_UNIX) as probe:probe.connect(str(Path(root)/'core.sock'))
            break
        except (FileNotFoundError,ConnectionRefusedError):pass
        if p.poll() is not None:raise RuntimeError(p.stderr.read().decode())
        if time.monotonic()>until:p.terminate();p.wait();raise TimeoutError('startup')
        time.sleep(.01)
    return p
def stop(p,label):
    workers=plugin_workers(p.pid)+plugin_refs(p.pid);p.terminate();rc=p.wait(timeout=10);p.stderr.close();live.remove(p)
    check(f'{label} Core clean shutdown rc 0 with {len(set(plugin_refs_in(workers)))} plugin-related processes',rc==0)
    wait_plugins_gone(set(workers),label+' leftover plugin processes')
    check(f'{label} no plugin processes left after Core shutdown',not any(alive_plugin(w) for w in workers))
    return set(workers)
def native_effect(root,name):
    until=time.monotonic()+30
    while True:
        s=req(root)
        if s['state']=='idle' and s['command'] is not None and s['command'].get('code')=='command_success' and s.get('wake_status')=='replay_finished':break
        if time.monotonic()>until:raise TimeoutError(s)
        time.sleep(.015)
    check(name,s['command']['receipt']['verified'])
def run_ui(root,td):
    artifacts=Path(td)/'artifacts';artifacts.mkdir()
    ui=subprocess.Popen(offscreen_command(root,artifacts,'plugins'),env={'PATH':'/usr/bin:/bin'},stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    def marker(name):
        until=time.monotonic()+55
        while not (artifacts/name).exists():
            if ui.poll() is not None:raise RuntimeError(ui.stderr.read().decode()+ui.stdout.read().decode())
            if time.monotonic()>until:raise TimeoutError(name)
            time.sleep(.02)
    try:
        marker('ready');marker('revoked')
        # The phase does not wait for the gate, so only sticky Core events are read here; file and state checks run in scenario 3.
        kinds=[e['kind'] for e in req(root)['events']]
        check('Qt revoke reached Core: plugin_revoked event recorded','plugin_revoked' in kinds)
        marker('reapproved');out,err=ui.communicate(timeout=60)
        if ui.returncode:raise RuntimeError(err.decode()+out.decode())
        row=json.loads(out);(EVIDENCE/'c0-plugins.png').write_bytes((artifacts/'ui.png').read_bytes())
        return row
    finally:
        if ui.poll() is None:ui.kill();ui.wait(timeout=3)
def gate(td,env,record_out):
    td=Path(td);root1=td/'core1';root=root1;row=None;core=None
    plain=td/'plain_opaque.bin';plain.write_bytes(OPAQUE_PAYLOAD)
    try:
        # Scenario 1: catalog and opaque plugin refusal.
        core=start(core_args(root),root,env);h=hub(root)
        check('C0 catalog verified with 3 entries',h['status']=='verified' and len(h['entries'])==3)
        check('C0 catalog sha256 pinned at Core boot',h['catalog_sha256']==sha(CATALOG))
        check('dummy_echo declares python3_script runtime and dummy_echo.echo',entry_of(h,ECHO)['runtime']=='python3_script' and entry_of(h,ECHO)['capabilities']==[ECHO_CAP])
        check('plain_opaque is opaque (no runtime)',entry_of(h,OPAQUE).get('runtime') is None)
        check('plain_opaque approve ok',approve(root,OPAQUE)['code']=='ok')
        stage_upload(str(root),OPAQUE,str(plain));check('plain_opaque install ok',install(root,OPAQUE)['code']=='ok')
        check('plain_opaque enable refused plugin_not_runnable',plugin_op(root,'plugin_enable',OPAQUE)['code']=='plugin_not_runnable')
        native_effect(root,'native S1 before any plugin enabled')
        # Gate prerequisite for Qt phase: dummy_echo approved, staged and installed over IPC.
        check('dummy_echo approve ok',approve(root,ECHO)['code']=='ok')
        stage_upload(str(root),ECHO,str(ECHO_SRC));check('dummy_echo install ok',install(root,ECHO)['code']=='ok')
        check('dummy_echo installed disabled before enable',plugin_item(req(root),ECHO)['state']=='disabled')
        # Scenario 2: enable, invoke, errors, timeout, cancel.
        check('dummy_echo enable ok',plugin_op(root,'plugin_enable',ECHO)['code']=='ok')
        wait_state(root,ECHO,'running')
        code,cr=invoke(root,ECHO_CAP,{'text':'hello'})
        check('capability_invoke text ok',code=='ok')
        check('dummy_echo uppercases text with count',cr['ok'] and cr['output']['text']=='HELLO' and cr['output']['count']>=1)
        check('invoke unknown capability => unknown_capability',req(root,'capability_invoke',capability='dummy_echo.nope',input={'text':'x'},deadline_ms=1000)['code']=='unknown_capability')
        check('non-object input => invalid_input (Core)',req(root,'capability_invoke',capability=ECHO_CAP,input='not-object',deadline_ms=1000)['code']=='invalid_input')
        check('deadline_ms 0 => invalid_input (Core)',req(root,'capability_invoke',capability=ECHO_CAP,input={'text':'x'},deadline_ms=0)['code']=='invalid_input')
        check('oversize input 9000 bytes => invalid_input (Core)',req(root,'capability_invoke',capability=ECHO_CAP,input={'text':'a'*9000},deadline_ms=1000)['code']=='invalid_input')
        code,cr=invoke(root,ECHO_CAP,{'text':'a'*257})
        check('plugin-side invalid input reported as plugin_error in capability_result (C0 mapping)',code=='ok' and cr['ok'] is False and cr['error']=='plugin_error')
        code,cr=invoke(root,ECHO_CAP,{'text':'slow','sleep_ms':500},deadline_ms=1)
        check('deadline 1 ms on sleep_ms=500 => capability_timeout',code=='ok' and cr['error']=='capability_timeout')
        time.sleep(.5)
        code,cr=invoke(root,ECHO_CAP,{'text':'after timeout'})
        check('plugin still usable after timeout',code=='ok' and cr['ok'] and cr['output']['text']=='AFTER TIMEOUT')
        check('cancel submit during sleep accepted',submit(root,ECHO_CAP,{'text':'c','sleep_ms':3000},10000)=='ok')
        time.sleep(.3);check('capability_cancel ok',req(root,'capability_cancel',capability=ECHO_CAP)['code']=='ok')
        cr=result(root,5);check('cancel during sleep => invoke_cancelled',cr['error']=='invoke_cancelled' and cr['ok'] is False)
        time.sleep(.5)
        check('dummy_echo disable ok',plugin_op(root,'plugin_disable',ECHO)['code']=='ok')
        wait_state(root,ECHO,'disabled')
        wait_plugins_gone(set(plugin_refs(core.pid)),'disable leaves plugin process')
        check('disable stops dummy_echo process',not plugin_refs(core.pid))
        # Qt phase: enable/invoke/revoke/re-approve/re-enable driven by the real UI.
        row=run_ui(root,td);record_out['ui']=row
        check('Qt plugins phase reports zero failures',row['failed']==0)
        checks.extend(row['checks'])
        wait_state(root,ECHO,'running')
        check('UI re-approval leaves dummy_echo enabled and running',plugin_item(req(root),ECHO)['enabled'] is True)
        # Scenario 3: IPC revoke, re-enable refusal, re-approve without reinstall.
        workers=set(plugin_workers(core.pid))
        check('revoke ok',plugin_op(root,'plugin_revoke',ECHO)['code']=='ok')
        wait_plugins_gone(workers,'revoke leaves plugin process')
        check('revoke removes plugin process (no /plugin/main.py descendant)',not plugin_refs(core.pid))
        check('invoke after revoke => capability_unavailable',req(root,'capability_invoke',capability=ECHO_CAP,input={'text':'x'},deadline_ms=1000)['code']=='capability_unavailable')
        check('capability_result cleared by revoke',req(root).get('capability_result') is None)
        check('approval record gone from hub-approvals.json',all(r['plugin_id']!=ECHO for r in ledger(root,'hub-approvals.json')['records']))
        check('re-enable after revoke => permissions_not_approved',plugin_op(root,'plugin_enable',ECHO)['code']=='permissions_not_approved')
        check('re-approve dummy_echo ok',approve(root,ECHO)['code']=='ok')
        check('re-enable after re-approve ok',plugin_op(root,'plugin_enable',ECHO)['code']=='ok')
        wait_state(root,ECHO,'running')
        check('re-approved dummy_echo still installed without reinstall',record(hub(root),ECHO) is not None)
        code,cr=invoke(root,ECHO_CAP,{'text':'again'})
        check('re-approved dummy_echo answers invoke',code=='ok' and cr['output']['text']=='AGAIN')
        # Scenario 4: dummy_evil probes inside the real sandbox.
        check('dummy_evil approve ok',approve(root,EVIL)['code']=='ok')
        stage_upload(str(root),EVIL,str(EVIL_SRC));check('dummy_evil install ok',install(root,EVIL)['code']=='ok')
        check('dummy_evil enable ok',plugin_op(root,'plugin_enable',EVIL)['code']=='ok')
        wait_state(root,EVIL,'running')
        for name in ['network','read_home','read_repo','write_root','exec','fork_bomb_limited','env','mem']:
            code,cr=invoke(root,EVIL_CAP,{'probe':name},deadline_ms=8000)
            ok=code=='ok' and cr is not None and cr['ok'] and cr['output']['result'] in ('denied','allowed')
            check(f'dummy_evil probe {name} answered',ok)
            details[name]={'result':cr['output']['result'],'detail':cr['output']['detail']}
            if name in PROBE_EXPECT:check(f'dummy_evil {name} {PROBE_EXPECT[name]}',cr['output']['result']==PROBE_EXPECT[name])
        details['exec_note']='C0 leaves exec open (documented); the observed exec result is recorded above, not asserted'
        code,cr=invoke(root,ECHO_CAP,{'text':'still'})
        check('dummy_echo still answers after evil probes',code=='ok' and cr['output']['text']=='STILL')
        for mode in ARGV_MODES:ignored.append(f'argv mode {mode}: not reachable from Core (plugin started without argv); input-based modes only')
        ignored.append('cpu_spin: 40 s busy loop, not part of the gate budget')
        # Scenario 5: remove an enabled plugin (dummy_evil) through Hub.
        before=set(plugin_workers(core.pid))
        check('two plugin processes running before remove',len(before)==2)
        check('hub_remove enabled dummy_evil ok',op(root,'hub_remove',EVIL)['code']=='ok')
        s=req(root);check('remove drops dummy_evil from enabled set',EVIL not in (ledger(root,'plugin-state.json') or {'enabled':[]})['enabled'] and plugin_item(s,EVIL) is None)
        until=time.monotonic()+8
        while len(plugin_workers(core.pid))!=1:
            if time.monotonic()>until:raise TimeoutError('remove leaves one plugin process')
            time.sleep(.05)
        after=set(plugin_workers(core.pid));gone=before-after
        check('remove stops dummy_evil process (its pid gone), dummy_echo process kept',len(gone)==1 and not any(alive_plugin(p) for p in gone) and len(after)==1)
        check('remove leaves dummy_echo running',plugin_item(req(root),ECHO)['state']=='running')
        # Scenario 6: restart with dummy_echo enabled.
        stop(core,'Core1 with running dummy_echo');core=None
        core=start(core_args(root),root,env);t0=time.monotonic();s=req(root);elapsed=time.monotonic()-t0
        check('restart: snapshot answers within 1 s of socket',elapsed<1.0)
        check('restart: enabled dummy_echo restored from plugin-state.json',(ledger(root,'plugin-state.json') or {}).get('enabled')==[ECHO])
        wait_state(root,ECHO,'running',5)
        code,cr=invoke(root,ECHO_CAP,{'text':'persist'})
        check('restart: dummy_echo invoke works',code=='ok' and cr['output']['text']=='PERSIST')
        # Scenario 7: native S1 while plugin running, idle CPU with idle plugin.
        native_effect(root,'native S1 while dummy_echo running after restart')
        time.sleep(.3);c0=ticks(core.pid);p0=sum(ticks(w) for w in plugin_workers(core.pid) if (Path('/proc')/str(w)).exists());t_start=time.monotonic()
        time.sleep(3);c1=ticks(core.pid);p1=sum(ticks(w) for w in plugin_workers(core.pid) if (Path('/proc')/str(w)).exists());window=time.monotonic()-t_start
        core_pct=(c1-c0)/(CLK*window)*100;details['idle_cpu']={'core_percent':round(core_pct,3),'plugin_percent':round((p1-p0)/(CLK*window)*100,3),'window_s':round(window,2)}
        check('idle Core CPU below 1% over 3 s with running idle plugin',core_pct<1.0)
        check('plugin still running after idle window',plugin_item(req(root),ECHO)['state']=='running')
        check('dummy_echo disable after idle ok',plugin_op(root,'plugin_disable',ECHO)['code']=='ok')
        wait_state(root,ECHO,'disabled')
        stop(core,'Core2 after dummy_echo disable');core=None
        # Scenario 7 continued: native S1 after disable, then after remove, each on a fresh boot.
        core=start(core_args(root),root,env);native_effect(root,'native S1 after dummy_echo disable')
        check('dummy_echo remove ok',op(root,'hub_remove',ECHO)['code']=='ok')
        check('remove leaves no dummy_echo in snapshot',plugin_item(req(root),ECHO) is None and record(hub(root),ECHO) is None)
        stop(core,'Core3 after disable and remove');core=None
        core=start(core_args(root),root,env);native_effect(root,'native S1 after dummy_echo remove on fresh boot')
        check('fresh boot after remove has no plugin processes',not plugin_refs(core.pid))
        # Scenario 9: shutdown with a running plugin proves no leftover children; here none remain.
        stop(core,'Core4 final');core=None
    finally:
        for p in list(live):
            if p.poll() is not None:details['core_exit']={'rc':p.returncode,'stderr_tail':p.stderr.read().decode(errors='replace')[-1200:]}
            else:p.kill();p.wait(timeout=3)
def main():
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=BASE,capture_output=True,text=True,check=True).stdout.strip()
    status_before=subprocess.run(['git','status','--porcelain'],cwd=BASE,capture_output=True,text=True,check=True).stdout
    EVIDENCE.mkdir(parents=True,exist_ok=True);out={}
    with tempfile.TemporaryDirectory(prefix='gideon-c0-plugins-') as td:
        env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td,'XDG_RUNTIME_DIR':td}
        error=None
        try:gate(td,env,out)
        except Exception as exc:error=f'{type(exc).__name__}: {exc} | '+' / '.join(traceback.format_exc().strip().splitlines()[-6:-1])[-1500:]
    status_after=subprocess.run(['git','status','--porcelain'],cwd=BASE,capture_output=True,text=True,check=True).stdout
    if status_before!=status_after:error=(error or '')+' repo status changed'
    result={'gate':'C0_PLUGINS','passed':len(checks),'failed':1 if error else 0,'ignored':len(ignored),'checks':checks,'ignored_items':ignored,'error':error,'ui':out.get('ui'),'evil_probes':details,'binary_sha256':sha(BIN),'commit':commit,'scope':'local fixture plugins dummy_echo and dummy_evil through real Core and bwrap sandbox; plain_opaque refusal; no network, no LLM, no real HOME; argv-only dummy_evil modes ignored; exec probe recorded','physical_validation':'NOT_PERFORMED'}
    (EVIDENCE/'c0-plugins.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if error:sys.exit(1)
if __name__=='__main__':main()
