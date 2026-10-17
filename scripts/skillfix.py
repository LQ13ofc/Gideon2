#!/usr/bin/env python3
"""Synthetic S4/D1 skill fixtures: loader and independent REFERENCE validator.

TEST ONLY. Nothing here is shipped. Stdlib only. Reads tests/fixtures/skills/ and nothing else.

The Core validator reports rejections as `skill_invalid:<reason>`. This module implements the
D1 rules a second time, independently, so tests can cross-check the Core. Reasons are the
names in REASON_MAP (fixture file stem -> reason). `malformed` is an extra reference-only code
for structural/type/limit errors that are not one of the listed negative cases.

Check order (first failure wins; every negative fixture trips exactly one rule):
   1 oversize            manifest > 16 KiB, or one step's args > 2 KiB
   2 malformed           required keys or root/steps/deps/args types wrong
   3 grant_field         a step key containing "grant" or "permission"
   4 unknown_key         unknown key at top level, publisher, input/output spec, step, undo, cond, attestation
   5 schema_version      schema_version != 1
   6 min_runtime         min_runtime > runtime 0.1.0
   7 bad_id              skill id, publisher id or step id fails its D1 pattern
   8 too_many_steps     more than 16 steps or 8 dependency capabilities
   9 duplicate_step_id   two steps with the same id
  10 reserved_capability a call or dependency in base., core., system., safety.
  11 malformed           call or dependency not capability_id / tool:<name> / skill:<id>
  12 out_of_scope        a step call not listed in dependency_capabilities
  13 future_ref          when/unless/args refs must name an EARLIER step; verify may name its own step
  14 exfiltration        args key naming a secret, or args string that looks like path, URL or shell
  15 cycle / depth       skill: calls followed through the installed catalog; nesting limit 2
  16 malformed           remaining length, range and type limits

Cross-skill checks (15) need installed skills: the default catalog is every fixture in valid/,
invalid/ and catalog/, keyed by manifest id. A missing catalog entry is not an error (D1: a
missing dependency blocks execution, it does not invalidate the manifest).
"""
import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "skills"
GROUPS = ("valid", "invalid", "catalog")
RUNTIME = (0, 1, 0)
MAX_BYTES = 16 * 1024
MAX_ARGS_BYTES = 2 * 1024
MAX_STEPS = 16
MAX_DEPS = 8
MAX_NEST = 2
CORE_PREFIX = "skill_invalid:"

# Fixture stem (invalid/ file name, or the generated "oversize") -> expected reference reason.
REASON_MAP = {
    "schema_version": "schema_version",
    "min_runtime_future": "min_runtime",
    "unknown_key": "unknown_key",
    "out_of_scope_call": "out_of_scope",
    "duplicate_step_id": "duplicate_step_id",
    "future_ref": "future_ref",
    "self_cycle": "cycle",
    "cycle_a": "cycle",
    "cycle_b": "cycle",
    "depth_3": "depth",
    "exfil_path": "exfiltration",
    "exfil_url": "exfiltration",
    "exfil_shell": "exfiltration",
    "exfil_secret_key": "exfiltration",
    "grant_field": "grant_field",
    "oversize": "oversize",
    "too_many_steps": "too_many_steps",
    "reserved_capability": "reserved_capability",
    "bad_id": "bad_id",
}
MALFORMED = "malformed"
REASONS = frozenset(REASON_MAP.values()) | {MALFORMED}
OVERSIZE = "oversize"

ID_RE = re.compile(r"[a-z][a-z0-9_]{2,40}")
PUB_ID_RE = re.compile(r"[a-z][a-z0-9_-]{2,40}")
STEP_ID_RE = re.compile(r"[a-z][a-z0-9_]{0,23}")
CAP_RE = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*")
TOOL_RE = re.compile(r"[a-z][a-z0-9_]{0,63}")
SEMVER_RE = re.compile(r"(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,5})")
TEMPLATE_RE = re.compile(r"\$\{([^}]*)\}")
RESERVED = ("base.", "core.", "system.", "safety.")
SECRET_WORDS = ("key", "token", "secret", "password")
GRANT_WORDS = ("grant", "permission")
TOP_KEYS = {
    "schema_version", "id", "name", "version", "publisher", "description", "license",
    "min_runtime", "triggers", "inputs", "outputs", "dependency_capabilities",
    "permissions_required", "prerequisites", "steps", "attestations", "readme",
}
REQUIRED_KEYS = TOP_KEYS - {"readme"}
STEP_KEYS = {
    "id", "call", "args", "when", "unless", "retries", "timeout_ms", "idempotent",
    "verify", "undo", "save",
}
COND_KEYS = {"ref", "op", "value"}
COND_OPS = {"eq", "ne", "exists", "gt", "lt"}
SPEC_TYPES = {"string", "int", "bool"}


def core_code(reason):
    """Core-side rejection code for a reference reason."""
    return CORE_PREFIX + reason


# ---------------------------------------------------------------- helpers

def _full(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _text(value, limit):
    return isinstance(value, str) and len(value) <= limit


def _dump(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8")


def _compact(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _semver(value):
    if not isinstance(value, str):
        return None
    match = SEMVER_RE.fullmatch(value)
    return tuple(int(part) for part in match.groups()) if match else None


def _call_form_ok(call):
    if not isinstance(call, str):
        return False
    if call.startswith("tool:"):
        return _full(TOOL_RE, call[5:])
    if call.startswith("skill:"):
        return _full(ID_RE, call[6:])
    return _full(CAP_RE, call)


def _has_word(text, words):
    return isinstance(text, str) and any(word in text.lower() for word in words)


def _depth(obj):
    if isinstance(obj, dict):
        return 1 + max((_depth(v) for v in obj.values()), default=0)
    if isinstance(obj, list):
        return 1 + max((_depth(v) for v in obj), default=0)
    return 0


def _all_keys(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield key
            yield from _all_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _all_keys(item)


def _all_strings(obj):
    if isinstance(obj, dict):
        for value in obj.values():
            yield from _all_strings(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _all_strings(item)
    elif isinstance(obj, str):
        yield obj


def _looks_exfil(text):
    return (text.startswith(("/", "~")) or ".." in text or "://" in text
            or any(ch in text for ch in ";|`") or "$(" in text)


def _unknown_keys(m):
    if set(m) - TOP_KEYS:
        return True
    pub = m.get("publisher")
    if isinstance(pub, dict) and set(pub) - {"id", "name"}:
        return True
    for field, allowed in (("inputs", {"type", "required", "default", "max", "min"}),
                           ("outputs", {"type"})):
        specs = m.get(field)
        if isinstance(specs, dict):
            for spec in specs.values():
                if isinstance(spec, dict) and set(spec) - allowed:
                    return True
    atts = m.get("attestations")
    if isinstance(atts, list):
        for att in atts:
            if isinstance(att, dict) and set(att) - {"kind", "text"}:
                return True
    steps = m.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            if set(step) - STEP_KEYS:
                return True
            undo = step.get("undo")
            if isinstance(undo, dict) and set(undo) - {"call", "args"}:
                return True
            for key in ("when", "unless", "verify"):
                cond = step.get(key)
                if isinstance(cond, dict) and set(cond) - COND_KEYS:
                    return True
    return False


def _ref_problem(ref, index_of_step, index, allow_self):
    if not isinstance(ref, str):
        return MALFORMED
    if ref.startswith("input.") and len(ref.split(".")) == 2:
        return None
    parts = ref.split(".")
    if len(parts) != 3 or parts[0] != "steps":
        return MALFORMED
    target = index.get(parts[1])
    if target is None or target > index_of_step or (target == index_of_step and not allow_self):
        return "future_ref"
    return None


def _skill_targets(node):
    steps = node.get("steps")
    if not isinstance(steps, list):
        return []
    return [s["call"][6:] for s in steps
            if isinstance(s, dict) and isinstance(s.get("call"), str)
            and s["call"].startswith("skill:")]


def _nesting(root_id, node, catalog, path, hops):
    """Walks skill: calls. Returns 'cycle', 'depth' or None."""
    for target in _skill_targets(node):
        if target == root_id or target in path:
            return "cycle"
        child = catalog.get(target)
        if not isinstance(child, dict):
            continue  # missing dependency: blocks the run, does not invalidate the manifest
        if hops + 1 > MAX_NEST:
            return "depth"
        found = _nesting(root_id, child, catalog, path + [target], hops + 1)
        if found:
            return found
    return None


def _limits_ok(m):
    if len(m["steps"]) < 1:
        return False
    if not (isinstance(m["name"], str) and 1 <= len(m["name"]) <= 64):
        return False
    if not (_text(m["description"], 512) and _text(m["license"], 32)):
        return False
    if _semver(m["version"]) is None:
        return False
    pub = m["publisher"]
    if not (isinstance(pub, dict) and _text(pub.get("name"), 64)):
        return False
    triggers = m["triggers"]
    if not (isinstance(triggers, list) and len(triggers) <= 5
            and all(_text(t, 64) for t in triggers)):
        return False
    for field, cap in (("inputs", 8), ("outputs", 8)):
        specs = m[field]
        if not (isinstance(specs, dict) and len(specs) <= cap):
            return False
        for spec in specs.values():
            if not (isinstance(spec, dict) and spec.get("type") in SPEC_TYPES):
                return False
            if "required" in spec and not isinstance(spec["required"], bool):
                return False
            for bound in ("max", "min"):
                if bound in spec and not (type(spec[bound]) is int):
                    return False
    if len(m["dependency_capabilities"]) > MAX_DEPS:
        return False
    perms = m["permissions_required"]
    if not (isinstance(perms, list) and len(perms) <= 8 and all(_text(p, 64) for p in perms)):
        return False
    prereqs = m["prerequisites"]
    if not (isinstance(prereqs, list) and len(prereqs) <= 4 and all(_text(p, 128) for p in prereqs)):
        return False
    atts = m["attestations"]
    if not (isinstance(atts, list) and len(atts) <= 4):
        return False
    for att in atts:
        if not (isinstance(att, dict) and _text(att.get("kind"), 32) and _text(att.get("text"), 128)):
            return False
    if "readme" in m and not _text(m["readme"], 2048):
        return False
    for step in m["steps"]:
        if "retries" in step and not (type(step["retries"]) is int and 0 <= step["retries"] <= 2):
            return False
        if "timeout_ms" in step and not (type(step["timeout_ms"]) is int
                                         and 1 <= step["timeout_ms"] <= 10000):
            return False
        if "idempotent" in step and not isinstance(step["idempotent"], bool):
            return False
        save = step.get("save")
        if save is not None and not (isinstance(save, dict)
                                     and all(isinstance(k, str) and isinstance(v, str)
                                             for k, v in save.items())):
            return False
        undo = step.get("undo")
        if undo is not None and not (isinstance(undo, dict) and _call_form_ok(undo.get("call"))
                                     and isinstance(undo.get("args"), dict)
                                     and _depth(undo["args"]) <= 3):
            return False
        for key in ("when", "unless", "verify"):
            cond = step.get(key)
            if cond is None:
                continue
            if not (isinstance(cond, dict) and cond.get("op") in COND_OPS
                    and isinstance(cond.get("ref"), str)):
                return False
            if "value" in cond and not isinstance(cond["value"], (str, int, bool)):
                return False
        if _depth(step["args"]) > 3:
            return False
    return True


# ---------------------------------------------------------------- reference validator

def reference_validate(manifest, catalog=None):
    """None when the manifest satisfies D1, else the reason (see REASON_MAP / MALFORMED).

    `catalog` maps installed skill id -> manifest for skill: nesting checks. Default: every
    fixture manifest (valid/, invalid/, catalog/), keyed by id.
    """
    if not isinstance(manifest, dict):
        return MALFORMED
    if len(_dump(manifest)) > MAX_BYTES:
        return OVERSIZE
    if not REQUIRED_KEYS <= set(manifest):
        return MALFORMED
    steps = manifest["steps"]
    deps = manifest["dependency_capabilities"]
    if not isinstance(steps, list) or not isinstance(deps, list):
        return MALFORMED
    for step in steps:
        if not (isinstance(step, dict) and isinstance(step.get("args"), dict)):
            return MALFORMED
        if len(_compact(step["args"])) > MAX_ARGS_BYTES:
            return OVERSIZE
    for step in steps:
        if any(_has_word(key, GRANT_WORDS) for key in step):
            return "grant_field"
    if _unknown_keys(manifest):
        return "unknown_key"
    schema = manifest["schema_version"]
    if not (type(schema) is int and schema == 1):
        return "schema_version"
    runtime = _semver(manifest["min_runtime"])
    if runtime is None:
        return MALFORMED
    if runtime > RUNTIME:
        return "min_runtime"
    pub = manifest["publisher"]
    if not isinstance(pub, dict):
        return MALFORMED
    if not _full(ID_RE, manifest["id"]) or not _full(PUB_ID_RE, pub.get("id")):
        return "bad_id"
    if not all(_full(STEP_ID_RE, step.get("id")) for step in steps):
        return "bad_id"
    if len(steps) > MAX_STEPS or len(deps) > MAX_DEPS:
        return "too_many_steps"
    ids = [step["id"] for step in steps]
    if len(set(ids)) != len(ids):
        return "duplicate_step_id"
    calls = [step.get("call") for step in steps]
    if any(isinstance(c, str) and c.startswith(RESERVED) for c in deps + calls):
        return "reserved_capability"
    if not all(_call_form_ok(c) for c in deps + calls):
        return MALFORMED
    if any(call not in deps for call in calls):
        return "out_of_scope"

    index = {sid: pos for pos, sid in enumerate(ids)}
    for pos, step in enumerate(steps):
        for key, allow_self in (("when", False), ("unless", False), ("verify", True)):
            cond = step.get(key)
            if cond is None:
                continue
            if not isinstance(cond, dict):
                return MALFORMED
            problem = _ref_problem(cond.get("ref"), pos, index, allow_self)
            if problem:
                return problem
        for text in _all_strings(step["args"]):
            for inner in TEMPLATE_RE.findall(text):
                problem = _ref_problem(inner, pos, index, False)
                if problem:
                    return problem

    for step in steps:
        for key in _all_keys(step["args"]):
            if _has_word(key, SECRET_WORDS):
                return "exfiltration"
        for text in _all_strings(step["args"]):
            if _looks_exfil(text):
                return "exfiltration"

    installed = _catalog() if catalog is None else catalog
    found = _nesting(manifest["id"], manifest, installed, [manifest["id"]], 0)
    if found:
        return found

    if not _limits_ok(manifest):
        return MALFORMED
    return None


# ---------------------------------------------------------------- loader

def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _stems(group):
    return sorted(path.stem for path in (ROOT / group).glob("*.json"))


def _oversize():
    """Generated, never stored. 16 steps with args just under 2 KiB each: the file is over 16 KiB,
    and every other rule holds."""
    return {
        "schema_version": 1,
        "id": "fixture_oversize",
        "name": "Fixture oversize",
        "version": "1.0.0",
        "publisher": {"id": "fixture_pub", "name": "Fixture publisher"},
        "description": "TEST FIXTURE ONLY. Negative: generated manifest over 16 KiB.",
        "license": "TEST-ONLY",
        "min_runtime": "0.1.0",
        "triggers": [],
        "inputs": {},
        "outputs": {},
        "dependency_capabilities": ["dummy_echo.echo"],
        "permissions_required": [],
        "prerequisites": [],
        "steps": [
            {"id": f"s{i}", "call": "dummy_echo.echo", "args": {"text": "x" * 1900}}
            for i in range(1, MAX_STEPS + 1)
        ],
        "attestations": [{"kind": "fixture", "text": "synthetic test only, never shipped"}],
    }


def load(name):
    """Load one fixture by 'group/stem', e.g. 'valid/branching' or 'invalid/cycle_a'.

    'invalid/oversize' is generated in memory (see _oversize), not read from disk.
    """
    group, sep, stem = name.partition("/")
    if not sep or group not in GROUPS or not stem:
        raise ValueError("bad fixture name: %r" % (name,))
    if name == "invalid/oversize":
        return _oversize()
    return _read_json(ROOT / group / (stem + ".json"))


def all_valid():
    """{stem: manifest} for every file in valid/."""
    return {stem: load("valid/" + stem) for stem in _stems("valid")}


def all_invalid():
    """{stem: manifest} for every file in invalid/, plus the generated oversize case."""
    found = {stem: load("invalid/" + stem) for stem in _stems("invalid")}
    found[OVERSIZE] = _oversize()
    return found


def all_catalog():
    """{stem: manifest} for the installed-skill helpers in catalog/."""
    return {stem: load("catalog/" + stem) for stem in _stems("catalog")}


@lru_cache(maxsize=1)
def _catalog():
    """Installed skills for nesting checks: every fixture manifest keyed by its id."""
    found = {}
    everything = list(all_valid().values()) + list(all_invalid().values()) + list(all_catalog().values())
    for manifest in everything:
        found.setdefault(manifest.get("id"), manifest)
    return found


if __name__ == "__main__":
    import sys

    failures = 0
    for stem, manifest in sorted(all_valid().items()):
        reason = reference_validate(manifest)
        print("valid/%s: %s" % (stem, "ok" if reason is None else reason))
        failures += reason is not None
    for stem, manifest in sorted(all_invalid().items()):
        reason = reference_validate(manifest)
        print("invalid/%s: %s (expected %s)" % (stem, reason, REASON_MAP[stem]))
        failures += reason != REASON_MAP[stem]
    sys.exit(1 if failures else 0)
