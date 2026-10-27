#!/usr/bin/env bash
# Writer checks tag refusal, temporary branch create/delete, PR create/close,
# and read-only main stability. It NEVER pushes or merges into main, even on
# the historical primary-probe repository. Main push/merge refusal remains
# UNVERIFIED; a writer PASS covers only the checks actually executed.
# PROBE_MODE=protection checks PATCH {} permission; reader also checks Git
# receive-pack, PR and tag permission. Both require PROBE_EXPECT_LOGIN.
# Tokens may come from PROBE_TOKEN / PROBE_SETUP_TOKEN in process memory or
# existing *_FILE inputs. No token or untrusted response is written/logged.
# Catchable exits clean temporary refs and PRs and verify the readback.
# SIGKILL, power loss and an unavailable server require manual reconciliation.
{ set +x; } 2> /dev/null
set -euo pipefail
ulimit -c 0
export LC_ALL=C NO_PROXY='*' no_proxy='*' GIT_TERMINAL_PROMPT=0
# Do not let inherited Git diagnostics log authorization headers.
for probe_env in $(compgen -v GIT_TRACE || true); do unset "${probe_env}"; done
unset GIT_CURL_VERBOSE GIT_CONFIG_PARAMETERS GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR
# Keep the script self-contained for the 06 SSH stdin transport.
# Embedded Python keeps `ssh ... bash -s < this-file` usable on 06.
case "${PROBE_MODE:-writer}" in
  writer) ;;
  reader|protection)
    python3 - <<'PY'
import base64
import http.client
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid


class ProbeError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'redirect refused', headers, fp)


base = os.environ.get('PROBE_GITEA', 'http://192.168.10.73:30300').rstrip('/')
api = os.environ.get('PROBE_API_BASE', base + '/api/v1').rstrip('/')
repo = os.environ.get('PROBE_REPO', 'bifrost/primary-probe')
mode = os.environ['PROBE_MODE']
login = os.environ.get('PROBE_EXPECT_LOGIN', '')
root = '/repos/' + repo
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
failed = False


def report(ok, check, detail):
    global failed
    failed |= not ok
    print(f'{"ok" if ok else "FAIL"} {repo} {login} {check}: {detail}', flush=True)


def token_file(name, default=''):
    try:
        value = os.environ.get(name.removesuffix('_FILE'))
        if value is None:
            value = Path(os.environ.get(name, default)).read_text().strip()
    except OSError:
        raise ProbeError('cannot read token file') from None
    if not value or '\n' in value or '\r' in value:
        raise ProbeError('empty or invalid token file')
    return value


def request(token, method, path, body=None, git=False, user=''):
    # Tests split file:// git transport from the local HTTP API/handshake.
    http_base = api.removesuffix('/api/v1') if 'PROBE_API_BASE' in os.environ else base
    url = http_base + path if git else api + path
    auth = 'token ' + token
    if git:
        auth = 'Basic ' + base64.b64encode(f'{user}:{token}'.encode()).decode()
    req = urllib.request.Request(url, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization': auth, 'Content-Type': 'application/json'})
    try:
        try:
            with opener.open(req, timeout=30) as response:
                code, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            with error:
                code, raw = error.code, error.read()
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError):
        # Also guard HTTPError.read(): protocol exceptions may contain raw
        # credential-bearing status lines, headers or partial response bodies.
        return 0, {}
    try:
        result = json.loads(raw)
    except ValueError:
        result = {'message': raw.decode(errors='replace').strip()} if git else {}
    return code, result if isinstance(result, dict) else {}


def require(ok, message):
    if not ok:
        raise ProbeError(message)


def identify(token, expected):
    code, body = request(token, 'GET', '/user')
    if code == 200 and body.get('login') == expected and body.get('is_admin') is False:
        return 'GET /user verified non-admin'
    accounts = {'agentd-agent-06-stg': 'bifrost-agentd-stg', 'agentd-agent-06': 'bifrost-agentd'}
    if (mode == 'protection' and os.environ.get('PROBE_IDENTITY_SOURCE') == 'installed-file'
            and code == 403 and 'required scope(s)' in body.get('message', '')
            and 'read:user' in body.get('message', '') and expected in accounts):
        account = pwd.getpwuid(os.geteuid())
        require(account.pw_name == accounts[expected], 'wrong Unix account')
        original = Path(account.pw_dir) / '.config/bifrost/agentd-git.token'
        require(token == original.read_text().strip(), 'token differs from installed credential')
        return 'installed-file/Unix-user provenance; GET /user lacks read:user'
    raise ProbeError(f'identity not verified as non-admin {expected} (HTTP {code})')


def denied(check, response):
    code, body = response
    message = body.get('message')
    # Exact, endpoint-specific Gitea 1.21.11 reasons. Never print raw bodies.
    acl = {
        'protection edit': 'user should be an owner or a collaborator with admin write of a repository',
        'tag create': 'user should have a permission to write to a repo',
    }
    scope = 'token does not have at least one of required scope(s): [write:repository]'
    # A generic "insufficient scope" does not identify the missing permission.
    # Git responses with no explicit write:repository reason stay unverified.
    known_scope = message == scope
    if code == 403 and known_scope and mode == 'reader':
        report(True, check, f'HTTP {code}; token scope; repository ACL unverified')
    elif code == 403 and check in acl and message == acl[check]:
        report(True, check, f'HTTP {code}; repository ACL denial')
    else:
        report(False, check, f'HTTP {code}; denial reason unverified')


def git_run(args, token, directory):
    # No inherited helper, header, URL rewrite, trace or repository selection.
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
               GIT_TERMINAL_PROMPT='0', GIT_CONFIG_COUNT='3',
               GIT_CONFIG_KEY_0=f'http.{base}/.extraHeader',
               GIT_CONFIG_VALUE_0='Authorization: token ' + token,
               GIT_CONFIG_KEY_1='http.followRedirects', GIT_CONFIG_VALUE_1='false',
               GIT_CONFIG_KEY_2='credential.helper', GIT_CONFIG_VALUE_2='')
    result = subprocess.run(['git', *args], cwd=directory, env=env,
                            capture_output=True, timeout=90)
    require(result.returncode == 0, 'fixture git command failed (output suppressed)')


def interrupted(signum, frame):
    raise ProbeError('interrupted; cleaning fixture')


signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)
branch = 'agent/_probe/' + uuid.uuid4().hex + '/a1'
tag = 'probe-' + uuid.uuid4().hex
fixture_started = tag_attempted = pr_attempted = False
reader_dir = ''
setup = token = ''
try:
    require(bool(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo)), 'invalid repository')
    require(bool(re.fullmatch(r'[A-Za-z0-9_.-]+', login)), 'PROBE_EXPECT_LOGIN required')
    token = token_file('PROBE_TOKEN_FILE', str(Path.home() / '.config/bifrost/agentd-git.token'))
    identity_source = identify(token, login)
    code, body = request(token, 'GET', root)
    require(code == 200 and body.get('mirror') is False and body.get('archived') is False,
            f'cannot read active regular repository (HTTP {code})')
    require(body.get('permissions', {}).get('admin') is False, 'repository admin or unknown permission')
    report(True, 'identity/read', identity_source + '; repository admin=false; HTTP 200')
    code, body = request(token, 'GET', root + '/branches/main')
    require(code == 200 and body.get('protected') is True, 'main is not verified protected')
    # Gitea 1.21 EditBranchProtection uses pointer/nil fields: {} leaves all
    # policy fields unchanged without concurrent edits. Server-side read/modify/
    # write can still race, update timestamps and trigger PR rechecks.
    denied('protection edit', request(token, 'PATCH', root + '/branch_protections/main', {}))
    if mode == 'reader':
        denied('push handshake', request(token, 'GET', '/' + repo + '.git/info/refs?service=git-receive-pack',
                                        git=True, user=login))
        setup = token_file('PROBE_SETUP_TOKEN_FILE')
        identify(setup, 'agentrt-landing-stg')
        # A real ahead-of-main branch prevents a nonexistent/same-head PR from
        # being mistaken for a permission denial. Setup never uses reader auth.
        # An explicit directory, removed in finally, so a failed removal is
        # reported with the path left behind (review 628 C1).
        reader_dir = tempfile.mkdtemp(prefix='p0-reader-')
        os.chmod(reader_dir, 0o700)
        git_run(['clone', '-q', '--branch', 'main', '--single-branch', base + '/' + repo + '.git', 'r'], setup, reader_dir)
        checkout = str(Path(reader_dir) / 'r')
        git_run(['-c', 'user.name=probe', '-c', 'user.email=probe@invalid',
                 'commit', '-q', '--allow-empty', '-m', 'P0 reader negative probe'], setup, checkout)
        fixture_started = True  # also clean up a lost push response
        git_run(['push', '-q', 'origin', 'HEAD:refs/heads/' + branch], setup, checkout)
        pr_attempted = True
        denied('PR open', request(token, 'POST', root + '/pulls',
               {'head': branch, 'base': 'main', 'title': 'P0 reader negative probe'}))
        tag_attempted = True
        denied('tag create', request(token, 'POST', root + '/tags',
               {'tag_name': tag, 'target': 'main'}))
except Exception:
    # Neither response bodies nor exceptions may echo credentials.
    report(False, 'precondition/execution', 'not verified; check identity, user Read scope, repository and fixture access')
finally:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if reader_dir:
        try:
            shutil.rmtree(reader_dir)
        except Exception:
            pass
        if os.path.exists(reader_dir):
            report(False, 'local cleanup', 'left behind ' + reader_dir + '; remove it by hand')
    if fixture_started:
        # Isolate each registered object: one failed lookup/readback must not
        # prevent cleanup of the remaining refs. Never log exception text.
        if pr_attempted:
            try:
                code, body = request(setup, 'GET', root + '/pulls/main/' + branch)
                if code == 200 and type(body.get('number')) is int and body['number'] > 0:
                    number = body['number']
                    closed, _ = request(setup, 'PATCH', root + f'/pulls/{number}', {'state': 'closed'})
                    status, state = request(setup, 'GET', root + f'/pulls/{number}')
                    report(closed in (200, 201) and status == 200 and state.get('state') == 'closed',
                           'PR cleanup', f'{branch}; PR #{number} closed readback; HTTP {closed}/{status}')
                else:
                    report(code == 404, 'PR cleanup', f'{branch} into main; lookup HTTP {code}; expected 404')
            except Exception:
                report(False, 'PR cleanup', f'not verified; inspect head {branch} into main')
        try:
            encoded = urllib.parse.quote(branch, safe='')
            deleted, _ = request(setup, 'DELETE', root + '/branches/' + encoded)
            code, _ = request(setup, 'GET', root + '/branches/' + encoded)
            report(deleted in (200, 204, 404) and code == 404, 'branch cleanup',
                   f'{branch}; delete HTTP {deleted}; readback HTTP {code}; expected 404')
        except Exception:
            report(False, 'branch cleanup', f'not verified; inspect refs/heads/{branch}')
        if tag_attempted:
            try:
                code, _ = request(setup, 'GET', root + '/tags/' + tag)
                if code not in (200, 404):
                    report(False, 'tag cleanup', f'{tag}; lookup HTTP {code}; absence not verified')
                if code != 404:
                    deleted, _ = request(setup, 'DELETE', root + '/tags/' + tag)
                    report(deleted in (200, 204, 404), 'tag cleanup', f'{tag}; delete HTTP {deleted}')
                    code, _ = request(setup, 'GET', root + '/tags/' + tag)
                report(code == 404, 'tag cleanup', f'{tag}; HTTP {code}; expected 404')
            except Exception:
                report(False, 'tag cleanup', f'not verified; inspect refs/tags/{tag}')
print(f'VERDICT {"FAIL" if failed else "PASS"} mode={mode} repo={repo} identity={login}')
raise SystemExit(int(failed))
PY
    exit $? ;;
  *) echo 'FAIL unsupported PROBE_MODE' >&2; exit 1 ;;
esac
BASE="${PROBE_GITEA:-http://192.168.10.73:30300}"
REPO="${PROBE_REPO:-bifrost/primary-probe}"
TOKEN_FILE="${PROBE_TOKEN_FILE:-$HOME/.config/bifrost/agentd-git.token}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
STAMP="${STAMP}-$$"
# S0 can reuse the same actual-refusal probe for the landing drill namespace.
case "${PROBE_BRANCH_PREFIX:-agent/_probe}" in
  agent/_probe|land/stg/_probe) ;;
  *) echo "probe: unsupported branch prefix" >&2; exit 1 ;;
esac
BRANCH="${PROBE_BRANCH_PREFIX:-agent/_probe}/${STAMP}/a1"
TAG="probe-${STAMP}"
URL="${BASE}/${REPO}.git"

if [[ -z "${PROBE_TOKEN+x}" ]]; then
  [[ -r "${TOKEN_FILE}" ]] || { echo "probe: cannot read ${TOKEN_FILE}" >&2; exit 1; }
  PROBE_TOKEN="$(tr -d '\r\n' < "${TOKEN_FILE}")"
fi
[[ -n "${PROBE_TOKEN}" ]] || { echo "probe: ${TOKEN_FILE} is empty" >&2; exit 1; }
# PROBE_API_BASE only for the tests, which serve git and the API from different places
export PROBE_TOKEN PROBE_API="${PROBE_API_BASE:-${BASE}/api/v1}"
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=3 \
  GIT_CONFIG_KEY_0="http.${BASE}/.extraHeader" GIT_CONFIG_VALUE_0="Authorization: token ${PROBE_TOKEN}" \
  GIT_CONFIG_KEY_1="http.followRedirects" GIT_CONFIG_VALUE_1="false" \
  GIT_CONFIG_KEY_2="credential.helper" GIT_CONFIG_VALUE_2=""

umask 077
work=""
fail=0
pr=""
pr_closed=0
branch_attempted=0
tag_attempted=0
pr_attempted=0
deleted=""

# api METHOD PATH JSON FIELD... — captured status and JSON fields only.
# Callers never log response fields. A redirect is refused; no proxy is used.
api() {
  python3 - "$@" << 'PY'
import http.client, json, os, sys, urllib.error, urllib.request
method, path, body, fields = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)
req = urllib.request.Request(os.environ["PROBE_API"] + path, method=method, data=body.encode() if body else None,
                             headers={"Authorization": "token " + os.environ["PROBE_TOKEN"], "Content-Type": "application/json"})
try:
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect).open(req, timeout=30) as r:
            code, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        with e:
            code, raw = e.code, e.read()
except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError):
    # Guard both success and error-body reads; never echo exception/response text.
    code, raw = 0, b"{}"
try:
    answer = json.loads(raw.decode() or "null")
except ValueError:
    answer = {}
if not isinstance(answer, dict):
    answer = {}
out = [str(code)] + [json.dumps(answer.get(f)) for f in fields]
print("\t".join(out))
PY
}

close_pr() {
  [[ -n "${pr}" && "${pr_closed}" -eq 0 ]] || return 0
  local closed code state
  IFS=$'\t' read -r closed _ <<< "$(api PATCH "/repos/${REPO}/pulls/${pr}" '{"state":"closed"}' state)" || true
  if [[ "${closed}" != 200 && "${closed}" != 201 ]]; then
    echo "FAIL  PR cleanup #${pr} from ${BRANCH}; close request HTTP ${closed:-none}; checking readback" >&2
    fail=1
  fi
  IFS=$'\t' read -r code state <<< "$(api GET "/repos/${REPO}/pulls/${pr}" "" state)" || true
  if [[ "${code}" == 200 && "${state}" == '"closed"' ]]; then
    pr_closed=1
  else
    echo "FAIL  close pull request #${pr} — still unverified (HTTP ${code:-none}); head ${BRANCH} into main; close it on the page" >&2
    fail=1
  fi
}

# Register before POST, then reconcile by unique base/head on EVERY exit path.
cleanup_pr() {
  [[ "${pr_attempted}" -eq 1 && "${pr_closed}" -eq 0 ]] || return 0
  local code number state
  if [[ -z "${pr}" ]]; then
    IFS=$'\t' read -r code number state <<< "$(api GET "/repos/${REPO}/pulls/main/${BRANCH}" "" number state)"
    if [[ "${code}" == 200 && "${number}" =~ ^[0-9]+$ ]]; then
      pr="${number}"
      [[ "${state}" == '"closed"' ]] && pr_closed=1
    elif [[ "${code}" == 404 ]]; then
      echo "ok    PR cleanup ${BRANCH}; lookup 404"
      return 0
    else
      echo "FAIL  PR cleanup ${BRANCH} into main; lookup HTTP ${code:-none}; inspect this head" >&2
      fail=1
      return 0
    fi
  fi
  close_pr
  [[ "${pr_closed}" -ne 1 ]] || echo "ok    PR cleanup #${pr} from ${BRANCH}; closed readback"
}

on_exit() {
  local rc=$? remaining lookup_failed=0
  trap '' INT TERM
  set +e
  cleanup_pr
  if [[ "${tag_attempted}" -eq 1 ]]; then
    if remaining="$(git ls-remote "${URL}" "refs/tags/${TAG}" 2>/dev/null)"; then
      if [[ -n "${remaining}" ]]; then
        echo "FAIL  tag cleanup refs/tags/${TAG}; unexpected tag exists; attempting deletion" >&2
        fail=1  # a lost creation response cannot hide an accepted tag
      fi
    else
      # Try deletion even if the first read fails; always verify afterwards.
      echo "FAIL  tag cleanup refs/tags/${TAG}; initial lookup failed; attempting deletion" >&2
      fail=1
      lookup_failed=1
    fi
    if [[ "${lookup_failed}" -eq 1 || -n "${remaining}" ]]; then
      git -C "${work}/r" push -q origin ":refs/tags/${TAG}" >/dev/null 2>&1 || {
        echo "FAIL  tag cleanup refs/tags/${TAG}; delete failed; checking absence" >&2
        fail=1
      }
    fi
    if remaining="$(git ls-remote "${URL}" "refs/tags/${TAG}" 2>/dev/null)" && [[ -z "${remaining}" ]]; then
      echo "ok    tag cleanup refs/tags/${TAG}"
    else
      echo "FAIL  tag cleanup refs/tags/${TAG}; absence not verified; inspect this tag" >&2
      fail=1
    fi
  fi
  if [[ "${branch_attempted}" -eq 1 && -z "${deleted}" ]]; then
    git -C "${work}/r" push -q origin ":refs/heads/${BRANCH}" > /dev/null 2>&1 || {
      echo "FAIL  exit cleanup refs/heads/${BRANCH}; delete failed; checking absence" >&2
      fail=1
    }
    if remaining="$(git ls-remote "${URL}" "refs/heads/${BRANCH}" 2>/dev/null)" && [[ -z "${remaining}" ]]; then
      echo "ok    exit cleanup ${BRANCH}"
    else
      echo "FAIL  exit cleanup ${BRANCH}; inspect this branch" >&2
      fail=1
    fi
  fi
  [[ -z "${work}" ]] || rm -rf "${work}" >/dev/null 2>&1 || {
    echo "FAIL local cleanup ${work}; directory may remain; inspect this path" >&2
    fail=1
  }
  [[ "${rc}" -ne 0 || "${fail}" -eq 0 ]] || rc=1
  if [[ "${rc}" -eq 0 ]]; then
    echo "VERDICT PASS mode=writer repo=${REPO} identity=${PROBE_EXPECT_LOGIN:-unspecified}"
  else
    echo "VERDICT FAIL mode=writer repo=${REPO} identity=${PROBE_EXPECT_LOGIN:-unspecified}"
  fi
  exit "${rc}"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
work="$(mktemp -d)"
chmod 700 "${work}"

report() { # <ok|FAIL> <what> <detail>
  printf '%-5s %s%s\n' "$1" "$2" "${3:+ — $3}"
  [[ "$1" == ok ]] || fail=1
}

# refused <what> <ref> <Gitea's words> <git push args…> — the push must be
# rejected for that ref, with Gitea's words for that rule
refused() {
  local what="$1" ref="$2" words="$3" out rc=0
  shift 3
  out="$(git -C "${work}/r" push --porcelain "$@" 2>&1)" || rc=$?
  if [[ "${rc}" -eq 0 ]]; then
    report FAIL "${what}" "Gitea accepted it"
  elif grep -qE "^!	[^	]*:${ref}	\[remote rejected\]" <<< "${out}" &&
    sed -n -e 's/^remote: Gitea: //p' <<< "${out}" | sed -e 's/[[:space:]]*$//' | grep -qxF -- "${words}"; then
    report ok "${what}" "refused: ${words}"
  else
    report FAIL "${what}" "refused, but not in the words of that rule (output suppressed)"
  fi
}

echo "== ${REPO} as $(id -un), ${STAMP}"
if [[ -n "${PROBE_EXPECT_LOGIN:-}" ]]; then
  IFS=$'\t' read -r code login admin <<< "$(api GET /user '' login is_admin)"
  [[ "${code}" == 200 && "${login}" == "\"${PROBE_EXPECT_LOGIN}\"" && "${admin}" == false ]] || {
    echo 'FAIL identity not verified; expected non-admin login and user Read scope' >&2
    exit 1
  }
  echo "ok identity ${PROBE_EXPECT_LOGIN} verified non-admin"
fi
IFS=$'\t' read -r code mirror <<< "$(api GET "/repos/${REPO}" "" mirror)"
[[ "${code}" == 200 ]] || { echo "probe: cannot read ${REPO} (HTTP ${code})" >&2; exit 1; }
case "${mirror}" in
  false) ;;
  true) echo "probe: ${REPO} is a mirror; the probe is for a regular repository" >&2; exit 1 ;;
  *) echo "probe: Gitea did not say whether ${REPO} is a mirror" >&2; exit 1 ;;
esac

git clone -q --branch main --single-branch "${URL}" "${work}/r" >/dev/null 2>&1 || { echo "probe: cannot clone ${REPO}" >&2; exit 1; }
git -C "${work}/r" -c user.name=probe -c user.email=probe@invalid commit -q --allow-empty -m "probe ${STAMP}"
main_before="$(git ls-remote "${URL}" refs/heads/main 2>/dev/null | cut -f1)"
[[ -n "${main_before}" ]] || exit 1
tags_before="$(git ls-remote --tags "${URL}" 2>/dev/null | cut -f2 | sort)"

echo "UNVERIFIED main push/merge: not attempted; no main write is permitted"
tag_attempted=1
refused "create tag ${TAG}" "refs/tags/${TAG}" "Tag ${TAG} is protected" origin "HEAD:refs/tags/${TAG}"
branch_attempted=1
if git -C "${work}/r" push -q origin "HEAD:refs/heads/${BRANCH}" >/dev/null 2>&1; then
  report ok "create ${BRANCH}"
else
  report FAIL "create ${BRANCH}" "push failed (output suppressed)"
  exit 1
fi

pr_attempted=1
IFS=$'\t' read -r code number <<< "$(api POST "/repos/${REPO}/pulls" "{\"head\":\"${BRANCH}\",\"base\":\"main\",\"title\":\"probe ${STAMP}\"}" number)"
if [[ "${code}" == 201 && "${number}" =~ ^[0-9]+$ ]]; then
  pr="${number}"
  cleanup_pr
  [[ "${pr_closed}" -eq 1 ]] && report ok "close pull request #${pr}"
else
  report FAIL "open a pull request from ${BRANCH}" "HTTP ${code}; response suppressed"
  cleanup_pr
fi

# agentd deletes attempt branches (TD-383): the deletion must go through.
if out="$(git -C "${work}/r" push --porcelain origin ":refs/heads/${BRANCH}" 2>&1)" &&
  remaining="$(git ls-remote "${URL}" "refs/heads/${BRANCH}" 2>/dev/null)" && [[ -z "${remaining}" ]]; then
  report ok "delete ${BRANCH}"
  deleted=1
else
  report FAIL "delete ${BRANCH}" "delete or readback failed (output suppressed)"
fi
main_after="$(git ls-remote "${URL}" refs/heads/main 2>/dev/null | cut -f1)" && [[ "${main_after}" == "${main_before}" ]] && report ok "main unchanged" || report FAIL "main unchanged" "main moved"
tags_after="$(git ls-remote --tags "${URL}" 2>/dev/null | cut -f2 | sort)" && [[ "${tags_after}" == "${tags_before}" ]] && report ok "no new tag" || report FAIL "no new tag" "the tags changed"

if [[ "${fail}" -eq 0 ]]; then
  echo "== all as expected; left behind: closed pull request #${pr}"
else
  echo "== NOT as expected: see FAIL lines and exit cleanup for ${BRANCH}${pr:+, pull request #${pr}}" >&2
fi
exit "${fail}"
