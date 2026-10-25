"""S0: exercise the real CI shell and keep clone identities in run results."""
import os
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "k8s/cicd/tekton/pipeline-ci-platform.yaml"


def pipeline():
    return yaml.safe_load(PIPELINE.read_text())["spec"]


def test_actual_clone_results_are_auditable():
    spec = pipeline()
    tasks = {t["name"]: t for t in spec["tasks"]}
    results = {r["name"]: r["value"] for r in spec["results"]}
    for result, task in [("platform-commit", "clone"), ("ui-commit", "clone-ui"),
                         ("infra-commit", "clone-infra")]:
        assert results[result] == "$(tasks." + task + ".results.commit)"
        assert tasks[task]["taskRef"]["name"] == "bifrost-git-clone-gitea"
    clone = yaml.safe_load((PIPELINE.parent / "task-git-clone-gitea.yaml").read_text())
    assert any(r["name"] == "commit" for r in clone["spec"]["results"])


def test_vet_only_defect_stops_the_actual_ci_script(tmp_path):
    """Build and ordinary go test pass; full vet's lostcancel must stop CI.

    go test's default vet subset does not run lostcancel. No module download,
    database, container or network is needed for this positive control.
    """
    api = tmp_path / "bifrost-platform/api"
    api.mkdir(parents=True)
    (api / "go.mod").write_text("module example.invalid/landing-vet\n\ngo 1.25.0\n")
    source = api / "lost.go"
    source.write_text('package probe\nimport "context"\n'
                      'func Lost() { ctx, _ := context.WithCancel(context.Background()); _ = ctx }\n')
    env = {**os.environ, "GOPROXY": "off", "GOSUMDB": "off", "GOTOOLCHAIN": "local",
           "GOCACHE": str(tmp_path / "gocache"), "GOMODCACHE": str(tmp_path / "gomod")}
    for args in [("build", "./..."), ("test", "./...")]:
        r = subprocess.run(["go", *args], cwd=api, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    spec = pipeline()
    task = next(t for t in spec["tasks"] if t["name"] == "test-api")
    script = task["taskSpec"]["steps"][0]["script"].replace("$(workspaces.source.path)", str(tmp_path))
    r = subprocess.run(["bash"], input=script, cwd=api, env=env, capture_output=True, text=True)
    assert r.returncode != 0
    assert "cancel function" in r.stderr
    assert "==> go test" not in r.stdout
    # The same script succeeds once the defect is fixed.
    source.write_text(source.read_text().replace("ctx, _ :=", "ctx, cancel :=").replace("_ = ctx", "defer cancel(); _ = ctx"))
    r = subprocess.run(["bash"], input=script, cwd=api, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_no_admin_or_legacy_credential_in_executable_tekton():
    for path in (ROOT / "k8s/cicd/tekton").rglob("*.yaml"):
        docs = list(yaml.safe_load_all(path.read_text()))
        # Ignore comments but include inline tasks and every nested spec field.
        text = yaml.safe_dump(docs)
        assert "gitea-bootstrap" not in text, path
        assert "gitea-git-credentials" not in text, path


def test_applier_cannot_read_the_retired_clone_credential():
    docs = list(yaml.safe_load_all((ROOT / "k8s/platform-rbac/30-applier.yaml").read_text()))
    role = next(d for d in docs if d["metadata"]["name"] == "bifrost-applier-read")
    rules = [r for r in role["rules"] if "secrets" in r["resources"]]
    assert rules == [{"apiGroups": [""], "resources": ["secrets"],
                      "resourceNames": ["gitea-ci-reader"], "verbs": ["get"]}]


def test_ci_default_has_no_credential_or_pod_creation_grants():
    docs = [d for p in (ROOT / "k8s").rglob("*.yaml")
            for d in yaml.safe_load_all(p.read_text()) if isinstance(d, dict)]
    roles = {(d["kind"], d["metadata"].get("namespace", ""), d["metadata"]["name"]): d
             for d in docs if d.get("kind") in ("Role", "ClusterRole")}
    for binding in docs:
        if binding.get("kind") not in ("RoleBinding", "ClusterRoleBinding"):
            continue
        ns = binding["metadata"].get("namespace", "")
        def matches(subject):
            kind, name = subject["kind"], subject["name"]
            return ((kind == "ServiceAccount" and name == "default" and subject.get("namespace", ns) == "cicd") or
                    (kind == "User" and name == "system:serviceaccount:cicd:default") or
                    (kind == "Group" and name in ("system:authenticated", "system:serviceaccounts", "system:serviceaccounts:cicd")))
        if not any(matches(s) for s in binding.get("subjects", [])):
            continue
        ref = binding["roleRef"]
        role = roles.get((ref["kind"], ns if ref["kind"] == "Role" else "", ref["name"]))
        assert role is not None, ("unresolved CI role", ref)
        for rule in role.get("rules", []):
            resources, verbs = set(rule.get("resources", [])), set(rule["verbs"])
            assert not (resources & {"secrets", "*"} and verbs & {"get", "list", "watch", "*"}), binding
            assert not (resources & {"pods", "deployments", "jobs", "pipelineruns", "taskruns", "roles", "rolebindings", "*"}
                        and verbs & {"create", "update", "patch", "*"}), binding
