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
import signal
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import redirect_stdout

HERE = Path(__file__).resolve().parent
PROBE = HERE / "probe-gitea-protection.sh"
TOKEN = "fixture-probe-token-0123456789"
SETUP_TOKEN = "fixture-drill-token-0123456789"
SCOPE_DENIAL = 'token does not have at least one of required scope(s): [write:repository]'
ADMIN_DENIAL = 'user should be an owner or a collaborator with admin write of a repository'
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
    refs/tags/*)
      [[ "$mode" == odd-refusal ]] && { echo "Gitea: Internal Server Connecting Error"; exit 1; }
      [[ "$mode" == protected-word ]] && { echo "Gitea: Internal Server Connecting Error: protected-tag service unavailable"; exit 1; }
      [[ "$mode" == near-words ]] && { echo "Gitea: Tag ${ref#refs/tags/}-other is protected"; exit 1; }
      if [[ "$mode" == open-tag || "$mode" == tag-delete-fail ]]; then
        [[ "$mode" == tag-delete-fail && "$new" == "$zero" ]] && exit 1
        continue
      fi
      echo "Gitea: Tag ${ref#refs/tags/} is protected"; exit 1 ;;
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
                 negative: dict | None = None, bare: Path | None = None,
                 delay_create=False, lookup_code=None) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.bodies: list[tuple[str, str, dict]] = []
        self.state = "open"
        self.opened = False
        self.tag_exists = False
        self.deletes = 0
        self.created = threading.Event()
        self.release = threading.Event()
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
                    code, body = negative.get('handshake', 403), {'message': negative.get('handshake_message', SCOPE_DENIAL)}
                elif negative is not None and self.path.endswith('/branch_protections/main'):
                    code, body = negative.get('protection', 403), {'message': negative.get('protection_message', ADMIN_DENIAL)}
                elif negative is not None and key == ('GET', '/api/v1/repos/bifrost/primary-probe/branches/main'):
                    code, body = 200, {'protected': True}
                elif negative is not None and '/branches/agent' in self.path:
                    from urllib.parse import unquote
                    branch = unquote(self.path.split('/branches/')[1])
                    lagging = False
                    if self.command == 'DELETE' and negative.get('delete_lag', 0) > outer.deletes:
                        # Gitea's branch table not synced yet: 500, nothing deleted.
                        outer.deletes += 1
                        lagging = True
                    elif self.command == 'DELETE' and not negative.get('cleanup_fail'):
                        subprocess.run(['git', '--git-dir', str(bare), 'update-ref', '-d', 'refs/heads/' + branch], check=True)
                    found = subprocess.run(['git', '--git-dir', str(bare), 'show-ref', '--verify', 'refs/heads/' + branch], capture_output=True)
                    code, body = (500 if lagging else 200 if found.returncode == 0 else 404), {}
                elif negative is not None and self.path.endswith('/tags'):
                    code, body = negative.get('tag', 403), {'message': negative.get('tag_message', SCOPE_DENIAL)}
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
                    if negative is not None and create_code != 201:
                        body = {'message': negative.get('pr_message', SCOPE_DENIAL)}
                    outer.created.set()
                    if delay_create:
                        outer.release.wait(10)
                elif self.command == "GET" and self.path.startswith("/api/v1/repos/bifrost/primary-probe/pulls/main/agent/_probe/"):
                    code, body = (200, {"number": 7, "state": outer.state, **pad}) if outer.opened else (404, {})
                    if lookup_code:
                        code, body = lookup_code, {}
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
        self.release.set()
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


# Feed real HTTP parser failures to the probe without opening any sockets.
PROTOCOL_HTTP_SHIM = '''
import http.client
fixture_transport = urllib.request.OpenerDirector.open
class WireSocket:
    def __init__(self, wire):
        self.wire = wire
    def makefile(self, *args, **kwargs):
        return io.BytesIO(self.wire)
def protocol_open(self, req, *args, **kwargs):
    path = urllib.parse.urlsplit(req.full_url).path
    method = os.environ.get('PROBE_HTTP_FAULT_METHOD', '')
    if os.environ['PROBE_HTTP_FAULT_PATH'] not in path or (method and method != req.get_method()):
        return fixture_transport(self, req, *args, **kwargs)
    # Preserve server-side effects, including a write whose answer is lost.
    try:
        response = fixture_transport(self, req, *args, **kwargs)
    except urllib.error.HTTPError as error:
        response = error
    response.close()
    secret = os.environ['PROBE_TOKEN'].encode()
    kind = os.environ['PROBE_HTTP_FAULT']
    if kind == 'unexpected':
        raise TypeError(secret.decode())
    if kind == 'status':
        wire = b'Authorization: token ' + secret + b'\\r\\n'
    elif kind == 'header':
        wire = b'HTTP/1.1 200 OK\\r\\nX-Secret: ' + secret + b'x' * 70000 + b'\\r\\n\\r\\n'
    else:
        code = b'403 Forbidden' if kind == 'error-body' else b'200 OK'
        wire = b'HTTP/1.1 ' + code + b'\\r\\nContent-Length: 10000\\r\\n\\r\\n' + secret
    response = http.client.HTTPResponse(WireSocket(wire))
    response.begin()
    if response.status >= 400:
        raise urllib.error.HTTPError(req.full_url, response.status, 'fixture', response.headers, response)
    return response
urllib.request.OpenerDirector.open = protocol_open
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
        subprocess.run(["git", "--git-dir", str(bare), "fetch", "-q", str(seed), "main:refs/heads/main"], check=True, env=env)
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
        env = {**os.environ, "HOME": str(self.root), "TMPDIR": str(self.root), "PROBE_GITEA": f"file://{self.gitea}", "PROBE_API_BASE": api.base,
               "PROBE_TOKEN_FILE": str(self.token_file), "PROBE_MERGEABLE_WAIT": "2"}
        env.update(extra or {})
        env.update(api.env)
        return subprocess.run(["bash", *bash, str(PROBE)], env=env, capture_output=True, text=True, timeout=120)

    def test_memory_token_input_leaves_no_copy_or_trace(self):
        self.token_file.unlink()
        api = FakeApi()
        try:
            result = self.run_probe(api, bash=('-x',), extra={'PROBE_TOKEN': TOKEN})
        finally:
            api.close()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(TOKEN, result.stdout + result.stderr)
        self.assertFalse(self.token_file.exists())
        self.assertFalse(list(self.root.glob('tmp.*')))
        for path in self.root.rglob('*'):
            if path.is_file():
                self.assertNotIn(TOKEN.encode(), path.read_bytes())

    def protocol_probe(self, mode, fault, path, method='', **options):
        with patch(__name__ + '.ThreadingHTTPServer', side_effect=PermissionError):
            api = FakeApi(negative={} if mode != 'writer' else None, bare=self.bare,
                          create_code=403 if mode == 'reader' else 201,
                          opened_anyway=False, **options)
        shim = Path(api.transport.name) / 'sitecustomize.py'
        shim.write_text(FILE_HTTP_SHIM + PROTOCOL_HTTP_SHIM)
        try:
            result = self.run_probe(api, bash=('-x',), extra={
                'PROBE_MODE': mode, 'PROBE_TOKEN': TOKEN, 'PROBE_SETUP_TOKEN': SETUP_TOKEN,
                'PROBE_EXPECT_LOGIN': 'reader' if mode != 'writer' else '',
                'PROBE_HTTP_FAULT': fault, 'PROBE_HTTP_FAULT_PATH': path,
                'PROBE_HTTP_FAULT_METHOD': method})
        finally:
            api.close()
        return result, api

    def test_review618_protocol_errors_never_echo_credentials(self):
        for mode in ('writer', 'reader', 'protection'):
            for fault in ('status', 'header', 'body', 'error-body'):
                with self.subTest(mode=mode, fault=fault):
                    path = '/repos/bifrost/primary-probe' if mode == 'writer' else '/user'
                    result, _ = self.protocol_probe(mode, fault, path)
                    output = result.stdout + result.stderr
                    self.assertNotEqual(result.returncode, 0)
                    # Boolean assertions keep even synthetic credentials out of failure logs.
                    self.assertFalse(TOKEN in output or SETUP_TOKEN in output)
                    self.assertNotIn('Traceback', output)
                    self.assertIn('VERDICT FAIL', output)

    def test_review618_reader_cleanup_continues_after_protocol_errors(self):
        for fault in ('status', 'body', 'error-body', 'unexpected'):
            for path, check in (('/pulls/main/', 'PR'), ('/branches/agent', 'branch'),
                                ('/tags/probe-', 'tag')):
                with self.subTest(fault=fault, path=path):
                    result, api = self.protocol_probe('reader', fault, path)
                    output = result.stdout + result.stderr
                    self.assertNotEqual(result.returncode, 0)
                    self.assertTrue(any(method == 'DELETE' and '/branches/agent' in p
                                        for method, p, _ in api.calls))
                    self.assertTrue(any(method == 'GET' and '/tags/probe-' in p
                                        for method, p, _ in api.calls))
                    refs = subprocess.check_output(['git', '--git-dir', str(self.bare),
                                                    'for-each-ref', 'refs/heads/agent'])
                    self.assertEqual(refs, b'')
                    head = next(body['head'] for method, p, body in api.bodies
                                if method == 'POST' and p.endswith('/pulls'))
                    ref = next(body['tag_name'] for method, p, body in api.bodies
                               if method == 'POST' and p.endswith('/tags')) if check == 'tag' else head
                    failures = [line for line in output.splitlines() if line.startswith('FAIL')]
                    self.assertTrue(any(check + ' cleanup' in line and ref in line for line in failures))
                    self.assertFalse(TOKEN in output or SETUP_TOKEN in output)
                    self.assertNotIn('Traceback', output)
                    self.assertIn('VERDICT FAIL mode=reader', output)

    def test_review618_writer_lost_pr_protocol_response_is_reconciled(self):
        for method in ('', 'POST'):
            with self.subTest(method=method):
                result, api = self.protocol_probe('writer', 'error-body', '/pulls', method=method)
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(TOKEN in output or SETUP_TOKEN in output)
                self.assertNotIn('Traceback', output)
                if method == 'POST':
                    self.assertEqual(api.state, 'closed')
                    self.assertIn('ok    PR cleanup #7', output)
                else:
                    self.assertIn('FAIL  PR cleanup agent/_probe/', output)
                self.assertIn('VERDICT FAIL mode=writer', output)
                self.assertTrue(any('/pulls/main/' in p for _, p, _ in api.calls))
                refs = subprocess.check_output(['git', '--git-dir', str(self.bare),
                                                'for-each-ref', 'refs/heads/agent'])
                self.assertEqual(refs, b'')

    def test_untrusted_git_errors_do_not_log_or_persist_tokens(self):
        extra = self.git_wrapper('''
if [[ "$*" == *HEAD:refs/tags/* || "$*" == *:refs/heads/agent/* ]]; then
  echo "fatal: $PROBE_TOKEN" >&2
  exit 42
fi
exec "$real_git" "$@"
''')
        api = FakeApi()
        try:
            result = self.run_probe(api, extra=extra)
        finally:
            api.close()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(TOKEN, result.stdout + result.stderr)
        self.assertFalse(list(self.root.glob('tmp.*')))

    def test_review622_writer_pr_cleanup_protocol_failures(self):
        for method in ('PATCH', 'GET'):
            for fault in ('status', 'header', 'body', 'error-body'):
                with self.subTest(method=method, fault=fault):
                    result, api = self.protocol_probe('writer', fault, '/pulls/7', method=method)
                    output = result.stdout + result.stderr
                    head = next(body['head'] for verb, path, body in api.bodies
                                if verb == 'POST' and path.endswith('/pulls'))
                    # The write took effect even though its response was lost.
                    self.assertEqual(api.state, 'closed')
                    self.assertTrue(any(verb == 'GET' and path.endswith('/pulls/7')
                                        for verb, path, _ in api.calls))
                    self.assertEqual(subprocess.check_output([
                        'git', '--git-dir', str(self.bare), 'for-each-ref',
                        'refs/heads/agent', 'refs/tags']), b'')
                    self.assertFalse(list(self.root.glob('tmp.*')))
                    self.assertNotIn(TOKEN, output)
                    self.assertNotIn(SETUP_TOKEN, output)
                    self.assertNotIn('Traceback', output)
                    self.assertNotEqual(result.returncode, 0)
                    failures = [line for line in output.splitlines() if line.startswith('FAIL')]
                    self.assertTrue(any('#7' in line and head in line and 'HTTP 0' in line
                                        for line in failures))
                    self.assertIn('VERDICT FAIL mode=writer', output)
                    self.assertNotIn('VERDICT PASS', output)

    def test_review622_writer_git_cleanup_failures_are_reported(self):
        for fault in ('tag-lookup', 'tag-delete', 'tag-readback', 'branch-delete'):
            with self.subTest(fault=fault):
                extra = self.git_wrapper('''
if [[ "$1" == ls-remote && "$3" == refs/tags/probe-* ]]; then
  if [[ ! -f "$PROBE_SEEN" ]]; then
    touch "$PROBE_SEEN"
    [[ "$PROBE_CLEANUP_FAULT" == tag-lookup ]] && exit 42
  elif [[ "$PROBE_CLEANUP_FAULT" == tag-readback ]]; then
    exit 42
  fi
fi
if [[ "$*" == *:refs/heads/agent/* && "$*" != *HEAD:refs/heads/agent/* && "$PROBE_CLEANUP_FAULT" == branch-delete ]]; then
  # Fail the normal delete, then lose the successful exit-cleanup response.
  if [[ ! -f "$PROBE_SEEN" ]]; then touch "$PROBE_SEEN"; exit 42; fi
  "$real_git" "$@"
  echo "$PROBE_TOKEN" >&2
  exit 42
fi
"$real_git" "$@"
rc=$?
if [[ "$*" == *:refs/tags/probe-* && "$*" != *HEAD:refs/tags/probe-* && "$PROBE_CLEANUP_FAULT" == tag-delete ]]; then
  echo "$PROBE_TOKEN" >&2
  exit 42
fi
exit "$rc"
''')
                marker = self.root / 'cleanup-seen'
                marker.unlink(missing_ok=True)
                extra.update(PROBE_CLEANUP_FAULT=fault, PROBE_SEEN=str(marker), PROBE_TOKEN=TOKEN)
                api = FakeApi()
                try:
                    result = self.run_probe(api, mode='open-tag' if fault == 'tag-delete' else '', extra=extra)
                finally:
                    api.close()
                output = result.stdout + result.stderr
                self.assertEqual(api.state, 'closed')
                self.assertEqual(subprocess.check_output([
                    'git', '--git-dir', str(self.bare), 'for-each-ref',
                    'refs/heads/agent', 'refs/tags']), b'')
                self.assertFalse(list(self.root.glob('tmp.*')))
                self.assertNotIn(TOKEN, output)
                self.assertNotEqual(result.returncode, 0)
                ref = 'refs/heads/agent/_probe/' if fault == 'branch-delete' else 'refs/tags/probe-'
                step = {'tag-lookup': 'lookup failed', 'tag-delete': 'delete failed',
                        'tag-readback': 'absence not verified', 'branch-delete': 'delete failed'}[fault]
                self.assertTrue(any(line.startswith('FAIL') and ref in line and step in line
                                    for line in output.splitlines()))
                self.assertIn('VERDICT FAIL mode=writer', output)

    def test_review622_writer_local_cleanup_failure_reports_directory(self):
        directory = self.root / 'bin'
        directory.mkdir()
        wrapper = directory / 'rm'
        wrapper.write_text('#!/bin/bash\necho "$PROBE_TOKEN" >&2\nexit 42\n')
        wrapper.chmod(0o755)
        api = FakeApi()
        try:
            result = self.run_probe(api, extra={
                'PATH': str(directory) + ':' + os.environ['PATH'], 'PROBE_TOKEN': TOKEN})
        finally:
            api.close()
        output = result.stdout + result.stderr
        # Where mktemp puts the directory differs (GNU honours TMPDIR, BSD may
        # not); take the path from the FAIL line and check it really remains.
        lines = [line for line in output.splitlines() if line.startswith('FAIL') and 'local cleanup' in line]
        self.assertEqual(len(lines), 1, output)
        remaining = [Path(word) for word in lines[0].split() if word.startswith('/') and Path(word.rstrip(';')).is_dir()]
        remaining = [Path(str(path).rstrip(';')) for path in remaining]
        self.assertEqual(len(remaining), 1, output)
        self.assertEqual(api.state, 'closed')
        self.assertEqual(subprocess.check_output([
            'git', '--git-dir', str(self.bare), 'for-each-ref',
            'refs/heads/agent', 'refs/tags']), b'')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(line.startswith('FAIL') and 'local cleanup' in line
                            and str(remaining[0]) in line for line in output.splitlines()))
        self.assertNotIn(TOKEN, output)
        self.assertIn('VERDICT FAIL mode=writer', output)

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

    def test_skip_pr_opens_no_pull_request_and_says_so(self) -> None:
        # S3 lander: its team has no pull-request unit; the probe leaves the PR
        # out, says the PR is unverified, and still checks tag, branch, main.
        api = FakeApi()
        try:
            r = self.run_probe(api, extra={"PROBE_SKIP_PR": "1"})
        finally:
            api.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(any(path.endswith("/pulls") for _, path, _ in api.calls), api.calls)
        self.assertIn("UNVERIFIED pull request: skipped", r.stdout)
        self.assertIn("ok    delete agent/_probe/", r.stdout)
        self.assertIn("no pull request was opened", r.stdout)
        self.assertNotIn("FAIL", r.stdout)

    def test_skip_pr_still_fails_an_open_tag(self) -> None:
        api = FakeApi()
        try:
            r = self.run_probe(api, mode="open-tag", extra={"PROBE_SKIP_PR": "1"})
        finally:
            api.close()
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("FAIL", r.stdout + r.stderr)

    def git_wrapper(self, body):
        directory = self.root / 'bin'
        directory.mkdir(exist_ok=True)
        wrapper = directory / 'git'
        wrapper.write_text('#!/bin/bash\nreal_git=' + shutil.which('git') + '\n' + body)
        wrapper.chmod(0o755)
        return {'PATH': str(directory) + ':' + os.environ['PATH']}

    def test_b1_never_pushes_or_merges_main_even_if_unprotected(self):
        before = subprocess.check_output(['git', '--git-dir', str(self.bare), 'rev-parse', 'main'])
        calls = self.root / 'git-calls'
        extra = self.git_wrapper('printf "%s\\n" "$*" >> "$PROBE_CALLS"\nexec "$real_git" "$@"\n')
        extra['PROBE_CALLS'] = str(calls)
        api = FakeApi(merge=(200, ''))
        try:
            result = self.run_probe(api, mode='open-main', extra=extra)
        finally:
            api.close()
        self.assertEqual(before, subprocess.check_output(['git', '--git-dir', str(self.bare), 'rev-parse', 'main']))
        self.assertFalse(any('push' in line and ':refs/heads/main' in line for line in calls.read_text().splitlines()))
        self.assertFalse(any(path.endswith('/merge') for _, path, _ in api.calls))
        self.assertIn('UNVERIFIED main push/merge', result.stdout)

    def test_c2_delete_readback_error_fails_and_retries_cleanup(self):
        extra = self.git_wrapper('''
if [[ "$1" == ls-remote && "$3" == refs/heads/agent/* ]]; then
  echo readback >> "$PROBE_READBACKS"
  exit 42
fi
exec "$real_git" "$@"
''')
        calls = self.root / 'readbacks'
        extra['PROBE_READBACKS'] = str(calls)
        api = FakeApi()
        try:
            result = self.run_probe(api, extra=extra)
        finally:
            api.close()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn('ok    delete agent/', result.stdout)
        self.assertGreaterEqual(len(calls.read_text().splitlines()), 2)
        self.assertIn('FAIL  exit cleanup', result.stderr)

    def test_c3_writer_cleans_unexpected_tag_even_after_lost_response(self):
        for lost in (False, True):
            with self.subTest(lost=lost):
                extra = self.git_wrapper('''
"$real_git" "$@"
rc=$?
if [[ "$*" == *HEAD:refs/tags/* && "$PROBE_LOSE_TAG" == yes ]]; then exit 42; fi
exit "$rc"
''')
                extra['PROBE_LOSE_TAG'] = 'yes' if lost else 'no'
                api = FakeApi()
                try:
                    result = self.run_probe(api, mode='open-tag', extra=extra)
                finally:
                    api.close()
                self.assertNotEqual(result.returncode, 0)
                refs = subprocess.check_output(['git', '--git-dir', str(self.bare), 'for-each-ref', 'refs/tags'])
                self.assertEqual(refs, b'')
                self.assertIn('tag cleanup', result.stdout)

    def test_c3_writer_reports_tag_cleanup_failure(self):
        api = FakeApi()
        try:
            result = self.run_probe(api, mode='tag-delete-fail')
        finally:
            api.close()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FAIL  tag cleanup refs/tags/probe-', result.stderr)

    def test_c4_signal_during_pr_creation_finds_and_closes_pr(self):
        for sig in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(sig=sig):
                api = FakeApi(delay_create=True)
                env = {**os.environ, **api.env, 'HOME': str(self.root),
                       'PROBE_GITEA': f'file://{self.gitea}', 'PROBE_API_BASE': api.base,
                       'PROBE_TOKEN_FILE': str(self.token_file), 'TMPDIR': str(self.root)}
                process = subprocess.Popen(['bash', str(PROBE)], env=env, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, text=True, start_new_session=True)
                try:
                    self.assertTrue(api.created.wait(10))
                    os.killpg(process.pid, sig)
                    api.release.set()
                    stdout, stderr = process.communicate(timeout=15)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()
                    api.close()
                self.assertEqual(process.returncode, 128 + sig)
                self.assertEqual(api.state, 'closed', stdout + stderr)
                self.assertNotIn(TOKEN, stdout + stderr)
                self.assertFalse(list(self.root.glob('tmp.*')))

    def test_c4_unknown_pr_lookup_failure_reports_head(self):
        api = FakeApi(create_code=502, lookup_code=500)
        try:
            result = self.run_probe(api)
        finally:
            api.close()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FAIL  PR cleanup agent/_probe/', result.stderr)

    # TD-383: an agent/ branch Gitea will not let agentd delete fails the probe
    def test_a_protected_agent_branch_fails_the_probe(self) -> None:
        r = self.assert_fails(FakeApi(), "delete or readback failed", mode="protected-agent")
        self.assertIn("FAIL  delete agent/_probe/", r.stdout)


    def test_a_refusal_that_is_not_a_rule_fails_the_probe(self) -> None:
        api = FakeApi()
        try:
            r = self.run_probe(api, mode="odd-refusal")
        finally:
            api.close()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("refused, but not in the words of that rule", r.stdout)


    # Unknown tag refusals fail; the temporary PR is still closed.
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


    def test_a_pull_request_that_will_not_close_fails_the_probe(self) -> None:
        api = FakeApi(close_code=500)
        self.assert_fails(api, "close pull request #7 — still")
        self.assertEqual(api.state, "open")

    # review 255 C: require the complete tag rule and exact ref.
    def test_words_for_another_tag_fail_the_probe(self) -> None:
        self.assert_fails(FakeApi(), "not in the words of that rule", mode="near-words")


    # review 255 B: a pull request opened although its answer was lost is found and closed
    def test_a_lost_answer_still_closes_the_pull_request(self) -> None:
        api = FakeApi(create_code=502)
        r = self.assert_fails(api, "PR cleanup #7")
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

    def test_review628_reader_local_cleanup_failure_reports_directory(self):
        # Review 628 C1: a reader clone directory that cannot be removed must be
        # named in a FAIL line, not swallowed by the generic precondition FAIL.
        shim_dir = self.root / 'rmtree-shim'
        shim_dir.mkdir()
        (shim_dir / 'sitecustomize.py').write_text(
            "import os, shutil\n"
            "from pathlib import Path\n"
            "_orig = shutil.rmtree\n"
            "def _refuse(path, *a, **k):\n"
            "    if Path(path).name.startswith('p0-reader-'):\n"
            "        raise PermissionError(13, 'injected cleanup failure', str(path))\n"
            "    return _orig(path, *a, **k)\n"
            "shutil.rmtree = _refuse\n"
            "_t = os.environ.get('PROBE_TEST_TRANSPORT')\n"
            "if _t and os.path.exists(os.path.join(_t, 'sitecustomize.py')):\n"
            "    exec(compile(open(os.path.join(_t, 'sitecustomize.py')).read(), 'transport_shim', 'exec'))\n")
        setup = self.root / 'setup-token'
        setup.write_text(SETUP_TOKEN)
        api = FakeApi(negative={}, bare=self.bare, create_code=403)
        # FakeApi.env is a property (and in sandbox transport mode it sets its own
        # PYTHONPATH); the shim goes first and chains the transport shim itself.
        transport_env = dict(api.env)
        transport_env['PYTHONPATH'] = str(shim_dir)
        try:
            with patch.object(type(api), 'env', new=property(lambda _self: transport_env)):
                result = self.run_probe(api, extra={
                    'PROBE_MODE': 'reader', 'PROBE_EXPECT_LOGIN': 'reader', 'PROBE_SETUP_TOKEN_FILE': str(setup)})
        finally:
            api.close()
        output = result.stdout + result.stderr
        remaining = list(self.root.glob('p0-reader-*'))
        self.assertEqual(len(remaining), 1, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(line.startswith('FAIL') and 'local cleanup' in line and str(remaining[0]) in line
                            for line in output.splitlines()), output)
        self.assertEqual(subprocess.check_output(['git', '--git-dir', str(self.bare), 'for-each-ref', 'refs/heads/agent'], text=True), '')
        self.assertNotIn(TOKEN, output)
        self.assertNotIn(SETUP_TOKEN, output)
        self.assertIn('VERDICT FAIL mode=reader', output)

    def test_protection_only_never_creates_a_fixture(self):
        result, api = self.negative_probe(probe_mode='protection')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any(method in ('POST', 'DELETE') for method, _, _ in api.calls))
        self.assertIn('VERDICT PASS mode=protection', result.stdout)

    def test_c1_401_is_not_authorization_evidence_after_valid_identity(self):
        result, _ = self.negative_probe({'handshake': 401, 'protection': 401, 'tag': 401}, create_code=401)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_c1_same_status_wrong_reason_fails_for_each_endpoint(self):
        for field in ('protection', 'handshake', 'pr', 'tag'):
            for message in ('', 'CSRF check failed', 'token is invalid', 'insufficient scope', ADMIN_DENIAL + ' unrelated', TOKEN):
                with self.subTest(field=field, message=message):
                    result, _ = self.negative_probe({field + '_message': message})
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_p0_01_git_bare_forbidden_is_a_scope_denial_only_for_the_handshake(self):
        # Gitea 1.21.11's git HTTP scope check answers a bare "Forbidden" (2026-10-27 P0-01 run).
        result, _ = self.negative_probe({'handshake_message': 'Forbidden'})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('push handshake: HTTP 403; token scope (git HTTP bare 403); repository ACL unverified', result.stdout)
        for field in ('protection', 'pr', 'tag'):
            with self.subTest(field=field):
                result, _ = self.negative_probe({field + '_message': 'Forbidden'})
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        result, _ = self.negative_probe({'handshake_message': 'Forbidden', 'handshake': 404})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_p0_01_branch_cleanup_waits_for_gitea_branch_table(self):
        # A just-pushed branch: DELETE answers 500 until Gitea syncs it (2026-10-27 P0-01 run).
        result, _ = self.negative_probe({'delete_lag': 2})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('after 3 attempt(s); readback HTTP 404', result.stdout)
        refs = subprocess.check_output(['git', '--git-dir', str(self.bare), 'for-each-ref', 'refs/heads/agent'], text=True)
        self.assertEqual(refs, '')

    def test_c1_scope_denial_is_labeled_separately(self):
        result, _ = self.negative_probe({'protection_message': SCOPE_DENIAL})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('token scope; repository ACL unverified', result.stdout)

    def test_c1_protection_mode_requires_acl_denial(self):
        result, _ = self.negative_probe({'protection_message': SCOPE_DENIAL}, probe_mode='protection')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

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


class DesktopCredential(unittest.TestCase):
    def test_review618_review_commands_include_committed_fixes(self):
        steps = HERE.parents[1] / 'agent-config/work/multi-agent/OWNER-STEPS-p0-remaining-2026-10-26.md'
        block = steps.read_text().split('```bash\n', 1)[1].split('```', 1)[0]
        files = ('scripts/agent-host/probe-gitea-protection.sh',
                 'scripts/agent-host/test_probe_gitea_protection.py',
                 'agent-config/work/multi-agent/OWNER-STEPS-p0-remaining-2026-10-26.md')
        for command in ('git show 531016b --', 'git diff 531016b HEAD --', 'git diff HEAD --'):
            lines = [line for line in block.splitlines() if line.startswith(command)]
            self.assertEqual(len(lines), 1, command)
            self.assertTrue(all(path in lines[0] for path in files))

    def test_c5_real_push_url_must_select_expected_credential(self):
        steps = HERE.parents[1] / 'agent-config/work/multi-agent/OWNER-STEPS-p0-remaining-2026-10-26.md'
        source = steps.read_text().split("<<'PY'\n")[-1].split('\nPY\n')[0]
        good = 'http://192.168.10.73:30300/bifrost/bifrost-platform.git'
        other = good.replace('http://', 'http://other-nonadmin@')
        for variant in ('username', 'pushurl', 'rewrite', 'multiple', 'wrong-path', 'good', 'named', 'good-rewrite'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                checkout = Path(directory) / 'repo'
                destination = Path(directory) / 'token'
                env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
                env.update(HOME=directory, GIT_TERMINAL_PROMPT='0')
                run = subprocess.run
                def git(*args):
                    return run(['git', '-C', str(checkout), *args], env=env, check=True, capture_output=True)
                run(['git', 'init', '-q', str(checkout)], env=env, check=True)
                helper = Path(directory) / 'helper'
                helper.write_text('#!/bin/sh\nu=bifrost-mbp\nwhile IFS= read -r line; do\n'
                                  'case "$line" in username=*) u=${line#username=};; esac\ndone\n'
                                  'printf "username=%s\\npassword=' + TOKEN + '\\n" "$u"\n')
                helper.chmod(0o755)
                git('config', 'credential.helper', str(helper))
                git('remote', 'add', 'origin', other if variant == 'username' else good)
                if variant == 'pushurl':
                    git('config', 'remote.origin.pushurl', other)
                if variant == 'rewrite':
                    git('config', 'url.' + other + '.pushInsteadOf', good)
                if variant == 'multiple':
                    git('config', '--add', 'remote.origin.pushurl', good)
                    git('config', '--add', 'remote.origin.pushurl', other)
                if variant == 'wrong-path':
                    git('config', 'remote.origin.pushurl', good.replace('bifrost-platform.git', 'another.git'))
                if variant == 'named':
                    git('config', 'remote.origin.pushurl', good.replace('http://', 'http://bifrost-mbp@'))
                if variant == 'good-rewrite':
                    git('remote', 'set-url', 'origin', 'fixture:repo')
                    git('config', 'url.' + good + '.pushInsteadOf', 'fixture:repo')
                expected_url = git('remote', 'get-url', '--push', 'origin').stdout.decode().strip()
                lookups, probes = [], []
                def run_checked(args, **kwargs):
                    if args[0] == 'bash':
                        probes.append(True)
                        self.assertEqual(kwargs['env']['PROBE_TOKEN'], TOKEN)
                        return subprocess.CompletedProcess(args, 0)
                    if 'credential' in args:
                        lookups.append(kwargs['input'])
                    return run(args, **kwargs)
                response = io.BytesIO(json.dumps({'permissions': {'admin': False}}).encode())
                response.status = 200
                output = io.StringIO()
                with patch.dict(os.environ, env, clear=True), patch('sys.argv', ['probe', str(checkout), 'bifrost-platform', str(destination)]), \
                     patch('urllib.request.build_opener', return_value=SimpleNamespace(open=lambda *a, **k: response)), \
                     patch('subprocess.run', side_effect=run_checked), redirect_stdout(output):
                    if variant in ('good', 'named', 'good-rewrite'):
                        exec(compile(source, str(steps), 'exec'), {})
                        self.assertEqual(lookups, ['url=' + expected_url + '\n\n'])
                        self.assertEqual(probes, [True])
                    else:
                        with self.assertRaises(SystemExit):
                            exec(compile(source, str(steps), 'exec'), {})
                        self.assertEqual(lookups, [])
                        self.assertEqual(probes, [])
                self.assertNotIn(TOKEN, output.getvalue())
                self.assertFalse(destination.exists())


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
