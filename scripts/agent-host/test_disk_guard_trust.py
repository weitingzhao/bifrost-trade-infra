"""disk-guard.sh sweep, part 6 (W-31 4.6 S1; review 549): a resumed removal allows only the
directory modes the sweeper recorded before changing them (A1); the state files are private
whatever the umask (C1); an inventory with a field out of type or range is unusable, never an
exception (C2); the journal counts in the report. Fixtures and SweepCase are in
test_disk_guard.py.

    python3 -m pytest -q scripts/agent-host/test_disk_guard_trust.py
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import disk_guard_apply  # noqa: E402
from disk_guard_base import QUARANTINE as QUAR  # noqa: E402
from test_disk_guard import SweepCase, finished_review, go_build, go_mod  # noqa: E402
from test_disk_guard_recovery import Crashed  # noqa: E402

MODULE = "codex-review-*/.gocache\tgo-mod\trun.done\treview module cache"
REVIEW = "codex-review-*/go-cache\tgo-build\trun.done\treview cache"


class Trust549(SweepCase):
    def journal_dir(self) -> Path:
        return self.aw / "status" / "lifecycle-journal"

    def left(self, review: str) -> Path:
        return next(p for p in (self.aw / review).iterdir() if QUAR in p.name)

    def crash_after_inventory(self) -> None:
        def die(it) -> None:
            raise Crashed(9)

        disk_guard_apply.after_inventory_written = die
        with self.assertRaises(Crashed):
            self.sweep("--apply")
        disk_guard_apply.after_inventory_written = None

    def crash_during_removal(self, when) -> None:
        def hook(crel: str) -> None:
            if when(crel):
                raise Crashed(9)

        disk_guard_apply.during_removal = hook
        with self.assertRaises(Crashed):
            self.sweep("--apply")
        disk_guard_apply.during_removal = None

    # A1: only recorded chmods

    def test_an_outside_chmod_before_any_of_the_sweepers_is_kept(self) -> None:
        finished_review(self.aw, "codex-review-1", ".gocache", go_mod)
        self.register(MODULE)
        self.crash_after_inventory()
        left = self.left("codex-review-1")
        self.assertFalse(list(self.journal_dir().glob("*.chmods")), "the sweeper changed no mode")
        os.chmod(left / "example.com" / "m@v1.0.0", 0o755)  # someone starts editing the module
        self.sweep("--apply")
        it = self.assertKept(str(left.relative_to(self.aw)), "changed-since-stopped")
        self.assertIn("example.com/m@v1.0.0 was replaced or changed", it["detail"])

    def test_a_recorded_chmod_allows_only_its_own_mode(self) -> None:
        finished_review(self.aw, "codex-review-1", ".gocache", go_mod)
        self.register(MODULE)
        self.crash_during_removal(lambda crel: crel.startswith("example.com/m@v1.0.0/"))
        left = self.left("codex-review-1")
        log = next(self.journal_dir().glob("*.chmods")).read_text()
        self.assertIn('"example.com/m@v1.0.0"', log)
        os.chmod(left / "example.com" / "m@v1.0.0", 0o777)  # not the mode the sweeper recorded
        self.sweep("--apply")
        self.assertKept(str(left.relative_to(self.aw)), "changed-since-stopped")

    def test_a_resumed_cap_root_says_what_it_finished(self) -> None:
        go_build(self.aw / ".cache" / "go-build")
        self.register(".cache/go-build\tgo-build\tcap=0\tshared")
        self.crash_during_removal(lambda crel: True)
        self.sweep("--apply")
        it = next(i for i in self.report()["items"] if i["path"].startswith(".cache/go-build" + QUAR))
        self.assertEqual(it["action"], "pruned", it)
        self.assertIn("finished the removal a stopped sweep began", it["detail"])

    # C1: private state files whatever the umask

    def test_state_files_are_private_under_umask_022(self) -> None:
        old = os.umask(0o022)
        try:
            self.journal_dir().mkdir(parents=True)
            os.chmod(self.journal_dir(), 0o755)  # wider than it should be, and this user's
            finished_review(self.aw, "codex-review-1", ".gocache", go_mod)
            self.register(MODULE)
            self.crash_during_removal(lambda crel: crel.startswith("example.com/m@v1.0.0/"))
        finally:
            os.umask(old)
        self.assertEqual(stat.S_IMODE(os.stat(self.journal_dir()).st_mode), 0o700)
        files = list(self.journal_dir().iterdir())
        self.assertEqual(sorted(p.suffix for p in files), [".chmods", ".inventory", ".json"])
        for p in files:
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600, p.name)

    def test_a_journal_path_that_is_not_a_directory_is_refused(self) -> None:
        cache = finished_review(self.aw, "codex-review-1")
        self.register(REVIEW)
        (self.aw / "status").mkdir()
        (self.aw / "status" / "lifecycle-journal").write_text("not a directory\n")
        self.sweep("--apply")
        self.assertKept("codex-review-1/go-cache", "journal-write-failed")
        self.assertTrue((cache / "00").is_dir(), "not renamed, not removed")

    # C2: strict inventory fields

    def corrupt(self, edit, review: str = "codex-review-1") -> Path:
        finished_review(self.aw, review)
        self.register(REVIEW)
        self.crash_during_removal(lambda crel: crel.startswith("00/"))
        entry = next(p for p in self.journal_dir().glob("*.json") if json.loads(p.read_text())["quarantine"].startswith(review + "/"))
        inv = Path(str(entry) + ".inventory")
        inv.write_text(edit(inv.read_text()))
        return self.left(review)

    def assert_unusable(self, left: Path) -> None:
        try:
            self.sweep("--apply")
        except Exception as e:  # an exception is the failure this test is about
            self.fail(f"the sweep raised on a bad inventory: {e!r}")
        self.assertKept(str(left.relative_to(self.aw)), "journal-inventory-unusable")
        self.assertTrue(left.is_dir())

    def test_a_number_out_of_range(self) -> None:
        self.assert_unusable(self.corrupt(lambda t: re.sub(r'"root": \[(\d+)', '"root": [1e400', t, count=1)))

    def test_a_leaf_that_is_not_a_string(self) -> None:
        self.assert_unusable(self.corrupt(lambda t: t.replace('"leaf": null', '"leaf": []').replace('"redact": false', '"redact": true')))

    def test_other_fields_out_of_type(self) -> None:
        for name, edit in (
            ("redact as a number", lambda t: t.replace('"redact": false', '"redact": 0')),
            ("a signature number as a string", lambda t: re.sub(r'("inv": \{"[^"]+": \[)(\d+)', r'\1"\2"', t, count=1)),
            ("a signature number as true", lambda t: re.sub(r'("inv": \{"[^"]+": \[)(\d+)', r'\1true', t, count=1)),
            ("a listing with a number", lambda t: t.replace('"listed": {"": [', '"listed": {"": [7, ', 1)),
        ):
            with self.subTest(name):
                self.assert_unusable(self.corrupt(edit, f"codex-review-{name.replace(' ', '-')}"))

    # D: the journal counts

    def test_the_journal_counts(self) -> None:
        d = self.journal_dir()
        d.mkdir(parents=True)
        (d / "bad.json").write_text("[]")
        self.sweep("--apply")
        j = self.report()["journal"]
        self.assertEqual((j["loaded_entries"], j["open_entries_at_end"], j["bad_files_at_end"]), (0, 0, 1))
        # a journal path that cannot be listed (a mode-000 directory of this user is now
        # tightened to 0700 and read, review 550 A1)
        for p in d.iterdir():
            p.unlink()
        d.rmdir()
        d.write_text("not a directory\n")
        self.sweep("--apply")
        self.assertEqual(self.report()["journal"]["open_entries_at_end"], "unknown")


if __name__ == "__main__":
    unittest.main()
