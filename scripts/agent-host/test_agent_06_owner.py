"""agent-06-owner.sh stop / start with one environment or both (Gitea-primary batch A starts
STG before PROD). The script is sourced with node_ssh replaced: the command it would send to 06
runs here, against a fake sudo and systemctl that keep which units are active in a directory.

    python3 -m unittest scripts/agent-host/test_agent_06_owner.py
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent

FAKE_SYSTEMCTL = r'''#!/usr/bin/env bash
# fake systemctl: $FAKE_UNITS/<unit> exists while the unit is active
echo "systemctl $*" >> "$FAKE_UNITS/calls"
case "$1" in
  stop) shift; for u in "$@"; do [ -f "$FAKE_UNITS/stuck" ] || rm -f "$FAKE_UNITS/$u"; done ;;
  enable) shift; [ "$1" = --now ] && shift; for u in "$@"; do [ -f "$FAKE_UNITS/fails" ] || touch "$FAKE_UNITS/$u"; done ;;
  is-active) shift; [ "$1" = --quiet ] && shift; for u in "$@"; do [ -f "$FAKE_UNITS/$u" ] || exit 3; done ;;
  *) exit 9 ;;
esac
'''


class StopStart(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.units = root / "units"
        self.units.mkdir()
        bindir = root / "bin"
        bindir.mkdir()
        (bindir / "systemctl").write_text(FAKE_SYSTEMCTL)
        (bindir / "sudo").write_text('#!/usr/bin/env bash\n[ "$1" = bash ] && { echo "check-agent-06 $*" >> "$FAKE_UNITS/calls"; exit 0; }\nexec "$@"\n')
        (bindir / "sleep").write_text("#!/bin/sh\nexit 0\n")
        for f in ("systemctl", "sudo", "sleep"):
            (bindir / f).chmod(0o755)
        home = root / "home"
        home.mkdir()
        self.env = {**os.environ, "HOME": str(home), "FAKE_UNITS": str(self.units), "PATH": f"{bindir}:{os.environ['PATH']}"}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_step(self, *args: str) -> subprocess.CompletedProcess:
        script = (f'source "{HERE / "agent-06-owner.sh"}"; node_ssh() {{ bash -c "$1"; }}; ' + " ".join(args))
        return subprocess.run(["bash", "-c", script], env=self.env, capture_output=True, text=True, timeout=60)

    def active(self) -> set[str]:
        return {p.name for p in self.units.iterdir() if p.name.endswith(".service")}

    def test_start_stg_alone(self) -> None:
        r = self.run_step("step_start", "stg")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.active(), {"bifrost-agentd-stg.service"})
        self.assertIn("running: bifrost-agentd-stg.service", r.stdout)
        self.assertNotIn("check-agent-06", (self.units / "calls").read_text())

    def test_start_both_runs_the_full_check(self) -> None:
        r = self.run_step("step_start")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.active(), {"bifrost-agentd.service", "bifrost-agentd-stg.service"})
        self.assertIn("check-agent-06 bash", (self.units / "calls").read_text())

    def test_start_that_does_not_come_up_fails(self) -> None:
        (self.units / "fails").write_text("")
        self.assertNotEqual(self.run_step("step_start", "prod").returncode, 0)

    def test_stop_one_leaves_the_other(self) -> None:
        for u in ("bifrost-agentd.service", "bifrost-agentd-stg.service"):
            (self.units / u).write_text("")
        r = self.run_step("step_stop", "prod")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.active(), {"bifrost-agentd-stg.service"})
        r = self.run_step("step_stop")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.active(), set())

    def test_stop_that_does_not_stop_fails(self) -> None:
        (self.units / "bifrost-agentd-stg.service").write_text("")
        (self.units / "stuck").write_text("")
        r = self.run_step("step_stop", "stg")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("stopped:", r.stdout)

    def test_unknown_environment(self) -> None:
        r = self.run_step("step_start", "dev")
        self.assertEqual(r.returncode, 1)
        self.assertIn("say prod, stg, or nothing for both", r.stderr)
        self.assertFalse((self.units / "calls").exists())


if __name__ == "__main__":
    unittest.main()
