"""prune-merged-branches.sh --local-only after review 551: pseudo refs (A2), the archive's
place (A3), the quarantine and the last moment (A4), bundles that restore alone (C1), the
repository identity (E). Each test builds a throwaway world (lifecycle_testlib.py).

    python3 -m pytest -q scripts/agent-host/test_lifecycle_final.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lifecycle_local  # noqa: E402
import lifecycle_quarantine as lq  # noqa: E402
import worktree_owner as wo  # noqa: E402
from lifecycle_git import repo_id  # noqa: E402
from lifecycle_testlib import World  # noqa: E402


@pytest.fixture(name="w")
def final_world(tmp_path):
    return World(tmp_path)


def ended(w, repo, rel, **kw):
    d = w.new_worktree(repo, rel, **kw)
    w.end(d)
    return d


def reason(rep, path):
    return World.items(rep)[str(path)]["reason"]


def restores_alone(w, bundle, sha):
    """A fresh empty repository gets sha from the bundle and nothing else."""
    empty = w.tmp / f"empty-{sha[:8]}.git"
    w.git(w.tmp, "init", "-q", "--bare", empty)
    w.git(empty, "fetch", "-q", bundle, "refs/lifecycle-archive/*:refs/restored/*")
    return w.has_commit(empty, sha)


def test_a_commit_only_orig_head_names_is_archived_before_removal(w):
    """A2: reflog gone, a local commit, reset back to main: only ORIG_HEAD names the commit.
    It goes into the unique bundle, which restores it into an empty repository."""
    repo = w.repo()
    d = w.new_worktree(repo, "orig/bifrost-x", detach="origin/main")
    lost = w.commit(d, "only ORIG_HEAD will name this")
    w.git(d, "reset", "-q", "--hard", "origin/main")
    admin = Path(wo.admin_of(str(d))[0])
    assert (admin / "ORIG_HEAD").read_text().strip() == lost
    (admin / "logs" / "HEAD").unlink()
    w.end(d)
    rc, out, rep = w.prune("--apply")
    assert rc == 0 and not d.exists(), out
    (run,) = w.run_dirs()
    assert restores_alone(w, run / "unique.bundle", lost)


def test_unknown_or_unreadable_admin_entries_keep_it(w):
    repo = w.repo()
    odd = ended(w, repo, "odd/bifrost-x", detach="origin/main")
    (Path(wo.admin_of(str(odd))[0]) / "MYSTERY").write_text("x\n")
    sealed = ended(w, repo, "sealed/bifrost-x", detach="origin/main")
    w.commit(sealed, "c")
    w.git(sealed, "reset", "-q", "--hard", "origin/main")
    orig = Path(wo.admin_of(str(sealed))[0]) / "ORIG_HEAD"
    orig.chmod(0)
    fetched = ended(w, repo, "fetched/bifrost-x", detach="origin/main")
    (Path(wo.admin_of(str(fetched))[0]) / "FETCH_HEAD").write_text("not a sha\t\tbranch 'x'\n")
    try:
        rc, out, rep = w.prune("--apply")
    finally:
        if orig.exists():
            orig.chmod(0o644)
    assert odd.exists() and reason(rep, odd) == "admin-entry-unknown"
    assert sealed.exists() and reason(rep, sealed) == "pseudo-ref-unreadable"
    assert fetched.exists() and reason(rep, fetched) == "pseudo-ref-unreadable"


def test_a_backup_root_inside_what_may_be_removed_refuses_the_run(w):
    """A3: an archive inside a candidate's cache root (or a disk-guard cache root) would go
    with it: the run is refused before anything is archived."""
    repo = w.repo()
    d = ended(w, repo, "fe/bifrost-x", detach="origin/main", extra=("--cache-root", "node_modules"))
    (d / "node_modules").mkdir()
    for backup in (d / "node_modules" / "lifecycle-backups", w.aw / ".cache" / "go-build" / "archive"):
        w.env["BACKUP_ROOT"] = str(backup)
        rc, out, rep = w.prune("--apply")
        assert rc == 4 and "cannot hold the archive" in out, out
        assert d.exists() and not backup.exists()


def test_a_commit_after_the_second_check_keeps_it_before_and_in_quarantine(w, monkeypatch):
    """A4: a detached commit landing just before the move, or in the quarantined tree, is
    seen by the checks in quarantine: the worktree goes back to its path, commit and all."""
    repo = w.repo()
    for seam in ("_before_quarantine", "_in_quarantine"):
        d = ended(w, repo, f"late-{seam}/bifrost-x", detach="origin/main")
        late = {}

        def commit_now(ctx, it, q=None, d=d):
            late["sha"] = w.commit(Path(q) if q else d, "a commit at the last moment")
        monkeypatch.setattr(lifecycle_local, seam, commit_now)
        rc, out, rep = w.prune("--apply", inproc=True)
        monkeypatch.setattr(lifecycle_local, seam, lambda *a: None)
        assert rc == 0, out
        assert d.exists() and w.git(d, "rev-parse", "HEAD") == late["sha"], seam
        assert reason(rep, d) == "head-changed"
        assert not [p for p in d.parent.iterdir() if lq.QUARANTINE in p.name]
        assert "locked" not in w.git(repo, "worktree", "list", "--porcelain")


def test_a_branch_checked_out_at_the_last_moment_stays(w, monkeypatch):
    repo = w.repo()
    d = ended(w, repo, "lane/bifrost-x", branch="w31/lane")
    w.git(d, "checkout", "-q", "--detach")
    other = w.aw / "other" / "bifrost-x"
    monkeypatch.setattr(lifecycle_local, "_before_branch_delete",
                        lambda ctx, it: w.git(repo, "worktree", "add", "-q", other, "w31/lane"))
    rc, out, rep = w.prune("--apply", inproc=True)
    assert rc == 0, out
    assert not d.exists() and other.exists()
    assert World.items(rep)["w31/lane"]["reason"] == "checked-out"


def test_an_interrupted_quarantine_is_moved_back_never_finished(w, monkeypatch):
    repo = w.repo()
    d = ended(w, repo, "cut/bifrost-x", detach="origin/main")

    def stop_in_quarantine(ctx, it, q):
        raise SystemExit(9)  # the run dies with the worktree in quarantine
    monkeypatch.setattr(lifecycle_local, "_in_quarantine", stop_in_quarantine)
    with pytest.raises(SystemExit):
        w.prune("--apply", inproc=True)
    left = [p for p in d.parent.iterdir() if lq.QUARANTINE in p.name]
    assert not d.exists() and len(left) == 1
    monkeypatch.setattr(lifecycle_local, "_in_quarantine", lambda *a: None)
    rc, out, rep = w.prune()
    assert any("--apply moves it back" in n for n in rep["notes"]) and not d.exists()
    rc, out, rep = w.prune("--apply", inproc=True)
    assert any("moved back" in n for n in rep["notes"])
    # back at its path, then judged like any other: ended and clean, so removed by this run
    assert World.items(rep)[str(d)]["action"] == "removed" and not left[0].exists()
    assert not list((w.status / lq.JOURNAL).iterdir())


def test_the_unique_bundle_restores_alone_after_the_tag_it_hung_on_goes(w):
    """C1 (review 551): a reflog-only commit whose parent only a remote tag reaches. The
    unique bundle carries its whole history, so it restores after the tag is deleted."""
    repo = w.repo()
    w.git(repo, "checkout", "-q", "-b", "side")
    parent = w.commit(repo, "only tag v1 reaches this")
    w.git(repo, "tag", "v1")
    w.git(repo, "push", "-q", "origin", "v1")
    w.git(repo, "checkout", "-q", "main")
    w.git(repo, "branch", "-q", "-D", "side")
    d = w.new_worktree(repo, "tagged/bifrost-x", detach=parent)
    lost = w.commit(d, "on top of the tagged commit")
    w.git(d, "checkout", "-q", "--detach", "origin/main")
    w.end(d)
    rc, out, rep = w.prune("--apply")
    assert rc == 0 and not d.exists(), out
    (run,) = w.run_dirs()
    man = json.loads((run / "manifest.json").read_text())
    unique = next(b for b in man["bundles"] if b["kind"] == "unique")
    assert unique["prerequisites"] == []
    w.git(w.tmp, "--git-dir", w.remotes / "bifrost-x.git", "tag", "-d", "v1")
    assert restores_alone(w, run / "unique.bundle", lost) and restores_alone(w, run / "unique.bundle", parent)


def test_two_clones_with_one_name_keep_separate_archives(w):
    """E: the backup namespace is <name>-<hash of the common git dir>."""
    a = w.repo("bifrost-finance", where=w.aw, listed=False)
    other = w.tmp / "elsewhere"
    other.mkdir()
    w.git(w.tmp, "clone", "-q", w.remotes / "bifrost-finance.git", other / "bifrost-finance")
    assert repo_id(str(a)) != repo_id(str(other / "bifrost-finance"))
    assert repo_id(str(a)).startswith("bifrost-finance-")
    d = ended(w, a, "fin/bifrost-finance", detach="origin/main")
    w.commit(d, "reflog only")
    w.git(d, "checkout", "-q", "--detach", "origin/main")
    w.end(d)
    rc, out, rep = w.prune("--apply")
    assert rc == 0, out
    assert [p.parent.name for p in w.run_dirs("bifrost-finance")] == [repo_id(str(a))]
    assert World.items(rep)[str(d)]["repo_id"] == repo_id(str(a))


def test_a_thin_bundle_records_the_prerequisites_its_header_lists(w):
    """C1: the manifest's prerequisites are the bundle's own (git's boundary), not the list of
    commits it was thinned against."""
    import lifecycle_bundles as lb
    repo = w.repo()
    base = w.git(repo, "rev-parse", "HEAD")
    w.git(repo, "checkout", "-q", "-b", "side")
    w.commit(repo, "b")
    tip = w.commit(repo, "c")
    w.git(repo, "checkout", "-q", "--orphan", "other")
    unrelated = w.commit(repo, "unrelated history", fname="u.txt")
    w.git(repo, "checkout", "-q", "-f", "main")
    run = w.tmp / "run"
    run.mkdir()
    entry = lb.make_bundle(dict(w.env), str(repo), str(run), "r1", "redundant", [tip], [base, unrelated])
    assert entry["prerequisites"] == [base]
    assert entry["thin_against"] == sorted([base, unrelated])
    assert lb.header(str(run / "redundant.bundle"))[1] == [base]


def test_a_lingering_auto_merge_tree_is_archived_as_a_commit(w):
    """A2: Git 2.42+ leaves AUTO_MERGE (a tree: the conflicted state) after an operation ends.
    --apply wraps the tree in a commit, archives it in the unique bundle, then removes; with
    MERGE_HEAD beside it the operation is under way and the worktree stays; an AUTO_MERGE that
    names no tree keeps it."""
    repo = w.repo()
    d = ended(w, repo, "am/bifrost-x", detach="origin/main")
    blob = subprocess.run(["git", "-C", str(d), "hash-object", "-w", "--stdin"], input="conflicted only\n",
                          env=w.env, capture_output=True, text=True, check=True).stdout.strip()
    tree = subprocess.run(["git", "-C", str(d), "mktree"], input=f"100644 blob {blob}\tonly-here.txt\n",
                          env=w.env, capture_output=True, text=True, check=True).stdout.strip()
    (Path(wo.admin_of(str(d))[0]) / "AUTO_MERGE").write_text(tree + "\n")
    busy = ended(w, repo, "am-busy/bifrost-x", detach="origin/main")
    (Path(wo.admin_of(str(busy))[0]) / "AUTO_MERGE").write_text(tree + "\n")
    (Path(wo.admin_of(str(busy))[0]) / "MERGE_HEAD").write_text(w.git(repo, "rev-parse", "HEAD") + "\n")
    bad = ended(w, repo, "am-bad/bifrost-x", detach="origin/main")
    (Path(wo.admin_of(str(bad))[0]) / "AUTO_MERGE").write_text(blob + "\n")
    rc, out, rep = w.prune("--apply")
    assert rc == 0 and not d.exists(), out
    assert busy.exists() and reason(rep, busy) == "operation-in-progress"
    assert bad.exists() and reason(rep, bad) == "pseudo-ref-unreadable"
    (run,) = w.run_dirs()
    empty = w.tmp / "empty-am.git"
    w.git(w.tmp, "init", "-q", "--bare", empty)
    w.git(empty, "fetch", "-q", run / "unique.bundle", "refs/lifecycle-archive/*:refs/restored/*")
    assert w.git(empty, "cat-file", "-p", f"{tree}:only-here.txt") == "conflicted only"


def test_a_fetch_head_past_one_mib_is_read_to_its_last_line(w, monkeypatch):
    """Review 552 A1: the whole pseudo ref is read; the last line of a 1.5 MiB FETCH_HEAD
    names a commit only this worktree knows, and it is archived. Past the limit the
    worktree is kept, never judged by a prefix."""
    import lifecycle_checks
    repo = w.repo()
    d = ended(w, repo, "fetched/bifrost-x", detach="origin/main")
    lost = w.commit(d, "only FETCH_HEAD names this")
    w.git(d, "reset", "-q", "--hard", "origin/main")
    admin = Path(wo.admin_of(str(d))[0])
    (admin / "logs" / "HEAD").unlink()
    (admin / "ORIG_HEAD").unlink()
    main = w.git(repo, "rev-parse", "HEAD")
    filler = "".join(f"{main}\tnot-for-merge\tbranch 'w31/filler-{n:06d}' of gitea\n" for n in range(24000))
    (admin / "FETCH_HEAD").write_text(filler + f"{lost}\t\tbranch 'w31/lost' of gitea\n")
    assert (admin / "FETCH_HEAD").stat().st_size > 3 << 19
    rc, out, rep = w.prune("--apply", inproc=True)
    assert rc == 0 and not d.exists(), out
    (run,) = w.run_dirs()
    assert restores_alone(w, run / "unique.bundle", lost)
    big = ended(w, repo, "toobig/bifrost-x", detach="origin/main")
    (Path(wo.admin_of(str(big))[0]) / "FETCH_HEAD").write_text(filler)
    monkeypatch.setattr(lifecycle_checks, "MAX_PSEUDO", 1 << 20)
    rc, out, rep = w.prune("--apply", inproc=True)
    assert big.exists() and reason(rep, big) == "pseudo-ref-unreadable" and "larger than" in World.items(rep)[str(big)]["detail"]


def test_a_mount_inside_the_worktree_keeps_it_at_any_check(w, monkeypatch):
    """Review 552 A5: a mount point anywhere inside the worktree (same-device bind mounts
    included: only the mount table tells) keeps it, and the table is read again at the
    second check: one that appears after the first check, or a table that can no longer be
    read, keeps it."""
    repo = w.repo()
    sub = ended(w, repo, "sub/bifrost-x", detach="origin/main", extra=("--cache-root", "go-build:build/cache"))
    late = ended(w, repo, "late/bifrost-x", detach="origin/main")
    blind = ended(w, repo, "blind/bifrost-x", detach="origin/main")
    (sub / "build").mkdir()
    table = "/dev/disk1 on / (apfs)\n"
    (w.lsof / "mount.out").write_text(table + f"/dev/disk1 on {os.path.realpath(sub / 'build')} (apfs, bind)\n")

    def mount_now(ctx, items):
        (w.lsof / "mount.out").write_text(table + f"/dev/disk2 on {os.path.realpath(late)}/node_modules (nfs)\n")
    monkeypatch.setattr(lifecycle_local, "_between_checks", mount_now)
    rc, out, rep = w.prune("--apply", inproc=True)
    assert rc == 0, out
    assert sub.exists() and reason(rep, sub) == "mount-inside-worktree"
    assert late.exists() and reason(rep, late) == "mount-inside-worktree"
    assert not blind.exists()  # no mount inside it: it goes
    blind2 = ended(w, repo, "blind2/bifrost-x", detach="origin/main")
    (w.lsof / "mount.out").write_text(table)
    monkeypatch.setattr(lifecycle_local, "_between_checks", lambda ctx, items: (w.lsof / "mount.out").write_text(""))
    rc, out, rep = w.prune("--apply", inproc=True)
    assert blind2.exists() and reason(rep, blind2) == "mount-table-unknown"


def test_records_and_registries_from_before_are_read_safely(w):
    """Review 552 D: a record with the old plain-string cache roots reads as paths with no
    kind; a disk-guard registry that cannot be read in full refuses the run; an AUTO_MERGE
    that names a commit (not a tree) keeps the worktree."""
    repo = w.repo()
    d = ended(w, repo, "old/bifrost-x", detach="origin/main")
    rec_path = Path(wo.admin_of(str(d))[0]) / wo.OWNER
    rec = json.loads(rec_path.read_text())
    rec["cache_roots"] = ["node_modules"]
    rec_path.write_text(json.dumps(rec))
    got, _, bad = wo.read_record(str(rec_path.parent))
    assert bad is None and got["cache_roots"] == [{"path": "node_modules", "kind": None}]
    (Path(wo.admin_of(str(d))[0]) / "AUTO_MERGE").write_text(w.git(repo, "rev-parse", "HEAD") + "\n")
    rc, out, rep = w.prune("--apply")
    assert d.exists() and reason(rep, d) == "pseudo-ref-unreadable"
    bad_reg = w.tmp / "roots.tsv"
    bad_reg.write_text("not a valid line\n")
    w.env["LIFECYCLE_CACHE_ROOTS"] = str(bad_reg)
    rc, out, rep = w.prune("--apply")
    assert rc == 4 and "registry" in out
