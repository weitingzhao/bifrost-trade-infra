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
    got = {row.target for row in report.rows}
    assert got == ids
    assert {row.verbs for row in report.rows} == {WRITE_VERBS}


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
    assert any("expiry" in item for item in report.invalid)
    assert all(row.classification != "named-exception" for row in report.rows)


def test_complete_exception_is_named() -> None:
    exceptions = [
        {
            "identity": "user:scoped-user",
            "target": "deployment/stg-api",
            "field": "image",
            "check": "fixture-check",
            "expiry": "2026-12-31",
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
    assert parallel.rows == []


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
    assert source.classification == "refused"
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
