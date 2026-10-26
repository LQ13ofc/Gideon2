#!/usr/bin/env python3
"""Core-brokered HTTP for C1 (python3 stdlib only; run as `python3 -I`).

stdin, line 1: one JSON request {"url","method":"POST","headers":{..},"body":str,
"timeout_s":int,"expected_host":str,"allow_http":bool,"allow_loopback":bool}.
stdin, line 2: {"key": "..."}; the key never appears in argv, env, stdout or stderr.
The keyless form {"key": null} is for local loopback providers only: it sends no Authorization
header and only IP-literal loopback targets are accepted (no name resolution).
stdout: JSON lines only: {"chunk": str<=16384 chars}, then exactly one terminal line:
{"done":true,"status":2xx[,"account": str][,"retry_after": int]} or
{"error": code[, "status": N][, "retry_after": int][, "provider_error": snake_str]}.
Bodies of failed responses are never printed; the only body fact kept is a snake_case
"error" token of a small JSON object (provider_error). Redirects are refused, never followed.
Connections (C-S5) use GET/POST/PATCH, and DELETE for Gmail message removal (E2.2), with an Idempotency-Key header
on idempotent writes; C1 uses POST only.

WP-18b additions (the request object has exactly these keys, `auth` and `dialect` included):
- "auth": "bearer" sends `Authorization: Bearer <key>`; "x-api-key" sends `x-api-key: <key>` plus the fixed
  `anthropic-version` header (Anthropic). Keyless requests send no credential header in either case.
- "dialect": "openai" forwards the body and the SSE unchanged; "anthropic" translates the OpenAI-style body the
  Core builds into a Messages API request, and translates the Anthropic SSE back into the OpenAI chat-completions
  SSE lines that the plugin already reads (text and tool calls). Unknown events are dropped.
- Keyless (no key) non-loopback targets are allowed only for GET over https to PUBLIC_GET_HOSTS (GitHub public
  read, no token). Everything else keyless is refused, as before.
"""
import codecs
import http.client
import ipaddress
import json
import socket
import ssl
import sys
import time
from urllib.parse import urlsplit

MAX_REQUEST = 1 << 20
MAX_KEY_LINE = 4096
MAX_BODY = 512 * 1024
MAX_CHUNK = 16384
MAX_TOTAL = 4 * 1024 * 1024
MAX_ERROR_BODY = 4096
ALLOWED_HEADERS = {"content-type", "accept", "idempotency-key", "user-agent", "x-github-api-version"}
ALLOWED_METHODS = ("GET", "POST", "PATCH", "DELETE")
ACCOUNT_MAX = 128
# GitHub answers 403 without a User-Agent (verified in WP-11); the header is allowed here and forwarded.
PUBLIC_GET_HOSTS = frozenset({"api.github.com", "raw.githubusercontent.com"})
AUTH_SCHEMES = ("bearer", "x-api-key")
DIALECTS = ("openai", "anthropic")
ANTHROPIC_VERSION = "2023-06-01"
MAX_SSE_LINE = 64 * 1024
STOP_REASONS = {"end_turn": "stop", "stop_sequence": "stop", "max_tokens": "length", "tool_use": "tool_calls"}


class Stop(Exception):
    def __init__(self, code, status=None, extra=None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.extra = extra or {}


def emit(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def read_request():
    line = sys.stdin.buffer.readline(MAX_REQUEST + 1)
    key_line = sys.stdin.buffer.readline(MAX_KEY_LINE + 1)
    if not line or len(line) > MAX_REQUEST or not key_line or len(key_line) > MAX_KEY_LINE:
        raise Stop("invalid_request")
    try:
        request = json.loads(line.decode("utf-8"))
    except ValueError:
        raise Stop("invalid_request")
    expected = {"url", "method", "headers", "body", "timeout_s", "expected_host",
                "allow_http", "allow_loopback", "auth", "dialect"}
    if not isinstance(request, dict) or set(request) != expected:
        raise Stop("invalid_request")
    headers = request["headers"]
    if (request["auth"] not in AUTH_SCHEMES or request["dialect"] not in DIALECTS
            or request["method"] not in ALLOWED_METHODS or not isinstance(request["url"], str)
            or not isinstance(request["body"], str) or len(request["body"]) > MAX_BODY
            or not isinstance(request["timeout_s"], int) or not 1 <= request["timeout_s"] <= 120
            or not isinstance(request["expected_host"], str)
            or not isinstance(request["allow_http"], bool)
            or not isinstance(request["allow_loopback"], bool)
            or not isinstance(headers, dict) or len(headers) > 8
            or any(not isinstance(k, str) or not isinstance(v, str)
                   for k, v in headers.items())):
        raise Stop("invalid_request")
    try:
        secret = json.loads(key_line.decode("utf-8"))
    except ValueError:
        raise Stop("invalid_request")
    if not isinstance(secret, dict) or set(secret) != {"key"}:
        raise Stop("invalid_request")
    key = secret["key"]
    if key is None:
        return request, None
    if not isinstance(key, str) or not 8 <= len(key) <= 256 or not key.isascii() \
            or not all(33 <= ord(c) <= 126 for c in key):
        raise Stop("invalid_request")
    return request, key


def check_target(request, keyless=False):
    parts = urlsplit(request["url"])
    if parts.scheme not in ("https", "http") or parts.username or parts.password \
            or parts.query or parts.fragment or not parts.hostname:
        raise Stop("host_not_allowed")
    host = parts.hostname
    if host != request["expected_host"]:
        raise Stop("host_not_allowed")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    loopback = host == "localhost" or (ip is not None and ip.is_loopback)
    if loopback and not request["allow_loopback"]:
        raise Stop("host_not_allowed")
    if keyless and loopback and ip is None:
        # Keyless loopback targets are IP literals only: no name resolution, even for localhost.
        raise Stop("host_not_allowed")
    if keyless and not loopback and not (
            host in PUBLIC_GET_HOSTS and request["method"] == "GET" and parts.scheme == "https"):
        raise Stop("host_not_allowed")
    if ip is not None and not loopback:
        raise Stop("host_not_allowed")
    if parts.scheme == "http" and not (request["allow_http"] and loopback):
        raise Stop("host_not_allowed")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return parts, host, port


def retry_after(response):
    raw = response.getheader("Retry-After")
    if raw is None or not raw.strip().isdigit():
        return None
    return min(int(raw.strip()), 3600)


def account_of(response):
    raw = response.getheader("X-Account")
    if raw is None:
        # Home Assistant names its instance in X-Instance (docs/S5.md E2.3); same printable rule.
        raw = response.getheader("X-Instance")
    if raw is None or len(raw) > ACCOUNT_MAX or not raw.isprintable() or not raw:
        return None
    return raw


def provider_code(raw):
    try:
        body = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None
    if not isinstance(body, dict) or not isinstance(body.get("error"), str):
        return None
    code = body["error"]
    if not 1 <= len(code) <= 40 or not all(c.islower() or c == "_" for c in code):
        return None
    return code


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content
                       if isinstance(part, dict) and isinstance(part.get("text"), str))
    return ""


def anthropic_body(body):
    """OpenAI-style chat body (built by the Core) to an Anthropic Messages request body."""
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        raise Stop("invalid_request")
    system = []
    messages = []
    for message in body["messages"]:
        if not isinstance(message, dict) or not isinstance(message.get("role"), str):
            raise Stop("invalid_request")
        role = message["role"]
        content = message.get("content")
        if role == "system":
            system.append(text_of(content))
        elif role == "tool":
            messages.append({"role": "user", "content": [{
                "type": "tool_result",
                "tool_use_id": str(message.get("tool_call_id", "")),
                "content": text_of(content)}]})
        elif role == "assistant":
            blocks = []
            if text_of(content):
                blocks.append({"type": "text", "text": text_of(content)})
            for call in message.get("tool_calls") or []:
                function = call.get("function") if isinstance(call, dict) else None
                if not isinstance(function, dict):
                    raise Stop("invalid_request")
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except ValueError:
                    arguments = {}
                if not isinstance(arguments, dict):
                    arguments = {}
                blocks.append({"type": "tool_use", "id": str(call.get("id", "")),
                               "name": str(function.get("name", "")), "input": arguments})
            if blocks:
                messages.append({"role": "assistant", "content": blocks})
        elif role == "user":
            messages.append({"role": "user", "content": text_of(content)})
        else:
            raise Stop("invalid_request")
    if body.get("response_format") is not None:
        system.append("Respond with one JSON object only.")
    limit = body.get("max_tokens")
    out = {"model": body.get("model"),
           "max_tokens": limit if isinstance(limit, int) and not isinstance(limit, bool) else 1024,
           "stream": True, "messages": messages}
    if isinstance(body.get("temperature"), (int, float)) and not isinstance(body.get("temperature"), bool):
        out["temperature"] = body["temperature"]
    joined = "\n\n".join(part for part in system if part)
    if joined:
        out["system"] = joined
    tools = []
    for tool in body.get("tools") or []:
        function = tool.get("function") if isinstance(tool, dict) else None
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            tools.append({"name": function["name"],
                          "description": str(function.get("description", ""))[:4096],
                          "input_schema": function.get("parameters")
                          or {"type": "object", "properties": {}}})
    if tools:
        out["tools"] = tools
    return out


def sse_frame(obj):
    return "data: " + json.dumps(obj, separators=(",", ":")) + "\n\n"


def sse_delta(delta, finish=None):
    choice = {"index": 0, "delta": delta}
    if finish is not None:
        choice["finish_reason"] = finish
    return sse_frame({"choices": [choice]})


class Translator:
    """Anthropic Messages SSE to the OpenAI chat-completions SSE the plugin reads (text and tool calls)."""

    def __init__(self):
        self.buffer = ""
        self.blocks = {}
        self.tool_count = 0

    def feed(self, text):
        self.buffer += text
        parts = self.buffer.split("\n")
        self.buffer = parts.pop()
        if len(self.buffer) > MAX_SSE_LINE:
            raise Stop("response_too_large")
        return "".join(self.line(part) for part in parts)

    def finish(self):
        if not self.buffer:
            return ""
        line, self.buffer = self.buffer, ""
        return self.line(line)

    def line(self, text):
        text = text.rstrip("\r")
        if not text.startswith("data:"):
            return ""
        try:
            obj = json.loads(text[5:].lstrip(" "))
        except ValueError:
            return ""
        if not isinstance(obj, dict):
            return ""
        kind = obj.get("type")
        if kind == "error":
            return sse_frame({"error": "http_error"})
        if kind == "content_block_start":
            block = obj.get("content_block") or {}
            if block.get("type") != "tool_use":
                return ""
            slot = self.tool_count
            self.tool_count += 1
            self.blocks[obj.get("index")] = slot
            return sse_delta({"tool_calls": [{
                "index": slot, "id": str(block.get("id", ""))[:128], "type": "function",
                "function": {"name": str(block.get("name", ""))[:128], "arguments": ""}}]})
        if kind == "content_block_delta":
            delta = obj.get("delta") or {}
            if delta.get("type") == "text_delta" and isinstance(delta.get("text"), str):
                return sse_delta({"content": delta["text"]})
            slot = self.blocks.get(obj.get("index"))
            if delta.get("type") == "input_json_delta" and slot is not None \
                    and isinstance(delta.get("partial_json"), str):
                return sse_delta({"tool_calls": [{"index": slot,
                                                  "function": {"arguments": delta["partial_json"]}}]})
            return ""
        if kind == "message_delta":
            delta = obj.get("delta") or {}
            usage = obj.get("usage")
            out = ""
            reason = STOP_REASONS.get(delta.get("stop_reason"))
            if reason is not None:
                out += sse_delta({}, reason)
            if isinstance(usage, dict) and isinstance(usage.get("output_tokens"), int):
                out += sse_frame({"usage": {"completion_tokens": usage["output_tokens"]}})
            return out
        if kind == "message_stop":
            return "data: [DONE]\n\n"
        return ""


def emit_text(text):
    for start in range(0, len(text), MAX_CHUNK):
        emit({"chunk": text[start:start + MAX_CHUNK]})


def stream(request, key):
    parts, host, port = check_target(request, keyless=key is None)
    deadline = time.monotonic() + request["timeout_s"]
    body_text = request["body"]
    translator = None
    if request["dialect"] == "anthropic":
        try:
            body_text = json.dumps(anthropic_body(json.loads(body_text)), separators=(",", ":"))
        except ValueError:
            raise Stop("invalid_request")
        if len(body_text) > MAX_BODY:
            raise Stop("invalid_request")
        translator = Translator()
    if parts.scheme == "https":
        connection = http.client.HTTPSConnection(
            host, port, timeout=request["timeout_s"], context=ssl.create_default_context())
    else:
        connection = http.client.HTTPConnection(host, port, timeout=request["timeout_s"])
    headers = {name: value for name, value in request["headers"].items()
               if name.lower() in ALLOWED_HEADERS}
    if key is not None and request["auth"] == "x-api-key":
        headers["x-api-key"] = key
        headers["anthropic-version"] = ANTHROPIC_VERSION
    elif key is not None:
        headers["Authorization"] = "Bearer " + key
    try:
        connection.request(request["method"], parts.path or "/", body=body_text.encode("utf-8"),
                           headers=headers)
        response = connection.getresponse()
        status = response.status
        if 300 <= status < 400:
            raise Stop("redirect_refused", status)
        if not 200 <= status < 300:
            extra = {}
            wait = retry_after(response)
            if wait is not None:
                extra["retry_after"] = wait
            code = provider_code(response.read(MAX_ERROR_BODY))
            if code is not None:
                extra["provider_error"] = code
            raise Stop("http_error", status, extra)
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        total = 0
        while True:
            if time.monotonic() > deadline:
                raise Stop("timeout")
            data = response.read1(MAX_CHUNK)
            if not data:
                break
            total += len(data)
            if total > MAX_TOTAL:
                raise Stop("response_too_large")
            text = decoder.decode(data)
            emit_text(translator.feed(text) if translator is not None else text)
        tail = decoder.decode(b"", final=True)
        if translator is not None:
            tail = translator.feed(tail) + translator.finish()
        emit_text(tail)
        done = {"done": True, "status": status}
        account = account_of(response)
        if account is not None:
            done["account"] = account
        wait = retry_after(response)
        if wait is not None:
            done["retry_after"] = wait
        emit(done)
    finally:
        connection.close()


def main():
    try:
        request, key = read_request()
        stream(request, key)
    except Stop as stop:
        fail = {"error": stop.code}
        if stop.status is not None:
            fail["status"] = stop.status
        fail.update(stop.extra)
        emit(fail)
    except (socket.timeout, TimeoutError):
        emit({"error": "timeout"})
    except Exception:  # noqa: BLE001 - every other failure is one opaque code, never text
        emit({"error": "network_unavailable"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
