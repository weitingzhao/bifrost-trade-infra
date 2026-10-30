import json
import shutil

import pytest
import yaml

from pins import ROOT, contract


def load(name):
    return yaml.safe_load((ROOT / "k8s/cicd/tekton" / name).read_text())


def test_unbuilt_is_rejected_and_real_pin_must_match_all_tasks(tmp_path):
    shutil.copytree(ROOT / "docker/s5-checker", tmp_path / "docker/s5-checker")
    target = tmp_path / "k8s/cicd/tekton"
    target.mkdir(parents=True)
    for p in (ROOT / "k8s/cicd/tekton").glob("*s5*"):
        shutil.copy(p, target / p.name)
    zero, pin = "sha256:" + "0" * 64, "sha256:" + "1" * 64
    (tmp_path / "docker/s5-checker/IMAGE_DIGEST").write_text(zero)
    with pytest.raises(ValueError, match="UNBUILT"):
        contract(tmp_path)
    (tmp_path / "docker/s5-checker/IMAGE_DIGEST").write_text(pin)
    for p in target.glob("task-s5-*.yaml"):
        p.write_text(p.read_text().replace(zero, pin))
    assert contract(tmp_path)["image"].endswith(pin)
    p = target / "task-s5-check.yaml"
    p.write_text(p.read_text().replace(pin, zero))
    with pytest.raises(ValueError, match="pin mismatch"):
        contract(tmp_path)


def test_mandatory_task_has_no_skip_or_inline_escape():
    c = contract(ready=False)
    pipeline = c["pipeline"]
    assert [t["name"] for t in pipeline["tasks"]] == ["s5-fetch", "s5-check"]
    assert "finally" not in pipeline
    for task in pipeline["tasks"]:
        assert not set(task) & {"when", "taskSpec", "matrix", "retries", "onError"}
        assert set(task["taskRef"]) == {"name"}
        p = {p["name"]: p["value"] for p in task["params"]}
        assert p["base"] == "$(params.base)" and p["revision"] == "$(params.revision)"
        assert (
            p["keyDigest"] == "$(params.keyDigest)"
            and p["generation"] == "$(params.generation)"
        )
        assert (
            p["uiRevision"] == "$(params.uiRevision)"
            and p["ciUID"] == "$(context.pipelineRun.uid)"
        )
    assert pipeline["tasks"][1]["runAfter"] == ["s5-fetch"]
    assert all(
        r["value"].startswith("$(tasks.s5-check.results.") for r in pipeline["results"]
    )
    assert {r["name"] for r in pipeline["results"]} == {
        r["name"] for r in c["tasks"]["check"]["results"]
    }


def test_readonly_mount_credentials_and_network_boundary():
    c = contract(ready=False)
    check = c["tasks"]["check"]
    assert check["workspaces"] == [
        {"name": "trees", "mountPath": "/workspace/trees", "readOnly": True}
    ]
    for stage, task in c["tasks"].items():
        assert len(task["steps"]) == 1
        step = task["steps"][0]
        assert step["command"] == ["python3", "-I", "/opt/s5/runner.py"]
        assert step["args"] == [stage]
        assert step["securityContext"]["allowPrivilegeEscalation"] is False
        assert step["securityContext"]["readOnlyRootFilesystem"] is True
        assert step["securityContext"]["capabilities"]["drop"] == ["ALL"]
        assert not any("valueFrom" in e for e in step["env"])
        assert not set(step) & {"script", "envFrom"}
        assert all(set(v) == {"name", "emptyDir"} for v in task["volumes"])
        assert step["computeResources"]["limits"] == {"cpu": "2", "memory": "2Gi"}
    template = c["runTemplate"]["taskRunTemplate"]
    assert template["serviceAccountName"] == "bifrost-s5"
    assert template["podTemplate"]["automountServiceAccountToken"] is False
    sa = load("s5-service-account.yaml")
    assert (
        sa["automountServiceAccountToken"] is False
        and "secrets" not in sa
        and "imagePullSecrets" not in sa
    )
    policy = load("s5-network-policy.yaml")["spec"]
    assert policy["podSelector"]["matchLabels"] == {
        "tekton.dev/task": "bifrost-s5-check"
    }
    assert policy["egress"] == [] and policy["ingress"] == []


def test_build_uses_separate_trusted_source_and_locked_tools():
    build = load("pipeline-build-s5-checker.yaml")["spec"]
    assert {p["name"] for p in build["params"]} == {"infraRevision", "checkerRevision"}
    step = next(t for t in build["tasks"] if t["name"] == "build")["taskSpec"]["steps"][
        0
    ]
    assert "--dockerfile=infra/docker/s5-checker/Dockerfile" in step["args"]
    assert "--digest-file=$(results.digest.path)" in step["args"]
    docker = (ROOT / "docker/s5-checker/Dockerfile").read_text()
    assert "go build -mod=readonly -trimpath" in docker
    assert "COPY --from=build /opt/s5/s5check/" in docker
    assert "npm install" not in docker and "COPY platform/console" not in docker
    tools = json.loads((ROOT / "docker/s5-checker/TOOLS.lock.json").read_text())
    assert tools["typescript"]["version"] == "5.9.3"
    assert (
        len(tools["node"]["sha256"]) == 64 and len(tools["typescript"]["sha512"]) == 128
    )
    # Independently compare the compiler lock to the previously reviewed npm SRI.
    import base64

    assert (
        base64.b64encode(bytes.fromhex(tools["typescript"]["sha512"])).decode()
        == "jl1vZzPDinLr9eUt3J/t7V6FgNEw9QjvBPdysz9KfQDD41fQrC2Y4vKQdiaUpFT4bXlb1RHhLpp8wtm6M5TgSw=="
    )
