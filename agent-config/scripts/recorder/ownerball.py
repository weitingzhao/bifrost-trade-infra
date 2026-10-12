"""Owner list and the ball. Pure. Called by fold."""

from __future__ import annotations

from model import (
    CLOCK_SKEW_S,
    OBS_VALID_S,
    REASONS,
    UNKNOWN_WHY_ORDER,
)
from validate import View
from fold import _confirm_reason, _observation_at

_CAN_ACT_ORDER = {"yes": 0, "unknown": 1, "not_yet": 2}


def _owner_all(built: list, rounds: list, now: float):
    """Items, plus merged status by (kind, id) for the ball."""
    items = []
    merged: dict[tuple, dict] = {}
    groups: dict[tuple, list] = {}
    for work in built:
        view: View = work["view"]
        for wait_id in view.wait_order:
            wait = view.waits[wait_id]
            if wait.ref["kind"] == "none":
                ident = (work["public"]["work_id"], wait.wait_id)
                if wait.settled:
                    merged[("none", *ident)] = {"status": "settled", "declared": True}
                    continue
                item = _declared_item(wait, view, work)
                items.append(item)
                merged[("none", *ident)] = {
                    "status": "yes" if wait.can_act == "yes" else "not_yet",
                    "declared": True,
                    "can_act": wait.can_act,
                }
                continue
            key = (wait.ref["kind"], wait.ref["id"])
            groups.setdefault(key, []).append((work, wait))
    for key, members in groups.items():
        status, item = _merged_record(key, members, built, rounds, now)
        merged[key] = status
        if item is not None:
            items.append(item)
    items.sort(key=_owner_sort)
    return items, merged


def _owner_sort(item: dict):
    source = 0 if item["source"] == "record" else 1
    act = _CAN_ACT_ORDER.get(item.get("can_act"), 9)
    if "deadline" in item:
        when = (0, item["deadline"])
    else:
        when = (1, 0)
    if item["source"] == "record":
        ref = item.get("ref") or {}
        ident = (ref.get("kind") or "", ref.get("id") or "")
    else:
        piece = (item.get("works") or [{}])[0]
        ident = (piece.get("work_id") or "", item.get("wait_id") or "")
    return (source, act, when, ident)


def _holds(wait_id: str, view: View) -> list:
    steps = [view.steps[sid] for sid in view.step_order]
    direct = [step.step_id for step in steps if wait_id in step.waiting_on]
    held = []
    seen = set()
    frontier = set()
    for step_id in direct:
        if step_id not in seen:
            held.append(step_id)
            seen.add(step_id)
            frontier.add(step_id)
    while frontier:
        nxt = []
        for step in steps:
            if step.step_id in seen:
                continue
            if step.after in frontier:
                nxt.append(step.step_id)
        if not nxt:
            break
        for step_id in nxt:
            held.append(step_id)
            seen.add(step_id)
        frontier = set(nxt)
    return held


def _effect(view: View, holds: list):
    if not holds:
        return None
    step = view.steps.get(holds[0])
    if step is None or step.usual_s is None:
        return None
    return step.usual_s


def _declared_item(wait, view: View, work: dict) -> dict:
    holds = _holds(wait.wait_id, view)
    item = {
        "source": "declared",
        "wait_id": wait.wait_id,
        "title": wait.title,
        "can_act": wait.can_act or "not_yet",
        "can_act_basis": "declared",
        "holds_up": holds,
        "works": [_work_piece(work, wait, holds)],
    }
    _copy_optional(item, wait)
    effect = _effect(view, holds)
    if effect is not None:
        item["effect_s"] = effect
    return item


def _copy_optional(item: dict, wait) -> None:
    for key in (
        "where",
        "reply",
        "reply_words",
        "advice",
        "blocks_text",
        "after_text",
        "not_before_text",
        "after",
    ):
        value = getattr(wait, key)
        if value is not None:
            item[key] = value
    if wait.reply_needed is False:
        item["reply_needed"] = False
    if wait.commands is not None:
        item["commands"] = list(wait.commands)
    if wait.deadline is not None:
        item["deadline"] = wait.deadline
    if wait.no_deadline:
        item["no_deadline"] = True
    if wait.blocks_nothing:
        item["blocks_nothing"] = True


def _work_piece(work: dict, wait, holds: list) -> dict:
    piece = {"work_id": work["public"]["work_id"], "title": wait.title, "holds_up": holds}
    for key in ("advice", "blocks_text", "after_text", "not_before_text"):
        value = getattr(wait, key)
        if value is not None:
            piece[key] = value
    effect = _effect(work["view"], holds)
    if effect is not None:
        piece["effect_s"] = effect
    if wait.blocks_nothing:
        piece["blocks_nothing"] = True
    return piece


def _merged_record(key, members, built, rounds, now):
    for _work, wait in members:
        if wait.terminal_state is not None:
            return {"status": "settled", "declared": False, "ref_state": wait.terminal_state}, None
    open_members = [(work, wait) for work, wait in members if not wait.settled]
    if not open_members:
        return {"status": "settled", "declared": False}, None
    observations = []
    for work, wait in open_members:
        for obs in wait.seen:
            observations.append((obs["sampled_at"], obs, work, wait))
    reason = _confirm_reason(f"{key[0]}:{key[1]}", rounds, now)
    if not observations:
        item = _unknown_record_item(key, open_members, None, rounds, reason or "not_confirmed")
        return {"status": "unknown", "declared": False, "can_act": "unknown", "reason": item["reason"]}, item
    latest_at = max(row[0] for row in observations)
    latest = [row for row in observations if row[0] == latest_at]
    if len({_obs_content(row[1]) for row in latest}) != 1:
        item = _unknown_record_item(key, open_members, None, rounds, "conflicting_observations")
        return {
            "status": "unknown",
            "declared": False,
            "can_act": "unknown",
            "reason": "conflicting_observations",
        }, item
    obs = latest[0][1]
    if reason is not None:
        item = _unknown_record_item(key, open_members, obs, rounds, reason)
        return {"status": "unknown", "declared": False, "can_act": "unknown", "reason": item["reason"]}, item
    state = obs["ref_state"]
    if state in {"approved", "running"}:
        return {"status": "in_flight", "declared": False, "ref_state": state}, None
    if state in {"pending", "open", "unknown"}:
        item = _yes_record_item(key, open_members, obs, rounds)
        return {"status": "yes", "declared": False, "can_act": "yes", "ref_state": state}, item
    item = _unknown_record_item(key, open_members, obs, rounds, "not_confirmed")
    return {"status": "unknown", "declared": False, "can_act": "unknown"}, item


def _obs_content(obs: dict):
    """What an exact sampled_at tie is allowed to disagree about."""
    return (
        obs.get("ref_state"),
        obs["expires_at"] if "expires_at" in obs else None,
        obs["number"] if "number" in obs else None,
    )


def _yes_record_item(key, members, obs, rounds) -> dict:
    ref_state = obs["ref_state"]
    item = {
        "source": "record",
        "ref": {"kind": key[0], "id": key[1]},
        "can_act": "yes",
        "ref_state": ref_state,
        "where": "console",
        "reply_needed": False,
        "works": [],
    }
    if "expires_at" in obs:
        item["deadline"] = obs["expires_at"]
        item["deadline_source"] = "record"
    if "number" in obs:
        item["number"] = obs["number"]
    item["last_seen"] = {
        "ref_state": ref_state,
        "at": _observation_at(rounds, f"{key[0]}:{key[1]}", obs),
    }
    for work, wait in members:
        holds = _holds(wait.wait_id, work["view"])
        item["works"].append(_work_piece(work, wait, holds))
    return item


def _unknown_record_item(key, members, obs, rounds, reason: str) -> dict:
    if reason not in REASONS:
        reason = "not_confirmed"
    item = {
        "source": "record",
        "ref": {"kind": key[0], "id": key[1]},
        "can_act": "unknown",
        "reason": reason,
        "where": "console",
        "reply_needed": False,
        "works": [],
    }
    if obs is not None and reason != "conflicting_observations":
        item["ref_state"] = obs["ref_state"]
        if "expires_at" in obs:
            item["deadline"] = obs["expires_at"]
            item["deadline_source"] = "record"
        if "number" in obs:
            item["number"] = obs["number"]
        item["last_seen"] = {
            "ref_state": obs["ref_state"],
            "at": _observation_at(rounds, f"{key[0]}:{key[1]}", obs),
        }
    for work, wait in members:
        holds = _holds(wait.wait_id, work["view"])
        item["works"].append(_work_piece(work, wait, holds))
    return item


def _ball(built: list, merged: dict, logs_unread: int, ghost: bool = False) -> dict:
    from model import UNKNOWN_WHY_ORDER

    judgments = []
    if logs_unread > 0:
        judgments.append({"holder": "unknown", "why": "fold_incomplete"})
    if ghost:
        judgments.append({"holder": "unknown", "why": "run_unrecorded"})
    for work in built:
        if work["public"].get("unrecorded_runs"):
            judgments.append({"holder": "unknown", "why": "run_unrecorded"})
            continue
        if work["closed"]:
            continue
        judgments.append(_judge_work(work, merged))
    if any(item["why"] == "fold_incomplete" for item in judgments):
        return {"holder": "unknown", "why": "fold_incomplete"}
    if any(item["holder"] == "agents" for item in judgments):
        return _pick(judgments, "agents", ("step_running", "record_created", "record_in_flight"))
    if any(item["holder"] == "unknown" for item in judgments):
        whys = {item["why"] for item in judgments if item["holder"] == "unknown"}
        for why in UNKNOWN_WHY_ORDER:
            if why in whys:
                return {"holder": "unknown", "why": why}
    if any(item["holder"] == "coordinator" for item in judgments):
        return _pick(judgments, "coordinator", ("next_not_sent", "owner_item_not_ready", "ended_awaiting_check"))
    if any(item["holder"] == "owner" for item in judgments):
        return _pick(judgments, "owner", ("owner_can_act",))
    ball = {"holder": "nobody", "why": "queue_done"}
    closed_at = [work["view"].closed_at for work in built if work["view"].closed_at is not None]
    if closed_at:
        ball["since"] = max(closed_at)
    return ball


def _pick(judgments: list, holder: str, order: tuple) -> dict:
    chosen = [item for item in judgments if item["holder"] == holder]
    why = next(code for code in order if any(item["why"] == code for item in chosen))
    times = [item["since"] for item in chosen if item["why"] == why and item.get("since") is not None]
    ball = {"holder": holder, "why": why}
    if times and holder != "unknown":
        ball["since"] = min(times)
    if holder == "owner" and all(item.get("basis") == "declared" for item in chosen if item["why"] == why):
        ball["basis"] = "declared"
    return ball


def _judge_work(work: dict, merged: dict) -> dict:
    view: View = work["view"]
    steps = work["public"]["steps"]
    flags = {step.step_id: flag for step, _public, flag in work["flags"]}

    def pack(holder, why, since, basis=None):
        item = {"holder": holder, "why": why}
        if since is not None:
            item["since"] = since
        if basis:
            item["basis"] = basis
        return item

    running = [step for step in steps if step["state"] in {"running", "slow", "quiet"}]
    if running:
        return pack("agents", "step_running", _running_since(view, running))
    created = [
        step for step in steps
        if flags.get(step["step_id"]) == "record_created" and step["state"] == "waiting"
    ]
    if created:
        return pack("agents", "record_created", _record_created_since(view, created))
    if _any_in_flight(view, merged):
        return pack("agents", "record_in_flight", _in_flight_since(view, merged))
    if any(step["state"] == "unknown" for step in steps):
        return pack("unknown", "step_unknown", None)
    if work["invalid"]:
        return pack("unknown", "log_invalid", None)
    if _any_owner_unknown(view, merged):
        return pack("unknown", "owner_item_unknown", None)
    nxt = _next_waiting(view, merged, steps)
    if nxt is not None:
        return pack("coordinator", "next_not_sent", nxt.declared_at)
    yes = _yes_waits(view, merged)
    if yes:
        basis = "declared" if all(item["declared"] for item in yes) else None
        return pack("owner", "owner_can_act", _owner_since(view, merged), basis)
    pending = _open_merged(view, merged)
    if pending and all(item["status"] == "not_yet" for item in pending):
        return pack("coordinator", "owner_item_not_ready", _not_yet_since(view, merged))
    return pack("coordinator", "ended_awaiting_check", _substantive(view))


def _substantive(view: View):
    """Latest valid event that is not a note and not a tail repair."""
    times = [event["at"] for event in view.valid if event["type"] not in {"note", "tail_repaired"}]
    return max(times) if times else None


def _streak_start(seen: list, states: set, key: str):
    """First sample of the current continuous run of ``states``. A repeat does not move it."""
    streak = []
    for obs in seen:
        if obs.get("ref_state") in states:
            streak.append(obs)
        else:
            streak = []
    if not streak or key not in streak[0]:
        return None
    return streak[0][key]


def _running_since(view: View, running: list):
    times = []
    for public in running:
        step = view.steps[public["step_id"]]
        if step.watch == "record":
            found = None
            for obs in step.record_obs:
                if obs.get("condition") in {"True", "False"}:
                    continue
                if "started_at" in obs:
                    found = obs["started_at"]
                    break
            if found is not None:
                times.append(found)
        elif step.started_at is not None:
            times.append(step.started_at)
    return min(times) if times else _substantive(view)


def _record_created_since(view: View, created: list):
    times = []
    for public in created:
        step = view.steps[public["step_id"]]
        streak = []
        for obs in step.record_obs:
            if obs.get("found") and "started_at" not in obs and "condition" not in obs:
                streak.append(obs)
            else:
                streak = []
        if streak:
            times.append(streak[0]["at"])
    return min(times) if times else _substantive(view)


def _in_flight_since(view: View, merged: dict):
    times = []
    for wait in view.waits.values():
        status = _wait_status(wait, merged, view.work_id)
        if status is None or status.get("status") != "in_flight":
            continue
        start = _streak_start(wait.seen, {"approved", "running"}, "sampled_at")
        if start is not None:
            times.append(start)
    return min(times) if times else _substantive(view)


def _owner_since(view: View, merged: dict):
    times = []
    for wait in view.waits.values():
        status = _wait_status(wait, merged, view.work_id)
        if status is None or status.get("status") != "yes":
            continue
        if status.get("declared"):
            times.append(wait.yes_at if wait.yes_at is not None else wait.opened_at)
            continue
        start = _streak_start(wait.seen, {"pending", "open", "unknown"}, "sampled_at")
        if start is not None:
            times.append(start)
    return max(times) if times else _substantive(view)


def _not_yet_since(view: View, merged: dict):
    times = []
    for wait in view.waits.values():
        status = _wait_status(wait, merged, view.work_id)
        if status and status.get("status") == "not_yet":
            times.append(wait.opened_at)
    return max(times) if times else _substantive(view)


def _wait_status(wait, merged: dict, work_id) -> dict | None:
    if wait.ref["kind"] == "none":
        return merged.get(("none", work_id, wait.wait_id))
    return merged.get((wait.ref["kind"], wait.ref["id"]))


def _any_in_flight(view: View, merged: dict) -> bool:
    for wait in view.waits.values():
        status = _wait_status(wait, merged, view.work_id)
        if status and status.get("status") == "in_flight":
            return True
    return False


def _any_owner_unknown(view: View, merged: dict) -> bool:
    for wait in view.waits.values():
        status = _wait_status(wait, merged, view.work_id)
        if status and status.get("status") == "unknown":
            return True
    return False


def _yes_waits(view: View, merged: dict) -> list:
    found = []
    for wait in view.waits.values():
        status = _wait_status(wait, merged, view.work_id)
        if status and status.get("status") == "yes":
            found.append(status)
    return found


def _open_merged(view: View, merged: dict) -> list:
    found = []
    for wait in view.waits.values():
        status = _wait_status(wait, merged, view.work_id)
        if status and status.get("status") in {"yes", "not_yet", "unknown", "in_flight"}:
            found.append(status)
    return found


def _next_waiting(view: View, merged: dict, steps: list):
    """The qualifying step whose declaration is the latest, or None."""
    by_id = {step["step_id"]: step for step in steps}
    chosen = None
    for step_id in view.step_order:
        step = view.steps[step_id]
        public = by_id.get(step_id)
        if public is None or public["state"] != "waiting":
            continue
        if step.waiting_on:
            settled = True
            for wait_id in step.waiting_on:
                wait = view.waits.get(wait_id)
                status = _wait_status(wait, merged, view.work_id) if wait is not None else None
                if status is None or status.get("status") != "settled":
                    settled = False
                    break
            if not settled:
                continue
        if step.after:
            target = by_id.get(step.after)
            if target is None or target["state"] not in {"done", "failed"}:
                continue
        if chosen is None or step.declared_at >= chosen.declared_at:
            chosen = step
    return chosen


