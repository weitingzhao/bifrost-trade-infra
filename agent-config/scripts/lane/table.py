"""Transition table and the six gates, as one table every command consults.

``consult`` is pure. Lock acquisition, repair and verdict flush are the gate
runners in ``commands``; they walk ``GATES`` in order and then call ``consult``.
"""

from __future__ import annotations

from dataclasses import dataclass

from query import IN_PROGRESS, NEGATIVE

GATES = (
    {"id": "lane_exec", "refusal": "a lane step cannot change a lane"},
    {"id": "lock"},
    {
        "id": "log",
        "refusal": "event log invalid at seq {seq}; a person must inspect it",
        "exception": "abandon",
    },
    {"id": "flush"},
    {"id": "table"},
    {"id": "default", "refusal": "{command} is not allowed in state {state}"},
)

RUN_STUB = "run is implemented in round 2"


@dataclass(frozen=True)
class Transition:
    allowed: bool
    message: str
    resulting_state: str | None
    new_round: bool
    effect: str


def settle(result: str, opened: int, budget: int) -> str:
    if result == "passed":
        return "passed"
    if result == "continue":
        return "ready"
    if result in ("unknown", "start_ambiguous"):
        return result
    if opened >= budget:
        return "over_budget"
    return result


def consult(state: str | None, command: str, ctx: dict) -> Transition:
    if state == "verdict_pending":
        pending = ctx.get("pending_result") or "step_failed"
        settled = settle(pending, int(ctx.get("opened") or 0), int(ctx.get("budget") or 2))
        forwarded = dict(ctx)
        forwarded["has_verdict"] = True
        forwarded["result"] = pending
        forwarded["verdict_result"] = pending
        inner = consult(settled, command, forwarded)
        if inner.allowed:
            return inner
        return Transition(False, inner.message, settled, False, "deny")
    if command == "new":
        if state is None:
            return Transition(True, "", "ready", True, "allow_new")
        return Transition(False, f"lane {ctx['lane_id']} exists", state, False, "deny")
    if state is None:
        return Transition(False, f"lane {ctx['lane_id']} does not exist", None, False, "deny")
    if command == "confirm-ended":
        return _confirm(state, ctx)
    if state == "passed":
        rnd = ctx.get("round") or 1
        return Transition(False, f"lane {ctx['lane_id']} passed in round {rnd}; it is closed", state, False, "deny")
    if state == "abandoned":
        return Transition(False, f"lane {ctx['lane_id']} was abandoned", state, False, "deny")
    if state in IN_PROGRESS:
        return Transition(False, f"{command} is not allowed in state {state}", state, False, "deny")
    if state in ("unknown", "start_ambiguous"):
        return _unknown(state, command, ctx)
    if state in NEGATIVE:
        return _negative(state, command, ctx)
    if state == "over_budget":
        return _over_budget(state, command, ctx)
    if state == "ready":
        return _ready(state, command, ctx)
    return Transition(False, f"{command} is not allowed in state {state}", state, False, "deny")


def _deny(state: str | None, message: str) -> Transition:
    return Transition(False, message, state, False, "deny")


def _confirm(state: str | None, ctx: dict) -> Transition:
    attempt = ctx.get("attempt") or ""
    if not ctx.get("known_attempt", True):
        return _deny(state, f"attempt {attempt} is unknown")
    if ctx.get("has_recorded_exit"):
        return _deny(state, "attempt has a recorded exit")
    if ctx.get("confirmed"):
        return _deny(state, f"attempt {attempt} is already confirmed")
    return Transition(True, "", state, False, "allow_confirm")


def _unknown(state: str, command: str, ctx: dict) -> Transition:
    rnd = ctx.get("round") or 1
    step = ctx.get("step") or "implement"
    if command in ("run", "next-round"):
        return _deny(state, f"round {rnd} {step} result is unknown; a person must resolve it")
    if command == "abandon":
        return Transition(True, "", "abandoned", False, "allow_abandon")
    if command == "resolve":
        return _resolve_open(state, ctx)
    return _deny(state, f"{command} is not allowed in state {state}")


def _negative(state: str, command: str, ctx: dict) -> Transition:
    rnd = ctx.get("round") or 1
    if command == "next-round":
        return Transition(True, "", "ready", True, "allow_next")
    if command == "run":
        return _deny(state, f"round {rnd} is closed ({state}); the only way on is next-round")
    if command == "resolve":
        return _resolve_closed(state, ctx)
    if command == "abandon":
        return Transition(True, "", "abandoned", False, "allow_abandon")
    return _deny(state, f"{command} is not allowed in state {state}")


def _over_budget(state: str, command: str, ctx: dict) -> Transition:
    rnd = ctx.get("round") or 1
    if command == "next-round":
        opened = ctx.get("opened")
        budget = ctx.get("budget")
        return _deny(state, f"over budget: {opened}/{budget}; the Owner decides")
    if command == "run":
        shown = ctx.get("verdict_result") or ctx.get("result") or "step_failed"
        return _deny(state, f"round {rnd} is closed ({shown}); the only way on is next-round")
    if command == "resolve":
        return _resolve_closed(state, ctx)
    if command == "abandon":
        return Transition(True, "", "abandoned", False, "allow_abandon")
    return _deny(state, f"{command} is not allowed in state {state}")


def _ready(state: str, command: str, ctx: dict) -> Transition:
    if command == "run":
        changed = ctx.get("file_changed")
        if changed:
            return _deny(state, f"{changed} changed since the lane was created")
        return Transition(True, "", "implementing", False, "allow_run")
    if command == "abandon":
        return Transition(True, "", "abandoned", False, "allow_abandon")
    return _deny(state, f"{command} is not allowed in state {state}")


def _resolve_open(state: str, ctx: dict) -> Transition:
    kind = ctx.get("kind") or "failed"
    attempt = ctx.get("attempt") or ""
    rnd = ctx.get("round") or 1
    if not ctx.get("known_attempt", True):
        return _deny(state, f"attempt {attempt} is unknown")
    if not ctx.get("is_problem", True):
        return _deny(state, f"attempt {attempt} is not the unresolved attempt")
    if kind == "exit-code":
        return _deny(state, f"no wait-based exit record exists for attempt {attempt}")
    if ctx.get("resolved_kind"):
        return _deny(state, f"attempt {attempt} is already resolved as {ctx['resolved_kind']}")
    if kind in ("failed", "cancelled"):
        if ctx.get("recorded"):
            shown = ctx.get("exit_code")
            if shown is None and ctx.get("exit_signal") is not None:
                shown = f"signal {ctx['exit_signal']}"
            if shown is None:
                shown = "none"
            return _deny(state, f"exit code is recorded ({shown}); use --kind evidence-lost")
        return Transition(True, "", settle("step_failed", int(ctx.get("opened") or 1), int(ctx.get("budget") or 2)), False, "allow_resolve")
    if kind == "evidence-lost":
        if not ctx.get("recorded"):
            return _deny(state, "attempt has no recorded exit; use failed or cancelled")
        if ctx.get("has_verdict"):
            return _deny(state, f"round {rnd} already has a verdict")
        return Transition(True, "", settle("step_failed", int(ctx.get("opened") or 1), int(ctx.get("budget") or 2)), False, "allow_resolve")
    if kind == "still-unknown":
        return Transition(True, "", state, False, "allow_resolve")
    return _deny(state, f"resolve is not allowed in state {state}")


def _resolve_closed(state: str, ctx: dict) -> Transition:
    kind = ctx.get("kind") or "failed"
    attempt = ctx.get("attempt") or ""
    rnd = ctx.get("round") or 1
    if kind == "exit-code":
        return _deny(state, f"no wait-based exit record exists for attempt {attempt}")
    if ctx.get("resolved_kind"):
        return _deny(state, f"attempt {attempt} is already resolved as {ctx['resolved_kind']}")
    return _deny(state, f"round {rnd} already has a verdict")
