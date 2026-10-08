#!/usr/bin/env python3
"""Ratchet for the release-chain lane (TD-162, TD-155, TD-95, TD-122, TD-121, TD-263).

No cluster. Fails if a deliver/build pipeline drops its lint-test or window
check, if the Tekton window decision drifts from window_decision.py, or if
the research rotation helper hard-codes one Deployment.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

import window_decision as wd  # noqa: E402

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def task_block(text: str, name: str) -> str:
    match = re.search(rf"\n    - name: {re.escape(name)}\n(.*?)(?=\n    - name: |\Z)", text, re.S)
    return match.group(1) if match else ""


def workspace_root() -> Path:
    return Path(os.environ.get("BIFROST_WORKSPACE", str(ROOT.parent)))


def collect_build_deliver_pipeline_paths() -> dict[str, Path]:
    """Map Pipeline metadata.name -> YAML for bifrost-build-* / bifrost-deliver-*."""
    paths: dict[str, Path] = {}
    tekton = ROOT / "k8s/cicd/tekton"
    for path in sorted(tekton.glob("pipeline-*.yaml")):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"\n  name: (bifrost-(?:build|deliver)-[^\n]+)", text)
        if match:
            paths[match.group(1).strip()] = path
    flex_root = os.environ.get("FLEX_QUERY_ROOT")
    if flex_root:
        flex_repo = Path(flex_root)
    else:
        flex_repo = workspace_root() / "bifrost-platform-plugin-flex-query"
    flex_yaml = flex_repo / "k8s/cicd/pipeline-build.yaml"
    if flex_yaml.is_file():
        text = flex_yaml.read_text(encoding="utf-8")
        match = re.search(r"\n  name: (bifrost-(?:build|deliver)-[^\n]+)", text)
        if match:
            paths[match.group(1).strip()] = flex_yaml
    return paths


def first_task_name(pipeline_yaml: str) -> str | None:
    match = re.search(
        r"\n  tasks:\n(?:    #.*\n)*    - name: ([^\n]+)",
        pipeline_yaml,
    )
    return match.group(1).strip() if match else None


def assert_guarded_pipelines_release_window_first() -> None:
    """TD-263: every window_decision.MUST_HOLD pipeline runs release-window first.

    Trade STG/PROD deliver pipelines are gated at platform-api; Tekton runs
    release-window first only for GUARDED plugin/research builds. flex-query
    YAML lives in bifrost-platform-plugin-flex-query — set BIFROST_WORKSPACE or
    FLEX_QUERY_ROOT when this repo is checked out without its sibling.
    """
    paths = collect_build_deliver_pipeline_paths()
    for pipeline in sorted(wd.MUST_HOLD):
        path = paths.get(pipeline)
        if path is None:
            check(
                False,
                f"{pipeline}: pipeline YAML not found "
                "(sibling bifrost-platform-plugin-flex-query or FLEX_QUERY_ROOT)",
            )
            continue
        text = path.read_text(encoding="utf-8")
        first = first_task_name(text)
        label = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        check(
            first == "release-window",
            f"{label}: first task is {first!r}, want release-window ({pipeline})",
        )
        block = task_block(text, "release-window")
        check("runAfter" not in block, f"{label}: release-window is not the first task ({pipeline})")


def load_task_decide():
    text = (ROOT / "k8s/cicd/tekton/task-release-window.yaml").read_text()
    match = re.search(r"script: \|\n(?P<body>(?:        .*\n| *\n)*)", text)
    if not match:
        raise SystemExit("task-release-window.yaml has no script")
    lines = []
    for line in match.group("body").splitlines():
        lines.append(line[8:] if line.startswith("        ") else line.strip())
    ns: dict = {}
    exec("\n".join(lines), ns, ns)
    return ns["decide"]


def main() -> int:
    task_decide = load_task_decide()
    cases = [
        (None, "bifrost-deliver-research"),
        ({"who": "ada@host", "what": "bifrost-research"}, "bifrost-deliver-research"),
        ({"who": "ada@host", "what": "bifrost-trade-core"}, "bifrost-deliver-research"),
        (None, "bifrost-deliver-stg"),
        ({"who": "ada@host", "what": ",".join(sorted(wd.TRADE_REPOS))}, "bifrost-deliver-stg"),
        (None, "bifrost-build-ib-gateway"),
        ({"who": "ada@host", "what": "bifrost-platform-plugin"}, "bifrost-build-market-data"),
    ]
    for window, pipeline in cases:
        got = task_decide(window, pipeline)
        want = wd.decide(window, pipeline)
        check(got == want, f"window task drifted for {pipeline}: {got!r} != {want!r}")

    research_pipelines = {
        "k8s/cicd/tekton/pipeline-deliver-research.yaml": "build-research",
        "k8s/cicd/tekton/pipeline-build-research-dagster.yaml": "kaniko",
    }
    for rel, build in research_pipelines.items():
        text = (ROOT / rel).read_text()
        check("name: validate-revision" in text, f"{rel} does not validate the revision")
        check("name: release-window" in text, f"{rel} has no release-window task")
        check("name: lint-test" in text, f"{rel} has no lint-test task")
        check("expectSha" in text, f"{rel} does not wait for the mirrored SHA")
        block = task_block(text, build)
        check("lint-test" in block and "runAfter" in block, f"{rel} {build} does not runAfter lint-test")
        rev = text.split("name: revision", 1)[1][:240]
        check("default: main" not in rev, f"{rel} still defaults revision to main")
        check("40-character" in text, f"{rel} does not document the SHA revision")

    assert_guarded_pipelines_release_window_first()

    mirror = (ROOT / "k8s/cicd/tekton/task-gitea-mirror-sync.yaml").read_text()
    check("expectSha" in mirror and "git/commits" in mirror, "mirror-sync does not poll for the SHA")

    ib = (ROOT / "k8s/cicd/tekton/pipeline-build-ib-gateway.yaml").read_text()
    check("--digest-file=$(results.digest.path)" in ib, "ib-gateway build does not record a digest")
    check("GIT_SHA" in ib, "ib-gateway build does not bake the git SHA")
    check("registry.cicd.svc.cluster.local:5000" in ib, "ib-gateway build does not push to the cluster registry")

    release = (ROOT / "scripts/release/release.sh").read_text()
    check("hold)" in release, "release.sh has no hold command")
    check("--allow-red" in release and "ci_gate.py" in release, "release.sh does not gate on CI")
    check("TRADE_WHAT=" in release and "bifrost-release-window" in release, "release.sh does not publish the window")
    check("bootstrap-gitea-mirrors.sh" in release, "release.sh does not sync the Gitea mirror")

    helper = (ROOT / "scripts/research-secret-restart.sh").read_text()
    check("deployment/research-api" not in helper, "rotation helper hard-codes research-api")
    check("research_secret_holders" in helper, "rotation helper does not derive holders")
    check("bifrost.io/secret-checksum" in helper, "rotation helper does not stamp a checksum annotation")

    for script in ("scripts/release/release.sh", "scripts/research-secret-restart.sh"):
        proc = subprocess.run(["bash", "-n", str(ROOT / script)], capture_output=True, text=True)
        check(proc.returncode == 0, f"bash -n {script} failed: {proc.stderr.strip()}")

    hold_test = ROOT / "scripts/release/test_release_hold_interrupt.sh"
    proc = subprocess.run(["bash", str(hold_test)], capture_output=True, text=True)
    check(proc.returncode == 0, f"test_release_hold_interrupt.sh failed: {proc.stderr.strip() or proc.stdout.strip()}")

    if failures:
        print("\n".join(failures))
        return 1
    print(f"check-release-chain: ok ({len(cases)} window cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
