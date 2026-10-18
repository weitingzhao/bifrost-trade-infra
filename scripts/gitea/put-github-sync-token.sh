#!/usr/bin/env bash
# put-github-sync-token.sh — the Owner puts the GitHub token the sync uses
# (Secret cicd/github-sync, key token; k8s/cicd/github-sync) into the cluster.
# OWNER-STEPS-gitea-primary.md section 1 item 7.
#
# It reads the token without echo from the terminal, and refuses when stdin is
# not one. It is a bash script so that it reads the same under the Owner's zsh:
# the one-line command it replaces used `read -p`, which in zsh means "read
# from the coprocess", and created nothing (2026-10-17).
#
#   bash scripts/gitea/put-github-sync-token.sh
#
# Before it writes anything it asks GitHub, with that token:
#   - GET /user is GITHUB_LOGIN (weitingzhao): the token is that account's
#   - for every repository in REPOS, the git push handshake
#     (info/refs?service=git-receive-pack) answers 200: the token can push
#     there. The handshake only lists refs; nothing is pushed.
# Any other answer stops it with nothing written. It then creates the Secret
# (never replaces one: an existing github-sync stops it) and prints only the
# Secret's key names.
#
# The token reaches curl as a config file on stdin and kubectl on stdin, never
# a command line or a file.
set -euo pipefail

GITHUB_LOGIN="${GITHUB_LOGIN:-weitingzhao}"
GITHUB_API="${GITHUB_API:-https://api.github.com}"
GITHUB_GIT="${GITHUB_GIT:-https://github.com/${GITHUB_LOGIN}}"
REPOS="${REPOS:-bifrost-trade-core bifrost-trade-api bifrost-trade-worker bifrost-trade-frontend bifrost-ui bifrost-platform bifrost-research bifrost-trade-infra bifrost-platform-plugin bifrost-platform-plugin-market-data bifrost-platform-plugin-flex-query}"
NS=cicd
NAME=github-sync
export KUBECONFIG="${PUT_TOKEN_KUBECONFIG:-$HOME/.bifrost-owner/kube/admin.yaml}"

die() { echo "ERROR: $*" >&2; echo "Nothing was written." >&2; exit 1; }

[[ -t 0 ]] || die "stdin is not a terminal; run it in a terminal tab"
[[ -r "${KUBECONFIG}" ]] || die "no admin kubeconfig at ${KUBECONFIG}"

if kubectl -n "${NS}" get secret "${NAME}" -o name > /dev/null 2>&1; then
  die "Secret ${NS}/${NAME} already exists; this script only creates it."
fi
kubectl -n "${NS}" get serviceaccount default -o name > /dev/null || die "cannot reach the cluster with ${KUBECONFIG}"

IFS= read -rs -p "GitHub sync token (input hidden): " t
echo
[[ -n "${t}" ]] || die "empty input"
[[ "${t}" =~ ^github_pat_[A-Za-z0-9_]+$ ]] || die "this is not a fine-grained token (they start with github_pat_)"

# curl with the token in a config read from stdin. $1 = what to send it as.
ask() { # MODE URL — prints the HTTP status, then the body into $work/body
  local mode="$1" url="$2"
  if [[ "${mode}" == bearer ]]; then
    printf 'header = "Authorization: Bearer %s"\n' "${t}"
  else
    printf 'user = "x-access-token:%s"\n' "${t}"
  fi | curl -sS -K - -o "${work}/body" -D "${work}/headers" -w '%{http_code}' --max-time 30 "${url}" || echo "000"
}
work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

code="$(ask bearer "${GITHUB_API}/user")"
[[ "${code}" == 200 ]] || die "GitHub GET /user → HTTP ${code}: the token is not accepted"
login="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("login",""))' "${work}/body")"
[[ "${login}" == "${GITHUB_LOGIN}" ]] || die "the token belongs to '${login}', not ${GITHUB_LOGIN}"
expiry="$(tr -d '\r' < "${work}/headers" | awk -F': ' 'tolower($1)=="github-authentication-token-expiration"{print $2}')"
echo "ok    token of ${login}; expires ${expiry:-(GitHub did not say)}"

bad=0
for repo in ${REPOS}; do
  code="$(ask basic "${GITHUB_GIT}/${repo}.git/info/refs?service=git-receive-pack")"
  if [[ "${code}" == 200 ]]; then
    echo "ok    can push to ${repo}"
  else
    echo "FAIL  ${repo}: push handshake → HTTP ${code} (Repository access All repositories, Contents Read and write?)"
    bad=1
  fi
done
[[ "${bad}" == 0 ]] || die "the token cannot push to every repository"

printf '%s' "${t}" | kubectl -n "${NS}" create secret generic "${NAME}" --from-file=token=/dev/stdin
unset t
keys="$(kubectl -n "${NS}" get secret "${NAME}" -o json | python3 -c 'import json,sys; print(" ".join(sorted(json.load(sys.stdin)["data"])))')"
[[ "${keys}" == token ]] || { echo "ERROR: Secret ${NS}/${NAME} has keys: ${keys}" >&2; exit 1; }
echo "==> Secret ${NS}/${NAME} created (key: token). Say 「第 3 段做完了」 in the thread."
