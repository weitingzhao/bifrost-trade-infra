"""disk-guard.sh sweep, part 4 (W-31 4.6 S1; review 544): removal touches only what the
second check accepted (A1), a leftover needs the sweep's own journal entry and a full Git
check of its original path (A2), exclusions overlap both ways (A3), Git paths are literal
(A4), npm's _lastverified (C1), and the report's sizes and temp-dir listing (D).
Fixtures and SweepCase are in test_disk_guard.py.

    python3 -m pytest -q scripts/agent-host/test_disk_guard_removal.py
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import disk_guard  # noqa: E402
import disk_guard_apply  # noqa: E402
from disk_guard_base import QUARANTINE as QUAR  # noqa: E402
from test_disk_guard import SweepCase, backdate, finished_review, go_build, go_mod, npm  # noqa: E402

REVIEW = "codex-review-*/go-cache\tgo-build\trun.done\treview cache"
ENTRY = "00" + "1" * 62 + "-a"


def git(repo: Path, *args: str) -> None:
    env = {**os.environ, "GIT_LITERAL_PATHSPECS": "1"}
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   check=True, capture_output=True, env=env)


class Removal544(SweepCase):
    """A1: a change after the second check stops the removal and keeps the new material."""

    def staged_dir(self) -> list:
        seen: list = []

        def remember(it, pfd, name, q) -> None:
            seen.append(Path(self.aw, it.path).parent / q)

        disk_guard_apply.between_recheck_and_remove = remember
        return seen

    def journal_files(self) -> list:
        d = self.aw / "status" / "lifecycle-journal"
        return sorted(d.glob("*.json")) if d.is_dir() else []

    def test_a_file_added_after_the_second_check(self) -> None:
        cache = finished_review(self.aw, "codex-review-1")
        self.register(REVIEW)

        def add(it, pfd, name, q) -> None:
            Path(self.aw, "codex-review-1", q, "00", "late.go").write_text("package late\n")

        disk_guard_apply.between_recheck_and_remove = add
        self.sweep("--apply")
        it = self.assertKept("codex-review-1/go-cache", "stopped-before-removal")
        self.assertIn("00/late.go is new", it["detail"])
        self.assertIn("nothing removed; renamed back", it["detail"])
        self.assertTrue((cache / "00" / "late.go").is_file())
        self.assertTrue((cache / "00" / ENTRY).is_file(), "nothing was removed")
        self.assertEqual(self.journal_files(), [], "renamed back: the journal entry goes")

    def test_a_subdirectory_replaced_after_the_second_check(self) -> None:
        cache = finished_review(self.aw, "codex-review-1")
        self.register(REVIEW)

        def replace(it, pfd, name, q) -> None:
            root = Path(self.aw, "codex-review-1", q)
            os.rename(root / "00", self.outside / "00-checked")
            (root / "00").mkdir()
            (root / "00" / "draft.go").write_text("package draft\n")

        disk_guard_apply.between_recheck_and_remove = replace
        self.sweep("--apply")
        it = self.assertKept("codex-review-1/go-cache", "stopped-before-removal")
        self.assertIn("00 was replaced or changed", it["detail"])
        self.assertTrue((cache / "00" / "draft.go").is_file())
        self.assertTrue((self.outside / "00-checked" / ENTRY).is_file())

    def test_a_file_rewritten_in_place_after_the_second_check(self) -> None:
        cache = finished_review(self.aw, "codex-review-1")
        self.register(REVIEW)

        def rewrite(it, pfd, name, q) -> None:
            with open(Path(self.aw, "codex-review-1", q, "ab", "ab" + "2" * 62 + "-d"), "ab") as f:
                f.write(b"someone's bytes")

        disk_guard_apply.between_recheck_and_remove = rewrite
        self.sweep("--apply")
        it = self.assertKept("codex-review-1/go-cache", "stopped-before-removal")
        self.assertIn("was replaced or changed", it["detail"])
        self.assertTrue((cache / "ab" / ("ab" + "2" * 62 + "-d")).read_bytes().endswith(b"someone's bytes"))

    def test_a_change_during_removal_leaves_it_partly_removed(self) -> None:
        finished_review(self.aw, "codex-review-1")
        self.register(REVIEW)
        staged = self.staged_dir()

        def meanwhile(crel: str) -> None:
            late = staged[0] / "ab" / "late.go"
            if not late.exists():
                late.write_text("package late\n")

        disk_guard_apply.during_removal = meanwhile
        self.sweep("--apply")
        it = self.item("codex-review-1/go-cache")
        self.assertEqual((it["action"], it["reason"]), ("keep", "partly-removed"), it)
        self.assertTrue(it["detail"].startswith("partly removed, stopped: ab/late.go is new"), it)
        left = staged[0]
        self.assertTrue((left / "ab" / "late.go").is_file(), "the new material stays")
        self.assertFalse((left / "00").exists(), "checked entries before the change are gone")
        self.assertTrue((left / "README").is_file(), "the marker goes last")
        self.assertEqual(len(self.journal_files()), 1, "the leftover keeps its journal entry")
        disk_guard_apply.during_removal = None
        disk_guard_apply.between_recheck_and_remove = None
        self.sweep("--apply")  # the next sweep finds a recorded leftover holding new material
        self.assertKept(str(left.relative_to(self.aw)), "handwritten-file")
        self.assertTrue((left / "ab" / "late.go").is_file())


class Journal544(SweepCase):
    """A2: leftovers by record only, and their original path checked by Git in full."""

    def test_the_journal_is_written_before_the_rename_and_dropped_after(self) -> None:
        finished_review(self.aw, "codex-review-1")
        self.register(REVIEW)
        seen = []

        def look(staged: list) -> None:
            d = self.aw / "status" / "lifecycle-journal"
            for p in d.glob("*.json"):
                seen.append(p.read_text())

        disk_guard_apply.between_check_and_delete = look
        self.sweep("--apply")
        self.assertDeleted("codex-review-1/go-cache")
        self.assertEqual(len(seen), 1)
        self.assertIn('"original": "codex-review-1/go-cache"', seen[0])
        self.assertIn(QUAR, seen[0])
        self.assertEqual(list((self.aw / "status" / "lifecycle-journal").glob("*.json")), [])

    def test_a_recorded_leftover_whose_original_is_no_longer_ignored(self) -> None:
        lane = self.aw / "lane-g"
        lane.mkdir()
        git(lane, "init", "-q")
        (lane / ".gitignore").write_text(".gocache/\n.gocache-2/\n")
        git(lane, "add", ".gitignore")
        git(lane, "commit", "-qm", "init")
        tail = QUAR + "20261024T000000Z-1"
        for n in (".gocache", ".gocache-2"):
            root = go_build(lane / n)
            backdate(root, 60)
            os.rename(root, str(root) + tail)
            self.journal(f"lane-g/{n}", f"lane-g/{n}{tail}")
        (lane / ".gitignore").write_text(".gocache-2/\n")  # the rule for .gocache was revoked
        self.register("lane-g/.gocache\tgo-build\tended\tx", "lane-g/.gocache-2\tgo-build\tended\tx")
        self.sweep("--apply")
        it = self.assertKept(f"lane-g/.gocache{tail}", "git-not-ignored")
        self.assertIn("no longer ignored", it["detail"])
        self.assertDeleted(f"lane-g/.gocache-2{tail}")


class Rules544(SweepCase):
    """A3 exclusions, A4 literal Git paths, C1 _lastverified, D sizes and listings."""

    def test_exclusions_overlap_both_ways(self) -> None:
        tail = QUAR + "20261024T000000Z-1"
        shared = go_build(self.aw / ".cache" / "go-build")
        os.rename(shared, str(shared) + tail)
        self.journal(".cache/go-build", ".cache/go-build" + tail)
        backdate(go_build(self.aw / "lane" / "cache"), 60)
        self.env["LIFECYCLE_EXCLUDE"] = ".cache/go-build:lane/cache/00"
        self.register(".cache/go-build\tgo-build\tcap=0\tshared", "lane/cache\tgo-build\tended\tx")
        self.sweep("--apply")
        self.assertKept(".cache/go-build" + tail, "excluded")
        self.assertKept("lane/cache", "excluded")

    def test_a_directory_named_like_pathspec_magic(self) -> None:
        lane = self.aw / "lane-m"
        lane.mkdir()
        git(lane, "init", "-q")
        (lane / ".gitignore").write_text("/:(literal)cache/\n")
        git(lane, "add", ".gitignore")
        root = go_build(lane / ":(literal)cache")
        git(lane, "add", "-f", "--", ":(literal)cache/README")
        backdate(root, 60)
        self.register("lane-m/:(literal)cache\tgo-build\tended\tx")
        self.sweep("--apply")
        self.assertKept("lane-m/:(literal)cache", "git-tracked-inside")

    def test_npm_lastverified(self) -> None:
        good = npm(self.aw / "npm-good")
        (good / "_cacache" / "_lastverified").write_text("1729700000000")
        bad = npm(self.aw / "npm-bad")
        (bad / "_cacache" / "_lastverified").write_text("verified by me\n")
        for p in (good, bad):
            backdate(p, 60)
        self.register("npm-good\tnpm\tended\tx", "npm-bad\tnpm\tended\tx")
        self.sweep("--apply")
        self.assertDeleted("npm-good")
        self.assertKept("npm-bad", "unknown-entry")

    def test_kept_by_design_says_why(self) -> None:
        npx = npm(self.aw / "npm-npx")
        (npx / "_npx" / "abc").mkdir(parents=True)
        tmp = go_mod(self.aw / "mod-tmp")
        (tmp / "cache" / "download" / "example.com" / "m" / "@v" / "v1.0.0.zip123456.tmp").write_text("x")
        writable = go_mod(self.aw / "mod-rw")
        os.chmod(writable / "example.com" / "m@v1.0.0", 0o755)
        for p in (npx, tmp, writable):
            backdate(p, 60)
        self.register("npm-npx\tnpm\tended\tx", "mod-tmp\tgo-mod\tended\tx", "mod-rw\tgo-mod\tended\tx")
        self.sweep("--apply")
        self.assertKept("npm-npx", "npm-npx-installs")
        self.assertKept("mod-tmp", "go-download-tmp")
        self.assertIn("-modcacherw", self.assertKept("mod-rw", "writable-in-module")["detail"])
        reasons = self.report()["kept_reasons"]
        for r in ("npm-npx-installs", "go-download-tmp", "writable-in-module"):
            self.assertIn(r, reasons)

    def test_sizes_with_read_errors_are_incomplete(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root reads a mode-000 directory")
        nm = self.aw / "lane-x" / "node_modules"
        (nm / "pkg" / "inner").mkdir(parents=True)
        (nm / "pkg" / "inner" / "x.js").write_text("x")
        (nm / "ok").mkdir()
        self.unreadable(nm / "pkg")
        self.sweep()
        it = self.item("lane-x/node_modules")
        self.assertEqual(it["reason"], "unmanaged-node-modules")
        self.assertFalse(it["bytes_complete"], it)

    def test_every_tmp_review_entry_is_listed(self) -> None:
        self.tool("go", "docker", "pgrep", "ipcs", "ipcrm", "tmutil")
        tmp = self.outside / "tmp"
        for n in range(25):
            (tmp / f"review-{n:02d}").mkdir(parents=True)
        self.env.update(LIFECYCLE_TMP_ROOT=str(tmp), FAKE_GOCACHE="")
        with contextlib.redirect_stdout(io.StringIO()):
            disk_guard.main(["sweep"], self.env)
        step = next(s for s in self.report()["host_steps"] if s["step"] == "tmp-review-dirs")
        self.assertEqual([e["name"] for e in step["entries"]], [f"review-{n:02d}" for n in range(25)])
        self.assertTrue(all(e["bytes_complete"] for e in step["entries"]))


if __name__ == "__main__":
    unittest.main()
