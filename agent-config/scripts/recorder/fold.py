"""``fold(logs, observer_log, now, logs_unread) -> document``.

Pure. The same inputs always give the same document. No file, no clock,
no network, and no earlier document. ``now`` is the caller's.
"""

from __future__ import annotations

import math

from model import (
    CLOCK_SKEW_S,
    GAP_S,
    OBS_VALID_S,
    QUIET_S,
    REASONS,
    SLOW_FACTOR,
)
from validate import View, classify

_CAN_ACT_ORDER = {"yes": 0, "unknown": 1, "not_yet": 2}


def fold(logs, observer_log, now, logs_unread=0) -> dict:
    if not _is_number(now):
        now = 0
    if not isinstance(logs_unread, int) or isinstance(logs_unread, bool) or logs_unread < 0:
        logs_unread = 0
    if not isinstance(logs, (list, tuple)):
        logs = []
    rounds = _rounds(observer_log)
    prepared = []
    for item in logs or []:
        prepared.append(_prepare(item))
    built = [_fold_one(item, rounds, now) for item in prepared]
    owner_all, merged = _owner_all(built, rounds, now)
    ball = _ball(built, merged, logs_unread)
    feed = []
    for work in built:
        feed.extend(work["feed"])
    clock_behind = any(
        work["max_at"] is not None and now < work["max_at"] - CLOCK_SKEW_S for work in built
    )
    document = {
        "at": now,
        "observations_valid_s": OBS_VALID_S,
        "fold_complete": logs_unread == 0,
        "logs_unread": logs_unread,
        "observer": {},
        "clock": {"reader_behind": clock_behind},
        "ball": ball,
        "owner_all": owner_all,
        "works": [work["public"] for work in built],
        "feed": feed,
    }
    if rounds:
        document["observer"] = {"last_round_at": rounds[-1]["ended_at"]}
    return document


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _prepare(item) -> dict:
    if isinstance(item, dict) and "events" in item:
        return {
            "work_id": item.get("work_id"),
            "events": list(item.get("events") or []),
            "invalid_at": item.get("invalid_at"),
            "full": bool(item.get("full")),
        }
    return {"work_id": None, "events": list(item or []), "invalid_at": None, "full": False}


def _rounds(observer_log) -> list:
    if isinstance(observer_log, dict) and "events" in observer_log:
        events = observer_log.get("events") or []
    elif isinstance(observer_log, (list, tuple)):
        events = list(observer_log)
    else:
        events = []
    view = classify(events, observer=True)
    rounds = list(view.rounds)
    rounds.sort(key=lambda event: (event["ended_at"], event.get("seq") or 0))
    return rounds


def _latest_round(rounds: list) -> dict | None:
    if not rounds:
        return None
    return rounds[-1]


def _confirm_reason(key: str, rounds: list, now: float) -> str | None:
    """None when the latest round confirms ``key`` and is fresh. Else a reason."""
    latest = _latest_round(rounds)
    if latest is None:
        return "not_confirmed"
    ended = latest["ended_at"]
    if ended > now + CLOCK_SKEW_S:
        return "reader_clock_behind"
    if now - ended > OBS_VALID_S:
        return "not_confirmed"
    for item in latest["failed"]:
        if item.get("key") == key:
            return item.get("error") or "not_confirmed"
    if key in latest["confirmed"]:
        return None
    return "not_confirmed"


def _fold_one(item: dict, rounds: list, now: float) -> dict:
    view = classify(item["events"], work_id=item["work_id"])
    invalid = item["invalid_at"]
    flags = []
    public_steps = []
    withdrawn = 0
    for step_id in view.step_order:
        step = view.steps[step_id]
        public, flag = _step_document(step, view, rounds, now, view.work_id or item["work_id"])
        if flag == "withdrawn":
            withdrawn += 1
            continue
        if invalid is not None and not view.closed and public["state"] not in {"done", "failed"}:
            public = _as_invalid(public)
            flag = "invalid"
        public_steps.append(public)
        flags.append((step, public, flag))
    eta_unsure = _eta_unsure(public_steps)
    public = _work_public(view, item, public_steps, withdrawn, eta_unsure, invalid)
    feed = _feed(view, item, public["work_id"])
    return {
        "public": public,
        "view": view,
        "flags": flags,
        "feed": feed,
        "max_at": view.max_at,
        "invalid": invalid is not None and not view.closed,
        "closed": view.closed,
    }


def _as_invalid(step: dict) -> dict:
    kept = {
        "step_id": step["step_id"],
        "name": step["name"],
        "who": step["who"],
        "kind": step["kind"],
        "watch": step["watch"],
        "state": "unknown",
        "reason": "log_invalid",
        "label": "Unknown",
    }
    for key in ("command", "last_seen", "round", "note", "superseded_by", "superseded_text"):
        if key in step:
            kept[key] = step[key]
    return kept


def _eta_unsure(steps: list) -> bool:
    for step in steps:
        state = step["state"]
        if state in {"quiet", "unknown", "dead", "failed"}:
            return True
        if state not in {"done", "failed"} and "usual_s" not in step:
            return True
    return False


def _work_public(view: View, item: dict, steps: list, withdrawn: int, eta_unsure: bool, invalid) -> dict:
    work_id = view.work_id or item["work_id"] or ""
    public = {
        "work_id": work_id,
        "source": "events",
        "steps": steps,
        "defects": list(view.defects),
        "withdrawn": withdrawn,
    }
    if view.title is not None:
        public["title"] = view.title
    if view.goal is not None:
        public["goal"] = view.goal
    if view.work_ref is not None:
        public["work_ref"] = view.work_ref
    if view.closed:
        public["closed_claim"] = view.closed_claim
    if invalid is not None:
        public["log_invalid_at"] = invalid
    if item["full"]:
        public["log_full"] = True
    if eta_unsure:
        public["eta_unsure"] = True
    if view.max_at is not None:
        public["last_at"] = view.max_at
    return public


def _feed(view: View, item: dict, work_id: str) -> list:
    rows = []
    for event in view.notes:
        rows.append(_feed_row(
            event["at"],
            work_id,
            event.get("step_id") or "",
            event.get("by") or "",
            "",
            event["text"],
        ))
    for event in view.valid:
        if event["type"] != "owner_wait_closed":
            continue
        wait = view.waits.get(event["wait_id"])
        if wait is None:
            continue
        rows.append(_feed_row(event["at"], work_id, "", event.get("by") or "", event["how"], wait.title))
        continue
    for wait in view.waits.values():
        if wait.terminal_state is None:
            continue
        for event in reversed(wait.seen):
            if event.get("ref_state") == wait.terminal_state:
                rows.append(_feed_row(
                    event["at"], work_id, "", event.get("by") or "", event["ref_state"], wait.title,
                ))
                break
    rows.sort(key=lambda row: (row["at"], row["text"]))
    return rows


def _feed_row(at, work, step, who, state, text) -> dict:
    return {"at": at, "work": work, "step": step, "who": who, "state": state, "text": text}


def _step_document(step, view: View, rounds, now, work_id):
    if step.watch == "record":
        return _record_step(step, view, rounds, now, work_id)
    return _watched_step(step, view, now)


def _base(step) -> dict:
    public = {
        "step_id": step.step_id,
        "name": step.name,
        "who": step.who,
        "kind": step.kind,
        "watch": step.watch,
    }
    if step.round is not None:
        public["round"] = step.round
    if step.usual_s is not None:
        public["usual_s"] = step.usual_s
    if step.command is not None:
        public["command"] = step.command
    if step.note is not None:
        public["note"] = step.note
    if step.quote is not None:
        public["quote"] = step.quote
    if step.superseded and step.by_step:
        public["superseded_by"] = step.by_step
    if step.superseded_text is not None:
        public["superseded_text"] = step.superseded_text
    if step.output_large:
        public["output_large"] = True
    return public


def _last_seen_process(step) -> dict | None:
    if step.seen:
        last = step.seen[-1]
        seen = {"alive": last["alive"], "at": last["sampled_at"]}
        if "output_bytes" in last:
            seen["output_bytes"] = last["output_bytes"]
        return seen
    if step.started:
        return {"started": True, "at": step.started_at}
    return None


def _finish(step, public: dict):
    event = step.finished
    public["ended"] = event["at"]
    if step.dead:
        public["was_seen_dead"] = True
    if step.watch == "none":
        if event["reported"] == "finished":
            public["state"] = "done"
            public["ended_how"] = "reported"
            public["label"] = "Reported finished by coordinator"
        else:
            public["state"] = "failed"
            public["reason"] = "reported_failed"
        return public, "ended"
    exit_body = event["exit"]
    if "signal" in exit_body and exit_body.get("signal"):
        public["state"] = "failed"
        public["reason"] = "ended_by_signal"
        public["signal"] = exit_body["signal"]
    elif exit_body.get("code") == 0:
        public["state"] = "done"
        public["ended_how"] = "exit_0"
        public["label"] = "Exited 0"
    else:
        public["state"] = "failed"
        public["reason"] = "exited_nonzero"
        public["exit_code"] = exit_body.get("code")
    return public, "ended"


def _gap(step) -> bool:
    if not step.started:
        return False
    times = [step.started_at]
    times.extend(obs["sampled_at"] for obs in step.seen)
    return any(later - earlier > GAP_S for earlier, later in zip(times, times[1:]))


def _silence_from(step):
    """When the silent interval starts, or None when quiet cannot apply."""
    previous = None
    grew_at = None
    saw_output = False
    for obs in step.seen:
        if "output_bytes" not in obs:
            continue
        saw_output = True
        size = obs["output_bytes"]
        if previous is None:
            if size > 0:
                grew_at = obs["sampled_at"]
        elif size > previous:
            grew_at = obs["sampled_at"]
        previous = size
    if not saw_output:
        return None
    if grew_at is None:
        return step.started_at
    return grew_at


def _watched_step(step, view: View, now: float):
    public = _base(step)
    if step.ended:
        if step.started_at is not None:
            public["started"] = step.started_at
        return _finish(step, public)
    if step.superseded and not step.by_step and not step.started:
        return public, "withdrawn"
    if not step.started:
        public["state"] = "waiting"
        return public, "waiting"
    if step.started_at is not None:
        public["started"] = step.started_at
    seen = _last_seen_process(step)
    if seen is not None:
        public["last_seen"] = seen
    if step.dead:
        public["state"] = "dead"
        public["reason"] = "wrapper_gone"
        if step.seen:
            public["since"] = step.seen[-1]["sampled_at"]
        return public, "dead"
    if step.watch == "none":
        return _timed(public, step, now, gap=False, none=True)
    behind = view.max_at is not None and now < view.max_at - CLOCK_SKEW_S
    ref_index = step.last_seen_index if step.last_seen_index is not None else step.start_index
    ref_time = step.last_sampled if step.seen else step.started_at
    if behind:
        return _unknown(public, "reader_clock_behind")
    if ref_index is not None and ref_index in view.backwards:
        return _unknown(public, "clock_backwards")
    if ref_time is not None and now - ref_time > OBS_VALID_S:
        return _unknown(public, "no_observation")
    silent_from = _silence_from(step)
    if silent_from is not None and now - silent_from > QUIET_S:
        public["state"] = "quiet"
        public["reason"] = "no_output"
        public["silent_s"] = now - silent_from
        return public, "quiet"
    return _timed(public, step, now, gap=_gap(step), none=False)


def _timed(public, step, now, gap: bool, none: bool):
    if gap:
        public["gap"] = True
    if (
        step.usual_s is not None
        and step.started_at is not None
        and not gap
        and now - step.started_at > SLOW_FACTOR * step.usual_s
    ):
        public["state"] = "slow"
        public["overdue"] = (now - step.started_at) - step.usual_s
        public["eta_end"] = step.started_at + step.usual_s
        return public, "slow"
    public["state"] = "running"
    if none:
        public["started_how"] = "reported"
        public["label"] = "Reported started, not watched"
    if step.usual_s is not None and step.started_at is not None:
        public["eta_end"] = step.started_at + step.usual_s
    return public, "running"


def _unknown(public, reason, row=None):
    public["state"] = "unknown"
    public["reason"] = reason
    public["label"] = "Unknown"
    return public, row or "unknown"


def _record_step(step, view: View, rounds, now, work_id):
    public = _base(step)
    true = next((obs for obs in step.record_obs if obs.get("condition") == "True"), None)
    false = next((obs for obs in step.record_obs if obs.get("condition") == "False"), None)
    if true is not None:
        public["state"] = "done"
        public["ended_how"] = "record"
        public["label"] = "Record: Succeeded"
        if "ended_at" in true:
            public["ended"] = true["ended_at"]
        if "started_at" in true:
            public["started"] = true["started_at"]
        if true.get("reason_quote"):
            public["reason_quote"] = true["reason_quote"]
        return public, "ended"
    if false is not None:
        public["state"] = "failed"
        public["reason"] = "record_failed"
        if "ended_at" in false:
            public["ended"] = false["ended_at"]
        if "started_at" in false:
            public["started"] = false["started_at"]
        if false.get("reason_quote"):
            public["reason_quote"] = false["reason_quote"]
        return public, "ended"
    if step.superseded and not step.by_step and not step.ever_found:
        return public, "withdrawn"
    locator = step.locator or {}
    if "name" not in locator:
        public["state"] = "waiting"
        return public, "waiting"
    key = f"step:{work_id}/{step.step_id}"
    reason = _confirm_reason(key, rounds, now)
    last = _record_last_seen(step, rounds)
    if reason is not None:
        if last is not None:
            public["last_seen"] = last
        return _unknown(public, reason)
    latest = step.record_obs[-1] if step.record_obs else None
    if latest is None or latest.get("found") is False:
        if _waiting_on_open(step, view):
            public["state"] = "waiting"
            return public, "waiting"
        if last is not None:
            public["last_seen"] = last
        return _unknown(public, "no_match")
    if "started_at" not in latest:
        public["state"] = "waiting"
        return public, "record_created"
    public["started"] = latest["started_at"]
    if step.usual_s is not None and now - latest["started_at"] > SLOW_FACTOR * step.usual_s:
        public["state"] = "slow"
        public["overdue"] = (now - latest["started_at"]) - step.usual_s
        public["eta_end"] = latest["started_at"] + step.usual_s
        return public, "slow"
    public["state"] = "running"
    if step.usual_s is not None:
        public["eta_end"] = latest["started_at"] + step.usual_s
    return public, "running"


def _record_last_seen(step, rounds) -> dict | None:
    if not step.record_obs:
        return None
    latest = step.record_obs[-1]
    latest_round = _latest_round(rounds)
    at = latest_round["ended_at"] if latest_round is not None else latest["sampled_at"]
    if "condition" in latest:
        ref_state = latest["condition"]
    elif latest.get("found") is False:
        ref_state = "not_found"
    else:
        ref_state = "found"
    return {"ref_state": ref_state, "at": at}


def _waiting_on_open(step, view: View) -> bool:
    if not step.waiting_on:
        return False
    for wait_id in step.waiting_on:
        wait = view.waits.get(wait_id)
        if wait is not None and not wait.settled:
            return True
    return False


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
                if wait.settled:
                    merged[( "none", wait.wait_id)] = {"status": "settled", "declared": True}
                    continue
                item = _declared_item(wait, view, work)
                items.append(item)
                merged[("none", wait.wait_id)] = {
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
    ident = item.get("wait_id") or (item.get("ref") or {}).get("id") or ""
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
            observations.append((obs["sampled_at"], obs.get("seq") or 0, obs, work, wait))
    reason = _confirm_reason(f"{key[0]}:{key[1]}", rounds, now)
    if not observations or reason is not None:
        item = _unknown_record_item(key, open_members, observations, rounds, reason or "not_confirmed")
        return {"status": "unknown", "declared": False, "can_act": "unknown", "reason": item["reason"]}, item
    observations.sort(key=lambda row: (row[0], row[1]))
    latest_at = observations[-1][0]
    latest = [row for row in observations if row[0] == latest_at]
    states = {row[2]["ref_state"] for row in latest}
    if len(states) > 1:
        item = _unknown_record_item(key, open_members, observations, rounds, "conflicting_observations")
        return {
            "status": "unknown",
            "declared": False,
            "can_act": "unknown",
            "reason": "conflicting_observations",
        }, item
    obs = latest[-1][2]
    state = obs["ref_state"]
    if state in {"approved", "running"}:
        return {"status": "in_flight", "declared": False, "ref_state": state}, None
    if state in {"pending", "open", "unknown"}:
        item = _yes_record_item(key, open_members, obs, rounds)
        return {"status": "yes", "declared": False, "can_act": "yes", "ref_state": state}, item
    item = _unknown_record_item(key, open_members, observations, rounds, "not_confirmed")
    return {"status": "unknown", "declared": False, "can_act": "unknown"}, item


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
    latest_round = _latest_round(rounds)
    if latest_round is not None:
        item["last_seen"] = {"ref_state": ref_state, "at": latest_round["ended_at"]}
    for work, wait in members:
        holds = _holds(wait.wait_id, work["view"])
        item["works"].append(_work_piece(work, wait, holds))
    return item


def _unknown_record_item(key, members, observations, rounds, reason: str) -> dict:
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
    if observations and reason != "conflicting_observations":
        observations.sort(key=lambda row: (row[0], row[1]))
        obs = observations[-1][2]
        item["ref_state"] = obs["ref_state"]
        if "expires_at" in obs:
            item["deadline"] = obs["expires_at"]
            item["deadline_source"] = "record"
        if "number" in obs:
            item["number"] = obs["number"]
        latest_round = _latest_round(rounds)
        at = latest_round["ended_at"] if latest_round is not None else obs["sampled_at"]
        item["last_seen"] = {"ref_state": obs["ref_state"], "at": at}
    for work, wait in members:
        holds = _holds(wait.wait_id, work["view"])
        item["works"].append(_work_piece(work, wait, holds))
    return item


def _ball(built: list, merged: dict, logs_unread: int) -> dict:
    if logs_unread > 0:
        ball = {"holder": "unknown", "why": "fold_incomplete"}
        times = [work["max_at"] for work in built if work["max_at"] is not None]
        if times:
            ball["since"] = max(times)
        return ball
    judgments = []
    for work in built:
        if work["closed"]:
            continue
        judgments.append(_judge_work(work, merged))
    if any(item["holder"] == "agents" for item in judgments):
        return _pick(judgments, "agents")
    if any(item["holder"] == "unknown" for item in judgments):
        return _pick(judgments, "unknown")
    if any(item["holder"] == "coordinator" for item in judgments):
        return _pick(judgments, "coordinator")
    if any(item["holder"] == "owner" for item in judgments):
        return _pick(judgments, "owner")
    ball = {"holder": "nobody", "why": "queue_done"}
    closed_at = [work["view"].closed_at for work in built if work["view"].closed_at is not None]
    if closed_at:
        ball["since"] = max(closed_at)
    return ball


def _pick(judgments: list, holder: str) -> dict:
    chosen = [item for item in judgments if item["holder"] == holder]
    chosen.sort(key=lambda item: item.get("since") or -1)
    best = chosen[-1]
    ball = {"holder": holder, "why": best["why"]}
    if "since" in best:
        ball["since"] = best["since"]
    if holder == "owner" and all(item.get("basis") == "declared" for item in chosen):
        ball["basis"] = "declared"
    return ball


def _judge_work(work: dict, merged: dict) -> dict:
    view: View = work["view"]
    since = view.max_at
    steps = work["public"]["steps"]
    flags = {step.step_id: flag for step, _public, flag in work["flags"]}

    def pack(holder, why, basis=None):
        item = {"holder": holder, "why": why}
        if since is not None:
            item["since"] = since
        if basis:
            item["basis"] = basis
        return item

    if any(step["state"] in {"running", "slow", "quiet"} for step in steps):
        return pack("agents", "step_running")
    if any(flags.get(step["step_id"]) == "record_created" and step["state"] == "waiting" for step in steps):
        return pack("agents", "record_created")
    if _any_in_flight(view, merged):
        return pack("agents", "record_in_flight")
    if work["invalid"]:
        return pack("unknown", "log_invalid")
    if any(step["state"] == "unknown" for step in steps):
        return pack("unknown", "step_unknown")
    if _any_owner_unknown(view, merged):
        return pack("unknown", "owner_item_unknown")
    if _next_not_sent(view, merged, steps):
        return pack("coordinator", "next_not_sent")
    yes = _yes_waits(view, merged)
    if yes:
        basis = "declared" if all(item["declared"] for item in yes) else None
        return pack("owner", "owner_can_act", basis)
    pending = _open_merged(view, merged)
    if pending and all(item["status"] == "not_yet" for item in pending):
        return pack("coordinator", "owner_item_not_ready")
    return pack("coordinator", "ended_awaiting_check")


def _wait_status(wait, merged: dict) -> dict | None:
    if wait.ref["kind"] == "none":
        return merged.get(("none", wait.wait_id))
    return merged.get((wait.ref["kind"], wait.ref["id"]))


def _any_in_flight(view: View, merged: dict) -> bool:
    for wait in view.waits.values():
        status = _wait_status(wait, merged)
        if status and status.get("status") == "in_flight":
            return True
    return False


def _any_owner_unknown(view: View, merged: dict) -> bool:
    for wait in view.waits.values():
        status = _wait_status(wait, merged)
        if status and status.get("status") == "unknown":
            return True
    return False


def _yes_waits(view: View, merged: dict) -> list:
    found = []
    for wait in view.waits.values():
        status = _wait_status(wait, merged)
        if status and status.get("status") == "yes":
            found.append(status)
    return found


def _open_merged(view: View, merged: dict) -> list:
    found = []
    for wait in view.waits.values():
        status = _wait_status(wait, merged)
        if status and status.get("status") in {"yes", "not_yet", "unknown", "in_flight"}:
            found.append(status)
    return found


def _next_not_sent(view: View, merged: dict, steps: list) -> bool:
    by_id = {step["step_id"]: step for step in steps}
    for step_id in view.step_order:
        step = view.steps[step_id]
        public = by_id.get(step_id)
        if public is None or public["state"] != "waiting":
            continue
        if step.waiting_on:
            settled = True
            for wait_id in step.waiting_on:
                wait = view.waits.get(wait_id)
                status = _wait_status(wait, merged) if wait is not None else None
                if status is None or status.get("status") != "settled":
                    settled = False
                    break
            if not settled:
                continue
        if step.after:
            target = by_id.get(step.after)
            if target is None or target["state"] not in {"done", "failed"}:
                continue
        return True
    return False


def select_logs(items: list, limit: int = 200) -> tuple[list, int]:
    """Keep the newest ``limit`` logs by mtime. The rest is ``logs_unread``.

    ``items`` are ``(mtime, log)``. This is the caller's cut, not part of
    ``fold``: the fold only receives the number it was not given.
    """
    if len(items) <= limit:
        return list(items), 0
    ordered = sorted(items, key=lambda item: item[0], reverse=True)
    return ordered[:limit], len(items) - limit
