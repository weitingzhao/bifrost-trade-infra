#!/usr/bin/env python3
"""Freeze-check domination for every Tekton Pipeline (W-56 step 1, slice B).

A side-effecting task is dominated only when every path from a root to it
passes through a freeze-check task that counts as protection.

A freeze task counts as protection only when all of these hold:

- It references Task ``freeze_task_ref`` by ``taskRef`` name. A pipeline-task
  name, a name substring, or an inline ``taskSpec`` is not a freeze check.
- It has no ``when``. A skipped check dominates nothing.
- It has no ``onError: continue``. That lets the pipeline keep running after
  the check fails, so the refusal never stops the write.
- It has no ``retries`` other than absent or 0. A refusal is a failed step.
  Tekton would run the task again, and a later attempt can succeed against a
  different object (the freeze lifted, or the object was replaced) and the run
  continues as if the first refusal had not happened. The cut is one read.
- It is not in ``finally``. Those tasks run even when the check failed, so a
  check placed there is not a gate.

A pipeline that contains a freeze task in an illegal position or form is a
violation even when it has no side-effecting task. There is no exemption list:
``not_this_slice`` is ignored.

Side effects:

- A name on ``side_effect`` is a side effect. That list is consulted first.
- A read-only ``taskRef`` is a Task defined in this repository whose steps the
  checker has examined and found not to write.
- A read-only inline task is ``(pipeline, task)`` plus the sha256 of its
  ``taskSpec`` (see ``taskspec_digest``). A changed spec invalidates it. A
  global read-only name does not cover an inline task.
- Anything else is side-effecting.

Messages:

- ``<pipeline>: <task> is not dominated by the freeze check``
- ``<pipeline>: <task> is not a valid freeze check (<reason>)``

Sibling pipelines use ``<repo>/<pipeline>`` as the pipeline label.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
EFFECTS_PATH = HERE / "freeze_effects.json"
GAPS_PATH = HERE / "freeze_known_gaps.json"
TEKTON = HERE.parents[1] / "k8s" / "cicd" / "tekton"
MESSAGE = "{pipeline}: {task} is not dominated by the freeze check"
INVALID = "{pipeline}: {task} is not a valid freeze check ({reason})"

# Writes to a registry or a cluster. ``kubectl get`` and ``kubectl create
# --dry-run`` are reads. Examined step scripts and args only.
_WRITE = re.compile(
    r"(git\s+push\b"
    r"|kubectl\s+(apply|delete|patch|replace|scale|annotate|label|exec|set)\b"
    r"|kubectl\s+rollout\s+restart\b"
    r"|docker\s+push\b"
    r"|--destination(?:=|\s)"
    r"|helm\s+(upgrade|install)\b"
    r"|argocd\s+app\s+sync\b)"
)
_KUBECTL_CREATE = re.compile(r"\bkubectl\s+create\b")

_TASKS: dict[str, dict] | None = None


def load_effects(path: Path | None = None) -> dict:
    return json.loads((path or EFFECTS_PATH).read_text(encoding="utf-8"))


def load_gap_document(path: Path | None = None) -> dict:
    return json.loads((path or GAPS_PATH).read_text(encoding="utf-8"))


def load_known_gaps(path: Path | None = None) -> list[dict]:
    return list(load_gap_document(path)["gaps"])


def taskspec_digest(spec: dict) -> str:
    """sha256 of the canonical JSON of a taskSpec. A changed spec will not match."""
    payload = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def definition_digest(task: dict) -> str:
    """sha256 of the definition a known gap is bound to.

    An inline task hashes its taskSpec. A taskRef hashes the taskRef and its
    params. A different digest is a different definition.
    """
    spec = task.get("taskSpec")
    if isinstance(spec, dict):
        return taskspec_digest(spec)
    ref = task.get("taskRef")
    body = {
        "params": task.get("params") or [],
        "taskRef": ref if isinstance(ref, dict) else {},
    }
    return taskspec_digest(body)


def load_task_index(tekton: Path | None = None) -> dict[str, dict]:
    """Task name -> spec, for Tasks defined under this repository's tekton dir."""
    found: dict[str, dict] = {}
    root = tekton or TEKTON
    for path in sorted(root.rglob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if not isinstance(doc, dict) or doc.get("kind") != "Task":
                continue
            name = str((doc.get("metadata") or {}).get("name") or "")
            if name:
                found[name] = doc.get("spec") or {}
    return found


def task_index() -> dict[str, dict]:
    global _TASKS
    if _TASKS is None:
        _TASKS = load_task_index()
    return _TASKS


def effect_identity(task: dict) -> str:
    ref = task.get("taskRef")
    if isinstance(ref, dict) and ref.get("name") and "taskSpec" not in task:
        return str(ref["name"])
    return str(task.get("name") or "")


def _step_text(spec: dict) -> str:
    chunks: list[str] = []
    for step in spec.get("steps") or []:
        if not isinstance(step, dict):
            continue
        for key in ("script", "command", "args"):
            value = step.get(key)
            if isinstance(value, str):
                chunks.append(value)
            elif isinstance(value, list):
                chunks.extend(str(item) for item in value)
    return "\n".join(chunks)


def steps_write(spec: dict) -> bool:
    """True when examined steps push an image or write to the cluster."""
    text = _step_text(spec)
    if _WRITE.search(text):
        return True
    for line in text.splitlines():
        if _KUBECTL_CREATE.search(line) and "--dry-run" not in line:
            return True
    return False


def _read_only_binding(task: dict, effects: dict, pipeline: str, tasks: dict[str, dict]) -> bool:
    ref = task.get("taskRef")
    if isinstance(ref, dict) and ref.get("name") and "taskSpec" not in task:
        name = str(ref["name"])
        if name not in set(effects.get("read_only_task_ref") or []):
            return False
        examined = tasks.get(name)
        if not isinstance(examined, dict):
            return False
        return not steps_write(examined)
    spec = task.get("taskSpec")
    if not isinstance(spec, dict):
        return False
    digest = taskspec_digest(spec)
    task_name = str(task.get("name") or "")
    for entry in effects.get("read_only_inline") or []:
        if (
            entry.get("pipeline") == pipeline
            and entry.get("task") == task_name
            and entry.get("taskspec_sha256") == digest
            and not steps_write(spec)
        ):
            return True
    return False


def is_side_effect(
    task: dict,
    effects: dict,
    pipeline: str,
    tasks: dict[str, dict] | None = None,
) -> bool:
    """True when the task writes, or is not a binding the checker has examined."""
    if effect_identity(task) in set(effects.get("side_effect") or []):
        return True
    examined = tasks if tasks is not None else task_index()
    if _read_only_binding(task, effects, pipeline, examined):
        return False
    return True


def _freeze_ref(task: dict, effects: dict) -> bool:
    """True only for the declared taskRef. Name patterns and inline specs are not it."""
    ref = task.get("taskRef")
    return isinstance(ref, dict) and ref.get("name") == effects["freeze_task_ref"]


def freeze_problem(task: dict, effects: dict, in_finally: bool) -> str | None:
    """Why this freeze task is not protection, or None if it is not a freeze task.

    A valid freeze task returns None as well; callers use ``freeze_protects``.
    """
    if not _freeze_ref(task, effects):
        return None
    reasons: list[str] = []
    if "taskSpec" in task:
        reasons.append("inline spec")
    if task.get("when"):
        reasons.append("when")
    on_error = task.get("onError")
    if on_error not in (None, "stopAndFail"):
        reasons.append("onError: continue" if on_error == "continue" else f"onError: {on_error}")
    if task.get("retries") not in (None, 0):
        reasons.append("retries")
    if in_finally:
        reasons.append("finally")
    if not reasons:
        return None
    return ", ".join(reasons)


def freeze_protects(task: dict, effects: dict) -> bool:
    return _freeze_ref(task, effects) and "taskSpec" not in task and freeze_problem(task, effects, False) is None


def is_freeze_check(task: dict, effects: dict) -> bool:
    """True when the task references the freeze Task, even if the form is illegal."""
    return _freeze_ref(task, effects)


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


def _collect(
    doc: dict,
    effects: dict | None = None,
    tasks: dict[str, dict] | None = None,
    pipeline_label: str | None = None,
) -> list[tuple[str, dict]]:
    """Violation message and the pipeline task it names, in report order."""
    effects = effects or load_effects()
    examined = tasks if tasks is not None else task_index()
    meta = doc.get("metadata") or {}
    pipeline = str(meta.get("name") or "")
    label = pipeline_label or pipeline
    spec = doc.get("spec") or {}
    body = list(spec.get("tasks") or [])
    finally_tasks = list(spec.get("finally") or [])
    misses: list[tuple[str, dict]] = []
    for task in body:
        reason = freeze_problem(task, effects, False)
        if reason:
            misses.append((INVALID.format(pipeline=label, task=str(task["name"]), reason=reason), task))
    for task in finally_tasks:
        reason = freeze_problem(task, effects, True)
        if reason:
            misses.append((INVALID.format(pipeline=label, task=str(task["name"]), reason=reason), task))
    freeze = {str(task["name"]) for task in body if freeze_protects(task, effects)}
    for task in body:
        name = str(task["name"])
        if not is_side_effect(task, effects, pipeline, examined):
            continue
        if _path_misses_freeze(body, name, freeze):
            misses.append((MESSAGE.format(pipeline=label, task=name), task))
    for task in finally_tasks:
        if is_side_effect(task, effects, pipeline, examined):
            misses.append((MESSAGE.format(pipeline=label, task=str(task["name"])), task))
    return misses


def violations_for(
    doc: dict,
    effects: dict | None = None,
    tasks: dict[str, dict] | None = None,
    pipeline_label: str | None = None,
) -> list[str]:
    return [msg for msg, _task in _collect(doc, effects, tasks, pipeline_label)]


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
    examined = task_index() if tekton == TEKTON else load_task_index(tekton)
    misses: list[str] = []
    for _path, doc in iter_pipelines(tekton):
        misses.extend(violations_for(doc, effects, examined))
    return misses


def records_for_doc(
    doc: dict,
    repo: str,
    effects: dict | None = None,
    tasks: dict[str, dict] | None = None,
) -> list[dict]:
    """One record per violation: repo, pipeline, task, definition digest, message."""
    name = str((doc.get("metadata") or {}).get("name") or "")
    records: list[dict] = []
    for msg, task in _collect(doc, effects, tasks, pipeline_label=f"{repo}/{name}"):
        records.append(
            {
                "repo": repo,
                "pipeline": name,
                "task": str(task.get("name") or ""),
                "digest": definition_digest(task),
                "message": msg,
            }
        )
    return records


def records_in_file(
    path: Path,
    repo: str,
    effects: dict | None = None,
    tasks: dict[str, dict] | None = None,
) -> list[dict]:
    """Violation records for a pipeline file outside this repository."""
    found: list[dict] = []
    for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
        if isinstance(doc, dict) and doc.get("kind") == "Pipeline":
            found.extend(records_for_doc(doc, repo, effects, tasks))
    return found


def violations_in_file(
    path: Path,
    repo: str,
    effects: dict | None = None,
    tasks: dict[str, dict] | None = None,
) -> list[str]:
    """Domination misses for a pipeline file outside this repository."""
    return [item["message"] for item in records_in_file(path, repo, effects, tasks)]


def _gap_age_days(item: dict, today: date) -> int | None:
    raw = item.get("date")
    if not isinstance(raw, str):
        return None
    try:
        recorded = date.fromisoformat(raw)
    except ValueError:
        return None
    return (today - recorded).days


def split_known_gaps(
    records: list[dict],
    gaps: list[dict] | None = None,
    max_age_days: int | None = None,
    today: date | None = None,
) -> tuple[list[str], list[dict]]:
    """Return (hard failure messages, tolerated gaps).

    A record is tolerated only when one entry matches repository, pipeline,
    task name and definition digest, and its date parses to an age from 0
    through max_age_days. The message alone is not a match. A different
    digest, an unparsed date, or an older entry is a new gap.
    """
    document = None if gaps is not None else load_gap_document()
    entries = list(gaps) if gaps is not None else list(document["gaps"])
    if max_age_days is None:
        raw_age = 0 if document is None else document.get("max_age_days")
        max_age_days = raw_age if isinstance(raw_age, int) and raw_age >= 0 else 0
    clock = today or date.today()
    hard: list[str] = []
    known: list[dict] = []
    for record in records:
        age: int | None = None
        matched: dict | None = None
        for entry in entries:
            if entry.get("repo") != record.get("repo"):
                continue
            if entry.get("pipeline") != record.get("pipeline"):
                continue
            if entry.get("task") != record.get("task"):
                continue
            if entry.get("spec_sha256") != record.get("digest"):
                continue
            candidate = _gap_age_days(entry, clock)
            if candidate is None or candidate < 0 or candidate > max_age_days:
                continue
            age = candidate
            matched = entry
            break
        if matched is None or age is None:
            hard.append(str(record.get("message") or ""))
            continue
        known.append(
            {
                "name": str(matched.get("name") or ""),
                "message": str(record.get("message") or ""),
                "age_days": age,
            }
        )
    return hard, known
