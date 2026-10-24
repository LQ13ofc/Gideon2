#!/usr/bin/env python3
"""Explore the packaged QML client on the real desktop (Wayland) like a user would.

Run: target/ui-venv/bin/python -I -B scripts/explore_ui.py --root ABS_CORE_ROOT [--out DIR] [--pages "Conversa,Plugins"]
Round 2: start the populated private Core first with scripts/explore_setup.py (it prints ROOT=...). The root must be
that private Core (a path containing GideonTeste is refused). --pages takes page labels (accent-insensitive); without
it every page is visited (through its tab and sub-tab), plus the Motor LLM form, Tab focus and the resize pass.

The app is loaded in-process exactly like app/main.py (same create(), same QT_QUICK_CONTROLS_STYLE=Basic).
Navigation is the window's own shell: a level-1 tab (objectName tab_<tab>), then a level-2 sub-tab (subtab_<page>).
Every interaction is an event delivered to our own QQuickWindow (QMouseEvent / QKeyEvent sent with
QCoreApplication.sendEvent, the same events QTest.mouseClick / keyClick build). QTest's own helpers deadlock
with the Qt render thread here (RoundedImage.paint needs the GIL), so they are not used. Nothing is injected
system-wide and nothing is clicked outside the window.

Safety: only navigation, tab switches, read-only probes (Simular/Validar dry runs, Testar leitura, Planejar,
Capturar, Árvore, Estado, Atualizar, model selection in the list) and Escape are clicked. Destructive, consenting,
connecting, installing, approving, exporting, saving, starting-agent, key and appearance buttons are recorded as
skipped (whitelist, not blacklist). Typed text: an invalid model id into the Motor LLM field (validator check, nothing
saved) and ONE chat message on the Conversa page to the scripted fake LLM (the page's own send button).
"""
import argparse, json, os, re, sys, time, traceback
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'app'))

DEFAULT_OUT = '/tmp/claude-1000/ui-shots2'

parser = argparse.ArgumentParser()
parser.add_argument('--root', required=True, help='absolute root of the private test Core (scripts/explore_setup.py)')
parser.add_argument('--out', default=DEFAULT_OUT)
parser.add_argument('--pages', default='', help='comma list of page labels (for example "Conversa,Plugins"); default all')
args = parser.parse_args()

if 'offscreen' in os.environ.get('QT_QPA_PLATFORM', ''):
    sys.exit('refusing: QT_QPA_PLATFORM must not be offscreen')
root = Path(args.root)
if not root.is_absolute():
    sys.exit('absolute root required')
if 'GideonTeste' in str(root):
    sys.exit('refusing: the owner profile GideonTeste is not an exploration target')
if not (root / 'core.sock').exists():
    sys.exit(f'no Core socket at {root / "core.sock"}: start scripts/explore_setup.py first')
WANT = None if not args.pages.strip() else {t.strip() for t in args.pages.split(',') if t.strip()}
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)

# Same as app/main.py __main__: the client ships its own look.
os.environ['QT_QUICK_CONTROLS_STYLE'] = 'Basic'
# The first-run guide (B1) covers the pages the explorer visits: it starts suppressed (read by uisettings.py).
os.environ['GIDEON_UI_NO_ONBOARDING'] = '1'

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickItem
from PySide6.QtGui import QKeyEvent, QMouseEvent
from main import create  # app/main.py: registers Gideon.Visual and defines create(app, root)


def pump_events(seconds):
    """Process Qt events while sleeping. time.sleep releases the GIL: the Qt render thread may call into Python
    and blocks on the GIL if the main thread blocks inside C++ waits."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.01)


class Input:
    """Event delivery into our own window, same shape as PySide6.QtTest mouseClick/keyClick/keyClicks.
    QTest itself deadlocks here (it waits for rendering while holding the GIL), so the events are sent directly."""
    @staticmethod
    def qWait(ms):
        pump_events(ms / 1000.0)

    @staticmethod
    def mouseClick(target, button, modifiers, pos):
        p = QPointF(pos)
        QCoreApplication.sendEvent(target, QMouseEvent(QEvent.Type.MouseButtonPress, p, p, button, button, modifiers))
        QCoreApplication.sendEvent(target, QMouseEvent(QEvent.Type.MouseButtonRelease, p, p, button, Qt.MouseButton.NoButton, modifiers))
        pump_events(0.02)

    @staticmethod
    def keyClick(target, key):
        Input.keyClicks_raw(target, key.value, Qt.KeyboardModifier.NoModifier, '' if key != Qt.Key.Key_Space else ' ')

    @staticmethod
    def keyClicks_raw(target, key_value, modifiers, text):
        QCoreApplication.sendEvent(target, QKeyEvent(QEvent.Type.KeyPress, key_value, modifiers, text))
        QCoreApplication.sendEvent(target, QKeyEvent(QEvent.Type.KeyRelease, key_value, modifiers, text))
        pump_events(0.02)

    @staticmethod
    def keyClicks(target, text):
        for ch in text:
            Input.keyClicks_raw(target, 0, Qt.KeyboardModifier.NoModifier, ch)

# Qt messages: a Python qInstallMessageHandler deadlocks here, so Qt's own C++ handler writes to stderr and fd 2 is
# redirected to a private log. collect_messages() reads what Qt wrote since the last call.
MESSAGES = []
MSG_LOG = out / 'qt-stderr.log'
_msg_fd = os.open(MSG_LOG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.dup2(_msg_fd, 2)
_msg_pos = 0


def collect_messages():
    global _msg_pos
    with open(MSG_LOG, 'rb') as handle:
        handle.seek(_msg_pos)
        data = handle.read()
    _msg_pos += len(data)
    for line in data.decode('utf-8', 'replace').splitlines():
        if not line.strip():
            continue
        low = line.lower()
        if 'fatal' in low:
            kind = 'QtFatalMsg'
        elif 'critical' in low or 'error' in low:
            kind = 'QtCriticalMsg'
        elif 'warn' in low or 'binding loop' in low or 'qml' in low or 'qrc:' in low or 'file:' in low:
            kind = 'QtWarningMsg'
        else:
            kind = 'other'
        MESSAGES.append({'type': kind, 'message': line[:400], 't': round(time.monotonic(), 2)})


app = QGuiApplication(sys.argv)
if app.platformName() != 'wayland':
    sys.exit(f'refusing: platform is {app.platformName()!r}, expected wayland')

bridge, engine = create(app, root)
window = engine.rootObjects()[0]

REPORT = {'platform': app.platformName(), 'root': str(root), 'out': str(out), 'started': time.strftime('%Y-%m-%d %H:%M:%S'),
          'pages': [], 'resize': [], 'tab_focus': [], 'dialogs': [], 'exceptions': [], 'notes': []}
EXC = REPORT['exceptions']

# Overlays: the modal dialogs (Motor LLM, confirmations) and the command palette.
DIALOGS = ['llmDialog', 'hubReviewDialog', 'removeConfirm', 'revokeConfirm', 'removeCustomConfirm', 'clearPluginConfirm',
           'removeSkillConfirm', 'restoreConfirm', 'devModeConfirm', 'recoverConfirm']
# Buttons whose click only reads, navigates or opens a dialog. Anything else is skipped (see module docstring).
SAFE_TEXT = {'Abrir Motor LLM', 'Configurar provedor e chaves', 'Planejar', 'Estado', 'Árvore', 'Capturar',
             'Revisar', 'Revisar permissões', 'Fechar', 'Close', 'Recomendados', 'Personalizados', 'Carregar mais',
             'Atualizar lista', 'Simular', 'Validar', 'Atualizar', 'Testar leitura', 'Ver em Extensões › Percepção e ação',
             'Ver em Extensões › Plugins'}
SAFE_OBJECTS = {'llmOpenButtonModels', 'llmOpenButton', 'paletteButton'}
# Per-row read-only buttons: skill detail selection, model/connection list refresh and tabs, route planning, dry runs.
SAFE_PREFIXES = ('skillPermissions_', 'skillDryRun_', 'skillValidate', 'modelsTab', 'modelsLoadMore', 'modelsRefresh',
                 'connRefresh_', 'connTest_', 'routePlan_', 'perception_', 'model_')
# Raw or English strings that must not reach the user, plus the labels the spec requires (SINTÉTICO/UNSUPPORTED).
FLAG_RE = re.compile(r'\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b|\b[a-z]+_[a-z_]+\b|\bDEV\b|\bPOC\b|\bUNSUPPORTED\b|\b(?:Ready|Error|Failed|'
                     r'Loading|Pending|Connected|Disconnected|Revoked|Unavailable|Enable|Disable|Save|Cancel|Remove|Install|'
                     r'Sandbox|Replay)\b')


def msg_count():
    collect_messages()
    return len(MESSAGES)


def all_items():
    """Visual tree from the content item and the overlay (dialogs, palette). Delegates are not reachable with findChild."""
    out, stack = [], [window.contentItem(), window.property('overlay')]
    while stack:
        cur = stack.pop()
        if cur is None:
            continue
        out.append(cur)
        stack.extend(cur.childItems())
    return out


def find(name):
    for item in all_items():
        if item.objectName() == name:
            return item
    return None


def eff_visible(item):
    p = item
    while p is not None:
        if not p.isVisible():
            return False
        p = p.parentItem()
    return True


def clipped_ancestor(item):
    p = item.parentItem()
    while p is not None:
        if p.inherits('QQuickFlickable') or p.property('clip') is True:
            return True
        p = p.parentItem()
    return False


def scene_point(item):
    return item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()


def in_window(point):
    return QRect(0, 0, window.width(), window.height()).contains(point)


def settle(ms=900):
    Input.qWait(ms)


def wait_until(cond, seconds):
    until = time.monotonic() + seconds
    while not cond():
        if time.monotonic() > until:
            return False
        Input.qWait(30)
    return True


def is_button(item):
    return item.inherits('QQuickAbstractButton') or 'Button' in item.metaObject().className()


def is_tab(item):
    return item.inherits('QQuickTabButton') or 'TabButton' in item.metaObject().className()


def click(item):
    """Deliver a click to our window: by mouse when the spot is inside the window, else keyboard Space on the focused item."""
    point = scene_point(item)
    if in_window(point):
        Input.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        return 'mouse'
    item.forceActiveFocus()
    Input.keyClick(window, Qt.Key.Key_Space)
    return 'keyboard'


def close_open_dialogs():
    closed = []
    for name in DIALOGS:
        d = window.findChild(QObject, name)
        if d is not None and d.property('visible'):
            Input.keyClick(window, Qt.Key.Key_Escape)
            Input.qWait(250)
            closed.append(name)
    return closed


def geometry_issues():
    issues = []
    bounds = QRectF(0, 0, window.width(), window.height())
    for item in all_items():
        if not eff_visible(item) or item.width() <= 0 or item.height() <= 0:
            continue
        if clipped_ancestor(item):
            continue
        cls = item.metaObject().className()
        r = item.mapRectToScene(QRectF(0, 0, item.width(), item.height()))
        if r.right() > bounds.right() + 2 or r.bottom() > bounds.bottom() + 2 or r.left() < -2 or r.top() < -2:
            if item.inherits('QQuickText') or is_button(item):
                issues.append({'kind': 'outside_window', 'class': cls, 'objectName': item.objectName(),
                               'text': str(item.property('text') or '')[:80]})
        if item.inherits('QQuickText') and str(item.property('text') or '').strip():
            pw, ph = float(item.property('paintedWidth') or 0), float(item.property('paintedHeight') or 0)
            try:
                wrap = int(item.property('wrapMode') or 0)
            except Exception:
                wrap = -1  # enum not convertible in PySide: horizontal check skipped for this item
            if ph > item.height() + 2:
                issues.append({'kind': 'text_clipped_vertical', 'objectName': item.objectName(), 'text': str(item.property('text'))[:80],
                               'painted_h': round(ph), 'h': round(item.height())})
            if wrap == 0 and pw > item.width() + 2:
                issues.append({'kind': 'text_clipped_horizontal', 'objectName': item.objectName(), 'text': str(item.property('text'))[:80],
                               'painted_w': round(pw), 'w': round(item.width())})
    return issues[:60]


def visible_texts():
    texts = []
    for item in all_items():
        if item.inherits('QQuickText') and eff_visible(item):
            t = str(item.property('text') or '').strip()
            if t and t not in texts:
                texts.append(t)
    return texts[:250]


def disabled_buttons():
    out = []
    for item in all_items():
        if is_button(item) and eff_visible(item) and item.property('enabled') is False:
            label = str(item.property('text') or item.objectName() or '')
            if label and label not in out:
                out.append(label)
    return out


def safe_candidates(page_id):
    out = []
    for item in all_items():
        if not (is_button(item) or is_tab(item)) or not eff_visible(item) or item.property('enabled') is False:
            continue
        name = item.objectName()
        if name.startswith(('tab_', 'subtab_')) or name in DIALOGS:
            continue
        text = str(item.property('text') or '')
        if not (is_tab(item) or text in SAFE_TEXT or name in SAFE_OBJECTS or name.startswith(SAFE_PREFIXES)):
            continue
        if not in_window(scene_point(item)):
            continue
        p = scene_point(item)
        out.append((f'{name}|{text}|{p.x()},{p.y()}', item, text or name))
    return out


def skipped_buttons():
    out = []
    for item in all_items():
        if not is_button(item) or not eff_visible(item):
            continue
        text = str(item.property('text') or '')
        if text in SAFE_TEXT or item.objectName() in SAFE_OBJECTS or item.objectName().startswith(SAFE_PREFIXES):
            continue
        label = text or item.objectName() or item.property('objectName')
        if label and label not in out:
            out.append(label + ('' if item.property('enabled') is not False else ' [disabled]'))
    return out[:80]


def go_page(page_id):
    """Open a page the way a user does: its tab (tab_<tab>) when its sub-tab is not in the bar, then the sub-tab (subtab_<page>)."""
    sub = find(f'subtab_{page_id}')
    if sub is None or not eff_visible(sub):
        tab = find(f'tab_{TAB_OF.get(page_id, "")}')
        if tab is None:
            return False
        click(tab)
        settle(450)
        sub = find(f'subtab_{page_id}')
    if sub is None or not eff_visible(sub):
        return False
    click(sub)
    settle(700)
    return window.property('pageId') == page_id


def slug(text):
    table = str.maketrans('áàâãéêíóôõúç ', 'aaaaeeiooouc-')
    return ''.join(ch for ch in text.lower().translate(table) if ch.isalnum() or ch == '-')


def want(label):
    return WANT is None or slug(label) in {slug(t) for t in WANT}


def flagged(texts):
    return [t for t in texts if FLAG_RE.search(t)][:40]


def chat_once():
    """One message to the scripted fake LLM through the page's own input and send button (round 2 allowance)."""
    field, send = find('chatInput'), find('chatSend')
    if field is None or send is None or not eff_visible(field):
        return {'sent': False, 'why': 'chat input or send button not available'}
    field.forceActiveFocus()
    Input.keyClicks(window, 'Oi, teste de exploracao da interface.')
    settle(300)
    if send.property('enabled') is False:  # the send button is enabled only with text (and a usable chat target)
        return {'sent': False, 'why': 'send button disabled after typing', 'input_text': str(field.property('text'))}
    before = msg_count()
    how = click(send)
    settle(2500)
    collect_messages()
    return {'sent': True, 'via': how, 'messages': MESSAGES[before:][:10],
            'state': str(window.property('pageId')), 'chat_state_text': [t for t in visible_texts() if 'Estado' in t or 'Resposta' in t or 'Pensando' in t][:6]}


def shot(name):
    path = out / f'{name}.png'
    window.grabWindow().save(str(path))
    return str(path)


def bridge_state():
    try:
        return {'connected': bridge.connected, 'state': bridge.state, 'result': bridge.result, 'subtitle': bridge.subtitle[:120]}
    except Exception as exc:
        return {'error': repr(exc)}


# ---- 1. connection -----------------------------------------------------------------------------------------------
REPORT['bridge_at_start'] = {'connected': wait_until(lambda: bridge.connected, 12)}
settle(800)
REPORT['window'] = {'width': window.width(), 'height': window.height(), 'minimum': [window.property('minimumWidth'), window.property('minimumHeight')]}
_defs = window.property('pageDefs')
_defs = _defs.toVariant() if hasattr(_defs, 'toVariant') else _defs
PAGE_DEFS = [dict(d) for d in _defs]
TAB_OF = {d['id']: d['tab'] for d in PAGE_DEFS}
PAGES = [(d['id'], d['label']) for d in PAGE_DEFS]
# The pages the Core offers now (the sub-bar lists only the active tab's pages, so the window's list decides).
_offered = window.property('offeredPages')
_offered = _offered.toVariant() if hasattr(_offered, 'toVariant') else _offered
OFFERED = {str(x) for x in _offered}
REPORT['pages_declared'] = [p for _, p in PAGES]
window.requestActivate()
settle(300)

# ---- 2. page sweep (each page through its tab and sub-tab) --------------------------------------------------------
for index, (page_id, label) in enumerate(PAGES):
    if not want(label):
        continue
    page = {'index': index, 'name': label, 'id': page_id, 'visible_in_nav': False, 'reached': False, 'exceptions': [], 'clicks': [],
            'skipped': [], 'disabled': [], 'texts': [], 'geometry': [], 'messages_from': msg_count()}
    REPORT['pages'].append(page)
    page['visible_in_nav'] = page_id in OFFERED
    if not page['visible_in_nav']:
        page['note'] = 'not offered by this Core (sub-tab hidden)'
        continue
    try:
        page['reached'] = go_page(page_id)
        if not page['reached']:
            page['note'] = f"page did not open (pageId={window.property('pageId')}; sub-tab offered: {page['visible_in_nav']})"
            page['messages_to'] = msg_count()
            page['messages'] = MESSAGES[page['messages_from']:page['messages_to']][:60]
            continue
        settle(900)
        page['bridge'] = bridge_state()
        name = f'{index:02d}-{page_id}'
        page['screenshot'] = shot(name)
        page['geometry'] = geometry_issues()
        page['texts'] = visible_texts()
        page['disabled'] = disabled_buttons()
        page['skipped'] = skipped_buttons()
        # Safe clicks, one at a time, re-discovering buttons after each click (layouts change).
        done = set()
        for _ in range(40):
            cands = [c for c in safe_candidates(page_id) if c[0] not in done]
            if not cands:
                break
            key, item, text = cands[0]
            done.add(key)
            before_msgs = msg_count()
            how = click(item)
            settle(800)
            closed = close_open_dialogs()
            collect_messages()
            entry = {'text': text, 'objectName': item.objectName(), 'via': how, 'pageId_after': window.property('pageId'),
                     'closed_dialogs': closed, 'messages': MESSAGES[before_msgs:][:10], 'bridge': bridge_state()}
            page['clicks'].append(entry)
            if window.property('pageId') != page_id:
                go_page(page_id)
                settle(500)
        if page['clicks']:
            page['screenshot_after_clicks'] = shot(f'{name}-after-clicks')
        if page_id == 'conversa' and window.property('pageId') == page_id:
            page['chat'] = chat_once()
            page['screenshot_after_chat'] = shot(f'{name}-after-chat')
        page['geometry_after_clicks'] = geometry_issues()
        page['texts_after_clicks'] = visible_texts()
        page['disabled_after_clicks'] = disabled_buttons()
        page['flagged_texts'] = flagged(page['texts'] + page['texts_after_clicks'])
    except Exception as exc:
        tb = traceback.format_exc()
        page['exceptions'].append(tb)
        EXC.append({'page': label, 'where': 'sweep', 'trace': tb})
    page['messages_to'] = msg_count()
    page['messages'] = MESSAGES[page['messages_from']:page['messages_to']][:60]

# ---- 3. Motor LLM form (Configurações > Privacidade opens it): open, look, close (Escape only; one invalid-character probe, nothing saved)
try:
    if WANT is None or want('Configurações') or want('Privacidade') or want('Motor LLM'):
        if go_page('cfg_privacidade'):
            settle(400)
            llm_open = find('llmOpenButton')
            if llm_open is not None and eff_visible(llm_open):
                click(llm_open)
                llm = window.findChild(QObject, 'llmDialog')
                entry = {'dialog': 'llm', 'opened': wait_until(lambda: llm.property('visible'), 3)}
                settle(600)
                entry['screenshot'] = shot('dialog-llm')
                entry['geometry'] = geometry_issues()
                field = find('llmModel')
                if field is not None and entry['opened']:
                    field.forceActiveFocus()
                    Input.keyClicks(window, '!!')
                    Input.qWait(200)
                    entry['llm_invalid_char_text'] = str(field.property('text'))
                    field.setProperty('text', '')
                    settle(200)
                entry['closed'] = close_open_dialogs()
                REPORT['dialogs'].append(entry)
except Exception:
    tb = traceback.format_exc()
    EXC.append({'where': 'dialogs', 'trace': tb})
    REPORT['dialogs'].append({'error': tb})

# ---- 4. keyboard Tab focus on Hoje ------------------------------------------------------------------------------
try:
    go_page('hoje')
    settle(500)
    window.requestActivate()
    for i in range(8 if WANT is None else 0):
        Input.keyClick(window, Qt.Key.Key_Tab)
        Input.qWait(200)
        focus = window.activeFocusItem()
        REPORT['tab_focus'].append({'press': i + 1, 'objectName': focus.objectName() if focus else None,
                                    'class': focus.metaObject().className() if focus else None,
                                    'text': str(focus.property('text') or '')[:60] if focus else None})
        if i == 3:
            REPORT['tab_focus_screenshot'] = shot('tab-focus-press4')
except Exception:
    EXC.append({'where': 'tab', 'trace': traceback.format_exc()})

# ---- 5. resize: 1000x700 and 600x500 on every offered page (narrow mode below 900 px: icon-only tabs) ------------
for size in ([(900, 700), (600, 500)] if WANT is None else []):
    for index, (page_id, label) in enumerate(PAGES):
        if page_id not in OFFERED:
            continue
        try:
            window.setProperty('width', size[0])
            window.setProperty('height', size[1])
            settle(250)
            go_page(page_id)
            settle(700)
            name = f'{index:02d}-{page_id}-{size[0]}x{size[1]}'
            rec = {'page': label, 'requested': list(size), 'actual': [window.width(), window.height()], 'screenshot': shot(name),
                   'geometry': geometry_issues()}
            REPORT['resize'].append(rec)
        except Exception:
            EXC.append({'where': f'resize {size} {label}', 'trace': traceback.format_exc()})
window.setProperty('width', 1380)
window.setProperty('height', 904)
settle(400)
REPORT['window_end_size'] = [window.width(), window.height()]

# ---- 6. close without crash -----------------------------------------------------------------------------------
try:
    close_result = {'bridge_connected_before_close': bridge.connected}
    window.close()
    Input.qWait(400)
    for w in engine.rootObjects():
        w.close()
        w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    Input.qWait(200)
    close_result['closed'] = True
    REPORT['close'] = close_result
except Exception:
    EXC.append({'where': 'close', 'trace': traceback.format_exc()})
    REPORT['close'] = {'closed': False}
del engine
del bridge

collect_messages()
REPORT['messages_total'] = len(MESSAGES)
REPORT['messages_by_type'] = {k: sum(1 for m in MESSAGES if m['type'] == k) for k in sorted({m['type'] for m in MESSAGES})}
REPORT['messages'] = MESSAGES[:300]
REPORT['finished'] = time.strftime('%Y-%m-%d %H:%M:%S')
(out / 'report.json').write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')

visited = [p['name'] for p in REPORT['pages'] if p.get('reached')]
print(f"platform={REPORT['platform']} pages_visited={len(visited)} of {len(PAGES)}")
print('visited:', ', '.join(visited))
print(f"messages(warning/critical/fatal)={len(MESSAGES)} exceptions={len(EXC)}")
geo = [(p['name'], g) for p in REPORT['pages'] for g in (p.get('geometry') or [])]
print(f"geometry issues on pages={len(geo)} resize_records={len(REPORT['resize'])}")
print('report:', out / 'report.json')
sys.stdout.flush()
os._exit(0 if not EXC else 3)
