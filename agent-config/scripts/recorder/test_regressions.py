"""One named test for each regression in design section 7 item 3.

Logs here are synthetic. Nothing starts a process or reads a platform.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from commands import RecorderError, close_work, declare_step, open_work, owner_close
from events import append_sealed, load_file
from locks import hold
from estimate import usual_for
from fold import fold, select_logs
from harness import (
    APPR,
    LOCATOR,
    N,
    P,
    QUESTION,
    R,
    RUN,
    RUN2,
    WAIT_A,
    WAIT_D,
    WORK,
    LogBuilder,
    fold_one,
    round_for,
    save_log,
    step_of,
    work_of,
)
from validate import refusal

HERE = Path(__file__).resolve().parent
REC = HERE / "rec.py"


def _rec(root, *args):
    return subprocess.run(
        [sys.executable, str(REC), "--root", str(root), *args],
        capture_output=True,
        text=True,
    )


def _process(log: LogBuilder, step=P, run=RUN, at=None, command="echo hi"):
    log.add("step_declared", "coordinator", at, step_id=step, name="实现", kind="implement", who="Cursor", watch="process")
    log.add("step_started", "wrapper", step_id=step, run_id=run, command=command)


def test_release_cannot_be_a_process_and_a_process_cannot_wait(tmp_path):
    open_work(tmp_path, WORK, "T")
    refused = _rec(
        tmp_path, "declare", "--work", WORK, "--name", "rel", "--kind", "release",
        "--who", "C", "--watch", "process",
    )
    assert refused.returncode != 0
    log = LogBuilder()
    log.add("work_opened", "coordinator", work_id=WORK, title="T")
    log.add(
        "step_declared", "coordinator", step_id=P, name="rel", kind="other", who="C",
        watch="process", waiting_on=[WAIT_D],
    )
    reason = refusal(log.events[:-1], log.events[-1], work_id=WORK)
    assert reason == "process_waiting_on"


def test_record_without_started_at_is_waiting_then_running_and_the_ball_follows():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=10, work_id=WORK, title="发布")
    log.add(
        "step_declared", "coordinator", step_id=R, name="发布", kind="release", who="C",
        watch="record", locator=LOCATOR,
    )
    log.add(
        "record_seen", "observer", at=20, step_id=R, sampled_at=20, found=True, uid="uid-1",
    )
    confirmed = [f"step:{WORK}/{R}"]
    waiting = fold_one(log.events, 20, observer=[round_for(20, confirmed)])
    step = step_of(waiting)
    assert step["state"] == "waiting"
    assert "started" not in step
    assert waiting["ball"] == {"holder": "agents", "why": "record_created", "since": 20}
    log.add(
        "record_seen", "observer", at=30, step_id=R, sampled_at=30, found=True, uid="uid-1",
        started_at=25,
    )
    running = fold_one(log.events, 30, observer=[round_for(30, confirmed, round_id="ab12cd35")])
    assert step_of(running)["state"] == "running"
    assert step_of(running)["started"] == 25
    expired = fold_one(log.events, 30 + 181, observer=[round_for(30, confirmed, round_id="ab12cd35")])
    assert step_of(expired)["state"] == "unknown"
    assert expired["ball"]["holder"] == "unknown"


def test_a_record_step_stays_waiting_and_rejects_process_events():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="发布")
    log.add(
        "step_declared", "coordinator", step_id=R, name="发布", kind="release", who="C",
        watch="record", locator={"cluster": "prod", "namespace": "cicd"},
    )
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
    for at, rid in ((100, "ab12cd34"), (4000, "ab12cd35")):
        log.add("owner_wait_seen", "observer", at=at, wait_id=WAIT_A, sampled_at=at, ref_state="pending")
    rounds = [round_for(100, [f"approval:{APPR}"], round_id="ab12cd34"), round_for(4000, [f"approval:{APPR}"], round_id="ab12cd35")]
    doc = fold_one(log.events, 4000, observer=rounds)
    assert step_of(doc)["state"] == "waiting"
    started = ev_copy(log, "step_started", "wrapper", step_id=R, run_id=RUN, command="watch")
    assert refusal(log.events, started, work_id=WORK) == "watch_mismatch"
    seen = ev_copy(log, "step_seen", "wrapper", step_id=R, run_id=RUN, sampled_at=4001, alive=True, output_bytes=1)
    assert refusal(log.events, seen, work_id=WORK) == "watch_mismatch"


def ev_copy(log, typ, by, **fields):
    from harness import ev
    return ev(len(log.events) + 1, log.at + 1, typ, by, **fields)


def test_other_process_keeps_watch_kind_and_command():
    log = LogBuilder()
    log.add("work_opened", "coordinator", work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=P, name="发布", kind="other", who="Cursor", watch="process")
    log.add("step_started", "wrapper", step_id=P, run_id=RUN, command="watch-agents.sh")
    log.add("step_seen", "wrapper", step_id=P, run_id=RUN, sampled_at=log.at, alive=True, output_bytes=3)
    step = step_of(fold_one(log.events, log.at))
    assert step["watch"] == "process"
    assert step["kind"] == "other"
    assert step["command"] == "watch-agents.sh"
    assert step["state"] == "running"


def test_a_finished_round_is_unchanged_when_the_next_round_runs():
    first = LogBuilder()
    first.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    _process(first, at=2)
    first.add("step_seen", "wrapper", step_id=P, run_id=RUN, sampled_at=3, alive=True, output_bytes=4)
    first.add("step_finished", "wrapper", step_id=P, run_id=RUN, exit={"code": 0})
    before = fold_one(first.events, first.at)
    saved = step_of(before)
    first.add("step_declared", "coordinator", step_id=N, name="next", kind="implement", who="Cursor", watch="process")
    first.add("step_started", "wrapper", step_id=N, run_id=RUN2, command="echo next")
    first.add("step_seen", "wrapper", step_id=N, run_id=RUN2, sampled_at=first.at, alive=True, output_bytes=1)
    after = fold_one(first.events, first.at)
    assert step_of(after, 0) == saved
    heartbeat = ev_copy(first, "step_seen", "wrapper", step_id=P, run_id=RUN2, sampled_at=first.at + 1, alive=True, output_bytes=9)
    assert refusal(first.events, heartbeat, work_id=WORK) == "run_mismatch"


def test_two_rounds_without_replaces_are_both_running():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    _process(log, at=2, command="echo old")
    log.add("step_seen", "wrapper", step_id=P, run_id=RUN, sampled_at=log.at, alive=True, output_bytes=2)
    log.add("step_declared", "coordinator", step_id=N, name="new", kind="implement", who="Cursor", watch="process")
    log.add("step_started", "wrapper", step_id=N, run_id=RUN2, command="echo new")
    log.add("step_seen", "wrapper", step_id=N, run_id=RUN2, sampled_at=log.at, alive=True, output_bytes=1)
    log.add("step_seen", "wrapper", step_id=P, run_id=RUN, sampled_at=log.at, alive=True, output_bytes=3)
    doc = fold_one(log.events, log.at)
    states = [step["state"] for step in work_of(doc)["steps"]]
    assert states == ["running", "running"]
    assert "superseded_by" not in work_of(doc)["steps"][0]


def test_replaces_marks_the_old_step_and_its_death_does_not_touch_the_new_one():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    _process(log, at=2, command="echo old")
    log.add("step_seen", "wrapper", step_id=P, run_id=RUN, sampled_at=log.at, alive=True, output_bytes=2)
    log.add("step_superseded", "coordinator", step_id=P, by_step=N)
    log.add("step_declared", "coordinator", step_id=N, name="new", kind="implement", who="Cursor", watch="process")
    # by_step must already exist. Declare first.
    log.events = log.events[:-2] + [log.events[-1], log.events[-2]]
    for index, event in enumerate(log.events, start=1):
        event["seq"] = index
    log.add("step_started", "wrapper", step_id=N, run_id=RUN2, command="echo new")
    log.add("step_seen", "wrapper", step_id=N, run_id=RUN2, sampled_at=log.at, alive=True, output_bytes=1)
    marked = fold_one(log.events, log.at)
    old = work_of(marked)["steps"][0]
    assert old["state"] == "running"
    assert old["superseded_by"] == N
    log.add("step_seen", "observer", step_id=P, run_id=RUN, sampled_at=log.at, alive=False)
    dead = fold_one(log.events, log.at)
    assert work_of(dead)["steps"][0]["state"] == "dead"
    assert work_of(dead)["steps"][1]["state"] == "running"


def test_dead_then_finished_is_done_and_a_later_heartbeat_is_refused():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    _process(log, at=2)
    running = fold_one(log.events, log.at)
    assert step_of(running)["state"] == "running"
    log.add("step_seen", "observer", step_id=P, run_id=RUN, sampled_at=log.at, alive=False)
    dead = fold_one(log.events, log.at)
    assert step_of(dead)["state"] == "dead"
    assert step_of(dead)["reason"] == "wrapper_gone"
    log.add("step_finished", "wrapper", step_id=P, run_id=RUN, exit={"code": 0})
    done = fold_one(log.events, log.at)
    step = step_of(done)
    assert step["state"] == "done"
    assert step["label"] == "Exited 0"
    assert step["was_seen_dead"] is True
    later = ev_copy(log, "step_seen", "wrapper", step_id=P, run_id=RUN, sampled_at=log.at + 1, alive=True, output_bytes=1)
    assert refusal(log.events, later, work_id=WORK) == "already_ended"


def test_close_while_an_approval_is_pending_is_refused_and_the_ball_is_owner(tmp_path):
    specs = [
        ("coordinator", 1, {"type": "work_opened", "work_id": WORK, "title": "T"}),
        ("coordinator", 2, {"type": "owner_wait_opened", "wait_id": WAIT_A, "title": "请批", "ref": {"kind": "approval", "id": APPR}}),
        ("observer", 3, {"type": "owner_wait_seen", "wait_id": WAIT_A, "sampled_at": 3, "ref_state": "pending"}),
    ]
    save_log(tmp_path / WORK, specs)
    try:
        close_work(tmp_path, WORK, "stopped")
    except RecorderError as exc:
        assert exc.reason == "closed_with_open_items"
    else:
        raise AssertionError("close was accepted")
    events = specs_as_events(specs)
    forged = ev_copy_at(events, "work_closed", "coordinator", 4, claim="stopped")
    doc = fold_one(events + [forged], 4, observer=[round_for(4, [f"approval:{APPR}"])])
    assert "closed_claim" not in work_of(doc)
    assert work_of(doc)["defects"][-1]["reason"] == "closed_with_open_items"
    assert len(doc["owner_all"]) == 1
    assert doc["owner_all"][0]["can_act"] == "yes"
    assert doc["ball"]["holder"] == "owner"
    assert doc["ball"]["why"] == "owner_can_act"


def specs_as_events(specs):
    from events import Log, dump_line, seal
    log = Log()
    events = []
    for by, at, fields in specs:
        sealed = seal(dict(fields), log, by, at)
        line = dump_line(sealed)
        log.events.append(sealed)
        log.digests.append(line.split(b" ", 1)[0].decode("ascii"))
        events.append(sealed)
    return events


def ev_copy_at(events, typ, by, at, **fields):
    from harness import ev
    return ev(len(events) + 1, at, typ, by, **fields)


def test_close_while_a_record_step_is_running_is_invalid():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=10, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=R, name="发布", kind="release", who="C", watch="record", locator=LOCATOR)
    log.add("record_seen", "observer", step_id=R, sampled_at=log.at, found=True, uid="uid-1", started_at=8)
    observer = [round_for(log.at, [f"step:{WORK}/{R}"])]
    doc = fold_one(log.events, log.at, observer=observer)
    assert step_of(doc)["state"] == "running"
    assert doc["ball"]["holder"] == "agents"
    forged = ev_copy(log, "work_closed", "coordinator", claim="landed")
    closed = fold_one(log.events + [forged], log.at + 1, observer=observer)
    assert "closed_claim" not in work_of(closed)
    assert work_of(closed)["defects"][-1]["reason"] == "closed_with_open_items"


def test_close_while_a_none_step_is_started_is_invalid():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=N, name="手工", kind="other", who="C", watch="none")
    log.add("step_started", "coordinator", step_id=N, run_id=RUN)
    doc = fold_one(log.events, log.at)
    assert step_of(doc)["state"] == "running"
    assert doc["ball"]["holder"] == "agents"
    forged = ev_copy(log, "work_closed", "coordinator", claim="stopped")
    closed = fold_one(log.events + [forged], log.at + 1)
    assert work_of(closed)["defects"][-1]["reason"] == "closed_with_open_items"
    assert doc["ball"]["holder"] == "agents"


def test_close_while_approval_is_approved_is_invalid():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
    log.add("owner_wait_seen", "observer", wait_id=WAIT_A, sampled_at=log.at, ref_state="approved")
    forged = ev_copy(log, "work_closed", "coordinator", claim="landed")
    assert refusal(log.events, forged, work_id=WORK) == "closed_with_open_items"


def test_close_with_only_a_dead_step_then_the_finish_arrives(tmp_path):
    specs = [
        ("coordinator", 1, {"type": "work_opened", "work_id": WORK, "title": "T"}),
        ("coordinator", 2, {"type": "step_declared", "step_id": P, "name": "实现", "kind": "implement", "who": "C", "watch": "process"}),
        ("wrapper", 3, {"type": "step_started", "step_id": P, "run_id": RUN, "command": "echo"}),
        ("observer", 4, {"type": "step_seen", "step_id": P, "run_id": RUN, "sampled_at": 4, "alive": False}),
    ]
    save_log(tmp_path / WORK, specs)
    closed = close_work(tmp_path, WORK, "stopped")
    assert closed["type"] == "work_closed"
    from events import load_file
    from commands import finish_step
    # finish_step is for a none step. The late exit is a wrapper event, appended
    # the same way the log already accepts a finish after close.
    from commands import _write
    late = _write(
        tmp_path, WORK,
        [{"type": "step_finished", "step_id": P, "run_id": RUN, "exit": {"code": 0}}],
        "wrapper", "finish",
    )[0]
    assert late["type"] == "step_finished"
    loaded = load_file(tmp_path / WORK / "events.jsonl")
    doc = fold_one(loaded.events, loaded.events[-1]["at"])
    assert work_of(doc)["closed_claim"] == "stopped"
    assert step_of(doc)["state"] == "done"
    assert step_of(doc)["was_seen_dead"] is True


def test_after_close_declare_and_owner_open_are_invalid(tmp_path):
    open_work(tmp_path, WORK, "T")
    close_work(tmp_path, WORK, "dropped")
    try:
        declare_step(tmp_path, WORK, name="n", kind="other", who="C", watch="none")
    except RecorderError as exc:
        assert exc.reason == "after_close"
    else:
        raise AssertionError("declare was accepted")
    try:
        from commands import owner_open
        owner_open(tmp_path, WORK, "ask", can_act="yes")
    except RecorderError as exc:
        assert exc.reason == "after_close"
    else:
        raise AssertionError("owner-open was accepted")


def test_approval_states_follow_the_bound_wait_table():
    def item_for(state):
        log = LogBuilder()
        log.add("work_opened", "coordinator", at=10, work_id=WORK, title="T")
        log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
        log.add("owner_wait_seen", "observer", wait_id=WAIT_A, sampled_at=10, ref_state=state)
        doc = fold_one(log.events, 10, observer=[round_for(10, [f"approval:{APPR}"])])
        return doc
    for state in ("pending", "unknown"):
        doc = item_for(state)
        assert len(doc["owner_all"]) == 1
        assert doc["owner_all"][0]["can_act"] == "yes"
        assert doc["owner_all"][0]["ref_state"] == state
        assert "reason" not in doc["owner_all"][0]
    for state in ("approved", "running"):
        doc = item_for(state)
        assert doc["owner_all"] == []
        assert doc["ball"]["why"] == "record_in_flight"
    for state in ("executed", "failed", "rejected", "expired"):
        doc = item_for(state)
        assert doc["owner_all"] == []
        assert doc["ball"]["holder"] == "coordinator"


def test_approved_then_platform_unknown_returns_to_the_list():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=10, work_id=WORK, title="T")
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
    log.add("owner_wait_seen", "observer", at=10, wait_id=WAIT_A, sampled_at=10, ref_state="approved")
    hidden = fold_one(log.events, 10, observer=[round_for(10, [f"approval:{APPR}"])])
    assert hidden["owner_all"] == []
    log.add("owner_wait_seen", "observer", at=20, wait_id=WAIT_A, sampled_at=20, ref_state="unknown")
    back = fold_one(log.events, 20, observer=[round_for(20, [f"approval:{APPR}"], round_id="ab12cd35")])
    assert back["owner_all"][0]["can_act"] == "yes"
    assert back["owner_all"][0]["ref_state"] == "unknown"


def test_a_terminal_observation_stays_out_when_a_later_round_fails():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=10, work_id=WORK, title="T")
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
    log.add("owner_wait_seen", "observer", wait_id=WAIT_A, sampled_at=10, ref_state="executed")
    rounds = [
        round_for(10, [f"approval:{APPR}"]),
        round_for(20, [], [{"key": f"approval:{APPR}", "error": "timeout"}], round_id="ab12cd35"),
    ]
    doc = fold_one(log.events, 20, observer=rounds)
    assert doc["owner_all"] == []


def test_owner_close_of_a_bound_wait_is_refused(tmp_path):
    specs = [
        ("coordinator", 1, {"type": "work_opened", "work_id": WORK, "title": "T"}),
        ("coordinator", 2, {"type": "owner_wait_opened", "wait_id": WAIT_A, "title": "请批", "ref": {"kind": "approval", "id": APPR}}),
    ]
    save_log(tmp_path / WORK, specs)
    try:
        owner_close(tmp_path, WORK, WAIT_A, "done")
    except RecorderError as exc:
        assert exc.reason == "bound_wait"
    else:
        raise AssertionError("owner-close was accepted")


def test_read_errors_make_the_item_unknown_and_keep_the_last_state():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=10, work_id=WORK, title="T")
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
    log.add("owner_wait_seen", "observer", at=10, wait_id=WAIT_A, sampled_at=10, ref_state="pending")
    for error in ("bad_reply", "forbidden", "not_found", "timeout"):
        rounds = [
            round_for(10, [f"approval:{APPR}"]),
            round_for(20, [], [{"key": f"approval:{APPR}", "error": error}], round_id="ab12cd35"),
        ]
        doc = fold_one(log.events, 20, observer=rounds)
        item = doc["owner_all"][0]
        assert item["can_act"] == "unknown"
        assert item["reason"] == error
        assert item["ref_state"] == "pending"
        assert item["last_seen"] == {"ref_state": "pending", "at": 20}


def test_no_credential_is_unknown():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=10, work_id=WORK, title="T")
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
    rounds = [round_for(10, [], [{"key": f"approval:{APPR}", "error": "no_credential"}])]
    doc = fold_one(log.events, 10, observer=rounds)
    assert doc["owner_all"][0]["can_act"] == "unknown"
    assert doc["owner_all"][0]["reason"] == "no_credential"


def test_observer_stopped_181_seconds_is_unknown():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=10, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=R, name="发布", kind="release", who="C", watch="record", locator=LOCATOR)
    log.add("record_seen", "observer", step_id=R, sampled_at=10, found=True, uid="uid-1", started_at=9)
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
    log.add("owner_wait_seen", "observer", wait_id=WAIT_A, sampled_at=10, ref_state="pending")
    fresh = fold_one(log.events, 10, observer=[round_for(10, [f"step:{WORK}/{R}", f"approval:{APPR}"])])
    assert step_of(fresh)["state"] == "running"
    assert fresh["owner_all"][0]["can_act"] == "yes"
    stale = fold_one(log.events, 191, observer=[round_for(10, [f"step:{WORK}/{R}", f"approval:{APPR}"])])
    assert step_of(stale)["state"] == "unknown"
    assert step_of(stale)["reason"] == "not_confirmed"
    assert stale["owner_all"][0]["can_act"] == "unknown"


def test_append_failed_is_unknown_not_the_previous_can_act():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=10, work_id=WORK, title="T")
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
    log.add("owner_wait_seen", "observer", wait_id=WAIT_A, sampled_at=10, ref_state="pending")
    rounds = [round_for(20, [], [{"key": f"approval:{APPR}", "error": "append_failed"}])]
    doc = fold_one(log.events, 20, observer=rounds)
    assert doc["owner_all"][0]["can_act"] == "unknown"
    assert doc["owner_all"][0]["reason"] == "append_failed"


def test_same_approval_is_one_item_with_two_works_records_first():
    def one(work_id, declared_title):
        log = LogBuilder()
        log.add("work_opened", "coordinator", at=1, work_id=work_id, title=work_id)
        log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
        log.add("owner_wait_seen", "observer", wait_id=WAIT_A, sampled_at=5, ref_state="pending")
        log.add(
            "owner_wait_opened", "coordinator", wait_id=WAIT_D, title=declared_title,
            ref={"kind": "none", "id": "c0ffee01"}, can_act="yes",
        )
        return {"work_id": work_id, "events": log.events}
    doc = fold(
        [one("w1", "甲"), one("w2", "乙"), one("w3", "丙")],
        [round_for(6, [f"approval:{APPR}"])],
        6,
    )
    # w2 and w3 reuse the same declared wait id and the same none ref id.
    # Declared items are per wait_id and are not merged, but the same wait_id
    # in three logs is three items. The approval is one item.
    approval = [item for item in doc["owner_all"] if item["source"] == "record"]
    assert len(approval) == 1
    assert [piece["work_id"] for piece in approval[0]["works"]] == ["w1", "w2", "w3"]
    assert doc["owner_all"][0]["source"] == "record"


def test_later_sampled_at_wins_and_a_tie_is_unknown():
    def seen(work_id, sampled, state):
        log = LogBuilder()
        log.add("work_opened", "coordinator", at=1, work_id=work_id, title=work_id)
        log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
        log.add("owner_wait_seen", "observer", at=sampled, wait_id=WAIT_A, sampled_at=sampled, ref_state=state)
        return {"work_id": work_id, "events": log.events}
    later = fold(
        [seen("w1", 10, "approved"), seen("w2", 12, "pending")],
        [round_for(12, [f"approval:{APPR}"])],
        12,
    )
    assert later["owner_all"][0]["ref_state"] == "pending"
    assert later["owner_all"][0]["can_act"] == "yes"
    conflict = fold(
        [seen("w1", 10, "pending"), seen("w2", 10, "approved")],
        [round_for(10, [f"approval:{APPR}"])],
        10,
    )
    assert conflict["owner_all"][0]["can_act"] == "unknown"
    assert conflict["owner_all"][0]["reason"] == "conflicting_observations"
    assert conflict["ball"]["holder"] == "unknown"


def test_partial_terminal_drops_the_item_but_the_other_log_still_will_not_close(tmp_path):
    def specs(state):
        return [
            ("coordinator", 1, {"type": "work_opened", "work_id": "w1", "title": "w1"}),
            ("coordinator", 2, {"type": "owner_wait_opened", "wait_id": WAIT_A, "title": "请批", "ref": {"kind": "approval", "id": APPR}}),
            ("observer", 3, {"type": "owner_wait_seen", "wait_id": WAIT_A, "sampled_at": 3, "ref_state": state}),
        ]
    left = specs("executed")
    right = [
        ("coordinator", 1, {"type": "work_opened", "work_id": "w2", "title": "w2"}),
        ("coordinator", 2, {"type": "owner_wait_opened", "wait_id": WAIT_A, "title": "请批", "ref": {"kind": "approval", "id": APPR}}),
        ("observer", 3, {"type": "owner_wait_seen", "wait_id": WAIT_A, "sampled_at": 2, "ref_state": "pending"}),
    ]
    doc = fold(
        [
            {"work_id": "w1", "events": specs_as_events(left)},
            {"work_id": "w2", "events": specs_as_events(right)},
        ],
        [round_for(4, [f"approval:{APPR}"])],
        4,
    )
    assert doc["owner_all"] == []
    assert doc["ball"]["holder"] == "coordinator"
    assert doc["ball"]["holder"] != "owner"
    save_log(tmp_path / "w2", right)
    try:
        close_work(tmp_path, "w2", "stopped")
    except RecorderError as exc:
        assert exc.reason == "closed_with_open_items"
    else:
        raise AssertionError("close was accepted")


def test_two_declared_waits_with_the_same_title_stay_two_items():
    log = LogBuilder()
    log.add("work_opened", "coordinator", work_id=WORK, title="T")
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_D, title="同一句", ref={"kind": "none", "id": "c0ffee01"}, can_act="yes")
    log.add("owner_wait_opened", "coordinator", wait_id="b2b2b2b2", title="同一句", ref={"kind": "none", "id": "c0ffee02"}, can_act="not_yet")
    doc = fold_one(log.events, log.at)
    assert len(doc["owner_all"]) == 2
    assert {item["wait_id"] for item in doc["owner_all"]} == {WAIT_D, "b2b2b2b2"}


def test_a_declared_item_omits_advice_where_and_reply_when_they_were_not_written():
    log = LogBuilder()
    log.add("work_opened", "coordinator", work_id=WORK, title="T")
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_D, title="请看", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet")
    item = fold_one(log.events, log.at)["owner_all"][0]
    assert "advice" not in item
    assert "where" not in item
    assert "reply" not in item


def test_zero_byte_heartbeats_become_quiet_and_last_seen_is_the_raw_observation():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=0, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", at=0, step_id=P, name="实现", kind="other", who="C", watch="process")
    log.add("step_started", "wrapper", at=0, step_id=P, run_id=RUN, command="sleep")
    for at in range(60, 481, 60):
        log.add("step_seen", "wrapper", at=at, step_id=P, run_id=RUN, sampled_at=at, alive=True, output_bytes=0)
    doc = fold_one(log.events, 480)
    step = step_of(doc)
    assert step["state"] == "quiet"
    assert step["reason"] == "no_output"
    assert step["last_seen"] == {"alive": True, "output_bytes": 0, "at": 480}


def test_last_seen_is_not_the_previous_state():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    _process(log, at=2)
    log.add("step_seen", "wrapper", at=10, step_id=P, run_id=RUN, sampled_at=10, alive=True, output_bytes=5)
    log.add("step_seen", "wrapper", at=20, step_id=P, run_id=RUN, sampled_at=20, alive=True, output_bytes=9)
    step = step_of(fold_one(log.events, 20))
    assert step["last_seen"] == {"alive": True, "output_bytes": 9, "at": 20}


def test_a_gap_is_unknown_then_running_without_slow_and_is_not_a_usual_sample(tmp_path):
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=0, work_id=WORK, title="T")
    log.add(
        "step_declared", "coordinator", step_id=P, name="实现", kind="implement", who="C",
        watch="process", usual_s=10, usual_basis="declared",
    )
    log.add("step_started", "wrapper", at=0, step_id=P, run_id=RUN, command="sleep")
    log.add("step_seen", "wrapper", at=10, step_id=P, run_id=RUN, sampled_at=10, alive=True, output_bytes=1)
    during = fold_one(log.events, 10 + 3 * 3600 / 2)
    assert step_of(during)["state"] == "unknown"
    assert step_of(during)["reason"] == "no_observation"
    log.add("step_seen", "wrapper", at=10 + 3 * 3600, step_id=P, run_id=RUN, sampled_at=10 + 3 * 3600, alive=True, output_bytes=2)
    recovered = fold_one(log.events, 10 + 3 * 3600)
    step = step_of(recovered)
    assert step["state"] == "running"
    assert step["gap"] is True
    assert "overdue" not in step
    _write_clean(tmp_path, "c1", 10)
    _write_clean(tmp_path, "c2", 30)
    assert usual_for(tmp_path, "implement") is None
    save_log(tmp_path / "gapped", _finished_specs(0, 10 + 3 * 3600, heartbeats=(10, 10 + 3 * 3600)))
    assert usual_for(tmp_path, "implement") is None
    _write_clean(tmp_path, "c3", 50)
    seconds, basis = usual_for(tmp_path, "implement")
    assert basis == "measured"
    assert seconds == 30


def _finished_specs(start, end, heartbeats=()):
    specs = [
        ("coordinator", start, {"type": "work_opened", "work_id": "x", "title": "T"}),
        ("coordinator", start, {"type": "step_declared", "step_id": P, "name": "实现", "kind": "implement", "who": "C", "watch": "process"}),
        ("wrapper", start, {"type": "step_started", "step_id": P, "run_id": RUN, "command": "echo"}),
    ]
    previous = 0
    for at in heartbeats:
        previous += 1
        specs.append(("wrapper", at, {"type": "step_seen", "step_id": P, "run_id": RUN, "sampled_at": at, "alive": True, "output_bytes": previous}))
    specs.append(("wrapper", end, {"type": "step_finished", "step_id": P, "run_id": RUN, "exit": {"code": 0}}))
    return specs


def _write_clean(root, work_id, duration):
    specs = _finished_specs(0, duration)
    specs[0] = ("coordinator", 0, {"type": "work_opened", "work_id": work_id, "title": work_id})
    save_log(root / work_id, specs)


def test_a_heartbeat_inside_a_backwards_interval_and_one_outside_it():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1000, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", at=1010, step_id=P, name="inside", kind="other", who="C", watch="process")
    log.add("step_started", "wrapper", at=1020, step_id=P, run_id=RUN, command="echo in")
    log.add("step_seen", "wrapper", at=1100, step_id=P, run_id=RUN, sampled_at=1100, alive=True, output_bytes=1)
    log.add("step_declared", "coordinator", at=1110, step_id=N, name="outside", kind="other", who="C", watch="process")
    log.add("step_started", "wrapper", at=1120, step_id=N, run_id=RUN2, command="echo out")
    log.add("step_seen", "wrapper", at=1130, step_id=N, run_id=RUN2, sampled_at=1130, alive=True, output_bytes=1)
    # max_at is 1130. The note opens the interval. The next heartbeat is still
    # before that max, and its sampled_at does not go backwards.
    log.add("note", "coordinator", at=100, text="back")
    log.add("step_seen", "wrapper", at=1105, step_id=P, run_id=RUN, sampled_at=1105, alive=True, output_bytes=2)
    during = fold_one(log.events, 1130)
    inside = work_of(during)["steps"][0]
    outside = work_of(during)["steps"][1]
    assert inside["state"] == "unknown"
    assert inside["reason"] == "clock_backwards"
    assert outside["state"] == "running"
    log.add("step_seen", "wrapper", at=1130, step_id=P, run_id=RUN, sampled_at=1130, alive=True, output_bytes=3)
    recovered = fold_one(log.events, 1130)
    assert work_of(recovered)["steps"][0]["state"] == "running"


def test_review_76_process_clock_and_the_record_side():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=0, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", at=1, step_id=P, name="实现", kind="implement", who="Cursor", watch="process")
    log.add("step_started", "wrapper", at=300, step_id=P, run_id=RUN, command="echo")
    log.add("note", "coordinator", at=240, text="late")
    at_240 = fold_one(log.events, 240)
    assert step_of(at_240)["state"] == "unknown"
    assert step_of(at_240)["reason"] == "reader_clock_behind"
    assert step_of(at_240)["last_seen"] == {"started": True, "at": 300}
    at_440 = fold_one(log.events, 440)
    assert step_of(at_440)["state"] == "running"
    at_2240 = fold_one(log.events, 2240)
    assert step_of(at_2240)["state"] == "unknown"
    assert step_of(at_2240)["reason"] == "no_observation"
    record = LogBuilder()
    record.add("work_opened", "coordinator", at=0, work_id=WORK, title="T")
    record.add("step_declared", "coordinator", at=1, step_id=R, name="发布", kind="release", who="C", watch="record", locator=LOCATOR)
    record.add("record_seen", "observer", at=300, step_id=R, sampled_at=300, found=True, uid="uid-1", started_at=280)
    record.add("owner_wait_opened", "coordinator", at=1, wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
    record.add("owner_wait_seen", "observer", at=300, wait_id=WAIT_A, sampled_at=300, ref_state="pending")
    rounds = [round_for(300, [f"step:{WORK}/{R}", f"approval:{APPR}"])]
    behind = fold_one(record.events, 240, observer=rounds)
    assert step_of(behind)["state"] == "unknown"
    assert step_of(behind)["reason"] == "reader_clock_behind"
    assert behind["owner_all"][0]["can_act"] == "unknown"
    assert behind["owner_all"][0]["reason"] == "reader_clock_behind"
    fresh = fold_one(record.events, 440, observer=rounds)
    assert step_of(fresh)["state"] == "running"
    assert fresh["owner_all"][0]["can_act"] == "yes"
    stale = fold_one(record.events, 500, observer=rounds)
    assert step_of(stale)["state"] == "unknown"
    assert step_of(stale)["reason"] == "not_confirmed"
    assert stale["owner_all"][0]["reason"] == "not_confirmed"


def test_ball_rows_and_synthesis_each_carry_since():
    def bare():
        log = LogBuilder()
        log.add("work_opened", "coordinator", at=5, work_id=WORK, title="T")
        return log
    running = bare()
    _process(running, at=6)
    running.add("step_seen", "wrapper", step_id=P, run_id=RUN, sampled_at=running.at, alive=True, output_bytes=1)
    doc = fold_one(running.events, running.at)
    assert doc["ball"]["holder"] == "agents" and doc["ball"]["why"] == "step_running"
    assert doc["ball"]["since"] == running.at
    unknown = bare()
    unknown.add("step_declared", "coordinator", step_id=P, name="n", kind="other", who="C", watch="process")
    unknown.add("step_started", "wrapper", at=10, step_id=P, run_id=RUN, command="echo")
    doc = fold_one(unknown.events, 10 + 181)
    assert doc["ball"] == {"holder": "unknown", "why": "step_unknown", "since": 10}
    invalid = fold_one(running.events, running.at, invalid_at=2)
    assert invalid["ball"]["why"] == "log_invalid"
    assert "since" in invalid["ball"]
    waiting = bare()
    waiting.add("step_declared", "coordinator", at=7, step_id=N, name="next", kind="other", who="C", watch="none")
    doc = fold_one(waiting.events, 7)
    assert doc["ball"] == {"holder": "coordinator", "why": "next_not_sent", "since": 7}
    owner = bare()
    owner.add("owner_wait_opened", "coordinator", at=8, wait_id=WAIT_D, title="请看", ref={"kind": "none", "id": "c0ffee01"}, can_act="yes")
    doc = fold_one(owner.events, 8)
    assert doc["ball"]["holder"] == "owner" and doc["ball"]["why"] == "owner_can_act"
    assert doc["ball"]["basis"] == "declared"
    assert doc["ball"]["since"] == 8
    not_yet = bare()
    not_yet.add("owner_wait_opened", "coordinator", at=9, wait_id=WAIT_D, title="请看", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet")
    doc = fold_one(not_yet.events, 9)
    assert doc["ball"] == {"holder": "coordinator", "why": "owner_item_not_ready", "since": 9}
    ended = bare()
    ended.add("step_declared", "coordinator", step_id=N, name="n", kind="other", who="C", watch="none")
    ended.add("step_started", "coordinator", step_id=N, run_id=RUN)
    ended.add("step_finished", "coordinator", step_id=N, run_id=RUN, reported="finished")
    doc = fold_one(ended.events, ended.at)
    assert doc["ball"]["why"] == "ended_awaiting_check"
    assert doc["ball"]["holder"] == "coordinator"
    assert "since" in doc["ball"]
    unread = fold([{"work_id": WORK, "events": ended.events}], [], ended.at, logs_unread=1)
    assert unread["fold_complete"] is False
    assert unread["ball"]["holder"] == "unknown"
    assert unread["ball"]["why"] == "fold_incomplete"
    assert unread["ball"]["since"] == ended.at
    closed = bare()
    closed.add("work_closed", "coordinator", at=11, claim="stopped")
    doc = fold_one(closed.events, 11)
    assert doc["ball"] == {"holder": "nobody", "why": "queue_done", "since": 11}


def test_ended_unclosed_work_is_coordinator():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=N, name="n", kind="other", who="C", watch="none")
    log.add("step_started", "coordinator", step_id=N, run_id=RUN)
    log.add("step_finished", "coordinator", step_id=N, run_id=RUN, reported="finished")
    doc = fold_one(log.events, log.at)
    assert "closed_claim" not in work_of(doc)
    assert doc["ball"]["holder"] == "coordinator"


def test_owner_loses_to_a_coordinator_work():
    owner = LogBuilder()
    owner.add("work_opened", "coordinator", at=1, work_id="w1", title="w1")
    owner.add("owner_wait_opened", "coordinator", at=2, wait_id=WAIT_D, title="请看", ref={"kind": "none", "id": "c0ffee01"}, can_act="yes")
    coord = LogBuilder()
    coord.add("work_opened", "coordinator", at=1, work_id="w2", title="w2")
    coord.add("step_declared", "coordinator", at=3, step_id=N, name="next", kind="other", who="C", watch="none")
    doc = fold(
        [{"work_id": "w1", "events": owner.events}, {"work_id": "w2", "events": coord.events}],
        [],
        3,
    )
    assert doc["ball"]["holder"] == "coordinator"
    assert doc["ball"]["why"] == "next_not_sent"


def test_only_a_declared_wait_is_owner_with_basis():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=4, work_id=WORK, title="T")
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_D, title="请看", ref={"kind": "none", "id": "c0ffee01"}, can_act="yes")
    ball = fold_one(log.events, log.at)["ball"]
    assert ball["holder"] == "owner"
    assert ball["basis"] == "declared"


def test_snapshot_expired_is_unknown():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=10, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=R, name="发布", kind="release", who="C", watch="record", locator=LOCATOR)
    log.add("record_seen", "observer", step_id=R, sampled_at=10, found=True, uid="uid-1", started_at=9)
    fresh = fold_one(log.events, 10, observer=[round_for(10, [f"step:{WORK}/{R}"])])
    assert step_of(fresh)["state"] == "running"
    stale = fold_one(log.events, 10 + 181, observer=[round_for(10, [f"step:{WORK}/{R}"])])
    assert step_of(stale)["state"] == "unknown"
    assert step_of(stale)["reason"] == "not_confirmed"
    assert stale["ball"]["holder"] == "unknown"


def test_two_hundred_and_one_logs_are_incomplete():
    items = [(index, {"work_id": f"w{index}", "events": []}) for index in range(201)]
    kept, unread = select_logs(items, 200)
    assert unread == 1
    assert len(kept) == 200
    doc = fold([item[1] for item in kept], [], 1, logs_unread=unread)
    assert doc["fold_complete"] is False
    assert doc["logs_unread"] == 1
    assert doc["ball"]["holder"] == "unknown"
    assert doc["ball"]["why"] == "fold_incomplete"


def test_question_open_is_yes_and_answered_is_settled():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=5, work_id=WORK, title="T")
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="问", ref={"kind": "question", "id": QUESTION})
    log.add("owner_wait_seen", "observer", wait_id=WAIT_A, sampled_at=5, ref_state="open")
    doc = fold_one(log.events, 5, observer=[round_for(5, [f"question:{QUESTION}"])])
    assert doc["owner_all"][0]["can_act"] == "yes"
    log.add("owner_wait_seen", "observer", at=8, wait_id=WAIT_A, sampled_at=8, ref_state="answered")
    settled = fold_one(log.events, 8, observer=[round_for(8, [f"question:{QUESTION}"], round_id="ab12cd35")])
    assert settled["owner_all"] == []


def test_a_corrupt_middle_line_keeps_the_ended_step(tmp_path):
    specs = [
        ("coordinator", 1, {"type": "work_opened", "work_id": WORK, "title": "T"}),
        ("coordinator", 2, {"type": "step_declared", "step_id": P, "name": "done", "kind": "other", "who": "C", "watch": "none"}),
        ("coordinator", 3, {"type": "step_started", "step_id": P, "run_id": RUN}),
        ("coordinator", 4, {"type": "step_finished", "step_id": P, "run_id": RUN, "reported": "finished"}),
        ("coordinator", 5, {"type": "step_declared", "step_id": "b9b9b9b9", "name": "open", "kind": "other", "who": "C", "watch": "none"}),
        ("coordinator", 6, {"type": "step_started", "step_id": "b9b9b9b9", "run_id": "c9c9c9c9"}),
        ("coordinator", 7, {"type": "note", "text": "tail"}),
    ]
    directory = tmp_path / WORK
    save_log(directory, specs)
    path = directory / "events.jsonl"
    lines = path.read_bytes().split(b"\n")
    flipped = bytearray(lines[5])
    flipped[70] ^= 0x01
    lines[5] = bytes(flipped)
    path.write_bytes(b"\n".join(lines))
    loaded = load_file(path)
    doc = fold_one(loaded.events, 8, work_id=WORK, invalid_at=loaded.invalid_seq)
    work = doc["works"][0]
    assert work["log_invalid_at"] == loaded.invalid_seq
    by_name = {step["name"]: step for step in work["steps"]}
    assert by_name["done"]["state"] == "done"
    assert by_name["open"]["state"] == "unknown"
    assert by_name["open"]["reason"] == "log_invalid"
    try:
        append_sealed(path, {"type": "note", "v": 1, "seq": 99, "prev_sha256": "", "at": 9, "by": "coordinator", "text": "no"})
    except ValueError:
        pass
    else:
        raise AssertionError("append was accepted")


def test_a_closed_prefix_stays_closed_when_the_tail_breaks(tmp_path):
    specs = [
        ("coordinator", 1, {"type": "work_opened", "work_id": WORK, "title": "T"}),
        ("coordinator", 2, {"type": "work_closed", "claim": "stopped"}),
        ("coordinator", 3, {"type": "note", "text": "after"}),
    ]
    directory = tmp_path / WORK
    save_log(directory, specs)
    path = directory / "events.jsonl"
    lines = path.read_bytes().split(b"\n")
    bad = bytearray(lines[2])
    bad[80] ^= 0x01
    lines[2] = bytes(bad)
    path.write_bytes(b"\n".join(lines))
    loaded = load_file(path)
    doc = fold_one(loaded.events, 4, invalid_at=loaded.invalid_seq)
    assert doc["works"][0]["closed_claim"] == "stopped"


def test_log_full_is_on_the_work():
    doc = fold_one([], 1, full=True)
    assert doc["works"][0]["log_full"] is True


def test_two_processes_both_land_and_seq_is_continuous(tmp_path):
    open_work(tmp_path, WORK, "T")
    code = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from pathlib import Path\n"
        "from commands import write_note\n"
        "root, tag = Path(sys.argv[2]), sys.argv[3]\n"
        "for i in range(12):\n"
        "    write_note(root, 'w1', f'{tag}-{i}')\n"
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", code, str(HERE), str(tmp_path), tag])
        for tag in ("a", "b")
    ]
    codes = [proc.wait(timeout=30) for proc in procs]
    assert codes == [0, 0]
    log = load_file(tmp_path / WORK / "events.jsonl")
    assert log.invalid_seq is None
    assert [event["seq"] for event in log.events] == list(range(1, 26))
    texts = [event["text"] for event in log.events if event["type"] == "note"]
    assert len(texts) == 24
    assert len(set(texts)) == 24


def test_a_held_lock_refuses_the_second_writer(tmp_path):
    directory = tmp_path / WORK
    directory.mkdir()
    code = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from pathlib import Path\n"
        "from commands import open_work\n"
        "try:\n"
        "    open_work(Path(sys.argv[2]), 'w1', 'T')\n"
        "except Exception as exc:\n"
        "    sys.stderr.write(str(exc))\n"
        "    raise SystemExit(1)\n"
    )
    with hold(directory, "test-hold"):
        proc = subprocess.run(
            [sys.executable, "-c", code, str(HERE), str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=15,
        )
    assert proc.returncode != 0
    assert "lock busy" in proc.stderr
    assert not (directory / "events.jsonl").exists()


def test_declare_replaces_appends_the_declaration_before_the_supersede(tmp_path):
    open_work(tmp_path, WORK, "T")
    first = declare_step(tmp_path, WORK, name="old", kind="other", who="C", watch="none")
    second = declare_step(
        tmp_path, WORK, name="new", kind="other", who="C", watch="none", replaces=first["step_id"]
    )
    events = load_file(tmp_path / WORK / "events.jsonl").events
    assert events[-2]["type"] == "step_declared"
    assert events[-2]["step_id"] == second["step_id"]
    assert events[-1]["type"] == "step_superseded"
    assert events[-1]["step_id"] == first["step_id"]
    assert events[-1]["by_step"] == second["step_id"]
    doc = fold_one(events, events[-1]["at"])
    assert [step["step_id"] for step in doc["works"][0]["steps"]] == [second["step_id"]]
    assert doc["works"][0]["withdrawn"] == 1


def test_unstarted_superseded_step_is_withdrawn():
    log = LogBuilder()
    log.add("work_opened", "coordinator", work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=P, name="old", kind="other", who="C", watch="none")
    log.add("step_declared", "coordinator", step_id=N, name="new", kind="other", who="C", watch="none")
    log.add("step_superseded", "coordinator", step_id=P, by_step=N)
    doc = fold_one(log.events, log.at)
    assert [step["step_id"] for step in doc["works"][0]["steps"]] == [N]
    assert doc["works"][0]["withdrawn"] == 1
    record = LogBuilder()
    record.add("work_opened", "coordinator", work_id=WORK, title="T")
    record.add(
        "step_declared", "coordinator", step_id=R, name="rec", kind="release", who="C", watch="record",
        locator=LOCATOR,
    )
    record.add("step_declared", "coordinator", step_id=N, name="new", kind="other", who="C", watch="none")
    record.add("step_superseded", "coordinator", step_id=R, by_step=N)
    folded = fold_one(record.events, record.at)
    assert [step["step_id"] for step in folded["works"][0]["steps"]] == [N]
    assert folded["works"][0]["withdrawn"] == 1


def test_self_supersede_is_absent_and_the_work_stays_open():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", at=2, step_id=P, name="A", kind="other", who="C", watch="none")
    log.add("step_superseded", "coordinator", at=3, step_id=P, by_step=P)
    log.add("work_closed", "coordinator", at=4, claim="stopped")
    doc = fold_one(log.events, 4)
    reasons = [item["reason"] for item in doc["works"][0]["defects"]]
    assert "self_supersede" in reasons
    assert "closed_with_open_items" in reasons
    assert "closed_claim" not in doc["works"][0]
    assert doc["works"][0]["steps"][0]["state"] == "waiting"
    assert doc["works"][0]["steps"][0]["step_id"] == P
    assert doc["ball"]["holder"] == "coordinator"
    assert doc["ball"]["why"] == "next_not_sent"
