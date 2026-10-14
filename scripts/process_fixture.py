"""Observe only PIDs already obtained from the fixture's owned process tree."""
from pathlib import Path

def command_line(pid):
    try:return Path(f'/proc/{pid}/cmdline').read_bytes()
    except (FileNotFoundError,ProcessLookupError):return b''

def resident_bytes(pid):
    """Exited owned children contribute no current RSS to a sampled tree."""
    import os
    try:fields=Path(f'/proc/{pid}/statm').read_text().split()
    except (FileNotFoundError,ProcessLookupError):return 0
    return int(fields[1])*os.sysconf('SC_PAGE_SIZE') if len(fields)>=2 else 0
