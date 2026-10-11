#!/usr/bin/env python3
"""Run one lane command and record its exit if lane.py is no longer around.

Usage: lane_runner.py <done-path> -- <argv...>

The record is JSON ``{"exit": n, "ended_at": ...}``, written atomically when
the command ends. stdout and stderr are the ones lane.py already pointed at
the attempt log.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def write_done(path: Path, code: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"exit": code, "ended_at": datetime.now(timezone.utc).isoformat()}
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
        print("usage: lane_runner.py <done-path> -- <argv...>", file=sys.stderr)
        return 2
    sep = args.index("--")
    done = Path(args[0])
    command = args[sep + 1:]
    if not command:
        print("usage: lane_runner.py <done-path> -- <argv...>", file=sys.stderr)
        return 2
    try:
        completed = subprocess.run(command, shell=False)
        code = int(completed.returncode)
    except FileNotFoundError:
        code = 127
    write_done(done, code)
    return code


if __name__ == "__main__":
    sys.exit(main())
