#!/usr/bin/env bash
# new-worktree.sh: make a registered worktree, end it, renew it (W-31 round 4, 4.6 S3;
# CUT-lifecycle-2026-10-24.md §4.2).
#
#   new-worktree.sh <repo> <dir> <branch> --work W-n [--base REV] [--session ID] [--purpose TEXT] [--cache-root REL]...
#   new-worktree.sh <repo> <dir> --detach <rev> --work W-n [...]
#   new-worktree.sh --end <dir> [--by WHO] [--reason TEXT]
#   new-worktree.sh --renew <dir>
#   new-worktree.sh --show <dir>
#
# The record goes into the worktree's Git admin dir (<repo>/.git/worktrees/<name>/bifrost-owner).
# A sweep (prune-merged-branches.sh --local-only) removes a worktree only after its record says
# ended. Rules, fields and environment are in new_worktree.py and worktree_owner.py beside this file.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec "${LIFECYCLE_PYTHON:-python3}" "$here/new_worktree.py" "$@"
