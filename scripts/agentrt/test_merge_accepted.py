"""merge_accepted: what the runtime accepted, read from its records; the merge built on main with
the attempt's author and trailers; the line it does not cross; the list of what is not on main.

    python3 -m pytest -q scripts/agentrt/test_merge_accepted.py

Git runs on repositories in a temporary directory (the origin a bare one beside them): no network.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge_accepted as ma  # noqa: E402

RealRuntime = ma.Runtime

TASK = "t_01M5B8BF2EM3SJQDKZ9E9TY2H8"
REVIEW = "t_01M5B8BF2EM3SJQDKZ9E9TY2H9"
ATTEMPT = "a_01M5B90JM164EEEKTVETQ166EA"


@pytest.fixture(autouse=True)
def identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for k, v in {"GIT_COMMITTER_NAME": "coordinator", "GIT_COMMITTER_EMAIL": "coordinator@example.invalid"}.items():
        monkeypatch.setenv(k, v)
    for k in ("CLAUDE_CODE_HOST_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL"):
        monkeypatch.delenv(k, raising=False)


def sh(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True,
                          env={**os.environ, **(env or {})}).stdout


AGENTD = {"GIT_AUTHOR_NAME": "agentd agent-06", "GIT_AUTHOR_EMAIL": "agentd@agent-06"}
MESSAGE = ("cluster: delete ExecSQLOnPrimary (TD-268)\n\nThe body says why.\n\n"
           f"Agentrt-Task: {TASK}\nChange-Id: I9436d586cce64a2c17e1a45aae79674bb4d7ccf8\nWork: W-31\n")


class World:
    """A workspace with one repository whose origin is a bare repository beside it, main with one
    commit, and the accepted attempt's branch on origin."""

    def __init__(self, root: Path, repo: str = "bifrost-ui", files: dict[str, str] | None = None):
        self.root, self.repo = root, repo
        self.ws = root / "ws"
        self.origin = root / "origin" / (repo + ".git")
        self.origin.parent.mkdir(parents=True)
        sh(root, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.dir = self.ws / repo
        self.ws.mkdir()
        sh(self.ws, "clone", "-q", str(self.origin), repo)
        (self.dir / "a.txt").write_text("one\n")
        sh(self.dir, "add", "a.txt")
        sh(self.dir, "commit", "-q", "-m", "base", env={**AGENTD, "GIT_AUTHOR_NAME": "someone"})
        sh(self.dir, "push", "-q", "origin", "HEAD:refs/heads/main")
        self.base = sh(self.dir, "rev-parse", "HEAD").strip()
        for name, text in (files if files is not None else {"a.txt": "two\n"}).items():
            (self.dir / name).write_text(text)
        sh(self.dir, "add", "-A")
        sh(self.dir, "commit", "-q", "--allow-empty", "-m", MESSAGE, env=AGENTD)
        self.commit = sh(self.dir, "rev-parse", "HEAD").strip()
        self.ref = f"refs/heads/agent/{TASK}/a2"
        sh(self.dir, "push", "-q", "origin", f"HEAD:{self.ref}")
        sh(self.dir, "reset", "-q", "--hard", self.base)

    def main_moves(self, name: str = "b.txt") -> None:
        """Another commit lands on main after the attempt's base."""
        (self.dir / name).write_text("other\n")
        sh(self.dir, "add", name)
        sh(self.dir, "commit", "-q", "-m", "other work")
        sh(self.dir, "push", "-q", "origin", "HEAD:refs/heads/main")

    def runtime(self, state: str = "accepted", txid: bool = True, extra: dict | None = None) -> ma.Runtime:
        extra = extra or {}
        rows = {
            f"tasks/{TASK}": {"task_id": TASK, "role": "implement", "state": state, "repo": self.repo, "mission_id": "M-9",
                              "base_commit": self.base, "title": "delete ExecSQLOnPrimary"},
            f"attempts/{ATTEMPT}": {"attempt_id": ATTEMPT, "attempt_no": 2, "executor_actor_id": "exec:codex",
                                    "pushed_ref": self.ref, "pushed_commit": self.commit},
            "missions/M-9": {"mission_id": "M-9", "work_id": "W-31", "title": "four small jobs"},
        }
        events = [
            {"seq": 1, "event_type": "attempt_leased", "task_id": REVIEW, "body_json": {"executor": "exec:claude"}, "txid": 1},
            {"seq": 2, "event_type": "attempt_leased", "task_id": REVIEW, "body_json": {"executor": "exec:cursor"}, "txid": 2},
            {"seq": 3, "event_type": "verification_recorded", "task_id": TASK, "attempt_id": ATTEMPT,
             "body_json": {"method": "deterministic", "verdict": "pass"}, "txid": 3},
            {"seq": 4, "event_type": "verification_recorded", "task_id": TASK, "attempt_id": ATTEMPT,
             "body_json": {"method": "review", "verdict": "pass"}, "txid": 9 if txid else None},
            {"seq": 5, "event_type": "task_state_changed", "task_id": REVIEW, "body_json": {"to": "accepted"}, "txid": 9 if txid else None},
            {"seq": 6, "event_type": "task_state_changed", "task_id": TASK, "body_json": {"to": "accepted"}, "txid": 9 if txid else None,
             "at": "2026-10-20T00:02:41.123456+00:00"},
        ]

        def get(path: str) -> object:
            if path.startswith("events?"):
                return [] if "after_seq" in path else events
            if path.startswith("tasks?"):
                if "state=accepted" in path:
                    return {"tasks": [rows[f"tasks/{TASK}"]] if "mission=M-9" in path and state == "accepted" else [], "truncated": False}
                return {"tasks": [rows[f"tasks/{TASK}"], {"task_id": REVIEW, "role": "review", "state": "accepted",
                                                         "subject_task_id": TASK}], "truncated": False}
            if path in rows:
                return rows[path]
            if path.startswith("missions/M-") and int(path.rsplit("-", 1)[1]) < 9:
                return {"mission_id": path.split("/")[1], "title": "an earlier mission"}  # numbered from M-1
            if path in extra:
                return extra[path]
            if path.startswith(("missions/", "tasks/")):
                raise urllib.error.HTTPError(path, 404, "not found", None, None)  # type: ignore[arg-type]
            raise AssertionError(path)
        return RealRuntime("prod", get)


def test_reads_the_accepted_attempt_and_its_reviewer(tmp_path: Path) -> None:
    w = World(tmp_path)
    a = ma.accepted(w.runtime(), TASK)
    assert (a.attempt, a.attempt_no, a.author, a.commit, a.ref) == (ATTEMPT, 2, "exec:codex", w.commit, w.ref)
    # The review accepted in the pass's transaction; its last attempt's executor.
    assert a.reviewers == ["exec:cursor"] and a.mission_label == "W-31" and a.accepted_at.startswith("2026-10-20T00:02")


def test_without_transactions_any_accepted_review_names_its_last_executor(tmp_path: Path) -> None:
    assert ma.accepted(World(tmp_path).runtime(txid=False), TASK).reviewers == ["exec:cursor"]


def test_refuses_what_is_not_an_accepted_implementation(tmp_path: Path) -> None:
    with pytest.raises(ma.Refused, match="is rework, not accepted"):
        ma.accepted(World(tmp_path).runtime(state="rework"), TASK)


def test_message_says_where_it_came_from_and_keeps_its_trailers(tmp_path: Path) -> None:
    w = World(tmp_path)
    msg = ma.message(MESSAGE, ma.accepted(w.runtime(), TASK))
    assert msg == ("cluster: delete ExecSQLOnPrimary (TD-268)\n\nThe body says why.\n\n"
                   f"Written by the agent runtime: PROD M-9 (W-31), task {TASK}, attempt 2 {ATTEMPT} (exec:codex), "
                   "reviewed by exec:cursor and accepted 2026-10-20 00:02Z. Until the release queue, the coordinator "
                   "merges accepted results with scripts/agentrt/merge_accepted.py (TD-383).\n\n"
                   f"(cherry picked from commit {w.commit})\n\n"
                   f"Agentrt-Task: {TASK}\nChange-Id: I9436d586cce64a2c17e1a45aae79674bb4d7ccf8\nWork: W-31, TD-383\n")
    # Merged again (amended, say), TD-383 is not added twice.
    assert ma.message(msg, ma.accepted(w.runtime(), TASK)).count("TD-383\n") == 1


def test_a_subject_that_names_only_the_task_takes_its_title(tmp_path: Path) -> None:
    msg = ma.message(f"agentrt: {TASK} attempt 2\n\nAgentrt-Task: {TASK}\nChange-Id: I1\nWork: unassigned\n",
                     ma.accepted(World(tmp_path).runtime(), TASK))
    assert msg.startswith("delete ExecSQLOnPrimary\n\nWritten by the agent runtime:") and msg.endswith("Work: TD-383\n")


@pytest.mark.parametrize("original", ["subject only\n", "subject\n\nbody, no trailers\n", "subject\n\nWork: W-31\n"])
def test_message_refuses_a_commit_without_the_runtime_trailers(tmp_path: Path, original: str) -> None:
    with pytest.raises(ma.Refused):
        ma.message(original, ma.accepted(World(tmp_path).runtime(), TASK))


def test_plan_lists_the_files_and_builds_on_main_with_the_author(tmp_path: Path) -> None:
    w = World(tmp_path)
    w.main_moves()
    a, files, msg = ma.plan(w.runtime(), TASK, w.ws)
    assert files == ["a.txt"]
    tree = ma.build(a, msg, w.ws, tmp_path / "merge")
    head = sh(tree, "log", "-1", "--format=%an <%ae>%x00%P%x00%B").split("\x00")
    main = sh(w.dir, "rev-parse", "origin/main").strip()
    assert head[0] == "agentd agent-06 <agentd@agent-06>" and head[1] == main and head[2].strip() == msg.strip()
    assert (tree / "a.txt").read_text() == "two\n" and (tree / "b.txt").exists()


def test_build_adds_the_merging_thread_when_there_is_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if not (ma.INFRA / "agent-config" / "scripts" / "git-hooks" / "lineage.sh").is_file():
        pytest.skip("no lineage.sh in this checkout")
    monkeypatch.setenv("CLAUDE_CODE_HOST_SESSION_ID", "local_test")
    w = World(tmp_path)
    a, _, msg = ma.plan(w.runtime(), TASK, w.ws)
    body = sh(ma.build(a, msg, w.ws, tmp_path / "merge"), "log", "-1", "--format=%B")
    assert "Claude-Session: local_test" in body and body.count("Change-Id:") == 1 and f"Agentrt-Task: {TASK}" in body


def test_plan_refuses_a_task_already_on_main(tmp_path: Path) -> None:
    w = World(tmp_path)
    sh(w.dir, "fetch", "-q", "origin", w.ref)
    sh(w.dir, "cherry-pick", w.commit)
    sh(w.dir, "push", "-q", "origin", "HEAD:refs/heads/main")
    with pytest.raises(ma.Refused, match="already on bifrost-ui main"):
        ma.plan(w.runtime(), TASK, w.ws)


def test_plan_refuses_an_empty_change(tmp_path: Path) -> None:
    w = World(tmp_path, files={})
    with pytest.raises(ma.Refused, match="changes nothing"):
        ma.plan(w.runtime(), TASK, w.ws)


def test_build_refuses_a_change_that_does_not_apply(tmp_path: Path) -> None:
    w = World(tmp_path)
    w.main_moves("a.txt")
    a, _, msg = ma.plan(w.runtime(), TASK, w.ws)
    with pytest.raises(ma.Refused, match="does not apply"):
        ma.build(a, msg, w.ws, tmp_path / "merge")


def test_only_repositories_whose_main_deploys_nothing_may_be_pushed() -> None:
    assert ma.may_push("bifrost-platform")[0] and ma.may_push("bifrost-ui")[0]
    ok, why = ma.may_push("bifrost-trade-infra")
    assert not ok and "Argo" in why and "agent-config" in why
    assert not ma.may_push("bifrost-research")[0] and not ma.may_push("bifrost-trade-api")[0]


def test_suite_runs_ci_then_code_health_and_names_what_failed(tmp_path: Path) -> None:
    ran: list[tuple[list[str], dict[str, str]]] = []

    def run(cmd: list[str], cwd: Path, env: dict[str, str]) -> int:
        ran.append((cmd, env))
        return 1 if "lint" in cmd or "code-health" in " ".join(cmd) else 0
    failed = ma.run_suite(tmp_path / "bifrost-platform", "bifrost-platform", run)
    assert ran[0][0][:5] == ["go", "-C", "api", "test", "./..."] and ran[0][1]["BIFROST_CI"] == "1"
    assert ran[-1][0][-2:] == ["--repo", "bifrost-platform"] and ran[-1][0][2:4] == ["--root", str(tmp_path)]
    assert failed == ["npm --prefix console run lint", "code-health"]
    assert ma.run_suite(tmp_path, "bifrost-trade-infra", run) == []


def test_list_names_what_is_accepted_and_not_on_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    w = World(tmp_path)
    assert ma.cmd_list(w.runtime(), w.ws) == 1
    out = capsys.readouterr().out
    assert f"bifrost-ui\tM-9\t{TASK}\tattempt 2 (exec:codex) {w.commit[:12]}" in out and "1 accepted implementation(s)" in out
    sh(w.dir, "fetch", "-q", "origin", w.ref)
    sh(w.dir, "cherry-pick", w.commit)
    sh(w.dir, "push", "-q", "origin", "HEAD:refs/heads/main")
    assert ma.cmd_list(w.runtime(), w.ws) == 0


def test_list_passes_over_an_empty_change(tmp_path: Path) -> None:
    w = World(tmp_path, files={})
    assert ma.cmd_list(w.runtime(), w.ws) == 0


def test_apply_pushes_only_with_push_and_only_where_it_may(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pushed: list[Path] = []
    monkeypatch.setattr(ma, "SUITES", {})
    monkeypatch.setattr(ma, "CODE_HEALTH", set())
    monkeypatch.setattr(ma, "push", pushed.append)
    for repo, push, rc, n in [("bifrost-ui", False, 0, 0), ("bifrost-ui", True, 0, 1), ("bifrost-trade-infra", True, 3, 1)]:
        w = World(tmp_path / f"{repo}-{push}", repo=repo)
        monkeypatch.setattr(ma, "Runtime", lambda env, w=w: w.runtime())
        monkeypatch.setattr(ma, "workspace", lambda w=w: w.ws)
        args = ["apply", TASK, "--dir", str(w.root / "merge")] + (["--push"] if push else [])
        assert ma.main(args) == rc and len(pushed) == n


def knows_nothing(path: str) -> object:
    """A runtime with no row at all: every read is 404."""
    raise urllib.error.HTTPError(path, 404, "not found", None, None)  # type: ignore[arg-type]


CANCELLED = "t_01M5B8BF2EM3SJQDKZ9E9TY2HA"
UNKNOWN = "t_01M5B8BF2EM3SJQDKZ9E9TY2HB"


def test_prunable_follows_td383s_rule(tmp_path: Path) -> None:
    w = World(tmp_path, repo="bifrost-platform")
    for ref in (f"refs/heads/agent/{TASK}/a1", f"refs/heads/agent/{CANCELLED}/a1", f"refs/heads/agent/{UNKNOWN}/a3"):
        sh(w.dir, "push", "-q", "origin", f"{w.base}:{ref}")
    prod = w.runtime(extra={f"tasks/{CANCELLED}": {"task_id": CANCELLED, "state": "cancelled"}})
    stg = RealRuntime("stg", knows_nothing)
    now = time.time()

    def decisions(at: float) -> dict[str, tuple[str, bool, str]]:
        return {ref.rsplit("/", 2)[-2][-2:] + "/" + ref.rsplit("/", 1)[-1]: (env, go, why)
                for ref, env, go, why in ma.prunable({"prod": prod, "stg": stg}, w.dir, at)}
    fresh = decisions(now)
    assert all(not go for _, go, _ in fresh.values()), fresh
    late = decisions(now + 8 * 86400)
    assert late["H8/a1"] == ("prod", True, "superseded: attempt 2 was accepted")
    assert late["H8/a2"] == ("prod", False, "its accepted result is not on main")
    assert late["HA/a1"] == ("prod", True, "its task is cancelled")
    assert late["HB/a3"] == ("", False, "no task of this id in prod or stg")
    # Merged: every branch of the task goes.
    sh(w.dir, "fetch", "-q", "origin", w.ref)
    sh(w.dir, "cherry-pick", w.commit)
    sh(w.dir, "push", "-q", "origin", "HEAD:refs/heads/main")
    merged = decisions(now + 8 * 86400)
    assert merged["H8/a2"][1] and merged["H8/a2"][2].startswith("its task is accepted and on main as ") and merged["H8/a1"][1]
