#!/usr/bin/env python3
"""TD-271 admission files match the actuation policy.

Without --live this only reads the repo. --live asks the API server with
kubectl dry-run=server and is for after the Owner applies k8s/platform-rbac.

The dry-runs impersonate the PROD platform and applier ServiceAccounts, so they
need the Owner kubeconfig (run through owner_run_command). With the Agent's
read-only identity the dry-runs are skipped and the exit code is 3; the
Application-namespace check still runs (TD-277). A dry-run counts as denied
only when the API server names a ValidatingAdmissionPolicy or refuses the
impersonated account; any other failure is reported, not taken as a denial.
"""
from __future__ import annotations

import pathlib
import subprocess
import re
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
    # namespaceSelector is a LabelSelector: matchNames is not a field and the
    # API server rejects the whole policy (found by server dry-run, 2026-10-09).
    if re.search(r"^\s*matchNames:", admission, re.M):
        problems.append("namespaceSelector uses matchNames; use matchLabels kubernetes.io/metadata.name")
    if "object.metadata.namespace == 'monitoring' || (\n          object.kind == 'Pod'" in admission:
        problems.append("platform Jobs and Pods must not skip host checks in monitoring")
    problems += pipeline_task_params()
    return problems


def pipeline_task_params() -> list[str]:
    """Every param an embedded taskSpec declares without a default must be passed.

    Tekton refuses the run at validation otherwise; the 2026-10-09 PROD smoke
    hit exactly that because no gate ever ran the pipeline.
    """
    import yaml

    path = ROOT / "k8s/cicd/tekton/apply-manifest/pipeline.yaml"
    doc = yaml.safe_load(path.read_text())
    problems: list[str] = []
    # workactions.Summarize reads these from the PipelineRun, not the TaskRun.
    promoted = {r.get("name") for r in doc["spec"].get("results") or []}
    for name in ("objects", "policy"):
        if name not in promoted:
            problems.append(f"pipeline does not promote task result {name} to the PipelineRun")
    for task in doc["spec"].get("tasks") or []:
        spec = task.get("taskSpec") or {}
        passed = {p["name"] for p in task.get("params") or []}
        for p in spec.get("params") or []:
            if "default" not in p and p["name"] not in passed:
                problems.append(f"pipeline task {task['name']} does not pass param {p['name']}")
        for step in spec.get("steps") or []:
            script = step.get("script") or ""
            # Gitea's web archive route ignores basic auth on a private repo (404).
            if "/archive/" in script and "/api/v1/repos/" not in script.split("/archive/")[0].splitlines()[-1]:
                problems.append(f"pipeline task {task['name']} fetches the archive outside /api/v1/repos/")
            # The cluster's Gitea (1.21) has no compare API; it answered 404 and
            # refused every tier C apply (TD-275). Reachability is git's job.
            if "/compare/" in script:
                problems.append(f"pipeline task {task['name']} calls the Gitea compare API, which Gitea 1.21 lacks")
            if "REQUIRE_ON_MAIN" in script and "merge-base --is-ancestor" not in script:
                problems.append(f"pipeline task {task['name']} checks main without git merge-base --is-ancestor")
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
    # Ask first: without impersonation kubectl fails while downloading OpenAPI as
    # the target ("failed to download openapi: unknown"), which names no cause.
    for identity in (platform, applier):
        if not may_impersonate(identity):
            raise OwnerOnly(identity)
    for name, identity, ns, body, want_deny in cases:
        outcome, detail = dry_run(identity, ns, body)
        if outcome == "impersonation":
            raise OwnerOnly(detail)
        if outcome == "error":
            problems.append(f"{name}: dry-run failed for another reason: {detail}")
            continue
        denied = outcome == "denied"
        if denied != want_deny:
            problems.append(f"{name}: denied={denied} want {want_deny}")
    return problems


class OwnerOnly(Exception):
    """The caller may not impersonate the accounts the dry-runs act as."""


def may_impersonate(identity: str) -> bool:
    """Whether the current kubeconfig may act as system:serviceaccount:<ns>:<name>."""
    _, _, ns, name = identity.split(":")
    r = subprocess.run(
        ["kubectl", "auth", "can-i", "impersonate", f"serviceaccounts/{name}", "-n", ns],
        capture_output=True,
        text=True,
    )
    return r.stdout.strip() == "yes"


def app_namespaces_in_project() -> list[str]:
    """Every namespace an Application deploys into must be a project destination.

    The destination alone is not enough: bifrost-research also deploys a
    NetworkPolicy into data, and its sync failed when the project left data out.
    """
    import json

    def get(args: list[str]) -> dict:
        r = subprocess.run(["kubectl", "-n", "cicd", "get", *args, "-o", "json"], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip())
        return json.loads(r.stdout)

    problems: list[str] = []
    try:
        projects = {p["metadata"]["name"]: p for p in get(["appprojects"])["items"]}
        apps = get(["applications"])["items"]
    except RuntimeError as err:
        return [f"could not read Applications: {err}"]
    for app in apps:
        name = app["metadata"]["name"]
        project = projects.get(app["spec"].get("project", ""))
        if project is None:
            problems.append(f"{name}: project {app['spec'].get('project')} not found")
            continue
        allowed = {d.get("namespace") for d in project["spec"].get("destinations") or []}
        used = {app["spec"]["destination"].get("namespace")}
        used |= {r["namespace"] for r in app.get("status", {}).get("resources") or [] if r.get("namespace")}
        for ns in sorted(used - allowed - {None}):
            if "*" not in allowed:
                problems.append(f"{name}: deploys into {ns}, which project {project['metadata']['name']} does not allow")
    return problems


def classify(identity: str, returncode: int, stderr: str) -> str:
    """allowed | denied | impersonation | error.

    Only an admission policy or an RBAC refusal of the impersonated account is a
    denial. Before TD-277 any non-zero exit counted, so a caller who could not
    impersonate saw every deny case pass.
    """
    if returncode == 0:
        return "allowed"
    if "cannot impersonate" in stderr:
        return "impersonation"
    if "ValidatingAdmissionPolicy" in stderr:
        return "denied"
    if "is forbidden" in stderr and f'User "{identity}"' in stderr:
        return "denied"
    return "error"


def dry_run(identity: str, namespace: str, body: str) -> tuple[str, str]:
    r = subprocess.run(
        ["kubectl", "apply", "--dry-run=server", "-n", namespace, "--as", identity, "-f", "-"],
        input=body,
        capture_output=True,
        text=True,
    )
    return classify(identity, r.returncode, r.stderr), r.stderr.strip()[:300]


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
    skipped = ""
    if "--live" in sys.argv[1:]:
        try:
            problems += live()
        except OwnerOnly as err:
            skipped = str(err)
        problems += app_namespaces_in_project()
    if problems:
        for item in problems:
            print(f"FAIL {item}", file=sys.stderr)
        return 1
    if skipped:
        print("SKIP live dry-runs: this identity may not impersonate the platform and applier accounts.", file=sys.stderr)
        print("     Run --live with the Owner kubeconfig through owner_run_command.", file=sys.stderr)
        print("ok: static checks and Application namespaces; dry-runs not run (exit 3)")
        return 3
    print("ok: admission files match the actuation policy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
