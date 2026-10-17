#!/bin/sh
# read-primaries.sh <out-file> <repo>... — writes to out-file, one per line,
# the repositories Gitea holds as its own (regular repositories, not pull
# mirrors). Only those are copied to GitHub; a pull mirror still has GitHub as
# its upstream (CUT-gitea-primary-2026-10-17 step 0e). A repository Gitea
# cannot read, or whose answer does not say, stops the run: the sync must not
# guess. Runs in curlimages/curl; GITEA_TOKEN comes from the environment.
set -eu

out="$1"
shift
: "${GITEA_API:=http://gitea.cicd.svc.cluster.local:3000/api/v1}"
: "${GITEA_ORG:=bifrost}"
if [ -z "${GITEA_TOKEN:-}" ]; then
  echo "ERROR: gitea-bootstrap/gitea_admin_token missing: cannot read the repositories" >&2
  exit 1
fi

: > "${out}"
for repo in "$@"; do
  info="$(curl -s -w '\n%{http_code}' -H "Authorization: token ${GITEA_TOKEN}" "${GITEA_API}/repos/${GITEA_ORG}/${repo}")"
  code="$(printf '%s' "${info}" | tail -n 1)"
  if [ "${code}" != "200" ]; then
    echo "ERROR: repository ${GITEA_ORG}/${repo} → HTTP ${code}" >&2
    exit 1
  fi
  if printf '%s' "${info}" | grep -q '"mirror":false'; then
    echo "${repo}" >> "${out}"
    echo "${GITEA_ORG}/${repo}: Gitea's primary"
  elif printf '%s' "${info}" | grep -q '"mirror":true'; then
    echo "${GITEA_ORG}/${repo}: pull mirror, GitHub is its upstream"
  else
    echo "ERROR: Gitea did not say whether ${GITEA_ORG}/${repo} is a mirror" >&2
    exit 1
  fi
done
