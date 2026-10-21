"""push-main.sh against fixture repositories and the real code-health scan (TD-341).

No network, no cluster: origin is a bare repository in a temporary directory
and the release window is a stub script whose exit code the test sets. The
workspace of shared checkouts (TD-408) is a temporary directory too, empty
unless a case puts one there: no case touches the real workspace.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Git here reads no global or system config: the Owner's ~/.gitconfig holds the Gitea-primary
# batches' url.*.insteadOf rules (scripts/gitea/global-insteadof.sh), which rewrite the GitHub
# addresses these cases use to Gitea, and the cases would test that Mac instead of push-main.
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
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


def _commit(cwd: Path, subject: str, lineage: tuple[str, ...] = ("Change-Id", "Claude-Session")) -> str:
    """Commits what is staged, with the lineage trailers the hooks write (TD-400)."""
    trailers = {"Change-Id": "I" + secrets.token_hex(20), "Claude-Session": "local_" + secrets.token_hex(8)}
    body = "\n".join(f"{k}: {v}" for k, v in trailers.items() if k in lineage)
    args = ["commit", "--quiet", "-m", subject]
    if body:
        args += ["-m", body]
    _git(cwd, *args)
    return _git(cwd, "rev-parse", "HEAD")


class PushMain(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.shared_root = root / "workspace"
        self.shared_root.mkdir()
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
        _commit(self.work, f"files {start}..{start + n - 1}")

    def _env(self, **more: str) -> dict[str, str]:
        return {**os.environ, "PUSH_MAIN_WINDOW": str(self.window), "PUSH_MAIN_SHARED_ROOT": str(self.shared_root), **more}

    def _push(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(PUSH_MAIN), *[a for a in args if a.startswith("--")], str(cwd or self.work),
             *[a for a in args if not a.startswith("--")]],
            env=self._env(), capture_output=True, text=True,
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
        env = self._env(PUSH_MAIN_PRIMARY_LIST=str(listing))
        r = subprocess.run(["bash", str(PUSH_MAIN), str(self.work)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("has Gitea as its primary", r.stderr)

    # Review 243 A2, A5: the push addresses decide, in any spelling.
    def test_a_primary_whose_push_address_is_github_is_refused(self) -> None:
        listing = Path(self._tmp.name) / "gitea-primary.txt"
        listing.write_text("Bifrost-Platform\n")
        env = self._env(PUSH_MAIN_PRIMARY_LIST=str(listing))
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
        env = self._env(PUSH_MAIN_PRIMARY_LIST=str(listing))
        _git(self.work, "remote", "set-url", "--add", "--push", "origin", str(self.origin))
        _git(self.work, "config", "remote.origin.pushurl", str(self.origin))
        (self.work / "y.go").write_text("package y\n")
        _git(self.work, "add", "y.go")
        _commit(self.work, "y")
        r = subprocess.run(["bash", str(PUSH_MAIN), str(self.work)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # Review 244 item 9: an address github_repo cannot read is not taken as "not GitHub".
    def test_a_push_address_outside_printable_ascii_is_refused(self) -> None:
        listing = Path(self._tmp.name) / "gitea-primary.txt"
        listing.write_text("bifrost-platform\n")
        env = self._env(PUSH_MAIN_PRIMARY_LIST=str(listing))
        before = self._remote_main()
        _git(self.work, "remote", "set-url", "--push", "origin", "https://ｇｉｔｈｕｂ.com/weitingzhao/bifrost-platform.git")
        r = subprocess.run(["bash", str(PUSH_MAIN), str(self.work)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("outside printable ASCII", r.stderr)
        self.assertEqual(self._remote_main(), before)

    def test_a_primary_whose_origin_is_gitea_goes_on(self) -> None:
        listing = Path(self._tmp.name) / "gitea-primary.txt"
        listing.write_text("bifrost-platform\n")
        env = self._env(PUSH_MAIN_PRIMARY_LIST=str(listing))
        (self.work / "x.go").write_text("package x\n")
        _git(self.work, "add", "x.go")
        head = _commit(self.work, "x")
        r = subprocess.run(["bash", str(PUSH_MAIN), str(self.work)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._remote_main(), head)

    # TD-400: a commit without its lineage is refused, each one named; with
    # --no-lineage <reason> they are pushed and the reason is printed.
    def _unlined(self) -> tuple[str, str, str]:
        (self.work / "a.txt").write_text("a\n")
        _git(self.work, "add", "a.txt")
        lined = _commit(self.work, "lined")
        (self.work / "b.txt").write_text("b\n")
        _git(self.work, "add", "b.txt")
        no_change = _commit(self.work, "no change id", lineage=("Claude-Session",))
        (self.work / "c.txt").write_text("c\n")
        _git(self.work, "add", "c.txt")
        no_session = _commit(self.work, "no session", lineage=("Change-Id",))
        return lined, no_change, no_session

    def test_a_commit_without_lineage_is_refused(self) -> None:
        before = self._remote_main()
        lined, no_change, no_session = self._unlined()
        r = self._push()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("2 commit(s)", r.stderr)
        self.assertIn(f"{no_change[:7]}", r.stderr)
        self.assertIn("(no Change-Id) no change id", r.stderr)
        self.assertIn(f"{no_session[:7]}", r.stderr)
        self.assertIn("(no Claude-Session) no session", r.stderr)
        self.assertNotIn(lined[:7], r.stderr)
        self.assertEqual(self._remote_main(), before)
        # Neither trailer, on a commit whose message has no trailer block at all.
        _git(self.work, "reset", "--quiet", "--hard", before)
        (self.work / "d.txt").write_text("d\n")
        _git(self.work, "add", "d.txt")
        _commit(self.work, "bare", lineage=())
        r = self._push()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("(no Change-Id Claude-Session) bare", r.stderr)

    def test_no_lineage_pushes_and_says_why(self) -> None:
        _, no_change, no_session = self._unlined()
        for empty in ("", "  "):
            r = self._push("--no-lineage=" + empty)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("--no-lineage needs a reason", r.stderr)
        r = subprocess.run(["bash", str(PUSH_MAIN), "--no-lineage"], env=self._env(), capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        r = subprocess.run(["bash", str(PUSH_MAIN), str(self.work), "--no-lineage", "the Owner's own commits, made in his terminal"],
                           env=self._env(), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("--no-lineage: the Owner's own commits, made in his terminal", r.stdout)
        self.assertIn(no_change[:7], r.stdout)
        self.assertIn(no_session[:7], r.stdout)
        self.assertEqual(self._remote_main(), no_session)

    def test_lined_commits_need_no_override(self) -> None:
        (self.work / "e.txt").write_text("e\n")
        _git(self.work, "add", "e.txt")
        head = _commit(self.work, "lined")
        r = self._push("--no-lineage=not needed")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("every commit carries its lineage", r.stdout)
        self.assertEqual(self._remote_main(), head)

    # TD-408: the repo's shared checkout in the workspace follows main.
    def _shared(self) -> Path:
        shared = self.shared_root / "bifrost-platform"
        _git(self.shared_root, "clone", "--quiet", "--branch", "main", str(self.origin), str(shared))
        return shared

    def _change(self, name: str) -> str:
        (self.work / name).write_text(name + "\n")
        _git(self.work, "add", name)
        return _commit(self.work, name)

    def test_a_clean_shared_checkout_follows(self) -> None:
        shared = self._shared()
        (shared / "untracked.txt").write_text("another session's scratch\n")
        head = self._change("f.txt")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"shared checkout {shared}: fast-forwarded to {head}", r.stdout)
        self.assertEqual(_git(shared, "rev-parse", "HEAD"), head)
        self.assertEqual(_git(shared, "symbolic-ref", "--short", "HEAD"), "main")
        self.assertTrue((shared / "untracked.txt").exists())
        # Pushed again, main is already there; the checkout is too.
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("main is already", r.stdout)
        self.assertIn(f"shared checkout {shared}: already at {head}", r.stdout)

    def test_a_lane_worktree_of_the_shared_checkout(self) -> None:
        # The lanes' topology: a worktree of the shared checkout pushes; the
        # shared checkout, on main, is fast-forwarded without a fetch.
        shared = self._shared()
        lane = Path(self._tmp.name) / "lanes" / "bifrost-platform"
        _git(shared, "worktree", "add", "--quiet", "-b", "w31/lane", str(lane))
        (lane / "g.txt").write_text("g\n")
        _git(lane, "add", "g.txt")
        head = _commit(lane, "g")
        r = self._push(cwd=lane)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._remote_main(), head)
        self.assertEqual(_git(shared, "rev-parse", "HEAD"), head)
        self.assertIn("fast-forwarded", r.stdout)

    def test_a_dirty_shared_checkout_is_left_and_named(self) -> None:
        shared = self._shared()
        before = _git(shared, "rev-parse", "HEAD")
        (shared / "README.md").write_text("another session's edit\n")
        head = self._change("h.txt")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._remote_main(), head)
        self.assertIn(f"shared checkout {shared}: has tracked changes; left as it is at {before[:12]}", r.stdout)
        self.assertEqual(_git(shared, "rev-parse", "HEAD"), before)
        self.assertEqual((shared / "README.md").read_text(), "another session's edit\n")

    def test_a_shared_checkout_that_cannot_follow_is_left(self) -> None:
        shared = self._shared()
        before = _git(shared, "rev-parse", "HEAD")
        # Not on main.
        _git(shared, "checkout", "--quiet", "-b", "other")
        self._change("i.txt")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"shared checkout {shared}: not on main; left as it is", r.stdout)
        self.assertEqual(_git(shared, "rev-parse", "HEAD"), before)
        # On main with a commit of its own that is not on main.
        _git(shared, "checkout", "--quiet", "main")
        (shared / "local.txt").write_text("local\n")
        _git(shared, "add", "local.txt")
        local = _commit(shared, "a local commit")
        self._change("j.txt")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("has commits that are not on main; left as it is", r.stdout)
        self.assertEqual(_git(shared, "rev-parse", "HEAD"), local)
        # The fast-forward itself fails (an untracked file the push adds): the
        # push still succeeds and says why the checkout did not follow.
        _git(shared, "reset", "--quiet", "--hard", before)
        (shared / "k.txt").write_text("in the way\n")
        head = self._change("k.txt")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._remote_main(), head)
        self.assertIn(f"shared checkout {shared}: the fast-forward failed; left as it is at {before[:12]}", r.stdout)
        self.assertEqual(_git(shared, "rev-parse", "HEAD"), before)
        # Another origin.
        _git(shared, "remote", "set-url", "origin", "https://example.invalid/bifrost-platform.git")
        self._change("l.txt")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"shared checkout {shared}: its origin is not {self.origin}; left as it is", r.stdout)

    def test_the_shared_checkout_is_the_push_source(self) -> None:
        # Pushing from the shared checkout itself (the coordinator in infra's):
        # it is not touched, and it says so.
        self.shared_root = self.work.parent
        head = self._change("m.txt")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"shared checkout {self.work}: is the checkout pushed from, at {head}", r.stdout)
        self.assertEqual(_git(self.work, "rev-parse", "HEAD"), head)
        # Its HEAD is past the commit pushed: left as it is.
        first = head
        self._change("n.txt")
        r = self._push(first)
        self.assertIn("main is already", r.stdout)
        self.assertIn("is the checkout pushed from; left as it is", r.stdout)

    def test_no_shared_checkout(self) -> None:
        self._change("o.txt")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"shared checkout {self.shared_root / 'bifrost-platform'}: none there; nothing followed", r.stdout)


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
