"""One named test for each row the round-3 design tables require.

Table A (16), Table A-2 (11), Table B at levels 0–6, Table C, the limit
rows, and the fallback document. Each test's name carries the table and row.
"""

from __future__ import annotations

import json

from events import dump_line
from harness import N, P, R, RUN, WORK, LogBuilder, _chain
from publish import publish_total
from read import PROBES, fold_total, read_log
from test_support import folded_for_test

OBS = "2026-10-11-0001.jsonl"


def _doc(events, now=20, observer=None, unread=0):
    obs = [(OBS, _chain(observer))] if observer else []
    return fold_total([(WORK, _chain(events))], obs, now, unread).document()


def _round(at, unrecorded):
    return {
        "type": "observer_round",
        "v": 2,
        "seq": 1,
        "prev_sha256": "",
        "at": at,
        "by": "observer",
        "round_id": "ab12cd34",
        "started_at": at - 1,
        "ended_at": at,
        "confirmed": [],
        "failed": [],
        "unrecorded": unrecorded,
    }


def _open():
    log = LogBuilder()
    log.add("work_opened", "coordinator", work_id=WORK, title="T")
    return log


def test_table_a_row_01_work_opened_not_first_is_absent():
    log = _open()
    log.add("note", "coordinator", text="n")
    log.events = [log.events[1], log.events[0]]
    doc = _doc(log.events)
    assert any(item["reason"] == "not_first" for item in doc["works"][0]["defects"])
    assert "title" not in doc["works"][0]


def test_table_a_row_02_step_declared_replaces_withdraws_the_old_step():
    log = _open()
    log.add("step_declared", "coordinator", step_id=P, name="old", kind="other", who="C", watch="none")
    log.add("step_declared", "coordinator", step_id=N, name="new", kind="other", who="C", watch="none", replaces=P)
    doc = _doc(log.events)
    assert [step["step_id"] for step in doc["works"][0]["steps"]] == [N]
    assert doc["works"][0]["withdrawn"] == 1


def test_table_a_row_03_step_started_late_is_absent():
    log = _open()
    log.add("step_declared", "coordinator", step_id=P, name="n", kind="other", who="C", watch="process")
    log.add("note", "coordinator", text="gap")
    log.add("step_started", "wrapper", step_id=P, run_id=RUN, command="echo")
    doc = _doc(log.events)
    assert any(item["reason"] == "late_start" for item in doc["works"][0]["defects"])
    assert doc["works"][0]["steps"][0]["state"] == "waiting"


def test_table_a_row_04_wrapper_declare_without_start_is_unknown():
    log = _open()
    log.add("step_declared", "wrapper", step_id=P, name="n", kind="other", who="W", watch="process")
    doc = _doc(log.events)
    step = doc["works"][0]["steps"][0]
    assert step["state"] == "unknown" and step["reason"] == "start_not_recorded"
    assert "command" not in step


def test_table_a_row_05_process_start_on_the_next_line_runs():
    log = _open()
    log.add("step_declared", "wrapper", step_id=P, name="n", kind="other", who="W", watch="process")
    log.add("step_started", "wrapper", step_id=P, run_id=RUN, command="echo")
    doc = _doc(log.events)
    assert doc["works"][0]["steps"][0]["state"] == "running"
    assert doc["works"][0]["steps"][0]["command"] == "echo"


def test_table_a_row_06_none_start_need_not_be_adjacent():
    log = _open()
    log.add("step_declared", "coordinator", step_id=N, name="n", kind="other", who="C", watch="none")
    log.add("note", "coordinator", text="gap")
    log.add("step_started", "coordinator", step_id=N, run_id=RUN)
    doc = _doc(log.events)
    assert doc["works"][0]["defects"] == []
    assert doc["works"][0]["steps"][0]["state"] == "running"


def test_table_a_row_07_step_seen_without_a_start_is_absent():
    log = _open()
    log.add("step_declared", "coordinator", step_id=P, name="n", kind="other", who="C", watch="process")
    log.add("step_seen", "wrapper", step_id=P, run_id=RUN, sampled_at=3, alive=True, output_bytes=1)
    doc = _doc(log.events)
    assert any(item["reason"] == "not_started" for item in doc["works"][0]["defects"])


def test_table_a_row_08_step_finished_without_a_start_is_absent():
    log = _open()
    log.add("step_declared", "coordinator", step_id=P, name="n", kind="other", who="C", watch="process")
    log.add("step_finished", "wrapper", step_id=P, run_id=RUN, exit={"code": 0})
    doc = _doc(log.events)
    assert any(item["reason"] == "not_started" for item in doc["works"][0]["defects"])


def test_table_a_row_09_record_seen_on_a_process_step_is_absent():
    log = _open()
    log.add("step_declared", "coordinator", step_id=P, name="n", kind="other", who="C", watch="process")
    log.add("record_seen", "observer", step_id=P, sampled_at=3, found=True, uid="u")
    doc = _doc(log.events)
    assert doc["works"][0]["defects"]


def test_table_a_row_10_owner_wait_opened_replaces_settles_the_old_wait():
    log = _open()
    log.add("owner_wait_opened", "coordinator", wait_id="f1b2c3d4", title="old", ref={"kind": "none", "id": "c0ffee01"}, can_act="yes")
    log.add("owner_wait_opened", "coordinator", wait_id="a2b2c3d4", title="new", ref={"kind": "none", "id": "c0ffee02"}, can_act="yes", replaces="f1b2c3d4")
    doc = _doc(log.events)
    assert len(doc["owner_all"]) == 1
    assert doc["owner_all"][0]["wait_id"] == "a2b2c3d4"


def test_table_a_row_11_same_wait_id_on_two_works_stays_two_items():
    other = LogBuilder()
    other.add("work_opened", "coordinator", work_id="w2", title="U")
    other.add("owner_wait_opened", "coordinator", wait_id="f1b2c3d4", title="a", ref={"kind": "none", "id": "c0ffee01"}, can_act="yes")
    log = _open()
    log.add("owner_wait_opened", "coordinator", wait_id="f1b2c3d4", title="b", ref={"kind": "none", "id": "c0ffee02"}, can_act="yes")
    doc = fold_total([(WORK, _chain(log.events)), ("w2", _chain(other.events))], [], 10).document()
    assert len(doc["owner_all"]) == 2


def test_table_a_row_12_observer_round_duplicate_key_is_a_defect():
    item = {"work_id": WORK, "step_id": P, "run_id": RUN}
    doc = _doc(_open().events, observer=[_round(10, [item, dict(item)])])
    assert doc["observer"]["defects"]
    assert doc["observer"]["defects"][0]["reason"] == "round_conflict"
    assert "unrecorded_runs" not in doc["works"][0]


def test_table_a_row_13_bad_version_breaks_the_chain():
    line = dump_line({"type": "note", "v": 1, "seq": 1, "prev_sha256": "", "at": 1, "by": "coordinator", "text": "n"})
    loaded = read_log(WORK, line)
    assert loaded.broken_why == "bad_version"
    assert loaded.broken_line == 1


def test_table_a_row_14_bad_chain_breaks_and_keeps_the_line_number():
    first = dump_line({"type": "note", "v": 2, "seq": 1, "prev_sha256": "", "at": 1, "by": "coordinator", "text": "n"})
    second = dump_line({"type": "note", "v": 2, "seq": 9, "prev_sha256": "ab" * 32, "at": 2, "by": "coordinator", "text": "m"})
    loaded = read_log(WORK, first + second)
    assert loaded.broken_line == 2 and loaded.broken_why == "bad_chain"


def test_table_a_row_15_unreadable_line_is_a_broken_chain_not_a_defect():
    loaded = read_log(WORK, b"not a line\n")
    assert loaded.broken_line == 1
    assert loaded.defects == []


def test_table_a_row_16_internal_exception_breaks_the_chain():
    def boom():
        raise RecursionError("hidden")

    PROBES["line"] = boom
    try:
        doc = _doc(_open().events)
    finally:
        PROBES["line"] = None
    assert doc["internal_errors"] == 1
    assert doc["works"][0]["log_invalid_why"] == "internal"
    assert "recorder_failed" not in doc


def test_table_a2_row_01_undeclared_open_work_counts():
    doc = _doc(_open().events, observer=[_round(10, [{"work_id": WORK, "step_id": P, "run_id": RUN}])])
    assert doc["works"][0]["unrecorded_runs"] == 1
    assert doc["ball"] == {"holder": "unknown", "why": "run_unrecorded"}


def test_table_a2_row_02_undeclared_closed_work_counts():
    log = _open()
    log.add("work_closed", "coordinator", claim="stopped")
    doc = _doc(log.events, observer=[_round(10, [{"work_id": WORK, "step_id": P, "run_id": RUN}])])
    assert doc["works"][0]["unrecorded_runs"] == 1
    assert doc["ball"]["why"] == "run_unrecorded"


def test_table_a2_row_03_wrapper_without_start_sets_last_seen():
    log = _open()
    log.add("step_declared", "wrapper", step_id=P, name="n", kind="other", who="W", watch="process")
    doc = _doc(log.events, observer=[_round(10, [{"work_id": WORK, "step_id": P, "run_id": RUN}])])
    step = doc["works"][0]["steps"][0]
    assert step["reason"] == "start_not_recorded"
    assert step["last_seen"] == {"alive": True, "at": 10}
    assert doc["works"][0]["unrecorded_runs"] == 1


def test_table_a2_row_04_coordinator_waiting_step_counts_and_stays_waiting():
    log = _open()
    log.add("step_declared", "coordinator", step_id=P, name="n", kind="other", who="C", watch="process")
    doc = _doc(log.events, observer=[_round(10, [{"work_id": WORK, "step_id": P, "run_id": RUN}])])
    assert doc["works"][0]["steps"][0]["state"] == "waiting"
    assert doc["works"][0]["unrecorded_runs"] == 1


def test_table_a2_row_05_withdrawn_step_on_open_work_counts():
    log = _open()
    log.add("step_declared", "coordinator", step_id=P, name="old", kind="other", who="C", watch="none")
    log.add("step_declared", "coordinator", step_id=N, name="new", kind="other", who="C", watch="none", replaces=P)
    doc = _doc(log.events, observer=[_round(10, [{"work_id": WORK, "step_id": P, "run_id": RUN}])])
    assert P not in {step["step_id"] for step in doc["works"][0]["steps"]}
    assert doc["works"][0]["unrecorded_runs"] == 1


def test_table_a2_row_06_withdrawn_step_on_closed_work_counts():
    log = _open()
    log.add("step_declared", "coordinator", step_id=P, name="old", kind="other", who="C", watch="none")
    log.add("step_superseded", "coordinator", step_id=P)
    log.add("work_closed", "coordinator", claim="stopped")
    doc = _doc(log.events, observer=[_round(10, [{"work_id": WORK, "step_id": P, "run_id": RUN}])])
    assert doc["works"][0]["unrecorded_runs"] == 1
    assert "closed_claim" in doc["works"][0]
    assert doc["ball"]["holder"] == "unknown" and doc["ball"]["why"] == "run_unrecorded"


def test_table_a2_row_07_ended_step_on_open_work_counts():
    log = _open()
    log.add("step_declared", "coordinator", step_id=N, name="n", kind="other", who="C", watch="none")
    log.add("step_started", "coordinator", step_id=N, run_id=RUN)
    log.add("step_finished", "coordinator", step_id=N, run_id=RUN, reported="finished")
    log.add("step_declared", "coordinator", step_id=P, name="keep", kind="other", who="C", watch="none")
    doc = _doc(log.events, observer=[_round(10, [{"work_id": WORK, "step_id": N, "run_id": "eeeeeeee"}])])
    assert doc["works"][0]["unrecorded_runs"] == 1


def test_table_a2_row_08_ended_step_on_closed_work_counts():
    log = _open()
    log.add("step_declared", "coordinator", step_id=N, name="n", kind="other", who="C", watch="none")
    log.add("step_started", "coordinator", step_id=N, run_id=RUN)
    log.add("step_finished", "coordinator", step_id=N, run_id=RUN, reported="finished")
    log.add("work_closed", "coordinator", claim="stopped")
    doc = _doc(log.events, observer=[_round(10, [{"work_id": WORK, "step_id": N, "run_id": "eeeeeeee"}])])
    assert doc["works"][0]["unrecorded_runs"] == 1


def test_table_a2_row_09_open_run_with_the_same_id_does_not_count():
    log = _open()
    log.add("step_declared", "wrapper", step_id=P, name="n", kind="other", who="W", watch="process")
    log.add("step_started", "wrapper", step_id=P, run_id=RUN, command="echo")
    doc = _doc(log.events, observer=[_round(10, [{"work_id": WORK, "step_id": P, "run_id": RUN}])])
    assert "unrecorded_runs" not in doc["works"][0]
    assert doc["ball"]["holder"] == "agents"


def test_table_a2_row_10_open_work_finished_run_counts():
    log = _open()
    log.add("step_declared", "wrapper", step_id=P, name="n", kind="other", who="W", watch="process")
    log.add("step_started", "wrapper", step_id=P, run_id=RUN, command="echo")
    log.add("step_finished", "wrapper", step_id=P, run_id=RUN, exit={"code": 0})
    log.add("step_declared", "coordinator", step_id=N, name="keep", kind="other", who="C", watch="none")
    doc = _doc(log.events, observer=[_round(10, [{"work_id": WORK, "step_id": P, "run_id": RUN}])])
    assert doc["works"][0]["unrecorded_runs"] == 1


def test_table_a2_row_11_closed_work_finished_run_counts():
    log = _open()
    log.add("step_declared", "coordinator", step_id=N, name="n", kind="other", who="C", watch="none")
    log.add("step_started", "coordinator", step_id=N, run_id=RUN)
    log.add("step_finished", "coordinator", step_id=N, run_id=RUN, reported="finished")
    log.add("work_closed", "coordinator", claim="stopped")
    doc = _doc(log.events, observer=[_round(10, [{"work_id": WORK, "step_id": N, "run_id": RUN}])])
    assert doc["works"][0]["unrecorded_runs"] == 1
    assert doc["ball"]["why"] == "run_unrecorded"


def test_table_c_row_01_duplicate_names_are_all_refused():
    body = _chain(_open().events)
    doc = fold_total([(WORK, body), (WORK, body)], [], 10).document()
    assert doc["logs_unread"] == 2
    assert doc["works"] == []
    assert doc["ball"]["why"] == "fold_incomplete"
    assert "since" not in doc["ball"]


def test_table_c_row_02_duplicate_observer_names_are_refused_in_either_order():
    body = _chain([_round(10, [{"work_id": WORK, "step_id": P, "run_id": RUN}])])
    left = fold_total([(WORK, _chain(_open().events))], [(OBS, body), (OBS, body)], 10).document()
    right = fold_total([(WORK, _chain(_open().events))], [(OBS, body), (OBS, body)], 10).document()
    assert left["observer"]["files_unread"] == 2
    assert "unrecorded_runs" not in left["works"][0]
    assert left == right


def test_limits_row_02_line_length():
    from model import MAX_LINE_BYTES
    line = b"a" * (MAX_LINE_BYTES + 1) + b"\n"
    loaded = read_log(WORK, line)
    assert loaded.broken_why == "limit_line" and loaded.broken_line == 1


def test_limits_row_03_bad_line_shape():
    loaded = read_log(WORK, b"zz\n")
    assert loaded.broken_why == "bad_line"


def test_limits_row_04_bad_digest():
    line = dump_line({"type": "note", "v": 2, "seq": 1, "prev_sha256": "", "at": 1, "by": "coordinator", "text": "n"})
    flipped = b"0" + line[1:]
    loaded = read_log(WORK, flipped)
    assert loaded.broken_why == "bad_digest"


def test_limits_row_05_depth():
    nested = "[" * 9 + "]" * 9
    body = '{"type":"note","v":2,"seq":1,"prev_sha256":"","at":1,"by":"coordinator","text":"n","extra":' + nested + "}"
    from events import sha256_bytes
    line = (sha256_bytes(body.encode()) + " " + body + "\n").encode()
    loaded = read_log(WORK, line)
    assert loaded.broken_why == "limit_depth"
    assert loaded.catches == 0


def test_limits_row_06_bad_utf8():
    loaded = read_log(WORK, b"\xff\n")
    assert loaded.broken_why in {"bad_line", "bad_utf8", "bad_digest"}


def test_limits_row_07_bad_chain_and_bad_version():
    test_table_a_row_13_bad_version_breaks_the_chain()
    test_table_a_row_14_bad_chain_breaks_and_keeps_the_line_number()


def test_limits_row_08_bad_number_does_not_break_the_chain():
    body = '{"at":1e309,"by":"coordinator","prev_sha256":"","seq":1,"text":"n","type":"note","v":2}'
    from events import sha256_bytes
    line = (sha256_bytes(body.encode()) + " " + body + "\n").encode()
    nxt = dump_line({"type": "note", "v": 2, "seq": 2, "prev_sha256": sha256_bytes(body.encode()), "at": 2, "by": "coordinator", "text": "m"})
    loaded = read_log(WORK, line + nxt)
    assert loaded.broken_line is None
    assert loaded.defects[0]["reason"] == "bad_number"
    assert len(loaded.events) == 1


def test_limits_row_09_lone_surrogate_is_a_defect():
    body = '{"at":1,"by":"coordinator","prev_sha256":"","seq":1,"text":"a\\ud800b","type":"note","v":2}'
    from events import sha256_bytes
    line = (sha256_bytes(body.encode()) + " " + body + "\n").encode()
    nxt_prev = sha256_bytes(body.encode())
    nxt = dump_line({"type": "note", "v": 2, "seq": 2, "prev_sha256": nxt_prev, "at": 2, "by": "coordinator", "text": "m"})
    loaded = read_log(WORK, line + nxt)
    assert loaded.defects[0]["reason"] == "limit_text"
    assert loaded.broken_line is None
    assert loaded.catches == 0


def test_limits_row_10_unknown_field_is_a_defect_and_the_chain_continues():
    log = _open()
    log.add("note", "coordinator", text="n", extra=1)
    log.add("note", "coordinator", text="m")
    doc = _doc(log.events)
    assert any(item["reason"] == "unknown_field" for item in doc["works"][0]["defects"])
    assert doc["feed"]


def test_fallback_row_invalid_argument_now():
    folded = fold_total([], [], True)
    doc = folded.document()
    assert doc["recorder_failed"]["reason"] == "invalid_argument"
    assert doc["recorder_failed"]["argument"] == "now"
    assert doc["internal_errors"] == 0
    assert doc["at"] == 0
    assert "since" not in doc["ball"]
    raw = publish_total(folded)
    assert b"recorder_failed" in raw


def test_fallback_row_invalid_argument_logs_none():
    doc = fold_total(None, [], 1).document()
    assert doc["recorder_failed"] == {"stage": "fold", "reason": "invalid_argument", "argument": "logs"}
    assert doc["internal_errors"] == 0


def test_table_b_row_01_logs_unread_survives_publish():
    folded = fold_total([(WORK, _chain([]))], [], 20, 3)
    doc = folded.document()
    assert doc["fold_complete"] is False
    assert doc["logs_unread"] == 3
    raw = publish_total(folded, "h")
    assert b'"logs_unread":3' in raw
    assert b'"fold_complete":false' in raw


def test_table_b_row_05_unrecorded_beats_a_running_step_in_the_same_work():
    log = _open()
    log.add("step_declared", "wrapper", step_id=P, name="n", kind="other", who="W", watch="process")
    log.add("step_started", "wrapper", step_id=P, run_id=RUN, command="echo")
    doc = _doc(log.events, observer=[_round(10, [{"work_id": WORK, "step_id": R, "run_id": "eeeeeeee"}])])
    assert doc["works"][0]["steps"][0]["state"] == "running"
    assert doc["works"][0]["unrecorded_runs"] == 1
    assert doc["ball"]["why"] == "run_unrecorded"


def test_review88_ten_thousand_nested_arrays_are_limit_depth():
    nested = "[" * 10000 + "]" * 10000
    body = '{"at":1,"by":"coordinator","prev_sha256":"","seq":1,"text":"n","type":"note","v":2,"x":' + nested + "}"
    from events import sha256_bytes
    line = (sha256_bytes(body.encode()) + " " + body + "\n").encode()
    loaded = read_log(WORK, line)
    assert loaded.broken_why == "limit_depth"
    assert loaded.catches == 0
    doc = fold_total([(WORK, line)], [], 1).document()
    assert doc["internal_errors"] == 0
    assert "recorder_failed" not in doc


def test_family_ding_keyboard_interrupt_propagates():
    def boom():
        raise KeyboardInterrupt

    PROBES["fold"] = boom
    try:
        try:
            fold_total([], [], 1)
        except KeyboardInterrupt:
            return
        raise AssertionError("swallowed")
    finally:
        PROBES["fold"] = None


def _level_sources():
    from test_publish import _blob, _owner, _shell, _step, _work

    docs = {}
    docs[0] = _shell([_work("w1", [_step("running")])])
    ended = [_step("done", note=_blob(4000), quote=_blob(4000), command=_blob(2000)) for _ in range(20)]
    for index, step in enumerate(ended):
        step["step_id"] = f"{index:08x}"
    docs[1] = _shell([_work("w1", ended)])
    feed = [{"at": index, "work": "w1", "step": "", "who": "C", "state": "", "text": _blob(5000)} for index in range(25)]
    docs[2] = _shell([_work("w1", [_step("running")])], feed=feed)
    closed = []
    for index in range(8):
        steps = []
        for nth in range(8):
            step = _step("running", note=_blob(2500))
            step["step_id"] = f"{index:04x}{nth:04x}"
            steps.append(step)
        closed.append(_work(f"c{index}", steps, closed=True, last=index))
    docs[3] = _shell(closed)
    running = []
    for index in range(20):
        step = _step("running", note=_blob(8000))
        step["step_id"] = f"{index:08x}"
        running.append(step)
    docs[4] = _shell([_work("w1", running)])
    commanded = []
    for index in range(4):
        step = _step("running", command=_blob(20000))
        step["step_id"] = f"{index:08x}"
        commanded.append(step)
    docs[5] = _shell([_work("w1", commanded)])
    owners = []
    for index in range(12):
        item = _owner(f"item-{index}", text=_blob(8000))
        item["wait_id"] = f"{index:08x}"
        owners.append(item)
    docs[6] = _shell([_work("w1", [_step("running")])], owner=owners)
    return docs


def _assert_marker(level: int, key: str, value):
    doc = _level_sources()[level]
    doc["internal_errors"] = 0
    doc["fold_complete"] = False
    for work in doc["works"]:
        work[key] = value
    raw = publish_total(folded_for_test(doc), "board")
    published = json.loads(raw)
    assert published.get("reduced", 0) == level
    for work in published["works"]:
        assert work[key] == value


def test_table_b_row_03_torn_tail_level_0():
    _assert_marker(0, "torn_tail", True)


def test_table_b_row_03_torn_tail_level_1():
    _assert_marker(1, "torn_tail", True)


def test_table_b_row_03_torn_tail_level_2():
    _assert_marker(2, "torn_tail", True)


def test_table_b_row_03_torn_tail_level_3():
    _assert_marker(3, "torn_tail", True)


def test_table_b_row_03_torn_tail_level_4():
    _assert_marker(4, "torn_tail", True)


def test_table_b_row_03_torn_tail_level_5():
    _assert_marker(5, "torn_tail", True)


def test_table_b_row_03_torn_tail_level_6():
    _assert_marker(6, "torn_tail", True)


def test_table_b_row_05_unrecorded_runs_level_0():
    _assert_marker(0, "unrecorded_runs", 1)


def test_table_b_row_05_unrecorded_runs_level_5():
    _assert_marker(5, "unrecorded_runs", 1)

