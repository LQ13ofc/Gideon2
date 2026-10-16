#!/usr/bin/env python3
"""C0 fixture tests (stdlib unittest).

Spawns the fixture plugins with `/usr/bin/python3 -I` over pipes, WITHOUT any
sandbox, and checks the JSON-lines protocol. Adversarial probes that touch the
network, filesystem, processes or memory are NOT run here: they are exercised only
by the Rust sandbox tests. Also validates tests/fixtures/hub-c0.json.
"""
import hashlib
import json
import os
import re
import select
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
CATALOG = FIXTURES / "hub-c0.json"
HUB = FIXTURES / "hub.json"
ECHO = FIXTURES / "dummy_echo.py"
EVIL = FIXTURES / "dummy_evil.py"
PYTHON = "/usr/bin/python3"
# Clean environment: no HOME, XDG or session variables reach the plugins.
CLEAN_ENV = {"PATH": "/usr/bin:/bin"}
REPO = "https://github.com/LQ13ofc/Gideon2"
CAPABILITY_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
RESERVED = ("base.", "core.", "system.", "safety.", "llm.", "screen.", "computer.",
            "audio.", "mic.", "camera.", "display.")
FIXTURE_BIN_SHA = "496d47696e6691915fbe6b1f7c34c52671552d7dcad27112dd24f99e20378514"


class Plugin:
    """One plugin process with a line reader on stdout (select-based timeouts)."""

    def __init__(self, script, *args):
        self.proc = subprocess.Popen(
            [PYTHON, "-I", str(script), *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=CLEAN_ENV,
            cwd="/",
        )
        self._buf = b""

    def send(self, obj):
        self.send_raw((json.dumps(obj) + "\n").encode("utf-8"))

    def send_raw(self, data):
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def line(self, timeout=5.0):
        fd = self.proc.stdout.fileno()
        deadline = time.monotonic() + timeout
        while b"\n" not in self._buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("no plugin line within timeout")
            readable, _, _ = select.select([fd], [], [], remaining)
            if not readable:
                raise TimeoutError("no plugin line within timeout")
            chunk = os.read(fd, 65536)
            if not chunk:
                raise EOFError("plugin closed stdout")
            self._buf += chunk
        raw, self._buf = self._buf.split(b"\n", 1)
        return raw

    def msg(self, timeout=5.0):
        return json.loads(self.line(timeout))

    def hello(self, plugin_id, req_id=1):
        self.send({"v": 1, "id": req_id, "op": "hello", "plugin_id": plugin_id})
        return self.msg()

    def invoke(self, req_id, capability, inp, deadline_ms=2000):
        self.send({"v": 1, "id": req_id, "op": "invoke", "capability": capability,
                   "input": inp, "deadline_ms": deadline_ms})

    def close(self):
        if self.proc.poll() is None:
            try:
                self.send({"v": 1, "id": 0, "op": "shutdown"})
            except OSError:
                pass
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        for stream in (self.proc.stdin, self.proc.stdout):
            try:
                stream.close()
            except OSError:
                pass


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class DummyEchoTest(unittest.TestCase):
    def setUp(self):
        self.plugin = Plugin(ECHO)

    def tearDown(self):
        self.plugin.close()

    def test_hello_reply_and_ready_log(self):
        reply = self.plugin.hello("dummy_echo", req_id=7)
        self.assertEqual(reply, {"v": 1, "id": 7, "ok": True, "plugin_id": "dummy_echo",
                                 "api": 1, "capabilities": ["dummy_echo.echo"]})
        self.assertEqual(self.plugin.msg(),
                         {"event": "log", "level": "info", "text": "dummy ready"})

    def test_invoke_uppercases_and_counts(self):
        self.plugin.hello("dummy_echo")
        self.plugin.msg()  # ready log
        self.plugin.invoke(2, "dummy_echo.echo", {"text": "hello gideon"})
        self.assertEqual(self.plugin.msg(),
                         {"id": 2, "ok": True,
                          "output": {"text": "HELLO GIDEON", "count": 1}})
        self.plugin.invoke(3, "dummy_echo.echo", {"text": "again"})
        self.assertEqual(self.plugin.msg(),
                         {"id": 3, "ok": True, "output": {"text": "AGAIN", "count": 2}})

    def test_invalid_input_rejected_and_not_counted(self):
        self.plugin.hello("dummy_echo")
        self.plugin.msg()
        bad_inputs = [
            {},
            {"text": 5},
            {"text": "x" * 257},
            {"text": "ok", "sleep_ms": 5001},
            {"text": "ok", "sleep_ms": -1},
            {"text": "ok", "sleep_ms": True},
            {"text": "ok", "extra": 1},
            "not an object",
        ]
        for index, inp in enumerate(bad_inputs, start=10):
            self.plugin.invoke(index, "dummy_echo.echo", inp)
            self.assertEqual(self.plugin.msg(),
                             {"id": index, "ok": False, "error": "invalid_input"})
        self.plugin.invoke(99, "dummy_echo.echo", {"text": "valid"})
        self.assertEqual(self.plugin.msg()["output"]["count"], 1)

    def test_unknown_capability(self):
        self.plugin.hello("dummy_echo")
        self.plugin.msg()
        self.plugin.invoke(4, "dummy_echo.nope", {"text": "x"})
        self.assertEqual(self.plugin.msg(),
                         {"id": 4, "ok": False, "error": "unknown_capability"})

    def test_sleep_completes_without_cancel(self):
        self.plugin.hello("dummy_echo")
        self.plugin.msg()
        self.plugin.invoke(5, "dummy_echo.echo", {"text": "slow", "sleep_ms": 100})
        self.assertEqual(self.plugin.msg(timeout=3),
                         {"id": 5, "ok": True, "output": {"text": "SLOW", "count": 1}})

    def test_cancel_during_sleep(self):
        self.plugin.hello("dummy_echo")
        self.plugin.msg()
        self.plugin.invoke(6, "dummy_echo.echo", {"text": "slow", "sleep_ms": 5000})
        time.sleep(0.2)
        self.plugin.send({"v": 1, "id": 6, "op": "cancel"})
        started = time.monotonic()
        reply = self.plugin.msg(timeout=3)
        elapsed = time.monotonic() - started
        self.assertEqual(reply, {"id": 6, "ok": False, "error": "cancelled"})
        self.assertLess(elapsed, 2.0, "cancel must cut the 5 s sleep short")

    def test_shutdown_exits_zero(self):
        self.plugin.hello("dummy_echo")
        self.plugin.msg()
        self.plugin.send({"v": 1, "id": 8, "op": "shutdown"})
        self.assertEqual(self.plugin.proc.wait(timeout=5), 0)


class DummyEvilBenignProbeTest(unittest.TestCase):
    """Only protocol-level behaviour that is safe without a sandbox."""

    def _spawn(self, mode=None):
        args = [mode] if mode else []
        plugin = Plugin(EVIL, *args)
        self.addCleanup(plugin.close)
        reply = plugin.hello("dummy_evil")
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["capabilities"], ["dummy_evil.probe"])
        return plugin

    def test_bad_json_line(self):
        plugin = self._spawn("bad_json")
        plugin.invoke(1, "dummy_evil.probe", {"probe": "env"})
        raw = plugin.line()
        with self.assertRaises(ValueError):
            json.loads(raw)

    def test_oversize_line(self):
        plugin = self._spawn("oversize")
        plugin.invoke(1, "dummy_evil.probe", {"probe": "env"})
        raw = plugin.line(timeout=5)
        self.assertGreaterEqual(len(raw), 100000)
        self.assertGreater(len(raw), 65536)

    def test_dup_id_replies_twice(self):
        plugin = self._spawn("dup_id")
        plugin.invoke(3, "dummy_evil.probe", {"probe": "env"})
        first = plugin.msg()
        second = plugin.msg()
        self.assertEqual(first["id"], 3)
        self.assertEqual(second["id"], 3)
        self.assertEqual(first, second)

    def test_crash_exit_code_3(self):
        plugin = self._spawn("crash")
        plugin.invoke(1, "dummy_evil.probe", {"probe": "env"})
        with self.assertRaises(EOFError):
            plugin.line(timeout=5)
        self.assertEqual(plugin.proc.wait(timeout=5), 3)

    def test_log_flood_counts_200_events(self):
        plugin = self._spawn("log_flood")
        plugin.invoke(1, "dummy_evil.probe", {"probe": "env"})
        events = 0
        while True:
            message = plugin.msg(timeout=5)
            if message.get("event") == "log":
                events += 1
                continue
            break
        self.assertEqual(events, 200)
        self.assertEqual(message["id"], 1)
        self.assertTrue(message["ok"])

    def test_env_probe_with_clean_environment_is_denied(self):
        plugin = self._spawn()
        plugin.invoke(1, "dummy_evil.probe", {"probe": "env"})
        reply = plugin.msg()
        self.assertEqual(reply["id"], 1)
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["output"]["result"], "denied")
        self.assertIn("detail", reply["output"])

    def test_unknown_probe_is_invalid_input(self):
        plugin = self._spawn()
        plugin.invoke(2, "dummy_evil.probe", {"probe": "not_a_probe"})
        self.assertEqual(plugin.msg(), {"id": 2, "ok": False, "error": "invalid_input"})

    @unittest.skip("network/read_home/read_repo/write_root/exec/fork_bomb_limited/mem/"
                   "cpu_spin must NOT run unsandboxed; exercised by the Rust sandbox tests")
    def test_adversarial_probes_skipped_outside_sandbox(self):
        pass


class CatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.hub = json.loads(HUB.read_text(encoding="utf-8"))
        cls.plugins = {p["plugin_id"]: p for p in cls.catalog["plugins"]}

    def test_top_level_shape(self):
        self.assertEqual(set(self.catalog), {"version", "repository", "plugins"})
        self.assertEqual(self.catalog["version"], 1)
        self.assertEqual(self.catalog["repository"], REPO)
        self.assertEqual(self.catalog["repository"], self.hub["repository"])
        self.assertLessEqual(len(self.catalog["plugins"]), 8)
        self.assertEqual(set(self.plugins),
                         {"dummy_echo", "dummy_evil", "plain_opaque"})

    def test_manifest_fields_match_hub_schema(self):
        base_keys = set(self.hub["plugins"][0])
        optional = {"runtime", "capabilities"}
        for plugin_id, plugin in self.plugins.items():
            keys = set(plugin)
            self.assertLessEqual(keys, base_keys | optional, plugin_id)
            self.assertTrue(base_keys <= keys, plugin_id)
            for binary in plugin["binaries"]:
                self.assertEqual(set(binary), {"target", "url", "sha256", "size"})

    def test_ids_and_capabilities_follow_c0_rules(self):
        id_re = re.compile(r"^[A-Za-z0-9_-]+$")
        for plugin_id, plugin in self.plugins.items():
            self.assertRegex(plugin_id, id_re)
            self.assertFalse(plugin_id.startswith(RESERVED), plugin_id)
            self.assertEqual(plugin["semver"], "1.0.0")
            self.assertEqual(plugin["api_version"], 1)
            caps = plugin.get("capabilities", [])
            self.assertLessEqual(len(caps), 8)
            for cap in caps:
                self.assertLessEqual(len(cap), 64)
                self.assertRegex(cap, CAPABILITY_RE)
                self.assertTrue(cap.startswith(plugin_id + "."), cap)
                self.assertFalse(cap.startswith(RESERVED), cap)

    def test_runtime_declared_only_for_dummies(self):
        for plugin_id in ("dummy_echo", "dummy_evil"):
            self.assertEqual(self.plugins[plugin_id]["runtime"], "python3_script")
        self.assertEqual(self.plugins["dummy_echo"]["capabilities"], ["dummy_echo.echo"])
        self.assertEqual(self.plugins["dummy_evil"]["capabilities"], ["dummy_evil.probe"])
        self.assertNotIn("runtime", self.plugins["plain_opaque"])
        self.assertNotIn("capabilities", self.plugins["plain_opaque"])

    def test_dummy_payload_digests_and_sizes(self):
        for plugin_id, path in (("dummy_echo", ECHO), ("dummy_evil", EVIL)):
            plugin = self.plugins[plugin_id]
            binary = plugin["binaries"][0]
            self.assertEqual(binary["target"], "linux_x86_64")
            self.assertEqual(binary["sha256"], sha256_file(path), plugin_id)
            self.assertEqual(binary["size"], path.stat().st_size, plugin_id)
            self.assertTrue(1 <= binary["size"] <= 67108864)
            self.assertRegex(binary["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(binary["url"].startswith(REPO + "/releases/download/"))
            self.assertEqual(plugin["entrypoint"], "bin/" + path.name)

    def test_plain_opaque_uses_fixture_binary(self):
        binary = self.plugins["plain_opaque"]["binaries"][0]
        self.assertEqual(binary["sha256"], FIXTURE_BIN_SHA)
        self.assertEqual(binary["size"], 15)
        hub_entry = next(p for p in self.hub["plugins"] if p["plugin_id"] == "benign_fixture")
        self.assertEqual(hub_entry["binaries"][0]["sha256"], FIXTURE_BIN_SHA)

    def test_urls_are_github_release_urls(self):
        for plugin in self.plugins.values():
            for binary in plugin["binaries"]:
                self.assertTrue(binary["url"].startswith("https://github.com/"))
            self.assertTrue(plugin["build_source"].startswith("https://github.com/"))
            self.assertNotIn("..", plugin["build_source"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
