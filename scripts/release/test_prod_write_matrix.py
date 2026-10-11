"""Offline fixtures for the platform PROD write matrix. No cluster."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prod_write_matrix as matrix  # noqa: E402
import prod_write_rbac as rbac  # noqa: E402


FIX = Path(__file__).resolve().parent / "testdata" / "prod_write_matrix"
WRITE_VERBS = ",".join(rbac.WRITE_VERBS)


def _docs(name: str) -> list[dict]:
    return matrix.load_files(FIX / name, {".yaml", ".yml", ".json"})


def _targets() -> list[rbac.Target]:
    return matrix.load_targets(FIX / "targets.yaml")


def _report(name: str, effects=None, exceptions=None, source: str = "repo") -> matrix.Report:
    return matrix.analyze(_docs(name), _targets(), effects or [], exceptions or [], source, include_fixed=False)


def _rows(report: matrix.Report, identity: str, target: str) -> list[matrix.Row]:
    return [row for row in report.rows if row.identity == identity and row.target == target]


def _verbs(report: matrix.Report, identity: str, target: str) -> set[str]:
    return {row.verbs for row in _rows(report, identity, target)}


def test_missing_identity_is_reported() -> None:
    report = _report("missing_identity")
    assert "system:serviceaccount:cicd:extra-writer" in report.not_in_plan_table
    assert _verbs(report, "system:serviceaccount:cicd:extra-writer", "deployment/platform-api") == {"patch"}
    text = matrix.render_md(report)
    assert "system:serviceaccount:cicd:extra-writer" in text


def test_wildcard_expands_to_every_target() -> None:
    report = _report("wildcard")
    ids = {target.id for target in _targets()}
    concrete = [row for row in report.rows if not row.identity.startswith("unknown-surface")]
    got = {row.target for row in concrete}
    assert got == ids
    assert {row.verbs for row in concrete} == {WRITE_VERBS}


def test_rolebinding_to_clusterrole_stays_in_its_namespace() -> None:
    report = _report("rolebinding_ns")
    assert _verbs(report, "user:scoped-user", "deployment/stg-api") == {"patch"}
    assert _rows(report, "user:scoped-user", "deployment/platform-api") == []


def test_resource_names_limit_update_but_not_create() -> None:
    report = _report("resource_names")
    user = "user:named-user"
    assert _verbs(report, user, "deployment/platform-api") == {"create,update"}
    assert _verbs(report, user, "deployment/platform-workers") == {"create"}
    assert _verbs(report, user, "deployment/stg-api") == {"create"}
    assert _rows(report, user, "deployment/platform-api/scale") == []


def test_subresource_rule_does_not_grant_the_parent() -> None:
    report = _report("subresource")
    user = "user:sub-user"
    assert _verbs(report, user, "deployment/platform-api/scale") == {"patch"}
    assert _rows(report, user, "deployment/platform-api") == []
    assert _rows(report, user, "pod/bifrost-platform-prod/eviction") == []


def test_aggregation_adds_the_selected_rules() -> None:
    report = _report("aggregation")
    user = "user:agg-user"
    assert _verbs(report, user, "deployment/platform-api") == {"patch"}
    assert _rows(report, user, "deployment/platform-api/scale") == []


def test_missing_binding_removes_the_rows() -> None:
    present = _report("binding_present")
    assert _verbs(present, "user:bound-user", "deployment/platform-api") == {"patch"}
    absent = _report("missing_binding")
    assert absent.rows == []
    stripped = [doc for doc in _docs("binding_present") if doc.get("kind") != "ClusterRoleBinding"]
    removed = matrix.analyze(stripped, _targets(), [], [], "repo", include_fixed=False)
    assert removed.rows == []


def test_matching_policy_without_effect_is_gated_unclassified() -> None:
    report = _report("gated")
    rows = _rows(report, "user:gated-user", "deployment/platform-api")
    assert len(rows) == 1
    assert rows[0].admission == "gated: demo-gate"
    assert rows[0].classification == "unclassified"
    assert "demo gate does not refuse image" in rows[0].cel
    stg = _rows(report, "user:gated-user", "deployment/stg-api")
    assert stg[0].admission == "none"
    assert stg[0].classification == "unclassified"


def test_reviewed_effect_refuses_only_while_the_policy_matches() -> None:
    effects = [
        {
            "policy": "demo-gate",
            "identity": "user:gated-user",
            "field": "image",
            "effect": "refuse",
            "note": "fixture refuse",
        }
    ]
    report = _report("gated", effects=effects)
    prod = _rows(report, "user:gated-user", "deployment/platform-api")[0]
    assert prod.classification == "refused"
    assert prod.admission == "gated: demo-gate"
    stg = _rows(report, "user:gated-user", "deployment/stg-api")[0]
    assert stg.classification == "unclassified"


def test_missing_policy_turns_refused_back_into_unclassified() -> None:
    loaded = yaml.safe_load((FIX / "missing_policy" / "effects.yaml").read_text(encoding="utf-8"))
    report = _report("missing_policy", effects=loaded["effects"])
    row = _rows(report, "user:gated-user", "deployment/platform-api")[0]
    assert row.classification == "unclassified"
    assert row.admission == "none"
    assert report.invalid == []


def test_exception_without_expiry_is_invalid_and_not_applied() -> None:
    loaded = yaml.safe_load((FIX / "bad_exception" / "exceptions.yaml").read_text(encoding="utf-8"))
    report = _report("rolebinding_ns", exceptions=loaded["exceptions"])
    assert report.exit_code == 1
    assert any("expires" in item for item in report.invalid)
    assert all(row.classification != "named-exception" for row in report.rows)


def test_complete_exception_is_named() -> None:
    exceptions = [
        {
            "identity": "user:scoped-user",
            "target": "deployment/stg-api",
            "field": "image",
            "check": "fixture-check",
            "expires": "2026-12-31",
            "removes": "step-9",
        }
    ]
    report = _report("rolebinding_ns", exceptions=exceptions)
    row = _rows(report, "user:scoped-user", "deployment/stg-api")[0]
    assert row.classification == "named-exception"
    assert report.exit_code == 0


def test_undominated_rollout_is_a_row_and_dominated_is_not() -> None:
    open_rows = matrix.analyze(_docs("dag/undominated.yaml"), [], [], [], "repo", include_fixed=False)
    assert [row.field for row in open_rows.rows] == ["rollout"]
    assert open_rows.rows[0].identity == "pipeline/demo-undominated"
    closed = matrix.analyze(_docs("dag/dominated.yaml"), [], [], [], "repo", include_fixed=False)
    assert closed.rows == []
    parallel = matrix.analyze(_docs("dag/parallel.yaml"), [], [], [], "repo", include_fixed=False)
    # runAfter is an edge, not a join. validate -> rollout never passes the freeze.
    assert [row.field for row in parallel.rows] == ["rollout"]


def test_dump_and_repo_objects_give_the_same_rows() -> None:
    targets = _targets()
    pair = FIX / "dump_pair"
    from_yaml = matrix.analyze(matrix.load_files(pair, {".yaml", ".yml"}), targets, [], [], "repo", include_fixed=True)
    from_json = matrix.analyze(matrix.load_dump(pair), targets, [], [], "measured", include_fixed=True)
    def bare(report: matrix.Report) -> list[tuple]:
        return [row.key() for row in report.rows]

    assert bare(from_yaml) == bare(from_json)
    assert {row.source for row in from_yaml.rows} == {"repo"}
    assert {row.source for row in from_json.rows} == {"measured"}


def test_cli_dump_marks_measured_and_matches_repo_loader() -> None:
    script = Path(matrix.__file__)
    completed = subprocess.run(
        [sys.executable, str(script), "--from-dump", str(FIX / "dump_pair"), "--format", "json"],
        check=False,
        capture_output=True,
        text=True,
    )
    # Fixture grants one write and the fixed rows are unclassified, so exit is 1.
    assert completed.returncode == 1, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["source"] == "measured"
    assert any(row["identity"] == "user:dump-user" and row["source"] == "measured" for row in payload["rows"])


def test_output_is_stable() -> None:
    first = _report("aggregation")
    second = _report("aggregation")
    assert matrix.render_md(first) == matrix.render_md(second)
    assert matrix.render_json(first) == matrix.render_json(second)
    assert matrix.render_md(first, list_only=True) == matrix.render_md(second, list_only=True)


def test_repository_matrix_sees_the_writers_the_plan_table_missed() -> None:
    report = matrix.build_report(matrix.REPO, None, matrix.TARGETS_PATH, matrix.EFFECTS_PATH, matrix.EXCEPTIONS_PATH)
    assert report.source == "repo"
    assert report.exit_code == 1
    assert report.invalid == []
    identities = {row.identity for row in report.rows}
    prod = "system:serviceaccount:bifrost-platform-prod:bifrost-platform"
    stg = "system:serviceaccount:bifrost-platform-stg:bifrost-platform"
    deliver = "system:serviceaccount:cicd:tekton-deliver"
    applier = "system:serviceaccount:cicd:bifrost-applier"
    trigger = "system:serviceaccount:cicd:tekton-trigger"
    ttl = "system:serviceaccount:cicd:tekton-pipelinerun-ttl"
    assert {prod, deliver, applier, trigger, stg, ttl} <= identities
    assert ttl in report.not_in_plan_table
    assert applier in report.not_in_plan_table
    assert stg in report.not_in_plan_table
    assert deliver not in report.not_in_plan_table

    def verbs(identity: str, target: str, field: str) -> str:
        found = [row.verbs for row in report.rows if row.identity == identity and row.target == target and row.field == field]
        assert found, (identity, target, field)
        return found[0]

    assert "patch" in verbs(deliver, "deployment/platform-api", "image")
    assert not any(row.identity == deliver and row.target == "deployment/platform-api/scale" for row in report.rows)
    assert verbs(deliver, "configmap/cicd", "data") == "create,patch,update"
    assert "patch" in verbs(deliver, "configmap/bifrost-release-freeze", "data")
    assert "patch" in verbs(deliver, "application/bifrost-platform-prod", "operation")
    assert "delete" not in verbs(deliver, "configmap/bifrost-release-freeze", "data")
    assert "patch" in verbs(stg, "configmap/bifrost-release-freeze", "data")
    assert not any(row.identity == stg and row.target == "deployment/platform-api" for row in report.rows)
    assert "delete" in verbs(prod, "pod/bifrost-platform-prod", "delete")
    assert "create" in verbs(prod, "pod/bifrost-platform-prod/eviction", "eviction")
    assert "patch" in verbs(prod, "deployment/platform-api/scale", "replicas")
    image = next(row for row in report.rows if row.identity == applier and row.target == "deployment/platform-api" and row.field == "image")
    assert image.classification == "unclassified"
    assert image.admission == "gated: bifrost-applier-pod-spec"
    source = next(row for row in report.rows if row.identity == prod and row.target == "application/bifrost-platform-prod" and row.field == "spec.source")
    assert source.classification == "unclassified"
    locked = next(row for row in report.rows if row.identity == prod and row.target == "application/bifrost-platform-prod" and row.field == "spec.source.repoURL")
    assert locked.classification == "refused"
    revision = next(row for row in report.rows if row.identity == prod and row.target == "application/bifrost-platform-prod" and row.field == "spec.source.targetRevision")
    assert revision.classification == "unclassified"
    assert "patch" in verbs(prod, "node", "cordon")
    assert any(row.identity == applier and row.target == "networkpolicy/bifrost-platform-prod" for row in report.rows)
    assert any(row.identity == applier and row.target == "poddisruptionbudget/bifrost-platform-prod" for row in report.rows)
    assert any(row.identity == applier and row.target == "serviceaccount/bifrost-platform-prod" for row in report.rows)
    assert any("unresolved roleRef: argocd-application-controller -> argocd-application-controller" in row.admission for row in report.rows)
    assert any(row.identity == "pipeline/bifrost-deliver-platform" and row.field == "image-push" for row in report.rows)
    assert any(row.identity == "system:masters" for row in report.rows)
    assert any(row.identity.startswith("unknown-surface:") for row in report.rows)
    operation = next(row for row in report.rows if row.identity == prod and row.target == "application/bifrost-platform-prod" and row.field == "operation")
    assert operation.classification == "unclassified"
    assert operation.admission == "gated: bifrost-platform-application"
    assert "delete" in verbs(ttl, "pipelinerun/cicd", "pipelineRef")
    trigger_ref = next(row for row in report.rows if row.identity == trigger and row.target == "pipelinerun/cicd" and row.field == "pipelineRef")
    assert trigger_ref.admission == "none"
    assert trigger_ref.classification == "unclassified"
    dag_fields = {row.field for row in report.rows if row.identity == "pipeline/bifrost-deliver-platform-prod"}
    assert {"rollout", "sync", "image-push"} <= dag_fields
    assert not any(row.identity == "pipeline/demo-dominated" for row in report.rows)
    assert any(row.identity == "anyone-who-reaches-the-registry" and row.admission.startswith("registry has no authentication") for row in report.rows)
    assert any(row.identity == "anyone-who-can-push-main" and row.field == "automated-sync" for row in report.rows)
    assert any(row.identity == "owner-admin" for row in report.rows)
    assert any(row.identity == "owner_run_command" for row in report.rows)


def _yaml(text: str) -> list[dict]:
    return [doc for doc in yaml.safe_load_all(text) if isinstance(doc, dict)]


def test_effect_names_exact_fields_not_the_parent() -> None:
    docs = _docs("gated")
    # Reuse the proven demo-gate, but refuse only a child field.
    effects = [{"policy": "demo-gate", "identity": "*", "field": "image.tag", "effect": "refuse", "note": "child only"}]
    targets = [
        rbac.Target("deployment/platform-api", "bifrost-platform-prod", "apps", "deployments", "platform-api", "", ("image", "image.tag"), "fixture", "v1")
    ]
    report = matrix.analyze(docs, targets, effects, [], "repo", include_fixed=False)
    parent = _rows(report, "user:gated-user", "deployment/platform-api")
    by_field = {row.field: row for row in parent}
    assert by_field["image"].classification == "unclassified"
    assert by_field["image.tag"].classification == "refused"
    shipped = matrix.load_effects()
    fields = {(item.get("policy"), item.get("field")) for item in shipped if item.get("effect") == "refuse"}
    assert ("bifrost-platform-application", "spec.source") not in fields
    assert ("bifrost-platform-application", "spec.source.repoURL") in fields
    assert ("bifrost-platform-application", "spec.source.targetRevision") not in fields


def test_uncertain_admission_does_not_refuse() -> None:
    effects = [{"policy": "demo-gate", "identity": "user:gated-user", "field": "image", "effect": "refuse", "note": "would refuse"}]
    base = """
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: {name: patch-dep}
rules: [{apiGroups: ["apps"], resources: ["deployments"], verbs: ["patch"]}]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: {name: patch-dep}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: patch-dep}
subjects: [{kind: User, name: gated-user}]
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata: {name: demo-gate}
spec:
  failurePolicy: Ignore
  matchConstraints:
    resourceRules: [{apiGroups: ["apps"], apiVersions: ["v1"], operations: ["UPDATE"], resources: ["deployments"]}]
  validations: [{expression: "true", message: uncertain}]
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: {name: demo-gate}
spec: {policyName: demo-gate, validationActions: [Deny]}
"""
    report = matrix.analyze(_yaml(base), _targets(), effects, [], "repo", include_fixed=False)
    row = _rows(report, "user:gated-user", "deployment/platform-api")[0]
    assert row.classification == "unclassified"
    assert "uncertain:" in row.admission
    unknown_condition = base.replace("failurePolicy: Ignore", "failurePolicy: Fail").replace(
        "validations:",
        "matchConditions: [{name: other, expression: 'request.userInfo.groups.exists(g, true)'}]\n  validations:",
    )
    conditioned = matrix.analyze(_yaml(unknown_condition), _targets(), effects, [], "repo", include_fixed=False)
    cond_row = _rows(conditioned, "user:gated-user", "deployment/platform-api")[0]
    assert cond_row.classification == "unclassified"
    assert "matchCondition" in cond_row.admission
    selected = base.replace("failurePolicy: Ignore", "failurePolicy: Fail").replace(
        "resources: [\"deployments\"]",
        "resources: [\"deployments\"]\n        scope: Namespaced",
    )
    # objectSelector makes a matching policy uncertain.
    selected = base.replace("failurePolicy: Ignore", "failurePolicy: Fail")
    selected = selected.replace(
        "resourceRules:",
        "objectSelector: {matchLabels: {app: demo}}\n    resourceRules:",
    )
    obj = matrix.analyze(_yaml(selected), _targets(), effects, [], "repo", include_fixed=False)
    obj_row = _rows(obj, "user:gated-user", "deployment/platform-api")[0]
    assert obj_row.classification == "unclassified"
    assert "objectSelector" in obj_row.admission


def test_admission_wildcard_does_not_cover_subresources() -> None:
    text = """
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: {name: patch-dep}
rules: [{apiGroups: ["apps", ""], resources: ["*"], verbs: ["patch"]}]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: {name: patch-dep}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: patch-dep}
subjects: [{kind: User, name: gated-user}]
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata: {name: demo-gate}
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules: [{apiGroups: ["*"], apiVersions: ["*"], operations: ["UPDATE"], resources: ["*"]}]
  validations: [{expression: "true", message: star}]
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: {name: demo-gate}
spec: {policyName: demo-gate, validationActions: [Deny]}
"""
    report = matrix.analyze(_yaml(text), _targets(), [], [], "repo", include_fixed=False)
    parent = _rows(report, "user:gated-user", "deployment/platform-api")[0]
    scale = _rows(report, "user:gated-user", "deployment/platform-api/scale")[0]
    assert parent.admission == "gated: demo-gate"
    assert scale.admission == "none"


def test_unconstrained_image_parameter_reaches_prod() -> None:
    text = """
apiVersion: tekton.dev/v1
kind: Pipeline
metadata: {name: deliver-stg, namespace: cicd}
spec:
  params: [{name: platformApiImage, type: string, default: registry.example/bifrost-platform-api:stg}]
  tasks:
    - name: build
      taskRef: {name: kaniko}
      params: [{name: image, value: $(params.platformApiImage)}]
---
apiVersion: tekton.dev/v1
kind: Task
metadata: {name: kaniko, namespace: cicd}
spec:
  params: [{name: image, type: string}]
  steps: [{name: push, image: gcr.io/kaniko-project/executor, args: ["--destination=$(params.image)"]}]
"""
    report = matrix.analyze(_yaml(text), [], [], [], "repo", include_fixed=False)
    assert any(row.identity == "pipeline/deliver-stg" and row.field == "image-push" for row in report.rows)
    pinned = text.replace("type: string, default:", "type: string, enum: ['registry.example/bifrost-platform-api:stg'], default:")
    closed = matrix.analyze(_yaml(pinned), [], [], [], "repo", include_fixed=False)
    assert closed.rows == []


def test_freeze_must_dominate_every_path_and_finally_runs() -> None:
    bypass = """
apiVersion: tekton.dev/v1
kind: Pipeline
metadata: {name: bypass, namespace: cicd}
spec:
  tasks:
    - name: release-window
      taskRef: {name: bifrost-release-window}
    - name: other
      taskSpec:
        steps: [{name: roll, script: kubectl rollout restart deployment/platform-api -n bifrost-platform-prod}]
    - name: rollout
      runAfter: [other]
      taskRef: {name: bifrost-rollout-platform-stg}
      params: [{name: namespace, value: bifrost-platform-prod}]
---
apiVersion: tekton.dev/v1
kind: Task
metadata: {name: bifrost-rollout-platform-stg, namespace: cicd}
spec:
  steps: [{name: roll, script: kubectl rollout restart deployment/platform-api}]
"""
    report = matrix.analyze(_yaml(bypass), [], [], [], "repo", include_fixed=False)
    assert any(row.target == "dag/bypass/rollout" for row in report.rows)
    skipped = bypass.replace("taskRef: {name: bifrost-release-window}", "taskRef: {name: bifrost-release-window}\n      when: [{input: 'yes', operator: in, values: ['yes']}]")
    # The dominated fixture has a single path. A when on that freeze keeps the row.
    dominated = (_docs("dag/dominated.yaml")[0])
    dominated["spec"]["tasks"][0]["when"] = [{"input": "yes", "operator": "in", "values": ["yes"]}]
    opened = matrix.analyze([dominated], [], [], [], "repo", include_fixed=False)
    assert opened.rows
    continued = _docs("dag/dominated.yaml")
    continued[0]["spec"]["tasks"][0]["onError"] = "continue"
    assert matrix.analyze(continued, [], [], [], "repo", include_fixed=False).rows
    final = """
apiVersion: tekton.dev/v1
kind: Pipeline
metadata: {name: fin, namespace: cicd}
spec:
  tasks:
    - name: release-window
      taskRef: {name: bifrost-release-window}
  finally:
    - name: rollout
      taskRef: {name: bifrost-rollout-platform-stg}
      params: [{name: namespace, value: bifrost-platform-prod}]
---
apiVersion: tekton.dev/v1
kind: Task
metadata: {name: bifrost-rollout-platform-stg, namespace: cicd}
spec:
  steps: [{name: roll, script: kubectl rollout restart deployment/platform-api}]
"""
    fin = matrix.analyze(_yaml(final), [], [], [], "repo", include_fixed=False)
    assert any(row.target == "dag/fin/rollout" for row in fin.rows)


def test_command_args_and_unclassified_steps_are_side_effects() -> None:
    text = """
apiVersion: tekton.dev/v1
kind: Pipeline
metadata: {name: cmd, namespace: cicd}
spec:
  tasks:
    - name: push
      taskSpec:
        steps: [{name: go, command: ["kubectl"], args: ["apply", "-f", "prod.yaml", "-n", "bifrost-platform-prod"]}]
    - name: mystery
      taskSpec:
        steps: [{name: run, script: "python3 /opt/unknown.py --namespace bifrost-platform-prod"}]
"""
    report = matrix.analyze(_yaml(text), [], [], [], "repo", include_fixed=False)
    fields = {row.field for row in report.rows}
    assert "apply" in fields
    assert "unclassified-step" in fields


def test_impersonate_bind_and_token_are_derived() -> None:
    text = """
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: {name: powerful}
rules: [{apiGroups: ["apps"], resources: ["deployments"], verbs: ["patch"]}]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: {name: borrower}
rules:
  - {apiGroups: [""], resources: ["users"], resourceNames: ["powerful-user"], verbs: ["impersonate"]}
  - {apiGroups: ["rbac.authorization.k8s.io"], resources: ["clusterroles"], resourceNames: ["powerful"], verbs: ["bind"]}
  - {apiGroups: ["rbac.authorization.k8s.io"], resources: ["clusterrolebindings"], verbs: ["create"]}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: {name: powerful}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: powerful}
subjects: [{kind: User, name: powerful-user}]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: {name: borrower}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: borrower}
subjects: [{kind: User, name: borrower}]
"""
    report = matrix.analyze(_yaml(text), _targets(), [], [], "repo", include_fixed=False)
    impersonated = [row for row in report.rows if row.identity == "user:borrower" and row.path == "via impersonate user:powerful-user"]
    assert impersonated
    assert any(row.target == "deployment/platform-api" for row in impersonated)
    bound = [row for row in report.rows if row.identity == "user:borrower" and row.path == "via bind clusterrole/powerful"]
    assert any(row.target == "deployment/platform-api" for row in bound)


def test_serviceaccount_inherits_groups_and_masters_is_fixed() -> None:
    text = """
apiVersion: v1
kind: ServiceAccount
metadata: {name: worker, namespace: bifrost-platform-prod}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: {name: writers}
rules: [{apiGroups: ["apps"], resources: ["deployments"], verbs: ["patch"]}]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: {name: writers}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: writers}
subjects: [{kind: Group, name: system:serviceaccounts}]
"""
    report = matrix.analyze(_yaml(text), _targets(), [], [], "repo", include_fixed=True, today=__import__("datetime").date(2026, 10, 11))
    assert _verbs(report, "system:serviceaccount:bifrost-platform-prod:worker", "deployment/platform-api") == {"patch"}
    assert any(row.identity == "system:masters" and row.verbs == "*" for row in report.rows)
    anon = """
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: {name: writers}
rules: [{apiGroups: ["apps"], resources: ["deployments"], verbs: ["patch"]}]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: {name: writers}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: writers}
subjects: [{kind: Group, name: system:unauthenticated}]
"""
    anon_report = matrix.analyze(_yaml(anon), _targets(), [], [], "repo", include_fixed=False)
    assert _verbs(anon_report, "system:anonymous", "deployment/platform-api") == {"patch"}


def test_unnamed_target_keeps_resource_names() -> None:
    text = """
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: {name: named}
rules: [{apiGroups: [""], resources: ["configmaps"], resourceNames: ["platform-config"], verbs: ["patch"]}]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: {name: named}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: named}
subjects: [{kind: User, name: named-user}]
"""
    target = rbac.Target("configmap/cicd", "cicd", "", "configmaps", "", "", ("data",), "unnamed", "v1")
    # ClusterRoleBinding is cluster scoped, so the namespace matches.
    report = matrix.analyze(_yaml(text), [target], [], [], "repo", include_fixed=False)
    rows = _rows(report, "user:named-user", "configmap/cicd")
    assert rows
    assert rows[0].only == "only: platform-config"
    assert rows[0].verbs == "patch"


def test_aggregation_cycle_and_dump_materialised_rules() -> None:
    text = """
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: {name: role-a}
aggregationRule: {clusterRoleSelectors: [{matchLabels: {aggregate: 'yes'}}]}
rules: []
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: {name: role-b, labels: {aggregate: 'yes'}}
aggregationRule: {clusterRoleSelectors: [{matchLabels: {aggregate: loop}}]}
rules: []
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: {name: role-c, labels: {aggregate: 'yes'}}
rules: [{apiGroups: ["apps"], resources: ["deployments"], verbs: ["patch"]}]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: {name: role-b}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: role-b}
subjects: [{kind: User, name: cycle-user}]
"""
    # role-a selects aggregate=yes (b and c). role-b selects aggregate=loop (nobody) but
    # the cycle the review describes is b aggregates a. Label a so b selects it.
    text = text.replace("metadata: {name: role-a}", "metadata: {name: role-a, labels: {aggregate: loop}}")
    report = matrix.analyze(_yaml(text), _targets(), [], [], "repo", include_fixed=False)
    assert _verbs(report, "user:cycle-user", "deployment/platform-api") == {"patch"}
    dumped = """
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: {name: role-a}
aggregationRule: {clusterRoleSelectors: [{matchLabels: {missing: label}}]}
rules: [{apiGroups: ["apps"], resources: ["deployments"], verbs: ["patch"]}]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: {name: role-a}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: role-a}
subjects: [{kind: User, name: dump-user}]
"""
    kept = matrix.analyze(_yaml(dumped), _targets(), [], [], "measured", include_fixed=False, from_dump=True)
    assert _verbs(kept, "user:dump-user", "deployment/platform-api") == {"patch"}
    dropped = matrix.analyze(_yaml(dumped), _targets(), [], [], "repo", include_fixed=False, from_dump=False)
    assert _rows(dropped, "user:dump-user", "deployment/platform-api") == []


def test_dump_manifest_and_unresolved_roleref() -> None:
    script = Path(matrix.__file__)
    missing = FIX / "dump_pair"
    # A copy is not required: deleting the check is the incomplete directory.
    incomplete = FIX / "dump_incomplete"
    incomplete.mkdir(exist_ok=True)
    (incomplete / "MANIFEST.json").write_text('{"files": []}\n', encoding="utf-8")
    completed = __import__("subprocess").run(
        [sys.executable, str(script), "--from-dump", str(incomplete), "--format", "json"],
        check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 1
    assert "missing file" in completed.stderr
    broken = """
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: {name: missing-bind}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: missing-role}
subjects: [{kind: User, name: someone}]
"""
    repo = matrix.analyze(_yaml(broken), _targets(), [], [], "repo", include_fixed=False)
    assert any(row.identity == "unresolved" and "missing-bind -> missing-role" in row.admission for row in repo.rows)
    assert repo.rows[0].classification == "unclassified"
    try:
        matrix.analyze(_yaml(broken), _targets(), [], [], "measured", include_fixed=False, from_dump=True)
    except SystemExit as exc:
        assert "unresolved roleRef: missing-bind -> missing-role" in str(exc)
    else:
        raise AssertionError("dump mode accepted an unresolved roleRef")


def test_exception_wildcard_expiry_and_system_component() -> None:
    import datetime as dt
    today = dt.date(2026, 10, 11)
    wildcard = [{
        "identity": "*", "target": "deployment/stg-api", "field": "image",
        "check": "fixture", "expires": "2099-01-01", "removes": "step",
    }]
    report = matrix.analyze(_docs("rolebinding_ns"), _targets(), [], wildcard, "repo", include_fixed=False, today=today)
    assert any("wildcard" in item for item in report.invalid)
    assert all(row.classification != "named-exception" for row in report.rows)
    expired = [{
        "identity": "user:scoped-user", "target": "deployment/stg-api", "field": "image",
        "check": "fixture", "expires": "2020-01-01", "removes": "step",
    }]
    old = matrix.analyze(_docs("rolebinding_ns"), _targets(), [], expired, "repo", include_fixed=False, today=today)
    assert any("expired" in item for item in old.invalid)
    prefix = [{
        "identity": "user:scoped-user", "target": "deployment/stg-api", "field": "image",
        "check": "fixture", "expires": "2099-01-01", "removes": "step",
    }]
    # exact field image does not match a different field via prefix
    other = matrix.analyze(_docs("rolebinding_ns"), _targets(), [], [{**prefix[0], "field": "ima"}], "repo", include_fixed=False, today=today)
    assert all(row.classification != "named-exception" for row in other.rows)
    component = [{
        "class": "system-component",
        "identity": "user:scoped-user", "target": "deployment/stg-api", "field": "image",
        "check": "fixture", "expires": "2099-01-01", "removes": "step",
        "installed_by": "owner", "why_needed": "controller", "narrowing": "tried a Role, the API is cluster scoped",
    }]
    bad = matrix.analyze(_docs("rolebinding_ns"), _targets(), [], component, "repo", include_fixed=False, today=today)
    assert any("review_every_days" in item for item in bad.invalid)
    component[0]["review_every_days"] = 90
    good = matrix.analyze(_docs("rolebinding_ns"), _targets(), [], component, "repo", include_fixed=False, today=today)
    assert good.invalid == []
    assert _rows(good, "user:scoped-user", "deployment/stg-api")[0].classification == "named-exception"
