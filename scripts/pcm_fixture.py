"""Authorized bounded PCM fixture reader shared by offline voice adapters."""
import hashlib
from pathlib import Path
import numpy as np
import soundfile as sf


def check_hash(path, expected):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('artifact hash mismatch')


def read_fixture(row):
    path = Path(row['path']); check_hash(path, row['sha256'])
    info = sf.info(path)
    if info.channels!=1 or info.frames>16000*60 or info.samplerate not in (16000,24000): raise ValueError('unsupported fixture')
    samples, sr = sf.read(path, dtype='float32')
    if sr==24000:
        # Explicit DEV-only interpolation; retain source WAV identity and transformation.
        samples = np.interp(np.arange(0,len(samples),sr/16000), np.arange(len(samples)), samples).astype(np.float32)
    return samples

