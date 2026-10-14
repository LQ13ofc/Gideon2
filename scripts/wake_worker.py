"""Offline CPU inference for A1. No devices/network and no client authority."""
from collections import deque
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
import sherpa_onnx
import soundfile as sf

ENGINE = 'sherpa-onnx-1.13.8/zipformer-zh-en-3M-2025-12-20-int8-chunk8/competitive-v2'


def check_hash(path, expected):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('artifact hash mismatch')


class WakeEngine:
    def __init__(self, manifest, *, dev_threshold=0.25):
        if not 0.25 <= dev_threshold <= 1: raise ValueError('invalid DEV threshold')
        if manifest['engine'] != ENGINE or sherpa_onnx.__version__ != '1.13.8':
            raise ValueError('engine version mismatch')
        phrases = manifest['supported_phrases']
        if not isinstance(phrases, dict) or not 1 <= len(phrases) <= 8:
            raise ValueError('invalid phrase catalog')
        labels = list(phrases.values()) + manifest['rejection_labels']
        if len(set(labels)) != len(labels) or any(not isinstance(x,str) or not x.isascii() or not x.replace('_','').isalnum() or len(x)>64 for x in [*phrases, *labels]):
            raise ValueError('invalid phrase IDs or labels')
        self.supported_phrases = tuple(phrases)
        self.active_phrase = manifest['active_phrase']
        if self.active_phrase not in phrases:
            raise ValueError('unsupported active phrase')
        self.active_label = phrases[self.active_phrase]
        self.labels = frozenset(labels)
        assets = Path(manifest['asset_root'])
        required = {manifest['encoder'], manifest['decoder'], manifest['joiner'], 'tokens.txt', 'keywords.txt'}
        if set(manifest['hashes']) != required:
            raise ValueError('missing or unexpected artifact hashes')
        for name, digest in manifest['hashes'].items():
            if Path(name).name != name: raise ValueError('unsafe asset path')
            check_hash(assets/name, digest)
        declared = []
        vocab = {line.split()[0] for line in (assets/'tokens.txt').read_text().splitlines() if line.split()}
        for line in (assets/'keywords.txt').read_text().splitlines():
            tokens = line.split()
            if len(tokens)<2 or not tokens[-1].startswith('@') or any(t not in vocab for t in tokens[:-1]):
                raise ValueError('invalid keyword tokens')
            declared.append(tokens[-1][1:])
        if len(declared) != len(self.labels) or set(declared) != self.labels:
            raise ValueError('keyword catalog mismatch')
        self.kws = sherpa_onnx.KeywordSpotter(tokens=str(assets/'tokens.txt'), encoder=str(assets/manifest['encoder']), decoder=str(assets/manifest['decoder']), joiner=str(assets/manifest['joiner']), keywords_file=str(assets/'keywords.txt'), num_threads=1, provider='cpu', keywords_threshold=dev_threshold, keywords_score=1.0)
        self.reset()

    def reset(self):
        self.stream = self.kws.create_stream()
        self.last_end = 0
        self.stream_start_us = 0
        self.recent = deque()

    def decode(self):
        events = []
        while self.kws.is_ready(self.stream):
            self.kws.decode_stream(self.stream)
            result = self.kws.get_result(self.stream)
            if result:
                if result not in self.labels: raise ValueError('unsupported detection')
                if result != self.active_label:
                    self.kws.reset_stream(self.stream)
                    continue
                native = self.kws.keyword_spotter.get_result(self.stream)
                times = native.timestamps
                start = self.stream_start_us + int((native.start_time + min(times))*1e6) if times else self.last_end-80000
                events.append({'phrase_id':self.active_phrase,'confidence':None,'start_us':start,'end_us':self.last_end,'engine':ENGINE})
                self.kws.reset_stream(self.stream)
        return events

    def accept(self, samples, timestamp_us):
        if timestamp_us != self.last_end or not 0<len(samples)<=1280 or not np.isfinite(samples).all() or np.max(np.abs(samples))>1:
            raise ValueError('invalid audio frame')
        # Native feature history can grow indefinitely on a never-ending silence stream.
        # Bound each stream to 10s and prime its replacement with 2s of PCM overlap.
        if timestamp_us - self.stream_start_us >= 10_000_000:
            self.stream = self.kws.create_stream()
            self.stream_start_us = self.recent[0][0] if self.recent else timestamp_us
            for _, old in self.recent:
                self.stream.accept_waveform(16000, old)
                self.decode()  # Already consumed overlap never emits a second wake.
        self.last_end += len(samples)*1_000_000//16000
        self.stream.accept_waveform(16000, samples)
        events = self.decode()
        self.recent.append((timestamp_us, samples.copy()))
        while self.recent and self.recent[0][0] < self.last_end - 2_000_000:
            self.recent.popleft()
        return events



def read_fixture(row):
    path = Path(row['path']); check_hash(path, row['sha256'])
    info = sf.info(path)
    if info.channels!=1 or info.frames>16000*60 or info.samplerate not in (16000,24000): raise ValueError('unsupported fixture')
    samples, sr = sf.read(path, dtype='float32')
    if sr==24000:
        # Explicit DEV-only interpolation; retain source WAV identity and transformation.
        samples = np.interp(np.arange(0,len(samples),sr/16000), np.arange(len(samples)), samples).astype(np.float32)
    return samples


def replay(manifest, row, emit=None):
    engine = WakeEngine(manifest)
    samples = read_fixture(row)
    samples = np.concatenate([samples,np.zeros(16000,dtype=np.float32)])
    detections = []
    started = time.monotonic()
    for offset in range(0,len(samples),1280):
        chunk = samples[offset:offset+1280]
        events = engine.accept(chunk, offset*1_000_000//16000)
        detections += events
        if emit:
            for event in events: emit(event)
    return {'detections': detections, 'wall_s': time.monotonic()-started, 'audio_s': len(samples)/16000}


class VadEngine:
    def __init__(self, manifest):
        if manifest['engine']!='silero-vad-v5.0/sherpa-onnx-1.13.8':raise ValueError('unsupported VAD')
        check_hash(Path(manifest['path']),manifest['sha256'])
        config=sherpa_onnx.VadModelConfig()
        config.silero_vad.model=manifest['path'];config.silero_vad.threshold=0.5
        config.silero_vad.min_speech_duration=0.1;config.silero_vad.min_silence_duration=0.1
        config.silero_vad.max_speech_duration=30.;config.silero_vad.window_size=512
        config.sample_rate=16000;config.num_threads=1;config.provider='cpu'
        self.vad=sherpa_onnx.VoiceActivityDetector(config,buffer_size_in_seconds=1.)
    def accept(self, samples):
        self.vad.accept_waveform(samples)
        result=self.vad.is_speech_detected()
        while not self.vad.empty():self.vad.pop()
        return bool(result)


def stream_fixture(manifest, row):
    engine = WakeEngine(manifest)
    vad = VadEngine(manifest["vad"]) if "vad" in manifest else None
    samples = np.concatenate([read_fixture(row), np.zeros(16000, dtype=np.float32)])
    for offset in range(0, len(samples), 1280):
        chunk = samples[offset:offset+1280]
        timestamp = offset*1_000_000//16000
        events = engine.accept(chunk, timestamp)
        print(json.dumps({'timestamp_us': timestamp, 'samples': chunk.tolist(), 'detections': events, 'speech':vad.accept(chunk) if vad else None}), flush=True)
        # Replay at real cadence; the Rust owner remains responsive to IPC/cancel.
        time.sleep(len(chunk)/16000)


if __name__ == '__main__':
    manifest = json.loads(Path(sys.argv[1]).read_text())
    if len(sys.argv) == 5 and sys.argv[3] == '--active-phrase': manifest['active_phrase'] = sys.argv[4]
    elif len(sys.argv) != 3: raise ValueError('invalid arguments')
    row = manifest['fixtures'][int(sys.argv[2])]
    stream_fixture(manifest, row)
