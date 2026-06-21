#!/usr/bin/env bash
# Copy bifrost_dev from embedded postgres (bifrost-dev) → CloudNativePG primary.
#
# Usage:
#   make k3s-migrate-dev-postgres-to-cnpg
#   SKIP_DAEMON_SCALE=1 make k3s-migrate-dev-postgres-to-cnpg
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

DEV_NAMESPACE="${DEV_NAMESPACE:-bifrost-dev}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
CLUSTER_NAME="${CLUSTER_NAME:-bifrost-postgres}"
DEV_DB="${DEV_DB:-bifrost_dev}"
PG_USER="${PG_USER:-bifrost}"
SKIP_DAEMON_SCALE="${SKIP_DAEMON_SCALE:-0}"

if ! kubectl get deployment postgres -n "${DEV_NAMESPACE}" >/dev/null 2>&1; then
  echo "No embedded postgres deployment in ${DEV_NAMESPACE} — skip migration (already cut over?)" >&2
  exit 0
fi

ready="$(kubectl get deployment postgres -n "${DEV_NAMESPACE}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"
if [[ "${ready}" != "1" ]]; then
  echo "Embedded postgres not ready in ${DEV_NAMESPACE}" >&2
  exit 1
fi

primary="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.currentPrimary}' 2>/dev/null || true)"
if [[ -z "${primary}" ]]; then
  echo "CNPG cluster ${CLUSTER_NAME} not ready" >&2
  exit 1
fi

echo "==> Migrate ${DEV_DB}: ${DEV_NAMESPACE}/postgres → ${DATA_NAMESPACE}/${primary}"

if [[ "${SKIP_DAEMON_SCALE}" != "1" ]]; then
  echo "==> Scale daemon to 0 (pause writes)"
  kubectl scale deployment/daemon -n "${DEV_NAMESPACE}" --replicas=0
  kubectl wait --for=delete pod -l app.kubernetes.io/name=daemon -n "${DEV_NAMESPACE}" --timeout=120s 2>/dev/null || true
fi

restore_daemon() {
  if [[ "${SKIP_DAEMON_SCALE}" != "1" ]]; then
    kubectl scale deployment/daemon -n "${DEV_NAMESPACE}" --replicas=1 2>/dev/null || true
  fi
}

echo "==> pg_dump (embedded) → local file → pg_restore (CNPG ${primary})"
DUMP_FILE="$(mktemp -t dev-pg.XXXXXX.dump)"
REMOTE_DUMP="/var/lib/postgresql/data/bifrost-dev-migrate.dump"
trap 'rm -f "${DUMP_FILE}"; restore_daemon' EXIT

kubectl exec -n "${DEV_NAMESPACE}" deploy/postgres -- \
  pg_dump -U "${PG_USER}" -d "${DEV_DB}" --no-owner --no-acl -Fc > "${DUMP_FILE}"

dump_size="$(wc -c < "${DUMP_FILE}" | tr -d ' ')"
if [[ "${dump_size}" -lt 1000 ]]; then
  echo "pg_dump small (${dump_size} bytes) — skip restore; schema refresh after cutover"
else
  REMOTE_DUMP="/var/lib/postgresql/data/bifrost-dev-migrate.dump"
  kubectl cp "${DUMP_FILE}" "${DATA_NAMESPACE}/${primary}:${REMOTE_DUMP}"
  set +e
  kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- \
    pg_restore -U postgres -d "${DEV_DB}" --no-owner --no-acl --clean --if-exists "${REMOTE_DUMP}"
  migrate_rc=$?
  kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- rm -f "${REMOTE_DUMP}" 2>/dev/null || true
  set -e
  if [[ "${migrate_rc}" -gt 1 ]]; then
    echo "pg_restore failed (exit ${migrate_rc})" >&2
    exit "${migrate_rc}"
  fi
fi

trap - EXIT
rm -f "${DUMP_FILE}"
restore_daemon

TABLES="$(kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- \
  psql -U postgres -d "${DEV_DB}" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo 0)"
echo "OK CNPG ${DEV_DB} public tables: ${TABLES}"

echo "Migration complete. Run: make k3s-cutover-dev-data-layer-phase3"
