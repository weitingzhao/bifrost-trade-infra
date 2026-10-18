"""scripts/gitea (CUT-gitea-primary-2026-10-17 step 0f), run locally.

compare-refs, copy-agent-branches and switch-local-remotes run real git
against bare repositories in a temporary directory standing for Gitea and
GitHub; protect-repo runs against a fake Gitea API that keeps the rules it is
given. No cluster, no network, no kubectl (GITEA_API, GITEA_GIT_BASE and
GITEA_TOKEN are given, so lib.sh neither reads the Secret nor port-forwards).

    python3 -m unittest scripts/gitea/test_gitea_scripts.py
"""

from __future__ import annotations

import base64
import json
import os
import select
import shutil
import subprocess
import tempfile
import threading
import time
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


def run_on_pty(cmd: list[str], env: dict, typed: str | None) -> tuple[subprocess.CompletedProcess, str]:
    """Runs cmd with a pty as stdin, types `typed` once it prompts "(input hidden): "; returns
    the result and what the terminal echoed. bash's read -s flushes pending terminal input when
    it turns echo off, so type only once the prompt is out, as a person would."""
    master, slave = os.openpty()
    try:
        p = subprocess.Popen(cmd, env=env, stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.close(slave)
        slave = -1
        err = b""
        deadline = time.monotonic() + 30
        while b"(input hidden): " not in err and time.monotonic() < deadline:
            ready, _, _ = select.select([p.stderr], [], [], 0.5)
            if ready:
                chunk = os.read(p.stderr.fileno(), 4096)
                if not chunk:
                    break
                err += chunk
        if b"(input hidden): " in err and typed is not None:
            time.sleep(0.3)
            os.write(master, (typed + "\n").encode())
        out, rest = p.communicate(timeout=30)
        echoed = b""
        while select.select([master], [], [], 0.2)[0]:
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            echoed += chunk
        return subprocess.CompletedProcess(cmd, p.returncode, out.decode(), (err + rest).decode()), echoed.decode(errors="replace")
    finally:
        if slave >= 0:
            os.close(slave)
        os.close(master)


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

    # review 250 A1: a working tree whose path holds a newline is read back too
    def test_a_worktree_path_with_a_newline_is_read_back(self) -> None:
        repo, extra = self.checkout()
        (repo / "f").write_text("x")
        git(repo, "add", "f")
        git(repo, "commit", "-q", "-m", "x")
        git(repo, "config", "extensions.worktreeConfig", "true")
        odd = self.root / "new\nline"
        git(repo, "worktree", "add", "-q", "-b", "side", str(odd))
        git(odd, "config", "--worktree", "remote.origin.pushurl", "https://github.com/weitingzhao/bifrost-ui.git")
        before = self.remotes(repo)
        r = self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.remotes(repo), before)

    # review 250 B4: a report that cannot be written undoes the run
    def test_a_report_that_cannot_be_written_undoes_the_run(self) -> None:
        repo, extra = self.checkout()
        before = self.remotes(repo)
        env = {**os.environ, **GIT_ENV, "HOME": str(self.root), **extra}
        with open(os.devnull, "rb") as read_only:
            r = subprocess.run(["bash", str(HERE / "switch-local-remotes.sh"), "bifrost-ui"], env=env, stdout=read_only,
                               stderr=subprocess.PIPE, text=True, timeout=60)
        self.assertNotEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.remotes(repo), before)
        self.assertFalse((repo / ".git" / "config.before-gitea-primary").exists())

    # review 250 C5: the saved copy is created only if absent; a link there is not taken for it
    def test_a_link_where_the_saved_copy_goes_is_left_alone(self) -> None:
        repo, extra = self.checkout()
        saved = repo / ".git" / "config.before-gitea-primary"
        saved.symlink_to("/dev/null")
        before = self.remotes(repo)
        r = self.run_script("switch-local-remotes.sh", "bifrost-ui", extra=extra)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(saved.is_symlink())
        self.assertEqual(self.remotes(repo), before)

    # review 249 B4, 250 A2: a rule is read as a gobwas glob (only ! negates a class)
    def test_protect_repo_reads_rules_as_globs(self) -> None:
        for stopped in ("[^m]ain", "a**"):
            api = FakeApi({"r": False}, rules={"r": {stopped: {"rule_name": stopped, "enable_push": True}}})
            try:
                r = self.run_script("protect-repo.sh", "--owner", "vision", "r", api=api)
                self.assertEqual(r.returncode, 1, stopped + r.stdout + r.stderr)
                self.assertIn("STOPPED", r.stdout)
            finally:
                api.close()
        for kept in ("main?", "ma[st]er", "[^x]ain", "agent/."):
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

    def run_it(self, *args: str, infra: Path | None = None, extra: dict | None = None) -> subprocess.CompletedProcess:
        script = (infra or self.infra) / "scripts" / "gitea" / "apply-step0.sh"
        env = {**os.environ, "HOME": str(self.home), "PATH": f"{self.bin}:{os.environ['PATH']}", **(extra or {})}
        return subprocess.run(["bash", str(script), *args], env=env, capture_output=True, text=True, timeout=60)

    def copy_of_infra(self) -> tuple[Path, callable]:
        copy = self.root / "infra"
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(self.infra), str(copy)], check=True, capture_output=True)
        (copy / "scripts" / "gitea" / "apply-step0.sh").write_bytes((HERE / "apply-step0.sh").read_bytes())
        g = lambda *a, **k: subprocess.run(["git", "-C", str(copy), *a], check=True, capture_output=True, text=True, **k).stdout.strip()
        return copy, g

    @staticmethod
    def loose_object(objects: Path, name: str, content: str) -> None:
        import zlib
        data = content.encode()
        path = objects / name[:2] / name[2:]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(zlib.compress(b"blob %d\0" % len(data) + data))

    def test_an_inherited_object_store_is_not_read(self) -> None:
        # review 252 A2: GIT_OBJECT_DIRECTORY holds an object named like the reviewed blob, other content
        copy, g = self.copy_of_infra()
        path = "k8s/cicd/tekton/task-gitea-mirror-sync.yaml"
        reviewed = "1de78f6811f209f766094dd621efa8c00711efe1"
        blob = g("rev-parse", f"{reviewed}:{path}")
        forged = self.root / "forged-objects"
        self.loose_object(forged, blob, g("show", f"{reviewed}:{path}").replace("bifrost-gitea-mirror-sync", "unreviewed-task") + "\n")
        extra = {"GIT_OBJECT_DIRECTORY": str(forged), "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(copy / ".git" / "objects")}
        r = self.run_it("apply", infra=copy, extra=extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("unreviewed", self.applied.read_text())

    # review 253b A1: conversions git archive would run (a smudge filter, line endings) are not run
    def test_a_smudge_filter_is_not_run(self) -> None:
        copy, g = self.copy_of_infra()
        marker = self.root / "filter-ran"
        g("config", "filter.x.smudge", f"touch {marker}; sed s/bifrost-gitea-mirror-sync/unreviewed-task/")
        (copy / ".git" / "info").mkdir(exist_ok=True)
        (copy / ".git" / "info" / "attributes").write_text("task-gitea-mirror-sync.yaml filter=x\n")
        r = self.run_it("apply", infra=copy)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(b"unreviewed", self.applied.read_bytes())
        self.assertFalse(marker.exists())

    def test_line_endings_are_not_converted(self) -> None:
        copy, _ = self.copy_of_infra()
        cfg = self.root / "global.gitconfig"
        cfg.write_text("[core]\n\tautocrlf = true\n")
        r = self.run_it("apply", infra=copy, extra={"GIT_CONFIG_GLOBAL": str(cfg)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(b"\r", self.applied.read_bytes())

    def test_an_object_that_does_not_match_its_name_stops_it(self) -> None:
        copy, _ = self.copy_of_infra()
        self.loose_object(copy / ".git" / "objects", "ab" * 20, "not what this name says\n")
        r = self.run_it("apply", infra=copy)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("do not match their names", r.stderr)
        self.assertEqual(self.applies(), [])

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

    def test_a_replacement_object_is_not_what_is_applied(self) -> None:
        # review 251 A1: refs/replace stands a different blob in for the reviewed one
        copy = self.root / "infra"
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(self.infra), str(copy)], check=True, capture_output=True)
        (copy / "scripts" / "gitea" / "apply-step0.sh").write_bytes((HERE / "apply-step0.sh").read_bytes())
        path = "k8s/cicd/tekton/task-gitea-mirror-sync.yaml"
        reviewed = "1de78f6811f209f766094dd621efa8c00711efe1"
        g = lambda *a, **k: subprocess.run(["git", "-C", str(copy), *a], check=True, capture_output=True, text=True, **k).stdout.strip()
        original = g("rev-parse", f"{reviewed}:{path}")
        text = g("show", f"{reviewed}:{path}").replace("bifrost-gitea-mirror-sync", "unreviewed-task") + "\n"
        forged = g("hash-object", "-w", "--stdin", input=text)
        g("replace", original, forged)
        self.assertIn("unreviewed-task", g("show", f"{reviewed}:{path}"))
        r = self.run_it("apply", infra=copy)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("unreviewed", self.applied.read_text())

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


class RotateAdminToken(unittest.TestCase):
    """rotate-admin-token.sh in the tests' mode: a fake kubectl keeping both Secrets in files (with resourceVersions),
    a fake Gitea that knows which user and which rights each token has, and a repository of its own whose
    leaked file holds a fixture token (the real leaked token is never used)."""

    OLD, NEW, NEW2, OTHER, NOREPO, READONLY, PLAIN, FORGED, GONE, CI, NOUSER = (c * 40 for c in "123456789ab")

    def setUp(self) -> None:
        import base64
        self.b64 = lambda v: base64.b64encode(v.encode()).decode()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = self.root / "store"
        self.store.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        rw = {"read", "write"}
        self.tokens = {
            self.OLD: ("weitingzhao", True, rw), self.NEW: ("weitingzhao", True, rw), self.NEW2: ("weitingzhao", True, rw),
            self.OTHER: ("someone-else", True, rw), self.NOREPO: ("weitingzhao", True, set()),
            self.READONLY: ("weitingzhao", True, {"read"}), self.PLAIN: ("plain", False, rw), self.CI: ("ci", False, {"read"}),
            self.NOUSER: ("weitingzhao", True, rw | {"no-user-scope"}),
        }
        self.repos = [{"name": "r", "mirror": True}, {"name": "primary-probe", "mirror": False}]
        # the Git side, served as file:// (no basic auth there: this shows every repository is listed)
        self.git_base = self.root / "git"
        for name in ("r", "primary-probe"):
            git(self.root, "init", "-q", "--bare", str(self.git_base / "bifrost" / f"{name}.git"))
        self.seen: list[str] = []
        self.posts: list[str] = []
        self.write_secret("gitea-bootstrap", {"gitea_admin_token": self.OLD})
        self.write_secret("gitea-git-credentials", {"username": "weitingzhao", "password": self.OLD})
        self.kubectl()
        # a repository whose history leaked the fixture token twice
        self.infra = self.root / "infra"
        (self.infra / "k8s" / "cicd" / "gitea").mkdir(parents=True)
        git(self.infra, "init", "-q")
        leaked = self.infra / "k8s" / "cicd" / "gitea" / "secret.yaml"
        leaked.write_text(f'stringData:\n  gitea_admin_token: "{self.OLD}"\n---\nstringData:\n  password: "{self.OLD}"\n')
        git(self.infra, "add", "k8s/cicd/gitea/secret.yaml")
        git(self.infra, "commit", "-q", "-m", "leak")
        self.commit = git(self.infra, "rev-parse", "HEAD")
        self.blob = git(self.infra, "rev-parse", "HEAD:k8s/cicd/gitea/secret.yaml")
        outer = self

        class H(BaseHTTPRequestHandler):
            def _go(self) -> None:
                import base64 as b
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)
                header = self.headers.get("Authorization") or ""
                if header.startswith("Basic "):
                    token = b.b64decode(header[6:]).decode().split(":", 1)[1]
                else:
                    token = header.removeprefix("token ")
                outer.seen.append(token)
                who = outer.tokens.get(token)
                path, _, query = self.path.partition("?")
                code, body = 401, {"message": "token is required"}
                if who:
                    login, admin, rights = who
                    if path == "/api/v1/user":
                        code, body = (403, {"message": "token does not have at least one of required scope(s)"}) if "no-user-scope" in rights else (200, {"login": login, "is_admin": admin})
                    elif self.command == "GET" and path == "/api/v1/orgs/bifrost/repos":
                        page = int(dict(kv.split("=") for kv in query.split("&") if "=" in kv).get("page", "1"))
                        code, body = (200, outer.repos if page == 1 else []) if "read" in rights else (403, {})
                    elif self.command == "GET" and path.startswith("/api/v1/repos/bifrost/") and path.endswith("/branches"):
                        code, body = (200, []) if "read" in rights else (403, {})
                    elif self.command == "POST" and path.endswith("/mirror-sync"):
                        outer.posts.append(path)
                        name = path.split("/")[5]
                        mirror = any(r["name"] == name and r["mirror"] for r in outer.repos)
                        if "write" not in rights:
                            code, body = 403, {"message": "token does not have at least one of required scope(s)"}
                        else:
                            code, body = (200, None) if mirror else (400, {"message": "Repository is not a mirror"})
                    else:
                        code, body = 404, {}
                data = b"" if body is None else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = _go

            def log_message(self, *a) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def write_secret(self, name: str, values: dict, rv: str = "100") -> None:
        doc = {"metadata": {"name": name, "resourceVersion": rv}, "data": {k: self.b64(v) for k, v in values.items()}}
        (self.store / f"{name}.json").write_text(json.dumps(doc))

    def secret(self, name: str, key: str) -> str:
        import base64
        return base64.b64decode(json.loads((self.store / f"{name}.json").read_text())["data"][key]).decode()

    def kubectl(self, marker: bool = True) -> None:
        k = self.bin / "kubectl"
        k.write_text(f"""#!/bin/bash
{"# rotate-admin-token fake kubectl" if marker else "# some other kubectl"}
store="{self.store}"
case "$*" in
  *"get secret "*) name="${{@: -3:1}}"; cat "$store/$name.json" ;;
  *"patch secret "*)
    name="$5"
    [[ "$name" == "${{FAKE_FAIL_PATCH:-}}" ]] && exit 1
    [[ "$name" == "${{FAKE_IGNORE_PATCH:-}}" ]] && {{ cat > /dev/null; exit 0; }}
    python3 -c '
import base64, json, os, sys
path, name = sys.argv[1], sys.argv[2]
secret = json.load(open(path))
if os.environ.get("FAKE_BUMP_BEFORE_PATCH") == name:
    secret["metadata"]["resourceVersion"] = str(int(secret["metadata"]["resourceVersion"]) + 1)
patch = json.load(sys.stdin)
if patch["metadata"]["resourceVersion"] != secret["metadata"]["resourceVersion"]:
    json.dump(secret, open(path, "w"))
    sys.exit("conflict")
for k, v in patch["stringData"].items():
    secret["data"][k] = base64.b64encode(v.encode()).decode()
secret["metadata"]["resourceVersion"] = str(int(secret["metadata"]["resourceVersion"]) + 1)
json.dump(secret, open(path, "w"))
' "$store/$name.json" "$name" ;;
  *) exit 2 ;;
esac
""")
        k.chmod(0o755)

    def run_it(self, *args: str, typed: str = "", bash: tuple[str, ...] = (), extra: dict | None = None,
               test_mode: bool = True) -> subprocess.CompletedProcess:
        env = {**os.environ, "HOME": str(self.root), "PATH": f"{self.bin}:{os.environ['PATH']}",
               "GITEA_API": f"http://127.0.0.1:{self.server.server_address[1]}/api/v1", "GITEA_GIT_BASE": f"file://{self.git_base}",
               **({"ROTATE_TEST_MODE": "1", "ROTATE_TEST_KUBECTL": str(self.bin / "kubectl"), "ROTATE_TEST_INFRA": str(self.infra),
                   "ROTATE_TEST_LEAKED_COMMIT": self.commit, "ROTATE_TEST_LEAKED_BLOB": self.blob} if test_mode else {}),
               **(extra or {})}
        for key in ("GITEA_TOKEN", "FAKE_FAIL_PATCH", "FAKE_IGNORE_PATCH", "FAKE_BUMP_BEFORE_PATCH"):
            if key not in (extra or {}):
                env.pop(key, None)
        return subprocess.run(["bash", *bash, str(HERE / "rotate-admin-token.sh"), *args], env=env, input=typed + "\n",
                              capture_output=True, text=True, timeout=60)

    def no_token_in(self, r: subprocess.CompletedProcess) -> None:
        for token in list(self.tokens) + [self.FORGED, self.GONE]:
            self.assertNotIn(token, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def both(self) -> tuple[str, str]:
        return self.secret("gitea-bootstrap", "gitea_admin_token"), self.secret("gitea-git-credentials", "password")

    def rotated(self, typed: str, **kw) -> subprocess.CompletedProcess:
        r = self.run_it("rotate", typed=typed, **kw)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("==> rotated", r.stdout)
        self.no_token_in(r)
        return r

    def refused(self, typed: str, words: str, **kw) -> subprocess.CompletedProcess:
        before = self.both()
        r = self.run_it("rotate", typed=typed, **kw)
        self.assertEqual(r.returncode, 1, typed + r.stdout + r.stderr)
        self.assertIn(words, r.stdout + r.stderr)
        self.assertEqual(self.both(), before)
        self.no_token_in(r)
        return r

    def test_check_says_what_each_secret_is_good_for(self) -> None:
        r = self.run_it("check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("gitea_admin_token: admin weitingzhao", r.stdout)
        self.assertIn("can read bifrost/r", r.stdout)
        self.assertIn("THE SAME token", r.stdout)
        self.assertEqual(r.stdout.count("STILL THE LEAKED TOKEN"), 2, r.stdout)
        self.no_token_in(r)
        self.rotated(self.NEW)
        r = self.run_it("check")
        self.assertEqual(r.stdout.count("not the leaked token"), 2, r.stdout)

    def test_rotate_puts_the_new_token_in_both_places(self) -> None:
        self.rotated(self.NEW)
        self.assertEqual(self.both(), (self.NEW, self.NEW))
        self.assertEqual(self.secret("gitea-git-credentials", "username"), "weitingzhao")

    def test_another_users_working_clone_is_left_alone(self) -> None:
        self.write_secret("gitea-git-credentials", {"username": "ci", "password": self.CI})
        self.rotated(self.NEW)
        self.assertEqual(self.both(), (self.NEW, self.CI))

    # review 256 A2, 257 A1: the new token is tried for what it is used for, without touching a mirror
    def test_a_token_that_does_not_pass_changes_nothing(self) -> None:
        for typed, words in (("not-a-token", "40 hex"), (self.OLD, "the leaked token"),
                             (self.OTHER, "logs in as admin someone-else, not as the administrator"),
                             ("f" * 40, "logs in as HTTP 401"), (self.PLAIN, "logs in as user plain"),
                             (self.NOREPO, "give it repository and organization"), (self.READONLY, "cannot write bifrost/primary-probe"),
                             (self.NOUSER, "give it user Read and Write")):
            self.refused(typed, words)
        self.assertFalse(any("/r/mirror-sync" in p for p in self.posts), self.posts)

    def test_no_regular_repository_means_nothing_is_written(self) -> None:
        self.repos = [{"name": "r", "mirror": True}]
        self.refused(self.NEW, "no regular repository")
        self.assertEqual(self.posts, [])

    def test_a_mirror_is_never_asked_to_fetch(self) -> None:
        self.rotated(self.NEW)
        self.assertTrue(self.posts)
        self.assertTrue(all(p.endswith("/primary-probe/mirror-sync") for p in self.posts), self.posts)

    # review 256 A1: a half-done rotation is finished by running rotate again, with the same or another token
    def test_a_failed_second_write_is_finished_by_running_again(self) -> None:
        r = self.run_it("rotate", typed=self.NEW, extra={"FAKE_FAIL_PATCH": "gitea-bootstrap"})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("run rotate again", r.stderr)
        self.assertEqual(self.both(), (self.OLD, self.NEW))
        self.rotated(self.NEW)
        self.assertEqual(self.both(), (self.NEW, self.NEW))

    def test_a_failed_second_write_finished_with_another_token(self) -> None:
        self.run_it("rotate", typed=self.NEW, extra={"FAKE_FAIL_PATCH": "gitea-bootstrap"})
        self.rotated(self.NEW2)
        admin, clone = self.both()
        self.assertEqual(admin, self.NEW2)
        self.assertNotEqual(clone, self.OLD)

    def test_only_the_admin_secret_changed_before_is_finished(self) -> None:
        self.write_secret("gitea-bootstrap", {"gitea_admin_token": self.NEW})
        self.rotated(self.NEW)
        self.assertEqual(self.both(), (self.NEW, self.NEW))

    # review 256 B3, 257 B2: a clone password that does not work, as stored, is the administrator's to rewrite
    def test_a_clone_password_with_a_newline_is_rewritten_clean(self) -> None:
        self.write_secret("gitea-git-credentials", {"username": "weitingzhao", "password": self.NEW + "\n"})
        self.rotated(self.NEW)
        self.assertEqual(self.both(), (self.NEW, self.NEW))

    def test_a_missing_clone_password_is_written(self) -> None:
        self.write_secret("gitea-git-credentials", {"username": "weitingzhao"})
        self.rotated(self.NEW)
        self.assertEqual(self.both(), (self.NEW, self.NEW))

    def test_another_users_broken_clone_stops_it(self) -> None:
        self.write_secret("gitea-git-credentials", {"username": "ci", "password": self.GONE})
        self.refused(self.NEW, "fix them by hand")

    # review 257 B3: the admin token of the start counts as old too
    def test_a_clone_left_on_the_start_token_is_not_done(self) -> None:
        self.write_secret("gitea-bootstrap", {"gitea_admin_token": self.NEW})
        self.write_secret("gitea-git-credentials", {"username": "weitingzhao", "password": self.NEW})
        r = self.run_it("rotate", typed=self.NEW2, extra={"FAKE_IGNORE_PATCH": "gitea-git-credentials"})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("NOT DONE: the clone password is still an old token", r.stdout)

    # review 257 B4: a broken or revoked admin token can be replaced
    def test_an_unclean_admin_token_can_be_replaced(self) -> None:
        self.write_secret("gitea-bootstrap", {"gitea_admin_token": self.OLD + "\n"})
        self.rotated(self.NEW)
        self.assertEqual(self.both(), (self.NEW, self.NEW))

    def test_a_revoked_admin_token_can_be_replaced(self) -> None:
        self.write_secret("gitea-bootstrap", {"gitea_admin_token": self.GONE})
        self.write_secret("gitea-git-credentials", {"username": "weitingzhao", "password": self.GONE})
        self.rotated(self.NEW)
        self.assertEqual(self.both(), (self.NEW, self.NEW))

    def test_an_admin_token_of_another_user_is_not_replaced_unseen(self) -> None:
        self.write_secret("gitea-bootstrap", {"gitea_admin_token": self.OTHER})
        self.refused(self.NEW, "look before replacing it")

    # review 256 B4: a value that is not a clean token is reported, not sent
    def test_an_unclean_value_is_not_sent(self) -> None:
        self.write_secret("gitea-git-credentials", {"username": "weitingzhao", "password": self.OLD + "\nx"})
        self.seen.clear()
        r = self.run_it("check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("CANNOT read a repository as Tekton does", r.stdout)
        self.assertNotIn(self.OLD + "\nx", self.seen)
        self.no_token_in(r)

    # review 256 B5: a Secret changed since it was read is not overwritten
    def test_a_secret_changed_meanwhile_is_not_overwritten(self) -> None:
        r = self.run_it("rotate", typed=self.NEW, extra={"FAKE_BUMP_BEFORE_PATCH": "gitea-git-credentials"})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("changed since it was read", r.stderr)
        self.assertEqual(self.both(), (self.OLD, self.OLD))

    # review 256 B6: a replacement object for the leaked file is not what revoked checks
    def test_revoked_reads_the_pinned_leaked_file(self) -> None:
        text = f'stringData:\n  gitea_admin_token: "{self.FORGED}"\n'
        forged = subprocess.run(["git", "-C", str(self.infra), "hash-object", "-w", "--stdin"], input=text,
                                capture_output=True, text=True, check=True).stdout.strip()
        git(self.infra, "replace", self.blob, forged)
        self.rotated(self.NEW)
        del self.tokens[self.OLD]  # the Owner revoked it
        self.seen.clear()
        r = self.run_it("revoked")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(self.OLD, self.seen)
        self.assertNotIn(self.FORGED, self.seen)
        self.assertIn("(refused, as it should be)", r.stdout)

    def test_revoked_fails_while_the_leaked_token_is_accepted(self) -> None:
        self.rotated(self.NEW)
        r = self.run_it("revoked")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("STILL ACCEPTED", r.stdout)
        self.no_token_in(r)

    # review 256 B7, 257 B5: the tests' mode cannot reach a real kubectl; outside it, no address from the environment
    def test_the_tests_mode_needs_the_fake_kubectl(self) -> None:
        self.kubectl(marker=False)
        self.seen.clear()
        r = self.run_it("check")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("the tests' fake kubectl", r.stderr)
        self.assertEqual(self.seen, [])

    def test_outside_the_tests_mode_gitea_is_only_reached_through_the_port_forward(self) -> None:
        self.seen.clear()
        r = self.run_it("check", test_mode=False)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("port-forward", r.stderr)
        self.assertEqual(self.seen, [])

    # review 258 B4: an empty admin value can be replaced too
    def test_an_empty_admin_value_can_be_replaced(self) -> None:
        self.write_secret("gitea-bootstrap", {"gitea_admin_token": ""})
        self.rotated(self.NEW)
        self.assertEqual(self.both(), (self.NEW, self.NEW))

    # review 258 B2, B8: every repository listed over Git HTTP with the clone credentials
    def test_a_repository_the_clone_cannot_list_over_git_is_not_done(self) -> None:
        import shutil
        shutil.rmtree(self.git_base / "bifrost" / "primary-probe.git")
        r = self.run_it("rotate", typed=self.NEW)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("cannot list over Git HTTP: primary-probe", r.stdout)
        self.no_token_in(r)

    def test_done_says_every_repository_was_listed(self) -> None:
        r = self.rotated(self.NEW)
        self.assertIn("lists all 2 repositories of bifrost over Git HTTP", r.stdout)

    def test_xtrace_does_not_print_a_token(self) -> None:
        self.rotated(self.NEW, bash=("-x",))


class CheckStep1(unittest.TestCase):
    """check-step1.sh against a fake Gitea answering the user, team and repository reads."""

    def setUp(self) -> None:
        none = {u: "none" for u in ("repo.issues", "repo.pulls", "repo.releases", "repo.wiki", "repo.projects", "repo.packages", "repo.actions")}
        self.users = {"bifrost-mbp": {"login": "bifrost-mbp", "is_admin": False},
                      "agentd-agent-06": {"login": "agentd-agent-06"}, "agentd-agent-06-stg": {"login": "agentd-agent-06-stg"}}
        self.teams = [
            {"id": 1, "name": "Owners", "permission": "owner", "includes_all_repositories": True, "units_map": {}},
            {"id": 2, "name": "maintainers", "permission": "write", "includes_all_repositories": True,
             "units_map": {"repo.code": "write", **{u: "read" for u in none}}},
            {"id": 3, "name": "agentd-write", "permission": "write", "includes_all_repositories": True,
             "units_map": {"repo.code": "write", **none, "repo.ext_issues": "read", "repo.ext_wiki": "read"}},
        ]
        self.members = {2: ["weitingzhao", "bifrost-mbp"], 3: ["agentd-agent-06", "agentd-agent-06-stg"]}
        self.probe = {"name": "primary-probe", "mirror": False, "private": True}
        self.template = None
        self.rules = {"primary-probe": [], "repo-template": []}
        self.tags = {}  # Gitea 1.21: no tag rule API, so 404 unless a test sets a list
        el = "http://el-bifrost-ci.cicd.svc.cluster.local:8080"
        self.hooks = [{"id": 1, "type": "gitea", "active": True, "events": ["push"],
                       "config": {"url": el, "content_type": "json"}}]
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                path = self.path.split("?")[0].removeprefix("/api/v1")
                code, body = 404, {"message": "not found"}
                if path.startswith("/users/") and path[7:] in outer.users:
                    code, body = 200, outer.users[path[7:]]
                elif path == "/orgs/bifrost/teams":
                    code, body = 200, outer.teams
                elif path.startswith("/teams/") and path.endswith("/members"):
                    tid = int(path.split("/")[2])
                    code, body = 200, [{"login": m} for m in outer.members.get(tid, [])]
                elif path == "/repos/bifrost/primary-probe" and outer.probe:
                    code, body = 200, outer.probe
                elif path == "/repos/bifrost/primary-probe/branches/main" and outer.probe and outer.probe.get("has_main", True):
                    code, body = 200, {"name": "main"}
                elif path == "/repos/bifrost/primary-probe/branches" and outer.probe:
                    code, body = 200, ([{"name": "main"}] if outer.probe.get("has_main", True) else [])
                elif path.endswith("/branch_protections") and path.split("/")[3] in outer.rules:
                    code, body = 200, [{"rule_name": n} for n in outer.rules[path.split("/")[3]]]
                elif path.endswith("/tag_protections") and path.split("/")[3] in outer.tags:
                    code, body = 200, outer.tags[path.split("/")[3]]
                elif path == "/repos/bifrost/repo-template/hooks" and outer.template:
                    code, body = 200, outer.hooks
                elif path == "/repos/bifrost/repo-template" and outer.template:
                    code, body = 200, outer.template
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def run_it(self) -> subprocess.CompletedProcess:
        env = {**os.environ, "GITEA_TOKEN": "fixture-admin-token", "GITEA_GIT_BASE": "http://127.0.0.1:9",
               "GITEA_API": f"http://127.0.0.1:{self.server.server_address[1]}/api/v1"}
        return subprocess.run(["bash", str(HERE / "check-step1.sh")], env=env, capture_output=True, text=True, timeout=60)

    def test_all_as_expected(self) -> None:
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FAIL", r.stdout)
        self.assertIn("none yet (section 1 part 2)", r.stdout)
        self.assertNotIn("fixture-admin-token", r.stdout + r.stderr)

    def test_each_wrong_setting_is_a_fail(self) -> None:
        cases = (
            ("bifrost-mbp is an administrator", lambda: self.users["bifrost-mbp"].update(is_admin=True), "IS an administrator"),
            ("agentd-write may open pull requests", lambda: self.teams[2]["units_map"].update({"repo.pulls": "write"}), "repo.pulls is write, not none"),
            ("maintainers only some repositories", lambda: self.teams[1].update(includes_all_repositories=False), "not all repositories"),
            ("maintainers is an admin team", lambda: self.teams[1].update(permission="admin"), "permission is admin"),
            ("bifrost-mbp not in maintainers", lambda: self.members.update({2: ["weitingzhao"]}), "has: weitingzhao"),
            ("agentd-write missing", lambda: self.teams.pop(2), "team bifrost/agentd-write — missing"),
            ("probe is a mirror", lambda: self.probe.update(mirror=True), "mirror True"),
            ("probe is empty", lambda: self.probe.update(has_main=False, default_branch="main"), "branches: none (empty repository); default branch main"),
        )
        for name, change, words in cases:
            self.setUp()
            try:
                change()
                r = self.run_it()
                self.assertEqual(r.returncode, 1, name + r.stdout + r.stderr)
                self.assertIn(words, r.stdout, name)
            finally:
                self.tearDown()
        self.setUp()

    def part_two_done(self) -> None:
        self.template = {"name": "repo-template", "template": True, "mirror": False}
        self.rules = {"primary-probe": ["main", "agent/**"], "repo-template": ["agent/**", "main"]}

    def test_part_two_as_expected(self) -> None:
        self.part_two_done()
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FAIL", r.stdout)
        self.assertIn("ok    bifrost/repo-template branch rules: agent/**, main", r.stdout)
        self.assertIn("ok    bifrost/repo-template webhook to http://el-bifrost-ci.cicd.svc.cluster.local:8080", r.stdout)
        self.assertIn("info  primary-probe tag rules: not readable through this Gitea's API", r.stdout)

    def test_tag_rules_are_checked_where_readable(self) -> None:
        self.part_two_done()
        good = [{"name_pattern": "*", "whitelist_usernames": ["weitingzhao"], "whitelist_teams": ["maintainers"]}]
        self.tags = {"primary-probe": good, "repo-template": good}
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok    bifrost/repo-template tag rule *: user weitingzhao and team maintainers", r.stdout)

    def test_each_wrong_part_two_setting_is_a_fail(self) -> None:
        cases = (
            ("template lacks agent/**", lambda: self.rules.update({"repo-template": ["main"]}), "repo-template branch rules: agent/**, main — has: main"),
            ("probe has an extra rule", lambda: self.rules.update({"primary-probe": ["main", "agent/**", "*"]}), "has: *, agent/**, main"),
            ("no webhook", lambda: self.hooks.clear(), "has: no webhooks"),
            ("webhook to another address", lambda: self.hooks[0]["config"].update(url="http://el-bifrost-ci.cicd:8080"), "has: http://el-bifrost-ci.cicd:8080"),
            ("webhook sends form data", lambda: self.hooks[0]["config"].update(content_type="form"), "content type form, not json"),
            ("webhook without push", lambda: self.hooks[0].update(events=["create"]), "no push event (has: create)"),
            ("webhook inactive", lambda: self.hooks[0].update(active=False), "not active"),
            ("webhook of another type", lambda: self.hooks[0].update(type="slack"), "type slack, not gitea"),
            ("tag rule lets everyone", lambda: self.tags.update({"primary-probe": [{"name_pattern": "*"}]}), "users none; teams none"),
            ("no * tag rule", lambda: self.tags.update({"repo-template": []}), "tag rule *: user weitingzhao and team maintainers — no * rule"),
        )
        for name, change, words in cases:
            self.setUp()
            try:
                self.part_two_done()
                change()
                r = self.run_it()
                self.assertEqual(r.returncode, 1, name + r.stdout + r.stderr)
                self.assertIn(words, r.stdout, name)
            finally:
                self.tearDown()
        self.setUp()


PAT_FIXTURE = "github_pat_fixture0123456789abcdefFIXTURE"

FAKE_KUBECTL = r'''#!/usr/bin/env bash
# fake kubectl for put-github-sync-token tests
state="$FAKE_STATE"
echo "$*" >> "$state/calls"
args=" $* "
case "$args" in
  *" get secret github-sync -o name "*) [[ -f "$state/secret" ]] && echo secret/github-sync && exit 0; exit 1 ;;
  *" get serviceaccount default "*) [[ -f "$state/unreachable" ]] && exit 1; echo serviceaccount/default ;;
  *" create secret generic github-sync --from-file=token=/dev/stdin "*) cat > "$state/secret"; echo secret/github-sync created ;;
  *" get secret github-sync -o json "*) python3 -c 'import base64,json,sys; print(json.dumps({"data":{"token":base64.b64encode(open(sys.argv[1],"rb").read()).decode()}}))' "$state/secret" ;;
  *) echo "unexpected kubectl $*" >&2; exit 9 ;;
esac
'''


class PutGithubSyncToken(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = root / "state"
        self.state.mkdir()
        bindir = root / "bin"
        bindir.mkdir()
        (bindir / "kubectl").write_text(FAKE_KUBECTL)
        (bindir / "kubectl").chmod(0o755)
        self.kubeconfig = root / "admin.yaml"
        self.kubeconfig.write_text("fixture\n")
        self.path = f"{bindir}:{os.environ['PATH']}"
        self.login = "weitingzhao"
        self.no_push: set[str] = set()
        self.seen_auth: list[str] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                auth = self.headers.get("Authorization", "")
                outer.seen_auth.append(auth)
                code, body, extra = 404, b"{}", {}
                if self.path == "/api/user":
                    if auth == "Bearer " + PAT_FIXTURE:
                        code, body = 200, json.dumps({"login": outer.login}).encode()
                        extra = {"github-authentication-token-expiration": "2027-10-17 21:00:00 -0400"}
                    else:
                        code = 401
                elif self.path.endswith(".git/info/refs?service=git-receive-pack"):
                    repo = self.path.split("/")[2].removesuffix(".git")
                    want = "Basic " + base64.b64encode(f"x-access-token:{PAT_FIXTURE}".encode()).decode()
                    code = 401 if auth != want else (403 if repo in outer.no_push else 200)
                    body = b"001f# service=git-receive-pack\n0000"
                self.send_response(code)
                for k, v in extra.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def run_it(self, typed: str | None = PAT_FIXTURE, tty: bool = True) -> subprocess.CompletedProcess:
        port = self.server.server_address[1]
        env = {**os.environ, "PATH": self.path, "FAKE_STATE": str(self.state), "PUT_TOKEN_KUBECONFIG": str(self.kubeconfig),
               "GITHUB_API": f"http://127.0.0.1:{port}/api", "GITHUB_GIT": f"http://127.0.0.1:{port}/weitingzhao",
               "REPOS": "bifrost-ui bifrost-platform", "NO_PROXY": "*", "no_proxy": "*"}
        cmd = ["bash", str(HERE / "put-github-sync-token.sh")]
        # never the real kubectl or the Owner's kubeconfig: a slip here would create the Secret for real
        self.assertEqual(shutil.which("kubectl", path=env["PATH"]), str(Path(self.path.split(":")[0]) / "kubectl"))
        self.assertIn("fixture", (self.kubeconfig).read_text())
        if not tty:
            return subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        r, self.echoed = run_on_pty(cmd, env, typed)
        return r

    def created(self) -> bool:
        return (self.state / "secret").exists()

    def test_creates_the_secret_after_github_says_yes(self) -> None:
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.state / "secret").read_text(), PAT_FIXTURE)
        self.assertIn("ok    token of weitingzhao; expires 2027-10-17 21:00:00 -0400", r.stdout)
        self.assertIn("ok    can push to bifrost-ui", r.stdout)
        self.assertIn("Secret cicd/github-sync created (key: token)", r.stdout)
        self.assertNotIn(PAT_FIXTURE, r.stdout + r.stderr)
        self.assertNotIn("fixture0123456789", self.echoed)  # read -s: not echoed to the terminal
        self.assertNotIn(PAT_FIXTURE, (self.state / "calls").read_text())  # never on kubectl's command line

    def test_refuses_without_a_terminal(self) -> None:
        r = self.run_it(tty=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a terminal", r.stderr)
        self.assertFalse(self.created())

    def test_nothing_written_when_anything_is_wrong(self) -> None:
        cases = (
            ("secret already there", lambda: (self.state / "secret").write_text("old"), None, "already exists"),
            ("cluster unreachable", lambda: (self.state / "unreachable").write_text(""), None, "cannot reach the cluster"),
            ("empty input", lambda: None, "", "empty input"),
            ("classic token", lambda: None, "ghp_abcdef0123456789", "not a fine-grained token"),
            ("quote in the token", lambda: None, 'github_pat_a"b', "not a fine-grained token"),
            ("token GitHub refuses", lambda: None, "github_pat_wrongwrongwrong", "GET /user → HTTP 401"),
            ("another account's token", lambda: setattr(self, "login", "someone-else"), None, "belongs to 'someone-else'"),
            ("cannot push to one repository", lambda: self.no_push.add("bifrost-platform"), None, "cannot push to every repository"),
        )
        for name, change, typed, words in cases:
            with self.subTest(name):
                self.tearDown()
                self.setUp()
                change()
                before = (self.state / "secret").read_text() if self.created() else None
                r = self.run_it(typed=PAT_FIXTURE if typed is None else typed)
                self.assertEqual(r.returncode, 1, name + r.stdout + r.stderr)
                self.assertIn(words, r.stdout + r.stderr, name)
                self.assertIn("Nothing was written.", r.stderr, name)
                after = (self.state / "secret").read_text() if self.created() else None
                self.assertEqual(before, after, name)
                self.assertNotIn(PAT_FIXTURE, r.stdout + r.stderr, name)

    def test_one_failing_repository_is_named(self) -> None:
        self.no_push.add("bifrost-platform")
        r = self.run_it()
        self.assertIn("ok    can push to bifrost-ui", r.stdout)
        self.assertIn("FAIL  bifrost-platform: push handshake → HTTP 403", r.stdout)



GITEA_TOKEN_FIXTURE = "0123456789abcdef0123456789abcdef01234567"


def isolated_git_env(root: Path) -> dict:
    """A git that reads only root/gitconfig: no system config (Apple's osxkeychain helper lives
    there), no ~/.gitconfig, no XDG file. Tests of credential and global-config scripts use it so
    that nothing reaches the Owner's keychain or ~/.gitconfig."""
    home = root / "home"
    home.mkdir(exist_ok=True)
    return {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
            "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"), "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(root / "gitconfig"), "NO_PROXY": "*", "no_proxy": "*"}


class StoreMbpToken(unittest.TestCase):
    """store-mbp-token.sh against a fake Gitea, with git's store helper in a temporary file."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = isolated_git_env(self.root)
        self.store = self.root / "credentials"
        (self.root / "gitconfig").write_text(f'[credential]\n\thelper = "store --file {self.store}"\n')
        self.login = "bifrost-mbp"
        self.push_code = 200
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                auth = self.headers.get("Authorization", "")
                code, body = 404, b"{}"
                if self.path == "/api/v1/user":
                    code, body = (200, json.dumps({"login": outer.login}).encode()) if auth == "token " + GITEA_TOKEN_FIXTURE else (401, b"{}")
                elif self.path == "/bifrost/primary-probe.git/info/refs?service=git-receive-pack":
                    want = "Basic " + base64.b64encode(f"bifrost-mbp:{GITEA_TOKEN_FIXTURE}".encode()).decode()
                    code, body = (outer.push_code, b"0000") if auth == want else (401, b"")
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.host = f"127.0.0.1:{self.server.server_address[1]}"
        self.env["GITEA_PUBLIC_BASE"] = f"http://{self.host}/bifrost"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def run_it(self, typed: str | None = GITEA_TOKEN_FIXTURE, tty: bool = True) -> subprocess.CompletedProcess:
        # the guard: under this environment git knows only the helpers this test wrote
        helpers = subprocess.run(["git", "config", "--get-all", "credential.helper"], env=self.env, capture_output=True, text=True).stdout
        self.assertNotIn("osxkeychain", helpers)
        cmd = ["bash", str(HERE / "store-mbp-token.sh")]
        if not tty:
            return subprocess.run(cmd, env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        r, self.echoed = run_on_pty(cmd, self.env, typed)
        return r

    def stored(self) -> str:
        return self.store.read_text() if self.store.exists() else ""

    def test_stores_after_gitea_says_yes(self) -> None:
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"http://bifrost-mbp:{GITEA_TOKEN_FIXTURE}@127.0.0.1%3a{self.server.server_address[1]}", self.stored())  # the store helper encodes the port colon
        self.assertIn("ok    token of bifrost-mbp", r.stdout)
        self.assertIn(f"git now pushes to http://{self.host} as bifrost-mbp", r.stdout)
        self.assertNotIn(GITEA_TOKEN_FIXTURE, r.stdout + r.stderr + self.echoed)

    def test_nothing_stored_when_anything_is_wrong(self) -> None:
        cases = (
            ("no helper", lambda: (self.root / "gitconfig").write_text(""), None, "no credential helper"),
            ("empty input", lambda: None, "", "empty input"),
            ("not a Gitea token", lambda: None, "github_pat_abc", "40 hex characters"),
            ("token Gitea refuses", lambda: None, "f" * 40, "GET /api/v1/user → HTTP 401"),
            ("another account's token", lambda: setattr(self, "login", "weitingzhao"), None, "belongs to 'weitingzhao'"),
            ("token without write", lambda: setattr(self, "push_code", 403), None, "push handshake on primary-probe → HTTP 403"),
        )
        for name, change, typed, words in cases:
            with self.subTest(name):
                self.tearDown()
                self.setUp()
                change()
                r = self.run_it(typed=GITEA_TOKEN_FIXTURE if typed is None else typed)
                self.assertEqual(r.returncode, 1, name + r.stdout + r.stderr)
                self.assertIn(words, r.stderr, name)
                self.assertIn("Nothing was stored.", r.stderr, name)
                self.assertEqual(self.stored(), "", name)
                self.assertNotIn(GITEA_TOKEN_FIXTURE, r.stdout + r.stderr, name)

    def test_refuses_without_a_terminal(self) -> None:
        r = self.run_it(tty=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a terminal", r.stderr)
        self.assertEqual(self.stored(), "")

    def test_another_entry_answering_first_is_named(self) -> None:
        helper = self.root / "first-helper.sh"
        helper.write_text("#!/bin/sh\n[ \"$1\" = get ] && printf 'username=weitingzhao\\npassword=other\\n'\nexit 0\n")
        helper.chmod(0o755)
        (self.root / "gitconfig").write_text(f'[credential]\n\thelper = "!{helper}"\n\thelper = "store --file {self.store}"\n')
        r = self.run_it()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("git answers user 'weitingzhao'", r.stderr)
        self.assertIn("remove it in Keychain Access (search 127.0.0.1)", r.stderr)
        self.assertNotIn(GITEA_TOKEN_FIXTURE, r.stdout + r.stderr)


class GlobalInsteadOf(unittest.TestCase):
    """global-insteadof.sh with GIT_CONFIG_GLOBAL in a temporary directory."""

    GITEA = "http://192.168.10.73:30300/bifrost"

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = isolated_git_env(self.root)
        self.config = self.root / "gitconfig"
        self.config.write_text("[user]\n\tname = t\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_it(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(HERE / "global-insteadof.sh"), *args], env=self.env, capture_output=True, text=True, timeout=60)

    def url(self, address: str) -> str:
        return subprocess.run(["git", "ls-remote", "--get-url", address], env=self.env, capture_output=True, text=True, check=True).stdout.strip()

    def test_add_then_remove(self) -> None:
        r = self.run_it("add", "bifrost-platform", "bifrost-ui")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for repo in ("bifrost-platform", "bifrost-ui"):
            self.assertEqual(self.url(f"git@github.com:weitingzhao/{repo}.git"), f"{self.GITEA}/{repo}.git")
            self.assertEqual(self.url(f"https://github.com/weitingzhao/{repo}.git"), f"{self.GITEA}/{repo}.git")
        # the prefix: bifrost-platform's rule leaves bifrost-platform-plugin alone
        self.assertEqual(self.url("git@github.com:weitingzhao/bifrost-platform-plugin.git"), "git@github.com:weitingzhao/bifrost-platform-plugin.git")
        self.assertEqual((self.root / "gitconfig.before-gitea-primary").read_text(), "[user]\n\tname = t\n")
        once = self.config.read_text()
        self.assertEqual(self.run_it("add", "bifrost-platform").returncode, 0)
        self.assertEqual(self.config.read_text(), once)  # again: nothing added twice
        r = self.run_it("remove", "bifrost-platform", "bifrost-ui")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.url("git@github.com:weitingzhao/bifrost-ui.git"), "git@github.com:weitingzhao/bifrost-ui.git")
        self.assertNotIn("insteadOf", self.config.read_text())

    def test_another_rule_stops_it_before_any_change(self) -> None:
        self.config.write_text('[url "ssh://elsewhere/"]\n\tinsteadOf = git@github.com:weitingzhao/\n')
        before = self.config.read_text()
        r = self.run_it("add", "bifrost-ui", "bifrost-platform")
        self.assertEqual(r.returncode, 1)
        self.assertIn("already resolves to ssh://elsewhere/bifrost-ui.git", r.stderr)
        self.assertEqual(self.config.read_text(), before)
        self.assertFalse((self.root / "gitconfig.before-gitea-primary").exists())

    def test_bad_arguments(self) -> None:
        for args, words in ((("add",), "name at least one repository"), (("move", "x"), "usage"),
                            (("add", "../x"), "not a repository name"), (("add", "a b"), "not a repository name")):
            r = self.run_it(*args)
            self.assertEqual(r.returncode, 1, args)
            self.assertIn(words, r.stderr, args)
        self.assertEqual(self.config.read_text(), "[user]\n\tname = t\n")

if __name__ == "__main__":
    unittest.main()
