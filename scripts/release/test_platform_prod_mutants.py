"""Each planted weakening must fail the named behavioral/structure test."""

import copy
import os
import subprocess
import sys

import pytest
import yaml

from test_platform_prod_gate import PIPELINE, ROOT


@pytest.mark.parametrize(
    "mutation,named_test",
    [
        ("order", "test_gate_order"),
        ("resolve", "test_mirror_resolution_refuses"),
        ("ci", "test_ci_refuses"),
        ("stg", "test_stg_refuses"),
        ("latest", "test_latest_stg_selects_newest"),
        ("sha", "test_checked_sha_is_built"),
        ("errors", "test_query_fail_closed"),
        ("identity-message", "test_default_identity_refuses"),
        ("image", "test_read_only_same_image"),
        ("ci-prefix", "test_ci_refuses[wrong-sha]"),
        ("ci-running", "test_ci_refuses[running]"),
        ("stg-prefix", "test_stg_refuses[wrong-sha]"),
        ("no-result", "test_stg_refuses[no-result]"),
        ("prod-as-stg", "test_prod_run_is_not_stg"),
        ("mirror-sha", "test_full_sha_mirror_mismatch"),
        ("task-name", "test_stg_refuses[task-name]"),
        ("child-kind", "test_stg_refuses[child-kind]"),
        ("stg-state", "test_stg_order_refuses[newest-running]"),
        ("completion-order", "test_stg_order_refuses[older-later]"),
    ],
)
def test_planted_violation(tmp_path, mutation, named_test):
    doc = copy.deepcopy(yaml.safe_load(PIPELINE.read_text()))
    tasks = {t["name"]: t for t in doc["spec"]["tasks"]}
    step = tasks["check-source"]["taskSpec"]["steps"][0]
    if mutation == "order":
        tasks["check-source"]["runAfter"] = ["preflight-stg"]
    elif mutation == "sha":
        next(p for p in tasks["clone-platform"]["params"] if p["name"] == "revision")[
            "value"
        ] = "$(params.revision)"
    elif mutation == "image":
        step["image"] = "alpine:3.20"
    else:
        before, after = {
            "resolve": ("if len(candidates) != 1:", "if not candidates:"),
            "ci": (
                'if classify(runs, "bifrost-platform", sha) != "succeeded":',
                "if False:",
            ),
            "stg": ("if len(commits) != 1 or commits[0] != sha:", "if False:"),
            "latest": (
                'latest = max(run_time(r, "creationTimestamp") for r in stg)',
                'latest = min(run_time(r, "creationTimestamp") for r in stg)',
            ),
            "ci-prefix": (
                'params.get("revision") != sha',
                '(params.get("revision") or "x")[:7] != sha[:7]',
            ),
            "ci-running": (
                'if state == "True":\n        ',
                'if state != "False":\n        ',
            ),
            "stg-prefix": ("commits[0] != sha", "commits[0][:7] != sha[:7]"),
            "no-result": (
                "if len(commits) != 1 or commits[0] != sha:",
                "if commits and (len(commits) != 1 or commits[0] != sha):",
            ),
            "prod-as-stg": (
                '_pipeline_name(r) == "bifrost-deliver-platform"',
                '_pipeline_name(r).startswith("bifrost-deliver-platform")',
            ),
            "mirror-sha": (
                "if SHA_RE.fullmatch(revision) and sha != revision:",
                "if False:",
            ),
            "task-name": ('task["metadata"]["name"] != children[0]["name"]', "False"),
            "child-kind": (' and c["kind"] == "TaskRun"', ""),
            "stg-state": ('if state != "True":', "if False:"),
            "completion-order": (
                'if run is not chosen and run_time(run, "completionTime") >= latest:',
                "if False:",
            ),
            "errors": ("        return 1\n", "        return 0\n"),
            "identity-message": (
                "identity cannot read PipelineRuns/TaskRuns in cicd",
                "query failed",
            ),
        }[mutation]
        assert before in step["script"]
        step["script"] = step["script"].replace(before, after)
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(doc))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "scripts/release/test_platform_prod_gate.py::" + named_test,
            "-q",
        ],
        cwd=ROOT,
        env={**os.environ, "GATE_PIPELINE": str(path)},
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert (
        "FAILED scripts/release/test_platform_prod_gate.py::" + named_test
        in result.stdout
    )
