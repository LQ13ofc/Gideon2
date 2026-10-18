#!/usr/bin/env python3
"""Real-Core snapshot contract: every snapshot the Core emits must pass app/bridge.validate_snapshot.

Starts target/release/gideon-base in private temp roots (private HOME/XDG, virtual input, sandboxed
commands, /usr/bin/python3 plugins, loopback fake LLM provider from tests/fixtures) and drives it through
fresh, verified Hub, approved, staged, installed, enabled and running plugin, configured LLM, streamed
and pending tool proposals, http_error capability result, quarantined Hub (corrupt ledger), staged
payload error, and crash-orphan sweep states. Every snapshot returned is validated with the bridge
validator; a single rejected snapshot fails the test (that is the UI going "Core offline").

Run with the UI venv (stdlib unittest; bridge imports PySide6 only for QObject):
  QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_snapshot_contract.py
"""
import hashlib, json, os, shutil, signal, socket, subprocess, sys, tempfile, time, unittest
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'app'))
sys.path.insert(0, str(BASE / 'scripts'))
from bridge import PERCEPTION_OUTPUTS, perception_input_problem, validate_snapshot  # noqa: E402
from hub_import import upload as stage_upload  # noqa: E402

BIN = BASE / 'target/release/gideon-base'
CATALOG = BASE / 'tests/fixtures/hub-c1.json'
C4_CATALOG = BASE / 'tests/fixtures/hub-c4.json'
PLUGIN_SRC = BASE / 'tests/fixtures/llm_engine.py'
FAKE_SRC = BASE / 'tests/fixtures/fake_llm_server.py'
GITHUB_SRC = BASE / 'tests/fixtures/connections/github_server.py'  # S5 E1 fake GitHub (loopback, stdlib)
GOOGLE_SRC = BASE / 'tests/fixtures/connections/google_server.py'  # S5 E2.2 fake Google (loopback, stdlib)
HA_SRC = BASE / 'tests/fixtures/connections/homeassistant_server.py'  # S5 E2.3 fake Home Assistant (loopback, stdlib)
HA_TOKEN = 'ha-contract-token-0123456789'  # test-only long-lived token for the fake; never a real credential
PYTHON = '/usr/bin/python3'
PLUGIN = 'llm_engine'
CAP = 'llm_engine.chat'
KEY = 'sk-fake-0123456789abcdef'  # test-only key for the loopback fake provider
CLEAN_ENV = {'PATH': '/usr/bin:/bin'}
PACK = BASE / 'target/base-pack-dev.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Core:
    """One real Core process over core.sock with snapshot validation on every answer."""

    def __init__(self, root, td):
        self.root, self.td, self.proc, self.counter = Path(root), Path(td), None, 0
        self.last_sequence = 0
        self.validated = []
        self.extra = []  # extra Core flags (C3 agent run: --home, --agent-synthetic)
        self.catalog = CATALOG  # C4 contract: a merged catalog of llm_engine and the six C4 plugins

    def args(self):
        args = [str(BIN), '--root', str(self.root), '--virtual-input', '--commands-sandbox',
                '--plugin-python', PYTHON, '--net-allow-loopback',
                '--hub-catalog', str(self.catalog), sha(self.catalog)]
        # Base pack needs its wake replay and TTS profile (same inputs as the C0/C1 gates); they add the
        # pack, speech and transcript sections to what the contract covers.
        manifest = BASE / 'target/a3-assets/replay-manifest.json'
        index = next(i for i, r in enumerate(json.loads(manifest.read_text())['fixtures'])
                     if r['id'] == 'wake-hey-brave__bf_emma__clean')
        args += ['--base-pack', str(PACK), '--tts-virtual', str(BASE / 'target/tts-venv/bin/python'),
                 str(BASE / 'target/a5-assets/manifest.json'), '--wake-replay',
                 str(BASE / 'target/a1-venv/bin/python'), str(manifest), str(index)]
        return args + self.extra

    def env(self):
        home = str(self.td)
        return {'PATH': '/usr/bin:/bin', 'HOME': home, 'XDG_CONFIG_HOME': home, 'XDG_DATA_HOME': home,
                'XDG_CACHE_HOME': home, 'XDG_RUNTIME_DIR': home}

    def start(self):
        # A new Core boot restarts the sequence; the bridge also starts a new sequence per connection.
        self.last_sequence = 0
        self.proc = subprocess.Popen(self.args(), env=self.env(), stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        until = time.monotonic() + 8
        while True:
            try:
                with socket.socket(socket.AF_UNIX) as probe:
                    probe.connect(str(self.root / 'core.sock'))
                break
            except (FileNotFoundError, ConnectionRefusedError):
                pass
            if self.proc.poll() is not None:
                raise RuntimeError(self.proc.stderr.read().decode())
            if time.monotonic() > until:
                raise TimeoutError('core startup')
            time.sleep(0.01)
        return self

    def stop(self):
        if self.proc is None:
            return
        self.proc.terminate()
        rc = self.proc.wait(timeout=10)
        self.proc.stderr.close()
        self.proc = None
        if rc != 0:
            raise RuntimeError(f'Core exit {rc}')

    def kill(self):
        self.proc.send_signal(signal.SIGKILL)
        self.proc.wait(timeout=5)
        self.proc.stderr.close()
        self.proc = None

    def req(self, op='snapshot', **fields):
        self.counter += 1
        ident = f'contract_{self.counter}'
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(10)
            s.connect(str(self.root / 'core.sock'))
            s.sendall((json.dumps({'version': 1, 'request_id': ident, 'op': op, **fields}) + '\n').encode())
            data = b''
            while not data.endswith(b'\n'):
                chunk = s.recv(65536)
                if not chunk:
                    raise RuntimeError('Core disconnected')
                data += chunk
        return json.loads(data)

    def snap(self, label):
        """Snapshot through the same validator the bridge runs on every poll."""
        ident = f'contract_{self.counter + 1}'
        data = self.req('snapshot')
        try:
            validate_snapshot(data, ident, self.last_sequence)
        except Exception as error:  # the validator raises ValueError with a bare message; keep the label
            raise AssertionError(f'{label}: bridge rejected snapshot: {error}\n{json.dumps(data, indent=1)[:4000]}')
        self.last_sequence = data['sequence']
        self.validated.append(label)
        return data

    def wait(self, predicate, seconds, label):
        until = time.monotonic() + seconds
        while True:
            data = self.req('snapshot')
            if predicate(data):
                return data
            if time.monotonic() > until:
                raise TimeoutError(label)
            time.sleep(0.02)


def plugin_item(snapshot, plugin_id=PLUGIN):
    return next((i for i in snapshot['plugins']['items'] if i['plugin_id'] == plugin_id), None)


class SnapshotContract(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        if not BIN.exists():
            raise unittest.SkipTest('target/release/gideon-base missing; run cargo build --release')

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix='gideon-contract-')
        self.td = Path(self._td.name)
        self.root = self.td / 'core'
        self.core = Core(self.root, self.td)
        self.fake = None
        self.github = None

    def tearDown(self):
        if self.core is not None:
            if self.core.proc is not None:
                self.core.proc.kill()
                self.core.proc.wait(timeout=5)
        if self.fake is not None:
            self.fake.kill()
            self.fake.wait(timeout=5)
            self.fake.stdin.close()
            self.fake.stdout.close()
        if self.github is not None:
            self.github.kill()
            self.github.wait(timeout=5)
            self.github.stdout.close()
        self._td.cleanup()

    def start_github(self):
        return self.start_loopback_fake(GITHUB_SRC)

    def start_google(self):
        return self.start_loopback_fake(GOOGLE_SRC)

    def start_loopback_fake(self, source):
        self.github = subprocess.Popen([PYTHON, '-I', str(source), '--port', '0'], stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=CLEAN_ENV, cwd='/')
        line = self.github.stdout.readline().decode('ascii').strip()
        self.assertTrue(line.startswith('PORT='), line)
        return f'http://127.0.0.1:{int(line[len("PORT="):])}'

    def github_control(self, base, name, body):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request = urllib.request.Request(base + '/__control/' + name, data=json.dumps(body).encode(),
                                         headers={'Content-Type': 'application/json'}, method='POST')
        with opener.open(request, timeout=10) as reply:
            return json.loads(reply.read())

    def ok_op(self, op, **fields):
        """Core op with the single-slot `busy` retried for up to 20 s (what the bridge does per click)."""
        until = time.monotonic() + 20
        while True:
            reply = self.core.req(op, **fields)
            if reply.get('code') != 'busy' or time.monotonic() > until:
                return reply
            time.sleep(0.2)

    def start_fake(self):
        self.fake = subprocess.Popen([PYTHON, '-I', str(FAKE_SRC), '--port', '0'], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=CLEAN_ENV, cwd='/')
        port = int(self.fake.stdout.readline())
        return f'http://127.0.0.1:{port}/v1'

    def approve_and_stage(self):
        hub = self.core.req()['hub']
        entry = next(e for e in hub['entries'] if e['plugin_id'] == PLUGIN)
        ack = self.core.req('hub_approve', revision=hub['approval_revision'], plugin_id=PLUGIN,
                            manifest_sha256=entry['manifest_sha256'], permissions=entry['permissions'],
                            publisher_unverified_ack=True)
        self.assertEqual(ack['code'], 'ok')
        stage_upload(str(self.root), PLUGIN, str(PLUGIN_SRC))
        return entry

    def install_and_enable(self):
        hub = self.core.req()['hub']
        entry = next(e for e in hub['entries'] if e['plugin_id'] == PLUGIN)
        install = self.core.req('hub_install', revision=hub['install_revision'], plugin_id=PLUGIN,
                                manifest_sha256=entry['manifest_sha256'])
        self.assertEqual(install['code'], 'ok')
        plugins_rev = self.core.req()['plugins']['revision']
        enable = self.core.req('plugin_enable', revision=plugins_rev, plugin_id=PLUGIN)
        self.assertEqual(enable['code'], 'ok')
        self.core.wait(lambda s: plugin_item(s) is not None and plugin_item(s)['state'] == 'running', 20,
                       'llm_engine running')

    def configure_llm(self, url):
        rev = self.core.req()['llm']['revision']
        cfg = self.core.req('llm_configure', revision=rev, provider='custom', model='fake/model-1',
                            custom_url=url, cloud_consent=True)
        self.assertEqual(cfg['code'], 'ok')
        self.assertEqual(self.core.req('secret_set', provider='custom', key=KEY)['code'], 'ok')

    def invoke(self, text, tools=False, deadline=10000):
        code = self.core.req('capability_invoke', capability=CAP, input={
            'messages': [{'role': 'user', 'content': text}], 'tools': tools, 'max_tokens': 64},
            deadline_ms=deadline)['code']
        self.assertEqual(code, 'ok')

    def test_fresh_hub_approved_staged_installed_running_and_llm(self):
        self.core.start()
        fresh = self.core.snap('fresh')
        self.assertEqual(fresh['hub']['status'], 'verified')
        self.assertEqual(fresh['hub']['orphans'], 0)
        self.assertNotIn('reason', fresh['hub'])
        self.approve_and_stage()
        staged = self.core.snap('approved and staged')
        entry = next(e for e in staged['hub']['entries'] if e['plugin_id'] == PLUGIN)
        self.assertTrue(entry['payload_staged'])
        self.install_and_enable()
        running = self.core.snap('enabled and running')
        self.assertEqual(plugin_item(running)['state'], 'running')
        self.assertEqual(running['hub']['installed'][0]['runtime'], 'running')
        url = self.start_fake()
        self.configure_llm(url)
        self.core.snap('llm configured')
        self.invoke('echo:hello contract')
        self.core.wait(lambda s: s.get('capability_result') is not None and s['capability_result'].get('ok'), 15,
                       'echo result')
        self.core.snap('capability result ok with partial')
        self.invoke('tool:open_app', tools=True)
        pending = self.core.wait(lambda s: any(p['state'] == 'pending' for p in s['tool_proposals']), 10,
                                 'pending proposal')
        self.core.snap('tool proposal pending')
        proposal = next(p for p in pending['tool_proposals'] if p['state'] == 'pending')
        self.assertEqual(self.core.req('tool_decide', proposal_id=proposal['proposal_id'], decision='deny')['code'], 'ok')
        self.core.snap('tool proposal denied')
        self.invoke('e503:x')
        failed = self.core.wait(lambda s: s.get('capability_result') is not None and not s['capability_result']['ok'],
                                15, 'http_error result')
        self.assertEqual(failed['capability_result']['error'], 'http_error')
        self.assertEqual(failed['capability_result']['http_status'], 503)
        self.core.snap('capability_result http_error with http_status')
        self.core.stop()

    def test_quarantined_hub_with_corrupt_ledger(self):
        self.core.start()
        self.approve_and_stage()
        self.core.snap('staged before corruption')
        self.core.stop()
        (self.root / 'hub-installed.json').write_bytes(b'{not json')
        self.core.start()
        quarantined = self.core.snap('quarantined hub (ledger_invalid)')
        self.assertEqual(quarantined['hub']['status'], 'quarantined')
        self.assertEqual(quarantined['hub']['reason'], 'ledger_invalid')
        self.core.stop()

    def test_quarantined_hub_with_missing_ledger(self):
        self.core.start()
        self.approve_and_stage()
        self.install_and_enable()
        self.core.stop()
        (self.root / 'hub-installed.json').unlink()
        self.core.start()
        missing = self.core.snap('quarantined hub (ledger_missing)')
        self.assertEqual(missing['hub']['reason'], 'ledger_missing')
        self.core.stop()

    def test_crash_orphan_sweep_and_staged_payload_error(self):
        self.core.start()
        hub = self.core.req()['hub']
        entry = next(e for e in hub['entries'] if e['plugin_id'] == PLUGIN)
        pending = self.root / ('.hub-' + entry['manifest_sha256'] + '.pending')
        approval = self.core.req('hub_approve', revision=hub['approval_revision'], plugin_id=PLUGIN,
                                 manifest_sha256=entry['manifest_sha256'], permissions=entry['permissions'],
                                 publisher_unverified_ack=True)
        self.assertEqual(approval['code'], 'ok')
        begun = self.core.req('hub_begin', revision=approval['hub']['approval_revision'], plugin_id=PLUGIN,
                              manifest_sha256=entry['manifest_sha256'])
        self.assertEqual(begun['code'], 'ok')
        self.core.snap('import in progress')
        self.core.kill()
        self.assertTrue(pending.exists())
        self.core.start()
        swept = self.core.snap('crash orphan swept')
        self.assertFalse(pending.exists())
        self.assertGreaterEqual(swept['hub']['orphans'], 1)
        stage_upload(str(self.root), PLUGIN, str(PLUGIN_SRC))
        self.assertTrue(self.core.snap('staged after orphan sweep')['hub']['entries'][0]['payload_staged'])
        self.core.stop()
        # Staged payload that no longer matches its hash: only that entry reports staged_error.
        payload = next(self.root.glob('hub-*.payload'))
        payload.write_bytes(b'x' * payload.stat().st_size)
        payload.chmod(0o600)
        self.core.start()
        broken = self.core.snap('staged payload error')
        self.assertEqual(broken['hub']['status'], 'verified')
        entry = next(e for e in broken['hub']['entries'] if e['plugin_id'] == PLUGIN)
        self.assertFalse(entry['payload_staged'])
        self.assertEqual(entry['staged_error'], 'staged_payload_invalid')
        self.core.stop()


    def test_agent_run_states_validate_against_real_core(self):
        # C3: the real agent snapshot must pass the bridge validator in every state it can show:
        # awaiting approval, done with a tool step, unknown tool step, aborted while awaiting a
        # destructive call (never executed in development). The scripted fake LLM is the llm_engine
        # plugin settings entry agent_script (read once per plugin process).
        home = self.td / 'home'
        (home / 'scripts').mkdir(parents=True)
        for name in ('command_worker.py', 'net_broker.py', 'wake_worker.py', 'stt_worker.py', 'tts_worker.py', 'pcm_fixture.py'):
            shutil.copy(BASE / 'scripts' / name, home / 'scripts' / name)
        self.core.extra = ['--home', str(home), '--agent-synthetic']
        script = {'steps': [
            {'text': '', 'tool_calls': [{'id': 'r1', 'name': 'synth_screen_read', 'arguments': {}}]},
            {'text': '', 'tool_calls': [{'id': 'i1', 'name': 'synth_counter_inc', 'arguments': {'epoch': 1}}]},
            {'text': 'Contador atualizado.', 'tool_calls': []},
            {'text': '', 'tool_calls': [{'id': 'x1', 'name': 'shell', 'arguments': {}}]},
            {'text': 'Nada feito.', 'tool_calls': []},
            {'text': '', 'tool_calls': [{'id': 'p1', 'name': 'synth_publish', 'arguments': {}}]},
        ]}
        self.core.start()
        settings = self.root / 'plugin-settings'
        settings.mkdir(mode=0o700)
        (settings / f'{PLUGIN}.json').write_text(json.dumps({'version': 1, 'data': {'agent_script': script}}))
        (settings / f'{PLUGIN}.json').chmod(0o600)
        self.approve_and_stage()
        self.install_and_enable()
        rev = self.core.req()['llm']['revision']
        port = self.start_fake_port()
        self.assertEqual(self.core.req('llm_configure', revision=rev, provider='local', model='gguf-local',
                                       custom_url=None, local_port=port, fallback=None, cloud_consent=False)['code'], 'ok')
        self.assertEqual(self.core.req('agent_start', goal='Incremente o contador')['code'], 'ok')
        waiting = self.core.wait(lambda s: s['agent'] is not None and s['agent']['state'] == 'awaiting_approval',
                                 20, 'awaiting approval')
        self.core.snap('agent awaiting approval')
        proposal = next(p for p in waiting['tool_proposals'] if p['state'] == 'pending')
        self.assertEqual(self.core.req('tool_decide', proposal_id=proposal['proposal_id'],
                                       decision='authorize')['code'], 'ok')
        done = self.core.wait(lambda s: s['agent'] is not None and s['agent']['state'] == 'done', 20, 'agent done')
        self.assertEqual(done['agent']['answer'], 'Contador atualizado.')
        self.core.snap('agent done with read and state-changing steps')
        self.assertEqual(self.core.req('agent_start', goal='Use uma ferramenta fora do registro')['code'], 'ok')
        self.core.wait(lambda s: s['agent'] is not None and s['agent']['state'] == 'done'
                       and s['agent']['goal_len'] == len('Use uma ferramenta fora do registro'), 20, 'second run')
        self.core.snap('agent done with unknown tool step')
        self.assertEqual(self.core.req('agent_start', goal='Publique')['code'], 'ok')
        held = self.core.wait(lambda s: s['agent'] is not None and s['agent']['state'] == 'awaiting_approval',
                              20, 'destructive held')
        self.core.snap('agent awaiting approval for destructive call')
        self.assertEqual(self.core.req('agent_abort', run_id=held['agent']['run_id'])['code'], 'ok')
        aborted = self.core.wait(lambda s: s['agent'] is not None and s['agent']['state'] == 'aborted', 10, 'aborted')
        self.assertEqual(aborted['agent']['error'], 'aborted')
        self.core.snap('agent aborted after destructive hold')
        self.core.stop()

    def start_fake_port(self):
        return int(self.start_fake().rsplit(':', 1)[1].split('/')[0])

    def test_c4_plugin_outputs_validate_against_real_core(self):
        # Every allowlisted C4 capability is invoked on the real Core (six plugins, synthetic world under a private
        # home) and each output must pass the bridge rule of its capability; the inputs pass perception_input_problem.
        home = self.td / 'home'
        home.mkdir()
        catalog = self.td / 'catalog-c4.json'
        c1 = json.loads(CATALOG.read_text(encoding='utf-8'))
        c4 = json.loads(C4_CATALOG.read_text(encoding='utf-8'))
        catalog.write_text(json.dumps({'version': c4['version'], 'repository': c4['repository'],
                                       'plugins': c1['plugins'] + c4['plugins']}), encoding='utf-8')
        self.core.catalog = catalog
        self.core.extra = ['--agent-synthetic', '--home', str(home)]
        self.core.start()
        C4_PLUGINS = ['screen_observe', 'computer_control', 'audio_advanced', 'mic_advanced', 'camera_gesture',
                      'display_manipulate']
        for pid in C4_PLUGINS:
            hub = self.core.req()['hub']
            entry = next(e for e in hub['entries'] if e['plugin_id'] == pid)
            ack = self.core.req('hub_approve', revision=hub['approval_revision'], plugin_id=pid,
                                manifest_sha256=entry['manifest_sha256'], permissions=entry['permissions'],
                                publisher_unverified_ack=True)
            self.assertEqual(ack['code'], 'ok', pid)
            stage_upload(str(self.root), pid, str(BASE / 'tests/fixtures/c4' / f'{pid}.py'))
            hub = self.core.req()['hub']
            install = self.core.req('hub_install', revision=hub['install_revision'], plugin_id=pid,
                                    manifest_sha256=entry['manifest_sha256'])
            self.assertEqual(install['code'], 'ok', pid)
            enable = self.core.req('plugin_enable', revision=self.core.req()['plugins']['revision'], plugin_id=pid)
            self.assertEqual(enable['code'], 'ok', pid)
            self.core.wait(lambda s, p=pid: plugin_item(s, p) is not None and plugin_item(s, p)['state'] == 'running',
                           20, f'{pid} running')
        calls = [
            ('screen_observe.status', {}), ('screen_observe.capture', {}),
            ('computer_control.status', {}), ('computer_control.tree', {}),
            ('computer_control.act', {'kind': 'click', 'epoch': 1, 'element': 'apply'}),
            ('computer_control.act', {'kind': 'focus', 'epoch': 2, 'element': 'field'}),
            ('computer_control.act', {'kind': 'type', 'epoch': 3, 'text': 'ola'}),
            ('computer_control.act', {'kind': 'key', 'epoch': 4, 'key': 'enter'}),
            ('audio_advanced.state', {}),
            ('audio_advanced.act', {'kind': 'route', 'route': 'headphones'}),
            ('audio_advanced.act', {'kind': 'app_volume', 'app': 'player', 'volume': 80}),
            ('audio_advanced.act', {'kind': 'eq', 'preset': 'music'}),
            ('audio_advanced.act', {'kind': 'denoise', 'enabled': True}),
            ('mic_advanced.state', {}), ('mic_advanced.configure', {'gain': 70, 'filter': 'voice'}),
            ('mic_advanced.monitor', {'enabled': True}), ('mic_advanced.record', {'action': 'start'}),
            ('mic_advanced.record', {'action': 'stop'}),
            ('camera_gesture.state', {}), ('camera_gesture.optin', {'enabled': True}),
            ('camera_gesture.capture', {}), ('camera_gesture.gestures', {}),
            ('camera_gesture.optin', {'enabled': False}),
            ('display_manipulate.status', {}),
        ]
        covered = set()
        for cap, inp in calls:
            self.assertIsNone(perception_input_problem(cap, json.dumps(inp)), (cap, inp))
            reply = self.core.req('capability_invoke', capability=cap, input=inp, deadline_ms=5000)
            self.assertEqual(reply['code'], 'ok', (cap, reply))
            self.core.wait(lambda s, c=cap: s.get('capability_result') is not None
                           and s['capability_result']['capability'] == c, 15, f'result {cap}')
            snap = self.core.snap(f'after {cap}')
            result = snap['capability_result']
            self.assertTrue(result['ok'], (cap, result))
            self.assertTrue(PERCEPTION_OUTPUTS[cap](result['output']), (cap, result['output']))
            covered.add(cap)
        self.assertEqual(covered, set(PERCEPTION_OUTPUTS), 'every allowlisted C4 capability was checked')
        # Negative controls: the rules refuse a near miss (extra key, wrong backend, missing focus flag).
        good = dict(result['output'])
        self.assertFalse(PERCEPTION_OUTPUTS['display_manipulate.status'](dict(good, extra=1)))
        self.assertFalse(PERCEPTION_OUTPUTS['display_manipulate.status']({'supported': True}))
        tree = self.core.req('capability_invoke', capability='computer_control.tree', input={}, deadline_ms=5000)
        self.assertEqual(tree['code'], 'ok')
        self.core.wait(lambda s: s.get('capability_result') is not None
                       and s['capability_result']['capability'] == 'computer_control.tree', 15, 'tree result')
        tree_out = self.core.req()['capability_result']['output']
        self.assertTrue(PERCEPTION_OUTPUTS['computer_control.tree'](tree_out))
        bad_tree = json.loads(json.dumps(tree_out))
        del bad_tree['elements'][0]['focused']
        self.assertFalse(PERCEPTION_OUTPUTS['computer_control.tree'](bad_tree))
        self.core.stop()

    def test_wake_replay_voice_session_validates_every_snapshot(self):
        # The replay starts at boot: capture, transcript, command receipt and speech (sink, PCM hash) all appear.
        self.core.start()
        deadline = time.monotonic() + 60
        while True:
            data = self.core.snap('voice session')
            done = data['wake_status'] == 'replay_finished' and data['state'] == 'idle' and data['command'] is not None
            if done:
                break
            self.assertLess(time.monotonic(), deadline, 'voice replay did not finish')
            time.sleep(0.01)
        self.assertEqual(data['speech_status'], 'completed')
        self.assertEqual(data['speech']['sink'], 'virtual')
        self.assertEqual(data['capture']['reason'], 'capture_completed')
        self.assertEqual(data['transcript']['source'], 'voice')
        self.assertTrue(data['command']['receipt']['verified'])
        self.core.stop()

    def test_skill_lifecycle_snapshots_validate_against_real_core(self):
        # S4 (docs/S4.md D2, D4): every snapshot of a skill lifecycle on the real Core must pass the bridge validator,
        # the skills block and the import preview included. Synthetic registry tools only (no plugin), private home.
        home = self.td / 'home'
        home.mkdir()
        self.core.extra = ['--agent-synthetic', '--home', str(home)]
        self.core.start()
        skill = 'skill_contract_rw'
        manifest = {'schema_version': 1, 'id': skill, 'name': 'Skill de contrato', 'version': '1.0.0',
                    'publisher': {'id': 'gideon-test', 'name': 'Gideon test'},
                    'description': 'Skill sintetica do teste de contrato', 'license': 'TEST-ONLY',
                    'min_runtime': '0.1.0', 'triggers': [], 'inputs': {},
                    'outputs': {'epoch': {'type': 'int'}, 'text': {'type': 'string'}},
                    'dependency_capabilities': ['tool:synth_screen_read', 'tool:synth_set_text'],
                    'permissions_required': [], 'prerequisites': [],
                    'attestations': [{'kind': 'test', 'text': 'synthetic test only, never shipped'}],
                    'steps': [
                        {'id': 'read', 'call': 'tool:synth_screen_read', 'args': {},
                         'save': {'epoch': 'epoch', 'text': 'text'}},
                        {'id': 'write', 'call': 'tool:synth_set_text',
                         'args': {'epoch': '${steps.read.epoch}', 'text': 'contrato'}}]}

        def rev():
            return self.core.req()['skills']['revision']

        def ok(reply):
            self.assertEqual(reply['code'], 'ok', reply)

        self.core.snap('skills empty')
        ok(self.core.req('skill_save_draft', manifest=manifest))
        self.core.snap('skill draft saved')
        ok(self.core.req('skill_dry_run', id=skill, skill_version='1.0.0', inputs={}))
        self.core.snap('skill tested by dry run')
        ok(self.core.req('skill_approve', id=skill, skill_version='1.0.0', revision=rev()))
        self.core.snap('skill approved')
        ok(self.core.req('skill_enable', id=skill, revision=rev()))
        self.core.snap('skill enabled')
        ok(self.core.req('skill_run', id=skill, inputs={}))
        waiting = self.core.wait(lambda s: s['skills']['run'] is not None
                                 and s['skills']['run']['state'] == 'awaiting_approval', 20, 'skill step awaiting')
        self.core.snap('skill run awaiting approval of a state-changing step')
        ok(self.core.req('skill_decide', run_id=waiting['skills']['run']['run_id'],
                         step=waiting['skills']['run']['step'], decision='authorize'))
        self.core.wait(lambda s: s['skills']['run'] is None, 20, 'skill run finished')
        self.core.snap('skill run finished')
        self.assertEqual(self.core.req()['skills']['history'][-1]['state'], 'done')
        ok(self.core.req('skill_export', id=skill, skill_version='1.0.0'))
        package = home / 'skill-exports' / f'{skill}-1.0.0.gskill'
        self.assertTrue(package.exists())
        self.core.snap('skill exported')
        ok(self.core.req('skill_remove', id=skill, revision=rev()))
        self.core.snap('skill removed')
        imports = home / 'skill-imports'
        imports.mkdir()
        (imports / 'contract.gskill').write_bytes(package.read_bytes())
        ok(self.core.req('skill_import', name='contract'))
        preview = self.core.snap('import preview')['skills']['import']
        self.assertTrue(preview['unverified'])
        self.assertEqual(preview['findings'], [])
        ok(self.core.req('skill_import_confirm', name='contract', revision=rev()))
        self.core.snap('import confirmed as draft')
        tampered = json.loads(package.read_bytes())
        tampered['manifest']['description'] = 'Descricao trocada depois da exportacao'
        (imports / 'tampered.gskill').write_text(json.dumps(tampered), encoding='utf-8')
        ok(self.core.req('skill_import', name='tampered'))
        finding = self.core.snap('import preview with hash_mismatch finding')['skills']['import']
        # The confirmed import is still in the ledger, so the same id is also a duplicate (both findings are real).
        # Two hash checks fail (the manifest digest and the package digest), so the codes are a set, not a list.
        self.assertEqual({f['code'] for f in finding['findings']},
                         {'skill_invalid:duplicate_id', 'skill_invalid:hash_mismatch'})
        self.assertTrue(finding['duplicate'])
        self.core.stop()

    def test_connections_snapshots_validate_against_real_core(self):
        # S5 E1 (docs/S5.md, "Snapshot connections"): every connections state the Core emits must pass the bridge
        # validator, the connection proposals included, against the real Core and the S5 fake GitHub.
        base = self.start_github()
        self.core.extra = ['--connections-fake', f'github={base}']
        self.core.start()
        c = self.core
        c.snap('connections: nothing added yet')
        self.assertEqual(self.ok_op('connection_add', provider='github', label='contrato')['code'], 'ok')
        cid = c.snap('connection added (disconnected)')['connections']['items'][0]['id']
        self.assertEqual(self.ok_op('connection_connect', id=cid)['code'], 'ok')
        c.wait(lambda s: any(i['id'] == cid and i.get('user_code') for i in s['connections']['items']), 15,
               'device code shown')
        pending = c.snap('connecting: user_code and pending scopes')
        item = next(i for i in pending['connections']['items'] if i['id'] == cid)
        self.assertEqual(set(item['pending_scopes']), {'repo:read', 'issues:write', 'pulls:write'})
        self.github_control(base, 'approve', {'user_code': item['user_code'], 'scopes': item['pending_scopes']})
        until = time.monotonic() + 20
        while self.ok_op('connection_consent', id=cid, scopes=['repo:read', 'issues:write'])['code'] != 'ok':
            self.assertLess(time.monotonic(), until, 'consent accepted after the device approval')
            time.sleep(0.2)
        c.wait(lambda s: next(i for i in s['connections']['items'] if i['id'] == cid)['status'] == 'connected',
               20, 'connected')
        connected = c.snap('connected with the consented scopes')
        granted = next(i for i in connected['connections']['items'] if i['id'] == cid)['granted_scopes']
        self.assertEqual(set(granted), {'repo:read', 'issues:write'})
        self.assertFalse(connected['connections']['storage_error'])

        self.assertEqual(self.ok_op('connection_call', id=cid, operation='repo.get',
                                    args={'repo': 'demo/private-repo'})['code'], 'ok')
        c.wait(lambda s: (s['connections'].get('last_call') or {}).get('outcome') == 'ok', 20, 'read finished')
        c.snap('read call finished (last_call ok)')

        code = self.ok_op('connection_call', id=cid, operation='issues.create',
                          args={'repo': 'demo/private-repo', 'title': 'contrato'})['code']
        self.assertEqual(code, 'pending_approval')
        write_pid = c.snap('write proposal pending')['connections']['last_call']['proposal_id']
        code = self.ok_op('connection_call', id=cid, operation='pulls.comment',
                          args={'repo': 'demo/private-repo', 'number': 1, 'body': 'contrato'})['code']
        self.assertEqual(code, 'scope_not_granted')  # pulls:write was not consented: no proposal, no request
        self.assertEqual(self.ok_op('tool_decide', proposal_id=write_pid, decision='authorize')['code'], 'ok')
        c.wait(lambda s: any(p['proposal_id'] == write_pid and p['state'] == 'executed'
                             for p in s['tool_proposals']), 20, 'write executed')
        done = c.snap('write proposal executed with projected result')
        proposal = next(p for p in done['tool_proposals'] if p['proposal_id'] == write_pid)
        self.assertEqual(proposal['kind'], 'connection')
        self.assertEqual(proposal['tool'], 'conn:github.issues.create')
        self.assertEqual(sorted(json.loads(proposal['result'])), ['number', 'public', 'state', 'title', 'url'])

        self.assertEqual(self.ok_op('connection_disconnect', id=cid)['code'], 'ok')
        c.snap('disconnected')
        self.assertEqual(self.ok_op('connection_remove', id=cid)['code'], 'ok')
        c.snap('removed')
        self.assertGreaterEqual(len(c.validated), 9, c.validated)  # nine connection states, every one validated
        self.assertTrue(any('proposal' in label for label in c.validated), c.validated)
        c.stop()

    def test_google_connections_snapshots_validate_against_real_core(self):
        # S5 E2.2 (docs/S5.md, "E2.2 google"): every google connections state passes the bridge validator, the
        # public, destructive and write proposals included, against the real Core and the Google fake.
        base = self.start_google()
        self.core.extra = ['--connections-fake', f'google={base}']
        self.core.start()
        c = self.core
        c.snap('google: nothing added yet')
        self.assertEqual(self.ok_op('connection_add', provider='google', label='contrato google')['code'], 'ok')
        cid = c.snap('google account added')['connections']['items'][0]['id']
        self.assertEqual(self.ok_op('connection_connect', id=cid)['code'], 'ok')
        c.wait(lambda s: any(i['id'] == cid and i.get('user_code') for i in s['connections']['items']), 15,
               'google device code shown')
        pending = c.snap('google connecting: user_code and seven pending scopes')
        item = next(i for i in pending['connections']['items'] if i['id'] == cid)
        self.assertEqual(len(item['pending_scopes']), 7)
        self.github_control(base, 'approve', {'user_code': item['user_code'], 'scopes': item['pending_scopes']})
        consent = ['gmail.read', 'gmail.send', 'gmail.delete', 'calendar.write']
        until = time.monotonic() + 20
        while self.ok_op('connection_consent', id=cid, scopes=consent)['code'] != 'ok':
            self.assertLess(time.monotonic(), until, 'google consent accepted after the device approval')
            time.sleep(0.2)
        c.wait(lambda s: next(i for i in s['connections']['items'] if i['id'] == cid)['status'] == 'connected',
               20, 'google connected')
        connected = c.snap('google connected with four consented scopes')
        granted = next(i for i in connected['connections']['items'] if i['id'] == cid)['granted_scopes']
        self.assertEqual(set(granted), set(consent))

        self.assertEqual(self.ok_op('connection_call', id=cid, operation='gmail.messages.list', args={})['code'], 'ok')
        c.wait(lambda s: (s['connections'].get('last_call') or {}).get('outcome') == 'ok', 20, 'list finished')
        c.snap('google list finished (last_call ok, no body in any state)')

        self.assertEqual(self.ok_op('connection_call', id=cid, operation='gmail.send',
                                    args={'to': 'bob@example.test', 'subject': 'contrato', 'body': 'corpo'})['code'],
                         'pending_approval')
        send_pid = c.snap('google public send proposal pending')['connections']['last_call']['proposal_id']
        self.assertEqual(self.ok_op('tool_decide', proposal_id=send_pid, decision='authorize')['code'],
                         'public_disabled')
        refused = c.snap('public send refused without the switch (still pending)')
        self.assertEqual(next(p for p in refused['tool_proposals'] if p['proposal_id'] == send_pid)['state'],
                         'pending')
        self.assertEqual(self.ok_op('tool_decide', proposal_id=send_pid, decision='deny')['code'], 'ok')

        self.assertEqual(self.ok_op('connection_call', id=cid, operation='gmail.messages.delete',
                                    args={'id': 'm1'})['code'], 'pending_approval')
        del_pid = c.snap('google destructive delete proposal pending')['connections']['last_call']['proposal_id']
        self.assertEqual(self.ok_op('tool_decide', proposal_id=del_pid, decision='deny')['code'], 'ok')

        self.assertEqual(self.ok_op('connection_call', id=cid, operation='calendar.events.create', args={
            'title': 'contrato', 'start': '2026-10-20T09:00:00Z', 'end': '2026-10-20T10:00:00Z'})['code'],
            'pending_approval')
        write_pid = c.snap('google write proposal pending')['connections']['last_call']['proposal_id']
        self.assertEqual(self.ok_op('tool_decide', proposal_id=write_pid, decision='authorize')['code'], 'ok')
        c.wait(lambda s: any(p['proposal_id'] == write_pid and p['state'] == 'executed'
                             for p in s['tool_proposals']), 20, 'google write executed')
        done = c.snap('google write proposal executed with projected result')
        proposal = next(p for p in done['tool_proposals'] if p['proposal_id'] == write_pid)
        self.assertEqual(proposal['tool'], 'conn:google.calendar.events.create')
        self.assertEqual(sorted(json.loads(proposal['result'])), ['end', 'id', 'start', 'title'])

        self.assertEqual(self.ok_op('connection_disconnect', id=cid)['code'], 'ok')
        c.snap('google disconnected')
        self.assertEqual(self.ok_op('connection_remove', id=cid)['code'], 'ok')
        c.snap('google removed')
        self.assertGreaterEqual(len(c.validated), 9, c.validated)
        c.stop()

    def test_homeassistant_snapshots_validate_against_real_core(self):
        # S5 E2.3 (docs/S5.md, "E2.3 homeassistant"): every homeassistant state passes the bridge validator, the
        # token never appears in any snapshot, and write and destructive service proposals validate.
        base = self.start_loopback_fake(HA_SRC)
        self.github_control(base, 'set_token', {'token': HA_TOKEN})
        self.core.extra = ['--connections-fake', f'homeassistant={base}']
        self.core.start()
        c = self.core
        c.snap('homeassistant: nothing added yet')
        self.assertEqual(self.ok_op('connection_add', provider='homeassistant', label='contrato casa')['code'], 'ok')
        cid = c.snap('homeassistant account added')['connections']['items'][0]['id']
        self.assertEqual(self.ok_op('connection_connect', id=cid)['code'], 'ok')
        pending = c.snap('homeassistant connecting: three pending scopes, no user_code')
        item = next(i for i in pending['connections']['items'] if i['id'] == cid)
        self.assertEqual(len(item['pending_scopes']), 3)
        self.assertNotIn('user_code', item)
        self.assertEqual(self.ok_op('connection_consent', id=cid, scopes=['states.read', 'services.call'])['code'],
                         'ok')
        self.assertEqual(self.ok_op('connection_set_token', id=cid, token=HA_TOKEN)['code'], 'ok')
        c.wait(lambda s: next(i for i in s['connections']['items'] if i['id'] == cid)['status'] == 'connected',
               20, 'homeassistant connected')
        connected = c.snap('homeassistant connected with the consented scopes')
        item = next(i for i in connected['connections']['items'] if i['id'] == cid)
        self.assertEqual(item['account_ref'], 'demo-home')
        self.assertEqual(set(item['granted_scopes']), {'states.read', 'services.call'})
        self.assertNotIn(HA_TOKEN, json.dumps(connected))

        self.assertEqual(self.ok_op('connection_call', id=cid, operation='states.list', args={})['code'], 'ok')
        c.wait(lambda s: (s['connections'].get('last_call') or {}).get('outcome') == 'ok', 20, 'states listed')
        c.snap('states list finished (entity, state and friendly name only)')

        self.assertEqual(self.ok_op('connection_call', id=cid, operation='service.call', args={
            'domain': 'light', 'service': 'turn_on', 'entity_id': 'light.kitchen', 'brightness': 100})['code'],
            'pending_approval')
        write_pid = c.snap('service write proposal pending')['connections']['last_call']['proposal_id']
        self.assertEqual(self.ok_op('tool_decide', proposal_id=write_pid, decision='authorize')['code'], 'ok')
        c.wait(lambda s: any(p['proposal_id'] == write_pid and p['state'] == 'executed'
                             for p in s['tool_proposals']), 20, 'service write executed')
        done = c.snap('service write executed with the projected states')
        proposal = next(p for p in done['tool_proposals'] if p['proposal_id'] == write_pid)
        self.assertEqual(proposal['tool'], 'conn:homeassistant.service.call')
        self.assertEqual(sorted(json.loads(proposal['result'])[0]), ['attributes', 'entity_id', 'state'])
        self.assertNotIn(HA_TOKEN, json.dumps(done))

        strong = self.ok_op('connection_add', provider='homeassistant', label='contrato perigoso')
        self.assertEqual(strong['code'], 'ok')
        sid = next(i['id'] for i in c.snap('second homeassistant account added')['connections']['items']
                   if i['label'] == 'contrato perigoso')
        self.assertEqual(self.ok_op('connection_connect', id=sid)['code'], 'ok')
        self.assertEqual(self.ok_op('connection_consent', id=sid,
                                    scopes=['states.read', 'services.call', 'services.dangerous'])['code'], 'ok')
        self.assertEqual(self.ok_op('connection_set_token', id=sid, token=HA_TOKEN)['code'], 'ok')
        c.wait(lambda s: next(i for i in s['connections']['items'] if i['id'] == sid)['status'] == 'connected',
               20, 'second homeassistant connected')
        self.assertEqual(self.ok_op('connection_call', id=sid, operation='service.call', args={
            'domain': 'lock', 'service': 'unlock', 'entity_id': 'lock.front_door'})['code'], 'pending_approval')
        lock_pid = c.snap('destructive unlock proposal pending')['connections']['last_call']['proposal_id']
        lock = next(p for p in c.snap('unlock card')['tool_proposals'] if p['proposal_id'] == lock_pid)
        self.assertEqual((lock['kind'], lock['risk']), ('connection', 'destructive'))
        self.assertEqual(self.ok_op('tool_decide', proposal_id=lock_pid, decision='deny')['code'], 'ok')

        for account in (cid, sid):
            self.assertEqual(self.ok_op('connection_disconnect', id=account)['code'], 'ok')
            self.assertEqual(self.ok_op('connection_remove', id=account)['code'], 'ok')
        self.assertNotIn(HA_TOKEN, json.dumps(c.snap('homeassistant removed')))
        self.assertGreaterEqual(len(c.validated), 9, c.validated)
        self.assertTrue(any('proposal' in label for label in c.validated), c.validated)
        c.stop()

if __name__ == '__main__':
    unittest.main(verbosity=2)
