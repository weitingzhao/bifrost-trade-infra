"""S1-5 no-op equivalence: without a collector token the wrapper, register-claude-work.py and
handin.sh behave as the scripts of 46d1a32 do (R5:5.5-12 S1-5).

python3 -m pytest -q scripts/agent-host/tests/test_collector_s15_noop.py
Compared: exit code, stdout, stderr, every request (method, path, Authorization,
X-Bifrost-Session, Content-Type, X-Artifact-Kind, body bytes), the files
handin.sh leaves under .git/handin, the wrapper's state.json, and, run as the
coordinator runs it (one file copied alone into an empty directory), --help, a
whole run and a refused registration. Two differences are intended and
checked as such, not as equal: the Codex child's environment lacks exactly
the credentials the test gives the wrapper, every other variable equal with
its value (review M5, R2-S2), and the wrapper's run directory gains
codex.json (pid, start time, mode 600) and child.json names its version (M1). Not compared: timing, register-claude-work.py's state files,
crash and resume paths. Requests go to a local fake platform or a fake curl;
the baseline comes from git, and without the commit the test fails.
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


def single_copy(tmp_path, source: Path, tag) -> Path:
    """The coordinator's way: this one file, copied alone into an empty directory."""
    directory = tmp_path / ("copy-" + tag)
    directory.mkdir()
    (directory / ".dispatch-codex.py").write_bytes(source.read_bytes())
    return directory / ".dispatch-codex.py"


def run_wrapper(tmp_path, script, case, tag, refuse=0, extra_env=None):
    platform = Platform()
    platform.refuse_registration = refuse
    try:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / "codex").write_text("#!" + sys.executable + "\nimport json, os\nopen(os.environ['LOG'], 'a').write(json.dumps(dict(os.environ)) + '\\n')\n")
        (bin_dir / "codex").chmod(0o755)
        (tmp_path / "description.json").write_text(json.dumps(DESCRIPTION, ensure_ascii=False))
        report = tmp_path / "REPORT.md"
        report.unlink(missing_ok=True)
        home = tmp_path / ("home-" + tag)
        setup_home(home, case)
        env = clean_env(home, platform.url, BIFROST_DISPATCH_TOKEN="DISPATCH", LOG=tmp_path / f"child-{tag}.log", PLATFORM_REPORTER_TOKEN="R",
                        AGENTRT_COORDINATOR_AGENTD_TOKEN="A", LANG="C", **(extra_env or {}), **{k: v for k, v in case.items() if k != "unreadable"})
        env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
        state = tmp_path / ("state-" + tag)
        args = ["--url", platform.url, "--session", "local_s", "--run-key", "rk-1", "--root", "R4", "--node", "R4:4.5-1",
                "--description", str(tmp_path / "description.json"), "--report", str(report), "--state-dir", str(state), "--repo", str(tmp_path)]
        proc = subprocess.run([sys.executable, str(script), *args, "--", "PRIVATE"], env=env, capture_output=True, text=True, timeout=60)
        log = tmp_path / f"child-{tag}.log"
        child = json.loads(log.read_text()) if log.exists() else None
        runs = list(state.glob("*/state.json")) if state.exists() else []
        files = sorted(f.name for f in runs[0].parent.iterdir()) if runs else []
        saved = json.loads(runs[0].read_text()) if runs else None
        codex = runs[0].parent / "codex.json" if runs else None
        record = (json.loads(codex.read_text()), oct(codex.stat().st_mode & 0o777)) if codex and codex.exists() else None
        if child is not None:  # the two runs differ only by their tag in paths and their fake platform's port
            child = {k: v.replace("-" + tag, "-<tag>").replace(platform.url, "<platform>") for k, v in child.items()}
        return {"result": (proc.returncode, proc.stdout, proc.stderr.replace(str(tmp_path), "<tmp>")), "requests": requests(platform),
                "child": child, "files": files, "state": saved, "codex": record}
    finally:
        platform.close()


# The credentials this test hands the wrapper, which the baseline passed on to Codex and the new one must not.
REMOVED = ("PLATFORM_REPORTER_TOKEN", "AGENTRT_COORDINATOR_AGENTD_TOKEN", "PLATFORM_COLLECTOR_TOKEN")


def assert_wrapper_equivalent(old, new):
    assert new["result"] == old["result"] and new["requests"] == old["requests"] and new["state"] == old["state"]
    if old["child"] is not None:
        # Intended (M5): exactly those credentials are gone; every other variable is there with its value.
        assert {"PLATFORM_REPORTER_TOKEN", "AGENTRT_COORDINATOR_AGENTD_TOKEN"} <= set(old["child"])
        assert new["child"] == {k: v for k, v in old["child"].items() if k not in REMOVED}
        assert new["child"]["PLATFORM_HEARTBEAT_URL"] == old["child"]["PLATFORM_HEARTBEAT_URL"], "review R2-M1: the beat's address stays"
    assert [f for f in new["files"] if f != "codex.json"] == old["files"], "intended (M1): codex.json only"
    if new["files"] and old["child"] is not None:
        (record, mode) = new["codex"]
        assert isinstance(record["pid"], int) and record["started"].startswith(("ps:", "proc:")) and mode == "0o600"


@pytest.mark.parametrize("case", NO_TOKEN, ids=["no-token", "blank-token", "unreadable-file"])
def test_the_codex_wrapper_copied_alone_runs_as_the_baseline(tmp_path, case):
    """Review M6: run exactly as dispatch.sh runs it, one copied file in an empty directory."""
    old_script = single_copy(tmp_path, baseline(tmp_path, "scripts/agent-host/dispatch-codex.py") / "dispatch-codex.py", "old")
    new_script = single_copy(tmp_path, AGENT_HOST / "dispatch-codex.py", "new")
    old = run_wrapper(tmp_path, old_script, case, "old")
    new = run_wrapper(tmp_path, new_script, case, "new")
    assert old["result"][0] == 0 and len(old["requests"]) >= 5, "the baseline ran the whole flow: the comparison proves something"
    assert_wrapper_equivalent(old, new)
    env = clean_env(tmp_path / "h", "http://offline.invalid")
    helps = [subprocess.run([sys.executable, str(s), "--help"], env=env, capture_output=True, text=True) for s in (old_script, new_script)]
    assert helps[0].returncode == helps[1].returncode == 0 and helps[0].stderr == helps[1].stderr == ""


def test_the_codex_wrapper_copied_alone_fails_a_refused_registration_as_the_baseline(tmp_path):
    old = run_wrapper(tmp_path, single_copy(tmp_path, baseline(tmp_path, "scripts/agent-host/dispatch-codex.py") / "dispatch-codex.py", "old"), {}, "old", refuse=1)
    new = run_wrapper(tmp_path, single_copy(tmp_path, AGENT_HOST / "dispatch-codex.py", "new"), {}, "new", refuse=1)
    assert old["result"][0] == 1 and "HTTP 400" in old["result"][2] and old["child"] is None
    assert_wrapper_equivalent(old, new)


def test_the_codex_wrapper_copied_alone_also_runs_as_a_collector(tmp_path):
    new = run_wrapper(tmp_path, single_copy(tmp_path, AGENT_HOST / "dispatch-codex.py", "new"), {}, "new", extra_env={"PLATFORM_COLLECTOR_TOKEN": "C"})
    assert new["result"][0] == 0, new["result"]
    [registration] = [json.loads(r[3]) for r in new["requests"] if r[1] == "/api/v1/agentrt/external-work"]
    assert (registration["vendor"], registration["session"], registration["epoch"]) == ("codex", "rk-1", 1)


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
    out.write_text(json.dumps({{"base_commit": os.environ["TEST_BASE"], "state": "ready", "repo": "platform", "mission_id": "M-1"}})); print("200", end="")
elif "/landing/missions/" in url:
    out.write_text(json.dumps({{"roots": []}})); print("200", end="")
elif "/tasks?mission=" in url:
    out.write_text(json.dumps({{"tasks": []}})); print("200", end="")
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


def without_one_per_repo_reads(calls):
    """The calls less the three reads run makes before it binds, which the baseline predates: the task, its mission's
    landing and its mission's tasks (one hand-in per repository at a time, R5:5.6-2). They must be there, in order."""
    lines = calls.splitlines(keepends=True)
    urls = [json.loads(line)[-1] for line in lines]
    i = next(k for k, u in enumerate(urls) if u.endswith("/landing/missions/M-1"))
    assert urls[i - 1].endswith("/tasks/t_" + "0" * 25 + "3") and urls[i + 1].endswith("/tasks?mission=M-1"), urls
    return "".join(lines[:i - 1] + lines[i + 2:])


@pytest.mark.parametrize("case", NO_TOKEN, ids=["no-token", "blank-token", "unreadable-file"])
def test_handin_squash_and_run_behave_as_the_baseline(tmp_path, case):
    old_script = baseline(tmp_path, "agent-config/scripts/landing/handin.sh") / "handin.sh"
    old = run_handin(tmp_path, old_script, case, "old")
    new = run_handin(tmp_path, HANDIN, case, "new")
    assert old[0][0][0] == 0 and old[1], "the baseline squashed and kept its state"
    assert (new[0], new[1], without_one_per_repo_reads(new[2])) == old
