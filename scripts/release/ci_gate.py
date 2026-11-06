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
pipelines have no such result. A malformed api-scope (two, empty, another
value) counts for nothing, as B5 reads it. Only when no full run has finished do the
console runs count: as succeeded for a push to main (push-main.sh: a lane's
commit gets only console runs until it is on main), as console (wait for a full
run, exit 2) with --require-full, which a release asks for (release.sh, the
platform PROD source gate).

Reuse runs carry tested-by. Only a listed, earlier, green original with no reuse
edge and identical platform-tree, ui-commit and infra-commit supplies their scope.
Legacy runs without reuse evidence retain their existing interpretation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
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


def _scope(run: dict) -> str:
    """full, console, or malformed: how much of the Go tests the run ran (R5:5.7-1).
    No api-scope result is full (an older platform run, or another pipeline); exactly
    one, full or console, is that; anything else (two, empty, another value) is
    malformed, as B5 reads it: neither a success nor a full run."""
    scopes = [str(r.get("value", "")) for r in ((run.get("status") or {}).get("results") or [])
              if isinstance(r, dict) and r.get("name") == "api-scope"]
    if not scopes:
        return "full"
    if scopes in (["full"], ["console"]):
        return scopes[0]
    # A landing run that tested what its change reaches (countdown 20) is a
    # partial run, as console is: a success, and not a full run.
    if scopes == ["incremental"]:
        return "console"
    return "malformed"


def _results(run: dict, name: str) -> list:
    return [r.get("value") for r in (run.get("status") or {}).get("results") or []
            if isinstance(r, dict) and r.get("name") == name]


def _original(run: dict, runs: list[dict]) -> Optional[dict]:
    """Resolve one reuse edge, failing closed on missing or ambiguous evidence."""
    names = _results(run, "tested-by")
    if len(names) != 1 or not isinstance(names[0], str) or not names[0]:
        return None
    candidates = [r for r in runs if (r.get("metadata") or {}).get("name") == names[0]
                  and (r.get("metadata") or {}).get("namespace") == (run.get("metadata") or {}).get("namespace")]
    if len(candidates) != 1:
        return None
    original = candidates[0]
    if (_pipeline_name(run) != "bifrost-ci-platform"
            or _pipeline_name(original) != "bifrost-ci-platform"
            or _succeeded(original) != "True" or _results(original, "tested-by")):
        return None
    for name in ("platform-tree", "ui-commit", "infra-commit"):
        values = _results(run, name)
        if len(values) != 1 or not isinstance(values[0], str) or not values[0] or values != _results(original, name):
            return None
    try:
        before, after = [datetime.fromisoformat(r["metadata"]["creationTimestamp"].replace("Z", "+00:00"))
                         for r in (original, run)]
        if before.tzinfo is None or after.tzinfo is None or before >= after:
            return None
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    return original


def _effective_scope(run: dict, runs: list[dict]) -> str:
    if not _results(run, "tested-by"):
        return _scope(run)
    original = _original(run, runs)
    return _scope(original) if original is not None else "malformed"


def classify(runs: Iterable[dict], repo: str, sha: str, require_full: bool = False) -> str:
    """Return succeeded, failed, missing, malformed, or (require_full) console for repo@sha.

    A full run decides; console runs count only when no full run has finished,
    and with require_full not as a success (console: a full run is still owed).
    A run with a malformed api-scope counts for nothing; when nothing else
    finished, the answer is malformed."""
    runs = list(runs)
    seen = {(scope, state): False for scope in ("full", "console", "malformed") for state in ("True", "False")}
    for run in runs:
        if _pipeline_name(run) not in CI_PIPELINES:
            continue
        params = _params(run)
        if _repo(run, params) != repo or params.get("revision") != sha:
            continue
        state = _succeeded(run)
        if state == "True":
            seen[(_effective_scope(run, runs), "True")] = True
        elif state == "False":
            seen[(_effective_scope(run, runs), "False")] = True
    if seen[("full", "True")]:
        return "succeeded"
    if seen[("full", "False")]:
        return "failed"
    if seen[("console", "True")]:
        return "console" if require_full else "succeeded"
    if seen[("console", "False")]:
        return "failed"
    if seen[("malformed", "True")] or seen[("malformed", "False")]:
        return "malformed"
    return "missing"


def gate(runs: Iterable[dict], pairs: list[tuple[str, str]], allow_red: str,
         require_full: bool = False) -> tuple[int, str]:
    """pairs is (repo, sha). allow_red empty means a red or missing run refuses."""
    runs = list(runs)
    lines = []
    worst = 0
    for repo, sha in pairs:
        state = classify(runs, repo, sha, require_full)
        lines.append(f"{repo} {sha} ci={state}")
        if state == "succeeded":
            for run in runs:
                params = _params(run)
                if (_repo(run, params) == repo and params.get("revision") == sha
                        and _succeeded(run) == "True" and _results(run, "tested-by")
                        and _effective_scope(run, runs) in (("full",) if require_full else ("full", "console"))):
                    original = _original(run, runs)
                    lines.append(f"  tested by {original['metadata']['name']}")
            continue
        if state == "console":
            lines.append("  only console-scope runs (api-scope=console) succeeded; a release needs a full run "
                         "(the push to main runs one)")
        if state == "malformed":
            lines.append("  the only finished runs have a malformed api-scope result (two, empty or unknown); "
                         "they count for nothing: run CI again")
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
