"""Torn-tail repair with a stable repair id.

A torn tail is the byte range after the last newline. A newline-terminated
line whose digest does not match is corruption and is never removed.
``repair_id`` is ``<offset>-<first 16 hex of sha256(torn bytes)>``.
"""

from __future__ import annotations

import os
from pathlib import Path

from events import append_obj, load_bytes, sha256_bytes
from fsutil import fsync_dir, fullsync, publish
from query import repair_ids as recorded_repairs


def repair_id(offset: int, torn: bytes) -> str:
    return f"{offset}-{sha256_bytes(torn)[:16]}"


def _torn_files(lane_dir: Path) -> list[Path]:
    found = []
    for path in lane_dir.iterdir():
        name = path.name
        if path.is_file() and name.startswith("events.torn-") and ".tmp-" not in name:
            found.append(path)
    return sorted(found, key=lambda item: item.name)


def _append_missing(lane_dir: Path) -> None:
    path = lane_dir / "events.jsonl"
    data = path.read_bytes() if path.is_file() else b""
    if data and not data.endswith(b"\n"):
        return
    log = load_bytes(data)
    if log.invalid_seq is not None:
        return
    known = recorded_repairs(log.events)
    pending = []
    for torn_path in _torn_files(lane_dir):
        rid = torn_path.name[len("events.torn-") :]
        if rid in known:
            continue
        blob = torn_path.read_bytes()
        offset_text, _, digest_prefix = rid.partition("-")
        if not offset_text.isdigit() or sha256_bytes(blob)[:16] != digest_prefix:
            continue
        pending.append((int(offset_text), rid, blob))
    for _offset, rid, blob in sorted(pending):
        append_obj(
            lane_dir,
            {
                "type": "tail_repaired",
                "repair_id": rid,
                "bytes": len(blob),
                "sha256": sha256_bytes(blob),
            },
        )


def repair_torn_tail(lane_dir: Path) -> str | None:
    """Save, truncate, then record. Idempotent at each crash point. Returns repair_id or None."""
    path = lane_dir / "events.jsonl"
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
        dest = lane_dir / f"events.torn-{rid}"
        if not dest.exists():
            publish(dest, torn)
        fd = os.open(path, os.O_RDWR)
        try:
            os.ftruncate(fd, offset)
            fullsync(fd)
        finally:
            os.close(fd)
        fsync_dir(lane_dir)
        just_truncated = True
    if just_truncated or _prefix_valid(path):
        _append_missing(lane_dir)
    return rid


def _prefix_valid(path: Path) -> bool:
    if not path.is_file():
        return True
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        return False
    return load_bytes(data).invalid_seq is None
