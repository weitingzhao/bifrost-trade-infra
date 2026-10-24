"""Test fixture for the local sweep and worktree records (W-31 4.6 S2, S3): a throwaway world
in a temp dir with a workspace, AGENT_WORK, bare remotes standing in for Gitea, a fake lsof
and a git wrapper that logs every call. Nothing outside the temp dir is read for deletion or
written. Used by scripts/test_prune_merged_branches.py and scripts/agent-host/test_lifecycle_*.py,
test_worktree_owner.py; not a test module itself.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import new_worktree  # noqa: E402

PRUNE = HERE.parent / "prune-merged-branches.sh"
NEW_WORKTREE = HERE / "new-worktree.sh"
REAL_GIT = shutil.which("git") or "/usr/bin/git"
FAKE_LSOF = """#!/usr/bin/env bash
d=${FAKE_LSOF_DIR:?}
[ -f "$d/out" ] && cat "$d/out"
[ -f "$d/err" ] && cat "$d/err" >&2
exit "$(cat "$d/rc" 2>/dev/null || echo 0)"
"""
# Logs every call; fails a call whose arguments contain $FAKE_GIT_FAIL (a read failure).
GIT_WRAPPER = f"""#!/usr/bin/env bash
[ -n "${{GIT_CALLS:-}}" ] && printf '%s\\n' "$*" >> "$GIT_CALLS"
if [ -n "${{FAKE_GIT_FAIL:-}}" ] && [[ " $* " == *" $FAKE_GIT_FAIL "* ]]; then echo "fatal: injected" >&2; exit 128; fi
exec {REAL_GIT} "$@"
"""


class World:
    def __init__(self, tmp: Path) -> None:
        self.tmp = Path(os.path.realpath(tmp))
        self.ws, self.aw = self.tmp / "ws", self.tmp / "aw"
        self.backup, self.status, self.tmpdir = self.tmp / "backup", self.tmp / "status", self.tmp / "tmpdir"
        self.remotes, self.bin, self.lsof = self.tmp / "remotes", self.tmp / "bin", self.tmp / "lsof"
        for d in (self.ws, self.aw, self.remotes, self.bin, self.lsof, self.tmpdir, self.tmp / "home"):
            d.mkdir(parents=True, exist_ok=True)
        self.repos_file = self.tmp / "repos.txt"
        self.repos_file.write_text("# test list\n")
        mount = "#!/usr/bin/env bash\n[ -f \"$FAKE_LSOF_DIR/mount.out\" ] && cat \"$FAKE_LSOF_DIR/mount.out\" || echo '/dev/disk1 on / (apfs, local)'\n"
        for name, text in (("lsof", FAKE_LSOF), ("mount", mount), ("git", GIT_WRAPPER),
                           ("gh", "#!/usr/bin/env bash\necho \"gh $*\" >> \"${GIT_CALLS:-/dev/null}\"\nexit 0\n")):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        self.git_calls = self.tmp / "git-calls.log"
        self.env: Dict[str, str] = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.tmp / "home"), "TMPDIR": str(self.tmpdir), "LANG": "C",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Lifecycle Test", "GIT_AUTHOR_EMAIL": "lifecycle@example.invalid",
            "GIT_COMMITTER_NAME": "Lifecycle Test", "GIT_COMMITTER_EMAIL": "lifecycle@example.invalid",
            "WORKSPACE": str(self.ws), "AGENT_WORK": str(self.aw), "BACKUP_ROOT": str(self.backup),
            "LIFECYCLE_STATUS_DIR": str(self.status), "LIFECYCLE_LOCK": str(self.tmp / "lock"),
            "LIFECYCLE_LSOF": str(self.bin / "lsof"), "LIFECYCLE_MOUNT": str(self.bin / "mount"),
            "LIFECYCLE_REPOS_FILE": str(self.repos_file), "LIFECYCLE_END_MIN_AGE_MIN": "0",
            "LIFECYCLE_MACHINE": "testhost", "FAKE_LSOF_DIR": str(self.lsof), "LIFECYCLE_PYTHON": sys.executable,
            "CLAUDE_CODE_SESSION_ID": "sess-1", "CLAUDE_CODE_HOST_SESSION_ID": "",
        }

    # -- git -------------------------------------------------------------------------------
    def git(self, cwd: Path, *args: str, check: bool = True) -> str:
        r = subprocess.run(["git", "-C", str(cwd), *map(str, args)], env=self.env, capture_output=True, text=True)
        if check and r.returncode != 0:
            raise AssertionError(f"git {' '.join(map(str, args))}: {r.stderr}")
        return r.stdout.strip()

    def repo(self, name: str = "bifrost-x", where: Optional[Path] = None, listed: bool = True) -> Path:
        bare = self.remotes / f"{name}.git"
        self.git(self.tmp, "init", "-q", "--bare", "--initial-branch=main", bare)
        d = (where or self.ws) / name
        self.git(self.tmp, "clone", "-q", bare, d)
        (d / "README").write_text("readme\n")
        (d / ".gitignore").write_text("node_modules/\nbuild/\n")
        self.git(d, "add", "README", ".gitignore")
        self.git(d, "commit", "-q", "-m", "Initial main")
        self.git(d, "push", "-q", "origin", "main")
        if listed:
            with open(self.repos_file, "a") as f:
                f.write(name + "\n")
        return d

    def commit(self, cwd: Path, msg: str, change_id: Optional[str] = None, fname: Optional[str] = None) -> str:
        f = cwd / (fname or "work.txt")
        f.write_text((f.read_text() if f.exists() else "") + msg + "\n")
        self.git(cwd, "add", f.name)
        body = msg + (f"\n\nChange-Id: {change_id}" if change_id else "")
        self.git(cwd, "commit", "-q", "-m", body)
        return self.git(cwd, "rev-parse", "HEAD")

    def remote_refs(self, name: str = "bifrost-x") -> Dict[str, str]:
        out = self.git(self.tmp, "--git-dir", self.remotes / f"{name}.git", "for-each-ref", "--format=%(refname) %(objectname)")
        return dict(line.split(" ") for line in out.splitlines())

    def has_commit(self, repo: Path, sha: str) -> bool:
        return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"], env=self.env).returncode == 0

    # -- worktrees ---------------------------------------------------------------------------
    def new_worktree(self, repo: Path, rel: str, branch: Optional[str] = None, detach: Optional[str] = None,
                     work: str = "W-31", session: str = "sess-1", extra: Tuple[str, ...] = ()) -> Path:
        d = self.aw / rel
        args = [str(repo), str(d)] + ([branch] if branch else ["--detach", detach or "origin/main"])
        args += ["--work", work, "--session", session, *extra]
        rc, out = self.call(new_worktree.main, args)
        assert rc == 0, out
        return d

    def end(self, d: Path, *extra: str) -> None:
        rc, out = self.call(new_worktree.main, ["--end", str(d), *extra])
        assert rc == 0, out

    def renew(self, d: Path) -> None:
        rc, out = self.call(new_worktree.main, ["--renew", str(d)])
        assert rc == 0, out

    def look(self, d: Path) -> Dict[str, object]:
        rc, out = self.call(new_worktree.main, ["--show", str(d)])
        return json.loads(out[out.index("{"):])

    def call(self, fn, args: List[str]) -> Tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = fn(args, dict(self.env))
        return rc, buf.getvalue()

    # -- the sweep ---------------------------------------------------------------------------
    def prune(self, *args: str, inproc: bool = False) -> Tuple[int, str, Dict[str, object]]:
        """prune-merged-branches.sh --local-only <args>, through bash (or in-process for seams)."""
        report = self.status / "lifecycle-local.json"
        if report.exists():
            report.unlink()
        if inproc:
            import lifecycle_local  # S2; the S3 tests never sweep
            rc, out = self.call(lifecycle_local.main, ["--local-only", *args])
        else:
            r = subprocess.run(["bash", str(PRUNE), "--local-only", *args], env=self.env, capture_output=True, text=True)
            rc, out = r.returncode, r.stdout + r.stderr
        rep = json.loads(report.read_text()) if report.exists() else {}
        return rc, out, rep

    @staticmethod
    def items(rep: Dict[str, object]) -> Dict[str, Dict[str, object]]:
        """Report items by name (worktree path or branch)."""
        out = {}
        for r in rep.get("repos", []):  # type: ignore[union-attr]
            for i in r["items"]:
                out[i["name"]] = i
        return out

    def run_dirs(self, repo: str = "bifrost-x") -> List[Path]:
        """Run directories under <backup>/testhost/<repo id>/, the repo id being <name>-<hash>."""
        base = self.backup / "testhost"
        if not base.exists():
            return []
        return sorted(r for d in base.iterdir() if d.name.rsplit("-", 1)[0] == repo for r in d.iterdir())

    def lsof_out(self, text: str = "", rc: int = 0, err: str = "") -> None:
        (self.lsof / "out").write_text(text)
        (self.lsof / "rc").write_text(str(rc))
        (self.lsof / "err").write_text(err)
