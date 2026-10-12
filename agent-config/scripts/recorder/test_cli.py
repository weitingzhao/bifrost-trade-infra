"""Thin CLI slice; real children and locks, with bounded waits and cleanup."""
from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from commands import _write
from harness import APPR
from read import fold_total
from runtime import read_root

REC = Path(__file__).with_name("rec.py")


def cli(root, *args, expected=0):
    result = subprocess.run([sys.executable, str(REC), "--root", str(root), *args],
                            capture_output=True, text=True, timeout=12)
    assert result.returncode == expected, result.stdout + result.stderr
    return result


def opened(root):
    return json.loads(cli(root, "open", "--work", "w1", "--title", "Work").stdout)


def run_args(root, name, command):
    return [sys.executable, str(REC), "--root", str(root), "run", "--work", "w1",
            "--name", name, "--kind", "other", "--who", "Codex", "--", *command]


def wait_file(path):
    deadline = time.monotonic() + 5
    while not path.exists():
        assert time.monotonic() < deadline, str(path)
        time.sleep(.02)


def folded(root):
    return json.loads(cli(root, "fold").stdout)


def test_owner_open_cli(tmp_path):
    root = tmp_path
    opened(root)
    event = json.loads(cli(root, "owner-open", "--work", "w1", "--title", "Look",
                           "--can-act", "yes", "--where", "terminal", "--command", "echo ok").stdout)
    item = folded(root)["owner_all"][0]
    assert event["type"] == "owner_wait_opened"
    assert item["commands"] == ["echo ok"]
    assert item["since"] == event["at"]


def test_fold_cli_total_read_only(tmp_path):
    opened(tmp_path)
    (tmp_path / "empty").mkdir()
    before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file()}
    logs, obs, unread = read_root(tmp_path)
    result = json.loads(cli(tmp_path, "fold", "--now", "10").stdout)
    assert result == fold_total(logs, obs, 10, unread).document()
    assert before == {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file()}
    missing = tmp_path / "missing"
    cli(missing, "fold", expected=2)
    assert not missing.exists()


def test_cli_end_to_end(tmp_path):
    opened(tmp_path)
    for name, code in (("ok", 0), ("bad", 9)):
        result = subprocess.run(run_args(tmp_path, name, [sys.executable, "-c", f"raise SystemExit({code})"]),
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == code, result.stderr
    owner = json.loads(cli(tmp_path, "owner-open", "--work", "w1", "--title", "Look", "--can-act", "yes").stdout)
    doc = folded(tmp_path)
    steps = {s["name"]: s for s in doc["works"][0]["steps"]}
    assert steps["ok"]["state"] == "done" and steps["ok"]["exit_code"] == 0
    assert steps["bad"]["state"] == "failed" and steps["bad"]["exit_code"] == 9
    assert doc["owner_all"][0]["since"] == owner["at"]
    pidfile = tmp_path / "pid"
    child_code = f"import os,time; from pathlib import Path; Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(30)"
    wrapper = subprocess.Popen(run_args(tmp_path, "killed", [sys.executable, "-c", child_code]),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        wait_file(pidfile)
        wrapper.kill()
        wrapper.communicate(timeout=5)
        os.kill(int(pidfile.read_text()), 0)  # Child still lives: it did not inherit alive.lock.
        cli(tmp_path, "observe")
        doc = folded(tmp_path)
        step = next(s for s in doc["works"][0]["steps"] if s["name"] == "killed")
        assert step["state"] == "dead" and step["reason"] == "wrapper_gone"
        assert "exit_code" not in step
        cli(tmp_path, "observe")  # An already-dead run is not appended twice.
        assert folded(tmp_path)["works"][0]["defects"] == []
    finally:
        if wrapper.poll() is None:
            wrapper.kill()
            wrapper.communicate(timeout=5)
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_run_signal_forwarding(tmp_path):
    opened(tmp_path)
    ready = tmp_path / "ready"
    code = f"import signal,time; from pathlib import Path; signal.signal(signal.SIGTERM,lambda *a:exit(9)); Path({str(ready)!r}).touch(); time.sleep(30)"
    wrapper = subprocess.Popen(run_args(tmp_path, "signal", [sys.executable, "-c", code]))
    try:
        wait_file(ready)
        wrapper.terminate()
        assert wrapper.wait(timeout=5) == 9
        assert folded(tmp_path)["works"][0]["steps"][0]["exit_code"] == 9
    finally:
        if wrapper.poll() is None:
            wrapper.kill()
            wrapper.wait(timeout=5)


def test_run_spawn_failure(tmp_path):
    opened(tmp_path)
    result = subprocess.run(run_args(tmp_path, "missing", [str(tmp_path / "no-command")]), capture_output=True, timeout=10)
    assert result.returncode == 127
    step = folded(tmp_path)["works"][0]["steps"][0]
    assert step["exit_code"] == 127 and step["quote"]


def test_run_lock_busy_still_starts_child(tmp_path):
    opened(tmp_path)
    lock = (tmp_path / "w1" / "lock").open("r+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    marker = tmp_path / "ran"
    start = time.monotonic()
    try:
        result = subprocess.run(run_args(tmp_path, "busy", [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch(); exit(9)"]),
                                capture_output=True, text=True, timeout=8)
        assert result.returncode == 9 and marker.exists()
        assert 1.8 <= time.monotonic() - start < 6
        assert "start not recorded" in result.stderr
    finally:
        lock.close()
    assert folded(tmp_path)["works"][0]["steps"] == []


def test_observe_unrecorded_and_platform_notice(tmp_path):
    opened(tmp_path)
    _write(tmp_path, "w1", [dict(type="owner_wait_opened", wait_id="aabbccdd", title="Bound",
           ref={"kind": "approval", "id": APPR})], "coordinator", "fixture")
    run = tmp_path / "w1" / "runs" / "11111111-22222222"
    run.mkdir(parents=True)
    lock = (run / "alive.lock").open("w+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = cli(tmp_path, "observe")
        assert result.stderr.count("platform references were not read") == 1
        assert json.loads(result.stdout)["unrecorded"] == [dict(work_id="w1", step_id="11111111", run_id="22222222")]
        assert folded(tmp_path)["works"][0]["unrecorded_runs"] == 1
    finally:
        lock.close()
    assert json.loads(cli(tmp_path, "observe").stdout)["unrecorded"] == []


def test_owner_since_ready_does_not_drift(tmp_path):
    opened(tmp_path)
    event = json.loads(cli(tmp_path, "owner-open", "--work", "w1", "--title", "Later", "--can-act", "not_yet").stdout)
    assert folded(tmp_path)["owner_all"][0]["since"] == event["at"]
    ready = json.loads(cli(tmp_path, "owner-ready", "--work", "w1", "--wait", event["wait_id"]).stdout)
    cli(tmp_path, "note", "--work", "w1", "--text", "Again")
    assert folded(tmp_path)["owner_all"][0]["since"] == ready["at"]


@pytest.mark.parametrize("mode", ["refused", "partial", "collision"])
def test_run_recording_failure_still_starts_child(tmp_path, mode):
    opened(tmp_path)
    marker = tmp_path / "ran"
    collision = tmp_path / "w1" / "runs" / "11111111-11111111"
    if mode == "collision":
        collision.mkdir(parents=True)
        (collision / "stdout").write_text("preserve")
    driver = f'''
import sys
sys.path.insert(0, {str(REC.parent)!r})
import runtime, rec
from commands import RecorderError
original = runtime._write
mode = {mode!r}
def broken(root, work, fields, by, command):
    if command == "run":
        if mode == "partial":
            original(root, work, fields[:1], by, command)
        raise RecorderError("planted append failure")
    return original(root, work, fields, by, command)
if mode == "collision":
    runtime._new_id = lambda: "11111111"
else:
    runtime._write = broken
raise SystemExit(rec.main(sys.argv[1:]))
'''
    args = run_args(tmp_path, mode, [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch(); exit(9)"])[2:]
    result = subprocess.run([sys.executable, "-c", driver, *args], capture_output=True, text=True, timeout=10)
    assert result.returncode == 9 and marker.exists(), result.stderr
    assert "start not recorded" in result.stderr
    steps = folded(tmp_path)["works"][0]["steps"]
    if mode == "partial":
        assert len(steps) == 1 and steps[0]["reason"] == "start_not_recorded"
        assert steps[0]["state"] == "unknown"
    else:
        assert steps == []
    if mode == "collision":
        assert (collision / "stdout").read_text() == "preserve"


def test_run_heartbeat_and_quote(tmp_path):
    opened(tmp_path)
    driver = f"import sys; sys.path.insert(0,{str(REC.parent)!r}); import runtime,rec; runtime.HEARTBEAT_SECONDS=.05; raise SystemExit(rec.main(sys.argv[1:]))"
    args = run_args(tmp_path, "pulse", [sys.executable, "-c", "import time; print('last line',flush=True); time.sleep(.2)"])[2:]
    result = subprocess.run([sys.executable, "-c", driver, *args], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    from events import load_file
    log = load_file(tmp_path / "w1" / "events.jsonl")
    seen = [e for e in log.events if e["type"] == "step_seen"]
    assert seen and all(e["alive"] is True and e["output_bytes"] == 10 and e["text"] == "last line" for e in seen)
    assert folded(tmp_path)["works"][0]["steps"][0]["quote"] == "last line"
    declared = next(e for e in log.events if e["type"] == "step_declared")
    started = next(e for e in log.events if e["type"] == "step_started")
    assert started["seq"] == declared["seq"] + 1 and started["at"] == declared["at"]


def test_run_replaces_and_report_first_line(tmp_path):
    opened(tmp_path)
    old = json.loads(cli(tmp_path, "declare", "--work", "w1", "--name", "Queued", "--kind", "review", "--who", "Codex", "--watch", "process").stdout)
    report = tmp_path / "report"
    report.write_text("Verdict is a quote\nSecond line\n")
    result = cli(tmp_path, "run", "--work", "w1", "--name", "Review", "--kind", "review", "--who", "Codex", "--replaces", old["step_id"], "--quote-first-line", str(report), "--", sys.executable, "-c", "print('output')")
    assert result.returncode == 0
    work = folded(tmp_path)["works"][0]
    assert len(work["steps"]) == 1 and work["withdrawn"] == 1
    assert work["steps"][0]["quote"] == "Verdict is a quote"


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGKILL])
def test_run_signal_wait_status(tmp_path, sig):
    opened(tmp_path)
    result = subprocess.run(run_args(tmp_path, "signal-exit", [sys.executable, "-c", f"import os; os.kill(os.getpid(),{sig})"]), capture_output=True, timeout=10)
    assert result.returncode == -sig
    step = folded(tmp_path)["works"][0]["steps"][0]
    assert step["state"] == "failed" and step["signal"] == signal.Signals(sig).name


def test_run_keeps_an_inherited_ignore(tmp_path):
    """Review 130: under nohup the wrapper must not turn an ignored HUP back into a kill."""
    opened(tmp_path)
    marker = tmp_path / "survived"
    proc = subprocess.Popen(run_args(tmp_path, "nohup", ["sh", "-c", f"sleep 1; echo ok > {marker}"]),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            preexec_fn=lambda: signal.signal(signal.SIGHUP, signal.SIG_IGN))
    time.sleep(.5)
    proc.send_signal(signal.SIGHUP)
    assert proc.wait(timeout=10) == 0
    assert marker.read_text() == "ok\n"


def test_run_starts_the_child_when_bookkeeping_raises(tmp_path):
    """Review 130: a name that cannot be written, or a bad work id, must not keep the command from running."""
    opened(tmp_path)
    for index, extra in enumerate((["--work", "w1", "--name", "bad\udcff"], ["--work", "a/b", "--name", "n"])):
        marker = tmp_path / f"made-{index}"
        args = [sys.executable, str(REC), "--root", str(tmp_path), "run", *extra,
                "--kind", "other", "--who", "Codex", "--", "touch", str(marker)]
        result = subprocess.run(args, capture_output=True, timeout=12)
        assert result.returncode == 0, result.stderr
        assert marker.exists(), extra


def test_run_says_where_the_output_went(tmp_path):
    """Review 130: the child's output goes to files; the wrapper names them before it starts the child."""
    opened(tmp_path)
    result = subprocess.run(run_args(tmp_path, "where", ["sh", "-c", "echo hi"]),
                            capture_output=True, text=True, timeout=12)
    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stderr.splitlines() if line.startswith("run: step ")]
    assert len(lines) == 1, result.stderr
    assert (Path(lines[0].split(" output ", 1)[1]) / "stdout").read_text() == "hi\n"

