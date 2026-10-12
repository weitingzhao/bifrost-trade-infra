"""Review 113: three inputs the production code answers wrongly.

Each states the design's rule and is expected to fail until the Owner's fix.
strict=True turns the test into a failure the day the code starts answering it.
"""

from __future__ import annotations

import pytest
from harness import APPR, LOCATOR, P, R, WORK, LogBuilder, _chain, fold_one, round_for
from read import fold_total

_XFAIL = "review 113 P1-{}: production answers wrongly; fix pending the Owner"


def _lines(count: int) -> bytes:
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    for _ in range(count - 1):
        log.add("note", "coordinator", at=2, text="n")
    return _chain(log.events)


def _cap(monkeypatch, data, *, events=None, nbytes=None):
    import read
    from model import MAX_EVENTS, MAX_LOG_BYTES

    monkeypatch.setattr(read, "MAX_EVENTS", events if events is not None else MAX_EVENTS)
    monkeypatch.setattr(read, "MAX_LOG_BYTES", nbytes if nbytes is not None else MAX_LOG_BYTES)
    return fold_total([(WORK, data)], [], 3).document()


@pytest.mark.xfail(strict=True, reason=_XFAIL.format(1))
def test_an_event_cap_followed_by_a_torn_tail_is_limit_log(monkeypatch):
    """Bytes after a full event cap are the next line. Only an exact cap is log_full."""
    doc = _cap(monkeypatch, _lines(2) + b"tail", events=2)
    work = doc["works"][0]
    assert work["log_invalid_at"] == 3
    assert work["log_invalid_why"] == "limit_log"
    assert work.get("log_full") is not True
    assert doc["ball"] == {"holder": "unknown", "why": "log_invalid"}


@pytest.mark.xfail(strict=True, reason=_XFAIL.format(1))
def test_a_byte_cap_followed_by_a_torn_tail_is_limit_log(monkeypatch):
    exact = _lines(1)
    doc = _cap(monkeypatch, exact + b"x", nbytes=len(exact))
    work = doc["works"][0]
    assert work["log_invalid_why"] == "limit_log"
    assert work.get("log_full") is not True
    assert doc["ball"]["why"] == "log_invalid"


@pytest.mark.xfail(strict=True, reason=_XFAIL.format(1))
def test_an_observer_cap_followed_by_a_torn_tail_is_limit_log(monkeypatch):
    import read

    monkeypatch.setattr(read, "MAX_EVENTS", 2)
    observed = read.read_log("2026-10-11-0001.jsonl", _lines(2) + b"x", observer=True)
    assert observed.broken_line == 3 and observed.broken_why == "limit_log" and observed.full is False


@pytest.mark.xfail(strict=True, reason=_XFAIL.format(2))
def test_record_created_since_keeps_going_across_unknown():
    """A continuous found segment is judged by found. Unknown does not cut it."""
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="发布")
    log.add(
        "step_declared", "coordinator", step_id=R, name="发布", kind="release", who="C",
        watch="record", locator=LOCATOR,
    )
    log.add(
        "record_seen", "observer", at=10, step_id=R, sampled_at=10, found=True,
        uid="uid-1", condition="Unknown",
    )
    log.add("record_seen", "observer", at=20, step_id=R, sampled_at=20, found=True, uid="uid-1")
    doc = fold_one(log.events, 20, observer=[round_for(20, [f"step:{WORK}/{R}"])])
    assert doc["works"][0]["defects"] == []
    assert doc["ball"] == {"holder": "agents", "why": "record_created", "since": 10}


@pytest.mark.xfail(strict=True, reason=_XFAIL.format(3))
def test_next_not_sent_since_uses_the_merged_terminal():
    """The earliest authoritative terminal sampled_at settles the wait across logs."""
    opened_a = LogBuilder()
    opened_a.add("work_opened", "coordinator", at=1, work_id="w1", title="A")
    opened_a.add(
        "owner_wait_opened", "coordinator", at=2, wait_id="f1b2c3d4", title="t",
        ref={"kind": "approval", "id": APPR},
    )
    opened_a.add(
        "owner_wait_seen", "observer", at=50, wait_id="f1b2c3d4", sampled_at=50, ref_state="executed",
    )
    opened_b = LogBuilder()
    opened_b.add("work_opened", "coordinator", at=1, work_id="w2", title="B")
    opened_b.add(
        "owner_wait_opened", "coordinator", at=2, wait_id="a2b2c3d4", title="t",
        ref={"kind": "approval", "id": APPR},
    )
    opened_b.add(
        "step_declared", "coordinator", at=5, step_id=P, name="n", kind="other", who="C",
        watch="none", waiting_on=["a2b2c3d4"],
    )
    doc = fold_total(
        [("w1", _chain(opened_a.events)), ("w2", _chain(opened_b.events))],
        [("2026-10-11-0001.jsonl", _chain([round_for(50, [f"approval:{APPR}"])]))],
        50,
    ).document()
    assert doc["works"][0]["defects"] == [] and doc["works"][1]["defects"] == []
    assert doc["ball"] == {"holder": "coordinator", "why": "next_not_sent", "since": 50}


