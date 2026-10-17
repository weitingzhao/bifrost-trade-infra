"""scripts/gitea (CUT-gitea-primary-2026-10-17 step 0f), run locally.

compare-refs, copy-agent-branches and switch-local-remotes run real git
against bare repositories in a temporary directory standing for Gitea and
GitHub; protect-repo runs against a fake Gitea API that keeps the rules it is
given. No cluster, no network, no kubectl (GITEA_API, GITEA_GIT_BASE and
GITEA_TOKEN are given, so lib.sh neither reads the Secret nor port-forwards).

    python3 -m unittest scripts/gitea/test_gitea_scripts.py
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, **GIT_ENV, "HOME": str(cwd)}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


class FakeApi:
    """GET /repos/{org}/{repo} from `repos`; mirror-sync; branch protections kept per repository."""

    def __init__(self, repos: dict[str, bool], drop_merge_whitelist: bool = False) -> None:
        self.repos, self.rules, self.calls = repos, {}, []
        outer = self

        class H(BaseHTTPRequestHandler):
            def _send(self, code: int, body) -> None:
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _go(self) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n)) if n else None
                path = urllib.parse.unquote(self.path)
                outer.calls.append(f"{self.command} {path}")
                parts = path.split("/")  # '', api, v1, repos, org, repo, ...
                repo = parts[5] if len(parts) > 5 else ""
                rules = outer.rules.setdefault(repo, {})
                if self.command == "GET" and len(parts) == 6:
                    if repo not in outer.repos:
                        return self._send(404, {})
                    return self._send(200, {"name": repo, "parent": None, "mirror": outer.repos[repo]})
                if self.command == "POST" and path.endswith("/mirror-sync"):
                    return self._send(200, {})
                if path.endswith("/branch_protections") and self.command == "GET":
                    return self._send(200, list(rules.values()))
                if path.endswith("/branch_protections") and self.command == "POST":
                    if drop_merge_whitelist:
                        body = {**body, "enable_merge_whitelist": False}
                    rules[body["rule_name"]] = body
                    return self._send(201, body)
                if "/branch_protections/" in path:
                    name = path.split("/branch_protections/", 1)[1]
                    if name not in rules:
                        return self._send(404, {})
                    if self.command == "PATCH":
                        rules[name] = {**rules[name], **body}
                    return self._send(200, rules[name])
                return self._send(404, {})

            do_GET = do_POST = do_PATCH = _go

            def log_message(self, *a) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def api(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/api/v1"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class Scripts(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.gitea = self.root / "gitea"
        self.github = self.root / "github"
        self.work = self.root / "work"
        self.work.mkdir()
        git(self.work, "init", "-q", "--initial-branch=main")
        (self.work / "f").write_text("one")
        git(self.work, "add", "f")
        git(self.work, "commit", "-q", "-m", "one")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def bare(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        git(self.root, "init", "-q", "--bare", "--initial-branch=main", str(path))
        return path

    def run_script(self, name: str, *args: str, api: FakeApi | None = None, extra: dict | None = None) -> subprocess.CompletedProcess:
        env = {**os.environ, **GIT_ENV, "HOME": str(self.root), "GITEA_TOKEN": "fixture-admin-token",
               "GITEA_API": api.api if api else "http://127.0.0.1:9/api/v1",
               "GITEA_GIT_BASE": f"file://{self.gitea}", "GITHUB_BASE": f"file://{self.github}",
               "COMPARE_WAIT_ROUNDS": "1", **(extra or {})}
        return subprocess.run(["bash", str(HERE / name), *args], env=env, capture_output=True, text=True, timeout=120)

    # compare-refs
    def test_compare_refs_same_and_different(self) -> None:
        g = self.bare(self.gitea / "bifrost" / "r.git")
        h = self.bare(self.github / "r.git")
        for side in (g, h):
            git(self.work, "push", "-q", str(side), "main")
        api = FakeApi({"r": True})
        try:
            r = self.run_script("compare-refs.sh", "r", api=api)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("r: same", r.stdout)
            self.assertIn("POST /api/v1/repos/bifrost/r/mirror-sync", api.calls)
            git(self.work, "tag", "v1")
            git(self.work, "push", "-q", str(h), "refs/tags/v1")
            r = self.run_script("compare-refs.sh", "r", api=api)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("r: DIFFERENT", r.stdout)
            self.assertIn("GitHub: ", r.stdout)
        finally:
            api.close()

    def test_compare_refs_does_not_follow_a_global_insteadof(self) -> None:
        # after a batch the Owner's ~/.gitconfig rewrites GitHub addresses to Gitea
        g = self.bare(self.gitea / "bifrost" / "r.git")
        h = self.bare(self.github / "r.git")
        for side in (g, h):
            git(self.work, "push", "-q", str(side), "main")
        git(self.work, "tag", "v1")
        git(self.work, "push", "-q", str(h), "refs/tags/v1")
        (self.root / ".gitconfig").write_text(
            f'[url "file://{self.gitea}/bifrost/"]\n\tinsteadOf = file://{self.github}/\n', encoding="utf-8")
        api = FakeApi({"r": False})
        try:
            r = self.run_script("compare-refs.sh", "r", api=api)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("r: DIFFERENT", r.stdout)
        finally:
            api.close()

    # copy-agent-branches
    def test_copy_agent_branches_copies_only_what_is_missing(self) -> None:
        src = self.bare(self.gitea / "bifrost-agents" / "r.git")
        dst = self.bare(self.gitea / "bifrost" / "r.git")
        git(self.work, "push", "-q", str(src), "main:refs/heads/agent/t_1/a1", "main:refs/heads/agent/t_2/a1")
        (self.work / "f").write_text("two")
        git(self.work, "commit", "-q", "-am", "two")
        git(self.work, "push", "-q", str(dst), "main:refs/heads/agent/t_2/a1")
        before = git(self.root, "--git-dir", str(dst), "rev-parse", "refs/heads/agent/t_2/a1")
        r = self.run_script("copy-agent-branches.sh", "r")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("r: 1 copied, 0 already there, 1 not copied", r.stdout)
        self.assertIn("DIFFERS refs/heads/agent/t_2/a1", r.stdout)
        self.assertEqual(git(self.root, "--git-dir", str(dst), "rev-parse", "refs/heads/agent/t_2/a1"), before)
        self.assertEqual(git(self.root, "--git-dir", str(dst), "rev-parse", "refs/heads/agent/t_1/a1"),
                         git(self.root, "--git-dir", str(src), "rev-parse", "refs/heads/agent/t_1/a1"))
        r = self.run_script("copy-agent-branches.sh", "r")
        self.assertIn("r: 0 copied, 1 already there, 1 not copied", r.stdout)

    # protect-repo
    def test_protect_repo_sets_both_rules_with_merge_whitelists(self) -> None:
        api = FakeApi({"r": False})
        try:
            r = self.run_script("protect-repo.sh", "--owner", "vision", "r", api=api)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            rules = api.rules["r"]
            self.assertEqual(sorted(rules), ["agent/**", "main"])
            self.assertEqual(rules["main"]["push_whitelist_teams"], ["maintainers"])
            self.assertEqual(rules["agent/**"]["push_whitelist_teams"], ["agentd-write"])
            for rule in rules.values():
                self.assertTrue(rule["enable_merge_whitelist"])
                self.assertEqual(rule["merge_whitelist_teams"], ["maintainers"])
                self.assertEqual(rule["merge_whitelist_usernames"], ["vision"])
            self.assertIn("Settings → Tags", r.stdout)
            # a second run edits, it does not add
            r = self.run_script("protect-repo.sh", "--owner", "vision", "r", api=api)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(len(api.rules["r"]), 2)
            self.assertTrue(any(c.startswith("PATCH ") for c in api.calls))
        finally:
            api.close()

    def test_protect_repo_reports_a_rule_gitea_did_not_keep(self) -> None:
        api = FakeApi({"r": False}, drop_merge_whitelist=True)
        try:
            r = self.run_script("protect-repo.sh", "--owner", "vision", "r", api=api)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("READ BACK DIFFERS", r.stdout)
            self.assertIn("enable_merge_whitelist", r.stdout)
        finally:
            api.close()

    def test_protect_repo_needs_an_owner(self) -> None:
        r = self.run_script("protect-repo.sh", "r")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("usage", r.stderr)

    # switch-local-remotes
    def test_switch_local_remotes_and_back(self) -> None:
        ws = self.root / "ws"
        repo = ws / "bifrost-ui"
        repo.mkdir(parents=True)
        git(repo, "init", "-q")
        git(repo, "remote", "add", "origin", "git@github.com:weitingzhao/bifrost-ui.git")
        extra = {"BIFROST_WORKSPACE": str(ws), "GITEA_PUBLIC_BASE": "http://gitea.test/bifrost"}
        r = self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(git(repo, "remote", "get-url", "origin"), "http://gitea.test/bifrost/bifrost-ui.git")
        self.assertEqual(git(repo, "remote", "get-url", "github"), "git@github.com:weitingzhao/bifrost-ui.git")
        self.assertEqual(git(repo, "remote", "get-url", "--push", "github"), "no-push://github-follows-from-the-cluster")
        again = self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra)
        self.assertIn("already on Gitea", again.stdout)
        r = self.run_script("switch-local-remotes.sh", "--back", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(git(repo, "remote", "get-url", "origin"), "git@github.com:weitingzhao/bifrost-ui.git")
        self.assertNotIn("github", git(repo, "remote").split())


if __name__ == "__main__":
    unittest.main()
