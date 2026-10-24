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
from worktree_paths import (INFRA, O_CLOEXEC, OWNER, OWNER_LOCK, RESUME_FAILED, Busy, Gone, OwnerError,  # noqa: F401 (re-exported)
                            admin_of, agent_work, gitdir_target, known_repos, read_all, registered, status_dir,
                            workspace)

SCHEMA = 1
TIME_FMT = "%Y-%m-%dT%H:%M:%SZ"
MAX_RECORD = 64 * 1024
WORK_RE = re.compile(r"^(?:(?:W|TD|BI)-[0-9]{1,6}|LANE-[A-Za-z0-9._-]{1,64})$")
SESSION_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
DEFAULT_LEASE_HOURS = 12.0


NS = 10 ** 9


def now_ts() -> float:
    return time.time()


def now_ns() -> int:
    return time.time_ns()


def ns_of(rec: Dict[str, object], key: str) -> Tuple[Optional[int], bool]:
    """(nanoseconds, exact) of a time field (review 553 A1, A4): <key>_ns when it is an
    integer in the second <key> names; otherwise the start of that second, inexact (records
    from before 553). (None, False) when <key> cannot be read."""
    sec = to_seconds(rec.get(key))
    if sec is None:
        return None, False
    ns = rec.get(key + "_ns")
    if type(ns) is int and ns // NS == int(sec):
        return ns, True
    return int(sec) * NS, False


def resumed_after(t: int, ref: Tuple[Optional[int], bool]) -> bool:
    """t is, or may be, after ref: a time inside a whole-second ref's second counts (it stays
    kept)."""
    ns, exact = ref
    return ns is not None and (t > ns if exact else t >= ns)


def surely_after(t: int, ref: Tuple[Optional[int], bool]) -> bool:
    """t is certainly after ref: a time inside a whole-second ref's second does not count."""
    ns, exact = ref
    return ns is not None and (t > ns if exact else t >= ns + NS)


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
    for k in ("ended_at", "owner_since"):
        ns = rec.get(k + "_ns")
        if ns is not None and not (type(ns) is int and k in rec and ns_of(rec, k)[1]):
            out.append(f"{k}_ns is not the nanoseconds of {k}")
    fu = rec.get("foreign_use")
    if fu is not None and not (isinstance(fu, dict) and isinstance(fu.get("session"), str) and to_seconds(fu.get("at")) is not None):
        out.append("foreign_use is not {session, at}")
    return out


def end_evidence(rec: Dict[str, object], now: float, grace: float) -> Tuple[Optional[str], str]:
    """(None, "") when the record proves its session ended at least grace seconds ago and
    nothing used the worktree since; else (code, why)."""
    if "ended_at" not in rec:
        return "not-ended", "the record has no ended_at: its session has not said it ended"
    ended_ns, _ = ns_of(rec, "ended_at")
    renewed = to_seconds(rec.get("renewed_at"))
    lease = to_seconds(rec.get("lease_until"))
    if ended_ns is None or renewed is None or lease is None:
        return "record-unusable", "a time in the record cannot be read"
    ended = ended_ns / NS
    if ended > now:
        return "ended-in-future", f"ended_at {rec['ended_at']} is later than now"
    if renewed > ended or lease > ended:
        return "lease-renewed", "the lease was renewed after ended_at"
    if now - ended < grace:
        return "end-too-recent", f"ended at {rec['ended_at']}, less than {grace / 60:.0f} min ago"
    return None, ""


def new_record(work: str, session: str, host_session: str, purpose: str, branch: Optional[str],
               branch_created: bool, base: str, cache_roots: List[Dict[str, object]], t: int,
               lease_hours: float) -> Dict[str, object]:
    """A record made at t (integer nanoseconds, now_ns())."""
    now = t / NS
    return {
        "schema": SCHEMA, "work": work, "session": session, "host_session": host_session,
        "purpose": purpose, "created_at": fmt(now), "cache_roots": list(cache_roots),
        "branch": branch, "branch_created": branch_created, "base": base,
        "renewed_at": fmt(now), "lease_until": fmt(now + lease_hours * 3600),
        "generation": 1, "owner_since": fmt(t / NS), "owner_since_ns": t,
    }


def renew(rec: Dict[str, object], t: int, lease_hours: float) -> bool:
    """A use at t (ns): renewed_at, the lease extended, an end voided. True when an end was voided."""
    now = t / NS
    voided = False
    if "ended_at" in rec:
        ends = list(rec.get("voided_ends") or [])
        rec.pop("ended_at_ns", None)
        ends.append({"ended_at": rec.pop("ended_at"), "ended_by": rec.pop("ended_by", ""),
                     "end_reason": rec.pop("end_reason", ""), "voided_at": fmt(now)})
        rec["voided_ends"] = ends[-5:]
        voided = True
    rec["renewed_at"] = fmt(now)
    old = to_seconds(rec.get("lease_until")) or 0.0
    rec["lease_until"] = fmt(max(old, now + lease_hours * 3600))
    return voided


def end(rec: Dict[str, object], t: int, by: str, reason: str) -> None:
    """A positive end at t (ns): ended_at (and ended_at_ns, review 553) and the lease
    released. A later end moves ended_at forward, so it is never older than a session marker
    the end follows (review 551 D1)."""
    now = t / NS
    rec["ended_at"], rec["ended_at_ns"] = fmt(now), t
    rec["ended_by"] = by
    rec["end_reason"] = reason
    renewed = to_seconds(rec.get("renewed_at")) or now
    rec["renewed_at"] = fmt(min(renewed, now))
    rec["lease_until"] = fmt(now)


def owner_since(rec: Dict[str, object]) -> Tuple[Optional[int], bool]:
    """When the current ownership generation began, as ns_of gives it (records before 552:
    created_at, inexact)."""
    got = ns_of(rec, "owner_since")
    return got if got[0] is not None else ns_of(rec, "created_at")


def take(rec: Dict[str, object], t: int, session: str, host_session: str, lease_hours: float) -> None:
    """Hand the worktree to another session as a new ownership generation: the old session's
    later end events match nothing, and an end event that matches only by host counts only
    from a session that started after this generation began (worktree_sessions.py); an end
    is voided, a recorded foreign use cleared (reviews 551 D2, 552 A3). host_session is the
    target's, or empty when it is not known."""
    now = t / NS
    hist = list(rec.get("taken_from") or [])
    hist.append({"session": rec.get("session"), "host_session": rec.get("host_session", ""),
                 "generation": rec.get("generation", 1), "at": fmt(now)})
    rec["taken_from"] = hist[-5:]
    rec["session"], rec["host_session"] = session, host_session
    rec["generation"] = int(rec.get("generation", 1)) + 1  # type: ignore[call-overload]
    rec["owner_since"], rec["owner_since_ns"] = fmt(now), t
    rec.pop("foreign_use", None)
    renew(rec, t, lease_hours)


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
