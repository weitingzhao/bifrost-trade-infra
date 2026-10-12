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
OTHER = "a" * 12 + "b" * 28


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
        "status": {
            "conditions": [{"type": "Succeeded", "status": ok}],
            "completionTime": timestamp,
        },
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


def execute(
    tmp_path,
    doc=None,
    task=None,
    mode="",
    git_mode="",
    source=None,
    revision="main",
    list_docs=None,
):
    default_doc, default_task = answers()
    (tmp_path / "runs.json").write_text(json.dumps(default_doc if doc is None else doc))
    (tmp_path / "task.json").write_text(
        json.dumps(default_task if task is None else task)
    )
    (tmp_path / "list-docs.json").write_text(json.dumps(list_docs or {}))
    fake = """#!{python}
import os,sys,time,json
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
 if mode=='timeout' and 'taskrun' in a: time.sleep(30)
 if mode=='empty': sys.exit(0)
 if mode=='duplicate': print('{{"items":[],"items":[]}}'); sys.exit(0)
 if mode=='malformed': print('{{'); sys.exit(0)
 if 'taskrun' in a: print((root/'task.json').read_text())
 else:
  selector=a[a.index('-l')+1].split('=',1)[1]
  docs=json.loads((root/'list-docs.json').read_text())
  doc=docs.get(selector,json.loads((root/'runs.json').read_text()))
  if selector not in docs and isinstance(doc.get('items'),list):
   doc['items']=[r for r in doc['items'] if r.get('metadata',{{}}).get('labels',{{}}).get('tekton.dev/pipeline')==selector]
  print(json.dumps(doc))
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
        "REVISION": revision,
        "UI_REVISION": "main",
        "GITEA_BASE": "http://mirror/bifrost",
        "COMMIT_PATH": str(tmp_path / "commit"),
        "UI_COMMIT_PATH": str(tmp_path / "ui-commit"),
    }
    return subprocess.run(
        [sys.executable, str(p)], env=env, text=True, capture_output=True, timeout=45
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
    from embed_platform_prod_gate import embedded_script, generated_pipeline

    assert script() == embedded_script()
    assert PIPELINE.read_text() == generated_pipeline(PIPELINE.read_text())
    assert "bifrost-ci-platform" in (ROOT / "scripts/release/release.sh").read_text()


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
    assert '["get", "pipelineruns", "-l"' in script()
    assert '["get", "taskrun", children[0]["name"]]' in script()
    assert '"patch"' not in script() and '"apply"' not in script()


def test_success(tmp_path):
    result = execute(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "commit").read_text() == SHA
    assert (tmp_path / "ui-commit").read_text() == SHA


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "failed",
        "running",
        "wrong-sha",
        "wrong-repo",
        "wrong-pipeline",
        "python-pipeline",
    ],
)
def test_ci_refuses(tmp_path, case):
    doc, task = answers()
    ci = doc["items"][0]
    if case == "missing":
        doc["items"].pop(0)
    if case == "failed":
        ci["status"]["conditions"][0]["status"] = "False"
    if case == "running":
        ci["status"]["conditions"][0]["status"] = "Unknown"
    if case == "python-pipeline":
        ci["metadata"]["labels"]["tekton.dev/pipeline"] = "bifrost-ci-python"
        ci["spec"]["pipelineRef"]["name"] = "bifrost-ci-python"
        ci["spec"]["params"].append({"name": "repo", "value": "bifrost-platform"})
    if case == "wrong-sha":
        ci["spec"]["params"][0]["value"] = OTHER
    if case == "wrong-repo":
        ci["metadata"]["labels"]["bifrost.io/repo"] = "bifrost-ui"
    if case == "wrong-pipeline":
        ci["metadata"]["labels"]["tekton.dev/pipeline"] = "bifrost-smoke"
    if case != "python-pipeline":
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
        "no-result",
        "task-name",
        "child-kind",
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
    if case == "no-result":
        task["status"]["results"] = []
    if case == "task-name":
        task["metadata"]["name"] = "another"
    if case == "child-kind":
        doc["items"][1]["status"]["childReferences"][0]["kind"] = "Pod"
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
    result = execute(tmp_path, mode=mode)
    refuse(result)
    if "forbidden" in mode:
        assert "identity cannot read" in result.stdout
    assert not (tmp_path / "commit").exists()
    calls = (tmp_path / "calls").read_text().splitlines()
    assert sum("kubectl" in c for c in calls) == (
        3 if mode in ("task-forbidden", "timeout") else 1
    )


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
    subprocess.run(["git", "-C", str(mirror), "branch", "wip/main"], check=True)
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
    selected = namespace["latest_stg"]([older, newest])
    assert selected["metadata"]["name"] == "newest"


def test_default_identity_refuses(tmp_path):
    result = execute(tmp_path, mode="forbidden")
    refuse(result, "CI")
    assert (
        result.stdout
        == f"REFUSED: CI cannot be shown for {SHA}: identity cannot read PipelineRuns/TaskRuns in cicd\n"
    )
    assert not (tmp_path / "commit").exists()


def test_unrelated_malformed_run_is_ignored(tmp_path):
    doc, task = answers()
    unrelated = {
        "metadata": {"labels": {"tekton.dev/pipeline": "bifrost-smoke"}},
        "spec": "malformed",
    }
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


@pytest.mark.parametrize(
    "case",
    [
        "newest-failed",
        "newest-running",
        "no-condition",
        "older-later",
        "other-running",
        "equal-completion",
        "bad-created",
        "bad-completed",
        "chosen-missing-completed",
    ],
)
def test_stg_order_refuses(tmp_path, case):
    doc, task = answers()
    chosen = doc["items"][1]
    other = copy.deepcopy(chosen)
    other["metadata"].update(name="older", creationTimestamp="2026-10-11T10:00:00Z")
    other["status"]["completionTime"] = "2026-10-11T11:00:00Z"
    doc["items"].append(other)
    if case == "newest-failed":
        chosen["status"]["conditions"][0]["status"] = "False"
    if case == "newest-running":
        chosen["status"]["conditions"][0]["status"] = "Unknown"
    if case == "no-condition":
        chosen["status"]["conditions"] = []
    if case == "older-later":
        other["status"]["completionTime"] = "2026-10-13T10:00:00Z"
    if case == "other-running":
        other["status"].pop("completionTime")
    if case == "equal-completion":
        other["status"]["completionTime"] = chosen["status"]["completionTime"]
    if case == "bad-created":
        other["metadata"]["creationTimestamp"] = "bad"
    if case == "bad-completed":
        other["status"]["completionTime"] = "bad"
    if case == "chosen-missing-completed":
        chosen["status"].pop("completionTime")
    result = execute(tmp_path, doc, task)
    refuse(result, "STG")
    if case != "bad-created":
        assert (
            "stg"
            if case.startswith("newest")
            or case in ("no-condition", "chosen-missing-completed")
            else "older"
        ) in result.stdout


def test_prod_run_is_not_stg(tmp_path):
    doc, task = answers()
    prod = run(
        "bifrost-deliver-platform-prod", name="prod", timestamp="2026-10-13T10:00:00Z"
    )
    namespace = {"__name__": "gate_test"}
    exec(script(), namespace)
    assert namespace["latest_stg"]([doc["items"][1], prod])["metadata"]["name"] == "stg"
    doc["items"] = [doc["items"][0], prod]
    refuse(execute(tmp_path, doc, task), "STG")


def test_full_sha_mirror_mismatch(tmp_path):
    refuse(execute(tmp_path, revision=OTHER), "CI/STG")


@pytest.mark.parametrize(
    "pipeline", ["bifrost-ci-platform", "bifrost-deliver-platform"]
)
@pytest.mark.parametrize("case", ["continue", "not-list", "wrong-pipeline"])
def test_selected_list_refuses(tmp_path, pipeline, case):
    bad = {"items": []}
    if case == "continue":
        bad["metadata"] = {"continue": "more"}
    if case == "not-list":
        bad["items"] = {}
    if case == "wrong-pipeline":
        bad["items"] = [run("bifrost-deliver-platform-prod")]
    refuse(execute(tmp_path, list_docs={pipeline: bad}))


def test_only_two_pipeline_lists(tmp_path):
    assert execute(tmp_path).returncode == 0
    calls = (tmp_path / "calls").read_text().splitlines()
    lists = [c for c in calls if "pipelineruns" in c]
    assert len(lists) == 2
    for pipeline in ("bifrost-ci-platform", "bifrost-deliver-platform"):
        assert sum("tekton.dev/pipeline=" + pipeline + "'" in c for c in lists) == 1


def test_task_params_declared_and_passed():
    import re

    task = tasks()["check-source"]
    used = set(re.findall(r"\$\(params\.([^)]+)\)", json.dumps(task["taskSpec"])))
    assert used == {"revision", "uiRevision", "giteaBase"}
    assert used <= {p["name"] for p in task["taskSpec"]["params"]}
    assert {p["name"]: p["value"] for p in task["params"]} == {
        name: "$(params." + name + ")" for name in used
    }


def test_trial_only_source_task():
    from platform_prod_gate_trial import trial_run

    trial = trial_run(SHA, OTHER)
    assert trial["metadata"] == {
        "generateName": "check-source-trial-",
        "namespace": "cicd",
        "labels": {"bifrost.io/purpose": "check-source-trial"},
    }
    spec = trial["spec"]
    assert len(spec["pipelineSpec"]["tasks"]) == 1
    task = spec["pipelineSpec"]["tasks"][0]
    assert task["name"] == "check-source"
    assert task["taskSpec"] == tasks()["check-source"]["taskSpec"]
    assert spec["taskRunSpecs"] == [
        {"pipelineTaskName": "check-source", "serviceAccountName": "tekton-deliver"}
    ]
    assert {p["name"]: p["value"] for p in spec["params"]}["revision"] == SHA
    assert {p["name"]: p["value"] for p in spec["params"]}["uiRevision"] == OTHER


def test_trial_cli_prints_only(monkeypatch, capsys):
    import platform_prod_gate_trial as trial

    monkeypatch.setattr(sys, "argv", ["trial", SHA])
    trial.main()
    doc = yaml.safe_load(capsys.readouterr().out)
    assert [t["name"] for t in doc["spec"]["pipelineSpec"]["tasks"]] == ["check-source"]


@pytest.mark.parametrize(
    "case", ["with-gate", "without-gate", "malformed", "unreadable"]
)
def test_pinned_live_pipeline(monkeypatch, capsys, case):
    import release_tool as tool

    stg = run("bifrost-deliver-platform", name="stg")
    stg["spec"]["taskRunSpecs"] = (
        [
            {"pipelineTaskName": "rollout", "serviceAccountName": "tekton-deliver"},
            {"pipelineTaskName": "check-source", "serviceAccountName": "wrong"},
        ]
        if case == "with-gate"
        else [{"pipelineTaskName": "rollout", "serviceAccountName": "tekton-deliver"}]
    )
    original = copy.deepcopy(stg)
    calls = []

    def get(*args):
        calls.append(args)
        if case == "unreadable":
            tool.die("kubectl read failed\nserver detail", 2)
        return {
            "spec": {
                "tasks": {}
                if case == "malformed"
                else (
                    [{"name": "check-source"}]
                    if case == "with-gate"
                    else [{"name": "rollout"}]
                )
            }
        }

    monkeypatch.setattr(tool, "kget", get)
    commits = {"clone-platform": SHA, "clone-ui": OTHER}
    if case in ("malformed", "unreadable"):
        with pytest.raises(SystemExit) as exc:
            tool.platform_pinned_run(stg, commits)
        assert exc.value.code == 1
        output = capsys.readouterr()
        assert len(output.err.splitlines()) == 1
        assert output.err.startswith("REFUSED:")
        assert output.out == ""
    else:
        result = tool.platform_pinned_run(stg, commits)
        overrides = result["spec"]["taskRunSpecs"]
        assert overrides[0] == original["spec"]["taskRunSpecs"][0]
        assert [t for t in overrides if t["pipelineTaskName"] == "check-source"] == (
            [
                {
                    "pipelineTaskName": "check-source",
                    "serviceAccountName": "tekton-deliver",
                }
            ]
            if case == "with-gate"
            else []
        )
        assert stg == original
    assert calls == [("pipeline", "bifrost-deliver-platform-prod")]
