#!/usr/bin/env python3
"""dummy_evil: adversarial C0 fixture plugin (stdlib only).

Capability `dummy_evil.probe`, input {"probe": name} performs ONE attempt of that
probe and reports output {"result": "denied"|"allowed", "detail": short}.
Probes: network, read_home, read_repo, write_root, exec, fork_bomb_limited, env,
mem, cpu_spin (busy loop only with input allow_spin true).

Optional argv[1] mode (used only by unsandboxed protocol tests; the Core starts the
plugin without arguments, so it always runs "normal"):
  ignore_cancel  invoke sleeps 3 s ignoring cancel
  bad_json       invoke prints a non-JSON line instead of a reply
  oversize       invoke prints a 100000-byte line instead of a reply
  dup_id         invoke replies twice with the same id
  crash          invoke exits the process with code 3
  log_flood      invoke emits 200 log events, then replies
"""
import json
import os
import select
import socket
import subprocess
import sys
import time

PLUGIN_ID = "dummy_evil"
# Test hook: sed-replace this constant to exercise capability-mismatch handling.
CAPABILITIES = ["dummy_evil.probe"]
CAPABILITY = "dummy_evil.probe"
MODE = sys.argv[1] if len(sys.argv) > 1 else "normal"
MAX_LINE = 65536

_buf = bytearray()
_discarding = False


def send(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _fill(timeout):
    fd = sys.stdin.fileno()
    readable, _, _ = select.select([fd], [], [], timeout)
    if not readable:
        return True
    chunk = os.read(fd, 65536)
    if not chunk:
        return False
    _buf.extend(chunk)
    return True


def _take_line():
    global _discarding
    while True:
        newline = _buf.find(b"\n")
        if newline < 0:
            if len(_buf) > MAX_LINE:
                _buf.clear()
                _discarding = True
            return None
        line = bytes(_buf[:newline])
        del _buf[: newline + 1]
        if _discarding:
            _discarding = False
            continue
        if len(line) > MAX_LINE:
            continue
        return line


def _parse(line):
    try:
        msg = json.loads(line)
    except ValueError:
        return None
    return msg if isinstance(msg, dict) else None


def _report(allowed, detail):
    return {"result": "allowed" if allowed else "denied", "detail": str(detail)[:200]}


def probe_network():
    outcomes = []
    for host, port in (("1.1.1.1", 53), ("127.0.0.1", 37700)):
        try:
            sock = socket.create_connection((host, port), timeout=2)
            sock.close()
            outcomes.append(f"{host}:{port} connected")
        except Exception as exc:  # any failure means the attempt was blocked
            outcomes.append(f"{host}:{port} {type(exc).__name__}")
    allowed = any(o.endswith("connected") for o in outcomes)
    return _report(allowed, "; ".join(outcomes))


def probe_read_home():
    notes = []
    allowed = False
    try:
        with open("/home/lucas/.bashrc", "rb") as handle:
            handle.read(1)
        allowed = True
        notes.append("bashrc read")
    except Exception as exc:
        notes.append(f"bashrc {type(exc).__name__}")
    try:
        os.listdir("/home")
        allowed = True
        notes.append("listdir /home ok")
    except Exception as exc:
        notes.append(f"listdir {type(exc).__name__}")
    return _report(allowed, ", ".join(notes))


def probe_read_repo():
    try:
        with open("/home/lucas/Documentos/Gideon/base/Cargo.toml", "rb") as handle:
            handle.read(1)
        return _report(True, "Cargo.toml read")
    except Exception as exc:
        return _report(False, f"Cargo.toml {type(exc).__name__}")


def probe_write_root():
    notes = []
    allowed = False
    for path in ("/plugin/x", "/etc/x", "/usr/x"):
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("x")
            allowed = True
            notes.append(f"{path} created")
            try:
                os.remove(path)
            except Exception:
                pass
        except Exception as exc:
            notes.append(f"{path} {type(exc).__name__}")
    return _report(allowed, ", ".join(notes))


def probe_exec():
    try:
        done = subprocess.run(["/usr/bin/id"], capture_output=True, timeout=5, check=False)
        return _report(done.returncode == 0, f"rc={done.returncode}")
    except Exception as exc:
        return _report(False, f"exec {type(exc).__name__}")


def probe_fork_bomb_limited():
    pids = []
    failed = 0
    for _ in range(64):
        try:
            pid = os.fork()
        except Exception:
            failed += 1
            continue
        if pid == 0:
            try:
                time.sleep(1)
            finally:
                os._exit(0)
        pids.append(pid)
    for pid in pids:
        try:
            os.waitpid(pid, 0)
        except Exception:
            pass
    return _report(len(pids) == 64, f"forked={len(pids)} failed={failed}")


def probe_env():
    keys = sorted(
        k for k in os.environ
        if k in ("HOME", "SSH_AUTH_SOCK") or k.startswith(("XDG", "DBUS"))
    )
    detail = "present: " + ",".join(keys) if keys else "none present"
    return _report(bool(keys), detail)


def probe_mem():
    try:
        block = bytearray(2 * 1024 ** 3)
        del block
        return _report(True, "2 GiB allocated")
    except Exception as exc:
        return _report(False, f"2 GiB {type(exc).__name__}")


def probe_cpu_spin(inp):
    if inp.get("allow_spin") is not True:
        return _report(False, "skipped: allow_spin not set")
    end = time.monotonic() + 40
    while time.monotonic() < end:
        pass
    return _report(True, "spun 40 s")


PROBES = {
    "network": probe_network,
    "read_home": probe_read_home,
    "read_repo": probe_read_repo,
    "write_root": probe_write_root,
    "exec": probe_exec,
    "fork_bomb_limited": probe_fork_bomb_limited,
    "env": probe_env,
    "mem": probe_mem,
    "cpu_spin": probe_cpu_spin,
}


def _handle_invoke(msg):
    req_id = msg.get("id")
    if not isinstance(req_id, int) or isinstance(req_id, bool):
        return
    if msg.get("capability") != CAPABILITY:
        send({"id": req_id, "ok": False, "error": "unknown_capability"})
        return
    inp = msg.get("input")
    probe = inp.get("probe") if isinstance(inp, dict) else None
    if not isinstance(probe, str) or probe not in PROBES:
        send({"id": req_id, "ok": False, "error": "invalid_input"})
        return

    if MODE == "ignore_cancel":
        time.sleep(3)
        send({"id": req_id, "ok": True, "output": {"detail": "slept 3 s ignoring cancel"}})
    elif MODE == "bad_json":
        sys.stdout.write("this is not json\n")
        sys.stdout.flush()
    elif MODE == "oversize":
        sys.stdout.write("x" * 100000 + "\n")
        sys.stdout.flush()
    elif MODE == "dup_id":
        reply = {"id": req_id, "ok": True, "output": {"detail": "dup"}}
        send(reply)
        send(reply)
    elif MODE == "crash":
        os._exit(3)
    elif MODE == "log_flood":
        for index in range(200):
            send({"event": "log", "level": "info", "text": f"flood {index}"})
        send({"id": req_id, "ok": True, "output": {"detail": "log_flood 200 sent"}})
    else:
        if probe == "cpu_spin":
            output = probe_cpu_spin(inp)
        else:
            output = PROBES[probe]()
        send({"id": req_id, "ok": True, "output": output})


def main():
    while True:
        line = _take_line()
        if line is None:
            if not _fill(None):
                return 0
            continue
        msg = _parse(line)
        if msg is None:
            continue
        if msg.get("v", 1) != 1:
            continue
        op = msg.get("op")
        if op == "shutdown":
            return 0
        if op == "hello":
            send({"v": 1, "id": msg.get("id"), "ok": True,
                  "plugin_id": msg.get("plugin_id"), "api": 1,
                  "capabilities": CAPABILITIES})
        elif op == "invoke":
            _handle_invoke(msg)
        # cancel and unknown ops are ignored: this plugin ignores cancellation.


if __name__ == "__main__":
    sys.exit(main())
