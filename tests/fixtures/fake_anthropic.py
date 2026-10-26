#!/usr/bin/env python3
"""Loopback fake of the Anthropic Messages API for the WP-18b broker tests (stdlib only).

`--port N` serves POST /v1/messages on 127.0.0.1. The key must arrive as `x-api-key` with the fixed
`anthropic-version`, or the fake answers 401 with Anthropic's error shape. A request that carries
`tools` gets one text block and one tool_use block; any other request gets a text answer that echoes
what the fake received (system text and message count), so tests can check the translation.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEY = "fake-key-0123456789"


def sse(event, data):
    return "event: %s\ndata: %s\n\n" % (event, json.dumps(data, separators=(",", ":")))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep stderr quiet
        return

    def _json(self, status, obj):
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if self.path != "/v1/messages":
            self._json(404, {"type": "error", "error": {"type": "not_found_error"}})
            return
        if self.headers.get("x-api-key") != KEY or self.headers.get("anthropic-version") != "2023-06-01" \
                or self.headers.get("Authorization") is not None:
            self._json(401, {"type": "error", "error": {"type": "authentication_error"}})
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
        frames = [sse("message_start", {"type": "message_start", "message": {"id": "msg_fake"}})]
        index = 0
        if body.get("tools"):
            frames.append(sse("content_block_start", {"type": "content_block_start", "index": 0,
                                                      "content_block": {"type": "text", "text": ""}}))
            frames.append(sse("content_block_delta", {"type": "content_block_delta", "index": 0,
                                                      "delta": {"type": "text_delta", "text": "vou medir"}}))
            frames.append(sse("content_block_stop", {"type": "content_block_stop", "index": 0}))
            index = 1
            frames.append(sse("content_block_start", {"type": "content_block_start", "index": index,
                                                      "content_block": {"type": "tool_use", "id": "toolu_1",
                                                                        "name": body["tools"][0]["name"],
                                                                        "input": {}}}))
            frames.append(sse("content_block_delta", {"type": "content_block_delta", "index": index,
                                                      "delta": {"type": "input_json_delta",
                                                                "partial_json": "{\"zone\":"}}))
            frames.append(sse("content_block_delta", {"type": "content_block_delta", "index": index,
                                                      "delta": {"type": "input_json_delta",
                                                                "partial_json": "\"sala\"}"}}))
            frames.append(sse("content_block_stop", {"type": "content_block_stop", "index": index}))
            stop = "tool_use"
        else:
            echo = "sys=%s|n=%d" % (body.get("system", ""), len(body.get("messages", [])))
            for piece in ("Olá ", echo):
                frames.append(sse("content_block_delta", {"type": "content_block_delta", "index": 0,
                                                          "delta": {"type": "text_delta", "text": piece}}))
            stop = "end_turn"
        frames.append(sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop},
                                            "usage": {"output_tokens": 7}}))
        frames.append(sse("message_stop", {"type": "message_stop"}))
        raw = "".join(frames).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main():
    port = int(sys.argv[sys.argv.index("--port") + 1])
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
