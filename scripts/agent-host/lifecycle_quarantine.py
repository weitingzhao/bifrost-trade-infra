"""The last step of the local sweep: archive placement, quarantine, removal (W-31 4.6 S2;
review 551 A3, A4; the same threat model as disk-guard, CUT-lifecycle-2026-10-24.md §4.1).

Guard (A3). The backup root and each run directory, by real path, may not lie inside or
contain any worktree of a scanned repository, its admin dir, or a cache root disk-guard may
remove (cache-roots.tsv patterns under AGENT_WORK). A run whose backup root overlaps one is
refused as a configuration error before anything is archived; the relation is checked again
just before each removal.

Quarantine (A4). After the second check, under the record's flock and this run's Git lock:
  1. a journal entry (<status>/lifecycle-local-journal/) records the original path, the
     quarantine path <name>.lifecycle-del-<run> in the same parent, the directory's identity
     and the HEAD that was archived;
  2. our Git lock is released and git worktree move renames the worktree to its quarantine
     (Git's own admin dir follows), and the lock is taken again there;
  3. every check runs again on the quarantined worktree (lifecycle_items.recheck_worktree:
     identity, HEAD, HEAD reflog, ORIG_HEAD and FETCH_HEAD, record, status), with a fresh
     lsof that must be complete and show nothing open and no cwd under either path, and
     the guard;
  4. only then git worktree remove (never --force) on the quarantined path; on any
     difference the worktree is moved back to its path and kept.
A run that dies between 1 and 4 leaves the entry: the next --apply moves the worktree back
(never finishes the removal) when the original path is free, and reports it otherwise.

Still not protected (mistakes are, a process working against the sweep is not): a process
that writes into the quarantined tree through a handle it already held (a cwd or an open
directory) after the last lsof snapshot and before git worktree remove finishes; git worktree
remove still refuses a tree with changes or untracked files at that moment, but a commit made
on a detached HEAD in that window goes with it. A branch checked out between the last
worktree-list read and update-ref -d is left on an unborn branch (its tip has a copy).
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from typing import Dict, List, Optional, Tuple

import worktree_owner as wo
from disk_guard_roots import OpenFiles, parse_registry
from disk_guard_state import _private_dir, _read_private, _write_private
from lifecycle_checks import Why, open_problem
from lifecycle_git import GitError, git, worktree_list
from lifecycle_items import QUARANTINE, Ctx, Item, recheck_worktree

JOURNAL = "lifecycle-local-journal"


def _overlap(a: str, b: str) -> bool:
    return a == b or a.startswith(b.rstrip(os.sep) + os.sep) or b.startswith(a.rstrip(os.sep) + os.sep)


def _pattern_overlap(pattern: str, rel: str) -> bool:
    """A cache-roots.tsv pattern (segments with * ? []) and a path under AGENT_WORK overlap
    when one is a prefix of the other segment by segment."""
    ps, rs = pattern.split("/"), rel.split("/")
    return all(fnmatch.fnmatchcase(r, p) for p, r in zip(ps, rs))


class Guard:
    def __init__(self, backup_root: str, agent_work: str, registries: List[Tuple[str, bool]]) -> None:
        self.backup_root = backup_root
        self.agent_work = agent_work
        self.patterns = [e.pattern for path, req in registries for e in parse_registry(path, req)[0]]
        self.run_dirs: List[str] = []

    def problem(self, *paths: str) -> Why:
        """Why the archive is not safe from removing paths (each a worktree, admin dir or
        quarantine), with every real path resolved now."""
        archives = [os.path.realpath(self.backup_root)] + [os.path.realpath(d) for d in self.run_dirs]
        for a in archives:
            for p in paths:
                for q in (os.path.abspath(p), os.path.realpath(p)):
                    if _overlap(a, q):
                        return "backup-overlap", f"the archive {a} and {q} overlap"
        real = os.path.realpath(self.backup_root)
        if real == self.agent_work or real.startswith(self.agent_work + os.sep):
            rel = real[len(self.agent_work) + 1:]
            hit = next((pat for pat in self.patterns if rel == "" or _pattern_overlap(pat, rel)), None)
            if hit:
                return "backup-overlap", f"the archive {real} overlaps disk-guard's cache root {hit}"
        return None


def journal_dir(env: Dict[str, str]) -> str:
    return os.path.join(wo.status_dir(env), JOURNAL)


def journal_write(env: Dict[str, str], run_id: str, repo: str, it: Item, quarantine: str) -> str:
    d = journal_dir(env)
    os.makedirs(os.path.dirname(d), exist_ok=True)
    _private_dir(d)
    p = os.path.join(d, f"{run_id}-{hashlib.sha1(quarantine.encode()).hexdigest()[:16]}.json")
    _write_private(p, {"run_id": run_id, "repo": repo, "original": it.name, "quarantine": quarantine,
                       "ident": list(it.ident), "admin": it.admin, "head": it.head, "written_at": wo.fmt(wo.now_ts())})
    return p


def journal_drop(path: str) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def restore(env: Dict[str, str], repos: List[str], apply: bool, notes: List[str]) -> None:
    """Move back every worktree an interrupted run left in quarantine (apply), or report them."""
    d = journal_dir(env)
    try:
        if not _private_dir(d, create=False):
            return
        names = sorted(os.listdir(d))
    except OSError as e:
        notes.append(f"the quarantine journal cannot be read ({e.strerror or e}): leftovers stay where they are")
        return
    for n in [x for x in names if x.endswith(".json")]:
        p = os.path.join(d, n)
        try:
            e = json.loads(_read_private(p) or "")
            repo, orig, q = str(e["repo"]), str(e["original"]), str(e["quarantine"])
            if repo not in repos or QUARANTINE not in os.path.basename(q):
                raise ValueError("not an entry of a scanned repository")
        except (OSError, ValueError, KeyError, TypeError) as err:
            notes.append(f"journal entry {n} cannot be used ({type(err).__name__}): its worktree stays where it is")
            continue
        try:
            listed = {str(w["path"]): w for w in worktree_list(env, repo)}
        except GitError as err:
            notes.append(f"journal entry {n}: {err}")
            continue
        if q not in listed:
            if not os.path.lexists(q):
                if apply:
                    journal_drop(p)
                notes.append(f"{q}: gone ({'entry dropped' if apply else 'entry stays until --apply'})")
            else:
                notes.append(f"{q}: in the journal but not a worktree of {repo}: left as it is")
            continue
        if not apply:
            notes.append(f"{q}: left in quarantine by run {e.get('run_id')}; --apply moves it back to {orig}")
            continue
        if os.path.lexists(orig):
            notes.append(f"{q}: left in quarantine; {orig} is taken, so it stays there")
            continue
        try:
            admin, _ = wo.admin_of(q)
            with wo.OwnerLock(admin, 0):
                if str(listed[q].get("locked", "")).startswith("lifecycle:"):
                    git(env, repo, "worktree", "unlock", q)
                git(env, repo, "worktree", "move", q, orig)
            journal_drop(p)
            notes.append(f"{q}: moved back to {orig} (an interrupted run left it in quarantine)")
        except (wo.OwnerError, OSError, GitError) as err:
            notes.append(f"{q}: could not be moved back ({err}); it stays")


def quarantine_remove(cfg: object, ctx: Ctx, it: Item, run_id: str, guard: Guard,
                      before: object, inside: object) -> bool:
    """Steps 1-4 above, called with the record's flock and this run's Git lock held and the
    second check passed; the caller releases a lock of this run that is still on it.name.
    False only when a step failed in a way the report must call a failure (a removal that
    failed, a move back that failed)."""
    env, repo, reason = ctx.env, ctx.repo, "lifecycle:" + run_id
    q = os.path.join(os.path.dirname(it.name), os.path.basename(it.name) + QUARANTINE + run_id)
    before(ctx, it)  # type: ignore[operator]  # test seam: after the second check
    if os.path.lexists(q):
        it.keep("quarantine-failed", f"{q} exists")
        return True
    try:
        jp = journal_write(env, run_id, repo, it, q)
    except OSError as e:
        it.keep("quarantine-failed", f"the journal cannot be written: {e.strerror or e}")
        return True
    try:
        git(env, repo, "worktree", "unlock", it.name)
        git(env, repo, "worktree", "move", it.name, q)
    except GitError as e:
        journal_drop(jp)
        it.keep("quarantine-failed", str(e))
        return True
    try:
        git(env, repo, "worktree", "lock", "--reason", reason, q)
    except GitError as e:
        return _back(env, repo, it, q, jp, ("quarantine-failed", f"cannot lock the quarantine: {e}"), locked=False)
    inside(ctx, it, q)  # type: ignore[operator]  # test seam: in quarantine, before the last checks
    bad = (recheck_worktree(ctx, it, reason, q) or open_problem(OpenFiles(cfg), q, it.name)  # type: ignore[arg-type]
           or guard.problem(q, it.name, it.admin))
    if bad:
        return _back(env, repo, it, q, jp, bad, locked=True)
    try:
        git(env, repo, "worktree", "unlock", q)
        git(env, repo, "worktree", "remove", q)
    except GitError as e:
        it.keep("remove-failed", f"{q}: {e}")
        return False
    journal_drop(jp)
    it.action, it.reason = "removed", "ended; archived; checked twice, then again in quarantine"
    return True


def _back(env: Dict[str, str], repo: str, it: Item, q: str, jp: str, why: Tuple[str, str], locked: bool) -> bool:
    try:
        if locked:
            git(env, repo, "worktree", "unlock", q)
        git(env, repo, "worktree", "move", q, it.name)
    except GitError as e:
        it.keep("left-in-quarantine", f"{why[1]}; moving it back failed ({e}): the next --apply tries again")
        return False
    journal_drop(jp)
    it.keep(*why)
    return True
