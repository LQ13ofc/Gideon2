#!/usr/bin/env python3
"""WP-11 connector self-test for the owner (python3 stdlib only; run as `python3 -I`).

Usage:
  python3 -I scripts/connector_selftest.py github-public
  python3 -I scripts/connector_selftest.py github-token --token-file PATH
  python3 -I scripts/connector_selftest.py homeassistant --url https://HOST:8123 --token-file PATH
  python3 -I scripts/connector_selftest.py google [--credentials PATH]
  python3 -I scripts/connector_selftest.py mcp --script /abs/path/server.py

Every network call goes through scripts/net_broker.py, the same broker the Core uses, so the host
allowlist and header rules are the real ones. A token is read from a 0600 file you own, placed
outside this repository; it travels only on the broker's key line and is never printed.

Exit codes: 0 = check passed, 2 = awaiting credentials (the honest state of google and
homeassistant until you provide them), 1 = check failed or blocked (the printed reason says why).
Output: one JSON object per check on stdout. No token, header or response body is ever printed.
"""
import argparse
import json
import stat
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BROKER = HERE / "net_broker.py"
DEFAULT_CREDENTIALS_DIR = Path.home() / ".config" / "gideon" / "connectors"
READINESS_WAITING = "pronto, aguardando credenciais"
MAX_LINE = 1 << 20


def report(provider, state, detail, code):
    line = {"provider": provider, "state": state, "detail": detail, "exit": code}
    sys.stdout.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return code


def read_secret(path):
    """A token file must be a regular file, owner-only (0600 or stricter), of printable ASCII."""
    target = Path(path)
    info = target.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("not_a_regular_file")
    if info.st_mode & 0o077:
        raise ValueError("permissions_too_open_use_0600")
    token = target.read_text(encoding="utf-8").strip()
    if not (8 <= len(token) <= 256 and token.isascii() and all(33 <= ord(c) <= 126 for c in token)):
        raise ValueError("token_shape_refused")
    return token


def broker_call(method, url, expected_host, headers, key, timeout_s=20):
    """Runs one request through scripts/net_broker.py exactly like the Core does. Returns (status, body_text, error)."""
    request = {
        "url": url,
        "method": method,
        "headers": headers,
        "body": "",
        "timeout_s": timeout_s,
        "expected_host": expected_host,
        "allow_http": False,
        "allow_loopback": False,
    }
    line = json.dumps(request, separators=(",", ":")) + "\n"
    key_line = json.dumps({"key": key}, separators=(",", ":")) + "\n"
    try:
        done = subprocess.run(
            [sys.executable, "-I", str(BROKER)],
            input=(line + key_line).encode("utf-8"),
            capture_output=True,
            timeout=timeout_s + 20,
        )
    except subprocess.TimeoutExpired:
        return None, "", "timeout"
    chunks, status, error = [], None, None
    for raw in done.stdout.splitlines()[:4096]:
        try:
            item = json.loads(raw.decode("utf-8"))
        except ValueError:
            continue
        if "chunk" in item:
            chunks.append(item["chunk"])
        if item.get("done"):
            status = item.get("status")
        if "error" in item:
            error = item["error"] if item.get("status") is None else "%s:%s" % (item["error"], item["status"])
    return status, "".join(chunks), error


def github_public():
    status, body, error = broker_call(
        "GET",
        "https://api.github.com/repos/LQ13ofc/Gideon2",
        "api.github.com",
        {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "gideon-core"},
        None,
    )
    if status == 200:
        repo = json.loads(body)
        return report("github", "pronto e verificado (leitura pública)", {"full_name": repo.get("full_name")}, 0)
    return report(
        "github",
        "bloqueado: broker recusou a leitura pública sem token (patch WP-6 em docs/WP11.md)",
        {"broker_error": error or "none", "status": status},
        1,
    )


def github_token(token_file):
    try:
        token = read_secret(token_file)
    except (OSError, ValueError) as error:
        return report("github", "pronto, aguardando credenciais", {"reason": str(error)}, 2)
    status, body, error = broker_call(
        "GET",
        "https://api.github.com/user",
        "api.github.com",
        {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "gideon-core"},
        token,
    )
    if status == 200:
        login = json.loads(body).get("login")
        return report("github", "conectado: token aceito", {"account": login}, 0)
    return report("github", "token recusado ou broker bloqueado", {"status": status, "broker_error": error}, 1)


def homeassistant(url, token_file):
    if not url or not token_file:
        return report("homeassistant", READINESS_WAITING, {"reason": "need --url and --token-file"}, 2)
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.path not in ("", "/"):
        return report("homeassistant", "url recusada", {"reason": "url_shape"}, 1)
    try:
        token = read_secret(token_file)
    except (OSError, ValueError) as error:
        return report("homeassistant", READINESS_WAITING, {"reason": str(error)}, 2)
    status, body, error = broker_call(
        "GET",
        url.rstrip("/") + "/api/states",
        parts.hostname,
        {"Accept": "application/json"},
        token,
    )
    if status == 200:
        return report("homeassistant", "conectado: token aceito", {"entities": len(json.loads(body))}, 0)
    return report("homeassistant", "instância recusou ou broker bloqueou", {"status": status, "broker_error": error}, 1)


def google(credentials):
    path = Path(credentials) if credentials else DEFAULT_CREDENTIALS_DIR / "google.json"
    if not path.exists():
        return report("google", READINESS_WAITING, {"expected": str(path)}, 2)
    return report(
        "google",
        "credenciais presentes; adaptador real do Google ainda não ligado (WP-11 pendente)",
        {"credentials_file": "present"},
        1,
    )


def mcp(script):
    """Speaks JSON-RPC to one server script directly (no sandbox): initialize, tools/list. Checks the shape only."""
    path = Path(script or "")
    if not path.is_absolute() or not path.is_file():
        return report("mcp", "script recusado", {"reason": "needs an absolute existing file"}, 1)
    messages = (
        '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},'
        '"clientInfo":{"name":"gideon-selftest","version":"1"}}}\n'
        '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
        '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n'
    )
    try:
        done = subprocess.run(
            [sys.executable, "-I", str(path), "--profile", "good"],
            input=messages.encode("utf-8"),
            capture_output=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return report("mcp", "servidor não respondeu a tempo", {}, 1)
    answers = {}
    for raw in done.stdout.splitlines()[:64]:
        try:
            item = json.loads(raw.decode("utf-8"))
        except ValueError:
            continue
        if isinstance(item, dict) and "id" in item:
            answers[item["id"]] = item
    init = answers.get(1, {}).get("result", {})
    tools = answers.get(2, {}).get("result", {}).get("tools")
    if not init.get("serverInfo", {}).get("name") or not isinstance(tools, list):
        return report("mcp", "resposta fora do protocolo", {}, 1)
    names = [t.get("name") for t in tools if isinstance(t, dict)]
    return report("mcp", "servidor responde ao protocolo", {"server": init["serverInfo"]["name"], "tools": names}, 0)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("check", choices=["github-public", "github-token", "homeassistant", "google", "mcp"])
    parser.add_argument("--token-file")
    parser.add_argument("--url")
    parser.add_argument("--credentials")
    parser.add_argument("--script")
    args = parser.parse_args(argv)
    if args.check == "github-public":
        return github_public()
    if args.check == "github-token":
        return github_token(args.token_file) if args.token_file else report("github", READINESS_WAITING, {"reason": "need --token-file"}, 2)
    if args.check == "homeassistant":
        return homeassistant(args.url, args.token_file)
    if args.check == "google":
        return google(args.credentials)
    return mcp(args.script)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
