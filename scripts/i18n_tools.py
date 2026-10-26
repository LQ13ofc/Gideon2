#!/usr/bin/env python3
"""WP-20 interface translations: refresh the .ts sources from the code, and compile the .qm catalogs.

`update` runs Qt's lupdate over app/**/*.qml, app/**/*.js and the Python modules that show text (source language
pt-BR) and merges the result into app/translations/gideon_en.ts and gideon_fr.ts. `release` runs lrelease on both
into app/translations/*.qm, the build output that scripts/build_package.py packages. This script only runs Qt tools;
the translations themselves are written in the .ts files.

Usage: target/ui-venv/bin/python scripts/i18n_tools.py update|release
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app'
TRANSLATIONS = APP / 'translations'
TARGET_LOCALES = {'en': 'en_US', 'fr': 'fr_FR'}
PYTHON_SOURCES = ('bridge.py', 'uisettings.py')
SKIPPED_DIRS = frozenset({'__pycache__', 'translations'})


def qt_tool(name):
    """Qt's own binary shipped inside the PySide6 package (the pyside6-* wrappers cannot locate it)."""
    spec = importlib.util.find_spec('PySide6')
    if spec is None or not spec.submodule_search_locations:
        raise SystemExit('PySide6 is not installed in this interpreter')
    path = Path(list(spec.submodule_search_locations)[0]) / name
    if not path.is_file():
        raise SystemExit(f'Qt tool not found: {path}')
    return str(path)


def sources():
    """Every QML and JS file under app/, plus the Python modules that build user-facing text."""
    found = [
        path for path in sorted(APP.rglob('*'))
        if path.suffix in ('.qml', '.js') and not SKIPPED_DIRS.intersection(path.parts)
    ]
    found += [APP / name for name in PYTHON_SOURCES]
    return [str(path.relative_to(ROOT)) for path in found]


def ts_path(code, source):
    """One .ts per source file: app/translations/<code>/<path under app/>.ts (keeps each page's strings reviewable)."""
    return TRANSLATIONS / code / (Path(source).relative_to('app').as_posix() + '.ts')


def update():
    """Refresh every per-file .ts from the code. Existing translations are kept; removed strings are dropped."""
    tool = qt_tool('lupdate')
    for source in sources():
        for code, locale in TARGET_LOCALES.items():
            ts = ts_path(code, source)
            ts.parent.mkdir(parents=True, exist_ok=True)
            command = [
                tool, '-no-obsolete', '-locations', 'relative',
                '-source-language', 'pt_BR', '-target-language', locale,
                source, '-ts', str(ts.relative_to(ROOT)),
            ]
            subprocess.run(command, cwd=ROOT, check=True)


def release():
    """Compile every language's .ts files into one catalog: app/translations/gideon_<code>.qm (build output)."""
    tool = qt_tool('lrelease')
    for code in TARGET_LOCALES:
        files = sorted((TRANSLATIONS / code).rglob('*.ts'))
        qm = TRANSLATIONS / f'gideon_{code}.qm'
        subprocess.run(
            [tool, *[str(path.relative_to(ROOT)) for path in files], '-qm', str(qm.relative_to(ROOT))],
            cwd=ROOT, check=True,
        )


def main(argv):
    commands = {'update': update, 'release': release}
    if len(argv) != 1 or argv[0] not in commands:
        print(__doc__)
        return 2
    commands[argv[0]]()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
