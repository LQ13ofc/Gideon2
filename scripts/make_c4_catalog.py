#!/usr/bin/env python3
"""Build the C4 catalog tests/fixtures/hub-c4.json: the six C4 plugins (C4.1-C4.6).

Each entry is a manifest in the C0 schema (fields as in tests/fixtures/hub-c0.json) plus one
linux_x86_64 binary whose sha256 and size come from the payload file
tests/fixtures/c4/<plugin_id>.py. A payload that does not exist yet is skipped with a message;
re-run this script once it appears. Manifest rules are checked here (C0 capability regex, id
prefix, reserved namespaces) so a bad catalog never gets written.

Prints the catalog file's own sha256 (the value the Core pins as expected). Stdlib only.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
PAYLOAD_DIR = FIXTURES / "c4"
CATALOG = FIXTURES / "hub-c4.json"
TARGET = "linux_x86_64"
REPOSITORY = "https://github.com/LQ13ofc/Gideon2"
RELEASE_URL = REPOSITORY + "/releases/download/c4-v1/%s.py"
BUILD_SOURCE = REPOSITORY + "/tree/c4-v1"
PUBLISHER = "Gideon local test fixture"
SUPPORT_POLICY = "Fixture de teste local; sem suporte de produto"
CAPABILITY_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
RESERVED = ("base", "core", "system", "safety", "llm", "screen", "computer", "audio",
            "mic", "camera", "display")  # mirror of src/plugins.rs RESERVED
MAX_CAPABILITIES = 8

# Order follows docs/C4.md. Permissions are the C4.0 manifest strings; none is granted by default.
PLUGINS = [
    {"plugin_id": "screen_observe", "permissions": ["screen_observe"],
     "capabilities": ["screen_observe.capture", "screen_observe.status"]},
    {"plugin_id": "computer_control", "permissions": ["input_control"],
     "capabilities": ["computer_control.tree", "computer_control.act", "computer_control.status"]},
    {"plugin_id": "audio_advanced", "permissions": ["audio_route"],
     "capabilities": ["audio_advanced.state", "audio_advanced.act"]},
    {"plugin_id": "mic_advanced", "permissions": ["mic_config"],
     "capabilities": ["mic_advanced.state", "mic_advanced.configure", "mic_advanced.monitor",
                      "mic_advanced.record"]},
    {"plugin_id": "camera_gesture", "permissions": ["camera_capture"],
     "capabilities": ["camera_gesture.state", "camera_gesture.optin", "camera_gesture.capture",
                      "camera_gesture.gestures"]},
    {"plugin_id": "display_manipulate", "permissions": ["display_manipulate"],
     "capabilities": ["display_manipulate.status"]},
]


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_spec(spec: dict) -> None:
    """Fail closed on a manifest the C0 rules would quarantine."""
    plugin_id = spec["plugin_id"]
    if plugin_id in RESERVED:
        raise ValueError(f"{plugin_id}: plugin id is reserved")
    caps = spec["capabilities"]
    if not 0 < len(caps) <= MAX_CAPABILITIES:
        raise ValueError(f"{plugin_id}: 1..8 capabilities required")
    for cap in caps:
        if not CAPABILITY_RE.match(cap) or len(cap) > 64:
            raise ValueError(f"{plugin_id}: bad capability id {cap!r}")
        if not cap.startswith(plugin_id + "."):
            raise ValueError(f"{plugin_id}: capability {cap!r} must start with the plugin id")
        if cap.split(".")[0] in RESERVED:
            raise ValueError(f"{plugin_id}: capability {cap!r} is in a reserved namespace")


def manifest(spec: dict, data: bytes) -> dict:
    plugin_id = spec["plugin_id"]
    return {
        "plugin_id": plugin_id,
        "api_version": 1,
        "publisher": PUBLISHER,
        "semver": "1.0.0",
        "targets": [TARGET],
        "binaries": [{
            "target": TARGET,
            "url": RELEASE_URL % plugin_id,
            "sha256": sha256_of(data),
            "size": len(data),
        }],
        "license": "MIT",
        "permissions": list(spec["permissions"]),
        "dependencies": [],
        "conflicts": [],
        "entrypoint": "bin/%s.py" % plugin_id,
        "build_source": BUILD_SOURCE,
        "support_policy": SUPPORT_POLICY,
        "signature": None,
        "runtime": "python3_script",
        "capabilities": list(spec["capabilities"]),
    }


def main() -> int:
    plugins, skipped = [], []
    for spec in PLUGINS:
        check_spec(spec)
        payload = PAYLOAD_DIR / (spec["plugin_id"] + ".py")
        if not payload.is_file():
            skipped.append(spec["plugin_id"])
            print(f"skip {spec['plugin_id']}: {payload} missing (re-run when it exists)")
            continue
        data = payload.read_bytes()
        plugins.append(manifest(spec, data))
        print(f"{spec['plugin_id']}: size={len(data)} sha256={sha256_of(data)}")

    if not plugins:
        print("error: no C4 payloads found; nothing written", file=sys.stderr)
        return 1
    catalog = {"version": 1, "repository": REPOSITORY, "plugins": plugins}
    CATALOG.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(plugins)}/{len(PLUGINS)} plugins to {CATALOG}")
    if skipped:
        print(f"missing payloads: {', '.join(skipped)}; re-run after they are written")
    print(f"catalog sha256: {sha256_of(CATALOG.read_bytes())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
