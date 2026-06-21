#!/usr/bin/env bash
# Copy bifrost_stg from embedded postgres (bifrost-stg) → CloudNativePG primary.
#
# Usage:
#   make k3s-migrate-stg-postgres-to-cnpg
#   SKIP_DAEMON_SCALE=1 make k3s-migrate-stg-postgres-to-cnpg  # no daemon pause
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

STG_NAMESPACE="${STG_NAMESPACE:-bifrost-stg}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
CLUSTER_NAME="${CLUSTER_NAME:-bifrost-postgres}"
STG_DB="${STG_DB:-bifrost_stg}"
PG_USER="${PG_USER:-bifrost}"
SKIP_DAEMON_SCALE="${SKIP_DAEMON_SCALE:-0}"

if ! kubectl get deployment postgres -n "${STG_NAMESPACE}" >/dev/null 2>&1; then
  echo "No embedded postgres deployment in ${STG_NAMESPACE} — skip migration (already cut over?)" >&2
  exit 0
fi

ready="$(kubectl get deployment postgres -n "${STG_NAMESPACE}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"
if [[ "${ready}" != "1" ]]; then
  echo "Embedded postgres not ready in ${STG_NAMESPACE}" >&2
  exit 1
fi

primary="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.currentPrimary}' 2>/dev/null || true)"
if [[ -z "${primary}" ]]; then
  echo "CNPG cluster ${CLUSTER_NAME} not ready" >&2
  exit 1
fi

echo "==> Migrate ${STG_DB}: ${STG_NAMESPACE}/postgres → ${DATA_NAMESPACE}/${primary}"

if [[ "${SKIP_DAEMON_SCALE}" != "1" ]]; then
  echo "==> Scale daemon to 0 (pause writes)"
  kubectl scale deployment/daemon -n "${STG_NAMESPACE}" --replicas=0
  kubectl wait --for=delete pod -l app.kubernetes.io/name=daemon -n "${STG_NAMESPACE}" --timeout=120s 2>/dev/null || true
fi

restore_daemon() {
  if [[ "${SKIP_DAEMON_SCALE}" != "1" ]]; then
    kubectl scale deployment/daemon -n "${STG_NAMESPACE}" --replicas=1 2>/dev/null || true
  fi
}

echo "==> pg_dump (embedded) → local file → pg_restore (CNPG ${primary})"
DUMP_FILE="$(mktemp -t stg-pg.XXXXXX.dump)"
trap 'rm -f "${DUMP_FILE}"; restore_daemon' EXIT

kubectl exec -n "${STG_NAMESPACE}" deploy/postgres -- \
  pg_dump -U "${PG_USER}" -d "${STG_DB}" --no-owner --no-acl -Fc > "${DUMP_FILE}"

dump_size="$(wc -c < "${DUMP_FILE}" | tr -d ' ')"
if [[ "${dump_size}" -lt 1000 ]]; then
  echo "pg_dump suspiciously small (${dump_size} bytes)" >&2
  exit 1
fi

set +e
cat "${DUMP_FILE}" | kubectl exec -i -n "${DATA_NAMESPACE}" "${primary}" -- \
  pg_restore -U postgres -d "${STG_DB}" --no-owner --no-acl --clean --if-exists /dev/stdin
migrate_rc=$?
set -e

trap - EXIT
rm -f "${DUMP_FILE}"
restore_daemon

if [[ "${migrate_rc}" -gt 1 ]]; then
  echo "pg_restore failed (exit ${migrate_rc})" >&2
  exit "${migrate_rc}"
fi

TABLES="$(kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- \
  psql -U postgres -d "${STG_DB}" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo 0)"
echo "OK CNPG ${STG_DB} public tables: ${TABLES}"

echo "Migration complete. Run: make k3s-cutover-stg-data-layer-phase2"
