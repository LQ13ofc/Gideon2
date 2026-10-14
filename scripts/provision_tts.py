import json,urllib.request,hashlib
from pathlib import Path
import yaml
base=Path(__file__).resolve().parents[1];root=base/'target/a5-assets'
cfg=yaml.safe_load((base/'target/tts-venv/lib/python3.13/site-packages/pocket_tts/config/english_2026-09.yaml').read_text())
repo='kyutai/pocket-tts-without-voice-cloning'
files=[('model.safetensors','languages/english_2026-09/model.safetensors','e7205b6ee50e654a5ea19f0e9df2b0813b05e921'),('tokenizer.json','languages/english_2026-09/tokenizer.json','00eac05ed3d16bdc3f6b5d598874019c34a89214'),('alba.safetensors','languages/english_2026-09/embeddings/alba.safetensors','4e1e0a3e611c51c0b4ed8174fc10f32a54644303')]
records=[]
for name,path,rev in files:
    info=json.load(urllib.request.urlopen(f'https://huggingface.co/api/models/{repo}/revision/{rev}?blobs=true'))
    row=next(x for x in info['siblings'] if x['rfilename']==path);expected=row.get('lfs',{}).get('sha256')
    url=f'https://huggingface.co/{repo}/resolve/{rev}/{path}';dest=root/name
    if not dest.exists():
        with urllib.request.urlopen(url,timeout=60) as r,dest.open('wb') as out:
            while chunk:=r.read(1024*1024):out.write(chunk)
    sha=hashlib.sha256(dest.read_bytes()).hexdigest()
    if expected and expected!=sha:raise ValueError('hash')
    records.append({'name':name,'sha256':sha,'size':dest.stat().st_size,'source':url,'upstream_sha256':expected})
    print(name,sha,flush=True)
cfg['weights_path']=str(root/'model.safetensors');cfg['weights_path_without_voice_cloning']=None
cfg['flow_lm']['lookup_table']['tokenizer_path']=str(root/'tokenizer.json')
(root/'config.yaml').write_text(yaml.safe_dump(cfg))
records.append({'name':'config.yaml','sha256':hashlib.sha256((root/'config.yaml').read_bytes()).hexdigest(),'source':'pocket-tts 3.3.0 bundled english_2026-09; local-only paths'})
manifest={'engine':'pocket-tts-3.3.0/english_2026-09/cpu','root':str(root),'config':str(root/'config.yaml'),'voice':str(root/'alba.safetensors'),'artifacts':records}
(root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
