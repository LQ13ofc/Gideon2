#!/usr/bin/env python3
"""Build one internal DEV pack description from existing pinned assets/evidence."""
import hashlib,json
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
# Catalog: KWS phone transcription, tuned boost/threshold and the evidence that measured them (wake-phrases.json).
PHRASES=[
    ('hey_gideon','Hey Gideon','HH EY1 G IH1 D IY0 AH0 N',1.2,0.22,'wake-hey-b12t22.json'),
    ('okay_gideon','Okay Gideon','OW2 K EY1 G IH1 D IY0 AH0 N',0.0,0.25,'wake-okay-b0.json'),
]
LEXICON=BASE/'target/a1-assets/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/en.phone'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def build(destination):
    replay=BASE/'target/a3-assets/replay-manifest.json';wake=BASE/'target/a1-competitive/manifest.json';stt=BASE/'target/a3-assets/manifest.json';tts=BASE/'target/a5-assets/manifest.json'
    def reference(path):return {'path':str(path),'sha256':sha(path)}
    payload={'version':1,'id':'base-en-dev-v1','wake_profile_sha256':sha(replay),'stt_profile_sha256':sha(stt),'tts_profile_sha256':sha(tts),'qualification_profile':reference(wake),'lexicon':reference(LEXICON),'phrases':{}}
    for ident,text,tokens,boost,threshold,report in PHRASES:
        source=BASE/'target/evidence'/report;data=json.loads(source.read_text())
        if data['manifest_sha256']!=sha(wake) or data['engine']!=json.loads(wake.read_text())['engine']:raise ValueError('qualification provenance mismatch')
        payload['phrases'][ident]={'text':text,'tokens':tokens,'language':'en','boost':boost,'threshold':threshold,'evidence':reference(source)}
    destination.write_text(json.dumps(payload,indent=2)+'\n');return payload
if __name__=='__main__':
    path=BASE/'target/base-pack-dev.json';build(path);print(path)
