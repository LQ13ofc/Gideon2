#!/usr/bin/env python3
"""display_manipulate 1.0.0: C4.6 fixture plugin (stdlib only, single file, no host calls).

Speaks JSON-lines protocol v1 on stdin/stdout (docs/C0.md, docs/C4.md). The only capability is
display_manipulate.status, input {} exactly. It always answers the UNSUPPORTED object of docs/C4.md:
this environment has no compositor API, and overlay or capture is not output manipulation. There
is no manipulation action, no host service and no real backend.
"""
import json
import os
import sys

PLUGIN_ID = "display_manipulate"
CAP_STATUS = "display_manipulate.status"
CAPABILITIES = [CAP_STATUS]
MAX_LINE = 65536
UNSUPPORTED = {
    "supported": False,
    "state": "UNSUPPORTED",
    "reason": "no_compositor_api_in_environment",
    "note": "overlay/captura não é manipulação de saída",
}

_buf = bytearray()
_discarding = False


class _Shutdown(Exception):
    pass


def _send(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


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


def _read_line():
    """Next complete line (bytes). Raises EOFError when stdin closes."""
    fd = sys.stdin.fileno()
    while True:
        line = _take_line()
        if line is not None:
            return line
        chunk = os.read(fd, 65536)
        if not chunk:
            raise EOFError
        _buf.extend(chunk)


def _parse(line):
    try:
        msg = json.loads(line)
    except ValueError:
        return None
    return msg if isinstance(msg, dict) else None


def _handle_invoke(msg):
    req_id = msg.get("id")
    if not isinstance(req_id, int) or isinstance(req_id, bool):
        return
    if msg.get("capability") != CAP_STATUS:
        _send({"id": req_id, "ok": False, "error": "unknown_capability"})
        return
    inp = msg.get("input")
    if not isinstance(inp, dict) or inp:
        _send({"id": req_id, "ok": False, "error": "invalid_input"})
        return
    _send({"id": req_id, "ok": True, "output": dict(UNSUPPORTED)})


def main():
    try:
        while True:
            msg = _parse(_read_line())
            if msg is None:
                continue
            if msg.get("v", 1) != 1:
                if isinstance(msg.get("id"), int):
                    _send({"id": msg["id"], "ok": False, "error": "unsupported_version"})
                continue
            op = msg.get("op")
            if op == "shutdown":
                return 0
            if op == "hello":
                _send({"v": 1, "id": msg.get("id"), "ok": True,
                       "plugin_id": msg.get("plugin_id"), "api": 1, "capabilities": CAPABILITIES})
            elif op == "invoke":
                _handle_invoke(msg)
            elif op in ("cancel", "host_reply"):
                continue
            elif isinstance(msg.get("id"), int):
                _send({"id": msg["id"], "ok": False, "error": "unknown_op"})
    except (EOFError, _Shutdown):
        return 0


if __name__ == "__main__":
    sys.exit(main())
