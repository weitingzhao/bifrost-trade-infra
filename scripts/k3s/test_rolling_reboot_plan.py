"""Plan order for scripts/k3s/rolling-reboot.sh. No cluster, no SSH."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "k3s" / "rolling-reboot.sh"

NODE_RE = re.compile(r"^node \d+/\d+ (\S+) role=(\S+)\s*$", re.M)

DEFAULT_ORDER = [
    ("ubt-k3s-05", "general"),
    ("ubt-k3s-06", "general"),
    ("ubt-k3s-01", "control-plane"),
    ("ubt-k3s-02", "prod"),
    ("ubt-k3s-04", "data-primary"),
]


def run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.pop("ROLLING_REBOOT_DOW", None)
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=ROOT,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


def nodes(text: str) -> list[tuple[str, str]]:
    return NODE_RE.findall(text)


class RollingRebootPlanTests(unittest.TestCase):
    def test_default_dry_run_order_primary_last(self) -> None:
        result = run(["--dry-run"])
        self.assertEqual(result.returncode, 0, result.stderr)
        found = nodes(result.stdout)
        self.assertEqual(found, DEFAULT_ORDER)
        self.assertEqual(found[-1][0], "ubt-k3s-04")
        self.assertIn("order: ubt-k3s-05 ubt-k3s-06 ubt-k3s-01 ubt-k3s-02 ubt-k3s-04", result.stdout)
        switch_at = result.stdout.index("switchover:")
        primary_at = result.stdout.index("node 5/5 ubt-k3s-04 role=data-primary")
        self.assertLess(switch_at, primary_at)
        self.assertIn("switchover-before: ubt-k3s-04", result.stdout)
        self.assertIn("sole control plane", result.stdout)
        self.assertIn("about 10s", result.stdout)
        self.assertNotIn("--disable-eviction", result.stdout)
        self.assertNotIn("--force", result.stdout)
        self.assertIn("gpu-server", result.stdout)
        for name, _role in DEFAULT_ORDER:
            self.assertIn(f"cordon {name}", result.stdout)
            self.assertIn(f"drain {name}", result.stdout)
            self.assertIn(f"reboot {name}", result.stdout)
            self.assertIn(f"uncordon {name}", result.stdout)
            self.assertIn(f"verify workloads on {name} are Ready", result.stdout)

    def test_scrambled_node_list_keeps_primary_last(self) -> None:
        spec = (
            "ubt-k3s-04:data-primary,"
            "ubt-k3s-02:prod,"
            "ubt-k3s-06:general,"
            "ubt-k3s-01:control-plane,"
            "ubt-k3s-05:general"
        )
        result = run(["--dry-run", "--nodes", spec])
        self.assertEqual(result.returncode, 0, result.stderr)
        found = nodes(result.stdout)
        self.assertEqual([name for name, _role in found], [name for name, _role in DEFAULT_ORDER])
        self.assertEqual(found[-1], ("ubt-k3s-04", "data-primary"))
        self.assertLess(
            result.stdout.index("switchover:"),
            result.stdout.index("role=data-primary"),
        )

    def test_general_then_primary_still_switches_before_reboot(self) -> None:
        result = run(["--dry-run", "--nodes", "ubt-k3s-04:data-primary,zzz-general:general"])
        self.assertEqual(result.returncode, 0, result.stderr)
        found = nodes(result.stdout)
        self.assertEqual(found, [("zzz-general", "general"), ("ubt-k3s-04", "data-primary")])
        self.assertLess(result.stdout.index("switchover:"), result.stdout.index("ubt-k3s-04 role=data-primary"))

    def test_execute_refused_on_weekday_does_not_call_kubectl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "kubectl.log"
            stub = Path(tmp) / "kubectl"
            stub.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$STUB_LOG\"\nexit 99\n",
                encoding="utf-8",
            )
            stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
            env = {
                "PATH": f"{tmp}:{os.environ.get('PATH', '')}",
                "ROLLING_REBOOT_DOW": "3",
                "STUB_LOG": str(log),
            }
            result = run(["--execute"], env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("REFUSED", result.stderr)
            self.assertFalse(log.exists())

    def test_allow_weekday_warns_and_stops_when_the_first_step_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "kubectl.log"
            stub = Path(tmp) / "kubectl"
            stub.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$STUB_LOG\"\nexit 99\n",
                encoding="utf-8",
            )
            stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
            env = {
                "PATH": f"{tmp}:{os.environ.get('PATH', '')}",
                "ROLLING_REBOOT_DOW": "3",
                "STUB_LOG": str(log),
            }
            result = run(["--execute", "--allow-weekday"], env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("WARNING", result.stderr)
            self.assertIn("--allow-weekday", result.stderr)
            called = log.read_text(encoding="utf-8")
            self.assertIn("cordon ubt-k3s-05", called)
            self.assertNotIn("reboot", called)
            self.assertNotIn("uncordon", called)
