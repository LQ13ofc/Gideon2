#!/usr/bin/env python3
"""Regenerate sha256/size of the C0 dummy payloads in tests/fixtures/hub-c0.json.

Reads tests/fixtures/dummy_echo.py and tests/fixtures/dummy_evil.py, rewrites the
matching linux_x86_64 binary entries in place (field order and other fields kept),
and prints the catalog file's own sha256 (the value the Core pins as expected).
plain_opaque is not touched: its payload is the 15-byte benign_fixture.bin.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
CATALOG = FIXTURES / "hub-c0.json"
PAYLOADS = {
    "dummy_echo": FIXTURES / "dummy_echo.py",
    "dummy_evil": FIXTURES / "dummy_evil.py",
}
TARGET = "linux_x86_64"


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    by_id = {plugin["plugin_id"]: plugin for plugin in catalog["plugins"]}
    for plugin_id, payload in PAYLOADS.items():
        plugin = by_id.get(plugin_id)
        if plugin is None:
            print(f"error: {plugin_id} missing from {CATALOG}", file=sys.stderr)
            return 1
        data = payload.read_bytes()
        matched = 0
        for binary in plugin["binaries"]:
            if binary["target"] == TARGET:
                binary["sha256"] = sha256_of(data)
                binary["size"] = len(data)
                matched += 1
        if matched != 1:
            print(f"error: {plugin_id} needs exactly one {TARGET} binary", file=sys.stderr)
            return 1
        print(f"{plugin_id}: size={len(data)} sha256={sha256_of(data)}")

    text = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
    CATALOG.write_text(text, encoding="utf-8")
    print(f"catalog sha256: {sha256_of(CATALOG.read_bytes())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
