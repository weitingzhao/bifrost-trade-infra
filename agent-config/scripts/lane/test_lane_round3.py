"""Round 3: a step runs only while its driver is alive."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import lane
import lane_steps
from test_lane import (
    LANE, cli, events, load, new_lane, pid_alive, scaffold, stop_process,
)

PY = sys.executable


def save(root: Path, lane_id: str, doc: dict) -> None:
    (root / lane_id / "lane.json").write_text(json.dumps(doc), encoding="utf-8")


def command(cfg: Path, name: str, argv: list[str]) -> None:
    doc = json.loads(cfg.read_text(encoding="utf-8"))
    doc[name] = argv
    cfg.write_text(json.dumps(doc), encoding="utf-8")


def git(cwd: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Lane Test",
        "GIT_AUTHOR_EMAIL": "lane@example.com",
        "GIT_COMMITTER_NAME": "Lane Test",
        "GIT_COMMITTER_EMAIL": "lane@example.com",
    }
    subprocess.run(["git", *args], cwd=cwd, check=True, env=env, capture_output=True, text=True)


def init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README").write_text("a\n", encoding="utf-8")
    git(path, "init")
    git(path, "add", "README")
    git(path, "commit", "-m", "init")


def wait_until(predicate, timeout: float = 5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def spawn_run(root, cfg, lane_id, stall="0.3", **env):
    merged = os.environ.copy()
    merged["LANE_FAKE"] = "pass"
    merged.update(env)
    return subprocess.Popen(
        [PY, str(LANE), "--root", str(root), "--config", str(cfg),
         "run", lane_id, "--stall-seconds", stall],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=merged,
    )


def running_step(root, lane_id):
    doc = load(root, lane_id)
    steps = [step for step in doc["steps"] if step.get("end") is None and step.get("pid")]
    return steps[-1] if steps else None


def test_exit_code_comes_from_the_process_not_the_file(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    done = root / "w66" / "round-1" / "verify-1" / "done"
    script = tmp_path / "lie.py"
    script.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        f"path = Path({str(done)!r})\n"
        "path.parent.mkdir(parents=True, exist_ok=True)\n"
        "path.write_text(json.dumps({'exit': 0}) + '\\n', encoding='utf-8')\n"
        "raise SystemExit(9)\n",
        encoding="utf-8",
    )
    command(cfg, "verify", [PY, str(script)])
    new_lane(root, cfg, ws, brief)
    proc = cli(root, cfg, "run", "w66")
    assert proc.returncode == 0, proc.stderr
    doc = load(root, "w66")
    assert doc["state"] == "failed"
    assert events(root, "w66")[-1]["why"] == "verify exited 9"
    assert json.loads(done.read_text(encoding="utf-8"))["exit"] == 9
    assert [step["name"] for step in doc["steps"]] == ["implement", "verify"]


def test_stderr_verdict_does_not_count(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    script = tmp_path / "err_verdict.py"
    script.write_text("import sys\nprint('VERDICT: pass', file=sys.stderr, flush=True)\n", encoding="utf-8")
    command(cfg, "verify", [PY, str(script)])
    new_lane(root, cfg, ws, brief)
    proc = cli(root, cfg, "run", "w66")
    assert proc.returncode == 0, proc.stderr
    doc = load(root, "w66")
    assert doc["state"] == "failed"
    assert events(root, "w66")[-1]["why"] == "verification produced no verdict"
    verify = doc["steps"][1]
    assert verify["log"].endswith("stdout.log")
    assert Path(verify["log"]).read_text(encoding="utf-8") == ""
    assert "VERDICT: pass" in Path(verify["stderr"]).read_text(encoding="utf-8")
    board = json.loads(cli(root, cfg, "board").stdout)
    assert board["works"][0]["steps"][1]["progress"].endswith("stdout.log")


def fresh_config(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_text((tmp_path / "lane-config.json").read_text(encoding="utf-8"), encoding="utf-8")
    return path


def test_worktree_must_match_the_commit(tmp_path):
    root, cfg, _ws, brief = scaffold(tmp_path)

    edited = tmp_path / "edited"
    init_repo(edited)
    script = tmp_path / "edit_tracked.py"
    script.write_text(
        "from pathlib import Path\n"
        "Path('README').write_text('edited\\n', encoding='utf-8')\n"
        "print('VERDICT: pass', flush=True)\n",
        encoding="utf-8",
    )
    tracked_cfg = fresh_config(tmp_path, "tracked.json")
    command(tracked_cfg, "verify", [PY, str(script)])
    new_lane(root, tracked_cfg, edited, brief, lane_id="tracked")
    proc = cli(root, tracked_cfg, "run", "tracked")
    assert proc.returncode == 0, proc.stderr
    assert events(root, "tracked")[-1]["why"] == "the work tree of edited changed during verify"

    loose = tmp_path / "loose"
    init_repo(loose)
    dropped = tmp_path / "drop_untracked.py"
    dropped.write_text(
        "from pathlib import Path\n"
        "Path('notes.txt').write_text('x\\n', encoding='utf-8')\n"
        "print('VERDICT: pass', flush=True)\n",
        encoding="utf-8",
    )
    loose_cfg = fresh_config(tmp_path, "loose.json")
    command(loose_cfg, "verify", [PY, str(dropped)])
    new_lane(root, loose_cfg, loose, brief, lane_id="dropped")
    proc = cli(root, loose_cfg, "run", "dropped")
    assert proc.returncode == 0, proc.stderr
    assert events(root, "dropped")[-1]["why"] == "the work tree of loose changed during verify"

    before = tmp_path / "before"
    init_repo(before)
    (before / "loose.txt").write_text("x\n", encoding="utf-8")
    new_lane(root, cfg, before, brief, lane_id="before")
    proc = cli(root, cfg, "run", "before")
    assert proc.returncode == 0, proc.stderr
    assert events(root, "before")[-1]["why"] == "uncommitted or untracked files in before before verify"
    assert not (root / "before" / "round-1" / "verify-1").exists()

    child = tmp_path / "parent"
    init_repo(child)
    plugin = child / "plugin"
    init_repo(plugin)
    (plugin / "extra.txt").write_text("x\n", encoding="utf-8")
    new_lane(root, cfg, child, brief, lane_id="child")
    proc = cli(root, cfg, "run", "child")
    assert proc.returncode == 0, proc.stderr
    assert events(root, "child")[-1]["why"] == "uncommitted or untracked files in plugin before verify"

    review_repo = tmp_path / "reviewed"
    init_repo(review_repo)
    review = tmp_path / "edit_review.py"
    review.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "Path('README').write_text('during review\\n', encoding='utf-8')\n"
        "Path(sys.argv[1]).write_text('VERDICT: safe to merge\\nEND OF REPORT\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    review_cfg = fresh_config(tmp_path, "review.json")
    command(review_cfg, "review", [PY, str(review), "{report}"])
    new_lane(root, review_cfg, review_repo, brief, lane_id="review-edit")
    proc = cli(root, review_cfg, "run", "review-edit")
    assert proc.returncode == 0, proc.stderr
    assert events(root, "review-edit")[-1]["why"] == "the work tree of reviewed changed during review"
    assert "verified_heads" not in load(root, "review-edit")

    ignored = tmp_path / "ignored"
    init_repo(ignored)
    (ignored / ".gitignore").write_text("*.ignored\n", encoding="utf-8")
    git(ignored, "add", ".gitignore")
    git(ignored, "commit", "-m", "ignore")
    (ignored / "noise.ignored").write_text("nope\n", encoding="utf-8")
    new_lane(root, cfg, ignored, brief, lane_id="ignored")
    proc = cli(root, cfg, "run", "ignored")
    assert proc.returncode == 0, proc.stderr
    assert load(root, "ignored")["state"] == "passed"


def test_stop_while_a_driver_is_running(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    script = tmp_path / "forever.py"
    script.write_text(
        "import sys, time\nwhile True:\n    print('tick', flush=True)\n    time.sleep(0.2)\n",
        encoding="utf-8",
    )
    command(cfg, "implement", [PY, str(script)])
    new_lane(root, cfg, ws, brief)
    proc = spawn_run(root, cfg, "w66", stall="30")
    try:
        assert wait_until(lambda: running_step(root, "w66") is not None)
        step = running_step(root, "w66")
        queued = json.loads(cli(root, cfg, "queue").stdout)
        assert all(item["title"] != "Dispatch chain" for item in queued)
        started = time.time()
        stopped = cli(root, cfg, "stop", "w66", "--by", "owner", "--reason", "enough")
        elapsed = time.time() - started
        assert stopped.returncode == 0, stopped.stderr
        assert elapsed < 15
        doc = load(root, "w66")
        assert doc["state"] == "failed"
        assert events(root, "w66")[-1]["why"] == "stopped by owner"
        assert events(root, "w66")[-1]["reaped"] is True
        assert doc["steps"][0]["reaped"] is True
        assert not (root / "w66" / "stop-request.json").exists()
        assert not pid_alive(step["pid"])
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        doc = load(root, "w66")
        for step in doc["steps"]:
            if step.get("pid"):
                stop_process(step["pid"])


def test_abandon_while_a_driver_is_running(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    script = tmp_path / "forever.py"
    script.write_text(
        "import time\nwhile True:\n    print('tick', flush=True)\n    time.sleep(0.2)\n",
        encoding="utf-8",
    )
    command(cfg, "implement", [PY, str(script)])
    new_lane(root, cfg, ws, brief, lane_id="drop", title="Drop")
    proc = spawn_run(root, cfg, "drop")
    try:
        assert wait_until(lambda: running_step(root, "drop") is not None)
        pid = running_step(root, "drop")["pid"]
        abandoned = cli(root, cfg, "abandon", "drop", "--reason", "drop it")
        assert abandoned.returncode == 0, abandoned.stderr
        doc = load(root, "drop")
        assert doc["state"] == "failed"
        assert doc["abandoned"] is True
        assert events(root, "drop")[-1]["why"] == "abandon: drop it; terminated the process group"
        assert not pid_alive(pid)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_stop_reaps_a_grandchild_after_the_leader_exits(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    pidfile = tmp_path / "grandchild"
    script = tmp_path / "leader.py"
    script.write_text(
        "import os, signal, sys, time\n"
        "from pathlib import Path\n"
        "signal.signal(signal.SIGHUP, signal.SIG_IGN)\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        "    Path(sys.argv[1]).write_text(str(os.getpid()))\n"
        "    time.sleep(120)\n"
        "    os._exit(0)\n"
        "os._exit(0)\n",
        encoding="utf-8",
    )
    leader = subprocess.Popen([PY, str(script), str(pidfile)], start_new_session=True)
    leader.wait(timeout=5)
    assert wait_until(lambda: pidfile.is_file())
    grandchild = int(pidfile.read_text(encoding="utf-8"))
    assert pid_alive(grandchild)
    new_lane(root, cfg, ws, brief, lane_id="group")
    doc = load(root, "group")
    attempt = root / "group" / "round-1" / "implement-1"
    attempt.mkdir(parents=True)
    (attempt / "started.json").write_text(json.dumps({
        "pid": leader.pid, "pgid": leader.pid, "started_at": doc["created_at"],
    }), encoding="utf-8")
    doc["state"] = "implementing"
    doc["steps"] = [{
        "name": "implement", "round": 1, "attempt": 1, "state": "running", "who": "Cursor",
        "start": doc["created_at"], "end": None, "pid": leader.pid, "pgid": leader.pid,
        "exit": None, "log": str(attempt / "stdout.log"), "stderr": str(attempt / "stderr.log"),
        "done": str(attempt / "done"), "report": str(attempt / "report"),
        "started": str(attempt / "started.json"), "heads": None,
    }]
    save(root, "group", doc)
    assert lane_steps.GROUP_WAIT_SECONDS == 5
    assert lane_steps.end_group.__defaults__ == (lane_steps.GROUP_WAIT_SECONDS,)
    started = time.time()
    stopped = cli(root, cfg, "stop", "group", "--by", "owner")
    elapsed = time.time() - started
    assert stopped.returncode == 0, stopped.stderr
    assert elapsed >= 4
    assert not pid_alive(grandchild)
    doc = load(root, "group")
    assert doc["steps"][0]["reaped"] is True
    assert events(root, "group")[-1]["reaped"] is True

    doc["steps"][0]["reaped"] = False
    doc["steps"][0]["pgid"] = 4242
    doc["state"] = "failed"
    save(root, "group", doc)
    status = cli(root, cfg, "status", "group")
    assert "processes may still be running: pgid 4242" in status.stdout
    queued = json.loads(cli(root, cfg, "queue").stdout)
    assert "processes may still be running: pgid 4242" in queued[0]["why_waiting"]


def test_register_timeout_and_driver_died(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    clean = tmp_path / "clean.json"
    clean.write_bytes(cfg.read_bytes())
    assert lane_steps.REGISTER_SECONDS == 5
    assert lane.STOP_WAIT_SECONDS == 15
    assert lane_steps.poll_interval(600) <= 1
    new_lane(root, cfg, ws, brief, lane_id="late")
    started = time.time()
    proc = cli(root, cfg, "run", "late", extra_env={"LANE_REGISTER_DELAY": "30"})
    assert time.time() - started < 12
    assert proc.returncode == 0, proc.stderr
    doc = load(root, "late")
    assert doc["state"] == "failed"
    assert events(root, "late")[-1]["why"] == "the step did not register"
    assert not (root / "late" / "round-1" / "implement-1" / "started.json").exists()
    assert not (root / "late" / "round-1" / "implement-2").exists()

    script = tmp_path / "forever.py"
    script.write_text("import time\nwhile True:\n    time.sleep(0.5)\n", encoding="utf-8")
    command(cfg, "implement", [PY, str(script)])
    new_lane(root, cfg, ws, brief, lane_id="dead", title="Dead driver")
    (root / "dead" / "round-1").mkdir(parents=True)
    driver = spawn_run(root, cfg, "dead", stall="30")
    try:
        assert wait_until(lambda: running_step(root, "dead") is not None, timeout=8)
        step = running_step(root, "dead")
        os.kill(driver.pid, signal.SIGKILL)
        driver.wait(timeout=5)
        status = cli(root, cfg, "status", "dead")
        assert "state=running (no driver)" in status.stdout
        check = cli(root, cfg, "status", "--check")
        assert check.returncode == 1
        queued = json.loads(cli(root, cfg, "queue").stdout)
        item = next(row for row in queued if row["title"] == "Dead driver")
        assert item["why_waiting"] == (
            "the driver died during implement: run `lane.py run dead` to close it, then retry"
        )
        # A done file claiming success must not be trusted.
        Path(step["done"]).write_text(json.dumps({"exit": 0}) + "\n", encoding="utf-8")
        closed = cli(root, cfg, "run", "dead")
        assert closed.returncode == 0, closed.stderr
        doc = load(root, "dead")
        assert doc["state"] == "failed"
        assert events(root, "dead")[-1]["why"] == "the driver died during implement"
        assert [s["attempt"] for s in doc["steps"]] == [1]
        assert not pid_alive(step["pid"])
    finally:
        if driver.poll() is None:
            driver.kill()
            driver.wait(timeout=5)
        current = load(root, "dead")
        for step in current["steps"]:
            if step.get("pgid"):
                stop_process(step["pgid"])

    retried = cli(root, clean, "retry", "dead", "--by", "sam", "--reason", "driver was killed")
    assert retried.returncode == 0, retried.stderr
    doc = load(root, "dead")
    assert doc["round"] == 1
    assert doc["state"] == "passed"
    assert [step["attempt"] for step in doc["steps"] if step["name"] == "implement"] == [1, 2]
    retry_event = next(event for event in events(root, "dead") if event.get("by") == "sam")
    assert retry_event["reason"] == "driver was killed"
    assert retry_event["why"] == "retry by sam: driver was killed"


def test_retry_refuses_a_verdict(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief, lane_id="fail")
    cli(root, cfg, "run", "fail", mode="verify-fail")
    before = (root / "fail" / "lane.json").read_bytes()
    refused = cli(root, cfg, "retry", "fail", "--by", "sam", "--reason", "again")
    assert refused.returncode != 0
    assert refused.stderr.strip() == "a verify FAIL goes through next-round"
    assert (root / "fail" / "lane.json").read_bytes() == before

    new_lane(root, cfg, ws, brief, lane_id="fix")
    cli(root, cfg, "run", "fix", mode="review-fix")
    before = (root / "fix" / "lane.json").read_bytes()
    refused = cli(root, cfg, "retry", "fix", "--by", "sam", "--reason", "again")
    assert refused.returncode != 0
    assert "next-round" in refused.stderr
    assert load(root, "fix")["state"] == "changes_requested"
    assert (root / "fix" / "lane.json").read_bytes() == before

    new_lane(root, cfg, ws, brief, lane_id="none")
    cli(root, cfg, "run", "none", mode="verify-none")
    assert load(root, "none")["state"] == "failed"
    retried = cli(root, cfg, "retry", "none", "--by", "sam", "--reason", "no verdict yet")
    assert retried.returncode == 0, retried.stderr
    doc = load(root, "none")
    assert doc["round"] == 1
    assert doc["state"] == "passed"
    assert [step["attempt"] for step in doc["steps"] if step["name"] == "verify"] == [1, 2]


def test_quiet_output_is_shown_and_not_a_state(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    script = tmp_path / "quiet.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    command(cfg, "implement", [PY, str(script)])
    new_lane(root, cfg, ws, brief, title="Quiet lane")
    proc = spawn_run(root, cfg, "w66")
    try:
        def quiet():
            status = cli(root, cfg, "status", "w66").stdout
            board = cli(root, cfg, "board").stdout
            queued = cli(root, cfg, "queue").stdout
            return "no output for" in status and "no output for" in board and "no output for" in queued
        assert wait_until(quiet, timeout=5), cli(root, cfg, "status", "w66").stdout
        doc = load(root, "w66")
        assert doc["state"] == "implementing"
        assert doc["steps"][0]["stalled_since"]
        assert all(event["to"] != "stalled" for event in events(root, "w66"))
    finally:
        cli(root, cfg, "stop", "w66", "--by", "owner")
        if proc.poll() is None:
            proc.wait(timeout=10)
