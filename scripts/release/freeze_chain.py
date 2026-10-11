#!/usr/bin/env python3
"""Freeze-check domination for every Tekton Pipeline (W-56 step 1, slice B).

A side-effecting task is dominated only when every path from a root to it
passes through a freeze-check task that has no `when`. Rules:

- Parallel roots: a root that reaches a side effect without the check is a miss.
  A join is not enough; the other root must itself run after the check.
- finally: these tasks run even when the check failed. A side-effecting finally
  task is a miss. A read-only finally task is not.
- when: a freeze check with a when dominates nothing (a skip is not a check).
  A when on some other task does not remove the check from the path.
- Inline taskSpec: there is no taskRef, so the pipeline task name is the
  identity. An unknown name is side-effecting until listed read-only.
- A name on neither list is side-effecting.

Messages are `<pipeline>: <task> is not dominated by the freeze check`.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
EFFECTS_PATH = HERE / "freeze_effects.json"
MESSAGE = "{pipeline}: {task} is not dominated by the freeze check"


def load_effects(path: Path | None = None) -> dict:
    return json.loads((path or EFFECTS_PATH).read_text(encoding="utf-8"))


def effect_identity(task: dict) -> str:
    ref = task.get("taskRef")
    if isinstance(ref, dict) and ref.get("name"):
        return str(ref["name"])
    return str(task.get("name") or "")


def is_side_effect(task: dict, effects: dict) -> bool:
    return effect_identity(task) not in set(effects["read_only"])


def is_freeze_check(task: dict, effects: dict) -> bool:
    ref = task.get("taskRef")
    if not isinstance(ref, dict):
        return False
    return ref.get("name") == effects["freeze_task_ref"]


def _successors(tasks: list[dict]) -> dict[str, list[str]]:
    succs: dict[str, list[str]] = {str(task["name"]): [] for task in tasks}
    names = set(succs)
    for task in tasks:
        for pred in task.get("runAfter") or []:
            if pred in names:
                succs[pred].append(str(task["name"]))
    return succs


def _roots(tasks: list[dict]) -> list[str]:
    return [str(task["name"]) for task in tasks if not task.get("runAfter")]


def _reachable(tasks: list[dict], target: str) -> bool:
    succs = _successors(tasks)
    seen: set[str] = set()
    stack = _roots(tasks)
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        if node == target:
            return True
        stack.extend(succs.get(node, []))
    return False


def _path_misses_freeze(tasks: list[dict], target: str, freeze: set[str]) -> bool:
    """True when some root reaches target without passing through freeze."""
    if not _reachable(tasks, target):
        return True
    succs = _successors(tasks)

    def walk(node: str, seen: set[str], hit: bool) -> bool:
        if node in freeze:
            hit = True
        if node == target:
            return not hit
        for nxt in succs.get(node, []):
            if nxt in seen:
                continue
            if walk(nxt, seen | {nxt}, hit):
                return True
        return False

    for root in _roots(tasks):
        if walk(root, {root}, root in freeze):
            return True
    return False


def violations_for(doc: dict, effects: dict | None = None) -> list[str]:
    effects = effects or load_effects()
    meta = doc.get("metadata") or {}
    pipeline = str(meta.get("name") or "")
    if pipeline in effects.get("not_this_slice", {}):
        return []
    spec = doc.get("spec") or {}
    tasks = list(spec.get("tasks") or [])
    finally_tasks = list(spec.get("finally") or [])
    freeze = {
        str(task["name"])
        for task in tasks
        if is_freeze_check(task, effects) and not task.get("when")
    }
    misses: list[str] = []
    for task in tasks:
        name = str(task["name"])
        if not is_side_effect(task, effects):
            continue
        if _path_misses_freeze(tasks, name, freeze):
            misses.append(MESSAGE.format(pipeline=pipeline, task=name))
    for task in finally_tasks:
        if is_side_effect(task, effects):
            misses.append(MESSAGE.format(pipeline=pipeline, task=str(task["name"])))
    return misses


def iter_pipelines(root: Path) -> list[tuple[Path, dict]]:
    found: list[tuple[Path, dict]] = []
    for path in sorted(root.rglob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        for doc in yaml.safe_load_all(text):
            if isinstance(doc, dict) and doc.get("kind") == "Pipeline":
                found.append((path, doc))
    return found


def violations_under(tekton: Path, effects: dict | None = None) -> list[str]:
    effects = effects or load_effects()
    misses: list[str] = []
    for _path, doc in iter_pipelines(tekton):
        misses.extend(violations_for(doc, effects))
    return misses
