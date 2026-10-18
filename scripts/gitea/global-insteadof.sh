#!/usr/bin/env bash
# global-insteadof.sh add|remove <repo>... — batch step 7
# (CUT-gitea-primary-2026-10-17 §5): in the Owner's global git config, the
# GitHub addresses of each repository are rewritten to the Gitea repository,
# so that clones outside the workspace (~/agent-work, made from GitHub
# addresses) fetch from and push to Gitea once Gitea holds it as its primary.
# Per repository, two rules on url.<gitea>/<repo>.git.insteadOf:
#     git@github.com:weitingzhao/<repo>.git
#     https://github.com/weitingzhao/<repo>.git
# Always with .git: insteadOf matches a prefix, and without it the rule for
# bifrost-platform would also rewrite bifrost-platform-plugin.
#
# add: first keeps a copy of the global config beside it
# (<file>.before-gitea-primary, only if there is none), then adds the rules a
# repository does not have yet, then reads back with git ls-remote --get-url
# that both GitHub addresses resolve to the Gitea one. remove: takes exactly
# these values out again and reads back that both resolve to GitHub. Another
# rule that already rewrites one of these addresses elsewhere stops it before
# anything changes. Only url.*.insteadOf in the global config is touched; no
# fetch, no push.
set -euo pipefail

GITEA="${GITEA_PUBLIC_BASE:-http://192.168.10.73:30300/bifrost}"
GH_OWNER="${GITHUB_OWNER:-weitingzhao}"

die() { echo "ERROR: $*" >&2; exit 1; }
mode="${1:-}"
[[ "${mode}" == add || "${mode}" == remove ]] || die "usage: global-insteadof.sh add|remove <repo>..."
shift
[[ $# -gt 0 ]] || die "name at least one repository"
for repo in "$@"; do
  [[ "${repo}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "not a repository name: ${repo}"
done

# The file git config --global writes: GIT_CONFIG_GLOBAL, else ~/.gitconfig,
# else the XDG file when only that one exists.
file="${GIT_CONFIG_GLOBAL:-${HOME}/.gitconfig}"
xdg="${XDG_CONFIG_HOME:-${HOME}/.config}/git/config"
if [[ -z "${GIT_CONFIG_GLOBAL:-}" && ! -e "${file}" && -e "${xdg}" ]]; then file="${xdg}"; fi
resolve() { git ls-remote --get-url "$1"; }

# Checked for every repository before anything changes.
for repo in "$@"; do
  want="${GITEA}/${repo}.git"
  for from in "git@github.com:${GH_OWNER}/${repo}.git" "https://github.com/${GH_OWNER}/${repo}.git"; do
    now="$(resolve "${from}")"
    if [[ "${now}" != "${from}" && "${now}" != "${want}" ]]; then
      die "${from} already resolves to ${now}: another url.*.insteadOf rule; nothing changed"
    fi
  done
done

if [[ "${mode}" == add ]]; then
  if [[ -f "${file}" && ! -e "${file}.before-gitea-primary" ]]; then
    cp -p "${file}" "${file}.before-gitea-primary"
    echo "kept a copy: ${file}.before-gitea-primary"
  fi
fi

for repo in "$@"; do
  want="${GITEA}/${repo}.git"
  key="url.${want}.insteadOf"
  for from in "git@github.com:${GH_OWNER}/${repo}.git" "https://github.com/${GH_OWNER}/${repo}.git"; do
    have="$(git config --global --fixed-value --get-all "${key}" "${from}" || true)"
    if [[ "${mode}" == add ]]; then
      [[ -n "${have}" ]] || git config --global --add "${key}" "${from}"
      expect="${want}"
    else
      [[ -z "${have}" ]] || git config --global --fixed-value --unset-all "${key}" "${from}"
      expect="${from}"
    fi
    got="$(resolve "${from}")"
    [[ "${got}" == "${expect}" ]] || die "${from} resolves to ${got}, not ${expect}"
    echo "ok    ${from} → ${got}"
  done
done
echo "==> ${mode} done for: $*"
