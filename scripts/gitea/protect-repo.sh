#!/usr/bin/env bash
# Owner only. Default dry-run; --apply performs the printed mutations.
# --check is a GET-only probe: missing/drifted/unreadable rules fail.
# S6 widens only a verified S0 infra main whitelist, preserving other settings.
case $- in *x*) { set +x; } 2>/dev/null; echo 'FAIL: xtrace is not allowed' >&2; exit 2 ;; esac
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# Credential sources unchanged: Owner's lib.sh bootstrap Secret / supplied env.
source "$HERE/lib.sh"
mode=dry-run owner="" operation=policy snapshot=""
repos=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --owner)
      [[ $# -ge 2 && -z "$owner" ]] || gitea_die 'usage: protect-repo.sh [--dry-run|--apply|--check] --owner <login> <repo>...'
      owner="$2"; shift 2 ;;
    --dry-run|--apply|--check)
      [[ "$mode" == dry-run && -z "${mode_set:-}" ]] || gitea_die 'choose one mode'
      mode="${1#--}"; mode_set=1; shift ;;
    --snapshot|--restore|--verify-snapshot)
      [[ $# -ge 2 && "$operation" == policy && -n "$2" ]] || gitea_die 'choose one snapshot operation and path'
      operation="${1#--}"; snapshot="$2"; shift 2 ;;
    --*) gitea_die 'unknown option' ;;
    *) repos+=("$1"); shift ;;
  esac
done
[[ "$owner" =~ ^[A-Za-z0-9][A-Za-z0-9_-]*$ && ${#repos[@]} -gt 0 ]] || gitea_die 'usage: protect-repo.sh [--dry-run|--apply|--check] --owner <login> <repo>...'
[[ "$owner" != agentrt-* && "$owner" != bifrost-*-reader* ]] || gitea_die 'Owner login required'
for repo in "${repos[@]}"; do
  [[ "$repo" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || gitea_die 'invalid repository'
done
if [[ "$operation" != policy ]]; then
  [[ ${#repos[@]} == 1 ]] || gitea_die 'snapshot operations require exactly one repository'
  if [[ "$operation" == restore ]]; then
    [[ "$mode" != check ]] || gitea_die 'use --verify-snapshot to check a restored state'
  else
    [[ -z "${mode_set:-}" ]] || gitea_die 'snapshot and verify-snapshot are read-only modes'
  fi
fi
api() {
  # lib.sh's generic API errors may include server response text. Never echo it.
  gitea_api "$@" 2>/dev/null || gitea_die "FAIL: $1 request failed; response suppressed"
}
state_tool() { python3 "$HERE/protection_state.py" "$@"; }
stop_partial() {
  echo "FAIL: stopped immediately; verified actions: ${verified:-none}; last attempted action: ${attempted:-none}" >&2
  if [[ -n "${current:-}" ]]; then
    state_tool summary <<< "$current" >&2 || echo 'current state: unreadable; last write may have taken effect' >&2
    if state_tool save "$record_dir/current.json" "$GITEA_ORG" "$repo" "$owner" <<< "$current"; then
      printf 'current state file: %q\n' "$record_dir/current.json" >&2
    fi
  else
    echo 'current state: unavailable; last write may have taken effect' >&2
  fi
  printf 'execution snapshot: %q\n' "$before_file" >&2
  printf 'rollback preview: bash %q --restore %q --owner %q %q\n' "$HERE/protect-repo.sh" "$before_file" "$owner" "$repo" >&2
  echo 'Keep landing disabled. Inspect the snapshot/runbook; add --apply only to execute the reviewed rollback.' >&2
  exit 1
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
  if [[ "$operation" == snapshot ]]; then
    state_tool save "$snapshot" "$GITEA_ORG" "$repo" "$owner" <<< "$existing"
    printf 'Saved read-only protection snapshot: %q\n' "$snapshot"
    continue
  elif [[ "$operation" == verify-snapshot ]]; then
    state_tool verify "$snapshot" "$GITEA_ORG" "$repo" "$owner" <<< "$existing"
    continue
  fi
  # Gitea 1.21 ListBranchProtections returns the complete, unpaginated list.
  if [[ "$operation" == restore ]]; then
    actions="$(state_tool restore "$snapshot" "$GITEA_ORG" "$repo" "$owner" <<< "$existing")" || exit 1
  elif ! actions="$(python3 "$HERE/protection_policy.py" "$mode" "$repo" "$owner" <<< "$existing")"; then
    fail=1
    continue
  fi
  if [[ "$mode" == check ]]; then
    echo "$repo: $actions"
    continue
  fi
  if [[ "$mode" == apply ]]; then
    # Local, read-only snapshot uses the initial GET; no additional API requests.
    record_dir="$(mktemp -d "${TMPDIR:-/tmp}/gitea-protection.XXXXXX")"
    before_file="$record_dir/before.json"
    state_tool save "$before_file" "$GITEA_ORG" "$repo" "$owner" <<< "$existing"
    printf 'Execution snapshot: %q\n' "$before_file"
    verified="" attempted="" current="$existing"
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
    if [[ "$operation" == restore ]]; then
      echo "$repo: $mode restore $method $encoded (values from snapshot)"
    else
      echo "$repo: $mode $action"
    fi
    [[ "$mode" == apply ]] || continue
    # Re-read immediately before each write. Abort on concurrent edits; Gitea
    # has no CAS for protection rules, so Owner must keep this change exclusive.
    current=""
    current="$(api GET "$path")" || stop_partial
    [[ "$current" == "$existing" ]] || stop_partial
    [[ "$method" != DELETE ]] || body=""
    attempted="$method $encoded"
    if ! (api "$method" "$endpoint" "$body") > /dev/null; then
      current="$(api GET "$path")" || current=""
      stop_partial
    fi
    current=""
    current="$(api GET "$path")" || stop_partial
    # Do not accept a bad readback as the new baseline. Verify the requested
    # transition AND every untouched rule before any subsequent write.
    state_tool step < <(printf '%s\n' "$existing" "$action" "$current") || stop_partial
    existing="$current"
    verified="${verified:+$verified; }$attempted"
  done <<< "$actions"
  if [[ "$mode" == apply ]]; then
    if [[ "$operation" == restore ]]; then
      state_tool verify "$snapshot" "$GITEA_ORG" "$repo" "$owner" <<< "$existing" || stop_partial
      continue
    elif python3 "$HERE/protection_policy.py" check "$repo" "$owner" <<< "$existing"; then
      echo "$repo: set and read back; agent/**: removed or absent (TD-383)"
    else
      stop_partial
    fi
  fi
  [[ "$repo" != bifrost-platform && "$repo" != bifrost-trade-infra ]] && team='team maintainers and ' || team=''
  echo "$repo: verify tag rule on the page: Settings → Tags → *, allowed: ${team}${owner}"
done
exit "$fail"
