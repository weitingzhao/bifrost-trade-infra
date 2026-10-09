#!/usr/bin/env python3
"""The Ops platform's ServiceAccounts can do what they need and nothing more (TD-204).

Asks the API server (kubectl auth can-i --as the ServiceAccount) about a fixed matrix
and, per B/C/D action in LANE-B1's tier table, that PROD can perform it and STG
cannot. Must stay denied: Secrets beyond the two named ones, pod logs outside
Bifrost namespaces, exec outside data, creating Namespaces, deleting pods in
kube-system, and any actuation from STG (Owner 2026-10-07: STG observes, PROD
maintains).

Usage: python3 scripts/check_platform_rbac.py   (needs KUBECONFIG with admin rights; read-only)
Exit 1 when any answer differs from the expectation.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# (verb, resource, namespace or "" for cluster scope, STG, PROD). "kind/name" names one
# object; "kind:sub" is a subresource (kubectl reads "pods:log" as the pod named "log").
MATRIX = [
    # read, both envs
    ("list", "pods", "", True, True),
    ("get", "nodes", "", True, True),
    ("list", "deployments.apps", "bifrost-prod", True, True),
    ("list", "statefulsets.apps", "data", True, True),
    ("list", "cronjobs.batch", "plugin-market-data", True, True),
    ("get", "services:proxy", "plugin-market-data", True, True),
    ("list", "events", "", True, True),
    ("list", "endpointslices.discovery.k8s.io", "data", True, True),
    ("list", "backups.postgresql.cnpg.io", "data", True, True),
    ("get", "clusters.postgresql.cnpg.io", "data", True, True),
    ("list", "pipelineruns.tekton.dev", "cicd", True, True),
    ("list", "taskruns.tekton.dev", "cicd", True, True),
    ("get", "applications.argoproj.io", "cicd", True, True),
    ("get", "ingressroutes.traefik.io", "bifrost-platform-prod", True, True),
    ("list", "nodes.metrics.k8s.io", "", True, True),
    ("get", "pods:log", "data", True, True),
    ("get", "pods:log", "bifrost-prod", True, True),
    ("get", "secret/gitea-bootstrap", "cicd", True, True),
    ("create", "configmaps", "cicd", True, True),
    # release window (LANE-W33C): PROD may delete that one ConfigMap, nothing else in cicd
    ("delete", "configmap/bifrost-release-window", "cicd", False, True),
    ("delete", "configmap/bifrost-platform-other", "cicd", False, False),
    # own-namespace state (each env checked against its own namespace below)
    ("update", "configmaps", "<own>", True, True),
    # actuation: PROD only
    ("update", "deployments.apps", "bifrost-prod", False, True),
    ("patch", "deployments.apps:scale", "bifrost-prod", False, True),
    ("delete", "pods", "data", False, True),
    ("patch", "nodes", "", False, True),
    ("create", "pods:exec", "data", False, True),
    ("create", "backups.postgresql.cnpg.io", "data", False, True),
    ("delete", "backups.postgresql.cnpg.io", "data", False, True),
    ("update", "configmaps", "data", False, True),
    ("get", "secret/minio-backup", "data", False, True),
    ("create", "pipelineruns.tekton.dev", "cicd", False, True),
    ("patch", "applications.argoproj.io", "cicd", False, True),
    # never
    ("get", "pods:log", "kube-system", False, False),
    ("create", "pods:exec", "bifrost-prod", False, False),
    ("list", "secrets", "data", False, False),
    ("get", "secret/bifrost-prod-secrets", "bifrost-prod", False, False),
    ("get", "secrets", "kube-system", False, False),
    ("create", "namespaces", "", False, False),
    ("create", "secrets", "bifrost-platform-prod", False, False),
    ("delete", "deployments.apps", "bifrost-prod", False, False),
    ("create", "clusterrolebindings.rbac.authorization.k8s.io", "", False, False),
    ("update", "deployments.apps", "kube-system", False, False),
    # drain evicts; it must not gain pod delete in kube-system
    ("delete", "pods", "kube-system", False, False),
]

# Decisive Kubernetes verb for each B/C/D action in LANE-B1. PROD must be
# allowed and STG must not. scale of Deployment "daemon" is tier X (D10):
# refuseDaemonScaleUp stays the gate; RBAC cannot name one Deployment, and
# this table does not add a scale verb.
# (id, tier, verb, resource, namespace or "" )
ACTIONS = [
    ("start_pipeline", "B/C", "create", "pipelineruns.tekton.dev", "cicd"),
    ("delete_pipeline_run", "B", "delete", "pipelineruns.tekton.dev", "cicd"),
    ("delete_pipeline_run", "B", "delete", "pods", "cicd"),
    ("gitops_sync", "B/C", "patch", "applications.argoproj.io", "cicd"),
    ("gitops_rollback", "B/C", "patch", "applications.argoproj.io", "cicd"),
    ("rollout_restart", "C", "update", "deployments.apps", "data"),
    ("rollout_restart", "C", "update", "deployments.apps", "bifrost-prod"),
    ("rollout_restart", "C", "update", "deployments.apps", "bifrost-platform-prod"),
    ("rollout_restart", "B", "update", "deployments.apps", "bifrost-stg"),
    ("scale", "C", "patch", "deployments.apps:scale", "bifrost-prod"),
    ("scale", "C", "patch", "deployments.apps:scale", "data"),
    ("delete_pod", "B", "delete", "pods", "data"),
    ("delete_pod", "B", "delete", "pods", "bifrost-prod"),
    ("cordon_node", "C", "patch", "nodes", ""),
    ("uncordon_node", "C", "patch", "nodes", ""),
    ("drain_node", "D", "create", "pods:eviction", "data"),
    ("drain_node", "D", "create", "pods:eviction", "bifrost-prod"),
    ("drain_node", "D", "create", "pods:eviction", "kube-system"),
    ("drain_node", "D", "list", "poddisruptionbudgets.policy", "bifrost-prod"),
    ("poweroff_node", "D", "create", "pods:eviction", "data"),
    ("repair_cnpg_wal_store", "D", "get", "secret/minio-backup", "data"),
    ("repair_cnpg_wal_store", "D", "create", "pods:exec", "data"),
    ("repair_cnpg_wal_store", "D", "create", "backups.postgresql.cnpg.io", "data"),
    ("trigger_cnpg_backup", "C", "create", "backups.postgresql.cnpg.io", "data"),
    ("data_clone", "C", "create", "pods:exec", "data"),
    ("ib_reconnect", "B", "update", "deployments.apps", "data"),
    ("ib_mode", "B", "update", "configmaps", "data"),
]

# B/C/D actions that do not call the API server. Dropping one fails the check.
NON_K8S = (
    ("wake_node", "B", "SSH wake-on-LAN"),
    ("market_data_heal", "B", "HTTP to the market-data plugin"),
    ("unifi_apply", "D", "UniFi API; PROD Secret bifrost-platform-unifi"),
    ("join_node", "D", "host join script; K3S_TOKEN, not a ServiceAccount verb"),
    ("stack_install", "D", "scripts create Namespaces, CRDs and ClusterRoles; TD-204 withholds that"),
    ("stack_upgrade", "D", "same as stack_install"),
)

REQUIRED_ACTIONS = {
    "start_pipeline", "delete_pipeline_run", "gitops_sync", "gitops_rollback",
    "rollout_restart", "scale", "delete_pod", "cordon_node", "uncordon_node",
    "drain_node", "poweroff_node", "join_node", "wake_node",
    "repair_cnpg_wal_store", "unifi_apply", "stack_install", "stack_upgrade",
    "market_data_heal", "ib_reconnect", "ib_mode", "trigger_cnpg_backup", "data_clone",
}


def can_i(env: str, verb: str, resource: str, ns: str) -> bool:
    sa = f"system:serviceaccount:bifrost-platform-{env}:bifrost-platform"
    if ns == "<own>":
        ns = f"bifrost-platform-{env}"
    sub = ""
    if ":" in resource:
        resource, sub = resource.split(":", 1)
    args = ["kubectl", "auth", "can-i", verb, resource, "--as", sa]
    if sub:
        args += ["--subresource", sub]
    if ns:
        args += ["-n", ns]
    r = subprocess.run(args, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode not in (0, 1) or r.stdout.strip() not in ("yes", "no"):
        print(f"kubectl auth can-i failed: {' '.join(args)}: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return r.stdout.strip() == "yes"


def static_job_rules() -> list[str]:
    """New Job and applier rules, from the YAML. Live can-i for them is --live."""
    problems: list[str] = []
    roles = (ROOT / "k8s" / "platform-rbac" / "00-clusterroles.yaml").read_text()
    if "name: bifrost-platform-job-actuator" not in roles:
        problems.append("missing ClusterRole bifrost-platform-job-actuator")
    if "resources: [jobs]" not in roles or "verbs: [get, list, create, delete]" not in roles:
        problems.append("job actuator is not limited to job create and delete")
    prod = (ROOT / "k8s" / "platform-rbac" / "20-prod.yaml").read_text()
    stg = (ROOT / "k8s" / "platform-rbac" / "10-stg.yaml").read_text()
    bound = set(re.findall(r"name: bifrost-platform-job-actuator-prod\n  namespace: (\S+)", prod))
    for ns in ("research", "bifrost-dev"):
        if ns not in bound:
            problems.append(f"PROD job actuator is not bound in {ns}")
    for ns in ("kube-system", "cicd"):
        if ns in bound:
            problems.append(f"PROD job actuator is bound in {ns}")
    if "bifrost-platform-job-actuator" in stg:
        problems.append("STG must not bind the job actuator")
    applier = (ROOT / "k8s" / "platform-rbac" / "30-applier.yaml").read_text()
    wide = applier.split("name: bifrost-applier-cicd", 1)[0]
    if "secrets" in wide or "rolebindings" in wide or "clusterroles" in wide:
        problems.append("applier ClusterRole can write Secrets or RBAC")
    if "namespace: kube-system" in applier:
        problems.append("applier is bound in kube-system")
    if "name: bifrost-applier-cicd" not in applier:
        problems.append("cicd applier role missing")
    return problems


def live_new_rules() -> list[str]:
    """can-i lines that pass only after the Owner applies the new RBAC."""
    problems: list[str] = []
    checks = [
        ("prod", "create", "jobs.batch", "research", True),
        ("prod", "delete", "jobs.batch", "bifrost-dev", True),
        ("prod", "create", "jobs.batch", "kube-system", False),
        ("prod", "create", "jobs.batch", "cicd", False),
        ("prod", "create", "secrets", "research", False),
        ("prod", "create", "rolebindings.rbac.authorization.k8s.io", "research", False),
    ]
    for env, verb, resource, ns, want in checks:
        if can_i(env, verb, resource, ns) != want:
            problems.append(f"{env} {verb} {resource} -n {ns} want {want}")
    applier = "system:serviceaccount:cicd:bifrost-applier"
    for verb, resource, ns, want in (
        ("patch", "deployments.apps", "research", True),
        ("create", "secrets", "research", False),
        ("create", "rolebindings.rbac.authorization.k8s.io", "research", False),
        ("create", "configmaps", "kube-system", False),
    ):
        args = ["kubectl", "auth", "can-i", verb, resource, "--as", applier, "-n", ns]
        r = subprocess.run(args, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        got = r.stdout.strip() == "yes"
        if got != want:
            problems.append(f"applier {verb} {resource} -n {ns} want {want}")
    return problems


def main() -> int:
    bad = 0
    for item in static_job_rules():
        bad += 1
        print(f"FAIL {item}")
    if "--live" in sys.argv[1:]:
        for item in live_new_rules():
            bad += 1
            print(f"FAIL {item}")
    covered = {row[0] for row in ACTIONS} | {row[0] for row in NON_K8S}
    missing = sorted(REQUIRED_ACTIONS - covered)
    extra = sorted(covered - REQUIRED_ACTIONS)
    if missing or extra:
        bad += 1
        print(f"FAIL action table: missing {missing or '[]'} extra {extra or '[]'}")
    for verb, res, ns, want_stg, want_prod in MATRIX:
        for env, want in (("stg", want_stg), ("prod", want_prod)):
            got = can_i(env, verb, res, ns)
            if got != want:
                bad += 1
                print(f"FAIL {env:4} {verb} {res.replace(':', '/')} -n {ns or '<cluster>'}: allowed={got}, want {want}")
    drain_pending = False
    for action, tier, verb, res, ns in ACTIONS:
        for env, want in (("stg", False), ("prod", True)):
            got = can_i(env, verb, res, ns)
            if got != want:
                bad += 1
                if env == "prod" and not got and ("eviction" in res or "poddisruptionbudgets" in res):
                    drain_pending = True
                print(
                    f"FAIL action {action} ({tier}) {env:4} {verb} {res.replace(':', '/')} "
                    f"-n {ns or '<cluster>'}: allowed={got}, want {want}"
                )
    total = 2 * (len(MATRIX) + len(ACTIONS))
    if drain_pending:
        print("hint: PROD cannot drain yet. k8s/platform-rbac grants pods/eviction and PDB list;")
        print("hint: Owner applies it with: kubectl apply -k k8s/platform-rbac")
    if bad:
        print(f"{bad} of {total} answers differ")
        return 1
    print(
        f"ok: {total} permission answers match "
        f"({len(REQUIRED_ACTIONS)} B/C/D actions, PROD can, STG cannot; "
        f"{len(NON_K8S)} are not API-server verbs)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
