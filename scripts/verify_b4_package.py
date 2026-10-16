#!/usr/bin/env python3
"""B4 relocatable package gate: build, relocate, hidden-source Core, native S1, Hub, restart, tamper, guards.

Usage: scripts/verify_b4_package.py   (stdlib only; no network; temp dirs only)
Hidden-source isolation: outer bwrap mounting only the package prefix, STATE, /usr, /lib,
/lib64, /bin, /sbin, ld.so.cache, /proc, /dev and a tmpfs /tmp, with --unshare-all.
If nested user namespaces fail, falls back to a cleared environment plus a /proc scan.
Writes target/evidence/b4-package.json. Exit 0 only when every check passes.
"""
import fnmatch
import errno
import hashlib
import json
import mmap
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
HOME_MARK = b"/home/lucas"
PKG_NAME = "gideon-base-0.1.0"
RELOCATED = "gideon-b4-relocated"
BENIGN = "benign_fixture"
BENIGN_BYTES = b"benign fixture\n"
EVIDENCE = REPO / "target/evidence/b4-package.json"
FIXTURE_ID = "wake-hey-brave__bf_emma__clean"
BUILD_MARKS = [REPO_PATH, HOME_MARK, UV_MARK]
ALLOWED = [
    ("runtime/python/lib/python3.13/_sysconfigdata*.py",
     "CPython sysconfig: build prefix string of the uv install dir; not read as input at runtime"),
]
NETWORK_TOKENS = [b"curl", b"wget", b"urllib", b"http.client", b"urlopen", b"requests", b"http://", b"https://"]

CHECKS = []
FAILS = []
UNREADABLE = []  # /proc entries of live processes that could not be read (a vanished process is not an entry here)
IGNORED = []  # items the gate could not check; only recorded when GIDEON_ALLOW_NO_ISOLATION=1
ALLOW_NO_ISOLATION = os.environ.get("GIDEON_ALLOW_NO_ISOLATION") == "1"
RESULT = {"scenarios": {}, "isolation": None, "allowlisted": {}, "network": None}
S = {}


def check(name, ok, detail=""):
    if ok:
        CHECKS.append(name)
    else:
        FAILS.append({"name": name, "detail": str(detail)[:3000]})
        print(f"FAIL {name}: {str(detail)[:800]}", file=sys.stderr)


def note_unreadable(pid, entry, exc):
    code = getattr(exc, "errno", None)
    if code not in (errno.ENOENT, errno.ESRCH):
        UNREADABLE.append({"pid": pid, "entry": entry, "errno": code, "error": str(exc)})


def isolation_unavailable(reason):
    """Hidden-source isolation missing: a failure, unless GIDEON_ALLOW_NO_ISOLATION=1 records it as ignored."""
    if ALLOW_NO_ISOLATION:
        IGNORED.append({"item": "hidden-source isolation", "reason": str(reason)[-300:]})
    else:
        check("3 hidden: outer bwrap isolation available (or set GIDEON_ALLOW_NO_ISOLATION=1 to record it as ignored)",
              False, reason)


def scenario(label, fn):
    try:
        fn()
        RESULT["scenarios"][label] = "done"
    except Exception as exc:
        RESULT["scenarios"][label] = "raised"
        check(f"{label}: completed without exception", False, f"{type(exc).__name__}: {exc}")
        core_stop_quiet()


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_bytes(path, needle):
    """Return (count, samples) of needle inside a regular file, streaming through mmap."""
    if path.stat().st_size == 0:
        return 0, []
    count, samples = 0, []
    with open(path, "rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as blob:
        at = blob.find(needle)
        while at != -1:
            count += 1
            if len(samples) < 3:
                samples.append(blob[at:at + 96].split(b"\x00")[0].decode("utf-8", "replace"))
            at = blob.find(needle, at + 1)
    return count, samples


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


def runtime_py(prefix):
    return prefix / "runtime/python/bin/python3.13"


def require_package():
    if "prefix" not in S:
        raise RuntimeError("package not built or relocated")


def bwrap_argv(prefix, state, extra_ro, argv):
    args = ["/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--clearenv",
            "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", str(state),
            "--ro-bind", "/usr", "/usr",
            "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib", "/lib64",
            "--symlink", "usr/bin", "/bin", "--symlink", "usr/bin", "/sbin",
            "--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--ro-bind", str(prefix), str(prefix), "--bind", str(state), str(state)]
    for path in extra_ro:
        args += ["--ro-bind", path, path]
    return args + ["--chdir", "/", "--", *argv]


def launch(argv, extra_ro=()):
    if S.get("isolation") == "outer_bwrap":
        return bwrap_argv(S["prefix"], S["state"], extra_ro, argv), host_env()
    return argv, {"PATH": "/usr/bin:/bin", "HOME": str(S["state"])}


def probe_isolation():
    nested = ["/usr/bin/bwrap", "--unshare-all", "--ro-bind", "/usr", "/usr",
              "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib", "/lib64",
              "--symlink", "usr/bin", "/bin", "--proc", "/proc", "--dev", "/dev", "--", "/bin/true"]
    try:
        probe = run(bwrap_argv(S["prefix"], S["state"], [], nested), timeout=60)
        RESULT["nested_probe_rc"] = probe.returncode
        return "outer_bwrap" if probe.returncode == 0 else "cmdline_fd_scan"
    except RuntimeError as exc:
        RESULT["nested_probe_error"] = str(exc)
        return "cmdline_fd_scan"


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


def scan_tree(root_pid):
    seen = tree_pids(root_pid)
    hits = []
    for pid in seen:
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
    return len(seen), hits


def tail(label):
    path = S["work"] / f"{label}.log"
    return path.read_bytes()[-800:].decode("utf-8", "replace") if path.exists() else ""


def core_start(label, extra=(), extra_ro=()):
    if "core" in S:
        raise RuntimeError("a Core is already running")
    if S.get("isolation") != "outer_bwrap" and not ALLOW_NO_ISOLATION:
        raise RuntimeError("outer bwrap isolation not available; refusing to run a Core unisolated")
    cmd, env = launch([str(S["prefix"] / "bin/gideon-core"), str(S["state"]), *extra], extra_ro)
    with open(S["work"] / f"{label}.log", "wb") as log:
        proc = subprocess.Popen(cmd, env=env, cwd="/", stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                start_new_session=True)
    S["core"], S["core_label"] = proc, label
    sock = S["state"] / "core" / "core.sock"
    deadline = time.monotonic() + 90
    while True:
        if proc.poll() is not None:
            raise RuntimeError(f"{label} exited rc={proc.returncode}: {tail(label)}")
        if sock.exists():
            try:
                with socket.socket(socket.AF_UNIX) as probe:
                    probe.settimeout(2)
                    probe.connect(str(sock))
                return proc
            except OSError:
                pass
        if time.monotonic() > deadline:
            raise TimeoutError(f"{label} socket not ready: {tail(label)}")
        time.sleep(0.05)


def group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def signal_group(pgid, sig):
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def core_stop():
    proc = S.pop("core", None)
    if proc is None:
        return None
    label = S.pop("core_label", "core")
    if proc.poll() is None:
        # SIGTERM only the Core binary (bwrap is the parent, not the Core); the Core reaps its workers.
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
            signal_group(proc.pid, signal.SIGKILL)
            rc = proc.wait(timeout=5)
            check(f"{label}: clean shutdown on SIGTERM", False, "required SIGKILL")
    else:
        rc = proc.returncode
    deadline = time.monotonic() + 5
    while group_alive(proc.pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    residual = group_alive(proc.pid)
    if residual:
        signal_group(proc.pid, signal.SIGKILL)
    check(f"{label}: no residual Core or worker processes after stop", not residual, f"pgid {proc.pid}")
    check(f"{label}: Core exit status after SIGTERM", rc == 0, f"rc={rc}")
    return rc


def core_stop_quiet():
    try:
        core_stop()
    except Exception as exc:
        check("cleanup: Core stop", False, f"{type(exc).__name__}: {exc}")


def req(root, op, **fields):
    S["n"] = S.get("n", 0) + 1
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(10)
        sock.connect(str(Path(root) / "core.sock"))
        sock.sendall((json.dumps({"version": 1, "request_id": f"b4_{S['n']}", "op": op, **fields}) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                raise RuntimeError("Core disconnected")
            data += chunk
    return json.loads(data)


def wait_snapshot(root, predicate, timeout, what):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = req(root, "snapshot")
        if predicate(last):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"{what} not reached: {json.dumps(last)[:900] if last else None}")


def kinds(snap):
    return [event.get("kind") for event in snap.get("events", [])]


def s1_check(label):
    root = S["state"] / "core"
    snap = wait_snapshot(
        root,
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
    check(f"{label}: speech started and finished on virtual TTS",
          snap["speech_status"] == "completed" and speech.get("samples", 0) > 0
          and "speech_started" in kinds(snap) and "speech_completed" in kinds(snap),
          {"speech_status": snap["speech_status"], "speech": speech, "kinds": kinds(snap)})
    return snap


def profile_digests(state):
    base = state / "profile"
    out = {}
    for path in sorted(base.rglob("*")):
        if path.is_file() and not path.is_symlink():
            out[path.relative_to(base).as_posix()] = sha256(path)
    return out


def hub_of(root):
    return req(root, "snapshot")["hub"]


def hub_entry(hub):
    return next(e for e in hub["entries"] if e["plugin_id"] == BENIGN)


def hub_record(hub):
    return next((r for r in hub["installed"] if r["plugin_id"] == BENIGN), None)


# ---------------------------------------------------------------- scenarios

def scenario_build():
    S["build"].mkdir()
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True,
                          timeout=30).stdout.strip()
    S["commit"] = head
    cargo = shutil.which("cargo")
    if cargo is None:
        raise RuntimeError("cargo not on PATH; the packaged binary cannot be built")
    # Build step only: real toolchain and cargo/rustup homes; the Core sandbox env stays host_env().
    build_env = {"PATH": f"{Path(cargo).parent}:/usr/bin:/bin", "HOME": str(Path.home())}
    for key in ("CARGO_HOME", "RUSTUP_HOME"):
        if os.environ.get(key):
            build_env[key] = os.environ[key]
    proc = run(["python3", str(REPO / "scripts/build_package.py"), str(S["build"])], env=build_env, timeout=900)
    check("1 build: build_package.py exits 0", proc.returncode == 0, proc.stderr.decode()[-800:])
    pkg = S["build"] / PKG_NAME
    if not (pkg / "PACKAGE.json").is_file():
        raise RuntimeError("PACKAGE.json missing after build")
    S["pkg"] = pkg
    manifest = json.loads((pkg / "PACKAGE.json").read_text(encoding="utf-8"))
    check("1 build: PACKAGE.json commit equals git rev-parse HEAD", manifest.get("commit") == head,
          f"manifest={manifest.get('commit')} head={head}")
    S["dirty"] = manifest.get("dirty")

    pkg_real = os.path.realpath(pkg)
    leaks, allowed, outside, dangling, links = [], {}, [], [], 0
    for path in sorted(pkg.rglob("*")):
        rel = path.relative_to(pkg).as_posix()
        if HOME_MARK.decode() in rel:
            leaks.append({"path": rel, "where": "file name"})
        if path.is_symlink():
            links += 1
            target = os.readlink(path)
            if HOME_MARK.decode() in target:
                leaks.append({"path": rel, "where": "symlink target", "target": target})
            if target.startswith("/"):
                outside.append({"path": rel, "target": target, "why": "absolute"})
            real = os.path.realpath(path)
            if not (real == pkg_real or real.startswith(pkg_real + os.sep)):
                outside.append({"path": rel, "target": target, "resolves": real})
            if not path.exists():
                dangling.append({"path": rel, "target": target})
            continue
        if not path.is_file():
            continue
        for mark in BUILD_MARKS:
            count, samples = find_bytes(path, mark)
            if not count:
                continue
            if any(fnmatch.fnmatch(rel, pattern) for pattern, _ in ALLOWED):
                allowed.setdefault(rel, {})[mark.decode()] = {"matches": count, "samples": samples}
            else:
                leaks.append({"path": rel, "mark": mark.decode(), "matches": count, "samples": samples})
    RESULT["allowlisted"] = allowed
    RESULT["build"] = {"entries": len(manifest["files"]), "symlinks": links}
    check("1 build: no repo, home or uv path in any file (binary or text) outside the allowlist",
          not leaks, json.dumps(leaks[:20]))
    check("1 build: no host path in any symlink target", not any(
        HOME_MARK.decode() in os.readlink(p) for p in pkg.rglob("*") if p.is_symlink()))
    binary = pkg / "bin/gideon-base"
    release = REPO / "target/release/gideon-base"
    strings_out = run(["strings", "-a", str(binary)], timeout=120).stdout
    found = [m.decode() for m in [REPO_PATH, HOME_MARK, UV_MARK] if m in strings_out]
    check("1 build: strings -a on packaged bin/gideon-base shows no repo, home or uv path",
          bool(strings_out) and not found, found or "strings produced no output")
    check("1 build: PACKAGE.json pins packaged and release binary sha256, source_equivalence recorded",
          manifest.get("gideon_base_sha256") == sha256(binary)
          and manifest.get("release_gideon_base_sha256") == sha256(release)
          and manifest.get("source_equivalence") == "same commit, remapped paths",
          {k: manifest.get(k) for k in ("gideon_base_sha256", "release_gideon_base_sha256", "source_equivalence")})
    packaged_run = run([str(binary)], timeout=60)
    release_run = run([str(release)], timeout=60)
    check("1 build: packaged and release gideon-base give identical usage output and exit code",
          packaged_run.returncode == release_run.returncode and packaged_run.stdout == release_run.stdout
          and packaged_run.stderr == release_run.stderr and b"usage: gideon-base" in packaged_run.stderr,
          {"packaged": packaged_run.returncode, "release": release_run.returncode})
    RESULT["release_binary_sha256"] = sha256(release)
    check("1 build: no symlink is absolute, escapes the prefix or dangles", not (outside or dangling),
          json.dumps({"outside": outside[:10], "dangling": dangling[:10]}))

    replay = json.loads((REPO / "target/a3-assets/replay-manifest.json").read_text(encoding="utf-8"))
    kept = next(r for r in replay["fixtures"] if r.get("id") == FIXTURE_ID)
    qa_hashes = {r["sha256"] for r in replay["fixtures"] if r.get("id") != FIXTURE_ID and r.get("sha256")}
    corpus = []
    for path in sorted((pkg / "assets").rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(pkg).as_posix()
        if ".cache" in rel:
            corpus.append({"path": rel, "why": "name"})
        if find_bytes(path, b".cache/gideon")[0]:
            corpus.append({"path": rel, "why": ".cache/gideon text"})
        if sha256(path) in qa_hashes:
            corpus.append({"path": rel, "why": "QA corpus sha256"})
    check("1 build: no file under assets/ matches a QA corpus (.cache/gideon or QA fixture sha)", not corpus,
          json.dumps(corpus[:20]))
    fixtures = sorted(p.name for p in (pkg / "assets/fixture").iterdir())
    kept_name = Path(kept["path"]).name
    check("1 build: assets/fixture contains only the kept fixture", fixtures == [kept_name], fixtures)
    check("1 build: kept fixture matches its replay pin",
          (pkg / "assets/fixture" / kept_name).is_file() and sha256(pkg / "assets/fixture" / kept_name) == kept["sha256"])


def scenario_relocate():
    if "pkg" not in S:
        raise RuntimeError("package not built")
    parent = Path(tempfile.mkdtemp(prefix="gb4r-", dir="/tmp"))
    S["reloc_parent"] = parent
    new = parent / RELOCATED
    old = S["pkg"]
    os.rename(old, new)
    S["prefix"] = new
    check("2 relocate: moved to a new name and different temp parent",
          new.is_dir() and not old.exists() and parent != old.parent and new.name != PKG_NAME,
          f"{old} -> {new}")
    verify = run([str(runtime_py(new)), "-I", "-B", str(new / "bin/gideon-verify")], timeout=600)
    check("2 relocate: gideon-verify passes at the new prefix",
          verify.returncode == 0 and b"gideon-verify: OK" in verify.stdout, verify.stderr.decode()[-600:])


def scenario_hidden_run():
    require_package()
    S["state"] = S["work"] / "st"
    S["state"].mkdir(mode=0o700)
    S["isolation"] = probe_isolation()
    RESULT["isolation"] = S["isolation"]
    if S["isolation"] == "outer_bwrap":
        probe = run(bwrap_argv(S["prefix"], S["state"], [],
                               ["/bin/sh", "-c", "[ ! -e /home ] && echo NOHOME; cat /proc/net/dev"]), timeout=60)
        text = probe.stdout.decode("utf-8", "replace")
        check("3 hidden: sandbox has no /home (repo and ~/.local/share/uv unreachable)",
              probe.returncode == 0 and "NOHOME" in text, probe.stderr.decode()[-400:])
        ifaces = [line.split(":")[0].strip() for line in text.splitlines()[2:] if ":" in line]
        S["netcheck"] = ifaces
        check("3 hidden: sandbox network namespace exposes only lo", ifaces == ["lo"], ifaces)
    else:
        RESULT["fallback_reason"] = RESULT.get("nested_probe_error") or f"nested bwrap rc={RESULT.get('nested_probe_rc')}"
        isolation_unavailable(RESULT["fallback_reason"])
    mark = len(UNREADABLE)
    core_start("native", ())
    scanned, hits = scan_tree(S["core"].pid)
    check(f"3 hidden: Core tree ({scanned} processes) has no repo or uv path in cmdline/environ/maps/mountinfo/cwd/fds",
          scanned >= 1 and not hits, json.dumps(hits[:10]))
    check("3 hidden: every /proc entry of the Core tree readable (none unreadable)", len(UNREADABLE) == mark,
          UNREADABLE[mark:][:10])


def core_exe_check(label):
    want = os.path.realpath(S["prefix"] / "bin/gideon-base")
    exes = []
    for pid in tree_pids(S["core"].pid):
        try:
            exes.append(os.readlink(f"/proc/{pid}/exe"))
        except OSError:
            pass
    check(f"{label}: Core process executes the packaged bin/gideon-base", want in exes,
          {"want": want, "exes": exes[:10]})


def tts_isolation_check(label):
    """STATE TTS artifacts must be independent files: never hard links into the package."""
    prefix, state = S["prefix"], S["state"]
    manifest = load_json_file(state / "profile/tts-manifest.json")
    names = [a["name"] for a in manifest["artifacts"] if a["name"] != "config.yaml"]
    bad = []
    for name in names:
        local = os.lstat(state / "profile/tts" / name)
        packaged = os.stat(prefix / "assets/tts" / name)
        if not stat.S_ISREG(local.st_mode) or local.st_nlink != 1 \
                or (local.st_dev, local.st_ino) == (packaged.st_dev, packaged.st_ino):
            bad.append({"name": name, "nlink": local.st_nlink, "ino": local.st_ino, "pkg_ino": packaged.st_ino})
    check(f"{label}: STATE tts artifacts have st_nlink 1 and a different inode than packaged originals",
          bool(names) and not bad, bad or names)


def load_json_file(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def scenario_native_s1():
    s1_check("4 native S1")
    core_exe_check("4 native")
    tts_isolation_check("4 native")
    core_stop()


def scenario_hub():
    require_package()
    root = S["state"] / "core"
    S["catdir"].mkdir(mode=0o755)
    catalog = S["catdir"] / "hub.json"
    shutil.copyfile(REPO / "tests/fixtures/hub.json", catalog)
    extra = ("--hub-catalog", str(catalog), sha256(catalog))
    core_start("hub", extra, extra_ro=[str(S["catdir"])])
    hub = hub_of(root)
    entry = hub_entry(hub)
    check("5 hub: benign fixture not installed before lifecycle",
          entry["status"] == "not_installed" and hub["installed"] == [], entry["status"])
    approved = req(root, "hub_approve", revision=hub["approval_revision"], plugin_id=BENIGN,
                   manifest_sha256=entry["manifest_sha256"], permissions=entry["permissions"],
                   publisher_unverified_ack=True)
    check("5 hub: explicit manifest approval accepted", approved.get("code") == "ok", approved)
    source = S["work"] / "benign.bin"
    source.write_bytes(BENIGN_BYTES)
    staged = run(["python3", str(REPO / "scripts/hub_import.py"), "--root", str(root), "--plugin", BENIGN,
                  "--source", str(source)], timeout=120)
    check("5 hub: repo hub_import.py stages payload as external client", staged.returncode == 0,
          staged.stderr.decode()[-600:])
    hub = hub_of(root)
    entry = hub_entry(hub)
    check("5 hub: payload staged and not installed", entry["payload_staged"] and hub["installed"] == [])
    digest = entry["manifest_sha256"]
    installed = req(root, "hub_install", revision=hub["install_revision"], plugin_id=BENIGN,
                    manifest_sha256=digest)
    check("5 hub: install ok", installed.get("code") == "ok", installed)
    record = hub_record(hub_of(root))
    check("5 hub: installed with runtime disabled",
          record is not None and record["state"] == "installed" and record["runtime"] == "disabled", record)
    payload = root / "hub-plugins" / f"{BENIGN}-{digest}.payload"
    check("5 hub: installed payload 0600 with exact bytes",
          payload.is_file() and stat.S_IMODE(payload.stat().st_mode) == 0o600
          and payload.read_bytes() == BENIGN_BYTES)
    core_stop()
    core_start("hub-restart", extra, extra_ro=[str(S["catdir"])])
    hub = hub_of(root)
    record = hub_record(hub)
    check("5 hub: still installed after restart, runtime disabled",
          record is not None and record["state"] == "installed" and record["runtime"] == "disabled", record)
    removed = req(root, "hub_remove", revision=hub["install_revision"], plugin_id=BENIGN)
    check("5 hub: remove ok", removed.get("code") == "ok", removed)
    check("5 hub: remove unlinks payload and empties installed",
          not payload.exists() and req(root, "snapshot")["hub"]["installed"] == [])
    core_stop()


def scenario_restart():
    require_package()
    state, prefix = S["state"], S["prefix"]
    before = profile_digests(state)
    cmd, env = launch([str(runtime_py(prefix)), "-I", "-B", str(prefix / "bin/gideon-configure"), str(state)])
    configured = run(cmd, env=env, timeout=300)
    check("6 restart: gideon-configure re-run exits 0", configured.returncode == 0, configured.stderr.decode()[-600:])
    tts_isolation_check("6 restart")
    after = profile_digests(state)
    check("6 restart: rendered profile file hashes identical after re-configure",
          before and before == after,
          json.dumps({k: (before.get(k), after.get(k)) for k in set(before) | set(after)
                      if before.get(k) != after.get(k)}, indent=1)[:1500])
    core_start("restart")
    s1_check("6 restart: native S1 passes again")
    core_stop()


def scenario_tamper():
    require_package()
    prefix = S["prefix"]
    worker = prefix / "scripts/stt_worker.py"
    original = worker.read_bytes()
    mode = stat.S_IMODE(worker.stat().st_mode)
    verify_cmd = [str(runtime_py(prefix)), "-I", "-B", str(prefix / "bin/gideon-verify")]
    worker.write_bytes(original + b"\n")
    verify = run(verify_cmd)
    check("7 tamper: gideon-verify exits non-zero after one appended byte",
          verify.returncode != 0 and b"FAIL" in verify.stderr, verify.stderr.decode()[-400:])
    sock = S["state"] / "core" / "core.sock"
    if sock.exists():
        sock.unlink()
    cmd, env = launch([str(prefix / "bin/gideon-core"), str(S["state"])])
    started = run(cmd, env=env, timeout=120)
    check("7 tamper: gideon-core exits non-zero and never creates core.sock",
          started.returncode != 0 and not sock.exists(),
          f"rc={started.returncode} sock={sock.exists()} {started.stderr.decode()[-300:]}")
    worker.write_bytes(original)
    os.chmod(worker, mode)
    check("7 tamper: restoring the byte makes gideon-verify pass again", run(verify_cmd).returncode == 0)
    extra = prefix / "scripts/extra_untracked.py"
    extra.write_text("# extra\n", encoding="utf-8")
    check("7 tamper: extra packaged-tree file makes gideon-verify fail", run(verify_cmd).returncode != 0)
    extra.unlink()
    check("7 tamper: removing the extra file makes gideon-verify pass again", run(verify_cmd).returncode == 0)


def scenario_guards():
    require_package()
    prefix, work = S["prefix"], S["work"]
    configure = [str(runtime_py(prefix)), "-I", "-B", str(prefix / "bin/gideon-configure")]
    rel = run(configure + ["relative-state"], cwd=str(work))
    check("8 guards: relative STATE refused", rel.returncode != 0 and not (work / "relative-state").exists(),
          rel.stderr.decode()[-300:])
    open_state = work / "open-state"
    open_state.mkdir(mode=0o755)
    open_state.chmod(0o755)
    perm = run(configure + [str(open_state)])
    check("8 guards: STATE with 0755 perms refused, nothing written",
          perm.returncode != 0 and b"0700" in perm.stderr and not (open_state / "profile").exists(),
          perm.stderr.decode()[-300:])
    long_state = "/tmp/" + "L" * 100
    longed = run(configure + [long_state])
    check("8 guards: STATE over the 108-byte socket limit refused, nothing written",
          longed.returncode != 0 and b"too long" in longed.stderr and not Path(long_state).exists(),
          longed.stderr.decode()[-300:])
    sentinel = work / "sentinel"
    sentinel.mkdir()
    (sentinel / "keep.txt").write_bytes(b"preserved")
    clean = work / "st-clean"
    package_before = tree_state(prefix)
    sentinel_before = tree_state(sentinel)
    home_before = tree_state(S["home"])
    good = run(configure + [str(clean)])
    check("8 guards: clean STATE configure exits 0", good.returncode == 0, good.stderr.decode()[-600:])
    check("8 guards: configure leaves package tree unchanged", tree_state(prefix) == package_before)
    check("8 guards: configure leaves sentinel and HOME unchanged",
          tree_state(sentinel) == sentinel_before and tree_state(S["home"]) == home_before)
    check("8 guards: clean STATE is 0700", stat.S_IMODE(clean.stat().st_mode) == 0o700)
    gcore = run([str(prefix / "bin/gideon-core"), "relative-state"], cwd=str(work))
    check("8 guards: gideon-core refuses relative STATE without starting", gcore.returncode != 0)


def scenario_network():
    require_package()
    prefix = S["prefix"]
    if S.get("isolation") == "outer_bwrap":
        RESULT["network"] = "unshared: outer bwrap --unshare-all, sandbox netns exposes only lo"
        check("9 network: Core sandbox exposes only loopback", S.get("netcheck") == ["lo"], S.get("netcheck"))
    else:
        RESULT["network"] = "not checked for hidden-source run: " + str(RESULT.get("fallback_reason"))
        if ALLOW_NO_ISOLATION:
            IGNORED.append({"item": "network namespace check", "reason": RESULT["network"][-300:]})
    hits = []
    for name in ("gideon-core", "gideon-configure", "gideon-verify", "gideon-app"):
        text = (prefix / "bin" / name).read_bytes()
        hits += [f"bin/{name}:{tok.decode()}" for tok in NETWORK_TOKENS if tok in text]
    for name in ("wake_worker.py", "stt_worker.py", "tts_worker.py", "command_worker.py", "pcm_fixture.py"):
        text = (prefix / "scripts" / name).read_bytes()
        hits += [f"scripts/{name}:{tok.decode()}" for tok in NETWORK_TOKENS if tok in text]
    check("9 network: launchers and worker scripts contain no download or network client code", not hits,
          hits[:20])


def main():
    started = time.monotonic()
    work = Path(tempfile.mkdtemp(prefix="gb4-", dir="/tmp"))
    S["work"] = work
    S["home"] = work / "home"
    S["home"].mkdir(mode=0o700)
    S["catdir"] = work / "cat"
    S["build"] = work / "build"
    try:
        scenario("1 build", scenario_build)
        scenario("2 relocate", scenario_relocate)
        scenario("3 hidden", scenario_hidden_run)
        scenario("4 native", scenario_native_s1)
        scenario("5 hub", scenario_hub)
        scenario("6 restart", scenario_restart)
        scenario("7 tamper", scenario_tamper)
        scenario("8 guards", scenario_guards)
        scenario("9 network", scenario_network)
    finally:
        core_stop_quiet()
        if "prefix" in S:
            RESULT["binary_sha256"] = sha256(S["prefix"] / "bin/gideon-base")
        for path in (S.get("reloc_parent"), work):
            if path is None:
                continue
            try:
                shutil.rmtree(path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                check("cleanup: temp dirs removed", False, f"{path}: {exc}")
    RESULT.update({
        "gate": "B4_PACKAGE",
        "passed": len(CHECKS),
        "failed": len(FAILS),
        "ignored": len(IGNORED),
        "ignored_items": IGNORED,
        "checks": CHECKS,
        "failures": FAILS,
        "commit": S.get("commit"),
        "dirty_at_build": S.get("dirty"),
        "scope": "offline relocatable package: build, relocation, hidden-source Core on virtual PCM/TTS, "
                 "Hub stage/install/remove, restart, tamper, guards; no network, no downloads, no physical devices",
        "physical_validation": "NOT_PERFORMED",
        "runtime_seconds": round(time.monotonic() - started, 1),
    })
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(RESULT, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: RESULT[k] for k in ("gate", "passed", "failed", "isolation", "network",
                                             "runtime_seconds")}, indent=2))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
