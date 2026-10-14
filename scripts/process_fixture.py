"""Observe only PIDs already obtained from the fixture's owned process tree."""
from pathlib import Path

def command_line(pid):
    try:return Path(f'/proc/{pid}/cmdline').read_bytes()
    except (FileNotFoundError,ProcessLookupError):return b''
