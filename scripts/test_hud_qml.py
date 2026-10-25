#!/usr/bin/env python3
"""WP-3 (HUD-01, HUD-02): the nine HUD states of app/pages/InicioHoje.qml drawn by app/components/Orb.qml.

Two kinds of evidence, both through the real QML shell (app/Main.qml via main.create) and the real bridge validator:

  HudContract  a real Core answers one snapshot (the idle snapshot is read from it); each state is then a copy of that
               snapshot with the Core fields of the state changed, checked by validate_snapshot and applied with
               bridge._apply. Nothing is faked on the QML side: the page only reads the bridge.
  HudLive      a real Core (release binary, virtual PCM, replay wake, the same arguments as verify_c0_plugins.py) answers
               the voice path: wake replay, transcription, speech and a command, and a command that fails. Every mode the
               page shows during those turns is recorded and screenshotted.

Run (offscreen, needs target/release/gideon-base and target/ui-venv):
  QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_hud_qml.py
Screenshots: target/evidence/wp3/*.png
"""
import copy
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['QT_QUICK_CONTROLS_STYLE'] = 'Basic'  # the app ships its own look (app/main.py)
os.environ['GIDEON_UI_NO_ONBOARDING'] = '1'     # the first-run guide would cover the page (uisettings.py)
os.environ['XDG_CONFIG_HOME'] = tempfile.mkdtemp(prefix='gideon-xdg-hud-')  # uisettings never writes the real ~/.config
sys.path.insert(0, str(BASE / 'app'))
sys.path.insert(0, str(BASE / 'scripts'))

from PySide6.QtCore import QObject, QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from bridge import AGENT_MAX_STEPS, AGENT_TOTAL_TOKENS, validate_snapshot  # noqa: E402
from main import create  # noqa: E402

BIN = BASE / 'target/release/gideon-base'
HUB = BASE / 'tests/fixtures/hub-c1.json'
TTS_PY = BASE / 'target/tts-venv/bin/python'
WAKE_PY = BASE / 'target/a1-venv/bin/python'
EVIDENCE = BASE / 'target/evidence/wp3'
APP = QGuiApplication.instance() or QGuiApplication(sys.argv)


def runtime_dir():
    """The Core socket path must stay under 108 bytes: the private runtime directory is the short place."""
    base = os.environ.get('XDG_RUNTIME_DIR') or '/tmp'
    return base


def sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def raw_request(root, op, **fields):
    """One request to the real Core over its socket, the same wire the bridge uses (newline-terminated JSON)."""
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(10)
        s.connect(str(Path(root) / 'core.sock'))
        s.sendall((json.dumps({'version': 1, 'request_id': 'hud_' + op, 'op': op, **fields}) + '\n').encode())
        data = b''
        while not data.endswith(b'\n'):
            chunk = s.recv(65536)
            if not chunk:
                raise RuntimeError('Core disconnected')
            data += chunk
    return json.loads(data)


class Core:
    """A release Core started by this test in a private root; stopped at the end of the class."""

    def __init__(self, root, args=()):
        self.root = Path(root)
        self.args = [str(BIN), '--root', str(self.root), '--commands-sandbox', '--hub-catalog', str(HUB), sha(HUB), *args]
        self.log = open(self.root.parent / (self.root.name + '.log'), 'w')
        self.proc = subprocess.Popen(self.args, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if (self.root / 'core.sock').exists():
                try:
                    raw_request(self.root, 'snapshot')
                    return
                except OSError:
                    pass
            time.sleep(0.1)
        self.stop()
        raise RuntimeError('the Core did not answer in 20 s')

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.log.close()


def new_root(prefix):
    return Path(tempfile.mkdtemp(prefix=prefix, dir=runtime_dir()))


def pump(ms=0):
    """Lets the QML bindings and the bridge's timers run."""
    until = time.monotonic() + ms / 1000
    while True:
        APP.processEvents()
        QTest.qWait(10)
        if time.monotonic() >= until:
            return


def wait_until(condition, seconds=15, what='condition'):
    until = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > until:
            raise TimeoutError('timed out waiting for ' + what)
        pump(20)


def find(window, name):
    item = window.findChild(QObject, name)
    if item is None:
        raise AssertionError('missing objectName ' + name)
    return item


def freeze(bridge):
    """A shell with no Core: no socket retries and no timeouts, so an injected snapshot is the snapshot until the test ends.
    Without this the bridge reconnects to the missing socket and its offline path empties the snapshot."""
    for timer in (bridge.retry, bridge.poll, bridge.timeout, bridge.restart_timer):
        timer.stop()
    for signal in (bridge.socket.errorOccurred, bridge.socket.disconnected, bridge.socket.connected):
        try:
            signal.disconnect()
        except (RuntimeError, TypeError):
            pass
    bridge.socket.abort()


def send_when_quiet(bridge, text):
    """The Core takes text only with no session and no request in flight (bridge.textAvailable); the test waits for that."""
    wait_until(lambda: bridge.textAvailable and bridge.pending is None and bridge.state == 'idle' and not bridge.sessionId,
               60, 'a quiet Core for text')
    bridge.submitText(text)
    pump(100)


def find_text(window, name):
    return find(window, name).property('text')


def shot(window, name):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    pump(60)
    window.grabWindow().save(str(EVIDENCE / (name + '.png')))


class Shell:
    """Main.qml with the real bridge and ui settings, on the Hoje page."""

    def __init__(self, root):
        self.bridge, self.engine = create(APP, root)
        # The engine and the bridge must outlive the page: QML reads `core` on every binding re-evaluation.
        self.window = self.engine.rootObjects()[0]
        self.window.setProperty('width', 640)
        self.window.setProperty('height', 900)
        self.window.setProperty('pageId', 'hoje')
        pump(120)
        self.page = find(self.window, 'page_hoje')

    def close(self):
        for w in self.engine.rootObjects():
            w.close()
            w.deleteLater()
        pump(50)
        self.bridge.deleteLater()
        pump(50)


def hud_names(window):
    """The HUD as the user sees it: orb mode, phrase, the visible rows and the cancel button."""
    def visible(name):
        item = window.findChild(QObject, name)
        return item is not None and item.property('visible') is True
    def text(name):
        item = window.findChild(QObject, name)
        return item.property('text') if item is not None else None
    return {
        'mode': find(window, 'hudOrb').property('mode'),
        'phrase': text('heroPhrase'),
        'sub': text('heroSub'),
        'micBadge': visible('hojeMicBadge'),
        'transcript': visible('hudTranscript'),
        'tool': visible('hudTool'),
        'progress': visible('hudProgress'),
        'progressText': text('hudProgressText'),
        'receipt': text('hudReceipt') if visible('hudReceipt') else None,
        'cancel': visible('hudCancel'),
    }


def mutate_base(base, **changes):
    snap = copy.deepcopy(base)
    snap.update(request_id='r')
    for key, value in changes.items():
        snap[key] = value
    return snap


class HudContract(unittest.TestCase):
    """Each state is a Core-shaped snapshot checked by validate_snapshot and applied to the real shell."""

    @classmethod
    def setUpClass(cls):
        root = new_root('gw-hud-c-')
        core = Core(root)
        try:
            cls.base = raw_request(root, 'snapshot')
        finally:
            core.stop()
        cls.shell_root = new_root('gw-hud-s-')  # no Core here: the shell is offline until a snapshot is applied
        cls.shell = Shell(cls.shell_root)
        cls.bridge = cls.shell.bridge
        freeze(cls.bridge)
        pump(100)

    @classmethod
    def tearDownClass(cls):
        cls.shell.close()

    def apply(self, **changes):
        """Validates the Core-shaped snapshot exactly as the bridge does on the socket, then publishes it."""
        snap = validate_snapshot(mutate_base(self.base, **changes), 'r', 0)
        self.bridge.online = True
        self.bridge.changed.emit()
        self.bridge._apply(snap)
        pump(80)
        return hud_names(self.shell.window)

    def live(self):
        return {'enabled': True, 'input_state': 'capturing', 'output_state': 'idle', 'mic_active': True, 'restart_required': False,
                'level': {'rms_dbfs': -40.0, 'peak_dbfs': -30.0, 'floor_dbfs': -41.5, 'speech_active': False,
                                              'speech_ms': 0, 'speech_unmatched': False, 'frames': 200, 'last_frame_age_ms': 20,
                                              'clipping': False},
                'silence_warning': None}

    def session_id(self):
        return self.base['session_id'] or 7

    def test_idle_is_the_resting_state(self):
        h = self.apply()
        self.assertEqual(h['mode'], 'idle')
        self.assertEqual(h['phrase'], 'Pronto para ouvir')
        self.assertFalse(h['cancel'])
        self.assertFalse(h['micBadge'])
        self.assertIsNone(h['receipt'])
        shot(self.shell.window, '01-idle')

    def test_wake_detected_is_the_first_moment_of_a_session(self):
        live = self.live()
        live['last_detection'] = {'at_ms': int(time.time() * 1000), 'phrase_id': 'hey_gideon'}
        h = self.apply(state='capturing', session_id=self.session_id(), audio={**self.base['audio'], 'live': live},
                       transcript=None)
        self.assertEqual(h['mode'], 'wake')
        self.assertEqual(h['phrase'], 'Gideon ativado')
        self.assertTrue(h['cancel'])
        self.assertTrue(h['micBadge'], 'HUD-02: the microphone notice is visible text while the recorder is on')
        shot(self.shell.window, '02-wake-detected')

    def test_listening_once_the_wake_window_has_passed(self):
        live = self.live()
        live['last_detection'] = {'at_ms': int(time.time() * 1000) - 60000, 'phrase_id': 'hey_gideon'}
        h = self.apply(state='capturing', session_id=self.session_id(), audio={**self.base['audio'], 'live': live}, transcript=None)
        self.assertEqual(h['mode'], 'listening')
        self.assertEqual(h['phrase'], 'Ouvindo…')
        self.assertTrue(h['cancel'])
        shot(self.shell.window, '03-listening')

    def test_transcribing_shows_the_words_heard(self):
        h = self.apply(state='transcribing', session_id=self.session_id(), transcript=self.transcript('Abrir o navegador', final=False))
        self.assertEqual(h['mode'], 'transcribing')
        self.assertEqual(h['phrase'], 'Transcrevendo…')
        self.assertEqual(h['sub'], 'Processando o que você disse.')
        self.assertTrue(h['transcript'])
        self.assertEqual(find_text(self.shell.window, 'hudTranscript'), 'Você (parcial): Abrir o navegador')
        self.assertTrue(h['cancel'])
        shot(self.shell.window, '04-transcribing')

    def test_speaking_can_be_cut_short(self):
        h = self.apply(state='speaking', session_id=self.session_id(), speech_status='speaking', transcript=self.transcript('Abrir o navegador'))
        self.assertEqual(h['mode'], 'speaking')
        self.assertEqual(h['phrase'], 'Falando…')
        self.assertTrue(h['cancel'])
        shot(self.shell.window, '05-speaking')

    def test_acting_names_the_running_tool_and_the_progress_of_the_run(self):
        steps = [agent_chat_step(1), agent_tool_step(2, 'open_app', 'running')]
        h = self.apply(state='idle', agent=agent_run('waiting_tool', 2, steps))
        self.assertEqual(h['mode'], 'acting')
        self.assertEqual(h['phrase'], 'Executando…')
        self.assertTrue(h['tool'])
        self.assertEqual(find_text(self.shell.window, 'hudTool'), 'Ferramenta: open_app')
        self.assertTrue(h['progress'])
        self.assertEqual(h['progressText'], 'Passo 2 de %d' % AGENT_MAX_STEPS)
        self.assertTrue(h['cancel'])
        shot(self.shell.window, '06-acting')

    def test_thinking_while_the_agent_plans(self):
        h = self.apply(state='idle', agent=agent_run('thinking', 1, [agent_chat_step(1, 'running')]))
        self.assertEqual(h['mode'], 'thinking')
        self.assertEqual(h['phrase'], 'Pensando…')
        self.assertEqual(h['sub'], 'O agente planeja o próximo passo.')
        self.assertTrue(h['cancel'])
        shot(self.shell.window, '07-thinking')

    def test_awaiting_confirmation_names_the_tool_and_offers_no_approval_here(self):
        h = self.apply(state='idle', tool_proposals=[tool_item('tool_1_1', 'open_app', 'pending')])
        self.assertEqual(h['mode'], 'confirm')
        self.assertEqual(h['phrase'], 'Aguardando sua aprovação')
        self.assertEqual(h['sub'], 'Ferramenta open_app precisa da sua decisão.')
        self.assertFalse(h['cancel'], 'no agent run: nothing to cancel from here')
        shot(self.shell.window, '08-awaiting-confirmation')

    def test_error_shows_the_failed_command_as_a_failed_receipt(self):
        h = self.apply(state='idle', command=command_outcome(self.session_id(), 'app_not_installed'))
        self.assertEqual(h['mode'], 'error')
        self.assertEqual(h['phrase'], 'Erro')
        self.assertEqual(h['receipt'], 'Falhou')
        shot(self.shell.window, '09-error')

    def test_verified_success_is_a_receipt_on_the_resting_state(self):
        h = self.apply(state='idle', command=command_outcome(self.session_id(), 'ok', verified=True, result='Processo do app verificado'))
        self.assertEqual(h['mode'], 'idle')
        self.assertEqual(h['receipt'], 'Concluído · ' + self.bridge.result)
        self.assertTrue(self.bridge.resultVerified)

    def test_reduced_motion_keeps_every_state_still_and_says_the_same(self):
        ui = self.shell.engine.rootContext().contextProperty('ui')
        orb = find(self.shell.window, 'hudOrb')
        try:
            for setting in ('off', 'reduced'):
                ui.set('theme.animation', setting)
                pump(60)
                self.assertFalse(orb.property('fullMotion'), 'no loops under ' + setting)
                live = self.live()
                live['last_detection'] = {'at_ms': int(time.time() * 1000), 'phrase_id': 'hey_gideon'}
                h = self.apply(state='capturing', session_id=self.session_id(), audio={**self.base['audio'], 'live': live}, transcript=None)
                self.assertEqual((h['mode'], h['phrase']), ('wake', 'Gideon ativado'), setting)
                h = self.apply(state='idle', tool_proposals=[tool_item('tool_1_1', 'open_app', 'pending')])
                self.assertEqual((h['mode'], h['phrase']), ('confirm', 'Aguardando sua aprovação'), setting)
                shot(self.shell.window, 'reduced-' + setting + '-confirm')
            ui.set('theme.animation', 'normal')
            pump(60)
            self.assertTrue(orb.property('fullMotion'))
        finally:
            ui.set('theme.animation', 'normal')
            pump(60)

    def test_disconnected_and_safe_mode_are_said_in_words(self):
        self.bridge.online = False
        self.bridge.changed.emit()
        pump(40)
        h = hud_names(self.shell.window)
        self.assertEqual(h['phrase'], 'Core desconectado')
        self.assertEqual(h['mode'], 'idle')
        h = self.apply(state='idle', configuration_status='safe_mode', configuration_recovery_available=False)
        self.assertEqual(h['mode'], 'error')
        self.assertEqual(h['phrase'], 'Modo seguro')

    def transcript(self, raw, final=True):
        return {'source': 'voice', 'session_id': self.session_id(), 'revision': 1, 'audio_end_us': 1000, 'raw': raw,
                'normalized': raw.lower(), 'is_final': final, 'confidence': 0.9}


# ---- snapshot builders (field names and closed vocabularies from src/protocol.rs, src/agent.rs, src/tools.rs) ----

def agent_chat_step(n, state='done'):
    return {'n': n, 'invocation_id': n, 'kind': 'chat', 'state': state}


def agent_tool_step(n, tool, state):
    return {'n': n, 'invocation_id': n, 'kind': 'tool', 'tool': tool, 'risk': 'read', 'state': state}


def agent_run(state, step, steps):
    return {'run_id': 'run_1_7', 'state': state, 'goal_len': 12, 'step': step, 'max_steps': AGENT_MAX_STEPS,
            'started_ms_ago': 4000, 'elapsed_ms': 4000, 'max_run_ms': 120000, 'steps': steps,
            'budget': {'tokens_used': 10, 'tokens_max': AGENT_TOTAL_TOKENS}}


def tool_item(pid, tool, state):
    return {'proposal_id': pid, 'plugin_id': 'llm_engine', 'call_id': 'call_' + pid, 'tool': tool,
            'args': {'desktop_id': 'brave.desktop'}, 'state': state, 'reason': None, 'result': None}


def command_outcome(session_id, code, verified=False, result=''):
    receipt = None
    if code == 'ok':
        receipt = {'job': {'session_id': session_id, 'command': {'kind': 'open_app', 'desktop_id': 'brave.desktop'}},
                   'verified': verified, 'scope': 'app', 'result': result}
    return {'session_id': session_id, 'code': code, 'receipt': receipt}


# ---- the real Core, voice path ----

class HudLive(unittest.TestCase):
    """A real Core with the wake replay: every mode the page shows during the real voice turns."""

    shots = set()

    @classmethod
    def setUpClass(cls):
        cls.root = new_root('gw-hud-l-')
        manifest = BASE / 'target/a3-assets/replay-manifest.json'
        fixtures = json.loads(manifest.read_text())['fixtures']
        index = next(i for i, r in enumerate(fixtures) if r['id'] == 'wake-hey-brave__bf_emma__clean')
        args = ['--virtual-input', '--plugin-python', '/usr/bin/python3',
                '--base-pack', str(BASE / 'target/base-pack-dev.json'),
                '--tts-virtual', str(TTS_PY), str(BASE / 'target/a5-assets/manifest.json'),
                '--wake-replay', str(WAKE_PY), str(manifest), str(index)]
        cls.core = Core(cls.root, args)
        cls.shell = Shell(cls.root)
        cls.bridge = cls.shell.bridge
        cls.seen = []
        cls.recorder = QTimer()
        cls.recorder.timeout.connect(cls.record)
        cls.recorder.start(20)

    @classmethod
    def record(cls):
        window = cls.shell.window
        h = hud_names(window)
        key = (h['mode'], h['phrase'], h['receipt'])
        if not cls.seen or cls.seen[-1][1] != key:
            cls.seen.append((round(time.monotonic(), 2), key))
            if h['mode'] not in cls.shots:
                cls.shots.add(h['mode'])
                shot(window, 'live-' + h['mode'])

    @classmethod
    def tearDownClass(cls):
        cls.recorder.stop()
        cls.shell.close()
        cls.core.stop()

    def test_voice_turns_show_their_states_from_the_real_core(self):
        wait_until(lambda: self.bridge.connected and self.bridge.snapshot.get('wake_status') == 'replay_finished', 60, 'wake replay')
        wait_until(lambda: self.bridge.state == 'idle' and self.bridge.snapshot.get('text_input_available') is True, 30, 'idle with text input')
        send_when_quiet(self.bridge, 'Hey Gideon, open brave.')
        wait_until(lambda: self.bridge.resultVerified and self.bridge.state == 'idle' and not self.bridge.sessionId, 60, 'verified command receipt')
        send_when_quiet(self.bridge, 'Hey Gideon, open nosuchapp.')
        wait_until(lambda: self.bridge.result.startswith('Comando não entendido') and not self.bridge.resultVerified
                   and self.bridge.state == 'idle' and not self.bridge.sessionId, 60, 'failed receipt')
        pump(300)
        modes = [m for _, (m, _, _) in self.seen]
        receipts = [r for _, (_, _, r) in self.seen if r]
        print('\nLIVE modes seen (in order):', modes, flush=True)
        # Transcribing and acting last a few hundred milliseconds on the real Core and a 20 ms poll does not catch them
        # on every run; they are reported above and in docs/WP3.md, not asserted here.
        self.assertIn('idle', modes)
        self.assertTrue(any(m in ('wake', 'listening') for m in modes), modes)
        self.assertIn('speaking', modes, modes)
        self.assertIn('error', modes, modes)
        self.assertIn('Concluído · Processo do app verificado no sandbox: com.brave.Browser.desktop', receipts)
        self.assertIn('Falhou', receipts)


if __name__ == '__main__':
    unittest.main(verbosity=2)
