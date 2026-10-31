"""W-31 B5 (DESIGN-B5-v3 §4.2): every bifrost-ci-platform run names the repository P was
cloned from in spec.params. The platform's release reader treats a run without it as
Unknown(ci_identity) and never falls back to the Pipeline default, so the Pipeline must
declare it, clone P from it, and the webhook template must pass it explicitly. Admission
allows the platform only this one value."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "k8s/cicd/tekton/pipeline-ci-platform.yaml"
TRIGGER = ROOT / "k8s/cicd/tekton/trigger-trade-ci.yaml"
ADMISSION = ROOT / "k8s/platform-rbac/40-admission.yaml"
URL = "http://gitea.cicd.svc.cluster.local:3000/bifrost/bifrost-platform.git"


def _yaml_docs(path: Path) -> list[dict]:
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def test_pipeline_declares_repo_url_and_clones_p_from_it() -> None:
    (doc,) = _yaml_docs(PIPELINE)
    params = [p for p in doc["spec"]["params"] if p["name"] == "repo-url"]
    assert params == [{"name": "repo-url", "type": "string", "default": URL}]
    (clone,) = [t for t in doc["spec"]["tasks"] if t["name"] == "clone"]
    urls = [p["value"] for p in clone["params"] if p["name"] == "url"]
    assert urls == ["$(params.repo-url)"]


def test_trigger_template_passes_the_literal_repo_url() -> None:
    (template,) = [d for d in _yaml_docs(TRIGGER)
                   if d["kind"] == "TriggerTemplate" and d["metadata"]["name"] == "bifrost-ci-platform-template"]
    # A literal, not $(tt.params.…): nothing in a webhook body can choose it.
    assert "repo-url" not in [p["name"] for p in template["spec"]["params"]]
    (run,) = template["spec"]["resourcetemplates"]
    assert run["spec"]["pipelineRef"] == {"name": "bifrost-ci-platform"}
    values = [p["value"] for p in run["spec"]["params"] if p["name"] == "repo-url"]
    assert values == [URL]


def test_admission_allows_only_the_platform_repo_url() -> None:
    (policy,) = [d for d in _yaml_docs(ADMISSION)
                 if d["kind"] == "ValidatingAdmissionPolicy" and d["metadata"]["name"] == "bifrost-platform-pipelinerun"]
    rules = [v["expression"] for v in policy["spec"]["validations"] if "'repo-url'" in v["expression"]]
    assert len(rules) == 1
    assert f"p.name != 'repo-url' || p.value == '{URL}'" in " ".join(rules[0].split())
