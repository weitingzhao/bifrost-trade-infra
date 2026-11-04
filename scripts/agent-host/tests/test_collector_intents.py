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
from pathlib import Path
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



def run_node(home, code, env):
    base = {"PATH": os.environ["PATH"], "HOME": str(home), "BIFROST_HOME_OVERRIDE": str(home), **env}
    p = subprocess.run(["node", "-e", code], env=base, capture_output=True, text=True, timeout=20)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def test_r2m2_a_resume_between_the_epoch_and_its_work_directory_still_keeps_the_cancel(w, tmp_path):
    """The review's window: the launch hook saved epoch 1 and paused; a plain resume superseded it; then the
    launch hook went on and started its writer. The resume keeps the cancel unconditionally."""
    js = AGENT_HOST.parents[1] / "agent-config" / "scripts"
    launch_env = {"BIFROST_LAUNCH_ID": w.launch_id, "BIFROST_PLAN_ROOT": "R5", "BIFROST_PLAN_NODE": "R5:5.5-12", "BIFROST_WORK_DESCRIPTION": w.desc, "CLAUDE_PID": str(os.getpid())}
    code = r"""
const fs = require('node:fs'), cp = require('node:child_process')
const spawned = []; cp.spawn = (bin, args) => { spawned.push(args); return { on() {}, unref() {} } }
const ep = require(EPOCHS), launch = require(LAUNCH)
const deps = { withLock: (f, fn) => fn(), startTime: p => 'start-' + p, now: () => new Date('2026-11-04T00:00:00Z') }
const payload = { hook_event_name: 'SessionStart' }
const first = { identity: { session: 'race' }, reason: 'startup', thread: 'race' }
const r1 = ep.resolve('claude', payload, first, deps, process.env)
const plain = { CLAUDE_PID: '7171' }
const resume = { identity: { session: 'race' }, reason: 'resume', thread: 'race' }
const r2 = ep.resolve('claude', payload, resume, deps, plain)
launch.afterResolve('claude', payload, resume, r2, deps, plain, 'http://offline.invalid')
launch.afterResolve('claude', payload, first, r1, deps, process.env, 'http://offline.invalid')
const dir = ep.sessionDir('claude', 'race')
console.log(JSON.stringify({ superseded: r2.superseded, spawned, kept: JSON.parse(fs.readFileSync(dir + '/1/terminal.json', 'utf8')).event }))
""".replace("EPOCHS", json.dumps(str(js / "collector-epochs.js"))).replace("LAUNCH", json.dumps(str(js / "collector-launch.js")))
    out = run_node(tmp_path / "home", code, launch_env)
    assert out["superseded"] == [1] and out["kept"] == "cancel"
    assert w.work.run_event("start", "claude", "race", 1, "http://offline.invalid", w.launch_id) is None, "the late start writer registers nothing"
    assert w.platform.works == {}


def test_r2m2_a_cancel_kept_while_registering_is_never_preceded_by_started(w, monkeypatch):
    client = w.work.dispatch.Client
    note = w.work.note_terminal

    class Racing(client):
        def request(self, method, path, body=None, *, raw=False):
            out = super().request(method, path, body, raw=raw)
            if path == "/external-work":
                note(w.work.auth.epoch_dir("claude", "race2", 1), "cancel")
            return out

    monkeypatch.setattr(w.work.dispatch, "Client", Racing)
    assert w.work.run_event("start", "claude", "race2", 1, "http://offline.invalid", w.launch_id)["state"] == "Cancelled"
    assert types(w) == ["cancelled"]


def test_r2s1_the_audit_owes_a_cancel_whose_registration_reply_was_lost(w, monkeypatch):
    """Every registration reply is lost, the first and the cancel's three tries: the platform has the work."""
    client = w.work.dispatch.Client

    class Losing(client):
        def request(self, method, path, body=None, *, raw=False):
            out = super().request(method, path, body, raw=raw)
            if path == "/external-work":
                raise RuntimeError("platform unavailable")
            return out

    monkeypatch.setattr(w.work.dispatch, "Client", Losing)
    with pytest.raises(RuntimeError):
        w.work.run_event("start", "claude", "old", 1, "http://offline.invalid", w.launch_id)
    with pytest.raises(RuntimeError):
        w.work.run_event("cancel", "claude", "old", 1)
    record = w.work.auth.launch_dir(w.launch_id) / "launch.json"
    rec = json.loads(record.read_text())
    rec["sessions"] = [{"vendor": "claude", "session": "old", "epoch": 1}]
    record.write_text(json.dumps(rec))
    home = Path(os.environ["BIFROST_HOME_OVERRIDE"])
    out = run_node(home, "console.log(JSON.stringify(require(" + json.dumps(str(AUDIT)) + ").audit()))", {})
    item = out["launches"][0]
    assert item["works"][0]["registration"] == "unconfirmed" and item["works"][0]["end_not_delivered"] is True
    assert {"work_not_registered", "work_end_not_delivered"} <= set(item["gaps"])
    assert next(iter(w.platform.works.values()))["state"] == "Registered", "the platform does have it"
