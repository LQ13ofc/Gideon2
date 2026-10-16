#!/usr/bin/env python3
"""C1 live gate (gate C1_LIVE): real Core, real provider endpoints, keys from GIDEON_LIVE_KEYS_FILE.

GIDEON_LIVE_KEYS_FILE must be an absolute path OUTSIDE the repo, a regular file with mode 0600,
holding JSON {provider: [key, ...]} with provider in google, mistral, openrouter, opencode.
Keys go only through IPC secret_set (memory), never argv/env/stdout/result file.
Per provider: fresh Core root, no --net-allow-loopback, llm_engine via Hub, consent ON, at most 3
invocations: 'Reply with the single word: pong' (max_tokens 16) and 'What time is it? Use the tool.'
(tools true). Classification uses the Core's capability_result.error and numeric capability_result.http_status:
  PASSED            ok reply containing pong, finish stop, partials seen (only this)
  EXTERNAL_BLOCKED  http_error with http_status (401/402/403/429/503 and any other HTTP status), or
                    network_unavailable. A 401/402/403/429/503 moves to the next key (max 3 keys).
  FAILED            missing key (key_missing), http_error WITHOUT http_status, plugin_error, any other
                    Core error, or a reply check failure. Harness problems are FAILED, never blocked.

NEEDS THE P12 CORE CHANGE: until src/plugins.rs passes provider error codes through and exposes
http_status in capability_result, every provider error arrives as plugin_error and is recorded FAILED
with that reason. The gate does not relax this; it is the contract.

Exit: 0 only if at least one provider PASSED and none FAILED. EXTERNAL_BLOCKED/SKIPPED do not fail.
Exit 2 (no result file) on any key-file or argument problem.

--self-test: labelled SELF-TEST. Uses a loopback fake provider and an in-memory fake key, exercises the
argument checks, the secret-scrub logic, the http_status classification (402/403/429/503 through the
real Core where the Core exposes http_status, otherwise recorded as IGNORED pending P12) and the result
writer. It never writes target/evidence/c1-live.json.
"""
import hashlib, http.client, itertools, json, os, secrets, socket, stat, subprocess, sys, tempfile, threading, time, traceback
from pathlib import Path
from hub_import import upload as stage_upload

BASE = Path(__file__).resolve().parents[1]
BIN = BASE / 'target/release/gideon-base'
CATALOG = BASE / 'tests/fixtures/hub-c1.json'
PLUGIN_SRC = BASE / 'tests/fixtures/llm_engine.py'
FAKE_SRC = BASE / 'tests/fixtures/fake_llm_server.py'
EVIDENCE = BASE / 'target/evidence'
RESULT_PATH = EVIDENCE / 'c1-live.json'
PYTHON = '/usr/bin/python3'
PLUGIN = 'llm_engine'
CAP = 'llm_engine.chat'
PLUGIN_MARK = b'/plugin/main.py'
BROKER_MARK = b'net_broker.py'
CLEAN_ENV = {'PATH': '/usr/bin:/bin'}
PONG_PROMPT = 'Reply with the single word: pong'
TIME_PROMPT = 'What time is it? Use the tool.'
BLOCK_CODES = (401, 402, 403, 429, 503)  # named in the spec; every HTTP status is blocked by classify()
MAX_KEYS = 3
MAX_CALLS = 3
KNOWN_PROVIDERS = ('google', 'mistral', 'openrouter', 'opencode')
PROVIDERS = [
    {'name': 'google', 'core': 'google', 'model': 'gemini-3.5-flash-lite', 'custom_url': None},
    {'name': 'mistral', 'core': 'custom', 'model': 'ministral-3b-latest', 'custom_url': 'https://api.mistral.ai/v1'},
    {'name': 'openrouter', 'core': 'openrouter', 'model': 'meta-llama/llama-3.2-3b-instruct', 'custom_url': None},
    {'name': 'opencode', 'core': 'opencode', 'model': 'gpt-5.4-nano', 'custom_url': None},
]
_counter = itertools.count(1)
_wire = threading.Lock()
R_IGNORED = []  # self-test codes whose real-Core check could not run (Core without http_status)


class ArgError(Exception):
    pass


# ---- key file and argument checks -------------------------------------------------
def valid_key(key):
    return isinstance(key, str) and 8 <= len(key) <= 256 and all(33 <= ord(c) <= 126 for c in key)


def load_keys(path, repo=BASE):
    """Returns {provider: [keys]} or raises ArgError with a clear message. Never echoes key text."""
    if not path:
        raise ArgError('GIDEON_LIVE_KEYS_FILE is not set')
    if not os.path.isabs(path):
        raise ArgError('GIDEON_LIVE_KEYS_FILE must be an absolute path')
    p = Path(path)
    try:
        resolved = p.resolve(strict=True)
    except OSError:
        raise ArgError('GIDEON_LIVE_KEYS_FILE does not exist')
    try:
        resolved.relative_to(Path(repo).resolve())
        raise ArgError('GIDEON_LIVE_KEYS_FILE must be outside the repository')
    except ValueError:
        pass
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise ArgError('GIDEON_LIVE_KEYS_FILE must be a regular file, not a link')
    if stat.S_IMODE(st.st_mode) != 0o600:
        raise ArgError('GIDEON_LIVE_KEYS_FILE must have mode 0600')
    try:
        data = json.loads(resolved.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise ArgError('GIDEON_LIVE_KEYS_FILE is not valid JSON')
    if not isinstance(data, dict):
        raise ArgError('GIDEON_LIVE_KEYS_FILE must be a JSON object {provider: [keys]}')
    keys = {}
    for provider, values in data.items():
        if provider not in KNOWN_PROVIDERS:
            raise ArgError(f'unknown provider id in keys file: {provider!r}')
        if not isinstance(values, list) or not all(valid_key(v) for v in values):
            raise ArgError(f'keys for {provider} must be a list of printable keys 8..256 chars (contents not shown)')
        keys[provider] = values
    return keys


def scrub(text, keys):
    """Replaces every loaded key in text. Used on every string that reaches the result."""
    for key in keys:
        text = text.replace(key, '<redacted>')
    return text


def contains_any(text, keys):
    return any(key in text for key in keys)


def tree_hits(root, keys):
    """Files under root (except secrets.json) that contain a loaded key."""
    hits = []
    for dirpath, _, files in os.walk(root):
        for name in files:
            path = Path(dirpath) / name
            if path.name == 'secrets.json' and path.parent == Path(root):
                continue  # the only file allowed to hold the key
            try:
                data = path.read_bytes().decode('utf-8', 'replace')
            except OSError:
                continue
            if contains_any(data, keys):
                hits.append(str(path.relative_to(root)))
    return hits


# ---- classification ---------------------------------------------------------------
def classify(result, keys, partials_seen):
    """Returns (verdict, text): PASSED | EXTERNAL_BLOCKED(http status) | FAILED(reason).

    Input is the Core's capability_result: error and http_status. PASSED only on pong."""
    if result is None:
        return 'FAILED', 'no capability result'
    if result.get('ok') is True:
        out = result.get('output') or {}
        text = scrub(str(out.get('text') or ''), keys)
        if 'pong' in text.lower() and out.get('finish_reason') == 'stop' and partials_seen:
            return 'PASSED', 'pong reply, finish stop, partials seen'
        return 'FAILED', f'reply check failed (pong={"pong" in text.lower()}, finish={out.get("finish_reason")}, partials={partials_seen})'
    code = result.get('error') or 'unknown'
    status = result.get('http_status')
    is_int = isinstance(status, int) and not isinstance(status, bool)
    if code == 'http_error':
        if is_int:
            return 'EXTERNAL_BLOCKED', f'http {status}'
        return 'FAILED', 'http_error without http_status: Core does not expose the status (P12 change pending)'
    if code == 'network_unavailable':
        return 'EXTERNAL_BLOCKED', 'network_unavailable'
    if code == 'plugin_error':
        return 'FAILED', 'plugin_error: Core did not pass the provider error code through (P12 change pending)'
    if code == 'key_missing':
        return 'FAILED', 'key_missing: harness did not load the key into the vault'
    return 'FAILED', f'core error {code}'


# ---- Core and IPC -----------------------------------------------------------------
def wire(root, payload):
    with _wire:
        n = next(_counter)
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(15)
        s.connect(str(Path(root) / 'core.sock'))
        s.sendall((json.dumps({'version': 1, 'request_id': f'live_{n}', **payload}) + '\n').encode())
        data = b''
        while not data.endswith(b'\n'):
            chunk = s.recv(65536)
            if not chunk:
                raise RuntimeError('Core disconnected')
            data += chunk
    return json.loads(data)


def core_args(root, bin_path, loopback):
    args = [str(bin_path), '--root', str(root), '--commands-sandbox', '--hub-catalog', str(CATALOG),
            hashlib.sha256(CATALOG.read_bytes()).hexdigest(), '--plugin-python', PYTHON]
    if loopback:
        args.append('--net-allow-loopback')
    return args


def start_core(root, log_path, bin_path, loopback):
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(root.parent), 'XDG_CONFIG_HOME': str(root.parent),
           'XDG_DATA_HOME': str(root.parent), 'XDG_CACHE_HOME': str(root.parent), 'XDG_RUNTIME_DIR': str(root.parent)}
    log = open(log_path, 'wb')
    proc = subprocess.Popen(core_args(root, bin_path, loopback), env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=log)
    until = time.monotonic() + 15
    while True:
        try:
            wire(root, {'op': 'snapshot'})
            return proc
        except (OSError, RuntimeError, ValueError):
            pass
        if proc.poll() is not None:
            raise RuntimeError(f'Core exited rc={proc.returncode}')
        if time.monotonic() > until:
            proc.kill()
            raise TimeoutError('Core startup')
        time.sleep(0.02)


def stop_core(proc):
    proc.terminate()
    try:
        return proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        return proc.wait()


def item(s):
    return next((i for i in s['plugins']['items'] if i['plugin_id'] == PLUGIN), None)


def install_llm(root):
    snap = wire(root, {'op': 'snapshot'})
    h = snap['hub']
    e = next(x for x in h['entries'] if x['plugin_id'] == PLUGIN)
    ok = [wire(root, {'op': 'hub_approve', 'revision': h['approval_revision'], 'plugin_id': PLUGIN,
                      'manifest_sha256': e['manifest_sha256'], 'permissions': e['permissions'],
                      'publisher_unverified_ack': True})['code']]
    stage_upload(str(root), PLUGIN, str(PLUGIN_SRC))
    h = wire(root, {'op': 'snapshot'})['hub']
    ok.append(wire(root, {'op': 'hub_install', 'revision': h['install_revision'], 'plugin_id': PLUGIN,
                          'manifest_sha256': e['manifest_sha256']})['code'])
    rev = wire(root, {'op': 'snapshot'})['plugins']['revision']
    ok.append(wire(root, {'op': 'plugin_enable', 'revision': rev, 'plugin_id': PLUGIN})['code'])
    until = time.monotonic() + 20
    while True:
        s = wire(root, {'op': 'snapshot'})
        if item(s) and item(s)['state'] == 'running':
            return ok
        if time.monotonic() > until:
            raise TimeoutError('llm_engine running')
        time.sleep(0.05)


def chat(root, text, tools, max_tokens, deadline=10000):
    """One invocation. Returns (result, partials_seen_count)."""
    code = wire(root, {'op': 'capability_invoke', 'capability': CAP, 'deadline_ms': deadline,
                       'input': {'messages': [{'role': 'user', 'content': text}], 'tools': tools,
                                 'max_tokens': max_tokens}})['code']
    if code != 'ok':
        return {'ok': False, 'error': f'invoke:{code}'}, 0
    partials = set()
    until = time.monotonic() + deadline / 1000 + 10
    while True:
        s = wire(root, {'op': 'snapshot'})
        if s.get('partial') is not None:
            partials.add(s['partial'])
        if s.get('capability_result') is not None:
            return s['capability_result'], len(partials)
        if time.monotonic() > until:
            return {'ok': False, 'error': 'timeout_waiting_result'}, len(partials)
        time.sleep(0.02)


def tool_outcome(root):
    s = wire(root, {'op': 'snapshot'})
    rows = [p for p in s.get('tool_proposals', []) if p.get('tool') == 'get_time']
    return rows[-1]['state'] if rows else None


# ---- per-provider run -------------------------------------------------------------
def run_provider(spec, keys, workdir, bin_path, loopback, prompt=PONG_PROMPT):
    name = spec['name']
    row = {'provider': name, 'model': spec['model'], 'status': None, 'reason': None, 'calls': 0,
           'keys_tried': 0, 'partials_seen': 0, 'tool_request': None, 'core_error': None,
           'http_status': None, 'blocked_status': None}
    if not keys:
        row.update(status='SKIPPED', reason='no key for this provider in the keys file')
        return row
    root = Path(workdir) / f'core-{name}' / 'core'
    root.parent.mkdir(parents=True)
    proc = start_core(root, root.parent / 'core.stderr', bin_path, loopback)
    try:
        install_llm(root)
        cfg = wire(root, {'op': 'llm_configure', 'revision': wire(root, {'op': 'snapshot'})['llm']['revision'],
                          'provider': spec['core'], 'model': spec['model'], 'custom_url': spec['custom_url'],
                          'cloud_consent': True})
        if cfg['code'] != 'ok':
            row.update(status='SKIPPED', reason=f'Core refuses this provider config: {cfg["code"]}')
            return row
        verdict, detail = 'FAILED', 'no key attempted'
        for key in keys[:MAX_KEYS]:
            if row['calls'] >= MAX_CALLS:
                break
            row['keys_tried'] += 1
            sec = wire(root, {'op': 'secret_set', 'provider': spec['core'], 'key': key})
            if sec['code'] != 'ok':
                verdict, detail = 'FAILED', f'secret_set:{sec["code"]}'
                break
            row['calls'] += 1
            result, partials = chat(root, prompt, False, 16)
            verdict, detail = classify(result, keys, partials)
            row['core_error'] = (result or {}).get('error')
            row['http_status'] = (result or {}).get('http_status')
            row['partials_seen'] = max(row['partials_seen'], partials)
            if verdict == 'EXTERNAL_BLOCKED':
                continue
            break
        if verdict == 'PASSED' and row['calls'] < MAX_CALLS:
            row['calls'] += 1
            result, partials = chat(root, TIME_PROMPT, True, 64)
            tv, td = classify(result, keys, partials) if result and not result.get('ok') else ('PASSED', 'ok')
            row['tool_request'] = {'verdict': tv, 'proposal_state': tool_outcome(root)}
            if tv == 'FAILED':
                verdict, detail = 'FAILED', f'tool call: {td}'
        row.update(status=verdict, reason=detail if verdict != 'PASSED' else None,
                   verdict_detail=detail if verdict == 'PASSED' else None)
        if verdict == 'EXTERNAL_BLOCKED':
            row['reason'] = detail
            row['blocked_status'] = row['http_status'] if row['http_status'] is not None else row['core_error']
        return row
    finally:
        code = stop_core(proc)
        row['core_rc'] = code
        hits = tree_hits(root, keys)
        log_file = root.parent / 'core.stderr'
        if log_file.exists() and contains_any(log_file.read_text(encoding='utf-8', errors='replace'), keys):
            hits.append('core.stderr')
        row['key_hits_outside_vault'] = hits
        if hits:
            row.update(status='FAILED', reason='key found in Core root files: refusing to pass')


def build_result(rows, keys, commit, binary, self_test):
    passed = [r['provider'] for r in rows if r['status'] == 'PASSED']
    failed = [r['provider'] for r in rows if r['status'] == 'FAILED']
    overall = 'PASSED' if passed and not failed else 'FAILED'
    result = {'gate': 'C1_LIVE', 'mode': 'SELF-TEST (loopback fake, not live)' if self_test else 'LIVE',
              'overall': overall, 'providers': rows, 'binary_sha256': binary, 'commit': commit,
              'scope': 'release Core through llm_engine via Hub; keys in memory only',
              'physical_validation': 'NOT_PERFORMED'}
    text = json.dumps(result, indent=2, ensure_ascii=False) + '\n'
    return scrub(text, keys), overall


def write_result(text, path, keys, self_mode):
    path = Path(path).resolve()
    if self_mode and path == RESULT_PATH.resolve():
        raise ArgError('refusing to write the live evidence path in self-test mode')
    if contains_any(text, keys):
        raise ArgError('result contains a loaded key: not written')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


# ---- self-test --------------------------------------------------------------------
def self_test():
    import shutil
    failures = []

    def expect(name, ok, detail=''):
        print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f' :: {detail}'))
        if not ok:
            failures.append(name)

    tmp = Path(tempfile.mkdtemp(prefix='c1live-selftest-'))
    try:
        # 1) argument checks
        for label, path, must in [
            ('relative path rejected', 'keys.json', 'absolute'),
            ('missing file rejected', str(tmp / 'missing.json'), 'does not exist'),
        ]:
            try:
                load_keys(path, repo=BASE)
                expect(label, False, 'accepted')
            except ArgError as exc:
                expect(label, must in str(exc), str(exc))
        inside = tmp / 'in_repo.json'
        inside.write_text('{}')
        inside.chmod(0o600)
        try:
            load_keys(str(inside), repo=tmp)
            expect('file inside repo rejected', False, 'accepted')
        except ArgError as exc:
            expect('file inside repo rejected', 'outside the repository' in str(exc), str(exc))
        wide = tmp / 'wide.json'
        wide.write_text('{"google": ["k-test-0123456789"]}')
        wide.chmod(0o644)
        try:
            load_keys(str(wide), repo=BASE)
            expect('mode 0644 rejected', False, 'accepted')
        except ArgError as exc:
            expect('mode 0644 rejected', 'mode 0600' in str(exc), str(exc))
        good = tmp / 'good.json'
        fake_live_key = 'selftest-key-' + secrets.token_hex(8)
        good.write_text(json.dumps({'google': [fake_live_key]}))
        good.chmod(0o600)
        loaded = load_keys(str(good), repo=BASE)
        expect('valid 0600 file outside repo accepted', loaded == {'google': [fake_live_key]})
        bad_provider = tmp / 'bad_provider.json'
        bad_provider.write_text(json.dumps({'nope': ['abcdefgh12345678']}))
        bad_provider.chmod(0o600)
        try:
            load_keys(str(bad_provider), repo=BASE)
            expect('unknown provider id rejected', False, 'accepted')
        except ArgError as exc:
            expect('unknown provider id rejected', 'unknown provider' in str(exc), str(exc))
        # 2) scrub logic and tree scan
        keys = [fake_live_key]
        expect('scrub removes loaded key', fake_live_key not in scrub(f'a {fake_live_key} b', keys))
        expect('scrub keeps unrelated text', scrub('pong', keys) == 'pong')
        # 3) classifier on synthetic results (no network)
        expect('classify ok pong => PASSED',
               classify({'ok': True, 'output': {'text': 'Pong!', 'finish_reason': 'stop'}}, keys, 2)[0] == 'PASSED')
        expect('classify ok without partials => FAILED',
               classify({'ok': True, 'output': {'text': 'pong', 'finish_reason': 'stop'}}, keys, 0)[0] == 'FAILED')
        expect('classify plugin_error => FAILED (never EXTERNAL_BLOCKED without status)',
               classify({'ok': False, 'error': 'plugin_error'}, keys, 0)[0] == 'FAILED')
        for code in BLOCK_CODES + (500,):
            expect(f'classify http_error http_status {code} => EXTERNAL_BLOCKED',
                   classify({'ok': False, 'error': 'http_error', 'http_status': code}, keys, 0)
                   == ('EXTERNAL_BLOCKED', f'http {code}'))
        expect('classify http_error without http_status => FAILED',
               classify({'ok': False, 'error': 'http_error'}, keys, 0)[0] == 'FAILED')
        expect('classify old "status" field is ignored (http_status is the contract)',
               classify({'ok': False, 'error': 'http_error', 'status': 402}, keys, 0)[0] == 'FAILED')
        expect('classify network_unavailable => EXTERNAL_BLOCKED',
               classify({'ok': False, 'error': 'network_unavailable'}, keys, 0)[0] == 'EXTERNAL_BLOCKED')
        expect('classify key_missing => FAILED (harness, never blocked)',
               classify({'ok': False, 'error': 'key_missing'}, keys, 0)[0] == 'FAILED')
        expect('classify timeout => FAILED (not in the external list)',
               classify({'ok': False, 'error': 'timeout'}, keys, 0)[0] == 'FAILED')
        # 4) full run against the loopback fake provider (Core with --net-allow-loopback, test only)
        srv = subprocess.Popen([PYTHON, '-I', str(FAKE_SRC), '--port', '0'], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=CLEAN_ENV, cwd='/')
        try:
            port = int(srv.stdout.readline())
            spec = {'name': 'selftest-fake', 'core': 'custom', 'model': 'fake/model-1',
                    'custom_url': f'http://127.0.0.1:{port}/v1'}
            rows_key = [fake_live_key]
            row = run_provider(spec, rows_key, tmp, BIN, True)
            expect('fake provider run PASSED through real Core', row['status'] == 'PASSED', row)
            expect('self-test run used at most 3 calls', row['calls'] <= MAX_CALLS, row['calls'])
            expect('self-test key never in run row', not contains_any(json.dumps(row), rows_key))
            text, overall = build_result([row], rows_key, 'self', 'self', True)
            expect('result text has no key', not contains_any(text, rows_key))
            expect('self-test overall PASSED on fake only', overall == 'PASSED')
            write_path = tmp / 'selftest-result.json'
            write_result(text, write_path, rows_key, True)
            expect('result writer writes to temp path', write_path.exists())
            refused = False
            try:
                write_result(text, RESULT_PATH, rows_key, True)
            except ArgError:
                refused = True
            expect('self-test refuses the live evidence path', refused)
            # 5) real Core against the loopback fake returning 402/403/429/503 (fake prefixes e402:..e503:).
            # Where the Core exposes http_status this must be EXTERNAL_BLOCKED; before the P12 Core change
            # the Core reports plugin_error and the run is recorded as IGNORED, never as a pass.
            for code in (402, 403, 429, 503):
                blocked_spec = dict(spec, name=f'selftest-{code}')
                brow = run_provider(blocked_spec, rows_key, tmp, BIN, True, prompt=f'e{code}:x')
                if brow.get('core_error') == 'http_error' and brow.get('http_status') == code:
                    expect(f'real Core http {code} => EXTERNAL_BLOCKED({code})',
                           brow['status'] == 'EXTERNAL_BLOCKED' and brow['blocked_status'] == code, brow)
                elif brow.get('core_error') == 'plugin_error':
                    print(f'IGNORED real Core http {code}: Core reports plugin_error, http_status not exposed yet (P12 pending)')
                    R_IGNORED.append(code)
                    expect(f'real Core http {code} not misclassified as PASSED', brow['status'] == 'FAILED', brow)
                else:
                    expect(f'real Core http {code} classified (core_error={brow.get("core_error")!r})', False, brow)
        finally:
            srv.terminate()
            srv.wait(timeout=5)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if R_IGNORED:
        print(f'SELF-TEST IGNORED: real-Core http_status checks {sorted(R_IGNORED)} not exercised (Core lacks P12 change)')
    print('SELF-TEST ' + ('PASSED' if not failures else f'FAILED: {failures}') + ' (not a live gate; no evidence written)')
    return 0 if not failures else 1


def main(argv):
    if '--self-test' in argv:
        return self_test()
    try:
        keys = load_keys(os.environ.get('GIDEON_LIVE_KEYS_FILE', ''))
    except ArgError as exc:
        print(f'C1_LIVE not run: {exc}. No result file written.', file=sys.stderr)
        return 2
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=BASE, capture_output=True, text=True).stdout.strip()
    binary = hashlib.sha256(BIN.read_bytes()).hexdigest()
    all_keys = [k for values in keys.values() for k in values]
    rows = []
    with tempfile.TemporaryDirectory(prefix='gideon-c1-live-') as workdir:
        for spec in PROVIDERS:
            try:
                row = run_provider(spec, keys.get(spec['name'], []), workdir, BIN, False)
            except Exception as exc:
                row = {'provider': spec['name'], 'model': spec['model'], 'status': 'FAILED',
                       'reason': scrub(f'{type(exc).__name__}: {exc}', all_keys)[:300]}
            rows.append(row)
            print(f"{spec['name']}: {row['status']}" + (f" ({row.get('reason')})" if row.get('reason') else ''))
    text, overall = build_result(rows, all_keys, commit, binary, False)
    if contains_any(text, all_keys):
        print('C1_LIVE: key found in result text; no result file written', file=sys.stderr)
        return 1
    write_result(text, RESULT_PATH, all_keys, False)
    print(f'C1_LIVE overall {overall}; evidence {RESULT_PATH}')
    return 0 if overall == 'PASSED' else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
