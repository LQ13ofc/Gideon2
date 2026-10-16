#!/usr/bin/env python3
"""Malformed IPC over actual Qt local sockets; no GUI/session/devices are opened."""
import copy,json,os,re,subprocess,sys,tempfile,time,unittest
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from bridge import Bridge,CHAT_STATE_LABELS,CODE_MESSAGES,PREFS_DONE,SECTION_SIGNALS,STALE_MESSAGE,bounded_output,chat_input_size,chat_messages_for,chat_problem,llm_url_ok,text_problem,valid_key,validate_snapshot
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalServer
# The QML child process needs QGuiApplication, which cannot coexist with a QCoreApplication.
QML_CHILD=sys.argv[1:2]==['--qml-child'];QML_CHAT_CHILD=sys.argv[1:2]==['--qml-chat-child']
APP=None if (QML_CHILD or QML_CHAT_CHILD) else QCoreApplication([])
FAKE_KEY='fake-key-0123456789abcdef'
EMPTY_LLM={'revision':0,'config':None,'secrets':{'openrouter':False,'opencode':False,'google':False,'custom':False}}
BASE={'version':1,'request_id':'r','code':'ok','state':'idle','sequence':1,'session_id':None,'transcript':None,'command':None,'events':[],'text_input_available':True,'speech_samples':0,'speech_status':'idle','wake_status':'unavailable','stt_status':'unavailable','plugins':{'revision':0,'status':'ok','items':[]},'llm':EMPTY_LLM,'tool_proposals':[]}
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
            bridge.revokePlugin('dummy_echo','2');request=next_request(peer)
            self.assertEqual((request['op'],request['revision'],request['plugin_id']),('plugin_revoke',2,'dummy_echo'))
            answer(peer,request,at('disabled',False,3));pump(lambda:bridge.pending is None);bridge.poll.stop()
            self.assertEqual(bridge.pluginResult,'Permissões revogadas; plugin desativado');self.assertEqual(bridge.capabilityResultText,'')
            bridge.enablePlugin('dummy_echo');request=next_request(peer)
            answer(peer,request,at('disabled',False,3),'stale_plugin_revision');pump(lambda:bridge.pending is None);bridge.poll.stop()
            self.assertEqual(bridge.pluginResult,CODE_MESSAGES['stale_plugin_revision'])
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
def wait_idle(ms=60):
    until=time.monotonic()+ms/1000
    while time.monotonic()<until:APP.processEvents();time.sleep(.005)
def next_request(peer):
    pump(lambda:peer.canReadLine());return json.loads(bytes(peer.readLine()))
def answer(peer,request,snap,code='ok'):
    peer.write((json.dumps({**snap,'request_id':request['request_id'],'code':code})+'\n').encode());peer.flush()
def settle(bridge):
    pump(lambda:bridge.pending is None);bridge.poll.stop()
def ready(snap):
    snap['preferences']={'version':1,'revision':0,'audible_feedback':True,'session_timeout_ms':30000};return snap
def dual_snapshot():
    """Two installed, approved, running plugins: enough to prove per-plugin state survives unrelated updates."""
    s=ready(copy.deepcopy(plugin_snapshot('running',True)))
    entry=copy.deepcopy(s['hub']['entries'][0]);entry.update(plugin_id='second_echo',capabilities=['second_echo.echo'])
    record=copy.deepcopy(s['hub']['installed'][0]);record['plugin_id']='second_echo'
    item=copy.deepcopy(s['plugins']['items'][0]);item.update(plugin_id='second_echo',capabilities=['second_echo.echo'],state='running',enabled=True)
    s['hub']['entries'].append(entry);s['hub']['installed'].append(record);s['plugins']['items'].append(item)
    return validate_snapshot(s,'r',0)
def connect_bridge(test,first):
    """Real local socket Core stand-in: answers the first snapshot and returns (bridge, peer)."""
    td=tempfile.TemporaryDirectory(prefix='gideon-ipc-');test.addCleanup(td.cleanup)
    root=Path(td.name);root.chmod(0o700);server=QLocalServer();test.assertTrue(server.listen(str(root/'core.sock')));(root/'core.sock').chmod(0o600)
    bridge=Bridge(root);pump(lambda:server.hasPendingConnections());peer=server.nextPendingConnection()
    def close():
        bridge.poll.stop();bridge.timeout.stop();bridge.socket.abort();bridge.retry.stop();peer.close();server.close()
    test.addCleanup(close)
    answer(peer,next_request(peer),first);pump(lambda:bridge.connected);settle(bridge)
    return bridge,peer
class Regressions(unittest.TestCase):
    def test_bounded_output_counts_core_utf8_bytes(self):
        accepted={'text':'á'*4000}
        self.assertEqual(len(json.dumps(accepted,separators=(',',':'),ensure_ascii=False).encode('utf-8')),8011)
        self.assertTrue(bounded_output(accepted))
        snap=plugin_snapshot();_result(snap)['output']=accepted;validate_snapshot(snap,'r',0)
        self.assertFalse(bounded_output({'text':'á'*4500}))
        self.assertFalse(bounded_output({'text':'x'*9000}))
        self.assertFalse(bounded_output({'text':float('nan')}))
        self.assertFalse(bounded_output(['x']))
        over=plugin_snapshot();_result(over)['output']={'text':'á'*4500}
        with self.assertRaises(ValueError):validate_snapshot(over,'r',0)
    def test_non_object_entries_are_invalid_not_exceptions(self):
        hub={'version':1,'status':'verified','repository':'https://github.com/a/b','catalog_sha256':'b'*64,'publisher_verified':False,'approval_revision':1,'install_revision':0,'entries':[5],'installed':[],'import':{'import_id':'t','plugin_id':'x','received':0,'expected':15}}
        with self.assertRaises(ValueError):validate_snapshot({**BASE,'hub':hub},'r',0)
    def test_status_enums_are_exact_core_sets(self):
        for key,value in [('wake_status','replay_finished'),('wake_status','replaying'),('stt_status','ready'),('speech_status','timed_out'),('speech_status','capture_completed'),('speech_status','cancelled')]:
            with self.subTest(key=key,value=value):validate_snapshot({**BASE,key:value},'r',0)
        for key,value in [('wake_status','ready'),('stt_status','replaying'),('speech_status','paused'),('speech_status',None)]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):validate_snapshot({**BASE,key:value},'r',0)
    def test_text_rules_match_core(self):
        self.assertEqual(text_problem('   '),'Texto vazio')
        self.assertIsNone(text_problem('á'*256))
        self.assertIsNotNone(text_problem('á'*257))
        self.assertIsNotNone(text_problem('ok\ntext'))
        self.assertIsNotNone(text_problem('a\tb'))
    def test_snapshot_sections_notify_only_their_own_consumers(self):
        bridge=Bridge('/nonexistent-gideon-root');counts=Counter()
        for signal in SECTION_SIGNALS.values():getattr(bridge,signal).connect(lambda n=signal:counts.update([n]))
        old=ready(plugin_snapshot('running',True))
        def changed(mutate):
            new=copy.deepcopy(old);mutate(new);counts.clear();bridge._publish(old,new);return dict(counts)
        self.assertEqual(changed(lambda s:s.update(sequence=2,state='capturing')),{'sessionChanged':1})
        self.assertEqual(changed(lambda s:_item(s).update(restarts=1)),{'pluginsChanged':1})
        self.assertEqual(changed(lambda s:s['preferences'].update(visual_feedback=False)),{'preferencesChanged':1})
        self.assertEqual(changed(lambda s:s['hub'].update(approval_revision=2)),{'hubChanged':1})
        self.assertEqual(changed(lambda s:s['hub']['entries'][0].update(payload_staged=True,status='update_available',manifest_sha256='c'*64)),{'hubEntriesChanged':1})
        self.assertEqual(changed(lambda s:s.update(capability_result=None)),{'capabilityChanged':1})
    def test_text_results_map_and_clear_only_on_ok(self):
        bridge,peer=connect_bridge(self,ready(copy.deepcopy(BASE)))
        sent=[];bridge.textSent.connect(sent.append)
        bridge.submitText('   ');self.assertEqual(bridge.textResult,'Texto vazio');wait_idle();self.assertFalse(peer.canReadLine())
        bridge.submitText('á'*300);self.assertEqual(bridge.textResult,'Texto acima de 512 bytes')
        bridge.submitText('ok\ntext');self.assertIsNotNone(bridge.textResult)
        wait_idle();self.assertFalse(peer.canReadLine())
        bridge.submitText('hello');bridge.submitText('second')
        self.assertEqual(bridge.textResult,'Texto na fila para envio')
        request=next_request(peer);self.assertEqual((request['op'],request['raw']),('text','hello'))
        answer(peer,request,ready(copy.deepcopy(BASE)),'busy')
        pump(lambda:bridge.textResult==CODE_MESSAGES['busy']);self.assertEqual(sent,[])
        # The queued text is re-checked and sent after the rejected answer; its field is cleared only on ok.
        request=next_request(peer);self.assertEqual(request['raw'],'second')
        answer(peer,request,ready(copy.deepcopy(BASE)),'ok');settle(bridge)
        self.assertEqual(sent,['second']);self.assertEqual(bridge.textResult,'Texto enviado')
    def test_queued_text_is_checked_again_before_sending(self):
        bridge,peer=connect_bridge(self,ready(copy.deepcopy(BASE)))
        sent=[];bridge.textSent.connect(sent.append)
        bridge.submitText('first');bridge.submitText('second')
        request=next_request(peer);self.assertEqual(request['raw'],'first');answer(peer,request,ready(copy.deepcopy(BASE)),'ok')
        pump(lambda:sent==['first'])
        request=next_request(peer);self.assertEqual((request['op'],request['raw']),('text','second'))
        answer(peer,request,ready(copy.deepcopy(BASE)),'ok');settle(bridge)
        self.assertEqual(sent,['first','second'])
    def test_stale_confirmations_are_refused_without_sending(self):
        bridge,peer=connect_bridge(self,ready(plugin_snapshot('disabled',False)))
        self.assertEqual((bridge.pluginsRevision,bridge.hubApprovalRevision,bridge.hubInstallRevision),('1','1','1'))
        bridge.revokePlugin('dummy_echo','0');self.assertEqual(bridge.pluginResult,STALE_MESSAGE)
        bridge.removeHub('dummy_echo','0');self.assertEqual(bridge.hubApprovalResult,STALE_MESSAGE)
        bridge.approveHub('dummy_echo','a'*64,[],True,'0');self.assertEqual(bridge.hubApprovalResult,STALE_MESSAGE)
        wait_idle();self.assertFalse(peer.canReadLine())
        bridge.approveHub('dummy_echo','a'*64,[],True,'1');request=next_request(peer)
        self.assertEqual((request['op'],request['revision'],request['plugin_id']),('hub_approve',1,'dummy_echo'))
        answer(peer,request,ready(plugin_snapshot('disabled',False)),'ok');settle(bridge)
        self.assertEqual(bridge.hubApprovalResult,'Permissões aprovadas: dummy_echo')
    def test_preference_rejection_is_reported_and_resynced(self):
        bridge,peer=connect_bridge(self,ready(copy.deepcopy(BASE)))
        seen=[];bridge.prefsSettled.connect(seen.append)
        bridge.savePreferences(False,1000);request=next_request(peer);self.assertEqual(request['op'],'preferences')
        answer(peer,request,ready(copy.deepcopy(BASE)),'busy');settle(bridge)
        self.assertEqual(seen,[CODE_MESSAGES['busy']]);self.assertEqual(bridge.preferencesResult,CODE_MESSAGES['busy'])
        bridge.savePreferences(True,30000);request=next_request(peer)
        answer(peer,request,ready(copy.deepcopy(BASE)),'ok');settle(bridge)
        self.assertEqual(seen[-1],PREFS_DONE)
    def test_malformed_entries_and_oversize_line_take_the_offline_path(self):
        hub={'version':1,'status':'verified','repository':'https://github.com/a/b','catalog_sha256':'b'*64,'publisher_verified':False,'approval_revision':1,'install_revision':0,'entries':[5],'installed':[],'import':{'import_id':'t','plugin_id':'x','received':0,'expected':15}}
        cases=[lambda rid:(json.dumps({**BASE,'hub':hub,'request_id':rid})+'\n').encode(),lambda rid:b'x'*70000]
        for index,payload in enumerate(cases):
            with self.subTest(case=index):
                bridge,peer=connect_bridge(self,ready(copy.deepcopy(BASE)))
                bridge.refresh();request=next_request(peer)
                peer.write(payload(request['request_id']));peer.flush()
                pump(lambda:not bridge.connected);self.assertEqual(bridge.snapshot,{})
    def test_unrelated_sections_keep_qml_delegates(self):
        """Qt child: real QML window, real Repeaters; the typed draft must survive unrelated and plugin updates."""
        env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_QUICK_CONTROLS_STYLE':'Basic'}
        proc=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--qml-child'],env=env,capture_output=True,text=True,timeout=240)
        self.assertEqual(proc.returncode,0,(proc.stdout+proc.stderr)[-4000:])
LLM_CONFIG={'provider':'google','model':'gemini-3.5-flash-lite','custom_url':None,'cloud_consent':True}
def llm_state(revision=1,config=None,secrets=None):
    return {'revision':revision,'config':config,'secrets':secrets or {'openrouter':False,'opencode':False,'google':True,'custom':False}}
def tool_item(pid='tool_1_1',tool='open_app',state='pending',args=None,reason=None,result=None):
    return {'proposal_id':pid,'plugin_id':'llm_engine','call_id':'call_'+pid,'tool':tool,'args':args if args is not None else {'desktop_id':'brave.desktop'},'state':state,'reason':reason,'result':result}
def chat_result(text='Olá',ok=True,error=None,partial=None,extra=None):
    result={'capability':'llm_engine.chat','plugin_id':'llm_engine','ok':ok,'elapsed_ms':12}
    if ok:result['output']={'text':text,'finish_reason':'stop','tool_calls':[]}
    else:result['error']=error
    if partial is not None:result['partial']=partial
    result.update(extra or {})
    return result
def chat_snapshot(state='running',enabled=True,result=None,partial=None,tools=None,llm=None,capabilities=('llm_engine.chat',)):
    """Installed, approved llm_engine plugin stand-in that exposes only the chat capability (no network in tests)."""
    digest='a'*64
    entry={'plugin_id':'llm_engine','semver':'0.1.0','publisher':'fixture','api_version':1,'targets':['linux_x86_64'],'license':'MIT','permissions':['network.llm'],'dependencies':[],'conflicts':[],'download_size':15,'support_policy':'fixture','status':'installed','reason':'none','manifest_sha256':digest,'permissions_approved':True,'payload_staged':False,'runtime':'python3_script','capabilities':list(capabilities)}
    record={'plugin_id':'llm_engine','semver':'0.1.0','manifest_sha256':digest,'state':'installed','runtime':'disabled','previous':None}
    hub={'version':1,'status':'verified','repository':'https://github.com/a/b','catalog_sha256':'b'*64,'publisher_verified':False,'approval_revision':1,'install_revision':1,'entries':[entry],'installed':[record]}
    item={'plugin_id':'llm_engine','semver':'0.1.0','capabilities':list(capabilities),'state':state,'enabled':enabled,'restarts':0,'last_error':None}
    snap={**ready(copy.deepcopy(BASE)),'hub':hub,'plugins':{'revision':1,'status':'ok','items':[item]},'llm':llm or llm_state(config=LLM_CONFIG),'tool_proposals':tools or []}
    if result is not None:snap['capability_result']=result
    if partial is not None:snap['partial']=partial
    return snap
def respond(bridge,peer,snap,code='ok'):
    request=next_request(peer);answer(peer,request,snap,code);settle(bridge);return request
def start_chat(test,bridge,peer,text='oi'):
    bridge.sendChat(text);request=next_request(peer);answer(peer,request,chat_snapshot());settle(bridge);return request
def secret_strings(value):
    if isinstance(value,str):yield value
    elif isinstance(value,dict):
        for key,child in value.items():yield from secret_strings(key);yield from secret_strings(child)
    elif isinstance(value,(list,tuple)):
        for child in value:yield from secret_strings(child)
def assert_no_key(test,bridge,key=FAKE_KEY):
    """The key may not survive in any bridge attribute, cached snapshot or result text after the write."""
    for name,value in vars(bridge).items():
        for text in secret_strings(value):test.assertNotIn(key,text,name)
    for text in secret_strings(bridge.snapshot):test.assertNotIn(key,text,'snapshot')
    for text in secret_strings(bridge.results):test.assertNotIn(key,text,'results')
class LlmContract(unittest.TestCase):
    def test_llm_snapshot_accepts_exact_shape_and_null_config(self):
        validate_snapshot({**BASE,'llm':llm_state(config=LLM_CONFIG)},'r',0)
        validate_snapshot({**BASE,'llm':llm_state()},'r',0)
        for config in [{'provider':'custom','model':'local-model','custom_url':'https://example.test/v1','cloud_consent':False},{'provider':'custom','model':'local','custom_url':'http://127.0.0.1:8080/v1','cloud_consent':True},{'provider':'opencode','model':'m:1/x-y.z','custom_url':None,'cloud_consent':False}]:
            with self.subTest(config=config):validate_snapshot({**BASE,'llm':llm_state(config=config)},'r',0)
    def test_llm_snapshot_rejects_key_material_at_every_level(self):
        cases=[('top-level key',lambda l:l.update(key=FAKE_KEY)),('secrets key',lambda l:l['secrets'].update(key=FAKE_KEY)),('secrets value is the key',lambda l:l['secrets'].update(google=FAKE_KEY)),('config key',lambda l:l['config'].update(key=FAKE_KEY)),('config api_key',lambda l:l['config'].update(api_key=FAKE_KEY)),('secrets missing provider',lambda l:l['secrets'].pop('custom')),('secrets extra provider',lambda l:l['secrets'].update(llamacpp=False))]
        for name,mutate in cases:
            llm=llm_state(config=LLM_CONFIG);mutate(llm)
            with self.subTest(case=name),self.assertRaises(ValueError):validate_snapshot({**BASE,'llm':llm},'r',0)
    def test_llm_config_fields_match_core_rules(self):
        bad=[{'provider':'llamacpp'},{'model':'bad model'},{'model':'m'*129},{'model':''},{'provider':'custom','custom_url':None},{'custom_url':'https://x.test'},{'provider':'custom','custom_url':'http://example.test'},{'provider':'custom','custom_url':'https://u:p@example.test'},{'provider':'custom','custom_url':'https://example.test?x=1'},{'cloud_consent':'yes'},{'cloud_consent':1},{'extra':1}]
        for change in bad:
            config={**LLM_CONFIG,**change}
            with self.subTest(change=change),self.assertRaises(ValueError):validate_snapshot({**BASE,'llm':llm_state(config=config)},'r',0)
        with self.assertRaises(ValueError):validate_snapshot({**BASE,'llm':llm_state(revision=True,config=LLM_CONFIG)},'r',0)
        with self.assertRaises(ValueError):validate_snapshot({**BASE,'llm':llm_state(revision=-1,config=LLM_CONFIG)},'r',0)
        validate_snapshot({**BASE,'llm':llm_state(revision=2**64-1,config=LLM_CONFIG)},'r',0)
        for flag in ('google','custom'):
            secrets={'openrouter':False,'opencode':False,'google':False,'custom':False};secrets[flag]='yes'
            with self.subTest(flag=flag),self.assertRaises(ValueError):validate_snapshot({**BASE,'llm':llm_state(secrets=secrets)},'r',0)
    def test_partial_is_a_bounded_string_or_absent(self):
        for partial in ('a'*16384,'á'*8192,'linha\nDois',None):
            validate_snapshot({**BASE,'partial':partial},'r',0)
        validate_snapshot(BASE,'r',0)
        for partial in ('á'*8193,'x'*16385,5,[],{'text':'x'}):
            with self.subTest(partial=str(partial)[:20]),self.assertRaises(ValueError):validate_snapshot({**BASE,'partial':partial},'r',0)
    def test_tool_proposals_accept_exact_bounded_items(self):
        items=[tool_item('tool_1_1'),tool_item('tool_1_2',tool='set_volume',args={'level':40}),tool_item('tool_1_3',tool='mute',args={}),tool_item('tool_1_4',tool='get_time',state='executed',args={'flag':True,'nothing':None,'ratio':0.5},result='ok')]
        validate_snapshot({**BASE,'tool_proposals':items},'r',0)
        validate_snapshot({**BASE,'tool_proposals':[tool_item(tool='nope',reason='unknown_tool',state='denied')]},'r',0)
        # The Core keeps the model's args as found: a malformed call has null args and nested or odd text is still valid JSON.
        validate_snapshot({**BASE,'tool_proposals':[tool_item(state='denied',args=None,reason='invalid_args'),tool_item('tool_1_2',args={'a':{'b':1}}),tool_item('tool_1_3',tool='open\napp'),tool_item('tool_1_4',tool='x'*100)]},'r',0)
    def test_tool_proposals_reject_forged_or_oversize_items(self):
        def item(**change):return {**tool_item(),**change}
        cases=[
            ('five items',{'tool_proposals':[tool_item(f'tool_1_{i}') for i in range(5)]}),
            ('extra authority key',{'tool_proposals':[{**tool_item(),'authority':'model'}]}),
            ('unknown state',{'tool_proposals':[item(state='approved')]}),
            ('duplicate proposal',{'tool_proposals':[tool_item(),tool_item()]}),
            ('args too deep',{'tool_proposals':[item(args={'a':{'b':{'c':{'d':{'e':1}}}}})]}),
            ('args oversize',{'tool_proposals':[item(args={'k':'x'*8200})]}),
            ('args infinite',{'tool_proposals':[item(args={'level':float('inf')})]}),
            ('tool name over 256 bytes',{'tool_proposals':[item(tool='x'*257)]}),
            ('call id over 64 bytes',{'tool_proposals':[item(call_id='c'*65)]}),
            ('reason not snake',{'tool_proposals':[item(reason='User Denied')]}),
            ('result over 1 KiB',{'tool_proposals':[item(state='executed',result='x'*1025)]}),
            ('proposal id with space',{'tool_proposals':[item(proposal_id='tool 1')]}),
            ('plugin id with slash',{'tool_proposals':[item(plugin_id='bad/plugin')]}),
            ('proposals not a list',{'tool_proposals':{'proposal_id':'tool_1_1'}}),
            ('missing result key',{'tool_proposals':[{k:v for k,v in tool_item().items() if k!='result'}]}),
        ]
        for name,change in cases:
            with self.subTest(case=name),self.assertRaises(ValueError):validate_snapshot({**BASE,**change},'r',0)
    def test_capability_result_partial_and_http_status_are_strict(self):
        validate_snapshot(chat_snapshot(result=chat_result('texto\nlinha',partial='parcial\nmais')),'r',0)
        validate_snapshot(chat_snapshot(result=chat_result(ok=False,error='http_error',extra={'http_status':429})),'r',0)
        validate_snapshot(chat_snapshot(result=chat_result(ok=False,error='timeout',partial='parc')),'r',0)
        bad=[chat_result(ok=False,error='http_error',extra={'http_status':99}),chat_result(ok=False,error='http_error',extra={'http_status':600}),chat_result(ok=False,error='timeout',extra={'http_status':429}),chat_result(extra={'http_status':429}),chat_result(ok=False,error='http_error',extra={'http_status':True}),chat_result(partial=5),chat_result(partial='x'*16385)]
        for result in bad:
            with self.subTest(result=str(result)[:60]),self.assertRaises(ValueError):validate_snapshot(chat_snapshot(result=result),'r',0)
    def test_snapshot_requires_llm_and_tool_sections(self):
        for key in ('llm','tool_proposals'):
            cfg={k:v for k,v in BASE.items() if k!=key}
            with self.subTest(missing=key),self.assertRaises(ValueError):validate_snapshot(cfg,'r',0)
    def test_chat_text_limits_are_utf8_bytes(self):
        self.assertEqual(chat_problem('   '),'Mensagem vazia')
        self.assertIsNone(chat_problem('á'*2048));self.assertIsNotNone(chat_problem('á'*2049))
        self.assertIsNone(chat_problem('x'*4096));self.assertIsNotNone(chat_problem('x'*4097))
        self.assertIsNotNone(chat_problem('oi\nlinha'));self.assertIsNotNone(chat_problem('a\tb'))
    def test_chat_history_trims_oldest_turns_to_8kib_with_accents(self):
        history=[{'role':'user' if i%2==0 else 'assistant','text':'á'*800,'state':'done'} for i in range(40)]
        messages=chat_messages_for(history,'í'*2000)
        self.assertIsNotNone(messages);self.assertLessEqual(chat_input_size(messages),8192)
        self.assertEqual(messages[-1],{'role':'user','content':'í'*2000})
        kept=messages[:-1];self.assertTrue(0<len(kept)<31)
        self.assertEqual(kept,[{'role':m['role'],'content':m['text']} for m in history][-len(kept):])
        self.assertIsNone(chat_messages_for([],'"'*4096))
        self.assertEqual(chat_messages_for([],'á'*2048)[-1]['content'],'á'*2048)
    def test_chat_history_drops_unfinished_oversize_and_empty_turns_and_caps_at_31(self):
        history=[{'role':'assistant','text':'partial','state':'error'},{'role':'user','text':'ok','state':'done'},{'role':'assistant','text':'z'*4097,'state':'done'},{'role':'assistant','text':'','state':'done'},{'role':'assistant','text':'cancelada','state':'cancelled'}]
        self.assertEqual(chat_messages_for(history,'next'),[{'role':'user','content':'ok'},{'role':'user','content':'next'}])
        many=[{'role':'user','text':f'm{i}','state':'done'} for i in range(50)]
        messages=chat_messages_for(many,'last');self.assertEqual(len(messages),32);self.assertEqual(messages[0]['content'],'m19')
    def test_secret_key_and_url_rules_match_core(self):
        self.assertTrue(valid_key(FAKE_KEY));self.assertTrue(valid_key('!'*8))
        for key in ('short','a'*257,'with space key1','tab\tkey1234','çççççççç',''):
            with self.subTest(key=key):self.assertFalse(valid_key(key))
        for url in ('https://api.example.test/v1','http://127.0.0.1:8080/v1','http://localhost'):
            with self.subTest(url=url):self.assertTrue(llm_url_ok(url))
        for url in ('http://example.test','https://user@example.test','https://example.test?x=1','ftp://example.test',' https://example.test','https://example.test:99999','https://example.test#frag'):
            with self.subTest(url=url):self.assertFalse(llm_url_ok(url))
class LlmBridge(unittest.TestCase):
    def test_new_sections_notify_only_their_consumers(self):
        bridge=Bridge('/nonexistent-gideon-root');counts=Counter()
        for signal in set(SECTION_SIGNALS.values()):getattr(bridge,signal).connect(lambda n=signal:counts.update([n]))
        old=chat_snapshot()
        def changed(mutate):
            new=copy.deepcopy(old);mutate(new);counts.clear();bridge._publish(old,new);return dict(counts)
        self.assertEqual(changed(lambda s:s['llm'].update(revision=4)),{'llmChanged':1})
        self.assertEqual(changed(lambda s:s.update(partial='oi')),{'chatChanged':1})
        self.assertEqual(changed(lambda s:s.update(tool_proposals=[tool_item()])),{'toolsChanged':1})
        self.assertEqual(changed(lambda s:s.update(sequence=2,state='capturing')),{'sessionChanged':1})
    def test_chat_available_requires_running_chat_capability(self):
        bridge=Bridge('/nonexistent-gideon-root');bridge.online=True
        bridge._apply(validate_snapshot(chat_snapshot(),'r',0));self.assertTrue(bridge.chatAvailable)
        for snap in (chat_snapshot(state='starting'),chat_snapshot(state='disabled',enabled=False),chat_snapshot(capabilities=('llm_engine.status',))):
            bridge._apply(validate_snapshot(snap,'r',0));self.assertFalse(bridge.chatAvailable)
        bridge._apply(validate_snapshot(chat_snapshot(state='starting'),'r',0));bridge.sendChat('oi')
        self.assertEqual(bridge.chatResult,'Motor LLM indisponível');self.assertEqual(bridge.chatMessages,[])
    def test_send_chat_request_is_exact_and_bounded(self):
        bridge,peer=connect_bridge(self,chat_snapshot())
        bridge.sendChat('Olá, tudo bem?')
        request=next_request(peer)
        self.assertEqual(set(request),{'version','request_id','op','capability','input','deadline_ms'})
        self.assertEqual((request['op'],request['capability'],request['deadline_ms']),('capability_invoke','llm_engine.chat',10000))
        self.assertEqual(request['input'],{'messages':[{'role':'user','content':'Olá, tudo bem?'}],'tools':True,'max_tokens':512})
        self.assertEqual(bridge.chatResult,'Invocando capability…')
        answer(peer,request,chat_snapshot());settle(bridge)
        self.assertEqual(bridge.chatState,'waiting');self.assertEqual(bridge.chatMessages,[{'role':'user','text':'Olá, tudo bem?','state':'done'}])
    def test_chat_state_machine_streams_then_finishes_once(self):
        bridge,peer=connect_bridge(self,chat_snapshot())
        start_chat(self,bridge,peer,'oi');self.assertEqual(bridge.chatState,'waiting')
        bridge.refresh();respond(bridge,peer,chat_snapshot(partial='Ol'))
        self.assertEqual((bridge.chatState,bridge.chatPartial),('streaming','Ol'))
        bridge.refresh();respond(bridge,peer,chat_snapshot(partial='Olá'))
        self.assertEqual(bridge.chatPartial,'Olá')
        bridge.refresh();respond(bridge,peer,chat_snapshot(result=chat_result('Olá, tudo bem!')))
        self.assertEqual(bridge.chatState,'done');self.assertEqual(bridge.chatPartial,'')
        self.assertEqual(bridge.chatMessages[-1],{'role':'assistant','text':'Olá, tudo bem!','state':'done'})
        for _ in range(2):
            bridge.refresh();respond(bridge,peer,chat_snapshot(result=chat_result('Olá, tudo bem!')))
        self.assertEqual(len(bridge.chatMessages),2)
    def test_chat_cancel_is_sent_and_result_keeps_partial_as_cancelled(self):
        bridge,peer=connect_bridge(self,chat_snapshot())
        start_chat(self,bridge,peer,'slow:demora')
        bridge.cancelChat();request=respond(bridge,peer,chat_snapshot(partial='parc'))
        self.assertEqual((request['op'],request['capability']),('capability_cancel','llm_engine.chat'))
        self.assertEqual(bridge.chatResult,'Cancelamento enviado')
        bridge.refresh();respond(bridge,peer,chat_snapshot(result=chat_result(ok=False,error='cancelled',partial='parc')))
        self.assertEqual(bridge.chatState,'cancelled');self.assertEqual(bridge.chatMessages[-1],{'role':'assistant','text':'parc','state':'cancelled'})
        self.assertEqual(bridge.chatResult,'')
    def test_chat_errors_show_http_status_or_code_once(self):
        bridge,peer=connect_bridge(self,chat_snapshot())
        start_chat(self,bridge,peer,'oi');bridge.refresh();respond(bridge,peer,chat_snapshot(result=chat_result(ok=False,error='http_error',extra={'http_status':429})))
        self.assertEqual((bridge.chatState,bridge.chatResult),('error','Erro HTTP 429'))
        bridge.sendChat('de novo');request=next_request(peer);answer(peer,request,chat_snapshot());settle(bridge)
        bridge.refresh();respond(bridge,peer,chat_snapshot(result=chat_result(ok=False,error='key_missing')))
        self.assertEqual((bridge.chatState,bridge.chatResult),('error',CODE_MESSAGES['key_missing']))
        self.assertEqual([m['role'] for m in bridge.chatMessages],['user','user'])
    def test_chat_double_send_is_refused_without_second_request(self):
        bridge,peer=connect_bridge(self,chat_snapshot())
        bridge.sendChat('primeiro');bridge.sendChat('segundo')
        self.assertEqual(bridge.chatResult,'Aguarde a resposta anterior')
        request=next_request(peer);self.assertEqual(request['input']['messages'][-1]['content'],'primeiro')
        wait_idle();self.assertFalse(peer.canReadLine())
        answer(peer,request,chat_snapshot());settle(bridge)
        bridge.sendChat('terceiro');self.assertEqual(bridge.chatResult,'Aguarde a resposta anterior')
        wait_idle();self.assertFalse(peer.canReadLine())
    def test_chat_busy_core_answer_keeps_input_and_history(self):
        bridge,peer=connect_bridge(self,chat_snapshot());sent=[];bridge.chatSent.connect(sent.append)
        bridge.sendChat('oi');respond(bridge,peer,chat_snapshot(),'busy')
        self.assertEqual((bridge.chatResult,bridge.chatState,bridge.chatMessages,sent),(CODE_MESSAGES['busy'],'idle',[],[]))
        bridge.sendChat('oi');request=next_request(peer);answer(peer,request,chat_snapshot());settle(bridge)
        self.assertEqual(sent,['oi'])
    def test_chat_history_is_sent_with_completed_turns_only(self):
        bridge,peer=connect_bridge(self,chat_snapshot())
        start_chat(self,bridge,peer,'primeira');bridge.refresh();respond(bridge,peer,chat_snapshot(result=chat_result('resposta um')))
        bridge.sendChat('segunda');request=next_request(peer)
        self.assertEqual(request['input']['messages'],[{'role':'user','content':'primeira'},{'role':'assistant','content':'resposta um'},{'role':'user','content':'segunda'}])
        answer(peer,request,chat_snapshot());settle(bridge)
    def test_tool_decide_payload_dedupe_and_refusals(self):
        bridge,peer=connect_bridge(self,chat_snapshot(tools=[tool_item('tool_1_1'),tool_item('tool_1_2',tool='mute',args={})]))
        self.assertEqual([p['proposal_id'] for p in bridge.toolProposals],['tool_1_1','tool_1_2'])
        bridge.decideTool('tool_1_1','authorize');bridge.decideTool('tool_1_1','authorize')
        request=next_request(peer)
        self.assertEqual(request,{'version':1,'request_id':request['request_id'],'op':'tool_decide','proposal_id':'tool_1_1','decision':'authorize'})
        wait_idle();self.assertFalse(peer.canReadLine())
        answer(peer,request,chat_snapshot(tools=[tool_item('tool_1_1',state='authorized'),tool_item('tool_1_2',tool='mute',args={})]));settle(bridge)
        self.assertEqual(bridge.toolResult,'Decisão enviada ao Core')
        bridge.decideTool('tool_1_1','deny');self.assertEqual(bridge.toolResult,CODE_MESSAGES['already_decided'])
        bridge.decideTool('ghost','deny');self.assertEqual(bridge.toolResult,CODE_MESSAGES['unknown_proposal'])
        bridge.decideTool('tool_1_2','maybe');wait_idle();self.assertFalse(peer.canReadLine())
        bridge.decideTool('tool_1_2','deny');request=next_request(peer)
        self.assertEqual((request['op'],request['proposal_id'],request['decision']),('tool_decide','tool_1_2','deny'))
        answer(peer,request,chat_snapshot(tools=[tool_item('tool_1_2',tool='mute',state='denied',args={},reason='user_denied')]));settle(bridge)
        self.assertEqual(bridge.toolProposals[0]['reason'],'user_denied')
    def test_set_api_key_payload_double_click_and_no_key_retained(self):
        bridge,peer=connect_bridge(self,chat_snapshot())
        bridge.setApiKey('openrouter',FAKE_KEY);bridge.setApiKey('openrouter',FAKE_KEY)
        request=next_request(peer)
        self.assertEqual(request,{'version':1,'request_id':request['request_id'],'op':'secret_set','provider':'openrouter','key':FAKE_KEY})
        wait_idle();self.assertFalse(peer.canReadLine())
        answer(peer,request,chat_snapshot(llm=llm_state(revision=2,config=LLM_CONFIG,secrets={'openrouter':True,'opencode':False,'google':True,'custom':False})));settle(bridge)
        self.assertEqual(bridge.llmResult,'Chave salva pelo Core');self.assertTrue(bridge.llmSecretsConfigured['openrouter'])
        assert_no_key(self,bridge)
    def test_set_api_key_refusals_never_reach_the_core(self):
        bridge,peer=connect_bridge(self,chat_snapshot())
        bridge.setApiKey('openrouter','short');self.assertEqual(bridge.llmResult,CODE_MESSAGES['invalid_secret'])
        bridge.setApiKey('llamacpp',FAKE_KEY);self.assertEqual(bridge.llmResult,CODE_MESSAGES['invalid_provider'])
        bridge.setApiKey('openrouter','with space key1');self.assertEqual(bridge.llmResult,CODE_MESSAGES['invalid_secret'])
        wait_idle();self.assertFalse(peer.canReadLine());assert_no_key(self,bridge)
    def test_clear_api_key_payload_and_core_answer(self):
        bridge,peer=connect_bridge(self,chat_snapshot())
        bridge.clearApiKey('google');request=next_request(peer)
        self.assertEqual(request,{'version':1,'request_id':request['request_id'],'op':'secret_clear','provider':'google'})
        answer(peer,request,chat_snapshot(llm=llm_state(revision=2,config=LLM_CONFIG,secrets={'openrouter':False,'opencode':False,'google':False,'custom':False})));settle(bridge)
        self.assertEqual(bridge.llmResult,'Chave removida pelo Core');self.assertFalse(bridge.llmSecretsConfigured['google'])
    def test_saved_consent_is_visible_to_the_dialog_and_saved_back_unchanged(self):
        bridge,peer=connect_bridge(self,chat_snapshot(llm=llm_state(revision=5,config=LLM_CONFIG)))
        revision=bridge.llmRevision;self.assertEqual((revision,bridge.llmConfig.get('cloud_consent') is True),('5',True))
        # Dialog passes the saved consent it shows; a model-only change must send the same value back, never False.
        bridge.configureLlm('google','gemini-2.5-flash','',bridge.llmConfig.get('cloud_consent') is True,revision)
        request=next_request(peer)
        self.assertEqual((request['revision'],request['model'],request['cloud_consent']),(5,'gemini-2.5-flash',True))
        answer(peer,request,chat_snapshot(llm=llm_state(revision=6,config={**LLM_CONFIG,'model':'gemini-2.5-flash'})));settle(bridge)
        self.assertEqual((bridge.llmResult,bridge.llmConfig['cloud_consent']),('Configuração salva pelo Core',True))
    def test_no_saved_config_means_no_consent_for_the_dialog(self):
        bridge,peer=connect_bridge(self,chat_snapshot(llm=llm_state(revision=1)))
        self.assertEqual(bridge.llmConfig,{});self.assertFalse(bridge.llmConfig.get('cloud_consent') is True)
        bridge.configureLlm('openrouter','m-1','',False,bridge.llmRevision);self.assertEqual(next_request(peer)['cloud_consent'],False)
    def test_motor_llm_dialog_reads_consent_from_core_and_never_auto_enables(self):
        # Source contract for the QML dialog (no Qt needed): open-time state comes from llm.config, the box is only changed by its own click.
        qml=(Path(__file__).resolve().parents[1]/'app'/'Main.qml').read_text(encoding='utf-8')
        start=qml.index('id: llmDialog');section=qml[start:qml.index('id: reviewDialog',start)]
        self.assertIn('consentBox.checked = core.llmConfig.cloud_consent === true',section)
        self.assertIn('window.llmRevisionCaptured = core.llmRevision',section)
        self.assertIn('core.configureLlm(providerBox.currentValue, modelField.text, providerBox.currentValue === "custom" ? urlField.text : "", consentBox.checked, window.llmRevisionCaptured)',section)
        self.assertIn('Mensagens serão enviadas ao provedor escolhido na nuvem',section)
        self.assertIn('keyField.text = ""',section)
        self.assertNotIn('consentBox.checked = true',qml);self.assertNotIn('consentBox.checked = false',qml)
    def test_configure_llm_payload_consent_default_and_revision_bound(self):
        bridge,peer=connect_bridge(self,chat_snapshot(llm=llm_state(revision=3)))
        self.assertEqual(bridge.llmRevision,'3')
        bridge.configureLlm('custom','local-model','https://example.test/v1',False,bridge.llmRevision)
        request=next_request(peer)
        self.assertEqual(request,{'version':1,'request_id':request['request_id'],'op':'llm_configure','revision':3,'provider':'custom','model':'local-model','custom_url':'https://example.test/v1','cloud_consent':False})
        answer(peer,request,chat_snapshot(llm=llm_state(revision=4,config={'provider':'custom','model':'local-model','custom_url':'https://example.test/v1','cloud_consent':False})));settle(bridge)
        self.assertEqual(bridge.llmResult,'Configuração salva pelo Core')
        bridge.configureLlm('google','gemini-3.5-flash-lite','',True,'3');self.assertEqual(bridge.llmResult,CODE_MESSAGES['stale_llm_revision'])
        bridge.configureLlm('openrouter','bad model!','',False,'4');self.assertEqual(bridge.llmResult,CODE_MESSAGES['invalid_config'])
        bridge.configureLlm('google','m','https://x.test',False,'4');self.assertEqual(bridge.llmResult,CODE_MESSAGES['invalid_config'])
        bridge.configureLlm('custom','m','http://example.test',False,'4');self.assertEqual(bridge.llmResult,CODE_MESSAGES['invalid_config'])
        wait_idle();self.assertFalse(peer.canReadLine())
        bridge.configureLlm('openrouter','m-1','',False,'4');request=next_request(peer)
        self.assertEqual((request['provider'],request['custom_url'],request['cloud_consent']),('openrouter',None,False))
        answer(peer,request,chat_snapshot(llm=llm_state(revision=4)),'stale_llm_revision');settle(bridge)
        self.assertEqual(bridge.llmResult,CODE_MESSAGES['stale_llm_revision'])
    def test_going_offline_mid_chat_finishes_it_and_keeps_no_inflight_state(self):
        bridge,peer=connect_bridge(self,chat_snapshot(tools=[tool_item()]))
        start_chat(self,bridge,peer,'oi');self.assertEqual(bridge.chatState,'waiting')
        bridge._offline()
        self.assertEqual((bridge.chatState,bridge.chatResult,bridge.toolProposals),('error','Core indisponível; resposta interrompida',[]))
        self.assertEqual(bridge.chatMessages,[{'role':'user','text':'oi','state':'done'}])
        self.assertIsNone(bridge.chat_inflight);self.assertFalse(bridge.chatAvailable)
    def test_chat_panel_and_motor_dialog_follow_qml_rules(self):
        env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_QUICK_CONTROLS_STYLE':'Basic'}
        proc=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--qml-chat-child'],env=env,capture_output=True,text=True,timeout=240)
        self.assertEqual(proc.returncode,0,(proc.stdout+proc.stderr)[-4000:])
    def test_code_messages_cover_c1_codes_in_portuguese(self):
        for code in ('key_missing','provider_not_configured','cloud_not_authorized','permission_denied','http_error','timeout','response_too_large','network_unavailable','unknown_tool','invalid_args','proposal_expired','already_decided','invalid_config','stale_llm_revision','invalid_secret','secrets_unavailable'):
            with self.subTest(code=code):
                self.assertIn(code,CODE_MESSAGES);self.assertNotIn('Core recusou',CODE_MESSAGES[code])
        self.assertEqual(set(CHAT_STATE_LABELS),{'idle','waiting','streaming','done','error','cancelled'})
def qml_chat_child():
    from PySide6.QtGui import QAccessible,QGuiApplication
    from PySide6.QtCore import QCoreApplication,QEvent,QMetaObject,QObject
    from PySide6.QtTest import QTest
    from main import create
    app=QGuiApplication(sys.argv[:1]);QAccessible.setActive(True);checks=[]
    def check(name,value):
        if not value:raise AssertionError(name)
        checks.append(name)
    with tempfile.TemporaryDirectory(prefix='gideon-qml-chat-') as td:
        bridge,engine=create(app,td);window=engine.rootObjects()[0]
        bridge.retry.stop();bridge.online=True
        try:return _qml_chat_checks(bridge,window,check,checks)
        finally:
            for w in engine.rootObjects():w.close();w.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            del engine;del bridge
def _qml_chat_checks(bridge,window,check,checks):
    from PySide6.QtGui import QAccessible
    from PySide6.QtCore import QMetaObject,QObject,Qt
    from PySide6.QtTest import QTest
    def items():
        stack=[window.contentItem()];found=[]
        while stack:
            current=stack.pop();found.append(current);stack.extend(current.childItems())
        return found
    def find(name):
        item=next((i for i in items() if i.objectName()==name),None)
        if item is None:raise AssertionError('missing '+name)
        return item
    def push(snap):bridge._apply(validate_snapshot(copy.deepcopy(snap),'r',0));QTest.qWait(30)
    window.setProperty('page',7);QTest.qWait(50)
    check('no plugin: chat panel hidden',not find('chatPanel').property('visible'))
    check('no plugin: unavailable explanation shown',find('chatUnavailable').property('visible'))
    check('no plugin: nav item Conversa hidden',not find('nav7').property('visible'))
    tools=[tool_item('tool_1_1'),tool_item('tool_1_2',tool='mute',args={},state='executed',result='Silenciado')]
    push(chat_snapshot(tools=tools,llm=llm_state(config=LLM_CONFIG)))
    check('running chat plugin: panel visible',find('chatPanel').property('visible'))
    check('running chat plugin: nav item Conversa visible',find('nav7').property('visible'))
    check('running chat plugin: unavailable explanation hidden',not find('chatUnavailable').property('visible'))
    check('pending proposal offers Negar',find('deny_tool_1_1').property('visible') and find('authorize_tool_1_1').property('visible'))
    check('executed proposal offers no decision buttons',not find('deny_tool_1_2').property('visible') and not find('authorize_tool_1_2').property('visible'))
    names=[]
    for obj in items():
        if obj.objectName().startswith(('deny_','authorize_')):names.append(QAccessible.queryAccessibleInterface(obj).text(QAccessible.Text.Name))
    check('decision names are unique per proposal',names and len(set(names))==len(names) and all(names))
    dialog=window.findChild(QObject,'llmDialog');QMetaObject.invokeMethod(dialog,'open');QTest.qWait(50)
    check('consent reflects saved Core consent on open',find('llmConsent').property('checked') is True)
    push(chat_snapshot(llm=llm_state(revision=1)));dialog.close();QMetaObject.invokeMethod(dialog,'open');QTest.qWait(50)
    check('no saved config opens with consent unchecked',find('llmConsent').property('checked') is False)
    push(chat_snapshot(llm=llm_state(revision=1,config=LLM_CONFIG)));dialog.close();QMetaObject.invokeMethod(dialog,'open');QTest.qWait(50)
    check('reopened dialog shows saved consent checked again',find('llmConsent').property('checked') is True)
    check('key status reflects the configured flag for the selected provider',find('llmKeyStatus').property('text')=='Chave configurada')
    find('llmKey').setProperty('text',FAKE_KEY);QTest.qWait(20)
    check('key field masked on screen',find('llmKey').property('displayText')!=FAKE_KEY and find('llmKey').property('text')==FAKE_KEY)
    check('save key enabled when field filled',find('saveKeyButton').property('enabled'))
    QMetaObject.invokeMethod(find('saveKeyButton'),'click');QTest.qWait(30)
    check('key field cleared right after save',find('llmKey').property('text')=='')
    check('bridge keeps no key after save',not any(FAKE_KEY in t for v in vars(bridge).values() for t in secret_strings(v)))
    push(chat_snapshot(llm=llm_state(revision=2,config=LLM_CONFIG)))
    find('llmModel').setProperty('text','bad model');QTest.qWait(10)
    check('model field refuses spaces',not find('llmModel').property('acceptableInput'))
    find('llmModel').setProperty('text','gemini-3.5-flash-lite');QTest.qWait(10)
    check('model field accepts Core charset',find('llmModel').property('acceptableInput'))
    check('custom URL field disabled unless Personalizado',not find('llmUrl').property('enabled'))
    chat_input=find('chatInput');chat_input.setProperty('text','oi');QTest.qWait(20)
    check('send enabled for trimmed text',find('chatSend').property('enabled'))
    chat_input.setProperty('text','   ');QTest.qWait(20)
    check('blank text cannot be sent',not find('chatSend').property('enabled'))
    print(f'qml chat checks ok: {len(checks)}');return 0
def qml_child():
    from PySide6.QtGui import QAccessible,QGuiApplication
    from PySide6.QtCore import QCoreApplication,QEvent,QMetaObject,QObject,Qt
    from PySide6.QtTest import QTest
    from main import create
    app=QGuiApplication(sys.argv[:1]);QAccessible.setActive(True);checks=[]
    def check(name,value):
        if not value:raise AssertionError(name)
        checks.append(name)
    with tempfile.TemporaryDirectory(prefix='gideon-qml-') as td:
        bridge,engine=create(app,td);window=engine.rootObjects()[0]
        # No Core here: stop the reconnect timer so its offline path cannot wipe the injected snapshot.
        bridge.retry.stop();bridge.online=True
        try:return _qml_checks(bridge,window,check,checks)
        finally:
            for w in engine.rootObjects():w.close();w.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            del engine;del bridge
def _qml_checks(bridge,window,check,checks):
    from PySide6.QtGui import QAccessible
    from PySide6.QtCore import QMetaObject,QObject,Qt
    from PySide6.QtTest import QTest
    def items():
        # Popups (dialogs) live under the window's overlay, so walk childItems like test_ui_offscreen.py; findChild misses delegates.
        stack=[window.contentItem()];found=[]
        while stack:
            current=stack.pop();found.append(current);stack.extend(current.childItems())
        return found
    def find(name):
        item=next((i for i in items() if i.objectName()==name),None)
        if item is None:raise AssertionError('missing '+name)
        return item
    counts=Counter();bridge.pluginsChanged.connect(lambda:counts.update(['plugins']));bridge.sessionChanged.connect(lambda:counts.update(['session']))
    check('QML minimum is 480x520',window.property('minimumWidth')==480 and window.property('minimumHeight')==520)
    def push(snap):bridge._apply(validate_snapshot(copy.deepcopy(snap),'r',0))
    first=dual_snapshot();push(first);QTest.qWait(50)
    QMetaObject.invokeMethod(window.findChild(QObject,'hubDialog'),'open');QTest.qWait(50)
    field=find('capabilityInput_dummy_echo');check('running plugin input enabled',field.property('enabled'))
    field.setProperty('gideonMarker',7)
    counts.clear();session={**copy.deepcopy(first),'sequence':2,'state':'capturing'};push(session);QTest.qWait(30)
    check('unrelated session update keeps the plugin delegate',find('capabilityInput_dummy_echo').property('gideonMarker')==7)
    check('session update does not notify the plugin list',counts['plugins']==0 and counts['session']==1)
    field=find('capabilityInput_dummy_echo');field.forceActiveFocus();QTest.qWait(20)
    for ch in 'draft':QTest.keyClick(window,getattr(Qt.Key,'Key_'+ch.upper()))
    QTest.qWait(20);check('typed draft reaches the field',find('capabilityInput_dummy_echo').property('text')=='draft')
    third=copy.deepcopy(session);next(i for i in third['plugins']['items'] if i['plugin_id']=='dummy_echo')['restarts']=1
    push(third);QTest.qWait(50)
    check('plugin update rebuilds delegate but restores the draft',find('capabilityInput_dummy_echo').property('text')=='draft' and find('capabilityInput_dummy_echo').property('gideonMarker') is None)
    names={}
    for obj in items():
        if re.match(r'^(enable|disable|revoke|invoke|cancelCapability|review|install|rollback|remove)_',obj.objectName()):
            name=QAccessible.queryAccessibleInterface(obj).text(QAccessible.Text.Name);names.setdefault(name,0);names[name]+=1
    check('action controls have names',bool(names) and all(names))
    check('action control names are unique across plugins',all(v==1 for v in names.values()))
    check('per-plugin names include the plugin id',{'Ativar dummy_echo','Ativar second_echo'}<=set(names))
    fourth=copy.deepcopy(third);fourth['preferences']['visual_feedback']=False;push(fourth);QTest.qWait(30)
    check('preference change resyncs the visual control',find('visualPagePreference').property('checked') is False)
    print(f'qml checks ok: {len(checks)}');return 0
if __name__=='__main__':
    if QML_CHILD:sys.exit(qml_child())
    if QML_CHAT_CHILD:sys.exit(qml_chat_child())
    unittest.main()
