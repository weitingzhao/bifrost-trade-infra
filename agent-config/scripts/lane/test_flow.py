"""T06, T08, T09, T14, T26, T30, T48, T54, T60."""

from __future__ import annotations

import threading
from contextlib import contextmanager

import pytest

from commands import cmd_abandon, cmd_confirm, cmd_next_round, cmd_queue, cmd_resolve, cmd_run
from errors import LaneError
from recorder import append_resolution, mark_started, open_intent_only
from support import B, TB, implement_ok, make_lane, review_ok, sha_set, verify_ok


def _boom(call):
    with pytest.raises(LaneError) as caught:
        call()
    return str(caught.value)


def test_t06_lane_exec_blocks_state_changes(tmp_path, monkeypatch):
    lane = make_lane(tmp_path)
    monkeypatch.setenv("LANE_EXEC", "step")
    attempts = (
        lambda: cmd_run(lane.root, lane.lane_id),
        lambda: cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief)),
        lambda: cmd_resolve(lane.root, lane.lane_id, attempt="att", kind="failed", operator="ada", reason="r", evidence="e"),
        lambda: cmd_confirm(lane.root, lane.lane_id, attempt="att", operator="ada", how="looked"),
        lambda: cmd_abandon(lane.root, lane.lane_id, operator="ada", reason="r"),
    )
    for call in attempts:
        assert _boom(call) == "a lane step cannot change a lane"
    monkeypatch.delenv("LANE_EXEC")
    failed = make_lane(tmp_path, "E")
    implement_ok(failed, exit_code=9)
    monkeypatch.setenv("LANE_EXEC", "")
    assert _boom(lambda: cmd_next_round(failed.root, failed.lane_id, brief=str(tmp_path / "missing-brief.md"))) == "a lane step cannot change a lane"


def test_t08_budget_and_run_never_opens_a_round(tmp_path):
    lane = make_lane(tmp_path, max_rounds=2)

    def opened():
        return [event for event in lane.events() if event["type"] == "round_opened"]

    assert _boom(lambda: cmd_run(lane.root, lane.lane_id)) == "run is implemented in round 2"
    assert len(opened()) == 1
    implement_ok(lane, exit_code=9)
    assert lane.status()["state"] == "step_failed"
    assert _boom(lambda: cmd_run(lane.root, lane.lane_id)).startswith("round 1 is closed")
    assert len(opened()) == 1
    cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief))
    implement_ok(lane, exit_code=9)
    assert lane.status()["state"] == "over_budget"
    message = _boom(lambda: cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief)))
    assert message == "over budget: 2/2; the Owner decides"
    assert lane.status()["state"] == "over_budget"
    rows, code = cmd_queue(lane.root)
    assert rows[0]["needs"] == "owner"
    assert code == 1
    assert _boom(lambda: cmd_run(lane.root, lane.lane_id)).startswith("round 2 is closed")
    assert len(opened()) == 2


def test_t09_middle_line_breaks_the_chain(tmp_path):
    lane = make_lane(tmp_path)
    implement_ok(lane)
    path = lane.dir / "events.jsonl"
    raw = bytearray(path.read_bytes())
    start = raw.find(b"\n") + 1
    raw[start + 3] = ord("0") if raw[start + 3] != ord("0") else ord("1")
    path.write_bytes(bytes(raw))
    status = lane.status()
    assert status["state"] == "unknown"
    assert status["reason"] == "event log invalid at seq 2"


def test_t14_abandon_keeps_unconfirmed_until_confirm(tmp_path):
    lane = make_lane(tmp_path)
    opened = open_intent_only(lane.dir)
    mark_started(lane.dir, opened)
    cmd_abandon(lane.root, lane.lane_id, operator="ada", reason="stopping")
    assert lane.status()["state"] == "abandoned"
    rows, _code = cmd_queue(lane.root)
    blob = " ".join(" ".join(row["why_waiting"]) for row in rows)
    assert f"execution not confirmed ended: {opened['attempt_id']}" in blob
    cmd_confirm(lane.root, lane.lane_id, attempt=opened["attempt_id"], operator="ada", how="pgrep empty")
    rows, _code = cmd_queue(lane.root)
    blob = " ".join(" ".join(row["why_waiting"]) for row in rows)
    assert "execution not confirmed ended" not in blob


def test_t26_verify_fail_advances(tmp_path):
    lane = make_lane(tmp_path)
    implement_ok(lane)
    line = b"VERDICT: FAIL (2 checks failed or produced no result)\n"
    lane.record(step="verify", stdout=line, exit_code=1, consumed=sha_set(B, TB), checks={})
    status = lane.status()
    assert status["state"] == "verify_failed"
    assert status["reason"] == "VERDICT: FAIL (2 checks failed or produced no result)"
    cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief))
    status = lane.status()
    assert status["state"] == "ready"
    assert status["round"] == 2


def test_t30_failed_close_still_unknown_and_budget(tmp_path):
    lane = make_lane(tmp_path, max_rounds=1)
    opened = open_intent_only(lane.dir)
    for reason in ("unsure", "still"):
        cmd_resolve(
            lane.root, lane.lane_id, attempt=opened["attempt_id"], kind="still-unknown",
            operator="ada", reason=reason, evidence="logs",
        )
    assert lane.status()["state"] == "start_ambiguous"
    cmd_resolve(
        lane.root, lane.lane_id, attempt=opened["attempt_id"], kind="failed",
        operator="ada", reason="gave up", evidence="logs",
    )
    status = lane.status()
    assert status["state"] == "over_budget"
    assert status["reason"] == "implement closed as failed by ada: gave up"
    assert _boom(lambda: cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief))).startswith("over budget:")

    noted = make_lane(tmp_path, "N", max_rounds=3)
    opened = open_intent_only(noted.dir)
    cmd_resolve(
        noted.root, noted.lane_id, attempt=opened["attempt_id"], kind="still-unknown",
        operator="ada", reason="unsure", evidence="logs",
    )
    implement_ok(noted, attempt_id=opened["attempt_id"])
    verify_ok(noted)
    review_ok(noted)
    finished = noted.status()
    assert finished["state"] == "passed"
    assert any(event.get("type") == "resolution" and event.get("kind") == "still-unknown" for event in noted.events())
    assert "still-unknown by ada: unsure" in finished["notes"]


def test_t48_verdict_pending_flushes_once(tmp_path):
    lane = make_lane(tmp_path, max_rounds=3)
    implement_ok(lane, write_verdict=False)
    assert lane.status()["state"] == "ready"
    assert lane.status()["next_step"] == "verify"
    assert _boom(lambda: cmd_run(lane.root, lane.lane_id)) == "run is implemented in round 2"
    steps = [event["exec"]["step"] for event in lane.events() if event["type"] == "step_intent"]
    assert steps == ["implement"]

    verified = make_lane(tmp_path, "V48", max_rounds=3)
    implement_ok(verified)
    verify_ok(verified, write_verdict=False)
    assert verified.status()["state"] == "ready"
    assert verified.status()["next_step"] == "review"
    assert _boom(lambda: cmd_run(verified.root, verified.lane_id)) == "run is implemented in round 2"
    verify_steps = [event["exec"]["step"] for event in verified.events() if event["type"] == "step_intent"]
    assert verify_steps == ["implement", "verify"]

    verify_fail = make_lane(tmp_path, "VF", max_rounds=3)
    implement_ok(verify_fail)
    verify_fail.record(
        step="verify",
        stdout=b"VERDICT: FAIL (1)\n",
        exit_code=1,
        consumed=sha_set(B, TB),
        checks={},
        write_verdict=False,
    )
    assert verify_fail.status()["display"] == "verdict_pending (verify_failed)"

    failed = make_lane(tmp_path, "F", max_rounds=3)
    implement_ok(failed, exit_code=9, write_verdict=False)
    assert failed.status()["display"] == "verdict_pending (step_failed)"
    message = _boom(lambda: cmd_run(failed.root, failed.lane_id))
    assert message == "round 1 is closed (step_failed); the only way on is next-round"
    assert failed.status()["reason"] == "implement exited 9"
    assert len([event for event in failed.events() if event["type"] == "verdict"]) == 1

    passed = make_lane(tmp_path, "P", max_rounds=3)
    implement_ok(passed)
    verify_ok(passed)
    review_ok(passed, write_verdict=False)
    assert passed.status()["display"] == "verdict_pending (passed)"
    _boom(lambda: cmd_run(passed.root, passed.lane_id))
    assert passed.status()["state"] == "passed"
    assert len([event for event in passed.events() if event["type"] == "verdict"]) == 1
    _boom(lambda: cmd_run(passed.root, passed.lane_id))
    assert len([event for event in passed.events() if event["type"] == "verdict"]) == 1


def test_t54_resolution_flush_is_stable(tmp_path):
    lane = make_lane(tmp_path, max_rounds=3)
    opened = open_intent_only(lane.dir)
    append_resolution(
        lane.dir, rnd=1, step="implement", attempt=opened["attempt_id"],
        kind="failed", operator="ada", reason="stuck", evidence="ps",
    )
    assert lane.status()["display"] == "verdict_pending (step_failed)"
    direct = make_lane(tmp_path, "D", max_rounds=3)
    other = open_intent_only(direct.dir)
    cmd_resolve(
        direct.root, direct.lane_id, attempt=other["attempt_id"], kind="failed",
        operator="ada", reason="stuck", evidence="ps",
    )
    _boom(lambda: cmd_run(lane.root, lane.lane_id))
    flushed = [event for event in lane.events() if event["type"] == "verdict"][-1]
    immediate = [event for event in direct.events() if event["type"] == "verdict"][-1]
    assert flushed["reason"] == immediate["reason"] == "implement closed as failed by ada: stuck"
    again = _boom(
        lambda: cmd_resolve(
            lane.root, lane.lane_id, attempt=opened["attempt_id"], kind="cancelled",
            operator="bea", reason="other", evidence="again",
        )
    )
    assert again == f"attempt {opened['attempt_id']} is already resolved as failed"
    third = make_lane(tmp_path, "S", max_rounds=3)
    pending = open_intent_only(third.dir)
    for reason in ("once", "twice"):
        cmd_resolve(
            third.root, third.lane_id, attempt=pending["attempt_id"], kind="still-unknown",
            operator="ada", reason=reason, evidence="looked",
        )
    assert third.status()["state"] == "start_ambiguous"
    cmd_resolve(
        third.root, third.lane_id, attempt=pending["attempt_id"], kind="failed",
        operator="ada", reason="enough", evidence="looked",
    )
    assert third.status()["reason"] == "implement closed as failed by ada: enough"


def test_t60_abandoned_survives_a_corrupt_tail(tmp_path):
    lane = make_lane(tmp_path)
    cmd_abandon(lane.root, lane.lane_id, operator="ada", reason="done")
    path = lane.dir / "events.jsonl"
    path.write_bytes(path.read_bytes() + b"0" * 64 + b" {not json}\n")
    status = lane.status()
    assert status["state"] == "abandoned"
    last = [event["seq"] for event in lane.events() if event["type"] == "abandoned"][-1]
    assert status["marker"] == f"event log invalid after seq {last}"

    other = make_lane(tmp_path, "M")
    blob = bytearray((other.dir / "events.jsonl").read_bytes())
    cut = blob.find(b"\n") + 1
    blob[cut + 2] = ord("0") if blob[cut + 2] != ord("0") else ord("1")
    target = other.dir / "events.jsonl"
    target.write_bytes(bytes(blob))
    before = target.read_bytes()
    cmd_abandon(other.root, other.lane_id, operator="ada", reason="corrupt")
    assert target.read_bytes() == before
    assert (other.dir / "abandoned.json").is_file()
    status = other.status()
    assert status["state"] == "abandoned"
    assert status["marker"].startswith("event log invalid after seq ")


def _hold_lock(path, ready, stop):
    from locks import acquire, release

    fd = acquire(path, "record")
    ready.set()
    stop.wait(15)
    release(fd)


def test_recorder_gate1_before_lock_and_repair(tmp_path, monkeypatch):
    """LANE_EXEC is gate 1, before the lock and before torn-tail repair."""
    import commands

    blocked = make_lane(tmp_path, "L", max_rounds=3)
    torn = make_lane(tmp_path, "T", max_rounds=3)
    monkeypatch.setenv("LANE_EXEC", "")
    ready = threading.Event()
    stop = threading.Event()
    thread = threading.Thread(target=_hold_lock, args=(blocked.dir / "lock", ready, stop))
    thread.start()
    assert ready.wait(5)
    try:
        assert _boom(lambda: open_intent_only(blocked.dir)) == "a lane step cannot change a lane"
        assert _boom(lambda: blocked.record(step="implement", exit_code=9)) == "a lane step cannot change a lane"
        assert _boom(lambda: mark_started(blocked.dir, {"lane_id": "L", "round": 1, "step": "implement", "step_index": 0, "attempt_id": "x"})) == "a lane step cannot change a lane"
    finally:
        stop.set()
        thread.join(5)

    path = torn.dir / "events.jsonl"
    path.write_bytes(path.read_bytes() + b"torn-tail")
    assert _boom(lambda: open_intent_only(torn.dir)) == "a lane step cannot change a lane"
    assert path.read_bytes().endswith(b"torn-tail")
    assert list(torn.dir.glob("events.torn-*")) == []

    monkeypatch.delenv("LANE_EXEC")
    order = []
    real_gate = commands.gate_lane_exec
    real_hold = commands.hold
    real_repair = commands.repair_torn_tail

    def gate():
        order.append("gate")
        return real_gate()

    @contextmanager
    def holding(*args, **kwargs):
        order.append("lock")
        with real_hold(*args, **kwargs):
            yield

    def fixing(lane_dir):
        order.append("repair")
        return real_repair(lane_dir)

    monkeypatch.setattr(commands, "gate_lane_exec", gate)
    monkeypatch.setattr(commands, "hold", holding)
    monkeypatch.setattr(commands, "repair_torn_tail", fixing)
    open_intent_only(torn.dir)
    assert order[:3] == ["gate", "lock", "repair"]
    assert path.read_bytes().endswith(b"\n")
    assert list(torn.dir.glob("events.torn-*"))
