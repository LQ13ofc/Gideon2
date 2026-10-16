#!/usr/bin/env python3
"""C2 live gate (gate C2_LIVE): real Core, real provider endpoints, keys from GIDEON_LIVE_KEYS_FILE.

GIDEON_LIVE_KEYS_FILE must be an absolute path OUTSIDE the repo, a regular file with mode 0600,
holding JSON {provider: [key, ...]} with provider in google, mistral (keys for mistral go through the
`custom` route, so the file key id is `mistral`). Keys go only through IPC secret_set (memory), never
argv/env/stdout/result file.

Per provider (google: gemini-3.5-flash-lite; mistral: ministral-3b-latest via custom https://api.mistral.ai/v1):
fresh Core root, llm_engine 1.1.0 via Hub (both permissions), secret_set, llm_configure with cloud consent,
then llm_engine.models:
  list      => the selected provider/model is a CERTIFIED recommended entry
  selftest  => ok with features streaming and tool_use 'supported' and source 'probed'
  llm_mark_good, then ONE chat 'Reply with the single word: pong' (max_tokens 16)
Provider request budget: 3 per provider. A selftest is charged 2 (streaming probe + tool probe) before it
runs; the chat is charged 1. A failed selftest spends the last request as a classifier chat, so a blocked
account still gets its real HTTP status.

Statuses:
  PASSED            certified match, selftest supported, pong reply with finish stop and partials seen
  EXTERNAL_BLOCKED  http_error with a numeric http_status (any HTTP status, e.g. 401/402/403/429/503),
                    or network_unavailable. A blocked key moves to the next key while budget allows.
  FAILED            missing key, selected model not certified, selftest failed without an external cause,
                    http_error without http_status, plugin_error, any other Core error, or a reply check failure.
  SKIPPED           no key for this provider in the keys file (no provider request made).

Exit: 0 only if at least one provider PASSED and none FAILED. EXTERNAL_BLOCKED/SKIPPED do not fail.
Exit 2 (no result file) on any key-file or argument problem.
The result never contains a key or a provider body; the scrub check is programmatic (write refused otherwise).

--self-test: labelled SELF-TEST against loopback fakes only (never reads the keys file, never writes
target/evidence/c2-live.json). Exercises the argument checks, the scrub logic, the classifiers, the real Core
pipeline on the local llama.cpp fake (selftest, mark_good, pong chat, partials), the certification gate
(a local candidate must be refused as FAILED), and the real Core http_status classification on the
cloud fake (402/403/429/503 => EXTERNAL_BLOCKED with that status).
"""
import hashlib, http.client, itertools, json, os, secrets, socket, stat, subprocess, sys, tempfile, threading, time
from pathlib import Path
from hub_import import upload as stage_upload

BASE = Path(__file__).resolve().parents[1]
BIN = BASE / 'target/release/gideon-base'
CATALOG = BASE / 'tests/fixtures/hub-c1.json'
PLUGIN_SRC = BASE / 'tests/fixtures/llm_engine.py'
CLOUD_FAKE = BASE / 'tests/fixtures/fake_llm_server.py'
LLAMA_FAKE = BASE / 'tests/fixtures/fake_llama_server.py'
EVIDENCE = BASE / 'target/evidence'
RESULT_PATH = EVIDENCE / 'c2-live.json'
PYTHON = '/usr/bin/python3'
PLUGIN = 'llm_engine'
CAP = 'llm_engine.chat'
MODELS = 'llm_engine.models'
PLUGIN_MARK = b'/plugin/main.py'
BROKER_MARK = b'net_broker.py'
CLEAN_ENV = {'PATH': '/usr/bin:/bin'}
PONG_PROMPT = 'Reply with the single word: pong'
SECRET_BODY = 'SECRET_PROVIDER_BODY'
MAX_KEYS = 3
BUDGET = 3          # provider requests per provider (selftest = 2, chat = 1)
SELFTEST_COST = 2
KNOWN_KEY_IDS = ('google', 'mistral')
PROVIDERS = [
    {'name': 'google', 'key_id': 'google', 'core': 'google', 'model': 'gemini-3.5-flash-lite', 'custom_url': None},
    {'name': 'mistral', 'key_id': 'mistral', 'core': 'custom', 'model': 'ministral-3b-latest',
     'custom_url': 'https://api.mistral.ai/v1'},
]
_counter = itertools.count(1)
_wire = threading.Lock()


class ArgError(Exception):
    pass


# ---- key file and argument checks ------------------------------------------------
def valid_key(key):
    return isinstance(key, str) and 8 <= len(key) <= 256 and all(33 <= ord(c) <= 126 for c in key)


def load_keys(path, repo=BASE):
    """Returns {key_id: [keys]} or raises ArgError. Never echoes key text."""
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
    for key_id, values in data.items():
        if key_id not in KNOWN_KEY_IDS:
            raise ArgError(f'unknown provider id in keys file: {key_id!r}')
        if not isinstance(values, list) or not all(valid_key(v) for v in values):
            raise ArgError(f'keys for {key_id} must be a list of printable keys 8..256 chars (contents not shown)')
        keys[key_id] = values
    return keys


def scrub(text, keys):
    for key in keys:
        text = text.replace(key, '<redacted>')
    return text


def contains_any(text, keys):
    return any(key in text for key in keys)


def tree_hits(root, keys):
    hits = []
    for dirpath, _, files in os.walk(root):
        for name in files:
            path = Path(dirpath) / name
            if path.name == 'secrets.json' and path.parent == Path(root):
                continue
            try:
                data = path.read_bytes().decode('utf-8', 'replace')
            except OSError:
                continue
            if contains_any(data, keys):
                hits.append(str(path.relative_to(root)))
    return hits


# ---- classification ---------------------------------------------------------------
def classify(result, keys, partials_seen):
    """(verdict, text) for one chat with the 'pong' prompt. PASSED | EXTERNAL_BLOCKED | FAILED."""
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
        return 'FAILED', 'http_error without http_status'
    if code == 'network_unavailable':
        return 'EXTERNAL_BLOCKED', 'network_unavailable'
    if code == 'plugin_error':
        return 'FAILED', 'plugin_error: Core did not pass the provider error code through'
    if code == 'key_missing':
        return 'FAILED', 'key_missing: harness did not load the key into the vault'
    return 'FAILED', f'core error {code}'


def selftest_verdict(result):
    """(ok, reason) for llm_engine.models selftest: streaming and tool_use must be supported, source probed."""
    if not result or result.get('ok') is not True:
        return False, f'selftest error {(result or {}).get("error")}'
    out = result.get('output') or {}
    feats = out.get('features') or {}
    if feats.get('streaming') != 'supported':
        return False, f'streaming {feats.get("streaming")}'
    if feats.get('tool_use') != 'supported':
        return False, f'tool_use {feats.get("tool_use")}'
    if out.get('source') != 'probed':
        return False, f'source {out.get("source")}'
    return True, 'streaming and tool_use supported (probed)'


def certified_match(recommended, spec):
    """The recommended entry the selected provider/model maps to, when it is certified; else None."""
    for entry in recommended:
        if entry.get('provider') == spec['core'] and entry.get('model') == spec['model'] \
                and entry.get('certification', {}).get('state') == 'certified':
            return entry
    return None


# ---- Core and IPC -----------------------------------------------------------------
def wire(root, payload):
    with _wire:
        n = next(_counter)
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(30)
        s.connect(str(Path(root) / 'core.sock'))
        s.sendall((json.dumps({'version': 1, 'request_id': f'c2live_{n}', **payload}) + '\n').encode())
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
    steps = [wire(root, {'op': 'hub_approve', 'revision': h['approval_revision'], 'plugin_id': PLUGIN,
                         'manifest_sha256': e['manifest_sha256'], 'permissions': e['permissions'],
                         'publisher_unverified_ack': True})['code']]
    stage_upload(str(root), PLUGIN, str(PLUGIN_SRC))
    h = wire(root, {'op': 'snapshot'})['hub']
    steps.append(wire(root, {'op': 'hub_install', 'revision': h['install_revision'], 'plugin_id': PLUGIN,
                             'manifest_sha256': e['manifest_sha256']})['code'])
    rev = wire(root, {'op': 'snapshot'})['plugins']['revision']
    steps.append(wire(root, {'op': 'plugin_enable', 'revision': rev, 'plugin_id': PLUGIN})['code'])
    until = time.monotonic() + 20
    while True:
        s = wire(root, {'op': 'snapshot'})
        if item(s) and item(s)['state'] == 'running':
            return steps
        if time.monotonic() > until:
            raise TimeoutError('llm_engine running')
        time.sleep(0.05)


def invoke(root, capability, inp, deadline):
    """Returns (code, capability_result or None)."""
    code = wire(root, {'op': 'capability_invoke', 'capability': capability, 'deadline_ms': deadline,
                       'input': inp})['code']
    if code != 'ok':
        return code, None
    until = time.monotonic() + deadline / 1000 + 10
    while True:
        s = wire(root, {'op': 'snapshot'})
        if s.get('capability_result') is not None:
            return code, s['capability_result']
        if time.monotonic() > until:
            return code, {'ok': False, 'error': 'timeout_waiting_result'}
        time.sleep(0.02)


def chat(root, text, max_tokens=16, deadline=10000):
    """One chat invocation. Returns (result, partials_seen_count)."""
    code = wire(root, {'op': 'capability_invoke', 'capability': CAP, 'deadline_ms': deadline,
                       'input': {'messages': [{'role': 'user', 'content': text}], 'tools': False,
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
            return s['capability_result'], streamed_count(s['capability_result'], partials)
        if time.monotonic() > until:
            return {'ok': False, 'error': 'timeout_waiting_result'}, len(partials)
        time.sleep(0.02)


def streamed_count(result, partials):
    """Partials seen by polling; a fast reply can finish between polls, so the final capability_result.partial
    equal to the output text (the Core accumulates the streamed text there) is counted as streaming evidence."""
    if partials:
        return len(partials)
    text = ((result or {}).get('output') or {}).get('text')
    return 1 if (result or {}).get('partial') and (result or {}).get('partial') == text else 0


def configure(root, spec, consent, local_port=None):
    rev = wire(root, {'op': 'snapshot'})['llm']['revision']
    return wire(root, {'op': 'llm_configure', 'revision': rev, 'provider': spec['core'], 'model': spec['model'],
                       'custom_url': spec.get('custom_url'), 'local_port': local_port, 'cloud_consent': consent})


def mark_good(root):
    rev = wire(root, {'op': 'snapshot'})['llm']['revision']
    return wire(root, {'op': 'llm_mark_good', 'revision': rev})['code']


def models_list(root):
    items, offset = [], 0
    while True:
        code, res = invoke(root, MODELS, {'action': 'list', 'tab': 'recommended', 'offset': offset, 'limit': 6}, 10000)
        if not res or res.get('ok') is not True:
            return None
        out = res.get('output') or {}
        page = out.get('items') or []
        items += page
        offset += len(page)
        if not page or offset >= (out.get('total') or 0):
            return items


# ---- per-provider run -------------------------------------------------------------
def run_provider(spec, keys, workdir, bin_path, loopback, require_certified=True, local_spec=None):
    """Models flow for one provider. keys: the list for spec['key_id']. Returns a row dict."""
    name = spec['name']
    row = {'provider': name, 'model': spec['model'], 'status': None, 'reason': None, 'provider_requests': 0,
           'keys_tried': 0, 'partials_seen': 0, 'selected_recommended': None, 'selftest': None,
           'mark_good': None, 'chat_error': None, 'http_status': None, 'blocked_status': None,
           'core_rc': None, 'key_hits_outside_vault': []}
    if not keys:
        row.update(status='SKIPPED', reason='no key for this provider in the keys file')
        return row
    root = Path(workdir) / f'core-{name}' / 'core'
    root.parent.mkdir(parents=True)
    proc = start_core(root, root.parent / 'core.stderr', bin_path, loopback)
    all_keys = list(keys)
    try:
        install_llm(root)
        cfg_spec = dict(spec, custom_url=spec.get('custom_url'))
        cfg = configure(root, cfg_spec, True, local_port=local_spec and local_spec.get('local_port'))
        if cfg['code'] != 'ok':
            row.update(status='FAILED', reason=f'Core refuses this provider config: {cfg["code"]}')
            return row
        recommended = models_list(root)
        if recommended is None:
            row.update(status='FAILED', reason='models.list failed')
            return row
        match = certified_match(recommended, spec)
        if match is None and require_certified:
            row.update(status='FAILED', reason='selected provider/model is not a certified recommended entry')
            return row
        row['selected_recommended'] = match['id'] if match else None
        verdict, detail = 'FAILED', 'no key attempted'
        budget = BUDGET
        local = spec['core'] in ('local', 'ollama')  # keyless loopback routes: no vault slot, no secret_set
        attempts = [None] if local else keys[:MAX_KEYS]
        for key in attempts:
            if budget < SELFTEST_COST:
                break
            row['keys_tried'] += 0 if local else 1
            if key is not None:
                sec = wire(root, {'op': 'secret_set', 'provider': spec['core'], 'key': key})
                if sec['code'] != 'ok':
                    verdict, detail = 'FAILED', f'secret_set:{sec["code"]}'
                    break
            budget -= SELFTEST_COST
            row['provider_requests'] += SELFTEST_COST
            _, st = invoke(root, MODELS, {'action': 'selftest'}, 30000)
            st_ok, st_reason = selftest_verdict(st)
            row['selftest'] = {'ok': st_ok, 'reason': st_reason, 'error': (st or {}).get('error')}
            if st_ok:
                row['mark_good'] = mark_good(root)
                if row['mark_good'] != 'ok':
                    verdict, detail = 'FAILED', f'llm_mark_good:{row["mark_good"]}'
                    break
                result, partials = chat(root, PONG_PROMPT, 16)
                budget -= 1
                row['provider_requests'] += 1
                verdict, detail = classify(result, all_keys, partials)
                row['chat_error'] = (result or {}).get('error')
                row['http_status'] = (result or {}).get('http_status')
                row['partials_seen'] = max(row['partials_seen'], partials)
                if verdict == 'EXTERNAL_BLOCKED':
                    row['blocked_status'] = row['http_status'] if row['http_status'] is not None else row['chat_error']
                    if budget >= SELFTEST_COST:
                        continue
                break
            # selftest failed: spend one request as a classifier so a blocked account keeps its status
            if budget < 1:
                verdict, detail = 'FAILED', f'selftest failed ({st_reason}); no request left to classify'
                break
            budget -= 1
            row['provider_requests'] += 1
            result, partials = chat(root, PONG_PROMPT, 16)
            cv, cd = classify(result, all_keys, partials)
            row['chat_error'] = (result or {}).get('error')
            row['http_status'] = (result or {}).get('http_status')
            if cv == 'EXTERNAL_BLOCKED':
                verdict, detail = 'EXTERNAL_BLOCKED', cd
                row['blocked_status'] = row['http_status'] if row['http_status'] is not None else row['chat_error']
                continue
            verdict, detail = 'FAILED', f'selftest failed ({st_reason}); classifier chat: {cd}'
            break
        row.update(status=verdict, reason=None if verdict == 'PASSED' else detail)
        if verdict == 'PASSED':
            row['reason'] = None
            row['verdict_detail'] = detail
        if verdict == 'EXTERNAL_BLOCKED':
            row['reason'] = detail
        return row
    finally:
        row['core_rc'] = stop_core(proc)
        hits = tree_hits(root, all_keys)
        log_file = root.parent / 'core.stderr'
        if log_file.exists() and contains_any(log_file.read_text(encoding='utf-8', errors='replace'), all_keys):
            hits.append('core.stderr')
        row['key_hits_outside_vault'] = hits
        if hits:
            row.update(status='FAILED', reason='key found in Core root files: refusing to pass')


def build_result(rows, keys, commit, binary, self_test, scope):
    passed = [r['provider'] for r in rows if r['status'] == 'PASSED']
    failed = [r['provider'] for r in rows if r['status'] == 'FAILED']
    overall = 'PASSED' if passed and not failed else 'FAILED'
    result = {'gate': 'C2_LIVE', 'mode': 'SELF-TEST (loopback fakes, not live)' if self_test else 'LIVE',
              'overall': overall, 'providers': rows, 'binary_sha256': binary, 'commit': commit,
              'scope': scope, 'budget_per_provider': BUDGET, 'physical_validation': 'NOT_PERFORMED'}
    text = json.dumps(result, indent=2, ensure_ascii=False) + '\n'
    return scrub(text, keys), overall


def write_result(text, path, keys, self_mode):
    path = Path(path).resolve()
    if self_mode and path == RESULT_PATH.resolve():
        raise ArgError('refusing to write the live evidence path in self-test mode')
    if contains_any(text, keys) or SECRET_BODY in text:
        raise ArgError('result contains a key or a provider body: not written')
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

    tmp = Path(tempfile.mkdtemp(prefix='c2live-selftest-'))
    srv_cloud = srv_llama = None
    try:
        # 1) argument checks
        for label, path, must in [('relative path rejected', 'keys.json', 'absolute'),
                                  ('missing file rejected', str(tmp / 'missing.json'), 'does not exist')]:
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
        fake_key = 'selftest-key-' + secrets.token_hex(8)
        good.write_text(json.dumps({'google': [fake_key]}))
        good.chmod(0o600)
        expect('valid 0600 file outside repo accepted', load_keys(str(good), repo=BASE) == {'google': [fake_key]})
        bad_id = tmp / 'bad_id.json'
        bad_id.write_text(json.dumps({'openrouter': ['abcdefgh12345678']}))
        bad_id.chmod(0o600)
        try:
            load_keys(str(bad_id), repo=BASE)
            expect('provider id outside google/mistral rejected (C2 live scope)', False, 'accepted')
        except ArgError as exc:
            expect('provider id outside google/mistral rejected (C2 live scope)', 'unknown provider' in str(exc), str(exc))
        # 2) scrub and classifiers (synthetic, no network)
        keys = [fake_key]
        expect('scrub removes loaded key', fake_key not in scrub(f'a {fake_key} b', keys))
        expect('scrub keeps unrelated text', scrub('pong', keys) == 'pong')
        expect('classify pong with partials => PASSED',
               classify({'ok': True, 'output': {'text': 'Pong!', 'finish_reason': 'stop'}}, keys, 2)[0] == 'PASSED')
        expect('classify pong without partials => FAILED',
               classify({'ok': True, 'output': {'text': 'pong', 'finish_reason': 'stop'}}, keys, 0)[0] == 'FAILED')
        expect('classify plugin_error => FAILED', classify({'ok': False, 'error': 'plugin_error'}, keys, 0)[0] == 'FAILED')
        for code in (401, 402, 403, 429, 503):
            expect(f'classify http_error status {code} => EXTERNAL_BLOCKED',
                   classify({'ok': False, 'error': 'http_error', 'http_status': code}, keys, 0)
                   == ('EXTERNAL_BLOCKED', f'http {code}'))
        expect('classify http_error without status => FAILED', classify({'ok': False, 'error': 'http_error'}, keys, 0)[0] == 'FAILED')
        expect('classify network_unavailable => EXTERNAL_BLOCKED',
               classify({'ok': False, 'error': 'network_unavailable'}, keys, 0)[0] == 'EXTERNAL_BLOCKED')
        expect('classify key_missing => FAILED', classify({'ok': False, 'error': 'key_missing'}, keys, 0)[0] == 'FAILED')
        ok_st = {'ok': True, 'output': {'features': {'streaming': 'supported', 'tool_use': 'supported'}, 'source': 'probed'}}
        expect('selftest supported + probed => ok', selftest_verdict(ok_st)[0] is True)
        expect('selftest tool_use unsupported => not ok',
               selftest_verdict({'ok': True, 'output': {'features': {'streaming': 'supported', 'tool_use': 'unsupported'},
                                                        'source': 'probed'}})[0] is False)
        expect('selftest error => not ok', selftest_verdict({'ok': False, 'error': 'model_selftest_failed'})[0] is False)
        rec = [{'id': 'x', 'provider': 'custom', 'model': 'ministral-3b-latest', 'certification': {'state': 'certified'}},
               {'id': 'y', 'provider': 'local', 'model': 'gguf-local', 'certification': {'state': 'candidate'}}]
        expect('certified match for mistral spec', (certified_match(rec, PROVIDERS[1]) or {}).get('id') == 'x')
        expect('candidate local is not a certified match', certified_match(rec, {'core': 'local', 'model': 'gguf-local'}) is None)
        # 3) real Core on the llama.cpp fake: models pipeline (selftest, mark_good, pong chat, partials)
        srv_llama = subprocess.Popen([PYTHON, '-I', str(LLAMA_FAKE), '--port', '0'], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=CLEAN_ENV, cwd='/')
        lport = int(srv_llama.stdout.readline())
        local_spec = {'name': 'selftest-local', 'key_id': 'google', 'core': 'local', 'model': 'gguf-local',
                      'custom_url': None, 'local_port': lport}
        row = run_provider(local_spec, [fake_key], tmp, BIN, True, require_certified=False, local_spec=local_spec)
        expect('loopback llama fake: models pipeline PASSED (selftest, mark_good, pong, partials)',
               row['status'] == 'PASSED' and row['selftest'] and row['selftest']['ok'] is True
               and row['mark_good'] == 'ok', row)
        expect('loopback run used at most 3 provider requests', row['provider_requests'] <= BUDGET, row['provider_requests'])
        expect('self-test key never in run row', not contains_any(json.dumps(row), [fake_key]))
        local_cand = dict(local_spec, name='selftest-candidate')
        cand = run_provider(local_cand, [fake_key], tmp, BIN, True, require_certified=True, local_spec=local_cand)
        expect('local candidate refused by the certification gate (FAILED, no provider request)',
               cand['status'] == 'FAILED' and cand['provider_requests'] == 0, cand)
        text, overall = build_result([row, cand], [fake_key], 'self', 'self', True, 'self-test')
        expect('self-test result text has no key', not contains_any(text, [fake_key]))
        refused = False
        try:
            write_result(text, RESULT_PATH, [fake_key], True)
        except ArgError:
            refused = True
        expect('self-test refuses the live evidence path', refused)
        # 4) real Core http_status classification on the cloud fake (chat only, loopback test mode)
        srv_cloud = subprocess.Popen([PYTHON, '-I', str(CLOUD_FAKE), '--port', '0'], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=CLEAN_ENV, cwd='/')
        cport = int(srv_cloud.stdout.readline())
        for code in (402, 403, 429, 503):
            root = tmp / f'http-{code}' / 'core'
            root.parent.mkdir(parents=True)
            proc = start_core(root, root.parent / 'core.stderr', BIN, True)
            try:
                install_llm(root)
                spec = {'core': 'custom', 'model': 'fake/model-1', 'custom_url': f'http://127.0.0.1:{cport}/v1'}
                configure(root, spec, True)
                wire(root, {'op': 'secret_set', 'provider': 'custom', 'key': fake_key})
                result, partials = chat(root, f'e{code}:x', 16)
                verdict, detail = classify(result, [fake_key], partials)
                expect(f'real Core http {code} => EXTERNAL_BLOCKED({code})',
                       verdict == 'EXTERNAL_BLOCKED' and detail == f'http {code}', (verdict, detail, result))
                expect(f'real Core http {code}: provider body absent from result',
                       SECRET_BODY not in json.dumps(result), result)
            finally:
                stop_core(proc)
    finally:
        for srv in (srv_cloud, srv_llama):
            if srv is not None:
                srv.terminate()
                srv.wait(timeout=5)
        shutil.rmtree(tmp, ignore_errors=True)
    print('SELF-TEST ' + ('PASSED' if not failures else f'FAILED: {failures}') + ' (not a live gate; no evidence written)')
    return 0 if not failures else 1


def main(argv):
    if '--self-test' in argv:
        return self_test()
    try:
        keys = load_keys(os.environ.get('GIDEON_LIVE_KEYS_FILE', ''))
    except ArgError as exc:
        print(f'C2_LIVE not run: {exc}. No result file written.', file=sys.stderr)
        return 2
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=BASE, capture_output=True, text=True).stdout.strip()
    binary = hashlib.sha256(BIN.read_bytes()).hexdigest()
    all_keys = [k for values in keys.values() for k in values]
    rows = []
    with tempfile.TemporaryDirectory(prefix='gideon-c2-live-') as workdir:
        for spec in PROVIDERS:
            try:
                row = run_provider(spec, keys.get(spec['key_id'], []), workdir, BIN, False)
            except Exception as exc:
                row = {'provider': spec['name'], 'model': spec['model'], 'status': 'FAILED',
                       'reason': scrub(f'{type(exc).__name__}: {exc}', all_keys)[:300]}
            rows.append(row)
            print(f"{spec['name']}: {row['status']}" + (f" ({row.get('reason')})" if row.get('reason') else ''))
    text, overall = build_result(rows, all_keys, commit, binary, False,
                                 'release Core through llm_engine 1.1.0 via Hub; keys in memory only; real providers')
    if contains_any(text, all_keys) or SECRET_BODY in text:
        print('C2_LIVE: key or provider body found in result text; no result file written', file=sys.stderr)
        return 1
    write_result(text, RESULT_PATH, all_keys, False)
    print(f'C2_LIVE overall {overall}; evidence {RESULT_PATH}')
    return 0 if overall == 'PASSED' else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
