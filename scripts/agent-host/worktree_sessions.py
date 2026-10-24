"""Session events for worktree records (W-31 round 4, 4.6 S3; CUT-lifecycle-2026-10-24.md
§4.2; reviews 551 D1, D2, 552 A2, A3). The hook (agent-config/claude/hooks/worktree-lease.py)
calls session_event; the local sweep calls session_problem.

SessionStart, in this order:
  1. Publish the session's marker <status>/lifecycle-sessions/<id>.json ({"active_since":
     seconds}), atomically, for the CLI session id and for the host session id.
  2. Read every record without a lock and keep those of this session (or host session), and
     those of another session whose worktree holds the hook's cwd (foreign use).
  3. Within one budget for the lock waits of the whole event (the scan before it has no
     time limit of its own), take each kept record's flock, check it still matches, and
     renew it (voiding an end), or mark the foreign use.
  4. If a marker could not be published: write a resume-failed state where it can, beside
     the markers (<id>.resume-failed) and in the admin dir of each of this session's records
     that was not renewed (bifrost-owner.resume-failed), each holding the time. The event
     returns the worktrees for which nothing protective could be written, and the hook shows
     them to the session and the user.
The sweep keeps an ended record unless it can show that its session did not resume after
the end: the markers directory exists and is readable (missing is "unknown", not "ended"),
and no marker or resume-failed state of its session or host session, and none in its admin
dir, is newer than ended_at or unreadable. new-worktree.sh makes the directory, so it exists
once anything was registered; only SessionStart writes markers.

SessionEnd: steps 2 and 3, writing ended_at (a later end moves it forward). A record matches
by its session id; it matches by host session only for a session that owned no earlier
generation of it (taken_from) and whose own marker says it started after the current
generation began (owner_since): the late end of an older session of the same Desktop thread,
or of the session a --take replaced, does nothing (reviews 552 A3, 553 A1).

Every time here is kept in integer nanoseconds (ended_at_ns, owner_since_ns, active_since_ns,
failed_at_ns) and compared in real order (review 553 A1, A4). A record from before 553 knows
its times only to the second: a marker inside that second counts as a resume (kept), and as
not after the ownership began (no match).
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional, Tuple

import worktree_owner as wo
from disk_guard_state import write_report

MARKERS = "lifecycle-sessions"
Why = Optional[Tuple[str, str]]


def markers_dir(env: Dict[str, str]) -> str:
    return os.path.join(wo.status_dir(env), MARKERS)


def marker_path(env: Dict[str, str], sid: str, suffix: str = ".json") -> str:
    return os.path.join(markers_dir(env), f"{sid}{suffix}")


def _write_time(path: str, sid: str, t: int, key: str) -> Optional[str]:
    try:
        write_report(path, {"session": sid, key + "_ns": t, key: t / wo.NS, "written_at": wo.fmt(t / wo.NS)})
        return None
    except OSError as e:
        return f"{path}: {e.strerror or e}"


def write_markers(env: Dict[str, str], ids: List[str], now: int) -> List[str]:
    """Publish the active-since marker of each id, never moving one back; the problems (empty
    when all were written)."""
    try:
        os.makedirs(markers_dir(env), mode=0o700, exist_ok=True)
    except OSError as e:
        return [f"cannot make {markers_dir(env)}: {e.strerror or e}"]
    probs = []
    for sid in dict.fromkeys(i for i in ids if i):
        old, _ = _read_time(marker_path(env, sid), "active_since")
        bad = _write_time(marker_path(env, sid), sid, max(now, old or 0), "active_since")
        if bad:
            probs.append(f"cannot publish the session marker: {bad}")
    return probs


def _read_time(path: str, key: str) -> Tuple[Optional[int], Optional[str]]:
    """(the time in ns, None); (None, None) when the file does not exist; (None, why) otherwise.
    A file written before 553 has only the seconds, read as ns."""
    try:
        with open(path, encoding="utf-8") as f:
            got = json.load(f)
        t = got.get(key + "_ns")
        if t is None:
            t = got[key]
            if type(t) not in (int, float) or t != t:
                raise ValueError
            t = int(t * wo.NS)
        if type(t) is not int:
            raise ValueError
        return t, None
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError, KeyError, TypeError) as e:
        return None, f"{os.path.basename(path)} cannot be read ({type(e).__name__})"


def session_problem(env: Dict[str, str], rec: Dict[str, object], admin: str) -> Why:
    """Why an ended record must still count as in use (the sweep's view of a resume)."""
    ended = wo.ns_of(rec, "ended_at")
    if ended[0] is None:
        return "record-unusable", "ended_at cannot be read"
    d = markers_dir(env)
    if not os.path.isdir(d) or not os.access(d, os.R_OK | os.X_OK):
        return "session-state-unknown", f"{d} is missing or unreadable: whether its session resumed cannot be told"
    for key in ("session", "host_session"):
        sid = rec.get(key)
        if not isinstance(sid, str) or not sid:
            continue
        if not wo.SESSION_RE.match(sid):
            return "session-marker-unreadable", f"{key} is not an id"
        for suffix, k, code in ((".json", "active_since", "session-resumed"), (".resume-failed", "failed_at", "resume-failed")):
            t, bad = _read_time(marker_path(env, sid, suffix), k)
            if bad:
                return "session-marker-unreadable", f"the {key} {bad}"
            if t is not None and wo.resumed_after(t, ended):
                return code, f"{key} {sid} started again at {wo.fmt(t / wo.NS)}, after ended_at {rec['ended_at']}"
    t, bad = _read_time(os.path.join(admin, wo.RESUME_FAILED), "failed_at")
    if bad:
        return "session-marker-unreadable", bad
    if t is not None and wo.resumed_after(t, ended):
        return "resume-failed", f"its session resumed at {wo.fmt(t / wo.NS)} but could not publish it"
    return None


def foreign_problem(rec: Dict[str, object]) -> Why:
    fu = rec.get("foreign_use")
    if isinstance(fu, dict):
        return "used-by-another-session", f"session {fu.get('session')} started inside it at {fu.get('at')}; new-worktree.sh --take hands it over"
    return None


def _worktree_of(admin: str) -> Optional[str]:
    try:
        return wo.gitdir_target(admin)
    except wo.OwnerError:
        return None


def _inside(path: str, top: Optional[str]) -> bool:
    return bool(top) and (path == top or path.startswith(str(top) + os.sep))


def matches(env: Dict[str, str], rec: Dict[str, object], session: str, host: str, event: str) -> bool:
    """Whether a session event is about this record: by session id, or by host session; for an
    end by host, only from a session that started after the record's current ownership began."""
    if rec.get("session") == session:
        return True
    if not host or rec.get("host_session") != host:
        return False
    if event == "start":
        return True  # renewing is never unsafe
    if any(isinstance(t, dict) and t.get("session") == session for t in rec.get("taken_from") or []):
        return False  # an owner of an earlier generation
    since, bad = _read_time(marker_path(env, session), "active_since")
    return bad is None and since is not None and wo.surely_after(since, wo.owner_since(rec))


def session_event(env: Dict[str, str], event: str, session: str, host: str, reason: str,
                  cwd: str = "", budget: float = 8.0) -> Tuple[List[str], List[str], List[str], bool]:
    """(changed admin dirs, problems, worktrees of this session nothing protects: neither a
    published marker, a renewal nor a resume-failed state, whether the markers were
    published) for "start" or "end"."""
    if not wo.SESSION_RE.match(session or ""):
        return [], [f"session id {session!r} is not an id: nothing done"], [], False
    host = host if wo.SESSION_RE.match(host or "") else ""
    deadline = time.monotonic() + budget
    now = wo.now_ns()
    marker_probs: List[str] = write_markers(env, [session, host], now) if event == "start" else []
    probs: List[str] = list(marker_probs)
    if marker_probs:
        for sid in dict.fromkeys(i for i in (session, host) if i):
            bad = _write_time(marker_path(env, sid, ".resume-failed"), sid, now, "failed_at")
            if bad:
                probs.append(f"cannot write the resume-failed state: {bad}")
    repos, notes = wo.known_repos(env)
    admins, more = wo.registered(repos)
    probs += notes + more
    real_cwd = os.path.realpath(cwd) if cwd else ""
    picked: List[Tuple[str, str]] = []  # (admin, "own" | "foreign")
    for admin in admins:
        rec, _, bad = wo.read_record(admin)
        if rec is None:
            if bad:
                probs.append(f"{admin}: {bad}")
            continue
        if matches(env, rec, session, host, event):
            picked.append((admin, "own"))
        elif event == "start" and real_cwd and _inside(real_cwd, _worktree_of(admin)):
            picked.append((admin, "foreign"))
    changed: List[str] = []
    unsafe: List[str] = []
    lease = wo.lease_hours(env)
    for admin, how in picked:
        done = False
        try:
            left = deadline - time.monotonic()
            if left <= 0:
                raise wo.Busy("out of time for this event")
            with wo.OwnerLock(admin, left):
                rec, _, bad = wo.read_record(admin)
                if rec is None or (how == "own") != matches(env, rec, session, host, event):
                    continue
                now = wo.now_ns()
                if how == "foreign":
                    if rec.get("foreign_use"):
                        continue
                    rec["foreign_use"] = {"session": session, "at": wo.fmt(now / wo.NS)}
                elif event == "end":
                    wo.end(rec, now, "session-end hook", reason)
                else:
                    wo.renew(rec, now, lease)
                wo.write_record(admin, rec)
                changed.append(admin)
                done = True
        except wo.Gone:
            continue
        except (wo.OwnerError, OSError) as e:
            probs.append(f"{admin}: {e}")
        if not done and event == "start" and how == "own" and marker_probs:
            bad = _write_time(os.path.join(admin, wo.RESUME_FAILED), session, now, "failed_at")
            if bad:
                probs.append(f"cannot write the resume-failed state: {bad}")
                unsafe.append(_worktree_of(admin) or admin)
    return changed, probs, unsafe, not marker_probs
