"""T22: every state x command cell, and no path back to passed."""

from __future__ import annotations

from query import NEGATIVE
from table import consult

STATES = (
    None,
    "ready",
    "implementing",
    "verifying",
    "reviewing",
    "verdict_pending",
    "unknown",
    "start_ambiguous",
    "verify_failed",
    "changes_requested",
    "step_failed",
    "over_budget",
    "passed",
    "abandoned",
)
COMMANDS = ("new", "run", "next-round", "resolve", "confirm-ended", "abandon")
KINDS = ("failed", "cancelled", "evidence-lost", "still-unknown", "exit-code")


def _ctx(state):
    ctx = {
        "lane_id": "L",
        "round": 1,
        "step": "implement",
        "attempt": "att",
        "result": None,
        "verdict_result": None,
        "pending_result": "step_failed",
        "opened": 1,
        "budget": 2,
        "has_verdict": False,
        "file_changed": None,
        "kind": "failed",
        "known_attempt": True,
        "is_problem": True,
        "recorded": False,
        "exit_code": None,
        "exit_signal": None,
        "resolved_kind": None,
        "has_recorded_exit": False,
        "confirmed": False,
    }
    if state in NEGATIVE:
        ctx["result"] = state
        ctx["verdict_result"] = state
        ctx["has_verdict"] = True
    if state == "over_budget":
        ctx["result"] = "step_failed"
        ctx["verdict_result"] = "step_failed"
        ctx["has_verdict"] = True
        ctx["opened"] = 2
        ctx["budget"] = 2
    return ctx


def _expect(state, command, ctx):
    """Section 5, transcribed as (allowed, message)."""
    lane = ctx["lane_id"]
    rnd = ctx["round"]
    step = ctx["step"]
    if state == "verdict_pending":
        settled = "step_failed" if ctx["opened"] < ctx["budget"] else "over_budget"
        if ctx["pending_result"] == "passed":
            settled = "passed"
        return _expect(settled, command, {**ctx, "has_verdict": True, "result": ctx["pending_result"], "verdict_result": ctx["pending_result"]})
    if command == "new":
        if state is None:
            return True, ""
        return False, f"lane {lane} exists"
    if state is None:
        return False, f"lane {lane} does not exist"
    if command == "confirm-ended":
        if ctx["has_recorded_exit"]:
            return False, "attempt has a recorded exit"
        return True, ""
    if state == "passed":
        return False, f"lane {lane} passed in round {rnd}; it is closed"
    if state == "abandoned":
        return False, f"lane {lane} was abandoned"
    if state in ("implementing", "verifying", "reviewing"):
        return False, f"{command} is not allowed in state {state}"
    if state in ("unknown", "start_ambiguous"):
        if command in ("run", "next-round"):
            return False, f"round {rnd} {step} result is unknown; a person must resolve it"
        if command == "abandon":
            return True, ""
        if command == "resolve":
            return True, ""
        return False, f"{command} is not allowed in state {state}"
    if state in NEGATIVE:
        if command == "next-round":
            return True, ""
        if command == "run":
            return False, f"round {rnd} is closed ({state}); the only way on is next-round"
        if command == "resolve":
            return False, f"round {rnd} already has a verdict"
        if command == "abandon":
            return True, ""
        return False, f"{command} is not allowed in state {state}"
    if state == "over_budget":
        if command == "next-round":
            return False, f"over budget: {ctx['opened']}/{ctx['budget']}; the Owner decides"
        if command == "run":
            shown = ctx["verdict_result"]
            return False, f"round {rnd} is closed ({shown}); the only way on is next-round"
        if command == "resolve":
            return False, f"round {rnd} already has a verdict"
        if command == "abandon":
            return True, ""
        return False, f"{command} is not allowed in state {state}"
    if state == "ready":
        if command == "run":
            if ctx["file_changed"]:
                return False, f"{ctx['file_changed']} changed since the lane was created"
            return True, ""
        if command == "abandon":
            return True, ""
        return False, f"{command} is not allowed in state {state}"
    return False, f"{command} is not allowed in state {state}"


def test_t22_table_cells_and_passed_is_unreachable():
    for state in STATES:
        ctx = _ctx(state)
        for command in COMMANDS:
            got = consult(state, command, ctx)
            allowed, message = _expect(state, command, ctx)
            assert (got.allowed, got.message) == (allowed, message), (state, command, got, message)
    # A changed file blocks run, and only run, from ready.
    changed = _ctx("ready")
    changed["file_changed"] = "lane-config.json"
    denied = consult("ready", "run", changed)
    assert denied.message == "lane-config.json changed since the lane was created"
    # Section 6 refusals that the grid's default kind does not show.
    unknown = _ctx("unknown")
    unknown["kind"] = "evidence-lost"
    unknown["recorded"] = False
    assert consult("unknown", "resolve", unknown).message == "attempt has no recorded exit; use failed or cancelled"
    recorded = _ctx("unknown")
    recorded["recorded"] = True
    recorded["exit_code"] = 9
    recorded["kind"] = "failed"
    assert consult("unknown", "resolve", recorded).message == "exit code is recorded (9); use --kind evidence-lost"
    closed = _ctx("step_failed")
    closed["resolved_kind"] = "failed"
    assert consult("step_failed", "resolve", closed).message == "attempt att is already resolved as failed"
    exit_code = _ctx("unknown")
    exit_code["kind"] = "exit-code"
    assert consult("unknown", "resolve", exit_code).message == "no wait-based exit record exists for attempt att"

    starts = [("verify_failed", "verify_failed"), ("changes_requested", "changes_requested"), ("step_failed", "step_failed"), ("over_budget", "step_failed")]
    for pending in ("verify_failed", "changes_requested", "step_failed"):
        starts.append(("verdict_pending", pending))
    for state, pending in starts:
        ctx = _ctx(state)
        ctx["pending_result"] = pending
        if state == "over_budget":
            ctx["opened"] = 2
        _search(state, ctx, origin_round=1)


def _search(state, ctx, origin_round: int) -> None:
    kinds = KINDS

    def walk(current, here, depth, path):
        if current == "passed" and here["round"] == origin_round:
            raise AssertionError("reached passed: " + " ".join(path))
        if depth == 4:
            return
        for command in COMMANDS:
            if command == "new":
                continue
            for kind in kinds if command == "resolve" else (here.get("kind"),):
                nxt_ctx = dict(here)
                nxt_ctx["kind"] = kind
                decision = consult(current, command, nxt_ctx)
                nxt = decision.resulting_state if decision.resulting_state is not None else current
                moved = dict(nxt_ctx)
                if decision.new_round:
                    moved["round"] = nxt_ctx["round"] + 1
                    moved["opened"] = int(nxt_ctx["opened"]) + 1
                    moved["has_verdict"] = False
                walk(nxt, moved, depth + 1, path + (f"{command}:{kind}" if command == "resolve" else command,))

    walk(state, ctx, 0, ())
