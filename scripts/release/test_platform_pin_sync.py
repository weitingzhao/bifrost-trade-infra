"""TD-335, TD-419 (W-31 3.4 ①): the pin-and-sync Task, run as embedded, against a fake kubectl."""

import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TEKTON = ROOT / "k8s/cicd/tekton"
TASK = TEKTON / "task-argocd-pin-sync-platform.yaml"
STG_PIPELINE = TEKTON / "pipeline-deliver-platform.yaml"
PROD_PIPELINE = TEKTON / "pipeline-deliver-platform-prod.yaml"
ADMISSION = ROOT / "k8s/platform-rbac/40-admission.yaml"
DELIVER = "system:serviceaccount:cicd:tekton-deliver"
API = "sha256:" + "1" * 64
CONSOLE = "sha256:" + "2" * 64
RUN = "bifrost-deliver-platform-1792630711"
WHO = "tekton-deliver-platform:" + RUN


def task():
    doc = yaml.safe_load(TASK.read_text())
    assert doc["metadata"] == {"name": "bifrost-argocd-pin-sync-platform", "namespace": "cicd",
                               "labels": {"bifrost.io/purpose": "platform-deliver"}}
    return doc["spec"]


def script():
    (step,) = task()["steps"]
    return step["script"]


FAKE = r'''#!/usr/bin/env python3
import json, os, sys
root = os.environ["FAKE_ROOT"]
mode = os.environ.get("FAKE_MODE", "ok")
a = sys.argv[1:]
with open(os.path.join(root, "calls"), "a") as f:
    f.write(json.dumps(a) + "\n")
state_path = os.path.join(root, "state.json")
st = json.load(open(state_path)) if os.path.exists(state_path) else {"reads": 0, "patched": None, "after": 0}
def save():
    json.dump(st, open(state_path, "w"))
if mode == "forbidden":
    print("Error from server (Forbidden): applications.argoproj.io is forbidden", file=sys.stderr); sys.exit(1)
if mode == "not-found":
    print('Error from server (NotFound): applications.argoproj.io "x" not found', file=sys.stderr); sys.exit(1)
app = a[a.index("application") + 1] if "application" in a else ""
# what the API server answered a refused patch (the first STG run's, 2026-10-22, for "denied")
REFUSED_PATCH = {
    "denied": 'The applications "' + app + '" is invalid: : ValidatingAdmissionPolicy \'bifrost-platform-application\' '
              "with binding 'bifrost-platform-application' denied request: platform may change only the sync operation",
    "webhook": 'Error from server: admission webhook "validate.example.io" denied the request: spec.source secret-value',
    "invalid": 'The Application "' + app + '" is invalid: spec.source.kustomize.images[0]: Invalid value: "secret-value"',
    "patch-forbidden": 'Error from server (Forbidden): applications.argoproj.io "' + app + '" is forbidden: cannot patch',
    "patch-lost": "Unable to connect to the server: EOF",
}
if a[2:4] == ["patch", "application"] and mode in REFUSED_PATCH:
    print(REFUSED_PATCH[mode], file=sys.stderr); sys.exit(1)
if a[2:4] == ["patch", "application"]:
    st["patched"] = json.loads(a[a.index("-p") + 1]); st["after"] = 0; save(); print("patched"); sys.exit()
if a[2:4] != ["get", "application"]:
    print("unexpected call", file=sys.stderr); sys.exit(1)
st["reads"] += 1
doc = {"metadata": {"name": app}, "spec": {"source": {"path": "k8s/overlays/" + app.replace("bifrost-", "")},
       "destination": {"namespace": app}}, "status": {}}
if mode == "wrong-path":
    doc["spec"]["source"]["path"] = "k8s/overlays/prod"
if st["patched"] is None:
    # before the patch: the last sync was someone else's, finished
    doc["status"]["operationState"] = {"phase": "Succeeded", "operation": {"initiatedBy": {"username": "admin"}}}
    if mode == "busy" and st["reads"] == 1:
        doc["operation"] = {"sync": {}}
else:
    st["after"] += 1
    who = st["patched"]["operation"]["initiatedBy"]["username"]
    images = [i.split("=", 1)[1] for i in st["patched"]["spec"]["source"]["kustomize"]["images"]]
    if mode == "keep-tag":
        images = [i.replace("api@", "api:prod@").replace("console@", "console:prod@") for i in images]
    phase = {"failed": "Failed", "error": "Error"}.get(mode, "Succeeded")
    if mode in ("never", "other") or st["after"] == 1:
        doc["operation"] = st["patched"]["operation"]
        doc["status"]["operationState"] = {"phase": "Running", "operation": {"initiatedBy": {"username": who}}}
    else:
        doc["status"]["operationState"] = {"phase": phase, "operation": {"initiatedBy": {"username": who}}}
        doc["status"]["summary"] = {"images": images + ["redis:7-alpine"]}
        if mode == "no-images":
            doc["status"]["summary"] = {"images": ["192.168.10.73:30500/bifrost-platform-api:prod"]}
    if mode == "other" and st["after"] > 1:
        doc.pop("operation", None)
        doc["status"]["operationState"] = {"phase": "Succeeded", "operation": {"initiatedBy": {"automated": True}}}
save()
print(json.dumps(doc))
'''


def execute(tmp_path, mode="ok", app="bifrost-platform-stg", api=API, console=CONSOLE, run=RUN, wait=6):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "kubectl").write_text(FAKE)
    (bin_dir / "kubectl").chmod(0o755)
    (tmp_path / "pin.py").write_text(script())
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "FAKE_ROOT": str(tmp_path),
           "FAKE_MODE": mode, "APPLICATION": app, "API_DIGEST": api, "CONSOLE_DIGEST": console, "DELIVER_RUN": run,
           "PIN_SYNC_WAIT_S": str(wait), "PIN_SYNC_POLL_S": "0.05"}
    out = subprocess.run([sys.executable, str(tmp_path / "pin.py")], env=env, capture_output=True, text=True, timeout=60)
    calls = [json.loads(x) for x in (tmp_path / "calls").read_text().splitlines()] if (tmp_path / "calls").exists() else []
    state = json.loads((tmp_path / "state.json").read_text()) if (tmp_path / "state.json").exists() else {}
    return out, calls, state


@pytest.mark.parametrize("app", ["bifrost-platform-stg", "bifrost-platform-prod"])
@pytest.mark.parametrize("mode", ["ok", "keep-tag"])
def test_pins_syncs_and_waits_for_its_own_sync(tmp_path, app, mode):
    out, calls, state = execute(tmp_path, mode, app=app)
    assert out.returncode == 0, out.stdout
    assert "synced " + app + " with the pinned images" in out.stdout
    patches = [c for c in calls if c[2:3] == ["patch"]]
    assert len(patches) == 1
    assert patches[0][:7] == ["-n", "cicd", "patch", "application", app, "--type", "merge"]
    assert state["patched"] == {
        "spec": {"source": {"kustomize": {"images": [
            "registry.cicd.svc.cluster.local:5000/bifrost-platform-api=192.168.10.73:30500/bifrost-platform-api@" + API,
            "registry.cicd.svc.cluster.local:5000/bifrost-platform-console=192.168.10.73:30500/bifrost-platform-console@" + CONSOLE,
        ]}}},
        "operation": {"initiatedBy": {"username": WHO}, "sync": {"revision": "HEAD"}},
    }


def test_a_running_sync_finishes_first(tmp_path):
    out, calls, _ = execute(tmp_path, "busy")
    assert out.returncode == 0, out.stdout
    # the patch went out only after a read without an operation
    first_patch = next(i for i, c in enumerate(calls) if c[2:3] == ["patch"])
    assert first_patch >= 2


@pytest.mark.parametrize(
    "mode, says, written, patches",
    [
        ("failed", "this run's sync ended Failed", True, 1),
        ("error", "this run's sync ended Error", True, 1),
        ("never", "did not finish with the pinned images", True, 1),
        # an automated sync that replaced this run's state is not this run's success
        ("other", "did not finish with the pinned images", True, 1),
        ("no-images", "did not finish with the pinned images", True, 1),
        ("wrong-path", "does not deploy k8s/overlays/platform-stg", False, 0),
        ("forbidden", "this identity cannot read the application", False, 0),
        ("not-found", "the application was not found", False, 0),
        # the API server refused the patch: nothing was stored, and the log says what refused it
        ("denied", "the admission policy bifrost-platform-application denied the patch of the application", False, 1),
        ("webhook", "the admission webhook validate.example.io denied the patch of the application", False, 1),
        ("invalid", "the API server rejected the patch of the application as invalid", False, 1),
        ("patch-forbidden", "this identity cannot patch the application", False, 1),
        # no answer: the patch may have been stored
        ("patch-lost", "the patch of the application failed", True, 1),
    ],
)
def test_refusals(tmp_path, mode, says, written, patches):
    out, calls, _ = execute(tmp_path, mode, wait=2)
    assert out.returncode == 1 and says in out.stdout, out.stdout
    assert out.stdout.splitlines()[-1].startswith("REFUSED: pin and sync of the platform application: ")
    assert ("may be pinned" in out.stdout) == written
    assert ("left as it was" in out.stdout) == (not written)
    assert sum(c[2:3] == ["patch"] for c in calls) == patches
    assert "a cluster call failed" not in out.stdout


@pytest.mark.parametrize(
    "over",
    [
        {"app": "bifrost-prod"},
        {"app": "bifrost-platform-stg; rm"},
        {"api": "sha256:" + "1" * 63},
        {"console": "latest"},
        {"run": "Bad_Run"},
    ],
)
def test_bad_inputs_refused_before_any_call(tmp_path, over):
    out, calls, _ = execute(tmp_path, **over)
    assert out.returncode == 1 and out.stdout.startswith("REFUSED: ")
    assert calls == []


def test_kubectl_keeps_the_in_cluster_identity(tmp_path):
    out, calls, _ = execute(tmp_path)
    assert out.returncode == 0
    for a in calls:
        assert a[:2] == ["-n", "cicd"], a
        assert a[2:4] in (["get", "application"], ["patch", "application"]), a
        assert not [x for x in a if x.startswith("--") and x != "--type"], a
    tree = ast.parse(script())
    runs = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.unparse(n.func) == "subprocess.run"]
    assert len(runs) == 1
    assert ast.unparse(runs[0].args[0]) == "['kubectl', '-n', NAMESPACE, *args]"


@pytest.mark.parametrize("mode", ["forbidden", "not-found", "denied", "webhook", "invalid", "patch-forbidden", "patch-lost"])
def test_the_log_says_only_fixed_phrases(tmp_path, mode):
    out, _, _ = execute(tmp_path, mode)
    for said in ("Error from server", "applications.argoproj.io", "secret-value", "denied request", "Unable to connect"):
        assert said not in out.stdout, (mode, out.stdout)


def test_task_shape_and_embedding():
    from embed_platform_pin_sync import embedded_script, generated_task

    assert script() == embedded_script()
    assert TASK.read_text() == generated_task(TASK.read_text())
    spec = task()
    assert [p["name"] for p in spec["params"]] == ["application", "apiDigest", "consoleDigest", "deliverRun"]
    assert all("default" not in p for p in spec["params"])
    (step,) = spec["steps"]
    assert {e["name"]: e["value"] for e in step["env"]} == {
        "APPLICATION": "$(params.application)",
        "API_DIGEST": "$(params.apiDigest)",
        "CONSOLE_DIGEST": "$(params.consoleDigest)",
        "DELIVER_RUN": "$(params.deliverRun)",
    }
    assert "onError" not in step


def tasks(path):
    return {t["name"]: t for t in yaml.safe_load(path.read_text())["spec"]["tasks"]}


@pytest.mark.parametrize(
    "path, app, digest_of",
    [
        (STG_PIPELINE, "bifrost-platform-stg", lambda kind: "$(tasks.build-platform-%s.results.digest)" % kind),
        (PROD_PIPELINE, "bifrost-platform-prod", lambda kind: "$(tasks.check-source.results.%s-digest)" % kind),
    ],
)
def test_both_deliveries_pin_before_the_rollout_check(path, app, digest_of):
    t = tasks(path)
    sync, rollout = t["gitops-sync"], t["rollout"]
    # the platform runs the task named gitops-sync as tekton-deliver: the name stays
    assert sync["taskRef"] == {"name": "bifrost-argocd-pin-sync-platform"}
    assert {p["name"]: p["value"] for p in sync["params"]} == {
        "application": app, "apiDigest": digest_of("api"), "consoleDigest": digest_of("console"),
        "deliverRun": "$(context.pipelineRun.name)"}
    assert rollout["runAfter"] == ["gitops-sync"]
    params = {p["name"]: p["value"] for p in rollout["params"]}
    assert params["requireSpecDigest"] == "true"
    assert params["apiDigest"] == digest_of("api") and params["consoleDigest"] == digest_of("console")
    assert not {"when", "onError", "retries"} & sync.keys()


def test_the_prod_delivery_builds_nothing():
    t = tasks(PROD_PIPELINE)
    refs = {x.get("taskRef", {}).get("name", "") for x in t.values()}
    assert not [r for r in refs if "kaniko" in r]
    assert not [n for n in t if n.startswith(("build-", "stage-")) or n == "clone-ui"]
    # the only clone is the platform's, for the schema check's migration files
    assert [n for n, x in t.items() if x.get("taskRef", {}).get("name") == "bifrost-git-clone-gitea"] == ["clone-platform"]
    assert t["agentrt-schema"]["runAfter"] == ["clone-platform"]
    assert t["promote-images"]["runAfter"] == ["agentrt-schema"]
    assert t["gitops-sync"]["runAfter"] == ["promote-images"]


def application_rules():
    (doc,) = [d for d in yaml.safe_load_all(ADMISSION.read_text()) if d and d["kind"] == "ValidatingAdmissionPolicy"
              and d["metadata"]["name"] == "bifrost-platform-application"]
    spec = doc["spec"]
    assert "'" + DELIVER + "'" in spec["matchConditions"][0]["expression"]
    return [" ".join(v["expression"].split()) for v in spec["validations"]]


def test_the_admission_policy_lets_a_delivery_pin_its_application_by_digest(tmp_path):
    """The first STG run's pin (2026-10-22) was denied: the policy let no one change spec.source.kustomize.

    There is no CEL engine here; the exception's parts are read off the policy, and the
    Task's own patch is matched against its image patterns. The Owner's apply script then
    tries the pin against the API server (--dry-run=server, as tekton-deliver)."""
    from platform_pin_sync import APPLICATIONS

    rules = application_rules()
    (general,) = [r for r in rules if "repoURL" in r]
    assert "kustomize" not in general
    (rule,) = [r for r in rules if "kustomize" in r]
    unchanged, exception = rule.split(" || ( request.userInfo.username ", 1)
    assert unchanged.endswith("|| ( has(object.spec.source.kustomize) == has(oldObject.spec.source.kustomize) && "
                              "(!has(object.spec.source.kustomize) || object.spec.source.kustomize == "
                              "oldObject.spec.source.kustomize) )")
    assert exception.endswith(" )") and " || " not in exception  # every part of the exception must hold
    parts = exception[: -len(" )")].split(" && ")
    assert parts[0] == "== '" + DELIVER + "'"
    assert parts[1] == "object.metadata.name in [" + ", ".join("'%s'" % a for a in APPLICATIONS) + "]"
    assert parts[2:6] == [
        "has(object.spec.source.kustomize)",
        "object.spec.source.kustomize.all(k, k == 'images')",
        "has(object.spec.source.kustomize.images)",
        "size(object.spec.source.kustomize.images) == 2",
    ]
    patterns = [re.fullmatch(r"object\.spec\.source\.kustomize\.images\[%d\]\.matches\('([^']*)'\)" % i, part).group(1)
                for i, part in enumerate(parts[6:])]
    assert len(patterns) == 2
    for app in APPLICATIONS:
        (tmp_path / app).mkdir()
        out, _, state = execute(tmp_path / app, app=app)
        assert out.returncode == 0, out.stdout
        kustomize = state["patched"]["spec"]["source"]["kustomize"]
        assert list(kustomize) == ["images"] and len(kustomize["images"]) == 2
        for pattern, image in zip(patterns, kustomize["images"]):
            assert re.search(pattern, image), (pattern, image)
    api = "registry.cicd.svc.cluster.local:5000/bifrost-platform-api=192.168.10.73:30500/bifrost-platform-api"
    for image in (
        api + ":stg",
        api + ":stg@" + API,
        api + "@sha256:" + "1" * 63,
        api + "@sha256:" + "A" * 64,
        api + "@" + API + "x",
        "x" + api + "@" + API,
        api.replace("=192.168.10.73:30500/", "=evil.example/") + "@" + API,
        api.replace("bifrost-platform-api=", "bifrost-platform-console=") + "@" + API,
        api.replace("192.168.10.73", "192x168.10.73") + "@" + API,
    ):
        assert not re.search(patterns[0], image), image
    assert re.search(patterns[0], api + "@" + API)
    assert re.search(patterns[1], api.replace("-api", "-console") + "@" + CONSOLE)
    assert not re.search(patterns[1], api + "@" + API)
