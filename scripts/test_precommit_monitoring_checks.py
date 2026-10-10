"""The shared pre-commit runs the static monitoring checks when a commit touches what they read.

Stub checks stand in for the real ones; each writes a marker so the test sees whether it ran.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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


class InterpreterTests(unittest.TestCase):
    """A python3 without PyYAML must neither pass the checks silently nor block when uv is there."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = self.tmp / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True, env=ENV)
        for name in ("coverage", "routing"):
            target = "check_http_metrics_coverage.py" if name == "coverage" else "check_alert_routing.py"
            (self.repo / "scripts" / target).write_text(stub(name, 0))
        path = self.repo / "k8s" / "monitoring" / "x.yaml"
        path.parent.mkdir(parents=True)
        path.write_text("kind: PodMonitor\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "k8s/monitoring/x.yaml"], check=True, env=ENV)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for tool in ("git", "grep"):
            (self.bin / tool).symlink_to(shutil.which(tool))
        self.exe("python3", "#!/bin/sh\nexit 1\n")

    def exe(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(body)
        path.chmod(0o755)

    def hook(self) -> subprocess.CompletedProcess[str]:
        env = {**ENV, "PATH": str(self.bin)}
        return subprocess.run(["/bin/sh", str(HOOK)], cwd=self.repo, capture_output=True, text=True, env=env)

    def test_uv_runs_the_checks_when_no_python3_has_yaml(self) -> None:
        self.exe("uv", f'#!/bin/sh\nwhile [ "$1" != python ]; do shift; done\nshift\n: > ran-uv\nexec {sys.executable} "$@"\n')
        r = self.hook()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.repo / "ran-uv").exists())
        self.assertTrue((self.repo / "ran-coverage").exists() and (self.repo / "ran-routing").exists())

    def test_no_yaml_and_no_uv_refuses_with_the_reason(self) -> None:
        r = self.hook()
        self.assertEqual(r.returncode, 1)
        self.assertIn("PyYAML", r.stderr)
        self.assertFalse((self.repo / "ran-coverage").exists())


if __name__ == "__main__":
    unittest.main()
