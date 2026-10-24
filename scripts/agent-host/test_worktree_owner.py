"""new-worktree.sh, the worktree record and the session hook (W-31 4.6 S3;
CUT-lifecycle-2026-10-24.md §4.2 and the S3 row of §5; review 539 F3, F4). The sweep's side
of S3 (no ended_at, no removal) is in scripts/test_prune_merged_branches.py.

    python3 -m pytest -q scripts/agent-host/test_worktree_owner.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import new_worktree  # noqa: E402
import worktree_owner as wo  # noqa: E402
from lifecycle_testlib import NEW_WORKTREE, World  # noqa: E402

HOOK = HERE.parent.parent / "agent-config" / "claude" / "hooks" / "worktree-lease.py"


@pytest.fixture(name="w")
def owner_world(tmp_path):
    return World(tmp_path)


def hook(w, payload, host=""):
    env = dict(w.env, CLAUDE_CODE_HOST_SESSION_ID=host)
    r = subprocess.run([sys.executable, str(HOOK)], input=payload if isinstance(payload, str) else json.dumps(payload),
                       env=env, capture_output=True, text=True)
    return r


def test_made_ended_renewed_ended_again_in_order(w):
    """The S3 acceptance: each step's state, through the shell entry point."""
    repo = w.repo()
    d = w.aw / "lane" / "bifrost-x"
    r = subprocess.run(["bash", str(NEW_WORKTREE), str(repo), str(d), "w31/lane", "--work", "W-31", "--purpose", "test"],
                       env=w.env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    s = w.look(d)
    assert s["state"] == "in-use" and s["record"]["session"] == "sess-1" and s["record"]["branch_created"] is True
    assert s["admin"].startswith(str(repo / ".git" / "worktrees"))
    assert w.git(d, "status", "--porcelain", "--ignored") == ""  # the record is not in the worktree
    w.end(d, "--reason", "lane done")
    s = w.look(d)
    assert s["state"] == "ended" and s["record"]["end_reason"] == "lane done"
    first_end = s["record"]["ended_at"]
    w.renew(d)
    s = w.look(d)
    assert s["state"] == "in-use" and "ended_at" not in s["record"]
    assert s["record"]["voided_ends"][-1]["ended_at"] == first_end
    w.end(d)
    assert w.look(d)["state"] == "ended"
    w.env["LIFECYCLE_END_MIN_AGE_MIN"] = "120"
    assert w.look(d)["state"] == "ended-recently"


def test_an_existing_branch_is_checked_out_not_claimed(w):
    repo = w.repo()
    w.git(repo, "branch", "w31/existing", "main")
    d = w.new_worktree(repo, "borrow/bifrost-x", branch="w31/existing")
    rec = w.look(d)["record"]
    assert rec["branch"] == "w31/existing" and rec["branch_created"] is False


def test_new_worktree_refuses_what_a_sweep_could_not_end_or_reach(w):
    repo = w.repo()
    w.repo("unlisted", listed=False)
    cases = [
        ([str(repo), str(w.ws / "wt"), "w31/a", "--work", "W-31"], "not under AGENT_WORK"),
        ([str(w.ws / "unlisted"), str(w.aw / "u"), "w31/a", "--work", "W-31"], "not a repository the lifecycle tools scan"),
        ([str(repo), str(w.aw / "x"), "w31/a"], "--work"),
        ([str(repo), str(w.aw / "x"), "w31/a", "--work", "W-31", "--cache-root", "../up"], "--cache-root"),
        ([str(repo), str(w.aw / "x"), "main", "--work", "W-31"], "not a branch name"),
    ]
    os.symlink(w.tmp, w.aw / "link")
    cases.append(([str(repo), str(w.aw / "link" / "x"), "w31/a", "--work", "W-31"], "symlink"))
    for args, msg in cases:
        rc, out = w.call(new_worktree.main, args)
        assert rc == 1 and msg in out, (args, out)
    env = dict(w.env)
    del env["CLAUDE_CODE_SESSION_ID"]
    rc = new_worktree.main([str(repo), str(w.aw / "y"), "w31/b", "--work", "W-31"], env)
    assert rc == 1 and not (w.aw / "y").exists()


def test_end_on_an_unregistered_worktree_needs_who_confirmed(w):
    repo = w.repo()
    d = w.aw / "old" / "bifrost-x"
    w.git(repo, "worktree", "add", "-q", "--detach", d, "origin/main")
    for args in (["--end", str(d)], ["--end", str(d), "--work", "W-31"], ["--end", str(d), "--by", "coordinator"]):
        rc, out = w.call(new_worktree.main, args)
        assert rc == 1 and "--work and --by" in out, args
    rc, out = w.call(new_worktree.main, ["--renew", str(d)])
    assert rc == 1
    w.end(d, "--work", "W-31", "--by", "coordinator, D-L8 check")
    rec = w.look(d)["record"]
    assert rec["registered_at_end"] is True and rec["ended_by"] == "coordinator, D-L8 check"


def test_session_end_ends_only_that_sessions_worktrees(w):
    repo = w.repo()
    mine = w.new_worktree(repo, "mine/bifrost-x", detach="origin/main", session="sess-1")
    theirs = w.new_worktree(repo, "theirs/bifrost-x", detach="origin/main", session="sess-2")
    r = hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-1", "reason": "other"})
    assert r.returncode == 0 and r.stdout == ""
    assert w.look(mine)["state"] == "ended" and w.look(theirs)["state"] == "in-use"
    assert w.look(mine)["record"]["ended_by"] == "session-end hook"


def test_a_clear_is_not_an_end_and_a_start_voids_one(w):
    repo = w.repo()
    d = w.new_worktree(repo, "lane/bifrost-x", detach="origin/main", session="sess-1")
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-1", "reason": "clear"})
    assert w.look(d)["state"] == "in-use"
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-1", "reason": "prompt_input_exit"})
    assert w.look(d)["state"] == "ended"
    r = hook(w, {"hook_event_name": "SessionStart", "session_id": "sess-1", "source": "resume"})
    assert r.returncode == 0 and r.stdout == ""
    assert w.look(d)["state"] == "in-use"


def test_the_host_session_carries_a_thread_across_a_new_cli_session(w):
    """After /clear the Desktop thread (CLAUDE_CODE_HOST_SESSION_ID) goes on in a new CLI session."""
    repo = w.repo()
    w.env["CLAUDE_CODE_HOST_SESSION_ID"] = "local_thread-1"
    d = w.new_worktree(repo, "lane/bifrost-x", detach="origin/main", session="sess-1")
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-9", "reason": "other"}, host="local_thread-1")
    assert w.look(d)["state"] == "ended"
    hook(w, {"hook_event_name": "SessionStart", "session_id": "sess-10", "source": "clear"}, host="local_thread-1")
    assert w.look(d)["state"] == "in-use"
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-11"}, host="local_thread-other")
    assert w.look(d)["state"] == "in-use"


def test_the_hook_never_breaks_a_session(w):
    for payload in ("not json", "[]", json.dumps({"hook_event_name": "SessionEnd", "session_id": "bad id with spaces"}),
                    json.dumps({"hook_event_name": "PreToolUse", "session_id": "sess-1"})):
        r = hook(w, payload)
        assert r.returncode == 0 and r.stdout == "", payload
    env = dict(w.env, LIFECYCLE_REPOS_FILE=str(w.tmp / "missing.txt"))
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"hook_event_name": "SessionEnd", "session_id": "sess-1"}),
                       env=env, capture_output=True, text=True)
    assert r.returncode == 0 and "cannot read the repository list" in r.stderr


def test_a_renewal_waits_for_the_sweep_and_finds_the_worktree_gone(w):
    """Review 539 F4: the sweep holds the record's flock through its last check and the
    removal; a renewal that comes meanwhile either gets the lock first (and the sweep sees the
    record changed) or after the removal, and then finds no record."""
    repo = w.repo()
    d = w.new_worktree(repo, "lane/bifrost-x", detach="origin/main", session="sess-1")
    w.end(d)
    admin, _ = wo.admin_of(str(d))
    with wo.OwnerLock(admin, 1):
        changed, probs = wo.session_event(dict(w.env), "start", "sess-1", "", "resume", wait=0.2)
        assert changed == [] and any("held by another process" in p for p in probs)
        w.git(repo, "worktree", "remove", d)  # the sweep's removal, still under the lock
    with pytest.raises(wo.Gone):
        with wo.OwnerLock(admin, 1):
            pass
    changed, probs = wo.session_event(dict(w.env), "start", "sess-1", "", "resume", wait=0.2)
    assert changed == [] and probs == []


def test_records_that_are_not_usable_are_refused(w):
    good = wo.new_record("W-31", "sess-1", "", "", None, False, "", [], 1_700_000_000, 12)
    assert wo.problems(good) == []
    for k, v in (("schema", 2), ("work", "W31"), ("session", ""), ("cache_roots", ["../x"]), ("ended_at", "yesterday"),
                 ("branch_created", "yes"), ("lease_until", 5)):
        bad = dict(good, **{k: v})
        assert wo.problems(bad), k
    rec = dict(good)
    wo.end(rec, 1_700_000_100, "t", "")
    assert wo.end_evidence(rec, 1_700_000_100, 0) == (None, "")
    assert wo.end_evidence(rec, 1_700_000_050, 0)[0] == "ended-in-future"
    assert wo.end_evidence(rec, 1_700_000_200, 3600)[0] == "end-too-recent"
    rec["lease_until"] = wo.fmt(1_700_009_999)
    assert wo.end_evidence(rec, 1_700_010_000, 0)[0] == "lease-renewed"
    with pytest.raises(wo.OwnerError):
        wo.write_record(str(w.tmp), dict(good, work="nope"))
