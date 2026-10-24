"""Removing what the checks passed (disk-guard, W-31 4.6 S1; review 539 F4, review 543 A2,
review 544 A1, A2).

Under the machine lock each root is renamed aside through a handle on its parent, after
checking that the path still leads to the same directories (device and inode) and after a
journal entry records the rename. It is then checked again in full, and that second check's
inventory (every entry it accepted, with device, inode, type and, for files, size and
mtime_ns; every directory's listing) is all the removal may touch. Removal goes through
handles opened without following links: it first compares the whole live tree with the
inventory, and removes nothing if anything is new, missing, replaced or changed (the root is
renamed back); while removing, every entry is compared again and the first difference
stops it. It never removes an entry it did not check, and never falls back to deleting what
a directory holds now.

A stop during removal leaves a cache partly removed: the entries already removed were
checked cache entries, which is acceptable for a cache; what is left stays under the
quarantine name with its journal entry, reported "partly removed, stopped: <entry> ...",
and the new material stays where it was put.
"""

from __future__ import annotations

import os
import stat
import time
from typing import Callable, List, Optional, Tuple

from disk_guard_base import Chain, Config, Ident, O_DIR, Problem, QUARANTINE, _join, gib, ident, open_dir_at, sig, split_rel
from disk_guard_items import Item, check_git_for, original_name
from disk_guard_layout import Walker, validate
from disk_guard_roots import OpenFiles, check_git, check_original, check_policy
from disk_guard_state import journal_drop, journal_write

# Test seams: called with the items about to be renamed; with the staged items after the
# renames, before the second check; with one item after its second check (Git and lsof
# included), right before its removal; and after each entry removed.
between_check_and_rename: Optional[Callable[[List[Item]], None]] = None
between_check_and_delete: Optional[Callable[[list], None]] = None
between_recheck_and_remove: Optional[Callable[[Item, int, str, str], None]] = None
during_removal: Optional[Callable[[str], None]] = None
BATCH = 64  # staged roots hold one directory handle each until removed
# Removed last, so a root a stop leaves behind is still recognisably the same cache.
MARKERS = {"README", "cache", "_cacache"}

Staged = Tuple[int, str, str, Optional[str]]  # parent handle, name, quarantine name, journal file


class Stop(Exception):
    def __init__(self, entry: str, why: str) -> None:
        super().__init__(f"{entry} {why}")
        self.entry, self.why, self.removed = entry, why, 0


def _check(fd: int, rel: str, w: Walker, n: str) -> os.stat_result:
    crel = _join(rel, n)
    want = w.inv.get(crel)
    if want is None:
        raise Stop(crel, "is new")
    try:
        st = os.stat(n, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        raise Stop(crel, "is missing")
    except OSError as e:
        raise Stop(crel, f"cannot be read ({e.strerror or e})")
    if sig(st) != want:
        raise Stop(crel, "was replaced or changed")
    return st


def _names(fd: int, rel: str, w: Walker) -> List[str]:
    """This directory's names, which must be exactly those the check read, in removal order."""
    if rel not in w.listed:
        raise Stop(rel or ".", "was not read by the check")
    try:
        now = set(os.listdir(fd))
    except OSError as e:
        raise Stop(rel or ".", f"cannot be listed ({e.strerror or e})")
    want = set(w.listed[rel])
    if now != want:
        extra, gone = sorted(now - want), sorted(want - now)
        raise Stop(_join(rel, extra[0]), "is new") if extra else Stop(_join(rel, gone[0]), "is missing")
    return sorted(want, key=lambda n: (rel == "" and n in MARKERS, n))


def _open_checked(fd: int, n: str, crel: str, st: os.stat_result) -> int:
    try:
        cfd = os.open(n, O_DIR, dir_fd=fd)
    except OSError as e:
        raise Stop(crel, f"cannot be opened ({e.strerror or e})")
    if ident(os.fstat(cfd)) != ident(st):
        os.close(cfd)
        raise Stop(crel, "was replaced")
    return cfd


def _compare(fd: int, rel: str, w: Walker) -> None:
    for n in _names(fd, rel, w):
        st = _check(fd, rel, w, n)
        if stat.S_ISDIR(st.st_mode):
            cfd = _open_checked(fd, n, _join(rel, n), st)
            try:
                _compare(cfd, _join(rel, n), w)
            finally:
                os.close(cfd)


def _remove(fd: int, rel: str, w: Walker, done: List[int]) -> None:
    st = os.fstat(fd)
    if (st.st_mode & stat.S_IRWXU) != stat.S_IRWXU:
        try:
            os.fchmod(fd, stat.S_IMODE(st.st_mode) | stat.S_IRWXU)  # Go's module dirs are 0555
        except OSError as e:
            raise Stop(rel or ".", f"cannot be made writable ({e.strerror or e})")
    for n in _names(fd, rel, w):
        crel = _join(rel, n)
        est = _check(fd, rel, w, n)
        try:
            if stat.S_ISDIR(est.st_mode):
                cfd = _open_checked(fd, n, crel, est)
                try:
                    _remove(cfd, crel, w, done)
                finally:
                    os.close(cfd)
                os.rmdir(n, dir_fd=fd)  # fails if anything appeared in it meanwhile
            else:
                os.unlink(n, dir_fd=fd)
        except OSError as e:
            raise Stop(crel, f"could not be removed ({e.strerror or e})")
        done[0] += 1
        if during_removal is not None:
            during_removal(crel)


def remove_checked(parent_fd: int, q: str, w: Walker) -> None:
    """Remove exactly the inventory of the second check, or stop at the first difference."""
    done = [0]
    try:
        fd = os.open(q, O_DIR, dir_fd=parent_fd)
    except OSError as e:
        raise Stop(".", f"cannot be opened ({e.strerror or e})")
    try:
        if ident(os.fstat(fd)) != w.root_id:
            raise Stop(".", "was replaced")
        _compare(fd, "", w)
        try:
            _remove(fd, "", w, done)
        except Stop as s:
            s.removed = done[0]
            raise
    finally:
        os.close(fd)
    try:
        os.rmdir(q, dir_fd=parent_fd)
    except OSError as e:
        s = Stop(".", f"could not be removed ({e.strerror or e})")
        s.removed = done[0]
        raise s


def _restore_at(parent_fd: int, name: str, q: str) -> Tuple[str, bool]:
    if q == name:
        return "", False
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        return f"; left as {q} because {name} exists again", False
    except FileNotFoundError:
        pass
    except OSError as e:
        return f"; left as {q}: {e.strerror or e}", False
    try:
        os.rename(q, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
    except OSError as e:
        return f"; left as {q}: rename back failed ({e.strerror or e})", False
    return "; renamed back", True


def _same_path(aw_fd: int, parent: str, it: Item) -> Chain:
    """The parent's chain, opened again from AGENT_WORK; the caller closes it."""
    ch = Chain(aw_fd, parent)
    if ch.ids != it.ids[:-1]:
        ch.close()
        raise Problem("path-changed", f"{parent or '.'} no longer leads to the directories first checked")
    return ch


def stage(cfg: Config, aw_fd: int, run_id: str, it: Item) -> Optional[Staged]:
    """Rename the root aside through its parent's handle, journal first."""
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
            if it.leftover:
                return os.dup(ch.fd), name, name, str((it.journal or {}).get("file") or "") or None
            q = name + QUARANTINE + run_id
            try:
                jfile = journal_write(cfg, run_id, it.path, _join(parent, q), it.ids[-1])
            except OSError as e:
                raise Problem("journal-write-failed", f"{e.strerror or e}: not renamed")
            try:
                os.rename(name, q, src_dir_fd=ch.fd, dst_dir_fd=ch.fd)
            except OSError as e:
                journal_drop(jfile)
                raise Problem("rename-failed", e.strerror or str(e))
            if ident(os.stat(q, dir_fd=ch.fd, follow_symlinks=False)) != it.ids[-1]:
                msg, back = _restore_at(ch.fd, name, q)
                if back:
                    journal_drop(jfile)
                raise Problem("path-changed", "another directory took its place during the rename" + msg)
            return os.dup(ch.fd), name, q, jfile
    except Problem as p:
        it.keep(p)
        return None


def _undo(it: Item, staged: Staged) -> str:
    """After a failed check: rename back (and drop the journal entry) unless it is a leftover."""
    pfd, name, q, jfile = staged
    if it.leftover:
        return ""
    msg, back = _restore_at(pfd, name, q)
    if back:
        journal_drop(jfile)
    return msg


def recheck_and_remove(cfg: Config, aw_fd: int, aw_id: Ident, it: Item, staged: Staged, lsof: OpenFiles, now: float) -> None:
    pfd, name, q, jfile = staged
    assert it.entry is not None and it.kind is not None
    parent, _ = split_rel(it.path)
    orig = os.path.join(cfg.agent_work, _join(parent, split_rel(original_name(it))[1]))
    here = os.path.join(cfg.agent_work, _join(parent, q))
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
            check_git(cfg, here, tracked_only=True)
            check_original(cfg, orig)  # nothing tracked, still ignored (review 544 A2)
            unknown = lsof.problem_for(here, orig)
            if unknown:
                raise Problem("open-files-unknown", unknown)
            if lsof.under(here, orig):
                raise Problem("open-files", "a process has a file open under it")
    except Problem as p:
        it.keep(Problem("recheck-" + p.code, p.detail + _undo(it, staged)))
        return
    except OSError as e:
        it.keep(Problem("recheck-unreadable", f"{e}{_undo(it, staged)}"))
        return
    if between_recheck_and_remove is not None:
        between_recheck_and_remove(it, pfd, name, q)
    try:
        remove_checked(pfd, q, w)
    except Stop as s:
        entry = w.show(s.entry)
        if s.removed == 0:
            it.keep(Problem("stopped-before-removal", f"{entry} {s.why} since the second check: nothing removed{_undo(it, staged)}"))
        else:
            it.keep(Problem("partly-removed", f"partly removed, stopped: {entry} {s.why}; {s.removed} checked entries removed, "
                                              f"the rest stays at {_join(parent, q)} with its journal entry"))
        return
    journal_drop(jfile)
    if it.action == "prune":
        it.action, it.detail = "pruned", f"{gib(w.bytes)} over the cap: the whole root removed"
    else:
        it.action = "deleted"


def apply_items(cfg: Config, aw_fd: int, run_id: str, items: List[Item]) -> None:
    todo = [it for it in items if it.action in ("delete", "prune")]
    if todo and between_check_and_rename is not None:
        between_check_and_rename(todo)
    aw_id = ident(os.fstat(aw_fd))
    for start in range(0, len(todo), BATCH):
        staged: List[Tuple[Item, Staged]] = []
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
