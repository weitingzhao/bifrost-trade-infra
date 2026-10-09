#!/usr/bin/env python3
"""TD-271 admission files match the actuation policy.

Without --live this only reads the repo. --live asks the API server with
kubectl dry-run=server and is for after the Owner applies k8s/platform-rbac.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
POLICY = ROOT / "k8s" / "cicd" / "tekton" / "apply-manifest" / "actuation-policy.yaml"
ADMISSION = ROOT / "k8s" / "platform-rbac" / "40-admission.yaml"
PROJECT = ROOT / "k8s" / "platform-rbac" / "42-appproject-bifrost.yaml"
EMPTY = ROOT / "k8s" / "cicd" / "appprojects" / "default-empty.yaml"
APPS = [
    ROOT / "k8s" / "cicd" / "applications" / name
    for name in (
        "bifrost-stg.yaml",
        "bifrost-prod.yaml",
        "bifrost-platform-stg.yaml",
        "bifrost-platform-prod.yaml",
        "bifrost-research.yaml",
    )
]


def listed(text: str, key: str) -> list[str]:
    lines = text.splitlines()
    out: list[str] = []
    capture = False
    indent = 0
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        current = len(raw) - len(raw.lstrip(" "))
        if capture and current <= indent:
            break
        if raw.strip() == f"{key}:":
            capture = True
            indent = current
            continue
        if capture and raw.strip().startswith("- "):
            item = raw.strip()[2:].strip().strip('"').strip("'")
            out.append(item)
    return out


def static() -> list[str]:
    problems: list[str] = []
    policy = POLICY.read_text()
    admission = ADMISSION.read_text()
    for key, needle in (
        ("pipeline_service_accounts", "bifrost-applier"),
        ("job_service_accounts", "maintainer-reconcile"),
        ("applier_pipeline", "bifrost-apply-manifest"),
    ):
        if needle not in admission:
            problems.append(f"admission file missing {needle}")
    for name in listed(policy, "pipeline_service_accounts") + listed(policy, "job_service_accounts"):
        if f"'{name}'" not in admission and f'"{name}"' not in admission:
            problems.append(f"admission allow-list missing {name}")
    if "argocd" not in admission:
        problems.append("admission file does not mention argocd")
    rendered = subprocess.run(
        ["kubectl", "kustomize", "k8s/platform-rbac"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if rendered.returncode != 0:
        problems.append(f"kustomize platform-rbac: {rendered.stderr.strip()}")
    else:
        for kind in (
            "kind: ValidatingAdmissionPolicy",
            "name: bifrost-platform-pipelinerun",
            "name: bifrost-applier",
            "name: bifrost",
        ):
            if kind not in rendered.stdout:
                problems.append(f"rendered platform-rbac missing {kind}")
    project = PROJECT.read_text()
    if "kind: Namespace" not in project:
        problems.append("appproject bifrost does not whitelist Namespace")
    if "https://github.com/weitingzhao/bifrost-trade-infra.git" not in project:
        problems.append("appproject bifrost missing infra repo")
    if "https://github.com/weitingzhao/bifrost-research.git" not in project:
        problems.append("appproject bifrost missing research repo")
    empty = EMPTY.read_text()
    if "sourceRepos: []" not in empty or "name: default" not in empty:
        problems.append("default-empty.yaml is not an empty default project")
    for app in APPS:
        if "project: bifrost" not in app.read_text():
            problems.append(f"{app.name} is not in project bifrost")
    return problems


def live() -> list[str]:
    """Server-side dry-runs. Refused until the policies are applied."""
    problems: list[str] = []
    identity = "system:serviceaccount:bifrost-platform-prod:bifrost-platform"
    cases = [
        ("inline-pipelinerun", "cicd", inline_run(), True),
        ("normal-pipelinerun", "cicd", normal_run(), False),
    ]
    for name, ns, body, want_deny in cases:
        denied = dry_run(identity, ns, body)
        if denied != want_deny:
            problems.append(f"{name}: denied={denied} want {want_deny}")
    return problems


def dry_run(identity: str, namespace: str, body: str) -> bool:
    r = subprocess.run(
        ["kubectl", "apply", "--dry-run=server", "-n", namespace, "--as", identity, "-f", "-"],
        input=body,
        capture_output=True,
        text=True,
    )
    return r.returncode != 0


def inline_run() -> str:
    return """apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: w33b-guard-inline
  namespace: cicd
spec:
  pipelineSpec:
    tasks:
      - name: x
        taskSpec:
          steps:
            - name: x
              image: alpine
              script: "true"
"""


def normal_run() -> str:
    return """apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: w33b-guard-ref
  namespace: cicd
spec:
  pipelineRef:
    name: bifrost-apply-manifest
  taskRunTemplate:
    serviceAccountName: bifrost-applier
"""


def main() -> int:
    problems = static()
    if "--live" in sys.argv[1:]:
        problems += live()
    if problems:
        for item in problems:
            print(f"FAIL {item}", file=sys.stderr)
        return 1
    print("ok: admission files match the actuation policy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
