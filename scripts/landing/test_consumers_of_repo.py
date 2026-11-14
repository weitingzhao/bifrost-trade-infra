"""consumers_of_repo.py: the repository that changes a fingerprinted line is told in its own CI.

Origin of the cases: 2026-11-14. Platform commit 98900d68 changed one line of
console/src/pages/shell/owner/OwnerConsolePage.tsx that this repository's registry of document
consumers fingerprints; the platform's CI did not look, and every landing of this repository was
refused for six hours (ci-infra-2ln4p, ci-infra-x6j7z). The same had happened on 2026-10-31,
11-01 and 11-02. The fixture rows carry that file's real lines.
"""
import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("consumers_of_repo.py")
D = runpy.run_path(str(Path(__file__).with_name("doc_consumers.py")))
REGISTRY = "agent-config/landing/doc-consumers.yaml"
PAGE = "console/src/pages/shell/owner/OwnerConsolePage.tsx"
BEFORE = "return { you: entry === 'command', work: entry === 'work', system: entry === 'system', crew: entry === 'crew' }\n"
AFTER = "return { you: entry === 'command', work: entry === 'work', system: entry === 'system', crew: entry === 'crew', services: entry === 'services' }\n"


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def commit(repo, files):
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        git(repo, "add", "--", name)
    git(repo, "-c", "user.name=CI fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
    return git(repo, "rev-parse", "HEAD")


def row(name, text, repo="bifrost-platform"):
    out = {"file": name, "class": "token", "effect": "runtime", "hits": D["fingerprint"](D["hits"](name, text.encode(), True)),
           "why": "a route id", "checked_by": "fixture"}
    if repo:
        out["repo"] = repo   # the one other repository the registry's own reader accepts
    return json.dumps(out)


@pytest.fixture
def repos(tmp_path):
    registry, other = tmp_path / "registry", tmp_path / "other"
    for r in (registry, other):
        r.mkdir()
        git(r, "init", "-q")
    # A row of the registry's own repository with the same file name must not be mistaken for the other's.
    commit(registry, {REGISTRY: "\n".join("- " + r for r in (row(PAGE, BEFORE), row("scripts/own.py", "x = '/work/'\n", repo=None))) + "\n"})
    commit(other, {PAGE: BEFORE, "api/plain.go": "package plain\n"})
    return registry, other


def run(registry, other, name="bifrost-platform"):
    return subprocess.run([sys.executable, str(SCRIPT), "--registry-repo", str(registry), "--name", name, "--candidate", str(other)],
                          capture_output=True, text=True, timeout=60)


def test_a_commit_that_matches_the_registry_passes(repos):
    r = run(*repos)
    assert r.returncode == 0 and r.stdout.startswith("ok: every hit of bifrost-platform"), r.stdout + r.stderr


def test_the_line_changed_on_2026_11_14_is_reported_with_the_value_the_row_needs(repos):
    registry, other = repos
    commit(other, {PAGE: AFTER})
    r = run(registry, other)
    assert r.returncode == 1, r.stdout + r.stderr
    now = D["fingerprint"](D["hits"](PAGE, AFTER.encode(), True))
    # The value this prints is the one the real registry row was given that day (a897dd87).
    assert now == "sha256:816c0f58b77c40a81bb5f8dc178e357b69447a80ffdb3088a725290838b6d436"
    assert f"FAIL consumer_changed {PAGE}" in r.stderr and f"hits now:       {now}" in r.stderr
    assert "line 1: return { you: entry === 'command'" in r.stderr and "hard floor" in r.stderr


def test_every_difference_is_listed_not_only_the_first(repos):
    # doc_consumers.py stops at the first: on 2026-10-31 that cost one CI run a difference.
    registry, other = repos
    commit(other, {PAGE: AFTER, "api/new.go": 'var path = "agent-config/work/x.md"\n', "docs/a.md": "see /work/ here\n"})
    r = run(registry, other)
    assert r.returncode == 1
    assert f"FAIL consumer_changed {PAGE}" in r.stderr and "FAIL unregistered_consumer api/new.go" in r.stderr
    assert '"repo": "bifrost-platform", "file": "api/new.go"' in r.stderr
    assert r.stderr.startswith("2 file(s)")
    # Markdown is not scanned, as in the registry check itself.
    assert "docs/a.md" not in r.stderr


def test_a_registered_file_that_is_gone_is_a_note_not_a_failure(repos):
    registry, other = repos
    git(other, "rm", "-q", PAGE)
    commit(other, {"api/plain.go": "package plain\n\n"})
    r = run(registry, other)
    assert r.returncode == 0 and "WARN 1 row(s)" in r.stdout and PAGE in r.stdout, r.stdout + r.stderr


def test_what_it_cannot_read_is_an_error_of_its_own(repos, tmp_path):
    registry, other = repos
    assert run(tmp_path / "nowhere", other).returncode == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    git(empty, "init", "-q")
    commit(empty, {"README": "no registry\n"})
    r = run(empty, other)
    assert r.returncode == 2 and r.stderr.startswith("FAIL "), r.stderr


def test_it_agrees_with_the_registry_check_on_the_same_tree(repos):
    # The narrowing search may only skip files without a hit: on this tree both list the same file.
    registry, other = repos
    commit(other, {PAGE: AFTER})
    rows = D["P"]["registry"](registry, git(registry, "rev-parse", "HEAD"))
    with pytest.raises(D["P"]["PolicyError"], match=f"consumer_changed {PAGE}"):
        D["verify"](rows, D["discover"](other, git(other, "rev-parse", "HEAD"), True), "bifrost-platform")


def test_the_platform_pipelines_step_runs_it_as_written(repos, tmp_path):
    """The step of pipeline-ci-platform.yaml, with the two checkouts where the pipeline puts them."""
    import os
    import shutil
    import yaml
    registry, other = repos
    pipeline = yaml.safe_load((Path(__file__).parents[2] / "k8s/cicd/tekton/pipeline-ci-platform.yaml").read_text())
    task = next(t for t in pipeline["spec"]["tasks"] if t["name"] == "consumers")
    assert task["runAfter"] == ["clone", "clone-infra"] and "when" not in task
    (step,) = task["taskSpec"]["steps"]
    ws = tmp_path / "ws"
    ws.mkdir()
    shutil.copytree(registry, ws / "bifrost-trade-infra")
    shutil.copytree(other, ws / "bifrost-platform")
    script = step["script"].replace("$(workspaces.source.path)", str(ws))
    assert "$(" not in script.replace("$(workspaces", "")

    def step_run(reuse="no"):
        return subprocess.run(["sh", "-c", script], env={"PATH": os.environ["PATH"], "REUSE": reuse}, capture_output=True, text=True, timeout=60)
    # An infra checkout from before the script: nothing to run, and it says so.
    r = step_run()
    assert r.returncode == 0 and "nothing to run" in r.stdout, r.stdout + r.stderr
    (ws / "bifrost-trade-infra/scripts/landing").mkdir(parents=True)
    for name in ("consumers_of_repo.py", "doc_consumers.py", "doc_policy.py"):
        shutil.copy(Path(__file__).with_name(name), ws / "bifrost-trade-infra/scripts/landing" / name)
    r = step_run()
    assert r.returncode == 0 and r.stdout.startswith("ok: every hit of bifrost-platform"), r.stdout + r.stderr
    commit(ws / "bifrost-platform", {PAGE: AFTER})
    r = step_run()
    assert r.returncode == 1 and f"FAIL consumer_changed {PAGE}" in r.stderr, r.stdout + r.stderr
    # A run that reuses another run's verdict does not look again.
    assert step_run("yes").returncode == 0
