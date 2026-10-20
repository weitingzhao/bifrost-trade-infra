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
    branches = ["agent/protected"] + [f"merged-{i:02d}" for i in range(59)]
    git("-C", clone, "push", "origin", *[f"main:refs/heads/{b}" for b in branches])
    if refuse:
        hook = bare / "hooks" / "pre-receive"
        hook.write_text(
            "#!/bin/sh\n"
            "while read -r old new ref; do\n"
            '  if [ "$ref" = refs/heads/agent/protected ]; then exit 1; fi\n'
            "done\n"
        )
        hook.chmod(0o755)

    result = subprocess.run(
        ["bash", str(SCRIPT), "--apply", "--repos", "clone", "--min-age-hours", "0"],
        env=env, capture_output=True, text=True,
    )
    remaining = set(git("--git-dir", bare, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines())
    assert remaining == ({"main", "agent/protected"} if refuse else {"main"})
    assert result.returncode == (1 if refuse else 0), result.stderr
    summary = next(line for line in result.stdout.splitlines() if line.startswith("remote  "))
    assert summary == (
        "remote  clone: deleted 59, refused 1 (agent/protected)"
        if refuse else "remote  clone: deleted 60"
    )
