"""Owner 2026-11-12: bifrost-platform's main takes a change only through a pull request that
the cluster merges when the commit's CI is green. A push to refs/heads/ready/<name> asks for
it: the CI gate runs on the whole suite, and bifrost-land-platform beside it passes the
release freeze check, waits for that gate, and merges the same commit as bifrost-merger, the
only non-Owner identity on main's merge whitelist. Pinned here: who starts a landing, the
order of the three tasks, where the token is, which CI runs count, and what `land` refuses."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import yaml

from test_ci_branch_trigger import SHA, ZERO, fired, push

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "k8s/cicd/tekton/pipeline-land-platform.yaml"
CI_PIPELINE = ROOT / "k8s/cicd/tekton/pipeline-ci-platform.yaml"
TRIGGER = ROOT / "k8s/cicd/tekton/trigger-trade-ci.yaml"
MAIN = "b" * 40
REF = "refs/heads/ready/x"
BOTH = ["platform-ci-ready", "platform-land"]
REPO_URL = "http://gitea.cicd.svc.cluster.local:3000/bifrost/bifrost-platform.git"


def pipeline():
    return yaml.safe_load(PIPELINE.read_text())["spec"]


def task(name):
    (found,) = [t for t in pipeline()["tasks"] if t["name"] == name]
    return found


def land_task():
    return task("land")


# --- who starts a landing ---------------------------------------------------------


def test_a_ready_branch_of_platform_starts_ci_on_the_whole_suite_and_the_landing():
    assert fired(push("bifrost-platform", REF)) == BOTH
    assert fired(push("bifrost-platform", "refs/heads/ready/wave-2/fix.1")) == BOTH
    for ref in ["refs/heads/w/some-lane", "refs/heads/main", "refs/heads/already/x"]:
        assert not set(BOTH) & set(fired(push("bifrost-platform", ref))), ref
    for repo in ["bifrost-trade-core", "bifrost-ui", "bifrost-trade-infra"]:
        assert not set(BOTH) & set(fired(push(repo, REF))), repo


def test_a_ready_ref_that_is_not_a_plain_name_starts_nothing():
    for ref in ["refs/heads/ready/", "refs/heads/ready/a b", "refs/heads/ready/a\nb", "refs/heads/ready/a$(x)",
                "refs/heads/ready/" + "a" * 101]:
        assert fired(push("bifrost-platform", ref)) == [], ref
    assert fired(push("bifrost-platform", REF, after=ZERO)) == []


def test_the_lander_starts_no_landing():
    body = push("bifrost-platform", REF)
    body["pusher"] = {"login": "agentrt-lander"}
    assert fired(body) == []


def test_the_ready_binding_names_no_base_and_only_the_two_ready_triggers_use_it():
    docs = [d for d in yaml.safe_load_all(TRIGGER.read_text()) if d]
    (binding,) = [d for d in docs if d["metadata"]["name"] == "bifrost-gitea-push-platform-ready"]
    assert {p["name"]: p["value"] for p in binding["spec"]["params"]} == {
        "revision": "$(body.after)", "branch": "$(body.ref)"}
    (el,) = [d for d in docs if d["kind"] == "EventListener" and d["metadata"]["name"] == "bifrost-ci"]
    use = {t["name"]: t["template"]["ref"] for t in el["spec"]["triggers"]
           if any(b["ref"] == "bifrost-gitea-push-platform-ready" for b in t["bindings"])}
    assert use == {"platform-ci-ready": "bifrost-ci-platform-template", "platform-land": "bifrost-land-platform-template"}
    lands = [d["metadata"]["name"] for d in docs if d["kind"] == "TriggerTemplate"
             and "bifrost-land-platform" in json.dumps(d["spec"]["resourcetemplates"])]
    assert lands == ["bifrost-land-platform-template"]
    (ci,) = [d for d in docs if d["metadata"]["name"] == "bifrost-ci-platform-template"]
    assert {p["name"]: p.get("default") for p in ci["spec"]["params"]}["base"] == ""


# --- the pipeline's wiring ---------------------------------------------------------


def test_freeze_check_then_ci_wait_then_land():
    tasks = pipeline()["tasks"]
    assert [t["name"] for t in tasks] == ["freeze-check", "ci-wait", "land"]
    assert tasks[0]["taskRef"] == {"name": "bifrost-release-freeze-check"} and "runAfter" not in tasks[0]
    assert tasks[1]["runAfter"] == ["freeze-check"] and tasks[2]["runAfter"] == ["ci-wait"]
    assert "finally" not in pipeline()
    assert all("when" not in t and "onError" not in t and "retries" not in t for t in tasks)


def test_the_ci_pipeline_itself_is_as_it_was():
    spec = yaml.safe_load(CI_PIPELINE.read_text())["spec"]
    assert "land" not in [t["name"] for t in spec["tasks"]] and "finally" not in spec
    assert "gitea-merger" not in CI_PIPELINE.read_text()


def test_the_merger_token_is_mounted_in_the_land_task_alone():
    assert PIPELINE.read_text().count("secretName: gitea-merger") == 1
    assert land_task()["taskSpec"]["volumes"] == [{"name": "gitea-merger", "secret": {"secretName": "gitea-merger"}}]
    for name in ("freeze-check", "ci-wait"):
        assert "gitea-merger" not in json.dumps(task(name)), name
    for path in (ROOT / "k8s").rglob("*.yaml"):
        if path != PIPELINE:
            assert "gitea-merger" not in path.read_text(), path


def test_land_and_ci_wait_are_inline_and_take_the_pushed_commit():
    for name in ("ci-wait", "land"):
        assert "taskRef" not in task(name), name
    assert {p["name"]: p["value"] for p in land_task()["params"]} == {
        "commit": "$(params.revision)", "branch": "$(params.branch)"}
    assert {p["name"]: p["value"] for p in task("ci-wait")["params"]} == {"commit": "$(params.revision)"}
    script = land_task()["taskSpec"]["steps"][0]["script"]
    assert "API = 'http://gitea.cicd.svc.cluster.local:3000/api/v1/repos/bifrost/bifrost-platform'" in script
    for name in ("ci-wait", "land"):
        assert "$(params" not in task(name)["taskSpec"]["steps"][0]["script"], name


# --- which CI runs count -------------------------------------------------------------


def ci_run(state="True", scope="full", **params):
    params = {"revision": SHA, "repo-url": REPO_URL, "base": "", **params}
    status = {"results": [{"name": "api-scope", "value": scope}]}
    if state:
        status["conditions"] = [{"type": "Succeeded", "status": state}]
    return {"spec": {"pipelineRef": {"name": "bifrost-ci-platform"},
                     "params": [{"name": k, "value": v} for k, v in params.items()]}, "status": status}


def verdict(runs):
    scope = {"__name__": "ci_wait_under_test"}
    exec(task("ci-wait")["taskSpec"]["steps"][0]["script"], scope)  # noqa: S102 - our own file
    return scope["verdict"](runs, SHA)


def test_a_green_whole_suite_run_of_the_commit_counts():
    assert verdict([ci_run()]) == "green"
    assert verdict([ci_run(scope="console")]) == "green"
    assert verdict([ci_run(state="False"), ci_run()]) == "green"


@pytest.mark.parametrize("other", [
    {"revision": "c" * 40}, {"revision": "main"}, {"base": "d" * 40},
    {"repo-url": "http://elsewhere/bifrost/bifrost-platform.git"}])
def test_a_green_run_of_another_commit_repository_or_an_increment_does_not_count(other):
    assert verdict([ci_run(**other)]) == "wait"


def test_an_incremental_scope_or_another_pipeline_does_not_count():
    assert verdict([ci_run(scope="incremental")]) == "red"
    other = ci_run()
    other["spec"]["pipelineRef"]["name"] = "bifrost-ci-python"
    assert verdict([other]) == "wait"


def test_red_only_when_every_run_of_the_commit_finished_without_a_green_one():
    assert verdict([]) == "wait"
    assert verdict([ci_run(state="Unknown")]) == "wait"
    assert verdict([ci_run(state=None)]) == "wait"
    assert verdict([ci_run(state="False")]) == "red"
    assert verdict([ci_run(state="False"), ci_run(state="Unknown")]) == "wait"


# --- what the task does ----------------------------------------------------------


class Gitea:
    """A stub of the four calls. `behind`, `moved`, `exists`, `busy` shape its answers."""

    def __init__(self, **kw):
        self.kw, self.calls, self.main = kw, [], MAIN
        gitea = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def answer(self, code, body):
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                gitea.calls.append(("GET", self.path, None, self.headers.get("Authorization")))
                if self.path == "/branches/main":
                    return self.answer(200, {"commit": {"id": gitea.main}})
                return self.answer(200, [gitea.pull()])

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                gitea.calls.append(("POST", self.path, body, self.headers.get("Authorization")))
                if self.path == "/pulls":
                    return self.answer(409, {"message": "exists"}) if kw.get("exists") else self.answer(201, gitea.pull())
                if kw.get("busy", 0) > 0:
                    kw["busy"] -= 1
                    return self.answer(405, {"message": "Please try again later"})
                if kw.get("deny"):
                    return self.answer(403, {"message": "not on the whitelist"})
                gitea.main = body["head_commit_id"]
                return self.answer(200, None)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def pull(self):
        return {"number": 7, "head": {"ref": "ready/x", "sha": "c" * 40 if self.kw.get("moved") else SHA},
                "base": {"ref": "main"}, "merge_base": "d" * 40 if self.kw.get("behind") else MAIN}

    def merges(self):
        return [c for c in self.calls if c[1] == "/pulls/7/merge"]


def run_land(gitea, ref=REF, commit=SHA):
    script = land_task()["taskSpec"]["steps"][0]["script"]
    fixed = "API = 'http://gitea.cicd.svc.cluster.local:3000/api/v1/repos/bifrost/bifrost-platform'"
    assert script.count(fixed) == 1
    scope = {"__name__": "land_under_test"}
    exec(script.replace(fixed, "API = 'http://127.0.0.1:%d'" % gitea.server.server_address[1]), scope)  # noqa: S102
    try:
        return scope["land"]("tok", ref, commit, tries=3, pause=0)
    finally:
        gitea.server.shutdown()


def test_a_green_branch_on_top_of_main_is_merged_as_the_same_commit():
    gitea = Gitea()
    assert run_land(gitea) == ""
    (merge,) = gitea.merges()
    assert merge[2] == {"Do": "rebase", "head_commit_id": SHA, "delete_branch_after_merge": True}
    assert {c[3] for c in gitea.calls} == {"token tok"}
    assert gitea.calls[0][2]["head"] == "ready/x" and gitea.calls[0][2]["base"] == "main"


def test_an_open_pull_request_for_the_branch_is_used():
    gitea = Gitea(exists=True)
    assert run_land(gitea) == ""
    assert len(gitea.merges()) == 1


def test_gitea_still_checking_is_waited_for():
    gitea = Gitea(busy=2)
    assert run_land(gitea) == ""
    assert len(gitea.merges()) == 3


@pytest.mark.parametrize("kw, word", [({"behind": True}, "behind main"), ({"moved": True}, "branch moved")])
def test_a_branch_behind_main_or_moved_since_the_run_is_not_merged(kw, word):
    gitea = Gitea(**kw)
    assert word in run_land(gitea)
    assert gitea.merges() == []


def test_a_refusal_by_gitea_is_reported_and_not_retried():
    gitea = Gitea(deny=True)
    assert "merge failed (403" in run_land(gitea)
    assert len(gitea.merges()) == 1


def test_gitea_never_ready_is_a_refusal():
    gitea = Gitea(busy=9)
    assert "did not accept" in run_land(gitea)


@pytest.mark.parametrize("ref, commit", [("refs/heads/main", SHA), ("refs/heads/w/x", SHA), ("ready/x", SHA),
                                         ("refs/heads/ready/a b", SHA), (REF, "main"), (REF, "")])
def test_anything_but_a_ready_ref_and_a_full_commit_calls_nothing(ref, commit):
    gitea = Gitea()
    assert run_land(gitea, ref, commit).startswith("refused")
    assert gitea.calls == []
