"""Pipeline task DAGs that can change platform PROD.

A side-effecting task (image push, rollout, sync, apply, or an unresolved
resolver) is a matrix row when it can reach platform PROD and no release-window
task is a runAfter ancestor. Tekton runAfter is a join: a parallel root does
not bypass the freeze task when the side effect also waits for that task.
A dominated side effect is omitted.
"""

from __future__ import annotations

import re


_PARAM = re.compile(r"\$\(params\.([A-Za-z0-9_-]+)\)")
_PROD_MARKERS = (
    "bifrost-platform-prod",
    "bifrost-platform-api:prod",
    "bifrost-platform-console:prod",
)


def _tasks_of(spec: dict) -> list[dict]:
    tasks = spec.get("tasks") or []
    return [task for task in tasks if isinstance(task, dict) and task.get("name")]


def _defaults(spec: dict) -> dict[str, str]:
    defaults = {}
    for param in spec.get("params") or []:
        if isinstance(param, dict) and param.get("name"):
            defaults[str(param["name"])] = "" if param.get("default") is None else str(param.get("default"))
    return defaults


def _resolve(value, defaults: dict[str, str]) -> str:
    if isinstance(value, list):
        return " ".join(_resolve(item, defaults) for item in value)
    if value is None:
        return ""
    text = str(value)

    def replace(match: re.Match) -> str:
        return defaults.get(match.group(1), match.group(0))

    return _PARAM.sub(replace, text)


def _task_index(docs: list[dict]) -> dict[tuple[str, str], dict]:
    index = {}
    for doc in docs:
        if str(doc.get("kind") or "") != "Task":
            continue
        meta = doc.get("metadata") or {}
        name = str(meta.get("name") or "")
        if name:
            index[(str(meta.get("namespace") or ""), name)] = doc
    return index


def _lookup_task(index: dict[tuple[str, str], dict], namespace: str, name: str) -> dict | None:
    if not name:
        return None
    return index.get((namespace, name)) or index.get(("", name)) or next(
        (doc for (ns, task_name), doc in index.items() if task_name == name),
        None,
    )


def _scripts(node: dict | None) -> str:
    if not node:
        return ""
    spec = node.get("spec") or node.get("taskSpec") or {}
    chunks = []
    for step in (spec.get("steps") or []) + (spec.get("sidecars") or []):
        if isinstance(step, dict):
            chunks.append(str(step.get("script") or ""))
            chunks.append(str(step.get("name") or ""))
    return "\n".join(chunks)


def effect_kind(pipeline_task: dict, task_def: dict | None) -> str | None:
    ref = pipeline_task.get("taskRef") or {}
    names = " ".join(
        [
            str(pipeline_task.get("name") or ""),
            str(ref.get("name") or ""),
            str(((task_def or {}).get("metadata") or {}).get("name") or ""),
        ]
    ).lower()
    if "release-window" in names or "release-freeze" in names:
        return "freeze"
    if ref.get("resolver"):
        return "resolver"
    script = (_scripts(pipeline_task) + "\n" + _scripts(task_def)).lower()
    if "rollout" in names or "kubectl rollout" in script:
        return "rollout"
    if "gitops" in names or "argocd-sync" in names or "kubectl patch application" in script:
        return "sync"
    if "kaniko" in names or "build-and-push" in names or "/kaniko/executor" in script:
        return "image-push"
    if "apply-manifest" in names or "kubectl apply" in script:
        return "apply"
    return None


def _param_text(pipeline_task: dict, task_def: dict | None, defaults: dict[str, str]) -> str:
    values = []
    passed = set()
    for param in pipeline_task.get("params") or []:
        if not isinstance(param, dict):
            continue
        passed.add(str(param.get("name") or ""))
        values.append(_resolve(param.get("value"), defaults))
    task_params = ((task_def or {}).get("spec") or {}).get("params") or []
    for param in task_params:
        if isinstance(param, dict) and str(param.get("name") or "") not in passed:
            values.append(str(param.get("default") or ""))
    return "\n".join(values)


def reaches_platform_prod(pipeline_name: str, pipeline_task: dict, task_def: dict | None, effect: str, defaults: dict[str, str]) -> bool:
    if effect == "freeze":
        return False
    if pipeline_name == "bifrost-apply-manifest" and effect == "apply":
        return True
    text = _param_text(pipeline_task, task_def, defaults)
    text += "\n" + _scripts(pipeline_task) + "\n" + _scripts(task_def)
    return any(marker in text for marker in _PROD_MARKERS)


def _freeze_ancestor(name: str, preds: dict[str, list[str]], freezes: set[str], memo: dict[str, bool]) -> bool:
    if name in memo:
        return memo[name]
    memo[name] = False
    found = False
    for pred in preds.get(name, []):
        if pred in freezes or _freeze_ancestor(pred, preds, freezes, memo):
            found = True
            break
    memo[name] = found
    return found


def _spec_rows(pipeline_name: str, namespace: str, spec: dict, task_index: dict[tuple[str, str], dict]) -> list[dict]:
    tasks = _tasks_of(spec)
    if not tasks:
        return []
    defaults = _defaults(spec)
    kinds = {}
    for task in tasks:
        ref = task.get("taskRef") or {}
        task_def = None if task.get("taskSpec") else _lookup_task(task_index, namespace, str(ref.get("name") or ""))
        kinds[str(task["name"])] = effect_kind(task, task_def)
    freezes = {name for name, kind in kinds.items() if kind == "freeze"}
    preds = {str(task["name"]): [str(item) for item in (task.get("runAfter") or [])] for task in tasks}
    memo: dict[str, bool] = {}
    rows = []
    for task in tasks:
        name = str(task["name"])
        kind = kinds[name]
        if kind in (None, "freeze"):
            continue
        ref = task.get("taskRef") or {}
        task_def = None if task.get("taskSpec") else _lookup_task(task_index, namespace, str(ref.get("name") or ""))
        if not reaches_platform_prod(pipeline_name, task, task_def, kind, defaults):
            continue
        if _freeze_ancestor(name, preds, freezes, memo):
            continue
        rows.append(
            {
                "identity": f"pipeline/{pipeline_name}",
                "target": f"dag/{pipeline_name}/{name}",
                "field": kind,
                "verbs": kind,
            }
        )
    return rows


def indirect_rows(docs: list[dict]) -> list[dict]:
    """Undominated platform-PROD side effects. Stable order."""
    task_index = _task_index(docs)
    found: list[dict] = []
    pipelines = []
    for doc in docs:
        kind = str(doc.get("kind") or "")
        meta = doc.get("metadata") or {}
        name = str(meta.get("name") or "")
        namespace = str(meta.get("namespace") or "")
        if not name:
            continue
        if kind == "Pipeline":
            pipelines.append((name, namespace, doc.get("spec") or {}))
        elif kind == "PipelineRun":
            spec = doc.get("spec") or {}
            inline = spec.get("pipelineSpec")
            if isinstance(inline, dict):
                pipelines.append((name, namespace, inline))
    for name, namespace, spec in sorted(pipelines):
        found.extend(_spec_rows(name, namespace, spec, task_index))
    found.sort(key=lambda row: (row["identity"], row["target"], row["field"]))
    return found
