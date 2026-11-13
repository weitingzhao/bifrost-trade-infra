#!/usr/bin/env python3
"""owner-exec's test seed stays out of PROD, and STG's runner stays powerless.

owner-exec runs owner_run_command cards the Owner approves in the Console with
a one-time code. Its STG copy generates a throwaway TOTP seed and prints it to
its log (OWNER_EXEC_TEST_SEED=generate) so the path can be exercised without a
Secret. That is safe only where the runner can do nothing to the cluster. The
program refuses the switch when a ServiceAccount token or a seed is mounted;
this check holds the manifests to the same rule before anything is deployed:

- the name OWNER_EXEC_TEST_SEED appears in no PROD manifest: not under
  k8s/overlays/*prod*/, not under k8s/owner-exec/ (the Owner-applied PROD kit),
  not in k8s/base-platform (which PROD inherits);
- wherever it is set (STG), that Pod has automountServiceAccountToken: false,
  names no ServiceAccount, and mounts no Secret.

Usage: python3 scripts/check_owner_exec.py [--self-test]   (exit 1 on any problem)
"""

from __future__ import annotations

import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SWITCH = "OWNER_EXEC_TEST_SEED"


def prod_files(root: pathlib.Path) -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for base in sorted((root / "k8s" / "overlays").glob("*prod*")) + [root / "k8s" / "owner-exec", root / "k8s" / "base-platform"]:
        if base.is_dir():
            out += [p for p in sorted(base.rglob("*")) if p.is_file()]
    return out


def switch_in_prod(root: pathlib.Path) -> list[str]:
    problems = []
    for path in prod_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if SWITCH in text:
            problems.append(f"{path.relative_to(root)}: names {SWITCH}; the test seed must never be reachable from a PROD manifest")
    return problems


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


def sets_switch(pod: dict) -> bool:
    for container in (pod.get("containers") or []) + (pod.get("initContainers") or []):
        for env in container.get("env") or []:
            if env.get("name") == SWITCH:
                return True
    return False


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
    for container in (pod.get("containers") or []) + (pod.get("initContainers") or []):
        for env in container.get("env") or []:
            if "secretKeyRef" in (env.get("valueFrom") or {}):
                problems.append(f"{name}: sets {SWITCH} and reads a Secret into {env.get('name')}")
        for source in container.get("envFrom") or []:
            if "secretRef" in source:
                problems.append(f"{name}: sets {SWITCH} and reads a Secret with envFrom")
    return problems


def switch_users(root: pathlib.Path) -> tuple[list[str], int]:
    problems, seen = [], 0
    for path in sorted((root / "k8s").rglob("*.yaml")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if SWITCH not in text:
            continue
        try:
            docs = list(yaml.safe_load_all(text))
        except yaml.YAMLError as err:
            problems.append(f"{path.relative_to(root)}: names {SWITCH} and does not parse: {err}")
            continue
        for doc in docs:
            for name, pod in pod_specs(doc):
                if sets_switch(pod):
                    seen += 1
                    problems += [f"{path.relative_to(root)}: {p}" for p in powerless(name, pod)]
    return problems, seen


def check(root: pathlib.Path) -> tuple[list[str], int]:
    problems = switch_in_prod(root)
    more, seen = switch_users(root)
    return problems + more, seen


def self_test() -> int:
    """Positive controls: each rule must catch a manifest built to break it."""
    import tempfile

    good_pod = {"automountServiceAccountToken": False,
                "containers": [{"name": "c", "env": [{"name": SWITCH, "value": "generate"}]}]}

    def deployment(pod):
        return yaml.safe_dump({"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "owner-exec"},
                               "spec": {"template": {"spec": pod}}})

    cases = {
        "stg, powerless": ("k8s/overlays/platform-stg/x.yaml", good_pod, 0),
        "prod overlay names the switch": ("k8s/overlays/platform-prod/x.yaml", good_pod, 1),
        "owner-applied prod kit names the switch": ("k8s/owner-exec/x.yaml", good_pod, 1),
        "base inherited by prod names the switch": ("k8s/base-platform/x.yaml", good_pod, 1),
        "token mounted": ("k8s/overlays/platform-stg/x.yaml", {**good_pod, "automountServiceAccountToken": True}, 1),
        "token mount left to the default": ("k8s/overlays/platform-stg/x.yaml",
                                            {k: v for k, v in good_pod.items() if k != "automountServiceAccountToken"}, 1),
        "named service account": ("k8s/overlays/platform-stg/x.yaml", {**good_pod, "serviceAccountName": "bifrost-platform"}, 1),
        "secret volume": ("k8s/overlays/platform-stg/x.yaml",
                          {**good_pod, "volumes": [{"name": "seed", "secret": {"secretName": "owner-exec-seed"}}]}, 1),
        "secret env": ("k8s/overlays/platform-stg/x.yaml",
                       {**good_pod, "containers": [{"name": "c", "env": [
                           {"name": SWITCH, "value": "generate"},
                           {"name": "T", "valueFrom": {"secretKeyRef": {"name": "s", "key": "k"}}}]}]}, 1),
    }
    failed = 0
    for label, (rel, pod, want) in cases.items():
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = root / rel
            path.parent.mkdir(parents=True)
            path.write_text(deployment(pod), encoding="utf-8")
            problems, _ = check(root)
            if (len(problems) > 0) != (want > 0):
                failed += 1
                print(f"self-test FAIL: {label}: got {problems}", file=sys.stderr)
    if failed:
        return 1
    print(f"check_owner_exec self-test ok ({len(cases)} cases)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return self_test()
    problems, seen = check(ROOT)
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        return 1
    print(f"check_owner_exec ok ({seen} pod(s) set {SWITCH}, none in PROD, all without a cluster identity)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
