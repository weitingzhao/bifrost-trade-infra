"""The STG platform delivery starts fewer pods and loses no check.

Owner 2026-11-15, five-step method (question, delete, simplify, then accelerate): of 172 s on
the critical path of the STG delivery 54 s were pod starts of tasks doing 0–2 s of work.

What changed in k8s/cicd/tekton/pipeline-deliver-platform.yaml: mirror-sync is gone (Gitea is
the primary of all three repositories since 2026-10-17, the task fetched nothing) and the two
stage-*-dockerfile tasks are the first step of the build Tasks. What these tests hold: nothing
can start unless freeze-check succeeded, the builds still take their Dockerfile from this
run's infra clone, and every task name and result that the platform and the PROD pipeline
read is still there.
"""

import copy
from pathlib import Path

import pytest
import yaml

import freeze_chain

ROOT = Path(__file__).resolve().parents[2]
TEKTON = ROOT / "k8s/cicd/tekton"
PIPELINE = TEKTON / "pipeline-deliver-platform.yaml"

# Tasks that change something outside the run: a push to the registry (the builds push
# :stg-candidate), STG's database, the running tags, the Argo application, the Deployments.
CHANGES_STATE = [
    "build-platform-api",
    "build-platform-console",
    "agentrt-migrate",
    "promote-images",
    "gitops-sync",
    "rollout",
]


def spec(path=PIPELINE):
    return yaml.safe_load(path.read_text())["spec"]


def tasks(pipeline_spec=None):
    return {t["name"]: t for t in (pipeline_spec or spec())["tasks"]}


def task_object(filename):
    docs = [d for d in yaml.safe_load_all((TEKTON / filename).read_text()) if d and d["kind"] == "Task"]
    assert len(docs) == 1, filename
    return docs[0]


def before(pipeline, name):
    """Every task a task waits for through runAfter, directly or through others."""
    seen, todo = set(), list(pipeline[name].get("runAfter", []))
    while todo:
        t = todo.pop()
        if t not in seen:
            seen.add(t)
            todo.extend(pipeline[t].get("runAfter", []))
    return seen


def unguarded(pipeline_spec):
    """Why this pipeline could change state while frozen; empty when it cannot."""
    found = []
    p = tasks(pipeline_spec)
    if pipeline_spec.get("finally"):
        found.append("finally tasks run whatever freeze-check said")
    freeze = p.get("freeze-check")
    if freeze is None:
        return found + ["no freeze-check"]
    if freeze.get("taskRef") != {"name": "bifrost-release-freeze-check"}:
        found.append("freeze-check is not the shared Task")
    # onError: continue would let the run go on after a refusal; a when could skip the check,
    # and tasks that only wait for a skipped task (runAfter) still run.
    for key in ("onError", "when", "runAfter", "retries"):
        if key in freeze:
            found.append("freeze-check has " + key)
    for name, task in p.items():
        if name == "freeze-check":
            continue
        if "freeze-check" not in before(p, name):
            found.append(name + " does not wait for freeze-check")
    return found


def test_the_removed_tasks_are_gone_and_no_other_task_went_with_them():
    assert list(tasks()) == [
        "freeze-check",
        "clone-infra",
        "clone-platform",
        "clone-ui",
        "build-platform-api",
        "build-platform-console",
        "agentrt-migrate",
        "promote-images",
        "gitops-sync",
        "rollout",
    ]
    # No inline task is left: the two stage tasks were the only ones.
    assert not [name for name, t in tasks().items() if "taskSpec" in t]
    assert "finally" not in spec()


def test_nothing_that_changes_state_can_start_unless_freeze_check_succeeded():
    p = tasks()
    assert unguarded(spec()) == []
    for name in CHANGES_STATE:
        assert "freeze-check" in before(p, name), name
    # freeze-check is the only task that starts on its own: every path from a root passes
    # through it, which is what scripts/release/freeze_chain.py (the repository's own
    # checker, a trust anchor) holds every pipeline to.
    assert [name for name, t in p.items() if not t.get("runAfter")] == ["freeze-check"]
    for name in p:
        if name != "freeze-check":
            assert "freeze-check" in before(p, name), name
    assert [v for v in freeze_chain.violations_under(TEKTON) if v.startswith("bifrost-deliver-platform:")] == []


def test_the_order_after_the_builds_is_what_it_was():
    p = tasks()
    assert p["agentrt-migrate"]["runAfter"] == ["build-platform-api", "clone-ui"]
    assert set(p["promote-images"]["runAfter"]) == {"agentrt-migrate", "build-platform-console"}
    assert p["gitops-sync"]["runAfter"] == ["promote-images"]
    assert p["rollout"]["runAfter"] == ["gitops-sync"]
    for name in ("promote-images", "gitops-sync", "rollout"):
        params = {x["name"]: x["value"] for x in p[name]["params"]}
        assert params["apiDigest"] == "$(tasks.build-platform-api.results.digest)", name
        assert params["consoleDigest"] == "$(tasks.build-platform-console.results.digest)", name


# Positive controls for unguarded(): each is this pipeline with one thing wrong.
def _start_beside_freeze(name):
    def change(s):
        tasks(s)[name].pop("runAfter")
    return change


def _continue_on_refusal(s):
    tasks(s)["freeze-check"]["onError"] = "continue"


def _skip_the_check(s):
    tasks(s)["freeze-check"]["when"] = [{"input": "a", "operator": "in", "values": ["b"]}]


def _finally(s):
    s["finally"] = [copy.deepcopy(tasks(s)["promote-images"])]


def _other_freeze_task(s):
    tasks(s)["freeze-check"]["taskRef"] = {"name": "bifrost-smoke"}


@pytest.mark.parametrize(
    "change, why",
    [
        (_start_beside_freeze("clone-infra"), "clone-infra does not wait for freeze-check"),
        (_start_beside_freeze("build-platform-api"), "build-platform-api does not wait for freeze-check"),
        (_start_beside_freeze("promote-images"), "promote-images does not wait for freeze-check"),
        (_continue_on_refusal, "freeze-check has onError"),
        (_skip_the_check, "freeze-check has when"),
        (_finally, "finally tasks run whatever freeze-check said"),
        (_other_freeze_task, "freeze-check is not the shared Task"),
    ],
)
def test_the_freeze_guard_sees_a_pipeline_that_could_change_state_while_frozen(change, why):
    s = spec()
    change(s)
    assert why in unguarded(s)


def test_tasks_after_an_unguarded_task_are_not_called_guarded_by_it():
    s = spec()
    for name in ("clone-infra", "clone-platform", "clone-ui"):
        _start_beside_freeze(name)(s)
    found = unguarded(s)
    assert {n + " does not wait for freeze-check" for n in CHANGES_STATE} <= set(found)


def test_the_builds_get_their_dockerfile_from_this_runs_infra_clone():
    p = tasks()
    clone = p["clone-infra"]
    assert clone["taskRef"] == {"name": "bifrost-git-clone-gitea"}
    assert {x["name"]: x["value"] for x in clone["params"]} == {
        "url": "$(params.giteaBase)/bifrost-trade-infra.git",
        "revision": "$(params.infraRevision)",
        "subdir": "bifrost-trade-infra",
    }
    assert clone["workspaces"] == [{"name": "output", "workspace": "build-context"}]
    for kind in ("api", "console"):
        build = p["build-platform-" + kind]
        want = ["clone-platform", "clone-ui", "clone-infra"] if kind == "console" else ["clone-platform", "clone-infra"]
        assert build["runAfter"] == want, kind
        assert build["workspaces"] == [{"name": "source", "workspace": "build-context"}]
        # The pipeline does not point the build at another Dockerfile.
        assert [x["name"] for x in build["params"]] == ["image"]
        task = task_object("task-kaniko-platform-%s-stg.yaml" % kind)["spec"]
        filename = "Dockerfile.platform-%s-stg" % kind
        stage, check, kaniko = task["steps"]
        assert (stage["name"], check["name"], kaniko["name"]) == ("stage-dockerfile", "assert-context", "build-and-push")
        assert all("onError" not in step for step in task["steps"])
        # The copy the pipeline task stage-<kind>-dockerfile made, line for line.
        assert stage["image"] == "alpine:3.20"
        assert stage["script"] == (
            "#!/usr/bin/env sh\n"
            "set -eu\n"
            'cp "$(workspaces.source.path)/bifrost-trade-infra/k8s/cicd/docker/%(f)s" "$(workspaces.source.path)/%(f)s"\n'
            'echo "=== %(f)s from this run\'s infra clone ==="\n'
            'cat "$(workspaces.source.path)/%(f)s"\n' % {"f": filename}
        )
        assert {x["name"]: x.get("default") for x in task["params"]}["dockerfile"] == filename
        assert "--dockerfile=$(params.dockerfile)" in kaniko["args"]
        assert "--context=$(workspaces.source.path)" in kaniko["args"]


# What reads this pipeline's runs by task name. Platform paths are in bifrost-platform
# api/internal/delivery at origin/main of 2026-11-15; the PROD reader is check-source in
# pipeline-deliver-platform-prod.yaml.
#   task name: (taskRef the reader insists on or None, results it reads, who reads)
READ_BY_NAME = {
    # stg_run_evidence.go Content (taskRef, url param, commit); stg_external.go;
    # PROD check-source stg_of / stg_child (clone-platform and clone-ui commit).
    "clone-platform": ("bifrost-git-clone-gitea", ["commit"]),
    "clone-ui": ("bifrost-git-clone-gitea", ["commit"]),
    "clone-infra": ("bifrost-git-clone-gitea", ["commit"]),
    # stg_run_evidence.go Content (taskRef, digest).
    "build-platform-api": ("bifrost-kaniko-platform-api-stg", ["digest"]),
    "build-platform-console": ("bifrost-kaniko-platform-console-stg", ["digest"]),
    # stg_run_evidence.go Content (taskRef and the four params); taskRunSpecs
    # (stg_execution.go stgExecutionV1, service.go platformTaskRunSpecs); phase GitOps.
    "gitops-sync": ("bifrost-argocd-pin-sync-platform", []),
    # PROD check-source (api-digest, console-digest); taskRunSpecs; phase Rollout.
    "rollout": ("bifrost-rollout-verify-platform", ["api-digest", "console-digest"]),
    # taskRunSpecs (stgExecutionV1; service.go platformDeclaredDeliverTasks) and the
    # admission policy k8s/platform-rbac/40-admission.yaml (tekton-deliver by task name).
    "agentrt-migrate": ("bifrost-agentrt-migrate-stg", []),
    # task-release-freeze-check.yaml: in-flight runs are listed by this task's result.
    "freeze-check": ("bifrost-release-freeze-check", ["passed_cut_at"]),
}
TASK_FILES = {
    "bifrost-git-clone-gitea": "task-git-clone-gitea.yaml",
    "bifrost-kaniko-platform-api-stg": "task-kaniko-platform-api-stg.yaml",
    "bifrost-kaniko-platform-console-stg": "task-kaniko-platform-console-stg.yaml",
    "bifrost-argocd-pin-sync-platform": "task-argocd-pin-sync-platform.yaml",
    "bifrost-rollout-verify-platform": "task-rollout-verify-platform.yaml",
    "bifrost-agentrt-migrate-stg": "task-agentrt-migrate-stg.yaml",
    "bifrost-release-freeze-check": "task-release-freeze-check.yaml",
}


def test_task_names_and_results_that_the_platform_and_prod_read_are_unchanged():
    p = tasks()
    for name, (ref, results) in READ_BY_NAME.items():
        assert name in p, name
        # The platform's evidence refuses an inline task and any taskRef but the plain name.
        assert "taskSpec" not in p[name], name
        assert p[name]["taskRef"] == {"name": ref}, name
        declared = [r["name"] for r in task_object(TASK_FILES[ref])["spec"].get("results", [])]
        for result in results:
            assert result in declared, (name, result)
    for repo, name in (("bifrost-platform", "clone-platform"), ("bifrost-ui", "clone-ui"), ("bifrost-trade-infra", "clone-infra")):
        params = {x["name"]: x["value"] for x in p[name]["params"]}
        assert params["url"] == "$(params.giteaBase)/%s.git" % repo
    assert {x["name"]: x.get("default") for x in spec()["params"]}["giteaBase"] == "http://gitea.cicd.svc.cluster.local:3000/bifrost"
    # What the STG evidence compares the gitops-sync TaskRun's params with.
    assert {x["name"]: x["value"] for x in p["gitops-sync"]["params"]} == {
        "application": "bifrost-platform-stg",
        "apiDigest": "$(tasks.build-platform-api.results.digest)",
        "consoleDigest": "$(tasks.build-platform-console.results.digest)",
        "deliverRun": "$(context.pipelineRun.name)",
    }
    # The PROD pipeline's source gate reads these three of the STG run by name.
    prod = (TEKTON / "pipeline-deliver-platform-prod.yaml").read_text()
    for needle in ('stg_child(run, "clone-platform", "clone")', 'stg_child(stg, "clone-ui", "UI clone")', 'stg_child(stg, "rollout", "rollout")'):
        assert needle in prod, needle


def test_the_tasks_that_run_as_tekton_deliver_keep_their_names_in_the_admission_policy():
    # The platform names these three in the run's taskRunSpecs; the admission policy admits
    # tekton-deliver for exactly these names of this pipeline. A merged or renamed task would
    # be refused at run creation (Tekton refuses taskRunSpecs that name an absent task).
    policy = (ROOT / "k8s/platform-rbac/40-admission.yaml").read_text()
    for name in ("rollout", "gitops-sync", "agentrt-migrate"):
        assert name in tasks()
        assert "'bifrost-deliver-platform/%s'" % name in policy
    assert "'bifrost-deliver-platform/promote-images'" not in policy
