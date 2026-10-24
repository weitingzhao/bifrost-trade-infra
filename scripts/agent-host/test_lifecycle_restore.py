"""A quarantine an interrupted or failed run leaves behind (review 552 A4, C1): it is moved
back only when its shape is unambiguous, inside this run's roots, with the directory the
journal recorded and the original path free; anything else is reported and left alone.

    python3 -m pytest -q scripts/agent-host/test_lifecycle_restore.py
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lifecycle_local  # noqa: E402
import lifecycle_quarantine as lq  # noqa: E402
import worktree_owner as wo  # noqa: E402
from lifecycle_testlib import World  # noqa: E402


@pytest.fixture(name="w")
def restore_world(tmp_path):
    return World(tmp_path)


def interrupted(w, monkeypatch, rel="cut/bifrost-x", relative=False):
    """An ended worktree whose sweep died in quarantine; renewed afterwards, so that once it
    is back no sweep removes it. (repo, original path, quarantine path, admin dir). With
    relative, the repository writes relative worktree links (worktree.useRelativePaths)."""
    repo = w.repo()
    if relative:
        w.git(repo, "config", "worktree.useRelativePaths", "true")
    d = w.new_worktree(repo, rel, detach="origin/main")
    if relative and os.path.isabs((Path(wo.admin_of(str(d))[0]) / "gitdir").read_text().strip()):
        pytest.skip("this git does not write relative worktree links")
    w.end(d)

    def stop_in_quarantine(ctx, it, q):
        raise SystemExit(9)
    monkeypatch.setattr(lifecycle_local, "_in_quarantine", stop_in_quarantine)
    with pytest.raises(SystemExit):
        w.prune("--apply", inproc=True)
    monkeypatch.setattr(lifecycle_local, "_in_quarantine", lambda *a: None)
    (q,) = [p for p in d.parent.iterdir() if lq.QUARANTINE in p.name]
    admin = Path(wo.admin_of(str(q))[0])
    w.renew(q)
    return repo, d, q, admin


def journal(w):
    return sorted((w.status / lq.JOURNAL).iterdir())


def consistent(w, repo, path):
    listing = w.git(repo, "worktree", "list", "--porcelain")
    return f"worktree {path}\n" in listing + "\n" and "prunable" not in listing and w.git(path, "rev-parse", "HEAD")


def notes(rep):
    return " ".join(rep["notes"])


def test_a_finished_quarantine_goes_back_only_inside_this_runs_roots(w, monkeypatch):
    repo, d, q, admin = interrupted(w, monkeypatch)
    w.env["LIFECYCLE_WORKTREE_ROOTS"] = str(w.ws)  # the run that comes next no longer covers AGENT_WORK
    rc, out, rep = w.prune("--apply", inproc=True)
    assert q.exists() and not d.exists() and len(journal(w)) == 1 and "left as it is" in notes(rep)
    del w.env["LIFECYCLE_WORKTREE_ROOTS"]
    rc, out, rep = w.prune("--apply", inproc=True)
    assert d.exists() and not q.exists() and journal(w) == [] and consistent(w, repo, d)


def test_another_directory_at_the_quarantine_or_a_taken_original_is_left_alone(w, monkeypatch):
    repo, d, q, admin = interrupted(w, monkeypatch)
    d.mkdir()  # someone made the original path again
    rc, out, rep = w.prune("--apply", inproc=True)
    assert q.exists() and "is taken" in notes(rep) and len(journal(w)) == 1
    d.rmdir()
    aside = q.parent / "aside"
    os.rename(q, aside)
    shutil.copytree(aside, q, symlinks=True)  # same content, another directory
    rc, out, rep = w.prune("--apply", inproc=True)
    assert q.exists() and not d.exists() and "not (only) the one the journal recorded" in notes(rep)
    assert len(journal(w)) == 1


def test_a_move_that_stopped_after_the_rename_is_finished_backwards(w, monkeypatch):
    """Directory at the quarantine, Git still naming the original: rename it back."""
    repo, d, q, admin = interrupted(w, monkeypatch)
    (admin / "gitdir").write_text(f"{d}/.git\n")
    rc, out, rep = w.prune("--apply", inproc=True)
    assert d.exists() and not q.exists() and journal(w) == [] and consistent(w, repo, d)
    assert "moved back" in notes(rep)


def test_a_move_that_stopped_before_the_rename_is_repaired(w, monkeypatch):
    """Directory at the original, Git already naming the quarantine: point Git back."""
    repo, d, q, admin = interrupted(w, monkeypatch)
    os.rename(q, d)
    rc, out, rep = w.prune("--apply", inproc=True)
    assert d.exists() and not q.exists() and journal(w) == [] and consistent(w, repo, d)


def test_a_move_that_reports_an_error_keeps_its_journal_until_settled(w):
    """git worktree move failing outright, or doing its work and then failing: the journal
    decides what is there, and the worktree ends up at its path, kept."""
    repo = w.repo()
    for env, rel in (({"FAKE_GIT_FAIL": "move"}, "fail/bifrost-x"), ({"FAKE_GIT_AFTER": "move"}, "after/bifrost-x")):
        d = w.new_worktree(repo, rel, detach="origin/main")
        w.end(d)
        w.env.update(env)
        rc, out, rep = w.prune("--apply")
        for k in env:
            del w.env[k]
        item = World.items(rep)[str(d)]
        assert rc == 0 and item["reason"] == "quarantine-failed", (env, out)
        assert d.exists() and journal(w) == [] and consistent(w, repo, d)
        assert not [p for p in d.parent.iterdir() if lq.QUARANTINE in p.name]


def links(path):
    """(the worktree's .git, its admin dir's gitdir) as text."""
    admin = Path(wo.admin_of(str(path))[0])
    return (path / ".git").read_text(), (admin / "gitdir").read_text()


def test_repairing_one_worktree_touches_no_other(w, monkeypatch):
    """Review 553 A2: the "directory back, gitdir still names the quarantine" shape is fixed
    by rewriting that one gitdir. git worktree repair <path> would also walk every linked
    worktree of the repository and rewrite links it finds broken (Git 2.50: it rewrites the
    .git of another worktree outside the roots). Both others stay byte for byte: one with
    relative links, one whose .git someone broke."""
    repo, d, q, admin = interrupted(w, monkeypatch)
    rel = w.tmp / "outside" / "relative"
    broken = w.tmp / "outside" / "broken"
    w.git(repo, "worktree", "add", "-q", "--relative-paths", "--detach", rel, "origin/main")
    w.git(repo, "worktree", "add", "-q", "--detach", broken, "origin/main")
    (broken / ".git").write_text("gitdir: /nowhere/admin\n")
    files = [rel / ".git", Path(wo.admin_of(str(rel))[0]) / "gitdir", broken / ".git"]
    before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in files]
    os.rename(q, d)  # the directory is back; Git still names the quarantine
    rc, out, rep = w.prune("--apply", inproc=True)
    assert d.exists() and journal(w) == [] and consistent(w, repo, d)
    assert [(p.read_bytes(), p.stat().st_mtime_ns) for p in files] == before


@pytest.mark.parametrize("shape", ["finished", "after-rename", "before-rename"])
def test_relative_links_are_followed_in_every_shape(w, monkeypatch, shape):
    """Review 553 A3: with relative worktree links the quarantine goes back in all three shapes,
    and the links stay relative."""
    repo, d, q, admin = interrupted(w, monkeypatch, relative=True)
    if shape == "after-rename":  # directory at q, Git still naming the original
        (admin / "gitdir").write_text(os.path.relpath(d / ".git", admin) + "\n")
    elif shape == "before-rename":  # directory back at the original, Git naming the quarantine
        os.rename(q, d)
    rc, out, rep = w.prune("--apply", inproc=True)
    assert d.exists() and not q.exists() and journal(w) == [] and consistent(w, repo, d), notes(rep)
    dotgit, gitdir = links(d)
    assert not os.path.isabs(gitdir.strip()) and not os.path.isabs(dotgit.strip()[len("gitdir: "):])


def test_a_shape_whose_links_do_not_close_keeps_its_journal(w, monkeypatch):
    """Review 553 D3, D1: back at the original path but its .git names another admin dir, or a
    gitdir file too long to be one: not settled, the journal stays, the report says so."""
    repo, d, q, admin = interrupted(w, monkeypatch)
    os.rename(q, d)
    (admin / "gitdir").write_text(f"{d}/.git\n")
    real = (d / ".git").read_text()
    (d / ".git").write_text("gitdir: " + str(w.tmp / "nowhere") + "\n")
    rc, out, rep = w.prune("--apply", inproc=True)
    assert len(journal(w)) == 1 and "needs repair by hand" in notes(rep)
    (d / ".git").write_text(real)
    (admin / "gitdir").write_text(f"{d}/.git" + " " * 9000 + "\n")
    rc, out, rep = w.prune("--apply", inproc=True)
    assert len(journal(w)) == 1 and "larger than" in notes(rep)
