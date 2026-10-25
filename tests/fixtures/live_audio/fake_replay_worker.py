#!/usr/bin/python3
"""Test-only stand-in for the wake python of the replay profile (A6).

The Core runs its wake worker with the same interpreter in both modes:
- replay (no `--live`): it exits 0 at once and writes nothing, so the Core reports `replay_finished`
  exactly as the boot replay does when its fixture is spent;
- live (`--live`): it hands over to the real `scripts/wake_worker.py` (test-energy detector, no models),
  so the live pipeline runs unchanged.
"""
import os
import sys

if "--live" in sys.argv[1:]:
    os.execv("/usr/bin/python3", ["/usr/bin/python3"] + sys.argv[1:])
sys.exit(0)
