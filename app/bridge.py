"""Thin, bounded Qt IPC adapter. Core owns all parsing, sessions and authority."""
import json,os,stat,uuid
from pathlib import Path
from PySide6.QtCore import QObject,Property,Signal,Slot,QTimer
from PySide6.QtNetwork import QLocalSocket

class Bridge(QObject):
    changed=Signal()
    def __init__(self,root):
        super().__init__();self.root=Path(root);self.snapshot={};self.buffer=bytearray();self.pending=None;self.cancel_id=None;self.text_request=None;self.online=False;self.error='Core offline';self._backoff=500;self._sequence=-1;self._counter=0;self._prefix=uuid.uuid4().hex[:16]
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
        self.online=False;self.error='Core offline — reconnecting';self.snapshot={};self.pending=None;self.cancel_id=None;self.text_request=None;self.buffer.clear();self._sequence=-1;self.poll.stop();self.timeout.stop()
        if self.socket.state()!=QLocalSocket.LocalSocketState.UnconnectedState:self.socket.abort()
        self.changed.emit()
        if not self.retry.isActive():self.retry.start(self._backoff);self._backoff=min(5000,self._backoff*2)
    def _request(self,op,**kw):
        if self.pending or self.socket.state()!=QLocalSocket.LocalSocketState.ConnectedState or (not self.online and op!='snapshot'):return
        self._counter+=1;rid=f'{self._prefix}_{self._counter}';self.pending=rid
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
                if data['version']!=1 or data['request_id']!=self.pending or data['state'] not in ('idle','capturing','transcribing','executing','speaking'):raise ValueError('IPC correlation')
                sequence=data['sequence']
                if type(sequence) is not int or sequence<self._sequence:raise ValueError('stale state')
                self._sequence=sequence
                sid=data['session_id']
                if sid is not None and (type(sid) is not int or not 0<sid<2**64):raise ValueError('session identity')
            except (ValueError,KeyError,TypeError):self._offline();return
            self.timeout.stop();self.pending=None;self.online=True;self.poll.start()
            # Python retains u64 precisely; QML never receives numeric session IDs.
            data['session_id']=str(sid) if sid is not None else ''
            data.pop('request_id',None)
            if data!=self.snapshot:self.snapshot=data;self.changed.emit()
            self.poll.setInterval(150 if sid is not None else 1000)
            if self.cancel_id is not None:
                old=self.cancel_id;self.cancel_id=None;self._request('cancel',session_id=int(old))
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
    @Property(bool,notify=changed)
    def textAvailable(self):return self.online and bool(self.snapshot.get('text_input_available')) and not self.sessionId and self.text_request is None
    @Property(bool,notify=changed)
    def connected(self):return self.online
    @Property(str,notify=changed)
    def state(self):return self.snapshot.get('state','offline')
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
        return ' · '.join([self.snapshot.get('wake_status','unavailable'),self.snapshot.get('stt_status','unavailable'),self.snapshot.get('speech_status','unavailable')])
