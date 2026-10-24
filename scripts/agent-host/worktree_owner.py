"""Worktree registration and end records (W-31 round 4, 4.6 S3; CUT-lifecycle-2026-10-24.md
§4.2; review 539 F3, F4). new-worktree.sh, the session hook and the local sweep
(prune-merged-branches.sh --local-only) all read and write records through this module.

new-worktree.sh writes a record into the Git admin dir of each worktree it makes:
<common dir>/worktrees/<name>/bifrost-owner, JSON. Git never commits that directory and
removes it with the worktree, so the record lives exactly as long as the worktree.

    schema 1; work (W-n, TD-n, BI-n or LANE-...); session (the Claude Code CLI session id,
    CLAUDE_CODE_SESSION_ID, or an id a wrapper passes); host_session (CLAUDE_CODE_HOST_SESSION_ID,
    may be empty); purpose; created_at; cache_roots ({path, kind}: a path inside the worktree
    meant for a cache, kind one of disk-guard's layouts or null); branch (null when detached);
    branch_created (new-worktree.sh made the branch for this work); base; renewed_at;
    lease_until; once ended: ended_at, ended_by, end_reason. voided_ends keeps the last five
    ends a later use voided; taken_from the sessions that handed it over (--take); foreign_use
    a session other than its owner that started inside it (worktree_sessions.py).

States, in order: in use (no ended_at) -> ended (a positive event wrote ended_at: the
SessionEnd hook, new-worktree.sh --end, a wrapper on exit; a later end moves it forward) ->
in use again when its session starts again (the SessionStart hook writes the session's
"active since" marker first, then voids the end; see worktree_sessions.py). Nothing is
inferred from time: a record without ended_at stays in use however old it is, and a
worktree without a record is never removed by a sweep (D-L8). Another session uses a
worktree only after new-worktree.sh --take hands it over: the old session's later end events
then match nothing.

Every read-modify-write of a record, and the sweep's last check and removal, hold flock on
<admin>/bifrost-owner.lock. A renewal is therefore ordered either before the sweep's last
check (the record changed: the worktree stays) or after the removal (the record is gone).
"""

from __future__ import annotations

import calendar
import errno
import fcntl
import json
import os
import re
import stat
import time
from typing import Dict, List, Optional, Tuple

from disk_guard_base import KINDS
from disk_guard_state import write_report

OWNER = "bifrost-owner"
OWNER_LOCK = "bifrost-owner.lock"
RESUME_FAILED = "bifrost-owner.resume-failed"  # worktree_sessions.py: a resume that could not be published
SCHEMA = 1
TIME_FMT = "%Y-%m-%dT%H:%M:%SZ"
MAX_RECORD = 64 * 1024
WORK_RE = re.compile(r"^(?:(?:W|TD|BI)-[0-9]{1,6}|LANE-[A-Za-z0-9._-]{1,64})$")
SESSION_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
HERE = os.path.dirname(os.path.abspath(__file__))
INFRA = os.path.dirname(os.path.dirname(HERE))
DEFAULT_LEASE_HOURS = 12.0
O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)


class OwnerError(Exception):
    """A record or a worktree that cannot be used; the message says why."""


class Busy(OwnerError):
    pass


class Gone(OwnerError):
    pass


def now_ts() -> float:
    return time.time()


def fmt(ts: float) -> str:
    return time.strftime(TIME_FMT, time.gmtime(int(ts)))


def to_seconds(v: object) -> Optional[float]:
    """Seconds since the epoch for a TIME_FMT string, None for anything else."""
    if not isinstance(v, str) or len(v) != 20:
        return None
    try:
        return float(calendar.timegm(time.strptime(v, TIME_FMT)))
    except ValueError:
        return None


def canonical_rel(p: object) -> bool:
    """A relative path a/b/c with no empty, '.' or '..' segment and no surrounding space."""
    return (isinstance(p, str) and p != "" and p == p.strip() and not p.startswith("/")
            and all(s not in ("", ".", "..") for s in p.split("/")) and "\0" not in p)


def problems(rec: object) -> List[str]:
    """What is wrong with a record; empty when it is usable."""
    if not isinstance(rec, dict):
        return ["not a JSON object"]
    out = []
    if rec.get("schema") != SCHEMA:
        out.append(f"schema is not {SCHEMA}")
    if not isinstance(rec.get("work"), str) or not WORK_RE.match(rec["work"]):
        out.append("work is not W-n, TD-n, BI-n or LANE-...")
    if not isinstance(rec.get("session"), str) or not SESSION_RE.match(rec["session"]):
        out.append("session is missing or not an id")
    for k in ("host_session", "purpose", "base"):
        if not isinstance(rec.get(k, ""), str):
            out.append(f"{k} is not a string")
    for k in ("created_at", "renewed_at", "lease_until"):
        if to_seconds(rec.get(k)) is None:
            out.append(f"{k} is not a time ({TIME_FMT})")
    if "ended_at" in rec and to_seconds(rec["ended_at"]) is None:
        out.append(f"ended_at is not a time ({TIME_FMT})")
    for k in ("ended_by", "end_reason"):
        if k in rec and not isinstance(rec[k], str):
            out.append(f"{k} is not a string")
    roots = rec.get("cache_roots", [])
    if not isinstance(roots, list) or not all(
            isinstance(r, dict) and canonical_rel(r.get("path")) and (r.get("kind") is None or r.get("kind") in KINDS)
            for r in roots):
        out.append("cache_roots is not a list of {path: canonical relative path, kind: null or a disk-guard kind}")
    if rec.get("branch") is not None and not isinstance(rec.get("branch"), str):
        out.append("branch is neither null nor a string")
    if not isinstance(rec.get("branch_created", False), bool):
        out.append("branch_created is not true or false")
    for k in ("voided_ends", "taken_from"):
        if not isinstance(rec.get(k, []), list):
            out.append(f"{k} is not a list")
    gen = rec.get("generation", 1)
    if type(gen) is not int or gen < 1:
        out.append("generation is not a whole number of at least 1")
    if "owner_since" in rec and to_seconds(rec["owner_since"]) is None:
        out.append(f"owner_since is not a time ({TIME_FMT})")
    fu = rec.get("foreign_use")
    if fu is not None and not (isinstance(fu, dict) and isinstance(fu.get("session"), str) and to_seconds(fu.get("at")) is not None):
        out.append("foreign_use is not {session, at}")
    return out


def end_evidence(rec: Dict[str, object], now: float, grace: float) -> Tuple[Optional[str], str]:
    """(None, "") when the record proves its session ended at least grace seconds ago and
    nothing used the worktree since; else (code, why)."""
    if "ended_at" not in rec:
        return "not-ended", "the record has no ended_at: its session has not said it ended"
    ended = to_seconds(rec["ended_at"])
    renewed = to_seconds(rec.get("renewed_at"))
    lease = to_seconds(rec.get("lease_until"))
    if ended is None or renewed is None or lease is None:
        return "record-unusable", "a time in the record cannot be read"
    if ended > now:
        return "ended-in-future", f"ended_at {rec['ended_at']} is later than now"
    if renewed > ended or lease > ended:
        return "lease-renewed", "the lease was renewed after ended_at"
    if now - ended < grace:
        return "end-too-recent", f"ended at {rec['ended_at']}, less than {grace / 60:.0f} min ago"
    return None, ""


def new_record(work: str, session: str, host_session: str, purpose: str, branch: Optional[str],
               branch_created: bool, base: str, cache_roots: List[Dict[str, object]], now: float,
               lease_hours: float) -> Dict[str, object]:
    return {
        "schema": SCHEMA, "work": work, "session": session, "host_session": host_session,
        "purpose": purpose, "created_at": fmt(now), "cache_roots": list(cache_roots),
        "branch": branch, "branch_created": branch_created, "base": base,
        "renewed_at": fmt(now), "lease_until": fmt(now + lease_hours * 3600),
        "generation": 1, "owner_since": fmt(now),
    }


def renew(rec: Dict[str, object], now: float, lease_hours: float) -> bool:
    """A use: renewed_at now, the lease extended, an end voided. True when an end was voided."""
    voided = False
    if "ended_at" in rec:
        ends = list(rec.get("voided_ends") or [])
        ends.append({"ended_at": rec.pop("ended_at"), "ended_by": rec.pop("ended_by", ""),
                     "end_reason": rec.pop("end_reason", ""), "voided_at": fmt(now)})
        rec["voided_ends"] = ends[-5:]
        voided = True
    rec["renewed_at"] = fmt(now)
    old = to_seconds(rec.get("lease_until")) or 0.0
    rec["lease_until"] = fmt(max(old, now + lease_hours * 3600))
    return voided


def end(rec: Dict[str, object], now: float, by: str, reason: str) -> None:
    """A positive end: ended_at now and the lease released. A later end moves ended_at
    forward, so it is never older than a session marker the end follows (review 551 D1)."""
    rec["ended_at"] = fmt(now)
    rec["ended_by"] = by
    rec["end_reason"] = reason
    renewed = to_seconds(rec.get("renewed_at")) or now
    rec["renewed_at"] = fmt(min(renewed, now))
    rec["lease_until"] = fmt(now)


def owner_since(rec: Dict[str, object]) -> float:
    """When the current ownership generation began (records before 552: created_at)."""
    return to_seconds(rec.get("owner_since")) or to_seconds(rec.get("created_at")) or 0.0


def take(rec: Dict[str, object], now: float, session: str, host_session: str, lease_hours: float) -> None:
    """Hand the worktree to another session as a new ownership generation: the old session's
    later end events match nothing, and an end event that matches only by host counts only
    from a session that started after this generation began (worktree_sessions.py); an end
    is voided, a recorded foreign use cleared (reviews 551 D2, 552 A3). host_session is the
    target's, or empty when it is not known."""
    hist = list(rec.get("taken_from") or [])
    hist.append({"session": rec.get("session"), "host_session": rec.get("host_session", ""),
                 "generation": rec.get("generation", 1), "at": fmt(now)})
    rec["taken_from"] = hist[-5:]
    rec["session"], rec["host_session"] = session, host_session
    rec["generation"] = int(rec.get("generation", 1)) + 1  # type: ignore[call-overload]
    rec["owner_since"] = fmt(now)
    rec.pop("foreign_use", None)
    renew(rec, now, lease_hours)


def read_record(admin: str) -> Tuple[Optional[Dict[str, object]], Optional[bytes], Optional[str]]:
    """(record, raw bytes, problem). (None, None, None) when there is no record; a record
    that cannot be read or is not usable gives (None, raw or None, why)."""
    path = os.path.join(admin, OWNER)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | O_CLOEXEC)
    except FileNotFoundError:
        return None, None, None
    except OSError as e:
        return None, None, f"{OWNER}: {e.strerror or e}"
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None, None, f"{OWNER} is not a regular file"
        raw = read_all(fd, MAX_RECORD)
    except OSError as e:
        return None, None, f"{OWNER}: {e.strerror or e}"
    except OwnerError as e:
        return None, None, f"{OWNER}: {e}"
    finally:
        os.close(fd)
    try:
        rec = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, raw, f"{OWNER} is not JSON"
    if isinstance(rec, dict) and isinstance(rec.get("cache_roots"), list):
        # a record written before kinds (a plain path): the same path, no kind (review 552 D)
        rec["cache_roots"] = [{"path": r, "kind": None} if isinstance(r, str) else r for r in rec["cache_roots"]]
    bad = problems(rec)
    if bad:
        return None, raw, f"{OWNER}: " + "; ".join(bad)
    return rec, raw, None


def write_record(admin: str, rec: Dict[str, object]) -> None:
    bad = problems(rec)
    if bad:
        raise OwnerError("refusing to write a record that is not usable: " + "; ".join(bad))
    write_report(os.path.join(admin, OWNER), rec)


class OwnerLock:
    """flock on <admin>/bifrost-owner.lock for the life of the with-block. Raises Busy when it
    is not had within wait seconds, Gone when the admin dir (the worktree) went meanwhile."""

    def __init__(self, admin: str, wait: float) -> None:
        self.admin = admin
        self.wait = wait
        self.fd = -1

    def __enter__(self) -> "OwnerLock":
        path = os.path.join(self.admin, OWNER_LOCK)
        try:
            self.fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | O_CLOEXEC, 0o600)
        except FileNotFoundError:
            raise Gone(f"{self.admin} is gone: the worktree was removed")
        except OSError as e:
            raise OwnerError(f"{path}: {e.strerror or e}")
        deadline = time.monotonic() + self.wait
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES):
                    self._close()
                    raise OwnerError(f"{path}: {e.strerror or e}")
                if time.monotonic() >= deadline:
                    self._close()
                    raise Busy(f"{path} is held by another process (a sweep or a renewal)")
                time.sleep(0.05)
        # The holder before us may have removed the worktree: the lock file we hold is then
        # unlinked, or a new one stands at the path.
        try:
            cur = os.lstat(path)
        except FileNotFoundError:
            self._close()
            raise Gone(f"{self.admin} is gone: the worktree was removed")
        st = os.fstat(self.fd)
        if (st.st_dev, st.st_ino) != (cur.st_dev, cur.st_ino):
            self._close()
            raise Gone(f"{path} was replaced while waiting")
        return self

    def _close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __exit__(self, *exc: object) -> None:
        self._close()


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


def _number(env: Dict[str, str], name: str, default: float, low: float, high: float) -> float:
    """A finite number in [low, high] from the environment; the default for anything else."""
    raw = env.get(name, "").strip()
    try:
        v = float(raw) if raw else default
    except ValueError:
        return default
    return v if low <= v <= high else default  # NaN fails both comparisons


def lease_hours(env: Dict[str, str]) -> float:
    return _number(env, "LIFECYCLE_LEASE_HOURS", DEFAULT_LEASE_HOURS, 0.01, 24 * 365)


def end_grace(env: Dict[str, str]) -> float:
    """Seconds an end must stand before a sweep acts on it (LIFECYCLE_END_MIN_AGE_MIN, 120)."""
    return _number(env, "LIFECYCLE_END_MIN_AGE_MIN", 120, 0, 60 * 24 * 365) * 60
