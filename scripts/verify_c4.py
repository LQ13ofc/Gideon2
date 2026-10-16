#!/usr/bin/env python3
"""Private real Core C4 gate (docs/C4.md "Gates"): the six C4 plugins through the real Hub, real capability
invocations, the synthetic world (`<BASE>/synthetic/world.json`, read as a file for every verification), the
S3 final agent scenario with the scripted fake LLM (llm_engine, plugin settings `agent_script`), the loopback
fake provider for the key-leak boundary, and the Qt offscreen perception phase. Writes target/evidence/c4.json.

Boots (one Core root each; the synthetic world is reset before every boot):
  P1..P6   one per plugin: Hub staging refused before approval, install refused before approval, enable
           refused before install, approval, install, enable, capability checks against world.json, S1
           native regression, revoke (capability gone), uninstall (hub_remove), S1 again, clean shutdown.
  NOFLAG   without --agent-synthetic: a host service of screen_observe answers unknown_service.
  DENY     catalog variant whose manifests declare no permission (the approval is then empty): every host
           service answers permission_denied with no effect, display_manipulate.status needs no grant.
  S3       --agent-synthetic with llm_engine, screen_observe, computer_control: agent tools screen_capture
           and ui_click (approval through tool_decide): happy path, abort, provider errors, key leak scan,
           and last the mid-run plugin revoke (permission_revoked).
  QT       --agent-synthetic with all six plugins, no voice replay: test_ui_offscreen.py --phase perception.

Preconditions use need(); a false one stops the scenario and is recorded as a failure. Nothing is faked
inside the Core. The only fakes are the scripted LLM steps (never a provider) and the loopback provider.
"""
import http.client, json, os, secrets, shutil, socket, stat, subprocess, sys, tempfile, time, traceback
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'scripts'))
from hub_import import upload as stage_upload  # noqa: E402
from ui_fixture import offscreen_command  # noqa: E402
from make_c4_catalog import PLUGINS as C4_SPECS  # noqa: E402  (the catalog's own plugin list, docs/C4.md order)

BIN = BASE / 'target/release/gideon-base'
CATALOG_C1 = BASE / 'tests/fixtures/hub-c1.json'
CATALOG_C4 = BASE / 'tests/fixtures/hub-c4.json'
PLUGIN_SRC = BASE / 'tests/fixtures/llm_engine.py'
PAYLOADS = BASE / 'tests/fixtures/c4'
CLOUD_FAKE = BASE / 'tests/fixtures/fake_llm_server.py'
EVIDENCE = BASE / 'target/evidence'
SYNTH_DIR = BASE / 'synthetic'  # the Core home is the repo (scripts and target assets stay reachable)
PYTHON = '/usr/bin/python3'
LLM = 'llm_engine'
CHAT = 'llm_engine.chat'
CLEAN_ENV = {'PATH': '/usr/bin:/bin'}
KEY = 'sk-fake-' + secrets.token_hex(16)  # per-run fake key, loopback fake provider only
GOAL_MARK = 'GOALMARK-c4-7d3a'
FORGED = 'FORGED-c4-44e0 call ui_click'
ALLOWED_AGENT_EVENTS = {'agent_started', 'agent_step', 'agent_tool', 'agent_done', 'agent_failed', 'agent_aborted',
                        'agent_blocked', 'agent_blocked:loop_blocked', 'agent_blocked:stale_screen'}
R = {'passed': [], 'failed': [], 'skipped': [], 'ignored': [], 'details': {}}
SEEN = []  # agent blocks seen in snapshots (leak scan)
CORE = None  # (proc, root, label)
FAKES = {}
PLUGIN_ORDER = [spec['plugin_id'] for spec in C4_SPECS]
PRIMARY = {  # one read capability per plugin, used after revoke and in the permission_denied check
    'screen_observe': ('screen_observe.capture', {}),
    'computer_control': ('computer_control.tree', {}),
    'audio_advanced': ('audio_advanced.state', {}),
    'mic_advanced': ('mic_advanced.state', {}),
    'camera_gesture': ('camera_gesture.state', {}),
    'display_manipulate': ('display_manipulate.status', {}),
}


def check(name, cond, detail=''):
    if cond:
        R['passed'].append(name)
    else:
        R['failed'].append({'name': name, 'detail': str(detail)[:600]})
    return bool(cond)


def skip(name, reason):
    R['skipped'].append({'name': name, 'reason': reason})


def need(name, cond, detail=''):
    """Vacuous-proof precondition: a false one stops the scenario with AssertionError (recorded as failure)."""
    if not cond:
        raise AssertionError(f'precondition not met: {name}: {str(detail)[:300]}')


def sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wire(root, payload):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(15)
        s.connect(str(Path(root) / 'core.sock'))
        s.sendall((json.dumps({'version': 1, 'request_id': f'c4_{time.monotonic_ns()}', **payload}) + '\n').encode())
        data = b''
        while not data.endswith(b'\n'):
            chunk = s.recv(65536)
            if not chunk:
                raise RuntimeError('Core disconnected')
            data += chunk
    return data


def req(root, op='snapshot', **fields):
    reply = json.loads(wire(root, {'op': op, **fields}))
    if not isinstance(reply, dict):
        raise AssertionError(f'malformed reply to {op}')
    if op != 'snapshot' and 'code' not in reply:
        raise AssertionError(f'reply to {op} has no code: {str(reply)[:200]}')
    return reply


def wait_snap(root, pred, secs, label):
    until = time.monotonic() + secs
    while True:
        s = req(root)
        if pred(s):
            return s
        if time.monotonic() > until:
            raise TimeoutError(label)
        time.sleep(0.02)


def item(s, pid):
    return next((i for i in s['plugins']['items'] if i['plugin_id'] == pid), None)


def entry(h, pid):
    return next((e for e in h['entries'] if e['plugin_id'] == pid), None)


def installed(s, pid):
    return any(i['plugin_id'] == pid for i in s['hub'].get('installed') or [])


def approve(root, pid):
    h = req(root)['hub']
    e = entry(h, pid)
    return req(root, 'hub_approve', revision=h['approval_revision'], plugin_id=pid,
               manifest_sha256=e['manifest_sha256'], permissions=e['permissions'], publisher_unverified_ack=True)


def install(root, pid):
    h = req(root)['hub']
    return req(root, 'hub_install', revision=h['install_revision'], plugin_id=pid,
               manifest_sha256=entry(h, pid)['manifest_sha256'])


def plugin_op(root, name, pid):
    return req(root, name, revision=req(root)['plugins']['revision'], plugin_id=pid)


def wait_running(root, pid, secs=15):
    return wait_snap(root, lambda s: item(s, pid) is not None and item(s, pid)['state'] == 'running', secs,
                     f'{pid} running')


def call_cap(root, cap, inp, secs=15):
    """Real capability_invoke. Returns the invoke code, or the CapabilityResult of this call (ok, output, error)."""
    reply = req(root, 'capability_invoke', capability=cap, input=inp, deadline_ms=5000)
    if reply['code'] != 'ok':
        return {'invoke': reply['code']}
    s = wait_snap(root, lambda s: s.get('capability_result') is not None
                  and s['capability_result']['capability'] == cap, secs, f'result of {cap}')
    return s['capability_result']


def world_bytes():
    path = SYNTH_DIR / 'world.json'
    return path.read_bytes() if path.exists() else None


# The Core creates world.json on its first write; until then it reads the default world of src/world.rs
# (`impl Default for World`, same field order, so canonical digests agree). Once the file exists it is the truth.
DEFAULT_WORLD = {
    'version': 1,
    'app': {'epoch': 1, 'counter': 0, 'text': '', 'published': False},
    'screen': {'epoch': 1, 'width': 1280, 'height': 720,
               'windows': [{'id': 'main', 'title': 'Janela sintetica', 'focused': True}],
               'elements': [{'id': 'field', 'role': 'textbox', 'name': 'Campo', 'x': 40, 'y': 40},
                            {'id': 'apply', 'role': 'button', 'name': 'Aplicar', 'x': 40, 'y': 100},
                            {'id': 'cancel', 'role': 'button', 'name': 'Cancelar', 'x': 160, 'y': 100}],
               'focus': None, 'text': '', 'last_click': None, 'last_key': None},
    'audio': {'routes': ['speakers', 'headphones', 'bluetooth'], 'route': 'speakers',
              'apps': [{'id': 'player', 'volume': 50}, {'id': 'browser', 'volume': 50}],
              'eq': 'flat', 'denoise': False},
    'mic': {'device': 'synthetic-mic', 'gain': 50, 'filter': 'off', 'monitor': False, 'recording': False,
            'indicator': False},
    'camera': {'opt_in': False, 'indicator': False, 'frame_seq': 0, 'gesture': None},
    'base': {'mic_state': 'base-idle', 'speaker_state': 'base-idle'},
}


def world():
    raw = world_bytes()
    return json.loads(raw) if raw is not None else json.loads(json.dumps(DEFAULT_WORLD))


def canon(obj):
    return json.dumps(obj, separators=(',', ':'), ensure_ascii=False)


def step(text='', calls=(), **extra):
    return {'text': text, 'tool_calls': [{'id': cid, 'name': name, 'arguments': args} for cid, name, args in calls],
            **extra}


def write_script(root, script):
    """Plugin settings (0600 file in a 0700 dir under the Core root). None removes the script entry."""
    settings = Path(root) / 'plugin-settings'
    path = settings / f'{LLM}.json'
    if script is None:
        path.unlink(missing_ok=True)
        return
    settings.mkdir(exist_ok=True)
    os.chmod(settings, 0o700)
    path.unlink(missing_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(json.dumps({'version': 1, 'data': {'agent_script': script}}).encode())
    os.chmod(path, 0o600)


def load_script(root, steps):
    """Writes the scripted steps and restarts the LLM plugin so its cursor starts at step 1."""
    write_script(root, {'steps': steps})
    restart_llm(root)


def restart_llm(root):
    if item(req(root), LLM)['enabled']:
        code = plugin_op(root, 'plugin_disable', LLM)['code']
        need('llm disable ok', code == 'ok', code)
        wait_snap(root, lambda s: not item(s, LLM)['enabled'], 15, 'llm disabled')
    code = plugin_op(root, 'plugin_enable', LLM)['code']
    need('llm enable ok', code == 'ok', code)
    wait_running(root, LLM)


# ---- agent helpers (same contract as verify_c3_agent.py) -------------------
def agent_start(root, goal):
    before = (req(root).get('agent') or {}).get('run_id')
    code = req(root, 'agent_start', goal=goal)['code']
    if code != 'ok':
        return code, None
    s = wait_snap(root, lambda s: s.get('agent') is not None and s['agent']['run_id'] != before, 10, 'new run')
    return code, s['agent']['run_id']


def wait_agent(root, pred, secs, label, trace=None):
    def ok(s):
        if s.get('agent') is not None and trace is not None and (not trace or trace[-1] != s['agent']['state']):
            trace.append(s['agent']['state'])
        return s.get('agent') is not None and pred(s['agent'])
    return wait_snap(root, ok, secs, label)


def run_props(s, rid):
    return [p for p in s['tool_proposals'] if p.get('run_id') == rid]


def pending_of(s, rid):
    return next(p for p in run_props(s, rid) if p['state'] == 'pending')


def steps_of(agent, kind=None):
    return [st for st in agent['steps'] if kind is None or st['kind'] == kind]


def kinds_of(agent):
    return [st['kind'] for st in agent['steps']]


def block_clean(agent, label):
    text = json.dumps(agent, ensure_ascii=False)
    SEEN.append(text)
    bad = [m for m in (GOAL_MARK, FORGED, KEY, 'tool_output', 'arguments', 'regions') if m in text]
    check(f'{label}: agent block carries no goal, forged text, key, observation or args',
          not bad, {'bad': bad})


def events_of(s, kind):
    return [e for e in s.get('events') or [] if e.get('kind') == kind]


# ---- Core -------------------------------------------------------------------
def merged_catalog(td, name, variant=False):
    """One catalog for the Core: the LLM plugin (hub-c1) and the six C4 plugins (hub-c4). `variant` declares no
    permission in any C4 manifest, so an approval grants nothing and every host service is permission_denied."""
    c1 = json.loads(CATALOG_C1.read_text(encoding='utf-8'))
    c4 = json.loads(CATALOG_C4.read_text(encoding='utf-8'))
    need('catalogs share repository and version', c1['repository'] == c4['repository'] and c1['version'] == c4['version'])
    plugins = json.loads(json.dumps(c1['plugins'] + c4['plugins']))
    if variant:
        for plugin in plugins:
            if plugin['plugin_id'] in PLUGIN_ORDER:
                plugin['permissions'] = []
    cat = {'version': c4['version'], 'repository': c4['repository'], 'plugins': plugins}
    path = Path(td) / f'{name}.json'
    path.write_text(json.dumps(cat, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return str(path), sha(path)


def core_args(root, catalog, extra, replay=True):
    base = [str(BIN), '--root', str(root), '--home', str(BASE), '--commands-sandbox', '--hub-catalog', catalog[0],
            catalog[1], '--plugin-python', PYTHON, '--net-allow-loopback']
    if not replay:  # no voice: the chat and agent controls stay visible in the Qt phase
        return base + list(extra)
    manifest = BASE / 'target/a3-assets/replay-manifest.json'
    index = next(i for i, r in enumerate(json.loads(manifest.read_text())['fixtures'])
                 if r['id'] == 'wake-hey-brave__bf_emma__clean')
    return base + ['--base-pack', str(BASE / 'target/base-pack-dev.json'),
                   '--tts-virtual', str(BASE / 'target/tts-venv/bin/python'), str(BASE / 'target/a5-assets/manifest.json'),
                   '--wake-replay', str(BASE / 'target/a1-venv/bin/python'), str(manifest), str(index), *extra]


def boot(td, label, catalog, extra, replay=True):
    global CORE
    root = Path(td) / label / 'core'
    root.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(SYNTH_DIR, ignore_errors=True)  # a fresh synthetic world for every boot
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(Path(td) / label), 'XDG_CONFIG_HOME': str(Path(td) / label),
           'XDG_DATA_HOME': str(Path(td) / label), 'XDG_CACHE_HOME': str(Path(td) / label),
           'XDG_RUNTIME_DIR': str(Path(td) / label)}
    log = open(Path(td) / label / 'core.stderr', 'wb')
    proc = subprocess.Popen(core_args(root, catalog, extra, replay), env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=log)
    CORE = (proc, root, label)
    until = time.monotonic() + 15
    while True:
        try:
            req(root)
            break
        except (OSError, RuntimeError, ValueError):
            pass
        if proc.poll() is not None:
            raise RuntimeError(f'Core {label} exited early rc={proc.returncode}')
        if time.monotonic() > until:
            raise TimeoutError(f'Core {label} startup')
        time.sleep(0.02)
    return root


def proc_table():
    out = {}
    for name in os.listdir('/proc'):
        if not name.isdigit():
            continue
        try:
            with open(f'/proc/{name}/stat', 'rb') as f:
                fields = f.read().decode(errors='replace').rsplit(')', 1)[1].split()
            with open(f'/proc/{name}/cmdline', 'rb') as f:
                argv = f.read()
            out[int(name)] = (int(fields[1]), fields[0], argv)
        except (OSError, IndexError):
            continue
    return out


def stop_core(label):
    global CORE
    proc, _, _ = CORE
    table = proc_table()
    children = {}
    for p, (pp, _, _) in table.items():
        children.setdefault(pp, []).append(p)
    found, todo = [], [proc.pid]
    while todo:
        for child in children.get(todo.pop(), []):
            found.append(child)
            todo.append(child)
    pids = [p for p in found if p in table and table[p][1] != 'Z'
            and any(m in table[p][2] for m in (b'/plugin/main.py', b'net_broker.py', b'llm_engine', b'/plugins/'))]
    proc.terminate()
    rc = proc.wait(timeout=15)
    CORE = None
    check(f'{label}: Core clean shutdown rc 0', rc == 0, f'rc={rc}')
    left = [p for p in pids if os.path.exists(f'/proc/{p}') and proc_table().get(p, (0, 'Z', b''))[1] != 'Z']
    check(f'{label}: no plugin or broker process left after shutdown', not left, left)


def native_check(root, label):
    until = time.monotonic() + 30
    while True:
        s = req(root)
        if s['state'] == 'idle' and s['command'] is not None and s['command'].get('code') == 'command_success' \
                and s.get('wake_status') == 'replay_finished':
            break
        if time.monotonic() > until:
            check(label, False, 'no S1 success')
            return
        time.sleep(0.015)
    check(label, bool(s['command']['receipt']['verified']))


class Fake:
    """Loopback fake OpenAI-shaped provider (tests/fixtures/fake_llm_server.py); never a real provider."""

    def __init__(self, src):
        self.proc = subprocess.Popen([PYTHON, '-I', str(src), '--port', '0'], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=CLEAN_ENV, cwd='/')
        self.port = int(self.proc.stdout.readline())

    def v1(self):
        return f'http://127.0.0.1:{self.port}/v1'

    def close(self):
        self.proc.terminate()
        self.proc.wait(timeout=5)


# ---- Hub lifecycle common to the six plugins ---------------------------------
def lifecycle_in(root, pid, td):
    """Staging, install and enable before approval are refused; then approve, install, enable."""
    try:
        stage_upload(str(root), pid, str(PAYLOADS / f'{pid}.py'))
        staged = 'ok'
    except RuntimeError as exc:
        staged = str(exc)
    check(f'{pid}: payload staging refused before approval', staged != 'ok', staged)
    inst = install(root, pid)
    check(f'{pid}: install refused before approval (code {inst["code"]})', inst['code'] != 'ok', inst['code'])
    enabled = plugin_op(root, 'plugin_enable', pid)
    check(f'{pid}: enable refused before install (code {enabled["code"]})', enabled['code'] != 'ok', enabled['code'])
    appr = approve(root, pid)
    check(f'{pid}: approve manifest permissions ok', appr['code'] == 'ok', appr.get('code'))
    stage_upload(str(root), pid, str(PAYLOADS / f'{pid}.py'))
    inst = install(root, pid)
    check(f'{pid}: installed after approval', inst['code'] == 'ok', inst.get('code'))
    enabled = plugin_op(root, 'plugin_enable', pid)
    check(f'{pid}: enable ok after install', enabled['code'] == 'ok', enabled.get('code'))
    wait_running(root, pid)


def install_all(root, specs_pids):
    for pid in specs_pids:
        approve(root, pid)
        stage_upload(str(root), pid, str(PAYLOADS / f'{pid}.py'))
        need(f'{pid} install', install(root, pid)['code'] == 'ok')
        need(f'{pid} enable', plugin_op(root, 'plugin_enable', pid)['code'] == 'ok')
        wait_running(root, pid)


# ---- per-plugin checks against world.json -----------------------------------
def check_screen(root):
    w0 = world()
    st = call_cap(root, 'screen_observe.status', {})
    check('C4.1 status: UNSUPPORTED real backend, reason needs_human_validation, backend synthetic',
          st.get('ok') and st['output'] == {'backend': 'synthetic', 'real_backend': 'unsupported',
                                            'reason': 'needs_human_validation'}, st)
    cap = call_cap(root, 'screen_observe.capture', {})
    out = cap.get('output') or {}
    scr = w0['screen']
    check('C4.1 capture ok with epoch, size and a 64-hex sha256 from the Core',
          cap.get('ok') and out.get('epoch') == scr['epoch'] and out.get('width') == scr['width']
          and out.get('height') == scr['height'] and len(out.get('sha256', '')) == 64, cap)
    expected = [{'role': e['role'], 'name': e['name'], 'x': e['x'], 'y': e['y']} for e in scr['elements']]
    check('C4.1 regions equal the elements in world.json', out.get('regions') == expected, out.get('regions'))
    import hashlib
    digest = sha(SYNTH_DIR / 'world.json') if (SYNTH_DIR / 'world.json').exists() else 'absent (default world)'
    screen_hash = hashlib.sha256(canon(scr).encode()).hexdigest()
    check('C4.1 sha256 is the digest of the screen object in world.json (canonical form)',
          out.get('sha256') == screen_hash, {'capture': out.get('sha256'), 'world_screen': screen_hash,
                                              'world_file': digest})
    check('C4.1 output carries the backend synthetic and no screenshot bytes',
          out.get('backend') == 'synthetic' and not any(k in out for k in ('pixels', 'image', 'png')), out)
    s = req(root)
    audit = events_of(s, 'screen_capture')
    check('C4.1 audit has screen_capture with no content', audit and all(
        set(e) <= {'sequence', 'request_id', 'session_id', 'kind'} for e in audit), audit[-2:] if audit else s.get('events'))
    check('C4.1 capture left world.json unchanged', world() == w0)
    R['details']['screen_observe'] = {'regions': len(out.get('regions') or []), 'epoch': out.get('epoch')}


def check_control(root):
    w0 = world()
    tree = call_cap(root, 'computer_control.tree', {})
    out = tree.get('output') or {}
    expected = [{'id': e['id'], 'role': e['role'], 'name': e['name'], 'x': e['x'], 'y': e['y'], 'focused': False}
                for e in w0['screen']['elements']]
    check('C4.2 a11y tree first: elements from world.json, focused flags, fresh epoch',
          tree.get('ok') and out.get('elements') == expected and out.get('epoch') == w0['screen']['epoch'], tree)
    click = call_cap(root, 'computer_control.act', {'kind': 'click', 'epoch': 1, 'element': 'apply'})
    out = click.get('output') or {}
    w1 = world()
    check('C4.2 click with the fresh epoch verified (epoch 1 -> 2, last_click apply in world.json)',
          click.get('ok') and out.get('verified') is True and out.get('epoch') == 2 and w1['screen']['epoch'] == 2
          and w1['screen']['last_click'] == 'apply', click)
    before_stale = world_bytes()
    stale = call_cap(root, 'computer_control.act', {'kind': 'click', 'epoch': 1, 'element': 'cancel'})
    check('C4.2 stale epoch refused with stale_screen and no effect on world.json',
          stale.get('ok') is False and stale.get('error') == 'stale_screen' and world_bytes() == before_stale, stale)
    tree = call_cap(root, 'computer_control.tree', {})
    check('C4.2 re-read tree gives the epoch the next action must carry (2)', tree.get('output', {}).get('epoch') == 2, tree)
    focus = call_cap(root, 'computer_control.act', {'kind': 'focus', 'epoch': 2, 'element': 'field'})
    check('C4.2 focus verified by the re-read tree (focused true)', focus.get('output', {}).get('verified') is True, focus)
    typed = call_cap(root, 'computer_control.act', {'kind': 'type', 'epoch': 3, 'text': 'ola'})
    check('C4.2 type verified (epoch advanced) and text in world.json',
          typed.get('output', {}).get('verified') is True and world()['screen']['text'] == 'ola', typed)
    call_cap(root, 'computer_control.act', {'kind': 'focus', 'epoch': 4, 'element': 'apply'})
    nofocus = call_cap(root, 'computer_control.act', {'kind': 'type', 'epoch': 5, 'text': 'x'})
    check('C4.2 type without a focused textbox refused with no_focus, text unchanged',
          nofocus.get('error') == 'no_focus' and world()['screen']['text'] == 'ola', nofocus)
    key = call_cap(root, 'computer_control.act', {'kind': 'key', 'epoch': 5, 'key': 'enter'})
    check('C4.2 key verified and last_key enter in world.json',
          key.get('output', {}).get('verified') is True and world()['screen']['last_key'] == 'enter', key)
    bad = call_cap(root, 'computer_control.act', {'kind': 'key', 'epoch': 6, 'key': 'Enter'})
    check('C4.2 key outside the fixed list refused as invalid_input', bad.get('error') == 'invalid_input', bad)
    R['details']['computer_control'] = {'epoch_after': world()['screen']['epoch']}


def check_audio(root):
    w0 = world()
    st = call_cap(root, 'audio_advanced.state', {})
    out = st.get('output') or {}
    audio = w0['audio']
    expected_routes = [{'id': r, 'active': r == audio['route']} for r in audio['routes']]
    check('C4.3 state mirrors world.json audio (routes with active flag, apps, eq, denoise)',
          st.get('ok') and out.get('routes') == expected_routes and out.get('apps') == [
              {'id': a['id'], 'volume': a['volume']} for a in audio['apps']] and out.get('eq') == audio['eq']
          and out.get('denoise') is audio['denoise'], st)
    route = call_cap(root, 'audio_advanced.act', {'kind': 'route', 'route': 'headphones'})
    check('C4.3 route change verified; world.json audio.route headphones',
          route.get('output', {}).get('verified') is True and world()['audio']['route'] == 'headphones', route)
    unknown = call_cap(root, 'audio_advanced.act', {'kind': 'route', 'route': 'nope'})
    check('C4.3 unknown route refused as unknown_route, no effect',
          unknown.get('error') == 'unknown_route' and world()['audio']['route'] == 'headphones', unknown)
    vol = call_cap(root, 'audio_advanced.act', {'kind': 'app_volume', 'app': 'player', 'volume': 80})
    check('C4.3 app volume verified; world.json apps player 80',
          vol.get('output', {}).get('verified') is True and any(
              a['id'] == 'player' and a['volume'] == 80 for a in world()['audio']['apps']), vol)
    over = call_cap(root, 'audio_advanced.act', {'kind': 'app_volume', 'app': 'player', 'volume': 101})
    check('C4.3 volume above 100 refused as invalid_input', over.get('error') == 'invalid_input', over)
    eq = call_cap(root, 'audio_advanced.act', {'kind': 'eq', 'preset': 'music'})
    check('C4.3 eq preset from the fixed list verified; world.json eq music',
          eq.get('output', {}).get('verified') is True and world()['audio']['eq'] == 'music', eq)
    badeq = call_cap(root, 'audio_advanced.act', {'kind': 'eq', 'preset': 'treble'})
    check('C4.3 eq preset outside the list refused as invalid_input', badeq.get('error') == 'invalid_input', badeq)
    dn = call_cap(root, 'audio_advanced.act', {'kind': 'denoise', 'enabled': True})
    check('C4.3 denoise verified; world.json denoise true',
          dn.get('output', {}).get('verified') is True and world()['audio']['denoise'] is True, dn)
    w1 = world()
    check('C4.3 base sentinel intact (base.* unchanged, mic unchanged)',
          w1['base'] == w0['base'] and w1['mic'] == w0['mic'] and w1['base'] == {
              'mic_state': 'base-idle', 'speaker_state': 'base-idle'}, w1['base'])
    R['details']['audio_advanced'] = {'route': w1['audio']['route'], 'eq': w1['audio']['eq']}


def check_mic(root):
    w0 = world()
    st = call_cap(root, 'mic_advanced.state', {})
    check('C4.4 state equals world.json mic view (indicator off, not recording)',
          st.get('ok') and st['output'].get('indicator') is False and st['output'].get('recording') is False
          and st['output'].get('device') == w0['mic']['device'], st)
    rec = call_cap(root, 'mic_advanced.record', {'action': 'start'})
    check('C4.4 record start refused without indicator (indicator_off), nothing recorded',
          rec.get('error') == 'indicator_off' and world()['mic']['recording'] is False, rec)
    mon = call_cap(root, 'mic_advanced.monitor', {'enabled': True})
    check('C4.4 monitor on verified; privacy indicator on in world.json',
          mon.get('output', {}).get('verified') is True and world()['mic']['indicator'] is True, mon)
    rec = call_cap(root, 'mic_advanced.record', {'action': 'start'})
    check('C4.4 explicit record start with the indicator on verified (recording and indicator true)',
          rec.get('output', {}).get('verified') is True and world()['mic']['recording'] is True
          and world()['mic']['indicator'] is True, rec)
    again = call_cap(root, 'mic_advanced.record', {'action': 'start'})
    check('C4.4 second start refused as already_recording', again.get('error') == 'already_recording', again)
    conf = call_cap(root, 'mic_advanced.configure', {'gain': 70, 'filter': 'voice'})
    check('C4.4 configure verified in world.json (gain 70, filter voice)',
          conf.get('output', {}).get('verified') is True and world()['mic']['gain'] == 70
          and world()['mic']['filter'] == 'voice', conf)
    badf = call_cap(root, 'mic_advanced.configure', {'filter': 'noise_gate'})
    check('C4.4 filter outside the fixed list refused as invalid_input', badf.get('error') == 'invalid_input', badf)
    off = call_cap(root, 'mic_advanced.monitor', {'enabled': False})
    check('C4.4 leaving monitor while recording keeps the indicator on',
          off.get('output', {}).get('verified') is True and world()['mic']['indicator'] is True, off)
    stop = call_cap(root, 'mic_advanced.record', {'action': 'stop'})
    m = world()['mic']
    check('C4.4 stop verified: not recording and indicator off in world.json',
          stop.get('output', {}).get('verified') is True and m['recording'] is False and m['indicator'] is False, stop)
    nostop = call_cap(root, 'mic_advanced.record', {'action': 'stop'})
    check('C4.4 stop when not recording refused as not_recording', nostop.get('error') == 'not_recording', nostop)
    check('C4.4 base sentinel intact', world()['base'] == w0['base'], world()['base'])


def check_camera(root):
    st = call_cap(root, 'camera_gesture.state', {})
    check('C4.5 default opt-in off: opt_in false, indicator false',
          st.get('ok') and st['output'].get('opt_in') is False and st['output'].get('indicator') is False, st)
    cap = call_cap(root, 'camera_gesture.capture', {})
    check('C4.5 capture without opt-in refused as opt_in_required', cap.get('error') == 'opt_in_required', cap)
    ges = call_cap(root, 'camera_gesture.gestures', {})
    check('C4.5 gestures without opt-in refused as opt_in_required', ges.get('error') == 'opt_in_required', ges)
    check('C4.5 refused calls changed nothing (frame_seq 0)', world()['camera']['frame_seq'] == 0, world()['camera'])
    on = call_cap(root, 'camera_gesture.optin', {'enabled': True})
    check('C4.5 opt-in on verified; privacy indicator on in world.json',
          on.get('output', {}).get('verified') is True and world()['camera']['indicator'] is True, on)
    cap = call_cap(root, 'camera_gesture.capture', {})
    out = cap.get('output') or {}
    check('C4.5 capture ok after opt-in: frame counter 1, counters only (no pixels)',
          cap.get('ok') and out.get('frame_seq') == 1 and out.get('indicator') is True
          and not any(k in out for k in ('pixels', 'image', 'frame')), cap)
    ges = call_cap(root, 'camera_gesture.gestures', {})
    check('C4.5 gestures listed after opt-in', ges.get('ok') and ges['output'].get('gestures') == ['wave', 'thumbs_up'], ges)
    off = call_cap(root, 'camera_gesture.optin', {'enabled': False})
    cam = world()['camera']
    check('C4.5 opt-out verified and clears frames and gesture in world.json',
          off.get('output', {}).get('verified') is True and cam['opt_in'] is False and cam['indicator'] is False
          and cam['frame_seq'] == 0 and cam['gesture'] is None, cam)
    R['details']['camera_gesture'] = {'opt_in_default': False}


def check_display(root):
    st = call_cap(root, 'display_manipulate.status', {})
    expected = {'supported': False, 'state': 'UNSUPPORTED', 'reason': 'no_compositor_api_in_environment',
                'note': 'overlay/captura não é manipulação de saída'}
    check('C4.6 status is exactly UNSUPPORTED (no compositor API in this environment)',
          st.get('ok') and st.get('output') == expected, st)
    s = req(root)
    caps = item(s, 'display_manipulate')['capabilities']
    check('C4.6 only display_manipulate.status is declared', caps == ['display_manipulate.status'], caps)
    nothing = [call_cap(root, c, {})['invoke'] for c in ('display_manipulate.act', 'display_manipulate.capture')]
    check('C4.6 nothing else callable (unknown_capability for act and capture)',
          all(code == 'unknown_capability' for code in nothing), nothing)


CHECKS = {'screen_observe': check_screen, 'computer_control': check_control, 'audio_advanced': check_audio,
          'mic_advanced': check_mic, 'camera_gesture': check_camera, 'display_manipulate': check_display}


# ---- scenarios -------------------------------------------------------------
def run_plugin(td, pid):
    """One plugin, its own Core root: lifecycle, real capability checks, revoke, uninstall, S1 regression."""
    root = boot(td, f'p-{pid}', MERGED, ['--agent-synthetic'])
    lifecycle_in(root, pid, td)
    CHECKS[pid](root)
    cap, inp = PRIMARY[pid]
    rev = plugin_op(root, 'plugin_revoke', pid)
    check(f'{pid}: plugin_revoke ok', rev['code'] == 'ok', rev.get('code'))
    gone = call_cap(root, cap, inp)
    check(f'{pid}: revoke => capability {cap} disappears (not invocable)', gone.get('invoke') is not None
          and gone['invoke'] != 'ok', gone)
    check(f'{pid}: plugin not running after revoke', item(req(root), pid) is None
          or item(req(root), pid)['state'] != 'running', item(req(root), pid))
    un = req(root, 'hub_remove', revision=req(root)['hub']['install_revision'], plugin_id=pid)
    check(f'{pid}: uninstall (hub_remove) ok', un['code'] == 'ok', un.get('code'))
    check(f'{pid}: not installed after uninstall', not installed(req(root), pid), req(root)['hub'].get('installed'))
    native_check(root, f'{pid}: S1 native regression after uninstall')
    stop_core(f'p-{pid}')


def run_noflag(td):
    root = boot(td, 'noflag', MERGED, [])
    approve(root, 'screen_observe')
    stage_upload(str(root), 'screen_observe', str(PAYLOADS / 'screen_observe.py'))
    need('noflag install', install(root, 'screen_observe')['code'] == 'ok')
    need('noflag enable', plugin_op(root, 'plugin_enable', 'screen_observe')['code'] == 'ok')
    wait_running(root, 'screen_observe')
    res = call_cap(root, 'screen_observe.capture', {})
    check('no flag: the host service does not exist (capture answers unknown_service)', res.get('error') == 'unknown_service', res)
    chat_tools = call_cap(root, 'screen_observe.status', {})
    check('no flag: status still answers (no host call)', chat_tools.get('ok') is True, chat_tools)
    native_check(root, 'NOFLAG: S1 native regression')
    stop_core('noflag')


def run_deny(td):
    root = boot(td, 'deny', DENY_CATALOG, ['--agent-synthetic'])
    install_all(root, PLUGIN_ORDER)
    before = world_bytes()
    for pid, (cap, inp) in ((pid, PRIMARY[pid]) for pid in ('screen_observe', 'computer_control', 'audio_advanced',
                                                              'mic_advanced', 'camera_gesture')):
        res = call_cap(root, cap, inp)
        check(f'{pid}: without the approved grant the host service answers permission_denied ({cap})',
              res.get('ok') is False and res.get('error') == 'permission_denied', res)
    res = call_cap(root, 'computer_control.act', {'kind': 'click', 'epoch': 1, 'element': 'apply'})
    check('computer_control: act without grant is permission_denied, world untouched',
          res.get('error') == 'permission_denied' and world_bytes() == before, res)
    res = call_cap(root, 'mic_advanced.record', {'action': 'start'})
    check('mic_advanced: record start without grant is permission_denied', res.get('error') == 'permission_denied', res)
    st = call_cap(root, 'display_manipulate.status', {})
    check('display_manipulate: status needs no grant (no host call) and stays UNSUPPORTED',
          st.get('ok') and st['output']['state'] == 'UNSUPPORTED', st)
    native_check(root, 'DENY: S1 native regression')
    stop_core('deny')


def agent_scenarios_s3(root, cloud_url):
    """S3 final: scripted LLM conversation through agent tools screen_capture + ui_click (approval through tool_decide)."""
    # A. happy path: screen_capture (read) then ui_click (state changing, approved) then the answer.
    reset = world_bytes()
    load_script(root, [step(calls=[('r1', 'screen_capture', {})]),
                       step(calls=[('c1', 'ui_click', {'epoch': 1, 'element': 'apply'})]),
                       step(text='Clique concluído.')])
    trace = []
    code, rid = agent_start(root, f'Clique em aplicar {GOAL_MARK}')
    check('S3 happy: agent_start ok', code == 'ok', code)
    s = wait_agent(root, lambda a: a['state'] == 'awaiting_approval', 20, 'S3 happy awaiting', trace)
    prop = pending_of(s, rid)
    check('S3 happy: pending proposal is ui_click (state changing) with the epoch the model saw',
          prop['tool'] == 'ui_click' and prop['args'] == {'epoch': 1, 'element': 'apply'}, prop)
    check('S3 happy: nothing clicked before the user decision', world()['screen']['last_click'] is None)
    check('S3 happy: decide authorize ok', req(root, 'tool_decide', proposal_id=prop['proposal_id'],
                                             decision='authorize')['code'] == 'ok')
    s = wait_agent(root, lambda a: a['state'] == 'done', 20, 'S3 happy done', trace)
    a = s['agent']
    w = world()
    check('S3 happy: click verified in world.json (last_click apply, epoch 2)',
          w['screen']['last_click'] == 'apply' and w['screen']['epoch'] == 2, w['screen'])
    check('S3 happy: final answer from the model', a.get('answer') == 'Clique concluído.', a.get('answer'))
    tools = steps_of(a, 'tool')
    check('S3 happy: read step (screen_capture) done, change step (ui_click) done',
          [t['risk'] for t in tools] == ['read', 'state_changing'] and [t['state'] for t in tools] == ['done', 'done'],
          tools)
    check('S3 happy: UI statuses seen by the page (awaiting_approval then done)',
          'awaiting_approval' in trace and trace[-1] == 'done', trace)
    audit = events_of(req(root), 'screen_capture')
    check('S3 happy: screen_capture audit present, no content', audit != [], s.get('events'))
    block_clean(a, 'S3 happy')
    R['details']['s3_happy'] = {'run': rid, 'kinds': kinds_of(a), 'trace': trace}

    # B. abort while the click waits for approval: nothing changes.
    before = world_bytes()
    load_script(root, [step(calls=[('c2', 'ui_click', {'epoch': 2, 'element': 'cancel'})]), step(text='nao')])
    code, rid = agent_start(root, 'Clique e aborte')
    s = wait_agent(root, lambda a: a['state'] == 'awaiting_approval', 20, 'S3 abort awaiting')
    prop = pending_of(s, rid)
    check('S3 abort: agent_abort ok', req(root, 'agent_abort', run_id=rid)['code'] == 'ok')
    s = wait_agent(root, lambda a: a['state'] == 'aborted', 10, 'S3 abort aborted')
    check('S3 abort: run aborted, proposal cancelled, no world change',
          s['agent'].get('error') == 'aborted' and world_bytes() == before and next(
              p for p in run_props(s, rid) if p['proposal_id'] == prop['proposal_id'])['state'] == 'cancelled', s['agent'])
    block_clean(s['agent'], 'S3 abort')

    # C. provider failure: a non-recoverable error fails the run with its real code; a recoverable one is retried.
    load_script(root, [step(text='', calls=[], error='model_unsupported_feature'), step(text='nao')])
    code, rid = agent_start(root, 'Falha do provedor')
    s = wait_agent(root, lambda a: a['state'] == 'failed', 20, 'S3 provider failed')
    check('S3 provider failure: failed with the real code model_unsupported_feature, no retry',
          s['agent'].get('error') == 'model_unsupported_feature' and len(steps_of(s['agent'], 'chat')) == 1, s['agent'])
    block_clean(s['agent'], 'S3 provider failure')
    load_script(root, [step(text='', calls=[], error='timeout'), step(text='Depois do retry.')])
    code, rid = agent_start(root, 'Timeout recuperavel')
    s = wait_agent(root, lambda a: a['state'] == 'done', 20, 'S3 retry done')
    chats = steps_of(s['agent'], 'chat')
    check('S3 provider timeout: retried once, then the answer', len(chats) == 2 and chats[0].get('code') == 'timeout'
          and s['agent'].get('answer') == 'Depois do retry.', chats)

    # D. mid-run revoke (LAST: it removes computer_control from running): the click is refused as permission_revoked.
    load_script(root, [step(calls=[('c3', 'ui_click', {'epoch': 2, 'element': 'apply'})]), step(text='parado')])
    before = world_bytes()
    code, rid = agent_start(root, 'Revogue no meio')
    s = wait_agent(root, lambda a: a['state'] == 'awaiting_approval', 20, 'S3 revoke awaiting')
    prop = pending_of(s, rid)
    check('S3 revoke: plugin_revoke of computer_control ok', plugin_op(root, 'plugin_revoke', 'computer_control')['code'] == 'ok')
    check('S3 revoke: authorize ok', req(root, 'tool_decide', proposal_id=prop['proposal_id'],
                                       decision='authorize')['code'] == 'ok')
    s = wait_agent(root, lambda a: a['state'] == 'done', 20, 'S3 revoke done')
    check('S3 revoke: step refused as permission_revoked and the run answered',
          steps_of(s['agent'], 'tool')[-1].get('code') == 'permission_revoked' and s['agent'].get('answer') == 'parado',
          steps_of(s['agent'], 'tool'))
    p = next(p for p in run_props(s, rid) if p['proposal_id'] == prop['proposal_id'])
    check('S3 revoke: proposal failed with reason permission_revoked, world.json unchanged',
          p['state'] == 'failed' and p.get('reason') == 'permission_revoked' and world_bytes() == before, p)
    block_clean(s['agent'], 'S3 revoke')


def run_s3(td):
    cloud = Fake(CLOUD_FAKE)
    FAKES['cloud'] = cloud
    try:
        root = boot(td, 's3', MERGED, ['--agent-synthetic'])
        for pid in (LLM, 'screen_observe', 'computer_control'):
            approve(root, pid)
            stage_upload(str(root), pid, str(PLUGIN_SRC if pid == LLM else PAYLOADS / f'{pid}.py'))
            need(f'S3 install {pid}', install(root, pid)['code'] == 'ok')
            need(f'S3 enable {pid}', plugin_op(root, 'plugin_enable', pid)['code'] == 'ok')
            wait_running(root, pid)
        check('S3: secret_set custom (fake key, loopback only) ok', req(root, 'secret_set', provider='custom',
                                                                       key=KEY)['code'] == 'ok')
        rev = req(root)['llm']['revision']
        check('S3: llm_configure custom loopback fake, consent on ok', req(
            root, 'llm_configure', revision=rev, provider='custom', model='fake/model-1', custom_url=cloud.v1(),
            local_port=None, fallback=None, cloud_consent=True)['code'] == 'ok')
        agent_scenarios_s3(root, cloud.v1())
        native_check(root, 'S3: S1 native after the agent scenarios')
        stop_core('s3')
    finally:
        cloud.close()


def run_qt(td):
    root = boot(td, 'qt', MERGED, ['--agent-synthetic'], replay=False)
    install_all(root, PLUGIN_ORDER)
    # the offscreen sandbox binds only the Core root's parent (and /tmp is a tmpfs): markers live beside the root
    artifacts = Path(root).parent / 'artifacts-perception'
    artifacts.mkdir(exist_ok=True)
    ui = subprocess.Popen(offscreen_command(root, artifacts, 'perception'), env=CLEAN_ENV,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for name in ('perception-ready', 'perception-captured', 'perception-unsupported'):
            until = time.monotonic() + 150
            while not (artifacts / name).exists():
                if ui.poll() is not None:
                    raise RuntimeError(f'Qt perception phase exited before {name}: '
                                       + ui.stderr.read().decode('utf-8', 'replace')[-800:])
                if time.monotonic() > until:
                    raise TimeoutError(f'Qt marker {name}')
                time.sleep(0.02)
        out, err = ui.communicate(timeout=120)
    finally:
        if ui.poll() is None:
            ui.kill()
            ui.wait(timeout=3)
    check('Qt perception phase exit 0', ui.returncode == 0, err.decode('utf-8', 'replace')[-800:])
    row = json.loads(out.decode('utf-8').strip().splitlines()[-1])
    names = row.get('checks') or []
    check('Qt perception self-report accepted (zero failures, passed equals listed)',
          row.get('phase') == 'perception' and row.get('failed') == 0 and row.get('ignored') == 0
          and row.get('passed') == len(names) and names, row)
    R['details']['qt_perception'] = {'passed': row.get('passed'), 'checks': names}
    stop_core('qt')


def run_all():
    global MERGED, DENY_CATALOG
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=BASE, capture_output=True, text=True, check=True).stdout.strip()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    td_obj = tempfile.TemporaryDirectory(prefix='gideon-c4-')
    td = td_obj.name
    MERGED = merged_catalog(td, 'catalog-c4-merged')
    DENY_CATALOG = merged_catalog(td, 'catalog-c4-deny', variant=True)
    try:
        for pid in PLUGIN_ORDER:
            run_step(f'plugin {pid}', run_plugin, td, pid)
        run_step('NOFLAG', run_noflag, td)
        run_step('DENY', run_deny, td)
        run_step('S3 final', run_s3, td)
        run_step('QT perception', run_qt, td)
    except Exception as exc:
        check('gate ran without exception', False, f'{type(exc).__name__}: {exc}')
    finally:
        if CORE is not None:
            try:
                stop_core('final')
            except Exception as exc:
                check('final Core stop', False, exc)
        for fake in FAKES.values():
            try:
                fake.close()
            except Exception:
                pass
        shutil.rmtree(SYNTH_DIR, ignore_errors=True)  # the gate's own synthetic world, never left in the repo

    check('agent blocks were observed (vacuity guard: the four S3 runs)', len(SEEN) >= 4, len(SEEN))
    check('key never seen in any agent block', not any(KEY in text for text in SEEN), '')
    hits = []
    for dirpath, _, files in os.walk(td):
        for name in files:
            path = Path(dirpath) / name
            if path.is_symlink() or path.name.endswith(('.stderr', '.out')):
                continue
            if name == 'secrets.json':
                mode = stat.S_IMODE(path.stat().st_mode)
                check('secrets.json is mode 0600', mode == 0o600, oct(mode))
                continue
            try:
                if KEY.encode() in path.read_bytes():
                    hits.append(str(path.relative_to(td)))
            except OSError:
                pass
    check('key absent from every file under the test root except secrets.json', not hits, hits)
    skip('S2 final matrix', 'not rerun by this gate; scripts/verify_s2_final.py is run separately')
    skip('installed package repeat of the six plugins', 'no package phase in this gate; the package regression is B4/C0 scope')
    skip('real backends (portal, PipeWire, libei, webcam, compositor)',
         'not present in this environment; docs/C4.md backend honesty: synthetic only, real_backend unsupported')

    out = {'gate': 'C4', 'passed': len(R['passed']), 'failed': len(R['failed']), 'skipped': R['skipped'],
           'ignored': R['ignored'], 'checks': R['passed'], 'failures': R['failed'], 'details': R['details'],
           'sampler': {'agent_blocks_scanned': len(SEEN), 'key_leaks': len(hits)},
           'binary_sha256': sha(BIN), 'commit': commit, 'runtime_s': round(time.monotonic() - started, 1),
           'plugins': PLUGIN_ORDER,
           'scope': 'release Core, llm_engine 1.1.0 (scripted fake LLM) and the six C4 plugins via the Hub; '
                    'synthetic world only; loopback fake provider only; no real network or hardware',
           'physical_validation': 'NOT_PERFORMED'}
    td_obj.cleanup()
    text = json.dumps(out, indent=2, ensure_ascii=False) + '\n'
    if KEY in text:
        out['failures'].append({'name': 'key found in result text (refusing to write)', 'detail': ''})
        text = text.replace(KEY, '<redacted>')
    (EVIDENCE / 'c4.json').write_text(text, encoding='utf-8')
    print(text)
    return 0 if not R['failed'] else 1


def run_step(name, fn, *args):
    try:
        fn(*args)
    except Exception as exc:
        check(f'scenario {name} completed without exception', False,
              f'{type(exc).__name__}: {exc} | ' + ' / '.join(traceback.format_exc().strip().splitlines()[-4:])[-500:])
        global CORE
        if CORE is not None:
            try:
                stop_core(f'{name} (after failure)')
            except Exception as stop_exc:
                check(f'{name}: Core stop after failure', False, stop_exc)


MERGED = None
DENY_CATALOG = None

if __name__ == '__main__':
    sys.exit(run_all())
