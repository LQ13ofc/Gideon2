#!/usr/bin/env python3
"""Unit-style tests for gideon-install and gideon-launch (B4.2) on a tiny synthetic package.

Run: python3 scripts/test_package_install.py   (stdlib unittest; no network; no real HOME).
Every test gets its own /tmp/gi-XXXXXX base; the fixture package is built here, never the 1.8 GiB one.
"""
import hashlib
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "scripts" / "package_tools"
INSTALL = TOOLS / "gideon-install"
LAUNCH = TOOLS / "gideon-launch"
VERIFY = TOOLS / "gideon-verify"
COMMIT = "a" * 40
ID1 = "0.1.0-aaaaaaaa"
ID2 = "0.2.0-aaaaaaaa"
ID3 = "0.3.0-aaaaaaaa"
STUB_CORE = b"#!/bin/sh\nprintf '%s\\n' \"$0\" \"$@\" > \"${GIDEON_STUB_MARK:?}\"\n"
ENV_KEYS = ("GIDEON_INSTALL_FAIL_AT", "GIDEON_INSTALL_FORCE_COPY", "GIDEON_STUB_MARK")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(root):
    """Every entry under root: type, mode or link target, and file bytes (byte-exact compare)."""
    state = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            st = os.lstat(full)
            if stat.S_ISLNK(st.st_mode):
                state[rel] = ("link", os.readlink(full))
            elif stat.S_ISDIR(st.st_mode):
                state[rel] = ("dir", stat.S_IMODE(st.st_mode))
            elif stat.S_ISREG(st.st_mode):
                state[rel] = ("file", stat.S_IMODE(st.st_mode), Path(full).read_bytes())
            else:
                state[rel] = ("other", stat.S_IFMT(st.st_mode))
    return state


def parse_stdout(stdout):
    return json.loads(stdout) if stdout.strip() else None


class PackageTestCase(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="gi-", dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.root = self.base / "r"
        self.counter = 0

    def make_pkg(self, version, payload=b"payload\n", commit=COMMIT):
        """Fixture package: PACKAGE.json, bin/gideon-verify (copied), bin/gideon-core stub, one payload file."""
        self.counter += 1
        pkg = self.base / f"src{self.counter}"
        files = {
            "bin/gideon-verify": (VERIFY.read_bytes(), 0o755),
            "bin/gideon-core": (STUB_CORE, 0o755),
            "data/payload.txt": (payload, 0o644),
        }
        entries = []
        for rel in sorted(files):
            data, mode = files[rel]
            path = pkg / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            os.chmod(path, mode)
            entries.append({"type": "file", "path": rel, "size": len(data), "sha256": sha256(data),
                            "mode": f"{mode:04o}"})
        manifest = {"format": 1, "name": f"gideon-base-{version}", "version": version,
                    "target": "linux_x86_64", "commit": commit, "dirty": False, "files": entries}
        (pkg / "PACKAGE.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return pkg

    def clean_env(self, extra):
        env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
        env.update(extra or {})
        return env

    def run_tool(self, *args, env=None, root=None):
        proc = subprocess.run(
            [sys.executable, "-I", "-B", str(INSTALL), "--install-root", str(root or self.root), *args],
            capture_output=True, text=True, timeout=600, env=self.clean_env(env))
        return proc.returncode, parse_stdout(proc.stdout), proc.stderr

    def ok(self, *args, env=None, root=None):
        rc, obj, err = self.run_tool(*args, env=env, root=root)
        self.assertEqual(rc, 0, f"{args}: rc={rc} {obj} {err}")
        return obj

    def refused(self, rc_expected, code, *args, env=None, root=None):
        rc, obj, err = self.run_tool(*args, env=env, root=root)
        self.assertEqual(rc, rc_expected, f"{args}: {obj} {err}")
        self.assertIsNotNone(obj)
        self.assertFalse(obj["ok"])
        self.assertEqual(obj["error"], code)
        return obj

    def ledger(self, root=None):
        return json.loads((root or self.root / "install.json").read_text())

    def link_target(self, name):
        path = self.root / name
        return os.readlink(path) if os.path.islink(path) else None


class InstallLifecycleTests(PackageTestCase):
    def test_install_creates_layout_and_consumes_source(self):
        src = self.make_pkg("0.1.0")
        obj = self.ok("install", str(src))
        self.assertEqual(obj["current"], ID1)
        self.assertEqual(obj["source"], "moved")
        self.assertFalse(src.exists(), "same-filesystem install consumes the source directory")
        self.assertEqual(stat.S_IMODE(os.lstat(self.root).st_mode), 0o700)
        self.assertEqual(self.link_target("current"), f"versions/{ID1}")
        self.assertFalse(os.path.lexists(self.root / "previous"))
        led = self.ledger()
        self.assertEqual((led["version"], led["revision"], led["current"], led["previous"]), (1, 1, ID1, None))
        self.assertEqual(stat.S_IMODE(os.lstat(self.root / "install.json").st_mode), 0o600)
        self.assertTrue((self.root / "versions" / ID1 / "bin" / "gideon-verify").is_file())

    def test_install_twice_refused(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.refused(5, "already_installed", "install", str(self.make_pkg("0.2.0")))

    def test_update_keeps_previous(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        obj = self.ok("update", str(self.make_pkg("0.2.0")))
        self.assertEqual((obj["current"], obj["previous"], obj["revision"]), (ID2, ID1, 2))
        self.assertEqual(self.link_target("current"), f"versions/{ID2}")
        self.assertEqual(self.link_target("previous"), f"versions/{ID1}")
        self.assertTrue((self.root / "versions" / ID1).is_dir())

    def test_rollback_swaps_current_and_previous(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.ok("update", str(self.make_pkg("0.2.0")))
        obj = self.ok("rollback")
        self.assertEqual((obj["current"], obj["previous"], obj["revision"]), (ID1, ID2, 3))
        self.assertEqual(self.link_target("current"), f"versions/{ID1}")
        self.assertEqual(self.link_target("previous"), f"versions/{ID2}")
        self.ok("rollback")
        self.assertEqual(self.ledger()["current"], ID2)

    def test_rollback_without_previous_refused(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        before = snapshot(self.root)
        self.refused(5, "no_previous", "rollback")
        self.assertEqual(snapshot(self.root), before)

    def test_update_with_tampered_package_leaves_everything_intact(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.ok("update", str(self.make_pkg("0.2.0")))
        before = snapshot(self.root)
        src = self.make_pkg("0.3.0", payload=b"payload\n")
        data = (src / "data/payload.txt").read_bytes()
        (src / "data/payload.txt").write_bytes(b"X" * len(data))  # same size, wrong bytes
        self.refused(4, "verify_failed", "update", str(src))
        self.assertEqual(snapshot(self.root), before)
        self.assertTrue(src.is_dir(), "a refused package is not consumed")

    def test_same_id_update_refused(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        before = snapshot(self.root)
        self.refused(5, "already_installed", "update", str(self.make_pkg("0.1.0", payload=b"other\n")))
        self.assertEqual(snapshot(self.root), before)

    def test_third_version_drops_oldest(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.ok("update", str(self.make_pkg("0.2.0")))
        obj = self.ok("update", str(self.make_pkg("0.3.0")))
        self.assertEqual(obj["dropped"], ID1)
        self.assertEqual(sorted(e["id"] for e in self.ledger()["versions"]), sorted([ID2, ID3]))
        self.assertEqual((self.ledger()["current"], self.ledger()["previous"]), (ID3, ID2))
        self.assertFalse((self.root / "versions" / ID1).exists())

    def test_copy_path_keeps_source_and_modes(self):
        src = self.make_pkg("0.1.0")
        obj = self.ok("install", str(src), env={"GIDEON_INSTALL_FORCE_COPY": "1"})
        self.assertEqual(obj["source"], "copied")
        self.assertTrue(src.is_dir())
        mode = stat.S_IMODE(os.lstat(self.root / "versions" / ID1 / "bin" / "gideon-core").st_mode)
        self.assertEqual(mode, 0o755)


class FailureInjectionTests(PackageTestCase):
    def _fail_at(self, point, leftovers, orphans_after):
        self.ok("install", str(self.make_pkg("0.1.0")))
        ledger_before = (self.root / "install.json").read_bytes()
        rc, obj, err = self.run_tool("update", str(self.make_pkg("0.2.0")),
                                     env={"GIDEON_INSTALL_FAIL_AT": point})
        self.assertEqual(rc, 99, err)
        self.assertEqual(obj["error"], "injected_failure")
        for rel in leftovers:
            self.assertTrue(os.path.lexists(self.root / rel), f"expected leftover {rel} after {point}")
        self.assertEqual((self.root / "install.json").read_bytes(), ledger_before)
        self.assertEqual(self.link_target("current"), f"versions/{ID1}")
        self.assertFalse(os.path.lexists(self.root / "previous"))
        listing = self.ok("list")
        self.assertEqual((listing["current"], listing["revision"]), (ID1, 1))
        self.assertEqual(listing["orphans"], orphans_after)
        # next mutating command recovers: own leftovers gone, new update works
        self.ok("update", str(self.make_pkg("0.3.0")))
        for rel in leftovers:
            self.assertFalse(os.path.lexists(self.root / rel), f"leftover {rel} not cleaned")
        self.assertEqual(self.ledger()["current"], ID3)
        self.assertEqual(self.ledger()["previous"], ID1)

    def test_fail_at_stage_cleans_stage_dir(self):
        self._fail_at("stage", [f"versions/.stage-{ID2}"], [])

    def test_fail_at_ledger_cleans_temp_ledger(self):
        self._fail_at("ledger", [".install.json.tmp"], [ID2])

    def test_fail_at_switch_cleans_temp_links(self):
        self._fail_at("switch", [".current.tmp", ".previous.tmp", ".install.json.tmp"], [ID2])

    def test_orphan_with_same_id_refused(self):
        self._fail_at_ledger_then_same_id_update()

    def _fail_at_ledger_then_same_id_update(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.run_tool("update", str(self.make_pkg("0.2.0")), env={"GIDEON_INSTALL_FAIL_AT": "ledger"})
        self.refused(5, "orphan_conflict", "update", str(self.make_pkg("0.2.0")))
        self.assertTrue((self.root / "versions" / ID2).is_dir(), "orphan is left alone")

    def test_foreign_orphan_untouched(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        foreign = self.root / "versions" / "foreign"
        foreign.mkdir()
        (foreign / "keep.txt").write_text("mine\n")
        self.assertEqual(self.ok("list")["orphans"], ["foreign"])
        self.ok("update", str(self.make_pkg("0.2.0")))
        self.assertEqual((foreign / "keep.txt").read_text(), "mine\n")
        self.assertEqual(self.ok("list")["orphans"], ["foreign"])


class ActiveProfileTests(PackageTestCase):
    def test_active_core_socket_refuses_update(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.ok("profile", "create", "p")
        core = self.root / "profiles" / "p" / "core"
        core.mkdir(mode=0o700, exist_ok=True)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(listener.close)
        listener.bind(str(core / "core.sock"))
        listener.listen(1)
        before = snapshot(self.root)
        src = self.make_pkg("0.2.0")
        obj = self.refused(3, "profile_active", "update", str(src))
        self.assertEqual(obj["profile"], "p")
        self.assertEqual(snapshot(self.root), before)
        self.assertTrue(src.is_dir())

    def test_stale_socket_is_ignored(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.ok("profile", "create", "p")
        core = self.root / "profiles" / "p" / "core"
        core.mkdir(mode=0o700, exist_ok=True)
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(core / "core.sock"))
        stale.close()  # file stays behind, nothing listens
        self.assertTrue((core / "core.sock").exists())
        self.ok("update", str(self.make_pkg("0.2.0")))
        self.assertEqual(self.ledger()["current"], ID2)


class RootGuardTests(PackageTestCase):
    def test_root_mode_0755_refused_without_mutation(self):
        self.root = self.base / "r755"
        self.root.mkdir(mode=0o755)
        os.chmod(self.root, 0o755)
        self.refused(5, "root_invalid", "install", str(self.make_pkg("0.1.0")), root=self.root)
        self.assertEqual(stat.S_IMODE(os.lstat(self.root).st_mode), 0o755)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_symlink_root_refused_without_mutation(self):
        real = self.base / "real"
        real.mkdir(mode=0o700)
        link = self.base / "rl"
        os.symlink(real, link)
        before = snapshot(real)
        self.refused(5, "root_invalid", "list", root=link)
        self.assertEqual(snapshot(real), before)
        self.assertTrue(os.path.islink(link))

    def test_fresh_root_created_0700_by_list(self):
        obj = self.ok("list")
        self.assertEqual((obj["revision"], obj["current"], obj["previous"], obj["versions"]), (0, None, None, []))
        self.assertEqual((obj["orphans"], obj["profiles"]), ([], []))
        self.assertEqual(stat.S_IMODE(os.lstat(self.root).st_mode), 0o700)

    def test_ledger_corrupt_refused_without_mutation(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        (self.root / "install.json").write_text("{not json")
        before = snapshot(self.root)
        self.refused(5, "ledger_invalid", "list")
        self.refused(5, "ledger_invalid", "update", str(self.make_pkg("0.2.0")))
        self.assertEqual(snapshot(self.root), before)

    def test_ledger_extra_key_refused(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        led = self.ledger()
        led["extra"] = 1
        (self.root / "install.json").write_text(json.dumps(led))
        before = snapshot(self.root)
        self.refused(5, "ledger_invalid", "rollback")
        self.assertEqual(snapshot(self.root), before)

    def test_ledger_wrong_mode_refused(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        os.chmod(self.root / "install.json", 0o644)
        self.refused(5, "ledger_invalid", "list")

    def test_symlink_mismatch_refused_without_mutation(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.ok("update", str(self.make_pkg("0.2.0")))
        os.unlink(self.root / "current")
        os.symlink(f"versions/{ID1}", self.root / "current")
        before = snapshot(self.root)
        self.refused(5, "layout_invalid", "list")
        self.refused(5, "layout_invalid", "rollback")
        self.assertEqual(snapshot(self.root), before)

    def test_dangling_link_refused(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        os.unlink(self.root / "current")
        os.symlink("versions/9.9.9-deadbeef", self.root / "current")
        self.refused(5, "layout_invalid", "list")


class ProfileTests(PackageTestCase):
    def test_profile_name_validation(self):
        self.ok("list")
        for bad in ("Bad", "a" * 33, "../x", "a/b", "", "sp ace"):
            self.refused(2, "invalid_profile_name", "profile", "create", bad)
        self.assertEqual(self.ok("profile", "create", "alice")["created"], True)
        self.assertEqual(self.ok("profile", "create", "a_b-1")["created"], True)
        self.assertEqual(self.ok("profile", "create", "alice")["created"], False)
        self.assertEqual(stat.S_IMODE(os.lstat(self.root / "profiles" / "alice").st_mode), 0o700)
        self.assertEqual(self.ok("profile", "list")["profiles"], ["a_b-1", "alice"])


class LaunchTests(PackageTestCase):
    def run_launch(self, *args, env=None, root=None):
        proc = subprocess.run(
            [sys.executable, "-I", "-B", str(LAUNCH), "--install-root", str(root or self.root), *args],
            capture_output=True, text=True, timeout=600, env=self.clean_env(env))
        return proc.returncode, proc.stderr

    def test_launch_execs_stub_core_with_right_argv(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        mark = self.base / "mark.txt"
        rc, err = self.run_launch("alice", "--flag", "x y", env={"GIDEON_STUB_MARK": str(mark)})
        self.assertEqual(rc, 0, err)
        lines = mark.read_text().splitlines()
        self.assertEqual(lines, [str(self.root / "current" / "bin" / "gideon-core"),
                                 str(self.root / "profiles" / "alice"), "--flag", "x y"])
        self.assertEqual(stat.S_IMODE(os.lstat(self.root / "profiles" / "alice").st_mode), 0o700)

    def test_launch_refuses_symlink_mismatch_without_exec(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        os.unlink(self.root / "current")
        os.symlink("versions/9.9.9-deadbeef", self.root / "current")
        mark = self.base / "mark.txt"
        rc, err = self.run_launch("alice", env={"GIDEON_STUB_MARK": str(mark)})
        self.assertNotEqual(rc, 0)
        self.assertIn("layout_invalid", err)
        self.assertFalse(mark.exists())

    def test_launch_refuses_ledger_corrupt_without_exec(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        (self.root / "install.json").write_text("garbage")
        mark = self.base / "mark.txt"
        rc, err = self.run_launch("alice", env={"GIDEON_STUB_MARK": str(mark)})
        self.assertEqual(rc, 5, err)
        self.assertFalse(mark.exists())

    def test_launch_refuses_tampered_current_without_exec(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        (self.root / "versions" / ID1 / "data" / "payload.txt").write_bytes(b"X" * 8)
        mark = self.base / "mark.txt"
        rc, err = self.run_launch("alice", env={"GIDEON_STUB_MARK": str(mark)})
        self.assertEqual(rc, 4, err)
        self.assertFalse(mark.exists())

    def test_launch_refuses_when_not_installed(self):
        mark = self.base / "mark.txt"
        rc, err = self.run_launch("alice", env={"GIDEON_STUB_MARK": str(mark)})
        self.assertEqual(rc, 5, err)
        self.assertFalse(mark.exists())

    def test_launch_rejects_bad_profile_name(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        mark = self.base / "mark.txt"
        rc, err = self.run_launch("Alice", env={"GIDEON_STUB_MARK": str(mark)})
        self.assertEqual(rc, 2, err)
        self.assertFalse(mark.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
