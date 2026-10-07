#!/usr/bin/env python3
"""Ratchet for the release-chain lane (TD-162, TD-155, TD-95, TD-122, TD-121).

No cluster. Fails if a deliver/build pipeline drops its lint-test or window
check, if the Tekton window decision drifts from window_decision.py, or if
the research rotation helper hard-codes one Deployment.
"""

from __future__ import annotations

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

    for rel in (
        "k8s/cicd/tekton/pipeline-build-market-data.yaml",
        "k8s/cicd/tekton/pipeline-build-ib-gateway.yaml",
    ):
        text = (ROOT / rel).read_text()
        check("name: release-window" in text, f"{rel} has no release-window task")
        first = task_block(text, "release-window")
        check("runAfter" not in first, f"{rel} release-window is not the first task")

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

    if failures:
        print("\n".join(failures))
        return 1
    print(f"check-release-chain: ok ({len(cases)} window cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
