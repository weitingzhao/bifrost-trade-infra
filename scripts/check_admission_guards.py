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
    for name in (
        listed(policy, "pipeline_service_accounts")
        + listed(policy, "job_service_accounts")
        + listed(policy, "applier_pod_service_accounts")
    ):
        if f"'{name}'" not in admission and f'"{name}"' not in admission:
            problems.append(f"admission allow-list missing {name}")
    for needle in (
        "!has(object.spec.pipelineRef.resolver)",
        "!has(object.spec.taskRef.resolver)",
        "hostPath",
        "object.spec.sources",
        "source.kustomize",
        "source.helm",
        "source.plugin",
        "source.directory",
        "volumeClaimTemplate",
        "emptyDir",
        "bifrost-applier-pod-spec",
        "bifrost-applier-tekton-spec",
    ):
        if needle not in admission:
            problems.append(f"admission file missing {needle}")
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
    platform = "system:serviceaccount:bifrost-platform-prod:bifrost-platform"
    applier = "system:serviceaccount:cicd:bifrost-applier"
    cases = [
        ("inline-pipelinerun", platform, "cicd", inline_run(), True),
        ("resolver-pipelinerun", platform, "cicd", resolver_run(), True),
        ("secret-workspace-pipelinerun", platform, "cicd", secret_workspace_run(), True),
        ("hostpath-podtemplate-pipelinerun", platform, "cicd", hostpath_run(), True),
        ("normal-pipelinerun", platform, "cicd", normal_run(), False),
        ("applier-hostpath-deployment", applier, "bifrost-dev", applier_hostpath_deployment(), True),
        ("applier-grafana-deployment", applier, "monitoring", applier_grafana_deployment(), True),
        ("application-sources", platform, "cicd", application_sources(), True),
        ("application-kustomize", platform, "cicd", application_kustomize(), True),
    ]
    for name, identity, ns, body, want_deny in cases:
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


def resolver_run() -> str:
    return """apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: w33br-guard-resolver
  namespace: cicd
spec:
  pipelineRef:
    resolver: git
    params:
      - name: url
        value: https://example.invalid/pipeline.yaml
"""


def secret_workspace_run() -> str:
    return """apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: w33br-guard-secret-ws
  namespace: cicd
spec:
  pipelineRef:
    name: bifrost-apply-manifest
  workspaces:
    - name: secrets
      secret:
        secretName: argocd-secret
"""


def hostpath_run() -> str:
    return """apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: w33br-guard-hostpath
  namespace: cicd
spec:
  pipelineRef:
    name: bifrost-apply-manifest
  taskRunTemplate:
    podTemplate:
      volumes:
        - name: host
          hostPath:
            path: /var/run
"""


def applier_hostpath_deployment() -> str:
    return """apiVersion: apps/v1
kind: Deployment
metadata:
  name: w33br-guard-hostpath
  namespace: bifrost-dev
spec:
  selector:
    matchLabels: {app: w33br-guard-hostpath}
  template:
    metadata:
      labels: {app: w33br-guard-hostpath}
    spec:
      containers:
        - name: c
          image: alpine
      volumes:
        - name: host
          hostPath:
            path: /var/run
"""


def applier_grafana_deployment() -> str:
    return """apiVersion: apps/v1
kind: Deployment
metadata:
  name: w33br-guard-grafana-sa
  namespace: monitoring
spec:
  selector:
    matchLabels: {app: w33br-guard-grafana-sa}
  template:
    metadata:
      labels: {app: w33br-guard-grafana-sa}
    spec:
      serviceAccountName: kube-prometheus-stack-grafana
      containers:
        - name: c
          image: alpine
"""


def application_sources() -> str:
    return """apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: bifrost-research
  namespace: cicd
spec:
  project: bifrost
  source:
    repoURL: https://github.com/weitingzhao/bifrost-research.git
    path: k8s
  sources:
    - repoURL: https://example.invalid/other.git
      path: k8s
  destination:
    server: https://kubernetes.default.svc
    namespace: research
"""


def application_kustomize() -> str:
    return """apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: bifrost-research
  namespace: cicd
spec:
  project: bifrost
  source:
    repoURL: https://github.com/weitingzhao/bifrost-research.git
    path: k8s
    kustomize:
      images: ["evil.example/x:1"]
  destination:
    server: https://kubernetes.default.svc
    namespace: research
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
