#!/usr/bin/env python3
"""Provisions the approved Pocket TTS Portuguese and French profiles (WP-7, VOZ-05).

Approved by the owner (2026-10-25): PT and FR TTS models only. Each file is taken from the revision that
pocket-tts 3.3.0 pins in its own bundled config (target/tts-venv: config/portuguese.yaml, config/french.yaml), so the
upstream provenance is the same one the library itself uses. Every download is checked against:
  - the LFS sha256 published by the Hub for that revision (model.safetensors, voice embeddings), or
  - the git blob id published by the Hub (tokenizer.json, not stored in LFS: sha1 of "blob <size>\\0" + content).
The sha256 of every file (and of the generated config.yaml) is then recorded in the profile manifest.

Output: target/tts-<lang>-assets/ with config.yaml, manifest.json (profile read by scripts/tts_worker.py) and the
artifacts. Existing files that already match are not downloaded again. Stdlib only (plus PyYAML from tts-venv).

Usage: target/tts-venv/bin/python scripts/provision_pt_fr_tts.py [--language portuguese|french]
"""
import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[1]
REPO = 'kyutai/pocket-tts-without-voice-cloning'
CONFIG_DIR = BASE / 'target/tts-venv/lib/python3.13/site-packages/pocket_tts/config'
# Revisions pinned by pocket-tts 3.3.0 (weights_path_without_voice_cloning / tokenizer_path / embeddings).
LANGS = {
    'portuguese': {
        'engine': 'pocket-tts-3.3.0/portuguese/cpu',
        'config_src': 'portuguese.yaml',
        'root': BASE / 'target/tts-pt-assets',
        'voice': 'rafael',
        'model_rev': '4e1e0a3e611c51c0b4ed8174fc10f32a54644303',
        'tokenizer_rev': '4e1e0a3e611c51c0b4ed8174fc10f32a54644303',
        'voice_rev': '4e1e0a3e611c51c0b4ed8174fc10f32a54644303',
    },
    'french': {
        'engine': 'pocket-tts-3.3.0/french/cpu',
        'config_src': 'french.yaml',
        'root': BASE / 'target/tts-fr-assets',
        'voice': 'estelle',
        'model_rev': '8843db76457a91db32077edf8dfcd1c0e3e755fd',
        'tokenizer_rev': '8843db76457a91db32077edf8dfcd1c0e3e755fd',
        'voice_rev': '4e1e0a3e611c51c0b4ed8174fc10f32a54644303',
    },
}
HEX64 = re.compile(r'^[0-9a-f]{64}$')


def hub_files(rev):
    url = f'https://huggingface.co/api/models/{REPO}/revision/{rev}?blobs=true'
    with urllib.request.urlopen(url, timeout=60) as response:
        info = json.load(response)
    return {row['rfilename']: row for row in info['siblings']}


def fetch(url, dest):
    with urllib.request.urlopen(url, timeout=120) as response, dest.open('wb') as out:
        while chunk := response.read(1024 * 1024):
            out.write(chunk)


def git_blob_id(path):
    data = path.read_bytes()
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def provision(language, spec):
    root = spec['root']
    root.mkdir(parents=True, exist_ok=True)
    artifacts = []
    wanted = [
        ('model.safetensors', f"languages/{language}/model.safetensors", spec['model_rev']),
        ('tokenizer.json', f"languages/{language}/tokenizer.json", spec['tokenizer_rev']),
        (f"{spec['voice']}.safetensors", f"languages/{language}/embeddings/{spec['voice']}.safetensors", spec['voice_rev']),
    ]
    for name, path, rev in wanted:
        row = hub_files(rev)[path]
        lfs = row.get('lfs') or {}
        expected_sha = lfs.get('sha256')
        expected_blob = None if lfs else row['blobId']
        dest = root / name
        if not dest.exists() or dest.stat().st_size != row['size']:
            fetch(f'https://huggingface.co/{REPO}/resolve/{rev}/{path}', dest)
        if dest.stat().st_size != row['size']:
            raise ValueError(f'size mismatch: {name}')
        sha = hashlib.sha256(dest.read_bytes()).hexdigest()
        if expected_sha is not None and sha != expected_sha:
            raise ValueError(f'lfs sha256 mismatch: {name}')
        if expected_blob is not None and git_blob_id(dest) != expected_blob:
            raise ValueError(f'git blob id mismatch: {name}')
        artifacts.append({
            'name': name, 'sha256': sha, 'size': dest.stat().st_size,
            'source': f'https://huggingface.co/{REPO}/resolve/{rev}/{path}',
            'upstream_sha256': expected_sha, 'upstream_git_blob': expected_blob, 'revision': rev,
            'verified': 'lfs_sha256' if expected_sha else 'git_blob_id',
        })
        print(name, sha, dest.stat().st_size, flush=True)
    # Config: the library's own file with local, absolute paths only (no hub:// reference, no voice cloning weights).
    cfg = yaml.safe_load((CONFIG_DIR / spec['config_src']).read_text())
    cfg['weights_path'] = str(root / 'model.safetensors')
    cfg['weights_path_without_voice_cloning'] = None
    cfg['flow_lm']['lookup_table']['tokenizer_path'] = str(root / 'tokenizer.json')
    (root / 'config.yaml').write_text(yaml.safe_dump(cfg, allow_unicode=True))
    artifacts.append({
        'name': 'config.yaml', 'sha256': hashlib.sha256((root / 'config.yaml').read_bytes()).hexdigest(),
        'source': f'pocket-tts 3.3.0 bundled {spec["config_src"]}; local-only paths',
    })
    manifest = {
        'engine': spec['engine'], 'language': language, 'voice_name': spec['voice'],
        'root': str(root), 'config': str(root / 'config.yaml'), 'voice': str(root / f"{spec['voice']}.safetensors"),
        'artifacts': artifacts,
        'license': {
            'code': 'MIT (pocket-tts)',
            'weights': 'cc-by-4.0 (cartao do modelo kyutai/pocket-tts)',
            'voice_embedding': 'NAO VERIFICADO: a licenca por voz do embedding predefinido nao consta do repositorio tts-voices',
        },
    }
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    print('manifest', root / 'manifest.json', flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description='Provision approved PT/FR Pocket TTS profiles.')
    parser.add_argument('--language', choices=sorted(LANGS), action='append')
    args = parser.parse_args()
    for language in args.language or sorted(LANGS):
        provision(language, LANGS[language])


if __name__ == '__main__':
    main()
