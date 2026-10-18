"""agent-06-owner.sh stop / start with one environment or both (Gitea-primary batch A starts
STG before PROD). The script is sourced with node_ssh replaced: the command it would send to 06
runs here, against a fake sudo and systemctl that keep which units are active in a directory.

    python3 -m unittest scripts/agent-host/test_agent_06_owner.py
"""

from __future__ import annotations

import json
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
        (bindir / "sudo").write_text(
            '#!/usr/bin/env bash\n'
            '[ "$1" = -v ] && { echo "sudo -v" >> "$FAKE_UNITS/calls"; [ "${FAIL_SUDO:-}" != 1 ]; exit; }\n'
            # install-secret.sh on 06: recorded with what it was given; FAIL_SECRET names a file whose sending fails
            'if [ "$1" = bash ] && [ "${2##*/}" = install-secret.sh ]; then echo "install-secret $3 $4" >> "$FAKE_UNITS/calls"; '
            'cat > /dev/null; [ "${FAIL_SECRET:-}" != "$4" ]; exit; fi\n'
            '[ "$1" = bash ] && { echo "check-agent-06 $*" >> "$FAKE_UNITS/calls"; exit 0; }\n'
            'exec "$@"\n')
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


    def stg_vendors(self, fail: str = "", fail_sudo: bool = False) -> subprocess.CompletedProcess:
        # The real step_vendor_creds and send_secret; only the Mac's credential files (fixtures of the right shape),
        # SSH (the command runs here) and copy and prepare (stubs) stand in.
        for u in ("bifrost-agentd.service", "bifrost-agentd-stg.service"):
            (self.units / u).write_text("")
        build = Path(self.env["HOME"]) / "build"
        build.mkdir(exist_ok=True)
        (build / "agentd-x").write_text("agentd")
        (build / "agentd.sha256").write_text(subprocess.run(["shasum", "-a", "256", "agentd-x"], cwd=build, capture_output=True, text=True).stdout)
        creds = Path(self.env["HOME"]) / "creds"
        creds.mkdir(exist_ok=True)
        (creds / "claude-oauth.token").write_text("sk-ant-fixture-not-a-real-token-000000\n")
        (creds / "cursor-api.key").write_text("fixture-cursor-key-not-real-0000000000\n")
        stub = (f'BINARY="{build}/agentd-x"; HERE="{build}"; '
                'step_copy() { echo copy >> "$FAKE_UNITS/calls"; }; '
                'step_prepare() { echo prepare >> "$FAKE_UNITS/calls"; }; ')
        script = f'source "{HERE / "agent-06-owner.sh"}"; node_ssh() {{ bash -c "$1"; }}; {stub} step_stg_vendors'
        env = {**self.env, "VENDOR_CREDS_DIR": str(creds), "FAIL_SECRET": fail, "FAIL_SUDO": "1" if fail_sudo else ""}
        return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=60)

    def test_stg_vendors_copies_the_credentials_to_stg_before_the_start(self) -> None:
        r = self.stg_vendors()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = (self.units / "calls").read_text().splitlines()
        order = [" ".join(c.split()[:2]) if c.startswith("systemctl") else " ".join(c.split()[:3]) for c in calls]
        order = [c for c in order if c in ("systemctl stop", "copy", "prepare", "systemctl enable") or c.startswith("install-secret")]
        self.assertEqual(order, ["systemctl stop", "copy", "prepare", "install-secret bifrost-agentd-stg claude-oauth.token",
                                 "install-secret bifrost-agentd-stg cursor-api.key", "systemctl enable"])
        self.assertEqual(self.active(), {"bifrost-agentd.service", "bifrost-agentd-stg.service"})
        self.assertNotIn("fixture", r.stdout + r.stderr)

    def test_stg_vendors_asks_for_this_macs_sudo_before_it_stops_anything(self) -> None:
        # lesson 175: asked for after the stop, the password held both agentd services down until someone typed it
        r = self.stg_vendors()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = (self.units / "calls").read_text().splitlines()
        self.assertLess(calls.index("sudo -v"), next(i for i, c in enumerate(calls) if c.startswith("systemctl stop")))
        (self.units / "calls").unlink()
        for u in ("bifrost-agentd.service", "bifrost-agentd-stg.service"):
            (self.units / u).write_text("")
        r = self.stg_vendors(fail_sudo=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing was stopped", r.stderr)
        self.assertFalse(any(c.startswith("systemctl stop") for c in (self.units / "calls").read_text().splitlines()))

    def test_stg_vendors_starts_nothing_when_a_credential_does_not_arrive(self) -> None:
        for fail in ("claude-oauth.token", "cursor-api.key"):
            (self.units / "calls").unlink(missing_ok=True)
            r = self.stg_vendors(fail)
            self.assertNotEqual(r.returncode, 0, fail)
            self.assertIn(f"{fail} did not reach bifrost-agentd-stg", r.stderr)
            self.assertNotIn("systemctl enable", (self.units / "calls").read_text())
            self.assertEqual(self.active(), set(), fail)


if __name__ == "__main__":
    unittest.main()


class ClaudePolicyCheck(unittest.TestCase):
    """check-claude-policy.sh: no managed claude policy that could run a hook
    (reviews 282-284, TD-371)."""

    def run_check(self, setup):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "claude-code"
            root.mkdir()
            setup(root, Path(tmp))
            r = subprocess.run(["bash", str(HERE / "check-claude-policy.sh"), str(root)], capture_output=True, text=True)
            return r.returncode, r.stdout

    def test_none(self):
        code, out = self.run_check(lambda root, tmp: None)
        self.assertEqual(code, 0, out)

    def test_a_policy_that_turns_hooks_off_passes_whatever_hooks_it_names(self):
        def setup(root, tmp):
            (root / "managed-settings.json").write_text(json.dumps({"disableAllHooks": True, "hooks": {"UserPromptSubmit": []}}))
        code, out = self.run_check(setup)
        self.assertEqual(code, 0, out)

    def test_a_policy_with_hooks_fails(self):
        def setup(root, tmp):
            (root / "managed-settings.json").write_text(json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "true"}]}]}}))
        code, out = self.run_check(setup)
        self.assertEqual(code, 1, out)

    def test_a_drop_in_fails(self):
        def setup(root, tmp):
            (root / "managed-settings.d").mkdir()
            (root / "managed-settings.d" / "10-hooks.json").write_text("{}")
        code, out = self.run_check(setup)
        self.assertEqual(code, 1, out)

    def test_drop_ins_through_a_link_to_a_directory_fail(self):
        def setup(root, tmp):
            elsewhere = tmp / "policy"
            elsewhere.mkdir()
            (elsewhere / "10-hooks.json").write_text("{}")
            (root / "managed-settings.d").symlink_to(elsewhere, target_is_directory=True)
        code, out = self.run_check(setup)
        self.assertEqual(code, 1, out)

    def test_a_managed_mcp_file_fails(self):
        def setup(root, tmp):
            (root / "managed-mcp.json").write_text("{}")
        code, out = self.run_check(setup)
        self.assertEqual(code, 1, out)
