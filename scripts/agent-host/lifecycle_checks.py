"""The content checks of the local sweep (W-31 4.6 S2; CUT-lifecycle-2026-10-24.md §2
principles 3-6; reviews 539 F1, 551 A1, A2, A5). Each returns None, or (code, why) for the
reason a worktree stays; a read that fails is a reason, never "nothing there".

- root_problem: the path lies strictly below a registered root, with nothing but plain
  directories (no symlink) from the root down.
- admin_state: every entry of the worktree's Git admin dir is one this sweep knows. The
  pseudo refs ORIG_HEAD and FETCH_HEAD name commits that go with the admin dir: they are
  archived like reflog commits. AUTO_MERGE names a tree (the conflicted state a merge, rebase
  or cherry-pick wrote; Git 2.42+ leaves it behind after the operation ends): --apply wraps
  it in a commit and archives that. An operation under way (MERGE_HEAD, CHERRY_PICK_HEAD,
  REVERT_HEAD, REBASE_HEAD, BISECT_*, rebase-merge, rebase-apply, sequencer, a .lock), a
  reflog other than logs/HEAD, a file under refs/, or anything unknown or unreadable keeps it.
- content_problem: git status shows nothing (a deletion included), no submodule, no index
  entry marked assume-unchanged or skip-worktree. Ignored content may go only inside a cache
  root the record names with a kind: the whole root must pass disk-guard's layout check
  for that kind (disk_guard_layout.validate), lie on the worktree's filesystem along its whole
  path and hold no mount point. A cache root without a kind (node_modules: no tool can tell
  its files from someone's) keeps the worktree whenever git shows anything in it; its size
  goes into the report so the cost is visible.
- open_problem: lsof's answer is complete and shows nothing open (no file, no cwd) under it.
"""

from __future__ import annotations

import hashlib
import os
import stat
from typing import Dict, List, Optional, Tuple

import worktree_owner as wo
from disk_guard_base import O_DIR, Chain, Problem
from disk_guard_layout import du, validate
from lifecycle_git import HEX, GitError, git, status_entries

Why = Optional[Tuple[str, str]]
ALLOWED_FILES = {"HEAD", "ORIG_HEAD", "FETCH_HEAD", "AUTO_MERGE", "commondir", "gitdir", "index", "locked",
                 "config.worktree", "COMMIT_EDITMSG", wo.OWNER, wo.OWNER_LOCK}
OPERATION = {"MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD", "MERGE_MSG", "MERGE_MODE",
             "MERGE_AUTOSTASH", "SQUASH_MSG", "rebase-merge", "rebase-apply", "sequencer"}
PSEUDO = ("ORIG_HEAD", "FETCH_HEAD")


def root_problem(path: str, roots: List[Tuple[str, str]]) -> Why:
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


class AdminState:
    def __init__(self) -> None:
        self.problem: Why = None
        self.pseudo: List[str] = []  # commits ORIG_HEAD and FETCH_HEAD name
        self.auto_merge: Optional[str] = None  # the tree AUTO_MERGE names
        self.digest = ""  # of HEAD, ORIG_HEAD, FETCH_HEAD and AUTO_MERGE as bytes


def _only(admin: str, sub: str, allowed: Tuple[str, ...], code: str) -> Why:
    """Under admin/sub: only plain directories, and files named in allowed."""
    errs: List[str] = []
    for dp, dns, fns in os.walk(os.path.join(admin, sub), onerror=lambda e: errs.append(str(e))):
        for n in dns + fns:
            p = os.path.join(dp, n)
            rel = os.path.relpath(p, admin)
            try:
                st = os.lstat(p)
            except OSError as e:
                return "admin-unreadable", f"{rel}: {e.strerror or e}"
            if stat.S_ISLNK(st.st_mode) or not (stat.S_ISDIR(st.st_mode) or (stat.S_ISREG(st.st_mode) and rel in allowed)):
                return code, f"{rel} in the admin dir"
    return ("admin-unreadable", errs[0]) if errs else None


def admin_state(env: Dict[str, str], repo: str, admin: str) -> AdminState:
    a = AdminState()
    try:
        names = sorted(os.listdir(admin))
    except OSError as e:
        a.problem = ("admin-unreadable", f"{admin}: {e.strerror or e}")
        return a
    for n in names:
        try:
            st = os.lstat(os.path.join(admin, n))
        except OSError as e:
            a.problem = ("admin-unreadable", f"{n}: {e.strerror or e}")
            return a
        if n in OPERATION or n.startswith("BISECT_") or (n.endswith(".lock") and n != wo.OWNER_LOCK):
            a.problem = ("operation-in-progress", n)
            return a
        plain = not stat.S_ISLNK(st.st_mode)
        if n in ("logs", "refs") and plain and stat.S_ISDIR(st.st_mode):
            bad = _only(admin, n, ("logs/HEAD",), "admin-entry-unknown") if n == "logs" else _only(admin, n, (), "per-worktree-refs")
            if bad:
                a.problem = bad
                return a
        elif not (n in ALLOWED_FILES and plain and stat.S_ISREG(st.st_mode)):
            a.problem = ("admin-entry-unknown", f"{n} in the admin dir is not something this sweep knows")
            return a
    h = hashlib.sha256()
    for n in ("HEAD",) + PSEUDO + ("AUTO_MERGE",):
        try:
            with open(os.path.join(admin, n), "rb") as f:
                raw = f.read(1 << 20)
        except FileNotFoundError:
            continue
        except OSError as e:
            a.problem = ("pseudo-ref-unreadable", f"{n}: {e.strerror or e}")
            return a
        h.update(n.encode() + b"\0" + raw + b"\0")
        if n == "HEAD":
            continue
        lines = [ln for ln in raw.decode("ascii", "replace").splitlines() if ln.strip()]
        shas = [ln.split("\t")[0].strip() for ln in lines]
        if not shas or not all(HEX.match(x) for x in shas) or (n in ("ORIG_HEAD", "AUTO_MERGE") and len(shas) != 1):
            a.problem = ("pseudo-ref-unreadable", f"{n} does not name commits this sweep can read")
            return a
        if n == "AUTO_MERGE":
            try:
                a.auto_merge = git(env, repo, "rev-parse", "--verify", "--quiet", shas[0] + "^{tree}").strip()
            except GitError:
                a.problem = ("pseudo-ref-unreadable", f"AUTO_MERGE names {shas[0][:12]}, which is not a tree here")
                return a
            continue
        for x in shas:
            try:
                a.pseudo.append(git(env, repo, "rev-parse", "--verify", "--quiet", x + "^{commit}").strip())
            except GitError:
                a.problem = ("pseudo-ref-unreadable", f"{n} names {x[:12]}, which is not a commit here")
                return a
    a.digest = h.hexdigest()
    return a


def _cache_root(path: str, root: Dict[str, object], mounts: Optional[List[str]]) -> Tuple[Why, int]:
    """(why the declared root keeps the worktree, its size in bytes for the report)."""
    rel = str(root["path"])
    kind = root.get("kind")
    top = os.path.join(path, rel)
    if not kind:
        size, _ = du(top)
        return ("cache-root-unverified", f"{rel} holds {size} bytes and no layout check exists for it (kind not given)"), size
    if mounts is None:
        return ("cache-root-mount-unknown", "the mount table could not be read"), 0
    real = os.path.realpath(top)
    hit = next((m for m in mounts if m == real or m.startswith(real + os.sep)), None)
    if hit:
        return ("cache-root-mount", f"{hit} is a mount point at or inside {rel}"), 0
    try:
        wfd = os.open(path, O_DIR)
    except OSError as e:
        return ("cache-root-unreadable", f"{path}: {e.strerror or e}"), 0
    try:
        dev = os.fstat(wfd).st_dev
        with Chain(wfd, rel) as ch:
            if any(d != dev for d, _ in ch.ids):
                return ("cache-root-mount", f"{rel} or a directory above it is on another filesystem"), 0
            w = validate(ch.fd, str(kind))
            return None, w.bytes
    except Problem as p:
        return (f"cache-root-{p.code}", f"{rel}: {p.detail}"), 0
    except OSError as e:
        return ("cache-root-unreadable", f"{rel}: {e.strerror or e}"), 0
    finally:
        os.close(wfd)


def content_problem(env: Dict[str, str], path: str, record: Dict[str, object],
                    mounts: Optional[List[str]], sizes: Optional[Dict[str, int]] = None) -> Why:
    try:
        entries = status_entries(env, path)
        gitmodules = git(env, path, "ls-files", "--", ".gitmodules").strip()
        # assume-unchanged (lower-case tag) and skip-worktree (S) entries hide their changes from status
        hidden = [ln[2:] for ln in git(env, path, "ls-files", "-v").splitlines() if ln[:1].islower() or ln[:1] == "S"]
    except GitError as e:
        return "git-error", str(e)
    if gitmodules:
        return "submodules", "the worktree has submodules"
    if hidden:
        return "hidden-changes", f"{len(hidden)} index entries are assume-unchanged or skip-worktree, e.g. {hidden[0]}"
    roots = [r for r in record.get("cache_roots", []) if isinstance(r, dict)]
    checked: Dict[str, Why] = {}
    for code, p in entries:
        if code == "!!":
            p2 = p.rstrip("/")
            hit = next((r for r in roots if p2 == r["path"] or p2.startswith(str(r["path"]) + "/")), None)
            if hit is None:
                return "ignored", f"ignored {p} is not inside a cache root its record names"
            if hit["path"] not in checked:
                why, size = _cache_root(path, hit, mounts)
                checked[str(hit["path"])] = why
                if sizes is not None:
                    sizes[str(hit["path"])] = size
            if checked[str(hit["path"])]:
                return checked[str(hit["path"])]
            continue
        if code == "??":
            return "untracked", f"untracked {p}"
        return "changes", f"uncommitted change {code.strip()} {p}"
    return None


def open_problem(lsof: object, *paths: str) -> Why:
    """Nothing open (file or cwd) under any of paths, by a complete lsof snapshot."""
    roots = [x for p in paths for x in (p, os.path.realpath(p))]
    p = lsof.problem_for(*roots)  # type: ignore[attr-defined]
    if p:
        return "lsof-unknown", p
    hit = lsof.under(*roots)  # type: ignore[attr-defined]
    if hit:
        return "in-use", f"open: {hit}"
    return None
