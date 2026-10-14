#!/usr/bin/env python3
"""Pinned local Pocket CPU into PCM pipe; no devices/network/output file."""
import hashlib,importlib.metadata,json,sys
from pathlib import Path

def load_profile(path):
    profile=json.loads(Path(path).read_text());root=Path(profile['root'])
    required={'model.safetensors','tokenizer.json','alba.safetensors','config.yaml'}
    artifacts=profile['artifacts']
    if profile['engine']!='pocket-tts-3.3.0/english_2026-09/cpu' or not root.is_absolute():raise ValueError('TTS profile')
    if not isinstance(artifacts,list) or len(artifacts)!=4 or {a['name'] for a in artifacts}!=required:raise ValueError('TTS hash catalog')
    if profile['config']!=str(root/'config.yaml') or profile['voice']!=str(root/'alba.safetensors'):raise ValueError('TTS path mismatch')
    for artifact in artifacts:
        file=root/artifact['name']
        if file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest()!=artifact['sha256']:raise ValueError('TTS hash mismatch')
    import yaml
    config=yaml.safe_load((root/'config.yaml').read_text())
    if config['weights_path']!=str(root/'model.safetensors') or config.get('weights_path_without_voice_cloning') is not None or config['flow_lm']['lookup_table']['tokenizer_path']!=str(root/'tokenizer.json'):raise ValueError('TTS must use pinned local files')
    return profile

def main():
    profile=load_profile(sys.argv[1])
    if importlib.metadata.version('pocket-tts')!='3.3.0':raise ValueError('TTS version')
    job=json.loads(sys.stdin.buffer.readline(4097))
    if set(job)!={'session_id','text'} or type(job['session_id']) is not int or not 0<job['session_id']<2**64 or not isinstance(job['text'],str) or not 0<len(job['text'])<=256:raise ValueError('speech job')
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

if __name__=='__main__':main()
