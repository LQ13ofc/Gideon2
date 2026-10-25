"""STT worker. Only Core's private PCM pipe is accepted.

Two engines, chosen by the manifest:
- Moonshine small streaming EN (default, streaming partials): `model_type` absent.
- sherpa-onnx offline transducer `nemo_transducer` (WP-7): one multilingual model for Portuguese and French
  (NVIDIA Parakeet-TDT-0.6B-v3, int8 ONNX). It has no streaming partials: the Core receives audio in frames, the
  worker decodes the whole utterance on `finish` and emits one `final`. Utterances are bounded by the Core (30 s).
"""
import importlib.metadata
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pcm_fixture import check_hash, np
try:  # the moonshine engine only; the nemo_transducer engine runs in a sherpa-only environment
    from moonshine_voice import Transcriber
    from moonshine_voice.moonshine_api import ModelArch
except ImportError:
    Transcriber = ModelArch = None

ENGINE='moonshine-voice-0.1.5/small-streaming-en-quantized-26_08_21'
NEMO_ENGINE='sherpa-onnx-1.13.8/nemo-parakeet-tdt-0.6b-v3-int8'
NEMO_LANGUAGES={'pt','fr'}
MAX_UTTERANCE_SAMPLES=16000*30
# Offline decoding of a short utterance needs silence on both sides (measured: 'Olá Gideon.' decoded to nothing without it).
TAIL_PAD_SAMPLES=int(16000*0.5)


def emit(value):
    print(json.dumps(value,ensure_ascii=True),flush=True)


def run(manifest):
    if manifest.get('model_type')=='nemo_transducer':return run_nemo(manifest)
    return run_moonshine(manifest)


def check_message(req):
    """Strict frame check shared by both engines (live frames are <= 2560 samples, finite, within [-1, 1])."""
    samples=np.asarray(req['samples'],dtype=np.float32)
    if not 0<len(samples)<=2560 or not np.isfinite(samples).all() or np.max(np.abs(samples))>1:raise ValueError('invalid PCM')
    return samples


def run_nemo(manifest):
    import sherpa_onnx
    if manifest['engine']!=NEMO_ENGINE or sherpa_onnx.__version__!='1.13.8':raise ValueError('version mismatch')
    languages=manifest.get('languages')
    if not isinstance(languages,list) or not languages or not set(languages)<=NEMO_LANGUAGES:raise ValueError('unsupported STT language')
    root=Path(manifest['model_root'])
    names={manifest['encoder'],manifest['decoder'],manifest['joiner'],manifest['tokens']}
    if set(manifest['hashes'])!=names:raise ValueError('missing model hashes')
    for name,digest in manifest['hashes'].items():
        if Path(name).name!=name:raise ValueError('unsafe asset path')
        check_hash(root/name,digest)
    recognizer=sherpa_onnx.OfflineRecognizer.from_transducer(encoder=str(root/manifest['encoder']),decoder=str(root/manifest['decoder']),joiner=str(root/manifest['joiner']),tokens=str(root/manifest['tokens']),num_threads=4,provider='cpu',model_type='nemo_transducer',decoding_method='greedy_search')
    state=None;audio=[];samples_total=0
    emit({'op':'ready','engine':NEMO_ENGINE})
    while True:
        line=sys.stdin.buffer.readline(65537)
        if not line:break
        if len(line)>65536 or not line.endswith(b'\n'):raise ValueError('oversize/partial message')
        req=json.loads(line);sid=req['session_id'];op=req['op']
        if not isinstance(sid,int) or not 0<=sid<2**64:raise ValueError('invalid session')
        if op=='start':
            state={'session_id':sid,'end_us':0};audio=[];samples_total=0
        elif op in ('frame','finish','cancel'):
            if state is None or state['session_id']!=sid:continue
            if op=='frame':
                samples=check_message(req)
                samples_total+=len(samples)
                if samples_total>MAX_UTTERANCE_SAMPLES:raise ValueError('utterance too long')
                audio.append(samples);state['end_us']=req['end_us']
            elif op=='finish':
                stream=recognizer.create_stream()
                if audio:
                    pad=np.zeros(TAIL_PAD_SAMPLES,dtype=np.float32)
                    stream.accept_waveform(16000,np.concatenate([pad,*audio,pad]).astype(np.float32))
                recognizer.decode_stream(stream)
                raw=' '.join(stream.result.text.split())
                emit({'op':'final','engine':NEMO_ENGINE,'session_id':sid,'revision':1,'audio_end_us':state['end_us'],'raw':raw})
                state=None;audio=[];samples_total=0
            else:
                state=None;audio=[];samples_total=0
        else:raise ValueError('unknown operation')


def run_moonshine(manifest):
    if manifest['engine']!=ENGINE or importlib.metadata.version('moonshine-voice')!='0.1.5':raise ValueError('version mismatch')
    root=Path(manifest['model_root'])
    required={'adapter.ort','cross_kv.ort','decoder_kv.ort','encoder.ort','frontend.model.ort','frontend.weights.ort','streaming_config.json','tokenizer.bin'}
    if set(manifest['hashes'])!=required:raise ValueError('missing model hashes')
    for name,digest in manifest['hashes'].items():check_hash(root/name,digest)
    transcriber=Transcriber(root,ModelArch.SMALL_STREAMING,update_interval=.25,options={'vad_threshold':0.,'ort_providers':'CPU','return_audio_data':False,'log_output_text':False,'log_api_calls':False,'identify_speakers':False,'vad_max_segment_duration':30.})
    stream=None;state=None
    emit({'op':'ready','engine':ENGINE})
    try:
        while True:
            line=sys.stdin.buffer.readline(65537)
            if not line:break
            if len(line)>65536 or not line.endswith(b'\n'):raise ValueError('oversize/partial message')
            req=json.loads(line);sid=req['session_id'];op=req['op']
            if not isinstance(sid,int) or not 0<=sid<2**64:raise ValueError('invalid session')
            if op=='start':
                if stream:stream.close()
                state={'session_id':sid,'revision':0,'end_us':0,'lines':{},'raw':''}
                stream=transcriber.create_stream(update_interval=.25)
                def listener(event, owner_state=state, owner_sid=sid):
                    # SDK callbacks may arrive after stream close/new session. Never
                    # borrow the next loop iteration's mutable state/session ID.
                    if state is not owner_state:return
                    if getattr(event,'error',None):
                        emit({'op':'error'})  # Owner's strict protocol fails closed.
                        return
                    data=getattr(event,'line',None)
                    if data is None:return
                    state['lines'][data.line_id]=data.text
                    raw=' '.join(t for t in state['lines'].values() if t)
                    if len(raw.encode())>4096:
                        emit({'op':'error'});return
                    if raw and raw!=state['raw']:
                        state['raw']=raw;state['revision']+=1
                        emit({'op':'partial','engine':ENGINE,'session_id':owner_sid,'revision':state['revision'],'audio_end_us':state['end_us'],'raw':raw})
                stream.add_listener(listener);stream.start()
            elif op in ('frame','finish','cancel'):
                if state is None or state['session_id']!=sid:continue
                if op=='frame':
                    samples=np.asarray(req['samples'],dtype=np.float32)
                    # Up to 160 ms per message: the Core merges live frames (src/stt.rs LIVE_CHUNK_SAMPLES = 2560).
                    if not 0<len(samples)<=2560 or not np.isfinite(samples).all() or np.max(np.abs(samples))>1:raise ValueError('invalid PCM')
                    state['end_us']=req['end_us'];stream.add_audio(samples.tolist(),16000)
                elif op=='finish':
                    result=stream.stop()
                    if result is None:raise RuntimeError('missing native final')
                    raw=' '.join(line.text for line in result.lines if line.text)
                    state['revision']+=1
                    emit({'op':'final','engine':ENGINE,'session_id':sid,'revision':state['revision'],'audio_end_us':state['end_us'],'raw':raw})
                    state=None;stream.close();stream=None
                else:
                    state=None;stream.close();stream=None
            else:raise ValueError('unknown operation')
    finally:
        if stream:stream.close()
        transcriber.close()


if __name__=='__main__':
    run(json.loads(Path(sys.argv[1]).read_text()))
