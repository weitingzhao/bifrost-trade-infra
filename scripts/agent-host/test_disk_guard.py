"""disk-guard.sh sweep (W-31 4.6 S1; CUT-lifecycle-2026-10-24.md §4.1 and the S1 row of §5;
review 539 F1–F4). Every test seeds a throwaway AGENT_WORK in a temp dir and runs the sweep
in-process against it; nothing outside the temp dir is read for deletion or written. This
file has the fixtures, SweepCase and the layout cases; test_disk_guard_runs.py the rest.

    python3 -m pytest -q scripts/agent-host/test_disk_guard.py scripts/agent-host/test_disk_guard_runs.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import disk_guard  # noqa: E402
import disk_guard_apply  # noqa: E402
from disk_guard_base import QUARANTINE as QUAR  # noqa: E402

GO_README = (
    "This directory holds cached build artifacts from the Go build system.\n"
    'Run "go clean -cache" if the directory is getting too large.\n'
)
# The shape of the real quoted dir: GOCACHE was given a whole line of assignments, so the
# value's slashes made a chain of single directories. The leaf name stands in for one that
# held a connection string.
CHAIN = ("Users", "you", "agent-work", ".cache", "go-mod AGENTRT_TEST_PG='postgres:fake-secret' AGENTRT_TEST_REQUIRED=1")
SECRET = "fake-secret"
FAKE_LSOF = """#!/usr/bin/env bash
d=${FAKE_LSOF_DIR:?}
[ -f "$d/out" ] && cat "$d/out"
[ -f "$d/err" ] && cat "$d/err" >&2
exit "$(cat "$d/rc" 2>/dev/null || echo 0)"
"""
FAKE_MOUNT = """#!/usr/bin/env bash
d=${FAKE_LSOF_DIR:?}
[ -f "$d/mount.out" ] && cat "$d/mount.out"
exit "$(cat "$d/mount.rc" 2>/dev/null || echo 0)"
"""
# Records every call; `go env GOCACHE` answers with $FAKE_GOCACHE.
FAKE_TOOL = """#!/usr/bin/env bash
echo "$(basename "$0") $* GOCACHE=${GOCACHE:-} GOMODCACHE=${GOMODCACHE:-} npm_config_cache=${npm_config_cache:-}" >> "${FAKE_CALLS:?}"
case "$(basename "$0") $1" in
  "go env") echo "${FAKE_GOCACHE:-}" ;;
  "pgrep -f") exit 1 ;;
  "ipcs -ma") printf 'IPC status\\nT ID KEY MODE OWNER GROUP CREATOR CGROUP NATTCH SEGSZ CPID\\nShared Memory:\\n'
              printf 'm 65536 0x0052e2c1 --rw------- you staff you staff 0 56 %s\\n' "${FAKE_DEAD_PID:-999999}" ;;
esac
exit 0
"""


def go_build(root: Path, exe: bool = False) -> Path:
    root.mkdir(parents=True)
    (root / "README").write_text(GO_README)
    (root / "trim.txt").write_text("1729700000\n")
    for b in ("00", "ab"):
        (root / b).mkdir()
        (root / b / (b + "1" * 62 + "-a")).write_bytes(b"a" * 64)
        (root / b / (b + "2" * 62 + "-d")).write_bytes(b"d" * 4096)
    if exe:  # go run / go tool keep an executable as <hash>-d/<name>
        d = root / "ab" / ("ab" + "3" * 62 + "-d")
        d.mkdir()
        (d / "probe").write_bytes(b"\x7fELF")
        (d / "probe").chmod(0o755)
    return root


def read_only(top: Path) -> None:
    for dp, dns, fns in os.walk(top, topdown=False):
        for f in fns:
            p = os.path.join(dp, f)
            if not os.path.islink(p):
                os.chmod(p, 0o444)
        os.chmod(dp, 0o555)


def go_mod(root: Path, extra=None) -> Path:
    dl = root / "cache" / "download" / "example.com" / "m" / "@v"
    dl.mkdir(parents=True)
    for n in ("list", "v1.0.0.info", "v1.0.0.mod", "v1.0.0.zip", "v1.0.0.ziphash", "v1.0.0.lock"):
        (dl / n).write_text("x")
    mod = root / "example.com" / "m@v1.0.0"
    (mod / "sub").mkdir(parents=True)
    (mod / "go.mod").write_text("module example.com/m\n")
    (mod / "m.go").write_text("package m\n")
    (mod / "sub" / "s.go").write_text("package sub\n")
    if extra:
        extra(mod)
    read_only(mod)
    return root


def npm(root: Path) -> Path:
    c = root / "_cacache"
    (c / "content-v2" / "sha512" / "ab" / "cd").mkdir(parents=True)
    (c / "content-v2" / "sha512" / "ab" / "cd" / ("ef" * 30)).write_bytes(b"x")
    (c / "index-v5" / "12" / "34").mkdir(parents=True)
    (c / "index-v5" / "12" / "34" / ("56" * 30)).write_text("{}")
    (c / "tmp").mkdir()
    (root / "_logs").mkdir()
    (root / "_logs" / "2026-10-23T18_02_50_152Z-debug-0.log").write_text("log")
    (root / "_update-notifier-last-checked").write_text("")
    return root


def chain(root: Path) -> Path:
    go_build(root.joinpath(*CHAIN))
    return root


def backdate(path: Path, minutes: float) -> None:
    t = time.time() - minutes * 60
    for dp, dns, fns in os.walk(path):
        for n in dns + fns:
            p = os.path.join(dp, n)
            if not os.path.islink(p):
                os.utime(p, (t, t))
    os.utime(path, (t, t))


def finished_review(aw: Path, name: str, sub: str = "go-cache", make=go_build) -> Path:
    """A review dir with BRIEF.md, a cache, and run.done written after the cache."""
    review = aw / name
    review.mkdir(parents=True, exist_ok=True)
    (review / "BRIEF.md").write_text("brief\n")
    cache = make(review / sub)
    backdate(cache, 60)
    (review / "run.done").write_text("exit=0\n")
    backdate(review / "run.done", 30)
    return cache

class SweepCase(unittest.TestCase):
    """A throwaway AGENT_WORK, a fake lsof, an empty registry; helpers to run and read a sweep."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.aw = base / "agent-work"
        self.aw.mkdir()
        self.outside = base / "outside"
        self.outside.mkdir()
        home = base / "home"
        home.mkdir()
        self.bin = base / "bin"
        self.bin.mkdir()
        self.fake = base / "fake"
        self.fake.mkdir()
        (self.bin / "lsof").write_text(FAKE_LSOF)
        (self.bin / "lsof").chmod(0o755)
        (self.bin / "mount").write_text(FAKE_MOUNT)
        (self.bin / "mount").chmod(0o755)
        self.calls = base / "calls"
        self.calls.write_text("")
        self.registry = base / "cache-roots.tsv"
        self.registry.write_text("")
        inherited = {k: v for k, v in os.environ.items()
                     if not k.startswith(("LIFECYCLE_", "DISK_GUARD_", "GO", "npm_config_"))
                     and k not in ("AGENT_WORK", "WARN_GB", "STOP_GB", "DEFAULT_GOCACHE_CAP_GB", "CURSOR_DB_WARN_GB")}
        self.env = {
            **inherited,
            "HOME": str(home),
            "AGENT_WORK": str(self.aw),
            "LIFECYCLE_CACHE_ROOTS": str(self.registry),
            "LIFECYCLE_LSOF": str(self.bin / "lsof"),
            "LIFECYCLE_MOUNT": str(self.bin / "mount"),
            "FAKE_LSOF_DIR": str(self.fake),
            "LIFECYCLE_DONE_MIN_AGE_MIN": "10",
            "FAKE_CALLS": str(self.calls),
            "PATH": f"{self.bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        }
        self.restore_modes: list = []

    def tearDown(self) -> None:
        disk_guard_apply.between_check_and_delete = None
        disk_guard_apply.between_check_and_rename = None
        disk_guard_apply.between_recheck_and_remove = None
        disk_guard_apply.during_removal = None
        disk_guard_apply.after_inventory_written = None
        for p, mode in self.restore_modes:
            with contextlib.suppress(OSError):
                os.chmod(p, mode)
        self.tmp.cleanup()

    def register(self, *lines: str) -> None:
        self.registry.write_text("".join(line + "\n" for line in lines))

    def journal(self, original: str, quarantine: str, root=None, run_id: str = "20261024T000000Z-1") -> Path:
        """The entry a sweep writes before renaming original to quarantine (review 544 A2)."""
        st = os.lstat(self.aw / quarantine)
        d = self.aw / "status" / "lifecycle-journal"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{run_id}-{abs(hash(quarantine))}.json"
        p.write_text(json.dumps({"run_id": run_id, "original": original, "quarantine": quarantine,
                                 "root": list(root or (st.st_dev, st.st_ino))}))
        return p

    def tool(self, *names: str) -> None:
        for n in names:
            (self.bin / n).write_text(FAKE_TOOL)
            (self.bin / n).chmod(0o755)

    def sweep(self, *args: str) -> tuple:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = disk_guard.main(["sweep", "--no-host", *args], self.env)
        return rc, out.getvalue()

    def report(self) -> dict:
        return json.loads((self.aw / "status" / "lifecycle.json").read_text())

    def item(self, path: str) -> dict:
        found = [i for i in self.report()["items"] if i["path"] == path]
        self.assertEqual(len(found), 1, f"{path}: {[i['path'] for i in self.report()['items']]}")
        return found[0]

    def assertKept(self, path: str, reason: str) -> dict:
        it = self.item(path)
        self.assertEqual((it["action"], it["reason"]), ("keep", reason), it)
        self.assertTrue((self.aw / path).exists(), path)
        return it

    def assertDeleted(self, path: str) -> None:
        it = self.item(path)
        self.assertEqual(it["action"], "deleted", it)
        self.assertFalse(os.path.lexists(self.aw / path), path)

    def unreadable(self, p: Path) -> None:
        self.restore_modes.append((p, stat.S_IMODE(os.lstat(p).st_mode)))
        os.chmod(p, 0)


class Layouts(SweepCase):
    """S1: what a sweep removes and what it keeps (layout, names, symlinks, git, end evidence)."""

    def test_real_cache_of_each_layout_is_removed(self) -> None:
        finished_review(self.aw, "codex-review-1", "go-cache", lambda p: go_build(p, exe=True))
        finished_review(self.aw, "codex-review-2", ".gocache", go_mod)
        finished_review(self.aw, "codex-review-3", "cache", npm)
        backdate(chain(self.aw / ".cache" / "go-build GOMODCACHE="), 60)
        self.register(
            "codex-review-*/go-cache\tgo-build\trun.done\treview cache",
            "codex-review-*/.gocache\tgo-mod\trun.done\treview module cache",
            "codex-review-*/cache\tnpm\trun.done\treview npm cache",
            ".cache/go-build GOMODCACHE=\tgo-build-chain\tended\tcoordinator 2026-10-24: GOCACHE typo leftover",
        )
        rc, out = self.sweep("--apply")
        self.assertEqual(rc, 0, out)
        for p in ("codex-review-1/go-cache", "codex-review-2/.gocache", "codex-review-3/cache", ".cache/go-build GOMODCACHE="):
            self.assertDeleted(p)
        for n in (1, 2, 3):
            self.assertTrue((self.aw / f"codex-review-{n}" / "BRIEF.md").is_file())
            self.assertTrue((self.aw / f"codex-review-{n}" / "run.done").is_file())
        self.assertEqual(self.report()["counts"].get("deleted"), 4)
        self.assertFalse((self.aw / ".lifecycle.lock" / "owner").exists(), "the lock is released")
        self.assertFalse(any(QUAR in n for n in os.listdir(self.aw / "codex-review-1")))

    def test_dry_run_removes_nothing(self) -> None:
        cache = finished_review(self.aw, "codex-review-1")
        self.register("codex-review-*/go-cache\tgo-build\trun.done\treview cache")
        rc, out = self.sweep()
        self.assertEqual(rc, 0, out)
        it = self.item("codex-review-1/go-cache")
        self.assertEqual(it["action"], "would-delete", it)
        self.assertTrue((cache / "00").is_dir())
        self.assertEqual(self.report()["mode"], "report-only")
        self.assertIn("would-delete: 1", out)

    def test_handwritten_go_inside_a_bucket_stays(self) -> None:
        cache = finished_review(self.aw, "codex-review-1")
        (cache / "00" / "draft.go").write_text("package draft\n")
        backdate(cache, 60)
        cache2 = finished_review(self.aw, "codex-review-2", ".gocache", go_mod)
        mod = cache2 / "example.com" / "m@v1.0.0"
        os.chmod(mod, 0o755)
        (mod / "notes.go").write_text("// mine\n")  # writable: Go never extracts a writable file
        os.chmod(mod, 0o555)
        backdate(cache2, 60)
        self.register(
            "codex-review-*/go-cache\tgo-build\trun.done\treview cache",
            "codex-review-*/.gocache\tgo-mod\trun.done\treview module cache",
        )
        self.sweep("--apply")
        it = self.assertKept("codex-review-1/go-cache", "handwritten-file")
        self.assertIn("00/draft.go", it["detail"])
        self.assertTrue((cache / "00" / "draft.go").is_file())
        self.assertKept("codex-review-2/.gocache", "writable-in-module")
        self.assertTrue((mod / "notes.go").is_file())

    def test_ignored_handwritten_material_stays(self) -> None:
        lane = self.aw / "lane-a"
        lane.mkdir()
        git = ["git", "-C", str(lane), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        subprocess.run([*git, "init", "-q"], check=True)
        (lane / ".gitignore").write_text(".gocache/\n.gocache-b/\n.gocache-t/\n")
        subprocess.run([*git, "add", ".gitignore"], check=True)
        subprocess.run([*git, "commit", "-qm", "init"], check=True)
        good = go_build(lane / ".gocache")
        material = go_build(lane / ".gocache-b")
        (material / "plan.md").write_text("ignored by git, still mine\n")
        tracked = go_build(lane / ".gocache-t")
        subprocess.run([*git, "add", "-f", ".gocache-t/README"], check=True)
        untracked = go_build(lane / "cache-u")  # not in .gitignore: git shows it as untracked
        for p in (good, material, tracked, untracked):
            backdate(p, 60)
        self.register(*(f"lane-a/{n}\tgo-build\tended\tlane finished (test)" for n in (".gocache", ".gocache-b", ".gocache-t", "cache-u")))
        self.sweep("--apply")
        self.assertDeleted("lane-a/.gocache")
        self.assertKept("lane-a/.gocache-b", "unknown-entry")
        self.assertTrue((material / "plan.md").is_file())
        self.assertKept("lane-a/.gocache-t", "git-tracked-inside")
        self.assertKept("lane-a/cache-u", "git-not-ignored")

    def test_git_error_keeps_the_root(self) -> None:
        lane = self.aw / "lane-b"
        lane.mkdir()
        (lane / ".git").write_text("gitdir: /nonexistent/worktrees/lane-b\n")
        backdate(go_build(lane / ".gocache"), 60)
        self.register("lane-b/.gocache\tgo-build\tended\tlane finished (test)")
        self.sweep("--apply")
        it = self.assertKept("lane-b/.gocache", "git-error")
        self.assertIn("not a git repository", it["detail"])

    def test_names_with_a_space_are_not_taken_by_a_wildcard(self) -> None:
        finished_review(self.aw, "codex-review-1")
        finished_review(self.aw, "codex-review-2 draft")
        drafts = self.aw / "codex-review-3 notes"
        drafts.mkdir()
        (drafts / "notes.md").write_text("my notes\n")
        backdate(go_build(self.aw / ".cache" / "go-build old"), 60)
        self.register(
            "codex-review-*/go-cache\tgo-build\trun.done\treview cache",
            ".cache/go-build *\tgo-build\tended\tglob over a name with a space (test)",
        )
        self.sweep("--apply")
        self.assertDeleted("codex-review-1/go-cache")
        self.assertKept("codex-review-2 draft/go-cache", "glob-weird-name")
        self.assertKept(".cache/go-build old", "glob-weird-name")
        self.assertTrue((drafts / "notes.md").is_file())
        self.assertFalse([i for i in self.report()["items"] if i["path"].startswith("codex-review-3 notes")])

    def test_nested_git_stays(self) -> None:
        cache = finished_review(self.aw, "codex-review-1")
        (cache / "00" / ".git").mkdir()
        (cache / "00" / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        backdate(cache, 60)

        def repo(mod: Path) -> None:  # inside a module any read-only name is allowed, .git is not
            (mod / ".git").mkdir()
            (mod / ".git" / "HEAD").write_text("ref: refs/heads/main\n")

        finished_review(self.aw, "codex-review-2", ".gocache", lambda p: go_mod(p, repo))
        self.register(
            "codex-review-*/go-cache\tgo-build\trun.done\treview cache",
            "codex-review-*/.gocache\tgo-mod\trun.done\treview module cache",
        )
        self.sweep("--apply")
        self.assertKept("codex-review-1/go-cache", "nested-git")
        self.assertKept("codex-review-2/.gocache", "nested-git")
        self.assertTrue((self.aw / "codex-review-2/.gocache/example.com/m@v1.0.0/.git/HEAD").is_file())

    def test_symlinks_out_of_the_root_are_not_followed(self) -> None:
        precious = self.outside / "precious"
        precious.mkdir()
        (precious / "keep.txt").write_text("not a cache\n")
        cache = finished_review(self.aw, "codex-review-1")
        # named like a cache entry, pointing at someone's file
        os.symlink(precious / "keep.txt", cache / "00" / ("00" + "9" * 62 + "-a"))
        backdate(cache, 60)

        def link(mod: Path) -> None:
            os.symlink(precious, mod / "vendor-link")

        finished_review(self.aw, "codex-review-2", ".gocache", lambda p: go_mod(p, link))
        # a review dir that is itself a symlink to a real-looking review elsewhere
        elsewhere = self.outside / "review-5"
        finished_review(self.outside, "review-5")
        os.symlink(elsewhere, self.aw / "codex-review-5")
        self.register(
            "codex-review-*/go-cache\tgo-build\trun.done\treview cache",
            "codex-review-*/.gocache\tgo-mod\trun.done\treview module cache",
        )
        self.sweep("--apply")
        self.assertKept("codex-review-1/go-cache", "symlink")
        self.assertKept("codex-review-2/.gocache", "symlink")
        self.assertKept("codex-review-5", "symlink-in-path")
        self.assertTrue((precious / "keep.txt").is_file())
        self.assertTrue((elsewhere / "go-cache" / "00").is_dir(), "the sweep reached through a symlink")

    def test_review_without_positive_end_evidence_stays(self) -> None:
        no_done = self.aw / "codex-review-1"
        no_done.mkdir()
        backdate(go_build(no_done / "go-cache"), 60)
        fresh = finished_review(self.aw, "codex-review-2")
        os.utime(self.aw / "codex-review-2" / "run.done")  # just written: the review may still be closing
        later = finished_review(self.aw, "codex-review-3")
        (later / "00" / ("00" + "7" * 62 + "-a")).write_bytes(b"new")  # a run after run.done
        not_a_file = self.aw / "codex-review-4"
        not_a_file.mkdir()
        backdate(go_build(not_a_file / "go-cache"), 60)
        (not_a_file / "run.done").mkdir()
        self.register("codex-review-*/go-cache\tgo-build\trun.done\treview cache")
        self.sweep("--apply")
        self.assertKept("codex-review-1/go-cache", "no-run-done")
        self.assertKept("codex-review-2/go-cache", "run-done-too-fresh")
        self.assertKept("codex-review-3/go-cache", "written-after-run-done")
        self.assertKept("codex-review-4/go-cache", "run-done-unreadable")
        self.assertTrue((fresh / "00").is_dir())

    def test_quoted_dir_shape(self) -> None:
        shared = self.aw / ".cache"
        backdate(chain(shared / "go-build GOMODCACHE="), 60)
        odd = chain(shared / "go-build GOMODCACHE=old")
        (odd / CHAIN[0] / CHAIN[1] / "notes.txt").write_text("left by hand\n")
        backdate(odd, 60)
        backdate(chain(shared / "go-build GOCACHE=x"), 60)
        drafted = chain(shared / "go-build GOMODCACHE=draft")
        drafted.joinpath(*CHAIN, "00", "draft.go").write_text("package draft\n")
        backdate(drafted, 60)
        self.register(
            ".cache/go-build GOMODCACHE=\tgo-build-chain\tended\tcoordinator: typo leftover (test)",
            ".cache/go-build GOMODCACHE=old\tgo-build-chain\tended\tcoordinator: typo leftover (test)",
            ".cache/go-build GOMODCACHE=draft\tgo-build-chain\tended\tcoordinator: typo leftover (test)",
        )
        rc, out = self.sweep("--apply")
        self.assertDeleted(".cache/go-build GOMODCACHE=")
        it = self.assertKept(".cache/go-build GOMODCACHE=old", "chain-shape")
        self.assertIn("level 2", it["detail"])
        leaf = self.assertKept(".cache/go-build GOMODCACHE=draft", "handwritten-file")
        self.assertEqual(leaf["detail"], "<leaf>/00/draft.go looks hand-written")
        un = self.assertKept(".cache/go-build GOCACHE=x", "unregistered")
        self.assertEqual(un["layout"], "go-build-chain")
        text = (self.aw / "status" / "lifecycle.json").read_text()
        self.assertNotIn(SECRET, text)
        self.assertNotIn(SECRET, out)

if __name__ == "__main__":
    unittest.main()
