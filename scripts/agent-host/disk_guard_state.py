"""The sweep's own state, kept outside the trees it checks (disk-guard, W-31 4.6 S1): the
machine lock, and the rename journal (review 544 A2).

Before a root is renamed to <name>.lifecycle-del-<run>, a journal entry records the original
path, the quarantine path, the root's (device, inode) and the run id; the entry goes once the
root is removed or renamed back. Only a directory that a journal entry names, with the same
original path and identity, is a leftover a later sweep may finish. A directory merely named
like a quarantine is reported, never removed.

Before the first entry of a root is removed, the inventory the second check accepted is
written beside its journal entry (<entry>.inventory). A sweep that died part way through a
removal leaves both, and the next sweep finishes it through that inventory (review 547 C1).
Files and the journal directory are fsynced, so an entry survives a crash of the process;
power loss is not tested.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import socket
from typing import Dict, List, Optional, Tuple

from disk_guard_base import Config, Ident, now_utc
from disk_guard_inventory import Inventory

JOURNAL_DIR = "lifecycle-journal"
Journal = Dict[str, Dict[str, object]]


def journal_dir(cfg: Config) -> str:
    return os.path.join(cfg.status_dir, JOURNAL_DIR)


def journal_load(cfg: Config) -> Tuple[Journal, List[str]]:
    """Entries by quarantine path. An entry whose quarantine path is gone grants nothing
    and is dropped."""
    d = journal_dir(cfg)
    try:
        names = sorted(os.listdir(d))
    except FileNotFoundError:
        return {}, []
    except OSError as e:
        return {}, [f"journal {d}: {e.strerror or e}: no leftover is finished this run"]
    out: Journal = {}
    notes: List[str] = []
    for n in names:
        if not n.endswith(".json"):
            continue
        p = os.path.join(d, n)
        try:
            with open(p, encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError) as e:
            notes.append(f"journal {n}: unreadable ({e}): ignored")
            continue
        if not isinstance(rec, dict):
            notes.append(f"journal {n}: not a JSON object: ignored")
            continue
        q, orig, root = rec.get("quarantine"), rec.get("original"), rec.get("root")
        if not (isinstance(q, str) and isinstance(orig, str) and isinstance(root, list) and len(root) == 2):
            notes.append(f"journal {n}: malformed: ignored")
            continue
        if not os.path.lexists(os.path.join(cfg.agent_work, q)):
            journal_drop(p)
            notes.append(f"journal {n}: {q} is gone: entry dropped")
            continue
        rec["file"] = p
        out[q] = rec
    return out, notes


def _write_durably(p: str, data: object) -> None:
    tmp = f"{p}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)
    dfd = os.open(os.path.dirname(p), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def journal_write(cfg: Config, run_id: str, original: str, quarantine: str, root: Ident) -> str:
    d = journal_dir(cfg)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{run_id}-{hashlib.sha1(quarantine.encode()).hexdigest()[:16]}.json")
    _write_durably(p, {"run_id": run_id, "original": original, "quarantine": quarantine, "root": list(root), "written_at": now_utc()})
    return p


def journal_open(cfg: Config) -> int:
    """Entries still in the journal (the report's count at the end of a run)."""
    try:
        return sum(1 for n in os.listdir(journal_dir(cfg)) if n.endswith(".json"))
    except OSError:
        return 0


def journal_drop(path: Optional[str]) -> None:
    if path:
        for p in (path + ".inventory", path):
            try:
                os.unlink(p)
            except OSError:
                pass


def inventory_write(journal_file: str, inv: Inventory) -> None:
    _write_durably(journal_file + ".inventory", {
        "root": list(inv.root_id), "redact": inv.redact, "leaf": inv.leaf,
        "inv": {k: list(v) for k, v in inv.inv.items()}, "listed": inv.listed})


def inventory_load(journal_file: str) -> Optional[Inventory]:
    """None when there is no inventory (the sweep died before removing anything); raises
    ValueError when there is one that cannot be used."""
    try:
        with open(journal_file + ".inventory", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except OSError as e:
        raise ValueError(f"unreadable: {e.strerror or e}")
    if not isinstance(data, dict) or not isinstance(data.get("inv"), dict) or not isinstance(data.get("listed"), dict):
        raise ValueError("not an inventory")
    try:
        inv = {str(k): tuple(int(x) for x in v) for k, v in data["inv"].items()}
        listed = {str(k): [str(n) for n in v] for k, v in data["listed"].items()}
        root = tuple(int(x) for x in data["root"])
    except (TypeError, ValueError, KeyError):
        raise ValueError("malformed inventory")
    if len(root) != 2 or any(len(v) != 6 for v in inv.values()):
        raise ValueError("malformed inventory")
    return Inventory(inv, listed, root, bool(data.get("redact")), data.get("leaf"), swept=True)  # type: ignore[arg-type]


class Lock:
    """One sweep per machine: flock on <lock dir>/lock (released by the kernel when the
    holder dies, so there is no stale lock to take over), and <lock dir>/owner saying who."""

    def __init__(self, path: str, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        self.fd: Optional[int] = None

    def owner(self) -> Optional[Dict[str, object]]:
        try:
            with open(os.path.join(self.path, "owner"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def acquire(self) -> Tuple[bool, str]:
        try:
            os.makedirs(self.path, exist_ok=True)
            fd = os.open(os.path.join(self.path, "lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), 0o600)
        except OSError as e:
            return False, f"cannot open {self.path}/lock: {e.strerror or e}"
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            o = self.owner()
            who = f"run {o.get('run_id')} pid {o.get('pid')} on {o.get('host')} since {o.get('started_at')}" if o else "an owner that wrote no record"
            return False, f"another sweep holds {self.path}: {who}"
        self.fd = fd
        rec = {"run_id": self.run_id, "pid": os.getpid(), "host": socket.gethostname(), "started_at": now_utc()}
        try:
            tmp = os.path.join(self.path, f"owner.tmp-{os.getpid()}")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(rec, f)
            os.replace(tmp, os.path.join(self.path, "owner"))
        except OSError as e:
            self.release()
            return False, f"cannot write {self.path}/owner: {e.strerror or e}"
        return True, ""

    def release(self) -> None:
        if self.fd is None:
            return
        o = self.owner()
        if o and o.get("run_id") == self.run_id:
            try:
                os.unlink(os.path.join(self.path, "owner"))
            except OSError:
                pass
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
            self.fd = None
