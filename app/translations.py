"""WP-20 interface language: the one QTranslator the QML engine and the bridge share.

Portuguese (pt-BR) is the source language, so it needs no catalog. English and French load the compiled catalogs
`translations/gideon_en.qm` and `translations/gideon_fr.qm`, built from the `.ts` sources by `scripts/i18n_tools.py`.
The language itself is the Core preference `preferences.ui_language` (src/storage.rs UiLanguage). Before the Core
answers, the app reads the profile's config.json with the same rule the Core uses for a missing value: the first
non-empty of LC_ALL, LC_MESSAGES, LANG, mapped to one of the three languages, otherwise pt-BR.
"""
import json
import os
from pathlib import Path
from PySide6.QtCore import QCoreApplication,QTranslator

UI_LANGUAGES=('pt-BR','en','fr')
SOURCE_LANGUAGE='pt-BR'
CATALOG_DIR=Path(__file__).resolve().parent/'translations'
CATALOG_NAMES={'en':'gideon_en.qm','fr':'gideon_fr.qm'}
_translator=None
_current=SOURCE_LANGUAGE


def from_locale(name):
    """UI language of a POSIX locale name (`fr_FR.UTF-8`, `en`, `pt_PT`), or None when it is none of the three."""
    if not isinstance(name,str):return None
    code=name.replace('-','_').replace('@','_').replace('.','_').split('_',1)[0].lower()
    return {'pt':'pt-BR','en':'en','fr':'fr'}.get(code)


def environment_language():
    """Same rule as src/storage.rs: the first non-empty of LC_ALL, LC_MESSAGES, LANG; no usable locale is pt-BR."""
    for name in ('LC_ALL','LC_MESSAGES','LANG'):
        value=os.environ.get(name,'')
        if value:return from_locale(value) or SOURCE_LANGUAGE
    return SOURCE_LANGUAGE


def profile_language(root):
    """The ui_language stored in the profile's config.json, or None when the file or the value is missing or invalid."""
    try:
        with open(Path(root)/'config.json','r',encoding='utf-8') as handle:data=json.load(handle)
    except (OSError,ValueError):return None
    value=data.get('ui_language') if isinstance(data,dict) else None
    return value if value in UI_LANGUAGES else None


def initial_language(root):
    return profile_language(root) or environment_language()


def current():
    return _current


def apply(app,language):
    """Make `language` the active UI language of `app`. False when its catalog is missing: the source text stays."""
    global _translator,_current
    if language not in UI_LANGUAGES:raise ValueError('unsupported ui language')
    if _translator is not None:
        app.removeTranslator(_translator)
        _translator=None
    _current=language
    if language==SOURCE_LANGUAGE:return True
    translator=QTranslator(app)
    if not translator.load(str(CATALOG_DIR/CATALOG_NAMES[language])):return False
    app.installTranslator(translator)
    _translator=translator
    return True


# WP-20 G5c: the translate helpers, moved from app/bridge.py so the msgs_* modules can use them without a cycle.
CONTEXT='Bridge'

def _tr(text,*args):
    """The text in the active UI language (translations.py); %1, %2... take `args`. Portuguese when no catalog has it."""
    out=QCoreApplication.translate(CONTEXT,text)
    for number,value in enumerate(args,1):out=out.replace(f'%{number}',str(value))
    return out

def _fill(text,*args):
    """A translated text (QCoreApplication.translate, so lupdate sees the literal) with its %1, %2... replaced by `args`."""
    for number,value in enumerate(args,1):text=text.replace(f'%{number}',str(value))
    return text

class _Messages(dict):
    """Message table: every lookup translates at access time, so a language switch shows the new text. Keys stay codes."""
    def __getitem__(self,key):return _tr(dict.__getitem__(self,key))
    def get(self,key,default=None):return self[key] if key in self else default
    def raw(self,key):
        """The Portuguese source of one entry, not translated: stored messages keep it and translate when they are read."""
        return dict.__getitem__(self,key)
