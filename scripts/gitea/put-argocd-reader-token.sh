#!/usr/bin/env bash
# put-argocd-reader-token.sh — batch C (CUT-gitea-primary-2026-10-17 §4 「第 C 批」
# step 2): the Owner puts the Gitea token of argocd-reader into the cluster as
# Argo CD's credentials for the Gitea repositories it reads: Secret
# cicd/repo-creds-gitea-bifrost, a credential template (label
# argocd.argoproj.io/secret-type: repo-creds) for every repository under
# http://gitea.cicd.svc.cluster.local:3000/bifrost.
#
#   bash scripts/gitea/put-argocd-reader-token.sh
#
# It reads the token without echo from the terminal and refuses when stdin is
# not one. Before it writes anything it asks Gitea (the NodePort this Mac
# reaches) with the token:
#   - who it is: GET /api/v1/user is argocd-reader; or, when that answers the
#     missing-scope 403 (the planned token has repository Read only), the
#     token can read bifrost-trade-infra and bifrost-research and is neither
#     administrator nor writer of them
#   - git can fetch both (upload-pack handshake 200) and cannot push to either
#     (receive-pack handshake refused): read only, as Argo needs
#   - it does not see bifrost/bifrost-platform (team argocd-read holds only the
#     two repositories)
# Any other answer stops it with nothing written. It creates the Secret
# (never replaces one) and prints only its key names and label.
#
# The token reaches curl as a config on stdin (curl -q: no ~/.curlrc) and
# kubectl as a manifest on stdin; xtrace is off.
set -euo pipefail
set +x

LOGIN="${ARGO_LOGIN:-argocd-reader}"
BASE="${GITEA_PUBLIC_BASE:-http://192.168.10.73:30300/bifrost}"
IN_CLUSTER="${GITEA_IN_CLUSTER:-http://gitea.cicd.svc.cluster.local:3000/bifrost}"
READ_REPOS="${READ_REPOS:-bifrost-trade-infra bifrost-research}"
HIDDEN_REPO="${HIDDEN_REPO:-bifrost-platform}"
NS=cicd
NAME=repo-creds-gitea-bifrost
export KUBECONFIG="${PUT_TOKEN_KUBECONFIG:-$HOME/.bifrost-owner/kube/admin.yaml}"
server="$(printf '%s' "${BASE}" | sed -nE 's#^(https?)://([^/]+)/(.+)$#\1 \2 \3#p')"
[[ -n "${server}" ]] || { echo "ERROR: cannot read the server of ${BASE}" >&2; exit 1; }
read -r proto host org <<< "${server}"
root="${proto}://${host}"

die() { echo "ERROR: $*" >&2; echo "Nothing was written." >&2; exit 1; }

[[ -t 0 ]] || die "stdin is not a terminal; run it in a terminal tab"
[[ -r "${KUBECONFIG}" ]] || die "no admin kubeconfig at ${KUBECONFIG}"
if kubectl -n "${NS}" get secret "${NAME}" -o name > /dev/null 2>&1; then
  die "Secret ${NS}/${NAME} already exists; this script only creates it."
fi
kubectl -n "${NS}" get serviceaccount default -o name > /dev/null || die "cannot reach the cluster with ${KUBECONFIG}"

IFS= read -rs -p "Gitea token of ${LOGIN} (input hidden): " t
echo
[[ -n "${t}" ]] || die "empty input"
[[ "${t}" =~ ^[0-9a-f]{40}$ ]] || die "a Gitea token is 40 hex characters"

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT
ask() { # MODE URL — the HTTP status; the body into $work/body
  local mode="$1" url="$2"
  if [[ "${mode}" == token ]]; then
    printf 'header = "Authorization: token %s"\n' "${t}"
  else
    printf 'user = "%s:%s"\n' "${LOGIN}" "${t}"
  fi | curl -q -sS -K - --noproxy '*' -o "${work}/body" -w '%{http_code}' --max-time 30 "${url}" || echo "000"
}
field() { python3 -c 'import json,sys
d = json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."):
    d = d.get(k) if isinstance(d, dict) else None
print({True: "true", False: "false", None: ""}.get(d, d))' "${work}/body" "$1"; }

code="$(ask token "${root}/api/v1/user")"
if [[ "${code}" == 200 ]]; then
  login="$(field login)"
  [[ "${login}" == "${LOGIN}" ]] || die "the token belongs to '${login}', not ${LOGIN}"
  echo "ok    token of ${login}"
elif [[ "${code}" == 403 ]] && grep -qi 'required scope' "${work}/body"; then
  echo "ok    the token has no user scope (repository Read only, as planned)"
else
  die "Gitea GET /api/v1/user → HTTP ${code}: the token is not accepted ($(head -c 200 "${work}/body" | tr -d '\n'))"
fi
for repo in ${READ_REPOS}; do
  code="$(ask token "${root}/api/v1/repos/${org}/${repo}")"
  [[ "${code}" == 200 ]] || die "GET /api/v1/repos/${org}/${repo} → HTTP ${code}: the token cannot read it"
  [[ "$(field permissions.admin)" == false && "$(field permissions.push)" == false && "$(field permissions.pull)" == true ]] \
    || die "on ${org}/${repo} the token's user has admin=$(field permissions.admin) push=$(field permissions.push) pull=$(field permissions.pull); Argo's account must only read"
  code="$(ask basic "${BASE}/${repo}.git/info/refs?service=git-upload-pack")"
  [[ "${code}" == 200 ]] || die "fetch handshake on ${repo} → HTTP ${code}"
  code="$(ask basic "${BASE}/${repo}.git/info/refs?service=git-receive-pack")"
  [[ "${code}" != 200 ]] || die "push handshake on ${repo} → 200: the token can push there"
  echo "ok    ${repo}: read only (fetch 200, push refused with ${code})"
done
code="$(ask token "${root}/api/v1/repos/${org}/${HIDDEN_REPO}")"
[[ "${code}" == 404 ]] || die "GET /api/v1/repos/${org}/${HIDDEN_REPO} → HTTP ${code}: the token sees more than ${READ_REPOS}"
echo "ok    ${HIDDEN_REPO} is not visible to it"

printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: %s\n  namespace: %s\n  labels:\n    argocd.argoproj.io/secret-type: repo-creds\nstringData:\n  type: git\n  url: %s\n  username: %s\n  password: "%s"\n' \
  "${NAME}" "${NS}" "${IN_CLUSTER}" "${LOGIN}" "${t}" | kubectl create -f - > /dev/null
unset t
got="$(kubectl -n "${NS}" get secret "${NAME}" -o json | python3 -c 'import json,sys
s = json.load(sys.stdin)
print(" ".join(sorted(s.get("data", {}))), s["metadata"].get("labels", {}).get("argocd.argoproj.io/secret-type", ""))')"
[[ "${got}" == "password type url username repo-creds" ]] || { echo "ERROR: Secret ${NS}/${NAME} reads back as: ${got}" >&2; exit 1; }
echo "==> Secret ${NS}/${NAME} created (keys password type url username; repo-creds for ${IN_CLUSTER}). Say 「Argo 令牌放好了」 in the thread."
