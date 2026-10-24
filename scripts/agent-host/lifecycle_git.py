"""Git reads for the local sweep (prune-merged-branches.sh --local-only; W-31 4.6 S2;
CUT-lifecycle-2026-10-24.md §2 principles 2-3, review 539 F1). Every read reports failure as
failure: a reflog or worktree list that cannot be read is an error the caller keeps the item
for, never an empty list.

Copies are judged by object reachability only (principle 2): a commit has a copy when it is
reachable from a ref the remote holds now. The remote's refs are read with git ls-remote
(read-only: no fetch, no push); remote-tracking refs can be stale (a branch deleted on Gitea
stays in refs/remotes until a fetch --prune), so they count only in --offline, which never
deletes. agent/** and land/** are not counted: agentd and 4.1's landing loop delete those on
their own rules, before S5 without keeping objects (R2, R3b).
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from typing import Dict, List, Optional, Set, Tuple

TRANSIENT = ("refs/heads/agent/", "refs/heads/land/")
HEX = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


class GitError(Exception):
    pass


class ReflogError(GitError):
    pass


def git_env(env: Dict[str, str]) -> Dict[str, str]:
    e = dict(env)
    e.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0", LC_ALL="C")
    e.pop("GIT_DIR", None)
    e.pop("GIT_WORK_TREE", None)
    return e


def git(env: Dict[str, str], cwd: str, *args: str, stdin: Optional[str] = None, timeout: float = 600) -> str:
    """stdout of git -C cwd args; GitError with the first stderr line on any failure."""
    try:
        r = subprocess.run(["git", "-C", cwd, *args], env=git_env(env), input=stdin, capture_output=True,
                           text=True, errors="surrogateescape", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GitError(f"git {args[0]}: {e}")
    if r.returncode != 0:
        first = (r.stderr.strip().splitlines() or ["no output"])[0]
        raise GitError(f"git {' '.join(args[:3])}: exit {r.returncode}: {first}")
    return r.stdout


def ok(env: Dict[str, str], cwd: str, *args: str) -> bool:
    try:
        git(env, cwd, *args)
        return True
    except GitError:
        return False


def repo_problem(env: Dict[str, str], repo: str) -> Optional[str]:
    """Why this repository's reachability cannot be judged by reading files, or None."""
    try:
        if git(env, repo, "rev-parse", "--is-shallow-repository").strip() != "false":
            return "shallow clone: reachability cannot be proven"
        fmt = git(env, repo, "rev-parse", "--show-ref-format").strip()
        if fmt not in ("files", "reftable"):  # git before 2.45 echoes the unknown option
            r = subprocess.run(["git", "-C", repo, "config", "--get", "extensions.refStorage"], env=git_env(env),
                               capture_output=True, text=True)
            if r.returncode not in (0, 1):
                return f"git config extensions.refStorage: exit {r.returncode}"
            fmt = r.stdout.strip() or "files"
    except GitError as e:
        return str(e)
    if fmt != "files":
        return f"ref storage {fmt!r}: the reflogs are not files this sweep reads"
    return None


def remote_refs(env: Dict[str, str], repo: str, offline: bool) -> Dict[str, str]:
    """{ref: commit-ish sha} the remote origin holds: heads (but agent/**, land/**) and tags,
    a tag peeled when ls-remote gives the peeled value."""
    out: Dict[str, str] = {}
    if offline:
        text = git(env, repo, "for-each-ref", "--format=%(objectname) %(refname)", "refs/remotes/origin/")
        for line in text.splitlines():
            sha, ref = line.split(" ", 1)
            if ref == "refs/remotes/origin/HEAD":
                continue
            ref = "refs/heads/" + ref[len("refs/remotes/origin/"):]
            if not ref.startswith(TRANSIENT):
                out[ref] = sha
        return out
    text = git(env, repo, "ls-remote", "origin", timeout=120)
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or not HEX.match(parts[0]):
            raise GitError(f"git ls-remote: unexpected line {line[:80]!r}")
        sha, ref = parts
        if not ref.startswith(("refs/heads/", "refs/tags/")) or ref.startswith(TRANSIENT):
            continue
        if ref.endswith("^{}"):
            out[ref[:-3]] = sha  # the peeled commit replaces the tag object
        elif ref not in out:
            out[ref] = sha
    return out


def commits_present(env: Dict[str, str], repo: str, shas: List[str]) -> Set[str]:
    """The shas that are commits in this repository's object store."""
    if not shas:
        return set()
    text = git(env, repo, "cat-file", "--batch-check=%(objectname) %(objecttype)", stdin="\n".join(shas) + "\n")
    have = set()
    for line in text.splitlines():
        parts = line.split(" ")
        if len(parts) == 2 and parts[1] == "commit":
            have.add(parts[0])
    return have


def without_copy(env: Dict[str, str], repo: str, shas: List[str], durable: List[str]) -> List[str]:
    """The commits reachable from shas that no durable sha reaches (git rev-list shas --not
    durable). A sha that is not a commit here makes it fail: that is an error, not 'none'."""
    if not shas:
        return []
    lines = list(dict.fromkeys(shas)) + ["--not"] + list(dict.fromkeys(durable))
    text = git(env, repo, "rev-list", "--stdin", stdin="\n".join(lines) + "\n")
    return [s for s in text.split() if s]


class Reflog:
    """A reflog file read whole: the shas in both columns and a digest of the bytes."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.shas: List[str] = []
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except FileNotFoundError:
            raw = b""  # no file: git keeps no reflog for this ref, so it holds no commit
            self.absent = True
        except OSError as e:
            raise ReflogError(f"reflog {path}: {e.strerror or e}")
        else:
            self.absent = False
        self.digest = hashlib.sha256(raw).hexdigest()
        for n, line in enumerate(raw.split(b"\n")):
            if not line:
                continue
            parts = line.split(b" ", 2)
            if len(parts) < 3:
                raise ReflogError(f"reflog {path}: line {n + 1} cannot be read")
            for p in parts[:2]:
                s = p.decode("ascii", "replace")
                if not HEX.match(s):
                    raise ReflogError(f"reflog {path}: line {n + 1} cannot be read")
                if s.strip("0"):
                    self.shas.append(s)


def worktree_list(env: Dict[str, str], repo: str) -> List[Dict[str, object]]:
    """git worktree list --porcelain -z, one dict per worktree, the main one first."""
    text = git(env, repo, "worktree", "list", "--porcelain", "-z")
    out: List[Dict[str, object]] = []
    cur: Dict[str, object] = {}
    for field in text.split("\0"):
        if field == "":
            if cur:
                out.append(cur)
                cur = {}
            continue
        key, _, val = field.partition(" ")
        if key == "worktree":
            cur = {"path": val}
        elif key == "HEAD":
            cur["head"] = val
        elif key == "branch":
            cur["branch"] = val
        elif key in ("detached", "bare"):
            cur[key] = True
        elif key in ("locked", "prunable"):
            cur[key] = val
    if cur:
        out.append(cur)
    if not out or any("path" not in w for w in out):
        raise GitError("git worktree list: output cannot be read")
    return out


def status_entries(env: Dict[str, str], worktree: str) -> List[Tuple[str, str]]:
    """(code, path) for everything git status reports, untracked and ignored included
    (ignored directories collapsed, as git shows them)."""
    text = git(env, worktree, "status", "--porcelain=v1", "-z", "--ignored=traditional",
               "--untracked-files=normal", "--ignore-submodules=none")
    out: List[Tuple[str, str]] = []
    fields = text.split("\0")
    i = 0
    while i < len(fields):
        f = fields[i]
        i += 1
        if not f:
            continue
        if len(f) < 4 or f[2] != " ":
            raise GitError("git status: output cannot be read")
        code, path = f[:2], f[3:]
        out.append((code, path))
        if code[0] in "RC":
            i += 1  # the rename's source path follows
    return out


def operation_markers(admin: str) -> List[str]:
    """Files git leaves while a rebase, merge, cherry-pick, revert or bisect is under way."""
    names = ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG", "sequencer")
    return [n for n in names if os.path.lexists(os.path.join(admin, n))]


def per_worktree_refs(env: Dict[str, str], worktree: str) -> List[str]:
    """Refs that live in the worktree's admin dir (refs/worktree, refs/bisect,
    refs/rewritten) and go with it."""
    text = git(env, worktree, "for-each-ref", "--format=%(refname)", "refs/worktree/", "refs/bisect/", "refs/rewritten/")
    return [ln for ln in text.splitlines() if ln]
