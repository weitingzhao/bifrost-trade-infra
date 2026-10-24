"""TD-432 S7 / TD-435: offline credential and parameter boundary tests."""
from __future__ import annotations

import base64
import json
import io
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import urllib.request

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TEKTON = ROOT / "k8s/cicd/tekton"
HOST = "http://gitea.cicd.svc.cluster.local:3000"
TOKEN = "fixture-reader-password"
AUTH = base64.b64encode(f"bifrost-ci-reader:{TOKEN}".encode()).decode()


def steps(value):
    if isinstance(value, dict):
        if "script" in value:
            yield value
        for child in value.values():
            yield from steps(child)
    elif isinstance(value, list):
        for child in value:
            yield from steps(child)


def script_violations(root):
    return [str(path) for path in root.rglob("*") if path.suffix in (".yaml", ".yml")
            for doc in yaml.safe_load_all(path.read_text())
            for step in steps(doc) if "$(params." in step["script"]]


def test_no_task_script_interpolates_params():
    # Includes Pipeline inline taskSpecs and nested directories, no exceptions.
    assert script_violations(TEKTON) == []


def test_ratchet_rejects_inline_task_and_nested_task(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    for kind, spec in [("Task", {"steps": [{"script": "echo $(params.bad)"}]}),
                       ("Pipeline", {"tasks": [{"taskSpec": {"steps": [
                           {"script": "echo $(params.bad)"}]}}]})]:
        (nested / (kind + (".yaml" if kind == "Task" else ".yml"))).write_text(yaml.safe_dump({"kind": kind, "spec": spec}))
    assert len(script_violations(tmp_path)) == 2


def test_migrated_parameter_guards_accept_values_and_reject_shell_text():
    valid = dict(namespace="research", deployment="research-api", application="bifrost-research",
                 expectTag="", tag="0.95.0", applyTimeoutSeconds="300", repo="bifrost-research",
                 sourceDir="repo", serviceBase="http://research-api.research:8080",
                 traefikBase="http://192.168.10.73:30880", gatewayHost="stg.trader.bifrost.lan")
    for path in TEKTON.rglob("*.yaml"):
        for doc in yaml.safe_load_all(path.read_text()):
            for step in steps(doc):
                params = {e["name"]: valid[re.fullmatch(r"\$\(params\.(\w+)\)", e["value"])[1]]
                          for e in step.get("env", []) if e["name"].startswith("TASK_")}
                if not params:
                    continue
                lines = step["script"].splitlines()
                last = max(i for i, line in enumerate(lines) if 'exit 1 ;; esac' in line and 'invalid' in line)
                prefix = "\n".join(lines[:last + 1]) + "\nexit 0\n"
                for key in params:
                    for value, expected in [(params[key], 0), ('x"; exit 0; #', 1), (params[key] + "\nbad", 1)]:
                        result = subprocess.run(["bash"], input=prefix,
                                                env={**os.environ, **params, key: value},
                                                capture_output=True, text=True)
                        assert result.returncode == expected, (path, key, value, result.stderr)


def test_reader_consumers_and_no_credential_initializer():
    paths = [TEKTON / f for f in ("task-git-clone-gitea.yaml", "task-refresh-dockerfile-cms.yaml",
             "task-gitea-mirror-sync.yaml", "pipeline-deliver-platform-prod.yaml",
             "apply-manifest/pipeline.yaml")]
    paths += [ROOT / "k8s/cicd/github-sync" / f for f in
              ("task-github-sync.yaml", "cronjob-reconcile.yaml")]
    for path in paths:
        text = path.read_text()
        assert "gitea-ci-reader" in text, path
        assert "gitea-git-credentials" not in text, path
        assert "gitea-bootstrap" not in text, path
    for path in (ROOT / "k8s/cicd").rglob("*.yaml"):
        for doc in yaml.safe_load_all(path.read_text()):
            if isinstance(doc, dict) and doc.get("kind") == "ServiceAccount":
                assert not any(s["name"] in ("gitea-ci-reader", "gitea-git-credentials")
                               for s in doc.get("secrets", [])), path
    example = (ROOT / "k8s/cicd/gitea/secret.yaml.example").read_text()
    assert "tekton.dev/git-" not in example
    role = list(yaml.safe_load_all((ROOT / "k8s/platform-rbac/30-applier.yaml").read_text()))
    read = next(d for d in role if d["kind"] == "Role" and d["metadata"]["name"] == "bifrost-applier-read")
    assert any(r.get("resourceNames") == ["gitea-ci-reader"] for r in read["rules"])


@pytest.fixture
def clone_fixture(tmp_path):
    real_git = shutil.which("git")
    env = {**os.environ, "HOME": str(tmp_path / "home"), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "Fixture",
           "GIT_AUTHOR_EMAIL": "fixture@example.invalid", "GIT_COMMITTER_NAME": "Fixture",
           "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
    Path(env["HOME"]).mkdir()
    source = tmp_path / "source"
    source.mkdir()

    def git(*args):
        return subprocess.check_output([real_git, *args], cwd=source, env=env, text=True).strip()

    git("init", "-q", "--initial-branch=main")
    (source / "file").write_text("fixture")
    git("add", "file")
    git("commit", "-qm", "fixture")
    git("tag", "v1.2.3")
    git("branch", "agent/test/a1")
    sha = git("rev-parse", "HEAD")
    bare = tmp_path / "repo.git"
    git("clone", "-q", "--bare", str(source), str(bare))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # Intercept the git executable only; the Task script is unmodified except
    # Tekton workspace/result substitutions. Real git clones a local bare repo.
    wrapper = bindir / "git"
    wrapper.write_text("#!/usr/bin/env python3\n" + '''import json, os, pathlib, sys
a = sys.argv[1:]
r = pathlib.Path(os.environ["PROBE_ROOT"])
keys = {k: v for k, v in os.environ.items() if k.startswith("GIT_CONFIG_") or k in ("GIT_USERNAME", "GIT_PASSWORD")}
with (r / "calls").open("a") as f:
    f.write(json.dumps({"args": a, "env": keys}) + "\\n")
if "fetch" in a and os.environ.get("REFUSE_FETCH") and not (r / "refused").exists():
    (r / "refused").touch()
    sys.exit(1)
os.execv(os.environ["REAL_GIT"], [os.environ["REAL_GIT"], "-c",
    "url.file://" + os.environ["BARE"] + ".insteadOf=" + os.environ["CLONE_URL"], *a])
''')
    wrapper.chmod(0o755)
    env.update(PATH=str(bindir) + ":" + env["PATH"], PROBE_ROOT=str(tmp_path),
               REAL_GIT=real_git, BARE=str(bare), CLONE_URL=HOST + "/bifrost/repo.git",
               REVISION="main", SUBDIR="repo", GIT_USERNAME="bifrost-ci-reader", GIT_PASSWORD=TOKEN,
               GITEA_BASE=HOST + "/bifrost")
    return tmp_path, env, sha


def run_clone(fixture, task="task-git-clone-gitea.yaml", **values):
    root, env, _ = fixture
    env = {**env, **values}
    script = yaml.safe_load((TEKTON / task).read_text())["spec"]["steps"][0]["script"]
    script = re.sub(r"\$\(workspaces\.[^.]+\.path\)", str(root / "workspace"), script)
    script = script.replace("$(results.commit.path)", str(root / "result"))
    # Model the next process in this shell; ordinary child processes must not
    # inherit raw credentials or header config after git completes.
    script += '\nenv > "' + str(root / "next-env") + '"\n'
    result = subprocess.run(["sh"], input=script, cwd=root, env=env, capture_output=True, text=True)
    return result


@pytest.mark.parametrize("revision", ["main", "agent/test/a1", "v1.2.3", "sha", "fallback"])
def test_clone_real_bare_repo_has_no_credentials(clone_fixture, revision):
    root, _, sha = clone_fixture
    values = {"REVISION": sha if revision in ("sha", "fallback") else revision}
    if revision == "fallback":
        values["REFUSE_FETCH"] = "yes"
    result = run_clone(clone_fixture, **values)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / "result").read_text() == sha
    calls = [json.loads(line) for line in (root / "calls").read_text().splitlines()]
    remote_calls = [c for c in calls if "fetch" in c["args"] or "clone" in c["args"]]
    assert remote_calls
    for call in remote_calls:
        assert call["env"]["GIT_CONFIG_VALUE_0"] == "Authorization: Basic " + AUTH
        assert HOST in call["env"]["GIT_CONFIG_KEY_0"]
        assert "GIT_PASSWORD" not in call["env"]
        assert TOKEN not in str(call["args"]) and AUTH not in str(call["args"])
    for tree in (root / "workspace", root / "home"):
        for path in tree.rglob("*"):
            if path.is_file():
                assert TOKEN.encode() not in path.read_bytes(), path
                assert AUTH.encode() not in path.read_bytes(), path
    config = (root / "workspace/repo/.git/config").read_text()
    assert HOST + "/bifrost/repo.git" in config
    assert "extraheader" not in config.lower()
    inherited = (root / "next-env").read_text()
    assert TOKEN not in inherited and AUTH not in inherited
    assert "GIT_CONFIG_VALUE_" not in inherited
    assert TOKEN not in result.stdout + result.stderr


@pytest.mark.parametrize("key,value", [
    ("REVISION", 'main"; touch marker; #'), ("REVISION", "$(touch marker)"),
    ("REVISION", "abc1234"), ("REVISION", "main\nbad"), ("REVISION", "../main"),
    ("SUBDIR", "../escape"), ("SUBDIR", "a/b"), ("SUBDIR", "."),
    ("CLONE_URL", "http://attacker.invalid/bifrost/repo.git"),
    ("CLONE_URL", HOST + "/bifrost/repo.git\nhttp://attacker.invalid")])
def test_bad_clone_parameter_fails_without_fetch(clone_fixture, key, value):
    root, _, _ = clone_fixture
    result = run_clone(clone_fixture, **{key: value})
    assert result.returncode != 0
    assert not (root / "workspace").exists()
    assert not (root / "marker").exists()
    if (root / "calls").exists():
        assert all("clone" not in c and "fetch" not in c for c in (root / "calls").read_text().splitlines())


@pytest.mark.parametrize("revision", ["main", "v1.2.3"])
def test_refresh_clones_main_or_explicit_tag(clone_fixture, revision):
    root, env, _ = clone_fixture
    env["CLONE_URL"] = HOST + "/bifrost/bifrost-trade-infra.git"
    result = run_clone(clone_fixture, "task-refresh-dockerfile-cms.yaml", REVISION=revision)
    assert result.returncode == 0, result.stderr
    for path in (root / "workspace").rglob("*"):
        if path.is_file():
            assert AUTH.encode() not in path.read_bytes()
    assert TOKEN not in (root / "next-env").read_text()


@pytest.mark.parametrize("revision", ["agent/test/a1", "deadbeef", "v1.2.3;id", "v1.2.3\n"])
def test_refresh_rejects_untrusted_revisions(clone_fixture, revision):
    result = run_clone(clone_fixture, "task-refresh-dockerfile-cms.yaml", REVISION=revision)
    assert result.returncode != 0


@pytest.mark.parametrize("name,token,expected", [("primary", TOKEN, 0), ("../escape", TOKEN, 1), ("primary", "", 1)])
def test_github_read_primaries_uses_reader_header(tmp_path, monkeypatch, name, token, expected):
    calls = []

    class Response(io.BytesIO):
        status = 200

    class Transport:
        def open(self, request, timeout):
            calls.append(request)
            return Response(b'{"mirror": false}')

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: Transport())
    monkeypatch.setenv("GITEA_TOKEN", token)
    monkeypatch.setenv("GITEA_API", HOST + "/api/v1")
    monkeypatch.setenv("GITEA_ORG", "bifrost")
    output = tmp_path / "primaries"
    monkeypatch.setattr(sys, "argv", ["read-primaries.py", str(output), name])
    module = runpy.run_path(str(ROOT / "k8s/cicd/github-sync/read-primaries.py"))
    assert module["main"]() == expected
    if expected == 0:
        assert output.read_text() == "primary\n"
        assert len(calls) == 1
        assert calls[0].headers["Authorization"] == "token " + TOKEN
        assert calls[0].full_url == HOST + "/api/v1/repos/bifrost/primary"
    else:
        assert calls == []

