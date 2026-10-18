#!/usr/bin/env bash
# store-mbp-token.sh — batch A step 6 (CUT-gitea-primary-2026-10-17 §5): the
# Owner stores the Gitea token of bifrost-mbp (made in section 1 item 1,
# named mbp-sessions, repository Read and Write) in git's credential store on
# this Mac, so that pushes from the workspace checkouts and ~/agent-work clones
# to Gitea go as bifrost-mbp once they point there (switch-local-remotes.sh,
# global-insteadof.sh).
#
#   bash scripts/gitea/store-mbp-token.sh
#
# It reads the token without echo from the terminal and refuses when stdin is
# not one. Before it stores anything it asks Gitea, with the token, who it is:
#   - GET /api/v1/user is bifrost-mbp; or, when that answers 403 because the
#     token has no user scope (Gitea 1.21 puts /user behind it; the planned
#     token has repository only), on bifrost/primary-probe the token's user is
#     not an administrator and may push main: of the two maintainers
#     (weitingzhao, an owner of the organization, and bifrost-mbp) only
#     bifrost-mbp is that; an agentd user may not push main (review 259 C3)
#   - the git push handshake on primary-probe
#     (info/refs?service=git-receive-pack) answers 200. The handshake lists
#     refs; nothing is pushed. primary-probe, because a pull mirror refuses the
#     handshake to everyone.
# It needs a credential helper (osxkeychain on this Mac) and refuses
# credential.useHttpPath (an entry per path would not serve the other
# repositories). It stores with git credential approve, then, in each checkout
# of CHECK_REPOS under the workspace, asks git what it would use for that
# repository's Gitea address, with prompts off: user bifrost-mbp and this
# token, and no http.extraHeader for the address, or it stops and says what
# answered instead (review 259 B1). The token reaches curl as a config on stdin
# (curl -q: no ~/.curlrc) and git on stdin; it is never printed, and xtrace is
# off while it is held (review 259 C4).
set -euo pipefail
set +x

LOGIN="${MBP_LOGIN:-bifrost-mbp}"
BASE="${GITEA_PUBLIC_BASE:-http://192.168.10.73:30300/bifrost}"
PROBE_REPO="${PROBE_REPO:-primary-probe}"
CHECK_REPOS="${CHECK_REPOS:-bifrost-platform bifrost-ui}"
WORKSPACE="${BIFROST_WORKSPACE:-${HOME}/Desktop/stocks}"
server="$(printf '%s' "${BASE}" | sed -nE 's#^(https?)://([^/]+)/(.+)$#\1 \2 \3#p')"
[[ -n "${server}" ]] || { echo "ERROR: cannot read the server of ${BASE}" >&2; exit 1; }
read -r proto host org <<< "${server}"
root="${proto}://${host}"

die() { echo "ERROR: $*" >&2; echo "Nothing was stored." >&2; exit 1; }

[[ -t 0 ]] || die "stdin is not a terminal; run it in a terminal tab"
helpers="$(git config --get-all credential.helper || true)"
[[ -n "${helpers}" ]] || die "git has no credential helper (git config credential.helper): approve would store nothing"
[[ "$(git config --type=bool --get credential.useHttpPath || echo false)" != true ]] \
  || die "credential.useHttpPath is true in your git config: the token would be stored for one path only"
echo "ok    credential helper: $(printf '%s' "${helpers}" | tr '\n' ' ')"

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
  # only the missing-scope refusal (review 260 C3); any other 403 stops below
  code="$(ask token "${root}/api/v1/repos/${org}/${PROBE_REPO}")"
  [[ "${code}" == 200 ]] || die "GET /api/v1/repos/${org}/${PROBE_REPO} → HTTP ${code}: the token cannot read the repository"
  [[ "$(field permissions.admin)" == false ]] || die "the token's user is an administrator of ${org}/${PROBE_REPO}: not ${LOGIN}"
  code="$(ask token "${root}/api/v1/repos/${org}/${PROBE_REPO}/branches/main")"
  [[ "${code}" == 200 ]] || die "GET …/${PROBE_REPO}/branches/main → HTTP ${code}"
  [[ "$(field user_can_push)" == true ]] || die "the token's user may not push main of ${PROBE_REPO}: not ${LOGIN} (an agentd user?)"
  echo "ok    token of a maintainer who is not an administrator: ${LOGIN} (no user scope, so read from what it may do)"
else
  die "Gitea GET /api/v1/user → HTTP ${code}: the token is not accepted ($(head -c 200 "${work}/body" | tr -d '\n'))"
fi
code="$(ask basic "${BASE}/${PROBE_REPO}.git/info/refs?service=git-receive-pack")"
[[ "${code}" == 200 ]] || die "push handshake on ${PROBE_REPO} → HTTP ${code} (token without repository Read and Write, or ${LOGIN} not in team maintainers?)"
echo "ok    can push to ${PROBE_REPO} (handshake only)"

printf 'protocol=%s\nhost=%s\nusername=%s\npassword=%s\n\n' "${proto}" "${host}" "${LOGIN}" "${t}" | git credential approve

# What git uses for a push to each repository: the remotes carry no username,
# so ask with the whole address and nothing else, in that checkout (its own
# config counts too): the workspace checkout of each of CHECK_REPOS, and every
# independent clone of one of them under AGENT_WORK (review 260 B1).
bad=0
checked=0
check_dir() { # REPO DIR LABEL
  local repo="$1" dir="$2" label="$3" url answer got_user got_pass header
  url="${BASE}/${repo}.git"
  answer="$(cd "${dir}" && printf 'url=%s\n\n' "${url}" | GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false SSH_ASKPASS=/usr/bin/false git credential fill 2> /dev/null || true)"
  got_user="$(printf '%s\n' "${answer}" | sed -n 's/^username=//p' | head -1)"
  got_pass="$(printf '%s\n' "${answer}" | sed -n 's/^password=//p' | head -1)"
  header="$(cd "${dir}" && git config --get-urlmatch http.extraHeader "${url}" || true)"
  checked=$((checked + 1))
  if [[ -n "${header}" ]]; then
    echo "FAIL  ${label}: http.extraHeader is set for ${url}; git would send that as well" >&2
    bad=1
  elif [[ "${got_user}" != "${LOGIN}" || "${got_pass}" != "${t}" ]]; then
    if [[ "${got_user}" == "${LOGIN}" ]]; then got_user="${LOGIN}' with another password"; else got_user="${got_user:-nobody}'"; fi
    echo "FAIL  ${label}: git answers user '${got_user} for ${url}" >&2
    bad=1
  else
    echo "ok    ${label}: git pushes to ${url} as ${LOGIN}"
  fi
}
for repo in ${CHECK_REPOS}; do
  if git -C "${WORKSPACE}/${repo}" rev-parse --git-dir > /dev/null 2>&1; then
    check_dir "${repo}" "${WORKSPACE}/${repo}" "${repo}"
  else
    check_dir "${repo}" "${work}" "${repo} (no checkout; global config)"
  fi
done
AGENT_WORK="${AGENT_WORK:-${HOME}/agent-work}"
if [[ -d "${AGENT_WORK}" ]]; then
  while IFS= read -r -d '' gitpath; do
    dir="${gitpath%/.git}"
    origin="$(git -C "${dir}" config --get remote.origin.url 2> /dev/null || true)"
    for repo in ${CHECK_REPOS}; do
      case "${origin}" in
        *github.com[:/]*/"${repo}".git | *github.com[:/]*/"${repo}" | "${BASE}/${repo}.git") check_dir "${repo}" "${dir}" "${dir#"${HOME}"/}" ;;
      esac
    done
  done < <(find "${AGENT_WORK}" -maxdepth 4 -name .git -prune -print0 2> /dev/null)
fi
unset t got_pass answer
if [[ "${bad}" != 0 ]]; then
  echo "ERROR: the token is stored, but git would not use it everywhere above. Another entry for ${host} may come first:" >&2
  echo "remove it in Keychain Access (search ${host%%:*}), or the setting named above, and run this again." >&2
  exit 1
fi
echo "==> git now pushes to ${root} as ${LOGIN} from the ${checked} checkout(s) above. Say 「令牌存好了」 in the thread."
