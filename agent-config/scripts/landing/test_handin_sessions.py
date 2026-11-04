"""handin.sh says which sessions wrote the work (R5:5.5-12 §5, S1-5).

python3 -m pytest -q agent-config/scripts/landing/test_handin_sessions.py
A real temporary Git repository; curl is a fake that answers GET
/api/v1/agent/threads from a table and records its arguments. No platform.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HANDIN = Path(__file__).resolve().with_name("handin.sh")
TASK = "t_" + "0" * 25 + "2"
LINKED, UNREG, ODD = "local_linked", "local_unreg", "local_odd"
FAKE_CURL = r'''#!{python}
import json, os, sys
from pathlib import Path
args = sys.argv[1:]; url = args[-1]
root = Path(os.environ["TEST_ROOT"])
header = args[args.index("-H") + 1]
with (root / "calls").open("a") as f:
    f.write(json.dumps({{"url": url, "header": Path(header[1:]).read_text() if header.startswith("@") else "ARGV"}}) + "\n")
out = Path(args[args.index("-o") + 1])
if "/api/v1/agent/threads?" in url:
    table = json.loads(os.environ["TEST_THREADS"])
    query = url.split("?", 1)[1]
    if query in table.get("fail", []):
        out.write_text("{{}}"); print("503", end=""); sys.exit(0)
    out.write_text(json.dumps({{"threads": [{{"binding": {{"state": s}}}} for s in table.get(query, [])]}}))
    print("200", end=""); sys.exit(0)
if "/tasks/" in url:
    out.write_text(json.dumps({{"base_commit": os.environ["TEST_BASE"], "state": "ready"}})); print("200", end=""); sys.exit(0)
out.write_text("{{}}"); print("500", end="")
'''
THREADS = {"sidebar=" + LINKED: ["unlinked", "linked"], "sidebar=" + UNREG: [], "session=" + UNREG: ["unlinked", "refused"],
           "sidebar=" + ODD: ["unsupported", "unlinked"]}


@pytest.fixture
def repo(tmp_path):
    work = tmp_path / "repo"
    work.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "curl").write_text(FAKE_CURL.format(python=sys.executable))
    (bin_dir / "curl").chmod(0o755)
    env = {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "HOME": str(tmp_path / "home"), "TEST_ROOT": str(tmp_path),
           "PLATFORM_AGENTRT_URL": "http://offline.invalid", "AGENTRT_COORDINATOR_AGENTD_TOKEN": "SENTINEL_AGENTD",
           "TEST_THREADS": json.dumps(THREADS), "GIT_CONFIG_GLOBAL": "/dev/null"}

    def git(*args):
        return subprocess.run(["git", *args], cwd=work, env=env, capture_output=True, text=True, check=True).stdout.strip()

    git("init", "-q", "-b", "unit")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    (work / "base").write_text("base\n")
    git("add", "base")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    commits = []
    for name, trailer in (("a", LINKED), ("b", UNREG), ("c", None), ("d", LINKED), ("e", ODD)):
        (work / name).write_text(name + "\n")
        git("add", name)
        git("commit", "-qm", f"work {name}" + (f"\n\nClaude-Session: {trailer}" if trailer else ""))
        commits.append(git("rev-parse", "HEAD"))
    env["TEST_BASE"] = base
    yield SimpleNamespace(root=tmp_path, work=work, env=env, git=git, base=base, commits=commits)


def handin(r, *args, collector=True, check=True):
    env = dict(r.env, PLATFORM_COLLECTOR_TOKEN="SENTINEL_COLLECTOR") if collector else r.env
    proc = subprocess.run(["bash", str(HANDIN), *args], cwd=r.work, env=env, capture_output=True, text=True, timeout=60)
    if check:
        assert proc.returncode == 0, proc.stderr
    assert "SENTINEL" not in proc.stdout + proc.stderr
    return proc


def squash(r, *extra, collector=True):
    selected = [x for c in r.commits for x in ("--commit", c)]
    return handin(r, "squash", "--task", TASK, "--base", r.base, *selected, *extra, collector=collector)


def calls(r):
    path = r.root / "calls"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_squash_says_registered_unregistered_uncertain_and_no_trailer_unknown(repo):
    proc = squash(repo)
    lines = [line for line in proc.stderr.splitlines() if line.startswith("handin: session") or "Claude-Session" in line]
    assert lines == [
        f"handin: commit {repo.commits[2][:9]}: unknown (no Claude-Session trailer)",
        f"handin: session {LINKED}: registered",
        f"handin: session {UNREG}: unregistered",
        f"handin: session {ODD}: uncertain",
    ]
    queried = [c["url"].split("/api/v1/agent/threads?")[1] for c in calls(repo)]
    assert queried == ["sidebar=" + LINKED, "sidebar=" + UNREG, "session=" + UNREG, "sidebar=" + ODD], "sidebar first, the session id only when nothing matched"
    assert all(c["header"] == "Authorization: Bearer SENTINEL_COLLECTOR\n" for c in calls(repo)), "the token goes in a header file, never argv"
    result = proc.stdout.strip()
    saved = json.loads((repo.work / ".git/handin/squash" / TASK / "sessions.json").read_text())
    assert saved["commit"] == result and saved["commits_without_trailer"] == [repo.commits[2]]
    assert [(s["session"], s["conclusion"]) for s in saved["sessions"]] == [(LINKED, "registered"), (UNREG, "unregistered"), (ODD, "uncertain")]
    # The same squash again is an idempotent retry: the same words, no new query.
    before = len(calls(repo))
    again = handin(repo, "squash", "--task", TASK, "--base", repo.base)
    assert again.stdout.strip() == result and len(calls(repo)) == before and f"handin: session {UNREG}: unregistered" in again.stderr


def test_a_squashed_commit_has_no_trailer_so_squashing_it_again_says_unknown(repo):
    first = squash(repo).stdout.strip()
    (repo.work / "rework").write_text("rework\n")
    repo.git("add", "rework")
    repo.git("commit", "-qm", "rework without a session")
    rework = repo.git("rev-parse", "HEAD")
    proc = handin(repo, "squash", "--task", TASK, "--base", repo.base, "--attempt", "2", "--commit", first, "--commit", rework)
    assert f"handin: commit {first[:9]}: unknown (no Claude-Session trailer)" in proc.stderr
    assert f"handin: commit {rework[:9]}: unknown (no Claude-Session trailer)" in proc.stderr
    assert "registered" not in proc.stderr


def test_run_replays_the_squash_result_into_unregistered_sessions_json(repo):
    result = squash(repo).stdout.strip()
    (repo.root / "report").write_text("report\n")
    before = len(calls(repo))
    proc = handin(repo, "run", "--task", TASK, "--report", str(repo.root / "report"), "--remote", "x", "--key", "k", check=False)
    assert f"handin: session {UNREG}: unregistered" in proc.stderr and f"handin: session {LINKED}: registered" in proc.stderr
    threads = [c for c in calls(repo)[before:] if "/agent/threads" in c["url"]]
    assert threads == [], "run only replays; it asks nothing"
    [out] = list((repo.work / ".git/handin/runs").glob("*.unregistered_sessions.json"))
    assert json.loads(out.read_text())["commit"] == result


def test_without_a_collector_token_nothing_is_asked_or_written(repo):
    proc = squash(repo, collector=False)
    assert "handin: session" not in proc.stderr and "Claude-Session" not in proc.stderr
    assert calls(repo) == [] and not (repo.work / ".git/handin/squash" / TASK / "sessions.json").exists()


def test_a_failed_read_is_unknown(repo):
    repo.env["TEST_THREADS"] = json.dumps({**THREADS, "fail": ["sidebar=" + LINKED]})
    proc = squash(repo)
    assert f"handin: session {LINKED}: unknown" in proc.stderr
