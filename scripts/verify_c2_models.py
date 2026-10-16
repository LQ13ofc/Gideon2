#!/usr/bin/env python3
"""Private real Core C2 model-manager gate (gate C2_MODELS): release Core, loopback fakes only,
llm_engine 1.1.0 installed through the Hub, native S1 regressions. Writes target/evidence/c2-models.json.

Fakes (loopback 127.0.0.1 only, never a real provider):
  A  fake_llama_server          local llama.cpp shape, selected for selftest / LKG / rollback
  T  fake_llama_server --text-only   local text-only model (tool_use must be refused)
  P  fake_llm_server + --script  primary of the fallback test; prefix "fb:" answers 503 (error503)
  F  fake_llm_server            fallback local route and the cloud echo target
  C  fake_llm_server            remote simulated as provider `custom` (loopback allowed by the test flag)

Never writes real keys: the key is per run and fake-looking (sk-fake-...), it exists only in this
process memory, the Core vault (secrets.json 0600) and the fake provider request. Checks that the key
is absent from snapshots, /proc of Core/broker/plugin, and every file under the test root except secrets.json.
Preconditions use need() (AssertionError, scenario stops); req() raises AssertionError on a malformed reply.
Check failures are recorded in the result and the gate exits 1; nothing is faked or relaxed.
"""
import hashlib, http.client, itertools, json, os, secrets, socket, stat, subprocess, sys, tempfile, threading, time, traceback
from pathlib import Path
from hub_import import upload as stage_upload
from ui_fixture import offscreen_command

BASE = Path(__file__).resolve().parents[1]
BIN = BASE / 'target/release/gideon-base'
CATALOG = BASE / 'tests/fixtures/hub-c1.json'
PLUGIN_SRC = BASE / 'tests/fixtures/llm_engine.py'
CLOUD_FAKE = BASE / 'tests/fixtures/fake_llm_server.py'
LLAMA_FAKE = BASE / 'tests/fixtures/fake_llama_server.py'
UI_TEST = BASE / 'scripts/test_ui_offscreen.py'
EVIDENCE = BASE / 'target/evidence'
PYTHON = '/usr/bin/python3'
PLUGIN = 'llm_engine'
CAP = 'llm_engine.chat'
MODELS = 'llm_engine.models'
PLUGIN_MARK = b'/plugin/main.py'
BROKER_MARK = b'net_broker.py'
KEY = 'sk-fake-' + secrets.token_hex(16)  # per-run fake key, never a real credential
KEY_B = KEY.encode()
CLK = os.sysconf('SC_CLK_TCK')
CLEAN_ENV = {'PATH': '/usr/bin:/bin'}
GOOGLE_ID = 'google-gemini-3.5-flash-lite'
MISTRAL_ID = 'mistral-ministral-3b-latest'
R = {'passed': [], 'failed': [], 'skipped': [], 'ignored': [], 'details': {}}
_counter = itertools.count(1)
_wire = threading.Lock()
LEAKS = []
SEEN = {'broker': 0, 'plugin': 0, 'scans': 0}
CORE = None  # (proc, root, label)
STOP = threading.Event()
PAUSE = threading.Event()
FAKES = {}


def check(name, cond, detail=''):
    if cond:
        R['passed'].append(name)
    else:
        R['failed'].append({'name': name, 'detail': str(detail)[:600]})
    return bool(cond)


def need(name, cond, detail=''):
    """Vacuous-proof precondition: a false one stops the scenario with AssertionError (recorded as failure)."""
    if not cond:
        raise AssertionError(f'precondition not met: {name}: {str(detail)[:300]}')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wire(root, payload):
    with _wire:
        n = next(_counter)
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(15)
        s.connect(str(Path(root) / 'core.sock'))
        s.sendall((json.dumps({'version': 1, 'request_id': f'c2m_{n}', **payload}) + '\n').encode())
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


def item(s):
    return next((i for i in s['plugins']['items'] if i['plugin_id'] == PLUGIN), None)


def entry(h):
    return next((e for e in h['entries'] if e['plugin_id'] == PLUGIN), None)


def approve(root):
    h = req(root)['hub']
    e = entry(h)
    return req(root, 'hub_approve', revision=h['approval_revision'], plugin_id=PLUGIN,
               manifest_sha256=e['manifest_sha256'], permissions=e['permissions'], publisher_unverified_ack=True)


def install(root):
    h = req(root)['hub']
    return req(root, 'hub_install', revision=h['install_revision'], plugin_id=PLUGIN,
               manifest_sha256=entry(h)['manifest_sha256'])


def hub_op(root, name):
    return req(root, name, revision=req(root)['hub']['install_revision'], plugin_id=PLUGIN)


def plugin_op(root, name):
    return req(root, name, revision=req(root)['plugins']['revision'], plugin_id=PLUGIN)


def wait_running(root, secs=15):
    return wait_snap(root, lambda s: item(s) is not None and item(s)['state'] == 'running', secs, 'llm_engine running')


def llm(root):
    return req(root)['llm']


def cfg(root):
    return llm(root).get('config')


def lkg_of(root):
    c = cfg(root)
    return c.get('lkg') if c else None


def same_route(a, b):
    keys = ('provider', 'model', 'custom_url', 'local_port')
    return a is not None and b is not None and all(a.get(k) == b.get(k) for k in keys)


def configure(root, provider, model, custom_url, consent, local_port=None, fallback=None):
    rev = llm(root)['revision']
    return req(root, 'llm_configure', revision=rev, provider=provider, model=model, custom_url=custom_url,
               local_port=local_port, fallback=fallback, cloud_consent=consent)


def set_secret(root, provider, key=KEY):
    return req(root, 'secret_set', provider=provider, key=key)


def invoke(root, capability, inp, deadline=10000):
    code = req(root, 'capability_invoke', capability=capability, input=inp, deadline_ms=deadline)['code']
    if code != 'ok':
        return code, None
    return code, wait_snap(root, lambda s: s.get('capability_result') is not None,
                           deadline / 1000 + 10, 'capability_result')['capability_result']


def chat(root, text, tools=False, max_tokens=64, require=None, fallback_flag=None, deadline=10000):
    inp = {'messages': [{'role': 'user', 'content': text}], 'tools': tools, 'max_tokens': max_tokens}
    if require is not None:
        inp['require'] = require
    if fallback_flag is not None:
        inp['fallback'] = fallback_flag
    return invoke(root, CAP, inp, deadline)


def models(root, inp):
    return invoke(root, MODELS, inp)


def list_all(root, tab, limit=6):
    """Pages through one tab the way the UI does (offset advances by the items received).
    Returns (items, pages, error); error is None only when the walk reached total with no refused
    or empty page before it."""
    items, pages, offset = [], [], 0
    while True:
        code, res = models(root, {'action': 'list', 'tab': tab, 'offset': offset, 'limit': limit})
        if code != 'ok' or not res or res.get('ok') is not True:
            return items, pages, ('refused', code, res)
        out = res.get('output') or {}
        pages.append(out)
        got = out.get('items') or []
        items += got
        offset += len(got)
        if offset >= out.get('total', 0):
            return items, pages, None
        if not got:
            return items, pages, ('empty_page_before_total', out.get('total'), offset)


def model_row(i, **over):
    m = {'id': f'custom-{i:02d}', 'label': f'Local test {i:02d}', 'kind': 'local', 'provider': 'local',
         'model': 'gguf-local', 'custom_url': None, 'tier': 'custom', 'license': 'MIT', 'quantization': None,
         'sha256': None, 'backend': 'llama.cpp',
         'features': {'streaming': 'supported', 'tool_use': 'supported', 'vision': 'unknown',
                      'cancel': 'unknown', 'context_tokens': 4096},
         'certification': {'state': 'declared', 'evidence': None, 'date': None},
         'cost': {'input_per_mtok': None, 'output_per_mtok': None, 'currency': None},
         'latency_hint': 'unknown', 'min_hardware': {'ram_gb': None, 'gpu': 'unknown'}, 'offline': True}
    m.update(over)
    if 'local_port' not in over:  # Model schema: 8080 default for local, null for every other provider
        m['local_port'] = 8080 if m['provider'] in ('local', 'ollama') else None
    return m


# ---- processes -------------------------------------------------------------
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


def descendants(pid):
    table = proc_table()
    children = {}
    for p, (pp, _, _) in table.items():
        children.setdefault(pp, []).append(p)
    found, todo = [], [pid]
    while todo:
        for child in children.get(todo.pop(), []):
            found.append(child)
            todo.append(child)
    return [p for p in found if p in table and table[p][1] != 'Z']


def alive(pid):
    try:
        with open(f'/proc/{pid}/stat', 'rb') as f:
            return f.read().decode(errors='replace').rsplit(')', 1)[1].split()[0] != 'Z'
    except OSError:
        return False


def sandbox_pids(core_pid, mark):
    table = proc_table()
    return [p for p in descendants(core_pid) if mark in table[p][2]]


def wait_no(core_pid, mark, secs):
    until = time.monotonic() + secs
    while sandbox_pids(core_pid, mark):
        if time.monotonic() > until:
            return False
        time.sleep(0.05)
    return True


def tick_sum(pids):
    total = 0
    for pid in pids:
        try:
            with open(f'/proc/{pid}/stat', 'rb') as f:
                fields = f.read().decode(errors='replace').rsplit(')', 1)[1].split()
            total += int(fields[11]) + int(fields[12])
        except (OSError, IndexError):
            pass
    return total


def scan_processes(core_pid):
    SEEN['scans'] += 1
    for pid in [core_pid] + descendants(core_pid):
        for part in ('cmdline', 'environ'):
            try:
                with open(f'/proc/{pid}/{part}', 'rb') as f:
                    data = f.read()
            except OSError:
                continue
            if KEY_B in data:
                LEAKS.append(('process', f'{pid}:{part}'))
        try:
            with open(f'/proc/{pid}/cmdline', 'rb') as f:
                argv = f.read()
        except OSError:
            continue
        if BROKER_MARK in argv:
            SEEN['broker'] += 1
        if PLUGIN_MARK in argv:
            SEEN['plugin'] += 1


class Sampler(threading.Thread):
    """Polls snapshots and the process tree of the running Core for the key."""

    def __init__(self):
        super().__init__(daemon=True)

    def run(self):
        while not STOP.is_set():
            target = CORE
            if PAUSE.is_set() or target is None:
                time.sleep(0.02)
                continue
            _, root, _ = target
            try:
                if KEY_B in wire(root, {'op': 'snapshot'}):
                    LEAKS.append(('snapshot', target[2]))
            except (OSError, RuntimeError, ValueError):
                pass
            try:
                scan_processes(target[0].pid)
            except OSError:
                pass
            time.sleep(0.03)


# ---- Core ------------------------------------------------------------------
def core_args(root):
    manifest = BASE / 'target/a3-assets/replay-manifest.json'
    index = next(i for i, r in enumerate(json.loads(manifest.read_text())['fixtures'])
                 if r['id'] == 'wake-hey-brave__bf_emma__clean')
    return [str(BIN), '--root', str(root), '--commands-sandbox', '--hub-catalog', str(CATALOG), sha(CATALOG),
            '--plugin-python', PYTHON, '--net-allow-loopback',
            '--base-pack', str(BASE / 'target/base-pack-dev.json'),
            '--tts-virtual', str(BASE / 'target/tts-venv/bin/python'), str(BASE / 'target/a5-assets/manifest.json'),
            '--wake-replay', str(BASE / 'target/a1-venv/bin/python'), str(manifest), str(index)]


def core_root(td):
    return Path(td) / 'core'


def start_core(td, label):
    global CORE
    root = core_root(td)
    env = {'PATH': '/usr/bin:/bin', 'HOME': td, 'XDG_CONFIG_HOME': td, 'XDG_DATA_HOME': td,
           'XDG_CACHE_HOME': td, 'XDG_RUNTIME_DIR': td}
    log = open(Path(td) / f'core-{label}.stderr', 'wb')
    proc = subprocess.Popen(core_args(root), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log)
    CORE = (proc, root, label)
    until = time.monotonic() + 15
    while True:
        try:
            req(root)
            break
        except (OSError, RuntimeError, ValueError):
            pass
        if proc.poll() is not None:
            raise RuntimeError(f'Core exited early rc={proc.returncode}')
        if time.monotonic() > until:
            raise TimeoutError(f'Core {label} startup')
        time.sleep(0.02)
    return proc


def stop_core(label):
    global CORE
    proc, _, _ = CORE
    table = proc_table()
    pids = [p for p in descendants(proc.pid) if any(m in table[p][2] for m in (PLUGIN_MARK, BROKER_MARK))]
    proc.terminate()
    rc = proc.wait(timeout=15)
    CORE = None
    check(f'{label}: Core clean shutdown rc 0', rc == 0, f'rc={rc}')
    check(f'{label}: no plugin or broker process left after shutdown', all(not alive(p) for p in pids),
          [p for p in pids if alive(p)])


def native_effect(root, name, secs=30):
    until = time.monotonic() + secs
    while True:
        s = req(root)
        if (s['state'] == 'idle' and s['command'] is not None and s['command'].get('code') == 'command_success'
                and s.get('wake_status') == 'replay_finished'):
            break
        if time.monotonic() > until:
            raise TimeoutError(f'{name}: no S1 success')
        time.sleep(0.015)
    check(name, bool(s['command']['receipt']['verified']))
    return s


def install_llm(root, reinstall=False):
    """Approve both permissions, stage the fixture payload, install, enable, wait running.
    On reinstall the approval may survive hub_remove: `already_approved` is then the valid state."""
    approved = approve(root)
    accepted = ('ok', 'already_approved') if reinstall else ('ok',)
    check('llm_engine approve (network_llm + storage_settings) ok'
          + (' or already approved after hub_remove' if reinstall else ''), approved.get('code') in accepted,
          f"code={approved.get('code')}")
    if reinstall:
        R['details']['reinstall_approve_code'] = approved.get('code')
    stage_upload(str(root), PLUGIN, str(PLUGIN_SRC))
    inst = install(root)
    check('llm_engine staged and installed from tests/fixtures/llm_engine.py', inst['code'] == 'ok', inst)
    enabled = plugin_op(root, 'plugin_enable')
    check('llm_engine enable ok', enabled['code'] == 'ok', enabled)
    wait_running(root)


# ---- fakes -----------------------------------------------------------------
class Fake:
    def __init__(self, src, extra=()):
        self.proc = subprocess.Popen([PYTHON, '-I', str(src), '--port', '0', *extra], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=CLEAN_ENV, cwd='/')
        self.port = int(self.proc.stdout.readline())

    def http(self, method, path):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.request(method, path)
            return json.loads(conn.getresponse().read())
        finally:
            conn.close()

    def log(self):
        return self.http('GET', '/__log')['requests']

    def reset(self):
        self.http('POST', '/__reset')

    def v1(self):
        return f'http://127.0.0.1:{self.port}/v1'

    def close(self):
        self.proc.terminate()
        self.proc.wait(timeout=5)


def auth_of(record):
    if 'authorization_received' in record:
        return record['authorization_received']
    return 'authorization' in (record.get('headers') or {})


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


# ---- scenarios -------------------------------------------------------------
def scen_install_and_models(td):
    root = core_root(td)
    native_effect(root, 'S1 native before any LLM plugin (wake replay to command)')
    h = req(root)['hub']
    e = entry(h)
    check('Hub catalog hub-c1.json verified with llm_engine 1.1.0 (both permissions, both capabilities)',
          h.get('status') == 'verified' and e is not None and e.get('semver') == '1.1.0'
          and e['permissions'] == ['network_llm', 'storage_settings'] and e['capabilities'] == [CAP, MODELS],
          {'status': h.get('status'), 'semver': e and e.get('semver')})
    install_llm(root)
    check('llm_engine running after install and enable', item(req(root))['state'] == 'running')
    check('no key configured at start (secrets flags all false)',
          llm(root)['secrets'] == {'openrouter': False, 'opencode': False, 'google': False, 'custom': False})
    rec, rec_pages, rec_err = list_all(root, 'recommended')
    check('models.list recommended pages ok (every page accepted, reaches total)', rec_err is None and bool(rec_pages), rec_err)
    out = rec_pages[0] if rec_pages else {}
    check('models.list page echoes tab, offset 0 and total equal to the entries listed',
          out.get('tab') == 'recommended' and out.get('offset') == 0 and out.get('total') == len(rec), out)
    check('models.list recommended has >= 6 entries', len(rec) >= 6, len(rec))
    code, res = models(root, {'action': 'list', 'tab': 'recommended', 'offset': 0, 'limit': 7})
    check('models.list limit 7 refused (invalid_input)', bool(res) and res.get('error') == 'invalid_input', res)
    code, res = models(root, {'action': 'list'})
    check('models.list without paging keys refused (invalid_input)', bool(res) and res.get('error') == 'invalid_input', res)
    certified = {m['id'] for m in rec if m['certification']['state'] == 'certified'}
    check('only google and mistral are certified in recommended', certified == {GOOGLE_ID, MISTRAL_ID}, sorted(certified))
    evidence_ok = []
    for mid in sorted(certified):
        dcode, dres = models(root, {'action': 'describe', 'id': mid})
        evidence_ok.append(bool(dres and dres.get('ok') is True
                                and ((dres.get('output') or {}).get('model') or {}).get('certification', {}).get('evidence')))
    check('certified recommended entries cite evidence (describe, not null)', bool(evidence_ok) and all(evidence_ok),
          {mid: ok for mid, ok in zip(sorted(certified), evidence_ok)})
    locals_ = [m for m in rec if m['kind'] == 'local']
    check('local recommended entries are candidate (not certified)',
          len(locals_) >= 2 and all(m['certification']['state'] == 'candidate' for m in locals_),
          [(m['id'], m['certification']['state']) for m in locals_])
    cust, cust_pages, cust_err = list_all(root, 'custom')
    check('models.list custom empty through paging (items [], total 0)',
          cust == [] and cust_err is None and bool(cust_pages) and cust_pages[0].get('total') == 0, cust_pages[:1])
    check('models.list selected null before any configuration', out.get('selected') is None, out.get('selected'))
    hw = out.get('hardware') or {}
    check('models.list hardware present (cpu_cores, ram_gb) with gpu unknown',
          isinstance(hw.get('cpu_cores'), int) and hw['cpu_cores'] >= 1 and isinstance(hw.get('ram_gb'), (int, float))
          and hw.get('gpu') == 'unknown', hw)
    code, res = models(root, {'action': 'describe', 'id': 'local-llamacpp-gguf'})
    check('models.describe recommended local entry ok', code == 'ok' and res and res.get('ok') is True
          and (res.get('output') or {}).get('model', {}).get('kind') == 'local', res)
    native_effect(root, 'S1 native still answers with llm_engine running (replay state of this boot)')


def scen_local_select(td, A):
    root = core_root(td)
    A.reset()
    code = configure(root, 'local', 'gguf-local', None, False, local_port=A.port)
    check('llm_configure local 127.0.0.1 port, no key, consent false => ok', code['code'] == 'ok', code)
    code, res = models(root, {'action': 'selftest'})
    out = (res or {}).get('output') or {}
    feats = out.get('features') or {}
    check('selftest local => ok, streaming supported, tool_use supported, source probed',
          code == 'ok' and bool(res) and res.get('ok') is True and feats.get('streaming') == 'supported'
          and feats.get('tool_use') == 'supported' and out.get('source') == 'probed', res)
    log = A.log()
    check('local fake received selftest requests (>= 2)', len(log) >= 2, len(log))
    check('local fake received NO Authorization header', bool(log) and all(not auth_of(r) for r in log),
          [auth_of(r) for r in log])
    code, res = models(root, {'action': 'features'})
    feat = (res or {}).get('output') or {}
    check('features after selftest reports tool_use supported (probed is part of the effective matrix)',
          (feat.get('features') or {}).get('tool_use') == 'supported', feat)
    check('features source of a local candidate is not "certified"', feat.get('source') != 'certified', feat.get('source'))
    rev = llm(root)['revision']
    code = req(root, 'llm_mark_good', revision=rev)
    check('llm_mark_good => ok', code['code'] == 'ok', code)
    lkg = lkg_of(root)
    check('llm.config.lkg set to the selected local route',
          lkg is not None and lkg.get('provider') == 'local' and lkg.get('local_port') == A.port, lkg)
    R['details']['selftest_local'] = {'latency_ms': out.get('latency_ms'), 'features': feats}


def scen_restart_persist(td):
    root = core_root(td)
    before_cfg = cfg(root)
    need('config present before restart', before_cfg is not None, before_cfg)
    stop_core('boot1 before restart')
    start_core(td, 'boot2')
    wait_running(root)
    after = cfg(root)
    check('restart: config persists (local, port, no consent)', after is not None and after.get('provider') == 'local'
          and after.get('local_port') == before_cfg.get('local_port') and after.get('cloud_consent') is False, after)
    check('restart: lkg persists', after is not None and same_route(after.get('lkg'), before_cfg.get('lkg')), after)
    check('restart: llm_engine enabled and running from plugin-state', item(req(root))['enabled'] is True
          and item(req(root))['state'] == 'running')


def scen_rollback(td, A):
    root = core_root(td)
    lkg = lkg_of(root)
    need('LKG present before rollback test', lkg is not None, lkg)
    dead = free_port()
    check('llm_configure local dead loopback port ok', configure(root, 'local', 'gguf-local', None, False,
                                                                 local_port=dead)['code'] == 'ok')
    code, res = models(root, {'action': 'selftest'})
    check('selftest on dead local port => model_selftest_failed', bool(res) and res.get('ok') is False
          and res.get('error') == 'model_selftest_failed', res)
    rev = llm(root)['revision']
    code = req(root, 'llm_rollback', revision=rev)
    check('llm_rollback with LKG => ok', code['code'] == 'ok', code)
    now = cfg(root)
    check('rollback restores LKG (config equals the earlier good one)', same_route(now, lkg)
          and now.get('cloud_consent') is False, now)
    rev = llm(root)['revision']
    code2 = req(root, 'llm_rollback', revision=rev)
    now2 = cfg(root)
    check('second rollback without LKG change is idempotent (ok, config still LKG)', code2['code'] == 'ok'
          and same_route(now2, lkg) and same_route(now2.get('lkg'), lkg), {'code': code2['code'], 'config': now2})
    R['details']['rollback'] = {'second_code': code2['code']}


def scen_text_only(td):
    root = core_root(td)
    T = FAKES['T']
    T.reset()
    check('llm_configure local text-only model ok', configure(root, 'local', 'gguf-local', None, False,
                                                               local_port=T.port)['code'] == 'ok')
    code, res = models(root, {'action': 'selftest'})
    feats = ((res or {}).get('output') or {}).get('features') or {}
    check('selftest text-only => tool_use unsupported (streaming supported)',
          bool(res) and res.get('ok') is True and feats.get('tool_use') == 'unsupported'
          and feats.get('streaming') == 'supported', res)
    code, res = models(root, {'action': 'features'})
    check('features reports tool_use unsupported after probe',
          ((res or {}).get('output') or {}).get('features', {}).get('tool_use') == 'unsupported', res)
    T.reset()
    code, res = chat(root, 'hello from the text-only check', tools=True, require=['tools'])
    check('chat require tools on text-only => model_unsupported_feature',
          code == 'ok' and bool(res) and res.get('ok') is False and res.get('error') == 'model_unsupported_feature', res)
    check('text-only chat with require tools made 0 chat requests', len(T.log()) == 0, len(T.log()))
    lkg = lkg_of(root)
    need('LKG still present for restore', lkg is not None, lkg)
    check('restore local LKG after text-only check', configure(root, 'local', 'gguf-local', None, False,
                                                                local_port=lkg['local_port'])['code'] == 'ok')


def scen_fallback(td):
    root = core_root(td)
    P, F = FAKES['P'], FAKES['F']
    fb_local = {'provider': 'local', 'model': 'gguf-local', 'custom_url': None, 'local_port': F.port}
    check('llm_configure primary local (503 fake) with local fallback ok',
          configure(root, 'local', 'gguf-local', None, False, local_port=P.port, fallback=fb_local)['code'] == 'ok')
    P.reset()
    F.reset()
    code, res = chat(root, 'fb:hello fallback', fallback_flag=True)
    out = (res or {}).get('output') or {}
    check('primary 503 + fallback:true => ok with used_fallback and the fallback text',
          bool(res) and res.get('ok') is True and out.get('used_fallback') is True
          and out.get('text') == 'fb:hello fallback', res)
    check('primary received exactly one request (503)', len(P.log()) == 1, len(P.log()))
    check('fallback local fake received exactly one request', len(F.log()) == 1, len(F.log()))
    events = req(root).get('events') or []
    check('event llm_fallback_used emitted', any(ev.get('kind') == 'llm_fallback_used' for ev in events),
          [ev.get('kind') for ev in events][-8:])
    P.reset()
    F.reset()
    code, res = chat(root, 'e401:fallback must not run', fallback_flag=True)
    check('primary 401 => http_error with http_status 401 (no fallback)', bool(res) and res.get('error') == 'http_error'
          and res.get('http_status') == 401, res)
    check('401 on primary => 0 fallback requests', len(F.log()) == 0, len(F.log()))
    set_secret(root, 'openrouter')
    fb_cloud = {'provider': 'openrouter', 'model': 'fake/model-1', 'custom_url': None, 'local_port': None}
    check('llm_configure primary local 503 with cloud fallback (openrouter, consent off) ok',
          configure(root, 'local', 'gguf-local', None, False, local_port=P.port, fallback=fb_cloud)['code'] == 'ok')
    P.reset()
    F.reset()
    code, res = chat(root, 'fb:cloud fallback without consent', fallback_flag=True)
    check('cloud fallback without consent => cloud_not_authorized', bool(res) and res.get('error') == 'cloud_not_authorized', res)
    check('cloud fallback without consent => 0 requests anywhere and no broker spawned',
          len(F.log()) == 0 and len(P.log()) == 1 and not sandbox_pids(CORE[0].pid, BROKER_MARK),
          {'fallback': len(F.log()), 'primary': len(P.log())})
    check('restore local LKG after fallback checks', configure(root, 'local', 'gguf-local', None, False,
                                                                local_port=FAKES['A'].port)['code'] == 'ok')


def scen_remote(td):
    root = core_root(td)
    C = FAKES['C']
    C.reset()
    check('secret_set custom => flag true', set_secret(root, 'custom')['code'] == 'ok'
          and llm(root)['secrets']['custom'] is True)
    check('llm_configure custom (simulated remote) with consent on ok',
          configure(root, 'custom', 'fake/model-1', C.v1(), True)['code'] == 'ok')
    code, res = chat(root, 'echo:remote hello')
    check('remote simulated: streaming chat ok with text', bool(res) and res.get('ok') is True
          and (res.get('output') or {}).get('text') == 'remote hello', res)
    log = C.log()
    check('remote fake got Authorization == Bearer <vault key> from Core', len(log) == 1
          and (log[0].get('headers') or {}).get('authorization') == f'Bearer {KEY}', len(log))
    check('remote fake got stream true and model chosen by Core', bool(log) and log[0]['body'].get('stream') is True
          and log[0]['body'].get('model') == 'fake/model-1', log and log[0]['body'].get('model'))
    C.reset()
    check('llm_configure openrouter (cloud, non-loopback) consent OFF ok',
          configure(root, 'openrouter', 'fake/model-1', None, False)['code'] == 'ok')
    code, res = chat(root, 'echo:no consent')
    check('openrouter key set + consent OFF => cloud_not_authorized', bool(res) and res.get('error') == 'cloud_not_authorized', res)
    check('openrouter consent OFF => 0 fake requests and no broker spawned',
          len(C.log()) == 0 and not sandbox_pids(CORE[0].pid, BROKER_MARK), len(C.log()))
    check('configure back to custom with consent ON for later steps',
          configure(root, 'custom', 'fake/model-1', C.v1(), True)['code'] == 'ok')


def save_ok(root, m):
    return models(root, {'action': 'save_custom', 'model': m})


def scen_custom(td):
    root = core_root(td)
    code, res = save_ok(root, model_row(1))
    out = (res or {}).get('output') or {}
    check('save_custom valid model => ok saved', code == 'ok' and bool(res) and res.get('ok') is True
          and out.get('saved') == 'custom-01', res)
    rows, _pages, err = list_all(root, 'custom')
    row = next((r for r in rows if r['id'] == 'custom-01'), None)
    check('list shows the custom as tier custom with certification declared',
          err is None and row is not None and row['tier'] == 'custom' and row['certification']['state'] == 'declared', rows)
    for i in range(2, 17):
        code, res = save_ok(root, model_row(i))
    rows, pages, err = list_all(root, 'custom')
    check('16 customs saved and ALL listed through paging (16 items, total 16 on every page)',
          err is None and [r['id'] for r in rows] == [f'custom-{i:02d}' for i in range(1, 17)]
          and {p.get('total') for p in pages} == {16}, {'count': len(rows), 'error': err})
    check('custom pages hold at most 6 Models each', bool(pages) and all(len(p.get('items') or []) <= 6 for p in pages),
          [len(p.get('items') or []) for p in pages])
    code, res = save_ok(root, model_row(17))
    check('17th custom refused (invalid_input)', bool(res) and res.get('ok') is False and res.get('error') == 'invalid_input', res)
    bad = [
        ('bad enum (features.streaming maybe)', model_row(18, features={'streaming': 'maybe', 'tool_use': 'supported',
                                                                      'vision': 'unknown', 'cancel': 'unknown',
                                                                      'context_tokens': 4096})),
        ('oversize label (49 chars)', model_row(19, label='L' * 49)),
        ('duplicate id of saved custom', model_row(1)),
    ]
    for label, m in bad:
        code, res = save_ok(root, m)
        check(f'invalid custom refused: {label}', bool(res) and res.get('ok') is False and res.get('error') == 'invalid_input', res)
    code, res = models(root, {'action': 'delete_custom', 'id': 'custom-16'})
    check('delete_custom existing => ok', code == 'ok' and bool(res) and res.get('ok') is True, res)
    code, res = models(root, {'action': 'delete_custom', 'id': 'custom-16'})
    check('delete_custom again => model_not_found', bool(res) and res.get('error') == 'model_not_found', res)
    plugin_root = Path(td) / 'core'
    files = [p for p in plugin_root.rglob('*.json') if p.name == f'{PLUGIN}.json' and p.parent.name == 'plugin-settings']
    check('plugin settings file under the Core root exists', len(files) == 1, [str(p) for p in files])
    if files:
        mode = stat.S_IMODE(files[0].stat().st_mode)
        check('plugin settings file is mode 0600', mode == 0o600, oct(mode))
        check('plugin settings file holds no secret', KEY_B not in files[0].read_bytes()
              and b'sk-fake' not in files[0].read_bytes())
    rows, _pages, err = list_all(root, 'custom')
    check('custom count after delete is 15 (all reachable through paging)', err is None and len(rows) == 15, len(rows))


def scen_reinstall(td):
    root = core_root(td)
    pre_cfg = cfg(root)
    pre_lkg = pre_cfg.get('lkg') if pre_cfg else None
    pre_rows, _pages, _err = list_all(root, 'custom')
    pre_custom = len(pre_rows)
    need('config and LKG present before reinstall', pre_cfg is not None and pre_lkg is not None, pre_cfg)
    check('hub_remove llm_engine ok', hub_op(root, 'hub_remove')['code'] == 'ok')
    check('llm_engine absent after hub_remove', item(req(root)) is None)
    install_llm(root, reinstall=True)
    post = cfg(root)
    check('reinstall: config persists (same route and consent)', same_route(post, pre_cfg)
          and post.get('cloud_consent') == pre_cfg.get('cloud_consent'), post)
    check('reinstall: lkg persists', same_route(lkg_of(root), pre_lkg), lkg_of(root))
    now_rows, _pages, now_err = list_all(root, 'custom')
    now_custom = len(now_rows)
    check('reinstall: customs persist (count equals pre-remove count 15)', now_err is None and now_custom == pre_custom == 15,
          {'before': pre_custom, 'after': now_custom})
    check('plugin_settings_clear ok', req(root, 'plugin_settings_clear', plugin_id=PLUGIN)['code'] == 'ok')
    gone_rows, gone_pages, gone_err = list_all(root, 'custom')
    check('after plugin_settings_clear: customs gone (total 0)', gone_err is None and gone_rows == []
          and bool(gone_pages) and gone_pages[0].get('total') == 0, gone_err)
    post2 = cfg(root)
    check('after plugin_settings_clear: config remains', same_route(post2, pre_cfg), post2)
    native_effect(root, 'S1 native after the manager flow and reinstall')


# Qt models phase (test_ui_offscreen.py --phase models): markers in order, then its JSON row.
UI_MARKERS = ['models-ready', 'custom-added', 'model-active', 'selftest-rolled-back', 'status-unavailable',
              'custom-removed']
UI_REQUIRED = [
    'actual Core connection', 'accessible cancel name', 'QML minimum is 480x520',
    'minimum layout size respected', 'Modelos LLM offered only because llm_engine.models runs',
    'models panel visible on its page', 'recommended tab has its accessible name',
    'only certified models read Certificado', 'Local filter hides cloud recommendations',
    'custom model saved through the Core and listed as Personalizado',
    'use runs configure, selftest and mark good', 'status line reads Disponível for the tested model',
    'failed selftest is reported and the last good model is restored',
    'cancelled removal keeps the custom model', 'confirmed removal deletes it through the Core',
]
UI_ONE_OF = ['text-only model shows INDISPONÍVEL for tool use',
             'text-only model failed its test and was rolled back']


def accept_qt_row(row):
    """Strict like verify_c1_llm / verify_c0_plugins: zero failures, passed equals the listed checks,
    every required check present, exactly one of the text-only alternatives."""
    names = (row or {}).get('checks') or []
    missing = sorted(set(UI_REQUIRED) - set(names))
    alternatives = [name for name in UI_ONE_OF if name in names]
    ok = (bool(row) and row.get('phase') == 'models' and row.get('failed') == 0 and row.get('ignored') == 0
          and row.get('passed') == len(names) and bool(names) and not missing and len(alternatives) == 1)
    check('Qt models phase self-report accepted (zero failures, passed equals listed, every required check '
          'present; missing ' + str(missing) + '; alternatives ' + str(alternatives) + ')', ok, row)


def scen_qt(td):
    root = core_root(td)
    artifacts = Path(td) / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    # Ports for the Qt phase: ok = fake llama.cpp (tools), text = fake text-only llama.cpp, fail = a
    # loopback port with no listener (selftest fails with a network error, so the Core rolls back).
    ports = {'ok': FAKES['A'].port, 'fail': free_port(), 'text': FAKES['T'].port}
    (artifacts / 'fake-ports.json').write_text(json.dumps(ports), encoding='utf-8')
    ui = subprocess.Popen(offscreen_command(root, artifacts, 'models'), env=CLEAN_ENV,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for name in UI_MARKERS:
            until = time.monotonic() + 150
            while not (artifacts / name).exists():
                if ui.poll() is not None:
                    raise RuntimeError(f'Qt models phase exited before {name}: '
                                       + ui.stderr.read().decode('utf-8', 'replace')[-800:])
                if time.monotonic() > until:
                    raise TimeoutError(f'Qt marker {name}')
                time.sleep(0.02)
        out, err = ui.communicate(timeout=120)
    finally:
        if ui.poll() is None:
            ui.kill()
            ui.wait(timeout=3)
    check('Qt models phase exit 0', ui.returncode == 0, err.decode('utf-8', 'replace')[-800:])
    row = json.loads(out.decode('utf-8').strip().splitlines()[-1])
    accept_qt_row(row)
    R['details']['qt_models'] = {'passed': row.get('passed'), 'state_trace': row.get('state_trace')}


def scen_idle_and_final_s1(td):
    root = core_root(td)
    PAUSE.set()
    time.sleep(0.4)
    c0 = tick_sum([CORE[0].pid])
    start = time.monotonic()
    time.sleep(3)
    window = time.monotonic() - start
    core_pct = (tick_sum([CORE[0].pid]) - c0) / (CLK * window) * 100
    R['details']['idle_cpu'] = {'core_percent': round(core_pct, 3), 'window_s': round(window, 2),
                                'plugin_pids': sandbox_pids(CORE[0].pid, PLUGIN_MARK)}
    PAUSE.clear()
    check('idle Core CPU below 1% over 3 s with idle llm_engine', core_pct < 1.0, core_pct)
    check('llm_engine running during idle window', item(req(root))['state'] == 'running')
    native_effect(root, 'S1 native at the end of the gate (llm_engine idle)')


def run_step(name, fn, *args):
    try:
        fn(*args)
    except Exception as exc:
        check(f'scenario {name} completed without exception', False,
              f'{type(exc).__name__}: {exc} | ' + ' / '.join(traceback.format_exc().strip().splitlines()[-4:])[-500:])


def main():
    global CORE
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=BASE, capture_output=True, text=True, check=True).stdout.strip()
    status_before = subprocess.run(['git', 'status', '--porcelain'], cwd=BASE, capture_output=True, text=True, check=True).stdout
    dirty_before = porcelain_paths(status_before)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    sampler = Sampler()
    sampler.start()
    td_obj = tempfile.TemporaryDirectory(prefix='gideon-c2-models-')
    td = td_obj.name
    script = Path(td) / 'fb-override.json'
    script.write_text(json.dumps({'commands': [{'op': 'override', 'prefix': 'fb:', 'scenario': 'error503'}]}))
    try:
        FAKES['A'] = Fake(LLAMA_FAKE)
        FAKES['T'] = Fake(LLAMA_FAKE, ['--text-only'])
        FAKES['P'] = Fake(CLOUD_FAKE, ['--script', str(script)])
        FAKES['F'] = Fake(CLOUD_FAKE)
        FAKES['C'] = Fake(CLOUD_FAKE)
        start_core(td, 'boot1')
        run_step('install and models', scen_install_and_models, td)
        run_step('local select and LKG', scen_local_select, td, FAKES['A'])
        run_step('restart persistence', scen_restart_persist, td)
        run_step('rollback on selftest failure', scen_rollback, td, FAKES['A'])
        run_step('text-only tool refusal', scen_text_only, td)
        run_step('fallback', scen_fallback, td)
        run_step('remote simulated', scen_remote, td)
        run_step('custom models', scen_custom, td)
        run_step('reinstall and settings clear', scen_reinstall, td)
        run_step('qt phase', scen_qt, td)
        run_step('idle cpu and final S1', scen_idle_and_final_s1, td)
    finally:
        if CORE is not None:
            try:
                stop_core('final')
            except Exception as exc:
                check('final Core stop', False, exc)
        STOP.set()
        for fake in FAKES.values():
            try:
                fake.close()
            except Exception:
                pass
    leftovers = [p for p in proc_table().values() if td.encode() in p[2]]
    check('no Core, broker, plugin or fake process left under the test root', not leftovers, len(leftovers))
    check('key never seen in snapshots or /proc of Core, broker or plugin', not LEAKS, LEAKS[:5])
    check('sampler scanned the live Core during the run', SEEN['scans'] > 50, SEEN)
    check('broker and plugin processes were observed during the run', SEEN['broker'] > 0 and SEEN['plugin'] > 0, SEEN)
    hits = []
    for dirpath, _, files in os.walk(td):
        for name in files:
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            if name == 'secrets.json' and Path(dirpath) == core_root(td):
                mode = stat.S_IMODE(path.stat().st_mode)
                check('secrets.json is mode 0600', mode == 0o600, oct(mode))
                check('secrets.json holds the key (vault works; only file allowed to contain it)', KEY_B in path.read_bytes())
                continue
            try:
                if KEY_B in path.read_bytes():
                    hits.append(str(path.relative_to(td)))
            except OSError:
                pass
    check('key absent from every file under the test root except secrets.json (logs, events, settings)', not hits, hits)
    status_after = subprocess.run(['git', 'status', '--porcelain'], cwd=BASE, capture_output=True, text=True, check=True).stdout
    new_paths = sorted(porcelain_paths(status_after) - dirty_before)
    check('gate created no new repo paths outside target/ (paths dirty at gate start tolerated)', not new_paths, new_paths[:20])
    out = {'gate': 'C2_MODELS', 'passed': len(R['passed']), 'failed': len(R['failed']), 'skipped': R['skipped'],
           'ignored': R['ignored'], 'checks': R['passed'], 'failures': R['failed'], 'details': R['details'],
           'sampler': {'process_scans': SEEN['scans'], 'key_leaks': len(LEAKS)},
           'binary_sha256': sha(BIN), 'commit': commit, 'runtime_s': round(time.monotonic() - started, 1),
           'scope': 'release Core, loopback fakes only (llama.cpp shape, OpenAI shape), llm_engine 1.1.0 via Hub; no real network',
           'physical_validation': 'NOT_PERFORMED'}
    td_obj.cleanup()
    text = json.dumps(out, indent=2, ensure_ascii=False) + '\n'
    if KEY in text:
        out['failures'].append({'name': 'key found in result text (refusing to write)', 'detail': ''})
        text = text.replace(KEY, '<redacted>')
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / 'c2-models.json').write_text(text, encoding='utf-8')
    print(text)
    sys.exit(0 if not R['failed'] else 1)


def porcelain_paths(text):
    paths = set()
    for line in text.splitlines():
        path = line[3:]
        if ' -> ' in path:
            path = path.split(' -> ', 1)[1]
        path = path.strip('"')
        if path and not path.startswith('target/'):
            paths.add(path)
    return paths


if __name__ == '__main__':
    main()
