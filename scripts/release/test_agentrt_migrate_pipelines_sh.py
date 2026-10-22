"""TD-411: the Owner's apply script checks before it writes, applies STG at once and
PROD's pipeline only once every PROD platform-api pod reports agentrt_schema_applied.

Run in a throwaway git repository holding the script and its files, with a fake kubectl
on PATH that answers PROD's Deployment, its pods and each pod's /health."""

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
    "k8s/cicd/tekton/task-promote-platform-images.yaml",
    "k8s/cicd/tekton/pipeline-deliver-platform.yaml",
]
PROD = "k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml"
NS = "bifrost-platform-prod"

FAKE_KUBECTL = r'''#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(" ".join(a) + "\n")
st = json.loads(os.environ["FAKE_STATE"])
RT = "--request-timeout=20s"
if a[:1] == ["get"] or a[:2] == ["auth", "can-i"]:
    # every read before the writes is bounded (review 503 B2)
    assert a[-1] == RT, a
    a = a[:-1]
if a[:2] == ["auth", "can-i"]:
    print(os.environ.get("FAKE_CAN", "yes") if " ".join(a[2:]) != os.environ.get("FAKE_CANNOT") else "no"); sys.exit()
if a[:3] == ["get", "deployment", "platform-api"]:
    assert a[3:] == ["-n", "bifrost-platform-prod", "-o", "json"], a
    print(json.dumps(st["deployment"])); sys.exit()
if a[:2] == ["get", "replicasets"]:
    assert a[2:] == ["-n", "bifrost-platform-prod", "-o", "json"], a
    print(json.dumps({"items": st["replicasets"]})); sys.exit()
if a[:2] == ["get", "pods"]:
    assert a[2:] == ["-n", "bifrost-platform-prod", "-l", "app.kubernetes.io/name=platform-api", "-o", "json"], a
    n_file = os.environ["FAKE_LOG"] + ".pods"
    n = int(open(n_file).read()) if os.path.exists(n_file) else 0
    open(n_file, "w").write(str(n + 1))
    sets = st["pods"]
    print(json.dumps({"items": sets[min(n, len(sets) - 1)]})); sys.exit()
if a[:2] == ["get", "--raw"]:
    pre, post = "/api/v1/namespaces/bifrost-platform-prod/pods/", ":8780/proxy/health"
    path = a[2]
    assert len(a) == 3, a
    assert path.startswith(pre) and path.endswith(post), path
    body = st["health"].get(path[len(pre):-len(post)])
    if body is None:
        print("pod not found", file=sys.stderr); sys.exit(1)
    print(json.dumps(body)); sys.exit()
if a[:2] == ["apply", "--dry-run=server"]:
    r = os.environ.get("FAKE_REFUSE")
    if r and a[3].endswith(r):
        print("refused", file=sys.stderr); sys.exit(1)
    sys.exit()
if a[:2] == ["apply", "-f"]:
    # what is applied, byte for byte
    with open(os.environ["FAKE_APPLIED"], "a") as f:
        f.write("--- " + a[2] + "\n" + open(a[2]).read())
    r = os.environ.get("FAKE_APPLY_FAILS")
    sys.exit(1 if r and a[2].endswith(r) else 0)
if a[:1] == ["diff"]:
    sys.exit(1)
'''


def deployment(replicas=2, converged=True):
    st = {k: replicas for k in ("replicas", "updatedReplicas", "readyReplicas", "availableReplicas")}
    if not converged:
        st["updatedReplicas"] = replicas - 1
    st["observedGeneration"] = 7
    return {"metadata": {"generation": 7, "uid": "deploy-uid"}, "spec": {"replicas": replicas}, "status": st}


def owner(uid):
    return [{"kind": "ReplicaSet", "uid": uid, "controller": True}]


# the Deployment's ReplicaSet, and one with the same label that another owner holds
REPLICASETS = [
    {"metadata": {"name": "platform-api-7f9", "uid": "rs-uid",
                  "ownerReferences": [{"kind": "Deployment", "uid": "deploy-uid", "controller": True}]}},
    {"metadata": {"name": "platform-api-old", "uid": "rs-foreign",
                  "ownerReferences": [{"kind": "Deployment", "uid": "another-deploy", "controller": True}]}},
]


def pod(name, ready=True, image="sha256:aaa", rs="rs-uid", container="containerd://c1", restarts=0):
    return {"metadata": {"name": name, "uid": "uid-" + name, "ownerReferences": owner(rs)},
            "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
                       "containerStatuses": [{"name": "platform-api", "imageID": "registry/bifrost-platform-api@" + image,
                                              "containerID": container + "-" + name, "restartCount": restarts}]}}


PODS = [pod("platform-api-1"), pod("platform-api-2")]
WITH = {"agentrt_schema": "current", "agentrt_schema_applied": []}
WITHOUT = {"agentrt_schema": "current"}


def state(health=None, deploy=None, pods=None):
    return {"deployment": deploy or deployment(), "pods": pods or [PODS], "replicasets": REPLICASETS,
            "health": health if health is not None else {"platform-api-1": WITHOUT, "platform-api-2": WITHOUT}}


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
    subprocess.run([*git, "update-ref", "refs/remotes/origin/main", "HEAD"], check=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "kubectl").write_text(FAKE_KUBECTL)
    (bin_dir / "kubectl").chmod(0o755)
    return r, bin_dir, tmp_path / "kubectl.log"


def run(repo, step, st=None, can="yes", refuse="", apply_fails="", cannot=""):
    r, bin_dir, log = repo
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_LOG": str(log),
           "FAKE_STATE": json.dumps(st or state()), "FAKE_CAN": can, "FAKE_CANNOT": cannot, "FAKE_REFUSE": refuse,
           "FAKE_APPLIED": str(log) + ".applied", "FAKE_APPLY_FAILS": apply_fails}
    out = subprocess.run(["bash", str(r / SCRIPT), step], env=env, capture_output=True, text=True, timeout=60)
    calls = log.read_text().splitlines() if log.exists() else []
    return out, calls


ALL_WITH = state({"platform-api-1": WITH, "platform-api-2": WITH})


def applied(calls):
    # the snapshot path ends with the file's path in the repository
    out = []
    for c in calls:
        if c.startswith("apply -f "):
            path = c.split()[-1]
            out.append(next(f for f in [*STG, PROD] if path.endswith("/" + f)))
    return out


def test_apply_waits_with_prod_until_health_says(repo):
    out, calls = run(repo, "apply")
    assert out.returncode == 0, out.stdout + out.stderr
    assert applied(calls) == STG
    assert "the PROD pipeline waits" in out.stdout and "Run apply again" in out.stdout


def test_apply_takes_prod_once_health_says(repo):
    out, calls = run(repo, "apply", ALL_WITH)
    assert out.returncode == 0, out.stdout + out.stderr
    assert applied(calls) == [*STG, PROD]
    # every file had a server dry-run before the first write
    first_write = next(i for i, c in enumerate(calls) if c.startswith("apply -f "))
    dry = [c.split()[-1] for c in calls[:first_write] if c.startswith("apply --dry-run=server")]
    assert [next(f for f in [*STG, PROD] if d.endswith("/" + f)) for d in dry] == [*STG, PROD]


def test_check_writes_nothing(repo):
    out, calls = run(repo, "check", ALL_WITH)
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


def test_an_edited_file_is_not_what_is_applied(repo):
    # Review 498 A3: the commit's bytes are applied, never the working tree's.
    r, _, log = repo
    committed = (r / STG[1]).read_text()
    with open(r / STG[1], "a") as f:
        f.write("# edited after the commit\n")
    out, calls = run(repo, "apply")
    assert out.returncode == 0, out.stdout + out.stderr
    text = (log.parent / (log.name + ".applied")).read_text()
    assert committed in text and "edited after the commit" not in text


def test_a_file_not_in_the_commit_stops_before_kubectl(repo):
    r, _, _ = repo
    git = ["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.hooksPath=/dev/null"]
    subprocess.run([*git, "rm", "-q", STG[2]], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "drop"], check=True)
    subprocess.run([*git, "update-ref", "refs/remotes/origin/main", "HEAD"], check=True)
    # put it back untracked: it is still not in the commit
    shutil.copy(ROOT / STG[2], r / STG[2])
    out, calls = run(repo, "apply")
    assert out.returncode == 1 and "is not in commit" in out.stdout and calls == []


def test_a_commit_not_on_main_stops_before_kubectl(repo):
    r, _, _ = repo
    git = ["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.hooksPath=/dev/null"]
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "local"], check=True)
    out, calls = run(repo, "apply")
    assert out.returncode == 1 and "not on origin/main" in out.stdout and calls == []


def test_prod_waits_while_its_rollout_is_unfinished(repo):
    st = state({"platform-api-1": WITH, "platform-api-2": WITH}, deploy=deployment(converged=False))
    out, calls = run(repo, "apply", st)
    assert out.returncode == 0 and applied(calls) == STG
    assert "has not converged on 2 replicas" in out.stdout and "the PROD pipeline waits" in out.stdout


@pytest.mark.parametrize(
    "pods, says",
    [
        ([pod("platform-api-1"), pod("platform-api-2", ready=False)], "2 pods, 1 Ready"),
        ([pod("platform-api-1"), pod("platform-api-2", image="sha256:bbb")], "2 Ready, 2 images"),
        ([pod("platform-api-1")], "1 pods, 1 Ready"),
    ],
)
def test_prod_waits_while_its_pods_are_not_one_ready_set(repo, pods, says):
    st = state({"platform-api-1": WITH, "platform-api-2": WITH}, pods=[pods])
    out, calls = run(repo, "apply", st)
    assert out.returncode == 0 and applied(calls) == STG
    assert says in out.stdout and "the PROD pipeline waits" in out.stdout


def test_prod_waits_while_one_pod_lacks_the_field(repo):
    # Review 500 B2: every replica is asked on its own, not the Service, which answers from any.
    out, calls = run(repo, "apply", state({"platform-api-1": WITH, "platform-api-2": WITHOUT}))
    assert out.returncode == 0 and applied(calls) == STG
    assert "pod platform-api-2 does not report agentrt_schema_applied" in out.stdout
    asked = [c for c in calls if c.startswith("get --raw")]
    assert [c.split("/")[-3].split(":")[0] for c in asked] == ["platform-api-1", "platform-api-2"]


def test_prod_waits_while_a_pod_cannot_be_asked(repo):
    out, calls = run(repo, "apply", state({"platform-api-1": WITH}))
    assert out.returncode == 0 and applied(calls) == STG
    assert "pod platform-api-2 could not be asked for its /health" in out.stdout


def test_prod_waits_while_a_labelled_pod_is_not_the_deployments(repo):
    # Review 503 B2: the pods counted are the Deployment's own, through its ReplicaSet.
    st = state({"platform-api-1": WITH, "platform-api-2": WITH},
               pods=[[pod("platform-api-1"), pod("platform-api-2", rs="rs-foreign")]])
    out, calls = run(repo, "apply", st)
    assert out.returncode == 0 and applied(calls) == STG
    assert "the Deployment does not own: platform-api-2" in out.stdout


@pytest.mark.parametrize(
    "later",
    [
        # the same names, another image: a container restarted and pulled a moving tag
        [pod("platform-api-1", image="sha256:bbb"), pod("platform-api-2", image="sha256:bbb")],
        # the same names, a restarted container
        [pod("platform-api-1"), pod("platform-api-2", container="containerd://c2", restarts=1)],
    ],
)
def test_the_same_pod_names_with_other_containers_stop_before_any_write(repo, later):
    # Review 503 B1: the second read compares uids, images and containers, not the names alone.
    st = state({"platform-api-1": WITH, "platform-api-2": WITH}, pods=[PODS, later])
    out, calls = run(repo, "apply", st)
    assert out.returncode == 1 and "pods changed during the checks; nothing is written" in out.stdout
    assert applied(calls) == []


def test_a_change_while_stg_is_applied_leaves_prods_pipeline_out(repo):
    # Review 503 B2: read again right before PROD's pipeline, after STG's four files.
    st = state({"platform-api-1": WITH, "platform-api-2": WITH},
               pods=[PODS, PODS, [pod("platform-api-1", image="sha256:bbb"), pod("platform-api-2", image="sha256:bbb")]])
    out, calls = run(repo, "apply", st)
    assert out.returncode == 1 and "so PROD's pipeline is not applied" in out.stdout
    assert applied(calls) == STG
    assert "applied: " + " ".join(STG) in out.stdout


def test_every_read_before_the_writes_is_bounded(repo):
    out, calls = run(repo, "apply", ALL_WITH)
    assert out.returncode == 0, out.stdout + out.stderr
    reads = [c for c in calls if c.startswith(("get ", "auth can-i "))]
    assert reads and all(c.endswith(" --request-timeout=20s") for c in reads)


def test_an_identity_that_cannot_ask_prods_pods_stops_before_anything(repo):
    out, calls = run(repo, "apply", ALL_WITH, cannot="get pods --subresource=proxy -n bifrost-platform-prod")
    assert out.returncode == 1 and "cannot get pods --subresource=proxy" in out.stdout
    assert all(c.startswith("auth can-i") for c in calls)


def test_pods_that_change_during_the_checks_stop_before_any_write(repo):
    st = state({"platform-api-1": WITH, "platform-api-2": WITH},
               pods=[PODS, [pod("platform-api-1"), pod("platform-api-3")]])
    out, calls = run(repo, "apply", st)
    assert out.returncode == 1 and "pods changed during the checks" in out.stdout
    assert applied(calls) == []


def test_a_failed_apply_names_what_went_and_says_rerun(repo):
    out, calls = run(repo, "apply", apply_fails=STG[2])
    assert out.returncode == 1
    assert "applied before it: " + STG[0] + " " + STG[1] in out.stdout
    assert "Run apply again at commit" in out.stdout and "it is safe" in out.stdout


def test_usage(repo):
    out, _ = run(repo, "")
    assert out.returncode == 2 and "check" in out.stdout and "apply" in out.stdout
