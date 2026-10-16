#!/usr/bin/env python3
"""B4.2 update/rollback gate: versioned install, profiles, update, rollback, tamper, injected failures, fail-closed launch.

Usage: scripts/verify_b4_update.py   (stdlib only; no network; temp dirs only; budget about 15 min)
Builds gideon-base-0.1.0 and -0.1.1 (and 0.1.2 for tamper/injection when free space allows) from the
committed tree with build_package.py, installs them with gideon-install under a short INSTALL_ROOT,
and runs every profile's Core inside an outer bwrap that mounts only ROOT, /usr and the loader cache.
Writes target/evidence/b4-update.json. Exit 0 only when every check passes.
"""
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
EVIDENCE = REPO / "target/evidence/b4-update.json"
GATE = "B4_2_UPDATE_ROLLBACK"
ALICE, BOB = "alice", "bob"
V1, V2, V3 = "0.1.0", "0.1.1", "0.1.2"
BENIGN = "benign_fixture"
BENIGN_BYTES = b"benign fixture\n"
MIN_FREE_FOR_THIRD = int(2.5 * 1024 ** 3)
HUB_FIXTURE = REPO / "tests/fixtures/hub.json"

CHECKS, FAILS = [], []
RESULT = {"scenarios": {}, "isolation": None, "binary_sha256": {}, "release_binary_sha256": None,
          "build": {}, "skipped": {}, "notes": []}
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
        for profile in list(S["cores"]):  # a failed scenario must not leave a Core that blocks later ones
            core_stop_quiet(profile)


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


def id_of(version):
    return f"{version}-{S['commit'][:8]}"


def root():
    return S["root"]


def core_root(profile):
    return S["root"] / "profiles" / profile / "core"


def inst(*args, timeout=900, env_extra=None):
    """Run the repo gideon-install against ROOT. Returns (rc, parsed JSON or None, stderr tail)."""
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
    S["cur"] = obj["current"]  # launcher path always follows the ledger, never the intended state
    return obj


def ledger_bytes():
    return (S["root"] / "install.json").read_bytes()


def links():
    return {name: (os.readlink(S["root"] / name) if os.path.islink(S["root"] / name) else None)
            for name in ("current", "previous")}


def tail(path):
    return path.read_bytes()[-800:].decode("utf-8", "replace") if path.exists() else ""


def bwrap_argv(argv, extra_ro=()):
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
    for path in extra_ro:
        args += ["--ro-bind", path, path]
    return args + ["--chdir", "/", "--", *argv]


def probe_isolation():
    try:
        outer = run(bwrap_argv(["/bin/true"]), timeout=60)
    except RuntimeError as exc:
        RESULT["outer_probe_error"] = str(exc)
        return "host"
    RESULT["outer_probe_rc"] = outer.returncode
    if outer.returncode != 0:
        RESULT["fallback_reason"] = outer.stderr.decode("utf-8", "replace")[-300:]
        return "host"
    nested = ["/usr/bin/bwrap", "--unshare-all", "--ro-bind", "/usr", "/usr",
              "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib", "/lib64",
              "--symlink", "usr/bin", "/bin", "--proc", "/proc", "--dev", "/dev", "--", "/bin/true"]
    try:
        RESULT["nested_probe_rc"] = run(bwrap_argv(nested), timeout=60).returncode
    except RuntimeError as exc:
        RESULT["nested_probe_error"] = str(exc)
    return "outer_bwrap"


def launcher_argv(profile, core_args=()):
    """Packaged launcher of the version that ROOT/current should point to (tracked as S["cur"])."""
    pkg = S["root"] / "versions" / S["cur"]
    return [str(pkg / "runtime/python/bin/python3.13"), "-I", "-B", str(pkg / "bin/gideon-launch"),
            "--install-root", str(S["root"]), profile, *core_args]


def hub_args():
    return ("--hub-catalog", str(S["catalog"]), sha256(S["catalog"]))


def tts_extra():
    return [str(S["cat"])]


def tree_pids(root_pid):
    kids = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            fields = Path(f"/proc/{entry}/stat").read_text().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        kids.setdefault(int(fields[1]), []).append(int(entry))
    seen, stack = [root_pid], [root_pid]
    while stack:
        for child in kids.get(stack.pop(), []):
            seen.append(child)
            stack.append(child)
    return seen


def scan_tree(root_pid):
    hits, seen = [], tree_pids(root_pid)
    for pid in seen:
        blobs = []
        for name in ("cmdline", "environ", "maps", "mountinfo"):
            try:
                blobs.append(Path(f"/proc/{pid}/{name}").read_bytes())
            except OSError:
                pass
        for link in ("cwd", "root"):
            try:
                blobs.append(os.readlink(f"/proc/{pid}/{link}").encode())
            except OSError:
                pass
        try:
            for fd in os.listdir(f"/proc/{pid}/fd"):
                try:
                    blobs.append(os.readlink(f"/proc/{pid}/fd/{fd}").encode())
                except OSError:
                    pass
        except OSError:
            pass
        for mark in (REPO_PATH, UV_MARK):
            if any(mark in blob for blob in blobs):
                hits.append({"pid": pid, "mark": mark.decode()})
    return len(seen), hits


def core_start(profile, label, core_args=(), extra_ro=()):
    if profile in S["cores"]:
        raise RuntimeError(f"{profile} Core already running")
    argv = launcher_argv(profile, core_args)
    if S.get("isolation") == "outer_bwrap":
        argv = bwrap_argv(argv, extra_ro)
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
    return proc


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
    check(f"{label}: no residual Core or worker processes after stop", not residual, f"pgid {proc.pid}")
    check(f"{label}: Core exit status 0 after SIGTERM", rc == 0, f"rc={rc}")
    return rc


def core_stop_quiet(profile):
    try:
        core_stop(profile)
    except Exception as exc:
        check(f"cleanup: stop {profile} Core", False, f"{type(exc).__name__}: {exc}")


def req(profile, op, **fields):
    S["n"] = S.get("n", 0) + 1
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(10)
        sock.connect(str(core_root(profile) / "core.sock"))
        sock.sendall((json.dumps({"version": 1, "request_id": f"b4u_{S['n']}", "op": op, **fields}) + "\n")
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


def compact(snap):
    if not snap:
        return None
    keys = ("state", "wake_status", "stt_status", "speech_status", "configuration_status")
    out = {k: snap.get(k) for k in keys}
    out["command"] = (snap.get("command") or {}).get("code")
    out["base_pack"] = (snap.get("base_pack") or {}).get("preflight")
    return out


def wait_snapshot(profile, predicate, timeout, what):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = snapshot(profile)
        if predicate(last):
            return last
        time.sleep(0.05)
    log = S["work"] / f"{S['cores'][profile]['label']}.log"
    raise TimeoutError(f"{what} not reached: {json.dumps(compact(last))}; core log tail: {tail(log)[-500:]}")


def kinds(snap):
    return [event.get("kind") for event in snap.get("events", [])]


def s1_check(profile, label, audible=True):
    # With audible_feedback false the Core records speech_status "disabled" (command_terminal); no speech runs.
    want_speech = "completed" if audible else "disabled"
    snap = wait_snapshot(
        profile,
        lambda s: s.get("state") == "idle" and s.get("wake_status") == "replay_finished"
        and (s.get("command") or {}).get("code") == "command_success"
        and s.get("stt_status") == "ready" and s.get("speech_status") == want_speech,
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
    if audible:
        check(f"{label}: speech started and finished on virtual TTS",
              snap["speech_status"] == "completed" and speech.get("samples", 0) > 0
              and "speech_started" in kinds(snap) and "speech_completed" in kinds(snap),
              {"speech_status": snap["speech_status"], "speech": speech, "kinds": kinds(snap)})
    else:
        check(f"{label}: audible_feedback false gives speech_status disabled and no speech samples",
              snap["speech_status"] == "disabled" and "speech_started" not in kinds(snap),
              {"speech_status": snap["speech_status"], "kinds": kinds(snap)})
    return snap


def core_exe_check(profile, version, label):
    want = os.path.realpath(S["root"] / "versions" / id_of(version) / "bin/gideon-base")
    exes = []
    for pid in tree_pids(S["cores"][profile]["proc"].pid):
        try:
            exes.append(os.readlink(f"/proc/{pid}/exe"))
        except OSError:
            pass
    check(f"{label}: Core process executes packaged bin/gideon-base of {version}", want in exes,
          {"want": want, "exes": exes[:10]})


def profile_refs(profile, ident):
    """Count files under the profile state that embed the version path (rendered by gideon-configure)."""
    needle = f"versions/{ident}".encode()
    base = S["root"] / "profiles" / profile / "profile"
    hits = {}
    for path in base.rglob("*"):
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= (1 << 20):
            count = path.read_bytes().count(needle)
            if count:
                hits[path.relative_to(base).as_posix()] = count
    return hits


def hub_of(profile):
    return snapshot(profile)["hub"]


def hub_entry(hub):
    return next(e for e in hub["entries"] if e["plugin_id"] == BENIGN)


def hub_record(hub):
    return next((r for r in hub["installed"] if r["plugin_id"] == BENIGN), None)


def hub_install_benign(profile):
    """Approve, stage (repo hub_import.py as external client) and install the benign fixture in profile."""
    cr = core_root(profile)
    hub = hub_of(profile)
    entry = hub_entry(hub)
    approved = req(profile, "hub_approve", revision=hub["approval_revision"], plugin_id=BENIGN,
                   manifest_sha256=entry["manifest_sha256"], permissions=entry["permissions"],
                   publisher_unverified_ack=True)
    check(f"{profile}: hub explicit manifest approval accepted", approved.get("code") == "ok", approved)
    source = S["work"] / f"benign-{profile}.bin"
    source.write_bytes(BENIGN_BYTES)
    staged = run(["python3", str(REPO / "scripts/hub_import.py"), "--root", str(cr), "--plugin", BENIGN,
                  "--source", str(source)], timeout=120)
    check(f"{profile}: repo hub_import.py stages payload as external client", staged.returncode == 0,
          staged.stderr.decode()[-600:])
    hub = hub_of(profile)
    digest = hub_entry(hub)["manifest_sha256"]
    installed = req(profile, "hub_install", revision=hub["install_revision"], plugin_id=BENIGN,
                    manifest_sha256=digest)
    check(f"{profile}: hub install ok", installed.get("code") == "ok", installed)
    record = hub_record(hub_of(profile))
    check(f"{profile}: benign plugin installed with runtime disabled",
          record is not None and record["state"] == "installed" and record["runtime"] == "disabled", record)


def set_pref(profile, revision, audible):
    return req(profile, "preferences", revision=revision, audible_feedback=audible, session_timeout_ms=30000)


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
               env=build_env, timeout=900)
    pkg = out_dir / f"gideon-base-{version}"
    check(f"build {version}: build_package.py --version {version} exits 0", proc.returncode == 0
          and (pkg / "PACKAGE.json").is_file(), proc.stderr.decode()[-800:])
    manifest = json.loads((pkg / "PACKAGE.json").read_text(encoding="utf-8"))
    check(f"build {version}: PACKAGE.json version and commit match", manifest.get("version") == version
          and manifest.get("commit") == S["commit"], {k: manifest.get(k) for k in ("version", "commit")})
    RESULT["binary_sha256"][version] = sha256(pkg / "bin/gideon-base")
    RESULT["build"][version] = {"dirty": manifest.get("dirty"), "files": len(manifest.get("files", []))}
    RESULT["release_binary_sha256"] = sha256(REPO / "target/release/gideon-base")
    return pkg, manifest


# ---------------------------------------------------------------- scenarios

def scenario_build():
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True,
                          timeout=30).stdout.strip()
    S["commit"] = head
    S["pkg1"], m1 = build_pkg(V1, S["work"] / "o1")
    S["pkg2"], m2 = build_pkg(V2, S["work"] / "o2")
    tracked = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"],
                             capture_output=True, text=True, timeout=60).stdout
    check("build: no tracked file differs from HEAD (build is the committed tree)", tracked == "", tracked[-400:])
    RESULT["notes"].append({"dirty_flag": {"v1": m1.get("dirty"), "v2": m2.get("dirty")},
                            "reason": "build_package.py flags any git status entry, including the untracked "
                                      "gate script scripts/verify_b4_update.py; no tracked file differs"})
    RESULT["commit"] = head
    RESULT["dirty_at_build"] = m1.get("dirty")


def scenario_install():
    rc, obj, err = inst("install", str(S["pkg1"]))
    check("1 install: gideon-install install v0.1.0 exits 0 with ok", rc == 0 and obj and obj.get("ok") is True,
          err or obj)
    S["cur"] = obj["current"]
    check("1 install: source consumed by rename on the same filesystem", obj.get("source") == "moved"
          and not S["pkg1"].exists(), obj)
    st = lst()
    check("1 install: list shows current 0.1.0 and no previous", st["current"] == id_of(V1)
          and st["previous"] is None and st["revision"] == 1 and len(st["versions"]) == 1 and st["orphans"] == [],
          st)
    rc, obj, err = inst("profile", "create", ALICE)
    check("1 profile: alice created", rc == 0 and obj.get("created") is True, err or obj)
    rc, obj, err = inst("profile", "create", BOB)
    check("1 profile: bob created", rc == 0 and obj.get("created") is True, err or obj)
    check("1 profile: list shows alice and bob", lst()["profiles"] == [ALICE, BOB], lst()["profiles"])
    check("1 install: ROOT is 0700 and owned by this user", stat.S_IMODE(os.lstat(S["root"]).st_mode) == 0o700)
    S["home_names"] = sorted(os.listdir(Path.home()))
    S["sentinel_pre"] = tree_state(S["sentinel"])


def scenario_hidden():
    S["isolation"] = probe_isolation()
    RESULT["isolation"] = {"mode": S["isolation"]}
    if S["isolation"] != "outer_bwrap":
        RESULT["notes"].append("outer bwrap unavailable; Cores run without hidden-source isolation")
        return
    probe = run(bwrap_argv(["/bin/sh", "-c", "[ ! -e /home ] && echo NOHOME; cat /proc/net/dev"]), timeout=60)
    text = probe.stdout.decode("utf-8", "replace")
    check("2 hidden: outer sandbox has no /home (repo and ~/.local/share/uv unreachable)",
          probe.returncode == 0 and "NOHOME" in text, probe.stderr.decode()[-400:])
    ifaces = [line.split(":")[0].strip() for line in text.splitlines()[2:] if ":" in line]
    RESULT["isolation"]["netns_interfaces"] = ifaces
    check("2 hidden: sandbox network namespace exposes only lo", ifaces == ["lo"], ifaces)


def scenario_alice_v1():
    S["catalog"] = S["cat"] / "hub.json"
    shutil.copyfile(HUB_FIXTURE, S["catalog"])
    core_start(ALICE, "alice-v010", hub_args(), tts_extra())
    scanned, hits = scan_tree(S["cores"][ALICE]["proc"].pid)
    check(f"2 hidden: alice Core tree ({scanned} processes) has no repo or uv path", scanned >= 1 and not hits,
          hits[:10])
    core_exe_check(ALICE, V1, "2 alice v0.1.0")
    s1_check(ALICE, "2 alice v0.1.0 S1")
    hub_install_benign(ALICE)
    rev = snapshot(ALICE)["preferences"]["revision"]
    changed = set_pref(ALICE, rev, False)
    check("2 alice: preference update accepted (audible_feedback false)", changed.get("code") == "ok"
          and changed["preferences"]["audible_feedback"] is False, changed)
    snap = snapshot(ALICE)["preferences"]
    check("2 alice: snapshot confirms audible_feedback false at revision 1",
          snap["audible_feedback"] is False and snap["revision"] == 1, snap)
    core_stop(ALICE)


def scenario_update():
    core_start(ALICE, "alice-v010-running", hub_args(), tts_extra())
    before = (ledger_bytes(), lst(), links())
    rc, obj, err = inst("update", str(S["pkg2"]))
    check("3 update: refused with exit 3 profile_active while alice Core runs",
          rc == 3 and obj and obj.get("error") == "profile_active" and obj.get("profile") == ALICE, err or obj)
    check("3 update: refusal leaves ledger, list and current/previous unchanged",
          (ledger_bytes(), lst(), links()) == before)
    check("3 update: refused source package not consumed", S["pkg2"].is_dir())
    core_stop(ALICE)
    rc, obj, err = inst("update", str(S["pkg2"]))
    check("3 update: update to v0.1.1 exits 0 with ok after Core stopped", rc == 0 and obj and obj.get("ok") is True,
          err or obj)
    check("3 update: source consumed by rename", obj and obj.get("source") == "moved" and not S["pkg2"].exists(), obj)
    st = lst()
    check("3 update: list shows current 0.1.1 previous 0.1.0 and exactly those two versions",
          st["current"] == id_of(V2) and st["previous"] == id_of(V1) and sorted(e["id"] for e in st["versions"])
          == sorted([id_of(V1), id_of(V2)]) and st["orphans"] == [], st)


def scenario_alice_v2():
    before_old = profile_refs(ALICE, id_of(V1))
    core_start(ALICE, "alice-v011", hub_args(), tts_extra())
    s1_check(ALICE, "4 alice v0.1.1 S1", audible=False)
    core_exe_check(ALICE, V2, "4 alice v0.1.1")
    snap = snapshot(ALICE)
    check("4 alice: audible_feedback false persisted across update (revision 1)",
          snap["preferences"]["audible_feedback"] is False and snap["preferences"]["revision"] == 1,
          snap["preferences"])
    check("4 alice: installed benign plugin preserved across update",
          hub_record(snap["hub"]) is not None and hub_record(snap["hub"])["state"] == "installed", snap["hub"].get("installed"))
    new_refs, old_refs = profile_refs(ALICE, id_of(V2)), profile_refs(ALICE, id_of(V1))
    check("4 configure: profile re-rendered and pinned to the 0.1.1 package path",
          bool(new_refs) and not old_refs, {"new": new_refs, "old_before": before_old, "old_after": old_refs})
    core_stop(ALICE)


def scenario_bob():
    core_start(ALICE, "alice-concurrent", hub_args(), tts_extra())
    core_start(BOB, "bob-concurrent")
    check("5 concurrent: alice and bob Cores both alive",
          S["cores"][ALICE]["proc"].poll() is None and S["cores"][BOB]["proc"].poll() is None)
    sa, sb = core_root(ALICE) / "core.sock", core_root(BOB) / "core.sock"
    check("5 concurrent: distinct sockets per profile", sa != sb and sa.exists() and sb.exists(), f"{sa} {sb}")
    snap_a, snap_b = snapshot(ALICE), snapshot(BOB)
    check("5 bob: default preferences (audible_feedback true, revision 0, timeout 30000)",
          snap_b["preferences"]["audible_feedback"] is True and snap_b["preferences"]["revision"] == 0
          and snap_b["preferences"]["session_timeout_ms"] == 30000, snap_b["preferences"])
    bob_hub = snap_b.get("hub")  # Option: absent without --hub-catalog, so bob has no Hub state at all
    check("5 bob: no alice approvals or installed plugins (no Hub state, or nothing installed or approved)",
          bob_hub is None or (bob_hub["installed"] == [] and hub_entry(bob_hub)["status"] == "not_installed"
                              and not hub_entry(bob_hub)["permissions_approved"]),
          None if bob_hub is None else {"installed": bob_hub["installed"]})
    check("5 bob: alice Core sees its own state (audible false, benign installed)",
          snap_a["preferences"]["audible_feedback"] is False and hub_record(snap_a["hub"]) is not None,
          snap_a["preferences"])
    check("5 concurrent: alice and bob snapshots differ", snap_a["preferences"] != snap_b["preferences"])
    names = [p.name for p in (S["root"] / "profiles" / BOB).rglob("*")]
    check("5 bob: profile tree has no benign plugin payload or alice state", not any(BENIGN in n for n in names),
          [n for n in names if BENIGN in n][:5])
    core_stop(BOB)
    core_stop(ALICE)


def scenario_rollback():
    rc, obj, err = inst("rollback")
    check("6 rollback: exits 0 to current 0.1.0 previous 0.1.1", rc == 0 and obj and obj.get("ok") is True
          and obj.get("current") == id_of(V1) and obj.get("previous") == id_of(V2), err or obj)
    st = lst()
    check("6 rollback: list shows current 0.1.0 previous 0.1.1", st["current"] == id_of(V1)
          and st["previous"] == id_of(V2), st)
    core_start(ALICE, "alice-rollback", hub_args(), tts_extra())
    s1_check(ALICE, "6 alice after rollback S1", audible=False)
    core_exe_check(ALICE, V1, "6 alice after rollback")
    snap = snapshot(ALICE)
    check("6 alice: preference still persisted after rollback", snap["preferences"]["audible_feedback"] is False
          and snap["preferences"]["revision"] == 1, snap["preferences"])
    core_stop(ALICE)
    rc, obj, err = inst("rollback")
    check("6 rollback: second rollback returns to current 0.1.1", rc == 0 and obj and obj.get("current") == id_of(V2)
          and obj.get("previous") == id_of(V1), err or obj)
    st = lst()
    check("6 rollback: list shows current 0.1.1 previous 0.1.0", st["current"] == id_of(V2)
          and st["previous"] == id_of(V1), st)


def scenario_tamper():
    free = shutil.disk_usage("/tmp").free
    if free < MIN_FREE_FOR_THIRD:
        RESULT["skipped"]["v0.1.2_tamper_and_injection"] = f"only {free} bytes free in /tmp"
        check("7 tamper: skipped, free space below 2.5 GiB", False, RESULT["skipped"])
        return
    pkg3, m3 = build_pkg(V3, S["work"] / "o3")
    S["pkg3"] = pkg3
    victim = pkg3 / "scripts/stt_worker.py"
    original = victim.read_bytes()
    original_sha = sha256(victim)
    before = (ledger_bytes(), lst(), links())
    with open(victim, "ab") as handle:
        handle.write(b"\n")
    rc, obj, err = inst("update", str(pkg3))
    check("7 tamper: update of tampered 0.1.2 exits 4 verify_failed", rc == 4 and obj and obj.get("error")
          == "verify_failed", err or obj)
    check("7 tamper: ledger, list and links unchanged after refusal", (ledger_bytes(), lst(), links()) == before)
    check("7 tamper: tampered source not consumed", pkg3.is_dir())
    victim.write_bytes(original)
    check("7 tamper: restoring the byte restores the original sha", sha256(victim) == original_sha)
    check("7 tamper: restored 0.1.2 source passes gideon-verify", run(
        [str(pkg3 / "runtime/python/bin/python3.13"), "-I", "-B", str(pkg3 / "bin/gideon-verify")],
        timeout=900).returncode == 0)
    id3 = id_of(V3)
    for point in ("ledger", "switch"):
        before = (ledger_bytes(), lst(), links())
        rc, obj, err = inst("update", str(pkg3), env_extra={"GIDEON_INSTALL_FAIL_AT": point,
                                                            "GIDEON_INSTALL_FORCE_COPY": "1"})
        check(f"7 inject {point}: update exits 99 with injected_failure", rc == 99 and obj
              and obj.get("error") == "injected_failure" and obj.get("point") == point, err or obj)
        after = lst()
        check(f"7 inject {point}: ledger and current/previous unchanged, state valid (list rc 0)",
              ledger_bytes() == before[0] and after["current"] == before[1]["current"]
              and after["previous"] == before[1]["previous"] and after["revision"] == before[1]["revision"],
              after)
        check(f"7 inject {point}: copy source intact, orphan versions/{id3} listed", pkg3.is_dir()
              and after["orphans"] == [id3], after["orphans"])
        leftovers = sorted(n for n in (".current.tmp", ".previous.tmp", ".install.json.tmp")
                           if os.path.lexists(S["root"] / n))
        expected = {"ledger": [".install.json.tmp"],
                    "switch": [".current.tmp", ".install.json.tmp", ".previous.tmp"]}[point]
        check(f"7 inject {point}: temporary leftovers exactly {expected} before next command",
              leftovers == expected, leftovers)
        rc, obj, err = inst("update", str(pkg3))
        check(f"7 inject {point}: next command cleans leftovers and refuses the orphan with exit 5", rc == 5 and obj
              and obj.get("error") == "orphan_conflict", err or obj)
        check(f"7 inject {point}: next command left ledger unchanged and no temp leftovers",
              ledger_bytes() == before[0] and not any(os.path.lexists(S["root"] / n) for n in
                                                      (".current.tmp", ".previous.tmp", ".install.json.tmp")))
        # documented manual step: the orphan version directory is removed by hand (tool never deletes it)
        shutil.rmtree(S["root"] / "versions" / id3)
        check(f"7 inject {point}: state valid after manual orphan removal", lst()["orphans"] == [])
    rc, obj, err = inst("update", str(pkg3))
    check("7 update: valid 0.1.2 update exits 0 (rename path)", rc == 0 and obj and obj.get("ok") is True
          and obj.get("dropped") == id_of(V1), err or obj)
    check("7 update: 0.1.2 source consumed by rename", obj and obj.get("source") == "moved" and not pkg3.exists(), obj)
    st = lst()
    check("7 update: list shows current 0.1.2 previous 0.1.1 and 0.1.0 dropped", st["current"] == id3
          and st["previous"] == id_of(V2) and not (S["root"] / "versions" / id_of(V1)).exists() and st["orphans"] == [],
          st)


def scenario_fail_closed():
    stash = {}
    lst()  # sync S["cur"] from the ledger before breaking anything

    def launch_fail(label, expect):
        assert not S["cores"], "no Core may be running for the fail-closed launch"
        stale = [p for p in S["root"].rglob("core.sock")]
        for path in stale:
            path.unlink()
        if stale:
            RESULT["notes"].append({"stale_core_sock_removed_before": label, "paths": [str(x) for x in stale]})
        proc = run(launcher_argv(ALICE), timeout=120)
        socks = [str(p) for p in S["root"].rglob("core.sock")]
        check(f"8 {label}: gideon-launch exits non-zero with {expect}", proc.returncode != 0
              and expect.encode() in proc.stderr, {"rc": proc.returncode, "stderr": proc.stderr.decode()[-300:]})
        check(f"8 {label}: no core.sock created", not socks, socks)

    ledger = S["root"] / "install.json"
    stash["ledger"] = ledger.read_bytes()
    ledger.write_bytes(stash["ledger"][: len(stash["ledger"]) // 2])
    launch_fail("corrupt ledger", "ledger_invalid")
    ledger.write_bytes(stash["ledger"])
    check("8 restore: ledger bytes restored", ledger.read_bytes() == stash["ledger"])

    cur = S["root"] / "current"
    os.unlink(cur)
    os.symlink("versions/0.9.9-deadbeef", cur)
    launch_fail("dangling current symlink", "layout_invalid")
    os.unlink(cur)
    os.symlink(os.path.join("versions", S["cur"]), cur)
    check("8 restore: current symlink points at the installed version again", os.readlink(cur)
          == os.path.join("versions", S["cur"]))

    obj = json.loads(stash["ledger"].decode("utf-8"))
    obj["extra"] = 1
    ledger.write_bytes(json.dumps(obj).encode("utf-8"))
    launch_fail("extra key in ledger", "ledger_invalid")
    ledger.write_bytes(stash["ledger"])
    check("8 restore: ledger bytes restored after extra-key case", ledger.read_bytes() == stash["ledger"])

    os.chmod(S["root"], 0o755)
    launch_fail("ROOT mode 0755", "root_invalid")
    os.chmod(S["root"], 0o700)
    check("8 restore: ROOT mode back to 0700", stat.S_IMODE(os.lstat(S["root"]).st_mode) == 0o700)
    st = lst()
    check("8 restore: installer list valid after all fail-closed cases", st["current"] == S["cur"]
          and st["orphans"] == [], st)
    core_start(ALICE, "alice-restored", hub_args(), tts_extra())
    s1_check(ALICE, "8 restored launch S1", audible=False)
    snap = snapshot(ALICE)
    check("8 restored launch: alice preference still audible false", snap["preferences"]["audible_feedback"] is False,
          snap["preferences"])
    core_stop(ALICE)


def scenario_isolation():
    check("9 isolation: real HOME top-level entries unchanged after install, Cores and fail-closed runs",
          sorted(os.listdir(Path.home())) == S["home_names"], "HOME entries changed")
    check("9 isolation: sentinel directory outside the temp parent unchanged",
          tree_state(S["sentinel"]) == S["sentinel_pre"])
    st = lst()
    for ident in (st["current"], st["previous"]):
        if ident is None:
            continue
        pkg = S["root"] / "versions" / ident
        rc = run([str(pkg / "runtime/python/bin/python3.13"), "-I", "-B", str(pkg / "bin/gideon-verify")],
                 timeout=900)
        check(f"9 retained {ident}: gideon-verify passes (package dir unchanged)", rc.returncode == 0,
              rc.stderr.decode()[-400:])
    check("9 isolation: no Core still running at the end", not S["cores"])
    RESULT["notes"].append({"core_sock_after_clean_stops": [str(p.relative_to(S["root"]))
                                                           for p in S["root"].rglob("core.sock")]})


def main():
    started = time.monotonic()
    work = Path(tempfile.mkdtemp(prefix="gb42-", dir="/tmp"))
    sentinel = Path(tempfile.mkdtemp(prefix="gb42s-", dir="/tmp"))
    S.update(work=work, home=work / "home", root=work / "r", cat=work / "cat", sentinel=sentinel)
    S["home"].mkdir(mode=0o700)
    S["cat"].mkdir(mode=0o755)
    (sentinel / "keep.txt").write_bytes(b"preserved")
    try:
        scenario("1 build", scenario_build)
        scenario("1 install", scenario_install)
        scenario("2 hidden", scenario_hidden)
        scenario("2 alice v0.1.0", scenario_alice_v1)
        scenario("3 update", scenario_update)
        scenario("4 alice v0.1.1", scenario_alice_v2)
        scenario("5 bob", scenario_bob)
        scenario("6 rollback", scenario_rollback)
        scenario("7 tamper", scenario_tamper)
        scenario("8 fail-closed", scenario_fail_closed)
        scenario("9 isolation", scenario_isolation)
    finally:
        for profile in list(S["cores"]):
            core_stop_quiet(profile)
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
        "ignored": 0,
        "checks": CHECKS,
        "failures": FAILS,
        "commit": S.get("commit"),
        "dirty_at_build": RESULT.get("dirty_at_build"),
        "isolation_mode": S.get("isolation"),
        "scope": "offline versioned install of relocatable packages: install, update, rollback, profiles, "
                 "hidden-source Cores on virtual PCM/TTS, Hub approve/stage/install, tamper, injected failures, "
                 "fail-closed launch; no network, no downloads, no physical devices",
        "physical_validation": "NOT_PERFORMED",
        "runtime_seconds": round(time.monotonic() - started, 1),
    })
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(RESULT, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: RESULT[k] for k in ("gate", "passed", "failed", "isolation_mode", "runtime_seconds")},
                     indent=2))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
