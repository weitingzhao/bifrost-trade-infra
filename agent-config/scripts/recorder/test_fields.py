"""Display fields, one named test per other field, and invalid input."""

from __future__ import annotations

import copy
import json

from fold import fold
from harness import APPR, LOCATOR, N, P, R, RUN, WAIT_A, WAIT_D, WORK, LogBuilder, fold_one, round_for, step_of
from model import SCHEMAS
from validate import refusal

_DISPLAY = (
    "title", "goal", "work_ref", "name", "who", "round", "command", "text", "note",
    "quote", "reason_quote", "advice", "reply", "reply_needed", "reply_words",
    "commands", "blocks_text", "blocks_nothing", "after_text", "not_before_text",
    "after", "number", "claim", "closed_claim", "superseded_text", "pid",
)


def _diffs(left, right, path=""):
    found = []
    if type(left) is not type(right):
        found.append((path, left, right))
        return found
    if isinstance(left, dict):
        for key in set(left) | set(right):
            if key not in left or key not in right:
                found.append((f"{path}.{key}", left.get(key, "<missing>"), right.get(key, "<missing>")))
            else:
                found.extend(_diffs(left[key], right[key], f"{path}.{key}"))
        return found
    if isinstance(left, list):
        if len(left) != len(right):
            found.append((path, left, right))
            return found
        for index, (a, b) in enumerate(zip(left, right)):
            found.extend(_diffs(a, b, f"{path}[{index}]"))
        return found
    if left != right:
        found.append((path, left, right))
    return found


def _only_display(events_a, events_b, old, new, now, observer=None):
    left = fold_one(events_a, now, observer=observer)
    right = fold_one(events_b, now, observer=observer)
    diffs = _diffs(left, right)
    for path, a, b in diffs:
        assert a in (old, "<missing>") or (isinstance(a, str) and (old in a or new in a)) or a == old
        assert b in (new, "<missing>") or (isinstance(b, str) and (old in b or new in b)) or b == new
        assert path.split(".")[-1].split("[")[0] in _DISPLAY or path.split(".")[-1] in _DISPLAY or "feed" in path


def _swap(events, index, key, new, now, observer=None):
    other = copy.deepcopy(events)
    old = other[index][key]
    other[index][key] = new
    diffs = _diffs(fold_one(events, now, observer=observer), fold_one(other, now, observer=observer))
    assert diffs, key
    for path, left, right in diffs:
        leaf = path.split(".")[-1].split("[")[0]
        assert leaf in _DISPLAY or leaf == "text", path
        assert _carries(left, old), (path, left, old)
        assert _carries(right, new), (path, right, new)


def _carries(value, expected) -> bool:
    if value == expected:
        return True
    if isinstance(expected, list) and value in expected:
        return True
    if isinstance(value, str) and isinstance(expected, str) and expected in value:
        return True
    return False


def test_display_fields_change_only_the_quoted_text():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="甲", goal="目标", work_ref="ref-a")
    log.add("step_declared", "coordinator", at=2, step_id=P, name="一步", who="甲", kind="other", watch="process", round=1)
    log.add("step_started", "wrapper", at=3, step_id=P, run_id=RUN, command="echo a", pid=1)
    log.add("step_seen", "wrapper", at=4, step_id=P, run_id=RUN, sampled_at=4, alive=True, output_bytes=1, text="看到甲")
    log.add("step_finished", "wrapper", at=5, step_id=P, run_id=RUN, exit={"code": 0}, quote="引甲")
    events = log.events
    _swap(events, 0, "title", "乙", 5)
    _swap(events, 0, "goal", "另一目标", 5)
    _swap(events, 0, "work_ref", "ref-b", 5)
    _swap(events, 1, "name", "二步", 5)
    _swap(events, 1, "who", "乙", 5)
    _swap(events, 1, "round", 2, 5)
    _swap(events, 2, "command", "echo b", 5)
    _swap(events, 3, "text", "看到乙", 5)
    _swap(events, 4, "quote", "引乙", 5)
    with_pid = copy.deepcopy(events)
    with_pid[2]["pid"] = 2
    assert fold_one(events, 5) == fold_one(with_pid, 5)
    note = LogBuilder()
    note.add("work_opened", "coordinator", work_id=WORK, title="T")
    note.add("note", "coordinator", text="甲")
    _swap(note.events, 1, "text", "乙", note.at)
    owner = LogBuilder()
    owner.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    owner.add("step_declared", "coordinator", step_id=N, name="n", kind="other", who="C", watch="none")
    owner.add(
        "owner_wait_opened", "coordinator", wait_id=WAIT_D, title="甲",
        ref={"kind": "none", "id": "c0ffee01"}, can_act="yes", where="terminal",
        advice="甲", reply="甲", reply_needed=False, reply_words="甲",
        commands=["echo 甲"], blocks_text="甲", blocks_nothing=True,
        after_text="甲", not_before_text="甲", after=N,
    )
    owned = owner.events
    _swap(owned, 2, "title", "乙", owner.at)
    _swap(owned, 2, "advice", "乙", owner.at)
    _swap(owned, 2, "reply", "乙", owner.at)
    _swap(owned, 2, "reply_words", "乙", owner.at)
    _swap(owned, 2, "commands", ["echo 乙"], owner.at)
    _swap(owned, 2, "blocks_text", "乙", owner.at)
    _swap(owned, 2, "after_text", "乙", owner.at)
    _swap(owned, 2, "not_before_text", "乙", owner.at)
    without_flag = copy.deepcopy(owned)
    without_flag[2].pop("reply_needed")
    without_flag[2].pop("blocks_nothing")
    without_flag[2].pop("after")
    diffs = _diffs(fold_one(owned, owner.at), fold_one(without_flag, owner.at))
    assert diffs
    for path, _left, _right in diffs:
        leaf = path.split(".")[-1].split("[")[0]
        assert leaf in {"reply_needed", "blocks_nothing", "after"}
    seen = LogBuilder()
    seen.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    seen.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
    seen.add("owner_wait_seen", "observer", wait_id=WAIT_A, sampled_at=1, ref_state="pending", number=1)
    _swap(seen.events, 2, "number", 2, 1, observer=[round_for(1, [f"approval:{APPR}"])])
    closed = LogBuilder()
    closed.add("work_opened", "coordinator", work_id=WORK, title="T")
    closed.add("work_closed", "coordinator", claim="stopped")
    _swap(closed.events, 1, "claim", "dropped", closed.at)


def test_field_step_declared_kind():
    log = LogBuilder()
    log.add("work_opened", "coordinator", work_id=WORK, title="T")
    bad = log.events + [_event(log, "step_declared", "coordinator", step_id=P, name="n", kind="release", who="C", watch="process")]
    assert fold_one(bad, 3)["works"][0]["defects"][-1]["reason"] == "kind_watch"


def test_field_step_declared_watch():
    none = LogBuilder()
    none.add("work_opened", "coordinator", work_id=WORK, title="T")
    none.add("step_declared", "coordinator", step_id=N, name="n", kind="other", who="C", watch="none")
    none.add("step_started", "coordinator", step_id=N, run_id=RUN)
    assert step_of(fold_one(none.events, none.at))["label"] == "Reported started, not watched"
    proc = LogBuilder()
    proc.add("work_opened", "coordinator", work_id=WORK, title="T")
    proc.add("step_declared", "coordinator", step_id=P, name="n", kind="other", who="C", watch="process")
    proc.add("step_started", "wrapper", step_id=P, run_id=RUN, command="echo")
    proc.add("step_seen", "wrapper", step_id=P, run_id=RUN, sampled_at=proc.at, alive=True, output_bytes=1)
    step = step_of(fold_one(proc.events, proc.at))
    assert step["state"] == "running"
    assert "started_how" not in step


def test_field_step_declared_waiting_on():
    log = LogBuilder()
    log.add("work_opened", "coordinator", work_id=WORK, title="T")
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_D, title="请看", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet")
    refused = _event(log, "step_declared", "coordinator", step_id=P, name="n", kind="other", who="C", watch="process", waiting_on=[WAIT_D])
    assert refusal(log.events, refused, work_id=WORK) == "process_waiting_on"
    log.add("step_declared", "coordinator", step_id=N, name="n", kind="other", who="C", watch="none", waiting_on=[WAIT_D])
    started = _event(log, "step_started", "coordinator", step_id=N, run_id=RUN)
    assert refusal(log.events, started, work_id=WORK) == "waits_open"
    record = LogBuilder()
    record.add("work_opened", "coordinator", at=10, work_id=WORK, title="T")
    record.add("owner_wait_opened", "coordinator", wait_id=WAIT_D, title="请看", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet")
    record.add("step_declared", "coordinator", step_id=R, name="发布", kind="release", who="C", watch="record", locator=LOCATOR, waiting_on=[WAIT_D])
    record.add("record_seen", "observer", step_id=R, sampled_at=10, found=False)
    waiting = fold_one(record.events, 10, observer=[round_for(10, [f"step:{WORK}/{R}"])])
    assert step_of(waiting)["state"] == "waiting"
    assert waiting["owner_all"][0]["holds_up"] == [R]
    record.events[2].pop("waiting_on")
    missing = fold_one(record.events, 10, observer=[round_for(10, [f"step:{WORK}/{R}"])])
    assert step_of(missing)["state"] == "unknown"
    assert step_of(missing)["reason"] == "no_match"


def test_field_step_declared_after():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_D, title="请看", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet")
    log.add("step_declared", "coordinator", step_id=P, name="first", kind="other", who="C", watch="none", waiting_on=[WAIT_D])
    log.add("step_declared", "coordinator", step_id=N, name="second", kind="other", who="C", watch="none", after=P)
    without = copy.deepcopy(log.events)
    without[3].pop("after")
    left = fold_one(log.events, log.at)
    right = fold_one(without, log.at)
    assert [step["state"] for step in left["works"][0]["steps"]] == [step["state"] for step in right["works"][0]["steps"]]
    assert left["owner_all"][0]["holds_up"] == [P, N]
    assert right["owner_all"][0]["holds_up"] == [P]
    assert left["ball"]["why"] == "owner_item_not_ready"
    assert right["ball"]["why"] == "next_not_sent"


def test_field_step_declared_locator_name():
    log = LogBuilder()
    log.add("work_opened", "coordinator", work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=R, name="发布", kind="release", who="C", watch="record", locator={"cluster": "prod", "namespace": "cicd"})
    step = step_of(fold_one(log.events, log.at))
    assert step["state"] == "waiting"
    assert "last_seen" not in step


def test_field_step_declared_usual_s():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=0, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=P, name="n", kind="other", who="C", watch="process", usual_s=10, usual_basis="declared")
    log.add("step_started", "wrapper", at=0, step_id=P, run_id=RUN, command="echo")
    log.add("step_seen", "wrapper", at=1, step_id=P, run_id=RUN, sampled_at=1, alive=True, output_bytes=1)
    running = step_of(fold_one(log.events, 1))
    assert running["state"] == "running"
    slow = step_of(fold_one(log.events, 20))
    assert slow["state"] == "slow"
    assert slow["overdue"] == 10
    assert slow["eta_end"] == 10
    bare = copy.deepcopy(log.events)
    bare[1].pop("usual_s")
    bare[1].pop("usual_basis")
    assert "usual_s" not in step_of(fold_one(bare, 20))
    assert fold_one(bare, 20)["works"][0]["eta_unsure"] is True


def test_field_step_superseded_by_step():
    log = LogBuilder()
    log.add("work_opened", "coordinator", work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=P, name="old", kind="other", who="C", watch="none")
    log.add("step_started", "coordinator", step_id=P, run_id=RUN)
    log.add("step_declared", "coordinator", step_id=N, name="new", kind="other", who="C", watch="none")
    log.add("step_superseded", "coordinator", step_id=P, by_step=N)
    marked = fold_one(log.events, log.at)
    assert marked["works"][0]["steps"][0]["state"] == "running"
    assert marked["works"][0]["steps"][0]["superseded_by"] == N
    unstarted = LogBuilder()
    unstarted.add("work_opened", "coordinator", work_id=WORK, title="T")
    unstarted.add("step_declared", "coordinator", step_id=P, name="old", kind="other", who="C", watch="none")
    unstarted.add("step_declared", "coordinator", step_id=N, name="new", kind="other", who="C", watch="none")
    unstarted.add("step_superseded", "coordinator", step_id=P, by_step=N)
    gone = fold_one(unstarted.events, unstarted.at)
    assert [step["step_id"] for step in gone["works"][0]["steps"]] == [N]
    assert gone["works"][0]["withdrawn"] == 1
    withdrawn = LogBuilder()
    withdrawn.add("work_opened", "coordinator", work_id=WORK, title="T")
    withdrawn.add("step_declared", "coordinator", step_id=P, name="old", kind="other", who="C", watch="none")
    withdrawn.add("step_superseded", "coordinator", step_id=P)
    assert fold_one(withdrawn.events, withdrawn.at)["works"][0]["steps"] == []
    started = _event(withdrawn, "step_started", "coordinator", step_id=P, run_id=RUN)
    # The step was withdrawn. A start is superseded.
    assert refusal(withdrawn.events, started, work_id=WORK) == "superseded"


def test_field_step_seen_alive():
    log = _running()
    log.add("step_seen", "observer", step_id=P, run_id=RUN, sampled_at=log.at, alive=False)
    step = step_of(fold_one(log.events, log.at))
    assert step["state"] == "dead"
    assert step["reason"] == "wrapper_gone"


def test_field_step_seen_output_bytes():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=0, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=P, name="n", kind="other", who="C", watch="process")
    log.add("step_started", "wrapper", at=0, step_id=P, run_id=RUN, command="echo")
    log.add("step_seen", "wrapper", at=10, step_id=P, run_id=RUN, sampled_at=10, alive=True, output_bytes=4)
    log.add("step_seen", "wrapper", at=500, step_id=P, run_id=RUN, sampled_at=500, alive=True, output_bytes=4)
    assert step_of(fold_one(log.events, 500))["state"] == "quiet"
    assert step_of(fold_one(log.events, 500))["reason"] == "no_output"


def test_field_step_seen_sampled_at():
    log = _running()
    log.add("step_seen", "wrapper", at=log.at + 200, step_id=P, run_id=RUN, sampled_at=log.at + 200, alive=True, output_bytes=2)
    during = fold_one(log.events[:4], log.events[2]["at"] + 181)
    assert step_of(during)["state"] == "unknown"
    assert step_of(during)["reason"] == "no_observation"
    recovered = fold_one(log.events, log.at)
    assert step_of(recovered)["state"] == "running"
    assert step_of(recovered).get("gap") is True


def test_field_step_finished_exit():
    log = _running()
    log.add("step_finished", "wrapper", step_id=P, run_id=RUN, exit={"code": 0})
    done = step_of(fold_one(log.events, log.at))
    assert done["state"] == "done" and done["ended_how"] == "exit_0"
    log.events[-1]["exit"] = {"code": 9}
    failed = step_of(fold_one(log.events, log.at))
    assert failed["state"] == "failed" and failed["reason"] == "exited_nonzero"
    log.events[-1]["exit"] = {"signal": "TERM"}
    signaled = step_of(fold_one(log.events, log.at))
    assert signaled["reason"] == "ended_by_signal"


def test_field_step_finished_reported():
    log = LogBuilder()
    log.add("work_opened", "coordinator", work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=N, name="n", kind="other", who="C", watch="none")
    log.add("step_started", "coordinator", step_id=N, run_id=RUN)
    log.add("step_finished", "coordinator", step_id=N, run_id=RUN, reported="finished")
    done = step_of(fold_one(log.events, log.at))
    assert done["state"] == "done" and done["ended_how"] == "reported"
    log.events[-1]["reported"] = "failed"
    failed = step_of(fold_one(log.events, log.at))
    assert failed["state"] == "failed" and failed["reason"] == "reported_failed"


def test_field_record_seen_found_uid_started_at_ended_at_condition():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=10, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=R, name="发布", kind="release", who="C", watch="record", locator=LOCATOR)
    log.add("record_seen", "observer", step_id=R, sampled_at=10, found=True, uid="uid-1")
    observer = [round_for(10, [f"step:{WORK}/{R}"])]
    assert step_of(fold_one(log.events, 10, observer=observer))["state"] == "waiting"
    changed = _event(log, "record_seen", "observer", step_id=R, sampled_at=11, found=True, uid="uid-2")
    assert refusal(log.events, changed, work_id=WORK) == "uid_changed"
    log.add("record_seen", "observer", at=12, step_id=R, sampled_at=12, found=True, uid="uid-1", started_at=11)
    assert step_of(fold_one(log.events, 12, observer=[round_for(12, [f"step:{WORK}/{R}"], round_id="ab12cd35")]))["state"] == "running"
    log.add("record_seen", "observer", at=14, step_id=R, sampled_at=14, found=True, uid="uid-1", condition="False", started_at=11, ended_at=13, reason_quote="nope")
    failed = step_of(fold_one(log.events, 14, observer=[round_for(14, [f"step:{WORK}/{R}"], round_id="ab12cd36")]))
    assert failed["state"] == "failed" and failed["reason"] == "record_failed"
    assert failed["ended"] == 13
    true = LogBuilder()
    true.add("work_opened", "coordinator", at=10, work_id=WORK, title="T")
    true.add("step_declared", "coordinator", step_id=R, name="发布", kind="release", who="C", watch="record", locator=LOCATOR)
    true.add("record_seen", "observer", step_id=R, sampled_at=10, found=True, uid="uid-1", condition="True", started_at=8, ended_at=9)
    done = step_of(fold_one(true.events, 10, observer=observer))
    assert done["state"] == "done" and done["ended_how"] == "record" and done["ended"] == 9 and done["started"] == 8


def test_field_owner_wait_opened_ref_can_act_deadline_where_ready_and_how():
    declared = LogBuilder()
    declared.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    declared.add("owner_wait_opened", "coordinator", wait_id=WAIT_D, title="请看", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet", deadline=50)
    declared.add("owner_wait_opened", "coordinator", wait_id="b2b2b2b2", title="后", ref={"kind": "none", "id": "c0ffee02"}, can_act="yes", no_deadline=True)
    doc = fold_one(declared.events, 1)
    assert [item["can_act"] for item in doc["owner_all"]] == ["yes", "not_yet"]
    assert doc["owner_all"][1]["deadline"] == 50
    assert doc["owner_all"][0]["no_deadline"] is True
    bad_where = _event(declared, "owner_wait_opened", "coordinator", wait_id="c3c3c3c3", title="x", ref={"kind": "none", "id": "c0ffee03"}, can_act="yes", where="phone")
    assert refusal(declared.events, bad_where, work_id=WORK) == "bad_value"
    ready = _event(declared, "owner_wait_ready", "coordinator", wait_id=WAIT_D)
    assert refusal(declared.events, ready, work_id=WORK) is None
    opened = fold_one(declared.events + [ready], 2)
    assert opened["owner_all"][1]["can_act"] == "yes"
    bound = LogBuilder()
    bound.add("work_opened", "coordinator", work_id=WORK, title="T")
    bound.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
    close = _event(bound, "owner_wait_closed", "coordinator", wait_id=WAIT_A, how="done")
    assert refusal(bound.events, close, work_id=WORK) == "bound_wait"
    withdraw = _event(bound, "owner_wait_closed", "coordinator", wait_id=WAIT_A, how="withdrawn")
    assert refusal(bound.events, withdraw, work_id=WORK) is None
    gone = fold_one(bound.events + [withdraw], bound.at + 1)
    assert gone["owner_all"] == []


def test_field_owner_wait_seen_ref_state_expires_at_sampled_at():
    def seen(state, sampled, expires=None):
        log = LogBuilder()
        log.add("work_opened", "coordinator", at=sampled, work_id=WORK, title="T")
        log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
        fields = {"wait_id": WAIT_A, "sampled_at": sampled, "ref_state": state}
        if expires is not None:
            fields["expires_at"] = expires
        log.add("owner_wait_seen", "observer", **fields)
        return fold_one(log.events, sampled, observer=[round_for(sampled, [f"approval:{APPR}"])])
    assert seen("pending", 10)["owner_all"][0]["can_act"] == "yes"
    assert seen("pending", 10, expires=80)["owner_all"][0]["deadline"] == 80
    assert seen("executed", 10)["owner_all"] == []
    early = LogBuilder()
    early.add("work_opened", "coordinator", at=10, work_id=WORK, title="T")
    early.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
    early.add("owner_wait_seen", "observer", at=10, wait_id=WAIT_A, sampled_at=10, ref_state="pending")
    late = LogBuilder()
    late.add("work_opened", "coordinator", at=12, work_id="w2", title="w2")
    late.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
    late.add("owner_wait_seen", "observer", at=12, wait_id=WAIT_A, sampled_at=12, ref_state="approved")
    doc = fold(
        [{"work_id": WORK, "events": early.events}, {"work_id": "w2", "events": late.events}],
        [round_for(12, [f"approval:{APPR}"])],
        12,
    )
    assert doc["owner_all"] == []
    assert doc["ball"]["why"] == "record_in_flight"


def test_field_observer_round_ended_at_confirmed_failed():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=10, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=R, name="发布", kind="release", who="C", watch="record", locator=LOCATOR)
    log.add("record_seen", "observer", step_id=R, sampled_at=10, found=True, uid="uid-1", started_at=9)
    confirmed = fold_one(log.events, 10, observer=[round_for(10, [f"step:{WORK}/{R}"])])
    assert step_of(confirmed)["state"] == "running"
    failed = fold_one(log.events, 10, observer=[round_for(10, [], [{"key": f"step:{WORK}/{R}", "error": "forbidden"}])])
    assert step_of(failed)["reason"] == "forbidden"
    stale = fold_one(log.events, 10 + 181, observer=[round_for(10, [f"step:{WORK}/{R}"])])
    assert step_of(stale)["reason"] == "not_confirmed"


def test_field_work_closed():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=N, name="n", kind="other", who="C", watch="none")
    forged = _event(log, "work_closed", "coordinator", claim="stopped")
    assert refusal(log.events, forged, work_id=WORK) == "closed_with_open_items"
    doc = fold_one(log.events + [forged], log.at + 1)
    assert "closed_claim" not in doc["works"][0]
    assert doc["ball"]["holder"] != "nobody"
    empty = LogBuilder()
    empty.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    empty.add("work_closed", "coordinator", at=2, claim="landed")
    closed = fold_one(empty.events, 2)
    assert closed["works"][0]["closed_claim"] == "landed"
    assert closed["ball"]["holder"] == "nobody"


def test_field_envelope_at_by_run_id_step_id_wait_id():
    log = _running()
    assert step_of(fold_one(log.events, log.at))["started"] == log.events[2]["at"]
    mismatch = _event(log, "step_seen", "coordinator", step_id=P, run_id=RUN, sampled_at=log.at + 1, alive=True, output_bytes=2)
    assert refusal(log.events, mismatch, work_id=WORK) == "by_mismatch"
    wrong_run = _event(log, "step_seen", "wrapper", step_id=P, run_id="00000000", sampled_at=log.at + 1, alive=True, output_bytes=2)
    assert refusal(log.events, wrong_run, work_id=WORK) == "run_mismatch"
    missing_step = _event(log, "step_seen", "wrapper", step_id="aaaaaaaa", run_id=RUN, sampled_at=log.at + 1, alive=True)
    assert refusal(log.events, missing_step, work_id=WORK) == "not_declared"
    missing_wait = _event(log, "owner_wait_ready", "coordinator", wait_id="bbbbbbbb")
    assert refusal(log.events, missing_wait, work_id=WORK) == "wait_missing"
    backwards = LogBuilder()
    backwards.add("work_opened", "coordinator", at=300, work_id=WORK, title="T")
    backwards.add("note", "coordinator", at=100, text="back")
    doc = fold_one(backwards.events, 100)
    assert doc["clock"]["reader_behind"] is True


def test_invalid_event_is_absent():
    """Delete a required field, change a type, leave the closed set, add a field, or rename type."""
    base = LogBuilder()
    base.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    base.add("step_declared", "coordinator", step_id=P, name="n", kind="other", who="C", watch="process")
    base.add("step_started", "wrapper", step_id=P, run_id=RUN, command="echo")
    samples = {
        "work_opened": {"work_id": "w9", "title": "T"},
        "work_closed": {"claim": "stopped"},
        "step_declared": {"step_id": N, "name": "m", "kind": "other", "who": "C", "watch": "none"},
        "step_superseded": {"step_id": P},
        "step_started": {"step_id": N, "run_id": "aaaaaaaa"},
        "step_seen": {"step_id": P, "run_id": RUN, "sampled_at": 1, "alive": True, "output_bytes": 1},
        "step_finished": {"step_id": P, "run_id": RUN, "exit": {"code": 0}},
        "record_seen": {"step_id": R, "sampled_at": 1, "found": False},
        "owner_wait_opened": {"wait_id": WAIT_D, "title": "t", "ref": {"kind": "none", "id": "c0ffee01"}, "can_act": "yes"},
        "owner_wait_seen": {"wait_id": WAIT_A, "sampled_at": 1, "ref_state": "pending"},
        "owner_wait_ready": {"wait_id": WAIT_D},
        "owner_wait_closed": {"wait_id": WAIT_D, "how": "done"},
        "note": {"text": "n"},
        "observer_round": {"round_id": "ab12cd34", "started_at": 1, "ended_at": 1, "confirmed": [], "failed": []},
        "tail_repaired": {"repair_id": "0-0123456789abcdef", "bytes": 1, "sha256": "ab" * 32},
    }
    # Context that makes the record and the approval wait exist, so a well-typed
    # mutation is the thing under test. Shape failures do not need that context.
    for kind, fields in samples.items():
        schema = SCHEMAS[kind]
        event = {"type": kind, "v": 1, "seq": 99, "prev_sha256": "", "at": 50, "by": "coordinator"}
        event.update(fields)
        mutations = []
        for key in schema["required"]:
            missing = dict(event)
            missing.pop(key, None)
            mutations.append(missing)
        mutated_type = dict(event)
        for key, value in list(mutated_type.items()):
            if isinstance(value, str):
                mutated_type[key] = 1
                break
        mutations.append(mutated_type)
        if kind == "work_closed":
            bad_value = dict(event)
            bad_value["claim"] = "passed"
            mutations.append(bad_value)
        extra = dict(event)
        extra["not_a_field"] = 1
        mutations.append(extra)
        unknown = dict(event)
        unknown["type"] = "not_an_event"
        mutations.append(unknown)
        for broken in mutations:
            doc = fold_one(base.events + [broken], 50)
            assert doc["works"][0]["defects"], kind
            seqs = {item["seq"] for item in doc["works"][0]["defects"]}
            assert broken.get("seq", 99) in seqs or any(item["reason"] for item in doc["works"][0]["defects"])
            kept = fold_one(base.events, 50)
            assert _without(doc) == _without(kept)


def _without(doc):
    copied = json.loads(json.dumps(doc))
    for work in copied["works"]:
        work.pop("defects", None)
    return copied


def _event(log: LogBuilder, typ: str, by: str, **fields) -> dict:
    from harness import ev
    return ev(len(log.events) + 1, log.at + 1, typ, by, **fields)


def _running() -> LogBuilder:
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=10, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=P, name="n", kind="other", who="C", watch="process")
    log.add("step_started", "wrapper", at=10, step_id=P, run_id=RUN, command="echo")
    log.add("step_seen", "wrapper", at=10, step_id=P, run_id=RUN, sampled_at=10, alive=True, output_bytes=1)
    return log
