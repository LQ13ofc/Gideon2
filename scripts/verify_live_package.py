#!/usr/bin/env python3
"""Live voice check of an INSTALLED gideon-base package (A14), with PipeWire lab devices and lab speech clips.

Usage: scripts/verify_live_package.py --install-root ROOT [--profile PERFIL] [--clips DIR]
                                      [--positives N] [--negatives N]

ROOT is a root made by gideon-install (scripts/package_tools/gideon-install) with the package installed as
`current`. The check:
  1. loads two PipeWire lab modules (a null sink and a remap source of its monitor, names gideon_verify_*); refuses
     to run if they already exist (nothing else is touched), and unloads exactly the modules it loaded;
  2. starts the installed `current/bin/gideon-launch ROOT PERFIL` (a process this script owns) and stops that
     process at the end;
  3. changes only the test profile's preferences (lab mic and lab sink, no session timeout, no feedback sound),
     turns the live microphone on through the ledger, and restarts the Core. The owner's defaults, the system
     default devices and every volume are never changed;
  4. plays >= 6 positive clips ("Hey Gideon, ..." recordings) and >= 3 negative clips into the lab sink, one at a
     time, and reads the Core snapshot after each one;
  5. asserts for each positive: session_started, transcript_final and a command outcome (command_success or
     command_rejected) of that same session; for each negative: no session_started (no false session);
  6. asserts that the diagnostics files live-last-error.txt and stt-last-error.txt are absent, and that the STT
     worker is ready at the end.
Prints a table and one JSON object; exit 0 only when every assertion holds. Stdlib only.
"""
import argparse
import glob
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LAB_SINK = 'gideon_verify_sink'
LAB_MIC = 'gideon_verify_mic'
POSITIVE_GLOB = 'positive/pos-hey_*-clean.wav'
NEGATIVE_GLOB = 'negative/neg-*.wav'
COMMAND_OUTCOMES = ('command_success', 'command_rejected')
CLIP_GAP_S = 5.0
POSITIVE_WAIT_S = 20.0
NEGATIVE_WAIT_S = 6.0
DIAGNOSTIC_FILES = ('live-last-error.txt', 'stt-last-error.txt')


def spread(paths, count):
    """Takes `count` clips round-robin over their kind (the second name field: hey_brave, gideon_alone, babble...)."""
    groups = {}
    for path in paths:
        groups.setdefault(path.name.split('-')[1], []).append(path)
    chosen = []
    while len(chosen) < count and any(groups.values()):
        for kind in sorted(groups):
            if groups[kind] and len(chosen) < count:
                chosen.append(groups[kind].pop(0))
    return chosen


def run_checked(argv):
    """One installer or configure step: argv only (no shell); a non-zero exit is a failure with its output tail."""
    done = subprocess.run(argv, capture_output=True, text=True, timeout=300, check=False)
    if done.returncode != 0:
        raise RuntimeError(f'{Path(argv[-1]).name or argv[-1]} failed ({done.returncode}): {done.stderr[-400:]}{done.stdout[-400:]}')
    return done.stdout


def prepare_profile(root, profile):
    """A fresh install has no profile: create it with gideon-install, then render its manifests with the package's
    own gideon-configure (the same steps the package verifier uses). An existing configured profile is left alone."""
    if not (root / 'profiles' / profile).is_dir():
        run_checked([str(root / 'current/bin/gideon-install'), '--install-root', str(root), 'profile', 'create', profile])
    if not (root / 'profiles' / profile / 'profile' / 'replay-manifest.json').is_file():
        run_checked([str(root / 'current/runtime/python/bin/python3.13'), '-I', '-B',
                     str(root / 'current/bin/gideon-configure'), str(root / 'profiles' / profile)])


def pactl(*args):
    return subprocess.run(['pactl', *args], capture_output=True, text=True, timeout=20).stdout.strip()


def lab_modules_present():
    return [line for line in pactl('list', 'short', 'modules').splitlines() if LAB_SINK in line or LAB_MIC in line]


class Core:
    """One Core socket of the profile; each request is one connection, as the Core protocol requires."""

    def __init__(self, root, profile):
        self.sock_path = root / 'profiles' / profile / 'core' / 'core.sock'
        self.counter = 0

    def call(self, op, **fields):
        self.counter += 1
        message = {'version': 1, 'request_id': f'verify-{os.getpid()}-{self.counter}', 'op': op, **fields}
        sock = socket.socket(socket.AF_UNIX)
        sock.settimeout(20)
        try:
            sock.connect(str(self.sock_path))
            sock.sendall((json.dumps(message) + '\n').encode())
            buffer = b''
            while b'\n' not in buffer:
                chunk = sock.recv(1 << 20)
                if not chunk:
                    break
                buffer += chunk
        finally:
            sock.close()
        return json.loads(buffer.split(b'\n', 1)[0])

    def snapshot(self):
        return self.call('snapshot')


def wait_until(label, seconds, check):
    end = time.monotonic() + seconds
    last = None
    while time.monotonic() < end:
        try:
            last = check()
            if last:
                return last
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(0.5)
    raise TimeoutError(f'timed out waiting for {label}')


def play(clip, sink):
    subprocess.run(['pw-play', '--target', sink, str(clip)], timeout=60, check=False)


def events_after(snap, sequence):
    return [e for e in snap.get('events') or [] if e.get('sequence', 0) > sequence]


def run_clip(core, clip, positive):
    snap = core.snapshot()
    before = max([e.get('sequence', 0) for e in snap.get('events') or []] or [0])
    play(clip, LAB_SINK)
    if positive:
        def settled():
            found = events_after(core.snapshot(), before)
            started = [e for e in found if e['kind'] == 'session_started']
            if not started:
                return None
            sid = started[0]['session_id']
            kinds = {e['kind'] for e in found if e.get('session_id') == sid}
            if 'transcript_final' in kinds and any(k in kinds for k in COMMAND_OUTCOMES):
                return found
            return None
        try:
            found = wait_until(f'session of {clip.name}', POSITIVE_WAIT_S, settled)
        except TimeoutError:
            found = events_after(core.snapshot(), before)
    else:
        time.sleep(NEGATIVE_WAIT_S)
        found = events_after(core.snapshot(), before)
    time.sleep(CLIP_GAP_S)
    return found


def row_of(clip, positive, found):
    started = [e for e in found if e['kind'] == 'session_started']
    sid = started[0]['session_id'] if started else None
    kinds = [e['kind'] for e in found if sid is not None and e.get('session_id') == sid]
    row = {
        'clip': clip.name,
        'expected': 'positive' if positive else 'negative',
        'session_started': bool(started),
        'transcript_final': 'transcript_final' in kinds,
        'command': next((k for k in kinds if k in COMMAND_OUTCOMES), None),
        'false_session': bool(started) and not positive,
        'events': [e['kind'] for e in found],
    }
    if positive:
        row['passed'] = row['session_started'] and row['transcript_final'] and row['command'] is not None
    else:
        row['passed'] = not row['false_session']
    return row


def print_table(rows):
    header = f"{'clip':<42}{'expect':<10}{'started':<9}{'final':<7}{'command':<18}{'result':<7}"
    print(header)
    print('-' * len(header))
    for row in rows:
        print(f"{row['clip']:<42}{row['expected']:<10}{str(row['session_started']):<9}"
              f"{str(row['transcript_final']):<7}{str(row['command']):<18}{'PASS' if row['passed'] else 'FAIL':<7}")


def main():
    parser = argparse.ArgumentParser(description='Live voice check of an installed gideon-base package (A14).')
    parser.add_argument('--install-root', required=True, help='absolute ROOT of gideon-install')
    parser.add_argument('--profile', default='t', help='profile name inside ROOT (default t)')
    parser.add_argument('--clips', default='/tmp/gideon-wake-lab/clips', help='directory with positive/ and negative/ clips')
    parser.add_argument('--positives', type=int, default=8)
    parser.add_argument('--negatives', type=int, default=4)
    # Test-profile experiment only: the owner's wake_sensitivity default is never changed by this tool.
    parser.add_argument('--wake-sensitivity', type=float, default=1.0)
    args = parser.parse_args()
    if not 0.5 <= args.wake_sensitivity <= 1.5:
        parser.error('--wake-sensitivity must be between 0.5 and 1.5')
    if args.positives < 6 or args.negatives < 3:
        parser.error('at least 6 positive and 3 negative clips are required')
    root = Path(args.install_root)
    if not root.is_absolute() or not (root / 'current' / 'bin' / 'gideon-launch').is_file():
        parser.error('--install-root must be an absolute root with current/bin/gideon-launch')
    clips = Path(args.clips)
    positives = sorted(Path(p) for p in glob.glob(str(clips / POSITIVE_GLOB)))
    negatives = sorted(Path(p) for p in glob.glob(str(clips / NEGATIVE_GLOB)))
    chosen_pos = spread(positives, args.positives)
    chosen_neg = spread(negatives, args.negatives)
    if len(chosen_pos) < args.positives or len(chosen_neg) < args.negatives:
        parser.error(f'not enough clips in {clips}: {len(positives)} positive, {len(negatives)} negative')
    if lab_modules_present():
        print(f'refusing: {LAB_SINK} or {LAB_MIC} PipeWire modules already exist; remove them first', file=sys.stderr)
        return 2
    try:
        prepare_profile(root, args.profile)
    except (RuntimeError, subprocess.SubprocessError, OSError) as error:
        print(f'profile setup failed: {error}', file=sys.stderr)
        return 2

    loaded = []
    launch = None
    log = None
    result = {'install_root': str(root), 'profile': args.profile, 'wake_sensitivity': args.wake_sensitivity,
              'rows': [], 'checks': {}}
    try:
        loaded.append(pactl('load-module', 'module-null-sink', f'sink_name={LAB_SINK}',
                            'sink_properties=device.description=GideonVerifySink'))
        loaded.append(pactl('load-module', 'module-remap-source', f'master={LAB_SINK}.monitor',
                            f'source_name={LAB_MIC}', 'source_properties=device.description=GideonVerifyMic'))
        result['lab_modules'] = loaded
        profile_dir = root / 'profiles' / args.profile
        # The launcher output is kept in an unnamed temporary file: nothing is added to the install root.
        log = tempfile.TemporaryFile()
        launch = subprocess.Popen([str(root / 'current/bin/gideon-launch'), '--install-root', str(root), args.profile],
                                  stdout=log, stderr=log)
        core = Core(root, args.profile)
        wait_until('Core socket', 120, lambda: core.snapshot().get('code') == 'ok')
        snap = core.snapshot()
        prefs = snap['preferences']
        reply = core.call('preferences', revision=prefs['revision'], audible_feedback=False,
                          session_timeout_ms=9000, wake_sensitivity=args.wake_sensitivity,
                          audio_input_device=LAB_MIC, audio_output_device=LAB_SINK)
        result['checks']['preferences_ok'] = reply.get('code') == 'ok'
        prefs = core.snapshot()['preferences']
        reply = core.call('live_audio_preference', revision=prefs['revision'], enabled=True, confirmed=True)
        result['checks']['live_preference_ok'] = reply.get('code') == 'ok'
        core.call('core_restart')
        time.sleep(4)
        wait_until('Core after restart', 120, lambda: core.snapshot().get('code') == 'ok')
        wait_until('microphone capturing', 90,
                   lambda: core.snapshot()['audio']['live']['input_state'] == 'capturing')
        wait_until('STT ready', 180, lambda: core.snapshot()['stt_status'] == 'ready')
        result['stt_ready'] = True
        for path in chosen_pos:
            found = run_clip(core, path, True)
            result['rows'].append(row_of(path, True, found))
        for path in chosen_neg:
            found = run_clip(core, path, False)
            result['rows'].append(row_of(path, False, found))
        snap = core.snapshot()
        result['final_stt_status'] = snap['stt_status']
        result['final_stt_last_error'] = snap.get('stt_last_error')
        result['checks']['stt_ready_at_end'] = snap['stt_status'] == 'ready'
        core_dir = profile_dir / 'core'
        for name in DIAGNOSTIC_FILES:
            result['checks'][f'{name}_absent'] = not (core_dir / name).exists()
    finally:
        if launch is not None:
            launch.terminate()
            try:
                launch.wait(30)
            except subprocess.TimeoutExpired:
                launch.kill()
                launch.wait(10)
        for module in reversed(loaded):
            if module:
                pactl('unload-module', module)
        result['lab_modules_left'] = len(lab_modules_present())
        if launch is not None and log is not None:
            log.seek(0)
            result['launcher_tail'] = log.read()[-600:].decode('utf-8', 'replace')
            log.close()
    print_table(result['rows'])
    checks = dict(result['checks'])
    checks['positives_pass'] = all(r['passed'] for r in result['rows'] if r['expected'] == 'positive')
    checks['negatives_pass'] = all(r['passed'] for r in result['rows'] if r['expected'] == 'negative')
    checks['lab_modules_unloaded'] = result['lab_modules_left'] == 0
    result['checks'] = checks
    result['passed'] = all(checks.values()) and len(result['rows']) == args.positives + args.negatives
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
