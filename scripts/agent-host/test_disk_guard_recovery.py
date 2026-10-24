"""disk-guard.sh sweep, part 5 (W-31 4.6 S1; review 547): a sweep that dies part way through
a removal is finished by the next one through the inventory it wrote first (C1), an empty
.lifecycle-del- suffix is not a leftover (A2), a chmod or a size-keeping rewrite after the
second check stops the removal (A3), only canonical LIFECYCLE_EXCLUDE paths (A4), and bad
journal records (D). Fixtures and SweepCase are in test_disk_guard.py.

    python3 -m pytest -q scripts/agent-host/test_disk_guard_recovery.py
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import disk_guard_apply  # noqa: E402
from disk_guard_base import QUARANTINE as QUAR  # noqa: E402
from test_disk_guard import CHAIN, SweepCase, backdate, chain, finished_review, go_build, go_mod  # noqa: E402

REVIEW = "codex-review-*/go-cache\tgo-build\trun.done\treview cache"


class Crashed(SystemExit):
    """Stands for the sweep's process dying in the middle of a removal."""


class Recovery547(SweepCase):
    """C1: the three interruption points review 547 lists, then the next sweep."""

    def crash_at(self, when) -> None:
        def hook(crel: str) -> None:
            if when(crel):
                raise Crashed(9)

        disk_guard_apply.during_removal = hook
        with self.assertRaises(Crashed):
            self.sweep("--apply")
        disk_guard_apply.during_removal = None

    def journal_dir(self) -> Path:
        return self.aw / "status" / "lifecycle-journal"

    def assert_finished(self, registered: str) -> None:
        left = [p for p in Path(self.aw, registered).parent.iterdir() if QUAR in p.name]
        self.assertEqual(len(left), 1, left)
        self.assertEqual(len(list(self.journal_dir().glob("*.json.inventory"))), 1, "the inventory was written first")
        self.sweep("--apply")
        it = self.item(str(left[0].relative_to(self.aw)))
        self.assertIn(it["action"], ("deleted", "pruned"), it)
        self.assertFalse(left[0].exists())
        self.assertEqual(list(self.journal_dir().glob("*")), [], "journal entry and inventory are gone")
        self.assertEqual(self.report()["journal"]["loaded_entries"], 1)
        self.assertEqual(self.report()["journal"]["open_entries_at_end"], 0)

    def test_crash_after_the_first_file_of_a_bucket(self) -> None:
        # the bucket stays, newer than run.done: a full recheck would say written-after-run-done
        finished_review(self.aw, "codex-review-1")
        self.register(REVIEW)
        self.crash_at(lambda crel: True)
        self.assert_finished("codex-review-1/go-cache")

    def test_crash_after_a_module_dir_was_made_writable(self) -> None:
        # the sweeper's own u+rwx on a 0555 module dir: a full recheck would say writable-in-module
        finished_review(self.aw, "codex-review-2", ".gocache", go_mod)
        self.register("codex-review-*/.gocache\tgo-mod\trun.done\treview module cache")
        self.crash_at(lambda crel: crel.startswith("example.com/m@v1.0.0/"))
        left = next(p for p in (self.aw / "codex-review-2").iterdir() if QUAR in p.name)
        self.assertEqual(os.stat(left / "example.com" / "m@v1.0.0").st_mode & 0o777, 0o755)
        self.assert_finished("codex-review-2/.gocache")

    def test_crash_after_the_last_marker(self) -> None:
        # an empty root: a full recheck would say layout-marker-missing
        finished_review(self.aw, "codex-review-3")
        self.register(REVIEW)
        self.crash_at(lambda crel: crel == "README")
        left = next(p for p in (self.aw / "codex-review-3").iterdir() if QUAR in p.name)
        self.assertEqual(os.listdir(left), [])
        self.assert_finished("codex-review-3/go-cache")

    def test_markers_go_last_at_every_level(self) -> None:
        backdate(chain(self.aw / ".cache" / "go-build GOMODCACHE="), 60)
        self.register(".cache/go-build GOMODCACHE=\tgo-build-chain\tended\tx")
        order: list = []
        disk_guard_apply.during_removal = order.append
        self.sweep("--apply")
        self.assertDeleted(".cache/go-build GOMODCACHE=")
        leaf = "/".join(CHAIN)
        inside = [c for c in order if c.startswith(leaf + "/")]
        self.assertEqual(inside[-1], leaf + "/README", inside)

    def test_an_unusable_inventory_keeps_the_leftover(self) -> None:
        finished_review(self.aw, "codex-review-4")
        self.register(REVIEW)
        self.crash_at(lambda crel: True)
        inv = next(self.journal_dir().glob("*.json.inventory"))
        inv.write_text("{not json")
        self.sweep("--apply")
        left = next(p for p in (self.aw / "codex-review-4").iterdir() if QUAR in p.name)
        self.assertKept(str(left.relative_to(self.aw)), "journal-inventory-unusable")


class Rules547(SweepCase):
    def test_an_empty_suffix_is_not_a_leftover(self) -> None:
        stray = go_build(self.aw / "lane" / ("cache" + QUAR))
        backdate(stray, 60)
        self.register("lane/cache\tgo-build\tended\tx")
        self.sweep("--apply")
        it = self.assertKept("lane/cache" + QUAR, "unrecorded-quarantine-name")
        self.assertIn("no run id", it["detail"])
        self.assertEqual(it["leftover"], "")

    def test_a_chmod_after_the_second_check_stops_the_removal(self) -> None:
        # a module directory made writable to start editing (only the mode shows it: a
        # directory's times are not compared), and a module file
        caches = {n: finished_review(self.aw, n, ".gocache", go_mod) for n in ("codex-review-1", "codex-review-2")}
        self.register("codex-review-*/.gocache\tgo-mod\trun.done\treview module cache")
        target = {"codex-review-1": ("example.com", "m@v1.0.0"), "codex-review-2": ("example.com", "m@v1.0.0", "m.go")}

        def edit(it, pfd, name, q) -> None:
            review = it.path.split("/")[0]
            os.chmod(Path(self.aw, review, q, *target[review]), 0o755 if review == "codex-review-1" else 0o644)

        disk_guard_apply.between_recheck_and_remove = edit
        self.sweep("--apply")
        for review, parts in target.items():
            it = self.assertKept(f"{review}/.gocache", "stopped-before-removal")
            self.assertIn(f"{'/'.join(parts)} was replaced or changed", it["detail"])
            self.assertTrue((caches[review] / "example.com" / "m@v1.0.0" / "m.go").is_file())

    def test_a_rewrite_that_keeps_size_and_mtime_stops_the_removal(self) -> None:
        cache = finished_review(self.aw, "codex-review-1")
        self.register(REVIEW)
        name = "ab" + "2" * 62 + "-d"

        def rewrite(it, pfd, n, q) -> None:
            p = Path(self.aw, "codex-review-1", q, "ab", name)
            st = os.stat(p)
            p.write_bytes(b"X" * st.st_size)
            os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))

        disk_guard_apply.between_recheck_and_remove = rewrite
        self.sweep("--apply")
        self.assertKept("codex-review-1/go-cache", "stopped-before-removal")
        self.assertEqual((cache / "ab" / name).read_bytes()[:1], b"X")

    def test_non_canonical_exclusions_are_refused(self) -> None:
        for bad in ("./lane/cache/00", "lane//cache/00", "lane/cache/00/", "lane/./cache", "/lane/cache", " lane/cache", "lane/../x"):
            with self.subTest(bad):
                self.env["LIFECYCLE_EXCLUDE"] = bad
                rc, out = self.sweep("--apply")
                self.assertEqual(rc, 4, out)
                self.assertIn("LIFECYCLE_EXCLUDE", out)

    def test_a_bad_journal_record_is_reported(self) -> None:
        d = self.aw / "status" / "lifecycle-journal"
        d.mkdir(parents=True)
        (d / "bad.json").write_text("[]")
        (d / "null.json").write_text("null")
        try:
            rc, out = self.sweep("--apply")
        except Exception as e:  # a crash is the failure this test is about
            self.fail(f"the sweep crashed on a bad journal record: {e!r}")
        self.assertEqual(rc, 0, out)
        notes = self.report()["journal"]["notes"]
        self.assertEqual(sum("not a JSON object" in n for n in notes), 2, notes)


if __name__ == "__main__":
    unittest.main()
