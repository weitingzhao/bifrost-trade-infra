"""The sweep's items: classify registered roots, and report unregistered caches and
unmanaged node_modules so their owners can register or remove them (disk-guard, W-31 4.6
S1; review 539 F1–F4, review 543 A1–A4 and B).
"""

from __future__ import annotations

import fnmatch
import os
import stat
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from disk_guard_base import CACHE_NAMES, Chain, Config, Ident, Problem, QUARANTINE, _join, _under, gib
from disk_guard_layout import detect, du, validate
from disk_guard_roots import Entry, OpenFiles, check_git, check_original, check_policy, expand, overlaps
from disk_guard_inventory import Inventory, Stop, compare_tree
from disk_guard_state import Journal, inventory_load


@dataclass
class Item:
    path: str
    source: str
    kind: Optional[str]
    policy: Optional[str]
    action: str = "keep"
    reason: str = ""
    detail: str = ""
    bytes: int = 0
    bytes_complete: bool = False
    layout: Optional[str] = None
    run_done: Optional[bool] = None
    entry: Optional[Entry] = field(default=None, repr=False)
    leftover: Optional[str] = None  # None: no .lifecycle-del- suffix; a str (maybe empty): the run id after it
    ids: List[Ident] = field(default_factory=list, repr=False)  # AGENT_WORK/... down to the root
    journal: Optional[Dict[str, object]] = field(default=None, repr=False)  # a leftover's record
    resume: Optional[Inventory] = field(default=None, repr=False)  # a stopped removal's inventory, while classified
    resuming: bool = False  # a stopped removal to finish (its inventory is read again at removal)

    def keep(self, p: Problem) -> "Item":
        self.action, self.reason, self.detail = "keep", p.code, p.detail
        return self

    def public(self) -> Dict[str, object]:
        d = {k: getattr(self, k) for k in ("path", "source", "kind", "policy", "action", "reason", "detail", "bytes", "bytes_complete", "layout", "run_done", "leftover")}
        return {k: v for k, v in d.items() if v is not None and (v != "" or k == "leftover")}


def registered_items(cfg: Config, entries: List[Entry]) -> List[Item]:
    by_path: Dict[str, Item] = {}
    order: List[str] = []
    for entry in entries:
        for c in expand(cfg.agent_work, entry):
            it = Item(c.rel, entry.source, entry.kind, entry.policy, entry=entry, leftover=c.leftover)
            if c.problem:
                it.keep(c.problem)
            elif c.missing:
                it.keep(Problem("missing", "the registered root does not exist"))
            prev = by_path.get(c.rel)
            if prev is None:
                by_path[c.rel] = it
                order.append(c.rel)
            elif (prev.kind, prev.policy) != (entry.kind, entry.policy) and not prev.reason and not it.reason:
                prev.keep(Problem("registry-conflict", f"also registered as {entry.kind} {entry.policy} at {entry.source}"))
    items = [by_path[p] for p in order]
    for a in items:
        for b in items:
            if a is not b and _under(b.path, a.path):
                for x in (a, b):
                    if not x.reason:
                        x.keep(Problem("registry-overlap", f"{a.path} contains {b.path}: register one or the other"))
    for it in items:
        if it.reason:
            continue
        # either direction, for the path it has and the path it had (review 544 A3)
        names = {it.path, original_name(it)}
        for ex in cfg.exclude:
            if any(overlaps(n, ex) for n in names):
                it.keep(Problem("excluded", f"{ex} is managed by its own owner (LIFECYCLE_EXCLUDE)"))
        for own in (cfg.lock_dir, cfg.status_dir):
            if any(overlaps(os.path.join(cfg.agent_work, n), own) for n in names):
                it.keep(Problem("excluded", "the sweep's own lock or status directory"))
    return items


def is_leftover(it: Item) -> bool:
    """The name carries a .lifecycle-del- suffix (review 547 A2: an empty run id counts too)."""
    return it.leftover is not None


def original_name(it: Item) -> str:
    return it.path.rsplit(QUARANTINE, 1)[0] if is_leftover(it) else it.path


def check_git_for(cfg: Config, it: Item) -> None:
    path = os.path.join(cfg.agent_work, it.path)
    if is_leftover(it):
        # renamed by a sweep that died: nothing tracked under the name it has, and its
        # original path must still pass Git in full, ignore rules included
        check_git(cfg, path, tracked_only=True)
        check_original(cfg, os.path.join(cfg.agent_work, original_name(it)))
    else:
        check_git(cfg, path)


def recorded(journal: Journal, it: Item) -> Dict[str, object]:
    """The journal entry that makes a .lifecycle-del- directory a leftover of this sweeper."""
    if it.leftover == "":
        raise Problem("unrecorded-quarantine-name", "a .lifecycle-del- suffix with no run id: no sweep names a rename so; reported only")
    rec = journal.get(it.path)
    if not rec or rec.get("original") != original_name(it):
        raise Problem("unrecorded-quarantine-name", "named like a sweep's rename, but no journal entry records it: reported only")
    return rec


def classify(cfg: Config, aw_fd: int, it: Item, lsof: OpenFiles, now: float, journal: Journal) -> None:
    """First check, through handles opened without following links; records the (device,
    inode) of every directory on the path for the checks before the rename and the removal."""
    if it.reason:
        return
    assert it.entry is not None and it.kind is not None
    path = os.path.join(cfg.agent_work, it.path)
    owner = it.path.split("/", 1)[0]
    try:
        rec = it.journal = recorded(journal, it) if is_leftover(it) else None
        if rec is not None:
            try:
                it.resume = inventory_load(str(rec["file"]))
            except ValueError as e:
                raise Problem("journal-inventory-unusable", f"{e}: reported only")
        with Chain(aw_fd, it.path) as ch:
            it.ids = list(ch.ids)
            if rec is not None and tuple(rec.get("root") or ()) != it.ids[-1]:
                raise Problem("unrecorded-quarantine-name", "the journal entry records another directory (device, inode): reported only")
            if it.resume is not None:
                resumable(ch.fd, it)
                it.resume, it.resuming = None, True  # read again per root when it is removed
            else:
                w = validate(ch.fd, it.kind)
                it.bytes, it.bytes_complete, it.layout = w.bytes, True, it.kind
                owner_fd = ch.fds[0] if len(ch.fds) >= 2 else None
                if it.entry.policy == "run.done" and owner_fd is not None:
                    try:
                        it.run_done = stat.S_ISREG(os.stat("run.done", dir_fd=owner_fd, follow_symlinks=False).st_mode)
                    except OSError:
                        it.run_done = False
                check_policy(cfg, it.entry, owner_fd, owner, w, now)
        if not it.resuming and it.entry.cap_bytes is not None and w.bytes <= it.entry.cap_bytes:
            raise Problem("under-cap", f"{gib(w.bytes)} <= cap {gib(it.entry.cap_bytes)}")
        check_git_for(cfg, it)
        unknown = lsof.problem_for(path)
        if unknown:
            raise Problem("open-files-unknown", unknown)
        if lsof.under(path):
            raise Problem("open-files", "a process has a file open under it")
    except Problem as p:
        if not it.bytes:
            it.bytes, it.bytes_complete = du(path)
        it.keep(p)
        return
    it.action = "prune" if it.entry.cap_bytes is not None else "delete"
    if it.resuming:
        it.bytes, it.bytes_complete = du(path)
        it.layout = it.kind
        it.reason, it.detail = "finishing-stopped-removal", "everything left is in the stopped removal's inventory"
    else:
        it.reason = "pruned-over-cap" if it.action == "prune" else "registered-and-ended"
        it.detail = f"{it.kind} layout checked in full ({w.files} files)"


def resumable(fd: int, it: Item) -> None:
    """A stopped removal may be finished when what is left is all in its inventory, matching:
    entries may be gone (removed before the stop, markers last of all) and directories may
    carry the sweeper's own u+rwx; nothing may be new or changed (review 547 C1)."""
    assert it.resume is not None
    if it.resume.root_id != it.ids[-1]:
        raise Problem("unrecorded-quarantine-name", "the inventory records another directory (device, inode): reported only")
    try:
        compare_tree(fd, it.resume)
    except Stop as s:
        raise Problem("changed-since-stopped", f"{it.resume.show(s.entry)} {s.why} since a sweep stopped removing it: reported only")


def discovered_items(cfg: Config, aw_fd: int, registered: List[Item]) -> List[Item]:
    """Caches found by name that nobody registered: reported so they can be registered."""
    taken = [it.path for it in registered]
    out: List[Item] = []
    seen = set()

    def add(rel: str, owner_done: Optional[bool]) -> None:
        if rel in seen or any(_under(rel, t) or _under(t, rel) for t in taken):
            return
        seen.add(rel)
        p = os.path.join(cfg.agent_work, rel)
        it = Item(rel, "discovered", None, None, run_done=owner_done)
        try:
            st = os.lstat(p)
        except OSError as e:
            out.append(it.keep(Problem("unreadable", e.strerror or str(e))))
            return
        if stat.S_ISLNK(st.st_mode):
            out.append(it.keep(Problem("unregistered", "a symlink (not followed)")))
            return
        if not stat.S_ISDIR(st.st_mode):
            it.bytes, it.bytes_complete = st.st_blocks * 512, True
            out.append(it.keep(Problem("unregistered", "a file, not a cache")))
            return
        kind, problem, (it.bytes, it.bytes_complete) = detect(aw_fd, rel, p)
        it.layout = kind
        if problem is None:
            hint = f"layout {kind} confirmed in full"
            if owner_done:
                hint += ", owner has run.done"
            out.append(it.keep(Problem("unregistered", hint + ": the sweep removes registered roots only")))
        else:
            out.append(it.keep(Problem("unregistered", f"layout {kind or 'unknown'}: {problem.code} {problem.detail}".strip())))

    for pattern in cfg.discover:
        for owner in _glob_dirs(cfg.agent_work, pattern.split("/")):
            if any(_under(owner, ex) for ex in cfg.exclude):
                continue
            done = os.path.isfile(os.path.join(cfg.agent_work, owner, "run.done"))
            try:
                names = sorted(os.listdir(os.path.join(cfg.agent_work, owner)))
            except OSError:
                continue
            for n in names:
                if n in CACHE_NAMES:
                    add(f"{owner}/{n}", done)
    shared = os.path.join(cfg.agent_work, ".cache")
    if os.path.isdir(shared) and not os.path.islink(shared):
        try:
            for n in sorted(os.listdir(shared)):
                add(f".cache/{n}", None)
        except OSError as e:
            out.append(Item(".cache", "discovered", None, None).keep(Problem("unreadable", e.strerror or str(e))))
    return out


def unmanaged_items(cfg: Config, taken: List[str], max_depth: int = 4) -> List[Item]:
    """node_modules nobody registered (review 543 B: the old sweep removed idle ones by name;
    this one reports each with its size so growth shows, and leaves it to its owner)."""
    out: List[Item] = []
    own = [os.path.relpath(p, cfg.agent_work) for p in (cfg.lock_dir, cfg.status_dir) if _under(p, cfg.agent_work)]

    def walk(abs_dir: str, rel: str, depth: int) -> None:
        try:
            with os.scandir(abs_dir) as it:
                ents = sorted((e for e in it if e.is_dir(follow_symlinks=False)), key=lambda e: e.name)
        except OSError:
            return
        for e in ents:
            crel = _join(rel, e.name)
            if e.name in (".git", ".cache") or QUARANTINE in e.name or any(_under(crel, t) for t in taken + own + cfg.exclude):
                continue
            if e.name == "node_modules":
                size, complete = du(e.path)
                out.append(Item(crel, "discovered", None, None, bytes=size, bytes_complete=complete).keep(
                    Problem("unmanaged-node-modules", f"{gib(size)}: not a registered cache root; its owner removes or registers it")))
            elif depth < max_depth:
                walk(e.path, crel, depth + 1)

    walk(cfg.agent_work, "", 1)
    return out


def _glob_dirs(base: str, segs: List[str]) -> List[str]:
    found: List[str] = []

    def rec(abs_dir: str, rel_dir: str, i: int) -> None:
        try:
            names = sorted(os.listdir(abs_dir))
        except OSError:
            return
        for n in names:
            if QUARANTINE in n or not fnmatch.fnmatchcase(n, segs[i]):
                continue
            p = os.path.join(abs_dir, n)
            if os.path.islink(p) or not os.path.isdir(p):
                continue
            rel = _join(rel_dir, n)
            if i == len(segs) - 1:
                found.append(rel)
            else:
                rec(p, rel, i + 1)

    rec(base, "", 0)
    return found
