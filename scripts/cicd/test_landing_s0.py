"""S0: exercise the real CI shell and keep clone identities in run results."""
import os
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "k8s/cicd/tekton/pipeline-ci-platform.yaml"


def pipeline():
    """The pipeline spec; test-api is its own Task (R5:5.7-1), read in as the taskSpec it was."""
    spec = yaml.safe_load(PIPELINE.read_text())["spec"]
    api = yaml.safe_load((PIPELINE.parent / "task-ci-platform-test-api.yaml").read_text())
    for t in spec["tasks"]:
        if t.get("taskRef", {}).get("name") == api["metadata"]["name"]:
            t["taskSpec"] = api["spec"]
    return spec


def test_actual_clone_results_are_auditable():
    spec = pipeline()
    tasks = {t["name"]: t for t in spec["tasks"]}
    results = {r["name"]: r["value"] for r in spec["results"]}
    for result, task in [("platform-commit", "clone"), ("ui-commit", "clone-ui"),
                         ("infra-commit", "clone-infra")]:
        assert results[result] == "$(tasks." + task + ".results.commit)"
        assert tasks[task]["taskRef"]["name"] == "bifrost-git-clone-gitea"
    assert [r["name"] for r in spec["results"]].count("platform-tree") == 1
    assert results["platform-tree"] == "$(tasks.clone.results.tree)"
    clone = yaml.safe_load((PIPELINE.parent / "task-git-clone-gitea.yaml").read_text())
    assert {"commit", "tree"} <= {r["name"] for r in clone["spec"]["results"]}


def test_t50_receives_a_pinned_baseline_before_api_tests():
    tasks = {t["name"]: t for t in pipeline()["tasks"]}
    legacy = tasks["clone-legacy"]
    assert legacy["taskRef"]["name"] == "bifrost-git-clone-gitea"
    params = {p["name"]: p["value"] for p in legacy["params"]}
    assert params["url"] == "$(params.giteaBase)/bifrost-platform.git"
    assert params["revision"] == "5a8edd550aaa49474a320eb15ed7c9c33f0e1bc5"
    assert params["subdir"] != "bifrost-platform"
    assert legacy["workspaces"] == [{"name": "output", "workspace": "source"}]
    api = tasks["test-api"]
    assert set(api["runAfter"]) == {"clone", "clone-legacy"}
    step = api["taskSpec"]["steps"][0]
    env = {e["name"]: e.get("value") for e in step["env"]}
    assert env["AGENTRT_T50_LEGACY_SRC"] == "$(workspaces.source.path)/" + params["subdir"] + "/api"
    assert env["AGENTRT_TEST_REQUIRED"] == "1"
    credentials = {e['name']: e['valueFrom']['secretKeyRef'] for e in step['env'] if 'valueFrom' in e}
    assert credentials == {
        'GIT_USERNAME': {'name': 'gitea-ci-reader', 'key': 'username'},
        'GIT_PASSWORD': {'name': 'gitea-ci-reader', 'key': 'password'},
    }
    assert "when" not in legacy and "onError" not in legacy


def test_build_cache_is_one_shared_claim_and_keys_on_the_database_version():
    # CI-7: test-api, test-api-store and test-console mount the RWX claim ci-build-cache
    # as a Task volume (no new Pipeline workspace), and go test caches results.
    claim = yaml.safe_load((PIPELINE.parent / "pvc-ci-build-cache.yaml").read_text())
    assert claim["kind"] == "PersistentVolumeClaim" and claim["metadata"]["name"] == "ci-build-cache"
    assert claim["spec"]["accessModes"] == ["ReadWriteMany"] and claim["spec"]["storageClassName"] == "nfs-fast"
    spec = pipeline()
    assert [w["name"] for w in spec["workspaces"]] == ["source"]
    tasks = {t["name"]: t for t in spec["tasks"]}
    for name in ("test-api", "test-console"):
        task = tasks[name]["taskSpec"]
        volumes = {v["name"]: v for v in task["volumes"]}
        assert volumes["build-cache"] == {"name": "build-cache", "persistentVolumeClaim": {"claimName": "ci-build-cache"}}
        step = task["steps"][0]
        assert {"name": "build-cache", "mountPath": "/ci-cache"} in step["volumeMounts"]
        assert "/ci-cache/" in step["script"]
    api = tasks["test-api"]["taskSpec"]
    assert "-count=1" not in "\n".join(l for l in api["steps"][0]["script"].splitlines() if not l.strip().startswith("#"))
    # A result Go cached against one Postgres must not answer for another: the
    # sidecar's version is in the DSN the tests read.
    image = next(s["image"] for s in api["sidecars"] if s["name"] == "postgres")
    version = image.split(":", 1)[1].split("@", 1)[0]
    env = {e["name"]: e.get("value") for e in api["steps"][0]["env"]}
    assert env["AGENTRT_TEST_PG"].split()[-1] == "application_name=ci-pg" + version


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
    scripts = api.parent / "scripts/ci"
    scripts.mkdir(parents=True)
    (scripts / "test_api_scoped.sh").write_text('cd api\ngo test ./...\n')
    subprocess.run(["git", "init", "-q", str(api.parent)], check=True)
    subprocess.run(["git", "-C", str(api.parent), "-c", "user.name=Test", "-c",
                    "user.email=test@example.invalid", "commit", "--allow-empty", "-qm", "fixture"], check=True)
    for name in ("API_SCOPE", "FAILED_TESTS", "API_PACKAGES", "API_STORE_RUN", "API_SCOPE_WHY"):
        env[name + "_RESULT"] = str(tmp_path / name)
    spec = pipeline()
    task = next(t for t in spec["tasks"] if t["name"] == "test-api")
    script = task["taskSpec"]["steps"][0]["script"].replace("$(workspaces.source.path)", str(tmp_path))
    script = script.replace("/ci-cache", str(tmp_path / "ci-cache"))
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


def test_api_scope_params_and_results():
    spec = pipeline()
    task = next(t for t in spec['tasks'] if t['name'] == 'test-api')
    for params in (spec['params'], task['taskSpec']['params']):
        by_name = {p['name']: p for p in params}
        for name in ('base', 'api-scope-request'):
            assert by_name[name]['type'] == 'string'
            assert by_name[name]['default'] == ''
    for name in ('test-api', 'test-api-store'):
        share = next(t for t in spec['tasks'] if t['name'] == name)
        params = {p['name']: p['value'] for p in share['params']}
        for param in ('base', 'api-scope-request'):
            assert params[param] == '$(params.' + param + ')'
    results = {r['name']: r['value'] for r in spec['results']}
    declared = {r['name'] for r in task['taskSpec']['results']}
    for name in ('api-scope', 'failed-tests', 'api-packages', 'api-store-run', 'api-scope-why'):
        assert name in declared
        assert results[name] == '$(tasks.test-api.results.' + name + ')'


def test_api_scope_execution_and_result_budget(tmp_path):
    """Exercise the manifest shell with a selector fixture, no Go or network."""
    root = tmp_path / 'bifrost-platform'
    (root / 'api').mkdir(parents=True)
    scripts = root / 'scripts/ci'
    scripts.mkdir(parents=True)
    (scripts / 'test_api_scoped.sh').write_text('''#!/bin/bash
printf '%s' "${API_SCOPE_REQUEST:-incremental}" > "$API_SCOPE_RESULT"
[ "${API_SCOPE_REQUEST:-}" = full ] || printf incremental > "$API_SCOPE_RESULT"
printf 'packages='
for i in {1..100}; do printf 'github.com/weitingzhao/bifrost-platform/api/internal/pkg%s ' "$i"; done
printf '\\nstore_run='
printf 'TestLongPattern%.0s' {1..100}
printf '\\nwhy=fixture\\nscope=%s\\n' "$(cat "$API_SCOPE_RESULT")"
printf 'failure%.0s' {1..500} > "$FAILED_TESTS_RESULT"
printf 'why=test output must not become a result\\n'
exit "${SELECTOR_STATUS:-0}"
''')
    bins = tmp_path / 'bin'
    bins.mkdir()
    (bins / 'go').write_text('''#!/bin/bash
echo "go $*" >> "$GO_CALLS"
echo "slow=${BIFROST_SLOW_TESTS:-}" >> "$GO_CALLS.env"
if [ "$1" = list ]; then
  if [ "$2" = ./internal/agentrt/store ]; then echo m/internal/agentrt/store; else printf 'm/a\\nm/internal/agentrt/store\\n'; fi
fi
exit 0
''')
    (bins / 'git').write_text('''#!/bin/bash
echo "$*" >> "$GIT_CALLS"
case "$1" in
rev-parse) if [ "$2" = --is-shallow-repository ]; then echo true; else printf 'b%.0s' {1..40}; fi ;;
cat-file) exit "${BASE_MISSING:-0}" ;;
diff) exit "${SELECTOR_CHANGED:-0}" ;;
esac
''')
    for path in bins.iterdir():
        path.chmod(0o755)
    task = next(t for t in pipeline()['tasks'] if t['name'] == 'test-api')
    script = task['taskSpec']['steps'][0]['script'].replace('$(workspaces.source.path)', str(tmp_path))
    script = script.replace('/ci-cache', str(tmp_path / 'ci-cache'))
    env = {**os.environ, 'PATH': str(bins) + ':' + os.environ['PATH'],
           'GIT_CALLS': str(tmp_path / 'git-calls'), 'GO_CALLS': str(tmp_path / 'go-calls'), 'API_PART': 'rest'}
    paths = {}
    for name in ('API_SCOPE', 'FAILED_TESTS', 'API_PACKAGES', 'API_STORE_RUN', 'API_SCOPE_WHY'):
        paths[name] = tmp_path / name
        env[name + '_RESULT'] = str(paths[name])
    cases = [('', '', 'no base (main push)', 'full', 0, 0),
             ('INVALID', '', 'invalid base', 'full', 0, 0),
             ('a' * 40, 'full', 'API_SCOPE_REQUEST=full', 'full', 0, 0),
             ('a' * 40, '', 'selector changed', 'full', 1, 0),
             ('a' * 40, '', 'fixture', 'incremental', 0, 0),
             ('a' * 40, '', 'fixture', 'incremental', 0, 1)]
    for base, request, why, scope, changed, missing in cases:
        (tmp_path / 'go-calls').write_text('')
        (tmp_path / 'go-calls.env').write_text('')
        run = subprocess.run(['bash'], input=script, text=True, capture_output=True,
                             env={**env, 'LANDING_BASE': base, 'API_SCOPE_REQUEST': request,
                                  'SELECTOR_CHANGED': str(changed), 'BASE_MISSING': str(missing),
                                  'SELECTOR_STATUS': '7'})
        assert paths['API_SCOPE'].read_text() == scope
        assert paths['API_SCOPE_WHY'].read_text() == why
        packages = paths['API_PACKAGES'].read_text()
        assert 'github.com/' not in packages
        assert sum(len(p.read_bytes()) for p in paths.values()) <= 4096 - 512
        go_calls = (tmp_path / 'go-calls').read_text()
        # Only the daily full CI (api-scope-request=full) runs the slow tests.
        slow = set((tmp_path / 'go-calls.env').read_text().split())
        assert slow == ({'slow=1'} if request == 'full' else {'slow='}), (request, slow)
        (tmp_path / 'go-calls.env').write_text('')
        if scope == 'full':
            # A full run keeps the split: part rest tests every package but
            # store itself, side by side with part store; no selector.
            assert run.returncode == 0, run.stdout + run.stderr
            assert packages == ''
            assert 'packages=github.com/' not in run.stdout
            # CI-7: no -count=1, so Go's test cache answers for unchanged packages.
            assert 'go test m/a -timeout=' in go_calls and '-count' not in go_calls
            assert 'm/internal/agentrt/store -timeout' not in go_calls
        else:
            assert run.returncode == 7, run.stdout + run.stderr
            assert len(packages.encode()) <= 1200
            assert len(paths['API_STORE_RUN'].read_bytes()) <= 600
            assert paths['API_STORE_RUN'].read_text().endswith('... (cut, see the log)')
            assert paths['FAILED_TESTS'].read_text().endswith('... (cut, see the log)')
            assert ('packages=github.com/' in run.stdout and 'store_run=TestLongPattern' in run.stdout)
            assert packages.endswith('... (cut, see the log)')
    # Part store: the store package alone on a full run; on an incremental one
    # the selector with API_SCOPED_PART=store (its share of the selection).
    (tmp_path / 'go-calls').write_text('')
    run = subprocess.run(['bash'], input=script, text=True, capture_output=True,
                         env={**env, 'API_PART': 'store', 'LANDING_BASE': '', 'API_SCOPE_REQUEST': '',
                              'SELECTOR_CHANGED': '0', 'BASE_MISSING': '0', 'SELECTOR_STATUS': '7'})
    assert run.returncode == 0, run.stdout + run.stderr
    assert 'go test ./internal/agentrt/store -timeout=' in (tmp_path / 'go-calls').read_text()
    assert 'packages=github.com/' not in run.stdout
    (scripts / 'test_api_scoped.sh').write_text('#!/bin/bash\necho "part=${API_SCOPED_PART:-none}"\nprintf incremental > "$API_SCOPE_RESULT"\n')
    for part in ('store', 'rest'):
        run = subprocess.run(['bash'], input=script, text=True, capture_output=True,
                             env={**env, 'API_PART': part, 'LANDING_BASE': 'a' * 40, 'API_SCOPE_REQUEST': '',
                                  'SELECTOR_CHANGED': '0', 'BASE_MISSING': '0', 'SELECTOR_STATUS': '0'})
        assert run.returncode == 0, run.stdout + run.stderr
        assert f'part={part}' in run.stdout
    calls = (tmp_path / 'git-calls').read_text()
    assert 'fetch --unshallow origin' in calls
    assert 'fetch origin ' + 'a' * 40 in calls
    assert '-- scripts/ci/test_api_scoped.sh api/cmd/testscope api/internal/testscope' in calls
