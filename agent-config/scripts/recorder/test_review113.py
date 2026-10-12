"""Review 113: three inputs the production code answers wrongly.

Each states the design's rule and now runs as a regression test.
"""

from __future__ import annotations

from harness import APPR, LOCATOR, P, R, WORK, LogBuilder, _chain, fold_one, round_for
from read import fold_total



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


def test_an_event_cap_followed_by_a_torn_tail_is_limit_log(monkeypatch):
    """Bytes after a full event cap are the next line. Only an exact cap is log_full."""
    doc = _cap(monkeypatch, _lines(2) + b"tail", events=2)
    work = doc["works"][0]
    assert work["log_invalid_at"] == 3
    assert work["log_invalid_why"] == "limit_log"
    assert work.get("log_full") is not True
    assert doc["ball"] == {"holder": "unknown", "why": "log_invalid"}


def test_a_byte_cap_followed_by_a_torn_tail_is_limit_log(monkeypatch):
    exact = _lines(1)
    doc = _cap(monkeypatch, exact + b"x", nbytes=len(exact))
    work = doc["works"][0]
    assert work["log_invalid_why"] == "limit_log"
    assert work.get("log_full") is not True
    assert doc["ball"]["why"] == "log_invalid"


def test_an_observer_cap_followed_by_a_torn_tail_is_limit_log(monkeypatch):
    import read

    monkeypatch.setattr(read, "MAX_EVENTS", 2)
    observed = read.read_log("2026-10-11-0001.jsonl", _lines(2) + b"x", observer=True)
    assert observed.broken_line == 3 and observed.broken_why == "limit_log" and observed.full is False


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




def test_real_event_cap_and_observer_cap_with_torn_tail():
    from model import MAX_EVENTS
    from read import read_log
    exact = _lines(MAX_EVENTS)
    for observer in (False, True):
        name = "2026-10-11-0001.jsonl" if observer else WORK
        loaded = read_log(name, exact + b"x", observer=observer)
        assert loaded.broken_line == 20001 and loaded.broken_why == "limit_log"
        assert loaded.full is False
        assert read_log(name, exact, observer=observer).full is True


def test_real_byte_cap_with_torn_tail():
    """Valid padded JSON rows reach exactly 16 MiB, below the event cap."""
    import hashlib
    from events import dump_line
    from model import MAX_LOG_BYTES
    from read import read_log
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    result = bytearray()
    prev = ""
    seq = 0
    while len(result) < MAX_LOG_BYTES:
        seq += 1
        fields = dict(type="note", text="n", v=2, by="coordinator", at=1,
                      seq=seq, prev_sha256=prev)
        if seq == 1:
            fields.update(type="work_opened", work_id=WORK, title="T")
            fields.pop("text")
        raw = dump_line(fields)
        target = min(131072, MAX_LOG_BYTES - len(result))
        body = raw[65:-1] + b" " * (target - len(raw))
        digest = hashlib.sha256(body).hexdigest().encode()
        result.extend(digest + b" " + body + b"\n")
        prev = digest.decode()
    assert len(result) == 16 * 1024 * 1024
    exact = read_log(WORK, bytes(result))
    assert exact.full and not exact.defects
    loaded = read_log(WORK, bytes(result) + b"x")
    assert loaded.broken_line == seq + 1 and loaded.broken_why == "limit_log" and not loaded.full


def test_record_created_since_unknown_after_found():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=R, name="release", kind="release", who="C",
            watch="record", locator=LOCATOR)
    log.add("record_seen", "observer", at=10, step_id=R, sampled_at=10, found=True, uid="uid-1")
    log.add("record_seen", "observer", at=20, step_id=R, sampled_at=20, found=True,
            uid="uid-1", condition="Unknown")
    log.add("record_seen", "observer", at=30, step_id=R, sampled_at=30, found=True, uid="uid-1")
    doc = fold_one(log.events, 30, observer=[round_for(30, [f"step:{WORK}/{R}"])])
    assert doc["ball"] == {"holder": "agents", "why": "record_created", "since": 10}
