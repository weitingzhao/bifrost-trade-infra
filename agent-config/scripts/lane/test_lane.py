"""Lane state machine. No network and no real agents: commands are a local fake."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import lane_state

HERE = Path(__file__).resolve().parent
LANE = HERE / "lane.py"
FAKE = r"""#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path

role, _ws, _brief, _round, report = sys.argv[1:6]
mode = os.environ.get("LANE_FAKE", "pass")
delay = float(os.environ.get("LANE_SLEEP", "0") or 0)
stall_for = float(os.environ.get("LANE_STALL_SLEEP", "8") or 8)
step = os.environ.get("LANE_STEP")
if step:
    print(f"LANE_STEP={step}", flush=True)
if delay:
    time.sleep(delay)

if role == "implement":
    if mode == "stall":
        print("working", flush=True)
        time.sleep(stall_for)
        sys.exit(0)
    print(json.dumps({"type": "result", "usage": {"inputTokens": 11, "outputTokens": 7}}), flush=True)
    sys.exit(3 if mode == "impl-fail" else 0)

if role == "verify":
    if mode == "verify-none":
        print("no verdict here", flush=True)
        sys.exit(0)
    if mode == "verify-fail":
        print("VERDICT: pass", flush=True)
        print("VERDICT: FAIL (2 checks failed or produced no result)", flush=True)
        sys.exit(0)
    if mode == "verify-exit":
        print("VERDICT: pass", flush=True)
        sys.exit(7)
    if mode == "verify-buried":
        print("VERDICT: pass", flush=True)
        print("still talking", flush=True)
        sys.exit(0)
    if mode == "verify-then-pass":
        print("VERDICT: FAIL buried", flush=True)
        print("VERDICT: pass", flush=True)
        sys.exit(0)
    print("checked", flush=True)
    print("VERDICT: pass", flush=True)
    sys.exit(0)

if role == "review":
    if mode == "review-none":
        sys.exit(0)
    if mode == "review-bad":
        Path(report).write_text("not a verdict\nP1 ignored\n", encoding="utf-8")
        sys.exit(0)
    if mode == "review-cut":
        Path(report).write_text("VERDICT: safe to merge\nP1 still open\n", encoding="utf-8")
        sys.exit(0)
    if mode == "review-late":
        Path(report).write_text("notes first\nVERDICT: safe to merge\nEND OF REPORT\n", encoding="utf-8")
        sys.exit(0)
    if mode == "review-exit":
        Path(report).write_text("VERDICT: safe to merge\nEND OF REPORT\n", encoding="utf-8")
        sys.exit(9)
    if mode == "review-bom":
        body = "\n\nVERDICT: safe to merge\nnote\nEND OF REPORT\n"
        Path(report).write_bytes(b"\xef\xbb\xbf" + body.encode())
        sys.exit(0)
    if mode == "review-fix":
        text = "VERDICT: fix first\nP1 the gate\nP2 a\nP2 b\nP3 nit\nEND OF REPORT\n"
    else:
        text = "VERDICT: safe to merge\nP3 note only\nEND OF REPORT\n"
    Path(report).write_text(text, encoding="utf-8")
    print("tokens used\n1,234", flush=True)
    sys.exit(0)

sys.exit("unknown role")
"""


def write_config(directory: Path, fake: Path) -> Path:
    py = sys.executable
    commands = {
        name: [py, str(fake), name, "{workspace}", "{brief}", "{round}", "{report}"]
        for name in ("implement", "verify", "review")
    }
    cfg = {
        **commands,
        "who": {"implement": "Cursor", "verify": "verify-branch.sh", "review": "Codex"},
        "usual_min": {"implement": 30, "verify": 5, "review": 10},
        "pattern": {
            "implement": "fake.py implement {id}",
            "verify": "fake.py verify {id}",
            "review": "fake.py review {id}",
        },
    }
    path = directory / "lane-config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def scaffold(tmp_path: Path):
    root = tmp_path / "lanes"
    root.mkdir()
    fake = tmp_path / "fake.py"
    fake.write_text(FAKE, encoding="utf-8")
    cfg = write_config(tmp_path, fake)
    ws = tmp_path / "ws"
    ws.mkdir()
    brief = tmp_path / "TASK.md"
    brief.write_text("do the work\n", encoding="utf-8")
    return root, cfg, ws, brief


def cli(root: Path, cfg: Path, *args: str, mode: str = "pass", sleep: str = "0", check: bool = False, extra_env: dict | None = None):
    env = os.environ.copy()
    env["LANE_FAKE"] = mode
    env["LANE_SLEEP"] = sleep
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(LANE), "--root", str(root), "--config", str(cfg), *args],
        capture_output=True, text=True, env=env, check=check, stdin=subprocess.DEVNULL,
    )


def new_lane(root, cfg, ws, brief, lane_id="w66", title="Dispatch chain", max_rounds="2"):
    proc = cli(
        root, cfg, "new", "--id", lane_id, "--work", "W-66,W-62", "--title", title,
        "--workspace", str(ws), "--branch", "w31/w66-lane", "--brief", str(brief),
        "--max-rounds", max_rounds,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads((root / lane_id / "lane.json").read_text(encoding="utf-8"))


def load(root: Path, lane_id: str) -> dict:
    return json.loads((root / lane_id / "lane.json").read_text(encoding="utf-8"))


def events(root: Path, lane_id: str) -> list[dict]:
    text = (root / lane_id / "events.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_help():
    proc = subprocess.run([sys.executable, str(LANE), "--help"], capture_output=True, text=True)
    assert proc.returncode == 0
    for name in ("new", "run", "status", "next-round", "extend", "abandon", "stop", "board", "queue"):
        assert name in proc.stdout


def test_happy_path_passed(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    doc = new_lane(root, cfg, ws, brief)
    for key in ("id", "work", "title", "repo_dirs", "branch", "brief", "round", "max_rounds",
                "state", "steps", "verdicts", "usage", "created_at", "updated_at"):
        assert key in doc
    assert doc["state"] == "ready"
    assert doc["round"] == 1
    assert doc["max_rounds"] == 2
    assert doc["work"] == ["W-66", "W-62"]
    assert doc["repo_dirs"]["workspace"] == str(ws)

    proc = cli(root, cfg, "run", "w66")
    assert proc.returncode == 0, proc.stderr
    doc = load(root, "w66")
    assert doc["state"] == "passed"
    assert [step["name"] for step in doc["steps"]] == ["implement", "verify", "review"]
    assert [step["exit"] for step in doc["steps"]] == [0, 0, 0]
    assert doc["usage"]["inputTokens"] == 11
    assert doc["usage"]["outputTokens"] == 7
    assert doc["usage"]["tokens"] == 1234
    assert doc["verdicts"]["P3"] == 1
    assert doc["verdicts"]["rounds"][-1]["review"] == "safe to merge"
    for step in doc["steps"]:
        done = json.loads(Path(step["done"]).read_text(encoding="utf-8"))
        assert done["exit"] == 0
        assert done["ended_at"]
        assert step["start"] and step["end"] and step["log"]
        assert f"/{step['name']}-{step['attempt']}/log" in step["log"].replace("\\", "/")
    tos = [event["to"] for event in events(root, "w66")]
    assert tos == ["ready", "implementing", "verifying", "reviewing", "passed"]
    for event in events(root, "w66"):
        assert {"time", "from", "to", "why"} <= set(event)

    status = cli(root, cfg, "status", "w66")
    assert "state=passed" in status.stdout
    assert "round=1" in status.stdout
    assert "step=review" in status.stdout
    listed = json.loads(cli(root, cfg, "status", "--json").stdout)
    assert listed[0]["state"] == "passed"
    assert listed[0]["step"] == "review"


def test_verify_fail_uses_last_verdict(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief)
    proc = cli(root, cfg, "run", "w66", mode="verify-fail")
    assert proc.returncode == 0, proc.stderr
    doc = load(root, "w66")
    assert doc["state"] == "failed"
    assert [step["name"] for step in doc["steps"]] == ["implement", "verify"]
    why = events(root, "w66")[-1]
    assert why["to"] == "failed"
    assert why["why"] == "VERDICT: FAIL (2 checks failed or produced no result)"


def test_verify_without_verdict(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief)
    cli(root, cfg, "run", "w66", mode="verify-none")
    doc = load(root, "w66")
    assert doc["state"] == "failed"
    assert events(root, "w66")[-1]["why"] == "verification produced no verdict"


def test_review_fix_first_and_bad_report(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief, lane_id="fix")
    cli(root, cfg, "run", "fix", mode="review-fix")
    doc = load(root, "fix")
    assert doc["state"] == "changes_requested"
    assert doc["verdicts"]["P1"] == 1
    assert doc["verdicts"]["P2"] == 2
    assert doc["verdicts"]["P3"] == 1

    new_lane(root, cfg, ws, brief, lane_id="bad")
    cli(root, cfg, "run", "bad", mode="review-bad")
    assert load(root, "bad")["state"] == "failed"
    assert events(root, "bad")[-1]["why"] == "review produced no verdict"
    assert load(root, "bad")["verdicts"]["P1"] == 1

    new_lane(root, cfg, ws, brief, lane_id="none")
    cli(root, cfg, "run", "none", mode="review-none")
    assert events(root, "none")[-1]["why"] == "review produced no verdict"


def test_round_budget_extend_and_one_more(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief, max_rounds="2")
    second = tmp_path / "round2.md"
    second.write_text("round two\n", encoding="utf-8")
    third = tmp_path / "round3.md"
    third.write_text("round three\n", encoding="utf-8")

    cli(root, cfg, "run", "w66", mode="review-fix")
    assert load(root, "w66")["state"] == "changes_requested"
    nxt = cli(root, cfg, "next-round", "w66", "--brief", str(second))
    assert nxt.returncode == 0, nxt.stderr
    assert load(root, "w66")["round"] == 2
    assert load(root, "w66")["state"] == "implementing"
    assert load(root, "w66")["brief"] == str(second)

    cli(root, cfg, "run", "w66", mode="review-fix")
    assert load(root, "w66")["state"] == "changes_requested"
    refused = cli(root, cfg, "next-round", "w66", "--brief", str(third))
    assert refused.returncode == 2
    assert load(root, "w66")["state"] == "over_budget"
    assert load(root, "w66")["round"] == 2
    assert events(root, "w66")[-1]["why"] == "round budget exhausted"

    extended = cli(root, cfg, "extend", "w66", "--reason", "one more pass", "--by", "coordinator")
    assert extended.returncode == 0, extended.stderr
    doc = load(root, "w66")
    assert doc["state"] == "changes_requested"
    assert doc["max_rounds"] == 2
    assert doc["extensions"] == [{
        "by": "coordinator",
        "reason": "one more pass",
        "at": doc["extensions"][0]["at"],
        "round": 2,
    }]
    assert events(root, "w66")[-1]["why"] == "extend by coordinator: one more pass"

    again = cli(root, cfg, "next-round", "w66", "--brief", str(third))
    assert again.returncode == 0, again.stderr
    assert load(root, "w66")["round"] == 3
    cli(root, cfg, "run", "w66", mode="review-fix")
    assert load(root, "w66")["state"] == "changes_requested"
    stopped = cli(root, cfg, "next-round", "w66", "--brief", str(second))
    assert stopped.returncode == 2
    assert load(root, "w66")["state"] == "over_budget"
    assert load(root, "w66")["round"] == 3
    assert load(root, "w66")["max_rounds"] == 2
    assert len(load(root, "w66")["extensions"]) == 1


def test_stalled_step_leaves_process_running(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief)
    proc = cli(root, cfg, "run", "w66", "--stall-seconds", "0.4", mode="stall")
    assert proc.returncode == 0, proc.stderr
    doc = load(root, "w66")
    try:
        assert doc["state"] == "stalled"
        step = doc["steps"][0]
        assert step["name"] == "implement"
        assert step["end"] is None
        assert step["exit"] is None
        assert not Path(step["done"]).exists()
        assert pid_alive(step["pid"])
        assert events(root, "w66")[-1]["to"] == "stalled"
    finally:
        stop_process(doc["steps"][0]["pid"])


def test_vanished_process(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief)
    path = root / "w66" / "lane.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    pid = unused_pid()
    log = root / "w66" / "round-1" / "implement.log"
    done = root / "w66" / "round-1" / "implement.done"
    doc["state"] = "implementing"
    doc["steps"] = [{
        "name": "implement",
        "round": 1,
        "who": "Cursor",
        "start": doc["created_at"],
        "end": None,
        "pid": pid,
        "exit": None,
        "log": str(log),
        "done": str(done),
    }]
    path.write_text(json.dumps(doc), encoding="utf-8")
    proc = cli(root, cfg, "run", "w66")
    assert proc.returncode == 0, proc.stderr
    done_doc = load(root, "w66")
    assert done_doc["state"] == "failed"
    assert done_doc["steps"][0]["vanished"] is True
    assert events(root, "w66")[-1]["why"] == "process vanished without an exit record"


def test_atomic_rewrite_survives_crash(tmp_path, monkeypatch):
    path = tmp_path / "lane.json"
    lane_state.atomic_write_json(path, {"n": 1, "state": "ready"})
    assert list(tmp_path.glob("lane.json.*.tmp")) == []

    def crash(src, dst):
        raise OSError("simulated crash before rename")

    monkeypatch.setattr(lane_state.os, "replace", crash)
    with pytest.raises(OSError, match="simulated crash"):
        lane_state.atomic_write_json(path, {"n": 2, "state": "implementing"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"n": 1, "state": "ready"}
    tmps = list(tmp_path.glob("lane.json.*.tmp"))
    assert len(tmps) == 1
    assert tmps[0].parent == path.parent
    assert str(os.getpid()) in tmps[0].name
    assert tmps[0].name != "lane.json.tmp"
    assert json.loads(tmps[0].read_text(encoding="utf-8"))["n"] == 2


def test_board_and_queue(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief, lane_id="older", title="Older lane")
    cli(root, cfg, "run", "older", mode="review-fix")
    time.sleep(0.01)
    new_lane(root, cfg, ws, brief, lane_id="newer", title="Newer lane")
    new_lane(root, cfg, ws, brief, lane_id="done", title="Done lane")
    cli(root, cfg, "run", "done", mode="pass")

    queue = json.loads(cli(root, cfg, "queue").stdout)
    assert [item["title"] for item in queue] == ["Older lane", "Newer lane"]
    assert queue[0]["why_waiting"] == "changes requested"
    assert queue[0]["needs_owner"] is False
    assert queue[1]["why_waiting"] == "ready to run"
    assert queue[1]["needs_owner"] is False

    board = json.loads(cli(root, cfg, "board").stdout)
    by_short = {work["short"]: work for work in board["works"]}
    assert set(by_short) == {"older", "newer", "done"}
    older = by_short["older"]
    assert older["round"] == 1
    assert older["goal"] == "W-66, W-62: Older lane"
    assert [step["name"] for step in older["steps"]] == ["implement", "verify", "review"]
    implement = older["steps"][0]
    assert implement["who"] == "Cursor"
    assert implement["usual_min"] == 30
    assert implement["pattern"] == "fake.py implement older"
    assert implement["progress"].endswith("implement-1/log")
    assert implement["done"].endswith("implement-1/done")
    assert json.loads(Path(implement["done"]).read_text(encoding="utf-8"))["exit"] == 0
    assert len(by_short["done"]["steps"]) == 3
    assert len(by_short["newer"]["steps"]) == 3


def test_two_lanes_do_not_touch(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    other = tmp_path / "ws-b"
    other.mkdir()
    new_lane(root, cfg, ws, brief, lane_id="lane-a", title="Lane A")
    cli(root, cfg, "run", "lane-a")
    before = snapshot(root / "lane-a")

    new_lane(root, cfg, other, brief, lane_id="lane-b", title="Lane B")
    proc = cli(root, cfg, "run", "lane-b", mode="verify-fail")
    assert proc.returncode == 0, proc.stderr
    assert snapshot(root / "lane-a") == before
    assert load(root, "lane-a")["state"] == "passed"
    assert load(root, "lane-b")["state"] == "failed"
    assert "lane-b" not in (root / "lane-a" / "lane.json").read_text(encoding="utf-8")
    assert "lane-a" not in (root / "lane-b" / "lane.json").read_text(encoding="utf-8")

    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    brief_l = tmp_path / "L.md"
    brief_r = tmp_path / "R.md"
    brief_l.write_text("left\n", encoding="utf-8")
    brief_r.write_text("right\n", encoding="utf-8")
    new_lane(root, cfg, left, brief_l, lane_id="par-a", title="Parallel A")
    new_lane(root, cfg, right, brief_r, lane_id="par-b", title="Parallel B")
    env = os.environ.copy()
    env["LANE_FAKE"] = "pass"
    env["LANE_SLEEP"] = "0.2"

    def spawn(lane_id):
        return subprocess.Popen(
            [sys.executable, str(LANE), "--root", str(root), "--config", str(cfg), "run", lane_id],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
        )

    procs = [spawn("par-a"), spawn("par-b")]
    for proc in procs:
        out, err = proc.communicate(timeout=30)
        assert proc.returncode == 0, err
    assert load(root, "par-a")["state"] == "passed"
    assert load(root, "par-b")["state"] == "passed"
    assert "par-b" not in (root / "par-a" / "lane.json").read_text(encoding="utf-8")
    assert "par-a" not in (root / "par-b" / "lane.json").read_text(encoding="utf-8")


def test_abandon_and_implement_failure(tmp_path):
    root, cfg, ws, brief = scaffold(tmp_path)
    new_lane(root, cfg, ws, brief, lane_id="stop")
    proc = cli(root, cfg, "abandon", "stop", "--reason", "no longer needed")
    assert proc.returncode == 0, proc.stderr
    assert load(root, "stop")["state"] == "failed"
    assert events(root, "stop")[-1]["why"] == "abandon: no longer needed"

    new_lane(root, cfg, ws, brief, lane_id="boom")
    cli(root, cfg, "run", "boom", mode="impl-fail")
    doc = load(root, "boom")
    assert doc["state"] == "failed"
    assert doc["steps"][0]["exit"] == 3
    assert json.loads(Path(doc["steps"][0]["done"]).read_text(encoding="utf-8"))["exit"] == 3
    assert events(root, "boom")[-1]["why"] == "implement exited 3"
    assert not (root / "boom" / "round-1" / "verify.log").exists()


def snapshot(directory: Path) -> dict:
    out = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(directory))] = path.read_bytes()
    return out


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def unused_pid() -> int:
    pid = 2_000_000_000
    while pid_alive(pid):
        pid += 1
    return pid


def stop_process(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
