"""prune-merged-branches.sh against throwaway repositories: the remote mode (rejected batches,
reviewed branches, agent/**), and --local-only, the acceptance cases of W-31 4.6 S2 and S3
(CUT-lifecycle-2026-10-24.md §5): each fails on the script before S2, which had no --local-only
and whose --local judged by Change-Id and removed worktrees with --force. More --local-only
cases are in scripts/agent-host/test_lifecycle_local.py; the fixture is lifecycle_testlib.py.

    python3 -m pytest -q scripts/test_prune_merged_branches.py
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

SCRIPT = Path(__file__).with_name("prune-merged-branches.sh").resolve()
sys.path.insert(0, str(SCRIPT.parent / "agent-host"))
import lifecycle_local  # noqa: E402
from lifecycle_testlib import World  # noqa: E402

W = World


@pytest.mark.parametrize("refuse", [True, False], ids=["rejected-batch", "all-deleted"])
def test_remote_pruning(tmp_path, refuse):
    env = os.environ.copy()
    env.update(
        WORKSPACE=str(tmp_path),
        BACKUP_ROOT=str(tmp_path),
        HOME=str(tmp_path),
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_AUTHOR_NAME="Pruning Test",
        GIT_AUTHOR_EMAIL="pruning@example.invalid",
        GIT_COMMITTER_NAME="Pruning Test",
        GIT_COMMITTER_EMAIL="pruning@example.invalid",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text("#!/bin/sh\nexit 0\n")
    gh.chmod(0o755)
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]

    def git(*args):
        return subprocess.run(
            ["git", *map(str, args)], env=env, check=True,
            capture_output=True, text=True,
        ).stdout

    bare = tmp_path / "remote.git"
    clone = tmp_path / "clone"
    git("init", "--bare", "--initial-branch=main", bare)
    git("clone", bare, clone)
    git("-C", clone, "commit", "--allow-empty", "-m", "Initial main")
    git("-C", clone, "push", "origin", "main")
    branches = ["protected"] + [f"merged-{i:02d}" for i in range(59)]
    git("-C", clone, "push", "origin", *[f"main:refs/heads/{b}" for b in branches])
    if refuse:
        hook = bare / "hooks" / "pre-receive"
        hook.write_text(
            "#!/bin/sh\n"
            "while read -r old new ref; do\n"
            '  if [ "$ref" = refs/heads/protected ]; then exit 1; fi\n'
            "done\n"
        )
        hook.chmod(0o755)

    result = subprocess.run(
        ["bash", str(SCRIPT), "--apply", "--repos", "clone", "--min-age-hours", "0"],
        env=env, capture_output=True, text=True,
    )
    remaining = set(git("--git-dir", bare, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines())
    assert remaining == ({"main", "protected"} if refuse else {"main"})
    assert result.returncode == (1 if refuse else 0), result.stderr
    summary = next(line for line in result.stdout.splitlines() if line.startswith("remote  "))
    assert summary == (
        "remote  clone: deleted 59, refused 1 (protected)"
        if refuse else "remote  clone: deleted 60"
    )


def test_reviewed_branches(tmp_path):
    """--reviewed deletes a listed branch not on main while it names the reviewed sha, and keeps the rest."""
    env = os.environ.copy()
    env.update(
        WORKSPACE=str(tmp_path), BACKUP_ROOT=str(tmp_path), HOME=str(tmp_path), GIT_CONFIG_GLOBAL="/dev/null",
        GIT_AUTHOR_NAME="Pruning Test", GIT_AUTHOR_EMAIL="pruning@example.invalid",
        GIT_COMMITTER_NAME="Pruning Test", GIT_COMMITTER_EMAIL="pruning@example.invalid",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text("#!/bin/sh\nexit 0\n")
    gh.chmod(0o755)
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]

    def git(*args):
        return subprocess.run(["git", *map(str, args)], env=env, check=True, capture_output=True, text=True).stdout.strip()

    bare = tmp_path / "remote.git"
    clone = tmp_path / "clone"
    git("init", "--bare", "--initial-branch=main", bare)
    git("clone", bare, clone)
    git("-C", clone, "commit", "--allow-empty", "-m", "Initial main")
    git("-C", clone, "push", "origin", "main")
    shas = {}
    for b in ("kept", "reviewed", "moved"):
        git("-C", clone, "checkout", "-q", "-b", b, "main")
        git("-C", clone, "commit", "--allow-empty", "-m", f"work on {b}")
        shas[b] = git("-C", clone, "rev-parse", "HEAD")
        git("-C", clone, "push", "-q", "origin", b)
    old_moved = shas["moved"]
    git("-C", clone, "checkout", "-q", "moved")
    git("-C", clone, "commit", "--allow-empty", "-m", "more work on moved")
    git("-C", clone, "push", "-q", "origin", "moved")
    listing = tmp_path / "reviewed.txt"
    listing.write_text(f"# reviewed 10-20\nclone reviewed {shas['reviewed']}\nclone moved {old_moved}\n\n")

    result = subprocess.run(
        ["bash", str(SCRIPT), "--apply", "--repos", "clone", "--min-age-hours", "0", "--reviewed", str(listing)],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    remaining = set(git("--git-dir", bare, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines())
    assert remaining == {"main", "kept", "moved"}
    assert "moved since it was reviewed" in result.stdout
    assert "remote  clone: deleted 1" in result.stdout

    listing.write_text("clone main " + shas["kept"] + "\n")
    bad = subprocess.run(
        ["bash", str(SCRIPT), "--repos", "clone", "--reviewed", str(listing)], env=env, capture_output=True, text=True,
    )
    assert bad.returncode == 2 and "bad line 1" in bad.stderr


def test_agent_branches_are_left_to_agentd(tmp_path):
    """agent/** on origin (Gitea) is agentd's to delete (TD-383): kept merged, reviewed or not; the rest as before."""
    env = os.environ.copy()
    env.update(
        WORKSPACE=str(tmp_path), BACKUP_ROOT=str(tmp_path), HOME=str(tmp_path), GIT_CONFIG_GLOBAL="/dev/null",
        GIT_AUTHOR_NAME="Pruning Test", GIT_AUTHOR_EMAIL="pruning@example.invalid",
        GIT_COMMITTER_NAME="Pruning Test", GIT_COMMITTER_EMAIL="pruning@example.invalid",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text("#!/bin/sh\nexit 0\n")
    gh.chmod(0o755)
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]

    def git(*args):
        return subprocess.run(["git", *map(str, args)], env=env, check=True, capture_output=True, text=True).stdout.strip()

    bare = tmp_path / "remote.git"
    clone = tmp_path / "clone"
    git("init", "--bare", "--initial-branch=main", bare)
    git("clone", bare, clone)
    git("-C", clone, "commit", "--allow-empty", "-m", "Initial main")
    git("-C", clone, "push", "origin", "main")
    git("-C", clone, "push", "-q", "origin", "main:refs/heads/agent/t_1/a1", "main:refs/heads/w31/merged")
    git("-C", clone, "checkout", "-q", "-b", "attempt", "main")
    git("-C", clone, "commit", "--allow-empty", "-m", "an attempt's result")
    unmerged = git("-C", clone, "rev-parse", "HEAD")
    git("-C", clone, "push", "-q", "origin", "attempt:refs/heads/agent/t_2/a1")
    listing = tmp_path / "reviewed.txt"
    listing.write_text(f"clone agent/t_2/a1 {unmerged}\n")

    result = subprocess.run(
        ["bash", str(SCRIPT), "--apply", "--repos", "clone", "--min-age-hours", "0", "--reviewed", str(listing)],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    remaining = set(git("--git-dir", bare, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines())
    assert remaining == {"main", "agent/t_1/a1", "agent/t_2/a1"}
    kept = [line.split() for line in result.stdout.splitlines() if line.startswith("  keep ")]
    assert sorted(k[2] for k in kept if "agentd's" in " ".join(k)) == ["agent/t_1/a1", "agent/t_2/a1"]
    assert "remote  clone: deleted 1" in result.stdout


# --local-only (S2, S3) ------------------------------------------------------------------------

@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def test_reflog_only_commit_is_archived_first_and_restores_from_the_bundle(world):
    """HEAD on main, an older commit only in this worktree's HEAD reflog (review 534 A2): it
    goes into the run's unique bundle before the worktree goes, and a fresh clone of the remote
    gets it back from that bundle."""
    w = world
    repo = w.repo()
    wt = w.new_worktree(repo, "lane/bifrost-x", detach="origin/main")
    lost = w.commit(wt, "work that only the reflog remembers")
    w.git(wt, "checkout", "-q", "--detach", "origin/main")
    w.end(wt)
    rc, out, rep = w.sweep("--apply")
    assert rc == 0, out
    assert not wt.exists() and W.items(rep)[str(wt)]["action"] == "removed"
    (run,) = w.run_dirs()
    man = json.loads((run / "manifest.json").read_text())
    unique = next(b for b in man["bundles"] if b["kind"] == "unique")
    assert unique["file"] == "unique.bundle" and lost in unique["heads"].values()
    fresh = w.tmp / "fresh"
    w.git(w.tmp, "clone", "-q", w.remotes / "bifrost-x.git", fresh)
    assert not w.has_commit(fresh, lost)
    w.git(fresh, "fetch", "-q", run / "unique.bundle", "refs/lifecycle-archive/*:refs/restored/*")
    assert w.has_commit(fresh, lost)
    assert "refs/lifecycle-archive" not in w.git(repo, "for-each-ref")  # the temporary names are gone


def test_detached_head_on_no_ref_stays_although_its_change_id_is_on_main(world):
    """A detached HEAD that no remote ref reaches stays, although main has a commit with the
    same Change-Id (the split version, review 534 A1): only objects count. The same for a
    branch made for the work, which the old --local deleted with -D on a Change-Id match."""
    w = world
    repo = w.repo()
    wt = w.new_worktree(repo, "merge-accepted/t_1/bifrost-x", detach="origin/main")
    br = w.new_worktree(repo, "lane/bifrost-x", branch="w31/split")
    cid, cid2 = "I" + "1" * 40, "I" + "2" * 40
    w.commit(wt, "the original", change_id=cid, fname="a.txt")
    original = w.commit(br, "the original on a branch", change_id=cid2, fname="c.txt")
    w.commit(repo, "the split version", change_id=cid, fname="b.txt")
    w.commit(repo, "the split version of the branch's", change_id=cid2, fname="d.txt")
    w.git(repo, "push", "-q", "origin", "main")
    w.end(wt)
    w.end(br)
    rc, out, rep = w.sweep("--apply")
    assert rc == 0, out
    items = W.items(rep)
    assert wt.exists() and items[str(wt)]["reason"] == "head-without-copy"
    assert br.exists() and items[str(br)]["reason"] == "head-without-copy"
    assert items["w31/split"]["reason"] == "checked-out"
    assert w.git(repo, "rev-parse", "refs/heads/w31/split") == original
    assert w.run_dirs() == []


def test_an_uncommitted_deletion_keeps_the_worktree(world):
    w = world
    repo = w.repo()
    wt = w.new_worktree(repo, "push-main.X/bifrost-x", detach="origin/main")
    (wt / "README").unlink()
    w.end(wt)
    rc, out, rep = w.sweep("--apply")
    assert rc == 0 and wt.exists()
    item = W.items(rep)[str(wt)]
    assert item["reason"] == "changes" and "README" in item["detail"]


def test_a_commit_after_the_check_keeps_the_worktree_and_its_branch(world, monkeypatch):
    """Another session commits between the first check and the removal: the second check
    sees HEAD move, so neither the worktree nor the branch made for it goes."""
    w = world
    repo = w.repo()
    wt = w.new_worktree(repo, "lane/bifrost-x", branch="w31/lane")
    w.end(wt)
    seen = []

    def commit_now(ctx, items):
        seen.append(sorted(i.name for i in items))
        w.commit(wt, "a late commit")
    monkeypatch.setattr(lifecycle_local, "_between_checks", commit_now)
    rc, out, rep = w.sweep("--apply", inproc=True)
    assert rc == 0, out
    assert seen == [sorted([str(wt), "w31/lane"])]  # both were candidates after the first check
    assert wt.exists() and w.git(repo, "rev-parse", "refs/heads/w31/lane") == w.git(wt, "rev-parse", "HEAD")
    items = W.items(rep)
    assert items[str(wt)]["reason"] == "head-changed"
    assert items["w31/lane"]["reason"] == "worktree-kept"


def test_local_only_never_pushes_fetches_or_calls_gh(world):
    """--local-only reads the remote with ls-remote and nothing else: the remote's refs, the
    clone's remote-tracking refs and the remote's receive hook all show no write."""
    w = world
    repo = w.repo()
    wt = w.new_worktree(repo, "lane/bifrost-x", branch="w31/pushed")
    w.commit(wt, "pushed work")
    w.git(wt, "push", "-q", "origin", "w31/pushed")
    w.end(wt)
    hook = w.remotes / "bifrost-x.git" / "hooks" / "pre-receive"
    marker = w.tmp / "received"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n")
    hook.chmod(0o755)
    before_remote = w.remote_refs()
    before_tracking = w.git(repo, "for-each-ref", "refs/remotes/")
    w.env["GIT_CALLS"] = str(w.git_calls)
    rc, out, rep = w.sweep("--apply")
    del w.env["GIT_CALLS"]
    assert rc == 0, out
    assert not wt.exists()  # it did act locally
    calls = w.git_calls.read_text().splitlines()
    assert not [c for c in calls if c.split()[2:3] in (["push"], ["fetch"], ["pull"], ["remote"]) or c.startswith("gh ")]
    assert any(c.split()[2:3] == ["ls-remote"] for c in calls)
    assert w.remote_refs() == before_remote and not marker.exists()
    assert w.git(repo, "for-each-ref", "refs/remotes/") == before_tracking


def test_two_runs_on_one_day_keep_both_bundles(world):
    """Each run writes its own run directory (mkdir, never reused), so a second run the same
    day with another deletion set leaves the first run's bundle where it was (review 534 A7)."""
    w = world
    repo = w.repo()
    shas = []
    for n in ("a", "b"):
        wt = w.new_worktree(repo, f"lane-{n}/bifrost-x", detach="origin/main")
        shas.append(w.commit(wt, f"reflog-only work {n}"))
        w.git(wt, "checkout", "-q", "--detach", "origin/main")
        w.end(wt)
        rc, out, _ = w.sweep("--apply")
        assert rc == 0, out
    runs = w.run_dirs()
    assert len(runs) == 2 and runs[0].name[:8] == runs[1].name[:8]  # same day
    for run, sha in zip(runs, shas):
        heads = w.git(repo, "bundle", "list-heads", run / "unique.bundle")
        assert sha in heads


def _aged_run(w, repo, name, kind, head, days):
    """A run directory as S2 writes it, created_at days ago, holding one bundle of head."""
    run = w.backup / "testhost" / "bifrost-x" / name
    run.mkdir(parents=True)
    ref = f"refs/lifecycle-archive/{name}/x0"
    w.git(repo, "update-ref", ref, head)
    w.git(repo, "bundle", "create", "-q", run / f"{kind}.bundle", ref)
    w.git(repo, "update-ref", "-d", ref)
    digest = hashlib.sha256((run / f"{kind}.bundle").read_bytes()).hexdigest()
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - days * 86400))
    (run / "manifest.json").write_text(json.dumps({"schema": 1, "created_at": created, "bundles": [
        {"kind": kind, "file": f"{kind}.bundle", "heads": {ref: head}, "sha256": digest}]}))
    return run / f"{kind}.bundle"


def test_a_bundle_with_unique_objects_outlives_90_days(world):
    """R12: a redundant bundle older than 90 days goes when the remote still holds every head;
    one with unique objects stays however old; so do a redundant one whose head the remote no
    longer holds, a young one, and the pre-S2 date-named bundles (no manifest)."""
    w = world
    repo = w.repo()
    on_main = w.git(repo, "rev-parse", "HEAD")
    w.git(repo, "checkout", "-q", "-b", "side")
    orphan = w.commit(repo, "on no remote ref")
    w.git(repo, "checkout", "-q", "main")
    unique = _aged_run(w, repo, "20260701T000000Z-1-aaaaaa", "unique", orphan, 120)
    gone = _aged_run(w, repo, "20260702T000000Z-1-bbbbbb", "redundant", orphan, 120)
    old = _aged_run(w, repo, "20260703T000000Z-1-cccccc", "redundant", on_main, 120)
    young = _aged_run(w, repo, "20261001T000000Z-1-dddddd", "redundant", on_main, 20)
    legacy = w.backup / "2026-07-01" / "bifrost-x.bundle"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(unique.read_bytes())
    rc, out, rep = w.sweep("--apply")
    assert rc == 0, out
    assert unique.exists() and gone.exists() and young.exists() and legacy.exists()
    assert not old.exists()
    reasons = {Path(e["dir"]).name: (e["action"], e["reason"]) for e in rep["bundles_expiry"]}
    assert reasons["20260701T000000Z-1-aaaaaa"][0] == "keep" and "never expired" in reasons["20260701T000000Z-1-aaaaaa"][1]
    assert reasons["20260702T000000Z-1-bbbbbb"] == ("keep", "a head is no longer on a ref the remote holds")
    assert reasons["20260703T000000Z-1-cccccc"][0] == "removed"
    man = json.loads((old.parent / "manifest.json").read_text())
    assert man["bundles"][0]["expired_at"]


def test_a_worktree_without_ended_at_is_never_removed(world):
    """S3 acceptance with S2: in use (no ended_at), unregistered (made by plain git worktree
    add), and ended then renewed (a resumed session voids the end) all stay; the ended one goes."""
    w = world
    repo = w.repo()
    in_use = w.new_worktree(repo, "in-use/bifrost-x", detach="origin/main")
    plain = w.aw / "plain/bifrost-x"
    w.git(repo, "worktree", "add", "-q", "--detach", plain, "origin/main")
    renewed = w.new_worktree(repo, "renewed/bifrost-x", detach="origin/main")
    w.end(renewed)
    w.renew(renewed)
    ended = w.new_worktree(repo, "ended/bifrost-x", detach="origin/main")
    w.end(ended)
    rc, out, rep = w.sweep("--apply")
    assert rc == 0, out
    items = W.items(rep)
    assert (items[str(in_use)]["reason"], items[str(plain)]["reason"], items[str(renewed)]["reason"]) == (
        "not-ended", "unregistered", "not-ended")
    assert in_use.exists() and plain.exists() and renewed.exists() and not ended.exists()


def test_the_old_local_mode_is_gone_and_local_only_takes_no_remote_option(world):
    w = world
    w.repo()
    for args in (["--apply", "--local"], ["--local-only", "--reviewed", "x"], ["--local-only", "--local"],
                 ["--local-only", "--apply", "--offline"], ["--offline"]):
        r = subprocess.run(["bash", str(SCRIPT), *args], env=w.env, capture_output=True, text=True)
        assert r.returncode == 2, (args, r.stdout, r.stderr)
