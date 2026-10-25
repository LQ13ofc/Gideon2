#!/usr/bin/env python3
"""WP-7 measurements for Portuguese (pt) and French (fr) speech: TTS, STT, wake and a PipeWire lab round trip.

Subcommands (run from the repo root; each writes only under target/wp7-measure/):
  tts   synthesizes scripts/wp7_sentences.json with the approved Pocket TTS profiles (target/tts-venv).
  stt   transcribes the synthetic WAVs through scripts/stt_worker.py (nemo_transducer engine, target/a1-venv) and
        reports word error rate per language. Every utterance goes through the worker's real stdin/stdout protocol.
  wake  runs the zh-en KWS (the one the package uses) on the synthetic WAVs with PT/FR wake phrases tokenized by hand
        (scripts/wp7_kws_pt_fr.txt) and counts hits and false hits.
  lab   PipeWire round trip: loads two lab modules (gideon_wp7_sink, gideon_wp7_mic; refuses if they exist), plays
        each synthetic WAV into the lab sink with pw-play, records the lab mic with pw-record, transcribes the
        recording with the STT worker and reports WER. Unloads exactly the modules it loaded. Never changes volumes
        or default devices.

Usage: python3 scripts/measure_pt_fr.py {tts|stt|wake|lab} [--limit N]
"""
import argparse
import json
import re
import signal
import subprocess
import sys
import time
import unicodedata
import wave
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'target/wp7-measure'
SENTENCES = BASE / 'scripts/wp7_sentences.json'
KWS_KEYWORDS = BASE / 'scripts/wp7_kws_pt_fr.txt'
TTS_PY = BASE / 'target/tts-venv/bin/python'
WORKER_PY = BASE / 'target/a1-venv/bin/python'
TTS_PROFILE = {'pt': BASE / 'target/tts-pt-assets/manifest.json', 'fr': BASE / 'target/tts-fr-assets/manifest.json'}
STT_MANIFEST = BASE / 'target/stt-pt-fr-assets/manifest.json'
KWS_ASSETS = BASE / 'target/a1-assets/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20'
LAB_SINK = 'gideon_wp7_sink'
LAB_MIC = 'gideon_wp7_mic'


def sentences(limit=None):
    rows = json.loads(SENTENCES.read_text())
    return rows[:limit] if limit else rows


def read_mono16k(path):
    with wave.open(str(path), 'rb') as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    samples = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != 16000:
        samples = np.interp(np.arange(0, len(samples), rate / 16000), np.arange(len(samples)), samples).astype(np.float32)
    return samples.astype(np.float32)


def norm_words(text):
    text = unicodedata.normalize('NFKD', text.lower())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9' ]+", ' ', text.replace('-', ' ').replace('’', "'")).split()


def word_errors(ref, hyp):
    r, h = norm_words(ref), norm_words(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)], len(r)


# WP-7c held-out wake set: sentences written after the WP-7 lab set and never used to choose the wake parameters.
# label 1 = contains the name "Gideon" (wake positive), 0 = no name, including hard negatives that share sounds
# with the name ("Deu", "Bidon", "Dom") or are common phrases. Rendered by the same Pocket TTS profiles.
HELDOUT_SENTENCES = [
    {'id': 'pt-pos01', 'lang': 'pt', 'label': 1, 'text': 'Oi Gideon, qual é o seu nome?'},
    {'id': 'pt-pos02', 'lang': 'pt', 'label': 1, 'text': 'Gideon, desligue as luzes da sala.'},
    {'id': 'pt-pos03', 'lang': 'pt', 'label': 1, 'text': 'Olá Gideon, quanto é dois mais dois?'},
    {'id': 'pt-pos04', 'lang': 'pt', 'label': 1, 'text': 'Gideon, toque uma música tranquila.'},
    {'id': 'pt-pos05', 'lang': 'pt', 'label': 1, 'text': 'Bom dia Gideon, como está o trânsito?'},
    {'id': 'pt-pos06', 'lang': 'pt', 'label': 1, 'text': 'Gideon, abra o arquivo de notas.'},
    {'id': 'pt-pos07', 'lang': 'pt', 'label': 1, 'text': 'Ei Gideon, você pode me ajudar?'},
    {'id': 'fr-pos01', 'lang': 'fr', 'label': 1, 'text': 'Bonjour Gideon, quel jour sommes-nous ?'},
    {'id': 'fr-pos02', 'lang': 'fr', 'label': 1, 'text': 'Gideon, éteins les lumières.'},
    {'id': 'fr-pos03', 'lang': 'fr', 'label': 1, 'text': "Salut Gideon, tu peux m'aider ?"},
    {'id': 'fr-pos04', 'lang': 'fr', 'label': 1, 'text': 'Gideon, mets de la musique calme.'},
    {'id': 'fr-pos05', 'lang': 'fr', 'label': 1, 'text': 'Bonsoir Gideon, quelle est la météo ?'},
    {'id': 'fr-pos06', 'lang': 'fr', 'label': 1, 'text': 'Gideon, ouvre le calendrier.'},
    {'id': 'pt-neg01', 'lang': 'pt', 'label': 0, 'text': 'A casa do meu avô fica perto do rio.'},
    {'id': 'pt-neg02', 'lang': 'pt', 'label': 0, 'text': 'Preciso comprar leite e ovos amanhã.'},
    {'id': 'pt-neg03', 'lang': 'pt', 'label': 0, 'text': 'Deu tudo certo no fim do dia.'},
    {'id': 'pt-neg04', 'lang': 'pt', 'label': 0, 'text': 'Dom Pedro foi o primeiro imperador do Brasil.'},
    {'id': 'pt-neg05', 'lang': 'pt', 'label': 0, 'text': 'Ela trabalha num hospital grande da cidade.'},
    {'id': 'fr-neg01', 'lang': 'fr', 'label': 0, 'text': 'Le train part à huit heures du matin.'},
    {'id': 'fr-neg02', 'lang': 'fr', 'label': 0, 'text': 'Nous avons mangé une soupe délicieuse hier soir.'},
    {'id': 'fr-neg03', 'lang': 'fr', 'label': 0, 'text': "Il fait beau et le ciel est bleu aujourd'hui."},
    {'id': 'fr-neg04', 'lang': 'fr', 'label': 0, 'text': 'Mon chat dort sur le canapé du salon.'},
    {'id': 'fr-neg05', 'lang': 'fr', 'label': 0, 'text': 'Bidon de lait vide sur la table de la cuisine.'},
]
HELDOUT_DIR = BASE / 'target/wp7c-heldout'


def cmd_heldout(args):
    """Renders HELDOUT_SENTENCES with the approved TTS profiles into target/wp7c-heldout/{lang}/{positive|negative}/."""
    for row in HELDOUT_SENTENCES:
        folder = HELDOUT_DIR / row['lang'] / ('positive' if row['label'] else 'negative')
        folder.mkdir(parents=True, exist_ok=True)
        wav = folder / f"{row['id']}.wav"
        if wav.exists() and not args.force:
            continue
        samples = synth(TTS_PROFILE[row['lang']], row['text'])
        with wave.open(str(wav), 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
            w.writeframes(np.clip(np.asarray(samples) * 32767, -32767, 32767).astype('<i2').tobytes())
        print(row['id'], f'{len(samples) / 24000:.2f}s', flush=True)
    (HELDOUT_DIR / 'sentences.json').write_text(json.dumps(HELDOUT_SENTENCES, ensure_ascii=False, indent=1) + '\n')


def cmd_tts(args):
    OUT.mkdir(parents=True, exist_ok=True)
    rows = sentences(args.limit)
    for row in rows:
        wav = OUT / f"{row['id']}.wav"
        if wav.exists() and not args.force:
            continue
        samples = synth(TTS_PROFILE[row['lang']], row['text'])
        with wave.open(str(wav), 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
            w.writeframes(np.clip(np.asarray(samples) * 32767, -32767, 32767).astype('<i2').tobytes())
        print(row['id'], f'{len(samples) / 24000:.2f}s', flush=True)


def synth(profile, text, sid=5):
    """One Pocket TTS job through scripts/tts_worker.py (the worker reads one job line and exits)."""
    proc = subprocess.Popen([str(TTS_PY), str(BASE / 'scripts/tts_worker.py'), str(profile)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    proc.stdin.write(json.dumps({'session_id': sid, 'text': text}) + '\n')
    proc.stdin.flush()
    samples = []
    for line in proc.stdout:
        message = json.loads(line)
        if message['op'] == 'pcm':
            samples.extend(message['samples'])
        elif message['op'] == 'done':
            break
    proc.stdin.close()
    if proc.wait(timeout=120) != 0:
        raise RuntimeError(proc.stderr.read()[-400:])
    return samples


class SttWorker:
    """Strict protocol client for scripts/stt_worker.py: start, frames (<= 2560 samples), finish -> final."""

    def __init__(self):
        self.proc = subprocess.Popen([str(WORKER_PY), str(BASE / 'scripts/stt_worker.py'), str(STT_MANIFEST)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        ready = json.loads(self.proc.stdout.readline() or '{}')
        if ready.get('op') != 'ready':
            raise RuntimeError('worker not ready: ' + self.proc.stderr.read()[-400:])
        self.sid = 0

    def transcribe(self, samples):
        self.sid += 1
        self.proc.stdin.write(json.dumps({'op': 'start', 'session_id': self.sid}) + '\n')
        end_us = 0
        for i in range(0, len(samples), 2560):
            chunk = samples[i:i + 2560]
            end_us = int((i + len(chunk)) * 1_000_000 / 16000)
            self.proc.stdin.write(json.dumps({'op': 'frame', 'session_id': self.sid, 'end_us': end_us,
                                              'samples': chunk.tolist()}) + '\n')
        self.proc.stdin.write(json.dumps({'op': 'finish', 'session_id': self.sid}) + '\n')
        self.proc.stdin.flush()
        final = json.loads(self.proc.stdout.readline())
        if final.get('op') != 'final':
            raise RuntimeError(f'unexpected reply {final}')
        return final['raw']

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=30)


def score(rows):
    summary = {}
    for lang in ('pt', 'fr'):
        picked = [r for r in rows if r['lang'] == lang]
        if not picked:
            continue
        errors = sum(r['errors'] for r in picked)
        words = sum(r['words'] for r in picked)
        summary[lang] = {'utterances': len(picked), 'errors': errors, 'words': words,
                         'wer': round(errors / words, 4), 'empty_hypotheses': sum(1 for r in picked if not r['hyp'].strip())}
    return summary


def cmd_stt(args):
    worker = SttWorker()
    rows = []
    try:
        for row in sentences(args.limit):
            wav = OUT / f"{row['id']}.wav"
            if not wav.exists():
                raise SystemExit(f'missing {wav}: run tts first')
            t0 = time.monotonic()
            hyp = worker.transcribe(read_mono16k(wav))
            decode = time.monotonic() - t0
            errors, words = word_errors(row['text'], hyp)
            rows.append({'id': row['id'], 'lang': row['lang'], 'ref': row['text'], 'hyp': hyp, 'errors': errors,
                         'words': words, 'decode_s': round(decode, 3)})
            print(row['id'], errors, words, repr(hyp), flush=True)
    finally:
        worker.close()
    result = {'summary': score(rows), 'rows': rows}
    (OUT / 'stt-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(result['summary'], ensure_ascii=False))


def kws_hits(path, keywords):
    import sherpa_onnx
    kws = sherpa_onnx.KeywordSpotter(tokens=str(KWS_ASSETS / 'tokens.txt'),
                                     encoder=str(KWS_ASSETS / 'encoder-epoch-13-avg-2-chunk-8-left-64.int8.onnx'),
                                     decoder=str(KWS_ASSETS / 'decoder-epoch-13-avg-2-chunk-8-left-64.onnx'),
                                     joiner=str(KWS_ASSETS / 'joiner-epoch-13-avg-2-chunk-8-left-64.int8.onnx'),
                                     keywords_file=str(keywords), num_threads=2, provider='cpu',
                                     keywords_threshold=KWS_THRESHOLD, keywords_score=1.0)
    x = read_mono16k(path)
    x = np.concatenate([np.zeros(48000, np.float32), x, np.zeros(16000, np.float32)])
    stream = kws.create_stream()
    hits = []
    for i in range(0, len(x), 320):
        stream.accept_waveform(16000, x[i:i + 320])
        while kws.is_ready(stream):
            kws.decode_stream(stream)
            result = kws.get_result(stream)
            if result:
                hits.append(result)
                kws.reset_stream(stream)
    return hits


KWS_THRESHOLD = 0.25


def cmd_wake(args):
    rows = sentences(args.limit)
    table = []
    for row in rows:
        wav = OUT / f"{row['id']}.wav"
        if not wav.exists():
            raise SystemExit(f'missing {wav}: run tts first')
        table.append({'id': row['id'], 'lang': row['lang'], 'text': row['text'], 'wake_word': 'gideon' in norm_words(row['text']),
                      'hits': kws_hits(wav, KWS_KEYWORDS)})
        print(row['id'], table[-1]['wake_word'], table[-1]['hits'], flush=True)
    positives = [r for r in table if r['wake_word']]
    result = {'threshold': KWS_THRESHOLD,
              'positives': len(positives), 'positives_detected': sum(1 for r in positives if r['hits']),
              'negatives': len(table) - len(positives), 'false_hits': sum(1 for r in table if not r['wake_word'] and r['hits']),
              'rows': table}
    (OUT / 'wake-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))


LAB_CLIPS = Path('/tmp/gideon-wake-lab/clips')  # EN lab clips (not in the repo, see docs/A14-live-stt-fix.md)
SILERO = BASE / 'target/a2-assets/silero_vad-v5.onnx'


def silero_flags(x, threshold, min_silence):
    import sherpa_onnx
    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = str(SILERO)
    cfg.silero_vad.threshold = threshold
    cfg.silero_vad.min_speech_duration = 0.1
    cfg.silero_vad.min_silence_duration = min_silence
    cfg.silero_vad.window_size = 512
    cfg.sample_rate = 16000
    vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)
    flags = []
    for i in range(0, len(x), 320):
        vad.accept_waveform(x[i:i + 320])
        flags.append(vad.is_speech_detected())
        while not vad.empty():
            vad.pop()
    return np.array(flags)


def cmd_vad(args):
    """Wake timing on the EN lab clips (KWS zh-en, live wake path) against silero speech flags, and the share of
    speech-flagged frames on negatives for each silero setting. Answers whether the VAD threshold can cause no_speech."""
    import sherpa_onnx
    kws = sherpa_onnx.KeywordSpotter(tokens=str(KWS_ASSETS / 'tokens.txt'),
                                     encoder=str(KWS_ASSETS / 'encoder-epoch-13-avg-2-chunk-8-left-64.int8.onnx'),
                                     decoder=str(KWS_ASSETS / 'decoder-epoch-13-avg-2-chunk-8-left-64.onnx'),
                                     joiner=str(KWS_ASSETS / 'joiner-epoch-13-avg-2-chunk-8-left-64.int8.onnx'),
                                     keywords_file=str(KWS_ASSETS / 'keywords.txt'), num_threads=2, provider='cpu',
                                     keywords_threshold=0.25, keywords_score=1.0)
    rows = []
    for clip in sorted((LAB_CLIPS / 'positive').glob('pos-hey_*-clean.wav')):
        x = read_mono16k(clip)
        padded = np.concatenate([np.zeros(48000, np.float32), x, np.zeros(16000, np.float32)])
        stream = kws.create_stream()
        wake_s = None
        for i in range(0, len(padded), 320):
            stream.accept_waveform(16000, padded[i:i + 320])
            while kws.is_ready(stream):
                kws.decode_stream(stream)
                if kws.get_result(stream) and wake_s is None:
                    wake_s = i / 16000 - 3.0
                    kws.reset_stream(stream)
        flags = silero_flags(padded, 0.5, 0.1)
        speech = np.flatnonzero(np.diff(flags.astype(int)) != 0) * 0.02 - 3.0
        rows.append({'clip': clip.name, 'kws_wake_s': None if wake_s is None else round(wake_s, 2),
                     'vad_edges_s': [round(float(t), 2) for t in speech]})
        print(rows[-1], flush=True)
    negatives = sorted((LAB_CLIPS / 'negative').glob('neg-*.wav'))
    sweep = {}
    for threshold in (0.3, 0.4, 0.5):
        for min_silence in (0.1, 0.3):
            flagged = total = 0
            for clip in negatives:
                flags = silero_flags(read_mono16k(clip), threshold, min_silence)
                flagged += int(flags.sum())
                total += len(flags)
            sweep[f'thr={threshold},min_silence={min_silence}'] = round(flagged / total, 4)
            print('negatives speech-flagged share', threshold, min_silence, round(flagged / total, 4), flush=True)
    result = {'positives': rows, 'negatives_speech_flagged_share': sweep, 'negative_clips': len(negatives)}
    (OUT / 'vad-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')


def pactl(*args):
    return subprocess.run(['pactl', *args], capture_output=True, text=True, timeout=20).stdout.strip()


def lab_modules():
    return [line for line in pactl('list', 'short', 'modules').splitlines() if LAB_SINK in line or LAB_MIC in line]


def cmd_lab(args):
    OUT.mkdir(parents=True, exist_ok=True)
    if lab_modules():
        print('refusing: lab modules already exist', file=sys.stderr)
        return 2
    loaded = []
    rows = []
    try:
        loaded.append(pactl('load-module', 'module-null-sink', f'sink_name={LAB_SINK}',
                            'sink_properties=device.description=GideonWp7Sink'))
        loaded.append(pactl('load-module', 'module-remap-source', f'master={LAB_SINK}.monitor',
                            f'source_name={LAB_MIC}', 'source_properties=device.description=GideonWp7Mic'))
        worker = SttWorker()
        try:
            for row in sentences(args.limit):
                wav = OUT / f"{row['id']}.wav"
                rec_path = OUT / f"lab-{row['id']}.wav"
                recorder = subprocess.Popen(['pw-record', '--target', LAB_MIC, '--rate', '16000', '--channels', '1',
                                             '--format', 's16', str(rec_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(0.6)
                duration = wave.open(str(wav)).getnframes() / 24000
                subprocess.run(['pw-play', '--target', LAB_SINK, str(wav)], timeout=120, check=False)
                time.sleep(1.2)
                recorder.send_signal(signal.SIGINT)
                recorder.wait(timeout=20)
                samples = read_mono16k(rec_path)
                hyp = worker.transcribe(samples)
                errors, words = word_errors(row['text'], hyp)
                rows.append({'id': row['id'], 'lang': row['lang'], 'ref': row['text'], 'hyp': hyp, 'errors': errors,
                             'words': words, 'recorded_s': round(len(samples) / 16000, 2), 'clip_s': round(duration, 2)})
                print(row['id'], errors, words, repr(hyp), flush=True)
                rec_path.unlink(missing_ok=True)
        finally:
            worker.close()
    finally:
        for module in reversed(loaded):
            if module:
                pactl('unload-module', module)
        left = len(lab_modules())
    result = {'summary': score(rows), 'rows': rows, 'lab_modules_left': left}
    (OUT / 'lab-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(result['summary'], ensure_ascii=False), 'lab_modules_left', left)
    return 0 if left == 0 else 1


LAB_WAKE_OUT = BASE / 'target/wp7c-lab-wake'
LAB_WAKE_EVIDENCE = BASE / 'docs/evidence/wake-pt-fr-lab-live.json'
LAB_WAKE_GAP_S = 3.0


def cmd_lab_wake(args):
    """PipeWire round trip for the transcript wake (WP-7c). Plays each lab clip into the lab sink, records the lab
    mic to one raw file, then feeds that file through scripts/wake_worker.py (live protocol, one 20 ms frame per
    packet) with the transcript manifest. Detections are attributed to the clip windows by their play times.
    Loads and unloads exactly the two lab modules (refuses if they exist); never changes volumes or defaults."""
    import wake_pt_fr_regression as R
    LAB_WAKE_OUT.mkdir(parents=True, exist_ok=True)
    if lab_modules():
        print('refusing: lab modules already exist', file=sys.stderr)
        return 2
    root, pins_path = R.SETS[args.set]
    clips = R.clip_list(root)
    if not R.verify_pins(root, pins_path, clips):
        return 2
    manifest_path = LAB_WAKE_OUT / 'manifest.json'
    manifest_path.write_text(json.dumps(R.manifest(), indent=1) + '\n')
    loaded = []
    rec_path = LAB_WAKE_OUT / 'lab-recording.wav'
    plays = []
    try:
        loaded.append(pactl('load-module', 'module-null-sink', f'sink_name={LAB_SINK}',
                            'sink_properties=device.description=GideonWp7Sink'))
        loaded.append(pactl('load-module', 'module-remap-source', f'master={LAB_SINK}.monitor',
                            f'source_name={LAB_MIC}', 'source_properties=device.description=GideonWp7Mic'))
        recorder = subprocess.Popen(['pw-record', '--target', LAB_MIC, '--rate', '16000', '--channels', '1',
                                     '--format', 's16', str(rec_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.6)
        t0 = time.monotonic()
        # Fixed order (lang, label, file) as in clip_list(); a 3 s gap after each clip.
        for lang, label, path in clips:
            start = time.monotonic() - t0
            subprocess.run(['pw-play', '--target', LAB_SINK, str(path)], timeout=120, check=False)
            plays.append({'file': str(path.relative_to(root)), 'label': label, 'start_s': round(start, 3),
                          'end_s': round(time.monotonic() - t0, 3)})
            time.sleep(LAB_WAKE_GAP_S)
        time.sleep(1.0)
        recorder.send_signal(signal.SIGINT)
        recorder.wait(timeout=20)
    finally:
        for module in reversed(loaded):
            if module:
                pactl('unload-module', module)
        left = len(lab_modules())
    # The worker expects the live format: 16 kHz mono s16, 320-sample frames.
    samples = np.clip(np.round(read_mono16k(rec_path) * 32767), -32768, 32767).astype('<i2')
    proc = subprocess.Popen([str(WORKER_PY), str(BASE / 'scripts/wake_worker.py'), str(manifest_path), '--live',
                             '--start-us', '0', '--keywords-threshold', '0.25'],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    detections = []

    def reader():
        for line in proc.stdout:
            packet = json.loads(line)
            for event in packet['detections']:
                detections.append(event['end_us'])

    import threading
    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        for offset in range(0, len(samples) - len(samples) % 320, 320):
            proc.stdin.write(samples[offset:offset + 320].tobytes())
        proc.stdin.flush()
    finally:
        proc.stdin.close()
        thread.join(timeout=600)
        proc.wait(timeout=60)
    err = proc.stderr.read().decode(errors='replace')[-400:]
    if proc.returncode != 0:
        print('worker failed:', err, file=sys.stderr)
        return 1
    cooldown_us = R.COOLDOWN_US
    accepted = []
    for end in sorted(detections):
        if not accepted or end - accepted[-1] >= cooldown_us:
            accepted.append(end)
    rows = []
    for play in plays:
        start_us = int((play['start_s'] + 0.1) * 1_000_000)
        stop_us = int((play['end_s'] + R.TAIL_S) * 1_000_000)
        hit = any(start_us <= end < stop_us for end in accepted)
        rows.append({**play, 'detected': hit})
    outside = [end for end in accepted if not any(
        int((p['start_s'] + 0.1) * 1_000_000) <= end < int((p['end_s'] + R.TAIL_S) * 1_000_000) for p in plays)]
    positives = [r for r in rows if r['label'] == 1]
    negatives = [r for r in rows if r['label'] == 0]
    result = {'set': args.set, 'recording_s': round(len(samples) / 16000, 1), 'lab_modules_left': left,
              'positives': len(positives), 'positive_hits': sum(1 for r in positives if r['detected']),
              'negatives': len(negatives), 'negative_false_triggers': sum(1 for r in negatives if r['detected']),
              'detections_outside_clips': len(outside), 'rows': rows}
    LAB_WAKE_EVIDENCE.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))
    rec_path.unlink(missing_ok=True)
    return 0 if left == 0 else 1


def main():
    parser = argparse.ArgumentParser(description='WP-7 PT/FR voice measurements.')
    parser.add_argument('command', choices=['tts', 'stt', 'wake', 'lab', 'vad', 'heldout', 'lab-wake'])
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--set', choices=['lab', 'heldout'], default='lab')
    args = parser.parse_args()
    if args.command == 'tts':
        cmd_tts(args)
    elif args.command == 'heldout':
        cmd_heldout(args)
    elif args.command == 'lab-wake':
        return cmd_lab_wake(args)
    elif args.command == 'stt':
        cmd_stt(args)
    elif args.command == 'wake':
        cmd_wake(args)
    elif args.command == 'vad':
        cmd_vad(args)
    else:
        return cmd_lab(args)
    return 0


if __name__ == '__main__':
    sys.exit(main())
