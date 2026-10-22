#!/usr/bin/env bash
# W-31 3.4 ①② (Owner 2026-10-21 「D3 A」): the Owner applies the release speed-up to cicd.
#
#   bash scripts/release/release-speedup-apply.sh check   read only: the commit, who you are,
#                                                          the release window, a server
#                                                          dry-run and a diff of every file
#   bash scripts/release/release-speedup-apply.sh apply   the same checks, then apply
#
# What is applied is this checkout's commit, which must be on origin/main: each file is
# taken from that commit into a snapshot, and the dry-run, the diff and the apply all
# read the snapshot. In this order: the pin-and-sync Task and the rollout check Task, the
# STG and PROD platform deliver pipelines (PROD builds nothing and deploys the digests
# STG verified; both pin their Argo application to digests), then the CI triggers (CI on
# every branch push). No Argo application is touched here: a delivery pins its own.
# Nothing is applied while a release window is open (a delivery may be running).
# Run it in your own terminal (your kubeconfig, not the agent's). It stops at its first
# error; nothing is written before every check passed; apply is safe to run again.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "${here}/../.." && pwd)"
FILES=(
  k8s/cicd/tekton/task-argocd-pin-sync-platform.yaml
  k8s/cicd/tekton/task-rollout-verify-platform.yaml
  k8s/cicd/tekton/pipeline-deliver-platform.yaml
  k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml
  k8s/cicd/tekton/trigger-trade-ci.yaml
)
WINDOW="${SPEEDUP_WINDOW:-${here}/release.sh}"
RT=--request-timeout=20s

say() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
die() { say "STOP: $*"; exit 1; }

step="${1:-}"
case "${step}" in
  check|apply) ;;
  *) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
cd "${root}"

# The commit, pinned once: on origin/main, holding every file.
sha="$(git rev-parse HEAD)"
git merge-base --is-ancestor "${sha}" refs/remotes/origin/main ||
  die "this checkout's commit ${sha:0:12} is not on origin/main: check out main as pushed"
snap="$(mktemp -d)"
trap 'rm -rf "${snap}"' EXIT
for f in "${FILES[@]}"; do
  git cat-file -e "${sha}:${f}" 2>/dev/null || die "${f} is not in commit ${sha:0:12} (is the release speed-up on main?)"
  mkdir -p "${snap}/$(dirname "${f}")"
  git show "${sha}:${f}" > "${snap}/${f}"
done
say "applying from commit ${sha:0:12} ($(git log -1 --format=%s "${sha}"))"

# Who you are, a first screen: the server dry-run below is the real check.
for want in "create tasks.tekton.dev -n cicd" "patch tasks.tekton.dev -n cicd" \
  "get pipelines.tekton.dev -n cicd" "patch pipelines.tekton.dev -n cicd" \
  "patch eventlisteners.triggers.tekton.dev -n cicd" "patch triggertemplates.triggers.tekton.dev -n cicd" \
  "patch triggerbindings.triggers.tekton.dev -n cicd"; do
  # shellcheck disable=SC2086 # the words are kubectl's arguments
  [[ "$(kubectl auth can-i ${want} "${RT}" 2>/dev/null || true)" == "yes" ]] ||
    die "this kubeconfig cannot ${want}: run this in your own terminal, with your admin kubeconfig"
done
say "this identity passes the first screen (tasks, pipelines, triggers in cicd)"

window_closed() {
  local rc=0
  "${WINDOW}" window >/dev/null 2>&1 || rc=$?
  case "${rc}" in
    0) return 0 ;;
    1) die "a release window is open (release.sh window): a delivery may be running; apply once it is closed" ;;
    *) die "cannot read the release window (exit ${rc})" ;;
  esac
}
window_closed

for f in "${FILES[@]}"; do
  kubectl apply --dry-run=server -f "${snap}/${f}" "${RT}" >/dev/null || die "the server refuses ${f}"
  say "server dry-run ok: ${f}"
done
for f in "${FILES[@]}"; do
  say "diff ${f}:"
  kubectl diff -f "${snap}/${f}" "${RT}" || [[ $? -eq 1 ]] || die "kubectl diff failed on ${f}"
done

if [[ "${step}" == check ]]; then
  say "check done; nothing written"
  exit 0
fi

window_closed
done_files=()
for f in "${FILES[@]}"; do
  if ! kubectl apply -f "${snap}/${f}"; then
    die "applying ${f} failed (it may be partly applied); applied before it: ${done_files[*]:-none}. Run apply again at commit ${sha:0:12}: it is safe"
  fi
  done_files+=("${f}")
done
kubectl get task bifrost-argocd-pin-sync-platform bifrost-rollout-verify-platform -n cicd "${RT}"
kubectl get pipeline bifrost-deliver-platform bifrost-deliver-platform-prod -n cicd "${RT}"
kubectl get eventlistener bifrost-ci -n cicd "${RT}"
say "done (${sha:0:12}): the next STG platform delivery pins STG to its digests; the next PROD one builds nothing; CI runs on branch pushes"
