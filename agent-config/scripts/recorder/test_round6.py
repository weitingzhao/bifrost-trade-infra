"""Round 6: one assertion of meaning for each ruling and each planted site."""

from __future__ import annotations

import gc
import json

import pytest

import publish
import read
from events import GENESIS, dump_line
from harness import (
    LOCATOR,
    P,
    R,
    RUN,
    WORK,
    LogBuilder,
    _chain,
    fold_one,
    round_for,
)
from model import (
    MAX_EVENTS,
    MAX_LOG_BYTES,
    OBS_VALID_S,
    PLATFORM_ENVELOPE_BYTES,
    PLATFORM_MAX_PUT_BYTES,
    PUBLISH_TARGET_BYTES,
    ROUND_ITEM_LIMIT,
    TWO53,
)
from publish import publish_total
from read import PROBES, Folded, fold_total, read_log
from redact_bound import RULE_MAX_GROWTH, growth, string_growth

OBS = "2026-10-11-0001.jsonl"


def _pub(folded, host=None, blocks=None) -> dict:
    raw = publish_total(folded, host, blocks)
    return json.loads(raw), raw


def _fits(raw: bytes, view: dict) -> bool:
    return len(raw) + growth(view) + PLATFORM_ENVELOPE_BYTES <= PLATFORM_MAX_PUT_BYTES


def _notes(count: int, text: str = "n") -> bytes:
    prev = GENESIS
    lines = []
    for seq in range(1, count + 1):
        body = {
            "at": 1,
            "by": "coordinator",
            "prev_sha256": prev,
            "seq": seq,
            "text": text,
            "type": "note",
            "v": 2,
        }
        raw = dump_line(body)
        prev = raw.split(b" ", 1)[0].decode("ascii")
        lines.append(raw)
    return b"".join(lines)


def test_redaction_growth_counts_consumed_characters_only():
    assert RULE_MAX_GROWTH == (0, 2, 9, 0, 0, 1, 9)
    assert string_growth("pwd=x") == 9
    assert string_growth("pwd=x,") == 9
    assert string_growth("://a:b@") == 27
    assert string_growth("Basic aaaaaaaa") == 2
    assert string_growth("xoxa-" + "a" * 10) == 1
    assert string_growth("-----BEGIN PRIVATE KEY-----") == 0
    assert growth({"usage": {"a": "pwd=x," * 3}, "n": 1}) == 27


def test_usage_of_secret_assignments_is_shed_before_the_platform_limit():
    raw_doc, raw = _pub(fold_total([], [], 0), "board", {"usage": {"a": "pwd=x," * 17500}})
    assert "recorder_failed" not in raw_doc
    assert "usage" in raw_doc["incomplete"]
    assert _fits(raw, raw_doc)
    assert len(raw) <= PUBLISH_TARGET_BYTES


def _with_unrecorded(at, items, confirmed=None):
    event = round_for(at, list(confirmed or []))
    event["unrecorded"] = items
    return event


def test_running_steps_full_of_assignments_stay_inside_the_platform_limit():
    blob = lambda n: ("pwd=x," * ((n // 6) + 1))[:n]
    logs = []
    for work_index in range(12):
        name = f"w{work_index}"
        log = LogBuilder()
        log.add("work_opened", "coordinator", at=1, work_id=name, title="T")
        for step_index in range(20):
            step = f"{step_index + 1:08x}"
            log.add(
                "step_declared", "coordinator",
                step_id=step, name=blob(80), kind="other", who=blob(80), watch="process",
            )
            log.add("step_started", "wrapper", step_id=step, run_id=RUN, command=blob(200))
            log.add(
                "step_seen", "wrapper",
                step_id=step, run_id=RUN, sampled_at=log.at, alive=True, text=blob(200),
            )
        logs.append((name, _chain(log.events)))
    doc, raw = _pub(fold_total(logs, [], 3))
    assert "recorder_failed" not in doc
    assert doc["works"]
    assert _fits(raw, doc)
    assert len(raw) <= PUBLISH_TARGET_BYTES


def test_event_cap_breaks_on_the_first_unread_line(monkeypatch):
    monkeypatch.setattr(read, "MAX_EVENTS", 2)
    exact = read_log(WORK, _notes(2))
    assert exact.full is True and exact.broken_line is None
    over = read_log(WORK, _notes(3))
    assert over.broken_line == 3 and over.broken_why == "limit_log" and over.full is False


def test_byte_cap_breaks_on_the_first_unread_line(monkeypatch):
    exact_bytes = _notes(2)
    monkeypatch.setattr(read, "MAX_LOG_BYTES", len(exact_bytes))
    exact = read_log(WORK, exact_bytes)
    assert exact.full is True and exact.broken_line is None and exact.broken_why is None
    over = read_log(WORK, _notes(3))
    assert over.broken_why == "limit_log" and over.broken_line == 3 and over.full is False


def test_twenty_thousand_lines_exactly_is_log_full_and_the_owner_remains():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    for _ in range(MAX_EVENTS - 2):
        log.add("note", "coordinator", at=2, text="n")
    log.add(
        "owner_wait_opened", "coordinator", at=3,
        wait_id="f1b2c3d4", title="t", ref={"kind": "none", "id": "c0ffee01"}, can_act="yes",
    )
    assert len(log.events) == MAX_EVENTS
    doc = fold_total([(WORK, _chain(log.events))], [], 3).document()
    assert doc["fold_complete"] is True
    assert doc["works"][0]["log_full"] is True
    assert "log_invalid_at" not in doc["works"][0]
    assert doc["owner_all"]


def test_twenty_thousand_and_one_sealed_owner_does_not_vanish():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    for _ in range(MAX_EVENTS - 1):
        log.add("note", "coordinator", at=2, text="n")
    log.add(
        "owner_wait_opened", "coordinator", at=3,
        wait_id="f1b2c3d4", title="t", ref={"kind": "none", "id": "c0ffee01"}, can_act="yes",
    )
    assert len(log.events) == MAX_EVENTS + 1
    doc = fold_total([(WORK, _chain(log.events))], [], 3).document()
    assert doc["fold_complete"] is False
    work = doc["works"][0]
    assert work["log_invalid_at"] == MAX_EVENTS + 1
    assert work["log_invalid_why"] == "limit_log"
    assert work.get("log_full") is not True
    assert doc["ball"]["holder"] != "nobody"


def test_sixteen_mebibytes_exact_boundary_is_log_full():
    prev = GENESIS
    lines = []
    used = 0
    seq = 0
    while used < MAX_LOG_BYTES:
        seq += 1
        text = "n" * 700
        body = {"at": 1, "by": "coordinator", "prev_sha256": prev, "seq": seq, "text": text, "type": "note", "v": 2}
        raw = dump_line(body)
        if used + len(raw) > MAX_LOG_BYTES:
            body["text"] = "n" * (700 - (used + len(raw) - MAX_LOG_BYTES))
            raw = dump_line(body)
            assert used + len(raw) == MAX_LOG_BYTES
        lines.append(raw)
        used += len(raw)
        prev = raw.split(b" ", 1)[0].decode("ascii")
        assert seq < MAX_EVENTS
    loaded = read_log(WORK, b"".join(lines))
    assert loaded.full is True and loaded.broken_line is None
    extra = dump_line({
        "at": 1, "by": "coordinator", "prev_sha256": prev, "seq": seq + 1,
        "text": "n", "type": "note", "v": 2,
    })
    over = read_log(WORK, b"".join(lines) + extra)
    assert over.broken_why == "limit_log" and over.full is False and over.broken_line == seq + 1


def test_two_declared_yes_in_one_work_take_the_earlier_since():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("owner_wait_opened", "coordinator", at=10, wait_id="f1b2c3d4", title="a",
            ref={"kind": "none", "id": "c0ffee01"}, can_act="yes")
    log.add("owner_wait_opened", "coordinator", at=20, wait_id="a2b2c3d4", title="b",
            ref={"kind": "none", "id": "c0ffee02"}, can_act="yes")
    doc = fold_one(log.events, 20)
    assert doc["ball"] == {"holder": "owner", "why": "owner_can_act", "since": 10, "basis": "declared"}
    folded = fold_total([(WORK, _chain(log.events))], [], 20)
    full = folded.document()
    assert full["clock"] == {"reader_behind": False}
    assert full["works"][0]["last_at"] == 20
    assert [item["wait_id"] for item in full["owner_all"]] == ["a2b2c3d4", "f1b2c3d4"]
    for item in full["owner_all"]:
        assert "blocks_nothing" not in item and "reply_needed" not in item
        for piece in item["works"]:
            assert "blocks_nothing" not in piece


def test_two_works_with_the_same_why_take_the_earlier_start():
    logs = []
    for name, at in (("w1", 20), ("w2", 10)):
        log = LogBuilder()
        log.add("work_opened", "coordinator", at=1, work_id=name, title="T")
        log.add("owner_wait_opened", "coordinator", at=at, wait_id="f1b2c3d4", title="t",
                ref={"kind": "none", "id": "c0ffee01"}, can_act="yes")
        logs.append((name, _chain(log.events)))
    doc = fold_total(logs, [], 20).document()
    assert doc["ball"]["why"] == "owner_can_act"
    assert doc["ball"]["since"] == 10
    assert doc["ball"]["basis"] == "declared"


def test_next_not_sent_is_the_latest_of_declaration_settlement_and_after():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("owner_wait_opened", "coordinator", at=2, wait_id="f1b2c3d4", title="t",
            ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet")
    log.add("step_declared", "coordinator", at=3, step_id=P, name="A", kind="other", who="C", watch="none")
    log.add("step_started", "coordinator", at=4, step_id=P, run_id=RUN)
    log.add("step_declared", "coordinator", at=5, step_id=R, name="B", kind="other", who="C", watch="none",
            after=P, waiting_on=["f1b2c3d4"])
    log.add("owner_wait_closed", "coordinator", at=30, wait_id="f1b2c3d4", how="done")
    log.add("step_finished", "coordinator", at=50, step_id=P, run_id=RUN, reported="finished")
    doc = fold_one(log.events, 50)
    assert doc["ball"]["holder"] == "coordinator"
    assert doc["ball"]["why"] == "next_not_sent"
    assert doc["ball"]["since"] == 50


def test_hash_and_equality_cannot_swap_a_fallback_with_a_real_fold():
    def _hash(self):
        raise AssertionError("hash")

    def _eq(self, other):
        raise AssertionError("eq")

    original_hash = Folded.__hash__
    original_eq = Folded.__eq__
    Folded.__hash__ = _hash
    Folded.__eq__ = _eq
    try:
        fallback = fold_total([], [], True)
        real = fold_total([], [], 1)
        bad = json.loads(publish_total(fallback))
        good = json.loads(publish_total(real))
    finally:
        Folded.__hash__ = original_hash
        Folded.__eq__ = original_eq
    assert bad["recorder_failed"]["reason"] == "invalid_argument"
    assert bad["fold_complete"] is False
    assert bad["ball"]["holder"] != "nobody"
    assert "recorder_failed" not in good
    assert good["ball"]["holder"] == "nobody"


def test_replacing_init_does_not_receive_the_token():
    seen = []
    original = Folded.__init__

    def _init(self, token=None, document=None):
        seen.append(token)
        raise TypeError("replaced")

    Folded.__init__ = _init
    try:
        folded = fold_total([], [], 1)
        raw = publish_total(folded)
    finally:
        Folded.__init__ = original
    assert seen == []
    assert b"recorder_failed" not in raw


def test_registry_grows_with_live_handles_and_shrinks_when_they_are_collected():
    before = len(read._REGISTRY)
    handles = [fold_total([], [], 1) for _ in range(20)]
    assert len(read._REGISTRY) == before + 20
    del handles
    gc.collect()
    assert len(read._REGISTRY) == before


def test_a_future_unrecorded_round_still_counts():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    item = {"work_id": WORK, "step_id": P, "run_id": RUN}
    doc = fold_total([(WORK, _chain(log.events))], [(OBS, _chain([_with_unrecorded(100, [item])]))], 10).document()
    assert doc["works"][0]["unrecorded_runs"] == 1
    assert doc["ball"]["why"] == "run_unrecorded"


def test_unknown_block_keys_are_blocks_even_when_the_key_is_huge():
    huge = json.loads(publish_total(fold_total([], [], 1), "board", {"k" * 250000: 1}))
    assert huge["incomplete"] == ["blocks"]
    assert "recorder_failed" not in huge
    named = json.loads(publish_total(fold_total([], [], 1), "board", {"works": []}))
    assert named["incomplete"] == ["blocks"]
    assert "works" not in json.dumps(named["incomplete"])


def test_sensitive_keys_nested_in_a_block_are_stripped_after_the_merge():
    raw = publish_total(fold_total([], [], 1), "board", {"usage": {"api_key": "v", "ok": 1}})
    doc = json.loads(raw)
    assert b"api_key" not in raw
    assert doc["usage"] == {"ok": 1}
    assert "recorder_failed" not in doc


def test_logs_unread_above_two_to_the_fifty_three_is_invalid_and_the_bound_is_kept():
    over = json.loads(publish_total(fold_total([], [], 1, 10**5000)))
    assert over["recorder_failed"] == {"stage": "fold", "reason": "invalid_argument", "argument": "logs_unread"}
    assert over["internal_errors"] == 0
    kept = json.loads(publish_total(fold_total([], [], 1, TWO53)))
    assert "recorder_failed" not in kept
    assert kept["logs_unread"] == TWO53


def test_owner_overflow_is_incomplete_not_only_cut():
    logs = []
    for name in ("w1", "w2"):
        log = LogBuilder()
        log.add("work_opened", "coordinator", at=1, work_id=name, title="T")
        for index in range(1, 17):
            log.add(
                "owner_wait_opened", "coordinator", at=2,
                wait_id=f"{index:08x}", title="t",
                ref={"kind": "none", "id": f"{index + 99:08x}"}, can_act="yes",
            )
        logs.append((name, _chain(log.events)))
    doc = json.loads(publish_total(fold_total(logs, [], 2)))
    assert doc["owner_all_cut"] == 2
    assert "owner_all" in doc["incomplete"]


def test_a_slow_step_keeps_the_ball_with_the_agents():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", at=2, step_id=P, name="n", kind="other", who="C",
            watch="none", usual_s=1, usual_basis="declared")
    log.add("step_started", "coordinator", at=3, step_id=P, run_id=RUN)
    doc = fold_one(log.events, 6)
    assert doc["works"][0]["steps"][0]["state"] == "slow"
    assert doc["ball"]["holder"] == "agents"
    assert doc["ball"]["why"] == "step_running"


def test_a_closed_work_with_a_torn_tail_stays_complete():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("work_closed", "coordinator", at=2, claim="stopped")
    data = _chain(log.events) + b"torn"
    doc = fold_total([(WORK, data)], [], 2).document()
    assert doc["works"][0]["torn_tail"] is True
    assert doc["works"][0].get("closed_claim") == "stopped"
    assert doc["fold_complete"] is True


def test_a_failed_step_survives_a_later_break_and_a_running_step_does_not():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=P, name="bad", kind="other", who="C", watch="none")
    log.add("step_started", "coordinator", step_id=P, run_id=RUN)
    log.add("step_finished", "coordinator", step_id=P, run_id=RUN, reported="failed")
    log.add("step_declared", "coordinator", step_id=R, name="go", kind="other", who="C", watch="none")
    log.add("step_started", "coordinator", step_id=R, run_id="e1b2c3d4")
    log.add("note", "coordinator", text="tail")
    doc = fold_one(log.events, log.at, invalid_at=len(log.events))
    states = {step["name"]: step for step in doc["works"][0]["steps"]}
    assert states["bad"]["state"] == "failed"
    assert states["go"]["state"] == "unknown"
    assert states["go"]["reason"] == "log_invalid"


def test_unrecorded_expiry_and_last_seen_use_the_round_end():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("step_declared", "wrapper", step_id=P, name="n", kind="other", who="W", watch="process")
    item = [{"work_id": WORK, "step_id": P, "run_id": RUN}]
    doc = fold_total(
        [(WORK, _chain(log.events))],
        [(OBS, _chain([_with_unrecorded(10, item)]))],
        10,
    ).document()
    assert doc["works"][0]["steps"][0]["last_seen"] == {"alive": True, "at": 10}
    aged = fold_total(
        [(WORK, _chain(log.events))],
        [(OBS, _chain([_with_unrecorded(10, item)]))],
        10 + OBS_VALID_S,
    ).document()
    assert aged["works"][0]["unrecorded_runs"] == 1


def test_a_confirmation_exactly_one_hundred_eighty_seconds_old_is_still_fresh():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=R, name="rec", kind="release", who="C",
            watch="record", locator=LOCATOR)
    log.add("record_seen", "observer", at=20, step_id=R, sampled_at=20, found=True, uid="uid-1",
            started_at=19, ended_at=20)
    now = 20 + OBS_VALID_S
    doc = fold_one(log.events, now, observer=[round_for(20, [f"step:{WORK}/{R}"])])
    step = doc["works"][0]["steps"][0]
    assert step["state"] != "unknown"
    assert step.get("reason") != "not_confirmed"
    assert doc["ball"]["why"] in {"record_created", "step_running"}


def test_a_valid_line_before_a_torn_tail_is_kept():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    loaded = read_log(WORK, _chain(log.events) + b"torn")
    assert loaded.torn_tail is True
    assert loaded.view.valid[0]["type"] == "work_opened"
    assert loaded.broken_line is None


def test_a_work_id_that_disagrees_with_the_directory_is_a_mismatch():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id="w2", title="T")
    doc = fold_total([("w1", _chain(log.events))], [], 1).document()
    assert doc["works"][0]["defects"][0]["reason"] == "work_id_mismatch"


def test_observer_bytes_count_toward_the_total():
    size = 16 * 1024 * 1024
    logs = [(f"w{index}", b"x" * size) for index in range(4)]
    doc = fold_total(logs, [(OBS, b"o" * size)], 1).document()
    assert doc["logs_unread"] == 1
    assert doc["logs_unread_names"] == ["w3"]
    assert [work["work_id"] for work in doc["works"]] == ["w0", "w1", "w2"]


def test_a_huge_usage_block_is_shed_rather_than_failing_the_publish():
    doc = json.loads(publish_total(fold_total([], [], 0), "board", {"usage": {"a": "x" * 210000}}))
    assert doc["incomplete"] == ["usage"]
    assert "reduced" not in doc
    assert "recorder_failed" not in doc
    assert doc["ball"]["holder"] == "nobody"


def test_recent_is_shed_before_usage_when_dropping_recent_is_enough():
    folded = fold_total([], [], 1)
    recent = ["r" * 200] * 30
    found = None
    for size in range(190000, 205000, 500):
        doc = json.loads(publish_total(folded, "board", {"usage": {"a": "u" * size}, "recent": recent}))
        if "recorder_failed" in doc:
            continue
        if "usage" in doc and "recent" not in doc and "recent" in doc.get("incomplete", []):
            found = doc
            break
    assert found is not None
    assert "usage" not in found["incomplete"]


def test_six_internal_errors_keep_five_entries(monkeypatch):
    def boom():
        raise RuntimeError("probe")

    monkeypatch.setitem(PROBES, "line", boom)
    logs = [(f"w{index}", b"x\n") for index in range(6)]
    doc = fold_total(logs, [], 1).document()
    assert doc["internal_errors"] == 6
    assert len(doc["internal"]) == 5


def test_unknown_reasons_keep_three_and_count_the_rest(monkeypatch):
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("step_declared", "wrapper", at=2, step_id="11111111", name="start", kind="other", who="W", watch="process")
    log.add("step_declared", "coordinator", at=3, step_id="22222222", name="quiet", kind="other", who="C", watch="process")
    log.add("step_started", "wrapper", at=4, step_id="22222222", run_id=RUN, command="echo")
    log.add("step_declared", "coordinator", at=5, step_id=R, name="rec", kind="release", who="C",
            watch="record", locator=LOCATOR)
    log.add("step_declared", "coordinator", at=1000, step_id="33333333", name="back", kind="other", who="C", watch="process")
    log.add("step_started", "wrapper", at=1010, step_id="33333333", run_id="e1b2c3d4", command="echo")
    log.add("step_seen", "wrapper", at=1100, step_id="33333333", run_id="e1b2c3d4", sampled_at=1100, alive=True, output_bytes=1)
    log.add("note", "coordinator", at=1200, text="high")
    log.add("note", "coordinator", at=100, text="back")
    log.add("step_seen", "wrapper", at=1105, step_id="33333333", run_id="e1b2c3d4", sampled_at=1105, alive=True, output_bytes=2)
    folded = fold_total([(WORK, _chain(log.events))], [], 1200)
    reasons = {step["reason"] for step in folded.document()["works"][0]["steps"] if step["state"] == "unknown"}
    assert reasons >= {"start_not_recorded", "no_observation", "not_confirmed", "clock_backwards"}
    monkeypatch.setattr(publish, "_nbytes", lambda doc, level, feed, cut: 1 if level >= 5 else PUBLISH_TARGET_BYTES + 1)
    doc = json.loads(publish_total(folded))
    assert len(doc["works"][0]["unknown_reasons"]) == 3
    assert doc["works"][0]["unknown_reasons_omitted"] >= 1


def test_four_hundred_round_items_are_valid_and_one_more_is_round_size():
    exact = [{"work_id": WORK, "step_id": f"{index:08x}", "run_id": RUN} for index in range(ROUND_ITEM_LIMIT)]
    fresh = fold_total([], [(OBS, _chain([_with_unrecorded(10, exact)]))], 10).document()
    assert fresh["observer"].get("defects", []) == []
    items = [{"work_id": WORK, "step_id": f"{index:08x}", "run_id": RUN} for index in range(ROUND_ITEM_LIMIT + 1)]
    over = fold_total([], [(OBS, _chain([_with_unrecorded(10, items)]))], 10).document()
    assert over["observer"]["defects"][0]["reason"] == "round_size"


def test_next_not_sent_does_not_borrow_another_whys_since():
    ready = LogBuilder()
    ready.add("work_opened", "coordinator", at=1, work_id="w1", title="T")
    ready.add("step_declared", "coordinator", at=2, step_id=P, name="A", kind="other", who="C", watch="none")
    ready.add("step_started", "coordinator", at=3, step_id=P, run_id=RUN)
    ready.add("step_finished", "coordinator", at=40, step_id=P, run_id=RUN, reported="finished")
    ready.add("step_declared", "coordinator", at=50, step_id=R, name="B", kind="other", who="C", watch="none", after=P)
    waiting = LogBuilder()
    waiting.add("work_opened", "coordinator", at=1, work_id="w2", title="T")
    waiting.add("owner_wait_opened", "coordinator", at=5, wait_id="f1b2c3d4", title="t",
                ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet")
    doc = fold_total([("w1", _chain(ready.events)), ("w2", _chain(waiting.events))], [], 50).document()
    assert doc["ball"]["why"] == "next_not_sent"
    assert doc["ball"]["since"] == 50


def test_mixed_declared_and_observed_yes_has_no_declared_basis():
    declared = LogBuilder()
    declared.add("work_opened", "coordinator", at=1, work_id="w1", title="T")
    declared.add("owner_wait_opened", "coordinator", at=10, wait_id="f1b2c3d4", title="t",
                 ref={"kind": "none", "id": "c0ffee01"}, can_act="yes")
    observed = LogBuilder()
    observed.add("work_opened", "coordinator", at=1, work_id="w2", title="T")
    observed.add("owner_wait_opened", "coordinator", at=2, wait_id="a2b2c3d4", title="t",
                 ref={"kind": "approval", "id": "appr_0123456789abcdef"})
    observed.add("owner_wait_seen", "observer", at=12, wait_id="a2b2c3d4", sampled_at=12, ref_state="pending")
    doc = fold_total(
        [("w1", _chain(declared.events)), ("w2", _chain(observed.events))],
        [(OBS, _chain([round_for(12, ["approval:appr_0123456789abcdef"])]))],
        12,
    ).document()
    assert doc["ball"]["why"] == "owner_can_act"
    assert "basis" not in doc["ball"]


def test_a_zero_float_now_on_the_fallback_is_published_as_an_integer_zero():
    raw = publish_total(fold_total([], [], 0.0, -1))
    assert b'"at":0.0' not in raw
    assert b'"at":0' in raw


def test_a_dead_step_on_a_closed_work_stays_dead_when_a_later_line_breaks():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=P, name="d", kind="other", who="C", watch="process")
    log.add("step_started", "wrapper", step_id=P, run_id=RUN, command="echo")
    log.add("step_seen", "observer", step_id=P, run_id=RUN, sampled_at=log.at, alive=False)
    log.add("work_closed", "coordinator", claim="stopped")
    log.add("note", "coordinator", text="tail")
    doc = fold_one(log.events, log.at, invalid_at=len(log.events))
    assert doc["works"][0]["closed_claim"] == "stopped"
    assert doc["works"][0]["steps"][0]["state"] == "dead"
