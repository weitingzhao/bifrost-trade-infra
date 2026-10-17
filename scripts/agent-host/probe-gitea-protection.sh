#!/usr/bin/env bash
# probe-gitea-protection.sh — runs on 06 as bifrost-agentd-stg (Gitea user
# agentd-agent-06-stg, team agentd-write), sent there by
# `agent-06-owner.sh probe-protection`. It checks the rules of the probe
# repository bifrost/primary-probe the way agentd will meet them once Gitea is
# the primary (CUT-gitea-primary-2026-10-17 §5 「第 1 步」 4;
# OWNER-STEPS-gitea-primary.md §1):
#
#   refused  a push to main; a tag; a pull request merged into main; a forced
#            push to its own agent/ branch; deleting that branch
#   allowed  creating agent/_probe/<stamp>/a1
#
# A refused push counts only when Gitea says the branch or tag is protected
# (its messages for main, a tag, a forced push and a delete all say so); a
# refusal for any other reason fails the probe. A merge counts as refused on
# HTTP 403 or 405. Main and the tags are read again at the end. What is left
# behind: the branch agent/_probe/<stamp>/a1 (agentd cannot delete it; the
# Owner may) and a closed pull request.
#
# The user's own Gitea token is read from its file into this shell; it goes
# only to Gitea, in a header (git: config from the environment, scoped to the
# Gitea host; the API: python), through no proxy and no redirect, and is never
# printed. Exits 1 on any unexpected answer.
{ set +x; } 2> /dev/null
set -euo pipefail
export LC_ALL=C NO_PROXY='*' no_proxy='*' GIT_TERMINAL_PROMPT=0
BASE="${PROBE_GITEA:-http://192.168.10.73:30300}"
REPO="${PROBE_REPO:-bifrost/primary-probe}"
TOKEN_FILE="${PROBE_TOKEN_FILE:-$HOME/.config/bifrost/agentd-git.token}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BRANCH="agent/_probe/${STAMP}/a1"
TAG="probe-${STAMP}"
URL="${BASE}/${REPO}.git"

[[ -r "${TOKEN_FILE}" ]] || { echo "probe: cannot read ${TOKEN_FILE}" >&2; exit 1; }
PROBE_TOKEN="$(tr -d '\r\n' < "${TOKEN_FILE}")"
[[ -n "${PROBE_TOKEN}" ]] || { echo "probe: ${TOKEN_FILE} is empty" >&2; exit 1; }
# PROBE_API_BASE only for the tests, which serve git and the API from different places
export PROBE_TOKEN PROBE_API="${PROBE_API_BASE:-${BASE}/api/v1}"
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=2 \
  GIT_CONFIG_KEY_0="http.${BASE}/.extraHeader" GIT_CONFIG_VALUE_0="Authorization: token ${PROBE_TOKEN}" \
  GIT_CONFIG_KEY_1="http.followRedirects" GIT_CONFIG_VALUE_1="false"

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT
fail=0

# api METHOD PATH [JSON] — prints "<status> <body>"; a redirect is refused
api() {
  python3 - "$1" "$2" "${3:-}" << 'PY'
import os, sys, urllib.error, urllib.request
method, path, body = sys.argv[1], sys.argv[2], sys.argv[3]
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)
req = urllib.request.Request(os.environ["PROBE_API"] + path, method=method, data=body.encode() if body else None,
                             headers={"Authorization": "token " + os.environ["PROBE_TOKEN"], "Content-Type": "application/json"})
try:
    with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect).open(req, timeout=30) as r:
        print(r.status, r.read().decode()[:2000])
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode()[:2000])
except (urllib.error.URLError, OSError) as e:
    print(0, str(e))
PY
}

report() { # <ok|FAIL> <what> <detail>
  printf '%-5s %s%s\n' "$1" "$2" "${3:+ — $3}"
  [[ "$1" == ok ]] || fail=1
}

# refused <what> <git push args…> — the push must fail because of a protection rule
refused() {
  local what="$1" out rc=0
  shift
  out="$(git -C "${work}/r" push "$@" 2>&1)" || rc=$?
  if [[ "${rc}" -eq 0 ]]; then
    report FAIL "${what}" "Gitea accepted it"
  elif grep -qi 'protected' <<< "${out}"; then
    report ok "${what}" "refused: $(grep -i 'protected' <<< "${out}" | head -n 1 | sed -e 's/^remote: *//' -e 's/[[:space:]]*$//')"
  else
    report FAIL "${what}" "refused, but not by a rule: $(tail -n 1 <<< "${out}")"
  fi
}

echo "== ${REPO} as $(id -un), ${STAMP}"
read -r code body <<< "$(api GET "/repos/${REPO}")"
[[ "${code}" == 200 ]] || { echo "probe: cannot read ${REPO} (HTTP ${code})" >&2; exit 1; }
[[ "$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read()).get("mirror"))' <<< "${body}")" == False ]] ||
  { echo "probe: ${REPO} is a mirror; the probe is for a regular repository" >&2; exit 1; }

git clone -q "${URL}" "${work}/r" || { echo "probe: cannot clone ${REPO}" >&2; exit 1; }
git -C "${work}/r" -c user.name=probe -c user.email=probe@invalid commit -q --allow-empty -m "probe ${STAMP}"
main_before="$(git ls-remote "${URL}" refs/heads/main | cut -f1)"
tags_before="$(git ls-remote --tags "${URL}" | cut -f2 | sort)"

refused "push to main" -q origin "HEAD:refs/heads/main"
refused "create tag ${TAG}" -q origin "HEAD:refs/tags/${TAG}"
if git -C "${work}/r" push -q origin "HEAD:refs/heads/${BRANCH}" 2> "${work}/err"; then
  report ok "create ${BRANCH}"
else
  report FAIL "create ${BRANCH}" "$(tail -n 1 "${work}/err")"
fi
git -C "${work}/r" -c user.name=probe -c user.email=probe@invalid commit -q --amend --allow-empty -m "probe ${STAMP} rewritten"
refused "force-push ${BRANCH}" -q --force origin "HEAD:refs/heads/${BRANCH}"
refused "delete ${BRANCH}" -q origin ":refs/heads/${BRANCH}"

read -r code body <<< "$(api POST "/repos/${REPO}/pulls" "{\"head\":\"${BRANCH}\",\"base\":\"main\",\"title\":\"probe ${STAMP}\"}")"
if [[ "${code}" == 201 ]]; then
  index="$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["number"])' <<< "${body}")"
  read -r code body <<< "$(api POST "/repos/${REPO}/pulls/${index}/merge" '{"Do":"merge"}')"
  case "${code}" in
    403 | 405) report ok "merge pull request #${index} into main" "refused (HTTP ${code})" ;;
    200 | 204) report FAIL "merge pull request #${index} into main" "Gitea merged it" ;;
    *) report FAIL "merge pull request #${index} into main" "HTTP ${code}: ${body:0:200}" ;;
  esac
  read -r code _ <<< "$(api PATCH "/repos/${REPO}/pulls/${index}" '{"state":"closed"}')"
  [[ "${code}" == 201 || "${code}" == 200 ]] || echo "(could not close pull request #${index}: HTTP ${code}; close it on the page)"
else
  report FAIL "open a pull request from ${BRANCH}" "HTTP ${code}: ${body:0:200}"
fi

[[ "$(git ls-remote "${URL}" refs/heads/main | cut -f1)" == "${main_before}" ]] && report ok "main unchanged" || report FAIL "main unchanged" "main moved"
[[ "$(git ls-remote --tags "${URL}" | cut -f2 | sort)" == "${tags_before}" ]] && report ok "no new tag" || report FAIL "no new tag" "the tags changed"

if [[ "${fail}" -eq 0 ]]; then
  echo "== all as expected; left behind: ${BRANCH} and a closed pull request"
else
  echo "== NOT as expected: see the FAIL lines" >&2
fi
exit "${fail}"
