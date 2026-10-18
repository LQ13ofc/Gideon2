#!/usr/bin/env python3
"""Fake GitHub API and OAuth device-flow server for S5/E1 connection tests.

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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
MAX_BODY = 16 * 1024
MAX_DISCARD = 1024 * 1024
DEVICE_TTL = 600
ACCESS_TTL = 3600
DEFAULT_ACCOUNT = "demo-user"
IDEMPOTENCY_HISTORY = 10
ACCOUNT_RE = re.compile(r"[A-Za-z0-9_.-]{1,39}")
USER_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ"
REPO_RE = re.compile(r"/api/repos/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(/.*)?", re.DOTALL)
GRANT_TYPE_DEVICE = "urn:ietf:params:oauth:grant-type:device_code"


class Fail(Exception):
    """Error response: HTTP status, JSON error code, extra headers."""

    def __init__(self, status, code, headers=None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.headers = headers or {}


def _issue(title, state):
    return {"title": title, "body": "", "state": state}


class Store:
    """All fake-server state. Every access happens while holding ``lock``."""

    def __init__(self):
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        self.account = DEFAULT_ACCOUNT
        self.denied = set()
        self.delay_left = 0
        self.delay_seconds = 0
        self.fail_after_create = 0
        self.rate_left = 0
        self.retry_after = 1
        self.device = {}
        self.access = {}
        self.refresh = {}
        self.repos = {
            "demo/public-repo": {"private": False, "default_branch": "main"},
            "demo/private-repo": {"private": True, "default_branch": "main"},
        }
        self.issues = {
            "demo/public-repo": {
                1: _issue("Seed issue one", "open"),
                2: _issue("Seed issue two", "open"),
                3: _issue("Seed issue three", "closed"),
            },
            "demo/private-repo": {
                1: _issue("Private seed issue one", "open"),
                2: _issue("Private seed issue two", "open"),
            },
        }
        self.next_issue = {repo: max(items) + 1 for repo, items in self.issues.items()}
        self.pulls = {
            "demo/public-repo": {1: {"title": "Seed pull request", "state": "open"}},
            "demo/private-repo": {1: {"title": "Private seed pull request", "state": "open"}},
        }
        self.actions = {
            repo: [
                {"id": 1, "name": "ci", "status": "completed"},
                {"id": 2, "name": "lint", "status": "in_progress"},
            ]
            for repo in self.repos
        }
        self.comments = []
        self.next_comment = 1
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


def _require_repo(store, repo):
    if repo not in store.repos:
        raise Fail(404, "not_found")


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


def _issue_view(store, base, repo, number):
    issue = store.issues[repo][number]
    return {
        "number": number,
        "title": issue["title"],
        "url": "%s/%s/issues/%d" % (base, repo, number),
        "state": issue["state"],
        "public": not store.repos[repo]["private"],
    }


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
    return 200, _issue_pair(store, rec["scopes"]), {}


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

def _list_repos(store, base, body, args, headers):
    return 200, [
        {"name": name, "private": info["private"], "default_branch": info["default_branch"]}
        for name, info in store.repos.items()
    ], {}


def _get_repo(store, base, body, args, headers):
    repo = args[0]
    _require_repo(store, repo)
    info = store.repos[repo]
    return 200, {"name": repo, "private": info["private"], "default_branch": info["default_branch"]}, {}


def _remember_key(store, key):
    store.idem_history.append(key)
    del store.idem_history[:-IDEMPOTENCY_HISTORY]


def _create_issue(store, base, body, args, headers):
    repo = args[0]
    _require_repo(store, repo)
    title = _text(body, "title", required=True, limit=256)
    issue_body = _text(body, "body", required=False, limit=MAX_BODY)
    key = headers.get("Idempotency-Key")
    if key is not None:
        key = key.strip()
        if not key or len(key) > 255:
            raise Fail(400, "invalid_idempotency_key")
        _remember_key(store, key)
        existing = store.idem.get((repo, key))
        if existing is not None:
            return 201, _issue_view(store, base, repo, existing), {"X-Idempotent-Replay": "true"}
    number = store.next_issue[repo]
    store.next_issue[repo] += 1
    store.issues[repo][number] = {"title": title, "body": issue_body, "state": "open"}
    if key is not None:
        store.idem[(repo, key)] = number
    if store.fail_after_create > 0:
        # The issue exists but the reply is a 500: a client retry with the same key must replay it.
        store.fail_after_create -= 1
        raise Fail(500, "server_error")
    return 201, _issue_view(store, base, repo, number), {}


def _update_issue(store, base, body, args, headers):
    repo, number = args
    _require_repo(store, repo)
    issue = store.issues[repo].get(number)
    if issue is None:
        raise Fail(404, "not_found")
    if "title" in body:
        issue["title"] = _text(body, "title", required=True, limit=256)
    if "body" in body:
        issue["body"] = _text(body, "body", required=False, limit=MAX_BODY)
    if "state" in body:
        if body["state"] not in ("open", "closed"):
            raise Fail(400, "validation_failed")
        issue["state"] = body["state"]
    return 200, _issue_view(store, base, repo, number), {}


def _get_pull(store, base, body, args, headers):
    repo, number = args
    _require_repo(store, repo)
    pull = store.pulls[repo].get(number)
    if pull is None:
        raise Fail(404, "not_found")
    return 200, {
        "number": number,
        "title": pull["title"],
        "state": pull["state"],
        "url": "%s/%s/pull/%d" % (base, repo, number),
        "public": not store.repos[repo]["private"],
    }, {}


def _create_comment(store, base, body, args, headers):
    repo, number = args
    _require_repo(store, repo)
    if number not in store.pulls[repo]:
        raise Fail(404, "not_found")
    text = _text(body, "body", required=True, limit=MAX_BODY)
    comment_id = store.next_comment
    store.next_comment += 1
    store.comments.append({"id": comment_id, "repo": repo, "pull": number, "body": text})
    return 201, {
        "id": comment_id,
        "body": text,
        "url": "%s/%s/pull/%d#issuecomment-%d" % (base, repo, number, comment_id),
    }, {}


def _list_actions(store, base, body, args, headers):
    repo = args[0]
    _require_repo(store, repo)
    return 200, [dict(run) for run in store.actions[repo]], {}


def _match_api(path):
    """Return ({method: (scope, handler)}, args) or (None, ())."""
    if path == "/api/repos":
        return {"GET": ("repo:read", _list_repos)}, ()
    match = REPO_RE.fullmatch(path)
    if match is None:
        return None, ()
    repo, rest = match.group(1), match.group(2) or ""
    if rest == "":
        return {"GET": ("repo:read", _get_repo)}, (repo,)
    if rest == "/issues":
        return {"POST": ("issues:write", _create_issue)}, (repo,)
    if rest == "/actions":
        return {"GET": ("repo:read", _list_actions)}, (repo,)
    found = re.fullmatch(r"/issues/([0-9]+)", rest)
    if found:
        return {"PATCH": ("issues:write", _update_issue)}, (repo, int(found.group(1)))
    found = re.fullmatch(r"/pulls/([0-9]+)", rest)
    if found:
        return {"GET": ("repo:read", _get_pull)}, (repo, int(found.group(1)))
    found = re.fullmatch(r"/pulls/([0-9]+)/comments", rest)
    if found:
        return {"POST": ("pulls:write", _create_comment)}, (repo, int(found.group(1)))
    return None, ()


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
    store.retry_after = retry_after
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


def _ctl_approve(store, base, body):
    """User approval of a pending device login. Addressed by `user_code` (what the user reads on the
    consent screen, and what the Core shows) or by `device_code`; exactly one of the two."""
    device_code = body.get("device_code")
    user_code = body.get("user_code")
    scopes = body.get("scopes")
    if (device_code is None) == (user_code is None):
        raise Fail(400, "invalid_request")
    if not isinstance(scopes, list) or not all(_nonempty_str(s) for s in scopes):
        raise Fail(400, "invalid_request")
    if user_code is not None:
        if not _nonempty_str(user_code):
            raise Fail(400, "invalid_request")
        device_code = next((code for code, d in store.device.items()
                            if d["user_code"] == user_code), None)
        if device_code is None:
            raise Fail(404, "unknown_user_code")
    elif not _nonempty_str(device_code):
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


def _ctl_delay(store, base, body):
    n = body.get("n")
    seconds = body.get("seconds")
    if not _is_int(n, 0, 10000) or not _is_int(seconds, 0, 60):
        raise Fail(400, "invalid_request")
    store.delay_left = n
    store.delay_seconds = seconds
    return 200, {"delayed": n, "seconds": seconds}, {}


def _ctl_fail_after_create(store, base, body):
    n = body.get("n")
    if not _is_int(n, 0, 100):
        raise Fail(400, "invalid_request")
    store.fail_after_create = n
    return 200, {"fail_after_create": n}, {}


def _ctl_invalidate_refresh(store, base, body):
    count = 0
    for rec in store.refresh.values():
        if not rec["revoked"]:
            rec["revoked"] = True
            count += 1
    return 200, {"invalidated": count}, {}


def _ctl_state(store, base, body):
    now = time.monotonic()
    return 200, {
        "account": store.account,
        "denied_scopes": sorted(store.denied),
        "rate_limit_remaining": store.rate_left,
        "requests": store.requests,
        "issues": {
            repo: [{"number": n, "title": i["title"], "state": i["state"]}
                   for n, i in sorted(items.items())]
            for repo, items in store.issues.items()
        },
        "comments": [dict(c) for c in store.comments],
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
    "set_account": ("POST", _ctl_set_account),
    "deny_scope": ("POST", _ctl_deny_scope),
    "approve": ("POST", _ctl_approve),
    "delay": ("POST", _ctl_delay),
    "fail_after_create": ("POST", _ctl_fail_after_create),
    "invalidate_refresh": ("POST", _ctl_invalidate_refresh),
    "state": ("GET", _ctl_state),
}


# ---------------------------------------------------------------- HTTP plumbing

class Handler(BaseHTTPRequestHandler):
    server_version = "FakeGitHub/1.0"
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
            pause = 0
            if not control:
                with self.server.store.lock:
                    if self.server.store.delay_left > 0:
                        self.server.store.delay_left -= 1
                        pause = self.server.store.delay_seconds
            if pause:
                # Slow reply (timeout tests): sleeps outside the lock so other requests proceed.
                time.sleep(pause)
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
        if store.rate_left > 0:
            store.rate_left -= 1
            raise Fail(429, "rate_limited", {"Retry-After": str(store.retry_after)})
        _authorize(store, self.headers.get("Authorization"), scope)
        body = {} if method == "GET" else _parse_body(raw, self.headers.get("Content-Type"))
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
    parser = argparse.ArgumentParser(description="Fake GitHub server (test fixture, 127.0.0.1 only).")
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
