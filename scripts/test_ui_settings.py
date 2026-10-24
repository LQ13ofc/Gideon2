#!/usr/bin/env python3
"""App-side UI settings (app/uisettings.py): schema, validation, contrast, import/export, persistence. No GUI is opened."""
import json,os,stat,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import bridge as bridge_module
from uisettings import APP_KEYS,CORE_KEYS,PRESETS,SCHEMA,SPECS,UiSettings,contrast_ratio,parse_color,settings_path,validate_tokens

# docs/ui-spec/01-ajustes-minimalismo.md 3.1 (minimum set) plus the Core-backed entries of docs/ui-spec/40-configuracoes.md.
MINIMUM_KEYS={'theme.mode','theme.preset','theme.accent','theme.density','theme.radius','theme.fontSize','theme.fontFamily','theme.contrast','theme.animation','theme.translucency','theme.shadow','theme.titleWeight','theme.lineHeight','theme.colors','theme.orb','theme.orbSize','behavior.startTab','behavior.rememberWindow','behavior.tips','behavior.shortcuts','behavior.advanced','behavior.devMode','behavior.toastSeconds','behavior.confirmWrites','behavior.reduceMotionFollowSystem','voice.partials','voice.showConfidence','audio.cues'}
CORE_EXPECTED={'core.wakePhrase','core.sessionTimeoutMs','core.responseGain','core.audibleFeedback','core.visualFeedback'}


class FakeBridge:
    """Stands in for app/bridge.py: the same attribute and slot names, no socket."""
    def __init__(self):
        self.preferencesAvailable=True;self.outputVolume=100;self.visualFeedback=True;self.audibleFeedback=True;self.sessionTimeout=30000
        self.wakeChoices=[{'id':'hey_gideon','text':'Hey Gideon','qualification_label':'em desenvolvimento'},{'id':'okay_gideon','text':'Okay Gideon','qualification_label':'requer prova de conceito'}]
        self.snapshot={'preferences':{'wake_phrase':None},'base_pack':{'default_phrase':'hey_gideon'}};self.calls=[]
    def selectWake(self,ident):self.calls.append(('selectWake',ident))
    def saveFeedback(self,visual,volume):self.calls.append(('saveFeedback',visual,volume))
    def savePreferences(self,audible,timeout):self.calls.append(('savePreferences',audible,timeout))


class UiSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=self.tmp.name
        self.bridge=FakeBridge();self.ui=self.new()
        self.events=[];self.ui.changed.connect(self.events.append)

    def tearDown(self):
        self.tmp.cleanup()

    def new(self,bridge=None,root='/srv/gideon-core'):
        return UiSettings(self.bridge if bridge is None else bridge,root,config_home=self.home)

    def file(self):
        return settings_path('/srv/gideon-core',self.home)

    def test_defaults_and_empty_modifications(self):
        values=self.ui.values
        self.assertEqual(set(values),set(SPECS))
        for key in APP_KEYS:
            self.assertEqual(values[key],SPECS[key]['default'],key)
        self.assertEqual(values['core.responseGain'],100)
        self.assertEqual(list(self.ui.modifiedKeys),[])
        self.assertEqual(self.ui.revision,0)
        self.assertFalse(self.file().exists(),'defaults must not write a file')

    def test_set_and_reset_track_modified_keys(self):
        result=self.ui.set('theme.radius',12)
        self.assertEqual(result,{'ok':True,'value':12})
        self.assertEqual(list(self.ui.modifiedKeys),['theme.radius'])
        self.assertEqual(self.events,['theme.radius'])
        self.assertEqual(self.ui.set('theme.radius',12.0)['ok'],True)
        self.assertEqual(self.ui.reset('theme.radius'),{'ok':True,'value':8})
        self.assertEqual(list(self.ui.modifiedKeys),[])
        self.assertEqual(self.ui.resetAll(),{'ok':True,'count':0})

    def test_validation_refuses_bad_values_without_change(self):
        cases=[('behavior.tips',1,'verdadeiro'),('theme.radius',17,'limite'),('theme.radius',2.5,'inteiro'),('theme.preset','neon',None),('theme.accent','rosa',None),('theme.colors',{'nope':'#ffffff'},None),('theme.colors',{'bg':'azul'},None),('theme.fontSize',True,None),('theme.lineHeight',1.9,'limite')]
        for key,value,fragment in cases:
            with self.subTest(key=key,value=value):
                result=self.ui.set(key,value)
                self.assertFalse(result['ok'])
                self.assertEqual(result['code'],'invalid_value')
                self.assertTrue(result['error'])
                if fragment:self.assertIn(fragment,result['error'])
        self.assertEqual(list(self.ui.modifiedKeys),[])
        unknown=self.ui.set('theme.nothing',1)
        self.assertEqual((unknown['ok'],unknown['code']),(False,'unknown_key'))

    def test_contrast_autocorrection_reports_fix(self):
        result=self.ui.set('theme.accent','#303030')
        self.assertTrue(result['ok'])
        self.assertTrue(result.get('corrected'))
        fixes=[row for row in result['corrected'] if row['token']=='accent']
        self.assertEqual(fixes[0]['from'],'#303030')
        self.assertLess(fixes[0]['ratio_before'],3.0);self.assertGreaterEqual(fixes[-1]['ratio_after'],3.0)
        stored=result['value']
        self.assertEqual(stored,fixes[-1]['to'])
        self.assertGreaterEqual(contrast_ratio(stored,PRESETS['gideon-escuro']['tokens']['bg']),3.0)
        self.assertGreaterEqual(contrast_ratio(stored,PRESETS['gideon-escuro']['tokens']['surface']),3.0)

    def test_validate_theme_reports_uncorrectable_pairs(self):
        mid={role:'#808080' for role in PRESETS['gideon-escuro']['tokens']}
        report=validate_tokens(mid,high=True)
        self.assertFalse(report['ok'])
        self.assertTrue(report['errors'])
        self.assertTrue(self.ui.validateTheme(PRESETS['gideon-claro']['tokens'])['ok'])

    def test_presets_pass_contrast_and_derive_tokens(self):
        for name in PRESETS:
            with self.subTest(preset=name):
                tokens=self.ui.presetTokens(name)
                self.assertEqual(len(tokens),16)
                for role in ('hover','pressed','focus','tint'):self.assertIn(role,tokens)
                report=self.ui.validateTheme({k:v for k,v in tokens.items() if k in PRESETS[name]['tokens']})
                self.assertTrue(report['ok'],report['errors']);self.assertEqual(report['fixes'],[])
        self.assertEqual(self.ui.presetTokens('inexistente'),{})
        self.assertAlmostEqual(self.ui.contrast('#000000','#ffffff'),21.0,places=3)
        self.assertEqual(self.ui.contrast('nao-cor','#ffffff'),0.0)
        self.assertEqual(parse_color('#ABC'),'#aabbcc')

    def test_import_export_round_trip(self):
        self.ui.set('theme.radius',4);self.ui.set('theme.preset','gideon-claro');self.ui.set('behavior.tips',False)
        exported=json.loads(self.ui.exportJson())
        self.assertEqual(exported['schemaVersion'],1)
        self.assertEqual(set(exported['values']),{'theme.radius','theme.preset','behavior.tips'})
        self.assertFalse(any(key.startswith('core.') for key in exported['values']))
        self.ui.resetAll()
        report=self.ui.importJson(json.dumps(exported))
        self.assertEqual((report['ok'],report['applied'],report['rejected']),(True,3,[]))
        self.assertEqual(self.ui.values['theme.radius'],4);self.assertEqual(self.ui.values['theme.preset'],'gideon-claro')
        self.assertEqual(sorted(self.ui.modifiedKeys),sorted(exported['values']))

    def test_import_rejects_unknown_core_and_invalid_entries(self):
        text=json.dumps({'schemaVersion':1,'values':{'theme.radius':99,'theme.nothing':1,'core.responseGain':10,'behavior.tips':False}})
        report=self.ui.importJson(text)
        self.assertTrue(report['ok']);self.assertEqual(report['applied'],1)
        self.assertEqual({row['key'] for row in report['rejected']},{'theme.radius','theme.nothing','core.responseGain'})
        self.assertEqual(self.bridge.calls,[],'import must never write Core values')
        self.assertFalse(self.ui.importJson('{not json')['ok'])
        self.assertFalse(self.ui.importJson(json.dumps({'schemaVersion':9,'values':{}}))['ok'])

    def test_corrupt_file_recovers_to_defaults_with_backup(self):
        self.file().parent.mkdir(parents=True,exist_ok=True)
        self.file().write_text('{"schemaVersion": 1, "values": {"theme.radius":',encoding='utf-8')
        ui=self.new()
        self.assertEqual(ui.values['theme.radius'],8)
        self.assertEqual(list(ui.modifiedKeys),[])
        self.assertTrue(self.file().with_name(self.file().name+'.bad').exists())
        self.assertFalse(self.file().exists())

    def test_persistence_is_atomic_private_and_reloads(self):
        self.ui.set('theme.preset','escuro-frio');self.ui.set('audio.cues',False)
        path=self.file()
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode),0o600)
        self.assertEqual(stat.S_IMODE(os.stat(path.parent).st_mode),0o700)
        self.assertEqual([p.name for p in path.parent.iterdir()],[path.name],'no temp files left behind')
        data=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(data['schemaVersion'],1)
        reloaded=self.new()
        self.assertEqual(reloaded.values['theme.preset'],'escuro-frio');self.assertFalse(reloaded.values['audio.cues'])

    def test_no_secrets_and_no_core_values_on_disk(self):
        self.ui.set('theme.radius',3);self.ui.set('core.responseGain',50)
        stored=json.loads(self.file().read_text(encoding='utf-8'))['values']
        self.assertTrue(set(stored)<=set(APP_KEYS))
        for key in stored:
            self.assertNotRegex(key,r'(?i)secret|token|password|key|senha|chave')
        self.assertNotIn('core.responseGain',stored)

    def test_failed_write_keeps_previous_values(self):
        blocked=Path(self.home)/'blocked';blocked.write_text('x',encoding='utf-8')
        ui=UiSettings(self.bridge,'/srv/gideon-core',config_home=str(blocked))
        result=ui.set('theme.radius',5)
        self.assertEqual((result['ok'],result['code']),(False,'storage'))
        self.assertEqual(ui.values['theme.radius'],8);self.assertEqual(list(ui.modifiedKeys),[])

    def test_search_ranks_and_ignores_accents_and_case(self):
        self.assertEqual(self.ui.search('   '),[])
        self.assertEqual(self.ui.search('contraste')[0]['key'],'theme.contrast')
        self.assertEqual(self.ui.search('COR DE DESTAQUE')[0]['key'],'theme.accent')
        self.assertEqual(self.ui.search('sessao')[0]['key'],'core.sessionTimeoutMs')
        self.assertEqual(self.ui.search('Animações')[0]['key'],'theme.animation')
        keys=[row['key'] for row in self.ui.search('tema')]
        self.assertIn('theme.preset',keys)
        self.assertEqual(keys[0],'theme.preset')
        self.assertTrue(all({'key','label','section','subtab','score'} <= set(row) for row in self.ui.search('volume')))
        self.assertEqual(self.ui.search('zzzqqq'),[])

    def test_schema_is_complete(self):
        keys=[entry['key'] for entry in self.ui.schema]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertTrue(MINIMUM_KEYS<=set(keys))
        self.assertTrue(CORE_EXPECTED<=set(keys))
        for entry in self.ui.schema:
            with self.subTest(key=entry['key']):
                self.assertTrue(entry['label'].strip());self.assertTrue(entry['help'].strip())
                self.assertIn('default',entry);self.assertIn(entry['type'],('bool','enum','int','float','color','string','json'))
                self.assertIn(entry['level'],('basic','advanced','dev'));self.assertIn(entry['source'],('app','core'))
                self.assertIsInstance(entry['restart'],bool);self.assertIsInstance(entry['keywords'],list)
                if entry['type']=='enum':self.assertTrue(entry['options'])
                if entry['source']=='app':
                    self.assertEqual(self.ui.set(entry['key'],entry['default'])['ok'],True,entry['key'])
                    self.ui.reset(entry['key'])
        self.assertEqual(sorted(CORE_KEYS),sorted(CORE_EXPECTED))

    def test_core_backed_settings_go_through_bridge(self):
        self.assertEqual(self.ui.values['core.sessionTimeoutMs'],30000)
        wake=next(e for e in self.ui.schema if e['key']=='core.wakePhrase')
        self.assertEqual([o['value'] for o in wake['options']],['hey_gideon','okay_gideon'])
        self.assertEqual(self.ui.values['core.wakePhrase'],'hey_gideon')
        self.assertEqual(self.ui.set('core.responseGain',40),{'ok':True,'value':40,'pending':True})
        self.assertEqual(self.ui.set('core.visualFeedback',False)['pending'],True)
        self.assertEqual(self.ui.set('core.audibleFeedback',False)['pending'],True)
        self.assertEqual(self.ui.set('core.sessionTimeoutMs',45000)['pending'],True)
        self.assertEqual(self.ui.set('core.wakePhrase','hey_gideon')['pending'],False)
        self.assertEqual(self.ui.set('core.wakePhrase','okay_gideon')['pending'],True)
        self.assertEqual(self.bridge.calls,[('saveFeedback',True,40),('saveFeedback',False,100),('savePreferences',False,30000),('savePreferences',True,45000),('selectWake','okay_gideon')])
        self.assertFalse(self.ui.set('core.sessionTimeoutMs',10)['ok'])
        self.assertFalse(self.ui.set('core.wakePhrase','frase_livre')['ok'])
        self.assertEqual(self.ui.reset('core.responseGain')['code'],'core_readonly')
        self.assertEqual(list(self.ui.modifiedKeys),[])
        self.bridge.preferencesAvailable=False
        refused=self.ui.set('core.responseGain',10)
        self.assertEqual((refused['ok'],refused['code']),(False,'preferences_unavailable'))
        detached=UiSettings(None,'/srv/gideon-core',config_home=self.home)
        self.assertEqual(detached.set('core.visualFeedback',True)['code'],'preferences_unavailable')

    def test_core_change_notifies_listeners(self):
        notified=[]
        self.ui.valuesChanged.connect(lambda: notified.append(True))
        self.bridge.outputVolume=70
        self.ui._core_changed()
        self.assertEqual(self.ui.values['core.responseGain'],70)
        self.assertEqual(notified,[True])

    def test_advanced_switch_drives_code_detail_in_bridge(self):
        self.ui.set('behavior.advanced',True)
        self.assertEqual(bridge_module.code_message('zzz_unknown_code'),'Não foi possível concluir a operação. Código: zzz_unknown_code')
        self.ui.reset('behavior.advanced')
        self.assertEqual(bridge_module.code_message('zzz_unknown_code'),'Não foi possível concluir a operação.')

    def test_bridge_messages_are_portuguese_and_never_raw(self):
        for code in ('stale_preferences','invalid_preferences','preferences_storage_error','preferences_unavailable'):
            with self.subTest(code=code):
                self.assertIn(code,bridge_module.CODE_MESSAGES)
                self.assertFalse(bridge_module.code_message(code).startswith('Core recusou'))
                self.assertNotEqual(bridge_module.code_message(code),code)
        self.assertEqual(bridge_module.code_message(None),'Não foi possível concluir a operação.')
        self.assertNotIn('Core recusou',bridge_module.code_message('some_code'))


if __name__=='__main__':
    unittest.main()
