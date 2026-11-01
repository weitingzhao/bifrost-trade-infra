"""Decide whether a SHA's CI run may ship (TD-95, TD-155).

Exit 0: a Succeeded ci-* run matches the repo and SHA, or --allow-red is set.
Exit 1: a terminal failure and no --allow-red.
Exit 2: no terminal run yet (the caller may wait and retry).

A run matches when its repo (spec.params repo, else the bifrost.io/repo label)
and spec.params revision equal the pair, and the
PipelineRun belongs to bifrost-ci-python, bifrost-ci-frontend, or bifrost-ci-platform.

R5:5.7-1: a bifrost-ci-platform run whose api-scope result is console ran only
the Go tests a console change can reach; one SHA can have such a run green and
a full run red. A full run decides: any full run Succeeded is succeeded, else
any full run Failed is failed. A run without the api-scope result is full: the
platform pipeline before R5:5.7-1 always ran every test, and the other
pipelines have no such result. Only when no full run has finished do the
console runs count: as succeeded for a push to main (push-main.sh: a lane's
commit gets only console runs until it is on main), as console (wait for a full
run, exit 2) with --require-full, which a release asks for (release.sh, the
platform PROD source gate).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Iterable, Optional


CI_PIPELINES = frozenset({"bifrost-ci-python", "bifrost-ci-frontend", "bifrost-ci-platform"})


def _params(run: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in (run.get("spec") or {}).get("params") or []:
        name = str(item.get("name", ""))
        if name:
            out[name] = str(item.get("value", ""))
    return out


def _repo(run: dict, params: dict[str, str]) -> str:
    """The repo a CI run checked. bifrost-ci-python carries it as a param;
    bifrost-ci-frontend (and the ui-push binding) only as the bifrost.io/repo label."""
    if params.get("repo"):
        return params["repo"]
    labels = ((run.get("metadata") or {}).get("labels") or {})
    return str(labels.get("bifrost.io/repo") or "")


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


def _full(run: dict) -> bool:
    """True when the run ran every test (R5:5.7-1): no api-scope result (an older
    platform run, or another pipeline), or exactly one, full. Anything else is not."""
    scopes = [str(r.get("value", "")) for r in ((run.get("status") or {}).get("results") or [])
              if isinstance(r, dict) and r.get("name") == "api-scope"]
    return not scopes or scopes == ["full"]


def classify(runs: Iterable[dict], repo: str, sha: str, require_full: bool = False) -> str:
    """Return succeeded, failed, missing, or (require_full) console for repo@sha.

    A full run decides; console runs count only when no full run has finished,
    and with require_full not as a success (console: a full run is still owed)."""
    seen = {(True, "True"): False, (True, "False"): False, (False, "True"): False, (False, "False"): False}
    for run in runs:
        if _pipeline_name(run) not in CI_PIPELINES:
            continue
        params = _params(run)
        if _repo(run, params) != repo or params.get("revision") != sha:
            continue
        state = _succeeded(run)
        if state == "True":
            seen[(_full(run), "True")] = True
        elif state == "False":
            seen[(_full(run), "False")] = True
    if seen[(True, "True")]:
        return "succeeded"
    if seen[(True, "False")]:
        return "failed"
    if seen[(False, "True")]:
        return "console" if require_full else "succeeded"
    if seen[(False, "False")]:
        return "failed"
    return "missing"


def gate(runs: Iterable[dict], pairs: list[tuple[str, str]], allow_red: str,
         require_full: bool = False) -> tuple[int, str]:
    """pairs is (repo, sha). allow_red empty means a red or missing run refuses."""
    lines = []
    worst = 0
    for repo, sha in pairs:
        state = classify(runs, repo, sha, require_full)
        lines.append(f"{repo} {sha} ci={state}")
        if state == "succeeded":
            continue
        if state == "console":
            lines.append("  only console-scope runs (api-scope=console) succeeded; a release needs a full run "
                         "(the push to main runs one)")
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
    parser.add_argument("--require-full", action="store_true",
                        help="a release: a run with api-scope=console does not count as a success (R5:5.7-1)")
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
    code, text = gate(_load_runs(args.runs), pairs, args.allow_red.strip(), args.require_full)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
