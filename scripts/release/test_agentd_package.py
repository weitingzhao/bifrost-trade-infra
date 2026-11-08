"""Identity, immutable publication, and credential isolation for the CD package."""

import copy
import hashlib
from pathlib import Path

import pytest
import yaml

from agentd_package import PACKAGE, delivery_proof, publish

P, U, INFRA = "a" * 40, "b" * 40, "c" * 40
TEKTON = Path(__file__).resolve().parents[2] / "k8s/cicd/tekton"


def evidence(runs, commit, ui, infra):
    task = yaml.safe_load((TEKTON / "task-agentrt-migrate-stg.yaml").read_text())
    selector = next(step for step in task["spec"]["steps"] if step["name"] == "agentd-ci-evidence")
    scope = {"__name__": "fixture"}
    exec(compile(selector["script"], "agentd-ci-evidence", "exec"), scope)
    return scope["evidence"](runs, commit, ui, infra)


def test_package_accepts_only_the_matching_receipt():
    receipt = {"commit": P, "ui": U, "infra": INFRA, "ci": "landing-ci-one"}
    assert delivery_proof(receipt, P, U, INFRA) == receipt
    with pytest.raises(ValueError, match="exact delivery inputs"):
        delivery_proof(dict(receipt, infra="d" * 40), P, U, INFRA)
    with pytest.raises(ValueError, match="invalid CI run"):
        delivery_proof(dict(receipt, ci=""), P, U, INFRA)


def green():
    return {"metadata": {"name": "landing-ci-one"}, "spec": {
        "pipelineRef": {"name": "bifrost-ci-platform"},
        "params": [{"name": "revision", "value": P}, {"name": "repo-url",
                    "value": "http://gitea.cicd.svc.cluster.local:3000/bifrost/bifrost-platform.git"}]}, "status": {
        "conditions": [{"type": "Succeeded", "status": "True"}],
        "results": [{"name": name, "value": value} for name, value in (
            ("platform-commit", P), ("ui-commit", U), ("infra-commit", INFRA), ("api-scope", "incremental"))]}}


def test_only_the_actual_successful_inputs_supply_evidence():
    run = green()
    assert evidence([run], P, U, INFRA) == "landing-ci-one"
    for name in ("platform-commit", "ui-commit", "infra-commit", "api-scope"):
        wrong = copy.deepcopy(run)
        for result in wrong["status"]["results"]:
            if result["name"] == name:
                result["value"] = "wrong"
        with pytest.raises(ValueError):
            evidence([wrong], P, U, INFRA)
    run["status"]["conditions"][0]["status"] = "False"
    with pytest.raises(ValueError):
        evidence([run], P, U, INFRA)


def test_upload_is_read_back_and_idempotent_and_conflicts_are_never_overwritten():
    files, calls = {}, []

    def request(method, name, body=None):
        calls.append((method, name))
        if method == "GET":
            return (200, files[name]) if name in files else (404, b"")
        files[name] = body
        return 201, b""

    binary = b"fixture binary"
    digest = publish(P, binary, "fixture", "not-a-secret", request)
    assert digest == hashlib.sha256(binary).hexdigest()
    assert [name for method, name in calls if method == "PUT"] == ["agentd-linux-amd64", "agentd.sha256"]
    calls.clear()
    assert publish(P, binary, "fixture", "not-a-secret", request) == digest
    assert all(method == "GET" for method, _ in calls)
    with pytest.raises(ValueError, match="never overwritten"):
        publish(P, b"different", "fixture", "not-a-secret", request)
    assert files["agentd-linux-amd64"] == binary


def test_failed_binary_upload_never_publishes_discovery_marker():
    calls = []

    def request(method, name, body=None):
        calls.append(name)
        return (404 if method == "GET" else 403), b""

    with pytest.raises(ValueError, match="403"):
        publish(P, b"fixture", "fixture", "not-a-secret", request)
    assert set(calls) == {"agentd-linux-amd64"}


def test_only_cd_upload_step_receives_the_publisher_secret():
    root = Path(__file__).resolve().parents[2]
    tekton = root / "k8s/cicd/tekton"
    task = yaml.safe_load((tekton / "task-agentd-package.yaml").read_text())
    holders = [step["name"] for step in task["spec"]["steps"] if any(
        env.get("valueFrom", {}).get("secretKeyRef", {}).get("name") == "gitea-agentd-publisher"
        for env in step.get("env", []))]
    assert holders == ["publish"]
    cd = yaml.safe_load((tekton / "pipeline-deliver-platform.yaml").read_text())
    package = next(t for t in cd["spec"]["tasks"] if t["name"] == "agentd-package")
    assert package["runAfter"] == ["rollout"]
    assert {"name": "ciEvidence", "value": "$(tasks.agentrt-migrate.results.agentd-ci-evidence)"} in package["params"]
    assert all("kubectl" not in step["script"] for step in task["spec"]["steps"])
    assert "agentd-package" not in (tekton / "pipeline-ci-platform.yaml").read_text()
    assert "go test" not in (tekton / "task-agentd-package.yaml").read_text()


def test_publisher_reader_and_host_use_the_isolated_package_owner():
    root = Path(__file__).resolve().parents[2]
    path = "/api/packages/bifrost-agentd-publisher/generic/agentd"
    assert PACKAGE.endswith(path)
    helper = (root / "scripts/agent-host/agentd-update").read_text()
    assert path + "/$1/agentd-linux-amd64" in helper
    assert "/api/packages/bifrost/generic/" not in helper
    patches = list(yaml.safe_load_all((root / "k8s/overlays/platform-prod/platform-agentd-deploy.patch.yaml").read_text()))
    assert {p["metadata"]["name"] for p in patches} == {"platform-api", "platform-workers"}
    for patch in patches:
        env = patch["spec"]["template"]["spec"]["containers"][0]["env"]
        url = next(e["value"] for e in env if e["name"] == "AGENTD_PACKAGE_SHA256_URL")
        assert url.endswith(path + "/{commit}/agentd.sha256")
        spec = patch["spec"]["template"]["spec"]
        mount = next(m for m in spec["containers"][0]["volumeMounts"] if m["name"] == "agentd-package-reader")
        assert mount["readOnly"] is True
        assert mount["mountPath"] == next(e["value"] for e in env if e["name"] == "AGENTD_PACKAGE_READER_DIR")
        volume = next(v for v in spec["volumes"] if v["name"] == "agentd-package-reader")
        assert volume["secret"]["secretName"] == "agentd-package-reader"
        assert volume["secret"]["defaultMode"] == 0o400
