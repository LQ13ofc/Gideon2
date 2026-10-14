#!/usr/bin/env python3
"""Real daemon tests; isolated environment, no personal peripherals or bus."""
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time

BASE = Path(__file__).resolve().parents[1]
BINARY = BASE / 'target/release/gideon-base'


def run():
    checks = []
    def check(name, condition):
        assert condition, name
        checks.append(name)
    with tempfile.TemporaryDirectory(prefix='gideon-a0-') as td:
        root = Path(td) / 'runtime'
        root.mkdir(mode=0o700)
        (root/'config.json').write_text(json.dumps({'version': 1, 'session_timeout_ms': 350}))
        (root/'config.json').chmod(0o600)
        env = {'PATH': '/usr/bin:/bin', 'HOME': td, 'XDG_RUNTIME_DIR': str(root), 'XDG_CONFIG_HOME': td+'/config', 'XDG_DATA_HOME': td+'/data', 'XDG_CACHE_HOME': td+'/cache', 'LANG': 'C'}
        process = None
        clients = []
        def start(virtual=True):
            p = subprocess.Popen([str(BINARY), '--root', str(root)] + (['--virtual-input'] if virtual else []), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            end = time.monotonic()+3
            while time.monotonic()<end:
                if p.poll() is not None:
                    raise AssertionError(p.stderr.read().decode())
                try:
                    s = connect(); s.close(); return p
                except (FileNotFoundError, ConnectionRefusedError):
                    time.sleep(0.01)
            p.terminate(); p.wait(); raise AssertionError('startup timeout')
        def connect():
            s = socket.socket(socket.AF_UNIX); s.settimeout(3); s.connect(str(root/'core.sock')); return s
        def request(s, ident, op, **kw):
            s.sendall((json.dumps({'version': 1, 'request_id': ident, 'op': op, **kw})+'\n').encode())
            data = b''
            while not data.endswith(b'\n'):
                chunk = s.recv(65536)
                if not chunk: raise AssertionError('unexpected EOF')
                data += chunk
            return json.loads(data)
        try:
            process = start(); s = connect(); clients.append(s)
            check('snapshot idle', request(s, 's', 'snapshot')['state']=='idle')
            wake = request(s, 'wake1', 'virtual_wake')
            check('wake correlated session', wake['code']=='ok' and wake['session_id'] is not None and wake['events'][-1]['request_id']=='wake1')
            sid = wake['session_id']
            check('busy bounded scheduler', request(s, 'busy', 'virtual_wake')['code']=='busy')
            check('replay fenced', request(s, 'wake1', 'virtual_wake')['code']=='duplicate')
            for capability in ['status', 'open_app', 'volume']:
                check('deny '+capability, request(s, capability, 'action', session_id=sid, capability=capability)['code']=='denied')
            s.close(); s = connect(); clients.append(s)
            check('reconnect snapshot', request(s, 'reconnect', 'snapshot')['session_id']==sid)
            check('cancel acknowledged', request(s, 'cancel1', 'cancel', session_id=sid)['state']=='idle')
            check('late result fenced', request(s, 'late', 'action', session_id=sid, capability='status')['code']=='stale_session')
            second = request(s, 'wake2', 'virtual_wake')
            time.sleep(0.45)
            expired = request(s, 'after-timeout', 'snapshot')
            check('deadline without client polling', expired['state']=='idle' and expired['events'][-1]['kind']=='timed_out')
            for payload in [b'{garbage}\n', b'{"version":99,"request_id":"version","op":"snapshot"}\n', b'{"version":1,"request_id":"x","op":"shell","command":"touch sentinel"}\n', b'{"version":1,"request_id":"x","op":"virtual_wake","grant":true}\n']:
                s.sendall(payload); reply = s.recv(65536)
                check('reject malformed '+str(len(checks)), json.loads(reply)['code'] in ['invalid_message', 'version_mismatch'])
            check('no unexpected effect', not (root/'sentinel').exists())
            large = connect(); clients.append(large); large.sendall(b'x'*5000)
            try: result = large.recv(10)
            except ConnectionResetError: result = b''
            check('oversize bounded close', result==b''); large.close()
            check('survives invalid peer', request(s, 'alive', 'snapshot')['code']=='ok')
            dup = subprocess.run([str(BINARY), '--root', str(root)], env=env, capture_output=True, timeout=3)
            check('single instance', dup.returncode!=0 and (root/'core.sock').exists())
            slow = connect(); clients.append(slow); slow.sendall(b'{')
            check('slow peer cannot block core', request(s, 'slow-ok', 'snapshot')['code']=='ok')
            time.sleep(5.1)
            check('slow peer deadline', slow.recv(10)==b''); slow.close()
            s.close()
            # Resident memory / CPU ticks while no clients and no active sessions.
            def stats():
                fields = Path(f'/proc/{process.pid}/stat').read_text().split()
                return int(fields[13])+int(fields[14]), int(fields[23])*os.sysconf('SC_PAGE_SIZE')
            ticks0, rss0 = stats(); started = time.monotonic(); time.sleep(2); ticks1, rss1 = stats()
            cpu = (ticks1-ticks0)/os.sysconf('SC_CLK_TCK')/(time.monotonic()-started)*100
            check('idle CPU below 1 percent', cpu<1)
            check('idle RSS below 32 MiB', rss1<32*1024*1024)
            process.kill(); process.wait(); process = start()
            s = connect(); clients.append(s)
            check('crash restart stale socket recovery', request(s, 'restart', 'snapshot')['state']=='idle')
            fresh = request(s, 'fresh', 'virtual_wake')
            check('restart does not reuse session identity', fresh['session_id'] != sid)
            check('precrash cancel cannot affect new session', request(s, 'stale-restart', 'cancel', session_id=sid)['code']=='stale_session')
            process.terminate(); check('graceful shutdown', process.wait(timeout=3)==0)
            check('socket cleanup', not (root/'core.sock').exists())
            process = start(False); s = connect(); clients.append(s)
            check('production rejects virtual wake', request(s, 'prod', 'virtual_wake')['code']=='virtual_input_disabled')
            process.terminate(); process.wait(timeout=3)
            check('private storage', all(p.stat().st_mode & 0o077==0 for p in root.iterdir()))
            (root/'config.json').write_text('broken')
            process = start(False); s = connect(); clients.append(s)
            invalid = request(s, 'invalid-config', 'snapshot')
            check('corrupt config preserved in safe mode', invalid['configuration_status']=='safe_mode' and invalid['state']=='idle' and (root/'config.json').read_text()=='broken')
            process.terminate(); process.wait(timeout=3)
            (root/'config.json').unlink(); sentinel = Path(td)/'sentinel'; sentinel.write_text('untouched')
            (root/'config.json').symlink_to(sentinel)
            unsafe = subprocess.run([str(BINARY), '--root', str(root)], env=env, capture_output=True, timeout=3)
            check('symlink config rejected', unsafe.returncode!=0 and sentinel.read_text()=='untouched')
            return {'gate': 'A0', 'checks': checks, 'passed': len(checks), 'failed': 0, 'ignored': 0, 'binary_sha256': hashlib.sha256(BINARY.read_bytes()).hexdigest(), 'idle_cpu_percent': cpu, 'idle_rss_bytes': rss1, 'physical_validation': 'NOT_PERFORMED', 'runtime': 'isolated HOME/XDG; Unix IPC; no device or personal bus adapters'}
        finally:
            for client in clients: client.close()
            if process and process.poll() is None: process.terminate(); process.wait(timeout=3)

if __name__ == '__main__':
    evidence = run()
    destination = BASE/'target/evidence/a0.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, indent=2)+'\n')
    print(json.dumps(evidence, indent=2))
