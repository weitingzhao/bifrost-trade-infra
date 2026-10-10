"""The shared pre-commit runs the static monitoring checks when a commit touches what they read.

Stub checks stand in for the real ones; each writes a marker so the test sees whether it ran.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOOK = HERE.parent / "agent-config" / "scripts" / "git-hooks" / "pre-commit"
ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
HAVE_YAML = any(
    shutil.which(p) and subprocess.run([p, "-c", "import yaml"], capture_output=True).returncode == 0
    for p in ("python3", "python3.13", "python3.12", "python3.11")
)


def stub(name: str, rc: int) -> str:
    return f"from pathlib import Path\nPath('ran-{name}').write_text('x')\nraise SystemExit({rc})\n"


@unittest.skipUnless(HAVE_YAML, "no python3 with PyYAML; the hook itself refuses in that case")
class MonitoringHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = self.tmp / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True, env=ENV)

    def checks(self, coverage_rc: int = 0, routing_rc: int = 0) -> None:
        (self.repo / "scripts" / "check_http_metrics_coverage.py").write_text(stub("coverage", coverage_rc))
        (self.repo / "scripts" / "check_alert_routing.py").write_text(stub("routing", routing_rc))

    def stage(self, rel: str) -> subprocess.CompletedProcess[str]:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("kind: PodMonitor\n")
        subprocess.run(["git", "-C", str(self.repo), "add", rel], check=True, env=ENV)
        return subprocess.run(["sh", str(HOOK)], cwd=self.repo, capture_output=True, text=True, env=ENV)

    def ran(self, name: str) -> bool:
        return (self.repo / f"ran-{name}").exists()

    def test_monitoring_change_runs_both_checks(self) -> None:
        self.checks()
        r = self.stage("k8s/monitoring/x-podmonitor.yaml")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.ran("coverage") and self.ran("routing"))

    def test_platform_overlay_change_runs_them(self) -> None:
        self.checks()
        self.stage("k8s/overlays/platform-stg/x.patch.yaml")
        self.assertTrue(self.ran("routing"))

    def test_a_red_check_blocks_the_commit(self) -> None:
        self.checks(coverage_rc=1)
        self.assertEqual(self.stage("k8s/monitoring/x.yaml").returncode, 1)
        self.checks(routing_rc=1)
        self.assertEqual(self.stage("k8s/overlays/platform-prod/y.yaml").returncode, 1)

    def test_unrelated_change_runs_nothing(self) -> None:
        self.checks(coverage_rc=1, routing_rc=1)
        r = self.stage("docs/notes.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.ran("coverage") or self.ran("routing"))

    def test_other_repos_are_left_alone(self) -> None:
        r = self.stage("k8s/monitoring/x.yaml")
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
