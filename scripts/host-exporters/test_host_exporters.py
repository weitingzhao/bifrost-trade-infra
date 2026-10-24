"""host-exporters.sh against a throwaway origin (W-68 B4 ①).

A bare repository stands in for origin with this directory and the four monitoring
files on main; the checkout under test is a clone of it (HOST_EXPORTERS_REPO). ssh and
kubectl are fakes that record what they were asked to do; ssh also keeps the command it
would run on the host, so the tests can open the tar that travels inside it.

    python3 -m unittest scripts/host-exporters/test_host_exporters.py
"""

from __future__ import annotations

import base64
import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
INFRA = HERE.parents[1]
SCRIPT = HERE / "host-exporters.sh"
MONITORING = ["bifrost-hosts-external.yaml", "bifrost-blackbox.yaml", "bifrost-host-rules.yaml",
              "grafana-dashboard-hosts.yaml"]

FAKE_SSH = r'''#!/usr/bin/env bash
# fake ssh: one record per call, NUL-separated args; the last arg is the remote command
n=$(ls "$FAKE_LOG" | grep -c '^ssh-' || true)
printf '%s\0' "$@" > "$FAKE_LOG/ssh-$n.args"
exit "${FAKE_SSH_RC:-0}"
'''

FAKE_KUBECTL = r'''#!/usr/bin/env bash
# fake kubectl: logs the call with KUBECONFIG; FAIL_DRYRUN names a file whose dry-run fails
echo "KUBECONFIG=$KUBECONFIG kubectl $*" >> "$FAKE_LOG/kubectl"
if [ -n "${FAIL_DRYRUN:-}" ] && [ "$2" = --dry-run=server ] && [ "${4##*/}" = "$FAIL_DRYRUN" ]; then exit 1; fi
exit 0
'''


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


class HostExporters(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.log = root / "log"
        self.log.mkdir()
        bindir = root / "bin"
        bindir.mkdir()
        for name, body in (("ssh", FAKE_SSH), ("kubectl", FAKE_KUBECTL)):
            (bindir / name).write_text(body)
            (bindir / name).chmod(0o755)
        self.origin = root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        self.clone = root / "infra"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.clone)], check=True, capture_output=True)
        git(self.clone, "config", "user.email", "test@example.invalid")
        git(self.clone, "config", "user.name", "test")
        git(self.clone, "config", "core.hooksPath", "/dev/null")
        git(self.clone, "commit", "-q", "--allow-empty", "-m", "base")
        git(self.clone, "push", "-q", "origin", "HEAD:main")
        home = root / "home"
        (home / ".ssh").mkdir(parents=True)
        (home / ".ssh" / "id_ed25519").write_text("not a key\n")
        self.node_key = home / "node"
        self.node_key.write_text("not a key\n")
        self.kubeconfig = home / "admin.yaml"
        self.kubeconfig.write_text("apiVersion: v1\n")
        self.env = {**os.environ, "HOME": str(home), "FAKE_LOG": str(self.log),
                    "PATH": f"{bindir}:{os.environ['PATH']}", "HOST_EXPORTERS_REPO": str(self.clone),
                    "HOST_EXPORTERS_NODE_KEY": str(self.node_key),
                    "HOST_EXPORTERS_KUBECONFIG": str(self.kubeconfig)}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def land(self) -> None:
        """Put this directory and the four monitoring files on origin/main."""
        shutil.copytree(HERE, self.clone / "scripts" / "host-exporters",
                        ignore=shutil.ignore_patterns("__pycache__", "test_*.py"))
        (self.clone / "k8s" / "monitoring").mkdir(parents=True)
        for f in MONITORING:
            shutil.copy(INFRA / "k8s" / "monitoring" / f, self.clone / "k8s" / "monitoring" / f)
        git(self.clone, "add", "scripts", "k8s")
        git(self.clone, "commit", "-q", "-m", "land")
        git(self.clone, "push", "-q", "origin", "HEAD:main")

    def run_step(self, *args: str, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(SCRIPT), *args], env={**self.env, **env},
                              capture_output=True, text=True, timeout=60)

    def ssh_calls(self) -> list[list[str]]:
        return [p.read_bytes().rstrip(b"\0").decode().split("\0") for p in sorted(self.log.glob("ssh-*.args"))]

    def kubectl_calls(self) -> list[str]:
        p = self.log / "kubectl"
        return p.read_text().splitlines() if p.exists() else []

    @staticmethod
    def tar_names(remote: str) -> set[str]:
        b64 = re.search(r"printf '%s' '([A-Za-z0-9+/=]+)'", remote).group(1)
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(b64))) as t:
            return {m.name for m in t.getmembers() if m.isfile()}

    def test_unknown_step_does_nothing(self) -> None:
        r = self.run_step("everything")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.ssh_calls(), [])

    def test_mini_needs_50_or_52(self) -> None:
        self.land()
        r = self.run_step("mini", "51")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.ssh_calls(), [])

    def test_nothing_runs_before_the_files_are_on_main(self) -> None:
        for step in (["mini", "50"], ["agent-06"], ["nas"], ["cluster"]):
            r = self.run_step(*step)
            self.assertNotEqual(r.returncode, 0, step)
            self.assertIn("is not on origin/main yet", r.stderr, step)
        self.assertEqual(self.ssh_calls(), [])
        self.assertEqual(self.kubectl_calls(), [])

    def test_mini_runs_install_mac_as_vision(self) -> None:
        self.land()
        r = self.run_step("mini", "52")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (call,) = self.ssh_calls()
        self.assertIn("vision@192.168.10.52", call)
        self.assertNotIn("sudo", call[-1])
        self.assertTrue(call[-1].endswith('install-mac.sh" 192.168.10.52'), call[-1])
        self.assertEqual(self.tar_names(call[-1]),
                         {"scripts/host-exporters/install-mac.sh", "scripts/host-exporters/versions.env"})

    def test_agent06_uses_the_node_key_only_and_sudo_without_a_prompt(self) -> None:
        self.land()
        r = self.run_step("agent-06")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (call,) = self.ssh_calls()
        for opt in ("-F", "/dev/null", "IdentityAgent=none", "IdentitiesOnly=yes", str(self.node_key),
                    "vision@192.168.10.79"):
            self.assertIn(opt, call)
        self.assertIn("| sudo -n bash -c", call[-1])
        self.assertIn('install-linux.sh" 192.168.10.79', call[-1])
        self.assertEqual(self.tar_names(call[-1]),
                         {"scripts/host-exporters/install-linux.sh", "scripts/host-exporters/versions.env"})

    def test_agent06_needs_the_node_key(self) -> None:
        self.land()
        self.node_key.unlink()
        r = self.run_step("agent-06")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.ssh_calls(), [])

    def test_nas_unpacks_into_roots_own_directory_with_a_terminal(self) -> None:
        self.land()
        r = self.run_step("nas")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (call,) = self.ssh_calls()
        self.assertIn("-t", call)
        self.assertIn("k8s_admin@192.168.10.20", call)
        self.assertIn("| sudo bash -c 't=$(mktemp -d)", call[-1])
        self.assertEqual(self.tar_names(call[-1]),
                         {"scripts/host-exporters/nas/install-nas.sh", "scripts/host-exporters/nas/compose.yaml"})

    def test_cluster_dry_runs_all_four_before_applying_any(self) -> None:
        self.land()
        r = self.run_step("cluster")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = self.kubectl_calls()
        self.assertTrue(all(c.startswith(f"KUBECONFIG={self.kubeconfig} ") for c in calls), calls)
        verbs = [("dry" if "--dry-run=server" in c else "apply" if " apply " in c else "other") for c in calls]
        self.assertEqual(verbs, ["dry"] * 4 + ["apply"] * 4 + ["other"])
        self.assertEqual([c.rsplit("/", 1)[-1] for c in calls[4:8]], MONITORING)

    def test_cluster_applies_nothing_when_a_dry_run_fails(self) -> None:
        self.land()
        r = self.run_step("cluster", FAIL_DRYRUN="bifrost-blackbox.yaml")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing applied", r.stderr)
        self.assertFalse([c for c in self.kubectl_calls() if "--dry-run" not in c])

    def test_the_remote_commands_unpack_and_reach_their_script(self) -> None:
        """Run each command ssh would send, here, with a sudo that does not elevate: the
        unpack works and the installer starts and stops at its own first guard."""
        self.land()
        bindir = Path(self.env["PATH"].split(":")[0])
        (bindir / "sudo").write_text('#!/usr/bin/env bash\n[ "$1" = -n ] && shift\nexec "$@"\n')
        (bindir / "sudo").chmod(0o755)
        shells = ["bash"] + (["zsh"] if shutil.which("zsh") else [])
        cases = [(["mini", "52"], "this Mac does not own 192.168.10.52|expects macOS arm64"),
                 (["agent-06"], "run as root"),
                 (["nas"], "run as root")]
        for step, guard in cases:
            for f in self.log.glob("ssh-*.args"):
                f.unlink()
            r = self.run_step(*step)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            (call,) = self.ssh_calls()
            for sh in shells:
                out = subprocess.run([sh, "-c", call[-1]], env=self.env, capture_output=True, text=True, timeout=60)
                self.assertNotEqual(out.returncode, 0, (step, sh))
                self.assertRegex(out.stderr, guard, (step, sh, out.stderr))

    def test_a_failed_ssh_fails_the_step(self) -> None:
        self.land()
        r = self.run_step("mini", "50", FAKE_SSH_RC="255")
        self.assertEqual(r.returncode, 255)


if __name__ == "__main__":
    unittest.main()
