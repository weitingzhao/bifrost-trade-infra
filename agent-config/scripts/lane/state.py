"""lane_state: one function of events, evidence and whether a driver holds run.lock."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from decide import RoundEvidence, StepView, decide
from events import Log, load_file
from evidence import assess_attempt
from query import (
    CLOSING_KINDS,
    PROGRESS_NAME,
    STEPS,
    abandoned_event,
    closing_resolutions,
    confirmed_ids,
    created,
    current_round,
    events_for_step,
    exec_of,
    max_rounds,
    opened_count,
    rejected_sets,
    resolutions,
    verdict_event,
)
from table import settle


def _parse_time(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _read_abandoned(lane_dir: Path) -> dict | None:
    path = lane_dir / "abandoned.json"
    if not path.is_file():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"present": True}
    return obj if isinstance(obj, dict) else {"present": True}


def inspect_lane(lane_dir: Path, *, driver: bool = False, now: datetime | None = None, log: Log | None = None) -> dict:
    if log is None:
        log = load_file(lane_dir / "events.jsonl")
    assessed: dict[str, dict] = {}
    intents = {}
    for event in log.events:
        if event.get("type") == "step_intent":
            intents[exec_of(event).get("attempt_id")] = event
    for event in log.events:
        if event.get("type") != "step_recorded":
            continue
        attempt = exec_of(event).get("attempt_id")
        assessed[attempt] = assess_attempt(lane_dir, intents.get(attempt), event)
    view = lane_state(
        log.events,
        assessed,
        driver,
        log.invalid_seq,
        log.last_valid_seq,
        _read_abandoned(lane_dir),
        now if now is not None else datetime.now(timezone.utc),
    )
    if log.events and log.digests:
        view["events_head"] = {"seq": log.events[-1]["seq"], "sha256": log.digests[-1]}
    return view


def lane_state(events, assessed, driver: bool, invalid_seq, last_valid_seq, abandoned_json, now) -> dict:
    info = created(events) or {}
    rnd = current_round(events)
    view = {
        "title": info.get("title") or "",
        "lane_id": info.get("lane_id"),
        "budget_max": max_rounds(events),
        "opened": opened_count(events),
        "round": rnd,
        "marker": None,
        "busy": None,
        "notes": [],
        "next_step": None,
        "overdue": False,
        "unconfirmed": [],
        "verdict_result": None,
        "pending_result": None,
        "decide_result": None,
        "decide_reason": None,
        "sha_set": {},
        "manifest_shas": {},
        "step": None,
        "attempt": None,
        "recorded": False,
        "exit_code": None,
        "has_verdict": False,
        "resolved_kind": None,
        "since": events[-1].get("at") if events else None,
        "targets": info.get("repos") or {},
        "driver": bool(driver),
        "attempts": {},
        "problem_attempt": None,
        "config_sha256": info.get("config_sha256"),
        "evidence_problems": _collect_problems(events, assessed, rnd),
        "verdict_seq": None,
        "events_head": None,
    }
    view["attempts"] = _index_attempts(events, assessed)
    view["unconfirmed"] = [
        aid for aid, item in view["attempts"].items() if not item["recorded"] and not item["confirmed"]
    ]
    if abandoned_event(events) is not None or abandoned_json is not None:
        view["state"] = "abandoned"
        view["display"] = "abandoned"
        view["reason"] = None
        if invalid_seq is not None:
            view["marker"] = f"event log invalid after seq {last_valid_seq or 0}"
        return view
    if invalid_seq is not None:
        view["state"] = "unknown"
        view["display"] = "unknown"
        view["reason"] = f"event log invalid at seq {invalid_seq}"
        return view
    if rnd is None:
        view["state"] = "unknown"
        view["display"] = "unknown"
        view["reason"] = "event log invalid at seq 1"
        return view
    evidence = _round_evidence(events, assessed, rnd, view["targets"])
    result, reason = decide(evidence)
    view["decide_result"] = result
    view["decide_reason"] = reason
    view["sha_set"] = _pinned_event(events, rnd)
    view["manifest_shas"] = _manifest_shas(events, rnd)
    view["notes"] = _notes(events, assessed, rnd)
    _mark_problem(view, rnd)
    verdict = verdict_event(events, rnd)
    if verdict is not None:
        view["has_verdict"] = True
        view["verdict_result"] = verdict.get("result")
        view["verdict_seq"] = verdict.get("seq")
        view["reason"] = verdict.get("reason")
        state = settle(verdict.get("result") or "step_failed", view["opened"], view["budget_max"])
        view["state"] = state
        view["display"] = state
        return view
    open_step = _open_step(view, rnd)
    view["overdue"] = _overdue(events, open_step[1] if open_step else None, now)
    if driver:
        if open_step is not None:
            _progress(view, open_step[0], open_step[1])
            return view
        last = _last_recorded_name(events, rnd)
        if last is not None:
            _progress(view, last, _attempt_for(events, rnd, last))
            return view
    if open_step is not None:
        view["state"] = result if result in ("unknown", "start_ambiguous") else "unknown"
        view["display"] = view["state"]
        view["reason"] = reason
        view["step"] = open_step[0]
        view["attempt"] = open_step[1]
        return view
    if result == "continue":
        view["state"] = "ready"
        view["display"] = "ready"
        view["reason"] = None
        view["next_step"] = _next_missing(events, rnd)
        return view
    if result in ("unknown", "start_ambiguous"):
        view["state"] = result
        view["display"] = result
        view["reason"] = reason
        return view
    view["state"] = "verdict_pending"
    view["pending_result"] = result
    view["reason"] = reason
    view["display"] = f"verdict_pending ({result})"
    return view


def _progress(view: dict, step: str, attempt: str | None) -> None:
    state = PROGRESS_NAME[step]
    view["state"] = state
    view["display"] = state
    view["reason"] = None
    view["step"] = step
    view["attempt"] = attempt


def _index_attempts(events: list[dict], assessed: dict) -> dict:
    intents: dict[str, dict] = {}
    recorded: dict[str, dict] = {}
    started: set[str] = set()
    for event in events:
        kind = event.get("type")
        attempt = exec_of(event).get("attempt_id")
        if not attempt:
            continue
        if kind == "step_intent":
            intents[attempt] = event
        elif kind == "step_recorded":
            recorded[attempt] = event
        elif kind == "step_started":
            started.add(attempt)
    resolved = {}
    for event in events:
        if event.get("type") == "resolution" and event.get("kind") in CLOSING_KINDS:
            resolved[event.get("attempt_id")] = event.get("kind")
    confirmed = confirmed_ids(events)
    out = {}
    for attempt, intent in intents.items():
        rec = recorded.get(attempt)
        exit_body = (rec or {}).get("exit") or {}
        problems = (assessed.get(attempt) or {}).get("problems") or []
        out[attempt] = {
            "step": exec_of(intent).get("step"),
            "round": int(exec_of(intent).get("round", 0)),
            "recorded": rec is not None,
            "exit_code": exit_body.get("code") if rec else None,
            "exit_signal": exit_body.get("signal") if rec else None,
            "resolved_kind": resolved.get(attempt),
            "confirmed": attempt in confirmed,
            "open": rec is None and attempt not in resolved,
            "invalid": bool(problems),
            "started": attempt in started,
        }
    return out


def _mark_problem(view: dict, rnd: int) -> None:
    attempts = view["attempts"]
    open_ids = [aid for aid, item in attempts.items() if item["open"] and item["round"] == rnd]
    invalid_ids = [
        aid
        for aid, item in attempts.items()
        if item["invalid"] and item["round"] == rnd and not item["resolved_kind"] and item["recorded"]
    ]
    chosen = open_ids[0] if open_ids else (invalid_ids[0] if invalid_ids else None)
    view["problem_attempt"] = chosen
    if chosen is None:
        return
    item = attempts[chosen]
    view["step"] = item["step"]
    view["attempt"] = chosen
    view["recorded"] = item["recorded"]
    view["exit_code"] = item["exit_code"]
    view["resolved_kind"] = item["resolved_kind"]


def _open_step(view: dict, rnd: int) -> tuple[str, str] | None:
    for aid, item in view["attempts"].items():
        if item["open"] and item["round"] == rnd:
            return item["step"], aid
    return None


def _round_evidence(events, assessed, rnd: int, targets: dict) -> RoundEvidence:
    steps = {}
    for name in STEPS:
        grouped = events_for_step(events, rnd, name)
        intent = grouped["step_intent"][0] if grouped["step_intent"] else None
        started = grouped["step_started"][0] if grouped["step_started"] else None
        recorded = grouped["step_recorded"][0] if grouped["step_recorded"] else None
        steps[name] = _step_view(name, intent, started, recorded, assessed)
    rows = []
    for row in resolutions(events, rnd):
        rows.append(
            {
                "step": row.get("step"),
                "kind": row.get("kind"),
                "operator": row.get("operator"),
                "reason": row.get("reason"),
                "attempt_id": row.get("attempt_id"),
            }
        )
    return RoundEvidence(
        round_no=rnd,
        steps=steps,
        targets=targets,
        rejected=tuple(rejected_sets(events)),
        resolutions=tuple(rows),
    )


def _step_view(name, intent, started, recorded, assessed) -> StepView:
    if intent is None or recorded is None and _closed(recorded, intent, assessed):
        if intent is None:
            return StepView(name=name)
    if recorded is None:
        return StepView(name=name, presence="absent", started=started is not None)
    attempt = exec_of(recorded).get("attempt_id")
    assessed_row = assessed.get(attempt) or {"problems": ["manifest missing"], "manifest": None}
    rejects = recorded.get("rejects") is True
    problems = assessed_row.get("problems") or []
    manifest = assessed_row.get("manifest")
    if problems or manifest is None:
        return StepView(name=name, presence="invalid", invalid_which=(problems or ["manifest missing"])[0], rejects=rejects, started=True)
    if manifest.get("not_started") is not None:
        return StepView(
            name=name,
            presence="not_started",
            started=True,
            not_started=manifest.get("not_started"),
            rejects=rejects,
        )
    outputs = manifest.get("outputs") or {}
    return StepView(
        name=name,
        presence="ran",
        started=True,
        exit=manifest.get("exit"),
        termination=manifest.get("termination"),
        checks=manifest.get("checks") or {},
        fields=manifest.get("fields") or {},
        pinned=manifest.get("pinned"),
        bundles=manifest.get("bundles"),
        consumed=manifest.get("consumed"),
        notes=tuple(manifest.get("notes") or ()),
        rejects=rejects,
        report=outputs.get("report"),
    )


def _closed(recorded, intent, assessed) -> bool:
    return False


def _pinned_event(events, rnd: int) -> dict:
    for event in events:
        if event.get("type") != "step_recorded":
            continue
        body = exec_of(event)
        if int(body.get("round", -1)) == rnd and body.get("step") == "implement":
            return event.get("pinned") or {}
    return {}


def _manifest_shas(events, rnd: int) -> dict:
    found = {}
    for event in events:
        if event.get("type") != "step_recorded":
            continue
        body = exec_of(event)
        if int(body.get("round", -1)) == rnd:
            found[body.get("step")] = event.get("manifest_sha256")
    return found


def _notes(events, assessed, rnd: int) -> list:
    for event in events:
        if event.get("type") != "step_recorded":
            continue
        body = exec_of(event)
        if int(body.get("round", -1)) != rnd or body.get("step") != "implement":
            continue
        row = assessed.get(body.get("attempt_id")) or {}
        if row.get("problems"):
            return []
        manifest = row.get("manifest") or {}
        return list(manifest.get("notes") or [])
    return []


def _next_missing(events, rnd: int) -> str | None:
    for name in STEPS:
        grouped = events_for_step(events, rnd, name)
        if not grouped["step_intent"]:
            return name
    return None


def _last_recorded_name(events, rnd: int) -> str | None:
    found = None
    for event in events:
        if event.get("type") != "step_recorded":
            continue
        body = exec_of(event)
        if int(body.get("round", -1)) == rnd:
            found = body.get("step")
    return found


def _attempt_for(events, rnd: int, step: str) -> str | None:
    grouped = events_for_step(events, rnd, step)
    if grouped["step_recorded"]:
        return exec_of(grouped["step_recorded"][-1]).get("attempt_id")
    if grouped["step_intent"]:
        return exec_of(grouped["step_intent"][-1]).get("attempt_id")
    return None


def _overdue(events, attempt: str | None, now: datetime | None) -> bool:
    if not attempt or now is None:
        return False
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    for event in events:
        if event.get("type") != "step_started":
            continue
        if exec_of(event).get("attempt_id") != attempt:
            continue
        limit = event.get("limit_seconds")
        started = event.get("started_at")
        if limit is None or not started:
            return False
        return (now - _parse_time(started)).total_seconds() > float(limit)
    return False


def closing_for(events, rnd: int) -> list[dict]:
    return closing_resolutions(events, rnd)


def _collect_problems(events, assessed, rnd: int | None) -> list[str]:
    if rnd is None:
        return []
    found: list[str] = []
    for event in events:
        if event.get("type") != "step_recorded":
            continue
        body = exec_of(event)
        if int(body.get("round", -1)) != rnd:
            continue
        row = assessed.get(body.get("attempt_id")) or {}
        found.extend(row.get("problems") or [])
    return found
