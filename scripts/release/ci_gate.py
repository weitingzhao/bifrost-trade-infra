"""Decide whether a SHA's CI run may ship (TD-95, TD-155).

Exit 0: a Succeeded ci-* run matches the repo and SHA, or --allow-red is set.
Exit 1: a terminal failure and no --allow-red.
Exit 2: no terminal run yet (the caller may wait and retry).

A run matches when spec.params repo + revision equal the pair, and the
PipelineRun belongs to bifrost-ci-python or bifrost-ci-frontend.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Iterable, Optional


CI_PIPELINES = frozenset({"bifrost-ci-python", "bifrost-ci-frontend"})


def _params(run: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in (run.get("spec") or {}).get("params") or []:
        name = str(item.get("name", ""))
        if name:
            out[name] = str(item.get("value", ""))
    return out


def _pipeline_name(run: dict) -> str:
    labels = ((run.get("metadata") or {}).get("labels") or {})
    named = labels.get("tekton.dev/pipeline") or ""
    if named:
        return str(named)
    ref = ((run.get("spec") or {}).get("pipelineRef") or {}).get("name") or ""
    return str(ref)


def _succeeded(run: dict) -> Optional[str]:
    """Return True/False/None (still running) for the Succeeded condition."""
    for cond in ((run.get("status") or {}).get("conditions") or []):
        if cond.get("type") == "Succeeded":
            status = str(cond.get("status", ""))
            if status == "True":
                return "True"
            if status == "False":
                return "False"
            return None
    return None


def classify(runs: Iterable[dict], repo: str, sha: str) -> str:
    """Return succeeded, failed, or missing for repo@sha."""
    saw_failure = False
    for run in runs:
        if _pipeline_name(run) not in CI_PIPELINES:
            continue
        params = _params(run)
        if params.get("repo") != repo or params.get("revision") != sha:
            continue
        state = _succeeded(run)
        if state == "True":
            return "succeeded"
        if state == "False":
            saw_failure = True
    return "failed" if saw_failure else "missing"


def gate(runs: Iterable[dict], pairs: list[tuple[str, str]], allow_red: str) -> tuple[int, str]:
    """pairs is (repo, sha). allow_red empty means a red or missing run refuses."""
    lines = []
    worst = 0
    for repo, sha in pairs:
        state = classify(runs, repo, sha)
        lines.append(f"{repo} {sha} ci={state}")
        if state == "succeeded":
            continue
        if allow_red:
            lines.append(f"  allow-red: {allow_red}")
            continue
        worst = 1 if state == "failed" else max(worst, 2)
    if worst == 0:
        return 0, "\n".join(lines)
    if worst == 1:
        return 1, "REFUSED: CI failed for a SHA this release ships\n" + "\n".join(lines)
    return 2, "CI has not finished for a SHA this release ships\n" + "\n".join(lines)


def _load_runs(paths: list[str]) -> list[dict]:
    runs: list[dict] = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        if isinstance(doc, dict) and "items" in doc:
            runs.extend(doc["items"])
        elif isinstance(doc, list):
            runs.extend(doc)
        else:
            raise SystemExit(f"{path}: expected a PipelineRun list or a kubectl list object")
    return runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refuse a release whose SHA has no Succeeded CI run")
    parser.add_argument("--runs", action="append", default=[], help="kubectl get pipelineruns -o json")
    parser.add_argument("--allow-red", default="", help="Owner reason that permits a red or missing run")
    parser.add_argument("pairs", nargs="*", help="repo=sha")
    args = parser.parse_args(argv)
    pairs: list[tuple[str, str]] = []
    for item in args.pairs:
        repo, sep, sha = item.partition("=")
        if not sep or len(sha) != 40:
            print(f"bad pair {item!r} (want repo=<40-char sha>)", file=sys.stderr)
            return 2
        pairs.append((repo, sha))
    if not pairs:
        print("no repo=sha pairs", file=sys.stderr)
        return 2
    code, text = gate(_load_runs(args.runs), pairs, args.allow_red.strip())
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
