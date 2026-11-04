"""S1-5: the Codex wrapper in collector mode, its reconcile, and bind (R5:5.5-12 §2.4, §2.5).

python3 -m pytest -q scripts/agent-host/tests/test_collector_codex.py
A fake codex executable and a local fake platform; no real CLI, no platform.
"""

import json
import os
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from collector_fakes import AGENT_HOST, COLLECTOR, Platform, clean_env, collector_env

WRAPPER = AGENT_HOST / "dispatch-codex.py"
REGISTER = AGENT_HOST / "register-claude-work.py"
DESCRIPTION = {"v": 1, "kind": "agentrt.external_work/v1", "task": "实现摘要", "executor": "codex", "provider": "openai",
               "repo": "platform", "branch": "test", "acceptance_refs": ["PV1"], "estimate_minutes": [1, 2]}


@pytest.fixture
def world(tmp_path):
    platform = Platform()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "codex").write_text(
        "#!" + sys.executable + "\nimport json, os, time\n"
        "open(os.environ['FAKE_CODEX_LOG'], 'a').write(json.dumps({'pid': os.getpid(), 'collector': 'PLATFORM_COLLECTOR_TOKEN' in os.environ, 'dispatch': 'BIFROST_DISPATCH_TOKEN' in os.environ}) + '\\n')\n"
        "time.sleep(float(os.environ.get('FAKE_DURATION', '0.2')))\n"
    )
    (bin_dir / "codex").chmod(0o755)
    (tmp_path / "description.json").write_text(json.dumps(DESCRIPTION, ensure_ascii=False))
    w = SimpleNamespace(tmp=tmp_path, home=tmp_path / "home", platform=platform, bin=bin_dir, log=tmp_path / "codex.log")
    yield w
    platform.close()
    for line in w.log.read_text().splitlines() if w.log.exists() else []:
        try:
            os.kill(json.loads(line)["pid"], signal.SIGKILL)
        except ProcessLookupError:
            pass


def wrapper_args(w, run_key="run-s15"):
    return ["--url", w.platform.url, "--session", "local_coordinator", "--run-key", run_key, "--root", "R4", "--node", "R4:4.5-1",
            "--description", str(w.tmp / "description.json"), "--report", str(w.tmp / "REPORT.md"), "--state-dir", str(w.tmp / "state"), "--repo", str(w.tmp)]


def env_of(w, collector=True, **extra):
    base = (collector_env if collector else clean_env)(w.home, w.platform.url, FAKE_CODEX_LOG=w.log, **extra)
    base["PATH"] = str(w.bin) + os.pathsep + base["PATH"]
    return base


def test_the_wrapper_registers_with_the_collector_token_as_codex_run_key_epoch_1(world):
    proc = subprocess.run([sys.executable, str(WRAPPER), *wrapper_args(world), "--", "PRIVATE"], env=env_of(world, BIFROST_DISPATCH_TOKEN="DISPATCH"), capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    p = world.platform
    [registration] = [c["body"] for c in p.calls if c["path"] == "/api/v1/agentrt/external-work"]
    assert {k: registration[k] for k in ("vendor", "session", "epoch", "source_run_key")} == {"vendor": "codex", "session": "run-s15", "epoch": 1, "source_run_key": "codex:run-s15:1"}
    assert [e["type"] for e in p.events()] == ["started", "submitted"]
    assert all((e["vendor"], e["session"], e["epoch"]) == ("codex", "run-s15", 1) for e in p.events())
    assert {c["auth"] for c in p.calls} == {"Bearer " + COLLECTOR}, "the collector token, not the dispatch token"
    [child] = [json.loads(line) for line in world.log.read_text().splitlines()]
    assert child == {"pid": child["pid"], "collector": False, "dispatch": False}, "the child gets neither token"
    state = json.loads(next((world.tmp / "state").glob("*/state.json")).read_text())
    assert state["registered_at"] == "2026-11-04T00:00:00.000Z"
    bad = subprocess.run([sys.executable, str(WRAPPER), *wrapper_args(world, "bad key!"), "--", "x"], env=env_of(world), capture_output=True, text=True, timeout=60)
    assert bad.returncode == 1 and "run key is the session" in bad.stderr


def start_and_lose_the_child(w, collector):
    env = env_of(w, collector, FAKE_DURATION="30", BIFROST_DISPATCH_TOKEN="DISPATCH")
    proc = subprocess.Popen([sys.executable, str(WRAPPER), *wrapper_args(w), "--", "x"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end = time.monotonic() + 20
    found = []
    while time.monotonic() < end and not found:
        found = list((w.tmp / "state").glob("*/child.json")) if (w.tmp / "state").exists() else []
        time.sleep(0.05)
    assert found, "the supervisor never started"
    run_dir = found[0].parent
    assert w.platform.wait(lambda p: any(e["type"] == "started" for e in p.events()))
    supervisor = json.loads(found[0].read_text())["pid"]
    proc.kill()
    proc.wait(timeout=5)
    os.kill(supervisor, signal.SIGKILL)
    time.sleep(0.3)
    assert not (run_dir / "exit.json").exists()
    return env


@pytest.mark.parametrize("collector", [True, False])
def test_reconcile_ends_a_run_whose_child_vanished_once_and_then_does_nothing(world, collector):
    env = start_and_lose_the_child(world, collector)
    reconcile = [sys.executable, str(WRAPPER), "reconcile", "--url", world.platform.url, "--session", "local_coordinator", "--run-key", "run-s15", "--state-dir", str(world.tmp / "state")]
    first = subprocess.run(reconcile, env=env, capture_output=True, text=True, timeout=30)
    assert first.returncode == 0, first.stderr
    assert [e["type"] for e in world.platform.events()][-1] == "cancelled"
    if collector:
        assert (world.platform.events()[-1]["vendor"], world.platform.events()[-1]["session"]) == ("codex", "run-s15")
    before = len(world.platform.calls)
    second = subprocess.run(reconcile, env=env, capture_output=True, text=True, timeout=30)
    assert second.returncode == 0 and "nothing sent" in second.stderr
    assert len(world.platform.calls) == before, "a second reconcile sends nothing"


def test_reconcile_refuses_a_run_whose_child_is_alive(world):
    env = env_of(world, FAKE_DURATION="30")
    proc = subprocess.Popen([sys.executable, str(WRAPPER), *wrapper_args(world), "--", "x"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert world.platform.wait(lambda p: any(e["type"] == "started" for e in p.events()))
        reconcile = [sys.executable, str(WRAPPER), "reconcile", "--url", world.platform.url, "--session", "local_coordinator", "--run-key", "run-s15", "--state-dir", str(world.tmp / "state")]
        busy = subprocess.run(reconcile, env=env, capture_output=True, text=True, timeout=30)
        assert busy.returncode == 1 and "wrapper owns this run" in busy.stderr
        proc.kill()
        proc.wait(timeout=5)
        alive = subprocess.run(reconcile, env=env, capture_output=True, text=True, timeout=30)
        assert alive.returncode == 1 and "still holds its lock" in alive.stderr, "the supervisor still runs the child"
        assert "cancelled" not in [e["type"] for e in world.platform.events()]
    finally:
        if proc.poll() is None:
            proc.kill()


def bind(w, *extra, node="R5:5.5-12"):
    args = [sys.executable, str(REGISTER), "bind", "--session", "00000000-0000-4000-8000-0000000000b1", "--epoch", "1", "--url", w.platform.url,
            "--root", "R5", "--node", node, "--description", str(w.tmp / "claude.json"), *extra]
    return subprocess.run(args, env=env_of(w), capture_output=True, text=True, timeout=30)


def test_bind_registers_once_and_repeating_it_writes_nothing(world):
    (world.tmp / "claude.json").write_text(json.dumps({**DESCRIPTION, "executor": "claude", "provider": "anthropic"}))
    first = bind(world)
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["state"] == "Running"
    p = world.platform
    def posts():
        return [c for c in p.calls if c["method"] in ("POST", "PUT")]

    assert [c["path"].rsplit("/", 1)[-1] for c in posts()][-2:] == ["external-work", "events"]
    count = len(posts())
    again = bind(world)
    assert again.returncode == 0 and len(posts()) == count, "a second bind registers nothing and sends no event"
    other = bind(world, node="R5:5.5-13")
    assert other.returncode == 1 and "already bound to other content" in other.stderr
    no_token = subprocess.run([sys.executable, str(REGISTER), "bind", "--session", "s2", "--epoch", "1", "--url", p.url, "--root", "R5", "--node", "x", "--description", str(world.tmp / "claude.json")],
                              env=clean_env(world.home, p.url), capture_output=True, text=True, timeout=30)
    assert no_token.returncode == 1 and "collector mode is off" in no_token.stderr


def test_writer_calls_that_arrive_out_of_order_converge(world):
    (world.tmp / "claude.json").write_text(json.dumps({**DESCRIPTION, "executor": "claude", "provider": "anthropic"}))
    assert bind(world).returncode == 0
    session = "00000000-0000-4000-8000-0000000000b1"
    def event(kind):
        return subprocess.run([sys.executable, str(REGISTER), "event", "--event", kind, "--session", session, "--epoch", "1", "--url", world.platform.url],
                              env=env_of(world), capture_output=True, text=True, timeout=30)

    assert event("submit").returncode == 0
    assert event("heartbeat").returncode == 0, "a heartbeat after the end is no error, and sends nothing"
    assert [e["type"] for e in world.platform.events()] == ["started", "submitted"]
    unknown = subprocess.run([sys.executable, str(REGISTER), "event", "--event", "start", "--session", "s-unknown", "--epoch", "1", "--url", world.platform.url],
                             env=env_of(world), capture_output=True, text=True, timeout=30)
    assert unknown.returncode == 0 and unknown.stdout == "", "a session with no launch and no bind has nothing to write"
