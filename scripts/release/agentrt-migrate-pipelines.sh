#!/usr/bin/env bash
# TD-411 (Owner 2026-10-21: 「STG 的迁移由发布流水线先跑、PROD 照旧由我建 Job」): the
# Owner applies the deliver pipelines' agentrt migration steps to the cluster.
#
#   bash scripts/release/agentrt-migrate-pipelines.sh check   read only: the commit, who you
#                                                              are, a server dry-run, a diff
#   bash scripts/release/agentrt-migrate-pipelines.sh apply   the same checks, then apply
#
# What is applied is this checkout's commit, which must be on origin/main: each file is
# taken from that commit into a snapshot, and the dry-run, the diff and the apply all read
# the snapshot. STG's files (the Role and RoleBinding in bifrost-platform-stg, the
# migration Task, the image promotion Task, the STG pipeline) go first. PROD's pipeline
# (the schema check and the promotion before its rollout) goes only once PROD's
# platform-api has rolled out and reports agentrt_schema_applied on /health, five reads in
# a row: before that its check would refuse every PROD release, the one that brings the
# field included. Until then apply says so and leaves PROD's pipeline as it is; run apply
# again after that release. A PROD platform rolled back to one without the field is
# refused by the check on every release: roll back only to a platform that has it.
# Run it in your own terminal (your kubeconfig, not the agent's). It stops at its first
# error; nothing is written before every check passed; apply is safe to run again.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "${here}/../.." && pwd)"
STG_FILES=(
  k8s/cicd/tekton/rbac-deliver-migrate-stg.yaml
  k8s/cicd/tekton/task-agentrt-migrate-stg.yaml
  k8s/cicd/tekton/task-promote-platform-images.yaml
  k8s/cicd/tekton/pipeline-deliver-platform.yaml
)
PROD_FILE=k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml
PROD_HEALTH="${AGENTRT_PROD_HEALTH:-http://192.168.10.100:30876/health}"

say() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
die() { say "STOP: $*"; exit 1; }

step="${1:-}"
case "${step}" in
  check|apply) ;;
  *) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
cd "${root}"

# The commit, pinned once: on origin/main, holding every file.
sha="$(git rev-parse HEAD)"
git merge-base --is-ancestor "${sha}" refs/remotes/origin/main ||
  die "this checkout's commit ${sha:0:12} is not on origin/main: check out main as pushed"
snap="$(mktemp -d)"
trap 'rm -rf "${snap}"' EXIT
for f in "${STG_FILES[@]}" "${PROD_FILE}"; do
  git cat-file -e "${sha}:${f}" 2>/dev/null || die "${f} is not in commit ${sha:0:12} (is TD-411's pipeline change on main?)"
  mkdir -p "${snap}/$(dirname "${f}")"
  git show "${sha}:${f}" > "${snap}/${f}"
done
say "applying from commit ${sha:0:12} ($(git log -1 --format=%s "${sha}"))"

# Who you are, a first screen: the server dry-run below is the real check.
for want in "create tasks.tekton.dev -n cicd" "patch tasks.tekton.dev -n cicd" \
  "get pipelines.tekton.dev -n cicd" "patch pipelines.tekton.dev -n cicd" \
  "create roles.rbac.authorization.k8s.io -n bifrost-platform-stg" "patch roles.rbac.authorization.k8s.io -n bifrost-platform-stg" \
  "create rolebindings.rbac.authorization.k8s.io -n bifrost-platform-stg" "patch rolebindings.rbac.authorization.k8s.io -n bifrost-platform-stg"; do
  # shellcheck disable=SC2086 # the words are kubectl's arguments
  [[ "$(kubectl auth can-i ${want} 2>/dev/null || true)" == "yes" ]] ||
    die "this kubeconfig cannot ${want}: run this in your own terminal, with your admin kubeconfig"
done
say "this identity passes the first screen (get, create, patch)"

# PROD's pipeline waits until PROD's platform-api has rolled out and says, on every read,
# which migrations its database has.
prod=yes
if ! kubectl rollout status deployment/platform-api -n bifrost-platform-prod --timeout=30s >/dev/null 2>&1; then
  prod=no
  say "PROD's platform-api has not finished rolling out: the PROD pipeline waits"
else
  for i in 1 2 3 4 5; do
    if ! body="$(curl -fsS --max-time 10 "${PROD_HEALTH}")" ||
      ! printf '%s' "${body}" | python3 -c 'import json,sys; sys.exit(0 if isinstance(json.load(sys.stdin).get("agentrt_schema_applied"), list) else 1)'; then
      prod=no
      say "PROD's platform-api (${PROD_HEALTH}, read ${i}) does not report agentrt_schema_applied: the PROD pipeline waits"
      break
    fi
  done
fi
files=("${STG_FILES[@]}")
[[ "${prod}" == yes ]] && files+=("${PROD_FILE}") && say "PROD's platform-api reports agentrt_schema_applied: the PROD pipeline goes too"

for f in "${files[@]}"; do
  kubectl apply --dry-run=server -f "${snap}/${f}" >/dev/null || die "the server refuses ${f}"
  say "server dry-run ok: ${f}"
done
for f in "${files[@]}"; do
  say "diff ${f}:"
  kubectl diff -f "${snap}/${f}" || [[ $? -eq 1 ]] || die "kubectl diff failed on ${f}"
done

if [[ "${step}" == check ]]; then
  say "check done; nothing written"
  exit 0
fi

done_files=()
for f in "${files[@]}"; do
  if ! kubectl apply -f "${snap}/${f}"; then
    die "applying ${f} failed; applied before it: ${done_files[*]:-none}. Running apply again is safe"
  fi
  done_files+=("${f}")
done
kubectl get role,rolebinding tekton-deliver-migrate -n bifrost-platform-stg
kubectl get task bifrost-agentrt-migrate-stg bifrost-promote-platform-images -n cicd
kubectl get pipeline bifrost-deliver-platform bifrost-deliver-platform-prod -n cicd
if [[ "${prod}" == yes ]]; then
  say "done (${sha:0:12}): STG runs its migrations before it rolls out; PROD checks its database before it rolls out"
else
  say "done for STG (${sha:0:12}). Run apply again once PROD's platform-api reports agentrt_schema_applied (a PROD release of platform with TD-411's health field)"
fi
