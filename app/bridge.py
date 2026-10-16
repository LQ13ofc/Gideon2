"""Thin, bounded Qt IPC adapter. Core owns all parsing, sessions and authority."""
import json,os,re,stat,uuid
from pathlib import Path
from PySide6.QtCore import QObject,Property,Signal,Slot,QTimer
from PySide6.QtNetwork import QLocalSocket
CAPABILITY_ID=re.compile(r'[a-z0-9_]+(\.[a-z0-9_]+)+');PLUGIN_ID=re.compile(r'[A-Za-z0-9_-]+');SNAKE_CODE=re.compile(r'[a-z][a-z0-9_]*')
PLUGIN_STATES=('disabled','starting','running','failed','stopped','quarantined')
def bounded_output(value):
    """Core output contract: JSON object, at most 8 KiB, at most 4 container levels."""
    def shallow(item,depth=0):
        if isinstance(item,dict):return depth<4 and all(shallow(child,depth+1) for child in item.values())
        if isinstance(item,list):return depth<4 and all(shallow(child,depth+1) for child in item)
        return True
    try:return isinstance(value,dict) and shallow(value) and len(json.dumps(value,separators=(',',':'),allow_nan=False).encode('utf-8'))<=8192
    except (TypeError,ValueError,RecursionError):return False


def validate_snapshot(data,request_id,min_sequence):
    """Validate presentation data before QML sees it; no command policy lives here."""
    def require(condition):
        if not condition:raise ValueError('invalid IPC snapshot')
    def integer(value,minimum=0,maximum=2**64-1):
        return type(value) is int and minimum<=value<=maximum
    def sid(value):return integer(value,1)
    def short(value,limit=64):return isinstance(value,str) and len(value.encode('utf-8'))<=limit
    require(isinstance(data,dict))
    require(type(data.get('version')) is int and data['version']==1)
    require(data.get('request_id')==request_id and isinstance(request_id,str))
    require(data.get('state') in ('idle','capturing','transcribing','executing','speaking'))
    require(integer(data.get('sequence')) and data['sequence']>=min_sequence)
    require('session_id' in data and (data['session_id'] is None or sid(data['session_id'])))
    for key in ('code','wake_status','stt_status','speech_status'):
        if key in data:require(short(data[key]))
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
        require(isinstance(prefs,dict) and type(prefs.get('version')) is int and prefs['version']==1)
        require(integer(prefs.get('revision')) and integer(prefs.get('session_timeout_ms'),50,60000))
        require(type(prefs.get('audible_feedback')) is bool)
        if 'visual_feedback' in prefs:require(type(prefs['visual_feedback']) is bool)
        if 'output_volume_percent' in prefs:require(integer(prefs['output_volume_percent'],0,100))
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
        require(hub.get('status') in ('verified','quarantined') and hub.get('publisher_verified') is False)
        if 'approval_revision' in hub:require(integer(hub['approval_revision']))
        if hub.get('import') is not None:
            transfer=hub['import'];require(isinstance(transfer,dict) and short(transfer.get('import_id')) and short(transfer.get('plugin_id')) and integer(transfer.get('expected'),1,67108864) and integer(transfer.get('received'),0,transfer['expected']))
        entries=hub.get('entries');require(isinstance(entries,list) and len(entries)<=8)
        installed=hub.get('installed');require(integer(hub.get('install_revision')) and isinstance(installed,list) and len(installed)<=8 and (hub['status']=='verified' or not installed))
        records={};digest=lambda v:isinstance(v,str) and len(v)==64 and all(c in '0123456789abcdef' for c in v)
        for record in installed:
            require(isinstance(record,dict) and set(record)=={'plugin_id','semver','manifest_sha256','state','runtime','previous'})
            require(short(record['plugin_id'],128) and bool(record['plugin_id']) and short(record['semver'],128) and bool(record['semver']) and record['state'] in ('installed','quarantined') and record['runtime']=='disabled' and digest(record['manifest_sha256']))
            previous=record['previous'];require(previous is None or (isinstance(previous,dict) and set(previous)=={'semver','manifest_sha256'} and short(previous['semver'],128) and bool(previous['semver']) and digest(previous['manifest_sha256'])))
            require(record['plugin_id'] not in records);records[record['plugin_id']]=record
        if hub['status']=='quarantined':require(hub.get('import') is None and not entries and hub.get('repository') is None and hub.get('catalog_sha256') is None)
        else:
            require(short(hub.get('repository'),256) and hub['repository'].startswith('https://github.com/'))
            digest=hub.get('catalog_sha256');require(isinstance(digest,str) and len(digest)==64 and all(c in '0123456789abcdef' for c in digest))
        if hub.get('import') is not None:
            transfer=hub['import'];matching=[e for e in entries if e.get('plugin_id')==transfer['plugin_id']]
            require(len(matching)==1 and matching[0].get('status') in ('not_installed','update_available') and matching[0].get('permissions_approved') is True and transfer['expected']==matching[0].get('download_size'))
        ids=set()
        for entry in entries:
            require(isinstance(entry,dict))
            for key in ('plugin_id','semver','publisher','license','support_policy'):require(short(entry.get(key),128) and bool(entry[key]))
            if 'manifest_sha256' in entry:require(isinstance(entry['manifest_sha256'],str) and len(entry['manifest_sha256'])==64 and all(c in '0123456789abcdef' for c in entry['manifest_sha256']))
            if 'payload_staged' in entry:require(type(entry['payload_staged']) is bool and (not entry['payload_staged'] or entry.get('status') in ('not_installed','update_available')))
            if 'permissions_approved' in entry:require(type(entry['permissions_approved']) is bool and (not entry['permissions_approved'] or (entry.get('status') in ('not_installed','update_available','installed') and 'manifest_sha256' in entry and integer(hub.get('approval_revision'),1))))
            require(entry['plugin_id'] not in ids);ids.add(entry['plugin_id'])
            require(integer(entry.get('api_version'),0,65535) and integer(entry.get('download_size'),0,67108864))
            require(entry.get('status') in ('not_installed','incompatible','installed','update_available') and entry.get('reason') in ('none','api_version','target','dependencies_unresolved'))
            require((entry['status']=='incompatible') == (entry['reason']!='none'))
            record=records.get(entry['plugin_id'])
            if entry['status']=='installed':require(record is not None and 'manifest_sha256' in entry and record['manifest_sha256']==entry['manifest_sha256'])
            elif entry['status']=='update_available':require(record is not None and 'manifest_sha256' in entry and record['manifest_sha256']!=entry['manifest_sha256'])
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
            require(item['last_error'] is None or (isinstance(item['last_error'],str) and len(item['last_error'])<=64 and SNAKE_CODE.fullmatch(item['last_error'])))
            record=installed.get(ident);entry=listed.get(ident)
            require(record is not None and record['semver']==item['semver'] and caps==(entry.get('capabilities',[]) if entry else []))
            require((item['state']=='quarantined')==(record['state']=='quarantined'))
            if item['enabled']:require(item['state'] in ('starting','running','failed','stopped') and record['state']=='installed' and entry is not None and entry['status']=='installed')
            else:require(item['state'] in ('disabled','quarantined'))
        require(names==set(installed))
    result=data.get('capability_result')
    if result is not None:
        require(isinstance(result,dict) and set(result)<={'capability','plugin_id','ok','output','error','elapsed_ms'} and {'capability','plugin_id','ok','elapsed_ms'}<=set(result))
        require(isinstance(result['capability'],str) and len(result['capability'])<=64 and CAPABILITY_ID.fullmatch(result['capability']) and isinstance(result['plugin_id'],str) and type(result['ok']) is bool and integer(result['elapsed_ms']))
        owner=next((i for i in items if i['plugin_id']==result['plugin_id']),None)
        require(owner is not None and result['capability'] in owner['capabilities'])
        if result['ok']:require('output' in result and 'error' not in result and bounded_output(result['output']))
        else:require('error' in result and 'output' not in result and isinstance(result['error'],str) and len(result['error'])<=64 and SNAKE_CODE.fullmatch(result['error']))
    pack=data.get('base_pack')
    if pack is not None:
        require(isinstance(pack,dict) and type(pack.get('version')) is int and pack['version']==1)
        require(short(pack.get('id')) and pack.get('scope')=='dev_virtual_en' and pack.get('preflight')=='verified')
        require(isinstance(pack.get('engines'),dict) and set(pack['engines'])=={'wake','stt','tts'} and all(short(v,160) for v in pack['engines'].values()))
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
        require(short(t.get('raw'),4096) and type(t.get('is_final')) is bool and sid(t.get('session_id')))
        require(integer(t.get('revision'),1,256))
    command=data.get('command')
    if command is not None:
        require(isinstance(command,dict) and sid(command.get('session_id')) and short(command.get('code')))
        receipt=command.get('receipt')
        if receipt is not None:
            require(isinstance(receipt,dict))
            require(type(receipt.get('verified')) is bool and short(receipt.get('scope')) and short(receipt.get('result'),256))
            job=receipt.get('job')
            require(isinstance(job,dict) and job.get('session_id')==command['session_id'] and isinstance(job.get('command'),dict))
    if 'events' in data:
        require(isinstance(data['events'],list) and len(data['events'])<=64)
        previous=-1
        for event in data['events']:
            require(isinstance(event,dict))
            require(integer(event.get('sequence')) and previous<event['sequence']<=data['sequence'])
            require(short(event.get('kind')) and short(event.get('request_id')))
            require('session_id' in event and (event['session_id'] is None or sid(event['session_id'])))
            previous=event['sequence']
    return data

HUB_PENDING={'hub_install':'Instalando no Core','hub_rollback':'Revertendo no Core','hub_remove':'Removendo no Core'}
HUB_DONE={'hub_install':'Plugin instalado (desativado)','hub_rollback':'Versão revertida','hub_remove':'Plugin removido'}
PLUGIN_PENDING={'plugin_enable':'Ativando plugin…','plugin_disable':'Desativando plugin…','plugin_revoke':'Revogando permissões…','capability_invoke':'Invocando capability…','capability_cancel':'Cancelando capability…'}
PLUGIN_DONE={'plugin_enable':'Plugin ativado','plugin_disable':'Plugin desativado','plugin_revoke':'Permissões revogadas; plugin desativado','capability_cancel':'Cancelamento enviado'}

class Bridge(QObject):
    changed=Signal()
    def __init__(self,root):
        super().__init__();self.root=Path(root);self.snapshot={};self.buffer=bytearray();self.pending=None;self.pending_op=None;self.cancel_id=None;self.text_request=None;self.preferences_request=None;self.preferences_result='';self.hub_result='';self.hub_target='';self.plugin_result='';self.capability_pending=False;self.online=False;self.error='Core offline';self._backoff=500;self._sequence=-1;self._counter=0;self._prefix=uuid.uuid4().hex[:16]
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
        self.online=False;self.error='Core offline — reconnecting';self.snapshot={};self.pending=None;self.pending_op=None;self.cancel_id=None;self.text_request=None;self.preferences_request=None;self.preferences_result='';self.hub_result='';self.hub_target='';self.plugin_result='';self.capability_pending=False;self.buffer.clear();self._sequence=-1;self.poll.stop();self.timeout.stop()
        if self.socket.state()!=QLocalSocket.LocalSocketState.UnconnectedState:self.socket.abort()
        self.changed.emit()
        if not self.retry.isActive():self.retry.start(self._backoff);self._backoff=min(5000,self._backoff*2)
    def _request(self,op,**kw):
        if self.pending or self.socket.state()!=QLocalSocket.LocalSocketState.ConnectedState or (not self.online and op!='snapshot'):return
        self._counter+=1;rid=f'{self._prefix}_{self._counter}';self.pending=rid;self.pending_op=op
        if op=='hub_approve':self.hub_target=kw['plugin_id']
        self.socket.write((json.dumps({'version':1,'request_id':rid,'op':op,**kw})+'\n').encode());self.timeout.start()
    @Slot()
    def refresh(self):self._request('snapshot')
    def _read(self):
        self.buffer.extend(bytes(self.socket.readAll()))
        if len(self.buffer)>65536:self._offline();return
        while b'\n' in self.buffer:
            line,_,tail=self.buffer.partition(b'\n');self.buffer=bytearray(tail)
            try:
                data=json.loads(line)
                validate_snapshot(data,self.pending,self._sequence)
                sid=data['session_id']
                self._sequence=data['sequence']
            except (ValueError,KeyError,TypeError,RecursionError,UnicodeError):self._offline();return
            pending_op=self.pending_op
            self.timeout.stop();self.pending=None;self.pending_op=None;self.online=True;self.poll.start()
            # Python retains u64 precisely; QML never receives numeric session IDs.
            data['session_id']=str(sid) if sid is not None else ''
            if pending_op=='recover_configuration':
                self.preferences_result=('Configuração recuperada; reinício necessário' if data.get('code')=='ok' else data.get('code','invalid_message'))
            elif pending_op=='hub_abort':
                self.hub_result=('Importação cancelada' if data.get('code')=='ok' else data.get('code','invalid_message'))
            elif pending_op=='hub_approve':
                self.hub_result=(f'Permissões aprovadas: {self.hub_target}' if data.get('code')=='ok' else data.get('code','invalid_message'))
            elif pending_op in HUB_PENDING:
                self.hub_result=(HUB_DONE[pending_op] if data.get('code')=='ok' else data.get('code','invalid_message'))
            elif pending_op in ('preferences','rollback_preferences','select_wake','feedback_preferences'):
                self.preferences_result=('Preferências salvas pelo Core' if data.get('code')=='ok' else data.get('code','invalid_message'))
            elif pending_op in PLUGIN_PENDING:
                if data.get('code')!='ok':self.plugin_result=data.get('code','invalid_message');self.capability_pending=False
                elif pending_op=='capability_invoke':self.capability_pending=True;self.plugin_result=PLUGIN_PENDING[pending_op]
                else:self.plugin_result=PLUGIN_DONE[pending_op]
            data.pop('request_id',None)
            # The invocation result arrives later in the snapshot; the Core clears it on every new invoke.
            if self.capability_pending and data.get('capability_result'):self.capability_pending=False;self.plugin_result=''
            if data!=self.snapshot:self.snapshot=data;self.changed.emit()
            self.poll.setInterval(150 if sid is not None else 1000)
            if self.cancel_id is not None:
                old=self.cancel_id;self.cancel_id=None;self._request('cancel',session_id=int(old))
            elif self.preferences_request is not None:
                op,kw=self.preferences_request;self.preferences_request=None;self._request(op,**kw)
            elif self.text_request is not None:
                text=self.text_request;self.text_request=None;self._request('text',raw=text)
    @Slot()
    def cancel(self):
        if self.online and self.sessionId:
            self.text_request=None;
            if self.pending:self.cancel_id=self.sessionId
            else:self._request('cancel',session_id=int(self.sessionId))
    @Slot(str)
    def submitText(self,text):
        if self.textAvailable:
            if self.pending:self.text_request=text;self.changed.emit()
            else:self._request('text',raw=text)
    @Property('QVariantList',notify=changed)
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
    @Property(bool,notify=changed)
    def visualFeedback(self):return self.snapshot.get('preferences',{}).get('visual_feedback',True)
    @Property(int,notify=changed)
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
        if op=='hub_approve':self.hub_result='Enviando aprovação ao Core'
        elif op=='hub_abort':self.hub_result='Enviando cancelamento ao Core'
        elif op in HUB_PENDING:self.hub_result=HUB_PENDING[op]
        elif op in PLUGIN_PENDING:self.plugin_result=PLUGIN_PENDING[op]
        else:self.preferences_result='Enviando ao Core'
        if self.pending:self.preferences_request=(op,kw)
        else:self._request(op,**kw)
        self.changed.emit()
    @Property(bool,notify=changed)
    def preferencesAvailable(self):return self.online and self.configurationStatus=='ready' and 'preferences' in self.snapshot and not self.sessionId and self.preferences_request is None
    @Property(bool,notify=changed)
    def rollbackAvailable(self):return self.preferencesAvailable and bool(self.snapshot.get("preferences",{}).get("previous_preferences"))
    @Property(bool,notify=changed)
    def voiceAvailable(self):return self.online and self.snapshot.get("speech_status","unavailable")!="unavailable"
    @Property(bool,notify=changed)
    def audibleFeedback(self):return self.snapshot.get('preferences',{}).get('audible_feedback',True)
    @Property(int,notify=changed)
    def sessionTimeout(self):return self.snapshot.get('preferences',{}).get('session_timeout_ms',30000)
    @Property(str,notify=changed)
    def preferencesRevision(self):return str(self.snapshot.get('preferences',{}).get('revision',0))
    @Property(str,notify=changed)
    def preferencesResult(self):return self.preferences_result
    @Property(bool,notify=changed)
    def textAvailable(self):return self.online and bool(self.snapshot.get('text_input_available')) and not self.sessionId and self.text_request is None
    @Property('QVariantMap',notify=changed)
    def snapshotPack(self):return self.snapshot.get('base_pack') or {}
    @Property(str,notify=changed)
    def wakeStatus(self):return self.snapshot.get('wake_status','unavailable')
    @Property(str,notify=changed)
    def sttStatus(self):return self.snapshot.get('stt_status','unavailable')
    @Property(str,notify=changed)
    def speechStatus(self):return self.snapshot.get('speech_status','unavailable')
    @Property(str,notify=changed)
    def hubApprovalResult(self):return self.hub_result
    @Slot()
    def beginHubReview(self):
        self.hub_result='';self.changed.emit()
    @Property(str,notify=changed)
    def hubApprovalRevision(self):return str((self.snapshot.get('hub') or {}).get('approval_revision',0))
    @Property(bool,notify=changed)
    def hubApprovalAvailable(self):return self.preferencesAvailable and (self.snapshot.get('hub') or {}).get('status')=='verified' and 'approval_revision' in self.snapshot['hub'] and self.snapshot['hub'].get('import') is None
    @Slot(str,str,'QVariantList',bool)
    def approveHub(self,plugin,manifest,permissions,acknowledged):
        if self.hubApprovalAvailable:self._preferences('hub_approve',revision=int(self.hubApprovalRevision),plugin_id=plugin,manifest_sha256=manifest,permissions=list(permissions),publisher_unverified_ack=acknowledged)
    @Property(bool,notify=changed)
    def hubLifecycleAvailable(self):return self.preferencesAvailable and (self.snapshot.get('hub') or {}).get('status')=='verified' and self.snapshot['hub'].get('import') is None
    @Property(str,notify=changed)
    def hubInstallRevision(self):return str((self.snapshot.get('hub') or {}).get('install_revision',0))
    @Property('QVariantList',notify=changed)
    def hubInstalled(self):return (self.snapshot.get('hub') or {}).get('installed',[])
    @Slot(str,str)
    def installHub(self,plugin,manifest):
        if self.hubLifecycleAvailable:self._preferences('hub_install',revision=int(self.hubInstallRevision),plugin_id=plugin,manifest_sha256=manifest)
    @Slot(str)
    def rollbackHub(self,plugin):
        if self.hubLifecycleAvailable:self._preferences('hub_rollback',revision=int(self.hubInstallRevision),plugin_id=plugin)
    @Slot(str)
    def removeHub(self,plugin):
        if self.hubLifecycleAvailable:self._preferences('hub_remove',revision=int(self.hubInstallRevision),plugin_id=plugin)
    @Property(bool,notify=changed)
    def pluginsAvailable(self):return self.hubLifecycleAvailable and 'plugins' in self.snapshot
    @Property('QVariantList',notify=changed)
    def pluginItems(self):return list((self.snapshot.get('plugins') or {}).get('items',[]))
    @Property(str,notify=changed)
    def pluginsRevision(self):return str((self.snapshot.get('plugins') or {}).get('revision',0))
    @Property(str,notify=changed)
    def pluginResult(self):return self.plugin_result
    @Property(str,notify=changed)
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
    @Slot(str)
    def revokePlugin(self,plugin):
        if self.pluginsAvailable:self._preferences('plugin_revoke',revision=int(self.pluginsRevision),plugin_id=plugin)
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
    @Property('QVariantList',notify=changed)
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
    @Property(str,notify=changed)
    def sessionId(self):return self.snapshot.get('session_id','')
    @Property(str,notify=changed)
    def subtitle(self):return (self.snapshot.get('transcript') or {}).get('raw','')
    @Property(bool,notify=changed)
    def partial(self):return bool(self.snapshot.get('transcript')) and not self.snapshot['transcript']['is_final']
    @Property(str,notify=changed)
    def result(self):
        c=self.snapshot.get('command') or {};r=c.get('receipt')
        return r['result'] if r else c.get('code','')
    @Property(bool,notify=changed)
    def resultVerified(self):return bool((self.snapshot.get('command') or {}).get('receipt',{})) and bool(self.snapshot['command']['receipt']['verified'])
    @Property(str,notify=changed)
    def diagnostic(self):
        if not self.online:return self.error
        return self.configurationMessage or ' · '.join([self.snapshot.get('wake_status','unavailable'),self.snapshot.get('stt_status','unavailable'),self.snapshot.get('speech_status','unavailable')])
