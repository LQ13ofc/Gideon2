#!/usr/bin/env python3
"""audio_advanced 1.0.0: C4.3 fixture plugin (stdlib only, single file, no file/env/network access).

Speaks JSON-lines protocol v1 on stdin/stdout (docs/C0.md, docs/C4.md). All data comes from the
host services synthetic.audio.{state,set_route,app_volume,eq,denoise} (the Core's synthetic world,
backend "synthetic"). The plugin never names base.*, has no real audio backend, and every output
says real_backend "unsupported" with reason "needs_human_validation".

Capability `audio_advanced.state` (read): input {} -> output {backend, real_backend, reason,
  routes: [{id, active}] (<=8), apps: [{id, volume}] (<=8), eq, denoise}.
Capability `audio_advanced.act` (state_changing): input exactly one of
  {"kind": "route", "route": id}
  {"kind": "app_volume", "app": id, "volume": 0..100}
  {"kind": "eq", "preset": P}            P in EQ_PRESETS (fixed list)
  {"kind": "denoise", "enabled": bool}
  Output: the state view plus {kind, verified}. The state is read again after the change;
  verified is true only when that read shows the requested value.
Host errors (permission_denied, invalid_input, ...) pass through unchanged. Any other host
error, or a malformed host reply, is plugin_error.
"""
import json
import os
import re
import sys

PLUGIN_ID = "audio_advanced"
CAP_STATE = "audio_advanced.state"
CAP_ACT = "audio_advanced.act"
CAPABILITIES = [CAP_STATE, CAP_ACT]
BACKEND = "synthetic"
REAL_BACKEND = "unsupported"
REASON = "needs_human_validation"
MAX_LINE = 65536
MAX_OUTPUT = 8192
MAX_HOST_REPLY = 4096
MAX_ITEMS = 8
EQ_PRESETS = ("flat", "voice", "bass", "treble")
HOST_ERRORS = ("permission_denied", "opt_in_required", "invalid_input", "unknown_service",
                "world_unavailable")
ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
ACT_KEYS = {
    "route": frozenset(("kind", "route")),
    "app_volume": frozenset(("kind", "app", "volume")),
    "eq": frozenset(("kind", "preset")),
    "denoise": frozenset(("kind", "enabled")),
}

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


def _int_in(value, low, high):
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _no_input(inp):
    if not isinstance(inp, dict) or inp:
        raise _Fail("invalid_input")


def _view(data):
    """Validated synthetic.audio.state reply as output fields (base.* and extra keys dropped)."""
    routes, apps = data.get("routes"), data.get("apps")
    eq, denoise = data.get("eq"), data.get("denoise")
    if not isinstance(routes, list) or len(routes) > MAX_ITEMS:
        raise _Fail("plugin_error")
    if not isinstance(apps, list) or len(apps) > MAX_ITEMS:
        raise _Fail("plugin_error")
    if not isinstance(eq, str) or eq not in EQ_PRESETS or not isinstance(denoise, bool):
        raise _Fail("plugin_error")
    clean_routes = []
    for route in routes:
        if not isinstance(route, dict) or not _valid_id(route.get("id")):
            raise _Fail("plugin_error")
        if not isinstance(route.get("active"), bool):
            raise _Fail("plugin_error")
        clean_routes.append({"id": route["id"], "active": route["active"]})
    clean_apps = []
    for app in apps:
        if not isinstance(app, dict) or not _valid_id(app.get("id")):
            raise _Fail("plugin_error")
        if not _int_in(app.get("volume"), 0, 100):
            raise _Fail("plugin_error")
        clean_apps.append({"id": app["id"], "volume": app["volume"]})
    return dict(_status(), routes=clean_routes, apps=clean_apps, eq=eq, denoise=denoise)


def _read(req_id):
    return _view(_host_call(req_id, "synthetic.audio.state", {}))


def _state(req_id, inp):
    _no_input(inp)
    return _read(req_id)


def _applied(kind, inp, view):
    if kind == "route":
        active = [route["id"] for route in view["routes"] if route["active"]]
        return active == [inp["route"]]
    if kind == "app_volume":
        return any(app["id"] == inp["app"] and app["volume"] == inp["volume"]
                   for app in view["apps"])
    if kind == "eq":
        return view["eq"] == inp["preset"]
    return view["denoise"] == inp["enabled"]


def _act(req_id, inp):
    if not isinstance(inp, dict):
        raise _Fail("invalid_input")
    kind = inp.get("kind")
    if not isinstance(kind, str) or ACT_KEYS.get(kind) != frozenset(inp):
        raise _Fail("invalid_input")
    if kind == "route":
        route = inp["route"]
        if not _valid_id(route):
            raise _Fail("invalid_input")
        service, args = "synthetic.audio.set_route", {"route": route}
    elif kind == "app_volume":
        app, volume = inp["app"], inp["volume"]
        if not _valid_id(app) or not _int_in(volume, 0, 100):
            raise _Fail("invalid_input")
        service, args = "synthetic.audio.app_volume", {"app": app, "volume": volume}
    elif kind == "eq":
        preset = inp["preset"]
        if not isinstance(preset, str) or preset not in EQ_PRESETS:
            raise _Fail("invalid_input")
        service, args = "synthetic.audio.eq", {"preset": preset}
    else:
        enabled = inp["enabled"]
        if not isinstance(enabled, bool):
            raise _Fail("invalid_input")
        service, args = "synthetic.audio.denoise", {"enabled": enabled}
    _host_call(req_id, service, args)
    view = _read(req_id)
    return dict(view, kind=kind, verified=_applied(kind, inp, view))


HANDLERS = {CAP_STATE: _state, CAP_ACT: _act}


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
