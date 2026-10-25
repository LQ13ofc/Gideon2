"""Test client for the A11 live run: Unix-socket requests to a private Core root.

The Core drops a peer that sends nothing for 5 s (src/transport.rs, peer). A send that fails on a dropped peer is
retried once on a fresh connection; the request is then sent for the first time, so nothing runs twice.
Request ids come from one process-wide counter, so reconnecting never repeats an id.
"""
import itertools
import json
import socket
import time
from pathlib import Path

_IDS = itertools.count(1)


class Client:
    def __init__(self, root: Path):
        self.root = root
        self.connect()

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(8)
        self.sock.connect(str(self.root / "core.sock"))
        self.file = self.sock.makefile("rb")

    def req(self, op="snapshot", **kw):
        rid = f"a11-{next(_IDS)}"
        line = (json.dumps({"version": 1, "request_id": rid, "op": op, **kw}) + "\n").encode()
        try:
            self.sock.sendall(line)
        except (BrokenPipeError, ConnectionResetError, OSError):
            self.close()
            self.connect()
            self.sock.sendall(line)
        reply = self.file.readline()
        if not reply:
            raise ConnectionError("core closed the connection before answering")
        return json.loads(reply)

    def snap(self):
        return self.req("snapshot")

    def wait_idle(self, timeout=20.0):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            s = self.snap()
            if s["state"] == "idle" and s["session_id"] is None:
                return s
            time.sleep(0.05)
        raise TimeoutError("core did not return to idle")

    def close(self):
        try:
            self.file.close()
            self.sock.close()
        except OSError:
            pass
