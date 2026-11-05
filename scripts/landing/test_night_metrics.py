"""S0b night metrics: fixtures only, no cluster, database or network."""
import json
import runpy
from argparse import Namespace
from pathlib import Path

import pytest

N = runpy.run_path(str(Path(__file__).with_name("night_metrics.py")))
F = runpy.run_path(str(Path(__file__).with_name("night_fetch.py")))
NIGHT = "2026-11-03"  # 05:00Z .. 15:00Z, handover to 18:00Z (CST, UTC-6)
OLD, MID, NEW, TIP = "a" * 40, "b" * 40, "c" * 40, "d" * 40


def at(hhmm, day="2026-11-04"):
    return f"{day}T{hhmm}:00Z"


def pipeline_run(name, rev, created, completed, status="True", base="", fail=None, reason=None):
    reason = reason or {"True": "Succeeded", "False": "Failed"}.get(status, "Running")
    return {"name": name, "created": created, "completed": completed, "status": status, "reason": reason,
            "params": {"revision": rev, "base": base}, "results": {}, "fail": fail}


def commit_of(sha, committed, landed=""):
    return {"sha": sha, "committed": committed, "authored": committed, "subject": sha[:4], "landed_by": landed}


def event_of(event_id, when, stream, **body):
    return {"event_id": event_id, "at": when, "stream": stream, "body": body}


def snapshot_of(runs=(), commits=(), events=(), tasks=(), checks=(), questions=None, fetched=at("23:00")):
    return {"schema": N["SNAPSHOT"], "fetched_at": fetched, "since": at("00:00", "2026-11-01"),
            "sources": {"runs": "ok", "git": "ok", "db": "ok"}, "runs": list(runs),
            "git": {"commits": list(commits)},
            "db": {"events": list(events), "tasks": list(tasks), "verifications": list(checks)},
            "questions": questions, "approvals": None}


def history():
    """OLD red before the night; MID green created 07:00, done 07:04; NEW red created 10:00, done 10:03."""
    commits = [commit_of(NEW, at("09:59")), commit_of(MID, at("06:59")), commit_of(OLD, at("03:00"))]
    runs = [pipeline_run("ci-old", OLD, at("03:00"), at("03:01"), "False"),
            pipeline_run("ci-mid", MID, at("07:00"), at("07:04"), base=OLD),
            pipeline_run("ci-new", NEW, at("10:00"), at("10:03"), "False", base=MID)]
    return runs, commits


def test_windows_follow_us_central_time():
    assert N["night_windows"](NIGHT) == {
        "night": (N["moment_of"](at("05:00")), N["moment_of"](at("15:00"))),
        "handover": (N["moment_of"](at("15:00")), N["moment_of"](at("18:00")))}
    before = N["night_windows"]("2026-10-30")
    assert [N["iso_z"](t) for t in before["night"]] == ["2026-10-31T04:00:00Z", "2026-10-31T14:00:00Z"]
    across = N["night_windows"]("2026-10-31")  # clocks go back during this night: it lasts 11 hours
    assert [N["iso_z"](t) for t in across["night"]] == ["2026-11-01T04:00:00Z", "2026-11-01T15:00:00Z"]
    spring = N["night_windows"]("2026-03-07")  # clocks go forward: 9 hours
    assert [N["iso_z"](t) for t in spring["night"]] == ["2026-03-08T05:00:00Z", "2026-03-08T14:00:00Z"]


def test_red_time_has_two_clocks_and_is_clipped_to_the_segment():
    runs, commits = history()
    night = N["compute_all"](snapshot_of(runs, commits), NIGHT)["segments"]["night"]["main_red"]
    # proxy: red 05:00-07:00 and 10:00-15:00; terminal: red 05:00-07:04 and 10:03-15:00
    assert night["proxy"]["red_s"] == 7 * 3600
    assert night["terminal"]["red_s"] == 2 * 3600 + 4 * 60 + 4 * 3600 + 57 * 60
    assert night["proxy"]["spans"][0] == {"from": at("05:00"), "to": at("07:00"), "state": "red",
                                         "runs": ["ci-old"]}
    handover = N["compute_all"](snapshot_of(runs, commits), NIGHT)["segments"]["handover"]["main_red"]
    assert handover["proxy"]["red_s"] == handover["terminal"]["red_s"] == 3 * 3600


def test_window_counts_by_start_time_and_cuts_at_the_edges():
    commits = [commit_of(TIP, at("14:59")), commit_of(NEW, at("04:59")), commit_of(OLD, at("03:00"))]
    runs = [pipeline_run("ci-before", OLD, at("04:50"), at("04:55"), "False"),
            pipeline_run("ci-start", NEW, at("05:00"), at("05:04"), base=OLD),
            pipeline_run("ci-end", TIP, at("15:00"), at("15:04"), "False", base=NEW)]
    seg = N["compute_all"](snapshot_of(runs, commits), NIGHT)["segments"]
    assert [r["run"] for r in seg["night"]["main_ci"]["runs"]] == ["ci-start"]
    assert [r["run"] for r in seg["handover"]["main_ci"]["runs"]] == ["ci-end"]
    assert seg["night"]["main_red"]["proxy"]["red_s"] == 0
    assert seg["night"]["main_red"]["terminal"]["red_s"] == 4 * 60
    assert seg["handover"]["main_red"]["terminal"]["red_s"] == 3 * 3600 - 4 * 60


def test_an_older_revision_rerun_does_not_set_mains_state():
    commits = [commit_of(NEW, at("06:00")), commit_of(OLD, at("03:00"))]
    runs = [pipeline_run("ci-new", NEW, at("06:00"), at("06:04"), "False", base=OLD),
            pipeline_run("ci-old-again", OLD, at("08:00"), at("08:04"))]
    red = N["compute_all"](snapshot_of(runs, commits), NIGHT)["segments"]["night"]["main_red"]
    assert red["terminal"]["red_s"] == 8 * 3600 + 56 * 60  # 06:04-15:00: the green rerun of OLD is ignored
    assert red["terminal"]["unknown_s"] == 3600 + 4 * 60


def test_time_before_the_oldest_kept_run_is_unknown_not_green():
    commits = [commit_of(NEW, at("08:00"))]
    runs = [pipeline_run("ci-new", NEW, at("08:00"), at("08:04"), "False")]
    red = N["compute_all"](snapshot_of(runs, commits), NIGHT)["segments"]["night"]["main_red"]["proxy"]
    assert red["unknown_s"] == 3 * 3600 and red["red_s"] == 7 * 3600
    cancelled = [dict(runs[0], status="False", reason="Cancelled")]
    none = N["compute_all"](snapshot_of(cancelled, commits), NIGHT)["segments"]["night"]["main_red"]["proxy"]
    assert none["unknown_s"] == 10 * 3600 and none["red_s"] == 0


def landing(op, kind, when, eid, **extra):
    return event_of(eid, when, "landing:bifrost-trade-infra", landing=dict(op=op, kind=kind, **extra))


def task_of(task_id, created, state="accepted", repo="bifrost-trade-infra"):
    return {"task_id": task_id, "repo": repo, "state": state, "created_at": created, "updated_at": created,
            "title": task_id, "plan_node_id": None, "round_no": 1}


def test_unfinished_deliveries_count_at_their_age_at_handover_end():
    events = [landing("land:t_quick:1", "awaiting_grant", at("06:30"), 1),
              landing("land:t_quick:1", "landed", at("09:00"), 2),
              landing("land:t_no:1", "failed", at("16:00"), 3, why="declined"),
              landing("land:t_late:1", "landed", at("19:00"), 4)]
    tasks = [task_of("t_late", at("06:00")), task_of("t_quick", at("06:00")), task_of("t_no", at("07:00")),
             task_of("t_evening", at("04:00")), task_of("t_morning", at("16:00"))]
    checks = [{"verification_id": "v_1", "task_id": "t_quick", "method": "review", "verdict": "fail",
               "created_at": at("06:10")},
              {"verification_id": "v_2", "task_id": "t_quick", "method": "review", "verdict": "pass",
               "created_at": at("06:20")},
              {"verification_id": "v_3", "task_id": "t_late", "method": "review", "verdict": "pass",
               "created_at": at("06:10")}]
    dl = N["compute_all"](snapshot_of(events=events, tasks=tasks, checks=checks), NIGHT)["deliveries"]
    rows = {i["task"]: i for i in dl["items"]}
    assert set(rows) == {"t_late", "t_quick", "t_no"}
    assert rows["t_late"]["status"] == "open" and rows["t_late"]["wait_s"] == 12 * 3600
    assert rows["t_quick"]["status"] == "landed" and rows["t_quick"]["wait_s"] == 3 * 3600
    assert rows["t_quick"]["grant_wait_s"] == 2.5 * 3600
    assert rows["t_no"]["status"] == "closed_unlanded" and rows["t_no"]["wait_s"] == 11 * 3600
    assert dl["landed_by_handover_end"] == 1 and dl["completion"] == pytest.approx(1 / 3)
    assert dl["wait_s"] == {"p50": 11 * 3600, "p90": 12 * 3600, "max": 12 * 3600, "open_counted_at_age": 2}
    assert dl["review_first_pass"] == {"rate": 0.5, "reviewed": 2, "without_review": 1}
    assert dl["min_sample_ok"] is True
    assert {b["task"] for b in dl["backlog_at_end"]} == {"t_late", "t_evening", "t_morning"}
    assert dl["backlog_night_deliveries"] == 1


def test_missing_sources_are_unknown_never_zero():
    snap = snapshot_of()
    snap["runs"], snap["db"], snap["sources"] = None, None, {"runs": "error: x", "git": "ok", "db": "error: y"}
    res = N["compute_all"](snap, NIGHT)
    night = res["segments"]["night"]
    assert "unknown" in night["main_ci"] and "unknown" in night["main_red"] and "unknown" in night["landings"]
    assert "unknown" in night["landing_cards"] and "unknown" in res["deliveries"]
    assert night["other_cards"]["questions"] == {"unknown": "question list not given"}
    empty = N["compute_all"](snapshot_of(), NIGHT)["deliveries"]
    assert empty["n"] == 0 and empty["completion"] is None and empty["min_sample_ok"] is False
    assert empty["wait_s"]["p50"] is None and empty["wait_s"]["max"] is None
    assert empty["review_first_pass"]["rate"] is None
    assert "Unknown" in N["render_md"](res)


def test_owner_pushes_repair_rules_and_landing_attribution():
    line = "FAIL unregistered_consumer k8s/x.py:9"
    commits = [commit_of(TIP, at("16:30"), landed="agentrt-prod/land:t_x:1"), commit_of(NEW, at("15:10")),
               commit_of(MID, at("13:00")), commit_of(OLD, at("03:00"))]
    runs = [pipeline_run("ci-old", OLD, at("03:00"), at("03:01"), "False", fail={"lines": [line]}),
            pipeline_run("landing-ci-infra-1", "e" * 40, at("06:00"), at("06:01"), "False", base=OLD,
                         fail={"step": "consumers", "lines": [line], "source": "pod-log"}),
            pipeline_run("ci-new", NEW, at("15:20"), at("15:24"), base=OLD),
            pipeline_run("ci-tip", TIP, at("16:40"), at("16:44"), base=NEW)]
    events = [landing("land:t_a:1", "ci_seen", at("06:00"), 1, run="landing-ci-infra-1"),
              landing("land:t_a:1", "failed", at("06:01"), 2, why="ci_red"),
              event_of(3, at("06:02"), "landing-cards:bifrost-trade-infra",
                       landing_card_prepared={"prep": "card:2", "op": "land:t_a:1", "kind": "root_failed"}),
              event_of(4, at("06:02"), "landing-cards:bifrost-trade-infra",
                       landing_card={"prep": "card:2", "question_id": "q_1"})]
    questions = [{"id": "q_1", "number": 102, "created_at": at("06:02"), "answered_at": at("15:21"),
                  "answer_option": "b", "title": "Landing failed", "task_id": "t_a"}]
    seg = N["compute_all"](snapshot_of(runs, commits, events, questions=questions), NIGHT)["segments"]
    failed = seg["night"]["landings"]["runs"][0]
    assert failed["op"] == "land:t_a:1" and failed["vs_base"] == "same_first_line_as_base"
    assert failed["base_run"] == "ci-old"
    assert seg["night"]["landing_cards"]["cards"][0] | {} == {
        "question": "q_1", "number": 102, "repo": "bifrost-trade-infra", "op": "land:t_a:1",
        "kind": "root_failed", "at": at("06:02"), "answered_at": at("15:21"), "answer": "b"}
    pushes = seg["handover"]["owner_pushes"]
    assert pushes["count"] == 1 and pushes["repair_rule_a"] == ["ci-new"] == pushes["repair_rule_b"]
    owner = pushes["pushes"][0]
    assert owner["commits"] == 2 and owner["base"] == OLD[:10] and owner["base_state"] == "red"
    assert [c["sha"] for c in owner["night_commits"]] == [MID[:10]]
    assert [p["by"] for p in pushes["pushes"]] == ["owner", "landing"]


def kubectl_runner(calls, logs):
    def respond(argv, stdin=None):
        calls.append(argv)
        if "pipelinerun" in argv:
            item = {"metadata": {"name": "ci-x", "uid": "u", "creationTimestamp": at("06:00"),
                                 "labels": {"bifrost.io/purpose": "push"}},
                    "spec": {"params": [{"name": "revision", "value": NEW}]},
                    "status": {"conditions": [{"status": "False", "reason": "Failed"}],
                               "completionTime": at("06:01")}}
            return json.dumps({"items": [item]})
        if "taskrun" in argv:
            steps = [{"name": "tools", "container": "step-tools", "terminated": {"exitCode": 0}},
                     {"name": "consumers", "container": "step-consumers", "terminated": {"exitCode": 1}},
                     {"name": "quick", "container": "step-quick", "terminated": {"exitCode": 1}}]
            return json.dumps({"items": [
                {"metadata": {"labels": {"tekton.dev/pipelineTask": "check"}},
                 "status": {"podName": "p", "steps": steps}},
                {"metadata": {"labels": {"tekton.dev/pipelineTask": "clone"}},
                 "status": {"podName": "c", "steps": [{"name": "clone", "terminated": {"exitCode": 0}}]}}]})
        return logs
    return respond


def test_fetch_reads_the_first_failing_step_and_keeps_unread_sources_null(monkeypatch):
    calls = []
    args = Namespace(kubectl="kubectl", namespace="cicd", kubeconfig="kc", no_logs=False)
    since, until = N["moment_of"](at("00:00")), N["moment_of"](at("23:00"))
    rows = F["fetch_runs"](args, since, until, kubectl_runner(calls, "ok\nFAIL unregistered_consumer a.py:1\nE  x\n"))
    assert rows[0]["fail"] == {"task": "check", "step": "consumers", "source": "pod-log",
                               "lines": ["FAIL unregistered_consumer a.py:1", "E  x"]}
    assert calls[-1][-2:] == ["-c", "step-consumers"] and all("--kubeconfig" in c for c in calls)
    monkeypatch.delenv("KUBECONFIG", raising=False)
    with pytest.raises(F["FetchError"]):
        F["fetch_runs"](Namespace(kubectl="kubectl", namespace="cicd", kubeconfig=None, no_logs=True),
                        since, until, kubectl_runner([], ""))
    missing = Namespace(since=at("00:00"), until=None, kubectl="kubectl", namespace="cicd", kubeconfig=None,
                        no_logs=True, git_repo="/nonexistent-s0b", git_ref="origin/main", git_depth=5,
                        psql="/nonexistent-s0b/psql", pg="", questions=None, approvals=None)
    snap = F["snapshot"](missing, N["moment_of"](at("23:00")))
    assert snap["runs"] is None and snap["git"] is None and snap["db"] is None
    assert snap["sources"]["questions"] == "not given" and snap["sources"]["runs"].startswith("error:")


def test_compute_command_reads_only_the_snapshot(tmp_path, capsys):
    runs, commits = history()
    path = tmp_path / "snap.json"
    path.write_text(json.dumps(snapshot_of(runs, commits)))
    assert N["main"](["--snapshot", str(path), "--night", NIGHT, "--json", str(tmp_path / "r.json")]) == 0
    assert "| main_red | proxy: 7.00 h |" in capsys.readouterr().out
    assert json.loads((tmp_path / "r.json").read_text())["version"] == N["VERSION"]
    path.write_text(json.dumps({"schema": "other"}))
    assert N["main"](["--snapshot", str(path), "--night", NIGHT]) == 2
