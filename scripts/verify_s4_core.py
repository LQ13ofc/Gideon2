#!/usr/bin/env python3
"""S4 process gate for D1 (manifest/validator) and D2 (executor) against the REAL release Core.

Gate scope (docs/S4.md, gates D1 and D2). Boots target/release/gideon-base with the C0 catalog
(tests/fixtures/hub-c0.json: dummy_echo) and --agent-synthetic (registry tools tool:synth_*, world at
<home>/synthetic/world.json). Every boot has its own private HOME/XDG and --root/--home under a temp dir.
Skill fixtures: tests/fixtures/skills/ (valid/, invalid/, catalog/) cross-checked against the independent
reference validator scripts/skillfix.py. Derived manifests are built in this file from those fixtures and
checked with the reference validator before use. Evidence: target/evidence/s4-core.json.

Phases:
  VAL      D1 every valid fixture accepted, every invalid fixture rejected with the reference reason (divergence
           per file reported), oversize, state machine only through ops, CAS, dry run zero side effects,
           no elevation, unapproved capability, destructive never runs.
  EXEC     happy read->process->write on the synthetic world, history and audit without content, restart
           persistence of ledgers, version rollback, key/secret leak scan.
  FAIL2    error in step 2 rolls back step 1 (file-level check of world.json).
  CANCEL   cancel mid-run rolls back and ends cancelled.
  REVOKE   plugin revoked mid-run ends failed with missing_dependency and rolls back.
  MISSDEP  a disabled dependency blocks the run before it starts; missing dependency is not an invalid manifest.
  S1       Base regression sanity: snapshot and the native replay command as in verify_c4.py.
"""
import copy
import hashlib
import json
import os
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'scripts'))
from hub_import import upload as stage_upload  # noqa: E402
import skillfix as ref  # noqa: E402  (independent reference validator, test only)

BIN = BASE / 'target/release/gideon-base'
CATALOG = BASE / 'tests/fixtures/hub-c0.json'
PAYLOAD = BASE / 'tests/fixtures/dummy_echo.py'
PLUGIN = 'dummy_echo'
ECHO = 'dummy_echo.echo'
PYTHON = '/usr/bin/python3'
EVIDENCE = BASE / 'target/evidence'
MARK = 'sk-fake-s4-' + secrets.token_hex(12)  # per-run sentinel, passed only as a skill run input
R = {'passed': [], 'failed': [], 'skipped': [], 'details': {}, 'divergences': []}
DECIDES = []
CORE = None  # (process, root, home, label)
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


# ---- check helpers ---------------------------------------------------------------
def check(name, cond, detail=''):
    if cond:
        R['passed'].append(name)
    else:
        R['failed'].append({'name': name, 'detail': str(detail)[:600]})
    return bool(cond)


def skip(name, reason):
    R['skipped'].append({'name': name, 'reason': reason})


def need(name, cond, detail=''):
    """Vacuity guard: a false precondition stops the scenario (recorded as a failure)."""
    if not cond:
        raise AssertionError(f'precondition not met: {name}: {str(detail)[:300]}')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---- wire --------------------------------------------------------------------------
def wire(root, payload):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(15)
        s.connect(str(Path(root) / 'core.sock'))
        s.sendall((json.dumps({'version': 1, 'request_id': f's4_{time.monotonic_ns()}', **payload}) + '\n').encode())
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


def wait_running(root, pid, secs=15):
    return wait_snap(root, lambda s: item(s, pid) is not None and item(s, pid)['state'] == 'running', secs,
                     f'{pid} running')


def install_plugin(root, pid):
    """Approve, stage the opaque payload, install, enable, wait running (same contract as verify_c4.py)."""
    h = req(root)['hub']
    e = next(x for x in h['entries'] if x['plugin_id'] == pid)
    code = req(root, 'hub_approve', revision=h['approval_revision'], plugin_id=pid,
               manifest_sha256=e['manifest_sha256'], permissions=e['permissions'],
               publisher_unverified_ack=True)['code']
    need(f'{pid} approve', code == 'ok', code)
    stage_upload(str(root), pid, str(PAYLOAD))
    h = req(root)['hub']
    code = req(root, 'hub_install', revision=h['install_revision'], plugin_id=pid,
               manifest_sha256=e['manifest_sha256'])['code']
    need(f'{pid} install', code == 'ok', code)
    code = req(root, 'plugin_enable', revision=req(root)['plugins']['revision'], plugin_id=pid)['code']
    need(f'{pid} enable', code == 'ok', code)
    wait_running(root, pid)


def plugin_op(root, name, pid):
    return req(root, name, revision=req(root)['plugins']['revision'], plugin_id=pid)


# ---- skill ops (wire names: skill_version for the version, see src/protocol.rs) -------
def sk_validate(root, m):
    return req(root, 'skill_validate', manifest=m)['code']


def sk_save(root, m):
    return req(root, 'skill_save_draft', manifest=m)['code']


def sk_dry(root, sid, ver, inputs):
    return req(root, 'skill_dry_run', id=sid, skill_version=ver, inputs=inputs)['code']


def sk_revision(root):
    return req(root)['skills']['revision']


def sk_approve(root, sid, ver, revision=None):
    rev = sk_revision(root) if revision is None else revision
    return req(root, 'skill_approve', id=sid, skill_version=ver, revision=rev)['code']


def sk_enable(root, sid, revision=None):
    rev = sk_revision(root) if revision is None else revision
    return req(root, 'skill_enable', id=sid, revision=rev)['code']


def sk_rollback(root, sid, revision=None):
    rev = sk_revision(root) if revision is None else revision
    return req(root, 'skill_rollback', id=sid, revision=rev)['code']


def sk_run(root, sid, inputs):
    return req(root, 'skill_run', id=sid, inputs=inputs)['code']


def sk_decide(root, run_id, step):
    return req(root, 'skill_decide', run_id=run_id, step=step, decision='authorize')['code']


def sk_cancel(root, run_id):
    return req(root, 'skill_cancel', run_id=run_id)['code']


def items(root):
    return (req(root).get('skills') or {}).get('items', [])


def item_of(root, sid):
    return next((i for i in items(root) if i['id'] == sid), None)


def history(root):
    return (req(root).get('skills') or {}).get('history', [])


def run_block(root):
    return (req(root).get('skills') or {}).get('run')


def drive(root, pred, label, secs=25):
    """Polls the run; authorizes every awaited step until pred(run) holds. pred(None) means run ended."""
    until = time.monotonic() + secs
    while True:
        run = run_block(root)
        if pred(run):
            return run
        if run is not None and run.get('state') == 'awaiting_approval':
            pending = [st['id'] for st in run['steps'] if st['state'] == 'awaiting_approval']
            DECIDES.append(sk_decide(root, run['run_id'], pending[-1]))
        if time.monotonic() > until:
            raise TimeoutError(f'{label}: run={json.dumps(run, ensure_ascii=False)[:400]}')
        time.sleep(0.03)


def seq_now(root):
    return req(root)['sequence']


def kinds_after(root, seq):
    return [e['kind'] for e in (req(root).get('events') or []) if e['sequence'] > seq]


# ---- synthetic world (<home>/synthetic/world.json; absent until the first write) --------
def world_path(home):
    return Path(home) / 'synthetic' / 'world.json'


def world_bytes(home):
    path = world_path(home)
    return path.read_bytes() if path.exists() else None


def world(home):
    raw = world_bytes(home)
    return json.loads(raw) if raw is not None else copy.deepcopy(DEFAULT_WORLD)


def app_text(home):
    return world(home)['app']['text']


def sections_except_app(home):
    return {k: v for k, v in world(home).items() if k != 'app'}


# ---- manifests: fixtures plus derived manifests (checked by the reference before use) -------
def fixture(name):
    return ref.load('valid/' + name)


def envelope(sid, name, deps, steps, outputs=None, inputs=None):
    return {'schema_version': 1, 'id': sid, 'name': name, 'version': '1.0.0',
            'publisher': {'id': 'fixture_pub', 'name': 'Fixture publisher'},
            'description': 'TEST FIXTURE ONLY. Derived in the S4 gate.', 'license': 'TEST-ONLY',
            'min_runtime': '0.1.0', 'triggers': [], 'inputs': inputs or {}, 'outputs': outputs or {},
            'dependency_capabilities': deps, 'permissions_required': [], 'prerequisites': [], 'steps': steps,
            'attestations': [{'kind': 'fixture', 'text': 'synthetic test only, never shipped'}]}


def rpw_proc():
    """read -> process (dummy_echo, prefix plus read text) -> write (synthetic set text, undo restores)."""
    m = envelope('fixture_rpw_proc', 'Fixture read process write', ['tool:synth_screen_read', ECHO,
                                                                    'tool:synth_set_text'], [
        {'id': 'read', 'call': 'tool:synth_screen_read', 'args': {}, 'save': {'epoch': 'epoch', 'text': 'text'}},
        {'id': 'proc', 'call': ECHO, 'args': {'text': 'ola-${steps.read.text}'}, 'idempotent': True,
         'save': {'text': 'text'}},
        {'id': 'write', 'call': 'tool:synth_set_text',
         'args': {'epoch': '${steps.read.epoch}', 'text': '${steps.proc.text}'},
         'undo': {'call': 'tool:synth_set_text', 'args': {'epoch': '${steps.read.epoch}', 'text': '${steps.read.text}'}},
         'idempotent': False, 'verify': {'ref': 'steps.write.text', 'op': 'exists'}, 'save': {'text': 'text'}},
    ], outputs={'epoch': {'type': 'int'}, 'text': {'type': 'string'}})
    return m


def fail_variant(sid, sleep_ms):
    """fixture fail_step2 (write, then dummy_echo step) with another id and sleep (cancel/revoke use 4000)."""
    m = fixture('fail_step2')
    m = copy.deepcopy(m)
    m['id'] = sid
    m['name'] = 'Fixture slow variant ' + sid
    m['steps'][1]['args']['sleep_ms'] = sleep_ms
    if sleep_ms <= 5000:
        m['steps'][1]['args']['text'] = 'slow'
    return m


def derived_ok(name, m):
    """Every manifest the gate builds must pass the reference validator, or the gate stops (no vacuity)."""
    need(f'reference validates derived {name}', ref.reference_validate(m) is None, ref.reference_validate(m))
    return m


# ---- Core boot (private root and home per label; the world is fresh per label) -----------
def home_of(td, label):
    return Path(td) / label / 'home'


def core_args(root, home, extra, replay):
    args = [str(BIN), '--root', str(root), '--home', str(home), '--commands-sandbox',
            '--hub-catalog', str(CATALOG), sha(CATALOG), '--plugin-python', PYTHON, *extra]
    if not replay:
        return args
    manifest = BASE / 'target/a3-assets/replay-manifest.json'
    index = next(i for i, r in enumerate(json.loads(manifest.read_text())['fixtures'])
                 if r['id'] == 'wake-hey-brave__bf_emma__clean')
    return args + ['--base-pack', str(BASE / 'target/base-pack-dev.json'),
                   '--tts-virtual', str(BASE / 'target/tts-venv/bin/python'), str(BASE / 'target/a5-assets/manifest.json'),
                   '--wake-replay', str(BASE / 'target/a1-venv/bin/python'), str(manifest), str(index)]


def boot(td, label, extra=('--agent-synthetic',), replay=False, home=None):
    """Starts the Core for `label`. A label reused after stop() restarts on the same root and home.
    `home` overrides the private home (S1 uses the repository home, as verify_c4.py does for replay)."""
    global CORE
    base = Path(td) / label
    home = Path(home) if home is not None else home_of(td, label)
    base.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    root = base / 'core'
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(base), 'XDG_CONFIG_HOME': str(base),
           'XDG_DATA_HOME': str(base), 'XDG_CACHE_HOME': str(base), 'XDG_RUNTIME_DIR': str(base)}
    log = open(base / 'core.stderr', 'ab')
    proc = subprocess.Popen(core_args(root, home, list(extra), replay), env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=log)
    CORE = (proc, root, home, label)
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


def descendants(pid):
    table = {}
    for name in os.listdir('/proc'):
        if not name.isdigit():
            continue
        try:
            with open(f'/proc/{name}/stat', 'rb') as f:
                fields = f.read().decode(errors='replace').rsplit(')', 1)[1].split()
            table[int(name)] = int(fields[1])
        except (OSError, IndexError):
            continue
    found, todo = [], [pid]
    while todo:
        cur = todo.pop()
        for p, parent in table.items():
            if parent == cur:
                found.append(p)
                todo.append(p)
    return found


def alive(pid):
    try:
        with open(f'/proc/{pid}/stat', 'rb') as f:
            return f.read().rsplit(b')', 1)[1].split()[0] != b'Z'
    except OSError:
        return False


def stop(label):
    global CORE
    proc, _, _, _ = CORE
    kids = descendants(proc.pid)
    proc.terminate()
    rc = proc.wait(timeout=15)
    CORE = None
    check(f'{label}: Core clean shutdown rc 0', rc == 0, f'rc={rc}')
    until = time.monotonic() + 5
    left = [p for p in kids if alive(p)]
    while left and time.monotonic() < until:
        time.sleep(0.1)
        left = [p for p in kids if alive(p)]
    check(f'{label}: no child process left after shutdown', not left, left)


def native_check(root, label):
    """S1 regression: the replay Base command succeeds and the wake replay finishes (verify_c4.py contract)."""
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


# ---- D1 + D2 validator phase -------------------------------------------------------------
DEFER = ('cycle_a', 'depth_3')  # the Core checks cycles and depth against INSTALLED skills only


def classify(core, want):
    naming = {'skill_invalid:duplicate_step_id': 'skill_invalid:duplicate_step',
              'skill_invalid:future_ref': 'skill_invalid:forward_ref'}
    if core == 'ok':
        return 'catalog_scope: reference treats every fixture as installed; Core checks only installed skills'
    if naming.get(want) == core:
        return 'naming: same rule, different motivo name in the Core'
    return 'unexplained'


def compare(root, stem, m, reason=None):
    reason = reason or ref.REASON_MAP[stem]
    want = 'skill_invalid:' + reason
    got_ref = ref.reference_validate(m)
    check(f'reference self-check {stem} == {reason} (got {got_ref})', got_ref == reason, got_ref)
    core = sk_validate(root, m)
    R['details'].setdefault('d1', {})[stem] = {'reference': want, 'core': core, 'match': core == want}
    if core != want:
        R['divergences'].append({'file': stem, 'reference': want, 'core': core, 'class': classify(core, want)})
    check(f'D1 invalid/{stem}: Core rejects as {want} (core={core})', core == want, core)


def d1_phase(td):
    root = boot(td, 'val')
    home = home_of(td, 'val')
    hub0 = json.dumps({'approval': req(root)['hub']['approval_revision'], 'installed': req(root)['hub'].get('installed')},
                      sort_keys=True)
    valid, invalid = ref.all_valid(), ref.all_invalid()
    catalog = ref.all_catalog()
    need('fixture counts (8 valid, 18 invalid files + generated oversize, 3 catalog)',
         len(valid) == 8 and len(invalid) == 19 and len(catalog) == 3, (len(valid), len(invalid), len(catalog)))
    for stem, m in sorted(valid.items()):
        code = sk_validate(root, m)
        check(f'D1 valid/{stem} accepted by Core', code == 'ok', code)
        check(f'D1 reference accepts valid/{stem}', ref.reference_validate(m) is None, ref.reference_validate(m))
    for stem, m in sorted(invalid.items()):
        if stem not in DEFER:
            compare(root, stem, m)
    check('validate writes nothing (no skill items after every fixture was validated)', items(root) == [], items(root))

    # Installed helpers so the chain rules see real installed skills (valid on their own).
    for stem in ('depth_leaf', 'depth_mid2', 'depth_mid1'):
        code = sk_save(root, catalog[stem])
        check(f'D1 catalog helper {stem} saved as draft', code == 'ok', code)
    code = sk_save(root, invalid['cycle_b'])
    check('D1 cycle_b saved as draft (its partner is not installed: missing dependency, not invalid)',
          code == 'ok', code)
    for stem in DEFER:
        compare(root, stem, invalid[stem])

    code = sk_save(root, invalid['oversize'])
    check('D1 oversize manifest refused on save (skill_invalid:oversize), nothing stored', code == 'skill_invalid:oversize'
          and len(items(root)) == 4, (code, items(root)))
    big_args = copy.deepcopy(fixture('read_process_write'))
    big_args['steps'][1]['args'] = {'value': 'a' * 2100}
    compare(root, 'args_over_2k', big_args, 'oversize')

    # State machine: draft -> validated -> tested (dry run) -> approved -> enabled, only through ops.
    rpw = fixture('read_process_write')
    sid, ver = rpw['id'], rpw['version']
    check('D1 read_process_write saved as draft', sk_save(root, rpw) == 'ok')
    it = item_of(root, sid)
    check('D2 saved draft is validated and created by the user', it is not None and it['state'] == 'validated'
          and it['source'] == 'created', it)
    check('D2 approve before dry run refused skill_not_tested', sk_approve(root, sid, ver) == 'skill_not_tested')
    check('D2 enable before approval refused skill_not_approved', sk_enable(root, sid) == 'skill_not_approved')
    check('D2 run before enable refused skill_not_enabled', sk_run(root, sid, {}) == 'skill_not_enabled')
    check('D2 run of a draft leaves no run', run_block(root) is None)
    seq = seq_now(root)
    w0 = world_bytes(home)
    code = sk_dry(root, sid, ver, {})
    check('D2 dry run ok (zero capability side effects: no capability_invoked, no skill_step)', code == 'ok', code)
    kinds = kinds_after(root, seq)
    check('D2 dry run emits no capability_invoked and no skill_step', 'capability_invoked' not in kinds
          and 'skill_step' not in kinds, kinds)
    check('D2 dry run leaves world.json unchanged (absent before, absent after)', world_bytes(home) == w0)
    check('D2 dry run starts no run and sets no capability result', run_block(root) is None
          and req(root).get('capability_result') is None)
    check('D2 dry run moves state to tested', item_of(root, sid)['state'] == 'tested', item_of(root, sid))
    rev = sk_revision(root)
    code = sk_approve(root, sid, ver, revision=rev - 1)
    check('CAS approve with stale revision refused stale_skill_revision (state unchanged)',
          code == 'stale_skill_revision' and item_of(root, sid)['state'] == 'tested', (code, item_of(root, sid)))
    check('D2 approve current revision ok', sk_approve(root, sid, ver) == 'ok')
    check('D2 approved state reached only by the user op', item_of(root, sid)['state'] == 'approved')
    check('D2 enable ok after approval', sk_enable(root, sid) == 'ok')
    check('D2 enabled state reached', item_of(root, sid)['state'] == 'enabled')
    check('D2 enable again answers already_enabled', sk_enable(root, sid) == 'already_enabled')
    code = sk_save(root, rpw)
    check(f'D2 an enabled version cannot be overwritten by save (code {code})', code != 'ok', code)
    check('D2 a saved version of an enabled skill is still enabled', item_of(root, sid)['state'] == 'enabled')

    # Unapproved capability: the skill depends on a plugin never installed here.
    ghost = copy.deepcopy(fixture('uses_stub_plugin'))
    ghost['id'] = 'fixture_unapproved'
    ghost['dependency_capabilities'] = ['dummy_evil.probe']
    ghost['steps'][0]['call'] = 'dummy_evil.probe'
    derived_ok('unapproved', ghost)
    check('D2 unapproved-capability skill saved', sk_save(root, ghost) == 'ok')
    seq = seq_now(root)
    code = sk_dry(root, 'fixture_unapproved', '1.0.0', {'text': 'hi'})
    check(f'D2 skill cannot reach an uninstalled or unapproved capability: dry run {code}',
          code == 'missing_dependency', code)
    check('D2 blocked dry run invokes nothing', 'capability_invoked' not in kinds_after(root, seq))
    check('D2 missing dependency keeps the manifest valid (saved, not skill_invalid)', item_of(root, 'fixture_unapproved')
          is not None and item_of(root, 'fixture_unapproved')['missing'] != [], item_of(root, 'fixture_unapproved'))
    dep = fixture('missing_dep')
    check('D1 missing_dep fixture saved and dry run blocked by missing_dependency',
          sk_save(root, dep) == 'ok' and sk_dry(root, dep['id'], '1.0.0', {}) == 'missing_dependency')

    # Destructive capability never runs in development.
    pub = derived_ok('publish', envelope('fixture_publish', 'Fixture publish', ['tool:synth_publish'],
                                         [{'id': 'publish', 'call': 'tool:synth_publish', 'args': {}}]))
    check('D2 destructive skill saved', sk_save(root, pub) == 'ok')
    code = sk_dry(root, 'fixture_publish', '1.0.0', {})
    check(f'D2 destructive capability never runs in development (dry run {code})', code == 'destructive_disabled',
          code)
    check('D2 refused dry run leaves the state validated', item_of(root, 'fixture_publish')['state'] == 'validated')

    hub1 = json.dumps({'approval': req(root)['hub']['approval_revision'], 'installed': req(root)['hub'].get('installed')},
                      sort_keys=True)
    check('no elevation: skill operations change no plugin approval or installation', hub0 == hub1, (hub0, hub1))
    stop('val')


# ---- EXEC phase: happy path, history/audit content, restart, versions, leak scan ----------------
def exec_phase(td):
    root = boot(td, 'exec')
    home = home_of(td, 'exec')
    install_plugin(root, PLUGIN)
    proc = rpw_proc()
    derived_ok('rpw_proc', proc)
    sid, ver = proc['id'], proc['version']
    code = sk_save(root, proc)
    check(f'D2 happy skill saved ({code})', code == 'ok', code)
    seq = seq_now(root)
    w0 = world_bytes(home)
    code = sk_dry(root, sid, ver, {})
    check(f'D2 dry run ok with dummy_echo running (RESOLVE_DEPS) ({code})', code == 'ok', code)
    kinds = kinds_after(root, seq)
    check('D2 dry run of the real chain: no capability_invoked, no skill_step', 'capability_invoked' not in kinds
          and 'skill_step' not in kinds, kinds)
    check('D2 dry run of the real chain leaves world.json absent', world_bytes(home) == w0)
    codes = (sk_approve(root, sid, ver), sk_enable(root, sid))
    check(f'D2 approve and enable {codes}', codes == ('ok', 'ok'), codes)
    code = sk_run(root, sid, {})
    check(f'D2 run accepted ({code})', code == 'ok', code)
    drive(root, lambda r: r is None, 'happy run ends')
    last = history(root)[-1]
    check(f'D2 happy run ends done ({last["state"]})', last['state'] == 'done' and last['skill'] == sid, last)
    check(f'happy read->process->write: world.json app.text is OLA- ({app_text(home)!r})', app_text(home) == 'OLA-',
          app_text(home))
    check('happy run leaves every other world section unchanged', sections_except_app(home) == {
        k: v for k, v in DEFAULT_WORLD.items() if k != 'app'}, sections_except_app(home))
    evs = [e['kind'] for e in req(root).get('events') or []]
    check('audit has skill_run_started, skill_step and skill_run_done', all(k in evs for k in
          ('skill_run_started', 'skill_step', 'skill_run_done')), evs[-12:])
    check('every decision of the run answered ok', DECIDES and all(c == 'ok' for c in DECIDES), DECIDES)

    # Ledgers: private files; history and audit carry no content.
    skills_json = root / 'skills.json'
    runs_json = root / 'skill-runs.json'
    manifest = root / 'skills' / sid / ver / 'skill.json'
    for path in (skills_json, runs_json, manifest):
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
        check(f'ledger {path.relative_to(root)} is mode 0600', mode == 0o600, oct(mode) if mode else mode)
    runs_text = runs_json.read_text(encoding='utf-8')
    check('history file has no content: no world text, no outputs, no arguments', 'OLA' not in runs_text
          and 'ola-' not in runs_text and '"args"' not in runs_text and 'outputs' not in runs_text, runs_text[:200])
    allowed = {'run_id', 'skill', 'version', 'state', 'step', 'codes'}
    check('history entries carry only run id, skill, version, state, step and codes',
          all(set(h) <= allowed for h in history(root)), history(root)[-1:])
    audit_keys_ok = all(set(e) <= {'sequence', 'request_id', 'session_id', 'kind'} for e in req(root)['events'])
    check('audit events carry no content (sequence, request_id, session_id, kind only)', audit_keys_ok)
    R['details']['exec'] = {'history_last': history(root)[-1], 'world_text': app_text(home)}

    # Restart persistence: items, history, world and file modes survive a restart.
    stop('exec-1')
    root = boot(td, 'exec')
    its = items(root)
    check('restart: skill item persists enabled, version 1.0.0, active', item_of(root, sid) is not None
          and item_of(root, sid)['state'] == 'enabled' and item_of(root, sid)['active'] is True
          and item_of(root, sid)['version'] == ver, its)
    check('restart: run history persists (last run done)', history(root)[-1]['state'] == 'done', history(root)[-1:])
    check('restart: world.json app.text still OLA-', app_text(home) == 'OLA-', app_text(home))
    if item(req(root), PLUGIN)['state'] != 'running':
        plugin_op(root, 'plugin_enable', PLUGIN)
        wait_running(root, PLUGIN)
    check('restart: plugin available again for dependency checks', item(req(root), PLUGIN)['state'] == 'running')

    # Versions: save 1.0.1, enable it, stale rollback refused, rollback to 1.0.0 moves active back.
    v2 = copy.deepcopy(proc)
    v2['version'] = '1.0.1'
    derived_ok('rpw_proc v1.0.1', v2)
    check('versions: 1.0.1 saved as draft', sk_save(root, v2) == 'ok')
    check('versions: 1.0.1 dry run ok', sk_dry(root, sid, '1.0.1', {}) == 'ok')
    check('versions: 1.0.1 approved', sk_approve(root, sid, '1.0.1') == 'ok')
    check('versions: 1.0.1 enabled', sk_enable(root, sid) == 'ok')
    cur = item_of(root, sid)
    check('versions: 1.0.1 is the active version', cur['version'] == '1.0.1' and cur['active'] is True, cur)
    check('versions: stale rollback refused stale_skill_revision', sk_rollback(root, sid,
          revision=sk_revision(root) - 1) == 'stale_skill_revision')
    check('versions: rollback ok', sk_rollback(root, sid) == 'ok')
    back = item_of(root, sid)
    check('versions: rollback makes 1.0.0 active and enabled again', back['version'] == '1.0.0'
          and back['active'] is True and back['state'] == 'enabled', back)
    stop('exec-2')
    root = boot(td, 'exec')
    after = item_of(root, sid)
    check('versions: rolled-back active version persists across restart', after is not None
          and after['version'] == '1.0.0' and after['active'] is True, after)

    # Key/secret leak scan: a sentinel used only as a run input must appear in no snapshot, audit, ledger or log.
    stub = fixture('uses_stub_plugin')
    check('leak scan: stub skill saved', sk_save(root, stub) == 'ok')
    check('leak scan: stub dry run ok with the sentinel as input', sk_dry(root, stub['id'], '1.0.0', {'text': MARK}) == 'ok')
    check('leak scan: stub approve and enable', sk_approve(root, stub['id'], '1.0.0') == 'ok'
          and sk_enable(root, stub['id']) == 'ok')
    check('leak scan: stub run accepted', sk_run(root, stub['id'], {'text': MARK}) == 'ok')
    drive(root, lambda r: r is None, 'stub run ends')
    check('leak scan: stub run done', history(root)[-1]['state'] == 'done', history(root)[-1])
    snap_text = json.dumps(req(root), ensure_ascii=False)
    check('leak scan: sentinel absent from snapshot, audit and history (case-sensitive and upper)',
          MARK not in snap_text and MARK.upper() not in snap_text, 'found')
    hits = []
    for dirpath, _, names in os.walk(td):
        for name in names:
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if MARK.encode() in data or MARK.upper().encode() in data:
                hits.append(str(path.relative_to(td)))
    check('leak scan: sentinel absent from every file under the test root (ledgers, manifests, logs)', not hits, hits)
    R['details']['leak'] = {'files_scanned': sum(len(n) for _, _, n in os.walk(td)), 'hits': hits}
    stop('exec-3')


# ---- FAIL2 / CANCEL / REVOKE: the fixtures' undo-rollback path --------------------------------
def rollback_check(root, home, before_sections, label):
    check(f'{label}: world.json app.text back to pre-run value (undo of step one)', app_text(home) == '',
          app_text(home))
    check(f'{label}: every other world section unchanged (file-level)', sections_except_app(home) == before_sections,
          sections_except_app(home))


def fail2_phase(td):
    root = boot(td, 'fail2')
    home = home_of(td, 'fail2')
    install_plugin(root, PLUGIN)
    m = derived_ok('fail_step2', fixture('fail_step2'))
    sid, ver = m['id'], m['version']
    check('fail2: saved, dry run, approve, enable', sk_save(root, m) == 'ok' and sk_dry(root, sid, ver, {}) == 'ok'
          and sk_approve(root, sid, ver) == 'ok' and sk_enable(root, sid) == 'ok')
    before = sections_except_app(home)
    check('fail2: run accepted', sk_run(root, sid, {}) == 'ok')
    drive(root, lambda r: r is not None and r['state'] == 'awaiting_approval' and r['steps'][-1]['id'] == 'fail',
          'fail2 reaches step two')
    check('fail2: step one wrote the world before step two (app.text fixture)', app_text(home) == 'fixture',
          app_text(home))
    drive(root, lambda r: r is None, 'fail2 run ends')
    last = history(root)[-1]
    check(f'fail2: run failed at step fail (state {last["state"]})', last['state'] == 'failed' and last['step'] == 'fail',
          last)
    check('fail2: rollback ran (skill_rolled_back event observed)', 'skill_rolled_back' in
          [e['kind'] for e in req(root).get('events') or []], [e['kind'] for e in req(root).get('events') or []][-8:])
    rollback_check(root, home, before, 'fail2')
    R['details']['fail2'] = {'codes': last['codes'], 'step': last['step']}
    stop('fail2')


def cancel_phase(td):
    root = boot(td, 'cancel')
    home = home_of(td, 'cancel')
    install_plugin(root, PLUGIN)
    m = derived_ok('cancel_slow', fail_variant('fixture_cancel_slow', 4000))
    sid, ver = m['id'], m['version']
    check('cancel: saved, dry run, approve, enable', sk_save(root, m) == 'ok' and sk_dry(root, sid, ver, {}) == 'ok'
          and sk_approve(root, sid, ver) == 'ok' and sk_enable(root, sid) == 'ok')
    before = sections_except_app(home)
    check('cancel: run accepted', sk_run(root, sid, {}) == 'ok')
    run = drive(root, lambda r: r is not None and r['state'] == 'running' and r['steps'][-1]['id'] == 'fail',
                'cancel reaches the slow step running')
    check('cancel: step one wrote before the slow step runs', app_text(home) == 'fixture', app_text(home))
    check('cancel: abort the slow step in flight', sk_cancel(root, run['run_id']) == 'ok')
    drive(root, lambda r: r is None, 'cancel run ends')
    last = history(root)[-1]
    check(f'cancel: run ends cancelled ({last["state"]})', last['state'] == 'cancelled', last)
    rollback_check(root, home, before, 'cancel')
    stop('cancel')


def revoke_phase(td):
    root = boot(td, 'revoke')
    home = home_of(td, 'revoke')
    install_plugin(root, PLUGIN)
    m = derived_ok('revoke_slow', fail_variant('fixture_revoke_slow', 4000))
    sid, ver = m['id'], m['version']
    check('revoke: saved, dry run, approve, enable', sk_save(root, m) == 'ok' and sk_dry(root, sid, ver, {}) == 'ok'
          and sk_approve(root, sid, ver) == 'ok' and sk_enable(root, sid) == 'ok')
    before = sections_except_app(home)
    check('revoke: run accepted', sk_run(root, sid, {}) == 'ok')
    drive(root, lambda r: r is not None and r['state'] == 'running' and r['steps'][-1]['id'] == 'fail',
          'revoke reaches the slow step running')
    check('revoke: plugin revoked mid-run', plugin_op(root, 'plugin_revoke', PLUGIN)['code'] == 'ok')
    drive(root, lambda r: r is None, 'revoke run ends')
    last = history(root)[-1]
    check(f'revoke: run fails with missing_dependency ({last["codes"]})', last['state'] == 'failed'
          and 'missing_dependency' in last['codes'], last)
    rollback_check(root, home, before, 'revoke')
    stop('revoke')


# ---- MISSDEP: a disabled dependency blocks the run before it starts ------------------------
def missdep_phase(td):
    root = boot(td, 'missdep')
    home = home_of(td, 'missdep')
    install_plugin(root, PLUGIN)
    stub = derived_ok('stub', fixture('uses_stub_plugin'))
    sid = stub['id']
    check('missdep: stub saved, dry run, approve, enable',
          sk_save(root, stub) == 'ok' and sk_dry(root, sid, '1.0.0', {'text': 'hi'}) == 'ok'
          and sk_approve(root, sid, '1.0.0') == 'ok' and sk_enable(root, sid) == 'ok')
    check('missdep: plugin disabled', plugin_op(root, 'plugin_disable', PLUGIN)['code'] == 'ok')
    code = sk_run(root, sid, {'text': 'hi'})
    check(f'missdep: run blocked before it starts ({code})', code == 'missing_dependency', code)
    check('missdep: no run started and world untouched', run_block(root) is None and world_bytes(home) is None)
    it = item_of(root, sid)
    check('missdep: snapshot lists the missing dependency and deps_ok false', it is not None and it['deps_ok'] is False
          and ECHO in it['missing'], it)
    check('missdep: skill still enabled (blocked, not revoked)', it['state'] == 'enabled', it)
    stop('missdep')


# ---- S1: Base regression sanity ----------------------------------------------------------------
def s1_phase(td):
    root = boot(td, 's1', replay=True, home=BASE)  # verify_c4.py replay boot: home is the repository
    check('S1 snapshot answers ok (state idle)', req(root)['state'] == 'idle', req(root)['state'])
    native_check(root, 'S1: Base replay command success and replay_finished')
    stop('s1')
    shutil.rmtree(BASE / 'synthetic', ignore_errors=True)  # the synthetic world of the S1 boot, never left in the repo


# ---- runner -----------------------------------------------------------------------------------
def run_step(name, fn, td):
    try:
        fn(td)
    except Exception as exc:
        check(f'phase {name} completed without exception', False,
              f'{type(exc).__name__}: {exc} | ' + ' / '.join(traceback.format_exc().strip().splitlines()[-4:])[-500:])
        global CORE
        if CORE is not None:
            try:
                stop(f'{name} (after failure)')
            except Exception as stop_exc:
                check(f'{name}: Core stop after failure', False, stop_exc)


def run_all():
    started = time.monotonic()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    td = tempfile.mkdtemp(prefix='gideon-s4-')
    global CORE
    try:
        run_step('D1/D2 validator and state machine', d1_phase, td)
        run_step('D2 happy path, restart, versions, leak scan', exec_phase, td)
        run_step('D2 error in step two', fail2_phase, td)
        run_step('D2 cancel mid-run', cancel_phase, td)
        run_step('D2 plugin revoked mid-run', revoke_phase, td)
        run_step('D2 missing dependency', missdep_phase, td)
        run_step('S1 Base regression', s1_phase, td)
    finally:
        if CORE is not None:
            try:
                stop('final')
            except Exception as exc:
                check('final Core stop', False, exc)
        if R['failed']:
            R['details']['kept_root'] = td  # keep logs and ledgers of a failing run for diagnosis
        else:
            shutil.rmtree(td, ignore_errors=True)

    try:
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=BASE, capture_output=True, text=True,
                                timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        commit = None
    out = {'gate': 'S4-core D1+D2', 'passed': len(R['passed']), 'failed': len(R['failed']),
           'skipped': R['skipped'], 'checks': R['passed'], 'failures': R['failed'],
           'divergences': R['divergences'], 'details': R['details'], 'decide_codes': sorted(set(DECIDES)),
           'binary_sha256': sha(BIN), 'commit': commit, 'catalog': 'tests/fixtures/hub-c0.json',
           'runtime_s': round(time.monotonic() - started, 1),
           'scope': 'release Core, C0 catalog (dummy_echo) and the synthetic registry tools; synthetic world only; '
                    'no D3/D4, no Qt, no real backend'}
    text = json.dumps(out, indent=2, ensure_ascii=False) + '\n'
    (EVIDENCE / 's4-core.json').write_text(text, encoding='utf-8')
    print(text)
    return 0 if not R['failed'] else 1


if __name__ == '__main__':
    sys.exit(run_all())
