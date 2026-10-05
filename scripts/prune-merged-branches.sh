#!/usr/bin/env bash
# Prune branches that main already carries, across the workspace's sibling repos: GitHub branches,
# then this Mac's worktrees and local branches. Gitea mirrors GitHub (pull mirror, 8h) and follows
# on its next sync -- `make k3s-sync-gitea-mirrors` makes that immediate.
#
#   scripts/prune-merged-branches.sh                 dry run: print what would go and what stays
#   scripts/prune-merged-branches.sh --apply         back up, then delete remote branches
#   scripts/prune-merged-branches.sh --apply --local also remove merged worktrees + local branches
#
# A branch counts as merged when every commit it has that main lacks (git cherry, patch-id) has a
# commit of the same subject on main -- lanes are rebased or folded into a batch before they land,
# so their patch ids change but their subjects stay. Kept regardless:
#   - a branch with an open PR, or whose tip is younger than --min-age-hours (default 24)
#   - a worktree with a file changed in the last --min-age-hours, a process running from it, or
#     changes other than an untracked node_modules
# --apply writes a bundle of every ref it deletes, plus a name -> sha list, to
# $BACKUP_ROOT/<date>/<repo>.{bundle,refs.tsv} first. Restore one: git push origin <sha>:refs/heads/<name>
#
# Options: --repos "a b"   only these repos (default: every sibling with an origin remote)
#          --min-age-hours N
# Pushes to no main; it only deletes branch refs. Exit 0 done, 1 a step failed, 2 usage.
set -euo pipefail

WORKSPACE="${WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
BACKUP_ROOT="${BACKUP_ROOT:-$HOME/bifrost-backups/git-branches}"
APPLY=0
LOCAL=0
REPOS=""
MIN_AGE_HOURS=24

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --local) LOCAL=1 ;;
    --repos) REPOS="$2"; shift ;;
    --min-age-hours) MIN_AGE_HOURS="$2"; shift ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
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

NOW=$(date +%s)
MIN_AGE_SECS=$((MIN_AGE_HOURS * 3600))
DAY=$(date +%Y-%m-%d)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
FAILED=0

# merged <repo-dir> <ref> <main-subjects-file>: 0 when every commit main lacks has a same-subject twin on main
merged() {
  local c subj
  for c in $(git -C "$1" cherry origin/main "$2" | awk '/^\+/{print $2}'); do
    subj=$(git -C "$1" log -1 --format=%s "$c")
    grep -Fxq -- "$subj" "$3" || return 1
  done
  return 0
}

# worktree_quiet <path>: 0 when nothing but an untracked node_modules differs and nothing changed lately
worktree_quiet() {
  [[ -z "$(git -C "$1" status --porcelain | grep -v -E '^\?\? (.*/)?node_modules/?$')" ]] || return 1
  # a process still running from it (a forgotten vite preview) writes nothing for days
  ! lsof -d cwd -Fn 2>/dev/null | grep -Fq -- "n$1" || return 1
  [[ -z "$(find "$1" -maxdepth 4 -newermt "-${MIN_AGE_HOURS} hours" -not -path '*/node_modules*' -not -path '*/.git*' 2>/dev/null | head -1)" ]]
}

for repo in $REPOS; do
  dir="$WORKSPACE/$repo"
  slug=$(git -C "$dir" remote get-url origin | sed -E 's#^(git@github.com:|https://github.com/)##; s#\.git$##')
  git -C "$dir" fetch --prune -q origin
  if ! git -C "$dir" rev-parse -q --verify origin/main >/dev/null; then
    echo "skip    $repo: origin has no main"; REPOS=$(echo " $REPOS " | sed "s/ $repo / /"); continue
  fi
  git -C "$dir" log origin/main --format=%s > "$TMP/$repo.subjects"
  gh pr list -R "$slug" --state open --json headRefName --jq '.[].headRefName' > "$TMP/$repo.prs" 2>/dev/null || : > "$TMP/$repo.prs"

  : > "$TMP/$repo.remote"
  while IFS='|' read -r ref ts; do
    b="${ref#origin/}"
    [[ "$b" == main || "$b" == HEAD || "$ref" == origin ]] && continue
    if grep -Fxq -- "$b" "$TMP/$repo.prs"; then why="open PR"
    elif (( NOW - ts < MIN_AGE_SECS )); then why="younger than ${MIN_AGE_HOURS}h"
    elif ! merged "$dir" "$ref" "$TMP/$repo.subjects"; then why="not on main"
    else echo "$b" >> "$TMP/$repo.remote"; continue
    fi
    printf '  keep   %-24s %-44s %s\n' "$repo" "$b" "$why"
  done < <(git -C "$dir" for-each-ref --format='%(refname:short)|%(committerdate:unix)' refs/remotes/origin)

  : > "$TMP/$repo.worktrees"
  : > "$TMP/$repo.local"
  if (( LOCAL )); then
    while IFS=$'\t' read -r path br; do
      [[ "$path" == "$dir" ]] && continue
      if [[ "$br" == "(detached)" ]]; then
        git -C "$dir" merge-base --is-ancestor "$(git -C "$path" rev-parse HEAD)" origin/main || { printf '  keep   %-24s %-44s %s\n' "$repo" "$path" "detached, not on main"; continue; }
      elif ! merged "$dir" "refs/heads/$br" "$TMP/$repo.subjects"; then
        printf '  keep   %-24s %-44s %s\n' "$repo" "$path" "$br not on main"; continue
      fi
      if ! worktree_quiet "$path"; then printf '  keep   %-24s %-44s %s\n' "$repo" "$path" "changes or recent edits"; continue; fi
      printf '%s\t%s\n' "$path" "$br" >> "$TMP/$repo.worktrees"
    done < <(git -C "$dir" worktree list --porcelain | awk '/^worktree /{p=substr($0,10)} /^branch /{b=substr($2,12)} /^detached/{b="(detached)"} /^$/{print p"\t"b; p="";b=""}')

    # local branches: merged, not main, not checked out in a worktree that stays
    git -C "$dir" for-each-ref --format='%(refname:short)' refs/heads | while read -r b; do
      [[ "$b" == main ]] && continue
      out=$(git -C "$dir" worktree list --porcelain | awk -v r="refs/heads/$b" '/^worktree /{p=substr($0,10)} $1=="branch" && $2==r {print p}')
      if [[ -n "$out" ]] && ! grep -Fq -- "$out"$'\t' "$TMP/$repo.worktrees"; then continue; fi
      if merged "$dir" "refs/heads/$b" "$TMP/$repo.subjects"; then echo "$b" >> "$TMP/$repo.local"; fi
    done
  fi

  printf '%-24s remote %3d   worktrees %3d   local %3d\n' "$repo" \
    "$(wc -l < "$TMP/$repo.remote")" "$(wc -l < "$TMP/$repo.worktrees")" "$(wc -l < "$TMP/$repo.local")"
done

(( APPLY )) || { echo "dry run -- add --apply to delete"; exit 0; }

mkdir -p "$BACKUP_ROOT/$DAY"
for repo in $REPOS; do
  dir="$WORKSPACE/$repo"
  if [[ ! -s "$TMP/$repo.remote" && ! -s "$TMP/$repo.local" ]]; then continue; fi
  {
    sed 's#^#refs/remotes/origin/#' "$TMP/$repo.remote"
    sed 's#^#refs/heads/#' "$TMP/$repo.local"
  } > "$TMP/$repo.refs"
  while read -r r; do printf '%s\t%s\n' "$r" "$(git -C "$dir" rev-parse "$r")"; done < "$TMP/$repo.refs" \
    > "$BACKUP_ROOT/$DAY/$repo.refs.tsv"
  git -C "$dir" bundle create -q "$BACKUP_ROOT/$DAY/$repo.bundle" --stdin < "$TMP/$repo.refs"
  git -C "$dir" bundle verify -q "$BACKUP_ROOT/$DAY/$repo.bundle" >/dev/null
  echo "backup  $repo: $(wc -l < "$TMP/$repo.refs" | tr -d ' ') refs -> $BACKUP_ROOT/$DAY/$repo.bundle"
done

for repo in $REPOS; do
  dir="$WORKSPACE/$repo"
  if [[ -s "$TMP/$repo.remote" ]]; then
    # one push per 50 refs keeps the command line and GitHub's per-push limits comfortable
    xargs -n 50 git -C "$dir" push -q origin --delete < "$TMP/$repo.remote" || FAILED=1
    echo "remote  $repo: deleted $(wc -l < "$TMP/$repo.remote" | tr -d ' ')"
  fi
  if (( LOCAL )); then
    while IFS=$'\t' read -r path br; do
      git -C "$dir" worktree remove --force "$path" || FAILED=1
    done < "$TMP/$repo.worktrees"
    git -C "$dir" worktree prune
    if [[ -s "$TMP/$repo.local" ]]; then xargs git -C "$dir" branch -q -D < "$TMP/$repo.local" || FAILED=1; fi
    echo "local   $repo: worktrees $(wc -l < "$TMP/$repo.worktrees" | tr -d ' '), branches $(wc -l < "$TMP/$repo.local" | tr -d ' ')"
  fi
done
exit "$FAILED"
