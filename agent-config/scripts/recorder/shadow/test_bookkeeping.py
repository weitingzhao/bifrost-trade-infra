"""Bookkeeping fallback when ``rec.py`` has no ``run``. Events come from the real commands."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

SHADOW = Path(__file__).resolve().parent / "shadow.py"


def _token() -> str:
    return "sj" + uuid.uuid4().hex[:12]


def _run(root: Path, *args, check=True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, str(SHADOW), "--root", str(root), *args],
        capture_output=True,
        text=True,
        env=env,
    )
    if check and proc.returncode != 0:
        raise AssertionError((proc.returncode, proc.stdout, proc.stderr))
    return proc


def _job(token: str, seconds: float) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", "import time,sys; time.sleep(float(sys.argv[1]))", str(seconds), token]
    )


def _events(root: Path) -> list[dict]:
    rows = []
    if not root.is_dir():
        return rows
    for path in sorted(root.glob("*/events.jsonl")):
        if path.parent.name.startswith("_") or path.parent.name.startswith("."):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append(json.loads(line.split(" ", 1)[1]))
    return rows


def _wait_finished(root: Path, timeout: float) -> list[dict]:
    deadline = time.monotonic() + timeout
    rows = _events(root)
    while time.monotonic() < deadline:
        rows = _events(root)
        if any(event.get("type") == "step_finished" for event in rows):
            return rows
        time.sleep(0.1)
    return rows


def _step(root: Path) -> dict:
    mapping = json.loads((root / "map.json").read_text(encoding="utf-8"))
    return mapping["steps"][0]


def _diffs(root: Path) -> list[dict]:
    path = root / "diff.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _stop(root: Path, job: subprocess.Popen | None = None) -> None:
    if job is not None and job.poll() is None:
        job.kill()
        try:
            job.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    path = root / "map.json"
    if not path.is_file():
        return
    me = {os.getpid(), os.getppid()}
    for step in json.loads(path.read_text(encoding="utf-8")).get("steps") or []:
        pid = step.get("pid")
        if type(pid) is int and pid not in me:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        done = step.get("done")
        if type(done) is not str or not done:
            continue
        found = subprocess.run(["pgrep", "-f", done], capture_output=True, text=True)
        for line in found.stdout.splitlines():
            if not line.strip().isdigit():
                continue
            child = int(line.strip())
            if child in me:
                continue
            try:
                os.kill(child, signal.SIGTERM)
            except OSError:
                pass


def _board(path: Path, step: dict) -> None:
    document = {"works": [{"title": "活", "steps": [step]}], "owner_all": []}
    path.write_text(json.dumps(document), encoding="utf-8")


def test_help_has_no_run():
    import shadow

    found = shadow._subcommands()
    assert "run" not in found
    assert {"open", "declare", "start", "finish"} <= found


def test_exit_0(tmp_path):
    token = _token()
    root = tmp_path / "root"
    done = tmp_path / "job.done"
    done.write_text("exit=0\nexit=9\n", encoding="utf-8")
    job = _job(token, 0.4)
    try:
        proc = _run(
            root,
            "start-step",
            "--title",
            "活",
            "--step",
            "一步",
            "--pattern",
            token,
            "--done",
            str(done),
            "--poll",
            "0.2",
        )
        assert proc.returncode == 0
        assert _step(root)["via"] == "bookkeeping"
        rows = _wait_finished(root, 15)
        finished = [event for event in rows if event.get("type") == "step_finished"]
        assert len(finished) == 1
        assert finished[0]["reported"] == "finished"
        assert finished[0]["quote"] == "exit=0"
        declared = next(event for event in rows if event.get("type") == "step_declared")
        assert declared["watch"] == "none"
        assert declared["name"] == "一步"
        assert any(event.get("type") == "step_started" for event in rows)
        started = next(event["at"] for event in rows if event.get("type") == "step_started")
        ended = finished[0]["at"]
        board = tmp_path / "status.json"
        _board(board, {"name": "一步", "state": "done", "started": started, "ended": ended})
        compared = _run(root, "compare", "--board", str(board))
        assert compared.stdout.strip() == "steps=1 owners=0 differences=0"
        assert _diffs(root) == []
        assert job.wait(timeout=5) == 0
    finally:
        _stop(root, job)


def test_exit_9(tmp_path):
    token = _token()
    root = tmp_path / "root"
    done = tmp_path / "job.done"
    done.write_text("noise exit=9 tail\n", encoding="utf-8")
    job = _job(token, 0.4)
    try:
        _run(
            root,
            "start-step",
            "--title",
            "活",
            "--step",
            "一步",
            "--pattern",
            token,
            "--done",
            str(done),
            "--poll",
            "0.2",
        )
        rows = _wait_finished(root, 15)
        finished = next(event for event in rows if event.get("type") == "step_finished")
        assert finished["reported"] == "failed"
        assert finished["quote"] == "exit=9"
        board = tmp_path / "status.json"
        _board(
            board,
            {
                "name": "一步",
                "state": "failed",
                "started": next(event["at"] for event in rows if event["type"] == "step_started"),
                "ended": finished["at"],
            },
        )
        compared = _run(root, "compare", "--board", str(board))
        assert "differences=0" in compared.stdout
        assert _diffs(root) == []
        assert job.wait(timeout=5) == 0
    finally:
        _stop(root, job)


def test_vanished_without_a_marker(tmp_path):
    token = _token()
    root = tmp_path / "root"
    done = tmp_path / "missing.done"
    started = time.monotonic()
    try:
        _run(
            root,
            "start-step",
            "--title",
            "活",
            "--step",
            "一步",
            "--pattern",
            token,
            "--done",
            str(done),
            "--poll",
            "1",
        )
        rows = _wait_finished(root, 50)
        elapsed = time.monotonic() - started
        finished = [event for event in rows if event.get("type") == "step_finished"]
        assert len(finished) == 1
        assert finished[0]["reported"] == "failed"
        assert finished[0]["quote"] == "exit=70"
        assert elapsed >= 30
        assert elapsed < 45
    finally:
        _stop(root)


def test_supervisor_killed_while_the_job_runs(tmp_path):
    token = _token()
    root = tmp_path / "root"
    done = tmp_path / "job.done"
    job = _job(token, 60)
    try:
        proc = _run(
            root,
            "start-step",
            "--title",
            "活",
            "--step",
            "一步",
            "--pattern",
            token,
            "--done",
            str(done),
            "--poll",
            "0.2",
        )
        assert proc.returncode == 0
        step = _step(root)
        assert step["via"] == "bookkeeping"
        pid = step["pid"]
        assert type(pid) is int
        os.kill(pid, 0)
        rows = _events(root)
        assert any(event.get("type") == "step_started" for event in rows)
        assert not any(event.get("type") == "step_finished" for event in rows)
        started = next(event["at"] for event in rows if event.get("type") == "step_started")
        board = tmp_path / "status.json"
        _board(board, {"name": "一步", "state": "running", "started": started})
        alive = _run(root, "compare", "--board", str(board))
        assert alive.stdout.strip() == "steps=1 owners=0 differences=0"
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("supervisor still alive")
        time.sleep(0.3)
        assert not any(event.get("type") == "step_finished" for event in _events(root))
        assert job.poll() is None
        gone = _run(root, "compare", "--board", str(board))
        assert "started_supervisor_gone" not in alive.stdout
        state = [row for row in _diffs(root) if row["field"] == "state"]
        assert len(state) == 1
        assert state[0]["board"] == "running"
        assert state[0]["recorder"] == "started_supervisor_gone"
        assert state[0]["facts"]["process"] is True
        assert "differences=1" in gone.stdout
    finally:
        _stop(root, job)
