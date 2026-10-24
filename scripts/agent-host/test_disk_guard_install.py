"""install-disk-guard.sh --alongside / --uninstall-alongside (W-31 4.6 S1): the trial beside
the old disk-guard, which keeps cleaning, installed into a temp HOME with a fake launchctl;
and the new sweep running while the old one deletes (an entry or a root that disappears
between its checks is kept or gone, never an error that stops the run).

    python3 -m pytest -q scripts/agent-host/test_disk_guard_install.py
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import disk_guard_apply  # noqa: E402
import disk_guard_items  # noqa: E402
import disk_guard_layout  # noqa: E402
from test_disk_guard import FAKE_TOOL, SweepCase, finished_review  # noqa: E402

MODULES = sorted(p.name for p in HERE.glob("disk_guard*.py"))
FAKE_LAUNCHCTL = '#!/usr/bin/env bash\necho "launchctl $*" >> "${FAKE_CALLS:?}"\nexit 0\n'
REVIEW = "codex-review-*/go-cache\tgo-build\trun.done\treview cache"


@unittest.skipUnless(sys.platform == "darwin", "the macOS install path")
class Alongside(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.home = base / "home"
        self.work = self.home / "agent-work"
        (self.work / "bin").mkdir(parents=True)
        self.old_script = self.work / "bin" / "disk-guard.sh"
        self.old_script.write_text("#!/usr/bin/env bash\n# the old disk-guard\n")
        self.agents = self.home / "Library" / "LaunchAgents"
        self.agents.mkdir(parents=True)
        self.old_plist = self.agents / "com.bifrost.disk-guard.plist"
        self.old_plist.write_text("<plist>the old one</plist>\n")
        self.bin = base / "bin"
        self.bin.mkdir()
        (self.bin / "launchctl").write_text(FAKE_LAUNCHCTL)
        (self.bin / "launchctl").chmod(0o755)
        self.calls = base / "calls"
        self.calls.write_text("")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("LIFECYCLE_", "AGENT_WORK"))}
        self.env.update(HOME=str(self.home), FAKE_CALLS=str(self.calls), PATH=f"{self.bin}:{os.environ['PATH']}")
        self.dest = self.work / "bin" / "disk-guard-next"
        self.plist = self.agents / "com.bifrost.disk-guard.next.plist"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_installer(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(HERE / "install-disk-guard.sh"), *args], env=self.env, capture_output=True, text=True, timeout=120)

    def tree(self) -> dict:
        return {str(p.relative_to(self.home)): (p.read_bytes() if p.is_file() else None) for p in sorted(self.home.rglob("*"))}

    def assert_old_untouched(self) -> None:
        self.assertEqual(self.old_script.read_text(), "#!/usr/bin/env bash\n# the old disk-guard\n")
        self.assertEqual(self.old_plist.read_text(), "<plist>the old one</plist>\n")
        self.assertFalse([p for p in self.home.rglob("*.pre-repo-*")])
        self.assertNotIn("com.bifrost.disk-guard ", self.calls.read_text() + " ")
        self.assertNotIn("com.bifrost.disk-guard.plist", self.calls.read_text())

    def test_dry_run_prints_every_file_and_the_plist_and_writes_nothing(self) -> None:
        before = self.tree()
        r = self.run_installer("--alongside", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        for f in ["disk-guard.sh", "cache-roots.tsv", "INSTALLED-BY", *MODULES]:
            self.assertIn(f"would write {self.dest}/{f}\n", r.stdout)
        self.assertIn(f"would write {self.plist}:\n", r.stdout)
        self.assertIn("<string>com.bifrost.disk-guard.next</string>", r.stdout)
        self.assertIn(f"<string>{self.work}/.lifecycle-next.lock</string>", r.stdout)
        self.assertNotIn("--apply", r.stdout)
        self.assertEqual(self.tree(), before, "a dry run wrote something")
        self.assertEqual(self.calls.read_text(), "")

    def test_install_beside_the_old_one(self) -> None:
        r = self.run_installer("--alongside")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_old_untouched()
        self.assertTrue(self.dest.is_dir(), "no disk-guard-next directory")
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), sorted(["disk-guard.sh", "cache-roots.tsv", "INSTALLED-BY", *MODULES]))
        self.assertTrue(self.plist.is_file(), "no .next plist")
        pl = plistlib.loads(self.plist.read_bytes())
        self.assertEqual(pl["Label"], "com.bifrost.disk-guard.next")
        self.assertEqual(pl["ProgramArguments"], ["/bin/bash", f"{self.dest}/disk-guard.sh", "sweep"])
        self.assertEqual(pl["StartInterval"], 3600)
        self.assertFalse(pl["RunAtLoad"])
        self.assertEqual(pl["StandardOutPath"], f"{self.work}/disk-guard-next.log")
        env = pl["EnvironmentVariables"]
        self.assertEqual(env.get("AGENT_WORK"), str(self.work))
        self.assertEqual(env.get("LIFECYCLE_STATUS_DIR"), f"{self.work}/status/disk-guard-next")
        self.assertEqual(env.get("LIFECYCLE_LOCK"), f"{self.work}/.lifecycle-next.lock")
        self.assertEqual(env.get("LIFECYCLE_MACHINE_ROOTS"), f"{self.work}/status/cache-roots.tsv")
        uid = os.getuid()
        self.assertEqual(self.calls.read_text().splitlines(),
                         [f"launchctl bootout gui/{uid}/com.bifrost.disk-guard.next", f"launchctl bootstrap gui/{uid} {self.plist}"])
        self.assert_old_untouched()
        self.assertIn("untouched:", r.stdout)
        # the installed copy runs on its own, with the plist's environment, and keeps to its paths
        fakes = Path(self.tmp.name) / "fakes"
        fakes.mkdir()
        for n in ("go", "docker", "pgrep", "ipcs", "ipcrm", "tmutil"):
            (fakes / n).write_text(FAKE_TOOL)
            (fakes / n).chmod(0o755)
        run_env = {**{k: v for k, v in os.environ.items() if not k.startswith(("LIFECYCLE_", "GO"))}, **env,
                   "HOME": str(self.home), "FAKE_CALLS": str(self.calls), "PATH": f"{fakes}:{env['PATH']}"}
        s = subprocess.run(pl["ProgramArguments"], env=run_env, capture_output=True, text=True, timeout=300)
        self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
        self.assertTrue((self.work / "status" / "disk-guard-next" / "lifecycle.json").is_file())
        self.assertTrue((self.work / ".lifecycle-next.lock" / "lock").is_file())
        self.assertFalse((self.work / "status" / "lifecycle.json").exists())
        self.assertFalse((self.work / ".lifecycle.lock").exists())
        self.assert_old_untouched()

    def test_apply_is_refused_alongside(self) -> None:
        before = self.tree()
        r = self.run_installer("--alongside", "--apply")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--apply is refused", r.stderr)
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.calls.read_text(), "")

    def test_uninstall_removes_only_the_next_label(self) -> None:
        self.assertEqual(self.run_installer("--alongside").returncode, 0)
        (self.work / "status" / "disk-guard-next").mkdir(parents=True)
        (self.work / "status" / "disk-guard-next" / "lifecycle.json").write_text("{}")
        self.calls.write_text("")
        before = self.tree()
        r = self.run_installer("--uninstall-alongside", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("would run: rm -rf --", r.stdout)
        self.assertEqual(self.tree(), before)
        r = self.run_installer("--uninstall-alongside")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.plist.exists())
        self.assertTrue((self.work / "status" / "disk-guard-next" / "lifecycle.json").is_file(), "the reports stay")
        self.assertEqual(self.calls.read_text().splitlines(), [f"launchctl bootout gui/{os.getuid()}/com.bifrost.disk-guard.next"])
        self.assert_old_untouched()

    def test_uninstall_refuses_a_directory_it_did_not_install(self) -> None:
        self.dest.mkdir(parents=True)
        (self.dest / "mine.txt").write_text("not the installer's\n")
        r = self.run_installer("--uninstall-alongside")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not this installer's", r.stderr)
        self.assertTrue((self.dest / "mine.txt").is_file())


class OsDeleting:
    """os, except that stat() of one name first removes it: the old disk-guard deleting a
    file in the instant between the new sweep listing a directory and reading the entry."""

    def __init__(self, victim: str) -> None:
        self.victim = victim

    def __getattr__(self, name: str):
        return getattr(os, name)

    def stat(self, name, *args, **kwargs):
        if name == self.victim and kwargs.get("dir_fd") is not None:
            try:
                os.unlink(name, dir_fd=kwargs["dir_fd"])
            except FileNotFoundError:
                pass
        return os.stat(name, *args, **kwargs)


class Coexist(SweepCase):
    """The old disk-guard deletes review caches by name while the new sweep reads them."""

    def sweep(self, *args: str) -> tuple:
        try:
            return super().sweep(*args)
        except Exception as e:  # stopping the run is the failure these tests are about
            self.fail(f"the sweep stopped on something the old disk-guard removed: {e!r}")

    def test_an_entry_removed_while_it_is_read_is_kept_as_gone(self) -> None:
        finished_review(self.aw, "codex-review-1")
        finished_review(self.aw, "codex-review-2")
        self.register(REVIEW)
        real = disk_guard_layout.os
        disk_guard_layout.os = OsDeleting("ab" + "2" * 62 + "-d")
        try:
            rc, out = self.sweep()
        finally:
            disk_guard_layout.os = real
        self.assertEqual(rc, 0, out)
        for n in (1, 2):
            it = self.item(f"codex-review-{n}/go-cache")
            self.assertEqual((it["action"], it["reason"]), ("keep", "gone"), it)

    def test_a_root_removed_after_it_was_found_is_kept_as_gone(self) -> None:
        finished_review(self.aw, "codex-review-1")
        self.register(REVIEW)
        real = disk_guard_items.expand

        def expand_then_old_cleaner(agent_work, entry):
            found = real(agent_work, entry)
            shutil.rmtree(self.aw / "codex-review-1" / "go-cache")
            return found

        disk_guard_items.expand = expand_then_old_cleaner
        try:
            rc, out = self.sweep("--apply")
        finally:
            disk_guard_items.expand = real
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.item("codex-review-1/go-cache")["reason"], "gone")

    def test_a_root_removed_between_the_check_and_the_rename_is_kept_as_gone(self) -> None:
        finished_review(self.aw, "codex-review-1")
        self.register(REVIEW)

        def old_cleaner(todo: list) -> None:
            shutil.rmtree(self.aw / "codex-review-1" / "go-cache")

        disk_guard_apply.between_check_and_rename = old_cleaner
        rc, out = self.sweep("--apply")
        self.assertEqual(rc, 0, out)
        it = self.item("codex-review-1/go-cache")
        self.assertEqual((it["action"], it["reason"]), ("keep", "gone"), it)
        self.assertEqual(self.report()["journal"]["open_entries_at_end"], 0)


if __name__ == "__main__":
    unittest.main()
