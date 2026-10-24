#!/usr/bin/env bash
# Prune branches across the workspace's sibling repos: origin's branches (the default mode), or
# this machine's worktrees and local branches (--local-only). origin is Gitea, the primary of every
# repository since 2026-10-17 (agent-config/gitea-primary.txt). GitHub receives only main and tags
# from the cluster; its older branches stay as they were at the cut, and this script does not touch them.
#
#   scripts/prune-merged-branches.sh                       dry run: print what would go and what stays
#   scripts/prune-merged-branches.sh --apply               back up, then delete remote branches
#   scripts/prune-merged-branches.sh --local-only [--apply] [--repos "a b"] [--offline]
#        this machine only (W-31 4.6 S2; CUT-lifecycle-2026-10-24.md §4.3): worktrees whose
#        registered session ended (new-worktree.sh) and branches made for them, judged by object
#        reachability from the refs origin holds, reflogs archived first into a run directory
#        that is never reused. Never pushes, fetches or calls gh. The rules are in
#        scripts/agent-host/lifecycle_local.py and lifecycle_items.py. Report only without --apply.
#
# The old --local (remote pruning, then worktrees removed with --force and branches deleted when a
# Change-Id or subject matched main) is gone: it lost reflog-only commits and detached work
# (review 534 A1, A2, A6). --local-only replaces it; it cannot be combined with the remote options.
#
# Remote mode. A branch counts as merged when every commit it has that main lacks (git cherry,
# patch-id) has a twin on main: the same Change-Id trailer anywhere in a main commit message
# (agent-config/scripts/git-hooks stamps one since 2026-10-06; it survives rebase, amend, a version
# bump and a squash), or, for a commit without one, the same subject. Kept regardless:
#   - a branch with an open PR, or whose tip is younger than --min-age-hours (default 24)
#   - an agent/** branch on origin: an attempt's result, which agentd deletes under the runtime's
#     rule (TD-383; CUT-gitea-primary-2026-10-17 §6), merged or not, reviewed or not
# --apply writes a bundle of every ref it deletes, plus a name -> sha list, to
# $BACKUP_ROOT/<date>/<repo>.{bundle,refs.tsv} first. Restore one: git push origin <sha>:refs/heads/<name>
# (S4 replaces this mode with --remote-only once D-L1 is decided.)
#
# Options: --repos "a b"   only these repos (default: every sibling with an origin remote)
#          --min-age-hours N
#          --reviewed FILE  also delete branches not on main that someone reviewed: each line
#                           "<repo> <branch> <40-hex sha>" (# comments and blank lines skipped); a listed
#                           branch goes only while it still names that sha (moved since: kept)
# Failed remote batches retry remaining refs individually and report deleted/refused counts.
# Pushes to no main; it only deletes branch refs. Exit 0 done, 1 a step failed, 2 usage
# (--local-only adds 3: another sweep holds the machine lock, 4: unusable configuration).
set -euo pipefail

for arg in "$@"; do
  if [[ "$arg" == --local-only ]]; then
    for other in "$@"; do
      case "$other" in
        --local-only|--apply|--offline|--repos) ;;
        --local|--reviewed|--min-age-hours)
          echo "$other cannot be combined with --local-only (it is the remote mode's option)" >&2; exit 2 ;;
      esac
    done
    here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
    exec "${LIFECYCLE_PYTHON:-python3}" "$here/agent-host/lifecycle_local.py" "$@"
  fi
done

WORKSPACE="${WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
BACKUP_ROOT="${BACKUP_ROOT:-$HOME/bifrost-backups/git-branches}"
APPLY=0
REPOS=""
MIN_AGE_HOURS=24
REVIEWED=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --local) echo "--local is gone: it removed worktrees with --force and judged branches by Change-Id; use --local-only" >&2; exit 2 ;;
    --offline) echo "--offline belongs to --local-only" >&2; exit 2 ;;
    --repos) REPOS="$2"; shift ;;
    --min-age-hours) MIN_AGE_HOURS="$2"; shift ;;
    --reviewed) REVIEWED="$2"; shift ;;
    -h|--help) sed -n '2,/^set -euo pipefail$/{/^#/p;}' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

if [[ -z "$REPOS" ]]; then
  for d in "$WORKSPACE"/*/; do
    d="${d%/}"
    if [[ -d "$d/.git" ]] && git -C "$d" remote get-url origin >/dev/null 2>&1; then REPOS="$REPOS $(basename "$d")"; fi
  done
fi

if [[ -n "$REVIEWED" ]]; then
  [[ -r "$REVIEWED" ]] || { echo "cannot read $REVIEWED" >&2; exit 2; }
  awk 'NF && $1 !~ /^#/ { if (NF != 3 || $3 !~ /^[0-9a-f]{40}$/ || $2 == "main") { print "bad line " NR ": " $0 > "/dev/stderr"; bad = 1 } } END { exit bad }' "$REVIEWED" || exit 2
fi
# reviewed_sha <repo> <branch>: the sha the branch was reviewed at, or nothing
reviewed_sha() {
  [[ -n "$REVIEWED" ]] || return 0
  awk -v r="$1" -v b="$2" 'NF == 3 && $1 == r && $2 == b { print $3; exit }' "$REVIEWED"
}

NOW=$(date +%s)
MIN_AGE_SECS=$((MIN_AGE_HOURS * 3600))
DAY=$(date +%Y-%m-%d)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
FAILED=0

# merged <repo-dir> <ref> <main-subjects-file> <main-change-ids-file>: 0 when every commit main lacks
# has a twin on main -- same Change-Id when it carries one, else same subject
merged() {
  local c subj cid
  for c in $(git -C "$1" cherry origin/main "$2" | awk '/^\+/{print $2}'); do
    cid=$(git -C "$1" log -1 --format='%(trailers:key=Change-Id,valueonly)' "$c" | head -1)
    if [[ -n "$cid" ]] && grep -Fxq -- "$cid" "$4"; then continue; fi
    subj=$(git -C "$1" log -1 --format=%s "$c")
    grep -Fxq -- "$subj" "$3" || return 1
  done
  return 0
}

for repo in $REPOS; do
  dir="$WORKSPACE/$repo"
  slug=$(git -C "$dir" remote get-url origin | sed -E 's#^(git@github.com:|https://github.com/)##; s#\.git$##')
  git -C "$dir" fetch --prune -q origin
  if ! git -C "$dir" rev-parse -q --verify origin/main >/dev/null; then
    echo "skip    $repo: origin has no main"; REPOS=$(echo " $REPOS " | sed "s/ $repo / /"); continue
  fi
  git -C "$dir" log origin/main --format=%s > "$TMP/$repo.subjects"
  # whole message, not just the trailer block: a squash keeps each folded commit's Change-Id in the body
  git -C "$dir" log origin/main --format=%B | sed -nE 's/^Change-Id: (I[0-9a-f]{40})[[:space:]]*$/\1/p' > "$TMP/$repo.changeids"
  gh pr list -R "$slug" --state open --json headRefName --jq '.[].headRefName' > "$TMP/$repo.prs" 2>/dev/null || : > "$TMP/$repo.prs"

  : > "$TMP/$repo.remote"
  while IFS='|' read -r ref ts; do
    b="${ref#origin/}"
    [[ "$b" == main || "$b" == HEAD || "$ref" == origin ]] && continue
    if [[ "$b" == agent/* ]]; then why="agentd's to delete (TD-383)"
    elif grep -Fxq -- "$b" "$TMP/$repo.prs"; then why="open PR"
    elif (( NOW - ts < MIN_AGE_SECS )); then why="younger than ${MIN_AGE_HOURS}h"
    elif ! merged "$dir" "$ref" "$TMP/$repo.subjects" "$TMP/$repo.changeids"; then
      want=$(reviewed_sha "$repo" "$b")
      if [[ -z "$want" ]]; then why="not on main"
      elif [[ "$(git -C "$dir" rev-parse "$ref")" != "$want" ]]; then why="not on main, moved since it was reviewed"
      else
        printf '  drop   %-24s %-44s %s\n' "$repo" "$b" "not on main, reviewed"
        echo "$b" >> "$TMP/$repo.remote"; continue
      fi
    else echo "$b" >> "$TMP/$repo.remote"; continue
    fi
    printf '  keep   %-24s %-44s %s\n' "$repo" "$b" "$why"
  done < <(git -C "$dir" for-each-ref --format='%(refname:short)|%(committerdate:unix)' refs/remotes/origin)

  printf '%-24s remote %3d\n' "$repo" "$(wc -l < "$TMP/$repo.remote")"
done

(( APPLY )) || { echo "dry run -- add --apply to delete"; exit 0; }

mkdir -p "$BACKUP_ROOT/$DAY"
for repo in $REPOS; do
  dir="$WORKSPACE/$repo"
  if [[ ! -s "$TMP/$repo.remote" ]]; then continue; fi
  sed 's#^#refs/remotes/origin/#' "$TMP/$repo.remote" > "$TMP/$repo.refs"
  while read -r r; do printf '%s\t%s\n' "$r" "$(git -C "$dir" rev-parse "$r")"; done < "$TMP/$repo.refs" \
    > "$BACKUP_ROOT/$DAY/$repo.refs.tsv"
  git -C "$dir" bundle create -q "$BACKUP_ROOT/$DAY/$repo.bundle" --stdin < "$TMP/$repo.refs"
  git -C "$dir" bundle verify -q "$BACKUP_ROOT/$DAY/$repo.bundle" >/dev/null
  echo "backup  $repo: $(wc -l < "$TMP/$repo.refs" | tr -d ' ') refs -> $BACKUP_ROOT/$DAY/$repo.bundle"
done

for repo in $REPOS; do
  dir="$WORKSPACE/$repo"
  if [[ -s "$TMP/$repo.remote" ]]; then
    # Keep normal pushes to 50 refs; a rejected batch must not strand its other refs.
    deleted=0
    refused=()
    batch=()
    last=$(tail -n 1 "$TMP/$repo.remote")
    while IFS= read -r b; do
      batch+=("$b")
      if (( ${#batch[@]} < 50 )) && [[ "$b" != "$last" ]]; then continue; fi
      if git -C "$dir" push -q origin --delete "${batch[@]}"; then
        deleted=$((deleted + ${#batch[@]}))
      else
        refs=("${batch[@]/#/refs/heads/}")
        # A failed push can still have deleted some refs. Only retry those still present.
        if git -C "$dir" ls-remote --heads origin "${refs[@]}" > "$TMP/$repo.remaining"; then
          known=1
        else
          known=0
        fi
        for b in "${batch[@]}"; do
          if (( known )) && ! awk '{print $2}' "$TMP/$repo.remaining" | grep -Fxq -- "refs/heads/$b"; then
            deleted=$((deleted + 1))
          elif git -C "$dir" push -q origin --delete "$b"; then
            deleted=$((deleted + 1))
          elif git -C "$dir" ls-remote --exit-code --heads origin "refs/heads/$b" > /dev/null; then
            refused+=("$b")
          else
            status=$?
            if (( status == 2 )); then
              deleted=$((deleted + 1))
            else
              refused+=("$b")
            fi
          fi
        done
      fi
      batch=()
    done < "$TMP/$repo.remote"
    printf 'remote  %s: deleted %d' "$repo" "$deleted"
    if (( ${#refused[@]} )); then
      FAILED=1
      printf ', refused %d (%s)' "${#refused[@]}" "${refused[*]}"
    fi
    printf '\n'
  fi
done
exit "$FAILED"
