#!/usr/bin/env python3
"""Offline tests for scripts/perception_worker.py (WP-12). No desktop side effects.

Covers: catalog <-> worker agreement, protocol (hello, dispatch, unknown capability, EOF/shutdown), strict input
refusals that happen before any backend is touched, read-only status calls, and pure helpers (key codes,
PNG header, WAV metering, PipeWire metadata parsing). Live desktop checks are in scripts/perception_live.py.

Run: python3 -I scripts/test_perception_worker.py   (stdlib unittest; PyGObject optional)
"""
import hashlib
import importlib.util
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / "scripts" / "perception_worker.py"
CATALOG = ROOT / "tests" / "fixtures" / "hub-perception.json"


def load_worker():
    spec = importlib.util.spec_from_file_location("perception_worker", WORKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PW = load_worker()


class Worker:
    """One worker process speaking the C0 JSON-lines protocol."""

    def __init__(self, plugin_id=None):
        self.proc = subprocess.Popen([sys.executable, "-I", str(WORKER)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.seq = 0
        if plugin_id is not None:
            self.hello(plugin_id)

    def send(self, obj):
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def read(self):
        line = self.proc.stdout.readline()
        return json.loads(line) if line else None

    def hello(self, plugin_id):
        self.seq += 1
        self.send({"v": 1, "id": self.seq, "op": "hello", "plugin_id": plugin_id})
        return self.read()

    def invoke(self, capability, inp=None):
        self.seq += 1
        self.send({"v": 1, "id": self.seq, "op": "invoke", "capability": capability,
                   "input": {} if inp is None else inp})
        return self.read()

    def close(self):
        try:
            self.send({"v": 1, "op": "shutdown"})
        except (OSError, ValueError):
            pass
        try:
            code = self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            code = None
        err = self.proc.stderr.read()
        for pipe in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                pipe.close()
            except OSError:
                pass
        return code, err


class CatalogAgreement(unittest.TestCase):
    def test_catalog_lists_seven_plugins_with_one_payload(self):
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        ids = [p["plugin_id"] for p in data["plugins"]]
        self.assertEqual(sorted(ids), sorted(PW.PLUGINS))
        sha = hashlib.sha256(WORKER.read_bytes()).hexdigest()
        for entry in data["plugins"]:
            self.assertEqual(entry["binaries"][0]["sha256"], sha, entry["plugin_id"])
            self.assertEqual(entry["binaries"][0]["size"], WORKER.stat().st_size)

    def test_catalog_capabilities_equal_worker_table(self):
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        for entry in data["plugins"]:
            self.assertEqual(entry["capabilities"], PW.PLUGINS[entry["plugin_id"]], entry["plugin_id"])
            self.assertLessEqual(len(entry["capabilities"]), 8)
            for cap in entry["capabilities"]:
                self.assertTrue(cap.startswith(entry["plugin_id"] + "."))

    def test_every_worker_capability_has_a_handler(self):
        for caps in PW.PLUGINS.values():
            for cap in caps:
                self.assertIn(cap, PW.HANDLERS)
        self.assertEqual(set(PW.HANDLERS), {c for caps in PW.PLUGINS.values() for c in caps})


class Protocol(unittest.TestCase):
    def test_hello_answers_plugin_capabilities(self):
        w = Worker()
        reply = w.hello("camera_gesture")
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["plugin_id"], "camera_gesture")
        self.assertEqual(reply["capabilities"], PW.PLUGINS["camera_gesture"])
        code, _err = w.close()
        self.assertEqual(code, 0)

    def test_unknown_plugin_is_refused(self):
        w = Worker()
        self.assertFalse(w.hello("not_a_plugin")["ok"])
        w.close()

    def test_invoke_before_hello_is_unknown_capability(self):
        w = Worker()
        reply = w.invoke("screen_observe.status")
        self.assertEqual(reply, {"id": 1, "ok": False, "error": "unknown_capability"})
        w.close()

    def test_capability_of_another_plugin_is_refused(self):
        w = Worker("screen_observe")
        reply = w.invoke("camera_gesture.state")
        self.assertEqual(reply["error"], "unknown_capability")
        w.close()

    def test_unsupported_version_and_unknown_op(self):
        w = Worker("screen_observe")
        w.send({"v": 2, "id": 9, "op": "invoke", "capability": "screen_observe.status", "input": {}})
        self.assertEqual(w.read(), {"id": 9, "ok": False, "error": "unsupported_version"})
        w.send({"v": 1, "id": 10, "op": "frobnicate"})
        self.assertEqual(w.read(), {"id": 10, "ok": False, "error": "unknown_op"})
        w.close()

    def test_eof_exits_cleanly(self):
        w = Worker("screen_observe")
        w.proc.stdin.close()
        self.assertEqual(w.proc.wait(timeout=30), 0)
        w.close()


class StrictInput(unittest.TestCase):
    """Each refusal below happens before any backend runs: no screen, camera, audio or display change."""

    def test_no_input_capability_rejects_fields(self):
        w = Worker("screen_observe")
        self.assertEqual(w.invoke("screen_observe.status", {"x": 1})["error"], "invalid_input")
        w.close()

    def test_camera_requires_opt_in_and_typed_optin(self):
        w = Worker("camera_gesture")
        self.assertEqual(w.invoke("camera_gesture.capture")["error"], "opt_in_required")
        self.assertEqual(w.invoke("camera_gesture.optin", {"enabled": "yes"})["error"], "invalid_input")
        self.assertEqual(w.invoke("camera_gesture.optin", {"enabled": True, "extra": 1})["error"],
                         "invalid_input")
        self.assertEqual(w.invoke("camera_gesture.gestures")["output"]["supported"], False)
        self.assertEqual(w.invoke("camera_gesture.optin", {"enabled": False})["output"]["opt_in"], False)
        w.close()

    def test_display_refuses_bad_values_and_names(self):
        w = Worker("display_manipulate")
        bad = [
            {"output": "DP-1; rm", "op": "scale", "value": 125},
            {"output": "DP-1", "op": "scale", "value": 130},
            {"output": "DP-1", "op": "brightness", "value": 5},
            {"output": "DP-1", "op": "rotate", "value": 90},
            {"output": "DP-1", "op": "scale"},
        ]
        for inp in bad:
            self.assertEqual(w.invoke("display_manipulate.act", inp)["error"], "invalid_input", inp)
        self.assertEqual(w.invoke("display_manipulate.restore")["output"]["restored"], 0)
        w.close()

    def test_audio_refuses_sinks_as_apps_and_unknown_routes(self):
        w = Worker("audio_advanced")
        self.assertEqual(w.invoke("audio_advanced.act", {"kind": "route", "sink": 999999})["error"],
                         "unknown_route")
        self.assertEqual(w.invoke("audio_advanced.act", {"kind": "app_volume", "stream": 999999,
                                                         "volume": 10})["error"], "unknown_app")
        self.assertEqual(w.invoke("audio_advanced.act", {"kind": "eq", "stream": 1})["error"],
                         "invalid_input")
        w.close()

    def test_computer_refuses_stale_epoch_and_bad_kind(self):
        w = Worker("computer_control")
        self.assertEqual(w.invoke("computer_control.act", {"kind": "type", "epoch": 0,
                                                           "text": "a"})["error"], "stale_screen")
        self.assertEqual(w.invoke("computer_control.act", {"kind": "click", "epoch": 1})["error"],
                         "invalid_input")
        self.assertEqual(w.invoke("computer_control.act", {"kind": "type", "epoch": 1,
                                                           "text": "x" * 65})["error"], "invalid_input")
        w.close()

    def test_mic_refusals_and_refused_monitor(self):
        w = Worker("mic_advanced")
        self.assertEqual(w.invoke("mic_advanced.configure", {"gain": 151})["error"], "invalid_input")
        self.assertEqual(w.invoke("mic_advanced.record", {"action": "stop"})["error"], "not_recording")
        self.assertEqual(w.invoke("mic_advanced.record", {"action": "pause"})["error"], "invalid_input")
        monitor = w.invoke("mic_advanced.monitor", {})["output"]
        self.assertEqual(monitor["supported"], False)
        self.assertIn("speakers", monitor["reason"])
        w.close()

    def test_shortcut_refuses_bad_ids_and_triggers_before_any_portal(self):
        w = Worker("shortcut_global")
        cases = [
            {"id": "Bad Id", "description": "x", "trigger": "CTRL+G"},
            {"id": "ok_id", "description": "", "trigger": "CTRL+G"},
            {"id": "ok_id", "description": "x", "trigger": "CTRL+X+Y"},
            {"id": "ok_id", "description": "x", "trigger": "F99"},
            {"id": "ok_id", "description": "x", "trigger": "HYPER+G"},
        ]
        for inp in cases:
            self.assertEqual(w.invoke("shortcut_global.bind", inp)["error"], "invalid_input", inp)
        self.assertEqual(w.invoke("shortcut_global.events")["output"]["events"], [])
        w.close()


class StatusCalls(unittest.TestCase):
    """Status and state reads touch no device state (they may read the portal, PipeWire, sysfs, kscreen)."""

    def test_status_shapes(self):
        for plugin, cap, keys in (
            ("screen_observe", "screen_observe.status", {"backend", "available", "reason"}),
            ("computer_control", "computer_control.status", {"backend", "available", "reason", "input_session"}),
            ("audio_advanced", "audio_advanced.state", {"backend", "default_sink", "sinks", "streams"}),
            ("mic_advanced", "mic_advanced.state", {"backend", "source", "gain", "muted", "recording", "indicator"}),
            ("camera_gesture", "camera_gesture.state", {"backend", "device", "present", "opt_in", "indicator"}),
            ("display_manipulate", "display_manipulate.status", {"backend", "outputs", "undo_pending"}),
            ("shortcut_global", "shortcut_global.status", {"backend", "available", "reason", "bound"}),
        ):
            w = Worker(plugin)
            reply = w.invoke(cap)
            self.assertTrue(reply["ok"], (plugin, reply))
            self.assertTrue(keys <= set(reply["output"]), (plugin, reply["output"]))
            w.close()


class PureHelpers(unittest.TestCase):
    def test_qt_key_sequences(self):
        self.assertEqual(PW._qt_key_sequence("CTRL+ALT+G"), 0x04000000 | 0x08000000 | 0x47)
        self.assertEqual(PW._qt_key_sequence("F5"), 0x01000034)
        self.assertEqual(PW._qt_key_sequence("SHIFT+1"), 0x02000000 | 0x31)
        self.assertEqual(PW._qt_key_sequence("space"), 0x20)
        for bad in ("F13", "CTRL+", "X+G", "CTRL+GG"):
            with self.assertRaises(PW._Fail):
                PW._qt_key_sequence(bad)

    def test_keysyms(self):
        self.assertEqual(PW._keysym_for("a"), 0x61)
        self.assertEqual(PW._keysym_for("é"), 0xe9)
        self.assertEqual(PW._keysym_for("€"), 0x01000000 + 0x20AC)
        self.assertEqual(PW.KEYSYMS["Return"], 0xff0d)

    def test_png_size_and_refusal(self):
        header = PW.PNG_SIG + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 1920, 1080)
        self.assertEqual(PW._png_size(header + b"\x00" * 8), (1920, 1080))
        with self.assertRaises(PW._Fail):
            PW._png_size(b"GIF89a" + b"\x00" * 20)

    def test_wav_meter_on_known_tone(self):
        rate = 16000
        samples = [int(10000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(rate)]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tone.wav")
            with wave.open(path, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(rate)
                wav.writeframes(struct.pack("<%dh" % len(samples), *samples))
            meter = PW._meter_wav(path)
        self.assertEqual(meter["samples"], rate)
        self.assertEqual(meter["seconds"], 1.0)
        self.assertEqual(meter["peak"], round(10000 * 100 / 32768))
        self.assertEqual(meter["rms"], round(10000 / math.sqrt(2) * 100 / 32768))

    def test_pipewire_defaults_and_nodes(self):
        objects = [
            {"type": "PipeWire:Interface:Metadata", "props": {"metadata.name": "default"},
             "metadata": [{"key": "default.audio.sink", "value": {"name": "sinkA"}},
                          {"key": "default.audio.source", "value": {"name": "srcB"}}]},
            {"type": "PipeWire:Interface:Node", "id": 7,
             "info": {"props": {"media.class": "Audio/Sink", "node.name": "sinkA"}}},
            {"type": "PipeWire:Interface:Node", "id": 8,
             "info": {"props": {"media.class": "Stream/Output/Audio", "application.name": "app"}}},
        ]
        self.assertEqual(PW._pw_defaults(objects), ("sinkA", "srcB"))
        self.assertEqual([i for i, _p in PW._pw_nodes(objects, "Audio/Sink")], [7])
        self.assertEqual([i for i, _p in PW._pw_nodes(objects, "Stream/Output/Audio")], [8])

    def test_clean_strips_controls_and_truncates_bytes(self):
        self.assertEqual(PW._clean("a\x00b\nc", 10), "abc")
        self.assertEqual(len(PW._clean("ã" * 100, 5).encode("utf-8")) <= 5, True)

    def test_output_limit_constant_matches_c0(self):
        self.assertEqual(PW.MAX_OUTPUT, 8192)
        self.assertEqual(PW.MAX_LINE, 65536)


if __name__ == "__main__":
    unittest.main(verbosity=2)
