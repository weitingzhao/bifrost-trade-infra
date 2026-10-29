#!/usr/bin/env bash
# put-reader-token.sh stg|prod|ci|drill|lander [replace] — TD-432 / landing S0, S3
# drill is deliberately NOT a reader: agentrt-landing-stg may write code only
# in platform and infra, but may not push main or administer any repository.
# lander (S3, CUT-landing §11.11) is the PROD landing identity agentrt-lander:
# it may write code only in platform, and push platform's main (it is on the
# main whitelist), but administer nothing; infra stays read-only until S6.
# Branch/tag/PR protection still needs the Owner's actual refusal probes.
# (agent-config/work/multi-agent/
# CUT-td432-gitea-credentials-2026-10-24.md; OWNER-STEPS-td432-2026-10-24.md):
# the Owner installs a reader or the fixed STG drill account into the cluster.
#
#   stg   account bifrost-platform-reader-stg   → Secret bifrost-platform-stg/bifrost-gitea-reader
#   prod  account bifrost-platform-reader-prod  → Secret bifrost-platform-prod/bifrost-gitea-reader
#   ci    account bifrost-ci-reader             → Secret cicd/gitea-ci-reader
#   drill account agentrt-landing-stg           → Secret bifrost-platform-stg/agentrt-landing-drill
#   lander account agentrt-lander               → Secret bifrost-platform-prod/agentrt-lander
#
# Each Secret is kubernetes.io/basic-auth (username, password). The platform
# mounts its own (k8s/overlays/platform-*/platform-gitea-reader.patch.yaml);
# the CI clone and the GitHub sync read gitea-ci-reader (later slice).
#
# It reads the token without echo from the terminal and refuses when stdin is
# not one. Before it writes anything it asks Gitea (the NodePort this Mac
# reaches) with the token, and stops with nothing written on any other answer:
#   - GET /api/v1/user is the account, and the account is not a site
#     administrator (the token needs user Read for this)
#   - GET /api/v1/orgs/bifrost/repos answers (organization Read: the
#     platform's lineage lists the organization's repositories with it)
#   - every repository of agent-config/gitea-primary.txt: the account can read
#     it and is neither its administrator nor a writer; git can fetch
#     (upload-pack handshake 200) and a push is refused with 401 or 403
#   - every repository the token can see (GET /api/v1/repos/search, page by
#     page until a page comes back empty; a search still going at page 40 is
#     an unfinished check and writes nothing) it can only read, and it sees at
#     least the primaries
# Without "replace" it creates the Secret and refuses one that exists (S1:
# nothing reads it yet). With "replace" (a rotation once the platform reads
# it) the Secret must exist and is replaced in place only after the new token
# passed every check above, so the reader is never without a credential. It
# prints only the key names.
#
# The token reaches curl as a config on stdin (curl -q: no ~/.curlrc) and
# kubectl as a manifest on stdin; xtrace is off.
set -euo pipefail
set +x

case "${1:-}" in
  stg) LOGIN=bifrost-platform-reader-stg NS=bifrost-platform-stg NAME=bifrost-gitea-reader ;;
  prod) LOGIN=bifrost-platform-reader-prod NS=bifrost-platform-prod NAME=bifrost-gitea-reader ;;
  ci) LOGIN=bifrost-ci-reader NS=cicd NAME=gitea-ci-reader ;;
  drill) LOGIN=agentrt-landing-stg NS=bifrost-platform-stg NAME=agentrt-landing-drill ;;
  lander) LOGIN=agentrt-lander NS=bifrost-platform-prod NAME=agentrt-lander ;;
  *)
    echo "usage: ${0##*/} stg|prod|ci|drill|lander [replace]" >&2
    exit 2
    ;;
esac
case "${2:-}" in
  "") MODE=create ;;
  replace) MODE=replace ;;
  *)
    echo "usage: ${0##*/} stg|prod|ci|drill|lander [replace]" >&2
    exit 2
    ;;
esac
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRIMARIES="${GITEA_PRIMARIES_FILE:-${HERE}/../../agent-config/gitea-primary.txt}"
BASE="${GITEA_PUBLIC_BASE:-http://192.168.10.73:30300/bifrost}"
export KUBECONFIG="${PUT_TOKEN_KUBECONFIG:-$HOME/.bifrost-owner/kube/admin.yaml}"
server="$(printf '%s' "${BASE}" | sed -nE 's#^(https?)://([^/]+)/(.+)$#\1 \2 \3#p')"
[[ -n "${server}" ]] || { echo "ERROR: cannot read the server of ${BASE}" >&2; exit 1; }
read -r proto host org <<< "${server}"
root="${proto}://${host}"

die() { echo "ERROR: $*" >&2; echo "Nothing was written." >&2; exit 1; }

[[ -t 0 ]] || die "stdin is not a terminal; run it in a terminal tab"
[[ -r "${KUBECONFIG}" ]] || die "no admin kubeconfig at ${KUBECONFIG}"
[[ -r "${PRIMARIES}" ]] || die "cannot read ${PRIMARIES}"
primaries="$(sed -e 's/#.*//' -e 's/[[:space:]]//g' "${PRIMARIES}" | sed '/^$/d' | sort -u)"
if [[ "$1" == drill ]]; then
  primaries=$'bifrost-platform\nbifrost-trade-infra'
fi
if [[ "$1" == lander ]]; then
  primaries=$'bifrost-platform\nbifrost-trade-infra'
fi
[[ -n "${primaries}" ]] || die "${PRIMARIES} names no repository"
if kubectl -n "${NS}" get secret "${NAME}" -o name > /dev/null 2>&1; then
  [[ "${MODE}" == replace ]] || die "Secret ${NS}/${NAME} already exists; to rotate its token run: ${0##*/} ${1} replace"
else
  [[ "${MODE}" == create ]] || die "Secret ${NS}/${NAME} does not exist; replace only rotates an existing one"
fi
kubectl -n "${NS}" get serviceaccount default -o name > /dev/null || die "cannot reach namespace ${NS} with ${KUBECONFIG}"

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
if [[ "${code}" == 403 ]] && grep -qi 'required scope' "${work}/body"; then
  die "the token has no user scope: make it with user Read as well as repository and organization Read"
fi
[[ "${code}" == 200 ]] || die "Gitea GET /api/v1/user → HTTP ${code}: the token is not accepted ($(head -c 200 "${work}/body" | tr -d '\n'))"
login="$(field login)"
[[ "${login}" == "${LOGIN}" ]] || die "the token belongs to '${login}', not ${LOGIN}"
[[ "$(field is_admin)" == false ]] || die "${LOGIN} is a site administrator (is_admin=$(field is_admin)); a reader must not be"
echo "ok    token of ${login}, not an administrator"

code="$(ask token "${root}/api/v1/orgs/${org}/repos?limit=1")"
if [[ "${code}" == 403 ]] && grep -qi 'required scope' "${work}/body"; then
  die "the token has no organization scope: make it with organization Read as well"
fi
[[ "${code}" == 200 ]] || die "GET /api/v1/orgs/${org}/repos → HTTP ${code}"
echo "ok    it can list the repositories of ${org}"

for repo in ${primaries}; do
  code="$(ask token "${root}/api/v1/repos/${org}/${repo}")"
  [[ "${code}" == 200 ]] || die "GET /api/v1/repos/${org}/${repo} → HTTP ${code}: the token cannot read it"
  expected_push=false
  [[ "$1" != drill ]] || expected_push=true
  [[ "$1" != lander || "${repo}" != bifrost-platform ]] || expected_push=true
  [[ "$(field permissions.admin)" == false && "$(field permissions.push)" == "${expected_push}" && "$(field permissions.pull)" == true ]] \
    || die "on ${org}/${repo} ${LOGIN} has admin=$(field permissions.admin) push=$(field permissions.push) pull=$(field permissions.pull); a reader must only read; drill must only write its two repositories; lander must only write platform"
  if [[ "$1" == drill ]]; then
    code="$(ask token "${root}/api/v1/repos/${org}/${repo}/branches/main")"
    [[ "${code}" == 200 && "$(field user_can_push)" == false ]] || die "${repo}: main is writable or its protection could not be verified"
  fi
  if [[ "$1" == lander ]]; then
    # platform's main whitelists the lander (S3); infra's does not (S6).
    main_push=false
    [[ "${repo}" != bifrost-platform ]] || main_push=true
    code="$(ask token "${root}/api/v1/repos/${org}/${repo}/branches/main")"
    [[ "${code}" == 200 && "$(field user_can_push)" == "${main_push}" ]] \
      || die "${repo}: main user_can_push=$(field user_can_push) (HTTP ${code}); the lander must push platform's main only"
  fi
  code="$(ask basic "${BASE}/${repo}.git/info/refs?service=git-upload-pack")"
  [[ "${code}" == 200 ]] || die "fetch handshake on ${repo} → HTTP ${code}"
  code="$(ask basic "${BASE}/${repo}.git/info/refs?service=git-receive-pack")"
  if [[ "$1" == drill || ( "$1" == lander && "${repo}" == bifrost-platform ) ]]; then
    [[ "${code}" == 200 ]] || die "$1 push handshake on ${repo} → HTTP ${code}"
    continue
  fi
  [[ "${code}" != 200 ]] || die "push handshake on ${repo} → 200: the token can push there"
  [[ "${code}" == 401 || "${code}" == 403 ]] || die "push handshake on ${repo} → HTTP ${code}: neither a refusal nor a yes; run this again when Gitea answers"
done
if [[ "$1" == drill ]]; then
  echo "ok    drill: two code writers, main user_can_push=false; actual tag/PR/push probes still required"
elif [[ "$1" == lander ]]; then
  echo "ok    lander: writes platform only, pushes platform main, infra read-only; actual tag/push probes still required"
else
  echo "ok    $(echo "${primaries}" | wc -l | tr -d ' ') primaries: read only (fetch 200, push refused)"
fi

: > "${work}/seen"
: > "${work}/writable"
: > "${work}/administrable"
page=1
while :; do
  code="$(ask token "${root}/api/v1/repos/search?limit=50&page=${page}")"
  [[ "${code}" == 200 ]] || die "GET /api/v1/repos/search page ${page} → HTTP ${code}"
  n="$(python3 -c 'import json,sys
d = json.load(open(sys.argv[1]))
rows = d.get("data") or []
open(sys.argv[2], "a").write("".join(r.get("full_name", "?") + "\n" for r in rows))
p = lambda r, k: (r.get("permissions") or {}).get(k)
open(sys.argv[3], "a").write("".join(r.get("full_name", "?") + "\n" for r in rows if p(r, "admin") is not False or p(r, "push") is not False))
open(sys.argv[4], "a").write("".join(r.get("full_name", "?") + "\n" for r in rows if p(r, "admin") is not False))
print(len(rows))' "${work}/body" "${work}/seen" "${work}/writable" "${work}/administrable")"
  [[ "${n}" -gt 0 ]] || break
  [[ "${page}" -lt 40 ]] || die "the search still returned repositories at page 40; the check is not finished"
  page=$((page + 1))
done
writable="$(sort -u "${work}/writable" | tr '\n' ' ')"
if [[ "$1" == drill ]]; then
  [[ ! -s "${work}/administrable" ]] || die "drill can administer a repository"
  [[ "${writable}" == "${org}/bifrost-platform ${org}/bifrost-trade-infra " ]] || die "drill has unexpected writable repositories: ${writable}"
elif [[ "$1" == lander ]]; then
  [[ ! -s "${work}/administrable" ]] || die "lander can administer a repository"
  [[ "${writable}" == "${org}/bifrost-platform " ]] || die "lander has unexpected writable repositories: ${writable}"
else
  [[ -z "${writable// /}" ]] || die "${LOGIN} is administrator or writer of: ${writable}"
fi
missing=""
for repo in ${primaries}; do
  grep -qx "${org}/${repo}" "${work}/seen" || missing="${missing} ${org}/${repo}"
done
[[ -z "${missing}" ]] || die "the search does not show:${missing}"
if [[ "$1" == drill ]]; then
  echo "ok    search complete: only platform and infra writable"
elif [[ "$1" == lander ]]; then
  echo "ok    search complete: only platform writable"
else
  echo "ok    it sees $(sort -u "${work}/seen" | wc -l | tr -d ' ') repositories and can write none"
fi

verb=create
[[ "${MODE}" == create ]] || verb=replace
component=gitea-reader
[[ "$1" != drill ]] || component=gitea-landing-drill
[[ "$1" != lander ]] || component=gitea-lander
emit_secret() {
  printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: %s\n  namespace: %s\n  labels:\n    bifrost.io/component: %s\ntype: kubernetes.io/basic-auth\nstringData:\n  username: %s\n  password: "%s"\n' \
    "${NAME}" "${NS}" "${component}" "${LOGIN}" "${t}"
}
emit_secret | kubectl "${verb}" --dry-run=server -f - > /dev/null
echo "ok    Secret server dry-run passed"
emit_secret | kubectl "${verb}" -f - > /dev/null
unset t
got="$(kubectl -n "${NS}" get secret "${NAME}" -o json | python3 -c 'import json,sys
s = json.load(sys.stdin)
print(" ".join(sorted(s.get("data", {}))), s.get("type", ""))')"
[[ "${got}" == "password username kubernetes.io/basic-auth" ]] || { echo "ERROR: Secret ${NS}/${NAME} reads back as: ${got}" >&2; exit 1; }
done_word=created
[[ "${MODE}" == create ]] || done_word=replaced
echo "==> Secret ${NS}/${NAME} ${done_word} (keys password username, type kubernetes.io/basic-auth; account ${LOGIN})."
