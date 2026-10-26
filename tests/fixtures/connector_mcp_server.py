#!/usr/bin/env python3
"""Real stdio MCP server used by WP-11 tests (python3 stdlib only, JSON-RPC 2.0, one message per line).

It is a genuine MCP server: initialize, notifications/initialized, tools/list and tools/call. The Core
launches it inside the plugin sandbox (no network, cleared environment, read-only root). The `--profile`
argument is the launch tag the Core always passes; this server ignores it. Its notes live in memory only,
so a restart forgets them. Nothing is written to disk and nothing is read from the host except stdin.
"""
import json
import sys

SERVER_NAME = "connector-notes"
NOTES = {"ola": "mundo", "lista": "um, dois, tres"}

TOOLS = [
    {
        "name": "list_notes",
        "description": "Lista os titulos das notas",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "read_note",
        "description": "Le o texto de uma nota",
        "inputSchema": {
            "type": "object",
            "properties": {"title": {"type": "string", "maxLength": 64}},
            "required": ["title"],
            "additionalProperties": False,
        },
    },
    {
        "name": "delete_note",
        "description": "Apaga uma nota",
        "annotations": {"destructiveHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {"title": {"type": "string", "maxLength": 64}},
            "required": ["title"],
            "additionalProperties": False,
        },
    },
]


def reply(message_id, result=None, error=None):
    message = {"jsonrpc": "2.0", "id": message_id}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def text_result(text, is_error=False):
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def call(name, args):
    if name == "list_notes":
        return text_result(", ".join(sorted(NOTES)) or "(sem notas)")
    if name == "read_note":
        title = args.get("title", "")
        if title not in NOTES:
            return text_result("nota nao encontrada", is_error=True)
        return text_result(NOTES[title])
    if name == "delete_note":
        title = args.get("title", "")
        if title not in NOTES:
            return text_result("nota nao encontrada", is_error=True)
        del NOTES[title]
        return text_result("apagada: " + title)
    return None


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except ValueError:
            reply(None, error={"code": -32700, "message": "parse error"})
            continue
        method = message.get("method")
        message_id = message.get("id")
        if message_id is None:
            # Notifications (for example notifications/initialized) get no answer.
            continue
        if method == "initialize":
            reply(
                message_id,
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": "1"},
                },
            )
        elif method == "tools/list":
            reply(message_id, {"tools": TOOLS})
        elif method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            if name not in {tool["name"] for tool in TOOLS}:
                reply(message_id, error={"code": -32602, "message": "unknown tool"})
                continue
            result = call(name, params.get("arguments") or {})
            reply(message_id, result)
        else:
            reply(message_id, error={"code": -32601, "message": "method not found"})


if __name__ == "__main__":
    sys.exit(main())
