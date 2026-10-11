"""Hash-chained event log.

A complete line is ``<sha256 of body> <canonical JSON>`` plus a newline.
The body carries ``seq`` and ``prev_sha256`` (the previous line's digest;
the first event uses the empty string). Bytes after the last newline are a
torn tail and are not part of the log.

The chain shows a torn write or an edit in the middle. It is not a signature:
the same Unix user can rewrite the file. It does not make the words true.

Taken from ``w31/w66-lane-v2`` ``events.py`` and fitted to this design:
``v`` is 1, ``at`` is a number (UTC seconds), and a full log is flagged.
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
    prefix = complete_prefix(data)
    log = Log(raw_valid=prefix)
    if len(prefix) >= MAX_BYTES:
        log.full = True
    if not prefix:
        return log
    lines = prefix.split(b"\n")[:-1]
    prev = GENESIS
    for index, line in enumerate(lines):
        want_seq = index + 1
        try:
            digest, obj = parse_line(line)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            log.invalid_seq = _seq_hint(line, want_seq)
            log.last_valid_seq = want_seq - 1 if want_seq > 1 else 0
            return log
        seq = obj.get("seq")
        if seq != want_seq or obj.get("prev_sha256") != prev:
            log.invalid_seq = seq if isinstance(seq, int) and not isinstance(seq, bool) else want_seq
            log.last_valid_seq = want_seq - 1 if want_seq > 1 else 0
            return log
        log.events.append(obj)
        log.digests.append(digest)
        prev = digest
    log.last_valid_seq = len(log.events) if log.events else 0
    if len(log.events) >= MAX_EVENTS or len(prefix) >= MAX_BYTES:
        log.full = True
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
    if len(log.events) + 1 > MAX_EVENTS or len(data) + len(line) > MAX_BYTES:
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
    if len(log.events) + extra > MAX_EVENTS or len(data) + len(blob) > MAX_BYTES:
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
    obj["v"] = 1
    obj["by"] = by
    obj["at"] = at
    obj["seq"] = len(log.events) + 1
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
