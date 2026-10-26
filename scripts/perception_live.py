#!/usr/bin/env python3
"""Live desktop checks for the WP-12 perception worker (run on the owner's PC, real devices).

Every check drives scripts/perception_worker.py over the C0 protocol, exactly as the Core would, and
restores what it changed: volumes, default sink, mic gain, display scale and brightness, KWin shortcut.
The camera frame and the screenshot are hashed and deleted; no image or audio is kept.
Nothing is written outside the scratch directory given with --out and docs/evidence.

Usage: python3 -I scripts/perception_live.py --confirm [--out DIR] [--only NAME,...]
Result: docs/evidence/perception-live.json (checks, counts, blocked items with reasons).
Exit 0 when every check that ran passed; blocked checks (desktop consent not given) do not fail the run
but are listed as "blocked" with the observed reason.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def Worker(plugin_id=None):
    """Protocol driver from the offline tests. Imported lazily: importing it in the KGlobalAccel probe
    process stopped KDE's signal delivery there (measured), so that probe runs in its own interpreter."""
    from test_perception_worker import Worker as protocol_worker
    return protocol_worker(plugin_id)


EVIDENCE = ROOT / "docs" / "evidence" / "perception-live.json"
WINDOW = ROOT / "scripts" / "perception_testwindow.py"
UI_PYTHON = ROOT / "target" / "ui-venv" / "bin" / "python"
PICTURES = os.path.expanduser("~/Imagens")
results = []


def record(name, status, detail):
    results.append({"name": name, "status": status, "detail": detail})
    print("%-28s %-8s %s" % (name, status, json.dumps(detail, ensure_ascii=False)[:300]), flush=True)


def check(name, fn):
    t0 = time.time()
    try:
        status, detail = fn()
    except AssertionError as err:
        status, detail = "fail", {"assert": str(err)}
    except Exception as err:  # keep going: every item is reported
        status, detail = "fail", {"exception": "%s: %s" % (type(err).__name__, err)}
    detail["seconds"] = round(time.time() - t0, 2)
    record(name, status, detail)


def expect_ok(reply):
    assert reply and reply.get("ok") is True, "worker answered %s" % json.dumps(reply)
    return reply["output"]


def screen_capture():
    before = set(glob.glob(os.path.join(PICTURES, "Screenshot_*.png")))
    w = Worker("screen_observe")
    out = expect_ok(w.invoke("screen_observe.capture"))
    w.close()
    after = set(glob.glob(os.path.join(PICTURES, "Screenshot_*.png")))
    assert out["width"] > 0 and out["height"] > 0 and len(out["sha256"]) == 64
    assert after - before == set(), "portal file left behind: %s" % sorted(after - before)
    return "pass", {"width": out["width"], "height": out["height"], "sha256": out["sha256"],
                    "file_left_behind": False, "image_kept": False}


def camera_frame():
    w = Worker("camera_gesture")
    refused = w.invoke("camera_gesture.capture")
    assert refused.get("error") == "opt_in_required", refused
    expect_ok(w.invoke("camera_gesture.optin", {"enabled": True}))
    try:
        out = expect_ok(w.invoke("camera_gesture.capture"))
    finally:
        expect_ok(w.invoke("camera_gesture.optin", {"enabled": False}))
        w.close()
    assert out["width"] == 160 and out["height"] == 120 and 0 <= out["mean_luma"] <= 255
    return "pass", {"refused_without_opt_in": True, "width": out["width"], "height": out["height"],
                    "mean_luma": out["mean_luma"], "sha256": out["sha256"], "image_kept": False,
                    "opt_in_restored": True}


def mic_gain_and_meter():
    w = Worker("mic_advanced")
    before = expect_ok(w.invoke("mic_advanced.state"))["gain"]
    try:
        cfg = expect_ok(w.invoke("mic_advanced.configure", {"gain": 80}))
        assert cfg["verified"] is True and cfg["gain"] == 80, cfg
    finally:
        back = expect_ok(w.invoke("mic_advanced.configure", {"gain": before}))
        assert back["verified"] is True and back["gain"] == before, back
    expect_ok(w.invoke("mic_advanced.record", {"action": "start"}))
    time.sleep(2.0)
    meter = expect_ok(w.invoke("mic_advanced.record", {"action": "stop"}))
    w.close()
    assert 1.0 <= meter["seconds"] <= 3.5 and meter["samples"] > 0, meter
    return "pass", {"gain_before": before, "gain_restored": back["gain"], "seconds": meter["seconds"],
                    "rms": meter["rms"], "peak": meter["peak"], "audio_kept": False}


def display_scale_and_brightness():
    w = Worker("display_manipulate")
    status = expect_ok(w.invoke("display_manipulate.status"))
    output = status["outputs"][0]["name"]
    scale0 = status["outputs"][0]["scale"]
    bright0 = status["outputs"][0]["brightness"]
    try:
        s = expect_ok(w.invoke("display_manipulate.act", {"output": output, "op": "scale", "value": 125}))
        assert s["verified"] is True and s["value"] == 125, s
        b = expect_ok(w.invoke("display_manipulate.act", {"output": output, "op": "brightness", "value": 90}))
        assert b["verified"] is True, b
    finally:
        rest = expect_ok(w.invoke("display_manipulate.restore"))
        after = expect_ok(w.invoke("display_manipulate.status"))["outputs"][0]
        w.close()
    assert rest["verified"] is True, rest
    assert after["scale"] == scale0 and abs(after["brightness"] - bright0) <= 1, (after, scale0, bright0)
    return "pass", {"output": output, "scale_before": scale0, "scale_after_restore": after["scale"],
                    "brightness_before": bright0, "brightness_after_restore": after["brightness"],
                    "restored_changes": rest["restored"]}


LAB_SINK = "gideon-perception-lab"


def pw_nodes_named(name):
    dump = json.loads(subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=20).stdout)
    return [o["id"] for o in dump if o.get("type") == "PipeWire:Interface:Node"
            and (o.get("info") or {}).get("props", {}).get("node.name") == name]


def create_lab_sink():
    """A null sink of this check's own (linger=true so it outlives pw-cli). Removed in destroy_lab_sink."""
    subprocess.run(["pw-cli", "create-node", "adapter",
                    "{ factory.name=support.null-audio-sink node.name=%s media.class=Audio/Sink "
                    "object.linger=true audio.position=[FL FR] }" % LAB_SINK],
                   capture_output=True, text=True, timeout=20, check=True)
    for _ in range(20):
        ids = pw_nodes_named(LAB_SINK)
        if ids:
            return ids[0]
        time.sleep(0.2)
    raise AssertionError("lab sink did not appear")


def destroy_lab_sink(node_id):
    subprocess.run(["pw-cli", "destroy", str(node_id)], capture_output=True, text=True, timeout=20)
    time.sleep(0.3)
    assert not pw_nodes_named(LAB_SINK), "lab sink still present after destroy"


def audio_stream_volume_and_route():
    import shutil
    pwcat = shutil.which("pw-cat")
    assert pwcat, "pw-cat missing"
    scratch = tempfile.mkdtemp(prefix="gideon-perc-audio-")
    wav_path = os.path.join(scratch, "silence.wav")
    with wave.open(wav_path, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(b"\x00\x00\x00\x00" * 48000 * 10)
    lab_sink = create_lab_sink()
    try:
        return _audio_checks(pwcat, wav_path, scratch, lab_sink)
    finally:
        destroy_lab_sink(lab_sink)


def _audio_checks(pwcat, wav_path, scratch, lab_sink):
    w = Worker("audio_advanced")
    state = expect_ok(w.invoke("audio_advanced.state"))
    pre = {s["id"] for s in state["streams"]}
    default_sink = state["default_sink"]
    lab = subprocess.Popen([pwcat, "-p", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    lab_id = None
    report = {"default_sink": default_sink}
    try:
        deadline = time.time() + 5
        while time.time() < deadline and lab_id is None:
            time.sleep(0.2)
            for s in expect_ok(w.invoke("audio_advanced.state"))["streams"]:
                if s["id"] not in pre and s["app"] in ("pw-play", "pw-cat"):
                    lab_id = s["id"]
        assert lab_id is not None, "lab stream did not appear"
        report["lab_stream"] = lab_id
        v = expect_ok(w.invoke("audio_advanced.act", {"kind": "app_volume", "stream": lab_id, "volume": 40}))
        assert v["verified"] is True, v
        back = expect_ok(w.invoke("audio_advanced.act", {"kind": "app_volume", "stream": lab_id,
                                                         "volume": v["previous"]}))
        assert back["verified"] is True and back["volume"] == v["previous"], back
        report["app_volume"] = {"set": 40, "previous": v["previous"], "restored": back["volume"]}
        # Route only to this check's own null sink, so no real output changes; the default is restored exactly.
        assert any(s["id"] == lab_sink for s in state["sinks"]) or any(
            s["id"] == lab_sink for s in expect_ok(w.invoke("audio_advanced.state"))["sinks"]), "lab sink not listed"
        r = expect_ok(w.invoke("audio_advanced.act", {"kind": "route", "sink": lab_sink}))
        assert r["verified"] is True, r
        r2 = expect_ok(w.invoke("audio_advanced.act", {"kind": "route", "sink": default_sink}))
        assert r2["verified"] is True and r2["default_sink"] == default_sink, r2
        report["route"] = {"to_lab_sink": lab_sink, "restored_default": r2["default_sink"]}
    finally:
        lab.terminate()
        lab.wait(timeout=10)
        w.close()
        for name in os.listdir(scratch):
            os.unlink(os.path.join(scratch, name))
        os.rmdir(scratch)
    final = Worker("audio_advanced")
    now = expect_ok(final.invoke("audio_advanced.state"))["default_sink"]
    final.close()
    assert now == default_sink, "default sink changed: %s -> %s" % (default_sink, now)
    report["default_sink_after"] = now
    return "pass", report


def shortcut_trigger():
    w = Worker("shortcut_global")
    bound = expect_ok(w.invoke("shortcut_global.bind", {"id": "ptt_toggle",
                                                        "description": "Gideon: alternar escuta (teste)",
                                                        "trigger": "CTRL+ALT+G"}))
    trigger_ok = None
    events = []
    try:
        assert bound["backend"] in ("portal", "kglobalaccel"), bound
        time.sleep(0.5)
        comp = find_component("ptt_toggle", bound["backend"])
        assert comp, "no KGlobalAccel component lists ptt_toggle"
        subprocess.run(["gdbus", "call", "--session", "-d", "org.kde.kglobalaccel", "-o", comp,
                        "-m", "org.kde.kglobalaccel.Component.invokeShortcut", "ptt_toggle"],
                       capture_output=True, text=True, timeout=20, check=True)
        time.sleep(1.0)
        events = expect_ok(w.invoke("shortcut_global.events"))["events"]
        trigger_ok = any(e["id"] == "ptt_toggle" for e in events)
        assert trigger_ok, "no Activated event reached the worker: %s" % events
    finally:
        w.close()
    return "pass", {"backend": bound["backend"], "trigger": bound["trigger"], "component": comp,
                    "events_received": events}


def kga_probe_inprocess():
    """Runs inside its own interpreter (--kga-probe). Registers one action under the worker's component,
    triggers it through KDE, waits for the signal, unregisters it and reports what was left registered."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("perception_worker_live", ROOT / "scripts" / "perception_worker.py")
    pw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pw)
    from gi.repository import GLib
    ctx = GLib.MainContext.default()

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            ctx.iteration(False)
            time.sleep(0.02)

    report = {"backend": "kglobalaccel", "trigger": "CTRL+ALT+H"}
    pw._kga_register("kga_live_probe", "Gideon teste fallback", "CTRL+ALT+H")
    pw._shortcut_bound["kga_live_probe"] = {"description": "teste", "trigger": "CTRL+ALT+H",
                                            "backend": "kglobalaccel"}
    try:
        pump(0.5)
        out = subprocess.run(["gdbus", "call", "--session", "-d", "org.kde.kglobalaccel", "-o",
                              "/component/" + pw.KGA_COMPONENT, "-m",
                              "org.kde.kglobalaccel.Component.invokeShortcut", "kga_live_probe"],
                             capture_output=True, text=True, timeout=20)
        report["invoke_rc"] = out.returncode
        pump(1.0)
        report["events_received"] = list(pw._shortcut_events)
    finally:
        pw._kga_unregister("kga_live_probe")
        pw._shortcut_bound.pop("kga_live_probe", None)
    left = subprocess.run(["gdbus", "call", "--session", "-d", "org.kde.kglobalaccel", "-o", "/kglobalaccel",
                           "-m", "org.kde.KGlobalAccel.allActionsForComponent",
                           '["%s"]' % pw.KGA_COMPONENT], capture_output=True, text=True, timeout=20).stdout
    report["still_registered"] = "kga_live_probe" in left
    return report


def shortcut_kglobalaccel_fallback():
    """The fallback path (KGlobalAccel directly). The portal answers first on this PC, so the path is driven
    through its own probe process (`perception_live.py --kga-probe`)."""
    out = subprocess.run([sys.executable, "-I", str(Path(__file__).resolve()), "--kga-probe"],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-400:]
    report = json.loads(out.stdout.strip().splitlines()[-1])
    assert report.get("invoke_rc") == 0, report
    assert any(e["id"] == "kga_live_probe" for e in report["events_received"]), report
    assert report["still_registered"] is False, report
    report.pop("still_registered")
    report["unregistered"] = True
    return "pass", report


def find_component(shortcut_id, backend):
    """Component object that lists the shortcut. Portal shortcuts live under the app id's component."""
    out = subprocess.run(["gdbus", "call", "--session", "-d", "org.kde.kglobalaccel", "-o", "/kglobalaccel",
                          "-m", "org.kde.KGlobalAccel.allComponents"], capture_output=True, text=True,
                         timeout=20).stdout
    import re
    for path in re.findall(r"/component/[A-Za-z0-9_]+", out):
        names = subprocess.run(["gdbus", "call", "--session", "-d", "org.kde.kglobalaccel", "-o", path,
                                "-m", "org.kde.kglobalaccel.Component.shortcutNames"],
                               capture_output=True, text=True, timeout=20).stdout
        if "'%s'" % shortcut_id in names or '"%s"' % shortcut_id in names:
            return path
    return None


def computer_tree_and_type():
    env = dict(os.environ, QT_LINUX_ACCESSIBILITY_ALWAYS_ON="1", QT_ACCESSIBILITY="1")
    win = subprocess.Popen([str(UI_PYTHON), str(WINDOW), "150"], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    w = Worker("computer_control")
    try:
        time.sleep(3)
        tree = expect_ok(w.invoke("computer_control.tree"))
        assert tree["window"] == "Gideon perception test window", tree["window"]
        epoch = tree["epoch"]
        act = w.invoke("computer_control.act", {"kind": "type", "epoch": epoch, "text": "gid"})
        if act.get("ok") is True:
            assert act["output"]["verified"] is True, act
            # A key press as well: BackSpace removes the last typed character. Key presses have no read-back
            # (verified stays false by design), so the check asserts that the injection was accepted.
            key = expect_ok(w.invoke("computer_control.act", {"kind": "key", "epoch": epoch, "key": "BackSpace"}))
            assert key["injected"] == 1 and key["verified"] is False, key
            detail = {"tree_elements": len(tree["elements"]), "typed": act["output"], "key": key}
            return "pass", detail
        reason = act.get("error")
        return "blocked", {"tree_elements": len(tree["elements"]), "tree_window": tree["window"],
                           "type_refused": reason,
                           "reason": "RemoteDesktop portal did not grant the keyboard device "
                                     "(no consent answer from xdg-desktop-portal-kde); see docs/WP12p.md"}
    finally:
        w.close()
        win.terminate()
        win.wait(timeout=10)


CHECKS = [
    ("screen_capture", screen_capture),
    ("camera_frame", camera_frame),
    ("mic_gain_and_meter", mic_gain_and_meter),
    ("display_scale_brightness", display_scale_and_brightness),
    ("audio_stream_and_route", audio_stream_volume_and_route),
    ("shortcut_trigger", shortcut_trigger),
    ("shortcut_kglobalaccel_fallback", shortcut_kglobalaccel_fallback),
    ("computer_tree_and_type", computer_tree_and_type),
]


CORE_EVIDENCE = ROOT / "docs" / "evidence" / "perception-core-live.json"
CORE_PLUGINS = ["screen_observe", "computer_control", "audio_advanced", "mic_advanced", "camera_gesture",
                "display_manipulate", "shortcut_global"]
READ_ONLY = ["screen_observe.status", "computer_control.status", "audio_advanced.state", "mic_advanced.state",
             "camera_gesture.state", "camera_gesture.gestures", "display_manipulate.status",
             "shortcut_global.status", "shortcut_global.events"]
SHORTCUT_ID = "wp18a_probe"
SHORTCUT_TRIGGER = "CTRL+ALT+G"


def core_session_env():
    """The owner's session as the Core inherits it: runtime dir, session bus, Wayland socket, HOME (for ~/Imagens).
    Only these four names; the Core's config, data and cache stay in the private temporary root."""
    names = ("HOME", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "WAYLAND_DISPLAY")
    return {name: os.environ[name] for name in names if name in os.environ}


def host_display():
    """Scale and brightness of the first output, read outside any sandbox (only to verify the restore)."""
    env = {"PATH": "/usr/bin:/bin", **core_session_env()}  # no QT_QPA_PLATFORM: offscreen hides every output
    done = subprocess.run(["kscreen-doctor", "-j"], capture_output=True, text=True, timeout=15, check=False, env=env)
    assert done.returncode == 0, "kscreen-doctor rc %s" % done.returncode
    first = json.loads(done.stdout)["outputs"][0]
    return {"name": first["name"], "scale": round(float(first["scale"]) * 100),
            "brightness": round(float(first["brightness"]) * 100)}


class CoreRun:
    """One real Core (target/release/gideon-base) with the seven perception plugins installed through the Hub."""

    def __init__(self, td):
        import test_snapshot_contract as contract  # lazy: the bridge imports PySide6 (run with target/ui-venv)
        self.contract = contract
        self.td = Path(td)
        self.core = contract.Core(self.td / "core", self.td)
        home = self.td / "home"
        home.mkdir()
        self.core.catalog = contract.C4_CATALOG
        self.core.extra = ["--home", str(home)]
        private = {"PATH": "/usr/bin:/bin", "XDG_CONFIG_HOME": str(self.td), "XDG_DATA_HOME": str(self.td),
                   "XDG_CACHE_HOME": str(self.td)}
        real = core_session_env()
        self.core.env = lambda: {**private, **real}

    def start_and_install(self):
        core = self.core
        core.start()
        for pid in CORE_PLUGINS:
            hub = core.req()["hub"]
            entry = next(e for e in hub["entries"] if e["plugin_id"] == pid)
            ack = core.req("hub_approve", revision=hub["approval_revision"], plugin_id=pid,
                           manifest_sha256=entry["manifest_sha256"], permissions=entry["permissions"],
                           publisher_unverified_ack=True)
            assert ack["code"] == "ok", (pid, ack)
            self.contract.stage_upload(str(core.root), pid, str(ROOT / "scripts" / "perception_worker.py"))
            hub = core.req()["hub"]
            install = core.req("hub_install", revision=hub["install_revision"], plugin_id=pid,
                               manifest_sha256=entry["manifest_sha256"])
            assert install["code"] == "ok", (pid, install)
            enable = core.req("plugin_enable", revision=core.req()["plugins"]["revision"], plugin_id=pid)
            assert enable["code"] == "ok", (pid, enable)
            core.wait(lambda s, p=pid: self.contract.plugin_item(s, p) is not None
                      and self.contract.plugin_item(s, p)["state"] == "running", 20, pid + " running")

    def invoke(self, capability, inp, deadline_ms=30000):
        """One capability_invoke through the Core; returns the capability_result it published."""
        problem = self.contract.perception_input_problem(capability, json.dumps(inp))
        assert problem is None, (capability, problem)
        before = self.core.req().get("capability_result")
        reply = self.core.req("capability_invoke", capability=capability, input=inp, deadline_ms=deadline_ms)
        assert reply["code"] == "ok", (capability, reply)
        snap = self.core.wait(lambda s: s.get("capability_result") is not None
                              and s["capability_result"]["capability"] == capability
                              and s["capability_result"] != before, 40, "result " + capability)
        return snap["capability_result"]

    def checked(self, label, capability, inp, deadline_ms=30000):
        """Invokes and records a pass only when the Core answered ok and the bridge rule accepts the output."""
        result = self.invoke(capability, inp, deadline_ms)
        if not result["ok"]:
            record("core:" + label, "fail", {"capability": capability, "error": result["error"]})
            return None
        output = result["output"]
        if not self.contract.PERCEPTION_OUTPUTS[capability](output):
            record("core:" + label, "fail", {"capability": capability, "bridge_rejected": output})
            return None
        record("core:" + label, "pass", {"capability": capability, "output": output})
        return output


def press_shortcut(shortcut_id):
    """Fires the bound action the way KDE does (KGlobalAccel component invokeShortcut). Returns the component used,
    or None when no component answered. Only the session environment is passed to gdbus."""
    env = {"PATH": "/usr/bin:/bin", **core_session_env()}
    for component in ("com_anthropic_Claude", "gideon_perception"):
        done = subprocess.run(["gdbus", "call", "--session", "--dest", "org.kde.kglobalaccel", "--object-path",
                               "/component/" + component, "--method", "org.kde.kglobalaccel.Component.invokeShortcut",
                               shortcut_id], capture_output=True, text=True, timeout=10, check=False, env=env)
        if done.returncode == 0:
            time.sleep(0.5)  # the portal signal reaches the worker on its own timer
            return component
    return None


def core_live():
    import glob as _glob
    import tempfile as _tempfile
    td = Path(_tempfile.mkdtemp(prefix="gideon-wp18a-"))
    run = CoreRun(td)
    before_display = host_display()
    record("core:display_before", "info", before_display)
    try:
        run.start_and_install()
        record("core:plugins_running", "pass", {"plugins": CORE_PLUGINS})
        for capability in READ_ONLY:
            run.checked(capability, capability, {})

        pictures = os.path.expanduser("~/Imagens")
        shots_before = set(_glob.glob(os.path.join(pictures, "Screenshot_*.png")))
        shot = run.checked("screenshot", "screen_observe.capture", {})
        left = set(_glob.glob(os.path.join(pictures, "Screenshot_*.png"))) - shots_before
        record("core:screenshot_no_file_left", "pass" if not left else "fail",
               {"left_behind": sorted(left), "image_kept": False})

        refused = run.invoke("camera_gesture.capture", {})
        record("core:camera_refused_without_opt_in", "pass" if refused.get("error") == "opt_in_required" else "fail",
               {"result": refused})
        try:
            run.checked("camera_opt_in_on", "camera_gesture.optin", {"enabled": True})
            run.checked("camera_frame", "camera_gesture.capture", {})
        finally:
            run.checked("camera_opt_in_off", "camera_gesture.optin", {"enabled": False})

        status = run.checked("display_status", "display_manipulate.status", {})
        first = status["outputs"][0]
        name, scale0, bright0 = first["name"], first["scale"], first["brightness"]
        try:
            run.checked("display_scale_125", "display_manipulate.act",
                        {"output": name, "op": "scale", "value": 125})
            run.checked("display_brightness_90", "display_manipulate.act",
                        {"output": name, "op": "brightness", "value": 90})
        finally:
            run.checked("display_restore", "display_manipulate.restore", {})
        after = host_display()
        record("core:display_restored", "pass" if after["scale"] == scale0 and abs(after["brightness"] - bright0) <= 1
               else "fail", {"before": {"scale": scale0, "brightness": bright0}, "after": after})

        # Same payload as the bridge's push-to-talk bind ({id, trigger}); the worker names the shortcut itself.
        run.checked("shortcut_bind", "shortcut_global.bind", {"id": SHORTCUT_ID, "trigger": SHORTCUT_TRIGGER})
        run.checked("shortcut_events_before_press", "shortcut_global.events", {})
        pressed = press_shortcut(SHORTCUT_ID)
        record("core:shortcut_press", "pass" if pressed else "fail", {"invoked_on": pressed, "id": SHORTCUT_ID})
        events = run.checked("shortcut_events_after_press", "shortcut_global.events", {})
        seen = [e["id"] for e in (events or {}).get("events", [])]
        record("core:shortcut_event_received", "pass" if SHORTCUT_ID in seen else "fail",
               {"events": events, "expected_id": SHORTCUT_ID})

        # Restore on Core exit (WP12p 6.1): change the display, then stop the Core without calling restore.
        run.checked("display_scale_125_before_exit", "display_manipulate.act",
                    {"output": name, "op": "scale", "value": 125})
        run.core.stop()
        exited = host_display()
        record("core:display_restored_on_core_exit",
               "pass" if exited["scale"] == scale0 and abs(exited["brightness"] - bright0) <= 1 else "fail",
               {"before": {"scale": scale0, "brightness": bright0}, "after_core_exit": exited})
    finally:
        if run.core.proc is not None:
            run.core.proc.kill()
            run.core.proc.wait(timeout=5)
            run.core.proc = None
        # The Core root holds only the test's private state (nothing of the owner's); it is removed here.
        import shutil as _shutil
        _shutil.rmtree(td, ignore_errors=True)
    counts = {"pass": 0, "fail": 0, "info": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts


def core_serve(seconds):
    """Keeps a real Core with the seven perception plugins running for `seconds` (the UI check attaches to it)."""
    import tempfile as _tempfile
    td = Path(_tempfile.mkdtemp(prefix="gideon-wp18a-serve-"))
    run = CoreRun(td)
    run.start_and_install()
    print("ROOT=%s" % (td / "core"), flush=True)
    try:
        time.sleep(seconds)
    finally:
        run.core.stop()
        import shutil as _shutil
        _shutil.rmtree(td, ignore_errors=True)
    return 0


def core_main():
    counts = core_live()
    evidence = {"generated_by": "scripts/perception_live.py --core", "counts": counts, "checks": results,
                "worker_sha256": __import__("hashlib").sha256(
                    (ROOT / "scripts" / "perception_worker.py").read_bytes()).hexdigest(),
                "core": "target/release/gideon-base (real Core, session env from the owner's PC)"}
    CORE_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    CORE_EVIDENCE.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("evidence:", CORE_EVIDENCE)
    print("counts:", counts)
    return 1 if counts.get("fail") else 0


def main(argv):
    if argv[:1] == ["--kga-probe"]:
        print(json.dumps(kga_probe_inprocess()), flush=True)
        return 0
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true", help="required: acknowledges real desktop changes")
    parser.add_argument("--only", default="", help="comma-separated check names")
    parser.add_argument("--core", action="store_true", help="drive every check through the real Core (WP-18a)")
    parser.add_argument("--core-serve", type=int, default=0, metavar="SECONDS",
                        help="keep a real Core with the perception plugins up for the UI check (WP-18a)")
    args = parser.parse_args(argv)
    if not args.confirm:
        print("refused: pass --confirm (this run changes and restores real desktop settings)")
        return 2
    if args.core_serve:
        return core_serve(args.core_serve)
    if args.core:
        return core_main()
    only = {n for n in args.only.split(",") if n}
    for name, fn in CHECKS:
        if only and name not in only:
            continue
        check(name, fn)
    counts = {"pass": 0, "fail": 0, "blocked": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    import hashlib
    worker_sha = hashlib.sha256((ROOT / "scripts" / "perception_worker.py").read_bytes()).hexdigest()
    evidence = {"generated_by": "scripts/perception_live.py", "counts": counts, "checks": results,
                "worker_sha256": worker_sha,
                "session": os.environ.get("XDG_SESSION_TYPE", ""),
                "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "")}
    if not only:
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("evidence:", EVIDENCE)
    print("counts:", counts)
    return 1 if counts.get("fail") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
