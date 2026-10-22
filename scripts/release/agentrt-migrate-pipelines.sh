#!/usr/bin/env bash
# TD-411 (Owner 2026-10-21: 「STG 的迁移由发布流水线先跑、PROD 照旧由我建 Job」): the
# Owner applies the deliver pipelines' agentrt migration steps to the cluster.
#
#   bash scripts/release/agentrt-migrate-pipelines.sh check   read only: who you are, a
#                                                              server dry-run and a diff
#   bash scripts/release/agentrt-migrate-pipelines.sh apply   the same checks, then apply
#
# STG (three files: the Role and RoleBinding in bifrost-platform-stg, the Task, the STG
# pipeline) is applied at once. PROD's pipeline (the schema check before its rollout) is
# applied only once PROD's platform-api reports agentrt_schema_applied on /health: before
# that the check would refuse every PROD release, the one that brings the field included.
# Until then apply says so and leaves the PROD pipeline as it is; run apply again after
# that release. Run it in your own terminal (your kubeconfig, not the agent's); it stops
# at its first error and writes nothing before every check has passed.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "${here}/../.." && pwd)"
STG_FILES=(
  k8s/cicd/tekton/rbac-deliver-migrate-stg.yaml
  k8s/cicd/tekton/task-agentrt-migrate-stg.yaml
  k8s/cicd/tekton/pipeline-deliver-platform.yaml
)
PROD_FILE=k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml
PROD_HEALTH="${AGENTRT_PROD_HEALTH:-http://192.168.10.100:30876/health}"

say() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
die() { say "STOP: $*"; exit 1; }

step="${1:-}"
case "${step}" in
  check|apply) ;;
  *) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
cd "${root}"

# The files are the committed ones: nothing applied differs from what was reviewed.
git diff --quiet HEAD -- "${STG_FILES[@]}" "${PROD_FILE}" ||
  die "these files differ from the checkout's commit $(git rev-parse --short HEAD); commit or restore them first"
for f in "${STG_FILES[@]}" "${PROD_FILE}"; do
  [[ -f "${f}" ]] || die "${f} is not in this checkout (is it at a commit with TD-411's pipeline change?)"
done
say "checkout ${root} at $(git rev-parse --short HEAD)"

# Who you are: the writes need more than the agent's read-only identity.
for want in "create tasks.tekton.dev -n cicd" "patch pipelines.tekton.dev -n cicd" \
  "create roles.rbac.authorization.k8s.io -n bifrost-platform-stg" \
  "create rolebindings.rbac.authorization.k8s.io -n bifrost-platform-stg"; do
  # shellcheck disable=SC2086 # the words are kubectl's arguments
  [[ "$(kubectl auth can-i ${want} 2>/dev/null || true)" == "yes" ]] ||
    die "this kubeconfig cannot ${want}: run this in your own terminal, with your admin kubeconfig"
done
say "this identity may write the pipelines and STG's Role"

# PROD's pipeline waits until PROD's platform-api says which migrations its database has.
prod=no
if body="$(curl -fsS --max-time 10 "${PROD_HEALTH}")" &&
  printf '%s' "${body}" | python3 -c 'import json,sys; sys.exit(0 if isinstance(json.load(sys.stdin).get("agentrt_schema_applied"), list) else 1)'; then
  prod=yes
  say "PROD's platform-api reports agentrt_schema_applied: the PROD pipeline goes too"
else
  say "PROD's platform-api (${PROD_HEALTH}) does not report agentrt_schema_applied yet: the PROD pipeline waits"
fi
files=("${STG_FILES[@]}")
[[ "${prod}" == yes ]] && files+=("${PROD_FILE}")

for f in "${files[@]}"; do
  kubectl apply --dry-run=server -f "${f}" >/dev/null || die "the server refuses ${f}"
  say "server dry-run ok: ${f}"
done
for f in "${files[@]}"; do
  say "diff ${f}:"
  kubectl diff -f "${f}" || [[ $? -eq 1 ]] || die "kubectl diff failed on ${f}"
done

if [[ "${step}" == check ]]; then
  say "check done; nothing written"
  exit 0
fi

for f in "${files[@]}"; do
  kubectl apply -f "${f}"
done
kubectl get role,rolebinding tekton-deliver-migrate -n bifrost-platform-stg
kubectl get task bifrost-agentrt-migrate-stg -n cicd
kubectl get pipeline bifrost-deliver-platform bifrost-deliver-platform-prod -n cicd
if [[ "${prod}" == yes ]]; then
  say "done: STG runs its migrations before it rolls out; PROD checks its database before it rolls out"
else
  say "done for STG. Run apply again once PROD's platform-api reports agentrt_schema_applied (a PROD release of platform with TD-411's health field)"
fi
