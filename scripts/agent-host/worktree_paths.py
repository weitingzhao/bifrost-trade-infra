"""Files and paths behind worktree records (W-31 round 4, 4.6 S3): the errors, bounded
reads that never take a prefix for a file (review 552 A1), the gitdir links of a linked
worktree read as Git reads them, relative ones included (review 553 A3, D1), and the
repositories the lifecycle tools scan. worktree_owner.py re-exports all of it.
"""

from __future__ import annotations

import os
import re
import stat
from typing import Dict, List, Optional, Tuple

OWNER = "bifrost-owner"
OWNER_LOCK = "bifrost-owner.lock"
RESUME_FAILED = "bifrost-owner.resume-failed"  # worktree_sessions.py: a resume that could not be published
HERE = os.path.dirname(os.path.abspath(__file__))
INFRA = os.path.dirname(os.path.dirname(HERE))
O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)


class OwnerError(Exception):
    """A record or a worktree that cannot be used; the message says why."""


class Busy(OwnerError):
    pass


class Gone(OwnerError):
    pass


def read_all(fd: int, limit: int) -> bytes:
    """A regular file read to its end; OwnerError when it holds more than limit bytes (a
    prefix is never taken for the file, review 552 A1)."""
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        raise OwnerError("not a regular file")
    parts: List[bytes] = []
    n = 0
    while True:
        b = os.read(fd, min(1 << 20, limit + 1 - n))
        if not b:
            return b"".join(parts)
        parts.append(b)
        n += len(b)
        if n > limit:
            raise OwnerError(f"larger than {limit} bytes")


def gitdir_target(admin: str) -> Optional[str]:
    """The worktree path an admin dir's gitdir file names (without /.git), a relative link
    resolved against the admin dir as Git does (review 553 A3, D1); None when there is no
    gitdir file. OwnerError when it cannot be read in full or is not a gitdir line."""
    path = os.path.join(admin, "gitdir")
    try:
        t = _read_small(path)
    except FileNotFoundError:
        return None
    except OSError as e:
        raise OwnerError(f"{path}: {e.strerror or e}")
    if not t.endswith(os.sep + ".git") and t != ".git":
        raise OwnerError(f"{path} does not name a .git file")
    full = t if os.path.isabs(t) else os.path.join(admin, t)
    return os.path.realpath(os.path.dirname(os.path.normpath(full)))


def _read_small(path: str) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | O_CLOEXEC)
    try:
        return read_all(fd, 8192).decode("utf-8", "surrogateescape").strip()
    except OwnerError as e:
        raise OwnerError(f"{path}: {e}")
    finally:
        os.close(fd)


def admin_of(worktree: str) -> Tuple[str, str]:
    """(admin dir, common dir) of a linked worktree, checked both ways: <worktree>/.git names
    <common>/worktrees/<name>, and that admin dir's gitdir file names <worktree>/.git."""
    dotgit = os.path.join(worktree, ".git")
    try:
        line = _read_small(dotgit)
    except (OSError, OwnerError) as e:
        raise OwnerError(f"{dotgit} cannot be read as a gitdir file: {getattr(e, 'strerror', None) or e}")
    if not line.startswith("gitdir: "):
        raise OwnerError(f"{dotgit} is not a gitdir file")
    target = line[len("gitdir: "):]
    admin = os.path.realpath(target if os.path.isabs(target) else os.path.join(worktree, target))
    parent = os.path.dirname(admin)
    if os.path.basename(parent) != "worktrees":
        raise OwnerError(f"{dotgit} does not name a <repo>/.git/worktrees/<name> dir")
    try:
        back = _read_small(os.path.join(admin, "gitdir"))
    except (OSError, OwnerError) as e:
        raise OwnerError(f"{admin}/gitdir cannot be read: {getattr(e, 'strerror', None) or e}")
    back = back if os.path.isabs(back) else os.path.join(admin, back)
    if os.path.realpath(back) != os.path.realpath(dotgit):
        raise OwnerError(f"{admin}/gitdir names {back}, not this worktree")
    return admin, os.path.dirname(parent)


# The repositories the tools scan: the list file under WORKSPACE, then the real clones (a
# .git directory, not a gitfile) directly under AGENT_WORK, such as bifrost-finance.

def workspace(env: Dict[str, str]) -> str:
    return os.path.realpath(env.get("WORKSPACE", "").strip() or os.path.dirname(INFRA))


def status_dir(env: Dict[str, str]) -> str:
    """Where the sweeps keep their state (LIFECYCLE_STATUS_DIR, else AGENT_WORK/status), as
    disk_guard_base.load_config computes it."""
    return os.path.realpath(env.get("LIFECYCLE_STATUS_DIR", "").strip() or os.path.join(agent_work(env), "status"))


def agent_work(env: Dict[str, str]) -> str:
    home = env.get("HOME") or os.path.expanduser("~")
    return os.path.realpath(env.get("AGENT_WORK", "").strip() or os.path.join(home, "agent-work"))


def known_repos(env: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """(repository dirs, notes). Raises OwnerError when the list file cannot be read."""
    listing = env.get("LIFECYCLE_REPOS_FILE", "").strip() or os.path.join(INFRA, "agent-config", "gitea-primary.txt")
    try:
        with open(listing, encoding="utf-8") as f:
            names = [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    except OSError as e:
        raise OwnerError(f"cannot read the repository list {listing}: {e.strerror or e}")
    ws, aw = workspace(env), agent_work(env)
    repos: List[str] = []
    notes: List[str] = []
    for n in names:
        if not re.match(r"^[A-Za-z0-9._-]+$", n) or n in (".", ".."):
            notes.append(f"{listing}: {n!r} is not a repository name")
            continue
        d = os.path.join(ws, n)
        if _is_clone(d):
            repos.append(d)
        else:
            notes.append(f"{n}: no checkout with a .git directory at {d}")
    try:
        entries = sorted(os.listdir(aw))
    except OSError as e:
        notes.append(f"cannot list AGENT_WORK {aw}: {e.strerror or e}; its clones are not scanned")
        entries = []
    for n in entries:
        d = os.path.join(aw, n)
        if d not in repos and _is_clone(d):
            repos.append(d)
    return repos, notes


def _is_clone(d: str) -> bool:
    try:
        return stat.S_ISDIR(os.lstat(d).st_mode) and stat.S_ISDIR(os.lstat(os.path.join(d, ".git")).st_mode)
    except OSError:
        return False


def registered(repos: List[str]) -> Tuple[List[str], List[str]]:
    """(admin dirs holding a record, notes about dirs that could not be read)."""
    out: List[str] = []
    notes: List[str] = []
    for r in repos:
        wt = os.path.join(r, ".git", "worktrees")
        try:
            names = sorted(os.listdir(wt))
        except FileNotFoundError:
            continue
        except OSError as e:
            notes.append(f"{wt}: {e.strerror or e}")
            continue
        for n in names:
            admin = os.path.join(wt, n)
            if os.path.lexists(os.path.join(admin, OWNER)):
                out.append(admin)
    return out, notes
