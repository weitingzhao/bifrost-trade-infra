"""Durable file publication. macOS fsync uses F_FULLFSYNC."""

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


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, data)
        fullsync(fd)
    finally:
        os.close(fd)


def publish(dest: Path, data: bytes) -> None:
    """Temp file, fsync, rename, fsync the parent directory."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f".{dest.name}.tmp-{secrets.token_hex(4)}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.write(fd, data)
        fullsync(fd)
    except Exception:
        os.close(fd)
        tmp.unlink(missing_ok=True)
        raise
    else:
        os.close(fd)
    os.rename(tmp, dest)
    fsync_dir(dest.parent)


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def publish_json(dest: Path, obj: object) -> bytes:
    data = (canonical_json(obj) + "\n").encode("utf-8")
    publish(dest, data)
    return data
