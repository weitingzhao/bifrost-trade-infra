"""Release gate for an unattended platform PROD promote (W-56 G1).

A pure decision: no network, no clock except the ``now`` the caller passes.
Exit 0 when every rule holds. Otherwise exit non-zero and print, as the first
line, which rule failed and with what. There is no switch that lets a red or
missing CI run through.

Rules, in order:

1. A Succeeded ``bifrost-ci-platform`` PipelineRun has ``spec.params.revision``
   equal to the platform SHA. Matching uses ``ci_gate`` (pipeline set includes
   ``bifrost-ci-platform``). Red -> ``CI failed for <sha>: <run>``. A matching
   run that is not terminal yet -> exit 2 ``CI has not finished for <sha>``.
   No matching run -> ``no CI run for <sha>``.
2. The newest ``bifrost-deliver-platform`` attempt (not an older success, and
   not ``bifrost-deliver-platform-prod``) itself Succeeded, and its
   clone-platform / clone-ui commits are these two SHAs.
   ``STG runs <actual>, not <wanted>``.
3. That delivery's completionTime is at least ``soak_minutes`` ago (default 10).
   ``STG has run this for 3 min, need 10``.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from typing import Any, Optional

import ci_gate

PLATFORM_CI = "bifrost-ci-platform"
STG_PIPELINE = "bifrost-deliver-platform"
CLONE_PLATFORM = "clone-platform"
CLONE_UI = "clone-ui"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def decide(doc: dict) -> tuple[int, str]:
    """Return (exit_code, message). The first line is the decision."""
    try:
        return _decide(doc)
    except _Bad as exc:
        return 1, f"malformed input: {exc}"


def _decide(doc: dict) -> tuple[int, str]:
    if not isinstance(doc, dict):
        raise _Bad("expected a JSON object")
    platform = _sha(doc.get("platform_sha"), "platform_sha")
    ui = _sha(doc.get("ui_sha"), "ui_sha")
    now = _time(doc.get("now"), "now")
    soak = _soak(doc.get("soak_minutes", 10))
    runs = _items(doc.get("pipelineruns"), "pipelineruns")
    taskruns = _items(doc.get("taskruns"), "taskruns") if "taskruns" in doc else []

    code, line = _ci(runs, platform)
    if code != 0:
        return code, line

    stg = _newest_stg(runs)
    if stg is None:
        return 1, "no STG delivery of the platform"
    name = _run_name(stg)
    state = ci_gate._succeeded(stg)
    if state != "True":
        if state is None:
            return 1, f"newest STG delivery {name} has not finished"
        return 1, f"newest STG delivery {name} did not succeed"

    got_platform, got_ui = _clone_shas(stg, taskruns)
    if not got_platform:
        return 1, f"STG delivery {name} has no clone-platform commit"
    if got_platform != platform:
        return 1, f"STG runs {got_platform}, not {platform}"
    if not got_ui:
        return 1, f"STG delivery {name} has no clone-ui commit"
    if got_ui != ui:
        return 1, f"STG runs {got_ui}, not {ui}"

    done = _time((stg.get("status") or {}).get("completionTime"), "completionTime")
    elapsed = (now - done).total_seconds() / 60
    if elapsed < soak:
        shown = max(0, math.floor(elapsed))
        return 1, f"STG has run this for {shown} min, need {_fmt_min(soak)}"

    soaked = math.floor(elapsed)
    return 0, "\n".join([
        "pass",
        f"platform {platform} ci=succeeded",
        f"stg {name} platform={platform} ui={ui} soaked={soaked} min",
    ])


def _ci(runs: list[dict], sha: str) -> tuple[int, str]:
    if PLATFORM_CI not in ci_gate.CI_PIPELINES:
        raise _Bad(f"{PLATFORM_CI} is not in ci_gate.CI_PIPELINES")
    matched = []
    for run in runs:
        if ci_gate._pipeline_name(run) != PLATFORM_CI:
            continue
        if _param(run, "revision") != sha:
            continue
        matched.append(run)
    if any(ci_gate._succeeded(run) == "True" for run in matched):
        return 0, ""
    failed = [run for run in matched if ci_gate._succeeded(run) == "False"]
    if failed:
        newest = max(failed, key=_sort_key)
        return 1, f"CI failed for {sha}: {_run_name(newest)}"
    if matched:
        return 2, f"CI has not finished for {sha}"
    return 1, f"no CI run for {sha}"


def _newest_stg(runs: list[dict]) -> Optional[dict]:
    stg = [run for run in runs if ci_gate._pipeline_name(run) == STG_PIPELINE]
    if not stg:
        return None
    return max(stg, key=_sort_key)


def _clone_shas(run: dict, taskruns: list[dict]) -> tuple[str, str]:
    """clone-platform and clone-ui commits for this delivery.

    TaskRun ``commit`` results win. ``status.cloneResults`` and the legacy
    ``status.taskRuns`` map fill anything the TaskRun list did not.
    """
    found: dict[str, tuple[tuple, str]] = {}
    status = run.get("status") or {}
    embedded = status.get("cloneResults") or {}
    if isinstance(embedded, dict):
        for task in (CLONE_PLATFORM, CLONE_UI):
            commit = _norm_sha(embedded.get(task))
            if commit:
                found[task] = ((True, ""), commit)
    inline = status.get("taskRuns") or {}
    if isinstance(inline, dict):
        for tr in inline.values():
            if isinstance(tr, dict):
                _consider(found, str(tr.get("pipelineTaskName") or ""), tr, (tr.get("status") or {}).get("results"))
    name = _run_name(run)
    for tr in taskruns:
        task = _task_of(tr, name)
        if not task:
            continue
        _consider(found, task, tr, (tr.get("status") or {}).get("results"))
    return found.get(CLONE_PLATFORM, ((), ""))[1], found.get(CLONE_UI, ((), ""))[1]


def _consider(found: dict, task: str, tr: dict, results: Any) -> None:
    if task not in (CLONE_PLATFORM, CLONE_UI):
        return
    commit = _commit(results)
    if not commit:
        return
    rank = _task_rank(tr)
    prev = found.get(task)
    if prev is None or rank >= prev[0]:
        found[task] = (rank, commit)


def _task_of(tr: dict, run_name: str) -> str:
    if not isinstance(tr, dict):
        raise _Bad("taskrun is not an object")
    meta = tr.get("metadata") or {}
    if not isinstance(meta, dict):
        raise _Bad("taskrun metadata is not an object")
    labels = meta.get("labels") or {}
    if not isinstance(labels, dict):
        labels = {}
    owner = str(labels.get("tekton.dev/pipelineRun") or "")
    task = str(labels.get("tekton.dev/pipelineTask") or "")
    tr_name = str(meta.get("name") or "")
    if owner:
        if owner != run_name:
            return ""
        return task
    prefix = run_name + "-"
    if run_name and tr_name.startswith(prefix):
        return task or tr_name[len(prefix):]
    return ""


def _task_rank(tr: dict) -> tuple:
    ok = ci_gate._succeeded(tr) == "True"
    done = str((tr.get("status") or {}).get("completionTime") or "")
    return (ok, done)


def _commit(results: Any) -> str:
    if not isinstance(results, list):
        return ""
    for item in results:
        if isinstance(item, dict) and item.get("name") == "commit":
            return _norm_sha(item.get("value"))
    return ""


def _norm_sha(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _param(run: dict, name: str) -> str:
    return ci_gate._params(run).get(name, "").strip().lower()


def _run_name(run: dict) -> str:
    return str((run.get("metadata") or {}).get("name") or "unknown")


def _sort_key(run: dict) -> tuple:
    status = run.get("status") or {}
    meta = run.get("metadata") or {}
    when = str(status.get("startTime") or meta.get("creationTimestamp") or "")
    return (when, _run_name(run))


def _items(value: Any, label: str) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict) and isinstance(value.get("items"), list):
        items = value["items"]
    else:
        raise _Bad(f"{label} is not a list or a kubectl list object")
    for item in items:
        if not isinstance(item, dict):
            raise _Bad(f"{label} entry is not an object")
    return items


def _sha(value: Any, label: str) -> str:
    text = _norm_sha(value)
    if not SHA_RE.match(text):
        raise _Bad(f"{label} must be a 40-character hex sha")
    return text


def _soak(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise _Bad("soak_minutes must be a number")
    try:
        soak = float(value)
    except ValueError as exc:
        raise _Bad("soak_minutes must be a number") from exc
    if soak < 0 or math.isnan(soak) or math.isinf(soak):
        raise _Bad("soak_minutes must be zero or more")
    return soak


def _fmt_min(soak: float) -> str:
    if soak == int(soak):
        return str(int(soak))
    return str(soak)


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise _Bad(f"{label} must be an RFC3339 timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise _Bad(f"{label} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise _Bad(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


class _Bad(Exception):
    pass


def _load_json(path: str) -> Any:
    if path == "-":
        raw = sys.stdin.read()
        label = "stdin"
    else:
        try:
            with open(path, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            raise _Bad(str(exc)) from exc
        label = path
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _Bad(f"{label}: {exc}") from exc


def _document(argv: list[str]) -> dict:
    parser = argparse.ArgumentParser(description="Decide whether a platform SHA may be promoted to PROD")
    parser.add_argument("--input", help="JSON object (file, or - for stdin)")
    parser.add_argument("--platform-sha")
    parser.add_argument("--ui-sha")
    parser.add_argument("--runs", help="kubectl get pipelinerun -o json")
    parser.add_argument("--taskruns", help="kubectl get taskrun -o json")
    parser.add_argument("--now", help="RFC3339 time the decision is made at")
    parser.add_argument("--soak-minutes", default=None)
    args = parser.parse_args(argv)
    if args.input:
        doc = _load_json(args.input)
        if not isinstance(doc, dict):
            raise _Bad("--input must be a JSON object")
        return doc
    flagged = any([
        args.platform_sha, args.ui_sha, args.runs, args.taskruns, args.now,
        args.soak_minutes is not None,
    ])
    if flagged:
        doc: dict[str, Any] = {
            "platform_sha": args.platform_sha,
            "ui_sha": args.ui_sha,
            "now": args.now,
            "soak_minutes": 10 if args.soak_minutes is None else args.soak_minutes,
        }
        if args.runs:
            doc["pipelineruns"] = _load_json(args.runs)
        if args.taskruns:
            doc["taskruns"] = _load_json(args.taskruns)
        return doc
    if sys.stdin.isatty():
        raise _Bad("pass --input, flags, or a JSON object on stdin")
    doc = json.loads(sys.stdin.read() or "null")
    if not isinstance(doc, dict):
        raise _Bad("stdin must be a JSON object")
    return doc


def main(argv: list[str] | None = None) -> int:
    try:
        code, text = decide(_document(list(sys.argv[1:] if argv is None else argv)))
    except _Bad as exc:
        print(f"malformed input: {exc}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"malformed input: {exc}")
        return 1
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
