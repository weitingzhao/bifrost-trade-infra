"""T15 and T59. Extension cells of T15 are second slice and are not here."""

from __future__ import annotations

import threading

from commands import cmd_abandon, cmd_next_round, cmd_queue, cmd_resolve
from locks import acquire, release
from recorder import mark_started, open_intent_only
from support import B, TB, implement_ok, make_lane, review_ok, sha_set, verify_ok


def _hold(paths, ready, stop):
    fds = [acquire(path, command) for path, command in paths]
    ready.set()
    stop.wait(15)
    for fd in reversed(fds):
        release(fd)


def test_t15_queue_lists_what_a_person_must_see(tmp_path):
    ready = make_lane(tmp_path, "ready")
    pending = make_lane(tmp_path, "pending", max_rounds=3)
    implement_ok(pending, exit_code=9, write_verdict=False)
    unknown = make_lane(tmp_path, "unknown")
    mark_started(unknown.dir, open_intent_only(unknown.dir))
    ambiguous = make_lane(tmp_path, "ambiguous")
    open_intent_only(ambiguous.dir)
    failed_verify = make_lane(tmp_path, "verifyf", max_rounds=3)
    implement_ok(failed_verify)
    failed_verify.record(step="verify", stdout=b"VERDICT: FAIL\n", exit_code=1, consumed=sha_set(B, TB), checks={})
    requested = make_lane(tmp_path, "changes", max_rounds=3)
    implement_ok(requested)
    verify_ok(requested)
    requested.record(step="review", report=b"VERDICT: fix first\n\nP1 a\n\nEND OF REPORT\n", consumed=sha_set(B, TB), checks={})
    failed = make_lane(tmp_path, "failed", max_rounds=3)
    implement_ok(failed, exit_code=9)
    budget = make_lane(tmp_path, "budget", max_rounds=1)
    implement_ok(budget, exit_code=9)
    passed = make_lane(tmp_path, "passed", max_rounds=3)
    implement_ok(passed)
    verify_ok(passed)
    review_ok(passed)
    abandoned = make_lane(tmp_path, "abandoned")
    cmd_abandon(abandoned.root, abandoned.lane_id, operator="ada", reason="stop")
    running = make_lane(tmp_path, "running")
    mark_started(running.dir, open_intent_only(running.dir), limit_seconds=3600)
    overdue = make_lane(tmp_path, "overdue")
    mark_started(
        overdue.dir,
        open_intent_only(overdue.dir),
        started_at="2000-01-01T00:00:00Z",
        limit_seconds=1,
    )
    started = threading.Event()
    stop = threading.Event()
    thread = threading.Thread(
        target=_hold,
        args=(
            [
                (running.dir / "lock", "run"),
                (running.dir / "run.lock", "run"),
                (overdue.dir / "run.lock", "run"),
            ],
            started,
            stop,
        ),
    )
    thread.start()
    assert started.wait(5)
    try:
        rows, code = cmd_queue(ready.root)
    finally:
        stop.set()
        thread.join(5)
    by_id = {row["id"]: row for row in rows}
    assert "passed" not in by_id
    assert "running" not in by_id
    assert by_id["ready"]["needs"] == "coordinator"
    assert by_id["pending"]["state"] == "verdict_pending"
    assert by_id["pending"]["needs"] == "coordinator"
    assert by_id["unknown"]["needs"] == "person"
    assert by_id["ambiguous"]["state"] == "start_ambiguous"
    assert by_id["verifyf"]["needs"] == "coordinator"
    assert by_id["changes"]["needs"] == "coordinator"
    assert by_id["failed"]["needs"] == "coordinator"
    assert by_id["budget"]["needs"] == "owner"
    assert by_id["abandoned"]["needs"] is None
    assert by_id["abandoned"]["why_waiting"] == ["abandoned"]
    assert by_id["overdue"]["state"] == "implementing"
    assert by_id["overdue"]["needs"] == "person"
    assert "overdue" in by_id["overdue"]["why_waiting"]
    assert code == 1


def test_t59_over_budget_keeps_an_unconfirmed_execution(tmp_path):
    lane = make_lane(tmp_path, max_rounds=2)
    opened = open_intent_only(lane.dir)
    cmd_resolve(
        lane.root, lane.lane_id, attempt=opened["attempt_id"], kind="failed",
        operator="ada", reason="gone", evidence="ps",
    )
    cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief))
    implement_ok(lane, exit_code=9)
    assert lane.status()["state"] == "over_budget"
    rows, code = cmd_queue(lane.root)
    assert code == 1
    assert rows[0]["needs"] == "owner"
    why = " ".join(rows[0]["why_waiting"])
    assert "over budget" in why
    assert f"execution not confirmed ended: {opened['attempt_id']}" in why
