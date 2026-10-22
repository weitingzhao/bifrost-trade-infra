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
    "k8s/platform-rbac/40-admission.yaml",
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
if a[2:3] == ["patch"]:
    # a delivery's pin as tekton-deliver: the live policy refuses it until 40-admission.yaml is
    # applied (FAKE_PIN=live), or answers as FAKE_PIN says
    mode = os.environ.get("FAKE_PIN", "live")
    if mode == "live":
        applied = os.path.exists(os.environ["FAKE_APPLIED"]) and "40-admission.yaml" in open(os.environ["FAKE_APPLIED"]).read()
        mode = "new" if applied else "old"
    by_tag = ":stg" in a[a.index("-p") + 1]
    deny = "The applications \"x\" is invalid: : ValidatingAdmissionPolicy 'bifrost-platform-application' with binding 'bifrost-platform-application' denied request: no"
    if mode == "old" or (mode == "new" and by_tag):
        print(deny, file=sys.stderr); sys.exit(1)
    if mode == "rbac":
        print("forbidden: User \"system:serviceaccount:cicd:tekton-deliver\" cannot patch", file=sys.stderr); sys.exit(1)
    print("application.argoproj.io/x patched (server dry run)"); sys.exit()
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


def test_no_argo_application_is_written(repo):
    # a delivery pins its own application; the Owner's apply only tries the pin, not stored
    out, calls = run(repo, "apply")
    assert out.returncode == 0, out.stdout + out.stderr
    named = [c for c in calls if "application" in c.lower() and "40-admission.yaml" not in c]
    assert len(named) == 3, calls
    for c in named:
        assert c.startswith("-n cicd patch applications.argoproj.io/bifrost-platform-"), c
        assert " --dry-run=server --as system:serviceaccount:cicd:tekton-deliver " in c, c
    code = [ln for ln in (ROOT / SCRIPT).read_text().splitlines() if not ln.strip().startswith("#")]
    kubectl_lines = [i for i, ln in enumerate(code) if "kubectl" in ln and "application" in ln.lower()]
    assert len(kubectl_lines) == 1 and "--dry-run=server" in code[kubectl_lines[0]], kubectl_lines


def pin_calls(calls):
    return [c for c in calls if c.startswith("-n cicd patch ")]


def test_apply_tries_a_delivery_pin_after_every_write(repo):
    out, calls = run(repo, "apply")
    assert out.returncode == 0, out.stdout + out.stderr
    last_write = max(i for i, c in enumerate(calls) if c.startswith("apply -f "))
    pins = [i for i, c in enumerate(calls) if c.startswith("-n cicd patch ")]
    assert pins and min(pins) > last_write
    assert "a delivery's digest pin of bifrost-platform-stg passes admission" in out.stdout
    assert "a delivery's digest pin of bifrost-platform-prod passes admission" in out.stdout
    assert "a pin by tag is refused by the admission policy" in out.stdout
    # the pin tried is the one the gitops-sync Task sends (review 514: the whole patch, not only its images)
    body = pin_calls(calls)[0].split(" -p ", 1)[1].split(" --dry-run=server", 1)[0]
    zero = "@sha256:" + "0" * 64
    assert __import__("json").loads(body) == {
        "spec": {"source": {"kustomize": {"images": [
            "registry.cicd.svc.cluster.local:5000/bifrost-platform-api=192.168.10.73:30500/bifrost-platform-api" + zero,
            "registry.cicd.svc.cluster.local:5000/bifrost-platform-console=192.168.10.73:30500/bifrost-platform-console" + zero,
        ]}}},
        "operation": {"initiatedBy": {"username": "tekton-deliver-platform:speedup-apply-check"}, "sync": {"revision": "HEAD"}},
    }
    task_patch = (ROOT / "scripts/release/platform_pin_sync.py").read_text()
    assert 'who = "tekton-deliver-platform:" + run' in task_patch
    assert '"operation": {"initiatedBy": {"username": who}, "sync": {"revision": "HEAD"}},' in task_patch


@pytest.mark.parametrize(
    "pin, says",
    [
        ("old", "a delivery's digest pin of bifrost-platform-stg is refused: The applications"),
        ("wide", "a pin by tag passes admission: the policy is wider than a digest pin"),
        ("rbac", "is refused: forbidden"),
    ],
)
def test_apply_stops_when_the_pin_is_not_answered_as_it_should_be(repo, pin, says):
    out, _ = run(repo, "apply", FAKE_PIN=pin)
    assert out.returncode == 1 and says in out.stdout, out.stdout
    assert "start no platform delivery" in out.stdout


def test_check_reports_the_policy_before_it_is_applied_and_writes_nothing(repo):
    out, calls = run(repo, "check")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "a delivery's digest pin of bifrost-platform-stg is refused" in out.stdout
    assert "until 40-admission.yaml is applied" in out.stdout and "nothing written" in out.stdout
    assert applied(calls) == []


def test_usage(repo):
    out, _ = run(repo, "")
    assert out.returncode == 2 and "check" in out.stdout and "apply" in out.stdout
