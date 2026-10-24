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


def interrupted(w, monkeypatch, rel="cut/bifrost-x"):
    """An ended worktree whose sweep died in quarantine; renewed afterwards, so that once it
    is back no sweep removes it. (repo, original path, quarantine path, admin dir)."""
    repo = w.repo()
    d = w.new_worktree(repo, rel, detach="origin/main")
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
