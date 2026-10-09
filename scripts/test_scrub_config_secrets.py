"""TD-280: tracked config YAML never carries a credential value. Fixtures are invented."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import scrub_config_secrets as scrub  # noqa: E402

HOOK = HERE.parent / "agent-config" / "scripts" / "git-hooks" / "pre-commit"
PLANTED = "planted-value-9f2c"


class FindingsTests(unittest.TestCase):
    def test_values_are_found(self) -> None:
        text = "\n".join([
            "postgres:",
            f'  password: "{PLANTED}"',
            "golden_source:",
            f"  fdw_password: {PLANTED}",
            "massive:",
            f"  api_key: '{PLANTED}'  # comment",
            "redis_ib:",
            f"  password: {PLANTED}",
            "ops:",
            "  auth:",
            "    tokens:",
            f"      - token: {PLANTED}",
            "        role: admin",
        ])
        keys = [key for _line, key in scrub.findings(text)]
        self.assertEqual(keys, ["password", "fdw_password", "api_key", "password", "tokens", "token"])

    def test_empty_and_env_references_pass(self) -> None:
        text = "\n".join([
            'password: ""',
            "password: ''",
            "password:",
            "password: null",
            "api_key: ~",
            "fdw_password: ${PGPASSWORD}",
            "password: $REDIS_IB_PASSWORD",
            "token_env: OPS_ADMIN_TOKEN",
            "tokens: []",
            "max_tokens: 4096",
        ])
        self.assertEqual(scrub.findings(text), [])

    def test_check_names_the_line_but_never_the_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "config" / "config.dev.yaml"
            cfg.parent.mkdir(parents=True)
            cfg.write_text(f"redis_ib:\n  password: {PLANTED}\n", encoding="utf-8")
            old_root, old_files = scrub.ROOT, scrub.FILES
            scrub.ROOT, scrub.FILES = root, [cfg]
            try:
                from contextlib import redirect_stderr, redirect_stdout
                import io
                err, out = io.StringIO(), io.StringIO()
                with redirect_stderr(err), redirect_stdout(out):
                    rc = scrub.check(staged=False)
            finally:
                scrub.ROOT, scrub.FILES = old_root, old_files
        self.assertEqual(rc, 1)
        self.assertIn("config/config.dev.yaml:2 password", err.getvalue())
        self.assertNotIn(PLANTED, err.getvalue() + out.getvalue())


class PreCommitHookTests(unittest.TestCase):
    def _repo(self, tmp: Path, with_check: bool) -> Path:
        repo = tmp / "repo"
        (repo / "config").mkdir(parents=True)
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        subprocess.run(["git", "init", "-q", str(repo)], check=True, env=env)
        if with_check:
            (repo / "scripts").mkdir()
            shutil.copy(HERE / "scrub_config_secrets.py", repo / "scripts" / "scrub_config_secrets.py")
        return repo

    def _stage_and_hook(self, repo: Path, text: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        (repo / "config" / "config.dev.yaml").write_text(text, encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "config/config.dev.yaml"], check=True, env=env)
        return subprocess.run(["sh", str(HOOK)], cwd=repo, capture_output=True, text=True, env=env)

    def test_hook_refuses_a_staged_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(Path(tmp), with_check=True)
            r = self._stage_and_hook(repo, f"postgres:\n  password: {PLANTED}\n")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertNotIn(PLANTED, r.stdout + r.stderr)

    def test_hook_checks_the_index_not_the_working_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(Path(tmp), with_check=True)
            r = self._stage_and_hook(repo, f"postgres:\n  password: {PLANTED}\n")
            self.assertEqual(r.returncode, 1)
            # Empty the working copy without restaging: the commit would still carry the value.
            (repo / "config" / "config.dev.yaml").write_text('postgres:\n  password: ""\n', encoding="utf-8")
            r = subprocess.run(["sh", str(HOOK)], cwd=repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_hook_passes_an_empty_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(Path(tmp), with_check=True)
            r = self._stage_and_hook(repo, 'postgres:\n  password: ""\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_hook_leaves_an_old_scrub_only_script_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(Path(tmp), with_check=False)
            (repo / "scripts").mkdir()
            old = repo / "scripts" / "scrub_config_secrets.py"
            old.write_text("import pathlib\npathlib.Path('ran').write_text('x')\n", encoding="utf-8")
            r = self._stage_and_hook(repo, f"postgres:\n  password: {PLANTED}\n")
            ran = (repo / "ran").exists()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(ran, "the hook ran a script that has no --check")

    def test_hook_is_a_no_op_in_other_repos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(Path(tmp), with_check=False)
            r = self._stage_and_hook(repo, f"postgres:\n  password: {PLANTED}\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
