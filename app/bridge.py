"""Thin, bounded Qt IPC adapter. Core owns all parsing, sessions and authority."""
import datetime,hashlib,json,math,os,re,stat,struct,time,unicodedata,uuid
import socket as _sock
from pathlib import Path
from urllib.parse import unquote,urlsplit
from PySide6.QtCore import QObject,Property,Signal,Slot,QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalSocket
CAPABILITY_ID=re.compile(r'[a-z0-9_]+(\.[a-z0-9_]+)+');PLUGIN_ID=re.compile(r'[A-Za-z0-9_-]+');SNAKE_CODE=re.compile(r'[a-z][a-z0-9_]*')
PLUGIN_STATES=('disabled','starting','running','failed','stopped','quarantined')
# Exact status sets emitted by the Core (src/core.rs, src/transport.rs). Anything else is an invalid snapshot.
WAKE_STATES=('unavailable','starting','replaying','failed','replay_finished')
STT_STATES=('unavailable','starting','ready','failed')
# Content-free STT failure reasons (src/stt.rs, src/live.rs reason_for); optional key stt_last_error.
STT_REASONS=('worker_crashed','worker_import_error','model_missing','worker_unavailable','worker_timeout','worker_backlog')
SPEECH_STATES=('unavailable','idle','muted','disabled','speaking','completed','failed','cancelled','timed_out','audio_error','stt_failed','stt_unavailable','transcript_final','capture_completed','no_speech','capture_too_long')
OUTPUT_LIMIT=8192;TEXT_LIMIT=512;HEX=frozenset('0123456789abcdef')
# Portuguese words for the Core state codes shown in the diagnostic line (same words as Main.qml statusLabels).
DIAG_LABELS={'unavailable':'indisponível','starting':'iniciando','replaying':'reproduzindo','failed':'falhou','replay_finished':'replay encerrado','ready':'pronto','idle':'em espera','muted':'mudo','disabled':'desligado','speaking':'respondendo','completed':'concluído','cancelled':'cancelado','timed_out':'tempo esgotado','audio_error':'erro de áudio','stt_failed':'falha na transcrição','stt_unavailable':'transcrição indisponível','transcript_final':'transcrição final','capture_completed':'captura concluída','no_speech':'sem fala detectada','capture_too_long':'captura longa demais'}
# Runtime state of an installed plugin: `disabled` when not enabled, else the host state (src/plugins.rs runtime_of).
# `stopped` is a host state too (a late stop event can land after a re-enable), so it is accepted.
RUNTIME_STATES=('disabled','starting','running','failed','stopped')
# Codes Core writes to plugin last_error (src/plugins.rs runtime start, violation and crash paths).
PLUGIN_LAST_ERRORS=frozenset({'plugin_crashed','plugin_cpu_exceeded','plugin_output_invalid','plugin_start_failed','plugin_not_runnable','plugin_quarantined','handshake_timeout','handshake_mismatch'})
# Codes a capability_result can carry (src/plugins.rs PASS_THROUGH_ERRORS plus Core-owned results).
CANCEL_CODES=frozenset({'cancelled','invoke_cancelled'})  # a cancelled capability is reported as invoke_cancelled by the Core (src/plugins.rs); 'cancelled' is the older name
CAPABILITY_ERRORS=frozenset({'backend_unavailable','key_missing','cloud_not_authorized','provider_not_configured','permission_denied','http_error','timeout','response_too_large','network_unavailable','cancelled','invalid_input','host_not_allowed','redirect_refused','busy','invalid_host_call','plugin_error','plugin_not_runnable','plugin_output_invalid','plugin_cpu_exceeded','capability_unavailable','capability_timeout','invoke_cancelled','model_unsupported_feature','model_not_found','model_selftest_failed','settings_unavailable','opt_in_required','stale_screen','unsupported','unknown_service','unknown_element','no_focus','unknown_route','unknown_app','indicator_off','already_recording','not_recording','world_unavailable','skill_invalid','model_output_invalid'})  # C4/S4 codes: plugin answers that the Core passes through unchanged (src/plugins.rs PASS_THROUGH_ERRORS)
# Tool proposal reasons (src/tools.rs and src/core.rs tool_denied/tool_failed).
TOOL_REASONS=frozenset({'superseded','expired','plugin_unavailable','executor_failed','executor_unavailable','user_denied','invalid_args','unknown_tool','busy'})
HUB_REASONS=('ledger_missing','ledger_invalid')
# WP-4 Hub import: the Core takes at most 2048 hex characters per hub_chunk (src/hub.rs chunk_import), so 1 KiB per request.
HUB_CHUNK_BYTES=1024
HUB_UPLOAD_MESSAGES={'busy':'Importação indisponível agora: o Core precisa estar conectado, sem sessão de voz e com o catálogo verificado',
    'entry':'Importe só o pacote de um plugin com permissões aprovadas e sem pacote guardado; nada foi enviado',
    'path':'Escolha um arquivo comum, por caminho absoluto; links simbólicos não são aceitos; nada foi enviado',
    'unreadable':'Não consegui abrir o arquivo do pacote; nada foi enviado',
    'size':'O tamanho do arquivo não bate com o tamanho do catálogo; nada foi enviado',
    'sending':'Enviando pacote ao Core…',
    'progress':'Enviando pacote: {done} de {total} bytes',
    'staged':'Pacote verificado e guardado pelo Core; ainda não instalado.',
    'hub_import_missing':'O Core não abriu a importação; nada foi guardado',
    'cancelled':'Importação cancelada; nada foi guardado',
    'core_offline':'Core desconectado durante a importação; nada foi guardado'}
STAGED_ERRORS=('staged_payload_invalid',)
# Finish reasons of the capture session (src/core.rs finish), recorded in capture.reason.
CAPTURE_REASONS=('audio_error','cancelled','capture_completed','stt_failed','stt_unavailable','transcript_final','no_speech','capture_too_long')
STT_SOURCES=('voice','user_text')
COMMAND_KINDS={'open_app':('desktop_id',),'volume':('level',),'mute':(),'unmute':(),'volume_up':(),'volume_down':(),'status':(),'time':(),'date':(),'cancel':()}
TOP_KEYS=frozenset({'version','request_id','code','state','session_id','sequence','events','plugins','llm','tool_proposals','text_input_available','speech_samples','speech_status','stt_status','stt_last_error','wake_status','hub','capability_result','partial','base_pack','configuration_status','configuration_recovery_available','preferences','actions','command','speech','transcript','capture','agent','skills','connections','registry','audio','languages','wake_phrases','phrase_check','personal','personal_reply'})
TOP_REQUIRED=frozenset({'version','request_id','code','state','session_id','sequence','events','plugins','llm','tool_proposals','text_input_available','speech_samples','speech_status','stt_status','wake_status'})
HUB_KEYS=frozenset({'version','status','publisher_verified','approval_revision','install_revision','installed','import','entries','orphans','reason','repository','catalog_sha256'})
HUB_REQUIRED=HUB_KEYS-{'reason'}
ENTRY_KEYS=frozenset({'manifest_sha256','permissions_approved','approved_at_ms','payload_staged','staged_error','plugin_id','semver','publisher','api_version','targets','license','permissions','dependencies','conflicts','download_size','support_policy','runtime','capabilities','status','reason'})
ENTRY_REQUIRED=ENTRY_KEYS-{'staged_error','runtime','capabilities','approved_at_ms'}
PREFERENCE_KEYS=frozenset({'version','session_timeout_ms','wake_phrase','revision','audible_feedback','visual_feedback','output_volume_percent','previous_preferences','wake_sensitivity','input_conditioning','audio_input_device','audio_output_device','live_audio','real_actions','stt_languages','tts_language','tts_voice','wake_phrases','history_retention','developer_mode'})
# CFG-04 retention (src/storage.rs HistoryRetention): exactly these four wire values. DIAG-02 developer mode is a strict bool.
HISTORY_RETENTION_VALUES=('days_7','days_30','days_90','never')
# DIAG-05 resource sampling: CPU ticks per second is read from the system (SC_CLK_TCK); the sample keeps the previous reading per pid.
CLOCK_TICKS=os.sysconf('SC_CLK_TCK') if hasattr(os,'sysconf') else 100
LATENCY_SAMPLES=20
def _peer_pid(sock):
    """Core process id: SO_PEERCRED on the connected local socket (Linux). None when the kernel or the socket cannot tell."""
    try:
        fd=int(sock.socketDescriptor())
        if fd<0:return None
        with _sock.socket(fileno=os.dup(fd)) as peer:
            pid,_uid,_gid=struct.unpack('3i',peer.getsockopt(_sock.SOL_SOCKET,_sock.SO_PEERCRED,struct.calcsize('3i')))
        return pid if pid>0 else None
    except (OSError,ValueError,struct.error,AttributeError):return None
def _proc_sample(pid):
    """(cpu ticks, rss kB, ppid) of one process from /proc, or None when it is gone or /proc is missing."""
    try:
        with open(f'/proc/{pid}/stat','rb') as handle:raw=handle.read().decode('ascii','replace')
        fields=raw[raw.rindex(')')+2:].split()
        ticks=int(fields[11])+int(fields[12])  # utime (field 14) + stime (field 15)
        with open(f'/proc/{pid}/status','rb') as handle:
            rss=next((int(line.split()[1]) for line in handle.read().decode('ascii','replace').splitlines() if line.startswith('VmRSS:')),0)
        return ticks,rss,int(fields[1])
    except (OSError,ValueError,IndexError):return None
def _children(pid):
    """Direct children from the kernel's task children list. None when the kernel does not expose it."""
    try:
        with open(f'/proc/{pid}/task/{pid}/children','rb') as handle:return [int(p) for p in handle.read().split()]
    except (OSError,ValueError):return None
# Frases de ativação (src/phrases.rs): the Core owns the catalog, tokens and measurements; these checks shape the wire.
WAKE_PHRASE_BLOCK_KEYS=frozenset({'max_active','max_custom','custom_revision','lexicon','settings','active','phrases','test'})
WAKE_PHRASE_ENTRY_KEYS=frozenset({'id','text','tokens','label','language','qualification','custom','selectable','boost','threshold','measurement'})
WAKE_PHRASE_QUALIFICATIONS=('dev_qualified','poc_required','custom')
WAKE_TEST_STATES=('running','done','failed')
PHRASE_CHECK_KEYS=frozenset({'ok','code','text','tokens','word'})
# Idiomas (src/languages.rs, docs/research/idiomas-stt-tts.md): the Core owns the catalog; these checks only shape the wire.
LANGUAGE_STATES=('bundled','available_not_installed','unsupported')
LANGUAGE_ITEM_KEYS=frozenset({'id','kind','label','state','engine','size_bytes','size_partial','size_note','license','sha256','quality','evidence','voices','reason','selected','selectable','source'})
LANGUAGE_BLOCK_KEYS=frozenset({'version','engines','stt_selected','tts_selected','tts_voice','restart_required','install'})
VOICE_ID=re.compile(r'[A-Za-z0-9_-]{1,64}')
# Core bounds (src/storage.rs): sensitivity 0.5..=1.5; device names 1..=128 bytes from this charset.
DEVICE_CHARS=frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:@/+ -')
def wake_sensitivity_ok(value):return type(value) in (int,float) and math.isfinite(value) and 0.5<=value<=1.5
# Preference `input_conditioning` (src/storage.rs InputConditioning): the Core accepts exactly these two values.
INPUT_CONDITIONING_VALUES=('auto','off')
def audio_device_ok(value):return isinstance(value,str) and 1<=len(value.encode('utf-8'))<=128 and all(c in DEVICE_CHARS for c in value)
# A4/A5 snapshot block `audio` (src/live.rs, src/devices.rs). `live` is always present from the Core; `devices` only after audio_devices.
AUDIO_SOURCES=('pactl','pw-dump','none')
AUDIO_REASONS=('no_audio_tool','audio_tool_failed')
LIVE_INPUT_STATES=('idle','capturing','error')
LIVE_OUTPUT_STATES=('idle','playing','error')
# A13: content-free reasons of a failed live input (src/live.rs reason_for). Older codes stay accepted.
LIVE_ERRORS=('recorder_unavailable','recorder_exited','sandbox_unavailable','wake_worker_unavailable','wake_worker_failed','restart_limit','invalid_device','player_unavailable','player_write_failed','player_failed','player_timeout','worker_crashed','worker_import_error','device_unavailable','model_missing')
def audio_devices_ok(d):
    if not isinstance(d,dict) or not {'inputs','outputs','source'}<=set(d)<={'inputs','outputs','source','reason'}:return False
    lists=(d['inputs'],d['outputs'])
    if not all(isinstance(x,list) and len(x)<=16 for x in lists) or d['source'] not in AUDIO_SOURCES:return False
    for item in lists[0]+lists[1]:
        if not isinstance(item,dict) or set(item)!={'id','label','default'} or not audio_device_ok(item['id']) or type(item['default']) is not bool:return False
        if not isinstance(item['label'],str) or not 1<=len(item['label'].encode('utf-8'))<=128:return False
    if d['source']=='none':return 'reason' in d and d['reason'] in AUDIO_REASONS and not lists[0] and not lists[1]
    return 'reason' not in d
# A9 level meter, warnings, last detection and the probe (src/levels.rs, src/live.rs). Numbers and closed codes only.
LIVE_WARNINGS=('no_frames','clipping','very_noisy','very_quiet')
PROBE_STATES=('running','done')
PROBE_VERDICTS=('ok','quiet','noisy','silent','error')
PROBE_REASONS=('recorder_unavailable','sandbox_unavailable','invalid_device','recorder_exited')
LEVEL_KEYS=frozenset({'rms_dbfs','peak_dbfs','floor_dbfs','speech_active','speech_ms','speech_unmatched','frames','last_frame_age_ms','clipping'})
PHRASE_ID=re.compile(r'[A-Za-z0-9_-]{1,64}')
def dbfs_ok(value):return type(value) in (int,float) and math.isfinite(value) and -90<=value<=0
def level_ok(level):
    if not isinstance(level,dict) or set(level)!=LEVEL_KEYS:return False
    if not all(dbfs_ok(level[k]) for k in ('rms_dbfs','peak_dbfs','floor_dbfs')):return False
    if any(type(level[k]) is not bool for k in ('speech_active','speech_unmatched','clipping')):return False
    if type(level['speech_ms']) is not int or level['speech_ms']<0 or type(level['frames']) is not int or level['frames']<0:return False
    age=level['last_frame_age_ms']
    if age is not None and (type(age) is not int or age<0):return False
    return not level['speech_unmatched'] or (level['speech_active'] and level['speech_ms']>=0)
def detection_ok(det):
    return isinstance(det,dict) and set(det)=={'at_ms','phrase_id'} and type(det['at_ms']) is int and det['at_ms']>=0 and isinstance(det['phrase_id'],str) and PHRASE_ID.fullmatch(det['phrase_id']) is not None
def probe_ok(probe):
    if not isinstance(probe,dict) or probe.get('state') not in PROBE_STATES:return False
    base={'id','device','state'}
    done={'frames','rms_dbfs','peak_dbfs','floor_dbfs','verdict','hint'}
    keys=set(probe)
    if not base<=keys<=base|done|{'reason'} or type(probe['id']) is not int or probe['id']<1 or not audio_device_ok(probe['device']):return False
    if probe['state']=='running':return keys==base
    if not done<=keys:return False
    if type(probe['frames']) is not int or probe['frames']<0 or probe['verdict'] not in PROBE_VERDICTS:return False
    if not all(dbfs_ok(probe[k]) for k in ('rms_dbfs','peak_dbfs','floor_dbfs')):return False
    if not isinstance(probe['hint'],str) or not 1<=len(probe['hint'].encode('utf-8'))<=300:return False
    # A reason comes with the error verdict and nothing else.
    return ('reason' in probe)==(probe['verdict']=='error') and ('reason' not in probe or probe['reason'] in PROBE_REASONS)
def audio_live_ok(live):
    base={'enabled','input_state','output_state','mic_active','restart_required','level','silence_warning'}
    if not isinstance(live,dict) or not base<=set(live)<=base|{'last_error','last_detection'}:return False
    if type(live['enabled']) is not bool or type(live['mic_active']) is not bool or type(live['restart_required']) is not bool:return False
    if live['input_state'] not in LIVE_INPUT_STATES or live['output_state'] not in LIVE_OUTPUT_STATES:return False
    if 'last_error' in live and live['last_error'] not in LIVE_ERRORS:return False
    # The microphone indicator is only true while the recorder captures; a disabled feature is idle.
    if live['mic_active']!=(live['input_state']=='capturing'):return False
    if not level_ok(live['level']):return False
    # The level and the warning describe the recorder only: while it is not capturing both are silent.
    if live['input_state']!='capturing' and (live['level']['frames']!=0 or live['silence_warning'] is not None):return False
    if live['silence_warning'] is not None and live['silence_warning'] not in LIVE_WARNINGS:return False
    if 'last_detection' in live and not detection_ok(live['last_detection']):return False
    return live['enabled'] or (live['input_state']=='idle' and not live['mic_active'])
# A13 microphone assistant (src/mic_assist.rs): numbers, closed reason ids and device ids only; no audio.
REC_STATES=('idle','running','done','failed')
REC_PROBLEMS=('clipping','rumble','too_noisy','too_quiet')
REC_REASONS=REC_PROBLEMS+('best',)
REC_ERRORS=('recorder_unavailable','recorder_exited','sandbox_unavailable','invalid_device','audio_tool_failed','no_audio_tool')
REC_ENTRY_BASE=frozenset({'id','label','camera','current','problems','score'})
REC_ENTRY_KEYS=REC_ENTRY_BASE|frozenset({'reason','rms_dbfs','peak_dbfs','floor_dbfs','clip','rumble','speech','error'})
def rec_entry_ok(item):
    if not isinstance(item,dict) or not REC_ENTRY_BASE<=set(item)<=REC_ENTRY_KEYS:return False
    if not audio_device_ok(item['id']) or not isinstance(item['label'],str) or not 1<=len(item['label'].encode('utf-8'))<=128:return False
    if type(item['camera']) is not bool or type(item['current']) is not bool:return False
    if not isinstance(item['problems'],list) or len(item['problems'])>len(REC_PROBLEMS) or any(p not in REC_PROBLEMS for p in item['problems']):return False
    if type(item['score']) not in (int,float) or not math.isfinite(item['score']) or not 0<=item['score']<=1:return False
    if not all(dbfs_ok(item[k]) for k in ('rms_dbfs','peak_dbfs','floor_dbfs') if k in item):return False
    if 'error' in item:return item['error'] in REC_ERRORS and 'reason' not in item and not item['problems'] and item['score']==0
    return item.get('reason')==(item['problems'][0] if item['problems'] else 'best') and item['reason'] in REC_REASONS
def recommendation_ok(rec):
    base={'state','ranked','recommended','current','current_is_bad','reason'}
    if not isinstance(rec,dict) or not base<=set(rec)<=base|{'error'} or rec['state'] not in REC_STATES:return False
    if ('error' in rec)!=(rec['state']=='failed') or ('error' in rec and rec['error'] not in REC_ERRORS):return False
    ranked=rec['ranked']
    if not isinstance(ranked,list) or len(ranked)>17 or not all(rec_entry_ok(i) for i in ranked):return False
    if rec['state']!='done' and (ranked or rec['recommended'] is not None or rec['current_is_bad'] is not None or rec['reason'] is not None):return False
    if rec['current'] is not None and not audio_device_ok(rec['current']):return False
    if rec['current_is_bad'] is not None and type(rec['current_is_bad']) is not bool:return False
    if rec['reason'] is not None and rec['reason'] not in REC_REASONS:return False
    if rec['current_is_bad'] is not None and rec['current_is_bad']!=(rec['reason']!='best'):return False
    # The top-level reason describes the current device's row, when that device was measured.
    own=next((i for i in ranked if i['current']),None)
    if rec['state']=='done' and own is not None and 'error' not in own and (own['id']!=rec['current'] or rec['reason']!=own['reason'] or rec['current_is_bad']!=(own['reason']!='best')):return False
    # A recommendation is a clean, measured, non-camera device; it is never the 'default' pseudo entry.
    clean={i['id'] for i in ranked if 'error' not in i and not i['problems'] and not i['camera'] and i['id']!='default'}
    return rec['recommended'] is None or rec['recommended'] in clean
def audio_ok(audio):return isinstance(audio,dict) and set(audio)<={'devices','live','probe','recommendation'} and 'live' in audio and audio_live_ok(audio['live']) and ('devices' not in audio or audio_devices_ok(audio['devices'])) and ('probe' not in audio or probe_ok(audio['probe'])) and ('recommendation' not in audio or recommendation_ok(audio['recommendation']))
REC_PROBLEM_TEXT={'rumble':'capta quase só ruído grave','clipping':'satura','too_noisy':'tem muito ruído de fundo','too_quiet':'capta sinal muito fraco'}
REC_ERROR_TEXT={'recorder_unavailable':'o gravador de áudio não está instalado','recorder_exited':'o gravador parou antes de gravar','sandbox_unavailable':'o isolamento do gravador (bwrap) não está disponível','invalid_device':'dispositivo inválido','audio_tool_failed':'a ferramenta de áudio falhou','no_audio_tool':'nenhuma ferramenta de áudio encontrada'}
def recommendation_banner(rec,saved_device,default_device=None):
    """Dispositivos banner (A13): only when the saved input (default included) measured bad and a clean alternative exists.
    `default_device` is the id the system marks as default, when the saved choice is 'default'. None means no banner."""
    if not isinstance(rec,dict) or rec.get('state')!='done' or rec.get('current_is_bad') is not True:return None
    resolved=default_device if saved_device==DEFAULT_DEVICE else saved_device
    if rec.get('current')!=resolved or not rec.get('recommended'):return None
    current=next((i for i in rec['ranked'] if i['id']==rec['current']),None)
    best=next((i for i in rec['ranked'] if i['id']==rec['recommended']),None)
    if current is None or best is None or not current['problems']:return None
    problems=' e '.join(REC_PROBLEM_TEXT[p] for p in current['problems'])
    return {'device':best['id'],'text':f"O microfone atual ({current['label']}) {problems}. O melhor encontrado é {best['label']}.",'action':f"Usar o {best['label']}"}
def recommendation_view(rec):
    """Plain dict for QML: state, progress-free ranking rows with their Portuguese problem names, and the recommended id."""
    rec=rec if isinstance(rec,dict) else {'state':'idle','ranked':[],'recommended':None,'current':None,'current_is_bad':None,'reason':None}
    rows=[{'id':i['id'],'label':i['label'],'camera':i['camera'],'current':i['current'],'error':i.get('error',''),'score':round(float(i['score']),3),'reason':i.get('reason',''),
           'problems':', '.join(REC_PROBLEM_TEXT[p] for p in i['problems']) if i['problems'] else ('' if 'error' in i else 'sem problemas'),
           'recommended':i['id']==rec.get('recommended')} for i in rec.get('ranked') or []]
    error=rec.get('error')
    return {'state':rec.get('state','idle'),'rows':rows,'recommended':rec.get('recommended') or '','current':rec.get('current') or '',
            'currentIsBad':rec.get('current_is_bad') is True,'reason':rec.get('reason') or '','error':REC_ERROR_TEXT.get(error,'') if error else ''}
# B16 texts (Portuguese only; no Core code reaches the screen). The default choice is the Core's 'default' preference.
DEFAULT_DEVICE='default'
DEFAULT_DEVICE_LABEL='Padrão do sistema'
DEFAULT_MARK=' · padrão do sistema'
UNAVAILABLE_DEVICE_LABEL='Dispositivo salvo · indisponível agora'
AUDIO_REASON_MESSAGES={'no_audio_tool':'Nenhuma ferramenta de áudio encontrada: instale pipewire-pulse/pactl','audio_tool_failed':'A ferramenta de áudio falhou ao listar dispositivos; tente Atualizar lista'}
AUDIO_SOURCE_LABELS={'pactl':'PipeWire/Pulse (pactl)','pw-dump':'PipeWire (pw-dump)'}
LIVE_ERROR_MESSAGES={'recorder_unavailable':'gravador de áudio indisponível (instale pipewire-pulse)','recorder_exited':'o gravador de áudio parou','sandbox_unavailable':'isolamento do gravador indisponível (bwrap ausente)','wake_worker_unavailable':'worker de wake indisponível','wake_worker_failed':'worker de wake falhou','restart_limit':'limite de reinícios atingido','invalid_device':'dispositivo de entrada inválido','player_unavailable':'reprodutor de áudio indisponível','player_write_failed':'falha ao enviar áudio ao reprodutor','player_failed':'o reprodutor de áudio falhou','player_timeout':'o reprodutor de áudio não respondeu','worker_crashed':'o worker de wake parou com erro (veja o diagnóstico)','worker_import_error':'faltam bibliotecas do worker de wake (veja o diagnóstico)','device_unavailable':'o microfone escolhido não está disponível','model_missing':'arquivo do modelo de wake ausente ou alterado'}
RESTORE_BUSY_TEXT='Indisponível durante a sessão de voz; tente quando o Gideon estiver em espera'
RESTORE_BACKUP_TEXT='Padrões não restaurados: não foi possível gravar a cópia config.json.bak nem trocar a configuração; os valores atuais continuam'
SENSITIVITY_RANGE_TEXT='Sensibilidade fora de 0,5 a 1,5; nada foi enviado'
DEVICE_INVALID_TEXT='Dispositivo inválido; nada foi enviado'
# Choices for one Select: "Padrão do sistema", the listed devices (default one marked), and the saved name when the Core no longer lists it.
def device_choices(devices,direction,saved):
    rows=[{'value':DEFAULT_DEVICE,'text':DEFAULT_DEVICE_LABEL}]
    listed=(devices or {}).get(direction) or []
    for item in listed:rows.append({'value':item['id'],'text':item['label']+(DEFAULT_MARK if item['default'] else '')})
    known={item['id'] for item in listed}
    if saved!=DEFAULT_DEVICE and saved not in known:rows.append({'value':saved,'text':UNAVAILABLE_DEVICE_LABEL})
    return rows
# A6 state line of the microphone consent: desligado / aguardando reinício / ouvindo / erro: motivo (texts only; no Core code).
def live_state_text(live):
    if not live:return 'sem informação do Core'
    if live.get('restart_required') is True:return 'aguardando reinício do Core'
    if not live.get('enabled'):return 'desligado'
    if live.get('input_state')=='capturing':return 'ouvindo'
    if live.get('input_state')=='error':
        error=live.get('last_error') or ''
        return 'erro: '+(LIVE_ERROR_MESSAGES.get(error,'falha na captura') if not error.startswith('player_') else 'falha na captura')
    return 'em espera'
def live_input_text(live):return 'Escuta do microfone: '+live_state_text(live)
# A11 host actions (docs/A11-real-actions-test.md): consent switch, state line and the Core's last host action. The Core
# sends content-free fields only; every word the user reads here is set in this file.
REAL_KINDS=('open_app','volume','mute','unmute','volume_up','volume_down')
REAL_APPS=('brave','steam','kcalc')
REAL_KIND_TEXT={'open_app':'Abriu','volume':'Volume ajustado','mute':'Mudo ativado','unmute':'Som ativado','volume_up':'Volume aumentado','volume_down':'Volume diminuído'}
REAL_ACTION_MESSAGES={'consent_required':'Ações no computador não ativadas: a confirmação não chegou ao Core; nada foi alterado'}
# Outcome codes of a command that produced no receipt (src/host.rs and src/core.rs codes).
COMMAND_CODE_MESSAGES={'app_not_installed':'Aplicativo não instalado neste computador; nada foi aberto','launch_failed':'Não consegui iniciar o aplicativo; nada foi confirmado',
    'launch_unconfirmed':'Pedi para abrir, mas o aplicativo não apareceu em 5 s; nada foi confirmado','volume_unavailable':'Não consegui ler o volume do computador; nada foi alterado',
    'volume_unverified':'O volume lido não bate com o pedido; a mudança não foi confirmada','command_failed':'Comando não concluído; nada foi confirmado',
    'app_unavailable':'Aplicativo fora da lista fixa; nada foi aberto','denied':'Valor fora da faixa de 0 a 100%; nada foi alterado','unsupported':'Comando não entendido; nada foi executado'}
def valid_actions_block(block):
    """`actions`: {real: {enabled: bool, last_action: null | {kind, app, ok, verified, at_ms}}}. Strict; app is set only for open_app."""
    if not isinstance(block,dict) or set(block)!={'real'}:return False
    real=block['real']
    if not isinstance(real,dict) or set(real)!={'enabled','last_action'} or type(real['enabled']) is not bool:return False
    last=real['last_action']
    if last is None:return True
    if not isinstance(last,dict) or set(last)!={'kind','app','ok','verified','at_ms'}:return False
    if last['kind'] not in REAL_KINDS or (last['app'] is not None and last['app'] not in REAL_APPS):return False
    if (last['kind']=='open_app')!=(last['app'] is not None):return False
    if type(last['ok']) is not bool or type(last['verified']) is not bool or (last['verified'] and not last['ok']):return False
    return type(last['at_ms']) is int and 0<=last['at_ms']<=2**64-1
def real_action_line(last):
    """State line of the last host action: 'Abriu: brave às 14:32 · confirmado'. Local time, HH:MM."""
    if not isinstance(last,dict):return 'Nenhuma ação no computador desde o início do Core'
    when=datetime.datetime.fromtimestamp(last['at_ms']/1000).strftime('%H:%M')
    if not last['ok']:return f'Não concluiu às {when}; nada foi confirmado'
    label=REAL_KIND_TEXT[last['kind']]+(f": {last['app']}" if last['app'] else '')
    return f"{label} às {when} · {'confirmado' if last['verified'] else 'sem confirmação'}"
def real_actions_state(enabled,last):
    if enabled is not True:return 'Desligado: os comandos usam só a simulação interna, sem efeito no computador'
    return real_action_line(last)
def real_action_code_message(op,code):
    """Refusal text of the consent op; other ops and codes keep the shared table."""
    if op=='real_actions_preference' and code in REAL_ACTION_MESSAGES:return REAL_ACTION_MESSAGES[code]
    return code_message(code)
def live_output_text(live):
    if not live:return 'Saída ao vivo: sem informação do Core'
    if not live.get('enabled'):return 'Saída ao vivo: desligada — a resposta usa a saída virtual'
    if live.get('output_state')=='playing':return 'Saída ao vivo: reproduzindo'
    if live.get('output_state')=='error':
        error=live.get('last_error') or ''
        return 'Saída ao vivo: erro: '+(LIVE_ERROR_MESSAGES.get(error,'falha na reprodução') if error.startswith('player_') else 'falha na reprodução')
    return 'Saída ao vivo: em espera'
def devices_status(devices):
    """Why the device lists are empty or missing, in words; '' when the Core listed devices."""
    if devices is None:return 'Dispositivos ainda não consultados: use Atualizar lista'
    if devices['source']=='none':return AUDIO_REASON_MESSAGES.get(devices.get('reason'),AUDIO_REASON_MESSAGES['audio_tool_failed'])
    if not devices['inputs'] and not devices['outputs']:return 'Nenhum dispositivo de áudio listado por '+AUDIO_SOURCE_LABELS.get(devices['source'],devices['source'])
    return ''
# A9 texts (Portuguese only). Numbers are shown with a decimal comma; zones carry words as well as colour.
LIVE_WARNING_TEXTS={
    'no_frames':'Nenhum áudio chegando do microfone.',
    'very_quiet':'Sinal muito baixo: aproxime-se ou aumente o ganho do microfone no sistema.',
    'clipping':'O sinal está saturando (distorção): afaste-se do microfone ou reduza o ganho.',
}
PROBE_VERDICT_TEXTS={'ok':'Captando bem','quiet':'Sinal baixo','noisy':'Ruído alto','silent':'Silêncio','error':'Erro'}
PROBE_VERDICT_ZONES={'ok':'ok','quiet':'warn','noisy':'bad','silent':'bad','error':'bad'}
LEVEL_CALIBRATING_FRAMES=150
def db_text(value):return f'{value:.1f}'.replace('.',',')+' dBFS'
def very_noisy_text(floor):return f'Este microfone tem muito ruído de fundo ({round(floor)} dBFS). Teste outro dispositivo.'
def level_zone(rms):
    if rms>=-12:return 'hot'
    if rms<-60:return 'low'
    return 'ok'
def floor_zone(floor):
    if floor>-35:return 'bad'
    if floor>-45:return 'warn'
    return 'ok'
ZONE_TEXTS={'hot':'Sinal alto: risco de distorção','low':'Sinal baixo','ok':'Sinal normal'}
FLOOR_TEXTS={'bad':'ruído alto','warn':'ruído moderado','ok':'ruído baixo'}
def level_view(live,online=True):
    """Shape for the QML meter (audioLevel). Empty when the Core is offline or the recorder is not capturing."""
    level=(live or {}).get('level') if online else None
    capturing=bool(online and live and live.get('input_state')=='capturing' and live.get('level'))
    if not capturing or not level:
        return {'capturing':False,'rms':-90.0,'peak':-90.0,'floor':-90.0,'zone':'ok','zoneText':'','floorZone':'ok','floorText':'','speechActive':False,'unmatched':False,'calibrating':True,'frames':0,'warning':'','warningText':'','rmsText':'','peakText':'','floorLine':'Aguardando o microfone','ageMs':-1}
    warning=live.get('silence_warning') or ''
    floor=level['floor_dbfs']
    warning_text=LIVE_WARNING_TEXTS.get(warning,'')
    if warning=='very_noisy':warning_text=very_noisy_text(floor)
    return {'capturing':True,'rms':level['rms_dbfs'],'peak':level['peak_dbfs'],'floor':floor,'zone':level_zone(level['rms_dbfs']),'zoneText':ZONE_TEXTS[level_zone(level['rms_dbfs'])],
            'floorZone':floor_zone(floor),'floorText':FLOOR_TEXTS[floor_zone(floor)],'speechActive':level['speech_active'],'unmatched':level['speech_unmatched'],
            'calibrating':level['frames']<LEVEL_CALIBRATING_FRAMES,'frames':level['frames'],'warning':warning,'warningText':warning_text,
            'rmsText':db_text(level['rms_dbfs']),'peakText':db_text(level['peak_dbfs']),'floorLine':'Ruído de fundo: '+db_text(floor)+' ('+FLOOR_TEXTS[floor_zone(floor)]+')','ageMs':level['last_frame_age_ms'] if level['last_frame_age_ms'] is not None else -1}
def live_hint_view(live,online=True):
    """Hoje's state line while the microphone is on: listening, speech heard but not recognised (hint: say the phrase)."""
    if not online or not live or live.get('enabled') is not True or live.get('input_state')!='capturing':return {'line':'','hint':''}
    if (live.get('level') or {}).get('speech_unmatched') is True:return {'line':'Ouvindo… fala detectada mas nenhuma frase reconhecida','hint':'Diga: Hey Gideon'}
    return {'line':'Ouvindo…','hint':''}
def probe_view(probe):
    """Shape for the QML probe table (audioProbe): {} when no probe ran; numbers are None while running."""
    if not probe:return {}
    done=probe['state']=='done'
    return {'id':probe['id'],'device':probe['device'],'running':not done,'done':done,'verdict':probe.get('verdict') or '','verdictText':PROBE_VERDICT_TEXTS.get(probe.get('verdict'),''),
            'zone':PROBE_VERDICT_ZONES.get(probe.get('verdict'),'bad'),'hint':probe.get('hint') or '','rms':probe.get('rms_dbfs'),'peak':probe.get('peak_dbfs'),'floor':probe.get('floor_dbfs'),
            'frames':probe.get('frames',0),'reason':probe.get('reason') or ''}
PACK_KEYS=frozenset({'version','id','scope','preflight','engines','wake_phrases','active_phrase','default_phrase','voice','language','audio_input','audio_output','pack_sha256'})
TRANSCRIPT_KEYS=frozenset({'source','session_id','revision','audio_end_us','raw','normalized','is_final','confidence'})
CAPTURE_KEYS=frozenset({'session_id','start_us','end_us','samples','pcm_sha256','reason'})
SPEECH_KEYS=frozenset({'output_volume_percent','session_id','sample_rate','samples','chunks','pcm_sha256','peak','rms','first_pcm_ms','elapsed_ms','sink'})
COMMAND_KEYS=frozenset({'session_id','code','receipt'})
RECEIPT_KEYS=frozenset({'job','verified','scope','result'})
JOB_KEYS=frozenset({'session_id','command'})
# Snapshot events (src/core.rs emit_with, src/protocol.rs origin_of/outcome_of/code_outcome). Closed vocabularies; at_ms is Unix ms and never decreases.
EVENT_KEYS=frozenset({'sequence','at_ms','request_id','session_id','kind','origin','outcome'})
EVENT_ORIGINS=('core','plugin','hub','skill','connection','tool','agent','llm','speech','config','registry')
EVENT_OUTCOMES=('ok','pending','denied','failed','expired','cancelled')
# Registry tool proposals (src/tools.rs): risk class names, and the effect templates with their exact parameters.
TOOL_RISKS=('read','state_changing','destructive','public')
EFFECT_PARAMS={'open_app':('app',),'set_volume':('level',),'mute':(),'get_status':(),'get_time':(),'get_date':()}
APP_ID=re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,119}')
def utf8_len(text):return len(text.encode('utf-8'))
def digest(value):return isinstance(value,str) and len(value)==64 and all(c in HEX for c in value)
def text_problem(text):
    """Core rule for Operation::Text: non-blank, at most 512 UTF-8 bytes, no control characters."""
    try:
        if not isinstance(text,str) or not text.strip():return 'Texto vazio'
        if utf8_len(text)>TEXT_LIMIT:return 'Texto acima de 512 bytes'
        if any(unicodedata.category(c)=='Cc' for c in text):return 'Texto com quebra de linha ou controle não é aceito'
    except UnicodeError:return 'Texto inválido'
    return None
def bounded_output(value):
    """Core output contract: JSON object, at most 8 KiB of UTF-8 JSON, at most 4 container levels."""
    def shallow(item,depth=0):
        if isinstance(item,dict):return depth<4 and all(shallow(child,depth+1) for child in item.values())
        if isinstance(item,list):return depth<4 and all(shallow(child,depth+1) for child in item)
        return True
    try:return isinstance(value,dict) and shallow(value) and utf8_len(json.dumps(value,separators=(',',':'),ensure_ascii=False,allow_nan=False))<=OUTPUT_LIMIT
    except (TypeError,ValueError,RecursionError):return False
# C1 (docs/C1.md) contract: Core limits mirrored here so the UI refuses before a round trip.
LLM_PROVIDERS=('openrouter','opencode','google','anthropic','custom');LLM_SECRET_KEYS=frozenset(LLM_PROVIDERS)
# WP-18b: the Core-managed local llama-server state (llm.local_server); no other values exist.
LOCAL_SERVER_STATES=('stopped','running','unavailable')
# C2 (docs/C2.md): local providers take a loopback port and never need a key or cloud consent.
LOCAL_PROVIDERS=('local','ollama');CONFIG_PROVIDERS=LLM_PROVIDERS+LOCAL_PROVIDERS;FIXED_CLOUD_PROVIDERS=('openrouter','opencode','google','anthropic')
LOCAL_PORT_MIN,LOCAL_PORT_MAX=1024,65535
# The Core serializes config with local_port, fallback and lkg omitted when null (skip_serializing_if): they are optional keys.
LLM_CONFIG_REQUIRED=frozenset({'provider','model','custom_url','cloud_consent'});LLM_CONFIG_KEYS=LLM_CONFIG_REQUIRED|{'local_port','fallback','lkg'}
LKG_KEYS=frozenset({'provider','model','custom_url','local_port','cloud_consent'});LKG_REQUIRED=frozenset({'provider','model','custom_url','cloud_consent'})
FALLBACK_KEYS=frozenset({'provider','model','custom_url','local_port'})
LLM_URL_LIMIT=200
MODEL_ID=re.compile(r'[A-Za-z0-9._:/-]{1,128}');PROPOSAL_ID=re.compile(r'[A-Za-z0-9_]{1,64}')
TOOL_STATES=('pending','denied','authorized','executed','failed','expired','cancelled')
TOOL_KEYS=frozenset({'proposal_id','plugin_id','call_id','tool','args','state','reason','result'})
PARTIAL_LIMIT=16384;ARGS_LIMIT=8192;TOOL_NAME_LIMIT=256;RESULT_TEXT_LIMIT=1024;TOOL_ITEMS=8
CHAT_CAPABILITY_SUFFIX='.chat';CHAT_TEXT_LIMIT=4096;CHAT_CONTENT_LIMIT=4096;CHAT_INPUT_LIMIT=8192;CHAT_TURNS=31;CHAT_MAX_TOKENS=512;CHAT_DEADLINE_MS=10000;CHAT_MESSAGES_KEPT=64
HTTP_STATUS_KEY='http_status'
# C3 agent runtime (docs/C3.md). Limits and state sets mirror the Core; the codes are an explicit allowlist, anything else refuses the snapshot.
AGENT_STATES=('thinking','waiting_tool','awaiting_approval','done','failed','aborted','blocked');AGENT_TERMINAL=('done','failed','aborted','blocked');AGENT_ERROR_STATES=('failed','aborted','blocked')
AGENT_STEP_KINDS=('chat','tool');AGENT_RISKS=('read','state_changing','destructive');AGENT_STEP_STATES=('running','done','awaiting_approval','denied','failed','stale','blocked','cancelled','expired')
AGENT_CODES=frozenset({'agent_busy','llm_unavailable','unknown_run','invalid_input','invalid_args','unknown_tool','too_many_calls','executor_unavailable','executor_failed','busy','denied','destructive_disabled','app_unavailable','app_write_failed','verify_failed','stale_screen','loop_blocked','max_steps','token_budget','run_deadline','capability_unavailable','unknown_capability','plugin_error','invalid_output','empty_answer','aborted','revoked','cancelled','permission_denied','cloud_not_authorized','key_missing','provider_not_configured','http_error','timeout','response_too_large','network_unavailable','model_unsupported_feature','settings_unavailable',
 'permission_revoked','awaiting_approval','route_unavailable'})  # the last two are named by docs/C3.md (the Core emits them when that path exists)
# C3: a proposal cancelled or refused by an agent run carries the run's code (or run_ended), and synthetic tools refuse with their own codes.
TOOL_REASONS=TOOL_REASONS|AGENT_CODES|{'run_ended','denied','destructive_disabled','app_unavailable','app_write_failed','verify_failed','stale_screen','aborted','revoked'}
# S5 connections (docs/S5.md E1). Providers, statuses and limits mirror the Core; the snapshot block 'connections' is refused when it breaks them. No secret, token or endpoint is ever part of it.
CONN_PROVIDERS=('github','google','homeassistant','mcp');CONN_STATUSES=('disconnected','connecting','connected','expired','offline','error','reauth_required');CONN_ACCESS=('read','write','destructive','public')
CONN_ITEMS_LIMIT=8;CONN_SCOPES_LIMIT=8;CONN_OPERATIONS_LIMIT=16;CONN_ARGS_LIMIT=4096;CONN_LABEL_LIMIT=64;CONN_ACCOUNT_LIMIT=128;CONN_USER_CODE_LIMIT=32
CONN_ID=re.compile(r'[A-Za-z0-9_-]{1,64}');CONN_NAME=re.compile(r'[a-z][a-z0-9_.:]{0,63}')
CONN_BLOCK_KEYS=frozenset({'revision','items','providers','last_call','storage_error'});CONN_ITEM_REQUIRED=frozenset({'id','provider','label','status','granted_scopes'});CONN_ITEM_OPTIONAL=frozenset({'account_ref','pending_scopes','user_code','fake','tools','granted_at_ms'});CONN_TOOLS_LIMIT=16;CONN_TOOL_STATES=('trusted','needs_reapproval','rejected');CONN_TOOL_RISKS=('write','destructive');CONN_TOOL_DESCRIPTION_LIMIT=1024;CONN_TOOL_KEYS=frozenset({'name','risk','state','description'});CONN_TRUST_LIMIT=16
CONN_PROPOSAL_KEYS=frozenset({'kind','connection_id','operation','risk'})
# Core codes for connection ops and for connection proposals (kind 'connection'). Each one has a Portuguese text in CONN_MESSAGES.
CONN_MESSAGES={
    'scope_not_granted':'Escopo não concedido: conceda o escopo antes de usar esta operação; nenhuma chamada foi feita',
    'rate_limited':'Limite de chamadas do servidor atingido; tente de novo em instantes',
    'unauthorized':'Autorização recusada pelo servidor; reconecte a conta',
    'forbidden_scope':'O servidor recusou o escopo pedido para esta operação',
    'account_mismatch':'A conta devolvida pelo servidor não confere; chamada recusada',
    'provider_unreachable':'Servidor do provedor inacessível neste ambiente',
    'real_backend_unsupported':'Backend real não suportado neste ambiente; use o servidor falso',
    'reauth_required':'Reautenticação necessária: conecte a conta de novo',
    'public_pending':'Ação pública aguarda sua aprovação explícita; nada foi publicado',
    'provider_error':'O provedor devolveu erro; nada foi confirmado',
    'unknown_connection':'Conta desconhecida ou já removida',
    'stale_connection_revision':'Contas mudaram no Core; atualize e tente de novo',
    'invalid_connection':'Dados da conta recusados pelo Core',
    'connection_limit':'Limite de 8 contas atingido; remova uma conta antes',
    'not_connected':'Conta não está conectada',
    'unknown_operation':'Operação desconhecida para este provedor',
    'connection_consent_required':'Escolha ao menos um escopo pedido para consentir',
    'connection_args_invalid':'Argumentos devem ser um objeto JSON de até 4 KiB',
    'connection_unavailable':'Conexões indisponíveis agora',
    'not_found':'Recurso não encontrado no servidor; nada foi alterado',
    'public_disabled':'Ação pública ou destrutiva desativada nesta build; nada foi executado',
    'scope_not_requested':'Escopo não pedido pelo dispositivo; nada foi concedido',
    'device_expired':'Código de confirmação expirou; conecte a conta de novo',
    'consent_denied':'Consentimento recusado no servidor; nada foi concedido',
    'connections_storage_error':'Contas indisponíveis: o arquivo de contas não pôde ser lido ou gravado',
    'consent_required':'Consinta os escopos antes de enviar o token; nada foi enviado ao servidor',
    'invalid_token':'Token inválido: use o token de longa duração do Home Assistant (16 a 256 caracteres, sem espaços)',
    'invalid_state':'Esta conta não está aguardando um token agora',
    'tool_trust_invalid':'Escolha ao menos uma ferramenta que aguarda sua confiança',
    'tool_not_trusted':'Ferramenta nova ou alterada: confie nela na página Conexões antes de chamar; nada foi executado',
    'tool_not_verified':'Servidor MCP reconectado ou reiniciado: liste as ferramentas de novo antes de chamar; nada foi executado',
    'tool_rejected':'Ferramenta recusada pelo Core (esquema fora do subconjunto simples ou grande demais); nada foi executado',
    'mcp_not_running':'Servidor MCP não está rodando; conecte a conta de novo',
    'mcp_crashed':'Servidor MCP parou de responder; a conta ficou com erro e o Core segue normal',
    'mcp_protocol':'Servidor MCP respondeu fora do protocolo; a conta ficou com erro',
    'mcp_too_large':'Servidor MCP enviou linha grande demais; a conta ficou com erro',
    'mcp_start_failed':'Servidor MCP não iniciou no sandbox',
    'mcp_tool_error':'A ferramenta MCP devolveu erro; nada foi confirmado',
    'mcp_rpc_error':'O servidor MCP recusou a chamada; nada foi confirmado',
    'mcp_too_many_tools':'Servidor MCP listou ferramentas demais (máximo 16); lista anterior mantida',
    'mcp_restart_limit':'Limite de reinícios do servidor MCP atingido; reinicie o Core para tentar de novo',
}
CONN_CODES=frozenset(CONN_MESSAGES)
# A failed connection tool of an agent run (github_create_issue, route_create_issue, ...) ends its step, and the run, with the connection code (rate_limited, forbidden_scope, provider_error, ...).
AGENT_CODES=AGENT_CODES|CONN_CODES
# S5 E3 CapabilityRegistry (docs/S5.md E3). Purposes, routes and statuses mirror the Core's fixed table; the snapshot block 'registry' is refused when it breaks them.
REG_PURPOSES=('create_issue','list_events','read_state');REG_VISUAL_PURPOSES=('create_issue',);REG_ROUTES=('connection','visual')
REG_STATUSES=('available','not_connected','expired','scope_not_granted','no_api','visual_not_allowed','disabled')
REG_BLOCK_KEYS=frozenset({'revision','purposes','visual_allowed'});REG_CANDIDATE_KEYS=frozenset({'route','status','reason'});REG_LABEL_LIMIT=64;REG_REASON_LIMIT=256
REG_VISUAL_WARNING='Atenção: o fallback visual dirige uma tela por cliques e digitação, é menos seguro que a API e só vale quando não há conta conectada. Nunca contorna token expirado, reautenticação ou escopo negado. A publicação ainda pede sua aprovação.'
REG_MESSAGES={
    'route_unavailable':'Nenhuma rota disponível para esta finalidade; veja os motivos. Nada foi executado',
    'unknown_purpose':'Finalidade desconhecida',
    'no_visual_route':'Esta finalidade não tem rota visual',
    'stale_registry_revision':'As rotas mudaram no Core; atualize e tente de novo',
    'registry_storage_error':'Rotas indisponíveis: o arquivo de permissões não pôde ser lido ou gravado',
    'registry_unavailable':'Rotas indisponíveis agora',
    'registry_revision_exhausted':'Revisão das rotas esgotada',
}
TOOL_REASONS=TOOL_REASONS|CONN_CODES
AGENT_STATE_LABELS={'thinking':'Pensando','waiting_tool':'Executando ferramenta','awaiting_approval':'Aguardando sua aprovação','done':'Concluído','failed':'Falhou','aborted':'Abortado','blocked':'Bloqueado'}
AGENT_MAX_STEPS=6;AGENT_CHAT_STEPS=12;AGENT_TOOL_STEPS=25;AGENT_TOTAL_TOKENS=4096;AGENT_GOAL_LIMIT=1024;AGENT_ANSWER_LIMIT=4096
AGENT_RUN_KEYS=frozenset({'run_id','state','goal_len','step','max_steps','started_ms_ago','steps','budget'});AGENT_STEP_KEYS=frozenset({'n','invocation_id','kind','tool','risk','state','code'});AGENT_PROPOSAL_KEYS=frozenset({'run_id','step'})
def is_int(value,minimum=0,maximum=2**64-1):return type(value) is int and minimum<=value<=maximum
def run_id_ok(value):return isinstance(value,str) and 1<=len(value)<=64 and value.isascii() and value.isprintable()
def plain_text(value,limit):
    """Core-independent PlainText rule: a string of at most `limit` UTF-8 bytes with no control characters."""
    try:return isinstance(value,str) and utf8_len(value)<=limit and not any(unicodedata.category(c)=='Cc' for c in value)
    except UnicodeError:return False
def llm_url_ok(url):
    """https always; http only for loopback (the Core allows that only with its test flag). No userinfo, query or fragment."""
    if not isinstance(url,str) or utf8_len(url)>LLM_URL_LIMIT or not plain_text(url,LLM_URL_LIMIT) or url!=url.strip():return False
    try:parts=urlsplit(url);port=parts.port
    except ValueError:return False
    if parts.username or parts.password or parts.query or parts.fragment or not parts.hostname:return False
    if parts.scheme=='https':return True
    return parts.scheme=='http' and parts.hostname in ('127.0.0.1','localhost','::1')
def valid_key(key):
    """Core secret rule: 8..=256 printable ASCII bytes without spaces or controls."""
    return isinstance(key,str) and 8<=len(key)<=256 and all('!'<=c<='~' for c in key)
def llm_config_problem(provider,model,url,consent,port=None):
    """Client-side mirror of LlmConfig::validate; True means refuse. The port matters only for local providers (ignored elsewhere, as in the Core)."""
    if provider not in CONFIG_PROVIDERS or type(consent) is not bool or not isinstance(model,str) or not MODEL_ID.fullmatch(model):return True
    if provider=='custom':return not llm_url_ok(url)
    if provider in LOCAL_PROVIDERS:return url is not None or not is_int(port,LOCAL_PORT_MIN,LOCAL_PORT_MAX)
    return url is not None
def target_problem(target,keys,required):
    """A last-known-good or fallback target: exact keys, then the same rules as the live config. True means refuse."""
    if not (isinstance(target,dict) and required<=set(target)<=keys):return True
    return llm_config_problem(target['provider'],target['model'],target.get('custom_url'),target.get('cloud_consent',False),target.get('local_port'))
def valid_llm(llm):
    if not (isinstance(llm,dict) and {'revision','config','secrets'}<=set(llm)<={'revision','config','secrets','last_chat','local_server'} and is_int(llm['revision'])):return False
    if llm.get('local_server',LOCAL_SERVER_STATES[0]) not in LOCAL_SERVER_STATES:return False
    # NF-10: last_chat is absent until a chat answered; then only the fallback flag and its time (no content).
    last=llm.get('last_chat')
    if last is not None and not (isinstance(last,dict) and set(last)=={'used_fallback','at_ms'} and type(last['used_fallback']) is bool and is_int(last['at_ms'],1)):return False
    secrets=llm['secrets']
    if not (isinstance(secrets,dict) and set(secrets)==LLM_SECRET_KEYS and all(type(v) is bool for v in secrets.values())):return False
    config=llm['config']
    if config is None:return True
    if not (isinstance(config,dict) and LLM_CONFIG_REQUIRED<=set(config)<=LLM_CONFIG_KEYS):return False
    if llm_config_problem(config['provider'],config['model'],config['custom_url'],config['cloud_consent'],config.get('local_port')):return False
    if config.get('local_port') is not None and not is_int(config['local_port'],1,LOCAL_PORT_MAX):return False
    if config.get('lkg') is not None and target_problem(config['lkg'],LKG_KEYS,LKG_REQUIRED):return False
    if config.get('fallback') is not None and target_problem(config['fallback'],FALLBACK_KEYS,{'provider','model'}):return False
    return True
# C2 model manager (docs/C2.md). The plugin owns the catalog; these rules only refuse what the schema forbids.
MODEL_CAPABILITY='llm_engine.models';MODEL_PLUGIN='llm_engine';MODELS_LIMIT=16;MODEL_TABS=('recommended','custom');MODELS_PAGE=6;MODEL_TOKEN=re.compile(r'[A-Za-z0-9._:/-]{1,64}')
MODEL_KEYS=frozenset({'id','label','kind','provider','model','tier','license','quantization','sha256','backend','features','certification','cost','latency_hint','min_hardware','offline','custom_url','local_port'})
FEATURE_KEYS=('streaming','tool_use','vision','cancel');FEATURE_STATES=('supported','unsupported','unknown');CERT_STATES=('certified','candidate','declared','probed')
CERT_BADGES={'certified':'Certificado','candidate':'Candidato','declared':'Declarado','probed':'Testado'}
FEATURE_LABELS={'supported':'Suportado','unsupported':'Não suportado','unknown':'Desconhecido'}
SELFTEST_DEADLINE_MS=30000;MODELS_DEADLINE_MS=5000
PENDING_MODELS={'list':'Carregando modelos…','selftest':'Testando modelo…','manual_selftest':'Testando modelo…','save_custom':'Salvando modelo personalizado…','delete_custom':'Removendo modelo personalizado…'}
# Core restart (Diagnóstico > Recuperação): the Core exits 75 after acking; gideon-launch starts it again. The bridge waits this long for the snapshot.
RESTART_TIMEOUT_MS=30000;RESTART_WAIT_TEXT='Reiniciando o Core…';RESTART_BACK_TEXT='Core reiniciado e conectado de novo';RESTART_TIMEOUT_TEXT='O Core não voltou em 30 s; use gideon-launch'
FALLBACK_NOTICE_MS=60000
def finite_number(value,limit):return value is None or (type(value) in (int,float) and math.isfinite(value) and 0<=value<=limit)
def feature_ok(features):
    if not (isinstance(features,dict) and set(features)==set(FEATURE_KEYS)|{'context_tokens'}):return False
    return all(features[k] in FEATURE_STATES for k in FEATURE_KEYS) and (features['context_tokens'] is None or is_int(features['context_tokens'],1,2**31-1))
def date_ok(value):
    if value is None:return True
    if not (isinstance(value,str) and len(value)==10):return False
    try:datetime.date.fromisoformat(value);return True
    except ValueError:return False
def text_ok(value,limit):return isinstance(value,str) and bool(value.strip()) and plain_text(value,limit)
def valid_model(model,tier):
    """Model schema (docs/C2.md): exact keys, enums, bounds, endpoint per provider; certified needs evidence; cost only when known."""
    if not (isinstance(model,dict) and set(model)==MODEL_KEYS and model['tier']==tier):return False
    kind,provider=model['kind'],model['provider']
    if not (isinstance(model['id'],str) and MODEL_TOKEN.fullmatch(model['id']) and text_ok(model['label'],128)):return False
    if kind not in ('local','cloud') or provider not in CONFIG_PROVIDERS:return False
    if (provider in LOCAL_PROVIDERS and kind!='local') or (provider in FIXED_CLOUD_PROVIDERS and kind!='cloud'):return False
    if not (isinstance(model['model'],str) and MODEL_ID.fullmatch(model['model'])):return False
    if not (text_ok(model['license'],64) and (model['quantization'] is None or text_ok(model['quantization'],32)) and (model['sha256'] is None or digest(model['sha256'])) and text_ok(model['backend'],64)):return False
    if not feature_ok(model['features']):return False
    cert=model['certification']
    if not (isinstance(cert,dict) and set(cert)=={'state','evidence','date'} and cert['state'] in CERT_STATES):return False
    if cert['evidence'] is not None and not text_ok(cert['evidence'],256):return False
    if cert['state']=='certified' and not text_ok(cert['evidence'],256):return False
    if not date_ok(cert['date']):return False
    cost=model['cost']
    if not (isinstance(cost,dict) and set(cost)=={'input_per_mtok','output_per_mtok','currency'}):return False
    if not (finite_number(cost['input_per_mtok'],1e6) and finite_number(cost['output_per_mtok'],1e6) and cost['currency'] in (None,'USD')):return False
    if (cost['currency']=='USD')!=(cost['input_per_mtok'] is not None or cost['output_per_mtok'] is not None):return False
    hw=model['min_hardware']
    if not (isinstance(hw,dict) and set(hw)=={'ram_gb','gpu'} and finite_number(hw['ram_gb'],4096) and hw['gpu'] in ('none','optional','required','unknown')):return False
    if model['latency_hint'] not in ('low','medium','high','unknown') or type(model['offline']) is not bool:return False
    if provider in LOCAL_PROVIDERS:return model['custom_url'] is None and is_int(model['local_port'],LOCAL_PORT_MIN,LOCAL_PORT_MAX)
    if provider=='custom':return llm_url_ok(model['custom_url']) and model['local_port'] is None
    return model['custom_url'] is None and model['local_port'] is None
def fresh_model_pages():
    """Paging state per tab: total unknown until the first page, next = offset where the next page starts."""
    return {tab:{'total':None,'next':0} for tab in MODEL_TABS}
def valid_models_page(output,tab,offset):
    """Output of action list (paginated, docs/C2.md): exact keys, the requested tab and offset echoed back, at most MODELS_PAGE full Models of that tab with unique ids, total bounded, a page consistent with offset and total, bounded like every capability output (8 KiB). A page may be shorter than MODELS_PAGE (the plugin cuts it to fit 8 KiB); an offset at or past total gives no items."""
    if not (isinstance(output,dict) and set(output)=={'tab','items','total','offset','selected','hardware'}):return False
    if tab not in MODEL_TABS or output['tab']!=tab or not is_int(offset,0,2**31-1) or output['offset']!=offset:return False
    items,total=output['items'],output['total']
    if not (isinstance(items,list) and len(items)<=MODELS_PAGE and is_int(total,0,MODELS_LIMIT)):return False
    if not all(valid_model(m,tab) for m in items):return False
    ids=[m['id'] for m in items]
    if len(set(ids))!=len(ids):return False
    if offset>=total:
        if items:return False
    elif not items or offset+len(items)>total:return False
    selected=output['selected']
    if selected is not None and not (isinstance(selected,dict) and set(selected)=={'provider','model'} and selected['provider'] in CONFIG_PROVIDERS and isinstance(selected['model'],str) and MODEL_ID.fullmatch(selected['model'])):return False
    hw=output['hardware']
    if not (isinstance(hw,dict) and set(hw)=={'cpu_cores','ram_gb','gpu'} and is_int(hw['cpu_cores'],1,4096) and finite_number(hw['ram_gb'],65536) and hw['gpu']=='unknown'):return False
    return bounded_output(output)
def valid_describe(output):
    """Answer of llm_describe (WP-19): exactly {'model': one Model of its own tier}, checked by the Model schema."""
    if not (isinstance(output,dict) and set(output)=={'model'}):return False
    model=output['model']
    return isinstance(model,dict) and model.get('tier') in MODEL_TABS and valid_model(model,model['tier'])
def valid_selftest(output):
    """Result of action selftest: a probe that passed. Vision is never probed, so it stays unknown."""
    return isinstance(output,dict) and set(output)=={'ok','latency_ms','features','source'} and output['ok'] is True and is_int(output['latency_ms'],0,600000) and output['source']=='probed' and feature_ok(output['features']) and output['features']['vision']=='unknown' and bounded_output(output)
def normal_form(form):
    """QML numbers arrive as doubles; integral values become ints before any rule runs."""
    if not isinstance(form,dict):return None
    out=dict(form)
    if type(out.get('local_port')) is float and out['local_port'].is_integer():out['local_port']=int(out['local_port'])
    return out
def custom_form_problem(form):
    """Rule for 'Adicionar modelo personalizado'; None means the form may be saved. Mirrors valid_model."""
    form=normal_form(form)
    if form is None:return 'Formulário inválido'
    provider,model,url,port,features=form.get('provider'),form.get('model'),form.get('custom_url') or '',form.get('local_port'),form.get('features')
    if provider not in CONFIG_PROVIDERS:return 'Escolha o provedor'
    if not (isinstance(model,str) and MODEL_ID.fullmatch(model)):return 'Identificador: letras ASCII, números e . _ : / - (1 a 128 caracteres)'
    if not isinstance(url,str):return 'URL inválida'
    if provider in LOCAL_PROVIDERS:
        if not is_int(port,LOCAL_PORT_MIN,LOCAL_PORT_MAX):return 'Porta local: 1024 a 65535'
        if url:return 'Provedor local não usa URL'
    elif provider=='custom':
        if not (url.startswith('https://') and llm_url_ok(url)):return 'URL: somente https, sem usuário, query ou fragmento (até 200 bytes)'
        if port is not None:return 'Provedor personalizado não usa porta local'
    elif url or port is not None:return 'Provedor na nuvem não usa URL nem porta'
    if not (isinstance(features,dict) and set(features)==set(FEATURE_KEYS) and all(features[k] in FEATURE_STATES for k in FEATURE_KEYS)):return 'Recursos declarados inválidos'
    return None
def custom_model(form):
    """Model saved through save_custom: declared only, never certified, endpoint kept per provider."""
    form=normal_form(form);provider,model=form['provider'],form['model'];local=provider in LOCAL_PROVIDERS
    ident='custom-'+hashlib.sha256(f'{provider}:{model}'.encode('utf-8')).hexdigest()[:24]
    return {'id':ident,'label':model,'kind':'local' if local else 'cloud','provider':provider,'model':model,'tier':'custom',
            'license':'Não informada','quantization':None,'sha256':None,'backend':{'local':'llama.cpp','ollama':'ollama'}.get(provider,'OpenAI-compatível'),
            'features':{**{k:form['features'][k] for k in FEATURE_KEYS},'context_tokens':None},'certification':{'state':'declared','evidence':None,'date':None},
            'cost':{'input_per_mtok':None,'output_per_mtok':None,'currency':None},'latency_hint':'unknown','min_hardware':{'ram_gb':None,'gpu':'unknown'},'offline':local,
            'custom_url':(form.get('custom_url') or None) if provider=='custom' else None,'local_port':form.get('local_port') if local else None}
def target_for(model,consent):
    """The configuration a model becomes; local_port is sent only for local providers, as the Core ignores it elsewhere."""
    target={'provider':model['provider'],'model':model['model'],'custom_url':model['custom_url'],'cloud_consent':consent}
    if model['provider'] in LOCAL_PROVIDERS:target['local_port']=model['local_port']
    return target
def fallback_for(model):
    target={'provider':model['provider'],'model':model['model']}
    if model['provider']=='custom':target['custom_url']=model['custom_url']
    if model['provider'] in LOCAL_PROVIDERS:target['local_port']=model['local_port']
    return target
def model_status(config,models,secrets,testing=False):
    """Status of the current model: Em teste | Sem chave | Sem consentimento | INDISPONÍVEL: recurso não suportado | Disponível."""
    if testing:return 'Em teste'
    if config is None:return 'Sem modelo selecionado'
    provider=config['provider']
    if provider in LLM_PROVIDERS and secrets.get(provider) is not True:return 'Sem chave'
    if provider in LLM_PROVIDERS and config.get('cloud_consent') is not True:return 'Sem consentimento'
    model=next((m for m in models if m['provider']==provider and m['model']==config['model'] and m['custom_url']==config.get('custom_url') and m['local_port']==config.get('local_port')),None)
    if model is None:return 'Sem dados do modelo'
    if model['features']['tool_use']=='unsupported':return 'INDISPONÍVEL: tool_use não suportado'
    return 'Disponível'
def bounded_json(value,limit):
    """Any JSON value: at most 4 container levels and `limit` bytes of UTF-8 JSON."""
    def shallow(item,depth=0):
        if isinstance(item,(dict,list)):
            return depth<4 and all(shallow(child,depth+1) for child in (item.values() if isinstance(item,dict) else item))
        return True
    try:return shallow(value) and utf8_len(json.dumps(value,separators=(',',':'),ensure_ascii=False,allow_nan=False))<=limit
    except (TypeError,ValueError,RecursionError,UnicodeError):return False
def valid_args(args):
    """Core stores the model's arguments as found (null when the call is malformed), so any JSON value fits here."""
    return bounded_json(args,ARGS_LIMIT)
def valid_tools(items):
    """Core proposal view: at most eight items (src/tools.rs: HISTORY_LIMIT 8 bounds pending plus history), exact keys (plus the C3 run_id/step pair), PlainText strings, bounded args."""
    if not (isinstance(items,list) and len(items)<=TOOL_ITEMS):return False
    ids=set()
    for item in items:
        if not (isinstance(item,dict) and TOOL_KEYS<=set(item)<=TOOL_KEYS|AGENT_PROPOSAL_KEYS|CONN_PROPOSAL_KEYS|{'effect'}):return False
        pid=item['proposal_id']
        if not (isinstance(pid,str) and PROPOSAL_ID.fullmatch(pid) and pid not in ids):return False
        ids.add(pid)
        if not (isinstance(item['plugin_id'],str) and PLUGIN_ID.fullmatch(item['plugin_id'])):return False
        # Model text: the Core caps call_id at 64 bytes and the tool name at 64 characters (<= 256 UTF-8 bytes). QML shows it as PlainText.
        if not (isinstance(item['call_id'],str) and utf8_len(item['call_id'])<=64 and isinstance(item['tool'],str) and utf8_len(item['tool'])<=TOOL_NAME_LIMIT):return False
        if not valid_args(item['args']) or item['state'] not in TOOL_STATES:return False
        reason=item['reason']
        if reason is not None and reason not in TOOL_REASONS:return False
        if item['result'] is not None and not (isinstance(item['result'],str) and utf8_len(item['result'])<=RESULT_TEXT_LIMIT):return False
        # C3: a proposal made by an agent run carries its run_id and step together; a chat or tool-only proposal carries neither.
        if ('run_id' in item)!=('step' in item):return False
        if 'run_id' in item and not (run_id_ok(item['run_id']) and is_int(item['step'],1,AGENT_MAX_STEPS)):return False
        if not valid_conn_proposal(item):return False
    return True
def valid_conn_proposal(item):
    """S5 (docs/S5.md E1): kind 'connection' carries connection_id, operation and risk, never an agent run or effect. Other proposals carry no connection fields; a registry tool may carry risk (TOOL_RISKS) and effect (closed template)."""
    if 'kind' in item and item['kind'] not in ('tool','connection'):return False
    if item.get('kind')!='connection':
        if set(item)&{'connection_id','operation'}:return False
        if 'risk' in item and item['risk'] not in TOOL_RISKS:return False
        return 'effect' not in item or valid_effect(item['effect'])
    return {'connection_id','operation','risk'}<=set(item) and 'effect' not in item and conn_id_ok(item['connection_id']) and isinstance(item['operation'],str) and CONN_NAME.fullmatch(item['operation']) is not None and item['risk'] in CONN_ACCESS
def valid_effect(effect):
    """Registry effect (src/tools.rs Effect): a known template id, exactly its own parameters, bounded values. Never free text."""
    if not (isinstance(effect,dict) and effect.get('id') in EFFECT_PARAMS and set(effect)=={'id',*EFFECT_PARAMS[effect['id']]}):return False
    if 'app' in effect and not (isinstance(effect['app'],str) and APP_ID.fullmatch(effect['app'])):return False
    return 'level' not in effect or is_int(effect['level'],0,100)
def agent_goal_problem(goal):
    """Rule for agentStart (docs/C3.md): trimmed, 1..=1024 UTF-8 bytes, no control characters. None means the goal may be sent (the trimmed text)."""
    try:
        if not isinstance(goal,str) or not goal.strip():return 'Objetivo vazio'
        text=goal.strip()
        if utf8_len(text)>AGENT_GOAL_LIMIT:return 'Objetivo acima de 1024 bytes'
        if any(unicodedata.category(c)=='Cc' for c in text):return 'Objetivo com quebra de linha ou controle não é aceito'
    except UnicodeError:return 'Objetivo inválido'
    return None
def agent_text_ok(text):
    """Answer rule: a PlainText string; newlines and tabs are part of a model answer, other control characters are not."""
    try:return isinstance(text,str) and not any(unicodedata.category(c)=='Cc' and c not in '\n\t' for c in text)
    except UnicodeError:return False
def valid_agent_step(step):
    """One entry of agent.steps: exact keys; chat steps carry no tool or risk; tool steps may. Codes come from AGENT_CODES only."""
    if not (isinstance(step,dict) and {'n','invocation_id','kind','state'}<=set(step)<=AGENT_STEP_KEYS):return False
    if not (is_int(step['n'],1,AGENT_MAX_STEPS) and is_int(step['invocation_id']) and step['kind'] in AGENT_STEP_KINDS and step['state'] in AGENT_STEP_STATES):return False
    if step['kind']=='chat':
        if 'tool' in step or 'risk' in step:return False
    else:
        if 'tool' in step and not (isinstance(step['tool'],str) and step['tool'] and utf8_len(step['tool'])<=TOOL_NAME_LIMIT and plain_text(step['tool'],TOOL_NAME_LIMIT)):return False
        if 'risk' in step and step['risk'] not in AGENT_RISKS:return False
    return 'code' not in step or step['code'] in AGENT_CODES
def valid_agent(agent):
    """Snapshot block agent (docs/C3.md): null, or the run view with exact keys, bounded steps, answer only when done, error from AGENT_CODES, budget within the Core total."""
    if agent is None:return True
    if not (isinstance(agent,dict) and AGENT_RUN_KEYS<=set(agent)<=AGENT_RUN_KEYS|{'answer','error','elapsed_ms','max_run_ms'}):return False
    if not (run_id_ok(agent['run_id']) and agent['state'] in AGENT_STATES and is_int(agent['goal_len'],1,AGENT_GOAL_LIMIT)):return False
    if not (is_int(agent['step'],0,AGENT_MAX_STEPS) and agent['max_steps']==AGENT_MAX_STEPS and is_int(agent['started_ms_ago'])):return False
    # Budget clocks (C3): optional so older snapshots still validate; typed when present.
    if 'elapsed_ms' in agent and not is_int(agent['elapsed_ms']):return False
    if 'max_run_ms' in agent and not is_int(agent['max_run_ms'],1):return False
    steps=agent['steps']
    if not (isinstance(steps,list) and len(steps)<=AGENT_CHAT_STEPS+AGENT_TOOL_STEPS):return False
    kinds=[step.get('kind') if isinstance(step,dict) else None for step in steps]
    if kinds.count('chat')>AGENT_CHAT_STEPS or kinds.count('tool')>AGENT_TOOL_STEPS or not all(valid_agent_step(step) for step in steps):return False
    budget=agent['budget']
    if not (isinstance(budget,dict) and set(budget)=={'tokens_used','tokens_max'} and budget['tokens_max']==AGENT_TOTAL_TOKENS and is_int(budget['tokens_used'],0,AGENT_TOTAL_TOKENS)):return False
    if 'answer' in agent and not (agent['state']=='done' and agent_text_ok(agent['answer']) and utf8_len(agent['answer'])<=AGENT_ANSWER_LIMIT):return False
    if 'error' in agent and not (agent['state'] in AGENT_ERROR_STATES and agent['error'] in AGENT_CODES):return False
    return True
def chat_problem(text):
    """UI rule for a chat turn: non-blank, at most 4096 UTF-8 bytes, single line, no control characters."""
    try:
        if not isinstance(text,str) or not text.strip():return 'Mensagem vazia'
        if utf8_len(text)>CHAT_TEXT_LIMIT:return 'Mensagem acima de 4096 bytes'
        if any(unicodedata.category(c)=='Cc' for c in text):return 'Mensagem com quebra de linha ou controle não é aceita'
    except UnicodeError:return 'Mensagem inválida'
    return None
def chat_input_size(messages):
    return utf8_len(json.dumps({'messages':messages,'tools':True,'max_tokens':CHAT_MAX_TOKENS},separators=(',',':'),ensure_ascii=False))
def chat_messages_for(history,text):
    """Newest completed turns (at most 31) plus the new user turn, oldest turns dropped until the 8 KiB input fits.
    Returns None when the new turn alone cannot fit."""
    turns=[{'role':m['role'],'content':m['text']} for m in history if m['state']=='done' and m['text'] and len(m['text'])<=CHAT_CONTENT_LIMIT][-CHAT_TURNS:]
    while True:
        messages=turns+[{'role':'user','content':text}]
        if chat_input_size(messages)<=CHAT_INPUT_LIMIT:return messages
        if not turns:return None
        turns=turns[1:]


# C4 perception and action plugins (docs/C4.md). The allowlist is the only capability set perceptionInvoke may send. Shapes below are the
# C4 contract (docs/C4.md): each rule matches the real output of its plugin, captured from the real Core by test_snapshot_contract.py (test_c4_plugin_outputs_validate_against_real_core).
PERCEPTION_PLUGINS=('screen_observe','computer_control','audio_advanced','mic_advanced','camera_gesture','display_manipulate','shortcut_global')
PERCEPTION_NO_INPUT=frozenset({'screen_observe.capture','screen_observe.status','computer_control.tree','computer_control.status','audio_advanced.state','mic_advanced.state','camera_gesture.state','camera_gesture.capture','camera_gesture.gestures','display_manipulate.status','display_manipulate.restore','shortcut_global.status','shortcut_global.events'})
PERCEPTION_CAPABILITIES=PERCEPTION_NO_INPUT|frozenset({'computer_control.act','audio_advanced.act','mic_advanced.configure','mic_advanced.monitor','mic_advanced.record','camera_gesture.optin','display_manipulate.act','shortcut_global.bind'})
PERCEPTION_INPUT_LIMIT=8192;PERCEPTION_DEADLINE_MS=5000;PERCEPTION_GESTURES=16;PERCEPTION_ELEMENTS=64
# WP-17: per-capability deadlines (ms). The Core accepts up to 60 s only for computer_control.act (portal consent).
PERCEPTION_DEADLINES={'computer_control.act':60000,'screen_observe.capture':30000}
PERCEPTION_STATUS_CAPABILITIES=('screen_observe.status','camera_gesture.state')
def perception_deadline(capability):return PERCEPTION_DEADLINES.get(capability,PERCEPTION_DEADLINE_MS)
PERCEPTION_LABELS={'backend':'backend','real_backend':'backend real','reason':'motivo','epoch':'época','width':'largura','height':'altura','sha256':'SHA-256','regions':'regiões','elements':'elementos','kind':'ação','verified':'verificado','routes':'rotas','apps':'apps','eq':'EQ','denoise':'redução de ruído','device':'dispositivo','gain':'ganho','filter':'filtro','monitor':'monitor','recording':'gravando','indicator':'indicador','opt_in':'opt-in','frame_seq':'quadro','gesture':'gesto','gestures':'gestos','supported':'suportado','state':'estado','note':'nota','volume':'volume','id':'id','role':'papel','name':'nome','x':'x','y':'y'}
PERCEPTION_VALUES={'portal':'portal XDG','atspi':'AT-SPI','remote_desktop':'RemoteDesktop','pipewire':'PipeWire','v4l2':'câmera (v4l2)','kscreen':'KScreen (Plasma)','kglobalaccel':'KGlobalAccel','ok':'ok','portal_missing':'portal ausente nesta sessão','pygobject_missing':'PyGObject ausente no Python do sistema','no_active_window':'nenhuma janela ativa','no_gesture_model_installed':'nenhum modelo de gesto instalado','monitor_would_feed_back_to_speakers':'monitoração recusada: realimentação nos alto-falantes','on':'ligado','off':'desligado','scale':'escala','brightness':'brilho','route':'rota de saída','app_volume':'volume do stream','key':'tecla','type':'texto','start':'iniciar','stop':'parar','synthetic':'sintético','unsupported':'não suportado','needs_human_validation':'pendente de validação humana','UNSUPPORTED':'UNSUPPORTED'}
PERCEPTION_MESSAGES={'permission_denied':'Permissão negada: o plugin precisa da permissão aprovada no Gideon Hub','stale_screen':'A tela mudou desde a última observação; observe de novo','backend_unavailable':'Este recurso não tem backend disponível nesta sessão (portal, AT-SPI, PipeWire, câmera ou KScreen); nada foi feito','not_recording':'Nenhuma gravação em andamento','already_recording':'Já há uma gravação em andamento','unknown_route':'Saída de áudio não encontrada; nada mudou','unknown_app':'Stream de áudio não encontrado; nada mudou','no_focus':'Nenhuma janela com foco; nada foi digitado','timeout':'O recurso não respondeu no prazo; nada foi confirmado','busy':'Outra operação de percepção está em andamento','invalid_input':'Entrada recusada pelo worker'}
PERCEPTION_UNREAD='não lido';PERCEPTION_ARM=object()
def _no_constant(name):raise ValueError(name)
def _exact(value,keys):return isinstance(value,dict) and set(value)==set(keys)
def _keys_ok(o,required,optional=()):return isinstance(o,dict) and set(required)<=set(o)<=set(required)|set(optional)
def _backend(o,names):return isinstance(o,dict) and o.get('backend') in names
def _refusal(o):return isinstance(o,dict) and o.get('supported') is False and o.get('reason') in PERCEPTION_REFUSALS
def _on_off(value):return value in ('on','off')
PERCEPTION_REFUSALS=('no_gesture_model_installed','monitor_would_feed_back_to_speakers')
# WP-17: the real worker answers (scripts/perception_worker.py). `available`/`reason` read the backend; refusals are ok outputs.
AVAILABILITY_KEYS=('backend','available','reason')
AUDIO_LEVEL_MAX=150
def _status(o,backend):return _keys_ok(o,AVAILABILITY_KEYS) and _backend(o,(backend,)) and type(o['available']) is bool and plain_text(o['reason'],64)
def _out_capture(o):return _keys_ok(o,('backend','epoch','width','height','sha256','regions')) and _backend(o,('portal',)) and is_int(o['epoch'],0,2**32) and is_int(o['width'],1,16384) and is_int(o['height'],1,16384) and digest(o['sha256']) and o['regions']==[]
def _out_status(o):return _status(o,'portal')
def _out_cc_status(o):return _status(o,'atspi')
def _out_tree(o):
    if not (_keys_ok(o,('backend','epoch','window','elements')) and _backend(o,('atspi',)) and is_int(o['epoch'],0,2**32) and plain_text(o['window'],256) and isinstance(o['elements'],list) and len(o['elements'])<=PERCEPTION_ELEMENTS):return False
    return all(_keys_ok(e,('id','role','name','x','y')) and is_int(e['id'],0,2**32) and plain_text(e['role'],64) and plain_text(e['name'],256) and is_int(e['x'],0,16384) and is_int(e['y'],0,16384) for e in o['elements'])
def _out_cc_act(o):return _keys_ok(o,('backend','kind','injected','verified')) and _backend(o,('remote_desktop',)) and o['kind'] in ('type','key') and is_int(o['injected'],0,4096) and type(o['verified']) is bool
def _sinks_ok(o):return isinstance(o['sinks'],list) and len(o['sinks'])<=64 and all(_keys_ok(s,('id','name')) and is_int(s['id'],0,2**32) and plain_text(s['name'],64) for s in o['sinks'])
def _streams_ok(o):return isinstance(o['streams'],list) and len(o['streams'])<=64 and all(_keys_ok(s,('id','app','volume')) and is_int(s['id'],0,2**32) and plain_text(s['app'],64) and is_int(s['volume'],0,AUDIO_LEVEL_MAX) for s in o['streams'])
def _out_audio_state(o):return _keys_ok(o,('backend','default_sink','sinks','streams')) and _backend(o,('pipewire',)) and is_int(o['default_sink'],-1,2**32) and _sinks_ok(o) and _streams_ok(o)
def _out_audio_act(o):
    if not _backend(o,('pipewire',)) or type(o.get('verified')) is not bool:return False
    if o.get('kind')=='route':return _keys_ok(o,('backend','kind','previous','default_sink','verified')) and is_int(o['previous'],-1,2**32) and is_int(o['default_sink'],-1,2**32)
    if o.get('kind')=='app_volume':return _keys_ok(o,('backend','kind','stream','previous','volume','verified')) and is_int(o['stream'],0,2**32) and is_int(o['previous'],0,AUDIO_LEVEL_MAX) and is_int(o['volume'],0,AUDIO_LEVEL_MAX)
    return False
def _mic_fields(o):return _backend(o,('pipewire',)) and is_int(o['gain'],0,AUDIO_LEVEL_MAX) and type(o['muted']) is bool and type(o['recording']) is bool and o['indicator']==('on' if o['recording'] else 'off')
def _out_mic_state(o):return _keys_ok(o,('backend','source','gain','muted','recording','indicator')) and is_int(o['source'],0,2**32) and _mic_fields(o)
def _out_mic_receipt(o):
    if _refusal(o):return _keys_ok(o,('backend','supported','reason')) and _backend(o,('pipewire',))
    return _keys_ok(o,('backend','previous','gain','verified')) and _backend(o,('pipewire',)) and is_int(o['previous'],0,AUDIO_LEVEL_MAX) and is_int(o['gain'],0,AUDIO_LEVEL_MAX) and type(o['verified']) is bool
def _out_mic_record(o):
    if not isinstance(o,dict):return False
    if o.get('recording') is True:return _keys_ok(o,('backend','recording','indicator','max_seconds')) and _backend(o,('pipewire',)) and o['indicator']=='on' and is_int(o['max_seconds'],1,120)
    return _keys_ok(o,('backend','recording','indicator','seconds','peak','rms','samples')) and _backend(o,('pipewire',)) and o['recording'] is False and o['indicator']=='off' and is_int(o['seconds'],0,3600) and is_int(o['peak'],0,32767) and is_int(o['rms'],0,32767) and is_int(o['samples'],0,2**40)
def _out_cam_state(o):return _keys_ok(o,('backend','device','present','opt_in','indicator')) and _backend(o,('v4l2',)) and plain_text(o['device'],64) and type(o['present']) is bool and type(o['opt_in']) is bool and o['indicator']==('on' if o['opt_in'] else 'off')
def _out_cam_optin(o):return _keys_ok(o,('backend','opt_in','indicator')) and _backend(o,('v4l2',)) and type(o['opt_in']) is bool and o['indicator']==('on' if o['opt_in'] else 'off')
def _out_cam_capture(o):return _keys_ok(o,('backend','width','height','sha256','mean_luma','indicator')) and _backend(o,('v4l2',)) and is_int(o['width'],1,4096) and is_int(o['height'],1,4096) and digest(o['sha256']) and is_int(o['mean_luma'],0,255) and o['indicator']=='on'
def _out_cam_gestures(o):return _refusal(o) and _keys_ok(o,('backend','supported','reason')) and _backend(o,('v4l2',))
def _out_display_status(o):
    if not (_keys_ok(o,('backend','outputs','undo_pending')) and _backend(o,('kscreen',)) and is_int(o['undo_pending'],0,64) and isinstance(o['outputs'],list) and len(o['outputs'])<=8):return False
    return all(_keys_ok(i,('name','enabled','scale','brightness')) and plain_text(i['name'],32) and type(i['enabled']) is bool and is_int(i['scale'],50,400) and is_int(i['brightness'],-1,100) for i in o['outputs'])
def _out_display_act(o):return _keys_ok(o,('backend','output','op','previous','value','verified')) and _backend(o,('kscreen',)) and plain_text(o['output'],32) and o['op'] in ('scale','brightness') and is_int(o['previous'],0,400) and is_int(o['value'],0,400) and type(o['verified']) is bool
def _out_display_restore(o):return _keys_ok(o,('backend','restored','verified')) and _backend(o,('kscreen',)) and is_int(o['restored'],0,64) and type(o['verified']) is bool
def _out_shortcut_status(o):return _keys_ok(o,('backend','available','reason','bound')) and _backend(o,('portal','kglobalaccel')) and type(o['available']) is bool and plain_text(o['reason'],64) and is_int(o['bound'],0,8)
def _out_shortcut_bind(o):return _keys_ok(o,('backend','id','trigger','bound')) and _backend(o,('portal','kglobalaccel')) and plain_text(o['id'],32) and plain_text(o['trigger'],32) and is_int(o['bound'],0,8)
def _out_shortcut_events(o):return _keys_ok(o,('backend','events')) and _backend(o,('portal','kglobalaccel')) and isinstance(o['events'],list) and len(o['events'])<=16 and all(_keys_ok(e,('id','at_ms')) and plain_text(e['id'],32) and is_int(e['at_ms'],0,2**53) for e in o['events'])
# Output rule per allowlisted capability: a result that fails its rule is refused before QML sees it.
PERCEPTION_OUTPUTS={'screen_observe.capture':_out_capture,'screen_observe.status':_out_status,'computer_control.tree':_out_tree,'computer_control.act':_out_cc_act,'computer_control.status':_out_cc_status,'audio_advanced.state':_out_audio_state,'audio_advanced.act':_out_audio_act,'mic_advanced.state':_out_mic_state,'mic_advanced.configure':_out_mic_receipt,'mic_advanced.monitor':_out_mic_receipt,'mic_advanced.record':_out_mic_record,'camera_gesture.state':_out_cam_state,'camera_gesture.optin':_out_cam_optin,'camera_gesture.capture':_out_cam_capture,'camera_gesture.gestures':_out_cam_gestures,'display_manipulate.status':_out_display_status,'display_manipulate.act':_out_display_act,'display_manipulate.restore':_out_display_restore,'shortcut_global.status':_out_shortcut_status,'shortcut_global.bind':_out_shortcut_bind,'shortcut_global.events':_out_shortcut_events}
def _in_act(capability,value):
    if capability=='computer_control.act':
        if value.get('kind')=='key':return set(value)=={'kind','key','epoch'} and plain_text(value['key'],16) and is_int(value['epoch'],0,2**32)
        if value.get('kind')=='type':return set(value)=={'kind','text','epoch'} and plain_text(value['text'],256) and is_int(value['epoch'],0,2**32)
        return False
    if capability=='audio_advanced.act':
        if value.get('kind')=='route':return set(value)=={'kind','sink'} and is_int(value['sink'],1,2**32)
        if value.get('kind')=='app_volume':return set(value)=={'kind','stream','volume'} and is_int(value['stream'],1,2**32) and is_int(value['volume'],0,100)
        return False
    if capability=='mic_advanced.configure':return set(value)=={'gain'} and is_int(value['gain'],0,150)
    if capability=='mic_advanced.monitor':return set(value)=={'enabled'} and type(value['enabled']) is bool
    if capability=='mic_advanced.record':return set(value)=={'action'} and value['action'] in ('start','stop')
    if capability=='display_manipulate.act':
        return set(value)=={'output','op','value'} and plain_text(value['output'],32) and ((value['op']=='scale' and value['value'] in (100,125,150,175,200)) or (value['op']=='brightness' and is_int(value['value'],20,100)))
    if capability=='display_manipulate.restore':return value=={}
    if capability=='shortcut_global.bind':return set(value)=={'id','trigger'} and plain_text(value['id'],32) and plain_text(value['trigger'],32)
    if capability in ('shortcut_global.status','shortcut_global.events'):return value=={}
    return set(value)=={'enabled'} and type(value['enabled']) is bool
def perception_input_problem(capability,text):
    """Strict input rule for perceptionInvoke: an allowlisted capability, a JSON object of at most 8 KiB, exact keys for reads, checked fields for actions."""
    if capability not in PERCEPTION_CAPABILITIES:return 'Capability de percepção desconhecida'
    if not isinstance(text,str) or utf8_len(text)>PERCEPTION_INPUT_LIMIT:return 'Entrada acima de 8 KiB'
    try:value=json.loads(text,parse_constant=_no_constant)
    except (ValueError,RecursionError):return 'Entrada não é JSON válido'
    if not (isinstance(value,dict) and bounded_output(value)):return 'Entrada deve ser um objeto JSON de até 8 KiB'
    if capability in PERCEPTION_NO_INPUT:return None if value=={} else 'Esta capability não aceita entrada'
    return None if _in_act(capability,value) else 'Entrada inválida para esta capability'
def perception_text(output):
    """PlainText summary of a validated output: one 'label: value' line per key, lists shown as their first items."""
    lines=[]
    for key,value in output.items():
        if type(value) is bool:shown='sim' if value else 'não'
        elif value is None:shown='nenhum'
        elif isinstance(value,list):
            shown=f'{len(value)} item(ns)'+''.join(f"\n  - {' · '.join(str(v) for v in item.values())}" for item in value[:8] if isinstance(item,dict))
        elif isinstance(value,str):shown=PERCEPTION_VALUES.get(value,value)
        else:shown=str(value)
        lines.append(f'{PERCEPTION_LABELS.get(key,key)}: {shown}')
    return '\n'.join(lines)[:2048]
def perception_code_message(code):return PERCEPTION_MESSAGES.get(code) or code_message(code)

def language_tag_ok(tag):return isinstance(tag,str) and 2<=len(tag)<=8 and all(c.isascii() and (c.isalnum() or c=='-') for c in tag)
def language_list_ok(items):return isinstance(items,list) and 1<=len(items)<=3 and all(language_tag_ok(i) for i in items) and len(set(items))==len(items)
def language_request_ok(stt,tts_language,tts_voice):return language_list_ok(stt) and language_tag_ok(tts_language) and isinstance(tts_voice,str) and VOICE_ID.fullmatch(tts_voice) is not None
def language_item_ok(item,kind):
    """One engine/language row of snapshot 'languages'. Strict keys; selectable only when bundled."""
    if not isinstance(item,dict) or set(item)!=LANGUAGE_ITEM_KEYS or item['kind']!=kind or not language_tag_ok(item['id']):return False
    def optional(value,limit):return value is None or (isinstance(value,str) and len(value.encode('utf-8'))<=limit)
    return (isinstance(item['label'],str) and 0<len(item['label'])<=40 and item['state'] in LANGUAGE_STATES
            and optional(item['engine'],160) and (item['size_bytes'] is None or (type(item['size_bytes']) is int and 0<=item['size_bytes']<=2**40))
            and type(item['size_partial']) is bool and optional(item['size_note'],200) and optional(item['license'],200)
            and (item['sha256'] is None or digest(item['sha256'])) and isinstance(item['quality'],str) and len(item['quality'])<=160
            and optional(item['evidence'],200) and isinstance(item['voices'],list) and len(item['voices'])<=8
            and all(isinstance(v,str) and VOICE_ID.fullmatch(v) is not None for v in item['voices'])
            and optional(item['reason'],300) and type(item['selected']) is bool and type(item['selectable']) is bool
            and item['selectable']==(item['state']=='bundled') and isinstance(item['source'],str) and len(item['source'])<=200)
def valid_languages_block(block):
    if not isinstance(block,dict) or set(block)!=LANGUAGE_BLOCK_KEYS or type(block['version']) is not int or block['version']!=1:return False
    engines=block['engines']
    if not isinstance(engines,dict) or set(engines)!={'stt','tts','wake'}:return False
    if not all(isinstance(engines[k],list) and len(engines[k])<=16 and all(language_item_ok(i,k) for i in engines[k]) for k in ('stt','tts','wake')):return False
    restart,install=block['restart_required'],block['install']
    return (language_list_ok(block['stt_selected']) and language_tag_ok(block['tts_selected']) and isinstance(block['tts_voice'],str) and VOICE_ID.fullmatch(block['tts_voice']) is not None
            and isinstance(restart,dict) and set(restart)=={'stt','tts'} and type(restart['stt']) is bool and type(restart['tts']) is bool
            and isinstance(install,dict) and set(install)=={'available','reason'} and install['available'] is False and isinstance(install['reason'],str) and len(install['reason'])<=200)
def short_text(value,limit=64):return isinstance(value,str) and len(value.encode('utf-8'))<=limit
def wake_phrase_id_ok(value):return short_text(value,64) and len(value)>=1 and all(c.isascii() and (c.isalnum() or c in '_-') for c in value)
def wake_setting_ok(item):
    return (isinstance(item,dict) and set(item)<={'id','active','sensitivity'} and {'id','active'}<=set(item) and wake_phrase_id_ok(item['id'])
            and type(item['active']) is bool and ('sensitivity' not in item or wake_sensitivity_ok(item['sensitivity'])))
def wake_setting_list_ok(items):
    return (isinstance(items,list) and len(items)<=16 and all(wake_setting_ok(i) for i in items)
            and len({i['id'] for i in items})==len(items) and sum(1 for i in items if i['active'])<=5)
def wake_measurement_ok(m):
    if m is None:return True
    return (isinstance(m,dict) and set(m)<={'source','positives','hits','negatives','false_wakes','latency_ms','passed'}
            and {'source','positives','hits','negatives','false_wakes','passed'}<=set(m) and m['source']=='synthetic'
            and all(type(m[k]) is int and 0<=m[k]<=64 for k in ('positives','hits','negatives','false_wakes')) and type(m['passed']) is bool
            and (m.get('latency_ms') is None or (type(m.get('latency_ms')) is int and 0<=m['latency_ms']<=600000)))
def wake_entry_ok(entry):
    return (isinstance(entry,dict) and set(entry)<=WAKE_PHRASE_ENTRY_KEYS and {'id','text','tokens','label','language','qualification','custom','selectable','boost','threshold'}<=set(entry)
            and wake_phrase_id_ok(entry['id']) and short_text(entry['text'],160) and short_text(entry['tokens'],200) and short_text(entry['label'],64) and short_text(entry['language'],8)
            and entry['qualification'] in WAKE_PHRASE_QUALIFICATIONS and type(entry['custom']) is bool and type(entry['selectable']) is bool
            and all(type(entry[k]) in (int,float) and 0<=entry[k]<=10 for k in ('boost','threshold')) and wake_measurement_ok(entry.get('measurement')))
def wake_phrases_block_ok(block):
    if not isinstance(block,dict) or not set(block)<=WAKE_PHRASE_BLOCK_KEYS or not {'max_active','max_custom','custom_revision','lexicon','settings','active','phrases'}<=set(block):return False
    if not (type(block['max_active']) is int and type(block['max_custom']) is int and type(block['custom_revision']) is int and type(block['lexicon']) is bool):return False
    if not wake_setting_list_ok(block['settings']):return False
    if not (isinstance(block['active'],list) and len(block['active'])<=5 and all(wake_phrase_id_ok(i) for i in block['active'])):return False
    if not (isinstance(block['phrases'],list) and len(block['phrases'])<=32 and all(wake_entry_ok(e) for e in block['phrases'])):return False
    test=block.get('test')
    return test is None or (isinstance(test,dict) and set(test)<={'id','state','code'} and wake_phrase_id_ok(test.get('id')) and test.get('state') in WAKE_TEST_STATES and ('code' not in test or short_text(test['code'])))
def phrase_check_ok(check):
    return (isinstance(check,dict) and set(check)<=PHRASE_CHECK_KEYS and {'ok','code'}<=set(check) and type(check['ok']) is bool and short_text(check['code'])
            and all(short_text(check[k],200) for k in ('text','tokens','word') if k in check))
def display_wake_entry(entry,settings,active):
    """One row of Configurações › Voz e Wake: the Core entry plus the active switch, sensitivity and labels."""
    setting=next((s for s in settings if s.get('id')==entry['id']),{})
    if entry['custom']:qualification_label='personalizada · não testada' if entry.get('measurement') is None else 'personalizada · teste sintético'
    else:qualification_label=WAKE_QUALIFICATION_LABELS.get(entry['qualification'],'')
    return {**entry,'active':entry['id'] in active,'sensitivity':setting.get('sensitivity'),'qualification_label':qualification_label,
            'measurement':entry.get('measurement')}
def validate_snapshot(data,request_id,min_sequence):
    """Validate presentation data before QML sees it; no command policy lives here."""
    def require(condition):
        if not condition:raise ValueError('invalid IPC snapshot')
    def integer(value,minimum=0,maximum=2**64-1):
        return type(value) is int and minimum<=value<=maximum
    def sid(value):return integer(value,1)
    def short(value,limit=64):return isinstance(value,str) and len(value.encode('utf-8'))<=limit
    require(isinstance(data,dict) and set(data)<=TOP_KEYS and TOP_REQUIRED<=set(data))
    require(type(data.get('version')) is int and data['version']==1)
    require(data.get('request_id')==request_id and isinstance(request_id,str))
    require(data.get('state') in ('idle','capturing','transcribing','executing','speaking'))
    require(integer(data.get('sequence')) and data['sequence']>=min_sequence)
    require('session_id' in data and (data['session_id'] is None or sid(data['session_id'])))
    if 'code' in data:require(short(data['code']))
    for key,states in (('wake_status',WAKE_STATES),('stt_status',STT_STATES),('speech_status',SPEECH_STATES)):
        if key in data:require(data[key] in states)
    if 'stt_last_error' in data:require(data['stt_last_error'] in STT_REASONS)
    if 'audio' in data:require(audio_ok(data['audio']))
    if 'text_input_available' in data:require(type(data['text_input_available']) is bool)
    if 'speech_samples' in data:require(integer(data['speech_samples'],0,240000))
    if 'configuration_status' in data:
        require(data['configuration_status'] in ('ready','safe_mode','restart_required'))
        if data['configuration_status']!='ready':require(data['state']=='idle' and data['session_id'] is None and data.get('text_input_available') is not True)
    if 'configuration_recovery_available' in data:
        require(type(data['configuration_recovery_available']) is bool)
        require(not data['configuration_recovery_available'] or data.get('configuration_status')=='safe_mode')
    prefs=data.get('preferences')
    if prefs is not None:
        require(isinstance(prefs,dict) and set(prefs)<=PREFERENCE_KEYS and {'version','session_timeout_ms','revision','audible_feedback','wake_phrase','visual_feedback','output_volume_percent'}<=set(prefs))
        require(type(prefs.get('version')) is int and prefs['version']==1)
        require(integer(prefs.get('revision')) and integer(prefs.get('session_timeout_ms'),50,60000))
        require(type(prefs.get('audible_feedback')) is bool)
        require(type(prefs['visual_feedback']) is bool and integer(prefs['output_volume_percent'],0,100))
        # A6 consent: the Core always reports it; strict bool.
        require(type(prefs.get('live_audio')) is bool)
        # A11 consent for host actions: the Core always reports it; strict bool.
        require(type(prefs.get('real_actions')) is bool)
        # CFG-04 retention and DIAG-02 developer mode: the Core always reports them; checked when present (older fixtures omit them).
        if 'history_retention' in prefs:require(prefs['history_retention'] in HISTORY_RETENTION_VALUES)
        if 'developer_mode' in prefs:require(type(prefs['developer_mode']) is bool)
        if 'wake_phrases' in prefs:require(wake_setting_list_ok(prefs['wake_phrases']))
        if 'wake_sensitivity' in prefs:require(wake_sensitivity_ok(prefs['wake_sensitivity']))
        if 'input_conditioning' in prefs:require(prefs['input_conditioning'] in INPUT_CONDITIONING_VALUES)
        for key in ('audio_input_device','audio_output_device'):
            if key in prefs:require(audio_device_ok(prefs[key]))
        previous=prefs.get('previous_preferences')
        if previous is not None:
            require(isinstance(previous,dict) and type(previous.get('audible_feedback')) is bool and integer(previous.get('session_timeout_ms'),50,60000))
            if 'visual_feedback' in previous:require(type(previous['visual_feedback']) is bool)
            if 'output_volume_percent' in previous:require(integer(previous['output_volume_percent'],0,100))
            if 'wake_sensitivity' in previous:require(wake_sensitivity_ok(previous['wake_sensitivity']))
            if 'input_conditioning' in previous:require(previous['input_conditioning'] in INPUT_CONDITIONING_VALUES)
            for key in ('audio_input_device','audio_output_device'):
                if key in previous:require(audio_device_ok(previous[key]))
        # Idiomas: when the Core reports them, all three are present and well-formed.
        if any(key in prefs for key in ('stt_languages','tts_language','tts_voice')):
            require(language_request_ok(prefs.get('stt_languages'),prefs.get('tts_language'),prefs.get('tts_voice')))
        wake=prefs.get('wake_phrase')
        require(wake is None or (short(wake) and len(wake)>0 and all(c.isascii() and (c.isalnum() or c in '_-') for c in wake)))
    if 'languages' in data:require(valid_languages_block(data['languages']))
    if 'actions' in data:require(valid_actions_block(data['actions']))
    if 'wake_phrases' in data:require(wake_phrases_block_ok(data['wake_phrases']))
    if 'phrase_check' in data:require(phrase_check_ok(data['phrase_check']))
    hub=data.get('hub')
    if hub is not None:
        require(isinstance(hub,dict) and type(hub.get('version')) is int and hub['version']==1)
        require(set(hub)<=HUB_KEYS and HUB_REQUIRED<=set(hub))
        require(hub.get('status') in ('verified','quarantined') and type(hub.get('publisher_verified')) is bool)
        require(hub.get('publisher_verified') is False or (hub.get('status')=='verified' and len(hub.get('entries') or [])>0))
        require(integer(hub['approval_revision']) and integer(hub['orphans']))
        if 'reason' in hub:require(hub['status']=='quarantined' and hub['reason'] in HUB_REASONS)
        if hub.get('import') is not None:
            transfer=hub['import'];require(isinstance(transfer,dict) and set(transfer)=={'import_id','plugin_id','received','expected'} and short(transfer.get('import_id')) and short(transfer.get('plugin_id')) and integer(transfer.get('expected'),1,67108864) and integer(transfer.get('received'),0,transfer['expected']))
        entries=hub.get('entries');require(isinstance(entries,list) and len(entries)<=8 and all(isinstance(e,dict) and set(e)<=ENTRY_KEYS and ENTRY_REQUIRED<=set(e) for e in entries))
        # Grant date only on an approved entry; a record from before the date existed has none (the Core omits it).
        require(all('approved_at_ms' not in e or (e['permissions_approved'] is True and integer(e['approved_at_ms'],1)) for e in entries))
        installed=hub.get('installed');require(integer(hub.get('install_revision')) and isinstance(installed,list) and len(installed)<=8 and (hub['status']=='verified' or not installed))
        records={}
        for record in installed:
            require(isinstance(record,dict) and set(record)=={'plugin_id','semver','manifest_sha256','state','runtime','previous'})
            require(short(record['plugin_id'],128) and bool(record['plugin_id']) and short(record['semver'],128) and bool(record['semver']) and record['state'] in ('installed','quarantined') and record['runtime'] in RUNTIME_STATES and digest(record['manifest_sha256']))
            previous=record['previous'];require(previous is None or (isinstance(previous,dict) and set(previous)=={'semver','manifest_sha256'} and short(previous['semver'],128) and bool(previous['semver']) and digest(previous['manifest_sha256'])))
            require(record['plugin_id'] not in records);records[record['plugin_id']]=record
        if hub['status']=='quarantined':require(hub.get('import') is None and not entries and hub.get('repository') is None and hub.get('catalog_sha256') is None)
        else:
            require(short(hub.get('repository'),256) and hub['repository'].startswith('https://github.com/'))
            require(digest(hub.get('catalog_sha256')))
        if hub.get('import') is not None:
            transfer=hub['import'];matching=[e for e in entries if e.get('plugin_id')==transfer['plugin_id']]
            require(len(matching)==1 and matching[0].get('status') in ('not_installed','update_available') and matching[0].get('permissions_approved') is True and transfer['expected']==matching[0].get('download_size'))
        ids=set()
        for entry in entries:
            for key in ('plugin_id','semver','publisher','license','support_policy'):require(short(entry.get(key),128) and bool(entry[key]))
            require(digest(entry['manifest_sha256']))
            require(type(entry['payload_staged']) is bool and (not entry['payload_staged'] or entry.get('status') in ('not_installed','update_available')))
            require(type(entry['permissions_approved']) is bool and (not entry['permissions_approved'] or (entry.get('status') in ('not_installed','update_available','installed') and integer(hub.get('approval_revision'),1))))
            if 'staged_error' in entry:require(entry['staged_error'] in STAGED_ERRORS and entry['payload_staged'] is False)
            require(entry['plugin_id'] not in ids);ids.add(entry['plugin_id'])
            require(integer(entry.get('api_version'),0,65535) and integer(entry.get('download_size'),0,67108864))
            require(entry.get('status') in ('not_installed','incompatible','installed','update_available') and entry.get('reason') in ('none','api_version','target','dependencies_unresolved'))
            require((entry['status']=='incompatible') == (entry['reason']!='none'))
            record=records.get(entry['plugin_id'])
            if entry['status']=='installed':require(record is not None and record['manifest_sha256']==entry['manifest_sha256'])
            elif entry['status']=='update_available':require(record is not None and record['manifest_sha256']!=entry['manifest_sha256'])
            elif entry['status']=='not_installed':require(record is None)
            for key in ('targets','permissions','conflicts'):
                require(isinstance(entry.get(key),list) and len(entry[key])<=8 and all(short(v) and bool(v) for v in entry[key]))
            deps=entry.get('dependencies');require(isinstance(deps,list) and len(deps)<=8 and all(isinstance(d,dict) and short(d.get('plugin_id')) and short(d.get('semver')) for d in deps))
            if 'runtime' in entry:require(entry['runtime']=='python3_script')
            if 'capabilities' in entry:
                caps=entry['capabilities'];require(isinstance(caps,list) and 1<=len(caps)<=8 and len(set(caps))==len(caps) and all(isinstance(c,str) and len(c)<=64 and CAPABILITY_ID.fullmatch(c) and c.startswith(entry['plugin_id']+'.') for c in caps))
                require('runtime' in entry)
    # Plugins: Core always sends the section when a hub exists; older no-hub Cores may omit it.
    plugins=data.get('plugins');items=[]
    if plugins is None:require(hub is None)
    else:
        require(isinstance(plugins,dict) and set(plugins)=={'revision','status','items'} and integer(plugins['revision']) and plugins['status'] in ('ok','quarantined'))
        items=plugins['items'];require(isinstance(items,list) and len(items)<=8)
        installed={r['plugin_id']:r for r in (hub or {}).get('installed',[])};listed={e['plugin_id']:e for e in (hub or {}).get('entries',[])}
        if hub is None or hub['status']!='verified':require(not items)
        names=set()
        for item in items:
            require(isinstance(item,dict) and set(item)=={'plugin_id','semver','capabilities','state','enabled','restarts','last_error'})
            ident=item['plugin_id'];require(isinstance(ident,str) and len(ident)<=64 and PLUGIN_ID.fullmatch(ident) and ident not in names);names.add(ident)
            caps=item['capabilities'];require(isinstance(caps,list) and len(caps)<=8 and len(set(caps))==len(caps) and all(isinstance(c,str) and len(c)<=64 and CAPABILITY_ID.fullmatch(c) for c in caps))
            require(short(item['semver'],128) and bool(item['semver']) and type(item['enabled']) is bool and item['state'] in PLUGIN_STATES and integer(item['restarts'],0,255))
            require(item['last_error'] is None or item['last_error'] in PLUGIN_LAST_ERRORS)
            record=installed.get(ident);entry=listed.get(ident)
            require(record is not None and record['semver']==item['semver'] and caps==(entry.get('capabilities',[]) if entry else []))
            require((item['state']=='quarantined')==(record['state']=='quarantined'))
            if item['enabled']:require(item['state'] in ('starting','running','failed','stopped') and record['state']=='installed' and entry is not None and entry['status']=='installed')
            else:require(item['state'] in ('disabled','quarantined'))
            if record['state']=='installed':require(record['runtime']==(item['state'] if item['enabled'] else 'disabled'))
        require(names==set(installed))
    result=data.get('capability_result')
    if result is not None:
        require(isinstance(result,dict) and set(result)<={'capability','plugin_id','ok','output','error','elapsed_ms','partial',HTTP_STATUS_KEY} and {'capability','plugin_id','ok','elapsed_ms'}<=set(result))
        require(isinstance(result['capability'],str) and len(result['capability'])<=64 and CAPABILITY_ID.fullmatch(result['capability']) and isinstance(result['plugin_id'],str) and type(result['ok']) is bool and integer(result['elapsed_ms']))
        owner=next((i for i in items if i['plugin_id']==result['plugin_id']),None)
        require(owner is not None and result['capability'] in owner['capabilities'])
        if result['ok']:require('output' in result and 'error' not in result and bounded_output(result['output']))
        else:require('error' in result and 'output' not in result and result['error'] in CAPABILITY_ERRORS)
        # Model text streams with newlines, so partial is only bounded here; QML shows it as PlainText.
        if 'partial' in result:require(isinstance(result['partial'],str) and utf8_len(result['partial'])<=PARTIAL_LIMIT)
        # model_selftest_failed may carry the provider's HTTP status too (C2); no other code may.
        if HTTP_STATUS_KEY in result:require(result['ok'] is False and result.get('error') in ('http_error','model_selftest_failed') and is_int(result[HTTP_STATUS_KEY],100,599))
    # Core always sends llm and tool_proposals; top-level partial exists only while an invocation streams.
    require('llm' in data and 'tool_proposals' in data and valid_llm(data['llm']) and valid_tools(data['tool_proposals']))
    # C3: the agent block is optional while Cores without the runtime omit it; when present it is null or the exact run view.
    if 'agent' in data:require(valid_agent(data['agent']))
    # S4: the skills block is optional (absent or null while the skill engine is not published); when present it is the exact view of docs/S4.md.
    if 'skills' in data:require(valid_skills(data['skills']))
    # S5: the connections block is optional (absent or null while the connection manager is not published); when present it is the exact view of docs/S5.md E1.
    if 'connections' in data:require(valid_connections(data['connections']))
    # S5 E3: the registry block is optional (absent or null while the registry is not published); when present it is the exact view of docs/S5.md E3.
    if 'registry' in data:require(valid_registry(data['registry']))
    # WP-10a: the personal block is always present once the Core runs; its reply is only on the answer to a personal request.
    if 'personal' in data:require(valid_personal(data['personal']))
    if 'personal_reply' in data:require(isinstance(data['personal_reply'],dict))
    partial=data.get('partial')
    require(partial is None or (isinstance(partial,str) and utf8_len(partial)<=PARTIAL_LIMIT))
    pack=data.get('base_pack')
    if pack is not None:
        require(isinstance(pack,dict) and type(pack.get('version')) is int and pack['version']==1)
        require(short(pack.get('id')) and pack.get('scope')=='dev_virtual_en' and pack.get('preflight')=='verified')
        # DIAG-01 / WP-15: pack_sha256 is the SHA-256 of the pack definition (src/pack.rs), always present in the Core block.
        require(set(pack)==PACK_KEYS and isinstance(pack.get('engines'),dict) and set(pack['engines'])=={'wake','stt','tts'} and all(short(v,160) for v in pack['engines'].values()))
        require(digest(pack['pack_sha256']))
        choices=pack.get('wake_phrases');require(isinstance(choices,list) and 1<=len(choices)<=8)
        ids=set()
        for choice in choices:
            require(isinstance(choice,dict) and short(choice.get('id')) and short(choice.get('text'),128) and choice.get('qualification') in ('dev_qualified','poc_required'))
            require(choice['id'] not in ids);ids.add(choice['id'])
        require(pack.get('active_phrase') is None or (isinstance(pack['active_phrase'],str) and pack['active_phrase'] in ids))
        require(isinstance(pack.get('default_phrase'),str) and pack['default_phrase'] in ids and short(pack.get('voice')) and pack.get('language')=='en')
        require(pack.get('audio_input')=='virtual_pcm' and pack.get('audio_output')=='virtual')
    t=data.get('transcript')
    if t is not None:
        require(isinstance(t,dict))
        require(set(t)==TRANSCRIPT_KEYS and t['source'] in STT_SOURCES and short(t.get('raw'),4096) and short(t.get('normalized'),4096) and type(t.get('is_final')) is bool and sid(t.get('session_id')))
        require(integer(t.get('revision'),1,256) and integer(t['audio_end_us']))
        require(t['confidence'] is None or (type(t['confidence']) in (int,float) and math.isfinite(t['confidence'])))
    capture=data.get('capture')
    if capture is not None:
        require(isinstance(capture,dict) and set(capture)==CAPTURE_KEYS and sid(capture['session_id']) and integer(capture['start_us']) and integer(capture['end_us']) and integer(capture['samples'],0,2**32))
        require(digest(capture['pcm_sha256']) and capture['reason'] in CAPTURE_REASONS)
    speech=data.get('speech')
    if speech is not None:
        require(isinstance(speech,dict) and set(speech)==SPEECH_KEYS and integer(speech['output_volume_percent'],0,100) and sid(speech['session_id']) and integer(speech['sample_rate'],1,2**32))
        require(integer(speech['samples'],0,2**32) and integer(speech['chunks'],0,2**32) and digest(speech['pcm_sha256']) and integer(speech['first_pcm_ms']) and integer(speech['elapsed_ms']))
        require(type(speech['peak']) in (int,float) and type(speech['rms']) in (int,float) and speech['sink']=='virtual')
    command=data.get('command')
    if command is not None:
        require(isinstance(command,dict) and set(command)==COMMAND_KEYS and sid(command.get('session_id')) and short(command.get('code')))
        receipt=command.get('receipt')
        if receipt is not None:
            require(isinstance(receipt,dict) and set(receipt)==RECEIPT_KEYS)
            require(type(receipt.get('verified')) is bool and short(receipt.get('scope')) and short(receipt.get('result'),256))
            job=receipt.get('job')
            require(isinstance(job,dict) and set(job)==JOB_KEYS and job.get('session_id')==command['session_id'] and isinstance(job.get('command'),dict))
            kind=job['command'].get('kind');require(kind in COMMAND_KINDS and set(job['command'])=={'kind',*COMMAND_KINDS[kind]})
    if 'events' in data:
        require(isinstance(data['events'],list) and len(data['events'])<=64)
        previous=-1;previous_ms=0
        for event in data['events']:
            require(isinstance(event,dict) and set(event)==EVENT_KEYS)
            require(integer(event.get('sequence')) and previous<event['sequence']<=data['sequence'])
            require(short(event.get('kind')) and short(event.get('request_id')))
            require('session_id' in event and (event['session_id'] is None or sid(event['session_id'])))
            require(integer(event.get('at_ms')) and event['at_ms']>=previous_ms)
            require(event.get('origin') in EVENT_ORIGINS and event.get('outcome') in EVENT_OUTCOMES)
            previous=event['sequence'];previous_ms=event['at_ms']
    return data

PREFS_DONE='Preferências salvas pelo Core'
# Core codes and states -> Portuguese UI text. Unknown codes fall back to a visible generic message.
CODE_MESSAGES={
    'invalid_message':'Mensagem inválida para o Core',
    'busy':'Core ocupado; tente novamente em instantes',
    'invalid_text':'Texto inválido: use 1 a 512 bytes, sem quebras de linha',
    'input_disabled':'Entrada de texto indisponível no momento',
    'stale_hub_revision':'Catálogo mudou; atualize e tente de novo',
    'hub_import_busy':'Importação do catálogo em andamento',
    'permissions_not_approved':'Aprove as permissões antes de ativar',
    'capability_unavailable':'Capability indisponível no momento',
    'stale_plugin_revision':'Estado do plugin mudou; atualize e tente de novo',
    'wake_not_qualified':'Frase de wake sem qualificação aprovada',
    'plugin_not_runnable':'Plugin não pode ser executado',
    'plugin_crashed':'Plugin encerrou com falha',
    'timed_out':'Tempo esgotado',
    'timeout':'Tempo do provedor esgotado',
    'cancelled':'Cancelado',
    'invoke_cancelled':'Cancelado',
    'capture_completed':'Captura concluída',
    'replaying':'Reprodução em andamento',
    # Preferências do app e do Core (app/uisettings.py e preferências da ponte).
    'stale_preferences':'Configurações mudaram no Core; atualize e tente de novo',
    'invalid_preferences':'Preferências recusadas pelo Core: valor inválido; nada foi salvo',
    'invalid_languages':'Idiomas recusados: escolha de 1 a 3 idiomas válidos para escuta e uma voz de fala; nada foi salvo',
    'language_not_installed':'Idioma ainda não instalado: o download depende da aprovação do dono; nada foi salvo','language_pack_unavailable':'Modelos do idioma ausentes ou diferentes do pacote; nada foi ativado',
    'language_unsupported':'Idioma sem suporte nesta versão; nada foi salvo',
    'preferences_storage_error':'Preferências indisponíveis: o arquivo de configuração não pôde ser lido ou gravado',
    'preferences_unavailable':'Preferências indisponíveis agora; tente quando o Gideon estiver em espera',
    'consent_required':'Escuta do microfone não ativada: a confirmação não chegou ao Core; nada foi alterado',
    # C1: LLM engine, secrets and tool proposals (Core codes from src/llmcfg.rs, src/core.rs, src/tools.rs).
    'key_missing':'Chave ausente para este provedor',
    'provider_not_configured':'Provedor não configurado',
    'cloud_not_authorized':'Envio à nuvem não autorizado; marque o consentimento em Motor LLM',
    'permission_denied':'Permissão de rede do plugin negada',
    'http_error':'Erro HTTP do provedor',
    'response_too_large':'Resposta do provedor grande demais',
    'network_unavailable':'Rede indisponível para o provedor',
    'unknown_tool':'Ferramenta desconhecida; ação recusada',
    'invalid_args':'Argumentos inválidos; ação recusada',
    'proposal_expired':'Proposta expirou sem decisão',
    'proposal_denied':'Proposta negada; não pode ser autorizada',
    'already_decided':'Proposta já foi decidida',
    'unknown_proposal':'Proposta desconhecida ou encerrada',
    'invalid_config':'Configuração do motor inválida',
    'stale_llm_revision':'Configuração do motor mudou; reabra o diálogo',
    'invalid_secret':'Chave inválida: 8 a 256 caracteres ASCII, sem espaços',
    'invalid_provider':'Provedor desconhecido',
    'secrets_unavailable':'Cofre de chaves indisponível',
    'secrets_storage_error':'Falha ao gravar o cofre de chaves',
    'llm_storage_error':'Falha ao gravar a configuração do motor',
    'llm_unavailable':'Configuração do motor indisponível',
    'invalid_input':'Entrada recusada pelo plugin',
    'executor_unavailable':'Executor de comandos indisponível',
    'user_denied':'Negada pelo usuário',
    'superseded':'Substituída por proposta mais recente',
    'expired':'Expirou sem decisão',
    'plugin_unavailable':'Plugin indisponível',
    'plugin_crashed':'Plugin encerrou com falha',
    # C2: model manager. Codes from the Core and the llm_engine.models capability (docs/C2.md).
    'model_unsupported_feature':'Modelo não suporta o recurso exigido; nada foi enviado ao provedor',
    'model_not_found':'Modelo não encontrado no catálogo; atualize a lista',
    'model_selftest_failed':'Teste do modelo falhou',
    'settings_unavailable':'Armazenamento de configurações do plugin indisponível',
    'no_lkg':'Não há configuração anterior salva para restaurar',
    # C3: agent runtime codes (AGENT_CODES, docs/C3.md). Keep this list in step with the allowlist above.
    'agent_busy':'Já existe um agente em execução; aguarde ou aborte',
    'unknown_run':'Execução do agente desconhecida ou já encerrada',
    'loop_blocked':'O agente repetiu a mesma ação; execução bloqueada',
    'stale_screen':'A tela mudou desde a observação; o agente vai reobservar',
    'permission_revoked':'Permissão da ferramenta revogada; execução bloqueada',
    'denied_by_user':'Negada pelo usuário; nada foi alterado',
    'revoked':'Motor LLM desativado ou revogado; execução encerrada',
    'max_steps':'Limite de passos do agente atingido',
    'budget_exhausted':'Limite de tokens do agente atingido',
    'deadline_exceeded':'Tempo limite da execução do agente atingido',
    'verification_failed':'Verificação após a ação falhou; efeito não confirmado',
    'awaiting_approval':'Aguardando sua aprovação na proposta de ferramenta',
    'executor_failed':'Executor da ferramenta falhou',
    'aborted':'Execução abortada',
    'verify_failed':'Verificação após a ação falhou; efeito não confirmado',
    'too_many_calls':'O modelo propôs mais ferramentas do que o limite por passo; excedentes recusados',
    'token_budget':'Limite de tokens do agente atingido',
    'run_deadline':'Tempo limite da execução do agente atingido',
    'empty_answer':'O modelo respondeu sem texto',
    'invalid_output':'Resposta do modelo fora do formato esperado',
    'destructive_disabled':'Ação destrutiva desativada nesta build; nada foi executado',
    'app_unavailable':'Aplicativo indisponível para a ferramenta',
    'app_write_failed':'Não foi possível gravar a alteração',
    'denied':'Ação recusada pelo Core',
    'unknown_capability':'Capability do motor LLM desconhecida',
    'plugin_error':'Motor LLM retornou erro interno',
    # C4: perception and action plugins (docs/C4.md). permission_denied and stale_screen read differently in the perception page (PERCEPTION_MESSAGES).
    'opt_in_required':'Câmera desligada: ative o opt-in antes de capturar',
    'unsupported':'Backend real não suportado neste ambiente; nada foi executado',
    'unknown_service':'Serviço de percepção indisponível nesta build',
    'capability_timeout':'Plugin de percepção não respondeu no prazo',
    # B6: the Core refuses the test wake unless it was started with --virtual-input (src/core.rs VirtualWake).
    'virtual_input_disabled':'Wake de teste indisponível: o Core foi iniciado sem --virtual-input',
}
STALE_MESSAGE='Estado mudou; reabra a confirmação'
# Display mapping (round 2). The Core wire values never change; these tables only choose the text the user reads.
# Each table has checks in scripts/test_bridge_protocol.py (class DisplayMapping).
WAKE_QUALIFICATION_LABELS={'dev_qualified':'em desenvolvimento','poc_required':'requer prova de conceito','custom':'personalizada · não testada'}
# Frases de ativação: Portuguese for every code the Core returns for the wake phrase ops (src/phrases.rs `code`).
PHRASE_MESSAGES={
    'phrase_empty':'Digite a frase.',
    'phrase_too_long':'Frase longa demais: use até 40 letras.',
    'phrase_invalid_characters':'Use só letras, espaços e apóstrofo: sem números nem pontuação.',
    'phrase_needs_two_words':'Use de 2 a 4 palavras; uma palavra sozinha é genérica demais.',
    'phrase_too_many_words':'Use no máximo 4 palavras.',
    'phrase_too_generic':'Frase genérica demais: use palavras mais específicas.',
    'phrase_too_few_tokens':'Frase curta demais para o detector: use palavras com mais sons.',
    'word_not_in_lexicon':'Palavra fora do dicionário do detector. Tente outra forma de escrever.',
    'token_not_in_vocabulary':'Som fora do vocabulário do detector.',
    'lexicon_unavailable':'Dicionário do detector indisponível neste pacote: frases personalizadas estão desligadas.',
    'phrase_duplicate':'Essa frase já existe.',
    'phrase_store_full':'Limite de 8 frases personalizadas atingido: remova uma antes.',
    'phrase_not_found':'Frase personalizada não encontrada.',
    'phrase_in_use':'Desative a frase antes de removê-la.',
    'phrase_unmeasured':'Teste a frase antes de ativá-la.',
    'phrase_measurement_failed':'Atenção: o teste sintético desta frase falhou. Ela pode não ser detectada ou disparar sem você falar. Ative só se aceitar esse risco.',
    'phrase_test_running':'Já há um teste em andamento. Aguarde o resultado.',
    'phrase_test_unavailable':'Teste indisponível: a voz de teste ou o dicionário não estão prontos.',
    'phrase_test_failed':'O teste não concluiu. Tente de novo.',
    'too_many_active_phrases':'Escolha até 5 frases ativas.',
    'invalid_wake_phrases':'Lista de frases recusada; nada foi salvo.',
    'wake_start_failed':'O detector não iniciou com essa lista. A lista anterior continua valendo.',
    'stale_phrase_store':'As frases personalizadas mudaram. Atualize a tela e tente de novo.',
    'phrase_store_error':'Não foi possível salvar as frases personalizadas.',
    # U1: only a safe-mode configuration needs recovery; a pending restart just needs the Core restarted.
    'configuration_not_ready':'Esta ação espera o reinício do Core. Reinicie o Core para continuar; a mudança salva já vale.',
}
# WP-10a personal areas (Memória, Almas, Hábitos, Automações, Histórico). The Core answers with these codes; the texts are Portuguese.
PERSONAL_AREAS=('memory','souls','habits','automations','conversations')
PERSONAL_MESSAGES={
    'personal_unavailable':'Dados pessoais indisponíveis: o armazenamento não abriu. Reinicie o Core.',
    'stale_revision':'Esta tela estava desatualizada: os dados mudaram. Atualize e tente de novo.',
    'consent_required':'Ative a fonte antes de salvar fatos dela.',
    'retention_never':'Histórico desligado (não guardar): nada de conversa é guardado.',
    'invalid_text':'Texto inválido ou vazio.',
    'memory_full':'Limite de fatos atingido: apague um antes.',
    'invalid_ttl':'Prazo inválido: use de 1 a 365 dias.',
    'unknown_fact':'Fato não encontrado.',
    'confirmation_required':'Confirme a ação antes de apagar.',
    'unknown_soul':'Alma não encontrada.',
    'soul_capacity':'Limite de almas atingido: apague uma antes.',
    'invalid_provenance':'Origem da alma inválida para este modo.',
    'invalid_confidence':'Confiança inválida.',
    'invalid_evidence':'Evidência inválida: informe trechos válidos.',
    'invalid_skill_id':'Skill inválida.',
    'skill_not_enabled':'A Skill precisa estar habilitada.',
    'habit_capacity':'Limite de hábitos atingido: remova um antes.',
    'habit_paused':'Hábito pausado: revise antes de executar.',
    'skill_version_changed':'A versão da Skill mudou: revise antes de executar.',
    'no_previous_version':'Não há versão anterior para voltar.',
    'invalid_inputs':'Entradas inválidas para a Skill.',
    'unknown_habit':'Hábito não encontrado.',
    'unknown_automation':'Automação não encontrada.',
    'automation_capacity':'Limite de automações atingido.',
    'schedule_in_past':'O horário já passou: escolha um horário futuro.',
    'invalid_schedule':'Agenda inválida.',
    'invalid_status':'Status inválido.',
    'automation_done':'Automação já concluída.',
    'automation_paused':'Automação pausada: revise antes de retomar.',
    'unknown_session':'Conversa não encontrada.',
    'conversation_capacity':'Limite de conversas atingido: apague uma antes.',
    'invalid_request':'Pedido inválido; nada foi alterado.',
    'unsupported_version':'Versão de pedido não suportada.',
    'unknown_area':'Área desconhecida.',
    'ledger_invalid':'Arquivo pessoal corrompido: a área ficou indisponível.',
    'ledger_unreadable':'Não foi possível ler o arquivo pessoal (permissões ou link). Nada foi alterado.',
    'ledger_write_failed':'Não foi possível gravar o arquivo pessoal. Nada foi alterado.',
    'ledger_full':'Arquivo pessoal cheio: apague dados antes.',
    'personal_dir_unavailable':'Pasta de dados pessoais indisponível.',
    'core_unavailable':'Core indisponível agora.',
    'deferred':'Adiado: o motor de Skills está ocupado. Tente de novo.',
    'needs_review':'Revise o hábito ou a automação antes de executar.',
    'reply_too_large':'Resultado grande demais para a tela. Use Exportar para guardar os dados em arquivo.',
    'personal_export_failed':'Não foi possível gravar a exportação. Nada foi apagado.',
    'live_audio_disabled':'Escuta do microfone desligada: ative o microfone em Configurações › Dispositivos.',
    'capture_unavailable':'Captura do microfone não está ativa neste Core.',
    'queued':'Na fila: o pedido segue quando a sessão de voz terminar.',
    'chat_failed':'O pedido da fila não pôde ser executado.',
    'stt_unavailable':'Transcrição indisponível agora.',
    'busy':'Ocupado: aguarde o término da ação atual.',
}
PERSONAL_OPS=frozenset({'personal','personal_export','personal_erase_all'})
LLM_PROVIDER_LABELS={'openrouter':'OpenRouter','opencode':'OpenCode','google':'Google','anthropic':'Anthropic','custom':'personalizado'}
LANGUAGE_LABELS={'EN':'inglês'}
RECEIPT_PREFIXES=(('Sandbox app process verified: ','Processo do app verificado no sandbox: '),)
def display_receipt(text):
    """Command receipt text as the user reads it: known Core prefixes are translated, anything else is shown as sent."""
    if isinstance(text,str):
        for raw,shown in RECEIPT_PREFIXES:
            if text.startswith(raw):return shown+text[len(raw):]
    return text
def display_wake_choice(choice):
    """A wake phrase row for QML: the Core fields plus the qualification label (empty for an unknown value)."""
    return {**choice,'qualification_label':WAKE_QUALIFICATION_LABELS.get(choice.get('qualification'),'')}
def display_provider(provider):return LLM_PROVIDER_LABELS.get(provider,provider or '')
PERMISSION_LABELS={'network_llm':'rede do motor LLM','storage_settings':'armazenamento de configurações','skills_author':'autoria de skills',
                   'screen_observe':'observação de tela','input_control':'controle de entrada','audio_route':'rota de áudio',
                   'mic_config':'configuração do microfone','camera_capture':'captura da câmera','display_manipulate':'ajuste de tela'}
def display_permission(permission):
    """Permission id as the user reads it. Unknown ids are shown as the Core sent them (they are never translated by guess)."""
    return PERMISSION_LABELS.get(permission,permission or '')
# Registry effect templates (src/tools.rs effect) and risk classes as Portuguese text. Unknown ids show no text (QML shows the absence text).
EFFECT_TEXT={'open_app':'Abrir {app}','set_volume':'Volume {level}','mute':'Silenciar',
             'get_status':'Consultar o estado do sistema','get_time':'Consultar a hora','get_date':'Consultar a data'}
RISK_TEXT={'read':'baixo','state_changing':'médio','destructive':'alto','public':'alto'}
def display_effect(effect):
    """Portuguese sentence for a registry effect, or '' when the proposal has no effect (the card then says 'não informado pelo plugin')."""
    if not (isinstance(effect,dict) and effect.get('id') in EFFECT_TEXT):return ''
    # A template whose parameters are missing (an old step with effect_id only) has no honest sentence: the absence text applies.
    if any(effect.get(param) in (None,'') for param in EFFECT_PARAMS[effect['id']]):return ''
    return EFFECT_TEXT[effect['id']].format(app=effect.get('app',''),level=effect.get('level',''))
def display_risk(risk):
    """'baixo', 'médio' or 'alto'; '' when the proposal declares no risk (the card then says 'não declarado')."""
    return RISK_TEXT.get(risk,'')
def grant_rows(snapshot):
    """Read-only Concessões rows (docs/ui-spec/30-permissoes.md §6), built only from the snapshot. Plugins: hub entries except incompatible ones. Skills: one row per skill item. Accounts: one approved row for granted scopes and one pending row for scopes awaiting consent."""
    rows=[]
    for entry in (snapshot.get('hub') or {}).get('entries') or []:
        if entry.get('status')=='incompatible':continue
        approved=entry.get('permissions_approved') is True
        if approved:state='approved'
        elif entry.get('status') in ('installed','update_available') and entry.get('permissions'):state='pending'
        else:state='not_approved'
        row={'origin':'plugin','owner_id':entry['plugin_id'],'label':', '.join(display_permission(p) for p in entry.get('permissions') or []) or 'sem permissões','state':state}
        if approved and 'approved_at_ms' in entry:row['approved_at_ms']=entry['approved_at_ms']
        rows.append(row)
    for item in (snapshot.get('skills') or {}).get('items') or []:
        rows.append({'origin':'skill','owner_id':item['id'],'label':item['name'],'state':'approved' if item['permissions_ok'] else 'pending'})
    conn=snapshot.get('connections') or {}
    labels={(p['id'],s['id']):s['label'] for p in conn.get('providers') or [] for s in p['scopes']}
    for item in conn.get('items') or []:
        for scopes,state in ((item.get('granted_scopes') or [],'approved'),(item.get('pending_scopes') or [],'pending')):
            if scopes:rows.append({'origin':'connection','owner_id':item['id'],'label':', '.join(labels.get((item['provider'],s),s) for s in scopes),'state':state})
    return rows
def pending_count(snapshot):
    """P of docs/ui-spec/30-permissoes.md §8: installed or updated plugins with permissions and no approval, plus accounts with scopes awaiting consent, plus one per MCP tool that needs re-approval (the queue of Visão geral lists each tool). Skills and action proposals are not counted."""
    count=sum(1 for e in (snapshot.get('hub') or {}).get('entries') or [] if e.get('permissions') and not e.get('permissions_approved') and e.get('status') in ('installed','update_available'))
    items=(snapshot.get('connections') or {}).get('items') or []
    count+=sum(1 for i in items if i.get('pending_scopes'))
    return count+sum(1 for i in items for t in i.get('tools') or [] if t.get('state')=='needs_reapproval')
CHAT_STATE_LABELS={'idle':'Em espera','waiting':'Aguardando resposta','streaming':'Respondendo','done':'Concluída','error':'Erro','cancelled':'Cancelada'}
# B12: actionable chat errors (Core codes of a failed chat turn). Each banner links to Extensões › Modelos LLM › Provedor e chaves.
CHAT_ERROR_BANNERS={'key_missing':'Falta a chave do provedor','provider_not_configured':'Nenhum provedor configurado','cloud_not_authorized':'Consentimento de nuvem necessário','model_unsupported_feature':'O modelo atual não suporta o recurso exigido'}
CHAT_ERROR_ACTION='Abrir Provedor e chaves'
# Raw Core codes never reach the screen. Unknown codes get one generic sentence; the code is appended only when the advanced setting (behavior.advanced) is on.
GENERIC_FAILURE='Não foi possível concluir a operação.'
CODE_DETAIL={'on':False}
def set_code_detail(on):CODE_DETAIL['on']=bool(on)
def code_message(code):
    text=CODE_MESSAGES.get(code) if isinstance(code,str) else None
    if text is not None:return text
    if CODE_DETAIL['on'] and isinstance(code,str) and SNAKE_CODE.fullmatch(code):return f'{GENERIC_FAILURE} Código: {code}'
    return GENERIC_FAILURE
# S4 skills (docs/S4.md D1-D4). The Core owns manifests, the ledger, dependencies and every transition; this layer checks the shape and size of what it shows and sends.
SKILL_STATES=('draft','validated','tested','approved','enabled','disabled','revised');SKILL_SOURCES=('created','imported','llm_draft')
SKILL_RUN_STATES=('running','awaiting_approval','done','failed','cancelled','rolled_back');SKILL_STEP_STATES=('pending','running','awaiting_approval','done','failed','denied','undone','cancelled')
# Validator reasons (skill_invalid:<reason>, docs/S4.md D1). Each one has a Portuguese message in CODE_MESSAGES.
SKILL_REASON_MESSAGES={
    'out_of_scope':'Passo chama capability fora das dependências declaradas',
    'exfiltration':'Manifest tenta enviar dados para fora: caminho, URL, shell ou segredo',
    'cycle':'Ciclo entre skills; recursão recusada',
    'depth':'Skill aninhada além do limite de profundidade (2)',
    'missing_dependency':'Dependência ausente: plugin ou ferramenta indisponível',
    'oversize':'Manifest ou campo acima do limite de tamanho',
    'unknown_key':'Campo desconhecido no manifest',
    'schema_version':'Versão de esquema não suportada (use 1)',
    'duplicate_id':'Já existe uma skill com este id',
    'permissions_escalated':'Esta versão pede mais permissões que a anterior; aprove de novo',
    'min_runtime':'Esta skill exige um Gideon mais novo',
    'reserved_capability':'Capability reservada da Base; a skill não pode usá-la',
    'grant_field':'Campo de permissão não é permitido dentro de passos',
    'unknown_step':'Referência a passo inexistente',
    'forward_ref':'Referência a passo que ainda não executou',
    'bad_template':'Template inválido: use só ${input.x} ou ${steps.id.campo}',
    'too_many_steps':'Mais passos que o limite (16)',
    'too_many_deps':'Mais dependências que o limite (8)',
    'bad_manifest':'Manifest malformado',
    'bad_id':'Id de skill inválido',
    'bad_version':'Versão inválida: use x.y.z',
    'bad_publisher':'Publisher inválido',
    'hash_mismatch':'Hash não confere: pacote adulterado',
    'corrupt_package':'Pacote corrompido',
    'symlink':'Link simbólico no pacote; recusado',
    'file_too_large':'Arquivo grande demais para importar (limite 64 KiB)',
    'path_not_allowed':'Arquivo fora da pasta de importação',
    'unverified_publisher':'Publisher não verificado',
}
SKILL_REASONS=frozenset(SKILL_REASON_MESSAGES)
# Operation codes the Core answers with for skill ops (not validator reasons). Codes shared with other channels reuse their CODE_MESSAGES text.
SKILL_OP_MESSAGES={
    'stale_skill_revision':'Skills mudaram no Core; atualize e tente de novo',
    'missing_dependency':'Dependência ausente: execução bloqueada antes de qualquer passo',
    'skill_busy':'Já existe uma skill em execução; aguarde ou cancele',
    'unknown_skill':'Skill desconhecida ou já removida',
    'unknown_skill_run':'Execução de skill desconhecida ou já encerrada',
    'skill_not_enabled':'Skill não está habilitada; nada foi executado',
    'skill_not_approved':'Aprove a skill antes de habilitar ou executar',
    'not_pending':'Este passo não está aguardando decisão',
    'unknown_step':'Passo desconhecido ou fora de ordem',
    'invalid_skill_input':'Entrada da skill inválida: confira os campos e os tipos',
    'invalid_manifest':'Manifest inválido: objeto JSON de até 16 KiB',
    'duplicate_skill':'Já existe uma skill com este id',
    'undo_failed':'Desfazer um passo falhou; confira o efeito manualmente',
    'rolled_back':'Execução revertida: os passos concluídos foram desfeitos',
    'invalid_import':'Pacote de importação inválido',
    'import_not_found':'Pacote não encontrado na pasta de importação',
    'stale_import':'A pré-visualização mudou; importe de novo',
}
SKILL_OP_CODES=frozenset(SKILL_OP_MESSAGES)|frozenset({'missing_dependency','permission_denied','verify_failed','capability_unavailable','capability_timeout','timeout','run_deadline','cancelled','denied','user_denied','destructive_disabled','plugin_error','invalid_output','invalid_input','max_steps','executor_unavailable','executor_failed','unknown_tool','llm_unavailable','unknown_service','aborted','awaiting_approval'})
SKILL_CODES=SKILL_OP_CODES|frozenset('skill_invalid:'+reason for reason in SKILL_REASONS)
CODE_MESSAGES.update({f'skill_invalid:{reason}':text for reason,text in SKILL_REASON_MESSAGES.items()})
CODE_MESSAGES.update({code:text for code,text in SKILL_OP_MESSAGES.items() if code not in CODE_MESSAGES})
CODE_MESSAGES.update({'skill_invalid':'Skill recusada pela validação do Core; nada foi gravado','model_output_invalid':'O modelo não devolveu um manifest JSON válido'}) 
CODE_MESSAGES.update(PHRASE_MESSAGES)
# setdefault: a code that already has a text (shared with other channels) keeps it.
for _code,_text in PERSONAL_MESSAGES.items():CODE_MESSAGES.setdefault(_code,_text)
CODE_MESSAGES.update(CONN_MESSAGES)
CODE_MESSAGES.update(REG_MESSAGES)
SKILL_ID=re.compile(r'[a-z][a-z0-9_]{2,40}');SKILL_STEP_ID=re.compile(r'[a-z][a-z0-9_]{0,23}');SKILL_IMPORT_NAME=re.compile(r'[A-Za-z0-9._-]{1,64}')
SKILL_SEMVER=re.compile(r'(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})')
# Limits mirror docs/S4.md: manifest and inputs at most 16 KiB; 16 skills x 3 versions in the ledger; 16 steps; 32 history entries; outputs at most 1 KiB.
SKILL_JSON_LIMIT=16384;SKILL_DESCRIPTION_LIMIT=1024;SKILL_ITEMS_LIMIT=48;SKILL_STEPS_LIMIT=16;SKILL_HISTORY_LIMIT=32;SKILL_OUTPUTS_LIMIT=1024;SKILL_FINDINGS_LIMIT=16;SKILL_CODES_LIMIT=8;SKILL_DEPS_LIMIT=8
SKILL_DRAFT_CAPABILITY='llm_engine.skill_draft';SKILL_DRAFT_PLUGIN='llm_engine';SKILL_DRAFT_DEADLINE_MS=30000
PENDING_SKILL_DRAFT='Gerando skill com o LLM…';SKILL_ARM=object()
SKILL_OPS=frozenset({'skill_validate','skill_save_draft','skill_dry_run','skill_approve','skill_enable','skill_disable','skill_rollback','skill_remove','skill_run','skill_decide','skill_cancel','skill_export','skill_import','skill_import_confirm'})
SKILL_ITEM_KEYS=frozenset({'id','name','version','state','source','active','deps_ok','permissions_ok','missing'});SKILL_ITEM_OPTIONAL=frozenset({'permissions_required'})
SKILL_RUN_KEYS=frozenset({'run_id','skill','state','step','steps'});SKILL_RUN_OPTIONAL=frozenset({'outputs'});SKILL_STEP_KEYS=frozenset({'id','state','code','risk','effect_id','effect','target'});SKILL_RISKS=('read','state_changing','destructive');SKILL_EFFECT=re.compile(r'[a-z_]{1,32}')
SKILL_HISTORY_KEYS=frozenset({'run_id','skill','version','state','step','codes'})
SKILL_IMPORT_KEYS=frozenset({'name','id','version','publisher','unverified','permissions_required','missing_deps','permission_delta','permissions_escalated','duplicate','findings'})
SKILL_FINDING_KEYS=frozenset({'code','field'})
SKILL_DRAFT_KEYS=frozenset({'draft_id','version','state','requirements','ambiguities','preview'});SKILL_DRAFT_OPTIONAL=frozenset({'diff','validation'})
def skill_json(text):
    """Local rule for a manifest or the inputs of a run: a JSON object of at most 16 KiB. Returns (value, problem); a None problem means the value may be sent."""
    try:
        if not isinstance(text,str):return None,'JSON inválido'
        if utf8_len(text)>SKILL_JSON_LIMIT:return None,'JSON acima de 16 KiB'
        value=json.loads(text,parse_constant=_no_constant)
    except (UnicodeError,ValueError,RecursionError):return None,'Entrada não é JSON válido'
    if not isinstance(value,dict):return None,'Deve ser um objeto JSON'
    return value,None
def skill_id_problem(ident,version=None):
    if not (isinstance(ident,str) and SKILL_ID.fullmatch(ident)):return 'Id de skill inválido'
    if version is not None and not (isinstance(version,str) and SKILL_SEMVER.fullmatch(version)):return 'Versão inválida: use x.y.z'
    return None
def skill_description_problem(text):
    """Rule for the LLM draft request: trimmed, 1..=1024 UTF-8 bytes, no control characters (the Core applies the same limit)."""
    try:
        if not isinstance(text,str) or not text.strip():return 'Descrição vazia'
        if utf8_len(text.strip())>SKILL_DESCRIPTION_LIMIT:return 'Descrição acima de 1024 bytes'
        if any(unicodedata.category(c)=='Cc' for c in text.strip()):return 'Descrição com quebra de linha ou controle não é aceita'
    except UnicodeError:return 'Descrição inválida'
    return None
def skill_code_ok(code):return isinstance(code,str) and code in SKILL_CODES
def valid_skill_item(item):
    """One ledger view row (docs/S4.md): exact keys, enums, semver, missing dependencies only as short plain names; deps_ok means nothing is missing; enabled is always active."""
    if not (isinstance(item,dict) and SKILL_ITEM_KEYS<=set(item)<=SKILL_ITEM_KEYS|SKILL_ITEM_OPTIONAL):return False
    if not (isinstance(item['id'],str) and SKILL_ID.fullmatch(item['id']) and text_ok(item['name'],64) and isinstance(item['version'],str) and SKILL_SEMVER.fullmatch(item['version'])):return False
    if item['state'] not in SKILL_STATES or item['source'] not in SKILL_SOURCES:return False
    if not all(type(item[k]) is bool for k in ('active','deps_ok','permissions_ok')):return False
    if item['state']=='enabled' and not item['active']:return False
    # permissions_required (manifest, at most 8): optional so older snapshots still validate.
    perms=item.get('permissions_required',[])
    if not (isinstance(perms,list) and len(perms)<=SKILL_CODES_LIMIT and all(isinstance(p,str) and text_ok(p,64) for p in perms)):return False
    missing=item['missing']
    if not (isinstance(missing,list) and len(missing)<=SKILL_DEPS_LIMIT and all(isinstance(m,str) and text_ok(m,128) for m in missing)):return False
    return item['deps_ok']==(not missing)
def valid_skill_run(run):
    """Run view (docs/S4.md D2): null, or exact keys with a known state, steps bounded and unique, codes from the allowlist, awaiting approval only with the current step, outputs at most 1 KiB."""
    if run is None:return True
    if not (isinstance(run,dict) and SKILL_RUN_KEYS<=set(run)<=SKILL_RUN_KEYS|SKILL_RUN_OPTIONAL):return False
    if not (run_id_ok(run['run_id']) and isinstance(run['skill'],str) and SKILL_ID.fullmatch(run['skill']) and run['state'] in SKILL_RUN_STATES):return False
    steps=run['steps']
    if not (isinstance(steps,list) and len(steps)<=SKILL_STEPS_LIMIT):return False
    ids=set();awaiting=[]
    for step in steps:
        if not (isinstance(step,dict) and {'id','state'}<=set(step)<=SKILL_STEP_KEYS):return False
        if not (isinstance(step['id'],str) and SKILL_STEP_ID.fullmatch(step['id']) and step['id'] not in ids and step['state'] in SKILL_STEP_STATES):return False
        if 'code' in step and not skill_code_ok(step['code']):return False
        # Decision steps only: the call's risk class (tool-proposal vocabulary) and the registry effect id.
        if 'risk' in step and step['risk'] not in SKILL_RISKS:return False
        # WP-15: the step's target (the capability or tool it acts on) when the manifest declares one.
        if 'target' in step and not text_ok(step['target'],128):return False
        if 'effect_id' in step and not (isinstance(step['effect_id'],str) and SKILL_EFFECT.fullmatch(step['effect_id'])):return False
        # The same closed effect object as a tool proposal (src/skills.rs StepView.effect); it must agree with effect_id.
        if 'effect' in step and not (valid_effect(step['effect']) and step.get('effect_id')==step['effect']['id']):return False
        ids.add(step['id'])
        if step['state']=='awaiting_approval':awaiting.append(step['id'])
    current=run['step']
    if current is not None and not (isinstance(current,str) and current in ids):return False
    if (run['state']=='awaiting_approval')!=bool(awaiting) or (awaiting and current not in awaiting):return False
    if 'outputs' in run and not (isinstance(run['outputs'],dict) and bounded_json(run['outputs'],SKILL_OUTPUTS_LIMIT)):return False
    return True
def valid_skill_history(entries):
    if not (isinstance(entries,list) and len(entries)<=SKILL_HISTORY_LIMIT):return False
    for entry in entries:
        # WP-15: history entries carry `at_ms` (unix ms); older records loaded from disk may not have it.
        if not (isinstance(entry,dict) and SKILL_HISTORY_KEYS<=set(entry)<=SKILL_HISTORY_KEYS|{'at_ms'} and run_id_ok(entry['run_id'])):return False
        if 'at_ms' in entry and not is_int(entry['at_ms']):return False
        if not (isinstance(entry['skill'],str) and SKILL_ID.fullmatch(entry['skill']) and isinstance(entry['version'],str) and SKILL_SEMVER.fullmatch(entry['version'])):return False
        if entry['state'] not in SKILL_RUN_STATES or (entry['step'] is not None and not (isinstance(entry['step'],str) and SKILL_STEP_ID.fullmatch(entry['step']))):return False
        codes=entry['codes']
        if not (isinstance(codes,list) and len(codes)<=SKILL_CODES_LIMIT and all(skill_code_ok(c) for c in codes)):return False
    return True
def valid_skill_import(preview):
    """Import preview (docs/S4.md D4). `unverified` is False only for a package whose publisher signature checked out (WP-5)."""
    if preview is None:return True
    if not (isinstance(preview,dict) and set(preview)==SKILL_IMPORT_KEYS):return False
    if not (isinstance(preview['name'],str) and SKILL_IMPORT_NAME.fullmatch(preview['name']) and isinstance(preview['id'],str) and SKILL_ID.fullmatch(preview['id'])):return False
    if not (isinstance(preview['version'],str) and SKILL_SEMVER.fullmatch(preview['version']) and text_ok(preview['publisher'],64)):return False
    if type(preview['unverified']) is not bool or type(preview['duplicate']) is not bool or type(preview['permissions_escalated']) is not bool:return False
    for key,limit,size in (('permissions_required',SKILL_CODES_LIMIT,64),('missing_deps',SKILL_DEPS_LIMIT,128),('permission_delta',SKILL_CODES_LIMIT,64)):
        value=preview[key]
        if not (isinstance(value,list) and len(value)<=limit and all(isinstance(v,str) and text_ok(v,size) for v in value)):return False
    findings=preview['findings']
    if not (isinstance(findings,list) and len(findings)<=SKILL_FINDINGS_LIMIT):return False
    return all(isinstance(f,dict) and set(f)<=SKILL_FINDING_KEYS and 'code' in f and skill_code_ok(f['code']) and ('field' not in f or text_ok(f['field'],64)) for f in findings)
def valid_skill_paths(paths):
    """skills.paths: exactly the import and export folders, absolute display paths (never read by the UI)."""
    return isinstance(paths,dict) and set(paths)=={'imports','exports'} and all(isinstance(paths[k],str) and paths[k].startswith('/') and len(paths[k])<=1024 and '\n' not in paths[k] for k in ('imports','exports'))
def valid_skill_export(item):
    """skills.last_export (WP-15): the package the last successful export wrote: id, version and absolute path."""
    return isinstance(item,dict) and set(item)=={'id','version','path'} and isinstance(item['id'],str) and SKILL_ID.fullmatch(item['id']) is not None and isinstance(item['version'],str) and SKILL_SEMVER.fullmatch(item['version']) is not None and isinstance(item['path'],str) and item['path'].startswith('/') and len(item['path'])<=1024 and '\n' not in item['path']
def valid_skill_index(index):
    """skills.index (SKILL-03): the listed GitHub index, or the refusal `error`. The UI never fetches `url`."""
    if not (isinstance(index,dict) and {'repository','entries'}<=set(index)<=frozenset({'repository','entries','error'})):return False
    if not (text_ok(index['repository'],128) and isinstance(index['entries'],list) and len(index['entries'])<=SKILL_ITEMS_LIMIT):return False
    if 'error' in index and not (isinstance(index['error'],str) and len(index['error'])<=64):return False
    for item in index['entries']:
        if not (isinstance(item,dict) and set(item)=={'name','version','sha256','url','signed','present'}):return False
        if not (isinstance(item['name'],str) and SKILL_IMPORT_NAME.fullmatch(item['name']) and isinstance(item['version'],str) and SKILL_SEMVER.fullmatch(item['version'])):return False
        if not (digest(item['sha256']) and isinstance(item['url'],str) and len(item['url'])<=512 and type(item['signed']) is bool and type(item['present']) is bool):return False
    return True
def valid_personal(block):
    """Snapshot block personal (WP-10a): `{"status":"unavailable"}` when the store did not open; otherwise the retention and one summary per area."""
    if not isinstance(block,dict):return False
    if block.get('status')=='unavailable':return set(block)=={'status'}
    return set(block)==set(PERSONAL_AREAS)|{'retention'} and block['retention'] in ('on','never') and all(isinstance(block[a],dict) for a in PERSONAL_AREAS)
def valid_skills(block):
    """Snapshot block skills: null, or revision, items (unique id+version), run, history and paths (docs/S4.md D2); import preview optional."""
    if block is None:return True
    if not (isinstance(block,dict) and {'revision','items','run','history'}<=set(block)<=frozenset({'revision','items','run','history','import','paths','last_export','index'})):return False
    if not is_int(block['revision']):return False
    if 'paths' in block and not valid_skill_paths(block['paths']):return False
    if 'last_export' in block and not valid_skill_export(block['last_export']):return False
    if 'index' in block and not valid_skill_index(block['index']):return False
    items=block['items']
    if not (isinstance(items,list) and len(items)<=SKILL_ITEMS_LIMIT and all(valid_skill_item(i) for i in items)):return False
    keys=[(i['id'],i['version']) for i in items]
    if len(set(keys))!=len(keys):return False
    return valid_skill_run(block['run']) and valid_skill_history(block['history']) and valid_skill_import(block.get('import'))
def valid_skill_draft(output):
    """Output of llm_engine.skill_draft (docs/S4.md D3): bounded PlainText fields; the draft itself is created by the Core, never enabled here."""
    if not (isinstance(output,dict) and set(output)<=SKILL_DRAFT_KEYS|SKILL_DRAFT_OPTIONAL and SKILL_DRAFT_KEYS<=set(output)):return False
    # D3: draft_put creates only draft, or revised in draft; an approved or enabled version is never the output of the LLM.
    if not (text_ok(output['draft_id'],64) and isinstance(output['version'],str) and SKILL_SEMVER.fullmatch(output['version']) and output['state'] in ('draft','revised')):return False
    for key,limit,size in (('requirements',SKILL_CODES_LIMIT,128),('ambiguities',SKILL_CODES_LIMIT,256)):
        value=output[key]
        if not (isinstance(value,list) and len(value)<=limit and all(isinstance(v,str) and plain_text(v,size) for v in value)):return False
    # preview: one {id, call} per manifest step (the plugin's _preview shape), both PlainText.
    preview=output['preview']
    if not (isinstance(preview,list) and len(preview)<=SKILL_STEPS_LIMIT and all(
            isinstance(step,dict) and set(step)=={'id','call'} and isinstance(step['id'],str) and SKILL_STEP_ID.fullmatch(step['id'])
            and plain_text(step['call'],128) for step in preview)):return False
    if 'diff' in output and not plain_text(output['diff'],2048):return False
    if 'validation' in output and output['validation']!={'ok':True}:return False
    return bounded_output(output)
# S5 connections: local rules for what the page sends and shows. Each rule mirrors docs/S5.md; the Core remains the authority.
def conn_id_ok(value):return isinstance(value,str) and CONN_ID.fullmatch(value) is not None
def conn_token_ok(value):
    """Home Assistant long-lived token: 16..256 printable ASCII characters, no spaces (the Core checks the same rule)."""
    return isinstance(value,str) and 16<=len(value)<=256 and value.isascii() and all(33<=ord(c)<=126 for c in value)
def conn_text_ok(value,limit):return plain_text(value,limit) and bool(value.strip())
def conn_label_problem(text):
    """Account name: trimmed, 1..64 UTF-8 bytes, no control characters. None means the name may be sent (the trimmed text is sent)."""
    try:
        if not isinstance(text,str) or not text.strip():return 'Nome da conta vazio'
        if utf8_len(text.strip())>CONN_LABEL_LIMIT:return 'Nome acima de 64 bytes'
        if any(unicodedata.category(c)=='Cc' for c in text.strip()):return 'Nome com quebra de linha ou controle não é aceito'
    except UnicodeError:return 'Nome inválido'
    return None
def conn_provider_problem(provider):return None if provider in CONN_PROVIDERS else CODE_MESSAGES['invalid_provider']
def conn_scope_list(value):
    return isinstance(value,list) and len(value)<=CONN_SCOPES_LIMIT and all(isinstance(s,str) and CONN_NAME.fullmatch(s) is not None for s in value) and len(set(value))==len(value)
def valid_conn_provider(provider):
    """Catalog entry (docs/S5.md E1): exact keys, unique scope and operation names, every operation names one of its provider's scopes."""
    if not (isinstance(provider,dict) and set(provider)=={'id','scopes','operations'} and provider['id'] in CONN_PROVIDERS):return False
    scopes=provider['scopes']
    if not (isinstance(scopes,list) and len(scopes)<=CONN_SCOPES_LIMIT):return False
    scope_ids=[]
    for scope in scopes:
        if not (isinstance(scope,dict) and set(scope)=={'id','label','access'} and isinstance(scope['id'],str) and CONN_NAME.fullmatch(scope['id']) and conn_text_ok(scope['label'],CONN_LABEL_LIMIT) and scope['access'] in CONN_ACCESS):return False
        scope_ids.append(scope['id'])
    if len(set(scope_ids))!=len(scope_ids):return False
    operations=provider['operations']
    if not (isinstance(operations,list) and len(operations)<=CONN_OPERATIONS_LIMIT):return False
    names=[]
    for operation in operations:
        if not (isinstance(operation,dict) and set(operation)=={'name','scope','risk','needs_args'} and isinstance(operation['name'],str) and CONN_NAME.fullmatch(operation['name']) and operation['scope'] in scope_ids and operation['risk'] in CONN_ACCESS and type(operation['needs_args']) is bool):return False
        names.append(operation['name'])
    return len(set(names))==len(names)
def valid_conn_item(item,catalog):
    """One account (docs/S5.md E1). Scopes are granted or pending, never both, and only among the provider's scopes. No secret field exists."""
    if not (isinstance(item,dict) and CONN_ITEM_REQUIRED<=set(item)<=CONN_ITEM_REQUIRED|CONN_ITEM_OPTIONAL):return False
    if not (conn_id_ok(item['id']) and item['provider'] in catalog and conn_text_ok(item['label'],CONN_LABEL_LIMIT) and item['status'] in CONN_STATUSES):return False
    scopes={scope['id'] for scope in catalog[item['provider']]['scopes']}
    granted=item['granted_scopes'];pending=item.get('pending_scopes',[])
    if not (conn_scope_list(granted) and conn_scope_list(pending) and set(granted)<=scopes and set(pending)<=scopes and not set(granted)&set(pending)):return False
    if 'account_ref' in item and not conn_text_ok(item['account_ref'],CONN_ACCOUNT_LIMIT):return False
    if 'user_code' in item and not conn_text_ok(item['user_code'],CONN_USER_CODE_LIMIT):return False
    if 'fake' in item and type(item['fake']) is not bool:return False
    if 'granted_at_ms' in item and not is_int(item['granted_at_ms']):return False
    return 'tools' not in item or (item['provider']=='mcp' and valid_conn_tools(item['tools']))
def valid_conn_tools(tools):
    """S5 E2.4: discovered MCP tools. Name, risk and trust state are fixed vocabularies; the description is server text and is shown only as PlainText, never used as an instruction."""
    if not (isinstance(tools,list) and 0<len(tools)<=CONN_TOOLS_LIMIT):return False
    names=[]
    for tool in tools:
        if not (isinstance(tool,dict) and CONN_TOOL_KEYS<=set(tool)<=CONN_TOOL_KEYS|{'reason'} and conn_id_ok(tool['name']) and tool['risk'] in CONN_TOOL_RISKS and tool['state'] in CONN_TOOL_STATES):return False
        if not (isinstance(tool['description'],str) and plain_text(tool['description'],CONN_TOOL_DESCRIPTION_LIMIT)):return False
        if 'reason' in tool and not (isinstance(tool['reason'],str) and SNAKE_CODE.fullmatch(tool['reason']) is not None):return False
        names.append(tool['name'])
    return len(set(names))==len(names)
def valid_conn_last_call(call):
    """Operation, outcome and code (docs/S5.md), plus the two fields a write or a rate limit needs: the proposal id of a
    card the user must decide (also listed in tool_proposals) and retry_after in seconds (Core clamps it to 1..60)."""
    if not (isinstance(call,dict) and {'operation','outcome'}<=set(call)<={'operation','outcome','code','retry_after','proposal_id','untrusted'}):return False
    if 'untrusted' in call and call['untrusted'] is not True:return False
    if not (isinstance(call['operation'],str) and CONN_NAME.fullmatch(call['operation']) and isinstance(call['outcome'],str) and SNAKE_CODE.fullmatch(call['outcome'])):return False
    if 'code' in call and not (isinstance(call['code'],str) and SNAKE_CODE.fullmatch(call['code']) is not None):return False
    if 'retry_after' in call and not is_int(call['retry_after'],0,3600):return False
    return 'proposal_id' not in call or (isinstance(call['proposal_id'],str) and PROPOSAL_ID.fullmatch(call['proposal_id']) is not None)
def valid_connections(block):
    """Snapshot block connections: null, or revision, providers (the fixed catalog), items (at most 8, unique ids) and an optional last_call."""
    if block is None:return True
    if not (isinstance(block,dict) and {'revision','items','providers'}<=set(block)<=CONN_BLOCK_KEYS and is_int(block['revision'])):return False
    if 'storage_error' in block and type(block['storage_error']) is not bool:return False
    providers=block['providers']
    if not (isinstance(providers,list) and len(providers)<=len(CONN_PROVIDERS)):return False
    catalog={}
    for provider in providers:
        if not valid_conn_provider(provider) or provider['id'] in catalog:return False
        catalog[provider['id']]=provider
    items=block['items']
    if not (isinstance(items,list) and len(items)<=CONN_ITEMS_LIMIT):return False
    ids=[]
    for item in items:
        if not valid_conn_item(item,catalog):return False
        ids.append(item['id'])
    if len(set(ids))!=len(ids):return False
    return 'last_call' not in block or valid_conn_last_call(block['last_call'])
def valid_registry(block):
    """Snapshot block registry: null, or revision, purposes (the fixed table: each with its candidates, and a chosen route that is an available candidate) and the purposes with the visual fallback allowed."""
    if block is None:return True
    if not (isinstance(block,dict) and set(block)==REG_BLOCK_KEYS and is_int(block['revision'])):return False
    purposes=block['purposes']
    if not (isinstance(purposes,list) and len(purposes)<=len(REG_PURPOSES)):return False
    ids=[]
    for item in purposes:
        if not (isinstance(item,dict) and {'id','label','candidates'}<=set(item)<={'id','label','candidates','route_chosen'} and item['id'] in REG_PURPOSES and conn_text_ok(item['label'],REG_LABEL_LIMIT)):return False
        candidates=item['candidates']
        if not (isinstance(candidates,list) and 0<len(candidates)<=len(REG_ROUTES)):return False
        routes=[]
        for candidate in candidates:
            if not (isinstance(candidate,dict) and set(candidate)==REG_CANDIDATE_KEYS and candidate['route'] in REG_ROUTES and candidate['status'] in REG_STATUSES and conn_text_ok(candidate['reason'],REG_REASON_LIMIT)):return False
            routes.append(candidate['route'])
        if len(set(routes))!=len(routes):return False
        if 'route_chosen' in item and not (item['route_chosen'] in routes and next(c for c in candidates if c['route']==item['route_chosen'])['status']=='available'):return False
        ids.append(item['id'])
    if len(set(ids))!=len(ids):return False
    allowed=block['visual_allowed']
    return isinstance(allowed,list) and len(allowed)<=len(REG_VISUAL_PURPOSES) and all(a in REG_VISUAL_PURPOSES for a in allowed) and len(set(allowed))==len(allowed)
# B5-B10 (docs/PENDENCIAS_IMPLEMENTACAO.md): package identity, developer tools and diagnostics. The Core decides; these checks only refuse what the Core would refuse, before a round trip.
PACKAGE_JSON_LIMIT=65536;PACKAGE_COMMIT=re.compile(r'[0-9a-f]{7,40}')
CAP_INPUT_LIMIT=2048;CAP_JSON_DEPTH=4;CAP_DEADLINE_MS=10000;CAP_SELFTEST_DEADLINE_MS=30000;CAP_RESULT_LIMIT=1024
HUB_REASON_LABELS={'ledger_missing':'registro de aprovações ausente','ledger_invalid':'registro de aprovações inválido'}
# Codes of a plugin capability invocation (capability_invoke ack or capability_result error). Others fall back to code_message.
CAPABILITY_MESSAGES={'unknown_capability':'Capacidade desconhecida ou sem plugin instalado','capability_unavailable':'Plugin desativado ou não está em execução',
    'invalid_input':'Entrada recusada: objeto JSON inválido ou acima do limite','busy':'Outra capacidade está em execução; aguarde','invoke_cancelled':'Invocação cancelada','cancelled':'Invocação cancelada',
    'capability_timeout':'Plugin não respondeu no prazo','timeout':'Tempo esgotado','plugin_error':'Plugin retornou erro interno','plugin_output_invalid':'Resposta do plugin fora do formato',
    'plugin_not_runnable':'Plugin não pode ser executado','plugin_cpu_exceeded':'Plugin passou do limite de processamento','response_too_large':'Resposta grande demais','permission_denied':'Permissão negada ao plugin'}
def clip_bytes(text,limit):
    """Text cut to at most `limit` UTF-8 bytes; never inside a character."""
    raw=text.encode('utf-8')
    return text if len(raw)<=limit else raw[:limit].decode('utf-8',errors='ignore')
def capability_code_message(code):return CAPABILITY_MESSAGES.get(code) or code_message(code)
def json_depth_ok(item,depth=0):
    """Same nesting rule as the Core (src/plugins.rs depth_ok): at most 4 container levels."""
    if isinstance(item,dict):return depth<CAP_JSON_DEPTH and all(json_depth_ok(v,depth+1) for v in item.values())
    if isinstance(item,list):return depth<CAP_JSON_DEPTH and all(json_depth_ok(v,depth+1) for v in item)
    return True
def capability_request(capability,text):
    """Developer JSON invocation (B7): (message, value, deadline_ms). message is None when the request may be sent.
    Refuses an identifier outside the grammar, more than 2 KiB of UTF-8, a value that is not an object, or nesting the Core refuses."""
    if not (isinstance(capability,str) and len(capability)<=64 and CAPABILITY_ID.fullmatch(capability)):return 'Identificador de capacidade inválido; use a forma plugin.capacidade.',None,0
    if not isinstance(text,str) or not text.strip():return 'Entrada vazia: escreva um objeto JSON entre chaves.',None,0
    if utf8_len(text)>CAP_INPUT_LIMIT:return 'Entrada acima de 2 KiB (2 048 bytes).',None,0
    try:value=json.loads(text,parse_constant=_no_constant)
    except (ValueError,RecursionError):return 'JSON inválido: use um objeto entre chaves.',None,0
    if not isinstance(value,dict):return 'A entrada deve ser um objeto JSON.',None,0
    if not json_depth_ok(value):return 'Objeto aninhado demais: no máximo 4 níveis.',None,0
    selftest=capability==MODEL_CAPABILITY and value.get('action')=='selftest'
    return None,value,CAP_SELFTEST_DEADLINE_MS if selftest else CAP_DEADLINE_MS
def package_info(app_dir):
    """Identity of the installed package (B5): PACKAGE.json at the package root, the parent of app/. A dev checkout has none, so installed is False."""
    absent={'installed':False,'version':'','commit':'','built':'','runtime':'','dirty':False}
    try:
        path=Path(app_dir).resolve().parent/'PACKAGE.json';info=path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size>PACKAGE_JSON_LIMIT:return absent
        obj=json.loads(path.read_bytes().decode('utf-8'))
    except (OSError,ValueError,RecursionError):return absent
    version=obj.get('version') if isinstance(obj,dict) else None
    if not (isinstance(version,str) and 0<len(version)<=64):return absent
    commit=obj.get('commit');runtime=obj.get('plugin_runtime')
    return {'installed':True,'version':version,'commit':commit[:8] if isinstance(commit,str) and PACKAGE_COMMIT.fullmatch(commit) else '',
            # PACKAGE.json has no build time; the file's own modification time is when the package was written.
            'built':datetime.datetime.fromtimestamp(info.st_mtime).strftime('%d/%m/%Y %H:%M'),
            'runtime':'Python embutido no pacote' if isinstance(runtime,dict) and runtime.get('runtime_dir') else 'não informado',
            'dirty':obj.get('dirty') is True}
def hub_storage(hub):
    """Catalog storage for Recuperação (B9). The hub view has no storage_error field, so the screen reports that as not informed."""
    if not hub:return {'state':'none','reason':'','orphans':None,'repository':'','catalogSha':''}
    quarantined=hub.get('status')=='quarantined'
    return {'state':'quarantined' if quarantined else 'verified','reason':HUB_REASON_LABELS.get(hub.get('reason'),'') if quarantined else '',
            'orphans':hub.get('orphans'),'repository':hub.get('repository') or '','catalogSha':(hub.get('catalog_sha256') or '')[:12]}
# op -> (result channel, done message or builder). One table drives every Core answer.
OPS={
    'preferences':('prefs',PREFS_DONE),'rollback_preferences':('prefs',PREFS_DONE),'select_wake':('prefs',PREFS_DONE),'select_wake_phrases':('prefs',PREFS_DONE),'wake_phrase_validate':('phrase',lambda _target:'Frase verificada'),
    'wake_phrase_add':('phrase','Frase salva: faça o teste antes de ativar'),'wake_phrase_remove':('phrase','Frase personalizada removida'),'wake_phrase_test':('phrase','Teste sintético iniciado: o resultado aparece na lista'),'feedback_preferences':('prefs',PREFS_DONE),
    'recover_configuration':('prefs','Configuração recuperada; reinício necessário'),
    'hub_abort':('hub','Importação cancelada'),
    'hub_approve':('hub',lambda target:f'Permissões aprovadas: {target}'),
    'hub_install':('hub','Plugin instalado (desativado)'),'hub_rollback':('hub','Versão revertida'),'hub_remove':('hub','Plugin removido'),
    'plugin_enable':('plugin','Plugin ativado'),'plugin_disable':('plugin','Plugin desativado'),'plugin_revoke':('plugin','Permissões revogadas; plugin desativado'),
    'capability_invoke':('plugin',None),'capability_cancel':('plugin','Cancelamento enviado'),
    'text':('text','Texto enviado'),'listen_start':('listen','Escuta iniciada: fale agora'),
    'secret_set':('llm','Chave salva pelo Core'),'secret_clear':('llm','Chave removida pelo Core'),'llm_configure':('llm','Configuração salva pelo Core'),
    'tool_decide':('tools','Decisão enviada ao Core'),
    'agent_start':('agent','Objetivo enviado ao Core'),'agent_abort':('agent','Aborto enviado ao Core'),
    # S4 skills: the Core's ack code is the result; validator reasons arrive as skill_invalid:<reason>.
    'skill_validate':('skills','Manifest válido; nada foi gravado'),'skill_save_draft':('skills','Rascunho salvo no Core'),'skill_dry_run':('skills','Simulação concluída; skill marcada como testada'),
    'skill_approve':('skills','Skill aprovada'),'skill_enable':('skills','Skill habilitada'),'skill_disable':('skills','Skill desabilitada'),'skill_rollback':('skills','Versão anterior restaurada'),'skill_remove':('skills','Skill removida'),
    'skill_run':('skills','Execução iniciada'),'skill_decide':('skills','Decisão enviada ao Core'),'skill_cancel':('skills','Cancelamento enviado'),
    'skill_export':('skills','Pacote exportado; publisher não verificado'),'skill_import':('skills','Pré-visualização de importação pronta'),'skill_import_confirm':('skills','Skill importada como rascunho; aprove antes de usar'),
}
PENDING={'listen_start':'Pedindo escuta ao Core…','agent_start':'Iniciando agente…','agent_abort':'Enviando aborto ao Core…','hub_approve':'Enviando aprovação ao Core','hub_abort':'Enviando cancelamento ao Core','hub_install':'Instalando no Core','hub_rollback':'Revertendo no Core','hub_remove':'Removendo no Core','plugin_enable':'Ativando plugin…','plugin_disable':'Desativando plugin…','plugin_revoke':'Revogando permissões…','capability_invoke':'Invocando capability…','capability_cancel':'Cancelando capability…','text':'Enviando texto ao Core',
    'secret_set':'Salvando chave no Core…','secret_clear':'Removendo chave no Core…','llm_configure':'Salvando configuração do motor…','tool_decide':'Enviando decisão ao Core…',
    'skill_validate':'Validando manifest no Core…','skill_save_draft':'Salvando rascunho no Core…','skill_dry_run':'Simulando skill no Core…','skill_approve':'Aprovando skill no Core…','skill_enable':'Habilitando skill no Core…','skill_disable':'Desabilitando skill no Core…','skill_rollback':'Revertendo versão no Core…','skill_remove':'Removendo skill no Core…','skill_run':'Iniciando skill no Core…','skill_decide':'Enviando decisão do passo ao Core…','skill_cancel':'Cancelando skill no Core…','skill_export':'Exportando pacote pelo Core…','skill_import':'Lendo pacote pelo Core…','skill_import_confirm':'Importando como rascunho pelo Core…'}
# S5 connection ops: the Core's ack code is the result; refusals of accounts and consent arrive as codes from CONN_MESSAGES.
CONN_OPS=frozenset({'connection_add','connection_connect','connection_consent','connection_refresh','connection_disconnect','connection_revoke','connection_revoke_scope','connection_remove','connection_call','connection_set_token','connection_trust_tools'})
OPS.update({
    'connection_add':('connections','Conta criada (desconectada)'),'connection_connect':('connections','Conexão iniciada: confirme o código no servidor e consinta os escopos'),
    'connection_consent':('connections','Escopos concedidos pelo usuário'),'connection_refresh':('connections','Atualização da conta solicitada'),
    'connection_disconnect':('connections','Conta desconectada; segredos apagados'),'connection_revoke':('connections','Acesso revogado no servidor'),
    'connection_remove':('connections','Conta removida'),'connection_call':('connections','Chamada enviada ao Core; resultado em Última chamada'),
    'connection_set_token':('connections','Token enviado ao Core para validação; o campo foi limpo'),
    'connection_trust_tools':('connections','Ferramentas confiadas pelo usuário; cada chamada ainda pede aprovação'),
    'connection_revoke_scope':('connections','Escopo revogado; chamadas que precisam dele pedem concessão de novo'),
    # C-wire: restart is answered by the Core, then the socket drops (see _restart_ack); the plugin clear answers on the plugin channel.
    'core_restart':('core','Reinício pedido ao Core'),'plugin_settings_clear':('plugin','Dados do plugin apagados'),'virtual_wake':('wake','Wake de teste enviado ao Core'),
    'registry_plan':('registry','Rota planejada; nada foi executado'),'registry_allow_visual':('registry','Fallback visual atualizado pelo Core'),
})
PENDING.update({
    'connection_add':'Criando conta no Core…','connection_connect':'Iniciando conexão no Core…','connection_consent':'Enviando consentimento ao Core…','connection_refresh':'Atualizando conta no Core…',
    'connection_disconnect':'Desconectando conta no Core…','connection_revoke':'Revogando acesso no Core…','connection_remove':'Removendo conta no Core…','connection_call':'Chamando operação pelo Core…',
    'connection_set_token':'Validando token no Core…','connection_trust_tools':'Confiando nas ferramentas no Core…','connection_revoke_scope':'Revogando escopo no Core…',
    'core_restart':'Pedindo reinício ao Core…','plugin_settings_clear':'Apagando dados do plugin…','virtual_wake':'Enviando wake de teste…',
    'registry_plan':'Planejando rota no Core…','registry_allow_visual':'Atualizando fallback visual no Core…',
})
# B16 (docs/A6-live-audio.md): device list, and the Core defaults restore (the Core keeps config.json.bak).
OPS.update({
    'audio_devices':('audio','Lista de dispositivos atualizada'),
    'preferences_restore_defaults':('prefs','Padrões do Core restaurados; cópia anterior em config.json.bak'),
})
PENDING.update({'audio_devices':'Consultando dispositivos no Core…','preferences_restore_defaults':'Restaurando padrões do Core…'})
# A9 probe of one input: 3 s of the microphone; the message says so, and the result comes in audio.probe.
OPS.update({'audio_probe':('audio','Teste iniciado: o microfone será usado por 3 segundos')})
PENDING.update({'audio_probe':'Iniciando o teste de 3 s no Core…'})
# A13 microphone assistant: 2 s from each listed input, one at a time; nothing is saved and the system default is not changed.
OPS.update({'audio_recommend_input':('audio','Verificação dos microfones iniciada: 2 s em cada entrada; nada é salvo')})
PENDING.update({'audio_recommend_input':'Verificando os microfones no Core…'})
CODE_MESSAGES.setdefault('audio_tool_failed','A ferramenta de áudio falhou; tente de novo')
CODE_MESSAGES.setdefault('invalid_device','Microfone não listado pelo sistema: atualize a lista e escolha de novo')
# A6 consent for the live microphone (docs/A6-live-audio.md): one op, read back from preferences.live_audio and audio.live.restart_required.
OPS.update({'live_audio_preference':('prefs','Escuta do microfone salva no Core; reinicie o Core para aplicar')})
PENDING.update({'live_audio_preference':'Salvando a escuta do microfone no Core…'})
# A11 consent for host actions (docs/A11-real-actions-test.md): applies at once; busy while a voice session or a command runs.
OPS.update({'real_actions_preference':('prefs','Ações no computador salvas no Core')})
PENDING.update({'real_actions_preference':'Salvando as ações no computador no Core…'})
# Idiomas (Frente 2): one op for the STT list and the TTS language/voice; applied at the next Core start.
OPS.update({'language_preference':('prefs','Idiomas salvos no Core; reinicie o Core para aplicar')})
PENDING.update({'language_preference':'Salvando idiomas no Core…'})
# CFG-03: verifies the packaged models of one bundled language (hash per file) and activates them in the Core state. No download.
OPS.update({'language_install':('prefs','Modelos verificados pelo hash e ativados no Core; a escolha vale na próxima fala')})
PENDING.update({'language_install':'Verificando os modelos do idioma no pacote…'})
# CFG-04 retention: applies at once; `never` also removes the audit trail (purge on commit). DIAG-02 developer mode: a plain switch.
OPS.update({'history_retention_preference':('prefs','Retenção do histórico salva no Core; vale já')})
PENDING.update({'history_retention_preference':'Salvando a retenção do histórico no Core…'})
OPS.update({'developer_mode_preference':('prefs','Modo desenvolvedor salvo no Core')})
PENDING.update({'developer_mode_preference':'Salvando o modo desenvolvedor no Core…'})
# DIAG-04 (docs/ui-spec/50-diagnostico.md §3.4): codes the Core emits that had no Portuguese text.
CODE_MESSAGES.update({'hub_storage_error':'Falha ao gravar o registro do catálogo.','plugin_storage_error':'Falha ao gravar o registro dos plugins.','hub_import_timeout':'Importação expirou antes de terminar.'})
# Snapshot keys grouped into sections; each section has its own NOTIFY signal so QML lists keep their delegates.
# 'partial' and the chat state share chatChanged: both move with one streamed chunk.
SECTION_SIGNALS={'personal':'personalChanged','entries':'hubEntriesChanged','installed':'hubInstalledChanged','hub':'hubChanged','plugins':'pluginsChanged','capability':'capabilityChanged','preferences':'preferencesChanged','pack':'packChanged','session':'sessionChanged','llm':'llmChanged','partial':'chatChanged','tools':'toolsChanged','agent':'agentChanged','skills':'skillsChanged','connections':'connectionsChanged','registry':'registryChanged','events':'eventsChanged','audio':'audioChanged','languages':'languagesChanged','actions':'actionsChanged'}
SNAPSHOT_SECTION_KEYS=('hub','plugins','capability_result','preferences','base_pack','llm','partial','tool_proposals','agent','skills','connections','registry','events','audio','languages','actions','personal','personal_reply')

class Bridge(QObject):
    changed=Signal()
    hubEntriesChanged=Signal();hubInstalledChanged=Signal();hubChanged=Signal();pluginsChanged=Signal();capabilityChanged=Signal()
    preferencesChanged=Signal();packChanged=Signal();sessionChanged=Signal();eventsChanged=Signal();audioChanged=Signal();languagesChanged=Signal();actionsChanged=Signal()
    llmChanged=Signal();toolsChanged=Signal();chatChanged=Signal();modelsCatalogChanged=Signal();modelsStateChanged=Signal();agentChanged=Signal()
    prefsSettled=Signal(str);textSent=Signal(str);chatSent=Signal(str);perceptionChanged=Signal();skillsChanged=Signal();connectionsChanged=Signal();registryChanged=Signal();personalChanged=Signal()
    def __init__(self,root):
        super().__init__();self.root=Path(root);self.snapshot={};self.buffer=bytearray();self.pending=None;self.pending_op=None;self.cancel_id=None;self.text_request=None;self.text_inflight=None;self.preferences_request=None;self.results={'prefs':'','hub':'','plugin':'','text':'','llm':'','chat':'','tools':'','agent':'','perception':'','skills':'','connections':'','registry':'','core':'','wake':'','audio':''};self.hub_target='';self.capability_pending=False;self.plugin_capability='';self._package=package_info(Path(__file__).resolve().parent);self.online=False;self.error='Core offline';self._backoff=500;self._sequence=-1;self._counter=0;self._prefix=uuid.uuid4().hex[:16]
        # C1 chat/tool state. Messages live here (window-level state, not Core snapshot). No key is ever stored here.
        self.chat_messages=[];self.chat_request=None;self.chat_inflight=None;self.chat_state='idle';self.chat_cancel_pending=False;self.pending_chat=False;self.pending_chat_cancel=False;self.tool_inflight=None
        # B12: the Core code of the last failed chat turn (refusal of the invoke, or the plugin's error). '' when the last turn did not fail with a known code.
        self.chat_last_error=''
        # C2 model manager. models_req=(kind,op) awaits the Core ack; models_wait=kind awaits the capability result; models_flow is the useModel state machine.
        # models_marker is the response count when the awaited capability invoke was acknowledged; only a later response can carry its answer.
        self.models_req=None;self.models_wait=None;self.models_marker=None;self.models_flow=None;self.models_recover=False;self.models_want_list=False;self.models_data=None;self.models_described=None;self.models_message=''
        self._responses=0
        # WP-10a: area of the personal request in flight, and the last reply ({area, code, reply}) shown by the pages.
        self.personal_area='';self.personal_reply={}
        # DIAG-05: send time of the request awaiting an answer, the last LATENCY_SAMPLES round trips, the Core pid and the per-pid CPU readings.
        self._sent_at=None;self._sent_op=None;self._latency=[];self._core_pid=None;self._cpu_prev={};self._sampled_at=None;self.resource_view={}
        # Paging (list is paginated per tab): models_page_req=(tab,offset) awaits the page answer; models_page[tab]={'total','next'} is where the next page starts.
        self.models_page_req=None;self.models_page=fresh_model_pages()
        # C4 perception: one allowlisted capability at a time. perception_req awaits the Core ack; perception_inflight awaits the plugin result; perception_before is the capability_result seen at ack, so a stale answer is never taken for the new one.
        self.perception_req=None;self.perception_inflight=None;self.perception_before=None;self.perception_indicators={'mic':None,'camera':None}
        self.perception_status={};self.perception_status_queue=[]
        # WP-17 push-to-talk: the global shortcut (shortcut_global plugin) starts a capture. Off until the owner turns it on.
        self.ptt={'enabled':False,'trigger':'CTRL+ALT+G','state':'off','message':''};self.ptt_timer=QTimer(self);self.ptt_timer.setInterval(900);self.ptt_timer.timeout.connect(self._ptt_tick)
        # S4 skills: skill_req awaits the Core ack of the LLM draft; skill_inflight awaits the plugin result; skill_before is the capability_result seen at ack (same rule as perception).
        self.skill_req=None;self.skill_inflight=None;self.skill_before=None;self.skill_draft={}
        # WP-4 Hub import: the open payload file and the step in flight (see importHubPayload). None when no upload runs.
        self.hub_upload=None
        # Core restart: waiting from the ack until the first snapshot of the new Core; the timer turns a silent Core into a message.
        self.restart_state=None;self.restart_dropped=False;self.restart_timer=QTimer(self);self.restart_timer.setSingleShot(True);self.restart_timer.setInterval(RESTART_TIMEOUT_MS);self.restart_timer.timeout.connect(self._restart_timeout)
        self.socket=QLocalSocket(self);self.socket.connected.connect(self._connected);self.socket.readyRead.connect(self._read);self.socket.disconnected.connect(self._offline);self.socket.errorOccurred.connect(self._offline)
        self.poll=QTimer(self);self.poll.setInterval(1000);self.poll.timeout.connect(self.refresh)
        self.retry=QTimer(self);self.retry.setSingleShot(True);self.retry.timeout.connect(self.connect_core)
        self.timeout=QTimer(self);self.timeout.setSingleShot(True);self.timeout.setInterval(2000);self.timeout.timeout.connect(self._offline)
        self.connect_core()
    def _safe_path(self):
        for path,kind in [(self.root,stat.S_ISDIR),(self.root/'core.sock',stat.S_ISSOCK)]:
            s=path.lstat()
            if s.st_uid!=os.getuid() or not kind(s.st_mode) or s.st_mode&0o077:raise ValueError('private IPC path required')
    @Slot()
    def connect_core(self):
        if self.socket.state()!=QLocalSocket.LocalSocketState.UnconnectedState:return
        try:self._safe_path()
        except (OSError,ValueError):self._offline();return
        self.socket.connectToServer(str(self.root/'core.sock'))
    def _connected(self):
        self.retry.stop();self.error='';self._backoff=500;self._core_pid=_peer_pid(self.socket);self.refresh()
    def _offline(self,*args):
        old=self.snapshot
        if self.restart_state is not None:self.restart_dropped=True
        self.online=False;self.error='Core offline — reconnecting';self.snapshot={};self.pending=None;self.pending_op=None;self.cancel_id=None;self.text_request=None;self.text_inflight=None;self.preferences_request=None;self.results=dict.fromkeys(self.results,'');self.hub_target='';self.capability_pending=False;self.buffer.clear();self._sequence=-1;self.poll.stop();self.timeout.stop()
        # DIAG-05: a new Core starts with empty latency and resource samples.
        self._sent_at=None;self._latency=[];self._core_pid=None;self._cpu_prev={};self._sampled_at=None;self.resource_view={}
        if self.socket.state()!=QLocalSocket.LocalSocketState.UnconnectedState:self.socket.abort()
        # After abort(): it re-enters _offline synchronously, which clears results; the chat message must survive that.
        self._chat_reset();self._models_reset();self._perception_reset();self._skill_reset()
        self._hub_upload_drop()
        self._publish(old,self.snapshot)
        self.changed.emit()
        if not self.retry.isActive():self.retry.start(self._backoff);self._backoff=min(5000,self._backoff*2)
    def _request(self,op,**kw):
        if self.pending or self.socket.state()!=QLocalSocket.LocalSocketState.ConnectedState or (not self.online and op!='snapshot'):return False
        self._counter+=1;rid=f'{self._prefix}_{self._counter}';self.pending=rid;self.pending_op=op
        if op=='hub_approve':self.hub_target=kw['plugin_id']
        if op=='text':self.text_inflight=kw['raw']
        self._sent_at=time.monotonic();self._sent_op=op
        self.socket.write((json.dumps({'version':1,'request_id':rid,'op':op,**kw})+'\n').encode());self.timeout.start();return True
    @Slot()
    def refresh(self):self._request('snapshot')
    def _sections(self,s):
        hub=s.get('hub') or {}
        return {'entries':hub.get('entries'),'installed':hub.get('installed'),'hub':{k:v for k,v in hub.items() if k not in('entries','installed')},
                'plugins':s.get('plugins'),'capability':s.get('capability_result'),'preferences':s.get('preferences'),'pack':s.get('base_pack'),
                'llm':s.get('llm'),'partial':s.get('partial'),'tools':s.get('tool_proposals'),'agent':s.get('agent'),'skills':s.get('skills'),'connections':s.get('connections'),'registry':s.get('registry'),'events':s.get('events'),'audio':s.get('audio'),'languages':s.get('languages'),'actions':s.get('actions'),'personal':s.get('personal'),
                'session':{k:v for k,v in s.items() if k not in SNAPSHOT_SECTION_KEYS}}
    def _publish(self,old,new):
        before,after=self._sections(old),self._sections(new)
        for name,signal in SECTION_SIGNALS.items():
            if before[name]!=after[name]:getattr(self,signal).emit()
    def _settle(self,op,data):
        """Map the Core answer of a finished request to one UI message through the OPS table."""
        code=data.get('code','invalid_message')
        if op=='core_restart':return self._restart_ack(code)
        if op in PERSONAL_OPS:self._personal_settled(op,code,data);return
        # B16: the Core refuses the defaults restore with busy during a voice session; the message says so and the toast follows.
        if op=='preferences_restore_defaults' and code=='busy':
            self.results['prefs']=RESTORE_BUSY_TEXT;self.prefsSettled.emit(RESTORE_BUSY_TEXT);return
        # WP-4 backup copy: the Core writes config.json.bak before it resets anything; a failure there (or in the commit) keeps the values.
        if op=='preferences_restore_defaults' and code=='preferences_storage_error':
            self.results['prefs']=RESTORE_BACKUP_TEXT;self.prefsSettled.emit(RESTORE_BACKUP_TEXT);return
        if self.models_req is not None and self.models_req[1]==op:
            kind=self.models_req[0];self.models_req=None;self._models_ack(kind,code);return
        if op=='capability_invoke' and self.pending_chat:
            self.pending_chat=False;self._chat_accepted(code);return
        if op=='capability_cancel' and self.pending_chat_cancel:
            self.pending_chat_cancel=False;self.results['chat']='Cancelamento enviado' if code=='ok' else code_message(code);self.chatChanged.emit()
        if op=='capability_invoke' and self.skill_req is not None:
            req,self.skill_req=self.skill_req,None
            if code=='ok':self.skill_inflight=req;self.skill_before=SKILL_ARM;self.results['skills']=PENDING_SKILL_DRAFT
            else:self.results['skills']=code_message(code)
            self._skills_touch();return
        if op=='capability_invoke' and self.perception_req is not None:
            req,self.perception_req=self.perception_req,None
            if code=='ok':self.perception_inflight=req;self.perception_before=PERCEPTION_ARM;self.results['perception']=PENDING['capability_invoke'] if not req.get('silent') else self.results['perception']
            elif req.get('silent'):self._ptt_observe(req,{'ok':False,'error':code})
            else:self.results['perception']=perception_code_message(code)
            self._perception_touch();return
        if op=='tool_decide':self.tool_inflight=None
        if op not in OPS:return
        channel,done=OPS[op]
        if op=='text':
            sent,self.text_inflight=self.text_inflight,None
            self.results['text']=done if code=='ok' else code_message(code)
            # N-5: a turn sent during a voice session is queued by the Core (`queued`); it counts as sent.
            if code in ('ok','queued'):self.textSent.emit(sent or '')
            return
        if code!='ok':
            self.results[channel]=capability_code_message(code) if op=='capability_invoke' else real_action_code_message(op,code)
            if op=='capability_invoke':self.capability_pending=False
        elif op=='capability_invoke':self.capability_pending=True;self.results[channel]=PENDING[op]
        else:self.results[channel]=done(self.hub_target) if callable(done) else done
        # The shell shows prefsSettled as a toast: the listen answer (HUD-03) reaches the user the same way.
        if channel=='prefs':self.prefsSettled.emit(self.results['prefs'])
        if channel=='listen':self.prefsSettled.emit(self.results['listen'])
    def _apply(self,data,settled=False):
        """Publish one validated snapshot; per-section signals fire only for sections that changed."""
        # Python retains u64 precisely; QML never receives numeric session IDs.
        data['session_id']=str(data['session_id']) if data.get('session_id') is not None else ''
        old=self.snapshot
        if data!=old:self.snapshot=data;self._publish(old,data)
        if data!=old or settled:self.changed.emit();self.perceptionChanged.emit()
    def _read(self):
        # Never read more than the 64 KiB cap plus one byte; the cap check below drops the Core.
        self.buffer.extend(bytes(self.socket.read(65537-len(self.buffer))))
        if len(self.buffer)>65536:self._offline();return
        while b'\n' in self.buffer:
            line,_,tail=self.buffer.partition(b'\n');self.buffer=bytearray(tail)
            try:
                data=json.loads(bytes(line))
                validate_snapshot(data,self.pending,self._sequence)
            except Exception:self._offline();return
            sid=data['session_id'];self._sequence=data['sequence'];self._responses+=1
            pending_op=self.pending_op
            # DIAG-05: the round trip of the request this answer settles (measured here, content-free).
            if self._sent_at is not None:
                self._latency.append((self._sent_op,round((time.monotonic()-self._sent_at)*1000)));del self._latency[:-LATENCY_SAMPLES];self._sent_at=None
            self.timeout.stop();self.pending=None;self.pending_op=None;self.online=True;self.poll.start()
            data.pop('request_id',None)
            self._settle(pending_op,data)
            # The invocation result arrives later in the snapshot; the Core clears it on every new invoke.
            if self.capability_pending and data.get('capability_result'):self.capability_pending=False;self.results['plugin']=''
            self._apply(data,settled=pending_op in OPS)
            # The ack itself is a snapshot of the old Core; only a snapshot after the socket dropped comes from the restarted one.
            if self.restart_dropped and self.restart_state is not None:self._restart_done()
            self._chat_observe();self._models_observe();self._perception_observe();self._skill_observe()
            self._maybe_sample()
            self.poll.setInterval(150 if sid is not None else 1000)
            if self.cancel_id is not None:
                old_id=self.cancel_id;self.cancel_id=None;self._request('cancel',session_id=int(old_id))
            elif self.chat_cancel_pending and self.chat_inflight is not None:
                self.chat_cancel_pending=False;self.pending_chat_cancel=self._request('capability_cancel',capability=self.chat_inflight['capability'])
            elif self.preferences_request is not None:
                op,kw=self.preferences_request;self.preferences_request=None;self._request(op,**kw)
            elif self.text_request is not None:
                text,self.text_request=self.text_request,None
                problem=text_problem(text) or (None if self._text_ready() else 'Entrada de texto indisponível agora')
                if problem is None:self._request('text',raw=text)
                else:self.results['text']=problem;self.changed.emit()
            # Model steps go last: one request in flight at a time, so they never displace a queued request above.
            if not self.pending:self._models_next()
            # WP-4: the Hub upload goes last too; it waits while another request holds the socket, and the next answer resumes it.
            self._hub_upload_pump(pending_op,data)
    @Slot()
    def cancel(self):
        if self.online and self.sessionId:
            self.text_request=None
            if self.pending:self.cancel_id=self.sessionId
            else:self._request('cancel',session_id=int(self.sessionId))
    # N-5: the Core queues a typed turn during a voice session, so the input stays open while one runs.
    def _text_ready(self):return self.online and bool(self.snapshot.get('text_input_available'))
    @Slot(str)
    def submitText(self,text):
        problem=text_problem(text)
        if problem is None and not self._text_ready():problem='Entrada de texto indisponível agora'
        if problem is None and self.text_request is not None:problem='Aguarde o envio anterior'
        if problem is not None:self.results['text']=problem;self.changed.emit();return
        if self.pending:self.text_request=text;self.results['text']='Texto na fila para envio'
        else:self._request('text',raw=text);self.results['text']=PENDING['text']
        self.changed.emit()
    # ---- C1 LLM engine: chat turns, tool decisions and Motor LLM settings. The Core decides; this only forwards bounded requests.
    def _touch(self):self.changed.emit();self.chatChanged.emit()
    def _refuse(self,channel,message):self.results[channel]=message;self._touch()
    def _send(self,channel,op,**kw):
        """One Core request for a C1 channel. Refused while another request is in flight; never queued, so no key waits in memory."""
        if self.pending:self.results[channel]=CODE_MESSAGES['busy']
        elif not self._request(op,**kw):self.results[channel]='Core indisponível'
        else:self.results[channel]=PENDING[op]
        self._touch();return self.pending_op==op and self.results[channel]==PENDING[op]
    def _chat_target(self):
        for item in (self.snapshot.get('plugins') or {}).get('items',[]):
            capability=next((c for c in item['capabilities'] if c.endswith(CHAT_CAPABILITY_SUFFIX)),None)
            if item['state']=='running' and capability:return {'plugin_id':item['plugin_id'],'capability':capability}
        return None
    def _chat_reset(self):
        if self.chat_inflight is not None or self.chat_request is not None:self.chat_state='error';self.results['chat']='Core indisponível; resposta interrompida'
        self.chat_inflight=None;self.chat_request=None;self.chat_cancel_pending=False;self.pending_chat=False;self.pending_chat_cancel=False;self.tool_inflight=None
        self.chatChanged.emit()
    # N-5: the chat and the agent stay on screen during a voice session (history and state are visible); only the input is
    # held back by chatInputAvailable. This used to depend on preferencesAvailable, which hides everything while a session runs.
    @Property(bool,notify=changed)
    def chatAvailable(self):return self.online and 'plugins' in self.snapshot and self._chat_target() is not None
    @Property(bool,notify=changed)
    def chatInputAvailable(self):return self.chatAvailable
    @Property(str,notify=changed)
    def chatBlockedText(self):return 'Durante a voz, o texto entra na fila e é enviado quando a sessão terminar.' if self.sessionId else ''
    @Slot(str,result=str)
    def chatTextProblem(self,text):return chat_problem(text) or ''
    # B13: the command line rule (1..512 UTF-8 bytes, no control characters). '' means the text may be sent.
    @Slot(str,result=str)
    def commandProblem(self,text):return text_problem(text) or ''
    @Property(str,notify=chatChanged)
    def chatLastErrorCode(self):return self.chat_last_error
    # B12: the banner for the last failed chat turn: {'code','text','action'}, or {} when there is nothing actionable.
    @Property('QVariantMap',notify=chatChanged)
    def chatErrorBanner(self):
        text=CHAT_ERROR_BANNERS.get(self.chat_last_error)
        return {'code':self.chat_last_error,'text':text,'action':CHAT_ERROR_ACTION} if text else {}
    @Slot(str,result=str)
    def codeMessage(self,code):return code_message(code) if isinstance(code,str) and SNAKE_CODE.fullmatch(code) else ''
    # Write-only clipboard for the copyable terminal commands (Diagnóstico > Recuperação). Bounded; never reads the clipboard.
    @Slot(str,result=bool)
    def copyText(self,text):
        if not isinstance(text,str) or not 0<len(text)<=512 or not text.isprintable():return False
        clipboard=QGuiApplication.clipboard()
        if clipboard is None:return False
        clipboard.setText(text);return True
    @Slot(str,result=str)
    def providerLabel(self,provider):return display_provider(provider)
    @Slot(str,result=str)
    def permissionLabel(self,permission):return display_permission(permission)
    @Slot('QVariantMap',result=str)
    def effectText(self,effect):return display_effect(effect)
    @Slot(str,result=str)
    def riskText(self,risk):return display_risk(risk)
    @Property('QVariantList',notify=eventsChanged)
    def events(self):return [{k:e.get(k) for k in ('sequence','at_ms','kind','origin','outcome')} for e in self.snapshot.get('events') or []]
    @Property('QVariantList',notify=changed)
    def grants(self):return grant_rows(self.snapshot)
    @Property(int,notify=changed)
    def pendingCount(self):return pending_count(self.snapshot)
    @Property(str,notify=chatChanged)
    def chatState(self):
        if self.chat_inflight is not None:return 'streaming' if self.snapshot.get('partial') else 'waiting'
        return self.chat_state
    @Property(str,notify=chatChanged)
    def chatStateLabel(self):return CHAT_STATE_LABELS.get(self.chatState,'Em espera')
    @Property('QVariantList',notify=chatChanged)
    def chatMessages(self):return [dict(m) for m in self.chat_messages]
    @Property(str,notify=chatChanged)
    def chatPartial(self):return self.snapshot.get('partial') or ''
    @Property(str,notify=chatChanged)
    def chatResult(self):return self.results['chat']
    @Slot(str)
    def sendChat(self,text):
        target=self._chat_target();problem=chat_problem(text)
        if problem is None and (target is None or not self.pluginsAvailable):problem='Motor LLM indisponível'
        if problem is None and (self.chat_inflight is not None or self.chat_request is not None):problem='Aguarde a resposta anterior'
        if problem is None and self.pending:problem=CODE_MESSAGES['busy']
        if problem is None and self._models_busy_now():problem='Aguarde o gerenciador de modelos'
        messages=chat_messages_for(self.chat_messages,text) if problem is None else None
        if problem is None and messages is None:problem='Mensagem grande demais para o contexto do motor'
        if problem is not None:self.results['chat']=problem;self.chatChanged.emit();return
        self.chat_request={'text':text,'target':target};self.pending_chat=True;self.chat_last_error=''
        input_={'messages':messages,'tools':True,'max_tokens':CHAT_MAX_TOKENS}
        if self._request('capability_invoke',capability=target['capability'],input=input_,deadline_ms=CHAT_DEADLINE_MS):self.results['chat']=PENDING['capability_invoke']
        else:self.chat_request=None;self.pending_chat=False;self.results['chat']='Core indisponível'
        self.chatChanged.emit()
    def _chat_accepted(self,code):
        request,self.chat_request=self.chat_request,None
        if code!='ok':self.chat_last_error=code;self.results['chat']=code_message(code);self.chatChanged.emit();return
        self.chat_last_error=''
        self.chat_messages.append({'role':'user','text':request['text'],'state':'done'});del self.chat_messages[:-CHAT_MESSAGES_KEPT]
        self.chat_inflight=request['target'];self.chat_state='waiting';self.results['chat']=''
        self.chatSent.emit(request['text']);self.chatChanged.emit()
    def _chat_observe(self):
        """Finishes the in-flight turn exactly once, when the Core publishes the matching capability_result."""
        if self.chat_inflight is None:return
        result=self.snapshot.get('capability_result')
        if not result or result['capability']!=self.chat_inflight['capability'] or result['plugin_id']!=self.chat_inflight['plugin_id']:return
        self.chat_inflight=None;self.chat_cancel_pending=False;partial=result.get('partial') or ''
        self.chat_last_error=''
        if result['ok']:
            text=result['output'].get('text');self.chat_messages.append({'role':'assistant','text':text if isinstance(text,str) else '','state':'done'})
            self.chat_state='done';self.results['chat']=''
        else:
            state='cancelled' if result['error'] in CANCEL_CODES else 'error';self.chat_state=state
            if state=='error':self.chat_last_error=result['error'] if isinstance(result['error'],str) else ''
            if partial:self.chat_messages.append({'role':'assistant','text':partial,'state':state})
            self.results['chat']='' if state=='cancelled' else (f"Erro HTTP {result[HTTP_STATUS_KEY]}" if result['error']=='http_error' and HTTP_STATUS_KEY in result else code_message(result['error']))
        del self.chat_messages[:-CHAT_MESSAGES_KEPT];self.chatChanged.emit()
    @Slot()
    def cancelChat(self):
        if self.chat_inflight is None:return
        if self.pending:self.chat_cancel_pending=True;self.results['chat']='Cancelamento na fila'
        elif self._request('capability_cancel',capability=self.chat_inflight['capability']):self.pending_chat_cancel=True;self.results['chat']=PENDING['capability_cancel']
        else:self.results['chat']='Core indisponível'
        self.chatChanged.emit()
    @Property('QVariantList',notify=toolsChanged)
    def toolProposals(self):return list(self.snapshot.get('tool_proposals') or [])
    @Property(str,notify=changed)
    def toolResult(self):return self.results['tools']
    @Slot(str,str)
    def decideTool(self,proposal,decision):
        # Only the user's click decides; a second click on the same proposal while it is in flight is dropped.
        if decision not in ('authorize','deny') or self.tool_inflight==proposal:return
        state=next((p['state'] for p in self.snapshot.get('tool_proposals') or [] if p['proposal_id']==proposal),None)
        if state is None:return self._refuse('tools',CODE_MESSAGES['unknown_proposal'])
        if state!='pending':return self._refuse('tools',CODE_MESSAGES['already_decided'])
        self.tool_inflight=proposal
        if not self._send('tools','tool_decide',proposal_id=proposal,decision=decision):self.tool_inflight=None
    # ---- C3 agent runtime: one run at a time, decided by the Core. The bridge refuses what it can see is impossible, forwards bounded requests, and shows the snapshot 'agent' block.
    def _agent_run(self):return self.snapshot.get('agent')
    def _agent_active(self):
        run=self._agent_run();return run is not None and run['state'] not in AGENT_TERMINAL
    @Slot(str)
    def agentStart(self,goal):
        problem=agent_goal_problem(goal)
        if problem is None and self._chat_target() is None:problem=CODE_MESSAGES['llm_unavailable']
        if problem is None and self._agent_active():problem=CODE_MESSAGES['agent_busy']
        if problem is None and (self.chat_inflight is not None or self.chat_request is not None or self.pending_chat):problem='Aguarde a conversa terminar'
        if problem is None and self._models_busy_now():problem='Aguarde o gerenciador de modelos'
        if problem is not None:return self._refuse('agent',problem)
        self._send('agent','agent_start',goal=goal.strip())
    @Slot()
    def agentAbort(self):
        run=self._agent_run()
        if run is None or not self._agent_active():return self._refuse('agent',CODE_MESSAGES['unknown_run'])
        self._send('agent','agent_abort',run_id=run['run_id'])
    @Slot(str,result=str)
    def agentGoalProblem(self,goal):return agent_goal_problem(goal) or ''
    @Property(str,notify=agentChanged)
    def agentState(self):return (self._agent_run() or {}).get('state','')
    @Property(bool,notify=agentChanged)
    def agentActive(self):return self._agent_active()
    @Property(str,notify=agentChanged)
    def agentStateLabel(self):
        run=self._agent_run()
        if run is None:return ''
        label=AGENT_STATE_LABELS[run['state']]
        return f"{label} · {code_message(run['error'])}" if 'error' in run else label
    @Property('QVariantList',notify=agentChanged)
    def agentSteps(self):return [dict(step) for step in (self._agent_run() or {}).get('steps',[])]
    @Property(str,notify=agentChanged)
    def agentAnswer(self):return (self._agent_run() or {}).get('answer') or ''
    @Property('QVariantMap',notify=agentChanged)
    def agentBudget(self):
        """Budget line of Assistente > Agente: steps, clocks (ms) and tokens of the live run; {} without a run. Clocks fall back to started_ms_ago when the Core is older."""
        run=self._agent_run()
        if run is None:return {}
        tokens=run.get('budget') or {}
        return {'steps':run['step'],'max_steps':run['max_steps'],'elapsed_ms':run.get('elapsed_ms',run['started_ms_ago']),'max_run_ms':run.get('max_run_ms'),
                'tokens_used':tokens.get('tokens_used',0),'tokens_max':tokens.get('tokens_max')}
    @Property(str,notify=changed)
    def agentResult(self):return self.results['agent']
    @Property('QVariantMap',notify=llmChanged)
    def llmConfig(self):return dict((self.snapshot.get('llm') or {}).get('config') or {})
    @Property('QVariantMap',notify=llmChanged)
    def llmSecretsConfigured(self):return dict((self.snapshot.get('llm') or {}).get('secrets') or {})
    @Property(str,notify=llmChanged)
    def llmRevision(self):return str((self.snapshot.get('llm') or {}).get('revision',0))
    @Property(bool,notify=changed)
    def llmConfigAvailable(self):return self.online and self.configurationStatus=='ready' and 'llm' in self.snapshot and not self.sessionId
    @Property(str,notify=changed)
    def llmResult(self):return self.results['llm']
    # Write-only: the key is passed straight into one Core request. It is not stored, logged, published or echoed.
    @Slot(str,str)
    def setApiKey(self,provider,key):
        if not self.llmConfigAvailable:return self._refuse('llm','Motor LLM indisponível agora')
        if provider not in LLM_PROVIDERS:return self._refuse('llm',CODE_MESSAGES['invalid_provider'])
        if not valid_key(key):return self._refuse('llm',CODE_MESSAGES['invalid_secret'])
        self._send('llm','secret_set',provider=provider,key=key)
    @Slot(str)
    def clearApiKey(self,provider):
        if not self.llmConfigAvailable:return self._refuse('llm','Motor LLM indisponível agora')
        if provider not in LLM_PROVIDERS:return self._refuse('llm',CODE_MESSAGES['invalid_provider'])
        self._send('llm','secret_clear',provider=provider)
    # Modelo atual actions: a manual selftest of the configured model (capability answer, 30 s) and the rollback or mark-good of the last good config (Core ops, live revision).
    @Slot()
    def llmSelftest(self):
        if self._models_blocked():return
        if not (self.snapshot.get('llm') or {}).get('config'):return self._models_say('Configure um modelo antes de testar.')
        self._models_capability('manual_selftest',{'action':'selftest'},SELFTEST_DEADLINE_MS)
    def _llm_revision_op(self,kind,op,message):
        if self._models_busy_now():return self._models_say('Aguarde a operação anterior do gerenciador')
        if self.chat_inflight is not None or self.chat_request is not None or self.pending_chat:return self._models_say('Aguarde a conversa terminar')
        if self._models_send(kind,op,revision=self._revision()):self.models_message=message;self._models_touch()
    @Slot()
    def llmRollback(self):
        if not self.llmRollbackAvailable:return self._models_say(CODE_MESSAGES['no_lkg'])
        self._llm_revision_op('rollback_manual','llm_rollback','Restaurando a configuração anterior no Core…')
    @Slot()
    def llmMarkGood(self):
        if not self.llmConfigAvailable:return self._models_say('Motor LLM indisponível agora')
        self._llm_revision_op('mark_manual','llm_mark_good','Marcando a configuração atual como boa…')
    # WP-19 describe(id): the Core op llm_describe asks the plugin; the answer is the llm_engine.models capability result.
    @Slot(str)
    def describeModel(self,ident):
        if self._models_blocked():return
        if not (isinstance(ident,str) and MODEL_TOKEN.fullmatch(ident)):return self._models_say(CODE_MESSAGES['invalid_input'])
        if self._models_send('describe','llm_describe',id=ident):self.models_message='Pedindo a descrição do modelo ao Core…';self._models_touch()
    @Property('QVariantMap',notify=modelsStateChanged)
    def modelDescription(self):return dict(self.models_described or {})
    @Property(bool,notify=changed)
    def llmTestAvailable(self):return self.modelsAvailable and bool((self.snapshot.get('llm') or {}).get('config')) and not self._models_busy_now()
    @Property(bool,notify=changed)
    def llmRollbackAvailable(self):return self.llmConfigAvailable and bool(((self.snapshot.get('llm') or {}).get('config') or {}).get('lkg')) and not self._models_busy_now()
    # The dialog passes the revision it captured when it opened; a changed snapshot revision is refused, not resent.
    @Slot(str,str,str,bool,str)
    def configureLlm(self,provider,model,custom_url,cloud_consent,revision):
        url=custom_url or None
        if not self.llmConfigAvailable:return self._refuse('llm','Motor LLM indisponível agora')
        if self._models_busy_now():return self._refuse('llm','Aguarde o gerenciador de modelos')
        if revision!=self.llmRevision:return self._refuse('llm',CODE_MESSAGES['stale_llm_revision'])
        if llm_config_problem(provider,model,url,cloud_consent):return self._refuse('llm',CODE_MESSAGES['invalid_config'])
        self._send('llm','llm_configure',revision=int(revision),provider=provider,model=model,custom_url=url,cloud_consent=bool(cloud_consent),**self._keep_fallback())
    # ---- C2 model manager. The plugin owns the catalog; the Core owns config, LKG and keys. Every request has one kind, and every answer is routed by it.
    def _models_target(self):
        for item in (self.snapshot.get('plugins') or {}).get('items',[]):
            if item['state']=='running' and MODEL_CAPABILITY in item['capabilities']:return item['plugin_id']
        return None
    def _models_busy_now(self):return self.models_req is not None or self.models_wait is not None or self.models_flow is not None or self.models_want_list
    def _models_touch(self,catalog=False):
        if catalog:self.modelsCatalogChanged.emit()
        self.modelsStateChanged.emit();self.changed.emit()
    def _models_say(self,message):self.models_message=message;self._models_touch()
    def _models_blocked(self):
        """Refuses a new operation and says why; nothing is sent."""
        if self._models_busy_now():self._models_say('Aguarde a operação anterior do gerenciador');return True
        if self.chat_inflight is not None or self.chat_request is not None or self.pending_chat:self._models_say('Aguarde a conversa terminar');return True
        if self._models_target() is None:self._models_say('Modelos LLM indisponíveis: o plugin não está ativo');return True
        return False
    def _revision(self):return int((self.snapshot.get('llm') or {}).get('revision',0))
    def _keep_fallback(self):
        """llm_configure replaces the whole config, so a missing fallback would clear the saved one: resend it unchanged."""
        fallback=((self.snapshot.get('llm') or {}).get('config') or {}).get('fallback')
        return {'fallback':fallback} if fallback is not None else {}
    def _all_models(self):
        data=self.models_data or {};return list(data.get('recommended',[]))+list(data.get('custom',[]))
    def _model_by_id(self,ident):return next((m for m in self._all_models() if m['id']==ident),None)
    def _result_text(self,result):
        text=code_message(result.get('error') or 'plugin_error')
        return f"{text} (HTTP {result[HTTP_STATUS_KEY]})" if HTTP_STATUS_KEY in result else text
    def _models_send(self,kind,op,**kw):
        """One Core request on the model channel. Refused while another request is in flight; never queued."""
        if self.pending:self._models_say(CODE_MESSAGES['busy']);return False
        if not self._request(op,**kw):self._models_say('Core indisponível');return False
        self.models_req=(kind,op);return True
    def _models_capability(self,kind,payload,deadline):
        if self._models_send(kind,'capability_invoke',capability=MODEL_CAPABILITY,input=payload,deadline_ms=deadline):self.models_message=PENDING_MODELS[kind];self._models_touch()
    def _models_reset(self):
        """Connection lost: in-flight model requests end here. A selftest that was running is rolled back once the Core is back."""
        testing=self.models_wait=='selftest' or (self.models_req is not None and self.models_req[0]=='selftest')
        active=self._models_busy_now()
        self.models_recover=self.models_recover or testing
        self.models_req=None;self.models_wait=None;self.models_marker=None;self.models_flow=None;self.models_want_list=False
        self.models_page_req=None;self.models_page=fresh_model_pages()
        if testing:self.models_message='Conexão caiu durante o teste; a configuração anterior será restaurada ao reconectar'
        elif active:self.models_message='Conexão caiu durante a operação; confira o modelo atual'
        had_catalog=self.models_data is not None;self.models_data=None
        if had_catalog:self.modelsCatalogChanged.emit()
        if active or had_catalog:self._models_touch()
    def _models_ack(self,kind,code):
        """The Core answered a models request. Capability acks wait for the result; llm ops finish here or queue the next step."""
        flow=self.models_flow
        if kind=='selftest' and flow is not None:
            # A refused selftest is a failed test: the candidate must not stay active untested.
            if code=='ok':self.models_wait='selftest';self.models_marker=self._responses;self.models_message='Testando o modelo no Core…'
            else:flow.update(next='rollback',reason_text=code_message(code))
        elif kind=='configure' and flow is not None:
            if code=='ok':flow['next']='selftest';self.models_message='Modelo salvo; testando…'
            else:self.models_flow=None;self.models_message=code_message(code)
        elif kind=='mark' and flow is not None:
            self.models_flow=None
            self.models_message=f"Modelo ativo: {flow['label']} · teste ok em {flow['latency']} ms" if code=='ok' else f"Teste ok, mas não marcado como bom: {code_message(code)}"
        elif kind=='rollback' and flow is not None:
            self.models_flow=None;reason=flow.get('reason_text') or 'falha no teste'
            self.models_message=f'Teste falhou ({reason}); configuração anterior restaurada' if code=='ok' else f'Teste falhou ({reason}); reversão não aplicada: {code_message(code)}'
        elif kind=='manual_selftest':
            if code=='ok':self.models_wait=kind;self.models_marker=self._responses;self.models_message='Testando o modelo no Core…'
            else:self.models_message=code_message(code)
        elif kind=='rollback_manual':self.models_message='Configuração anterior restaurada' if code=='ok' else code_message(code)
        elif kind=='mark_manual':self.models_message='Configuração marcada como boa' if code=='ok' else code_message(code)
        elif kind=='fallback':self.models_message='Fallback salvo pelo Core' if code=='ok' else code_message(code)
        elif kind=='clear':self.models_message='Dados do plugin apagados' if code=='ok' else code_message(code)
        elif kind=='describe':
            if code=='ok':self.models_wait=kind;self.models_marker=self._responses
            else:self.models_message=code_message(code)
        elif kind in ('list','save_custom','delete_custom'):
            if code=='ok':self.models_wait=kind;self.models_marker=self._responses
            else:self.models_message=code_message(code);self.models_page_req=None
        self._models_touch()
    def _models_observe(self):
        """Finishes the one awaited capability answer. The Core clears capability_result on each invoke, so only a response received after the invoke's ack can carry the answer. Equal values are not a staleness test: an identical answer is still the answer."""
        kind=self.models_wait
        if kind is None:return
        result=self.snapshot.get('capability_result')
        if self._responses<=self.models_marker or not result or result.get('capability')!=MODEL_CAPABILITY or result.get('plugin_id')!=self._models_target():return
        self.models_wait=None;self.models_marker=None;ok=result['ok'];output=result.get('output')
        if kind=='list':
            req,self.models_page_req=self.models_page_req,None
            if not ok:self.models_message=self._result_text(result)
            elif req is None or not valid_models_page(output,req[0],req[1]):self.models_message='Resposta do plugin recusada pelo esquema; catálogo não alterado'
            elif not self._merge_page(req[0],req[1],output):self.models_message='Página fora de ordem; catálogo não alterado, atualize a lista'
            else:self.models_message='Catálogo atualizado';self._models_touch(catalog=True);return
        elif kind in ('save_custom','delete_custom'):
            if ok:self.models_want_list='custom';self.models_message='Modelo personalizado salvo' if kind=='save_custom' else 'Modelo personalizado removido'
            else:self.models_message=self._result_text(result)
        elif kind=='describe':
            if ok and valid_describe(output):
                self.models_described=output['model'];self.models_message=f"Modelo descrito pelo plugin: {output['model']['label']}"
            else:self.models_message=self._result_text(result) if not ok else 'Resposta do plugin recusada pelo esquema'
        elif kind=='manual_selftest':
            if ok and valid_selftest(output):self.models_message=f"Teste ok: resposta em {output['latency_ms']} ms"
            else:self.models_message=self._result_text(result) if not ok else 'Resposta do teste recusada pelo esquema'
        elif kind=='selftest' and self.models_flow is not None:
            flow=self.models_flow
            if ok and valid_selftest(output):flow.update(next='mark',latency=output['latency_ms']);self.models_message='Teste ok; marcando como bom…'
            else:flow.update(next='rollback',reason_text=self._result_text(result) if not ok else 'Resposta do teste recusada pelo esquema')
        self._models_touch()
    def _models_next(self):
        """Sends the next model step when nothing else is in flight: the flow's selftest/mark/rollback, a recovery rollback, or a queued catalog refresh."""
        if self.pending or not self.online:return
        flow=self.models_flow
        if flow is None and self.models_recover:
            self.models_recover=False;self.models_flow=flow={'label':'','next':'rollback','reason_text':'conexão caiu durante o teste','latency':None}
        if flow is not None:
            step,flow['next']=flow.get('next'),None
            if step=='selftest' and not self._models_send('selftest','capability_invoke',capability=MODEL_CAPABILITY,input={'action':'selftest'},deadline_ms=SELFTEST_DEADLINE_MS):self.models_flow=None
            elif step in ('mark','rollback') and not self._models_send(step,'llm_mark_good' if step=='mark' else 'llm_rollback',revision=self._revision()):self.models_flow=None
            return
        if self.models_want_list and self.models_wait is None and self.models_req is None:
            tab,self.models_want_list=self.models_want_list,False
            if self._models_target() is not None:self._models_page_send(tab,0,announce=False)
    def _models_page_send(self,tab,offset,announce=True):
        """One page of action list. The tab and offset are kept until the answer, so the page merges where it was asked for. A refresh after a save or delete keeps the message it follows."""
        if self._models_send('list','capability_invoke',capability=MODEL_CAPABILITY,input={'action':'list','tab':tab,'offset':offset,'limit':MODELS_PAGE},deadline_ms=MODELS_DEADLINE_MS):
            self.models_page_req=(tab,offset)
            if announce:self.models_message=PENDING_MODELS['list']
            self._models_touch()
    def _merge_page(self,tab,offset,output):
        """Appends one valid page in order. Offset 0 replaces the tab; any other offset must be where the last page ended (else stale, nothing changes). Duplicate ids are dropped; the total follows the newest page."""
        state=self.models_page[tab]
        if offset!=0 and offset!=state['next']:return False
        data=dict(self.models_data or {'recommended':[],'custom':[]})
        items=[] if offset==0 else list(data.get(tab,[]))
        seen={m['id'] for m in items}
        for model in output['items']:
            if model['id'] not in seen:seen.add(model['id']);items.append(model)
        data[tab]=items;data['hardware']=output['hardware'];data['selected']=output['selected']
        self.models_data=data;self.models_page[tab]={'total':output['total'],'next':offset+len(output['items'])}
        return True
    @Slot(str)
    def listModels(self,tab):
        """Reloads the first page of one tab ('recommended' or 'custom'); the tab's loaded items are replaced when it arrives. A reload asked while another page is in flight (a tab switch, say) waits for that answer instead of being lost."""
        if tab not in MODEL_TABS:return
        if self.models_page_req is not None:self.models_want_list=tab;self._models_touch();return
        if not self._models_blocked():self._models_page_send(tab,0)
    @Slot(str)
    def loadMoreModels(self,tab):
        """Requests the page after the last one loaded for this tab. Nothing happens when every Model is loaded or a request is in flight."""
        if tab not in MODEL_TABS or self._models_blocked():return
        state=self.models_page[tab]
        if state['total'] is not None and state['next']>=state['total']:return
        self._models_page_send(tab,state['next'])
    @Slot(str,str)
    def useModel(self,ident,revision):
        """useModel flow: llm_configure -> selftest -> llm_mark_good on success, llm_rollback on any failure. One pass, no retry."""
        if self._models_blocked():return
        model=self._model_by_id(ident)
        if model is None:return self._models_say(CODE_MESSAGES['model_not_found'])
        if revision!=self.llmRevision:return self._models_say(CODE_MESSAGES['stale_llm_revision'])
        llm=self.snapshot.get('llm') or {};config=llm.get('config') or {};consent=config.get('cloud_consent') is True
        if model['provider'] in LLM_PROVIDERS and (llm.get('secrets') or {}).get(model['provider']) is not True:return self._models_say('Sem chave: salve a chave do provedor em Motor LLM')
        if model['provider'] in LLM_PROVIDERS and not consent:return self._models_say('Sem consentimento: marque o consentimento de nuvem em Motor LLM')
        self.models_flow={'label':model['label'],'next':None,'reason_text':'','latency':None}
        if self._models_send('configure','llm_configure',revision=int(revision),**target_for(model,consent),**self._keep_fallback()):self.models_message='Salvando modelo no Core…';self._models_touch()
        else:self.models_flow=None
    @Slot('QVariantMap')
    def saveCustomModel(self,form):
        problem=custom_form_problem(form)
        if problem is not None:return self._models_say(problem)
        model=custom_model(form)
        if not valid_model(model,'custom'):return self._models_say('Modelo personalizado recusado pelo esquema')
        if not self._models_blocked():self._models_capability('save_custom',{'action':'save_custom','model':model},MODELS_DEADLINE_MS)
    @Slot(str)
    def deleteCustomModel(self,ident):
        if self._models_blocked():return
        if not any(m['id']==ident for m in (self.models_data or {}).get('custom',[])):return self._models_say(CODE_MESSAGES['model_not_found'])
        self._models_capability('delete_custom',{'action':'delete_custom','id':ident},MODELS_DEADLINE_MS)
    @Slot(str,str)
    def setFallback(self,ident,revision):self._fallback_change(ident,revision,True)
    @Slot(str)
    def clearFallback(self,revision):self._fallback_change(None,revision,False)
    def _fallback_change(self,ident,revision,enable):
        """Fallback is a field of llm_configure (C2): the primary stays as it is; a cloud fallback needs saved key and consent."""
        if self._models_blocked():return
        llm=self.snapshot.get('llm') or {};config=llm.get('config')
        if config is None:return self._models_say('Escolha o modelo principal antes do fallback')
        if revision!=self.llmRevision:return self._models_say(CODE_MESSAGES['stale_llm_revision'])
        fallback=None
        if enable:
            model=self._model_by_id(ident)
            if model is None:return self._models_say(CODE_MESSAGES['model_not_found'])
            if model['provider'] in LLM_PROVIDERS and (llm.get('secrets') or {}).get(model['provider']) is not True:return self._models_say('Sem chave: salve a chave do provedor em Motor LLM')
            if model['provider'] in LLM_PROVIDERS and config.get('cloud_consent') is not True:return self._models_say('Fallback na nuvem exige o consentimento marcado em Motor LLM')
            fallback=fallback_for(model)
        primary={'provider':config['provider'],'model':config['model'],'custom_url':config['custom_url'],'cloud_consent':config['cloud_consent']}
        if config['provider'] in LOCAL_PROVIDERS:primary['local_port']=config.get('local_port')
        if self._models_send('fallback','llm_configure',revision=int(revision),**primary,fallback=fallback):self.models_message='Salvando fallback no Core…';self._models_touch()
    @Slot()
    def clearPluginSettings(self):
        """Erases the plugin's own settings ledger (C2). The Core config and keys are not touched. The QML asks first."""
        if self._models_busy_now():return self._models_say('Aguarde a operação anterior do gerenciador')
        self._models_capability_plain('clear','plugin_settings_clear',plugin_id=MODEL_PLUGIN)
    @Slot(str)
    def clearPluginSettingsOf(self,pluginId):
        """Erases one plugin's own settings ledger: plugin_settings_clear {plugin_id}, no revision. Only that plugin's file changes; the QML asks first. Answers on the plugin channel."""
        if not (isinstance(pluginId,str) and len(pluginId)<=64 and PLUGIN_ID.fullmatch(pluginId)):return self._refuse('plugin','Id de plugin inválido')
        if not self.pluginsAvailable:return self._refuse('plugin','Plugins indisponíveis agora')
        if self._models_busy_now():return self._refuse('plugin','Aguarde a operação anterior do gerenciador')
        self._send('plugin','plugin_settings_clear',plugin_id=pluginId)
    def _models_capability_plain(self,kind,op,**kw):
        if self._models_send(kind,op,**kw):self.models_message='Apagando dados do plugin…';self._models_touch()
    @Slot('QVariantMap',result=str)
    def customFormProblem(self,form):return custom_form_problem(form) or ''
    @Slot(str,result=str)
    def certificationBadge(self,state):return CERT_BADGES.get(state,'')
    @Slot(str,result=str)
    def featureLabel(self,state):return FEATURE_LABELS.get(state,'Desconhecido')
    @Property(bool,notify=changed)
    def modelsAvailable(self):return self.online and self._models_target() is not None
    @Property(bool,notify=changed)
    def modelsBusy(self):return self._models_busy_now()
    @Property(str,notify=changed)
    def modelsResult(self):return self.models_message
    @Property(str,notify=changed)
    def modelsStatus(self):
        llm=self.snapshot.get('llm') or {}
        return model_status(llm.get('config'),self._all_models(),llm.get('secrets') or {},self.models_flow is not None)
    @Property('QVariantList',notify=modelsCatalogChanged)
    def modelsRecommended(self):return list((self.models_data or {}).get('recommended',[]))
    @Property('QVariantList',notify=modelsCatalogChanged)
    def modelsCustom(self):return list((self.models_data or {}).get('custom',[]))
    @Property(int,notify=modelsCatalogChanged)
    def modelsRecommendedTotal(self):return self.models_page['recommended']['total'] or 0
    @Property(int,notify=modelsCatalogChanged)
    def modelsCustomTotal(self):return self.models_page['custom']['total'] or 0
    @Property('QVariantMap',notify=modelsCatalogChanged)
    def modelsHardware(self):return dict((self.models_data or {}).get('hardware') or {})
    @Property('QVariantMap',notify=llmChanged)
    def modelsSelected(self):
        config=(self.snapshot.get('llm') or {}).get('config')
        return {'provider':config['provider'],'model':config['model']} if config else {}
    @Property('QVariantMap',notify=llmChanged)
    def modelsFallback(self):
        config=(self.snapshot.get('llm') or {}).get('config')
        return dict(config.get('fallback') or {}) if config else {}
    @Property('QVariantList',notify=packChanged)
    def wakeChoices(self):return [display_wake_choice(p) for p in (self.snapshot.get('base_pack',{}).get('wake_phrases',[]) if self.snapshot.get('base_pack') else [])]
    @Property(str,notify=changed)
    def packDescription(self):
        pack=self.snapshot.get('base_pack')
        if not pack:return ''
        active=next((p['text'] for p in pack['wake_phrases'] if p['id']==pack['active_phrase']),'inativo')
        configured=self.snapshot.get('preferences',{}).get('wake_phrase') or pack['default_phrase']
        saved=next((p['text'] for p in pack['wake_phrases'] if p['id']==configured),'incompatível')
        return f"{pack['id']} · em desenvolvimento · virtual\nPerfil no processo: {active}\nConfiguração salva: {saved}\nVoz: {pack['voice']} · {LANGUAGE_LABELS['EN']} · candidata"
    @Slot(str)
    def selectWake(self,ident):
        if self.preferencesAvailable:self._preferences('select_wake',revision=int(self.preferencesRevision),phrase_id=ident)
    # ---- Frases de ativação (src/phrases.rs): lista ativa, frases personalizadas e teste sintético.
    def _wake_block(self):return self.snapshot.get('wake_phrases') or {}
    def _wake_items(self):
        """Current wake phrase list as the Core stores it: `[{id, active, sensitivity?}]`."""
        return [dict(s) for s in self._wake_block().get('settings',[])]
    def _wake_send(self,items,acknowledge=False):
        if sum(1 for i in items if i['active'])>5:return self._refuse('prefs',PHRASE_MESSAGES['too_many_active_phrases'])
        if self.preferencesAvailable:self._preferences('select_wake_phrases',revision=int(self.preferencesRevision),phrases=items,acknowledge_untested=bool(acknowledge))
    @Slot(str,bool,bool)
    def setWakePhraseActive(self,ident,active,acknowledge):
        if not wake_phrase_id_ok(ident):return self._refuse('prefs',CODE_MESSAGES['invalid_wake_phrases'])
        items=self._wake_items()
        if not any(i['id']==ident for i in items):items.append({'id':ident,'active':False})
        for item in items:
            if item['id']==ident:item['active']=bool(active)
        self._wake_send(items,acknowledge)
    @Slot(str,float)
    def setWakePhraseSensitivity(self,ident,value):
        if not wake_phrase_id_ok(ident) or not wake_sensitivity_ok(value):return self._refuse('prefs',SENSITIVITY_RANGE_TEXT)
        items=self._wake_items()
        for item in items:
            if item['id']==ident:item['sensitivity']=round(float(value),2)
        self._wake_send(items)
    @Slot()
    def restoreWakePhraseDefaults(self):
        default=(self.snapshot.get('base_pack') or {}).get('default_phrase')
        if isinstance(default,str):self._wake_send([{'id':default,'active':True}])
    @Slot(str)
    def checkWakePhrase(self,text):
        if short_text(text,160):self._request('wake_phrase_validate',text=text)
    @Slot(str)
    def addWakePhrase(self,text):
        if not short_text(text,160) or not self.preferencesAvailable:return
        if self.online:self._preferences('wake_phrase_add',revision=int(self._wake_block().get('custom_revision',0)),text=text)
    @Slot(str)
    def removeWakePhrase(self,ident):
        if wake_phrase_id_ok(ident) and self.online:self._preferences('wake_phrase_remove',revision=int(self._wake_block().get('custom_revision',0)),id=ident)
    @Slot(str)
    def testWakePhrase(self,ident):
        if wake_phrase_id_ok(ident) and self.online:self._preferences('wake_phrase_test',id=ident)
    @Property('QVariantList',notify=changed)
    def wakePhraseRows(self):
        block=self._wake_block()
        settings=block.get('settings',[]);active=set(block.get('active',[]))
        return [display_wake_entry(e,settings,active) for e in block.get('phrases',[])]
    @Property('QVariantMap',notify=changed)
    def wakePhraseCheck(self):
        check=self.snapshot.get('phrase_check') or {}
        return {**check,'message':'' if check.get('ok') else CODE_MESSAGES.get(check.get('code'),'')} if check else {}
    @Property('QVariantMap',notify=changed)
    def wakePhraseTest(self):
        test=self._wake_block().get('test') or {}
        return {**test,'message':CODE_MESSAGES.get(test.get('code'),'')} if test else {}
    @Property(str,notify=changed)
    def wakePhraseResult(self):return self.results.get('phrase','')
    @Property(int,notify=changed)
    def wakePhraseMaxActive(self):return int(self._wake_block().get('max_active',5))
    @Property(int,notify=changed)
    def wakePhraseActiveCount(self):return len(self._wake_block().get('active',[]))
    @Property(int,notify=changed)
    def wakePhraseCustomCount(self):return sum(1 for e in self._wake_block().get('phrases',[]) if e.get('custom'))
    @Property(bool,notify=changed)
    def wakePhraseLexicon(self):return bool(self._wake_block().get('lexicon',False))
    @Property(bool,notify=preferencesChanged)
    def visualFeedback(self):return self.snapshot.get('preferences',{}).get('visual_feedback',True)
    @Property(int,notify=preferencesChanged)
    def outputVolume(self):return self.snapshot.get('preferences',{}).get('output_volume_percent',100)
    @Slot(bool,int)
    def saveFeedback(self,visual,volume):
        if self.preferencesAvailable:self._preferences('feedback_preferences',revision=int(self.preferencesRevision),visual_feedback=visual,output_volume_percent=volume)
    @Slot()
    def recoverConfiguration(self):
        if self.recoveryAvailable:self._preferences('recover_configuration',revision=int(self.preferencesRevision))
    # ---- Core restart (docs/ui-spec/40-configuracoes.md §8.5). The Core refuses with busy while a session, an agent run, a skill run or a plugin call is active.
    @Slot()
    def coreRestart(self):
        if not self.online:return self._refuse('core','Core desconectado: nada a reiniciar')
        if self.restart_state=='waiting':return
        if self.sessionId:return self._refuse('core','Indisponível durante a sessão de voz')
        self._send('core','core_restart')
    def _restart_ack(self,code):
        """core_restart answered. 'ok' means the Core exits next: the socket drop and the first snapshot after it finish the wait; the timer turns a silent Core into a message."""
        if code!='ok':self.results['core']=code_message(code);self.changed.emit();return
        self.restart_state='waiting';self.restart_dropped=False;self.results['core']=PENDING['core_restart']
        self.restart_timer.start();self.changed.emit()
    def _restart_done(self):
        self.restart_state=None;self.restart_dropped=False;self.restart_timer.stop();self.results['core']=RESTART_BACK_TEXT;self.changed.emit()
    def _restart_timeout(self):
        if self.restart_state=='waiting':self.restart_state='failed';self.results['core']='';self.changed.emit()
    @Property(bool,notify=changed)
    def coreRestartAvailable(self):return self.online and self.restart_state!='waiting' and not self.sessionId
    @Property(bool,notify=changed)
    def coreRestartBusy(self):return self.restart_state=='waiting' or self.pending_op=='core_restart'
    @Property(str,notify=changed)
    def coreRestartResult(self):
        if self.restart_state=='waiting':return RESTART_WAIT_TEXT
        if self.restart_state=='failed':return RESTART_TIMEOUT_TEXT
        return self.results['core']
    @Property('QVariantMap',notify=llmChanged)
    def llmLastChat(self):return dict((self.snapshot.get('llm') or {}).get('last_chat') or {})
    @Property(str,notify=changed)
    def configurationStatus(self):return self.snapshot.get('configuration_status','ready' if self.online else 'offline')
    @Property(bool,notify=changed)
    def recoveryAvailable(self):return self.online and self.configurationStatus=='safe_mode' and bool(self.snapshot.get('configuration_recovery_available')) and self.preferences_request is None
    @Property(str,notify=changed)
    def configurationMessage(self):
        if self.configurationStatus=='safe_mode':return ('Modo seguro: configuração inválida preservada; áudio e comandos bloqueados' if self.snapshot.get('configuration_recovery_available') else 'Modo seguro: arquivo excede o limite de recuperação automática; conteúdo preservado')
        # The restart signal (the saved selection is not running yet). U1: further changes are still accepted while it is pending.
        if self.configurationStatus=='restart_required':return 'Mudança salva: reinicie o Core para aplicar. Você pode fazer outras mudanças antes do reinício.'
        return ''
    @Slot(bool,int)
    def savePreferences(self,audible,timeout):
        if self.preferencesAvailable:
            self._preferences('preferences',revision=int(self.preferencesRevision),audible_feedback=audible,session_timeout_ms=timeout)
    @Slot()
    def rollbackPreferences(self):
        if self.preferencesAvailable:self._preferences('rollback_preferences',revision=int(self.preferencesRevision))
    def _preferences(self,op,**kw):
        channel=OPS[op][0]
        self.results[channel]=PENDING.get(op,'Enviando ao Core')
        if self.pending:self.preferences_request=(op,kw)
        else:self._request(op,**kw)
        self.changed.emit()
    @Property(bool,notify=changed)
    def preferencesAvailable(self):return self.online and self.configurationStatus in ('ready','restart_required') and 'preferences' in self.snapshot and not self.sessionId and self.preferences_request is None
    @Property(bool,notify=changed)
    def rollbackAvailable(self):return self.preferencesAvailable and bool(self.snapshot.get("preferences",{}).get("previous_preferences"))
    @Property(bool,notify=changed)
    def voiceAvailable(self):return self.online and self.snapshot.get("speech_status","unavailable")!="unavailable"
    @Property(bool,notify=preferencesChanged)
    def audibleFeedback(self):return self.snapshot.get('preferences',{}).get('audible_feedback',True)
    @Property(int,notify=preferencesChanged)
    def sessionTimeout(self):return self.snapshot.get('preferences',{}).get('session_timeout_ms',30000)
    @Property(str,notify=preferencesChanged)
    def preferencesRevision(self):return str(self.snapshot.get('preferences',{}).get('revision',0))
    @Property(str,notify=changed)
    def preferencesResult(self):return self.results['prefs']
    # ---- B16 Voz e Wake, Dispositivos and Geral (docs/A6-live-audio.md). The Core owns every value: these slots send one bounded
    # request through the preferences op (absent optional fields keep the stored value) and the properties read the snapshot.
    def _devices(self):return (self.snapshot.get('audio') or {}).get('devices')
    def _live(self):return (self.snapshot.get('audio') or {}).get('live') or {}
    def _saved_device(self,key):return (self.snapshot.get('preferences') or {}).get(key) or DEFAULT_DEVICE
    def _prefs_unavailable_text(self):
        if not self.online:return 'Core desconectado: nada foi alterado'
        if self.sessionId:return RESTORE_BUSY_TEXT
        if self.configurationStatus!='ready':return CODE_MESSAGES['preferences_unavailable']
        return 'O Core está ocupado com outra alteração; tente de novo em instantes'
    def _pref_request(self,**changes):
        prefs=self.snapshot.get('preferences') or {}
        return {'revision':int(self.preferencesRevision),'audible_feedback':bool(prefs.get('audible_feedback',True)),'session_timeout_ms':int(prefs.get('session_timeout_ms',30000)),**changes}
    @Property(float,notify=preferencesChanged)
    def wakeSensitivity(self):return float((self.snapshot.get('preferences') or {}).get('wake_sensitivity',1.0))
    @Property(bool,notify=preferencesChanged)
    def inputConditioningOn(self):return (self.snapshot.get('preferences') or {}).get('input_conditioning','auto')!='off'
    @Property(str,notify=preferencesChanged)
    def audioInputSaved(self):return self._saved_device('audio_input_device')
    @Property(str,notify=preferencesChanged)
    def audioOutputSaved(self):return self._saved_device('audio_output_device')
    @Property('QVariantMap',notify=audioChanged)
    def audioDevices(self):
        devices=self._devices()
        return {'known':devices is not None,'source':(devices or {}).get('source',''),'status':devices_status(devices),'inputs':list((devices or {}).get('inputs',[])),'outputs':list((devices or {}).get('outputs',[]))}
    @Property('QVariantList',notify=changed)
    def audioInputChoices(self):return device_choices(self._devices(),'inputs',self._saved_device('audio_input_device'))
    @Property('QVariantList',notify=changed)
    def audioOutputChoices(self):return device_choices(self._devices(),'outputs',self._saved_device('audio_output_device'))
    @Property(str,notify=changed)
    def audioInputLabel(self):
        saved=self._saved_device('audio_input_device')
        choice=next((c for c in device_choices(self._devices(),'inputs',saved) if c['value']==saved),None)
        return choice['text'].replace(DEFAULT_MARK,'') if choice else DEFAULT_DEVICE_LABEL
    @Property('QVariantMap',notify=audioChanged)
    def audioLive(self):return dict(self._live())
    @Property(bool,notify=audioChanged)
    def micActive(self):return self._live().get('mic_active') is True
    @Property(str,notify=audioChanged)
    def audioLiveText(self):return live_input_text(self._live())
    @Property(str,notify=audioChanged)
    def audioOutputText(self):return live_output_text(self._live())
    @Property(str,notify=changed)
    def audioResult(self):return self.results['audio']
    # A6 consent: the switch shows the ledger value; the state line and the restart flag come from audio.live.
    @Property(bool,notify=preferencesChanged)
    def liveAudioEnabled(self):return (self.snapshot.get('preferences') or {}).get('live_audio') is True
    @Property(bool,notify=audioChanged)
    def liveAudioRestartRequired(self):return self._live().get('restart_required') is True
    @Property(str,notify=audioChanged)
    def liveAudioStateText(self):return live_state_text(self._live() if self.online else None)
    # Voice turns come from the boot replay fixture or the virtual PCM whenever the microphone is not live: such a turn is test audio.
    @Property(bool,notify=changed)
    def lastInteractionIsTestAudio(self):return (self.snapshot.get('transcript') or {}).get('source')=='voice' and self._live().get('enabled') is not True
    @Slot(bool)
    def setLiveAudio(self,enabled):
        """Consent switch. The dialog (Cancelar by default) runs before enabled=True; the Core refuses an enable without confirmed."""
        if not self.preferencesAvailable:return self._refuse('prefs',self._prefs_unavailable_text())
        if type(enabled) is not bool:return self._refuse('prefs',CODE_MESSAGES['invalid_preferences'])
        self._preferences('live_audio_preference',revision=int(self.preferencesRevision),enabled=enabled,confirmed=enabled)
    # ---- A11 host actions. The switch shows the ledger value; the state line is the Core's last host action (content-free).
    @Property(bool,notify=preferencesChanged)
    def realActionsEnabled(self):return (self.snapshot.get('preferences') or {}).get('real_actions') is True
    @Property(str,notify=actionsChanged)
    def realActionStateText(self):return real_actions_state(self.realActionsEnabled,((self.snapshot.get('actions') or {}).get('real') or {}).get('last_action'))
    @Slot(bool)
    def setRealActions(self,enabled):
        """Consent switch. The dialog (Cancelar by default) runs before enabled=True; the Core refuses an enable without confirmed."""
        if not self.preferencesAvailable:return self._refuse('prefs',self._prefs_unavailable_text())
        if type(enabled) is not bool:return self._refuse('prefs',CODE_MESSAGES['invalid_preferences'])
        self._preferences('real_actions_preference',revision=int(self.preferencesRevision),enabled=enabled,confirmed=enabled)
    # ---- CFG-04 retention of the history (timeline and audit trail) and DIAG-02 developer mode. Both are Core preferences.
    @Property(str,notify=preferencesChanged)
    def historyRetention(self):
        value=(self.snapshot.get('preferences') or {}).get('history_retention')
        return value if value in HISTORY_RETENTION_VALUES else ''
    @Slot(str)
    def setHistoryRetention(self,value):
        if not self.preferencesAvailable:return self._refuse('prefs',self._prefs_unavailable_text())
        if value not in HISTORY_RETENTION_VALUES:return self._refuse('prefs',CODE_MESSAGES['invalid_preferences'])
        self._preferences('history_retention_preference',revision=int(self.preferencesRevision),retention=value)
    @Property(bool,notify=preferencesChanged)
    def developerMode(self):return (self.snapshot.get('preferences') or {}).get('developer_mode') is True
    @Slot(bool)
    def setDeveloperMode(self,enabled):
        if not self.preferencesAvailable:return self._refuse('prefs',self._prefs_unavailable_text())
        if type(enabled) is not bool:return self._refuse('prefs',CODE_MESSAGES['invalid_preferences'])
        self._preferences('developer_mode_preference',revision=int(self.preferencesRevision),enabled=enabled)
    # ---- DIAG-01 fields the diagnostics describe. All come from the snapshot; empty or 0 when the Core does not report them.
    @Property(int,notify=changed)
    def protocolVersion(self):return int(self.snapshot.get('version') or 0)
    @Property(str,notify=changed)
    def catalogSha256(self):return str((self.snapshot.get('hub') or {}).get('catalog_sha256') or '')
    # DIAG-01 (WP-15): the Core's pack digest, shown in Diagnóstico as packHash.
    @Property(str,notify=packChanged)
    def packHash(self):return str((self.snapshot.get('base_pack') or {}).get('pack_sha256') or '')
    @Property('QVariantMap',notify=packChanged)
    def packEngines(self):return dict((self.snapshot.get('base_pack') or {}).get('engines') or {})
    @Property(str,notify=packChanged)
    def packAudioInput(self):return str((self.snapshot.get('base_pack') or {}).get('audio_input') or '')
    @Property(str,notify=packChanged)
    def packAudioOutput(self):return str((self.snapshot.get('base_pack') or {}).get('audio_output') or '')
    @Property('QVariantMap',notify=changed)
    def lastSpeech(self):
        """Last spoken answer of the session (Core `speech` summary). Empty map when there is none."""
        speech=self.snapshot.get('speech')
        if not speech:return {}
        return {'elapsed_ms':int(speech.get('elapsed_ms') or 0),'samples':int(speech.get('samples') or 0),'chunks':int(speech.get('chunks') or 0),'peak':float(speech.get('peak') or 0.0),'rms':float(speech.get('rms') or 0.0),'first_pcm_ms':int(speech.get('first_pcm_ms') or 0)}
    # ---- WP-10a personal areas. One Core request per call; the reply is kept as {area, code, reply} for the pages.
    def _personal_refuse(self,area,code):self.personal_reply={'area':area,'code':code,'reply':{}};self.personalChanged.emit()
    def _personal_settled(self,op,code,data):
        reply=data.get('personal_reply');reply=reply.get('reply') if isinstance(reply,dict) else None
        area={'personal':self.personal_area,'personal_export':'export','personal_erase_all':'erase'}[op]
        self.personal_reply={'area':area,'code':code,'reply':reply if isinstance(reply,dict) else {}};self.personalChanged.emit()
    @Slot(str,str)
    def personalOp(self,area,payload):
        if area not in PERSONAL_AREAS:self._personal_refuse(area,'unknown_area');return
        if not isinstance(payload,str) or len(payload)>8192:self._personal_refuse(area,'invalid_request');return
        try:body=json.loads(payload)
        except ValueError:self._personal_refuse(area,'invalid_request');return
        if not isinstance(body,dict):self._personal_refuse(area,'invalid_request');return
        self.personal_area=area
        if not self._request('personal',area=area,payload=body):self._personal_refuse(area,'busy' if self.pending else 'core_unavailable')
    @Slot()
    def personalExport(self):
        self.personal_area='export'
        if not self._request('personal_export'):self._personal_refuse('export','busy' if self.pending else 'core_unavailable')
    @Slot(bool)
    def personalEraseAll(self,confirmed):
        # Only a confirmed request leaves the bridge; the page shows its own confirmation first.
        if confirmed is not True:self._personal_refuse('erase','confirmation_required');return
        self.personal_area='erase'
        if not self._request('personal_erase_all',confirm=True):self._personal_refuse('erase','busy' if self.pending else 'core_unavailable')
    @Property('QVariantMap',notify=personalChanged)
    def personal(self):return dict(self.snapshot.get('personal') or {})
    @Property(bool,notify=changed)
    def personalAvailable(self):return self.online and isinstance((self.snapshot.get('personal') or {}).get('memory'),dict)
    @Property('QVariantMap',notify=personalChanged)
    def personalReply(self):return dict(self.personal_reply)
    # ---- HUD-03: Ctrl+M asks the Core for a listening session; the Core refuses with a reason when live audio or the capture is off.
    @Slot()
    def listenStart(self):self._send('listen','listen_start')
    # ---- DIAG-03: the Core's timeline holds llm_fallback_used (the fallback answer was used) in this session.
    @Property(bool,notify=eventsChanged)
    def llmFallbackUsed(self):return any(e.get('kind')=='llm_fallback_used' for e in (self.snapshot.get('events') or []))
    # ---- DIAG-05 latency and resources. Latency is the round trip measured here; resources are read from /proc (Linux only).
    def _maybe_sample(self):
        now=time.monotonic()
        if self._sampled_at is not None and now-self._sampled_at<1.0:return
        self._sampled_at=now
        self._sample_resources(now)
    def _sample_resources(self,now):
        pid=self._core_pid
        if pid is None:
            self.resource_view={'known':False};self.changed.emit();return
        seen=[];queue=[pid];children_known=True
        while queue and len(seen)<256:
            current=queue.pop()
            if current in seen:continue
            seen.append(current)
            kids=_children(current)
            if kids is None:children_known=False
            else:queue.extend(kids)
        rows={};previous={}
        for process in dict.fromkeys(seen+[os.getpid()]):
            sample=_proc_sample(process)
            if sample is None:continue
            ticks,rss,_ppid=sample
            before=self._cpu_prev.get(process)
            cpu=None if before is None or now<=before[1] else round(max(0.0,(ticks-before[0])/CLOCK_TICKS/(now-before[1])*100),1)
            previous[process]=(ticks,now);rows[process]=(cpu,rss)
        self._cpu_prev=previous
        core=rows.get(pid);workers=[rows[p] for p in seen[1:] if p in rows];own=rows.get(os.getpid())
        def total(values):
            cpus=[c for c,_r in values if c is not None]
            return (round(sum(cpus),1) if cpus else None),sum(r for _c,r in values)
        workers_cpu,workers_rss=total(workers)
        self.resource_view={'known':core is not None,'core_cpu_percent':core[0] if core else None,'core_rss_kb':core[1] if core else 0,
            'workers_known':children_known,'workers_count':len(workers),'workers_cpu_percent':workers_cpu,'workers_rss_kb':workers_rss,
            'bridge_cpu_percent':own[0] if own else None,'bridge_rss_kb':own[1] if own else 0}
        self.changed.emit()
    @Property('QVariantMap',notify=changed)
    def coreLatency(self):
        samples=list(self._latency)
        if not samples:return {'known':False,'samples':0,'last_ms':0,'average_ms':0,'last_op':''}
        values=[ms for _op,ms in samples]
        return {'known':True,'samples':len(values),'last_ms':int(values[-1]),'average_ms':int(sum(values)/len(values)),'last_op':samples[-1][0] or ''}
    @Property('QVariantMap',notify=changed)
    def speechLatency(self):
        speech=self.snapshot.get('speech')
        if not speech:return {'known':False,'first_pcm_ms':0,'elapsed_ms':0}
        return {'known':True,'first_pcm_ms':int(speech.get('first_pcm_ms') or 0),'elapsed_ms':int(speech.get('elapsed_ms') or 0)}
    @Property('QVariantMap',notify=changed)
    def diagResources(self):return dict(self.resource_view)
    # ---- Idiomas (Frente 2). The view comes from snapshot 'languages'; the Core refuses non-installed languages.
    def _languages(self):return dict(self.snapshot.get('languages') or {})
    def _language_items(self,kind):return [dict(item) for item in ((self._languages().get('engines') or {}).get(kind) or [])]
    @Property('QVariantList',notify=languagesChanged)
    def languageSttItems(self):return self._language_items('stt')
    @Property('QVariantList',notify=languagesChanged)
    def languageTtsItems(self):return self._language_items('tts')
    @Property('QVariantList',notify=languagesChanged)
    def languageSttSelected(self):return list(self._languages().get('stt_selected') or [])
    @Property(str,notify=languagesChanged)
    def languageTtsSelected(self):return str(self._languages().get('tts_selected') or '')
    @Property(str,notify=languagesChanged)
    def languageTtsVoice(self):return str(self._languages().get('tts_voice') or '')
    @Property(bool,notify=languagesChanged)
    def languageRestartStt(self):return (self._languages().get('restart_required') or {}).get('stt') is True
    @Property(bool,notify=languagesChanged)
    def languageRestartTts(self):return (self._languages().get('restart_required') or {}).get('tts') is True
    @Property(str,notify=languagesChanged)
    def languageInstallReason(self):
        # CFG-03: PT and FR ship inside the package now (bundled), so the old "awaiting approval" text no longer applies.
        # Languages that are not bundled cannot be installed yet: there is no install operation in the Core.
        return 'Não incluído neste pacote: a instalação de idiomas extras ainda não existe.' if (self._languages().get('install') or {}).get('available') is not True else ''
    @Property(bool,notify=languagesChanged)
    def languagesAvailable(self):return self.preferencesAvailable and 'languages' in self.snapshot
    @Slot(str,str,str)
    def setLanguages(self,stt_json,tts_language,tts_voice):
        """Saves the STT list (JSON array of tags) and the TTS language and voice. Shape is checked here; installation by the Core."""
        if not self.preferencesAvailable:return self._refuse('prefs',self._prefs_unavailable_text())
        try:stt=json.loads(stt_json)
        except (TypeError,ValueError):return self._refuse('prefs',CODE_MESSAGES['invalid_languages'])
        if not language_request_ok(stt,tts_language,tts_voice):return self._refuse('prefs',CODE_MESSAGES['invalid_languages'])
        self._preferences('language_preference',revision=int(self.preferencesRevision),stt_languages=stt,tts_language=tts_language,tts_voice=tts_voice)
    @Slot(str)
    def installLanguage(self,language):
        """CFG-03: the Core verifies the packaged models of `language` and activates them. Nothing is downloaded."""
        if not self.preferencesAvailable:return self._refuse('prefs',self._prefs_unavailable_text())
        if not language_tag_ok(language):return self._refuse('prefs',CODE_MESSAGES['invalid_languages'])
        self._preferences('language_install',language=language)
    @Slot(float)
    def setWakeSensitivity(self,value):
        if not self.preferencesAvailable:return self._refuse('prefs',self._prefs_unavailable_text())
        if not wake_sensitivity_ok(value):return self._refuse('prefs',SENSITIVITY_RANGE_TEXT)
        self._preferences('preferences',**self._pref_request(wake_sensitivity=round(float(value),2)))
    @Slot(bool)
    def setInputConditioning(self,on):
        if not self.preferencesAvailable:return self._refuse('prefs',self._prefs_unavailable_text())
        self._preferences('preferences',**self._pref_request(input_conditioning='auto' if on else 'off'))
    @Slot(str,str)
    def setAudioDevices(self,input_device,output_device):
        if not self.preferencesAvailable:return self._refuse('prefs',self._prefs_unavailable_text())
        if not audio_device_ok(input_device) or not audio_device_ok(output_device):return self._refuse('prefs',DEVICE_INVALID_TEXT)
        self._preferences('preferences',**self._pref_request(audio_input_device=input_device,audio_output_device=output_device))
    @Slot()
    def refreshAudioDevices(self):
        if not self.online:return self._refuse('audio','Core desconectado: nada a consultar')
        self._send('audio','audio_devices')
    @Slot(str,result=bool)
    def probeAudioInput(self,device):
        """A9: 3 s of the microphone for one listed input (or 'default'). Refused locally when malformed; the Core refuses while a voice session or another probe runs."""
        if not self.online:self._refuse('audio','Core desconectado: nada a testar');return False
        if not audio_device_ok(device):self._refuse('audio',DEVICE_INVALID_TEXT);return False
        return self._send('audio','audio_probe',device=device)
    # A13 microphone assistant: one run (2 s per listed input). The result is audio.recommendation; nothing is saved by the run.
    @Slot(result=bool)
    def recommendMicrophones(self):
        if not self.online:self._refuse('audio','Core desconectado: nada a verificar');return False
        if self.sessionId:self._refuse('audio','Indisponível durante a sessão de voz');return False
        return self._send('audio','audio_recommend_input')
    @Slot(str,result=bool)
    def useAudioInput(self,device):
        """A13 'Usar o …': saves the chosen input as Gideon's own preference. The system default is never changed."""
        if not self.preferencesAvailable:self._refuse('prefs',self._prefs_unavailable_text());return False
        if not audio_device_ok(device):self._refuse('prefs',DEVICE_INVALID_TEXT);return False
        self._preferences('preferences',**self._pref_request(audio_input_device=device));return True
    def _default_input_id(self):return next((i['id'] for i in (self._devices() or {}).get('inputs',[]) if i.get('default')),None)
    @Property('QVariantMap',notify=audioChanged)
    def micRecommendation(self):return recommendation_view((self.snapshot.get('audio') or {}).get('recommendation'))
    @Property('QVariantMap',notify=audioChanged)
    def micBanner(self):
        banner=recommendation_banner((self.snapshot.get('audio') or {}).get('recommendation'),self._saved_device('audio_input_device'),self._default_input_id())
        return {**banner,'show':True} if banner else {'show':False,'device':'','text':'','action':''}
    @Slot(result=str)
    def liveLastErrorText(self):
        """A13/A14 diagnostics: the last stderr tails of the wake worker and of the STT worker, from the 0600 files in the Core data dir. Only Diagnóstico › Desenvolvedor reads them; never the snapshot."""
        parts=[]
        for label,name in (('Worker de wake','live-last-error.txt'),('Worker de STT','stt-last-error.txt')):
            try:
                with open(self.root/name,'rb') as handle:data=handle.read(4096)
            except OSError:continue
            parts.append(label+':\n'+data.decode('utf-8','replace')[-2048:])
        return '\n\n'.join(parts)
    # A9 meter and probe (Dispositivos) and the state line (Hoje). Every value comes from audio.live / audio.probe.
    @Property('QVariantMap',notify=audioChanged)
    def audioLevel(self):return level_view(self._live(),self.online)
    @Property('QVariantMap',notify=audioChanged)
    def audioProbe(self):return probe_view((self.snapshot.get('audio') or {}).get('probe'))
    @Property(bool,notify=audioChanged)
    def audioProbeRunning(self):return ((self.snapshot.get('audio') or {}).get('probe') or {}).get('state')=='running'
    @Property('QVariantMap',notify=audioChanged)
    def liveStateView(self):return live_hint_view(self._live(),self.online)
    @Slot()
    def restoreCoreDefaults(self):
        if self.sessionId:return self._refuse('prefs',RESTORE_BUSY_TEXT)
        if not self.preferencesAvailable:return self._refuse('prefs',self._prefs_unavailable_text())
        self._preferences('preferences_restore_defaults',revision=int(self.preferencesRevision))
    @Property(bool,notify=changed)
    def textAvailable(self):return self._text_ready() and self.text_request is None
    @Property(str,notify=changed)
    def textResult(self):return self.results['text']
    @Property('QVariantMap',notify=packChanged)
    def snapshotPack(self):return self.snapshot.get('base_pack') or {}
    @Property(str,notify=sessionChanged)
    def wakeStatus(self):return self.snapshot.get('wake_status','unavailable')
    @Property(str,notify=sessionChanged)
    def sttStatus(self):return self.snapshot.get('stt_status','unavailable')
    @Property(str,notify=sessionChanged)
    def speechStatus(self):return self.snapshot.get('speech_status','unavailable')
    @Property(str,notify=changed)
    def hubApprovalResult(self):return self.results['hub']
    @Slot()
    def beginHubReview(self):
        self.results['hub']='';self.changed.emit()
    @Property(str,notify=hubChanged)
    def hubApprovalRevision(self):return str((self.snapshot.get('hub') or {}).get('approval_revision',0))
    @Property(bool,notify=changed)
    def hubApprovalAvailable(self):return self.preferencesAvailable and (self.snapshot.get('hub') or {}).get('status')=='verified' and 'approval_revision' in self.snapshot['hub'] and self.snapshot['hub'].get('import') is None
    def _stale(self,channel):
        self.results[channel]=STALE_MESSAGE;self.changed.emit()
    def _same_entry(self,plugin,manifest):
        return any(e.get('plugin_id')==plugin and e.get('manifest_sha256')==manifest for e in (self.snapshot.get('hub') or {}).get('entries',[]))
    # Confirmation dialogs pass the revision captured when they opened; a changed live record is refused, not resent.
    @Slot(str,str,'QVariantList',bool,str)
    def approveHub(self,plugin,manifest,permissions,acknowledged,revision):
        if not self.hubApprovalAvailable:return
        if str(revision)!=self.hubApprovalRevision or not self._same_entry(plugin,manifest):return self._stale('hub')
        self._preferences('hub_approve',revision=int(revision),plugin_id=plugin,manifest_sha256=manifest,permissions=list(permissions),publisher_unverified_ack=acknowledged)
    @Property(bool,notify=changed)
    def hubLifecycleAvailable(self):return self.preferencesAvailable and (self.snapshot.get('hub') or {}).get('status')=='verified' and self.snapshot['hub'].get('import') is None
    @Property(str,notify=hubChanged)
    def hubInstallRevision(self):return str((self.snapshot.get('hub') or {}).get('install_revision',0))
    @Property('QVariantList',notify=hubInstalledChanged)
    def hubInstalled(self):return (self.snapshot.get('hub') or {}).get('installed',[])
    @Slot(str,str)
    def installHub(self,plugin,manifest):
        if self.hubLifecycleAvailable and self._same_entry(plugin,manifest):self._preferences('hub_install',revision=int(self.hubInstallRevision),plugin_id=plugin,manifest_sha256=manifest)
    @Slot(str)
    def rollbackHub(self,plugin):
        if self.hubLifecycleAvailable:self._preferences('hub_rollback',revision=int(self.hubInstallRevision),plugin_id=plugin)
    @Slot(str,str)
    def removeHub(self,plugin,revision):
        if not self.hubLifecycleAvailable:return
        if str(revision)!=self.hubInstallRevision:return self._stale('hub')
        self._preferences('hub_remove',revision=int(revision),plugin_id=plugin)
    @Property(bool,notify=changed)
    def pluginsAvailable(self):return self.hubLifecycleAvailable and 'plugins' in self.snapshot
    @Property('QVariantList',notify=pluginsChanged)
    def pluginItems(self):return list((self.snapshot.get('plugins') or {}).get('items',[]))
    @Property(str,notify=pluginsChanged)
    def pluginsRevision(self):return str((self.snapshot.get('plugins') or {}).get('revision',0))
    @Property(str,notify=changed)
    def pluginResult(self):return self.results['plugin']
    @Property(str,notify=capabilityChanged)
    def capabilityResultText(self):
        result=self.snapshot.get('capability_result')
        if not result:return ''
        if not result['ok']:return capability_code_message(result['error'])
        # B7: text is shown as is; an output without text is shown as its JSON (both PlainText, at most 1 KiB).
        output=result['output'];text=output.get('text')
        if not isinstance(text,str):text=json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)
        return clip_bytes(text,CAP_RESULT_LIMIT)
    @Slot(str)
    def enablePlugin(self,plugin):
        if self.pluginsAvailable:self._preferences('plugin_enable',revision=int(self.pluginsRevision),plugin_id=plugin)
    @Slot(str)
    def disablePlugin(self,plugin):
        if self.pluginsAvailable:self._preferences('plugin_disable',revision=int(self.pluginsRevision),plugin_id=plugin)
    @Slot(str,str)
    def revokePlugin(self,plugin,revision):
        if not self.pluginsAvailable:return
        if str(revision)!=self.pluginsRevision:return self._stale('plugin')
        self._preferences('plugin_revoke',revision=int(revision),plugin_id=plugin)
    @Slot(str,str)
    def invokeCapability(self,capability,text):
        if self.pluginsAvailable:self.plugin_capability=capability;self._preferences('capability_invoke',capability=capability,input={'text':text[:256]},deadline_ms=3000)
    @Slot(str)
    def cancelCapability(self,capability):
        if self.pluginsAvailable:self._preferences('capability_cancel',capability=capability)
    @Slot(str,str)
    def invokeCapabilityJson(self,capability,jsonText):
        """B7: developer invocation with a JSON object (2 KiB). Refusals stay here; the deadline is 10 s, or 30 s for the model selftest."""
        message,value,deadline=capability_request(capability,jsonText)
        if message is None and self.capability_pending:message='Já há uma capacidade em execução; aguarde ou cancele'
        if message is None and self._models_busy_now():message=CODE_MESSAGES['busy']
        if message is None and not self.pluginsAvailable:message='Plugins indisponíveis agora: o Core precisa estar conectado, sem sessão de voz e com catálogo verificado'
        if message is not None:self.results['plugin']=message;self.changed.emit();return
        self.plugin_capability=capability
        self._preferences('capability_invoke',capability=capability,input=value,deadline_ms=deadline)
    @Property(bool,notify=changed)
    def capabilityPending(self):return bool(self.capability_pending)
    @Property(str,notify=changed)
    def capabilityInFlight(self):return self.plugin_capability if self.capability_pending else ''
    @Property(bool,notify=changed)
    def hubImportActive(self):return self.online and bool((self.snapshot.get('hub') or {}).get('import'))
    @Property(str,notify=changed)
    def hubImportDescription(self):
        transfer=(self.snapshot.get('hub') or {}).get('import')
        return f"Preparando {transfer['plugin_id']}: {transfer['received']}/{transfer['expected']} bytes" if transfer else ''
    @Slot()
    def abortHubImport(self):
        if self.hub_upload is not None:self.hub_upload['cancel']=True
        if self.hubImportActive:self._preferences('hub_abort',import_id=self.snapshot['hub']['import']['import_id'])
    # ---- Hub payload import (WP-4, Gideon Hub). The Core has the staged-payload protocol (hub_begin, hub_chunk, hub_finish,
    # hub_abort); this slot reads the file the user picked and sends it in 1 KiB chunks, one request in flight on this socket.
    # The Core verifies the bytes and stages them. Nothing is installed here: installing stays a separate, confirmed action.
    @Property(bool,notify=changed)
    def hubImportPickable(self):return self.hubLifecycleAvailable and not self.hubImportActive and self.hub_upload is None
    @Slot(str,str,result=str)
    def importHubPayload(self,plugin_id,location):
        """Starts the upload of the payload for an approved catalog entry. Returns '' when it started, else the refusal text."""
        hub=self.snapshot.get('hub') or {}
        entry=next((e for e in hub.get('entries',[]) if e.get('plugin_id')==plugin_id),None)
        if not self.hubImportPickable:return self._hub_refuse(self._prefs_unavailable_text() if not self.hubLifecycleAvailable else HUB_UPLOAD_MESSAGES['busy'])
        if entry is None or entry.get('status') not in ('not_installed','update_available') or entry.get('permissions_approved') is not True or entry.get('payload_staged') is True:
            return self._hub_refuse(HUB_UPLOAD_MESSAGES['entry'])
        path=unquote(urlsplit(location).path) if isinstance(location,str) and location.startswith('file://') else location
        if not isinstance(path,str) or not os.path.isabs(path) or '\x00' in path:return self._hub_refuse(HUB_UPLOAD_MESSAGES['path'])
        try:handle=os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb')
        except OSError:return self._hub_refuse(HUB_UPLOAD_MESSAGES['unreadable'])
        meta=os.fstat(handle.fileno())
        if not stat.S_ISREG(meta.st_mode):handle.close();return self._hub_refuse(HUB_UPLOAD_MESSAGES['path'])
        if meta.st_size!=entry.get('download_size'):handle.close();return self._hub_refuse(HUB_UPLOAD_MESSAGES['size'])
        self.hub_upload={'plugin_id':plugin_id,'handle':handle,'size':meta.st_size,'offset':0,'sent':0,'import_id':None,'inflight':None,'failure':None,'cancel':False,'revision':int(hub.get('approval_revision',0)),'manifest':entry.get('manifest_sha256')}
        self.results['hub']=HUB_UPLOAD_MESSAGES['sending']
        self._hub_upload_pump(None,None)
        self.changed.emit()
        return ''
    def _hub_refuse(self,message):
        self.results['hub']=message;self.changed.emit();return message
    def _hub_upload_drop(self):
        if self.hub_upload is not None:
            try:self.hub_upload['handle'].close()
            except OSError:pass
        self.hub_upload=None
    def _hub_upload_done(self,code):
        self.results['hub']=HUB_UPLOAD_MESSAGES['staged'] if code=='ok' else (HUB_UPLOAD_MESSAGES.get(code) or code_message(code))
        self._hub_upload_drop();self.changed.emit()
    def _hub_upload_pump(self,op,data):
        """Called after every Core answer and on start. Settles the request in flight, then sends the next step."""
        up=self.hub_upload
        if up is None:return
        if up['inflight'] is not None and op==up['inflight']:
            up['inflight']=None;code=(data or {}).get('code','invalid_message')
            if op=='hub_begin' and code=='ok':
                up['import_id']=((data.get('hub') or {}).get('import') or {}).get('import_id')
                if not up['import_id']:code='hub_import_missing'
            if op=='hub_chunk' and code=='ok':up['offset']+=up['sent']
            if op=='hub_finish':
                if code=='ok':return self._hub_upload_done('ok')
                up['failure']=code
            elif op=='hub_abort':return self._hub_upload_done(up['failure'] or code)
            elif code!='ok':up['failure']=code
        if self.pending or up['inflight'] is not None:return
        if up['failure'] is not None or up['cancel']:
            if up['import_id'] is None:return self._hub_upload_done(up['failure'] or 'cancelled')
            return self._hub_upload_send('hub_abort',import_id=up['import_id'])
        if up['import_id'] is None:return self._hub_upload_send('hub_begin',revision=up['revision'],plugin_id=up['plugin_id'],manifest_sha256=up['manifest'])
        chunk=up['handle'].read(HUB_CHUNK_BYTES)
        if chunk:
            up['sent']=len(chunk);self.results['hub']=HUB_UPLOAD_MESSAGES['progress'].format(done=min(up['size'],up['offset']+len(chunk)),total=up['size'])
            return self._hub_upload_send('hub_chunk',import_id=up['import_id'],offset=up['offset'],hex=chunk.hex())
        return self._hub_upload_send('hub_finish',import_id=up['import_id'])
    def _hub_upload_send(self,op,**kw):
        self.hub_upload['inflight']=op
        if not self._request(op,**kw):self.hub_upload['inflight']=None;self._hub_upload_done('core_offline')
    @Property('QVariantList',notify=hubEntriesChanged)
    def hubEntries(self):return (self.snapshot.get('hub') or {}).get('entries',[])
    @Property(str,notify=changed)
    def hubDescription(self):
        hub=self.snapshot.get('hub')
        if not self.online:return 'Core offline'
        if not hub:return 'Catálogo não configurado'
        if hub['status']=='quarantined':return 'Catálogo em quarentena; Base continua disponível'
        if hub.get('publisher_verified') is True:return 'Catálogo local com checksum verificado; publisher verificado por assinatura. Plugins instalados ficam desativados até ativação explícita; ativos rodam em sandbox sem rede.'
        return 'Catálogo local com checksum verificado; publisher não autenticado. Plugins instalados ficam desativados até ativação explícita; ativos rodam em sandbox sem rede.'
    # EXT-01 / SKILL-02: the publisher state is the Core flag, never a constant. The Core sets it only when every plugin of the catalog verifies.
    @Property(bool,notify=changed)
    def hubPublisherVerified(self):return (self.snapshot.get('hub') or {}).get('publisher_verified') is True
    @Property(bool,notify=changed)
    def connected(self):return self.online
    @Property(str,notify=changed)
    def state(self):return 'safe_mode' if self.configurationStatus=='safe_mode' else 'restart_required' if self.configurationStatus=='restart_required' else self.snapshot.get('state','offline')
    @Property(str,notify=sessionChanged)
    def sessionId(self):return self.snapshot.get('session_id','')
    @Property(str,notify=sessionChanged)
    def subtitle(self):return (self.snapshot.get('transcript') or {}).get('raw','')
    @Property(bool,notify=sessionChanged)
    def partial(self):return bool(self.snapshot.get('transcript')) and not self.snapshot['transcript']['is_final']
    @Property(str,notify=sessionChanged)
    def result(self):
        c=self.snapshot.get('command') or {};r=c.get('receipt')
        return display_receipt(r['result']) if r else COMMAND_CODE_MESSAGES.get(c.get('code',''),c.get('code',''))
    @Property(bool,notify=sessionChanged)
    def resultVerified(self):return bool((self.snapshot.get('command') or {}).get('receipt',{})) and bool(self.snapshot['command']['receipt']['verified'])
    @Property(str,notify=changed)
    def diagnostic(self):
        if not self.online:return self.error
        return self.configurationMessage or ' · '.join(DIAG_LABELS.get(self.snapshot.get(k,'unavailable'),'indisponível') for k in ('wake_status','stt_status','speech_status'))
    # ---- C4 perception and action. Only the allowlist above reaches the Core, as capability_invoke with a 5 s deadline; every answer is checked against its C4 rule before QML shows it.
    def _perception_items(self):
        entries={e.get('plugin_id'):e for e in (self.snapshot.get('hub') or {}).get('entries',[])}
        rows=[]
        for item in (self.snapshot.get('plugins') or {}).get('items',[]):
            if item['plugin_id'] in PERCEPTION_PLUGINS:
                entry=entries.get(item['plugin_id']) or {}
                rows.append({**item,'permissions':list(entry.get('permissions',[])),'approved':entry.get('permissions_approved') is True})
        return rows
    def _perception_running(self,capability):
        plugin=capability.split('.')[0]
        return any(i['plugin_id']==plugin and i['state']=='running' and capability in i['capabilities'] for i in self._perception_items())
    def _perception_busy_now(self):return self.perception_req is not None or self.perception_inflight is not None
    def _perception_touch(self):self.changed.emit();self.perceptionChanged.emit()
    def _perception_reset(self):
        """Connection lost: the invocation in flight ends here; the indicators are read again after reconnecting."""
        self.perception_req=None;self.perception_inflight=None;self.perception_before=None;self.perception_indicators={'mic':None,'camera':None}
        self.perceptionChanged.emit()
    def _perception_observe(self):
        req=self.perception_inflight
        if req is None:return
        result=self.snapshot.get('capability_result')
        # The first snapshot after the ack is the baseline: the Core clears the previous answer on every new invoke.
        if self.perception_before is PERCEPTION_ARM:self.perception_before=result;return
        if not result or result.get('capability')!=req['capability'] or result.get('plugin_id')!=req['plugin_id'] or result==self.perception_before:return
        self.perception_inflight=None;self.perception_before=None
        if req.get('silent'):return self._ptt_observe(req,result)
        if not result['ok']:self.results['perception']=perception_code_message(result['error'])
        elif not PERCEPTION_OUTPUTS[req['capability']](result.get('output')):self.results['perception']='Resposta do plugin recusada pelo esquema; nada exibido'
        else:
            output=result['output'];self.results['perception']=perception_text(output)
            if 'indicator' in output and req['capability'].startswith('mic_advanced.'):self.perception_indicators['mic']=output['indicator']
            if 'indicator' in output and req['capability'].startswith('camera_gesture.'):self.perception_indicators['camera']=output['indicator']
            if req['capability'] in PERCEPTION_STATUS_CAPABILITIES:self.perception_status[req['capability']]=dict(output)
        self._perception_touch();self._perception_pump()
    @Property(bool,notify=changed)
    def perceptionAvailable(self):return self.online and any(i['state']=='running' for i in self._perception_items())
    # WP-17: real status reads for Configurações > Dispositivos (camera and screen). Read one at a time, through the same invoke path.
    @Slot()
    def perceptionRefreshStatus(self):
        self.perception_status_queue=[c for c in PERCEPTION_STATUS_CAPABILITIES if self._perception_running(c)]
        self._perception_pump()
    def _perception_pump(self):
        if self.perception_status_queue and not self._perception_busy_now() and self.perception_req is None:
            self.perceptionInvoke(self.perception_status_queue.pop(0),'{}')
    # WP-17 push-to-talk. The owner switches it on in Configurações (consent asked there). The bridge binds the shortcut once,
    # then reads its events every 0.9 s; each activation is a listen_start (the Core still applies the microphone consent).
    @Slot(bool,str)
    def setPushToTalk(self,on,trigger):
        if on is not True and on is not False:return
        if not isinstance(trigger,str) or re.fullmatch(r'[A-Za-z0-9+_ ]{1,32}',trigger) is None:trigger='CTRL+ALT+G'
        self.ptt.update(enabled=on,trigger=trigger.strip() or 'CTRL+ALT+G',state='binding' if on else 'off',message='')
        if on:self.ptt_timer.start();self._ptt_tick()
        else:self.ptt_timer.stop();self.perception_status_queue=[]
        self._ptt_touch()
    @Property(str,notify=perceptionChanged)
    def pushToTalkState(self):return self.ptt['state']
    @Property(str,notify=perceptionChanged)
    def pushToTalkMessage(self):return self.ptt['message']
    @Property(str,notify=perceptionChanged)
    def pushToTalkTrigger(self):return self.ptt['trigger']
    def _ptt_touch(self):self.perceptionChanged.emit()
    def _ptt_tick(self):
        if not self.ptt['enabled']:return
        if not self.online:self.ptt.update(state='offline',message='Core offline: o atalho volta quando o Core responder');return self._ptt_touch()
        if not self._perception_running('shortcut_global.bind'):
            self.ptt.update(state='plugin_unavailable',message='Plugin shortcut_global não está em execução: aprove-o no Gideon Hub (permissão atalho global)');return self._ptt_touch()
        if self._perception_busy_now() or self.pending:return
        capability='shortcut_global.events' if self.ptt['state']=='bound' else 'shortcut_global.bind'
        payload={} if capability=='shortcut_global.events' else {'id':'ptt_toggle','trigger':self.ptt['trigger']}
        self.perception_req={'capability':capability,'plugin_id':'shortcut_global','silent':True}
        if not self._request('capability_invoke',capability=capability,input=payload,deadline_ms=PERCEPTION_DEADLINE_MS):self.perception_req=None
    def _ptt_observe(self,req,result):
        if not result['ok']:
            # A refused bind stops the poll (no retry loop); the owner switches it on again after fixing the cause.
            if req['capability']=='shortcut_global.bind':self.ptt_timer.stop();self.ptt.update(state='error',message=perception_code_message(result['error']))
            else:self.ptt.update(message=perception_code_message(result['error']))
            return self._ptt_touch()
        output=result.get('output')
        if req['capability']=='shortcut_global.bind':
            if not PERCEPTION_OUTPUTS[req['capability']](output):self.ptt.update(state='error',message='Resposta do atalho recusada pelo esquema');return self._ptt_touch()
            self.ptt.update(state='bound',message=f"Atalho {output['trigger']} registrado pelo {output['backend']}");return self._ptt_touch()
        if not PERCEPTION_OUTPUTS[req['capability']](output):self.ptt.update(state='error',message='Eventos do atalho recusados pelo esquema');return self._ptt_touch()
        if any(e['id']=='ptt_toggle' for e in output['events']):self.listenStart()
        self._ptt_touch()
    @Property('QVariantMap',notify=perceptionChanged)
    def perceptionCameraStatus(self):return dict(self.perception_status.get('camera_gesture.state') or {})
    @Property('QVariantMap',notify=perceptionChanged)
    def perceptionScreenStatus(self):return dict(self.perception_status.get('screen_observe.status') or {})
    @Property('QVariantList',notify=perceptionChanged)
    def perceptionPlugins(self):return self._perception_items()
    @Property(bool,notify=perceptionChanged)
    def perceptionBusy(self):return self._perception_busy_now()
    @Property(str,notify=perceptionChanged)
    def perceptionResult(self):return self.results['perception']
    def _indicator_text(self,plugin,value):
        if not any(i['plugin_id']==plugin and i['state']=='running' for i in self._perception_items()):return 'plugin inativo'
        # The worker reports 'on'/'off'; older synthetic answers used booleans. Anything else is not a reading.
        return PERCEPTION_UNREAD if value is None else ('ligado' if value in ('on', True) else 'desligado')
    @Property(str,notify=perceptionChanged)
    def perceptionMicIndicator(self):return self._indicator_text('mic_advanced',self.perception_indicators['mic'])
    @Property(str,notify=perceptionChanged)
    def perceptionCameraIndicator(self):return self._indicator_text('camera_gesture',self.perception_indicators['camera'])
    @Slot(str,str)
    def perceptionInvoke(self,capability,text):
        problem=perception_input_problem(capability,text)
        if problem is None and not self._perception_running(capability):problem=CODE_MESSAGES['capability_unavailable']
        if problem is None and self._perception_busy_now():problem='Aguarde a ação de percepção anterior'
        if problem is None and self.pending:problem=CODE_MESSAGES['busy']
        if problem is None and (self.chat_inflight is not None or self.chat_request is not None or self.pending_chat):problem='Aguarde a conversa terminar'
        if problem is None and self._models_busy_now():problem='Aguarde o gerenciador de modelos'
        if problem is None and self._agent_active():problem=CODE_MESSAGES['agent_busy']
        if problem is not None:self.results['perception']=problem;self._perception_touch();return
        self.perception_req={'capability':capability,'plugin_id':capability.split('.')[0]}
        if self._request('capability_invoke',capability=capability,input=json.loads(text),deadline_ms=perception_deadline(capability)):self.results['perception']=PENDING['capability_invoke']
        else:self.perception_req=None;self.results['perception']='Core indisponível'
        self._perception_touch()
    # ---- S4 skills (docs/S4.md). The Core decides every transition and every permission; the bridge refuses what it can see is impossible, sends one bounded request at a time and shows the snapshot 'skills' block.
    def _skills_ready(self):return self.online and isinstance(self.snapshot.get('skills'),dict)
    def _skill_block(self):return self.snapshot.get('skills') or {}
    def _skill_revision(self):return int(self._skill_block().get('revision',0))
    def _skill_run(self):return self._skill_block().get('run')
    def _skill_run_active(self):
        run=self._skill_run();return run is not None and run['state'] in ('running','awaiting_approval')
    def _skill_import(self):return self._skill_block().get('import')
    def _skill_busy_now(self):return self.skill_req is not None or self.skill_inflight is not None
    def _skills_touch(self):self.changed.emit()
    def _skill_op(self,op,**kw):
        """One Core request on the skills channel. Refused while unavailable or while another request is in flight; never queued."""
        if not self._skills_ready():return self._refuse('skills','Skills indisponíveis agora')
        if self._skill_busy_now():return self._refuse('skills',CODE_MESSAGES['busy'])
        return self._send('skills',op,**kw)
    def _skill_by_id(self,op,ident):
        """Lifecycle ops carry the live ledger revision, like the plugin ops: the Core refuses a revision it no longer has."""
        problem=skill_id_problem(ident)
        if problem is not None:return self._refuse('skills',problem)
        self._skill_op(op,id=ident,revision=self._skill_revision())
    def _skill_manifest(self,op,text):
        value,problem=skill_json(text)
        if problem is not None:return self._refuse('skills',problem)
        self._skill_op(op,manifest=value)
    @Slot(str)
    def skillValidate(self,text):self._skill_manifest('skill_validate',text)
    @Slot(str)
    def skillSaveDraft(self,text):self._skill_manifest('skill_save_draft',text)
    @Slot(str,str,str)
    def skillDryRun(self,ident,version,inputs):
        value,problem=skill_json(inputs);problem=skill_id_problem(ident,version) or problem
        if problem is not None:return self._refuse('skills',problem)
        self._skill_op('skill_dry_run',id=ident,skill_version=version,inputs=value)
    @Slot(str,str)
    def skillApprove(self,ident,version):
        problem=skill_id_problem(ident,version)
        if problem is not None:return self._refuse('skills',problem)
        self._skill_op('skill_approve',id=ident,skill_version=version,revision=self._skill_revision())
    @Slot(str)
    def skillEnable(self,ident):self._skill_by_id('skill_enable',ident)
    @Slot(str)
    def skillDisable(self,ident):self._skill_by_id('skill_disable',ident)
    @Slot(str)
    def skillRollback(self,ident):self._skill_by_id('skill_rollback',ident)
    @Slot(str)
    def skillRemove(self,ident):self._skill_by_id('skill_remove',ident)
    @Slot(str,str)
    def skillRun(self,ident,inputs):
        value,problem=skill_json(inputs);problem=skill_id_problem(ident) or problem
        if problem is None and self._skill_run_active():problem=CODE_MESSAGES['skill_busy']
        if problem is not None:return self._refuse('skills',problem)
        self._skill_op('skill_run',id=ident,inputs=value)
    @Slot(str,str,str)
    def skillDecide(self,runId,step,decision):
        """Only a step the Core is waiting on can be decided; authorize and deny are the two answers, as in tool_decide."""
        run=self._skill_run();states={s['id']:s['state'] for s in (run or {}).get('steps',[])}
        if decision not in ('authorize','deny') or not run or run['run_id']!=runId or states.get(step)!='awaiting_approval':return self._refuse('skills',CODE_MESSAGES['not_pending'])
        self._skill_op('skill_decide',run_id=runId,step=step,decision=decision)
    @Slot(str)
    def skillCancel(self,runId):
        run=self._skill_run()
        if not run or run['run_id']!=runId or not self._skill_run_active():return self._refuse('skills',CODE_MESSAGES['unknown_skill_run'])
        self._skill_op('skill_cancel',run_id=runId)
    @Slot(str,str)
    def skillExport(self,ident,version):
        problem=skill_id_problem(ident,version)
        if problem is not None:return self._refuse('skills',problem)
        self._skill_op('skill_export',id=ident,skill_version=version)
    @Slot(str)
    def skillImport(self,name):
        if not SKILL_IMPORT_NAME.fullmatch(name):return self._refuse('skills','Nome inválido: letras, números, . _ - (até 64)')
        self._skill_op('skill_import',name=name)
    @Slot(str)
    def skillImportConfirm(self,name):
        preview=self._skill_import()
        if not preview or preview['name']!=name:return self._refuse('skills',CODE_MESSAGES['stale_import'])
        self._skill_op('skill_import_confirm',name=name,revision=self._skill_revision())
    def _skill_llm_available(self):
        return self.online and any(i['plugin_id']==SKILL_DRAFT_PLUGIN and i['state']=='running' and SKILL_DRAFT_CAPABILITY in i['capabilities'] for i in (self.snapshot.get('plugins') or {}).get('items',[]))
    @Slot(str)
    def skillDraftWithLlm(self,description):
        """llm_engine.skill_draft through capability_invoke (30 s). Only when the LLM plugin runs; the draft is created by the Core as draft, never enabled."""
        problem=skill_description_problem(description)
        if problem is None and not self._skill_llm_available():problem=CODE_MESSAGES['capability_unavailable']
        if problem is None and (self._skill_busy_now() or self.pending or self.capability_pending or self.perception_req is not None or self.perception_inflight is not None or self._models_busy_now() or self._agent_active() or self.chat_inflight is not None or self.chat_request is not None or self.pending_chat):problem=CODE_MESSAGES['busy']
        if problem is not None:return self._refuse('skills',problem)
        self.skill_req={'capability':SKILL_DRAFT_CAPABILITY,'plugin_id':SKILL_DRAFT_PLUGIN};self.skill_draft={}
        if self._request('capability_invoke',capability=SKILL_DRAFT_CAPABILITY,input={'description':description.strip()},deadline_ms=SKILL_DRAFT_DEADLINE_MS):self.results['skills']=PENDING_SKILL_DRAFT
        else:self.skill_req=None;self.results['skills']='Core indisponível'
        self._skills_touch()
    def _skill_reset(self):
        """Connection lost: a draft in flight ends here and nothing is re-sent; the Core keeps whatever it already wrote."""
        self.skill_req=None;self.skill_inflight=None;self.skill_before=None;self.skill_draft={}
        self._skills_touch()
    def _skill_observe(self):
        """Finishes the one awaited draft. The first snapshot after the ack is the baseline (the Core clears the previous answer on each invoke)."""
        req=self.skill_inflight
        if req is None:return
        result=self.snapshot.get('capability_result')
        if self.skill_before is SKILL_ARM:self.skill_before=result;return
        if not result or result.get('capability')!=req['capability'] or result.get('plugin_id')!=req['plugin_id'] or result==self.skill_before:return
        self.skill_inflight=None;self.skill_before=None
        if not result['ok']:self.skill_draft={};self.results['skills']=code_message(result['error'])
        elif not valid_skill_draft(result.get('output')):self.skill_draft={};self.results['skills']='Resposta do plugin recusada pelo esquema; nada exibido'
        else:
            output=result['output'];self.skill_draft=dict(output)
            self.results['skills']=f"Rascunho {output['draft_id']} v{output['version']} criado como {output['state']}; revise e valide antes de usar"
        self._skills_touch()
    @Property(bool,notify=changed)
    def skillsAvailable(self):return self._skills_ready()
    @Property(bool,notify=changed)
    def skillsBusy(self):return self.pending_op in SKILL_OPS or self._skill_busy_now()
    @Property(bool,notify=changed)
    def skillLlmAvailable(self):return self._skill_llm_available()
    @Property(str,notify=skillsChanged)
    def skillsRevision(self):return str(self._skill_block().get('revision',0))
    @Property(str,notify=changed)
    def skillsResult(self):return self.results['skills']
    @Property('QVariantList',notify=skillsChanged)
    def skillsItems(self):return [{**i,'permissionsRequired':list(i.get('permissions_required') or [])} for i in self._skill_block().get('items',[])]
    # WP-15 / SKILL-03: the last export (package path, shown to the user) and the listed GitHub index (never fetched here).
    @Property('QVariantMap',notify=skillsChanged)
    def skillLastExport(self):return dict(self._skill_block().get('last_export') or {})
    @Property('QVariantMap',notify=skillsChanged)
    def skillIndex(self):return dict(self._skill_block().get('index') or {})
    @Property(str,notify=changed)
    def listenResult(self):return self.results.get('listen','')
    @Property('QVariantMap',notify=skillsChanged)
    def skillPaths(self):return dict(self._skill_block().get('paths') or {})
    # Named skillCurrentRun, not skillRun: the Qt property and the skillRun slot would share one name in QML.
    @Property('QVariantMap',notify=skillsChanged)
    def skillCurrentRun(self):return dict(self._skill_run() or {})
    @Property('QVariantList',notify=skillsChanged)
    def skillHistory(self):return [dict(e) for e in self._skill_block().get('history',[])]
    @Property('QVariantMap',notify=skillsChanged)
    def skillImportPreview(self):return dict(self._skill_import() or {})
    @Property('QVariantMap',notify=changed)
    def skillDraftOutput(self):return dict(self.skill_draft)
    # ---- S5 connections (docs/S5.md E1, UI). The Core owns accounts, consent, secrets and every call. The bridge refuses what it can see is impossible, sends one bounded request per click and shows the snapshot 'connections' block.
    def _conn_block(self):return self.snapshot.get('connections') or {}
    def _conn_ready(self):return self.online and isinstance(self.snapshot.get('connections'),dict)
    def _conn_revision(self):return int(self._conn_block().get('revision',0))
    def _conn_item(self,ident):return next((i for i in self._conn_block().get('items',[]) if i['id']==ident),None)
    def _conn_op(self,op,**kw):
        """One Core request on the connections channel: refused while unavailable or while another request is in flight; never queued."""
        if not self._conn_ready():self._refuse('connections',CONN_MESSAGES['connection_unavailable']);return
        if self.pending:self._refuse('connections',CODE_MESSAGES['busy']);return
        self._send('connections',op,**kw)
    def _conn_unknown(self,ident):
        """True when the id is malformed or not in the live block (refused here, so it never reaches the Core)."""
        if not conn_id_ok(ident):self._refuse('connections','Id de conta inválido');return True
        if self._conn_item(ident) is None:self._refuse('connections',CONN_MESSAGES['unknown_connection']);return True
        return False
    @Slot(str,str)
    def connectionAdd(self,provider,label):
        problem=conn_provider_problem(provider) or conn_label_problem(label)
        if problem is not None:self._refuse('connections',problem);return
        if len(self._conn_block().get('items',[]))>=CONN_ITEMS_LIMIT:self._refuse('connections',CONN_MESSAGES['connection_limit']);return
        self._conn_op('connection_add',provider=provider,label=label.strip(),revision=self._conn_revision())
    @Slot(str)
    def connectionConnect(self,ident):
        if self._conn_unknown(ident):return
        self._conn_op('connection_connect',id=ident,revision=self._conn_revision())
    @Slot(str,str)
    def connectionConsent(self,ident,scopes):
        """Consent is per scope: a non-empty subset of the scopes the account is waiting for, nothing else."""
        if self._conn_unknown(ident):return
        try:value=json.loads(scopes,parse_constant=_no_constant)
        except (ValueError,RecursionError):self._refuse('connections',CONN_MESSAGES['connection_consent_required']);return
        pending=set(self._conn_item(ident).get('pending_scopes') or [])
        if not conn_scope_list(value) or not value or not set(value)<=pending:self._refuse('connections',CONN_MESSAGES['connection_consent_required']);return
        self._conn_op('connection_consent',id=ident,scopes=value,revision=self._conn_revision())
    def _conn_lifecycle(self,op,ident):
        if self._conn_unknown(ident):return
        self._conn_op(op,id=ident,revision=self._conn_revision())
    @Slot(str)
    def connectionRefresh(self,ident):self._conn_lifecycle('connection_refresh',ident)
    @Slot(str)
    def connectionDisconnect(self,ident):self._conn_lifecycle('connection_disconnect',ident)
    @Slot(str)
    def connectionRevoke(self,ident):self._conn_lifecycle('connection_revoke',ident)
    @Slot(str,str)
    def connectionRevokeScope(self,ident,scope):
        """One granted scope (connection_revoke_scope {id, scope, revision}). Refused here when the live item does not grant it; the Core checks the revision."""
        if self._conn_unknown(ident):return
        if not isinstance(scope,str) or scope not in (self._conn_item(ident).get('granted_scopes') or []):return self._refuse('connections',CONN_MESSAGES['scope_not_granted'])
        self._conn_op('connection_revoke_scope',id=ident,scope=scope,revision=self._conn_revision())
    @Slot(str)
    def connectionRemove(self,ident):self._conn_lifecycle('connection_remove',ident)
    @Slot(str,str,str)
    def connectionCall(self,ident,operation,args):
        """Operation call for an account. Refused here when the account is not connected, the operation is unknown or its scope is not granted: no network call happens for those."""
        if self._conn_unknown(ident):return
        item=self._conn_item(ident);provider=next((p for p in self._conn_block().get('providers',[]) if p['id']==item['provider']),{})
        try:value=json.loads(args,parse_constant=_no_constant)
        except (ValueError,RecursionError,TypeError):self._refuse('connections',CONN_MESSAGES['connection_args_invalid']);return
        if not isinstance(value,dict) or not bounded_json(value,CONN_ARGS_LIMIT):self._refuse('connections',CONN_MESSAGES['connection_args_invalid']);return
        spec=next((o for o in provider.get('operations',[]) if isinstance(operation,str) and o['name']==operation),None)
        if spec is None:self._refuse('connections',CONN_MESSAGES['unknown_operation']);return
        if item['status']!='connected':self._refuse('connections',CONN_MESSAGES['not_connected']);return
        if spec['scope'] not in item['granted_scopes']:self._refuse('connections',CONN_MESSAGES['scope_not_granted']);return
        self._conn_op('connection_call',id=ident,operation=operation,args=value)
    @Slot(str,str)
    def connectionSetToken(self,ident,token):
        """Home Assistant (docs/S5.md E2.3): the long-lived token goes once to the Core, which validates it with one probe.
        The bridge keeps no copy beyond the request; the page clears its field right after this call."""
        if self._conn_unknown(ident):return
        if not conn_token_ok(token):self._refuse('connections',CONN_MESSAGES['invalid_token']);return
        if self._conn_item(ident)['provider']!='homeassistant':self._refuse('connections',CONN_MESSAGES['invalid_state']);return
        self._conn_op('connection_set_token',id=ident,token=token,revision=self._conn_revision())
    @Slot(str,str)
    def connectionTrustTools(self,ident,names):
        """MCP (docs/S5.md E2.4): the user re-approves discovered tools by name. Only tools the snapshot lists as needs_reapproval are sent; trusting never grants a scope and every call still needs its own approval."""
        if self._conn_unknown(ident):return
        item=self._conn_item(ident)
        if item['provider']!='mcp':self._refuse('connections',CONN_MESSAGES['invalid_state']);return
        try:value=json.loads(names,parse_constant=_no_constant)
        except (ValueError,RecursionError,TypeError):self._refuse('connections',CONN_MESSAGES['connection_args_invalid']);return
        waiting={t['name'] for t in item.get('tools',[]) if t['state']=='needs_reapproval'}
        if not (isinstance(value,list) and 0<len(value)<=CONN_TRUST_LIMIT and all(isinstance(n,str) for n in value) and len(set(value))==len(value) and set(value)<=waiting):self._refuse('connections',CONN_MESSAGES['tool_trust_invalid']);return
        self._conn_op('connection_trust_tools',id=ident,tools=value,revision=self._conn_revision())
    @Slot(str,result=str)
    def connectionLabelProblem(self,label):return conn_label_problem(label) or ''
    @Property(bool,notify=changed)
    def connectionsAvailable(self):return self._conn_ready()
    @Property(bool,notify=changed)
    def connectionsBusy(self):return self.pending_op in CONN_OPS
    @Property(str,notify=changed)
    def connectionsResult(self):return self.results['connections']
    @Property(str,notify=connectionsChanged)
    def connectionsRevision(self):return str(self._conn_block().get('revision',0))
    @Property('QVariantList',notify=connectionsChanged)
    def connectionsItems(self):return [{**i,'grantedAtMs':i.get('granted_at_ms')} for i in self._conn_block().get('items',[])]
    @Property('QVariantList',notify=connectionsChanged)
    def connectionsProviders(self):return [dict(p) for p in self._conn_block().get('providers',[])]
    @Property('QVariantMap',notify=connectionsChanged)
    def connectionLastCall(self):return dict(self._conn_block().get('last_call') or {})
    # ---- S5 E3 CapabilityRegistry (docs/S5.md E3, UI). The Core picks routes and owns the visual permission; this page only asks for a plan or flips the user's switch for one purpose. Nothing here executes a route.
    def _reg_block(self):return self.snapshot.get('registry') or {}
    def _reg_ready(self):return self.online and isinstance(self.snapshot.get('registry'),dict)
    def _reg_op(self,op,**kw):
        """One Core request on the registry channel: refused while unavailable or while another request is in flight; never queued."""
        if not self._reg_ready():self._refuse('registry',REG_MESSAGES['registry_unavailable']);return
        if self.pending:self._refuse('registry',CODE_MESSAGES['busy']);return
        self._send('registry',op,**kw)
    @Slot(str)
    def registryPlan(self,purpose):
        if purpose not in REG_PURPOSES:self._refuse('registry',REG_MESSAGES['unknown_purpose']);return
        self._reg_op('registry_plan',purpose=purpose)
    @Slot(str,bool)
    def registryAllowVisual(self,purpose,enabled):
        """The user's switch (default off). Refused here for an unknown purpose or one with no visual route; the Core checks the revision."""
        if purpose not in REG_PURPOSES:self._refuse('registry',REG_MESSAGES['unknown_purpose']);return
        if purpose not in REG_VISUAL_PURPOSES:self._refuse('registry',REG_MESSAGES['no_visual_route']);return
        self._reg_op('registry_allow_visual',purpose=purpose,enabled=bool(enabled),revision=int(self._reg_block().get('revision',0)))
    @Property(bool,notify=changed)
    def registryAvailable(self):return self._reg_ready()
    @Property(bool,notify=changed)
    def registryBusy(self):return self.pending_op in ('registry_plan','registry_allow_visual')
    @Property(str,notify=changed)
    def registryResult(self):return self.results['registry']
    @Property(str,constant=True)
    def registryVisualWarning(self):return REG_VISUAL_WARNING
    @Property(str,notify=registryChanged)
    def registryRevision(self):return str(self._reg_block().get('revision',0))
    @Property('QVariantList',notify=registryChanged)
    def registryPurposes(self):return [dict(p) for p in self._reg_block().get('purposes',[])]
    @Property('QVariantList',notify=registryChanged)
    def registryVisualAllowed(self):return list(self._reg_block().get('visual_allowed',[]))
    # ---- B5-B10 (docs/PENDENCIAS_IMPLEMENTACAO.md): package identity, test wake, diagnostics of the last capture and reply, catalog storage.
    @Property('QVariantMap',constant=True)
    def packageInfo(self):return dict(self._package)
    @Property(str,constant=True)
    def coreRootPath(self):return str(self.root)
    # Permissões › Auditoria (docs/ui-spec/30 §11.6): the Core writes audit.log (and audit.log.1) in its root folder (src/storage.rs).
    @Property(str,constant=True)
    def auditLogPath(self):return str(self.root/'audit.log')
    @Property(bool,notify=changed)
    def virtualWakeAvailable(self):return self.online and self.configurationStatus=='ready' and not self.sessionId
    @Property(str,notify=changed)
    def wakeResult(self):return self.results['wake']
    @Slot()
    def virtualWake(self):
        """B6: the Core's test wake (op virtual_wake). The Core refuses it unless it was started with --virtual-input; that refusal arrives as virtual_input_disabled."""
        if not self.virtualWakeAvailable:
            self.results['wake']='Indisponível: o Core está desconectado' if not self.online else 'Indisponível: há uma sessão de voz em andamento' if self.sessionId else 'Indisponível agora: a configuração precisa estar pronta'
        else:self.results['wake']=PENDING['virtual_wake'] if self._request('virtual_wake') else CODE_MESSAGES['busy']
        self.changed.emit()
    @Property('QVariantMap',notify=sessionChanged)
    def captureSummary(self):return dict(self.snapshot.get('capture') or {})
    @Property('QVariantMap',notify=sessionChanged)
    def speechSummary(self):return dict(self.snapshot.get('speech') or {})
    @Property('QVariantMap',notify=sessionChanged)
    def transcriptSummary(self):return dict(self.snapshot.get('transcript') or {})
    @Property('QVariantMap',notify=changed)
    def hubStorage(self):return hub_storage(self.snapshot.get('hub'))
