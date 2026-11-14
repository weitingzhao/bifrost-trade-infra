"""console-scope of task changes (task-ci-platform-changes.yaml): a commit that changes only
backend files no Console test reads does not run the Console's checks.

Owner, 2026-11-13: "if only the backend changed, do not test the frontend". That day three
backend-only runs spent most of their time in test-console: ci-platform-cwnqz (b3d486bd, one
file, api/internal/delivery/service.go) 389 s there against 105 s and 164 s in the Go tasks;
ci-platform-wcgvh 299 s; ci-platform-w2wrb 315 s.

The step's own script runs here against a local repository. Only `git clone` is redirected
to it; everything else is the script as the cluster runs it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "k8s/cicd/tekton/task-ci-platform-changes.yaml"
PIPELINE = ROOT / "k8s/cicd/tekton/pipeline-ci-platform.yaml"
URL = "http://gitea.cicd.svc.cluster.local:3000/bifrost/bifrost-platform.git"
LIST = "scripts/ci/console_reads_api.txt"
READS = textwrap.dedent("""\
    # what the Console tests read
    api/internal/questions/testdata/contract/
    api/internal/approvals/types.go
    """)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args],
        cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: Path, files: dict[str, str | None], message: str) -> str:
    for name, body in files.items():
        path = repo / name
        if body is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
    _git(repo, "add", "-A", ".")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture()
def world(tmp_path: Path):
    """main with the list and one file of each kind; returns a function that runs the step."""
    if not shutil.which("git"):
        pytest.skip("no git")
    repo = tmp_path / "origin"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, {
        LIST: READS,
        "api/internal/delivery/service.go": "package delivery\n",
        "api/internal/approvals/types.go": "package approvals\n",
        "api/internal/questions/testdata/contract/open.json": "{}\n",
        "console/src/pages/Page.tsx": "export {}\n",
        "config/x.yaml": "a: 1\n",
    }, "main")
    (doc,) = [d for d in yaml.safe_load_all(TASK.read_text()) if d]
    (step,) = doc["spec"]["steps"]
    script = step["script"]
    results = tmp_path / "results"
    results.mkdir()
    for name in ("api-scope", "why", "console-scope", "console-why"):
        script = script.replace(f"$(results.{name}.path)", str(results / name))
    real = shutil.which("git")
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "git").write_text(textwrap.dedent(f"""\
        #!/bin/sh
        # git clone of the Gitea address reads the local repository instead.
        for a in "$@"; do [ "$a" = clone ] && exec {real} clone -q --bare --no-tags {repo} "$(eval echo \\${{$#}})"; done
        exec {real} "$@"
        """))
    (shim / "git").chmod(0o755)
    path = tmp_path / "step.sh"
    path.write_text(script)

    def run(revision: str) -> dict[str, str]:
        for old in results.iterdir():
            old.unlink()
        env = {"PATH": f"{shim}:{os.environ['PATH']}", "GIT_USERNAME": "u", "GIT_PASSWORD": "p",
               "REPO_URL": URL, "REVISION": revision, "HOME": str(tmp_path), "TMPDIR": str(tmp_path)}
        done = subprocess.run(["sh", str(path)], env=env, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        return {p.name: p.read_text() for p in results.iterdir()}

    def branch(files: dict[str, str | None]) -> str:
        _git(repo, "checkout", "-q", "-B", "ready/x", "main")
        sha = _commit(repo, files, "change")
        _git(repo, "checkout", "-q", "main")
        return sha

    return run, branch, repo


def test_a_backend_only_commit_skips_the_console(world) -> None:
    # The shape of b3d486bd (ci-platform-cwnqz): one Go file under api/.
    run, branch, _ = world
    got = run(branch({"api/internal/delivery/service.go": "package delivery // changed\n"}))
    assert got["console-scope"] == "skip"
    assert "1 file(s), each under api/" in got["console-why"]
    # The Go side is judged as before: this is not a console-scope change.
    assert got["api-scope"] == "full"


@pytest.mark.parametrize("files, why", [
    # A Go file the Console's approvals test parses: the contract moved, both sides test.
    ({"api/internal/approvals/types.go": "package approvals // changed\n"}, "api/internal/approvals/types.go is a file the Console tests read"),
    # A new example in the directory both sides test against.
    ({"api/internal/questions/testdata/contract/closed.json": "{}\n"}, "api/internal/questions/testdata/contract/closed.json is a file the Console tests read"),
    # Backend and Console in one commit.
    ({"api/internal/delivery/service.go": "package delivery // changed\n", "console/src/pages/Page.tsx": "export { }\n"}, "console/src/pages/Page.tsx is outside api/"),
    # Not api/ and not console/: the Console tests read some of these (config, mcp); all of them run.
    ({"config/x.yaml": "a: 2\n"}, "config/x.yaml is outside api/"),
    # The list itself.
    ({LIST: READS + "api/internal/delivery/service.go\n"}, f"{LIST} is outside api/"),
    # A deleted backend file that is listed.
    ({"api/internal/approvals/types.go": None}, "api/internal/approvals/types.go is a file the Console tests read"),
])
def test_anything_else_runs_the_console_and_says_why(world, files, why) -> None:
    run, branch, _ = world
    got = run(branch(files))
    assert got["console-scope"] == "run"
    assert got["console-why"] == why


def test_a_console_only_commit_runs_the_console_and_keeps_its_go_scope(world) -> None:
    run, branch, _ = world
    got = run(branch({"console/src/pages/Page.tsx": "export { }\n"}))
    assert (got["console-scope"], got["api-scope"]) == ("run", "console")


def test_without_a_usable_list_the_console_runs(world) -> None:
    run, branch, repo = world
    # A branch from a main that has no list (every commit before this change).
    _git(repo, "checkout", "-q", "main")
    _commit(repo, {LIST: None}, "no list")
    got = run(branch({"api/internal/delivery/service.go": "package delivery // changed\n"}))
    assert got["console-scope"] == "run"
    assert "no scripts/ci/console_reads_api.txt" in got["console-why"]
    # A list with a line that is not a path under api/ is not trusted either.
    got = run(branch({LIST: "../etc\n", "api/internal/delivery/service.go": "package delivery // 2\n"}))
    assert got["console-scope"] == "run"


def test_a_commit_the_task_cannot_compare_runs_the_console(world) -> None:
    run, _, repo = world
    # A commit on main (a main push, a bifrost-ui push): nothing to compare it with.
    got = run(_git(repo, "rev-parse", "main"))
    assert (got["console-scope"], got["api-scope"]) == ("run", "full")
    assert got["console-why"] == got["why"] == "the commit is on main: nothing to compare it with"
    got = run("main")
    assert (got["console-scope"], got["console-why"]) == ("run", "revision is not a commit SHA")


def test_the_pipeline_hands_the_answer_to_test_console_and_reports_it() -> None:
    (doc,) = [d for d in yaml.safe_load_all(PIPELINE.read_text()) if d]
    (console,) = [t for t in doc["spec"]["tasks"] if t["name"] == "test-console"]
    assert {"name": "console-scope", "value": "$(tasks.changes.results.console-scope)"} in console["params"]
    results = {r["name"]: r["value"] for r in doc["spec"]["results"]}
    assert results["console-scope"] == "$(tasks.changes.results.console-scope)"
    assert results["console-scope-why"] == "$(tasks.changes.results.console-why)"
