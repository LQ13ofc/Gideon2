#!/usr/bin/env python3
"""Private populated test Core for the live UI exploration (scripts/explore_ui.py --root ...).

Run: /usr/bin/python3 -I -B scripts/explore_setup.py [--keep-dir]
     (start it in the background; it stays alive until SIGTERM/SIGINT, then stops the Core and the fakes)
The Qt client that explores this Core (scripts/explore_ui.py) sets GIDEON_UI_NO_ONBOARDING=1 itself, so the first-run
guide does not cover the pages it visits. This script starts no Qt client.

Everything lives in a fresh temp dir (printed as TMP=...): Core root, data dir, private HOME, logs. The repo is
only read: --home is the repo (scripts, target assets), every write goes to --data-dir. Nothing touches
/home/lucas/GideonTeste.

Boot (same flags and helpers as the gates verify_c4.py, verify_s4_share.py, verify_e1_connections.py):
  - Core: target/release/gideon-base, --commands-sandbox, merged Hub catalog (hub-c1 + hub-c4 built at runtime by
    verify_c4.merged_catalog), --plugin-python /usr/bin/python3, --net-allow-loopback, S1 replay on,
    --agent-synthetic, --connections-fake github=<fake URL>.
  - Fakes (loopback, killed at exit): GitHub device-flow fake (tests/fixtures/connections/github_server.py) and
    the OpenAI-shaped fake provider (tests/fixtures/fake_llm_server.py). Never a real service.
  - Plugins: llm_engine (scripted agent_script in plugin settings, never a provider) and the six C4 plugins
    installed, approved and enabled through the Hub.
  - LLM: the custom loopback fake provider configured (secret set, llm_configure).
  - Skill: tests/fixtures/skills/valid/nested_child.json saved, approved and enabled (read-only synthetic tool).
  - Connections: one connected github account (device flow approved on the fake, consent with the pending scopes).
"""
import argparse, json, os, secrets, shutil, signal, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'scripts'))
import verify_c4 as c4  # noqa: E402  (merged_catalog, core_args, write_script, step, PLUGIN_ORDER, wire helpers)
import verify_s4_share as sh  # noqa: E402  (install: approve, upload, install, enable; promote: save, dry run, approve, enable)

BIN = BASE / 'target/release/gideon-base'
PYTHON = '/usr/bin/python3'
LLM = 'llm_engine'
LLM_SRC = BASE / 'tests/fixtures/llm_engine.py'
GITHUB_SRC = BASE / 'tests/fixtures/connections/github_server.py'
SKILL_SRC = BASE / 'tests/fixtures/skills/valid/nested_child.json'
PAYLOADS = BASE / 'tests/fixtures/c4'
ACCOUNT_LABEL = 'Conta de teste'
KEY = 'sk-fake-explore-' + secrets.token_hex(16)  # loopback fake provider only
CLEAN_ENV = {'PATH': '/usr/bin:/bin'}
SCRIPT_STEPS = [
    c4.step('Resposta roteirizada do motor de teste. Nenhum provedor real foi chamado.'),
    c4.step('Segunda resposta roteirizada para a exploracao de interface.'),
]
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PROCS = []  # every process this script started


def need(name, cond, detail=''):
    if not cond:
        raise SystemExit(f'setup failed: {name}: {str(detail)[:300]}')


def call(root, op, **fields):
    """One Core op; `busy` (a poll or network job holds the slot) is retried for up to 20 s, as a client does."""
    until = time.monotonic() + 20
    while True:
        reply = c4.req(root, op, **fields)
        if reply.get('code') != 'busy' or time.monotonic() > until:
            return reply
        time.sleep(0.2)


def wait_for(secs, label, fn):
    until = time.monotonic() + secs
    while True:
        value = fn()
        if value is not None:
            return value
        if time.monotonic() > until:
            raise SystemExit(f'setup timeout: {label}')
        time.sleep(0.05)


def start_github():
    log = open(TMP / 'github.stderr', 'wb')
    proc = subprocess.Popen([PYTHON, '-I', str(GITHUB_SRC), '--port', '0'], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=log, env=CLEAN_ENV, cwd='/')
    PROCS.append(proc)
    line = proc.stdout.readline().decode('ascii', 'replace').strip()
    need('fake github prints PORT', line.startswith('PORT='), line)
    return proc, int(line[len('PORT='):])


def fake_post(port, path, body):
    request = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=json.dumps(body).encode(), method='POST',
                                     headers={'Content-Type': 'application/json'})
    with NO_PROXY.open(request, timeout=10) as reply:
        return reply.status


def connect_github(root, port):
    """add, connect (device code), user approval on the fake, consent with the pending scopes, wait connected."""
    code = call(root, 'connection_add', provider='github', label=ACCOUNT_LABEL)['code']
    need('connection_add', code == 'ok', code)
    cid = next(i['id'] for i in c4.req(root)['connections']['items'] if i['label'] == ACCOUNT_LABEL)
    code = call(root, 'connection_connect', id=cid)['code']
    need('connection_connect', code == 'ok', code)
    item = wait_for(20, 'device code', lambda: next((i for i in c4.req(root)['connections']['items']
                                                   if i['id'] == cid and i.get('user_code') and i.get('pending_scopes')), None))
    status = fake_post(port, '/__control/approve', {'user_code': item['user_code'], 'scopes': item['pending_scopes']})
    need('fake approves the device code', status == 200, status)
    scopes = item['pending_scopes']
    wait_for(25, 'consent accepted', lambda: True if call(root, 'connection_consent', id=cid, scopes=scopes)['code'] == 'ok' else None)
    wait_for(25, 'connected', lambda: True if next((i for i in c4.req(root)['connections']['items']
                                                   if i['id'] == cid and i.get('status') == 'connected'), None) else None)
    return cid


def boot_core(td, catalog, github_port, fake_url):
    root = td / 'core'
    data = td / 'data'
    home = td / 'home'
    for path in (root, home, data):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path, 0o700)  # the Core refuses a root or data dir that other users can read
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'XDG_CONFIG_HOME': str(home), 'XDG_DATA_HOME': str(home),
           'XDG_CACHE_HOME': str(home), 'XDG_RUNTIME_DIR': str(td)}
    extra = ['--agent-synthetic', '--connections-fake', f'github=http://127.0.0.1:{github_port}',
             '--data-dir', str(data)]
    args = c4.core_args(root, catalog, extra, replay=True)
    log = open(td / 'core.stderr', 'wb')
    proc = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log)
    PROCS.append(proc)
    until = time.monotonic() + 20
    while True:
        try:
            c4.req(root)
            break
        except (OSError, RuntimeError, ValueError):
            pass
        need('core alive during startup', proc.poll() is None, f'rc={proc.poll()}')
        need('core startup within 20 s', time.monotonic() < until, 'timeout')
        time.sleep(0.02)
    return proc, root


def descendants(pid):
    table = c4.proc_table()
    children = {}
    for p, (pp, _, _) in table.items():
        children.setdefault(pp, []).append(p)
    found, todo = [], [pid]
    while todo:
        for child in children.get(todo.pop(), []):
            found.append(child)
            todo.append(child)
    return found


def stop_all():
    for proc in reversed(PROCS):
        if proc.poll() is None:
            kids = descendants(proc.pid)
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            for kid in kids:
                try:
                    os.kill(kid, signal.SIGTERM)
                except OSError:
                    pass


def main():
    global TMP
    parser = argparse.ArgumentParser()
    parser.add_argument('--keep-dir', action='store_true', help='keep the temp dir after exit (default: removed)')
    args = parser.parse_args()
    for path in (BIN, LLM_SRC, GITHUB_SRC, SKILL_SRC, PAYLOADS):
        need(f'asset present {path.name}', path.exists(), path)

    TMP = Path(tempfile.mkdtemp(prefix='gideon-explore-'))
    print(f'TMP={TMP}', flush=True)
    try:
        gh_proc, gh_port = start_github()
        llm_fake, llm_url = sh.fake_provider()
        PROCS.append(llm_fake)
        catalog = c4.merged_catalog(TMP, 'explore-catalog')
        # The scripted LLM reads its steps from plugin settings when llm_engine starts (during install below),
        # so the settings file is written into the root before the Core boots.
        (TMP / 'core').mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(TMP / 'core', 0o700)
        c4.write_script(TMP / 'core', {'steps': SCRIPT_STEPS})
        core_proc, root = boot_core(TMP, catalog, gh_port, llm_url)

        sh.install(root, LLM, LLM_SRC)
        for pid in c4.PLUGIN_ORDER:
            sh.install(root, pid, PAYLOADS / f'{pid}.py')

        need('secret set for the loopback fake provider', call(root, 'secret_set', provider='custom', key=KEY)['code'] == 'ok')
        rev = c4.req(root)['llm']['revision']
        code = call(root, 'llm_configure', revision=rev, provider='custom', model='fake/model-1', custom_url=llm_url,
                    local_port=None, fallback=None, cloud_consent=True)['code']
        need('llm_configure', code == 'ok', code)

        manifest = json.loads(SKILL_SRC.read_text(encoding='utf-8'))
        codes = sh.promote(root, manifest)
        need('skill saved, dry run, approved and enabled', all(c == 'ok' for c in codes), codes)

        cid = connect_github(root, gh_port)
        snap = c4.req(root)
        print(json.dumps({'ready': True, 'root': str(root), 'tmp': str(TMP), 'core_pid': core_proc.pid,
                          'github_pid': gh_proc.pid, 'github_port': gh_port, 'llm_fake_url': llm_url,
                          'llm_fake_pid': llm_fake.pid, 'connection_id': cid,
                          'plugins_running': sorted(i['plugin_id'] for i in snap['plugins']['items'] if i['state'] == 'running'),
                          'skills': [i['id'] for i in (snap.get('skills') or {}).get('items', [])]}, ensure_ascii=False),
              flush=True)
        print(f'ROOT={root}', flush=True)
        print('Waiting. Send SIGTERM (kill <pid>) to stop the Core and fakes.', flush=True)

        def leave(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, leave)
        while core_proc.poll() is None:
            time.sleep(0.5)
        print(f'Core exited rc={core_proc.returncode}', flush=True)
    except KeyboardInterrupt:
        print('stopping', flush=True)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr, flush=True)
        raise
    finally:
        stop_all()
        if not args.keep_dir:
            shutil.rmtree(TMP, ignore_errors=True)


if __name__ == '__main__':
    main()
