#!/usr/bin/env python3
"""Pinned local Pocket CPU into PCM pipe; no network, microphone, speaker or output file."""
import hashlib,importlib.metadata,json,sys
from pathlib import Path
profile=json.loads(Path(sys.argv[1]).read_text());root=Path(profile['root'])
for artifact in profile['artifacts']:
    path=root/artifact['name']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=artifact['sha256']:raise ValueError('TTS hash mismatch')
if importlib.metadata.version('pocket-tts')!='3.3.0':raise ValueError('TTS version')
job=json.loads(sys.stdin.buffer.readline(4097))
if set(job)!={'session_id','text'} or type(job['session_id']) is not int or not isinstance(job['text'],str) or not 0<len(job['text'])<=256:raise ValueError('speech job')
import torch
from pocket_tts import TTSModel
torch.set_num_threads(2);torch.set_num_interop_threads(1);torch.manual_seed(20261014)
model=TTSModel.load_model(config=profile['config']);state=model.get_state_for_audio_prompt(Path(profile['voice']))
if model.sample_rate!=24000 or model.device.type!='cpu':raise ValueError('CPU/sample rate')
print(json.dumps({'op':'ready','session_id':job['session_id']}),flush=True)
count=0
for chunk in model.generate_audio_stream(state,job['text']):
    samples=chunk.detach().cpu().flatten().tolist();count+=len(samples)
    if count>240000:raise ValueError('speech too long')
    for start in range(0,len(samples),1920):
        print(json.dumps({'op':'pcm','session_id':job['session_id'],'samples':samples[start:start+1920]},allow_nan=False),flush=True)
print(json.dumps({'op':'done','session_id':job['session_id']}),flush=True)
