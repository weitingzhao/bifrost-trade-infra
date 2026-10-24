"""Removing what the checks passed (disk-guard, W-31 4.6 S1; review 539 F4, review 543 A2,
review 544 A1, A2, review 547 A1, C1).

Under the machine lock each root is renamed aside through a handle on its parent, after
checking that the path still leads to the same directories (device and inode) and after a
journal entry records the rename. It is then checked again in full (layout, end evidence,
Git on the original path, open files); that second check's inventory is written beside the
journal entry, and removal touches only what the inventory holds (disk_guard_inventory.py):
the whole live tree is compared with it first, and nothing is removed if anything is new,
missing, replaced or changed (the root is renamed back); while removing, the first
difference stops it. A stop part way leaves a cache partly removed: the entries already
gone were checked cache entries, which is acceptable for a cache; what is left stays under
the quarantine name with its journal entry and inventory, reported "partly removed,
stopped: ...", and the new material stays where it was put. The next sweep finishes a
removal that stopped or died part way when the remaining entries match the inventory and
the other checks (Git, open files, exclusions, journal identity) pass. A leftover's
inventory is read when its root is classified and again, per root, when it is removed; it is
not held in memory between the two.

Threat model (review 547 A1): this guards against accidental loss, not against a process
working against the sweep. The sweeper runs as the same user as every producer; such a
process could delete the material itself. What is protected: nothing is removed unless the
root has left its registered name, lsof saw no open file in it, and every entry removed
matched the second check's inventory at its last comparison. What is not: a name swapped
for other material after its last comparison and before the name operation (unlink, or
rmdir, which for a directory comes after everything under it is removed), and a directory
moved out of the quarantine while its entries are being removed (the open handle follows
it).
"""

from __future__ import annotations

import os
import stat
import time
from typing import Callable, List, Optional, Tuple

from disk_guard_base import Chain, Config, Ident, Problem, QUARANTINE, _join, gib, ident, open_dir_at, split_rel
from disk_guard_inventory import Inventory, Stop, compare_tree, remove_checked
from disk_guard_items import Item, check_git_for, is_leftover, original_name
from disk_guard_layout import Walker, validate
from disk_guard_roots import OpenFiles, check_git, check_original, check_policy
from disk_guard_state import chmod_recorder, inventory_load, inventory_write, journal_drop, journal_write

# Test seams: called with the items about to be renamed; with the staged items after the
# renames, before the second check; with one item after its second check (Git and lsof
# included), right before its removal; and after each entry removed.
between_check_and_rename: Optional[Callable[[List[Item]], None]] = None
between_check_and_delete: Optional[Callable[[list], None]] = None
between_recheck_and_remove: Optional[Callable[[Item, int, str, str], None]] = None
after_inventory_written: Optional[Callable[[Item], None]] = None
during_removal: Optional[Callable[[str], None]] = None
BATCH = 64  # staged roots hold one directory handle each until removed

Staged = Tuple[int, str, str, Optional[str]]  # parent handle, name, quarantine name, journal file


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
            except FileNotFoundError:
                raise Problem("gone", f"{it.path} is no longer there (another cleaner, or its owner, removed it)")
            except OSError as e:
                raise Problem("path-changed", f"{it.path}: {e.strerror or e}")
            if not stat.S_ISDIR(st.st_mode) or ident(st) != it.ids[-1]:
                raise Problem("path-changed", f"{it.path} is not the directory first checked")
            check_git_for(cfg, it)  # in full, on the name it has now
            if is_leftover(it):
                jfile = (it.journal or {}).get("file")
                return os.dup(ch.fd), name, name, str(jfile) if jfile is not None else None
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
    if is_leftover(it):
        return ""
    msg, back = _restore_at(pfd, name, q)
    if back:
        journal_drop(jfile)
    return msg


def _second_check(it: Item, rfd: int, jfile: Optional[str]) -> Tuple[Inventory, int, Optional[Walker]]:
    """(inventory to remove, bytes, walker for the end evidence): a full layout check, or for
    a stopped removal the comparison with its own inventory, read again from its file."""
    if it.resuming:
        try:
            inv = inventory_load(jfile) if jfile else None
        except ValueError as e:
            raise Problem("journal-inventory-unusable", str(e))
        if inv is None:
            raise Problem("journal-inventory-unusable", "the inventory is gone")
        if it.kind == "go-build-chain":
            inv.redact = True  # by the registry's kind, not by what the file says
        if inv.root_id != it.ids[-1]:
            raise Problem("unrecorded-quarantine-name", "the inventory records another directory (device, inode)")
        try:
            compare_tree(rfd, inv)
        except Stop as s:
            raise Problem("changed-since-stopped", f"{inv.show(s.entry)} {s.why}")
        return inv, it.bytes, None
    assert it.kind is not None
    w = validate(rfd, it.kind)
    return w.inventory(), w.bytes, w


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
            inv, size, w = _second_check(it, rfd, jfile)
        finally:
            os.close(rfd)
        # The path must still lead here: Git and lsof only know paths.
        if ident(os.stat(cfg.agent_work)) != aw_id:
            raise Problem("path-changed", "AGENT_WORK is not the directory the sweep opened")
        with _same_path(aw_fd, parent, it) as ch:
            if ident(os.fstat(ch.fd)) != ident(os.fstat(pfd)):
                raise Problem("path-changed", f"{parent or '.'} is not the parent renamed in")
            if w is not None:  # a stopped removal's end evidence was its first sweep's
                check_policy(cfg, it.entry, ch.fds[0] if ch.fds else None, it.path.split("/", 1)[0], w, now)
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
    if jfile is None:
        it.keep(Problem("journal-write-failed", f"no journal entry: nothing removed{_undo(it, staged)}"))
        return
    if not it.resuming:
        # written before the first unlink, so a sweep that dies part way can be finished
        try:
            inventory_write(jfile, inv)
        except OSError as e:
            it.keep(Problem("inventory-write-failed", f"{e}: nothing removed{_undo(it, staged)}"))
            return
        if after_inventory_written is not None:
            after_inventory_written(it)
    try:
        remove_checked(pfd, q, inv, during_removal, chmod_recorder(jfile))
    except Stop as s:
        entry = inv.show(s.entry)
        if s.removed == 0:
            it.keep(Problem("stopped-before-removal", f"{entry} {s.why} since the second check: nothing removed{_undo(it, staged)}"))
        else:
            it.keep(Problem("partly-removed", f"partly removed, stopped: {entry} {s.why}; {s.removed} checked entries removed, "
                                              f"the rest stays at {_join(parent, q)} with its journal entry"))
        return
    journal_drop(jfile)
    if it.action == "prune":
        it.action = "pruned"
        it.detail = ("finished the removal a stopped sweep began (what was left may be under the cap)" if it.resuming
                     else f"{gib(size)} over the cap: the whole root removed")
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
