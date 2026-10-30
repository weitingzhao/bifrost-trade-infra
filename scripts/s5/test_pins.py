import json
import shutil

import pytest
import yaml

from pins import MATERIALS, ROOT, backfill, contract

ZERO, PIN = "sha256:" + "0" * 64, "sha256:" + "1" * 64
BUILT = {
    "callersDigest": "c" * 64,
    "profileDigest": "a" * 64,
    "testsDigest": "e" * 64,
    "toolchainDigest": "b" * 64,
    "typesDigest": "d" * 64,
    "uiSHA": "7" * 40,
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def tree(tmp_path):
    shutil.copytree(ROOT / "docker/s5-checker", tmp_path / "docker/s5-checker")
    target = tmp_path / "k8s/cicd/tekton"
    target.mkdir(parents=True)
    for p in (ROOT / "k8s/cicd/tekton").glob("*s5*"):
        shutil.copy(p, target / p.name)
    return target


def load(name):
    return yaml.safe_load((ROOT / "k8s/cicd/tekton" / name).read_text())


def test_unbuilt_is_rejected_and_real_pin_must_match_all_tasks(tmp_path):
    target = tree(tmp_path)
    zero, pin = ZERO, PIN
    (tmp_path / "docker/s5-checker/IMAGE_DIGEST").write_text(zero)
    with pytest.raises(ValueError, match="UNBUILT"):
        contract(tmp_path)
    (tmp_path / "docker/s5-checker/IMAGE_DIGEST").write_text(pin)
    (tmp_path / MATERIALS).write_text(canonical(BUILT) + "\n")
    for p in target.glob("task-s5-*.yaml"):
        p.write_text(p.read_text().replace(zero, pin))
    assert contract(tmp_path)["image"].endswith(pin)
    p = target / "task-s5-check.yaml"
    p.write_text(p.read_text().replace(pin, zero))
    with pytest.raises(ValueError, match="pin mismatch"):
        contract(tmp_path)


def test_shipped_materials_are_the_unbuilt_placeholder_in_platform_shape():
    c = contract(ready=False)
    # Exactly landingci s5Materials; the platform refuses the zeros (UNBUILT).
    assert set(c["materials"]) == set(BUILT)
    assert all(set(v) == {"0"} for v in c["materials"].values())
    with pytest.raises(ValueError, match="UNBUILT"):
        contract(ready=True)


@pytest.mark.parametrize(
    "image,materials,match",
    [
        # A built image with placeholder materials is refused even when not --ready.
        (PIN, None, "missing trusted material"),
        # Materials without a built image cannot be real: they come from the build.
        (ZERO, canonical(BUILT), "placeholder"),
        (PIN, canonical({**BUILT, "uiSHA": "0" * 40}), "missing trusted material"),
        (PIN, canonical({**BUILT, "extra": "x"}), "exactly"),
        (PIN, canonical({k: v for k, v in BUILT.items() if k != "uiSHA"}), "exactly"),
        (PIN, canonical({**BUILT, "testsDigest": "E" * 64}), "invalid"),
        (PIN, json.dumps(BUILT, sort_keys=True), "canonical"),
    ],
)
def test_materials_must_match_the_image_state(tmp_path, image, materials, match):
    target = tree(tmp_path)
    (tmp_path / "docker/s5-checker/IMAGE_DIGEST").write_text(image)
    for p in target.glob("task-s5-*.yaml"):
        p.write_text(p.read_text().replace(ZERO, image))
    if materials is not None:
        (tmp_path / MATERIALS).write_text(materials)
    with pytest.raises(ValueError, match=match):
        contract(tmp_path, ready=False)


def test_backfill_records_digest_and_materials_in_one_step(tmp_path):
    target = tree(tmp_path)
    c = backfill(tmp_path, PIN, canonical(BUILT) + "\n")
    assert c["image"].endswith(PIN) and c["materials"] == BUILT
    assert contract(tmp_path, ready=True) == c
    assert (tmp_path / MATERIALS).read_text() == canonical(BUILT) + "\n"
    for p in target.glob("task-s5-*.yaml"):
        assert ZERO not in p.read_text()


@pytest.mark.parametrize(
    "digest,materials",
    [
        (ZERO, canonical(BUILT)),
        ("sha256:" + "1" * 63, canonical(BUILT)),
        (PIN, canonical({k: "0" * len(v) for k, v in BUILT.items()})),
        (PIN, json.dumps(BUILT)),
        (PIN, "{}"),
    ],
)
def test_backfill_writes_nothing_when_invalid(tmp_path, digest, materials):
    tree(tmp_path)
    before = {
        p: p.read_text()
        for p in tmp_path.rglob("*")
        if p.is_file() and p.suffix in {".yaml", ".json", ""}
    }
    with pytest.raises(ValueError):
        backfill(tmp_path, digest, materials)
    assert {p: p.read_text() for p in before} == before


def test_mandatory_task_has_no_skip_or_inline_escape():
    c = contract(ready=False)
    pipeline = c["pipeline"]
    assert [t["name"] for t in pipeline["tasks"]] == [
        "freeze-check", "s5-fetch", "s5-check"
    ]
    assert pipeline["tasks"][0]["taskRef"] == {"name": "bifrost-release-freeze-check"}
    assert "runAfter" not in pipeline["tasks"][0]
    assert "finally" not in pipeline
    for task in pipeline["tasks"]:
        assert not set(task) & {"when", "taskSpec", "matrix", "retries", "onError"}
        assert set(task["taskRef"]) == {"name"}
    for task in pipeline["tasks"][1:]:
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
    assert pipeline["tasks"][1]["runAfter"] == ["freeze-check"]
    assert pipeline["tasks"][2]["runAfter"] == ["s5-fetch"]
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
        secret = [e for e in step["env"] if "valueFrom" in e]
        if stage == "check":
            assert secret == []
        else:
            # TD-432: only fetch reads Gitea, with the read-only reader secret.
            assert secret == [
                {
                    "name": "GIT_" + n.upper(),
                    "valueFrom": {"secretKeyRef": {"name": "gitea-ci-reader", "key": n}},
                }
                for n in ("username", "password")
            ]
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


def test_build_reports_materials_from_the_image_it_built():
    build = load("pipeline-build-s5-checker.yaml")["spec"]
    results = {r["name"]: r["value"] for r in build["results"]}
    assert results == {
        "image-digest": "$(tasks.build.results.digest)",
        "materials": "$(tasks.report-materials.results.materials)",
    }
    task = next(t for t in build["tasks"] if t["name"] == "report-materials")
    assert task["runAfter"] == ["build"]
    assert task["params"] == [
        {"name": "digest", "value": "$(tasks.build.results.digest)"}
    ]
    (step,) = task["taskSpec"]["steps"]
    assert step["image"] == (
        "registry.cicd.svc.cluster.local:5000/bifrost-s5-checker@$(params.digest)"
    )
    assert step["command"] == ["python3", "-I", "-c"]
    assert "/opt/s5/materials.json" in step["args"][0]
    assert step["env"] == [{"name": "RESULT", "value": "$(results.materials.path)"}]
    assert step["securityContext"]["readOnlyRootFilesystem"] is True


def test_run_template_is_tekton_stored_form_with_one_freeze_override():
    c = contract(ready=False)
    run = c["runTemplate"]
    # Tekton stores metav1.Duration ("1200s" would read back as "20m0s");
    # the template, the pipeline and admission use the stored form.
    assert run["timeouts"] == {"pipeline": "20m0s"}
    assert [t["timeout"] for t in c["pipeline"]["tasks"][1:]] == ["10m0s", "10m0s"]
    # The freeze check reads cicd/bifrost-release-freeze with the default SA
    # token (tekton-release-window); every S5 task keeps the no-token template.
    assert run["taskRunSpecs"] == [
        {
            "pipelineTaskName": "freeze-check",
            "serviceAccountName": "default",
            "podTemplate": {"nodeSelector": {"kubernetes.io/arch": "amd64"}},
        }
    ]
    policy = (ROOT / "k8s/platform-rbac/40-admission.yaml").read_text()
    s5 = policy.split("- name: s5", 1)[1].split("validations:", 1)[0]
    assert "'pipelineTaskName': 'freeze-check', 'serviceAccountName': 'default'" in s5
    assert "object.spec.timeouts == {'pipeline': '20m0s'}" in s5
    assert "1200s" not in s5 and "!has(object.spec.taskRunSpecs)" not in s5
    assert "metadata.all(k, k == 'creationTimestamp')" in s5
