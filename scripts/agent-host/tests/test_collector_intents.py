"""S1-5 review round 1: an end or a cancel is never lost, and a cancelled epoch never comes back (M2, M3).

python3 -m pytest -q scripts/agent-host/tests/test_collector_intents.py
The writer runs in-process against the fake platform's answers (no socket);
the last test runs the real hooks and writer processes.
"""

import fcntl
import importlib.util
import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from collector_fakes import AGENT_HOST, AUDIT, Platform, clean_env, collector_env, fake_claude


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, AGENT_HOST / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def w(tmp_path, monkeypatch):
    work = load("collector_work_t", "collector_work.py")
    launcher = load("dispatch_claude_t", "dispatch-claude.py")
    platform = Platform.memory()
    faults = {}
    monkeypatch.setattr(work.dispatch, "Client", platform.client(faults))
    monkeypatch.setattr(work, "RETRY_SECONDS", (0.01, 0.01), raising=False)
    monkeypatch.setenv("BIFROST_HOME_OVERRIDE", str(tmp_path / "home"))
    monkeypatch.setenv("PLATFORM_COLLECTOR_TOKEN", "COLLECTOR")
    args = ["--root", "R5", "--node", "R5:5.5-12", "--plan-version", "7", "--task", "t", "--repo", "infra", "--branch", "b",
            "--acceptance-ref", "S1-5", "--estimate-minutes", "1", "2"]
    launch_id, env = launcher.prepare(launcher.parser().parse_args(args), {}, os.getpid())
    return SimpleNamespace(work=work, platform=platform, faults=faults, launch_id=launch_id, desc=env["BIFROST_WORK_DESCRIPTION"])


def bind(w, session="s1"):
    return w.work.bind("claude", session, 1, "R5", "R5:5.5-12", w.desc, "http://offline.invalid")


def types(w):
    return [e["type"] for e in w.platform.events()]


def test_m2_a_submit_whose_read_fails_is_kept_and_the_next_call_delivers_it(w):
    bind(w)
    w.faults["get"] = 3
    with pytest.raises(RuntimeError):
        w.work.run_event("submit", "claude", "s1", 1)
    assert json.loads((w.work.auth.epoch_dir("claude", "s1", 1) / "terminal.json").read_text())["event"] == "submit"
    assert bind(w)["state"] == "Submitted", "bind delivers the kept end"
    assert types(w) == ["started", "submitted"]


def test_m2_a_submit_that_cannot_take_the_lock_is_kept_and_bind_delivers_it(w):
    bind(w)
    directory = w.work.auth.epoch_dir("claude", "s1", 1)
    with (directory / "wrapper.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        with pytest.raises(RuntimeError, match="another writer"):
            w.work.run_event("submit", "claude", "s1", 1, wait=0.03)
    assert bind(w)["state"] == "Submitted"
    assert types(w) == ["started", "submitted"]


def test_m2_a_retry_inside_the_writer_delivers_after_a_passing_failure(w):
    bind(w)
    w.faults["get"] = 1
    assert w.work.run_event("submit", "claude", "s1", 1)["state"] == "Submitted"


def test_m3_a_cancel_before_the_delayed_start_keeps_the_epoch_from_ever_running(w):
    assert w.work.run_event("cancel", "claude", "old", 1) is None
    assert w.work.run_event("start", "claude", "old", 1, "http://offline.invalid", w.launch_id) is None
    assert w.work.run_event("heartbeat", "claude", "old", 1, "http://offline.invalid", w.launch_id) is None
    assert w.platform.works == {} and types(w) == [], "nothing registered, nothing Running"
    assert not (w.work.auth.epoch_dir("claude", "old", 1) / "state.json").exists(), "no work is even begun for it"


def test_m3_a_registration_whose_reply_was_lost_is_cancelled_not_forgotten(w):
    w.faults["lose"] = "register"
    with pytest.raises(RuntimeError):
        w.work.run_event("start", "claude", "old", 1, "http://offline.invalid", w.launch_id)
    assert len(w.platform.works) == 1, "the platform has the work although the client never heard"
    assert w.work.run_event("cancel", "claude", "old", 1)["state"] == "Cancelled"
    assert types(w) == ["cancelled"]
    w.work.run_event("heartbeat", "claude", "old", 1, "http://offline.invalid", w.launch_id)
    assert types(w) == ["cancelled"], "a late heartbeat does not revive it"


def test_m3_a_cancelled_epoch_is_not_started_by_a_late_start(w):
    w.work.run_event("start", "claude", "s2", 1, "http://offline.invalid", w.launch_id)
    w.work.run_event("cancel", "claude", "s2", 1)
    w.work.run_event("start", "claude", "s2", 1, "http://offline.invalid", w.launch_id)
    w.work.run_event("submit", "claude", "s2", 1, "http://offline.invalid", w.launch_id)
    assert types(w) == ["started", "cancelled"], "the first kept end stands: cancel, not submit"


def test_m3_hooks_keep_the_cancel_of_a_superseded_launch_epoch_before_any_writer_runs(tmp_path):
    """The resume's hook keeps the old epoch's cancel itself, so the old start writer, whenever it runs, registers nothing Running."""
    platform = Platform()
    try:
        claude = fake_claude(tmp_path / "bin")
        s = "00000000-0000-4000-8000-0000000000c1"
        plan = [{"event": "SessionStart", "session": s, "extra": {"source": "startup"}, "sleep": 0},
                {"event": "SessionStart", "session": s, "pid": 7171, "extra": {"source": "resume"}, "sleep": 0.8, "plain": True}]
        env = collector_env(tmp_path / "home", platform.url, FAKE_CLAUDE_PLAN=json.dumps(plan), FAKE_CLAUDE_RECORD=tmp_path / "rec.json")
        env["PATH"] = str(claude.parent) + os.pathsep + env["PATH"]
        args = ["--root", "R5", "--node", "R5:5.5-12", "--plan-version", "7", "--acceptance-ref", "S1-5", "--task", "t", "--repo", "r", "--branch", "b", "--estimate-minutes", "1", "2"]
        assert subprocess.run([sys.executable, str(AGENT_HOST / "dispatch-claude.py"), *args, "--", "-p", "x"], env=env, capture_output=True, timeout=60).returncode == 0
        kept = tmp_path / "home/.cache/bifrost/external-work/claude" / s / "1" / "terminal.json"
        assert json.loads(kept.read_text())["event"] == "cancel"
        time.sleep(3)  # every detached writer has had its turn, in whatever order
        assert [w["state"] for w in platform.works.values()] in ([], ["Cancelled"]), "epoch 1 is never left Running"
        report = json.loads(subprocess.run(["node", str(AUDIT)], env=clean_env(tmp_path / "home", platform.url), capture_output=True, text=True, check=True).stdout)
        assert not {"work_end_not_delivered", "work_not_registered"} & set(report["launches"][0]["gaps"]), report
    finally:
        platform.close()


def test_m2_the_audit_reports_an_end_that_was_kept_but_not_delivered(tmp_path):
    platform = Platform()
    try:
        claude = fake_claude(tmp_path / "bin")
        s = "00000000-0000-4000-8000-0000000000c2"
        plan = [{"event": "SessionStart", "session": s, "extra": {"source": "startup"}, "sleep": 1.0}]
        env = collector_env(tmp_path / "home", platform.url, FAKE_CLAUDE_PLAN=json.dumps(plan), FAKE_CLAUDE_RECORD=tmp_path / "rec.json")
        env["PATH"] = str(claude.parent) + os.pathsep + env["PATH"]
        args = ["--root", "R5", "--node", "R5:5.5-12", "--plan-version", "7", "--acceptance-ref", "S1-5", "--task", "t", "--repo", "r", "--branch", "b", "--estimate-minutes", "1", "2"]
        subprocess.run([sys.executable, str(AGENT_HOST / "dispatch-claude.py"), *args, "--", "-p", "x"], env=env, capture_output=True, timeout=60)
        assert platform.wait(lambda p: any(e["type"] == "started" for e in p.events()))
        directory = tmp_path / "home/.cache/bifrost/external-work/claude" / s / "1"
        (directory / "terminal.json").write_text(json.dumps({"event": "submit", "at": "2026-11-04T00:00:00Z"}))
        report = json.loads(subprocess.run(["node", str(AUDIT)], env=clean_env(tmp_path / "home", platform.url), capture_output=True, text=True, check=True).stdout)
        assert "work_end_not_delivered" in report["launches"][0]["gaps"]
    finally:
        platform.close()


def test_m2_the_hooks_keep_the_end_themselves_when_no_writer_can_run(tmp_path):
    """Without python3 the writer never starts; the hook has kept the end before trying."""
    platform = Platform()
    try:
        claude = fake_claude(tmp_path / "bin")
        node = subprocess.run(["which", "node"], capture_output=True, text=True, check=True).stdout.strip()
        os.symlink(node, claude.parent / "node")
        s = "00000000-0000-4000-8000-0000000000c3"
        plan = [{"event": "SessionStart", "session": s, "extra": {"source": "startup"}}, {"event": "SessionEnd", "session": s, "extra": {"reason": "other"}}]
        env = collector_env(tmp_path / "home", platform.url, FAKE_CLAUDE_PLAN=json.dumps(plan), FAKE_CLAUDE_RECORD=tmp_path / "rec.json")
        env["PATH"] = str(claude.parent)  # node and claude only: no python3 to start a writer
        args = ["--root", "R5", "--node", "R5:5.5-12", "--plan-version", "7", "--acceptance-ref", "S1-5", "--task", "t", "--repo", "r", "--branch", "b", "--estimate-minutes", "1", "2"]
        assert subprocess.run([sys.executable, str(AGENT_HOST / "dispatch-claude.py"), *args, "--", "-p", "x"], env=env, capture_output=True, timeout=60).returncode == 0
        kept = tmp_path / "home/.cache/bifrost/external-work/claude" / s / "1" / "terminal.json"
        assert json.loads(kept.read_text())["event"] == "submit"
        assert not [c for c in platform.calls if "/agentrt/" in c["path"]], "no writer ran"
    finally:
        platform.close()
