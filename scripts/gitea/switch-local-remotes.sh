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
# One run is one transaction. Each checkout's config is locked the way git
# locks it (config.lock, created only if absent; review 248 B5, 249 C5) from
# the first check to the end. Every checkout is checked before any is
# changed: the new config is tried in a scratch repository under the same
# global and system config (review 248 A3). Each change is a new temporary
# file renamed into place (review 249 B3). After the changes every working
# tree of each repository is read back with its own config (review 249 A1);
# if any step fails, whatever the reason, every checkout this run changed is
# put back as it was before the run (review 249 B2), and if that fails too
# the earlier configs are kept and named.
#
# The first switch keeps a copy of the checkout's config beside it
# (config.before-gitea-primary, created only if absent). A checkout already on
# Gitea is set again, not skipped (review 246 A4). Remote keys with no value
# are refused (review 248 B4).
#
# --back puts remote.origin.* and remote.github.* back exactly as that copy
# had them (byte for byte, checked before anything changes) and fails while
# git would still resolve origin to something else: the batch's global
# insteadOf in ~/.gitconfig is still there (review 246 A5). The copies are
# removed only when the whole batch is back.
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
made=()
scratch="$(mktemp -d)"
changed_cfg=()
changed_prev=()
changed_saved=()
saved_to_remove=()
committed=0

say() {
  echo "switch-local-remotes.sh: $*" >&2
}

die() {
  say "$*"
  exit 1
}

# install_config <file> <cfg> — cfg becomes a copy of file: a new temporary
# file beside it, renamed into place
install_config() {
  local t
  t="$(mktemp "$2.tmp-XXXXXX")" || return 1
  [[ "${t}" == "$2".tmp-* && "${t}" != *$'\n'* ]] || return 1
  made+=("${t}")
  cp -p "$1" "${t}" && mv "${t}" "$2"
}

# rollback — every config this run replaced goes back; fails if one could not
rollback() {
  local i bad=0
  for ((i = ${#changed_cfg[@]} - 1; i >= 0; i--)); do
    if install_config "${changed_prev[$i]}" "${changed_cfg[$i]}"; then
      [[ -z "${changed_saved[$i]}" ]] || rm -f "${changed_saved[$i]}" || true
    else
      bad=1
      say "could not put back ${changed_cfg[$i]}; its config before this run is ${changed_prev[$i]}"
    fi
  done
  return "${bad}"
}

on_exit() {
  local rc=$? keep=0 f
  set +e
  if [[ "${committed}" -ne 1 && ${#changed_cfg[@]} -gt 0 ]]; then
    if rollback; then say "every checkout this run changed is back as it was before the run"; else keep=1; fi
  fi
  for f in "${made[@]+"${made[@]}"}"; do rm -f "${f}" 2> /dev/null; done
  for f in "${locks[@]+"${locks[@]}"}"; do rm -f "${f}" 2> /dev/null; done
  if [[ "${keep}" -eq 0 ]]; then rm -rf "${scratch}" 2> /dev/null; else say "kept ${scratch}"; fi
  exit "${rc}"
}
trap on_exit EXIT

# config_of <repo> — the config file of the checkout (shared by its worktrees)
config_of() {
  local common
  common="$(git -C "${ws}/$1" rev-parse --path-format=absolute --git-common-dir 2> /dev/null)" || return 1
  printf '%s/config\n' "${common}"
}

# lock <cfg> — git's own lock on that config file, held until this script
# ends; a path that is already there, of any kind, is someone else's
lock() {
  python3 -c 'import os, sys; os.close(os.open(sys.argv[1], os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))' "$1.lock" 2> /dev/null ||
    die "$1 is locked (git, or another run, is writing it); try again"
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

# github_of <repo> <cfg> — the GitHub address to keep as remote github. The
# scp form git@github.com:<owner>/<repo>.git is kept as the same address in URL
# form, ssh://git@github.com/<owner>/<repo>.git: global-insteadof.sh rewrites
# the scp and HTTPS forms to Gitea, and github would fetch from Gitea too
# (review 259 B2).
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
    *github.com[:/]*/"$1".git | *github.com[:/]*/"$1") ;;
    "${gitea}/$1.git" | "") url="${github}/$1.git" ;;
    *) return 1 ;;
  esac
  case "${url}" in
    git@github.com:*) printf 'ssh://git@github.com/%s\n' "${url#git@github.com:}" ;;
    *) printf '%s\n' "${url}" ;;
  esac
}

# switched <cfg> <out> <repo> <github address> — the config with origin on Gitea and github read-only
switched() {
  cp -p "$1" "$2"
  git config --file "$2" --unset-all remote.origin.url || [[ $? -eq 5 ]]
  git config --file "$2" --unset-all remote.origin.pushurl || [[ $? -eq 5 ]]
  git config --file "$2" --add remote.origin.url "${gitea}/$3.git"
  if has_section "$2" remote.github; then git config --file "$2" --remove-section remote.github; fi
  git config --file "$2" --add remote.github.url "$4"
  git config --file "$2" --add remote.github.fetch '+refs/heads/*:refs/remotes/github/*'
  git config --file "$2" --add remote.github.pushurl "${no_push}"
}

# restored <cfg> <saved dump> <out> — the config with the two remotes as the saved copy had them
restored() {
  local entry section
  cp -p "$1" "$3"
  for section in remote.origin remote.github; do
    if has_section "$3" "${section}"; then git config --file "$3" --remove-section "${section}"; fi
  done
  while IFS= read -r -d '' entry; do
    git config --file "$3" --add "${entry%%$'\n'*}" "${entry#*$'\n'}"
  done < "$2"
}

# switched_right <repo> <git args…> — origin pushes only to Gitea, github only to no_push
switched_right() {
  local repo="$1" origin gh
  shift
  origin="$(git "$@" remote get-url --push --all origin)" || return 1
  gh="$(git "$@" remote get-url --push --all github)" || return 1
  [[ "${origin}" == "${gitea}/${repo}.git" && "${gh}" == "${no_push}" ]] || {
    echo "origin pushes to ${origin}, github to ${gh}"
    return 1
  }
}

# back_right <saved> <git args…> — origin fetches and pushes as the saved copy says
back_right() {
  local saved="$1" want_fetch want_push got_fetch got_push
  shift
  want_fetch="$(values "${saved}" remote.origin.url)"
  want_push="$(values "${saved}" remote.origin.pushurl)"
  [[ -n "${want_push}" ]] || want_push="${want_fetch}"
  got_fetch="$(git "$@" remote get-url --all origin)" || return 1
  got_push="$(git "$@" remote get-url --push --all origin)" || return 1
  [[ "${got_fetch}" == "${want_fetch}" && "${got_push}" == "${want_push}" ]] || {
    echo "git resolves origin to ${got_fetch} / push ${got_push}, the saved copy says ${want_fetch} / push ${want_push}"
    return 1
  }
}

# every_worktree <repo> <check> [arg] — runs the check in each working tree of the repository
every_worktree() {
  local repo="$1" check="$2" list="${scratch}/${1}.worktrees" wt why
  shift 2
  # NUL-separated: a working tree's path may hold a newline (review 250 A1)
  git -C "${ws}/${repo}" worktree list --porcelain -z > "${list}" || return 1
  while IFS= read -r -d '' wt; do
    [[ "${wt}" == "worktree "* ]] || continue
    wt="${wt#worktree }"
    [[ -d "${wt}" ]] || continue
    if [[ "${check}" == switched ]]; then
      why="$(switched_right "${repo}" -C "${wt}")" || { echo "in ${wt}: ${why:-git could not read the remotes}"; return 1; }
    else
      why="$(back_right "$1" -C "${wt}")" || { echo "in ${wt}: ${why:-git could not read the remotes}"; return 1; }
    fi
  done < "${list}"
}

# check, before anything changes
for repo in "$@"; do
  cfg="$(config_of "${repo}")" || die "${repo}: no checkout at ${ws}/${repo}"
  lock "${cfg}"
  saved="${cfg%/config}/${saved_name}"
  if [[ -L "${saved}" ]] || { [[ -e "${saved}" ]] && [[ ! -f "${saved}" ]]; }; then
    die "${repo}: ${saved} is there but is not a plain file; look at it first"
  fi
  try="${scratch}/${repo}.try"
  git init -q "${try}"
  if [[ "${back}" -eq 1 ]]; then
    [[ -f "${saved}" ]] || die "${repo}: no ${saved}: nothing to put back"
    dump "${saved}" "${scratch}/${repo}.saved"
    ! valueless "${scratch}/${repo}.saved" || die "${repo}: ${saved} has a remote key with no value; put it back by hand"
    restored "${cfg}" "${scratch}/${repo}.saved" "${try}/.git/config"
    dump "${try}/.git/config" "${scratch}/${repo}.rebuilt"
    cmp -s "${scratch}/${repo}.saved" "${scratch}/${repo}.rebuilt" || die "${repo}: the remotes cannot be rebuilt exactly from ${saved}; nothing changed"
    why="$(back_right "${saved}" "--git-dir=${try}/.git")" || die "${repo}: once back, ${why:-git could not read the remotes}: take this batch's insteadOf lines out of ~/.gitconfig first; nothing changed"
    continue
  fi
  dump "${cfg}" "${scratch}/${repo}.now"
  ! valueless "${scratch}/${repo}.now" || die "${repo}: a remote.origin or remote.github key has no value; give it one (true) first"
  [[ "$(values "${cfg}" remote.origin.url | grep -c .)" -eq 1 ]] || die "${repo}: origin should have exactly one url"
  gh="$(github_of "${repo}" "${cfg}")" || die "${repo}: remote github or origin is not a GitHub address of ${repo}; look before switching"
  switched "${cfg}" "${try}/.git/config" "${repo}" "${gh}"
  why="$(switched_right "${repo}" "--git-dir=${try}/.git")" || die "${repo}: after the switch ${why:-git could not read the remotes} (a pushInsteadOf or insteadOf in ~/.gitconfig?); nothing changed"
done

# change: every checkout, then every working tree read back
for repo in "$@"; do
  cfg="$(config_of "${repo}")"
  saved="${cfg%/config}/${saved_name}"
  prev="${scratch}/${repo}.prev"
  cp -p "${cfg}" "${prev}"
  made_saved=""
  if [[ "${back}" -eq 0 && ! -f "${saved}" ]]; then
    # created only if absent, the way the lock is (review 250 C5)
    python3 -c 'import os, sys; data = open(sys.argv[1], "rb").read(); fd = os.open(sys.argv[2], os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644); os.write(fd, data); os.close(fd)' "${cfg}" "${saved}" ||
      die "${repo}: cannot keep ${saved}"
    made_saved="${saved}"
  fi
  changed_cfg+=("${cfg}")
  changed_prev+=("${prev}")
  changed_saved+=("${made_saved}")
  if [[ "${back}" -eq 1 ]]; then
    restored "${cfg}" "${scratch}/${repo}.saved" "${scratch}/${repo}.new"
    saved_to_remove+=("${saved}")
  else
    gh="$(github_of "${repo}" "${cfg}")" || die "${repo}: cannot tell the GitHub address"
    switched "${cfg}" "${scratch}/${repo}.new" "${repo}" "${gh}"
  fi
  install_config "${scratch}/${repo}.new" "${cfg}"
done
done_lines=()
for repo in "$@"; do
  cfg="$(config_of "${repo}")"
  if [[ "${back}" -eq 1 ]]; then
    why="$(every_worktree "${repo}" back "${cfg%/config}/${saved_name}")" || die "${repo}: once back, ${why}"
    done_lines+=("${repo}: origin $(values "${cfg}" remote.origin.url) (back as before the switch)")
  else
    why="$(every_worktree "${repo}" switched)" || die "${repo}: after the switch ${why}"
    done_lines+=("${repo}: origin ${gitea}/${repo}.git, github $(values "${cfg}" remote.github.url) (read-only)")
  fi
done
# the report is part of the run: if it cannot be written, the run is undone (review 250 B4). It goes
# through a file and cat: a failed write by bash's own printf leaves its text buffered, and the next
# command substitution (the undo's mktemp) would read it back
printf '%s\n' "${done_lines[@]}" > "${scratch}/report"
cat "${scratch}/report"
committed=1
for saved in "${saved_to_remove[@]+"${saved_to_remove[@]}"}"; do
  rm -f "${saved}" || say "could not remove ${saved}; remove it by hand"
done
