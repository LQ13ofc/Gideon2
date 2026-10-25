#!/usr/bin/env python3
"""Frente 2 (Idiomas): app/pages/CfgIdiomas.qml loads like app/main.py (QQmlApplicationEngine, `core` context
property) and renders the languages block the Core sends: checkboxes, radios, disabled install controls, restart note.

Run with the UI venv (offscreen, needs no display):
  QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_languages_qml.py
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ['QT_QUICK_CONTROLS_STYLE'] = 'Basic'  # the app ships its own look, never a desktop style (app/main.py)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'app'))

from PySide6.QtCore import QObject, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402

from bridge import Bridge  # noqa: E402

LABELS = {'en': 'Inglês', 'fr': 'Francês', 'pt-BR': 'Português (Brasil)'}
INSTALL_REASON = 'Não incluído neste pacote: a instalação de idiomas extras ainda não existe.'


def item(ident, kind, state, **kw):
    row = {'id': ident, 'kind': kind, 'label': LABELS[ident], 'state': state, 'engine': None, 'size_bytes': None,
           'size_partial': False, 'size_note': None, 'license': None, 'sha256': None, 'quality': 'não medido',
           'evidence': None, 'voices': [], 'reason': None, 'selected': False, 'source': 'teste'}
    if state == 'available_not_installed':
        row['reason'] = 'Não instalado: ' + INSTALL_REASON
    row.update(kw)
    row['selectable'] = state == 'bundled'
    return row


def languages_block(restart_tts=False):
    return {
        'version': 1,
        'engines': {
            'stt': [item('en', 'stt', 'bundled', engine='moonshine', selected=True, license='MIT'),
                    item('fr', 'stt', 'available_not_installed', engine='vosk', size_bytes=41000000, size_partial=True),
                    item('pt-BR', 'stt', 'available_not_installed', engine='vosk-pt', size_bytes=31000000, size_partial=True)],
            'tts': [item('en', 'tts', 'bundled', engine='pocket', voices=['alba'], selected=True, license='CC-BY-4.0'),
                    item('fr', 'tts', 'available_not_installed', engine='pocket-fr', size_bytes=219336289, size_partial=True),
                    item('pt-BR', 'tts', 'available_not_installed', engine='pocket-pt', size_bytes=219337561, size_partial=True)],
            'wake': [item('en', 'wake', 'bundled', engine='kws'), item('fr', 'wake', 'unsupported', reason='Sem modelo'),
                     item('pt-BR', 'wake', 'unsupported', reason='Sem modelo')],
        },
        'stt_selected': ['en'], 'tts_selected': 'en', 'tts_voice': 'alba',
        'restart_required': {'stt': False, 'tts': restart_tts},
        'install': {'available': False, 'reason': INSTALL_REASON},
    }


def walk(obj):
    """Visual tree: Repeater delegates are not QObject children of the page, so childItems are walked too."""
    yield obj
    children = list(obj.findChildren(QObject, options=Qt.FindChildOption.FindDirectChildrenOnly))
    if isinstance(obj, QQuickItem):
        children += [c for c in obj.childItems() if c not in children]
    for child in children:
        yield from walk(child)


class Values:
    """Read-only copy of an item's properties, shaped like the QObject.property() calls the tests use."""

    def __init__(self, values):
        self.values = values

    def property(self, name):
        return self.values.get(name)


APP = None


def setUpModule():
    global APP
    APP = QGuiApplication.instance() or QGuiApplication(sys.argv)


class IdiomasPage(unittest.TestCase):
    def setUp(self):
        self.kept = []

    def load(self, snapshot=None):
        bridge = Bridge(Path(tempfile.mkdtemp(prefix='gideon-idiomas-')))
        if snapshot is not None:
            bridge.snapshot = {'languages': snapshot}
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty('core', bridge)
        engine.load(QUrl.fromLocalFile(str(BASE / 'app/pages/CfgIdiomas.qml')))
        for _ in range(3):
            APP.processEvents()
        roots = engine.rootObjects()
        self.assertEqual(len(roots), 1, 'CfgIdiomas.qml must load without QML errors')
        # The engine and the bridge must outlive the test: QML reads `core` on every binding re-evaluation.
        self.kept.extend([bridge, engine])
        return roots[0], bridge

    def named(self, page):
        """Plain values read at once: delegate items can be destroyed by the next model change, so no wrappers are kept."""
        out = {}
        for o in walk(page):
            if o.objectName():
                out[o.objectName()] = Values({p: o.property(p) for p in ('enabled', 'checked', 'visible', 'text')})
        return out

    def test_page_loads_and_shows_one_row_per_language_with_honest_state(self):
        page, _ = self.load(languages_block(restart_tts=True))
        names = self.named(page)
        for ident in ('en', 'fr', 'pt-BR'):
            self.assertIn('sttLanguage_' + ident, names)
            self.assertIn('ttsLanguage_' + ident, names)
        self.assertIn('installStt_fr', names)
        self.assertIn('installTts_pt-BR', names)
        # English is installed: selectable and checked; French and Portuguese are not selectable.
        self.assertTrue(names['sttLanguage_en'].property('enabled'))
        self.assertTrue(names['sttLanguage_en'].property('checked'))
        self.assertFalse(names['sttLanguage_fr'].property('enabled'))
        self.assertFalse(names['ttsLanguage_pt-BR'].property('enabled'))
        self.assertTrue(names['ttsLanguage_en'].property('checked'))

    def test_install_controls_stay_disabled_with_the_owner_approval_reason(self):
        page, _ = self.load(languages_block())
        names = self.named(page)
        for name in ('installStt_fr', 'installStt_pt-BR', 'installTts_fr', 'installTts_pt-BR'):
            self.assertFalse(names[name].property('enabled'), name)
        self.assertIn(INSTALL_REASON, names['installReasonText'].property('text'))

    def test_restart_note_follows_the_core_flag_and_apply_needs_a_change(self):
        page, _ = self.load(languages_block(restart_tts=True))
        names = self.named(page)
        self.assertTrue(names['languagesRestartNote'].property('text').startswith('Idioma salvo'))
        self.assertFalse(names['applyLanguagesButton'].property('enabled'), 'no change, nothing to apply')
        page2, _ = self.load(languages_block(restart_tts=False))
        self.assertFalse(self.named(page2)['languagesRestartNote'].property('visible'))

    def test_without_a_snapshot_the_page_loads_empty_and_nothing_can_be_applied(self):
        page, _ = self.load(None)
        names = self.named(page)
        self.assertIn('applyLanguagesButton', names)
        self.assertFalse(any(n.startswith('sttLanguage_') for n in names))
        self.assertFalse(names['applyLanguagesButton'].property('enabled'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
