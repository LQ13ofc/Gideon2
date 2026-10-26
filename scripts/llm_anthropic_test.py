#!/usr/bin/env python3
"""WP-18b broker tests: Anthropic dialect, x-api-key auth, GitHub public GET policy (stdlib, run `python3 -I`).

The Anthropic cases run the real `scripts/net_broker.py` against `tests/fixtures/fake_anthropic.py` on
loopback (the same path the Core uses for a local test route). The GitHub case uses the real network
(api.github.com, public repository, no token) and is skipped only when the host has no network.
"""
import json
import os
import socket
import subprocess
import sys
import time
import unittest
from urllib.request import urlopen

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BROKER = os.path.join(ROOT, "scripts", "net_broker.py")
FAKE = os.path.join(ROOT, "tests", "fixtures", "fake_anthropic.py")
KEY = "fake-key-0123456789"

FAKE_PROCESS = None
PORT = None


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def setUpModule():
    global FAKE_PROCESS, PORT
    PORT = free_port()
    FAKE_PROCESS = subprocess.Popen([sys.executable, "-I", FAKE, "--port", str(PORT)],
                                    stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("fake Anthropic server did not start")


def tearDownModule():
    if FAKE_PROCESS is not None:
        FAKE_PROCESS.terminate()
        FAKE_PROCESS.wait(timeout=10)


def request(url, method="POST", headers=None, body="", auth="x-api-key", dialect="anthropic",
            expected_host="127.0.0.1", allow_http=True, allow_loopback=True, key=KEY):
    return {"url": url, "method": method, "headers": headers or {}, "body": body, "timeout_s": 20,
            "expected_host": expected_host, "allow_http": allow_http, "allow_loopback": allow_loopback,
            "auth": auth, "dialect": dialect}, {"key": key}


def run_broker(req, key_obj, raw=None):
    if raw is None:
        lines = json.dumps(req, separators=(",", ":")) + "\n" + json.dumps(key_obj) + "\n"
    else:
        lines = raw
    proc = subprocess.run([sys.executable, "-I", BROKER], input=lines.encode("utf-8"),
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
    out = [json.loads(line) for line in proc.stdout.decode("utf-8").splitlines() if line.strip()]
    return out


def chunks_text(lines):
    return "".join(line["chunk"] for line in lines if "chunk" in line)


def sse_objects(text):
    objects = []
    done = False
    for line in text.split("\n"):
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            done = True
            continue
        objects.append(json.loads(payload))
    return objects, done


class AnthropicDialect(unittest.TestCase):
    def messages_url(self):
        return "http://127.0.0.1:%d/v1/messages" % PORT

    def body(self, **extra):
        body = {"model": "claude-test", "stream": True, "max_tokens": 64,
                "messages": [{"role": "system", "content": "Sê breve"},
                             {"role": "user", "content": "oi"}]}
        body.update(extra)
        return json.dumps(body)

    def test_text_stream_is_translated_to_openai_sse(self):
        req, key = request(self.messages_url(), body=self.body())
        lines = run_broker(req, key)
        self.assertEqual(lines[-1], {"done": True, "status": 200})
        objects, done = sse_objects(chunks_text(lines))
        self.assertTrue(done)
        choices = [o for o in objects if "choices" in o]
        text = "".join(o["choices"][0]["delta"].get("content", "") for o in choices)
        self.assertEqual(text, "Olá sys=Sê breve|n=1")
        self.assertEqual(choices[-1]["choices"][0]["finish_reason"], "stop")
        self.assertIn({"usage": {"completion_tokens": 7}}, objects)

    def test_tool_use_becomes_openai_tool_call_deltas(self):
        tools = [{"type": "function", "function": {"name": "get_time", "description": "hora",
                                                    "parameters": {"type": "object", "properties": {}}}}]
        req, key = request(self.messages_url(), body=self.body(tools=tools))
        lines = run_broker(req, key)
        self.assertEqual(lines[-1], {"done": True, "status": 200})
        objects, _ = sse_objects(chunks_text(lines))
        choices = [o for o in objects if "choices" in o]
        names = [c for o in choices for c in o["choices"][0]["delta"].get("tool_calls", [])]
        self.assertEqual(names[0]["function"]["name"], "get_time")
        self.assertEqual(names[0]["id"], "toolu_1")
        self.assertEqual({c["index"] for c in names}, {0})
        arguments = "".join(c["function"]["arguments"] for c in names)
        self.assertEqual(json.loads(arguments), {"zone": "sala"})
        self.assertEqual(choices[-1]["choices"][0]["finish_reason"], "tool_calls")

    def test_wrong_key_is_a_provider_error_and_never_echoes_the_key(self):
        req, key = request(self.messages_url(), body=self.body(), key="fake-key-wrong-0000")
        lines = run_broker(req, key)
        self.assertEqual(lines, [{"error": "http_error", "status": 401}])
        self.assertNotIn("fake-key-wrong", json.dumps(lines))

    def test_request_shape_is_strict(self):
        req, key = request(self.messages_url(), body=self.body())
        req["auth"] = "basic"
        self.assertEqual(run_broker(req, key), [{"error": "invalid_request"}])
        req, key = request(self.messages_url(), body="[]")
        self.assertEqual(run_broker(req, key), [{"error": "invalid_request"}])

    def test_keyless_non_loopback_is_refused_except_public_get(self):
        req, key = request("https://api.anthropic.com/v1/messages", body=self.body(), key=None,
                           allow_http=False, allow_loopback=False, expected_host="api.anthropic.com")
        self.assertEqual(run_broker(req, key), [{"error": "host_not_allowed"}])
        req, key = request("https://example.com/", method="GET", key=None, auth="bearer",
                           dialect="openai", allow_http=False, allow_loopback=False,
                           expected_host="example.com")
        self.assertEqual(run_broker(req, key), [{"error": "host_not_allowed"}])
        req, key = request("https://api.github.com/repos/x/y", method="POST", key=None, auth="bearer",
                           dialect="openai", allow_http=False, allow_loopback=False,
                           expected_host="api.github.com")
        self.assertEqual(run_broker(req, key), [{"error": "host_not_allowed"}])


class GitHubPublicRead(unittest.TestCase):
    def test_public_repo_read_without_token_through_the_broker(self):
        try:
            urlopen("https://api.github.com/", timeout=10).read(1)
        except OSError:
            self.skipTest("no network to api.github.com")
        req, key = request("https://api.github.com/repos/LQ13ofc/Gideon2", method="GET",
                           headers={"Accept": "application/vnd.github+json",
                                    "User-Agent": "gideon-broker-test",
                                    "X-GitHub-Api-Version": "2022-11-28"},
                           auth="bearer", dialect="openai", expected_host="api.github.com",
                           allow_http=False, allow_loopback=False, key=None)
        lines = run_broker(req, key)
        self.assertEqual(lines[-1], {"done": True, "status": 200})
        record = json.loads(chunks_text(lines))
        self.assertEqual(record["full_name"], "LQ13ofc/Gideon2")
        self.assertFalse(record["private"])

    def test_github_without_user_agent_is_refused_by_github(self):
        try:
            urlopen("https://api.github.com/", timeout=10).read(1)
        except OSError:
            self.skipTest("no network to api.github.com")
        req, key = request("https://api.github.com/repos/LQ13ofc/Gideon2", method="GET",
                           headers={"Accept": "application/vnd.github+json"}, auth="bearer",
                           dialect="openai", expected_host="api.github.com", allow_http=False,
                           allow_loopback=False, key=None)
        self.assertEqual(run_broker(req, key), [{"error": "http_error", "status": 403}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
