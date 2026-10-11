#!/usr/bin/env python3
"""Register a lane step, then become the command.

Usage: lane_runner.py <started-path> -- <argv...>

The runner is the session leader, so its pgid equals its pid. It writes
``started.json`` atomically (``pid``, ``pgid``, ``started_at``) and then
``os.execvp``s the command. The process keeps that pid, and the command's own
exit code is what ``lane.py`` reads from ``proc.wait()``. This program does
not write ``done``.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def write_started(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "pgid": os.getpgrp(),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    token = f"{os.getpid()}.{random.randrange(16 ** 8):08x}"
    tmp = path.with_name(f".{path.name}.{token}.tmp")
    data = json.dumps(payload) + "\n"
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--" not in args or not args or args[0] == "--":
        print("usage: lane_runner.py <started-path> -- <argv...>", file=sys.stderr)
        return 2
    sep = args.index("--")
    started = Path(args[0])
    command = args[sep + 1:]
    if not command:
        print("usage: lane_runner.py <started-path> -- <argv...>", file=sys.stderr)
        return 2
    # lane.py starts this process with a new session. If a caller did not, become
    # the session leader here so the recorded pgid is this pid.
    if os.getpgrp() != os.getpid():
        os.setsid()
    delay = os.environ.get("LANE_REGISTER_DELAY", "")
    if delay:
        time.sleep(float(delay))
    write_started(started)
    try:
        os.execvp(command[0], command)
    except OSError as exc:
        print(f"exec failed: {exc}", file=sys.stderr)
        return 127
    return 127


if __name__ == "__main__":
    sys.exit(main())
