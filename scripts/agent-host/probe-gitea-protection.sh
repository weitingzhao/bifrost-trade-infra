#!/usr/bin/env bash
# probe-gitea-protection.sh — runs on 06 as bifrost-agentd-stg (Gitea user
# agentd-agent-06-stg, team agentd-write), sent there by
# `agent-06-owner.sh probe-protection`. It checks the rules of the probe
# repository bifrost/primary-probe the way agentd will meet them once Gitea is
# the primary (CUT-gitea-primary-2026-10-17 §5 「第 1 步」 4;
# OWNER-STEPS-gitea-primary.md §1):
#
#   refused  a push to main; a tag; a pull request merged into main
#   allowed  creating agent/_probe/<stamp>/a1, and deleting it once its pull
#            request is closed (TD-383, Owner 10-20 「分支 B 用 agentd」:
#            agent/** is no longer protected; agentd deletes attempt branches
#            under the runtime's rule, so a refused deletion fails the probe)
#
# A refusal counts only as Gitea 1.21 words it for that rule and that ref
# (review 254 A3, 255 C): the push is rejected for that ref (git push
# --porcelain) and one line from Gitea's hook is, word for word, "Not allowed
# to push to protected branch main", "Tag <tag> is protected", "branch <b> is
# protected from ...". The merge is tried only
# once Gitea says the pull request can be merged, and counts as refused only on
# HTTP 405 with the message "User not allowed to merge PR" (review 254 A1). Anything else is reported as
# not recognised and fails the probe: a person looks, it is not a pass. Main
# and the tags are read again at the end.
#
# What is left behind: a closed pull request (and the branch, when its
# deletion is refused, which fails the probe). A pull request the
# probe opened is closed on every way out, and the closing is read back
# (review 254 B4).
#
# The user's own Gitea token is read from its file into this shell; it goes
# only to Gitea, in a header (git: config from the environment, scoped to the
# Gitea host; the API: python), through no proxy and no redirect, and is never
# printed. Exits 1 on any unexpected or unrecognised answer.
#
# S0 optional modes (default remains writer): PROBE_MODE=protection sends
# PATCH {} to main's protection; PROBE_MODE=reader also tests receive-pack,
# PR creation and tag creation refusals. Both require PROBE_EXPECT_LOGIN.
# Reader additionally requires PROBE_SETUP_TOKEN_FILE for the drill identity
# to prepare/clean its temporary branch. Every mode ends with VERDICT.
# user Read verifies login where available. 06 repository-only tokens can
# explicitly use installed-file provenance under their matching Unix user.
{ set +x; } 2> /dev/null
set -euo pipefail
export LC_ALL=C NO_PROXY='*' no_proxy='*' GIT_TERMINAL_PROMPT=0
# Do not let inherited Git diagnostics log authorization headers.
for probe_env in $(compgen -v GIT_TRACE || true); do unset "${probe_env}"; done
unset GIT_CURL_VERBOSE GIT_CONFIG_PARAMETERS GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR
# Optional S0 checks are separate from the historical eight-check default.
# Embedded Python keeps `ssh ... bash -s < this-file` usable on 06.
case "${PROBE_MODE:-writer}" in
  writer) ;;
  reader|protection)
    python3 - <<'PY'
import base64
import json
import os
from pathlib import Path
import pwd
import re
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
        with opener.open(req, timeout=30) as response:
            code, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        code, raw = error.code, error.read()
    except (urllib.error.URLError, OSError):
        return 0, {}
    try:
        result = json.loads(raw)
    except ValueError:
        result = {}
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


def denied(check, code):
    report(code in (401, 403), check, f'HTTP {code}; expected 401/403')


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
    # policy fields unchanged, even if permission is accidentally granted.
    # Unlike replaying a stale snapshot this cannot overwrite concurrent edits.
    denied('protection edit', request(token, 'PATCH', root + '/branch_protections/main', {})[0])
    if mode == 'reader':
        denied('push handshake', request(token, 'GET', '/' + repo + '.git/info/refs?service=git-receive-pack',
                                        git=True, user=login)[0])
        setup = token_file('PROBE_SETUP_TOKEN_FILE')
        identify(setup, 'agentrt-landing-stg')
        # A real ahead-of-main branch prevents a nonexistent/same-head PR from
        # being mistaken for a permission denial. Setup never uses reader auth.
        with tempfile.TemporaryDirectory(prefix='p0-reader-') as work:
            os.chmod(work, 0o700)
            git_run(['clone', '-q', '--branch', 'main', '--single-branch', base + '/' + repo + '.git', 'r'], setup, work)
            checkout = str(Path(work) / 'r')
            git_run(['-c', 'user.name=probe', '-c', 'user.email=probe@invalid',
                     'commit', '-q', '--allow-empty', '-m', 'P0 reader negative probe'], setup, checkout)
            fixture_started = True  # also clean up a lost push response
            git_run(['push', '-q', 'origin', 'HEAD:refs/heads/' + branch], setup, checkout)
        pr_attempted = True
        denied('PR open', request(token, 'POST', root + '/pulls',
               {'head': branch, 'base': 'main', 'title': 'P0 reader negative probe'})[0])
        tag_attempted = True
        denied('tag create', request(token, 'POST', root + '/tags',
               {'tag_name': tag, 'target': 'main'})[0])
except (ProbeError, OSError, subprocess.SubprocessError):
    # Neither response bodies nor exceptions may echo credentials.
    report(False, 'precondition/execution', 'not verified; check identity, user Read scope, repository and fixture access')
finally:
    if fixture_started:
        try:
            if pr_attempted:
                code, body = request(setup, 'GET', root + '/pulls/main/' + branch)
                if code == 200 and isinstance(body.get('number'), int):
                    number = body['number']
                    request(setup, 'PATCH', root + f'/pulls/{number}', {'state': 'closed'})
                    status, state = request(setup, 'GET', root + f'/pulls/{number}')
                    report(status == 200 and state.get('state') == 'closed', 'PR cleanup', f'PR #{number} closed readback')
                else:
                    report(code == 404, 'PR cleanup', f'lookup HTTP {code}; expected 404')
            encoded = urllib.parse.quote(branch, safe='')
            request(setup, 'DELETE', root + '/branches/' + encoded)
            code, _ = request(setup, 'GET', root + '/branches/' + encoded)
            report(code == 404, 'branch cleanup', f'{branch}; HTTP {code}; expected 404')
            if tag_attempted:
                code, _ = request(setup, 'GET', root + '/tags/' + tag)
                if code == 200:
                    request(setup, 'DELETE', root + '/tags/' + tag)
                    code, _ = request(setup, 'GET', root + '/tags/' + tag)
                report(code == 404, 'tag cleanup', f'{tag}; HTTP {code}; expected 404')
        except (OSError, ValueError):
            report(False, 'cleanup', f'not verified; inspect {branch} and {tag}')
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
MERGEABLE_WAIT="${PROBE_MERGEABLE_WAIT:-30}"

[[ -r "${TOKEN_FILE}" ]] || { echo "probe: cannot read ${TOKEN_FILE}" >&2; exit 1; }
PROBE_TOKEN="$(tr -d '\r\n' < "${TOKEN_FILE}")"
[[ -n "${PROBE_TOKEN}" ]] || { echo "probe: ${TOKEN_FILE} is empty" >&2; exit 1; }
# PROBE_API_BASE only for the tests, which serve git and the API from different places
export PROBE_TOKEN PROBE_API="${PROBE_API_BASE:-${BASE}/api/v1}"
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=3 \
  GIT_CONFIG_KEY_0="http.${BASE}/.extraHeader" GIT_CONFIG_VALUE_0="Authorization: token ${PROBE_TOKEN}" \
  GIT_CONFIG_KEY_1="http.followRedirects" GIT_CONFIG_VALUE_1="false" \
  GIT_CONFIG_KEY_2="credential.helper" GIT_CONFIG_VALUE_2=""

work="$(mktemp -d)"
chmod 700 "${work}"
fail=0
pr=""
pr_closed=0
branch_attempted=0
deleted=""

# api METHOD PATH JSON FIELD... — one line: the HTTP status, then each named
# top-level field of the answer as JSON (message: as plain text on one line),
# tab-separated; a field the answer does not have is "null". The whole answer is parsed; only an error's message is cut
# for reading. A redirect is refused; no proxy is used.
api() {
  python3 - "$@" << 'PY'
import json, os, sys, urllib.error, urllib.request
method, path, body, fields = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)
req = urllib.request.Request(os.environ["PROBE_API"] + path, method=method, data=body.encode() if body else None,
                             headers={"Authorization": "token " + os.environ["PROBE_TOKEN"], "Content-Type": "application/json"})
try:
    with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect).open(req, timeout=30) as r:
        code, raw = r.status, r.read()
except urllib.error.HTTPError as e:
    code, raw = e.code, e.read()
except (urllib.error.URLError, OSError) as e:
    code, raw = 0, json.dumps({"message": str(e)}).encode()
try:
    answer = json.loads(raw.decode() or "null")
except ValueError:
    answer = {"message": raw.decode(errors="replace")}
if not isinstance(answer, dict):
    answer = {}
out = [str(code)] + [json.dumps(answer.get(f)) for f in fields]
if "message" in fields:  # plain text for reading, on one line
    out[1 + fields.index("message")] = " ".join(str(answer.get("message") or "").replace(os.environ["PROBE_TOKEN"], "[redacted]").split())[:300]
print("\t".join(out))
PY
}

close_pr() {
  [[ -n "${pr}" && "${pr_closed}" -eq 0 ]] || return 0
  local code state
  IFS=$'\t' read -r code _ <<< "$(api PATCH "/repos/${REPO}/pulls/${pr}" '{"state":"closed"}' state)" || true
  IFS=$'\t' read -r code state <<< "$(api GET "/repos/${REPO}/pulls/${pr}" "" state)" || true
  if [[ "${code}" == 200 && "${state}" == '"closed"' ]]; then
    pr_closed=1
  else
    echo "FAIL  close pull request #${pr} — still ${state:-unknown} (HTTP ${code:-none}); close it on the page" >&2
    fail=1
  fi
}

on_exit() {
  local rc=$?
  set +e
  close_pr
  if [[ "${branch_attempted}" -eq 1 && -z "${deleted}" ]]; then
    git -C "${work}/r" push -q origin ":refs/heads/${BRANCH}" > /dev/null 2>&1
    if remaining="$(git ls-remote "${URL}" "refs/heads/${BRANCH}" 2>/dev/null)" && [[ -z "${remaining}" ]]; then
      echo "ok    exit cleanup ${BRANCH}"
    else
      echo "FAIL  exit cleanup ${BRANCH}; inspect this branch" >&2
      fail=1
    fi
  fi
  rm -rf "${work}"
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
    report FAIL "${what}" "refused, but not in the words of that rule: $(grep -E '^(remote: |!	|error: |fatal: )' <<< "${out}" | head -n 2 | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
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

git clone -q "${URL}" "${work}/r" || { echo "probe: cannot clone ${REPO}" >&2; exit 1; }
git -C "${work}/r" -c user.name=probe -c user.email=probe@invalid commit -q --allow-empty -m "probe ${STAMP}"
main_before="$(git ls-remote "${URL}" refs/heads/main | cut -f1)"
tags_before="$(git ls-remote --tags "${URL}" | cut -f2 | sort)"

refused "push to main" "refs/heads/main" "Not allowed to push to protected branch main" origin "HEAD:refs/heads/main"
refused "create tag ${TAG}" "refs/tags/${TAG}" "Tag ${TAG} is protected" origin "HEAD:refs/tags/${TAG}"
branch_attempted=1
if git -C "${work}/r" push -q origin "HEAD:refs/heads/${BRANCH}" 2> "${work}/err"; then
  report ok "create ${BRANCH}"
else
  report FAIL "create ${BRANCH}" "$(tail -n 1 "${work}/err")"
fi

IFS=$'\t' read -r code number message <<< "$(api POST "/repos/${REPO}/pulls" "{\"head\":\"${BRANCH}\",\"base\":\"main\",\"title\":\"probe ${STAMP}\"}" number message)"
if [[ "${code}" == 201 && "${number}" =~ ^[0-9]+$ ]]; then
  pr="${number}"
  mergeable=null
  for _ in $(seq 1 "${MERGEABLE_WAIT}"); do
    IFS=$'\t' read -r code mergeable <<< "$(api GET "/repos/${REPO}/pulls/${pr}" "" mergeable)"
    [[ "${code}" == 200 && "${mergeable}" == true ]] && break
    sleep 1
  done
  if [[ "${mergeable}" != true ]]; then
    report FAIL "merge pull request #${pr} into main" "Gitea never said it can be merged (mergeable ${mergeable}); the rule was not tried"
  else
    IFS=$'\t' read -r code message <<< "$(api POST "/repos/${REPO}/pulls/${pr}/merge" '{"Do":"merge"}' message)"
    case "${code}" in
      200 | 204) report FAIL "merge pull request #${pr} into main" "Gitea merged it" ;;
      405)
        if [[ "${message}" == "User not allowed to merge PR" ]]; then
          report ok "merge pull request #${pr} into main" "refused: ${message}"
        else
          report FAIL "merge pull request #${pr} into main" "HTTP 405 for another reason: ${message}"
        fi ;;
      *) report FAIL "merge pull request #${pr} into main" "not recognised: HTTP ${code} ${message}" ;;
    esac
  fi
  close_pr
  [[ "${pr_closed}" -eq 1 ]] && report ok "close pull request #${pr}"
else
  report FAIL "open a pull request from ${BRANCH}" "HTTP ${code} ${message:-}"
  # Gitea may have opened it all the same (the answer lost on the way): look it up by base and head, close it
  IFS=$'\t' read -r code number state <<< "$(api GET "/repos/${REPO}/pulls/main/${BRANCH}" "" number state)"
  if [[ "${code}" == 200 && "${number}" =~ ^[0-9]+$ ]]; then
    pr="${number}"
    [[ "${state}" == '"closed"' ]] && pr_closed=1
    close_pr
    [[ "${pr_closed}" -eq 1 ]] && echo "(pull request #${pr} from ${BRANCH} was there after all; it is closed)"
  elif [[ "${code}" != 404 ]]; then
    echo "FAIL  there may be an open pull request from ${BRANCH} into main (lookup: HTTP ${code}); look on the page" >&2
  fi
fi

# agentd deletes attempt branches (TD-383): the deletion must go through.
if out="$(git -C "${work}/r" push --porcelain origin ":refs/heads/${BRANCH}" 2>&1)" &&
  [[ -z "$(git ls-remote "${URL}" "refs/heads/${BRANCH}")" ]]; then
  report ok "delete ${BRANCH}"
  deleted=1
else
  report FAIL "delete ${BRANCH}" "$(grep -E '^(remote: |!	|error: |fatal: )' <<< "${out}" | head -n 2 | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
fi
[[ "$(git ls-remote "${URL}" refs/heads/main | cut -f1)" == "${main_before}" ]] && report ok "main unchanged" || report FAIL "main unchanged" "main moved"
[[ "$(git ls-remote --tags "${URL}" | cut -f2 | sort)" == "${tags_before}" ]] && report ok "no new tag" || report FAIL "no new tag" "the tags changed"

if [[ "${fail}" -eq 0 ]]; then
  echo "== all as expected; left behind: closed pull request #${pr}"
else
  echo "== NOT as expected: see the FAIL lines; left behind: ${deleted:+no branch}${deleted:-${BRANCH}}${pr:+, pull request #${pr}}" >&2
fi
exit "${fail}"
