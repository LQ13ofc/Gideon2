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
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'app'))
sys.path.insert(0, str(BASE / 'scripts'))
from bridge import validate_snapshot  # noqa: E402
from hub_import import upload as stage_upload  # noqa: E402

BIN = BASE / 'target/release/gideon-base'
CATALOG = BASE / 'tests/fixtures/hub-c1.json'
PLUGIN_SRC = BASE / 'tests/fixtures/llm_engine.py'
FAKE_SRC = BASE / 'tests/fixtures/fake_llm_server.py'
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

    def args(self):
        args = [str(BIN), '--root', str(self.root), '--virtual-input', '--commands-sandbox',
                '--plugin-python', PYTHON, '--net-allow-loopback',
                '--hub-catalog', str(CATALOG), sha(CATALOG)]
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
        self._td.cleanup()

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

if __name__ == '__main__':
    unittest.main(verbosity=2)
