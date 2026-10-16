#!/usr/bin/env python3
"""C2 fixture tests: llm_engine 1.1.0 (models capability, require, fallback). stdlib unittest.

Runs tests/fixtures/llm_engine.py against loopback fakes only:
  fake_llm_server.py    cloud-shaped OpenAI-compatible provider (needs a key and consent)
  fake_llama_server.py  llama.cpp-shaped local server (full, --text-only, --no-stream)
A host simulator plays the Core: llm.http host_calls go to the fakes over real HTTP (the
simulator adds Authorization only for cloud routes), settings.get / settings.put are served
from an in-memory store with the Core's limits (<= 8 KiB, depth <= 4), faults are injected per
target ("primary" / "fallback"). No real network, no real keys.
"""
import codecs
import hashlib
import http.client
import importlib.util
import json
import queue
import random
import secrets
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
PLUGIN = FIXTURES / "llm_engine.py"
CLOUD_SERVER = FIXTURES / "fake_llm_server.py"
LLAMA_SERVER = FIXTURES / "fake_llama_server.py"
CATALOG = FIXTURES / "hub-c1.json"
MODELS_SRC = FIXTURES / "llm_models.json"
PYTHON = sys.executable
CLEAN_ENV = {"PATH": "/usr/bin:/bin"}
CAP = "llm_engine.chat"
CAP_MODELS = "llm_engine.models"
PLUGIN_ID = "llm_engine"
MAX_OUTPUT = 8192
MAX_SETTINGS = 8192
GOOGLE_MODEL = "gemini-3.5-flash-lite"
GOOGLE_CTX = {"llm": {"provider": "google", "model": GOOGLE_MODEL}}
LOCAL_CTX = {"llm": {"provider": "local", "model": "gguf-local"}}
TEXT_CTX = {"llm": {"provider": "custom", "model": "text-only-3b"}}
FAKE_KEY = "sk-fake-" + secrets.token_hex(16)  # random fake string; only the cloud fake sees it
RECOMMENDED_IDS = ("google-gemini-3.5-flash-lite", "mistral-ministral-3b-latest",
                   "openrouter-llama-3.2-3b-instruct", "opencode-gpt-5.4-nano",
                   "local-llamacpp-gguf", "local-ollama-llama3.2-3b")
_ids = iter(range(10, 100_000))


def next_id():
    return next(_ids)


def _size(obj):
    return len(json.dumps(obj, separators=(",", ":")))


def _depth(value):
    if isinstance(value, dict):
        return 1 + max((_depth(v) for v in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_depth(v) for v in value), default=0)
    return 0


def spawn(script, *args):
    return subprocess.Popen([PYTHON, "-I", str(script), *args], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=CLEAN_ENV, cwd="/")


class FakeServer:
    """A fake provider process (cloud or llama-shaped) on a random loopback port."""

    def __init__(self, script, *args):
        self.name = script.name + " " + " ".join(args)
        self.proc = spawn(script, "--port", "0", *args)
        self.port = int(self.proc.stdout.readline())

    def request(self, method, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path)
            return json.loads(conn.getresponse().read())
        finally:
            conn.close()

    def log(self):
        return self.request("GET", "/__log")["requests"]

    def reset(self):
        self.request("POST", "/__reset")

    def close(self):
        self.proc.terminate()
        self.proc.wait(timeout=5)
        for pipe in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            pipe.close()


class Plugin:
    def __init__(self):
        self.proc = spawn(PLUGIN)
        self.queue = queue.Queue()
        self.transcript = []
        self.lock = threading.Lock()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for raw in iter(self.proc.stdout.readline, b""):
            self.transcript.append(raw)
            try:
                obj = json.loads(raw)
            except ValueError:
                obj = {"_raw": raw.decode("utf-8", "replace")}
            self.queue.put(obj)
        self.queue.put(None)

    def write(self, obj):
        with self.lock:
            self.proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
            self.proc.stdin.flush()

    def get(self, timeout):
        item = self.queue.get(timeout=timeout)
        if item is None:
            raise EOFError("plugin closed stdout")
        return item

    def hello(self):
        self.write({"v": 1, "id": next_id(), "op": "hello", "plugin_id": PLUGIN_ID})
        while True:
            item = self.get(10)
            if item.get("event") == "log":
                continue
            return item

    def close(self):
        try:
            self.write({"op": "shutdown"})
        except OSError:
            pass
        code = self.proc.wait(timeout=5)
        stderr = self.proc.stderr.read()
        for pipe in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            pipe.close()
        return code, stderr


class Route:
    """Where a host_call target goes: a fake server, whether it is cloud, consent and key."""

    def __init__(self, server, cloud=False, consent=True, key=None):
        self.server = server
        self.cloud = cloud
        self.consent = consent
        self.key = key


class HostSim:
    """Plays the Core for llm.http, settings.get and settings.put."""

    def __init__(self, plugin):
        self.plugin = plugin
        self.routes = {}
        self.faults = {}  # target -> (error code, status or None)
        self.store = None  # the settings data object the Core keeps (None = never written)
        self.settings_fault = None  # "get" | "put" | None
        self.settings_denied = False
        self.calls = []
        self.violations = []
        self.cancel = threading.Event()
        self.rng = random.Random(5)

    def llm_calls(self):
        return [c for c in self.calls if c["service"] == "llm.http"]

    def settings_calls(self):
        return [c for c in self.calls if c["service"].startswith("settings.")]

    def _reply(self, hid, **fields):
        # The Core's host_reply envelope (src/plugins.rs): v, op, id, then done/data, chunk or error.
        self.plugin.write(dict({"v": 1, "op": "host_reply", "id": hid}, **fields))

    def handle(self, msg):
        self.calls.append(msg)
        if msg.get("op") != "host_call":
            self.violations.append(msg)
        service = msg.get("service")
        if service in ("settings.get", "settings.put"):
            self._settings(msg)
        elif service == "llm.http":
            self._llm(msg)
        else:
            self.violations.append(msg)
            self._reply(msg["id"], error="permission_denied")

    def _settings(self, msg):
        hid, args = msg["id"], msg.get("args")
        if self.settings_denied:
            self._reply(hid, error="permission_denied")
            return
        if msg["service"] == "settings.get":
            if args != {}:
                self.violations.append(msg)
            if self.settings_fault == "legacy":  # a retired reply shape (chunk + done): refused
                self._reply(hid, chunk=json.dumps({"data": self.store}))
                self._reply(hid, done=True, status=200)
                return
            if args != {} or self.settings_fault == "get":
                self._reply(hid, error="plugin_error")
                return
            # Core: data is the stored object itself, null when never written.
            self._reply(hid, done=True, data=self.store)
            return
        data = args.get("data") if isinstance(args, dict) and set(args) == {"data"} else None
        if (not isinstance(data, dict) or _size(data) > MAX_SETTINGS or _depth(data) > 4
                or self.settings_fault == "put"):
            if not isinstance(data, dict) or _size(data) > MAX_SETTINGS:
                self.violations.append(msg)
            self._reply(hid, error="plugin_error")
            return
        self.store = json.loads(json.dumps(data))
        self._reply(hid, done=True, data=None)  # Core: settings.put replies data null

    def _llm(self, msg):
        hid, args = msg["id"], msg.get("args")
        if not isinstance(args, dict):
            args = {}
        target = args.get("target", "primary")
        allowed = {"path", "body", "stream", "target"}
        if (set(args) - allowed or args.get("path") != "/chat/completions"
                or args.get("stream") is not True or not isinstance(args.get("body"), dict)
                or ("target" in args and args["target"] != "fallback")):
            self.violations.append(msg)
            self._reply(hid, error="permission_denied")
            return
        if target in self.faults:
            code, status = self.faults[target]
            fields = {"error": code}
            if status is not None:
                fields["status"] = status
            self._reply(hid, **fields)
            return
        route_name = "fallback" if args.get("target") == "fallback" else "primary"
        route = self.routes.get(route_name)
        if route is None:
            self._reply(hid, error="provider_not_configured")
            return
        if route.cloud and not route.consent:
            self._reply(hid, error="cloud_not_authorized")
            return
        if route.cloud and route.key is None:
            self._reply(hid, error="key_missing")
            return
        self._http(hid, route, args["body"])

    def _http(self, hid, route, body):
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if route.cloud:
            headers["Authorization"] = "Bearer " + route.key
        conn = http.client.HTTPConnection("127.0.0.1", route.server.port, timeout=20)
        try:
            conn.request("POST", "/chat/completions", body=json.dumps(body).encode("utf-8"),
                         headers=headers)
            resp = conn.getresponse()
            if resp.status != 200:
                resp.read(65536)  # the provider body never reaches the plugin
                self._reply(hid, error="http_error", status=resp.status)
                return
            self._stream(hid, resp)
        except socket.timeout:
            self._reply(hid, error="timeout")
        except (OSError, http.client.HTTPException):
            if not self.cancel.is_set():
                self._reply(hid, error="network_unavailable")
        finally:
            conn.close()

    def _stream(self, hid, resp):
        decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
        buf = bytearray()
        while not self.cancel.is_set():
            data = resp.read1(4096)
            if not data:
                break
            buf.extend(data)
            while buf:
                size = self.rng.randint(1, 4096)
                piece = bytes(buf[:size])
                del buf[:size]
                text = decoder.decode(piece)
                if text:
                    self._reply(hid, chunk=text)
        tail = decoder.decode(b"", final=True)
        if tail:
            self._reply(hid, chunk=tail)
        self._reply(hid, done=True, status=200)


class Result:
    def __init__(self, reply, partials):
        self.reply = reply
        self.partials = partials


def invoke(plugin, sim, capability, inp, ctx=None, timeout=60):
    inv_id = next_id()
    envelope = {"v": 1, "id": inv_id, "op": "invoke", "capability": capability,
                "input": inp, "deadline_ms": 60000}
    if ctx is not None:
        envelope["ctx"] = ctx
    plugin.write(envelope)
    partials = []
    deadline = time.monotonic() + timeout
    while True:
        item = plugin.get(max(0.1, deadline - time.monotonic()))
        if item.get("op") == "host_call":
            sim.handle(item)
        elif item.get("event") == "partial":
            partials.append(item["text"])
        elif item.get("event") == "log":
            continue
        elif item.get("id") == inv_id:
            return Result(item, partials)
        else:
            raise AssertionError("unexpected plugin line: %r" % item)


def chat(plugin, sim, content="hello", ctx=LOCAL_CTX, tools=False, max_tokens=64, **extra):
    inp = {"messages": [{"role": "user", "content": content}], "tools": tools,
           "max_tokens": max_tokens}
    inp.update(extra)
    return invoke(plugin, sim, CAP, inp, ctx=ctx)


def models(plugin, sim, inp, ctx=None):
    return invoke(plugin, sim, CAP_MODELS, inp, ctx=ctx)


def custom(model_id="custom-01", **overrides):
    """A valid user-declared custom Model (local llama.cpp by default)."""
    model = {
        "id": model_id, "label": "My local model", "kind": "local", "provider": "local",
        "model": "gguf-local", "custom_url": None, "tier": "custom", "license": "user supplied",
        "quantization": None, "sha256": None, "backend": "llama.cpp",
        "features": {"streaming": "unknown", "tool_use": "unknown", "vision": "unknown",
                     "cancel": "unknown", "context_tokens": None},
        "certification": {"state": "declared", "evidence": None, "date": None},
        "cost": {"input_per_mtok": None, "output_per_mtok": None, "currency": None},
        "latency_hint": "unknown", "min_hardware": {"ram_gb": None, "gpu": "unknown"},
        "offline": True,
    }
    model.update(overrides)
    if "local_port" not in overrides:  # local providers need a loopback port, the others none
        model["local_port"] = 8080 if model["provider"] in ("local", "ollama") else None
    return model


def with_path(model, path, value):
    """Copy of `model` with one nested field replaced (path is a tuple of keys)."""
    copy = json.loads(json.dumps(model))
    node = copy
    for key in path[:-1]:
        node = node[key]
    if value == "__delete__":
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return copy


class C2Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plugin = Plugin()
        cls.hello = cls.plugin.hello()
        cls.cloud = FakeServer(CLOUD_SERVER)
        cls.llama = FakeServer(LLAMA_SERVER)
        cls.llama_text = FakeServer(LLAMA_SERVER, "--text-only")
        cls.llama_nostream = FakeServer(LLAMA_SERVER, "--no-stream")

    @classmethod
    def tearDownClass(cls):
        code, stderr = cls.plugin.close()
        for server in (cls.cloud, cls.llama, cls.llama_text, cls.llama_nostream):
            server.close()
        assert code == 0, "plugin exit code %r" % code
        assert stderr == b"", "plugin wrote to stderr"
        transcript = b"".join(cls.plugin.transcript)
        assert FAKE_KEY.encode() not in transcript, "API key reached the plugin"

    def setUp(self):
        for server in (self.cloud, self.llama, self.llama_text, self.llama_nostream):
            server.reset()
        self.sim = HostSim(self.plugin)
        self.sim.routes["primary"] = Route(self.llama)
        self.sim.routes["fallback"] = Route(self.llama_text)

    def ok(self, result):
        self.assertTrue(result.reply.get("ok"), result.reply)
        return result.reply["output"]

    def err(self, result, code):
        self.assertEqual(result.reply, {"id": result.reply["id"], "ok": False, "error": code})

    def list_page(self, tab, offset=0, limit=6, ctx=None):
        inp = {"action": "list", "tab": tab, "offset": offset, "limit": limit}
        return models(self.plugin, self.sim, inp, ctx=ctx)

    def list_out(self, tab="recommended", offset=0, limit=6, ctx=None):
        return self.ok(self.list_page(tab, offset, limit, ctx))

    def all_pages(self, tab, ctx=None, limit=6):
        """Pages through one tab until total is reached: (items in order, page outputs).
        An empty page before total ends the walk, so the caller's assertions fail."""
        items, pages, offset = [], [], 0
        while True:
            out = self.list_out(tab, offset, limit, ctx)
            pages.append(out)
            items += out["items"]
            offset += len(out["items"])
            if offset >= out["total"] or not out["items"]:
                return items, pages

    def save(self, model):
        return models(self.plugin, self.sim, {"action": "save_custom", "model": model})

    def use_cloud(self, consent=True):
        self.sim.routes["primary"] = Route(self.cloud, cloud=True, consent=consent, key=FAKE_KEY)


class CatalogAndManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.plugin = cls.catalog["plugins"][0]
        cls.source = json.loads(MODELS_SRC.read_text(encoding="utf-8"))["models"]
        spec = importlib.util.spec_from_file_location("llm_engine_fixture", PLUGIN)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_manifest_declares_1_1_0_models_capability_and_permissions(self):
        self.assertEqual(self.plugin["semver"], "1.1.0")
        self.assertEqual(self.plugin["capabilities"], [CAP, CAP_MODELS])
        self.assertEqual(self.plugin["permissions"], ["network_llm", "storage_settings"])
        payload = PLUGIN.read_bytes()
        binary = self.plugin["binaries"][0]
        self.assertEqual(binary["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(binary["size"], len(payload))

    def test_embedded_catalog_equals_source_json(self):
        self.assertEqual(self.module.RECOMMENDED, self.source)
        self.assertEqual([m["id"] for m in self.source], list(RECOMMENDED_IDS))

    def test_only_cloud_google_or_custom_entries_are_certified(self):
        certified = [m for m in self.source if m["certification"]["state"] == "certified"]
        self.assertEqual(sorted(m["id"] for m in certified),
                         ["google-gemini-3.5-flash-lite", "mistral-ministral-3b-latest"])
        for model in certified:
            self.assertIn(model["provider"], ("google", "custom"))
            self.assertEqual(model["kind"], "cloud")
            self.assertEqual(model["features"]["streaming"], "supported")
            self.assertEqual(model["features"]["tool_use"], "supported")
            self.assertEqual(model["features"]["vision"], "unknown")
            self.assertIn("docs/evidence/c1-llm.json", model["certification"]["evidence"])
            self.assertIn("tests: cancel closes provider connection",
                          model["certification"]["evidence"])
            self.assertEqual(model["certification"]["date"], "2026-10-16")
            self.assertTrue((ROOT / "docs/evidence/c1-llm.json").is_file())

    def test_local_and_unverified_providers_never_certified(self):
        for model in self.source:
            if model["provider"] in ("local", "ollama", "openrouter", "opencode"):
                self.assertEqual(model["certification"], {"state": "candidate", "evidence": None,
                                                          "date": None}, model["id"])
                self.assertTrue(all(model["features"][k] == "unknown"
                                    for k in ("streaming", "tool_use", "vision", "cancel")),
                                model["id"])

    def test_llama_cpp_candidate_fields(self):
        llama = next(m for m in self.source if m["backend"] == "llama.cpp")
        self.assertEqual((llama["kind"], llama["provider"]), ("local", "local"))
        self.assertEqual(llama["quantization"], "Q4_K_M")
        self.assertIsNone(llama["sha256"])
        self.assertEqual(llama["min_hardware"], {"ram_gb": 8, "gpu": "optional"})
        self.assertTrue(llama["offline"])

    def test_local_ports_are_declared_defaults_only_for_local_providers(self):
        ports = {m["id"]: m["local_port"] for m in self.source}
        self.assertEqual(ports["local-llamacpp-gguf"], 8080)
        self.assertEqual(ports["local-ollama-llama3.2-3b"], 11434)
        for model in self.source:
            if model["provider"] not in ("local", "ollama"):
                self.assertIsNone(model["local_port"], model["id"])

    def test_costs_are_null_because_none_is_verified(self):
        for model in self.source:
            self.assertEqual(model["cost"], {"input_per_mtok": None, "output_per_mtok": None,
                                             "currency": None}, model["id"])

    def test_plugin_source_has_no_authorization_or_key_material(self):
        text = PLUGIN.read_text(encoding="utf-8")
        self.assertNotIn('"Authorization"', text)
        self.assertNotIn("'Authorization'", text)
        self.assertNotIn("Bearer ", text)
        self.assertNotIn("sk-live", text)
        self.assertNotIn("api_key=", text)
        catalog_text = MODELS_SRC.read_text(encoding="utf-8")
        self.assertNotIn("sk-", catalog_text)


class ModelsCapabilityTest(C2Base):
    def test_hello_lists_both_capabilities(self):
        self.assertEqual(self.hello["capabilities"], [CAP, CAP_MODELS])

    def test_list_pages_recommended_with_hardware_and_no_storage_read(self):
        out = self.list_out()
        self.assertEqual(set(out), {"tab", "items", "total", "offset", "selected", "hardware"})
        self.assertEqual((out["tab"], out["total"], out["offset"]), ("recommended", 6, 0))
        self.assertEqual([m["id"] for m in out["items"]], list(RECOMMENDED_IDS))
        self.assertEqual(len(RECOMMENDED_IDS), 6)
        self.assertIsNone(out["selected"])
        self.assertEqual(set(out["hardware"]), {"cpu_cores", "ram_gb", "gpu"})
        self.assertEqual(out["hardware"]["gpu"], "unknown")
        cores, ram = out["hardware"]["cpu_cores"], out["hardware"]["ram_gb"]
        self.assertTrue(cores is None or (isinstance(cores, int) and cores >= 1))
        self.assertTrue(ram is None or (isinstance(ram, float) and ram > 0))
        self.assertEqual(self.sim.calls, [])  # the recommended catalog is embedded
        self.assertEqual(self.sim.llm_calls(), [])

    def test_custom_tab_reads_storage_and_is_empty_at_first(self):
        out = self.list_out("custom")
        self.assertEqual((out["tab"], out["items"], out["total"]), ("custom", [], 0))
        self.assertEqual([c["service"] for c in self.sim.calls], ["settings.get"])

    def test_list_reports_selected_from_context(self):
        out = self.list_out(ctx=LOCAL_CTX)
        self.assertEqual(out["selected"], {"provider": "local", "model": "gguf-local"})

    def test_list_pages_are_slices_in_order_with_offset_and_total(self):
        self.ok(self.save(custom("a")))
        self.ok(self.save(custom("b")))
        self.ok(self.save(custom("c")))
        out = self.list_out("custom", offset=1, limit=1)
        self.assertEqual((out["offset"], out["total"], [m["id"] for m in out["items"]]),
                         (1, 3, ["b"]))
        out = self.list_out("recommended", offset=4, limit=6)
        self.assertEqual([m["id"] for m in out["items"]], list(RECOMMENDED_IDS)[4:])
        past = self.list_out("custom", offset=99, limit=6)
        self.assertEqual((past["items"], past["total"], past["offset"]), ([], 3, 99))

    def test_all_sixteen_customs_are_reachable_through_paging(self):
        for i in range(16):
            saved = self.ok(self.save(custom("custom-%02d" % i, label="Custom %02d" % i)))
            self.assertEqual(saved["custom_count"], i + 1)
        items, pages = self.all_pages("custom")
        self.assertEqual([m["id"] for m in items], ["custom-%02d" % i for i in range(16)])
        self.assertEqual({p["total"] for p in pages}, {16})
        self.assertTrue(all(len(p["items"]) <= 6 for p in pages))
        self.assertEqual(len(self.sim.store["customs"]), 16)  # storage keeps all of them

    def test_page_is_cut_to_fit_8k_and_next_page_starts_where_it_stopped(self):
        # A custom URL of 200 UTF-8 bytes made of emoji escapes to ~570 bytes, so six such Models
        # with full keys overflow 8 KiB: the first page stops early and the next starts there.
        url = "https://e.io/" + "\U0001F600" * 46
        for i in range(6):
            self.ok(self.save(custom("heavy-%d" % i, kind="cloud", provider="custom",
                                     model="m-%d" % i, custom_url=url,
                                     label="\U0001F600" * 12, license="\U0001F600" * 16)))
        result = self.list_page("custom", 0, 6)
        out = self.ok(result)
        self.assertLessEqual(_size(result.reply["output"]), MAX_OUTPUT)
        self.assertTrue(0 < len(out["items"]) < 6, len(out["items"]))
        items, pages = self.all_pages("custom")
        self.assertEqual([m["id"] for m in items], ["heavy-%d" % i for i in range(6)])
        self.assertTrue(all(_size(p) <= MAX_OUTPUT for p in pages))
        self.assertGreater(len(pages), 1)

    def test_describe_recommended_and_custom_and_unknown(self):
        out = self.ok(models(self.plugin, self.sim, {"action": "describe",
                                                     "id": "google-gemini-3.5-flash-lite"}))
        self.assertEqual(out["model"]["certification"]["state"], "certified")
        self.ok(self.save(custom("mine")))
        out = self.ok(models(self.plugin, self.sim, {"action": "describe", "id": "mine"}))
        self.assertEqual(out["model"]["certification"]["state"], "declared")
        self.err(models(self.plugin, self.sim, {"action": "describe", "id": "nope"}),
                 "model_not_found")

    def test_save_custom_persists_through_settings_store(self):
        self.ok(self.save(custom("mine")))
        self.assertEqual(len(self.sim.store["customs"]), 1)
        self.assertEqual(self.sim.store["customs"][0][0], "mine")
        self.assertEqual(set(self.sim.store), {"customs"})
        out = self.list_out("custom")
        self.assertEqual([m["id"] for m in out["items"]], ["mine"])
        self.assertEqual(out["items"][0]["certification"],
                         {"state": "declared", "evidence": None, "date": None})
        self.assertEqual(out["items"][0]["tier"], "custom")

    def test_customs_survive_a_new_plugin_process(self):
        self.ok(self.save(custom("mine")))
        stored = json.loads(json.dumps(self.sim.store))
        other = Plugin()
        other.hello()
        sim = HostSim(other)
        sim.store = stored
        try:
            out = self.ok(models(other, sim, {"action": "list", "tab": "custom", "offset": 0,
                                              "limit": 6}))
            self.assertEqual([m["id"] for m in out["items"]], ["mine"])
        finally:
            other.close()

    def test_delete_custom_removes_and_unknown_is_not_found(self):
        self.ok(self.save(custom("a")))
        self.ok(self.save(custom("b")))
        out = self.ok(models(self.plugin, self.sim, {"action": "delete_custom", "id": "a"}))
        self.assertEqual(out, {"deleted": "a", "custom_count": 1})
        self.assertEqual([m["id"] for m in self.list_out("custom")["items"]], ["b"])
        self.err(models(self.plugin, self.sim, {"action": "delete_custom", "id": "a"}),
                 "model_not_found")
        self.err(models(self.plugin, self.sim, {"action": "delete_custom",
                                                "id": "google-gemini-3.5-flash-lite"}),
                 "model_not_found")

    def test_seventeenth_custom_is_rejected_and_store_unchanged(self):
        for i in range(16):
            self.ok(self.save(custom("c%02d" % i)))
        before = json.loads(json.dumps(self.sim.store))
        self.err(self.save(custom("c16")), "invalid_input")
        self.assertEqual(self.sim.store, before)
        self.assertEqual(len(self.sim.store["customs"]), 16)

    def test_duplicate_custom_id_rejected(self):
        self.ok(self.save(custom("dup")))
        self.err(self.save(custom("dup", label="Other")), "invalid_input")
        self.assertEqual(len(self.sim.store["customs"]), 1)

    def test_custom_id_cannot_shadow_recommended(self):
        self.err(self.save(custom("google-gemini-3.5-flash-lite")), "invalid_input")
        self.assertIsNone(self.sim.store)

    def test_strict_validation_rejects_every_bad_field(self):
        base = custom()
        bad = {
            "unknown kind": with_path(base, ("kind",), "remote"),
            "cloud kind with local provider": custom(kind="cloud", provider="local",
                                                     model="m", custom_url=None),
            "local kind with cloud provider": custom(kind="local", provider="google"),
            "tier recommended": with_path(base, ("tier",), "recommended"),
            "custom provider http url": custom(kind="cloud", provider="custom",
                                               custom_url="http://api.example.com/v1"),
            "custom provider userinfo": custom(kind="cloud", provider="custom",
                                               custom_url="https://user:pw@example.com/v1"),
            "custom provider query": custom(kind="cloud", provider="custom",
                                            custom_url="https://example.com/v1?key=abc"),
            "custom provider without url": custom(kind="cloud", provider="custom"),
            "url on openrouter": custom(kind="cloud", provider="openrouter",
                                        custom_url="https://openrouter.ai/api/v1"),
            "claims certified": with_path(base, ("certification",),
                                          {"state": "certified", "evidence": "x",
                                           "date": "2026-10-16"}),
            "declared with evidence": with_path(base, ("certification",),
                                                {"state": "declared", "evidence": "x",
                                                 "date": None}),
            "feature state word": with_path(base, ("features", "tool_use"), "yes"),
            "context tokens zero": with_path(base, ("features", "context_tokens"), 0),
            "context tokens bool": with_path(base, ("features", "context_tokens"), True),
            "bad latency": with_path(base, ("latency_hint",), "fast"),
            "ram too big": with_path(base, ("min_hardware", "ram_gb"), 5000),
            "ram bool": with_path(base, ("min_hardware", "ram_gb"), True),
            "bad gpu": with_path(base, ("min_hardware", "gpu"), "cuda"),
            "currency EUR": with_path(base, ("cost", "currency"), "EUR"),
            "price without USD": with_path(base, ("cost", "input_per_mtok"), 1.5),
            "negative price": with_path(base, ("cost", "input_per_mtok"), -1),
            "sha not hex": with_path(base, ("sha256",), "ABC"),
            "quantization too long": with_path(base, ("quantization",), "q" * 33),
            "label too long": with_path(base, ("label",), "L" * 49),
            "label control char": with_path(base, ("label",), "a\nb"),
            "id uppercase": with_path(base, ("id",), "BadID"),
            "model with spaces": with_path(base, ("model",), "gguf local"),
            "model too long": with_path(base, ("model",), "m" * 97),
            "license too long": with_path(base, ("license",), "x" * 65),
            "backend with spaces": with_path(base, ("backend",), "llama cpp"),
            "offline not bool": with_path(base, ("offline",), "yes"),
            "missing key": with_path(base, ("offline",), "__delete__"),
            "extra key": dict(base, name="x"),
            "secret-looking label": with_path(base, ("label",), "sk-abc123456789xyz"),
            "api key in license": with_path(base, ("license",), "uses my api_key here"),
            "bearer in backend": with_path(base, ("backend",), "bearer"),
            "local_port missing": with_path(base, ("local_port",), "__delete__"),
            "local port below 1024": with_path(base, ("local_port",), 80),
            "local port above 65535": with_path(base, ("local_port",), 70000),
            "local port as bool": with_path(base, ("local_port",), True),
            "local port as float": with_path(base, ("local_port",), 8080.0),
            "local kind without port": with_path(base, ("local_port",), None),
            "cloud custom with port": custom(kind="cloud", provider="custom",
                                             custom_url="https://example.com/v1", local_port=8080),
            "openrouter with port": custom(kind="cloud", provider="openrouter", local_port=11434),
        }
        for label, model in bad.items():
            with self.subTest(case=label):
                self.err(self.save(model), "invalid_input")
        self.assertIsNone(self.sim.store)
        self.assertEqual(self.sim.llm_calls(), [])

    def test_models_input_is_strict_and_bounded(self):
        page = {"action": "list", "tab": "custom", "offset": 0, "limit": 6}
        cases = [
            {"action": "nuke"},
            {"action": "list"},  # paging keys are required
            dict(page, extra=1),
            dict(page, tab="all"),
            dict(page, tab=None),
            dict(page, offset=-1),
            dict(page, offset=True),
            dict(page, offset=1.0),
            dict(page, offset="0"),
            dict(page, limit=0),
            dict(page, limit=7),
            dict(page, limit=True),
            dict(page, limit=6.0),
            dict(page, limit="6"),
            {"action": "list", "tab": "custom", "offset": 0},
            {"action": 5},
            {"action": "describe"},
            {"action": "delete_custom"},
            {"action": "describe", "id": "google-gemini-3.5-flash-lite", "pad": "y" * 9000},
            [],
        ]
        for inp in cases:
            with self.subTest(inp=str(inp)[:40]):
                self.err(models(self.plugin, self.sim, inp), "invalid_input")
        self.assertEqual(self.sim.calls, [])

    def test_settings_failures_map_to_settings_unavailable(self):
        self.sim.settings_fault = "get"
        self.err(models(self.plugin, self.sim, {"action": "list", "tab": "custom", "offset": 0, "limit": 6}), "settings_unavailable")
        self.sim.settings_fault = "put"
        self.err(self.save(custom("mine")), "settings_unavailable")
        self.assertIsNone(self.sim.store)

    def test_settings_reply_must_be_the_core_shape(self):
        self.sim.settings_fault = "legacy"
        self.err(models(self.plugin, self.sim, {"action": "list", "tab": "custom", "offset": 0, "limit": 6}), "settings_unavailable")
        self.err(chat(self.plugin, self.sim, ctx=GOOGLE_CTX, require=["tools"]),
                 "settings_unavailable")
        self.assertEqual(self.sim.llm_calls(), [])

    def test_settings_permission_denied_passes_through(self):
        self.sim.settings_denied = True
        self.err(models(self.plugin, self.sim, {"action": "list", "tab": "custom", "offset": 0, "limit": 6}), "permission_denied")

    def test_corrupt_storage_fails_closed(self):
        bad_probe = {"features": {"streaming": "supported", "tool_use": "supported",
                                  "vision": "unknown", "cancel": "unknown",
                                  "context_tokens": None},
                     "latency_ms": 5, "at": 1, "source": "probed"}
        for stored in ({"customs": [["bad"]]}, {"customs": "x"}, {"other": 1},
                       {"customs": [["x"] * 23] * 1}, {"customs": [], "probes": []},
                       {"customs": [], "probes": {"local|gguf-local": bad_probe}},
                       {"customs": [], "probes": {"local|gguf-local|8080": dict(bad_probe, at=0)}},
                       {"customs": [], "probes": {"local|gguf-local|8080": dict(bad_probe,
                                                                             source="declared")}},
                       {"customs": [], "probes": {"a|b|1": dict(bad_probe, latency_ms=-1)}},
                       {"customs": [], "probes": {"a|b|1": dict(bad_probe, features={
                           "streaming": "supported", "tool_use": "supported",
                           "vision": "supported", "cancel": "unknown",
                           "context_tokens": None})}}):
            with self.subTest(stored=str(stored)[:40]):
                self.sim.store = stored
                self.err(models(self.plugin, self.sim, {"action": "list", "tab": "custom", "offset": 0, "limit": 6}),
                         "settings_unavailable")

    def test_sixteen_max_length_customs_fit_the_storage_budget(self):
        for i in range(16):
            self.ok(self.save(custom("c%02d" % i, label="L" * 48, license="x" * 64,
                                     model="m" * 96, backend="b" * 32)))
        self.assertLessEqual(_size({"customs": self.sim.store["customs"]}), MAX_SETTINGS)

    def test_selftest_local_reports_streaming_and_tool_use(self):
        result = models(self.plugin, self.sim, {"action": "selftest"}, ctx=LOCAL_CTX)
        out = self.ok(result)
        self.assertEqual(out["features"], {"streaming": "supported", "tool_use": "supported",
                                           "vision": "unknown", "cancel": "unknown",
                                           "context_tokens": None})
        self.assertEqual(out["source"], "probed")
        self.assertIs(out["ok"], True)
        self.assertGreaterEqual(out["latency_ms"], 0)
        # The result is persisted as a probe under the matched entry's provider|model|port.
        self.assertEqual([c["service"] for c in self.sim.settings_calls()],
                         ["settings.get", "settings.put"])
        probe = self.sim.store["probes"]["local|gguf-local|8080"]
        self.assertEqual(probe["features"], out["features"])
        self.assertEqual((probe["source"], probe["at"]), ("probed", 1))
        self.assertEqual(set(self.sim.store), {"customs", "probes"})
        log = self.llama.log()
        self.assertEqual(len(log), 2)
        self.assertTrue(all(entry["authorization_received"] is False for entry in log))
        self.assertLessEqual(_size(out), MAX_OUTPUT)

    def test_selftest_text_only_reports_tool_use_unsupported(self):
        self.sim.routes["primary"] = Route(self.llama_text)
        out = self.ok(models(self.plugin, self.sim, {"action": "selftest"}, ctx=LOCAL_CTX))
        self.assertEqual(out["features"]["tool_use"], "unsupported")
        self.assertEqual(out["features"]["streaming"], "supported")
        probe = self.llama_text.log()[-1]["body"]
        self.assertIn("tools", probe)  # the probe asked for tools; the text-only server ignored them

    def test_probed_tool_unsupported_is_the_effective_matrix_and_blocks_require(self):
        self.sim.routes["primary"] = Route(self.llama_text)
        self.ok(models(self.plugin, self.sim, {"action": "selftest"}, ctx=LOCAL_CTX))
        out = self.ok(models(self.plugin, self.sim, {"action": "features"}, ctx=LOCAL_CTX))
        self.assertEqual(out["source"], "probed")
        self.assertEqual(out["features"]["tool_use"], "unsupported")
        self.assertEqual(out["features"]["streaming"], "supported")
        self.assertEqual(out["features"]["vision"], "unknown")  # a probe never determines vision
        sent = len(self.llama_text.log())
        self.sim.calls.clear()
        self.err(chat(self.plugin, self.sim, ctx=LOCAL_CTX, tools=True, require=["tools"]),
                 "model_unsupported_feature")
        self.assertEqual(self.sim.llm_calls(), [])  # refused before any llm.http host_call
        self.assertEqual([c["service"] for c in self.sim.calls], ["settings.get"])
        self.assertEqual(len(self.llama_text.log()), sent)

    def test_probe_is_keyed_by_provider_model_and_port(self):
        self.ok(models(self.plugin, self.sim, {"action": "selftest"}, ctx=LOCAL_CTX))
        other = {"llm": {"provider": "local", "model": "other-gguf"}}
        out = self.ok(models(self.plugin, self.sim, {"action": "features"}, ctx=other))
        self.assertEqual(out["source"], "unknown")
        self.assertEqual(out["features"]["tool_use"], "unknown")
        out = self.ok(models(self.plugin, self.sim, {"action": "features"}, ctx=LOCAL_CTX))
        self.assertEqual(out["source"], "probed")

    def test_probes_are_evicted_oldest_first_and_capped_at_32(self):
        probe = {"features": {"streaming": "supported", "tool_use": "supported",
                              "vision": "unknown", "cancel": "unknown", "context_tokens": None},
                 "latency_ms": 1, "source": "probed"}
        self.sim.store = {"customs": [], "probes": {
            "a|m%d|1" % i: dict(probe, at=i + 1) for i in range(32)}}
        self.ok(models(self.plugin, self.sim, {"action": "selftest"}, ctx=LOCAL_CTX))
        probes = self.sim.store["probes"]
        self.assertEqual(len(probes), 32)
        self.assertNotIn("a|m0|1", probes)  # oldest (at 1) evicted
        self.assertEqual(probes["local|gguf-local|8080"]["at"], 33)
        self.assertLessEqual(_size(self.sim.store), MAX_SETTINGS)

    def test_size_pressure_evicts_probes_and_never_customs(self):
        for i in range(15):
            self.ok(self.save(custom("c%02d" % i, label="L" * 48, license="x" * 64,
                                     model="m" * 96, backend="b" * 32)))
        probe = {"features": {"streaming": "supported", "tool_use": "supported",
                              "vision": "unknown", "cancel": "unknown", "context_tokens": None},
                 "latency_ms": 1, "source": "probed"}
        self.sim.store = dict(self.sim.store, probes={
            "p|%s|1" % ("m" * 90 + "%02d" % i): dict(probe, at=i + 1) for i in range(20)})
        customs_before = json.loads(json.dumps(self.sim.store["customs"]))
        self.ok(self.save(custom("late", label="L" * 48, license="x" * 64, model="m" * 96,
                                 backend="b" * 32)))  # 16th custom: probes must give way
        self.assertEqual(self.sim.store["customs"][:15], customs_before)
        self.assertEqual(len(self.sim.store["customs"]), 16)
        self.assertLessEqual(_size(self.sim.store), MAX_SETTINGS)
        self.assertNotIn("p|" + "m" * 90 + "00|1", self.sim.store.get("probes", {}))

    def test_selftest_without_stream_fails_with_model_selftest_failed(self):
        self.sim.routes["primary"] = Route(self.llama_nostream)
        self.err(models(self.plugin, self.sim, {"action": "selftest"}, ctx=LOCAL_CTX),
                 "model_selftest_failed")
        self.assertIsNone(self.sim.store)  # a failed probe stores nothing

    def test_selftest_provider_error_fails_with_model_selftest_failed(self):
        self.sim.faults["primary"] = ("http_error", 503)
        self.err(models(self.plugin, self.sim, {"action": "selftest"}, ctx=LOCAL_CTX),
                 "model_selftest_failed")
        self.assertEqual(self.llama.log(), [])

    def test_selftest_without_context_makes_no_host_call(self):
        self.err(models(self.plugin, self.sim, {"action": "selftest"}),
                 "provider_not_configured")
        self.assertEqual(self.sim.calls, [])

    def test_features_sources_certified_declared_unknown(self):
        out = self.ok(models(self.plugin, self.sim, {"action": "features"}, ctx=GOOGLE_CTX))
        self.assertEqual(out["source"], "certified")
        self.assertEqual(out["features"]["tool_use"], "supported")
        # features reads the stored probes too (a probe overrides the certified matrix)
        self.assertEqual([c["service"] for c in self.sim.settings_calls()], ["settings.get"])
        self.ok(self.save(custom("text-only-3b", kind="cloud", provider="custom",
                                 model="text-only-3b", custom_url="https://example.com/v1",
                                 features={"streaming": "supported", "tool_use": "unsupported",
                                           "vision": "unknown", "cancel": "unknown",
                                           "context_tokens": None})))
        out = self.ok(models(self.plugin, self.sim, {"action": "features"}, ctx=TEXT_CTX))
        self.assertEqual(out["source"], "declared")
        self.assertEqual(out["features"]["tool_use"], "unsupported")
        out = self.ok(models(self.plugin, self.sim, {"action": "features"},
                             ctx={"llm": {"provider": "local", "model": "nope"}}))
        self.assertEqual(out["source"], "unknown")
        self.assertEqual(out["features"]["streaming"], "unknown")
        out = self.ok(models(self.plugin, self.sim, {"action": "features"}))
        self.assertEqual(out, {"selected": None, "source": "unknown",
                               "features": {"streaming": "unknown", "tool_use": "unknown",
                                            "vision": "unknown", "cancel": "unknown",
                                            "context_tokens": None}})


class ChatRequireAndFallbackTest(C2Base):
    def test_require_tools_on_text_only_model_is_unavailable_with_zero_llm_requests(self):
        self.ok(self.save(custom("text-only-3b", kind="cloud", provider="custom",
                                 model="text-only-3b", custom_url="https://example.com/v1",
                                 features={"streaming": "supported", "tool_use": "unsupported",
                                           "vision": "unknown", "cancel": "unknown",
                                           "context_tokens": None})))
        self.sim.calls.clear()
        self.err(chat(self.plugin, self.sim, ctx=TEXT_CTX, tools=True,
                      require=["tools"]), "model_unsupported_feature")
        self.assertEqual(self.sim.llm_calls(), [])
        self.assertEqual(self.llama.log() + self.llama_text.log() + self.cloud.log(), [])

    def test_require_supported_or_unknown_features_proceed(self):
        self.use_cloud()
        out = self.ok(chat(self.plugin, self.sim, ctx=GOOGLE_CTX, require=["streaming", "tools"]))
        self.assertEqual(out["text"], "hello")
        self.assertIs(out["used_fallback"], False)
        out = self.ok(chat(self.plugin, self.sim, ctx=GOOGLE_CTX, require=["vision"]))
        self.assertEqual(out["text"], "hello")

    def test_invalid_require_and_fallback_values_are_rejected_before_any_call(self):
        cases = [
            {"require": ["audio"]}, {"require": "tools"}, {"require": ["tools", "tools"]},
            {"require": ["tools", "vision", "streaming", "tools"]}, {"fallback": "yes"},
            {"require": [["tools"]]},
        ]
        for extra in cases:
            with self.subTest(extra=extra):
                self.err(chat(self.plugin, self.sim, **extra), "invalid_input")
        self.assertEqual(self.sim.calls, [])

    def test_chat_without_require_makes_no_storage_read(self):
        self.ok(chat(self.plugin, self.sim, ctx=LOCAL_CTX))
        self.assertEqual(self.sim.settings_calls(), [])
        self.assertEqual([c["service"] for c in self.sim.calls], ["llm.http"])

    def test_fallback_used_once_after_primary_503(self):
        self.sim.faults["primary"] = ("http_error", 503)
        out = self.ok(chat(self.plugin, self.sim, content="hi there", ctx=LOCAL_CTX,
                           fallback=True))
        self.assertIs(out["used_fallback"], True)
        self.assertEqual(out["text"], "hi there")
        calls = self.sim.llm_calls()
        self.assertEqual(len(calls), 2)
        self.assertNotIn("target", calls[0]["args"])
        self.assertEqual(calls[1]["args"]["target"], "fallback")
        self.assertEqual(len(self.llama_text.log()), 1)
        self.assertEqual(self.llama.log(), [])

    def test_no_fallback_without_flag(self):
        self.sim.faults["primary"] = ("http_error", 503)
        self.err(chat(self.plugin, self.sim, ctx=LOCAL_CTX), "http_error")
        self.assertEqual(len(self.sim.llm_calls()), 1)

    def test_auth_and_payment_errors_never_fall_back(self):
        for status in (401, 402, 403):
            with self.subTest(status=status):
                self.sim.calls.clear()
                self.sim.faults["primary"] = ("http_error", status)
                self.err(chat(self.plugin, self.sim, ctx=LOCAL_CTX, fallback=True), "http_error")
                self.assertEqual(len(self.sim.llm_calls()), 1)
                self.sim.faults.clear()

    def test_key_and_consent_errors_never_fall_back(self):
        self.sim.routes["primary"] = Route(self.cloud, cloud=True, consent=False, key=FAKE_KEY)
        self.err(chat(self.plugin, self.sim, ctx=GOOGLE_CTX, fallback=True),
                 "cloud_not_authorized")
        self.assertEqual(len(self.sim.llm_calls()), 1)
        self.assertEqual(self.cloud.log(), [])
        self.sim.calls.clear()
        self.sim.routes["primary"] = Route(self.cloud, cloud=True, consent=True, key=None)
        self.err(chat(self.plugin, self.sim, ctx=GOOGLE_CTX, fallback=True), "key_missing")
        self.assertEqual(len(self.sim.llm_calls()), 1)

    def test_recoverable_http_statuses_fall_back(self):
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status):
                self.sim.calls.clear()
                self.sim.faults["primary"] = ("http_error", status)
                out = self.ok(chat(self.plugin, self.sim, content="ok?", ctx=LOCAL_CTX,
                                   fallback=True))
                self.assertIs(out["used_fallback"], True)
                self.assertEqual(len(self.sim.llm_calls()), 2)
                self.sim.faults.clear()

    def test_network_and_timeout_errors_fall_back(self):
        for code in ("network_unavailable", "timeout"):
            with self.subTest(code=code):
                self.sim.calls.clear()
                self.sim.faults["primary"] = (code, None)
                out = self.ok(chat(self.plugin, self.sim, content="ok?", ctx=LOCAL_CTX,
                                   fallback=True))
                self.assertIs(out["used_fallback"], True)
                self.sim.faults.clear()

    def test_fallback_also_failing_returns_fallback_error(self):
        self.sim.faults["primary"] = ("http_error", 503)
        self.sim.faults["fallback"] = ("http_error", 502)
        self.err(chat(self.plugin, self.sim, ctx=LOCAL_CTX, fallback=True), "http_error")
        self.assertEqual(len(self.sim.llm_calls()), 2)

    def test_fallback_failing_on_real_server_returns_error_after_two_requests(self):
        self.sim.routes["primary"] = Route(self.llama)
        self.sim.routes["fallback"] = Route(self.llama)
        self.err(chat(self.plugin, self.sim, content="e503:both down", ctx=LOCAL_CTX,
                      fallback=True), "http_error")
        self.assertEqual(len(self.llama.log()), 2)

    def test_fallback_cloud_without_consent_sends_nothing(self):
        self.sim.faults["primary"] = ("http_error", 503)
        self.sim.routes["fallback"] = Route(self.cloud, cloud=True, consent=False, key=FAKE_KEY)
        self.err(chat(self.plugin, self.sim, ctx=LOCAL_CTX, fallback=True),
                 "cloud_not_authorized")
        self.assertEqual(self.cloud.log(), [])

    def test_local_fallback_never_sends_authorization(self):
        self.sim.faults["primary"] = ("http_error", 503)
        self.ok(chat(self.plugin, self.sim, ctx=LOCAL_CTX, fallback=True))
        log = self.llama_text.log()
        self.assertEqual(len(log), 1)
        self.assertIs(log[0]["authorization_received"], False)

    def test_cloud_primary_key_reaches_only_the_provider(self):
        self.use_cloud()
        out = self.ok(chat(self.plugin, self.sim, content="hello cloud", ctx=GOOGLE_CTX))
        self.assertEqual(out["text"], "hello cloud")
        log = self.cloud.log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["headers"].get("authorization"), "Bearer " + FAKE_KEY)
        self.assertEqual(self.llama.log(), [])
        self.assertNotIn(FAKE_KEY, json.dumps(self.sim.calls))

    def test_plugin_host_calls_never_carry_headers_or_keys(self):
        self.use_cloud()
        self.ok(chat(self.plugin, self.sim, ctx=GOOGLE_CTX))
        self.ok(self.save(custom("mine")))
        for call in self.sim.calls:
            text = json.dumps(call)
            self.assertNotIn("Authorization", text)
            self.assertNotIn("headers", text)
            self.assertNotIn(FAKE_KEY, text)
        for call in self.sim.llm_calls():
            self.assertEqual(set(call["args"]) - {"path", "body", "stream", "target"}, set())

    def test_fallback_success_output_is_bounded(self):
        self.sim.faults["primary"] = ("http_error", 503)
        result = chat(self.plugin, self.sim, content="x" * 4000, ctx=LOCAL_CTX, fallback=True)
        out = self.ok(result)
        self.assertLessEqual(_size(out), MAX_OUTPUT)
        self.assertIs(out["used_fallback"], True)

    def test_plain_chat_output_reports_used_fallback_false(self):
        out = self.ok(chat(self.plugin, self.sim, content="plain", ctx=LOCAL_CTX))
        self.assertIs(out["used_fallback"], False)
        self.assertEqual(out["text"], "plain")


if __name__ == "__main__":
    unittest.main(verbosity=2)
