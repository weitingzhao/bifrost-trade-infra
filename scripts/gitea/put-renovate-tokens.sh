#!/usr/bin/env bash
# The Owner's two tokens for Renovate -> Secret cicd/renovate
# (keys gitea-token, github-com-token). Run it in a terminal tab:
#
#   scripts/gitea/put-renovate-tokens.sh            create the Secret
#   scripts/gitea/put-renovate-tokens.sh --check    ask and check, write nothing
#
# Before running it, in Gitea (http://192.168.10.73:30300), as the admin:
#   1. create the user `renovate-bot` (not an admin), with a full name and an
#      e-mail address;
#   2. give it Write on bifrost/bifrost-trade-infra and on nothing else;
#   3. sign in as it, Settings -> Applications -> generate a token with:
#      repository Read and Write, user Read, issue Read and Write,
#      organization Read.
# And on github.com, Settings -> Developer settings -> Fine-grained tokens:
#   4. a token with Repository access "Public repositories (read-only)" and no
#      other permission.
#
# It asks for the two tokens with the input hidden, checks what each can do
# (the Gitea one: belongs to renovate-bot, is not an admin, can write the one
# repository; the GitHub one: is accepted), and only then creates the Secret.
# It only creates: an existing Secret stops it. The tokens reach curl as a
# config on stdin (curl -q: no ~/.curlrc) and kubectl on stdin, never a command
# line or a file; xtrace is off. The last lines read the Secret back and print
# its key names only.
set -euo pipefail
set +x  # a token must not reach a trace

GITEA="${GITEA:-http://192.168.10.73:30300}"
GITEA_BOT="${GITEA_BOT:-renovate-bot}"
GITEA_REPO="${GITEA_REPO:-bifrost/bifrost-trade-infra}"
GITHUB_API="${GITHUB_API:-https://api.github.com}"
NS=cicd
NAME=renovate
CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1
export KUBECONFIG="${PUT_TOKEN_KUBECONFIG:-$HOME/.bifrost-owner/kube/admin.yaml}"

die() { echo "ERROR: $*" >&2; echo "Nothing was written." >&2; exit 1; }

[[ $- != *x* ]] || die "xtrace is on"
[[ -t 0 ]] || die "stdin is not a terminal; run it in a terminal tab"
if [[ "${CHECK_ONLY}" == 0 ]]; then
  [[ -r "${KUBECONFIG}" ]] || die "no admin kubeconfig at ${KUBECONFIG}"
  if kubectl -n "${NS}" get secret "${NAME}" -o name > /dev/null 2>&1; then
    die "Secret ${NS}/${NAME} already exists; this script only creates it."
  fi
  kubectl -n "${NS}" get serviceaccount default -o name > /dev/null || die "cannot reach the cluster with ${KUBECONFIG}"
fi

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

# curl with a token in a config read from stdin. Prints the HTTP status; the
# body goes to $work/body.
ask() { # TOKEN SCHEME URL
  printf 'header = "Authorization: %s %s"\n' "$2" "$1" \
    | curl -q -sS -K - -o "${work}/body" -w '%{http_code}' --max-time 30 "$3" || echo "000"
}
field() { python3 -c 'import json,sys
d=json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."):
    d=d.get(k) if isinstance(d,dict) else None
print("" if d is None else d)' "${work}/body" "$1"; }

IFS= read -rs -p "Gitea token of ${GITEA_BOT} (input hidden): " gt
echo
[[ "${gt}" =~ ^[0-9a-f]{40}$ ]] || die "this is not a Gitea token (40 hex characters)"

code="$(ask "${gt}" token "${GITEA}/api/v1/user")"
[[ "${code}" == 200 ]] || die "Gitea GET /user -> HTTP ${code}: the token is not accepted (user Read scope?)"
[[ "$(field login)" == "${GITEA_BOT}" ]] || die "the token belongs to '$(field login)', not ${GITEA_BOT}"
[[ "$(field is_admin)" != True ]] || die "${GITEA_BOT} is a Gitea admin; it must not be"
echo "ok    Gitea token of ${GITEA_BOT} (not an admin)"

code="$(ask "${gt}" token "${GITEA}/api/v1/repos/${GITEA_REPO}")"
[[ "${code}" == 200 ]] || die "Gitea GET /repos/${GITEA_REPO} -> HTTP ${code} (repository Read scope? access to the repository?)"
[[ "$(field permissions.push)" == True ]] || die "${GITEA_BOT} cannot push branches to ${GITEA_REPO} (give it Write)"
[[ "$(field permissions.admin)" != True ]] || die "${GITEA_BOT} administers ${GITEA_REPO}; Write is enough and admin could change the branch protection"
echo "ok    can push branches to ${GITEA_REPO}, does not administer it"

code="$(ask "${gt}" token "${GITEA}/api/v1/repos/${GITEA_REPO}/pulls?state=open&limit=1")"
[[ "${code}" == 200 ]] || die "Gitea GET pulls -> HTTP ${code} (issue Read and Write scope?)"
echo "ok    can read pull requests"

code="$(ask "${gt}" token "${GITEA}/api/v1/user/repos?limit=50")"
[[ "${code}" == 200 ]] || die "Gitea GET /user/repos -> HTTP ${code}"
others="$(python3 -c 'import json,sys
want=sys.argv[2]
print(" ".join(r["full_name"] for r in json.load(open(sys.argv[1])) if r["full_name"]!=want and r.get("permissions",{}).get("push")))' "${work}/body" "${GITEA_REPO}")"
[[ -z "${others}" ]] || die "${GITEA_BOT} can also push to: ${others}. Remove that access first."
echo "ok    /user/repos lists no other repository it can push to"

IFS= read -rs -p "github.com read-only token (input hidden): " ht
echo
[[ "${ht}" =~ ^github_pat_[A-Za-z0-9_]+$ ]] || die "this is not a fine-grained GitHub token (they start with github_pat_)"
code="$(ask "${ht}" Bearer "${GITHUB_API}/repos/renovatebot/renovate/releases/latest")"
[[ "${code}" == 200 ]] || die "GitHub GET a public release -> HTTP ${code}: the token is not accepted"
echo "ok    GitHub token reads public releases"
echo "note  this script cannot see the GitHub token's permissions; it trusts step 4 above (public repositories, read-only)"

if [[ "${CHECK_ONLY}" == 1 ]]; then
  unset gt ht
  echo "==> --check: both tokens pass. Nothing was written."
  exit 0
fi

# Both values travel on stdin as one JSON document; kubectl builds the Secret.
python3 -c 'import json,sys
g,h=sys.stdin.read().split("\n")[:2]
print(json.dumps({"apiVersion":"v1","kind":"Secret","type":"Opaque",
  "metadata":{"name":sys.argv[2],"namespace":sys.argv[1]},
  "stringData":{"gitea-token":g,"github-com-token":h}}))' "${NS}" "${NAME}" <<<"${gt}"$'\n'"${ht}" \
  | kubectl create -f - > /dev/null
unset gt ht
keys="$(kubectl -n "${NS}" get secret "${NAME}" -o json | python3 -c 'import json,sys; print(" ".join(sorted(json.load(sys.stdin)["data"])))')"
[[ "${keys}" == "gitea-token github-com-token" ]] || { echo "ERROR: Secret ${NS}/${NAME} has keys: ${keys}" >&2; exit 1; }
echo "==> Secret ${NS}/${NAME} created (keys: gitea-token github-com-token)."
