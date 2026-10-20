"""merge_accepted: what the runtime accepted, read from its records; the merge built on main with
the attempt's author and trailers; the line it does not cross; what is not on main; which agent/
branches TD-383's rule would delete.

    python3 -m pytest -q scripts/agentrt/test_merge_accepted.py

Git runs on repositories in a temporary directory (each origin a bare one beside them); the runtime
is a dictionary. No network, no loopback.
"""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge_accepted as ma  # noqa: E402

TASK = "t_01M5B8BF2EM3SJQDKZ9E9TY2H8"
REVIEW = "t_01M5B8BF2EM3SJQDKZ9E9TY2H9"
OLD_REVIEW = "t_01M5B8BF2EM3SJQDKZ9E9TY2HC"
ATTEMPT = "a_01M5B90JM164EEEKTVETQ166EA"
EARLIER = "a_01M5B90JM164EEEKTVETQ166E9"
CANCELLED = "t_01M5B8BF2EM3SJQDKZ9E9TY2HA"
JUST_CANCELLED = "t_01M5B8BF2EM3SJQDKZ9E9TY2HD"
UNKNOWN = "t_01M5B8BF2EM3SJQDKZ9E9TY2HB"
BOTH = "t_01M5B8BF2EM3SJQDKZ9E9TY2HE"
CHANGE = "I9436d586cce64a2c17e1a45aae79674bb4d7ccf8"
NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ma.Runtime, "PAUSE", 0.0)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for k, v in {"GIT_COMMITTER_NAME": "coordinator", "GIT_COMMITTER_EMAIL": "coordinator@example.invalid"}.items():
        monkeypatch.setenv(k, v)
    for k in ("CLAUDE_CODE_HOST_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "PLATFORM_ROOT"):
        monkeypatch.delenv(k, raising=False)


def sh(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True,
                          env={**os.environ, **(env or {})}).stdout


def not_found(path: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(path, 404, "not found", None, None)  # type: ignore[arg-type]


def knows_nothing(path: str) -> object:
    """A runtime with no row at all: every read is 404."""
    raise not_found(path)


AGENTD = {"GIT_AUTHOR_NAME": "agentd agent-06", "GIT_AUTHOR_EMAIL": "agentd@agent-06"}
MESSAGE = f"cluster: delete ExecSQLOnPrimary (TD-268)\n\nThe body says why.\n\nAgentrt-Task: {TASK}\nChange-Id: {CHANGE}\nWork: W-31\n"
RealRuntime = ma.Runtime


def origin(root: Path, ws: Path, repo: str) -> Path:
    """A clone of a new bare origin, its main one commit."""
    bare = root / "origin" / (repo + ".git")
    bare.parent.mkdir(parents=True, exist_ok=True)
    sh(root, "init", "-q", "--bare", "-b", "main", str(bare))
    sh(ws, "clone", "-q", str(bare), repo)
    (ws / repo / "a.txt").write_text("one\n")
    sh(ws / repo, "add", "a.txt")
    sh(ws / repo, "commit", "-q", "-m", "base", env={**AGENTD, "GIT_AUTHOR_NAME": "someone"})
    sh(ws / repo, "push", "-q", "origin", "HEAD:refs/heads/main")
    return ws / repo


class World:
    """A workspace with one repository (and, for platform, the siblings its suite needs), main
    with one commit, and the accepted attempt's branch on origin."""

    def __init__(self, root: Path, repo: str = "bifrost-ui", files: dict[str, str] | None = None):
        self.root, self.repo = root, repo
        self.ws = root / "ws"
        self.ws.mkdir()
        self.dir = origin(root, self.ws, repo)
        for sib in ma.SIBLINGS.get(repo, []):
            origin(root, self.ws, sib)
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

    def lands(self, keep_task: bool = True) -> str:
        """The accepted commit lands on main by hand, with or without its Agentrt-Task."""
        sh(self.dir, "fetch", "-q", "origin", self.ref)
        sh(self.dir, "cherry-pick", self.commit)
        if not keep_task:
            body = sh(self.dir, "log", "-1", "--format=%B").replace(f"Agentrt-Task: {TASK}\n", "")
            sh(self.dir, "commit", "-q", "--amend", "-m", body)
        sh(self.dir, "push", "-q", "origin", "HEAD:refs/heads/main")
        return sh(self.dir, "rev-parse", "HEAD").strip()

    def reverts(self, sha: str) -> None:
        sh(self.dir, "revert", "--no-edit", sha)
        sh(self.dir, "push", "-q", "origin", "HEAD:refs/heads/main")

    def runtime(self, state: str = "accepted", txid: bool = True, extra: dict | None = None, reviews: int = 1) -> ma.Runtime:
        extra = extra or {}
        rows = {
            f"tasks/{TASK}": {"task_id": TASK, "role": "implement", "state": state, "repo": self.repo, "mission_id": "M-9",
                              "base_commit": self.base, "title": "delete ExecSQLOnPrimary", "updated_at": NOW.isoformat()},
            f"attempts/{ATTEMPT}": {"attempt_id": ATTEMPT, "attempt_no": 2, "executor_actor_id": "exec:codex",
                                    "pushed_ref": self.ref, "pushed_commit": self.commit},
            "missions/M-9": {"mission_id": "M-9", "work_id": "W-31", "title": "four small jobs"},
        }

        def tx(n: int) -> int | None:
            return n if txid else None
        events = [
            # Round 1: attempt 1's review failed; its review task was accepted (its result used).
            {"seq": 1, "event_type": "attempt_leased", "task_id": OLD_REVIEW, "body_json": {"executor": "exec:other"}, "txid": tx(1)},
            {"seq": 2, "event_type": "verification_recorded", "task_id": TASK, "attempt_id": EARLIER,
             "body_json": {"method": "review", "verdict": "fail"}, "txid": tx(2)},
            {"seq": 3, "event_type": "task_state_changed", "task_id": OLD_REVIEW, "body_json": {"to": "accepted"}, "txid": tx(2)},
            # Round 2: attempt 2's deterministic pass, then its review (two leases) passed and accepted it.
            {"seq": 4, "event_type": "verification_recorded", "task_id": TASK, "attempt_id": ATTEMPT,
             "body_json": {"method": "deterministic", "verdict": "pass"}, "txid": tx(3)},
            {"seq": 5, "event_type": "attempt_leased", "task_id": REVIEW, "body_json": {"executor": "exec:claude"}, "txid": tx(4)},
            {"seq": 6, "event_type": "attempt_leased", "task_id": REVIEW, "body_json": {"executor": "exec:cursor"}, "txid": tx(5)},
            {"seq": 7, "event_type": "verification_recorded", "task_id": TASK, "attempt_id": ATTEMPT,
             "body_json": {"method": "review", "verdict": "pass"}, "txid": tx(9)},
            {"seq": 8, "event_type": "task_state_changed", "task_id": REVIEW, "body_json": {"to": "accepted"}, "txid": tx(9)},
            {"seq": 9, "event_type": "task_state_changed", "task_id": TASK, "body_json": {"to": "accepted"}, "txid": tx(9),
             "at": "2026-10-20T00:02:41.123456+00:00"},
        ]
        review_rows = [{"task_id": REVIEW, "role": "review", "state": "accepted", "subject_task_id": TASK},
                       {"task_id": OLD_REVIEW, "role": "review", "state": "accepted", "subject_task_id": TASK}][:reviews]

        def get(path: str) -> object:
            if path.startswith("events?"):
                return [] if "after_seq" in path else events
            if path.startswith("tasks?"):
                if "state=accepted" in path:
                    return {"tasks": [rows[f"tasks/{TASK}"]] if "mission=M-9" in path and state == "accepted" else [], "truncated": False}
                return {"tasks": [rows[f"tasks/{TASK}"], *review_rows], "truncated": False}
            if path in extra:
                return extra[path]
            if path in rows:
                return rows[path]
            if path.startswith("missions/M-") and int(path.rsplit("-", 1)[1]) < 9:
                return {"mission_id": path.split("/")[1], "title": "an earlier mission"}  # numbered from M-1
            raise not_found(path)
        return RealRuntime("prod", get)


# ── what the runtime accepted ─────────────────────────────────────────────────

def test_reads_the_accepted_attempt_and_its_reviewer(tmp_path: Path) -> None:
    w = World(tmp_path)
    a = ma.accepted(w.runtime(), TASK)
    # Not attempt 1, whose review failed, nor its reviewer; the review accepted in the pass's
    # transaction, its last attempt's executor.
    assert (a.attempt, a.attempt_no, a.author, a.commit, a.ref) == (ATTEMPT, 2, "exec:codex", w.commit, w.ref)
    assert a.reviewers == ["exec:cursor"] and a.mission_label == "W-31" and a.accepted_at.startswith("2026-10-20T00:02")


@pytest.mark.parametrize("reviews, want", [(1, ["exec:cursor"]), (2, [])])
def test_without_transactions_only_a_sole_accepted_review_names_the_reviewer(tmp_path: Path, reviews: int, want: list[str]) -> None:
    assert ma.accepted(World(tmp_path).runtime(txid=False, reviews=reviews), TASK).reviewers == want


def test_refuses_what_is_not_an_accepted_implementation(tmp_path: Path) -> None:
    with pytest.raises(ma.Refused, match="is rework, not accepted"):
        ma.accepted(World(tmp_path).runtime(state="rework"), TASK)


def test_runtime_reads_every_page_and_tells_404_from_an_error() -> None:
    def pages(path: str) -> object:
        if path.startswith("events?"):
            after = int(path.split("after_seq=")[1]) if "after_seq=" in path else 0
            return [{"seq": n} for n in range(after + 1, min(after + ma.EVENTS_PAGE, 1001) + 1)]
        if path.startswith("tasks?"):
            return {"tasks": [], "truncated": True}
        if path == "tasks/t_missing":
            raise not_found(path)
        raise urllib.error.HTTPError(path, 500, "boom", None, None)  # type: ignore[arg-type]
    rt = RealRuntime("prod", pages)
    assert [e["seq"] for e in rt.events("M-1")] == list(range(1, 1002))
    with pytest.raises(ma.Refused, match="more tasks than one list answers"):
        rt.tasks("M-1")
    assert rt.find_task("t_missing") is None
    with pytest.raises(urllib.error.HTTPError):
        rt.find_task("t_other")


def test_a_read_the_platform_fails_is_tried_again_and_a_refusal_is_not() -> None:
    calls: list[str] = []

    def flaky(path: str) -> object:
        calls.append(path)
        if path == "tasks/t_once" and calls.count(path) == 1:
            raise urllib.error.HTTPError(path, 500, "boom", None, None)  # type: ignore[arg-type]
        if path == "tasks/t_forbidden":
            raise urllib.error.HTTPError(path, 403, "no", None, None)  # type: ignore[arg-type]
        if path == "tasks/t_down":
            raise urllib.error.URLError("refused")
        return {"task_id": path}
    rt = RealRuntime("prod", flaky)
    assert rt.task("t_once") == {"task_id": "tasks/t_once"} and calls.count("tasks/t_once") == 2
    with pytest.raises(urllib.error.HTTPError):
        rt.task("t_forbidden")
    with pytest.raises(urllib.error.URLError):
        rt.task("t_down")
    assert calls.count("tasks/t_forbidden") == 1 and calls.count("tasks/t_down") == ma.Runtime.TRIES


# ── the message ───────────────────────────────────────────────────────────────

def test_message_says_where_it_came_from_and_keeps_its_trailers(tmp_path: Path) -> None:
    w = World(tmp_path)
    msg = ma.message(MESSAGE, ma.accepted(w.runtime(), TASK))
    assert msg == ("cluster: delete ExecSQLOnPrimary (TD-268)\n\nThe body says why.\n\n"
                   f"Written by the agent runtime: PROD M-9 (W-31), task {TASK}, attempt 2 {ATTEMPT} (exec:codex), "
                   "reviewed by exec:cursor and accepted 2026-10-20 00:02Z. Until the release queue, the coordinator "
                   "merges accepted results with scripts/agentrt/merge_accepted.py (TD-383).\n\n"
                   f"(cherry picked from commit {w.commit})\n\n"
                   f"Agentrt-Task: {TASK}\nChange-Id: {CHANGE}\nWork: W-31, TD-383\n")
    # Merged again (amended, say), TD-383 is not added twice.
    assert ma.message(msg, ma.accepted(w.runtime(), TASK)).count("TD-383\n") == 1


def test_a_subject_that_names_only_the_task_takes_its_title(tmp_path: Path) -> None:
    msg = ma.message(f"agentrt: {TASK} attempt 2\n\nAgentrt-Task: {TASK}\nChange-Id: {CHANGE}\nWork: unassigned\n",
                     ma.accepted(World(tmp_path).runtime(), TASK))
    assert msg.startswith("delete ExecSQLOnPrimary\n\nWritten by the agent runtime:") and msg.endswith("Work: TD-383\n")


@pytest.mark.parametrize("original, why", [
    ("subject only\n", "ends in no trailers"),
    ("subject\n\nbody, no trailers\n", "ends in no trailers"),
    (f"subject\n\nChange-Id: {CHANGE}\nWork: W-31\n", "carries Agentrt-Task none"),
    (f"subject\n\nAgentrt-Task: {TASK}\nWork: W-31\n", "no single Change-Id"),
    (f"subject\n\nAgentrt-Task: {UNKNOWN}\nChange-Id: {CHANGE}\n", "not its own"),
    (f"subject\n\nAgentrt-Task: {TASK}\nChange-Id: Inot-hex\n", "no single Change-Id"),
])
def test_message_refuses_a_commit_without_its_own_trailers(tmp_path: Path, original: str, why: str) -> None:
    with pytest.raises(ma.Refused, match=why):
        ma.message(original, ma.accepted(World(tmp_path).runtime(), TASK))


# ── plan and build ────────────────────────────────────────────────────────────

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


@pytest.mark.parametrize("keep_task", [True, False])
def test_plan_refuses_a_task_already_on_main(tmp_path: Path, keep_task: bool) -> None:
    w = World(tmp_path)
    w.lands(keep_task)  # without its Agentrt-Task it is found by its Change-Id
    with pytest.raises(ma.Refused, match="already on bifrost-ui main"):
        ma.plan(w.runtime(), TASK, w.ws)


def test_plan_takes_a_task_whose_landing_was_reverted(tmp_path: Path) -> None:
    w = World(tmp_path)
    w.reverts(w.lands())
    assert ma.plan(w.runtime(), TASK, w.ws)[1] == ["a.txt"]


def test_plan_refuses_an_empty_change(tmp_path: Path) -> None:
    w = World(tmp_path, files={})
    with pytest.raises(ma.Refused, match="changes nothing"):
        ma.plan(w.runtime(), TASK, w.ws)


@pytest.mark.parametrize("base, why", [("", "names no base commit"), ("0" * 40, "is not one commit on its task's base")])
def test_plan_refuses_a_commit_not_on_its_tasks_base(tmp_path: Path, base: str, why: str) -> None:
    w = World(tmp_path)
    row = dict(w.runtime().task(TASK), base_commit=base)
    with pytest.raises(ma.Refused, match=why):
        ma.plan(w.runtime(extra={f"tasks/{TASK}": row}), TASK, w.ws)


def test_a_build_that_fails_leaves_nothing_and_can_run_again(tmp_path: Path) -> None:
    w = World(tmp_path, repo="bifrost-platform")
    w.main_moves("a.txt")
    a, _, msg = ma.plan(w.runtime(), TASK, w.ws)
    dest = tmp_path / "merge"
    for _ in range(2):
        with pytest.raises(ma.Refused, match="does not apply"):
            ma.build(a, msg, w.ws, dest)
        assert not dest.exists()
        for repo in ("bifrost-platform", "bifrost-trade-infra", "bifrost-ui"):
            assert str(dest) not in sh(w.ws / repo, "worktree", "list")


# ── the line, the suite, apply ────────────────────────────────────────────────

def test_only_platform_is_pushed() -> None:
    assert ma.may_push("bifrost-platform")[0]
    for repo, says in [("bifrost-ui", "the Console and the Trade frontend"), ("bifrost-trade-infra", "Argo"),
                       ("bifrost-research", "follows its own release rules")]:
        ok, why = ma.may_push(repo)
        assert not ok and says in why


def test_suite_runs_every_ci_step_then_code_health_in_the_tree(tmp_path: Path) -> None:
    ran: list[tuple[list[str], dict[str, str]]] = []

    def run(cmd: list[str], cwd: Path, env: dict[str, str]) -> int:
        ran.append((cmd, env))
        return 1 if "lint" in cmd or "code-health" in " ".join(cmd) else 0
    tree = tmp_path / "bifrost-platform"
    checked, failed = ma.run_suite(tree, "bifrost-platform", run)
    assert [c for c, _ in ran[:-1]] == ma.SUITES["bifrost-platform"]
    assert ran[-1][0][-4:] == ["--root", str(tmp_path), "--repo", "bifrost-platform"]
    assert all(e == {"BIFROST_CI": "1", "PLATFORM_ROOT": str(tree), "AGENTRT_TEST_REQUIRED": "1"} for _, e in ran)
    assert checked and failed == ["npm --prefix console run lint", "code-health"]
    assert ma.run_suite(tmp_path, "bifrost-trade-infra", run) == (False, [])


@pytest.mark.parametrize("repo, push, suite_fails, rc, pushes", [
    ("bifrost-platform", False, False, 0, 0),
    ("bifrost-platform", True, False, 0, 1),
    ("bifrost-platform", True, True, 1, 0),
    ("bifrost-ui", True, False, 4, 0),  # no suite here: built, not verified
    ("bifrost-trade-infra", True, False, 4, 0),
])
def test_apply_pushes_only_a_verified_platform_commit_and_only_when_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                         repo: str, push: bool, suite_fails: bool, rc: int,
                                                                         pushes: int) -> None:
    monkeypatch.setenv("AGENTRT_TEST_PG", "host=test")
    monkeypatch.setenv("AGENTRT_TEST_REDIS", "redis://test")
    pushed: list[Path] = []
    monkeypatch.setattr(ma, "push", lambda tree: pushed.append(tree) or 0)
    w = World(tmp_path, repo=repo)
    got = ma.apply(w.runtime(), TASK, w.ws, tmp_path / "merge", push, run=lambda cmd, cwd, env: 1 if suite_fails else 0)
    assert (got, len(pushed)) == (rc, pushes)


def test_apply_refuses_without_the_test_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTRT_TEST_PG", raising=False)
    monkeypatch.setenv("AGENTRT_TEST_REDIS", "redis://test")
    w = World(tmp_path, repo="bifrost-platform")
    with pytest.raises(ma.Refused, match="set AGENTRT_TEST_PG"):
        ma.apply(w.runtime(), TASK, w.ws, tmp_path / "merge", True, run=lambda cmd, cwd, env: 0)
    assert not (tmp_path / "merge").exists()


# ── list ──────────────────────────────────────────────────────────────────────

def test_list_names_what_is_accepted_and_not_on_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    w = World(tmp_path)
    assert ma.cmd_list(w.runtime(), w.ws) == 1
    out = capsys.readouterr().out
    assert f"bifrost-ui\tM-9\t{TASK}\tattempt 2 (exec:codex) {w.commit[:12]}; not on main" in out
    assert "1 accepted implementation(s)" in out
    landed = w.lands(keep_task=False)  # by hand, its Change-Id kept
    assert ma.cmd_list(w.runtime(), w.ws) == 0
    w.reverts(landed)
    assert ma.cmd_list(w.runtime(), w.ws) == 1
    assert f"it landed as {landed[:12]} and was reverted" in capsys.readouterr().out


def test_list_passes_over_an_empty_change(tmp_path: Path) -> None:
    w = World(tmp_path, files={})
    assert ma.cmd_list(w.runtime(), w.ws) == 0


# ── prunable ──────────────────────────────────────────────────────────────────

def test_prunable_follows_td383s_rule(tmp_path: Path) -> None:
    w = World(tmp_path, repo="bifrost-platform")
    for ref in (f"refs/heads/agent/{TASK}/a1", f"refs/heads/agent/{CANCELLED}/a1", f"refs/heads/agent/{JUST_CANCELLED}/a1",
                f"refs/heads/agent/{UNKNOWN}/a3", f"refs/heads/agent/{BOTH}/a1", "refs/heads/agent/manual/foo"):
        sh(w.dir, "push", "-q", "origin", f"{w.base}:{ref}")
    long_ago = (NOW - timedelta(days=10)).isoformat()
    prod = w.runtime(extra={
        f"tasks/{CANCELLED}": {"task_id": CANCELLED, "state": "cancelled", "updated_at": long_ago},
        # An old commit whose task was cancelled today: its seven days start today.
        f"tasks/{JUST_CANCELLED}": {"task_id": JUST_CANCELLED, "state": "cancelled", "updated_at": NOW.isoformat()},
        f"tasks/{BOTH}": {"task_id": BOTH, "state": "cancelled", "updated_at": long_ago},
    })
    stg = RealRuntime("stg", lambda p: {"task_id": BOTH, "state": "running"} if p == f"tasks/{BOTH}" else knows_nothing(p))

    def decisions(at: datetime) -> dict[str, tuple[str, bool, str]]:
        return {ref.removeprefix("refs/heads/agent/").replace("t_01M5B8BF2EM3SJQDKZ9E9TY2", ""): (env, go, why)
                for ref, env, go, why in ma.prunable({"prod": prod, "stg": stg}, w.dir, at.timestamp())}
    now = decisions(NOW)
    assert now["H8/a1"] == ("prod", False, "superseded: attempt 2 was accepted; 0.0 of 7 days")
    assert now["HA/a1"] == ("prod", True, "its task is cancelled")
    assert now["HD/a1"] == ("prod", False, "its task is cancelled; 0.0 of 7 days")
    assert now["HB/a3"] == ("", False, "no task of this id in prod or stg")
    assert now["HE/a1"] == ("", False, "a task of this id is known to prod and stg")
    assert now["manual/foo"] == ("", False, "not an attempt branch (agent/<task>/a<n>)")
    late = decisions(NOW + timedelta(days=8))
    assert late["H8/a1"] == ("prod", True, "superseded: attempt 2 was accepted")
    assert late["H8/a2"] == ("prod", False, "its accepted result is not on main")
    assert late["HD/a1"][1] and not late["HE/a1"][1] and not late["HB/a3"][1]
    # Landed: its seven days start at the landing, and then every branch of the task goes.
    landed = w.lands()
    assert not decisions(NOW + timedelta(days=1))["H8/a2"][1]
    merged = decisions(NOW + timedelta(days=8))
    assert merged["H8/a2"] == ("prod", True, f"its task is accepted and on main as {landed[:12]}") and merged["H8/a1"][1]
    # Reverted: the accepted attempt stays; the superseded one still goes.
    w.reverts(landed)
    reverted = decisions(NOW + timedelta(days=8))
    assert reverted["H8/a2"] == ("prod", False, f"it landed as {landed[:12]} and was reverted") and reverted["H8/a1"][1]
