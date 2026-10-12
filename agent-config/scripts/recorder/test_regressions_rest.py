"""One named test for each regression in design section 7 item 3.

Logs here are synthetic. Nothing starts a process or reads a platform.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from commands import RecorderError, close_work, declare_step, open_work, owner_close
from events import append_sealed, load_file
from locks import hold
from estimate import usual_for
from fold import select_logs
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
    fold_items as fold,
    fold_one,
    round_for,
    save_log,
    step_of,
    work_of,
)
from validate import refusal
from test_regressions import _finished_specs, _write_clean

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
    assert doc["ball"]["since"] == 7
    unknown = bare()
    unknown.add("step_declared", "coordinator", step_id=P, name="n", kind="other", who="C", watch="process")
    unknown.add("step_started", "wrapper", at=10, step_id=P, run_id=RUN, command="echo")
    doc = fold_one(unknown.events, 10 + 181)
    assert doc["ball"] == {"holder": "unknown", "why": "step_unknown"}
    invalid = fold_one(running.events, running.at, invalid_at=2)
    assert invalid["ball"]["why"] == "log_invalid"
    assert "since" not in invalid["ball"]
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
    assert "since" not in unread["ball"]
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
    from read import fold_total
    doc = fold_total([(WORK, path.read_bytes())], [], 8)
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
    from read import fold_total
    doc = fold_total([(WORK, path.read_bytes())], [], 4)
    assert doc["works"][0]["closed_claim"] == "stopped"


def test_log_full_is_on_the_work():
    from model import MAX_EVENTS
    events = [{"type": "note", "at": 1, "by": "coordinator", "text": "n"} for _ in range(MAX_EVENTS)]
    doc = fold_one(events, 1)
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
    assert events[-1]["type"] == "step_declared"
    assert events[-1]["step_id"] == second["step_id"]
    assert events[-1]["replaces"] == first["step_id"]
    assert "by_step" not in events[-1]
    doc = fold_one(events, events[-1]["at"])
    assert [step["step_id"] for step in doc["works"][0]["steps"]] == [second["step_id"]]
    assert doc["works"][0]["withdrawn"] == 1


def test_unstarted_superseded_step_is_withdrawn():
    log = LogBuilder()
    log.add("work_opened", "coordinator", work_id=WORK, title="T")
    log.add("step_declared", "coordinator", step_id=P, name="old", kind="other", who="C", watch="none")
    log.add("step_declared", "coordinator", step_id=N, name="new", kind="other", who="C", watch="none", replaces=P)
    doc = fold_one(log.events, log.at)
    assert [step["step_id"] for step in doc["works"][0]["steps"]] == [N]
    assert doc["works"][0]["withdrawn"] == 1
    record = LogBuilder()
    record.add("work_opened", "coordinator", work_id=WORK, title="T")
    record.add(
        "step_declared", "coordinator", step_id=R, name="rec", kind="release", who="C", watch="record",
        locator=LOCATOR,
    )
    record.add("step_declared", "coordinator", step_id=N, name="new", kind="other", who="C", watch="none", replaces=R)
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
    assert "unknown_field" in reasons
    assert "self_supersede" not in reasons
    assert "closed_with_open_items" in reasons
    assert "closed_claim" not in doc["works"][0]
    assert doc["works"][0]["steps"][0]["state"] == "waiting"
    assert doc["works"][0]["steps"][0]["step_id"] == P
    assert doc["ball"]["holder"] == "coordinator"
    assert doc["ball"]["why"] == "next_not_sent"


def test_the_last_appended_round_wins_even_when_its_clock_is_earlier():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
    log.add("owner_wait_seen", "observer", at=90, wait_id=WAIT_A, sampled_at=90, ref_state="pending")
    rounds = [
        round_for(200, [f"approval:{APPR}"]),
        round_for(100, [], [{"key": f"approval:{APPR}", "error": "timeout"}], round_id="ab12cd35"),
    ]
    doc = fold_one(log.events, 200, observer=rounds)
    assert doc["owner_all"][0]["can_act"] != "yes"
    assert doc["owner_all"][0]["reason"] == "timeout"


def test_last_seen_at_is_the_last_successful_confirmation():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add(
        "step_declared", "coordinator", step_id=R, name="发布", kind="release", who="C",
        watch="record", locator=LOCATOR,
    )
    log.add("record_seen", "observer", at=90, step_id=R, sampled_at=90, found=True, uid="uid-1", started_at=80)
    log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
    log.add("owner_wait_seen", "observer", at=90, wait_id=WAIT_A, sampled_at=90, ref_state="pending")
    key_step = f"step:{WORK}/{R}"
    key_approval = f"approval:{APPR}"
    rounds = [
        round_for(100, [key_step, key_approval]),
        round_for(
            150, [],
            [{"key": key_step, "error": "timeout"}, {"key": key_approval, "error": "timeout"}],
            round_id="ab12cd35",
        ),
    ]
    doc = fold_one(log.events, 150, observer=rounds)
    assert step_of(doc)["last_seen"]["at"] == 100
    assert doc["owner_all"][0]["last_seen"]["at"] == 100
    never = [
        round_for(
            150, [],
            [{"key": key_step, "error": "timeout"}, {"key": key_approval, "error": "timeout"}],
        ),
    ]
    missed = fold_one(log.events, 150, observer=never)
    assert step_of(missed)["last_seen"]["at"] == 90
    assert missed["owner_all"][0]["last_seen"]["at"] == 90


def test_an_exact_tie_with_different_deadlines_is_unknown():
    def one(work_id, deadline):
        log = LogBuilder()
        log.add("work_opened", "coordinator", at=1, work_id=work_id, title=work_id)
        log.add("owner_wait_opened", "coordinator", wait_id=WAIT_A, title="请批", ref={"kind": "approval", "id": APPR})
        log.add(
            "owner_wait_seen", "observer", at=10, wait_id=WAIT_A, sampled_at=10,
            ref_state="pending", expires_at=deadline,
        )
        return {"work_id": work_id, "events": log.events}

    rounds = [round_for(10, [f"approval:{APPR}"])]
    forward = fold([one("w1", 100), one("w2", 200)], rounds, 10)
    backward = fold([one("w2", 200), one("w1", 100)], rounds, 10)
    assert forward["owner_all"][0]["reason"] == "conflicting_observations"
    assert forward["owner_all"][0]["can_act"] == "unknown"
    assert json.dumps(forward, ensure_ascii=False) == json.dumps(backward, ensure_ascii=False)


def test_permuting_logs_does_not_change_the_document():
    def one(work_id, at, text):
        log = LogBuilder()
        log.add("work_opened", "coordinator", at=at, work_id=work_id, title=work_id)
        log.add("note", "coordinator", at=at + 1, text=text)
        return {"work_id": work_id, "events": log.events}

    left = [one("w2", 5, "later"), one("w1", 1, "earlier")]
    right = [one("w1", 1, "earlier"), one("w2", 5, "later")]
    assert json.dumps(fold(left, [], 6), ensure_ascii=False) == json.dumps(fold(right, [], 6), ensure_ascii=False)
    assert [work["work_id"] for work in fold(left, [], 6)["works"]] == ["w1", "w2"]


def test_a_finish_in_a_backwards_interval_is_not_a_sample(tmp_path):
    _write_clean(tmp_path, "c1", 10)
    _write_clean(tmp_path, "c2", 20)
    back = _finished_specs(100, 90)
    back[0] = ("coordinator", 100, {"type": "work_opened", "work_id": "back", "title": "back"})
    save_log(tmp_path / "back", back)
    assert usual_for(tmp_path, "implement") is None
    barely = _finished_specs(100, 99)
    barely[0] = ("coordinator", 100, {"type": "work_opened", "work_id": "barely", "title": "barely"})
    save_log(tmp_path / "barely", barely)
    assert usual_for(tmp_path, "implement") is None


def test_a_record_step_takes_the_handwritten_usual(tmp_path):
    events = tmp_path / "events"
    events.mkdir()
    status = tmp_path / "status"
    status.mkdir()
    (status / "tasks.json").write_text(json.dumps({
        "works": [{"steps": [
            {"kind": "release", "usual_min": 5},
            {"kind": "implement", "usual_min": 9},
        ]}],
    }), encoding="utf-8")
    for index, duration in enumerate((10, 20, 30)):
        _write_clean(events, f"c{index}", duration)
    assert usual_for(events, "implement")[1] == "measured"
    assert usual_for(events, "implement", measured=False) == (540.0, "declared")
    open_work(events, WORK, "T")
    declared = declare_step(
        events, WORK, name="发布", kind="release", who="C", watch="record", locator=LOCATOR,
    )
    assert declared["usual_s"] == 300
    assert declared["usual_basis"] == "declared"


def test_a_note_does_not_move_ball_since():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    opened = fold_one(log.events, 1)
    log.add("note", "coordinator", at=100, text="later")
    noted = fold_one(log.events, 100)
    assert opened["ball"] == {"holder": "coordinator", "why": "ended_awaiting_check", "since": 1}
    assert noted["ball"] == opened["ball"]


def test_feed_is_ordered_across_works_by_time():
    def one(work_id, at, text):
        log = LogBuilder()
        log.add("work_opened", "coordinator", at=1, work_id=work_id, title=work_id)
        log.add("note", "coordinator", at=at, text=text)
        return {"work_id": work_id, "events": log.events}

    doc = fold([one("w2", 10, "second"), one("w1", 5, "first")], [], 10)
    assert [(row["at"], row["work"]) for row in doc["feed"]] == [(5, "w1"), (10, "w2")]
