#!/usr/bin/env bash
# Owner only. Default dry-run; --apply performs the printed mutations.
# --check is a GET-only probe: missing/drifted/unreadable rules fail.
# S6 widens only a verified S0 infra main whitelist, preserving other settings.
case $- in *x*) { set +x; } 2>/dev/null; echo 'FAIL: xtrace is not allowed' >&2; exit 2 ;; esac
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# Credential sources unchanged: Owner's lib.sh bootstrap Secret / supplied env.
source "$HERE/lib.sh"
mode=dry-run owner=""
repos=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --owner)
      [[ $# -ge 2 && -z "$owner" ]] || gitea_die 'usage: protect-repo.sh [--dry-run|--apply|--check] --owner <login> <repo>...'
      owner="$2"; shift 2 ;;
    --dry-run|--apply|--check)
      [[ "$mode" == dry-run && -z "${mode_set:-}" ]] || gitea_die 'choose one mode'
      mode="${1#--}"; mode_set=1; shift ;;
    --*) gitea_die 'unknown option' ;;
    *) repos+=("$1"); shift ;;
  esac
done
[[ "$owner" =~ ^[A-Za-z0-9][A-Za-z0-9_-]*$ && ${#repos[@]} -gt 0 ]] || gitea_die 'usage: protect-repo.sh [--dry-run|--apply|--check] --owner <login> <repo>...'
[[ "$owner" != agentrt-* && "$owner" != bifrost-*-reader* ]] || gitea_die 'Owner login required'
for repo in "${repos[@]}"; do
  [[ "$repo" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || gitea_die 'invalid repository'
done
api() {
  # lib.sh's generic API errors may include server response text. Never echo it.
  gitea_api "$@" 2>/dev/null || gitea_die "FAIL: $1 request failed; response suppressed"
}
gitea_connect
identity="$(api GET /user)" || exit 1
python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
    ok=d.get("login")==sys.argv[1] and d.get("is_admin") is True
except (ValueError, AttributeError):
    ok=False
if not ok:
    sys.exit("FAIL: credential must belong to the named Owner administrator")
' "$owner" <<< "$identity"
fail=0
for repo in "${repos[@]}"; do
  path="/repos/${GITEA_ORG}/${repo}/branch_protections"
  existing="$(api GET "$path")" || exit 1
  # Gitea 1.21 ListBranchProtections returns the complete, unpaginated list.
  if ! actions="$(python3 "$HERE/protection_policy.py" "$mode" "$repo" "$owner" <<< "$existing")"; then
    fail=1
    continue
  fi
  if [[ "$mode" == check ]]; then
    echo "$repo: $actions"
    continue
  fi
  if [[ -z "$actions" ]]; then
    echo "$repo main: there as the baseline, left as it is"
  fi
  while IFS= read -r action; do
    [[ -n "$action" ]] || continue
    read -r method encoded <<< "$(python3 -c 'import json,sys,urllib.parse
x=json.load(sys.stdin); print(x["method"],urllib.parse.quote(x["rule"],safe=""))' <<< "$action")"
    body="$(python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["body"]))' <<< "$action")"
    endpoint="$path"
    [[ "$method" == POST ]] || endpoint="$path/$encoded"
    echo "$repo: $mode $action"
    [[ "$mode" == apply ]] || continue
    # Re-read immediately before each write. Abort on concurrent edits; Gitea
    # has no CAS for protection rules, so Owner must keep this change exclusive.
    now="$(api GET "$path")" || exit 1
    [[ "$now" == "$existing" ]] || gitea_die 'FAIL: branch rules changed during execution; stop and re-plan'
    [[ "$method" != DELETE ]] || body=""
    api "$method" "$endpoint" "$body" > /dev/null || exit 1
    existing="$(api GET "$path")" || exit 1
  done <<< "$actions"
  if [[ "$mode" == apply ]]; then
    if python3 "$HERE/protection_policy.py" check "$repo" "$owner" <<< "$existing"; then
      echo "$repo: set and read back; agent/**: removed or absent (TD-383)"
    else
      echo "$repo: READ BACK DIFFERS; stop and inspect partial changes" >&2
      fail=1
    fi
  fi
  [[ "$repo" != bifrost-platform && "$repo" != bifrost-trade-infra ]] && team='team maintainers and ' || team=''
  echo "$repo: verify tag rule on the page: Settings → Tags → *, allowed: ${team}${owner}"
done
exit "$fail"
