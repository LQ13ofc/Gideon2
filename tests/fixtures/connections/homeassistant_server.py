#!/usr/bin/env python3
"""Fake Home Assistant REST API server for S5/E2.3 connection tests.

TEST FIXTURE ONLY. Binds 127.0.0.1, keeps all state in memory, uses the Python
standard library only and never contacts a real service. Prints PORT=<n> on
stdout once listening. Request log lines (stderr) carry method, path and status
only: never headers, bodies or token values.

Auth is a single long-lived bearer token (no OAuth device flow). The token is
installed by a control endpoint; until then every API call is 401.

Control endpoints under /__control/ exist for tests; see README.txt.
"""
import argparse
import json
import re
import secrets
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
MAX_BODY = 16 * 1024
MAX_DISCARD = 1024 * 1024
DEFAULT_INSTANCE = "demo-home"
CALL_HISTORY = 50
TOKEN_MAX = 256
ACCOUNT_RE = re.compile(r"[A-Za-z0-9_.-]{1,39}")
ENTITY_RE = re.compile(r"[a-z_]{1,64}\.[a-z0-9_]{1,64}")
STATE_PATH_RE = re.compile(r"/api/states/([a-z_]{1,64}\.[a-z0-9_]{1,64})")
SERVICE_PATH_RE = re.compile(r"/api/services/([a-z_]{1,64})/([a-z_]{1,64})")

# (domain, service) -> (target state, extra fields allowed beside entity_id)
SERVICES = {
    ("light", "turn_on"): ("on", frozenset({"brightness"})),
    ("light", "turn_off"): ("off", frozenset()),
    ("switch", "turn_on"): ("on", frozenset()),
    ("switch", "turn_off"): ("off", frozenset()),
    ("lock", "unlock"): ("unlocked", frozenset()),
    ("lock", "lock"): ("locked", frozenset()),
    ("cover", "open_cover"): ("open", frozenset()),
    ("cover", "close_cover"): ("closed", frozenset()),
    ("alarm_control_panel", "alarm_disarm"): ("disarmed", frozenset({"code"})),
}


class Fail(Exception):
    """Error response: HTTP status, JSON error code, extra headers."""

    def __init__(self, status, code, headers=None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.headers = headers or {}


def _seed_entities():
    return {
        "light.kitchen": {"state": "off", "attributes": {"friendly_name": "Kitchen light",
                                                         "brightness": 0}},
        "lock.front_door": {"state": "locked", "attributes": {"friendly_name": "Front door"}},
        "cover.garage": {"state": "closed", "attributes": {"friendly_name": "Garage door"}},
        "alarm_control_panel.home": {"state": "armed_away",
                                     "attributes": {"friendly_name": "Home alarm"}},
        "switch.coffee": {"state": "off", "attributes": {"friendly_name": "Coffee maker"}},
    }


class Store:
    """All fake-server state. Every access happens while holding ``lock``."""

    def __init__(self):
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        self.instance = DEFAULT_INSTANCE
        self.token = None
        self.entities = _seed_entities()
        self.calls = []
        self.requests = 0
        self.auth_failures = 0


# ---------------------------------------------------------------- helpers

def _log_line(method, path, status):
    text = "%s %s %s" % (method, path[:200], status)
    sys.stderr.write(text.encode("unicode_escape").decode("ascii") + "\n")
    sys.stderr.flush()


def _is_int(value, low, high):
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _parse_body(raw, content_type):
    """JSON object or form-encoded body -> dict. Empty body -> {}."""
    if not raw:
        return {}
    kind = (content_type or "").split(";")[0].strip().lower()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise Fail(400, "invalid_json")
    if kind == "application/x-www-form-urlencoded":
        return dict(urllib.parse.parse_qsl(text, keep_blank_values=True))
    try:
        data = json.loads(text)
    except ValueError:
        raise Fail(400, "invalid_json")
    if not isinstance(data, dict):
        raise Fail(400, "invalid_json")
    return data


def _authorize(store, header):
    scheme, _, token = (header or "").partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token or store.token is None:
        store.auth_failures += 1
        raise Fail(401, "bad_credentials")
    if not secrets.compare_digest(token.encode("utf-8"), store.token.encode("utf-8")):
        store.auth_failures += 1
        raise Fail(401, "bad_credentials")


def _entity_view(store, entity_id):
    entity = store.entities[entity_id]
    return {
        "entity_id": entity_id,
        "state": entity["state"],
        "attributes": dict(entity["attributes"]),
    }


# ---------------------------------------------------------------- API handlers

def _list_states(store, base, body, args, headers):
    return 200, [_entity_view(store, eid) for eid in sorted(store.entities)], {}


def _get_state(store, base, body, args, headers):
    entity_id = args[0]
    if entity_id not in store.entities:
        raise Fail(404, "not_found")
    return 200, _entity_view(store, entity_id), {}


def _call_service(store, base, body, args, headers):
    domain, service = args
    spec = SERVICES.get((domain, service))
    if spec is None:
        raise Fail(404, "not_found")
    target, extras = spec
    entity_id = body.get("entity_id")
    if not isinstance(entity_id, str) or not ENTITY_RE.fullmatch(entity_id):
        raise Fail(400, "validation_failed")
    if entity_id.split(".", 1)[0] != domain:
        raise Fail(400, "validation_failed")
    if entity_id not in store.entities:
        raise Fail(404, "not_found")
    if set(body) - {"entity_id"} - extras:
        raise Fail(400, "validation_failed")
    if "brightness" in body and not _is_int(body["brightness"], 0, 255):
        raise Fail(400, "validation_failed")
    if "code" in body and (not isinstance(body["code"], str) or len(body["code"]) > 16):
        raise Fail(400, "validation_failed")
    entity = store.entities[entity_id]
    entity["state"] = target
    if "brightness" in body:
        entity["attributes"]["brightness"] = body["brightness"]
    store.calls.append({"service": "%s.%s" % (domain, service), "entity_id": entity_id})
    del store.calls[:-CALL_HISTORY]
    # HA answers with the list of states that changed. The "code" field is never stored.
    return 200, [_entity_view(store, entity_id)], {}


API_ROUTES = {
    "/api/states": {"GET": _list_states},
}


def _match_api(path):
    """Return ({method: handler}, args) or (None, ())."""
    spec = API_ROUTES.get(path)
    if spec is not None:
        return spec, ()
    found = STATE_PATH_RE.fullmatch(path)
    if found:
        return {"GET": _get_state}, (found.group(1),)
    found = SERVICE_PATH_RE.fullmatch(path)
    if found:
        return {"POST": _call_service}, (found.group(1), found.group(2))
    return None, ()


# ---------------------------------------------------------------- control handlers

def _ctl_reset(store, base, body):
    store.reset()
    return 200, {"ok": True}, {}


def _ctl_set_token(store, base, body):
    if "token" not in body:
        raise Fail(400, "invalid_request")
    token = body["token"]
    if token is None:
        store.token = None
        return 200, {"token_set": False}, {}
    if not isinstance(token, str) or not 1 <= len(token) <= TOKEN_MAX:
        raise Fail(400, "invalid_request")
    store.token = token
    return 200, {"token_set": True}, {}


def _ctl_set_instance(store, base, body):
    name = body.get("name")
    if not isinstance(name, str) or not ACCOUNT_RE.fullmatch(name):
        raise Fail(400, "invalid_request")
    store.instance = name
    return 200, {"instance": name}, {}


def _ctl_set_friendly_name(store, base, body):
    entity_id = body.get("entity_id")
    name = body.get("friendly_name")
    if not isinstance(entity_id, str) or entity_id not in store.entities:
        raise Fail(404, "not_found")
    if not isinstance(name, str) or not 1 <= len(name) <= 255 or not name.isprintable():
        raise Fail(400, "invalid_request")
    store.entities[entity_id]["attributes"]["friendly_name"] = name
    return 200, {"ok": True}, {}


def _ctl_state(store, base, body):
    return 200, {
        "instance": store.instance,
        "token_set": store.token is not None,
        "requests": store.requests,
        "auth_failures": store.auth_failures,
        "entities": {eid: _entity_view(store, eid) for eid in sorted(store.entities)},
        "calls": [dict(c) for c in store.calls],
    }, {}


CONTROL_ROUTES = {
    "reset": ("POST", _ctl_reset),
    "set_token": ("POST", _ctl_set_token),
    "set_instance": ("POST", _ctl_set_instance),
    "set_friendly_name": ("POST", _ctl_set_friendly_name),
    "state": ("GET", _ctl_state),
}


# ---------------------------------------------------------------- HTTP plumbing

class Handler(BaseHTTPRequestHandler):
    server_version = "FakeHomeAssistant/1.0"
    sys_version = ""
    timeout = 10

    def log_message(self, format, *args):  # noqa: A002 - silenced; _log_line logs safely
        """Default logging would print headers-adjacent detail; disabled on purpose."""

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method):
        path = self.path.split("?", 1)[0]
        control = path.startswith("/__control/")
        try:
            raw = self._read_body()
            with self.server.store.lock:
                if not control:
                    self.server.store.requests += 1
                status, payload, extra = self._route(method, path, raw)
        except Fail as exc:
            status, payload, extra = exc.status, {"error": exc.code}, exc.headers
        except Exception as exc:  # never log request data, only the exception type
            _log_line("ERROR", "internal-%s" % type(exc).__name__, 500)
            status, payload, extra = 500, {"error": "internal"}, {}
        self._send(method, path, status, payload, extra)

    def _read_body(self):
        if self.headers.get("Transfer-Encoding"):
            raise Fail(411, "length_required")
        declared = self.headers.get("Content-Length")
        if declared is None:
            return b""
        try:
            length = int(declared)
        except ValueError:
            raise Fail(400, "invalid_request")
        if length < 0:
            raise Fail(400, "invalid_request")
        if length > MAX_DISCARD:
            raise Fail(413, "payload_too_large")
        data = self.rfile.read(length) if length else b""
        if length > MAX_BODY:
            raise Fail(413, "payload_too_large")
        return data

    def _route(self, method, path, raw):
        store = self.server.store
        base = self.server.base_url
        if path.startswith("/__control/"):
            return self._control(method, path[len("/__control/"):], raw, store, base)
        if path == "/api" or path.startswith("/api/"):
            return self._api(method, path, raw, store, base)
        raise Fail(404, "not_found")

    def _control(self, method, name, raw, store, base):
        entry = CONTROL_ROUTES.get(name)
        if entry is None:
            raise Fail(404, "not_found")
        want, func = entry
        if method != want:
            raise Fail(405, "method_not_allowed", {"Allow": want})
        body = _parse_body(raw, self.headers.get("Content-Type")) if want == "POST" else {}
        return func(store, base, body)

    def _api(self, method, path, raw, store, base):
        spec, args = _match_api(path)
        if spec is None:
            raise Fail(404, "not_found")
        if method not in spec:
            raise Fail(405, "method_not_allowed", {"Allow": ", ".join(sorted(spec))})
        _authorize(store, self.headers.get("Authorization"))
        body = {} if method == "GET" else _parse_body(raw, self.headers.get("Content-Type"))
        return spec[method](store, base, body, args, self.headers)

    def _send(self, method, path, status, payload, extra):
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            with self.server.store.lock:
                instance = self.server.store.instance
            self.send_header("X-Instance", instance)
            for name, value in extra.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        _log_line(method, path, status)


class Server(ThreadingHTTPServer):
    daemon_threads = True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fake Home Assistant server (test fixture, 127.0.0.1 only).")
    parser.add_argument("--port", type=int, default=0,
                        help="TCP port on 127.0.0.1; 0 picks an ephemeral port")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    server = Server((HOST, args.port), Handler)
    server.store = Store()
    port = server.server_address[1]
    server.base_url = "http://%s:%d" % (HOST, port)
    sys.stdout.write("PORT=%d\n" % port)
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
