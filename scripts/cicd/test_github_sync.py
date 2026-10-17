"""k8s/cicd/github-sync: read-primaries.sh and sync.sh, run locally.

Step 0e of agent-config/work/multi-agent/CUT-gitea-primary-2026-10-17.md: the
repositories Gitea holds as its primary have main and their tags copied to
GitHub, fast-forward only, never forced, never deleted. sync.sh runs with real
git against two local bare repositories standing for Gitea and GitHub;
read-primaries.sh runs with a fake curl. No cluster, no network.

    python3 -m unittest scripts/cicd/test_github_sync.py
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "k8s" / "cicd" / "github-sync"
SYNC = DIR / "sync.sh"
READ = DIR / "read-primaries.sh"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(cwd: Path, *args: str, env: dict | None = None) -> str:
    full = {**os.environ, **GIT_ENV, "HOME": str(cwd), **(env or {})}
    return subprocess.run(["git", *args], cwd=cwd, env=full, check=True, capture_output=True, text=True).stdout.strip()


class Fixture:
    """Gitea and GitHub as bare repositories under one root, and a working clone."""

    def __init__(self, root: Path, repo: str = "r1") -> None:
        self.root, self.repo = root, repo
        self.gitea = root / "gitea"
        self.github = root / "github"
        for side in (self.gitea, self.github):
            side.mkdir()
            git(root, "init", "-q", "--bare", "--initial-branch=main", str(side / f"{repo}.git"))
        self.work = root / "work"
        git(root, "clone", "-q", str(self.gitea / f"{repo}.git"), str(self.work))
        self.commit("first")
        git(self.work, "push", "-q", "origin", "main")
        git(self.work, "push", "-q", str(self.github / f"{repo}.git"), "main")

    def commit(self, msg: str) -> str:
        (self.work / "f").write_text(msg, encoding="utf-8")
        git(self.work, "add", "f")
        git(self.work, "commit", "-q", "-m", msg)
        return git(self.work, "rev-parse", "HEAD")

    def head(self, side: Path, ref: str = "refs/heads/main") -> str:
        out = git(self.root, "ls-remote", str(side / f"{self.repo}.git"), ref)
        return out.split()[0] if out else ""

    def run(self, *args: str, token: str | None = "fixture", primaries: list[str] | None = None) -> subprocess.CompletedProcess:
        listing = self.root / "primaries"
        listing.write_text("\n".join(primaries if primaries is not None else [self.repo]) + "\n", encoding="utf-8")
        env = {
            **os.environ,
            **GIT_ENV,
            "HOME": str(self.root),
            "GITEA_GIT_BASE": f"file://{self.gitea}",
            "GITHUB_BASE": f"file://{self.github}",
        }
        env.pop("GITHUB_TOKEN", None)
        if token is not None:
            env["GITHUB_TOKEN"] = token
        return subprocess.run(["sh", str(SYNC), str(listing), *args], env=env, capture_output=True, text=True, timeout=120)


class Sync(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Fixture(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_main_ahead_on_gitea_is_fast_forwarded(self) -> None:
        sha = self.f.commit("second")
        git(self.f.work, "push", "-q", "origin", "main")
        result = self.f.run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.f.head(self.f.github), sha)
        self.assertIn("pushed", result.stdout)

    def test_a_diverged_github_is_reported_and_left_alone(self) -> None:
        git(self.f.work, "push", "-q", "origin", "main")
        other = self.f.commit("on github only")
        git(self.f.work, "push", "-q", str(self.f.github / "r1.git"), "main")
        git(self.f.work, "reset", "-q", "--hard", "HEAD~1")
        mine = self.f.commit("on gitea only")
        git(self.f.work, "push", "-q", "-f", "origin", "main")
        result = self.f.run()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("does not contain", result.stdout)
        self.assertEqual(self.f.head(self.f.github), other)
        self.assertEqual(self.f.head(self.f.gitea), mine)

    def test_tags_are_copied_and_a_moved_tag_is_not(self) -> None:
        git(self.f.work, "tag", "-a", "v1", "-m", "one")
        git(self.f.work, "push", "-q", "origin", "refs/tags/v1")
        git(self.f.work, "tag", "v2")
        git(self.f.work, "push", "-q", "origin", "refs/tags/v2")
        self.f.commit("third")
        git(self.f.work, "tag", "v2-github")
        git(self.f.work, "push", "-q", str(self.f.github / "r1.git"), "refs/tags/v2-github:refs/tags/v2")
        result = self.f.run()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        # the annotated tag object, not only its commit
        self.assertEqual(self.f.head(self.f.github, "refs/tags/v1"), self.f.head(self.f.gitea, "refs/tags/v1"))
        self.assertIn("refs/tags/v2: GitHub has the tag at", result.stdout)
        self.assertNotEqual(self.f.head(self.f.github, "refs/tags/v2"), self.f.head(self.f.gitea, "refs/tags/v2"))

    def test_one_ref_touches_only_that_ref(self) -> None:
        git(self.f.work, "tag", "v1")
        git(self.f.work, "push", "-q", "origin", "refs/tags/v1")
        sha = self.f.commit("second")
        git(self.f.work, "push", "-q", "origin", "main")
        result = self.f.run("refs/heads/main")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.f.head(self.f.github), sha)
        self.assertEqual(self.f.head(self.f.github, "refs/tags/v1"), "")

    def test_other_branches_are_never_copied(self) -> None:
        result = self.f.run("refs/heads/agent/t_1/a1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)  # not on Gitea: nothing to do
        git(self.f.work, "push", "-q", "origin", "HEAD:refs/heads/agent/t_1/a1")
        result = self.f.run("refs/heads/agent/t_1/a1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("only main and tags are copied", result.stdout)
        self.assertEqual(self.f.head(self.f.github, "refs/heads/agent/t_1/a1"), "")

    def test_no_token_is_needed_until_something_must_be_pushed(self) -> None:
        result = self.f.run(token=None)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.f.commit("second")
        git(self.f.work, "push", "-q", "origin", "main")
        result = self.f.run(token=None)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("no GitHub token", result.stdout)

    def test_no_primaries_is_nothing_to_do(self) -> None:
        self.f.commit("second")
        git(self.f.work, "push", "-q", "origin", "main")
        result = self.f.run(token=None, primaries=[])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotEqual(self.f.head(self.f.github), self.f.head(self.f.gitea))

    def test_the_token_is_never_on_a_command_line(self) -> None:
        text = SYNC.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "GITHUB_TOKEN" in line and "git " in line:
                self.fail(f"a git command line names the token: {line}")


FAKE_CURL = """#!/usr/bin/env python3
import json, os, sys
from urllib.parse import urlparse
url = [a for a in sys.argv[1:] if a.startswith("http")][-1]
code, body = json.loads(os.environ["FAKE_GITEA"]).get(urlparse(url).path, [404, "{}"])
sys.stdout.write(body + "\\n" + str(code))
"""


class ReadPrimaries(unittest.TestCase):
    def run_read(self, repos: list[str], gitea: dict) -> tuple[subprocess.CompletedProcess, list[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            bindir.mkdir()
            curl = bindir / "curl"
            curl.write_text(FAKE_CURL, encoding="utf-8")
            curl.chmod(curl.stat().st_mode | stat.S_IXUSR)
            out = Path(tmp) / "primaries"
            env = {"PATH": f"{bindir}:/usr/bin:/bin", "GITEA_TOKEN": "fixture", "FAKE_GITEA": json.dumps(gitea)}
            result = subprocess.run(["sh", str(READ), str(out), *repos], env=env, capture_output=True, text=True, timeout=60)
            listed = out.read_text(encoding="utf-8").split() if out.exists() else []
            return result, listed

    @staticmethod
    def repo(name: str, mirror) -> dict:
        body = {"name": name, "parent": None, "mirror_interval": "8h0m0s"}
        if mirror is not None:
            body["mirror"] = mirror
        return {f"/api/v1/repos/bifrost/{name}": [200, json.dumps(body, separators=(",", ":"))]}

    def test_only_regular_repositories_are_listed(self) -> None:
        result, listed = self.run_read(["a", "b"], {**self.repo("a", True), **self.repo("b", False)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(listed, ["b"])

    def test_an_unreadable_or_silent_repository_stops_the_run(self) -> None:
        for gitea, want in (({}, "HTTP 404"), (self.repo("a", None), "did not say")):
            result, _ = self.run_read(["a"], gitea)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(want, result.stderr)


if __name__ == "__main__":
    unittest.main()
