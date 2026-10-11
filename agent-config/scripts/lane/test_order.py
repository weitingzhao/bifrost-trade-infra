"""Duplicate and out-of-order attempts, the start of the pass contract, and the round brief."""

from __future__ import annotations

import json

import pytest

from commands import cmd_next_round
from errors import LaneError
from events import append_obj, sha256_bytes
from evidence import attempt_dir
from query import created, expected_start, make_exec
from recorder import append_resolution, open_intent_only
from support import A, B, C, TA, TB, TC, implement_ok, make_lane, passing_prechecks, review_ok, sha_set, verify_ok


def _boom(call):
    with pytest.raises(LaneError) as caught:
        call()
    return str(caught.value)


def _quiet(lane):
    implement_ok(lane, write_verdict=False)
    verify_ok(lane, write_verdict=False)
    review_ok(lane, write_verdict=False)


def test_t22_reader_rejects_duplicate_and_disorder(tmp_path):
    hidden = make_lane(tmp_path, "H", max_rounds=3)
    _quiet(hidden)
    assert hidden.status()["display"] == "verdict_pending (passed)"
    first = [event for event in hidden.events() if event["type"] == "step_recorded" and event["exec"]["step"] == "implement"][0]
    clone = dict(first)
    clone["exec"] = dict(first["exec"])
    clone["exec"]["attempt_id"] = "secondtry"
    clone["exit"] = {"code": 9, "signal": None}
    append_obj(hidden.dir, clone)
    status = hidden.status()
    assert status["state"] == "unknown"
    assert status["reason"] == "evidence invalid: event 12 step_recorded: duplicate attempt for implement"
    assert status["display"] != "verdict_pending (passed)"

    rejected = make_lane(tmp_path, "R", max_rounds=3)
    _quiet(rejected)
    review = [event for event in rejected.events() if event["type"] == "step_recorded" and event["exec"]["step"] == "review"][0]
    second = dict(review)
    second["exec"] = dict(review["exec"])
    second["exec"]["attempt_id"] = "reject-2"
    second["rejects"] = True
    second["sha_set"] = review.get("consumed") or {}
    append_obj(rejected.dir, second)
    status = rejected.status()
    assert status["state"] == "unknown"
    assert status["reason"] == "evidence invalid: event 12 step_recorded: duplicate attempt for review"

    fresh = make_lane(tmp_path, "O")
    append_obj(
        fresh.dir,
        {"type": "step_intent", "exec": make_exec(fresh.lane_id, 1, "verify", "v-only"), "intent_sha256": "ab" * 32},
    )
    assert fresh.status()["reason"] == "evidence invalid: event 3 step_intent: verify before implement"

    bare = make_lane(tmp_path, "B")
    append_obj(
        bare.dir,
        {
            "type": "step_recorded",
            "exec": make_exec(bare.lane_id, 1, "implement", "no-intent"),
            "manifest_sha256": "cd" * 32,
            "not_started": None,
            "exit": {"code": 0, "signal": None},
            "consumed": {},
            "pinned": {},
            "bundles": {},
        },
    )
    assert bare.status()["reason"] == "evidence invalid: event 3 step_recorded: implement recorded without a matching intent"

    dup_intent = make_lane(tmp_path, "D")
    open_intent_only(dup_intent.dir)
    opened = [event for event in dup_intent.events() if event["type"] == "step_intent"][0]
    again = dict(opened)
    again["exec"] = dict(opened["exec"])
    again["exec"]["attempt_id"] = "other-intent"
    append_obj(dup_intent.dir, again)
    assert dup_intent.status()["reason"] == "evidence invalid: event 4 step_intent: duplicate attempt for implement"


def test_t22_recorder_refuses_each_second_attempt(tmp_path):
    continued = make_lane(tmp_path, "C", max_rounds=3)
    first = implement_ok(continued)
    assert _boom(lambda: implement_ok(continued)) == f"implement already has attempt {first['attempt_id']} in round 1"
    assert _boom(lambda: open_intent_only(continued.dir)) == f"implement already has attempt {first['attempt_id']} in round 1"
    assert _boom(lambda: verify_ok(make_lane(tmp_path, "early"))) == "verify is out of order in round 1"
    assert _boom(lambda: continued.record(step="review", report=b"x", consumed=sha_set(B, TB))) == "review is out of order in round 1"

    mismatch = make_lane(tmp_path, "M")
    opened = open_intent_only(mismatch.dir)
    assert "not the open intent" in _boom(
        lambda: mismatch.record(
            step="implement",
            attempt_id="not-the-open-one",
            pinned=sha_set(B, TB),
            consumed=sha_set(A, TA),
            bundle_bytes={"repo": b"bundle"},
            pre_checks=passing_prechecks("implement", sha_set(A, TA)),
        )
    )

    passed = make_lane(tmp_path, "P", max_rounds=3)
    implement_ok(passed)
    verify_ok(passed)
    review_ok(passed)
    assert _boom(lambda: implement_ok(passed)) == "round 1 already has a verdict"

    closed = make_lane(tmp_path, "X", max_rounds=3)
    pending = open_intent_only(closed.dir)
    append_resolution(
        closed.dir, rnd=1, step="implement", attempt=pending["attempt_id"],
        kind="failed", operator="ada", reason="stuck", evidence="ps",
    )
    assert _boom(lambda: implement_ok(closed)) == "round 1 has a closing resolution"
    assert opened["attempt_id"] != pending["attempt_id"]


def test_t31_wrong_start_is_not_passed(tmp_path):
    lane = make_lane(tmp_path, max_rounds=3)
    wrong = sha_set(B, TB)
    implement_ok(
        lane,
        consumed=wrong,
        pinned=sha_set(C, TC),
        pre_checks=passing_prechecks("implement", wrong),
        bundle_bytes={"repo": b"bundle"},
    )
    assert lane.status()["state"] == "unknown"
    assert lane.status()["reason"] == "evidence invalid: event 3 step_intent: consumed does not equal the current set"
    assert lane.status()["state"] != "passed"


def test_round_brief_is_the_published_copy(tmp_path):
    lane = make_lane(tmp_path, max_rounds=3)
    first = implement_ok(lane, exit_code=9)
    intent = json.loads((attempt_dir(lane.dir, first) / "rec" / "intent.json").read_text())
    assert intent["brief"]["path"].startswith("r1/brief-")
    copy = lane.dir / intent["brief"]["path"]
    blob = copy.read_bytes()
    assert intent["brief"]["sha256"] == sha256_bytes(blob)
    assert intent["brief"]["length"] == len(blob)
    other = tmp_path / "round-two.md"
    other.write_text("a different brief\n")
    from commands import cmd_next_round

    cmd_next_round(lane.root, lane.lane_id, brief=str(other))
    second = implement_ok(lane, exit_code=9, write_verdict=False)
    later = json.loads((attempt_dir(lane.dir, second) / "rec" / "intent.json").read_text())
    assert later["brief"]["path"].startswith("r2/brief-")
    assert later["brief"]["sha256"] != intent["brief"]["sha256"]
    assert later["brief"]["sha256"] == sha256_bytes((lane.dir / later["brief"]["path"]).read_bytes())


def test_artifacts_are_durable_before_the_manifest(tmp_path, monkeypatch):
    import evidence
    import recorder

    order = []
    real_write = recorder.write_bytes
    real_publish = evidence.publish

    def write(path, data):
        order.append(("write", path.name))
        return real_write(path, data)

    def publish(dest, data):
        order.append(("publish", dest.name))
        return real_publish(dest, data)

    monkeypatch.setattr(recorder, "write_bytes", write)
    monkeypatch.setattr(evidence, "publish", publish)
    lane = make_lane(tmp_path)
    implement_ok(lane, exit_code=9)
    stdout_at = next(index for index, item in enumerate(order) if item == ("write", "stdout"))
    bundle_at = next(index for index, item in enumerate(order) if item[0] == "write" and item[1].endswith(".bundle"))
    manifest_at = max(index for index, item in enumerate(order) if item == ("publish", "manifest.json"))
    assert stdout_at < manifest_at
    assert bundle_at < manifest_at


def _start_at(lane, rnd: int) -> dict:
    events = lane.events()
    targets = (created(events) or {})["repos"]
    return expected_start(events, rnd, targets)


def test_empty_pin_keeps_the_previous_start(tmp_path):
    lane = make_lane(tmp_path, "P", max_rounds=4)
    implement_ok(lane, exit_code=9)
    cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief))
    lane.record(step="implement", not_started={"check": "fetch", "repo": "repo", "reason": "cannot fetch"})
    assert lane.status()["reason"] == "implement did not start: cannot fetch"
    cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief))
    start = _start_at(lane, 3)
    assert start["repo"]["commit"] == B
    assert start["repo"]["tree"] == TB
    lane.record(
        step="implement",
        consumed=sha_set(A, TA),
        pinned=sha_set(C, TC),
        pre_checks=passing_prechecks("implement", sha_set(A, TA), kind="pinned", expected=sha_set(A, TA)),
        bundle_bytes={"repo": b"bundle"},
    )
    assert lane.status()["state"] == "unknown"
    assert lane.status()["reason"] == "evidence invalid: event 12 step_intent: consumed does not equal the current set"
    assert lane.status()["state"] != "passed"


def test_failed_implement_that_pinned_nothing_keeps_the_start(tmp_path):
    lane = make_lane(tmp_path, "F", max_rounds=4)
    implement_ok(lane, exit_code=9)
    cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief))
    implement_ok(lane, exit_code=9, pinned={}, bundle_bytes={})
    recorded = [
        event for event in lane.events()
        if event["type"] == "step_recorded" and event["exec"]["step"] == "implement" and event["exec"]["round"] == 2
    ][-1]
    assert recorded["pinned"] == {}
    assert lane.status()["reason"] == "implement exited 9"
    cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief))
    start = _start_at(lane, 3)
    assert start["repo"]["commit"] == B
    assert start["repo"]["tree"] == TB


def test_explicit_baseline_start_returns_to_the_baseline(tmp_path):
    lane = make_lane(tmp_path, "B2", max_rounds=3)
    implement_ok(lane, exit_code=9)
    cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief), start="baseline")
    opened = [event for event in lane.events() if event["type"] == "round_opened"][-1]
    assert opened["start"] == "baseline"
    start = _start_at(lane, 2)
    assert start["repo"]["commit"] == A
    assert start["repo"]["commit"] != B
