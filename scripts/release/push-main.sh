#!/usr/bin/env bash
# Push a commit to a repo's main the way CI will judge it (TD-341).
#
#   push-main.sh <checkout> [<commit>]      <commit> defaults to the checkout's HEAD
#
# 1. The release window must be closed (release.sh window), checked again
#    right before the push.
# 2. The commit must fast-forward origin/main (fetched first).
# 3. For a repo whose CI runs the code-health ratchet, scan.sh runs on a
#    fresh worktree of exactly <commit> (not the working tree, which may hold
#    other sessions' edits), so a metric over its baseline (a file over 800
#    lines, say) is refused here instead of turning main red.
# 4. git push origin <commit>:refs/heads/main.
#
# preflight.js refuses a direct `git push` to main, so this is the way an
# agent pushes main. go test and lint stay in the pusher's own routine: they
# need the repo's toolchain and take minutes. The scan uses the baselines of
# the infra checkout this script lives in; CI uses infra main's.
set -euo pipefail

usage() {
  echo "usage: push-main.sh <checkout> [<commit>]" >&2
  exit 2
}
die() {
  echo "push-main: $*" >&2
  exit 1
}
[[ $# -ge 1 && $# -le 2 ]] || usage
DIR="$1"
REF="${2:-HEAD}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SCAN="${PUSH_MAIN_SCAN:-$HERE/../../agent-config/scripts/code-health/scan.sh}"
WINDOW="${PUSH_MAIN_WINDOW:-$HERE/release.sh}"
# The repos whose CI pipeline has a code-health task (k8s/cicd/tekton:
# pipeline-ci-platform, pipeline-ci-frontend, pipeline-ci-python,
# task-research-lint-test). Keep in step with those.
GATED=" bifrost-platform bifrost-trade-frontend bifrost-research bifrost-trade-api bifrost-trade-core bifrost-trade-worker "

top="$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null)" || die "$DIR is not a git checkout"
commit="$(git -C "$top" rev-parse --verify --quiet "$REF^{commit}")" || die "$REF is not a commit in $top"
url="$(git -C "$top" remote get-url origin)" || die "$top has no remote origin"
repo="$(basename "${url%.git}")"
repo="${repo##*:}"

# A repository Gitea holds as its primary is pushed to Gitea; GitHub follows
# from the cluster (k8s/cicd/github-sync), never from here
# (CUT-gitea-primary-2026-10-17 step 0g).
PRIMARY_LIST="${PUSH_MAIN_PRIMARY_LIST:-$HERE/../../agent-config/gitea-primary.txt}"
if [[ -f "$PRIMARY_LIST" ]]; then
  primaries="$(sed -e 's/#.*//' -e 's/[[:space:]]//g' "$PRIMARY_LIST")"
  if grep -qx -- "$repo" <<<"$primaries"; then
    case "$url" in
      *github.com[:/]*) die "$repo has Gitea as its primary (agent-config/gitea-primary.txt) but origin is $url: point origin at Gitea and push there; GitHub follows from the cluster" ;;
    esac
  fi
fi

window() {
  local rc=0
  "$WINDOW" window || rc=$?
  case "$rc" in
    0) ;;
    1) die "the release window is open; nothing pushed" ;;
    *) die "cannot read the release window (exit $rc); nothing pushed" ;;
  esac
}

window

git -C "$top" fetch --quiet origin main
git -C "$top" merge-base --is-ancestor origin/main "$commit" ||
  die "$commit does not fast-forward origin/main of $repo; rebase onto it first"
if [[ "$(git -C "$top" rev-parse origin/main)" == "$commit" ]]; then
  echo "push-main: $repo main is already $commit"
  exit 0
fi

if [[ "$GATED" == *" $repo "* ]]; then
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/push-main.XXXXXX")"
  cleanup() {
    git -C "$top" worktree remove --force "$tmp/$repo" >/dev/null 2>&1 || true
    rmdir "$tmp" 2>/dev/null || true
  }
  trap cleanup EXIT
  git -C "$top" -c core.hooksPath=/dev/null worktree add --quiet --detach "$tmp/$repo" "$commit"
  rc=0
  bash "$SCAN" --root "$tmp" --repo "$repo" || rc=$?
  [[ "$rc" -eq 0 ]] || die "code-health refused $commit of $repo (exit $rc); nothing pushed"
else
  echo "push-main: $repo has no code-health task in CI; not scanned"
fi

window
git -C "$top" push origin "$commit:refs/heads/main"
echo "push-main: pushed $commit to $repo main"
