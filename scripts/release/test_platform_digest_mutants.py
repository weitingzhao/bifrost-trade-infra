"""Plant guard weakenings in a temporary Task; each must turn behavioral tests red."""

import ast
import copy
import os
import re
import subprocess
import sys

import pytest
import yaml

from embed_platform_digest_verify import ROOT, TASK

# The first eight exercise the principal guards; the rest cover each remaining
# predicate separately. Mutants never alter the real Task or verifier source.
MUTATIONS = [
    (
        "pod-rs-uid",
        'if rm["uid"] != pr["uid"]:',
        "if False:",
        "test_refuses and rs-uid",
    ),
    (
        "rs-deployment-uid",
        'dr["uid"] != metadata["uid"]',
        "False",
        "test_refuses and (rs-deployment-uid or rs-other-deployment or foreign-replacement)",
    ),
    (
        "controller",
        'if r.get("controller") is True',
        "if True",
        "test_refuses and (no-controller or rs-no-controller)",
    ),
    (
        "kind",
        'if ref["apiVersion"] != "apps/v1" or ref["kind"] != kind:',
        "if False:",
        "test_refuses and (job-owner or statefulset-owner or daemonset-owner or pod-api-version or rs-kind or rs-api-version)",
    ),
    (
        "current-revision",
        'rm["annotations"][REVISION] != revision',
        "False",
        "test_refuses and old-revision",
    ),
    (
        "pod-count",
        "if len(active) != replicas:",
        "if False:",
        "test_refuses and (no-pods or only-terminating or fewer-replicas)",
    ),
    (
        "image-digest",
        "if not DIGEST_RE.fullmatch(digest) or digest != expected:",
        "if False:",
        "test_refuses and (image-mismatch or workers-console-digest or empty-image or malformed-image or console-only)",
    ),
    (
        "running",
        'if set(cs["state"]) != {"running"} or not isinstance(cs["state"]["running"], dict) or cs["ready"] is not True:',
        'if cs["ready"] is not True:',
        "test_refuses and (waiting or terminated or extra-state)",
    ),
    (
        "observed-generation",
        'status["observedGeneration"] != generation',
        "False",
        "test_refuses and generation",
    ),
    (
        "positive-replicas",
        "if type(replicas) is not int or replicas < 1:",
        "if False:",
        "test_zero_replicas_not_vacuous_success",
    ),
    (
        "replica-status",
        'if any(type(status[k]) is not int or status[k] != replicas for k in ("replicas", "updatedReplicas", "readyReplicas", "availableReplicas")):',
        "if False:",
        "test_refuses and (replica-count or updated-count or ready-count or available-count)",
    ),
    (
        "pod-phase",
        'if state["phase"] != "Running":',
        "if False:",
        "test_refuses and pending",
    ),
    (
        "pod-containers",
        'if len(containers) != 1 or containers[0]["name"] != container_name:',
        "if False:",
        "test_refuses and (extra-container or wrong-container)",
    ),
    (
        "extra-containers",
        'if state.get("initContainerStatuses") or state.get("ephemeralContainerStatuses") or ps.get("initContainers") or ps.get("ephemeralContainers"):',
        "if False:",
        "test_refuses and (init-status or ephemeral-status or init-spec or ephemeral-spec)",
    ),
    (
        "status-unique",
        'if len(statuses) != 1 or statuses[0]["name"] != container_name:',
        "if False:",
        "test_refuses and (duplicate-status or wrong-status-name)",
    ),
    ("ready", 'or cs["ready"] is not True', "", "test_refuses and not-ready"),
    ("spec-digest", "if require_spec:", "if False:", "test_spec_digest_check"),
    (
        "fail-closed",
        "        return 1\n",
        "        return 0\n",
        "test_read_errors and failed",
    ),
    (
        "required-digests",
        "if not DIGEST_RE.fullmatch(api_digest) or not DIGEST_RE.fullmatch(console_digest):",
        "if False:",
        "test_bad_digest",
    ),
    (
        "ignore-terminating",
        'if "deletionTimestamp" not in p["metadata"]',
        "if True",
        "test_terminating_old_pod_ignored",
    ),
]


@pytest.mark.parametrize(
    "name,before,after,selection", MUTATIONS, ids=[m[0] for m in MUTATIONS]
)
def test_planted_violation(tmp_path, name, before, after, selection):
    doc = copy.deepcopy(yaml.safe_load(TASK.read_text()))
    step = next(s for s in doc["spec"]["steps"] if s["name"] == "verify-digests")
    # Locate multiline guards by their fixed refusal, so formatting cannot turn
    # a mutation into a source-string mismatch instead of a behavioral failure.
    reasons = {
        "running": "container is not running and ready",
        "replica-status": "Deployment replicas are not fully rolled out",
        "extra-containers": "init or ephemeral containers are not supported",
        "required-digests": "invalid expected digest",
    }
    if name in reasons:
        guard = next(
            node
            for node in ast.walk(ast.parse(step["script"]))
            if isinstance(node, ast.If)
            and any(
                isinstance(item, ast.Raise)
                and isinstance(item.exc, ast.Call)
                and item.exc.args
                and isinstance(item.exc.args[0], ast.Constant)
                and item.exc.args[0].value == reasons[name]
                for item in node.body
            )
        )
        before = ast.get_source_segment(step["script"], guard.test)
        after = 'cs["ready"] is not True' if name == "running" else "False"
    assert before in step["script"]
    step["script"] = step["script"].replace(before, after)
    path = tmp_path / "mutant-task.yaml"
    path.write_text(yaml.safe_dump(doc))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "scripts/release/test_platform_digest_verify.py",
            "-q",
            "-k",
            selection,
        ],
        cwd=ROOT,
        env={**os.environ, "DIGEST_TASK": str(path)},
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    failed = len(
        re.findall(
            r"^FAILED scripts/release/test_platform_digest_verify.py::",
            result.stdout,
            re.M,
        )
    )
    assert failed > 0, result.stdout + result.stderr
    print(f"MUTANT {name}: {failed} behavioral tests red")
