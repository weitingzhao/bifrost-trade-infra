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
# A refusal counts only as Gitea 1.21 words it for that rule and that ref
# (review 254 A3, 255 C): the push is rejected for that ref (git push
# --porcelain) and one line from Gitea's hook is, word for word, "Not allowed
# to push to protected branch main", "Tag <tag> is protected", "branch <b> is
# protected from force push" or "... from deletion". The merge is tried only
# once Gitea says the pull request can be merged, and counts as refused only on
# HTTP 405 with the message "User not allowed to merge PR" (review 254 A1). Anything else is reported as
# not recognised and fails the probe: a person looks, it is not a pass. Main
# and the tags are read again at the end.
#
# What is left behind: the branch agent/_probe/<stamp>/a1 (agentd cannot
# delete it; the Owner may) and a closed pull request. A pull request the
# probe opened is closed on every way out, and the closing is read back
# (review 254 B4).
#
# The user's own Gitea token is read from its file into this shell; it goes
# only to Gitea, in a header (git: config from the environment, scoped to the
# Gitea host; the API: python), through no proxy and no redirect, and is never
# printed. Exits 1 on any unexpected or unrecognised answer.
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
MERGEABLE_WAIT="${PROBE_MERGEABLE_WAIT:-30}"

[[ -r "${TOKEN_FILE}" ]] || { echo "probe: cannot read ${TOKEN_FILE}" >&2; exit 1; }
PROBE_TOKEN="$(tr -d '\r\n' < "${TOKEN_FILE}")"
[[ -n "${PROBE_TOKEN}" ]] || { echo "probe: ${TOKEN_FILE} is empty" >&2; exit 1; }
# PROBE_API_BASE only for the tests, which serve git and the API from different places
export PROBE_TOKEN PROBE_API="${PROBE_API_BASE:-${BASE}/api/v1}"
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=2 \
  GIT_CONFIG_KEY_0="http.${BASE}/.extraHeader" GIT_CONFIG_VALUE_0="Authorization: token ${PROBE_TOKEN}" \
  GIT_CONFIG_KEY_1="http.followRedirects" GIT_CONFIG_VALUE_1="false"

work="$(mktemp -d)"
fail=0
pr=""
pr_closed=0

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
    out[1 + fields.index("message")] = " ".join(str(answer.get("message") or "").split())[:300]
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
  rm -rf "${work}"
  [[ "${rc}" -ne 0 || "${fail}" -eq 0 ]] || rc=1
  exit "${rc}"
}
trap on_exit EXIT

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
if git -C "${work}/r" push -q origin "HEAD:refs/heads/${BRANCH}" 2> "${work}/err"; then
  report ok "create ${BRANCH}"
else
  report FAIL "create ${BRANCH}" "$(tail -n 1 "${work}/err")"
fi
git -C "${work}/r" -c user.name=probe -c user.email=probe@invalid commit -q --amend --allow-empty -m "probe ${STAMP} rewritten"
refused "force-push ${BRANCH}" "refs/heads/${BRANCH}" "branch ${BRANCH} is protected from force push" --force origin "HEAD:refs/heads/${BRANCH}"
refused "delete ${BRANCH}" "refs/heads/${BRANCH}" "branch ${BRANCH} is protected from deletion" origin ":refs/heads/${BRANCH}"

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

[[ "$(git ls-remote "${URL}" refs/heads/main | cut -f1)" == "${main_before}" ]] && report ok "main unchanged" || report FAIL "main unchanged" "main moved"
[[ "$(git ls-remote --tags "${URL}" | cut -f2 | sort)" == "${tags_before}" ]] && report ok "no new tag" || report FAIL "no new tag" "the tags changed"

if [[ "${fail}" -eq 0 ]]; then
  echo "== all as expected; left behind: ${BRANCH} and closed pull request #${pr}"
else
  echo "== NOT as expected: see the FAIL lines; left behind: ${BRANCH}${pr:+, pull request #${pr}}" >&2
fi
exit "${fail}"
