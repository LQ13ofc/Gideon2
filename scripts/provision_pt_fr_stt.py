#!/usr/bin/env python3
"""Provisions the approved multilingual STT model for Portuguese and French (WP-7, VOZ-05).

Choice (docs/research/idiomas-stt-tts.md, item D15): NVIDIA Parakeet-TDT-0.6B-v3 (CC-BY-4.0), one model for both
PT and FR. The research listed the NeMo original (nvidia/parakeet-tdt-0.6b-v3, a 2.4 GB .nemo file that needs NeMo to
run). This script fetches the ONNX int8 export published by the sherpa-onnx project (k2-fsa), which runs with the
sherpa-onnx 1.13.8 already pinned for the wake engine. The export is a conversion of the same weights; its provenance
is recorded in the manifest as a derivative, not as the NVIDIA file.

Verification: LFS files must match the sha256 the Hub publishes for the pinned revision; tokens.txt (not LFS) must
match its git blob id. Each sha256 is recorded in the manifest.

Output: target/stt-pt-fr-assets/ with the four artifacts and manifest.json. Stdlib only.
Usage: python3 scripts/provision_pt_fr_stt.py
"""
import hashlib
import json
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
REPO = 'csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8'
REV = '2bda32ec70b097a55adaa07d9a7173915b43cc78'
ROOT = BASE / 'target/stt-pt-fr-assets'
FILES = ['encoder.int8.onnx', 'decoder.int8.onnx', 'joiner.int8.onnx', 'tokens.txt']


def git_blob_id(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def main():
    with urllib.request.urlopen(f'https://huggingface.co/api/models/{REPO}/revision/{REV}?blobs=true', timeout=60) as r:
        info = json.load(r)
    rows = {row['rfilename']: row for row in info['siblings']}
    ROOT.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for name in FILES:
        row = rows[name]
        lfs = row.get('lfs') or {}
        dest = ROOT / name
        if not dest.exists() or dest.stat().st_size != row['size']:
            url = f'https://huggingface.co/{REPO}/resolve/{REV}/{name}'
            with urllib.request.urlopen(url, timeout=120) as response, dest.open('wb') as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
        data_size = dest.stat().st_size
        if data_size != row['size']:
            raise ValueError(f'size mismatch: {name}')
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        if lfs:
            if digest != lfs['sha256']:
                raise ValueError(f'lfs sha256 mismatch: {name}')
            verified = 'lfs_sha256'
        else:
            if git_blob_id(dest.read_bytes()) != row['blobId']:
                raise ValueError(f'git blob id mismatch: {name}')
            verified = 'git_blob_id'
        artifacts.append({'name': name, 'sha256': digest, 'size': data_size, 'verified': verified,
                          'source': f'https://huggingface.co/{REPO}/resolve/{REV}/{name}', 'revision': REV})
        print(name, digest, data_size, verified, flush=True)
    manifest = {
        'engine': 'sherpa-onnx-1.13.8/nemo-parakeet-tdt-0.6b-v3-int8',
        'languages': ['pt', 'fr'],
        'model_type': 'nemo_transducer',
        'model_root': str(ROOT),
        'encoder': 'encoder.int8.onnx', 'decoder': 'decoder.int8.onnx', 'joiner': 'joiner.int8.onnx',
        'tokens': 'tokens.txt',
        'provider': 'CPU',
        'hashes': {item['name']: item['sha256'] for item in artifacts},
        'artifacts': artifacts,
        'license': {
            'weights': 'CC-BY-4.0 (cartao de nvidia/parakeet-tdt-0.6b-v3); export ONNX de csukuangfj: licenca do repositorio nao publicada, herdada',
            'origin': 'nvidia/parakeet-tdt-0.6b-v3 (NeMo) convertido para ONNX pelo projeto sherpa-onnx',
        },
    }
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    print('manifest', ROOT / 'manifest.json', flush=True)


if __name__ == '__main__':
    main()
