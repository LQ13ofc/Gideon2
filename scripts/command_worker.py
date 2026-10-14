#!/usr/bin/env python3
"""Trusted deterministic executor inside unshare-all/tmpfs. Never a host adapter."""
import datetime,json,os,subprocess,sys
from pathlib import Path

if len(sys.argv)==4 and sys.argv[1]=='--app':
    # Stand-in application: real exec and application-owned proof of identity.
    Path('/tmp/app-proof.json').write_text(json.dumps({'desktop_id':sys.argv[2],'session_id':int(sys.argv[3]),'pid':os.getpid()}))
    sys.exit(0)

job=json.loads(sys.stdin.buffer.readline(4097))
if set(job)!={'session_id','command'} or type(job['session_id']) is not int:
    raise ValueError('invalid job')
c=job['command'];kind=c['kind']
if kind=='open_app' and set(c)=={'kind','desktop_id'} and c['desktop_id']=='com.brave.Browser.desktop':
    p=subprocess.run([sys.executable,'-I',str(Path(__file__).resolve()),'--app',c['desktop_id'],str(job['session_id'])],check=True,timeout=1)
    proof=json.loads(Path('/tmp/app-proof.json').read_text())
    assert proof['desktop_id']==c['desktop_id'] and proof['session_id']==job['session_id'] and proof['pid']>0
    result='Sandbox app process verified: '+c['desktop_id']
elif kind in ('volume','mute'):
    assert (kind=='mute' and set(c)=={'kind'}) or (kind=='volume' and set(c)=={'kind','level'} and type(c['level']) is int and 0<=c['level']<=100)
    state={'level':c.get('level',0),'muted':kind=='mute'}
    path=Path('/tmp/simulated-audio.json');path.write_text(json.dumps(state));assert json.loads(path.read_text())==state
    result='Simulated audio verified: '+json.dumps(state,sort_keys=True)
elif kind in ('time','date','status') and set(c)=={'kind'}:
    now=datetime.datetime.now(datetime.timezone.utc)
    result=now.strftime('%H:%M:%S UTC') if kind=='time' else now.date().isoformat() if kind=='date' else 'Sandbox executor ready'
else:
    raise ValueError('denied command')
print(json.dumps({'job':job,'verified':True,'scope':'sandbox','result':result}),flush=True)
