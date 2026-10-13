"""Static deployment boundaries; run alongside test_backup_logic.py with pytest."""

from pathlib import Path
import re

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CLUSTER = ROOT / "k8s/data/cluster-state-backup"


def docs(path):
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def job():
    return next(d for d in docs(HERE / "cronjob-backup.yaml") if d["kind"] == "CronJob")


def template():
    return job()["spec"]["jobTemplate"]["spec"]["template"]


def deployment():
    return next(
        d
        for d in docs(ROOT / "k8s/cicd/gitea/deployment.yaml")
        if d["kind"] == "Deployment"
    )["spec"]["template"]["spec"]


def containers(spec):
    return spec.get("containers", []) + spec.get("initContainers", [])


def assert_no_credentials(spec):
    assert spec["automountServiceAccountToken"] is False
    assert "serviceAccountName" not in spec
    for v in spec.get("volumes", []):
        assert "secret" not in v
        assert "csi" not in v  # CSI Secret stores cannot introduce credentials.
        for source in v.get("projected", {}).get("sources", []):
            assert "serviceAccountToken" not in source and "secret" not in source
    for c in containers(spec):
        for e in c.get("envFrom", []):
            assert "secretRef" not in e
        for e in c.get("env", []):
            assert "secretKeyRef" not in e.get("valueFrom", {})


def test_no_service_account_token_by_any_route():
    assert_no_credentials(template()["spec"])
    forbidden = {
        "ServiceAccount",
        "Role",
        "RoleBinding",
        "ClusterRole",
        "ClusterRoleBinding",
        "Secret",
    }
    for path in HERE.glob("*.yaml"):
        assert all(d.get("kind") not in forbidden for d in docs(path))


def test_credential_mutations_are_rejected():
    from copy import deepcopy
    import pytest

    base = template()["spec"]
    mutations = [
        lambda s: s.update(automountServiceAccountToken=True),
        lambda s: s["volumes"].append(
            {
                "name": "token",
                "projected": {"sources": [{"serviceAccountToken": {"path": "token"}}]},
            }
        ),
        lambda s: s["volumes"].append(
            {"name": "secret", "secret": {"secretName": "foo"}}
        ),
    ]
    for kind in ("containers", "initContainers"):
        mutations.extend(
            [
                lambda s, k=kind: s[k][0].update(
                    envFrom=[{"secretRef": {"name": "foo"}}]
                ),
                lambda s, k=kind: s[k][0].update(
                    env=[
                        {
                            "name": "TOKEN",
                            "valueFrom": {
                                "secretKeyRef": {"name": "foo", "key": "token"}
                            },
                        }
                    ]
                ),
            ]
        )
    for mutate in mutations:
        spec = deepcopy(base)
        mutate(spec)
        with pytest.raises(AssertionError):
            assert_no_credentials(spec)


def test_live_mounts_read_only_in_every_container():
    spec = template()["spec"]
    volumes = {v["name"]: v for v in spec["volumes"]}
    live = {
        n
        for n, v in volumes.items()
        if v.get("persistentVolumeClaim", {}).get("claimName") == "gitea-data"
    }
    assert live
    for n in live:
        assert volumes[n]["persistentVolumeClaim"]["readOnly"] is True
    for c in containers(spec):
        for mount in c.get("volumeMounts", []):
            if mount["name"] in live:
                assert mount["readOnly"] is True
    mounts = {m["mountPath"]: m for m in spec["containers"][0]["volumeMounts"]}
    assert "emptyDir" in volumes[mounts["/work"]["name"]]
    assert "emptyDir" in volumes[mounts["/tools"]["name"]]
    assert not any(
        "subPath" in m for c in containers(spec) for m in c.get("volumeMounts", [])
    )


def test_image_uid_affinity_and_tolerations():
    spec = template()["spec"]
    assert spec["containers"][0]["image"] == deployment()["containers"][0]["image"]
    assert (
        spec["securityContext"]["runAsUser"]
        == spec["securityContext"]["runAsGroup"]
        == 1000
    )
    required = spec["affinity"]["podAffinity"][
        "requiredDuringSchedulingIgnoredDuringExecution"
    ]
    assert required == [
        {
            "labelSelector": {"matchLabels": {"app": "gitea"}},
            "topologyKey": "kubernetes.io/hostname",
        }
    ]
    assert spec["tolerations"] == deployment()["tolerations"]
    cluster_job = next(
        d for d in docs(CLUSTER / "cronjob.yaml") if d["kind"] == "CronJob"
    )
    cluster_init = cluster_job["spec"]["jobTemplate"]["spec"]["template"]["spec"][
        "initContainers"
    ][0]
    assert spec["initContainers"][0]["image"] == cluster_init["image"]


def test_exact_network_policy():
    spec = docs(HERE / "network-policy.yaml")[0]["spec"]
    assert spec["podSelector"] == {"matchLabels": template()["metadata"]["labels"]}
    assert spec["policyTypes"] == ["Ingress", "Egress"]
    assert spec["ingress"] == []
    assert spec["egress"] == [
        {
            "to": [
                {
                    "namespaceSelector": {
                        "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
                    },
                    "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
                }
            ],
            "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}],
        },
        {
            "to": [
                {
                    "ipBlock": {
                        "cidr": "0.0.0.0/0",
                        "except": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
                    }
                }
            ],
            "ports": [{"protocol": "TCP", "port": 443}],
        },
    ]


def test_same_recipient_and_age_pin():
    assert (
        docs(HERE / "recipient-configmap.yaml")[0]["data"]["recipient"]
        == docs(CLUSTER / "recipient-configmap.yaml")[0]["data"]["recipient"]
    )
    for key in ("AGE_URL", "AGE_SHA"):
        pattern = rf"^{key}=(.+)$"
        assert (
            re.search(pattern, (HERE / "fetch-tools.sh").read_text(), re.M)[1]
            == re.search(pattern, (CLUSTER / "fetch-tools.sh").read_text(), re.M)[1]
        )
    assert "kubectl" not in (HERE / "fetch-tools.sh").read_text().split("set -eu")[1]


def test_one_cronjob_and_no_test_hooks():
    jobs = [
        d for p in HERE.glob("*.yaml") for d in docs(p) if d.get("kind") == "CronJob"
    ]
    assert [d["metadata"]["name"] for d in jobs] == ["gitea-backup"]
    assert (
        "GITEA_BACKUP_TEST_HOOK_DIR" not in (HERE / "cronjob-backup.yaml").read_text()
    )
    assert not (HERE / "drill.sh").exists()
    assert not (HERE / "cronjob-drill.yaml").exists()
    k = docs(HERE / "kustomization.yaml")[0]
    assert all((HERE / r).is_file() for r in k["resources"])
    assert k["configMapGenerator"][0]["files"] == [
        "backup.sh",
        "verify-stage.sh",
        "fetch-tools.sh",
    ]


def test_alert_and_maintainers():
    rules = docs(ROOT / "k8s/monitoring/bifrost-alerting-rules.yaml")[0]["spec"][
        "groups"
    ]
    alerts = [
        r
        for g in rules
        for r in g["rules"]
        if r.get("alert", "").startswith("BifrostGiteaBackup")
    ]
    assert len(alerts) == 1
    assert alerts[0]["alert"] == "BifrostGiteaBackupMissing"
    assert "absent(kube_cronjob_status_last_successful_time" in alerts[0]["expr"]
    assert (
        "kube_cronjob_created" in alerts[0]["expr"] and "> 93600" in alerts[0]["expr"]
    )
    # max(created) has no labels; absent infers cronjob/namespace labels.
    assert "and on()" in alerts[0]["expr"]
    for p in (
        ROOT / "agent-config/MAINTAINERS.yaml",
        ROOT / "k8s/monitoring/maintainer-reconcile/MAINTAINERS.yaml",
    ):
        s = p.read_text()
        assert s.count("id: cronjob/cicd/gitea-backup\n") == 1
        assert "gitea-backup-drill" not in s


def test_stage_cannot_act_on_world_and_emptydir_needs_no_fsgroup():
    script = (HERE / "verify-stage.sh").read_text()
    for key, value in {
        "webhook__ALLOWED_HOST_LIST": "loopback",
        "mirror__ENABLED": "false",
        "cron__ENABLED": "false",
        "actions__ENABLED": "false",
        "mailer__ENABLED": "false",
    }.items():
        assert f"export GITEA__{key}={value}" in script
    assert "fsGroup" not in template()["spec"]["securityContext"]


def test_fetch_retries_six_times_offline(tmp_path):
    import os
    import subprocess
    bins = tmp_path / "bin"
    bins.mkdir()
    tools = tmp_path / "tools"
    tools.mkdir()
    log = tmp_path / "attempts"
    # Model only tool download/extraction; never invoke network or real wget.
    (bins / "wget").write_text(
        '#!/bin/sh\nn=0; [ ! -f "$FETCH_LOG" ] || n=$(cat "$FETCH_LOG")\n'
        'n=$((n+1)); echo "$n" > "$FETCH_LOG"\n'
        '[ "$n" -gt "$FETCH_FAILURES" ] || exit 1\n'
        'touch age.tar.gz\n'
    )
    (bins / "sha256sum").write_text('#!/bin/sh\ncat >/dev/null\n')
    (bins / "tar").write_text('#!/bin/sh\nmkdir age; echo binary > age/age\n')
    (bins / "sleep").write_text('#!/bin/sh\necho "$1" >> "$SLEEP_LOG"\n')
    for p in bins.iterdir():
        p.chmod(0o755)
    script = tmp_path / "fetch.sh"
    # /tools is a mount in production. Rebase only the fixture copy.
    script.write_text((HERE / "fetch-tools.sh").read_text().replace("/tools", str(tools)))
    for failures in (5, 6):
        log.unlink(missing_ok=True)
        sleeps = tmp_path / "sleeps"
        sleeps.unlink(missing_ok=True)
        env = dict(os.environ, PATH=str(bins)+os.pathsep+os.environ["PATH"],
                   FETCH_LOG=str(log), FETCH_FAILURES=str(failures), SLEEP_LOG=str(sleeps))
        r = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)
        assert (r.returncode == 0) == (failures == 5), r.stderr
        assert log.read_text().strip() == "6"
        assert sleeps.read_text().splitlines() == ["5"] * 5
        if failures == 6:
            assert "age download failed after 6 attempts" in r.stderr
