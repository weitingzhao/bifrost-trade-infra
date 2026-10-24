"""What the local sweep may remove, and the checks it repeats before removing (W-31 4.6 S2;
CUT-lifecycle-2026-10-24.md §2 principles 2-7, R5, R6, R7, R11; reviews 539 F1-F4, 551).

A linked worktree may go only when all of these hold, checked in this order (the first that
fails is the reason it stays):
  - its path lies under a registered root (LIFECYCLE_WORKTREE_ROOTS: AGENT_WORK, WORKSPACE,
    TMPDIR) with no symlink below the root, its directory is there (a worktree whose
    directory is gone keeps its admin dir: git worktree prune is never run), and it is not a
    quarantine an interrupted sweep left (.lifecycle-del-);
  - nobody holds a Git lock on it (any lock, any reason);
  - its .git file and admin dir name each other, and every admin-dir entry is known
    (lifecycle_checks.admin_state: no operation under way, no unknown or unreadable entry);
  - its record (worktree_owner.py) says its session ended at least LIFECYCLE_END_MIN_AGE_MIN
    ago and nothing renewed it since; no other session started inside it (foreign use); its
    session's "active since" marker is not newer than the end and can be read
    (worktree_sessions.py). No record, an unusable record or no ended_at keeps it;
  - HEAD is what the worktree list says, and no per-worktree ref exists;
  - every commit HEAD reaches is reachable from a ref the remote holds (only objects count);
  - its HEAD reflog can be read; the commits it and the pseudo refs (ORIG_HEAD, FETCH_HEAD)
    name, where no remote ref reaches them, go into the run's unique bundle first, and so
    does a commit wrapping the tree AUTO_MERGE names;
  - no mount point inside it (mount table read again at each check), and git status and the
    cache roots pass lifecycle_checks.content_problem;
  - lsof's complete answer shows nothing open under it.
A local branch may go only when it is not checked out in a worktree that stays, an ended
worktree record that this run removes names it as the branch made for its work (review 539
F3), its tip is reachable from the remote's refs and its reflog can be read.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import worktree_owner as wo
import worktree_sessions as ws
from disk_guard_roots import mount_points
from lifecycle_checks import Why, admin_state, content_problem, mount_problem, open_problem, root_problem
from lifecycle_git import GitError, Reflog, ReflogError, git, per_worktree_refs, without_copy, worktree_list

QUARANTINE = ".lifecycle-del-"


@dataclass
class Item:
    repo: str
    repo_id: str
    kind: str  # worktree | branch
    name: str  # the worktree's path, or the branch's short name
    head: str = ""
    action: str = "keep"
    reason: str = ""
    detail: str = ""
    branch: Optional[str] = None
    admin: str = ""
    record: Optional[Dict[str, object]] = None
    record_raw: Optional[bytes] = None
    reflog_path: str = ""
    reflog_digest: str = ""
    reflog_shas: List[str] = field(default_factory=list)
    pseudo_shas: List[str] = field(default_factory=list)  # ORIG_HEAD, FETCH_HEAD
    auto_merge: Optional[str] = None  # the tree AUTO_MERGE names
    auto_merge_commit: Optional[str] = None  # --apply: the commit wrapping it, archived
    admin_digest: str = ""
    archive: List[str] = field(default_factory=list)  # commits without a copy, from reflog and pseudo refs
    ident: Tuple[int, int] = (0, 0)
    admin_ident: Tuple[int, int] = (0, 0)
    cache_bytes: Dict[str, int] = field(default_factory=dict)
    evidence: Optional["Item"] = None  # a branch: the ended worktree whose record names it

    def keep(self, code: str, detail: str = "") -> "Item":
        self.action, self.reason, self.detail = "keep", code, detail
        return self

    def history(self) -> List[str]:
        return self.reflog_shas + self.pseudo_shas + ([self.auto_merge_commit] if self.auto_merge_commit else [])

    def public(self) -> Dict[str, object]:
        d = {"repo": os.path.basename(self.repo), "repo_id": self.repo_id, "kind": self.kind, "name": self.name,
             "head": self.head, "action": self.action, "reason": self.reason, "detail": self.detail}
        if self.branch:
            d["branch"] = self.branch
        if self.archive:
            d["commits_archived" if self.action in ("removed", "deleted") else "commits_to_archive"] = len(self.archive)
        if self.auto_merge:
            d["auto_merge_tree"] = self.auto_merge
        if self.cache_bytes:
            d["cache_root_bytes"] = dict(self.cache_bytes)
        if self.record:
            d["work"] = self.record.get("work")
            d["session"] = self.record.get("session")
            d["ended_at"] = self.record.get("ended_at")
        return d


@dataclass
class Ctx:
    env: Dict[str, str]
    repo: str
    repo_id: str
    durable: List[str]
    roots: List[Tuple[str, str]]  # (as given, real path)
    now: float
    grace: float
    lsof: object  # disk_guard_roots.OpenFiles
    mounts: Optional[List[str]]  # the mount table read for the first check, None when it could not be read
    cfg: object = None  # disk_guard_base.Config: lsof and mount, read again at each later check

    def fresh_mounts(self) -> Optional[List[str]]:
        """The mount table now (review 552 A5): None when it cannot be read."""
        if self.cfg is None:
            return None
        points, err = mount_points(self.cfg)  # type: ignore[arg-type]
        return None if err else points


def _ident(path: str) -> Tuple[int, int]:
    st = os.lstat(path)
    return (st.st_dev, st.st_ino)


def record_problem(ctx: Ctx, rec: Dict[str, object], admin: str) -> Why:
    code, why = wo.end_evidence(rec, ctx.now, ctx.grace)
    if code:
        return code, why
    return ws.foreign_problem(rec) or ws.session_problem(ctx.env, rec, admin)


def classify_worktree(ctx: Ctx, wt: Dict[str, object]) -> Item:
    path = str(wt["path"])
    it = Item(ctx.repo, ctx.repo_id, "worktree", path, head=str(wt.get("head", "")))
    br = wt.get("branch")
    it.branch = str(br)[len("refs/heads/"):] if isinstance(br, str) and br.startswith("refs/heads/") else None
    if "prunable" in wt:
        return it.keep("missing", f"its directory is gone ({wt['prunable']}); the admin dir and HEAD reflog stay")
    if QUARANTINE in os.path.basename(path):
        return it.keep("quarantined-leftover", "an interrupted sweep's quarantine; the journal restores it, nothing else removes it")
    bad = root_problem(path, ctx.roots)
    if bad:
        return it.keep(*bad)
    if "locked" in wt:
        return it.keep("locked", f"git worktree lock: {wt['locked'] or 'no reason given'}")
    try:
        it.admin, common = wo.admin_of(path)
        if os.path.realpath(common) != os.path.realpath(os.path.join(ctx.repo, ".git")):
            return it.keep("admin-mismatch", f"its admin dir belongs to {common}")
        it.ident, it.admin_ident = _ident(path), _ident(it.admin)
    except (wo.OwnerError, OSError) as e:
        return it.keep("admin-mismatch", str(e))
    it.record, it.record_raw, bad_rec = wo.read_record(it.admin)
    if bad_rec:
        return it.keep("record-unusable", bad_rec)
    if it.record is None:
        return it.keep("unregistered", "no record: made before new-worktree.sh or by a tool that does not register (D-L8)")
    bad = record_problem(ctx, it.record, it.admin)
    if bad:
        return it.keep(*bad)
    st = admin_state(ctx.env, ctx.repo, it.admin)
    if st.problem:
        return it.keep(*st.problem)
    it.pseudo_shas, it.auto_merge, it.admin_digest = st.pseudo, st.auto_merge, st.digest
    try:
        if git(ctx.env, path, "rev-parse", "HEAD").strip() != it.head:
            return it.keep("head-changed", "HEAD is not what the worktree list said")
        refs = per_worktree_refs(ctx.env, path)
        if refs:
            return it.keep("per-worktree-refs", ", ".join(refs[:3]))
        missing = without_copy(ctx.env, ctx.repo, [it.head], ctx.durable)
        if missing:
            return it.keep("head-without-copy", f"{len(missing)} commit(s) of HEAD are on no ref the remote holds")
        it.reflog_path = os.path.join(it.admin, "logs", "HEAD")
        rl = Reflog(it.reflog_path)
        it.reflog_digest, it.reflog_shas = rl.digest, rl.shas
        it.archive = without_copy(ctx.env, ctx.repo, it.history(), ctx.durable)
    except ReflogError as e:
        return it.keep("reflog-unreadable", str(e))
    except GitError as e:
        return it.keep("git-error", str(e))
    bad = mount_problem(path, ctx.mounts) or content_problem(ctx.env, path, it.record, ctx.mounts, it.cache_bytes)
    if bad:
        return it.keep(*bad)
    bad = open_problem(ctx.lsof, path)
    if bad:
        return it.keep(*bad)
    it.action, it.reason = "remove", "ended, everything it holds has a copy or is archived"
    return it


def classify_branches(ctx: Ctx, worktrees: List[Dict[str, object]], items: List[Item]) -> List[Item]:
    out: List[Item] = []
    text = git(ctx.env, ctx.repo, "for-each-ref", "--format=%(objectname) %(refname)", "refs/heads/")
    held: Dict[str, str] = {}
    for wt in worktrees:
        if isinstance(wt.get("branch"), str):
            held[str(wt["branch"])] = str(wt["path"])
    leaving = {i.name for i in items if i.kind == "worktree" and i.action == "remove"}
    for line in text.splitlines():
        sha, ref = line.split(" ", 1)
        b = ref[len("refs/heads/"):]
        if b == "main":
            continue
        it = Item(ctx.repo, ctx.repo_id, "branch", b, head=sha, branch=b)
        out.append(it)
        if ref in held and held[ref] not in leaving:
            it.keep("checked-out", f"checked out at {held[ref]}")
            continue
        ev = [w for w in items if w.kind == "worktree" and w.action == "remove" and w.record
              and w.record.get("branch") == b and w.record.get("branch_created") is True]
        if not ev:
            it.keep("no-end-evidence", "no ended worktree record this run removes names it as the branch made for its work")
            continue
        it.evidence = ev[0]
        try:
            missing = without_copy(ctx.env, ctx.repo, [sha], ctx.durable)
            if missing:
                it.keep("tip-without-copy", f"{len(missing)} commit(s) of the tip are on no ref the remote holds")
                continue
            it.reflog_path = os.path.join(ctx.repo, ".git", "logs", "refs", "heads", *b.split("/"))
            rl = Reflog(it.reflog_path)
            it.reflog_digest, it.reflog_shas = rl.digest, rl.shas
            it.archive = without_copy(ctx.env, ctx.repo, rl.shas, ctx.durable)
        except ReflogError as e:
            it.keep("reflog-unreadable", str(e))
            continue
        except GitError as e:
            it.keep("git-error", str(e))
            continue
        it.action, it.reason = "delete", "made for an ended worktree's work; tip has a copy, reflog archived"
    return out


def recheck_worktree(ctx: Ctx, it: Item, lock_reason: str, path: Optional[str] = None) -> Why:
    """Every check again, on the worktree at path (its quarantine once it is moved there):
    the same identity, HEAD, reflog, pseudo refs and record as when it was archived."""
    path = path or it.name
    try:
        now = {str(w["path"]): w for w in worktree_list(ctx.env, ctx.repo)}
    except GitError as e:
        return "git-error", str(e)
    wt = now.get(path)
    if wt is None or "prunable" in wt:
        return "gone", f"{path} is not in the worktree list"
    if wt.get("locked") != lock_reason:
        return "locked", "the Git lock is not this run's"
    if wt.get("head") != it.head or (wt.get("branch") or None) != (f"refs/heads/{it.branch}" if it.branch else None):
        return "head-changed", "HEAD or its branch moved since the check"
    bad = root_problem(path, ctx.roots)
    if bad:
        return bad
    try:
        if _ident(path) != it.ident or _ident(it.admin) != it.admin_ident:
            return "replaced", "the directory or its admin dir is not the one checked"
    except OSError as e:
        return "replaced", str(e)
    rec, raw, bad_rec = wo.read_record(it.admin)
    if bad_rec or rec is None or raw != it.record_raw:
        return "record-changed", "the record changed since the check (a renewal voids an end)"
    bad = record_problem(ctx, rec, it.admin)
    if bad:
        return bad
    st = admin_state(ctx.env, ctx.repo, it.admin)
    if st.problem:
        return st.problem
    if st.digest != it.admin_digest or st.pseudo != it.pseudo_shas or st.auto_merge != it.auto_merge:
        return "pseudo-refs-changed", "HEAD, ORIG_HEAD, FETCH_HEAD or AUTO_MERGE changed since they were archived"
    try:
        if git(ctx.env, path, "rev-parse", "HEAD").strip() != it.head:
            return "head-changed", "HEAD moved since the check"
        if per_worktree_refs(ctx.env, path):
            return "per-worktree-refs", "a per-worktree ref appeared"
        if Reflog(it.reflog_path).digest != it.reflog_digest:
            return "reflog-changed", "the HEAD reflog changed since it was archived"
        if without_copy(ctx.env, ctx.repo, [it.head], ctx.durable):
            return "head-without-copy", "HEAD is no longer reachable from the remote's refs"
    except GitError as e:
        return "git-error", str(e)
    mounts = ctx.fresh_mounts()
    return mount_problem(path, mounts) or mount_problem(it.name, mounts) or content_problem(ctx.env, path, rec, mounts)


def recheck_branch(ctx: Ctx, it: Item) -> Why:
    try:
        tip = git(ctx.env, ctx.repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{it.name}").strip()
        if tip != it.head:
            return "moved", "the branch moved since the check"
        if without_copy(ctx.env, ctx.repo, [it.head], ctx.durable):
            return "tip-without-copy", "the tip is no longer reachable from the remote's refs"
    except GitError as e:
        return "git-error", str(e)
    return last_branch_check(ctx, it)


def last_branch_check(ctx: Ctx, it: Item) -> Why:
    """Just before update-ref -d: checked out nowhere, and its reflog as archived."""
    try:
        for wt in worktree_list(ctx.env, ctx.repo):
            if wt.get("branch") == f"refs/heads/{it.name}":
                return "checked-out", f"checked out at {wt['path']} since the check"
        if Reflog(it.reflog_path).digest != it.reflog_digest:
            return "reflog-changed", "its reflog changed since it was archived"
    except GitError as e:
        return "git-error", str(e)
    return None
