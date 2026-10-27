"""Offline tests of probe-main-refusal.py: a local bare repository stands in for
Gitea's git side (a pre-receive hook refuses main like a protected branch) and a
small HTTP server for its API. Run: python3 -m pytest -q scripts/agent-host/test_probe_main_refusal.py
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'probe-main-refusal.py'
TOKEN = 'p0-secret-token-value-must-not-print'
REPO = 'bifrost/probe-repo'
REFUSE_HOOK = '''#!/bin/sh
while read old new ref; do
  if [ "$ref" = refs/heads/main ]; then
    echo "Not allowed to push to protected branch main" >&2
    exit 1
  fi
done
exit 0
'''


def git(*args, cwd=None):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class FakeGitea:
    def __init__(self, bare, merge=(405, 'User not allowed to merge PR'), admin=False, protected=True,
                 delete_lag=0, mergeable_after=1):
        self.bare, self.merge, self.calls = bare, merge, []
        self.pr_state, self.polls, self.deletes = 'open', 0, 0
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _go(self):
                n = int(self.headers.get('Content-Length') or 0)
                payload = json.loads(self.rfile.read(n)) if n else None
                outer.calls.append((self.command, self.path, self.headers.get('Authorization', ''), payload))
                root = '/api/v1/repos/' + REPO
                p = self.path
                code, body = 404, {}
                if p == root and self.command == 'GET':
                    code, body = 200, {'permissions': {'admin': admin}}
                elif p == root + '/branches/main':
                    code, body = 200, {'protected': protected, 'commit': {'id': git('--git-dir', str(bare), 'rev-parse', 'refs/heads/main')}}
                elif p.startswith(root + '/branches/agent'):
                    name = unquote(p.split('/branches/')[1])
                    if self.command == 'DELETE':
                        if outer.deletes < delete_lag:
                            outer.deletes += 1
                            code = 500
                        else:
                            subprocess.run(['git', '--git-dir', str(bare), 'update-ref', '-d', 'refs/heads/' + name])
                            code = 204
                    if self.command == 'GET' or code == 204:
                        found = subprocess.run(['git', '--git-dir', str(bare), 'show-ref', '--verify', 'refs/heads/' + name], capture_output=True)
                        code = 200 if found.returncode == 0 else 404
                elif p == root + '/pulls' and self.command == 'POST':
                    outer.head = payload['head']
                    code, body = 201, {'number': 4}
                elif p == root + '/pulls/4' and self.command == 'GET':
                    outer.polls += 1
                    code, body = 200, {'state': outer.pr_state, 'mergeable': outer.polls >= mergeable_after}
                elif p == root + '/pulls/4' and self.command == 'PATCH':
                    outer.pr_state = payload.get('state', outer.pr_state)
                    code, body = 201, {'state': outer.pr_state}
                elif p == root + '/pulls/4/merge':
                    code, body = outer.merge[0], ({'message': outer.merge[1]} if outer.merge[1] else {})
                    if code == 200:  # a misconfigured Gitea would merge
                        sha = git('--git-dir', str(bare), 'rev-parse', 'refs/heads/' + outer.head)
                        git('--git-dir', str(bare), 'update-ref', 'refs/heads/main', sha)
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            do_GET = do_POST = do_PATCH = do_DELETE = _go

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'

    def close(self):
        self.server.shutdown()


class MainRefusal(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bare = self.tmp / 'repo.git'
        git('init', '-q', '--bare', '-b', 'main', str(self.bare))
        seed = self.tmp / 'seed'
        git('init', '-q', '-b', 'main', str(seed))
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'base', cwd=seed)
        git('push', '-q', str(self.bare), 'main', cwd=seed)
        self.main0 = git('--git-dir', str(self.bare), 'rev-parse', 'main')
        self.hook(REFUSE_HOOK)

    def hook(self, text):
        h = self.bare / 'hooks' / 'pre-receive'
        h.write_text(text)
        h.chmod(0o755)

    def run_probe(self, api):
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        env.update(PROBE_GITEA_BASE=api.base, PROBE_REPO=REPO, PROBE_TOKEN=TOKEN, PROBE_GIT_URL='file://' + str(self.bare),
                   PROBE_IDENTITY='bifrost-mbp', PROBE_WAIT_SECONDS='0.05')
        try:
            return subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=120)
        finally:
            api.close()

    def assert_clean(self, result):
        self.assertNotIn(TOKEN, result.stdout + result.stderr)
        refs = git('--git-dir', str(self.bare), 'for-each-ref', 'refs/heads/agent')
        self.assertEqual(refs, '', result.stdout)

    def test_refused_push_and_merge_pass_and_clean_up(self):
        api = FakeGitea(self.bare, delete_lag=1, mergeable_after=3)
        r = self.run_probe(api)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('ok   bifrost/probe-repo main push: refused: protected branch', r.stdout)
        self.assertIn('ok   bifrost/probe-repo PR merge: HTTP 405; User not allowed to merge PR', r.stdout)
        self.assertIn('PR cleanup: #4 closed', r.stdout)
        self.assertIn('VERDICT PASS mode=main-refusal repo=bifrost/probe-repo identity=bifrost-mbp', r.stdout)
        self.assertEqual(git('--git-dir', str(self.bare), 'rev-parse', 'main'), self.main0)
        self.assertEqual(api.pr_state, 'closed')
        self.assert_clean(r)
        # Every API call carries the token as a header, never in the path.
        for method, path, auth, _ in api.calls:
            self.assertEqual(auth, 'token ' + TOKEN)
            self.assertNotIn(TOKEN, path)

    def test_an_accepted_push_reports_main_changed(self):
        self.hook('#!/bin/sh\nexit 0\n')
        api = FakeGitea(self.bare)
        r = self.run_probe(api)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn('FAIL bifrost/probe-repo main push: NOT refused', r.stdout)
        self.assertIn(f'MAIN CHANGED bifrost/probe-repo: was {self.main0}, now ', r.stdout)
        self.assertIn('VERDICT FAIL', r.stdout)
        self.assertNotIn('/pulls/4/merge', [c[1] for c in api.calls])
        self.assert_clean(r)

    def test_a_merge_that_goes_through_reports_main_changed(self):
        api = FakeGitea(self.bare, merge=(200, ''))
        r = self.run_probe(api)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn('FAIL bifrost/probe-repo PR merge: HTTP 200', r.stdout)
        self.assertIn('MAIN CHANGED', r.stdout)
        self.assert_clean(r)

    def test_other_refusals_are_not_permission_evidence(self):
        for merge in ((405, 'Please try again later'), (403, 'User not allowed to merge PR'), (405, ''), (409, 'conflict')):
            with self.subTest(merge=merge):
                self.setUp()
                api = FakeGitea(self.bare, merge=merge)
                r = self.run_probe(api)
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn('FAIL bifrost/probe-repo PR merge', r.stdout)
                self.assert_clean(r)

    def test_a_push_refused_for_another_reason_fails(self):
        self.hook('#!/bin/sh\necho "disk full" >&2\nexit 1\n')
        api = FakeGitea(self.bare)
        r = self.run_probe(api)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn('main push: NOT refused as expected', r.stdout)
        self.assert_clean(r)

    def test_unprotected_main_or_admin_stops_before_any_write(self):
        for kwargs in ({'protected': False}, {'admin': True}):
            with self.subTest(**kwargs):
                self.setUp()
                api = FakeGitea(self.bare, **kwargs)
                r = self.run_probe(api)
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn('STOP', r.stdout)
                self.assertFalse(any(c[0] in ('POST', 'PATCH', 'DELETE') for c in api.calls))
                self.assertEqual(git('--git-dir', str(self.bare), 'rev-parse', 'main'), self.main0)

    def test_never_mergeable_is_not_a_refusal(self):
        api = FakeGitea(self.bare, mergeable_after=10**6)
        r = self.run_probe(api)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn('never became mergeable', r.stdout)
        self.assertNotIn('/pulls/4/merge', [c[1] for c in api.calls])
        self.assert_clean(r)


if __name__ == '__main__':
    unittest.main()
