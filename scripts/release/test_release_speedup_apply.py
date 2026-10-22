"""W-31 3.4 ①②: the Owner's apply script checks before it writes and applies the commit's bytes.

Run in a throwaway git repository holding the script and its files, with a fake kubectl
and a fake release window on PATH."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = "scripts/release/release-speedup-apply.sh"
FILES = [
    "k8s/cicd/tekton/task-argocd-pin-sync-platform.yaml",
    "k8s/cicd/tekton/task-rollout-verify-platform.yaml",
    "k8s/cicd/tekton/pipeline-deliver-platform.yaml",
    "k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml",
    "k8s/cicd/tekton/trigger-trade-ci.yaml",
]

FAKE_KUBECTL = r'''#!/usr/bin/env python3
import os, sys
a = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(" ".join(a) + "\n")
if a[:2] == ["auth", "can-i"]:
    print(os.environ.get("FAKE_CAN", "yes")); sys.exit()
if a[:2] == ["apply", "--dry-run=server"]:
    r = os.environ.get("FAKE_REFUSE")
    sys.exit(1 if r and a[3].endswith(r) else 0)
if a[:2] == ["apply", "-f"]:
    with open(os.environ["FAKE_APPLIED"], "a") as f:
        f.write("--- " + a[2] + "\n" + open(a[2]).read())
    r = os.environ.get("FAKE_APPLY_FAILS")
    sys.exit(1 if r and a[2].endswith(r) else 0)
if a[:1] == ["diff"]:
    sys.exit(1)
'''


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "infra"
    for rel in [SCRIPT, *FILES]:
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, r / rel)
    git = ["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.hooksPath=/dev/null"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "x"], check=True)
    subprocess.run([*git, "update-ref", "refs/remotes/origin/main", "HEAD"], check=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "kubectl").write_text(FAKE_KUBECTL)
    (bin_dir / "kubectl").chmod(0o755)
    window = tmp_path / "window.sh"
    window.write_text('#!/bin/sh\nexit "${FAKE_WINDOW:-0}"\n')
    window.chmod(0o755)
    return r, bin_dir, tmp_path / "kubectl.log", window


def run(repo, step, **env_over):
    r, bin_dir, log, window = repo
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_LOG": str(log),
           "FAKE_APPLIED": str(log) + ".applied", "SPEEDUP_WINDOW": str(window), **env_over}
    out = subprocess.run(["bash", str(r / SCRIPT), step], env=env, capture_output=True, text=True, timeout=60)
    calls = log.read_text().splitlines() if log.exists() else []
    return out, calls


def applied(calls):
    return [next(f for f in FILES if c.split()[2].endswith("/" + f)) for c in calls if c.startswith("apply -f ")]


def test_apply_writes_every_file_in_order_after_every_dry_run(repo):
    out, calls = run(repo, "apply")
    assert out.returncode == 0, out.stdout + out.stderr
    assert applied(calls) == FILES
    first_write = next(i for i, c in enumerate(calls) if c.startswith("apply -f "))
    dry = [c.split()[3] for c in calls[:first_write] if c.startswith("apply --dry-run=server")]
    assert [next(f for f in FILES if d.endswith("/" + f)) for d in dry] == FILES


def test_check_writes_nothing(repo):
    out, calls = run(repo, "check")
    assert out.returncode == 0 and applied(calls) == []
    assert "nothing written" in out.stdout


def test_an_open_window_stops_before_any_write(repo):
    out, calls = run(repo, "apply", FAKE_WINDOW="1")
    assert out.returncode == 1 and "a release window is open" in out.stdout
    assert applied(calls) == [] and not [c for c in calls if c.startswith("apply")]


def test_an_agent_identity_stops_before_anything(repo):
    out, calls = run(repo, "apply", FAKE_CAN="no")
    assert out.returncode == 1 and "run this in your own terminal" in out.stdout
    assert all(c.startswith("auth can-i") for c in calls)


def test_a_refused_dry_run_stops_before_any_write(repo):
    out, calls = run(repo, "apply", FAKE_REFUSE=FILES[3])
    assert out.returncode == 1 and "the server refuses " + FILES[3] in out.stdout
    assert applied(calls) == []


def test_an_edited_file_is_not_what_is_applied(repo):
    r, _, log, _ = repo
    committed = (r / FILES[0]).read_text()
    with open(r / FILES[0], "a") as f:
        f.write("# edited after the commit\n")
    out, _ = run(repo, "apply")
    assert out.returncode == 0, out.stdout + out.stderr
    text = (log.parent / (log.name + ".applied")).read_text()
    assert committed in text and "edited after the commit" not in text


def test_a_commit_not_on_main_stops_before_kubectl(repo):
    r, _, _, _ = repo
    git = ["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.hooksPath=/dev/null"]
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "local"], check=True)
    out, calls = run(repo, "apply")
    assert out.returncode == 1 and "not on origin/main" in out.stdout and calls == []


def test_a_failed_apply_names_what_went_and_says_rerun(repo):
    out, calls = run(repo, "apply", FAKE_APPLY_FAILS=FILES[2])
    assert out.returncode == 1
    assert "applied before it: " + FILES[0] + " " + FILES[1] in out.stdout
    assert "Run apply again at commit" in out.stdout


def test_every_cluster_call_is_bounded(repo):
    out, calls = run(repo, "apply")
    assert out.returncode == 0
    for c in calls:
        if not c.startswith("apply -f "):
            assert c.endswith(" --request-timeout=20s"), c


def test_no_argo_application_is_touched():
    # a delivery pins its own application; the Owner's apply never names one
    code = [ln for ln in (ROOT / SCRIPT).read_text().splitlines() if not ln.strip().startswith("#")]
    assert not [ln for ln in code if "application" in ln.lower()]


def test_usage(repo):
    out, _ = run(repo, "")
    assert out.returncode == 2 and "check" in out.stdout and "apply" in out.stdout
