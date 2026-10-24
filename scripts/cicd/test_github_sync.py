"""k8s/cicd/github-sync: read-primaries.py and sync.sh, run locally.

Step 0e of agent-config/work/multi-agent/CUT-gitea-primary-2026-10-17.md: the
repositories Gitea holds as its primary have main and their tags copied to
GitHub, fast-forward only, never forced, never deleted. sync.sh runs with real
git against two local bare repositories standing for Gitea and GitHub;
read-primaries.py runs against a local fake Gitea. No cluster, no network.

    python3 -m unittest scripts/cicd/test_github_sync.py
"""

from __future__ import annotations

import os
import io
import contextlib
import runpy
import shutil
import urllib.request
from unittest.mock import patch
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_task_gitea_mirror_sync import FakeGitea, repo  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "k8s" / "cicd" / "github-sync"
SYNC = DIR / "sync.sh"
READ = DIR / "read-primaries.py"
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
            "GITEA_GIT_BASE": "http://attacker.invalid/bifrost",
            "GITEA_TOKEN": "fixture-reader",
            "GIT_CONFIG_GLOBAL": "/host-config",
            "GITHUB_BASE": f"file://{self.github}",
        }
        env.pop("GITHUB_TOKEN", None)
        if token is not None:
            env["GITHUB_TOKEN"] = token
        bindir = self.root / 'bin'
        bindir.mkdir(exist_ok=True)
        wrapper = bindir / 'git'
        wrapper.write_text("#!/usr/bin/env python3\n" + r'''import json, os, sys
args = sys.argv[1:]
if any(c in args for c in ('ls-remote', 'fetch', 'push', 'merge-base', 'init')):
    config = {os.environ['GIT_CONFIG_KEY_' + str(i)]: os.environ['GIT_CONFIG_VALUE_' + str(i)]
              for i in range(int(os.environ['GIT_CONFIG_COUNT']))}
    assert config['http.followRedirects'] == 'false'
    assert config['credential.helper'] == ''
    assert config['http.http://gitea.cicd.svc.cluster.local:3000/.extraHeader'] == 'Authorization: token fixture-reader'
    assert os.environ['GIT_CONFIG_GLOBAL'] == '/dev/null'
    assert 'fixture-reader' not in str(args)
    assert 'GITEA_TOKEN' not in os.environ
    assert 'attacker.invalid' not in str(args)
os.execv(os.environ['REAL_GIT'], [os.environ['REAL_GIT'], '-c',
    'url.file://' + os.environ['LOCAL_GITEA'] + '/.insteadOf=http://gitea.cicd.svc.cluster.local:3000/bifrost/', *args])
''')
        wrapper.chmod(0o755)
        env.update(REAL_GIT=shutil.which('git'), LOCAL_GITEA=str(self.gitea),
                   PATH=str(bindir) + ':' + os.environ['PATH'])
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

    def test_plus_tag_matches_trigger_and_is_copied(self) -> None:
        tag = 'v1.2.3+build.1'
        git(self.f.work, 'tag', tag)
        git(self.f.work, 'push', '-q', 'origin', 'refs/tags/' + tag)
        result = self.f.run('refs/tags/' + tag)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.f.head(self.f.github, 'refs/tags/' + tag), self.f.head(self.f.gitea, 'refs/tags/' + tag))
        trigger = (ROOT / 'k8s/cicd/tekton/trigger-trade-ci.yaml').read_text()
        self.assertIn("^refs/tags/[A-Za-z0-9._/+-]{1,200}$", trigger)

    def test_other_branches_are_never_copied(self) -> None:
        result = self.f.run("refs/heads/agent/t_1/a1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)  # rejected before reading Gitea
        git(self.f.work, "push", "-q", "origin", "HEAD:refs/heads/agent/t_1/a1")
        result = self.f.run("refs/heads/agent/t_1/a1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("only main and tags are copied", result.stdout + result.stderr)
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


class ReadPrimaries(unittest.TestCase):
    def run_read(self, repos: list[str], routes: dict) -> tuple[subprocess.CompletedProcess, list[str], FakeGitea]:
        from http_transport_fixture import response
        with tempfile.TemporaryDirectory() as tmp, FakeGitea(routes) as g:
            out = Path(tmp) / 'primaries'
            def http_open(self, req):
                assert req.host == 'gitea.cicd.svc.cluster.local:3000' and not req.has_proxy()
                path = urllib.request.urlparse(req.full_url).path
                g.requests.append((req.get_method(), path, req.headers['Authorization']))
                status, body = routes.get(req.get_method() + ' ' + path, (404, '{}'))
                return response(req, status, body)
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, {'GITEA_TOKEN': 'fixture-admin-token', 'GITEA_API': 'http://attacker.invalid'}), \
                    patch.object(sys, 'argv', [str(READ), str(out), *repos]), \
                    patch.object(urllib.request.HTTPHandler, 'http_open', http_open), \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = runpy.run_path(str(READ))['main']()
            result = subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())
            listed = out.read_text().split() if out.exists() else []
            return result, listed, g

    def test_only_regular_repositories_are_listed(self) -> None:
        result, listed, g = self.run_read(["a", "b"], {**repo("a", '{"mirror":true}'), **repo("b", '{"mirror":false}')})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(listed, ["b"])
        self.assertTrue(all(auth == "token fixture-admin-token" for _, _, auth in g.requests))

    def test_the_top_level_field_decides_not_a_parents(self) -> None:
        routes = {
            **repo("mirrored", '{"name":"mirrored","parent":{"mirror":false},"mirror":true}'),
            **repo("fork", '{ "name": "fork", "parent": { "mirror": true }, "mirror": false }'),
        }
        result, listed, _ = self.run_read(["mirrored", "fork"], routes)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(listed, ["fork"])

    def test_an_unreadable_or_silent_repository_stops_the_run(self) -> None:
        for routes, want in (({}, "HTTP 404"), (repo("a", '{"name":"a"}'), "did not say"), (repo("a", "nope"), "did not say")):
            result, listed, _ = self.run_read(["a"], routes)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(want, result.stderr)
            self.assertEqual(listed, [])


if __name__ == "__main__":
    unittest.main()
