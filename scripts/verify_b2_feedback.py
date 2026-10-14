#!/usr/bin/env python3
"""Private real Core/namespace command/Pocket PCM and native Qt feedback gate."""
import hashlib,json,signal,socket,subprocess,tempfile,time
from pathlib import Path
from ui_fixture import offscreen_command
BASE=Path(__file__).resolve().parents[1];BIN=BASE/'target/release/gideon-base';checks=[];rows=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
with tempfile.TemporaryDirectory(prefix='gideon-b2-feedback-') as td:
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
    def request(op='snapshot',**kw):
        global counter
        counter+=1
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(3);s.connect(str(root/'core.sock'))
            s.sendall((json.dumps({'version':1,'request_id':f'feedback_{counter}','op':op,**kw})+'\n').encode())
            data=b''
            while not data.endswith(b'\n'):data+=s.recv(65536)
        return json.loads(data)
    def update(rev,volume=50,visual=False,**kw):return request('feedback_preferences',revision=rev,visual_feedback=visual,output_volume_percent=volume,**kw)
    def wait(predicate,seconds=35):
        until=time.monotonic()+seconds
        while True:
            snap=request()
            if predicate(snap):return snap
            if time.monotonic()>until:raise TimeoutError(snap)
            time.sleep(.025)
    def speak():
        check('text uses real shared executor',request('text',raw='open brave')['code']=='ok')
        snap=wait(lambda s:s['state']=='idle' and s['command'] is not None)
        check('command effect independently verified',snap['command']['receipt']['verified'])
        return snap
    try:
        core=start()
        for value in (-1,101,256,True,1.5):
            check('invalid volume rejected '+str(value),update(0,value)['code'] in ('invalid_preferences','invalid_message'))
        check('caller permission injection refused',update(0,grant=True)['code']=='invalid_message')
        full=speak()['speech'];check('default real native PCM',full['output_volume_percent']==100 and full['samples']>0)
        check('feedback update',update(0)['code']=='ok')
        check('stale feedback revision refused',update(0)['code']=='stale_preferences')
        half=speak()['speech'];rows.extend([full,half])
        check('gain preserves native timing and sample count',full['samples']==half['samples'] and full['chunks']==half['chunks'])
        check('half gain scales native peak and RMS',abs(half['peak']/full['peak']-.5)<1e-5 and abs(half['rms']/full['rms']-.5)<1e-5)
        check('hash describes attenuated consumed PCM',half['pcm_sha256']!=full['pcm_sha256'] and half['output_volume_percent']==50)
        stop();core=start();prefs=request()['preferences']
        check('feedback persists across process restart',prefs['revision']==1 and not prefs['visual_feedback'] and prefs['output_volume_percent']==50)
        before=(root/'config.json').read_bytes();sentinel=Path(td)/'sentinel';sentinel.write_text('untouched');(root/'.config.json.pending').symlink_to(sentinel)
        check('feedback storage failure leaves effective state',update(1,25)['code']=='preferences_storage_error' and request()['preferences']['output_volume_percent']==50)
        check('failed feedback write preserves private files',(root/'config.json').read_bytes()==before and sentinel.read_text()=='untouched');(root/'.config.json.pending').unlink()
        check('mute saved',update(1,0)['code']=='ok');muted=speak()
        check('zero gain verifies effect without speech job',muted['speech_status']=='muted' and muted['speech'] is None and not any(e['kind']=='speech_started' for e in muted['events']))
        check('rollback restores half volume',request('rollback_preferences',revision=2)['preferences']['output_volume_percent']==50)
        request('text',raw='open brave');live=wait(lambda s:s['speech_samples']>0)
        check('busy rejects feedback during actual PCM',update(3,25)['code']=='busy')
        check('cancel interrupts real half volume job',request('cancel',session_id=live['session_id'])['code']=='ok')
        cancelled=wait(lambda s:s['state']=='idle');time.sleep(.2);late=request()
        check('cancel fences late completion and keeps verified receipt',late['speech'] is None and late['speech_status']=='cancelled' and cancelled['command']['receipt']['verified'])
        stop();core=None
        root=Path(td)/'ui-core';args[2]=str(root);core=start()
        ui=subprocess.run(offscreen_command(root,artifacts,'feedback'),env={'PATH':'/usr/bin:/bin'},capture_output=True,timeout=55)
        if ui.returncode:raise RuntimeError(ui.stderr.decode()+ui.stdout.decode())
        checks.extend(json.loads(ui.stdout)['checks']);(BASE/'target/evidence/b2-feedback.png').write_bytes((artifacts/'ui.png').read_bytes())
        stop();core=None
    finally:
        if core is not None and core.poll() is None:core.send_signal(signal.SIGCONT);core.terminate();core.wait(timeout=3);core.stderr.close()
result={'gate':'B2_3_FEEDBACK','passed':len(checks),'failed':0,'ignored':0,'checks':checks,'native_pcm':rows,'binary_sha256':hashlib.sha256(BIN.read_bytes()).hexdigest(),'physical_validation':'NOT_PERFORMED'}
(BASE/'target/evidence/b2-feedback.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
