"""The sweep's own state, kept outside the trees it checks (disk-guard, W-31 4.6 S1): the
machine lock, and the rename journal (review 544 A2).

Before a root is renamed to <name>.lifecycle-del-<run>, a journal entry records the original
path, the quarantine path, the root's (device, inode) and the run id; the entry goes once the
root is removed or renamed back. Only a directory that a journal entry names, with the same
original path and identity, is a leftover a later sweep may finish. A directory merely named
like a quarantine is reported, never removed.

Before the first entry of a root is removed, the inventory the second check accepted is
written beside its journal entry (<entry>.inventory); before the sweeper changes a
directory's mode to empty it, it appends that directory's identity and new mode to
<entry>.chmods (review 549 A1). A sweep that died part way leaves all three, and the next
sweep finishes the removal through the inventory when the remaining entries and the other
checks pass (review 547 C1). These files are trusted state: they are the sweeper's own,
written by the same user as every producer, and nothing authenticates them (the threat model
is in disk_guard_apply.py).

Files are created 0600 and the journal directory 0700 here, whatever the entry point's umask
(review 549 C1: a chain's directory names can hold a whole command line); a journal directory
owned by someone else, or not a directory, is refused. Files and the directory are fsynced,
so an entry survives a crash of the process; power loss is not tested.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import socket
import stat
from typing import Dict, List, Optional, Tuple

from disk_guard_base import Config, Ident, now_utc
from disk_guard_inventory import Inventory

JOURNAL_DIR = "lifecycle-journal"
Journal = Dict[str, Dict[str, object]]
# Bounds a signature field must lie in (review 549 C2): st_dev, st_ino, st_mode, size,
# mtime_ns, ctime_ns.
SIG_BOUNDS = ((0, 2 ** 64), (0, 2 ** 64), (0, 2 ** 32), (0, 2 ** 63), (-(2 ** 63), 2 ** 63), (-(2 ** 63), 2 ** 63))


def journal_dir(cfg: Config) -> str:
    return os.path.join(cfg.status_dir, JOURNAL_DIR)


def _private_dir(d: str) -> None:
    """d exists, is a directory of this user and is 0700. Raises OSError otherwise."""
    try:
        os.mkdir(d, 0o700)
    except FileExistsError:
        pass
    st = os.lstat(d)
    if not stat.S_ISDIR(st.st_mode):
        raise OSError(f"{d} is not a directory")
    if st.st_uid != os.geteuid():
        raise OSError(f"{d} belongs to uid {st.st_uid}, not this user")
    if stat.S_IMODE(st.st_mode) != 0o700:
        os.chmod(d, 0o700)


def _valid_entry(rec: object) -> bool:
    if not isinstance(rec, dict):
        return False
    root = rec.get("root")
    return (isinstance(rec.get("quarantine"), str) and isinstance(rec.get("original"), str)
            and isinstance(root, list) and len(root) == 2 and all(_int_in(x, b) for x, b in zip(root, SIG_BOUNDS)))


def _int_in(x: object, bounds: Tuple[int, int]) -> bool:
    return type(x) is int and bounds[0] <= x < bounds[1]  # bool and float are not ints here


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
        if not _valid_entry(rec):
            notes.append(f"journal {n}: malformed: ignored")
            continue
        q = str(rec["quarantine"])
        if not os.path.lexists(os.path.join(cfg.agent_work, q)):
            journal_drop(p)
            notes.append(f"journal {n}: {q} is gone: entry dropped")
            continue
        rec["file"] = p
        out[q] = rec
    return out, notes


def _write_private(p: str, data: object) -> None:
    """Write p as JSON: a 0600 temp file made with O_EXCL, fsynced, renamed over p, and the
    directory fsynced."""
    tmp = f"{p}.tmp-{os.getpid()}"
    try:
        os.unlink(tmp)  # a temp file a killed run of this pid left
    except FileNotFoundError:
        pass
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = -1
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
    finally:
        if fd >= 0:
            os.close(fd)
    os.replace(tmp, p)
    _fsync_dir(os.path.dirname(p))


def _fsync_dir(d: str) -> None:
    dfd = os.open(d, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def journal_write(cfg: Config, run_id: str, original: str, quarantine: str, root: Ident) -> str:
    os.makedirs(cfg.status_dir, exist_ok=True)
    d = journal_dir(cfg)
    _private_dir(d)
    p = os.path.join(d, f"{run_id}-{hashlib.sha1(quarantine.encode()).hexdigest()[:16]}.json")
    _write_private(p, {"run_id": run_id, "original": original, "quarantine": quarantine, "root": list(root), "written_at": now_utc()})
    return p


def journal_open(cfg: Config) -> Tuple[Optional[int], int]:
    """(entries still open, bad .json files) at the end of a run; open is None when the
    directory cannot be read."""
    d = journal_dir(cfg)
    try:
        names = [n for n in os.listdir(d) if n.endswith(".json")]
    except FileNotFoundError:
        return 0, 0
    except OSError:
        return None, 0
    good = bad = 0
    for n in names:
        try:
            with open(os.path.join(d, n), encoding="utf-8") as f:
                ok = _valid_entry(json.load(f))
        except (OSError, ValueError):
            ok = False
        good, bad = (good + 1, bad) if ok else (good, bad + 1)
    return good, bad


def journal_drop(path: Optional[str]) -> None:
    if path:
        for p in (path + ".chmods", path + ".inventory", path):
            try:
                os.unlink(p)
            except OSError:
                pass


def inventory_write(journal_file: str, inv: Inventory) -> None:
    _write_private(journal_file + ".inventory", {
        "root": list(inv.root_id), "redact": inv.redact, "leaf": inv.leaf,
        "inv": {k: list(v) for k, v in inv.inv.items()}, "listed": inv.listed})


def chmod_recorder(journal_file: str) -> "ChmodLog":
    return ChmodLog(journal_file + ".chmods")


class ChmodLog:
    """Before the sweeper changes a directory's mode, one line: path, device, inode, new mode;
    fsynced before the change is made (review 549 A1)."""

    def __init__(self, path: str) -> None:
        self.path = path

    def __call__(self, rel: str, dev: int, ino: int, mode: int) -> None:
        line = json.dumps([rel, dev, ino, mode]) + "\n"
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), 0o600)
        try:
            os.fchmod(fd, 0o600)
            os.write(fd, line.encode())
            os.fsync(fd)
        finally:
            os.close(fd)


def _sig(v: object) -> Tuple[int, ...]:
    if not (isinstance(v, list) and len(v) == 6 and all(_int_in(x, b) for x, b in zip(v, SIG_BOUNDS))):
        raise ValueError("a signature is not six integers in range")
    return tuple(v)  # type: ignore[arg-type]


def inventory_load(journal_file: str) -> Optional[Inventory]:
    """None when there is no inventory (the sweep died before removing anything); raises
    ValueError when there is one that cannot be used. Every field is checked as written, with
    no type coercion (review 549 C2)."""
    try:
        with open(journal_file + ".inventory", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except OSError as e:
        raise ValueError(f"unreadable: {e.strerror or e}")
    except ValueError as e:
        raise ValueError(f"not JSON: {e}")
    if not isinstance(data, dict):
        raise ValueError("not an inventory")
    inv, listed, root, redact, leaf = data.get("inv"), data.get("listed"), data.get("root"), data.get("redact"), data.get("leaf")
    if not (isinstance(inv, dict) and isinstance(listed, dict)):
        raise ValueError("inv or listed is not an object")
    if not (isinstance(root, list) and len(root) == 2 and all(_int_in(x, b) for x, b in zip(root, SIG_BOUNDS))):
        raise ValueError("root is not two integers in range")
    if type(redact) is not bool:
        raise ValueError("redact is not true or false")
    if not (leaf is None or isinstance(leaf, str)):
        raise ValueError("leaf is not a string or null")
    sigs = {k: _sig(v) for k, v in inv.items()}
    for k, v in listed.items():
        if not (isinstance(v, list) and all(isinstance(n, str) for n in v)):
            raise ValueError(f"the listing of {k!r} is not a list of names")
    out = Inventory(sigs, {k: list(v) for k, v in listed.items()}, (root[0], root[1]), redact, leaf, swept=True)  # type: ignore[arg-type]
    out.chmods = _chmods_load(journal_file + ".chmods", sigs)
    return out


def _chmods_load(path: str, sigs: Dict[str, Tuple[int, ...]]) -> Dict[str, int]:
    """The modes the sweeper recorded before changing them, by path; each must name an
    inventory directory with the same identity."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except FileNotFoundError:
        return {}
    except OSError as e:
        raise ValueError(f"chmod record unreadable: {e.strerror or e}")
    out: Dict[str, int] = {}
    for line in lines:
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            raise ValueError("a chmod record is not JSON")
        if not (isinstance(rec, list) and len(rec) == 4 and isinstance(rec[0], str)
                and _int_in(rec[1], SIG_BOUNDS[0]) and _int_in(rec[2], SIG_BOUNDS[1]) and _int_in(rec[3], SIG_BOUNDS[2])):
            raise ValueError("a chmod record is malformed")
        want = sigs.get(rec[0])
        if want is None or (want[0], want[1]) != (rec[1], rec[2]) or not stat.S_ISDIR(want[2]):
            raise ValueError(f"a chmod record names no directory of the inventory: {rec[0]!r}")
        out[rec[0]] = rec[3]
    return out


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
