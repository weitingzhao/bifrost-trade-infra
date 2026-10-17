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
      [[ "$mode" == protected-word ]] && { echo "Gitea: Internal Server Connecting Error: protected-branch service unavailable"; exit 1; }
      [[ "$mode" == near-words ]] && { echo "Gitea: Not allowed to push to protected branch main-other"; exit 1; }
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
    """The repository and pull-request calls, with answers as large as Gitea's (a padding field)."""

    def __init__(self, merge: tuple[int, str] = (405, "User not allowed to merge PR"), close_code: int = 201,
                 mergeable: bool = True, create_code: int = 201, opened_anyway: bool = True) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.state = "open"
        self.opened = False
        outer = self
        pad = {"padding": "x" * 5000}

        class H(BaseHTTPRequestHandler):
            def _go(self) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)
                outer.calls.append((self.command, self.path, self.headers.get("Authorization", "")))
                key, pr = (self.command, self.path), "/api/v1/repos/bifrost/primary-probe/pulls/7"
                if key == ("GET", "/api/v1/repos/bifrost/primary-probe"):
                    code, body = 200, {"name": "primary-probe", "mirror": False, **pad}
                elif key == ("POST", "/api/v1/repos/bifrost/primary-probe/pulls"):
                    # create_code other than 201: the answer is lost; the pull request may exist all the same
                    outer.opened = create_code == 201 or opened_anyway
                    code, body = (201, {"number": 7, "state": "open", **pad}) if create_code == 201 else (create_code, {"message": "gateway"})
                elif self.command == "GET" and self.path.startswith("/api/v1/repos/bifrost/primary-probe/pulls/main/agent/_probe/"):
                    code, body = (200, {"number": 7, "state": outer.state, **pad}) if outer.opened else (404, {})
                elif key == ("GET", pr):
                    code, body = 200, {"number": 7, "state": outer.state, "mergeable": mergeable, **pad}
                elif key == ("POST", pr + "/merge"):
                    code, body = merge[0], {"message": merge[1], "url": "https://example.invalid/api/swagger"}
                elif key == ("PATCH", pr):
                    if close_code in (200, 201):
                        outer.state = "closed"
                    code, body = close_code, {"number": 7, "state": outer.state, **pad}
                else:
                    code, body = 404, {}
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
               "PROBE_TOKEN_FILE": str(self.token_file), "PROBE_MERGEABLE_WAIT": "2"}
        return subprocess.run(["bash", *bash, str(PROBE)], env=env, capture_output=True, text=True, timeout=120)

    def test_every_rule_holds(self) -> None:
        api = FakeApi()
        try:
            r = self.run_probe(api)
        finally:
            api.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.count("\nok "), 9, r.stdout)
        self.assertEqual(api.state, "closed")
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
        self.assertIn("refused, but not in the words of that rule", r.stdout)

    def test_a_merged_pull_request_fails_the_probe(self) -> None:
        api = FakeApi(merge=(200, ""))
        try:
            r = self.run_probe(api)
        finally:
            api.close()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("Gitea merged it", r.stdout)

    # review 254: a refusal or a merge answer that is not the rule's fails the probe; the pull request is closed
    def assert_fails(self, api: FakeApi, words: str, mode: str = "") -> subprocess.CompletedProcess:
        try:
            r = self.run_probe(api, mode=mode)
        finally:
            api.close()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(words, r.stdout + r.stderr)
        self.assertNotIn("all as expected", r.stdout)
        return r

    def test_a_refusal_that_only_mentions_protected_fails_the_probe(self) -> None:
        self.assert_fails(FakeApi(), "not in the words of that rule", mode="protected-word")

    def test_a_merge_refused_for_another_reason_fails_the_probe(self) -> None:
        api = FakeApi(merge=(405, "Please try again later"))
        self.assert_fails(api, "HTTP 405 for another reason")
        self.assertEqual(api.state, "closed")

    def test_a_merge_forbidden_fails_the_probe(self) -> None:
        self.assert_fails(FakeApi(merge=(403, "token does not have at least one of required scope(s)")), "not recognised: HTTP 403")

    def test_a_pull_request_never_mergeable_is_not_a_pass(self) -> None:
        api = FakeApi(mergeable=False)
        self.assert_fails(api, "never said it can be merged")
        self.assertFalse(any(c[1].endswith("/merge") for c in api.calls))

    def test_a_pull_request_that_will_not_close_fails_the_probe(self) -> None:
        api = FakeApi(close_code=500)
        self.assert_fails(api, "close pull request #7 — still")
        self.assertEqual(api.state, "open")

    # review 255 C: Gitea's words, whole, for that rule; the merge message, whole
    def test_words_for_another_branch_fail_the_probe(self) -> None:
        self.assert_fails(FakeApi(), "not in the words of that rule", mode="near-words")

    def test_a_longer_merge_message_fails_the_probe(self) -> None:
        self.assert_fails(FakeApi(merge=(405, "User not allowed to merge PR: unrelated permission denied")), "HTTP 405 for another reason")

    # review 255 B: a pull request opened although its answer was lost is found and closed
    def test_a_lost_answer_still_closes_the_pull_request(self) -> None:
        api = FakeApi(create_code=502)
        r = self.assert_fails(api, "was there after all; it is closed")
        self.assertEqual(api.state, "closed")

    def test_a_lost_answer_with_nothing_opened(self) -> None:
        api = FakeApi(create_code=502, opened_anyway=False)
        r = self.assert_fails(api, "open a pull request from")
        self.assertFalse(any(c[0] == "PATCH" for c in api.calls))

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
