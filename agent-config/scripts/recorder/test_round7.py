"""Rules the round-6 survivors sit on.

One function loops the cases so the mutant run stays a single test. Each
assertion names the design rule: table A validity, the step and wait
reductions, the publish shape limits, table B's kept markers, and the
number tokens of section 12.2.
"""

from __future__ import annotations

import json

P = "a1b2c3d4"
N = "c1b2c3d4"
M = "d4c3b2a1"
R = "b1b2c3d4"
RUN = "d1b2c3d4"
WAIT = "f1b2c3d4"
WAIT2 = "a2b2c3d4"
APPR = "appr_0123456789abcdef"
APPR2 = "appr_fedcba9876543210"
QUESTION = "q_0123456789abcdef"
WORK = "w1"
LOC = {"cluster": "prod", "namespace": "cicd", "name": "run-1"}
SHA = "ab" * 32


def _need(cond, detail):
    if not cond:
        raise AssertionError(detail)


def _ev(typ, by="coordinator", **fields):
    event = {"type": typ, "v": 2, "at": 1, "by": by}
    event.update(fields)
    return event


def _parse(event):
    from validate import parse_event
    return parse_event(event)[1]


def _chain(rows):
    out = []
    for index, (typ, by, fields) in enumerate(rows, 1):
        event = {"type": typ, "v": 2, "seq": index, "at": index, "by": by, "prev_sha256": ""}
        event.update(fields)
        out.append(event)
    return out


def _reasons(rows, work_id=WORK):
    from validate import classify
    view = classify(_chain(rows), work_id=work_id)
    return [item["reason"] for item in view.defects], view


def _field_rules():
    """Section 12.2 rows 8–10 and the closed field lists: one bad value, one reason."""
    step = dict(step_id=P, name="n", kind="other", who="C", watch="none")
    cases = [
        (_ev("work_opened", work_id=WORK, title="T"), None),
        (_ev("work_opened", work_id=1, title="T"), "bad_value"),
        (_ev("work_opened", work_id="", title="T"), "bad_value"),
        (_ev("work_opened", work_id="w 1", title="T"), "bad_value"),
        (_ev("work_opened", work_id=WORK, title=1), "bad_type"),
        (_ev("work_opened", work_id=WORK, title="T", goal=1), "bad_type"),
        (_ev("work_closed", claim="landed"), None),
        (_ev("work_closed", claim="nope"), "bad_value"),
        (_ev("work_closed", claim=1), "bad_type"),
        (_ev("step_declared", **step), None),
        (_ev("step_declared", **dict(step, step_id="ZZZZZZZZ")), "bad_value"),
        (_ev("step_declared", **dict(step, step_id=1)), "bad_value"),
        (_ev("step_declared", **dict(step, kind="nope")), "bad_value"),
        (_ev("step_declared", **dict(step, kind=1)), "bad_type"),
        (_ev("step_declared", **dict(step, watch="nope")), "bad_value"),
        (_ev("step_declared", **dict(step, usual_s=-1, usual_basis="declared")), "bad_value"),
        (_ev("step_declared", **dict(step, usual_s=0, usual_basis="declared")), None),
        (_ev("step_declared", **dict(step, usual_s=True, usual_basis="declared")), "bad_value"),
        (_ev("step_declared", **dict(step, usual_s="x", usual_basis="declared")), "bad_value"),
        (_ev("step_declared", **dict(step, usual_basis="nope")), "bad_value"),
        (_ev("step_declared", **dict(step, usual_basis=1)), "bad_type"),
        (_ev("step_declared", **dict(step, round="x")), "bad_type"),
        (_ev("step_declared", **dict(step, round=1)), None),
        (_ev("step_declared", **dict(step, after=1)), "bad_type"),
        (_ev("step_declared", **dict(step, after="zzzzzzzz")), "bad_value"),
        (_ev("step_declared", **dict(step, after=N)), None),
        (_ev("step_declared", **dict(step, waiting_on="x")), "bad_type"),
        (_ev("step_declared", **dict(step, waiting_on=["zz"])), "bad_value"),
        (_ev("step_declared", **dict(step, waiting_on=[WAIT, WAIT])), "bad_value"),
        (_ev("step_declared", **dict(step, waiting_on=[WAIT])), None),
        (_ev("step_declared", **dict(step, locator="x")), "bad_type"),
        (_ev("step_declared", **dict(step, kind="release", watch="record", locator={})), "missing_field"),
        (_ev("step_declared", **dict(step, kind="release", watch="record", locator=LOC)), None),
        (_ev("step_declared", **dict(step, kind="release", watch="record", locator={**LOC, "extra": 1})), "bad_value"),
        (_ev("step_declared", **dict(step, replaces="zz")), "bad_value"),
        (_ev("step_declared", **dict(step, replaces=1)), "bad_value"),
        (_ev("step_declared", **dict(step, replaces=N)), None),
        (_ev("step_declared", **dict(step, replaces_text="t")), "bad_value"),
        (_ev("step_declared", **dict(step, replaces=N, replaces_text=1)), "bad_type"),
        (_ev("step_superseded", step_id=P), None),
        (_ev("step_superseded", step_id="zz"), "bad_value"),
        (_ev("step_superseded", step_id=P, text=1), "bad_type"),
        (_ev("step_started", step_id=P, run_id=RUN), None),
        (_ev("step_started", step_id="zz", run_id=RUN), "bad_value"),
        (_ev("step_started", step_id=P, run_id=RUN, command=1), "bad_type"),
        (_ev("step_started", step_id=P, run_id=RUN, pid=True), "bad_type"),
        (_ev("step_started", step_id=P, run_id=RUN, pid=1), None),
        (_ev("step_seen", step_id=P, run_id=RUN, sampled_at=1, alive=True), None),
        (_ev("step_seen", step_id=P, run_id=RUN, sampled_at="x", alive=True), "bad_type"),
        (_ev("step_seen", step_id=P, run_id=RUN, sampled_at=1, alive=1), "bad_type"),
        (_ev("step_seen", step_id=P, run_id=RUN, sampled_at=1, alive=True, output_bytes=-1), "bad_value"),
        (_ev("step_seen", step_id=P, run_id=RUN, sampled_at=1, alive=True, output_bytes=0), None),
        (_ev("step_seen", step_id=P, run_id=RUN, sampled_at=1, alive=True, output_bytes=True), "bad_value"),
        (_ev("step_seen", step_id=P, run_id=RUN, sampled_at=1, alive=True, text=1), "bad_type"),
        (_ev("step_finished", step_id=P, run_id=RUN, exit={"code": 0}), None),
        (_ev("step_finished", step_id=P, run_id=RUN, reported="nope"), "bad_value"),
        (_ev("step_finished", step_id=P, run_id=RUN, reported="finished"), None),
        (_ev("step_finished", step_id=P, run_id=RUN, quote=1), "bad_type"),
        (_ev("record_seen", step_id=P, sampled_at=1, found=True, uid="u"), None),
        (_ev("record_seen", step_id="zz", sampled_at=1, found=False), "bad_value"),
        (_ev("record_seen", step_id=P, sampled_at="x", found=False), "bad_type"),
        (_ev("record_seen", step_id=P, sampled_at=1, found="x"), "bad_type"),
        (_ev("record_seen", step_id=P, sampled_at=1, found=True, uid=1), "bad_type"),
        (_ev("record_seen", step_id=P, sampled_at=1, found=True, uid="u" * 81), "limit_text"),
        (_ev("record_seen", step_id=P, sampled_at=1, found=False, started_at="x"), "bad_type"),
        (_ev("record_seen", step_id=P, sampled_at=1, found=True, uid="u", condition="nope"), "bad_value"),
        (_ev("record_seen", step_id=P, sampled_at=1, found=True, uid="u", condition="True"), None),
        (_ev("record_seen", step_id=P, sampled_at=1, found=True, uid="u", reason_quote=1), "bad_type"),
        (_ev("owner_wait_opened", wait_id=WAIT, title="W", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet"), None),
        (_ev("owner_wait_opened", wait_id="zz", title="W", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet"), "bad_value"),
        (_ev("owner_wait_opened", wait_id=WAIT, title=1, ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet"), "bad_type"),
        (_ev("owner_wait_opened", wait_id=WAIT, title="W", ref={"kind": "none", "id": "c0ffee01"}, can_act="nope"), "bad_value"),
        (_ev("owner_wait_opened", wait_id=WAIT, title="W", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet", where="nope"), "bad_value"),
        (_ev("owner_wait_opened", wait_id=WAIT, title="W", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet", after="zz"), "bad_value"),
        (_ev("owner_wait_opened", wait_id=WAIT, title="W", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet", deadline="x"), "bad_type"),
        (_ev("owner_wait_opened", wait_id=WAIT, title="W", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet", no_deadline=False), "bad_value"),
        (_ev("owner_wait_opened", wait_id=WAIT, title="W", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet", no_deadline=True), None),
        (_ev("owner_wait_opened", wait_id=WAIT, title="W", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet", blocks_nothing=False), "bad_value"),
        (_ev("owner_wait_opened", wait_id=WAIT, title="W", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet", blocks_nothing=True), None),
        (_ev("owner_wait_opened", wait_id=WAIT, title="W", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet", reply_needed=True), "bad_value"),
        (_ev("owner_wait_opened", wait_id=WAIT, title="W", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet", reply_needed=False), None),
        (_ev("owner_wait_opened", wait_id=WAIT, title="W", ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet", commands="echo"), "bad_type"),
        (_ev("owner_wait_opened", wait_id=WAIT, title="W", ref={"kind": "approval", "id": APPR}), None),
        (_ev("owner_wait_seen", wait_id=WAIT, sampled_at=1, ref_state="pending"), None),
        (_ev("owner_wait_seen", wait_id="zz", sampled_at=1, ref_state="pending"), "bad_value"),
        (_ev("owner_wait_seen", wait_id=WAIT, sampled_at="x", ref_state="pending"), "bad_type"),
        (_ev("owner_wait_seen", wait_id=WAIT, sampled_at=1, ref_state=1), "bad_type"),
        (_ev("owner_wait_seen", wait_id=WAIT, sampled_at=1, ref_state="p" * 81), "limit_text"),
        (_ev("owner_wait_seen", wait_id=WAIT, sampled_at=1, ref_state="pending", expires_at="x"), "bad_type"),
        (_ev("owner_wait_seen", wait_id=WAIT, sampled_at=1, ref_state="pending", number=1.5), "bad_type"),
        (_ev("owner_wait_seen", wait_id=WAIT, sampled_at=1, ref_state="pending", number=1), None),
        (_ev("owner_wait_ready", wait_id=WAIT), None),
        (_ev("owner_wait_ready", wait_id="zz"), "bad_value"),
        (_ev("owner_wait_closed", wait_id=WAIT, how="done"), None),
        (_ev("owner_wait_closed", wait_id=WAIT, how="nope"), "bad_value"),
        (_ev("owner_wait_closed", wait_id="zz", how="done"), "bad_value"),
        (_ev("note", text="n"), None),
        (_ev("note", text=1), "bad_type"),
        (_ev("note", text="n", step_id="zz"), "bad_value"),
        (_ev("note", text="n", step_id=P), None),
        (_ev("observer_round", by="observer", round_id=P, started_at=1, ended_at=1, confirmed=[], failed=[]), None),
        (_ev("observer_round", by="observer", round_id="zz", started_at=1, ended_at=1, confirmed=[], failed=[]), "bad_value"),
        (_ev("observer_round", by="observer", round_id=P, started_at="x", ended_at=1, confirmed=[], failed=[]), "bad_type"),
        (_ev("observer_round", by="observer", round_id=P, started_at=1, ended_at=1, confirmed="x", failed=[]), "bad_type"),
        (_ev("observer_round", by="observer", round_id=P, started_at=1, ended_at=1, confirmed=[], failed=[], truncated=False), "bad_value"),
        (_ev("observer_round", by="observer", round_id=P, started_at=1, ended_at=1, confirmed=[], failed=[], truncated=True), None),
        (_ev("tail_repaired", repair_id="r", bytes=0, sha256=SHA), None),
        (_ev("tail_repaired", repair_id=1, bytes=0, sha256=SHA), "bad_value"),
        (_ev("tail_repaired", repair_id="r", bytes=-1, sha256=SHA), "bad_value"),
        (_ev("tail_repaired", repair_id="r", bytes=True, sha256=SHA), "bad_value"),
        (_ev("tail_repaired", repair_id="r", bytes=0, sha256="ab"), "bad_value"),
        (_ev("tail_repaired", repair_id="r", bytes=0, sha256=1), "bad_value"),
        (_ev("nope"), "unknown_type"),
        (["nope"], "bad_type"),
    ]
    for event, reason in cases:
        got = _parse(event)
        _need(got == reason, ("field", event.get("type") if isinstance(event, dict) else type(event), reason, got))


def _shape_and_ref_and_exit():
    from validate import _exit, _ref, _shape
    _need(_shape([]) == "bad_type", "a non-dict event is bad_type before any field lookup")
    _need(_shape({"type": 1, "v": 2, "at": 1, "by": "coordinator"}) == "unknown_type", "type must be a string from the schema")
    _need(_ref([]) == "bad_type", "ref")
    _need(_ref({}) == "missing_field", "ref needs kind and id")
    _need(_ref({"kind": "none"}) == "missing_field", "ref id")
    _need(_ref({"kind": "none", "id": "c", "extra": 1}) == "unknown_field", "ref extra")
    _need(_ref({"kind": 1, "id": "c"}) == "bad_type", "ref kind type")
    _need(_ref({"kind": "nope", "id": "c"}) == "bad_value", "ref kind")
    _need(_ref({"kind": "approval", "id": "appr_short"}) == "ref_format", "approval id")
    _need(_ref({"kind": "question", "id": "q_short"}) == "ref_format", "question id")
    _need(_ref({"kind": "approval", "id": APPR}) is None, "approval id ok")
    _need(_ref({"kind": "question", "id": QUESTION}) is None, "question id ok")
    _need(_ref({"kind": "none", "id": "c0ffee01"}) is None, "declared id")
    _need(_exit([]) == "bad_type", "exit")
    _need(_exit({"code": 0, "extra": 1}) == "unknown_field", "exit extra")
    _need(_exit({"code": None}) == "bad_type", "null code")
    _need(_exit({"signal": None}) == "bad_type", "null signal")
    _need(_exit({}) == "bad_exit", "exit needs exactly one")
    _need(_exit({"code": 0, "signal": "TERM"}) == "bad_exit", "exit is exclusive")
    _need(_exit({"code": 0, "signal": ""}) is None, "empty signal is absent")
    _need(_exit({"code": True}) == "bad_type", "bool is not an exit code")
    _need(_exit({"signal": "x" * 81}) == "bad_value", "signal length")
    _need(_exit({"code": 0}) is None, "exit 0")
    _need(_exit({"signal": "TERM"}) is None, "signal")


def _context_rules():
    """Table A: an event that fails is absent, and the reason is the row's code."""
    opened = ("work_opened", "coordinator", {"work_id": WORK, "title": "T"})
    declare = ("step_declared", "coordinator", {"step_id": P, "name": "n", "kind": "other", "who": "C", "watch": "none"})
    proc = ("step_declared", "coordinator", {"step_id": P, "name": "n", "kind": "other", "who": "C", "watch": "process"})
    rec = ("step_declared", "coordinator", {"step_id": R, "name": "r", "kind": "release", "who": "C", "watch": "record", "locator": LOC})
    start = ("step_started", "wrapper", {"step_id": P, "run_id": RUN, "command": "echo"})
    none_start = ("step_started", "coordinator", {"step_id": P, "run_id": RUN})
    finish = ("step_finished", "wrapper", {"step_id": P, "run_id": RUN, "exit": {"code": 0}})
    none_wait = ("owner_wait_opened", "coordinator", {"wait_id": WAIT, "title": "W", "ref": {"kind": "none", "id": "c0ffee01"}, "can_act": "not_yet"})
    appr = ("owner_wait_opened", "coordinator", {"wait_id": WAIT, "title": "W", "ref": {"kind": "approval", "id": APPR}})
    cases = [
        ([opened, ("work_closed", "coordinator", {"claim": "landed"}), ("work_closed", "coordinator", {"claim": "stopped"})], ["already_closed"]),
        ([opened, ("work_closed", "coordinator", {"claim": "landed"}), ("note", "coordinator", {"text": "n"})], []),
        ([opened, ("work_closed", "coordinator", {"claim": "landed"}), ("tail_repaired", "coordinator", {"repair_id": "r", "bytes": 1, "sha256": SHA})], []),
        ([opened, ("work_closed", "coordinator", {"claim": "landed"}), declare], ["after_close"]),
        ([("note", "coordinator", {"text": "n"}), opened], ["not_first"]),
        ([("work_opened", "coordinator", {"work_id": "other", "title": "T"})], ["work_id_mismatch"]),
        ([opened, declare, ("work_closed", "coordinator", {"claim": "landed"})], ["closed_with_open_items"]),
        ([opened, declare, ("step_declared", "coordinator", {"step_id": P, "name": "m", "kind": "other", "who": "C", "watch": "none"})], ["step_exists"]),
        ([opened, ("step_declared", "coordinator", {"step_id": P, "name": "n", "kind": "release", "who": "C", "watch": "process"})], ["kind_watch"]),
        ([opened, ("step_declared", "coordinator", {"step_id": P, "name": "n", "kind": "other", "who": "C", "watch": "process", "waiting_on": [WAIT]})], ["process_waiting_on"]),
        ([opened, ("step_declared", "coordinator", {"step_id": R, "name": "r", "kind": "release", "who": "C", "watch": "record"})], ["needs_locator"]),
        ([opened, ("step_declared", "coordinator", {**declare[2], "after": M})], ["unknown_id"]),
        ([opened, ("step_declared", "coordinator", {"step_id": P, "name": "n", "kind": "other", "who": "C", "watch": "none", "waiting_on": [WAIT]})], ["unknown_id"]),
        ([opened, ("step_declared", "coordinator", {**declare[2], "usual_s": 10})], ["bad_value"]),
        ([opened, ("step_declared", "coordinator", {**declare[2], "usual_basis": "declared"})], ["bad_value"]),
        ([opened, ("step_declared", "coordinator", {**declare[2], "replaces": M})], ["unknown_id"]),
        ([opened, declare, ("step_declared", "coordinator", {"step_id": N, "name": "n", "kind": "other", "who": "C", "watch": "none", "replaces": P}), ("step_declared", "coordinator", {"step_id": M, "name": "m", "kind": "other", "who": "C", "watch": "none", "replaces": P})], ["superseded"]),
        ([opened, ("step_superseded", "coordinator", {"step_id": P})], ["unknown_id"]),
        ([opened, declare, ("step_superseded", "coordinator", {"step_id": P}), ("step_superseded", "coordinator", {"step_id": P})], ["superseded"]),
        ([opened, proc, start, ("step_superseded", "coordinator", {"step_id": P})], ["withdraw_started"]),
        ([opened, rec, ("record_seen", "observer", {"step_id": R, "sampled_at": 3, "found": True, "uid": "u"}), ("step_superseded", "coordinator", {"step_id": R})], ["withdraw_started"]),
        ([opened, ("step_started", "wrapper", {"step_id": P, "run_id": RUN, "command": "echo"})], ["not_declared"]),
        ([opened, declare, ("step_declared", "coordinator", {"step_id": N, "name": "n", "kind": "other", "who": "C", "watch": "none", "replaces": P}), ("step_started", "coordinator", {"step_id": P, "run_id": RUN})], ["superseded"]),
        ([opened, declare, none_start, none_start], ["already_started"]),
        ([opened, proc, ("note", "coordinator", {"text": "gap"}), start], ["late_start"]),
        ([opened, none_wait, ("step_declared", "coordinator", {"step_id": P, "name": "n", "kind": "other", "who": "C", "watch": "none", "waiting_on": [WAIT]}), ("step_started", "coordinator", {"step_id": P, "run_id": RUN})], ["waits_open"]),
        ([opened, rec, ("step_started", "wrapper", {"step_id": R, "run_id": RUN, "command": "echo"})], ["watch_mismatch"]),
        ([opened, proc, ("step_started", "coordinator", {"step_id": P, "run_id": RUN, "command": "echo"})], ["by_mismatch"]),
        ([opened, proc, ("step_started", "wrapper", {"step_id": P, "run_id": RUN})], ["missing_field"]),
        ([opened, declare, ("step_started", "coordinator", {"step_id": P, "run_id": RUN, "command": "echo"})], ["bad_value"]),
        ([opened, proc, ("step_seen", "wrapper", {"step_id": P, "run_id": RUN, "sampled_at": 3, "alive": True})], ["not_started"]),
        ([opened, declare, ("step_seen", "wrapper", {"step_id": P, "run_id": RUN, "sampled_at": 3, "alive": True})], ["watch_mismatch"]),
        ([opened, proc, start, ("step_seen", "wrapper", {"step_id": P, "run_id": M, "sampled_at": 4, "alive": True})], ["run_mismatch"]),
        ([opened, proc, start, finish, ("step_seen", "wrapper", {"step_id": P, "run_id": RUN, "sampled_at": 5, "alive": True})], ["already_ended"]),
        ([opened, proc, start, ("step_seen", "observer", {"step_id": P, "run_id": RUN, "sampled_at": 4, "alive": False}), ("step_seen", "observer", {"step_id": P, "run_id": RUN, "sampled_at": 5, "alive": False})], ["already_dead"]),
        ([opened, proc, start, ("step_seen", "wrapper", {"step_id": P, "run_id": RUN, "sampled_at": 4, "alive": True, "output_bytes": 10}), ("step_seen", "wrapper", {"step_id": P, "run_id": RUN, "sampled_at": 5, "alive": True, "output_bytes": 9})], ["output_shrunk"]),
        ([opened, proc, start, ("step_seen", "wrapper", {"step_id": P, "run_id": RUN, "sampled_at": 40, "alive": True})], ["sampled_at"]),
        ([opened, proc, start, ("step_seen", "observer", {"step_id": P, "run_id": RUN, "sampled_at": 4, "alive": True})], ["by_mismatch"]),
        ([opened, proc, start, ("step_seen", "wrapper", {"step_id": P, "run_id": RUN, "sampled_at": 4, "alive": False})], ["by_mismatch"]),
        ([opened, ("step_finished", "wrapper", {"step_id": P, "run_id": RUN, "exit": {"code": 0}})], ["not_declared"]),
        ([opened, rec, ("step_finished", "wrapper", {"step_id": R, "run_id": RUN, "exit": {"code": 0}})], ["watch_mismatch"]),
        ([opened, proc, finish], ["not_started"]),
        ([opened, proc, start, ("step_finished", "wrapper", {"step_id": P, "run_id": M, "exit": {"code": 0}})], ["run_mismatch"]),
        ([opened, proc, start, finish, finish], ["already_ended"]),
        ([opened, proc, start, ("step_finished", "coordinator", {"step_id": P, "run_id": RUN, "exit": {"code": 0}})], ["by_mismatch"]),
        ([opened, proc, start, ("step_finished", "wrapper", {"step_id": P, "run_id": RUN})], ["bad_exit"]),
        ([opened, proc, start, ("step_finished", "wrapper", {"step_id": P, "run_id": RUN, "exit": {"code": 0}, "reported": "finished"})], ["bad_exit"]),
        ([opened, declare, none_start, ("step_finished", "coordinator", {"step_id": P, "run_id": RUN})], ["bad_exit"]),
        ([opened, declare, none_start, ("step_finished", "coordinator", {"step_id": P, "run_id": RUN, "reported": "finished", "exit": {"code": 0}})], ["bad_exit"]),
        ([opened, ("record_seen", "observer", {"step_id": R, "sampled_at": 2, "found": False})], ["not_declared"]),
        ([opened, proc, start, ("record_seen", "observer", {"step_id": P, "sampled_at": 4, "found": False})], ["watch_mismatch"]),
        ([opened, rec, ("record_seen", "observer", {"step_id": R, "sampled_at": 3, "found": True, "uid": "u", "condition": "True"}), ("record_seen", "observer", {"step_id": R, "sampled_at": 4, "found": True, "uid": "u", "condition": "True"})], ["already_ended"]),
        ([opened, rec, ("step_superseded", "coordinator", {"step_id": R}), ("record_seen", "observer", {"step_id": R, "sampled_at": 4, "found": True, "uid": "u"})], ["never_found"]),
        ([opened, rec, ("record_seen", "coordinator", {"step_id": R, "sampled_at": 3, "found": False})], ["by_mismatch"]),
        ([opened, rec, ("record_seen", "observer", {"step_id": R, "sampled_at": 3, "found": True})], ["missing_field"]),
        ([opened, rec, ("record_seen", "observer", {"step_id": R, "sampled_at": 3, "found": True, "uid": "u"}), ("record_seen", "observer", {"step_id": R, "sampled_at": 4, "found": True, "uid": "v"})], ["uid_changed"]),
        ([opened, rec, ("record_seen", "observer", {"step_id": R, "sampled_at": 3, "found": False, "uid": "u"})], ["bad_value"]),
        ([opened, rec, ("record_seen", "observer", {"step_id": R, "sampled_at": 3, "found": False, "condition": "True"})], ["bad_value"]),
        ([opened, rec, ("record_seen", "observer", {"step_id": R, "sampled_at": 3, "found": False, "started_at": 1})], ["bad_value"]),
        ([opened, rec, ("record_seen", "observer", {"step_id": R, "sampled_at": 3, "found": False, "ended_at": 2})], ["bad_value"]),
        ([opened, none_wait, ("owner_wait_opened", "coordinator", {"wait_id": WAIT, "title": "W2", "ref": {"kind": "none", "id": "c0ffee02"}, "can_act": "yes"})], ["ref_busy"]),
        ([opened, ("owner_wait_opened", "coordinator", {"wait_id": WAIT, "title": "W", "ref": {"kind": "none", "id": "c0ffee01"}})], ["missing_field"]),
        ([opened, ("owner_wait_opened", "coordinator", {"wait_id": WAIT, "title": "W", "ref": {"kind": "approval", "id": APPR}, "where": "console"})], ["record_fields"]),
        ([opened, ("owner_wait_opened", "coordinator", {"wait_id": WAIT, "title": "W", "ref": {"kind": "none", "id": "c0ffee01"}, "can_act": "not_yet", "where": "thread", "commands": ["echo"]})], ["commands_where"]),
        ([opened, ("owner_wait_opened", "coordinator", {"wait_id": WAIT, "title": "W", "ref": {"kind": "none", "id": "c0ffee01"}, "can_act": "not_yet", "deadline": 9, "no_deadline": True})], ["bad_value"]),
        ([opened, ("owner_wait_opened", "coordinator", {"wait_id": WAIT, "title": "W", "ref": {"kind": "none", "id": "c0ffee01"}, "can_act": "not_yet", "after": M})], ["unknown_id"]),
        ([opened, ("owner_wait_opened", "coordinator", {"wait_id": WAIT, "title": "W", "ref": {"kind": "none", "id": "c0ffee01"}, "can_act": "not_yet", "replaces": WAIT2})], ["unknown_id"]),
        ([opened, appr, ("owner_wait_opened", "coordinator", {"wait_id": WAIT2, "title": "W2", "ref": {"kind": "approval", "id": APPR2}, "replaces": WAIT})], ["not_a_record"]),
        ([opened, none_wait, ("owner_wait_closed", "coordinator", {"wait_id": WAIT, "how": "done"}), ("owner_wait_opened", "coordinator", {"wait_id": WAIT2, "title": "W2", "ref": {"kind": "none", "id": "c0ffee02"}, "can_act": "not_yet", "replaces": WAIT})], ["already_settled"]),
        ([opened, appr, ("owner_wait_opened", "coordinator", {"wait_id": WAIT2, "title": "W2", "ref": {"kind": "approval", "id": APPR}})], ["ref_busy"]),
        ([opened, ("owner_wait_seen", "observer", {"wait_id": WAIT, "sampled_at": 2, "ref_state": "pending"})], ["wait_missing"]),
        ([opened, none_wait, ("owner_wait_seen", "observer", {"wait_id": WAIT, "sampled_at": 3, "ref_state": "pending"})], ["not_a_record"]),
        ([opened, appr, ("owner_wait_seen", "observer", {"wait_id": WAIT, "sampled_at": 3, "ref_state": "executed"}), ("owner_wait_seen", "observer", {"wait_id": WAIT, "sampled_at": 4, "ref_state": "executed"})], ["already_settled"]),
        ([opened, appr, ("owner_wait_seen", "coordinator", {"wait_id": WAIT, "sampled_at": 3, "ref_state": "pending"})], ["by_mismatch"]),
        ([opened, appr, ("owner_wait_seen", "observer", {"wait_id": WAIT, "sampled_at": 3, "ref_state": "nope"})], ["bad_value"]),
        ([opened, ("owner_wait_ready", "coordinator", {"wait_id": WAIT})], ["wait_missing"]),
        ([opened, appr, ("owner_wait_ready", "coordinator", {"wait_id": WAIT})], ["bound_wait"]),
        ([opened, none_wait, ("owner_wait_closed", "coordinator", {"wait_id": WAIT, "how": "done"}), ("owner_wait_ready", "coordinator", {"wait_id": WAIT})], ["already_settled"]),
        ([opened, ("owner_wait_opened", "coordinator", {"wait_id": WAIT, "title": "W", "ref": {"kind": "none", "id": "c0ffee01"}, "can_act": "yes"}), ("owner_wait_ready", "coordinator", {"wait_id": WAIT})], ["already_ready"]),
        ([opened, none_wait, ("owner_wait_ready", "observer", {"wait_id": WAIT})], ["by_mismatch"]),
        ([opened, ("owner_wait_closed", "coordinator", {"wait_id": WAIT, "how": "done"})], ["wait_missing"]),
        ([opened, none_wait, ("owner_wait_closed", "coordinator", {"wait_id": WAIT, "how": "done"}), ("owner_wait_closed", "coordinator", {"wait_id": WAIT, "how": "withdrawn"})], ["already_settled"]),
        ([opened, appr, ("owner_wait_seen", "observer", {"wait_id": WAIT, "sampled_at": 3, "ref_state": "pending"}), ("owner_wait_closed", "coordinator", {"wait_id": WAIT, "how": "withdrawn"})], ["bound_wait"]),
        ([opened, appr, ("owner_wait_closed", "coordinator", {"wait_id": WAIT, "how": "done"})], ["bound_wait"]),
        ([opened, none_wait, ("owner_wait_closed", "observer", {"wait_id": WAIT, "how": "done"})], ["by_mismatch"]),
        ([opened, ("note", "coordinator", {"text": "n", "step_id": P})], ["step_missing"]),
        ([opened, ("observer_round", "observer", {"round_id": P, "started_at": 1, "ended_at": 2, "confirmed": [], "failed": []})], ["wrong_log"]),
        ([opened, proc, start, finish, ("work_closed", "coordinator", {"claim": "landed"}), ("step_finished", "wrapper", {"step_id": P, "run_id": RUN, "exit": {"code": 0}})], ["after_close"]),
        ([opened, rec, ("record_seen", "observer", {"step_id": R, "sampled_at": 3, "found": False}), ("record_seen", "observer", {"step_id": R, "sampled_at": 2, "found": False})], ["sampled_at"]),
        ([opened, appr, ("owner_wait_seen", "observer", {"wait_id": WAIT, "sampled_at": 3, "ref_state": "executed"}), ("owner_wait_opened", "coordinator", {"wait_id": WAIT2, "title": "W2", "ref": {"kind": "approval", "id": APPR}})], []),
        ([opened, appr, ("owner_wait_seen", "observer", {"wait_id": WAIT, "sampled_at": 3, "ref_state": "pending"}), ("owner_wait_seen", "observer", {"wait_id": WAIT, "sampled_at": 2, "ref_state": "pending"})], ["sampled_at"]),
        ([opened, none_wait, ("owner_wait_closed", "coordinator", {"wait_id": WAIT, "how": "done"}), ("step_declared", "coordinator", {"step_id": P, "name": "n", "kind": "other", "who": "C", "watch": "none", "waiting_on": [WAIT]}), ("step_started", "coordinator", {"step_id": P, "run_id": RUN})], []),
    ]
    for rows, reasons in cases:
        got, _view = _reasons(rows)
        _need(got == reasons, ("context", rows[-1][0], reasons, got))
    # A bound wait that was never seen may be withdrawn. It is not a defect.
    got, view = _reasons([opened, appr, ("owner_wait_closed", "coordinator", {"wait_id": WAIT, "how": "withdrawn"})])
    _need(got == [], ("withdraw unseen", got))
    _need(view.waits[WAIT].settled_how == "withdrawn", "withdrawn how")
    many = [opened]
    for index in range(200):
        many.append(("step_declared", "coordinator", {"step_id": f"{index:08x}", "name": "n", "kind": "other", "who": "C", "watch": "none"}))
    many.append(("step_declared", "coordinator", {"step_id": M, "name": "n", "kind": "other", "who": "C", "watch": "none"}))
    got, _view = _reasons(many)
    _need(got == ["too_many_steps"], ("too many steps", got))
    waits = [opened]
    for index in range(20):
        waits.append(("owner_wait_opened", "coordinator", {"wait_id": f"{index:08x}", "title": "W", "ref": {"kind": "none", "id": f"id{index}"}, "can_act": "not_yet"}))
    waits.append(("owner_wait_opened", "coordinator", {"wait_id": M, "title": "W", "ref": {"kind": "none", "id": "overflow"}, "can_act": "not_yet"}))
    got, _view = _reasons(waits)
    _need(got == ["too_many_waits"], ("too many waits", got))
    from contextual import _contextual
    from validate import Step, View, classify
    late = {"type": "work_opened", "v": 2, "seq": 2, "at": 1, "by": "coordinator", "prev_sha256": "", "work_id": WORK, "title": "T"}
    got = [item["reason"] for item in classify([late], work_id=WORK).defects]
    _need(got == ["not_first"], ("opened at seq 2", got))
    found = View(work_id=WORK)
    step = Step(R, "r", "release", "C", "record", 0, 1, superseded=True, ever_found=True)
    found.steps[R] = step
    reason = _contextual(found, {"type": "record_seen", "step_id": R, "by": "observer", "found": False, "sampled_at": 1, "at": 1}, 1)
    _need(reason != "never_found", reason)
    dangling = View(work_id=WORK)
    dangling.steps[P] = Step(P, "n", "other", "C", "none", 0, 1, waiting_on=["missing"])
    reason = _contextual(dangling, {"type": "step_started", "step_id": P, "by": "coordinator", "run_id": RUN, "at": 2, "seq": 2}, 1)
    _need(reason != "waits_open", reason)


def _apply_rules():
    """What a valid event writes. The early return is not the rule; the fields are."""
    from model import OUTPUT_LARGE_BYTES
    opened = ("work_opened", "coordinator", {"work_id": WORK, "title": "T"})
    proc = ("step_declared", "coordinator", {"step_id": P, "name": "n", "kind": "other", "who": "C", "watch": "process"})
    start = ("step_started", "wrapper", {"step_id": P, "run_id": RUN, "command": "echo"})
    rec = ("step_declared", "coordinator", {"step_id": R, "name": "r", "kind": "release", "who": "C", "watch": "record", "locator": LOC})
    _reasons_big, view = _reasons([
        opened, proc, start,
        ("step_seen", "wrapper", {"step_id": P, "run_id": RUN, "sampled_at": 4, "alive": True, "output_bytes": OUTPUT_LARGE_BYTES}),
    ])
    _need(_reasons_big == [], _reasons_big)
    _need(view.steps[P].output_large is False, "1 GiB is not over the limit")
    _need(view.steps[P].last_output == OUTPUT_LARGE_BYTES, "last output is kept")
    _got, view = _reasons([
        opened, proc, start,
        ("step_seen", "wrapper", {"step_id": P, "run_id": RUN, "sampled_at": 4, "alive": True, "output_bytes": OUTPUT_LARGE_BYTES + 1}),
    ])
    _need(view.steps[P].output_large is True, "over 1 GiB is output_large")
    _got, view = _reasons([
        opened, proc, start,
        ("step_seen", "observer", {"step_id": P, "run_id": RUN, "sampled_at": 4, "alive": False}),
    ])
    _need(view.steps[P].dead is True, "alive false is dead")
    _got, view = _reasons([
        opened, rec,
        ("record_seen", "observer", {"step_id": R, "sampled_at": 3, "found": True, "uid": "u", "condition": "True"}),
    ])
    _need(view.steps[R].ended is True and view.steps[R].found_uid == "u", "True ends a record and keeps the first uid")
    _got, view = _reasons([
        opened, rec,
        ("record_seen", "observer", {"step_id": R, "sampled_at": 3, "found": True, "uid": "u", "condition": "False"}),
    ])
    _need(view.steps[R].ended is True, "False ends a record")
    _got, view = _reasons([
        opened, rec,
        ("record_seen", "observer", {"step_id": R, "sampled_at": 3, "found": True, "uid": "u", "condition": "Unknown"}),
    ])
    _need(view.steps[R].ended is False, "Unknown does not end a record")
    _got, view = _reasons([
        opened,
        ("owner_wait_opened", "coordinator", {"wait_id": WAIT, "title": "W", "ref": {"kind": "none", "id": "c0ffee01"}, "can_act": "yes", "blocks_nothing": True}),
    ])
    _need(view.waits[WAIT].yes_at == 2, "yes is stamped at the open")
    _need(view.waits[WAIT].blocks_nothing is True, "blocks_nothing true is kept")
    _got, view = _reasons([
        opened,
        ("owner_wait_opened", "coordinator", {"wait_id": WAIT, "title": "W", "ref": {"kind": "none", "id": "c0ffee01"}, "can_act": "not_yet"}),
    ])
    _need(view.waits[WAIT].yes_at is None, "not_yet has no yes_at")
    _got, view = _reasons([
        opened,
        ("step_declared", "coordinator", {"step_id": P, "name": "old", "kind": "other", "who": "C", "watch": "none"}),
        ("step_declared", "coordinator", {"step_id": N, "name": "new", "kind": "other", "who": "C", "watch": "none", "replaces": P, "replaces_text": "gone"}),
    ])
    _need(view.steps[P].superseded_text == "gone", "replaces_text is kept on the old step")
    _got, view = _reasons([
        opened,
        ("owner_wait_opened", "coordinator", {"wait_id": WAIT, "title": "W", "ref": {"kind": "approval", "id": APPR}}),
        ("owner_wait_seen", "observer", {"wait_id": WAIT, "sampled_at": 3, "ref_state": "executed"}),
    ])
    _need(view.waits[WAIT].settled_at == 3, "the first terminal observation stamps settled_at")
    from contextual import _apply
    from validate import View
    bare = View()
    _apply(bare, {
        "type": "step_declared", "at": 5, "step_id": P, "name": "n", "kind": "other", "who": "C",
        "watch": "none", "by": "",
    }, 0)
    _need(bare.steps[P].declared_by == "coordinator", "a missing by is recorded as coordinator")
    _need(bare.steps[P].declared_seq == 0, "a missing seq is recorded as 0")


def _eta_and_feed():
    from fold import _eta_unsure
    from harness import fold_one
    _need(_eta_unsure([{"state": "quiet", "usual_s": 10}]) is True, "quiet is unsure even with a usual")
    _need(_eta_unsure([{"state": "unknown", "usual_s": 10}]) is True, "unknown")
    _need(_eta_unsure([{"state": "dead", "usual_s": 10}]) is True, "dead")
    _need(_eta_unsure([{"state": "failed", "usual_s": 10}]) is True, "failed")
    _need(_eta_unsure([{"state": "running", "usual_s": 10}]) is False, "a running step with a usual is sure")
    _need(_eta_unsure([{"state": "running"}]) is True, "a running step without a usual is unsure")
    _need(_eta_unsure([{"state": "waiting"}]) is True, "waiting without a usual")
    _need(_eta_unsure([{"state": "done"}]) is False, "done needs no usual")
    _need(_eta_unsure([{"state": "done", "usual_s": 10}]) is False, "done with a usual")
    rows = [
        ("work_opened", "coordinator", {"work_id": WORK, "title": "T"}),
        ("step_declared", "coordinator", {"step_id": P, "name": "n", "kind": "other", "who": "C", "watch": "none"}),
        ("note", "coordinator", {"text": "hello", "step_id": P}),
        ("note", "coordinator", {"text": "plain"}),
    ]
    doc = fold_one(_chain(rows), 10)
    feed = {(row["text"], row["step"]) for row in doc["feed"]}
    _need(("hello", P) in feed, feed)
    _need(("plain", "") in feed, feed)
    closed = [
        ("work_opened", "coordinator", {"work_id": WORK, "title": "T"}),
        ("owner_wait_opened", "coordinator", {"wait_id": WAIT, "title": "Approve", "ref": {"kind": "none", "id": "c0ffee01"}, "can_act": "yes"}),
        ("owner_wait_closed", "coordinator", {"wait_id": WAIT, "how": "done"}),
    ]
    doc = fold_one(_chain(closed), 10)
    _need(any(row["text"] == "Approve" and row["state"] == "done" for row in doc["feed"]), doc["feed"])
    terminal = [
        ("work_opened", "coordinator", {"work_id": WORK, "title": "T"}),
        ("owner_wait_opened", "coordinator", {"wait_id": WAIT, "title": "Ticket", "ref": {"kind": "approval", "id": APPR}}),
        ("owner_wait_seen", "observer", {"wait_id": WAIT, "sampled_at": 3, "ref_state": "executed"}),
    ]
    doc = fold_one(_chain(terminal), 10)
    _need(any(row["text"] == "Ticket" and row["state"] == "executed" for row in doc["feed"]), doc["feed"])


def _shape_limits():
    """Platform array caps are strict: the boundary length is kept, one past it is not."""
    from publish import _owner_now_ok, shape_ok

    def raw(**fields):
        body = {"at": 1}
        body.update(fields)
        return json.dumps(body).encode()

    _need(shape_ok(raw()) is True, "at alone")
    _need(shape_ok(b"[]") is False, "not an object")
    _need(shape_ok("nope") is False, "bytes only")
    _need(shape_ok(raw(needs_you=["a"] * 30)) is True, "needs_you 30")
    _need(shape_ok(raw(needs_you=["a"] * 31)) is False, "needs_you 31")
    _need(shape_ok(raw(needs_you=[1])) is False, "needs_you strings")
    _need(shape_ok(raw(needs_you="a")) is False, "needs_you list")
    _need(shape_ok(raw(recent=["a"] * 30)) is True and shape_ok(raw(recent=["a"] * 31)) is False, "recent")
    _need(shape_ok(raw(owner_now=[{}] * 10)) is True, "owner_now 10")
    _need(shape_ok(raw(owner_now=[{}] * 11)) is False, "owner_now 11")
    _need(shape_ok(raw(owner_now=[1])) is False, "owner_now item")
    _need(shape_ok(raw(owner_now=[{"actions": [{}] * 10}])) is True, "actions 10")
    _need(shape_ok(raw(owner_now=[{"actions": [{}] * 11}])) is False, "actions 11")
    _need(shape_ok(raw(owner_now=[{"actions": [1]}])) is False, "action dict")
    _need(shape_ok(raw(owner_now=[{"actions": "x"}])) is False, "actions list")
    _need(shape_ok(raw(owner_next={})) is True and shape_ok(raw(owner_next=[])) is False, "owner_next")
    _need(shape_ok(raw(graph=[1] * 60)) is True and shape_ok(raw(graph=[1] * 61)) is False, "graph")
    _need(shape_ok(raw(graph="x")) is False, "graph list")
    _need(shape_ok(raw(queue=[1] * 30)) is True and shape_ok(raw(queue=[1] * 31)) is False, "queue")
    _need(shape_ok(raw(queue="x")) is False, "queue list")
    _need(shape_ok(raw(works=[{}] * 30)) is True and shape_ok(raw(works=[{}] * 31)) is False, "works")
    _need(shape_ok(raw(works="x")) is False, "works list")
    _need(shape_ok(raw(works=[1])) is False, "work dict")
    _need(shape_ok(raw(works=[{"next": {}}])) is True and shape_ok(raw(works=[{"next": []}])) is False, "work next")
    _need(shape_ok(raw(works=[{"steps": [{}] * 20}])) is True, "steps 20")
    _need(shape_ok(raw(works=[{"steps": [{}] * 21}])) is False, "steps 21")
    _need(shape_ok(raw(works=[{"steps": "x"}])) is False, "steps list")
    _need(shape_ok(raw(works=[{"steps": [1]}])) is False, "step dict")
    _need(shape_ok(raw(works=[{"steps": [{"events": [{}] * 30}]}])) is True, "events 30")
    _need(shape_ok(raw(works=[{"steps": [{"events": [{}] * 31}]}])) is False, "events 31")
    _need(shape_ok(raw(works=[{"steps": [{"events": [1]}]}])) is False, "event dict")
    _need(shape_ok(raw(works=[{"steps": [{"events": "x"}]}])) is False, "events list")
    _need(shape_ok(raw(feed=[{"at": 1}] * 50)) is True, "feed 50")
    _need(shape_ok(raw(feed=[{"at": 1}] * 51)) is False, "feed 51")
    _need(shape_ok(raw(feed="x")) is False, "feed list")
    _need(shape_ok(raw(feed=[1])) is False, "feed row")
    _need(shape_ok(raw(feed=[{"at": "x"}])) is False, "feed at")
    _need(shape_ok(raw(coordinator={})) is True and shape_ok(raw(coordinator=[])) is False, "coordinator")
    _need(_owner_now_ok([{}] * 10) is True and _owner_now_ok([{}] * 11) is False, "owner helper")
    _need(_owner_now_ok([{"actions": None}]) is True, "missing actions")
    _need(_owner_now_ok("x") is False, "owner helper type")


def _keep_rules():
    """Table B: levels 0–6 keep every marker. A level outside that list drops them."""
    import copy
    from survive import apply_keep

    def doc():
        return {
            "recorder_failed": {"stage": "fold"},
            "owner_all": [{"can_act": "unknown", "reason": "not_confirmed"}, {"can_act": "yes"}, "nope"],
            "works": [{
                "steps": [{"gap": True, "state": "unknown", "reason": "log_invalid"}, "nope"],
                "state_counts": {"unknown": 2, "waiting": 1},
            }],
        }

    kept = doc()
    apply_keep(kept, 0)
    _need("recorder_failed" in kept, "level 0 keeps recorder_failed")
    _need(kept["owner_all"][0]["can_act"] == "unknown", "level 0 keeps owner unknown")
    _need(kept["works"][0]["steps"][0]["state"] == "unknown", "level 0 keeps step unknown")
    _need("gap" in kept["works"][0]["steps"][0], "level 0 keeps gap")
    _need(kept["works"][0]["state_counts"]["unknown"] == 2, "level 0 keeps the unknown count")
    _need("gap" not in kept["works"][0], "a zero gap flag does not invent gap")
    dropped = doc()
    apply_keep(dropped, 7)
    _need("recorder_failed" not in dropped, "an unlisted level drops recorder_failed")
    _need(dropped["owner_all"][0]["can_act"] == "yes" and "reason" not in dropped["owner_all"][0], "unknown becomes yes")
    _need(dropped["owner_all"][1]["can_act"] == "yes", "yes stays yes")
    _need(dropped["works"][0]["steps"][0]["state"] == "waiting" and "reason" not in dropped["works"][0]["steps"][0], "unknown step becomes waiting")
    _need("gap" not in dropped["works"][0]["steps"][0], "gap is dropped")
    _need(dropped["works"][0]["state_counts"] == {"unknown": 0, "waiting": 3}, dropped["works"][0]["state_counts"])
    empty = {"works": ["nope"]}
    apply_keep(copy.deepcopy(empty), 7)


def _number_tokens():
    """12.2 row 8: -0 is zero, 17-digit integers are out of range, NaN is not a number."""
    from model import TWO53
    from read import _token_bad
    _need(_token_bad("-0") is False, "-0")
    _need(_token_bad("-0.0") is False, "-0.0")
    _need(_token_bad("0") is False, "0")
    _need(_token_bad(str(TWO53)) is False, "2^53 is in range")
    _need(_token_bad(str(-TWO53)) is False, "-2^53 is in range")
    _need(_token_bad(str(TWO53 + 1)) is True, "past 2^53")
    _need(_token_bad(str(-TWO53 - 1)) is True, "past -2^53")
    _need(_token_bad("1" * 18) is True, "18 digit integer")
    _need(_token_bad("nan") is True, "nan")
    _need(_token_bad("inf") is True, "inf")
    _need(_token_bad("-inf") is True, "-inf")
    _need(_token_bad(str(float(TWO53))) is False, "the float of 2^53 is in range")


def _field_edges():
    """A non-string id is bad_value before the pattern runs. A bad pattern is too."""
    step = dict(step_id=P, name="n", kind="other", who="C", watch="none")
    none_ref = {"kind": "none", "id": "c0ffee01"}
    opened = dict(wait_id=WAIT, title="W", ref=none_ref, can_act="not_yet")
    cases = [
        (_ev("step_declared", **dict(step, name=1)), "bad_type"),
        (_ev("step_superseded", step_id=1), "bad_value"),
        (_ev("step_seen", step_id=P, run_id="zz", sampled_at=1, alive=True), "bad_value"),
        (_ev("step_finished", step_id=P, run_id="zz", exit={"code": 0}), "bad_value"),
        (_ev("step_finished", step_id=P, run_id=RUN, exit={"code": True}), "bad_type"),
        (_ev("record_seen", step_id=1, sampled_at=1, found=False), "bad_value"),
        (_ev("owner_wait_opened", **dict(opened, wait_id=1)), "bad_value"),
        (_ev("owner_wait_opened", wait_id=WAIT, title="W", ref={"kind": "nope", "id": "c"}), "bad_value"),
        (_ev("owner_wait_opened", **dict(opened, after=1)), "bad_value"),
        (_ev("owner_wait_opened", **dict(opened, replaces="zz")), "bad_value"),
        (_ev("owner_wait_opened", **dict(opened, replaces=1)), "bad_value"),
        (_ev("owner_wait_seen", wait_id=1, sampled_at=1, ref_state="pending"), "bad_value"),
        (_ev("owner_wait_ready", wait_id=1), "bad_value"),
        (_ev("owner_wait_closed", wait_id=1, how="done"), "bad_value"),
        (_ev("note", text="n", step_id=1), "bad_value"),
        (_ev("observer_round", by="observer", round_id=1, started_at=1, ended_at=1, confirmed=[], failed=[]), "bad_value"),
        (_ev("observer_round", by="observer", round_id=P, started_at=1, ended_at="x", confirmed=[], failed=[]), "bad_type"),
        (_ev("observer_round", by="observer", round_id=P, started_at=1, ended_at=1, confirmed=[], failed="x"), "bad_type"),
        (_ev("tail_repaired", repair_id="r" * 81, bytes=0, sha256=SHA), "bad_value"),
        (_ev("work_opened", work_id=WORK, title="T", seq=True), "bad_type"),
        (_ev("work_opened", work_id=WORK, title="T", seq=1.5), "bad_type"),
        (_ev("work_opened", work_id=WORK, title="T", prev_sha256=1), "bad_type"),
        (_ev("work_opened", work_id=WORK, title="T", prev_sha256="zz"), "bad_value"),
        (_ev("work_opened", work_id=WORK, title="T", v=True), "bad_type"),
        (_ev("work_opened", work_id=WORK, title="T", v=1), "bad_value"),
    ]
    for event, reason in cases:
        got = _parse(event)
        _need(got == reason, ("field edge", event.get("type"), reason, got))

    class _EqualsKind:
        def __eq__(self, other):
            return other == "work_opened"

        def __hash__(self):
            return hash("work_opened")

    _need(_parse({"type": _EqualsKind(), "v": 2, "at": 1, "by": "coordinator", "work_id": WORK, "title": "T"}) == "unknown_type", "kind is a string before membership")


def _publish_order_and_record():
    """Section 5 keep order, and the record-step table in section 4."""
    from fold import _record_step
    from model import watch_matches
    from ownerball import _owner_sort
    from publish import _step_sort, _work_group
    from validate import Step, View, has_control

    record = {"source": "record", "can_act": "yes", "deadline": 1, "ref": {"kind": "approval", "id": APPR}}
    later = {"source": "record", "can_act": "yes", "deadline": 2, "ref": {"kind": "approval", "id": APPR}}
    declared = {"source": "declared", "can_act": "not_yet", "works": [{"work_id": WORK}], "wait_id": WAIT}
    _need(_owner_sort(record) < _owner_sort(declared), "records sort before declared")
    _need(_owner_sort(record) < _owner_sort(later), "an earlier deadline sorts first")
    no_deadline = {"source": "record", "can_act": "yes", "ref": {"kind": "approval", "id": APPR}}
    _need(_owner_sort(record) < _owner_sort(no_deadline), "a deadline sorts before none")
    _need(_owner_sort({"source": "record", "can_act": "yes"})[3] == ("", ""), "a missing ref sorts as empty")
    _need(_owner_sort({"source": "declared", "can_act": "yes"})[3] == ("", ""), "a missing declared id sorts as empty")

    running = {"work_id": "w", "last_at": 5, "steps": [{"state": "running"}]}
    quiet = {"work_id": "q", "last_at": 9, "steps": [{"state": "quiet"}]}
    _need(_work_group(quiet, set())[0] == 0, "quiet is the first keep group")
    _need(_work_group(running, {"w"})[0] == 0, "an owner id is the first keep group")
    _need(_work_group(running, set()) == (1, -5), "running is the second group, newest first")
    closed = {"work_id": "c", "closed_claim": "landed", "_closed_at": 4, "last_at": 9}
    _need(_work_group(closed, set()) == (3, -4, "c"), "closed sorts by its close time")
    _need(_work_group({"work_id": "c", "closed_claim": "landed", "_closed_at": True, "last_at": 9}, set())[1] == -9, "a boolean close time falls back to last_at")
    _need(_work_group({"closed_claim": "landed", "_closed_at": 1, "last_at": 3}, set())[2] == "", "a missing work id sorts as empty")
    plain = {"work_id": "p", "last_at": 2, "steps": [{"state": "waiting"}]}
    _need(_work_group(plain, set()) == (2, -2), "other open work is the third group")

    done = {"state": "done", "ended": 10}
    _need(_step_sort({"state": "done", "ended": 10, "superseded_by": "x"}, 0)[0] == 1, "a superseded ended step sorts last")
    _need(_step_sort(done, 0)[0] == 0, "an ordinary done step is not last")
    _need(_step_sort(done, 0)[2] == -10, "done steps sort by ended, newest first")
    _need(_step_sort({"state": "done"}, 3)[2] == 0, "a done step without ended sorts as 0")
    _need(_step_sort({"state": "running"}, 4)[2] == 4, "an open step keeps its declaration index")

    _need(watch_matches("implement", "process") and watch_matches("implement", "none"), "implement watches a process or nothing")
    _need(not watch_matches("implement", "record"), "implement is not a record")
    _need(watch_matches("release", "record") and not watch_matches("release", "none"), "release is only a record")
    _need(watch_matches("ci", "record") and watch_matches("ci", "none") and not watch_matches("ci", "process"), "ci is a record or nothing")
    _need(not watch_matches("nope", "process"), "an unknown kind matches nothing")
    _need(not has_control("ok"), "ordinary text")
    _need(has_control("\n") and has_control("\x7f") and has_control("\u2028") and has_control("\u2029") and has_control("\u202e"), "controls and separators")
    _need(not has_control("\u202f"), "a narrow no-break space is not one of those")

    key = f"step:{WORK}/{R}"
    rounds = [{"ended_at": 10, "confirmed": [key], "failed": []}]
    failed = Step(R, "r", "release", "C", "record", 0, 1, locator=dict(LOC))
    failed.record_obs = [{"condition": "False", "started_at": 2, "ended_at": 3, "reason_quote": "boom"}]
    failed.ever_found = True
    public, row = _record_step(failed, View(work_id=WORK), rounds, 10, WORK)
    _need(row == "ended" and public["started"] == 2 and public["reason_quote"] == "boom", (row, public))
    found = Step(R, "r", "release", "C", "record", 0, 1, locator=dict(LOC), usual_s=10)
    found.ever_found = True
    found.record_obs = [{"found": True, "started_at": 0}]
    public, row = _record_step(found, View(work_id=WORK), rounds, 15, WORK)
    _need(row == "running", (row, public))
    public, row = _record_step(found, View(work_id=WORK), rounds, 16, WORK)
    _need(row == "slow" and public["state"] == "slow", (row, public))
    nameless = Step(R, "r", "release", "C", "record", 0, 1, locator=None)
    public, row = _record_step(nameless, View(work_id=WORK), rounds, 10, WORK)
    _need(row == "waiting", row)
    gone = Step(R, "r", "release", "C", "record", 0, 1, locator=dict(LOC))
    gone.superseded = True
    gone.ever_found = True
    public, row = _record_step(gone, View(work_id=WORK), rounds, 10, WORK)
    _need(row != "withdrawn", row)


def _shape_edges():
    from publish import shape_ok

    def raw(**fields):
        return json.dumps({"at": 1, **fields}).encode()

    _need(shape_ok(json.dumps({"host": "h"}).encode()) is False, "at is required")
    _need(shape_ok(json.dumps({"at": 1, "x": None}).encode()) is False, "null is absent")
    _need(shape_ok(raw(host=1)) is False, "host is a string")
    _need(shape_ok(raw(coordinator={"at": "x"})) is False, "coordinator at is a number")
    _need(shape_ok(raw(recent="ab")) is False, "recent is a list")
    _need(shape_ok(raw(recent=[1])) is False, "recent items are strings")
    _need(shape_ok(raw(works=1)) is False, "works is a list")
    _need(shape_ok(raw(works=[{"title": 1}])) is False, "work title is a string")
    _need(shape_ok(raw(works=[{"steps": 1}])) is False, "steps is a list")
    _need(shape_ok(raw(works=[{"steps": [{"name": 1}]}])) is False, "step name is a string")
    _need(shape_ok(raw(works=[{"steps": [{"events": 1}]}])) is False, "events is a list")
    _need(shape_ok(raw(feed=1)) is False, "feed is a list")
    _need(shape_ok(raw(feed=[{}])) is False, "a feed row has a numeric at")
    _need(shape_ok(raw(feed=[{"at": 1, "text": 1}])) is False, "feed text is a string")


def _read_edges():
    from harness import _chain
    from read import read_log
    data = _chain(_chain_events())
    loaded = read_log(WORK, data)
    _need(loaded.nbytes == len(data) and loaded.broken_line is None, (loaded.nbytes, loaded.broken_why))
    empty = read_log(WORK, b"")
    _need(empty.torn_tail is False and empty.events == [], "empty is an empty log, not a torn tail")
    torn = read_log(WORK, b"\nabc")
    _need(torn.torn_tail is True and torn.events == [], "a newline at byte 0 still leaves the following bytes as a torn tail")


def _chain_events():
    return _chain([
        ("work_opened", "coordinator", {"work_id": WORK, "title": "T"}),
    ])




def run_checks():
    _field_rules()
    _field_edges()
    _shape_and_ref_and_exit()
    _context_rules()
    _apply_rules()
    _eta_and_feed()
    _shape_limits()
    _shape_edges()
    _keep_rules()
    _number_tokens()
    _publish_order_and_record()
    _read_edges()
    from test_round7b import _ball_rules, _direct_edges, _small_rules
    _direct_edges()
    _ball_rules()
    _small_rules()


def test_round7_rules():
    run_checks()
