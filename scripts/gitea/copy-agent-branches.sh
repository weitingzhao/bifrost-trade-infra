#!/usr/bin/env bash
# copy-agent-branches.sh <repo> — batch A, between the conversion and protect-repo.sh (CUT-gitea-primary-2026-10-17):
# copies every refs/heads/agent/* of <agent org>/<repo> (bifrost-agents) to
# bifrost/<repo>, so that earlier attempts' branches, check tasks' bases and
# lineage are still found once agentd pushes there. Copies only: never
# forced, nothing deleted on either side; a branch already in bifrost/<repo>
# at the same commit is skipped, at another commit is reported and left. Run
# it before protect-repo.sh sets the agent/** rule: the rule's push whitelist
# (team agentd-write and the Owner) does not hold the admin account whose
# token this pushes with, and Gitea 1.21 lets no admin past a whitelist.
# Exits 1 on any difference.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib.sh
source "$HERE/lib.sh"
[[ $# -eq 1 ]] || gitea_die "usage: copy-agent-branches.sh <repo>"
repo="$1"
agent_org="${GITEA_AGENT_ORG:-bifrost-agents}"
gitea_connect
from="${GITEA_GIT_BASE}/${agent_org}/${repo}.git"
to="${GITEA_GIT_BASE}/${GITEA_ORG}/${repo}.git"
work="$(mktemp -d)"
trap 'rm -rf "${work}"; kill "${GITEA_PF_PID:-}" 2> /dev/null || true' EXIT
git init -q --bare "${work}/r.git"
git -C "${work}/r.git" fetch -q --no-tags "${from}" "+refs/heads/agent/*:refs/heads/agent/*" || gitea_die "cannot fetch the agent branches of ${agent_org}/${repo}"
there="$(git ls-remote --refs "${to}" 'refs/heads/agent/*')" || gitea_die "cannot list ${GITEA_ORG}/${repo}"
copied=0 same=0 differ=0
while read -r sha ref; do
  [[ -n "${ref}" ]] || continue
  cur="$(awk -v r="${ref}" '$2 == r { print $1 }' <<< "${there}")"
  if [[ "${cur}" == "${sha}" ]]; then
    same=$((same + 1))
  elif [[ -n "${cur}" ]]; then
    echo "DIFFERS ${ref}: ${agent_org} ${sha}, ${GITEA_ORG} ${cur}; left as it is"
    differ=$((differ + 1))
  elif git -C "${work}/r.git" push -q "${to}" "${ref}:${ref}"; then
    copied=$((copied + 1))
  else
    echo "REFUSED ${ref}"
    differ=$((differ + 1))
  fi
done < <(git -C "${work}/r.git" for-each-ref --format='%(objectname) %(refname)' refs/heads/agent/)
echo "${repo}: ${copied} copied, ${same} already there, ${differ} not copied"
[[ "${differ}" -eq 0 ]]
