"""Removing what the first check passed (disk-guard, W-31 4.6 S1; review 539 F4, review
543 A2): under the machine lock, each root is renamed aside through a handle on its parent
(after checking the path still leads to the same directories, by device and inode), checked
again in full, and removed through handles opened without following links. Nothing after
the first check trusts a path: a parent swapped for a symlink, or a directory swapped for
another, stops the removal and the root stays (renamed back when it can be).
"""

from __future__ import annotations

import fcntl
import json
import os
import socket
import stat
import time
from typing import Callable, Dict, List, Optional, Tuple

from disk_guard_base import Chain, Config, Ident, O_DIR, Problem, QUARANTINE, _join, gib, ident, now_utc, open_dir_at, split_rel
from disk_guard_items import Item, check_git_for, original_name
from disk_guard_layout import validate
from disk_guard_roots import OpenFiles, check_git, check_policy

# Test seams (review 539 F4, 543 A2): called with the items about to be renamed, and with
# the staged items after the renames and before the second check, so a test can play
# another session changing the tree in between.
between_check_and_rename: Optional[Callable[[List[Item]], None]] = None
between_check_and_delete: Optional[Callable[[list], None]] = None
BATCH = 64  # staged roots hold one directory handle each until removed


def remove_at(parent_fd: int, name: str, expect: Ident, dev: int) -> None:
    fd = os.open(name, O_DIR, dir_fd=parent_fd)
    try:
        if ident(os.fstat(fd)) != expect:
            raise OSError(f"{name} is not the directory checked")
        _empty(fd, dev)
    finally:
        os.close(fd)
    os.rmdir(name, dir_fd=parent_fd)


def _empty(fd: int, dev: int) -> None:
    st = os.fstat(fd)
    if st.st_dev != dev:
        raise OSError("another filesystem")
    if (st.st_mode & stat.S_IRWXU) != stat.S_IRWXU:
        os.fchmod(fd, stat.S_IMODE(st.st_mode) | stat.S_IRWXU)  # Go's module dirs are 0555
    for n in os.listdir(fd):
        est = os.stat(n, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISDIR(est.st_mode):
            cfd = os.open(n, O_DIR, dir_fd=fd)
            try:
                if ident(os.fstat(cfd)) != ident(est):
                    raise OSError(f"{n} changed while being removed")
                _empty(cfd, dev)
            finally:
                os.close(cfd)
            os.rmdir(n, dir_fd=fd)
        else:
            os.unlink(n, dir_fd=fd)


def _restore_at(parent_fd: int, name: str, q: str) -> str:
    if q == name:
        return ""
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        return f"; left as {q} because {name} exists again"
    except FileNotFoundError:
        pass
    except OSError as e:
        return f"; left as {q}: {e.strerror or e}"
    try:
        os.rename(q, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
    except OSError as e:
        return f"; left as {q}: rename back failed ({e.strerror or e})"
    return "; renamed back"


def _same_path(aw_fd: int, parent: str, it: Item) -> Chain:
    """The parent's chain, opened again from AGENT_WORK; the caller closes it."""
    ch = Chain(aw_fd, parent)
    if ch.ids != it.ids[:-1]:
        ch.close()
        raise Problem("path-changed", f"{parent or '.'} no longer leads to the directories first checked")
    return ch


def stage(cfg: Config, aw_fd: int, run_id: str, it: Item) -> Optional[Tuple[int, str, str]]:
    """Rename the root aside through its parent's handle: (parent handle, name, new name)."""
    parent, name = split_rel(it.path)
    try:
        with _same_path(aw_fd, parent, it) as ch:
            try:
                st = os.stat(name, dir_fd=ch.fd, follow_symlinks=False)
            except OSError as e:
                raise Problem("path-changed", f"{it.path}: {e.strerror or e}")
            if not stat.S_ISDIR(st.st_mode) or ident(st) != it.ids[-1]:
                raise Problem("path-changed", f"{it.path} is not the directory first checked")
            check_git_for(cfg, it)  # in full, on the name it has now
            q = name if it.leftover else name + QUARANTINE + run_id
            if q != name:
                try:
                    os.rename(name, q, src_dir_fd=ch.fd, dst_dir_fd=ch.fd)
                except OSError as e:
                    raise Problem("rename-failed", e.strerror or str(e))
                if ident(os.stat(q, dir_fd=ch.fd, follow_symlinks=False)) != it.ids[-1]:
                    raise Problem("path-changed", "another directory took its place during the rename" + _restore_at(ch.fd, name, q))
            return os.dup(ch.fd), name, q
    except Problem as p:
        it.keep(p)
        return None


def recheck_and_remove(cfg: Config, aw_fd: int, aw_id: Ident, it: Item, staged: Tuple[int, str, str], lsof: OpenFiles, now: float) -> None:
    pfd, name, q = staged
    assert it.entry is not None and it.kind is not None
    parent, _ = split_rel(it.path)
    orig_name = split_rel(original_name(it))[1]
    try:
        rfd = open_dir_at(pfd, q, _join(parent, q))
        try:
            if ident(os.fstat(rfd)) != it.ids[-1]:
                raise Problem("path-changed", f"{_join(parent, q)} is not the directory first checked")
            w = validate(rfd, it.kind)
        finally:
            os.close(rfd)
        # The path must still lead here: Git and lsof only know paths.
        if ident(os.stat(cfg.agent_work)) != aw_id:
            raise Problem("path-changed", "AGENT_WORK is not the directory the sweep opened")
        with _same_path(aw_fd, parent, it) as ch:
            if ident(os.fstat(ch.fd)) != ident(os.fstat(pfd)):
                raise Problem("path-changed", f"{parent or '.'} is not the parent renamed in")
            owner_fd = ch.fds[0] if ch.fds else None
            check_policy(cfg, it.entry, owner_fd, it.path.split("/", 1)[0], w, now)
            check_git(cfg, os.path.join(cfg.agent_work, _join(parent, orig_name)), tracked_only=True)
            if not lsof.ok:
                raise Problem("open-files-unknown", lsof.error)
            if lsof.under(os.path.join(cfg.agent_work, _join(parent, q)), os.path.join(cfg.agent_work, _join(parent, orig_name))):
                raise Problem("open-files", "a process has a file open under it")
    except Problem as p:
        back = "" if it.leftover else _restore_at(pfd, name, q)
        it.keep(Problem("recheck-" + p.code, p.detail + back))
        return
    except OSError as e:
        back = "" if it.leftover else _restore_at(pfd, name, q)
        it.keep(Problem("recheck-unreadable", f"{e}{back}"))
        return
    try:
        remove_at(pfd, q, it.ids[-1], w.dev)
    except OSError as e:
        it.keep(Problem("delete-error", f"{e}; what is left stays at {_join(parent, q)}"))
        return
    if it.action == "prune":
        it.action, it.detail = "pruned", f"{gib(w.bytes)} over the cap: removed whole (as go clean -cache / -modcache, npm cache clean)"
    else:
        it.action = "deleted"


def apply_items(cfg: Config, aw_fd: int, run_id: str, items: List[Item]) -> None:
    todo = [it for it in items if it.action in ("delete", "prune")]
    if todo and between_check_and_rename is not None:
        between_check_and_rename(todo)
    aw_id = ident(os.fstat(aw_fd))
    for start in range(0, len(todo), BATCH):
        staged: List[Tuple[Item, Tuple[int, str, str]]] = []
        for it in todo[start:start + BATCH]:
            s = stage(cfg, aw_fd, run_id, it)
            if s is not None:
                staged.append((it, s))
        try:
            if staged and between_check_and_delete is not None:
                between_check_and_delete([(it, s[0], s[1], s[2]) for it, s in staged])
            lsof = OpenFiles(cfg)
            now = time.time()
            for it, s in staged:
                recheck_and_remove(cfg, aw_fd, aw_id, it, s, lsof, now)
        finally:
            for _, s in staged:
                os.close(s[0])


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
