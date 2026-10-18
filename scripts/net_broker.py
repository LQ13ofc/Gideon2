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
ALLOWED_HEADERS = {"content-type", "accept", "idempotency-key"}
ALLOWED_METHODS = ("GET", "POST", "PATCH", "DELETE")
ACCOUNT_MAX = 128


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
                "allow_http", "allow_loopback"}
    if not isinstance(request, dict) or set(request) != expected:
        raise Stop("invalid_request")
    headers = request["headers"]
    if (request["method"] not in ALLOWED_METHODS or not isinstance(request["url"], str)
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
    if keyless and (ip is None or not ip.is_loopback):
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


def stream(request, key):
    parts, host, port = check_target(request, keyless=key is None)
    deadline = time.monotonic() + request["timeout_s"]
    if parts.scheme == "https":
        connection = http.client.HTTPSConnection(
            host, port, timeout=request["timeout_s"], context=ssl.create_default_context())
    else:
        connection = http.client.HTTPConnection(host, port, timeout=request["timeout_s"])
    headers = {name: value for name, value in request["headers"].items()
               if name.lower() in ALLOWED_HEADERS}
    if key is not None:
        headers["Authorization"] = "Bearer " + key
    try:
        connection.request(request["method"], parts.path or "/", body=request["body"].encode("utf-8"),
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
            if text:
                emit({"chunk": text})
        tail = decoder.decode(b"", final=True)
        if tail:
            emit({"chunk": tail})
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
