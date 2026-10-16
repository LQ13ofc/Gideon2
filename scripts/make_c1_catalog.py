#!/usr/bin/env python3
"""Build the llm_engine 1.1.0 fixture: embed the recommended model catalog, refresh the manifest.

1. Reads tests/fixtures/llm_models.json (pretty source, validated here) and writes it as a Python
   literal between the GENERATED markers of tests/fixtures/llm_engine.py (the plugin is a single
   file; the catalog ships inside it, no runtime file).
2. Applies the 1.1.0 manifest fields to the llm_engine entry of tests/fixtures/hub-c1.json
   (semver, permissions, capabilities, release URLs).
3. Rewrites the linux_x86_64 binary sha256/size from the final llm_engine.py bytes and prints
   the catalog file's own sha256 (the value the Core pins as expected). hub-c0.json is not touched.

Run after every edit of llm_engine.py or llm_models.json. Stdlib only.
"""
import hashlib
import json
import pprint
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
CATALOG = FIXTURES / "hub-c1.json"
MODELS_SRC = FIXTURES / "llm_models.json"
PAYLOAD = FIXTURES / "llm_engine.py"
TARGET = "linux_x86_64"
PLUGIN_ID = "llm_engine"
MANIFEST = {
    "semver": "1.1.0",
    "permissions": ["network_llm", "storage_settings"],
    "capabilities": ["llm_engine.chat", "llm_engine.models"],
    "binary_url": "https://github.com/LQ13ofc/Gideon2/releases/download/c2-v1/llm_engine.py",
    "build_source": "https://github.com/LQ13ofc/Gideon2/tree/c2-v1",
}
BEGIN = "# BEGIN GENERATED RECOMMENDED CATALOG"
END = "# END GENERATED RECOMMENDED CATALOG"
BLOCK_RE = re.compile(r"(^" + re.escape(BEGIN) + r"[^\n]*\n).*?(^" + re.escape(END) + r")",
                      re.S | re.M)
LOCAL = ("local", "ollama")
CLOUD_CERTIFIABLE = ("google", "custom")
FEATURE_KEYS = ("streaming", "tool_use", "vision", "cancel", "context_tokens")


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_models(models: dict) -> list:
    """Honesty rules enforced at build time: only cloud google/custom entries may be certified."""
    if models.get("version") != 1 or not isinstance(models.get("models"), list):
        raise ValueError("llm_models.json: version 1 with a models list is required")
    entries = models["models"]
    ids = [entry["id"] for entry in entries]
    if len(set(ids)) != len(ids):
        raise ValueError("llm_models.json: duplicate ids")
    for entry in entries:
        cert = entry["certification"]
        features = entry["features"]
        if set(features) != set(FEATURE_KEYS):
            raise ValueError("%s: feature keys" % entry["id"])
        if cert["state"] == "certified":
            if entry["provider"] not in CLOUD_CERTIFIABLE or entry["kind"] != "cloud":
                raise ValueError("%s: only cloud google/custom entries may be certified" % entry["id"])
            if not cert.get("evidence") or not cert.get("date"):
                raise ValueError("%s: certified entries need evidence and date" % entry["id"])
        elif cert["state"] == "candidate":
            if cert.get("evidence") is not None or cert.get("date") is not None:
                raise ValueError("%s: candidate entries carry no evidence" % entry["id"])
            if any(value != "unknown" for key, value in features.items() if key != "context_tokens"):
                raise ValueError("%s: candidate entries declare no features" % entry["id"])
        else:
            raise ValueError("%s: recommended state must be certified or candidate" % entry["id"])
        if entry["provider"] in LOCAL and cert["state"] == "certified":
            raise ValueError("%s: local models are never certified" % entry["id"])
        if entry["provider"] == "custom" and not entry.get("custom_url"):
            raise ValueError("%s: custom entries need custom_url" % entry["id"])
        if "local_port" not in entry:
            raise ValueError("%s: local_port key is required (null unless local)" % entry["id"])
        port = entry["local_port"]
        if entry["provider"] in LOCAL:
            if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
                raise ValueError("%s: local entries need local_port 1024..65535" % entry["id"])
        elif port is not None:
            raise ValueError("%s: only local entries carry local_port" % entry["id"])
    return entries


def embed(payload_text: str, entries: list) -> str:
    body = "RECOMMENDED = " + pprint.pformat(entries, width=100, sort_dicts=False) + "\n"
    new, count = BLOCK_RE.subn(lambda m: m.group(1) + body + m.group(2), payload_text)
    if count != 1:
        raise ValueError("llm_engine.py: expected exactly one generated catalog block")
    return new


def patch_manifest(plugin: dict) -> None:
    plugin["semver"] = MANIFEST["semver"]
    plugin["permissions"] = list(MANIFEST["permissions"])
    plugin["capabilities"] = list(MANIFEST["capabilities"])
    plugin["build_source"] = MANIFEST["build_source"]
    for binary in plugin["binaries"]:
        if binary["target"] == TARGET:
            binary["url"] = MANIFEST["binary_url"]


def main() -> int:
    models = json.loads(MODELS_SRC.read_text(encoding="utf-8"))
    entries = check_models(models)
    payload_text = PAYLOAD.read_text(encoding="utf-8")
    PAYLOAD.write_text(embed(payload_text, entries), encoding="utf-8")

    data = PAYLOAD.read_bytes()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    by_id = {plugin["plugin_id"]: plugin for plugin in catalog["plugins"]}
    plugin = by_id.get(PLUGIN_ID)
    if plugin is None:
        print(f"error: {PLUGIN_ID} missing from {CATALOG}", file=sys.stderr)
        return 1
    patch_manifest(plugin)
    matched = 0
    for binary in plugin["binaries"]:
        if binary["target"] == TARGET:
            binary["sha256"] = sha256_of(data)
            binary["size"] = len(data)
            matched += 1
    if matched != 1:
        print(f"error: {PLUGIN_ID} needs exactly one {TARGET} binary", file=sys.stderr)
        return 1
    print(f"{PLUGIN_ID}: size={len(data)} sha256={sha256_of(data)} recommended={len(entries)}")

    text = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
    CATALOG.write_text(text, encoding="utf-8")
    print(f"catalog sha256: {sha256_of(CATALOG.read_bytes())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
