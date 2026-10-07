#!/usr/bin/env python3
"""The Ops platform's ServiceAccounts can do what they need and nothing more (TD-204).

Asks the API server (kubectl auth can-i --as the ServiceAccount) about a fixed matrix:
what platform code calls (measured from client-go and dynamic-client usage), and what
must stay denied: Secrets beyond the two named ones, pod logs outside Bifrost
namespaces, exec outside data, creating Namespaces, and any actuation from STG
(Owner 2026-10-07: STG observes, PROD maintains).

Usage: python3 scripts/check_platform_rbac.py   (needs KUBECONFIG with admin rights; read-only)
Exit 1 when any answer differs from the expectation.
"""

from __future__ import annotations

import subprocess
import sys

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
]


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


def main() -> int:
    bad = 0
    for verb, res, ns, want_stg, want_prod in MATRIX:
        for env, want in (("stg", want_stg), ("prod", want_prod)):
            got = can_i(env, verb, res, ns)
            if got != want:
                bad += 1
                print(f"FAIL {env:4} {verb} {res.replace(':', '/')} -n {ns or '<cluster>'}: allowed={got}, want {want}")
    total = 2 * len(MATRIX)
    if bad:
        print(f"{bad} of {total} answers differ")
        return 1
    print(f"ok: {total} permission answers match (STG observes, PROD maintains)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
