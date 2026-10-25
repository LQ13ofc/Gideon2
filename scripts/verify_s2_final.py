#!/usr/bin/env python3
"""S2 final gate (docs/B4.md "Contrato gate final S2"): installed packages, real UI, real Core.

Usage: scripts/verify_s2_final.py   (stdlib only; no network; temp dirs under /tmp only; budget about 20 min)

Builds gideon-base 0.1.0 and 0.1.1 from the repository with build_package.py, installs 0.1.0 with
gideon-install under a short ROOT, creates profile `main` and runs:
  A) Core v0.1.0 (hidden-source bwrap, gideon-launch) + packaged Qt UI (offscreen, own bwrap, no repo, no uv,
     no network): S1 observed by the UI; configure (feedback, Hub approve, gate staging via hub_import.py,
     Qt install, wake selection last); B) Core restart + UI observe; C) update refused while the Core runs,
     then update to 0.1.1, UI observe; D) rollback to 0.1.0, UI observe, Qt removal, Core restart, UI observe.
  E) identity: commit, PACKAGE.json hashes, binary hashes, ledger revision, gideon-verify of retained versions.
Writes target/evidence/s2-final.json. Exit 0 only when every check passes.
"""
import errno
import hashlib
import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPO_PATH = str(REPO).encode()
UV_MARK = b".local/share/uv"
INSTALL_TOOL = REPO / "scripts/package_tools/gideon-install"
DRIVER = REPO / "scripts/s2_final_driver.py"
HUB_IMPORT = REPO / "scripts/hub_import.py"
HUB_FIXTURE = REPO / "tests/fixtures/hub.json"
EVIDENCE = REPO / "target/evidence/s2-final.json"
GATE = "S2_FINAL"
PROFILE = "main"
V1, V2 = "0.1.0", "0.1.1"
BENIGN = "benign_fixture"
BENIGN_BYTES = b"benign fixture\n"
MIN_FREE = 6 * 1024 ** 3
CORE_START_TIMEOUT = 90
UI_TIMEOUT = 420
def wake_persisted(preferences):
    """Persisted wake shape (src/storage.rs update_wake_phrases): `wake_phrases` lists hey_gideon active, and the
    legacy `wake_phrase` agrees (the Core keeps it equal to the first active id)."""
    listed = any(p.get("id") == "hey_gideon" and p.get("active") is True for p in preferences.get("wake_phrases") or [])
    return listed and preferences.get("wake_phrase") == "hey_gideon"


S2_UI_REQUIRED = {
    "s1-A": ["actual Core connection", "configuration ready", "base pack preflight verified", "wake replay finished", "stt ready", "command_success receipt verified in UI", "event session_started observed by UI", "event transcript_final observed by UI", "event command_success observed by UI", "transcript source voice", "subtitle non-empty in UI", "result receipt non-empty in UI", "UI observed states ['executing', 'speaking', 'transcribing']", "speech completed on virtual sink with samples"],
    "configure": ["configuration ready before changes", "object visualPagePreference present", "Qt switch save acknowledged by Core", "object gainSlider present", "volume draft reaches 50 on the slider", "object applyGainButton present", "Core persisted volume 50 and visual off", "object hubReviewDialog present", "object publisherAcknowledgement present", "object approveHubButton present", "review never defaults to publisher acknowledgement", "explicit acknowledgement enables approval", "Qt approval persisted by Core", "acknowledged approval disables duplicate submit", "approval is not installation nor publisher identity", "staged payload is not installed", "fixture installed with runtime disabled", "state label shows desativado after install", "install control unavailable once installed", "object wakeRow_hey_gideon present", "object wakeSwitch_okay_gideon present", "object restoreWakeDefaults present", "explicit phrase text presented", "POC phrase cannot be selected", "wake hey_gideon persisted by Core", "selection requires real restart"],
    "persisted-B": ["volume 50 persisted and shown", "visual feedback off persisted", "wake hey_gideon persisted and active", "installed plugin persisted, runtime disabled", "configuration ready", "base pack preflight verified", "wake replay finished", "stt ready", "command_success receipt verified in UI", "event session_started observed by UI", "event transcript_final observed by UI", "event command_success observed by UI", "transcript source voice", "subtitle non-empty in UI", "result receipt non-empty in UI", "UI observed states ['executing', 'speaking', 'transcribing']", "speech completed on virtual sink with samples"],
    "persisted-C": ["volume 50 persisted and shown", "visual feedback off persisted", "wake hey_gideon persisted and active", "installed plugin persisted, runtime disabled", "configuration ready", "base pack preflight verified", "wake replay finished", "stt ready", "command_success receipt verified in UI", "event session_started observed by UI", "event transcript_final observed by UI", "event command_success observed by UI", "transcript source voice", "subtitle non-empty in UI", "result receipt non-empty in UI", "UI observed states ['executing', 'speaking', 'transcribing']", "speech completed on virtual sink with samples"],
    "persisted-D": ["volume 50 persisted and shown", "visual feedback off persisted", "wake hey_gideon persisted and active", "installed plugin persisted, runtime disabled", "configuration ready", "base pack preflight verified", "wake replay finished", "stt ready", "command_success receipt verified in UI", "event session_started observed by UI", "event transcript_final observed by UI", "event command_success observed by UI", "transcript source voice", "subtitle non-empty in UI", "result receipt non-empty in UI", "UI observed states ['executing', 'speaking', 'transcribing']", "speech completed on virtual sink with samples"],
    "remove-D": ["object removeConfirm present", "removal waits for confirmation", "Core snapshot installed list empty", "hub result shows Plugin removido"],
    "final-E": ["volume 50 persisted and shown", "visual feedback off persisted", "wake hey_gideon persisted and active", "plugin absent after removal", "configuration ready", "base pack preflight verified", "wake replay finished", "stt ready", "command_success receipt verified in UI", "event session_started observed by UI", "event transcript_final observed by UI", "event command_success observed by UI", "transcript source voice", "subtitle non-empty in UI", "result receipt non-empty in UI", "UI observed states ['executing', 'speaking', 'transcribing']", "speech completed on virtual sink with samples"],
}

CHECKS, FAILS, ROWS = [], [], []
UNREADABLE = []  # /proc entries of live processes that could not be read (a vanished process is not an entry here)
IGNORED = []  # nothing is skipped in this gate; kept so "ignored" is derived, never a literal
RESULT = {"steps": None, "isolation": {}, "binary_sha256": {}, "identity": {}, "build": {}, "notes": []}
S = {"core": None, "uis": {}}


def check(name, ok, detail=""):
    if ok:
        CHECKS.append(name)
    else:
        text = detail if isinstance(detail, str) else json.dumps(detail, default=str, ensure_ascii=False)
        FAILS.append({"name": name, "detail": text[:3000]})
        print(f"FAIL {name}: {text[:800]}", file=sys.stderr)


def note_unreadable(pid, entry, exc):
    code = getattr(exc, "errno", None)
    if code not in (errno.ENOENT, errno.ESRCH):
        UNREADABLE.append({"pid": pid, "entry": entry, "errno": code, "error": str(exc)})


def scenario(label, fn):
    started, before_pass, before_fail = time.monotonic(), len(CHECKS), len(FAILS)
    try:
        fn()
        status = "done"
    except Exception as exc:  # a broken scenario fails the gate and must not leave a Core or UI behind
        status = "raised"
        check(f"{label}: completed without exception", False, f"{type(exc).__name__}: {exc}")
        stop_all_quiet()
    ROWS.append({"row": label, "status": status, "passed": len(CHECKS) - before_pass,
                 "failed": len(FAILS) - before_fail, "runtime_seconds": round(time.monotonic() - started, 1)})


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_state(root):
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            st = os.lstat(full)
            out[full] = (st.st_mode, st.st_size, st.st_mtime_ns, st.st_ino)
    return out


def host_env():
    home = str(S["home"])
    return {"PATH": "/usr/bin:/bin", "HOME": home, "XDG_CONFIG_HOME": home,
            "XDG_DATA_HOME": home, "XDG_CACHE_HOME": home, "XDG_RUNTIME_DIR": home}


def run(args, env=None, timeout=300, cwd="/"):
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout, cwd=cwd, env=env or host_env())
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"timeout {timeout}s running {args[:3]}") from exc


def tail(path, size=800):
    return path.read_bytes()[-size:].decode("utf-8", "replace") if path.exists() else ""


def id_of(version):
    return f"{version}-{S['commit'][:8]}"


def state_dir():
    return S["root"] / "profiles" / PROFILE


def core_root():
    return state_dir() / "core"


def inst(*args, timeout=900, env_extra=None):
    """Repo gideon-install against ROOT. Returns (rc, parsed JSON or None, stderr tail)."""
    env = host_env()
    env.update(env_extra or {})
    proc = run([sys.executable, "-I", "-B", str(INSTALL_TOOL), "--install-root", str(S["root"]), *args],
               env=env, timeout=timeout)
    text = proc.stdout.decode("utf-8", "replace")
    try:
        obj = json.loads(text) if text.strip() else None
    except ValueError:
        obj = None
    return proc.returncode, obj, proc.stderr.decode("utf-8", "replace")[-600:]


def lst():
    rc, obj, err = inst("list")
    if rc != 0 or not obj:
        raise RuntimeError(f"list failed rc={rc}: {json.dumps(obj)} {err}")
    S["cur"] = obj["current"]  # the launcher follows the ledger, never the intended state
    return obj


def ledger_bytes():
    return (S["root"] / "install.json").read_bytes()


def links():
    return {name: (os.readlink(S["root"] / name) if os.path.islink(S["root"] / name) else None)
            for name in ("current", "previous")}


def bwrap_argv(argv):
    """Core outer sandbox (as B4.2): only ROOT (rw), /usr and the loader cache; no repo, no uv, --unshare-all."""
    rootp = str(S["root"])
    args = ["/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--clearenv",
            "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", rootp,
            "--ro-bind", "/usr", "/usr",
            "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib", "/lib64",
            "--symlink", "usr/bin", "/bin", "--symlink", "usr/bin", "/sbin",
            "--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--bind", rootp, rootp]
    return args + ["--chdir", "/", "--", *argv]


def ui_base(pkg, state):
    """UI outer sandbox (shape of ui_fixture.offscreen_command with package paths): packaged prefix ro,
    STATE rw, artifacts rw, driver ro at /driver.py, no repo, no uv, --unshare-all (no network)."""
    return ["/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--clearenv",
            "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/tmp",
            "--setenv", "XDG_CACHE_HOME", "/tmp/cache", "--setenv", "XDG_CONFIG_HOME", "/tmp/config",
            "--setenv", "XDG_RUNTIME_DIR", "/tmp/runtime", "--setenv", "QT_QPA_PLATFORM", "offscreen",
            "--setenv", "GIDEON_UI_NO_ONBOARDING", "1",
            "--setenv", "QT_QUICK_BACKEND", "software", "--setenv", "QT_SCALE_FACTOR", "2",
            "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib", "/lib64",
            "--symlink", "usr/bin", "/bin", "--symlink", "usr/bin", "/sbin",
            "--ro-bind", "/etc/fonts", "/etc/fonts", "--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--ro-bind", str(pkg), str(pkg),
            "--bind", str(state), str(state),
            "--bind", str(S["art"]), str(S["art"]),
            "--ro-bind", str(DRIVER), "/driver.py",
            "--chdir", "/tmp"]


def ui_argv(step, extra=()):
    pkg = Path(os.path.realpath(S["root"] / "current"))  # resolved through ROOT/current, never hard-coded
    check("UI package resolves inside ROOT/versions", pkg.parent == S["root"] / "versions", str(pkg))
    state = state_dir()
    py = pkg / "venvs/ui/bin/python"
    return ui_base(pkg, state) + ["--", str(py), "-I", "/driver.py", "--app-dir", str(pkg / "app"),
                                  "--root", str(state / "core"), "--artifacts", str(S["art"]),
                                  "--step", step, *extra]


def probe_isolation():
    try:
        outer = run(bwrap_argv(["/bin/true"]), timeout=60)
    except RuntimeError as exc:
        RESULT["isolation"]["outer_probe_error"] = str(exc)
        return "host"
    RESULT["isolation"]["outer_probe_rc"] = outer.returncode
    if outer.returncode != 0:
        RESULT["isolation"]["fallback_reason"] = outer.stderr.decode("utf-8", "replace")[-300:]
        return "host"
    nested = ["/usr/bin/bwrap", "--unshare-all", "--ro-bind", "/usr", "/usr",
              "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib", "/lib64",
              "--symlink", "usr/bin", "/bin", "--proc", "/proc", "--dev", "/dev", "--", "/bin/true"]
    try:
        RESULT["isolation"]["nested_probe_rc"] = run(bwrap_argv(nested), timeout=60).returncode
    except RuntimeError as exc:
        RESULT["isolation"]["nested_probe_error"] = str(exc)
    return "outer_bwrap"


def launcher_argv(core_args=()):
    pkg = S["root"] / "versions" / S["cur"]
    return [str(pkg / "runtime/python/bin/python3.13"), "-I", "-B", str(pkg / "bin/gideon-launch"),
            "--install-root", str(S["root"]), PROFILE, *core_args]


def hub_args():
    return ["--hub-catalog", str(S["catalog"]), sha256(S["catalog"])]


def tree_pids(root_pid):
    kids = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            fields = Path(f"/proc/{entry}/stat").read_text().rsplit(")", 1)[1].split()
        except OSError as exc:
            note_unreadable(int(entry), "stat", exc)
            continue
        except IndexError as exc:
            note_unreadable(int(entry), "stat", exc)
            continue
        kids.setdefault(int(fields[1]), []).append(int(entry))
    seen, stack = [root_pid], [root_pid]
    while stack:
        for child in kids.get(stack.pop(), []):
            seen.append(child)
            stack.append(child)
    return seen


def sandboxed_pids(wrapper_pid):
    """Processes inside the sandbox: the bwrap parent and its forked wrapper carry host paths in argv
    (the --ro-bind of the driver), so they are not sandbox processes and are excluded from the scan."""
    out = []
    for pid in tree_pids(wrapper_pid)[1:]:
        try:
            if Path(f"/proc/{pid}/cmdline").read_bytes().startswith(b"/usr/bin/bwrap"):
                continue
        except OSError as exc:
            note_unreadable(pid, "cmdline", exc)
            continue
        out.append(pid)
    return out


def scan_pids(pids):
    hits = []
    for pid in pids:
        blobs = []
        for name in ("cmdline", "environ", "maps", "mountinfo"):
            try:
                blobs.append(Path(f"/proc/{pid}/{name}").read_bytes())
            except OSError as exc:
                note_unreadable(pid, name, exc)
        for link in ("cwd", "root"):
            try:
                blobs.append(os.readlink(f"/proc/{pid}/{link}").encode())
            except OSError as exc:
                note_unreadable(pid, link, exc)
        try:
            fds = os.listdir(f"/proc/{pid}/fd")
        except OSError as exc:
            note_unreadable(pid, "fd", exc)
            fds = []
        for fd in fds:
            try:
                blobs.append(os.readlink(f"/proc/{pid}/fd/{fd}").encode())
            except OSError as exc:
                note_unreadable(pid, f"fd{fd}", exc)
        for mark in (REPO_PATH, UV_MARK):
            if any(mark in blob for blob in blobs):
                hits.append({"pid": pid, "mark": mark.decode()})
    return hits


def core_start(label, core_args=()):
    if S["core"] is not None:
        raise RuntimeError(f"{S['core']['label']} Core already running")
    argv = bwrap_argv(launcher_argv(core_args))
    with open(S["work"] / f"{label}.log", "wb") as handle:
        proc = subprocess.Popen(argv, env=host_env(), cwd="/", stdin=subprocess.DEVNULL,
                                stdout=handle, stderr=handle, start_new_session=True)
    S["core"] = {"proc": proc, "label": label}
    sock = core_root() / "core.sock"
    deadline = time.monotonic() + CORE_START_TIMEOUT
    while True:
        if proc.poll() is not None:
            raise RuntimeError(f"{label} exited rc={proc.returncode}: {tail(S['work'] / f'{label}.log')}")
        if sock.exists():
            try:
                with socket.socket(socket.AF_UNIX) as probe:
                    probe.settimeout(2)
                    probe.connect(str(sock))
                break
            except OSError:
                pass
        if time.monotonic() > deadline:
            raise TimeoutError(f"{label} socket not ready: {tail(S['work'] / f'{label}.log')}")
        time.sleep(0.05)
    mark = len(UNREADABLE)
    scanned = tree_pids(proc.pid)
    hits = scan_pids(scanned)
    check(f"{label}: Core process tree ({len(scanned)} processes) has no repo or uv path", not hits, hits[:10])
    check(f"{label}: every /proc entry of the Core process tree readable", len(UNREADABLE) == mark, UNREADABLE[mark:][:10])
    return proc


def group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def core_stop(label=None):
    entry = S["core"]
    if entry is None:
        return None
    S["core"] = None
    proc, name = entry["proc"], entry["label"]
    if proc.poll() is None:
        targets = []
        for pid in tree_pids(proc.pid):
            try:
                if b"gideon-base" in Path(f"/proc/{pid}/cmdline").read_bytes():
                    targets.append(pid)
            except OSError:
                pass
        for pid in targets or [proc.pid]:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            rc = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            rc = proc.wait(timeout=5)
            check(f"{name}: clean shutdown on SIGTERM", False, "required SIGKILL")
    else:
        rc = proc.returncode
    deadline = time.monotonic() + 5
    while group_alive(proc.pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    residual = group_alive(proc.pid)
    if residual:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    check(f"{name}: no residual Core or worker processes after stop", not residual, f"pgid {proc.pid}")
    check(f"{name}: Core exit status 0 after SIGTERM", rc == 0, f"rc={rc}")
    return rc


def stop_all_quiet():
    for label, proc in list(S["uis"].items()):
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=10)
        S["uis"].pop(label, None)
    try:
        core_stop()
    except Exception as exc:
        check("cleanup: stop Core", False, f"{type(exc).__name__}: {exc}")


def req(op, **fields):
    S["n"] = S.get("n", 0) + 1
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(10)
        sock.connect(str(core_root() / "core.sock"))
        sock.sendall((json.dumps({"version": 1, "request_id": f"s2f_{S['n']}", "op": op, **fields}) + "\n")
                     .encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                raise RuntimeError("Core disconnected")
            data += chunk
    return json.loads(data)


def snap():
    return req("snapshot")


def record_of(snapshot, plugin_id=BENIGN):
    return next((r for r in (snapshot.get("hub") or {}).get("installed", []) if r["plugin_id"] == plugin_id), None)


def ui_popen(step, label, extra=()):
    out = open(S["work"] / f"ui-{label}.out", "wb")
    err = open(S["work"] / f"ui-{label}.err", "wb")
    proc = subprocess.Popen(ui_argv(step, extra), stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                            env=host_env(), cwd="/", start_new_session=True)
    S["uis"][label] = proc
    S[f"ui_t0_{label}"] = time.monotonic()
    return proc


def ui_finish(proc, label, timeout=UI_TIMEOUT):
    """Waits for a UI driver; returns (rc, parsed last JSON line, isolation scan of its processes)."""
    scan = {"processes_max": 0, "hits": []}
    mark = len(UNREADABLE)
    deadline = time.monotonic() + timeout
    while True:
        kids = sandboxed_pids(proc.pid)
        scan["processes_max"] = max(scan["processes_max"], len(kids))
        for hit in scan_pids(kids):
            if hit not in scan["hits"]:
                scan["hits"].append(hit)
        if proc.poll() is not None:
            break
        if time.monotonic() > deadline:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=10)
            S["uis"].pop(label, None)
            raise TimeoutError(f"UI {label} did not finish in {timeout}s: {tail(S['work'] / f'ui-{label}.err')}")
        time.sleep(0.2)
    S["uis"].pop(label, None)
    scan["unreadable"] = UNREADABLE[mark:]
    text = (S["work"] / f"ui-{label}.out").read_text(encoding="utf-8", errors="replace").strip()
    try:
        obj = json.loads(text.splitlines()[-1]) if text else None
    except ValueError:
        obj = None
    return proc.returncode, obj, scan


def ui_step(step, label, extra=()):
    started = time.monotonic()
    proc = ui_popen(step, label, extra)
    rc, obj, scan = ui_finish(proc, label)
    return ui_record(label, step, rc, obj, scan, started)


def ui_record(label, step, rc, obj, scan, started):
    ok = rc == 0 and bool(obj) and obj.get("failed") == 0 and obj.get("passed", 0) > 0
    check(f"ui {label}: driver {step} passes every assertion (rc {rc})", ok,
          {"rc": rc, "failure": (obj or {}).get("failure"), "stderr": tail(S["work"] / f"ui-{label}.err")})
    names = (obj or {}).get("checks") or []
    required = S2_UI_REQUIRED.get(label) or []
    missing = sorted(set(required) - set(names))
    accepted = bool(required) and bool(names) and (obj or {}).get("passed") == len(names) and not missing
    check(f"ui {label}: self-report accepted (passed equals listed, every required check present)", accepted,
          {"missing": missing, "listed": len(names), "passed": (obj or {}).get("passed")})
    if accepted:
        CHECKS.extend(f"ui {label}: {name}" for name in names)
    check(f"ui {label}: UI process tree has no repo or uv path", scan["processes_max"] >= 1 and not scan["hits"], scan)
    check(f"ui {label}: every /proc entry of the UI process tree readable", not scan.get("unreadable"),
          (scan.get("unreadable") or [])[:10])
    ROWS.append({"row": f"ui {label}", "step": step, "rc": rc, "passed": (obj or {}).get("passed"),
                 "failed": (obj or {}).get("failed"), "state_trace": (obj or {}).get("state_trace"),
                 "observed": (obj or {}).get("observed"), "scan": scan,
                 "runtime_seconds": round(time.monotonic() - started, 1)})
    return obj


def core_exe_check(version, label):
    want = os.path.realpath(S["root"] / "versions" / id_of(version) / "bin/gideon-base")
    exes = []
    for pid in tree_pids(S["core"]["proc"].pid):
        try:
            exes.append(os.readlink(f"/proc/{pid}/exe"))
        except OSError:
            pass
    check(f"{label}: Core process executes packaged bin/gideon-base of {version}", want in exes,
          {"want": want, "exes": exes[:10]})


def profile_refs(ident):
    needle = f"versions/{ident}".encode()
    base = state_dir() / "profile"
    hits = {}
    for path in base.rglob("*"):
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= (1 << 20):
            count = path.read_bytes().count(needle)
            if count:
                hits[path.relative_to(base).as_posix()] = count
    return hits


def build_pkg(version, out_dir):
    cargo = shutil.which("cargo")
    if cargo is None:
        raise RuntimeError("cargo not on PATH; the packaged binary cannot be built")
    out_dir.mkdir()
    build_env = {"PATH": f"{Path(cargo).parent}:/usr/bin:/bin", "HOME": str(Path.home())}
    for key in ("CARGO_HOME", "RUSTUP_HOME"):
        if os.environ.get(key):
            build_env[key] = os.environ[key]
    proc = run(["python3", str(REPO / "scripts/build_package.py"), str(out_dir), "--version", version],
               env=build_env, timeout=1200)
    pkg = out_dir / f"gideon-base-{version}"
    check(f"build {version}: build_package.py --version {version} exits 0", proc.returncode == 0
          and (pkg / "PACKAGE.json").is_file(), proc.stderr.decode()[-800:])
    manifest = json.loads((pkg / "PACKAGE.json").read_text(encoding="utf-8"))
    check(f"build {version}: PACKAGE.json version and commit match HEAD", manifest.get("version") == version
          and manifest.get("commit") == S["commit"], {k: manifest.get(k) for k in ("version", "commit")})
    RESULT["build"][version] = {"dirty": manifest.get("dirty"), "package_json_sha256_at_build": sha256(pkg / "PACKAGE.json"),
                                "gideon_base_sha256": manifest.get("gideon_base_sha256"),
                                "release_gideon_base_sha256": manifest.get("release_gideon_base_sha256")}
    return pkg, manifest


# ---------------------------------------------------------------- scenarios

def sc_setup():
    free = shutil.disk_usage("/tmp").free
    check("space: at least 6 GiB free in /tmp for two packages", free >= MIN_FREE, f"{free} bytes free")
    S["commit"] = run(["git", "-C", str(REPO), "rev-parse", "HEAD"], timeout=30).stdout.decode().strip()
    status = run(["git", "-C", str(REPO), "status", "--porcelain"], timeout=60).stdout.decode()
    RESULT["git_status_at_build"] = status.splitlines()
    tracked = run(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"], timeout=60)
    check("build: no tracked file differs from HEAD", tracked.stdout.strip() == b"", tracked.stdout[-400:].decode())
    S["pkg1"], m1 = build_pkg(V1, S["work"] / "o1")
    S["pkg2"], m2 = build_pkg(V2, S["work"] / "o2")
    RESULT["commit"] = S["commit"]
    RESULT["dirty_at_build"] = {V1: m1.get("dirty"), V2: m2.get("dirty")}
    check("identity: dirty_at_build false for both packages", m1.get("dirty") is False and m2.get("dirty") is False,
          {"dirty": RESULT["dirty_at_build"], "git_status": RESULT["git_status_at_build"]})


def sc_install():
    rc, obj, err = inst("install", str(S["pkg1"]))
    check("1 install: gideon-install install v0.1.0 exits 0 with ok", rc == 0 and obj and obj.get("ok") is True,
          err or obj)
    check("1 install: source consumed by rename", obj and obj.get("source") == "moved" and not S["pkg1"].exists(), obj)
    st = lst()
    check("1 install: list shows current 0.1.0, no previous, revision 1", st["current"] == id_of(V1)
          and st["previous"] is None and st["revision"] == 1 and st["orphans"] == [], st)
    rc, obj, err = inst("profile", "create", PROFILE)
    check("1 profile: main created", rc == 0 and obj and obj.get("created") is True, err or obj)
    shutil.copyfile(HUB_FIXTURE, state_dir() / "hub-catalog.json")
    os.chmod(state_dir() / "hub-catalog.json", 0o600)
    S["catalog"] = state_dir() / "hub-catalog.json"
    check("1 profile: Hub catalog copy placed under profile STATE", S["catalog"].read_bytes() == HUB_FIXTURE.read_bytes())
    S["home_names"] = sorted(os.listdir(Path.home()))
    S["sentinel_pre"] = tree_state(S["sentinel"])


def sc_hidden():
    S["isolation"] = probe_isolation()
    RESULT["isolation"]["core_mode"] = S["isolation"]
    check("2 hidden: Core runs under outer bwrap (hidden source, no repo, no uv, no network)",
          S["isolation"] == "outer_bwrap", RESULT["isolation"])
    probe = run(ui_base(Path(os.path.realpath(S["root"] / "current")), state_dir()) + [
        "--", "/bin/sh", "-c", f"[ ! -e /home ] && echo NOHOME; [ ! -e {REPO} ] && echo NOREPO; cat /proc/net/dev"],
        timeout=60)
    text = probe.stdout.decode("utf-8", "replace")
    check("2 hidden: UI sandbox has no /home and no repo", probe.returncode == 0 and "NOHOME" in text
          and "NOREPO" in text, probe.stderr.decode()[-400:])
    ifaces = [line.split(":")[0].strip() for line in text.splitlines()[2:] if ":" in line]
    RESULT["isolation"]["ui"] = {"mode": "outer_bwrap_no_repo_no_uv_no_network", "netns_interfaces": ifaces,
                                 "binds": ["packaged prefix ro", "STATE rw", "artifacts rw", "driver ro at /driver.py"]}
    check("2 hidden: UI sandbox network namespace exposes only lo", ifaces == ["lo"], ifaces)


def sc_A():
    core_start("core-A-v010", hub_args())
    core_exe_check(V1, "A core v0.1.0")
    obj = ui_step("s1_observe", "s1-A", ("--expect-speech", "completed"))
    check("A s1: UI observed S1 completed with verified result", obj is not None and obj.get("passed", 0) > 0)
    configure()
    snapshot = snap()
    rec = record_of(snapshot)
    check("A configure: Core ledger shows benign installed with runtime disabled",
          rec is not None and rec["state"] == "installed" and rec["runtime"] == "disabled", rec)
    check("A configure: Core persisted volume 50, visual off and wake hey_gideon",
          snapshot["preferences"]["output_volume_percent"] == 50 and snapshot["preferences"]["visual_feedback"] is False
          and wake_persisted(snapshot["preferences"]), snapshot["preferences"])
    check("A configure: Hub approval recorded for exact manifest (not publisher identity)",
          not snapshot["hub"]["publisher_verified"], snapshot["hub"].get("publisher_verified"))
    RESULT["identity"]["A_hub_installed"] = {k: rec[k] for k in ("plugin_id", "state", "runtime")}


def configure():
    art = S["art"]
    proc = ui_popen("configure", "configure")
    deadline = time.monotonic() + UI_TIMEOUT
    while not (art / "approved").exists() and proc.poll() is None:
        if time.monotonic() > deadline:
            raise TimeoutError("configure: approval marker never appeared")
        time.sleep(0.2)
    check("A configure: UI approved exact manifest before gate staging", (art / "approved").exists(),
          tail(S["work"] / "ui-configure.err"))
    source = S["work"] / "benign.bin"
    source.write_bytes(BENIGN_BYTES)
    staged = run([sys.executable, "-I", "-B", str(HUB_IMPORT), "--root", str(core_root()), "--plugin", BENIGN,
                  "--source", str(source)], timeout=120)
    check("A configure: scripts/hub_import.py stages payload as external client", staged.returncode == 0,
          staged.stderr.decode()[-600:])
    (art / "staged").touch()
    started = time.monotonic()
    rc, obj, scan = ui_finish(proc, "configure")
    ui_record("configure", "configure", rc, obj, scan, started)
    check("A configure: UI wrote installed marker", (art / "installed").exists())


def sc_B():
    core_stop()
    core_start("core-B-restart", hub_args())
    core_exe_check(V1, "B core restart")
    ui_step("observe_persisted", "persisted-B", ("--expect-speech", "completed", "--expect-plugin", "present"))
    snapshot = snap()
    check("B persisted: Core snapshot keeps volume 50, visual off, hey_gideon, plugin installed",
          snapshot["preferences"]["output_volume_percent"] == 50 and snapshot["preferences"]["visual_feedback"] is False
          and wake_persisted(snapshot["preferences"]) and record_of(snapshot) is not None, snapshot["preferences"])


def sc_C():
    before = (ledger_bytes(), lst(), links())
    rc, obj, err = inst("update", str(S["pkg2"]))
    check("C update: refused with exit 3 profile_active while Core runs", rc == 3 and obj
          and obj.get("error") == "profile_active" and obj.get("profile") == PROFILE, err or obj)
    check("C update: refusal leaves ledger, list and links unchanged", (ledger_bytes(), lst(), links()) == before)
    check("C update: refused package not consumed", S["pkg2"].is_dir())
    core_stop()
    rc, obj, err = inst("update", str(S["pkg2"]))
    check("C update: update to v0.1.1 exits 0 after Core stopped", rc == 0 and obj and obj.get("ok") is True,
          err or obj)
    check("C update: source consumed by rename", obj and obj.get("source") == "moved" and not S["pkg2"].exists(), obj)
    st = lst()
    check("C update: list shows current 0.1.1 previous 0.1.0", st["current"] == id_of(V2)
          and st["previous"] == id_of(V1) and st["orphans"] == [], st)
    core_start("core-C-v011", hub_args())
    core_exe_check(V2, "C core v0.1.1")
    ui_step("observe_persisted", "persisted-C", ("--expect-speech", "completed", "--expect-plugin", "present"))
    check("C configure: profile re-rendered to the 0.1.1 package path",
          bool(profile_refs(id_of(V2))) and not profile_refs(id_of(V1)),
          {"new": profile_refs(id_of(V2)), "old": profile_refs(id_of(V1))})
    snapshot = snap()
    check("C core: base pack preflight verified after update", (snapshot.get("base_pack") or {}).get("preflight")
          == "verified", snapshot.get("base_pack"))
    check("C core: preferences and Hub state preserved across update",
          snapshot["preferences"]["output_volume_percent"] == 50 and record_of(snapshot) is not None, snapshot["preferences"])
    core_stop()
    pkg = S["root"] / "versions" / id_of(V2)
    record_identity(V2, pkg)


def record_identity(version, pkg):
    manifest = json.loads((pkg / "PACKAGE.json").read_text(encoding="utf-8"))
    RESULT["binary_sha256"][version] = {
        "installed_bin_gideon_base_sha256": sha256(pkg / "bin/gideon-base"),
        "package_json_sha256": sha256(pkg / "PACKAGE.json"),
        "manifest_gideon_base_sha256": manifest.get("gideon_base_sha256"),
        "manifest_release_gideon_base_sha256": manifest.get("release_gideon_base_sha256"),
        "manifest_commit": manifest.get("commit"), "manifest_dirty": manifest.get("dirty"),
    }
    check(f"identity {version}: installed binary matches manifest gideon_base_sha256",
          RESULT["binary_sha256"][version]["installed_bin_gideon_base_sha256"]
          == manifest.get("gideon_base_sha256"), RESULT["binary_sha256"][version])


def sc_D():
    rc, obj, err = inst("rollback")
    check("D rollback: exits 0 to current 0.1.0 previous 0.1.1", rc == 0 and obj and obj.get("ok") is True
          and obj.get("current") == id_of(V1) and obj.get("previous") == id_of(V2), err or obj)
    st = lst()
    check("D rollback: list shows current 0.1.0 previous 0.1.1", st["current"] == id_of(V1)
          and st["previous"] == id_of(V2), st)
    core_start("core-D-rollback", hub_args())
    core_exe_check(V1, "D core rollback")
    ui_step("observe_persisted", "persisted-D", ("--expect-speech", "completed", "--expect-plugin", "present"))
    ui_step("remove_plugin", "remove-D")
    snapshot = snap()
    check("D remove: Core snapshot installed list empty", snapshot["hub"]["installed"] == [], snapshot["hub"]["installed"])
    core_stop()
    core_start("core-E-final", hub_args())
    core_exe_check(V1, "E final core")
    ui_step("observe_persisted", "final-E", ("--expect-speech", "completed", "--expect-plugin", "absent"))
    core_stop()
    record_identity(V1, S["root"] / "versions" / id_of(V1))


def sc_E():
    st = lst()
    RESULT["identity"]["ledger_revision"] = st["revision"]
    RESULT["identity"]["current"] = st["current"]
    RESULT["identity"]["previous"] = st["previous"]
    for ident in (st["current"], st["previous"]):
        if ident is None:
            continue
        pkg = S["root"] / "versions" / ident
        rc = run([str(pkg / "runtime/python/bin/python3.13"), "-I", "-B", str(pkg / "bin/gideon-verify")], timeout=900)
        check(f"E retained {ident}: gideon-verify passes (package unchanged after lifecycle)", rc.returncode == 0,
              rc.stderr.decode()[-400:])
        RESULT["identity"].setdefault("verified", []).append(ident)
    check("E identity: no Core still running", S["core"] is None)


def sc_isolation():
    check("F isolation: real HOME top-level entries unchanged",
          sorted(os.listdir(Path.home())) == S["home_names"], "HOME entries changed")
    check("F isolation: sentinel directory outside the temp parent unchanged",
          tree_state(S["sentinel"]) == S["sentinel_pre"])
    check("F isolation: no UI driver still running", not S["uis"])


def main():
    started = time.monotonic()
    work = Path(tempfile.mkdtemp(prefix="gs2-", dir="/tmp"))
    sentinel = Path(tempfile.mkdtemp(prefix="gs2s-", dir="/tmp"))
    S.update(work=work, home=work / "home", root=work / "r", art=work / "art", sentinel=sentinel)
    S["home"].mkdir(mode=0o700)
    S["art"].mkdir(mode=0o700)
    (sentinel / "keep.txt").write_bytes(b"preserved")
    try:
        scenario("0 setup and build", sc_setup)
        scenario("1 install and profile", sc_install)
        scenario("2 hidden sandboxes", sc_hidden)
        scenario("A v0.1.0 S1, UI configure, Hub", sc_A)
        scenario("B restart and UI reconnect", sc_B)
        scenario("C update refused then applied", sc_C)
        scenario("D rollback, UI remove, final S1", sc_D)
        scenario("E identity", sc_E)
        scenario("F isolation", sc_isolation)
    finally:
        stop_all_quiet()
        for path in (work, sentinel):
            try:
                shutil.rmtree(path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                check("cleanup: temp dirs removed", False, f"{path}: {exc}")
    RESULT.update({
        "gate": GATE,
        "passed": len(CHECKS),
        "failed": len(FAILS),
        "ignored": len(IGNORED),
        "checks": CHECKS,
        "failures": FAILS,
        "steps": ROWS,
        "commit": S.get("commit"),
        "physical_validation": "NOT_PERFORMED",
        "scope": "installed relocatable packages 0.1.0 and 0.1.1 under a versioned ROOT; Core under hidden-source "
                 "bwrap; packaged Qt UI offscreen under its own bwrap (no repo, no uv, no network); virtual PCM/TTS "
                 "S1; Hub approve/stage/install/remove; restart; update; rollback. No LLM, no network, no devices.",
        "runtime_seconds": round(time.monotonic() - started, 1),
    })
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(RESULT, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: RESULT[k] for k in ("gate", "passed", "failed", "ignored", "runtime_seconds")}, indent=2))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
