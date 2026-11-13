#!/usr/bin/env python3
"""owner-exec's test seed stays out of PROD, and STG's runner stays powerless.

owner-exec runs owner_run_command cards the Owner approves in the Console with
a one-time code. Its STG copy generates a throwaway TOTP seed and prints it to
its log (OWNER_EXEC_TEST_SEED=generate) so the path can be exercised without a
Secret. That is safe only where the runner can do nothing to the cluster. The
program refuses the switch when a ServiceAccount token or a seed is mounted;
this check holds the manifests to the same rule before anything is deployed.

It renders the kustomizations named below (what would be applied, bases and
patches included) and holds:

- in a PROD one, no Pod sets OWNER_EXEC_TEST_SEED;
- anywhere else, a Pod that sets it has automountServiceAccountToken: false,
  names no ServiceAccount, and mounts or reads no Secret.

The list is fixed on purpose: a new PROD kustomization that could carry the
runner has to be added here by hand.

Usage: python3 scripts/check_owner_exec.py [--self-test]   (exit 1 on any problem)
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SWITCH = "OWNER_EXEC_TEST_SEED"

# (kustomization, is it PROD). k8s/owner-exec is the Owner-applied PROD runner.
RENDERED = (
    ("k8s/overlays/platform-stg", False),
    ("k8s/overlays/platform-prod", True),
    ("k8s/overlays/prod", True),
    ("k8s/owner-exec", True),
)


def pod_specs(doc):
    """Every Pod template in a manifest document, with the object's name."""
    if not isinstance(doc, dict):
        return
    name = (doc.get("metadata") or {}).get("name", "?")
    spec = doc.get("spec") or {}
    if doc.get("kind") == "Pod":
        yield name, spec
    template = spec.get("template") or (((spec.get("jobTemplate") or {}).get("spec") or {}).get("template") or {})
    if isinstance(template, dict) and isinstance(template.get("spec"), dict):
        yield name, template["spec"]


def containers(pod: dict) -> list[dict]:
    return (pod.get("containers") or []) + (pod.get("initContainers") or [])


def sets_switch(pod: dict) -> bool:
    return any(env.get("name") == SWITCH for c in containers(pod) for env in c.get("env") or [])


def powerless(name: str, pod: dict) -> list[str]:
    problems = []
    if pod.get("automountServiceAccountToken") is not False:
        problems.append(f"{name}: sets {SWITCH} without automountServiceAccountToken: false")
    account = pod.get("serviceAccountName") or pod.get("serviceAccount")
    if account not in (None, "", "default"):
        problems.append(f"{name}: sets {SWITCH} and runs as ServiceAccount {account}")
    for volume in pod.get("volumes") or []:
        if "secret" in volume or any("secret" in src for src in (volume.get("projected") or {}).get("sources") or []):
            problems.append(f"{name}: sets {SWITCH} and mounts a Secret ({volume.get('name')})")
    for container in containers(pod):
        for env in container.get("env") or []:
            if "secretKeyRef" in (env.get("valueFrom") or {}):
                problems.append(f"{name}: sets {SWITCH} and reads a Secret into {env.get('name')}")
        for source in container.get("envFrom") or []:
            if "secretRef" in source:
                problems.append(f"{name}: sets {SWITCH} and reads a Secret with envFrom")
    return problems


def judge(where: str, prod: bool, docs: list) -> tuple[list[str], int]:
    """Problems in one rendered kustomization, and how many Pods set the switch."""
    problems, seen = [], 0
    for doc in docs:
        for name, pod in pod_specs(doc):
            if not sets_switch(pod):
                continue
            seen += 1
            if prod:
                problems.append(f"{where}: {name} sets {SWITCH}; the test seed must never be reachable in PROD")
            else:
                problems += [f"{where}: {p}" for p in powerless(name, pod)]
    return problems, seen


def render(path: pathlib.Path) -> list:
    out = subprocess.run(["kubectl", "kustomize", str(path)], capture_output=True, text=True, check=True)
    return [d for d in yaml.safe_load_all(out.stdout) if d]


def self_test() -> int:
    """Positive controls: each rule must catch a manifest built to break it."""
    good = {"automountServiceAccountToken": False,
            "containers": [{"name": "c", "env": [{"name": SWITCH, "value": "generate"}]}]}

    def deployment(pod):
        return [{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "owner-exec"},
                 "spec": {"template": {"spec": pod}}}]

    cases = {
        "stg, powerless": (False, good, False),
        "prod sets the switch": (True, good, True),
        "prod sets it in an init container": (True, {"automountServiceAccountToken": False, "containers": [{"name": "c"}],
                                                      "initContainers": [{"name": "i", "env": [{"name": SWITCH, "value": "generate"}]}]}, True),
        "prod without the switch": (True, {"containers": [{"name": "c", "env": [{"name": "OTHER", "value": "1"}]}]}, False),
        "token mounted": (False, {**good, "automountServiceAccountToken": True}, True),
        "token mount left to the default": (False, {k: v for k, v in good.items() if k != "automountServiceAccountToken"}, True),
        "named service account": (False, {**good, "serviceAccountName": "bifrost-platform"}, True),
        "secret volume": (False, {**good, "volumes": [{"name": "seed", "secret": {"secretName": "owner-exec-seed"}}]}, True),
        "projected secret": (False, {**good, "volumes": [{"name": "p", "projected": {"sources": [{"secret": {"name": "s"}}]}}]}, True),
        "secret env": (False, {**good, "containers": [{"name": "c", "env": [
            {"name": SWITCH, "value": "generate"},
            {"name": "T", "valueFrom": {"secretKeyRef": {"name": "s", "key": "k"}}}]}]}, True),
        "secret envFrom": (False, {**good, "containers": [{"name": "c", "env": [{"name": SWITCH, "value": "generate"}],
                                                           "envFrom": [{"secretRef": {"name": "s"}}]}]}, True),
    }
    failed = 0
    for label, (prod, pod, want_problem) in cases.items():
        problems, _ = judge("self-test", prod, deployment(pod))
        if bool(problems) != want_problem:
            failed += 1
            print(f"self-test FAIL: {label}: got {problems}", file=sys.stderr)
    if failed:
        return 1
    print(f"check_owner_exec self-test ok ({len(cases)} cases)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return self_test()
    problems, seen, rendered = [], 0, 0
    for rel, prod in RENDERED:
        path = ROOT / rel
        if not path.is_dir():
            continue  # k8s/owner-exec arrives in its own change
        rendered += 1
        found, count = judge(rel, prod, render(path))
        problems += found
        seen += count
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        return 1
    if seen == 0:
        # Without one Pod that sets the switch this run exercised nothing.
        print(f"check_owner_exec: no rendered Pod sets {SWITCH}; the STG runner is gone or renamed", file=sys.stderr)
        return 1
    print(f"check_owner_exec ok ({rendered} kustomizations rendered; {seen} pod(s) set {SWITCH}, none in PROD, all without a cluster identity)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
