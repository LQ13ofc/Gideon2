#!/usr/bin/env python3
"""camera_gesture 1.0.0: C4.5 fixture plugin (stdlib only, single file, no file/env/network access).

Speaks JSON-lines protocol v1 on stdin/stdout (docs/C0.md, docs/C4.md). All data comes from the
host services synthetic.camera.{state,optin,capture,gestures} (the Core's synthetic world,
backend "synthetic"). The plugin never names base.*, has no real webcam backend, and every
output says real_backend "unsupported" with reason "needs_human_validation".

Privacy: opt-in is OFF by default. The privacy indicator equals the opt-in state: a view where
indicator and opt_in differ is never reported (plugin_error). Capture returns counters only,
never pixels. Host errors pass through unchanged (permission_denied, opt_in_required, ...).

Capabilities (input must match exactly):
  camera_gesture.state     {}                 -> {opt_in, indicator, frame_seq, gesture}
  camera_gesture.optin     {"enabled": bool}  -> view + verified (opt-out clears frames)
  camera_gesture.capture   {}                 -> view (frame_seq counter only); no opt-in ->
                                                 opt_in_required
  camera_gesture.gestures  {}                 -> {gestures: [id, ...] (<=16)}; no opt-in ->
                                                 opt_in_required
Any other host error, or a malformed host reply, is plugin_error.
"""
import json
import os
import re
import sys

PLUGIN_ID = "camera_gesture"
CAP_STATE = "camera_gesture.state"
CAP_OPTIN = "camera_gesture.optin"
CAP_CAPTURE = "camera_gesture.capture"
CAP_GESTURES = "camera_gesture.gestures"
CAPABILITIES = [CAP_STATE, CAP_OPTIN, CAP_CAPTURE, CAP_GESTURES]
BACKEND = "synthetic"
REAL_BACKEND = "unsupported"
REASON = "needs_human_validation"
MAX_LINE = 65536
MAX_OUTPUT = 8192
MAX_HOST_REPLY = 4096
MAX_GESTURES = 16
MAX_FRAME_SEQ = 2 ** 31 - 1
HOST_ERRORS = ("permission_denied", "opt_in_required", "invalid_input", "unknown_service",
               "world_unavailable")
ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")

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


def _host_call(req_id, service, args):
    """One host_call; returns the reply data object. A cancel for req_id while waiting raises
    _Cancel. Host errors in HOST_ERRORS pass through; anything else is plugin_error."""
    global _host_seq
    _host_seq += 1
    host_id = _host_seq
    _send({"op": "host_call", "id": host_id, "service": service, "args": args})
    while True:
        msg = _parse(_read_line())
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
        data = msg.get("data")
        if msg.get("done") is not True or not isinstance(data, dict):
            raise _Fail("plugin_error")
        if _size(data) > MAX_HOST_REPLY:
            raise _Fail("plugin_error")
        return data


def _status():
    return {"backend": BACKEND, "real_backend": REAL_BACKEND, "reason": REASON}


def _valid_id(value):
    return isinstance(value, str) and ID_RE.fullmatch(value) is not None


def _no_input(inp):
    if not isinstance(inp, dict) or inp:
        raise _Fail("invalid_input")


def _view(data):
    """Validated synthetic.camera reply: opt_in, indicator (equal to opt_in), frame_seq."""
    opt_in, indicator, frame_seq = data.get("opt_in"), data.get("indicator"), data.get("frame_seq")
    if not isinstance(opt_in, bool) or not isinstance(indicator, bool):
        raise _Fail("plugin_error")
    if indicator != opt_in:
        raise _Fail("plugin_error")  # the privacy indicator is on exactly while opt-in is on
    if isinstance(frame_seq, bool) or not isinstance(frame_seq, int):
        raise _Fail("plugin_error")
    if not 0 <= frame_seq <= MAX_FRAME_SEQ:
        raise _Fail("plugin_error")
    return dict(_status(), opt_in=opt_in, indicator=indicator, frame_seq=frame_seq)


def _read(req_id):
    return _view(_host_call(req_id, "synthetic.camera.state", {}))


def _state(req_id, inp):
    _no_input(inp)
    data = _host_call(req_id, "synthetic.camera.state", {})
    gesture = data.get("gesture")
    if gesture is not None and not _valid_id(gesture):
        raise _Fail("plugin_error")
    return dict(_view(data), gesture=gesture)


def _optin(req_id, inp):
    if not isinstance(inp, dict) or set(inp) != {"enabled"} or not isinstance(inp["enabled"], bool):
        raise _Fail("invalid_input")
    enabled = inp["enabled"]
    _host_call(req_id, "synthetic.camera.optin", {"enabled": enabled})
    view = _read(req_id)
    return dict(view, verified=view["opt_in"] == enabled)


def _capture(req_id, inp):
    _no_input(inp)
    view = _view(_host_call(req_id, "synthetic.camera.capture", {}))
    if not view["opt_in"]:
        raise _Fail("opt_in_required")
    return view


def _gestures(req_id, inp):
    _no_input(inp)
    data = _host_call(req_id, "synthetic.camera.gestures", {})
    items = data.get("gestures")
    if not isinstance(items, list) or len(items) > MAX_GESTURES:
        raise _Fail("plugin_error")
    if not all(_valid_id(item) for item in items):
        raise _Fail("plugin_error")
    return dict(_status(), gestures=list(items))


HANDLERS = {CAP_STATE: _state, CAP_OPTIN: _optin, CAP_CAPTURE: _capture, CAP_GESTURES: _gestures}


def _handle_invoke(msg):
    req_id = msg.get("id")
    if not isinstance(req_id, int) or isinstance(req_id, bool):
        return
    capability = msg.get("capability")
    handler = HANDLERS.get(capability) if isinstance(capability, str) else None
    if handler is None:
        _send({"id": req_id, "ok": False, "error": "unknown_capability"})
        return
    try:
        output = handler(req_id, msg.get("input"))
    except _Fail as fail:
        _send({"id": req_id, "ok": False, "error": fail.code})
    except _Cancel:
        _send({"id": req_id, "ok": False, "error": "cancelled"})
    else:
        if _size(output) > MAX_OUTPUT:
            _send({"id": req_id, "ok": False, "error": "plugin_error"})
        else:
            _send({"id": req_id, "ok": True, "output": output})


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
