# shellcheck shell=bash
# Shared by the Gitea-primary scripts (agent-config/work/multi-agent/
# CUT-gitea-primary-2026-10-17.md, step 0f). Sourced, not run.
#
# The Owner runs these from his Mac. Gitea is reached through a port-forward
# made with his admin kubeconfig, and the admin token is read from Secret
# cicd/gitea-bootstrap into this shell only: it is never printed, never on a
# command line (API calls go through python3 with the token in a header; git
# gets it as environment config scoped to the forwarded host).
#
# Tests point GITEA_API and GITEA_GIT_BASE at local fakes and set GITEA_TOKEN,
# which skips the Secret and the port-forward.

set -euo pipefail

GITEA_ORG="${GITEA_ORG:-bifrost}"
GITHUB_OWNER="${GITHUB_OWNER:-weitingzhao}"
GITHUB_BASE="${GITHUB_BASE:-https://github.com/${GITHUB_OWNER}}"
GITEA_LOCAL_PORT="${GITEA_LOCAL_PORT:-3998}"

gitea_die() {
  echo "${0##*/}: $*" >&2
  exit 1
}

# gitea_connect — sets GITEA_API and GITEA_GIT_BASE (a port-forward to
# svc/gitea unless both are given) and GITEA_TOKEN (from the Secret unless
# given). Call once.
gitea_connect() {
  if [[ -z "${GITEA_API:-}" || -z "${GITEA_GIT_BASE:-}" ]]; then
    export KUBECONFIG="${GITEA_KUBECONFIG:-$HOME/.bifrost-owner/kube/admin.yaml}"
    kubectl -n cicd port-forward svc/gitea "${GITEA_LOCAL_PORT}:3000" > /dev/null 2>&1 &
    GITEA_PF_PID=$!
    trap 'kill "${GITEA_PF_PID}" 2> /dev/null || true' EXIT
    GITEA_API="http://127.0.0.1:${GITEA_LOCAL_PORT}/api/v1"
    GITEA_GIT_BASE="http://127.0.0.1:${GITEA_LOCAL_PORT}"
    local i
    for i in $(seq 1 30); do
      curl -sf "${GITEA_API}/version" > /dev/null 2>&1 && break
      [[ "$i" -lt 30 ]] || gitea_die "Gitea did not answer through the port-forward"
      sleep 1
    done
  fi
  if [[ -z "${GITEA_TOKEN:-}" ]]; then
    GITEA_TOKEN="$(kubectl -n cicd get secret gitea-bootstrap -o json |
      python3 -c 'import base64,json,sys; print(base64.b64decode(json.load(sys.stdin)["data"]["gitea_admin_token"]).decode())')" ||
      gitea_die "cannot read gitea_admin_token from Secret cicd/gitea-bootstrap"
    [[ -n "${GITEA_TOKEN}" ]] || gitea_die "gitea_admin_token is empty"
  fi
  export GITEA_API GITEA_GIT_BASE GITEA_TOKEN
  # git: the token as a header for the Gitea host only
  local host
  host="$(printf '%s' "${GITEA_GIT_BASE}" | sed -nE 's#^(https?://[^/]+).*#\1/#p')"
  if [[ -n "${host}" ]]; then
    export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0="http.${host}.extraHeader" GIT_CONFIG_VALUE_0="Authorization: token ${GITEA_TOKEN}"
  fi
  export GIT_TERMINAL_PROMPT=0
}

# gitea_api METHOD PATH [JSON] — prints the body; exits non-zero on a status
# outside 2xx (the status and body go to stderr).
gitea_api() {
  python3 - "$1" "$2" "${3:-}" << 'PY'
import os, sys, urllib.error, urllib.request
method, path, body = sys.argv[1], sys.argv[2], sys.argv[3]
req = urllib.request.Request(os.environ["GITEA_API"].rstrip("/") + path, method=method,
                             data=body.encode() if body else None,
                             headers={"Authorization": "token " + os.environ["GITEA_TOKEN"],
                                      "Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        sys.stdout.write(r.read().decode())
except urllib.error.HTTPError as e:
    sys.stderr.write(f"{method} {path} → HTTP {e.code}: {e.read().decode()[:300]}\n")
    sys.exit(1)
except (urllib.error.URLError, OSError) as e:
    sys.stderr.write(f"{method} {path}: {e}\n")
    sys.exit(1)
PY
}

# heads_and_tags <url> — "sha ref" lines for refs/heads/* and refs/tags/*,
# sorted; refs/pull/* and peeled tags left out. The global and system git
# config are not read: once a batch is done the Owner's ~/.gitconfig rewrites
# its GitHub addresses to Gitea (insteadOf), and a GitHub read would then be a
# second Gitea read. The Gitea token header comes from the environment.
heads_and_tags() {
  local listed
  listed="$(GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 git ls-remote --refs "$1")" || return 1
  printf '%s\n' "${listed}" | awk '$2 ~ /^refs\/(heads|tags)\// { print $1, $2 }' | sort -k2
}
