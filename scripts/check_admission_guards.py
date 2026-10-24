#!/usr/bin/env python3
"""TD-271 admission files match the actuation policy.

Without --live this only reads the repo. --live asks the API server with
kubectl dry-run=server and is for after the Owner applies k8s/platform-rbac.

The dry-runs impersonate the PROD platform, applier and tekton-deliver ServiceAccounts,
so they need the Owner kubeconfig (run through owner_run_command). With the Agent's
read-only identity the dry-runs are skipped and the exit code is 3; the
Application-namespace check still runs (TD-277). A dry-run counts as denied
only when the API server names a ValidatingAdmissionPolicy or refuses the
impersonated account; any other failure is reported, not taken as a denial.
"""
from __future__ import annotations

import pathlib
import hashlib
import json
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
        "object.spec.source.kustomize.all(k, k == 'images')",
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
    # Gitea is the primary since Gitea-primary batch C; the GitHub addresses stay one week
    # for a move back (CUT-gitea-primary-2026-10-17), then this check drops them.
    for repo in ("bifrost-trade-infra", "bifrost-research"):
        for url in (f"http://gitea.cicd.svc.cluster.local:3000/bifrost/{repo}.git",
                    f"https://github.com/weitingzhao/{repo}.git"):
            if url not in project:
                problems.append(f"appproject bifrost missing {url}")
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
    problems += review_545_static(admission)
    return problems


APPLY_PIPELINE = ROOT / "k8s" / "cicd" / "tekton" / "apply-manifest" / "pipeline.yaml"
F1_REFUSAL = 'echo "tier ${tier} is applied only from main: requireOnMain must be true"'


def review_545_static(admission: str) -> list[str]:
    """Review 545: the Pod template denials are written for all three places, the delivery
    step list is readable, and the apply pipeline refuses tier C/D from a branch (F1)."""
    problems = []
    for prefix in ("object.spec.taskRunTemplate.podTemplate", "s.podTemplate", "object.spec.podTemplate"):
        for f in POD_TEMPLATE_DENIED:
            if f"!has({prefix}.{f})" not in admission:
                problems.append(f"40-admission.yaml: {prefix}.{f} is not required absent (review 545 F2)")
    if len(deliver_steps()) < 15:
        problems.append(f"40-admission.yaml: only {len(deliver_steps())} delivery steps found for tekton-deliver")
    pipeline = APPLY_PIPELINE.read_text()
    tier_at = pipeline.find("tier=$(sh /checks/apply-manifest-check.sh")
    refusal_at = pipeline.find(F1_REFUSAL)
    apply_at = pipeline.find("kubectl apply -f /tmp/normalized.json")
    if not (0 <= tier_at < refusal_at < apply_at):
        problems.append("apply-manifest pipeline: no tier C/D refusal between the tier check and kubectl apply (review 545 F1)")
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
            problems += plan_diff_problems(task["name"], script)
    return problems


def plan_diff_problems(task: str, script: str) -> list[str]:
    """The plan's server-side diff must act as the applier and must not hide errors.

    Under kubectl's default field manager, a changed field that bifrost-applier
    owns is a conflict and diff exits 2; `|| test "$?" -eq 1` then failed the
    plan with the reason left in /tmp/diff.txt (market-data 0.87.1, 2026-10-09).
    """
    problems: list[str] = []
    for line in script.splitlines():
        line = line.strip()
        if line.startswith("kubectl diff") and "--server-side" in line and "--field-manager=bifrost-applier" not in line:
            problems.append(f"pipeline task {task} diffs without --field-manager=bifrost-applier")
        if line.startswith("kubectl apply") and "--server-side" in line and "--field-manager=bifrost-applier" not in line:
            problems.append(f"pipeline task {task} applies without --field-manager=bifrost-applier")
        if line.startswith("kubectl diff") and '|| test "$?" -eq 1' in line:
            problems.append(f"pipeline task {task} swallows kubectl diff errors into the diff file")
    return problems


def live() -> list[str]:
    """Server-side dry-runs. Refused until the policies are applied."""
    problems: list[str] = []
    platform = "system:serviceaccount:bifrost-platform-prod:bifrost-platform"
    applier = "system:serviceaccount:cicd:bifrost-applier"
    deliver = "system:serviceaccount:cicd:tekton-deliver"
    stg_platform = "system:serviceaccount:bifrost-platform-stg:bifrost-platform"
    # A refusal case names the policy and a stable part of the validation message it must be
    # refused with (review 545 F3, 546 R2); RBAC or another validation refusing it is reported.
    pr_ref = (PR_POLICY, "must name a pipelineRef and must not use a resolver or an inline spec")
    pr_workspace = (PR_POLICY, "PipelineRun workspaces may only be volumeClaimTemplate or emptyDir")
    pr_pod = (PR_POLICY, "PipelineRun podTemplate may set only nodeSelector, tolerations and affinity")
    pr_steps = (PR_POLICY, "tekton-deliver runs only the listed delivery steps")
    pr_params = (PR_POLICY, "platform run parameters must be plain strings")
    pr_gitea = (PR_POLICY, "platform run giteaBase must be the in-cluster Gitea")
    tr_identity = (TR_POLICY, "platform TaskRuns run as default")
    tr_pod = (TR_POLICY, "TaskRun podTemplate may set only nodeSelector, tolerations and affinity")
    tr_params = (TR_POLICY, "platform TaskRun parameters must be plain strings")
    tr_gitea = (TR_POLICY, "platform TaskRun giteaBase must be the in-cluster Gitea")
    cm_platform = (CM_POLICY, "the Ops platform may write only its own ConfigMaps in cicd")
    cm_deliver = (CM_POLICY, "tekton-deliver may write only the STG Dockerfile ConfigMaps in cicd")
    app_spec = ("bifrost-platform-application", "platform may change only the sync operation and targetRevision")
    app_kustomize = ("bifrost-platform-application", "only a platform delivery may change spec.source.kustomize")
    cases = [
        ("inline-pipelinerun", platform, "cicd", inline_run(), True, pr_ref),
        ("resolver-pipelinerun", platform, "cicd", resolver_run(), True, pr_ref),
        ("secret-workspace-pipelinerun", platform, "cicd", secret_workspace_run(), True, pr_workspace),
        ("hostpath-podtemplate-pipelinerun", platform, "cicd", hostpath_run(), True, pr_pod),
        ("normal-pipelinerun", platform, "cicd", normal_run(), False),
        # TD-436: which steps may run as which identity, and plain parameters (TD-435).
        ("ci-template-deliver-pipelinerun", platform, "cicd", tekton_run("bifrost-ci-platform", [], template_sa="tekton-deliver"), True, pr_steps),
        ("gitea-base-pipelinerun", platform, "cicd", tekton_run("bifrost-ci-platform", [], params=[("giteaBase", "http://example.invalid/bifrost")]), True, pr_gitea),
        ("applier-taskrun", platform, "cicd", tekton_taskrun("bifrost-apply-manifest", "bifrost-applier"), True, tr_identity),
        ("deliver-other-taskrun", platform, "cicd", tekton_taskrun("bifrost-git-clone-gitea", "tekton-deliver"), True, tr_identity),
        ("refresh-taskrun", platform, "cicd", tekton_taskrun("bifrost-refresh-dockerfile-cms", "tekton-deliver"), False),
        # Review 545 F2: a Pod template may only place the Pod; it may not redirect names or add env.
        ("amd64-template-pipelinerun", platform, "cicd", tekton_run("bifrost-ci-platform", [], template_pod=AMD64), False),
        ("host-alias-template-pipelinerun", platform, "cicd", tekton_run("bifrost-ci-platform", [], template_pod=HOST_ALIAS), True, pr_pod),
        ("dns-step-pipelinerun", platform, "cicd",
         tekton_run("bifrost-deliver-platform", [("rollout", "tekton-deliver")], step_pod=DNS_OVERRIDE), True, pr_pod),
        ("amd64-mirror-taskrun", platform, "cicd", tekton_taskrun("bifrost-gitea-mirror-sync", "default", pod=AMD64), False),
        ("host-alias-mirror-taskrun", platform, "cicd", tekton_taskrun("bifrost-gitea-mirror-sync", "default", pod=HOST_ALIAS), True, tr_pod),
        ("env-mirror-taskrun", platform, "cicd",
         tekton_taskrun("bifrost-gitea-mirror-sync", "default", pod={"env": [{"name": "X", "value": "1"}]}), True, tr_pod),
        ("url-other-host-taskrun", platform, "cicd",
         tekton_taskrun("bifrost-refresh-dockerfile-cms", "tekton-deliver", params=[("url", "http://example.invalid/bifrost/x")]), True, tr_gitea),
        ("url-gitea-taskrun", platform, "cicd",
         tekton_taskrun("bifrost-refresh-dockerfile-cms", "tekton-deliver",
                        params=[("url", "http://gitea.cicd.svc.cluster.local:3000/bifrost/bifrost-trade-infra")]), False),
        ("semicolon-taskrun", platform, "cicd",
         tekton_taskrun("bifrost-refresh-dockerfile-cms", "tekton-deliver", params=[("revision", "main;true")]), True, tr_params),
        ("empty-param-taskrun", platform, "cicd",
         tekton_taskrun("bifrost-refresh-dockerfile-cms", "tekton-deliver", params=[("revision", "")]), False),
        # TD-434: the platform writes only its own ConfigMaps in cicd.
        ("deliver-writes-sync-script", deliver, "cicd", configmap("github-sync-scripts"), True, cm_deliver),
    ]
    cases += [(f"deliver-writes-{name}", deliver, "cicd", configmap(name), False) for name in DOCKERFILE_CONFIGMAPS]
    # Review 542 TD-434: every ConfigMap in cicd that another workload runs or obeys is refused
    # to both platform accounts; the five kinds the platform owns still pass.
    for who, identity in (("prod", platform), ("stg", stg_platform)):
        cases += [(f"{who}-writes-{name}", identity, "cicd", configmap(name), True, cm_platform) for name in CICD_FOREIGN_CONFIGMAPS]
        cases += [(f"{who}-writes-{name}", identity, "cicd", configmap(name), False) for name in PLATFORM_CICD_CONFIGMAPS]
    # TD-436: every step admission lets tekton-deliver run is allowed, and no CI step may borrow it.
    cases += [(f"deliver-step-{pair}", platform, "cicd", tekton_run(pair.split("/")[0], [(pair.split("/")[1], "tekton-deliver")]), False)
              for pair in deliver_steps()]
    cases += [(f"ci-step-as-deliver-{step}", platform, "cicd", tekton_run("bifrost-ci-platform", [(step, "tekton-deliver")]), True, pr_steps)
              for step in ci_platform_steps()]
    # TD-435, review 545 F5: Git ref characters pass, shell syntax, a leading dash, arrays and length do not.
    for label, value, deny in PARAM_CASES:
        cases.append((f"param-{label}", platform, "cicd", tekton_run("bifrost-ci-platform", [], params=[("revision", value)]), deny,
                      pr_params if deny else None))
    cases += [
        ("applier-hostpath-deployment", applier, "bifrost-dev", applier_hostpath_deployment(), True,
         ("bifrost-applier-pod-spec", "applier workloads must not use hostPath")),
        ("applier-grafana-deployment", applier, "monitoring", applier_grafana_deployment(), True,
         ("bifrost-applier-pod-spec", "applier workloads may only use a service account measured for that namespace")),
        ("application-sources", platform, "cicd", application_sources(), True, app_spec),
        ("application-kustomize", platform, "cicd", application_kustomize(), True, app_kustomize),
    ]
    # Built from the live Application where it can be read, so each case differs from it in the
    # one field it tests: a fixed repoURL or path would be denied by the repoURL rule instead and
    # pass for the wrong reason once the source moved to Gitea (review 261 B7).
    research = live_application("bifrost-research")
    if research is None:
        # no fixed fallback: it would be denied by the repoURL rule and pass for the wrong reason (review 262 B7)
        cases = cases[:-2]
        problems.append("application-sources, application-kustomize: cannot read the live Application bifrost-research")
    else:
        cases[-2:] = [
            ("application-sources", platform, "cicd", with_spec(research, sources=[{"repoURL": "https://example.invalid/other.git", "path": "k8s"}]), True, app_spec),
            ("application-kustomize", platform, "cicd", with_source(research, kustomize={"images": ["evil.example/x:1"]}), True, app_kustomize),
        ]
    # A platform delivery may pin its own application by digest and nothing else (TD-335).
    stg = live_application("bifrost-platform-stg")
    if stg is None:
        problems.append("deliver-pin: cannot read the live Application bifrost-platform-stg")
    else:
        cases += [
            ("deliver-pin", deliver, "cicd", with_source(stg, kustomize=delivery_pin()), False),
            ("deliver-pin-other-registry", deliver, "cicd",
             with_source(stg, kustomize=delivery_pin(api="evil.example/bifrost-platform-api@" + ZERO_DIGEST)), True, app_kustomize),
            ("deliver-pin-by-tag", deliver, "cicd",
             with_source(stg, kustomize=delivery_pin(console=PIN_TARGET % "console" + ":stg")), True, app_kustomize),
            ("deliver-pin-and-more", deliver, "cicd",
             with_source(stg, kustomize={**delivery_pin(), "namePrefix": "x-"}), True, app_kustomize),
            ("platform-pin", platform, "cicd", with_source(stg, kustomize=delivery_pin()), True, app_kustomize),
        ]
        if research is not None:
            cases.append(("deliver-pin-research", deliver, "cicd", with_source(research, kustomize=delivery_pin()), True, app_kustomize))
    # Review 542 A2, 545 F3/F4, 546 R1/R2: the platform may restart or scale a Deployment and set
    # its session annotation, nothing else. Sent as a full-object update (kubectl replace) of the
    # live object with its metadata kept (resourceVersion included, managedFields dropped), the
    # way the platform's GET-then-Update sends it.
    gitea = live_object("cicd", "deployment", "gitea", keep_metadata=True)
    if gitea is None:
        problems.append("deployment cases: cannot read the live Deployment cicd/gitea")
    else:
        for label, change, message in DEPLOYMENT_CASES:
            changed = json.loads(json.dumps(gitea))
            change(changed)
            if changed == gitea:
                problems.append(f"platform-deployment-{label}: the change leaves the live object as it is")
                continue
            cases.append((f"platform-deployment-{label}", platform, "cicd", json.dumps(changed), message is not None,
                          (DEPLOY_POLICY, message) if message else None, "replace"))
    # Ask first: without impersonation kubectl fails while downloading OpenAPI as
    # the target ("failed to download openapi: unknown"), which names no cause.
    for identity in (platform, applier, deliver, stg_platform):
        if not may_impersonate(identity):
            raise OwnerOnly(identity)
    for name, identity, ns, body, want_deny, *rest in cases:
        expect = rest[0] if rest else None
        verb = rest[1] if len(rest) > 1 else "apply"
        if want_deny and expect is None:
            problems.append(f"{name}: a refusal case must name its policy and message")
            continue
        outcome, detail = dry_run(identity, ns, body, verb)
        if outcome == "impersonation":
            raise OwnerOnly(detail)
        if outcome == "error":
            problems.append(f"{name}: dry-run failed for another reason: {detail}")
            continue
        denied = outcome == "denied"
        if denied != want_deny:
            problems.append(f"{name}: denied={denied} want {want_deny}" + (f": {detail}" if denied else ""))
        elif denied and not (f"'{expect[0]}'" in detail and expect[1] in detail):
            # review 545 F3, 546 R2: the refusal must come from the validation under test, not
            # from RBAC, another policy or another validation of the same policy
            problems.append(f"{name}: denied, but not by {expect[0]} with \"{expect[1]}\": {detail}")
    return problems


def crd_pod_template_drift() -> list[str]:
    """Review 545 F2: the Pod template fields of the live Tekton CRDs are exactly the allowed and
    denied lists, so a field a Tekton upgrade adds is decided before it can pass unchecked."""
    problems = []
    known = set(POD_TEMPLATE_ALLOWED) | set(POD_TEMPLATE_DENIED)
    for crd, path in (("taskruns.tekton.dev", ("podTemplate",)),
                      ("pipelineruns.tekton.dev", ("taskRunTemplate", "podTemplate")),
                      ("pipelineruns.tekton.dev", ("taskRunSpecs", "podTemplate"))):
        r = subprocess.run(["kubectl", "get", "crd", crd, "-o", "json"], capture_output=True, text=True)
        if r.returncode != 0:
            problems.append(f"crd {crd}: cannot read it: {r.stderr.strip()[:200]}")
            continue
        versions = [v for v in json.loads(r.stdout)["spec"]["versions"] if v["name"] == "v1"]
        node = versions[0]["schema"]["openAPIV3Schema"]["properties"]["spec"] if versions else {}
        for step in path:
            node = node.get("properties", {}).get(step, {})
            if node.get("type") == "array":
                node = node.get("items", {})
        fields = set(node.get("properties", {}))
        if not fields:
            problems.append(f"crd {crd} {'.'.join(path)}: no typed fields (a schemaless template needs a different rule)")
        for f in sorted(fields - known):
            problems.append(f"crd {crd} {'.'.join(path)}: new field {f}: add it to POD_TEMPLATE_DENIED and 40-admission.yaml, or allow it")
        for f in sorted(known - fields):
            problems.append(f"crd {crd} {'.'.join(path)}: field {f} is gone: check the lists still match the CRD")
        if node.get("x-kubernetes-preserve-unknown-fields") or node.get("additionalProperties"):
            problems.append(f"crd {crd} {'.'.join(path)}: no longer prunes unknown fields: the deny list is no allow-list")
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
    if "resulted in error" in stderr or "compilation error" in stderr:
        return "error"  # a policy that failed to evaluate denies too; it is not the rule working (review 545 F3)
    if "ValidatingAdmissionPolicy" in stderr:
        return "denied"
    if "is forbidden" in stderr and f'User "{identity}"' in stderr:
        return "denied"
    return "error"


def dry_run(identity: str, namespace: str, body: str, verb: str = "apply") -> tuple[str, str]:
    r = subprocess.run(
        ["kubectl", verb, "--dry-run=server", "-n", namespace, "--as", identity, "-f", "-"],
        input=body,
        capture_output=True,
        text=True,
    )
    return classify(identity, r.returncode, r.stderr), r.stderr.strip()[:600]


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


def live_application(name: str) -> dict | None:
    """The live Application without status and server-kept fields, or None when it cannot be read."""
    out = subprocess.run(["kubectl", "get", "application", name, "-n", "cicd", "-o", "json"], capture_output=True, text=True)
    if out.returncode != 0:
        return None
    obj = json.loads(out.stdout)
    obj.pop("status", None)
    for key in ("managedFields", "resourceVersion", "generation", "uid", "creationTimestamp", "annotations"):
        obj["metadata"].pop(key, None)
    return obj


PIN_SOURCE = "registry.cicd.svc.cluster.local:5000/bifrost-platform-%s"
PIN_TARGET = "192.168.10.73:30500/bifrost-platform-%s"
# Never a live pin, so each case changes spec.source.kustomize and is checked by the rule.
ZERO_DIGEST = "sha256:" + "0" * 64


def delivery_pin(api: str | None = None, console: str | None = None) -> dict:
    """The kustomize override a platform delivery's gitops-sync writes (task-argocd-pin-sync-platform)."""
    return {"images": [
        PIN_SOURCE % "api" + "=" + (api or PIN_TARGET % "api" + "@" + ZERO_DIGEST),
        PIN_SOURCE % "console" + "=" + (console or PIN_TARGET % "console" + "@" + ZERO_DIGEST),
    ]}


def with_spec(obj: dict, **fields) -> str:
    new = json.loads(json.dumps(obj))
    new["spec"].update(fields)
    return json.dumps(new)


def with_source(obj: dict, **fields) -> str:
    new = json.loads(json.dumps(obj))
    new["spec"]["source"].update(fields)
    return json.dumps(new)


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


def tekton_run(pipeline: str, steps: list[tuple[str, str]], template_sa: str = "",
               params: list[tuple[str, object]] | None = None, template_pod: dict | None = None,
               step_pod: dict | None = None) -> str:
    """A PipelineRun the platform could create: one pipeline, per-step identities, parameters,
    Pod templates for all steps or for the first listed step (TD-436, review 545 F2)."""
    key = repr((pipeline, steps, template_sa, params, template_pod, step_pod))
    spec: dict = {"pipelineRef": {"name": pipeline}}
    if template_sa or template_pod:
        spec["taskRunTemplate"] = {}
        if template_sa:
            spec["taskRunTemplate"]["serviceAccountName"] = template_sa
        if template_pod:
            spec["taskRunTemplate"]["podTemplate"] = template_pod
    if steps:
        spec["taskRunSpecs"] = [{"pipelineTaskName": task, "serviceAccountName": sa} for task, sa in steps]
        if step_pod:
            spec["taskRunSpecs"][0]["podTemplate"] = step_pod
    if params:
        spec["params"] = [{"name": n, "value": v} for n, v in params]
    return json.dumps({"apiVersion": "tekton.dev/v1", "kind": "PipelineRun",
                       "metadata": {"name": "td436-" + hashlib.sha1(key.encode()).hexdigest()[:10], "namespace": "cicd"},
                       "spec": spec})


def tekton_taskrun(task: str, sa: str, params: list[tuple[str, object]] | None = None,
                   pod: dict | None = None) -> str:
    """A TaskRun the platform could create with this identity (TD-436, review 545 F2)."""
    key = repr((task, sa, params, pod))
    spec: dict = {"taskRef": {"name": task}, "serviceAccountName": sa}
    if params:
        spec["params"] = [{"name": n, "value": v} for n, v in params]
    if pod:
        spec["podTemplate"] = pod
    return json.dumps({"apiVersion": "tekton.dev/v1", "kind": "TaskRun",
                       "metadata": {"name": "td436-" + hashlib.sha1(key.encode()).hexdigest()[:10], "namespace": "cicd"},
                       "spec": spec})


# Review 545 F2: the Pod template fields a platform run may set; every other field of the
# CRD's podTemplate must be absent (40-admission.yaml), and a field the CRD gains later is
# reported by crd_pod_template_drift() until it is placed in one list or the other.
POD_TEMPLATE_ALLOWED = ("affinity", "nodeSelector", "tolerations")
POD_TEMPLATE_DENIED = ("automountServiceAccountToken", "dnsConfig", "dnsPolicy", "enableServiceLinks", "env",
                       "hostAliases", "hostNetwork", "imagePullSecrets", "priorityClassName", "runtimeClassName",
                       "schedulerName", "securityContext", "topologySpreadConstraints", "volumes")
AMD64 = {"nodeSelector": {"kubernetes.io/arch": "amd64"}}
HOST_ALIAS = {"hostAliases": [{"ip": "192.0.2.10", "hostnames": ["gitea.cicd.svc.cluster.local"]}]}
DNS_OVERRIDE = {"dnsPolicy": "None", "dnsConfig": {"nameservers": ["192.0.2.53"]}}
PR_POLICY = "bifrost-platform-pipelinerun"
TR_POLICY = "bifrost-platform-taskrun"
CM_POLICY = "bifrost-cicd-configmap-writers"
DEPLOY_POLICY = "bifrost-platform-deployment-restart-scale"


def deliver_steps() -> list[str]:
    """The (pipeline/step) pairs 40-admission.yaml lets tekton-deliver run."""
    text = ADMISSION.read_text()
    return sorted(set(re.findall(r"'(bifrost-deliver-[a-z-]+/[a-z-]+)'", text)))


def ci_platform_steps() -> list[str]:
    import yaml
    docs = yaml.safe_load_all((ROOT / "k8s" / "cicd" / "tekton" / "pipeline-ci-platform.yaml").read_text())
    pipeline = next(d for d in docs if isinstance(d, dict) and d.get("kind") == "Pipeline")
    return [t["name"] for t in pipeline["spec"]["tasks"]]


# Inputs of other workloads in cicd (review 542): scripts and checkers that jobs execute,
# the applier's allowlist, backup settings, Argo CD configuration. A made-up backup-scripts
# suffix stands for the hashed name: the policy refuses every name outside the allowlist.
CICD_FOREIGN_CONFIGMAPS = (
    "github-sync-scripts",
    "bifrost-apply-manifest-check",
    "bifrost-actuation-policy",
    "bifrost-release-freeze-check",
    "gitea-backup-scripts-td434",
    "gitea-backup-recipient",
    "bifrost-api-stg-dockerfile",
    "argocd-cm",
    "argocd-rbac-cm",
)
# The platform's own ConfigMaps in cicd (46-cicd-configmaps.yaml); release-<run> by a sample name.
PLATFORM_CICD_CONFIGMAPS = (
    "lineage-thread-titles",
    "bifrost-release-window",
    "bifrost-release-policy",
    "bifrost-release-freeze",
    "release-td434-guard",
)


def configmap(name: str) -> str:
    """A ConfigMap write in cicd (TD-434)."""
    return f"apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: {name}\n  namespace: cicd\ndata:\n  td434: guard\n"


def live_object(namespace: str, kind: str, name: str, keep_metadata: bool = False) -> dict | None:
    """The live object stripped to what kubectl apply needs, or None when it cannot be read.
    keep_metadata keeps all metadata but managedFields (resourceVersion included) for a
    full-object update (kubectl replace), as the platform's GET-then-Update sends it."""
    r = subprocess.run(["kubectl", "get", kind, name, "-n", namespace, "-o", "json"], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    obj = json.loads(r.stdout)
    meta = obj.get("metadata", {})
    if keep_metadata:
        kept = {k: v for k, v in meta.items() if k != "managedFields"}
    else:
        kept = {"name": meta.get("name"), "namespace": meta.get("namespace")}
    obj["metadata"] = kept
    obj.pop("status", None)
    return obj


def _set_template_annotation(key: str, value: str):
    def change(d: dict) -> None:
        d["spec"]["template"].setdefault("metadata", {}).setdefault("annotations", {})[key] = value
    return change


def _set_annotation(key: str, value: str):
    def change(d: dict) -> None:
        d["metadata"].setdefault("annotations", {})[key] = value
    return change


def _flip_strategy(d: dict) -> None:
    kind = d["spec"].get("strategy", {}).get("type", "RollingUpdate")
    d["spec"]["strategy"] = {"type": "RollingUpdate"} if kind == "Recreate" else {"type": "Recreate"}


def _set_image(d: dict) -> None:
    d["spec"]["template"]["spec"]["containers"][0]["image"] = "example.invalid/gitea:td432"


# (label, change to a copy of the live cicd/gitea Deployment, None when allowed or the
# validation message that must refuse it) — review 545 F3/F4, 546 R1/R2
DEPLOYMENT_CASES = (
    ("restart", _set_template_annotation("kubectl.kubernetes.io/restartedAt", "2026-10-24T00:00:00Z"), None),
    ("scale", lambda d: d["spec"].__setitem__("replicas", 0 if d["spec"].get("replicas", 1) else 1), None),
    ("session-annotation", _set_annotation("bifrost.dev/session-desired-replicas", "td432"), None),
    ("image", _set_image, "not change its pod spec"),
    ("pause", lambda d: d["spec"].__setitem__("paused", not d["spec"].get("paused", False)), "how a Deployment rolls out"),
    ("strategy", _flip_strategy, "how a Deployment rolls out"),
    ("min-ready", lambda d: d["spec"].__setitem__("minReadySeconds", d["spec"].get("minReadySeconds", 0) + 7), "how a Deployment rolls out"),
    ("template-label", lambda d: d["spec"]["template"].setdefault("metadata", {}).setdefault("labels", {}).__setitem__("td432", "x"),
     "pod template labels"),
    ("template-annotation", _set_template_annotation("td432/other", "x"), "only the restartedAt annotation"),
    ("own-label", lambda d: d["metadata"].setdefault("labels", {}).__setitem__("td432", "x"), "session-desired-replicas annotation"),
    ("own-annotation", _set_annotation("td432/other", "x"), "session-desired-replicas annotation"),
    ("finalizer", lambda d: d["metadata"].setdefault("finalizers", []).append("td432.example/hold"), "finalizers or owner references"),
    ("owner-reference", lambda d: d["metadata"].setdefault("ownerReferences", []).append(
        {"apiVersion": "v1", "kind": "ConfigMap", "name": "td432", "uid": "00000000-0000-0000-0000-000000000000"}),
     "finalizers or owner references"),
)

# The five STG Dockerfile ConfigMaps tekton-deliver writes (46-cicd-configmaps.yaml).
DOCKERFILE_CONFIGMAPS = (
    "bifrost-api-stg-dockerfile",
    "bifrost-frontend-stg-dockerfile",
    "bifrost-worker-stg-dockerfile",
    "bifrost-platform-api-stg-dockerfile",
    "bifrost-platform-console-stg-dockerfile",
)

# (label, revision parameter value, denied?) — TD-435, review 545 F5
PARAM_CASES = (
    ("sha", "0" * 40, False),
    ("branch-with-equals", "feature/fix=1", False),
    ("branch-non-ascii", "feature/修复", False),
    ("tag", "v0.24.0+build.1", False),
    ("length-256", "a" * 256, False),
    ("length-257", "a" * 257, True),
    ("semicolon", "main;true", True),
    ("command-substitution", "$(id)", True),
    ("space", "main true", True),
    ("leading-dash", "--upload-pack=x", True),
    ("empty", "", False),
    ("object", {"a": "b"}, True),
    ("array", ["main"], True),
)


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
        problems += crd_pod_template_drift()
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
