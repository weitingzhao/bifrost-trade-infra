"""ci_gate finds a CI run for repo@sha whether the repo is a param or a label."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from ci_gate import classify  # noqa: E402

SHA = "a" * 40


def _run(pipeline, params, labels=None, ok="True"):
    return {
        "metadata": {"labels": {"tekton.dev/pipeline": pipeline, **(labels or {})}},
        "spec": {"params": [{"name": k, "value": v} for k, v in params.items()]},
        "status": {"conditions": [{"type": "Succeeded", "status": ok}]},
    }


def test_python_run_with_repo_param() -> None:
    runs = [_run("bifrost-ci-python", {"repo": "bifrost-trade-core", "revision": SHA})]
    assert classify(runs, "bifrost-trade-core", SHA) == "succeeded"


def test_frontend_run_with_repo_only_as_label() -> None:
    # 2026-10-07: ci-frontend-9ptxp had revision + uiRevision params and the repo
    # only in bifrost.io/repo, so release.sh read it as missing.
    runs = [_run("bifrost-ci-frontend", {"revision": SHA, "uiRevision": "main"},
                 {"bifrost.io/repo": "bifrost-trade-frontend"})]
    assert classify(runs, "bifrost-trade-frontend", SHA) == "succeeded"


def test_label_of_another_repo_does_not_match() -> None:
    runs = [_run("bifrost-ci-frontend", {"revision": SHA}, {"bifrost.io/repo": "bifrost-ui"})]
    assert classify(runs, "bifrost-trade-frontend", SHA) == "missing"


def test_failed_run_reads_failed() -> None:
    runs = [_run("bifrost-ci-frontend", {"revision": SHA}, {"bifrost.io/repo": "bifrost-trade-frontend"}, ok="False")]
    assert classify(runs, "bifrost-trade-frontend", SHA) == "failed"
