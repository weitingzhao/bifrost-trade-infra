"""Execute the actual inline task with fake kubectl and mirror answers."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml
from ci_gate import classify

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml"
SHA = "a" * 40
OTHER = "b" * 40


def tasks():
    path = Path(os.environ.get("GATE_PIPELINE", PIPELINE))
    return {t["name"]: t for t in yaml.safe_load(path.read_text())["spec"]["tasks"]}


def script():
    return tasks()["check-source"]["taskSpec"]["steps"][0]["script"]


def run(pipeline, sha=SHA, ok="True", name="ci", timestamp="2026-10-12T10:00:00Z"):
    return {
        "metadata": {
            "name": name,
            "creationTimestamp": timestamp,
            "labels": {
                "tekton.dev/pipeline": pipeline,
                "bifrost.io/repo": "bifrost-platform",
            },
        },
        "spec": {
            "pipelineRef": {"name": pipeline},
            "params": [{"name": "revision", "value": sha}],
        },
        "status": {"conditions": [{"type": "Succeeded", "status": ok}]},
    }


def answers():
    stg = run("bifrost-deliver-platform", name="stg")
    stg["status"]["childReferences"] = [
        {"name": "clone", "kind": "TaskRun", "pipelineTaskName": "clone-platform"}
    ]
    task = run("unused", name="clone")
    task["metadata"]["labels"]["tekton.dev/pipelineRun"] = "stg"
    task["status"]["results"] = [{"name": "commit", "value": SHA}]
    return {"items": [run("bifrost-ci-platform"), stg]}, task


def execute(tmp_path, doc=None, task=None, mode="", git_mode="", source=None):
    default_doc, default_task = answers()
    (tmp_path / "runs.json").write_text(json.dumps(default_doc if doc is None else doc))
    (tmp_path / "task.json").write_text(
        json.dumps(default_task if task is None else task)
    )
    fake = """#!{python}
import os,sys,time
from pathlib import Path
root=Path(os.environ['FAKE_ROOT'])
a=sys.argv[1:]
with (root/'calls').open('a') as f: f.write(Path(sys.argv[0]).name+' '+repr(a)+'\\n')
if Path(sys.argv[0]).name=='git':
 if 'ls-remote' in a:
  mode=os.environ.get('GIT_MODE','')
  if mode=='empty': sys.exit(0)
  print('a'*40+'\\trefs/heads/main')
  if mode=='ambiguous': print('b'*40+'\\trefs/tags/main')
 if 'rev-parse' in a: print('a'*40)
else:
 mode=os.environ.get('MODE','')
 if mode=='forbidden' or (mode=='task-forbidden' and 'taskrun' in a):
  print('Error from server (Forbidden)',file=sys.stderr); sys.exit(1)
 if mode=='failed': sys.exit(1)
 if mode=='timeout': time.sleep(5)
 if mode=='empty': sys.exit(0)
 if mode=='duplicate': print('{{"items":[],"items":[]}}'); sys.exit(0)
 if mode=='malformed': print('{{'); sys.exit(0)
 print((root/('task.json' if 'taskrun' in a else 'runs.json')).read_text())
""".format(python=sys.executable)
    for name in ("git", "kubectl"):
        p = tmp_path / name
        p.write_text(fake)
        p.chmod(0o755)
    p = tmp_path / "gate.py"
    p.write_text(script() if source is None else source)
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "FAKE_ROOT": str(tmp_path),
        "MODE": mode,
        "GIT_MODE": git_mode,
        "REVISION": "main",
        "UI_REVISION": "main",
        "GITEA_BASE": "http://mirror/bifrost",
        "COMMIT_PATH": str(tmp_path / "commit"),
        "UI_COMMIT_PATH": str(tmp_path / "ui-commit"),
    }
    return subprocess.run(
        [sys.executable, str(p)], env=env, text=True, capture_output=True, timeout=10
    )


def refuse(result, condition=""):
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr == ""
    assert len(result.stdout.splitlines()) == 1
    assert result.stdout.startswith("REFUSED: " + condition)


def test_gate_order():
    t = tasks()
    assert t["check-source"]["runAfter"] == ["mirror-sync"]
    assert t["clone-platform"]["runAfter"] == ["check-source"]
    assert t["clone-ui"]["runAfter"] == ["check-source"]


def test_checked_sha_is_built():
    for name, result in [("clone-platform", "commit"), ("clone-ui", "ui-commit")]:
        params = {p["name"]: p["value"] for p in tasks()[name]["params"]}
        assert params["revision"] == "$(tasks.check-source.results." + result + ")"


def test_shared_ci_definition():
    helper = (
        (ROOT / "scripts/release/ci_gate.py")
        .read_text()
        .split("\ndef gate(")[0]
        .replace("from __future__ import annotations\n", "")
    )
    gate = (
        (ROOT / "scripts/release/platform_prod_gate.py")
        .read_text()
        .replace("from ci_gate import classify, _pipeline_name, _succeeded", helper)
    )
    assert script() == "#!/usr/bin/env python3\n" + gate
    assert "bifrost-ci-platform" in (ROOT / "scripts/release/release.sh").read_text()


def test_health_unchanged():
    old = subprocess.check_output(
        ["git", "show", "HEAD:k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml"],
        cwd=ROOT,
        text=True,
    )
    old_task = next(
        t for t in yaml.safe_load(old)["spec"]["tasks"] if t["name"] == "preflight-stg"
    )
    assert tasks()["preflight-stg"] == old_task


def test_read_only_same_image():
    rollout = list(
        yaml.safe_load_all(
            (ROOT / "k8s/cicd/tekton/task-deliver-platform.yaml").read_text()
        )
    )[0]
    assert (
        tasks()["check-source"]["taskSpec"]["steps"][0]["image"]
        == rollout["spec"]["steps"][0]["image"]
    )
    assert "apk add" not in script()
    assert '["get", "pipelineruns"]' in script()
    assert '["get", "taskrun", children[0]["name"]]' in script()
    assert '"patch"' not in script() and '"apply"' not in script()


def test_success(tmp_path):
    result = execute(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "commit").read_text() == SHA
    assert (tmp_path / "ui-commit").read_text() == SHA


@pytest.mark.parametrize(
    "case", ["missing", "failed", "wrong-sha", "wrong-repo", "wrong-pipeline"]
)
def test_ci_refuses(tmp_path, case):
    doc, task = answers()
    ci = doc["items"][0]
    if case == "missing":
        doc["items"].pop(0)
    if case == "failed":
        ci["status"]["conditions"][0]["status"] = "False"
    if case == "wrong-sha":
        ci["spec"]["params"][0]["value"] = OTHER
    if case == "wrong-repo":
        ci["metadata"]["labels"]["bifrost.io/repo"] = "bifrost-ui"
    if case == "wrong-pipeline":
        ci["metadata"]["labels"]["tekton.dev/pipeline"] = "bifrost-smoke"
    assert classify(doc["items"], "bifrost-platform", SHA) != "succeeded"
    refuse(execute(tmp_path, doc, task), "CI")
    assert not (tmp_path / "commit").exists()


def test_two_ci_one_succeeded(tmp_path):
    doc, task = answers()
    doc["items"].insert(0, run("bifrost-ci-platform", ok="False", name="failed"))
    assert execute(tmp_path, doc, task).returncode == 0


@pytest.mark.parametrize(
    "case",
    [
        "wrong-sha",
        "missing",
        "older-match",
        "tie",
        "two-children",
        "two-results",
        "task-owner",
        "task-failed",
    ],
)
def test_stg_refuses(tmp_path, case):
    doc, task = answers()
    if case == "missing":
        doc["items"].pop()
    if case in ("wrong-sha", "older-match"):
        task["status"]["results"][0]["value"] = OTHER
    if case in ("older-match", "tie"):
        earlier = copy.deepcopy(doc["items"][1])
        earlier["metadata"]["name"] = "earlier"
        if case == "older-match":
            earlier["metadata"]["creationTimestamp"] = "2026-10-11T10:00:00Z"
        doc["items"].append(earlier)
    if case == "two-children":
        doc["items"][1]["status"]["childReferences"] *= 2
    if case == "two-results":
        task["status"]["results"] *= 2
    if case == "task-owner":
        task["metadata"]["labels"]["tekton.dev/pipelineRun"] = "other"
    if case == "task-failed":
        task["status"]["conditions"][0]["status"] = "False"
    refuse(execute(tmp_path, doc, task), "STG")


@pytest.mark.parametrize(
    "mode",
    [
        "forbidden",
        "task-forbidden",
        "failed",
        "empty",
        "malformed",
        "duplicate",
        "timeout",
    ],
)
def test_query_fail_closed(tmp_path, mode):
    result = execute(
        tmp_path, mode=mode, source=script().replace("BUDGET = 20", "BUDGET = 1")
    )
    refuse(result)
    if "forbidden" in mode:
        assert "identity cannot read" in result.stdout
    assert not (tmp_path / "commit").exists()
    calls = (tmp_path / "calls").read_text().splitlines()
    assert sum("kubectl" in c for c in calls) == (2 if mode == "task-forbidden" else 1)


@pytest.mark.parametrize(
    "case", ["continue", "params", "condition", "bad-date", "not-list"]
)
def test_parse_fail_closed(tmp_path, case):
    doc, task = answers()
    if case == "continue":
        doc["metadata"] = {"continue": "more"}
    if case == "params":
        doc["items"][0]["spec"]["params"] *= 2
    if case == "condition":
        doc["items"][0]["status"]["conditions"] *= 2
    if case == "bad-date":
        doc["items"][1]["metadata"]["creationTimestamp"] = "bad"
    if case == "not-list":
        doc = {"items": {}}
    refuse(execute(tmp_path, doc, task))


@pytest.mark.parametrize("git_mode", ["empty", "ambiguous"])
def test_mirror_resolution_refuses(tmp_path, git_mode):
    refuse(execute(tmp_path, git_mode=git_mode), "CI/STG")


def test_real_mirror_resolution(tmp_path):
    namespace = {"__name__": "gate_test"}
    exec(script(), namespace)
    mirror = tmp_path / "mirror"
    subprocess.run(
        ["git", "init", "-q", "--initial-branch=test", str(mirror)], check=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(mirror),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "test",
        ],
        check=True,
    )
    sha = subprocess.check_output(
        ["git", "-C", str(mirror), "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.run(["git", "-C", str(mirror), "branch", "main"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(mirror),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "tag",
            "-a",
            "v1",
            "-m",
            "tag",
        ],
        check=True,
    )
    assert namespace["resolve"](str(mirror), "main", str(tmp_path / "branch")) == sha
    assert namespace["resolve"](str(mirror), "v1", str(tmp_path / "tag")) == sha
    assert namespace["resolve"](str(mirror), sha, str(tmp_path / "sha")) == sha
    subprocess.run(["git", "-C", str(mirror), "tag", "main"], check=True)
    with pytest.raises(ValueError, match="ambiguous"):
        namespace["resolve"](str(mirror), "main", str(tmp_path / "ambiguous"))


def test_latest_stg_selects_newest():
    namespace = {"__name__": "gate_test"}
    exec(script(), namespace)
    older = run(
        "bifrost-deliver-platform", name="older", timestamp="2026-10-11T10:00:00Z"
    )
    newest = run("bifrost-deliver-platform", name="newest")
    pending = run(
        "bifrost-deliver-platform",
        ok="Unknown",
        name="pending",
        timestamp="2026-10-13T10:00:00Z",
    )
    selected = namespace["latest_stg"]([older, newest, pending])
    assert selected["metadata"]["name"] == "newest"


def test_default_identity_refuses(tmp_path):
    result = execute(tmp_path, mode="forbidden")
    refuse(result, "CI")
    assert (
        result.stdout
        == f"REFUSED: CI cannot be shown for {SHA}: identity cannot read PipelineRuns/TaskRuns in cicd\n"
    )
    assert not (tmp_path / "commit").exists()


def test_unrelated_array_param_is_valid(tmp_path):
    doc, task = answers()
    unrelated = run("bifrost-smoke")
    unrelated["spec"]["params"] = [{"name": "targets", "value": ["a", "b"]}]
    doc["items"].append(unrelated)
    assert execute(tmp_path, doc, task).returncode == 0


def test_clone_credentials_reused():
    clone = yaml.safe_load(
        (ROOT / "k8s/cicd/tekton/task-git-clone-gitea.yaml").read_text()
    )
    original = clone["spec"]["steps"][0]["env"]
    actual = tasks()["check-source"]["taskSpec"]["steps"][0]["env"]
    for name in ("GIT_USERNAME", "GIT_PASSWORD"):
        assert next(e for e in actual if e["name"] == name) == next(
            e for e in original if e["name"] == name
        )


def test_git_auth_stays_out_of_argv(monkeypatch):
    from types import SimpleNamespace

    namespace = {"__name__": "gate_test"}
    exec(script(), namespace)
    captured = {}

    def fake_run(args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return SimpleNamespace(stdout="ok")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("GIT_USERNAME", "test-user")
    monkeypatch.setenv("GIT_PASSWORD", "test-password")
    namespace["command"](["git", "ls-remote", "http://mirror/repo"])
    assert "test-password" not in repr(captured["args"])
    env = captured["kwargs"]["env"]
    assert env["GIT_CONFIG_KEY_0"] == "http.extraHeader"
    assert env["GIT_CONFIG_VALUE_0"].startswith("Authorization: Basic ")
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert captured["kwargs"]["timeout"] == 20
