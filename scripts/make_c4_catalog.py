#!/usr/bin/env python3
"""Build the perception catalogs (C4 plugins, WP-12).

--real: tests/fixtures/hub-perception.json. Seven plugins, one payload: scripts/perception_worker.py
(real backends: xdg-desktop-portal, AT-SPI, PipeWire, v4l2, kscreen-doctor, KGlobalAccel). Every plugin
entry names the same payload, and the worker answers only the capabilities of the plugin_id it receives
in `hello` (its PLUGINS table must equal the capabilities below; scripts/test_perception_worker.py checks that).

Default (no flag, also --synthetic): tests/fixtures/hub-c4.json, the six synthetic C4 fixtures
(tests/fixtures/c4/<id>.py) that the C4 gates still use. They are test fixtures only, never a product backend.

Each entry is a manifest in the C0 schema plus one linux_x86_64 binary whose sha256 and size come from the
payload. Manifest rules are checked here (C0 capability regex, id prefix, reserved namespaces) so a bad
catalog is never written. Prints the catalog file's own sha256 (the value the Core pins). Stdlib only.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
TARGET = "linux_x86_64"
REPOSITORY = "https://github.com/LQ13ofc/Gideon2"
PUBLISHER = "Gideon local test fixture"
SUPPORT_POLICY = "Fixture de teste local; sem suporte de produto"
CAPABILITY_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
RESERVED = ("base", "core", "system", "safety", "llm", "screen", "computer", "audio",
            "mic", "camera", "display")  # mirror of src/plugins.rs RESERVED
MAX_CAPABILITIES = 8

REAL = {
    "catalog": FIXTURES / "hub-perception.json",
    "payload": ROOT / "scripts" / "perception_worker.py",
    "release_url": REPOSITORY + "/releases/download/wp12-v1/%s.py",
    "build_source": REPOSITORY + "/tree/wp12-v1",
    "plugins": [
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
         "capabilities": ["display_manipulate.status", "display_manipulate.act",
                          "display_manipulate.restore"]},
        {"plugin_id": "shortcut_global", "permissions": ["global_shortcut"],
         "capabilities": ["shortcut_global.status", "shortcut_global.bind", "shortcut_global.events"]},
    ],
}

SYNTHETIC = {
    "catalog": FIXTURES / "hub-c4.json",
    "payload_dir": FIXTURES / "c4",
    "release_url": REPOSITORY + "/releases/download/c4-v1/%s.py",
    "build_source": REPOSITORY + "/tree/c4-v1",
    "plugins": [
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
    ],
}


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


def manifest(spec: dict, mode: dict, data: bytes) -> dict:
    plugin_id = spec["plugin_id"]
    return {
        "plugin_id": plugin_id,
        "api_version": 1,
        "publisher": PUBLISHER,
        "semver": "1.0.0",
        "targets": [TARGET],
        "binaries": [{
            "target": TARGET,
            "url": mode["release_url"] % plugin_id,
            "sha256": sha256_of(data),
            "size": len(data),
        }],
        "license": "MIT",
        "permissions": list(spec["permissions"]),
        "dependencies": [],
        "conflicts": [],
        "entrypoint": "bin/%s.py" % plugin_id,
        "build_source": mode["build_source"],
        "support_policy": SUPPORT_POLICY,
        "signature": None,
        "runtime": "python3_script",
        "capabilities": list(spec["capabilities"]),
    }


def payload_for(mode: dict, plugin_id: str) -> Path:
    if "payload" in mode:
        return mode["payload"]
    return mode["payload_dir"] / (plugin_id + ".py")


PLUGINS = SYNTHETIC["plugins"]  # alias kept for verify_c4.py (the synthetic plugin list, docs/C4.md order)


def main(argv) -> int:
    mode = REAL if "--real" in argv else SYNTHETIC
    plugins, skipped = [], []
    for spec in mode["plugins"]:
        check_spec(spec)
        payload = payload_for(mode, spec["plugin_id"])
        if not payload.is_file():
            skipped.append(spec["plugin_id"])
            print(f"skip {spec['plugin_id']}: {payload} missing")
            continue
        data = payload.read_bytes()
        plugins.append(manifest(spec, mode, data))
        print(f"{spec['plugin_id']}: size={len(data)} sha256={sha256_of(data)}")
    if not plugins:
        print("error: no payloads found; nothing written", file=sys.stderr)
        return 1
    catalog = {"version": 1, "repository": REPOSITORY, "plugins": plugins}
    out = mode["catalog"]
    out.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(plugins)}/{len(mode['plugins'])} plugins to {out}")
    if skipped:
        print(f"missing payloads: {', '.join(skipped)}")
    print(f"catalog sha256: {sha256_of(out.read_bytes())}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
