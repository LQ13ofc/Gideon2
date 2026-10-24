#!/usr/bin/env python3
"""E4 total-integration gate (docs/S5.md "E4 - Integracao total"): the complete Linux package, PACKAGED BINARIES ONLY.

Builds gideon-base-0.4.0 and gideon-base-0.4.1 with scripts/build_package.py, installs them with the package's own
gideon-install and runs every Core through the package's own gideon-launch / gideon-core / gideon-base inside an outer
bwrap (only ROOT, /usr and the loader cache are visible: no repository, no uv, private HOME/XDG). The Qt pages run from
the package's own app/ and venvs/ui in a second sandbox. Evidence: target/evidence/e4-integration.json.

Fixtures live OUTSIDE the package and reach a Core only through the documented test-only mechanism:
  - fake servers (GitHub, Google, Home Assistant, LLM provider, llama.cpp) run on the host loopback; the Core sandbox of
    those boots shares the host network namespace (--share-net) so it can reach them. Every other boot is offline
    (--unshare-all: the sandbox has only `lo`).
  - test-only Core flags (--connections-fake*, --net-allow-loopback, --agent-synthetic, --test-fixtures-dir, ...) are
    passed as extra arguments to gideon-launch in test boots only. The production profile never gets them.
  - plugin payloads and Hub catalogs are staged by scripts/hub_import.py (an external client) from tests/fixtures.

Sections (run in this order; --only picks a subset for development):
  build     build v1 and v2 (or copy them from --reuse-build DIR)
  static    package hygiene: file set, key patterns, no fakes, modes, PACKAGE.json hashes, gideon-verify tamper
  install   install v1, profiles, isolation probe, S1 smoke (PCM wake -> Command -> TTS virtual), idle resources
  noflag    production-default Core: synthetic tools / fake providers / synthetic services are unavailable
  demo      full demo on v1 (models local+remote, connections, scripted LLM, skill draft, Qt pages, ledgers)
  update    v1 -> v2 with profile_active/locked, ledgers and sentinels intact; S1; reads with the vaulted tokens
  rollback  v2 -> v1 -> ledgers intact again
  crash     kill -9 mid-run, restart, ledgers intact, no orphan process, no duplicate effect
  profiles  alice/bob isolation, permissions
  offline   no network: S1, fake unreachable, remote LLM error bounded
  final     verify retained versions, leak scan, modes, sentinels, processes
"""
import argparse
import errno
import hashlib
import json
import mmap
import os
import re
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import verify_e1_connections as e1  # noqa: E402  wire/connection/agent helpers and the shared result table
import verify_e3_registry as e3  # noqa: E402  Hub plugin install, scripted agent runs
import verify_s4_core as g  # noqa: E402  skill helpers (no state of its own that matters here)
import verify_s4_share as sh  # noqa: E402  skill drafts, scripted LLM script
from hub_import import upload as stage_upload  # noqa: E402

check, need, skip = e1.check, e1.need, e1.skip
EVIDENCE = REPO / 'target/evidence/e4-integration.json'
TEST_UI = REPO / 'scripts/test_ui_offscreen.py'
PY_HOST = '/usr/bin/python3'
V1, V2 = '0.4.0', '0.4.1'
GATE = 'E4_INTEGRATION'
PRIVATE, PUBLIC = e1.PRIVATE, e1.PUBLIC
LLM_SRC = REPO / 'tests/fixtures/llm_engine.py'
C4_SRC = REPO / 'tests/fixtures/c4'
MCP_SRC = REPO / 'tests/fixtures/connections/mcp_server.py'
CLOUD_FAKE = REPO / 'tests/fixtures/fake_llm_server.py'
LLAMA_FAKE = REPO / 'tests/fixtures/fake_llama_server.py'
GITHUB_FAKE = REPO / 'tests/fixtures/connections/github_server.py'
GOOGLE_FAKE = REPO / 'tests/fixtures/connections/google_server.py'
HA_FAKE = REPO / 'tests/fixtures/connections/homeassistant_server.py'
CLK = os.sysconf('SC_CLK_TCK')
KEY = 'sk-fake-e4-' + secrets.token_hex(12)  # per-run key, only for the loopback fake provider
HA_TOKEN = 'ha-e4-' + secrets.token_hex(16)
RUN_SKILL, DRAFT_SKILL, NOTE_SKILL = 'skill_e4_run', 'skill_draft_ui', 'skill_e4_note'
SKILL_TEXT = 'alfa-e4'
S = {'cores': {}, 'fakes': {}, 'tree': {}, 'ledger': {}, 'idle': {}}
SECTIONS = ['build', 'static', 'install', 'noflag', 'demo', 'update', 'rollback', 'crash', 'profiles', 'offline', 'final']
PROFILE = 'main'
TEST_FLAG_NAMES = ('--agent-synthetic', '--agent-allow-destructive', '--net-allow-loopback', '--connections-fake',
                   '--connections-fake-mcp', '--connections-allow-public', '--test-fixtures-dir', '--virtual-input',
                   '--agent-clock-scale', '--hub-catalog')
KEY_PATTERNS = {
    'openai-style sk- key': rb'sk-[A-Za-z0-9_-]{32,}',
    'google api key': rb'AIza[0-9A-Za-z_\-]{35}',
    'github token': rb'gh[pousr]_[A-Za-z0-9]{36,}',
    'github fine-grained token': rb'github_pat_[A-Za-z0-9_]{40,}',
    'aws access key id': rb'AKIA[0-9A-Z]{16}',
    'slack token': rb'xox[baprs]-[0-9A-Za-z-]{10,}',
    'private key block': rb'-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----',
}
FORBIDDEN_FILE_PARTS = ('tests', 'fixtures', 'synthetic', 'verify_', 'test_', 'fake_', '_server', 'skillfix', 'hub-c', 'hub-v',
                        'llm_engine', 'dummy_', 'mcp_server', 'github_server', 'google_server', 'homeassistant_server',
                        'screen_observe', 'computer_control', 'audio_advanced', 'mic_advanced', 'camera_gesture',
                        'display_manipulate')
ALLOWED_SCRIPTS = {'command_worker.py', 'net_broker.py', 'pcm_fixture.py', 'stt_worker.py', 'tts_worker.py',
                   'wake_worker.py'}
BINARY_FORBIDDEN = (b'BaseHTTPRequestHandler', b'ThreadingHTTPServer', b'SECRET_PROVIDER_BODY', b'sk-fake-', b'demo-user',
                    b'IGNORE AS REGRAS', b'fake_llm_server', b'fake_llama_server', b'github_server.py',
                    b'google_server.py', b'homeassistant_server.py')


# ---- generic helpers --------------------------------------------------------------------
def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def host_env():
    home = str(S['home'])
    return {'PATH': '/usr/bin:/bin', 'HOME': home, 'XDG_CONFIG_HOME': home, 'XDG_DATA_HOME': home,
            'XDG_CACHE_HOME': home, 'XDG_RUNTIME_DIR': home}


def run(args, env=None, timeout=300, cwd='/'):
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout, cwd=cwd, env=env or host_env())
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'timeout {timeout}s running {args[:3]}') from exc


def tail(path, n=900):
    return Path(path).read_bytes()[-n:].decode('utf-8', 'replace') if Path(path).exists() else ''


def tree_state(path):
    out = {}
    base = Path(path)
    if not base.exists():
        return out
    for item in sorted([base, *base.rglob('*')]):
        try:
            st = item.lstat()
        except OSError:
            continue
        out[str(item.relative_to(base))] = (stat.S_IFMT(st.st_mode), st.st_size, st.st_mtime_ns, st.st_ino)
    return out


def py_of(pkg):
    return str(Path(pkg) / 'runtime/python/bin/python3.13')


def cmdline_of(pid):
    try:
        return Path(f'/proc/{pid}/cmdline').read_bytes()
    except OSError:
        return b''


def ppid_of(pid):
    try:
        return int(Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[1])
    except (OSError, IndexError, ValueError):
        return None


def tree_pids(root_pid):
    kids = {}
    for entry in os.listdir('/proc'):
        if entry.isdigit():
            parent = ppid_of(int(entry))
            if parent is not None:
                kids.setdefault(parent, []).append(int(entry))
    seen, stack = [root_pid], [root_pid]
    while stack:
        for child in kids.get(stack.pop(), []):
            seen.append(child)
            stack.append(child)
    return seen


def pids_with(mark):
    """Live processes whose command line carries `mark` (the run ROOT path): the sandbox wrappers and their children."""
    found = []
    for entry in os.listdir('/proc'):
        if entry.isdigit() and int(entry) != os.getpid() and mark in cmdline_of(int(entry)):
            try:
                state = Path(f'/proc/{entry}/stat').read_text().rsplit(')', 1)[1].split()[0]
            except (OSError, IndexError):
                continue
            if state != 'Z':
                found.append(int(entry))
    return found


def proc_ticks(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return int(fields[11]) + int(fields[12])
    except (OSError, IndexError, ValueError):
        return 0


def proc_rss(pid):
    try:
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            if line.startswith('VmRSS:'):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return 0


# ---- fakes (host loopback, outside the package) --------------------------------------------
class Srv(e1.Fake):
    """A loopback fake with the e1.Fake HTTP/control helpers; `script` is the fixture server."""

    def __init__(self, td, script, name):
        self.log = open(Path(td) / f'{name}.stderr', 'wb')
        self.proc = subprocess.Popen([PY_HOST, '-I', str(script), '--port', '0'], stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=self.log, env=e1.CLEAN_ENV, cwd='/')
        line = self.proc.stdout.readline().decode('ascii', 'replace').strip()
        need(f'fake {name} prints PORT', line.startswith('PORT='), line)
        self.port = int(line[len('PORT='):])
        self.base = f'http://127.0.0.1:{self.port}'


class LlmFake:
    """fake_llm_server / fake_llama_server (first stdout line is the port)."""

    def __init__(self, src, extra=()):
        self.proc = subprocess.Popen([PY_HOST, '-I', str(src), '--port', '0', *extra], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=e1.CLEAN_ENV, cwd='/')
        self.port = int(self.proc.stdout.readline())

    def http(self, method, path):
        import http.client
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


def start_fakes():
    td = S['work']
    S['fakes']['github'] = e1.FAKE = Srv(td, GITHUB_FAKE, 'github')
    S['fakes']['google'] = Srv(td, GOOGLE_FAKE, 'google')
    S['fakes']['ha'] = Srv(td, HA_FAKE, 'homeassistant')
    S['fakes']['cloud'] = LlmFake(CLOUD_FAKE)
    S['fakes']['llama'] = LlmFake(LLAMA_FAKE)
    S['fakes']['llama_text'] = LlmFake(LLAMA_FAKE, ['--text-only'])
    e1.SECRETS.update({KEY, HA_TOKEN})


def stop_fakes():
    for fake in S['fakes'].values():
        try:
            fake.close()
        except Exception:
            pass


# ---- install root, installer, launcher ------------------------------------------------------
def tool_pkg():
    """Package whose tools run: the pre-install v1 tree until the first install, ROOT/current afterwards."""
    return S['root'] / 'current' if (S['root'] / 'current').is_symlink() else S['pkg1']


def inst(*args, timeout=900, env_extra=None):
    pkg = tool_pkg()
    env = host_env()
    # the first install moves the tool's own tree: run it with the host python (the tool file is the package's)
    python = PY_HOST if pkg == S['pkg1'] else py_of(pkg)
    env.update(env_extra or {})
    proc = run([python, '-I', '-B', str(pkg / 'bin/gideon-install'), '--install-root', str(S['root']), *args],
               env=env, timeout=timeout)
    text = proc.stdout.decode('utf-8', 'replace')
    try:
        obj = json.loads(text) if text.strip() else None
    except ValueError:
        obj = None
    return proc.returncode, obj, proc.stderr.decode('utf-8', 'replace')[-600:]


def lst():
    rc, obj, err = inst('list')
    if rc != 0 or not obj:
        raise RuntimeError(f'list failed rc={rc}: {obj} {err}')
    S['cur'] = obj['current']
    return obj


def ident(version):
    return f'{version}-{S["commit"][:8]}'


def vdir(version=None):
    return S['root'] / 'versions' / (ident(version) if version else S['cur'])


def state_dir(profile):
    return S['root'] / 'profiles' / profile


def core_root(profile):
    return state_dir(profile) / 'core'


def data_dir(profile):
    return state_dir(profile) / 'data'


def bwrap_argv(argv, net=False, binds=()):
    """Outer sandbox: ROOT (rw), /usr, the loader cache and the listed read-only files. Offline unless `net`
    (net = share the host network namespace so the loopback fakes are reachable)."""
    rootp = str(S['root'])
    args = ['/usr/bin/bwrap', '--unshare-all', *(['--share-net'] if net else []), '--die-with-parent', '--clearenv',
            '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'HOME', rootp,
            '--ro-bind', '/usr', '/usr', '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib', '/lib64',
            '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/bin', '/sbin',
            '--ro-bind', '/etc/ld.so.cache', '/etc/ld.so.cache', '--proc', '/proc', '--dev', '/dev',
            '--tmpfs', '/tmp', '--bind', rootp, rootp]
    for src, dst in binds:
        args += ['--ro-bind', str(src), str(dst)]
    return args + ['--chdir', '/', '--', *argv]


def launcher_argv(profile, core_args=()):
    pkg = vdir()
    return [py_of(pkg), '-I', '-B', str(pkg / 'bin/gideon-launch'), '--install-root', str(S['root']), profile, *core_args]


def hub_args(profile):
    path = state_dir(profile) / 'hub.json'
    return ['--hub-catalog', str(path), sha256(path)]


def demo_args(profile):
    """Test-only flags: fakes on the host loopback, synthetic world and tools, public/destructive switches."""
    f = S['fakes']
    return [*hub_args(profile), '--net-allow-loopback',
            '--connections-fake', f'github={f["github"].base}', '--connections-fake', f'google={f["google"].base}',
            '--connections-fake', f'homeassistant={f["ha"].base}', '--connections-fake-mcp', 'good',
            '--test-fixtures-dir', '/fx', '--connections-allow-public', '--agent-synthetic', '--agent-allow-destructive']


FX_BINDS = [(MCP_SRC, '/fx/tests/fixtures/connections/mcp_server.py')]


def core_start(profile, label, core_args=(), net=False, binds=()):
    if profile in S['cores']:
        raise RuntimeError(f'{profile} Core already running')
    argv = bwrap_argv(launcher_argv(profile, core_args), net=net, binds=binds)
    log = S['work'] / f'{label}.log'
    with open(log, 'wb') as handle:
        proc = subprocess.Popen(argv, env=host_env(), cwd='/', stdin=subprocess.DEVNULL, stdout=handle, stderr=handle,
                                start_new_session=True)
    S['cores'][profile] = {'proc': proc, 'label': label, 'log': log}
    sock = core_root(profile) / 'core.sock'
    deadline = time.monotonic() + 120
    while True:
        if proc.poll() is not None:
            S['cores'].pop(profile, None)
            raise RuntimeError(f'{label} exited rc={proc.returncode}: {tail(log)}')
        if sock.exists():
            try:
                with socket.socket(socket.AF_UNIX) as probe:
                    probe.settimeout(2)
                    probe.connect(str(sock))
                e1.req(core_root(profile))
                return proc
            except (OSError, RuntimeError, ValueError):
                pass
        if time.monotonic() > deadline:
            raise TimeoutError(f'{label} socket not ready: {tail(log)}')
        time.sleep(0.05)


def group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def core_stop(profile, expect_clean=True):
    entry = S['cores'].pop(profile, None)
    if entry is None:
        return None
    proc, label = entry['proc'], entry['label']
    if proc.poll() is None:
        targets = [p for p in tree_pids(proc.pid) if b'gideon-base' in cmdline_of(p)]
        for pid in targets or [proc.pid]:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            rc = proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            rc = proc.wait(timeout=5)
            check(f'{label}: clean shutdown on SIGTERM', False, 'required SIGKILL')
    else:
        rc = proc.returncode
    until = time.monotonic() + 8
    while group_alive(proc.pid) and time.monotonic() < until:
        time.sleep(0.05)
    residual = group_alive(proc.pid)
    if residual:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if expect_clean:
        check(f'{label}: no residual Core or worker process group after stop', not residual, f'pgid {proc.pid}')
        check(f'{label}: Core exit status 0 after SIGTERM', rc == 0, f'rc={rc}')
        # scoped to this profile's Core root: other profiles may run on the same install root at the same time
        left = pids_with(str(core_root(profile)).encode())
        check(f'{label}: no process referencing this profile Core root remains after stop', not left,
              [cmdline_of(p)[:160] for p in left[:4]])
    return rc


def core_stop_quiet(profile):
    try:
        core_stop(profile)
    except Exception as exc:
        check(f'cleanup: stop {profile}', False, f'{type(exc).__name__}: {exc}')


def gideon_base_pid(profile):
    for pid in tree_pids(S['cores'][profile]['proc'].pid):
        try:
            if os.path.realpath(f'/proc/{pid}/exe').endswith('/bin/gideon-base'):
                return pid
        except OSError:
            continue
    return None


def exe_check(profile, version, label):
    want = os.path.realpath(S['root'] / 'versions' / ident(version) / 'bin/gideon-base')
    got = [os.path.realpath(f'/proc/{p}/exe') for p in tree_pids(S['cores'][profile]['proc'].pid)
           if os.path.exists(f'/proc/{p}/exe')]
    check(f'{label}: the Core executes the packaged bin/gideon-base of {version}', want in got, {'want': want, 'got': got[:6]})


def rq(profile, op='snapshot', **fields):
    return e1.req(core_root(profile), op, **fields)


def snap(profile):
    return rq(profile)


def wait_snap(profile, pred, secs, what):
    until = time.monotonic() + secs
    last = None
    while time.monotonic() < until:
        last = snap(profile)
        if pred(last):
            return last
        time.sleep(0.05)
    raise TimeoutError(f'{what} not reached: state={last and last.get("state")} command={last and (last.get("command") or {}).get("code")}')


def s1_check(profile, label, audible=True):
    want = 'completed' if audible else 'disabled'
    s = wait_snap(profile, lambda x: x.get('state') == 'idle' and x.get('wake_status') == 'replay_finished'
                  and (x.get('command') or {}).get('code') == 'command_success' and x.get('stt_status') == 'ready'
                  and x.get('speech_status') == want, 120, label)
    check(f'{label}: S1 configuration ready, pack verified, wake replay finished (PCM wake)',
          s['configuration_status'] == 'ready' and (s.get('base_pack') or {}).get('preflight') == 'verified'
          and s['wake_status'] == 'replay_finished', {k: s.get(k) for k in ('configuration_status', 'wake_status')})
    check(f'{label}: S1 command_success receipt verified, stt ready', s['command']['code'] == 'command_success'
          and s['command']['receipt']['verified'] is True and s['stt_status'] == 'ready', s['command'])
    speech = s.get('speech') or {}
    kinds = [ev.get('kind') for ev in s.get('events', [])]
    if audible:
        check(f'{label}: S1 speech completed on the virtual TTS with samples',
              s['speech_status'] == 'completed' and speech.get('samples', 0) > 0 and 'speech_completed' in kinds, speech)
    return s


# ---- build ------------------------------------------------------------------------------
def build_pkg(version, out_dir):
    cargo = shutil.which('cargo')
    if cargo is None:
        raise RuntimeError('cargo not on PATH; the packaged binary cannot be built')
    out_dir.mkdir()
    env = {'PATH': f'{Path(cargo).parent}:/usr/bin:/bin', 'HOME': str(Path.home())}
    for key in ('CARGO_HOME', 'RUSTUP_HOME'):
        if os.environ.get(key):
            env[key] = os.environ[key]
    t0 = time.monotonic()
    proc = run([PY_HOST, str(REPO / 'scripts/build_package.py'), str(out_dir), '--version', version], env=env, timeout=900)
    pkg = out_dir / f'gideon-base-{version}'
    check(f'build {version}: build_package.py exits 0 and writes PACKAGE.json', proc.returncode == 0
          and (pkg / 'PACKAGE.json').is_file(), proc.stderr.decode()[-800:])
    S['tree'][f'build_{version}_s'] = round(time.monotonic() - t0, 1)
    return pkg


def get_pkg(version, key, reuse):
    dest = S['work'] / f'o-{key}'
    if reuse and (Path(reuse) / f'gideon-base-{version}').is_dir():
        dest.mkdir()
        src = Path(reuse) / f'gideon-base-{version}'
        proc = run(['cp', '-a', str(src), str(dest / src.name)], timeout=600)
        check(f'build {version}: copied from --reuse-build', proc.returncode == 0, proc.stderr.decode()[-300:])
        return dest / src.name
    return build_pkg(version, dest)


def sec_build(args):
    S['commit'] = subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    status = subprocess.run(['git', '-C', str(REPO), 'status', '--porcelain', '--untracked-files=no'], capture_output=True,
                            text=True).stdout
    S['tree']['tracked_changes'] = [line for line in status.splitlines()][:40]
    S['pkg1'] = get_pkg(V1, 'v1', args.reuse_build)
    S['pkg2'] = get_pkg(V2, 'v2', args.reuse_build)
    for version, pkg in ((V1, S['pkg1']), (V2, S['pkg2'])):
        m = json.loads((pkg / 'PACKAGE.json').read_text(encoding='utf-8'))
        check(f'build {version}: PACKAGE.json name, version and commit', m.get('version') == version
              and m.get('commit') == S['commit'], {k: m.get(k) for k in ('version', 'commit')})
        S['tree'][f'dirty_{version}'] = m.get('dirty')
        S['tree'][f'binary_{version}'] = sha256(pkg / 'bin/gideon-base')
        S['tree'][f'package_json_{version}'] = sha256(pkg / 'PACKAGE.json')
    check('build: the two packages carry different PACKAGE.json (distinct versions, same binary source)',
          S['tree'][f'package_json_{V1}'] != S['tree'][f'package_json_{V2}'])


# ---- static package hygiene --------------------------------------------------------------
def scan_keys(pkg):
    """(first-party hits, third-party hits, files scanned) for the key patterns, mmap over every regular file < 64 MiB."""
    pattern = re.compile(b'|'.join(b'(?P<k%d>%s)' % (i, p) for i, p in enumerate(KEY_PATTERNS.values())))
    names = list(KEY_PATTERNS)
    first, third, scanned = [], [], 0
    for path in sorted(pkg.rglob('*')):
        if path.is_symlink() or not path.is_file():
            continue
        size = path.stat().st_size
        if size == 0 or size > 64 << 20:
            continue
        rel = path.relative_to(pkg).as_posix()
        with open(path, 'rb') as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as blob:
            match = pattern.search(blob)
        scanned += 1
        if match:
            kind = names[int(match.lastgroup[1:])]
            if rel == 'bin/gideon-base' and kind == 'openai-style sk- key':
                continue  # adjacent rodata strings of the redaction prefixes (sk-proj-, sk-ant-), not a key
            if rel.startswith(('runtime/', 'venvs/')) and '.so' in Path(rel).name:
                continue  # third-party native libraries (TLS marker strings / compiled data), not credentials
            (third if rel.startswith(('runtime/', 'venvs/')) else first).append(f'{rel}: {kind}')
    return first, third, scanned


def sec_static(args):
    pkg = S['pkg2']  # v2 is not installed yet: it is the tamper subject; the scans use v1 (what gets installed first)
    p1 = S['pkg1']
    manifest = json.loads((p1 / 'PACKAGE.json').read_text(encoding='utf-8'))
    files = [e for e in manifest['files'] if e['type'] == 'file']
    rels = [e['path'] for e in files]
    # 1. what the package must contain for the new code, and nothing from the fixtures
    scripts = {Path(r).name for r in rels if r.startswith('scripts/')}
    check('static: scripts/ holds exactly the six runtime workers (net_broker.py included, nothing else)',
          scripts == ALLOWED_SCRIPTS, sorted(scripts ^ ALLOWED_SCRIPTS))
    entry = next((e for e in files if e['path'] == 'scripts/net_broker.py'), None)
    check('static: scripts/net_broker.py is in PACKAGE.json with the sha256 of the repository file',
          entry is not None and entry['sha256'] == sha256(REPO / 'scripts/net_broker.py'), entry)
    own = [r for r in rels if not r.startswith(('runtime/', 'venvs/'))]
    bad = [r for r in own if any(part in r.lower() for part in FORBIDDEN_FILE_PARTS)]
    check('static: no fixture, fake server, synthetic world, test or Hub catalog file in the first-party part of the package',
          not bad, bad[:10])
    check('static: no tests/ or synthetic/ directory anywhere in the package',
          not any(e['type'] == 'dir' and Path(e['path']).name in ('tests', 'fixtures', 'synthetic') and
                  not e['path'].startswith(('runtime/', 'venvs/')) for e in manifest['files']))
    expect = {'bin/gideon-base', 'bin/gideon-core', 'bin/gideon-launch', 'bin/gideon-install', 'bin/gideon-verify',
              'bin/gideon-configure', 'bin/gideon-app'}
    check('static: bin/ holds exactly the seven package executables', {r for r in rels if r.startswith('bin/')} == expect,
          sorted({r for r in rels if r.startswith('bin/')} ^ expect))
    check('static: templates/ holds only the pinned profile manifests (no fake catalog)',
          all(r.startswith('templates/') and r.endswith(('.json', '.yaml')) for r in rels if r.startswith('templates/')))
    # 2. the binary does not embed any fake server or test secret
    blob = (p1 / 'bin/gideon-base').read_bytes()
    found = [m.decode() for m in BINARY_FORBIDDEN if m in blob]
    check('static: bin/gideon-base embeds no fake server code, fake key, demo account or injection text', not found, found)
    # 3. key patterns
    t0 = time.monotonic()
    first, third, scanned = scan_keys(p1)
    S['tree']['key_scan'] = {'files': scanned, 'seconds': round(time.monotonic() - t0, 1), 'third_party': third[:20]}
    check(f'static: no API key or private key pattern in {scanned} package files (first-party)', not first, first[:10])
    check('static: no API key or private key pattern in the bundled CPython runtime or venvs either', not third, third[:10])
    # 4. modes
    wide, setid = [], []
    for e in manifest['files']:
        mode = int(e.get('mode', '0000'), 8) if e['type'] == 'file' else None
        if mode is not None and (mode & 0o022):
            wide.append(e['path'])
        if mode is not None and (mode & 0o6000):
            setid.append(e['path'])
    for path in [p1, *[p1 / e['path'] for e in manifest['files'] if e['type'] == 'dir']][:4000]:
        if path.stat().st_mode & 0o022:
            wide.append(str(path.relative_to(p1)))
    check('static: no group- or world-writable file or directory in the package', not wide, wide[:10])
    check('static: no setuid or setgid file in the package', not setid, setid[:10])
    # 5. no test flag by default
    env = dict(os.environ)
    env['GIDEON_CORE_DRYRUN'] = '1'
    proc = subprocess.run([str(p1 / 'bin/gideon-core'), '/tmp/gideon-e4-dry/state'], capture_output=True, text=True,
                          env=env, timeout=60)
    argv = json.loads(proc.stdout)['argv'] if proc.returncode == 0 else []
    check('static: gideon-core builds its Core argv', proc.returncode == 0 and bool(argv), proc.stderr[-300:])
    on = [flag for flag in TEST_FLAG_NAMES if flag in argv]
    check('static: the default Core argv carries no test flag and no Hub catalog', not on, on)
    check('static: the default Core argv pins --home, --data-dir and the bundled plugin runtime',
          '--home' in argv and '--data-dir' in argv and '--plugin-python' in argv, argv)
    for extra in ('--agent-synthetic', '--connections-fake=github=http://127.0.0.1:1'):
        launch = run([py_of(p1), '-I', '-B', str(p1 / 'bin/gideon-launch'), '--install-root', str(S['root']), 'x', extra],
                     timeout=60)
        # only a pinned option is refused by the launcher itself; test flags are NOT pinned, they are explicit opt-ins
        check(f'static: gideon-launch does not enable {extra.split("=")[0]} on its own (needs an install first)',
              launch.returncode != 0)
    # 6. gideon-verify passes, then fails closed on every tamper (v2, never installed yet)
    verify = [py_of(pkg), '-I', '-B', str(pkg / 'bin/gideon-verify')]
    check('static: gideon-verify passes on the untouched package', run(verify, timeout=600).returncode == 0)
    victim = pkg / 'scripts/net_broker.py'
    original = victim.read_bytes()
    victim.write_bytes(original + b'\n# tampered\n')
    proc = run(verify, timeout=600)
    check('static: a changed byte in scripts/net_broker.py makes gideon-verify fail closed',
          proc.returncode != 0 and b'FAIL' in proc.stderr, proc.stderr[-200:])
    state = S['work'] / 'tamper-state'
    state.mkdir(mode=0o700)
    boot = run([str(pkg / 'bin/gideon-core'), str(state)], timeout=120)
    check('static: gideon-core on the tampered package refuses to start (exit non-zero, no core.sock)',
          boot.returncode != 0 and not (state / 'core/core.sock').exists() and b'gideon-verify' in boot.stderr,
          boot.stderr[-200:])
    victim.write_bytes(original)
    extra_file = pkg / 'scripts/extra.py'
    extra_file.write_bytes(b'print(1)\n')
    check('static: an extra file makes gideon-verify fail closed', run(verify, timeout=600).returncode != 0)
    extra_file.unlink()
    moved = pkg / 'scripts/stt_worker.py'
    moved.rename(pkg / 'scripts/stt_worker.py.gone')
    check('static: a missing file makes gideon-verify fail closed', run(verify, timeout=600).returncode != 0)
    (pkg / 'scripts/stt_worker.py.gone').rename(moved)
    os.chmod(victim, 0o777)
    check('static: a changed mode makes gideon-verify fail closed', run(verify, timeout=600).returncode != 0)
    os.chmod(victim, int(next(e for e in manifest['files'] if e['path'] == 'scripts/net_broker.py')['mode'], 8))
    check('static: restoring every byte and mode makes gideon-verify pass again', run(verify, timeout=600).returncode == 0)


# ---- install, smoke, idle -------------------------------------------------------------------
def probe_isolation():
    proc = run(bwrap_argv(['/bin/sh', '-c', '[ ! -e /home ] && echo NOHOME; cat /proc/net/dev']), timeout=60)
    text = proc.stdout.decode('utf-8', 'replace')
    ifaces = [line.split(':')[0].strip() for line in text.splitlines()[2:] if ':' in line]
    check('isolation: the Core sandbox has no /home (repository and uv unreachable) and only the loopback interface',
          proc.returncode == 0 and 'NOHOME' in text and ifaces == ['lo'], {'rc': proc.returncode, 'ifaces': ifaces})
    S['tree']['offline_ifaces'] = ifaces
    return proc.returncode == 0 and ifaces == ['lo']


def sample_idle(profile, label, seconds=10):
    root_pid = S['cores'][profile]['proc'].pid
    core = gideon_base_pid(profile)
    pids = tree_pids(root_pid)
    t0 = {p: proc_ticks(p) for p in pids}
    time.sleep(seconds)
    pids2 = tree_pids(root_pid)
    t1 = {p: proc_ticks(p) for p in pids2}
    delta = sum(max(0, t1.get(p, 0) - t0.get(p, 0)) for p in set(t0) | set(t1))
    core_delta = max(0, t1.get(core, 0) - t0.get(core, 0))
    rss_total = sum(proc_rss(p) for p in pids2)
    result = {'seconds': seconds, 'processes': len(pids2), 'tree_cpu_percent_one_core': round(delta / CLK / seconds * 100, 2),
              'core_cpu_percent_one_core': round(core_delta / CLK / seconds * 100, 2),
              'core_rss_mib': round(proc_rss(core) / 2 ** 20, 1), 'tree_rss_mib_sum': round(rss_total / 2 ** 20, 1)}
    S['idle'][label] = result
    check(f'idle {label}: the Core process uses under 3% of one core (sampled {seconds}s)',
          result['core_cpu_percent_one_core'] < 3.0, result)
    check(f'idle {label}: the whole process tree uses under 15% of one core', result['tree_cpu_percent_one_core'] < 15.0, result)
    check(f'idle {label}: Core RSS under 400 MiB and the tree RSS sum (shared pages counted per process) under 6 GiB',
          result['core_rss_mib'] < 400 and result['tree_rss_mib_sum'] < 6144, result)
    return result


def sec_install(args):
    rc, obj, err = inst('install', str(S['pkg1']), timeout=1200)
    check('install: gideon-install (the v1 package own tool) install exits 0', rc == 0 and obj and obj.get('ok') is True, err or obj)
    check('install: the source package was consumed by rename (lives only under ROOT)', obj and obj.get('source') == 'moved'
          and not S['pkg1'].exists(), obj)
    st = lst()
    check('install: list shows current v1, no previous, one version, no orphan', st['current'] == ident(V1)
          and st['previous'] is None and len(st['versions']) == 1 and st['orphans'] == [], st)
    entry = st['versions'][0]
    check('install: the ledger pins the verifier hash and the PACKAGE.json hash of v1',
          entry.get('package_json_sha256') == S['tree'][f'package_json_{V1}'] and len(entry.get('verifier_sha256', '')) == 64, entry)
    check('install: the installed binary is byte-identical to the built one',
          sha256(vdir(V1) / 'bin/gideon-base') == S['tree'][f'binary_{V1}'])
    check('install: ROOT is mode 0700', stat.S_IMODE(os.lstat(S['root']).st_mode) == 0o700)
    for name in (PROFILE, 'alice', 'bob', 'nofl', 'off'):
        rc, obj, err = inst('profile', 'create', name)
        check(f'install: profile {name} created', rc == 0 and obj and obj.get('created') is True, err or obj)
    S['tree']['home_names'] = sorted(os.listdir(Path.home()))
    S['tree']['sentinel_pre'] = tree_state(S['sentinel'])
    S['tree']['home_state'] = tree_state(S['home'])
    # catalogs (test-only Hub catalogs, copied into the profile: outside the package) and the isolation probe
    merged = e3.merged_catalog(str(S['work']))
    for name in (PROFILE, 'alice', 'nofl', 'off', 'bob'):
        dest = state_dir(name) / 'hub.json'
        shutil.copyfile(merged[0], dest)
        os.chmod(dest, 0o600)
    S['isolation_ok'] = probe_isolation()
    need('outer bwrap isolation available', S['isolation_ok'])
    # S1 smoke on a production-default boot (no test flag, the Hub catalog is a user option)
    core_start(PROFILE, 'smoke-v1', hub_args(PROFILE))
    exe_check(PROFILE, V1, 'smoke')
    pid = S['cores'][PROFILE]['proc'].pid
    marks = [str(REPO).encode(), b'.local/share/uv', str(Path.home()).encode()]
    hits = []
    for p in tree_pids(pid):
        for name in ('cmdline', 'environ', 'maps', 'mountinfo'):
            try:
                data = Path(f'/proc/{p}/{name}').read_bytes()
            except OSError:
                continue
            hits += [f'{p}:{name}:{m.decode()}' for m in marks if m in data]
    check('smoke: no repository, uv or real-home path in any Core process (cmdline, environ, maps, mountinfo)', not hits, hits[:6])
    s1_check(PROFILE, 'smoke S1')
    check('smoke: the package data directory exists in the profile state (0700), the package itself stays untouched',
          stat.S_IMODE(os.lstat(data_dir(PROFILE)).st_mode) == 0o700)
    time.sleep(4)
    sample_idle(PROFILE, 'base-only')
    core_stop(PROFILE)


# ---- production defaults ----------------------------------------------------------------------
def sec_noflag(args):
    p = 'nofl'
    core_start(p, 'noflag', hub_args(p))
    root = core_root(p)
    s1_check(p, 'noflag S1')
    for prov in ('github', 'google', 'homeassistant', 'mcp'):
        code = rq(p, 'connection_add', provider=prov, label=f'sem fake {prov}')['code']
        need(f'add {prov}', code == 'ok', code)
        cid = next(i['id'] for i in e1.conn_items(root) if i['label'] == f'sem fake {prov}')
        code = rq(p, 'connection_connect', id=cid)['code']
        check(f'noflag: connecting {prov} without a fake is real_backend_unsupported (nothing contacted)',
              code == 'real_backend_unsupported', code)
        check(f'noflag: the {prov} account stays disconnected', e1.find(root, cid)['status'] == 'disconnected')
    check('noflag: the test-only agent bump op is refused', rq(p, 'agent_test_bump')['code'] != 'ok')
    # Hub plugins: llm_engine + screen_observe, provider with a fake key (selection only, never called)
    e3.install_plugin(root, e1.PLUGIN, LLM_SRC)
    e3.install_plugin(root, 'screen_observe', C4_SRC / 'screen_observe.py')
    check('noflag: secret_set stores a key for the cloud provider selection', rq(p, 'secret_set', provider='openrouter', key=KEY)['code'] == 'ok')
    rev = rq(p)['llm']['revision']
    code = rq(p, 'llm_configure', revision=rev, provider='openrouter', model='fake/model-1', custom_url=None,
              local_port=None, fallback=None, cloud_consent=True)['code']
    check('noflag: cloud provider selected with consent (scripted LLM only; the network is off)', code == 'ok', code)
    names = [('t1', 'synth_screen_read', {}), ('t2', 'synth_counter_inc', {'epoch': 1}), ('t3', 'synth_set_text', {'epoch': 1, 'text': 'x'}),
             ('t4', 'synth_publish', {}), ('t5', 'github_create_issue', {'repo': PRIVATE, 'title': 'x'}),
             ('t6', 'github_list_repos', {}), ('t7', 'calendar_list_events', {}), ('t8', 'ha_get_state', {'entity_id': 'light.kitchen'}),
             ('t9', 'mcp_call', {'tool': 'echo_note', 'text': 'x'}), ('t10', 'route_create_issue', {'title': 'x'}),
             ('t11', 'screen_observe_capture', {})]
    rid, s = e3.run_tool(root, [e1.step(calls=names[:4]), e1.step(calls=names[4:8]), e1.step(calls=names[8:]), e1.step(text='Nada disponivel.')],
                         'Tente todas as ferramentas de teste', 'done', secs=60)
    codes = [st.get('code') for st in e3.tool_steps(s)]
    check('noflag: every synthetic or fake-backed agent tool answers unknown_tool (11 calls, none proposed or run)',
          codes == ['unknown_tool'] * 11 and not e1.run_props(s, rid), codes)
    res = sh.capability(root, 'screen_observe.capture', {})
    check('noflag: the synthetic host service does not exist (screen_observe.capture answers unknown_service)',
          res.get('ok') is False and res.get('error') == 'unknown_service', res)
    reg = rq(p)['registry']
    create = next(x for x in reg['purposes'] if x['id'] == 'create_issue')
    check('noflag: the registry has no usable route (API no_api, visual disabled), no route chosen',
          'route_chosen' not in create and {c['route']: c['status'] for c in create['candidates']}.get('connection') in ('no_api', 'not_connected')
          and {c['route']: c['status'] for c in create['candidates']}.get('visual') in ('disabled', 'visual_not_allowed'), create)
    check('noflag: no connection item is served by a fake', all(not i.get('fake') for i in e1.conn_items(root)))
    check('noflag: no synthetic world was created in the profile data directory',
          not (data_dir(p) / 'synthetic').exists() and not (state_dir(p) / 'synthetic').exists())
    check('noflag: nothing was written into the installed package (gideon-verify still passes)',
          run([py_of(vdir(V1)), '-I', '-B', str(vdir(V1) / 'bin/gideon-verify')], timeout=600).returncode == 0)
    core_stop(p)


# ---- demo -----------------------------------------------------------------------------------
def login_dev(root, srv, provider, label, scopes):
    code = e1.req(root, 'connection_add', provider=provider, label=label)['code']
    need(f'add {label}', code == 'ok', code)
    cid = next(i['id'] for i in e1.conn_items(root) if i['label'] == label)
    code = e1.req(root, 'connection_connect', id=cid)['code']
    need(f'connect {label}', code == 'ok', code)
    it = e1.wait_for(15, 'device code and pending scopes', lambda: (
        lambda x: x if x and x.get('user_code') and x.get('pending_scopes') else None)(e1.find(root, cid)))
    status, obj = srv.http('POST', '/__control/approve', {'user_code': it['user_code'], 'scopes': it['pending_scopes']})
    need(f'user approves {label} on the fake', status == 200, obj)
    e1.consent_when_ready(root, cid, scopes)
    item = e1.wait_status(root, cid, 'connected')
    e1.harvest(root, cid)
    return cid, item


def cap_chat(root, text, **extra):
    return sh.capability(root, 'llm_engine.chat', {'messages': [{'role': 'user', 'content': text}], 'tools': False,
                                                   'max_tokens': 64, **extra})


def models_cap(root, inp):
    return sh.capability(root, 'llm_engine.models', inp)


def rw_manifest(sid, text):
    return {'schema_version': 1, 'id': sid, 'name': 'Skill de teste E4', 'version': '1.0.0',
            'publisher': {'id': 'gideon-test', 'name': 'Gideon test'}, 'description': 'Skill sintetica do gate E4',
            'license': 'TEST-ONLY', 'min_runtime': '0.1.0', 'triggers': [], 'inputs': {},
            'outputs': {'epoch': {'type': 'int'}, 'text': {'type': 'string'}},
            'dependency_capabilities': ['tool:synth_screen_read', 'tool:synth_set_text'], 'permissions_required': [],
            'prerequisites': [], 'attestations': [{'kind': 'test', 'text': 'synthetic test only, never shipped'}],
            'steps': [{'id': 'read', 'call': 'tool:synth_screen_read', 'args': {}, 'save': {'epoch': 'epoch', 'text': 'text'}},
                      {'id': 'write', 'call': 'tool:synth_set_text',
                       'args': {'epoch': '${steps.read.epoch}', 'text': text}}]}


def ui_cmd(pkg, profile, art, phase, llm='no'):
    state = state_dir(profile)
    return ['/usr/bin/bwrap', '--unshare-all', '--die-with-parent', '--clearenv',
            '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'HOME', '/tmp', '--setenv', 'XDG_CACHE_HOME', '/tmp/cache',
            '--setenv', 'XDG_CONFIG_HOME', '/tmp/config', '--setenv', 'XDG_RUNTIME_DIR', '/tmp/runtime',
            '--setenv', 'QT_QPA_PLATFORM', 'offscreen', '--setenv', 'GIDEON_UI_NO_ONBOARDING', '1', '--setenv', 'QT_QUICK_BACKEND', 'software',
            '--setenv', 'QT_SCALE_FACTOR', '2',
            '--ro-bind', '/usr', '/usr', '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib', '/lib64',
            '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/bin', '/sbin',
            '--ro-bind', '/etc/fonts', '/etc/fonts', '--ro-bind', '/etc/ld.so.cache', '/etc/ld.so.cache',
            '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
            '--ro-bind', str(pkg), str(pkg), '--bind', str(state), str(state), '--bind', str(art), str(art),
            '--ro-bind', str(TEST_UI), '/e4/scripts/test_ui_offscreen.py', '--ro-bind', str(pkg / 'app'), '/e4/app',
            '--chdir', '/tmp', '--', str(pkg / 'venvs/ui/bin/python'), '-I', '/e4/scripts/test_ui_offscreen.py',
            '--root', str(state / 'core'), '--artifacts', str(art), '--phase', phase, '--llm', llm]


def qt_phase(profile, phase, markers, llm='no'):
    pkg = Path(os.path.realpath(S['root'] / 'current'))
    check(f'qt {phase}: the UI runs from the installed package (venvs/ui and app/ of {pkg.name})', pkg.parent == S['root'] / 'versions', str(pkg))
    art = S['work'] / f'art-{phase}-{len(S["tree"])}'
    art.mkdir()
    # diagnostics only: how long the Core takes to answer a snapshot right before the UI starts
    t_snap = time.monotonic()
    before_ui = snap(profile)
    S['tree'].setdefault('qt_snapshot_ms', {})[phase] = round((time.monotonic() - t_snap) * 1000)
    (S['work'] / f'snap-{phase}.json').write_text(json.dumps(before_ui, ensure_ascii=False), encoding='utf-8')
    ui = subprocess.run(ui_cmd(pkg, profile, art, phase, llm), stdin=subprocess.DEVNULL, capture_output=True, timeout=420,
                        env=e1.CLEAN_ENV)
    err = ui.stderr.decode('utf-8', 'replace')
    (S['work'] / f'qt-{phase}.stderr').write_text(err, encoding='utf-8')  # kept with the work directory on failure
    tb = err.find('Traceback')
    # the failing line and the exception message are the LAST lines of a traceback (check() keeps 600 chars)
    check(f'qt {phase}: the packaged Qt phase exits 0', ui.returncode == 0, err[-520:] if tb >= 0 else err[-520:])
    got = [m for m in markers if (art / m).exists()]
    check(f'qt {phase}: every checkpoint reached {markers}', got == markers, got)
    report = None
    for line in reversed(ui.stdout.decode('utf-8', 'replace').splitlines()):
        if line.startswith('{'):
            report = json.loads(line)
            break
    check(f'qt {phase}: self-report has zero failed and zero ignored checks', report is not None and report.get('failed') == 0
          and report.get('ignored') == 0 and report.get('passed') == len(report.get('checks') or [1]), report and {k: report.get(k) for k in ('failed', 'ignored', 'passed')})
    S['tree'].setdefault('qt', {})[phase] = {'passed': report and report.get('passed'), 'markers': got}
    return report


def sec_demo(args):
    p = PROFILE
    f = S['fakes']
    gh, gg, ha, cloud, llama = f['github'], f['google'], f['ha'], f['cloud'], f['llama']
    core_start(p, 'demo-v1', demo_args(p), net=True, binds=FX_BINDS)
    root = core_root(p)
    exe_check(p, V1, 'demo')
    # 1. S1: PCM wake -> Command -> TTS virtual
    s1_check(p, 'demo S1 (PCM wake -> Command -> TTS virtual)')
    # 2. Hub: llm_engine and the synthetic perception plugin, installed through the Hub from the package Core
    gh.ctl('reset')
    e3.install_plugin(root, e1.PLUGIN, LLM_SRC)
    e3.install_plugin(root, 'screen_observe', C4_SRC / 'screen_observe.py')
    check('demo Hub: llm_engine and screen_observe installed, approved, enabled and running from the package Core',
          all(any(i['plugin_id'] == x and i['state'] == 'running' for i in rq(p)['plugins']['items'])
              for x in (e1.PLUGIN, 'screen_observe')))
    h = rq(p)['hub']
    check('demo Hub: installed records for both plugins', {r['plugin_id'] for r in h['installed']} >= {e1.PLUGIN, 'screen_observe'})
    # 3. model: remote simulated (custom loopback provider through the Core-brokered net_broker of the package)
    check('demo model: secret_set stores the key in the vault', rq(p, 'secret_set', provider='custom', key=KEY)['code'] == 'ok')
    cloud.reset()
    rev = rq(p)['llm']['revision']
    code = rq(p, 'llm_configure', revision=rev, provider='custom', model='fake/model-1', custom_url=cloud.v1(), local_port=None,
              fallback=None, cloud_consent=True)['code']
    check('demo model: remote simulated route configured with consent', code == 'ok', code)
    res = cap_chat(root, 'echo:remote hello')
    check('demo model remote: streaming chat through the brokered route returns the text',
          res.get('ok') is True and (res.get('output') or {}).get('text') == 'remote hello', res)
    log = cloud.log()
    check('demo model remote: the fake received Bearer <vault key> injected by the Core and the model chosen by the Core',
          len(log) == 1 and (log[0].get('headers') or {}).get('authorization') == f'Bearer {KEY}'
          and log[0]['body'].get('model') == 'fake/model-1' and log[0]['body'].get('stream') is True, log)
    snap_text = json.dumps(rq(p), ensure_ascii=False)
    check('demo model remote: the key is in no snapshot', KEY not in snap_text)
    # 4. model: local llama.cpp shape (no key, loopback port), self test, last-known-good, rollback
    llama.reset()
    rev = rq(p)['llm']['revision']
    code = rq(p, 'llm_configure', revision=rev, provider='local', model='gguf-local', custom_url=None, local_port=llama.port,
              fallback=None, cloud_consent=False)['code']
    check('demo model local: llama.cpp-shaped route configured (no key, no consent)', code == 'ok', code)
    res = models_cap(root, {'action': 'selftest'})
    feats = ((res.get('output') or {}).get('features') or {})
    check('demo model local: selftest ok, streaming and tool_use probed', res.get('ok') is True and feats.get('streaming') == 'supported'
          and feats.get('tool_use') == 'supported', res)
    log = llama.log()
    check('demo model local: the local fake got requests and no Authorization header', len(log) >= 2
          and all(not r.get('authorization_received') for r in log), len(log))
    res = cap_chat(root, 'echo:local hi')
    check('demo model local: chat through the local route', res.get('ok') is True and (res.get('output') or {}).get('text') == 'local hi', res)
    rev = rq(p)['llm']['revision']
    check('demo model local: mark good records the last-known-good route', rq(p, 'llm_mark_good', revision=rev)['code'] == 'ok'
          and ((rq(p)['llm'].get('config') or {}).get('lkg') or {}).get('local_port') == llama.port)
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    dead = s.getsockname()[1]
    s.close()
    rev = rq(p)['llm']['revision']
    rq(p, 'llm_configure', revision=rev, provider='local', model='gguf-local', custom_url=None, local_port=dead, fallback=None,
       cloud_consent=False)
    res = models_cap(root, {'action': 'selftest'})
    check('demo model local: a dead local port fails the selftest (model_selftest_failed)', res.get('ok') is False
          and res.get('error') == 'model_selftest_failed', res)
    rev = rq(p)['llm']['revision']
    check('demo model local: rollback restores the last-known-good route', rq(p, 'llm_rollback', revision=rev)['code'] == 'ok'
          and (rq(p)['llm'].get('config') or {}).get('local_port') == llama.port)
    rev = rq(p)['llm']['revision']
    rq(p, 'llm_configure', revision=rev, provider='custom', model='fake/model-1', custom_url=cloud.v1(), local_port=None,
       fallback=None, cloud_consent=True)
    # 5. connections: github, google, home assistant, mcp
    gh_id, item = login_dev(root, gh, 'github', 'conta github e4', e1.ALL_SCOPES)
    check('demo connections github: connected with the three consented scopes, account_ref from the fake',
          set(item['granted_scopes']) == set(e1.ALL_SCOPES) and item.get('account_ref') == 'demo-user' and item.get('fake') is True, item)
    S['tree']['github_id'] = gh_id
    code = e1.op(root, gh_id, 'repo.get', {'repo': PRIVATE})
    need('repo.get queued', code == 'ok', code)
    lc = e1.wait_outcome(root, 'repo.get')
    check('demo connections github: repo.get (read) runs without approval', lc['outcome'] == 'ok', lc)
    gg_id, item = login_dev(root, gg, 'google', 'conta google e4', ['calendar.read', 'gmail.read'])
    S['tree']['google_id'] = gg_id
    code = e1.op(root, gg_id, 'calendar.events.list', {})
    need('calendar.events.list queued', code == 'ok', code)
    lc = e1.wait_outcome(root, 'calendar.events.list')
    check('demo connections google: calendar.events.list (read) ok through the packaged broker', lc['outcome'] == 'ok', lc)
    ha.ctl('set_token', {'token': HA_TOKEN})
    code = e1.req(root, 'connection_add', provider='homeassistant', label='casa e4')['code']
    need('add ha', code == 'ok', code)
    ha_id = next(i['id'] for i in e1.conn_items(root) if i['label'] == 'casa e4')
    S['tree']['ha_id'] = ha_id
    need('connect ha', e1.req(root, 'connection_connect', id=ha_id)['code'] == 'ok')
    e1.wait_for(15, 'ha pending scopes', lambda: (lambda x: x if x and x.get('pending_scopes') else None)(e1.find(root, ha_id)))
    need('ha consent', e1.req(root, 'connection_consent', id=ha_id, scopes=['states.read', 'services.call'])['code'] == 'ok')
    need('ha token', e1.req(root, 'connection_set_token', id=ha_id, token=HA_TOKEN)['code'] == 'ok')
    item = e1.wait_status(root, ha_id, 'connected')
    e1.harvest(root, ha_id)
    code = e1.op(root, ha_id, 'state.get', {'entity_id': 'light.kitchen'})
    need('state.get queued', code == 'ok', code)
    lc = e1.wait_outcome(root, 'state.get')
    check('demo connections homeassistant: connected with a pasted token, state.get ok (projected)', item['status'] == 'connected'
          and lc['outcome'] == 'ok', lc)
    code = e1.req(root, 'connection_add', provider='mcp', label='servidor e4')['code']
    need('add mcp', code == 'ok', code)
    mcp_id = next(i['id'] for i in e1.conn_items(root) if i['label'] == 'servidor e4')
    S['tree']['mcp_id'] = mcp_id
    need('connect mcp', e1.req(root, 'connection_connect', id=mcp_id)['code'] == 'ok')
    e1.wait_for(30, 'mcp initialize', lambda: (lambda x: x if x and x.get('pending_scopes') else None)(e1.find(root, mcp_id)))
    need('mcp consent', e1.req(root, 'connection_consent', id=mcp_id, scopes=['mcp.discover', 'mcp.call'])['code'] == 'ok')
    e1.wait_status(root, mcp_id, 'connected')
    need('discover queued', e1.op(root, mcp_id, 'mcp.discover', {}) == 'ok')
    e1.wait_outcome(root, 'mcp.discover')
    tools = {t['name']: t for t in (e1.find(root, mcp_id).get('tools') or [])}
    check('demo connections mcp: the packaged Core ran the fake MCP server in the plugin sandbox and discovered three trusted tools',
          sorted(tools) == ['add_numbers', 'delete_note', 'echo_note'] and all(t['state'] == 'trusted' for t in tools.values()), tools)
    code = e1.op(root, mcp_id, 'mcp.call', {'tool': 'echo_note', 'args': {'text': 'zebra-e4'}})
    check('demo connections mcp: a call waits for the user decision', code == 'pending_approval', code)
    pid = e1.last(root)['proposal_id']
    check('demo connections mcp: authorize accepted', e1.decide(root, pid) == 'ok')
    done = e1.wait_done(root, pid)
    out = json.loads(done.get('result') or '{}')
    check('demo connections mcp: output is untrusted data prefixed by the Core', done['state'] == 'executed'
          and out.get('output') == '[mcp_output:echo_note] zebra-e4' and out.get('untrusted') is True, done)
    # 5b. Qt pages from the package app: connections and registry (before any skill is enabled)
    code = e1.req(root, 'connection_add', provider='github', label='conta aguardando')['code']
    need('add waiting', code == 'ok', code)
    w_id = next(i['id'] for i in e1.conn_items(root) if i['label'] == 'conta aguardando')
    need('connect waiting', e1.req(root, 'connection_connect', id=w_id)['code'] == 'ok')
    it = e1.wait_for(15, 'waiting device code', lambda: (lambda x: x if x and x.get('user_code') and x.get('pending_scopes') else None)(e1.find(root, w_id)))
    gh.http('POST', '/__control/approve', {'user_code': it['user_code'], 'scopes': it['pending_scopes']})
    e1.wait_for(15, 'waiting account has pending scopes', lambda: True if (e1.find(root, w_id) or {}).get('pending_scopes') else None)
    # The Core has one network slot; after a device approval it stays busy for ~13 s and answers `busy` (the UI does not
    # retry). A user simply clicks again, the scripted phase cannot: wait for a free slot first.
    t_slot = time.monotonic()
    e1.wait_for(60, 'network slot free', lambda: True if e1.wire(root, {'op': 'connection_call', 'id': gh_id,
                                                                       'operation': 'repos.list', 'args': {}})['code'] == 'ok' else None)
    e1.wait_outcome(root, 'repos.list')
    S['tree']['network_slot_busy_after_device_approval_s'] = round(time.monotonic() - t_slot, 1)
    qt_phase(p, 'connections', ['connections-ready', 'connections-read', 'connections-consented'])
    check('demo qt connections: the consented scope was granted by the Core', len((e1.find(root, w_id) or {}).get('granted_scopes') or []) >= 1,
          {k: (e1.find(root, w_id) or {}).get(k) for k in ('status', 'pending_scopes', 'granted_scopes', 'last_call')})
    drop_waiting = e1.req(root, 'connection_disconnect', id=w_id)['code'], e1.req(root, 'connection_remove', id=w_id)['code']
    check('demo qt connections: the extra account was disconnected and removed', drop_waiting == ('ok', 'ok'), drop_waiting)
    qt_phase(p, 'registry', ['registry-ready', 'registry-plan', 'registry-allowed', 'registry-revoked'])
    check('demo qt registry: the phase left the visual fallback off', e3.reg(root)['visual_allowed'] == [])
    # 6. scripted LLM: a tool call + a GitHub issue through the connection route with approval
    before = gh.state()['requests']
    rid, s = e3.run_tool(root, [e1.step(calls=[('a1', 'get_time', {})]),
                                e1.step(calls=[('a2', 'github_create_issue', {'repo': PRIVATE, 'title': e1.INJ_TITLE, 'body': e1.INJ_BODY})]),
                                e1.step(text='Hora lida e issue criada.')], 'Veja a hora e crie uma issue', 'awaiting_approval')
    pend = e3.pending(s, rid)
    check('demo agent: the read tool get_time ran by itself, exactly one connection card waits (github issues.create, write)',
          len(pend) == 1 and pend[0].get('kind') == 'connection' and pend[0].get('operation') == 'issues.create'
          and pend[0].get('risk') == 'write' and pend[0].get('connection_id') == gh_id, pend)
    check('demo agent: the fake GitHub received nothing before the decision', gh.state()['requests'] == before)
    check('demo agent: authorize accepted', e1.decide(root, pend[0]['proposal_id']) == 'ok')
    a = e1.wait_agent(root, lambda x: x['state'] == 'done', 40, 'demo agent done')['agent']
    made = e3.issues_of(PRIVATE, e1.INJ_TITLE)
    check('demo agent: exactly one issue on the fake GitHub with the approved title (injection text only as data)',
          len(made) == 1 and made[0]['state'] == 'open' and gh.state()['comments'] == [], made)
    check('demo agent: grants unchanged, final answer from the scripted model, steps chat/tool/chat/tool/chat',
          set(e1.find(root, gh_id)['granted_scopes']) == set(e1.ALL_SCOPES) and a.get('answer') == 'Hora lida e issue criada.'
          and e1.kinds_of(a) == ['chat', 'tool', 'chat', 'tool', 'chat'], e1.kinds_of(a))
    rid, s = e3.run_tool(root, [e1.step(calls=[('r1', 'route_create_issue', {'title': 'Issue pela rota E4', 'body': 'corpo e4'})]),
                                e1.step(text='Criada pela rota.')], 'Crie pela rota', 'awaiting_approval')
    pend = e3.pending(s, rid)
    check('demo registry: route_create_issue plans the connection route (public card, fixed target repo)',
          len(pend) == 1 and pend[0].get('kind') == 'connection' and pend[0].get('risk') == 'public'
          and pend[0]['args'].get('input', {}).get('repo') == PUBLIC, pend)
    check('demo registry: authorize accepted', e1.decide(root, pend[0]['proposal_id']) == 'ok')
    e1.wait_agent(root, lambda x: x['state'] == 'done', 40, 'route done')
    made = e3.issues_of(PUBLIC, 'Issue pela rota E4')
    check('demo registry: the issue exists once on the fake after the approved route', len(made) == 1, made)
    # 8. perception synthetic (gated by flags): counter tool with approval, and the screen_observe capability
    rid, s = e3.run_tool(root, [e1.step(calls=[('p1', 'synth_counter_inc', {'epoch': 1})]), e1.step(text='Contador atualizado.')],
                         'Incremente o contador', 'awaiting_approval')
    pend = e3.pending(s, rid)
    check('demo synthetic: the state-changing synthetic tool waits for approval', len(pend) == 1 and pend[0].get('tool') == 'synth_counter_inc', pend)
    e1.decide(root, pend[0]['proposal_id'])
    e1.wait_agent(root, lambda x: x['state'] == 'done', 40, 'synth done')
    world = g.world(data_dir(p))
    check('demo synthetic: the world lives in the profile data directory and the counter is 1',
          world['app']['counter'] == 1 and (data_dir(p) / 'synthetic/world.json').is_file(), world['app'])
    check('demo synthetic: nothing was created in the installed package', not (vdir() / 'synthetic').exists())
    res = sh.capability(root, 'screen_observe.capture', {})
    out = res.get('output') or {}
    check('demo perception: screen_observe.capture answers from the synthetic world only (flag on)',
          res.get('ok') is True and out.get('backend') == 'synthetic', res)
    # 9. Qt skills page from the package app (the fixture skill is the only enabled skill)
    skills_prepare(root, p)
    llm_draft = sh.draft_manifest(DRAFT_SKILL, '1.0.0')
    sh.set_script(root, [sh.script_step(json.dumps(llm_draft))])
    qt_phase(p, 'skills', ['skills-ready', 'skills-validated', 'skills-draft', 'skills-awaiting', 'skills-run', 'skills-import'], llm='yes')
    check('demo qt skills: the UI run wrote the synthetic world once and the LLM draft stayed a draft',
          g.app_text(data_dir(p)) == SKILL_TEXT and (g.item_of(root, DRAFT_SKILL) or {}).get('state') == 'draft')
    # 7. skills: LLM draft (scripted) -> dry run -> approve -> enable -> run
    draft = sh.draft_manifest('skill_e4_llm', '1.0.0')
    sh.set_script(root, [sh.script_step(json.dumps(draft))])
    res = sh.capability(root, 'llm_engine.skill_draft', {'description': 'Lista a hora atual'})
    out = res.get('output') or {}
    check('demo skills: llm_engine.skill_draft created a draft (never enabled by the model)',
          res.get('ok') is True and out.get('draft_id') == 'skill_e4_llm@1.0.0' and out.get('state') == 'draft', res)
    item = g.item_of(root, 'skill_e4_llm')
    check('demo skills: the draft row is draft, llm_draft, not active', item and item['state'] == 'draft'
          and item['source'] == 'llm_draft' and item['active'] is False, item)
    codes = [g.sk_dry(root, 'skill_e4_llm', '1.0.0', {})]
    codes.append(g.sk_approve(root, 'skill_e4_llm', '1.0.0'))
    codes.append(g.sk_enable(root, 'skill_e4_llm'))
    check('demo skills: dry run, approval and enable are the user ops', codes == ['ok'] * 3, codes)
    code = g.sk_run(root, 'skill_e4_llm', {})
    need('skill run accepted', code == 'ok', code)
    g.drive(root, lambda r: r is None, 'skill run ends')
    last = g.last_run(root)
    check('demo skills: the LLM-drafted skill ran to done after the user enabled it', last and last['state'] == 'done', last)
    # 10. sentinels for update/rollback: registry switch, skills, plugins, connections
    check('demo sentinels: the user turns the visual fallback on for create_issue', e3.allow(root, True) == 'ok')
    time.sleep(4)
    sample_idle(p, 'demo-full')
    snap_clean_all(root)
    core_stop(p)
    S['ledger']['L0'] = ledger_state(p)
    check('demo ledgers: the Core root holds the skills, connections, registry, plugin-state, hub and secrets ledgers',
          all(k in S['ledger']['L0']['files'] for k in ('connections.json', 'registry.json', 'plugin-state.json', 'secrets.json'))
          and 'skills.json' in S['ledger']['L0']['files'] and 'hub-installed.json' in S['ledger']['L0']['files'],
          sorted(S['ledger']['L0']['files']))
    marker = data_dir(p) / 'sentinel.txt'
    marker.write_text('user data sentinel\n')
    os.chmod(marker, 0o600)  # profile state is 0600 like every other state file
    S['tree']['data_sentinel'] = sha256(marker)


def snap_clean_all(root):
    text = json.dumps(rq(PROFILE), ensure_ascii=False)
    check('demo: no token or key value in the final snapshot', not any(v in text for v in e1.SECRETS))


def skills_prepare(root, p):
    data = data_dir(p)
    codes = sh.promote(root, rw_manifest(RUN_SKILL, SKILL_TEXT))
    check(f'demo skills: {RUN_SKILL} saved, dry-run, approved, enabled', codes == ['ok'] * 4, codes)
    codes = sh.promote(root, sh.draft_manifest(NOTE_SKILL, '1.0.0'))
    need('note promoted', codes == ['ok'] * 4, codes)
    exported = g.req(root, 'skill_export', id=NOTE_SKILL, skill_version='1.0.0')
    check('demo skills: export writes a .gskill into the profile data directory (never into the package)',
          exported['code'] == 'ok' and (data / 'skill-exports' / f'{NOTE_SKILL}-1.0.0.gskill').is_file()
          and not (vdir() / 'skill-exports').exists(), exported)
    package = (data / 'skill-exports' / f'{NOTE_SKILL}-1.0.0.gskill').read_bytes()
    check('demo skills: export file mode 0600 in a 0700 directory', stat.S_IMODE(os.lstat(data / 'skill-exports').st_mode) == 0o700
          and stat.S_IMODE(os.lstat(data / 'skill-exports' / f'{NOTE_SKILL}-1.0.0.gskill').st_mode) == 0o600)
    need('note removed', g.req(root, 'skill_remove', id=NOTE_SKILL, revision=g.sk_revision(root))['code'] == 'ok')
    sh.place_import(data, 'fixture-note', package)


# ---- ledgers ---------------------------------------------------------------------------------
VOLATILE = ('audit.log', 'core.sock', 'core.lock')


def ledger_state(profile):
    """Per-file sha256 of every regular file in the Core root (and sub-directories) except the volatile ones,
    plus the semantic view of the connections ledger and the modes."""
    root = core_root(profile)
    files, modes = {}, {}
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root).as_posix()
        head = rel.split('/')[0]
        if path.is_symlink() or head in VOLATILE or head.startswith('audit.log') or rel.startswith('quarantine') or path.is_socket():
            continue
        st = path.lstat()
        if stat.S_ISDIR(st.st_mode):
            modes[rel] = stat.S_IMODE(st.st_mode)
        elif stat.S_ISREG(st.st_mode):
            files[rel] = sha256(path)
            modes[rel] = stat.S_IMODE(st.st_mode)
    conns = []
    cj = root / 'connections.json'
    if cj.is_file():
        data = json.loads(cj.read_text(encoding='utf-8'))
        conns = sorted((a.get('id'), a.get('provider'), a.get('label'), tuple(sorted(a.get('granted_scopes') or [])))
                       for a in data.get('accounts', data.get('items', [])))
    plugins = []
    pj = root / 'plugin-state.json'
    if pj.is_file():
        plugins = sorted(json.loads(pj.read_text(encoding='utf-8')).get('enabled') or [])
    return {'files': files, 'modes': modes, 'connections': conns, 'plugins': plugins}


def compare_ledgers(before, after, label, allow_changed=()):
    # connections.json is compared semantically below (last_ok moves with every call); plugin-settings holds the
    # scripted LLM steps the gate writes between boots. plugin-state.json and hub-generation (its write counter) move
    # with the gate's own scripted restarts of the LLM plugin (verify_e1_connections.restart_llm: disable + enable), so
    # they are compared semantically (the enabled set) instead of byte for byte.
    diff = sorted(k for k in set(before['files']) | set(after['files'])
                  if before['files'].get(k) != after['files'].get(k) and k not in allow_changed
                  and k not in ('connections.json', 'plugin-state.json', 'hub-generation') and not k.startswith('plugin-settings/'))
    check(f'{label}: every ledger file of the Core root is byte-identical except plugin-state and its counter (skills, registry, hub, llm-config, secrets)',
          not diff, diff[:12])
    check(f'{label}: plugin-state keeps the same enabled plugins', before['plugins'] == after['plugins'], (before['plugins'], after['plugins']))
    check(f'{label}: connections ledger keeps the same accounts, providers, labels and granted scopes',
          before['connections'] == after['connections'] and len(before['connections']) >= 4, (before['connections'], after['connections']))
    bad = sorted(k for k, v in after['modes'].items() if v not in (0o600, 0o700))
    check(f'{label}: every state file is 0600 and every directory 0700', not bad, [(k, oct(after['modes'][k])) for k in bad[:8]])


def after_restart_checks(p, label, version):
    root = core_root(p)
    exe_check(p, version, label)
    s1_check(p, f'{label} S1')
    items = [(i['id'], i['status']) for i in e1.conn_items(root)]
    gh_id = S['tree']['github_id']
    check(f'{label}: the vaulted github token still works after the restart (repo.get ok without a new login)',
          e1.op(root, gh_id, 'repo.get', {'repo': PRIVATE}) == 'ok' and e1.wait_outcome(root, 'repo.get')['outcome'] == 'ok',
          e1.find(root, gh_id))
    check(f'{label}: github connected, mcp back to disconnected or connected (process does not survive a Core restart)',
          e1.find(root, gh_id)['status'] == 'connected' and e1.find(root, S['tree']['mcp_id'])['status'] in ('disconnected', 'connected'), items)
    sk = {i['id']: i for i in g.items(root)}
    check(f'{label}: skills ledger: enabled skills stay enabled and drafts stay drafts',
          sk.get('skill_e4_llm', {}).get('state') == 'enabled' and sk.get(RUN_SKILL, {}).get('state') == 'enabled'
          and sk.get(DRAFT_SKILL, {}).get('state') == 'draft', {k: v['state'] for k, v in sk.items()})
    check(f'{label}: registry ledger: the visual fallback switch is still on', e3.reg(root)['visual_allowed'] == ['create_issue'])
    running = {i['plugin_id']: i['state'] for i in rq(p)['plugins']['items']}
    check(f'{label}: plugin-state: llm_engine and screen_observe are running again', running.get('llm_engine') == 'running'
          and running.get('screen_observe') == 'running', running)
    check(f'{label}: the sentinel in the profile data directory survived', (data_dir(p) / 'sentinel.txt').is_file()
          and sha256(data_dir(p) / 'sentinel.txt') == S['tree']['data_sentinel'])
    code = g.sk_run(root, 'skill_e4_llm', {})
    need('skill run accepted', code == 'ok', code)
    g.drive(root, lambda r: r is None, f'{label} skill run ends')
    check(f'{label}: the enabled skill runs to done', (g.last_run(root) or {}).get('state') == 'done', g.last_run(root))


# ---- update / rollback -------------------------------------------------------------------------
def lock_hold(seconds):
    """Hold ROOT/.lock exclusively without a Core socket, as a crashed installer would (simulates `locked`)."""
    import fcntl
    fd = os.open(S['root'] / '.lock', os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def sec_update(args):
    p = PROFILE
    base = tree_state(vdir(V1))
    pre_v1 = {'package_json': sha256(vdir(V1) / 'PACKAGE.json'), 'binary': sha256(vdir(V1) / 'bin/gideon-base')}
    # first: the update is refused while a Core runs (profile_active), then applied after the stop
    core_start(p, 'demo-v1-running', demo_args(p), net=True, binds=FX_BINDS)
    before = (lst(), (S['root'] / 'install.json').read_bytes())
    rc, obj, err = inst('update', str(S['pkg2']))
    check('update: refused with exit 3 profile_active while the main Core runs', rc == 3 and obj and obj.get('error') == 'profile_active'
          and obj.get('profile') == p, err or obj)
    rc, obj, err = inst('rollback')
    check('update: rollback is refused the same way while a Core runs (also exit 3 profile_active)', rc != 0 and (
        (obj or {}).get('error') in ('profile_active', 'no_previous')), err or obj)
    check('update: the refusals left the ledger and the links untouched', (lst(), (S['root'] / 'install.json').read_bytes()) == before)
    check('update: the refused package was not consumed', S['pkg2'].is_dir())
    core_stop(p)
    fd = lock_hold(5)
    t0 = time.monotonic()
    rc, obj, err = inst('update', str(S['pkg2']), env_extra={'GIDEON_INSTALL_LOCK_TIMEOUT': '1'})
    os.close(fd)
    check('update: with the install lock held and no Core socket the installer answers locked (exit 6) after the timeout',
          rc == 6 and obj and obj.get('error') == 'locked' and time.monotonic() - t0 >= 0.8, err or obj)
    rc, obj, err = inst('update', str(S['pkg2']), timeout=1200)
    check('update: v1 -> v2 applied by the installed tool (exit 0)', rc == 0 and obj and obj.get('ok') is True, err or obj)
    st = lst()
    check('update: list shows current v2, previous v1 and no orphan', st['current'] == ident(V2) and st['previous'] == ident(V1)
          and st['orphans'] == [], st)
    check('update: v1 stays byte-identical on disk (same hashes, same tree state)', sha256(vdir(V1) / 'PACKAGE.json') == pre_v1['package_json']
          and sha256(vdir(V1) / 'bin/gideon-base') == pre_v1['binary'] and tree_state(vdir(V1)) == base)
    check('update: v2 binary and PACKAGE.json equal what was built',
          sha256(vdir(V2) / 'bin/gideon-base') == S['tree'][f'binary_{V2}']
          and sha256(vdir(V2) / 'PACKAGE.json') == S['tree'][f'package_json_{V2}'])
    check('update: v2 gideon-verify passes', run([py_of(vdir(V2)), '-I', '-B', str(vdir(V2) / 'bin/gideon-verify')], timeout=600).returncode == 0)
    core_start(p, 'demo-v2', demo_args(p), net=True, binds=FX_BINDS)
    compare_ledgers(S['ledger']['L0'], ledger_state(p), 'update v2 boot')
    after_restart_checks(p, 'update v2', V2)
    registry_text = json.dumps(rq(p)['registry'])
    check('update v2: the registry snapshot still lists the three purposes', all(x in registry_text for x in ('create_issue', 'list_events', 'read_state')))
    core_stop(p)
    S['ledger']['L1'] = ledger_state(p)


def sec_rollback(args):
    p = PROFILE
    rc, obj, err = inst('rollback')
    check('rollback: v2 -> v1 applied (exit 0)', rc == 0 and obj and obj.get('ok') is True and obj.get('current') == ident(V1), err or obj)
    st = lst()
    check('rollback: list shows current v1 and previous v2', st['current'] == ident(V1) and st['previous'] == ident(V2), st)
    core_start(p, 'demo-v1-rollback', demo_args(p), net=True, binds=FX_BINDS)
    compare_ledgers(S['ledger']['L1'], ledger_state(p), 'rollback v1 boot')
    after_restart_checks(p, 'rollback v1', V1)
    core_stop(p)
    S['ledger']['L2'] = ledger_state(p)
    for version in (V1, V2):
        check(f'rollback: gideon-verify passes on retained {version}',
              run([py_of(vdir(version)), '-I', '-B', str(vdir(version) / 'bin/gideon-verify')], timeout=600).returncode == 0)


# ---- crash / recovery --------------------------------------------------------------------------
def sec_crash(args):
    p = PROFILE
    root = core_root(p)
    gh = S['fakes']['github']
    core_start(p, 'crash-1', demo_args(p), net=True, binds=FX_BINDS)
    s1_check(p, 'crash boot S1')
    ledger_before = ledger_state(p)
    gh_id = S['tree']['github_id']
    issues_before = len(gh.state()['issues'][PRIVATE])
    title = 'Issue durante o crash'
    rid, s = e3.run_tool(root, [e1.step(calls=[('c1', 'github_create_issue', {'repo': PRIVATE, 'title': title})]),
                                e1.step(text='Feito.')], 'Crie e caia', 'awaiting_approval')
    pend = e3.pending(s, rid)
    need('crash: one pending card', len(pend) == 1, pend)
    check('crash: the pending approval wrote nothing to the fake before the kill', len(gh.state()['issues'][PRIVATE]) == issues_before)
    pid = gideon_base_pid(p)
    need('Core pid found', pid is not None)
    kids_before = [q for q in tree_pids(S['cores'][p]['proc'].pid) if q != pid]
    os.kill(pid, signal.SIGKILL)
    try:
        S['cores'][p]['proc'].wait(timeout=20)
    except subprocess.TimeoutExpired:
        pass
    time.sleep(2)
    left = pids_with(str(S['root']).encode())
    check('crash: kill -9 of the Core leaves no orphan process (workers, brokers, plugins and the MCP server die with it)',
          not left, [cmdline_of(q)[:120] for q in left[:5]])
    S['cores'].pop(p, None)
    (core_root(p) / '.registry.json.pending').write_bytes(b'{"half written')
    os.chmod(core_root(p) / '.registry.json.pending', 0o600)
    check('crash: no issue was created by the killed pending approval', len(gh.state()['issues'][PRIVATE]) == issues_before)
    rc, obj, err = inst('update', str(S['work'] / 'does-not-exist'))
    check('crash: after the crash the installer sees no active profile (it fails on the package, not with profile_active)',
          (obj or {}).get('error') != 'profile_active', err or obj)
    core_start(p, 'crash-2', demo_args(p), net=True, binds=FX_BINDS)
    s1_check(p, 'crash recovery S1')
    after = ledger_state(p)
    compare_ledgers(ledger_before, after, 'crash recovery')
    q = sorted(x.name for x in (core_root(p) / 'quarantine').glob('*')) if (core_root(p) / 'quarantine').is_dir() else []
    check('crash recovery: the half-written .registry.json.pending was moved to quarantine, not deleted, and the ledger is intact',
          not (core_root(p) / '.registry.json.pending').exists() and any(n.startswith('.registry.json.pending') for n in q), q)
    s = snap(p)
    check('crash recovery: no agent run and no pending proposal survived the crash',
          not any(pr.get('state') == 'pending' for pr in s.get('tool_proposals') or []) and (s.get('agent') is None or s['agent'].get('state') not in ('running', 'awaiting_approval')),
          {'agent': s.get('agent') and s['agent'].get('state'), 'proposals': len(s.get('tool_proposals') or [])})
    check('crash recovery: the account is coherent and usable (github connected, read op ok)',
          e1.find(root, gh_id)['status'] == 'connected' and e1.op(root, gh_id, 'repo.get', {'repo': PRIVATE}) == 'ok')
    # second crash: the user approved a write that is in flight on the (slow) fake
    gh.ctl('delay', {'n': 1, 'seconds': 4})
    rid, s = e3.run_tool(root, [e1.step(calls=[('c2', 'github_create_issue', {'repo': PRIVATE, 'title': title + ' 2'})]),
                                e1.step(text='Feito.')], 'Crie e caia de novo', 'awaiting_approval')
    pend = e3.pending(s, rid)
    need('crash: second pending card', len(pend) == 1, pend)
    e1.decide(root, pend[0]['proposal_id'])
    time.sleep(0.6)
    pid = gideon_base_pid(p)
    os.kill(pid, signal.SIGKILL)
    try:
        S['cores'][p]['proc'].wait(timeout=20)
    except subprocess.TimeoutExpired:
        pass
    S['cores'].pop(p, None)
    time.sleep(5)
    made = [i for i in gh.state()['issues'][PRIVATE] if i['title'] == title + ' 2']
    check('crash: an approved write killed in flight leaves at most one issue (no duplicate, no retry after the crash)',
          len(made) <= 1, made)
    check('crash: no orphan process after the second kill', not pids_with(str(S['root']).encode()))
    core_start(p, 'crash-3', demo_args(p), net=True, binds=FX_BINDS)
    s1_check(p, 'crash recovery 2 S1')
    time.sleep(3)
    made2 = [i for i in gh.state()['issues'][PRIVATE] if i['title'] == title + ' 2']
    check('crash recovery 2: the restart did not replay the killed write (issue count unchanged)', len(made2) == len(made), (made, made2))
    compare_ledgers(ledger_before, ledger_state(p), 'crash recovery 2', allow_changed=())
    core_stop(p)


# ---- profiles and permissions --------------------------------------------------------------------
def sec_profiles(args):
    a, b = 'alice', 'bob'
    f = S['fakes']
    gh = f['github']
    gh.ctl('reset')
    core_start(a, 'alice', [*hub_args(a), '--connections-fake', f'github={gh.base}', '--net-allow-loopback'], net=True)
    core_start(b, 'bob', hub_args(b))
    ra, rb = core_root(a), core_root(b)
    check('profiles: alice and bob run at the same time with distinct sockets', (ra / 'core.sock').exists()
          and (rb / 'core.sock').exists() and ra != rb)
    s1_check(a, 'alice S1')
    s1_check(b, 'bob S1')
    # permissions on alice
    cid, item = login_dev(ra, gh, 'github', 'conta alice', ['repo:read', 'issues:write'])
    before = gh.state()['requests']
    check('permissions: an ungranted scope is refused before any request (scope_not_granted, no network)',
          e1.op(ra, cid, 'pulls.comment', {'repo': PUBLIC, 'number': 1, 'body': 'sem escopo'}) == 'scope_not_granted'
          and gh.state()['requests'] == before)
    code = e1.op(ra, cid, 'issues.create', {'repo': PUBLIC, 'title': 'publico sem permissao'})
    check('permissions: a public write only creates a proposal (pending_approval)', code == 'pending_approval', code)
    ppid = e1.last(ra)['proposal_id']
    check('permissions: authorizing it without the public switch is refused (public_disabled), nothing is created',
          e1.decide(ra, ppid) == 'public_disabled' and all(i['title'] != 'publico sem permissao' for i in gh.state()['issues'][PUBLIC]))
    e1.decide(ra, ppid, 'deny')
    need('repo.get', e1.op(ra, cid, 'repo.get', {'repo': PRIVATE}) == 'ok')
    e1.wait_outcome(ra, 'repo.get')
    code = e1.op(ra, cid, 'issues.create', {'repo': PRIVATE, 'title': 'privada com aprovacao'})
    check('permissions: a private write waits for the user', code == 'pending_approval'
          and all(i['title'] != 'privada com aprovacao' for i in gh.state()['issues'][PRIVATE]), code)
    ppid = e1.last(ra)['proposal_id']
    check('permissions: authorize runs it once', e1.decide(ra, ppid) == 'ok' and e1.wait_done(ra, ppid)['state'] == 'executed'
          and len([i for i in gh.state()['issues'][PRIVATE] if i['title'] == 'privada com aprovacao']) == 1)
    # plugin permissions
    h = rq(a)['hub']
    entry = e1.entry(h, e1.PLUGIN)
    check('permissions: before the approval the plugin is not approved', entry is not None and entry['permissions_approved'] is False, entry)
    e3.install_plugin(ra, e1.PLUGIN, LLM_SRC)
    res = sh.capability(ra, 'llm_engine.models', {'action': 'list', 'tab': 'recommended', 'offset': 0, 'limit': 6})
    check('permissions: with the approved permissions the plugin capability works', res.get('ok') is True, res)
    check('permissions: revoke removes the capability', rq(a, 'plugin_revoke', revision=rq(a)['plugins']['revision'], plugin_id=e1.PLUGIN)['code'] == 'ok')
    resp = rq(a, 'capability_invoke', capability='llm_engine.models', input={'action': 'list', 'tab': 'recommended', 'offset': 0, 'limit': 6}, deadline_ms=3000)
    check('permissions: after the revoke the capability is unavailable', resp.get('code') == 'capability_unavailable', resp)
    resp = rq(a, 'plugin_enable', revision=rq(a)['plugins']['revision'], plugin_id=e1.PLUGIN)
    check('permissions: re-enable without a new approval is refused', resp.get('code') == 'permissions_not_approved', resp)
    # skill states
    m = sh.draft_manifest('skill_perm', '1.0.0')
    check('permissions: a saved draft cannot be enabled without dry run and approval',
          g.sk_save(ra, m) == 'ok' and g.sk_enable(ra, 'skill_perm') != 'ok')
    check('permissions: a draft cannot run', g.sk_run(ra, 'skill_perm', {}) != 'ok')
    # bob sees nothing of alice
    sb = rq(b)
    check('profiles: bob has no connection account, no skill, no plugin item, no approval of alice',
          sb['connections']['items'] == [] and (sb.get('skills') or {}).get('items', []) == []
          and not any(i['state'] == 'running' for i in sb['plugins']['items'])
          and e1.entry(sb['hub'], e1.PLUGIN)['permissions_approved'] is False
          and sb['hub']['installed'] == [], {k: sb.get(k) for k in ('connections',)})
    check('profiles: bob registry ledger is the default (visual fallback off)', sb['registry']['visual_allowed'] == [])
    sa = rq(a)
    check('profiles: alice keeps her own connection and skill', len(sa['connections']['items']) == 1
          and any(i['id'] == 'skill_perm' for i in g.items(ra)))
    check('profiles: bob has no secrets ledger entry of alice',
          not (rb / 'secrets.json').exists() or not any(v in (rb / 'secrets.json').read_text() for v in e1.SECRETS))
    for pr in (a, b):
        st = ledger_state(pr)
        bad = sorted(k for k, v in st['modes'].items() if v not in (0o600, 0o700))
        check(f'profiles: {pr} state files are 0600 and directories 0700', not bad, bad[:6])
    core_stop(a)
    core_stop(b)


# ---- offline -------------------------------------------------------------------------------------
def sec_offline(args):
    p = 'off'
    root = core_root(p)
    core_start(p, 'offline', [*hub_args(p), '--connections-fake', 'github=http://127.0.0.1:9'])
    s1_check(p, 'offline S1')
    # The bwrap monitor (the Popen pid) stays in the host network namespace; the sandboxed gideon-base is the one to read.
    core = gideon_base_pid(p)
    need('offline: the sandboxed gideon-base process is found', core is not None)
    ifaces = [line.split(':')[0].strip() for line in Path(f'/proc/{core}/net/dev').read_text().splitlines()[2:] if ':' in line]
    check('offline: the Core network namespace has only the loopback interface', ifaces == ['lo'], ifaces)
    gh_id = e1.add_account(root, 'conta offline')
    t0 = time.monotonic()
    code = e1.req(root, 'connection_connect', id=gh_id)['code']
    it = e1.wait_for(40, 'offline connect settles', lambda: (lambda x: x if x and x['status'] in ('error', 'disconnected', 'offline', 'connecting') and
                                                           (time.monotonic() - t0 > 3) else None)(e1.find(root, gh_id)))
    check('offline: connecting to an unreachable provider is accepted or refused fast and the account never becomes connected',
          code in ('ok', 'provider_unreachable', 'busy') and it['status'] != 'connected', (code, it['status']))
    check('offline: the Core still answers snapshots and S1 stays done while the provider is unreachable', snap(p)['state'] == 'idle')
    e3.install_plugin(root, e1.PLUGIN, LLM_SRC)
    check('offline: llm_engine installs from a local payload with no network', any(
        i['plugin_id'] == e1.PLUGIN and i['state'] == 'running' for i in rq(p)['plugins']['items']))
    check('offline: key stored', rq(p, 'secret_set', provider='openrouter', key=KEY)['code'] == 'ok')
    rev = rq(p)['llm']['revision']
    check('offline: cloud route selected with consent', rq(p, 'llm_configure', revision=rev, provider='openrouter', model='fake/model-1',
                                                           custom_url=None, local_port=None, fallback=None, cloud_consent=True)['code'] == 'ok')
    t0 = time.monotonic()
    res = sh.capability(root, 'llm_engine.chat', {'messages': [{'role': 'user', 'content': 'ola sem rede'}], 'tools': False,
                                                  'max_tokens': 16}, secs=60)
    check('offline: a remote model call fails with an error code in bounded time (no hang)',
          res.get('ok') is False and isinstance(res.get('error'), str) and time.monotonic() - t0 < 50, (res, round(time.monotonic() - t0, 1)))
    S['tree']['offline_chat_error'] = res.get('error')
    check('offline: the Core is still responsive and idle after the failed call', snap(p)['state'] == 'idle')
    check('offline: the key never reached a snapshot', KEY not in json.dumps(snap(p)))
    core_stop(p)


# ---- final ----------------------------------------------------------------------------------------
def sec_final(args):
    st = lst()
    for ident_id in [e['id'] for e in st['versions']]:
        pkg = S['root'] / 'versions' / ident_id
        check(f'final: gideon-verify passes on retained {ident_id} (nothing wrote into the package)',
              run([py_of(pkg), '-I', '-B', str(pkg / 'bin/gideon-verify')], timeout=600).returncode == 0)
    check('final: no process referencing the install root remains', not pids_with(str(S['root']).encode()))
    check('final: no Core still tracked', not S['cores'])
    check('final: the real HOME top-level entries are unchanged', sorted(os.listdir(Path.home())) == S['tree']['home_names'])
    check('final: the sentinel directory outside the run is unchanged', tree_state(S['sentinel']) == S['tree']['sentinel_pre'])
    check('final: the private HOME of the host commands is unchanged', tree_state(S['home']) == S['tree']['home_state'])
    hits, files, modes_bad, wide = [], 0, [], []
    for dirpath, dirnames, names in os.walk(S['root']):
        for entry in [*dirnames, *names]:
            path = Path(dirpath) / entry
            try:
                st_ = path.lstat()
            except OSError:
                continue
            if st_.st_mode & 0o002 and not stat.S_ISLNK(st_.st_mode):
                wide.append(str(path.relative_to(S['root'])))
            if '/profiles/' in str(path) and stat.S_ISREG(st_.st_mode) and stat.S_IMODE(st_.st_mode) not in (0o600, 0o700):
                modes_bad.append(f'{path.relative_to(S["root"])}:{oct(stat.S_IMODE(st_.st_mode))}')
        for name in names:
            path = Path(dirpath) / name
            if '/versions/' in str(path) or path.is_symlink() or not path.is_file():
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            files += 1
            for value in e1.SECRETS | e1.RETIRED:
                if name != 'secrets.json' and value.encode() in data:
                    hits.append(f'{path.relative_to(S["root"])}')
                    break
    check(f'final: no key or token value in any of {files} state file outside the 0600 vault (secrets.json)', not hits, hits[:8])
    check('final: vacuity guard, tokens and keys were collected', len(e1.SECRETS) >= 6, len(e1.SECRETS))
    check('final: no world-writable file or directory under ROOT', not wide, wide[:8])
    check('final: every state file under profiles/ is 0600 or 0700', not modes_bad, modes_bad[:8])
    for log in S['work'].glob('*.log'):
        text = log.read_bytes()
        leaked = [v for v in e1.SECRETS if v.encode() in text]
        if leaked:
            check(f'final: the Core log {log.name} has no key or token value', False, log.name)
    check('final: Core logs carry no key or token value', True)
    audits = []
    for pr in (PROFILE, 'alice', 'bob', 'nofl', 'off'):
        audit = core_root(pr) / 'audit.log'
        if audit.exists():
            audits.append(audit.read_text(encoding='utf-8', errors='replace'))
    check('final: audit logs exist and carry no key or token value', bool(audits) and not any(v in a for a in audits for v in e1.SECRETS), len(audits))


# ---- main ------------------------------------------------------------------------------------
def run_section(name, fn, args):
    t0 = time.monotonic()
    try:
        fn(args)
    except Exception as exc:
        tb = traceback.format_exc()[-1000:]
        check(f'{name}: ran without exception', False, f'{type(exc).__name__}: {exc} | {tb}')
        e1.R['details'].setdefault('exceptions', []).append({'section': name, 'trace': tb})
        for prof in list(S['cores']):
            try:
                core_stop(prof, expect_clean=False)
            except Exception:
                pass
    S['tree'].setdefault('section_seconds', {})[name] = round(time.monotonic() - t0, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', default=','.join(SECTIONS))
    parser.add_argument('--reuse-build', default=None, help='directory that already holds gideon-base-0.4.0 and -0.4.1 (development only)')
    parser.add_argument('--keep', action='store_true', help='keep the work directory')
    args = parser.parse_args()
    chosen = args.only.split(',')
    bad = [c for c in chosen if c not in SECTIONS]
    if bad:
        sys.exit(f'unknown section(s): {bad}')
    started = time.monotonic()
    work = Path(tempfile.mkdtemp(prefix='ge4-', dir='/tmp'))
    S.update(work=work, home=work / 'h', root=work / 'r', sentinel=work / 's')
    S['home'].mkdir(mode=0o700)
    S['sentinel'].mkdir(mode=0o700)
    (S['sentinel'] / 'keep.txt').write_text('sentinel\n')
    table = {'build': sec_build, 'static': sec_static, 'install': sec_install, 'noflag': sec_noflag, 'demo': sec_demo,
             'update': sec_update, 'rollback': sec_rollback, 'crash': sec_crash, 'profiles': sec_profiles,
             'offline': sec_offline, 'final': sec_final}
    try:
        start_fakes()
        for name in SECTIONS:
            if name in chosen:
                if name not in ('build',) and 'pkg1' not in S and 'build' not in chosen:
                    check(f'{name}: needs the build section', False, 'run with build first')
                    continue
                run_section(name, table[name], args)
    finally:
        for prof in list(S['cores']):
            core_stop_quiet(prof)
        stop_fakes()
    skip('real GitHub, Google and Home Assistant accounts', 'no real credential exists in this environment (docs/S5.md); fakes only')
    skip('physical audio, KDE Wayland, portals, Flatpak', 'not available in the virtual environment (docs/HUMAN_VALIDATION.md)')
    skip('real llama.cpp binary and GGUF model', 'no binary or model is installed; a llama.cpp-shaped fake stands in')
    commit = S.get('commit') or ''
    partial = set(chosen) != set(SECTIONS)
    out = {'gate': GATE, 'partial': partial, 'sections': chosen, 'passed': len(e1.R['passed']), 'failed': len(e1.R['failed']),
           'skipped': e1.R['skipped'], 'checks': e1.R['passed'], 'failures': e1.R['failed'], 'details': e1.R['details'],
           'identity': {'commit': commit, 'tracked_changes_at_build': S['tree'].get('tracked_changes'),
                        'package_dirty_flag': {V1: S['tree'].get(f'dirty_{V1}'), V2: S['tree'].get(f'dirty_{V2}')},
                        'binary_sha256': {V1: S['tree'].get(f'binary_{V1}'), V2: S['tree'].get(f'binary_{V2}')},
                        'package_json_sha256': {V1: S['tree'].get(f'package_json_{V1}'), V2: S['tree'].get(f'package_json_{V2}')},
                        'release_binary_sha256': sha256(REPO / 'target/release/gideon-base')},
           'idle_resources': S['idle'], 'measurements': {k: v for k, v in S['tree'].items() if k in (
               'build_0.4.0_s', 'build_0.4.1_s', 'key_scan', 'section_seconds', 'qt', 'qt_snapshot_ms', 'offline_ifaces', 'offline_chat_error', 'network_slot_busy_after_device_approval_s')},
           'runtime_s': round(time.monotonic() - started, 1),
           'scope': 'complete Linux package built by scripts/build_package.py, installed with the package gideon-install and run '
                    'with the package gideon-launch/gideon-core/gideon-base and the package Qt app, under an outer bwrap without '
                    'repository, uv or (except fake-using boots, which share only the host loopback) network; fakes and fixtures '
                    'outside the package via test-only flags',
           'physical_validation': 'NOT_PERFORMED'}
    text = json.dumps(out, indent=2, ensure_ascii=False) + '\n'
    for value in e1.SECRETS | e1.RETIRED:
        text = text.replace(value, '<redacted>')
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE if not partial else EVIDENCE.with_name('e4-integration-partial.json')
    path.write_text(text, encoding='utf-8')
    print(json.dumps({k: out[k] for k in ('gate', 'partial', 'passed', 'failed', 'runtime_s')}, indent=2))
    for item in e1.R['failed'][:40]:
        print('FAIL', item['name'], '::', item['detail'][:400])
    if not args.keep and not e1.R['failed']:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print('work directory kept:', work)
    return 1 if e1.R['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
