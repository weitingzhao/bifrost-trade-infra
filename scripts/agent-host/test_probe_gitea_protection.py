"""probe-gitea-protection.sh against a local stand-in for Gitea.

The git side is a bare repository served as file:// whose pre-receive hook
refuses with Gitea 1.21's protection messages (main and tags protected;
agent/** not protected since TD-383, so its branches may be created and
deleted; mode protected-agent puts the old rule back); the API side is a small
local HTTP server for the repository and pull-request calls. No network, no
cluster.

    python3 -m unittest scripts/agent-host/test_probe_gitea_protection.py
"""

from __future__ import annotations

import json
import io
import ast
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PROBE = HERE / "probe-gitea-protection.sh"
TOKEN = "fixture-probe-token-0123456789"
SETUP_TOKEN = "fixture-drill-token-0123456789"
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
      if [[ "$mode" == protected-agent && "$new" == "$zero" ]]; then
        echo "Gitea: branch ${ref#refs/heads/} is protected from deletion"; exit 1
      fi ;;
  esac
done
"""


class FakeApi:
    """The repository and pull-request calls, with answers as large as Gitea's (a padding field)."""

    def __init__(self, merge: tuple[int, str] = (405, "User not allowed to merge PR"), close_code: int = 201,
                 mergeable: bool = True, create_code: int = 201, opened_anyway: bool = True,
                 negative: dict | None = None, bare: Path | None = None) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.bodies: list[tuple[str, str, dict]] = []
        self.state = "open"
        self.opened = False
        self.tag_exists = False
        outer = self
        pad = {"padding": "x" * 5000}

        class H(BaseHTTPRequestHandler):
            def _go(self) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(n)) if n else None
                outer.bodies.append((self.command, self.path, payload))
                outer.calls.append((self.command, self.path, self.headers.get("Authorization", "")))
                key, pr = (self.command, self.path), "/api/v1/repos/bifrost/primary-probe/pulls/7"
                if negative is not None and key == ('GET', '/api/v1/user'):
                    setup = self.headers.get('Authorization') == 'token ' + SETUP_TOKEN
                    code, body = 200, {'login': 'agentrt-landing-stg' if setup else negative.get('login', 'reader'), 'is_admin': False}
                elif negative is not None and self.path.endswith('/info/refs?service=git-receive-pack'):
                    code, body = negative.get('handshake', 403), {}
                elif negative is not None and self.path.endswith('/branch_protections/main'):
                    code, body = negative.get('protection', 403), {}
                elif negative is not None and key == ('GET', '/api/v1/repos/bifrost/primary-probe/branches/main'):
                    code, body = 200, {'protected': True}
                elif negative is not None and '/branches/agent' in self.path:
                    from urllib.parse import unquote
                    branch = unquote(self.path.split('/branches/')[1])
                    if self.command == 'DELETE' and not negative.get('cleanup_fail'):
                        subprocess.run(['git', '--git-dir', str(bare), 'update-ref', '-d', 'refs/heads/' + branch], check=True)
                    found = subprocess.run(['git', '--git-dir', str(bare), 'show-ref', '--verify', 'refs/heads/' + branch], capture_output=True)
                    code, body = (200 if found.returncode == 0 else 404), {}
                elif negative is not None and self.path.endswith('/tags'):
                    code, body = negative.get('tag', 403), {}
                    outer.tag_exists = code in (200, 201)
                elif negative is not None and '/tags/probe-' in self.path:
                    if self.command == 'DELETE' and not negative.get('cleanup_fail'):
                        outer.tag_exists = False
                    code, body = (200 if outer.tag_exists else 404), {}
                elif key == ("GET", "/api/v1/repos/bifrost/primary-probe"):
                    code, body = 200, {"name": "primary-probe", "mirror": False, "archived": False, 'permissions': {'admin': False}, **pad}
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

            do_GET = do_POST = do_PATCH = do_DELETE = _go

            def log_message(self, *a) -> None:
                pass

        self.transport = None
        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        except PermissionError:
            # Restricted runners cannot bind even loopback. Exercise the same
            # handler through files, without skipping any assertion or opening
            # a socket. The child shim replaces only this fixture's HTTP URL.
            self.server = None
            self.transport = tempfile.TemporaryDirectory(prefix='probe-http-fixture-')
            directory = Path(self.transport.name)
            (directory / 'sitecustomize.py').write_text(FILE_HTTP_SHIM)
            self.stopping = threading.Event()

            def serve_files():
                while not self.stopping.wait(0.01):
                    for path in directory.glob('*.request'):
                        data = json.loads(path.read_text())
                        handler = H.__new__(H)
                        handler.command, handler.path = data['method'], data['path']
                        handler.headers = data['headers']
                        handler.rfile = io.BytesIO(data['body'].encode())
                        handler.wfile = io.BytesIO()
                        handler.send_response = lambda code: setattr(handler, 'code', code)
                        handler.send_header = lambda *args: None
                        handler.end_headers = lambda: None
                        handler._go()
                        answer = path.with_suffix('.tmp')
                        answer.write_text(json.dumps({'code': handler.code, 'body': handler.wfile.getvalue().decode()}))
                        answer.rename(path.with_suffix('.response'))
                        path.unlink()

            self.thread = threading.Thread(target=serve_files, daemon=True)
            self.thread.start()
        else:
            threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def base(self) -> str:
        if self.transport:
            return 'http://probe-fixture.invalid/api/v1'
        return f"http://127.0.0.1:{self.server.server_address[1]}/api/v1"

    @property
    def env(self) -> dict:
        if self.transport:
            return {'PYTHONPATH': self.transport.name, 'PROBE_TEST_TRANSPORT': self.transport.name}
        return {}

    def close(self) -> None:
        if self.transport:
            self.stopping.set()
            self.thread.join(timeout=5)
            self.transport.cleanup()
            return
        self.server.shutdown()
        self.server.server_close()


FILE_HTTP_SHIM = '''import io, json, os, time, urllib.error, urllib.parse, urllib.request, uuid
from pathlib import Path
original_open = urllib.request.OpenerDirector.open
def fixture_open(self, req, *args, **kwargs):
    if not req.full_url.startswith('http://probe-fixture.invalid/'):
        return original_open(self, req, *args, **kwargs)
    directory = Path(os.environ['PROBE_TEST_TRANSPORT'])
    path = directory / (uuid.uuid4().hex + '.request')
    body = (req.data or b'').decode()
    parsed = urllib.parse.urlsplit(req.full_url)
    headers = {k.title(): v for k, v in req.header_items()}
    headers['Content-Length'] = str(len(body.encode()))
    data = {'method': req.get_method(), 'path': parsed.path + ('?' + parsed.query if parsed.query else ''),
            'headers': headers, 'body': body}
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data))
    temp.rename(path)
    answer = path.with_suffix('.response')
    deadline = time.monotonic() + 15
    while not answer.exists():
        if time.monotonic() > deadline:
            raise OSError('fixture response timed out')
        time.sleep(0.01)
    response = json.loads(answer.read_text())
    answer.unlink()
    stream = io.BytesIO(response['body'].encode())
    if not 200 <= response['code'] < 300:
        raise urllib.error.HTTPError(req.full_url, response['code'], 'fixture response', {}, stream)
    stream.status = response['code']
    return stream
urllib.request.OpenerDirector.open = fixture_open
'''


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

    def run_probe(self, api: FakeApi, mode: str = "", bash: tuple[str, ...] = (), extra: dict | None = None) -> subprocess.CompletedProcess:
        (self.bare / "probe-mode").write_text(mode)
        env = {**os.environ, "HOME": str(self.root), "PROBE_GITEA": f"file://{self.gitea}", "PROBE_API_BASE": api.base,
               "PROBE_TOKEN_FILE": str(self.token_file), "PROBE_MERGEABLE_WAIT": "2"}
        env.update(extra or {})
        env.update(api.env)
        return subprocess.run(["bash", *bash, str(PROBE)], env=env, capture_output=True, text=True, timeout=120)

    def test_every_rule_holds(self) -> None:
        api = FakeApi()
        try:
            r = self.run_probe(api)
        finally:
            api.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.count("\nok "), 8, r.stdout)
        self.assertIn("ok    delete agent/_probe/", r.stdout)
        refs = subprocess.run(["git", "--git-dir", str(self.bare), "for-each-ref", "refs/heads/agent"], capture_output=True, text=True)
        self.assertEqual(refs.stdout, "", "the probe's branch is gone")
        self.assertEqual(api.state, "closed")
        self.assertNotIn("FAIL", r.stdout)
        self.assertIn("all as expected", r.stdout)
        self.assertTrue(all(auth == "token " + TOKEN for _, _, auth in api.calls))
        self.assertNotIn(TOKEN, r.stdout + r.stderr)

    # TD-383: an agent/ branch Gitea will not let agentd delete fails the probe
    def test_a_protected_agent_branch_fails_the_probe(self) -> None:
        r = self.assert_fails(FakeApi(), "is protected from deletion", mode="protected-agent")
        self.assertIn("FAIL  delete agent/_probe/", r.stdout)

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

    def negative_probe(self, options=None, probe_mode='reader', create_code=403, opened_anyway=False):
        options = options or {}
        setup = self.root / 'setup-token'
        setup.write_text(SETUP_TOKEN)
        api = FakeApi(negative=options, bare=self.bare, create_code=create_code, opened_anyway=opened_anyway)
        try:
            result = self.run_probe(api, bash=('-x',), extra={
                'PROBE_MODE': probe_mode, 'PROBE_EXPECT_LOGIN': 'reader',
                'PROBE_SETUP_TOKEN_FILE': str(setup)})
        finally:
            api.close()
        self.assertNotIn(TOKEN, result.stdout + result.stderr)
        self.assertNotIn(SETUP_TOKEN, result.stdout + result.stderr)
        return result, api

    def test_reader_denials_and_cleanup(self):
        result, api = self.negative_probe()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for check in ('push handshake', 'PR open', 'tag create', 'protection edit'):
            self.assertIn(f'{check}: HTTP 403', result.stdout)
        self.assertIn('VERDICT PASS mode=reader', result.stdout)
        refs = subprocess.check_output(['git', '--git-dir', str(self.bare), 'for-each-ref', 'refs/heads/agent'], text=True)
        self.assertEqual(refs, '')
        for method, path, body in api.bodies:
            if '/branch_protections/' in path:
                self.assertEqual((method, body), ('PATCH', {}))
            if method == 'POST' and path.endswith('/pulls'):
                self.assertTrue(body['head'].startswith('agent/_probe/'))
                self.assertEqual(body['base'], 'main')
        # Only the target token performs the denial attempts, not the setup token.
        for method, path, auth in api.calls:
            if method in ('POST', 'PATCH') and not path.endswith('/pulls/7'):
                self.assertEqual(auth, 'token ' + TOKEN)

    def test_protection_only_never_creates_a_fixture(self):
        result, api = self.negative_probe(probe_mode='protection')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any(method in ('POST', 'DELETE') for method, _, _ in api.calls))
        self.assertIn('VERDICT PASS mode=protection', result.stdout)

    def test_401_is_an_authorization_denial_after_valid_identity(self):
        result, _ = self.negative_probe({'handshake': 401, 'protection': 401, 'tag': 401}, create_code=401)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unexpected_tag_is_removed_but_still_fails(self):
        result, api = self.negative_probe({'tag': 201})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertFalse(api.tag_exists)
        self.assertTrue(any(method == 'DELETE' and '/tags/' in path for method, path, _ in api.calls))

    def test_non_authorization_answers_are_failures(self):
        for field in ('handshake', 'protection', 'tag'):
            for status in (200, 404, 422, 500, 302):
                with self.subTest(field=field, status=status):
                    result, _ = self.negative_probe({field: status})
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('VERDICT FAIL', result.stdout)

    def test_reader_pr_unexpected_success_and_lost_response_are_closed(self):
        for status in (201, 502):
            with self.subTest(status=status):
                result, api = self.negative_probe(create_code=status, opened_anyway=True)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(api.state, 'closed')
                self.assertIn('PR #7 closed readback', result.stdout)

    def test_reader_pr_validation_error_is_not_denial(self):
        result, _ = self.negative_probe(create_code=422)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('PR open: HTTP 422', result.stdout)

    def test_cleanup_failure_is_not_a_pass(self):
        result, _ = self.negative_probe({'cleanup_fail': True})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('FAIL bifrost/primary-probe reader branch cleanup', result.stdout)

    def test_wrong_identity_stops_before_writes(self):
        result, api = self.negative_probe({'login': 'weitingzhao'})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertFalse(any(method != 'GET' for method, _, _ in api.calls))


class InstalledIdentity(unittest.TestCase):
    """Old 06 credentials have repository scope only; never widen it for a probe."""

    def test_installed_file_fallback_is_bound_to_user_file_and_scope_denial(self):
        source = PROBE.read_text().split("python3 - <<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
        module = ast.parse(source)
        definitions = [node for node in module.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                       and node.name in ('ProbeError', 'require', 'identify')]
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / '.config/bifrost/agentd-git.token'
            original.parent.mkdir(parents=True)
            original.write_text(TOKEN)
            account = SimpleNamespace(pw_name='bifrost-agentd-stg', pw_dir=directory)
            namespace = {'Path': Path, 'os': os, 'mode': 'protection',
                         'pwd': SimpleNamespace(getpwuid=lambda uid: account)}
            exec(compile(ast.Module(body=definitions, type_ignores=[]), str(PROBE), 'exec'), namespace)
            with patch.dict(os.environ, {'PROBE_IDENTITY_SOURCE': 'installed-file'}):
                cases = [
                    (403, {'message': 'token does not have at least one of required scope(s): [read:user]'}, 'bifrost-agentd-stg', TOKEN, True),
                    (401, {}, 'bifrost-agentd-stg', TOKEN, False),
                    (403, {'message': 'other forbidden'}, 'bifrost-agentd-stg', TOKEN, False),
                    (200, {'login': 'weitingzhao', 'is_admin': True}, 'bifrost-agentd-stg', TOKEN, False),
                    (403, {'message': 'required scope(s): [read:user]'}, 'bifrost-agentd', TOKEN, False),
                    (403, {'message': 'required scope(s): [read:user]'}, 'bifrost-agentd-stg', SETUP_TOKEN, False),
                ]
                for code, body, user, token, allowed in cases:
                    with self.subTest(code=code, user=user, allowed=allowed):
                        account.pw_name = user
                        namespace['request'] = lambda *args: (code, body)
                        if allowed:
                            self.assertIn('installed-file/Unix-user', namespace['identify'](token, 'agentd-agent-06-stg'))
                        else:
                            with self.assertRaises(namespace['ProbeError']):
                                namespace['identify'](token, 'agentd-agent-06-stg')


if __name__ == "__main__":
    unittest.main()
