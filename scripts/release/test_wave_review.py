"""wave_review.py against a recorded snapshot of cleanup wave 2 (2026-11-12); no cluster.

The fixture is the script's own snapshot, cut to the runs created 16:20-16:45Z, main's
first-parent history since 11-12 00:00 CT and cards #460-#466 (trimmed fields).
"""
import copy
import json
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
M = runpy.run_path(str(HERE / "wave_review.py"))
FIXTURE = HERE / "fixtures" / "wave-review" / "cleanup-wave-2.json"
WAVE2_SHAS = ["ab4c2fba", "06c63320", "568cc4ab", "f3bc0a69"]


def snap():
    return json.loads(FIXTURE.read_text())


def review(shas=WAVE2_SHAS, since="2026-11-12 08:51", until="2026-11-12 10:47", cards="460-466", data=None):
    data = data or snap()
    since, until = M["parse_time"](since), M["parse_time"](until)
    runs = M["select"](data["runs"], since, until, shas)
    picked = M["pick_cards"](data["approvals"], M["card_range"](cards), since, until)
    summary = M["summarize"](runs, picked, data["git"], since, until)
    return runs, summary, M["render"]("t", data, runs, summary, since, until, shas)


def test_wave_two_matches_the_hand_made_table():
    runs, s, md = review()
    assert len(runs) == 19
    assert M["span"](s["first_ci_to_prod_s"]) == "17m01s"
    assert s["platform_ci_full"] == ["ci-platform-hwsrs"]
    assert s["platform_ci_reused"] == ["ci-platform-vjljb"]
    assert sorted(n for n, _ in s["infra_ci"]) == ["ci-infra-bmzkq", "ci-infra-dphhq", "ci-infra-lc4k9"]
    assert [n for n, r in s["infra_ci"] if r != "Succeeded"] == ["ci-infra-dphhq"]
    assert [(n, M["span"](d)) for n, d, _ in s["stg"]] == [("bifrost-deliver-platform-1794501356", "4m57s")]
    assert [(n, M["span"](d)) for n, d, _ in s["prod"]] == [
        ("bifrost-deliver-platform-prod-eee1641584dde920-1", "1m11s")]
    assert (s["apply_plan"], s["apply_apply"]) == (6, 6)
    assert [c["number"] for c in s["cards"]] == list(range(460, 467))
    assert "apply_manifest ×6, start_pipeline_run ×1" in md
    assert "on the Mac terminal (runner owner): 0" in md
    assert sorted(s["pushes"]["infra"]) == ["ci-infra-bmzkq", "ci-infra-dphhq", "ci-infra-lc4k9"]
    assert s["pushes"]["platform"] == ["ci-platform-vjljb"]
    assert "| ci-platform-vjljb | ci-platform | ab4c2fba | 11-12 10:35:10 | 0m25s | Succeeded | yes / ci-platform-hwsrs | full |" in md
    assert "| ci-platform-hwsrs | ci-platform | ab4c2fba | 11-12 10:26:51 | 7m20s | Succeeded | no / - | full |" in md
    assert "no record: push-main.sh keeps no log" in md


def test_a_window_alone_also_lists_another_thread_s_landing_run():
    runs, s, _ = review(shas=[])
    assert s["landing_ci"] == ["landing-ci-be6694c106ced7cf8927659c-1"]
    assert len(runs) == 20


def test_commits_alone_pick_the_wave_and_the_branch_push_is_not_a_main_push():
    data = snap()
    runs = M["select"](data["runs"], None, None, WAVE2_SHAS)
    s = M["summarize"](runs, [], data["git"], None, None)
    assert len(runs) == 19
    assert "ci-platform-hwsrs" not in s["pushes"]["platform"]  # base 0000: a new branch


def test_expired_window_says_so():
    data = snap()
    data["oldest_run"] = "2026-11-12T16:00:00Z"
    runs, _, md = review(shas=["f9315a0c", "8ec87181"], since="2026-11-11 22:35", until="2026-11-11 23:53",
                         cards="", data=data)
    assert runs == []
    assert "**Run records expired**" in md and "none were found" in md


def test_cards_without_records_are_listed_by_number():
    data = snap()
    data["approvals"] = []
    _, s, md = review(cards="460-462,#466", data=data)
    assert [c["number"] for c in s["cards"]] == [460, 461, 462, 466]
    assert "types unknown" in md


def test_times_default_to_chicago():
    assert M["iso"](M["parse_time"]("2026-11-12 08:51")) == "2026-11-12T14:51:00Z"
    assert M["iso"](M["parse_time"]("2026-11-12T14:51:00Z")) == "2026-11-12T14:51:00Z"
    assert M["span"](3725) == "1h02m05s"


def test_trim_keeps_the_review_fields_and_reuse_comes_from_the_reuse_task():
    raw = {"metadata": {"name": "ci-platform-x", "creationTimestamp": "2026-11-12T16:00:00Z",
                        "labels": {"tekton.dev/pipeline": "bifrost-ci-platform", "other": "dropped"},
                        "annotations": {"bifrost.io/approval-id": "appr_1"}},
           "spec": {"params": [{"name": "revision", "value": "abc"}, {"name": "repo-url", "value": "dropped"}]},
           "status": {"startTime": "2026-11-12T16:00:01Z", "completionTime": "2026-11-12T16:01:01Z",
                      "conditions": [{"reason": "Succeeded"}],
                      "results": [{"name": "api-scope", "value": "full"}, {"name": "platform-tree", "value": "t"}]}}
    run = M["trim_run"](raw)
    assert run["params"] == {"revision": "abc"} and run["results"] == {"api-scope": "full"}
    assert run["labels"] == {} and run["approval"] == "appr_1"
    reuse = M["reuse_results"]({"items": [{"metadata": {"labels": {"tekton.dev/pipelineRun": "ci-platform-x"}},
                                           "status": {"results": [{"name": "reuse", "value": "yes"},
                                                                  {"name": "tested-by", "value": "ci-platform-y"}]}}]})
    run["reuse"] = reuse["ci-platform-x"]
    assert M["reuse_of"](run) == ("yes", "ci-platform-y")
    assert M["duration"](run) == 60


def test_earlier_snapshots_fill_in_runs_the_cluster_deleted(tmp_path):
    old = snap()
    (tmp_path / "2026-11-12T170000Z-old.json").write_text(json.dumps(old))
    (tmp_path / "notes.txt").write_text("ignored")
    live = copy.deepcopy(old)
    live["runs"] = [r for r in live["runs"] if not r["name"].startswith("ci-infra-")]
    live["oldest_run"] = "2026-11-12T16:30:00Z"
    merged = M["merge_archive"](live, tmp_path)
    assert merged["archive_runs"] == 3
    assert merged["archive_oldest_run"] == old["oldest_run"]
    assert {r["name"] for r in merged["runs"]} == {r["name"] for r in old["runs"]}


def test_cli_from_snapshot_writes_json_and_no_archive(tmp_path, capsys):
    out = tmp_path / "summary.json"
    rc = M["main"](["--from-snapshot", str(FIXTURE), "--since", "2026-11-12 08:51", "--until", "2026-11-12 10:47",
                    "--cards", "460-466", "--archive", str(tmp_path / "archive"), "--json-out", str(out),
                    *[x for s in WAVE2_SHAS for x in ("--sha", s)]])
    assert rc == 0
    assert "| first CI start → PROD done | 17m01s" in capsys.readouterr().out
    assert json.loads(out.read_text())["summary"]["platform_ci"] == 2
    assert not (tmp_path / "archive").exists()
