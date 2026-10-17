"""push-main.sh against fixture repositories and the real code-health scan (TD-341).

No network, no cluster: origin is a bare repository in a temporary directory
and the release window is a stub script whose exit code the test sets.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PUSH_MAIN = HERE / "push-main.sh"
BASELINES = HERE.parent.parent / "agent-config" / "scripts" / "code-health" / "baselines.env"


def _baseline(name: str) -> int:
    m = re.search(rf"^{name}=(\d+)$", BASELINES.read_text(), re.M)
    assert m, name
    return int(m.group(1))


def _git(cwd: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    out = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", *args],
        cwd=cwd, env=env, check=True, capture_output=True, text=True,
    )
    return out.stdout.strip()


class PushMain(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.window_rc = root / "window.rc"
        self.window_rc.write_text("0")
        self.window = root / "window.sh"
        self.window.write_text(f'#!/bin/sh\nexit "$(cat {self.window_rc})"\n')
        self.window.chmod(0o755)
        self.origin = root / "remote" / "bifrost-platform.git"
        self.origin.parent.mkdir()
        _git(root, "init", "--quiet", "--bare", "--initial-branch=main", str(self.origin))
        self.work = root / "work" / "bifrost-platform"
        self.work.parent.mkdir()
        _git(root, "clone", "--quiet", str(self.origin), str(self.work))
        _git(self.work, "checkout", "--quiet", "-b", "main")
        (self.work / "README.md").write_text("fixture\n")
        _git(self.work, "add", "README.md")
        _git(self.work, "commit", "--quiet", "-m", "init")
        _git(self.work, "push", "--quiet", "origin", "main")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _big_files(self, start: int, n: int) -> None:
        body = "package x\n" + "// line\n" * 801
        for i in range(start, start + n):
            (self.work / f"big{i}.go").write_text(body)
            _git(self.work, "add", f"big{i}.go")
        _git(self.work, "commit", "--quiet", "-m", f"files {start}..{start + n - 1}")

    def _push(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PUSH_MAIN_WINDOW": str(self.window)}
        return subprocess.run(
            ["bash", str(PUSH_MAIN), str(self.work), *args],
            env=env, capture_output=True, text=True,
        )

    def _remote_main(self) -> str:
        return _git(self.origin, "rev-parse", "main")

    def test_at_the_baseline_pushes(self) -> None:
        self._big_files(0, _baseline("OVERSIZED_PLATFORM_BASELINE"))
        head = _git(self.work, "rev-parse", "HEAD")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._remote_main(), head)
        self.assertEqual(_git(self.work, "worktree", "list").count("\n"), 0, "the scan worktree was left behind")

    def test_over_the_baseline_is_refused(self) -> None:
        before = self._remote_main()
        self._big_files(0, _baseline("OVERSIZED_PLATFORM_BASELINE") + 1)
        r = self._push()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("code-health refused", r.stderr)
        self.assertIn("files over 800 lines", r.stderr)
        self.assertEqual(self._remote_main(), before)
        self.assertEqual(_git(self.work, "worktree", "list").count("\n"), 0, "the scan worktree was left behind")

    def test_the_scan_reads_the_commit_not_the_working_tree(self) -> None:
        # An uncommitted file over the line (another session's edit) does not
        # count; a committed one does.
        self._big_files(0, _baseline("OVERSIZED_PLATFORM_BASELINE"))
        (self.work / "wip.go").write_text("package x\n" + "// line\n" * 801)
        _git(self.work, "add", "wip.go")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_an_open_window_refuses(self) -> None:
        before = self._remote_main()
        self._big_files(0, 1)
        self.window_rc.write_text("1")
        r = self._push()
        self.assertEqual(r.returncode, 1)
        self.assertIn("release window is open", r.stderr)
        self.assertEqual(self._remote_main(), before)
        self.window_rc.write_text("3")
        r = self._push()
        self.assertEqual(r.returncode, 1)
        self.assertIn("cannot read the release window", r.stderr)

    def test_not_a_fast_forward_is_refused(self) -> None:
        base = _git(self.work, "rev-parse", "HEAD")
        self._big_files(0, 1)
        ahead = _git(self.work, "rev-parse", "HEAD")
        self.assertEqual(self._push().returncode, 0)
        _git(self.work, "checkout", "--quiet", "--detach", base)
        self._big_files(5, 1)
        r = self._push()
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not fast-forward", r.stderr)
        self.assertEqual(self._remote_main(), ahead)

    def test_a_named_commit(self) -> None:
        self._big_files(0, 1)
        first = _git(self.work, "rev-parse", "HEAD")
        self._big_files(1, 1)
        r = self._push(first)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._remote_main(), first)
        self.assertNotEqual(self._push("no-such-ref").returncode, 0)


    # CUT-gitea-primary 0g: a repository on the primary list whose origin is
    # still GitHub is refused before anything is fetched or pushed.
    def test_a_primary_whose_origin_is_github_is_refused(self) -> None:
        listing = Path(self._tmp.name) / "gitea-primary.txt"
        listing.write_text("# fixture\nbifrost-platform\n")
        _git(self.work, "remote", "set-url", "origin", "git@github.com:weitingzhao/bifrost-platform.git")
        env = {**os.environ, "PUSH_MAIN_WINDOW": str(self.window), "PUSH_MAIN_PRIMARY_LIST": str(listing)}
        r = subprocess.run(["bash", str(PUSH_MAIN), str(self.work)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("has Gitea as its primary", r.stderr)

    # Review 243 A2, A5: the push addresses decide, in any spelling.
    def test_a_primary_whose_push_address_is_github_is_refused(self) -> None:
        listing = Path(self._tmp.name) / "gitea-primary.txt"
        listing.write_text("Bifrost-Platform\n")
        env = {**os.environ, "PUSH_MAIN_WINDOW": str(self.window), "PUSH_MAIN_PRIMARY_LIST": str(listing)}
        before = self._remote_main()
        for push_url in (
            "https://github.com/weitingzhao/bifrost-platform.git",
            "ssh://git@ssh.github.com:443/WeitingZhao/Bifrost-Platform.git/",
            "https://GITHUB.COM:443/weitingzhao/bifrost-platform",
        ):
            _git(self.work, "remote", "set-url", "--push", "origin", push_url)
            r = subprocess.run(["bash", str(PUSH_MAIN), str(self.work)], env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 1, push_url + r.stdout + r.stderr)
            self.assertIn("has Gitea as its primary", r.stderr)
        # a second push address beside a local one
        _git(self.work, "remote", "set-url", "--push", "origin", str(self.origin))
        _git(self.work, "remote", "set-url", "--add", "--push", "origin", "git@github.com:weitingzhao/bifrost-platform.git")
        r = subprocess.run(["bash", str(PUSH_MAIN), str(self.work)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        # pushInsteadOf rewrites the push address to GitHub
        _git(self.work, "config", "--unset-all", "remote.origin.pushurl")
        _git(self.work, "config", f"url.git@github.com:weitingzhao/.pushInsteadOf", str(self.origin.parent) + "/")
        r = subprocess.run(["bash", str(PUSH_MAIN), str(self.work)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self._remote_main(), before)

    def test_a_local_push_address_goes_on(self) -> None:
        listing = Path(self._tmp.name) / "gitea-primary.txt"
        listing.write_text("bifrost-platform\n")
        env = {**os.environ, "PUSH_MAIN_WINDOW": str(self.window), "PUSH_MAIN_PRIMARY_LIST": str(listing)}
        _git(self.work, "remote", "set-url", "--add", "--push", "origin", str(self.origin))
        _git(self.work, "config", "remote.origin.pushurl", str(self.origin))
        (self.work / "y.go").write_text("package y\n")
        _git(self.work, "add", "y.go")
        _git(self.work, "commit", "--quiet", "-m", "y")
        r = subprocess.run(["bash", str(PUSH_MAIN), str(self.work)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # Review 244 item 9: an address github_repo cannot read is not taken as "not GitHub".
    def test_a_push_address_outside_printable_ascii_is_refused(self) -> None:
        listing = Path(self._tmp.name) / "gitea-primary.txt"
        listing.write_text("bifrost-platform\n")
        env = {**os.environ, "PUSH_MAIN_WINDOW": str(self.window), "PUSH_MAIN_PRIMARY_LIST": str(listing)}
        before = self._remote_main()
        _git(self.work, "remote", "set-url", "--push", "origin", "https://ｇｉｔｈｕｂ.com/weitingzhao/bifrost-platform.git")
        r = subprocess.run(["bash", str(PUSH_MAIN), str(self.work)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("outside printable ASCII", r.stderr)
        self.assertEqual(self._remote_main(), before)

    def test_a_primary_whose_origin_is_gitea_goes_on(self) -> None:
        listing = Path(self._tmp.name) / "gitea-primary.txt"
        listing.write_text("bifrost-platform\n")
        env = {**os.environ, "PUSH_MAIN_WINDOW": str(self.window), "PUSH_MAIN_PRIMARY_LIST": str(listing)}
        (self.work / "x.go").write_text("package x\n")
        _git(self.work, "add", "x.go")
        _git(self.work, "commit", "--quiet", "-m", "x")
        head = _git(self.work, "rev-parse", "HEAD")
        r = subprocess.run(["bash", str(PUSH_MAIN), str(self.work)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._remote_main(), head)


class GithubRepo(unittest.TestCase):
    """push-main.sh github_repo and preflight.js githubRepoOf answer the same
    cases (review 244 item 9); the Node side is in agent-guard/test.js."""

    CASES = HERE.parent.parent / "agent-config" / "scripts" / "agent-guard" / "github-repo-cases.json"

    def test_the_shared_cases(self) -> None:
        text = PUSH_MAIN.read_text(encoding="utf-8")
        program = text.split("github_repo() {\n  python3 - \"$1\" <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        cases = json.loads(self.CASES.read_text(encoding="utf-8"))
        self.assertGreater(len(cases), 10)
        for address, want in cases:
            r = subprocess.run(["python3", "-c", program, address], capture_output=True, text=True, check=True)
            self.assertEqual(r.stdout.strip() or None, want, repr(address))


if __name__ == "__main__":
    unittest.main()
