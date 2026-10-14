"""Thin, bounded Qt IPC adapter. Core owns all parsing, sessions and authority."""
import json,os,stat,uuid
from pathlib import Path
from PySide6.QtCore import QObject,Property,Signal,Slot,QTimer
from PySide6.QtNetwork import QLocalSocket


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
        previous=prefs.get('previous_preferences')
        if previous is not None:require(isinstance(previous,dict) and type(previous.get('audible_feedback')) is bool and integer(previous.get('session_timeout_ms'),50,60000))
        wake=prefs.get('wake_phrase')
        require(wake is None or (short(wake) and len(wake)>0 and all(c.isascii() and (c.isalnum() or c in '_-') for c in wake)))
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

class Bridge(QObject):
    changed=Signal()
    def __init__(self,root):
        super().__init__();self.root=Path(root);self.snapshot={};self.buffer=bytearray();self.pending=None;self.pending_op=None;self.cancel_id=None;self.text_request=None;self.preferences_request=None;self.preferences_result='';self.online=False;self.error='Core offline';self._backoff=500;self._sequence=-1;self._counter=0;self._prefix=uuid.uuid4().hex[:16]
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
        self.online=False;self.error='Core offline — reconnecting';self.snapshot={};self.pending=None;self.pending_op=None;self.cancel_id=None;self.text_request=None;self.preferences_request=None;self.preferences_result='';self.buffer.clear();self._sequence=-1;self.poll.stop();self.timeout.stop()
        if self.socket.state()!=QLocalSocket.LocalSocketState.UnconnectedState:self.socket.abort()
        self.changed.emit()
        if not self.retry.isActive():self.retry.start(self._backoff);self._backoff=min(5000,self._backoff*2)
    def _request(self,op,**kw):
        if self.pending or self.socket.state()!=QLocalSocket.LocalSocketState.ConnectedState or (not self.online and op!='snapshot'):return
        self._counter+=1;rid=f'{self._prefix}_{self._counter}';self.pending=rid;self.pending_op=op
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
            elif pending_op in ('preferences','rollback_preferences'):
                self.preferences_result=('Preferências salvas pelo Core' if data.get('code')=='ok' else data.get('code','invalid_message'))
            data.pop('request_id',None)
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
        if self.configurationStatus=='restart_required':return 'Configuração recuperada; reinicie o Core para ativar os recursos'
        return ''
    @Slot(bool,int)
    def savePreferences(self,audible,timeout):
        if self.preferencesAvailable:
            self._preferences('preferences',revision=int(self.preferencesRevision),audible_feedback=audible,session_timeout_ms=timeout)
    @Slot()
    def rollbackPreferences(self):
        if self.preferencesAvailable:self._preferences('rollback_preferences',revision=int(self.preferencesRevision))
    def _preferences(self,op,**kw):
        self.preferences_result='Enviando ao Core'
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
