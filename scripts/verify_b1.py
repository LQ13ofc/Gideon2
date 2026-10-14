#!/usr/bin/env python3
"""Core outside / Qt offscreen inside private namespace; no display or personal endpoints."""
import hashlib,json,os,signal,subprocess,tempfile,time
from pathlib import Path
from ui_fixture import offscreen_command
BASE=Path(__file__).resolve().parents[1];BIN=BASE/'target/release/gideon-base'
manifest=BASE/'target/a3-assets/replay-manifest.json';m=json.loads(manifest.read_text());index=next(i for i,r in enumerate(m['fixtures']) if r['id']=='wake-hey-brave__bf_emma__clean');rows=[]
for phase in ('voice','cancel','reconnect','timeout'):
    with tempfile.TemporaryDirectory(prefix='gideon-b1-') as td:
        root=Path(td)/'core';artifacts=Path(td)/'artifacts';artifacts.mkdir()
        env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td,'XDG_RUNTIME_DIR':td,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
        coreargs=[str(BIN),'--root',str(root),'--commands-sandbox']
        if phase not in ('reconnect','timeout'):coreargs+=['--tts-virtual',str(BASE/'target/tts-venv/bin/python'),str(BASE/'target/a5-assets/manifest.json'),'--wake-replay',str(BASE/'target/a1-venv/bin/python'),str(manifest),str(index)]
        else:coreargs+=['--virtual-input']
        core=subprocess.Popen(coreargs,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);ui=None
        try:
            until=time.monotonic()+3
            while not (root/'core.sock').exists():
                if core.poll() is not None:raise RuntimeError(core.stderr.read().decode())
                if time.monotonic()>until:raise TimeoutError('Core start')
                time.sleep(.01)
            cmd=offscreen_command(root,artifacts,phase)
            ui=subprocess.Popen(cmd,env={'PATH':'/usr/bin:/bin'},stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            if phase in ('reconnect','timeout'):
                for marker in ('connected','offline'):
                    until=time.monotonic()+12
                    while not (artifacts/marker).exists():
                        if ui.poll() is not None:raise RuntimeError(ui.stderr.read().decode())
                        if time.monotonic()>until:raise TimeoutError(marker)
                        time.sleep(.02)
                    if marker=='connected':
                        if phase=='timeout':core.send_signal(signal.SIGSTOP)
                        else:core.kill();core.wait(timeout=3);core.stderr.close()
                if phase=='timeout':core.send_signal(signal.SIGCONT)
                else:core=subprocess.Popen(coreargs,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            out,err=ui.communicate(timeout=45)
            if ui.returncode:raise RuntimeError(err.decode()+out.decode())
            row=json.loads(out);rows.append(row)
            if phase=='voice':(BASE/'target/evidence/b1-ui.png').write_bytes((artifacts/'ui.png').read_bytes())
            core.terminate()
            if core.wait(timeout=3)!=0:raise RuntimeError('Core shutdown')
        finally:
            if ui and ui.poll() is None:ui.kill();ui.wait(timeout=3)
            if core.poll() is None:core.send_signal(signal.SIGCONT);core.terminate();core.wait(timeout=3)
            core.stderr.close()
result={'gate':'B1_UI_INTEGRATION','passed':sum(r['passed'] for r in rows),'failed':0,'ignored':0,'rows':rows,'binary_sha256':hashlib.sha256(BIN.read_bytes()).hexdigest(),'physical_validation':'NOT_PERFORMED'}
(BASE/'target/evidence/b1-ui.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
