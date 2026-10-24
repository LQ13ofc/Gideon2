#!/usr/bin/env python3
"""S2 final QA driver for scripts/verify_s2_final.py. NOT shipped.

Runs only inside the packaged UI sandbox, with the packaged interpreter:
  <prefix>/venvs/ui/bin/python -I /driver.py --app-dir <prefix>/app --root <STATE>/core --artifacts DIR --step NAME
It drives the real Qt UI (forceActiveFocus + QTest.keyClick Space, dialogs, bridge properties) against the
real Core. Each step prints one JSON line {step,passed,failed,checks,...} and exits 0 only when every check
passes. Marker files in --artifacts coordinate with the gate: `approved` and `installed` are written here,
`staged` is written by the gate after scripts/hub_import.py has staged the payload.
"""
import argparse
import json
import sys
import time
from pathlib import Path

STEPS = ("s1_observe", "configure", "observe_persisted", "remove_plugin")
PLUGIN = "benign_fixture"
HEY, OKAY = "Hey Gideon", "Okay Gideon"

parser = argparse.ArgumentParser()
parser.add_argument("--app-dir", required=True)
parser.add_argument("--root", required=True)
parser.add_argument("--artifacts", required=True)
parser.add_argument("--step", required=True, choices=STEPS)
parser.add_argument("--expect-speech", choices=("completed", "disabled"), default="completed")
parser.add_argument("--expect-plugin", choices=("present", "absent"), default="present")
args = parser.parse_args()
ART = Path(args.artifacts)
sys.path.insert(0, args.app_dir)

from PySide6.QtGui import QGuiApplication, QAccessible
from PySide6.QtCore import QObject, Qt, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from main import create

CHECKS, TRACE, OBSERVED = [], [], {}


def check(name, value, detail=None):
    if not value:
        suffix = "" if detail is None else " " + json.dumps(detail, default=str, ensure_ascii=False)[:800]
        raise AssertionError(name + suffix)
    CHECKS.append(name)


def wait(condition, seconds, what):
    until = time.monotonic() + seconds
    while True:
        if condition():
            return
        if not TRACE or TRACE[-1] != bridge.state:
            TRACE.append(bridge.state)
        if time.monotonic() > until:
            raise TimeoutError(f"{what} not reached (state={bridge.state}, configuration={bridge.configurationStatus}, "
                               f"diagnostic={bridge.diagnostic!r})")
        QTest.qWait(15)  # keeps the Qt event loop, and therefore the bridge socket, alive


def wait_marker(name, seconds):
    wait(lambda: (ART / name).exists(), seconds, f"gate marker {name}")


def touch(name):
    (ART / name).touch()


def activate(item):
    """Real keyboard activation of a Qt control."""
    item.forceActiveFocus()
    QTest.keyClick(window, Qt.Key.Key_Space)


def visual_item(name):
    stack = [window.contentItem()]
    while stack:
        current = stack.pop()
        if current.objectName() == name:
            return current
        stack.extend(current.childItems())
    raise AssertionError(f"missing visual item {name}")


def find(name):
    obj = window.findChild(QObject, name)
    check(f"object {name} present", obj is not None)
    return obj


def prefs():
    return bridge.snapshot.get("preferences") or {}


def record(plugin_id):
    return next((r for r in bridge.hubInstalled if r.get("plugin_id") == plugin_id), None)


def entry(plugin_id):
    return next((e for e in bridge.hubEntries if e.get("plugin_id") == plugin_id), None)


def visual_items():
    stack = [window.contentItem()]
    found = []
    while stack:
        current = stack.pop()
        found.append(current)
        stack.extend(current.childItems())
    return found


def open_page(page_id, tab):
    """Opens a page the way a user does: its tab when its sub-tab is not in the bar, then the sub-tab.
    The redesign has no Hub or settings dialogs: Plugins (Extensões) is the Hub, Configurações holds the settings."""
    sub = next((i for i in visual_items() if i.objectName() == "subtab_" + page_id), None)
    if sub is None or not sub.isVisible():
        activate(visual_item("tab_" + tab))
        QTest.qWait(60)
        sub = visual_item("subtab_" + page_id)
    activate(sub)
    wait(lambda: window.property("pageId") == page_id, 3, f"page {page_id} open")


def open_hub():
    open_page("plugins", "extensoes")


def open_settings(page_id):
    open_page(page_id, "configuracoes")


def assert_s1(expect):
    """S1 as observed by the UI: Core snapshot state plus the bridge properties QML renders."""
    wait(lambda: bridge.snapshot.get("speech_status") == expect and bridge.snapshot.get("state") == "idle"
         and bridge.resultVerified, 240, f"S1 finished as seen by UI (speech {expect})")
    snap = bridge.snapshot
    kinds = [event.get("kind") for event in snap.get("events", [])]
    check("configuration ready", bridge.configurationStatus == "ready", bridge.configurationStatus)
    check("base pack preflight verified", (snap.get("base_pack") or {}).get("preflight") == "verified",
          snap.get("base_pack"))
    check("wake replay finished", snap.get("wake_status") == "replay_finished", snap.get("wake_status"))
    check("stt ready", snap.get("stt_status") == "ready", snap.get("stt_status"))
    command = snap.get("command") or {}
    check("command_success receipt verified in UI",
          command.get("code") == "command_success" and bridge.resultVerified, command)
    for kind in ("session_started", "transcript_final", "command_success"):
        check(f"event {kind} observed by UI", kind in kinds, kinds[-20:])
    check("transcript source voice", (snap.get("transcript") or {}).get("source") == "voice", snap.get("transcript"))
    check("subtitle non-empty in UI", bool(bridge.subtitle), bridge.subtitle)
    check("result receipt non-empty in UI", bool(bridge.result), bridge.result)
    # Live sampled states, plus states implied by events the UI received (the 150 ms poll can miss short states).
    derived = set()
    if "transcript_final" in kinds:
        derived.add("transcribing")
    if "command_success" in kinds:
        derived.add("executing")
    if "speech_started" in kinds:
        derived.add("speaking")
    seen = set(TRACE) | derived
    need = {"transcribing", "executing"} | ({"speaking"} if expect == "completed" else set())
    check(f"UI observed states {sorted(need)}", need <= seen, {"live": sorted(TRACE), "derived": sorted(derived)})
    if expect == "completed":
        speech = snap.get("speech") or {}
        check("speech completed on virtual sink with samples",
              snap.get("speech_status") == "completed" and speech.get("samples", 0) > 0
              and speech.get("sink") == "virtual" and "speech_completed" in kinds, speech)
        OBSERVED["speech"] = {k: speech.get(k) for k in ("samples", "sink", "output_volume_percent")}
    else:
        check("audible feedback disabled: no speech started",
              snap.get("speech_status") == "disabled" and "speech_started" not in kinds, snap.get("speech_status"))
        OBSERVED["speech"] = None
    OBSERVED.update({"speech_status": snap.get("speech_status"), "states_live": sorted(set(TRACE)),
                     "states_derived": sorted(derived)})


def s1_observe():
    wait(lambda: bridge.connected, 30, "actual Core connection")
    check("actual Core connection", bridge.connected)
    assert_s1(args.expect_speech)
    QTest.qWait(100)
    window.grabWindow().save(str(ART / "s1.png"))


def configure():
    wait(lambda: bridge.connected, 30, "actual Core connection")
    wait(lambda: bridge.preferencesAvailable, 20, "preferences available")
    check("configuration ready before changes", bridge.configurationStatus == "ready", bridge.configurationStatus)

    # 1. Feedback through real Qt controls: the visual indicator is a switch that saves on change (Aparência);
    #    the volume is a draft on the slider, applied with Aplicar (Áudio).
    open_settings("cfg_aparencia")
    activate(find("visualPagePreference"))
    wait(lambda: not bridge.visualFeedback, 10, "visual indicator switch saved by Core")
    check("Qt switch save acknowledged by Core", bridge.preferencesResult == "Preferências salvas pelo Core",
          bridge.preferencesResult)
    open_settings("cfg_audio")
    slider = find("gainSlider")
    slider.forceActiveFocus()
    for _ in range(10):
        QTest.keyClick(window, Qt.Key.Key_Left)
    check("volume draft reaches 50 on the slider", round(slider.property("value")) == 50)
    activate(find("applyGainButton"))
    wait(lambda: bridge.outputVolume == 50 and bridge.preferencesRevision == "2", 10, "volume saved by Core")
    check("Core persisted volume 50 and visual off", prefs().get("output_volume_percent") == 50
          and prefs().get("visual_feedback") is False, prefs())
    QTest.qWait(50)

    # 2. Hub: review permissions, explicit acknowledgement, approve exactly the benign fixture.
    open_hub()
    activate(visual_item(f"review_{PLUGIN}"))
    review = find("hubReviewDialog")
    wait(lambda: review.property("visible"), 3, "permission review dialog open")
    ack, approve = find("publisherAcknowledgement"), find("approveHubButton")
    check("review never defaults to publisher acknowledgement", not ack.property("checked")
          and not approve.property("enabled"))
    activate(ack)
    check("explicit acknowledgement enables approval", ack.property("checked") and approve.property("enabled"))
    activate(approve)
    wait(lambda: bridge.hubApprovalResult == f"Permissões aprovadas: {PLUGIN}", 10, "approval accepted by Core")
    check("Qt approval persisted by Core", entry(PLUGIN) is not None and entry(PLUGIN)["permissions_approved"],
          entry(PLUGIN))
    QTest.qWait(100)
    check("acknowledged approval disables duplicate submit", not approve.property("enabled"))
    check("approval is not installation nor publisher identity", entry(PLUGIN)["status"] == "not_installed"
          and not bridge.snapshot["hub"]["publisher_verified"])
    review.close()
    QTest.qWait(50)
    touch("approved")

    # 3. The gate stages the payload through scripts/hub_import.py (external client of the Core).
    wait_marker("staged", 300)
    wait(lambda: (entry(PLUGIN) or {}).get("payload_staged") is True, 30, "staged payload visible in UI")
    check("staged payload is not installed", entry(PLUGIN)["status"] == "not_installed", entry(PLUGIN))

    # 4. Real Qt install control, keyboard activation.
    open_hub()
    install = visual_item(f"install_{PLUGIN}")
    wait(lambda: install.property("enabled") is True, 10, "install control enabled after staging")
    activate(install)
    wait(lambda: record(PLUGIN) is not None and record(PLUGIN)["state"] == "installed", 60,
         "Core ledger shows fixture installed")
    rec = record(PLUGIN)
    check("fixture installed with runtime disabled", rec["runtime"] == "disabled", rec)
    # The state line of an installed plugin that is not running reads "Desativado" (docs/ui-spec/20-extensoes.md §11).
    status_text = visual_item(f"status_{PLUGIN}").property("text")
    check("state label shows desativado after install", str(status_text).endswith("Desativado"), status_text)
    # The install button is shown only while installing is the next action; once installed it is hidden (unavailable).
    install_now = visual_item(f"install_{PLUGIN}")
    check("install control unavailable once installed", install_now.property("visible") is False
          or install_now.property("enabled") is False)
    QTest.qWait(100)
    window.grabWindow().save(str(ART / "ui.png"))
    QTest.qWait(50)

    # 5. Wake: only the qualified phrase is selectable; selection needs a real Core restart.
    # Done after Hub install on purpose: Core reports restart_required, which disables Hub approve/install.
    open_settings("cfg_voz")
    combo, select = find("wakeChoice"), find("selectWakeButton")
    check("explicit phrase text presented", combo.property("currentText") == HEY, combo.property("currentText"))
    combo.setProperty("currentIndex", 1)
    QTest.qWait(50)
    check("POC phrase cannot be selected", combo.property("currentText") == OKAY and not select.property("enabled"))
    combo.setProperty("currentIndex", 0)
    QTest.qWait(50)
    activate(select)
    # Changing the wake phrase asks first (wakeConfirm); the user's confirmation is the only way to save it.
    confirm = find("wakeConfirm")
    wait(lambda: confirm.property("visible"), 3, "wake change confirmation shown")
    activate(visual_item("confirmWakeButton"))
    wait(lambda: bridge.configurationStatus == "restart_required", 10,
         f"restart_required after wake selection (preferences result {bridge.preferencesResult!r}, "
         f"wake choice {combo.property('currentText')!r}, revision {bridge.preferencesRevision})")
    check("wake hey_gideon persisted by Core", prefs().get("wake_phrase") == "hey_gideon", prefs())
    check("selection requires real restart", not bridge.preferencesAvailable and not bridge.textAvailable)
    window.grabWindow().save(str(ART / "pack.png"))
    QTest.qWait(50)
    touch("installed")
    OBSERVED["installed"] = {k: rec.get(k) for k in ("plugin_id", "state", "runtime")}


def observe_persisted():
    wait(lambda: bridge.connected, 90, "UI reconnected to restarted Core")
    wait(lambda: bridge.configurationStatus == "ready", 30, "configuration ready after restart")
    check("volume 50 persisted and shown", prefs().get("output_volume_percent") == 50 and bridge.outputVolume == 50,
          prefs())
    check("visual feedback off persisted", prefs().get("visual_feedback") is False and not bridge.visualFeedback,
          prefs())
    check("wake hey_gideon persisted and active", prefs().get("wake_phrase") == "hey_gideon"
          and (bridge.snapshot.get("base_pack") or {}).get("active_phrase") == "hey_gideon",
          {"prefs": prefs(), "active": (bridge.snapshot.get("base_pack") or {}).get("active_phrase")})
    rec = record(PLUGIN)
    if args.expect_plugin == "present":
        check("installed plugin persisted, runtime disabled",
              rec is not None and rec["state"] == "installed" and rec["runtime"] == "disabled", rec)
    else:
        check("plugin absent after removal", rec is None, rec)
    assert_s1(args.expect_speech)
    QTest.qWait(100)
    window.grabWindow().save(str(ART / f"persisted-{args.expect_speech}.png"))


def remove_plugin():
    wait(lambda: bridge.connected, 30, "actual Core connection")
    wait(lambda: record(PLUGIN) is not None, 30, "installed plugin present before removal")
    open_hub()
    remove = visual_item(f"remove_{PLUGIN}")
    # The Core may still be speaking its boot replay when this step starts; removal is offered once it is idle again.
    wait(lambda: remove.property("enabled") is True, 60, "remove control enabled")
    activate(remove)
    confirm = find("removeConfirm")
    wait(lambda: confirm.property("visible"), 3, "removal confirmation shown")
    check("removal waits for confirmation", record(PLUGIN) is not None)
    confirm.accept()
    wait(lambda: record(PLUGIN) is None and visual_item("hubLifecycleResult").property("text") != "Removendo no Core",
         30, "plugin removed from Core ledger")
    check("Core snapshot installed list empty", not bridge.hubInstalled, bridge.hubInstalled)
    check("hub result shows Plugin removido", visual_item("hubLifecycleResult").property("text") == "Plugin removido")
    QTest.qWait(100)
    window.grabWindow().save(str(ART / "removed.png"))
    touch("removed")


STEP_FUNCS = {"s1_observe": s1_observe, "configure": configure,
              "observe_persisted": observe_persisted, "remove_plugin": remove_plugin}

app = QGuiApplication(sys.argv)
QAccessible.setActive(True)
bridge, engine = create(app, args.root)
window = engine.rootObjects()[0]
window.setProperty("width", 640)
window.setProperty("height", 520)
QTest.qWait(100)
failure = None
try:
    STEP_FUNCS[args.step]()
except Exception as exc:  # reported as a failed check, never a silent pass
    failure = f"{type(exc).__name__}: {exc}"
finally:
    try:
        bridge.poll.stop()
        bridge.retry.stop()
        bridge.timeout.stop()
        bridge.socket.close()
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    except Exception:
        pass
    del engine
    del bridge
result = {"step": args.step, "passed": len(CHECKS), "failed": 0 if failure is None else 1, "ignored": 0,
          "checks": CHECKS, "state_trace": TRACE, "observed": OBSERVED}
if failure is not None:
    result["failure"] = failure
print(json.dumps(result, ensure_ascii=False), flush=True)
sys.exit(0 if failure is None else 1)
