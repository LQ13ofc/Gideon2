#!/usr/bin/env python3
"""C4.3-C4.6 fixture tests (stdlib unittest): audio_advanced, mic_advanced, camera_gesture,
display_manipulate, and the C4 catalog written by scripts/make_c4_catalog.py.

Each plugin runs as `python3 -I payload` with no sandbox. A host simulator plays the Core for
one area: it applies the permission gate (one grant per area, else permission_denied), answers
only synthetic.<area>.<verb> services from an in-memory World, and records every host_call.
The World shapes are assumptions of this fixture (docs/C4.md names the services but not their
replies); the Core side must match them. No hardware, no network.
"""
import copy
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
FIXTURES = ROOT / "tests" / "fixtures"
C4 = FIXTURES / "c4"
C0_CATALOG = FIXTURES / "hub-c0.json"
C4_CATALOG = FIXTURES / "hub-c4.json"
CATALOG_SCRIPT = ROOT / "scripts" / "make_c4_catalog.py"
PYTHON = sys.executable
CLEAN_ENV = {"PATH": "/usr/bin:/bin"}
AREA_PERMISSION = {"audio": "audio_route", "mic": "mic_config", "camera": "camera_capture"}
MAX_OUTPUT = 8192
_ids = iter(range(10, 1000000))


def next_id():
    return next(_ids)


class HostFault(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class Plugin:
    def __init__(self, payload):
        self.proc = subprocess.Popen([PYTHON, "-I", str(payload)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env=CLEAN_ENV, cwd="/")
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

    def get(self, timeout=10):
        item = self.queue.get(timeout=timeout)
        if item is None:
            raise EOFError("plugin closed stdout")
        return item

    def hello(self, plugin_id):
        self.write({"v": 1, "id": next_id(), "op": "hello", "plugin_id": plugin_id})
        return self.get()

    def close(self):
        try:
            self.write({"op": "shutdown"})
        except OSError:
            pass
        code = self.proc.wait(timeout=5)
        return code, self.proc.stderr.read()


class World:
    """The synthetic world as the Core would serve it (fixture assumption)."""

    def __init__(self):
        self.audio = {
            "routes": [{"id": "speakers", "active": True}, {"id": "headset", "active": False}],
            "apps": [{"id": "music", "volume": 50}, {"id": "video", "volume": 20}],
            "eq": "flat",
            "denoise": False,
        }
        self.mic = {"device": "synthetic-mic-0", "gain": 50, "filter": "off", "monitor": False,
                    "recording": False, "indicator": False}
        self.camera = {"opt_in": False, "indicator": False, "frame_seq": 0, "gesture": None}
        self.gestures = ["wave", "thumbs_up"]
        self.base = {"mic_state": "idle", "speaker_state": "idle"}  # sentinel, never changed
        self.fault = None  # host error code returned by every service
        self.garbage = False  # every service returns an unexpected object
        self.stuck = False  # audio and mic writes are accepted but change nothing
        self.no_indicator = False  # mic recording starts without the privacy indicator

    def snapshot(self):
        return copy.deepcopy({"audio": self.audio, "mic": self.mic, "camera": self.camera,
                              "base": self.base})

    def call(self, service, args):
        if self.fault is not None:
            raise HostFault(self.fault)
        if self.garbage:
            return {"nonsense": 1}
        handlers = {
            "synthetic.audio.state": self._audio_state,
            "synthetic.audio.set_route": self._audio_set_route,
            "synthetic.audio.app_volume": self._audio_app_volume,
            "synthetic.audio.eq": self._audio_eq,
            "synthetic.audio.denoise": self._audio_denoise,
            "synthetic.mic.state": self._mic_state,
            "synthetic.mic.configure": self._mic_configure,
            "synthetic.mic.monitor": self._mic_monitor,
            "synthetic.mic.record_start": self._mic_record_start,
            "synthetic.mic.record_stop": self._mic_record_stop,
            "synthetic.camera.state": self._camera_state,
            "synthetic.camera.optin": self._camera_optin,
            "synthetic.camera.capture": self._camera_capture,
            "synthetic.camera.gestures": self._camera_gestures,
        }
        handler = handlers.get(service)
        if handler is None:
            raise HostFault("unknown_service")
        return handler(args)

    def _audio_state(self, args):
        return copy.deepcopy(self.audio)

    def _audio_set_route(self, args):
        if args.get("route") not in [route["id"] for route in self.audio["routes"]]:
            raise HostFault("invalid_input")
        if not self.stuck:
            for route in self.audio["routes"]:
                route["active"] = route["id"] == args["route"]
        return copy.deepcopy(self.audio)

    def _audio_app_volume(self, args):
        for app in self.audio["apps"]:
            if app["id"] == args.get("app"):
                if not self.stuck:
                    app["volume"] = args["volume"]
                return copy.deepcopy(self.audio)
        raise HostFault("invalid_input")

    def _audio_eq(self, args):
        if args.get("preset") not in ("flat", "voice", "bass", "treble"):
            raise HostFault("invalid_input")
        if not self.stuck:
            self.audio["eq"] = args["preset"]
        return copy.deepcopy(self.audio)

    def _audio_denoise(self, args):
        if not self.stuck:
            self.audio["denoise"] = args["enabled"]
        return copy.deepcopy(self.audio)

    def _mic_state(self, args):
        return copy.deepcopy(self.mic)

    def _mic_configure(self, args):
        if not self.stuck:
            self.mic.update(args)
        return copy.deepcopy(self.mic)

    def _mic_monitor(self, args):
        if not self.stuck:
            self.mic["monitor"] = args["enabled"]
        return copy.deepcopy(self.mic)

    def _mic_record_start(self, args):
        self.mic["recording"] = True
        self.mic["indicator"] = not self.no_indicator
        return copy.deepcopy(self.mic)

    def _mic_record_stop(self, args):
        self.mic["recording"] = False
        self.mic["indicator"] = False
        return copy.deepcopy(self.mic)

    def _camera_state(self, args):
        return copy.deepcopy(self.camera)

    def _camera_optin(self, args):
        enabled = args["enabled"]
        self.camera["opt_in"] = enabled
        self.camera["indicator"] = enabled
        if not enabled:
            self.camera["frame_seq"] = 0  # opt-out clears the frames
        return copy.deepcopy(self.camera)

    def _camera_capture(self, args):
        if not self.camera["opt_in"]:
            raise HostFault("opt_in_required")
        self.camera["frame_seq"] += 1
        return copy.deepcopy(self.camera)

    def _camera_gestures(self, args):
        if not self.camera["opt_in"]:
            raise HostFault("opt_in_required")
        return {"gestures": list(self.gestures)}


class HostSim:
    """Plays the Core for one plugin area: permission gate, world answers, call log."""

    def __init__(self, plugin, world, area, grants=()):
        self.plugin = plugin
        self.world = world
        self.area = area
        self.grants = set(grants)
        self.calls = []
        self.violations = []
        self.hold = False  # True: never answer a host_call (cancel tests)

    def handle(self, msg):
        hid = msg["id"]
        service = msg.get("service")
        self.calls.append((service, msg.get("args")))
        if self.hold:
            return
        if not self.area or not isinstance(service, str) or not service.startswith(
                "synthetic.%s." % self.area):
            self.violations.append(service)
            self._reply(hid, error="unknown_service")
            return
        if AREA_PERMISSION[self.area] not in self.grants:
            self._reply(hid, error="permission_denied")
            return
        try:
            data = self.world.call(service, msg.get("args"))
        except HostFault as fault:
            self._reply(hid, error=fault.code)
            return
        self._reply(hid, data=data)

    def _reply(self, hid, data=None, error=None):
        if error is not None:
            self.plugin.write({"v": 1, "op": "host_reply", "id": hid, "error": error})
        else:
            self.plugin.write({"v": 1, "op": "host_reply", "id": hid, "done": True, "data": data})


def invoke(plugin, sim, capability, inp, cancel_after=None, timeout=10):
    """Send one invoke, answer its host_calls, return the final reply line."""
    inv_id = next_id()
    timer = None
    if cancel_after is not None:
        timer = threading.Timer(cancel_after,
                                lambda: plugin.write({"op": "cancel", "id": inv_id}))
        timer.start()
    plugin.write({"v": 1, "id": inv_id, "op": "invoke", "capability": capability,
                  "input": inp, "deadline_ms": 5000})
    deadline = time.monotonic() + timeout
    try:
        while True:
            item = plugin.get(max(0.1, deadline - time.monotonic()))
            if item.get("op") == "host_call":
                sim.handle(item)
            elif item.get("id") == inv_id:
                return item
            else:
                raise AssertionError("unexpected plugin line: %r" % (item,))
    finally:
        if timer is not None:
            timer.cancel()


class FixtureCase(unittest.TestCase):
    PLUGIN_ID = None
    AREA = None
    GRANTS = ()
    CAPS = []

    @classmethod
    def setUpClass(cls):
        cls.plugin = Plugin(C4 / (cls.PLUGIN_ID + ".py"))
        cls.hello = cls.plugin.hello(cls.PLUGIN_ID)

    @classmethod
    def tearDownClass(cls):
        code, stderr = cls.plugin.close()
        assert code == 0, "plugin exit code %r" % code
        assert stderr == b"", "plugin wrote to stderr"
        for raw in cls.plugin.transcript:
            assert isinstance(json.loads(raw), dict), "stdout line is not a protocol object"

    def setUp(self):
        self.world = World()
        self.sim = HostSim(self.plugin, self.world, self.AREA, self.GRANTS)

    def tearDown(self):
        self.assertEqual(self.sim.violations, [], "host_call outside synthetic.%s" % self.AREA)

    def call(self, capability, inp, **kw):
        return invoke(self.plugin, self.sim, capability, inp, **kw)

    def assertOutput(self, reply):
        self.assertIs(reply.get("ok"), True, reply)
        self.assertLessEqual(len(json.dumps(reply["output"], separators=(",", ":"))), MAX_OUTPUT)
        return reply["output"]

    def assertError(self, reply, code):
        self.assertEqual(set(reply), {"id", "ok", "error"}, reply)
        self.assertIs(reply["ok"], False, reply)
        self.assertEqual(reply["error"], code, reply)


class HostChecks:
    """Checks shared by the three plugins that call synthetic.<area>.* services.
    Needs STATE_CAP and INVALID on the concrete class."""

    def test_hello_lists_capabilities(self):
        self.assertIs(self.hello.get("ok"), True)
        self.assertEqual(self.hello["plugin_id"], self.PLUGIN_ID)
        self.assertEqual(self.hello["api"], 1)
        self.assertEqual(self.hello["capabilities"], self.CAPS)

    def test_unknown_capability(self):
        self.assertError(self.call(self.PLUGIN_ID + ".nope", {}), "unknown_capability")
        self.assertEqual(self.sim.calls, [])

    def test_invalid_inputs_never_reach_the_host(self):
        for capability, inp in self.INVALID:
            with self.subTest(capability=capability, inp=inp):
                self.assertError(self.call(capability, inp), "invalid_input")
        self.assertEqual(self.sim.calls, [])

    def test_permission_denied_without_grant_leaves_world_unchanged(self):
        self.sim = HostSim(self.plugin, self.world, self.AREA, grants=())
        before = self.world.snapshot()
        self.assertError(self.call(self.STATE_CAP, {}), "permission_denied")
        self.assertEqual(self.world.snapshot(), before)

    def test_host_errors_pass_through(self):
        for code in ("permission_denied", "opt_in_required", "invalid_input",
                     "unknown_service", "world_unavailable"):
            with self.subTest(code=code):
                self.world.fault = code
                self.assertError(self.call(self.STATE_CAP, {}), code)
        self.world.fault = "weird_code"
        self.assertError(self.call(self.STATE_CAP, {}), "plugin_error")

    def test_malformed_host_reply_is_plugin_error(self):
        self.world.garbage = True
        self.assertError(self.call(self.STATE_CAP, {}), "plugin_error")

    def test_cancel_during_host_call_then_plugin_still_serves(self):
        before = self.world.snapshot()
        self.sim.hold = True
        self.assertError(self.call(self.STATE_CAP, {}, cancel_after=0.3), "cancelled")
        self.assertEqual(self.world.snapshot(), before)
        self.sim.hold = False
        self.assertOutput(self.call(self.STATE_CAP, {}))

    def test_base_sentinel_untouched_by_every_path(self):
        base = copy.deepcopy(self.world.base)
        self.call(self.STATE_CAP, {})
        for capability, inp in self.SAMPLE_ACTIONS:
            self.call(capability, inp)
        self.assertEqual(self.world.base, base)
        self.assertTrue(all(service.startswith("synthetic.%s." % self.AREA)
                            for service, _ in self.sim.calls))


class AudioTest(HostChecks, FixtureCase):
    PLUGIN_ID = "audio_advanced"
    AREA = "audio"
    GRANTS = ("audio_route",)
    CAPS = ["audio_advanced.state", "audio_advanced.act"]
    STATE_CAP = "audio_advanced.state"
    ACT_CAP = "audio_advanced.act"
    SAMPLE_ACTIONS = [
        ("audio_advanced.act", {"kind": "route", "route": "headset"}),
        ("audio_advanced.act", {"kind": "app_volume", "app": "video", "volume": 0}),
        ("audio_advanced.act", {"kind": "eq", "preset": "bass"}),
        ("audio_advanced.act", {"kind": "denoise", "enabled": True}),
    ]
    INVALID = [
        ("audio_advanced.state", {"x": 1}),
        ("audio_advanced.state", []),
        ("audio_advanced.act", None),
        ("audio_advanced.act", {}),
        ("audio_advanced.act", {"kind": "route"}),
        ("audio_advanced.act", {"kind": "reverb", "level": 1}),
        ("audio_advanced.act", {"kind": ["route"], "route": "headset"}),
        ("audio_advanced.act", {"kind": "route", "route": "Head Set"}),
        ("audio_advanced.act", {"kind": "route", "route": "../etc"}),
        ("audio_advanced.act", {"kind": "route", "route": "headset", "extra": 1}),
        ("audio_advanced.act", {"kind": "route", "route": 7}),
        ("audio_advanced.act", {"kind": "app_volume", "app": "music"}),
        ("audio_advanced.act", {"kind": "app_volume", "app": "music", "volume": 101}),
        ("audio_advanced.act", {"kind": "app_volume", "app": "music", "volume": -1}),
        ("audio_advanced.act", {"kind": "app_volume", "app": "music", "volume": 5.0}),
        ("audio_advanced.act", {"kind": "app_volume", "app": "music", "volume": True}),
        ("audio_advanced.act", {"kind": "eq", "preset": "rock"}),
        ("audio_advanced.act", {"kind": "eq", "preset": ["flat"]}),
        ("audio_advanced.act", {"kind": "denoise", "enabled": "yes"}),
        ("audio_advanced.act", {"kind": "denoise", "enabled": 1}),
    ]

    def test_state_is_synthetic_and_never_real(self):
        out = self.assertOutput(self.call(self.STATE_CAP, {}))
        self.assertEqual(set(out), {"backend", "real_backend", "reason", "routes", "apps",
                                    "eq", "denoise"})
        self.assertEqual(out["backend"], "synthetic")
        self.assertEqual(out["real_backend"], "unsupported")
        self.assertEqual(out["reason"], "needs_human_validation")
        self.assertEqual(out["routes"], self.world.audio["routes"])
        self.assertEqual(out["apps"], self.world.audio["apps"])
        self.assertEqual(out["eq"], "flat")
        self.assertIs(out["denoise"], False)

    def test_route_change_is_verified_by_a_reread(self):
        out = self.assertOutput(self.call(self.ACT_CAP, {"kind": "route", "route": "headset"}))
        self.assertEqual(out["kind"], "route")
        self.assertIs(out["verified"], True)
        self.assertEqual([r["id"] for r in out["routes"] if r["active"]], ["headset"])
        self.assertEqual([s for s, _ in self.sim.calls],
                         ["synthetic.audio.set_route", "synthetic.audio.state"])

    def test_app_volume_bounds_0_and_100_are_accepted(self):
        for volume in (0, 100):
            with self.subTest(volume=volume):
                out = self.assertOutput(self.call(
                    self.ACT_CAP, {"kind": "app_volume", "app": "music", "volume": volume}))
                self.assertIs(out["verified"], True)
                self.assertEqual(out["apps"][0], {"id": "music", "volume": volume})

    def test_eq_presets_are_the_fixed_list(self):
        for preset in ("flat", "voice", "bass", "treble"):
            with self.subTest(preset=preset):
                out = self.assertOutput(self.call(self.ACT_CAP, {"kind": "eq", "preset": preset}))
                self.assertEqual(out["eq"], preset)
                self.assertIs(out["verified"], True)

    def test_denoise_toggle_is_verified(self):
        out = self.assertOutput(self.call(self.ACT_CAP, {"kind": "denoise", "enabled": True}))
        self.assertIs(out["denoise"], True)
        self.assertIs(out["verified"], True)
        self.assertIs(self.world.audio["denoise"], True)

    def test_unverified_change_reports_false(self):
        self.world.stuck = True
        out = self.assertOutput(self.call(
            self.ACT_CAP, {"kind": "app_volume", "app": "video", "volume": 90}))
        self.assertIs(out["verified"], False)
        self.assertEqual(out["apps"][1], {"id": "video", "volume": 20})

    def test_act_without_grant_is_permission_denied(self):
        self.sim = HostSim(self.plugin, self.world, self.AREA, grants=())
        before = self.world.snapshot()
        self.assertError(self.call(self.ACT_CAP, {"kind": "eq", "preset": "treble"}),
                         "permission_denied")
        self.assertEqual(self.world.snapshot(), before)

    def test_act_host_error_passes_through(self):
        self.world.fault = "invalid_input"
        self.assertError(self.call(self.ACT_CAP, {"kind": "route", "route": "speakers"}),
                         "invalid_input")

    def test_unknown_route_is_refused_by_the_host(self):
        self.assertError(self.call(self.ACT_CAP, {"kind": "route", "route": "ghost"}),
                         "invalid_input")


class MicTest(HostChecks, FixtureCase):
    PLUGIN_ID = "mic_advanced"
    AREA = "mic"
    GRANTS = ("mic_config",)
    CAPS = ["mic_advanced.state", "mic_advanced.configure", "mic_advanced.monitor",
            "mic_advanced.record"]
    STATE_CAP = "mic_advanced.state"
    CONFIGURE_CAP = "mic_advanced.configure"
    MONITOR_CAP = "mic_advanced.monitor"
    RECORD_CAP = "mic_advanced.record"
    SAMPLE_ACTIONS = [
        ("mic_advanced.configure", {"gain": 60}),
        ("mic_advanced.monitor", {"enabled": True}),
        ("mic_advanced.record", {"action": "start"}),
        ("mic_advanced.record", {"action": "stop"}),
    ]
    INVALID = [
        ("mic_advanced.state", {"x": 1}),
        ("mic_advanced.configure", {}),
        ("mic_advanced.configure", {"gain": 101}),
        ("mic_advanced.configure", {"gain": -1}),
        ("mic_advanced.configure", {"gain": True}),
        ("mic_advanced.configure", {"gain": "5"}),
        ("mic_advanced.configure", {"filter": "reverb"}),
        ("mic_advanced.configure", {"filter": ["off"]}),
        ("mic_advanced.configure", {"mute": True}),
        ("mic_advanced.monitor", {}),
        ("mic_advanced.monitor", {"enabled": 1}),
        ("mic_advanced.monitor", {"enabled": "yes"}),
        ("mic_advanced.monitor", {"enabled": True, "gain": 3}),
        ("mic_advanced.record", {}),
        ("mic_advanced.record", {"action": "toggle"}),
        ("mic_advanced.record", {"action": ["start"]}),
        ("mic_advanced.record", {"action": "start", "extra": 1}),
    ]

    def test_state_view(self):
        out = self.assertOutput(self.call(self.STATE_CAP, {}))
        self.assertEqual(out["backend"], "synthetic")
        self.assertEqual(out["real_backend"], "unsupported")
        self.assertEqual(out["reason"], "needs_human_validation")
        self.assertEqual({k: out[k] for k in ("device", "gain", "filter", "monitor",
                                              "recording", "indicator")},
                         {"device": "synthetic-mic-0", "gain": 50, "filter": "off",
                          "monitor": False, "recording": False, "indicator": False})
        self.assertNotIn("base", out)

    def test_configure_gain_is_verified(self):
        out = self.assertOutput(self.call(self.CONFIGURE_CAP, {"gain": 70}))
        self.assertEqual(out["gain"], 70)
        self.assertIs(out["verified"], True)
        self.assertEqual(self.world.mic["gain"], 70)

    def test_configure_gain_bounds_0_and_100(self):
        for gain in (0, 100):
            with self.subTest(gain=gain):
                out = self.assertOutput(self.call(self.CONFIGURE_CAP, {"gain": gain}))
                self.assertEqual(out["gain"], gain)

    def test_configure_each_filter_and_both_keys(self):
        for filt in ("off", "noise_gate", "highpass"):
            with self.subTest(filter=filt):
                out = self.assertOutput(self.call(self.CONFIGURE_CAP, {"filter": filt}))
                self.assertEqual(out["filter"], filt)
                self.assertIs(out["verified"], True)
        out = self.assertOutput(self.call(self.CONFIGURE_CAP,
                                          {"gain": 30, "filter": "noise_gate"}))
        self.assertEqual((out["gain"], out["filter"]), (30, "noise_gate"))
        self.assertIs(out["verified"], True)

    def test_configure_unverified_reports_false(self):
        self.world.stuck = True
        out = self.assertOutput(self.call(self.CONFIGURE_CAP, {"gain": 10}))
        self.assertIs(out["verified"], False)
        self.assertEqual(out["gain"], 50)

    def test_monitor_enable_and_disable(self):
        out = self.assertOutput(self.call(self.MONITOR_CAP, {"enabled": True}))
        self.assertIs(out["monitor"], True)
        self.assertIs(out["verified"], True)
        out = self.assertOutput(self.call(self.MONITOR_CAP, {"enabled": False}))
        self.assertIs(out["monitor"], False)
        self.assertIs(out["verified"], True)

    def test_record_start_shows_indicator_in_the_result(self):
        out = self.assertOutput(self.call(self.RECORD_CAP, {"action": "start"}))
        self.assertEqual(out["action"], "start")
        self.assertIs(out["recording"], True)
        self.assertIs(out["indicator"], True)
        self.assertIs(out["verified"], True)
        self.assertEqual([s for s, _ in self.sim.calls],
                         ["synthetic.mic.record_start", "synthetic.mic.state"])

    def test_record_stop_clears_recording_and_indicator(self):
        self.assertOutput(self.call(self.RECORD_CAP, {"action": "start"}))
        out = self.assertOutput(self.call(self.RECORD_CAP, {"action": "stop"}))
        self.assertIs(out["recording"], False)
        self.assertIs(out["indicator"], False)
        self.assertIs(out["verified"], True)

    def test_record_without_consent_is_permission_denied(self):
        self.sim = HostSim(self.plugin, self.world, self.AREA, grants=())
        self.assertError(self.call(self.RECORD_CAP, {"action": "start"}), "permission_denied")
        self.assertIs(self.world.mic["recording"], False)

    def test_recording_without_indicator_is_never_reported(self):
        self.world.no_indicator = True
        self.assertError(self.call(self.RECORD_CAP, {"action": "start"}), "plugin_error")

    def test_state_with_recording_but_no_indicator_is_plugin_error(self):
        self.world.mic["recording"] = True
        self.assertError(self.call(self.STATE_CAP, {}), "plugin_error")

    def test_host_permission_error_on_configure_passes_through(self):
        self.world.fault = "permission_denied"
        self.assertError(self.call(self.CONFIGURE_CAP, {"gain": 1}), "permission_denied")


class CameraTest(HostChecks, FixtureCase):
    PLUGIN_ID = "camera_gesture"
    AREA = "camera"
    GRANTS = ("camera_capture",)
    CAPS = ["camera_gesture.state", "camera_gesture.optin", "camera_gesture.capture",
            "camera_gesture.gestures"]
    STATE_CAP = "camera_gesture.state"
    OPTIN_CAP = "camera_gesture.optin"
    CAPTURE_CAP = "camera_gesture.capture"
    GESTURES_CAP = "camera_gesture.gestures"
    SAMPLE_ACTIONS = [
        ("camera_gesture.optin", {"enabled": True}),
        ("camera_gesture.capture", {}),
        ("camera_gesture.gestures", {}),
        ("camera_gesture.optin", {"enabled": False}),
    ]
    INVALID = [
        ("camera_gesture.state", {"x": 1}),
        ("camera_gesture.optin", {}),
        ("camera_gesture.optin", {"enabled": "yes"}),
        ("camera_gesture.optin", {"enabled": 1}),
        ("camera_gesture.optin", {"enabled": True, "x": 1}),
        ("camera_gesture.capture", {"frame": 1}),
        ("camera_gesture.capture", None),
        ("camera_gesture.gestures", {"all": True}),
    ]

    def optin(self, enabled=True):
        return self.assertOutput(self.call(self.OPTIN_CAP, {"enabled": enabled}))

    def test_default_is_opted_out(self):
        out = self.assertOutput(self.call(self.STATE_CAP, {}))
        self.assertEqual(set(out), {"backend", "real_backend", "reason", "opt_in", "indicator",
                                    "frame_seq", "gesture"})
        self.assertEqual(out["backend"], "synthetic")
        self.assertEqual(out["real_backend"], "unsupported")
        self.assertIs(out["opt_in"], False)
        self.assertIs(out["indicator"], False)
        self.assertEqual(out["frame_seq"], 0)
        self.assertIsNone(out["gesture"])

    def test_capture_without_opt_in_is_refused(self):
        self.assertError(self.call(self.CAPTURE_CAP, {}), "opt_in_required")
        self.assertEqual(self.world.camera["frame_seq"], 0)

    def test_gestures_without_opt_in_is_refused(self):
        self.assertError(self.call(self.GESTURES_CAP, {}), "opt_in_required")

    def test_optin_turns_the_indicator_on_and_is_verified(self):
        out = self.optin(True)
        self.assertIs(out["opt_in"], True)
        self.assertIs(out["indicator"], True)
        self.assertIs(out["verified"], True)
        self.assertIs(self.world.camera["indicator"], True)

    def test_capture_after_opt_in_returns_counters_only(self):
        self.optin(True)
        out = self.assertOutput(self.call(self.CAPTURE_CAP, {}))
        self.assertEqual(set(out), {"backend", "real_backend", "reason", "opt_in", "indicator",
                                    "frame_seq"})
        self.assertEqual(out["frame_seq"], 1)
        self.assertIs(out["opt_in"], True)

    def test_gestures_after_opt_in_come_from_the_world(self):
        self.optin(True)
        out = self.assertOutput(self.call(self.GESTURES_CAP, {}))
        self.assertEqual(out["gestures"], ["wave", "thumbs_up"])
        self.assertEqual(out["backend"], "synthetic")

    def test_gesture_list_bound_is_plugin_error(self):
        self.optin(True)
        self.world.gestures = ["g%d" % i for i in range(17)]
        self.assertError(self.call(self.GESTURES_CAP, {}), "plugin_error")

    def test_optout_clears_frames_and_indicator(self):
        self.optin(True)
        self.assertOutput(self.call(self.CAPTURE_CAP, {}))
        self.assertOutput(self.call(self.CAPTURE_CAP, {}))
        out = self.optin(False)
        self.assertIs(out["opt_in"], False)
        self.assertIs(out["indicator"], False)
        self.assertEqual(out["frame_seq"], 0)
        self.assertIs(out["verified"], True)
        self.assertError(self.call(self.CAPTURE_CAP, {}), "opt_in_required")

    def test_state_reports_gesture_from_the_world(self):
        self.world.camera.update({"opt_in": True, "indicator": True, "gesture": "wave"})
        out = self.assertOutput(self.call(self.STATE_CAP, {}))
        self.assertEqual(out["gesture"], "wave")

    def test_state_rejects_an_invalid_gesture_id(self):
        self.world.camera["gesture"] = "Wave!"
        self.assertError(self.call(self.STATE_CAP, {}), "plugin_error")

    def test_indicator_must_equal_opt_in(self):
        self.world.camera.update({"opt_in": False, "indicator": True})
        self.assertError(self.call(self.STATE_CAP, {}), "plugin_error")

    def test_optin_without_grant_is_permission_denied(self):
        self.sim = HostSim(self.plugin, self.world, self.AREA, grants=())
        self.assertError(self.call(self.OPTIN_CAP, {"enabled": True}), "permission_denied")
        self.assertIs(self.world.camera["opt_in"], False)

    def test_capture_host_error_passes_through(self):
        self.optin(True)
        self.world.fault = "opt_in_required"
        self.assertError(self.call(self.CAPTURE_CAP, {}), "opt_in_required")


class DisplayTest(FixtureCase):
    PLUGIN_ID = "display_manipulate"
    AREA = None
    GRANTS = ()
    CAPS = ["display_manipulate.status"]
    EXPECTED = {
        "supported": False,
        "state": "UNSUPPORTED",
        "reason": "no_compositor_api_in_environment",
        "note": "overlay/captura não é manipulação de saída",
    }

    def test_hello_lists_only_status(self):
        self.assertIs(self.hello.get("ok"), True)
        self.assertEqual(self.hello["capabilities"], self.CAPS)

    def test_status_is_the_unsupported_object(self):
        self.assertEqual(self.assertOutput(self.call("display_manipulate.status", {})),
                         self.EXPECTED)

    def test_status_is_stable_across_calls(self):
        first = self.assertOutput(self.call("display_manipulate.status", {}))
        second = self.assertOutput(self.call("display_manipulate.status", {}))
        self.assertEqual(first, second)

    def test_status_rejects_any_input(self):
        for inp in ({"x": 1}, [], None, "status"):
            with self.subTest(inp=inp):
                self.assertError(self.call("display_manipulate.status", inp), "invalid_input")

    def test_no_manipulation_capability_exists(self):
        for capability in ("display_manipulate.set", "display_manipulate.act",
                           "display_manipulate.overlay", "display_manipulate.capture"):
            with self.subTest(capability=capability):
                self.assertError(self.call(capability, {}), "unknown_capability")

    def test_no_host_call_ever(self):
        self.call("display_manipulate.status", {})
        self.call("display_manipulate.status", {"x": 1})
        self.assertEqual(self.sim.calls, [])


class CatalogTest(unittest.TestCase):
    MINE = ("audio_advanced", "mic_advanced", "camera_gesture", "display_manipulate")
    PERMISSIONS = {
        "screen_observe": ["screen_observe"],
        "computer_control": ["input_control"],
        "audio_advanced": ["audio_route"],
        "mic_advanced": ["mic_config"],
        "camera_gesture": ["camera_capture"],
        "display_manipulate": ["display_manipulate"],
    }
    CAPABILITIES = {
        "screen_observe": ["screen_observe.capture", "screen_observe.status"],
        "computer_control": ["computer_control.tree", "computer_control.act",
                             "computer_control.status"],
        "audio_advanced": ["audio_advanced.state", "audio_advanced.act"],
        "mic_advanced": ["mic_advanced.state", "mic_advanced.configure", "mic_advanced.monitor",
                         "mic_advanced.record"],
        "camera_gesture": ["camera_gesture.state", "camera_gesture.optin",
                           "camera_gesture.capture", "camera_gesture.gestures"],
        "display_manipulate": ["display_manipulate.status"],
    }

    @classmethod
    def setUpClass(cls):
        cls.script_result = subprocess.run([PYTHON, "-I", str(CATALOG_SCRIPT)], cwd="/",
                                 capture_output=True, text=True, check=False)
        cls.catalog = json.loads(C4_CATALOG.read_text(encoding="utf-8"))
        cls.by_id = {plugin["plugin_id"]: plugin for plugin in cls.catalog["plugins"]}

    def test_script_runs_clean(self):
        self.assertEqual(self.script_result.returncode, 0, self.script_result.stderr)
        self.assertEqual(self.script_result.stderr, "")

    def test_my_four_plugins_are_present(self):
        for plugin_id in self.MINE:
            with self.subTest(plugin_id=plugin_id):
                self.assertIn(plugin_id, self.by_id)

    def test_every_present_plugin_matches_its_doc_entry(self):
        c0_keys = set(json.loads(C0_CATALOG.read_text(encoding="utf-8"))["plugins"][0])
        for plugin_id, plugin in self.by_id.items():
            with self.subTest(plugin_id=plugin_id):
                self.assertEqual(set(plugin), c0_keys)
                self.assertEqual(plugin["runtime"], "python3_script")
                self.assertEqual(plugin["entrypoint"], "bin/%s.py" % plugin_id)
                self.assertEqual(plugin["semver"], "1.0.0")
                self.assertEqual(plugin["api_version"], 1)
                self.assertIsNone(plugin["signature"])
                self.assertEqual(plugin["permissions"], self.PERMISSIONS[plugin_id])
                self.assertEqual(plugin["capabilities"], self.CAPABILITIES[plugin_id])

    def test_capability_ids_follow_c0_rules(self):
        import re
        cap_re = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
        reserved = ("base", "core", "system", "safety", "llm", "screen", "computer", "audio",
                    "mic", "camera", "display")
        for plugin_id, plugin in self.by_id.items():
            for cap in plugin["capabilities"]:
                with self.subTest(cap=cap):
                    self.assertRegex(cap, cap_re)
                    self.assertLessEqual(len(cap), 64)
                    self.assertTrue(cap.startswith(plugin_id + "."))
                    self.assertNotIn(cap.split(".")[0], reserved)
            self.assertLessEqual(len(plugin["capabilities"]), 8)

    def test_binary_digest_and_size_match_the_payload(self):
        for plugin_id, plugin in self.by_id.items():
            with self.subTest(plugin_id=plugin_id):
                data = (C4 / (plugin_id + ".py")).read_bytes()
                binary = plugin["binaries"][0]
                self.assertEqual(binary["target"], "linux_x86_64")
                self.assertEqual(binary["size"], len(data))
                self.assertEqual(binary["sha256"], hashlib.sha256(data).hexdigest())
                self.assertIn("/c4-v1/", binary["url"])

    def test_no_secret_material_in_catalog(self):
        self.assertNotIn("sk-", C4_CATALOG.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
