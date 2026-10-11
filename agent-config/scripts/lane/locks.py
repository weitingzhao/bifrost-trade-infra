"""Two flock files. Take ``lock`` then ``run.lock``, both non-blocking; release in reverse.

The bytes in a lock file are a label ``{pid, command, since}`` for messages.
A successful probe means the label is void.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import fcntl

from errors import LaneError
from events import head_token
from fsutil import fullsync

RETRY_SECONDS = 2.0


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lock_path(lane_dir: Path) -> Path:
    return lane_dir / "lock"


def run_lock_path(lane_dir: Path) -> Path:
    return lane_dir / "run.lock"


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
    """Return ``(free, label_if_held)``. Missing file is free. Does not create it."""
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
    payload = json.dumps({"pid": os.getpid(), "command": command, "since": _now()}, sort_keys=True) + "\n"
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
                raise TimeoutError(path)
            time.sleep(0.02)
    _write_label(fd, command)
    return fd


def release(fd: int) -> None:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def busy_message(lane_dir: Path, lane_id: str) -> LaneError:
    free, label = probe(run_lock_path(lane_dir))
    if not free:
        pid = (label or {}).get("pid", "unknown")
        return LaneError(f"lane {lane_id} is being driven by pid {pid}", exit_code=3)
    label = _read_label(lock_path(lane_dir)) or {}
    pid = label.get("pid", "unknown")
    command = label.get("command", "unknown")
    return LaneError(f"lane {lane_id} is busy: {command} (pid {pid})", exit_code=3)


@contextmanager
def hold(lane_dir: Path, lane_id: str, command: str):
    try:
        fd = acquire(lock_path(lane_dir), command)
    except TimeoutError:
        raise busy_message(lane_dir, lane_id) from None
    try:
        yield fd
    finally:
        release(fd)


@dataclass
class Snapshot:
    stable: bool
    data: bytes
    driver: bool
    lock_held: bool
    lock_label: dict | None
    run_label: dict | None


def read_snapshot(lane_dir: Path, *, gap=None, attempts: int = 3) -> Snapshot:
    """Head, probe both locks, head again. Three unstable tries yield ``changing``."""
    path = lane_dir / "events.jsonl"

    def read() -> tuple[tuple, bytes]:
        data = path.read_bytes() if path.is_file() else b""
        return head_token(data), data

    for _ in range(attempts):
        token1, _data1 = read()
        lock_free, lock_label = probe(lock_path(lane_dir))
        run_free, run_label = probe(run_lock_path(lane_dir))
        if gap is not None:
            gap()
        token2, data2 = read()
        if token1 == token2:
            from events import complete_prefix

            return Snapshot(
                stable=True,
                data=complete_prefix(data2),
                driver=not run_free,
                lock_held=not lock_free,
                lock_label=None if lock_free else lock_label,
                run_label=None if run_free else run_label,
            )
    return Snapshot(False, b"", False, False, None, None)
