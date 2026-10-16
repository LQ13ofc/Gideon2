#!/usr/bin/env python3
"""mic_advanced 1.0.0: C4.4 fixture plugin (stdlib only, single file, no file/env/network access).

Speaks JSON-lines protocol v1 on stdin/stdout (docs/C0.md, docs/C4.md). All data comes from the
host services synthetic.mic.{state,configure,monitor,record_start,record_stop} (the Core's
synthetic world, backend "synthetic"). The plugin never names base.*, has no real microphone
backend, and every output says real_backend "unsupported" with reason "needs_human_validation".

Capabilities (input must match exactly; output = mic view + status fields):
  mic_advanced.state      {}                               -> view
  mic_advanced.configure  {"gain"?: 0..100, "filter"?: F}  (at least one key) -> view + verified
                          F in MIC_FILTERS (fixed list)
  mic_advanced.monitor    {"enabled": bool}                -> view + verified
  mic_advanced.record     {"action": "start" | "stop"}     -> view + verified
The view is {device, gain, filter, monitor, recording, indicator}. recording true with
indicator false is never reported (plugin_error): nothing records without the indicator.
"verified" is taken from a fresh synthetic.mic.state read after the change.
Host errors (permission_denied, ...) pass through unchanged. Any other host error, or a
malformed host reply, is plugin_error.
"""
import json
import os
import re
import sys

PLUGIN_ID = "mic_advanced"
CAP_STATE = "mic_advanced.state"
CAP_CONFIGURE = "mic_advanced.configure"
CAP_MONITOR = "mic_advanced.monitor"
CAP_RECORD = "mic_advanced.record"
CAPABILITIES = [CAP_STATE, CAP_CONFIGURE, CAP_MONITOR, CAP_RECORD]
BACKEND = "synthetic"
REAL_BACKEND = "unsupported"
REASON = "needs_human_validation"
MAX_LINE = 65536
MAX_OUTPUT = 8192
MAX_HOST_REPLY = 4096
MIC_FILTERS = ("off", "low_cut", "voice")
CONFIGURE_KEYS = frozenset(("gain", "filter"))
RECORD_SERVICES = {"start": "synthetic.mic.record_start", "stop": "synthetic.mic.record_stop"}
HOST_ERRORS = ("permission_denied", "opt_in_required", "invalid_input", "unknown_service",
                "world_unavailable", "indicator_off", "already_recording",
                "not_recording")
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


def _int_in(value, low, high):
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _no_input(inp):
    if not isinstance(inp, dict) or inp:
        raise _Fail("invalid_input")


def _view(data):
    """Validated synthetic.mic.state reply as output fields (extra keys dropped)."""
    device, gain, filt = data.get("device"), data.get("gain"), data.get("filter")
    monitor, recording, indicator = data.get("monitor"), data.get("recording"), data.get("indicator")
    if not _valid_id(device) or not _int_in(gain, 0, 100):
        raise _Fail("plugin_error")
    if not isinstance(filt, str) or filt not in MIC_FILTERS:
        raise _Fail("plugin_error")
    if not all(isinstance(flag, bool) for flag in (monitor, recording, indicator)):
        raise _Fail("plugin_error")
    if recording and not indicator:
        raise _Fail("plugin_error")  # recording without the privacy indicator is never reported
    return dict(_status(), device=device, gain=gain, filter=filt, monitor=monitor,
                recording=recording, indicator=indicator)


def _read(req_id):
    return _view(_host_call(req_id, "synthetic.mic.state", {}))


def _state(req_id, inp):
    _no_input(inp)
    return _read(req_id)


def _configure(req_id, inp):
    if not isinstance(inp, dict) or not inp or not set(inp) <= CONFIGURE_KEYS:
        raise _Fail("invalid_input")
    args = {}
    if "gain" in inp:
        if not _int_in(inp["gain"], 0, 100):
            raise _Fail("invalid_input")
        args["gain"] = inp["gain"]
    if "filter" in inp:
        if not isinstance(inp["filter"], str) or inp["filter"] not in MIC_FILTERS:
            raise _Fail("invalid_input")
        args["filter"] = inp["filter"]
    _host_call(req_id, "synthetic.mic.configure", args)
    view = _read(req_id)
    applied = all(view[key] == value for key, value in args.items())
    return dict(view, verified=applied)


def _monitor(req_id, inp):
    if not isinstance(inp, dict) or set(inp) != {"enabled"} or not isinstance(inp["enabled"], bool):
        raise _Fail("invalid_input")
    enabled = inp["enabled"]
    _host_call(req_id, "synthetic.mic.monitor", {"enabled": enabled})
    view = _read(req_id)
    return dict(view, verified=view["monitor"] == enabled)


def _record(req_id, inp):
    if not isinstance(inp, dict) or set(inp) != {"action"}:
        raise _Fail("invalid_input")
    action = inp["action"]
    if not isinstance(action, str) or action not in RECORD_SERVICES:
        raise _Fail("invalid_input")
    _host_call(req_id, RECORD_SERVICES[action], {})
    view = _read(req_id)
    if action == "start":
        verified = view["recording"] and view["indicator"]
    else:
        verified = not view["recording"] and not view["indicator"]
    return dict(view, action=action, verified=verified)


HANDLERS = {CAP_STATE: _state, CAP_CONFIGURE: _configure, CAP_MONITOR: _monitor,
            CAP_RECORD: _record}


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
