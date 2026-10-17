#!/usr/bin/env bash
# compare-refs.sh <repo>... — before a batch converts these repositories
# (CUT-gitea-primary-2026-10-17, batch step 3): asks Gitea to fetch each one
# that is still a pull mirror, then compares its branches and tags with
# GitHub's. Prints "same" per repository or each difference; exits 1 on any.
# Read-only apart from the mirror fetch.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib.sh
source "$HERE/lib.sh"
[[ $# -ge 1 ]] || gitea_die "usage: compare-refs.sh <repo>..."
gitea_connect
rounds="${COMPARE_WAIT_ROUNDS:-12}"
fail=0
for repo in "$@"; do
  info="$(gitea_api GET "/repos/${GITEA_ORG}/${repo}")" || gitea_die "cannot read ${GITEA_ORG}/${repo}"
  mirror="$(python3 -c 'import json,sys; v=json.load(sys.stdin).get("mirror"); print({True: "true", False: "false"}.get(v, "?"))' <<< "${info}")"
  [[ "${mirror}" != "?" ]] || gitea_die "Gitea did not say whether ${GITEA_ORG}/${repo} is a mirror"
  if [[ "${mirror}" == true ]]; then
    gitea_api POST "/repos/${GITEA_ORG}/${repo}/mirror-sync" '{}' > /dev/null || gitea_die "mirror-sync of ${repo} refused"
  fi
  for i in $(seq 1 "${rounds}"); do
    g="$(heads_and_tags gitea "${GITEA_GIT_BASE}/${GITEA_ORG}/${repo}.git")" || gitea_die "cannot list ${repo} on Gitea"
    h="$(heads_and_tags github "${GITHUB_BASE}/${repo}.git")" || gitea_die "cannot list ${repo} on GitHub"
    [[ "${g}" == "${h}" || "${mirror}" != true || "${i}" -eq "${rounds}" ]] && break
    sleep 5 # the fetch is asynchronous
  done
  if [[ "${g}" == "${h}" ]]; then
    echo "${repo}: same ($(grep -c . <<< "${g}") branches and tags)"
  else
    echo "${repo}: DIFFERENT"
    diff <(printf '%s\n' "${g}") <(printf '%s\n' "${h}") | sed -n -e 's/^< /  Gitea:  /p' -e 's/^> /  GitHub: /p'
    fail=1
  fi
done
exit "${fail}"
