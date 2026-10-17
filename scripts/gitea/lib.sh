# shellcheck shell=bash
# Shared by the Gitea-primary scripts (agent-config/work/multi-agent/
# CUT-gitea-primary-2026-10-17.md, step 0f). Sourced, not run.
#
# The Owner runs these from his Mac. Gitea is reached through a port-forward
# made with his admin kubeconfig, and the admin token is read from Secret
# cicd/gitea-bootstrap into this shell only: it is never printed, never on a
# command line (API calls go through python3 with the token in a header; git
# gets it as environment config scoped to the forwarded host). Neither follows
# a redirect, so the token never goes on to another host (review 246 A1).
#
# Tests point GITEA_API and GITEA_GIT_BASE at local fakes and set GITEA_TOKEN,
# which skips the Secret and the port-forward.

# xtrace would print the token (review 246 B10): off before anything reads it
{ set +x; } 2> /dev/null
set -euo pipefail

GITEA_ORG="${GITEA_ORG:-bifrost}"
GITHUB_OWNER="${GITHUB_OWNER:-weitingzhao}"
GITHUB_BASE="${GITHUB_BASE:-https://github.com/${GITHUB_OWNER}}"
GITEA_PF_PID=""
GITEA_PF_LOG=""
GITEA_EMPTY_DIR=""

gitea_die() {
  echo "${0##*/}: $*" >&2
  exit 1
}

# gitea_cleanup — stops the port-forward and removes what gitea_connect made.
# A script that sets its own EXIT trap calls it from there.
gitea_cleanup() {
  [[ -z "${GITEA_PF_PID}" ]] || kill "${GITEA_PF_PID}" 2> /dev/null || true
  [[ -z "${GITEA_PF_LOG}" ]] || rm -f "${GITEA_PF_LOG}"
  [[ -z "${GITEA_EMPTY_DIR}" ]] || rmdir "${GITEA_EMPTY_DIR}" 2> /dev/null || true
}

# gitea_connect — sets GITEA_API and GITEA_GIT_BASE (a port-forward to
# svc/gitea unless both are given) and GITEA_TOKEN (from the Secret unless
# given). Call once.
gitea_connect() {
  trap gitea_cleanup EXIT
  GITEA_EMPTY_DIR="$(mktemp -d)"
  if [[ -z "${GITEA_API:-}" || -z "${GITEA_GIT_BASE:-}" ]]; then
    export KUBECONFIG="${GITEA_KUBECONFIG:-$HOME/.bifrost-owner/kube/admin.yaml}"
    # kubectl picks a free local port and says which: a port some other
    # service already holds is never used (review 246 A2)
    GITEA_PF_LOG="$(mktemp)"
    kubectl -n cicd port-forward svc/gitea :3000 > "${GITEA_PF_LOG}" 2>&1 &
    GITEA_PF_PID=$!
    local i port=""
    for i in $(seq 1 30); do
      port="$(sed -nE 's#^Forwarding from 127\.0\.0\.1:([0-9]+) -> 3000$#\1#p' "${GITEA_PF_LOG}")" || port=""
      port="${port%%$'\n'*}"
      [[ -z "${port}" ]] || break
      kill -0 "${GITEA_PF_PID}" 2> /dev/null || gitea_die "the port-forward to svc/gitea did not start: $(head -c 300 "${GITEA_PF_LOG}")"
      [[ "$i" -lt 30 ]] || gitea_die "the port-forward to svc/gitea did not say its local port"
      sleep 1
    done
    GITEA_API="http://127.0.0.1:${port}/api/v1"
    GITEA_GIT_BASE="http://127.0.0.1:${port}"
    curl -sf "${GITEA_API}/version" > /dev/null 2>&1 || gitea_die "Gitea did not answer through the port-forward"
    kill -0 "${GITEA_PF_PID}" 2> /dev/null || gitea_die "the port-forward to svc/gitea stopped"
  fi
  if [[ -z "${GITEA_TOKEN:-}" ]]; then
    GITEA_TOKEN="$(kubectl -n cicd get secret gitea-bootstrap -o json |
      python3 -c 'import base64,json,sys; print(base64.b64decode(json.load(sys.stdin)["data"]["gitea_admin_token"]).decode())')" ||
      gitea_die "cannot read gitea_admin_token from Secret cicd/gitea-bootstrap"
    [[ -n "${GITEA_TOKEN}" ]] || gitea_die "gitea_admin_token is empty"
  fi
  export GITEA_API GITEA_GIT_BASE GITEA_TOKEN
  # git: the token as a header for the Gitea host only, and no redirects
  local host
  host="$(printf '%s' "${GITEA_GIT_BASE}" | sed -nE 's#^(https?://[^/]+).*#\1/#p')"
  if [[ -n "${host}" ]]; then
    export GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0="http.${host}.extraHeader" GIT_CONFIG_VALUE_0="Authorization: token ${GITEA_TOKEN}" \
      GIT_CONFIG_KEY_1="http.followRedirects" GIT_CONFIG_VALUE_1="false"
  fi
  export GIT_TERMINAL_PROMPT=0
}

# gitea_api METHOD PATH [JSON] — prints the body; exits non-zero on a status
# outside 2xx (the status and body go to stderr). A redirect is refused, not
# followed: urllib would send the Authorization header on to its Location.
gitea_api() {
  python3 - "$1" "$2" "${3:-}" << 'PY'
import os, sys, urllib.error, urllib.request
method, path, body = sys.argv[1], sys.argv[2], sys.argv[3]

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"redirect to {newurl} refused", headers, fp)

req = urllib.request.Request(os.environ["GITEA_API"].rstrip("/") + path, method=method,
                             data=body.encode() if body else None,
                             headers={"Authorization": "token " + os.environ["GITEA_TOKEN"],
                                      "Content-Type": "application/json"})
try:
    with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as r:
        sys.stdout.write(r.read().decode())
except urllib.error.HTTPError as e:
    sys.stderr.write(f"{method} {path} → HTTP {e.code}: {e.msg}: {e.read().decode()[:300]}\n")
    sys.exit(1)
except (urllib.error.URLError, OSError) as e:
    sys.stderr.write(f"{method} {path}: {e}\n")
    sys.exit(1)
PY
}

# heads_and_tags gitea|github <url> — "sha ref" lines for refs/heads/* and
# refs/tags/*, sorted; refs/pull/* and peeled tags left out. git runs in an
# empty directory with no repository above it and reads no global, system or
# repository config: after a batch the Owner's ~/.gitconfig (and any checkout
# he runs this from) can rewrite GitHub addresses to Gitea, and a GitHub read
# would then be a second Gitea read (review 246 A3). Only the Gitea read
# carries the token header.
heads_and_tags() {
  local listed
  local -a drop=(-u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_CONFIG_PARAMETERS -u GIT_CONFIG)
  if [[ "$1" != gitea ]]; then
    drop+=(-u GIT_CONFIG_COUNT -u GIT_CONFIG_KEY_0 -u GIT_CONFIG_VALUE_0 -u GIT_CONFIG_KEY_1 -u GIT_CONFIG_VALUE_1)
  fi
  listed="$(cd "${GITEA_EMPTY_DIR}" && env "${drop[@]}" GIT_CEILING_DIRECTORIES="${GITEA_EMPTY_DIR%/*}" \
    GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 git ls-remote --refs "$2")" || return 1
  printf '%s\n' "${listed}" | awk '$2 ~ /^refs\/(heads|tags)\// { print $1, $2 }' | sort -k2
}
