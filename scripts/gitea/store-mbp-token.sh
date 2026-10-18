#!/usr/bin/env bash
# store-mbp-token.sh — batch A step 6 (CUT-gitea-primary-2026-10-17 §5): the
# Owner stores the Gitea token of bifrost-mbp (made in section 1 item 1,
# named mbp-sessions) in git's credential store on this Mac, so that pushes
# from the workspace checkouts and ~/agent-work clones to Gitea go as
# bifrost-mbp once they point there (switch-local-remotes.sh,
# global-insteadof.sh).
#
#   bash scripts/gitea/store-mbp-token.sh
#
# It reads the token without echo from the terminal and refuses when stdin is
# not one. Before it stores anything it asks Gitea, with the token:
#   - GET /api/v1/user is bifrost-mbp
#   - the git push handshake on bifrost/primary-probe
#     (info/refs?service=git-receive-pack, as bifrost-mbp) answers 200: the
#     token has repository write and bifrost-mbp may push there. The handshake
#     lists refs; nothing is pushed. primary-probe, because a pull mirror
#     refuses the handshake to everyone.
# It needs a credential helper (git config credential.helper; osxkeychain on
# this Mac) and stores with git credential approve. Then it reads back what
# git would use for a push to the host, with prompts off: the username must be
# bifrost-mbp and the password this token, or it stops and says which entry
# answered instead. The token reaches curl as a config on stdin and git on
# stdin; it is never printed.
set -euo pipefail

LOGIN="${MBP_LOGIN:-bifrost-mbp}"
BASE="${GITEA_PUBLIC_BASE:-http://192.168.10.73:30300/bifrost}"
PROBE_REPO="${PROBE_REPO:-primary-probe}"
server="$(printf '%s' "${BASE}" | sed -nE 's#^(https?)://([^/]+)/.*$#\1 \2#p')"
[[ -n "${server}" ]] || { echo "ERROR: cannot read the server of ${BASE}" >&2; exit 1; }
proto="${server%% *}"
host="${server#* }"
root="${proto}://${host}"

die() { echo "ERROR: $*" >&2; echo "Nothing was stored." >&2; exit 1; }

[[ -t 0 ]] || die "stdin is not a terminal; run it in a terminal tab"
helpers="$(git config --get-all credential.helper || true)"
[[ -n "${helpers}" ]] || die "git has no credential helper (git config credential.helper): approve would store nothing"
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
  fi | curl -sS -K - --noproxy '*' -o "${work}/body" -w '%{http_code}' --max-time 30 "${url}" || echo "000"
}

code="$(ask token "${root}/api/v1/user")"
[[ "${code}" == 200 ]] || die "Gitea GET /api/v1/user → HTTP ${code}: the token is not accepted"
login="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("login",""))' "${work}/body")"
[[ "${login}" == "${LOGIN}" ]] || die "the token belongs to '${login}', not ${LOGIN}"
echo "ok    token of ${login}"
code="$(ask basic "${BASE}/${PROBE_REPO}.git/info/refs?service=git-receive-pack")"
[[ "${code}" == 200 ]] || die "push handshake on ${PROBE_REPO} → HTTP ${code} (token without repository Read and Write, or ${LOGIN} not in team maintainers?)"
echo "ok    can push to ${PROBE_REPO} (handshake only)"

printf 'protocol=%s\nhost=%s\nusername=%s\npassword=%s\n\n' "${proto}" "${host}" "${LOGIN}" "${t}" | git credential approve

# What git uses for a push there: the remotes carry no username, so ask without one.
answer="$(printf 'protocol=%s\nhost=%s\n\n' "${proto}" "${host}" | GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false SSH_ASKPASS=/usr/bin/false git credential fill 2> /dev/null || true)"
got_user="$(printf '%s\n' "${answer}" | sed -n 's/^username=//p' | head -1)"
got_pass="$(printf '%s\n' "${answer}" | sed -n 's/^password=//p' | head -1)"
if [[ "${got_user}" != "${LOGIN}" || "${got_pass}" != "${t}" ]]; then
  unset t got_pass answer
  echo "ERROR: git credential approve ran, but for ${root} git answers user '${got_user:-nobody}'$([[ "${got_user}" == "${LOGIN}" ]] && echo ' with another password')." >&2
  echo "Another entry for ${host} comes first: remove it in Keychain Access (search ${host%%:*}) and run this again." >&2
  exit 1
fi
unset t got_pass answer
echo "==> git now pushes to ${root} as ${LOGIN}. Say 「令牌存好了」 in the thread."
