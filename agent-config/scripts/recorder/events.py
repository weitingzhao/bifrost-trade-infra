"""Hash-chained event log. ``v`` is 2. A line whose ``v`` is not 2 is a broken chain.

Taken from ``w31/w66-lane-v2`` ``events.py`` and fitted to this design.
Bytes after the last newline are a torn tail and are not part of the log.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from fsutil import canonical_json, fullsync, loads_strict

GENESIS = ""
MAX_EVENTS = 20_000
MAX_BYTES = 16 * 1024 * 1024


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump_line(obj: dict) -> bytes:
    body = canonical_json(obj).encode("utf-8")
    digest = sha256_bytes(body)
    return digest.encode("ascii") + b" " + body + b"\n"


def _seq_hint(line: bytes, expected: int) -> int:
    space = line.find(b" ")
    if space < 0:
        return expected
    try:
        obj = loads_strict(line[space + 1 :].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return expected
    seq = obj.get("seq") if isinstance(obj, dict) else None
    return seq if isinstance(seq, int) and not isinstance(seq, bool) else expected


def parse_line(line: bytes) -> tuple[str, dict]:
    space = line.find(b" ")
    if space != 64:
        raise ValueError("bad line")
    digest = line[:space].decode("ascii")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("bad digest")
    body = line[space + 1 :]
    if sha256_bytes(body) != digest:
        raise ValueError("digest mismatch")
    obj = loads_strict(body.decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("body")
    return digest, obj


def complete_prefix(data: bytes) -> bytes:
    if not data:
        return b""
    if data.endswith(b"\n"):
        return data
    cut = data.rfind(b"\n")
    return b"" if cut < 0 else data[: cut + 1]


def head_token(data: bytes) -> tuple:
    prefix = complete_prefix(data)
    if not prefix:
        return (0, None)
    last = prefix.split(b"\n")[-2]
    space = last.find(b" ")
    digest = last[:space].decode("ascii", "replace") if space > 0 else ""
    return (len(prefix), digest)


@dataclass
class Log:
    events: list[dict] = field(default_factory=list)
    digests: list[str] = field(default_factory=list)
    invalid_seq: int | None = None
    last_valid_seq: int | None = None
    raw_valid: bytes = b""
    full: bool = False


def load_bytes(data: bytes) -> Log:
    from read import read_log

    loaded = read_log(None, data if type(data) is bytes else b"")
    log = Log(raw_valid=complete_prefix(data if type(data) is bytes else b""))
    log.full = loaded.full
    log.digests = list(loaded.digests)
    log.events = [dict(event._fields) for event in loaded.events]
    if loaded.broken_line is not None:
        log.invalid_seq = loaded.broken_line
        log.last_valid_seq = loaded.broken_line - 1
    else:
        log.last_valid_seq = len(log.events)
    return log


def load_file(path: Path) -> Log:
    if not path.is_file():
        return Log()
    return load_bytes(path.read_bytes())


def append_sealed(path: Path, obj: dict) -> None:
    """Append one already-sealed line. The caller holds the log lock.

    Refuses a torn tail, a broken chain, and a log that is already full.
    Does not decide whether the event is meaningful.
    """
    data = path.read_bytes() if path.is_file() else b""
    if data and not data.endswith(b"\n"):
        raise ValueError("refusing to append over a torn tail")
    log = load_bytes(data)
    if log.invalid_seq is not None:
        raise ValueError("refusing to append to an invalid log")
    if log.full:
        raise ValueError("refusing to append to a full log")
    line = dump_line(obj)
    if len(log.digests) + 1 > MAX_EVENTS or len(data) + len(line) > MAX_BYTES:
        raise ValueError("refusing to append to a full log")
    fd = os_open_append(path)
    try:
        os_write_all(fd, line)
        fullsync(fd)
    finally:
        os_close(fd)


def append_bytes(path: Path, blob: bytes) -> None:
    """Append already-sealed lines in one write. The caller holds the lock."""
    if not blob:
        return
    data = path.read_bytes() if path.is_file() else b""
    if data and not data.endswith(b"\n"):
        raise ValueError("refusing to append over a torn tail")
    log = load_bytes(data)
    if log.invalid_seq is not None:
        raise ValueError("refusing to append to an invalid log")
    if log.full:
        raise ValueError("refusing to append to a full log")
    extra = blob.count(b"\n")
    if len(log.digests) + extra > MAX_EVENTS or len(data) + len(blob) > MAX_BYTES:
        raise ValueError("refusing to append to a full log")
    fd = os_open_append(path)
    try:
        os_write_all(fd, blob)
        fullsync(fd)
    finally:
        os_close(fd)


def seal(fields: dict, log: Log, by: str, at: float) -> dict:
    """Fill ``v``, ``seq``, ``prev_sha256``, ``at`` and ``by``. Does not write."""
    obj = dict(fields)
    obj["v"] = 2
    obj["by"] = by
    obj["at"] = at
    obj["seq"] = len(log.digests) + 1
    obj["prev_sha256"] = log.digests[-1] if log.digests else GENESIS
    return obj


def os_open_append(path: Path) -> int:
    import os

    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)


def os_write_all(fd: int, data: bytes) -> None:
    from fsutil import write_all

    write_all(fd, data)


def os_close(fd: int) -> None:
    import os

    os.close(fd)
