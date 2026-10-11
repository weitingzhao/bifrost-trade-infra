"""Torn-tail repair with a stable repair id.

A torn tail is the byte range after the last newline. A newline-terminated
line whose digest does not match is corruption and is never removed.
``repair_id`` is ``<offset>-<first 16 hex of sha256(torn bytes)>``.

The caller holds the log lock. This function does not take it again: flock
on a second descriptor in the same process would wait on itself.

Taken from ``w31/w66-lane-v2`` ``repair.py``. The repair id is read off the
log itself; the stopped branch's ``query`` module is not used.
"""

from __future__ import annotations

import os
from pathlib import Path

from events import append_sealed, load_bytes, seal, sha256_bytes
from fsutil import fsync_dir, fullsync, publish


def repair_id(offset: int, torn: bytes) -> str:
    return f"{offset}-{sha256_bytes(torn)[:16]}"


def _torn_files(directory: Path) -> list[Path]:
    found = []
    if not directory.is_dir():
        return found
    for path in directory.iterdir():
        name = path.name
        if path.is_file() and name.startswith("events.torn-") and ".tmp-" not in name:
            found.append(path)
    return sorted(found, key=lambda item: item.name)


def _recorded(events: list[dict]) -> set[str]:
    found = set()
    for event in events:
        if event.get("type") == "tail_repaired" and isinstance(event.get("repair_id"), str):
            found.add(event["repair_id"])
    return found


def _append_missing(directory: Path, by: str, at: float) -> None:
    path = directory / "events.jsonl"
    data = path.read_bytes() if path.is_file() else b""
    if data and not data.endswith(b"\n"):
        return
    log = load_bytes(data)
    if log.invalid_seq is not None or log.full:
        return
    known = _recorded(log.events)
    pending = []
    for torn_path in _torn_files(directory):
        rid = torn_path.name[len("events.torn-") :]
        if rid in known:
            continue
        blob = torn_path.read_bytes()
        offset_text, _, digest_prefix = rid.partition("-")
        if not offset_text.isdigit() or sha256_bytes(blob)[:16] != digest_prefix:
            continue
        pending.append((int(offset_text), rid, blob))
    for _offset, rid, blob in sorted(pending):
        fresh = load_bytes(path.read_bytes())
        if fresh.invalid_seq is not None or fresh.full:
            return
        obj = seal(
            {
                "type": "tail_repaired",
                "repair_id": rid,
                "bytes": len(blob),
                "sha256": sha256_bytes(blob),
            },
            fresh,
            by,
            at,
        )
        append_sealed(path, obj)


def repair_torn_tail(directory: Path, *, by: str = "coordinator", at: float | None = None) -> str | None:
    """Save, truncate, then record. Idempotent at each crash point.

    Returns the repair id when this call found a torn tail, else None.
    ``at`` defaults to 0 when the caller has no clock sample; the command
    path passes the same clock reading it uses for the event it is about to write.
    """
    if at is None:
        at = 0
    path = directory / "events.jsonl"
    if not path.is_file():
        return None
    data = path.read_bytes()
    rid = None
    just_truncated = False
    if data and not data.endswith(b"\n"):
        cut = data.rfind(b"\n")
        offset = 0 if cut < 0 else cut + 1
        torn = data[offset:]
        rid = repair_id(offset, torn)
        dest = directory / f"events.torn-{rid}"
        if not dest.exists():
            publish(dest, torn)
        fd = os.open(path, os.O_RDWR)
        try:
            os.ftruncate(fd, offset)
            fullsync(fd)
        finally:
            os.close(fd)
        fsync_dir(directory)
        just_truncated = True
    if just_truncated or _prefix_valid(path):
        _append_missing(directory, by, at)
    return rid


def _prefix_valid(path: Path) -> bool:
    if not path.is_file():
        return True
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        return False
    return load_bytes(data).invalid_seq is None
