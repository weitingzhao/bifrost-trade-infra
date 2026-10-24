"""Exercise remote pruning against local repositories, including rejected batches."""

import os
from pathlib import Path
import subprocess

import pytest


SCRIPT = Path(__file__).with_name("prune-merged-branches.sh").resolve()


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
