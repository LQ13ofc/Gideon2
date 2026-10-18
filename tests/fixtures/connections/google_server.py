#!/usr/bin/env python3
"""Fake Google (Gmail, Calendar, Drive) API and OAuth device-flow server for S5/E2.2 tests.

TEST FIXTURE ONLY. Binds 127.0.0.1, keeps all state in memory, uses the Python
standard library only and never contacts a real service. Prints PORT=<n> on
stdout once listening. Request log lines (stderr) carry method, path and status
only: never headers, bodies or credential values.

Control endpoints under /__control/ exist for tests; see README.txt.
"""
import argparse
import json
import re
import secrets
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
MAX_BODY = 16 * 1024
MAX_DISCARD = 1024 * 1024
DEVICE_TTL = 600
ACCESS_TTL = 3600
DEFAULT_ACCOUNT = "demo-user"
IDEMPOTENCY_HISTORY = 10
CALL_HISTORY = 50
FIELD_MAX = 256
FILE_CONTENT_MAX = 8 * 1024
ACCOUNT_RE = re.compile(r"[A-Za-z0-9_.-]{1,39}")
USER_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ"
GRANT_TYPE_DEVICE = "urn:ietf:params:oauth:grant-type:device_code"
SCOPES = ("gmail.read", "gmail.send", "gmail.delete",
          "calendar.read", "calendar.write", "drive.read", "drive.write")
EMAIL_RE = re.compile(r"[^@\s<>]{1,64}@[^@\s<>]{1,253}")
MESSAGE_RE = re.compile(r"/api/gmail/messages/([A-Za-z0-9_-]{1,64})")


class Fail(Exception):
    """Error response: HTTP status, JSON error code, extra headers."""

    def __init__(self, status, code, headers=None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.headers = headers or {}


class Store:
    """All fake-server state. Every access happens while holding ``lock``."""

    def __init__(self):
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        self.account = DEFAULT_ACCOUNT
        self.denied = set()
        self.ceiling = None  # None: refresh keeps every granted scope
        self.quota_left = 0
        self.quota_retry = 1
        self.rate_left = 0
        self.rate_retry = 1
        self.device = {}
        self.user_codes = {}
        self.access = {}
        self.refresh = {}
        self.messages = {
            "m1": {"from": "alice@example.test", "subject": "Seed one", "body": "Seed body one"},
            "m2": {"from": "bob@example.test", "subject": "Seed two", "body": "Seed body two"},
        }
        self.sent = []
        self.next_sent = 1
        self.events = {
            "e1": {"title": "Seed event", "start": "2026-10-20T09:00:00Z",
                   "end": "2026-10-20T10:00:00Z"},
        }
        self.next_event = 2
        self.files = {"f1": {"name": "seed.txt", "content": "seed"}}
        self.next_file = 2
        self.idem = {}
        self.idem_history = []
        self.requests = 0
        self.tokens_issued = 0
        self.tokens_revoked = 0


# ---------------------------------------------------------------- helpers

def _log_line(method, path, status):
    text = "%s %s %s" % (method, path[:200], status)
    sys.stderr.write(text.encode("unicode_escape").decode("ascii") + "\n")
    sys.stderr.flush()


def _nonempty_str(value):
    return isinstance(value, str) and value != ""


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


def _text(body, field, required, limit):
    value = body.get(field)
    if value is None:
        if required:
            raise Fail(400, "validation_failed")
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise Fail(400, "validation_failed")
    if required and not value.strip():
        raise Fail(400, "validation_failed")
    return value


def _when(value):
    """RFC 3339 date-time (with 'T') -> aware or naive datetime, else 400."""
    if "T" not in value:
        raise Fail(400, "validation_failed")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise Fail(400, "validation_failed")


def _authorize(store, header, scope):
    scheme, _, token = (header or "").partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise Fail(401, "bad_credentials")
    rec = store.access.get(token)
    if rec is None or rec["revoked"] or time.monotonic() >= rec["expires_at"]:
        raise Fail(401, "bad_credentials")
    if scope in store.denied or scope not in rec["scopes"]:
        raise Fail(403, "insufficient_scope")
    return rec


def _issue_pair(store, scopes):
    access = secrets.token_urlsafe(32)
    refresh = secrets.token_urlsafe(32)
    store.access[access] = {
        "scopes": frozenset(scopes),
        "expires_at": time.monotonic() + ACCESS_TTL,
        "revoked": False,
    }
    store.refresh[refresh] = {"scopes": list(scopes), "revoked": False}
    store.tokens_issued += 1
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": ACCESS_TTL,
        "scope": " ".join(scopes),
        "account": store.account,
    }


def _event_view(store, event_id):
    event = store.events[event_id]
    return {"id": event_id, "title": event["title"], "start": event["start"], "end": event["end"]}


def _remember_key(store, key):
    store.idem_history.append(key)
    del store.idem_history[:-IDEMPOTENCY_HISTORY]


# ---------------------------------------------------------------- OAuth device flow

def _login_device_code(store, base, body):
    device_code = secrets.token_urlsafe(24)
    user_code = "%s-%s" % (
        "".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(4)),
        "".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(4)),
    )
    store.device[device_code] = {
        "user_code": user_code,
        "expires_at": time.monotonic() + DEVICE_TTL,
        "approved": False,
        "used": False,
        "scopes": [],
    }
    store.user_codes[user_code] = device_code
    return 200, {
        "device_code": device_code,
        "user_code": user_code,
        "verification_uri": base + "/login/device",
        "expires_in": DEVICE_TTL,
        "interval": 1,
    }, {}


def _login_access_token(store, base, body):
    grant = body.get("grant_type")
    device_code = body.get("device_code")
    if not _nonempty_str(grant) or not _nonempty_str(device_code):
        raise Fail(400, "invalid_request")
    dev = store.device.get(device_code)
    if dev is None or dev["used"]:
        raise Fail(400, "invalid_grant")
    if time.monotonic() >= dev["expires_at"]:
        raise Fail(400, "expired_token")
    if not dev["approved"]:
        raise Fail(400, "authorization_pending")
    dev["used"] = True
    return 200, _issue_pair(store, dev["scopes"]), {}


def _login_refresh(store, base, body):
    token = body.get("refresh_token")
    rec = store.refresh.get(token) if _nonempty_str(token) else None
    if rec is None or rec["revoked"]:
        raise Fail(400, "invalid_grant")
    rec["revoked"] = True  # rotation: the presented refresh token is spent
    scopes = [s for s in rec["scopes"] if store.ceiling is None or s in store.ceiling]
    return 200, _issue_pair(store, scopes), {}


def _login_revoke(store, base, body):
    token = body.get("token")
    if not _nonempty_str(token):
        raise Fail(400, "invalid_request")
    hit = False
    for table in (store.access, store.refresh):
        rec = table.get(token)
        if rec is not None and not rec["revoked"]:
            rec["revoked"] = True
            hit = True
    if hit:
        store.tokens_revoked += 1
    return 200, {"revoked": hit}, {}


LOGIN_ROUTES = {
    "/login/device/code": _login_device_code,
    "/login/oauth/access_token": _login_access_token,
    "/login/oauth/refresh": _login_refresh,
    "/login/oauth/revoke": _login_revoke,
}


# ---------------------------------------------------------------- API handlers

def _list_messages(store, base, body, args, headers):
    # Projection: id, from and subject only. Bodies are never listed.
    return 200, [
        {"id": mid, "from": msg["from"], "subject": msg["subject"]}
        for mid, msg in sorted(store.messages.items())
    ], {}


def _send_message(store, base, body, args, headers):
    to = _text(body, "to", required=True, limit=254)
    if not EMAIL_RE.fullmatch(to):
        raise Fail(400, "validation_failed")
    subject = _text(body, "subject", required=True, limit=FIELD_MAX)
    text = _text(body, "body", required=True, limit=MAX_BODY)
    sent_id = "s%d" % store.next_sent
    store.next_sent += 1
    store.sent.append({"id": sent_id, "to": to, "subject": subject, "body": text})
    return 201, {"id": sent_id, "to": to, "subject": subject}, {}


def _delete_message(store, base, body, args, headers):
    message_id = args[0]
    if message_id not in store.messages:
        raise Fail(404, "not_found")
    del store.messages[message_id]
    return 200, {"id": message_id, "deleted": True}, {}


def _list_events(store, base, body, args, headers):
    return 200, [_event_view(store, eid) for eid in sorted(store.events)], {}


def _create_event(store, base, body, args, headers):
    title = _text(body, "title", required=True, limit=FIELD_MAX)
    start_text = _text(body, "start", required=True, limit=40)
    end_text = _text(body, "end", required=True, limit=40)
    start = _when(start_text)
    end = _when(end_text)
    try:
        ordered = end >= start
    except TypeError:  # one aware, one naive
        ordered = False
    if not ordered:
        raise Fail(400, "validation_failed")
    fingerprint = (title, start_text, end_text)
    key = headers.get("Idempotency-Key")
    if key is not None:
        key = key.strip()
        if not key or len(key) > 255:
            raise Fail(400, "invalid_idempotency_key")
        _remember_key(store, key)
        existing = store.idem.get(key)
        if existing is not None:
            event_id, seen = existing
            if seen != fingerprint:
                raise Fail(409, "idempotency_conflict")
            return 201, _event_view(store, event_id), {"X-Idempotent-Replay": "true"}
    event_id = "e%d" % store.next_event
    store.next_event += 1
    store.events[event_id] = {"title": title, "start": start_text, "end": end_text}
    if key is not None:
        store.idem[key] = (event_id, fingerprint)
    return 201, _event_view(store, event_id), {}


def _list_files(store, base, body, args, headers):
    return 200, [{"id": fid, "name": store.files[fid]["name"]}
                 for fid in sorted(store.files)], {}


def _create_file(store, base, body, args, headers):
    name = _text(body, "name", required=True, limit=128)
    if "/" in name or "\\" in name or name in (".", ".."):
        raise Fail(400, "validation_failed")
    content = _text(body, "content", required=False, limit=FILE_CONTENT_MAX)
    file_id = "f%d" % store.next_file
    store.next_file += 1
    store.files[file_id] = {"name": name, "content": content}
    return 201, {"id": file_id, "name": name}, {}


API_ROUTES = {
    "/api/gmail/messages": {"GET": ("gmail.read", _list_messages)},
    "/api/gmail/send": {"POST": ("gmail.send", _send_message)},
    "/api/calendar/events": {
        "GET": ("calendar.read", _list_events),
        "POST": ("calendar.write", _create_event),
    },
    "/api/drive/files": {
        "GET": ("drive.read", _list_files),
        "POST": ("drive.write", _create_file),
    },
}


def _match_api(path):
    """Return ({method: (scope, handler)}, args) or (None, ())."""
    found = MESSAGE_RE.fullmatch(path)
    if found:
        return {"DELETE": ("gmail.delete", _delete_message)}, (found.group(1),)
    spec = API_ROUTES.get(path)
    if spec is None:
        return None, ()
    return spec, ()


# ---------------------------------------------------------------- control handlers

def _ctl_reset(store, base, body):
    store.reset()
    return 200, {"ok": True}, {}


def _ctl_expire_token(store, base, body):
    now = time.monotonic()
    access = body.get("access_token")
    device_code = body.get("device_code")
    if access is not None:
        rec = store.access.get(access) if _nonempty_str(access) else None
        if rec is None:
            raise Fail(404, "unknown_token")
        rec["expires_at"] = now - 1
        return 200, {"expired": 1}, {}
    if device_code is not None:
        dev = store.device.get(device_code) if _nonempty_str(device_code) else None
        if dev is None:
            raise Fail(404, "unknown_device_code")
        dev["expires_at"] = now - 1
        return 200, {"expired": 1}, {}
    for rec in store.access.values():
        rec["expires_at"] = now - 1
    return 200, {"expired": len(store.access)}, {}


def _ctl_rate_limit(store, base, body):
    n = body.get("n")
    retry_after = body.get("retry_after", 1)
    if not _is_int(n, 0, 10000) or not _is_int(retry_after, 0, 3600):
        raise Fail(400, "invalid_request")
    store.rate_left = n
    store.rate_retry = retry_after
    return 200, {"remaining": n, "retry_after": retry_after}, {}


def _ctl_quota(store, base, body):
    n = body.get("n")
    retry_after = body.get("retry_after", 1)
    if not _is_int(n, 0, 10000) or not _is_int(retry_after, 0, 3600):
        raise Fail(400, "invalid_request")
    store.quota_left = n
    store.quota_retry = retry_after
    return 200, {"remaining": n, "retry_after": retry_after}, {}


def _ctl_set_account(store, base, body):
    name = body.get("name")
    if not isinstance(name, str) or not ACCOUNT_RE.fullmatch(name):
        raise Fail(400, "invalid_request")
    store.account = name
    return 200, {"account": name}, {}


def _ctl_deny_scope(store, base, body):
    scope = body.get("scope")
    if not _nonempty_str(scope) or len(scope) > 64:
        raise Fail(400, "invalid_request")
    store.denied.add(scope)
    return 200, {"denied": sorted(store.denied)}, {}


def _ctl_change_scopes(store, base, body):
    if "scopes" not in body:
        raise Fail(400, "invalid_request")
    scopes = body["scopes"]
    if scopes is None:
        store.ceiling = None
    else:
        if not isinstance(scopes, list) or not all(s in SCOPES for s in scopes):
            raise Fail(400, "invalid_scope")
        store.ceiling = set(scopes)
    return 200, {"ceiling": None if store.ceiling is None else sorted(store.ceiling)}, {}


def _ctl_approve(store, base, body):
    """Approve a pending device flow by user_code OR device_code (exactly one)."""
    has_device = "device_code" in body
    has_user = "user_code" in body
    if has_device == has_user:
        raise Fail(400, "invalid_request")
    scopes = body.get("scopes")
    if (not isinstance(scopes, list) or len(scopes) > len(SCOPES)
            or not all(isinstance(s, str) and s in SCOPES for s in scopes)):
        raise Fail(400, "invalid_scope")
    if has_user:
        code = body["user_code"]
        if not _nonempty_str(code):
            raise Fail(400, "invalid_request")
        device_code = store.user_codes.get(code)
        if device_code is None:
            raise Fail(404, "unknown_user_code")
    else:
        device_code = body["device_code"]
        if not _nonempty_str(device_code):
            raise Fail(400, "invalid_request")
    dev = store.device.get(device_code)
    if dev is None:
        raise Fail(404, "unknown_device_code")
    if time.monotonic() >= dev["expires_at"]:
        raise Fail(409, "expired_token")
    if dev["used"]:
        raise Fail(409, "already_used")
    granted = []
    for scope in scopes:
        if scope not in store.denied and scope not in granted:
            granted.append(scope)
    dev["approved"] = True
    dev["scopes"] = granted
    return 200, {"ok": True, "granted_scopes": granted}, {}


def _ctl_state(store, base, body):
    now = time.monotonic()
    return 200, {
        "account": store.account,
        "denied_scopes": sorted(store.denied),
        "scope_ceiling": None if store.ceiling is None else sorted(store.ceiling),
        "quota_remaining": store.quota_left,
        "rate_limit_remaining": store.rate_left,
        "requests": store.requests,
        "messages": [{"id": mid, "subject": m["subject"]}
                     for mid, m in sorted(store.messages.items())],
        "sent": [{"id": s["id"], "to": s["to"], "subject": s["subject"]} for s in store.sent],
        "events": [_event_view(store, eid) for eid in sorted(store.events)],
        "files": [{"id": fid, "name": f["name"]} for fid, f in sorted(store.files.items())],
        "last_idempotency_keys": list(store.idem_history),
        "device_codes_pending": sum(
            1 for d in store.device.values()
            if not d["used"] and not d["approved"] and now < d["expires_at"]),
        "tokens": {
            "issued": store.tokens_issued,
            "revoked": store.tokens_revoked,
            "active": sum(1 for r in store.access.values()
                          if not r["revoked"] and now < r["expires_at"]),
        },
    }, {}


CONTROL_ROUTES = {
    "reset": ("POST", _ctl_reset),
    "expire_token": ("POST", _ctl_expire_token),
    "rate_limit": ("POST", _ctl_rate_limit),
    "quota": ("POST", _ctl_quota),
    "set_account": ("POST", _ctl_set_account),
    "deny_scope": ("POST", _ctl_deny_scope),
    "change_scopes": ("POST", _ctl_change_scopes),
    "approve": ("POST", _ctl_approve),
    "state": ("GET", _ctl_state),
}


# ---------------------------------------------------------------- HTTP plumbing

class Handler(BaseHTTPRequestHandler):
    server_version = "FakeGoogle/1.0"
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
        if path in LOGIN_ROUTES:
            if method != "POST":
                raise Fail(405, "method_not_allowed", {"Allow": "POST"})
            body = _parse_body(raw, self.headers.get("Content-Type"))
            return LOGIN_ROUTES[path](store, base, body)
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
        scope, func = spec[method]
        if store.quota_left > 0:
            store.quota_left -= 1
            raise Fail(429, "quota_exceeded", {"Retry-After": str(store.quota_retry)})
        if store.rate_left > 0:
            store.rate_left -= 1
            raise Fail(429, "rate_limited", {"Retry-After": str(store.rate_retry)})
        _authorize(store, self.headers.get("Authorization"), scope)
        body = {} if method in ("GET", "DELETE") else _parse_body(
            raw, self.headers.get("Content-Type"))
        return func(store, base, body, args, self.headers)

    def _send(self, method, path, status, payload, extra):
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            with self.server.store.lock:
                account = self.server.store.account
            self.send_header("X-Account", account)
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
    parser = argparse.ArgumentParser(description="Fake Google server (test fixture, 127.0.0.1 only).")
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
