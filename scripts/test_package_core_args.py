#!/usr/bin/env python3
"""gideon-core argv construction (dry run only; no verify, configure or exec).

Run: python3 -I -B scripts/test_package_core_args.py   (stdlib unittest; no network; no real HOME).
Each test builds a tiny synthetic package under a fresh /tmp base; the 1.8 GiB package is never touched.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "scripts" / "package_tools" / "gideon-core"
STATE = "/var/tmp/gideon-state-fixture"


class CoreArgsTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="gc-", dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.pkg = self.base / "pkg"
        (self.pkg / "bin").mkdir(parents=True)
        shutil.copy2(CORE, self.pkg / "bin" / "gideon-core")
        self.py = self.pkg / "runtime/python/bin/python3.13"

    def add_runtime(self):
        self.py.parent.mkdir(parents=True)
        self.py.write_bytes(b"not really python; dry run never executes it\n")
        os.chmod(self.py, 0o755)

    def dry(self, *args):
        env = {k: v for k, v in os.environ.items() if k != "GIDEON_CORE_DRYRUN"}
        env["GIDEON_CORE_DRYRUN"] = "1"
        return subprocess.run(
            [str(self.pkg / "bin" / "gideon-core"), *args],
            capture_output=True, text=True, timeout=60, env=env)

    def argv(self, *args):
        proc = self.dry(*args)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)["argv"]

    def expected_base(self, extra=()):
        pkg = self.pkg.resolve()
        return [
            str(pkg / "bin/gideon-base"), "--root", f"{STATE}/core", "--home", str(pkg),
            "--commands-sandbox",
            "--base-pack", f"{STATE}/profile/pack.json",
            "--tts-virtual", str(pkg / "venvs/tts/bin/python"), f"{STATE}/profile/tts-manifest.json",
            "--wake-replay", str(pkg / "venvs/a1/bin/python"), f"{STATE}/profile/replay-manifest.json", "0",
            *extra,
        ]

    def test_plugin_flag_present_when_runtime_exists(self):
        self.add_runtime()
        argv = self.argv(STATE)
        self.assertEqual(argv, self.expected_base(["--plugin-python", str(self.py.resolve())]))

    def test_plugin_flag_absent_without_runtime(self):
        argv = self.argv(STATE)
        self.assertEqual(argv, self.expected_base())
        self.assertNotIn("--plugin-python", argv)

    def test_extra_args_kept_in_order_after_plugin_flag(self):
        self.add_runtime()
        extra = ["--flag", "x y", "--quote\"back\\slash", "--virtual-input"]
        argv = self.argv(STATE, *extra)
        self.assertEqual(argv, self.expected_base(["--plugin-python", str(self.py.resolve()), *extra]))

    def test_extra_args_kept_without_runtime(self):
        argv = self.argv(STATE, "--virtual-input")
        self.assertEqual(argv, self.expected_base(["--virtual-input"]))

    def test_duplicate_plugin_python_rejected(self):
        self.add_runtime()
        for dup in (["--plugin-python", "/usr/bin/python3"], ["--plugin-python=/usr/bin/python3"]):
            proc = self.dry(STATE, *dup)
            self.assertEqual(proc.returncode, 2, proc.stdout)
            self.assertIn("--plugin-python", proc.stderr)
            self.assertEqual(proc.stdout, "", "no argv printed for a rejected call")

    def test_duplicate_plugin_python_rejected_without_runtime(self):
        proc = self.dry(STATE, "--plugin-python", "/usr/bin/python3")
        self.assertEqual(proc.returncode, 2, proc.stderr)

    def test_relative_state_dir_rejected(self):
        proc = self.dry("relative/state")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("absolute STATE_DIR", proc.stderr)

    def test_missing_state_dir_is_usage_error(self):
        proc = self.dry()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage", proc.stderr)

    def test_dry_run_skips_verify_and_configure(self):
        # The fixture has no bin/gideon-verify or bin/gideon-configure: dry run must not reach them.
        self.assertFalse((self.pkg / "bin/gideon-verify").exists())
        self.add_runtime()
        self.argv(STATE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
