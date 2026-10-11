"""Durable file publication. macOS fsync uses F_FULLFSYNC.

Taken from the stopped branch ``w31/w66-lane-v2`` (``agent-config/scripts/lane/fsutil.py``).
Nothing here judges a step or releases anything.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


def fullsync(fd: int) -> None:
    if fcntl is not None and hasattr(fcntl, "F_FULLFSYNC"):
        try:
            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
            return
        except OSError:
            pass
    os.fsync(fd)


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        fullsync(fd)
    finally:
        os.close(fd)


def write_all(fd: int, data: bytes) -> None:
    """Write every byte. A zero return is an error, not a short write to retry."""
    view = memoryview(data)
    while len(view):
        wrote = os.write(fd, view)
        if wrote == 0:
            raise OSError("os.write returned 0")
        view = view[wrote:]


def write_bytes(path: Path, data: bytes) -> None:
    """Write every byte, fsync the file, then fsync the directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        write_all(fd, data)
        fullsync(fd)
    finally:
        os.close(fd)
    fsync_dir(path.parent)


def publish(dest: Path, data: bytes) -> None:
    """Temp file, fsync, rename, fsync the parent directory."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f".{dest.name}.tmp-{secrets.token_hex(4)}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        write_all(fd, data)
        fullsync(fd)
    except Exception:
        os.close(fd)
        tmp.unlink(missing_ok=True)
        raise
    else:
        os.close(fd)
    os.rename(tmp, dest)
    fsync_dir(dest.parent)


def _reject_duplicate_keys(pairs: list) -> dict:
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate key {key}")
        obj[key] = value
    return obj


def loads_strict(text: str):
    """Parse JSON and refuse duplicate keys. ``json.loads`` would keep the last one."""
    return json.loads(text, object_pairs_hook=_reject_duplicate_keys)


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def publish_json(dest: Path, obj: object) -> bytes:
    data = (canonical_json(obj) + "\n").encode("utf-8")
    publish(dest, data)
    return data
