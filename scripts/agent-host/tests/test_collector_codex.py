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
        "if os.environ.get('FAKE_CLOSE_FDS'): os.closerange(3, 1024)\n"
        "if os.environ.get('FAKE_DUMP_ENV'): open(os.path.join(os.path.dirname(os.environ['FAKE_CODEX_LOG']), 'codex-env.json'), 'w').write(json.dumps(dict(os.environ)))\n"
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


def start_and_lose_the_supervisor(w, collector, session="local_coordinator", **extra):
    """Kill the wrapper and the supervisor; the fake Codex itself goes on running."""
    env = env_of(w, collector, FAKE_DURATION="30", BIFROST_DISPATCH_TOKEN="DISPATCH", **extra)
    proc = subprocess.Popen([sys.executable, str(WRAPPER), *wrapper_args(w), "--", "x"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end = time.monotonic() + 20
    while time.monotonic() < end and not (w.log.exists() and list((w.tmp / "state").glob("*/codex.json"))):
        time.sleep(0.05)
    [codex_file] = list((w.tmp / "state").glob("*/codex.json"))
    assert w.platform.wait(lambda p: any(e["type"] == "started" for e in p.events()))
    assert w.platform.wait(lambda p: isinstance(json.loads(codex_file.read_text()).get("pid"), int), 5)
    supervisor = json.loads((codex_file.parent / "child.json").read_text())["pid"]
    proc.kill()
    proc.wait(timeout=5)
    os.kill(supervisor, signal.SIGKILL)
    time.sleep(0.3)
    assert not (codex_file.parent / "exit.json").exists()
    return env, json.loads(codex_file.read_text())["pid"], codex_file.parent


def reconcile_cmd(w):
    return [sys.executable, str(WRAPPER), "reconcile", "--url", w.platform.url, "--session", "local_coordinator", "--run-key", "run-s15", "--state-dir", str(w.tmp / "state")]


@pytest.mark.parametrize("collector", [True, False])
def test_reconcile_ends_a_run_only_once_its_codex_is_gone_and_then_does_nothing(world, collector):
    env, codex, _ = start_and_lose_the_supervisor(world, collector)
    alive = subprocess.run(reconcile_cmd(world), env=env, capture_output=True, text=True, timeout=30)
    assert alive.returncode == 1 and ("still holds its lock" in alive.stderr or "still running" in alive.stderr), alive.stderr
    assert "cancelled" not in [e["type"] for e in world.platform.events()], "review M1: a live Codex is never cancelled"
    os.kill(codex, signal.SIGKILL)
    time.sleep(0.3)
    first = subprocess.run(reconcile_cmd(world), env=env, capture_output=True, text=True, timeout=30)
    assert first.returncode == 0, first.stderr
    assert [e["type"] for e in world.platform.events()][-1] == "cancelled"
    if collector:
        assert (world.platform.events()[-1]["vendor"], world.platform.events()[-1]["session"]) == ("codex", "run-s15")
    before = len(world.platform.calls)
    second = subprocess.run(reconcile_cmd(world), env=env, capture_output=True, text=True, timeout=30)
    assert second.returncode == 0 and "nothing sent" in second.stderr
    assert len(world.platform.calls) == before, "a second reconcile sends nothing"


def test_reconcile_refuses_a_live_codex_that_let_go_of_the_child_lock(world):
    """Review M1: the lock is not the only witness; the recorded pid and start time are."""
    env, codex, _ = start_and_lose_the_supervisor(world, True, FAKE_CLOSE_FDS="1")
    refused = subprocess.run(reconcile_cmd(world), env=env, capture_output=True, text=True, timeout=30)
    assert refused.returncode == 1 and "Codex is still running" in refused.stderr, refused.stderr
    assert "cancelled" not in [e["type"] for e in world.platform.events()]


@pytest.mark.parametrize("record", [{"pid": 1}, "codex-pid-null"], ids=["older-wrapper", "supervisor-died-starting-codex"])
def test_reconcile_keeps_a_run_unconfirmed_when_the_codex_process_cannot_be_told(world, record):
    env, codex, run_dir = start_and_lose_the_supervisor(world, True)
    os.kill(codex, signal.SIGKILL)
    if record == "codex-pid-null":
        (run_dir / "codex.json").write_text(json.dumps({"pid": None}))
    else:
        (run_dir / "child.json").write_text(json.dumps(record))
        (run_dir / "codex.json").unlink()
    refused = subprocess.run(reconcile_cmd(world), env=env, capture_output=True, text=True, timeout=30)
    assert refused.returncode == 1 and "stays Unconfirmed" in refused.stderr
    assert "cancelled" not in [e["type"] for e in world.platform.events()]


def test_two_callers_with_other_sessions_cannot_both_launch_one_collector_work(world):
    """Review M4: the collector's work is (codex, run key, 1) whatever --session says; so is its lock."""
    env = env_of(world, FAKE_DURATION="3")
    first = subprocess.Popen([sys.executable, str(WRAPPER), *wrapper_args(world), "--", "x"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert world.platform.wait(lambda p: any(e["type"] == "started" for e in p.events()))
        args = wrapper_args(world)
        args[args.index("--session") + 1] = "local_other"
        second = subprocess.run([sys.executable, str(WRAPPER), *args, "--", "x"], env=env, capture_output=True, text=True, timeout=30)
        assert second.returncode == 1 and "another wrapper owns this run" in second.stderr
        assert first.wait(timeout=30) == 0
    finally:
        if first.poll() is None:
            first.kill()
    assert len(world.log.read_text().splitlines()) == 1, "one Codex for one work"
    third = subprocess.run([sys.executable, str(WRAPPER), *args, "--", "x"], env=env, capture_output=True, text=True, timeout=30)
    assert third.returncode == 0 and len(world.log.read_text().splitlines()) == 1, "after it ended, the other session finds it ended"


@pytest.mark.parametrize("collector", [True, False])
def test_codex_gets_no_credential_in_its_environment(world, collector):
    """Review M5: every credential-shaped and platform variable is removed; the executor's own stay."""
    secrets = {"PLATFORM_REPORTER_TOKEN": "R", "AGENTRT_COORDINATOR_AGENTD_TOKEN": "A", "AGENTRT_COORDINATOR_PROPOSER_TOKEN": "P",
               "HANDIN_AGENTD_TOKEN_FILE": "/x", "GITHUB_TOKEN": "G", "SOME_SECRET": "S", "DB_PASSWORD": "D", "BIFROST_DISPATCH_TOKEN": "DISPATCH",
               "PLATFORM_AGENTRT_URL": "http://x.invalid"}
    env = env_of(world, collector, FAKE_DUMP_ENV="1", OPENAI_BASE_URL="http://keep.invalid", LANG="C", **secrets)
    proc = subprocess.run([sys.executable, str(WRAPPER), *wrapper_args(world), "--", "x"], env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    dumped = json.loads((world.tmp / "codex-env.json").read_text())
    assert not [k for k in dumped if k in secrets or "TOKEN" in k or k == "PLATFORM_COLLECTOR_TOKEN"], sorted(dumped)
    assert dumped["OPENAI_BASE_URL"] == "http://keep.invalid" and dumped["LANG"] == "C" and dumped["PATH"] == env["PATH"]


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
