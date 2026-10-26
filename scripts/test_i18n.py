#!/usr/bin/env python3
"""WP-20 interface language: the catalogs, the translations module, the Portuguese left outside qsTr, and a live switch.

Run with the UI venv (offscreen, needs no display):
  QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_i18n.py

- Catalogs: every app source has an en and an fr catalog; no message is unfinished or empty; the catalogs match what
  lupdate extracts from the code (a string added or removed without `scripts/i18n_tools.py update` fails here).
- translations.py: locale mapping, the profile's config.json, the system fallback, and the installed catalog.
- Hard-coded Portuguese: a scan of app/**/*.qml, *.js and the bridge modules. A Portuguese literal outside qsTr,
  QT_TR_NOOP or translate fails, unless its file is in PENDING_FILES (the list of screens not yet migrated) or it is a
  language's own name. A file that is migrated must leave PENDING_FILES, so the list cannot go stale.
- Live switch: CfgIdiomas.qml is loaded, the language is switched with the same calls main.py makes, and its texts
  change without a restart.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

os.environ['QT_QUICK_CONTROLS_STYLE'] = 'Basic'
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

BASE = Path(__file__).resolve().parents[1]
APP = BASE / 'app'
sys.path.insert(0, str(APP))
sys.path.insert(0, str(BASE / 'scripts'))

import i18n_tools  # noqa: E402
import translations  # noqa: E402

LANGS = ('en', 'fr')

# Screens and modules still written in Portuguese only (WP-20 pending). Each entry is removed when its file is migrated;
# the test fails when a listed file has become clean, so the list is always the real state. See docs/WP20.md.
PENDING_FILES = frozenset({
    'app/bridge.py', 'app/uisettings.py',
    'app/components/AProposalCard.qml', 'app/components/BExt.js', 'app/components/BPluginDetail.qml',
    'app/components/BPluginRow.qml', 'app/components/BSkillDetail.qml', 'app/components/BSkillRow.qml',
    'app/components/CAccountCard.qml', 'app/components/CModelDetail.qml', 'app/components/CPerceptionCard.qml',
    'app/components/DPermDialogs.qml', 'app/components/ECfgSearch.qml', 'app/components/EColorRole.qml',
    'app/components/EJsonDialog.qml', 'app/components/EPreviewCard.qml', 'app/components/ILevelMeter.qml',
    'app/components/IMicOffer.qml', 'app/components/IMicProbe.qml', 'app/components/LiveAudioConsent.qml',
    'app/components/OOnboarding.qml', 'app/components/Orb.qml', 'app/components/PResult.qml',
    'app/components/PRetentionNote.qml', 'app/components/RealActionsConsent.qml', 'app/components/SettingRow.qml',
    'app/pages/Agente.qml', 'app/pages/Almas.qml', 'app/pages/Atividade.qml', 'app/pages/Automacoes.qml',
    'app/pages/CfgAparencia.qml', 'app/pages/CfgAudio.qml', 'app/pages/CfgDispositivos.qml', 'app/pages/CfgGeral.qml',
    'app/pages/CfgPrivacidade.qml', 'app/pages/CfgVoz.qml', 'app/pages/Conexoes.qml', 'app/pages/Conversa.qml',
    'app/pages/Conversas.qml', 'app/pages/DiagDev.qml', 'app/pages/DiagEstado.qml', 'app/pages/DiagMotores.qml',
    'app/pages/DiagRecuperacao.qml', 'app/pages/Habitos.qml', 'app/pages/InicioHoje.qml', 'app/pages/Memoria.qml',
    'app/pages/ModelosLlm.qml', 'app/pages/Percepcao.qml', 'app/pages/PermAuditoria.qml', 'app/pages/PermConcessoes.qml',
    'app/pages/PermVisao.qml', 'app/pages/Plugins.qml', 'app/pages/Skills.qml', 'app/shell/ActivityRows.js',
    'app/shell/CfgSettings.js', 'app/shell/EventLabels.js', 'app/shell/PermRows.js',
    'app/components/GDrawer.qml', 'app/components/Modal.qml', 'app/components/PConfirm.qml', 'app/components/Toast.qml',
})

# Literal texts that are a language's own name (endonyms). They stay as they are in every language.
ENDONYMS = frozenset({'Português (Brasil)', 'Français'})

QT_TEXT_CALL = re.compile(r'\b(?:qsTr|QT_TR_NOOP|tr)\(\s*("(?:[^"\\]|\\.)*")')
TRANSLATE_CALL = re.compile(r'\btranslate\(\s*(?:"[^"]*"|\'[^\']*\')\s*,\s*("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')')
LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'')
PT_ACCENTS = re.compile('[àáâãçéêíóôõúÀÁÂÃÇÉÊÍÓÔÕÚ]')
PT_WORDS = re.compile(r'\b(?:de|do|da|dos|das|não|para|com|sem|uma|você|seu|sua|foi|está|estão|são|nenhum|nenhuma|'
                      r'Core|salvo|salva|escolha|Erro|Falha|Concluído|Pronto|Ativo|Parado|Modo|Escuta|'
                      # Common Portuguese UI words without accents: the accent test alone misses them.
                      r'Salvar|Cancelar|Fechar|Abrir|Aplicar|Restaurar|Instalar|Verificar|Ativar|Desativar|Conexão|'
                      r'Conexões|Configuração|Configurações|Permissão|Permissões|Hoje|Conversa|Histórico|Agente|'
                      r'Atividade|Automação|Automações|Memória|Dispositivo|Dispositivos|Privacidade|Aparência|'
                      r'Diagnóstico|Estado|Motor|Motores|Recuperação|Excluir|Apagar|Enviar|Carregar|Pausar|Tente|'
                      r'Clique|Digite|Confirmar|Desconectar|Conectar|Atualizar|Voltar|Próximo|Anterior|Sim|Iniciar|'
                      r'Parar|Mostrar|Ocultar|Ligar|Desligar|Aguardando|Pendente|Gravar|Ouvir|Captura|Resposta|'
                      r'Sessão|Modelo|Modelos|Ouvindo|Transcrevendo|Executando|Respondendo|Reinício|Mudo|Desligado|'
                      r'Tamanho|Licença|Qualidade|Instalado|Concluída|falhou|cancelado|pendente|erro|ativo|ativa)\b')


def sources():
    return [BASE / name for name in i18n_tools.sources()]


def catalog(code, source):
    return BASE / i18n_tools.ts_path(code, str(source.relative_to(BASE))).relative_to(BASE)


def messages(path):
    """(context, source, translation, unfinished) for every message of one .ts file."""
    out = []
    root = ET.parse(path).getroot()
    for context in root.findall('context'):
        name = context.findtext('name')
        for message in context.findall('message'):
            translation = message.find('translation')
            unfinished = translation is None or translation.get('type') == 'unfinished'
            out.append((name, message.findtext('source') or '', (translation.text or '') if translation is not None else '', unfinished))
    return out


def portuguese_literals(text):
    """Quoted texts of one code line that are Portuguese, after removing the calls that already translate them."""
    stripped = QT_TEXT_CALL.sub('""', text)
    stripped = TRANSLATE_CALL.sub('""', stripped)
    found = []
    for match in LITERAL.finditer(stripped):
        value = match.group(1) if match.group(1) is not None else match.group(2)
        if not value or value in ENDONYMS:
            continue
        if PT_ACCENTS.search(value) or PT_WORDS.search(value):
            found.append(value)
    return found


def scan_file(path):
    hits = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if line.lstrip().startswith(('//', '#', '*')):
            continue
        hits.extend((number, value) for value in portuguese_literals(line))
    return hits


def scanned_files():
    names = [p for p in sorted(APP.rglob('*')) if p.suffix in ('.qml', '.js') and '__pycache__' not in p.parts
             and 'translations' not in p.parts]
    names += [APP / 'bridge.py', APP / 'uisettings.py']
    return names


class Catalogs(unittest.TestCase):
    def test_every_source_has_a_catalog_per_language(self):
        missing = [str(catalog(code, s)) for s in sources() for code in LANGS if not catalog(code, s).is_file()]
        self.assertEqual(missing, [])

    def test_no_message_is_unfinished_or_empty(self):
        bad = []
        for code in LANGS:
            for path in sorted((BASE / 'app/translations' / code).rglob('*.ts')):
                for context, source, translation, unfinished in messages(path):
                    if unfinished or not translation.strip():
                        bad.append((code, context, source))
        self.assertEqual(bad, [], f'{len(bad)} message(s) without a translation')

    def test_catalogs_match_the_code_extraction(self):
        """lupdate is the reference: the same (context, source) pairs must be in the code and in every catalog."""
        with tempfile.TemporaryDirectory(prefix='gideon-i18n-') as tmp:
            combined = Path(tmp) / 'extracted.ts'
            command = [i18n_tools.qt_tool('lupdate'), '-no-obsolete', '-locations', 'none',
                       '-source-language', 'pt_BR', *[str(s.relative_to(BASE)) for s in sources()],
                       '-ts', str(combined)]
            subprocess.run(command, cwd=BASE, check=True, capture_output=True)
            extracted = {(c, s) for c, s, _, _ in messages(combined)}
        for code in LANGS:
            committed = set()
            for s in sources():
                path = catalog(code, s)
                if path.is_file():
                    committed |= {(c, src) for c, src, _, _ in messages(path)}
            self.assertEqual(committed - extracted, set(), f'{code}: strings no longer in the code')
            self.assertEqual(extracted - committed, set(), f'{code}: strings in the code without a translation')

    def test_compiled_catalogs_are_built_from_the_sources(self):
        self.assertEqual(i18n_tools.main(['release']), 0)
        for code in LANGS:
            qm = APP / 'translations' / f'gideon_{code}.qm'
            self.assertTrue(qm.is_file() and qm.stat().st_size > 0, qm)


class TranslationsModule(unittest.TestCase):
    def test_locale_names_map_to_the_three_languages_or_none(self):
        self.assertEqual(translations.from_locale('pt_BR.UTF-8'), 'pt-BR')
        self.assertEqual(translations.from_locale('pt_PT'), 'pt-BR')
        self.assertEqual(translations.from_locale('en_GB'), 'en')
        self.assertEqual(translations.from_locale('fr'), 'fr')
        self.assertIsNone(translations.from_locale('de_DE'))
        self.assertIsNone(translations.from_locale('C'))
        self.assertIsNone(translations.from_locale(None))

    def test_system_language_follows_the_first_locale_variable_that_is_set(self):
        with mock.patch.dict(os.environ, {'LC_ALL': '', 'LC_MESSAGES': 'fr_FR.UTF-8', 'LANG': 'en_US'}, clear=False):
            self.assertEqual(translations.environment_language(), 'fr')
        with mock.patch.dict(os.environ, {'LC_ALL': 'de_DE', 'LANG': 'fr_FR'}, clear=False):
            self.assertEqual(translations.environment_language(), 'pt-BR')
        with mock.patch.dict(os.environ, {'LC_ALL': '', 'LC_MESSAGES': '', 'LANG': ''}, clear=False):
            self.assertEqual(translations.environment_language(), 'pt-BR')

    def test_profile_value_wins_only_when_it_is_one_of_the_three(self):
        with tempfile.TemporaryDirectory(prefix='gideon-i18n-profile-') as tmp:
            root = Path(tmp)
            self.assertIsNone(translations.profile_language(root))
            (root / 'config.json').write_text(json.dumps({'ui_language': 'en'}), encoding='utf-8')
            self.assertEqual(translations.profile_language(root), 'en')
            self.assertEqual(translations.initial_language(root), 'en')
            (root / 'config.json').write_text(json.dumps({'ui_language': 'pt-PT'}), encoding='utf-8')
            self.assertIsNone(translations.profile_language(root))
            (root / 'config.json').write_text('not json', encoding='utf-8')
            self.assertIsNone(translations.profile_language(root))

    def test_apply_rejects_unknown_languages(self):
        from PySide6.QtCore import QCoreApplication
        app = QCoreApplication.instance() or QCoreApplication(sys.argv)
        with self.assertRaises(ValueError):
            translations.apply(app, 'de')


class HardcodedPortuguese(unittest.TestCase):
    def test_no_portuguese_literal_outside_qstr_except_pending_files(self):
        found = {}
        for path in scanned_files():
            hits = scan_file(path)
            if hits:
                found[str(path.relative_to(BASE))] = hits[:5]
        unexpected = {p: h for p, h in found.items() if p not in PENDING_FILES}
        self.assertEqual(unexpected, {}, 'Portuguese text outside qsTr in a migrated file')

    def test_pending_list_is_exact(self):
        """A pending file that is clean must leave PENDING_FILES, so the list is the real state of the migration."""
        clean = []
        for name in sorted(PENDING_FILES):
            if not scan_file(BASE / name):
                clean.append(name)
        self.assertEqual(clean, [], 'clean files still listed as pending')
        missing = [name for name in PENDING_FILES if not (BASE / name).is_file()]
        self.assertEqual(missing, [])


class LiveSwitch(unittest.TestCase):
    """The page reads the language from the translator main.py installs; switching it re-evaluates the bindings."""
    def setUp(self):
        from PySide6.QtGui import QGuiApplication
        self.app = QGuiApplication.instance()

    def tearDown(self):
        translations.apply(self.app, translations.SOURCE_LANGUAGE)

    def test_cfg_idiomas_changes_language_without_restart(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuick import QQuickItem
        from bridge import Bridge
        bridge = Bridge(Path(tempfile.mkdtemp(prefix='gideon-i18n-live-')))
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty('core', bridge)
        engine.load(QUrl.fromLocalFile(str(APP / 'pages/CfgIdiomas.qml')))
        self.assertEqual(len(engine.rootObjects()), 1)
        page = engine.rootObjects()[0]

        def button_text():
            for child in page.findChildren(QQuickItem):
                if child.objectName() == 'applyLanguagesButton':
                    return child.property('text')
            return None

        self.assertEqual(button_text(), 'Aplicar')
        self.assertEqual(translations.apply(self.app, 'en'), True)
        engine.retranslate()
        self.assertEqual(button_text(), 'Apply')
        self.assertEqual(translations.apply(self.app, 'fr'), True)
        engine.retranslate()
        self.assertEqual(button_text(), 'Appliquer')
        self.assertEqual(translations.apply(self.app, 'pt-BR'), True)
        engine.retranslate()
        self.assertEqual(button_text(), 'Aplicar')
        bridge.deleteLater()


def main():
    from PySide6.QtGui import QGuiApplication
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    unittest.main(argv=[sys.argv[0]] + sys.argv[1:], verbosity=2)


if __name__ == '__main__':
    main()
