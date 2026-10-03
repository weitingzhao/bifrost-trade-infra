#!/usr/bin/env bash
# Tag the bifrost-core commit that reached PROD (TD-37).
#
# Core's release identity is the commit SHA the deliver pipeline cloned and built
# together with api and worker; the pyproject version is only a compatibility
# floor for downstreams. A tag v<version> marks which commit of that version
# reached PROD. Find the SHA in the PROD run's clone-core log (`=== HEAD <sha> ===`)
# or in any PROD api pod's /health (`core_sha`).
#
# Dry-run by default: prints what it would do and changes nothing.
#
# Usage:
#   scripts/release/tag_core_release.sh [--push] [--repo <core checkout>] [--remote <name>] <core_sha>
#
#   --push        create the annotated tag locally and push it to <remote>
#   --repo PATH   core checkout to use (default: $BIFROST_CORE_REPO, else ../bifrost-trade-core
#                 next to this infra repo)
#   --remote NAME remote to compare against and push to (default: origin, i.e. GitHub;
#                 Gitea mirrors it)
#
# Exit codes: 0 = tagged, would tag, or already tagged at this SHA
#             1 = usage / repository error
#             2 = refused: v<version> already names a different commit
set -euo pipefail

tag_release_usage() { sed -n '2,23p' "$0" | sed 's/^# \{0,1\}//'; }

push=0
remote="origin"
infra_root="$(cd "$(dirname "$0")/../.." && pwd)"
repo="${BIFROST_CORE_REPO:-${infra_root}/../bifrost-trade-core}"
sha_arg=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push) push=1; shift ;;
    --repo) repo="${2:?--repo needs a path}"; shift 2 ;;
    --remote) remote="${2:?--remote needs a name}"; shift 2 ;;
    -h|--help) tag_release_usage; exit 0 ;;
    -*) echo "unknown option: $1" >&2; tag_release_usage >&2; exit 1 ;;
    *)
      if [[ -n "${sha_arg}" ]]; then echo "only one <core_sha> please" >&2; exit 1; fi
      sha_arg="$1"; shift ;;
  esac
done

if [[ -z "${sha_arg}" ]]; then tag_release_usage >&2; exit 1; fi
if ! git -C "${repo}" rev-parse --git-dir >/dev/null 2>&1; then
  echo "not a git checkout: ${repo}" >&2
  exit 1
fi
if ! git -C "${repo}" remote get-url "${remote}" >/dev/null 2>&1; then
  echo "remote '${remote}' not configured in ${repo}" >&2
  exit 1
fi

if ! sha="$(git -C "${repo}" rev-parse --verify --quiet "${sha_arg}^{commit}")"; then
  echo "commit ${sha_arg} is not in ${repo} — run: git -C ${repo} fetch ${remote}" >&2
  exit 1
fi

if ! pyproject="$(git -C "${repo}" show "${sha}:pyproject.toml" 2>/dev/null)"; then
  echo "no pyproject.toml at ${sha}" >&2
  exit 1
fi
version="$(printf '%s\n' "${pyproject}" | sed -n 's/^version *= *"\([^"]*\)".*/\1/p' | head -n 1)"
if [[ -z "${version}" ]]; then
  echo "could not read [project] version from pyproject.toml at ${sha}" >&2
  exit 1
fi
tag="v${version}"

echo "core commit : ${sha}"
echo "  $(git -C "${repo}" log -1 --format='%s (%cs)' "${sha}")"
echo "version     : ${version}"
echo "tag         : ${tag}"

# Where the tag points now, locally and on the remote (peeled to the commit).
local_at="$(git -C "${repo}" rev-parse --verify --quiet "refs/tags/${tag}^{commit}" || true)"
remote_refs="$(git -C "${repo}" ls-remote --tags "${remote}" "refs/tags/${tag}" "refs/tags/${tag}^{}")" || {
  echo "could not list tags on ${remote}" >&2
  exit 1
}
remote_at="$(printf '%s\n' "${remote_refs}" | awk -v t="refs/tags/${tag}^{}" '$2 == t { print $1 }')"
if [[ -z "${remote_at}" ]]; then
  # Lightweight tag: no peeled line, the ref itself names the commit.
  remote_at="$(printf '%s\n' "${remote_refs}" | awk -v t="refs/tags/${tag}" '$2 == t { print $1 }')"
fi

for pair in "local:${local_at}" "${remote}:${remote_at}"; do
  where="${pair%%:*}"
  at="${pair#*:}"
  if [[ -n "${at}" && "${at}" != "${sha}" ]]; then
    echo >&2
    echo "REFUSED: ${tag} already exists (${where}) at ${at}, not ${sha}." >&2
    echo "Version ${version} names two different contents. Do not move the tag:" >&2
    echo "bump core's pyproject version for the newer content and release that." >&2
    exit 2
  fi
done

if [[ "${local_at}" == "${sha}" && "${remote_at}" == "${sha}" ]]; then
  echo "${tag} already marks ${sha} locally and on ${remote} — nothing to do."
  exit 0
fi

if git -C "${repo}" merge-base --is-ancestor "${sha}" "refs/remotes/${remote}/main" 2>/dev/null; then
  :
else
  echo "warning: ${sha} is not on ${remote}/main as this checkout knows it (fetch, or check the SHA)." >&2
fi

message="bifrost-core ${version}: commit ${sha} reached PROD"
create_cmd=(git -C "${repo}" tag -a "${tag}" -m "${message}" "${sha}")
push_cmd=(git -C "${repo}" push "${remote}" "refs/tags/${tag}")

if [[ "${push}" -eq 0 ]]; then
  echo
  echo "dry-run — would run:"
  if [[ -z "${local_at}" ]]; then printf ' '; printf ' %q' "${create_cmd[@]}"; echo; fi
  if [[ -z "${remote_at}" ]]; then printf ' '; printf ' %q' "${push_cmd[@]}"; echo; fi
  echo "re-run with --push to do it."
  exit 0
fi

if [[ -z "${local_at}" ]]; then
  "${create_cmd[@]}"
  echo "created ${tag} at ${sha}"
fi
if [[ -z "${remote_at}" ]]; then
  "${push_cmd[@]}"
  echo "pushed ${tag} to ${remote}"
fi
