"""T23 and T50."""

from __future__ import annotations

from commands import cmd_next_round
from support import implement_ok, make_lane, sha_set, verify_ok


def _round_same(lane):
    cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief))
    implement_ok(lane)
    return lane.status()


def test_t23_signal_still_rejects_the_set(tmp_path):
    lane = make_lane(tmp_path, max_rounds=3)
    implement_ok(lane)
    verify_ok(lane)
    report = b"VERDICT: fix first\n\nP1 a\n\nEND OF REPORT\n"
    lane.record(step="review", report=report, consumed=sha_set("b" * 40, "2" * 40), checks={}, signal=15, exit_code=None)
    status = lane.status()
    assert status["state"] == "step_failed"
    assert status["reason"] == "review ended by signal 15"
    review = [event for event in lane.events() if event["type"] == "step_recorded" and event["exec"]["step"] == "review"][-1]
    assert review["rejects"] is True
    again = _round_same(lane)
    assert again["state"] == "step_failed"
    assert again["reason"] == "no new commit since round 1 said fix first"


def test_t50_unfinished_review_can_be_repeated_a_rejection_cannot(tmp_path):
    crashed = make_lane(tmp_path, "C", max_rounds=3)
    implement_ok(crashed)
    verify_ok(crashed)
    crashed.record(step="review", report=None, exit_code=1, consumed=sha_set("b" * 40, "2" * 40), checks={})
    assert crashed.status()["state"] == "step_failed"
    cmd_next_round(crashed.root, crashed.lane_id, brief=str(crashed.brief))
    implement_ok(crashed)
    assert crashed.status()["state"] == "ready"
    assert crashed.status()["next_step"] == "verify"
    verify_ok(crashed)
    assert crashed.status()["next_step"] == "review"

    cut = make_lane(tmp_path, "T", max_rounds=3)
    implement_ok(cut)
    verify_ok(cut)
    cut.record(step="review", report=b"hello\n\npartial\n", consumed=sha_set("b" * 40, "2" * 40), checks={})
    assert cut.status()["reason"] == "review report is truncated"
    cmd_next_round(cut.root, cut.lane_id, brief=str(cut.brief))
    implement_ok(cut)
    assert cut.status()["next_step"] == "verify"

    rejected = make_lane(tmp_path, "R", max_rounds=3)
    implement_ok(rejected)
    verify_ok(rejected)
    rejected.record(
        step="review",
        report=b"VERDICT: fix first\n\npartial\n",
        consumed=sha_set("b" * 40, "2" * 40),
        checks={},
    )
    review = [event for event in rejected.events() if event["type"] == "step_recorded" and event["exec"]["step"] == "review"][-1]
    assert review["rejects"] is True
    assert rejected.status()["reason"] == "review report is truncated"
    again = _round_same(rejected)
    assert again["reason"] == "no new commit since round 1 said fix first"
