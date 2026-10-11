"""One flock per event log, held only while a single append is in progress.

Non-blocking. If the lock is taken, retry for two seconds, then fail.
There is no ``run.lock`` here: that belonged to the stopped lane and was dropped.

The bytes in the lock file are a label ``{pid, command, since}`` so a refusal
can name who holds it. A successful probe means the label is void.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import fcntl

from fsutil import fullsync

RETRY_SECONDS = 2.0


class LockBusy(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lock_path(directory: Path) -> Path:
    return directory / "lock"


def _read_label(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    line = text.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def probe(path: Path) -> tuple[bool, dict | None]:
    """Return ``(free, label_if_held)``. A missing file is free. Does not create it."""
    if not path.exists():
        return True, None
    fd = os.open(path, os.O_RDWR)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return False, _read_label(path)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return True, None
    finally:
        os.close(fd)


def _write_label(fd: int, command: str) -> None:
    payload = json.dumps(
        {"pid": os.getpid(), "command": command, "since": _now()},
        sort_keys=True,
    ) + "\n"
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    os.write(fd, payload.encode("utf-8"))
    fullsync(fd)


def acquire(path: Path, command: str, *, timeout: float = RETRY_SECONDS) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    os.set_inheritable(fd, False)
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(fd)
                label = _read_label(path) or {}
                pid = label.get("pid", "unknown")
                held = label.get("command", "unknown")
                raise LockBusy(f"lock busy: {held} (pid {pid})")
            time.sleep(0.02)
    _write_label(fd, command)
    return fd


def release(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


@contextmanager
def hold(directory: Path, command: str, *, timeout: float = RETRY_SECONDS):
    fd = acquire(lock_path(directory), command, timeout=timeout)
    try:
        yield fd
    finally:
        release(fd)
