"""TD-411: the Owner's apply script checks before it writes, applies STG at once and
PROD's pipeline only once PROD's health reports agentrt_schema_applied.

Run in a throwaway git repository holding the script and its four files, with fake
kubectl and curl on PATH."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = "scripts/release/agentrt-migrate-pipelines.sh"
STG = [
    "k8s/cicd/tekton/rbac-deliver-migrate-stg.yaml",
    "k8s/cicd/tekton/task-agentrt-migrate-stg.yaml",
    "k8s/cicd/tekton/pipeline-deliver-platform.yaml",
]
PROD = "k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml"

FAKE_KUBECTL = r'''#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
case "$1 $2" in
  "auth can-i") echo "${FAKE_CAN:-yes}"; exit 0 ;;
esac
if [[ "$1" == apply && "$2" == --dry-run=server ]]; then
  [[ -n "${FAKE_REFUSE:-}" && "$4" == "$FAKE_REFUSE" ]] && { echo refused >&2; exit 1; }
  exit 0
fi
[[ "$1" == diff ]] && exit 1
exit 0
'''

FAKE_CURL = r'''#!/usr/bin/env bash
printf '%s' "$FAKE_HEALTH"
'''


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "infra"
    for rel in [SCRIPT, *STG, PROD]:
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, r / rel)
    git = ["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.hooksPath=/dev/null"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "x"], check=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("kubectl", FAKE_KUBECTL), ("curl", FAKE_CURL)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    return r, bin_dir, tmp_path / "kubectl.log"


def run(repo, step, health=None, can="yes", refuse=""):
    r, bin_dir, log = repo
    body = json.dumps(health if health is not None else {"agentrt_schema": "current"})
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_LOG": str(log),
           "FAKE_HEALTH": body, "FAKE_CAN": can, "FAKE_REFUSE": refuse}
    out = subprocess.run(["bash", str(r / SCRIPT), step], env=env, capture_output=True, text=True, timeout=60)
    calls = log.read_text().splitlines() if log.exists() else []
    return out, calls


def applied(calls):
    return [c.split()[-1] for c in calls if c.startswith("apply -f ")]


def test_apply_waits_with_prod_until_health_says(repo):
    out, calls = run(repo, "apply")
    assert out.returncode == 0, out.stdout + out.stderr
    assert applied(calls) == STG
    assert "the PROD pipeline waits" in out.stdout and "Run apply again" in out.stdout


def test_apply_takes_prod_once_health_says(repo):
    out, calls = run(repo, "apply", {"agentrt_schema": "current", "agentrt_schema_applied": []})
    assert out.returncode == 0, out.stdout + out.stderr
    assert applied(calls) == [*STG, PROD]
    # every file had a server dry-run before the first write
    first_write = next(i for i, c in enumerate(calls) if c.startswith("apply -f "))
    dry = [c.split()[-1] for c in calls[:first_write] if c.startswith("apply --dry-run=server")]
    assert dry == [*STG, PROD]


def test_check_writes_nothing(repo):
    out, calls = run(repo, "check", {"agentrt_schema_applied": []})
    assert out.returncode == 0 and applied(calls) == []
    assert "nothing written" in out.stdout


def test_an_agent_identity_stops_before_anything(repo):
    out, calls = run(repo, "apply", can="no")
    assert out.returncode == 1 and "run this in your own terminal" in out.stdout
    assert all(c.startswith("auth can-i") for c in calls)


def test_a_refused_dry_run_stops_before_any_write(repo):
    out, calls = run(repo, "apply", refuse=STG[2])
    assert out.returncode == 1 and "the server refuses " + STG[2] in out.stdout
    assert applied(calls) == []


def test_an_edited_file_stops_before_kubectl(repo):
    r, _, _ = repo
    with open(r / STG[1], "a") as f:
        f.write("# edited\n")
    out, calls = run(repo, "apply")
    assert out.returncode == 1 and "differ from the checkout's commit" in out.stdout
    assert calls == []


def test_usage(repo):
    out, _ = run(repo, "")
    assert out.returncode == 2 and "check" in out.stdout and "apply" in out.stdout
