"""Owner 2026-11-12: bifrost-platform's main takes a change only through a pull request that
the CI run itself merges when it is green. A push to refs/heads/ready/<name> asks for it; the
last task of bifrost-ci-platform, holding the only non-Owner identity on main's merge
whitelist, opens the pull request and merges the commit the run tested. Pinned here: who can
start a landing run, that the task waits for every other task, where the token is, and what
the task refuses."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import yaml

from test_ci_branch_trigger import SHA, ZERO, fired, push

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "k8s/cicd/tekton/pipeline-ci-platform.yaml"
TRIGGER = ROOT / "k8s/cicd/tekton/trigger-trade-ci.yaml"
MAIN = "b" * 40
REF = "refs/heads/ready/x"


def pipeline():
    return yaml.safe_load(PIPELINE.read_text())["spec"]


def land_task():
    (task,) = [t for t in pipeline()["tasks"] if t["name"] == "land"]
    return task


# --- who starts a landing run ---------------------------------------------------


def test_only_a_ready_branch_of_platform_starts_a_landing_run():
    assert fired(push("bifrost-platform", REF)) == ["platform-ci-land"]
    assert fired(push("bifrost-platform", "refs/heads/ready/wave-2/fix.1")) == ["platform-ci-land"]
    for ref in ["refs/heads/w/some-lane", "refs/heads/main", "refs/heads/already/x"]:
        assert "platform-ci-land" not in fired(push("bifrost-platform", ref)), ref
    assert "platform-ci-land" not in fired(push("bifrost-trade-core", REF))
    assert "platform-ci-land" not in fired(push("bifrost-ui", REF))


def test_a_ready_ref_that_is_not_a_plain_name_starts_nothing():
    for ref in ["refs/heads/ready/", "refs/heads/ready/a b", "refs/heads/ready/a\nb", "refs/heads/ready/a$(x)",
                "refs/heads/ready/" + "a" * 101]:
        assert fired(push("bifrost-platform", ref)) == [], ref
    assert fired(push("bifrost-platform", REF, after=ZERO)) == []


def test_the_lander_starts_no_landing_run():
    body = push("bifrost-platform", REF)
    body["pusher"] = {"login": "agentrt-lander"}
    assert fired(body) == []


def test_only_the_landing_binding_says_land_and_it_names_no_base():
    docs = [d for d in yaml.safe_load_all(TRIGGER.read_text()) if d]
    saying = {d["metadata"]["name"]: {p["name"]: p["value"] for p in d["spec"]["params"]}
              for d in docs if d["kind"] == "TriggerBinding" and any(p["name"] == "land" for p in d["spec"]["params"])}
    assert saying == {"bifrost-gitea-push-platform-land": {
        "revision": "$(body.after)", "land": "yes", "branch": "$(body.ref)"}}
    (template,) = [d for d in docs if d["metadata"]["name"] == "bifrost-ci-platform-template"]
    defaults = {p["name"]: p.get("default") for p in template["spec"]["params"]}
    assert defaults["land"] == "no" and defaults["branch"] == "" and defaults["base"] == ""
    (el,) = [d for d in docs if d["kind"] == "EventListener" and d["metadata"]["name"] == "bifrost-ci"]
    users = [t["name"] for t in el["spec"]["triggers"]
             if any(b["ref"] == "bifrost-gitea-push-platform-land" for b in t["bindings"])]
    assert users == ["platform-ci-land"]


def test_the_pipeline_defaults_to_not_landing():
    params = {p["name"]: p["default"] for p in pipeline()["params"]}
    assert params["land"] == "no" and params["branch"] == ""


# --- the task's wiring -----------------------------------------------------------


def test_land_runs_after_every_other_task():
    others = [t["name"] for t in pipeline()["tasks"] if t["name"] != "land"]
    assert sorted(land_task()["runAfter"]) == sorted(others)
    assert pipeline()["tasks"][-1]["name"] == "land"


def test_the_merger_token_is_mounted_in_the_land_task_alone():
    text = PIPELINE.read_text()
    assert text.count("secretName: gitea-merger") == 1
    assert land_task()["taskSpec"]["volumes"] == [
        {"name": "gitea-merger", "secret": {"secretName": "gitea-merger", "optional": True}}]
    for task in pipeline()["tasks"]:
        if task["name"] != "land":
            assert "gitea-merger" not in json.dumps(task), task["name"]
    for path in (ROOT / "k8s").rglob("*.yaml"):
        if path != PIPELINE:
            assert "gitea-merger" not in path.read_text(), path


def test_land_is_inline_and_takes_the_commit_the_run_cloned():
    task = land_task()
    assert "taskRef" not in task
    assert {p["name"]: p["value"] for p in task["params"]} == {
        "commit": "$(tasks.clone.results.commit)", "branch": "$(params.branch)", "land": "$(params.land)"}
    script = task["taskSpec"]["steps"][0]["script"]
    assert "API = 'http://gitea.cicd.svc.cluster.local:3000/api/v1/repos/bifrost/bifrost-platform'" in script
    assert "$(params" not in script and "giteaBase" not in script


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
