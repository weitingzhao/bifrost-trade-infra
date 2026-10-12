"""Per-event relations and the reduction of one accepted event onto a view."""

from __future__ import annotations

from model import (
    MAX_OPEN_WAITS,
    MAX_STEPS,
    OBSERVER_ERRORS,
    OUTPUT_LARGE_BYTES,
    ROUND_ITEM_LIMIT,
    ref_state_ok,
    terminal_state,
    watch_matches,
)
from validate import (
    Step,
    View,
    Wait,
    _open_items,
    _ref_key,
    _sampled,
    _unsettled_count,
    wait_is_unsettled,
)


def _apply(view: View, event: dict, index: int) -> None:
    kind = event["type"]
    view.valid.append(event)
    at = event["at"]
    view.max_at = at if view.max_at is None else max(view.max_at, at)
    if kind == "work_opened":
        view.opened = True
        view.work_id = event["work_id"]
        view.title = event["title"]
        view.goal = event.get("goal")
        view.work_ref = event.get("work_ref")
        return
    if kind == "work_closed":
        view.closed = True
        view.closed_claim = event["claim"]
        view.closed_at = at
        return
    if kind == "step_declared":
        step = Step(
            step_id=event["step_id"],
            name=event["name"],
            kind=event["kind"],
            who=event["who"],
            watch=event["watch"],
            index=len(view.step_order),
            declared_at=at,
            locator=dict(event["locator"]) if "locator" in event else None,
            waiting_on=list(event.get("waiting_on") or []),
            after=event.get("after"),
            usual_s=event.get("usual_s"),
            usual_basis=event.get("usual_basis"),
            round=event.get("round"),
        )
        step.declared_by = event.get("by") or "coordinator"
        step.declared_seq = event.get("seq") or 0
        view.steps[step.step_id] = step
        view.step_order.append(step.step_id)
        if "replaces" in event:
            old = view.steps[event["replaces"]]
            old.superseded = True
            old.by_step = event["step_id"]
            if "replaces_text" in event:
                old.superseded_text = event["replaces_text"]
        return
    if kind == "step_superseded":
        step = view.steps[event["step_id"]]
        step.superseded = True
        step.superseded_text = event.get("text")
        return
    if kind == "step_started":
        step = view.steps[event["step_id"]]
        step.started = True
        step.started_at = at
        step.start_index = index
        step.run_id = event["run_id"]
        step.command = event.get("command")
        return
    if kind == "step_seen":
        step = view.steps[event["step_id"]]
        step.seen.append(event)
        step.last_sampled = event["sampled_at"]
        if "output_bytes" in event:
            step.last_output = event["output_bytes"]
            if event["output_bytes"] > OUTPUT_LARGE_BYTES:
                step.output_large = True
        if event.get("text") is not None:
            step.note = event["text"]
        if event["alive"] is False:
            step.dead = True
        step.last_seen_index = index
        return
    if kind == "step_finished":
        step = view.steps[event["step_id"]]
        step.ended = True
        step.finished = event
        step.quote = event.get("quote")
        return
    if kind == "record_seen":
        step = view.steps[event["step_id"]]
        step.record_obs.append(event)
        step.last_sampled = event["sampled_at"]
        if event["found"]:
            step.ever_found = True
            if step.found_uid is None:
                step.found_uid = event.get("uid")
        if event.get("condition") in {"True", "False"}:
            step.ended = True
        step.last_seen_index = index
        return
    if kind == "owner_wait_opened":
        wait = Wait(
            wait_id=event["wait_id"],
            title=event["title"],
            ref=dict(event["ref"]),
            index=len(view.wait_order),
            opened_at=at,
            can_act=event.get("can_act"),
            where=event.get("where"),
            reply=event.get("reply"),
            reply_needed=event.get("reply_needed"),
            reply_words=event.get("reply_words"),
            commands=list(event["commands"]) if "commands" in event else None,
            deadline=event.get("deadline"),
            no_deadline=event.get("no_deadline") is True,
            blocks_nothing=event.get("blocks_nothing") is True,
            not_before_text=event.get("not_before_text"),
            advice=event.get("advice"),
            blocks_text=event.get("blocks_text"),
            after_text=event.get("after_text"),
            after=event.get("after"),
            yes_at=at if event.get("can_act") == "yes" else None,
        )
        view.waits[wait.wait_id] = wait
        view.wait_order.append(wait.wait_id)
        if "replaces" in event:
            previous = view.waits[event["replaces"]]
            previous.settled = True
            previous.settled_how = "withdrawn"
            previous.settled_at = at
        return
    if kind == "owner_wait_seen":
        wait = view.waits[event["wait_id"]]
        wait.seen.append(event)
        wait.ever_seen = True
        if terminal_state(wait.ref["kind"], event["ref_state"]):
            if not wait.settled:
                wait.settled_at = event["sampled_at"]
            wait.settled = True
            wait.settled_how = event["ref_state"]
            wait.terminal_state = event["ref_state"]
        return
    if kind == "owner_wait_ready":
        wait = view.waits[event["wait_id"]]
        wait.can_act = "yes"
        wait.yes_at = at
        return
    if kind == "owner_wait_closed":
        wait = view.waits[event["wait_id"]]
        wait.settled = True
        wait.settled_how = event["how"]
        wait.settled_at = at
        return
    if kind == "note":
        view.notes.append(event)
        return
    if kind == "observer_round":
        view.rounds.append(event)
        return


def _contextual(view: View, event: dict, index: int) -> str | None:
    kind = event["type"]
    if kind == "work_closed" and view.closed:
        return "already_closed"
    if view.closed and kind not in {"note", "tail_repaired", "step_finished"}:
        return "after_close"
    if kind == "work_opened":
        if index != 0 and event.get("seq") != 1:
            return "not_first"
        if event.get("seq") != 1:
            return "not_first"
        if view.work_id is not None and event["work_id"] != view.work_id:
            return "work_id_mismatch"
        return None
    if kind == "work_closed":
        if view.closed:
            return "already_closed"
        if _open_items(view):
            return "closed_with_open_items"
        return None
    if kind == "step_declared":
        if event["step_id"] in view.steps:
            return "step_exists"
        if not watch_matches(event["kind"], event["watch"]):
            return "kind_watch"
        if event["watch"] == "process" and "waiting_on" in event:
            return "process_waiting_on"
        if event["watch"] == "record" and "locator" not in event:
            return "needs_locator"
        if "after" in event and event["after"] not in view.steps:
            return "unknown_id"
        for wait_id in event.get("waiting_on") or []:
            if wait_id not in view.waits:
                return "unknown_id"
        if ("usual_s" in event) != ("usual_basis" in event):
            return "bad_value"
        if len(view.steps) >= MAX_STEPS:
            return "too_many_steps"
        if "replaces" in event:
            target = view.steps.get(event["replaces"])
            if target is None:
                return "unknown_id"
            if target.superseded:
                return "superseded"
        return None
    if kind == "step_superseded":
        step = view.steps.get(event["step_id"])
        if step is None:
            return "unknown_id"
        if step.superseded:
            return "superseded"
        started = step.started if step.watch != "record" else step.ever_found
        if started:
            return "withdraw_started"
        return None
    if kind == "step_started":
        step = view.steps.get(event["step_id"])
        if step is None:
            return "not_declared"
        if step.superseded:
            return "superseded"
        if step.started:
            return "already_started"
        if step.watch == "process" and event.get("seq") != step.declared_seq + 1:
            return "late_start"
        if step.watch == "none":
            for wait_id in step.waiting_on:
                wait = view.waits.get(wait_id)
                if wait is not None and wait_is_unsettled(wait):
                    return "waits_open"
        if step.watch == "record":
            return "watch_mismatch"
        expect = "wrapper" if step.watch == "process" else "coordinator"
        if event["by"] != expect:
            return "by_mismatch"
        if step.watch == "process" and "command" not in event:
            return "missing_field"
        if step.watch == "none" and "command" in event:
            return "bad_value"
        return None
    if kind == "step_seen":
        step = view.steps.get(event["step_id"])
        if step is None or step.watch != "process":
            return "watch_mismatch" if step is not None else "not_declared"
        if not step.started:
            return "not_started"
        if event["run_id"] != step.run_id:
            return "run_mismatch"
        if step.ended:
            return "already_ended"
        if step.dead:
            return "already_dead"
        if step.last_output is not None and "output_bytes" in event and event["output_bytes"] < step.last_output:
            return "output_shrunk"
        err = _sampled(event, step.last_sampled)
        if err:
            return err
        expect = "wrapper" if event["alive"] else "observer"
        if event["by"] != expect:
            return "by_mismatch"
        return None
    if kind == "step_finished":
        step = view.steps.get(event["step_id"])
        if step is None:
            return "not_declared"
        if view.closed and not step.dead:
            return "after_close"
        if step.watch == "record":
            return "watch_mismatch"
        if not step.started:
            return "not_started"
        if event["run_id"] != step.run_id:
            return "run_mismatch"
        if step.ended:
            return "already_ended"
        expect = "wrapper" if step.watch == "process" else "coordinator"
        if event["by"] != expect:
            return "by_mismatch"
        if step.watch == "process":
            if "exit" not in event or "reported" in event:
                return "bad_exit"
        else:
            if "reported" not in event or "exit" in event:
                return "bad_exit"
        return None
    if kind == "record_seen":
        step = view.steps.get(event["step_id"])
        if step is None:
            return "not_declared"
        if step.watch != "record":
            return "watch_mismatch"
        if step.ended:
            return "already_ended"
        if step.superseded and not step.ever_found:
            return "never_found"
        if event["by"] != "observer":
            return "by_mismatch"
        if event["found"]:
            if "uid" not in event:
                return "missing_field"
            if step.found_uid is not None and event["uid"] != step.found_uid:
                return "uid_changed"
        elif "uid" in event or "condition" in event or "started_at" in event or "ended_at" in event:
            return "bad_value"
        err = _sampled(event, step.last_sampled)
        if err:
            return err
        return None
    if kind == "owner_wait_opened":
        if event["wait_id"] in view.waits:
            return "ref_busy"
        ref = event["ref"]
        if ref["kind"] == "none":
            if "can_act" not in event:
                return "missing_field"
        else:
            for key in ("where", "reply", "reply_words", "commands", "can_act", "deadline", "no_deadline"):
                if key in event:
                    return "record_fields"
        if "commands" in event and event.get("where") != "terminal":
            return "commands_where"
        if "deadline" in event and "no_deadline" in event:
            return "bad_value"
        if "after" in event and event["after"] not in view.steps:
            return "unknown_id"
        if "replaces" in event:
            target = view.waits.get(event["replaces"])
            if target is None:
                return "unknown_id"
        key = _ref_key(ref)
        for wait in view.waits.values():
            if _ref_key(wait.ref) == key and wait_is_unsettled(wait):
                return "ref_busy"
        if _unsettled_count(view) >= MAX_OPEN_WAITS:
            return "too_many_waits"
        if "replaces" in event:
            target = view.waits[event["replaces"]]
            if target.ref["kind"] != "none":
                return "not_a_record"
            if target.settled:
                return "already_settled"
        return None
    if kind == "owner_wait_seen":
        wait = view.waits.get(event["wait_id"])
        if wait is None:
            return "wait_missing"
        if wait.ref["kind"] == "none":
            return "not_a_record"
        if wait.settled:
            return "already_settled"
        if event["by"] != "observer":
            return "by_mismatch"
        if not ref_state_ok(wait.ref["kind"], event["ref_state"]):
            return "bad_value"
        err = _sampled(event, wait.seen[-1]["sampled_at"] if wait.seen else None)
        if err:
            return err
        return None
    if kind == "owner_wait_ready":
        wait = view.waits.get(event["wait_id"])
        if wait is None:
            return "wait_missing"
        if wait.ref["kind"] != "none":
            return "bound_wait"
        if wait.settled:
            return "already_settled"
        if wait.can_act == "yes":
            return "already_ready"
        if event["by"] != "coordinator":
            return "by_mismatch"
        return None
    if kind == "owner_wait_closed":
        wait = view.waits.get(event["wait_id"])
        if wait is None:
            return "wait_missing"
        if wait.settled:
            return "already_settled"
        if wait.ref["kind"] != "none":
            if not (event["how"] == "withdrawn" and not wait.ever_seen):
                return "bound_wait"
        if event["by"] != "coordinator":
            return "by_mismatch"
        return None
    if kind == "note":
        if "step_id" in event and event["step_id"] not in view.steps:
            return "step_missing"
        return None
    if kind == "observer_round":
        return "wrong_log"
    if kind == "tail_repaired":
        return None
    return "unknown_type"


def _contextual_observer(view: View, event: dict) -> str | None:
    if event["type"] != "observer_round":
        return "wrong_log"
    if event["by"] != "observer":
        return "by_mismatch"
    if event["ended_at"] < event["started_at"]:
        return "round_order"
    unrecorded = event.get("unrecorded") or []
    if len(event["confirmed"]) + len(event["failed"]) + len(unrecorded) > ROUND_ITEM_LIMIT:
        return "round_size"
    for item in event["failed"]:
        if item.get("error") not in OBSERVER_ERRORS:
            return "bad_error"
    keys = list(event["confirmed"])
    keys.extend(item["key"] for item in event["failed"])
    keys.extend(f"step:{item['work_id']}/{item['step_id']}" for item in unrecorded)
    if len(keys) != len(set(keys)):
        return "round_conflict"
    return None


