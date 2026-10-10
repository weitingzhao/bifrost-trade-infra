"""Tests for check_hardcoded_paths.py (run: python3 -m unittest agent-config/scripts/test_check_hardcoded_paths.py)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_hardcoded_paths as chp  # noqa: E402

# Built by concatenation so this file carries no home path of its own.
HOME = "/" + "Users" + "/"


def git_repo(files: dict[str, str]) -> Path:
    repo = Path(tempfile.mkdtemp(prefix="hcp-"))
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    for name, body in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    subprocess.run(["git", "add", "--", *files], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--no-verify", "-m", "t"],
                   cwd=repo, check=True)
    return repo


class ScanRepo(unittest.TestCase):
    def test_counts_every_owner_path_and_ignores_placeholders(self):
        repo = git_repo({
            "a.sh": f"cd {HOME}alice/ws && ls {HOME}alice/ws/x\n",
            "b.md": f"use {HOME}you/ws or {HOME}x/ws\n",
            "c.txt": "~/Desktop/stocks and /home/today/ are fine\n",
        })
        self.assertEqual(chp.scan_repo(repo, "bifrost-ui", "HEAD"), Counter({"bifrost-ui/a.sh": 2}))

    def test_skips_infra_work_reports(self):
        repo = git_repo({
            "agent-config/work/r.md": f"{HOME}alice/ws\n",
            "agent-config/x.json": f"{HOME}alice/ws\n",
        })
        self.assertEqual(chp.scan_repo(repo, "bifrost-trade-infra", "HEAD"),
                         Counter({"bifrost-trade-infra/agent-config/x.json": 1}))

    def test_worktree_mode_sees_uncommitted_files(self):
        repo = git_repo({"a.txt": "clean\n"})
        (repo / "new.txt").write_text(f"{HOME}alice/ws\n")
        self.assertEqual(chp.scan_repo(repo, "bifrost-ui", "HEAD"), Counter())
        self.assertEqual(chp.scan_repo(repo, "bifrost-ui", chp.WORKTREE), Counter({"bifrost-ui/new.txt": 1}))


class Compare(unittest.TestCase):
    def test_new_file_and_growth_fail(self):
        grown, _ = chp.compare(Counter({"r/a": 2, "r/b": 1}), {"r/a": 1}, ["r"])
        self.assertEqual(grown, ["r/a: 2 (baseline 1)", "r/b: 1 (baseline 0)"])

    def test_lowered_count_asks_for_update_only_for_scanned_repos(self):
        grown, lower = chp.compare(Counter({"r/a": 1}), {"r/a": 3, "r/gone": 1, "other/z": 2}, ["r"])
        self.assertEqual(grown, [])
        self.assertEqual(lower, ["r/a: 1 (baseline 3)", "r/gone: 0 (baseline 1)"])

    def test_at_baseline_passes(self):
        self.assertEqual(chp.compare(Counter({"r/a": 2}), {"r/a": 2}, ["r"]), ([], []))


class ExitCode(unittest.TestCase):
    def test_new_only_blocks_growth_and_lets_a_lowerable_baseline_through(self):
        self.assertEqual(chp.exit_code(["r/a: 2 (baseline 1)"], [], new_only=True), 1)
        self.assertEqual(chp.exit_code([], ["r/a: 0 (baseline 1)"], new_only=True), 0)
        self.assertEqual(chp.exit_code([], ["r/a: 0 (baseline 1)"], new_only=False), 1)
        self.assertEqual(chp.exit_code([], [], new_only=False), 0)


class Cli(unittest.TestCase):
    """The command check-agent-config-parity.sh runs, against a throwaway workspace."""

    def run_cli(self, ws: Path, baseline: Path, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(Path(chp.__file__)), "--repos", "bifrost-ui", "--baseline", str(baseline),
             "--ref", "HEAD", *extra],
            capture_output=True, text=True, env={**os.environ, "BIFROST_WORKSPACE": str(ws)},
        )

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp(prefix="hcp-ws-"))
        (self.ws / chp.MARKER).parent.mkdir(parents=True)
        (self.ws / chp.MARKER).write_text("")
        ui = git_repo({"a.sh": f"cd {HOME}alice/ws\n"})
        (self.ws / "bifrost-ui").symlink_to(ui)
        self.baseline = self.ws / "baseline.txt"

    def test_new_path_fails_in_new_only_mode(self):
        self.baseline.write_text("# head\n")
        r = self.run_cli(self.ws, self.baseline, "--new-only")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("bifrost-ui/a.sh: 1 (baseline 0)", r.stdout)

    def test_baseline_entries_pass_and_a_lowerable_one_only_warns(self):
        self.baseline.write_text("1 bifrost-ui/a.sh\n2 bifrost-ui/gone.sh\n")
        r = self.run_cli(self.ws, self.baseline, "--new-only")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("⚠ baseline can be lowered", r.stdout)
        self.assertEqual(self.run_cli(self.ws, self.baseline).returncode, 1)


class Baseline(unittest.TestCase):
    def test_round_trip_keeps_comments(self):
        path = Path(tempfile.mkdtemp()) / "b.txt"
        path.write_text("# head\n3 r/a\n\n1 r/b  # note\n")
        self.assertEqual(chp.load_baseline(path), {"r/a": 3, "r/b": 1})
        chp.write_baseline(Counter({"r/a": 2}), path)
        self.assertEqual(path.read_text(), "# head\n2 r/a\n")

    def test_committed_baseline_parses(self):
        self.assertTrue(all(n > 0 for n in chp.load_baseline().values()))


if __name__ == "__main__":
    unittest.main()
