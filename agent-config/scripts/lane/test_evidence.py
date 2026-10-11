"""T27, T28, T29, T32, T49, T53, T61."""

from __future__ import annotations

import pytest

from commands import cmd_next_round, cmd_pass_set, cmd_resolve, cmd_run
from errors import LaneError
from evidence import attempt_dir
from events import load_file
from lane import main
from recorder import mark_started, open_intent_only
from support import A, B, TA, TB, implement_ok, make_lane, review_ok, sha_set, verify_ok


def _boom(call):
    with pytest.raises(LaneError) as caught:
        call()
    return str(caught.value)


def _fix_report(end=True):
    body = b"VERDICT: fix first\n\nP1 one\n\n"
    return body + (b"END OF REPORT\n" if end else b"")


def test_t27_stdout_byte_after_record(tmp_path):
    lane = make_lane(tmp_path, max_rounds=3)
    opened = implement_ok(lane, write_verdict=False)
    out = attempt_dir(lane.dir, opened) / "out" / "stdout"
    out.write_bytes(out.read_bytes() + b"x")
    status = lane.status()
    assert status["state"] == "unknown"
    assert status["reason"].startswith("evidence invalid: implement ")

    passed = make_lane(tmp_path, "P", max_rounds=3)
    implement_ok(passed)
    verified = verify_ok(passed)
    review_ok(passed)
    assert passed.status()["state"] == "passed"
    target = attempt_dir(passed.dir, verified) / "out" / "stdout"
    target.write_bytes(target.read_bytes() + b"x")
    assert passed.status()["state"] == "passed"
    assert _boom(lambda: cmd_pass_set(passed.root, passed.lane_id)) == "evidence changed after the verdict"


def test_t28_resolve_is_not_a_way_to_pass(tmp_path):
    lane = make_lane(tmp_path, max_rounds=3)
    with pytest.raises(SystemExit):
        main(["--root", str(lane.root), "resolve", lane.lane_id, "--kind", "passed", "--attempt", "a", "--operator", "ada", "--reason", "r", "--evidence", "e"])
    with pytest.raises(SystemExit):
        main(["--root", str(lane.root), "resolve", lane.lane_id, "--kind", "failed", "--attempt", "a", "--reason", "r", "--evidence", "e"])
    opened = implement_ok(lane, exit_code=9, write_verdict=False)
    manifest = attempt_dir(lane.dir, opened) / "rec" / "manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b" ")
    assert lane.status()["state"] == "unknown"
    message = _boom(
        lambda: cmd_resolve(
            lane.root, lane.lane_id, attempt=opened["attempt_id"], kind="failed",
            operator="ada", reason="no", evidence="diff",
        )
    )
    assert message == "exit code is recorded (9); use --kind evidence-lost"
    message = _boom(
        lambda: cmd_resolve(
            lane.root, lane.lane_id, attempt="not-this", kind="evidence-lost",
            operator="ada", reason="no", evidence="diff",
        )
    )
    assert "attempt not-this" in message
    cmd_resolve(
        lane.root, lane.lane_id, attempt=opened["attempt_id"], kind="evidence-lost",
        operator="ada", reason="lost", evidence="diff",
    )
    closed = make_lane(tmp_path, "V", max_rounds=3)
    recorded = implement_ok(closed, exit_code=9)
    assert closed.status()["state"] == "step_failed"
    message = _boom(
        lambda: cmd_resolve(
            closed.root, closed.lane_id, attempt=recorded["attempt_id"], kind="cancelled",
            operator="bea", reason="again", evidence="diff",
        )
    )
    assert message == "round 1 already has a verdict"
    for field, kwargs in (
        ("operator", {"operator": "", "reason": "r", "evidence": "e"}),
        ("reason", {"operator": "ada", "reason": "", "evidence": "e"}),
        ("evidence", {"operator": "ada", "reason": "r", "evidence": ""}),
        ("attempt", {"operator": "ada", "reason": "r", "evidence": "e", "attempt": ""}),
    ):
        missing = make_lane(tmp_path, f"M{field}", max_rounds=3)
        pending = open_intent_only(missing.dir)
        call = {"attempt": pending["attempt_id"], "kind": "failed", "operator": "ada", "reason": "r", "evidence": "e"}
        call.update(kwargs)
        assert "resolve requires" in _boom(lambda call=call, missing=missing: cmd_resolve(missing.root, missing.lane_id, **call))
    known = make_lane(tmp_path, "K", max_rounds=3)
    done = implement_ok(known)
    other = open_intent_only(known.dir, step="verify")
    assert _boom(
        lambda: cmd_resolve(
            known.root, known.lane_id, attempt=done["attempt_id"], kind="failed",
            operator="ada", reason="r", evidence="e",
        )
    ) == f"attempt {done['attempt_id']} is not the unresolved attempt"
    assert other["step"] == "verify"


def test_t29_exit_code_kind_is_refused(tmp_path):
    lane = make_lane(tmp_path)
    opened = open_intent_only(lane.dir)
    mark_started(lane.dir, opened)
    message = _boom(
        lambda: cmd_resolve(
            lane.root, lane.lane_id, attempt=opened["attempt_id"], kind="exit-code",
            operator="ada", reason="saw 0", evidence="none", code=0,
        )
    )
    assert message == f"no wait-based exit record exists for attempt {opened['attempt_id']}"


def test_t32_unreferenced_manifest_and_tampered_digest(tmp_path):
    lane = make_lane(tmp_path, max_rounds=3)
    opened = open_intent_only(lane.dir, step="implement")
    mark_started(lane.dir, opened)
    rec = attempt_dir(lane.dir, opened) / "rec"
    (rec / "manifest.json.tmp-abc").write_bytes(b"{}")
    (rec / "manifest.json").write_bytes(b"{}")
    assert lane.status()["state"] == "unknown"
    cmd_resolve(
        lane.root, lane.lane_id, attempt=opened["attempt_id"], kind="failed",
        operator="ada", reason="orphan", evidence="dir",
    )
    assert lane.status()["state"] == "step_failed"

    other = make_lane(tmp_path, "Q", max_rounds=3)
    recorded = implement_ok(other, write_verdict=False)
    path = attempt_dir(other.dir, recorded) / "rec" / "manifest.json"
    path.write_bytes(path.read_bytes().replace(b"implement", b"implemant"))
    status = other.status()
    assert status["state"] == "unknown"
    assert "evidence invalid:" in status["reason"]
    cmd_resolve(
        other.root, other.lane_id, attempt=recorded["attempt_id"], kind="evidence-lost",
        operator="ada", reason="changed", evidence="hash",
    )
    assert other.status()["state"] == "step_failed"


def test_t49_missing_report_is_a_recorded_fact(tmp_path):
    lane = make_lane(tmp_path, max_rounds=3)
    implement_ok(lane)
    verify_ok(lane)
    lane.record(step="review", report=None, consumed=sha_set(B, TB), checks={})
    status = lane.status()
    assert status["state"] == "step_failed"
    assert status["reason"] == "review produced no report"
    assert status["state"] != "unknown"

    other = make_lane(tmp_path, "R", max_rounds=3)
    implement_ok(other)
    verify_ok(other)
    recorded = other.record(
        step="review",
        report=b"VERDICT: safe to merge\n\nbody\n\nEND OF REPORT\n",
        consumed=sha_set(B, TB),
        checks={},
        write_verdict=False,
    )
    report = attempt_dir(other.dir, recorded) / "out" / "report"
    report.unlink()
    status = other.status()
    assert status["state"] == "unknown"
    assert status["reason"] == "evidence invalid: review report missing"
    assert "exit code is recorded" in _boom(
        lambda: cmd_resolve(
            other.root, other.lane_id, attempt=recorded["attempt_id"], kind="failed",
            operator="ada", reason="no", evidence="gone",
        )
    )
    cmd_resolve(
        other.root, other.lane_id, attempt=recorded["attempt_id"], kind="evidence-lost",
        operator="ada", reason="gone", evidence="gone",
    )
    assert other.status()["state"] == "step_failed"

    fresh = make_lane(tmp_path, "U", max_rounds=3)
    pending = open_intent_only(fresh.dir)
    assert "no recorded exit" in _boom(
        lambda: cmd_resolve(
            fresh.root, fresh.lane_id, attempt=pending["attempt_id"], kind="evidence-lost",
            operator="ada", reason="no", evidence="none",
        )
    )


def test_t53_recorded_rejection_survives_lost_evidence(tmp_path):
    def same_set_fails(lane, brief):
        cmd_next_round(lane.root, lane.lane_id, brief=str(brief))
        implement_ok(lane)
        assert lane.status()["reason"] == "no new commit since round 1 said fix first"

    full = make_lane(tmp_path, "A", max_rounds=3)
    implement_ok(full)
    verify_ok(full)
    recorded = full.record(step="review", report=_fix_report(True), consumed=sha_set(B, TB), checks={})
    assert full.status()["state"] == "changes_requested"
    root = attempt_dir(full.dir, recorded)
    (root / "rec" / "manifest.json").unlink()
    (root / "out" / "report").unlink()
    assert full.status()["state"] == "changes_requested"
    same_set_fails(full, full.brief)

    cut = make_lane(tmp_path, "B", max_rounds=3)
    implement_ok(cut)
    verify_ok(cut)
    recorded_cut = cut.record(step="review", report=_fix_report(False), consumed=sha_set(B, TB), checks={}, signal=15, exit_code=None)
    assert cut.status()["state"] == "step_failed"
    review = [event for event in cut.events() if event["type"] == "step_recorded" and event["exec"]["step"] == "review"][-1]
    assert review["rejects"] is True
    cut_root = attempt_dir(cut.dir, recorded_cut)
    (cut_root / "rec" / "manifest.json").unlink()
    (cut_root / "out" / "report").unlink()
    assert cut.status()["state"] == "step_failed"
    same_set_fails(cut, cut.brief)

    pending = make_lane(tmp_path, "C", max_rounds=3)
    implement_ok(pending)
    verify_ok(pending)
    recorded = pending.record(step="review", report=_fix_report(True), consumed=sha_set(B, TB), checks={}, write_verdict=False)
    (attempt_dir(pending.dir, recorded) / "rec" / "manifest.json").unlink()
    assert pending.status()["display"] == "verdict_pending (changes_requested)"
    message = _boom(
        lambda: cmd_resolve(
            pending.root, pending.lane_id, attempt=recorded["attempt_id"], kind="evidence-lost",
            operator="ada", reason="lost", evidence="gone",
        )
    )
    assert message == "round 1 already has a verdict"
    verdict = [event for event in pending.events() if event["type"] == "verdict"][-1]
    assert verdict["result"] == "changes_requested"
    assert verdict["reason"] == "fix first (recorded in the event; evidence lost)"
    same_set_fails(pending, pending.brief)
    assert load_file(pending.dir / "events.jsonl").invalid_seq is None
    _boom(lambda: cmd_run(pending.root, pending.lane_id))


def test_t61_closing_resolution_survives_earlier_evidence_loss(tmp_path):
    lane = make_lane(tmp_path, max_rounds=3)
    implement_ok(lane)
    verify_ok(lane)
    opened = open_intent_only(lane.dir, step="review")
    from recorder import append_resolution

    append_resolution(
        lane.dir, rnd=1, step="review", attempt=opened["attempt_id"],
        kind="failed", operator="ada", reason="stuck", evidence="ps",
    )
    implement = [event for event in lane.events() if event["type"] == "step_recorded" and event["exec"]["step"] == "implement"][-1]
    (attempt_dir(lane.dir, implement["exec"]) / "rec" / "manifest.json").unlink()
    assert lane.status()["display"] == "verdict_pending (step_failed)"
    _boom(lambda: cmd_run(lane.root, lane.lane_id))
    assert lane.status()["reason"] == "review closed as failed by ada: stuck"
    assert lane.status()["state"] == "step_failed"
