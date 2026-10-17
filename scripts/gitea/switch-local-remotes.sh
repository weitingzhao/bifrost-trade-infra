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
# Each checkout's config is locked the way git locks it (config.lock) from the
# first check to the end, so no other run or git command writes it meanwhile
# (review 248 B5). Every checkout is checked before any is changed, the new
# config included: it is tried in a scratch repository under the same global
# and system config, and must push origin to Gitea and github nowhere (review
# 248 A3). The first switch keeps a copy of the checkout's config beside it
# (config.before-gitea-primary, created only if absent); each change is made
# on a copy and moved into place; if a checkout then pushes anywhere else,
# every checkout this run changed is put back as it was. A checkout already on
# Gitea is set again, not skipped (review 246 A4). Remote keys with no value
# are refused rather than restored wrongly (review 248 B4).
#
# --back puts remote.origin.* and remote.github.* back exactly as the copy had
# them (compared byte for byte before it is moved into place), and fails,
# keeping the copy, while git still resolves origin to something else: the
# batch's global insteadOf in ~/.gitconfig is still there (review 246 A5).
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
REMOTES='^remote\.(origin|github)\.'

locks=()
scratch="$(mktemp -d)"
changed_cfg=()
changed_prev=()
changed_saved=()

cleanup() {
  local f
  for f in "${locks[@]+"${locks[@]}"}"; do rm -f "${f}" "${f%.lock}.tmp-gitea-primary"; done
  rm -rf "${scratch}"
}
trap cleanup EXIT

die() {
  echo "switch-local-remotes.sh: $*" >&2
  exit 1
}

# undo_and_die <message> — puts back every config this run replaced, then stops
undo_and_die() {
  local i
  for ((i = ${#changed_cfg[@]} - 1; i >= 0; i--)); do
    install_config "${changed_prev[$i]}" "${changed_cfg[$i]}"
    [[ -z "${changed_saved[$i]}" ]] || rm -f "${changed_saved[$i]}"
  done
  die "$* (every checkout this run changed is back as it was)"
}

# install_config <file> <cfg> — cfg becomes a copy of file in one step (a rename in cfg's directory)
install_config() {
  cp "$1" "$2.tmp-gitea-primary" && mv "$2.tmp-gitea-primary" "$2"
}

# config_of <repo> — the config file of the checkout (shared by its worktrees)
config_of() {
  local common
  common="$(git -C "${ws}/$1" rev-parse --path-format=absolute --git-common-dir 2> /dev/null)" || return 1
  printf '%s/config\n' "${common}"
}

# lock <cfg> — git's own lock on that config file, held until this script ends
lock() {
  (set -o noclobber && : > "$1.lock") 2> /dev/null || die "$1 is locked (git, or another run, is writing it); try again"
  locks+=("$1.lock")
}

# values <file> <key> — every raw value of key in that file (nothing when unset)
values() {
  git config --file "$1" --get-all "$2" || [[ $? -eq 1 ]]
}

has_section() {
  git config --file "$1" --get-regexp "^$2\\." > /dev/null || return 1
}

# dump <file> <out> — the remote.origin.* and remote.github.* entries, NUL-separated
dump() {
  git config --file "$1" --null --get-regexp "${REMOTES}" > "$2" || [[ $? -eq 1 ]]
}

# valueless <dump> — succeeds when an entry has no value (no newline after its key)
valueless() {
  python3 -c 'import sys; d = open(sys.argv[1], "rb").read().split(b"\0"); sys.exit(0 if any(e and b"\n" not in e for e in d) else 1)' "$1"
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

# switched <cfg> <out> <repo> <github address> — the config with origin on Gitea and github read-only
switched() {
  cp "$1" "$2"
  git config --file "$2" --unset-all remote.origin.url || [[ $? -eq 5 ]]
  git config --file "$2" --unset-all remote.origin.pushurl || [[ $? -eq 5 ]]
  git config --file "$2" --add remote.origin.url "${gitea}/$3.git"
  if has_section "$2" remote.github; then git config --file "$2" --remove-section remote.github; fi
  git config --file "$2" --add remote.github.url "$4"
  git config --file "$2" --add remote.github.fetch '+refs/heads/*:refs/remotes/github/*'
  git config --file "$2" --add remote.github.pushurl "${no_push}"
}

# pushes_right <git dir option> <repo> — origin pushes only to Gitea, github only to no_push
pushes_right() {
  local origin gh
  origin="$(git "$1" remote get-url --push --all origin)" || return 1
  gh="$(git "$1" remote get-url --push --all github)" || return 1
  [[ "${origin}" == "${gitea}/$2.git" && "${gh}" == "${no_push}" ]] || {
    echo "origin pushes to ${origin}, github to ${gh}"
    return 1
  }
}

# check, before anything changes
for repo in "$@"; do
  cfg="$(config_of "${repo}")" || die "${repo}: no checkout at ${ws}/${repo}"
  lock "${cfg}"
  saved="${cfg%/config}/${saved_name}"
  if [[ "${back}" -eq 1 ]]; then
    [[ -f "${saved}" ]] || die "${repo}: no ${saved}: nothing to put back"
    dump "${saved}" "${scratch}/${repo}.saved"
    ! valueless "${scratch}/${repo}.saved" || die "${repo}: ${saved} has a remote key with no value; put it back by hand"
    continue
  fi
  dump "${cfg}" "${scratch}/${repo}.now"
  ! valueless "${scratch}/${repo}.now" || die "${repo}: a remote.origin or remote.github key has no value; give it one (true) first"
  [[ "$(values "${cfg}" remote.origin.url | grep -c .)" -eq 1 ]] || die "${repo}: origin should have exactly one url"
  gh="$(github_of "${repo}" "${cfg}")" || die "${repo}: remote github or origin is not a GitHub address of ${repo}; look before switching"
  try="${scratch}/${repo}.try"
  git init -q "${try}"
  switched "${cfg}" "${try}/.git/config" "${repo}" "${gh}"
  why="$(pushes_right "--git-dir=${try}/.git" "${repo}")" || die "${repo}: after the switch ${why:-git could not read the remotes} (a pushInsteadOf or insteadOf in ~/.gitconfig?); nothing changed"
done

for repo in "$@"; do
  cfg="$(config_of "${repo}")"
  saved="${cfg%/config}/${saved_name}"
  tmp="$(mktemp "${scratch}/${repo}.XXXXXX")"
  if [[ "${back}" -eq 1 ]]; then
    cp "${cfg}" "${tmp}"
    for section in remote.origin remote.github; do
      if has_section "${tmp}" "${section}"; then git config --file "${tmp}" --remove-section "${section}"; fi
    done
    while IFS= read -r -d '' entry; do
      git config --file "${tmp}" --add "${entry%%$'\n'*}" "${entry#*$'\n'}"
    done < "${scratch}/${repo}.saved"
    dump "${tmp}" "${scratch}/${repo}.restored"
    cmp -s "${scratch}/${repo}.saved" "${scratch}/${repo}.restored" || die "${repo}: the remotes could not be rebuilt exactly from ${saved}; nothing changed"
    install_config "${tmp}" "${cfg}"
    want_fetch="$(values "${saved}" remote.origin.url)"
    want_push="$(values "${saved}" remote.origin.pushurl)"
    [[ -n "${want_push}" ]] || want_push="${want_fetch}"
    got_fetch="$(git -C "${ws}/${repo}" remote get-url --all origin)"
    got_push="$(git -C "${ws}/${repo}" remote get-url --push --all origin)"
    if [[ "${got_fetch}" != "${want_fetch}" || "${got_push}" != "${want_push}" ]]; then
      die "${repo}: remotes put back as they were, but git still resolves origin to ${got_fetch} / push ${got_push}: take this batch's insteadOf lines out of ~/.gitconfig, then run --back again (${saved} is kept)"
    fi
    rm -f "${saved}"
    echo "${repo}: origin ${got_fetch} (back as before the switch)"
    continue
  fi
  gh="$(github_of "${repo}" "${cfg}")"
  prev="${scratch}/${repo}.prev"
  cp "${cfg}" "${prev}"
  made=""
  if [[ ! -f "${saved}" ]]; then
    (set -o noclobber && cat "${cfg}" > "${saved}") || undo_and_die "${repo}: cannot keep ${saved}"
    made="${saved}"
  fi
  changed_cfg+=("${cfg}")
  changed_prev+=("${prev}")
  changed_saved+=("${made}")
  switched "${cfg}" "${tmp}" "${repo}" "${gh}"
  install_config "${tmp}" "${cfg}"
  why="$(pushes_right "--git-dir=${cfg%/config}" "${repo}")" || undo_and_die "${repo}: after the switch ${why:-git could not read the remotes}"
  echo "${repo}: origin ${gitea}/${repo}.git, github ${gh} (read-only)"
done
