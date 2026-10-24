#!/usr/bin/env python3
"""gideon-launch supervisor: restart on exit 75, bounded to 3 per 60 s; other statuses pass through.

Run: python3 -I -B scripts/test_package_launch_restart.py   (stdlib unittest; no network; no real Core).
The real-child test runs a tiny Python stand-in for gideon-core, never the Core itself.
"""
import importlib.machinery
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LAUNCH = REPO / "scripts" / "package_tools" / "gideon-launch"


def load_launch():
    loader = importlib.machinery.SourceFileLoader("gideon_launch_under_test", str(LAUNCH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


L = load_launch()


class FakeRun:
    """Stands in for run_once: returns the scripted statuses in order and counts the calls."""

    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = 0

    def __call__(self, argv, env, pass_fds, state):
        self.calls += 1
        return self.statuses.pop(0)


def clock(values):
    it = iter(values)
    return lambda: next(it)


class SupervisorTests(unittest.TestCase):
    def test_zero_and_other_statuses_pass_through_without_restart(self):
        for status in (0, 1, 4, 6):
            run = FakeRun([status])
            self.assertEqual(L.supervise(["core"], {}, (), run=run, now=lambda: 0.0), status)
            self.assertEqual(run.calls, 1)

    def test_exit_75_restarts_until_the_core_stops_normally(self):
        run = FakeRun([75, 75, 0])
        self.assertEqual(L.supervise(["core"], {}, (), run=run, now=lambda: 0.0), 0)
        self.assertEqual(run.calls, 3)

    def test_fourth_restart_inside_one_window_is_refused(self):
        run = FakeRun([75, 75, 75, 75, 0])
        status = L.supervise(["core"], {}, (), run=run, now=lambda: 10.0)
        self.assertEqual(status, L.RESTART_REFUSED)
        # Three restarts happened; the fourth exit of 75 stopped the launcher.
        self.assertEqual(run.calls, 4)

    def test_window_slides_so_an_old_restart_stops_counting(self):
        run = FakeRun([75, 75, 75, 75, 0])
        status = L.supervise(["core"], {}, (), run=run, now=clock([0.0, 0.0, 0.0, 61.0]))
        self.assertEqual(status, 0)
        self.assertEqual(run.calls, 5)

    def test_forwarded_signal_blocks_the_restart(self):
        def run(argv, env, pass_fds, state):
            state["stop"] = True
            return L.RESTART_EXIT

        self.assertEqual(L.supervise(["core"], {}, (), run=run, now=lambda: 0.0), L.RESTART_EXIT)

    def test_child_killed_by_signal_maps_to_shell_status(self):
        run = FakeRun([-15])
        self.assertEqual(L.supervise(["core"], {}, (), run=run, now=lambda: 0.0), 143)

    def test_constants_match_the_core_contract(self):
        # transport::RESTART_EXIT_CODE is 75; the budget is 3 restarts per 60 seconds.
        self.assertEqual(L.RESTART_EXIT, 75)
        self.assertEqual((L.RESTART_LIMIT, L.RESTART_WINDOW), (3, 60.0))


class RealChildTests(unittest.TestCase):
    def test_real_child_restarts_with_the_same_argv_and_keeps_the_fd(self):
        base = Path(tempfile.mkdtemp(prefix="gl-restart-"))
        self.addCleanup(shutil.rmtree, base, True)
        count = base / "count"
        script = base / "stand_in_core.py"
        script.write_text(
            "import os, sys\n"
            "p = os.environ['GL_COUNT']\n"
            "n = int(open(p).read()) if os.path.exists(p) else 0\n"
            "open(p, 'w').write(str(n + 1))\n"
            "open(p + '.argv', 'w').write(repr(sys.argv[1:]))\n"
            "sys.exit(75 if n < 2 else 0)\n")
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, read_fd)
        self.addCleanup(os.close, write_fd)
        env = dict(os.environ, GL_COUNT=str(count))
        status = L.supervise(
            [sys.executable, "-I", "-B", str(script), "--flag", "x y"], env, (write_fd,))
        self.assertEqual(status, 0)
        self.assertEqual(count.read_text(), "3")
        self.assertEqual(Path(str(count) + ".argv").read_text(), repr(["--flag", "x y"]))


if __name__ == "__main__":
    unittest.main(verbosity=1, exit=True)
