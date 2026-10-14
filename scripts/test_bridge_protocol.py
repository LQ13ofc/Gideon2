#!/usr/bin/env python3
"""Malformed IPC over actual Qt local sockets; no GUI/session/devices are opened."""
import copy,json,os,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from bridge import Bridge,validate_snapshot
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalServer
APP=QCoreApplication([])
BASE={'version':1,'request_id':'r','code':'ok','state':'idle','sequence':1,'session_id':None,'transcript':None,'command':None,'events':[],'text_input_available':True,'speech_samples':0,'speech_status':'idle','wake_status':'unavailable','stt_status':'unavailable'}
def pump(condition):
    until=time.monotonic()+2
    while not condition():
        APP.processEvents();time.sleep(.002)
        if time.monotonic()>until:raise TimeoutError('Qt IPC')
class Tests(unittest.TestCase):
    def test_malformed_nested_envelopes_are_rejected(self):
        for key,value in [('transcript',[]),('transcript',{'raw':5,'is_final':True}),('command',[]),('command',{'session_id':1,'code':'command_success','receipt':{'verified':True}}),('events',[{'sequence':99}]),('speech_samples',-1),('text_input_available','yes'),('session_id',True),('version',True),('sequence',-1)]:
            cfg=copy.deepcopy(BASE);cfg[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):validate_snapshot(cfg,'r',0)
        self.assertIs(validate_snapshot(copy.deepcopy(BASE),'r',1)['session_id'],None)
        with self.assertRaises(ValueError):validate_snapshot(copy.deepcopy(BASE),'other',1)
        with self.assertRaises(ValueError):validate_snapshot(copy.deepcopy(BASE),'r',2)
    def test_preferences_presentation_rejects_bad_values(self):
        valid={'version':1,'revision':2**64-1,'audible_feedback':False,'session_timeout_ms':60000,'wake_phrase':None}
        cfg=copy.deepcopy(BASE);cfg['preferences']=valid
        validate_snapshot(cfg,'r',0)
        for key,value in [('version',True),('revision',True),('revision',-1),('revision',2**64),('audible_feedback','yes'),('session_timeout_ms',0),('session_timeout_ms',60001),('wake_phrase','../private'),('previous_preferences',[]),('previous_preferences',{'audible_feedback':True,'session_timeout_ms':0})]:
            cfg=copy.deepcopy(BASE);cfg['preferences']={**valid,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):validate_snapshot(cfg,'r',0)
    def test_real_socket_malformed_nested_data_and_deep_json_clear_stale_state(self):
        for deep in (False,True,"preferences"):
            with self.subTest(deep=deep),tempfile.TemporaryDirectory(prefix='gideon-ipc-audit-') as td:
                root=Path(td);root.chmod(0o700);server=QLocalServer();self.assertTrue(server.listen(str(root/'core.sock')));(root/'core.sock').chmod(0o600)
                bridge=Bridge(root);pump(lambda:server.hasPendingConnections());peer=server.nextPendingConnection();pump(lambda:peer.canReadLine())
                request=json.loads(bytes(peer.readLine()));good=copy.deepcopy(BASE);good['request_id']=request['request_id'];peer.write((json.dumps(good)+'\n').encode());peer.flush();pump(lambda:bridge.connected)
                bridge.refresh();pump(lambda:peer.canReadLine());request=json.loads(bytes(peer.readLine()))
                if deep is True:bad='['*1100+'0'+']'*1100+'\n'
                else:
                    good['request_id']=request['request_id']
                    if deep=='preferences':good['preferences']={'version':1,'revision':True,'audible_feedback':False,'session_timeout_ms':30000}
                    else:good['command']=[]
                    bad=json.dumps(good)+'\n'
                peer.write(bad.encode());peer.flush();pump(lambda:not bridge.connected)
                self.assertEqual(bridge.snapshot,{});self.assertFalse(bridge.textAvailable);self.assertEqual(bridge.result,'')
                bridge.poll.stop();bridge.timeout.stop();bridge.socket.abort();bridge.retry.stop();peer.close();server.close()
if __name__=='__main__':unittest.main()
