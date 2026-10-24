"""The inventory of a checked tree, and removal bound to it (disk-guard, W-31 4.6 S1; review
544 A1, review 547 A3, C1).

An inventory is what a full layout check accepted: every entry by path relative to the root,
with its signature (device, inode, whole st_mode; for a file also size, mtime_ns, ctime_ns),
every directory's names, and the root's identity. Removal compares the whole live tree with
it first and removes nothing if anything differs; while removing, it compares every entry
again and stops at the first difference; it never removes an entry the inventory does not
hold. Markers (README, cache, _cacache) go last at every level, so a stopped removal still
looks like the cache it was.

A resumed inventory (swept) belongs to a removal a sweep stopped part way: entries may be
gone, and a directory may carry the u+rwx the sweeper added before emptying it. Nothing may
be new, and every remaining entry must match.
"""

from __future__ import annotations

import os
import stat
from typing import Callable, Dict, List, Optional

from disk_guard_base import Ident, O_DIR, Sig, _join, ident, same_entry, sig

MARKERS = {"README", "cache", "_cacache"}


class Inventory:
    def __init__(self, inv: Dict[str, Sig], listed: Dict[str, List[str]], root_id: Ident,
                 redact: bool = False, leaf: Optional[str] = None, swept: bool = False) -> None:
        self.inv, self.listed, self.root_id = inv, listed, root_id
        self.redact, self.leaf, self.swept = redact, leaf, swept

    def show(self, rel: str) -> str:
        """A chain's directory names can hold a whole command line: name a chain level by
        number only, and the leaf's entries from the leaf down."""
        if not self.redact:
            return rel
        if self.leaf is not None and (rel == self.leaf or rel.startswith(self.leaf + "/")):
            return "<leaf>" + rel[len(self.leaf):]
        return "<chain level>"


class Stop(Exception):
    def __init__(self, entry: str, why: str) -> None:
        super().__init__(f"{entry} {why}")
        self.entry, self.why, self.removed = entry, why, 0


def _check(fd: int, rel: str, inv: Inventory, n: str) -> os.stat_result:
    crel = _join(rel, n)
    want = inv.inv.get(crel)
    if want is None:
        raise Stop(crel, "is new")
    try:
        st = os.stat(n, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        raise Stop(crel, "is missing")
    except OSError as e:
        raise Stop(crel, f"cannot be read ({e.strerror or e})")
    if not same_entry(sig(st), want, inv.swept):
        raise Stop(crel, "was replaced or changed")
    return st


def _names(fd: int, rel: str, inv: Inventory) -> List[str]:
    """The names to handle in this directory, in removal order (markers last). They must be
    exactly those the check read; for a resumed removal, a subset of them."""
    if rel not in inv.listed:
        raise Stop(rel or ".", "was not read by the check")
    try:
        now = set(os.listdir(fd))
    except OSError as e:
        raise Stop(rel or ".", f"cannot be listed ({e.strerror or e})")
    want = set(inv.listed[rel])
    extra, gone = sorted(now - want), sorted(want - now)
    if extra:
        raise Stop(_join(rel, extra[0]), "is new")
    if gone and not inv.swept:
        raise Stop(_join(rel, gone[0]), "is missing")
    return sorted(now, key=lambda n: (n in MARKERS, n))


def _open_checked(fd: int, n: str, crel: str, st: os.stat_result) -> int:
    try:
        cfd = os.open(n, O_DIR, dir_fd=fd)
    except OSError as e:
        raise Stop(crel, f"cannot be opened ({e.strerror or e})")
    if ident(os.fstat(cfd)) != ident(st):
        os.close(cfd)
        raise Stop(crel, "was replaced")
    return cfd


def compare_tree(fd: int, inv: Inventory, rel: str = "") -> None:
    """Raise Stop at the first difference between the live tree under fd and the inventory."""
    if rel == "" and ident(os.fstat(fd)) != inv.root_id:
        raise Stop(".", "was replaced")
    for n in _names(fd, rel, inv):
        st = _check(fd, rel, inv, n)
        if stat.S_ISDIR(st.st_mode):
            cfd = _open_checked(fd, n, _join(rel, n), st)
            try:
                compare_tree(cfd, inv, _join(rel, n))
            finally:
                os.close(cfd)


def _remove(fd: int, rel: str, inv: Inventory, done: List[int], after: Optional[Callable[[str], None]]) -> None:
    st = os.fstat(fd)
    if (st.st_mode & stat.S_IRWXU) != stat.S_IRWXU:
        try:
            os.fchmod(fd, stat.S_IMODE(st.st_mode) | stat.S_IRWXU)  # Go's module dirs are 0555
        except OSError as e:
            raise Stop(rel or ".", f"cannot be made writable ({e.strerror or e})")
    for n in _names(fd, rel, inv):
        crel = _join(rel, n)
        est = _check(fd, rel, inv, n)
        try:
            if stat.S_ISDIR(est.st_mode):
                cfd = _open_checked(fd, n, crel, est)
                try:
                    _remove(cfd, crel, inv, done, after)
                finally:
                    os.close(cfd)
                os.rmdir(n, dir_fd=fd)  # fails if anything appeared in it meanwhile
            else:
                os.unlink(n, dir_fd=fd)
        except OSError as e:
            raise Stop(crel, f"could not be removed ({e.strerror or e})")
        done[0] += 1
        if after is not None:
            after(crel)


def remove_checked(parent_fd: int, q: str, inv: Inventory, after: Optional[Callable[[str], None]] = None) -> None:
    """Remove exactly the inventory, or stop at the first difference (Stop.removed says how
    many entries went first)."""
    done = [0]
    try:
        fd = os.open(q, O_DIR, dir_fd=parent_fd)
    except OSError as e:
        raise Stop(".", f"cannot be opened ({e.strerror or e})")
    try:
        compare_tree(fd, inv)
        try:
            _remove(fd, "", inv, done, after)
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
