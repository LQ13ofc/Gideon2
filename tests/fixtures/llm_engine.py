#!/usr/bin/env python3
"""llm_engine: C1 fixture plugin (stdlib only; no file, env, network or log-content access).

Speaks JSON-lines protocol v1 on stdin/stdout (docs/C0.md, docs/C1.md).
Capability `llm_engine.chat`:
  input  {"messages": [{"role", "content"}] (1..=32, content str <=4096 chars),
          "tools": bool, "max_tokens": int 1..=1024}
  the invoke envelope carries "ctx": {"llm": {"provider", "model"}} chosen by the Core.
  output {"text", "finish_reason", "tool_calls": [{"id","name","arguments"}] (<=4), "usage"?}
The plugin never holds the API key and never adds Authorization: it asks the Core for
`llm.http` with host_call and reassembles the SSE lines that come back in host_reply chunks.
"""
import json
import os
import select
import sys
import time

PLUGIN_ID = "llm_engine"
CAPABILITY = "llm_engine.chat"
CAPABILITIES = [CAPABILITY]
SERVICE = "llm.http"
PATH = "/chat/completions"
MAX_LINE = 65536
MAX_BODY = 256 * 1024
MAX_RAW = 8 * 1024 * 1024  # plugin-side guard; the Core enforces 4 MiB
MAX_SSE_LINE = 65536
MAX_CHUNK = 16384
MAX_MESSAGES = 32
MAX_CONTENT = 4096
MAX_TOKENS = 1024
MAX_OUTPUT = 8192
MAX_PARTIAL = 2048
PARTIAL_TOTAL = 16384  # the Core accumulates at most 16 KiB of partial text
PARTIAL_GAP = 0.05  # at most 20 partial events per second
MAX_TOOL_CALLS = 4
MAX_TOOL_SLOTS = 32
MAX_ID = 64
ROLES = ("system", "user", "assistant", "tool")
INPUT_KEYS = frozenset(("messages", "tools", "max_tokens"))
MESSAGE_KEYS = frozenset(("role", "content"))
HOST_ERRORS = (
    "permission_denied", "cloud_not_authorized", "provider_not_configured", "key_missing",
    "http_error", "timeout", "response_too_large", "network_unavailable", "cancelled",
)


def _tool(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


TOOLS = [
    _tool("open_app", "Open a desktop application by id.",
          {"desktop_id": {"type": "string"}}, ["desktop_id"]),
    _tool("set_volume", "Set the output volume level.",
          {"level": {"type": "integer"}}, ["level"]),
    _tool("mute", "Mute the output.", {}, []),
    _tool("get_status", "Read the assistant status.", {}, []),
    _tool("get_time", "Read the current time.", {}, []),
    _tool("get_date", "Read the current date.", {}, []),
]

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


def _depth(value):
    if isinstance(value, dict):
        return 1 + max((_depth(v) for v in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_depth(v) for v in value), default=0)
    return 0


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


def _valid_input(inp):
    """Return (messages, tools, max_tokens) or None when the input is invalid."""
    if not isinstance(inp, dict) or set(inp) != INPUT_KEYS:
        return None
    messages, tools, max_tokens = inp["messages"], inp["tools"], inp["max_tokens"]
    if not isinstance(messages, list) or not 1 <= len(messages) <= MAX_MESSAGES:
        return None
    clean = []
    for message in messages:
        if not isinstance(message, dict) or set(message) != MESSAGE_KEYS:
            return None
        role, content = message["role"], message["content"]
        if role not in ROLES or not isinstance(content, str) or len(content) > MAX_CONTENT:
            return None
        clean.append({"role": role, "content": content})
    if not isinstance(tools, bool):
        return None
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
        return None
    if not 1 <= max_tokens <= MAX_TOKENS:
        return None
    return clean, tools, max_tokens


def _llm_model(msg):
    """Model chosen by the Core in the invoke envelope, or None when not configured."""
    ctx = msg.get("ctx")
    llm = ctx.get("llm") if isinstance(ctx, dict) else None
    if not isinstance(llm, dict):
        return None
    provider, model = llm.get("provider"), llm.get("model")
    if not isinstance(provider, str) or not provider:
        return None
    if not isinstance(model, str) or not 0 < len(model) <= 128:
        return None
    return model


class _Chat:
    """One invocation: SSE text in, partial events out, one final output."""

    def __init__(self, req_id):
        self.id = req_id
        self.sse = ""
        self.raw = 0
        self.text_parts = []
        self.finish = None
        self.usage = None
        self.calls = {}
        self.done = False
        self.pending = ""
        self.emitted = 0
        self.partial_closed = False
        self.last_emit = 0.0

    # -- SSE reassembly -------------------------------------------------
    def feed(self, chunk):
        self.raw += len(chunk)
        if self.raw > MAX_RAW:
            raise _Fail("response_too_large")
        parts = (self.sse + chunk).split("\n")
        self.sse = parts.pop()
        if len(self.sse) > MAX_SSE_LINE:
            raise _Fail("response_too_large")
        for line in parts:
            self._sse_line(line)

    def finish_stream(self):
        if self.sse:
            line, self.sse = self.sse, ""
            self._sse_line(line)

    def _sse_line(self, line):
        line = line.rstrip("\r")
        if self.done or not line.startswith("data:"):
            return
        payload = line[5:].lstrip(" ")
        if payload == "[DONE]":
            self.done = True
            return
        try:
            obj = json.loads(payload)
        except ValueError:
            return
        if not isinstance(obj, dict):
            return
        if "error" in obj:
            raise _Fail("http_error")
        usage = obj.get("usage")
        if isinstance(usage, dict) and _depth(usage) <= 1 and _size(usage) <= 512:
            self.usage = usage
        choices = obj.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return
        choice = choices[0]
        finish = choice.get("finish_reason")
        if isinstance(finish, str) and len(finish) <= 64:
            self.finish = finish
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            return
        content = delta.get("content")
        if isinstance(content, str) and content:
            self._text(content)
        tool_calls = delta.get("tool_calls")
        if isinstance(tool_calls, list):
            for pos, tool_call in enumerate(tool_calls):
                self._tool_delta(tool_call, pos)

    def _text(self, piece):
        self.text_parts.append(piece)
        if not self.partial_closed:
            self.pending += piece

    def _tool_delta(self, tool_call, pos):
        if not isinstance(tool_call, dict):
            return
        index = tool_call.get("index", pos)
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < MAX_TOOL_SLOTS:
            return
        slot = self.calls.get(index)
        if slot is None:
            if len(self.calls) >= MAX_TOOL_SLOTS:
                return
            slot = self.calls[index] = {"id": None, "name": None, "args": []}
        tool_id = tool_call.get("id")
        if slot["id"] is None and isinstance(tool_id, str):
            slot["id"] = tool_id
        function = tool_call.get("function")
        if not isinstance(function, dict):
            return
        name = function.get("name")
        if slot["name"] is None and isinstance(name, str):
            slot["name"] = name
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            slot["args"].append(arguments)
        elif isinstance(arguments, dict):
            slot["args"].append(json.dumps(arguments, separators=(",", ":")))

    # -- partial events (coalesced, <=20/s, <=2048 chars each) ----------
    def _partial_due(self):
        return bool(self.pending) and time.monotonic() - self.last_emit >= PARTIAL_GAP

    def _wait_timeout(self):
        if not self.pending:
            return None
        return max(0.0, PARTIAL_GAP - (time.monotonic() - self.last_emit))

    def _emit_partial(self):
        piece = self.pending[:MAX_PARTIAL]
        self.pending = self.pending[MAX_PARTIAL:]
        self.emitted += len(piece)
        self.last_emit = time.monotonic()
        _send({"event": "partial", "id": self.id, "text": piece})
        if self.emitted >= PARTIAL_TOTAL:
            self.pending = ""
            self.partial_closed = True

    # -- main loop ------------------------------------------------------
    def run(self, host_id):
        while True:
            while self._partial_due():
                self._emit_partial()
            line = _read_line(self._wait_timeout())
            if line is None:
                continue
            msg = _parse(line)
            if msg is None:
                continue
            op = msg.get("op")
            if op == "cancel":
                if msg.get("id") == self.id:
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
            if "chunk" in msg:
                chunk = msg["chunk"]
                if not isinstance(chunk, str) or len(chunk) > MAX_CHUNK:
                    raise _Fail("plugin_error")
                self.feed(chunk)
            if msg.get("done") is True:
                status = msg.get("status", 200)
                if isinstance(status, int) and not isinstance(status, bool) and status != 200:
                    raise _Fail("http_error")
                self.finish_stream()
                break
        while self.pending:
            time.sleep(self._wait_timeout() or 0.0)
            self._emit_partial()
        return self._output()

    def _output(self):
        calls, dropped = [], 0
        for index in sorted(self.calls):
            slot = self.calls[index]
            call_id = slot["id"] if slot["id"] is not None else "call_%d" % index
            name = slot["name"]
            try:
                args_text = "".join(slot["args"]).strip()
                arguments = json.loads(args_text) if args_text else {}
            except ValueError:
                arguments = None
            valid = (
                isinstance(call_id, str) and 0 < len(call_id) <= MAX_ID
                and isinstance(name, str) and 0 < len(name) <= MAX_ID
                and isinstance(arguments, dict) and _depth(arguments) <= 1
            )
            if not valid or len(calls) >= MAX_TOOL_CALLS:
                dropped += 1
                continue
            calls.append({"id": call_id, "name": name, "arguments": arguments})
        out = {"text": "".join(self.text_parts), "finish_reason": self.finish, "tool_calls": calls}
        if self.usage is not None:
            out["usage"] = self.usage
        truncated = False
        while True:
            # Flags are set before measuring so the 8 KiB bound covers the final object.
            if dropped:
                out["tool_calls_dropped"] = dropped
            if truncated:
                out["truncated"] = True
            size = _size(out)
            if size <= MAX_OUTPUT:
                return out
            over = size - MAX_OUTPUT
            if out["text"]:
                out["text"] = out["text"][: max(0, len(out["text"]) - over - 16)]
                truncated = True
            elif out["tool_calls"]:
                out["tool_calls"].pop()
                dropped += 1
            elif "usage" in out:
                del out["usage"]
            else:
                return out


def _handle_invoke(msg):
    global _host_seq
    req_id = msg.get("id")
    if not isinstance(req_id, int) or isinstance(req_id, bool):
        return
    if msg.get("capability") != CAPABILITY:
        _send({"id": req_id, "ok": False, "error": "unknown_capability"})
        return
    parsed = _valid_input(msg.get("input"))
    if parsed is None:
        _send({"id": req_id, "ok": False, "error": "invalid_input"})
        return
    messages, tools, max_tokens = parsed
    model = _llm_model(msg)
    if model is None:
        _send({"id": req_id, "ok": False, "error": "provider_not_configured"})
        return
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "stream": True}
    if tools:
        body["tools"] = TOOLS
    host_call = {
        "op": "host_call",
        "id": _host_seq + 1,
        "service": SERVICE,
        "args": {"path": PATH, "body": body, "stream": True},
    }
    if _size(body) > MAX_BODY or _size(host_call) > MAX_LINE:
        _send({"id": req_id, "ok": False, "error": "invalid_input"})
        return
    _host_seq += 1
    _send(host_call)
    try:
        output = _Chat(req_id).run(host_call["id"])
    except _Fail as fail:
        _send({"id": req_id, "ok": False, "error": fail.code})
    except _Cancel:
        _send({"id": req_id, "ok": False, "error": "cancelled"})
    else:
        _send({"id": req_id, "ok": True, "output": output})


def _handle_hello(msg):
    _send({"v": 1, "id": msg.get("id"), "ok": True, "plugin_id": msg.get("plugin_id"),
           "api": 1, "capabilities": CAPABILITIES})
    _send({"event": "log", "level": "info", "text": "llm_engine ready"})


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
