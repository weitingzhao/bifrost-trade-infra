#!/bin/sh
# Wire the lineage hooks into every workspace repo (local git config only; idempotent).
#
#   repos without their own hooks dir → core.hooksPath = this directory
#   repos with husky / .githooks      → leave core.hooksPath alone (npm install rewrites
#                                       it anyway); a committed stub forwards to
#                                       bifrost.hooksDir, so it is a no-op on CI and on
#                                       machines that never ran this script
#
# Usage: sh install.sh [--check]
hooks=$(cd "$(dirname "$0")" && pwd -P)
root=$(cd "$hooks/../../../.." && pwd -P)
check=${1-}
rc=0
for repo in "$root"/bifrost-*/; do
  repo=${repo%/}
  name=$(basename "$repo")
  [ -e "$repo/.git" ] || continue
  [ "$name" = bifrost-analytics ] && continue   # archived
  cur=$(git -C "$repo" config --get core.hooksPath)
  case "$cur" in
    "" | "$hooks")
      custom=$(ls "$repo/.git/hooks" 2>/dev/null | grep -v '\.sample$')
      if [ -n "$custom" ]; then
        echo "✗ $name: .git/hooks has $custom — not overriding"; rc=1; continue
      fi
      if [ "$check" != --check ]; then
        git -C "$repo" config core.hooksPath "$hooks"
        git -C "$repo" config bifrost.hooksDir "$hooks"
      fi
      [ "$(git -C "$repo" config --get core.hooksPath)" = "$hooks" ] && echo "✓ $name: core.hooksPath" \
        || { echo "✗ $name: core.hooksPath not set"; rc=1; } ;;
    *)
      dir=$cur; [ "$cur" = .husky/_ ] && dir=.husky
      [ "$check" != --check ] && git -C "$repo" config bifrost.hooksDir "$hooks"
      missing=""
      for h in prepare-commit-msg commit-msg; do
        [ -f "$repo/$dir/$h" ] || missing="$missing $h"
      done
      if [ -n "$missing" ]; then echo "✗ $name: hooksPath=$cur, stub missing:$missing"; rc=1
      elif [ "$(git -C "$repo" config --get bifrost.hooksDir)" != "$hooks" ]; then echo "✗ $name: bifrost.hooksDir not set"; rc=1
      else echo "✓ $name: $dir stub"; fi ;;
  esac
done
exit $rc
