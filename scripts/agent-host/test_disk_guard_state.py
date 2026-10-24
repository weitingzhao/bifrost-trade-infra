"""disk-guard.sh sweep, part 7 (W-31 4.6 S1; review 550): the journal directory is checked on
every run that loads state, not only when an entry is written (A1); no diagnostic carries a
path, key or name from a state file, and the report is 0600 (A2); a classified inventory is
not kept on the item (C1); the chmod log's directory is fsynced when it is created.
Fixtures and SweepCase are in test_disk_guard.py.

    python3 -m pytest -q scripts/agent-host/test_disk_guard_state.py
"""

from __future__ import annotations

import json
import os
import stat
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import disk_guard_apply  # noqa: E402
import disk_guard_items  # noqa: E402
import disk_guard_state  # noqa: E402
from disk_guard_base import O_DIR, QUARANTINE as QUAR, load_config  # noqa: E402
from disk_guard_inventory import Inventory  # noqa: E402
from disk_guard_roots import OpenFiles, parse_registry  # noqa: E402
from test_disk_guard import SECRET, SweepCase, backdate, chain, finished_review, go_mod  # noqa: E402
from test_disk_guard_recovery import Crashed  # noqa: E402

REVIEW = "codex-review-*/go-cache\tgo-build\trun.done\treview cache"
CHAIN_ROOT = ".cache/go-build GOMODCACHE="


class State550(SweepCase):
    def tearDown(self) -> None:
        disk_guard_state._me = lambda: os.geteuid()
        super().tearDown()

    def journal_dir(self) -> Path:
        return self.aw / "status" / "lifecycle-journal"

    def crash(self, when=lambda crel: True) -> None:
        def hook(crel: str) -> None:
            if when(crel):
                raise Crashed(9)

        disk_guard_apply.during_removal = hook
        with self.assertRaises(Crashed):
            self.sweep("--apply")
        disk_guard_apply.during_removal = None

    def left(self, parent: str) -> str:
        p = next(p for p in (self.aw / parent).iterdir() if QUAR in p.name)
        return str(p.relative_to(self.aw))

    def report_text(self) -> str:
        return (self.aw / "status" / "lifecycle.json").read_text()

    # A1: the journal directory on the load and resume path

    def test_an_old_leftover_alone_gets_its_state_made_private(self) -> None:
        finished_review(self.aw, "codex-review-1")
        self.register(REVIEW)
        self.crash()
        # as a previous version left it, under umask 022
        os.chmod(self.journal_dir(), 0o755)
        for p in self.journal_dir().iterdir():
            os.chmod(p, 0o644)
        # excluded, so its inventory is never opened: only the check of the whole directory
        # can bring that file to 0600
        self.env["LIFECYCLE_EXCLUDE"] = "codex-review-1"
        self.sweep()  # report only: nothing new to journal, only the old leftover
        self.assertEqual(stat.S_IMODE(os.stat(self.journal_dir()).st_mode), 0o700)
        for p in self.journal_dir().iterdir():
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600, p.name)

    def test_a_journal_directory_of_another_owner_grants_nothing(self) -> None:
        finished_review(self.aw, "codex-review-1")
        self.register(REVIEW)
        self.crash()
        old = self.left("codex-review-1")
        fresh = finished_review(self.aw, "codex-review-2")
        disk_guard_state._me = lambda: os.geteuid() + 1  # the directory now "belongs to someone else"
        rc, out = self.sweep("--apply")
        self.assertEqual(rc, 0, out)
        it = self.assertKept(old, "journal-refused")
        self.assertIn("belongs to uid", it["detail"])
        self.assertKept("codex-review-2/go-cache", "journal-write-failed")
        self.assertTrue((fresh / "00").is_dir())

    # A2: nothing from the state files in the report

    def test_a_corrupt_chain_listing_leaks_nothing(self) -> None:
        backdate(chain(self.aw / CHAIN_ROOT), 60)
        self.register(f"{CHAIN_ROOT}\tgo-build-chain\tended\tx")
        out_crash = self.crash_output()
        inv = next(self.journal_dir().glob("*.inventory"))
        data = json.loads(inv.read_text())
        key = next(k for k in data["listed"] if SECRET in k)
        data["listed"][key] = [7]
        inv.write_text(json.dumps(data))
        rc, out = self.sweep("--apply")
        it = self.assertKept(self.left(".cache"), "journal-inventory-unusable")
        self.assertIn("listed entry", it["detail"])
        for text in (self.report_text(), out, out_crash):
            self.assertNotIn(SECRET, text)

    def test_a_corrupt_chmod_record_leaks_nothing(self) -> None:
        backdate(chain(self.aw / CHAIN_ROOT), 60)
        self.register(f"{CHAIN_ROOT}\tgo-build-chain\tended\tx")
        self.crash_output()
        inv = next(self.journal_dir().glob("*.inventory"))
        key = next(k for k in json.loads(inv.read_text())["inv"] if SECRET in k)
        Path(str(inv)[: -len(".inventory")] + ".chmods").write_text(json.dumps([key + "/x", 1, 2, 0o40755]) + "\n")
        rc, out = self.sweep("--apply")
        it = self.assertKept(self.left(".cache"), "journal-inventory-unusable")
        self.assertIn("chmod record 0", it["detail"])
        for text in (self.report_text(), out):
            self.assertNotIn(SECRET, text)

    def crash_output(self) -> str:
        import contextlib
        import io

        def hook(crel: str) -> None:
            raise Crashed(9)

        disk_guard_apply.during_removal = hook
        buf = io.StringIO()
        with self.assertRaises(Crashed), contextlib.redirect_stdout(buf):
            import disk_guard
            disk_guard.main(["sweep", "--no-host", "--apply"], self.env)
        disk_guard_apply.during_removal = None
        return buf.getvalue()

    def test_the_report_is_private_under_umask_022(self) -> None:
        old = os.umask(0o022)
        try:
            finished_review(self.aw, "codex-review-1")
            self.register(REVIEW)
            self.sweep()
        finally:
            os.umask(old)
        self.assertEqual(stat.S_IMODE(os.stat(self.aw / "status" / "lifecycle.json").st_mode), 0o600)

    # C1: the item keeps no inventory

    def test_a_classified_leftover_holds_no_inventory(self) -> None:
        finished_review(self.aw, "codex-review-1")
        self.register(REVIEW)
        self.crash()
        left = self.aw / self.left("codex-review-1")
        (left / "ab" / "late.go").write_text("package late\n")  # resumable() refuses it
        cfg = load_config(self.env)
        journal, _, _ = disk_guard_state.journal_load(cfg)
        entries = parse_registry(str(self.registry), True)[0]
        aw_fd = os.open(cfg.agent_work, O_DIR)
        try:
            items = disk_guard_items.registered_items(cfg, entries)
            lsof = OpenFiles(cfg)
            for it in items:
                disk_guard_items.classify(cfg, aw_fd, it, lsof, 0.0, journal)
        finally:
            os.close(aw_fd)
        it = next(i for i in items if i.path == str(left.relative_to(self.aw)))
        self.assertEqual(it.reason, "changed-since-stopped")
        held = [v for v in vars(it).values() if isinstance(v, Inventory)]
        held += [v for v in (it.journal or {}).values() if isinstance(v, Inventory)]
        self.assertEqual(held, [], "the item kept the inventory")

    # the chmod log's directory entry is made durable when the log is created

    def test_the_chmod_log_directory_is_fsynced_when_created(self) -> None:
        finished_review(self.aw, "codex-review-1", ".gocache", go_mod)
        self.register("codex-review-*/.gocache\tgo-mod\trun.done\treview module cache")
        seen: list = []
        real = disk_guard_state._fsync_dir

        def watch(d: str) -> None:
            seen.append((d, any(n.endswith(".chmods") for n in os.listdir(d))))
            real(d)

        disk_guard_state._fsync_dir = watch
        try:
            self.crash(lambda crel: crel.startswith("example.com/m@v1.0.0/"))
        finally:
            disk_guard_state._fsync_dir = real
        self.assertIn((str(self.journal_dir()), True), seen)


if __name__ == "__main__":
    unittest.main()
