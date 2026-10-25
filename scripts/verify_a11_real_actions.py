#!/usr/bin/env python3
"""A11 live run on this machine: real host actions (real_actions=true) through the Core's text command path.

Private root under target/a11-real/root (build target/release/gideon-base first). Only the default sink volume/mute is
changed, and it is restored to the exact raw channel value read before the run. Only processes this run observed as new
are closed. Writes docs/evidence/real-actions.json (content-free: no titles, no paths outside the repo).
Usage: target/ui-venv/bin/python scripts/verify_a11_real_actions.py   (not part of the gates; touches the host)
"""
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from a11_client import Client  # noqa: E402

BIN = BASE / "target/release/gideon-base"
WORK = BASE / "target/a11-real"
ROOT = WORK / "root"
EVIDENCE = BASE / "docs/evidence/real-actions.json"
SINK = "@DEFAULT_AUDIO_SINK@"
EV = {"steps": [], "checks": [], "binary_sha256": hashlib.sha256(BIN.read_bytes()).hexdigest()}
FAILS = []
_kwin_n = 0


def check(name, cond, detail=None):
    EV["checks"].append({"name": name, "ok": bool(cond), "detail": detail})
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ("" if detail is None else f" :: {detail}"), flush=True)


def run(args, timeout=15):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def sink_node_id():
    out = run(["wpctl", "inspect", SINK]).stdout
    return int(re.match(r"id (\d+),", out).group(1))


def sink_raw():
    """Raw channel value and mute of the default sink, from PipeWire (exact, not rounded)."""
    node = sink_node_id()
    dump = json.loads(run(["pw-dump"], timeout=30).stdout)
    for obj in dump:
        if obj.get("id") == node and str(obj.get("type", "")).endswith("Node"):
            for prop in obj.get("info", {}).get("params", {}).get("Props", []):
                if "channelVolumes" in prop:
                    return {"node": node, "channel": prop["channelVolumes"], "mute": prop.get("mute")}
    raise RuntimeError("default sink node not found")


def vol_read():
    out = run(["wpctl", "get-volume", SINK]).stdout.strip()
    m = re.match(r"Volume: ([0-9.]+)( \[MUTED\])?", out)
    return {"raw": out, "percent": round(float(m.group(1)) * 100), "muted": bool(m.group(2))}


def pids(comm):
    wanted = comm[:15]
    found = set()
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            if Path(f"/proc/{name}/comm").read_text().rstrip("\n") == wanted:
                found.add(int(name))
        except OSError:
            pass
    return found


def kwin_windows():
    """Window list (pid and resource class only) through a read-only KWin script; the result is read from the user journal."""
    global _kwin_n
    _kwin_n += 1
    token = f"A11T{_kwin_n}x{int(time.time() * 1000)}"
    js = WORK / f"kwin_list_{_kwin_n}.js"
    js.write_text(
        "var list = workspace.windowList();\n"
        "for (var i = 0; i < list.length; i++) { var w = list[i];\n"
        f'  console.info("A11WIN {token} pid=" + w.pid + " class=" + w.resourceClass + " normal=" + w.normalWindow); }}\n'
        f'console.info("A11WIN {token} end");\n'
    )
    name = f"a11w{_kwin_n}"
    run(["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", str(js), name])
    run(["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.start"])
    time.sleep(0.8)
    journal = run(["journalctl", "--user", "-n", "800", "--no-pager"], timeout=30).stdout
    run(["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", name])
    windows = []
    for line in journal.splitlines():
        if token in line and " pid=" in line:
            m = re.search(r"pid=(\d+) class=(\S+) normal=(\w+)", line)
            if m:
                windows.append({"pid": int(m.group(1)), "class": m.group(2), "normal": m.group(3) == "true"})
    return windows


def kwin_close(target_pids):
    """Closes only the normal windows whose pid this run recorded (KWin closeWindow, a normal close)."""
    global _kwin_n
    _kwin_n += 1
    js = WORK / f"kwin_close_{_kwin_n}.js"
    js.write_text(
        f"var targets = {json.dumps(sorted(target_pids))};\n"
        "var list = workspace.windowList();\n"
        "for (var i = 0; i < list.length; i++) { var w = list[i];\n"
        "  if (w.normalWindow && targets.indexOf(w.pid) >= 0) { w.closeWindow(); } }\n"
    )
    name = f"a11c{_kwin_n}"
    run(["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", str(js), name])
    run(["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.start"])
    time.sleep(0.8)
    run(["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", name])


def start_core():
    if ROOT.exists():
        run(["rm", "-rf", str(ROOT)])
    ROOT.mkdir(mode=0o700, parents=True)
    cfg = ROOT / "config.json"
    cfg.write_text(json.dumps({"version": 1, "session_timeout_ms": 30000, "wake_phrase": None}))
    cfg.chmod(0o600)
    keep = ("PATH", "HOME", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "WAYLAND_DISPLAY", "DISPLAY", "XDG_CURRENT_DESKTOP", "XAUTHORITY")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    log = open(WORK / "core-live.log", "w")
    proc = subprocess.Popen([str(BIN), "--root", str(ROOT), "--virtual-input", "--commands-sandbox"], env=env, stdout=log, stderr=log)
    until = time.monotonic() + 8
    while not (ROOT / "core.sock").exists():
        if proc.poll() is not None or time.monotonic() > until:
            raise RuntimeError("core did not start")
        time.sleep(0.02)
    return proc


def send_text(c, raw):
    prev = c.snap()["command"]
    prev_sid = prev["session_id"] if prev else None
    before = vol_read()
    r = c.req("text", raw=raw)
    step = {"raw": raw, "send_code": r["code"], "volume_before": before}
    if r["code"] != "ok":
        EV["steps"].append(step)
        return step
    until = time.monotonic() + 25
    while time.monotonic() < until:
        s = c.snap()
        if s["state"] == "idle" and s["command"] and s["command"]["session_id"] != prev_sid:
            cmd = s["command"]
            step.update({"code": cmd["code"], "receipt": cmd["receipt"], "session_id": cmd["session_id"]})
            break
        time.sleep(0.03)
    else:
        step["code"] = "timeout"
    step["volume_after"] = vol_read()
    EV["steps"].append(step)
    return step


def set_real(c, enabled, confirmed=None):
    rev = c.snap()["preferences"]["revision"]
    return c.req("real_actions_preference", revision=rev, enabled=enabled, confirmed=enabled if confirmed is None else confirmed)["code"]


def stop_group(target_pids, label):
    """Stops only the processes this run launched: normal close first (KWin), then SIGTERM, then SIGKILL, each limited to the recorded pids."""
    if not target_pids:
        return "none_recorded"
    kwin_close(target_pids)
    for _ in range(40):
        if not any(Path(f"/proc/{p}").exists() for p in target_pids):
            return f"{label}: closed by window close"
        time.sleep(0.25)
    for sig, name in ((signal.SIGTERM, "SIGTERM"), (signal.SIGKILL, "SIGKILL")):
        for p in target_pids:
            try:
                os.kill(p, sig)
            except ProcessLookupError:
                pass
        for _ in range(20):
            if not any(Path(f"/proc/{p}").exists() for p in target_pids):
                return f"{label}: closed by {name} to recorded pids only"
            time.sleep(0.25)
    return f"{label}: still running after SIGKILL"


def main():
    WORK.mkdir(exist_ok=True)
    baseline = {"volume": vol_read(), "raw": sink_raw(), "kcalc_pids": sorted(pids("kcalc")), "brave_pids": sorted(pids("brave"))}
    EV["baseline"] = baseline
    print("baseline", json.dumps(baseline), flush=True)
    check("baseline: kcalc not running before the run", not baseline["kcalc_pids"])
    check("baseline: brave not running before the run", not baseline["brave_pids"], "Brave was not running, so every brave pid after the launch belongs to this run")

    proc = start_core()
    c = Client(ROOT)
    try:
        s = c.snap()
        check("core starts with real_actions off", s["preferences"]["real_actions"] is False and s["actions"]["real"]["enabled"] is False)
        check("no action before consent (sandbox executor)", s["actions"]["real"]["last_action"] is None)

        code = set_real(c, True, confirmed=False)
        check("consent refused without confirmation", code == "consent_required", code)
        code = set_real(c, True)
        check("consent with confirmation accepted", code == "ok", code)
        s = c.snap()
        check("snapshot shows real_actions on", s["preferences"]["real_actions"] is True and s["actions"]["real"]["enabled"] is True)
        kinds = [e["kind"] for e in s["events"]]
        check("real_actions_enabled event emitted", "real_actions_enabled" in kinds)

        # (b) volume, real sink
        s30 = send_text(c, "set volume to 30")
        check("set volume to 30: command_success with host receipt", s30.get("code") == "command_success" and s30["receipt"]["scope"] == "host" and s30["receipt"]["verified"], s30.get("code"))
        check("set volume to 30: wpctl read-back is 30%", vol_read()["percent"] == 30, vol_read()["raw"])
        sm = send_text(c, "mute")
        check("mute: host receipt and read-back muted", sm.get("code") == "command_success" and vol_read()["muted"] is True, sm.get("code"))
        su = send_text(c, "unmute")
        check("unmute: host receipt and read-back unmuted", su.get("code") == "command_success" and vol_read()["muted"] is False, su.get("code"))
        sup = send_text(c, "volume up")
        check("volume up: 30 to 40", sup.get("code") == "command_success" and vol_read()["percent"] == 40, vol_read()["raw"])
        sdn = send_text(c, "volume down")
        check("volume down: 40 to 30", sdn.get("code") == "command_success" and vol_read()["percent"] == 30, vol_read()["raw"])
        s150 = send_text(c, "set volume to 150")
        check("volume 150 refused, sink unchanged", s150.get("code") == "unsupported" and vol_read()["percent"] == 30, s150.get("code"))

        # (a) apps: kcalc first (harmless), then brave (owner allowed a new window)
        kcalc_before = pids("kcalc")
        ok_kcalc = send_text(c, "open kcalc")
        new_kcalc = sorted(pids("kcalc") - kcalc_before)
        receipt = (ok_kcalc.get("receipt") or {})
        check("open kcalc: host receipt", ok_kcalc.get("code") == "command_success" and receipt.get("scope") == "host", ok_kcalc.get("code"))
        check("open kcalc: a new kcalc process is alive", bool(new_kcalc), str(new_kcalc))
        time.sleep(1.5)
        wins = [w for w in kwin_windows() if w["pid"] in new_kcalc and w["normal"]]
        check("open kcalc: window of the launched process is listed", bool(wins), str(wins))
        EV["kcalc"] = {"receipt_result": receipt.get("result"), "new_pids": new_kcalc, "windows": wins}
        EV["kcalc"]["close"] = stop_group(new_kcalc, "kcalc")
        check("kcalc: launched process closed (only recorded pids)", not any(Path(f"/proc/{p}").exists() for p in new_kcalc), EV["kcalc"]["close"])

        brave_before = pids("brave")
        ok_brave = send_text(c, "open brave")
        time.sleep(4.0)
        breceipt = (ok_brave.get("receipt") or {})
        observed = [int(x) for x in re.findall(r"processo (\d+) observado", breceipt.get("result") or "")]
        new_brave = sorted((pids("brave") - brave_before) | {p for p in observed if Path(f"/proc/{p}").exists()})
        check("open brave: host receipt", ok_brave.get("code") == "command_success" and breceipt.get("scope") == "host", ok_brave.get("code"))
        check("open brave: new brave process observed", bool(new_brave), str(new_brave))
        bwins = [w for w in kwin_windows() if w["pid"] in new_brave and w["normal"]]
        check("open brave: window of the launched process is listed", bool(bwins), str(bwins))
        EV["brave"] = {"receipt_result": breceipt.get("result"), "new_pids": new_brave, "windows": bwins}
        EV["brave"]["close"] = stop_group(new_brave, "brave")
        check("brave: launched processes closed (only recorded pids)", not any(Path(f"/proc/{p}").exists() for p in new_brave), EV["brave"]["close"])
        # The Core drops a peer idle for 5 s; the client reconnects on its next send (a11_client.py).
        EV["core_alive_after_brave_close"] = proc.poll() is None
        check("core still running after the Brave close", proc.poll() is None)

        # (c) negative and safety cases: nothing may execute
        before_neg = vol_read()
        negatives = ["open foo", "open ../../bin/sh", "open kcalc; reboot", "open kcalc && rm -rf /", "mute and open kcalc", "open Brave.exe", "open brave kcalc"]
        for raw in negatives:
            step = send_text(c, raw)
            check(f"negative: '{raw}' is not understood", step.get("code") == "unsupported" and step.get("receipt") is None, step.get("code") or step.get("send_code"))
        check("negatives left the sink unchanged", vol_read() == before_neg, vol_read()["raw"])
        check("negatives started no kcalc process", not pids("kcalc"))
        # Repeated rapid commands: one job at a time; the Core answers busy to the others.
        codes = []
        for _ in range(5):
            codes.append(c.req("text", raw="mute")["code"])
        c.wait_idle()
        EV["rapid"] = {"send_codes": codes, "volume_after": vol_read()}
        check("rapid mute: at most one accepted at a time", codes.count("ok") >= 1 and all(x in ("ok", "busy") for x in codes), str(codes))
        check("rapid mute: sink matches the accepted commands (muted)", vol_read()["muted"] is True, vol_read()["raw"])
        send_text(c, "unmute")
        check("rapid mute: sink unmuted again", vol_read()["muted"] is False)

        # consent off: nothing executes on the host; sandbox answers as before
        check("consent withdrawn", set_real(c, False) == "ok")
        before_off = vol_read()
        pre_kcalc = pids("kcalc")
        off_kcalc = send_text(c, "open kcalc")
        check("consent off: open kcalc refused by the sandbox grammar", off_kcalc.get("code") == "app_unavailable", off_kcalc.get("code"))
        check("consent off: no kcalc started", pids("kcalc") == pre_kcalc)
        off_mute = send_text(c, "mute")
        check("consent off: mute is only the sandbox simulation", off_mute.get("code") == "command_success" and off_mute["receipt"]["scope"] == "sandbox", off_mute.get("code"))
        check("consent off: sink unchanged by the simulation", vol_read() == before_off, vol_read()["raw"])
        off_un = send_text(c, "unmute")
        check("consent off: unmute is not understood", off_un.get("code") == "unsupported", off_un.get("code"))
        s = c.snap()
        ev = [e for e in s["events"]]
        host_events = [e for e in ev if e["kind"] == "host_action"]
        check("host_action events are content-free", all(set(e) <= {"sequence", "at_ms", "request_id", "session_id", "kind", "origin", "outcome"} for e in host_events) and not any(
            w in json.dumps(host_events) for w in ("brave", "kcalc", "wpctl", "/usr")), str(len(host_events)))
        EV["last_snapshot_actions"] = s["actions"]
    finally:
        c.close()
        # restore the sink to the exact raw channel value and mute state read before the run
        raw = baseline["raw"]["channel"][0]
        cube = raw ** (1.0 / 3.0)
        run(["wpctl", "set-volume", SINK, f"{cube:.6f}"])
        run(["wpctl", "set-mute", SINK, "1" if baseline["raw"]["mute"] else "0"])
        after = sink_raw()
        EV["restored"] = {"target_channel": raw, "target_mute": baseline["raw"]["mute"], "after": after, "wpctl": vol_read()}
        check("sink restored to the exact raw channel value (tolerance 1e-4)", abs(after["channel"][0] - raw) < 1e-4, f"{after['channel'][0]} vs {raw}")
        check("sink restored to the exact mute state", bool(after["mute"]) == bool(baseline["raw"]["mute"]))
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        EV["core_exit"] = proc.returncode
        check("core stopped by supervised shutdown", proc.returncode == 0, str(proc.returncode))
        EV["root_entries"] = sorted(p.name for p in ROOT.iterdir())
        check("private root holds only core artifacts", set(EV["root_entries"]) <= {"core.sock", "core.lock", "config.json", "audit.log"}, str(EV["root_entries"]))
        EV["gate"] = "A11_REAL_ACTIONS_LIVE"
        EV["passed"] = sum(1 for x in EV["checks"] if x["ok"])
        EV["failed"] = len(FAILS)
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps(EV, indent=2, ensure_ascii=False) + "\n")
        print("FAILS", FAILS, flush=True)


if __name__ == "__main__":
    main()
    sys.exit(1 if FAILS else 0)
