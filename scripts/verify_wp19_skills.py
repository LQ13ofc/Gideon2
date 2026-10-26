#!/usr/bin/env python3
"""WP-19 SKILL-03 gate: the Core fetches the public skills index through the broker and keeps it as the import index.

Real release Core (target/release/gideon-base) with a private root and HOME. The index base is a loopback fake
(`--skill-index-base http://127.0.0.1:PORT`, test only, needs `--net-allow-loopback`) that serves the same path as
https://raw.githubusercontent.com/LQ13ofc/Gideon2/main/skills-index.json. Checks:
  A  valid index: op skill_index_fetch is ok, event skill_index_saved, the local index equals the repository file,
     mode 0600, no temporary file left.
  B  malformed body: event skill_index_failed, the local index keeps the valid bytes of A.
  C  HTTP 404: event skill_index_failed, the local index keeps the valid bytes of A.
  D  a base that is not loopback (or not the raw host) is refused at start (no Core runs).
Usage: scripts/verify_wp19_skills.py [--live]
  --live also runs one fetch against the real raw.githubusercontent.com path and prints its outcome. The file is
  reachable only after the owner pushes skills-index.json; the outcome is reported, not asserted.
Writes nothing into the repository. Stdlib only.
"""
import argparse, http.server, json, os, shutil, socket, stat, subprocess, sys, tempfile, threading, time, traceback
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
BIN = BASE / 'target/release/gideon-base'
INDEX_PATH = '/LQ13ofc/Gideon2/main/skills-index.json'
REPO_INDEX = BASE / 'skills-index.json'
PYTHON = '/usr/bin/python3'
RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond)))
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else f'  {detail}'), flush=True)


class Fake:
    """Serves INDEX_PATH with the body and status of `mode`; counts requests."""
    def __init__(self):
        self.mode = 'valid'
        self.hits = 0
        self.valid = REPO_INDEX.read_bytes()
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                fake.hits += 1
                if self.path != INDEX_PATH or fake.mode == 'missing':
                    code, body = 404, b'Not Found'
                elif fake.mode == 'invalid':
                    code, body = 200, b'{"format": 2, "skills": "nope"}'
                else:
                    code, body = 200, fake.valid
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def url(self):
        return f'http://127.0.0.1:{self.port}'


def wire(root, payload, request_id=None):
    request_id = request_id or f'wp19_{time.monotonic_ns()}'
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(20)
        s.connect(str(Path(root) / 'core.sock'))
        s.sendall((json.dumps({'version': 1, 'request_id': request_id, **payload}) + '\n').encode())
        data = b''
        while not data.endswith(b'\n'):
            chunk = s.recv(1 << 20)
            if not chunk:
                raise RuntimeError('Core disconnected')
            data += chunk
    return json.loads(data)


def snap(root):
    return wire(root, {'op': 'snapshot'})


def wait_event(root, request_id, secs):
    until = time.monotonic() + secs
    while time.monotonic() < until:
        for ev in snap(root).get('events') or []:
            if ev.get('request_id') == request_id and str(ev.get('kind', '')).startswith('skill_index_'):
                return ev['kind']
        time.sleep(0.2)
    return None


def start_core(root, home, base, extra=()):
    args = [str(BIN), '--root', str(root), '--home', str(home), '--commands-sandbox', '--plugin-python', PYTHON,
            '--net-allow-loopback', *extra]
    if base is not None:
        args += ['--skill-index-base', base]
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            env={'PATH': '/usr/bin:/bin', 'HOME': str(home), 'XDG_CONFIG_HOME': str(home),
                                 'XDG_DATA_HOME': str(home), 'XDG_CACHE_HOME': str(home), 'XDG_RUNTIME_DIR': str(home)})
    until = time.monotonic() + 60
    while time.monotonic() < until:
        if proc.poll() is not None:
            raise RuntimeError(f'core exited {proc.returncode}: {proc.stderr.read().decode(errors="replace")[-400:]}')
        if (Path(root) / 'core.sock').exists():
            try:
                snap(root)
                return proc
            except (OSError, RuntimeError, json.JSONDecodeError):
                pass
        time.sleep(0.2)
    proc.kill()
    raise RuntimeError('core did not start')


def stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def fetch(root):
    rid = f'wp19_fetch_{time.monotonic_ns()}'
    reply = wire(root, {'op': 'skill_index_fetch'}, rid)
    code = reply.get('code')
    return code, (wait_event(root, rid, 40) if code == 'ok' else None)


def run(live):
    if not BIN.is_file():
        raise SystemExit(f'missing {BIN}: cargo build --release --offline first')
    td = Path(tempfile.mkdtemp(prefix='wp19skills-'))
    os.chmod(td, 0o700)
    fake = Fake()
    proc = None
    try:
        home = td / 'home'
        home.mkdir(mode=0o700)
        (home / 'scripts').symlink_to(BASE / 'scripts')  # the Core runs scripts/net_broker.py under its home
        root = td / 'core'
        imports = home / 'skill-imports'
        proc = start_core(root, home, fake.url())
        valid = fake.valid

        code, kind = fetch(root)
        check('A valid index: skill_index_fetch is ok and the event is skill_index_saved', code == 'ok' and kind == 'skill_index_saved', (code, kind))
        saved = imports / 'index.json'
        check('A the local index equals the repository skills-index.json', saved.is_file() and saved.read_bytes() == valid)
        check('A the local index is mode 0600', saved.is_file() and stat.S_IMODE(saved.stat().st_mode) == 0o600)
        check('A no temporary file is left behind', not (imports / 'index.json.tmp').exists())
        stop(proc)
        proc = None

        # Restart with a malformed body: the valid local index must stay as it was.
        fake.mode = 'invalid'
        proc = start_core(root, home, fake.url())
        code, kind = fetch(root)
        check('B malformed body: event skill_index_failed', code == 'ok' and kind == 'skill_index_failed', (code, kind))
        check('B malformed body keeps the valid local index byte for byte', saved.read_bytes() == valid)
        stop(proc)
        proc = None

        fake.mode = 'missing'
        proc = start_core(root, home, fake.url())
        code, kind = fetch(root)
        check('C HTTP 404: event skill_index_failed', code == 'ok' and kind == 'skill_index_failed', (code, kind))
        check('C HTTP 404 keeps the valid local index', saved.read_bytes() == valid)
        stop(proc)
        proc = None

        # Refused at start: a base that is not loopback, or not the raw host.
        for base in ('http://example.com:80', 'https://evil.example', 'http://10.0.0.5:8080'):
            r = subprocess.run([str(BIN), '--root', str(td / f'refused-{abs(hash(base))}'), '--home', str(home),
                                '--net-allow-loopback', '--skill-index-base', base], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
            check(f'D base {base} is refused at start', r.returncode != 0, r.returncode)

        if live:
            live_root = td / 'live'
            live_home = td / 'live-home'
            live_home.mkdir(mode=0o700)
            (live_home / 'scripts').symlink_to(BASE / 'scripts')
            proc = start_core(live_root, live_home, None)
            code, kind = fetch(live_root)
            print(f'LIVE skill_index_fetch against raw.githubusercontent.com: op={code} event={kind} '
                  f'local_index={"present" if (live_home / "skill-imports" / "index.json").exists() else "absent"}')
            stop(proc)
            proc = None
    except Exception:
        traceback.print_exc()
        check('gate ran without exception', False)
    finally:
        if proc is not None:
            stop(proc)
        fake.server.shutdown()
        shutil.rmtree(td, ignore_errors=True)
    failed = [name for name, ok in RESULTS if not ok]
    print(json.dumps({'gate': 'WP19_SKILLS', 'passed': sum(1 for _, ok in RESULTS if ok), 'failed': len(failed),
                      'failures': failed}, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    sys.exit(run(args.live))
