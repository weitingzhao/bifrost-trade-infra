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
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import new_worktree  # noqa: E402
import worktree_owner as wo  # noqa: E402
import worktree_sessions as ws  # noqa: E402
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
    # an end that matches only by host counts from a session that started after the record's
    # ownership began (its marker says so): sess-9 never started, so its end does nothing
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-9", "reason": "other"}, host="local_thread-1")
    assert w.look(d)["state"] == "in-use"
    hook(w, {"hook_event_name": "SessionStart", "session_id": "sess-10", "source": "clear"}, host="local_thread-1")
    assert w.look(d)["state"] == "in-use"
    time.sleep(1.1)  # past the start's second: ended_at has whole seconds
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-10", "reason": "other"}, host="local_thread-1")
    assert w.look(d)["state"] == "ended"
    hook(w, {"hook_event_name": "SessionStart", "session_id": "sess-11", "source": "startup"}, host="local_thread-other")
    assert w.look(d)["state"] == "ended"


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
        changed, probs, unsafe, published = ws.session_event(dict(w.env), "start", "sess-1", "", "resume", budget=0.2)
        assert changed == [] and any("held by another process" in p for p in probs) and published and unsafe == []
        w.git(repo, "worktree", "remove", d)  # the sweep's removal, still under the lock
    with pytest.raises(wo.Gone):
        with wo.OwnerLock(admin, 1):
            pass
    changed, probs, unsafe, published = ws.session_event(dict(w.env), "start", "sess-1", "", "resume", budget=0.2)
    assert changed == [] and probs == [] and published


def test_records_that_are_not_usable_are_refused(w):
    S = wo.NS
    good = wo.new_record("W-31", "sess-1", "", "", None, False, "", [], 1_700_000_000 * S, 12)
    assert wo.problems(good) == []
    for k, v in (("schema", 2), ("work", "W31"), ("session", ""), ("cache_roots", ["../x"]), ("ended_at", "yesterday"),
                 ("branch_created", "yes"), ("lease_until", 5), ("owner_since_ns", 5), ("generation", 0)):
        bad = dict(good, **{k: v})
        assert wo.problems(bad), k
    rec = dict(good)
    wo.end(rec, 1_700_000_100 * S + 7, "t", "")
    assert rec["ended_at_ns"] == 1_700_000_100 * S + 7 and wo.problems(rec) == []
    assert wo.end_evidence(rec, 1_700_000_100.5, 0) == (None, "")
    assert wo.end_evidence(rec, 1_700_000_050, 0)[0] == "ended-in-future"
    assert wo.end_evidence(rec, 1_700_000_200, 3600)[0] == "end-too-recent"
    rec["lease_until"] = wo.fmt(1_700_009_999)
    assert wo.end_evidence(rec, 1_700_010_000, 0)[0] == "lease-renewed"
    with pytest.raises(wo.OwnerError):
        wo.write_record(str(w.tmp), dict(good, work="nope"))


def hold(admin):
    """Another process holding a record's flock until killed."""
    p = subprocess.Popen([sys.executable, "-c", (
        "import fcntl,os,time\n"
        f"fd=os.open({os.path.join(admin, wo.OWNER_LOCK)!r}, os.O_RDWR|os.O_CREAT, 0o600)\n"
        "fcntl.flock(fd, fcntl.LOCK_EX); print('held', flush=True); time.sleep(60)\n")], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    return p


def test_unrelated_locked_records_do_not_stop_a_resumed_session(w):
    """Review 551 D1: records are filtered by session before any lock is taken, under one
    time budget for the whole event."""
    repo = w.repo()
    others = [w.new_worktree(repo, f"other{n}/bifrost-x", detach="origin/main", session=f"sess-{n}") for n in (2, 3)]
    mine = w.new_worktree(repo, "mine/bifrost-x", detach="origin/main", session="sess-1")
    w.end(mine)
    holders = [hold(wo.admin_of(str(d))[0]) for d in others]
    try:
        changed, probs, _, _ = ws.session_event(dict(w.env), "start", "sess-1", "", "resume", budget=1.0)
    finally:
        for h in holders:
            h.kill()
            h.wait()
    assert changed == [wo.admin_of(str(mine))[0]] and probs == []
    assert w.look(mine)["state"] == "in-use"


def test_a_renewal_that_fails_still_leaves_the_worktree_in_use(w):
    """Review 551 D1: the session marker is written before any record; a record the renewal
    cannot write keeps its old ended_at, and the sweep still counts the worktree in use. A
    later end moves ended_at past the marker."""
    repo = w.repo()
    d = w.new_worktree(repo, "lane/bifrost-x", detach="origin/main", session="sess-1")
    w.end(d)
    admin = Path(wo.admin_of(str(d))[0])
    admin.chmod(0o555)
    try:
        changed, probs, _, _ = ws.session_event(dict(w.env), "start", "sess-1", "", "resume")
    finally:
        admin.chmod(0o755)
    assert changed == [] and probs and "ended_at" in w.look(d)["record"]
    assert w.look(d)["state"] == "session-resumed"
    rc, out, rep = w.prune("--apply")
    assert d.exists() and World.items(rep)[str(d)]["reason"] == "session-resumed"
    # ended_at has whole seconds and the marker does not: an end in the same second as the
    # start still counts as resumed (the safe side), so this end comes a second later
    time.sleep(1.1)
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-1", "reason": "other"})
    assert w.look(d)["state"] == "ended"
    marker = Path(ws.marker_path(w.env, "sess-1"))
    marker.write_text("{not json")
    assert w.look(d)["state"] == "session-marker-unreadable"


def test_take_hands_a_worktree_to_another_session(w):
    """Review 551 D2: after --take the old session's end matches nothing; the new one's does."""
    repo = w.repo()
    d = w.new_worktree(repo, "shared/bifrost-x", detach="origin/main", session="sess-a")
    rc, out = w.call(new_worktree.main, ["--take", str(d), "--session", "sess-b"])
    assert rc == 0, out
    rec = w.look(d)["record"]
    assert rec["session"] == "sess-b" and rec["taken_from"][-1]["session"] == "sess-a"
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-a", "reason": "other"})
    assert w.look(d)["state"] == "in-use"
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-b", "reason": "other"})
    assert w.look(d)["state"] == "ended"


def test_a_session_starting_inside_someone_elses_worktree_keeps_it(w):
    """Review 551 D2: a SessionStart whose cwd is inside another session's worktree marks
    foreign use; the sweep keeps it until --take, which clears the mark."""
    repo = w.repo()
    d = w.new_worktree(repo, "theirs/bifrost-x", detach="origin/main", session="sess-a")
    w.end(d)
    r = hook(w, {"hook_event_name": "SessionStart", "session_id": "sess-b", "source": "startup", "cwd": str(d)})
    assert r.returncode == 0 and r.stdout == ""
    assert w.look(d)["state"] == "used-by-another-session"
    rc, out, rep = w.prune("--apply")
    assert d.exists() and World.items(rep)[str(d)]["reason"] == "used-by-another-session"
    rc, out = w.call(new_worktree.main, ["--take", str(d), "--session", "sess-b"])
    assert rc == 0 and "foreign_use" not in w.look(d)["record"] and w.look(d)["state"] == "in-use"


def test_a_resume_that_cannot_publish_its_marker_still_keeps_the_worktree(w):
    """Review 552 A2: markers directory unwritable and the record's lock held: the renewal and
    the marker both fail, so the hook writes a resume-failed state into the admin dir; the
    sweep keeps the worktree on it. When even that cannot be written, the hook says so to
    the session and the user (JSON on stdout). A missing markers directory is unknown."""
    repo = w.repo()
    d = w.new_worktree(repo, "lane/bifrost-x", detach="origin/main", session="sess-1")
    w.end(d)
    time.sleep(1.1)  # the resume comes in a later second than the end
    admin = Path(wo.admin_of(str(d))[0])
    markers = Path(ws.markers_dir(w.env))
    markers.chmod(0o555)
    holder = hold(str(admin))
    try:
        changed, probs, unsafe, published = ws.session_event(dict(w.env), "start", "sess-1", "", "resume", budget=0.3)
    finally:
        holder.kill()
        holder.wait()
        markers.chmod(0o755)
    assert changed == [] and not published and unsafe == []
    assert (admin / wo.RESUME_FAILED).exists() and w.look(d)["state"] == "resume-failed"
    rc, out, rep = w.prune("--apply")
    assert d.exists() and World.items(rep)[str(d)]["reason"] == "resume-failed"
    (admin / wo.RESUME_FAILED).unlink()
    markers.chmod(0o555)
    admin.chmod(0o555)
    holder = hold(str(admin))
    try:
        r = hook(w, {"hook_event_name": "SessionStart", "session_id": "sess-1", "source": "resume"})
    finally:
        holder.kill()
        holder.wait()
        markers.chmod(0o755)
        admin.chmod(0o755)
    assert r.returncode == 0
    said = json.loads(r.stdout)
    assert str(d) in said["hookSpecificOutput"]["additionalContext"] and "--renew" in said["systemMessage"]
    for p in markers.iterdir():
        p.unlink()
    markers.rmdir()
    assert w.look(d)["state"] == "session-state-unknown"


def test_take_for_another_session_does_not_inherit_the_callers_host(w):
    """Review 552 A3, first case: run in A's thread, --take --session B records B's host as
    unknown (not A's), so A's end, which matches only by host, ends nothing."""
    repo = w.repo()
    w.env["CLAUDE_CODE_SESSION_ID"], w.env["CLAUDE_CODE_HOST_SESSION_ID"] = "sess-a", "local_a"
    d = w.new_worktree(repo, "a/bifrost-x", detach="origin/main", session="sess-a")
    rc, out = w.call(new_worktree.main, ["--take", str(d), "--session", "sess-b"])
    assert rc == 0, out
    rec = w.look(d)["record"]
    assert (rec["session"], rec["host_session"], rec["generation"]) == ("sess-b", "", 2)
    hook(w, {"hook_event_name": "SessionStart", "session_id": "sess-a2", "source": "clear"}, host="local_a")
    time.sleep(1.1)
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-a2", "reason": "other"}, host="local_a")
    assert w.look(d)["state"] == "in-use"


def test_a_late_end_of_an_older_session_of_the_same_thread_does_nothing(w):
    """Review 552 A3, second case: two CLI sessions of one Desktop thread. B takes the
    worktree (its own host recorded, generation 2); the older session A ends afterwards and
    matches only by host, but A started before this ownership began: nothing. B's end ends it."""
    repo = w.repo()
    hook(w, {"hook_event_name": "SessionStart", "session_id": "sess-a", "source": "startup"}, host="local_t")
    w.env["CLAUDE_CODE_HOST_SESSION_ID"] = "local_t"
    d = w.new_worktree(repo, "t/bifrost-x", detach="origin/main", session="sess-a")
    time.sleep(1.1)
    hook(w, {"hook_event_name": "SessionStart", "session_id": "sess-b", "source": "clear"}, host="local_t")
    w.env["CLAUDE_CODE_SESSION_ID"] = "sess-b"
    rc, out = w.call(new_worktree.main, ["--take", str(d), "--session", "sess-b"])
    assert rc == 0, out
    rec = w.look(d)["record"]
    assert (rec["session"], rec["host_session"], rec["generation"]) == ("sess-b", "local_t", 2)
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-a", "reason": "other"}, host="local_t")
    assert w.look(d)["state"] == "in-use"
    time.sleep(1.1)  # past B's start second (ended_at has whole seconds)
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-b", "reason": "other"}, host="local_t")
    assert w.look(d)["state"] == "ended"


def test_one_second_holds_a_start_a_take_and_a_late_old_end(w):
    """Review 553 A1: times in nanoseconds. Within one second: A starts, C (same thread)
    starts, B starts, A hands the worktree to B; then A's and C's late ends arrive. A owned
    an earlier generation and C started before this one: neither ends B's use. B's end does."""
    repo = w.repo()
    w.env["CLAUDE_CODE_SESSION_ID"], w.env["CLAUDE_CODE_HOST_SESSION_ID"] = "sess-a", "local_t"
    hook(w, {"hook_event_name": "SessionStart", "session_id": "sess-a", "source": "startup"}, host="local_t")
    d = w.new_worktree(repo, "t/bifrost-x", detach="origin/main", session="sess-a")
    # C never owns it and starts after it was made, before the take: only owner_since keeps
    # C's end out; A is kept out by the generation as well
    for sid in ("sess-c", "sess-b"):
        hook(w, {"hook_event_name": "SessionStart", "session_id": sid, "source": "startup"}, host="local_t")
    rc, out = w.call(new_worktree.main, ["--take", str(d), "--session", "sess-b", "--host-session", "local_t"])
    assert rc == 0, out
    for sid in ("sess-a", "sess-c"):
        hook(w, {"hook_event_name": "SessionEnd", "session_id": sid, "reason": "other"}, host="local_t")
        assert w.look(d)["state"] == "in-use", sid
    # A resumes after the take: its marker is now newer than owner_since, yet A owned an
    # earlier generation, so its end still matches nothing (the generation, not only time)
    hook(w, {"hook_event_name": "SessionStart", "session_id": "sess-a", "source": "resume"}, host="local_t")
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-a", "reason": "other"}, host="local_t")
    assert w.look(d)["state"] == "in-use"
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-b", "reason": "other"}, host="local_t")
    assert w.look(d)["state"] == "ended"


def test_a_resume_and_an_end_in_one_second_end_it(w):
    """Review 553 A4: a start and a normal end within the same second leave it ended, and a
    sweep removes it once the grace period passes. A record from before 553 (ended_at to the
    second only) with a marker inside that second stays kept."""
    repo = w.repo()
    d = w.new_worktree(repo, "quick/bifrost-x", detach="origin/main", session="sess-1")
    hook(w, {"hook_event_name": "SessionStart", "session_id": "sess-1", "source": "resume"})
    hook(w, {"hook_event_name": "SessionEnd", "session_id": "sess-1", "reason": "other"})
    assert w.look(d)["state"] == "ended"
    old = w.new_worktree(repo, "old/bifrost-x", detach="origin/main", session="sess-2")
    w.end(old)
    admin = Path(wo.admin_of(str(old))[0])
    rec = json.loads((admin / wo.OWNER).read_text())
    rec.pop("ended_at_ns")
    (admin / wo.OWNER).write_text(json.dumps(rec))
    sec = wo.to_seconds(rec["ended_at"])
    Path(ws.marker_path(w.env, "sess-2")).write_text(json.dumps({"session": "sess-2", "active_since_ns": int(sec) * wo.NS + 5}))
    rc, out, rep = w.prune("--apply")
    assert rc == 0 and not d.exists(), out
    assert old.exists() and World.items(rep)[str(old)]["reason"] == "session-resumed"


def test_the_hook_puts_the_instruction_first_and_caps_the_rest(w):
    """Review 553 D2: with many worktrees and a long error, both fields start with the
    instruction, list at most 20 paths and say how many more, and cut the error alone."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("worktree_lease", HOOK)
    hook_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook_mod)
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        hook_mod.warn("start", "E" * 5000, [f"/w/{n:03d}" for n in range(30)])
    said = json.loads(buf.getvalue())
    for text in (said["systemMessage"], said["hookSpecificOutput"]["additionalContext"]):
        assert text.startswith("Use none of these worktrees before") and "--renew <dir> succeeds" in text[:200]
        assert "/w/019" in text and "/w/020" not in text and "(and 10 more)" in text
        assert "E" * 400 in text and "E" * 401 not in text
