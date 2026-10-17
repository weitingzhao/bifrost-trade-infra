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

    def __init__(self, repos: dict[str, bool], drop_merge_whitelist: bool = False, redirect: str | None = None,
                 rules: dict | None = None) -> None:
        self.repos, self.rules, self.calls, self.auth = repos, rules or {}, [], []
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
                outer.auth.append(self.headers.get("Authorization", ""))
                if redirect:
                    self.send_response(302)
                    self.send_header("Location", redirect + self.path)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return None
                if path == "/api/v1/version":
                    return self._send(200, {"version": "1.21.11"})
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

    def run_script(self, name: str, *args: str, api: FakeApi | None = None, extra: dict | None = None,
                   cwd: Path | None = None, bash: tuple[str, ...] = (), path: Path | None = None,
                   connect: bool = False) -> subprocess.CompletedProcess:
        env = {**os.environ, **GIT_ENV, "HOME": str(self.root), "GITEA_TOKEN": "fixture-admin-token",
               "GITEA_API": api.api if api else "http://127.0.0.1:9/api/v1",
               "GITEA_GIT_BASE": f"file://{self.gitea}", "GITHUB_BASE": f"file://{self.github}",
               "COMPARE_WAIT_ROUNDS": "1", **(extra or {})}
        if connect:  # lib.sh makes the port-forward and reads the Secret itself
            for key in ("GITEA_TOKEN", "GITEA_API", "GITEA_GIT_BASE"):
                env.pop(key)
        if path:
            env["PATH"] = f"{path}:{env['PATH']}"
        return subprocess.run(["bash", *bash, str(HERE / name), *args], env=env, cwd=cwd or self.root,
                              capture_output=True, text=True, timeout=120)

    def wrapper(self, name: str, body: str) -> Path:
        """A directory holding an executable `name` (put in front of PATH)."""
        d = self.root / f"bin-{name}-{len(list(self.root.iterdir()))}"
        d.mkdir()
        f = d / name
        f.write_text("#!/bin/bash\n" + body)
        f.chmod(0o755)
        return d

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
    def checkout(self, *config: tuple[str, str]) -> tuple[Path, dict]:
        ws = self.root / "ws"
        repo = ws / "bifrost-ui"
        repo.mkdir(parents=True)
        git(repo, "init", "-q")
        git(repo, "remote", "add", "origin", "git@github.com:weitingzhao/bifrost-ui.git")
        for key, value in config:
            git(repo, "config", "--add", key, value)
        return repo, {"BIFROST_WORKSPACE": str(ws), "GITEA_PUBLIC_BASE": "http://gitea.test/bifrost"}

    def remotes(self, repo: Path) -> str:
        return git(repo, "config", "--get-regexp", r"^remote\.")

    def test_switch_local_remotes_and_back(self) -> None:
        repo, extra = self.checkout(("remote.origin.tagOpt", "--no-tags"))
        before = self.remotes(repo)
        r = self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(git(repo, "remote", "get-url", "--push", "--all", "origin"), "http://gitea.test/bifrost/bifrost-ui.git")
        self.assertEqual(git(repo, "remote", "get-url", "github"), "git@github.com:weitingzhao/bifrost-ui.git")
        self.assertEqual(git(repo, "remote", "get-url", "--push", "github"), "no-push://github-follows-from-the-cluster")
        self.assertEqual(git(repo, "config", "remote.origin.tagOpt"), "--no-tags")
        again = self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra)
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        r = self.run_script("switch-local-remotes.sh", "--back", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.remotes(repo), before)
        self.assertFalse((repo / ".git" / "config.before-gitea-primary").exists())

    def test_switch_removes_a_github_push_address_when_origin_already_reads_gitea(self) -> None:
        # review 246 A4: origin already fetches from Gitea, its push address is still GitHub
        repo, extra = self.checkout()
        git(repo, "remote", "set-url", "origin", "http://gitea.test/bifrost/bifrost-ui.git")
        git(repo, "remote", "set-url", "--push", "origin", "https://github.com/weitingzhao/bifrost-ui.git")
        r = self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(git(repo, "remote", "get-url", "--push", "--all", "origin"), "http://gitea.test/bifrost/bifrost-ui.git")

    def test_back_fails_while_a_global_insteadof_still_rewrites_origin(self) -> None:
        # review 246 A5: batch step 7 put GitHub → Gitea in ~/.gitconfig
        repo, extra = self.checkout(("remote.origin.pushurl", "git@github.com:weitingzhao/bifrost-ui.git"))
        before = self.remotes(repo)
        self.assertEqual(self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra).returncode, 0)
        gitconfig = self.root / ".gitconfig"
        gitconfig.write_text('[url "http://gitea.test/bifrost/bifrost-ui.git"]\n\tinsteadOf = git@github.com:weitingzhao/bifrost-ui.git\n')
        r = self.run_script("switch-local-remotes.sh", "--back", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("insteadOf", r.stderr)
        self.assertTrue((repo / ".git" / "config.before-gitea-primary").exists())
        gitconfig.unlink()
        r = self.run_script("switch-local-remotes.sh", "--back", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.remotes(repo), before)

    def test_switch_refuses_a_github_remote_that_points_elsewhere(self) -> None:
        # review 246 B6: a github remote already there is not a slot to overwrite
        repo, extra = self.checkout()
        git(repo, "remote", "add", "github", "git@github.com:someone/other.git")
        before = self.remotes(repo)
        r = self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.remotes(repo), before)
        self.assertFalse((repo / ".git" / "config.before-gitea-primary").exists())

    # review 248 A3: a switch that would still push to GitHub is caught before anything changes
    def test_switch_checks_the_new_config_before_changing_anything(self) -> None:
        repo, extra = self.checkout()
        before = self.remotes(repo)
        (self.root / ".gitconfig").write_text(
            '[url "https://github.com/weitingzhao/"]\n\tpushInsteadOf = http://gitea.test/bifrost/\n')
        r = self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("nothing changed", r.stderr)
        self.assertEqual(self.remotes(repo), before)
        self.assertFalse((repo / ".git" / "config.before-gitea-primary").exists())

    def test_a_failed_switch_puts_every_checkout_of_the_run_back(self) -> None:
        # the second checkout's own include rewrites Gitea to GitHub; the scratch check cannot see it
        repo, extra = self.checkout()
        other = repo.parent / "bifrost-platform"
        other.mkdir()
        git(other, "init", "-q")
        git(other, "remote", "add", "origin", "git@github.com:weitingzhao/bifrost-platform.git")
        (other / ".git" / "extra.cfg").write_text('[url "https://github.com/weitingzhao/"]\n\tpushInsteadOf = http://gitea.test/bifrost/\n')
        git(other, "config", "include.path", "extra.cfg")
        before = (self.remotes(repo), self.remotes(other))
        r = self.run_script("switch-local-remotes.sh", "bifrost-ui", "bifrost-platform", extra=extra)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("back as it was", r.stderr)
        self.assertEqual((self.remotes(repo), self.remotes(other)), before)
        for d in (repo, other):
            self.assertFalse((d / ".git" / "config.before-gitea-primary").exists())

    # review 248 B4: a remote key with no value is refused, not restored as a string
    def test_switch_refuses_a_remote_key_with_no_value(self) -> None:
        repo, extra = self.checkout()
        cfg = repo / ".git" / "config"
        cfg.write_text(cfg.read_text().replace('[remote "origin"]\n', '[remote "origin"]\n\tprune\n'))
        before = cfg.read_text()
        r = self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("no value", r.stderr)
        self.assertEqual(cfg.read_text(), before)

    # review 248 B5: a config git (or another run) holds the lock on is left alone, lock included
    def test_switch_waits_for_nobody_and_leaves_a_held_lock(self) -> None:
        repo, extra = self.checkout()
        held = repo / ".git" / "config.lock"
        held.write_text("someone else")
        before = self.remotes(repo)
        r = self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("locked", r.stderr)
        self.assertEqual(self.remotes(repo), before)
        self.assertEqual(held.read_text(), "someone else")

    def test_switch_and_back_on_bash_3(self) -> None:
        if not Path("/bin/bash").exists():
            self.skipTest("no /bin/bash")
        repo, extra = self.checkout(("remote.origin.pushurl", "git@github.com:weitingzhao/bifrost-ui.git"))
        before = self.remotes(repo)
        env = {**os.environ, **GIT_ENV, "HOME": str(self.root), **extra}
        for args in ((), ("--back",)):
            r = subprocess.run(["/bin/bash", str(HERE / "switch-local-remotes.sh"), *args, "bifrost-ui"], env=env,
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.remotes(repo), before)

    def test_back_without_a_saved_config_changes_nothing(self) -> None:
        repo, extra = self.checkout()
        before = self.remotes(repo)
        r = self.run_script("switch-local-remotes.sh", "--back", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.remotes(repo), before)

    # lib.sh: the token goes nowhere else (review 246 A1, A2, A3, B10)
    def test_a_redirect_is_not_followed_with_the_token(self) -> None:
        other = FakeApi({"r": False})
        api = FakeApi({}, redirect=f"http://127.0.0.1:{other.server.server_address[1]}")
        try:
            r = self.run_script("protect-repo.sh", "--owner", "vision", "r", api=api)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("302", r.stderr)
            self.assertEqual(other.calls, [])
        finally:
            api.close()
            other.close()

    def fake_kubectl(self, api: FakeApi | None, fail: bool = False, die_on_secret: bool = False) -> Path:
        port = api.server.server_address[1] if api else 9
        token = "a3ViZWN0bC1zZWNyZXQtdG9rZW4="  # "kubectl-secret-token"
        pidfile = self.root / "forward.pid"
        pf = 'echo "error: unable to listen on any of the requested ports" >&2; exit 1' if fail else (
            f'echo $$ > "{pidfile}"; echo "Forwarding from 127.0.0.1:{port} -> 3000"; echo "Forwarding from [::1]:{port} -> 3000"; exec sleep 60')
        secret = f"""echo '{{"data": {{"gitea_admin_token": "{token}"}}}}'"""
        if die_on_secret:
            secret = f'kill "$(cat "{pidfile}")"; sleep 0.2; ' + secret
        return self.wrapper("kubectl", f"""case "$*" in
  *port-forward*) {pf} ;;
  *"get secret"*) {secret} ;;
  *) exit 2 ;;
esac
""")

    def forward_alive(self) -> bool:
        pid = int((self.root / "forward.pid").read_text())
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False

    def test_a_port_forward_that_did_not_start_sends_nothing(self) -> None:
        # something else answering on a local port is never asked
        api = FakeApi({"r": False})
        try:
            r = self.run_script("protect-repo.sh", "--owner", "vision", "r", connect=True,
                                path=self.fake_kubectl(api, fail=True))
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("did not start", r.stderr)
            self.assertEqual(api.calls, [])
        finally:
            api.close()

    def test_the_port_forward_kubectl_chose_is_used(self) -> None:
        api = FakeApi({"r": False})
        try:
            r = self.run_script("protect-repo.sh", "--owner", "vision", "r", connect=True, path=self.fake_kubectl(api))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(sorted(api.rules["r"]), ["agent/**", "main"])
            self.assertEqual({a for a in api.auth if a}, {"token kubectl-secret-token"})
        finally:
            api.close()

    # review 248 A1: no proxy from the Owner's environment carries the token
    def test_no_proxy_is_used(self) -> None:
        proxy = FakeApi({})
        api = FakeApi({"r": False})
        address = f"http://127.0.0.1:{proxy.server.server_address[1]}"
        extra = {k: address for k in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")}
        extra.update(no_proxy="", NO_PROXY="")
        try:
            r = self.run_script("protect-repo.sh", "--owner", "vision", "r", connect=True, path=self.fake_kubectl(api), extra=extra)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(proxy.calls, [])
            self.assertEqual(sorted(api.rules["r"]), ["agent/**", "main"])
        finally:
            api.close()
            proxy.close()

    # review 248 A2: a forward that is gone by the time the token is read gets nothing sent through its port
    def test_a_forward_gone_after_the_check_gets_nothing(self) -> None:
        api = FakeApi({"r": False})
        try:
            r = self.run_script("protect-repo.sh", "--owner", "vision", "r", connect=True,
                                path=self.fake_kubectl(api, die_on_secret=True))
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("port-forward to svc/gitea stopped", r.stderr)
            self.assertEqual([a for a in api.auth if a], [])
        finally:
            api.close()

    # review 248 B6: the forward is stopped even when removing the work directory fails
    def test_copy_stops_the_forward_when_rm_fails(self) -> None:
        api = FakeApi({})
        try:
            bad_rm = self.wrapper("rm", "exit 1\n")
            kubectl = self.fake_kubectl(api)
            r = self.run_script("copy-agent-branches.sh", "r", connect=True, path=Path(f"{bad_rm}:{kubectl}"))
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse(self.forward_alive())
        finally:
            api.close()

    # review 248 B7: a rule that can match neither main nor agent/ stays
    def test_protect_repo_keeps_a_rule_that_cannot_match_first(self) -> None:
        api = FakeApi({"r": False}, rules={"r": {"release/**": {"rule_name": "release/**", "enable_push": True}}})
        try:
            r = self.run_script("protect-repo.sh", "--owner", "vision", "r", api=api)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(sorted(api.rules["r"]), ["agent/**", "main", "release/**"])
        finally:
            api.close()

    def test_compare_refs_does_not_follow_the_checkout_it_runs_in(self) -> None:
        g = self.bare(self.gitea / "bifrost" / "r.git")
        h = self.bare(self.github / "r.git")
        for side in (g, h):
            git(self.work, "push", "-q", str(side), "main")
        git(self.work, "tag", "v1")
        git(self.work, "push", "-q", str(h), "refs/tags/v1")
        here = self.root / "here"
        here.mkdir()
        git(here, "init", "-q")
        git(here, "config", f"url.file://{self.gitea}/bifrost/.insteadOf", f"file://{self.github}/")
        api = FakeApi({"r": False})
        try:
            r = self.run_script("compare-refs.sh", "r", api=api, cwd=here)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("r: DIFFERENT", r.stdout)
        finally:
            api.close()

    def test_xtrace_does_not_print_the_token(self) -> None:
        api = FakeApi({"r": False})
        try:
            r = self.run_script("protect-repo.sh", "--owner", "vision", "r", api=api, bash=("-x",))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertNotIn("fixture-admin-token", r.stdout + r.stderr)
        finally:
            api.close()

    # protect-repo: another rule would decide first (review 246 B9)
    def test_protect_repo_stops_on_another_branch_rule(self) -> None:
        api = FakeApi({"r": False}, rules={"r": {"**": {"rule_name": "**", "enable_push": True}}})
        try:
            r = self.run_script("protect-repo.sh", "--owner", "vision", "r", api=api)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("STOPPED", r.stdout)
            self.assertEqual(sorted(api.rules["r"]), ["**"])
            self.assertFalse(any(c.startswith(("POST ", "PATCH ")) for c in api.calls))
        finally:
            api.close()

    # copy-agent-branches: a branch made meanwhile is not fast-forwarded (B7); a failed listing stops it (B8)
    def test_copy_does_not_fast_forward_a_branch_made_meanwhile(self) -> None:
        src = self.bare(self.gitea / "bifrost-agents" / "r.git")
        dst = self.bare(self.gitea / "bifrost" / "r.git")
        ancestor = git(self.work, "rev-parse", "HEAD")
        git(self.work, "push", "-q", str(dst), "main")  # the target has the ancestor
        (self.work / "f").write_text("two")
        git(self.work, "commit", "-q", "-am", "two")
        git(self.work, "push", "-q", str(src), "main:refs/heads/agent/t_1/a1")
        real = subprocess.run(["sh", "-c", "command -v git"], capture_output=True, text=True, check=True).stdout.strip()
        race = self.wrapper("git", f"""if [[ " $* " == *" push "* && ! -e "{self.root}/raced" ]]; then
  touch "{self.root}/raced"
  "{real}" --git-dir "{dst}" update-ref refs/heads/agent/t_1/a1 {ancestor}
fi
exec "{real}" "$@"
""")
        r = self.run_script("copy-agent-branches.sh", "r", path=race)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("REFUSED refs/heads/agent/t_1/a1", r.stdout)
        self.assertEqual(git(self.root, "--git-dir", str(dst), "rev-parse", "refs/heads/agent/t_1/a1"), ancestor)

    def test_copy_stops_when_the_branches_cannot_be_listed(self) -> None:
        src = self.bare(self.gitea / "bifrost-agents" / "r.git")
        self.bare(self.gitea / "bifrost" / "r.git")
        git(self.work, "push", "-q", str(src), "main:refs/heads/agent/t_1/a1")
        real = subprocess.run(["sh", "-c", "command -v git"], capture_output=True, text=True, check=True).stdout.strip()
        broken = self.wrapper("git", f"""if [[ " $* " == *" for-each-ref "* ]]; then exit 128; fi
exec "{real}" "$@"
""")
        r = self.run_script("copy-agent-branches.sh", "r", path=broken)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("0 copied", r.stdout)

    # review 249 A1: a linked worktree's own config is read back too
    def test_switch_reads_back_a_linked_worktree_and_puts_it_back(self) -> None:
        main = self.root / "main" / "bifrost-ui"
        main.mkdir(parents=True)
        git(main, "init", "-q", "--initial-branch=main")
        (main / "f").write_text("x")
        git(main, "add", "f")
        git(main, "commit", "-q", "-m", "x")
        git(main, "remote", "add", "origin", "git@github.com:weitingzhao/bifrost-ui.git")
        git(main, "config", "extensions.worktreeConfig", "true")
        ws = self.root / "ws"
        ws.mkdir()
        linked = ws / "bifrost-ui"
        git(main, "worktree", "add", "-q", "-b", "side", str(linked))
        git(linked, "config", "--worktree", "remote.origin.pushurl", "https://github.com/weitingzhao/bifrost-ui.git")
        before = git(main, "config", "--get-regexp", r"^remote\.")
        extra = {"BIFROST_WORKSPACE": str(ws), "GITEA_PUBLIC_BASE": "http://gitea.test/bifrost"}
        r = self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"in {linked.resolve()}", r.stderr)
        self.assertEqual(git(main, "config", "--get-regexp", r"^remote\."), before)
        self.assertFalse((main / ".git" / "config.before-gitea-primary").exists())

    def mv_failing_for(self, path: Path) -> Path:
        real = subprocess.run(["sh", "-c", "command -v mv"], capture_output=True, text=True, check=True).stdout.strip()
        return self.wrapper("mv", f"""if [[ "${{@: -1}}" == "{path}" && ! -e "{self.root}/mv-failed" ]]; then touch "{self.root}/mv-failed"; exit 1; fi
exec "{real}" "$@"
""")

    # review 249 B2: any failure puts back every checkout the run changed, the switch and --back alike
    def test_a_failed_install_puts_the_whole_batch_back(self) -> None:
        repo, extra = self.checkout()
        other = repo.parent / "bifrost-platform"
        other.mkdir()
        git(other, "init", "-q")
        git(other, "remote", "add", "origin", "git@github.com:weitingzhao/bifrost-platform.git")
        before = (self.remotes(repo), self.remotes(other))
        failing = self.mv_failing_for((other / ".git" / "config").resolve())
        r = self.run_script("switch-local-remotes.sh", "bifrost-ui", "bifrost-platform", extra=extra, path=failing)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.remotes(repo), self.remotes(other)), before)
        self.assertFalse((repo / ".git" / "config.before-gitea-primary").exists())
        # now switched for real, then a --back that fails half-way
        (self.root / "mv-failed").unlink()
        self.assertEqual(self.run_script("switch-local-remotes.sh", "bifrost-ui", "bifrost-platform", extra=extra).returncode, 0)
        switched = (self.remotes(repo), self.remotes(other))
        r = self.run_script("switch-local-remotes.sh", "--back", "bifrost-ui", "bifrost-platform", extra=extra, path=failing)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.remotes(repo), self.remotes(other)), switched)
        for d in (repo, other):
            self.assertTrue((d / ".git" / "config.before-gitea-primary").exists())

    # review 249 B3: the old fixed temporary name, as a link to the saved copy, changes nothing
    def test_a_link_where_the_old_temporary_file_was_is_not_followed(self) -> None:
        repo, extra = self.checkout()
        self.assertEqual(self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra).returncode, 0)
        saved = repo / ".git" / "config.before-gitea-primary"
        kept = saved.read_bytes()
        (repo / ".git" / "config.tmp-gitea-primary").symlink_to(saved)
        r = self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(saved.read_bytes(), kept)
        self.assertFalse((repo / ".git" / "config").is_symlink())

    # review 249 C5: a lock path that is already there, as a link, is someone else's and stays
    def test_a_linked_lock_is_not_taken(self) -> None:
        repo, extra = self.checkout()
        lock = repo / ".git" / "config.lock"
        lock.symlink_to("/dev/null")
        before = self.remotes(repo)
        r = self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("locked", r.stderr)
        self.assertTrue(lock.is_symlink())
        self.assertEqual(self.remotes(repo), before)

    # review 249 B4: a rule is read as a glob, not by its fixed start
    def test_protect_repo_reads_rules_as_globs(self) -> None:
        for kept in ("main?", "ma[st]er"):
            api = FakeApi({"r": False}, rules={"r": {kept: {"rule_name": kept, "enable_push": True}}})
            try:
                r = self.run_script("protect-repo.sh", "--owner", "vision", "r", api=api)
                self.assertEqual(r.returncode, 0, kept + r.stdout + r.stderr)
            finally:
                api.close()
        api = FakeApi({"r": False}, rules={"r": {"a**": {"rule_name": "a**", "enable_push": True}}})
        try:
            r = self.run_script("protect-repo.sh", "--owner", "vision", "r", api=api)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("STOPPED", r.stdout)
        finally:
            api.close()


class ApplyStep0(unittest.TestCase):
    """apply-step0.sh against a fake kubectl that records its calls and what it was asked to apply; HOME is a temporary directory."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.infra = HERE.parent.parent
        self.home = self.root / "home"
        kube = self.home / ".bifrost-owner" / "kube"
        kube.mkdir(parents=True)
        (kube / "admin.yaml").write_text("fixture\n")
        self.calls = self.root / "calls"
        self.applied = self.root / "applied"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.kubectl("true")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def kubectl(self, on_apply: str) -> None:
        k = self.bin / "kubectl"
        k.write_text(f"""#!/bin/bash
echo "$*" >> "{self.calls}"
case "$1" in
  kustomize) cat "$2"/*.sh "$2"/*.py "$2"/*.yaml 2> /dev/null; true ;;
  apply) f="${{@: -1}}"; cat "$f" >> "{self.applied}"; {on_apply} ;;
  *) exit 2 ;;
esac
""")
        k.chmod(0o755)

    def run_it(self, *args: str, infra: Path | None = None) -> subprocess.CompletedProcess:
        script = (infra or self.infra) / "scripts" / "gitea" / "apply-step0.sh"
        env = {**os.environ, "HOME": str(self.home), "PATH": f"{self.bin}:{os.environ['PATH']}"}
        return subprocess.run(["bash", str(script), *args], env=env, capture_output=True, text=True, timeout=60)

    def applies(self) -> list[str]:
        return [c for c in (self.calls.read_text().splitlines() if self.calls.exists() else []) if c.startswith("apply")]

    def test_check_only_dry_runs(self) -> None:
        r = self.run_it("check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.applies()), 1)
        self.assertIn("--dry-run=server", self.applies()[0])

    def test_apply_dry_runs_then_applies_the_same_file(self) -> None:
        r = self.run_it("apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        dry, real = self.applies()
        self.assertIn("--dry-run=server", dry)
        self.assertNotIn("--dry-run", real)
        self.assertEqual(dry.split()[-1], real.split()[-1])
        text = self.applied.read_text()
        for name in ("bifrost-gitea-mirror-sync", "bifrost-ci", "BifrostGitHubSyncStale", "bifrost-github-sync-reconcile"):
            self.assertIn(name, text)

    def test_the_working_tree_is_not_what_is_applied(self) -> None:
        # review 250 A3: a change git does not show (assume-unchanged) and a plain one
        copy = self.root / "infra"
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(self.infra), str(copy)], check=True, capture_output=True)
        (copy / "scripts" / "gitea" / "apply-step0.sh").write_bytes((HERE / "apply-step0.sh").read_bytes())
        task = copy / "k8s" / "cicd" / "tekton" / "task-gitea-mirror-sync.yaml"
        subprocess.run(["git", "-C", str(copy), "update-index", "--assume-unchanged", str(task)], check=True)
        task.write_text(task.read_text().replace("bifrost-gitea-mirror-sync", "unreviewed-task"))
        sync = copy / "k8s" / "cicd" / "github-sync" / "sync.sh"
        sync.write_text(sync.read_text() + "\n# unreviewed change\n")
        r = self.run_it("apply", infra=copy)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = self.applied.read_text()
        self.assertNotIn("unreviewed", text)
        self.assertIn("bifrost-gitea-mirror-sync", text)

    def test_a_failed_dry_run_applies_nothing(self) -> None:
        self.kubectl('[[ "$*" != *--dry-run* ]]')
        r = self.run_it("apply")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.applies()), 1)

    def test_a_missing_commit_changes_nothing(self) -> None:
        copy = self.root / "shallow"
        subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{self.infra}", str(copy)], check=True, capture_output=True)
        (copy / "scripts" / "gitea" / "apply-step0.sh").write_bytes((HERE / "apply-step0.sh").read_bytes())
        r = self.run_it("apply", infra=copy)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("git fetch", r.stderr)
        self.assertEqual(self.applies(), [])

if __name__ == "__main__":
    unittest.main()
