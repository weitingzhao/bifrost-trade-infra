"""Static checks for the Gitea backup manifests.

Lives next to the manifests (the same place as
k8s/data/role-matrix/test_check_role_matrix.py). This repository has no single
pytest suite for manifests; run this file directly:

    python3 -m pytest k8s/cicd/gitea-backup/test_gitea_backup.py -q
"""

from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DEPLOYMENT = ROOT / "k8s/cicd/gitea/deployment.yaml"


def docs(name):
    return [doc for doc in yaml.safe_load_all((HERE / name).read_text()) if doc]


def cronjob(name):
    found = [doc for doc in docs(name) if doc.get("kind") == "CronJob"]
    assert len(found) == 1
    return found[0]


def pod_spec(job):
    return job["spec"]["jobTemplate"]["spec"]["template"]["spec"]


def deployment_pod():
    for doc in yaml.safe_load_all(DEPLOYMENT.read_text()):
        if doc and doc.get("kind") == "Deployment":
            return doc["spec"]["template"]["spec"]
    raise AssertionError("gitea Deployment not found")


def test_live_data_mount_is_read_only():
    spec = pod_spec(cronjob("cronjob-backup.yaml"))
    mounts = {m["name"]: m for m in spec["containers"][0]["volumeMounts"]}
    volumes = {v["name"]: v for v in spec["volumes"]}
    assert mounts["gitea-data"]["readOnly"] is True
    claim = volumes["gitea-data"]["persistentVolumeClaim"]
    assert claim["claimName"] == "gitea-data"
    assert claim["readOnly"] is True


def test_no_service_account_token_and_no_rbac():
    for name in ("cronjob-backup.yaml", "cronjob-drill.yaml"):
        spec = pod_spec(cronjob(name))
        assert spec["automountServiceAccountToken"] is False
        assert "serviceAccountName" not in spec
    for path in HERE.glob("*.yaml"):
        for doc in yaml.safe_load_all(path.read_text()):
            if not doc:
                continue
            assert doc.get("kind") not in {
                "ServiceAccount",
                "Role",
                "RoleBinding",
                "ClusterRole",
                "ClusterRoleBinding",
            }


def test_image_tag_matches_the_deployment():
    deploy_image = deployment_pod()["containers"][0]["image"]
    assert deploy_image == "gitea/gitea:1.21.11"
    for name in ("cronjob-backup.yaml", "cronjob-drill.yaml"):
        image = pod_spec(cronjob(name))["containers"][0]["image"]
        assert image == deploy_image


def test_backup_pod_affinity_and_tolerations_match_the_deployment():
    spec = pod_spec(cronjob("cronjob-backup.yaml"))
    required = spec["affinity"]["podAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
    assert len(required) == 1
    assert required[0]["topologyKey"] == "kubernetes.io/hostname"
    assert required[0]["labelSelector"]["matchLabels"] == {"app": "gitea"}
    assert spec["tolerations"] == deployment_pod()["tolerations"]


def test_both_pods_are_covered_by_the_deny_all_network_policy():
    policies = [doc for doc in docs("network-policy.yaml") if doc.get("kind") == "NetworkPolicy"]
    assert len(policies) == 1
    spec = policies[0]["spec"]
    assert spec["policyTypes"] == ["Ingress", "Egress"]
    assert spec["ingress"] == []
    assert spec["egress"] == []
    selected = set(spec["podSelector"]["matchExpressions"][0]["values"])
    assert selected == {"gitea-backup", "gitea-backup-drill"}
    for name, job_file in (
        ("gitea-backup", "cronjob-backup.yaml"),
        ("gitea-backup-drill", "cronjob-drill.yaml"),
    ):
        labels = cronjob(job_file)["spec"]["jobTemplate"]["spec"]["template"]["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == name
        assert name in selected


def test_drill_mounts_no_live_data():
    spec = pod_spec(cronjob("cronjob-drill.yaml"))
    for mount in spec["containers"][0]["volumeMounts"]:
        assert mount.get("name") != "gitea-data"
    claims = []
    for volume in spec["volumes"]:
        claim = volume.get("persistentVolumeClaim")
        if claim:
            claims.append(claim["claimName"])
            assert claim["claimName"] != "gitea-data"
        else:
            assert "emptyDir" in volume or volume["name"] == "scripts"
    assert claims == ["gitea-backup", "gitea-backup"]
    mounts = {m["mountPath"]: m for m in spec["containers"][0]["volumeMounts"]}
    assert mounts["/backup"]["readOnly"] is True
    assert mounts["/data"]["name"] == "work"
    work = next(v for v in spec["volumes"] if v["name"] == "work")
    assert "emptyDir" in work
