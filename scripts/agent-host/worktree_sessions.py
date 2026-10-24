"""Session events for worktree records (W-31 round 4, 4.6 S3; CUT-lifecycle-2026-10-24.md
§4.2; review 551 D1, D2). The hook (agent-config/claude/hooks/worktree-lease.py) calls
session_event; the local sweep calls session_problem.

SessionStart, in this order:
  1. Write the session's marker <status>/lifecycle-sessions/<id>.json ({"active_since":
     seconds}), atomically, for the CLI session id and for the host session id. The sweep
     treats a record whose session or host session has a marker newer than its ended_at as
     in use, and one whose marker it cannot read as in use: a renewal that fails later in
     this event (a lock not had in time, a write that fails) still leaves the worktree in use.
  2. Read every record without a lock and keep those of this session (or host session), and
     those of another session whose worktree holds the hook's cwd (foreign use).
  3. Within one time budget for the whole event, take each kept record's flock, check it
     still matches, and renew it (voiding an end), or mark the foreign use, which keeps that
     worktree from any sweep until new-worktree.sh --take hands it over.
SessionEnd: steps 2 and 3, writing ended_at; it writes no marker. A later end moves ended_at
past the marker, so the worktree becomes removable again only by a positive end.
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional, Tuple

import worktree_owner as wo
from disk_guard_state import write_report

MARKERS = "lifecycle-sessions"


def marker_path(env: Dict[str, str], sid: str) -> str:
    return os.path.join(wo.status_dir(env), MARKERS, f"{sid}.json")


def write_markers(env: Dict[str, str], ids: List[str], now: float) -> List[str]:
    probs = []
    d = os.path.join(wo.status_dir(env), MARKERS)
    for sid in dict.fromkeys(i for i in ids if i):
        try:
            os.makedirs(d, mode=0o700, exist_ok=True)
            write_report(marker_path(env, sid), {"session": sid, "active_since": now, "written_at": wo.fmt(now)})
        except OSError as e:
            probs.append(f"cannot write the session marker for {sid}: {e.strerror or e}")
    return probs


def session_problem(env: Dict[str, str], rec: Dict[str, object]) -> Optional[Tuple[str, str]]:
    """Why an ended record must still count as in use: its session (or host session) started
    again after the end, or the marker that would say so cannot be read."""
    ended = wo.to_seconds(rec.get("ended_at"))
    if ended is None:
        return "record-unusable", "ended_at cannot be read"
    for key in ("session", "host_session"):
        sid = rec.get(key)
        if not isinstance(sid, str) or not sid:
            continue
        if not wo.SESSION_RE.match(sid):
            return "session-marker-unreadable", f"{key} is not an id"
        try:
            with open(marker_path(env, sid), encoding="utf-8") as f:
                since = json.load(f)["active_since"]
            if not isinstance(since, (int, float)) or since != since:
                raise ValueError("active_since is not a number")
        except FileNotFoundError:
            continue
        except (OSError, ValueError, KeyError, TypeError) as e:
            return "session-marker-unreadable", f"the {key} marker cannot be read ({type(e).__name__})"
        if since > ended:
            return "session-resumed", f"{key} {sid} started again at {wo.fmt(since)}, after ended_at {rec['ended_at']}"
    return None


def foreign_problem(rec: Dict[str, object]) -> Optional[Tuple[str, str]]:
    fu = rec.get("foreign_use")
    if isinstance(fu, dict):
        return "used-by-another-session", f"session {fu.get('session')} started inside it at {fu.get('at')}; new-worktree.sh --take hands it over"
    return None


def _worktree_of(admin: str) -> Optional[str]:
    try:
        with open(os.path.join(admin, "gitdir"), encoding="utf-8") as f:
            return os.path.realpath(os.path.dirname(f.read().strip()))
    except OSError:
        return None


def _inside(path: str, top: Optional[str]) -> bool:
    return bool(top) and (path == top or path.startswith(str(top) + os.sep))


def session_event(env: Dict[str, str], event: str, session: str, host: str, reason: str,
                  cwd: str = "", budget: float = 8.0) -> Tuple[List[str], List[str]]:
    """(changed admin dirs, problems) for a SessionStart ("start") or SessionEnd ("end")."""
    if not wo.SESSION_RE.match(session or ""):
        return [], [f"session id {session!r} is not an id: nothing done"]
    host = host if wo.SESSION_RE.match(host or "") else ""
    deadline = time.monotonic() + budget
    now = wo.now_ts()
    probs: List[str] = write_markers(env, [session, host], now) if event == "start" else []
    repos, notes = wo.known_repos(env)
    admins, more = wo.registered(repos)
    probs += notes + more
    real_cwd = os.path.realpath(cwd) if cwd else ""

    def mine(rec: Dict[str, object]) -> bool:
        return rec.get("session") == session or bool(host and rec.get("host_session") == host)

    picked: List[Tuple[str, str]] = []  # (admin, "own" | "foreign")
    for admin in admins:
        rec, _, bad = wo.read_record(admin)
        if rec is None:
            if bad:
                probs.append(f"{admin}: {bad}")
            continue
        if mine(rec):
            picked.append((admin, "own"))
        elif event == "start" and real_cwd and _inside(real_cwd, _worktree_of(admin)):
            picked.append((admin, "foreign"))
    changed: List[str] = []
    lease = wo.lease_hours(env)
    for admin, how in picked:
        left = deadline - time.monotonic()
        if left <= 0:
            probs.append(f"{admin}: out of time for this event; " + (
                "the session marker keeps it in use" if event == "start" else "its end is not recorded, so it stays in use"))
            continue
        try:
            with wo.OwnerLock(admin, left):
                rec, _, bad = wo.read_record(admin)
                if rec is None or (how == "own") != mine(rec):
                    continue
                now = wo.now_ts()
                if how == "foreign":
                    if rec.get("foreign_use"):
                        continue
                    rec["foreign_use"] = {"session": session, "at": wo.fmt(now)}
                elif event == "end":
                    wo.end(rec, now, "session-end hook", reason)
                else:
                    wo.renew(rec, now, lease)
                wo.write_record(admin, rec)
                changed.append(admin)
        except wo.Gone:
            continue
        except (wo.OwnerError, OSError) as e:
            probs.append(f"{admin}: {e}")
    return changed, probs
