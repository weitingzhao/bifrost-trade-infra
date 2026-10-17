"""probe-gitea-protection.sh against a local stand-in for Gitea.

The git side is a bare repository served as file:// whose pre-receive hook
refuses with Gitea 1.21's protection messages (main and tags protected;
agent/** may be created but not forced or deleted); the API side is a small
local HTTP server for the repository and pull-request calls. No network, no
cluster.

    python3 -m unittest scripts/agent-host/test_probe_gitea_protection.py
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE / "probe-gitea-protection.sh"
TOKEN = "fixture-probe-token-0123456789"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_NOSYSTEM": "1"}

# Gitea 1.21's own words, as its pre-receive hook prints them
HOOK = r"""#!/bin/bash
mode="$(cat "$GIT_DIR/probe-mode" 2>/dev/null || true)"
zero=0000000000000000000000000000000000000000
while read -r old new ref; do
  case "$ref" in
    refs/heads/main)
      [[ "$mode" == open-main ]] && continue
      [[ "$mode" == odd-refusal ]] && { echo "Gitea: Internal Server Connecting Error"; exit 1; }
      echo "Gitea: Not allowed to push to protected branch main"; exit 1 ;;
    refs/tags/*) echo "Gitea: Tag ${ref#refs/tags/} is protected"; exit 1 ;;
    refs/heads/agent/*)
      if [[ "$new" == "$zero" ]]; then echo "Gitea: branch ${ref#refs/heads/} is protected from deletion"; exit 1; fi
      if [[ "$old" != "$zero" ]] && ! git merge-base --is-ancestor "$old" "$new"; then
        echo "Gitea: branch ${ref#refs/heads/} is protected from force push"; exit 1
      fi ;;
  esac
done
"""


class FakeApi:
    def __init__(self, merge_code: int = 405) -> None:
        self.calls: list[tuple[str, str, str]] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def _go(self) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)
                outer.calls.append((self.command, self.path, self.headers.get("Authorization", "")))
                routes = {
                    ("GET", "/api/v1/repos/bifrost/primary-probe"): (200, {"name": "primary-probe", "mirror": False}),
                    ("POST", "/api/v1/repos/bifrost/primary-probe/pulls"): (201, {"number": 7}),
                    ("POST", "/api/v1/repos/bifrost/primary-probe/pulls/7/merge"): (merge_code, {"message": "not allowed"}),
                    ("PATCH", "/api/v1/repos/bifrost/primary-probe/pulls/7"): (201, {"number": 7, "state": "closed"}),
                }
                code, body = routes.get((self.command, self.path), (404, {}))
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PATCH = _go

            def log_message(self, *a) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/api/v1"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class Probe(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.gitea = self.root / "gitea"
        bare = self.gitea / "bifrost" / "primary-probe.git"
        bare.parent.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "--bare", "--initial-branch=main", str(bare)], check=True)
        seed = self.root / "seed"
        env = {**os.environ, **GIT_ENV, "HOME": str(self.root)}
        subprocess.run(["git", "init", "-q", "--initial-branch=main", str(seed)], check=True, env=env)
        subprocess.run(["git", "-C", str(seed), "commit", "-q", "--allow-empty", "-m", "init"], check=True, env=env)
        subprocess.run(["git", "-C", str(seed), "push", "-q", str(bare), "main"], check=True, env=env)
        hook = bare / "hooks" / "pre-receive"
        hook.write_text(HOOK)
        hook.chmod(0o755)
        self.bare = bare
        self.token_file = self.root / "token"
        self.token_file.write_text(TOKEN + "\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_probe(self, api: FakeApi, mode: str = "", bash: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
        (self.bare / "probe-mode").write_text(mode)
        env = {**os.environ, "HOME": str(self.root), "PROBE_GITEA": f"file://{self.gitea}", "PROBE_API_BASE": api.base,
               "PROBE_TOKEN_FILE": str(self.token_file)}
        return subprocess.run(["bash", *bash, str(PROBE)], env=env, capture_output=True, text=True, timeout=120)

    def test_every_rule_holds(self) -> None:
        api = FakeApi()
        try:
            r = self.run_probe(api)
        finally:
            api.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.count("\nok "), 8, r.stdout)
        self.assertNotIn("FAIL", r.stdout)
        self.assertIn("all as expected", r.stdout)
        self.assertTrue(all(auth == "token " + TOKEN for _, _, auth in api.calls))
        self.assertNotIn(TOKEN, r.stdout + r.stderr)

    def test_a_main_that_takes_the_push_fails_the_probe(self) -> None:
        api = FakeApi()
        try:
            r = self.run_probe(api, mode="open-main")
        finally:
            api.close()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("FAIL  push to main — Gitea accepted it", r.stdout)
        self.assertIn("FAIL  main unchanged", r.stdout)

    def test_a_refusal_that_is_not_a_rule_fails_the_probe(self) -> None:
        api = FakeApi()
        try:
            r = self.run_probe(api, mode="odd-refusal")
        finally:
            api.close()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("refused, but not by a rule", r.stdout)

    def test_a_merged_pull_request_fails_the_probe(self) -> None:
        api = FakeApi(merge_code=200)
        try:
            r = self.run_probe(api)
        finally:
            api.close()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("Gitea merged it", r.stdout)

    def test_xtrace_does_not_print_the_token(self) -> None:
        api = FakeApi()
        try:
            r = self.run_probe(api, bash=("-x",))
        finally:
            api.close()
        self.assertNotIn(TOKEN, r.stdout + r.stderr)

    def test_an_unreadable_gitea_stops_it_without_the_token(self) -> None:
        env = {**os.environ, "HOME": str(self.root), "PROBE_GITEA": "http://127.0.0.1:9",
               "PROBE_TOKEN_FILE": str(self.token_file)}
        r = subprocess.run(["bash", str(PROBE)], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("cannot read bifrost/primary-probe", r.stderr)
        self.assertNotIn(TOKEN, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
