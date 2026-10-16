#!/usr/bin/env python3
"""dummy_echo: C0 fixture plugin (stdlib only, no file/network/exec side effects).

Speaks JSON-lines protocol v1 on stdin/stdout. Every stdout line is flushed.
Capability `dummy_echo.echo`: input {"text": str<=256, "sleep_ms": int 0..5000 (optional)}
-> output {"text": text.upper(), "count": n}, where n counts valid invocations in this process.
"""
import json
import os
import select
import sys
import time

PLUGIN_ID = "dummy_echo"
CAPABILITY = "dummy_echo.echo"
CAPABILITIES = [CAPABILITY]
MAX_LINE = 65536
MAX_TEXT = 256
MAX_SLEEP_MS = 5000
INPUT_KEYS = {"text", "sleep_ms"}

_buf = bytearray()
_discarding = False
_invocations = 0


def send(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _fill(timeout):
    """Wait up to timeout seconds (None = forever) for stdin. False on EOF."""
    fd = sys.stdin.fileno()
    readable, _, _ = select.select([fd], [], [], timeout)
    if not readable:
        return True
    chunk = os.read(fd, 65536)
    if not chunk:
        return False
    _buf.extend(chunk)
    return True


def _take_line():
    """Next complete line without newline, or None. Lines over MAX_LINE are dropped."""
    global _discarding
    while True:
        newline = _buf.find(b"\n")
        if newline < 0:
            if len(_buf) > MAX_LINE:
                _buf.clear()
                _discarding = True
            return None
        line = bytes(_buf[:newline])
        del _buf[: newline + 1]
        if _discarding:
            _discarding = False
            continue
        if len(line) > MAX_LINE:
            continue
        return line


def _parse(line):
    try:
        msg = json.loads(line)
    except ValueError:
        return None
    return msg if isinstance(msg, dict) else None


def _valid_input(inp):
    """Return (text, sleep_ms) or None when input is invalid."""
    if not isinstance(inp, dict) or not set(inp) <= INPUT_KEYS:
        return None
    text = inp.get("text")
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        return None
    sleep_ms = inp.get("sleep_ms", 0)
    if isinstance(sleep_ms, bool) or not isinstance(sleep_ms, int):
        return None
    if not 0 <= sleep_ms <= MAX_SLEEP_MS:
        return None
    return text, sleep_ms


def _sleep_cancellable(req_id, seconds):
    """Sleep in small slices; return False if a cancel for req_id arrives first."""
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True
        if not _fill(min(remaining, 0.02)):
            sys.exit(0)
        while True:
            line = _take_line()
            if line is None:
                break
            msg = _parse(line)
            if msg is None:
                continue
            if msg.get("op") == "cancel" and msg.get("id") == req_id:
                return False
            if msg.get("op") == "shutdown":
                sys.exit(0)


def _handle_invoke(msg):
    global _invocations
    req_id = msg.get("id")
    if not isinstance(req_id, int) or isinstance(req_id, bool):
        return
    if msg.get("capability") != CAPABILITY:
        send({"id": req_id, "ok": False, "error": "unknown_capability"})
        return
    parsed = _valid_input(msg.get("input"))
    if parsed is None:
        send({"id": req_id, "ok": False, "error": "invalid_input"})
        return
    text, sleep_ms = parsed
    _invocations += 1
    if sleep_ms and not _sleep_cancellable(req_id, sleep_ms / 1000.0):
        send({"id": req_id, "ok": False, "error": "cancelled"})
        return
    send({"id": req_id, "ok": True,
          "output": {"text": text.upper(), "count": _invocations}})


def _handle_hello(msg):
    send({"v": 1, "id": msg.get("id"), "ok": True, "plugin_id": msg.get("plugin_id"),
          "api": 1, "capabilities": CAPABILITIES})
    send({"event": "log", "level": "info", "text": "dummy ready"})


def main():
    while True:
        line = _take_line()
        if line is None:
            if not _fill(None):
                return 0
            continue
        msg = _parse(line)
        if msg is None:
            continue
        if msg.get("v", 1) != 1:
            if isinstance(msg.get("id"), int):
                send({"id": msg["id"], "ok": False, "error": "unsupported_version"})
            continue
        op = msg.get("op")
        if op == "shutdown":
            return 0
        if op == "hello":
            _handle_hello(msg)
        elif op == "invoke":
            _handle_invoke(msg)
        elif op == "cancel":
            continue
        elif isinstance(msg.get("id"), int):
            send({"id": msg["id"], "ok": False, "error": "unknown_op"})


if __name__ == "__main__":
    sys.exit(main())
