#!/usr/bin/env python3
"""WP-6 unit tests (stdlib unittest; run as `python3 -I scripts/llm_test_plugin.py`).

Pure logic only: no Core, no server, no network. The real end-to-end run is scripts/llm_gate.py.
Covers: the production plugin's skill normalisation and request shaping, the Hub catalog hash, the
safe archive extraction and hash refusal of scripts/llm_local.py, and the benchmark summary.
"""
import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "scripts"))

import llm_bench  # noqa: E402
import llm_engine_plugin as plugin  # noqa: E402
import llm_local  # noqa: E402

CATALOG = BASE / "tests/fixtures/llm_hub_prod.json"


def manifest(steps, **extra):
    base = {"schema_version": 1, "id": "say_time_pt", "name": "Say time", "version": "1.0.0",
            "steps": steps, "dependency_capabilities": [], "ambiguities": []}
    base.update(extra)
    return base


class SkillNormalisation(unittest.TestCase):
    def test_read_only_steps_survive_and_dependencies_follow_them(self):
        steps = [{"id": "read_time", "call": "tool:get_time", "args": {}, "save": {}},
                 {"id": "read_date", "call": "tool:get_date", "args": {}, "save": {}}]
        out = plugin._normalize_skill(manifest(steps))
        self.assertEqual([s["id"] for s in out["steps"]], ["read_time", "read_date"])
        self.assertEqual(out["dependency_capabilities"], ["tool:get_date", "tool:get_time"])
        self.assertEqual(out["ambiguities"], [])

    def test_invented_tools_are_removed_and_reported_as_ambiguity(self):
        steps = [{"id": "read_time", "call": "tool:get_time", "args": {}, "save": {}},
                 {"id": "translate_time", "call": "tool:translate_time", "args": {}, "save": {}},
                 {"id": "say_time", "call": "tool:say_time", "args": {}, "save": {}}]
        out = plugin._normalize_skill(manifest(steps))
        self.assertEqual([s["call"] for s in out["steps"]], ["tool:get_time"])
        self.assertEqual(out["dependency_capabilities"], ["tool:get_time"])
        self.assertEqual(len(out["ambiguities"]), 1)
        self.assertIn("translate_time, say_time", out["ambiguities"][0])

    def test_state_changing_tools_are_never_kept(self):
        steps = [{"id": "open", "call": "tool:open_app", "args": {}, "save": {}},
                 {"id": "vol", "call": "tool:set_volume", "args": {"level": 5}, "save": {}}]
        with self.assertRaises(plugin._Fail) as raised:
            plugin._normalize_skill(manifest(steps))
        self.assertEqual(raised.exception.code, "model_output_invalid")

    def test_no_steps_or_non_list_steps_are_model_output_invalid(self):
        for bad in (manifest([]), manifest("tool:get_time")):
            with self.assertRaises(plugin._Fail):
                plugin._normalize_skill(bad)

    def test_long_non_string_step_labels_are_safe(self):
        out = plugin._normalize_skill(manifest(
            [{"id": "read", "call": "tool:get_time", "args": {}, "save": {}}, 7, {"id": "x" * 80, "call": "tool:bad"}]))
        self.assertEqual(out["ambiguities"][0].split(": ", 1)[1], "unnamed, " + "x" * 40)


class RequestShaping(unittest.TestCase):
    def test_plain_chat_keeps_the_provider_default_sampling(self):
        body = plugin._chat_body("m", [{"role": "user", "content": "oi"}], 16, False)
        self.assertNotIn("temperature", body)
        self.assertNotIn("response_format", body)
        self.assertTrue(body["stream"])

    def test_tool_turns_are_greedy(self):
        body = plugin._chat_body("m", [{"role": "user", "content": "hora"}], 32, True)
        self.assertEqual(body["temperature"], 0)
        self.assertIn("tools", body)
        self.assertNotIn("response_format", body)

    def test_skill_drafts_are_greedy_json(self):
        body = plugin._chat_body("m", [{"role": "user", "content": "x"}], 1024, False, json_mode=True)
        self.assertEqual(body["temperature"], 0)
        self.assertEqual(body["response_format"], {"type": "json_object"})

    def test_production_plugin_has_no_scripted_mode_left_in_the_chat_path(self):
        source = (BASE / "scripts/llm_engine_plugin.py").read_text(encoding="utf-8")
        self.assertNotIn("_script_turn(req_id)", source)
        self.assertNotIn("data.get(SCRIPT_KEY)", source)
        self.assertEqual(plugin.PLUGIN_VERSION, "1.3.0")


class CatalogAndManifest(unittest.TestCase):
    def test_hub_catalog_pins_the_production_plugin_bytes(self):
        data = (BASE / "scripts/llm_engine_plugin.py").read_bytes()
        entry = next(p for p in json.loads(CATALOG.read_text(encoding="utf-8"))["plugins"]
                     if p["plugin_id"] == "llm_engine")
        binary = entry["binaries"][0]
        self.assertEqual(binary["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(binary["size"], len(data))
        self.assertEqual(entry["semver"], plugin.PLUGIN_VERSION)

    def test_local_model_entry_matches_the_manifest_hash(self):
        manifest_data = json.loads((BASE / "scripts/llm_manifest.json").read_text(encoding="utf-8"))
        local = next(m for m in plugin.RECOMMENDED if m["id"] == "local-qwen2.5-1.5b-q4km")
        self.assertEqual(local["sha256"], manifest_data["model"]["sha256"])
        self.assertEqual(local["model"], manifest_data["model"]["file"])


class LocalManager(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="llm-test-"))
        os.chmod(self.tmp, 0o700)

    def tearDown(self):
        for path in sorted(self.tmp.rglob("*"), reverse=True):
            path.unlink() if path.is_file() or path.is_symlink() else path.rmdir()
        self.tmp.rmdir()

    def make_tar(self, name, payload, arcname=None):
        archive = self.tmp / name
        with tarfile.open(archive, "w:gz") as tar:
            info = tarfile.TarInfo(arcname or "llama-b1/llama-server")
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        return archive

    def test_extract_refuses_path_traversal_and_links(self):
        for arcname in ("../escape", "/abs/path"):
            archive = self.make_tar("t.tar.gz", b"x", arcname=arcname)
            with self.assertRaises(llm_local.Fail) as raised:
                llm_local.safe_extract(archive, self.tmp / "dest")
            self.assertEqual(raised.exception.code, "archive_path_unsafe")
            self.assertFalse((self.tmp / "escape").exists())

    def test_extract_accepts_a_plain_member(self):
        archive = self.make_tar("ok.tar.gz", b"binary")
        count = llm_local.safe_extract(archive, self.tmp / "dest")
        self.assertEqual(count, 1)
        self.assertEqual((self.tmp / "dest/llama-b1/llama-server").read_bytes(), b"binary")

    def make_link_tar(self, name, linkname):
        archive = self.tmp / name
        with tarfile.open(archive, "w:gz") as tar:
            payload = b"so"
            info = tarfile.TarInfo("llama-b1/libx.so.0")
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
            link = tarfile.TarInfo("llama-b1/libx.so")
            link.type = tarfile.SYMTYPE
            link.linkname = linkname
            tar.addfile(link)
        return archive

    def test_relative_symlink_inside_the_archive_extracts(self):
        archive = self.make_link_tar("links.tar.gz", "libx.so.0")
        llm_local.safe_extract(archive, self.tmp / "dest")
        self.assertEqual((self.tmp / "dest/llama-b1/libx.so").resolve().read_bytes(), b"so")

    def test_symlink_escaping_the_destination_is_refused(self):
        for linkname in ("../../outside", "/etc/passwd"):
            archive = self.make_link_tar("escape.tar.gz", linkname)
            with self.assertRaises(llm_local.Fail) as raised:
                llm_local.safe_extract(archive, self.tmp / "dest2")
            self.assertEqual(raised.exception.code, "archive_link_unsafe")

    def test_hash_mismatch_is_refused_and_missing_file_too(self):
        path = self.tmp / "model.gguf"
        path.write_bytes(b"not the model")
        with self.assertRaises(llm_local.Fail) as raised:
            llm_local.check_hash(path, "0" * 64)
        self.assertEqual(raised.exception.code, "sha256_mismatch")
        with self.assertRaises(llm_local.Fail) as missing:
            llm_local.check_hash(self.tmp / "absent.gguf", "0" * 64)
        self.assertEqual(missing.exception.code, "file_missing")


class BenchSummary(unittest.TestCase):
    def test_summary_takes_medians_from_server_timings(self):
        runs = [{"ttft_s": 0.1, "server_timings": {"predicted_per_second": 30.0, "prompt_per_second": 100.0,
                                                  "predicted_n": 10}},
                {"ttft_s": 0.3, "server_timings": {"predicted_per_second": 40.0, "prompt_per_second": 200.0,
                                                  "predicted_n": 20}},
                {"ttft_s": 0.2, "server_timings": {"predicted_per_second": 50.0, "prompt_per_second": 300.0,
                                                  "predicted_n": 30}}]
        report = llm_bench.summarize(runs)
        self.assertEqual(report["ttft_s_median"], 0.2)
        self.assertEqual(report["decode_tokens_per_s_median"], 40.0)
        self.assertEqual(report["generated_tokens_per_run"], [10, 20, 30])


if __name__ == "__main__":
    unittest.main(verbosity=1)
