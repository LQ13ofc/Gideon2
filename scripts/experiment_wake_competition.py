#!/usr/bin/env python3
"""DEV-only KWS decoder experiment; forbidden to certify from these scores."""
import hashlib
import json
from pathlib import Path
import time
import sherpa_onnx
from wake_worker import read_fixture, np

BASE=Path(__file__).resolve().parents[1]
manifest=json.loads((BASE/'target/a1-assets/manifest.json').read_text())
assets=Path(manifest['asset_root'])
keywords=BASE/'target/a1-experiments/competitive-keywords.txt'
keywords.write_text('HH EY1 G IH1 D IY0 AH0 N @HEY_GIDEON\nOW2 K EY1 G IH1 D IY0 AH0 N @REJECT_OKAY\nHH AY1 G IH1 D IY0 AH0 N @REJECT_HI\n')
for name,digest in manifest['hashes'].items():
    if hashlib.sha256((assets/name).read_bytes()).hexdigest()!=digest:raise ValueError('hash mismatch')
kws=sherpa_onnx.KeywordSpotter(tokens=str(assets/'tokens.txt'),encoder=str(assets/manifest['encoder']),decoder=str(assets/manifest['decoder']),joiner=str(assets/manifest['joiner']),keywords_file=str(keywords),num_threads=1,provider='cpu',keywords_threshold=.25,keywords_score=1.0)
rows=[]
for i,row in enumerate(manifest['fixtures']):
    stream=kws.create_stream();samples=np.concatenate([read_fixture(row),np.zeros(16000,dtype=np.float32)]);events=[];started=time.monotonic()
    for offset in range(0,len(samples),1280):
        stream.accept_waveform(16000,samples[offset:offset+1280])
        while kws.is_ready(stream):
            kws.decode_stream(stream);label=kws.get_result(stream)
            if label:
                events.append({'label':label,'end_us':int((offset+len(samples[offset:offset+1280]))*1000000/16000)})
                kws.reset_stream(stream)
    rows.append({'id':row['id'],'positive':row['positive'],'sha256':row['sha256'],'events':events,'wall_s':time.monotonic()-started})
    if i%80==0:print('evaluated',i,flush=True)
p=[r for r in rows if r['positive']];n=[r for r in rows if not r['positive']]
result={'experiment':'KWS competition; hey sole supported wake; okay/hi rejection classes','candidate_frozen':False,'keywords_sha256':hashlib.sha256(keywords.read_bytes()).hexdigest(),'threshold':.25,'score':1.,'positive_count':len(p),'detected_positive':sum(any(e['label']=='HEY_GIDEON' for e in r['events']) for r in p),'negative_count':len(n),'false_wakes':sum(sum(e['label']=='HEY_GIDEON' for e in r['events']) for r in n),'rows':rows}
(BASE/'target/evidence/a1-competition-dev.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
