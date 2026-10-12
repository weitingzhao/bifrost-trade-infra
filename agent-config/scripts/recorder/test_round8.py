"""Round 8. Each check is an input on which a round-7 survivor's expression differs.

The assertions state the rule that expression implements. A mutation that
answers the input differently fails here.
"""

from __future__ import annotations

P = "a1b2c3d4"
N = "c1b2c3d4"
R = "b1b2c3d4"
RUN = "d1b2c3d4"
WAIT = "f1b2c3d4"
WAIT2 = "a2b2c3d4"
WORK = "w1"


def _need(cond, detail):
    if not cond:
        raise AssertionError(detail)


def _step(**fields):
    from validate import Step

    step = Step(P, "n", "implement", "C", "process", 0, 1)
    for key, value in fields.items():
        setattr(step, key, value)
    return step


def _view(**fields):
    from validate import View

    view = View(work_id=WORK)
    for key, value in fields.items():
        setattr(view, key, value)
    return view


def _loaded(view, name="w1", broken_line=None, broken_why=None, defects=None):
    class Loaded:
        pass

    item = Loaded()
    item.view = view
    item.name = name
    item.broken_line = broken_line
    item.broken_why = broken_why
    item.defects = list(defects or [])
    item.torn_tail = False
    item.full = False
    return item


def _watched():
    """Ended steps keep started_at; boundaries of behind, stale, and quiet."""
    from model import CLOCK_SKEW_S, OBS_VALID_S, QUIET_S
    from fold import _watched_step

    view = _view(max_at=100, backwards=set())
    ended = _step(ended=True, started=True, started_at=5, finished={"at": 8, "exit": {"code": 0}})
    public, row = _watched_step(ended, view, 10)
    _need(row == "ended" and public.get("started") == 5, (row, public))
    no_start = _step(ended=True, started=True, finished={"at": 8, "exit": {"code": 0}})
    public, _row = _watched_step(no_start, view, 10)
    _need("started" not in public, public)
    wrapper = _step(watch="process", declared_by="wrapper")
    public, row = _watched_step(wrapper, view, 10)
    _need(row == "unknown" and public.get("reason") == "start_not_recorded", (row, public))
    other = _step(watch="none", declared_by="wrapper")
    _public, row = _watched_step(other, view, 10)
    _need(row == "waiting", row)
    fresh = {"alive": True, "sampled_at": 100, "output_bytes": 1}
    boundary = _step(started=True, started_at=90, watch="process", seen=[fresh], last_sampled=100)
    _public, row = _watched_step(boundary, _view(max_at=100, backwards=set()), 100 - CLOCK_SKEW_S)
    _need(row != "unknown", row)
    missing_clock = _step(started=True, started_at=1, watch="process", seen=[dict(fresh, sampled_at=9)], last_sampled=9)
    _public, row = _watched_step(missing_clock, _view(max_at=None, backwards=set()), 10)
    _need(row != "unknown", row)
    blank = _step(started=True, started_at=1, watch="process", seen=[], start_index=None, last_seen_index=None)
    public, row = _watched_step(blank, _view(max_at=10, backwards={None}), 10)
    _need(row == "running" and public.get("reason") != "clock_backwards", (row, public))
    stale_edge = _step(
        started=True, started_at=0, watch="process",
        seen=[{"alive": True, "sampled_at": 0, "output_bytes": 1}], last_sampled=0,
    )
    _public, row = _watched_step(stale_edge, _view(max_at=OBS_VALID_S, backwards=set()), OBS_VALID_S)
    _need(row == "running", row)
    quiet_edge = _step(
        started=True, started_at=0, watch="process",
        seen=[{"alive": True, "sampled_at": QUIET_S, "output_bytes": 0}], last_sampled=QUIET_S,
    )
    _public, row = _watched_step(quiet_edge, _view(max_at=QUIET_S, backwards=set()), QUIET_S)
    _need(row == "running", row)
    no_time = _step(started=True, started_at=None, watch="process", seen=[])
    _public, row = _watched_step(no_time, _view(max_at=10, backwards=set()), 10)
    _need(row == "running", row)


def _timed_and_small():
    from model import GAP_S, SLOW_FACTOR
    from fold import _confirm_reason, _finish, _gap, _is_number, _last_confirmed_at, _silence_from, _timed, _unknown, _waiting_on_open

    step = _step(started=True, started_at=0, usual_s=10)
    public, row = _timed({}, step, SLOW_FACTOR * 10, gap=False, none=False)
    _need(row == "running" and "overdue" not in public, (row, public))
    public, row = _timed({}, step, SLOW_FACTOR * 10 + 1, gap=False, none=False)
    _need(row == "slow", row)
    no_start = _step(usual_s=10, started_at=None)
    public, row = _timed({}, no_start, 100, gap=False, none=False)
    _need(row == "running" and "eta_end" not in public, public)
    _need(_is_number(True) is False and _is_number(1) is True and _is_number(float("nan")) is False, "a number is finite and not a boolean")
    _need(_is_number("1") is False, "a string is not a number")
    _public, row = _unknown({}, "clock", row="kept")
    _need(row == "kept", row)
    _need(_last_confirmed_at([{"ended_at": 4}], "missing") is None, "a round without confirmed does not confirm")
    _need(_last_confirmed_at([{"confirmed": ["k"], "ended_at": 4}], "k") == 4, "the confirming round supplies ended_at")
    ended = _step(finished={"at": 3, "exit": {"signal": ""}}, watch="process")
    public, _row = _finish(ended, {})
    _need(public.get("reason") != "ended_by_signal", public)
    signaled = _step(finished={"at": 3, "exit": {"signal": "TERM"}}, watch="process")
    public, _row = _finish(signaled, {})
    _need(public.get("reason") == "ended_by_signal" and public.get("signal") == "TERM", public)
    coded = _step(finished={"at": 3, "exit": {"code": 0}}, watch="process")
    public, _row = _finish(coded, {})
    _need(public.get("state") == "done" and public.get("ended_how") == "exit_0", public)
    exact = _step(started=True, started_at=0, seen=[{"sampled_at": GAP_S}])
    _need(_gap(exact) is False, "a gap equal to the limit is not a gap")
    over = _step(started=True, started_at=0, seen=[{"sampled_at": GAP_S + 1}])
    _need(_gap(over) is True, "one second over the limit is a gap")
    unstarted = _step(started=False, started_at=0, seen=[{"sampled_at": GAP_S + 5}])
    _need(_gap(unstarted) is False, "a step that has not started has no gap")
    silent = _step(seen=[{"sampled_at": 1}], started_at=2)
    _need(_silence_from(silent) is None, "quiet needs an output size")
    zero = _step(seen=[{"output_bytes": 0, "sampled_at": 1}], started_at=4)
    _need(_silence_from(zero) == 4, "output that never grew is silent from the start")
    one_byte = _step(seen=[{"output_bytes": 1, "sampled_at": 5}], started_at=2)
    _need(_silence_from(one_byte) == 5, "one byte of output is growth")
    grew = _step(seen=[{"output_bytes": 0, "sampled_at": 1}, {"output_bytes": 3, "sampled_at": 6}], started_at=1)
    _need(_silence_from(grew) == 6, "silence starts at the last growth")
    from validate import Wait

    view = _view()
    waiting = _step(waiting_on=[WAIT])
    _need(_waiting_on_open(waiting, view) is False, "a missing wait is not open")
    view.waits[WAIT] = Wait(WAIT, "a", {"kind": "none", "id": "c"}, 0, 1, settled=True)
    _need(_waiting_on_open(waiting, view) is False, "a settled wait is not open")
    view.waits[WAIT].settled = False
    _need(_waiting_on_open(waiting, view) is True, "an unsettled wait is open")
    on_skew = {"ended_at": 12, "failed": [{"key": "k", "error": "read_failed"}], "confirmed": []}
    _need(_confirm_reason("k", [on_skew], 10) == "read_failed", "a round ending exactly at now plus skew is still read")
    _need(_confirm_reason("k", [{"ended_at": 10, "failed": [{"key": "k", "error": ""}], "confirmed": []}], 10) == "not_confirmed", "a blank error is not a reason")
    _need(_confirm_reason("k", [{"ended_at": 10, "failed": [{"key": "k", "error": "read_failed"}], "confirmed": []}], 10) == "read_failed", "the recorded error is the reason")


def _fold_and_feed():
    from model import CLOCK_SKEW_S
    from fold import _apply_unrecorded, _feed, _fold_one, _record_last_seen, _work_public, fold
    from validate import View

    plain = _view()
    plain.max_at = 10
    plain.valid = [{"type": "work_opened", "at": 10}]
    doc = fold([_loaded(plain)], None, 10 - CLOCK_SKEW_S)
    _need(doc["clock"]["reader_behind"] is False, doc["clock"])
    doc = fold(None, [], 1)
    _need(doc["works"] == [], doc["works"])
    first = _loaded(_view(), name="a.jsonl", broken_line=2, broken_why="bad_line")
    second = _loaded(_view(), name="b.jsonl", broken_line=4, broken_why="limit_line")
    doc = fold([], [first, second], 1)
    _need(doc["observer"]["log_invalid_at"]["file"] == "a.jsonl", doc["observer"])
    from validate import Step

    view = View(work_id=WORK)
    step = Step(P, "n", "implement", "C", "process", 0, 1, declared_by="wrapper", run_id="other")
    view.steps[P] = step
    view.step_order = [P]
    built = [{"public": {"work_id": WORK, "steps": [{"step_id": P, "state": "running"}]}, "view": view}]
    rounds = [{"ended_at": 10, "unrecorded": [{"work_id": WORK, "step_id": P, "run_id": RUN}]}]
    _apply_unrecorded(built, rounds, 10)
    _need(built[0]["public"].get("unrecorded_runs") == 1, built[0]["public"])
    step.started = True
    step.run_id = RUN
    built[0]["public"]["unrecorded_runs"] = 0
    built[0]["public"]["steps"] = []
    _apply_unrecorded(built, rounds, 10)
    _need(built[0]["public"].get("unrecorded_runs") == 1, "a missing public step is still unrecorded")
    step.started = False
    step.run_id = RUN
    built[0]["public"]["steps"] = [{"step_id": P, "state": "running"}]
    built[0]["public"]["unrecorded_runs"] = 0
    _apply_unrecorded(built, rounds, 10)
    _need(built[0]["public"].get("unrecorded_runs") == 1, "an unstarted step with this run is still unrecorded")
    step.started = False
    step.declared_by = "coordinator"
    step.run_id = "other"
    public_step = {"step_id": P, "state": "waiting", "reason": "start_not_recorded"}
    built[0]["public"]["steps"] = [public_step]
    built[0]["public"]["unrecorded_runs"] = 0
    _apply_unrecorded(built, rounds, 10)
    _need("last_seen" not in public_step, public_step)
    step.declared_by = "wrapper"
    step.started = True
    public_step.pop("last_seen", None)
    _apply_unrecorded(built, rounds, 10)
    _need("last_seen" not in public_step, public_step)
    view.steps.pop(P)
    public_step = {"step_id": P, "state": "waiting", "reason": "start_not_recorded"}
    built[0]["public"]["steps"] = [public_step]
    built[0]["public"]["unrecorded_runs"] = 0
    _apply_unrecorded(built, rounds, 10)
    _need("last_seen" not in public_step, "a public step with no view step is not a missing start")
    view.steps[P] = step
    view.notes = [{"at": 1, "text": "n"}]
    rows = _feed(view, {}, WORK)
    _need(rows and rows[0]["who"] == "", rows)
    from validate import Wait

    view.notes = []
    view.waits[WAIT] = Wait(WAIT, "title", {"kind": "none", "id": "c"}, 0, 1)
    view.valid = [{"type": "owner_wait_closed", "at": 2, "wait_id": WAIT, "how": "done"}]
    rows = _feed(view, {}, WORK)
    _need(rows and rows[0]["who"] == "", rows)
    view.valid = []
    view.waits[WAIT].terminal_state = "executed"
    view.waits[WAIT].seen = [{"at": 4, "ref_state": "executed"}]
    rows = _feed(view, {}, WORK)
    _need(rows and rows[0]["who"] == "", rows)
    view.notes = []
    view.waits.clear()
    view.valid = [{"type": "owner_wait_closed", "at": 2, "wait_id": "missing", "by": "coordinator", "how": "done"}]
    _need(_feed(view, {}, WORK) == [], "a close whose wait is gone is not a feed row")
    absent = _step(record_obs=[])
    _need(_record_last_seen(absent, [], WORK) is None, "no observation has no last seen")
    found = _step(record_obs=[{"found": True, "sampled_at": 3}])
    _need(_record_last_seen(found, [], WORK)["ref_state"] == "found", "found without a condition is found")
    conditioned = _step(record_obs=[{"condition": "Unknown", "found": True, "sampled_at": 3}])
    _need(_record_last_seen(conditioned, [], WORK)["ref_state"] == "Unknown", "a condition is the ref state")
    missed = _step(record_obs=[{"found": False, "sampled_at": 3}])
    _need(_record_last_seen(missed, [], WORK)["ref_state"] == "not_found", "found false is not_found")
    loaded = _loaded(View(work_id=None), name="from-file")
    one = _fold_one(loaded, [], 1)
    _need(one["public"]["work_id"] == "from-file", one["public"])
    named = _loaded(View(work_id=WORK), name="from-file")
    one = _fold_one(named, [], 1)
    _need(one["public"]["work_id"] == WORK, one["public"])
    named.view.closed = False
    named.broken_line = 3
    named.broken_why = "bad_line"
    one = _fold_one(named, [], 1)
    _need(one["invalid"] is True, one["invalid"])
    named.view.closed = True
    one = _fold_one(named, [], 1)
    _need(one["invalid"] is False, "a closed work keeps its step states")
    public = _work_public(View(work_id=""), loaded, [], 0, False, None)
    _need(public["work_id"] == "from-file", public)
    public = _work_public(View(work_id=WORK), loaded, [], 0, False, None)
    _need(public["work_id"] == WORK, public)
    nameless = _loaded(View(work_id=None), name=None)
    public = _work_public(View(work_id=None), nameless, [], 0, False, None)
    _need(public["work_id"] == "", public)
    record = Step(R, "r", "release", "C", "record", 0, 1, locator={"name": "r"})
    record.record_obs = [{"found": True, "started_at": 1, "sampled_at": 2}]
    named_view = View(work_id=WORK)
    named_view.steps[R] = record
    named_view.step_order = [R]
    confirmed = [{"ended_at": 3, "confirmed": [f"step:{WORK}/{R}"], "failed": []}]
    folded = _fold_one(_loaded(named_view, name="from-file"), confirmed, 10)
    _need(folded["public"]["steps"][0]["state"] == "running", folded["public"]["steps"][0])
    file_view = View(work_id="")
    file_view.steps[R] = record
    file_view.step_order = [R]
    confirmed = [{"ended_at": 3, "confirmed": [f"step:from-file/{R}"], "failed": []}]
    folded = _fold_one(_loaded(file_view, name="from-file"), confirmed, 10)
    _need(folded["public"]["steps"][0]["state"] == "running", folded["public"]["steps"][0])


def _owner():
    from model import REASONS
    from ownerball import (
        _any_in_flight, _any_owner_unknown, _declared_item, _effect, _ended_at, _holds,
        _in_flight_since, _judge_work, _merged_record, _obs_content, _one_next_since,
        _open_merged, _owner_since, _pick, _qualifying_next, _record_created_since,
        _running_since, _streak_start, _unknown_record_item, _yes_waits,
    )
    from validate import Step, Wait

    view = _view(valid=[{"type": "work_opened", "at": 3}])
    wait = Wait(WAIT, "a", {"kind": "none", "id": "c0"}, 0, 10)
    view.waits = {WAIT: wait}
    _need(_in_flight_since(view, {}) == 3, "a wait with no merged status is not in flight")
    _need(_owner_since(view, {}) == 3, "a wait with no merged status is not yes")
    _need(_any_in_flight(view, {}) is False and _any_owner_unknown(view, {}) is False, "missing status is neither")
    _need(_yes_waits(view, {}) == [], "missing status is not yes")
    _need(_open_merged(view, {}) == [], "missing status is not an open merged state")
    yes = {("none", WORK, WAIT): {"status": "yes"}}
    _need([item["status"] for item in _open_merged(view, yes)] == ["yes"], "yes stays open")
    unknown = {("none", WORK, WAIT): {"status": "unknown"}}
    _need([item["status"] for item in _open_merged(view, unknown)] == ["unknown"], "unknown stays open")
    closed = {("none", WORK, WAIT): {"status": "closed"}}
    _need(_open_merged(view, closed) == [], "closed is not open")
    step = Step(R, "r", "release", "C", "record", 0, 1)
    step.record_obs = [{"found": True, "started_at": 4, "at": 5}, {"found": True, "at": 10}]
    view.steps = {R: step}
    created = _record_created_since(view, [{"step_id": R}])
    _need(created == 5, created)  # Continuous found segment includes the first observation.
    bare = Step(R, "r", "release", "C", "record", 0, 1)
    bare.record_obs = [{"found": True, "at": 8}]
    view.steps[R] = bare
    _need(_record_created_since(view, [{"step_id": R}]) == 8, "a found observation with no start and no condition counts")
    running = Step(R, "r", "release", "C", "record", 0, 1)
    running.record_obs = [{"condition": "False", "started_at": 2}]
    view.steps[R] = running
    _need(_running_since(view, [{"step_id": R}]) == 3, "a False condition is not the running start")
    running.record_obs = [{"started_at": 6}]
    _need(_running_since(view, [{"step_id": R}]) == 6, "started_at with no condition is the running start")
    _need(_streak_start([{"ref_state": "approved"}], {"approved"}, "sampled_at") is None, "a streak with no sampled_at has no start")
    _need(_streak_start([{"ref_state": "approved", "sampled_at": 4}], {"approved"}, "sampled_at") == 4, "the first sample is the start")
    finished = Step(P, "n", "implement", "C", "process", 0, 1)
    _need(_ended_at(finished) is None, "no finish and no record observation has no end")
    finished.finished = {"at": 9}
    _need(_ended_at(finished) == 9, "the finish event supplies the end")
    held = Step(P, "n", "implement", "C", "process", 0, 1, usual_s=None)
    view.steps[P] = held
    _need(_effect(view, [P]) is None, "a step with no usual time has no effect")
    held.usual_s = 5
    _need(_effect(view, [P]) == 5, "the usual time is the effect")
    declared = Wait(WAIT, "t", {"kind": "none", "id": "c"}, 0, 1, can_act="")
    item = _declared_item(declared, view, {"public": {"work_id": WORK}, "view": view})
    _need(item["can_act"] == "not_yet", item["can_act"])
    declared.can_act = "yes"
    item = _declared_item(declared, view, {"public": {"work_id": WORK}, "view": view})
    _need(item["can_act"] == "yes", item["can_act"])
    obs = {"ref_state": "pending", "number": 2, "expires_at": 9, "sampled_at": 4}
    _need(_obs_content(obs)[2] == 2, _obs_content(obs))
    _need(_obs_content({"ref_state": "pending"})[2] is None, "a missing number is none")
    members = [({"public": {"work_id": WORK}, "view": view}, wait)]
    unknown_item = _unknown_record_item(("approval", "appr_0123456789abcdef"), members, obs, [], "not_confirmed")
    _need(unknown_item.get("number") == 2 and unknown_item.get("deadline") == 9, unknown_item)
    conflict = _unknown_record_item(("approval", "appr_0123456789abcdef"), members, obs, [], "conflicting_observations")
    _need("number" not in conflict and "ref_state" not in conflict, conflict)
    _need("conflicting_observations" in REASONS, "the conflict reason is one of the closed reasons")
    work = {
        "view": view,
        "public": {"steps": [{"step_id": P, "state": "quiet"}]},
        "flags": [],
        "invalid": False,
        "closed": False,
    }
    judged = _judge_work(work, {})
    _need(judged["why"] == "step_running", judged)
    work["public"]["steps"] = [{"step_id": P, "state": "waiting"}]
    work["flags"] = [(held, {}, "record_created")]
    # state waiting is required; a done step with the flag is not record_created
    work["public"]["steps"] = [{"step_id": P, "state": "done"}]
    judged = _judge_work(work, {})
    _need(judged["why"] != "record_created", judged)
    view.steps[P] = Step(P, "n", "other", "C", "none", 0, 5, waiting_on=[WAIT])
    view.step_order = [P]
    view.waits[WAIT].settled_at = None
    merged = {("none", WORK, WAIT): {"status": "yes"}}
    _need(_qualifying_next(view, merged, [{"step_id": P, "state": "waiting"}]) == [], "an unsettled wait blocks the next step")
    merged = {("none", WORK, WAIT): None}
    _need(_qualifying_next(view, merged, [{"step_id": P, "state": "waiting"}]) == [], "a missing status is not settled")
    view.steps[P].waiting_on = []
    view.steps[P].after = N
    _need(_qualifying_next(view, {}, [{"step_id": P, "state": "waiting"}, {"step_id": N, "state": "running"}]) == [], "after must be done or failed")
    _need(_qualifying_next(view, {}, [{"step_id": P, "state": "waiting"}, {"step_id": N, "state": "failed"}]) == [view.steps[P]], "a failed after step qualifies")
    nxt = Step(P, "n", "other", "C", "none", 0, 5, waiting_on=[WAIT, "missing"])
    view.steps[P] = nxt
    view.waits[WAIT].settled_at = 8
    since = _one_next_since(nxt, view)
    _need(since == 8, since)
    ball = _pick(
        [{"holder": "owner", "why": "owner_can_act", "since": 4, "basis": "declared"}],
        "owner",
        ("owner_can_act",),
    )
    _need(ball.get("basis") == "declared", ball)
    agents = _pick([{"holder": "agents", "why": "step_running", "since": 4, "basis": "declared"}], "agents", ("step_running",))
    _need("basis" not in agents, agents)
    unknown_ball = _pick([{"holder": "unknown", "why": "step_unknown", "since": 4}], "unknown", ("step_unknown",))
    _need("since" not in unknown_ball, unknown_ball)
    waiting = Step(P, "n", "implement", "C", "process", 0, 1, waiting_on=[WAIT], after=N)
    waiting.declared_at = 5
    view.steps = {P: waiting}
    view.step_order = [P]
    view.waits[WAIT] = Wait(WAIT, "t", {"kind": "none", "id": "c"}, 0, 1)
    view.waits[WAIT].settled_at = None
    _need(_one_next_since(waiting, view) == 5, "an unsettled wait does not move the declaration")
    waiting.waiting_on = []
    try:
        missing_after = _qualifying_next(view, {}, [{"step_id": P, "state": "waiting"}])
    except TypeError:
        missing_after = None
    _need(missing_after == [], "a missing after step does not qualify")
    bare_wait = Wait(WAIT, "t", {"kind": "none", "id": "c"}, 0, 1)
    bare_wait.seen = []
    key = ("approval", "appr_0123456789abcdef")
    confirmed = [{"ended_at": 3, "confirmed": [f"{key[0]}:{key[1]}"], "failed": []}]
    _status, item = _merged_record(key, [({"public": {"work_id": WORK}, "view": view}, bare_wait)], [], confirmed, 10)
    _need(item["reason"] == "not_confirmed", item)
    ready = {
        "view": view,
        "public": {"steps": []},
        "flags": [],
        "invalid": False,
    }
    view.waits = {WAIT: bare_wait}
    ball = _judge_work(ready, {("none", WORK, WAIT): {"status": "not_yet", "declared": True}})
    _need(ball["why"] == "owner_item_not_ready", ball)
    # A step already held, whose after is itself, is held once. Skipping the
    # seen step must return; walking it again does not finish.
    import threading

    again = Step(P, "n", "other", "C", "none", 0, 1, waiting_on=[WAIT], after=P)
    view.steps = {P: again}
    view.step_order = [P]
    box = []
    worker = threading.Thread(target=lambda: box.append(_holds(WAIT, view)), daemon=True)
    worker.start()
    worker.join(0.2)
    _need(not worker.is_alive() and box == [[P]], "a step is held once")


def _context_and_model():
    from contextual import _apply, _contextual_observer
    from model import terminal_state
    from validate import View, Wait

    view = View(work_id=WORK)
    view.waits[WAIT] = Wait(WAIT, "a", {"kind": "none", "id": "c"}, 0, 1)
    _apply(view, {"type": "owner_wait_ready", "wait_id": WAIT, "at": 6}, 1)
    _need(view.waits[WAIT].can_act == "yes" and view.waits[WAIT].yes_at == 6, "ready sets yes")
    _apply(view, {"type": "observer_round", "at": 2, "ended_at": 2, "started_at": 1, "confirmed": [], "failed": []}, 2)
    _need(len(view.rounds) == 1, view.rounds)
    _need(_contextual_observer(view, {"type": "note", "by": "observer", "ended_at": 2, "started_at": 1}) == "wrong_log", "only a round belongs on the observer log")
    _need(_contextual_observer(view, {"type": "observer_round", "by": "coordinator", "ended_at": 2, "started_at": 1}) == "by_mismatch", "a round is written by the observer")
    _need(_contextual_observer(view, {"type": "observer_round", "by": "observer", "ended_at": 2, "started_at": 2, "confirmed": [], "failed": []}) is None, "equal ends are in order")
    _need(_contextual_observer(view, {"type": "observer_round", "by": "observer", "ended_at": 1, "started_at": 2, "confirmed": [], "failed": []}) == "round_order", "an end before the start is out of order")
    _need(terminal_state("approval", "executed") is True, "executed ends an approval")
    _need(terminal_state("approval", "pending") is False, "pending does not")
    _need(terminal_state("question", "answered") is True and terminal_state("question", "open") is False, "answered ends a question")
    _need(terminal_state("none", "executed") is False, "a none ref has no terminal state")


def _read_tokens():
    from read import _token_bad

    _need(_token_bad("1e999") is True, "an exponent that overflows is not a token")
    _need(_token_bad("1.5") is False, "a finite float is a token")
    _need(_token_bad("nan") is True, "nan is not a token, and it never reaches the float branch")


def run_checks():
    from test_round8b import _soon
    from validate import _backwards

    # Dropping the backwards comparison makes every later event take the branch
    # and then continue without moving the index.
    found = _soon(lambda: _backwards([{"at": 10}, {"at": 10}]))
    _need(found == set(), found)
    _watched()
    _timed_and_small()
    _fold_and_feed()
    _owner()
    _context_and_model()
    _read_tokens()
    from test_round8b import run_checks as more
    more()


def test_round8_rules():
    run_checks()
