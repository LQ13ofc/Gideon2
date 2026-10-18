#!/usr/bin/env python3
"""Tests for the fake GitHub server fixture (S5/E1).

Starts tests/fixtures/connections/github_server.py as a subprocess on an
ephemeral loopback port and talks to it with urllib (stdlib only).
Run: python3 scripts/test_connections_fixtures.py
"""
import collections
import http.client
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "tests", "fixtures", "connections", "github_server.py")
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
GRANT = "urn:ietf:params:oauth:grant-type:device_code"
ALL_SCOPES = ["repo:read", "issues:write", "pulls:write"]
PUBLIC = "demo/public-repo"
PRIVATE = "demo/private-repo"
LOG_LINE = re.compile(r"^[A-Z]+ \S* \d{3}$")
MAX_BODY = 16 * 1024

Reply = collections.namedtuple("Reply", "status headers json raw")


class ServerProcess:
    """Runs the fixture server; exposes its port and accumulated stderr."""

    def __init__(self, port=0):
        self.proc = subprocess.Popen(
            [sys.executable, SERVER, "--port", str(port)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._lines = queue.Queue()
        self._stderr = []
        threading.Thread(target=self._pump_out, daemon=True).start()
        threading.Thread(target=self._pump_err, daemon=True).start()
        first = self._lines.get(timeout=10)
        if first is None:
            raise RuntimeError("server did not start: " + self.stderr_text())
        text = first.decode("ascii").strip()
        if not text.startswith("PORT="):
            raise RuntimeError("unexpected first stdout line: %r" % text)
        self.port = int(text[len("PORT="):])

    def _pump_out(self):
        for line in iter(self.proc.stdout.readline, b""):
            self._lines.put(line)
        self._lines.put(None)

    def _pump_err(self):
        for line in iter(self.proc.stderr.readline, b""):
            self._stderr.append(line.decode("utf-8", errors="replace"))

    def stderr_text(self):
        return "".join(self._stderr)

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        for stream in (self.proc.stdout, self.proc.stderr):
            stream.close()


def call(base, method, path, body=None, token=None, headers=None, raw=None):
    data = raw
    if data is None and body is not None:
        data = json.dumps(body).encode("utf-8")
    hdrs = {}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    if token is not None:
        hdrs["Authorization"] = "Bearer " + token
    hdrs.update(headers or {})
    request = urllib.request.Request(base + path, data=data, method=method, headers=hdrs)
    try:
        response = OPENER.open(request, timeout=10)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        raw_body = response.read()
        status = response.getcode()
        hdrs_out = response.headers
    try:
        parsed = json.loads(raw_body.decode("utf-8")) if raw_body else None
    except ValueError:
        parsed = None
    return Reply(status, hdrs_out, parsed, raw_body)


def listening_addresses(port):
    """Local IPv4/IPv6 addresses (hex, /proc format) with a LISTEN socket on port."""
    found = set()
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        if not os.path.exists(path):
            continue
        with open(path) as handle:
            for line in handle.readlines()[1:]:
                fields = line.split()
                if len(fields) > 3 and fields[3] == "0A" and fields[1].endswith(":%04X" % port):
                    found.add(fields[1].split(":")[0])
    return found


class ServerCase(unittest.TestCase):
    """Shares one server process; every test starts from the seed state."""

    @classmethod
    def setUpClass(cls):
        cls.proc = ServerProcess(0)
        cls.base = "http://127.0.0.1:%d" % cls.proc.port

    @classmethod
    def tearDownClass(cls):
        cls.proc.close()

    def setUp(self):
        self.assertEqual(call(self.base, "POST", "/__control/reset").status, 200)

    def device_code(self):
        reply = call(self.base, "POST", "/login/device/code", {})
        self.assertEqual(reply.status, 200)
        return reply.json["device_code"]

    def approve(self, device_code, scopes=ALL_SCOPES):
        return call(self.base, "POST", "/__control/approve",
                    {"device_code": device_code, "scopes": list(scopes)})

    def exchange(self, device_code):
        return call(self.base, "POST", "/login/oauth/access_token",
                    {"device_code": device_code, "grant_type": GRANT})

    def token(self, scopes=ALL_SCOPES):
        device_code = self.device_code()
        self.assertEqual(self.approve(device_code, scopes).status, 200)
        reply = self.exchange(device_code)
        self.assertEqual(reply.status, 200, reply.raw)
        return reply.json

    def api(self, method, path, token, body=None, headers=None):
        return call(self.base, method, path, body, token=token, headers=headers)

    def state(self):
        reply = call(self.base, "GET", "/__control/state")
        self.assertEqual(reply.status, 200)
        return reply.json

    def wait_for_log(self, needle, timeout=3.0):
        end = time.time() + timeout
        while time.time() < end:
            if needle in self.proc.stderr_text():
                return
            time.sleep(0.05)
        self.fail("log line not seen: %r" % needle)


class StartupTests(unittest.TestCase):
    def test_prints_port_and_listens_on_loopback_only(self):
        proc = ServerProcess(0)
        try:
            self.assertGreater(proc.port, 0)
            reply = call("http://127.0.0.1:%d" % proc.port, "GET", "/api/repos")
            self.assertEqual(reply.status, 401)
            if not os.path.exists("/proc/net/tcp"):
                self.skipTest("no /proc/net/tcp on this platform")
            self.assertEqual(listening_addresses(proc.port), {"0100007F"})
        finally:
            proc.close()

    def test_port_zero_gives_distinct_ephemeral_ports(self):
        first = ServerProcess(0)
        second = ServerProcess(0)
        try:
            self.assertGreater(first.port, 0)
            self.assertNotEqual(first.port, second.port)
        finally:
            first.close()
            second.close()

    def test_fixed_port_is_honoured(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        proc = ServerProcess(port)
        try:
            self.assertEqual(proc.port, port)
        finally:
            proc.close()

    def test_out_of_range_port_is_rejected(self):
        result = subprocess.run([sys.executable, SERVER, "--port", "70000"],
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(b"PORT=", result.stdout)


class DeviceFlowTests(ServerCase):
    def test_device_code_response_shape(self):
        reply = call(self.base, "POST", "/login/device/code", {})
        self.assertEqual(reply.status, 200)
        body = reply.json
        self.assertEqual(set(body), {"device_code", "user_code", "verification_uri",
                                     "expires_in", "interval"})
        self.assertEqual(body["expires_in"], 600)
        self.assertEqual(body["interval"], 1)
        self.assertTrue(body["verification_uri"].startswith(self.base))
        self.assertRegex(body["user_code"], r"^[A-Z]{4}-[A-Z]{4}$")

    def test_exchange_is_pending_until_approved(self):
        device_code = self.device_code()
        for _ in range(2):
            reply = self.exchange(device_code)
            self.assertEqual(reply.status, 400)
            self.assertEqual(reply.json, {"error": "authorization_pending"})

    def test_approve_then_exchange_returns_token_set(self):
        device_code = self.device_code()
        self.assertEqual(self.approve(device_code, ["repo:read", "issues:write"]).status, 200)
        reply = self.exchange(device_code)
        self.assertEqual(reply.status, 200)
        self.assertEqual(set(reply.json), {"access_token", "refresh_token", "expires_in",
                                           "scope", "account"})
        self.assertEqual(reply.json["expires_in"], 3600)
        self.assertEqual(reply.json["scope"], "repo:read issues:write")
        self.assertEqual(reply.json["account"], "demo-user")
        self.assertNotEqual(reply.json["access_token"], reply.json["refresh_token"])

    def test_device_code_is_single_use(self):
        device_code = self.device_code()
        self.approve(device_code)
        self.assertEqual(self.exchange(device_code).status, 200)
        reply = self.exchange(device_code)
        self.assertEqual(reply.status, 400)
        self.assertEqual(reply.json, {"error": "invalid_grant"})

    def test_expired_device_code_reports_expired_token(self):
        device_code = self.device_code()
        reply = call(self.base, "POST", "/__control/expire_token", {"device_code": device_code})
        self.assertEqual(reply.status, 200)
        reply = self.exchange(device_code)
        self.assertEqual(reply.status, 400)
        self.assertEqual(reply.json, {"error": "expired_token"})

    def test_approve_expired_device_code_is_409(self):
        device_code = self.device_code()
        call(self.base, "POST", "/__control/expire_token", {"device_code": device_code})
        self.assertEqual(self.approve(device_code).status, 409)

    def test_approve_unknown_device_code_is_404(self):
        self.assertEqual(self.approve("no-such-code").status, 404)

    def test_exchange_without_grant_type_is_400(self):
        device_code = self.device_code()
        self.approve(device_code)
        reply = call(self.base, "POST", "/login/oauth/access_token", {"device_code": device_code})
        self.assertEqual(reply.status, 400)
        self.assertEqual(reply.json, {"error": "invalid_request"})

    def test_exchange_unknown_device_code_is_invalid_grant(self):
        reply = call(self.base, "POST", "/login/oauth/access_token",
                     {"device_code": "nope", "grant_type": GRANT})
        self.assertEqual(reply.json, {"error": "invalid_grant"})

    def test_form_encoded_exchange_is_accepted(self):
        device_code = self.device_code()
        self.approve(device_code)
        raw = urllib.parse.urlencode({"device_code": device_code, "grant_type": GRANT}).encode()
        reply = call(self.base, "POST", "/login/oauth/access_token", raw=raw,
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(reply.status, 200)
        self.assertIn("access_token", reply.json)

    def test_denied_scope_is_stripped_from_grant(self):
        call(self.base, "POST", "/__control/deny_scope", {"scope": "pulls:write"})
        device_code = self.device_code()
        granted = self.approve(device_code, ALL_SCOPES).json["granted_scopes"]
        self.assertEqual(granted, ["repo:read", "issues:write"])
        self.assertEqual(self.exchange(device_code).json["scope"], "repo:read issues:write")

    def test_approve_rejects_non_list_scopes(self):
        device_code = self.device_code()
        reply = call(self.base, "POST", "/__control/approve",
                     {"device_code": device_code, "scopes": "repo:read"})
        self.assertEqual(reply.status, 400)


class RefreshRevokeTests(ServerCase):
    def test_refresh_rotates_tokens_and_keeps_scope(self):
        old = self.token(["repo:read"])
        reply = call(self.base, "POST", "/login/oauth/refresh",
                     {"refresh_token": old["refresh_token"]})
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.json["scope"], "repo:read")
        self.assertNotEqual(reply.json["access_token"], old["access_token"])
        self.assertEqual(self.api("GET", "/api/repos", reply.json["access_token"]).status, 200)
        again = call(self.base, "POST", "/login/oauth/refresh",
                     {"refresh_token": old["refresh_token"]})
        self.assertEqual(again.status, 400)
        self.assertEqual(again.json, {"error": "invalid_grant"})

    def test_refresh_unknown_token_is_invalid_grant(self):
        reply = call(self.base, "POST", "/login/oauth/refresh", {"refresh_token": "bogus"})
        self.assertEqual(reply.status, 400)
        self.assertEqual(reply.json, {"error": "invalid_grant"})

    def test_revoke_access_token_makes_api_401(self):
        tok = self.token()
        self.assertEqual(self.api("GET", "/api/repos", tok["access_token"]).status, 200)
        reply = call(self.base, "POST", "/login/oauth/revoke", {"token": tok["access_token"]})
        self.assertEqual(reply.json, {"revoked": True})
        after = self.api("GET", "/api/repos", tok["access_token"])
        self.assertEqual(after.status, 401)
        self.assertEqual(after.json, {"error": "bad_credentials"})

    def test_revoke_refresh_token_blocks_refresh(self):
        tok = self.token()
        call(self.base, "POST", "/login/oauth/revoke", {"token": tok["refresh_token"]})
        reply = call(self.base, "POST", "/login/oauth/refresh",
                     {"refresh_token": tok["refresh_token"]})
        self.assertEqual(reply.json, {"error": "invalid_grant"})

    def test_revoke_unknown_token_reports_not_revoked(self):
        reply = call(self.base, "POST", "/login/oauth/revoke", {"token": "nothing"})
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.json, {"revoked": False})

    def test_revoke_without_token_is_400(self):
        reply = call(self.base, "POST", "/login/oauth/revoke", {})
        self.assertEqual(reply.status, 400)


class ExpiryTests(ServerCase):
    def test_expire_all_access_tokens(self):
        first = self.token()
        second = self.token()
        self.assertEqual(call(self.base, "POST", "/__control/expire_token", {}).status, 200)
        for tok in (first, second):
            reply = self.api("GET", "/api/repos", tok["access_token"])
            self.assertEqual(reply.status, 401)
            self.assertEqual(reply.json, {"error": "bad_credentials"})

    def test_expire_single_access_token(self):
        first = self.token()
        second = self.token()
        call(self.base, "POST", "/__control/expire_token", {"access_token": first["access_token"]})
        self.assertEqual(self.api("GET", "/api/repos", first["access_token"]).status, 401)
        self.assertEqual(self.api("GET", "/api/repos", second["access_token"]).status, 200)

    def test_expire_unknown_access_token_is_404(self):
        reply = call(self.base, "POST", "/__control/expire_token", {"access_token": "nope"})
        self.assertEqual(reply.status, 404)

    def test_expired_access_token_can_be_refreshed(self):
        tok = self.token()
        call(self.base, "POST", "/__control/expire_token", {"access_token": tok["access_token"]})
        reply = call(self.base, "POST", "/login/oauth/refresh",
                     {"refresh_token": tok["refresh_token"]})
        self.assertEqual(reply.status, 200)
        self.assertEqual(self.api("GET", "/api/repos", reply.json["access_token"]).status, 200)


class AuthTests(ServerCase):
    def test_missing_authorization_is_401(self):
        reply = call(self.base, "GET", "/api/repos")
        self.assertEqual(reply.status, 401)
        self.assertEqual(reply.json, {"error": "bad_credentials"})

    def test_unknown_token_is_401_and_not_echoed(self):
        reply = call(self.base, "GET", "/api/repos", token="sentinel-bad-token-123")
        self.assertEqual(reply.status, 401)
        self.assertNotIn(b"sentinel-bad-token-123", reply.raw)

    def test_non_bearer_scheme_is_401(self):
        tok = self.token()
        reply = call(self.base, "GET", "/api/repos", headers={
            "Authorization": "Basic " + tok["access_token"]})
        self.assertEqual(reply.status, 401)

    def test_missing_scope_is_403(self):
        tok = self.token(["repo:read"])
        reply = self.api("POST", "/api/repos/%s/issues" % PUBLIC, tok["access_token"],
                         {"title": "x"})
        self.assertEqual(reply.status, 403)
        self.assertEqual(reply.json, {"error": "insufficient_scope"})

    def test_comment_needs_pulls_write(self):
        tok = self.token(["repo:read", "issues:write"])
        reply = self.api("POST", "/api/repos/%s/pulls/1/comments" % PUBLIC, tok["access_token"],
                         {"body": "hi"})
        self.assertEqual(reply.status, 403)

    def test_denied_scope_blocks_already_granted_scope(self):
        tok = self.token(["repo:read"])
        call(self.base, "POST", "/__control/deny_scope", {"scope": "repo:read"})
        reply = self.api("GET", "/api/repos", tok["access_token"])
        self.assertEqual(reply.status, 403)
        self.assertEqual(reply.json, {"error": "insufficient_scope"})


class ReposTests(ServerCase):
    def test_list_repos_returns_seed_repos(self):
        tok = self.token()
        reply = self.api("GET", "/api/repos", tok["access_token"])
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.json, [
            {"name": PUBLIC, "private": False, "default_branch": "main"},
            {"name": PRIVATE, "private": True, "default_branch": "main"},
        ])

    def test_get_public_and_private_repo(self):
        tok = self.token()
        public = self.api("GET", "/api/repos/%s" % PUBLIC, tok["access_token"]).json
        private = self.api("GET", "/api/repos/%s" % PRIVATE, tok["access_token"]).json
        self.assertEqual(public, {"name": PUBLIC, "private": False, "default_branch": "main"})
        self.assertTrue(private["private"])

    def test_unknown_repo_is_404(self):
        tok = self.token()
        reply = self.api("GET", "/api/repos/demo/none", tok["access_token"])
        self.assertEqual(reply.status, 404)
        self.assertEqual(reply.json, {"error": "not_found"})

    def test_repo_without_owner_segment_is_404(self):
        tok = self.token()
        self.assertEqual(self.api("GET", "/api/repos/public-repo", tok["access_token"]).status, 404)


class IssueTests(ServerCase):
    def issues_path(self, repo=PUBLIC):
        return "/api/repos/%s/issues" % repo

    def test_create_issue_shape_for_public_repo(self):
        tok = self.token()
        reply = self.api("POST", self.issues_path(), tok["access_token"], {"title": "New"})
        self.assertEqual(reply.status, 201)
        self.assertEqual(set(reply.json), {"number", "title", "url", "state", "public"})
        self.assertEqual(reply.json["number"], 4)
        self.assertEqual(reply.json["title"], "New")
        self.assertEqual(reply.json["state"], "open")
        self.assertIs(reply.json["public"], True)
        self.assertTrue(reply.json["url"].endswith("/demo/public-repo/issues/4"))

    def test_create_issue_in_private_repo_is_not_public(self):
        tok = self.token()
        reply = self.api("POST", self.issues_path(PRIVATE), tok["access_token"], {"title": "P"})
        self.assertIs(reply.json["public"], False)
        self.assertEqual(reply.json["number"], 3)

    def test_issue_numbers_increase_per_repo(self):
        tok = self.token()
        first = self.api("POST", self.issues_path(), tok["access_token"], {"title": "a"}).json
        second = self.api("POST", self.issues_path(), tok["access_token"], {"title": "b"}).json
        self.assertEqual(second["number"], first["number"] + 1)

    def test_create_issue_validation(self):
        tok = self.token()
        cases = [{}, {"title": ""}, {"title": "   "}, {"title": 5}, {"title": "ok", "body": 7}]
        for body in cases:
            with self.subTest(body=body):
                reply = self.api("POST", self.issues_path(), tok["access_token"], body)
                self.assertEqual(reply.status, 400)
                self.assertEqual(reply.json, {"error": "validation_failed"})

    def test_idempotency_key_replays_same_issue(self):
        tok = self.token()
        headers = {"Idempotency-Key": "k-replay-1"}
        first = self.api("POST", self.issues_path(), tok["access_token"], {"title": "A"}, headers)
        second = self.api("POST", self.issues_path(), tok["access_token"], {"title": "A"}, headers)
        third = self.api("POST", self.issues_path(), tok["access_token"], {"title": "A"}, headers)
        self.assertEqual(first.status, 201)
        self.assertIsNone(first.headers.get("X-Idempotent-Replay"))
        self.assertEqual(second.json["number"], first.json["number"])
        self.assertEqual(third.json["number"], first.json["number"])
        self.assertEqual(second.headers.get("X-Idempotent-Replay"), "true")
        self.assertEqual(len(self.state()["issues"][PUBLIC]), 4)

    def test_distinct_idempotency_keys_create_distinct_issues(self):
        tok = self.token()
        a = self.api("POST", self.issues_path(), tok["access_token"], {"title": "A"},
                     {"Idempotency-Key": "k-a"})
        b = self.api("POST", self.issues_path(), tok["access_token"], {"title": "B"},
                     {"Idempotency-Key": "k-b"})
        self.assertNotEqual(a.json["number"], b.json["number"])
        self.assertIsNone(b.headers.get("X-Idempotent-Replay"))

    def test_idempotency_key_is_scoped_per_repo(self):
        tok = self.token()
        headers = {"Idempotency-Key": "shared-key"}
        public = self.api("POST", self.issues_path(), tok["access_token"], {"title": "A"}, headers)
        private = self.api("POST", self.issues_path(PRIVATE), tok["access_token"],
                           {"title": "A"}, headers)
        self.assertIsNone(private.headers.get("X-Idempotent-Replay"))
        self.assertEqual(private.json["number"], 3)
        self.assertEqual(public.json["number"], 4)

    def test_update_issue_title_and_state(self):
        tok = self.token()
        reply = self.api("PATCH", self.issues_path() + "/1", tok["access_token"],
                         {"title": "Renamed", "state": "closed"})
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.json["title"], "Renamed")
        self.assertEqual(reply.json["state"], "closed")
        listed = self.state()["issues"][PUBLIC][0]
        self.assertEqual((listed["title"], listed["state"]), ("Renamed", "closed"))

    def test_update_issue_rejects_bad_state(self):
        tok = self.token()
        reply = self.api("PATCH", self.issues_path() + "/1", tok["access_token"], {"state": "merged"})
        self.assertEqual(reply.status, 400)

    def test_update_unknown_issue_is_404(self):
        tok = self.token()
        reply = self.api("PATCH", self.issues_path() + "/999", tok["access_token"], {"title": "x"})
        self.assertEqual(reply.status, 404)

    def test_update_needs_issues_write(self):
        tok = self.token(["repo:read"])
        reply = self.api("PATCH", self.issues_path() + "/1", tok["access_token"], {"title": "x"})
        self.assertEqual(reply.status, 403)

    def test_concurrent_creates_get_unique_numbers(self):
        tok = self.token()
        numbers = []
        errors = []
        lock = threading.Lock()

        def worker(index):
            for step in range(5):
                reply = self.api("POST", self.issues_path(), tok["access_token"],
                                 {"title": "c"}, {"Idempotency-Key": "w%d-%d" % (index, step)})
                with lock:
                    if reply.status == 201:
                        numbers.append(reply.json["number"])
                    else:
                        errors.append(reply.status)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual(errors, [])
        self.assertEqual(len(numbers), 40)
        self.assertEqual(len(set(numbers)), 40)


class PullActionTests(ServerCase):
    def test_get_seed_pull(self):
        tok = self.token()
        reply = self.api("GET", "/api/repos/%s/pulls/1" % PUBLIC, tok["access_token"])
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.json["number"], 1)
        self.assertEqual(reply.json["title"], "Seed pull request")
        self.assertEqual(reply.json["state"], "open")
        self.assertIs(reply.json["public"], True)

    def test_unknown_pull_is_404(self):
        tok = self.token()
        self.assertEqual(self.api("GET", "/api/repos/%s/pulls/77" % PUBLIC,
                                  tok["access_token"]).status, 404)

    def test_pull_read_needs_repo_read(self):
        tok = self.token(["issues:write"])
        self.assertEqual(self.api("GET", "/api/repos/%s/pulls/1" % PUBLIC,
                                  tok["access_token"]).status, 403)

    def test_create_comment_is_recorded(self):
        tok = self.token()
        reply = self.api("POST", "/api/repos/%s/pulls/1/comments" % PUBLIC,
                         tok["access_token"], {"body": "LGTM"})
        self.assertEqual(reply.status, 201)
        self.assertIsInstance(reply.json["id"], int)
        self.assertEqual(reply.json["body"], "LGTM")
        self.assertIn({"id": reply.json["id"], "repo": PUBLIC, "pull": 1, "body": "LGTM"},
                      self.state()["comments"])

    def test_comment_requires_body(self):
        tok = self.token()
        reply = self.api("POST", "/api/repos/%s/pulls/1/comments" % PUBLIC,
                         tok["access_token"], {})
        self.assertEqual(reply.status, 400)

    def test_comment_on_unknown_pull_is_404(self):
        tok = self.token()
        reply = self.api("POST", "/api/repos/%s/pulls/50/comments" % PUBLIC,
                         tok["access_token"], {"body": "x"})
        self.assertEqual(reply.status, 404)

    def test_actions_list_shape(self):
        tok = self.token()
        reply = self.api("GET", "/api/repos/%s/actions" % PRIVATE, tok["access_token"])
        self.assertEqual(reply.status, 200)
        self.assertGreaterEqual(len(reply.json), 1)
        for run in reply.json:
            self.assertEqual(set(run), {"id", "name", "status"})


class ControlTests(ServerCase):
    def test_state_shape_and_no_credentials_in_output(self):
        tok = self.token()
        self.api("GET", "/api/repos", tok["access_token"])
        reply = call(self.base, "GET", "/__control/state")
        self.assertEqual(reply.status, 200)
        for key in ("account", "denied_scopes", "rate_limit_remaining", "requests", "issues",
                    "comments", "last_idempotency_keys", "tokens", "device_codes_pending"):
            self.assertIn(key, reply.json)
        self.assertEqual(set(reply.json["tokens"]), {"issued", "revoked", "active"})
        self.assertNotIn(tok["access_token"].encode(), reply.raw)
        self.assertNotIn(tok["refresh_token"].encode(), reply.raw)
        self.assertNotIn(b"Bearer", reply.raw)

    def test_state_counts_tokens_issued_and_revoked(self):
        tok = self.token()
        before = self.state()["tokens"]
        self.assertEqual(before, {"issued": 1, "revoked": 0, "active": 1})
        call(self.base, "POST", "/login/oauth/revoke", {"token": tok["access_token"]})
        after = self.state()["tokens"]
        self.assertEqual(after, {"issued": 1, "revoked": 1, "active": 0})

    def test_state_records_idempotency_keys(self):
        tok = self.token()
        self.api("POST", self.issues_path_public(), tok["access_token"], {"title": "k"},
                 {"Idempotency-Key": "abc-123"})
        self.assertEqual(self.state()["last_idempotency_keys"], ["abc-123"])

    def issues_path_public(self):
        return "/api/repos/%s/issues" % PUBLIC

    def test_reset_restores_seed_and_drops_tokens(self):
        tok = self.token()
        self.api("POST", self.issues_path_public(), tok["access_token"], {"title": "extra"})
        call(self.base, "POST", "/__control/deny_scope", {"scope": "repo:read"})
        self.assertEqual(call(self.base, "POST", "/__control/reset").status, 200)
        self.assertEqual(self.api("GET", "/api/repos", tok["access_token"]).status, 401)
        state = self.state()
        self.assertEqual(len(state["issues"][PUBLIC]), 3)
        self.assertEqual(state["denied_scopes"], [])
        self.assertEqual(state["tokens"], {"issued": 0, "revoked": 0, "active": 0})

    def test_set_account_changes_token_account_and_header(self):
        self.assertEqual(call(self.base, "POST", "/__control/set_account",
                              {"name": "acme-test"}).status, 200)
        tok = self.token()
        self.assertEqual(tok["account"], "acme-test")
        reply = self.api("GET", "/api/repos", tok["access_token"])
        self.assertEqual(reply.headers.get("X-Account"), "acme-test")
        missing = self.api("GET", "/api/repos/demo/none", tok["access_token"])
        self.assertEqual(missing.headers.get("X-Account"), "acme-test")

    def test_set_account_rejects_invalid_names(self):
        for name in ("bad name", "x\r\nInjected: 1", "", 42):
            with self.subTest(name=name):
                reply = call(self.base, "POST", "/__control/set_account", {"name": name})
                self.assertEqual(reply.status, 400)

    def test_x_account_header_on_every_response(self):
        reply = call(self.base, "GET", "/nope")
        self.assertEqual(reply.status, 404)
        self.assertEqual(reply.headers.get("X-Account"), "demo-user")

    def test_rate_limit_returns_429_with_retry_after(self):
        tok = self.token()
        call(self.base, "POST", "/__control/rate_limit", {"n": 2, "retry_after": 7})
        for _ in range(2):
            reply = self.api("GET", "/api/repos", tok["access_token"])
            self.assertEqual(reply.status, 429)
            self.assertEqual(reply.headers.get("Retry-After"), "7")
            self.assertEqual(reply.json, {"error": "rate_limited"})
        self.assertEqual(self.api("GET", "/api/repos", tok["access_token"]).status, 200)

    def test_rate_limit_does_not_touch_login_routes(self):
        call(self.base, "POST", "/__control/rate_limit", {"n": 1})
        reply = call(self.base, "POST", "/login/device/code", {})
        self.assertEqual(reply.status, 200)
        self.assertEqual(self.state()["rate_limit_remaining"], 1)

    def test_rate_limit_rejects_bad_values(self):
        reply = call(self.base, "POST", "/__control/rate_limit", {"n": "two"})
        self.assertEqual(reply.status, 400)

    def test_deny_scope_is_listed_in_state(self):
        call(self.base, "POST", "/__control/deny_scope", {"scope": "pulls:write"})
        self.assertEqual(self.state()["denied_scopes"], ["pulls:write"])

    def test_control_unknown_is_404_and_wrong_method_405(self):
        self.assertEqual(call(self.base, "POST", "/__control/nope", {}).status, 404)
        self.assertEqual(call(self.base, "GET", "/__control/reset").status, 405)
        self.assertEqual(call(self.base, "POST", "/__control/state", {}).status, 405)


class SecurityTests(ServerCase):
    def test_unknown_paths_are_404(self):
        tok = self.token()
        cases = [("GET", "/"), ("POST", "/nope"), ("GET", "/login/nope"),
                 ("GET", "/api/nope")]
        for method, path in cases:
            with self.subTest(method=method, path=path):
                reply = call(self.base, method, path, token=tok["access_token"])
                self.assertEqual(reply.status, 404)
                self.assertEqual(reply.json, {"error": "not_found"})

    def test_known_path_with_wrong_method_is_405(self):
        self.assertEqual(call(self.base, "DELETE", "/api/repos").status, 405)
        self.assertEqual(call(self.base, "PUT", "/login/device/code", {}).status, 405)
        self.assertEqual(call(self.base, "GET", "/login/oauth/revoke").status, 405)

    def test_body_at_16_kib_is_accepted(self):
        tok = self.token()
        overhead = len(json.dumps({"title": "t", "body": ""}).encode("utf-8"))
        raw = json.dumps({"title": "t", "body": "x" * (MAX_BODY - overhead)}).encode("utf-8")
        self.assertEqual(len(raw), MAX_BODY)
        reply = call(self.base, "POST", "/api/repos/%s/issues" % PUBLIC, token=tok["access_token"],
                     raw=raw)
        self.assertEqual(reply.status, 201)

    def test_body_over_16_kib_is_413_and_creates_nothing(self):
        tok = self.token()
        before = len(self.state()["issues"][PUBLIC])
        overhead = len(json.dumps({"title": "t", "body": ""}).encode("utf-8"))
        raw = json.dumps({"title": "t", "body": "x" * (MAX_BODY + 1 - overhead)}).encode("utf-8")
        self.assertEqual(len(raw), MAX_BODY + 1)
        reply = call(self.base, "POST", "/api/repos/%s/issues" % PUBLIC, token=tok["access_token"],
                     raw=raw)
        self.assertEqual(reply.status, 413)
        self.assertEqual(reply.json, {"error": "payload_too_large"})
        self.assertEqual(len(self.state()["issues"][PUBLIC]), before)

    def test_oversized_control_body_is_413(self):
        raw = b"{" + b'"name": "' + b"a" * MAX_BODY + b'"}'
        reply = call(self.base, "POST", "/__control/set_account", raw=raw)
        self.assertEqual(reply.status, 413)

    def test_invalid_json_is_400(self):
        tok = self.token()
        reply = call(self.base, "POST", "/api/repos/%s/issues" % PUBLIC, token=tok["access_token"],
                     raw=b"{not json")
        self.assertEqual(reply.status, 400)
        self.assertEqual(reply.json, {"error": "invalid_json"})

    def test_json_array_body_is_400(self):
        tok = self.token()
        reply = call(self.base, "POST", "/api/repos/%s/issues" % PUBLIC, token=tok["access_token"],
                     raw=b"[1, 2]")
        self.assertEqual(reply.status, 400)

    def test_chunked_request_is_411(self):
        port = self.proc.port
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            conn.putrequest("POST", "/api/repos/%s/issues" % PUBLIC)
            conn.putheader("Transfer-Encoding", "chunked")
            conn.endheaders()
            response = conn.getresponse()
            self.assertEqual(response.status, 411)
            response.read()
        finally:
            conn.close()

    def test_logs_hold_only_method_path_status_and_no_secrets(self):
        tok = self.token()
        self.api("GET", "/api/repos", tok["access_token"])
        self.api("GET", "/api/repos", "sentinel-bad-token-999")
        self.wait_for_log("GET /api/repos 401")
        text = self.proc.stderr_text()
        lines = [line for line in text.splitlines() if line]
        self.assertTrue(lines)
        for line in lines:
            self.assertRegex(line, LOG_LINE)
        for secret in (tok["access_token"], tok["refresh_token"], "sentinel-bad-token-999"):
            self.assertNotIn(secret, text)
        self.assertNotIn("Bearer", text)
        self.assertNotIn("Authorization", text)


class UserCodeApprovalTests(ServerCase):
    def start_login(self):
        reply = call(self.base, "POST", "/login/device/code", {})
        self.assertEqual(reply.status, 200)
        return reply.json["device_code"], reply.json["user_code"]

    def test_approve_by_user_code_grants_requested_scopes(self):
        device_code, user_code = self.start_login()
        reply = call(self.base, "POST", "/__control/approve",
                     {"user_code": user_code, "scopes": ["repo:read"]})
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.json["granted_scopes"], ["repo:read"])
        token = self.exchange(device_code)
        self.assertEqual(token.status, 200)
        self.assertEqual(token.json["scope"], "repo:read")

    def test_approve_by_user_code_strips_denied_scopes(self):
        call(self.base, "POST", "/__control/deny_scope", {"scope": "pulls:write"})
        device_code, user_code = self.start_login()
        reply = call(self.base, "POST", "/__control/approve",
                     {"user_code": user_code, "scopes": ALL_SCOPES})
        self.assertEqual(reply.json["granted_scopes"], ["repo:read", "issues:write"])
        self.assertEqual(self.exchange(device_code).status, 200)

    def test_approve_by_unknown_user_code_is_404(self):
        reply = call(self.base, "POST", "/__control/approve",
                     {"user_code": "ZZZZ-ZZZZ", "scopes": ["repo:read"]})
        self.assertEqual(reply.status, 404)
        self.assertEqual(reply.json, {"error": "unknown_user_code"})

    def test_approve_needs_exactly_one_of_device_or_user_code(self):
        device_code, user_code = self.start_login()
        both = call(self.base, "POST", "/__control/approve",
                    {"device_code": device_code, "user_code": user_code, "scopes": ["repo:read"]})
        neither = call(self.base, "POST", "/__control/approve", {"scopes": ["repo:read"]})
        self.assertEqual(both.status, 400)
        self.assertEqual(neither.status, 400)
        self.assertEqual(self.exchange(device_code).json, {"error": "authorization_pending"})

    def test_user_code_approval_then_exchange_is_single_use(self):
        device_code, user_code = self.start_login()
        call(self.base, "POST", "/__control/approve", {"user_code": user_code, "scopes": ["repo:read"]})
        self.assertEqual(self.exchange(device_code).status, 200)
        self.assertEqual(self.exchange(device_code).json, {"error": "invalid_grant"})


class FaultControlTests(ServerCase):
    def test_delay_slows_the_next_api_requests_only(self):
        tok = self.token()
        self.assertEqual(call(self.base, "POST", "/__control/delay", {"n": 1, "seconds": 1}).status, 200)
        started = time.monotonic()
        self.assertEqual(self.api("GET", "/api/repos", tok["access_token"]).status, 200)
        self.assertGreaterEqual(time.monotonic() - started, 0.9)
        started = time.monotonic()
        self.assertEqual(self.api("GET", "/api/repos", tok["access_token"]).status, 200)
        self.assertLess(time.monotonic() - started, 0.9)

    def test_delay_rejects_out_of_range_values(self):
        reply = call(self.base, "POST", "/__control/delay", {"n": 1, "seconds": 61})
        self.assertEqual(reply.status, 400)

    def test_fail_after_create_keeps_the_issue_and_replays_the_key(self):
        tok = self.token(["repo:read", "issues:write"])
        call(self.base, "POST", "/__control/fail_after_create", {"n": 1})
        key = {"Idempotency-Key": "retry-key-1"}
        body = {"title": "uma vez"}
        first = self.api("POST", "/api/repos/%s/issues" % PRIVATE, tok["access_token"], body, key)
        self.assertEqual(first.status, 500)
        second = self.api("POST", "/api/repos/%s/issues" % PRIVATE, tok["access_token"], body, key)
        self.assertEqual(second.status, 201)
        self.assertEqual(second.headers.get("X-Idempotent-Replay"), "true")
        titles = [i["title"] for i in self.state()["issues"][PRIVATE] if i["title"] == "uma vez"]
        self.assertEqual(len(titles), 1)

    def test_invalidate_refresh_spends_every_refresh_token(self):
        tok = self.token()
        reply = call(self.base, "POST", "/__control/invalidate_refresh", {})
        self.assertEqual(reply.status, 200)
        self.assertGreaterEqual(reply.json["invalidated"], 1)
        refused = call(self.base, "POST", "/login/oauth/refresh", {"refresh_token": tok["refresh_token"]})
        self.assertEqual(refused.json, {"error": "invalid_grant"})

    def test_reset_clears_delay_and_fail_controls(self):
        call(self.base, "POST", "/__control/fail_after_create", {"n": 5})
        call(self.base, "POST", "/__control/delay", {"n": 5, "seconds": 2})
        call(self.base, "POST", "/__control/reset", {})
        tok = self.token(["repo:read", "issues:write"])
        started = time.monotonic()
        reply = self.api("POST", "/api/repos/%s/issues" % PRIVATE, tok["access_token"], {"title": "ok"},
                         {"Idempotency-Key": "after-reset"})
        self.assertEqual(reply.status, 201)
        self.assertLess(time.monotonic() - started, 1.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
