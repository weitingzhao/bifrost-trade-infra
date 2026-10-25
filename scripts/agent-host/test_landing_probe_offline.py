"""Landing prefix integration: real local git; fake API process, no sockets.

The existing protection suite covers HTTP parsing. This fixture isolates the
new branch selection and cleanup while exercising real git pre-receive hooks.
"""
import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_probe_gitea_protection import HOOK, PROBE


@pytest.mark.parametrize("prefix", ["agent/_probe", "land/stg/_probe", "main"])
def test_prefix_and_cleanup(tmp_path, prefix):
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
    source = tmp_path / "source"
    source.mkdir()

    def git(*args, cwd=source):
        return subprocess.check_output(["git", *args], cwd=cwd, env=env, text=True).strip()

    git("init", "-q", "--initial-branch=main")
    git("commit", "-qm", "fixture", "--allow-empty")
    before = git("rev-parse", "HEAD")
    bare = tmp_path / "bifrost/primary-probe.git"
    bare.parent.mkdir()
    git("clone", "-q", "--bare", str(source), str(bare))
    hook = bare / "hooks/pre-receive"
    hook.write_text(HOOK)
    hook.chmod(0o755)
    token = tmp_path / "token"
    token.write_text("fixture-token")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # Match only the existing api() subprocess protocol, not any git call.
    fake = bindir / "python3"
    fake.write_text('''#!/bin/bash
cat >/dev/null
echo "$*" >> "$API_CALLS"
case "$2:$3" in
  GET:/repos/bifrost/primary-probe) printf '200\tfalse\n' ;;
  POST:/repos/bifrost/primary-probe/pulls) printf '201\t7\t\n' ;;
  POST:/repos/bifrost/primary-probe/pulls/7/merge) printf '405\tUser not allowed to merge PR\n' ;;
  PATCH:/repos/bifrost/primary-probe/pulls/7) printf '200\t"closed"\n'; touch "$API_CLOSED" ;;
  GET:/repos/bifrost/primary-probe/pulls/7)
    if [ -f "$API_CLOSED" ]; then printf '200\t"closed"\n'; else printf '200\ttrue\n'; fi ;;
  *) echo 'unexpected fake API call' >&2; exit 9 ;;
esac
''')
    fake.chmod(0o755)
    env.update(PATH=str(bindir) + ":" + env["PATH"], PROBE_GITEA="file://" + str(tmp_path),
               PROBE_TOKEN_FILE=str(token), PROBE_BRANCH_PREFIX=prefix,
               API_CALLS=str(tmp_path / "calls"), API_CLOSED=str(tmp_path / "closed"))
    result = subprocess.run(["bash", str(PROBE)], env=env, capture_output=True, text=True)
    if prefix == "main":
        assert result.returncode != 0
        assert "unsupported branch prefix" in result.stderr
        assert not (tmp_path / "calls").exists()
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "ok    delete " + prefix + "/" in result.stdout
        assert "all as expected" in result.stdout
        assert (tmp_path / "closed").exists()
    assert git("--git-dir", str(bare), "rev-parse", "main") == before
    assert git("--git-dir", str(bare), "for-each-ref", "--format=%(refname)") == "refs/heads/main"
