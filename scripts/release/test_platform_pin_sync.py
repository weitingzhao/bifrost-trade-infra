"""TD-335, TD-419 (W-31 3.4 ①): the pin-and-sync Task, run as embedded, against a fake kubectl."""

import ast
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TEKTON = ROOT / "k8s/cicd/tekton"
TASK = TEKTON / "task-argocd-pin-sync-platform.yaml"
STG_PIPELINE = TEKTON / "pipeline-deliver-platform.yaml"
PROD_PIPELINE = TEKTON / "pipeline-deliver-platform-prod.yaml"
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
app = a[a.index("application") + 1] if "application" in a else ""
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
    "mode, says, written",
    [
        ("failed", "this run's sync ended Failed", True),
        ("error", "this run's sync ended Error", True),
        ("never", "did not finish with the pinned images", True),
        # an automated sync that replaced this run's state is not this run's success
        ("other", "did not finish with the pinned images", True),
        ("no-images", "did not finish with the pinned images", True),
        ("wrong-path", "does not deploy k8s/overlays/platform-stg", False),
        ("forbidden", "cannot read or patch the application", False),
    ],
)
def test_refusals(tmp_path, mode, says, written):
    out, calls, _ = execute(tmp_path, mode, wait=2)
    assert out.returncode == 1 and says in out.stdout, out.stdout
    assert out.stdout.splitlines()[-1].startswith("REFUSED: pin and sync of the platform application: ")
    assert ("may be pinned" in out.stdout) == written
    assert ("left as it was" in out.stdout) == (not written)
    assert sum(c[2:3] == ["patch"] for c in calls) == (1 if written else 0)


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


def test_the_log_says_only_fixed_phrases(tmp_path):
    out, _, _ = execute(tmp_path, "forbidden")
    assert "Error from server" not in out.stdout and "applications.argoproj.io" not in out.stdout


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
