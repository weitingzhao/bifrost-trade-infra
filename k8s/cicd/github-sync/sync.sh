#!/bin/sh
# sync.sh <primaries-file> [<ref>] — copies main and the tags of each
# repository Gitea holds as its primary to GitHub: fast-forward only, never
# forced, never deleting (CUT-gitea-primary-2026-10-17 step 0e; the Owner chose
# 9.1 A: GitHub gets main and tags only, agent and work branches stay on Gitea).
#
# With <ref> (the TaskRun a Gitea push starts) only that ref is copied;
# without it (the reconcile CronJob) main and every tag. A main GitHub has
# moved past or away from, or a tag GitHub has at another object, is reported
# and fails the run; it is never overwritten. A ref Gitea no longer has is left
# on GitHub.
#
# Credentials come from the environment and reach git as environment config
# scoped to each host (GIT_CONFIG_*), never on a command line or in a log:
# GITEA_TOKEN for Gitea, GITHUB_TOKEN (Secret cicd/github-sync) for GitHub.
# Runs in alpine/git. Tested by scripts/cicd/test_github_sync.py.
set -eu

primaries="$1"
only="${2:-}"
: "${GITEA_GIT_BASE:=http://gitea.cicd.svc.cluster.local:3000/bifrost}"
: "${GITHUB_BASE:=https://github.com/weitingzhao}"

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

# host_of <base> — "http://host:port/" of an http(s) base, empty otherwise.
host_of() {
  printf '%s' "$1" | sed -nE 's#^(https?://[^/]+)/.*#\1/#p'
}
GIT_CONFIG_COUNT=0
export GIT_CONFIG_COUNT
add_config() {
  export "GIT_CONFIG_KEY_${GIT_CONFIG_COUNT}=$1" "GIT_CONFIG_VALUE_${GIT_CONFIG_COUNT}=$2"
  GIT_CONFIG_COUNT=$((GIT_CONFIG_COUNT + 1))
  export GIT_CONFIG_COUNT
}
gitea_host="$(host_of "${GITEA_GIT_BASE}")"
github_host="$(host_of "${GITHUB_BASE}")"
if [ -n "${GITEA_TOKEN:-}" ] && [ -n "${gitea_host}" ]; then
  add_config "http.${gitea_host}.extraHeader" "Authorization: token ${GITEA_TOKEN}"
fi
if [ -n "${GITHUB_TOKEN:-}" ] && [ -n "${github_host}" ]; then
  add_config "http.${github_host}.extraHeader" "Authorization: Basic $(printf 'x-access-token:%s' "${GITHUB_TOKEN}" | base64 | tr -d '\n')"
fi
export GIT_TERMINAL_PROMPT=0

fails=0
fail() {
  echo "FAIL $*"
  fails=$((fails + 1))
}

# remote_sha <url> <ref> — the object ref names on url, empty when absent;
# fails when url cannot be read (not hidden in a pipeline).
remote_sha() {
  _listed="$(git ls-remote "$1" "$2")" || return 1
  printf '%s\n' "${_listed}" | awk -v r="$2" '$2 == r { print $1 }'
}

sync_ref() { # sync_ref <repo> <bare> <gitea-url> <github-url> <ref>
  repo="$1" bare="$2" from="$3" to="$4" ref="$5"
  g="$(remote_sha "${from}" "${ref}")" || { fail "${repo} ${ref}: Gitea could not be read"; return; }
  if [ -z "${g}" ]; then
    echo "${repo} ${ref}: not on Gitea; GitHub left as it is"
    return
  fi
  h="$(remote_sha "${to}" "${ref}")" || { fail "${repo} ${ref}: GitHub could not be read"; return; }
  if [ "${g}" = "${h}" ]; then
    echo "${repo} ${ref}: in step (${g})"
    return
  fi
  case "${ref}" in
    refs/tags/*)
      if [ -n "${h}" ]; then
        fail "${repo} ${ref}: GitHub has the tag at ${h}, Gitea at ${g}; not moved"
        return
      fi
      ;;
    refs/heads/main) ;;
    *)
      fail "${repo} ${ref}: only main and tags are copied"
      return
      ;;
  esac
  git -C "${bare}" fetch -q --no-tags "${from}" "+${ref}:${ref}" || { fail "${repo} ${ref}: fetch from Gitea failed"; return; }
  if [ "${ref}" = "refs/heads/main" ] && [ -n "${h}" ]; then
    git -C "${bare}" fetch -q --no-tags "${to}" "+refs/heads/main:refs/github/main" || { fail "${repo} main: fetch from GitHub failed"; return; }
    if ! git -C "${bare}" merge-base --is-ancestor "${h}" "${g}"; then
      fail "${repo} main: GitHub has ${h}, which Gitea's ${g} does not contain (diverged or ahead); not pushed"
      return
    fi
  fi
  if [ -z "${GITHUB_TOKEN:-}" ]; then
    fail "${repo} ${ref}: needs a push and there is no GitHub token (Secret cicd/github-sync, key token)"
    return
  fi
  if git -C "${bare}" push -q "${to}" "${ref}:${ref}"; then
    echo "${repo} ${ref}: pushed ${g} to GitHub"
  else
    fail "${repo} ${ref}: GitHub refused the push of ${g}"
  fi
}

while IFS= read -r repo; do
  [ -n "${repo}" ] || continue
  from="${GITEA_GIT_BASE}/${repo}.git"
  to="${GITHUB_BASE}/${repo}.git"
  bare="${work}/${repo}.git"
  git init -q --bare "${bare}"
  if [ -n "${only}" ]; then
    sync_ref "${repo}" "${bare}" "${from}" "${to}" "${only}"
    continue
  fi
  sync_ref "${repo}" "${bare}" "${from}" "${to}" refs/heads/main
  listed="$(git ls-remote --tags --refs "${from}")" || { fail "${repo}: Gitea's tags could not be listed"; continue; }
  tags="$(printf '%s\n' "${listed}" | awk 'NF == 2 { print $2 }')"
  for ref in ${tags}; do
    sync_ref "${repo}" "${bare}" "${from}" "${to}" "${ref}"
  done
done < "${primaries}"

if [ "${fails}" -gt 0 ]; then
  echo "github-sync: ${fails} ref(s) not in step"
  exit 1
fi
echo "github-sync: every ref in step"
