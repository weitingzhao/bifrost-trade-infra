"""Owner 2026-11-12 / 2026-11-13: main takes a change only through a pull request that the
cluster merges when the commit's CI is green. A push to refs/heads/ready/<name> asks for it:
the repository's CI gate runs on the whole suite, and bifrost-land beside it passes the
release freeze check, opens the pull request, has Gitea rebase a branch that is behind main,
waits for that gate, and merges the same commit as bifrost-merger, the only non-Owner identity
on main's merge whitelist. There is one landing pipeline for every repository; what differs is
a row in LANDING_REPOS (pipeline-land.yaml). Pinned here: that there is only one, who starts a landing, where
the token is, which CI runs count, and what `land` refuses."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import yaml

from test_ci_branch_trigger import SHA, ZERO, fired, filters, push

ROOT = Path(__file__).resolve().parents[2]
TEKTON = ROOT / "k8s/cicd/tekton"
PIPELINE = TEKTON / "pipeline-land.yaml"
CI_PIPELINE = TEKTON / "pipeline-ci-platform.yaml"
TRIGGER = TEKTON / "trigger-trade-ci.yaml"
MAIN = "b" * 40
REF = "refs/heads/ready/x"
PLATFORM = "bifrost-platform"
INFRA = "bifrost-trade-infra"


def pipeline():
    return yaml.safe_load(PIPELINE.read_text())["spec"]


def table():
    """LANDING_REPOS: the one place a repository's landing facts are written."""
    (value,) = [e["value"] for e in land_task()["taskSpec"]["steps"][0]["env"] if e["name"] == "LANDING_REPOS"]
    return json.loads(value)


def policy():
    """The policy as release.sh policy sign writes it: the template with paths.json merged in."""
    return {"paths": json.loads((ROOT / "agent-config/release-policy/paths.json").read_text())["paths"]}


def guard_paths(repo):
    """One concrete path for each glob of the signed group, read and not copied."""
    return [p.replace("**", "x.yaml") for group in policy()["paths"]["no_d10_paths"] if group["repo"] == repo
            for p in group["paths"]]


def land_task():
    (found,) = [t for t in pipeline()["tasks"] if t["name"] == "land"]
    return found


def script():
    return land_task()["taskSpec"]["steps"][0]["script"]


def module():
    scope = {"__name__": "land_under_test"}
    exec(script(), scope)  # noqa: S102 - our own file
    return scope


# --- there is one landing pipeline --------------------------------------------------


def tekton_docs():
    for name in sorted(os.listdir(TEKTON)):
        if name.endswith(".yaml"):
            for doc in yaml.safe_load_all((TEKTON / name).read_text()):
                if isinstance(doc, dict):
                    yield name, doc


MIGRATING = True  # platform still lands through bifrost-land-platform; False in the next commit


def test_one_pipeline_holds_the_merger_token_and_none_is_named_for_a_repository():
    """A copy of the landing pipeline for one more repository fails here, under any name:
    what marks a landing pipeline is that it can reach the merging account's token.
    The mistake this answers: 2026-11-12 built a landing pipeline named for one repository,
    and the Owner's word on 2026-11-13 was that reaching more repositories extends what
    exists and does not copy it."""
    old = [("pipeline-land-platform.yaml", "bifrost-land-platform")] if MIGRATING else []
    holders = sorted({(name, doc["metadata"]["name"]) for name, doc in tekton_docs()
                      if "gitea-merger" in json.dumps(doc) and doc["kind"] != "ConfigMap"})
    assert holders == sorted(old + [("pipeline-land.yaml", "bifrost-land")])
    lands = sorted(doc["metadata"]["name"] for _, doc in tekton_docs()
                   if doc["kind"] == "Pipeline" and doc["metadata"]["name"].startswith("bifrost-land"))
    assert lands == sorted(["bifrost-land"] + [name for _, name in old])
    assert sorted(n for n in os.listdir(TEKTON) if n.startswith("pipeline-land")) == sorted(
        ["pipeline-land.yaml"] + [name for name, _ in old])


def landing_templates():
    docs = [d for d in yaml.safe_load_all(TRIGGER.read_text()) if d]
    return docs, [d["metadata"]["name"] for d in docs if d["kind"] == "TriggerTemplate"
                  and '"name": "bifrost-land' in json.dumps(d["spec"]["resourcetemplates"])]


def test_one_trigger_and_one_template_start_it_and_the_trigger_names_no_repository():
    docs, templates = landing_templates()
    assert sorted(templates) == (["bifrost-land-platform-template"] if MIGRATING else []) + ["bifrost-land-template"]
    (el,) = [d for d in docs if d["kind"] == "EventListener" and d["metadata"]["name"] == "bifrost-ci"]
    assert [t["name"] for t in el["spec"]["triggers"] if t["template"]["ref"] == "bifrost-land-template"] == ["land"]
    named = " && body.repository.name != 'bifrost-platform'" if MIGRATING else ""
    assert " ".join(filters()["land"].split()).endswith("body.repository.name.matches('^[a-z0-9-]{1,100}$')" + named)
    assert "bifrost-" not in filters()["land"].replace(named.strip(" &"), "")


def test_the_pipeline_names_no_repository_and_every_row_is_complete():
    assert not [repo for repo in table() if repo in script()]
    assert set(table()) == {PLATFORM, INFRA}
    mounted = {v["secret"]["secretName"] for v in land_task()["taskSpec"]["volumes"] if "secret" in v}
    for repo, entry in table().items():
        assert module()["row"](table(), repo) == entry, repo
        assert isinstance(entry["ci"]["pipeline"], str) and (TEKTON / ("pipeline-" + entry["ci"]["pipeline"][8:] + ".yaml")).exists()
        assert {entry["merger"]} == mounted, repo
    for name in ("bifrost-ui", "", "Bifrost-Platform", "bifrost-platform/x", None, 7):
        assert module()["row"](table(), name) is None, name


# --- who starts a landing ---------------------------------------------------------


def test_a_ready_branch_starts_the_landing_and_for_platform_ci_on_the_whole_suite():
    both = ["platform-ci-ready", "platform-land"] if MIGRATING else ["land", "platform-ci-ready"]
    assert fired(push(PLATFORM, REF)) == both
    assert fired(push(PLATFORM, "refs/heads/ready/wave-2/fix.1")) == both
    for ref in ["refs/heads/w/some-lane", "refs/heads/main", "refs/heads/already/x"]:
        assert not set(both + ["land"]) & set(fired(push(PLATFORM, ref))), ref
    body = push(INFRA, REF)
    body["repository"]["full_name"] = "bifrost/" + INFRA
    assert fired(body) == ["infra-ci", "land"]
    for ref in ["refs/heads/w/some-lane", "refs/heads/main", "refs/heads/already/x"]:
        assert "land" not in fired(push(INFRA, ref)), ref


def test_a_ready_ref_or_repository_name_that_is_not_plain_starts_nothing():
    for ref in ["refs/heads/ready/", "refs/heads/ready/a b", "refs/heads/ready/a\nb", "refs/heads/ready/a$(x)",
                "refs/heads/ready/" + "a" * 101]:
        assert fired(push(PLATFORM, ref)) == [], ref
        assert "land" not in fired(push(INFRA, ref)), ref
    assert fired(push(PLATFORM, REF, after=ZERO)) == [] and "land" not in fired(push(INFRA, REF, after=ZERO))
    for repo in ["bifrost platform", "bifrost-platform;x", "$(id)", "a/b", ""]:
        assert "land" not in fired(push(repo, REF)), repo


def test_the_lander_starts_no_landing():
    for repo in (PLATFORM, INFRA):
        body = push(repo, REF)
        body["pusher"] = {"login": "agentrt-lander"}
        assert not {"land", "platform-land"} & set(fired(body)), repo


def test_the_ready_binding_and_template_pass_on_the_repository_commit_and_branch():
    docs = [d for d in yaml.safe_load_all(TRIGGER.read_text()) if d]
    (binding,) = [d for d in docs if d["metadata"]["name"] == "bifrost-gitea-push-ready"]
    assert {p["name"]: p["value"] for p in binding["spec"]["params"]} == {
        "repo": "$(body.repository.name)", "revision": "$(body.after)", "branch": "$(body.ref)"}
    (el,) = [d for d in docs if d["kind"] == "EventListener" and d["metadata"]["name"] == "bifrost-ci"]
    use = {t["name"]: t["template"]["ref"] for t in el["spec"]["triggers"]
           if any(b["ref"] == "bifrost-gitea-push-ready" for b in t["bindings"])}
    ci = {} if MIGRATING else {"platform-ci-ready": "bifrost-ci-platform-template"}
    assert use == {**ci, "land": "bifrost-land-template"}
    (template,) = [d for d in docs if d["metadata"]["name"] == "bifrost-land-template"]
    run = template["spec"]["resourcetemplates"][0]["spec"]
    assert run["pipelineRef"] == {"name": "bifrost-land"}
    assert {p["name"]: p["value"] for p in run["params"]} == {
        "repo": "$(tt.params.repo)", "revision": "$(tt.params.revision)", "branch": "$(tt.params.branch)"}
    assert run["taskRunSpecs"] == [{"pipelineTaskName": "land", "serviceAccountName": "tekton-platform-ci-reuse"}]


def test_an_infra_ready_run_is_judged_against_main():
    """The gap of 2026-11-13: a first push of a branch skipped two stages and took its own
    check scripts. The clone task now takes main as the base of a commit that heads a ready/
    branch (scripts/landing/test_ci_infra_transport.py runs it), and the landing counts a run
    only when that base is main's head. Neither the run's params nor the CI pipeline change:
    the platform starts the same pipeline and pins both."""
    spec = yaml.safe_load((TEKTON / "pipeline-ci-infra.yaml").read_text())["spec"]
    assert {"name": "base-commit", "value": "$(tasks.clone.results.base-commit)"} in spec["results"]
    (check,) = [t for t in spec["tasks"] if t["name"] == "check"]
    assert {"name": "base", "value": "$(tasks.clone.results.base-commit)"} in check["params"]
    assert table()[INFRA]["ci"] == {"pipeline": "bifrost-ci-infra", "params": {"purpose": "push"},
                                    "base_result": "base-commit"}


# --- the pipeline's wiring ---------------------------------------------------------


def test_freeze_check_then_land():
    tasks = pipeline()["tasks"]
    assert [t["name"] for t in tasks] == ["freeze-check", "land"]
    assert tasks[0]["taskRef"] == {"name": "bifrost-release-freeze-check"} and "runAfter" not in tasks[0]
    assert tasks[1]["runAfter"] == ["freeze-check"]
    assert "finally" not in pipeline()
    assert all("when" not in t and "onError" not in t and "retries" not in t for t in tasks)


def test_the_ci_pipeline_itself_is_as_it_was():
    spec = yaml.safe_load(CI_PIPELINE.read_text())["spec"]
    assert "land" not in [t["name"] for t in spec["tasks"]] and "finally" not in spec


def test_land_is_inline_takes_the_pushed_commit_and_talks_to_gitea_only():
    assert "taskRef" not in land_task()
    assert {p["name"]: p["value"] for p in land_task()["params"]} == {
        "repo": "$(params.repo)", "commit": "$(params.revision)", "branch": "$(params.branch)"}
    assert "GITEA = 'http://gitea.cicd.svc.cluster.local:3000'" in script()
    assert "$(params" not in script() and "$(tasks" not in script()
    assert pipeline()["results"] == [{"name": "outcome", "description": pipeline()["results"][0]["description"],
                                      "value": "$(tasks.land.results.outcome)"}]


# --- which CI runs count -------------------------------------------------------------


def ci_run(state="True", scope="full", **params):
    params = {"revision": SHA, **table()[PLATFORM]["ci"]["params"], **params}
    status = {"results": [{"name": "api-scope", "value": scope}]}
    if state:
        status["conditions"] = [{"type": "Succeeded", "status": state}]
    return {"spec": {"pipelineRef": {"name": "bifrost-ci-platform"},
                     "params": [{"name": k, "value": v} for k, v in params.items()]}, "status": status}


def infra_run(state="True", base=MAIN, **params):
    params = {"revision": SHA, "purpose": "push", "base": "e" * 40, **params}
    status = {"results": [{"name": "base-commit", "value": base}]} if state in ("True", "False") else {}
    if state:
        status["conditions"] = [{"type": "Succeeded", "status": state}]
    return {"spec": {"pipelineRef": {"name": "bifrost-ci-infra"},
                     "params": [{"name": k, "value": v} for k, v in params.items()]}, "status": status}


def verdict(runs, repo=PLATFORM):
    return module()["verdict"](runs, SHA, table()[repo]["ci"], MAIN)


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
    assert verdict([ci_run()], INFRA) == "wait" and verdict([infra_run()]) == "wait"


def test_red_only_when_every_run_of_the_commit_finished_without_a_green_one():
    assert verdict([]) == "wait"
    assert verdict([ci_run(state="Unknown")]) == "wait"
    assert verdict([ci_run(state=None)]) == "wait"
    assert verdict([ci_run(state="False")]) == "red"
    assert verdict([ci_run(state="False"), ci_run(state="Unknown")]) == "wait"


def test_an_infra_run_counts_only_when_it_was_judged_against_main_as_it_is_now():
    assert verdict([infra_run()], INFRA) == "green"
    assert verdict([infra_run(state="False")], INFRA) == "red"
    assert verdict([infra_run(state="Unknown")], INFRA) == "wait"
    # judged against the commit the branch moved from, an older main, or nothing at all
    for base in ("e" * 40, "", None):
        assert verdict([infra_run(base=base)], INFRA) == "stale", base
        assert verdict([infra_run(state="False", base=base)], INFRA) == "stale", base
    assert verdict([infra_run(base="e" * 40), infra_run()], INFRA) == "green"
    # the platform's own landing lane runs the same pipeline with another purpose
    assert verdict([infra_run(purpose="landing")], INFRA) == "wait"


def test_ci_wait_gives_a_starting_run_time_and_then_answers():
    wait = module()["ci_wait"]
    ci = table()[INFRA]["ci"]
    seen = []

    def runs(name):
        seen.append(name)
        return [] if len(seen) < 3 else [infra_run()]

    assert wait(SHA, ci, MAIN, runs=runs, pause=0) == "green" and seen == ["bifrost-ci-infra"] * 3
    assert "no whole-suite CI run" in wait(SHA, ci, MAIN, runs=lambda n: [infra_run(state="False")], grace=-1, pause=0)
    assert wait(SHA, ci, MAIN, runs=lambda n: [infra_run(base="e" * 40)], grace=-1, pause=0) == "stale"
    assert "did not finish" in wait(SHA, ci, MAIN, runs=lambda n: [], limit=-1, pause=0)


# --- what the task does ----------------------------------------------------------


class Gitea:
    """A stub of the calls. `behind`, `moved`, `exists`, `busy`, `deny`, `conflict`,
    `files`, `bare` and `moves` shape its answers."""

    def __init__(self, **kw):
        self.kw, self.calls, self.main, self.rebased = kw, [], MAIN, False
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
                if self.path.endswith("/branches/main"):
                    return self.answer(200, {"commit": {"id": gitea.main}})
                if "/commits" in self.path:
                    trailer = "" if kw.get("bare") else "\n\nChange-Id: I" + "1" * 40
                    return self.answer(200, [{"sha": SHA, "commit": {"message": "fix: a thing" + trailer}}])
                if "/files" in self.path:
                    return self.answer(200, [{"filename": n} for n in kw.get("files", ["docs/RELEASE.md"])])
                return self.answer(200, [gitea.pull()])

            def do_POST(self):
                size = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(size)) if size else None
                gitea.calls.append(("POST", self.path, body, self.headers.get("Authorization")))
                if self.path.endswith("/pulls"):
                    return self.answer(409, {"message": "exists"}) if kw.get("exists") else self.answer(201, gitea.pull())
                if "/update" in self.path:
                    if kw.get("conflict"):
                        return self.answer(409, {"message": "rebase failed because of conflict"})
                    gitea.rebased = True
                    return self.answer(200, None)
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

    def paths(self, word):
        return [c for c in self.calls if word in c[1]]

    def merges(self):
        return self.paths("/pulls/7/merge")


def run_land(gitea, ref=REF, commit=SHA, repo=PLATFORM, wait=None):
    waits = []

    def waited(commit, ci, base):
        waits.append((ci["pipeline"], base))
        if gitea.kw.get("moves") and len(waits) == 1:
            gitea.kw["behind"] = True  # another branch landed while CI ran
            gitea.main = "f" * 40
        return "green"

    try:
        got = module()["land"]("tok", table(), policy(), repo, ref, commit, wait=wait or waited,
                               gitea="http://127.0.0.1:%d" % gitea.server.server_address[1], tries=3, pause=0)
    finally:
        gitea.server.shutdown()
    gitea.waits = waits
    return got


def test_a_green_branch_on_top_of_main_is_merged_as_the_same_commit():
    gitea = Gitea()
    assert run_land(gitea) == ("landed", "")
    (merge,) = gitea.merges()
    assert merge[2] == {"Do": "rebase", "head_commit_id": SHA, "delete_branch_after_merge": True}
    assert {c[3] for c in gitea.calls} == {"token tok"}
    assert gitea.calls[0][2]["head"] == "ready/x" and gitea.calls[0][2]["base"] == "main"
    assert {c[1].split("/pulls")[0].split("/branches")[0] for c in gitea.calls} == {"/api/v1/repos/bifrost/bifrost-platform"}
    assert gitea.waits == [("bifrost-ci-platform", MAIN)]


def test_the_same_code_lands_another_listed_repository_with_its_own_ci():
    gitea = Gitea()
    assert run_land(gitea, repo=INFRA) == ("landed", "")
    assert {c[1].split("/pulls")[0].split("/branches")[0] for c in gitea.calls} == {"/api/v1/repos/bifrost/bifrost-trade-infra"}
    assert gitea.waits == [("bifrost-ci-infra", MAIN)]


def test_an_open_pull_request_for_the_branch_is_used():
    gitea = Gitea(exists=True)
    assert run_land(gitea) == ("landed", "")
    assert len(gitea.merges()) == 1


def test_gitea_still_checking_is_waited_for():
    gitea = Gitea(busy=2)
    assert run_land(gitea) == ("landed", "")
    assert len(gitea.merges()) == 3


def test_a_branch_behind_main_is_rebased_by_gitea_before_any_ci_is_waited_for():
    gitea = Gitea(behind=True)
    assert run_land(gitea) == ("rebased", "")
    assert [c[1] for c in gitea.paths("/update")] == ["/api/v1/repos/bifrost/bifrost-platform/pulls/7/update?style=rebase"]
    assert gitea.merges() == [] and gitea.waits == []


def test_main_moving_while_ci_ran_is_a_rebase_too_and_not_a_merge():
    gitea = Gitea(moves=True)
    assert run_land(gitea) == ("rebased", "")
    assert len(gitea.waits) == 1 and len(gitea.paths("/update")) == 1 and gitea.merges() == []


def test_a_stale_ci_answer_on_an_unmoved_main_is_asked_again_and_then_refused():
    gitea = Gitea()
    outcome, problem = run_land(gitea, repo=INFRA, wait=lambda commit, ci, base: "stale")
    assert outcome == "" and "main kept moving" in problem and gitea.merges() == []


def test_a_rebase_gitea_cannot_do_is_a_refusal_that_says_what_to_do():
    gitea = Gitea(behind=True, conflict=True)
    outcome, problem = run_land(gitea)
    assert outcome == "" and "behind main" in problem and "conflict" in problem and "push ready/ again" in problem
    assert gitea.merges() == []


def test_a_branch_moved_since_the_run_is_not_merged():
    gitea = Gitea(moved=True)
    assert "branch moved" in run_land(gitea)[1]
    assert gitea.merges() == [] and gitea.paths("/update") == []


def test_a_change_to_a_trade_execution_guard_path_is_not_taken():
    """Owner 2026-11-13: trade and money stay out of this lane. The paths are the signed release
    policy's no_d10_paths group for the repository."""
    assert len(guard_paths(INFRA)) == 5
    for path in guard_paths(INFRA):
        gitea = Gitea(files=["docs/RELEASE.md", path], behind=True)
        outcome, problem = run_land(gitea, repo=INFRA)
        assert outcome == "" and path in problem and "no_d10_paths" in problem, path
        assert gitea.merges() == [] and gitea.paths("/update") == [] and gitea.waits == [], path


def test_other_paths_and_the_same_paths_in_another_repository_are_taken():
    for files, repo in ((["k8s/overlays/platform-prod/kustomization.yaml", "k8s/overlays/stg/config/x.yaml",
                          "scripts/release/release.sh"], INFRA),
                        (guard_paths(INFRA), PLATFORM)):
        gitea = Gitea(files=files)
        assert run_land(gitea, repo=repo) == ("landed", ""), files
    assert module()["guarded"](policy(), PLATFORM, set(guard_paths(PLATFORM))) == guard_paths(PLATFORM)[0]


def test_a_commit_without_a_change_id_is_refused_before_anything_is_changed():
    gitea = Gitea(bare=True, behind=True)
    outcome, problem = run_land(gitea)
    assert outcome == "" and "no Change-Id trailer" in problem and SHA[:12] in problem
    assert gitea.merges() == [] and gitea.paths("/update") == [] and gitea.waits == []


def test_a_red_or_late_ci_is_the_refusal():
    gitea = Gitea()
    assert run_land(gitea, wait=lambda commit, ci, base: "refused: no whole-suite CI run") == ("", "refused: no whole-suite CI run")
    assert gitea.merges() == []


def test_a_refusal_by_gitea_is_reported_and_not_retried():
    gitea = Gitea(deny=True)
    assert "merge failed (403" in run_land(gitea)[1]
    assert len(gitea.merges()) == 1


def test_gitea_never_ready_is_a_refusal():
    gitea = Gitea(busy=9)
    assert "did not accept" in run_land(gitea)[1]


@pytest.mark.parametrize("ref, commit, repo", [
    ("refs/heads/main", SHA, PLATFORM), ("refs/heads/w/x", SHA, PLATFORM), ("ready/x", SHA, PLATFORM),
    ("refs/heads/ready/a b", SHA, PLATFORM), (REF, "main", PLATFORM), (REF, "", PLATFORM),
    (REF, SHA, "bifrost-ui"), (REF, SHA, "bifrost-platform/../x"), (REF, SHA, "")])
def test_anything_but_a_ready_ref_a_full_commit_and_a_listed_repository_calls_nothing(ref, commit, repo):
    gitea = Gitea()
    assert run_land(gitea, ref, commit, repo)[1].startswith("refused")
    assert gitea.calls == []
