#!/usr/bin/env python3
"""Bounded private DEV evaluation. No threshold tuning or certification implied."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from wake_worker import WakeEngine, read_fixture, np


def evaluate(manifest_path, output, silence_seconds, threshold, active_phrase=None):
    manifest = json.loads(manifest_path.read_text())
    if active_phrase: manifest['active_phrase'] = active_phrase
    engine = WakeEngine(manifest, dev_threshold=threshold)
    rows=[]
    for i,row in enumerate(manifest['fixtures']):
        engine.reset()
        samples=np.concatenate([read_fixture(row), np.zeros(16000,dtype=np.float32)])
        detections=[];start=time.monotonic()
        for offset in range(0,len(samples),1280):
            detections.extend(engine.accept(samples[offset:offset+1280],offset*1_000_000//16000))
        rows.append({'id':row['id'],'sha256':row['sha256'],'positive':row['expected_wake_phrase']==engine.active_phrase,'detections':detections,'wall_s':time.monotonic()-start,'audio_s':len(samples)/16000})
        if i%80==0: print(f'evaluated {i}/{len(manifest["fixtures"])}',flush=True)
    engine.reset()
    start=time.monotonic();silence_wakes=0
    for offset in range(0,silence_seconds*16000,1280):
        silence_wakes+=len(engine.accept(np.zeros(min(1280,silence_seconds*16000-offset),dtype=np.float32),offset*1_000_000//16000))
    positive=[r for r in rows if r['positive']];negative=[r for r in rows if not r['positive']]
    recall=sum(bool(r['detections']) for r in positive)/len(positive)
    false_wakes=sum(len(r['detections']) for r in negative)
    result={'gate':'A1','quality':'PASS_DEV_ONLY' if recall>=.95 and false_wakes==0 and silence_wakes==0 and silence_seconds>=3600 else 'FAILED',
            'engine':manifest['engine'],'active_phrase':engine.active_phrase,'threshold':threshold,'score':1.0,'threads':1,'provider':'cpu',
            'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            'worker_sha256':hashlib.sha256(Path(__file__).with_name('wake_worker.py').read_bytes()).hexdigest(),
            'positive_count':len(positive),'detected_positive':sum(bool(r['detections']) for r in positive),'recall':recall,
            'negative_count':len(negative),'false_wakes':false_wakes,'speech_negative_audio_s':sum(r['audio_s']-1 for r in negative),
            'corpus_rtf':sum(r['wall_s'] for r in rows)/sum(r['audio_s'] for r in rows),
            'max_rss_bytes':int(next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmHWM:')))*1024,
            'memory_source':'Linux /proc/self/status VmHWM; ru_maxrss discrepancy excluded',
            'procedural_silence':{'seconds':silence_seconds,'false_wakes':silence_wakes,'wall_s':time.monotonic()-start,'independent_environment_evidence':False},
            'rows':rows,'physical_validation':'NOT_PERFORMED','distribution_certified':False,
            'scope':'synthetic private DEV; four Kokoro voices; no independent holdout; no model training; source fixtures only read'}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('manifest',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--active-phrase');parser.add_argument('--dev-threshold',type=float,default=.25);parser.add_argument('--silence-seconds',type=int,default=3600)
    args=parser.parse_args()
    if not 0<=args.silence_seconds<=3600:parser.error('silence bounded to one hour')
    evaluate(args.manifest,args.output,args.silence_seconds,args.dev_threshold,args.active_phrase)
