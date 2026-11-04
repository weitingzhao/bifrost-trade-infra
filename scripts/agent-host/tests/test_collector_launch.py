"""S1-5: the Claude launcher, the hooks it feeds and the work's single writer (R5:5.5-12 §2.2–§2.4, §9).

python3 -m pytest -q scripts/agent-host/tests/test_collector_launch.py
Real processes: dispatch-claude.py becomes a fake claude, which runs the real
hook (thread-heartbeat.js); the hook starts the real writer. Requests go to a
local fake platform only.
"""

import importlib.util
import json
import os
import subprocess
import sys
import uuid
from types import SimpleNamespace

import pytest

from collector_fakes import AGENT_HOST, AUDIT, Platform, clean_env, collector_env, fake_claude

LAUNCHER = AGENT_HOST / "dispatch-claude.py"
spec = importlib.util.spec_from_file_location("dispatch_claude", LAUNCHER)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
LINKED = ["--root", "R5", "--node", "R5:5.5-12", "--plan-version", "7", "--acceptance-ref", "S1-5", "--task", "launch test", "--repo", "bifrost-trade-infra", "--branch", "r5/test", "--estimate-minutes", "5", "10"]
S = "00000000-0000-4000-8000-0000000000a1"


@pytest.fixture
def world(tmp_path):
    platform = Platform()
    claude = fake_claude(tmp_path / "bin")
    yield SimpleNamespace(home=tmp_path / "home", platform=platform, bin=claude.parent, record=tmp_path / "claude.json")
    platform.close()


def launch(w, args, plan, **env):
    base = collector_env(w.home, w.platform.url, FAKE_CLAUDE_PLAN=json.dumps(plan), FAKE_CLAUDE_RECORD=w.record, **env)
    base["PATH"] = str(w.bin) + os.pathsep + base["PATH"]
    proc = subprocess.run([sys.executable, str(LAUNCHER), *args, "--", "-p", "PRIVATE_PROMPT"], env=base, capture_output=True, text=True, timeout=60)
    return proc


def launches(w):
    root = w.home / ".cache" / "bifrost" / "external-work" / "launches"
    return [json.loads((d / "launch.json").read_text()) for d in sorted(root.iterdir())] if root.is_dir() else []


def steps(*events, session=S):
    extras = {"SessionStart": {"source": "startup"}, "SessionEnd": {"reason": "other"}, "UserPromptSubmit": {"prompt": "x"}}
    return [{"event": e, "session": session, "extra": extras.get(e, {})} for e in events]


def test_launch_record_and_sessions_backfill_and_the_writer(world):
    proc = launch(world, LINKED, steps("SessionStart", "UserPromptSubmit", "SessionEnd"))
    assert proc.returncode == 0, proc.stderr
    [record] = launches(world)
    child = json.loads(world.record.read_text())
    assert record["cli_pid"] == child["pid"], "exec keeps the pid: the record's cli_pid is the CLI's"
    assert record["sessions"] and [(s["vendor"], s["session"], s["epoch"]) for s in record["sessions"]] == [("claude", S, 1)]
    assert child["env"]["BIFROST_LAUNCH_ID"] == record["launch_id"] and child["env"]["BIFROST_PLAN_NODE"] == "R5:5.5-12"
    assert "PRIVATE_PROMPT" not in json.dumps(record)
    p = world.platform
    assert p.wait(lambda p: [e["type"] for e in p.events()] == ["started", "heartbeat", "submitted"])
    [registration] = [c["body"] for c in p.calls if c["path"] == "/api/v1/agentrt/external-work"]
    assert {k: registration[k] for k in ("vendor", "session", "epoch", "source_run_key", "root", "plan_node_id")} == {
        "vendor": "claude", "session": S, "epoch": 1, "source_run_key": f"claude:{S}:1", "root": "R5", "plan_node_id": "R5:5.5-12"}
    assert all((e["vendor"], e["session"], e["epoch"]) == ("claude", S, 1) for e in p.events())
    assert all(c["auth"] == "Bearer COLLECTOR_TEST_TOKEN" for c in p.calls)
    # The first beat goes before the registration has arrived: no client_bind (§13 I6); later ones say linked.
    beats = p.beats()
    assert "client_bind" not in beats[0] and beats[-1]["client_bind"]["state"] == "linked"


def test_an_incomplete_description_refuses_to_launch(world):
    for missing in ("--branch", "--acceptance-ref", "--estimate-minutes"):
        at = LINKED.index(missing)
        args = LINKED[:at] + LINKED[at + (3 if missing == "--estimate-minutes" else 2):]
        proc = launch(world, args, steps("SessionStart"))
        assert proc.returncode == 2 and missing in proc.stderr
    assert launches(world) == [] and not world.record.exists(), "nothing is written and claude is not started"
    assert launch(world, ["--unlinked", "--root", "R5"], []).returncode == 2, "--unlinked takes no plan context"


def test_heartbeat_off_leaves_no_session_and_the_audit_reports_the_gap(world):
    proc = launch(world, LINKED, steps("SessionStart", "SessionEnd"), BIFROST_HEARTBEAT="off")
    assert proc.returncode == 0 and "collector mode is off" in proc.stderr
    [record] = launches(world)
    assert record["sessions"] == [] and world.platform.calls == []
    out = subprocess.run(["node", str(AUDIT)], env=clean_env(world.home, world.platform.url), capture_output=True, text=True, check=True)
    report = json.loads(out.stdout)
    assert report["launches"][0]["gaps"] == ["launch_without_sessions"] and report["launches_with_gaps"] == 1


def test_an_unlinked_launch_is_recorded_and_its_beats_say_unlinked(world):
    proc = launch(world, ["--unlinked"], steps("SessionStart", "UserPromptSubmit", "SessionEnd"))
    assert proc.returncode == 0, proc.stderr
    [record] = launches(world)
    assert record["mode"] == "unlinked" and len(record["sessions"]) == 1 and "root" not in record
    p = world.platform
    assert p.wait(lambda p: len(p.beats()) == 3)
    assert all((b["client_bind"]["state"], b["client_bind"]["reason"]) == ("unlinked", "no_context") for b in p.beats())
    assert not [c for c in p.calls if "/agentrt/" in c["path"]], "no external work for an unlinked launch"
    report = json.loads(subprocess.run(["node", str(AUDIT)], env=clean_env(world.home, world.platform.url), capture_output=True, text=True, check=True).stdout)
    assert report["launches"][0]["gaps"] == [] and report["launches"][0]["works"][0]["registration"] == "none"


def test_a_session_nested_in_the_launch_is_not_the_launch(world):
    nested = "00000000-0000-4000-8000-0000000000a2"
    plan = steps("SessionStart") + [{"event": "SessionStart", "session": nested, "pid": 4242, "extra": {"source": "startup"}}]
    assert launch(world, LINKED, plan).returncode == 0
    [record] = launches(world)
    assert [s["session"] for s in record["sessions"]] == [S], "only the launch's own process is recorded"
    p = world.platform
    assert p.wait(lambda p: len(p.beats()) == 2 and p.events())
    [nested_beat] = [b for b in p.beats() if b["session"] == nested]
    assert (nested_beat["client_bind"]["state"], nested_beat["client_bind"]["reason"]) == ("unlinked", "no_context")
    assert {c["body"]["session"] for c in p.calls if c["path"] == "/api/v1/agentrt/external-work"} == {S}


def test_sidebar_inherited_from_a_running_session_is_not_the_launch_s(tmp_path, monkeypatch):
    """§12 D6 / §13 I4: CLAUDE_CODE_SESSION_ID set means a parent CLI; its sidebar is the parent's."""
    lid = str(uuid.uuid4())
    assert launcher.sidebar_for({"CLAUDE_CODE_HOST_SESSION_ID": "local_parent", "CLAUDE_CODE_SESSION_ID": "s-parent"}, lid) == ("launch-" + lid, "launch", "s-parent")
    assert launcher.sidebar_for({"CLAUDE_CODE_HOST_SESSION_ID": "local_desk"}, lid) == ("local_desk", "desktop", "")
    assert launcher.sidebar_for({}, lid) == ("launch-" + lid, "launch", "")
    monkeypatch.setenv("BIFROST_HOME_OVERRIDE", str(tmp_path))
    options = launcher.parser().parse_args(LINKED)
    _, env = launcher.prepare(options, {"CLAUDE_CODE_HOST_SESSION_ID": "local_parent", "CLAUDE_CODE_SESSION_ID": "s-parent", "BIFROST_PLAN_NODE": "stale"}, 4321)
    assert env["CLAUDE_CODE_HOST_SESSION_ID"].startswith("launch-") and env["BIFROST_PLAN_NODE"] == "R5:5.5-12"
    record = json.loads((tmp_path / ".cache/bifrost/external-work/launches" / env["BIFROST_LAUNCH_ID"] / "launch.json").read_text())
    assert (record["parent_session"], record["sidebar_source"], record["cli_pid"]) == ("s-parent", "launch", 4321)
    assert oct((tmp_path / ".cache/bifrost/external-work/launches" / env["BIFROST_LAUNCH_ID"] / "launch.json").stat().st_mode & 0o777) == "0o600"


def test_a_refused_registration_is_kept_and_the_beats_say_refused(world):
    world.platform.refuse_registration = 1
    assert launch(world, LINKED, steps("SessionStart", "UserPromptSubmit", "UserPromptSubmit")).returncode == 0
    p = world.platform
    assert p.wait(lambda p: len(p.beats()) == 3)
    assert p.wait(lambda p: p.beats()[-1].get("client_bind", {}).get("reason") == "register_failed")
    registrations = [c for c in p.calls if c["path"] == "/api/v1/agentrt/external-work"]
    assert len(registrations) == 1, "a refused registration is not retried by the hooks"
    report = json.loads(subprocess.run(["node", str(AUDIT)], env=clean_env(world.home, p.url), capture_output=True, text=True, check=True).stdout)
    assert report["launches"][0]["works"][0]["registration"] == "refused" and "work_not_registered" in report["launches"][0]["gaps"]


def test_a_resume_cancels_the_epoch_it_superseded(world):
    plan = steps("SessionStart") + [{"event": "SessionStart", "session": S, "pid": 5151, "extra": {"source": "resume"}, "sleep": 0.8}]
    assert launch(world, LINKED, plan).returncode == 0
    p = world.platform
    assert p.wait(lambda p: any(e["type"] == "cancelled" for e in p.events()))
    cancelled = [e for e in p.events() if e["type"] == "cancelled"]
    assert [e["epoch"] for e in cancelled] == [1], "only the launch's epoch 1 had a work; the resume's other process is not the launch's"
