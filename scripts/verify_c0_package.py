#!/usr/bin/env python3
"""C0 package gate: plugin runtime (dummy_echo, dummy_evil) from the INSTALLED relocatable package.

Usage: scripts/verify_c0_package.py   (stdlib only; no network; temp dirs only under /tmp; about 6-10 min)
Builds ONE gideon-base-0.1.0 package (build_package.py), installs it with gideon-install into a short
ROOT (/tmp/gc0-XXXXXXXX), creates profile main, copies tests/fixtures/hub-c0.json under ROOT/profiles/main
(inside ROOT, so the outer sandbox bind covers it), and runs every Core via gideon-launch inside an outer
bwrap that mounts only ROOT, /usr and the loader cache. The plugin sandbox (src/plugins.rs sandbox_command)
is nested inside it. Clients (scripts/hub_import.py and raw IPC) run outside the hidden sandbox.
Writes target/evidence/c0-package.json. Exit 0 only when every check passes.
"""
import hashlib
import errno
import importlib.util
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
REAL_HOME_MARK = b"/home/lucas"
INSTALL_TOOL = REPO / "scripts/package_tools/gideon-install"
HUB_IMPORT = REPO / "scripts/hub_import.py"
CATALOG_FIXTURE = REPO / "tests/fixtures/hub-c0.json"
ECHO_FIXTURE = REPO / "tests/fixtures/dummy_echo.py"
EVIL_FIXTURE = REPO / "tests/fixtures/dummy_evil.py"
EVIDENCE = REPO / "target/evidence/c0-package.json"
GATE = "C0_PACKAGE"
VERSION = "0.1.0"
PROFILE = "main"
ECHO, EVIL = "dummy_echo", "dummy_evil"
ECHO_CAP, EVIL_CAP = "dummy_echo.echo", "dummy_evil.probe"
PROBES = ["network", "read_home", "read_repo", "write_root", "env", "mem"]
PLUGIN_MARK = b"/plugin/main.py"
CANARY = "GIDEON_CANARY"  # set in the outer sandbox environment of every Core; plugins must not see it
UNREADABLE, IGNORED = [], []


def note_unreadable(pid, entry, exc):
    """An unreadable /proc entry fails the gate; an entry of a process that already exited does not."""
    code = getattr(exc, "errno", None)
    if code not in (errno.ENOENT, errno.ESRCH):
        UNREADABLE.append({"pid": pid, "entry": entry, "errno": code, "error": str(exc)})


def evil_input(probe):
    data = {"probe": probe}
    if probe == "read_repo":
        data["path"] = str(REPO / "Cargo.toml")
    if probe == "env":
        data["names"] = [CANARY]
    return data


def load_evil():
    spec = importlib.util.spec_from_file_location("dummy_evil_proof", EVIL_FIXTURE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unsandboxed_proof(port):
    """Same fixture functions, run in-process with no sandbox: each target must be reachable."""
    evil = load_evil()
    out = {"network": evil.probe_network({"listener": ["127.0.0.1", port]})["result"],
           "read_repo": evil.probe_read_repo({"path": str(REPO / "Cargo.toml")})["result"]}
    previous = os.environ.get(CANARY)
    os.environ[CANARY] = "1"
    try:
        out["env"] = evil.probe_env({"names": [CANARY]})["result"]
    finally:
        if previous is None:
            os.environ.pop(CANARY, None)
        else:
            os.environ[CANARY] = previous
    return out

CHECKS, FAILS = [], []
RESULT = {"scenarios": {}, "isolation": {}, "identity": {}, "notes": [], "probe_results": {}}
S = {"cores": {}}


def check(name, ok, detail=""):
    if ok:
        CHECKS.append(name)
    else:
        text = detail if isinstance(detail, str) else json.dumps(detail, default=str, ensure_ascii=False)
        FAILS.append({"name": name, "detail": text[:3000]})
        print(f"FAIL {name}: {text[:800]}", file=sys.stderr)


def scenario(label, fn):
    try:
        fn()
        RESULT["scenarios"][label] = "done"
    except Exception as exc:
        RESULT["scenarios"][label] = "raised"
        check(f"{label}: completed without exception", False, f"{type(exc).__name__}: {exc}")
        for profile in list(S["cores"]):
            core_stop_quiet(profile)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def host_env():
    home = str(S["home"])
    return {"PATH": "/usr/bin:/bin", "HOME": home, "XDG_CONFIG_HOME": home,
            "XDG_DATA_HOME": home, "XDG_CACHE_HOME": home, "XDG_RUNTIME_DIR": home}


def run(args, env=None, timeout=300, cwd="/"):
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout, cwd=cwd, env=env or host_env())
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"timeout {timeout}s running {args[:3]}") from exc


def inst(*args, timeout=900):
    """Run the repo gideon-install against ROOT. Returns (rc, parsed JSON or None, stderr tail)."""
    proc = run([sys.executable, "-I", "-B", str(INSTALL_TOOL), "--install-root", str(S["root"]), *args],
               timeout=timeout)
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
    return obj


def core_root(profile):
    return S["root"] / "profiles" / profile / "core"


def installed_dir():
    return S["root"] / "versions" / S["ident"]


def bwrap_argv(argv, setenv=()):
    """Outer sandbox: only ROOT (rw), /usr and the loader cache; no repo, no uv, no network (--unshare-all)."""
    rootp = str(S["root"])
    args = ["/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--clearenv",
            "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", rootp,
            "--ro-bind", "/usr", "/usr",
            "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib", "/lib64",
            "--symlink", "usr/bin", "/bin", "--symlink", "usr/bin", "/sbin",
            "--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--bind", rootp, rootp]
    for name, value in setenv:
        args += ["--setenv", name, value]
    return args + ["--chdir", "/", "--", *argv]


def probe_isolation():
    """Outer bwrap must work; the sandbox must have no /home and only lo in its netns."""
    try:
        probe = run(bwrap_argv(["/bin/sh", "-c", "[ ! -e /home ] && echo NOHOME; cat /proc/net/dev"]), timeout=60)
    except RuntimeError as exc:
        RESULT["isolation"]["outer_probe_error"] = str(exc)
        return False
    text = probe.stdout.decode("utf-8", "replace")
    RESULT["isolation"]["outer_probe_rc"] = probe.returncode
    check("isolation: outer bwrap runs and hides /home (repo and ~/.local/share/uv unreachable)",
          probe.returncode == 0 and "NOHOME" in text, probe.stderr.decode()[-400:])
    ifaces = [line.split(":")[0].strip() for line in text.splitlines()[2:] if ":" in line]
    RESULT["isolation"]["netns_interfaces"] = ifaces
    check("isolation: outer network namespace exposes only lo", ifaces == ["lo"], ifaces)
    return probe.returncode == 0 and "NOHOME" in text and ifaces == ["lo"]


def launcher_argv(profile, core_args=()):
    """gideon-launch of the installed package (ROOT/versions/<ident>) only, through the ledger current link."""
    pkg = installed_dir()
    return [str(pkg / "runtime/python/bin/python3.13"), "-I", "-B", str(pkg / "bin/gideon-launch"),
            "--install-root", str(S["root"]), profile, *core_args]


def hub_args():
    return ["--hub-catalog", str(S["catalog"]), sha256(S["catalog"])]


def tree_pids(root_pid):
    kids = {}
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            ppid = ppid_of(int(entry))
            if ppid is not None:
                kids.setdefault(ppid, []).append(int(entry))
    seen, stack = [root_pid], [root_pid]
    while stack:
        for child in kids.get(stack.pop(), []):
            seen.append(child)
            stack.append(child)
    return seen


def plugin_pids():
    """Plugin processes of THIS run only: cmdline has /plugin/main.py and the run ROOT is in the process
    or its parent cmdline (the nested bwrap argv carries the payload path under ROOT). Other sessions'
    plugin processes (for example a concurrent cargo test) are never counted or signalled."""
    root_bytes = str(S["root"]).encode()
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        cmd = cmdline_of(pid)
        if PLUGIN_MARK not in cmd:
            continue
        parent = ppid_of(pid)
        if root_bytes in cmd or (parent and root_bytes in cmdline_of(parent)):
            found.append(pid)
    return sorted(found)


def python_pids():
    return [p for p in plugin_pids() if cmdline_of(p).split(b"\0")[0].find(b"python") >= 0]


def ppid_of(pid):
    try:
        return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
    except OSError as exc:
        note_unreadable(pid, "stat", exc)
    except (IndexError, ValueError) as exc:
        note_unreadable(pid, "stat", exc)
    return None


def cmdline_of(pid):
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError as exc:
        note_unreadable(pid, "cmdline", exc)
        return b""


def bwrap_ancestor(pid):
    cur, seen = ppid_of(pid), 0
    while cur and cur > 1 and seen < 8:
        if b"bwrap" in cmdline_of(cur):
            return True
        cur, seen = ppid_of(cur), seen + 1
    return False


def describe_pids(pids):
    out = []
    for pid in pids:
        ppid = ppid_of(pid)
        out.append({"pid": pid, "ppid": ppid, "cmdline": cmdline_of(pid)[:400].decode("utf-8", "replace"),
                    "parent_cmdline": cmdline_of(ppid)[:200].decode("utf-8", "replace") if ppid else None})
    return out


def scan_pids(pids):
    hits = []
    for pid in pids:
        blobs = []
        for name in ("cmdline", "environ", "maps", "mountinfo"):
            try:
                blobs.append((name, Path(f"/proc/{pid}/{name}").read_bytes()))
            except OSError as exc:
                note_unreadable(pid, name, exc)
        for link in ("cwd", "root", "exe"):
            try:
                blobs.append((link, os.readlink(f"/proc/{pid}/{link}").encode()))
            except OSError as exc:
                note_unreadable(pid, link, exc)
        try:
            fds = os.listdir(f"/proc/{pid}/fd")
        except OSError as exc:
            note_unreadable(pid, "fd", exc)
            fds = []
        for fd in fds:
            try:
                blobs.append((f"fd{fd}", os.readlink(f"/proc/{pid}/fd/{fd}").encode()))
            except OSError as exc:
                note_unreadable(pid, f"fd{fd}", exc)
        for mark in (REPO_PATH, UV_MARK, REAL_HOME_MARK):
            for source, blob in blobs:
                if mark in blob:
                    hits.append({"pid": pid, "mark": mark.decode(), "source": source,
                                 "context": blob[max(0, blob.find(mark) - 120):blob.find(mark) + 120]
                                 .decode("utf-8", "replace")})
                    break
    return hits


def wait_no_plugins(label, timeout=8):
    deadline = time.monotonic() + timeout
    while plugin_pids() and time.monotonic() < deadline:
        time.sleep(0.05)
    left = plugin_pids()
    check(f"{label}: no plugin process left", not left, {"pids": left, "cmdlines": [
        cmdline_of(p)[:200].decode("utf-8", "replace") for p in left]})


def core_start(profile, label, core_args=()):
    if profile in S["cores"]:
        raise RuntimeError(f"{profile} Core already running")
    if S.get("isolation_ok") is not True:
        raise RuntimeError("outer bwrap isolation not available; refusing to run a Core unisolated")
    argv = bwrap_argv(launcher_argv(profile, core_args), setenv=((CANARY, "1"),))
    log = S["work"] / f"{label}.log"
    with open(log, "wb") as handle:
        proc = subprocess.Popen(argv, env=host_env(), cwd="/", stdin=subprocess.DEVNULL,
                                stdout=handle, stderr=handle, start_new_session=True)
    S["cores"][profile] = {"proc": proc, "label": label}
    sock = core_root(profile) / "core.sock"
    deadline = time.monotonic() + 90
    while True:
        if proc.poll() is not None:
            raise RuntimeError(f"{label} exited rc={proc.returncode}: {tail(log)}")
        if sock.exists():
            try:
                with socket.socket(socket.AF_UNIX) as probe:
                    probe.settimeout(2)
                    probe.connect(str(sock))
                return proc
            except OSError:
                pass
        if time.monotonic() > deadline:
            raise TimeoutError(f"{label} socket not ready: {tail(log)}")
        time.sleep(0.05)


def tail(path):
    return path.read_bytes()[-800:].decode("utf-8", "replace") if path.exists() else ""


def group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def core_stop(profile):
    entry = S["cores"].pop(profile, None)
    if entry is None:
        return None
    proc, label = entry["proc"], entry["label"]
    if proc.poll() is None:
        targets = [pid for pid in tree_pids(proc.pid) if b"gideon-base" in cmdline_of(pid)]
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
            check(f"{label}: clean shutdown on SIGTERM", False, "required SIGKILL")
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
    check(f"{label}: no residual Core process group after stop", not residual, f"pgid {proc.pid}")
    check(f"{label}: Core exit status 0 after SIGTERM", rc == 0, f"rc={rc}")
    wait_no_plugins(f"{label} after Core stop")
    return rc


def core_stop_quiet(profile):
    try:
        core_stop(profile)
    except Exception as exc:
        check(f"cleanup: stop {profile} Core", False, f"{type(exc).__name__}: {exc}")


def req(profile, op, **fields):
    S["n"] = S.get("n", 0) + 1
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(15)
        sock.connect(str(core_root(profile) / "core.sock"))
        sock.sendall((json.dumps({"version": 1, "request_id": f"c0_{S['n']}", "op": op, **fields}) + "\n")
                     .encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                raise RuntimeError("Core disconnected")
            data += chunk
    return json.loads(data)


def snapshot(profile):
    return req(profile, "snapshot")


def hub_of(profile):
    return snapshot(profile)["hub"]


def hub_entry(hub, plugin_id):
    return next(e for e in hub["entries"] if e["plugin_id"] == plugin_id)


def plugin_item(snap, plugin_id):
    return next((i for i in snap["plugins"]["items"] if i["plugin_id"] == plugin_id), None)


def wait_item(profile, plugin_id, predicate, timeout, what):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = snapshot(profile)
        item = plugin_item(last, plugin_id)
        if item is not None and predicate(item):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"{what} not reached: {json.dumps(plugin_item(last, plugin_id) if last else None)}")


def wait_result(profile, capability, prior, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = snapshot(profile).get("capability_result")
        if result and result.get("capability") == capability and result != prior:
            return result
        time.sleep(0.05)
    raise TimeoutError(f"no capability_result for {capability}")


def approve(profile, plugin_id):
    hub = hub_of(profile)
    entry = hub_entry(hub, plugin_id)
    return req(profile, "hub_approve", revision=hub["approval_revision"], plugin_id=plugin_id,
               manifest_sha256=entry["manifest_sha256"], permissions=entry["permissions"],
               publisher_unverified_ack=True)


def plugin_op(profile, op, plugin_id):
    revision = snapshot(profile)["plugins"]["revision"]
    return req(profile, op, revision=revision, plugin_id=plugin_id)


def invoke(profile, capability, payload, deadline_ms=5000):
    prior = snapshot(profile).get("capability_result")
    response = req(profile, "capability_invoke", capability=capability, input=payload, deadline_ms=deadline_ms)
    return response, prior


def s1_check(profile, label):
    snap = wait_snapshot(
        profile,
        lambda s: s.get("state") == "idle" and s.get("wake_status") == "replay_finished"
        and (s.get("command") or {}).get("code") == "command_success"
        and s.get("stt_status") == "ready" and s.get("speech_status") == "completed",
        90, label)
    check(f"{label}: configuration_status ready", snap["configuration_status"] == "ready", snap["configuration_status"])
    check(f"{label}: base_pack preflight verified", (snap.get("base_pack") or {}).get("preflight") == "verified",
          snap.get("base_pack"))
    check(f"{label}: wake replay finished", snap["wake_status"] == "replay_finished", snap["wake_status"])
    check(f"{label}: command_success receipt verified",
          snap["command"]["code"] == "command_success" and snap["command"]["receipt"]["verified"] is True,
          snap["command"])
    check(f"{label}: stt_status ready", snap["stt_status"] == "ready", snap["stt_status"])
    speech = snap.get("speech") or {}
    check(f"{label}: speech completed on virtual TTS with samples",
          snap["speech_status"] == "completed" and speech.get("samples", 0) > 0, {
              "speech_status": snap["speech_status"], "speech": speech})
    return snap


def wait_snapshot(profile, predicate, timeout, what):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = snapshot(profile)
        if predicate(last):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"{what} not reached: state={last.get('state')} wake={last.get('wake_status')} "
                       f"command={(last.get('command') or {}).get('code')} speech={last.get('speech_status')}")


def hub_install_plugin(profile, plugin_id, fixture):
    """Approve, stage the fixture bytes (repo hub_import.py as external client), install."""
    cr = core_root(profile)
    approved = approve(profile, plugin_id)
    check(f"{plugin_id}: hub explicit manifest approval accepted", approved.get("code") == "ok", approved)
    staged = run(["python3", str(HUB_IMPORT), "--root", str(cr), "--plugin", plugin_id,
                  "--source", str(fixture)], timeout=120)
    check(f"{plugin_id}: repo hub_import.py stages payload as external client", staged.returncode == 0,
          staged.stderr.decode()[-600:])
    hub = hub_of(profile)
    digest = hub_entry(hub, plugin_id)["manifest_sha256"]
    installed = req(profile, "hub_install", revision=hub["install_revision"], plugin_id=plugin_id,
                    manifest_sha256=digest)
    check(f"{plugin_id}: hub install ok", installed.get("code") == "ok", installed)
    record = next((r for r in hub_of(profile)["installed"] if r["plugin_id"] == plugin_id), None)
    check(f"{plugin_id}: installed state recorded", record is not None and record["state"] == "installed",
          record)


# ---------------------------------------------------------------- scenarios

def scenario_build():
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True,
                          timeout=30).stdout.strip()
    S["commit"] = head
    cargo = shutil.which("cargo")
    if cargo is None:
        raise RuntimeError("cargo not on PATH; the packaged binary cannot be built")
    out_dir = S["work"] / "o1"
    out_dir.mkdir()
    # build_package.py binds the read-only cargo/rustup toolchain from the real HOME (as B4 does); nothing is written there.
    build_env = {"PATH": f"{Path(cargo).parent}:/usr/bin:/bin", "HOME": str(Path.home())}
    for key in ("CARGO_HOME", "RUSTUP_HOME"):
        if os.environ.get(key):
            build_env[key] = os.environ[key]
    proc = run(["python3", str(REPO / "scripts/build_package.py"), str(out_dir), "--version", VERSION],
               env=build_env, timeout=1200)
    pkg = out_dir / f"gideon-base-{VERSION}"
    check("build: build_package.py --version 0.1.0 exits 0", proc.returncode == 0
          and (pkg / "PACKAGE.json").is_file(), proc.stderr.decode()[-800:])
    manifest = json.loads((pkg / "PACKAGE.json").read_text(encoding="utf-8"))
    check("build: PACKAGE.json version and commit match HEAD", manifest.get("version") == VERSION
          and manifest.get("commit") == head, {k: manifest.get(k) for k in ("version", "commit")})
    tracked = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"],
                             capture_output=True, text=True, timeout=60).stdout
    check("build: no tracked file differs from HEAD", tracked == "", tracked[-400:])
    S["pkg"] = pkg
    S["ident"] = f"{VERSION}-{head[:8]}"
    S["build_pkg_json_sha"] = sha256(pkg / "PACKAGE.json")
    S["build_bin_sha"] = sha256(pkg / "bin/gideon-base")
    RESULT["identity"].update({
        "commit": head,
        "dirty_at_build": manifest.get("dirty"),
        "package_json_sha256_at_build": S["build_pkg_json_sha"],
        "packaged_binary_sha256": S["build_bin_sha"],
        "package_version": manifest.get("version"),
    })
    check("identity: dirty_at_build is false (clean tree at build)", manifest.get("dirty") is False,
          {"dirty": manifest.get("dirty")})


def scenario_install():
    rc, obj, err = inst("install", str(S["pkg"]))
    check("install: gideon-install install 0.1.0 exits 0 with ok", rc == 0 and obj and obj.get("ok") is True,
          err or obj)
    check("install: source consumed by rename (package now lives only under ROOT)",
          obj is not None and obj.get("source") == "moved" and not S["pkg"].exists(), obj)
    st = lst()
    check("install: list shows current 0.1.0 and revision 1", st["current"] == S["ident"]
          and st["revision"] == 1 and st["orphans"] == [], st)
    rc, obj, err = inst("profile", "create", PROFILE)
    check("install: profile main created", rc == 0 and obj is not None and obj.get("created") is True, err or obj)
    profile_dir = S["root"] / "profiles" / PROFILE
    profile_dir.mkdir(exist_ok=True, mode=0o700)
    S["catalog"] = profile_dir / "hub-c0.json"
    shutil.copyfile(CATALOG_FIXTURE, S["catalog"])
    S["catalog"].chmod(0o600)
    check("install: catalog copy is byte-identical to tests/fixtures/hub-c0.json",
          sha256(S["catalog"]) == sha256(CATALOG_FIXTURE))
    check("install: ROOT is 0700 and owned by this user", stat.S_IMODE(os.lstat(S["root"]).st_mode) == 0o700)
    installed = installed_dir()
    check("install: installed bin/gideon-base sha256 equals the built binary",
          sha256(installed / "bin/gideon-base") == S["build_bin_sha"], "binary changed by install")
    check("install: installed PACKAGE.json sha256 equals the built PACKAGE.json",
          sha256(installed / "PACKAGE.json") == S["build_pkg_json_sha"], "PACKAGE.json changed by install")
    RESULT["identity"]["package_json_sha256"] = sha256(installed / "PACKAGE.json")
    RESULT["identity"]["packaged_binary_sha256"] = sha256(installed / "bin/gideon-base")


def scenario_isolation():
    S["isolation_ok"] = probe_isolation()
    RESULT["isolation"]["mode"] = "outer_bwrap" if S["isolation_ok"] else "unavailable"
    check("isolation: outer bwrap hidden-source mode required for C0", S["isolation_ok"] is True,
          RESULT["isolation"])


def scenario_core1():
    """Core 1: S1 before plugins; hub install; echo IPC; revoke; re-approve; evil probes."""
    core_start(PROFILE, "core1-before", hub_args())
    s1_check(PROFILE, "S1 before plugins")
    snap = snapshot(PROFILE)
    check("core1: both plugins absent or disabled before any enable", all(
        plugin_item(snap, pid) is None or plugin_item(snap, pid)["state"] == "disabled" for pid in (ECHO, EVIL)),
        [plugin_item(snap, p) for p in (ECHO, EVIL)])
    check("core1: no plugin process before any enable", plugin_pids() == [], plugin_pids())
    hub_install_plugin(PROFILE, ECHO, ECHO_FIXTURE)
    hub_install_plugin(PROFILE, EVIL, EVIL_FIXTURE)

    # Enable echo and invoke: uppercase + count.
    enabled = plugin_op(PROFILE, "plugin_enable", ECHO)
    check("echo: plugin_enable ok", enabled.get("code") == "ok", enabled)
    wait_item(PROFILE, ECHO, lambda i: i["state"] == "running" and i["enabled"], 30, "echo running")
    check("echo: plugin bwrap and python processes present after enable",
          len(plugin_pids()) >= 2, plugin_pids())
    response, prior = invoke(PROFILE, ECHO_CAP, {"text": "gideon c0"})
    check("echo: capability_invoke accepted", response.get("code") == "ok", response)
    result = wait_result(PROFILE, ECHO_CAP, prior)
    check("echo: uppercase output and count 1", result.get("ok") is True
          and result["output"] == {"text": "GIDEON C0", "count": 1}, result)
    response, prior = invoke(PROFILE, ECHO_CAP, {"text": "again"})
    result = wait_result(PROFILE, ECHO_CAP, prior)
    check("echo: second invoke count 2", result.get("ok") is True and result["output"]
          == {"text": "AGAIN", "count": 2}, result)
    response = req(PROFILE, "capability_invoke", capability=ECHO_CAP, input="not-an-object", deadline_ms=1000)
    check("echo: non-object input refused at Core (invalid_input)", response.get("code") == "invalid_input", response)
    response = req(PROFILE, "capability_invoke", capability="dummy_echo.missing", input={}, deadline_ms=1000)
    check("echo: unknown capability refused", response.get("code") == "unknown_capability", response)

    # Revoke: capability gone, process gone, approval revision bumped, result cleared.
    before = snapshot(PROFILE)["hub"]["approval_revision"]
    revoked = plugin_op(PROFILE, "plugin_revoke", ECHO)
    check("echo: plugin_revoke ok", revoked.get("code") == "ok", revoked)
    wait_no_plugins("echo revoke")
    snap = snapshot(PROFILE)
    check("echo: approval revision +1 on revoke", snap["hub"]["approval_revision"] == before + 1,
          {"before": before, "after": snap["hub"]["approval_revision"]})
    check("echo: permissions no longer approved after revoke",
          hub_entry(snap["hub"], ECHO)["permissions_approved"] is False, hub_entry(snap["hub"], ECHO))
    check("echo: item disabled and not enabled after revoke",
          plugin_item(snap, ECHO)["state"] == "disabled" and plugin_item(snap, ECHO)["enabled"] is False,
          plugin_item(snap, ECHO))
    check("echo: last capability_result cleared by revoke", snap.get("capability_result") is None,
          snap.get("capability_result"))
    response, _ = invoke(PROFILE, ECHO_CAP, {"text": "x"})
    check("echo: invoke after revoke is capability_unavailable", response.get("code") == "capability_unavailable",
          response)
    response = plugin_op(PROFILE, "plugin_enable", ECHO)
    check("echo: re-enable without approval refused (permissions_not_approved)",
          response.get("code") == "permissions_not_approved", response)
    approved = approve(PROFILE, ECHO)
    check("echo: re-approval of the unchanged manifest accepted", approved.get("code") == "ok", approved)
    response = plugin_op(PROFILE, "plugin_enable", ECHO)
    check("echo: re-enable after re-approval ok", response.get("code") == "ok", response)
    wait_item(PROFILE, ECHO, lambda i: i["state"] == "running" and i["enabled"], 30, "echo running again")
    response, prior = invoke(PROFILE, ECHO_CAP, {"text": "back"})
    result = wait_result(PROFILE, ECHO_CAP, prior)
    check("echo: fresh process after re-enable answers count 1", result.get("ok") is True
          and result["output"] == {"text": "BACK", "count": 1}, result)

    # dummy_evil: adversarial probes inside the packaged plugin sandbox.
    response = plugin_op(PROFILE, "plugin_enable", EVIL)
    check("evil: plugin_enable ok", response.get("code") == "ok", response)
    wait_item(PROFILE, EVIL, lambda i: i["state"] == "running" and i["enabled"], 30, "evil running")
    repo_markers = (str(REPO), "Documentos", "Gideon/base", "/home/")
    for probe in PROBES:
        response, prior = invoke(PROFILE, EVIL_CAP, evil_input(probe), deadline_ms=9000)
        check(f"evil {probe}: invoke accepted", response.get("code") == "ok", response)
        result = wait_result(PROFILE, EVIL_CAP, prior, timeout=25)
        output = result.get("output") or {}
        RESULT["probe_results"][probe] = {"ok": result.get("ok"), "result": output.get("result"),
                                          "detail": output.get("detail"), "elapsed_ms": result.get("elapsed_ms")}
        check(f"evil {probe}: denied inside the packaged sandbox", result.get("ok") is True
              and output.get("result") == "denied", result)
        text = json.dumps(result, ensure_ascii=False)
        check(f"evil {probe}: plugin answer carries no repo or home path",
              not any(marker in text for marker in repo_markers), text[:400])
    # Loopback listener owned by the gate (host netns): the sandboxed plugin must not reach it.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    port = listener.getsockname()[1]
    response, prior = invoke(PROFILE, EVIL_CAP, {"probe": "network", "listener": ["127.0.0.1", port]}, deadline_ms=9000)
    result = wait_result(PROFILE, EVIL_CAP, prior, timeout=25)
    check("evil network to gate loopback listener denied inside packaged sandbox",
          result.get("ok") is True and (result.get("output") or {}).get("result") == "denied", result)
    check("evil env probe saw no GIDEON_CANARY (Core env carries it, plugin must not)",
          RESULT["probe_results"]["env"]["result"] == "denied"
          and CANARY not in str(RESULT["probe_results"]["env"]["detail"]))
    for name, value in unsandboxed_proof(port).items():
        check(f"unsandboxed proof: dummy_evil {name} probe succeeds outside the sandbox (sandbox denials not vacuous)",
              value == "allowed", value)
    listener.close()
    pids = plugin_pids()
    check("evil: plugin processes still alive after probes (no crash from probes)", len(pids) >= 4, pids)
    mark = len(UNREADABLE)
    hits = scan_pids(pids)
    check("evil: every /proc entry of the plugin processes readable", len(UNREADABLE) == mark, UNREADABLE[mark:][:10])
    check("evil: no repo, uv or real-home path in any plugin cmdline, environ, maps, mountinfo, cwd, root or fd",
          not hits, hits[:10])
    py = python_pids()
    RESULT["isolation"]["core1_plugin_pids"] = len(pids)
    RESULT["isolation"]["core1_plugin_python_pids"] = len(py)
    RESULT["isolation"]["nested_bwrap_ancestor"] = bool(py) and all(bwrap_ancestor(p) for p in py)
    check("isolation: every plugin python process is a descendant of a nested bwrap (sandbox used)",
          RESULT["isolation"]["nested_bwrap_ancestor"] is True, describe_pids(py))
    interpreters = {}
    bundled_runtime = os.path.realpath(installed_dir() / "runtime/python")
    host_python = os.path.realpath("/usr/bin/python3")
    for pid in py:
        try:
            exe = os.path.realpath(f"/proc/{pid}/exe")
        except OSError as exc:
            note_unreadable(pid, "exe", exc)
            exe = "?"
        interpreters[str(pid)] = {"exe": exe, "argv0": cmdline_of(pid).split(b"\0")[0].decode("utf-8", "replace")}
    RESULT["isolation"]["plugin_interpreters"] = interpreters
    RESULT["isolation"]["bundled_runtime"] = bundled_runtime
    RESULT["isolation"]["host_python"] = host_python

    def under(path, root):
        try:
            return os.path.commonpath([path, root]) == root
        except ValueError:
            return False

    check("isolation: plugin python executable realpath lies under the bundled runtime of the installed package",
          bool(py) and all(under(i["exe"], bundled_runtime) for i in interpreters.values()), interpreters)
    check("isolation: plugin python executable is not host /usr/bin/python3 (realpath)",
          bool(py) and all(i["exe"] != host_python and not under(i["exe"], host_python) for i in interpreters.values()),
          interpreters)
    core_stop(PROFILE)


def scenario_restart_running():
    """Core 2: enabled plugins come back after restart; S1 while plugins run; disable one."""
    core_start(PROFILE, "core2-restart", hub_args())
    wait_item(PROFILE, ECHO, lambda i: i["state"] == "running" and i["enabled"], 40, "echo back after restart")
    wait_item(PROFILE, EVIL, lambda i: i["state"] == "running" and i["enabled"], 40, "evil back after restart")
    s1_check(PROFILE, "S1 while plugins run after restart")
    snap = snapshot(PROFILE)
    check("restart: both plugins still running after S1", all(
        plugin_item(snap, p)["state"] == "running" for p in (ECHO, EVIL)),
        [plugin_item(snap, p) for p in (ECHO, EVIL)])
    response, prior = invoke(PROFILE, ECHO_CAP, {"text": "restart"})
    result = wait_result(PROFILE, ECHO_CAP, prior)
    check("restart: echo fresh process answers count 1 after restart", result.get("ok") is True
          and result["output"] == {"text": "RESTART", "count": 1}, result)
    response, prior = invoke(PROFILE, EVIL_CAP, {"probe": "env"}, deadline_ms=9000)
    result = wait_result(PROFILE, EVIL_CAP, prior)
    check("restart: evil env probe still denied after restart", (result.get("output") or {}).get("result")
          == "denied", result)
    pids = plugin_pids()
    check("restart: plugin processes are present before Core stop", len(pids) >= 4, pids)
    mark = len(UNREADABLE)
    hits = scan_pids(pids)
    check("restart: every /proc entry of the plugin processes readable", len(UNREADABLE) == mark, UNREADABLE[mark:][:10])
    check("restart: no repo, uv or real-home path in plugin processes", not hits,
          {"hits": hits[:10], "processes": describe_pids(pids)})
    response = plugin_op(PROFILE, "plugin_disable", EVIL)
    check("restart: plugin_disable evil ok", response.get("code") == "ok", response)
    wait_item(PROFILE, EVIL, lambda i: i["state"] == "disabled", 20, "evil disabled")
    check("restart: disabling evil leaves echo running", plugin_item(snapshot(PROFILE), ECHO)["state"]
          == "running", plugin_item(snapshot(PROFILE), ECHO))
    core_stop(PROFILE)


def scenario_tamper():
    """Tamper the installed echo payload while the Core is stopped: nothing runs, enable refused/quarantined."""
    hub_dir = core_root(PROFILE) / "hub-plugins"
    payloads = sorted(hub_dir.glob(f"{ECHO}-*.payload"))
    check("tamper: exactly one installed echo payload under profiles/main/core/hub-plugins",
          len(payloads) == 1, [p.name for p in payloads])
    payload = payloads[0]
    original = payload.read_bytes()
    check("tamper: payload bytes equal the fixture before tampering", original == ECHO_FIXTURE.read_bytes())
    with open(payload, "ab") as handle:
        handle.write(b"\n# tampered\n")
    check("tamper: payload file changed (size and sha)", payload.read_bytes() != original)
    core_start(PROFILE, "core3-tampered", hub_args())
    s1_check(PROFILE, "S1 after tamper")
    item = plugin_item(snapshot(PROFILE), ECHO)
    RESULT["notes"].append({"tampered_boot_item": item})
    check("tamper: echo not running after boot with a tampered payload", item["state"] != "running", item)
    check("tamper: echo quarantined (Hub) or failed with plugin_quarantined at boot",
          item["state"] == "quarantined" or item.get("last_error") == "plugin_quarantined", item)
    early = plugin_pids()
    check("tamper: no plugin process runs for the tampered payload", early == [], describe_pids(early))
    response, _ = invoke(PROFILE, ECHO_CAP, {"text": "x"})
    check("tamper: invoke is capability_unavailable", response.get("code") == "capability_unavailable", response)
    disabled = plugin_op(PROFILE, "plugin_disable", ECHO)
    check("tamper: plugin_disable after quarantine returns ok or not_enabled", disabled.get("code")
          in ("ok", "not_enabled"), disabled)
    enabled = plugin_op(PROFILE, "plugin_enable", ECHO)
    RESULT["notes"].append({"tampered_enable_response": enabled})
    time.sleep(1.5)
    item = plugin_item(snapshot(PROFILE), ECHO)
    check("tamper: enable of tampered payload does not reach running", item["state"] != "running", item)
    check("tamper: enable of tampered payload refused or quarantined, nothing runs", (
        enabled.get("code") != "ok") or item.get("last_error") == "plugin_quarantined",
        {"enable": enabled, "item": item})
    late = plugin_pids()
    check("tamper: still no plugin process after enable attempt", late == [], {
        "processes": describe_pids(late), "enable_code": enabled.get("code")})
    core_stop(PROFILE)
    payload.write_bytes(original)
    check("tamper: restoring the original bytes restores the fixture sha", sha256(payload) == sha256(ECHO_FIXTURE))



def scenario_recover_and_update_refused():
    core_start(PROFILE, "core4-recovered", hub_args())
    s1_check(PROFILE, "S1 after tamper restored")
    if plugin_item(snapshot(PROFILE), ECHO)["enabled"] is False:
        check("recover: enable echo after restore ok", plugin_op(PROFILE, "plugin_enable", ECHO).get("code")
              == "ok", "enable failed")
    wait_item(PROFILE, ECHO, lambda i: i["state"] == "running" and i["enabled"], 30, "echo running after restore")
    response, prior = invoke(PROFILE, ECHO_CAP, {"text": "recovered"})
    result = wait_result(PROFILE, ECHO_CAP, prior)
    check("recover: restored echo answers count 1", result.get("ok") is True and result["output"]
          == {"text": "RECOVERED", "count": 1}, result)
    pids = plugin_pids()
    check("recover: plugin process running while Core active", len(pids) >= 2, pids)
    # Update must be refused while this plugin-running Core is active. Only ONE package exists: use a
    # hardlinked copy (no extra space) of the installed tree as the update source; it is never consumed.
    update_src = S["work"] / "upd-src"
    proc = run(["cp", "-al", str(installed_dir()), str(update_src)], timeout=300)
    check("update: hardlinked copy of installed tree made (no extra data)", proc.returncode == 0,
          proc.stderr.decode()[-300:])
    rc, obj, err = inst("update", str(update_src))
    check("update: refused with exit 3 profile_active while plugin-running Core is active",
          rc == 3 and obj and obj.get("error") == "profile_active" and obj.get("profile") == PROFILE, err or obj)
    check("update: refused source not consumed", update_src.is_dir())
    check("update: plugin still running after refused update",
          plugin_item(snapshot(PROFILE), ECHO)["state"] == "running", plugin_item(snapshot(PROFILE), ECHO))
    core_stop(PROFILE)
    rc, obj, err = inst("update", str(update_src))
    check("update: after Core stop the same id is refused as already_installed (not applied)",
          rc != 0 and obj and obj.get("error") == "already_installed", err or obj)
    st = lst()
    check("update: ledger still current only 0.1.0 with no orphans", st["current"] == S["ident"]
          and st["previous"] is None and st["orphans"] == [], st)
    shutil.rmtree(update_src, ignore_errors=True)


def scenario_final():
    rc = run([str(installed_dir() / "runtime/python/bin/python3.13"), "-I", "-B",
              str(installed_dir() / "bin/gideon-verify")], timeout=900)
    check("final: gideon-verify passes on the installed package after tamper and restore", rc.returncode == 0,
          rc.stderr.decode()[-400:])
    check("final: no plugin process anywhere after all Core stops", plugin_pids() == [], plugin_pids())
    check("final: no Core still running", not S["cores"])


def main():
    started = time.monotonic()
    work = Path(tempfile.mkdtemp(prefix="gc0-", dir="/tmp"))
    S.update(work=work, home=work / "h", root=work / "r")
    S["home"].mkdir(mode=0o700)
    S["ident"] = None
    try:
        scenario("1 build", scenario_build)
        if S.get("ident"):
            scenario("1 install", scenario_install)
            scenario("2 isolation", scenario_isolation)
            scenario("3 core1 echo and evil", scenario_core1)
            scenario("4 core2 restart", scenario_restart_running)
            scenario("5 tamper", scenario_tamper)
            scenario("6 recover and update refused", scenario_recover_and_update_refused)
            scenario("7 final", scenario_final)
    finally:
        for profile in list(S["cores"]):
            core_stop_quiet(profile)
        try:
            shutil.rmtree(work)
        except FileNotFoundError:
            pass
        except OSError as exc:
            check("cleanup: temp dir removed", False, f"{work}: {exc}")
    head = S.get("commit")
    RESULT.update({
        "gate": GATE,
        "passed": len(CHECKS),
        "failed": len(FAILS),
        "ignored": len(IGNORED),
        "checks": CHECKS,
        "failures": FAILS,
        "commit": head,
        "dirty_at_build": RESULT["identity"].get("dirty_at_build"),
        "isolation_mode": RESULT["isolation"].get("mode"),
        "identity": RESULT["identity"],
        "scope": "plugin runtime (dummy_echo, dummy_evil) inside the installed relocatable package under an outer "
                 "bwrap without repo, uv or network; nested plugin bwrap; Hub approve/stage/install, enable, invoke, "
                 "revoke, re-approve, restart, tamper, update refused with profile_active; no physical devices",
        "physical_validation": "NOT_PERFORMED",
        "runtime_seconds": round(time.monotonic() - started, 1),
    })
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(RESULT, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: RESULT[k] for k in ("gate", "passed", "failed", "isolation_mode", "dirty_at_build",
                                             "runtime_seconds")}, indent=2))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
