"""prune-merged-branches.sh --local-only, the protections beyond the §5 acceptance cases
(those are in scripts/test_prune_merged_branches.py): locks, roots, symlinks, tool checkouts,
clones, lsof, read failures, stale and transient remote refs, branch end evidence, cache
roots, the second check (W-31 4.6 S2; CUT-lifecycle-2026-10-24.md §2-§4; review 539 F1-F4).
Each test builds a throwaway world (lifecycle_testlib.py); nothing outside it is touched.

    python3 -m pytest -q scripts/agent-host/test_lifecycle_local.py
"""

from __future__ import annotations

import fcntl
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lifecycle_items  # noqa: E402
import lifecycle_local  # noqa: E402
import worktree_owner as wo  # noqa: E402
from lifecycle_testlib import World  # noqa: E402


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


def ended(w, repo, rel, **kw):
    d = w.new_worktree(repo, rel, **kw)
    w.end(d)
    return d


def reason(rep, path):
    return World.items(rep)[str(path)]["reason"]


def test_someone_elses_git_lock_is_never_touched(w):
    repo = w.repo()
    d = ended(w, repo, "held/bifrost-x", detach="origin/main")
    w.git(repo, "worktree", "lock", "--reason", "codex review 600", d)
    rc, out, rep = w.sweep("--apply")
    assert rc == 0 and d.exists() and reason(rep, d) == "locked"
    assert "locked codex review 600" in w.git(repo, "worktree", "list", "--porcelain")


def hold_record_lock(admin):
    """Another process holding the record's flock until killed (a live sweep or renewal)."""
    p = subprocess.Popen([sys.executable, "-c", (
        "import fcntl,os,sys,time\n"
        f"fd=os.open({os.path.join(admin, wo.OWNER_LOCK)!r}, os.O_RDWR|os.O_CREAT, 0o600)\n"
        "fcntl.flock(fd, fcntl.LOCK_EX); print('held', flush=True); time.sleep(60)\n")], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    return p


def test_a_lock_a_dead_sweep_left_is_released_and_the_worktree_judged_again(w):
    """A lifecycle:<run> lock whose record nobody holds is a dead sweep's: released. One whose
    record flock is held belongs to a live sweep (under another lock dir): kept."""
    repo = w.repo()
    d = ended(w, repo, "stale/bifrost-x", detach="origin/main")
    live = ended(w, repo, "live/bifrost-x", detach="origin/main")
    w.git(repo, "worktree", "lock", "--reason", "lifecycle:20260101T000000Z-1-abcdef", d)
    w.git(repo, "worktree", "lock", "--reason", "lifecycle:20260101T000000Z-2-fedcba", live)
    holder = hold_record_lock(wo.admin_of(str(live))[0])
    try:
        rc, out, rep = w.sweep("--apply")
    finally:
        holder.kill()
        holder.wait()
    assert rc == 0, out
    assert not d.exists()
    notes = [n for r in rep["repos"] for n in r["notes"]]
    assert any("released lifecycle:20260101T000000Z-1-abcdef" in n for n in notes)
    assert live.exists() and reason(rep, live) == "locked"
    assert any(n.startswith("kept lifecycle:20260101T000000Z-2-fedcba") for n in notes)


def test_paths_outside_the_roots_or_through_a_symlink_stay(w):
    repo = w.repo()
    outside = w.ws / ".worktrees" / "old"
    w.git(repo, "worktree", "add", "-q", "--detach", outside, "origin/main")
    w.end(outside, "--work", "W-31", "--by", "coordinator")
    inside = ended(w, repo, "moved/bifrost-x", detach="origin/main")
    os.rename(w.aw / "moved", w.aw / "real")
    os.symlink(w.aw / "real", w.aw / "moved")  # git still names aw/moved/bifrost-x
    w.env["LIFECYCLE_WORKTREE_ROOTS"] = str(w.aw)
    rc, out, rep = w.sweep("--apply")
    assert rc == 0, out
    assert outside.exists() and reason(rep, outside) == "outside-roots"
    assert (w.aw / "real" / "bifrost-x").exists() and reason(rep, inside) == "symlink-in-path"


def test_a_tool_checkout_in_tmpdir_needs_an_end_like_any_worktree(w):
    """R11: push-main's and merge-accepted's checkouts meet the same bar: no record, no
    removal; an end confirmed by hand lets a clean one go; a deletion keeps one regardless."""
    repo = w.repo()
    left = w.tmpdir / "push-main.AbC" / "bifrost-x"
    dirty = w.tmpdir / "push-main.DeF" / "bifrost-x"
    for d in (left, dirty):
        w.git(repo, "worktree", "add", "-q", "--detach", d, "origin/main")
    rc, out, rep = w.sweep("--apply")
    assert left.exists() and reason(rep, left) == "unregistered"
    (dirty / "README").unlink()
    for d in (left, dirty):
        w.end(d, "--work", "TD-341", "--by", "coordinator: push-main was killed")
    rc, out, rep = w.sweep("--apply")
    assert rc == 0, out
    assert not left.exists()
    assert dirty.exists() and reason(rep, dirty) == "changes"


def test_a_clone_under_agent_work_is_swept_but_never_removed(w):
    clone = w.repo("bifrost-finance", where=w.aw, listed=False)
    d = ended(w, clone, "fin-lane/bifrost-finance", branch="w31/fin")
    rc, out, rep = w.sweep("--apply")
    assert rc == 0, out
    assert not d.exists() and (clone / ".git").is_dir() and (clone / "README").exists()
    assert World.items(rep)["w31/fin"]["action"] == "deleted"
    assert w.run_dirs("bifrost-finance")


def test_open_files_or_an_incomplete_lsof_keep_a_worktree(w):
    repo = w.repo()
    d = ended(w, repo, "open/bifrost-x", detach="origin/main")
    w.lsof_out(f"p123\nn{d}/README\n")
    rc, out, rep = w.sweep("--apply")
    assert d.exists() and reason(rep, d) == "in-use"
    w.lsof_out("", rc=1, err="lsof: something failed\n")
    rc, out, rep = w.sweep("--apply")
    assert d.exists() and reason(rep, d) == "lsof-unknown"


def test_the_second_check_takes_a_fresh_lsof(w, monkeypatch):
    repo = w.repo()
    d = ended(w, repo, "late-open/bifrost-x", detach="origin/main")
    monkeypatch.setattr(lifecycle_local, "_between_checks", lambda ctx, items: w.lsof_out(f"p9\nn{os.path.realpath(d)}\n"))
    rc, out, rep = w.sweep("--apply", inproc=True)
    assert rc == 0 and d.exists() and reason(rep, d) == "in-use"


def test_a_renewal_between_the_checks_keeps_it(w, monkeypatch):
    """Review 539 F4: a session that resumes after the first check renews the record under
    its flock; the second check finds the record changed."""
    repo = w.repo()
    d = ended(w, repo, "resumed/bifrost-x", detach="origin/main")
    monkeypatch.setattr(lifecycle_local, "_between_checks", lambda ctx, items: w.renew(d))
    rc, out, rep = w.sweep("--apply", inproc=True)
    assert rc == 0 and d.exists() and reason(rep, d) == "record-changed"


def test_a_record_held_by_another_process_keeps_it(w):
    repo = w.repo()
    d = ended(w, repo, "busy/bifrost-x", detach="origin/main")
    holder = hold_record_lock(wo.admin_of(str(d))[0])
    try:
        rc, out, rep = w.sweep("--apply")
    finally:
        holder.kill()
        holder.wait()
    assert rc == 0 and d.exists() and reason(rep, d) == "record-busy"


def test_a_ref_the_remote_drops_mid_run_is_still_in_the_run_s_bundle(w, monkeypatch):
    """The remote is read again before the archive; a ref it drops after that read is not
    seen. Nothing is lost: the tips beyond main go into redundant.bundle, and that bundle
    never expires while a head is on no remote ref."""
    repo = w.repo()
    d = ended(w, repo, "gone-ref/bifrost-x", detach="origin/main")
    head = w.commit(d, "on the remote only as w31/gone")
    w.git(d, "push", "-q", "origin", "HEAD:refs/heads/w31/gone")
    w.end(d)
    bare = w.remotes / "bifrost-x.git"
    monkeypatch.setattr(lifecycle_local, "_between_checks",
                        lambda ctx, items: w.git(w.tmp, "--git-dir", bare, "update-ref", "-d", "refs/heads/w31/gone"))
    rc, out, rep = w.sweep("--apply", inproc=True)
    assert rc == 0, out
    (run,) = w.run_dirs()
    assert head in w.git(repo, "bundle", "list-heads", run / "redundant.bundle")
    man = json.loads((run / "manifest.json").read_text())
    man["created_at"] = "2026-01-01T00:00:00Z"
    (run / "manifest.json").write_text(json.dumps(man))
    monkeypatch.setattr(lifecycle_local, "_between_checks", lambda ctx, items: None)
    rc, out, rep = w.sweep("--apply", inproc=True)
    assert (run / "redundant.bundle").exists()
    assert [e["reason"] for e in rep["bundles_expiry"] if e["kind"] == "redundant"] == ["a head is no longer on a ref the remote holds"]


def test_a_reflog_commit_whose_remote_branch_goes_mid_run_is_in_the_redundant_bundle(w, monkeypatch):
    """A reflog commit that a remote branch other than main holds is not unique when checked;
    if the remote drops that branch before the removal, the run's redundant bundle has it."""
    repo = w.repo()
    d = ended(w, repo, "side/bifrost-x", detach="origin/main")
    side = w.commit(d, "on the remote only as w31/side")
    w.git(d, "push", "-q", "origin", "HEAD:refs/heads/w31/side")
    w.git(d, "checkout", "-q", "--detach", "origin/main")
    w.end(d)
    bare = w.remotes / "bifrost-x.git"
    monkeypatch.setattr(lifecycle_local, "_between_checks",
                        lambda ctx, items: w.git(w.tmp, "--git-dir", bare, "update-ref", "-d", "refs/heads/w31/side"))
    rc, out, rep = w.sweep("--apply", inproc=True)
    assert rc == 0 and not d.exists(), out
    (run,) = w.run_dirs()
    assert not (run / "unique.bundle").exists()
    fresh = w.tmp / "fresh"
    w.git(w.tmp, "clone", "-q", bare, fresh)
    w.git(fresh, "fetch", "-q", run / "redundant.bundle", "refs/lifecycle-archive/*:refs/restored/*")
    assert w.has_commit(fresh, side)


def test_a_branch_checked_out_elsewhere_after_the_check_stays(w, monkeypatch):
    repo = w.repo()
    d = ended(w, repo, "lane/bifrost-x", branch="w31/lane")
    w.git(d, "checkout", "-q", "--detach")
    other = w.aw / "other" / "bifrost-x"
    monkeypatch.setattr(lifecycle_local, "_between_checks",
                        lambda ctx, items: w.git(repo, "worktree", "add", "-q", other, "w31/lane"))
    rc, out, rep = w.sweep("--apply", inproc=True)
    assert rc == 0, out
    assert not d.exists() and other.exists()
    assert World.items(rep)["w31/lane"]["reason"] == "checked-out"


def test_update_ref_refuses_a_branch_that_moved_after_the_last_check(w, monkeypatch):
    """The last guard: update-ref -d <ref> <old sha> (the recheck is bypassed here)."""
    repo = w.repo()
    d = ended(w, repo, "lane/bifrost-x", branch="w31/lane")
    w.git(d, "checkout", "-q", "--detach")
    newer = w.commit(repo, "main moves on")
    w.git(repo, "push", "-q", "origin", "main")

    def move_then_pass(ctx, it):
        w.git(repo, "update-ref", "refs/heads/w31/lane", newer)
        return None
    monkeypatch.setattr(lifecycle_local, "recheck_branch", move_then_pass)
    rc, out, rep = w.sweep("--apply", inproc=True)
    assert rc == 0, out
    assert w.git(repo, "rev-parse", "refs/heads/w31/lane") == newer
    assert World.items(rep)["w31/lane"]["reason"] == "moved"


def test_an_unreadable_reflog_or_record_keeps_it(w):
    """Review 539 F1: a read that fails is not an empty history."""
    repo = w.repo()
    a = ended(w, repo, "noreflog/bifrost-x", detach="origin/main")
    b = ended(w, repo, "badrecord/bifrost-x", detach="origin/main")
    c = ended(w, repo, "badfield/bifrost-x", detach="origin/main")
    log = Path(wo.admin_of(str(a))[0]) / "logs" / "HEAD"
    log.chmod(0)
    (Path(wo.admin_of(str(b))[0]) / wo.OWNER).write_text("{not json")
    rec_c = Path(wo.admin_of(str(c))[0]) / wo.OWNER
    rec_c.write_text(json.dumps(dict(json.loads(rec_c.read_text()), cache_roots=["../elsewhere"])))
    try:
        rc, out, rep = w.sweep("--apply")
    finally:
        if log.exists():
            log.chmod(0o644)
    assert a.exists() and reason(rep, a) == "reflog-unreadable"
    assert b.exists() and reason(rep, b) == "record-unusable"
    assert c.exists() and reason(rep, c) == "record-unusable"


def test_a_worktree_list_or_remote_that_cannot_be_read_keeps_the_repository(w):
    repo = w.repo()
    d = ended(w, repo, "lane/bifrost-x", detach="origin/main")
    w.env["FAKE_GIT_FAIL"] = "list"
    rc, out, rep = w.sweep("--apply")
    del w.env["FAKE_GIT_FAIL"]
    assert d.exists() and "git worktree list" in rep["repos"][0]["problem"]
    w.git(repo, "remote", "set-url", "origin", w.tmp / "no-such-remote.git")
    rc, out, rep = w.sweep("--apply")
    assert d.exists() and "ls-remote" in rep["repos"][0]["problem"]


def test_stale_remote_tracking_and_agent_refs_are_no_copy(w):
    """A branch deleted on the remote stays in refs/remotes until a fetch --prune; agentd
    deletes agent/** without keeping objects (before S5). Neither counts as a copy. --offline
    trusts the stale ref, which is why it never applies."""
    repo = w.repo()
    stale = ended(w, repo, "stale/bifrost-x", detach="origin/main")
    w.commit(stale, "pushed, fetched, then deleted on the remote")
    w.git(stale, "push", "-q", "origin", "HEAD:refs/heads/w31/deleted")
    w.git(repo, "fetch", "-q", "origin")
    w.git(w.tmp, "--git-dir", w.remotes / "bifrost-x.git", "update-ref", "-d", "refs/heads/w31/deleted")
    agent = ended(w, repo, "agent/bifrost-x", detach="origin/main")
    w.commit(agent, "an attempt's result")
    w.git(agent, "push", "-q", "origin", "HEAD:refs/heads/agent/t_1/a1")
    w.end(stale)
    w.end(agent)
    rc, out, rep = w.sweep("--apply")
    assert rc == 0, out
    assert stale.exists() and reason(rep, stale) == "head-without-copy"
    assert agent.exists() and reason(rep, agent) == "head-without-copy"
    rc, out, rep = w.sweep("--offline")
    assert World.items(rep)[str(stale)]["action"] == "would-remove" and stale.exists()


def test_branches_need_end_evidence(w):
    """Review 539 F3: a branch goes only as the branch new-worktree.sh made for an ended
    worktree this run removes; a branch it merely checked out, or one no record names, stays."""
    repo = w.repo()
    w.git(repo, "branch", "w31/someone-elses", "main")
    w.git(repo, "branch", "w31/never-checked-out", "main")
    d = ended(w, repo, "borrow/bifrost-x", branch="w31/someone-elses")
    rc, out, rep = w.sweep("--apply")
    assert rc == 0, out
    items = World.items(rep)
    assert not d.exists()
    assert items["w31/someone-elses"]["reason"] == "no-end-evidence"
    assert items["w31/never-checked-out"]["reason"] == "no-end-evidence"
    assert "w31/someone-elses" in w.git(repo, "branch", "--list")


def test_cache_roots_the_record_names_may_go_with_it_nothing_else_ignored(w):
    repo = w.repo()
    ok = w.new_worktree(repo, "fe/bifrost-x", detach="origin/main", extra=("--cache-root", "node_modules"))
    (ok / "node_modules" / "pkg").mkdir(parents=True)
    (ok / "node_modules" / "pkg" / "index.js").write_text("x\n")
    undeclared = w.new_worktree(repo, "fe2/bifrost-x", detach="origin/main")
    (undeclared / "build").mkdir()
    (undeclared / "build" / "notes.md").write_text("hand-written, ignored\n")
    nested = w.new_worktree(repo, "fe3/bifrost-x", detach="origin/main", extra=("--cache-root", "node_modules"))
    (nested / "node_modules" / "dep").mkdir(parents=True)
    w.git(nested / "node_modules" / "dep", "init", "-q")
    w.commit(nested / "node_modules" / "dep", "a repository someone cloned into the cache")
    for d in (ok, undeclared, nested):
        w.end(d)
    rc, out, rep = w.sweep("--apply")
    assert rc == 0, out
    assert not ok.exists()
    assert undeclared.exists() and reason(rep, undeclared) == "ignored"
    assert nested.exists() and reason(rep, nested) == "cache-root-unsafe"


def test_index_flags_that_hide_changes_keep_it(w):
    repo = w.repo()
    d = ended(w, repo, "hidden/bifrost-x", detach="origin/main")
    w.git(d, "update-index", "--assume-unchanged", "README")
    (d / "README").write_text("edited, and status does not say so\n")
    assert w.git(d, "status", "--porcelain") == ""
    rc, out, rep = w.sweep("--apply")
    assert d.exists() and reason(rep, d) == "hidden-changes"


def test_untracked_operations_and_per_worktree_refs_keep_it(w):
    repo = w.repo()
    a = ended(w, repo, "untracked/bifrost-x", detach="origin/main")
    (a / "draft.go").write_text("package x\n")
    b = ended(w, repo, "merging/bifrost-x", detach="origin/main")
    (Path(wo.admin_of(str(b))[0]) / "MERGE_HEAD").write_text(w.git(repo, "rev-parse", "HEAD") + "\n")
    c = ended(w, repo, "wtref/bifrost-x", detach="origin/main")
    w.git(c, "update-ref", "refs/worktree/keep", "HEAD")
    rc, out, rep = w.sweep("--apply")
    assert (reason(rep, a), reason(rep, b), reason(rep, c)) == ("untracked", "operation-in-progress", "per-worktree-refs")
    assert a.exists() and b.exists() and c.exists()


def test_a_worktree_whose_dir_is_gone_keeps_its_admin_dir(w):
    """git worktree prune would drop the admin dir and the HEAD reflog with it: never run."""
    repo = w.repo()
    d = ended(w, repo, "vanished/bifrost-x", detach="origin/main")
    w.commit(d, "only in this HEAD reflog")
    w.git(d, "checkout", "-q", "--detach", "origin/main")
    admin = Path(wo.admin_of(str(d))[0])
    subprocess.run(["rm", "-rf", str(d)], check=True)
    rc, out, rep = w.sweep("--apply")
    assert rc == 0 and admin.is_dir() and reason(rep, d) == "missing"


def test_report_only_writes_nothing_in_the_repositories(w):
    repo = w.repo()
    d = ended(w, repo, "lane/bifrost-x", branch="w31/lane")
    before = w.git(repo, "for-each-ref")
    rc, out, rep = w.sweep()
    assert rc == 0 and d.exists() and w.git(repo, "for-each-ref") == before
    assert World.items(rep)[str(d)]["action"] == "would-remove" and not w.backup.exists()
    assert stat.S_IMODE(os.stat(w.status / "lifecycle-local.json").st_mode) == 0o600
    assert "locked" not in w.git(repo, "worktree", "list", "--porcelain")


def test_a_held_machine_lock_stops_the_run(w):
    repo = w.repo()
    d = ended(w, repo, "lane/bifrost-x", detach="origin/main")
    (w.tmp / "lock").mkdir()
    fd = os.open(str(w.tmp / "lock" / "lock"), os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        rc, out, rep = w.sweep("--apply")
    finally:
        os.close(fd)
    assert rc == 3 and d.exists()


def test_root_problem_accepts_only_plain_directories_below_a_root(tmp_path):
    root = tmp_path / "root"
    (root / "a" / "b").mkdir(parents=True)
    roots = [(str(root), os.path.realpath(root))]
    assert lifecycle_items.root_problem(str(root / "a" / "b"), roots) is None
    assert lifecycle_items.root_problem(str(root), roots)[0] == "outside-roots"
    assert lifecycle_items.root_problem(str(tmp_path / "elsewhere"), roots)[0] == "outside-roots"
    os.symlink(root / "a", root / "link")
    assert lifecycle_items.root_problem(str(root / "link" / "b"), roots)[0] == "symlink-in-path"
