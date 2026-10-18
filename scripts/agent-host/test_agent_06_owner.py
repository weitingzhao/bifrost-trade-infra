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

    def update(self, fail: str = "") -> subprocess.CompletedProcess:
        # copy and prepare are stubbed (they would scp and run prepare on 06); the binary is a
        # file under HOME that matches the agentd.sha256 written for it
        build = Path(self.env["HOME"]) / "build"
        build.mkdir(exist_ok=True)
        (build / "agentd-x").write_text("agentd")
        (build / "agentd.sha256").write_text(subprocess.run(["shasum", "-a", "256", "agentd-x"], cwd=build, capture_output=True, text=True).stdout)
        stub = (f'BINARY="{build}/agentd-x"; HERE="{build}"; '
                'step_copy() { echo copy >> "$FAKE_UNITS/calls"; [ "$FAIL" != copy ]; }; '
                'step_prepare() { echo prepare >> "$FAKE_UNITS/calls"; [ "$FAIL" != prepare ]; }; ')
        script = f'source "{HERE / "agent-06-owner.sh"}"; node_ssh() {{ bash -c "$1"; }}; {stub} step_update_agentd'
        return subprocess.run(["bash", "-c", script], env={**self.env, "FAIL": fail}, capture_output=True, text=True, timeout=60)

    def test_update_agentd_stops_copies_prepares_starts(self) -> None:
        for u in ("bifrost-agentd.service", "bifrost-agentd-stg.service"):
            (self.units / u).write_text("")
        r = self.update()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = [" ".join(c.split()[:2]) if c.startswith("systemctl") else c for c in (self.units / "calls").read_text().splitlines()]
        order = [c for c in calls if c in ("systemctl stop", "copy", "prepare", "systemctl enable")]
        self.assertEqual(order, ["systemctl stop", "copy", "prepare", "systemctl enable"])
        self.assertEqual(self.active(), {"bifrost-agentd.service", "bifrost-agentd-stg.service"})

    def test_update_agentd_stops_at_a_failed_copy(self) -> None:
        r = self.update(fail="copy")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("both agentd services are stopped", r.stderr)
        self.assertNotIn("prepare", (self.units / "calls").read_text())
        self.assertEqual(self.active(), set())

    def test_update_agentd_refuses_a_binary_that_does_not_match(self) -> None:
        for u in ("bifrost-agentd.service", "bifrost-agentd-stg.service"):
            (self.units / u).write_text("")
        build = Path(self.env["HOME"]) / "build"
        build.mkdir(exist_ok=True)
        (build / "agentd-x").write_text("agentd")
        (build / "agentd.sha256").write_text("0" * 64 + "  agentd-x\n")
        script = f'source "{HERE / "agent-06-owner.sh"}"; node_ssh() {{ bash -c "$1"; }}; BINARY="{build}/agentd-x"; HERE="{build}"; step_update_agentd'
        r = subprocess.run(["bash", "-c", script], env=self.env, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing was stopped", r.stderr)
        self.assertEqual(self.active(), {"bifrost-agentd.service", "bifrost-agentd-stg.service"})


if __name__ == "__main__":
    unittest.main()
