"""push-main.sh against fixture repositories and the real code-health scan (TD-341).

No network, no cluster: origin is a bare repository in a temporary directory
and the release window is a stub script whose exit code the test sets.
"""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
