#!/usr/bin/env python3
"""computer_control 1.0.0: C4.2 fixture plugin (stdlib only; no file, env, network or exec access).

Speaks JSON-lines protocol v1 on stdin/stdout (docs/C0.md). Every observation and action goes
through host_call to the Core (services below). Backend is always "synthetic"; the real backend
is not implemented (status: real_backend "unsupported", reason "needs_human_validation").

Host services (args; reply data object or error code):
  synthetic.input.a11y_tree  {}                       -> {epoch, elements:[{id,role,name,x,y,focused}]}
  synthetic.input.click      {element, epoch}         -> {} (any object)
  synthetic.input.focus      {element, epoch}         -> {} (any object)
  synthetic.input.type       {text, epoch}            -> {} (any object)
  synthetic.input.key        {key, epoch}             -> {} (any object)
A stale epoch is refused by the Core with stale_screen and has no effect.

Capability `computer_control.tree` (input {}): a11y tree first, no pixels.
  output {"backend", "epoch", "elements": [{id,role,name,x,y,focused}] (<= 64), "truncated"?}

Capability `computer_control.act` (input is one typed action; unknown keys => invalid_input):
  {"kind": "click"|"focus", "epoch": int, "element": id}   id: [A-Za-z0-9_.:-]{1,64}
  {"kind": "type", "epoch": int, "text": str}              1..=64 UTF-8 bytes, no control chars
  {"kind": "key", "epoch": int, "key": one of KEYS}
  After the action the plugin re-reads a11y_tree and returns
  {"backend", "kind", "epoch": post-action epoch, "verified": bool, "element"?: id}.
  verified: click/focus => the element has focused true in the re-read tree;
            type/key    => the re-read epoch is greater than the input epoch.
  A host error (stale_screen, permission_denied, ...) on the action or on the re-read is returned
  as is; the action is not retried.

Capability `computer_control.status` (input {}): {"backend", "real_backend": "unsupported",
  "reason": "needs_human_validation"}. Makes no host_call.

Host errors in HOST_ERRORS pass through; any other code or a malformed reply is plugin_error.
Output is always <= 8 KiB.
"""
import json
import os
import re
import select
import sys

PLUGIN_ID = "computer_control"
PLUGIN_VERSION = "1.0.0"
CAPABILITY_TREE = "computer_control.tree"
CAPABILITY_ACT = "computer_control.act"
CAPABILITY_STATUS = "computer_control.status"
CAPABILITIES = [CAPABILITY_TREE, CAPABILITY_ACT, CAPABILITY_STATUS]
TREE_SERVICE = "synthetic.input.a11y_tree"
ACT_SERVICE = {
    "click": "synthetic.input.click",
    "focus": "synthetic.input.focus",
    "type": "synthetic.input.type",
    "key": "synthetic.input.key",
}
BACKEND = "synthetic"
REAL_BACKEND = "unsupported"
REASON = "needs_human_validation"
KEYS = ("Enter", "Escape", "Tab", "Backspace", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight")
MAX_LINE = 65536
MAX_OUTPUT = 8192
MAX_ELEMENTS = 64
MAX_HOST_ELEMENTS = 256
MAX_INT = 2 ** 31 - 1
TEXT_MAX = 64
ID_RE = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
TREE_KEYS = frozenset(("epoch", "elements"))
ELEMENT_KEYS = frozenset(("id", "role", "name", "x", "y", "focused"))
ACT_KEYS = {
    "click": frozenset(("kind", "epoch", "element")),
    "focus": frozenset(("kind", "epoch", "element")),
    "type": frozenset(("kind", "epoch", "text")),
    "key": frozenset(("kind", "epoch", "key")),
}
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
            and _int_in(el["y"], -10000, 10000) and isinstance(el["focused"], bool)):
        raise _Fail("plugin_error")


def _check_tree(tree):
    """Strict check of the host a11y tree. Anything off-contract is plugin_error."""
    if not isinstance(tree, dict) or set(tree) != TREE_KEYS:
        raise _Fail("plugin_error")
    if not _int_in(tree["epoch"], 0, MAX_INT):
        raise _Fail("plugin_error")
    elements = tree["elements"]
    if not isinstance(elements, list) or len(elements) > MAX_HOST_ELEMENTS:
        raise _Fail("plugin_error")
    for el in elements:
        _check_element(el)
    return tree


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


def _tree_output(tree):
    _check_tree(tree)
    out = {"backend": BACKEND, "epoch": tree["epoch"],
           "elements": [dict(el) for el in tree["elements"][:MAX_ELEMENTS]]}
    return _bounded(out, len(tree["elements"]) > MAX_ELEMENTS, "elements")


def _require_empty(inp):
    if not isinstance(inp, dict) or inp:
        raise _Fail("invalid_input")


def _valid_act(inp):
    """(kind, epoch, element_or_None, host_args) for a valid typed action; invalid_input otherwise."""
    if not isinstance(inp, dict):
        raise _Fail("invalid_input")
    kind = inp.get("kind")
    if not isinstance(kind, str) or kind not in ACT_KEYS or set(inp) != ACT_KEYS[kind]:
        raise _Fail("invalid_input")
    epoch = inp["epoch"]
    if not _int_in(epoch, 0, MAX_INT):
        raise _Fail("invalid_input")
    if kind in ("click", "focus"):
        element = inp["element"]
        if not isinstance(element, str) or not ID_RE.fullmatch(element):
            raise _Fail("invalid_input")
        return kind, epoch, element, {"element": element, "epoch": epoch}
    if kind == "type":
        text = inp["text"]
        if not _is_text(text, 1, TEXT_MAX):
            raise _Fail("invalid_input")
        return kind, epoch, None, {"text": text, "epoch": epoch}
    key = inp["key"]
    if not isinstance(key, str) or key not in KEYS:
        raise _Fail("invalid_input")
    return kind, epoch, None, {"key": key, "epoch": epoch}


def _act_output(req_id, inp):
    kind, epoch, element, args = _valid_act(inp)
    _host_call(req_id, ACT_SERVICE[kind], args)
    post = _check_tree(_host_call(req_id, TREE_SERVICE, {}))
    if kind in ("click", "focus"):
        verified = any(el["id"] == element and el["focused"] for el in post["elements"])
    else:
        verified = post["epoch"] > epoch
    out = {"backend": BACKEND, "kind": kind, "epoch": post["epoch"], "verified": verified}
    if element is not None:
        out["element"] = element
    return out


def _status_output():
    return {"backend": BACKEND, "real_backend": REAL_BACKEND, "reason": REASON}


def _run(req_id, capability, inp):
    if capability == CAPABILITY_STATUS:
        _require_empty(inp)
        return _status_output()
    if capability == CAPABILITY_TREE:
        _require_empty(inp)
        return _tree_output(_host_call(req_id, TREE_SERVICE, {}))
    return _act_output(req_id, inp)


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
