#!/usr/bin/env python3
"""Regression tests for the B4 packaging hardening (F1-F14): crash windows, verifier pin, fail-closed
verify, FIFOs, pinned Core options, configure paths, build helpers, lock held by a running Core.

Run: python3 -I -B scripts/test_package_hardening.py   (stdlib unittest; no network; no real HOME).
Temp trees live under /tmp/gi-<hex>/ only; the packaged fixtures are tiny synthetic packages built here.
"""
import fcntl
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import time
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "scripts" / "package_tools"
INSTALL = TOOLS / "gideon-install"
LAUNCH = TOOLS / "gideon-launch"
VERIFY = TOOLS / "gideon-verify"
CORE = TOOLS / "gideon-core"
CONFIGURE = TOOLS / "gideon-configure"
APP = TOOLS / "gideon-app"
BUILD = REPO / "scripts" / "build_package.py"
COMMIT = "a" * 40
ID1 = "0.1.0-aaaaaaaa"
ID2 = "0.2.0-aaaaaaaa"
ID3 = "0.3.0-aaaaaaaa"
# Stub Core: records its argv; with GIDEON_STUB_HOLD it execs sleep so a running Core holds the lock.
STUB_CORE = (b"#!/bin/sh\nprintf '%s\\n' \"$0\" \"$@\" > \"${GIDEON_STUB_MARK:?}\"\n"
             b"if [ -n \"${GIDEON_STUB_HOLD:-}\" ]; then exec sleep \"$GIDEON_STUB_HOLD\"; fi\n")
ENV_KEYS = ("GIDEON_INSTALL_FAIL_AT", "GIDEON_INSTALL_FORCE_COPY", "GIDEON_STUB_MARK", "GIDEON_STUB_HOLD",
            "GIDEON_INSTALL_LOCK_TIMEOUT", "GIDEON_CORE_DRYRUN", "GIDEON_PINNED_VERIFIER_SHA256")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(root):
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


def load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def force_rmtree(path):
    if not os.path.lexists(path):
        return
    for dirpath, dirnames, _ in os.walk(path):
        for name in dirnames:
            try:
                os.chmod(os.path.join(dirpath, name), 0o700)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.base = Path("/tmp") / f"gi-{uuid.uuid4().hex[:12]}"
        self.base.mkdir(mode=0o700)
        self.addCleanup(force_rmtree, self.base)
        self.root = self.base / "r"
        self.counter = 0

    def make_pkg(self, version, payload=b"payload\n", commit=COMMIT, core=STUB_CORE, extra=None):
        """Synthetic package: PACKAGE.json, bin/gideon-verify (real), bin/gideon-core, data/payload.txt.
        extra: callable(pkg) -> list of additional manifest entries (already on disk)."""
        self.counter += 1
        pkg = self.base / f"src{self.counter}"
        files = {"bin/gideon-verify": (VERIFY.read_bytes(), 0o755),
                 "bin/gideon-core": (core, 0o755),
                 "data/payload.txt": (payload, 0o644)}
        entries = []
        for rel in sorted(files):
            data, mode = files[rel]
            path = pkg / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            os.chmod(path, mode)
            entries.append({"type": "file", "path": rel, "size": len(data), "sha256": sha256(data),
                            "mode": f"{mode:04o}"})
        if extra:
            entries.extend(extra(pkg))
        manifest = {"format": 1, "name": f"gideon-base-{version}", "version": version,
                    "target": "linux_x86_64", "commit": commit, "dirty": False, "files": entries}
        (pkg / "PACKAGE.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return pkg

    def clean_env(self, extra):
        env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
        env.update(extra or {})
        return env

    def run_tool(self, *args, env=None, root=None, timeout=120):
        proc = subprocess.run(
            [sys.executable, "-I", "-B", str(INSTALL), "--install-root", str(root or self.root), *args],
            capture_output=True, text=True, timeout=timeout, env=self.clean_env(env))
        return proc.returncode, (json.loads(proc.stdout) if proc.stdout.strip() else None), proc.stderr

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

    def kill_at(self, point, *args, root=None):
        rc, obj, err = self.run_tool(*args, env={"GIDEON_INSTALL_FAIL_AT": point}, root=root)
        self.assertEqual(rc, 99, f"{args} kill at {point}: {obj} {err}")
        self.assertEqual(obj["point"], point)

    def link_target(self, name):
        path = self.root / name
        return os.readlink(path) if os.path.islink(path) else None

    def ledger(self):
        return json.loads((self.root / "install.json").read_text())

    def run_verify(self, pkg, timeout=30):
        return subprocess.run([sys.executable, "-I", "-B", str(pkg / "bin" / "gideon-verify")],
                              capture_output=True, text=True, timeout=timeout)

    def run_launch(self, *args, env=None, root=None):
        proc = subprocess.run(
            [sys.executable, "-I", "-B", str(LAUNCH), "--install-root", str(root or self.root), *args],
            capture_output=True, text=True, timeout=120, env=self.clean_env(env))
        return proc.returncode, proc.stderr


# F2: crash windows between the link replaces and the ledger commit; repair; fresh-install recovery.
class CrashWindowTests(Base):
    def assert_state(self, current, previous, revision):
        listing = self.ok("list")
        self.assertEqual((listing["current"], listing["previous"], listing["revision"]),
                         (current, previous, revision))
        self.assertEqual(self.link_target("current"), f"versions/{current}")
        self.assertEqual(self.link_target("previous"), f"versions/{previous}" if previous else None)
        self.assertFalse(os.path.lexists(self.root / ".install.json.tmp"))
        return listing

    def test_fresh_install_killed_before_commit_needs_repair_then_rolls_forward(self):
        self.kill_at("before_commit", "install", str(self.make_pkg("0.1.0")))
        self.assertTrue(os.path.islink(self.root / "current"))
        self.assertFalse(os.path.lexists(self.root / "install.json"))
        self.refused(5, "needs_repair", "list")
        self.refused(5, "needs_repair", "update", str(self.make_pkg("0.2.0")))
        rep = self.ok("repair")
        self.assertEqual(rep["action"], "rolled_forward")
        self.assert_state(ID1, None, 1)

    def test_fresh_install_killed_at_switch_repair_completes_it(self):
        self.kill_at("switch", "install", str(self.make_pkg("0.1.0")))
        self.assertEqual(self.ok("list")["revision"], 0)
        self.assertEqual(self.ok("repair")["action"], "rolled_forward")
        self.assert_state(ID1, None, 1)
        self.refused(5, "already_installed", "install", str(self.make_pkg("0.2.0")))

    def test_fresh_install_killed_at_stage_repair_restores_nothing_installed(self):
        self.kill_at("stage", "install", str(self.make_pkg("0.1.0")))
        self.assertEqual(self.ok("list")["revision"], 0)
        self.assertEqual(self.ok("repair")["action"], "none")
        listing = self.ok("list")
        self.assertEqual((listing["current"], listing["revision"], listing["versions"]), (None, 0, []))
        self.assertFalse(os.path.lexists(self.root / "current"))
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.assert_state(ID1, None, 1)

    def test_fresh_install_without_ledger_rebuilt_by_repair(self):
        self.kill_at("before_commit", "install", str(self.make_pkg("0.1.0")))
        os.unlink(self.root / ".install.json.tmp")  # pending ledger lost: links alone are not a state
        self.refused(5, "layout_invalid", "list")
        rep = self.ok("repair")
        self.assertEqual(rep["action"], "rebuilt")
        self.assert_state(ID1, None, 1)

    def test_update_killed_between_links_repair_restores_old_state_exactly(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        ledger_before = (self.root / "install.json").read_bytes()
        self.kill_at("between_links", "update", str(self.make_pkg("0.2.0")))
        self.refused(5, "needs_repair", "list")
        rep = self.ok("repair")
        self.assertEqual(rep["action"], "discarded_pending")
        self.assertEqual((self.root / "install.json").read_bytes(), ledger_before)
        listing = self.assert_state(ID1, None, 1)
        self.assertEqual(listing["orphans"], [f".quarantine-{ID2}"])
        self.assertTrue((self.root / "versions" / f".quarantine-{ID2}" / "data" / "payload.txt").is_file())

    def test_update_killed_before_commit_repair_rolls_forward(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.kill_at("before_commit", "update", str(self.make_pkg("0.2.0")))
        self.refused(5, "needs_repair", "rollback")
        self.assertEqual(self.ok("repair")["action"], "rolled_forward")
        listing = self.assert_state(ID2, ID1, 2)
        self.assertEqual(listing["orphans"], [])

    def test_update_killed_at_switch_keeps_old_state_without_repair_need(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.kill_at("switch", "update", str(self.make_pkg("0.2.0")))
        self.assertEqual(self.ok("list")["revision"], 1)
        self.assertEqual(self.ok("repair")["action"], "discarded_pending")
        self.assert_state(ID1, None, 1)
        self.ok("update", str(self.make_pkg("0.2.0")))  # retry with the same version id succeeds
        self.assert_state(ID2, ID1, 2)

    def test_rollback_killed_between_links_repair_restores_current_state(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.ok("update", str(self.make_pkg("0.2.0")))
        self.kill_at("between_links", "rollback")
        self.refused(5, "needs_repair", "list")
        self.assertEqual(self.ok("repair")["action"], "discarded_pending")
        self.assert_state(ID2, ID1, 2)

    def test_rollback_killed_before_commit_repair_rolls_forward(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.ok("update", str(self.make_pkg("0.2.0")))
        self.kill_at("before_commit", "rollback")
        self.assertEqual(self.ok("repair")["action"], "rolled_forward")
        self.assert_state(ID1, ID2, 3)

    def test_repair_on_clean_state_is_a_noop(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        before = snapshot(self.root)
        rep = self.ok("repair")
        self.assertEqual(rep["action"], "none")
        self.assertEqual(snapshot(self.root), before)

    def test_repair_refused_while_core_active(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.ok("profile", "create", "p")
        core = self.root / "profiles" / "p" / "core"
        core.mkdir(mode=0o700, exist_ok=True)
        self.kill_at("between_links", "update", str(self.make_pkg("0.2.0")))
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(listener.close)
        listener.bind(str(core / "core.sock"))
        listener.listen(1)
        before = snapshot(self.root)
        self.refused(3, "profile_active", "repair")
        self.assertEqual(snapshot(self.root), before)

    def test_launch_prints_repair_hint_when_needs_repair(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.kill_at("between_links", "update", str(self.make_pkg("0.2.0")))
        mark = self.base / "mark.txt"
        rc, err = self.run_launch("alice", env={"GIDEON_STUB_MARK": str(mark)})
        self.assertEqual(rc, 5, err)
        self.assertIn("needs_repair", err)
        self.assertIn("repair", err)
        self.assertFalse(mark.exists())

    def test_refused_needs_repair_mutates_nothing(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.kill_at("between_links", "update", str(self.make_pkg("0.2.0")))
        before = snapshot(self.root)
        src = self.make_pkg("0.3.0")
        self.refused(5, "needs_repair", "update", str(src))
        self.assertEqual(snapshot(self.root), before)
        self.assertTrue(src.is_dir(), "a refused package is not consumed")

    def test_stage_leftover_is_quarantined_not_deleted(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.kill_at("stage", "update", str(self.make_pkg("0.2.0")))
        self.ok("update", str(self.make_pkg("0.3.0")))
        self.assertFalse(os.path.lexists(self.root / "versions" / f".stage-{ID2}"))
        quarantined = [n for n in os.listdir(self.root / "versions") if n.startswith(".quarantine-")]
        self.assertEqual(len(quarantined), 1)
        self.assertTrue((self.root / "versions" / quarantined[0] / "data" / "payload.txt").is_file())


# F1: the ledger pins sha256(bin/gideon-verify); launch and core refuse when the on-disk verifier differs.
class VerifierPinTests(Base):
    def test_ledger_records_verifier_pin(self):
        pkg = self.make_pkg("0.1.0")
        verifier = (pkg / "bin" / "gideon-verify").read_bytes()
        self.ok("install", str(pkg))
        self.assertEqual(self.ledger()["versions"][0]["verifier_sha256"], sha256(verifier))

    def test_launch_refuses_when_verifier_replaced_by_exit_zero(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        (self.root / "versions" / ID1 / "bin" / "gideon-verify").write_text("import sys\nsys.exit(0)\n")
        mark = self.base / "mark.txt"
        rc, err = self.run_launch("alice", env={"GIDEON_STUB_MARK": str(mark)})
        self.assertEqual(rc, 4, err)
        self.assertIn("verifier_modified", err)
        self.assertFalse(mark.exists())

    def test_update_and_list_refuse_replaced_verifier_without_mutation(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        (self.root / "versions" / ID1 / "bin" / "gideon-verify").write_text("import sys\nsys.exit(0)\n")
        before = snapshot(self.root)
        self.refused(4, "verifier_modified", "list")
        src = self.make_pkg("0.2.0")
        self.refused(4, "verifier_modified", "update", str(src))
        self.assertEqual(snapshot(self.root), before)

    def test_core_refuses_pinned_verifier_mismatch(self):
        pkg = self.make_pkg("0.1.0", core=CORE.read_bytes())
        self.ok("install", str(pkg))
        core = self.root / "current" / "bin" / "gideon-core"
        state = str(self.base / "state")

        def run(pin):
            return subprocess.run([str(core), state], capture_output=True, text=True, timeout=60,
                                  env={**self.clean_env({}), "GIDEON_PINNED_VERIFIER_SHA256": pin})
        wrong = run("0" * 64)
        self.assertEqual(wrong.returncode, 4, wrong.stderr)
        self.assertIn("verifier_modified", wrong.stderr)
        right = run(sha256((self.root / "current" / "bin" / "gideon-verify").read_bytes()))
        self.assertNotIn("verifier_modified", right.stderr)
        self.assertNotEqual(right.returncode, 4)

    def test_ledger_without_verifier_pin_is_rejected(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        led = self.ledger()
        del led["versions"][0]["verifier_sha256"]
        (self.root / "install.json").write_text(json.dumps(led))
        self.refused(5, "ledger_invalid", "list")


# F3/F4/F5 in gideon-verify: fail closed on unreadable or unexpected directories, hard link aliases, FIFOs.
class VerifyFailClosedTests(Base):
    def test_listed_empty_dir_is_accepted(self):
        def empty_dir(pkg):
            (pkg / "empty").mkdir()
            return [{"type": "dir", "path": "empty"}]
        pkg = self.make_pkg("0.1.0", extra=empty_dir)
        proc = self.run_verify(pkg)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_unlisted_empty_dir_is_rejected(self):
        pkg = self.make_pkg("0.1.0")
        (pkg / "junk").mkdir()
        proc = self.run_verify(pkg)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("extra directory", proc.stderr)

    def test_listed_dir_made_unreadable_fails_closed(self):
        def locked_dir(pkg):
            (pkg / "locked").mkdir()
            return [{"type": "dir", "path": "locked"}]
        pkg = self.make_pkg("0.1.0", extra=locked_dir)
        os.chmod(pkg / "locked", 0)
        self.addCleanup(os.chmod, pkg / "locked", 0o700)
        proc = self.run_verify(pkg)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("cannot list directory", proc.stderr)

    def test_hard_link_alias_of_listed_file_is_rejected(self):
        def alias(pkg):
            os.link(pkg / "data" / "payload.txt", pkg / "data" / "alias.txt")
            data = (pkg / "data" / "payload.txt").read_bytes()
            return [{"type": "file", "path": "data/alias.txt", "size": len(data), "sha256": sha256(data),
                     "mode": "0644"}]
        pkg = self.make_pkg("0.1.0", extra=alias)
        proc = self.run_verify(pkg)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("hard link", proc.stderr)

    def test_fifo_in_package_fails_without_hanging(self):
        pkg = self.make_pkg("0.1.0")
        os.mkfifo(pkg / "data" / "pipe")
        started = time.monotonic()
        proc = self.run_verify(pkg, timeout=20)
        self.assertEqual(proc.returncode, 1)
        self.assertLess(time.monotonic() - started, 10)

    def test_verify_fails_closed_on_unexpected_error(self):
        pkg = self.make_pkg("0.1.0")
        manifest = json.loads((pkg / "PACKAGE.json").read_text())
        manifest["files"].append("not-an-object")
        (pkg / "PACKAGE.json").write_text(json.dumps(manifest))
        proc = self.run_verify(pkg)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FAIL", proc.stderr)


# F5: FIFO at install.json must not block; lock released.
class FifoTests(Base):
    def test_fifo_ledger_is_immediate_error_and_lock_is_released(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        (self.root / "install.json").unlink()
        os.mkfifo(self.root / "install.json")
        started = time.monotonic()
        rc, obj, err = self.run_tool("list", timeout=20)
        self.assertEqual(rc, 5, err)
        self.assertEqual(obj["error"], "ledger_invalid")
        self.assertLess(time.monotonic() - started, 10)
        rc, obj, err = self.run_tool("repair", timeout=20)
        self.assertEqual(rc, 5, err)
        self.assertLess(time.monotonic() - started, 15)


# F8: gideon-launch keeps a shared lock for the Core's lifetime (inherited across exec).
class LockHeldByCoreTests(Base):
    def test_running_core_blocks_update_until_it_exits(self):
        self.ok("install", str(self.make_pkg("0.1.0", core=STUB_CORE)))
        mark = self.base / "mark.txt"
        env = {"GIDEON_STUB_MARK": str(mark), "GIDEON_STUB_HOLD": "120",
               "GIDEON_INSTALL_LOCK_TIMEOUT": "0.3"}
        proc = subprocess.Popen([sys.executable, "-I", "-B", str(LAUNCH), "--install-root", str(self.root), "alice"],
                                env=self.clean_env(env), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.addCleanup(self.reap, proc)
        deadline = time.monotonic() + 15
        while not mark.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(mark.exists(), "Core stub did not start")
        rc, obj, err = self.run_tool("update", str(self.make_pkg("0.2.0")),
                                     env={"GIDEON_INSTALL_LOCK_TIMEOUT": "0.3"}, timeout=60)
        self.assertEqual(rc, 6, f"update must be refused while the Core holds the lock: {obj} {err}")
        self.assertEqual(obj["error"], "locked")
        self.assertEqual(self.ledger()["current"], ID1)
        proc.kill()
        proc.wait(timeout=10)
        self.ok("update", str(self.make_pkg("0.2.0")))
        self.assertEqual(self.ledger()["current"], ID2)

    def start_core(self, name):
        mark = self.base / f"mark-{name}.txt"
        env = {"GIDEON_STUB_MARK": str(mark), "GIDEON_STUB_HOLD": "120"}
        proc = subprocess.Popen([sys.executable, "-I", "-B", str(LAUNCH), "--install-root", str(self.root), name],
                                env=self.clean_env(env), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.addCleanup(self.reap, proc)
        deadline = time.monotonic() + 15
        while not mark.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(mark.exists(), "Core stub did not start")
        return proc

    @staticmethod
    def reap(proc):
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
        proc.stderr.close()

    def profile_core_dir(self, name):
        core = self.root / "profiles" / name / "core"
        core.mkdir(mode=0o700, exist_ok=True)
        return core

    def test_running_profile_core_gives_profile_active_at_once(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.start_core("alice")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(listener.close)
        listener.bind(str(self.profile_core_dir("alice") / "core.sock"))
        listener.listen(1)
        started = time.monotonic()
        rc, obj, err = self.run_tool("update", str(self.make_pkg("0.2.0")),
                                     env={"GIDEON_INSTALL_LOCK_TIMEOUT": "30"}, timeout=60)
        elapsed = time.monotonic() - started
        self.assertEqual(rc, 3, f"update must be refused by the active profile: {obj} {err}")
        self.assertFalse(obj["ok"])
        self.assertEqual(obj["error"], "profile_active")
        self.assertEqual(obj["profile"], "alice")
        self.assertLess(elapsed, 2, "profile_active must not wait for the lock timeout")
        self.assertEqual(self.ledger()["current"], ID1)
        # Read-only commands keep working under the Core's shared lock.
        self.assertEqual(self.ok("list")["ok"], True)

    def test_stale_profile_socket_is_not_active_so_lock_wait_gives_locked(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        self.start_core("alice")
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(self.profile_core_dir("alice") / "core.sock"))
        stale.close()  # socket file stays on disk, nothing listens
        rc, obj, err = self.run_tool("update", str(self.make_pkg("0.2.0")),
                                     env={"GIDEON_INSTALL_LOCK_TIMEOUT": "0.3"}, timeout=60)
        self.assertEqual(rc, 6, f"stale socket must not count as active: {obj} {err}")
        self.assertEqual(obj["error"], "locked")
        self.assertEqual(self.ledger()["current"], ID1)

    def test_lock_held_by_installer_without_profile_socket_gives_locked_after_timeout(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        fd = os.open(self.root / ".lock", os.O_RDWR)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        started = time.monotonic()
        rc, obj, err = self.run_tool("update", str(self.make_pkg("0.2.0")),
                                     env={"GIDEON_INSTALL_LOCK_TIMEOUT": "0.3"}, timeout=60)
        elapsed = time.monotonic() - started
        self.assertEqual(rc, 6, f"{obj} {err}")
        self.assertEqual(obj["error"], "locked")
        self.assertGreaterEqual(elapsed, 0.3)
        self.assertEqual(self.ledger()["current"], ID1)

    def test_pinned_core_options_are_rejected_by_launch_before_exec(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        mark = self.base / "mark.txt"
        for bad in ("--root=/x", "--plugin-python=/usr/bin/python3", "--commands-sandbox"):
            rc, err = self.run_launch("alice", bad, env={"GIDEON_STUB_MARK": str(mark)})
            self.assertEqual(rc, 2, err)
        self.assertFalse(mark.exists())


# F6: user options the package pins are refused with exit 2 (gideon-core and gideon-launch).
PINNED = ["--root", "--home", "--base-pack", "--tts-virtual", "--wake-replay", "--commands-sandbox",
          "--plugin-python"]


def core_dry(base, *args):
    pkg = base / "corepkg"
    (pkg / "bin").mkdir(parents=True, exist_ok=True)
    shutil.copy2(CORE, pkg / "bin" / "gideon-core")
    env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    env["GIDEON_CORE_DRYRUN"] = "1"
    return subprocess.run([str(pkg / "bin" / "gideon-core"), "/abs/state", *args],
                          capture_output=True, text=True, timeout=60, env=env)


class PinnedOptionTests(Base):
    def core_dry(self, *args):
        return core_dry(self.base, *args)

    def test_core_rejects_every_pinned_option_spaced_and_equals_forms(self):
        for option in PINNED:
            for args in ([option, "x"], [f"{option}=x"], [option]):
                proc = self.core_dry(*args)
                self.assertEqual(proc.returncode, 2, f"{args}: {proc.stdout} {proc.stderr}")
                self.assertIn(option, proc.stderr)
                self.assertEqual(proc.stdout, "")

    def test_core_keeps_non_pinned_options(self):
        proc = self.core_dry("--hub-catalog", "/abs/cat.json", "digest", "--virtual-input")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        argv = json.loads(proc.stdout)["argv"]
        self.assertEqual(argv[-4:], ["--hub-catalog", "/abs/cat.json", "digest", "--virtual-input"])

    def test_launch_rejects_pinned_options_with_exit_2(self):
        self.ok("install", str(self.make_pkg("0.1.0")))
        mark = self.base / "mark.txt"
        for bad in ([f"--home=/x"], ["--base-pack", "/x"], ["--wake-replay", "a", "b", "0"]):
            rc, err = self.run_launch("alice", *bad, env={"GIDEON_STUB_MARK": str(mark)})
            self.assertEqual(rc, 2, err)
        self.assertFalse(mark.exists())


# F7: gideon-configure refuses STATE and package paths that cannot be injected into config.yaml safely.
class ConfigurePathTests(Base):
    def make_configure(self, where):
        pkg = where / "bin"
        pkg.mkdir(parents=True)
        shutil.copy2(CONFIGURE, pkg / "gideon-configure")
        return pkg / "gideon-configure"

    def run_configure(self, tool, state):
        return subprocess.run([sys.executable, "-I", "-B", str(tool), state], capture_output=True, text=True,
                              timeout=60)

    def test_state_with_space_and_hash_is_rejected_without_writes(self):
        tool = self.make_configure(self.base / "pkg")
        state = "/tmp/My State #1"
        proc = self.run_configure(tool, state)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("STATE_DIR may only", proc.stderr)
        self.assertFalse(os.path.exists(state))

    def test_other_unsafe_state_characters_rejected(self):
        tool = self.make_configure(self.base / "pkg")
        for state in ['/tmp/a"b', "/tmp/a'b", "/tmp/a\\b", "/tmp/a\nb", "/tmp/a#b", "/tmp/a b", "/tmp/a\tb"]:
            proc = self.run_configure(tool, state)
            self.assertEqual(proc.returncode, 1, state)
            self.assertIn("STATE_DIR may only", proc.stderr)

    def test_safe_state_is_accepted_by_the_check(self):
        tool = self.make_configure(self.base / "pkg")
        proc = self.run_configure(tool, str(self.base / "state-1.2+x"))
        self.assertNotIn("STATE_DIR may only", proc.stderr)

    def test_package_path_with_space_is_rejected(self):
        tool = self.make_configure(self.base / "pkg with space")
        proc = self.run_configure(tool, str(self.base / "state"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("package path", proc.stderr)
        self.assertFalse((self.base / "state").exists())


# F11: DRYRUN argv is emitted by python json.dumps from NUL-separated args (newlines and trailing newlines survive).
class DryRunJsonTests(Base):
    def test_argv_faithful_for_newlines_quotes_and_unicode(self):
        tricky = ["a\nb\n", "tab\t", 'q"b\\', "ünï", "", "trailing\n"]
        proc = core_dry(self.base, "--flag", *tricky)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["argv"][-len(tricky) - 1:], ["--flag", *tricky])


# F14: sh launchers pin PATH before any command runs.
class ShellPathTests(Base):
    def test_dry_run_works_with_empty_caller_path(self):
        pkg = self.base / "corepkg"
        (pkg / "bin").mkdir(parents=True, exist_ok=True)
        shutil.copy2(CORE, pkg / "bin" / "gideon-core")
        proc = subprocess.run([str(pkg / "bin" / "gideon-core"), "/abs/state"], capture_output=True, text=True,
                              timeout=60, env={"PATH": "", "GIDEON_CORE_DRYRUN": "1"})
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_launchers_set_path_first(self):
        for tool in (CORE, APP):
            lines = [l for l in tool.read_text().splitlines() if l and not l.startswith("#")]
            self.assertEqual(lines[0], "PATH=/usr/bin:/bin", tool.name)


# F13: unexpected exceptions (including TimeoutExpired) become JSON error other, exit 6.
class CatchAllTests(Base):
    def test_timeout_becomes_json_other_rc6(self):
        gi = load_module("gideon_install_t13", INSTALL)
        import subprocess as sp
        with mock.patch.object(gi, "dispatch", side_effect=sp.TimeoutExpired(cmd="verify", timeout=1)):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = gi.main(["--install-root", str(self.root), "list"])
        self.assertEqual(rc, 6)
        obj = json.loads(out.getvalue())
        self.assertEqual((obj["ok"], obj["error"]), (False, "other"))
        self.assertIn("TimeoutExpired", obj["message"])


# F12: the version tree is fsynced (files, then dirs) before the ledger commit.
class FsyncTests(Base):
    def test_fsync_tree_covers_every_regular_file_and_directory(self):
        gi = load_module("gideon_install_t12", INSTALL)
        tree = self.base / "tree"
        (tree / "a" / "b").mkdir(parents=True)
        (tree / "a" / "f1").write_text("1")
        (tree / "a" / "b" / "f2").write_text("2")
        (tree / "top").write_text("3")
        synced = set(gi.fsync_tree(str(tree)))
        expected = {str(p) for p in tree.rglob("*") if p.is_file() or p.is_dir()} | {str(tree)}
        self.assertEqual(synced, expected)

    def test_install_version_syncs_tree_before_returning(self):
        gi = load_module("gideon_install_t12b", INSTALL)
        sys.dont_write_bytecode = True
        src = self.make_pkg("0.1.0")
        info = gi.package_info(str(src))
        (self.root / "versions").mkdir(parents=True)
        calls = []
        real = gi.fsync_tree
        with mock.patch.object(gi, "fsync_tree", side_effect=lambda p: calls.append(p) or real(p)):
            how = gi.install_version(str(self.root), str(src), info)
        self.assertEqual(how, "moved")
        self.assertEqual(calls, [str(self.root / "versions" / ID1)])


# F10: a moved source that fails post-rename verification is moved back, never deleted.
class SourceRestoreTests(Base):
    def test_failed_verification_restores_moved_source(self):
        gi = load_module("gideon_install_t10", INSTALL)
        src = self.make_pkg("0.1.0")
        info = gi.package_info(str(src))
        (self.root / "versions").mkdir(parents=True)

        def reject(path):
            raise gi.Fail("verify_failed", "forced", rc=4)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GIDEON_INSTALL_FORCE_COPY", None)
            with mock.patch.object(gi, "verify_pkg", side_effect=reject):
                with self.assertRaises(gi.Fail) as cm:
                    gi.install_version(str(self.root), str(src), info)
        self.assertEqual(cm.exception.extra["source_restored"], str(src))
        self.assertTrue((src / "data" / "payload.txt").is_file(), "source must survive verification failure")
        self.assertEqual(os.listdir(self.root / "versions"), [])

    def test_restore_goes_to_quarantine_when_original_path_is_taken(self):
        gi = load_module("gideon_install_t10b", INSTALL)
        stage = self.root / "versions" / ".stage-x"
        stage.mkdir(parents=True)
        (stage / "keep.txt").write_text("source")
        src = self.base / "taken"
        src.mkdir()
        where = gi.restore_source(str(stage), str(src))
        self.assertTrue(where.startswith(str(self.base / ".quarantine-taken")))
        self.assertEqual(Path(where, "keep.txt").read_text(), "source")
        self.assertTrue(src.is_dir())


# F9: build_package helpers (no build): name validation, --home probe, atomic staged build.
class BuildPackageTests(Base):
    def setUp(self):
        super().setUp()
        self.bp = load_module("build_package_t9", BUILD)

    def test_checked_join_rejects_absolute_and_parent_names(self):
        for bad in ("/etc/passwd", "../x", "a/../../x", "a/../b", "", "a\\b", "a\x00b"):
            with self.assertRaises(SystemExit, msg=repr(bad)):
                self.bp.checked_join(str(self.base), bad)

    def test_checked_join_accepts_plain_relative_names(self):
        self.assertEqual(self.bp.checked_join(str(self.base), "data/x.bin"), self.base / "data" / "x.bin")

    def test_copy_pinned_refuses_escaping_manifest_name_and_writes_nothing(self):
        src_dir = self.base / "assets"
        src_dir.mkdir()
        (self.base / "evil").write_text("x")
        (src_dir / "fine").write_text("ok")
        dst = self.base / "dst"
        dst.mkdir()
        digest = sha256(b"x")
        with self.assertRaises(SystemExit):
            self.bp.copy_pinned(src_dir, ["../evil"], dst, {"../evil": digest})
        self.assertEqual(os.listdir(dst), [])

    def test_supports_home_detects_unknown_option(self):
        unsupported = self.base / "old-gideon-base"
        unsupported.write_text("#!/bin/sh\necho 'unknown or duplicate option' >&2\nexit 1\n")
        os.chmod(unsupported, 0o755)
        supported = self.base / "new-gideon-base"
        supported.write_text("#!/bin/sh\necho 'absolute --home required' >&2\nexit 1\n")
        os.chmod(supported, 0o755)
        self.assertFalse(self.bp.supports_home(unsupported))
        self.assertTrue(self.bp.supports_home(supported))

    def _fake_repo(self):
        repo = self.base / "repo"
        (repo / "target" / "release").mkdir(parents=True)
        (repo / "target" / "release" / "gideon-base").write_bytes(b"release")
        return repo

    def _run_main(self, out, build_tree):
        argv = ["build_package.py", str(out), "--version", "9.9.9"]
        with mock.patch.object(self.bp, "REPO", self._fake_repo()), \
                mock.patch.object(self.bp, "build_packaged_binary", return_value=self.base / "bin"), \
                mock.patch.object(self.bp, "build_tree", side_effect=build_tree), \
                mock.patch.object(sys, "argv", argv):
            return self.bp.main()

    def test_failed_build_leaves_no_partial_package(self):
        out = self.base / "out"
        out.mkdir()

        def partial(pkg, name, version, gideon_base, binary):
            pkg.mkdir()
            (pkg / "half.bin").write_bytes(b"partial")
            self.bp.die("disk full (simulated)")
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            self._run_main(out, partial)
        self.assertEqual(os.listdir(out), [], "no gideon-base-* and no staging leftovers")

    def test_successful_build_is_renamed_into_place(self):
        out = self.base / "out"
        out.mkdir()

        def good(pkg, name, version, gideon_base, binary):
            pkg.mkdir()
            (pkg / "PACKAGE.json").write_text(json.dumps({"name": name, "files": []}))
            return ["dropped-item"]
        with redirect_stdout(io.StringIO()) as captured:
            self._run_main(out, good)
        self.assertEqual(os.listdir(out), ["gideon-base-9.9.9"])
        self.assertIn("dropped-item", captured.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
