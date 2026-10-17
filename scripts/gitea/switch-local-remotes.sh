#!/usr/bin/env bash
# switch-local-remotes.sh [--back] <repo>... — batch step 9
# (CUT-gitea-primary-2026-10-17): in each checkout of the workspace
# (BIFROST_WORKSPACE, default ~/Desktop/stocks; its worktrees share the
# config), origin becomes the Gitea repository and the GitHub address stays as
# remote github, read-only: its push address is one git cannot reach, so a
# push to it fails (preflight.js refuses it before that). --back puts origin
# back on GitHub and removes the github remote (the rollback). Touches only
# remote config; no fetch, no push. Pushing to Gitea afterwards uses the
# bifrost-mbp token in the keychain (the Owner's steps).
set -euo pipefail
back=0
if [[ "${1:-}" == "--back" ]]; then
  back=1
  shift
fi
[[ $# -ge 1 ]] || { echo "usage: switch-local-remotes.sh [--back] <repo>..." >&2; exit 2; }
ws="${BIFROST_WORKSPACE:-$HOME/Desktop/stocks}"
gitea="${GITEA_PUBLIC_BASE:-http://192.168.10.73:30300/bifrost}"
github="${GITHUB_BASE:-git@github.com:weitingzhao}"
no_push="no-push://github-follows-from-the-cluster"
for repo in "$@"; do
  dir="${ws}/${repo}"
  git -C "${dir}" rev-parse --git-dir > /dev/null 2>&1 || { echo "${repo}: no checkout at ${dir}" >&2; exit 1; }
  if [[ "${back}" -eq 1 ]]; then
    gh="$(git -C "${dir}" remote get-url github 2> /dev/null || echo "${github}/${repo}.git")"
    git -C "${dir}" remote set-url origin "${gh}"
    git -C "${dir}" config --unset-all remote.origin.pushurl 2> /dev/null || true
    git -C "${dir}" remote remove github 2> /dev/null || true
    echo "${repo}: origin $(git -C "${dir}" remote get-url origin) (back on GitHub)"
    continue
  fi
  old="$(git -C "${dir}" remote get-url origin)"
  if [[ "${old}" == "${gitea}/${repo}.git" ]]; then
    echo "${repo}: origin already on Gitea"
    continue
  fi
  if git -C "${dir}" remote get-url github > /dev/null 2>&1; then
    git -C "${dir}" remote set-url github "${old}"
  else
    git -C "${dir}" remote add github "${old}"
  fi
  git -C "${dir}" remote set-url --push github "${no_push}"
  git -C "${dir}" config --unset-all remote.origin.pushurl 2> /dev/null || true
  git -C "${dir}" remote set-url origin "${gitea}/${repo}.git"
  echo "${repo}: origin ${gitea}/${repo}.git, github ${old} (read-only)"
done
