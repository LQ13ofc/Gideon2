#!/usr/bin/env python3
"""C4.1 / C4.2 fixture tests (stdlib unittest).

Runs tests/fixtures/c4/screen_observe.py and tests/fixtures/c4/computer_control.py without any
sandbox. CoreSim plays the Core: it answers host_call for synthetic.screen.* and synthetic.input.*
from an in-memory world, enforces the --agent-synthetic flag and the per-service permission grant,
and replies with host_reply (data or error). The plugin never sees the world object directly.
"""
import hashlib
import json
import queue
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C4 = ROOT / "tests" / "fixtures" / "c4"
SCREEN = C4 / "screen_observe.py"
COMPUTER = C4 / "computer_control.py"
PYTHON = sys.executable
CLEAN_ENV = {"PATH": "/usr/bin:/bin"}
MAX_OUTPUT = 8192
HOST_ERRORS = ("permission_denied", "stale_screen", "unknown_service", "invalid_input",
               "response_too_large", "timeout", "cancelled")
PERMS = {
    "synthetic.screen.capture": "screen_observe",
    "synthetic.input.a11y_tree": "input_control",
    "synthetic.input.click": "input_control",
    "synthetic.input.focus": "input_control",
    "synthetic.input.type": "input_control",
    "synthetic.input.key": "input_control",
}
ARGS = {
    "synthetic.screen.capture": frozenset(),
    "synthetic.input.a11y_tree": frozenset(),
    "synthetic.input.click": frozenset(("element", "epoch")),
    "synthetic.input.focus": frozenset(("element", "epoch")),
    "synthetic.input.type": frozenset(("text", "epoch")),
    "synthetic.input.key": frozenset(("key", "epoch")),
}
_ids = iter(range(10, 10_000))


def next_id():
    return next(_ids)


def spawn(script):
    return subprocess.Popen([PYTHON, "-I", str(script)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=CLEAN_ENV, cwd="/")


def sha256_of(screen):
    return hashlib.sha256(json.dumps(screen, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


class Plugin:
    def __init__(self, script):
        self.proc = spawn(script)
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

    def hello(self, plugin_id):
        self.write({"v": 1, "id": next_id(), "op": "hello", "plugin_id": plugin_id})
        return self.get(10)

    def close(self):
        try:
            self.write({"op": "shutdown"})
        except OSError:
            pass
        code = self.proc.wait(timeout=5)
        return code, self.proc.stderr.read()


class SimError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class World:
    def __init__(self):
        self.epoch = 1
        self.width = 1280
        self.height = 720
        self.windows = [{"id": "win-1", "title": "Demo", "focused": True}]
        self.elements = [
            {"id": "btn-ok", "role": "button", "name": "OK", "x": 100, "y": 200},
            {"id": "txt-name", "role": "textbox", "name": "Nome", "x": 100, "y": 260},
        ]
        self.focused = None
        self.typed = ""
        self.keys = []
        self.ignore_input = False  # actions are accepted but change nothing

    def screen(self):
        return {"epoch": self.epoch, "width": self.width, "height": self.height,
                "windows": [dict(w) for w in self.windows],
                "elements": [dict(e) for e in self.elements]}

    def tree(self):
        return {"epoch": self.epoch,
                "elements": [dict(e, focused=(e["id"] == self.focused)) for e in self.elements]}

    def state(self):
        return (self.epoch, self.focused, self.typed, list(self.keys), self.elements)


class CoreSim:
    """Plays the Core for host_call: flag, permission grant, fault injection, world effects."""

    def __init__(self, plugin):
        self.plugin = plugin
        self.world = World()
        self.grants = {"screen_observe": True, "input_control": True}
        self.synthetic = True  # the --agent-synthetic flag
        self.fault = None  # host error code returned before the handler (None = off)
        self.override = None  # replaces the data object of a successful reply
        self.raw_reply = None  # body of a malformed reply (op/id added by the sim)
        self.calls = []
        self.violations = []

    def _error(self, hid, code):
        self.plugin.write({"v": 1, "op": "host_reply", "id": hid, "error": code})

    def handle(self, msg):
        hid = msg.get("id")
        self.calls.append(msg)
        args = msg.get("args")
        service = msg.get("service")
        if (msg.get("v") != 1 or msg.get("op") != "host_call" or not isinstance(args, dict)
                or not isinstance(service, str)):
            self.violations.append(msg)
            return self._error(hid, "invalid_input")
        if not self.synthetic:
            return self._error(hid, "unknown_service")
        if service not in PERMS:
            self.violations.append(msg)
            return self._error(hid, "unknown_service")
        if not self.grants.get(PERMS[service]):
            return self._error(hid, "permission_denied")
        if self.fault is not None:
            return self._error(hid, self.fault)
        if set(args) != ARGS[service]:
            self.violations.append(msg)
            return self._error(hid, "invalid_input")
        if self.raw_reply is not None:
            self.plugin.write(dict(self.raw_reply, op="host_reply", id=hid))
            return
        try:
            data = self.override if self.override is not None else self._dispatch(service, args)
        except SimError as err:
            return self._error(hid, err.code)
        self.plugin.write({"v": 1, "op": "host_reply", "id": hid, "done": True, "data": data})

    def _dispatch(self, service, args):
        w = self.world
        if service == "synthetic.screen.capture":
            return w.screen()
        if service == "synthetic.input.a11y_tree":
            return w.tree()
        if args["epoch"] != w.epoch:
            raise SimError("stale_screen")
        if w.ignore_input:
            return {}
        if service in ("synthetic.input.click", "synthetic.input.focus"):
            if not any(e["id"] == args["element"] for e in w.elements):
                raise SimError("invalid_input")
            w.focused = args["element"]
        elif service == "synthetic.input.type":
            w.typed += args["text"]
        else:
            w.keys.append(args["key"])
        w.epoch += 1
        return {}


def invoke(plugin, sim, capability, inp, timeout=20):
    """Send one invoke, serve host_call from sim, return the invoke reply line."""
    inv_id = next_id()
    plugin.write({"v": 1, "id": inv_id, "op": "invoke", "capability": capability,
                  "input": inp, "deadline_ms": 10000})
    deadline = time.monotonic() + timeout
    while True:
        item = plugin.get(max(0.1, deadline - time.monotonic()))
        if item.get("op") == "host_call":
            sim.handle(item)
        elif item.get("id") == inv_id:
            return item
        else:
            raise AssertionError("unexpected plugin line: %r" % (item,))


class PluginTestMixin:
    """Shared setup for one plugin process per class. Not a TestCase on its own."""
    SCRIPT = None
    PLUGIN_ID = None
    CAPABILITIES = None

    @classmethod
    def setUpClass(cls):
        cls.plugin = Plugin(cls.SCRIPT)
        cls.hello = cls.plugin.hello(cls.PLUGIN_ID)

    @classmethod
    def tearDownClass(cls):
        code, stderr = cls.plugin.close()
        assert code == 0, "plugin exit code %r" % code
        assert stderr == b"", "plugin wrote to stderr"

    def setUp(self):
        self.sim = CoreSim(self.plugin)

    def run_invoke(self, capability, inp):
        return invoke(self.plugin, self.sim, capability, inp)

    def ok(self, reply):
        self.assertIs(reply.get("ok"), True, reply)
        self.assertEqual(set(reply), {"id", "ok", "output"}, reply)
        self.assertLessEqual(len(json.dumps(reply["output"], separators=(",", ":"))), MAX_OUTPUT)
        return reply["output"]

    def err(self, reply, code):
        self.assertEqual(reply.get("ok"), False, reply)
        self.assertEqual(set(reply), {"id", "ok", "error"}, reply)
        self.assertEqual(reply["error"], code, reply)

    def test_hello_reply(self):
        self.assertIs(self.hello.get("ok"), True)
        self.assertEqual(self.hello.get("api"), 1)
        self.assertEqual(self.hello.get("plugin_id"), self.PLUGIN_ID)
        self.assertEqual(self.hello.get("capabilities"), self.CAPABILITIES)

    def test_unknown_capability(self):
        self.err(self.run_invoke(self.PLUGIN_ID + ".other", {}), "unknown_capability")
        self.assertEqual(self.sim.calls, [])


class ScreenObserveTest(PluginTestMixin, unittest.TestCase):
    SCRIPT = SCREEN
    PLUGIN_ID = "screen_observe"
    CAPABILITIES = ["screen_observe.capture", "screen_observe.status"]
    CAP = "screen_observe.capture"

    def test_capture_happy_path_and_host_call_shape(self):
        out = self.ok(self.run_invoke(self.CAP, {}))
        screen = self.sim.world.screen()
        self.assertEqual(set(out), {"backend", "epoch", "width", "height", "sha256", "regions"})
        self.assertEqual(out["backend"], "synthetic")
        self.assertEqual(out["epoch"], 1)
        self.assertEqual((out["width"], out["height"]), (1280, 720))
        self.assertEqual(out["regions"], [
            {"role": "button", "name": "OK", "x": 100, "y": 200},
            {"role": "textbox", "name": "Nome", "x": 100, "y": 260},
        ])
        self.assertEqual(out["sha256"], sha256_of(screen))
        self.assertEqual(len(self.sim.calls), 1)
        call = self.sim.calls[0]
        self.assertEqual(call["v"], 1)
        self.assertEqual(call["op"], "host_call")
        self.assertEqual(call["service"], "synthetic.screen.capture")
        self.assertEqual(call["args"], {})
        self.assertEqual(self.sim.violations, [])

    def test_sha256_follows_world_state(self):
        first = self.ok(self.run_invoke(self.CAP, {}))["sha256"]
        self.sim.world.epoch += 1
        second = self.ok(self.run_invoke(self.CAP, {}))
        self.assertEqual(second["epoch"], 2)
        self.assertNotEqual(first, second["sha256"])
        self.assertEqual(second["sha256"], sha256_of(self.sim.world.screen()))

    def test_status_is_synthetic_only_and_makes_no_host_call(self):
        out = self.ok(self.run_invoke("screen_observe.status", {}))
        self.assertEqual(out, {"backend": "synthetic", "real_backend": "unsupported",
                               "reason": "needs_human_validation"})
        self.assertEqual(self.sim.calls, [])

    def test_invalid_input_rejected_before_host_call(self):
        cases = {
            "unknown key": {"x": 1},
            "epoch key": {"epoch": 1},
            "list": [],
            "string": "x",
            "null": None,
        }
        for label, bad in cases.items():
            with self.subTest(case=label):
                self.err(self.run_invoke(self.CAP, bad), "invalid_input")
                self.err(self.run_invoke("screen_observe.status", bad), "invalid_input")
        self.assertEqual(self.sim.calls, [])

    def test_permission_denied_passthrough(self):
        self.sim.grants["screen_observe"] = False
        self.err(self.run_invoke(self.CAP, {}), "permission_denied")
        self.assertEqual(len(self.sim.calls), 1)

    def test_host_error_codes_pass_through(self):
        for code in HOST_ERRORS:
            with self.subTest(code=code):
                self.sim.fault = code
                self.err(self.run_invoke(self.CAP, {}), code)
        self.sim.fault = None

    def test_unknown_host_code_becomes_plugin_error(self):
        self.sim.fault = "weird_code"
        self.err(self.run_invoke(self.CAP, {}), "plugin_error")

    def test_no_synthetic_flag_gives_unknown_service(self):
        self.sim.synthetic = False
        self.err(self.run_invoke(self.CAP, {}), "unknown_service")

    def test_malformed_host_replies_are_plugin_error(self):
        cases = {
            "data not object": {"done": True, "data": []},
            "missing done": {"data": {}},
            "extra reply key": {"done": True, "data": {}, "chunk": "x"},
        }
        for label, raw in cases.items():
            with self.subTest(case=label):
                self.sim.raw_reply = raw
                self.err(self.run_invoke(self.CAP, {}), "plugin_error")
        self.sim.raw_reply = None

    def test_screen_contract_violations_are_plugin_error(self):
        good = self.sim.world.screen()
        bad_epoch = dict(good, epoch=-1)
        bad_extra = dict(good, extra=1)
        bad_name = dict(good, elements=[dict(good["elements"][0], name="a\tb")])
        too_many = dict(good, elements=[dict(good["elements"][0], id="e%d" % i)
                                        for i in range(300)])
        for label, override in {"epoch": bad_epoch, "extra key": bad_extra,
                                "control char": bad_name, "too many": too_many}.items():
            with self.subTest(case=label):
                self.sim.override = override
                self.err(self.run_invoke(self.CAP, {}), "plugin_error")
        self.sim.override = None

    def test_output_stays_within_8_kib_and_flags_truncation(self):
        # ASCII names: the host reply must stay under the plugin line limit (64 KiB) while the
        # regions still overflow 8 KiB, which exercises the shrink-and-flag path.
        elements = [{"id": "e%03d" % i, "role": "button", "name": "n" * 120 + str(i),
                     "x": i, "y": i} for i in range(200)]
        screen = dict(self.sim.world.screen(), elements=elements)
        self.sim.override = screen
        out = self.ok(self.run_invoke(self.CAP, {}))
        self.assertIs(out["truncated"], True)
        self.assertGreater(len(out["regions"]), 0)
        self.assertLess(len(out["regions"]), 64)
        self.assertLessEqual(len(json.dumps(out, separators=(",", ":"))), MAX_OUTPUT)
        self.assertEqual(out["sha256"], sha256_of(screen))
        self.sim.override = None

    def test_64_regions_without_truncation_when_small(self):
        elements = [{"id": "e%02d" % i, "role": "button", "name": "b%d" % i, "x": i, "y": i}
                    for i in range(64)]
        self.sim.override = dict(self.sim.world.screen(), elements=elements)
        out = self.ok(self.run_invoke(self.CAP, {}))
        self.assertEqual(len(out["regions"]), 64)
        self.assertNotIn("truncated", out)
        self.sim.override = None


class ComputerControlTest(PluginTestMixin, unittest.TestCase):
    SCRIPT = COMPUTER
    PLUGIN_ID = "computer_control"
    CAPABILITIES = ["computer_control.tree", "computer_control.act", "computer_control.status"]
    TREE = "computer_control.tree"
    ACT = "computer_control.act"

    def act(self, inp):
        return self.run_invoke(self.ACT, inp)

    def tree_elements(self):
        return [
            {"id": "btn-ok", "role": "button", "name": "OK", "x": 100, "y": 200, "focused": False},
            {"id": "txt-name", "role": "textbox", "name": "Nome", "x": 100, "y": 260,
             "focused": False},
        ]

    # -- read paths -----------------------------------------------------------
    def test_tree_happy_path_and_host_call_shape(self):
        out = self.ok(self.run_invoke(self.TREE, {}))
        self.assertEqual(out, {"backend": "synthetic", "epoch": 1,
                               "elements": self.tree_elements()})
        self.assertEqual(len(self.sim.calls), 1)
        call = self.sim.calls[0]
        self.assertEqual(call["v"], 1)
        self.assertEqual(call["op"], "host_call")
        self.assertEqual(call["service"], "synthetic.input.a11y_tree")
        self.assertEqual(call["args"], {})
        self.assertEqual(self.sim.violations, [])

    def test_status_is_synthetic_only_and_makes_no_host_call(self):
        out = self.ok(self.run_invoke("computer_control.status", {}))
        self.assertEqual(out, {"backend": "synthetic", "real_backend": "unsupported",
                               "reason": "needs_human_validation"})
        self.assertEqual(self.sim.calls, [])

    def test_tree_output_stays_within_8_kib(self):
        self.sim.world.elements = [{"id": "e%03d" % i, "role": "button", "name": "n" * 120 + str(i),
                                    "x": i, "y": i} for i in range(200)]
        out = self.ok(self.run_invoke(self.TREE, {}))
        self.assertIs(out["truncated"], True)
        self.assertLess(len(out["elements"]), 64)
        self.assertLessEqual(len(json.dumps(out, separators=(",", ":"))), MAX_OUTPUT)

    # -- actions: happy path ---------------------------------------------------
    def test_click_happy_path_verified_true(self):
        out = self.ok(self.act({"kind": "click", "epoch": 1, "element": "btn-ok"}))
        self.assertEqual(out, {"backend": "synthetic", "kind": "click", "epoch": 2,
                               "verified": True, "element": "btn-ok"})
        self.assertEqual(self.sim.world.focused, "btn-ok")
        act_call, tree_call = self.sim.calls
        self.assertEqual(act_call["service"], "synthetic.input.click")
        self.assertEqual(act_call["args"], {"element": "btn-ok", "epoch": 1})
        self.assertEqual(tree_call["service"], "synthetic.input.a11y_tree")
        self.assertEqual(tree_call["args"], {})
        self.assertEqual(self.sim.violations, [])

    def test_focus_happy_path_verified_true(self):
        out = self.ok(self.act({"kind": "focus", "epoch": 1, "element": "txt-name"}))
        self.assertEqual(out["verified"], True)
        self.assertEqual(out["element"], "txt-name")
        self.assertEqual(self.sim.calls[0]["service"], "synthetic.input.focus")
        self.assertEqual(self.sim.calls[0]["args"], {"element": "txt-name", "epoch": 1})

    def test_click_reflected_in_tree_after_action(self):
        self.ok(self.act({"kind": "click", "epoch": 1, "element": "btn-ok"}))
        out = self.ok(self.run_invoke(self.TREE, {}))
        focused = [e["id"] for e in out["elements"] if e["focused"]]
        self.assertEqual(focused, ["btn-ok"])

    def test_type_happy_path_and_boundary_64_bytes(self):
        out = self.ok(self.act({"kind": "type", "epoch": 1, "text": "Ana"}))
        self.assertEqual(out, {"backend": "synthetic", "kind": "type", "epoch": 2,
                               "verified": True})
        self.assertEqual(self.sim.world.typed, "Ana")
        self.assertEqual(self.sim.calls[0]["service"], "synthetic.input.type")
        self.assertEqual(self.sim.calls[0]["args"], {"text": "Ana", "epoch": 1})
        boundary = "ç" * 32  # 64 UTF-8 bytes: the largest accepted text
        self.ok(self.act({"kind": "type", "epoch": 2, "text": boundary}))
        self.assertEqual(self.sim.world.typed, "Ana" + boundary)

    def test_key_happy_path(self):
        out = self.ok(self.act({"kind": "key", "epoch": 1, "key": "Enter"}))
        self.assertEqual(out, {"backend": "synthetic", "kind": "key", "epoch": 2,
                               "verified": True})
        self.assertEqual(self.sim.world.keys, ["Enter"])
        self.assertEqual(self.sim.calls[0]["service"], "synthetic.input.key")
        self.assertEqual(self.sim.calls[0]["args"], {"key": "Enter", "epoch": 1})

    # -- freshness and verification ---------------------------------------------
    def test_stale_epoch_has_no_effect(self):
        before = self.sim.world.state()
        self.err(self.act({"kind": "click", "epoch": 0, "element": "btn-ok"}), "stale_screen")
        self.assertEqual(self.sim.world.state(), before)
        self.assertEqual(len(self.sim.calls), 1)  # no re-read after a refused action

    def test_verified_false_when_world_ignores_input(self):
        self.sim.world.ignore_input = True
        out = self.ok(self.act({"kind": "click", "epoch": 1, "element": "btn-ok"}))
        self.assertIs(out["verified"], False)
        self.assertEqual(out["epoch"], 1)
        out = self.ok(self.act({"kind": "type", "epoch": 1, "text": "x"}))
        self.assertIs(out["verified"], False)
        self.assertEqual(self.sim.world.typed, "")

    # -- invalid input -----------------------------------------------------------
    def test_invalid_inputs_rejected_before_host_call(self):
        cases = {
            "not object": [],
            "null": None,
            "missing kind": {"epoch": 1, "element": "btn-ok"},
            "unknown kind": {"kind": "drag", "epoch": 1},
            "kind not string": {"kind": ["click"], "epoch": 1, "element": "btn-ok"},
            "click missing element": {"kind": "click", "epoch": 1},
            "click extra text": {"kind": "click", "epoch": 1, "element": "btn-ok", "text": "x"},
            "element with space": {"kind": "click", "epoch": 1, "element": "btn ok"},
            "element empty": {"kind": "click", "epoch": 1, "element": ""},
            "element too long": {"kind": "click", "epoch": 1, "element": "x" * 65},
            "element not string": {"kind": "click", "epoch": 1, "element": 5},
            "epoch missing": {"kind": "click", "element": "btn-ok"},
            "epoch bool": {"kind": "click", "epoch": True, "element": "btn-ok"},
            "epoch negative": {"kind": "click", "epoch": -1, "element": "btn-ok"},
            "epoch string": {"kind": "click", "epoch": "1", "element": "btn-ok"},
            "epoch too big": {"kind": "click", "epoch": 2 ** 31, "element": "btn-ok"},
            "type empty": {"kind": "type", "epoch": 1, "text": ""},
            "type 65 bytes": {"kind": "type", "epoch": 1, "text": "a" * 65},
            "type 66 bytes utf8": {"kind": "type", "epoch": 1, "text": "ç" * 33},
            "type control char": {"kind": "type", "epoch": 1, "text": "a\tb"},
            "type missing text": {"kind": "type", "epoch": 1},
            "type with element": {"kind": "type", "epoch": 1, "text": "a", "element": "btn-ok"},
            "key not in list": {"kind": "key", "epoch": 1, "key": "F12"},
            "key lowercase": {"kind": "key", "epoch": 1, "key": "enter"},
            "key not string": {"kind": "key", "epoch": 1, "key": ["Enter"]},
            "key missing": {"kind": "key", "epoch": 1},
        }
        for label, bad in cases.items():
            with self.subTest(case=label):
                self.err(self.act(bad), "invalid_input")
        self.assertEqual(self.sim.calls, [])
        self.assertEqual(self.sim.world.state()[0], 1)

    def test_tree_rejects_any_input_key(self):
        self.err(self.run_invoke(self.TREE, {"epoch": 1}), "invalid_input")
        self.err(self.run_invoke("computer_control.status", {"x": 1}), "invalid_input")
        self.assertEqual(self.sim.calls, [])

    # -- host error passthrough ----------------------------------------------------
    def test_action_host_errors_pass_through_without_reread(self):
        for code in HOST_ERRORS:
            with self.subTest(code=code):
                self.sim.calls.clear()
                self.sim.fault = code
                self.err(self.act({"kind": "click", "epoch": 1, "element": "btn-ok"}), code)
                self.assertEqual(len(self.sim.calls), 1)
        self.sim.fault = None

    def test_tree_host_errors_pass_through(self):
        for code in HOST_ERRORS:
            with self.subTest(code=code):
                self.sim.fault = code
                self.err(self.run_invoke(self.TREE, {}), code)
        self.sim.fault = None

    def test_permission_denied_without_input_control_grant(self):
        self.sim.grants["input_control"] = False
        self.err(self.run_invoke(self.TREE, {}), "permission_denied")
        self.err(self.act({"kind": "key", "epoch": 1, "key": "Tab"}), "permission_denied")
        self.assertEqual(self.sim.world.keys, [])

    def test_no_synthetic_flag_gives_unknown_service(self):
        self.sim.synthetic = False
        self.err(self.act({"kind": "click", "epoch": 1, "element": "btn-ok"}), "unknown_service")

    def test_unknown_element_passes_host_invalid_input(self):
        self.err(self.act({"kind": "click", "epoch": 1, "element": "nope"}), "invalid_input")

    def test_unknown_host_code_becomes_plugin_error(self):
        self.sim.fault = "weird_code"
        self.err(self.act({"kind": "focus", "epoch": 1, "element": "btn-ok"}), "plugin_error")
        self.sim.fault = None

    def test_malformed_tree_reply_is_plugin_error(self):
        bad = {"epoch": 1, "elements": [{"id": "x"}]}
        self.sim.override = bad
        self.err(self.run_invoke(self.TREE, {}), "plugin_error")
        self.err(self.act({"kind": "click", "epoch": 1, "element": "btn-ok"}), "plugin_error")
        self.sim.override = None

    def test_malformed_host_reply_shapes_are_plugin_error(self):
        cases = {
            "data not object": {"done": True, "data": "x"},
            "missing done": {"data": {"epoch": 1, "elements": []}},
            "extra reply key": {"done": True, "data": {"epoch": 1, "elements": []}, "chunk": "x"},
        }
        for label, raw in cases.items():
            with self.subTest(case=label):
                self.sim.raw_reply = raw
                self.err(self.run_invoke(self.TREE, {}), "plugin_error")
        self.sim.raw_reply = None


if __name__ == "__main__":
    unittest.main(verbosity=2)
