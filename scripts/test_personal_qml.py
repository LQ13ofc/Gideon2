#!/usr/bin/env python3
"""WP-10a: the five personal-data pages (Memoria, Almas, Habitos, Automacoes, Conversas) load offscreen and speak one
contract to the Core: `core.personal` (snapshot block), `core.personalReply` ({area, code, reply}),
`core.personalOp(area, json)`, `core.personalAvailable`, `core.historyRetention`, `core.skillsItems`, `core.codeMessage`.

The Core is a fake QObject with that contract. The tests check what the pages show from the snapshot, which requests
they send (versioned, with the current revision), and that refusals are shown. Nothing here touches the real Core.

Run (offscreen): QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_personal_qml.py
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['QT_QUICK_CONTROLS_STYLE'] = 'Basic'
os.environ['GIDEON_UI_NO_ONBOARDING'] = '1'
os.environ['XDG_CONFIG_HOME'] = tempfile.mkdtemp(prefix='gideon-xdg-personal-')

from PySide6.QtCore import QMetaObject, QObject, Property, Qt, Signal, Slot, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402

APP = QGuiApplication.instance() or QGuiApplication(sys.argv)

PAGES = {
    'memoria': 'Memoria.qml',
    'almas': 'Almas.qml',
    'habitos': 'Habitos.qml',
    'automacoes': 'Automacoes.qml',
    'conversas': 'Conversas.qml',
}

class FakeCore(QObject):
    """The Core side of the contract. Requests are recorded; the test pushes snapshots and replies."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.calls = []
        self._personal = {}
        self._available = True
        self._reply = {}
        self._retention = 'days_30'
        self._skills = []

    def set(self, personal=None, reply=None, retention=None, skills=None, available=None):
        if personal is not None:
            self._personal = personal
        if reply is not None:
            self._reply = reply
        if retention is not None:
            self._retention = retention
        if skills is not None:
            self._skills = skills
        if available is not None:
            self._available = available
        self.changed.emit()

    def _get_personal(self):
        return self._personal

    def _get_reply(self):
        return self._reply

    def _get_available(self):
        return self._available

    def _get_retention(self):
        return self._retention

    def _get_skills(self):
        return self._skills

    personal = Property('QVariantMap', _get_personal, notify=changed)
    personalReply = Property('QVariantMap', _get_reply, notify=changed)
    personalAvailable = Property(bool, _get_available, notify=changed)
    historyRetention = Property(str, _get_retention, notify=changed)
    skillsItems = Property('QVariantList', _get_skills, notify=changed)
    connected = Property(bool, lambda self: True, notify=changed)

    @Slot(str, str)
    def personalOp(self, area, payload):
        self.calls.append((area, json.loads(payload)))

    @Slot(str, result=str)
    def codeMessage(self, code):
        return 'Mensagem para ' + code

    @Slot()
    def refresh(self):
        self.calls.append(('refresh', {}))


def snapshot(**areas):
    base = {
        'memory': {'revision': 0, 'count': 0, 'capacity': 300, 'consent': {'user_typed': False, 'conversation': False, 'import': False}, 'facts': []},
        'souls': {'revision': 0, 'active': None, 'capacity': 12, 'souls': []},
        'habits': {'revision': 0, 'count': 0, 'capacity': 24, 'habits': []},
        'automations': {'revision': 0, 'count': 0, 'capacity': 16, 'automations': []},
        'conversations': {'revision': 0, 'recording': True, 'count': 0, 'capacity': 100, 'sessions': []},
    }
    base.update(areas)
    return base


CORE = FakeCore()

ENABLED_SKILL = {'id': 'notas', 'name': 'Notas', 'version': '1.0.0', 'state': 'enabled', 'active': True,
                 'deps_ok': True, 'permissions_ok': True}


class PersonalPages(unittest.TestCase):
    def setUp(self):
        # One core for the whole run, reset per test: an engine must never outlive the object it reads as `core`.
        self.core = CORE
        self.core.calls = []
        self.core.set(personal=snapshot(), reply={}, retention='days_30', skills=[], available=True)
        self.engines = []

    def load(self, page):
        engine = QQmlApplicationEngine()
        self.engines.append(engine)
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(str(i) for i in items))
        engine.rootContext().setContextProperty('core', self.core)
        engine.rootContext().setContextProperty('hostPageId', page)
        engine.rootContext().setContextProperty('hostPageUrl', QUrl.fromLocalFile(str(BASE / 'app' / 'pages' / PAGES[page])))
        engine.load(QUrl.fromLocalFile(str(BASE / 'scripts' / 'personal_host.qml')))
        self.assertTrue(engine.rootObjects(), 'host did not load: %s' % warnings)
        window = engine.rootObjects()[0]
        host = window.findChild(QObject, 'page')
        self.pump(lambda: host.property('item') is not None, 'page did not load: %s' % warnings)
        item = host.property('item')
        return window, item, warnings

    def pump(self, ready, message, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            APP.processEvents()
            if ready():
                return
            time.sleep(0.01)
        self.fail(message)

    def find_all(self, item, name):
        """Every visual item with this objectName. Rows made by a Repeater are visual children of its parent, not QObject
        children of the page, so the walk goes through childItems(); dialogs (Popups) are found by QObject search."""
        found = []

        def walk(node):
            for child in node.childItems():
                if child.objectName() == name:
                    found.append(child)
                walk(child)

        walk(item)
        found.extend(item.findChildren(QObject, name))
        return found

    def find(self, item, name):
        found = self.find_all(item, name)
        self.assertTrue(found, 'missing objectName %s' % name)
        return found[0]

    def click(self, item, name):
        QMetaObject.invokeMethod(self.find(item, name), 'click')
        APP.processEvents()

    def tearDown(self):
        for engine in self.engines:
            engine.deleteLater()
        for _ in range(3):
            APP.processEvents()
        self.engines = []

    def test_every_page_loads_with_a_core_block(self):
        for page in PAGES:
            with self.subTest(page=page):
                self.core.set(personal=snapshot())
                _, item, warnings = self.load(page)
                self.assertIsNotNone(item)
                self.assertFalse([w for w in warnings if PAGES[page] in w and 'error' in w.lower()], warnings)

    def test_memoria_consent_add_and_refusal(self):
        self.core.set(personal=snapshot(memory={
            'revision': 4, 'count': 1, 'capacity': 300,
            'consent': {'user_typed': True, 'conversation': False, 'import': False},
            'facts': [{'id': 'fact_1', 'text': 'Prefiro reuniões pela manhã', 'kind': 'preference',
                       'source': 'user_typed', 'created_ms': 1, 'expires_ms': None}]}))
        window, item, _ = self.load('memoria')
        self.assertTrue(self.find(item, 'memoryAdd').property('enabled') is False)  # empty text
        self.find(item, 'memoryNewText').setProperty('text', 'Gosto de chá')
        APP.processEvents()
        self.assertTrue(self.find(item, 'memoryAdd').property('enabled'))
        self.click(item, 'memoryAdd')
        area, payload = self.core.calls[-1]
        self.assertEqual(area, 'memory')
        self.assertEqual(payload['version'], 1)
        self.assertEqual(payload['op'], 'add')
        self.assertEqual(payload['revision'], 4)
        self.assertEqual(payload['source'], 'user_typed')
        self.assertEqual(payload['text'], 'Gosto de chá')
        # A refused request is shown as the Core's message, not as a raw code.
        self.core.set(reply={'area': 'memory', 'code': 'stale_revision', 'reply': {}})
        self.pump(lambda: self.find(item, 'personalResultText').property('text') == 'Mensagem para stale_revision',
                  'refusal not shown')

    def test_memoria_conversation_source_disabled_when_history_is_never(self):
        self.core.set(personal=snapshot(), retention='never')
        _, item, _ = self.load('memoria')
        self.assertFalse(self.find(item, 'consentConversation').property('enabled'))

    def test_revoking_a_source_asks_first(self):
        self.core.set(personal=snapshot(memory={
            'revision': 2, 'count': 1, 'capacity': 300,
            'consent': {'user_typed': True, 'conversation': False, 'import': False},
            'facts': [{'id': 'fact_1', 'text': 'x', 'kind': 'fact', 'source': 'user_typed', 'created_ms': 1, 'expires_ms': None}]}))
        _, item, _ = self.load('memoria')
        page_consent = self.find(item, 'consentUserTyped')
        # A click is what the user does: it toggles the switch and runs onToggled.
        self.click(item, 'consentUserTyped')
        self.assertEqual(self.core.calls, [], 'a revoke with facts must wait for the confirmation')

    def test_almas_create_sends_provenance_and_lists_souls(self):
        soul = {'id': 'soul_1', 'name': 'Calmo', 'description': 'Tom sereno', 'style': 'Frases curtas',
                'priorities': ['clareza'], 'mode': 'influence', 'mode_label': 'Influência: sugere estilo',
                'provenance': {'kind': 'declared', 'evidence': [], 'confidence': 1.0}, 'version': 1, 'active': True}
        self.core.set(personal=snapshot(souls={'revision': 3, 'active': 'soul_1', 'capacity': 12, 'souls': [soul]}))
        _, item, _ = self.load('almas')
        self.assertEqual(len(self.find_all(item, 'soulActivate')), 1)
        for name, text in (('soulName', 'Direto'), ('soulDescription', 'Objetivo'), ('soulStyle', 'Sem rodeios')):
            self.find(item, name).setProperty('text', text)
        self.find(item, 'soulPriorities').setProperty('text', 'clareza, segurança')
        APP.processEvents()
        self.click(item, 'soulCreate')
        area, payload = self.core.calls[-1]
        self.assertEqual((area, payload['op'], payload['revision']), ('souls', 'create', 3))
        self.assertEqual(payload['provenance'], {'kind': 'declared', 'evidence': [], 'confidence': 1.0})
        self.assertEqual(payload['priorities'], ['clareza', 'segurança'])
        self.assertEqual(payload['mode'], 'influence')

    def test_habitos_only_enabled_skills_and_json_inputs(self):
        habit = {'id': 'habit_1', 'name': 'Anotar', 'phrases': ['anota'], 'status': 'active',
                 'current': {'version': 1, 'skill_id': 'notas', 'skill_version': '1.0.0', 'inputs': {'pasta': 'diario'}},
                 'previous': None, 'outcomes': [{'at_ms': 1, 'code': 'ok', 'started': True}], 'created_ms': 1, 'updated_ms': 1}
        disabled = dict(ENABLED_SKILL, id='outra', state='disabled', active=False)
        self.core.set(personal=snapshot(habits={'revision': 1, 'count': 1, 'capacity': 24, 'habits': [habit]}),
                      skills=[ENABLED_SKILL, disabled])
        _, item, _ = self.load('habitos')
        self.assertEqual(len(self.find_all(item, 'habitRun')), 1)
        self.assertTrue(self.find(item, 'habitRun').property('enabled'))
        self.assertFalse(self.find(item, 'habitCreate').property('enabled'))
        self.find(item, 'habitName').setProperty('text', 'Diário')
        self.find(item, 'habitInputs').setProperty('text', '{nao json')
        APP.processEvents()
        self.assertFalse(self.find(item, 'habitCreate').property('enabled'), 'invalid JSON inputs must block create')
        self.find(item, 'habitInputs').setProperty('text', '{"pasta": "diario"}')
        APP.processEvents()
        self.assertTrue(self.find(item, 'habitCreate').property('enabled'))
        self.click(item, 'habitCreate')
        area, payload = self.core.calls[-1]
        self.assertEqual((area, payload['op'], payload['skill_id']), ('habits', 'create', 'notas'))
        self.assertEqual(payload['inputs'], {'pasta': 'diario'})

    def test_automacoes_once_schedule_is_in_the_future(self):
        self.core.set(personal=snapshot(), skills=[ENABLED_SKILL])
        before = time.time() * 1000
        _, item, _ = self.load('automacoes')
        self.find(item, 'autoName').setProperty('text', 'Relatório')
        APP.processEvents()
        self.click(item, 'autoCreate')
        area, payload = self.core.calls[-1]
        self.assertEqual((area, payload['op'], payload['skill_id']), ('automations', 'create', 'notas'))
        self.assertEqual(payload['schedule']['kind'], 'once')
        self.assertGreater(payload['schedule']['at_ms'], before)

    def test_conversas_lists_opens_and_exports(self):
        session = {'id': 'conv_1', 'title': 'Que horas são?', 'turns': 2, 'created_ms': 1, 'updated_ms': 2}
        self.core.set(personal=snapshot(conversations={'revision': 5, 'recording': True, 'count': 1, 'capacity': 100,
                                                       'sessions': [session]}))
        _, item, _ = self.load('conversas')
        self.assertEqual(len(self.find_all(item, 'conversaOpen')), 1)
        self.click(item, 'conversaOpen')
        self.assertEqual(self.core.calls[-1], ('conversations', {'version': 1, 'op': 'get', 'session_id': 'conv_1'}))
        self.core.set(reply={'area': 'conversations', 'code': 'ok', 'reply': {'session': {
            'id': 'conv_1', 'title': 'Que horas são?', 'created_ms': 1, 'updated_ms': 2,
            'turns': [{'role': 'user', 'text': 'Que horas são?', 'at_ms': 1},
                      {'role': 'assistant', 'text': 'São 10h.', 'at_ms': 2}]}}})
        self.pump(lambda: item.property('openSession') is not None, 'conversation not shown')
        self.click(item, 'conversasExport')
        self.assertEqual(self.core.calls[-1], ('conversations', {'version': 1, 'op': 'export'}))


if __name__ == '__main__':
    unittest.main(verbosity=2)
