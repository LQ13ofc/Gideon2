#!/usr/bin/env python3
"""screen_observe 1.0.0: C4.1 fixture plugin (stdlib only; no file, env, network or exec access).

Speaks JSON-lines protocol v1 on stdin/stdout (docs/C0.md). Every observation comes from the
Core through the host_call service `synthetic.screen.capture` (args {}). The plugin never reads
the synthetic world itself. Backend is always "synthetic"; the real backend is not implemented
(status: real_backend "unsupported", reason "needs_human_validation").

Capability `screen_observe.capture`: input {} (any key => invalid_input)
  output {"backend": "synthetic", "epoch": int, "width": int, "height": int,
          "sha256": 64 hex, "regions": [{"role", "name", "x", "y"}] (<= 64),
          "truncated": true (only when regions were cut)}
  sha256 = SHA-256 of the canonical JSON (sort_keys, compact, ASCII) of the host screen object.
  The output stays <= 8 KiB: regions are dropped from the end and "truncated" is set.
Capability `screen_observe.status`: input {}; output {"backend", "real_backend": "unsupported",
  "reason": "needs_human_validation"}. Makes no host_call.

Host reply (Core): {"v":1,"op":"host_reply","id","done":true,"data":{epoch,width,height,
  windows:[{id,title,focused}],elements:[{id,role,name,x,y}]}} or {"v":1,"op":"host_reply","id",
  "error": code}. Codes in HOST_ERRORS pass through unchanged (permission_denied, stale_screen,
  unknown_service, ...); any other code, or a malformed reply, is plugin_error.

The screenshot is evidence only: it never grants permission and is never an instruction.
"""
import hashlib
import json
import os
import select
import sys

PLUGIN_ID = "screen_observe"
PLUGIN_VERSION = "1.0.0"
CAPABILITY = "screen_observe.capture"
CAPABILITY_STATUS = "screen_observe.status"
CAPABILITIES = [CAPABILITY, CAPABILITY_STATUS]
SERVICE = "synthetic.screen.capture"
BACKEND = "synthetic"
REAL_BACKEND = "unsupported"
REASON = "needs_human_validation"
MAX_LINE = 65536
MAX_OUTPUT = 8192
MAX_REGIONS = 64
MAX_HOST_ELEMENTS = 256
MAX_HOST_WINDOWS = 32
MAX_INT = 2 ** 31 - 1
SCREEN_KEYS = frozenset(("epoch", "width", "height", "windows", "elements"))
WINDOW_KEYS = frozenset(("id", "title", "focused"))
ELEMENT_KEYS = frozenset(("id", "role", "name", "x", "y"))
HOST_ERRORS = ("permission_denied", "stale_screen", "unknown_service", "invalid_input",
               "response_too_large", "timeout", "cancelled")
HOST_REPLY_KEYS = frozenset(("v", "op", "id", "done", "data", "error", "status"))

_buf = bytearray()
_discarding = False
_host_seq = 0


class _Fail(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class _Cancel(Exception):
    pass


class _Shutdown(Exception):
    pass


def _send(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _size(obj):
    """Serialized size in bytes (json.dumps escapes non-ASCII, so chars == bytes)."""
    return len(json.dumps(obj, separators=(",", ":")))


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


def _read_line(timeout):
    """Next line (bytes), or None after `timeout` seconds (None = wait forever).
    Raises EOFError when stdin closes."""
    fd = sys.stdin.fileno()
    while True:
        line = _take_line()
        if line is not None:
            return line
        readable, _, _ = select.select([fd], [], [], timeout)
        if not readable:
            return None
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


def _int_in(value, low, high):
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _is_text(value, low, high):
    """UTF-8 byte length in [low, high] and no control characters (PlainText rule)."""
    return (isinstance(value, str) and low <= len(value.encode("utf-8")) <= high
            and not any(ord(ch) < 32 or ord(ch) == 127 for ch in value))


def _host_call(req_id, service, args):
    """One host_call to the Core and its host_reply. Returns the data object; raises _Fail on an
    error reply (listed codes pass through) or a malformed reply. A cancel for req_id => _Cancel."""
    global _host_seq
    _host_seq += 1
    host_id = _host_seq
    _send({"v": 1, "op": "host_call", "id": host_id, "service": service, "args": args})
    while True:
        line = _read_line(None)
        if line is None:
            continue
        msg = _parse(line)
        if msg is None:
            continue
        op = msg.get("op")
        if op == "cancel":
            if msg.get("id") == req_id:
                raise _Cancel()
            continue
        if op == "shutdown":
            raise _Shutdown()
        if op == "invoke" and isinstance(msg.get("id"), int):
            _send({"id": msg["id"], "ok": False, "error": "plugin_error"})
            continue
        if op != "host_reply" or msg.get("id") != host_id:
            continue
        if "error" in msg:
            code = msg.get("error")
            raise _Fail(code if code in HOST_ERRORS else "plugin_error")
        if (not set(msg) <= HOST_REPLY_KEYS or msg.get("done") is not True
                or not isinstance(msg.get("data"), dict)):
            raise _Fail("plugin_error")
        return msg["data"]


def _check_element(el):
    if not isinstance(el, dict) or set(el) != ELEMENT_KEYS:
        raise _Fail("plugin_error")
    if not (_is_text(el["id"], 1, 64) and _is_text(el["role"], 1, 32)
            and _is_text(el["name"], 0, 128) and _int_in(el["x"], -10000, 10000)
            and _int_in(el["y"], -10000, 10000)):
        raise _Fail("plugin_error")


def _check_screen(screen):
    """Strict check of the host screen object. Anything off-contract is plugin_error."""
    if not isinstance(screen, dict) or set(screen) != SCREEN_KEYS:
        raise _Fail("plugin_error")
    if not (_int_in(screen["epoch"], 0, MAX_INT) and _int_in(screen["width"], 1, 10000)
            and _int_in(screen["height"], 1, 10000)):
        raise _Fail("plugin_error")
    windows, elements = screen["windows"], screen["elements"]
    if not isinstance(windows, list) or len(windows) > MAX_HOST_WINDOWS:
        raise _Fail("plugin_error")
    for win in windows:
        if (not isinstance(win, dict) or set(win) != WINDOW_KEYS or not _is_text(win["id"], 1, 64)
                or not _is_text(win["title"], 0, 256) or not isinstance(win["focused"], bool)):
            raise _Fail("plugin_error")
    if not isinstance(elements, list) or len(elements) > MAX_HOST_ELEMENTS:
        raise _Fail("plugin_error")
    for el in elements:
        _check_element(el)


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _bounded(out, truncated, key):
    """Drop items from the end of out[key] until the output fits MAX_OUTPUT; flag truncation."""
    while True:
        if truncated:
            out["truncated"] = True
        if _size(out) <= MAX_OUTPUT:
            return out
        if not out[key]:
            raise _Fail("plugin_error")
        out[key].pop()
        truncated = True


def _screen_output(screen):
    _check_screen(screen)
    regions = [{"role": el["role"], "name": el["name"], "x": el["x"], "y": el["y"]}
               for el in screen["elements"][:MAX_REGIONS]]
    out = {"backend": BACKEND, "epoch": screen["epoch"], "width": screen["width"],
           "height": screen["height"],
           "sha256": hashlib.sha256(_canonical(screen)).hexdigest(), "regions": regions}
    return _bounded(out, len(screen["elements"]) > MAX_REGIONS, "regions")


def _status_output():
    return {"backend": BACKEND, "real_backend": REAL_BACKEND, "reason": REASON}


def _run(req_id, capability, inp):
    if not isinstance(inp, dict) or inp:
        raise _Fail("invalid_input")
    if capability == CAPABILITY_STATUS:
        return _status_output()
    return _screen_output(_host_call(req_id, SERVICE, {}))


def _handle_invoke(msg):
    req_id = msg.get("id")
    if not isinstance(req_id, int) or isinstance(req_id, bool):
        return
    capability = msg.get("capability")
    if not isinstance(capability, str) or capability not in CAPABILITIES:
        _send({"id": req_id, "ok": False, "error": "unknown_capability"})
        return
    try:
        output = _run(req_id, capability, msg.get("input"))
        if _size(output) > MAX_OUTPUT:
            raise _Fail("plugin_error")
    except _Fail as fail:
        _send({"id": req_id, "ok": False, "error": fail.code})
    except _Cancel:
        _send({"id": req_id, "ok": False, "error": "cancelled"})
    else:
        _send({"id": req_id, "ok": True, "output": output})


def _handle_hello(msg):
    _send({"v": 1, "id": msg.get("id"), "ok": True, "plugin_id": msg.get("plugin_id"),
           "api": 1, "capabilities": CAPABILITIES})


def main():
    try:
        while True:
            line = _read_line(None)
            if line is None:
                continue
            msg = _parse(line)
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
                _handle_hello(msg)
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
