#!/usr/bin/env python3
"""P0-06 remainder: does Gitea refuse this identity a push to main and a PR merge into main?

Owner-run, one repository per invocation. With the token in PROBE_TOKEN (process
memory only) it:
  1. reads main's head and confirms main is protected and the identity is not a
     repository admin;
  2. builds one empty commit on top of main in a private temporary clone and
     pushes it to refs/heads/main: the push must be refused as a protected
     branch, and main must read back unchanged;
  3. pushes the same commit to a temporary agent/_probe/<id>/a1 branch, opens a
     pull request into main, waits until Gitea has computed it mergeable, and
     asks to merge it: the merge must be refused with HTTP 405 "User not
     allowed to merge PR", and main must read back unchanged;
  4. always closes the pull request and deletes the branch (retrying while
     Gitea's branch table catches up), and reads both back.

If main ever moves, it prints MAIN CHANGED with the old and new SHA and exits 2:
the only possible change is the one empty commit (or a merge of it), which the
Owner puts back. No token, response body or git output is printed.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = os.environ.get('PROBE_GITEA_BASE', 'http://192.168.10.73:30300').rstrip('/')
API = BASE + '/api/v1'
REPO = os.environ.get('PROBE_REPO', '')
GIT_URL = os.environ.get('PROBE_GIT_URL', BASE + '/' + REPO + '.git')
TOKEN = os.environ.pop('PROBE_TOKEN', '')
IDENTITY = os.environ.get('PROBE_IDENTITY', 'unspecified')
WAIT = float(os.environ.get('PROBE_WAIT_SECONDS', '2'))
PUSH_REFUSED = re.compile(r'not allowed to push to protected branch main', re.I)
MERGE_REFUSED = 'User not allowed to merge PR'
failures = []


def report(ok, check, detail):
    print(('ok   ' if ok else 'FAIL ') + f'{REPO} {check}: {detail}', flush=True)
    if not ok:
        failures.append(check)


class Stop(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'redirect refused', headers, fp)


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)


def request(method, path, body=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': 'token ' + TOKEN, 'Content-Type': 'application/json'})
    try:
        try:
            with OPENER.open(req, timeout=30) as r:
                code, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            with e:
                code, raw = e.code, e.read()
    except Exception:
        return 0, {}
    try:
        out = json.loads(raw) if raw else {}
    except ValueError:
        out = {}
    return code, out if isinstance(out, dict) else {}


def git(args, cwd):
    """Run git with the token as a header from the environment, never argv/URL."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0',
               GIT_CONFIG_COUNT='3',
               GIT_CONFIG_KEY_0='http.extraHeader',
               GIT_CONFIG_VALUE_0='Authorization: token ' + TOKEN,
               GIT_CONFIG_KEY_1='http.followRedirects', GIT_CONFIG_VALUE_1='false',
               GIT_CONFIG_KEY_2='credential.helper', GIT_CONFIG_VALUE_2='')
    r = subprocess.run(['git', *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
    return r.returncode, r.stderr


def main_head():
    code, body = request('GET', f'/repos/{REPO}/branches/main')
    if code != 200:
        raise Stop(f'cannot read main (HTTP {code})')
    sha = (body.get('commit') or {}).get('id', '')
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise Stop('main head unreadable')
    return sha, body.get('protected') is True


def interrupted(signum, frame):
    raise Stop('interrupted; cleaning up')


def run():
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', REPO) or not TOKEN:
        raise Stop('PROBE_REPO and PROBE_TOKEN are required')
    code, body = request('GET', f'/repos/{REPO}')
    if code != 200 or body.get('permissions', {}).get('admin') is not False:
        raise Stop(f'identity is a repository admin or permission unknown (HTTP {code})')
    main0, protected = main_head()
    if not protected:
        raise Stop('main is not protected: refusing to try a push')
    report(True, 'preflight', f'main {main0[:12]} protected; repository admin=false; identity={IDENTITY}')

    branch = 'agent/_probe/' + uuid.uuid4().hex + '/a1'
    work = tempfile.mkdtemp(prefix='p0-main-')
    os.chmod(work, 0o700)
    number = None
    branch_pushed = False
    try:
        rc, _ = git(['clone', '-q', '--depth', '1', '--branch', 'main', '--single-branch', GIT_URL, 'r'], work)
        if rc:
            raise Stop('clone failed (output suppressed)')
        repo_dir = os.path.join(work, 'r')
        rc, _ = git(['-c', 'user.name=p0-probe', '-c', 'user.email=p0-probe@invalid',
                     'commit', '-q', '--allow-empty', '-m', 'P0-06 probe: this push to main must be refused'], repo_dir)
        if rc:
            raise Stop('local empty commit failed')

        # 1. Push to main: must be refused as a protected branch.
        rc, err = git(['push', '-q', 'origin', 'HEAD:refs/heads/main'], repo_dir)
        refused = rc != 0 and bool(PUSH_REFUSED.search(err))
        main1, _ = main_head()
        report(refused, 'main push', 'refused: protected branch' if refused else
               f'NOT refused as expected (exit {rc}; reason {"matched" if PUSH_REFUSED.search(err) else "unrecognised"})')
        if main1 != main0:
            print(f'MAIN CHANGED {REPO}: was {main0}, now {main1}', flush=True)
            return 2
        report(True, 'main unchanged after push', main0[:12])

        # 2. Branch + PR + merge: the merge must be refused.
        rc, _ = git(['push', '-q', 'origin', 'HEAD:refs/heads/' + branch], repo_dir)
        branch_pushed = True  # clean up a lost answer too
        if rc:
            raise Stop('probe branch push failed (output suppressed)')
        code, body = request('POST', f'/repos/{REPO}/pulls',
                             {'base': 'main', 'head': branch, 'title': 'P0-06 probe: merge must be refused',
                              'body': 'Temporary pull request of the P0-06 probe; closed by the probe.'})
        if code != 201 or not isinstance(body.get('number'), int):
            raise Stop(f'cannot open the probe pull request (HTTP {code})')
        number = body['number']
        mergeable = None
        for _ in range(30):
            code, pr = request('GET', f'/repos/{REPO}/pulls/{number}')
            mergeable = pr.get('mergeable') if code == 200 else None
            if mergeable is True:
                break
            time.sleep(WAIT / 2)
        if mergeable is not True:
            raise Stop('pull request never became mergeable; a refusal now would not prove permission')
        code, body = request('POST', f'/repos/{REPO}/pulls/{number}/merge', {'Do': 'merge'})
        refused = code == 405 and body.get('message') == MERGE_REFUSED
        main2, _ = main_head()
        report(refused, 'PR merge', f'HTTP {code}; ' + ('User not allowed to merge PR' if refused else 'not the permission refusal'))
        if main2 != main0:
            print(f'MAIN CHANGED {REPO}: was {main0}, now {main2}', flush=True)
            return 2
        report(True, 'main unchanged after merge', main0[:12])
        return 0
    finally:
        if number is not None:
            closed, _ = request('PATCH', f'/repos/{REPO}/pulls/{number}', {'state': 'closed'})
            code, pr = request('GET', f'/repos/{REPO}/pulls/{number}')
            report(code == 200 and pr.get('state') == 'closed', 'PR cleanup', f'#{number} closed; HTTP {closed}/{code}')
        if branch_pushed:
            encoded = urllib.parse.quote(branch, safe='')
            attempts, code = 0, 0
            while attempts < 10:
                attempts += 1
                request('DELETE', f'/repos/{REPO}/branches/{encoded}')
                code, _ = request('GET', f'/repos/{REPO}/branches/{encoded}')
                if code == 404:
                    break
                time.sleep(WAIT)
            report(code == 404, 'branch cleanup', f'{branch}; readback HTTP {code} after {attempts} attempt(s)')
        try:
            shutil.rmtree(work)
        except OSError:
            report(False, 'local cleanup', 'left behind ' + work + '; remove it by hand')


def entry():
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        rc = run()
    except Stop as e:
        print(f'STOP {REPO}: {e}', flush=True)
        rc = 1
    if rc == 0 and failures:
        rc = 1
    print(f'VERDICT {"PASS" if rc == 0 else "FAIL"} mode=main-refusal repo={REPO} identity={IDENTITY}', flush=True)
    return rc


if __name__ == '__main__':
    sys.exit(entry())
