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


def fold(logs, observer_files, now, logs_unread=0, unread_names=None, files_unread=0) -> dict:
    from ownerball import _ball, _owner_all
    rounds = []
    observer_defects = []
    observer_break = None
    for loaded in observer_files or []:
        rounds.extend(loaded.view.rounds)
        for item in loaded.defects:
            observer_defects.append({"file": item.get("file", loaded.name), "seq": item["seq"], "reason": item["reason"]})
        if loaded.broken_line is not None and observer_break is None:
            observer_break = {"file": loaded.name, "line": loaded.broken_line, "why": loaded.broken_why}
    built = [_fold_one(item, rounds, now) for item in logs or []]
    ghost = _apply_unrecorded(built, rounds, now)
    built.sort(key=lambda work: work["public"]["work_id"])
    owner_all, merged = _owner_all(built, rounds, now)
    ball = _ball(built, merged, logs_unread, ghost)
    feed = []
    for work in built:
        feed.extend(work["feed"])
    feed.sort(key=lambda row: (row["at"], row["work"], row["step"], row["text"], row["who"], row["state"]))
    clock_behind = any(
        work["max_at"] is not None and now < work["max_at"] - CLOCK_SKEW_S for work in built
    )
    incomplete = logs_unread > 0 or any(
        (not work["closed"]) and (
            work["public"].get("log_invalid_at") is not None or work["public"].get("torn_tail")
        )
        for work in built
    )
    observer = {}
    if rounds:
        observer["last_round_at"] = rounds[-1]["ended_at"]
    if observer_defects:
        observer["defects"] = observer_defects
    if observer_break is not None:
        observer["log_invalid_at"] = observer_break
    if files_unread:
        observer["files_unread"] = files_unread
    document = {
        "at": now,
        "observations_valid_s": OBS_VALID_S,
        "fold_complete": not incomplete,
        "logs_unread": logs_unread,
        "internal_errors": 0,
        "observer": observer,
        "clock": {"reader_behind": clock_behind},
        "ball": ball,
        "owner_all": owner_all,
        "works": [work["public"] for work in built],
        "feed": feed,
    }
    if unread_names:
        document["logs_unread_names"] = list(unread_names)
    return document


def _apply_unrecorded(built, rounds, now) -> bool:
    """Table A-2. Returns whether an item named a work that was not read."""
    if not rounds:
        return False
    latest = rounds[-1]
    if now - latest["ended_at"] > OBS_VALID_S:
        return False
    by_id = {work["public"]["work_id"]: work for work in built}
    ghost = False
    for item in latest.get("unrecorded") or []:
        work = by_id.get(item["work_id"])
        if work is None:
            ghost = True
            continue
        public = next((step for step in work["public"]["steps"] if step["step_id"] == item["step_id"]), None)
        view_step = work["view"].steps.get(item["step_id"])
        open_states = {"running", "slow", "quiet", "unknown"}
        recorded = (
            view_step is not None
            and view_step.started
            and view_step.run_id == item["run_id"]
            and public is not None
            and public.get("state") in open_states
        )
        if recorded:
            continue
        work["public"]["unrecorded_runs"] = work["public"].get("unrecorded_runs", 0) + 1
        if (
            public is not None
            and view_step is not None
            and view_step.declared_by == "wrapper"
            and not view_step.started
            and public.get("reason") == "start_not_recorded"
        ):
            public["last_seen"] = {"alive": True, "at": latest["ended_at"]}
    return ghost


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
    return list(view.rounds)


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


def _fold_one(loaded, rounds, now) -> dict:
    view = loaded.view
    invalid = loaded.broken_line
    flags = []
    public_steps = []
    withdrawn = 0
    for step_id in view.step_order:
        step = view.steps[step_id]
        public, flag = _step_document(step, view, rounds, now, view.work_id or loaded.name)
        if flag == "withdrawn":
            withdrawn += 1
            continue
        if invalid is not None and not view.closed and public["state"] not in {"done", "failed"}:
            public = _as_invalid(public)
            flag = "invalid"
        public_steps.append(public)
        flags.append((step, public, flag))
    eta_unsure = _eta_unsure(public_steps)
    public = _work_public(view, loaded, public_steps, withdrawn, eta_unsure, invalid)
    feed = _feed(view, loaded, public["work_id"])
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


def _work_public(view: View, loaded, steps: list, withdrawn: int, eta_unsure: bool, invalid) -> dict:
    work_id = view.work_id or loaded.name or ""
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
    if view.closed_at is not None:
        public["_closed_at"] = view.closed_at
    if invalid is not None:
        public["log_invalid_at"] = invalid
        if loaded.broken_why:
            public["log_invalid_why"] = loaded.broken_why
    if loaded.torn_tail:
        public["torn_tail"] = True
    if loaded.full:
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
    if step.superseded and not step.started:
        return public, "withdrawn"
    if not step.started:
        if step.watch == "process" and step.declared_by == "wrapper":
            public["state"] = "unknown"
            public["reason"] = "start_not_recorded"
            public["label"] = "Unknown"
            return public, "unknown"
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
    if step.superseded and not step.ever_found:
        return public, "withdrawn"
    locator = step.locator or {}
    if "name" not in locator:
        public["state"] = "waiting"
        return public, "waiting"
    key = f"step:{work_id}/{step.step_id}"
    reason = _confirm_reason(key, rounds, now)
    last = _record_last_seen(step, rounds, work_id)
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


def _last_confirmed_at(rounds, key: str):
    """ended_at of the last appended round whose confirmed list contains key."""
    found = None
    for event in rounds:
        confirmed = event.get("confirmed") or []
        if key in confirmed:
            found = event["ended_at"]
    return found


def _observation_at(rounds, key: str, obs: dict):
    confirmed = _last_confirmed_at(rounds, key)
    if confirmed is not None:
        return confirmed
    return obs["sampled_at"]


def _record_last_seen(step, rounds, work_id) -> dict | None:
    if not step.record_obs:
        return None
    latest = step.record_obs[-1]
    at = _observation_at(rounds, f"step:{work_id}/{step.step_id}", latest)
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


def select_logs(items: list, limit: int = 200) -> tuple[list, int]:
    """Keep the newest ``limit`` logs by mtime. The rest is ``logs_unread``.

    ``items`` are ``(mtime, log)``. This is the caller's cut, not part of
    ``fold``: the fold only receives the number it was not given.
    """
    if len(items) <= limit:
        return list(items), 0
    ordered = sorted(items, key=lambda item: item[0], reverse=True)
    return ordered[:limit], len(items) - limit
