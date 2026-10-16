#!/usr/bin/env python3
"""Malformed IPC over actual Qt local sockets; no GUI/session/devices are opened."""
import copy,json,os,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from bridge import Bridge,validate_snapshot
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalServer
APP=QCoreApplication([])
BASE={'version':1,'request_id':'r','code':'ok','state':'idle','sequence':1,'session_id':None,'transcript':None,'command':None,'events':[],'text_input_available':True,'speech_samples':0,'speech_status':'idle','wake_status':'unavailable','stt_status':'unavailable','plugins':{'revision':0,'status':'ok','items':[]}}
def plugins_for(hub):
    return {'revision':0,'status':'ok','items':[{'plugin_id':r['plugin_id'],'semver':r['semver'],'capabilities':[],'state':'quarantined' if r['state']=='quarantined' else 'disabled','enabled':False,'restarts':0,'last_error':None} for r in hub.get('installed',[])]}
def snap(hub):return {**BASE,'hub':hub,'plugins':plugins_for(hub)}
def pump(condition):
    until=time.monotonic()+2
    while not condition():
        APP.processEvents();time.sleep(.002)
        if time.monotonic()>until:raise TimeoutError('Qt IPC')
def plugin_snapshot(state='running',enabled=True):
    digest='a'*64
    record={'plugin_id':'dummy_echo','semver':'0.1.0','manifest_sha256':digest,'state':'installed','runtime':'disabled','previous':None}
    entry={'plugin_id':'dummy_echo','semver':'0.1.0','publisher':'fixture','api_version':1,'targets':['linux_x86_64'],'license':'MIT','permissions':[],'dependencies':[],'conflicts':[],'download_size':15,'support_policy':'fixture','status':'installed','reason':'none','manifest_sha256':digest,'permissions_approved':False,'payload_staged':False,'runtime':'python3_script','capabilities':['dummy_echo.echo']}
    hub={'version':1,'status':'verified','repository':'https://github.com/a/b','catalog_sha256':'b'*64,'publisher_verified':False,'approval_revision':1,'install_revision':1,'entries':[entry],'installed':[record]}
    item={'plugin_id':'dummy_echo','semver':'0.1.0','capabilities':['dummy_echo.echo'],'state':state,'enabled':enabled,'restarts':0,'last_error':None}
    cap={'capability':'dummy_echo.echo','plugin_id':'dummy_echo','ok':True,'output':{'text':'HELLO','count':1},'elapsed_ms':3}
    return {**BASE,'hub':hub,'plugins':{'revision':1,'status':'ok','items':[item]},'capability_result':cap}
def _item(s):return s['plugins']['items'][0]
def _result(s):return s['capability_result']
def _failed(s):_result(s).pop('output');_result(s).update(ok=False,error='Plugin Crashed')
def _no_output(s):_result(s).pop('output')
def _quarantine_hub(s):s['hub'].update(status='quarantined',repository=None,catalog_sha256=None,entries=[],installed=[])
def _drop_hub(s):del s['hub']
def _drop_plugins(s):del s['plugins']
def _stale_entry(s):s['hub']['entries'][0].update(status='update_available',manifest_sha256='c'*64)
def _record_quarantined(s):s['hub']['installed'][0]['state']='quarantined'
def _quarantined_enabled(s):s['hub']['installed'][0]['state']='quarantined';_item(s).update(state='quarantined',enabled=True)
def _extra_item_key(s):_item(s)['status']='ok'
def _extra_plugins_key(s):s['plugins']['debug']=1
def _duplicate(s):s['plugins']['items'].append(dict(_item(s)))
def _too_many(s):s['plugins']['items'].extend(dict(_item(s),plugin_id=f'p{i}') for i in range(8))
def _bad_capability(s):_item(s)['capabilities']=['Dummy.Echo'];s['hub']['entries'][0]['capabilities']=['Dummy.Echo']
def _oversize(s):_result(s)['output']={'text':'x'*9000}
def _deep(s):_result(s)['output']={'a':{'b':{'c':{'d':{'e':1}}}}}
def _scalar_output(s):_result(s)['output']='HELLO'
def _unknown_result_plugin(s):_result(s)['plugin_id']='ghost'
def _foreign_capability(s):_result(s)['capability']='other.echo'
def _negative_restarts(s):_item(s)['restarts']=-1
def _string_revision(s):s['plugins']['revision']='1'
def _mismatch_state(s):s['hub']['installed'][0]['state']='quarantined'
def _not_snake_error(s):_item(s).update(state='failed',last_error='Plugin Crashed')
def _semver_drift(s):_item(s)['semver']='9.9.9'
def _negative_elapsed(s):_result(s)['elapsed_ms']=-1
CASES=[('unknown state',lambda s:_item(s).update(state='paused')),('running but not enabled',lambda s:_item(s).update(enabled=False)),('quarantined and enabled',_quarantined_enabled),('duplicate plugin ids',_duplicate),('more than eight items',_too_many),('extra item key',_extra_item_key),('extra plugins key',_extra_plugins_key),('bad capability id',_bad_capability),('oversize output',_oversize),('deep output',_deep),('non-object output',_scalar_output),('error not snake_case',_failed),('capability_result for unknown plugin',_unknown_result_plugin),('capability not owned by plugin',_foreign_capability),('negative restarts',_negative_restarts),('revision not int',_string_revision),('plugins under quarantined hub with items',_quarantine_hub),('plugins missing while hub present',_drop_plugins),('plugin items without hub',_drop_hub),('enabled while approval entry stale',_stale_entry),('item state disagrees with ledger',_mismatch_state),('record quarantined but item enabled',_record_quarantined),('last_error not snake_case',_not_snake_error),('semver differs from installed record',_semver_drift),('negative elapsed_ms',_negative_elapsed),('ok result without output',_no_output)]
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
        for key,value in [('version',True),('revision',True),('revision',-1),('revision',2**64),('audible_feedback','yes'),('visual_feedback','yes'),('output_volume_percent',True),('output_volume_percent',101),('previous_preferences',{'audible_feedback':True,'session_timeout_ms':30000,'output_volume_percent':-1}),('session_timeout_ms',0),('session_timeout_ms',60001),('wake_phrase','../private'),('previous_preferences',[]),('previous_preferences',{'audible_feedback':True,'session_timeout_ms':0})]:
            cfg=copy.deepcopy(BASE);cfg['preferences']={**valid,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):validate_snapshot(cfg,'r',0)
    def test_configuration_health_cannot_present_active_sessions(self):
        for status in ('safe_mode','restart_required'):
            valid={**BASE,'text_input_available':False,'configuration_status':status,'configuration_recovery_available':status=='safe_mode'}
            validate_snapshot(valid,'r',0)
            for key,value in [('state','capturing'),('session_id',1),('text_input_available',True),('configuration_recovery_available','yes')]:
                with self.subTest(status=status,key=key),self.assertRaises(ValueError):validate_snapshot({**valid,key:value},'r',0)
        with self.assertRaises(ValueError):validate_snapshot({**BASE,'configuration_status':'ready','configuration_recovery_available':True},'r',0)
    def test_pack_presentation_is_bounded_and_has_no_fake_phrases(self):
        pack={'version':1,'id':'pack','scope':'dev_virtual_en','preflight':'verified','engines':{'wake':'kws','stt':'stt','tts':'tts'},'wake_phrases':[{'id':'opaque','text':'Explicit words','qualification':'dev_qualified'}],'active_phrase':'opaque','default_phrase':'opaque','voice':'Alba','language':'en','audio_input':'virtual_pcm','audio_output':'virtual'}
        validate_snapshot({**BASE,'base_pack':pack},'r',0)
        for key,value in [('version',True),('wake_phrases',[]),('wake_phrases',[{'id':'x','text':'no grant','qualification':'certified'}]),('active_phrase',[]),('default_phrase','missing'),('audio_input','microphone')]:
            with self.subTest(key=key),self.assertRaises(ValueError):validate_snapshot({**BASE,'base_pack':{**pack,key:value}},'r',0)
    def test_hub_cannot_fake_installation_or_publisher_verification(self):
        valid={'version':1,'status':'quarantined','repository':None,'catalog_sha256':None,'publisher_verified':False,'entries':[],'install_revision':0,'installed':[]}
        validate_snapshot({**BASE,'hub':valid},'r',0)
        for key,value in [('version',True),('status','installed'),('publisher_verified',True),('entries',[{}]),('catalog_sha256','a'*64)]:
            with self.subTest(key=key),self.assertRaises(ValueError):validate_snapshot({**BASE,'hub':{**valid,key:value}},'r',0)
    def test_hub_approval_cannot_fake_authority_or_revision(self):
        entry={'plugin_id':'benign','semver':'1.0.0','publisher':'fixture','api_version':1,'targets':['linux_x86_64'],'license':'MIT','permissions':['notifications'],'dependencies':[],'conflicts':[],'download_size':1,'support_policy':'fixture','status':'not_installed','reason':'none','manifest_sha256':'a'*64,'permissions_approved':True}
        hub={'version':1,'status':'verified','repository':'https://github.com/a/b','catalog_sha256':'b'*64,'publisher_verified':False,'approval_revision':2**64-1,'entries':[entry],'install_revision':0,'installed':[]}
        validate_snapshot({**BASE,'hub':hub},'r',0)
        for key,value in [('approval_revision',True),('approval_revision',0),('approval_revision',2**64)]:
            with self.subTest(key=key),self.assertRaises(ValueError):validate_snapshot({**BASE,'hub':{**hub,key:value}},'r',0)
        for key,value in [('manifest_sha256','false'),('permissions_approved','yes'),('status','installed')]:
            with self.subTest(key=key),self.assertRaises(ValueError):validate_snapshot({**BASE,'hub':{**hub,'entries':[{**entry,key:value}]}},'r',0)
    def test_revoked_installed_plugin_can_be_reapproved_but_not_incompatible(self):
        entry={'plugin_id':'benign','semver':'1.0.0','publisher':'fixture','api_version':1,'targets':['linux_x86_64'],'license':'MIT','permissions':[],'dependencies':[],'conflicts':[],'download_size':15,'support_policy':'fixture','status':'installed','reason':'none','manifest_sha256':'a'*64,'permissions_approved':True,'payload_staged':False}
        record={'plugin_id':'benign','semver':'1.0.0','manifest_sha256':'a'*64,'state':'installed','runtime':'disabled','previous':None}
        hub={'version':1,'status':'verified','repository':'https://github.com/a/b','catalog_sha256':'b'*64,'publisher_verified':False,'approval_revision':1,'install_revision':1,'entries':[entry],'installed':[record]}
        validate_snapshot(snap(hub),'r',0)
        with self.assertRaises(ValueError):validate_snapshot(snap({**hub,'entries':[{**entry,'manifest_sha256':'c'*64}]}),'r',0)
        incompatible={**entry,'status':'incompatible','reason':'api_version'}
        with self.assertRaises(ValueError):validate_snapshot(snap({**hub,'entries':[incompatible],'installed':[]}),'r',0)
    def test_staging_progress_cannot_invent_payload_installation_or_bounds(self):
        entry={'plugin_id':'benign','semver':'1.0.0','publisher':'fixture','api_version':1,'targets':['linux_x86_64'],'license':'MIT','permissions':[],'dependencies':[],'conflicts':[],'download_size':15,'support_policy':'fixture','status':'not_installed','reason':'none','manifest_sha256':'a'*64,'permissions_approved':True,'payload_staged':False}
        transfer={'import_id':'transfer','plugin_id':'benign','received':0,'expected':15}
        hub={'version':1,'status':'verified','repository':'https://github.com/a/b','catalog_sha256':'b'*64,'publisher_verified':False,'approval_revision':1,'entries':[entry],'import':transfer,'install_revision':0,'installed':[]}
        validate_snapshot({**BASE,'hub':hub},'r',0)
        for key,value in [('received',True),('received',16),('expected',0),('expected',16),('plugin_id','missing')]:
            with self.subTest(key=key),self.assertRaises(ValueError):validate_snapshot({**BASE,'hub':{**hub,'import':{**transfer,key:value}}},'r',0)
        for key,value in [('payload_staged','yes'),('status','installed'),('permissions_approved',False)]:
            with self.subTest(key=key),self.assertRaises(ValueError):validate_snapshot({**BASE,'hub':{**hub,'entries':[{**entry,key:value}]}},'r',0)
    def test_installed_lifecycle_cannot_invent_execution_or_authority(self):
        digest='a'*64;new='c'*64
        record={'plugin_id':'benign','semver':'1.0.0','manifest_sha256':digest,'state':'installed','runtime':'disabled','previous':None}
        entry={'plugin_id':'benign','semver':'1.0.0','publisher':'fixture','api_version':1,'targets':['linux_x86_64'],'license':'MIT','permissions':[],'dependencies':[],'conflicts':[],'download_size':15,'support_policy':'fixture','status':'installed','reason':'none','manifest_sha256':digest,'permissions_approved':False,'payload_staged':False}
        hub={'version':1,'status':'verified','repository':'https://github.com/a/b','catalog_sha256':'b'*64,'publisher_verified':False,'approval_revision':1,'install_revision':3,'entries':[entry],'installed':[record]}
        validate_snapshot(snap(hub),'r',0)
        update={**entry,'status':'update_available','manifest_sha256':new,'payload_staged':True}
        validate_snapshot(snap({**hub,'entries':[update]}),'r',0)
        validate_snapshot(snap({**hub,'entries':[update],'installed':[{**record,'previous':{'semver':'0.9.0','manifest_sha256':'d'*64}}]}),'r',0)
        bad_cases=[
            ('runtime enabled',{**hub,'installed':[{**record,'runtime':'enabled'}]}),
            ('state running',{**hub,'installed':[{**record,'state':'running'}]}),
            ('installed without record',{**hub,'installed':[]}),
            ('update without record',{**hub,'entries':[update],'installed':[]}),
            ('update same manifest',{**hub,'entries':[{**update,'manifest_sha256':digest}]}),
            ('duplicate plugin_id',{**hub,'installed':[record,dict(record)]}),
            ('more than eight installed',{**hub,'installed':[{**record,'plugin_id':f'p{i}'} for i in range(9)]}),
            ('bad digest',{**hub,'installed':[{**record,'manifest_sha256':'A'*64}]}),
            ('bad previous digest',{**hub,'installed':[{**record,'previous':{'semver':'0.9.0','manifest_sha256':'short'}}]}),
            ('extra key',{**hub,'installed':[{**record,'payload_path':'/tmp/x'}]}),
            ('publisher verified',{**hub,'publisher_verified':True}),
            ('quarantined with installed',{**hub,'status':'quarantined','repository':None,'catalog_sha256':None,'entries':[],'installed':[record]}),
            ('missing install_revision',{k:v for k,v in hub.items() if k!='install_revision'}),
            ('install_revision bool',{**hub,'install_revision':True}),
            ('status installed on incompatible reason',{**hub,'entries':[{**entry,'reason':'api_version'}]}),
            ('payload staged on installed',{**hub,'entries':[{**entry,'payload_staged':True}]}),
        ]
        for name,bad in bad_cases:
            with self.subTest(case=name),self.assertRaises(ValueError):validate_snapshot(snap(bad),'r',0)
    def test_plugin_snapshot_accepts_valid_and_rejects_forged_state(self):
        validate_snapshot(plugin_snapshot(),'r',0)
        failed=plugin_snapshot('failed',True);_item(failed).update(last_error='plugin_crashed');validate_snapshot(failed,'r',0)
        disabled=plugin_snapshot('disabled',False);disabled.pop('capability_result');validate_snapshot(disabled,'r',0)
        quarantined=plugin_snapshot('quarantined',False);quarantined['hub']['installed'][0]['state']='quarantined';quarantined.pop('capability_result');validate_snapshot(quarantined,'r',0)
        absent={k:v for k,v in BASE.items() if k!='plugins'};validate_snapshot(absent,'r',0)
        for name,mutate in CASES:
            cfg=copy.deepcopy(plugin_snapshot());mutate(cfg)
            with self.subTest(case=name),self.assertRaises(ValueError):validate_snapshot(cfg,'r',0)
        without_plugins=copy.deepcopy(plugin_snapshot());del without_plugins['plugins']
        with self.subTest(case='plugins missing with hub'),self.assertRaises(ValueError):validate_snapshot(without_plugins,'r',0)
    def test_plugins_absent_only_for_hubless_core(self):
        old={k:v for k,v in BASE.items() if k!='plugins'};validate_snapshot(old,'r',0)
        self.assertGreaterEqual(len(CASES),15)
        with self.assertRaises(ValueError):validate_snapshot({**old,'plugins':{'revision':0,'status':'ok','items':[{'plugin_id':'x','semver':'1','capabilities':[],'state':'disabled','enabled':False,'restarts':0,'last_error':None}]}},'r',0)
    def test_plugin_requests_bind_revision_and_bounded_input_over_socket(self):
        def at(state,enabled,revision,result=None):
            snap=plugin_snapshot(state,enabled);snap['plugins']['revision']=revision;snap['preferences']={'version':1,'revision':0,'audible_feedback':True,'session_timeout_ms':30000}
            if result is None:snap.pop('capability_result',None)
            else:snap['capability_result']=result
            return snap
        def next_request(peer):
            pump(lambda:peer.canReadLine());return json.loads(bytes(peer.readLine()))
        def answer(peer,request,snap,code='ok'):
            peer.write((json.dumps({**snap,'request_id':request['request_id'],'code':code})+'\n').encode());peer.flush()
        with tempfile.TemporaryDirectory(prefix='gideon-plugin-ipc-') as td:
            root=Path(td);root.chmod(0o700);server=QLocalServer();self.assertTrue(server.listen(str(root/'core.sock')));(root/'core.sock').chmod(0o600)
            bridge=Bridge(root);pump(lambda:server.hasPendingConnections());peer=server.nextPendingConnection()
            answer(peer,next_request(peer),at('disabled',False,1));pump(lambda:bridge.connected);bridge.poll.stop()
            self.assertTrue(bridge.pluginsAvailable);self.assertEqual(bridge.pluginsRevision,'1')
            bridge.enablePlugin('dummy_echo');request=next_request(peer)
            self.assertEqual(request,{'version':1,'request_id':request['request_id'],'op':'plugin_enable','revision':1,'plugin_id':'dummy_echo'})
            answer(peer,request,at('starting',True,2));pump(lambda:bridge.pending is None);bridge.poll.stop()
            self.assertEqual(bridge.pluginResult,'Plugin ativado');self.assertEqual(bridge.pluginsRevision,'2')
            bridge.invokeCapability('dummy_echo.echo','x'*300);request=next_request(peer)
            self.assertEqual(request['op'],'capability_invoke');self.assertEqual(request['capability'],'dummy_echo.echo');self.assertEqual(request['input'],{'text':'x'*256});self.assertEqual(request['deadline_ms'],3000);self.assertNotIn('revision',request)
            answer(peer,request,at('running',True,2));pump(lambda:bridge.pending is None);bridge.poll.stop()
            self.assertEqual(bridge.pluginResult,'Invocando capability…');self.assertEqual(bridge.capabilityResultText,'')
            bridge.refresh();answer(peer,next_request(peer),at('running',True,2,{'capability':'dummy_echo.echo','plugin_id':'dummy_echo','ok':True,'output':{'text':'HELLO','count':1},'elapsed_ms':4}));pump(lambda:bridge.capabilityResultText=='HELLO');bridge.poll.stop()
            self.assertEqual(bridge.pluginResult,'');
            bridge.revokePlugin('dummy_echo');request=next_request(peer)
            self.assertEqual((request['op'],request['revision'],request['plugin_id']),('plugin_revoke',2,'dummy_echo'))
            answer(peer,request,at('disabled',False,3));pump(lambda:bridge.pending is None);bridge.poll.stop()
            self.assertEqual(bridge.pluginResult,'Permissões revogadas; plugin desativado');self.assertEqual(bridge.capabilityResultText,'')
            bridge.enablePlugin('dummy_echo');request=next_request(peer)
            answer(peer,request,at('disabled',False,3),'stale_plugin_revision');pump(lambda:bridge.pending is None);bridge.poll.stop()
            self.assertEqual(bridge.pluginResult,'stale_plugin_revision')
            bridge.poll.stop();bridge.timeout.stop();bridge.socket.abort();bridge.retry.stop();peer.close();server.close()
    def test_real_socket_malformed_nested_data_and_deep_json_clear_stale_state(self):
        for deep in (False,True,"preferences","hub"):
            with self.subTest(deep=deep),tempfile.TemporaryDirectory(prefix='gideon-ipc-audit-') as td:
                root=Path(td);root.chmod(0o700);server=QLocalServer();self.assertTrue(server.listen(str(root/'core.sock')));(root/'core.sock').chmod(0o600)
                bridge=Bridge(root);pump(lambda:server.hasPendingConnections());peer=server.nextPendingConnection();pump(lambda:peer.canReadLine())
                request=json.loads(bytes(peer.readLine()));good=copy.deepcopy(BASE);good['request_id']=request['request_id'];peer.write((json.dumps(good)+'\n').encode());peer.flush();pump(lambda:bridge.connected)
                bridge.refresh();pump(lambda:peer.canReadLine());request=json.loads(bytes(peer.readLine()))
                if deep is True:bad='['*1100+'0'+']'*1100+'\n'
                else:
                    good['request_id']=request['request_id']
                    if deep=='hub':good['hub']={'version':1,'status':'verified','publisher_verified':True,'entries':[]}
                    elif deep=='preferences':good['preferences']={'version':1,'revision':True,'audible_feedback':False,'session_timeout_ms':30000}
                    else:good['command']=[]
                    bad=json.dumps(good)+'\n'
                peer.write(bad.encode());peer.flush();pump(lambda:not bridge.connected)
                self.assertEqual(bridge.snapshot,{});self.assertFalse(bridge.textAvailable);self.assertEqual(bridge.result,'')
                bridge.poll.stop();bridge.timeout.stop();bridge.socket.abort();bridge.retry.stop();peer.close();server.close()
if __name__=='__main__':unittest.main()
