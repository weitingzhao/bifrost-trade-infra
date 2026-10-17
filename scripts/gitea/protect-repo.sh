#!/usr/bin/env bash
# protect-repo.sh --owner <login> <repo>... — the two branch rules of the
# Gitea-primary cut (§2.9, §3; batch step 5) on each converted repository,
# then read back and compared field by field:
#   main      push: team maintainers and <login>; merge (PR): the same
#   agent/**  push: team agentd-write and <login>; merge (PR): maintainers and <login>
# Both rules carry a merge whitelist: without one, code write is enough to
# merge a pull request into the branch (Gitea 1.21 IsUserMergeWhitelisted).
# The tag rule (*: maintainers and <login>) has no API in 1.21: the script
# prints the page to set it on. A rule that exists is edited to this, not
# duplicated. Any other branch rule on the repository stops it for that
# repository before anything is changed: Gitea 1.21 takes the first rule that
# matches, so an older `**` or a narrower rule would decide instead of these
# (review 246 B9). Exits 1 when a repository is stopped or a read-back differs.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib.sh
source "$HERE/lib.sh"
owner=""
if [[ "${1:-}" == "--owner" && -n "${2:-}" ]]; then
  owner="$2"
  shift 2
fi
[[ -n "${owner}" && $# -ge 1 ]] || gitea_die "usage: protect-repo.sh --owner <your Gitea login> <repo>..."
# the read-back must hold every field that was set (lists in any order)
COMPARE_RULE='
import json, sys
want, got = json.loads(sys.argv[1]), json.load(sys.stdin)
norm = lambda v: sorted(v or []) if isinstance(v, list) else v
bad = [k for k, v in want.items() if (norm(got.get(k)) if isinstance(v, list) else got.get(k)) != norm(v)]
for k in bad:
    print(f"    {k}: want {want[k]!r}, Gitea has {got.get(k)!r}")
sys.exit(1 if bad else 0)
'
gitea_connect
fail=0
for repo in "$@"; do
  existing="$(gitea_api GET "/repos/${GITEA_ORG}/${repo}/branch_protections")" || gitea_die "cannot read the rules of ${repo}"
  others="$(python3 -c 'import json,sys; print(" ".join(sorted(str(r.get("rule_name") or r.get("branch_name")) for r in json.load(sys.stdin) if (r.get("rule_name") or r.get("branch_name")) not in ("main", "agent/**"))))' <<< "${existing}")" ||
    gitea_die "cannot read the rules of ${repo}"
  if [[ -n "${others}" ]]; then
    echo "${repo}: STOPPED, nothing changed: other branch rules are there (${others}); remove them on the page or say why they stay, then run this again"
    fail=1
    continue
  fi
  for rule in main 'agent/**'; do
    if [[ "${rule}" == main ]]; then push_team=maintainers; else push_team=agentd-write; fi
    body="$(python3 - "${rule}" "${push_team}" "${owner}" << 'PY'
import json, sys
rule, team, owner = sys.argv[1:4]
print(json.dumps({
    "rule_name": rule,
    "enable_push": True,
    "enable_push_whitelist": True,
    "push_whitelist_teams": [team],
    "push_whitelist_usernames": [owner],
    "push_whitelist_deploy_keys": False,
    "enable_merge_whitelist": True,
    "merge_whitelist_teams": ["maintainers"],
    "merge_whitelist_usernames": [owner],
}))
PY
)"
    enc="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "${rule}")"
    existing="$(gitea_api GET "/repos/${GITEA_ORG}/${repo}/branch_protections")" || gitea_die "cannot read the rules of ${repo}"
    if python3 -c 'import json,sys; sys.exit(0 if any(r.get("rule_name") == sys.argv[1] for r in json.load(sys.stdin)) else 1)' "${rule}" <<< "${existing}"; then
      gitea_api PATCH "/repos/${GITEA_ORG}/${repo}/branch_protections/${enc}" "${body}" > /dev/null || gitea_die "${repo} ${rule}: edit refused"
    else
      gitea_api POST "/repos/${GITEA_ORG}/${repo}/branch_protections" "${body}" > /dev/null || gitea_die "${repo} ${rule}: create refused"
    fi
    got="$(gitea_api GET "/repos/${GITEA_ORG}/${repo}/branch_protections/${enc}")" || gitea_die "${repo} ${rule}: cannot read it back"
    if python3 -c "${COMPARE_RULE}" "${body}" <<< "${got}"; then
      echo "${repo} ${rule}: set and read back"
    else
      echo "${repo} ${rule}: READ BACK DIFFERS"
      fail=1
    fi
  done
  echo "${repo}: now add the tag rule on the page: Gitea → ${GITEA_ORG}/${repo} → Settings → Tags → New rule: *, allowed: team maintainers and ${owner}"
done
exit "${fail}"
