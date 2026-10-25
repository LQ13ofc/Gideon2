#!/usr/bin/python3
"""Test-only stand-in for scripts/stt_worker.py (A14 tests). Same stdin/stdout protocol, no model.

The manifest (argv[1]) is written by the test:
- engine: the engine name the worker reports (must match the profile the Core reads);
- stall_messages / stall_s: the first N frame messages each block the reader for stall_s seconds (a slow model);
- crash_after: a run exits 1 after this many frame messages (with a stderr line the Core keeps as its diagnostic
  tail). The sandbox /tmp is private, so the test changes the manifest to 0 after the first failure instead.
Only the transport is faked: the text is fixed, so tests check the Core's behaviour, not recognition.
"""
import json
import sys
import time

manifest = json.loads(open(sys.argv[1], 'rb').read())
ENGINE = manifest['engine']
STALL_MESSAGES = int(manifest.get('stall_messages', 0))
STALL_S = float(manifest.get('stall_s', 0.0))
CRASH_AFTER = int(manifest.get('crash_after', 0))


def emit(value):
    print(json.dumps(value, ensure_ascii=True), flush=True)


emit({'op': 'ready', 'engine': ENGINE})
sid = None
end_us = 0
revision = 0
messages = 0
for line in sys.stdin.buffer:
    req = json.loads(line)
    op = req['op']
    if op == 'start':
        sid, end_us, revision, messages = req['session_id'], 0, 0, 0
    elif op == 'frame':
        if req['session_id'] != sid:
            continue
        messages += 1
        end_us = req['end_us']
        if messages <= STALL_MESSAGES:
            time.sleep(STALL_S)
        if CRASH_AFTER and messages >= CRASH_AFTER:
            sys.stderr.write('fake stt crash after %d messages\n' % messages)
            sys.stderr.flush()
            sys.exit(1)
        if messages == 2:
            revision += 1
            emit({'op': 'partial', 'engine': ENGINE, 'session_id': sid, 'revision': revision,
                  'audio_end_us': end_us, 'raw': 'hey gideon'})
    elif op == 'finish':
        if req['session_id'] == sid:
            revision += 1
            emit({'op': 'final', 'engine': ENGINE, 'session_id': sid, 'revision': revision,
                  'audio_end_us': end_us, 'raw': 'hey gideon open brave'})
            sid = None
    elif op == 'cancel':
        if req['session_id'] == sid:
            sid = None
