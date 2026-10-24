"""Handovers, unreadable markers and fixed-time order for the worktree record (W-31 4.6 S3;
review 554 A1, A3, D). The rest of the record and the session hook are in
test_worktree_owner.py.

    python3 -m pytest -q scripts/agent-host/test_worktree_handover.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import new_worktree  # noqa: E402
import worktree_owner as wo  # noqa: E402
import worktree_sessions as ws  # noqa: E402
from lifecycle_testlib import World  # noqa: E402
from test_worktree_owner import hook  # noqa: E402


@pytest.fixture(name="w")
def handover_world(tmp_path):
    return World(tmp_path)


def handed_on_six_times(w):
    """A makes a worktree in thread local_t and it is handed on six times in that thread
    (A -> B -> ... -> G, generation 7); A has resumed since the last handover."""
    repo = w.repo()
    w.env["CLAUDE_CODE_SESSION_ID"], w.env["CLAUDE_CODE_HOST_SESSION_ID"] = "sess-a", "local_t"
    hook(w, {"hook_event_name": "SessionStart", "session_id": "sess-a", "source": "startup"}, host="local_t")
    d = w.new_worktree(repo, "t/bifrost-x", detach="origin/main", session="sess-a")
    for sid in ("sess-b", "sess-c", "sess-d", "sess-e", "sess-f", "sess-g"):
        rc, out = w.call(new_worktree.main, ["--take", str(d), "--session", sid, "--host-session", "local_t"])
        assert rc == 0, out
    assert w.look(d)["record"]["generation"] == 7
    hook(w, {"hook_event_name": "SessionStart", "session_id": "sess-a", "source": "resume"}, host="local_t")
    return d


def test_the_first_owner_stays_out_after_six_handovers(w):
    """Review 554 A1: with only the last five handovers kept, A dropped out of taken_from
    after the sixth, and A's end (by host, marker newer than owner_since) ended G's use.
    Every earlier owner is kept now: A's end does nothing; a new CLI session of the thread,
    started after the last handover, still ends it by host."""
    d = handed_on_six_times(w)
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-a", "reason": "other"}, host="local_t")
    assert w.look(d)["state"] == "in-use"
    hook(w, {"hook_event_name": "SessionStart", "session_id": "sess-g2", "source": "clear"}, host="local_t")
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-g2", "reason": "other"}, host="local_t")
    assert w.look(d)["state"] == "ended"


def test_a_handover_history_that_lost_an_owner_ends_only_by_its_own_session(w):
    """Review 554 A1: a record whose taken_from no longer lists every earlier owner (written
    by the five-entry code, or handed over more than TAKEN_KEEP times) cannot show that a
    session never owned it. No end that matches only by host counts for it; its own
    session's end and new-worktree.sh --end still do."""
    d = handed_on_six_times(w)
    admin = Path(wo.admin_of(str(d))[0])
    rec = json.loads((admin / wo.OWNER).read_text())
    rec["taken_from"] = rec["taken_from"][-5:]  # A is gone from it, as the old code left it
    (admin / wo.OWNER).write_text(json.dumps(rec))
    for sid in ("sess-a", "sess-g2"):
        if sid == "sess-g2":
            hook(w, {"hook_event_name": "SessionStart", "session_id": sid, "source": "clear"}, host="local_t")
        hook(w, {"hook_event_name": "SessionEnd", "session_id": sid, "reason": "other"}, host="local_t")
        assert w.look(d)["state"] == "in-use", sid
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-g", "reason": "other"}, host="local_t")
    assert w.look(d)["state"] == "ended"
    rec = wo.new_record("W-31", "s0", "h", "", None, False, "", [], 1_700_000_000 * wo.NS, 12)
    for n in range(1, wo.TAKEN_KEEP + 2):
        assert wo.history_complete(rec), n
        wo.take(rec, (1_700_000_000 + n) * wo.NS, f"s{n}", "h", 12)
    assert len(rec["taken_from"]) == wo.TAKEN_KEEP and not wo.history_complete(rec) and wo.problems(rec) == []


@pytest.mark.parametrize("text", ["[]", "null", '"x"', '{"active_since": 1e999}', '{"active_since": 1e300}'])
def test_a_marker_that_is_no_time_is_unreadable_and_the_report_still_comes(w, text):
    """Review 554 A3: a marker or resume-failed file that is valid JSON but not an object, or
    an old seconds value that is infinite or overflows in nanoseconds, made the report-only
    sweep stop with no report. It is unreadable evidence: that worktree is kept and named."""
    repo = w.repo()
    d = w.new_worktree(repo, "lane/bifrost-x", detach="origin/main", session="sess-1")
    w.end(d)
    Path(ws.marker_path(w.env, "sess-1")).write_text(text)
    rc, out, rep = w.prune()
    assert rc == 0 and World.items(rep)[str(d)]["reason"] == "session-marker-unreadable", out
    Path(ws.marker_path(w.env, "sess-1")).unlink()
    (Path(wo.admin_of(str(d))[0]) / wo.RESUME_FAILED).write_text(text)
    rc, out, rep = w.prune()
    assert rc == 0 and World.items(rep)[str(d)]["reason"] == "session-marker-unreadable", out


def test_the_last_nanoseconds_of_a_second_stay_in_that_second(w):
    """Review 554 D: t / NS as a float rounds the last nanoseconds of a second up into the
    next, so the readable time and the nanoseconds disagreed and the record was refused."""
    t = 1_700_000_000 * wo.NS + 999_999_999
    rec = wo.new_record("W-31", "sess-1", "", "", None, False, "", [], t, 12)
    assert rec["owner_since"] == rec["created_at"] == wo.fmt(1_700_000_000) and wo.problems(rec) == []
    wo.end(rec, t, "t", "")
    assert rec["ended_at"] == wo.fmt(1_700_000_000) and wo.problems(rec) == []
    wo.take(rec, t, "sess-2", "", 12)
    assert rec["owner_since"] == wo.fmt(1_700_000_000) and wo.problems(rec) == []


def test_order_at_fixed_times(w):
    """Review 554 D: the order rules at fixed times, not the clock. Exact times compare in
    real order within a second; a whole-second time keeps a marker inside its second as a
    resume and not as a start after it; a resume-failed state counts only if it is newer
    than the end."""
    S = wo.NS
    base = 1_700_000_000 * S
    os.makedirs(ws.markers_dir(w.env), exist_ok=True)
    admin = w.tmp / "admin"
    admin.mkdir()
    rec = wo.new_record("W-31", "sess-1", "local_t", "", None, False, "", [], base + 100, 12)
    wo.end(rec, base + 500, "t", "")
    ended = wo.ns_of(rec, "ended_at")
    assert ended == (base + 500, True)
    assert wo.resumed_after(base + 501, ended) and not wo.resumed_after(base + 499, ended)
    old = dict(rec)
    old.pop("ended_at_ns")
    assert wo.ns_of(old, "ended_at") == (base, False)
    assert wo.resumed_after(base + 1, wo.ns_of(old, "ended_at")) and not wo.surely_after(base + S - 1, wo.ns_of(old, "ended_at"))
    assert wo.surely_after(base + S, wo.ns_of(old, "ended_at"))
    for failed_at, want in ((base + 499, None), (base + 501, "resume-failed")):
        ws._write_time(ws.marker_path(w.env, "sess-1", ".resume-failed"), "sess-1", failed_at, "failed_at")
        got = ws.session_problem(w.env, rec, str(admin))
        assert (got and got[0]) == want, failed_at
    os.unlink(ws.marker_path(w.env, "sess-1", ".resume-failed"))
    # an end that matches by host: a marker one ns after owner_since counts, one before does not
    for since, want in ((base + 101, True), (base + 99, False)):
        ws._write_time(ws.marker_path(w.env, "sess-9"), "sess-9", since, "active_since")
        assert ws.matches(w.env, rec, "sess-9", "local_t", "end") is want, since
    legacy = dict(rec)
    legacy.pop("owner_since_ns")
    ws._write_time(ws.marker_path(w.env, "sess-9"), "sess-9", base + S - 1, "active_since")
    assert ws.matches(w.env, legacy, "sess-9", "local_t", "end") is False
