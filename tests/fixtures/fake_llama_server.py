#!/usr/bin/env python3
"""fake_llama_server: loopback imitation of llama.cpp's OpenAI-compatible server (stdlib only).

Binds 127.0.0.1 only. Usage:
  fake_llama_server.py [--port N] [--text-only] [--no-stream]
--port 0 (default) picks a random port; the first stdout line is that port.
Endpoints: GET /health ({"status":"ok"}), GET /props, GET /v1/models, POST /v1/chat/completions
(also accepted without the /v1 prefix), GET /__log (loopback only), POST /__reset (loopback only).
  --text-only  ignores the request's `tools` and never emits tool_calls.
  --no-stream  answers every chat request with one non-streaming JSON body (no SSE frames).
Scenario = content of the LAST user message, by prefix (no prefix means echo):
  echo:<text>  echo the rest      tool:get_time  one get_time tool call (text-only: plain text)
  slow:        long stream (about 10 s, cancel test)
  e401: e429: e500: e503:  provider error with status N; the body never carries request data
  "Call the get_time tool."  the selftest tool probe (get_time call in full mode)
Every record in /__log keeps method, path, body, scenario, the header NAMES and
authorization_received (bool); it never stores the Authorization value.
"""
import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOOPBACK = ("127.0.0.1",)
MODEL_ID = "gguf-local"
SECRET_BODY = "SECRET_PROVIDER_BODY"
TOOL_PROBE = "Call the get_time tool."
DELTA = 4
ERROR_STATUS = {"e401:": 401, "e429:": 429, "e500:": 500, "e503:": 503}


class ClientGone(Exception):
    pass


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.log = []

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.log))

    def reset(self):
        with self.lock:
            self.log.clear()


STATE = State()
TEXT_ONLY = False
NO_STREAM = False


def scenario_of(content):
    """(scenario, rest) for the last user message."""
    if content == TOOL_PROBE:
        return "tool_probe", ""
    for prefix, status in ERROR_STATUS.items():
        if content.startswith(prefix):
            return "error", str(status)
    for prefix, scenario in (("echo:", "echo"), ("tool:get_time", "tool_get_time"),
                             ("slow:", "slow")):
        if content.startswith(prefix):
            return scenario, content[len(prefix):]
    return "echo", content


def write(handler, data):
    try:
        handler.wfile.write(data)
        handler.wfile.flush()
    except OSError as exc:
        raise ClientGone() from exc


def sse(obj):
    return ("data: " + json.dumps(obj) + "\n\n").encode("utf-8")


def chunk(model, delta, finish=None, usage=None):
    obj = {"id": "chatcmpl-llama", "object": "chat.completion.chunk", "created": 0,
           "model": model, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    if usage is not None:
        obj["usage"] = usage
    return obj


def stream_text(handler, model, text):
    for start in range(0, len(text), DELTA):
        write(handler, sse(chunk(model, {"content": text[start:start + DELTA]})))


def finish(handler, model, reason, usage=None):
    write(handler, sse(chunk(model, {}, reason, usage)))
    write(handler, b"data: [DONE]\n\n")


def stream_get_time(handler, model):
    first = {"index": 0, "id": "call_1", "type": "function",
             "function": {"name": "get_time", "arguments": ""}}
    write(handler, sse(chunk(model, {"tool_calls": [first]})))
    args = json.dumps({})
    for start in range(0, len(args), 5):
        piece = {"index": 0, "function": {"arguments": args[start:start + 5]}}
        write(handler, sse(chunk(model, {"tool_calls": [piece]})))
    finish(handler, model, "tool_calls")


def sc_echo(handler, model, rest, prompt_chars):
    stream_text(handler, model, rest)
    usage = {"prompt_tokens": prompt_chars, "completion_tokens": len(rest),
             "total_tokens": prompt_chars + len(rest)}
    finish(handler, model, "stop", usage)


def sc_tool_get_time(handler, model, tools):
    if TEXT_ONLY or not tools:
        stream_text(handler, model, "This model cannot call tools.")
        finish(handler, model, "stop")
        return
    stream_get_time(handler, model)


def sc_slow(handler, model):
    for i in range(50):
        write(handler, sse(chunk(model, {"content": "tick%d " % i})))
        time.sleep(0.2)
    finish(handler, model, "stop")


def sc_error(handler, status):
    body = json.dumps({"error": {"message": SECRET_BODY + " upstream rejected the request",
                                 "code": status}}).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    write(handler, body)


def no_stream_body(model):
    return {"id": "chatcmpl-llama", "object": "chat.completion", "created": 0, "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"},
                         "finish_reason": "stop"}]}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "fake-llama"
    sys_version = ""

    def log_message(self, format, *args):  # never write request data to stderr
        return

    def _json(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _loopback(self):
        return self.client_address[0] in LOOPBACK

    def do_GET(self):
        if self.path == "/__log":
            if not self._loopback():
                self._json(403, {"error": "loopback only"})
                return
            self._json(200, {"requests": STATE.snapshot()})
        elif self.path == "/health":
            self._json(200, {"status": "ok"})
        elif self.path == "/props":
            self._json(200, {"default_generation_settings": {"n_ctx": 4096},
                             "total_slots": 1, "model_path": MODEL_ID + ".gguf",
                             "build_info": "fake-llama"})
        elif self.path.endswith("/models"):
            self._json(200, {"object": "list", "data": [
                {"id": MODEL_ID, "object": "model", "owned_by": "llamacpp"}]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/__reset":
            if not self._loopback():
                self._json(403, {"error": "loopback only"})
                return
            STATE.reset()
            self._json(200, {"ok": True})
        elif self.path.endswith("/chat/completions"):
            self._chat()
        else:
            self._json(404, {"error": "not found"})

    def _chat(self):
        length = min(int(self.headers.get("Content-Length") or 0), 8 * 1024 * 1024)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        messages = body.get("messages")
        content = ""
        for message in reversed(messages if isinstance(messages, list) else []):
            if isinstance(message, dict) and message.get("role") == "user":
                content = message.get("content") if isinstance(message.get("content"), str) else ""
                break
        scenario, rest = scenario_of(content)
        names = sorted(self.headers.keys(), key=str.lower)
        entry = {"method": "POST", "path": self.path, "header_names": [n.lower() for n in names],
                 "authorization_received": self.headers.get("Authorization") is not None,
                 "body": body, "scenario": scenario, "disconnected": False}
        with STATE.lock:
            STATE.log.append(entry)
        model = body.get("model") if isinstance(body.get("model"), str) else MODEL_ID
        tools = bool(body.get("tools"))
        try:
            if scenario == "error":
                sc_error(self, int(rest))
            elif NO_STREAM:
                self._json(200, no_stream_body(model))
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                if scenario == "echo":
                    sc_echo(self, model, rest, len(content))
                elif scenario == "tool_get_time":
                    sc_tool_get_time(self, model, tools)
                elif scenario == "tool_probe":
                    sc_tool_get_time(self, model, tools)
                elif scenario == "slow":
                    sc_slow(self, model)
        except ClientGone:
            entry["disconnected"] = True


def main():
    global TEXT_ONLY, NO_STREAM
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--text-only", action="store_true")
    parser.add_argument("--no-stream", action="store_true")
    args = parser.parse_args()
    TEXT_ONLY = args.text_only
    NO_STREAM = args.no_stream
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    print(server.server_address[1], flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
