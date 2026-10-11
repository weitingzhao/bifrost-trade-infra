"""The usual duration, fixed at declare time from earlier logs.

The fold reads the number on the step. It does not reach into other logs.
Fewer than three clean runs: a handwritten ``usual_min`` from ``tasks.json``
beside the events root, in minutes, stored as seconds. Otherwise the field
is left off and the step is never ``slow``.
"""

from __future__ import annotations

import json
from pathlib import Path

from events import load_file
from model import GAP_S
from validate import classify

# tasks.json names a step in Chinese. The kind on an event is one of these.
_KIND_NAMES = {
    "implement": {"实现"},
    "verify": {"验收", "验证"},
    "review": {"复核"},
    "merge": {"合并"},
    "release": {"发布"},
    "ci": {"CI", "ci"},
    "other": set(),
}


def usual_for(root: Path, kind: str, measured: bool = True) -> tuple[float, str] | None:
    samples = _measured(root, kind) if measured else []
    if len(samples) >= 3:
        last = samples[:20]
        return _median([item[1] for item in last]), "measured"
    handwritten = _handwritten(root, kind)
    if handwritten is None:
        return None
    return handwritten, "declared"


def _measured(root: Path, kind: str) -> list[tuple[float, float]]:
    found = []
    if not root.is_dir():
        return found
    for directory in sorted(root.iterdir()):
        if not directory.is_dir() or directory.name.startswith(".") or directory.name.startswith("_"):
            continue
        log = load_file(directory / "events.jsonl")
        if log.invalid_seq is not None:
            continue
        view = classify(log.events, work_id=directory.name)
        for step in view.steps.values():
            if step.kind != kind or step.watch != "process" or not step.ended or not step.started:
                continue
            finished = step.finished or {}
            exit_body = finished.get("exit") or {}
            if exit_body.get("code") != 0:
                continue
            if _anomalous(view, step):
                continue
            found.append((finished["at"], finished["at"] - step.started_at))
    found.sort(key=lambda item: item[0], reverse=True)
    return found


def _anomalous(view, step) -> bool:
    times = [step.started_at]
    for event in step.seen:
        times.append(event["sampled_at"])
    if any(later - earlier > GAP_S for earlier, later in zip(times, times[1:])):
        return True
    for index, event in enumerate(view.valid):
        if event.get("step_id") != step.step_id:
            continue
        if event["type"] in {"step_started", "step_seen", "step_finished"} and index in view.backwards:
            return True
    finished = step.finished or {}
    if step.started_at is not None and finished.get("at") is not None:
        if finished["at"] - step.started_at <= 0:
            return True
    return False


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _handwritten(root: Path, kind: str):
    path = root.parent / "status" / "tasks.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    names = _KIND_NAMES.get(kind, set())
    works = data.get("works") if isinstance(data, dict) else None
    if not isinstance(works, list):
        return None
    for work in works:
        if not isinstance(work, dict):
            continue
        for step in work.get("steps") or []:
            if not isinstance(step, dict):
                continue
            matched = step.get("kind") == kind or step.get("name") in names
            if not matched:
                continue
            if isinstance(step.get("usual_s"), (int, float)) and not isinstance(step.get("usual_s"), bool):
                return float(step["usual_s"])
            if isinstance(step.get("usual_min"), (int, float)) and not isinstance(step.get("usual_min"), bool):
                return float(step["usual_min"]) * 60
    return None
