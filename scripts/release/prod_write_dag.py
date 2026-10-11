"""Pipeline DAGs that can change platform PROD.

A pipeline has a PROD row when a PROD value is reachable by a parameter a
caller may set (image, tag, namespace, application, context, path), unless an
enum or a reviewed param policy rules that value out. Defaults are not
substituted: a STG default with no enum can still be set to PROD.

A freeze task counts only when its taskRef is in prod_freeze_tasks.yaml, it
has no when and no onError continue, it is not in finally, and it sits on
every path to the side effect. A finally task is never dominated: it runs
even when the freeze failed.

Steps are classified from command, args and script. A task whose steps cannot
be classified is side-effecting.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


HERE = Path(__file__).resolve().parent
FREEZE_PATH = HERE / "prod_freeze_tasks.yaml"

_PARAM = re.compile(r"\$\(params\.([A-Za-z0-9_-]+)\)")
_SENSITIVE = ("image", "tag", "namespace", "application", "context", "path")
_WRITES = (
    (re.compile(r"\bkubectl\s+apply\b", re.I), "apply"),
    (re.compile(r"\bkubectl\s+patch\b", re.I), "patch"),
    (re.compile(r"\bkubectl\s+rollout\b", re.I), "rollout"),
    (re.compile(r"\bkubectl\s+set\s+image\b", re.I), "set-image"),
    (re.compile(r"\bkubectl\s+delete\b", re.I), "delete"),
    (re.compile(r"\b(argocd\b.*\bsync\b|/kaniko/executor|docker\s+push|crane\s+(push|copy)|skopeo\s+copy)\b", re.I), "sync-or-push"),
    (re.compile(r"\bgit\s+push\b", re.I), "git-push"),
    (re.compile(r"\bcurl\b[\s\S]{0,240}(-X|--request)\s*(POST|PUT|PATCH|DELETE)\b", re.I), "api-write"),
    (re.compile(r"\bcurl\b[\s\S]{0,120}(\s-d\b|\s--data\b)", re.I), "api-write"),
)
_KANIKO = re.compile(r"kaniko|crane\s+push|skopeo\s+copy|--destination=", re.I)
_PUSH_KIND = {
    "sync-or-push": None,  # split below
}


def load_freeze(path: Path = FREEZE_PATH) -> tuple[set[str], list[dict]]:
    if not path.is_file():
        return set(), []
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    names = {str(item) for item in (loaded.get("freeze_tasks") or [])}
    policies = [item for item in (loaded.get("param_policies") or []) if isinstance(item, dict)]
    return names, policies


def _tasks_of(spec: dict, key: str) -> list[dict]:
    return [task for task in (spec.get(key) or []) if isinstance(task, dict) and task.get("name")]


def _sensitive(name: str) -> bool:
    low = name.lower().replace("_", "").replace("-", "")
    return any(part in low for part in _SENSITIVE)


def _prodish(text: str) -> bool:
    low = text.lower()
    return "bifrost-platform-prod" in low or ":prod" in low or low.strip() in {"prod"}


def _params_by_name(spec: dict | None) -> dict[str, dict]:
    found = {}
    for param in (spec or {}).get("params") or []:
        if isinstance(param, dict) and param.get("name"):
            found[str(param["name"])] = param
    return found


def _policy_allows_prod(name: str, policies: list[dict]) -> bool | None:
    """True/False when a policy pins this parameter, else None."""
    for policy in policies:
        if str(policy.get("param") or "") != name:
            continue
        allowed = [str(item) for item in (policy.get("allowed") or [])]
        return any(_prodish(item) for item in allowed)
    return None


def _param_can_be_prod(name: str, pipeline_params: dict[str, dict], policies: list[dict], concrete: bool) -> bool:
    pinned = _policy_allows_prod(name, policies)
    if pinned is not None:
        return pinned
    spec = pipeline_params.get(name) or {}
    if concrete:
        if "override" in spec:
            return _prodish(str(spec.get("override") or ""))
        return _prodish(str(spec.get("default") or ""))
    enum = spec.get("enum")
    if enum:
        return any(_prodish(str(item)) for item in enum)
    return _sensitive(name)


def _values_can_reach(value, pipeline_params, task_param: str, policies, concrete: bool) -> bool:
    if isinstance(value, list):
        return any(_values_can_reach(item, pipeline_params, task_param, policies, concrete) for item in value)
    if isinstance(value, dict):
        return any(_values_can_reach(item, pipeline_params, task_param, policies, concrete) for item in value.values())
    text = "" if value is None else str(value)
    if _prodish(text) and "$(" not in text:
        return True
    names = _PARAM.findall(text)
    if not names:
        return False
    for name in names:
        if _param_can_be_prod(name, pipeline_params, policies, concrete):
            return True
        if _sensitive(task_param) and _param_open(name, pipeline_params, policies, concrete):
            return True
    return False


def _param_open(name: str, pipeline_params: dict[str, dict], policies: list[dict], concrete: bool) -> bool:
    """An unconstrained parameter can carry a PROD value when its slot is sensitive."""
    if concrete:
        return _param_can_be_prod(name, pipeline_params, policies, True)
    pinned = _policy_allows_prod(name, policies)
    if pinned is not None:
        return pinned
    spec = pipeline_params.get(name)
    if spec is None:
        return True
    enum = spec.get("enum")
    if enum:
        return any(_prodish(str(item)) for item in enum)
    return True


def reaches_prod(pipeline_task: dict, task_def: dict | None, pipeline_params: dict[str, dict], policies: list[dict], concrete: bool = False) -> bool:
    for param in pipeline_task.get("params") or []:
        if not isinstance(param, dict):
            continue
        if _values_can_reach(param.get("value"), pipeline_params, str(param.get("name") or ""), policies, concrete):
            return True
    for param_name in pipeline_params:
        if not _sensitive(param_name):
            continue
        if not _param_can_be_prod(param_name, pipeline_params, policies, concrete):
            continue
        blob = yaml.safe_dump(pipeline_task, default_flow_style=True)
        if f"$(params.{param_name})" in blob:
            return True
    if task_def:
        for param in ((task_def.get("spec") or {}).get("params") or []):
            if isinstance(param, dict) and _sensitive(str(param.get("name") or "")) and _prodish(str(param.get("default") or "")):
                passed = {str(item.get("name") or "") for item in (pipeline_task.get("params") or []) if isinstance(item, dict)}
                if str(param.get("name") or "") not in passed:
                    return True
    for step in _steps_of(pipeline_task) + _steps_of(task_def):
        if _prodish(_step_blob(step)):
            return True
    return False


def _step_blob(step: dict) -> str:
    command = step.get("command") or []
    args = step.get("args") or []
    if not isinstance(command, list):
        command = [command]
    if not isinstance(args, list):
        args = [args]
    invocation = " ".join(str(item) for item in list(command) + list(args))
    parts = [str(step.get("script") or ""), invocation, str(step.get("image") or "")]
    return "\n".join(parts)


def _steps_of(node: dict | None) -> list[dict]:
    if not node:
        return []
    spec = node.get("spec") or node.get("taskSpec") or {}
    if node.get("taskSpec"):
        spec = node["taskSpec"]
    steps = []
    for step in (spec.get("steps") or []) + (spec.get("sidecars") or []):
        if isinstance(step, dict):
            steps.append(step)
    return steps


def classify_steps(pipeline_task: dict, task_def: dict | None) -> set[str]:
    """Write kinds. ``unclassified-step`` means the program cannot say it is read-only."""
    steps = _steps_of(pipeline_task) + _steps_of(task_def)
    if not steps:
        return {"unclassified-step"}
    kinds: set[str] = set()
    for step in steps:
        blob = _step_blob(step)
        if not blob.strip():
            kinds.add("unclassified-step")
            continue
        found = False
        if _KANIKO.search(blob) and ("--destination" in blob or "kaniko" in blob.lower()):
            kinds.add("image-push")
            found = True
        if re.search(r"\bkubectl\s+patch\s+application\b", blob, re.I):
            kinds.add("sync")
            found = True
        for pattern, kind in _WRITES:
            if not pattern.search(blob):
                continue
            found = True
            if kind == "sync-or-push":
                if re.search(r"\bsync\b", blob, re.I) and "kaniko" not in blob.lower():
                    kinds.add("sync")
                if _KANIKO.search(blob):
                    kinds.add("image-push")
            else:
                kinds.add(kind)
        if not found and not _read_only(blob):
            kinds.add("unclassified-step")
    kinds.discard("sync-or-push")
    return kinds or {"unclassified-step"}


def _read_only(blob: str) -> bool:
    """True when the step text has no write tool the program failed to classify."""
    if re.search(r"\b(curl|wget|kaniko|docker|crane|skopeo|argocd|helm|urllib|requests|python\d*|perl|ruby|node)\b", blob, re.I):
        return False
    if re.search(r"\bgit\s+push\b", blob, re.I):
        return False
    if re.search(r"\bkubectl\s+(apply|patch|rollout|delete|replace|edit|scale|taint|cordon|drain|exec|auth)\b", blob, re.I):
        return False
    if re.search(r"\bkubectl\s+set\s+image\b", blob, re.I):
        return False
    if re.search(r"\bkubectl\s+create\b", blob, re.I) and "dry-run" not in blob:
        return False
    return True


def _qualifies_freeze(task: dict, freeze_refs: set[str]) -> bool:
    ref = str((task.get("taskRef") or {}).get("name") or "")
    if ref not in freeze_refs:
        return False
    if task.get("when"):
        return False
    if str(task.get("onError") or "").lower() == "continue":
        return False
    return True


def _dominates(name: str, preds: dict[str, list[str]], freezes: set[str]) -> bool:
    """True when every path from a root to name passes a freeze task."""
    if name in freezes:
        return False
    children: dict[str, list[str]] = {}
    nodes = set(preds)
    for task, parents in preds.items():
        nodes.add(task)
        for parent in parents:
            nodes.add(parent)
            children.setdefault(parent, []).append(task)
    roots = [node for node in nodes if not preds.get(node)]
    seen = set()
    stack = [root for root in roots if root not in freezes]
    while stack:
        current = stack.pop()
        if current == name:
            return False
        if current in seen or current in freezes:
            continue
        seen.add(current)
        stack.extend(children.get(current, []))
    return True


def _lookup(index: dict[tuple[str, str], dict], namespace: str, name: str) -> dict | None:
    if not name:
        return None
    if (namespace, name) in index:
        return index[(namespace, name)]
    if ("", name) in index:
        return index[("", name)]
    for (item_ns, item_name), doc in index.items():
        if item_name == name:
            return doc
    return None


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


def _spec_rows(pipeline_name: str, namespace: str, spec: dict, task_index, freeze_refs: set[str], policies: list[dict], identity_prefix: str) -> list[dict]:
    concrete = identity_prefix == "pipelinerun"
    pipeline_params = _params_by_name(spec)
    rows = []
    graph_tasks = _tasks_of(spec, "tasks")
    finally_tasks = _tasks_of(spec, "finally")
    freezes = {str(task["name"]) for task in graph_tasks if _qualifies_freeze(task, freeze_refs)}
    preds = {str(task["name"]): [str(item) for item in (task.get("runAfter") or [])] for task in graph_tasks}

    def emit(task: dict, dominated_ok: bool) -> None:
        name = str(task["name"])
        ref = task.get("taskRef") or {}
        task_def = None if task.get("taskSpec") else _lookup(task_index, namespace, str(ref.get("name") or ""))
        if _qualifies_freeze(task, freeze_refs) and dominated_ok:
            return
        if not reaches_prod(task, task_def, pipeline_params, policies, concrete):
            return
        kinds = classify_steps(task, task_def)
        if dominated_ok and freezes and _dominates(name, preds, freezes):
            return
        for kind in sorted(kinds):
            rows.append(
                {
                    "identity": f"{identity_prefix}/{pipeline_name}",
                    "target": f"dag/{pipeline_name}/{name}",
                    "field": kind,
                    "verbs": kind,
                }
            )

    for task in graph_tasks:
        emit(task, dominated_ok=True)
    for task in finally_tasks:
        emit(task, dominated_ok=False)
    return rows


def _pipelines(docs: list[dict]) -> list[tuple[str, str, dict, str]]:
    found = []
    named = {}
    for doc in docs:
        kind = str(doc.get("kind") or "")
        meta = doc.get("metadata") or {}
        name = str(meta.get("name") or "")
        namespace = str(meta.get("namespace") or "")
        if kind == "Pipeline" and name:
            named[(namespace, name)] = doc.get("spec") or {}
            found.append((name, namespace, doc.get("spec") or {}, "pipeline"))
    for doc in docs:
        if str(doc.get("kind") or "") != "PipelineRun":
            continue
        meta = doc.get("metadata") or {}
        name = str(meta.get("name") or "")
        namespace = str(meta.get("namespace") or "")
        spec = doc.get("spec") or {}
        if not name:
            continue
        inline = spec.get("pipelineSpec")
        if isinstance(inline, dict):
            merged = _overlay_params(inline, spec.get("params") or [])
            found.append((name, namespace, merged, "pipelinerun"))
            continue
        ref = spec.get("pipelineRef") or {}
        base = named.get((namespace, str(ref.get("name") or ""))) or named.get(("", str(ref.get("name") or "")))
        if base is None:
            for (item_ns, item_name), body in named.items():
                if item_name == ref.get("name"):
                    base = body
                    break
        if base is not None:
            found.append((name, namespace, _overlay_params(base, spec.get("params") or []), "pipelinerun"))
    return found


def _overlay_params(spec: dict, overrides: list) -> dict:
    """Return a spec whose params include PipelineRun overrides as reachable values.

    An override replaces the default and, when it is a concrete PROD value, is
    prodish. An override that is not PROD does not delete the caller's ability
    to pass another value on the Pipeline itself; that row is separate.
    """
    import copy

    merged = copy.deepcopy(spec)
    by_name = _params_by_name(merged)
    for param in overrides or []:
        if not isinstance(param, dict) or not param.get("name"):
            continue
        name = str(param["name"])
        current = by_name.get(name) or {"name": name}
        value = param.get("value")
        if value is not None:
            current["default"] = value
            # A concrete override is the value this run uses. Keep enum so a
            # pinned parameter stays pinned, but record the value for literals.
            current["override"] = value
        by_name[name] = current
    merged["params"] = list(by_name.values())
    return merged


def indirect_rows(docs: list[dict], freeze_path: Path = FREEZE_PATH) -> list[dict]:
    freeze_refs, policies = load_freeze(freeze_path)
    task_index = _task_index(docs)
    found: list[dict] = []
    for name, namespace, spec, prefix in sorted(_pipelines(docs)):
        found.extend(_spec_rows(name, namespace, spec, task_index, freeze_refs, policies, prefix))
    found.sort(key=lambda row: (row["identity"], row["target"], row["field"]))
    # PipelineRun rows are additional. Drop a pipelinerun row that only repeats
    # a non-PROD override: reaches_prod already requires a reachable PROD value.
    return found
