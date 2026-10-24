"""The sweep's own state, kept outside the trees it checks (disk-guard, W-31 4.6 S1): the
machine lock, and the rename journal (review 544 A2).

Before a root is renamed to <name>.lifecycle-del-<run>, a journal entry records the original
path, the quarantine path, the root's (device, inode) and the run id; the entry goes once the
root is removed or renamed back. Only a directory that a journal entry names, with the same
original path and identity, is a leftover a later sweep may finish. A directory merely named
like a quarantine is reported, never removed.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import socket
from typing import Dict, List, Optional, Tuple

from disk_guard_base import Config, Ident, now_utc

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


def journal_write(cfg: Config, run_id: str, original: str, quarantine: str, root: Ident) -> str:
    d = journal_dir(cfg)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{run_id}-{hashlib.sha1(quarantine.encode()).hexdigest()[:16]}.json")
    rec = {"run_id": run_id, "original": original, "quarantine": quarantine, "root": list(root), "written_at": now_utc()}
    tmp = f"{p}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)
    return p


def journal_drop(path: Optional[str]) -> None:
    if path:
        try:
            os.unlink(path)
        except OSError:
            pass


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
