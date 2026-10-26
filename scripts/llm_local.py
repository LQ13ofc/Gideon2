#!/usr/bin/env python3
"""WP-6 local LLM runtime manager (stdlib only; run as `python3 -I scripts/llm_local.py ...`).

Runs the llama.cpp server (`llama-server`) that the Core reaches through the local provider
(`local`, 127.0.0.1:<local_port>, keyless loopback). The server is bound to 127.0.0.1 only, with the
built-in web UI off. It is a separate supervised process: the plugin that asks for chats runs in the
bwrap sandbox without network and reaches the server only through the Core's net broker.

Every path is an argument. Nothing is read from or written to the repository, except the manifest.

Commands (one JSON object on stdout; exit 0 on success, 1 on failure):
  verify  --manifest M [--archive A] [--model F]
          sha256 of the archive and of the GGUF against the manifest (published hashes).
  extract --manifest M --archive A --bin-dir D
          verify the archive sha256, then unpack it safely (regular files and directories only) into D.
  start   --manifest M --bin-dir D --model F --run-dir R --port P [--threads N] [--ctx N]
          verify the model, start llama-server on 127.0.0.1:P, wait for /health.
  stop    --run-dir R
          SIGTERM to the recorded pid, only when its command line is the recorded llama-server;
          SIGKILL after 15 s. Removes the state file.
  status  --run-dir R
          pid liveness and /health.
"""
import argparse
import hashlib
import http.client
import json
import os
import signal
import subprocess
import sys
import tarfile
import time
from pathlib import Path

CHUNK = 1 << 20
HEALTH_WAIT_S = 180
STOP_WAIT_S = 15
PORT_MIN, PORT_MAX = 1024, 65535
STATE_NAME = "llama-server.json"
LOG_NAME = "llama-server.log"
LOOPBACK = "127.0.0.1"


class Fail(Exception):
    def __init__(self, code, **extra):
        super().__init__(code)
        self.code = code
        self.extra = extra


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Fail("manifest_unreadable")
    if not isinstance(data, dict) or data.get("version") != 1:
        raise Fail("manifest_invalid")
    return data


def check_hash(path, expected_sha, expected_size=None):
    """Returns (ok, actual_sha). A missing file is a failure, never a pass."""
    file_path = Path(path)
    if not file_path.is_file():
        raise Fail("file_missing", path=str(file_path))
    if expected_size is not None and file_path.stat().st_size != expected_size:
        raise Fail("size_mismatch", path=str(file_path))
    actual = sha256_file(file_path)
    if actual != expected_sha:
        raise Fail("sha256_mismatch", path=str(file_path), actual=actual)
    return actual


def verify_model(manifest, model_path):
    model = manifest["model"]
    if Path(model_path).name != model["file"]:
        raise Fail("model_name_mismatch", expected=model["file"])
    check_hash(model_path, model["sha256"], model["size"])
    return model["sha256"]


def safe_extract(archive, dest):
    dest_root = Path(dest).resolve()
    dest_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            name = member.name
            if name.startswith("/") or ".." in Path(name).parts:
                raise Fail("archive_path_unsafe", member=name)
            target = (dest_root / name).resolve()
            if dest_root not in target.parents and target != dest_root:
                raise Fail("archive_path_unsafe", member=name)
            if member.issym():
                # llama.cpp ships relative symlinks between its .so files; they must stay inside dest.
                link = member.linkname
                if link.startswith("/") or ".." in Path(link).parts:
                    raise Fail("archive_link_unsafe", member=name)
                resolved = (target.parent / link).resolve()
                if dest_root not in resolved.parents:
                    raise Fail("archive_link_unsafe", member=name)
                continue
            if not (member.isreg() or member.isdir()):
                raise Fail("archive_member_unsafe", member=name)
        tar.extractall(dest_root, members=members, filter="data")
    return len(members)


def health(port, timeout=2.0):
    try:
        conn = http.client.HTTPConnection(LOOPBACK, port, timeout=timeout)
        conn.request("GET", "/health")
        response = conn.getresponse()
        body = response.read(4096)
        conn.close()
        return response.status == 200 and b'"ok"' in body
    except (OSError, http.client.HTTPException):
        return False


def read_state(run_dir):
    path = Path(run_dir) / STATE_NAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Fail("state_unreadable")


def write_private(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)


def process_alive(pid):
    """True when pid exists and is not a zombie."""
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as handle:
            fields = handle.read().rsplit(")", 1)[1].split()
        return fields[0] != "Z"
    except (OSError, IndexError):
        return False


def is_our_server(pid, server, port):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            argv = handle.read().split(b"\0")
    except OSError:
        return False
    if not argv or argv[0].decode("utf-8", "replace") != str(server):
        return False
    tokens = [token.decode("utf-8", "replace") for token in argv]
    return "--port" in tokens and tokens[tokens.index("--port") + 1:tokens.index("--port") + 2] == [str(port)]


def cmd_verify(args):
    manifest = load_manifest(args.manifest)
    checks = {}
    if args.archive:
        engine = manifest["engine"]
        checks["archive_sha256"] = check_hash(args.archive, engine["asset_sha256"], engine["asset_size"])
    if args.model:
        checks["model_sha256"] = verify_model(manifest, args.model)
    return {"ok": True, "checks": checks}


def cmd_extract(args):
    manifest = load_manifest(args.manifest)
    engine = manifest["engine"]
    check_hash(args.archive, engine["asset_sha256"], engine["asset_size"])
    count = safe_extract(args.archive, args.bin_dir)
    server = Path(args.bin_dir) / engine["extracted_server"]
    if not server.is_file():
        raise Fail("server_missing", path=str(server))
    return {"ok": True, "members": count, "server": str(server)}


def cmd_start(args):
    manifest = load_manifest(args.manifest)
    engine = manifest["engine"]
    if not PORT_MIN <= args.port <= PORT_MAX:
        raise Fail("port_invalid")
    if not 1 <= args.threads <= 128 or not 512 <= args.ctx <= 32768:
        raise Fail("argument_invalid")
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    stale = read_state(run_dir)
    if stale is not None:
        if process_alive(stale["pid"]):
            raise Fail("already_running")
        (run_dir / STATE_NAME).unlink(missing_ok=True)
    if health(args.port):
        raise Fail("port_in_use")
    sha = verify_model(manifest, args.model)
    server = Path(args.bin_dir) / engine["extracted_server"]
    if not server.is_file():
        raise Fail("server_missing", path=str(server))
    libdir = str(server.parent)
    env = {"PATH": "/usr/bin:/bin", "LD_LIBRARY_PATH": libdir, "HOME": str(run_dir),
           "LANG": "C.UTF-8"}
    argv = [str(server), "-m", str(Path(args.model)), "--host", LOOPBACK, "--port", str(args.port),
            "--no-webui", "-c", str(args.ctx), "-t", str(args.threads), "-np", "1", "--jinja"]
    log_path = run_dir / LOG_NAME
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    log = os.fdopen(fd, "wb")
    started = time.monotonic()
    proc = subprocess.Popen(argv, cwd=str(run_dir), env=env, stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    log.close()
    state = {"pid": proc.pid, "port": args.port, "server": str(server), "threads": args.threads,
             "ctx": args.ctx, "model_sha256": sha, "started_at": int(time.time())}
    write_private(run_dir / STATE_NAME, json.dumps(state))
    deadline = time.monotonic() + HEALTH_WAIT_S
    while True:
        if proc.poll() is not None:
            raise Fail("server_exited", returncode=proc.returncode)
        if health(args.port):
            break
        if time.monotonic() > deadline:
            proc.kill()
            raise Fail("health_timeout")
        time.sleep(0.2)
    return {"ok": True, "pid": proc.pid, "port": args.port, "threads": args.threads, "ctx": args.ctx,
            "load_seconds": round(time.monotonic() - started, 2), "model_sha256": sha}


def cmd_stop(args):
    state = read_state(args.run_dir)
    if state is None:
        return {"ok": True, "stopped": False, "reason": "no_state"}
    pid, port, server = state["pid"], state["port"], state["server"]
    if not process_alive(pid):
        Path(args.run_dir, STATE_NAME).unlink(missing_ok=True)
        return {"ok": True, "stopped": False, "reason": "not_running"}
    if not is_our_server(pid, server, port):
        return {"ok": False, "error": "pid_not_ours", "pid": pid}
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + STOP_WAIT_S
    while process_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    how = "sigterm"
    if process_alive(pid):
        os.kill(pid, signal.SIGKILL)
        how = "sigkill"
        time.sleep(0.5)
    Path(args.run_dir, STATE_NAME).unlink(missing_ok=True)
    return {"ok": True, "stopped": True, "pid": pid, "how": how, "port_closed": not health(port, 1.0)}


def cmd_status(args):
    state = read_state(args.run_dir)
    if state is None:
        return {"ok": True, "running": False, "reason": "no_state"}
    alive = process_alive(state["pid"])
    return {"ok": True, "running": alive and health(state["port"]), "pid": state["pid"],
            "port": state["port"], "process_alive": alive}


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--manifest", required=True)
    v.add_argument("--archive")
    v.add_argument("--model")
    e = sub.add_parser("extract")
    e.add_argument("--manifest", required=True)
    e.add_argument("--archive", required=True)
    e.add_argument("--bin-dir", required=True)
    s = sub.add_parser("start")
    s.add_argument("--manifest", required=True)
    s.add_argument("--bin-dir", required=True)
    s.add_argument("--model", required=True)
    s.add_argument("--run-dir", required=True)
    s.add_argument("--port", type=int, required=True)
    s.add_argument("--threads", type=int, default=8)
    s.add_argument("--ctx", type=int, default=4096)
    t = sub.add_parser("stop")
    t.add_argument("--run-dir", required=True)
    u = sub.add_parser("status")
    u.add_argument("--run-dir", required=True)
    return parser


COMMANDS = {"verify": cmd_verify, "extract": cmd_extract, "start": cmd_start, "stop": cmd_stop,
            "status": cmd_status}


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = COMMANDS[args.command](args)
    except Fail as fail:
        print(json.dumps({"ok": False, "error": fail.code, **fail.extra}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
