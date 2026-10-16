"""Thin, bounded Qt IPC adapter. Core owns all parsing, sessions and authority."""
import datetime,hashlib,json,math,os,re,stat,unicodedata,uuid
from pathlib import Path
from urllib.parse import urlsplit
from PySide6.QtCore import QObject,Property,Signal,Slot,QTimer
from PySide6.QtNetwork import QLocalSocket
CAPABILITY_ID=re.compile(r'[a-z0-9_]+(\.[a-z0-9_]+)+');PLUGIN_ID=re.compile(r'[A-Za-z0-9_-]+');SNAKE_CODE=re.compile(r'[a-z][a-z0-9_]*')
PLUGIN_STATES=('disabled','starting','running','failed','stopped','quarantined')
# Exact status sets emitted by the Core (src/core.rs, src/transport.rs). Anything else is an invalid snapshot.
WAKE_STATES=('unavailable','starting','replaying','failed','replay_finished')
STT_STATES=('unavailable','starting','ready','failed')
SPEECH_STATES=('unavailable','idle','muted','disabled','speaking','completed','failed','cancelled','timed_out','audio_error','stt_failed','stt_unavailable','transcript_final','capture_completed','no_speech','capture_too_long')
OUTPUT_LIMIT=8192;TEXT_LIMIT=512;HEX=frozenset('0123456789abcdef')
# Runtime state of an installed plugin: `disabled` when not enabled, else the host state (src/plugins.rs runtime_of).
# `stopped` is a host state too (a late stop event can land after a re-enable), so it is accepted.
RUNTIME_STATES=('disabled','starting','running','failed','stopped')
# Codes Core writes to plugin last_error (src/plugins.rs runtime start, violation and crash paths).
PLUGIN_LAST_ERRORS=frozenset({'plugin_crashed','plugin_cpu_exceeded','plugin_output_invalid','plugin_start_failed','plugin_not_runnable','plugin_quarantined','handshake_timeout','handshake_mismatch'})
# Codes a capability_result can carry (src/plugins.rs PASS_THROUGH_ERRORS plus Core-owned results).
CAPABILITY_ERRORS=frozenset({'key_missing','cloud_not_authorized','provider_not_configured','permission_denied','http_error','timeout','response_too_large','network_unavailable','cancelled','invalid_input','host_not_allowed','redirect_refused','busy','invalid_host_call','plugin_error','plugin_not_runnable','plugin_output_invalid','plugin_cpu_exceeded','capability_unavailable','capability_timeout','invoke_cancelled','model_unsupported_feature','model_not_found','model_selftest_failed','settings_unavailable'})
# Tool proposal reasons (src/tools.rs and src/core.rs tool_denied/tool_failed).
TOOL_REASONS=frozenset({'superseded','expired','plugin_unavailable','executor_failed','executor_unavailable','user_denied','invalid_args','unknown_tool','busy'})
HUB_REASONS=('ledger_missing','ledger_invalid')
STAGED_ERRORS=('staged_payload_invalid',)
# Finish reasons of the capture session (src/core.rs finish), recorded in capture.reason.
CAPTURE_REASONS=('audio_error','cancelled','capture_completed','stt_failed','stt_unavailable','transcript_final','no_speech','capture_too_long')
STT_SOURCES=('voice','user_text')
COMMAND_KINDS={'open_app':('desktop_id',),'volume':('level',),'mute':(),'status':(),'time':(),'date':(),'cancel':()}
TOP_KEYS=frozenset({'version','request_id','code','state','session_id','sequence','events','plugins','llm','tool_proposals','text_input_available','speech_samples','speech_status','stt_status','wake_status','hub','capability_result','partial','base_pack','configuration_status','configuration_recovery_available','preferences','command','speech','transcript','capture'})
TOP_REQUIRED=frozenset({'version','request_id','code','state','session_id','sequence','events','plugins','llm','tool_proposals','text_input_available','speech_samples','speech_status','stt_status','wake_status'})
HUB_KEYS=frozenset({'version','status','publisher_verified','approval_revision','install_revision','installed','import','entries','orphans','reason','repository','catalog_sha256'})
HUB_REQUIRED=HUB_KEYS-{'reason'}
ENTRY_KEYS=frozenset({'manifest_sha256','permissions_approved','payload_staged','staged_error','plugin_id','semver','publisher','api_version','targets','license','permissions','dependencies','conflicts','download_size','support_policy','runtime','capabilities','status','reason'})
ENTRY_REQUIRED=ENTRY_KEYS-{'staged_error','runtime','capabilities'}
PREFERENCE_KEYS=frozenset({'version','session_timeout_ms','wake_phrase','revision','audible_feedback','visual_feedback','output_volume_percent','previous_preferences'})
PACK_KEYS=frozenset({'version','id','scope','preflight','engines','wake_phrases','active_phrase','default_phrase','voice','language','audio_input','audio_output'})
TRANSCRIPT_KEYS=frozenset({'source','session_id','revision','audio_end_us','raw','normalized','is_final','confidence'})
CAPTURE_KEYS=frozenset({'session_id','start_us','end_us','samples','pcm_sha256','reason'})
SPEECH_KEYS=frozenset({'output_volume_percent','session_id','sample_rate','samples','chunks','pcm_sha256','peak','rms','first_pcm_ms','elapsed_ms','sink'})
COMMAND_KEYS=frozenset({'session_id','code','receipt'})
RECEIPT_KEYS=frozenset({'job','verified','scope','result'})
JOB_KEYS=frozenset({'session_id','command'})
EVENT_KEYS=frozenset({'sequence','request_id','session_id','kind'})
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
LLM_PROVIDERS=('openrouter','opencode','google','custom');LLM_SECRET_KEYS=frozenset(LLM_PROVIDERS)
# C2 (docs/C2.md): local providers take a loopback port and never need a key or cloud consent.
LOCAL_PROVIDERS=('local','ollama');CONFIG_PROVIDERS=LLM_PROVIDERS+LOCAL_PROVIDERS;FIXED_CLOUD_PROVIDERS=('openrouter','opencode','google')
LOCAL_PORT_MIN,LOCAL_PORT_MAX=1024,65535
# The Core serializes config with local_port, fallback and lkg omitted when null (skip_serializing_if): they are optional keys.
LLM_CONFIG_REQUIRED=frozenset({'provider','model','custom_url','cloud_consent'});LLM_CONFIG_KEYS=LLM_CONFIG_REQUIRED|{'local_port','fallback','lkg'}
LKG_KEYS=frozenset({'provider','model','custom_url','local_port','cloud_consent'});LKG_REQUIRED=frozenset({'provider','model','custom_url','cloud_consent'})
FALLBACK_KEYS=frozenset({'provider','model','custom_url','local_port'})
LLM_URL_LIMIT=200
MODEL_ID=re.compile(r'[A-Za-z0-9._:/-]{1,128}');PROPOSAL_ID=re.compile(r'[A-Za-z0-9_]{1,64}')
TOOL_STATES=('pending','denied','authorized','executed','failed','expired','cancelled')
TOOL_KEYS=frozenset({'proposal_id','plugin_id','call_id','tool','args','state','reason','result'})
PARTIAL_LIMIT=16384;ARGS_LIMIT=8192;TOOL_NAME_LIMIT=256;RESULT_TEXT_LIMIT=1024;TOOL_ITEMS=4
CHAT_CAPABILITY_SUFFIX='.chat';CHAT_TEXT_LIMIT=4096;CHAT_CONTENT_LIMIT=4096;CHAT_INPUT_LIMIT=8192;CHAT_TURNS=31;CHAT_MAX_TOKENS=512;CHAT_DEADLINE_MS=10000;CHAT_MESSAGES_KEPT=64
HTTP_STATUS_KEY='http_status'
def is_int(value,minimum=0,maximum=2**64-1):return type(value) is int and minimum<=value<=maximum
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
    if not (isinstance(llm,dict) and set(llm)=={'revision','config','secrets'} and is_int(llm['revision'])):return False
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
SELFTEST_DEADLINE_MS=10000;MODELS_DEADLINE_MS=5000
PENDING_MODELS={'list':'Carregando modelos…','selftest':'Testando modelo…','save_custom':'Salvando modelo personalizado…','delete_custom':'Removendo modelo personalizado…'}
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
    """Core proposal view: at most four items, exact keys, PlainText strings, bounded args."""
    if not (isinstance(items,list) and len(items)<=TOOL_ITEMS):return False
    ids=set()
    for item in items:
        if not (isinstance(item,dict) and set(item)==TOOL_KEYS):return False
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
        previous=prefs.get('previous_preferences')
        if previous is not None:
            require(isinstance(previous,dict) and type(previous.get('audible_feedback')) is bool and integer(previous.get('session_timeout_ms'),50,60000))
            if 'visual_feedback' in previous:require(type(previous['visual_feedback']) is bool)
            if 'output_volume_percent' in previous:require(integer(previous['output_volume_percent'],0,100))
        wake=prefs.get('wake_phrase')
        require(wake is None or (short(wake) and len(wake)>0 and all(c.isascii() and (c.isalnum() or c in '_-') for c in wake)))
    hub=data.get('hub')
    if hub is not None:
        require(isinstance(hub,dict) and type(hub.get('version')) is int and hub['version']==1)
        require(set(hub)<=HUB_KEYS and HUB_REQUIRED<=set(hub))
        require(hub.get('status') in ('verified','quarantined') and hub.get('publisher_verified') is False)
        require(integer(hub['approval_revision']) and integer(hub['orphans']))
        if 'reason' in hub:require(hub['status']=='quarantined' and hub['reason'] in HUB_REASONS)
        if hub.get('import') is not None:
            transfer=hub['import'];require(isinstance(transfer,dict) and set(transfer)=={'import_id','plugin_id','received','expected'} and short(transfer.get('import_id')) and short(transfer.get('plugin_id')) and integer(transfer.get('expected'),1,67108864) and integer(transfer.get('received'),0,transfer['expected']))
        entries=hub.get('entries');require(isinstance(entries,list) and len(entries)<=8 and all(isinstance(e,dict) and set(e)<=ENTRY_KEYS and ENTRY_REQUIRED<=set(e) for e in entries))
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
    partial=data.get('partial')
    require(partial is None or (isinstance(partial,str) and utf8_len(partial)<=PARTIAL_LIMIT))
    pack=data.get('base_pack')
    if pack is not None:
        require(isinstance(pack,dict) and type(pack.get('version')) is int and pack['version']==1)
        require(short(pack.get('id')) and pack.get('scope')=='dev_virtual_en' and pack.get('preflight')=='verified')
        require(set(pack)==PACK_KEYS and isinstance(pack.get('engines'),dict) and set(pack['engines'])=={'wake','stt','tts'} and all(short(v,160) for v in pack['engines'].values()))
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
        previous=-1
        for event in data['events']:
            require(isinstance(event,dict) and set(event)==EVENT_KEYS)
            require(integer(event.get('sequence')) and previous<event['sequence']<=data['sequence'])
            require(short(event.get('kind')) and short(event.get('request_id')))
            require('session_id' in event and (event['session_id'] is None or sid(event['session_id'])))
            previous=event['sequence']
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
    'capture_completed':'Captura concluída',
    'replaying':'Reprodução em andamento',
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
}
STALE_MESSAGE='Estado mudou; reabra a confirmação'
CHAT_STATE_LABELS={'idle':'Em espera','waiting':'Aguardando resposta','streaming':'Respondendo','done':'Concluída','error':'Erro','cancelled':'Cancelada'}
def code_message(code):return CODE_MESSAGES.get(code,f'Core recusou a ação: {code}')
# op -> (result channel, done message or builder). One table drives every Core answer.
OPS={
    'preferences':('prefs',PREFS_DONE),'rollback_preferences':('prefs',PREFS_DONE),'select_wake':('prefs',PREFS_DONE),'feedback_preferences':('prefs',PREFS_DONE),
    'recover_configuration':('prefs','Configuração recuperada; reinício necessário'),
    'hub_abort':('hub','Importação cancelada'),
    'hub_approve':('hub',lambda target:f'Permissões aprovadas: {target}'),
    'hub_install':('hub','Plugin instalado (desativado)'),'hub_rollback':('hub','Versão revertida'),'hub_remove':('hub','Plugin removido'),
    'plugin_enable':('plugin','Plugin ativado'),'plugin_disable':('plugin','Plugin desativado'),'plugin_revoke':('plugin','Permissões revogadas; plugin desativado'),
    'capability_invoke':('plugin',None),'capability_cancel':('plugin','Cancelamento enviado'),
    'text':('text','Texto enviado'),
    'secret_set':('llm','Chave salva pelo Core'),'secret_clear':('llm','Chave removida pelo Core'),'llm_configure':('llm','Configuração salva pelo Core'),
    'tool_decide':('tools','Decisão enviada ao Core'),
}
PENDING={'hub_approve':'Enviando aprovação ao Core','hub_abort':'Enviando cancelamento ao Core','hub_install':'Instalando no Core','hub_rollback':'Revertendo no Core','hub_remove':'Removendo no Core','plugin_enable':'Ativando plugin…','plugin_disable':'Desativando plugin…','plugin_revoke':'Revogando permissões…','capability_invoke':'Invocando capability…','capability_cancel':'Cancelando capability…','text':'Enviando texto ao Core',
    'secret_set':'Salvando chave no Core…','secret_clear':'Removendo chave no Core…','llm_configure':'Salvando configuração do motor…','tool_decide':'Enviando decisão ao Core…'}
# Snapshot keys grouped into sections; each section has its own NOTIFY signal so QML lists keep their delegates.
# 'partial' and the chat state share chatChanged: both move with one streamed chunk.
SECTION_SIGNALS={'entries':'hubEntriesChanged','installed':'hubInstalledChanged','hub':'hubChanged','plugins':'pluginsChanged','capability':'capabilityChanged','preferences':'preferencesChanged','pack':'packChanged','session':'sessionChanged','llm':'llmChanged','partial':'chatChanged','tools':'toolsChanged'}
SNAPSHOT_SECTION_KEYS=('hub','plugins','capability_result','preferences','base_pack','llm','partial','tool_proposals')

class Bridge(QObject):
    changed=Signal()
    hubEntriesChanged=Signal();hubInstalledChanged=Signal();hubChanged=Signal();pluginsChanged=Signal();capabilityChanged=Signal()
    preferencesChanged=Signal();packChanged=Signal();sessionChanged=Signal()
    llmChanged=Signal();toolsChanged=Signal();chatChanged=Signal();modelsCatalogChanged=Signal();modelsStateChanged=Signal()
    prefsSettled=Signal(str);textSent=Signal(str);chatSent=Signal(str)
    def __init__(self,root):
        super().__init__();self.root=Path(root);self.snapshot={};self.buffer=bytearray();self.pending=None;self.pending_op=None;self.cancel_id=None;self.text_request=None;self.text_inflight=None;self.preferences_request=None;self.results={'prefs':'','hub':'','plugin':'','text':'','llm':'','chat':'','tools':''};self.hub_target='';self.capability_pending=False;self.online=False;self.error='Core offline';self._backoff=500;self._sequence=-1;self._counter=0;self._prefix=uuid.uuid4().hex[:16]
        # C1 chat/tool state. Messages live here (window-level state, not Core snapshot). No key is ever stored here.
        self.chat_messages=[];self.chat_request=None;self.chat_inflight=None;self.chat_state='idle';self.chat_cancel_pending=False;self.pending_chat=False;self.pending_chat_cancel=False;self.tool_inflight=None
        # C2 model manager. models_req=(kind,op) awaits the Core ack; models_wait=kind awaits the capability result; models_flow is the useModel state machine.
        self.models_req=None;self.models_wait=None;self.models_before=None;self.models_flow=None;self.models_recover=False;self.models_want_list=False;self.models_data=None;self.models_message=''
        # Paging (list is paginated per tab): models_page_req=(tab,offset) awaits the page answer; models_page[tab]={'total','next'} is where the next page starts.
        self.models_page_req=None;self.models_page=fresh_model_pages()
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
        self.retry.stop();self.error='';self._backoff=500;self.refresh()
    def _offline(self,*args):
        old=self.snapshot
        self.online=False;self.error='Core offline — reconnecting';self.snapshot={};self.pending=None;self.pending_op=None;self.cancel_id=None;self.text_request=None;self.text_inflight=None;self.preferences_request=None;self.results=dict.fromkeys(self.results,'');self.hub_target='';self.capability_pending=False;self.buffer.clear();self._sequence=-1;self.poll.stop();self.timeout.stop()
        if self.socket.state()!=QLocalSocket.LocalSocketState.UnconnectedState:self.socket.abort()
        # After abort(): it re-enters _offline synchronously, which clears results; the chat message must survive that.
        self._chat_reset();self._models_reset()
        self._publish(old,self.snapshot)
        self.changed.emit()
        if not self.retry.isActive():self.retry.start(self._backoff);self._backoff=min(5000,self._backoff*2)
    def _request(self,op,**kw):
        if self.pending or self.socket.state()!=QLocalSocket.LocalSocketState.ConnectedState or (not self.online and op!='snapshot'):return False
        self._counter+=1;rid=f'{self._prefix}_{self._counter}';self.pending=rid;self.pending_op=op
        if op=='hub_approve':self.hub_target=kw['plugin_id']
        if op=='text':self.text_inflight=kw['raw']
        self.socket.write((json.dumps({'version':1,'request_id':rid,'op':op,**kw})+'\n').encode());self.timeout.start();return True
    @Slot()
    def refresh(self):self._request('snapshot')
    def _sections(self,s):
        hub=s.get('hub') or {}
        return {'entries':hub.get('entries'),'installed':hub.get('installed'),'hub':{k:v for k,v in hub.items() if k not in('entries','installed')},
                'plugins':s.get('plugins'),'capability':s.get('capability_result'),'preferences':s.get('preferences'),'pack':s.get('base_pack'),
                'llm':s.get('llm'),'partial':s.get('partial'),'tools':s.get('tool_proposals'),
                'session':{k:v for k,v in s.items() if k not in SNAPSHOT_SECTION_KEYS}}
    def _publish(self,old,new):
        before,after=self._sections(old),self._sections(new)
        for name,signal in SECTION_SIGNALS.items():
            if before[name]!=after[name]:getattr(self,signal).emit()
    def _settle(self,op,data):
        """Map the Core answer of a finished request to one UI message through the OPS table."""
        code=data.get('code','invalid_message')
        if self.models_req is not None and self.models_req[1]==op:
            kind=self.models_req[0];self.models_req=None;self._models_ack(kind,code);return
        if op=='capability_invoke' and self.pending_chat:
            self.pending_chat=False;self._chat_accepted(code);return
        if op=='capability_cancel' and self.pending_chat_cancel:
            self.pending_chat_cancel=False;self.results['chat']='Cancelamento enviado' if code=='ok' else code_message(code);self.chatChanged.emit()
        if op=='tool_decide':self.tool_inflight=None
        if op not in OPS:return
        channel,done=OPS[op]
        if op=='text':
            sent,self.text_inflight=self.text_inflight,None
            self.results['text']=done if code=='ok' else code_message(code)
            if code=='ok':self.textSent.emit(sent or '')
            return
        if code!='ok':
            self.results[channel]=code_message(code)
            if op=='capability_invoke':self.capability_pending=False
        elif op=='capability_invoke':self.capability_pending=True;self.results[channel]=PENDING[op]
        else:self.results[channel]=done(self.hub_target) if callable(done) else done
        if channel=='prefs':self.prefsSettled.emit(self.results['prefs'])
    def _apply(self,data,settled=False):
        """Publish one validated snapshot; per-section signals fire only for sections that changed."""
        # Python retains u64 precisely; QML never receives numeric session IDs.
        data['session_id']=str(data['session_id']) if data.get('session_id') is not None else ''
        old=self.snapshot
        if data!=old:self.snapshot=data;self._publish(old,data)
        if data!=old or settled:self.changed.emit()
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
            sid=data['session_id'];self._sequence=data['sequence']
            pending_op=self.pending_op
            self.timeout.stop();self.pending=None;self.pending_op=None;self.online=True;self.poll.start()
            data.pop('request_id',None)
            self._settle(pending_op,data)
            # The invocation result arrives later in the snapshot; the Core clears it on every new invoke.
            if self.capability_pending and data.get('capability_result'):self.capability_pending=False;self.results['plugin']=''
            self._apply(data,settled=pending_op in OPS)
            self._chat_observe();self._models_observe()
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
    @Slot()
    def cancel(self):
        if self.online and self.sessionId:
            self.text_request=None
            if self.pending:self.cancel_id=self.sessionId
            else:self._request('cancel',session_id=int(self.sessionId))
    def _text_ready(self):return self.online and bool(self.snapshot.get('text_input_available')) and not self.sessionId
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
    @Property(bool,notify=changed)
    def chatAvailable(self):return self.pluginsAvailable and self._chat_target() is not None
    @Slot(str,result=str)
    def chatTextProblem(self,text):return chat_problem(text) or ''
    @Slot(str,result=str)
    def codeMessage(self,code):return code_message(code) if isinstance(code,str) and SNAKE_CODE.fullmatch(code) else ''
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
        self.chat_request={'text':text,'target':target};self.pending_chat=True
        input_={'messages':messages,'tools':True,'max_tokens':CHAT_MAX_TOKENS}
        if self._request('capability_invoke',capability=target['capability'],input=input_,deadline_ms=CHAT_DEADLINE_MS):self.results['chat']=PENDING['capability_invoke']
        else:self.chat_request=None;self.pending_chat=False;self.results['chat']='Core indisponível'
        self.chatChanged.emit()
    def _chat_accepted(self,code):
        request,self.chat_request=self.chat_request,None
        if code!='ok':self.results['chat']=code_message(code);self.chatChanged.emit();return
        self.chat_messages.append({'role':'user','text':request['text'],'state':'done'});del self.chat_messages[:-CHAT_MESSAGES_KEPT]
        self.chat_inflight=request['target'];self.chat_state='waiting';self.results['chat']=''
        self.chatSent.emit(request['text']);self.chatChanged.emit()
    def _chat_observe(self):
        """Finishes the in-flight turn exactly once, when the Core publishes the matching capability_result."""
        if self.chat_inflight is None:return
        result=self.snapshot.get('capability_result')
        if not result or result['capability']!=self.chat_inflight['capability'] or result['plugin_id']!=self.chat_inflight['plugin_id']:return
        self.chat_inflight=None;self.chat_cancel_pending=False;partial=result.get('partial') or ''
        if result['ok']:
            text=result['output'].get('text');self.chat_messages.append({'role':'assistant','text':text if isinstance(text,str) else '','state':'done'})
            self.chat_state='done';self.results['chat']=''
        else:
            state='cancelled' if result['error']=='cancelled' else 'error';self.chat_state=state
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
        self.models_req=None;self.models_wait=None;self.models_before=None;self.models_flow=None;self.models_want_list=False
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
            if code=='ok':self.models_wait='selftest';self.models_before=self.snapshot.get('capability_result');self.models_message='Testando o modelo no Core…'
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
        elif kind=='fallback':self.models_message='Fallback salvo pelo Core' if code=='ok' else code_message(code)
        elif kind=='clear':self.models_message='Dados do plugin apagados' if code=='ok' else code_message(code)
        elif kind in ('list','save_custom','delete_custom'):
            if code=='ok':self.models_wait=kind;self.models_before=self.snapshot.get('capability_result')
            else:self.models_message=code_message(code);self.models_page_req=None
        self._models_touch()
    def _models_observe(self):
        """Finishes the one awaited capability answer. The Core clears capability_result on each invoke; a result equal to the one before the invoke is stale."""
        kind=self.models_wait
        if kind is None:return
        result=self.snapshot.get('capability_result')
        if not result or result.get('capability')!=MODEL_CAPABILITY or result.get('plugin_id')!=self._models_target() or result==self.models_before:return
        self.models_wait=None;self.models_before=None;ok=result['ok'];output=result.get('output')
        if kind=='list':
            req,self.models_page_req=self.models_page_req,None
            if not ok:self.models_message=self._result_text(result)
            elif req is None or not valid_models_page(output,req[0],req[1]):self.models_message='Resposta do plugin recusada pelo esquema; catálogo não alterado'
            elif not self._merge_page(req[0],req[1],output):self.models_message='Página fora de ordem; catálogo não alterado, atualize a lista'
            else:self.models_message='Catálogo atualizado';self._models_touch(catalog=True);return
        elif kind in ('save_custom','delete_custom'):
            if ok:self.models_want_list='custom';self.models_message='Modelo personalizado salvo' if kind=='save_custom' else 'Modelo personalizado removido'
            else:self.models_message=self._result_text(result)
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
    def wakeChoices(self):return self.snapshot.get('base_pack',{}).get('wake_phrases',[]) if self.snapshot.get('base_pack') else []
    @Property(str,notify=changed)
    def packDescription(self):
        pack=self.snapshot.get('base_pack')
        if not pack:return ''
        active=next((p['text'] for p in pack['wake_phrases'] if p['id']==pack['active_phrase']),'inativo')
        configured=self.snapshot.get('preferences',{}).get('wake_phrase') or pack['default_phrase']
        saved=next((p['text'] for p in pack['wake_phrases'] if p['id']==configured),'incompatível')
        return f"{pack['id']} · DEV virtual\nPerfil no processo: {active}\nConfiguração salva: {saved}\nVoz: {pack['voice']} · EN · candidata"
    @Slot(str)
    def selectWake(self,ident):
        if self.preferencesAvailable:self._preferences('select_wake',revision=int(self.preferencesRevision),phrase_id=ident)
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
    @Property(str,notify=changed)
    def configurationStatus(self):return self.snapshot.get('configuration_status','ready' if self.online else 'offline')
    @Property(bool,notify=changed)
    def recoveryAvailable(self):return self.online and self.configurationStatus=='safe_mode' and bool(self.snapshot.get('configuration_recovery_available')) and self.preferences_request is None
    @Property(str,notify=changed)
    def configurationMessage(self):
        if self.configurationStatus=='safe_mode':return ('Modo seguro: configuração inválida preservada; áudio e comandos bloqueados' if self.snapshot.get('configuration_recovery_available') else 'Modo seguro: arquivo excede o limite de recuperação automática; conteúdo preservado')
        if self.configurationStatus=='restart_required':return 'Configuração salva; reinicie o Core para ativar os recursos'
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
    def preferencesAvailable(self):return self.online and self.configurationStatus=='ready' and 'preferences' in self.snapshot and not self.sessionId and self.preferences_request is None
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
        if not result['ok']:return result['error']
        output=result['output'];text=output.get('text')
        return (text if isinstance(text,str) else json.dumps(output,ensure_ascii=False,sort_keys=True))[:512]
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
        if self.pluginsAvailable:self._preferences('capability_invoke',capability=capability,input={'text':text[:256]},deadline_ms=3000)
    @Slot(str)
    def cancelCapability(self,capability):
        if self.pluginsAvailable:self._preferences('capability_cancel',capability=capability)
    @Property(bool,notify=changed)
    def hubImportActive(self):return self.online and bool((self.snapshot.get('hub') or {}).get('import'))
    @Property(str,notify=changed)
    def hubImportDescription(self):
        transfer=(self.snapshot.get('hub') or {}).get('import')
        return f"Preparando {transfer['plugin_id']}: {transfer['received']}/{transfer['expected']} bytes" if transfer else ''
    @Slot()
    def abortHubImport(self):
        if self.hubImportActive:self._preferences('hub_abort',import_id=self.snapshot['hub']['import']['import_id'])
    @Property('QVariantList',notify=hubEntriesChanged)
    def hubEntries(self):return (self.snapshot.get('hub') or {}).get('entries',[])
    @Property(str,notify=changed)
    def hubDescription(self):
        hub=self.snapshot.get('hub')
        if not self.online:return 'Core offline'
        if not hub:return 'Catálogo não configurado'
        if hub['status']=='quarantined':return 'Catálogo em quarentena; Base continua disponível'
        return 'Catálogo local com checksum verificado; publisher não autenticado. Plugins instalados ficam desativados até ativação explícita; ativos rodam em sandbox sem rede.'
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
        return r['result'] if r else c.get('code','')
    @Property(bool,notify=sessionChanged)
    def resultVerified(self):return bool((self.snapshot.get('command') or {}).get('receipt',{})) and bool(self.snapshot['command']['receipt']['verified'])
    @Property(str,notify=changed)
    def diagnostic(self):
        if not self.online:return self.error
        return self.configurationMessage or ' · '.join([self.snapshot.get('wake_status','unavailable'),self.snapshot.get('stt_status','unavailable'),self.snapshot.get('speech_status','unavailable')])
