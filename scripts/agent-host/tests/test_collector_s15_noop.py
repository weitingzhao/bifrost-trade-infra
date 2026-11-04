"""S1-5 no-op equivalence: without a collector token the wrapper, register-claude-work.py and
handin.sh behave as the scripts of 46d1a32 do (R5:5.5-12 S1-5).

python3 -m pytest -q scripts/agent-host/tests/test_collector_s15_noop.py
Compared: exit code, stdout, stderr, every request (method, path, Authorization,
X-Bifrost-Session, Content-Type, X-Artifact-Kind, body bytes), what the child
was given (the Codex wrapper), and the files handin.sh leaves under .git/handin.
Not compared: timing. Requests go to a local fake platform or a fake curl. The
baseline scripts come from git; without the commit the test fails.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from collector_fakes import AGENT_HOST, INFRA, Platform, clean_env

BASELINE = "46d1a32"
HANDIN = INFRA / "agent-config" / "scripts" / "landing" / "handin.sh"
DESCRIPTION = {"v": 1, "kind": "agentrt.external_work/v1", "task": "任务", "executor": "codex", "provider": "openai",
               "repo": "platform", "branch": "b", "acceptance_refs": ["PV1"], "estimate_minutes": [1, 2]}
# Without a collector token, a blank one, and an unreadable token file.
NO_TOKEN = [{}, {"PLATFORM_COLLECTOR_TOKEN": "   "}, {"unreadable": True}]


def baseline(tmp_path, *names):
    out = tmp_path / "baseline"
    out.mkdir(exist_ok=True)
    for name in names:
        r = subprocess.run(["git", "-C", str(INFRA), "show", f"{BASELINE}:{name}"], capture_output=True)
        assert r.returncode == 0, f"git show {BASELINE}:{name} failed (fetch the baseline commit): {r.stderr!r}"
        (out / Path(name).name).write_bytes(r.stdout)
    return out


def setup_home(home, case):
    home.mkdir(parents=True, exist_ok=True)
    if case.get("unreadable"):
        token = home / ".config" / "bifrost" / "collector.token"
        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text("COLLECTOR\n")
        token.chmod(0o000)


def requests(platform):
    return [(c["method"], c["path"], c["headers"], c["raw"]) for c in platform.calls]


def run_wrapper(tmp_path, script_dir, case, tag):
    platform = Platform()
    try:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / "codex").write_text("#!" + sys.executable + "\nimport os\nopen(os.environ['LOG'], 'a').write(repr(sorted(k for k in os.environ if 'TOKEN' in k)) + '\\n')\n")
        (bin_dir / "codex").chmod(0o755)
        (tmp_path / "description.json").write_text(json.dumps(DESCRIPTION, ensure_ascii=False))
        report = tmp_path / "REPORT.md"
        report.unlink(missing_ok=True)
        home = tmp_path / ("home-" + tag)
        setup_home(home, case)
        env = clean_env(home, platform.url, BIFROST_DISPATCH_TOKEN="DISPATCH", LOG=tmp_path / f"child-{tag}.log",
                        **{k: v for k, v in case.items() if k != "unreadable"})
        env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
        args = ["--url", platform.url, "--session", "local_s", "--run-key", "rk-1", "--root", "R4", "--node", "R4:4.5-1",
                "--description", str(tmp_path / "description.json"), "--report", str(report), "--state-dir", str(tmp_path / ("state-" + tag)), "--repo", str(tmp_path)]
        proc = subprocess.run([sys.executable, str(script_dir / "dispatch-codex.py"), *args, "--", "PRIVATE"], env=env, capture_output=True, text=True, timeout=60)
        return proc.returncode, proc.stdout, proc.stderr, requests(platform), (tmp_path / f"child-{tag}.log").read_text()
    finally:
        platform.close()


@pytest.mark.parametrize("case", NO_TOKEN, ids=["no-token", "blank-token", "unreadable-file"])
def test_the_codex_wrapper_sends_what_the_baseline_sends(tmp_path, case):
    old = run_wrapper(tmp_path, baseline(tmp_path, "scripts/agent-host/dispatch-codex.py"), case, "old")
    new = run_wrapper(tmp_path, AGENT_HOST, case, "new")
    assert old[0] == 0 and len(old[3]) >= 5, "the baseline ran the whole flow: the comparison proves something"
    assert new == old


def run_register(tmp_path, script_dir, case, tag):
    platform = Platform()
    try:
        description = tmp_path / "claude.json"
        description.write_text(json.dumps({**DESCRIPTION, "executor": "claude", "provider": "anthropic"}, ensure_ascii=False))
        report = tmp_path / "REPORT-claude.md"
        report.write_text("report\n")
        home = tmp_path / ("rhome-" + tag)
        setup_home(home, case)
        env = clean_env(home, platform.url, BIFROST_DISPATCH_TOKEN="DISPATCH", **{k: v for k, v in case.items() if k != "unreadable"})
        state = tmp_path / ("rstate-" + tag)
        script = str(script_dir / "register-claude-work.py")
        outs = []
        for args in (["register", "--url", platform.url, "--session", "local_x", "--run-key", "rk", "--root", "R4", "--node", "R4:1", "--description", str(description), "--state-dir", str(state)],
                     ["heartbeat", "--state-dir", str(state)], ["submit", "--state-dir", str(state), "--report", str(report)], ["abandon", "--state-dir", str(state)]):
            p = subprocess.run([sys.executable, script, *args], env=env, capture_output=True, text=True, timeout=60)
            outs.append((p.returncode, p.stdout, p.stderr))
        return outs, requests(platform)
    finally:
        platform.close()


@pytest.mark.parametrize("case", NO_TOKEN, ids=["no-token", "blank-token", "unreadable-file"])
def test_register_claude_work_manual_mode_sends_what_the_baseline_sends(tmp_path, case):
    old_dir = baseline(tmp_path, "scripts/agent-host/register-claude-work.py", "scripts/agent-host/dispatch-codex.py")
    old = run_register(tmp_path, old_dir, case, "old")
    new = run_register(tmp_path, AGENT_HOST, case, "new")
    assert [o[0] for o in old[0]][:3] == [0, 0, 0] and len(old[1]) >= 6
    assert new == old


FAKE_CURL = r'''#!{python}
import json, os, sys
from pathlib import Path
args = sys.argv[1:]; url = args[-1]; root = Path(os.environ["TEST_ROOT"])
shown = ["<out>" if i and args[i - 1] == "-o" else ("@header" if a.startswith("@") else a) for i, a in enumerate(args)]
with (root / "calls").open("a") as f: f.write(json.dumps(shown) + "\n")
out = Path(args[args.index("-o") + 1])
if "/tasks/" in url:
    out.write_text(json.dumps({{"base_commit": os.environ["TEST_BASE"], "state": "ready"}})); print("200", end="")
else:
    out.write_text("{{}}"); print("500", end="")
'''


def run_handin(tmp_path, script, case, tag):
    root = tmp_path / ("handin-" + tag)
    work = root / "repo"
    work.mkdir(parents=True)
    bin_dir = root / "bin"
    bin_dir.mkdir()
    (bin_dir / "curl").write_text(FAKE_CURL.format(python=sys.executable))
    (bin_dir / "curl").chmod(0o755)
    # The squash Change-Id is random; a fixed one makes both versions' commits comparable.
    (bin_dir / "openssl").write_text("#!/bin/sh\necho " + "c" * 40 + "\n")
    (bin_dir / "openssl").chmod(0o755)
    home = root / "home"
    setup_home(home, case)
    env = {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "HOME": str(home), "TEST_ROOT": str(root), "GIT_CONFIG_GLOBAL": "/dev/null",
           "PLATFORM_AGENTRT_URL": "http://offline.invalid", "AGENTRT_COORDINATOR_AGENTD_TOKEN": "SENTINEL",
           "GIT_AUTHOR_DATE": "2026-11-04T00:00:00Z", "GIT_COMMITTER_DATE": "2026-11-04T00:00:00Z",
           **{k: v for k, v in case.items() if k != "unreadable"}}
    def git(*a):
        return subprocess.run(["git", *a], cwd=work, env=env, capture_output=True, text=True, check=True).stdout.strip()

    git("init", "-q", "-b", "unit")
    git("config", "user.name", "F")
    git("config", "user.email", "f@example.invalid")
    task = "t_" + "0" * 25 + "3"
    for name, message in (("base", "base"), ("a", "a\n\nClaude-Session: local_one"), ("b", "b")):
        (work / name).write_text(name)
        git("add", name)
        git("commit", "-qm", message)
    base = git("rev-list", "--max-parents=0", "HEAD")
    env["TEST_BASE"] = base
    commits = git("rev-list", "--reverse", base + "..HEAD").split()
    outs = []
    selected = [x for c in commits for x in ("--commit", c)]
    (root / "report").write_text("r\n")
    # The run binding hashes the platform URL, host, task and key: the same in both versions.
    for args in (["squash", "--task", task, "--base", base, *selected], ["squash", "--task", task, "--base", base],
                 ["run", "--task", task, "--report", str(root / "report"), "--remote", "x", "--key", "k"]):
        p = subprocess.run(["bash", str(script), *args], cwd=work, env=env, capture_output=True, text=True, timeout=60)
        outs.append((p.returncode, p.stdout, p.stderr.replace(str(root), "<root>")))
    files = {}
    for f in sorted((work / ".git" / "handin").rglob("*")):
        if f.is_file():
            files[str(f.relative_to(work / ".git"))] = f.read_text()
    calls = (root / "calls").read_text() if (root / "calls").exists() else ""
    return outs, files, calls.replace(str(root), "<root>")


@pytest.mark.parametrize("case", NO_TOKEN, ids=["no-token", "blank-token", "unreadable-file"])
def test_handin_squash_and_run_behave_as_the_baseline(tmp_path, case):
    old_script = baseline(tmp_path, "agent-config/scripts/landing/handin.sh") / "handin.sh"
    old = run_handin(tmp_path, old_script, case, "old")
    new = run_handin(tmp_path, HANDIN, case, "new")
    assert old[0][0][0] == 0 and old[1], "the baseline squashed and kept its state"
    assert new == old
