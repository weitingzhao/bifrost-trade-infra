#!/usr/bin/env bash
# switch-local-remotes.sh [--back] <repo>... — batch step 9
# (CUT-gitea-primary-2026-10-17): in each checkout of the workspace
# (BIFROST_WORKSPACE, default ~/Desktop/stocks; its worktrees share the
# config), origin becomes the Gitea repository and the GitHub address stays as
# remote github, read-only: its push address is one git cannot reach, so a
# push to it fails (preflight.js refuses it before that). Touches only remote
# config; no fetch, no push. Pushing to Gitea afterwards uses the bifrost-mbp
# token in the keychain (the Owner's steps).
#
# Every checkout is checked before any is changed. The first switch keeps a
# copy of the checkout's config beside it (config.before-gitea-primary); each
# change is made on a copy and moved into place in one step, then the push
# addresses git actually uses are read back (review 246 A4, B6). A checkout
# already on Gitea is set again, not skipped: a push address left on GitHub
# is removed. --back puts remote.origin.* and remote.github.* back exactly as
# that copy had them, and fails while git still resolves origin to something
# else (the batch's global insteadOf in ~/.gitconfig is still there; review
# 246 A5); the copy is removed only when the read-back matches.
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
saved_name="config.before-gitea-primary"
tmp=""
entries=""
trap 'rm -f "${tmp}" "${entries}"' EXIT

die() {
  echo "switch-local-remotes.sh: $*" >&2
  exit 1
}

# config_of <repo> — the config file of the checkout (shared by its worktrees)
config_of() {
  local common
  common="$(git -C "${ws}/$1" rev-parse --path-format=absolute --git-common-dir 2> /dev/null)" || return 1
  printf '%s/config\n' "${common}"
}

# values <file> <key> — every raw value of key in that file (nothing when unset)
values() {
  git config --file "$1" --get-all "$2" || [[ $? -eq 1 ]]
}

has_section() {
  git config --file "$1" --get-regexp "^$2\\." > /dev/null || return 1
}

# lines_equal <a> <b> — the same lines, in the same order
lines_equal() {
  [[ "$1" == "$2" ]]
}

# github_of <repo> <cfg> — the GitHub address to keep as remote github
github_of() {
  local saved="${2%/config}/${saved_name}" url
  if [[ -f "${saved}" ]]; then
    url="$(values "${saved}" remote.origin.url)"
  elif has_section "$2" remote.github; then
    url="$(values "$2" remote.github.url)"
  else
    url="$(values "$2" remote.origin.url)"
  fi
  case "${url}" in
    *github.com[:/]*/"$1".git | *github.com[:/]*/"$1") printf '%s\n' "${url}" ;;
    "${gitea}/$1.git" | "") printf '%s\n' "${github}/$1.git" ;;
    *) return 1 ;;
  esac
}

# check, before anything changes
for repo in "$@"; do
  cfg="$(config_of "${repo}")" || die "${repo}: no checkout at ${ws}/${repo}"
  saved="${cfg%/config}/${saved_name}"
  if [[ "${back}" -eq 1 ]]; then
    [[ -f "${saved}" ]] || die "${repo}: no ${saved}: nothing to put back"
    continue
  fi
  [[ "$(values "${cfg}" remote.origin.url | grep -c .)" -eq 1 ]] || die "${repo}: origin should have exactly one url"
  github_of "${repo}" "${cfg}" > /dev/null || die "${repo}: remote github or origin is not a GitHub address of ${repo}; look before switching"
done

for repo in "$@"; do
  cfg="$(config_of "${repo}")"
  saved="${cfg%/config}/${saved_name}"
  tmp="$(mktemp "${cfg}.XXXXXX")"
  cp "${cfg}" "${tmp}"
  if [[ "${back}" -eq 1 ]]; then
    for section in remote.origin remote.github; do
      if has_section "${tmp}" "${section}"; then git config --file "${tmp}" --remove-section "${section}"; fi
    done
    entries="$(mktemp)"
    git config --file "${saved}" --null --get-regexp '^remote\.(origin|github)\.' > "${entries}" || [[ $? -eq 1 ]]
    while IFS= read -r -d '' entry; do
      git config --file "${tmp}" --add "${entry%%$'\n'*}" "${entry#*$'\n'}"
    done < "${entries}"
    rm -f "${entries}"
    mv "${tmp}" "${cfg}"
    want_fetch="$(values "${saved}" remote.origin.url)"
    want_push="$(values "${saved}" remote.origin.pushurl)"
    [[ -n "${want_push}" ]] || want_push="${want_fetch}"
    got_fetch="$(git -C "${ws}/${repo}" remote get-url --all origin)"
    got_push="$(git -C "${ws}/${repo}" remote get-url --push --all origin)"
    if ! lines_equal "${got_fetch}" "${want_fetch}" || ! lines_equal "${got_push}" "${want_push}"; then
      die "${repo}: remotes put back as they were, but git still resolves origin to ${got_fetch} / push ${got_push}: take this batch's insteadOf lines out of ~/.gitconfig, then run --back again (${saved} is kept)"
    fi
    rm -f "${saved}"
    echo "${repo}: origin ${got_fetch} (back as before the switch)"
    continue
  fi
  gh="$(github_of "${repo}" "${cfg}")"
  [[ -f "${saved}" ]] || cp "${cfg}" "${saved}"
  git config --file "${tmp}" --unset-all remote.origin.url || [[ $? -eq 5 ]]
  git config --file "${tmp}" --unset-all remote.origin.pushurl || [[ $? -eq 5 ]]
  git config --file "${tmp}" --add remote.origin.url "${gitea}/${repo}.git"
  if has_section "${tmp}" remote.github; then git config --file "${tmp}" --remove-section remote.github; fi
  git config --file "${tmp}" --add remote.github.url "${gh}"
  git config --file "${tmp}" --add remote.github.fetch '+refs/heads/*:refs/remotes/github/*'
  git config --file "${tmp}" --add remote.github.pushurl "${no_push}"
  mv "${tmp}" "${cfg}"
  got_push="$(git -C "${ws}/${repo}" remote get-url --push --all origin)"
  got_github="$(git -C "${ws}/${repo}" remote get-url --push --all github)"
  if ! lines_equal "${got_push}" "${gitea}/${repo}.git" || ! lines_equal "${got_github}" "${no_push}"; then
    die "${repo}: switched, but git pushes origin to ${got_push} and github to ${got_github} (a pushInsteadOf in ~/.gitconfig?); --back puts it as it was"
  fi
  echo "${repo}: origin ${gitea}/${repo}.git, github ${gh} (read-only)"
done
