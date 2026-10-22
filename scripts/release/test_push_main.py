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
import shutil
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
SCAN = HERE.parent.parent / "agent-config" / "scripts" / "code-health" / "scan.sh"
REAL_GIT = shutil.which("git")
# W-31 3.4 ②: push-main reads the commit's ci-* runs with kubectl. This one answers for every
# commit of every git repository under FAKE_CI_DIR (any checkout a case pushes from), in the
# state FAKE_CI_STATE says (True, False, Unknown; none: no run;
# error: kubectl fails; later: Unknown at the first read, then True), as bifrost-ci-platform runs
# of FAKE_CI_REPO; the other CI pipelines have none.
FAKE_KUBECTL = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
state = os.environ.get("FAKE_CI_STATE", "True")
log = os.environ.get("FAKE_CI_LOG")
if log:
    with open(log, "a") as f:
        f.write(" ".join(sys.argv[1:]) + "\n")
if state == "error":
    print("The connection to the server localhost:8080 was refused", file=sys.stderr)
    sys.exit(1)
if state == "later":
    seen = os.environ["FAKE_CI_DIR"] + "/ci-reads"
    n = int(open(seen).read()) if os.path.exists(seen) else 0
    open(seen, "w").write(str(n + 1))
    state = "Unknown" if n < 3 else "True"
pipeline = sys.argv[sys.argv.index("-l") + 1].split("=", 1)[1]
items = []
if pipeline == "bifrost-ci-platform" and state != "none":
    shas = set()
    for dirpath, dirnames, _ in os.walk(os.environ["FAKE_CI_DIR"]):
        if os.path.basename(dirpath) == ".git" or dirpath.endswith(".git") and "objects" in dirnames:
            shas |= set(subprocess.run(["git", "--git-dir", dirpath, "rev-list", "--all"],
                                       capture_output=True, text=True).stdout.split())
            dirnames[:] = []
    for sha in shas:
        items.append({"metadata": {"labels": {"tekton.dev/pipeline": pipeline,
                                              "bifrost.io/repo": os.environ.get("FAKE_CI_REPO", "bifrost-platform")}},
                      "spec": {"params": [{"name": "revision", "value": sha}]},
                      "status": {"conditions": [{"type": "Succeeded", "status": state}]}})
print(json.dumps({"items": items}))
'''


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


class _Fixture(unittest.TestCase):
    """The fixture repositories and helpers; the test classes below share it."""

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
        self.kubectl = root / "kubectl-ci"
        self.kubectl.write_text(FAKE_KUBECTL)
        self.kubectl.chmod(0o755)
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
        return {**os.environ, "PUSH_MAIN_WINDOW": str(self.window), "PUSH_MAIN_SHARED_ROOT": str(self.shared_root),
                "PUSH_MAIN_KUBECTL": str(self.kubectl), "FAKE_CI_DIR": self._tmp.name, "PUSH_MAIN_CI_POLL": "0",
                "PUSH_MAIN_CI_WAIT": "5", **more}

    def _push(self, *args: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(PUSH_MAIN), *[a for a in args if a.startswith("--")], str(cwd or self.work),
             *[a for a in args if not a.startswith("--")]],
            env=env or self._env(), capture_output=True, text=True,
        )

    def _wrapped_git(self, cases: str) -> dict[str, str]:
        """An environment whose git is a wrapper running the shell case
        branches given (matched against "$*") before the real git."""
        bin_dir = Path(self._tmp.name) / "bin"
        bin_dir.mkdir(exist_ok=True)
        wrapper = bin_dir / "git"
        wrapper.write_text(f'#!/bin/sh\nREAL="{REAL_GIT}"\ncase "$*" in\n{cases}\nesac\nexec "$REAL" "$@"\n')
        wrapper.chmod(0o755)
        return self._env(PATH=f"{bin_dir}:{os.environ['PATH']}")

    def _remote_main(self) -> str:
        return _git(self.origin, "rev-parse", "main")


class PushMain(_Fixture):
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

    # Review td400-1 B1: a git log that fails refuses the push; it does not
    # read as a range with no commit.
    def test_a_trailer_read_that_fails_refuses(self) -> None:
        before = self._remote_main()
        (self.work / "p.txt").write_text("p\n")
        _git(self.work, "add", "p.txt")
        _commit(self.work, "unlined", lineage=())
        env = self._wrapped_git('  *"trailers:key=Change-Id"*) echo "fatal: injected" >&2; exit 128 ;;')
        r = self._push(env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("cannot read the trailers", r.stderr)
        self.assertEqual(self._remote_main(), before)

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
        # main is already the commit and the shared checkout fell behind: it
        # follows too.
        _git(shared, "reset", "--quiet", "--hard", "HEAD~1")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("main is already", r.stdout)
        self.assertIn(f"shared checkout {shared}: fast-forwarded to {head}", r.stdout)
        self.assertEqual(_git(shared, "rev-parse", "HEAD"), head)

    # Review td400-1 A1: an ignored file the commit adds is not replaced.
    def test_an_ignored_file_the_commit_adds_is_kept(self) -> None:
        shared = self._shared()
        before = _git(shared, "rev-parse", "HEAD")
        (shared / ".git" / "info" / "exclude").write_text("secret.txt\n")
        (shared / "secret.txt").write_text("a session's own\n")
        (self.work / "secret.txt").write_text("the commit's\n")
        _git(self.work, "add", "secret.txt")
        head = _commit(self.work, "secret")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._remote_main(), head)
        self.assertIn(f"shared checkout {shared}: the fast-forward failed; left as it is at {before[:12]}", r.stdout)
        self.assertEqual(_git(shared, "rev-parse", "HEAD"), before)
        self.assertEqual((shared / "secret.txt").read_text(), "a session's own\n")

    # Review td400-1 B2: following runs none of the shared checkout's hooks
    # (one could wait on anything after the push has happened).
    def test_following_runs_no_hook(self) -> None:
        shared = self._shared()
        marker = Path(self._tmp.name) / "hook-ran"
        hooks = shared / ".git" / "hooks"
        for name in ("post-merge", "reference-transaction", "post-checkout"):
            (hooks / name).write_text(f"#!/bin/sh\necho {name} >> '{marker}'\n")
            (hooks / name).chmod(0o755)
        head = self._change("s.txt")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(_git(shared, "rev-parse", "HEAD"), head)
        self.assertFalse(marker.exists(), marker.read_text() if marker.exists() else "")

    # Review td400-1 A2: the checks are made after the fetch, so a branch
    # switched meanwhile is not the one moved.
    def test_a_branch_switched_during_the_fetch_is_not_moved(self) -> None:
        shared = self._shared()
        before = _git(shared, "rev-parse", "HEAD")
        env = self._wrapped_git(
            f'  *"-C {shared} "*fetch*) "$REAL" "$@"; rc=$?; "$REAL" -C "{shared}" checkout --quiet -b other; exit $rc ;;')
        head = self._change("q.txt")
        r = self._push(env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._remote_main(), head)
        self.assertIn(f"shared checkout {shared}: not on main; left as it is", r.stdout)
        self.assertEqual(_git(shared, "symbolic-ref", "--short", "HEAD"), "other")
        self.assertEqual(_git(shared, "rev-parse", "other"), before)
        self.assertEqual(_git(shared, "rev-parse", "main"), before)

    # Without PUSH_MAIN_SHARED_ROOT the workspace is the parent of the infra
    # repository's main worktree, also when the script runs from a lane's
    # worktree of it.
    def test_the_default_workspace_from_a_lane_of_infra(self) -> None:
        ws = Path(self._tmp.name) / "ws"
        infra = ws / "bifrost-trade-infra"
        (infra / "scripts" / "release").mkdir(parents=True)
        shutil.copy(PUSH_MAIN, infra / "scripts" / "release" / "push-main.sh")
        shutil.copy(HERE / "ci_gate.py", infra / "scripts" / "release" / "ci_gate.py")  # its CI step (W-31 3.4 ②)
        _git(ws, "init", "--quiet", "--initial-branch=main", str(infra))
        _git(infra, "add", "scripts")
        _commit(infra, "infra")
        lane = Path(self._tmp.name) / "lanes" / "bifrost-trade-infra"
        _git(infra, "worktree", "add", "--quiet", "-b", "w31/lane", str(lane))
        shared = ws / "bifrost-platform"
        _git(ws, "clone", "--quiet", "--branch", "main", str(self.origin), str(shared))
        head = self._change("r.txt")
        env = {k: v for k, v in self._env(PUSH_MAIN_SCAN=str(SCAN)).items() if k != "PUSH_MAIN_SHARED_ROOT"}
        r = subprocess.run(["bash", str(lane / "scripts" / "release" / "push-main.sh"), str(self.work)],
                           env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"shared checkout {shared.resolve()}: fast-forwarded to {head}", r.stdout)
        self.assertEqual(_git(shared, "rev-parse", "HEAD"), head)

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
        # Reached through another spelling of its path: still the source.
        alias = Path(self._tmp.name) / "alias"
        alias.symlink_to(self.work.parent)
        self.shared_root = alias
        r = self._push(first)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("is the checkout pushed from; left as it is", r.stdout)

    def test_no_shared_checkout(self) -> None:
        self._change("o.txt")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"shared checkout {self.shared_root / 'bifrost-platform'}: none there; nothing followed", r.stdout)


    # TD-413: the repo's fast tests run on the clean worktree of the commit,
    # and a failure refuses the push; --skip-tests <reason> skips them.
    def _infra(self) -> tuple[Path, Path]:
        """A fixture bifrost-trade-infra whose main has one passing test."""
        root = Path(self._tmp.name)
        origin = root / "remote" / "bifrost-trade-infra.git"
        _git(root, "init", "--quiet", "--bare", "--initial-branch=main", str(origin))
        work = root / "work" / "bifrost-trade-infra"
        _git(root, "clone", "--quiet", str(origin), str(work))
        _git(work, "checkout", "--quiet", "-b", "main")
        (work / "scripts" / "release").mkdir(parents=True)
        (work / "scripts" / "release" / "test_ok.py").write_text("def test_ok():\n    assert True\n")
        _git(work, "add", "scripts")
        _commit(work, "init")
        _git(work, "push", "--quiet", "origin", "main")
        return origin, work

    def _add(self, work: Path, rel: str, text: str) -> str:
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text)
        _git(work, "add", rel)
        return _commit(work, rel)

    def test_a_commit_whose_infra_test_fails_is_refused(self) -> None:
        origin, work = self._infra()
        before = _git(origin, "rev-parse", "main")
        self._add(work, "scripts/agentrt/test_planted.py", "def test_planted_failure():\n    assert 1 == 2\n")
        r = self._push(cwd=work)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("tests of bifrost-trade-infra: python3 -m pytest -q scripts/release scripts/agentrt", r.stdout)
        self.assertIn("test_planted_failure", r.stdout)
        self.assertIn("the tests of bifrost-trade-infra failed on", r.stderr)
        self.assertEqual(_git(origin, "rev-parse", "main"), before)
        self.assertEqual(_git(work, "worktree", "list").count("\n"), 0, "the test worktree was left behind")

    def test_skip_tests_pushes_and_says_why(self) -> None:
        origin, work = self._infra()
        head = self._add(work, "scripts/agentrt/test_planted.py", "def test_planted_failure():\n    assert 1 == 2\n")
        for empty in ("", " "):
            r = self._push("--skip-tests=" + empty, cwd=work)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("--skip-tests needs a reason", r.stderr)
        r = self._push("--skip-tests=the Owner's hotfix; the suite runs after", cwd=work)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("--skip-tests: the Owner's hotfix; the suite runs after; the tests of bifrost-trade-infra were not run", r.stdout)
        self.assertNotIn("test_planted_failure", r.stdout)
        self.assertEqual(_git(origin, "rev-parse", "main"), head)

    def test_passing_infra_tests_push_and_the_working_tree_does_not_count(self) -> None:
        origin, work = self._infra()
        head = self._add(work, "scripts/agent-host/test_fine.py", "def test_fine():\n    assert 2 == 2\n")
        # Another session's uncommitted failing test is not the commit's.
        (work / "scripts" / "release" / "test_wip.py").write_text("def test_wip():\n    assert False\n")
        r = self._push(cwd=work)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("the tests of bifrost-trade-infra passed", r.stdout)
        self.assertNotIn("test_wip", r.stdout)
        self.assertEqual(_git(origin, "rev-parse", "main"), head)

    # TD-413 docs: a push that changes only Markdown runs none of the tests
    # but the document guards (the exam-key scan), and says so without a
    # reason; one file that is not Markdown beside them runs every test.
    def _infra_red(self) -> tuple[Path, Path]:
        """The fixture infra with a test red on main and an exam-key guard."""
        origin, work = self._infra()
        self._add(work, "scripts/release/test_red.py", "def test_red_on_main():\n    assert False\n")
        self._add(work, "scripts/agentrt/test_no_exam_keys.py",
                  "import pathlib\n\n\ndef test_no_exam_key_in_a_document():\n"
                  "    for p in pathlib.Path('.').rglob('*.md'):\n"
                  "        assert 'EXAMKEY' not in p.read_text(), p\n")
        _git(work, "push", "--quiet", "origin", "main")
        return origin, work

    def test_only_documentation_runs_only_the_document_guards(self) -> None:
        origin, work = self._infra_red()
        self._add(work, "README.md", "docs\n")
        head = self._add(work, "notes/plan.md", "a plan\n")
        r = self._push(cwd=work)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("only documentation changed: README.md, notes/plan.md\n", r.stdout)
        self.assertIn("of the tests of bifrost-trade-infra only the document guards run", r.stdout)
        self.assertIn("tests of bifrost-trade-infra: python3 -m pytest -q scripts/agentrt/test_no_exam_keys.py", r.stdout)
        self.assertNotIn("test_red_on_main", r.stdout)
        self.assertEqual(_git(origin, "rev-parse", "main"), head)
        # A document an exam key went into is refused all the same.
        self._add(work, "notes/keys.md", "EXAMKEY\n")
        r = self._push(cwd=work)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("test_no_exam_key_in_a_document", r.stdout)
        self.assertIn("the tests of bifrost-trade-infra failed", r.stderr)
        self.assertEqual(_git(origin, "rev-parse", "main"), head)

    def test_a_file_beside_the_documents_runs_every_test(self) -> None:
        origin, work = self._infra_red()
        before = _git(origin, "rev-parse", "main")
        self._add(work, "README.md", "docs\n")
        self._add(work, "scripts/helper.py", "X = 1\n")
        r = self._push(cwd=work)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertNotIn("only documentation changed", r.stdout)
        self.assertIn("tests of bifrost-trade-infra: python3 -m pytest -q scripts/release scripts/agentrt", r.stdout)
        self.assertIn("test_red_on_main", r.stdout)
        self.assertEqual(_git(origin, "rev-parse", "main"), before)

    def test_a_rename_to_markdown_is_not_documentation_only(self) -> None:
        origin, work = self._infra_red()
        before = _git(origin, "rev-parse", "main")
        (work / "notes").mkdir()
        _git(work, "mv", "scripts/release/test_ok.py", "notes/test_ok.md")
        _commit(work, "a test becomes a note")
        r = self._push(cwd=work)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertNotIn("only documentation changed", r.stdout)
        self.assertIn("test_red_on_main", r.stdout)
        self.assertEqual(_git(origin, "rev-parse", "main"), before)

    # Review td413docs-1: what is named .md but is no plain Markdown file
    # runs every test (A1); a submodule the local diff config would hide is
    # read all the same (A2); a document whose path git would quote is still
    # a document (B1); a document guard that is not there runs every test
    # instead of none (B2).
    def test_a_md_that_is_not_a_plain_document_runs_every_test(self) -> None:
        origin, work = self._infra_red()
        before = _git(origin, "rev-parse", "main")
        cases = {
            "a gitlink named .md": lambda: _git(work, "update-index", "--add", "--cacheinfo", f"160000,{before},module.md"),
            "a symlink named .md": lambda: (os.symlink("scripts/release/test_ok.py", work / "linked.md"), _git(work, "add", "linked.md")),
            "an executable .md": lambda: ((work / "run.md").write_text("x\n"), _git(work, "add", "--chmod=+x", "run.md")),
        }
        for name, make in cases.items():
            _git(work, "reset", "--quiet", "--hard", before)
            make()
            _commit(work, name)
            r = self._push(cwd=work)
            self.assertEqual(r.returncode, 1, name + r.stdout + r.stderr)
            self.assertNotIn("only documentation changed", r.stdout, name)
            self.assertIn("test_red_on_main", r.stdout, name)
            self.assertEqual(_git(origin, "rev-parse", "main"), before, name)
        # A .md whose mode changes to executable is no document change either.
        _git(work, "reset", "--quiet", "--hard", before)
        head = self._add(work, "plain.md", "plain\n")
        _git(work, "push", "--quiet", "origin", "main")
        _git(work, "update-index", "--chmod=+x", "plain.md")
        _commit(work, "chmod")
        r = self._push(cwd=work)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertNotIn("only documentation changed", r.stdout)
        self.assertEqual(_git(origin, "rev-parse", "main"), head)

    def test_a_submodule_hidden_by_the_diff_config_is_read(self) -> None:
        origin, work = self._infra_red()
        before = _git(origin, "rev-parse", "main")
        _git(work, "config", "diff.ignoreSubmodules", "all")
        _git(work, "update-index", "--add", "--cacheinfo", f"160000,{before},module")
        (work / "README.md").write_text("docs\n")
        _git(work, "add", "README.md")
        _commit(work, "a submodule beside a document")
        r = self._push(cwd=work)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertNotIn("only documentation changed", r.stdout)
        self.assertIn("test_red_on_main", r.stdout)
        self.assertEqual(_git(origin, "rev-parse", "main"), before)

    def test_a_document_git_would_quote_is_a_document(self) -> None:
        origin, work = self._infra_red()
        self._add(work, "notes/中文.md", "笔记\n")
        head = self._add(work, "notes/a\nb.md", "two lines in a name\n")
        r = self._push(cwd=work)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("only documentation changed: notes/a\\nb.md, notes/中文.md\n", r.stdout)
        self.assertNotIn("test_red_on_main", r.stdout)
        self.assertEqual(_git(origin, "rev-parse", "main"), head)

    def test_a_missing_document_guard_runs_every_test(self) -> None:
        origin, work = self._infra()
        self._add(work, "scripts/release/test_red.py", "def test_red_on_main():\n    assert False\n")
        _git(work, "push", "--quiet", "origin", "main")
        before = _git(origin, "rev-parse", "main")
        self._add(work, "README.md", "docs\n")
        r = self._push(cwd=work)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("the document guard scripts/agentrt/test_no_exam_keys.py is not in", r.stdout)
        self.assertIn("test_red_on_main", r.stdout)
        self.assertNotIn("the tests of bifrost-trade-infra passed", r.stdout)
        self.assertEqual(_git(origin, "rev-parse", "main"), before)

    def test_platform_documentation_runs_no_test(self) -> None:
        self._go_module()
        for i in range(7):
            self._add(self.work, f"docs/n{i}.md", f"note {i}\n")
        head = _git(self.work, "rev-parse", "HEAD")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("only documentation changed: docs/n0.md, docs/n1.md, docs/n2.md, docs/n3.md, docs/n4.md, and 2 more; "
                      "the tests of bifrost-platform were not run", r.stdout)
        self.assertNotIn("go vet", r.stdout)
        self.assertNotIn("no fast tests", r.stdout)
        self.assertEqual(self._remote_main(), head)

    def _go_module(self) -> None:
        """The fixture platform gets api/: package a (passing) and package
        b, whose test fails, both on main."""
        api = self.work / "api"
        (api / "internal" / "a").mkdir(parents=True)
        (api / "internal" / "b").mkdir(parents=True)
        (api / "go.mod").write_text("module example.invalid/api\n\ngo 1.21\n")
        (api / "internal" / "a" / "a.go").write_text("package a\n\nfunc A() int { return 1 }\n")
        (api / "internal" / "a" / "a_test.go").write_text(
            'package a\n\nimport "testing"\n\nfunc TestA(t *testing.T) {\n\tif A() != 1 {\n\t\tt.Fatal("A")\n\t}\n}\n')
        (api / "internal" / "b" / "b.go").write_text("package b\n\nfunc B() int { return 2 }\n")
        (api / "internal" / "b" / "b_test.go").write_text(
            'package b\n\nimport "testing"\n\nfunc TestB(t *testing.T) {\n\tif B() != 3 {\n\t\tt.Fatal("planted: B is not 3")\n\t}\n}\n')
        _git(self.work, "add", "api")
        _commit(self.work, "api")
        _git(self.work, "push", "--quiet", "origin", "main")

    def test_platform_tests_the_packages_it_touches(self) -> None:
        self._go_module()
        # Package a touched: vet and a's tests pass; b, red on main, is not run.
        head = self._add(self.work, "api/internal/a/a2.go", "package a\n\nfunc A2() int { return A() + 1 }\n")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("tests of bifrost-platform: go vet ./...", r.stdout)
        self.assertIn("tests of bifrost-platform: go test ./internal/a/", r.stdout)
        self.assertNotIn("internal/b", r.stdout)
        self.assertEqual(self._remote_main(), head)
        # Package b touched: its failing test refuses the push.
        self._add(self.work, "api/internal/b/b2.go", "package b\n\nfunc B2() int { return B() }\n")
        r = self._push()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("go test ./internal/b/", r.stdout)
        self.assertIn("planted: B is not 3", r.stdout)
        self.assertIn("the tests of bifrost-platform failed", r.stderr)
        self.assertEqual(self._remote_main(), head)

    # Review td413-1 B1: a touched directory whose files a build constraint
    # all excludes is no package of this build: not tested, not refused.
    def test_a_package_excluded_by_build_constraints_is_not_tested(self) -> None:
        self._go_module()
        head = self._add(self.work, "api/internal/optional/optional.go",
                         "//go:build review_optional\n\npackage optional\n\nfunc O() int { return 0 }\n")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no Go package of bifrost-platform is touched; go vet only", r.stdout)
        self.assertEqual(self._remote_main(), head)
        # Its testdata is no package either.
        head = self._add(self.work, "api/internal/a/testdata/fixture.go", "package broken(\n")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._remote_main(), head)

    def test_platform_vet_refuses(self) -> None:
        self._go_module()
        before = self._remote_main()
        self._add(self.work, "api/internal/a/bad.go",
                  'package a\n\nimport "fmt"\n\nfunc Bad() string { return fmt.Sprintf("%d", "not a number") }\n')
        r = self._push()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("go vet", r.stdout + r.stderr)
        self.assertIn("the tests of bifrost-platform failed", r.stderr)
        self.assertEqual(self._remote_main(), before)

    def test_a_repo_without_fast_tests(self) -> None:
        # The fixture platform without api/ says so and pushes; a repo with no
        # test set says it has none.
        head = self._change("t.txt")
        r = self._push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("bifrost-platform has no api/go.mod; no tests run", r.stdout)
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


class PushMainCI(_Fixture):
    """W-31 3.4 ② (Owner 2026-10-21 「D3 A」): a commit of a repo with its own CI reaches main
    only with a Succeeded ci-* run of that exact commit."""

    def _code_change(self) -> str:
        (self.work / "x.go").write_text("package x\n")
        _git(self.work, "add", "x.go")
        return _commit(self.work, "a change")

    def test_a_green_commit_is_pushed_and_said(self) -> None:
        head = self._code_change()
        r = self._push(env=self._env(FAKE_CI_STATE="True"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("bifrost-platform " + head + " ci=succeeded", r.stdout)
        self.assertEqual(self._remote_main(), head)

    def test_a_red_commit_is_refused(self) -> None:
        before = self._remote_main()
        self._code_change()
        r = self._push(env=self._env(FAKE_CI_STATE="False"))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("CI failed", r.stderr)
        self.assertIn("--allow-red", r.stderr)
        self.assertEqual(self._remote_main(), before)

    def test_a_commit_without_finished_ci_is_refused_after_the_wait(self) -> None:
        before = self._remote_main()
        self._code_change()
        for state in ("Unknown", "none"):
            r = self._push(env=self._env(FAKE_CI_STATE=state, PUSH_MAIN_CI_WAIT="0"))
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("has not succeeded within 0s", r.stderr)
            self.assertIn("git push origin <branch>", r.stderr)
            self.assertEqual(self._remote_main(), before)

    def test_ci_that_turns_green_while_waited_for_is_pushed(self) -> None:
        head = self._code_change()
        r = self._push(env=self._env(FAKE_CI_STATE="later", PUSH_MAIN_CI_WAIT="60"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("has not finished, or has not started", r.stdout)
        self.assertEqual(self._remote_main(), head)

    def test_unreadable_runs_refuse(self) -> None:
        before = self._remote_main()
        self._code_change()
        r = self._push(env=self._env(FAKE_CI_STATE="error"))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("cannot read the CI runs in cicd", r.stderr)
        self.assertEqual(self._remote_main(), before)

    def test_allow_red_pushes_and_says_why(self) -> None:
        head = self._code_change()
        log = Path(self._tmp.name) / "ci.log"
        r = self._push("--allow-red=the Owner's hotfix", env=self._env(FAKE_CI_STATE="False", FAKE_CI_LOG=str(log)))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--allow-red: the Owner's hotfix", r.stdout)
        self.assertEqual(self._remote_main(), head)
        self.assertFalse(log.exists(), "the runs were read though CI was not required")

    def test_allow_red_needs_a_reason(self) -> None:
        self._code_change()
        r = self._push("--allow-red= ", env=self._env(FAKE_CI_STATE="True"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--allow-red needs a reason", r.stderr)

    def test_a_documentation_push_is_not_checked(self) -> None:
        (self.work / "NOTES.md").write_text("notes\n")
        _git(self.work, "add", "NOTES.md")
        head = _commit(self.work, "notes")
        r = self._push(env=self._env(FAKE_CI_STATE="False"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("only documentation changed; no CI checked", r.stdout)
        self.assertEqual(self._remote_main(), head)

    def test_the_runs_are_read_as_release_sh_reads_them(self) -> None:
        self._code_change()
        log = Path(self._tmp.name) / "ci.log"
        r = self._push(env=self._env(FAKE_CI_STATE="True", FAKE_CI_LOG=str(log)))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(log.read_text().splitlines(), [
            "-n cicd get pipelineruns -l tekton.dev/pipeline=" + p + " -o json --request-timeout=20s"
            for p in ("bifrost-ci-python", "bifrost-ci-frontend", "bifrost-ci-platform")
        ])

    def test_a_repo_without_ci_of_its_own_is_not_checked(self) -> None:
        root = Path(self._tmp.name)
        origin = root / "remote" / "bifrost-ui.git"
        _git(root, "init", "--quiet", "--bare", "--initial-branch=main", str(origin))
        work = root / "work" / "bifrost-ui"
        _git(root, "clone", "--quiet", str(origin), str(work))
        _git(work, "checkout", "--quiet", "-b", "main")
        (work / "README.md").write_text("ui\n")
        _git(work, "add", "README.md")
        _git(work, "commit", "--quiet", "-m", "init")
        _git(work, "push", "--quiet", "origin", "main")
        (work / "a.ts").write_text("export const a = 1\n")
        _git(work, "add", "a.ts")
        head = _commit(work, "ui change")
        r = self._push(cwd=work, env=self._env(FAKE_CI_STATE="False"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("bifrost-ui has no CI of its own; no CI checked", r.stdout)
        self.assertEqual(_git(origin, "rev-parse", "main"), head)

    def test_a_missing_ci_gate_refuses_instead_of_waiting(self) -> None:
        lone = Path(self._tmp.name) / "lone"
        lone.mkdir()
        shutil.copy(PUSH_MAIN, lone / "push-main.sh")
        self._code_change()
        r = subprocess.run(["bash", str(lone / "push-main.sh"), str(self.work)],
                           env=self._env(FAKE_CI_STATE="True", PUSH_MAIN_SCAN=str(SCAN), PUSH_MAIN_CI_WAIT="600"),
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("ci_gate.py is not beside push-main.sh", r.stderr)

