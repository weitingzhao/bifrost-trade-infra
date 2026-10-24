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

import contextlib
import fnmatch
import hashlib
import json
import os
import stat
from typing import Dict, List, Optional, Tuple

import worktree_owner as wo
from disk_guard_base import ConfigError
from disk_guard_roots import OpenFiles, parse_registry
from disk_guard_state import _private_dir, _read_private, _write_private
from lifecycle_checks import Why, open_problem, root_problem
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
        self.patterns: List[str] = []
        for path, req in registries:
            entries, errors = parse_registry(path, req)
            if errors:  # an incomplete list of what disk-guard removes cannot clear the archive (552 D)
                raise ConfigError("disk-guard's cache-root registry cannot be read in full: " + "; ".join(errors[:3]))
            self.patterns += [e.pattern for e in entries]
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


def _ident(path: str) -> Optional[Tuple[int, int]]:
    """(dev, ino) of a real directory at path; None when nothing is there. OSError for a
    symlink or anything that is not a directory."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(st.st_mode):
        raise OSError(f"{path} is not a directory (a symlink is not followed)")
    return (st.st_dev, st.st_ino)


def _parent_ok(parent: str, roots: List[Tuple[str, str]]) -> Why:
    if any(parent in (g, r) for g, r in roots):
        return None
    return root_problem(parent, roots)


def _same(target: Optional[str], path: str) -> bool:
    return target is not None and target == os.path.realpath(path)


def _closed(orig: str, q: str, want: Tuple[int, ...], admin: str) -> bool:
    """The one test a settled entry must pass (review 553 D3): the directory the journal
    recorded is at the original path, its .git and the admin dir's gitdir name each other,
    and no quarantine is left."""
    try:
        return (_ident(orig) == want and _same(wo.gitdir_target(admin), orig) and _dotgit_names(orig, admin)
                and not os.path.lexists(q))
    except (OSError, wo.OwnerError):
        return False


def _admin_problem(repo: str, admin: str) -> Optional[str]:
    """Why admin is not a real directory directly under this repository's .git/worktrees
    (review 554 A2): the literal path must name <.git>/worktrees/<name>, and with every
    symlink resolved it must still be that place, so neither the admin dir nor the worktrees
    dir above it may be a link that leads elsewhere. None when it is, or when nothing is there."""
    dotgit = os.path.realpath(os.path.join(repo, ".git"))
    parent = os.path.dirname(admin)
    if os.path.basename(parent) != "worktrees" or os.path.realpath(os.path.dirname(parent)) != dotgit:
        return f"the journal's admin dir is not under {repo}/.git/worktrees"
    try:
        st = os.lstat(admin)
    except FileNotFoundError:
        return None
    except OSError as e:
        return f"{admin}: {e.strerror or e}"
    if not stat.S_ISDIR(st.st_mode):
        return f"{admin} is not a directory (a symlink is not followed)"
    if os.path.realpath(admin) != os.path.join(dotgit, "worktrees", os.path.basename(admin)):
        return f"{admin} resolves outside {repo}/.git/worktrees"
    return None


def _point_admin_at(repo: str, admin: str, orig: str) -> None:
    """Rewrite this admin dir's gitdir to name <orig>/.git, in the form (relative or absolute)
    it had. Only this one link of this one worktree is written: git worktree repair would
    walk every linked worktree of the repository (review 553 A2). The admin dir is checked
    again and opened once, without following a link, and the read, the temporary file and
    the replace all go through that one handle (review 554 A2)."""
    bad = _admin_problem(repo, admin)
    if bad:
        raise OSError(bad)
    dfd = os.open(admin, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        want = os.lstat(os.path.join(os.path.realpath(os.path.join(repo, ".git")), "worktrees", os.path.basename(admin)))
        got = os.fstat(dfd)
        if (got.st_dev, got.st_ino) != (want.st_dev, want.st_ino):
            raise OSError(f"{admin} changed while it was checked")
        fd = os.open("gitdir", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dfd)
        try:
            old = wo.read_all(fd, 8192).decode("utf-8", "surrogateescape").strip()
        finally:
            os.close(fd)
        dotgit = os.path.join(orig, ".git")
        text = dotgit if os.path.isabs(old) else os.path.relpath(dotgit, admin)
        tmp = "gitdir.lifecycle-tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=dfd)
        try:
            os.write(fd, (text + "\n").encode("utf-8", "surrogateescape"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, "gitdir", src_dir_fd=dfd, dst_dir_fd=dfd)
    finally:
        os.close(dfd)


def settle(env: Dict[str, str], e: Dict[str, object], roots: List[Tuple[str, str]], apply: bool,
           lock_held: bool = False) -> Tuple[bool, str]:
    """Bring a journaled quarantine back to its original path when its shape is unambiguous
    (reviews 552 A4, C1, 553 A2, A3, D3); (settled, what was found or done). Settled means the
    entry may go, and only after _closed() (or "removed") holds.

    The directory is recognised only by the device and inode the journal recorded, the admin
    dir only by the path it recorded, and both paths must lie in one parent that this run's
    roots allow, with no symlink. Links may be relative (worktree.useRelativePaths); they
    are resolved as Git does. Shapes, by where the directory is and where the admin dir's
    gitdir points:
      at q, gitdir q        a finished quarantine: git worktree move q -> original
      at q, gitdir original a move that stopped after the rename: rename q -> original
      at original, gitdir q a move that stopped after Git's update: rewrite that one gitdir,
                            under the record's lock, and check both links again
      at original, gitdir original  back already (or never moved), when _closed() holds
      neither, no admin dir  removed
    Anything else (both, another directory, a symlink, an admin dir that is not a real
    directory directly under the repo's .git/worktrees, the original path taken, links that
    do not name each other) is reported and left alone; the report says when it needs repair
    by hand."""
    try:
        repo, orig, q, admin = (str(e[k]) for k in ("repo", "original", "quarantine", "admin"))
        want = tuple(e["ident"])  # type: ignore[arg-type]
        parent = os.path.dirname(orig)
        if os.path.dirname(q) != parent or QUARANTINE not in os.path.basename(q):
            return False, f"{q}: the journal does not name a quarantine beside {orig}"
        bad = _parent_ok(parent, roots)
        if bad:
            return False, f"{q}: {bad[1]}; left as it is"
        bad_admin = _admin_problem(repo, admin)
        if bad_admin:
            return False, f"{q}: {bad_admin}; left as it is"
        at_o, at_q = _ident(orig), _ident(q)
        has_admin = os.path.lexists(admin)
        target = wo.gitdir_target(admin) if has_admin else None
    except (KeyError, TypeError, ValueError, OSError, wo.OwnerError) as err:
        return False, f"journal entry for {e.get('quarantine')}: {err}; left as it is"
    if at_o is None and at_q is None:
        return (not has_admin), (f"{q}: removed" if not has_admin else f"{q}: no directory at either path but {admin} is there; left as it is")
    if at_q == want and os.path.lexists(orig) and at_o != want:
        return False, f"{q}: {orig} is taken by something else; left in quarantine"
    if (at_o is not None and at_o != want) or (at_q is not None and at_q != want) or (at_o and at_q):
        return False, f"{q}: the directories at {orig} and {q} are not (only) the one the journal recorded; left as they are"
    if not has_admin:
        return False, f"{q}: {admin} is gone but the directory is there; left as it is"
    where = "q" if at_q else "orig"
    points = "q" if _same(target, q) else "orig" if _same(target, orig) else None
    if points is None:
        return False, f"{q}: {admin}/gitdir names neither path; needs repair by hand"
    if where == "orig" and points == "orig":
        if _closed(orig, q, want, admin):
            return True, f"{q}: {orig} is back in place"
        return False, f"{q}: {orig} is back but its links do not name each other; needs repair by hand"
    if not apply:
        return False, f"{q}: left in quarantine by run {e.get('run_id')}; --apply moves it back to {orig}"
    if not _dotgit_names(q if where == "q" else orig, admin):
        return False, f"{q}: its .git file does not name {admin}; needs repair by hand"
    try:
        with (contextlib.nullcontext() if lock_held else wo.OwnerLock(admin, 0)):
            if where == "q" and points == "q":
                if os.path.lexists(orig):
                    return False, f"{q}: {orig} is taken; left in quarantine"
                _unlock_ours(env, repo, q)
                git(env, repo, "worktree", "move", q, orig)
            elif where == "q":
                if os.path.lexists(orig):
                    return False, f"{q}: {orig} is taken; left in quarantine"
                os.rename(q, orig)  # same parent; Git already names orig
            else:
                _point_admin_at(repo, admin, orig)
            _unlock_ours(env, repo, orig)
    except (wo.OwnerError, OSError, GitError) as err:
        failed: Optional[BaseException] = err  # a step may have done its work and still failed
    else:
        failed = None
    if not _closed(orig, q, want, admin):
        return False, f"{q}: could not be moved back ({failed or 'its links do not check out afterwards'}); needs repair by hand"
    return True, f"{q}: moved back to {orig}" + (f" (a step reported: {failed})" if failed else "")


def _dotgit_names(path: str, admin: str) -> bool:
    """<path>/.git is a gitdir file naming admin (one way: during a half move the admin dir's
    gitdir names the other path)."""
    try:
        fd = os.open(os.path.join(path, ".git"), os.O_RDONLY | os.O_NOFOLLOW)
        try:
            line = wo.read_all(fd, 8192).decode("utf-8", "surrogateescape").strip()
        finally:
            os.close(fd)
    except (OSError, wo.OwnerError):
        return False
    if not line.startswith("gitdir: "):
        return False
    t = line[len("gitdir: "):]
    return os.path.realpath(t if os.path.isabs(t) else os.path.join(path, t)) == os.path.realpath(admin)


def _unlock_ours(env: Dict[str, str], repo: str, path: str) -> None:
    for wt in worktree_list(env, repo):
        if str(wt["path"]) == path and str(wt.get("locked", "")).startswith("lifecycle:"):
            git(env, repo, "worktree", "unlock", path)


def restore(env: Dict[str, str], repos: List[str], roots: List[Tuple[str, str]], apply: bool, notes: List[str]) -> None:
    """Settle every journaled quarantine of an interrupted run (apply), or report them."""
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
            if not isinstance(e, dict) or str(e.get("repo")) not in repos:
                raise ValueError("not an entry of a scanned repository")
        except (OSError, ValueError, TypeError) as err:
            notes.append(f"journal entry {n} cannot be used ({type(err).__name__}): its worktree stays where it is")
            continue
        done, note = settle(env, e, roots, apply)
        if done and apply:
            journal_drop(p)
        notes.append(note + ("" if not done else " (journal entry dropped)" if apply else " (entry stays until --apply)"))


def quarantine_remove(cfg: object, ctx: Ctx, it: Item, run_id: str, guard: Guard,
                      before: object, inside: object) -> bool:
    """Steps 1-4 above, called with the record's flock and this run's Git lock held and the
    second check passed; the caller releases a lock of this run that is still on it.name.
    False only when a step failed in a way the report must call a failure (a removal that
    failed, a quarantine that could not be settled)."""
    env, repo, reason = ctx.env, ctx.repo, "lifecycle:" + run_id
    q = os.path.join(os.path.dirname(it.name), os.path.basename(it.name) + QUARANTINE + run_id)
    before(ctx, it)  # type: ignore[operator]  # test seam: after the second check
    if os.path.lexists(q):
        it.keep("quarantine-failed", f"{q} exists")
        return True
    entry = {"run_id": run_id, "repo": repo, "original": it.name, "quarantine": q, "ident": list(it.ident),
             "admin": it.admin, "head": it.head}
    try:
        jp = journal_write(env, run_id, repo, it, q)
    except OSError as e:
        it.keep("quarantine-failed", f"the journal cannot be written: {e.strerror or e}")
        return True
    try:
        git(env, repo, "worktree", "unlock", it.name)
        git(env, repo, "worktree", "move", it.name, q)
        git(env, repo, "worktree", "lock", "--reason", reason, q)
    except GitError as e:  # the move may have stopped half way: settle it from the journal (552 C1)
        return _back(env, ctx.roots, it, entry, jp, ("quarantine-failed", str(e)))
    inside(ctx, it, q)  # type: ignore[operator]  # test seam: in quarantine, before the last checks
    bad = (recheck_worktree(ctx, it, reason, q) or open_problem(OpenFiles(cfg), q, it.name)  # type: ignore[arg-type]
           or guard.problem(q, it.name, it.admin))
    if bad:
        return _back(env, ctx.roots, it, entry, jp, bad)
    try:
        git(env, repo, "worktree", "unlock", q)
        git(env, repo, "worktree", "remove", q)
    except GitError as e:
        it.keep("remove-failed", f"{q}: {e}")
        return False
    journal_drop(jp)
    it.action, it.reason = "removed", "ended; archived; checked twice, then again in quarantine"
    return True


def _back(env: Dict[str, str], roots: List[Tuple[str, str]], it: Item, entry: Dict[str, object], jp: str,
          why: Tuple[str, str]) -> bool:
    done, note = settle(env, entry, roots, True, lock_held=True)  # the caller holds the record's flock
    if not done:
        it.keep("left-in-quarantine", f"{why[1]}; {note}: the journal entry stays for the next --apply")
        return False
    journal_drop(jp)
    it.keep(*why)
    return True
