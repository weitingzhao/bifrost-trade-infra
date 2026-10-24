"""disk-guard.sh sweep, part 2 (W-31 4.6 S1): read errors and lsof (review 539 F1),
registration only, the machine lock and the second check after the rename (F4), shared roots
pruned by their tool (R9), the report, the host steps, check's exit codes, the installer.
Fixtures and SweepCase are in test_disk_guard.py.

    python3 -m pytest -q scripts/agent-host/test_disk_guard_runs.py
"""

from __future__ import annotations

import contextlib
import fcntl
import io
import json
import os
import plistlib
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import disk_guard  # noqa: E402
import disk_guard_apply  # noqa: E402
from disk_guard_base import QUARANTINE as QUAR  # noqa: E402
from test_disk_guard import CHAIN, SweepCase, backdate, chain, finished_review, go_build, go_mod, npm  # noqa: E402


class Runs(SweepCase):
    """Read errors, registration, locks, the second check, shared roots, the report, host steps."""

    def test_unreadable_directory_is_kept_with_the_reason(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root reads a mode-000 directory")
        cache = finished_review(self.aw, "codex-review-1")
        self.unreadable(cache / "ab")
        finished_review(self.aw, "codex-review-9")
        self.unreadable(self.aw / "codex-review-9")
        self.register("codex-review-*/go-cache\tgo-build\trun.done\treview cache")
        self.sweep("--apply")
        it = self.assertKept("codex-review-1/go-cache", "unreadable")
        self.assertIn("ab", it["detail"])
        self.assertIn("ermission denied", it["detail"])
        it9 = self.item("codex-review-9/go-cache")
        self.assertEqual((it9["action"], it9["reason"]), ("keep", "unreadable"), it9)
        os.chmod(self.aw / "codex-review-9", 0o755)
        self.assertTrue((self.aw / "codex-review-9" / "go-cache" / "00").is_dir())

    def test_lsof_failure_keeps_everything(self) -> None:
        finished_review(self.aw, "codex-review-1")
        self.register("codex-review-*/go-cache\tgo-build\trun.done\treview cache")
        (self.fake / "rc").write_text("1")
        (self.fake / "err").write_text("lsof: can't read kernel name list\n")
        self.sweep("--apply")
        it = self.assertKept("codex-review-1/go-cache", "open-files-unknown")
        self.assertIn("kernel name list", it["detail"])
        # failing without a word is still failing
        (self.fake / "err").unlink()
        self.sweep("--apply")
        it = self.assertKept("codex-review-1/go-cache", "open-files-unknown")
        self.assertIn("lsof exit 1", it["detail"])
        # a warning about this very volume is as bad as a failure
        (self.fake / "rc").write_text("0")
        (self.fake / "err").write_text(f"lsof: WARNING: can't stat() apfs file system {self.aw.parent}\n      Output information may be incomplete.\n")
        self.sweep("--apply")
        self.assertKept("codex-review-1/go-cache", "open-files-unknown")
        # review 543 A3: so is a warning about a mount inside AGENT_WORK
        (self.fake / "err").write_text(f"lsof: WARNING: can't stat() nfs file system {self.aw / '.cache' / 'go-mod'}\n      Output information may be incomplete.\n")
        self.sweep("--apply")
        self.assertKept("codex-review-1/go-cache", "open-files-unknown")

    # The one stderr form a sweep tolerates (Owner 2026-10-24, after review 543 A3): lsof's
    # three-line can't-stat warning for a mount point in the mount table, outside AGENT_WORK.
    # The path holds a UUID on a real Mac, so it is matched against the mount table, not set
    # in a configuration.
    SHARE = "/mnt/backup-share/4D3E36C4-0000-4000-8000-123456789ABC/TimeMachine"

    def warn(self, path: str, second: str = "Output information may be incomplete.",
             third: str = 'assuming "dev=36000349" from mount table', extra: str = "") -> None:
        lines = [f"lsof: WARNING: can't stat() smbfs file system {path}"]
        lines += [f"      {ln}" for ln in (second, third) if ln is not None]
        (self.fake / "err").write_text("\n".join(lines) + "\n" + extra)

    def mounts(self, *paths: str, linux: bool = False) -> None:
        rows = ["/dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)"]
        for p in paths:
            rows.append(f"/dev/sdb1 on {p} type cifs (rw,relatime)" if linux
                        else f"//you@backup-host._smb._tcp.local./TimeMachine on {p} (smbfs, nodev, nosuid, mounted by you)")
        (self.fake / "mount.out").write_text("\n".join(rows) + "\n")

    def test_the_cant_stat_warning_for_an_outside_mount(self) -> None:
        finished_review(self.aw, "codex-review-1")
        self.register("codex-review-*/go-cache\tgo-build\trun.done\treview cache")
        aw = str(self.aw)
        keeps = [
            ("names AGENT_WORK", lambda: (self.warn(aw), self.mounts(aw))),
            ("names a parent of AGENT_WORK", lambda: (self.warn(str(self.aw.parent)), self.mounts(str(self.aw.parent)))),
            ("names a mount inside AGENT_WORK", lambda: (self.warn(aw + "/.cache/go-mod"), self.mounts(aw + "/.cache/go-mod"))),
            ("names a path not in the mount table", lambda: (self.warn(self.SHARE), self.mounts("/mnt/elsewhere"))),
            ("has an extra unknown line", lambda: (self.warn(self.SHARE, extra="lsof: WARNING: something else\n"), self.mounts(self.SHARE))),
            ("has a different second line", lambda: (self.warn(self.SHARE, second="Output information is fine."), self.mounts(self.SHARE))),
            ("lacks the third line", lambda: (self.warn(self.SHARE, third=None), self.mounts(self.SHARE))),
            ("names a relative path", lambda: (self.warn("mnt/share"), self.mounts("/mnt/share"))),
        ]
        for why, seed in keeps:
            with self.subTest(why):
                seed()
                (self.fake / "mount.rc").write_text("0")
                self.sweep("--apply")
                self.assertKept("codex-review-1/go-cache", "open-files-unknown")
        with self.subTest("the mount table cannot be read"):
            self.warn(self.SHARE)
            self.mounts(self.SHARE)
            (self.fake / "mount.rc").write_text("1")
            self.sweep("--apply")
            self.assertKept("codex-review-1/go-cache", "open-files-unknown")
        (self.fake / "mount.rc").write_text("0")
        self.warn(self.SHARE)
        self.mounts(self.SHARE)
        self.sweep("--apply")
        self.assertDeleted("codex-review-1/go-cache")
        self.assertEqual(self.report()["lsof"]["tolerated"], [self.SHARE])

    def test_the_mount_table_in_both_formats(self) -> None:
        import disk_guard_base
        import disk_guard_roots
        cfg = disk_guard_base.load_config(self.env)
        for linux in (False, True):
            self.mounts(self.SHARE, "/mnt/with space", linux=linux)
            points, err = disk_guard_roots.mount_points(cfg)
            self.assertEqual(err, "")
            self.assertEqual(points, ["/", self.SHARE, "/mnt/with space"])
        (self.fake / "mount.out").write_text("")
        self.assertIn("no mount table", disk_guard_roots.mount_points(cfg)[1])

    def test_open_file_keeps_the_cache(self) -> None:
        lsof = shutil.which("lsof") or ("/usr/sbin/lsof" if os.path.exists("/usr/sbin/lsof") else None)
        if not lsof:
            self.skipTest("no lsof")
        self.env["LIFECYCLE_LSOF"] = lsof
        self.env["LIFECYCLE_MOUNT"] = "/sbin/mount"  # the real one: this Mac's lsof warns about its backup share
        cache = finished_review(self.aw, "codex-review-1")
        finished_review(self.aw, "codex-review-2")
        self.register("codex-review-*/go-cache\tgo-build\trun.done\treview cache")
        with open(cache / "00" / ("00" + "1" * 62 + "-a"), "rb"):
            self.sweep("--apply")
        self.assertKept("codex-review-1/go-cache", "open-files")
        self.assertDeleted("codex-review-2/go-cache")

    def test_unregistered_cache_is_only_reported(self) -> None:
        cache = finished_review(self.aw, "codex-review-7")
        (self.aw / ".cache").mkdir()
        (self.aw / ".cache" / "api-new.go").write_text("package api\n")
        backdate(go_build(self.aw / ".cache" / "go-build"), 60)
        self.sweep("--apply")
        it = self.assertKept("codex-review-7/go-cache", "unregistered")
        self.assertEqual(it["layout"], "go-build")
        self.assertTrue(it["run_done"])
        self.assertIn("confirmed in full", it["detail"])
        self.assertKept(".cache/api-new.go", "unregistered")
        self.assertKept(".cache/go-build", "unregistered")
        self.assertTrue((cache / "00").is_dir())

    def test_registry_errors_are_reported_and_ignored(self) -> None:
        finished_review(self.aw, "codex-review-1")
        self.register(
            "/abs/go-cache\tgo-build\tended\tx",
            "codex-review-1/../x\tgo-build\tended\tx",
            "codex-review-1/go-cache\tnode_modules\tended\tx",
            "go-cache\tgo-build\trun.done\tx",
            "codex-review-1/go-cache\tgo-build\tended",
            "codex-review-1/go-cache\tgo-build-chain\tcap=5\tx",
            "codex-review-1/go-cache\tgo-build\tcap=lots\tx",
            "only-two-columns\tgo-build",
        )
        rc, out = self.sweep("--apply")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(self.report()["errors"]), 8, self.report()["errors"])
        self.assertKept("codex-review-1/go-cache", "unregistered")

    def test_overlap_and_exclusions_keep(self) -> None:
        backdate(chain(self.aw / "w" / "cache"), 60)
        backdate(go_build(self.aw / "agentd" / "tasks" / "go-cache"), 60)
        self.env["LIFECYCLE_EXCLUDE"] = "agentd"
        self.register(
            "w/cache\tgo-build-chain\tended\tx",
            f"w/cache/{CHAIN[0]}\tgo-build-chain\tended\tx",
            "agentd/tasks/go-cache\tgo-build\tended\tagentd keeps its own root",
        )
        self.sweep("--apply")
        self.assertKept("w/cache", "registry-overlap")
        self.assertKept(f"w/cache/{CHAIN[0]}", "registry-overlap")
        self.assertKept("agentd/tasks/go-cache", "excluded")

    def test_a_live_lock_stops_the_run(self) -> None:
        cache = finished_review(self.aw, "codex-review-1")
        self.register("codex-review-*/go-cache\tgo-build\trun.done\treview cache")
        lock = self.aw / ".lifecycle.lock"
        lock.mkdir()
        (lock / "owner").write_text(json.dumps({"run_id": "other", "pid": os.getpid(), "host": socket.gethostname(), "started_at": "now"}))
        fd = os.open(lock / "lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # another sweep, alive
            rc, out = self.sweep("--apply")
        finally:
            os.close(fd)
        self.assertEqual(rc, 3, out)
        self.assertIn("another sweep holds", out)
        self.assertIn("run other", out)
        self.assertTrue((cache / "00").is_dir())
        self.assertFalse((self.aw / "status" / "lifecycle.json").exists())
        self.assertTrue((lock / "owner").is_file(), "someone else's lock stays")

    def test_a_dead_holders_lock_is_taken_over(self) -> None:
        finished_review(self.aw, "codex-review-1")
        self.register("codex-review-*/go-cache\tgo-build\trun.done\treview cache")
        p = subprocess.Popen(["true"])
        p.wait()
        lock = self.aw / ".lifecycle.lock"
        lock.mkdir()
        (lock / "owner").write_text(json.dumps({"run_id": "dead", "pid": p.pid, "host": socket.gethostname(), "started_at": "then"}))
        rc, out = self.sweep("--apply")  # nobody holds the flock: the kernel let go when it died
        self.assertEqual(rc, 0, out)
        self.assertDeleted("codex-review-1/go-cache")
        self.assertFalse((lock / "owner").exists())

    def test_a_write_between_check_and_delete_keeps_it(self) -> None:
        a = finished_review(self.aw, "codex-review-1")
        finished_review(self.aw, "codex-review-2")
        self.register("codex-review-*/go-cache\tgo-build\trun.done\treview cache")

        def another_session(staged: list) -> None:
            for it, pfd, name, q in staged:
                if it.path == "codex-review-1/go-cache":
                    Path(self_aw, "codex-review-1", q, "00", "late.go").write_text("package late\n")
                if it.path == "codex-review-2/go-cache":
                    os.unlink(os.path.join(self_aw, "codex-review-2", "run.done"))  # the review restarted

        self_aw = str(self.aw)
        disk_guard_apply.between_check_and_delete = another_session
        self.sweep("--apply")
        self.assertKept("codex-review-1/go-cache", "recheck-handwritten-file")
        self.assertTrue((a / "00" / "late.go").is_file(), "renamed back with the new file")
        self.assertKept("codex-review-2/go-cache", "recheck-no-run-done")
        self.assertIn("renamed back", self.item("codex-review-2/go-cache")["detail"])
        self.assertFalse(any(QUAR in n for d in ("codex-review-1", "codex-review-2") for n in os.listdir(self.aw / d)))

    def test_a_rename_left_by_a_dead_sweep_is_finished_or_kept(self) -> None:
        tail = QUAR + "20261024T000000Z-1"
        good = finished_review(self.aw, "codex-review-1")
        os.rename(good, str(good) + tail)
        recorded = self.journal("codex-review-1/go-cache", "codex-review-1/go-cache" + tail)
        bad = finished_review(self.aw, "codex-review-2")
        (bad / "00" / "draft.go").write_text("package d\n")
        backdate(bad, 60)
        os.rename(bad, str(bad) + tail)
        self.journal("codex-review-2/go-cache", "codex-review-2/go-cache" + tail)
        # review 544 A2: the suffix alone proves nothing
        stray = finished_review(self.aw, "codex-review-3")
        os.rename(stray, str(stray) + tail)
        other = finished_review(self.aw, "codex-review-4")
        os.rename(other, str(other) + tail)
        self.journal("codex-review-4/go-cache", "codex-review-4/go-cache" + tail, root=(1, 2))  # another directory
        self.register("codex-review-*/go-cache\tgo-build\trun.done\treview cache")
        self.sweep("--apply")
        self.assertDeleted("codex-review-1/go-cache" + tail)
        self.assertFalse(recorded.exists(), "the journal entry goes with the root")
        self.assertKept("codex-review-2/go-cache" + tail, "handwritten-file")
        self.assertKept("codex-review-3/go-cache" + tail, "unrecorded-quarantine-name")
        it = self.assertKept("codex-review-4/go-cache" + tail, "unrecorded-quarantine-name")
        self.assertIn("another directory", it["detail"])

    def test_shared_roots_over_the_cap_are_removed_after_the_same_checks(self) -> None:
        self.tool("go", "npm")  # the tools follow the path, so they are not called (review 543 A2)
        shared = self.aw / ".cache"
        go_build(shared / "go-build")
        go_mod(shared / "go-mod")
        npm(shared / "npm")
        go_build(shared / "go-build-2")
        (shared / "go-build-2" / "00" / "notes.go").write_text("package notes\n")
        go_build(shared / "go-build-3")
        self.register(
            ".cache/go-build\tgo-build\tcap=0\tshared",
            ".cache/go-mod\tgo-mod\tcap=0\tshared",
            ".cache/npm\tnpm\tcap=100\tshared",
            ".cache/go-build-2\tgo-build\tcap=0\tshared",
            ".cache/go-build-3\tgo-build\tcap=0\tshared",
        )
        self.sweep()
        self.assertEqual(self.item(".cache/go-build")["action"], "would-prune")
        self.assertTrue((shared / "go-build" / "00").is_dir())

        def a_build_starts(staged: list) -> None:
            for it, pfd, name, q in staged:
                if it.path == ".cache/go-build-3":
                    Path(shared, q, "ab", "notes.md").write_text("written during the sweep\n")

        disk_guard_apply.between_check_and_delete = a_build_starts
        self.sweep("--apply")
        self.assertEqual(self.calls.read_text(), "", "no tool is called")
        for p in (".cache/go-build", ".cache/go-mod"):
            self.assertEqual(self.item(p)["action"], "pruned")
            self.assertFalse(os.path.lexists(self.aw / p))
        self.assertKept(".cache/npm", "under-cap")
        self.assertKept(".cache/go-build-2", "handwritten-file")
        self.assertKept(".cache/go-build-3", "recheck-handwritten-file")
        self.assertTrue((shared / "go-build-3" / "ab" / "notes.md").is_file())

    def test_report_has_free_space_counts_and_reasons(self) -> None:
        finished_review(self.aw, "codex-review-1")
        no_done = self.aw / "codex-review-2"
        no_done.mkdir()
        go_build(no_done / "go-cache")
        self.register("codex-review-*/go-cache\tgo-build\trun.done\treview cache")
        self.sweep()
        r = self.report()
        self.assertGreater(r["volume"]["free_bytes"], 0)
        self.assertIn(r["volume"]["level"], ("ok", "warn", "stop"))
        self.assertEqual(r["counts"], {"would-delete": 1, "keep": 1})
        self.assertEqual(r["kept_reasons"], {"no-run-done": 1})
        self.assertEqual(r["registries"][0]["entries"], 1)
        self.assertTrue(r["lsof"]["ok"])

    def test_host_steps_change_nothing_in_a_report_only_run(self) -> None:
        self.tool("go", "docker", "pgrep", "ipcs", "ipcrm", "tmutil")
        default_cache = go_build(self.outside / "go-build-default")
        p = subprocess.Popen(["true"])
        p.wait()
        self.env.update(FAKE_GOCACHE=str(default_cache), FAKE_DEAD_PID=str(p.pid), DEFAULT_GOCACHE_CAP_GB="0",
                        WARN_GB="1000000000", STOP_GB="1000000000")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            disk_guard.main(["sweep"], self.env)
        calls = self.calls.read_text()
        for mutating in ("clean", "prune", "ipcrm", "thinlocalsnapshots"):
            self.assertNotIn(mutating, calls, calls)
        steps = {s["step"]: s["action"] for s in self.report()["host_steps"]}
        self.assertEqual(steps["default-go-cache"], "would-clean")
        self.assertEqual(steps["docker"], "would-prune")
        if sys.platform == "darwin":
            self.assertEqual(steps["shared-memory"], "would-remove")
            self.assertEqual(steps["time-machine"], "would-thin")
        with contextlib.redirect_stdout(out):
            disk_guard.main(["sweep", "--apply"], self.env)
        calls = self.calls.read_text()
        self.assertIn("go clean -cache", calls)
        self.assertIn("docker builder prune -a -f --filter until=168h", calls)
        if sys.platform == "darwin":
            self.assertIn("ipcrm -m 65536", calls)
            self.assertIn("tmutil thinlocalsnapshots / 60000000000 4", calls)
        self.assertTrue((default_cache / "00").is_dir(), "the fake go removed nothing")

    def test_check_exit_codes(self) -> None:
        def check(**kw: str) -> int:
            with contextlib.redirect_stdout(io.StringIO()):
                return disk_guard.main(["check"], {**self.env, **kw})

        self.assertEqual(check(WARN_GB="0", STOP_GB="0"), 0)
        self.assertEqual(check(WARN_GB="1000000000", STOP_GB="0"), 1)
        self.assertEqual(check(WARN_GB="1000000000", STOP_GB="1000000000"), 2)
        self.assertEqual(check(DISK_GUARD_VOLUME=str(self.aw / "missing")), 2, "unreadable counts as under the stop line")
        self.assertEqual(check(WARN_GB="10", STOP_GB="20"), 2)
        self.assertEqual(check(WARN_GB="lots"), 2)


class Install(unittest.TestCase):
    def test_plist_renders_report_only_unless_asked(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "AGENT_WORK": "/Users/you/agent-work"}
            for args, tail in (([], "sweep"), (["--apply"], "--apply")):
                out = Path(d) / "p.plist"
                subprocess.run(["bash", str(HERE / "install-disk-guard.sh"), "--render-plist", str(out), *args], env=env, check=True)
                pl = plistlib.loads(out.read_bytes())
                self.assertEqual(pl["Label"], "com.bifrost.disk-guard")
                self.assertEqual(pl["ProgramArguments"][:3], ["/bin/bash", "/Users/you/agent-work/bin/disk-guard/disk-guard.sh", "sweep"])
                self.assertEqual(pl["ProgramArguments"][-1], tail)
                self.assertEqual(pl["EnvironmentVariables"]["AGENT_WORK"], "/Users/you/agent-work")
                self.assertNotIn("@", out.read_text().split("-->", 1)[1])
                if shutil.which("plutil"):
                    subprocess.run(["plutil", "-lint", str(out)], check=True, capture_output=True)

    @unittest.skipUnless(sys.platform == "darwin", "the macOS install path")
    def test_install_dry_run_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "home"
            (home / "agent-work").mkdir(parents=True)
            env = {**os.environ, "HOME": str(home), "AGENT_WORK": str(home / "agent-work")}
            r = subprocess.run(["bash", str(HERE / "install-disk-guard.sh"), "--dry-run", "--apply"], env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("would run: launchctl bootstrap", r.stdout)
            self.assertIn("dry run, nothing changed", r.stdout)
            self.assertEqual(sorted(p.name for p in home.rglob("*")), ["agent-work"])

    def test_installer_copies_every_module(self) -> None:
        text = (HERE / "install-disk-guard.sh").read_text()
        line = next(ln for ln in text.splitlines() if ln.startswith("modules="))
        listed = sorted(line.split("=", 1)[1].strip('"').split())
        self.assertEqual(listed, sorted(p.name for p in HERE.glob("disk_guard*.py")))

    def test_systemd_units(self) -> None:
        svc = (HERE / "bifrost-disk-guard@.service").read_text()
        self.assertIn("ExecStart=/bin/bash /usr/local/libexec/bifrost/disk-guard/disk-guard.sh sweep $DISK_GUARD_ARGS\n", svc)
        self.assertIn("Environment=DISK_GUARD_ARGS=\n", svc)
        self.assertIn("User=%i\n", svc)
        self.assertIn("Environment=LIFECYCLE_EXCLUDE=agentd\n", svc)
        timer = (HERE / "bifrost-disk-guard@.timer").read_text()
        self.assertIn("OnUnitInactiveSec=1h\n", timer)
        self.assertIn("WantedBy=timers.target\n", timer)

if __name__ == "__main__":
    unittest.main()
