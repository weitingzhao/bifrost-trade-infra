"""What the local sweep may remove, and the checks it repeats just before removing
(W-31 4.6 S2; CUT-lifecycle-2026-10-24.md §2 principles 2-7, R5, R6, R7, R11; review 539 F1-F4).

A linked worktree may go only when all of these hold, checked in this order (the first that
fails is the reason it stays):
  - its path lies under a registered root (LIFECYCLE_WORKTREE_ROOTS: AGENT_WORK, WORKSPACE,
    TMPDIR) with no symlink below the root, and the directory is there (a worktree whose
    directory is gone keeps its admin dir and HEAD reflog: git worktree prune is never run);
  - nobody holds a Git lock on it (any lock, any reason);
  - its .git file and admin dir name each other, and no rebase, merge, cherry-pick, revert or
    bisect is under way;
  - its record (worktree_owner.py) says its session ended at least LIFECYCLE_END_MIN_AGE_MIN
    ago and nothing renewed it since: no record, an unusable record or no ended_at keeps it;
  - HEAD is what the worktree list says, and no per-worktree ref (refs/worktree, bisect,
    rewritten) exists;
  - every commit HEAD reaches is reachable from a ref the remote holds (a detached HEAD whose
    "twin" with the same Change-Id is on main is not: only objects count);
  - its HEAD reflog can be read; the commits only that reflog reaches go into the run's
    unique bundle before anything is removed;
  - git status reports nothing: no change (a deletion included), nothing untracked, nothing
    ignored except whole directories its record names as cache roots, which hold no .git
    entry and no other filesystem; no submodule;
  - lsof saw nothing open under it, and lsof's answer is complete.
A local branch may go only when it is not checked out in a worktree that stays, an ended
worktree record that this run removes names it as the branch made for its work (review 539
F3: no end evidence, no deletion), its tip is reachable from the remote's refs and its reflog
can be read (its own reflog commits are archived like a worktree's).
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import worktree_owner as wo
from lifecycle_git import (GitError, Reflog, ReflogError, git, operation_markers, per_worktree_refs, status_entries,
                           without_copy, worktree_list)


@dataclass
class Item:
    repo: str
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
    archive: List[str] = field(default_factory=list)  # reflog commits without a copy
    ident: Tuple[int, int] = (0, 0)
    admin_ident: Tuple[int, int] = (0, 0)
    evidence: Optional["Item"] = None  # a branch: the ended worktree whose record names it

    def keep(self, code: str, detail: str = "") -> "Item":
        self.action, self.reason, self.detail = "keep", code, detail
        return self

    def public(self) -> Dict[str, object]:
        d = {"repo": os.path.basename(self.repo), "kind": self.kind, "name": self.name, "head": self.head,
             "action": self.action, "reason": self.reason, "detail": self.detail}
        if self.branch:
            d["branch"] = self.branch
        if self.archive:
            d["reflog_commits_archived" if self.action in ("removed", "deleted") else "reflog_commits_to_archive"] = len(self.archive)
        if self.record:
            d["work"] = self.record.get("work")
            d["session"] = self.record.get("session")
            d["ended_at"] = self.record.get("ended_at")
        return d


@dataclass
class Ctx:
    env: Dict[str, str]
    repo: str
    durable: List[str]
    roots: List[Tuple[str, str]]  # (as given, real path)
    now: float
    grace: float
    lsof: object  # disk_guard_roots.OpenFiles


def root_problem(path: str, roots: List[Tuple[str, str]]) -> Optional[Tuple[str, str]]:
    """Why path is not a worktree dir this sweep may remove: it must lie strictly below a
    registered root, as written or by its real path, with no symlink and nothing but
    directories from the root down."""
    for given, real in roots:
        for r in (given, real):
            if path.startswith(r + os.sep) and len(path) > len(r) + 1:
                cur = r
                for comp in path[len(r) + 1:].split(os.sep):
                    if comp in ("", ".", ".."):
                        return "outside-roots", f"{path} is not a canonical path"
                    cur = os.path.join(cur, comp)
                    try:
                        st = os.lstat(cur)
                    except FileNotFoundError:
                        return "missing", f"{cur} is not there"
                    except OSError as e:
                        return "unreadable", f"{cur}: {e.strerror or e}"
                    if stat.S_ISLNK(st.st_mode):
                        return "symlink-in-path", f"{cur} is a symlink (not followed)"
                    if not stat.S_ISDIR(st.st_mode):
                        return "not-a-directory", cur
                return None
    return "outside-roots", f"{path} is under none of the registered roots"


def _ident(path: str) -> Tuple[int, int]:
    st = os.lstat(path)
    return (st.st_dev, st.st_ino)


def _cache_root_problem(wt: str, rel: str) -> Optional[str]:
    """A declared cache root git reports as ignored may go with the worktree when it holds no
    .git entry, no symlinked directory component and nothing on another filesystem."""
    top = os.path.join(wt, rel)
    cur = wt
    for comp in rel.split("/"):
        cur = os.path.join(cur, comp)
        try:
            if not stat.S_ISDIR(os.lstat(cur).st_mode):
                return f"{cur} is not a directory"
        except OSError as e:
            return f"{cur}: {e.strerror or e}"
    dev = os.lstat(wt).st_dev
    errors: List[str] = []
    for dp, dns, fns in os.walk(top, onerror=lambda e: errors.append(str(e))):
        for n in dns + fns:
            if n == ".git":
                return f"{os.path.join(dp, n)}: a repository inside a cache root"
        for n in dns:
            try:
                if os.lstat(os.path.join(dp, n)).st_dev != dev:
                    return f"{os.path.join(dp, n)} is on another filesystem"
            except OSError as e:
                return str(e)
    return errors[0] if errors else None


def content_problem(ctx: Ctx, path: str, record: Dict[str, object]) -> Optional[Tuple[str, str]]:
    """git status and submodules: what keeps a worktree for its content."""
    try:
        entries = status_entries(ctx.env, path)
        gitmodules = git(ctx.env, path, "ls-files", "--", ".gitmodules").strip()
        # assume-unchanged (lower-case tag) and skip-worktree (S) entries hide their changes from status
        hidden = [ln[2:] for ln in git(ctx.env, path, "ls-files", "-v").splitlines() if ln[:1].islower() or ln[:1] == "S"]
    except GitError as e:
        return "git-error", str(e)
    if gitmodules:
        return "submodules", "the worktree has submodules"
    if hidden:
        return "hidden-changes", f"{len(hidden)} index entries are assume-unchanged or skip-worktree, e.g. {hidden[0]}"
    roots = [str(r).rstrip("/") for r in record.get("cache_roots", [])]
    for code, p in entries:
        if code == "!!":
            p2 = p.rstrip("/")
            hit = next((r for r in roots if p2 == r or p2.startswith(r + "/")), None)
            if hit is None:
                return "ignored", f"ignored {p} is not a cache root its record names"
            bad = _cache_root_problem(path, p2)
            if bad:
                return "cache-root-unsafe", bad
            continue
        if code == "??":
            return "untracked", f"untracked {p}"
        return "changes", f"uncommitted change {code.strip()} {p}"
    return None


def open_problem(lsof: object, path: str) -> Optional[Tuple[str, str]]:
    real = os.path.realpath(path)
    p = lsof.problem_for(path, real)  # type: ignore[attr-defined]
    if p:
        return "lsof-unknown", p
    hit = lsof.under(path, real)  # type: ignore[attr-defined]
    if hit:
        return "in-use", f"open: {hit}"
    return None


def classify_worktree(ctx: Ctx, wt: Dict[str, object]) -> Item:
    path = str(wt["path"])
    it = Item(ctx.repo, "worktree", path, head=str(wt.get("head", "")))
    br = wt.get("branch")
    it.branch = str(br)[len("refs/heads/"):] if isinstance(br, str) and br.startswith("refs/heads/") else None
    if "prunable" in wt:
        return it.keep("missing", f"its directory is gone ({wt['prunable']}); the admin dir and HEAD reflog stay")
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
    marks = operation_markers(it.admin)
    if marks:
        return it.keep("operation-in-progress", ", ".join(marks))
    it.record, it.record_raw, bad_rec = wo.read_record(it.admin)
    if bad_rec:
        return it.keep("record-unusable", bad_rec)
    if it.record is None:
        return it.keep("unregistered", "no record: made before new-worktree.sh or by a tool that does not register (D-L8)")
    code, why = wo.end_evidence(it.record, ctx.now, ctx.grace)
    if code:
        return it.keep(code, why)
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
        it.archive = without_copy(ctx.env, ctx.repo, rl.shas, ctx.durable)
    except ReflogError as e:
        return it.keep("reflog-unreadable", str(e))
    except GitError as e:
        return it.keep("git-error", str(e))
    bad = content_problem(ctx, path, it.record)
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
        it = Item(ctx.repo, "branch", b, head=sha, branch=b)
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


def recheck_worktree(ctx: Ctx, it: Item, lock_reason: str) -> Optional[Tuple[str, str]]:
    """The checks repeated under the record's flock and our Git lock, just before removal."""
    try:
        now = {str(w["path"]): w for w in worktree_list(ctx.env, ctx.repo)}
    except GitError as e:
        return "git-error", str(e)
    wt = now.get(it.name)
    if wt is None or "prunable" in wt:
        return "gone", "no longer in the worktree list"
    if wt.get("locked") != lock_reason:
        return "locked", "the Git lock is not this run's"
    if wt.get("head") != it.head or (wt.get("branch") or None) != (f"refs/heads/{it.branch}" if it.branch else None):
        return "head-changed", "HEAD or its branch moved since the check"
    bad = root_problem(it.name, ctx.roots)
    if bad:
        return bad
    try:
        if _ident(it.name) != it.ident or _ident(it.admin) != it.admin_ident:
            return "replaced", "the directory or its admin dir is not the one checked"
    except OSError as e:
        return "replaced", str(e)
    rec, raw, bad_rec = wo.read_record(it.admin)
    if bad_rec or rec is None or raw != it.record_raw:
        return "record-changed", "the record changed since the check (a renewal voids an end)"
    code, why = wo.end_evidence(rec, ctx.now, ctx.grace)
    if code:
        return code, why
    marks = operation_markers(it.admin)
    if marks:
        return "operation-in-progress", ", ".join(marks)
    try:
        if git(ctx.env, it.name, "rev-parse", "HEAD").strip() != it.head:
            return "head-changed", "HEAD moved since the check"
        if per_worktree_refs(ctx.env, it.name):
            return "per-worktree-refs", "a per-worktree ref appeared"
        if Reflog(it.reflog_path).digest != it.reflog_digest:
            return "reflog-changed", "the HEAD reflog changed since it was archived"
        if without_copy(ctx.env, ctx.repo, [it.head], ctx.durable):
            return "head-without-copy", "HEAD is no longer reachable from the remote's refs"
    except GitError as e:
        return "git-error", str(e)
    return content_problem(ctx, it.name, rec)


def recheck_branch(ctx: Ctx, it: Item) -> Optional[Tuple[str, str]]:
    try:
        tip = git(ctx.env, ctx.repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{it.name}").strip()
        if tip != it.head:
            return "moved", "the branch moved since the check"
        for wt in worktree_list(ctx.env, ctx.repo):
            if wt.get("branch") == f"refs/heads/{it.name}":
                return "checked-out", f"checked out at {wt['path']} since the check"
        if Reflog(it.reflog_path).digest != it.reflog_digest:
            return "reflog-changed", "its reflog changed since it was archived"
        if without_copy(ctx.env, ctx.repo, [it.head], ctx.durable):
            return "tip-without-copy", "the tip is no longer reachable from the remote's refs"
    except GitError as e:
        return "git-error", str(e)
    return None


def digest(b: Optional[bytes]) -> str:
    return hashlib.sha256(b or b"").hexdigest()
