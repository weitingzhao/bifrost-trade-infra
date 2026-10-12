"""since stays at the first continuous evidence. Capacity is the longest prefix."""

from __future__ import annotations

from harness import APPR, LOCATOR, R, WAIT_A, WORK, LogBuilder, _chain, fold_one, round_for
from read import fold_total

_MIB = 1024 * 1024


def _pending(log: LogBuilder, at: int) -> None:
    log.add("owner_wait_seen", "observer", at=at, wait_id=WAIT_A, sampled_at=at, ref_state="pending")


def test_since_stays_at_the_first_pending_observation():
    """pending@10, a confirming round at 20, pending@20. since stays 10."""
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add(
        "owner_wait_opened", "coordinator", at=2, wait_id=WAIT_A, title="请批",
        ref={"kind": "approval", "id": APPR},
    )
    _pending(log, 10)
    doc = fold_one(
        log.events, 20,
        observer=[
            round_for(10, []),
            round_for(20, [f"approval:{APPR}"], round_id="ab12cd35"),
        ],
    )
    assert doc["ball"]["since"] == 10
    _pending(log, 20)
    again = fold_one(
        log.events, 20,
        observer=[
            round_for(10, []),
            round_for(20, [f"approval:{APPR}"], round_id="ab12cd35"),
        ],
    )
    assert again["ball"]["holder"] == "owner"
    assert again["ball"]["why"] == "owner_can_act"
    assert again["ball"]["since"] == 10


def test_record_running_since_is_the_first_started_at():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=10, work_id=WORK, title="发布")
    log.add(
        "step_declared", "coordinator",         step_id=R, name="发布", kind="release", who="C",
        watch="record", locator=LOCATOR,
    )
    log.add(
        "record_seen", "observer", at=20, step_id=R, sampled_at=20, found=True,
        uid="uid-1", started_at=25,
    )
    log.add(
        "record_seen", "observer", at=40, step_id=R, sampled_at=40, found=True,
        uid="uid-1", started_at=25,
    )
    confirmed = [f"step:{WORK}/{R}"]
    doc = fold_one(log.events, 40, observer=[round_for(40, confirmed)])
    assert doc["ball"]["why"] == "step_running"
    assert doc["ball"]["since"] == 25


def test_record_created_since_is_the_first_find():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=10, work_id=WORK, title="发布")
    log.add(
        "step_declared", "coordinator",         step_id=R, name="发布", kind="release", who="C",
        watch="record", locator=LOCATOR,
    )
    log.add("record_seen", "observer", at=20, step_id=R, sampled_at=20, found=True, uid="uid-1")
    log.add("record_seen", "observer", at=30, step_id=R, sampled_at=30, found=True, uid="uid-1")
    doc = fold_one(log.events, 30, observer=[round_for(30, [f"step:{WORK}/{R}"])])
    assert doc["ball"]["why"] == "record_created"
    assert doc["ball"]["since"] == 20


def test_capacity_is_the_longest_prefix():
    huge = b"x" * (64 * _MIB + 1)
    empty = b""
    orders = ([("a", huge), ("b", empty)], [("b", empty), ("a", huge)])
    for logs in orders:
        doc = fold_total(logs, [], 1).document()
        assert doc["logs_unread"] == 2
        assert doc["works"] == []
        assert doc["fold_complete"] is False
        assert doc["ball"]["holder"] != "nobody"
        assert doc["ball"]["why"] == "fold_incomplete"


def test_observer_capacity_is_the_longest_prefix():
    huge = b"y" * (16 * _MIB + 1)
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    work = _chain(log.events)
    newer = "2026-10-11-0002.jsonl"
    older = "2026-10-11-0001.jsonl"
    orders = ([(newer, huge), (older, b"")], [(older, b""), (newer, huge)])
    for observer in orders:
        doc = fold_total([("w1", work)], observer, 1).document()
        assert doc["observer"] == {"files_unread": 2}
