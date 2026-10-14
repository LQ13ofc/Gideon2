#!/usr/bin/env python3
"""Reference visual QA using actual isolated Core, native CPU voice and offscreen Qt."""
import hashlib,json,subprocess,tempfile,time
from pathlib import Path
from ui_fixture import offscreen_command
BASE=Path(__file__).resolve().parents[1];BIN=BASE/'target/release/gideon-base'
manifest=BASE/'target/a3-assets/replay-manifest.json';index=next(i for i,r in enumerate(json.loads(manifest.read_text())['fixtures']) if r['id']=='wake-hey-brave__bf_emma__clean')
catalog=BASE/'tests/fixtures/hub.json';digest=hashlib.sha256(catalog.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='gideon-design-') as td:
 root=Path(td)/'core';artifacts=Path(td)/'artifacts';artifacts.mkdir()
 env={'PATH':'/usr/bin:/bin','HOME':td,'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'XDG_CACHE_HOME':td,'XDG_RUNTIME_DIR':td}
 args=[str(BIN),'--root',str(root),'--commands-sandbox','--virtual-input','--base-pack',str(BASE/'target/base-pack-dev.json'),'--hub-catalog',str(catalog),digest,'--tts-virtual',str(BASE/'target/tts-venv/bin/python'),str(BASE/'target/a5-assets/manifest.json'),'--wake-replay',str(BASE/'target/a1-venv/bin/python'),str(manifest),str(index)]
 core=subprocess.Popen(args,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 try:
  until=time.monotonic()+5
  while not (root/'core.sock').exists():
   if core.poll() is not None:raise RuntimeError(core.stderr.read().decode())
   if time.monotonic()>until:raise TimeoutError('Core startup')
   time.sleep(.01)
  ui=subprocess.run(offscreen_command(root,artifacts,'design'),env={'PATH':'/usr/bin:/bin'},capture_output=True,timeout=70)
  for p in artifacts.glob('*.png'):(BASE/'target/evidence'/('design-'+p.name)).write_bytes(p.read_bytes())
  if ui.returncode:raise RuntimeError(ui.stderr.decode()+ui.stdout.decode())
  if any(word in ui.stderr.decode() for word in ('Error:','Unable to','Binding loop','ReferenceError','TypeError')):raise RuntimeError('QML diagnostics: '+ui.stderr.decode())
  result=json.loads(ui.stdout);result['binary_sha256']=hashlib.sha256(BIN.read_bytes()).hexdigest();result['qml_stderr']=ui.stderr.decode();result['physical_validation']='NOT_PERFORMED'
  core.terminate();assert core.wait(timeout=3)==0
 finally:
  if core.poll() is None:core.terminate();core.wait(timeout=3)
  core.stderr.close()
(BASE/'target/evidence/design.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
