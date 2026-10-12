"""Watch a job without touching it.

Stays alive while ``pgrep -f`` still sees a match. When none is left, reads
the completion marker and exits with the code in ``exit=<n>``. If the marker
is still missing 30 seconds later, exits 70.

The pattern also appears on this process's own command line, and on the
recorder ``run`` wrapper that started it. Those two pids are not the job.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

MARKER_WAIT_S = 30
_EXIT = re.compile(r"exit=(\d+)")


def matching(pattern: str) -> bool:
    """True when some process other than this one and its parent matches."""
    skip = {os.getpid(), os.getppid()}
    try:
        proc = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return True
    if proc.returncode not in (0, 1):
        return True
    for line in proc.stdout.splitlines():
        text = line.strip()
        if not text.isdigit():
            continue
        if int(text) not in skip:
            return True
    return False


def marker_exit(path: Path) -> int | None:
    """The first ``exit=<n>`` in the marker, or None when it is not there yet."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    except OSError:
        return None
    found = _EXIT.search(text)
    if found is None:
        return None
    return int(found.group(1))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="proxy.py")
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--done", required=True)
    parser.add_argument("--poll", type=float, default=2)
    args = parser.parse_args(argv)
    if args.poll <= 0:
        print("poll must be greater than 0", file=sys.stderr)
        return 2
    done = Path(args.done)
    gone_at = None
    while True:
        if matching(args.pattern):
            gone_at = None
            time.sleep(args.poll)
            continue
        code = marker_exit(done)
        if code is not None:
            return code
        now = time.monotonic()
        if gone_at is None:
            gone_at = now
        if now - gone_at >= MARKER_WAIT_S:
            return 70
        time.sleep(args.poll)


if __name__ == "__main__":
    sys.exit(main())
