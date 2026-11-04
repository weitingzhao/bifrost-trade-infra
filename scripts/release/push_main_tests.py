#!/usr/bin/env python3
"""Run a repository's fast tests side by side, each test file in its own processes (R5:5.7-3).

    push_main_tests.py [--jobs N] [--deadline SECONDS] <path>...

Run from the root of the tree under test; paths are relative to it. A directory
stands for the pytest files under it (test_*.py and *_test.py, in the directories
pytest itself enters: not hidden ones, build, dist, node_modules, venv, *.egg,
CVS, _darcs, {arch}, nor one holding a virtual environment). A .py file runs
with pytest -q -p no:cacheprovider, a .sh file with bash, a .test.js file with
node --test (TD-515).

A test file runs as one process, or, from PART_BYTES of source up, as one per
part: part i of n runs the file's i-th, (i+n)-th, ... tests in collection
order, so the parts together run each test once. Each process's exit code is
the one Popen.wait() returns for it, never read through a pipe (twice a
pusher's pipe hid a red test, LESSONS 186); its output goes to a file, printed
in full when it fails. A pytest process's 5 (no test to run) counts as passed,
as such a file adds nothing to a directory's run; a .sh test's 5 is a failure
like any other code but 0. --jobs processes run at once (the slowest
first, below); at --deadline every one still running is stopped with its
children, and it and those not started fail.

The slowest start first: each process's last duration is kept in
PUSH_MAIN_TEST_TIMES (default ~/.cache/bifrost/push-main-test-times.json,
written whole or not at all; an unreadable one counts as empty); one never
measured counts a second per kilobyte of its file. The order changes only
how long the run takes, never what runs.

Exit 0 when every process passed; 1 when any failed or did not finish; 2 when
the arguments name no test file; 130 when stopped by a signal.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SKIP_DIRS = {"build", "dist", "node_modules", "venv", "CVS", "_darcs", "{arch}"}
NO_TESTS = 5
PART_BYTES = int(os.environ.get("PUSH_MAIN_PART_BYTES") or 20000)
PYTEST = ["-q", "-p", "no:cacheprovider"]
# pytest with only part i of n of the collected tests (the others deselected).
PART = """
import sys
import pytest
i, n = map(int, sys.argv[1].split("/"))
class Part:
    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, config, items):
        drop = [t for k, t in enumerate(items) if k % n != i]
        items[:] = [t for k, t in enumerate(items) if k % n == i]
        if drop:
            config.hook.pytest_deselected(items=drop)
sys.exit(pytest.main(sys.argv[2:], plugins=[Part()]))
"""


def _times_path() -> Path:
    if os.environ.get("PUSH_MAIN_TEST_TIMES"):
        return Path(os.environ["PUSH_MAIN_TEST_TIMES"])
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(cache) / "bifrost" / "push-main-test-times.json"


def _load_times() -> dict[str, float]:
    try:
        data = json.loads(_times_path().read_text())
        return {str(k): float(v) for k, v in data.items() if isinstance(v, (int, float))}
    except (OSError, ValueError, AttributeError):
        return {}


def _save_times(times: dict[str, float]) -> None:
    path = _times_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}")
        tmp.write_text(json.dumps(times, sort_keys=True))
        os.replace(tmp, path)
    except OSError:
        pass


def _enters(directory: Path) -> bool:
    name = directory.name
    return not (name.startswith(".") or name in SKIP_DIRS or name.endswith(".egg")
                or (directory / "pyvenv.cfg").exists())


def files_of(root: Path, path: str) -> list[str]:
    """The test files a path stands for, relative to root, sorted."""
    target = root / path
    if target.is_file():
        return [path]
    if not target.is_dir():
        return []
    found = []
    for directory, subdirs, files in os.walk(target):
        here = Path(directory)
        subdirs[:] = sorted(d for d in subdirs if _enters(here / d))
        for name in files:
            if name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py")):
                found.append(str((here / name).relative_to(root)))
    return sorted(found)


def runs_of(root: Path, path: str) -> list[tuple[str, list[str], int]]:
    """(label, command, size) for each process a test file runs as."""
    size = (root / path).stat().st_size
    if path.endswith(".sh"):
        return [(path, ["bash", path], size)]
    if path.endswith(".test.js"):
        return [(path, ["node", "--test", path], size)]
    parts = max(1, math.ceil(size / PART_BYTES))
    if parts == 1:
        return [(path, ["python3", "-m", "pytest", *PYTEST, path], size)]
    return [(f"{path} [part {i + 1} of {parts}]", ["python3", "-c", PART, f"{i}/{parts}", *PYTEST, path], size // parts)
            for i in range(parts)]


def _signal_group(process: subprocess.Popen, sig: int) -> None:
    """Signal the test process's group. A group already gone is ESRCH; one left with
    only zombies is EPERM on macOS (seen 11-01: the KILL after the TERM crashed the
    runner, which then printed nothing): both mean nothing is left to stop."""
    try:
        os.killpg(process.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _stop(process: subprocess.Popen) -> None:
    """Stop a test process and everything it started (its own session): a TERM, up to
    5 s for it to end, then a KILL for whatever of the group is left."""
    _signal_group(process, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    _signal_group(process, signal.SIGKILL)
    process.wait()


def run(root: Path, paths: list[str], jobs: int, deadline: float, out=sys.stdout) -> int:
    files: list[str] = []
    for p in paths:
        for f in files_of(root, p):
            if f not in files:
                files.append(f)
    if not files:
        print(f"push-main: no test file in {' '.join(paths)}", file=out)
        return 2
    runs = [r for f in files for r in runs_of(root, f)]
    # The slowest first (as last measured; else a second per kB), so it does not start last.
    times = _load_times()
    queue = sorted(runs, key=lambda r: (-times.get(r[0], r[2] / 1000), r[0]))
    logs = Path(tempfile.mkdtemp(prefix="push-main-tests."))
    log_of = {label: logs / f"{n}.log" for n, (label, _c, _s) in enumerate(runs)}
    running: dict[str, tuple[subprocess.Popen, float, object]] = {}
    results: dict[str, tuple[int | None, float]] = {}
    started = time.monotonic()
    try:
        while queue or running:
            while queue and len(running) < jobs:
                label, cmd, _size = queue.pop(0)
                log = open(log_of[label], "wb")
                try:
                    process = subprocess.Popen(cmd, cwd=root, stdin=subprocess.DEVNULL, stdout=log,
                                               stderr=subprocess.STDOUT, start_new_session=True)
                except OSError as e:
                    # Not started (no process slot, say): a failure, said, not a crash.
                    log.write(f"push-main: could not start {cmd[0]}: {e}\n".encode())
                    log.close()
                    results[label] = (-1, 0.0)
                    continue
                running[label] = (process, time.monotonic(), log)
            for label, (process, since, log) in list(running.items()):
                if process.poll() is None:
                    continue
                code = process.wait()
                log.close()
                results[label] = (code, time.monotonic() - since)
                del running[label]
            if time.monotonic() - started > deadline:
                for label, (process, since, log) in running.items():
                    _stop(process)
                    log.close()
                    results[label] = (None, time.monotonic() - since)
                running.clear()
                for label, _cmd, _size in queue:
                    results[label] = (None, 0.0)
                queue.clear()
                break
            time.sleep(0.05)
    except KeyboardInterrupt:
        for process, _since, log in running.values():
            _stop(process)
            log.close()
        raise
    failed = []
    for label, cmd, _size in runs:
        code, took = results[label]
        # pytest's 5 is "no test to run"; any other program's 5 is a failure.
        if code == 0 or (code == NO_TESTS and cmd[0] == "python3"):
            continue
        failed.append(label)
        said = "did not finish within the deadline" if code is None else f"exit {code}"
        print(f"push-main: FAILED {label} ({said}, {took:.0f} s):", file=out)
        if log_of[label].exists():
            print(log_of[label].read_text(errors="replace"), file=out)
    times.update({label: round(took, 1) for label, (code, took) in results.items() if code is not None})
    _save_times(times)
    slowest = sorted(results.items(), key=lambda kv: -kv[1][1])[:3]
    print(f"push-main: {len(runs) - len(failed)} of {len(runs)} test runs passed ({len(files)} files) in "
          f"{time.monotonic() - started:.0f} s, {jobs} at a time (slowest: "
          + ", ".join(f"{label} {t:.0f} s" for label, (_c, t) in slowest) + ")", file=out)
    for label in failed:
        print(f"push-main: failed: {label}", file=out)
    for log in logs.iterdir():
        log.unlink()
    logs.rmdir()
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--jobs", type=int, default=int(os.environ.get("PUSH_MAIN_TEST_JOBS") or min(8, os.cpu_count() or 2)))
    parser.add_argument("--deadline", type=float, default=float(os.environ.get("PUSH_MAIN_TEST_DEADLINE") or 1800))
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    if args.jobs < 1 or args.deadline <= 0:
        parser.error("--jobs and --deadline must be positive")

    def stopped(signum, _frame):
        raise KeyboardInterrupt(f"signal {signum}")
    # Stopped from outside (push-main is), the test processes stop too.
    signal.signal(signal.SIGTERM, stopped)
    signal.signal(signal.SIGHUP, stopped)
    try:
        return run(Path.cwd(), args.paths, args.jobs, args.deadline)
    except KeyboardInterrupt:
        print("push-main: the tests were stopped", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
