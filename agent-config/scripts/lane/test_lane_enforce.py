"""Round 2: a failed, stale, concurrent, or self-authorised step does not get through."""
from __future__ import annotations

import json
import os
import pty
import signal
import subprocess
import time
from pathlib import Path

import lane
import lane_runner
import lane_state
import lane_steps
from test_lane import (
    HERE, LANE, cli, events, load, new_lane, scaffold, stop_process, unused_pid, write_config,
)

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Lane Test",
    "GIT_AUTHOR_EMAIL": "lane@example.com",
    "GIT_COMMITTER_NAME": "Lane Test",
    "GIT_COMMITTER_EMAIL": "lane@example.com",
}


def save(root: Path, lane_id: str, doc: dict) -> None:
    (root / lane_id / "lane.json").write_text(json.dumps(doc), encoding="utf-8")


def git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Lane Test", "-c", "user.email=lane@example.com", *args],
        cwd=cwd, check=True, env={**os.environ, **GIT_ENV}, capture_output=True, text=True,
    )


def init_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README").write_text("a\n", encoding="utf-8")
    git("init", cwd=path)
    git("add", "README", cwd=path)
    git("commit", "-m", "init", cwd=path)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True,
    ).stdout.strip()


def test_p1_nonzero_exit_is_not_a_pass(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief, lane_id="verify-bad")
    proc = cli(root, cfg, "run", "verify-bad", mode="verify-exit")
    assert proc.returncode == 0, proc.stderr
    doc = load(root, "verify-bad")
    assert doc["state"] == "failed"
    assert [step["name"] for step in doc["steps"]] == ["implement", "verify"]
    assert events(root, "verify-bad")[-1]["why"] == "verify exited 7"
    verify = [item for item in doc["verdicts"]["entries"] if item["step"] == "verify"][-1]
    assert verify["exit"] == 7
    assert verify["verdict"] == "VERDICT: pass"

    new_lane(root, cfg, ws, brief, lane_id="review-bad")
    proc = cli(root, cfg, "run", "review-bad", mode="review-exit")
    assert proc.returncode == 0, proc.stderr
    doc = load(root, "review-bad")
    assert doc["state"] == "failed"
    assert "verified_heads" not in doc
    assert events(root, "review-bad")[-1]["why"] == "review exited 9"
    review = [item for item in doc["verdicts"]["entries"] if item["step"] == "review"][-1]
    assert review["exit"] == 9


def test_p1_fresh_attempt_directory(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief)
    marker_dir = root / "w66" / "round-1" / "implement-1"
    marker_dir.mkdir(parents=True)
    marker = marker_dir / "marker"
    marker.write_text("keep\n", encoding="utf-8")
    proc = cli(root, cfg, "run", "w66")
    assert proc.returncode == 0, proc.stderr
    doc = load(root, "w66")
    assert marker.read_text(encoding="utf-8") == "keep\n"
    assert not (marker_dir / "log").exists()
    assert doc["steps"][0]["attempt"] == 2
    assert doc["steps"][0]["log"].endswith("implement-2/log")
    verify = next(item for item in doc["verdicts"]["entries"] if item["step"] == "verify")
    assert set(verify) >= {"round", "step", "attempt", "verdict", "heads", "exit", "at"}
    assert verify["verdict"] == "VERDICT: pass"
    assert verify["exit"] == 0
    assert verify["heads"] == {}
    assert "verify.txt" not in (HERE / "lane-config.json").read_text(encoding="utf-8")


def test_p1_heads_bound_to_this_commit(tmp_path):
    root, cfg, _ws, brief = scaffold(tmp_path)
    repo = tmp_path / "repo"
    parent = init_repo(repo)
    child = repo / "plugin"
    child_head = init_repo(child)
    new_lane(root, cfg, repo, brief, lane_id="clean")
    proc = cli(root, cfg, "run", "clean")
    assert proc.returncode == 0, proc.stderr
    doc = load(root, "clean")
    assert doc["state"] == "passed"
    assert doc["verified_heads"] == {"plugin": child_head, "repo": parent}
    status = cli(root, cfg, "status", "clean")
    assert f"heads=plugin:{child_head[:7]},repo:{parent[:7]}" in status.stdout

    dirty = tmp_path / "dirty"
    init_repo(dirty)
    (dirty / "README").write_text("changed\n", encoding="utf-8")
    new_lane(root, cfg, dirty, brief, lane_id="dirty")
    proc = cli(root, cfg, "run", "dirty")
    assert proc.returncode == 0, proc.stderr
    assert load(root, "dirty")["state"] == "failed"
    assert events(root, "dirty")[-1]["why"] == "uncommitted changes in dirty"
    assert not (root / "dirty" / "round-1" / "verify-1").exists()

    moved = tmp_path / "moved"
    init_repo(moved)
    script = tmp_path / "move_verify.py"
    script.write_text(
        "import os, subprocess, sys\n"
        "from pathlib import Path\n"
        "env = os.environ.copy()\n"
        "env.update(%r)\n" % GIT_ENV
        + "Path('during.txt').write_text('x\\n', encoding='utf-8')\n"
        "subprocess.run(['git', '-c', 'user.name=Lane Test', '-c', 'user.email=lane@example.com', 'add', 'during.txt'], check=True, env=env)\n"
        "subprocess.run(['git', '-c', 'user.name=Lane Test', '-c', 'user.email=lane@example.com', 'commit', '-m', 'during'], check=True, env=env)\n"
        "print('VERDICT: pass', flush=True)\n",
        encoding="utf-8",
    )
    move_cfg = write_config(tmp_path, tmp_path / "fake.py")
    commands = json.loads(move_cfg.read_text(encoding="utf-8"))
    commands["verify"] = [os.environ.get("PYTHON", "") or __import__("sys").executable, str(script)]
    move_cfg.write_text(json.dumps(commands), encoding="utf-8")
    new_lane(root, move_cfg, moved, brief, lane_id="during")
    proc = cli(root, move_cfg, "run", "during")
    assert proc.returncode == 0, proc.stderr
    assert load(root, "during")["state"] == "failed"
    assert events(root, "during")[-1]["why"] == "the branch moved during verification"
    assert [step["name"] for step in load(root, "during")["steps"]] == ["implement", "verify"]


def test_p1_review_heads_must_match_the_verify(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief, lane_id="stale")
    doc = load(root, "stale")
    doc["state"] = "reviewing"
    doc["steps"] = [{
        "name": "verify", "round": 1, "attempt": 1, "state": "finished", "who": "verify",
        "start": doc["created_at"], "end": doc["created_at"], "pid": 1, "exit": 0,
        "log": "log", "done": "done", "report": "report", "heads": {},
    }]
    doc["verdicts"] = {"entries": [{
        "round": 1, "step": "verify", "attempt": 1, "verdict": "VERDICT: pass",
        "heads": {"repo": "0" * 40}, "exit": 0, "at": doc["created_at"],
    }]}
    save(root, "stale", doc)
    proc = cli(root, cfg, "run", "stale")
    assert proc.returncode == 0, proc.stderr
    assert load(root, "stale")["state"] == "failed"
    assert events(root, "stale")[-1]["why"] == "review needs a passing verify for the current heads"
    assert not (root / "stale" / "round-1" / "review-1").exists()

    repo = tmp_path / "reviewrepo"
    init_repo(repo)
    review = tmp_path / "move_review.py"
    review.write_text(
        "import os, subprocess, sys\n"
        "from pathlib import Path\n"
        "env = os.environ.copy()\n"
        "env.update(%r)\n" % GIT_ENV
        + "report = Path(sys.argv[1])\n"
        "Path('during-review.txt').write_text('y\\n', encoding='utf-8')\n"
        "subprocess.run(['git', '-c', 'user.name=Lane Test', '-c', 'user.email=lane@example.com', 'add', 'during-review.txt'], check=True, env=env)\n"
        "subprocess.run(['git', '-c', 'user.name=Lane Test', '-c', 'user.email=lane@example.com', 'commit', '-m', 'during review'], check=True, env=env)\n"
        "report.write_text('VERDICT: safe to merge\\nEND OF REPORT\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    commands = json.loads(cfg.read_text(encoding="utf-8"))
    py = __import__("sys").executable
    commands["review"] = [py, str(review), "{report}"]
    moved_cfg = tmp_path / "moved-review.json"
    moved_cfg.write_text(json.dumps(commands), encoding="utf-8")
    new_lane(root, moved_cfg, repo, brief, lane_id="shift")
    proc = cli(root, moved_cfg, "run", "shift")
    assert proc.returncode == 0, proc.stderr
    done = load(root, "shift")
    assert done["state"] == "failed"
    assert "verified_heads" not in done
    assert events(root, "shift")[-1]["why"] == "the branch moved during review"


def test_p1_lock_two_processes(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief)
    env = os.environ.copy()
    env["LANE_FAKE"] = "pass"
    env["LANE_SLEEP"] = "1.2"
    first = subprocess.Popen(
        [__import__("sys").executable, str(LANE), "--root", str(root), "--config", str(cfg), "run", "w66"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )
    lock = root / "w66" / "lock"
    try:
        deadline = time.time() + 5
        while time.time() < deadline:
            if lock.is_file() and lock.read_text(encoding="utf-8").strip() == str(first.pid):
                break
            time.sleep(0.05)
        else:
            out, err = first.communicate(timeout=5)
            raise AssertionError(f"lock was not taken\n{out}\n{err}")
        second = subprocess.run(
            [__import__("sys").executable, str(LANE), "--root", str(root), "--config", str(cfg), "run", "w66"],
            capture_output=True, text=True, env=env, timeout=5,
        )
        assert second.returncode == 3
        assert second.stderr.strip() == f"lane w66 is being driven by pid {first.pid}"
        out, err = first.communicate(timeout=15)
        assert first.returncode == 0, err
    finally:
        if first.poll() is None:
            first.terminate()
            first.wait(timeout=5)
        doc = load(root, "w66")
        for step in doc["steps"]:
            if step.get("pid"):
                stop_process(step["pid"])
    doc = load(root, "w66")
    assert doc["state"] == "passed"
    assert [step["name"] for step in doc["steps"]] == ["implement", "verify", "review"]
    assert doc["steps"][0]["attempt"] == 1


def test_p1_run_checks_the_budget_itself(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief, lane_id="high", max_rounds="2")
    doc = load(root, "high")
    doc["round"] = 3
    doc["state"] = "implementing"
    save(root, "high", doc)
    proc = cli(root, cfg, "run", "high")
    assert proc.returncode == 0, proc.stderr
    doc = load(root, "high")
    assert doc["state"] == "over_budget"
    assert doc["steps"] == []
    assert not (root / "high" / "round-3").exists()

    new_lane(root, cfg, ws, brief, lane_id="granted", max_rounds="2")
    doc = load(root, "granted")
    doc["round"] = 3
    doc["extensions"] = [{"by": "coordinator", "reason": "need one more", "at": doc["created_at"], "round": 2}]
    save(root, "granted", doc)
    proc = cli(root, cfg, "run", "granted")
    assert proc.returncode == 0, proc.stderr
    assert load(root, "granted")["state"] == "passed"
    assert load(root, "granted")["steps"][0]["name"] == "implement"


def test_p1_a_step_cannot_change_the_lane(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief)
    path = root / "w66" / "lane.json"
    before = path.read_bytes()
    calls = [
        ["next-round", "w66", "--brief", str(brief)],
        ["extend", "w66", "--reason", "quiet", "--by", "coordinator"],
        ["abandon", "w66", "--reason", "quiet"],
    ]
    for args in calls:
        proc = cli(root, cfg, *args, extra_env={"LANE_STEP": "w66/implement"})
        assert proc.returncode != 0
        assert proc.stderr.strip() == "a lane step cannot change a lane"
        assert path.read_bytes() == before
    proc = cli(root, cfg, "run", "w66")
    assert proc.returncode == 0, proc.stderr
    log = Path(load(root, "w66")["steps"][0]["log"]).read_text(encoding="utf-8")
    assert "LANE_STEP=w66/implement" in log
    assert "LANE_STEP=w66/verify" in Path(load(root, "w66")["steps"][1]["log"]).read_text(encoding="utf-8")


def test_p1_coordinator_extension_once_and_visible(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief, max_rounds="1")
    cli(root, cfg, "run", "w66", mode="review-fix")
    refused = cli(root, cfg, "next-round", "w66", "--brief", str(brief))
    assert refused.returncode == 2
    assert load(root, "w66")["state"] == "over_budget"
    granted = cli(root, cfg, "extend", "w66", "--reason", "need one more", "--by", "coordinator")
    assert granted.returncode == 0, granted.stderr
    doc = load(root, "w66")
    assert doc["max_rounds"] == 1
    assert len(doc["extensions"]) == 1
    phrase = "budget extended once by coordinator: need one more"
    assert phrase in cli(root, cfg, "status", "w66").stdout
    queued = json.loads(cli(root, cfg, "queue").stdout)
    assert queued[0]["why_waiting"] == f"changes requested; {phrase}"
    assert queued[0]["needs_owner"] is False
    board = json.loads(cli(root, cfg, "board").stdout)
    assert board["works"][0]["budget"] == phrase

    doc = load(root, "w66")
    doc["state"] = "over_budget"
    save(root, "w66", doc)
    again = cli(root, cfg, "extend", "w66", "--reason", "another", "--by", "coordinator")
    assert again.returncode != 0
    assert again.stderr.strip() == "the coordinator has used its one extension; the Owner decides"
    assert len(load(root, "w66")["extensions"]) == 1
    waiting = json.loads(cli(root, cfg, "queue").stdout)
    assert waiting[0]["needs_owner"] is True
    assert phrase in waiting[0]["why_waiting"]
    text = lane.__doc__ + "\n" + (HERE / "README.md").read_text(encoding="utf-8")
    assert "a process running as the same Unix user can still edit the lane directory" in text
    assert "stops accidents and a coordinator quietly extending" in text
    assert "another user or in a sandbox (ADR §12)" in text


def _pty_extend(root, cfg, typed: str) -> subprocess.CompletedProcess:
    import sys
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [sys.executable, str(LANE), "--root", str(root), "--config", str(cfg),
         "extend", "w66", "--reason", "owner allows it", "--by", "owner"],
        stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    os.close(slave)
    os.write(master, typed.encode())
    out, err = proc.communicate(timeout=10)
    os.close(master)
    return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)


def test_p1_owner_extension_needs_the_terminal(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief, max_rounds="1")
    doc = load(root, "w66")
    doc["state"] = "over_budget"
    save(root, "w66", doc)
    before = (root / "w66" / "lane.json").read_bytes()
    blocked = cli(root, cfg, "extend", "w66", "--reason", "owner allows it", "--by", "owner")
    assert blocked.returncode != 0
    assert "owner extension needs a terminal" in blocked.stderr
    assert (root / "w66" / "lane.json").read_bytes() == before
    other = cli(root, cfg, "extend", "w66", "--reason", "no", "--by", "agent")
    assert "extend --by accepts only coordinator or owner" in other.stderr
    assert (root / "w66" / "lane.json").read_bytes() == before

    wrong = _pty_extend(root, cfg, "nope\n")
    assert wrong.returncode != 0
    assert "owner extension was not confirmed" in wrong.stderr
    assert (root / "w66" / "lane.json").read_bytes() == before

    ok = _pty_extend(root, cfg, "w66\n")
    assert ok.returncode == 0, ok.stderr
    doc = load(root, "w66")
    assert doc["state"] == "changes_requested"
    assert doc["max_rounds"] == 1
    assert doc["extensions"][0]["by"] == "owner"
    assert doc["extensions"][0]["reason"] == "owner allows it"
    assert doc["extensions"][0]["round"] == 1
    nxt = cli(root, cfg, "next-round", "w66", "--brief", str(brief))
    assert nxt.returncode == 0, nxt.stderr
    assert load(root, "w66")["round"] == 2


def test_p1_argv_not_a_shell(tmp_path):
    root, _cfg, _ws, brief = scaffold(tmp_path)
    weird = tmp_path / 'job $(touch X) `touch Y` "q" dir'
    weird.mkdir()
    argv_out = tmp_path / "argv.json"
    script = tmp_path / "argv_child.py"
    script.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['ARGV_OUT']).write_text(json.dumps(sys.argv), encoding='utf-8')\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    verify = tmp_path / "argv_verify.py"
    verify.write_text("print('VERDICT: pass', flush=True)\n", encoding="utf-8")
    review = tmp_path / "argv_review.py"
    review.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "Path(sys.argv[1]).write_text('VERDICT: safe to merge\\nEND OF REPORT\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    py = __import__("sys").executable
    cfg = tmp_path / "argv-config.json"
    cfg.write_text(json.dumps({
        "implement": [py, str(script), "{workspace}"],
        "verify": [py, str(verify)],
        "review": [py, str(review), "{report}"],
        "who": {"implement": "Cursor", "verify": "verify-branch.sh", "review": "Codex"},
        "usual_min": {"implement": 1, "verify": 1, "review": 1},
        "pattern": {"implement": "argv", "verify": "argv", "review": "argv"},
    }), encoding="utf-8")
    new_lane(root, cfg, weird, brief, lane_id="inject")
    proc = cli(root, cfg, "run", "inject", extra_env={"ARGV_OUT": str(argv_out)})
    assert proc.returncode == 0, proc.stderr
    argv = json.loads(argv_out.read_text(encoding="utf-8"))
    assert argv[1:] == [str(weird)]
    assert not (weird / "X").exists()
    assert not (weird / "Y").exists()
    assert not (tmp_path / "X").exists()
    assert not (tmp_path / "Y").exists()
    assert not Path("X").exists()
    assert not Path("Y").exists()

    home = lane_state.render_argv(
        ["~/agent-work/verify-branch.sh", "say {workspace}"],
        workspace='a b " $(touch X)',
    )
    assert home[0] == str(Path("~/agent-work/verify-branch.sh").expanduser())
    assert home[1] == 'say a b " $(touch X)'
    assert len(home) == 2

    bad = tmp_path / "string-config.json"
    bad.write_text(json.dumps({
        "implement": "echo {workspace}",
        "verify": ["true"],
        "review": ["true"],
    }), encoding="utf-8")
    refused = cli(root, bad, "board")
    assert refused.returncode != 0
    assert '["bash", "~/agent-work/verify-branch.sh", "{workspace}", "bifrost-platform"]' in refused.stderr
    real = json.loads((HERE / "lane-config.json").read_text(encoding="utf-8"))
    assert real["verify"] == ["bash", "~/agent-work/verify-branch.sh", "{workspace}", "bifrost-platform"]
    assert "END OF REPORT" in real["review"][-1]
    assert all(isinstance(real[name], list) for name in ("implement", "verify", "review"))


def test_p2_runner_records_the_exit(tmp_path):
    done = tmp_path / "done"
    proc = subprocess.run(
        [__import__("sys").executable, str(HERE / "lane_runner.py"), str(done), "--",
         __import__("sys").executable, "-c", "import sys; sys.exit(7)"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 7
    body = json.loads(done.read_text(encoding="utf-8"))
    assert body["exit"] == 7
    assert body["ended_at"]
    assert lane_runner.main([str(done), "--"]) == 2


def test_p2_crash_recovery(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief, lane_id="start")
    doc = load(root, "start")
    attempt = root / "start" / "round-1" / "implement-1"
    attempt.mkdir(parents=True)
    doc["state"] = "implementing"
    doc["steps"] = [{
        "name": "implement", "round": 1, "attempt": 1, "state": "starting", "who": "Cursor",
        "start": doc["created_at"], "end": None, "pid": None, "lstart": None, "exit": None,
        "log": str(attempt / "log"), "done": str(attempt / "done"), "report": str(attempt / "report"),
        "heads": None,
    }]
    save(root, "start", doc)
    proc = cli(root, cfg, "run", "start")
    assert proc.returncode == 0, proc.stderr
    doc = load(root, "start")
    assert doc["state"] == "failed"
    assert len(doc["steps"]) == 1
    assert not (root / "start" / "round-1" / "implement-2").exists()
    assert events(root, "start")[-1]["why"] == "stopped while starting; check for a stray process"

    new_lane(root, cfg, ws, brief, lane_id="done")
    doc = load(root, "done")
    attempt = root / "done" / "round-1" / "implement-1"
    attempt.mkdir(parents=True)
    (attempt / "done").write_text(json.dumps({"exit": 0, "ended_at": doc["created_at"]}) + "\n", encoding="utf-8")
    (attempt / "log").write_text(
        json.dumps({"type": "result", "usage": {"inputTokens": 11, "outputTokens": 7}}) + "\n",
        encoding="utf-8",
    )
    doc["state"] = "implementing"
    doc["steps"] = [{
        "name": "implement", "round": 1, "attempt": 1, "state": "running", "who": "Cursor",
        "start": doc["created_at"], "end": None, "pid": unused_pid(), "lstart": "not-this-process",
        "exit": None, "log": str(attempt / "log"), "done": str(attempt / "done"),
        "report": str(attempt / "report"), "heads": None,
    }]
    save(root, "done", doc)
    proc = cli(root, cfg, "run", "done")
    assert proc.returncode == 0, proc.stderr
    doc = load(root, "done")
    assert doc["state"] == "passed"
    assert [step["attempt"] for step in doc["steps"] if step["name"] == "implement"] == [1]
    assert not (root / "done" / "round-1" / "implement-2").exists()

    sleeper = subprocess.Popen(
        [__import__("sys").executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    try:
        new_lane(root, cfg, ws, brief, lane_id="reuse")
        doc = load(root, "reuse")
        attempt = root / "reuse" / "round-1" / "implement-1"
        attempt.mkdir(parents=True)
        doc["state"] = "implementing"
        doc["steps"] = [{
            "name": "implement", "round": 1, "attempt": 1, "state": "running", "who": "Cursor",
            "start": doc["created_at"], "end": None, "pid": sleeper.pid, "lstart": "not-this-process",
            "exit": None, "log": str(attempt / "log"), "done": str(attempt / "done"),
            "report": str(attempt / "report"), "heads": None,
        }]
        save(root, "reuse", doc)
        started = time.time()
        proc = subprocess.run(
            [__import__("sys").executable, str(LANE), "--root", str(root), "--config", str(cfg), "run", "reuse"],
            capture_output=True, text=True, timeout=5,
            env={**os.environ, "LANE_FAKE": "pass"},
        )
        assert time.time() - started < 4
        assert proc.returncode == 0, proc.stderr
        assert load(root, "reuse")["state"] == "failed"
        assert events(root, "reuse")[-1]["why"] == "process vanished without an exit record"
        assert sleeper.poll() is None
    finally:
        stop_process(sleeper.pid)


def test_p2_abandon_stop_and_reattach(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief, lane_id="live")
    proc = cli(root, cfg, "run", "live", "--stall-seconds", "0.3", mode="stall", extra_env={"LANE_STALL_SLEEP": "30"})
    assert proc.returncode == 0, proc.stderr
    pid = load(root, "live")["steps"][0]["pid"]
    assert lane_steps.pid_alive(pid)
    abandoned = cli(root, cfg, "abandon", "live", "--reason", "drop it")
    assert abandoned.returncode == 0, abandoned.stderr
    doc = load(root, "live")
    assert doc["state"] == "failed"
    assert doc["abandoned"] is True
    assert doc["steps"][0]["terminated"]["signals"] == ["TERM"]
    assert events(root, "live")[-1]["why"] == "abandon: drop it; terminated the process group"
    deadline = time.time() + 2
    while lane_steps.pid_alive(pid) and time.time() < deadline:
        time.sleep(0.05)
    assert not lane_steps.pid_alive(pid)

    new_lane(root, cfg, ws, brief, lane_id="halt")
    proc = cli(root, cfg, "run", "halt", "--stall-seconds", "0.3", mode="stall", extra_env={"LANE_STALL_SLEEP": "30"})
    assert proc.returncode == 0, proc.stderr
    pid = load(root, "halt")["steps"][0]["pid"]
    stopped = cli(root, cfg, "stop", "halt", "--by", "owner")
    assert stopped.returncode == 0, stopped.stderr
    doc = load(root, "halt")
    assert doc["state"] == "failed"
    assert doc.get("abandoned") is not True
    assert events(root, "halt")[-1]["why"] == "stopped by owner"
    assert doc["steps"][0]["terminated"]["by"] == "owner"
    deadline = time.time() + 2
    while lane_steps.pid_alive(pid) and time.time() < deadline:
        time.sleep(0.05)
    assert not lane_steps.pid_alive(pid)

    new_lane(root, cfg, ws, brief, lane_id="again")
    proc = cli(root, cfg, "run", "again", "--stall-seconds", "0.25", mode="stall", extra_env={"LANE_STALL_SLEEP": "1.2"})
    assert proc.returncode == 0, proc.stderr
    first = load(root, "again")["steps"][0]
    assert first["end"] is None
    proc = cli(root, cfg, "run", "again", "--stall-seconds", "10")
    assert proc.returncode == 0, proc.stderr
    doc = load(root, "again")
    assert doc["state"] == "passed"
    implement = [step for step in doc["steps"] if step["name"] == "implement"]
    assert len(implement) == 1
    assert implement[0]["pid"] == first["pid"]
    assert implement[0]["attempt"] == 1

    ignorer = subprocess.Popen(
        [__import__("sys").executable, "-c",
         "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"],
        start_new_session=True,
    )
    try:
        signals = lane_steps.terminate_group(ignorer.pid, wait_s=0.3)
        assert signals == ["TERM", "KILL"]
        assert ignorer.wait(timeout=2) is not None
        assert lane_steps.terminate_group.__defaults__ == (lane_steps.TERM_WAIT_SECONDS,)
        assert lane_steps.TERM_WAIT_SECONDS == 5
    finally:
        if ignorer.poll() is None:
            stop_process(ignorer.pid)


def test_p2_queue_and_status_check(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief, lane_id="ready-one", title="Ready lane")
    new_lane(root, cfg, ws, brief, lane_id="failed-one", title="Failed lane")
    doc = load(root, "failed-one")
    doc["state"] = "failed"
    save(root, "failed-one", doc)
    new_lane(root, cfg, ws, brief, lane_id="gone", title="Abandoned lane")
    proc = cli(root, cfg, "abandon", "gone", "--reason", "not this one")
    assert proc.returncode == 0, proc.stderr
    new_lane(root, cfg, ws, brief, lane_id="budget", title="Budget lane")
    doc = load(root, "budget")
    doc["state"] = "over_budget"
    save(root, "budget", doc)
    new_lane(root, cfg, ws, brief, lane_id="owner-budget", title="Owner budget")
    doc = load(root, "owner-budget")
    doc["state"] = "over_budget"
    doc["extensions"] = [{"by": "coordinator", "reason": "need one more", "at": doc["created_at"], "round": 1}]
    save(root, "owner-budget", doc)
    new_lane(root, cfg, ws, brief, lane_id="busy", title="Busy lane")
    doc = load(root, "busy")
    doc["state"] = "implementing"
    save(root, "busy", doc)
    new_lane(root, cfg, ws, brief, lane_id="stuck", title="Stuck lane")
    proc = cli(root, cfg, "run", "stuck", "--stall-seconds", "0.3", mode="stall", extra_env={"LANE_STALL_SLEEP": "30"})
    assert proc.returncode == 0, proc.stderr
    pid = load(root, "stuck")["steps"][0]["pid"]
    try:
        queued = json.loads(cli(root, cfg, "queue").stdout)
        titles = [item["title"] for item in queued]
        assert "Ready lane" in titles
        assert "Failed lane" in titles
        assert "Budget lane" in titles
        assert "Owner budget" in titles
        assert "Stuck lane" in titles
        assert "Abandoned lane" not in titles
        assert "Busy lane" not in titles
        by_title = {item["title"]: item for item in queued}
        assert by_title["Ready lane"]["why_waiting"] == "ready to run"
        assert by_title["Ready lane"]["needs_owner"] is False
        assert by_title["Failed lane"]["why_waiting"] == "failed; a person has to decide"
        assert by_title["Budget lane"]["why_waiting"] == "over the round budget"
        assert by_title["Budget lane"]["needs_owner"] is False
        assert by_title["Owner budget"]["needs_owner"] is True
        assert "budget extended once by coordinator: need one more" in by_title["Owner budget"]["why_waiting"]
        assert "stalled" in by_title["Stuck lane"]["why_waiting"]
        assert by_title["Stuck lane"]["needs_owner"] is False
        os.killpg(pid, signal.SIGKILL)
        deadline = time.time() + 2
        while lane_steps.pid_alive(pid) and time.time() < deadline:
            time.sleep(0.05)
        status = cli(root, cfg, "status", "stuck")
        assert "state=running (process gone)" in status.stdout
        check = cli(root, cfg, "status", "--check")
        assert check.returncode == 1
        one = cli(root, cfg, "status", "ready-one", "--check")
        assert one.returncode == 0
    finally:
        stop_process(pid)


def test_p2_strict_verdicts(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief, lane_id="buried")
    cli(root, cfg, "run", "buried", mode="verify-buried")
    assert load(root, "buried")["state"] == "failed"
    assert events(root, "buried")[-1]["why"] == "verification produced no verdict"
    assert [step["name"] for step in load(root, "buried")["steps"]] == ["implement", "verify"]

    new_lane(root, cfg, ws, brief, lane_id="final-pass")
    cli(root, cfg, "run", "final-pass", mode="verify-then-pass")
    assert load(root, "final-pass")["state"] == "passed"

    new_lane(root, cfg, ws, brief, lane_id="cut")
    cli(root, cfg, "run", "cut", mode="review-cut")
    assert load(root, "cut")["state"] == "failed"
    assert events(root, "cut")[-1]["why"] == "review produced no verdict"
    assert load(root, "cut")["verdicts"]["P1"] == 1

    new_lane(root, cfg, ws, brief, lane_id="late")
    cli(root, cfg, "run", "late", mode="review-late")
    assert load(root, "late")["state"] == "failed"
    assert events(root, "late")[-1]["why"] == "review produced no verdict"

    new_lane(root, cfg, ws, brief, lane_id="bom")
    cli(root, cfg, "run", "bom", mode="review-bom")
    assert load(root, "bom")["state"] == "passed"
    assert load(root, "bom")["verdicts"]["entries"][-1]["verdict"] == "VERDICT: safe to merge"
