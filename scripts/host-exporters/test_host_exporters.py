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

FAKE_CURL = r'''#!/usr/bin/env bash
# fake curl: every endpoint answers with the metrics host-exporters.sh check looks for,
# except the one named in FAKE_CURL_DOWN
for a in "$@"; do url=$a; done
[ -n "${FAKE_CURL_DOWN:-}" ] && [ "${url#*//}" = "$FAKE_CURL_DOWN/metrics" ] && exit 7
printf 'node_exporter_build_info 1\nnode_md_disks 3\nsmartctl_device_smart_status 1\n'
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
        for name, body in (("ssh", FAKE_SSH), ("kubectl", FAKE_KUBECTL), ("curl", FAKE_CURL)):
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
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "test", "-f",
                        str(home / ".ssh" / "id_ed25519")], check=True)
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

    def test_nas_runs_as_the_owners_admin_account_into_roots_own_directory(self) -> None:
        # Review 540 A1: root work on the NAS never goes through k8s_admin (home was 777).
        self.land()
        r = self.run_step("nas")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (call,) = self.ssh_calls()
        self.assertIn("-t", call)
        self.assertIn("Wzhao@192.168.10.20", call)
        self.assertFalse([a for a in call if "k8s_admin@" in a])
        self.assertIn("| sudo bash -c 't=$(mktemp -d)", call[-1])
        self.assertTrue({"scripts/host-exporters/nas/install-nas.sh", "scripts/host-exporters/nas/compose.yaml",
                         "scripts/host-exporters/nas/secure-dir.sh", "scripts/host-exporters/nas/prepare-dir.sh"}
                        <= self.tar_names(call[-1]))

    def test_nas_home_checks_as_root_from_the_admin_account(self) -> None:
        self.land()
        fp = subprocess.run(["ssh-keygen", "-lf", str(Path(self.env["HOME"]) / ".ssh" / "id_ed25519.pub")],
                            capture_output=True, text=True, check=True).stdout.split()[1]
        for args, mode in ((["nas-home"], "fix"), (["nas-home", "check"], "check")):
            for f in self.log.glob("ssh-*.args"):
                f.unlink()
            r = self.run_step(*args)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            (call,) = self.ssh_calls()
            self.assertIn("-t", call)
            self.assertIn("Wzhao@192.168.10.20", call)
            self.assertFalse([a for a in call if "k8s_admin@" in a])
            self.assertIn("| sudo bash -c 't=$(mktemp -d)", call[-1])
            self.assertTrue(call[-1].endswith(f'check-k8s-admin-home.sh" {fp} {mode}\''), call[-1])
            self.assertEqual(self.tar_names(call[-1]), {"scripts/host-exporters/nas/check-k8s-admin-home.sh"})
        r = self.run_step("nas-home", "chmod")
        self.assertNotEqual(r.returncode, 0)

    def test_cluster_dry_runs_all_four_before_applying_any(self) -> None:
        self.land()
        r = self.run_step("cluster")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = self.kubectl_calls()
        self.assertTrue(all(c.startswith(f"KUBECONFIG={self.kubeconfig} ") for c in calls), calls)
        verbs = [("dry" if "--dry-run=server" in c else "apply" if " apply " in c else "other") for c in calls]
        self.assertEqual(verbs, ["dry"] * 4 + ["apply"] * 4 + ["other"])
        self.assertEqual([c.rsplit("/", 1)[-1] for c in calls[4:8]], MONITORING)

    def test_cluster_waits_for_the_hosts(self) -> None:
        self.land()
        r = self.run_step("cluster", FAKE_CURL_DOWN="192.168.10.20:9633")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("MISSING  nas 192.168.10.20:9633", r.stdout)
        self.assertIn("finish steps 2-4 first; nothing applied", r.stderr)
        self.assertEqual(self.kubectl_calls(), [])

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
                 (["nas"], "run as root"),
                 (["nas-home"], "/home/k8s_admin is a link or not a directory")]
        for step, guard in cases:
            for f in self.log.glob("ssh-*.args"):
                f.unlink()
            r = self.run_step(*step)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            (call,) = self.ssh_calls()
            for sh in shells:
                out = subprocess.run([sh, "-c", call[-1]], env=self.env, capture_output=True, text=True, timeout=60)
                self.assertNotEqual(out.returncode, 0, (step, sh))
                self.assertRegex(out.stdout + out.stderr, guard, (step, sh, out.stderr))

    def test_a_failed_ssh_fails_the_step(self) -> None:
        self.land()
        r = self.run_step("mini", "50", FAKE_SSH_RC="255")
        self.assertEqual(r.returncode, 255)


SECURE_DIR = HERE / "nas" / "secure-dir.sh"


class SecureDir(unittest.TestCase):
    """Review 537 A1: root's compose file on the NAS sits only under directories that no
    other account can write, rename or link (secure-dir.sh, called by install-nas.sh)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(os.path.realpath(self.tmp.name))
        self.uid = str(os.getuid())
        r = self.check(self.base)
        if r.returncode != 0:
            self.tmp.cleanup()
            self.skipTest(f"this machine's temp directory is not private: {r.stderr.strip()}")
        self.parent = self.base / "bifrost"
        self.dir = self.parent / "host-exporters"
        self.dir.mkdir(parents=True)
        os.chmod(self.parent, 0o755)
        os.chmod(self.dir, 0o755)
        self.file = self.dir / "compose.yaml"
        self.file.write_text("name: test\n")
        os.chmod(self.file, 0o644)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def check(self, path: Path) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(SECURE_DIR), self.uid, str(path)], capture_output=True, text=True,
                              timeout=30)

    def test_a_private_path_passes(self) -> None:
        r = self.check(self.file)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_world_writable_parent_is_refused(self) -> None:
        # /volume1/docker is 777: a root directory inside it can be renamed and replaced.
        os.chmod(self.parent, 0o777)
        r = self.check(self.file)
        self.assertEqual(r.returncode, 1)
        self.assertIn(f"{self.parent} (mode 777) can be written by its group or by others", r.stderr)

    def test_a_group_writable_file_is_refused(self) -> None:
        os.chmod(self.file, 0o664)
        r = self.check(self.file)
        self.assertEqual(r.returncode, 1)
        self.assertIn("can be written by its group or by others", r.stderr)

    def test_a_symbolic_link_on_the_way_is_refused(self) -> None:
        elsewhere = self.base / "elsewhere"
        self.parent.rename(elsewhere)
        self.parent.symlink_to(elsewhere)
        r = self.check(self.file)
        self.assertEqual(r.returncode, 1)
        self.assertIn(f"{self.parent} is a symbolic link", r.stderr)

    def test_a_missing_path_is_refused(self) -> None:
        r = self.check(self.dir / "absent.yaml")
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not exist", r.stderr)

    def test_install_nas_checks_before_it_writes_and_before_compose_reads(self) -> None:
        text = (HERE / "nas" / "install-nas.sh").read_text()
        code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
        self.assertIn("BASE=/volume1/@bifrost", code)
        self.assertNotIn("DIR=/volume1/docker", code)
        # Review 540 A1 P2: nothing existing is taken over.
        self.assertNotIn("chown", code)
        self.assertNotIn("chmod", code)
        prep = code.index('prepare-dir.sh" 0 /volume1 "$DIR"')
        before = code.index('secure "$COMPOSE"')
        write = code.index("install -o root -g root -m 0644")
        after = code.index('secure "$COMPOSE"', write)
        compose = code.index('docker compose -f "$COMPOSE" config')
        self.assertTrue(prep < before < write < after < compose)


PREPARE_DIR = HERE / "nas" / "prepare-dir.sh"


class PrepareDir(unittest.TestCase):
    """Review 540 A1 P2: a directory that already exists is checked as it is and refused
    if it is not safe, never chown'ed or chmod'ed into shape; only a missing one is
    created, and checked right after."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(os.path.realpath(self.tmp.name)) / "volume1"
        self.root.mkdir()
        os.chmod(self.root, 0o755)
        self.uid = str(os.getuid())
        r = subprocess.run(["bash", str(SECURE_DIR), self.uid, str(self.root)], capture_output=True, text=True)
        if r.returncode != 0:
            self.tmp.cleanup()
            self.skipTest(f"this machine's temp directory is not private: {r.stderr.strip()}")
        self.base = self.root / "@bifrost"
        self.dir = self.base / "host-exporters"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def prepare(self) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(PREPARE_DIR), self.uid, str(self.root), str(self.dir)],
                              capture_output=True, text=True, timeout=30)

    @staticmethod
    def mode(p: Path) -> int:
        return os.lstat(p).st_mode & 0o7777

    def test_an_existing_world_writable_directory_is_refused_and_left_alone(self) -> None:
        self.base.mkdir()
        os.chmod(self.base, 0o777)
        r = self.prepare()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"{self.base} already exists and is not safe; refusing, nothing changed", r.stderr)
        self.assertEqual(self.mode(self.base), 0o777)
        self.assertFalse(self.dir.exists())

    def test_an_existing_link_is_refused_and_left_alone(self) -> None:
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        os.chmod(elsewhere, 0o755)
        self.base.symlink_to(elsewhere)
        r = self.prepare()
        self.assertEqual(r.returncode, 1)
        self.assertTrue(self.base.is_symlink())
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_an_existing_file_in_the_way_is_refused(self) -> None:
        self.base.write_text("")
        os.chmod(self.base, 0o644)
        r = self.prepare()
        self.assertEqual(r.returncode, 1)
        self.assertIn("is not a directory", r.stderr)

    def test_an_unsafe_trusted_root_is_refused(self) -> None:
        os.chmod(self.root, 0o777)
        r = self.prepare()
        self.assertEqual(r.returncode, 1)
        self.assertFalse(self.base.exists())

    def test_missing_directories_are_created_0755_and_checked(self) -> None:
        r = self.prepare()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.mode(self.base), self.mode(self.dir)), (0o755, 0o755))
        self.assertIn(f"created {self.dir}", r.stdout)

    def test_existing_safe_directories_pass_unchanged(self) -> None:
        self.dir.mkdir(parents=True)
        os.chmod(self.base, 0o700)
        os.chmod(self.dir, 0o755)
        r = self.prepare()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.mode(self.base), 0o700)
        self.assertNotIn("created", r.stdout)


HOME_CHECK = HERE / "nas" / "check-k8s-admin-home.sh"


class K8sAdminHome(unittest.TestCase):
    """Review 540 A1 P1: the home that was 777 is inspected as root from another account,
    never by logging into it; anything suspicious stops before the chmod."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(os.path.realpath(self.tmp.name))
        self.home = root / "k8s_admin"
        (self.home / ".ssh").mkdir(parents=True)
        (self.home / "Music").mkdir()
        (self.home / ".bash_history").write_text("ls\n")
        key = root / "key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "k8s", "-f", str(key)], check=True)
        self.pub = (root / "key.pub").read_text()
        self.fp = subprocess.run(["ssh-keygen", "-lf", str(root / "key.pub")], capture_output=True, text=True,
                                 check=True).stdout.split()[1]
        (self.home / ".ssh" / "authorized_keys").write_text(self.pub)
        os.chmod(self.home / ".ssh" / "authorized_keys", 0o600)
        os.chmod(self.home / ".ssh", 0o700)
        os.chmod(self.home, 0o777)
        self.user = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
        self.other = root / "other"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "other", "-f", str(self.other)],
                       check=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_check(self, mode: str) -> subprocess.CompletedProcess:
        # HOME and SSH_CLIENT as an ssh login into that account would have them: the script
        # must still not run anything from the home it inspects.
        env = {**os.environ, "HOME": str(self.home), "SSH_CLIENT": "192.168.10.40 50000 22"}
        return subprocess.run(["bash", str(HOME_CHECK), self.fp, mode, str(self.home), self.user],
                              env=env, capture_output=True, text=True, timeout=30)

    def mode(self) -> int:
        return os.lstat(self.home).st_mode & 0o777

    def test_a_clean_home_is_listed_read_only_by_check(self) -> None:
        r = self.run_check("check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("clean: nothing suspicious (read only, nothing changed)", r.stdout)
        self.assertIn(self.fp, r.stdout)
        self.assertEqual(self.mode(), 0o777)

    def test_a_clean_home_is_closed_by_fix(self) -> None:
        r = self.run_check("fix")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.mode(), 0o700)

    def test_a_planted_bashrc_stops_fix_and_is_never_run(self) -> None:
        marker = self.home.parent / "ran"
        (self.home / ".bashrc").write_text(f"touch {marker}\n")
        r = self.run_check("fix")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn(f"SUSPICIOUS: {self.home}/.bashrc exists: it runs at login", r.stdout)
        self.assertIn("nothing was changed", r.stdout)
        self.assertEqual(self.mode(), 0o777)
        self.assertFalse(marker.exists())

    def test_every_startup_entry_stops_fix(self) -> None:
        for rel in (".profile", ".bash_profile", ".bash_login", ".bash_logout", ".inputrc", ".pam_environment",
                    ".ssh/rc", ".ssh/environment", ".ssh/authorized_keys2"):
            p = self.home / rel
            p.write_text("x\n")
            r = self.run_check("fix")
            self.assertEqual(r.returncode, 3, rel)
            self.assertEqual(self.mode(), 0o777, rel)
            p.unlink()

    def test_an_unknown_key_stops_fix(self) -> None:
        with open(self.home / ".ssh" / "authorized_keys", "a") as f:
            f.write((self.other.parent / "other.pub").read_text())
        r = self.run_check("fix")
        self.assertEqual(r.returncode, 3)
        self.assertIn("is not the expected one", r.stdout)
        self.assertEqual(self.mode(), 0o777)

    def test_a_forced_command_on_the_expected_key_stops_fix(self) -> None:
        (self.home / ".ssh" / "authorized_keys").write_text('command="/tmp/x" ' + self.pub)
        r = self.run_check("fix")
        self.assertEqual(r.returncode, 3)
        self.assertIn("has a key line with options in front of it", r.stdout)
        self.assertEqual(self.mode(), 0o777)

    def test_a_writable_or_linked_ssh_directory_stops_fix(self) -> None:
        os.chmod(self.home / ".ssh", 0o770)
        r = self.run_check("fix")
        self.assertEqual(r.returncode, 3)
        self.assertIn("can be written by its group or others", r.stdout)
        os.chmod(self.home / ".ssh", 0o700)
        (self.home / ".ssh").rename(self.home / "ssh-real")
        (self.home / ".ssh").symlink_to(self.home / "ssh-real")
        r = self.run_check("fix")
        self.assertEqual(r.returncode, 3)
        self.assertIn(".ssh is a link or not a directory", r.stdout)
        self.assertEqual(self.mode(), 0o777)

    def test_a_bad_fingerprint_argument_is_a_usage_error(self) -> None:
        r = subprocess.run(["bash", str(HOME_CHECK), "md5:xx", "fix", str(self.home), self.user],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.mode(), 0o777)


if __name__ == "__main__":
    unittest.main()
