"""disk-guard.sh sweep, part 3 (W-31 4.6 S1; review 543): every layout level accepts only its
own entries (A1), nothing after the first check follows or trusts a path (A2), a Git
worktree above AGENT_WORK counts (A4), non-finite numbers are refused (C), run.done has no
grace period, and the layouts accept what the real tools write. lsof warnings (A3) are in
test_disk_guard_runs.py. Fixtures and SweepCase are in test_disk_guard.py.

    python3 -m pytest -q scripts/agent-host/test_disk_guard_hardening.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import disk_guard  # noqa: E402
import disk_guard_apply  # noqa: E402
from test_disk_guard import SweepCase, backdate, finished_review, go_build, go_mod, npm  # noqa: E402

REVIEW = "codex-review-*/go-cache\tgo-build\trun.done\treview cache"
H64 = "ab" * 32


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   check=True, capture_output=True)


class Layouts543(SweepCase):
    """A1: the open subtrees are closed."""

    def test_material_in_the_formerly_open_subtrees_stays(self) -> None:
        lane = self.aw / "lane-n"
        lane.mkdir()
        git(lane, "init", "-q")
        (lane / ".gitignore").write_text(".npm-cache/\n.npm-cache-2/\n")
        git(lane, "add", ".gitignore")
        git(lane, "commit", "-qm", "init")
        tmp_notes = npm(lane / ".npm-cache")  # an ignored root: Git calling it ignored proves nothing
        (tmp_notes / "_cacache" / "tmp" / "notes").write_text("mine\n")
        tmp_go = npm(lane / ".npm-cache-2")
        (tmp_go / "_cacache" / "tmp" / "draft.go").write_text("package d\n")

        def vcs(root: Path) -> None:
            (root / "cache" / "vcs" / H64).mkdir(parents=True)
            (root / "cache" / "vcs" / H64 / "notes").write_text("mine\n")

        def lookup(root: Path) -> None:
            d = root / "cache" / "download" / "sumdb" / "sum.golang.org" / "lookup"
            d.mkdir(parents=True)
            (d / "notes").write_text("mine\n")

        def tile(root: Path) -> None:
            d = root / "cache" / "download" / "sumdb" / "sum.golang.org" / "tile" / "8" / "0"
            d.mkdir(parents=True)
            (d / "notes").write_text("mine\n")

        def at_v(root: Path) -> None:
            (root / "cache" / "download" / "example.com" / "m" / "@v" / "notes.zip").write_text("mine\n")

        for n, extra in (("vcs", vcs), ("lookup", lookup), ("tile", tile), ("at-v", at_v)):
            root = go_mod(self.aw / f"mod-{n}")
            extra(root)
        exe = go_build(self.aw / "build-exe")
        d = exe / "ab" / ("ab" + "4" * 62 + "-d")
        d.mkdir()
        (d / "draft.go").write_text("package d\n")
        (d / "draft.go").chmod(0o755)
        trim = go_build(self.aw / "build-trim")
        (trim / "trim.txt").write_text("my notes, not a timestamp\n")
        for p in self.aw.iterdir():
            backdate(p, 60)
        self.register(
            "lane-n/.npm-cache\tnpm\tended\tlane finished (test)",
            "lane-n/.npm-cache-2\tnpm\tended\tlane finished (test)",
            *(f"mod-{n}\tgo-mod\tended\tx" for n in ("vcs", "lookup", "tile", "at-v")),
            "build-exe\tgo-build\tended\tx",
            "build-trim\tgo-build\tended\tx",
        )
        self.sweep("--apply")
        self.assertKept("lane-n/.npm-cache", "npm-tmp-not-empty")
        self.assertKept("lane-n/.npm-cache-2", "handwritten-file")
        self.assertKept("mod-vcs", "go-vcs-checkouts")
        self.assertKept("mod-lookup", "unknown-entry")
        self.assertKept("mod-tile", "unknown-entry")
        self.assertKept("mod-at-v", "unknown-entry")
        self.assertKept("build-exe", "handwritten-file")
        self.assertKept("build-trim", "unknown-entry")

    def test_a_real_sumdb_and_an_empty_tmp_go(self) -> None:
        root = go_mod(self.aw / "mod-sumdb")
        s = root / "cache" / "download" / "sumdb" / "sum.golang.org"
        (s / "lookup" / "example.com").mkdir(parents=True)
        (s / "lookup" / "example.com" / "m@v1.0.0").write_text("x")
        (s / "tile" / "8" / "0" / "x001").mkdir(parents=True)
        (s / "tile" / "8" / "0" / "x001" / "234").write_text("x")
        (s / "tile" / "8" / "0" / "005.p").mkdir()
        (s / "tile" / "8" / "0" / "005.p" / "17").write_text("x")
        (root / "cache" / "vcs").mkdir()
        (root / "cache" / "lock").write_text("")
        backdate(root, 60)
        self.register("mod-sumdb\tgo-mod\tended\tx")
        self.sweep("--apply")
        self.assertDeleted("mod-sumdb")

    def test_what_the_real_tools_write_is_accepted(self) -> None:
        go, npm_exe = shutil.which("go"), shutil.which("npm")
        if not go and not npm_exe:
            self.skipTest("no go and no npm")
        base = self.outside
        # NODE_USE_SYSTEM_CA makes node read the keychain, which a sandbox refuses (review 544)
        env = {k: v for k, v in self.env.items() if not k.startswith(("GO", "npm_config_")) and k != "NODE_USE_SYSTEM_CA"}
        env.update(HOME=str(base / "toolhome"), GOPATH=str(base / "gopath"), GOTOOLCHAIN="local", GOFLAGS="-mod=mod",
                   GOSUMDB="off", GONOSUMDB="*", GOPRIVATE="", GOENV="off", GOTELEMETRY="off")
        (base / "toolhome").mkdir()
        roots = []
        exe_dirs: list = []
        if go:
            review = self.aw / "codex-review-1"
            review.mkdir()
            gocache, gomod = review / "go-cache", review / ".gocache"
            proxy = base / "proxy" / "example.com" / "dep" / "@v"
            proxy.mkdir(parents=True)
            (proxy / "list").write_text("v1.0.0\n")
            (proxy / "v1.0.0.info").write_text('{"Version":"v1.0.0","Time":"2024-01-01T00:00:00Z"}\n')
            (proxy / "v1.0.0.mod").write_text("module example.com/dep\n")
            with zipfile.ZipFile(proxy / "v1.0.0.zip", "w") as z:
                z.writestr("example.com/dep@v1.0.0/go.mod", "module example.com/dep\n")
                z.writestr("example.com/dep@v1.0.0/dep.go", "package dep\n\nfunc N() int { return 1 }\n")
            prog = base / "prog"
            prog.mkdir()
            (prog / "go.mod").write_text("module example.com/probe\n\ngo 1.21\n\nrequire example.com/dep v1.0.0\n")
            (prog / "main.go").write_text('package main\n\nimport "example.com/dep"\n\nfunc main() { _ = dep.N() }\n')
            genv = {**env, "GOCACHE": str(gocache), "GOMODCACHE": str(gomod), "GOPROXY": f"file://{base / 'proxy'}"}
            r = subprocess.run([go, "run", "."], cwd=prog, env=genv, capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stderr)
            exe_dirs = [p for p in gocache.glob("*/*-d") if p.is_dir()]
            roots += ["codex-review-*/go-cache\tgo-build\trun.done\treal go run", "codex-review-*/.gocache\tgo-mod\trun.done\treal go mod download"]
            (review / "run.done").write_text("exit=0\n")
        if npm_exe:
            pkg = base / "pkg"
            pkg.mkdir()
            (pkg / "package.json").write_text(json.dumps({"name": "probe-pkg", "version": "1.0.0"}))
            (pkg / "index.js").write_text("module.exports = 1\n")
            nenv = {**env, "npm_config_cache": str(base / "pack-cache"), "npm_config_update_notifier": "false", "npm_config_audit": "false", "npm_config_fund": "false"}
            r = subprocess.run([npm_exe, "pack", "--silent"], cwd=pkg, env=nenv, capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stderr)
            review3 = self.aw / "codex-review-3"
            review3.mkdir()
            nenv["npm_config_cache"] = str(review3 / "cache")
            r = subprocess.run([npm_exe, "cache", "add", str(pkg / "probe-pkg-1.0.0.tgz")], cwd=pkg, env=nenv, capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stderr)
            r = subprocess.run([npm_exe, "cache", "verify"], cwd=pkg, env=nenv, capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((review3 / "cache" / "_cacache" / "_lastverified").is_file(), "npm cache verify wrote no _lastverified")
            roots.append("codex-review-*/cache\tnpm\trun.done\treal npm cache add and verify")
            (review3 / "run.done").write_text("exit=0\n")
        for review in self.aw.glob("codex-review-*"):
            for sub in review.iterdir():
                if sub.is_dir():
                    backdate(sub, 60)
            backdate(review / "run.done", 30)
        self.register(*roots)
        self.sweep("--apply")
        mine = [it for it in self.report()["items"] if it["source"] != "discovered"]
        want = (["codex-review-1/.gocache", "codex-review-1/go-cache"] if go else []) + (["codex-review-3/cache"] if npm_exe else [])
        self.assertEqual(sorted(it["path"] for it in mine), sorted(want), mine)
        for it in mine:
            self.assertEqual(it["action"], "deleted", it)
        if go:  # go run keeps its executable as <hash>-d/<name>: the layout knows it
            self.assertTrue(exe_dirs, "go run left no executable entry to check")


class Paths543(SweepCase):
    """A2: a parent swapped for a symlink, or a root swapped for another directory, between
    the checks; the sweep must neither follow it nor remove the wrong directory."""

    def test_parent_swapped_for_a_symlink_before_the_rename(self) -> None:
        finished_review(self.aw, "codex-review-1")
        decoy = finished_review(self.outside, "review-x")
        self.register(REVIEW)

        def swap(todo: list) -> None:
            os.rename(self.aw / "codex-review-1", self.aw / "codex-review-1-real")
            os.symlink(self.outside / "review-x", self.aw / "codex-review-1")

        disk_guard_apply.between_check_and_rename = swap
        self.sweep("--apply")
        it = self.item("codex-review-1/go-cache")
        self.assertEqual(it["action"], "keep", it)
        self.assertIn(it["reason"], ("symlink-in-path", "path-changed"), it)
        self.assertTrue((decoy / "00").is_dir(), "the sweep reached outside AGENT_WORK")
        self.assertTrue((self.aw / "codex-review-1-real" / "go-cache" / "00").is_dir())

    def test_parent_swapped_for_a_symlink_after_the_rename(self) -> None:
        finished_review(self.aw, "codex-review-2")
        self.register(REVIEW)
        decoys = []

        def swap(staged: list) -> None:
            for it, pfd, name, q in staged:
                os.rename(self.aw / "codex-review-2", self.aw / "codex-review-2-real")
                decoys.append(finished_review(self.outside, "review-y", sub=q))  # same new name, outside
                os.symlink(self.outside / "review-y", self.aw / "codex-review-2")

        disk_guard_apply.between_check_and_delete = swap
        self.sweep("--apply")
        it = self.item("codex-review-2/go-cache")
        self.assertEqual(it["action"], "keep", it)
        self.assertIn(it["reason"], ("recheck-symlink-in-path", "recheck-path-changed"), it)
        self.assertIn("renamed back", it["detail"])
        self.assertTrue((decoys[0] / "00").is_dir(), "the sweep removed a directory outside AGENT_WORK")
        self.assertTrue((self.aw / "codex-review-2-real" / "go-cache" / "00").is_dir(), "renamed back in the real parent")

    def test_root_swapped_for_another_directory_before_the_rename(self) -> None:
        finished_review(self.aw, "codex-review-3")
        self.register(REVIEW)

        def swap(todo: list) -> None:
            os.rename(self.aw / "codex-review-3" / "go-cache", self.aw / "codex-review-3" / "go-cache-first")
            backdate(go_build(self.aw / "codex-review-3" / "go-cache"), 60)

        disk_guard_apply.between_check_and_rename = swap
        self.sweep("--apply")
        self.assertKept("codex-review-3/go-cache", "path-changed")
        self.assertTrue((self.aw / "codex-review-3" / "go-cache" / "00").is_dir())
        self.assertTrue((self.aw / "codex-review-3" / "go-cache-first" / "00").is_dir())


class Git543(SweepCase):
    """A4: the Git worktree may sit above AGENT_WORK; a Git error on any call keeps."""

    def test_a_repository_above_agent_work(self) -> None:
        repo = self.outside / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        (repo / ".gitignore").write_text("scratch/codex-review-3/\n")
        git(repo, "add", ".gitignore")
        git(repo, "commit", "-qm", "init")
        self.aw = repo / "scratch"
        self.aw.mkdir()
        self.env["AGENT_WORK"] = str(self.aw)
        for n in (1, 2, 3):
            finished_review(self.aw, f"codex-review-{n}")
        git(repo, "add", "-f", "scratch/codex-review-1/go-cache/README")
        self.register(REVIEW)
        self.sweep("--apply")
        self.assertKept("codex-review-1/go-cache", "git-tracked-inside")
        self.assertKept("codex-review-2/go-cache", "git-not-ignored")
        self.assertDeleted("codex-review-3/go-cache")

    def test_a_failing_git_status_keeps(self) -> None:
        real = shutil.which("git")
        (self.bin / "git").write_text(f'#!/usr/bin/env bash\nfor a in "$@"; do [ "$a" = status ] && {{ echo "fatal: index file corrupt" >&2; exit 128; }}; done\nexec {real} "$@"\n')
        (self.bin / "git").chmod(0o755)
        lane = self.aw / "lane-s"
        lane.mkdir()
        git(lane, "init", "-q")
        (lane / ".gitignore").write_text(".gocache/\n")
        backdate(go_build(lane / ".gocache"), 60)
        self.register("lane-s/.gocache\tgo-build\tended\tx")
        self.sweep("--apply")
        it = self.assertKept("lane-s/.gocache", "git-error")
        self.assertIn("git status", it["detail"])


class Numbers543(SweepCase):
    """C: NaN and infinity are refused; run.done has no grace period."""

    def test_non_finite_numbers(self) -> None:
        def check(**kw: str) -> int:
            with contextlib.redirect_stdout(io.StringIO()):
                return disk_guard.main(["check"], {**self.env, **kw})

        for kw in ({"WARN_GB": "nan", "STOP_GB": "nan"}, {"WARN_GB": "inf"}, {"STOP_GB": "-inf"}, {"WARN_GB": "1e400"}):
            self.assertEqual(check(**kw), 2, kw)
        finished_review(self.aw, "codex-review-1")
        self.register("codex-review-1/go-cache\tgo-build\tcap=inf\tx", "codex-review-1/go-cache\tgo-build\tcap=nan\tx",
                      "codex-review-1/go-cache\tgo-build\tcap=1e400\tx")
        rc, out = self.sweep("--apply")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(self.report()["errors"]), 3, self.report()["errors"])
        self.env["LIFECYCLE_DONE_MIN_AGE_MIN"] = "nan"
        rc, out = self.sweep("--apply")
        self.assertEqual(rc, 4, out)

    def test_nothing_in_the_cache_may_be_newer_than_run_done(self) -> None:
        same = finished_review(self.aw, "codex-review-1")
        later = finished_review(self.aw, "codex-review-2")
        for review, cache, delta in (("codex-review-1", same, 0), ("codex-review-2", later, 5)):
            t = os.stat(self.aw / review / "run.done").st_mtime
            f = cache / "00" / ("00" + "1" * 62 + "-a")
            os.utime(f, (t + delta, t + delta))
        self.register(REVIEW)
        self.sweep("--apply")
        self.assertDeleted("codex-review-1/go-cache")
        self.assertKept("codex-review-2/go-cache", "written-after-run-done")


if __name__ == "__main__":
    unittest.main()
