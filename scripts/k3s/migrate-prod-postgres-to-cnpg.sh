#!/usr/bin/env bash
# Copy legacy bare-metal PG (192.168.10.80 / options_db) → CloudNativePG bifrost_prod.
#
# Usage:
#   make k3s-migrate-prod-postgres-to-cnpg
#   SKIP_DAEMON_SCALE=1 make k3s-migrate-prod-postgres-to-cnpg
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

PROD_NAMESPACE="${PROD_NAMESPACE:-bifrost-prod}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
CLUSTER_NAME="${CLUSTER_NAME:-bifrost-postgres}"
TARGET_DB="${TARGET_DB:-bifrost_prod}"

LEGACY_PG_HOST="${LEGACY_PG_HOST:-192.168.10.80}"
LEGACY_PG_PORT="${LEGACY_PG_PORT:-5432}"
LEGACY_PG_USER="${LEGACY_PG_USER:-bifrost}"
LEGACY_PG_DB="${LEGACY_PG_DB:-options_db}"

if [[ -f "${ROOT}/.env" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "${ROOT}/.env"
  set +a
fi
LEGACY_PG_PASSWORD="${LEGACY_PG_PASSWORD:-${POSTGRES_PASSWORD:-OptionPSW!@}}"
SKIP_DAEMON_SCALE="${SKIP_DAEMON_SCALE:-0}"

PG_DUMP="${PG_DUMP:-pg_dump}"
if ! command -v "${PG_DUMP}" >/dev/null 2>&1; then
  echo "pg_dump not found — install libpq (brew install libpq)" >&2
  exit 1
fi

primary="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.currentPrimary}' 2>/dev/null || true)"
if [[ -z "${primary}" ]]; then
  echo "CNPG cluster ${CLUSTER_NAME} not ready" >&2
  exit 1
fi

echo "==> Migrate ${LEGACY_PG_DB} @ ${LEGACY_PG_HOST} → CNPG ${TARGET_DB} (${primary})"

if [[ "${SKIP_DAEMON_SCALE}" != "1" ]]; then
  echo "==> Scale prod daemon to 0 (pause writes)"
  kubectl scale deployment/daemon -n "${PROD_NAMESPACE}" --replicas=0
  kubectl wait --for=delete pod -l app.kubernetes.io/name=daemon -n "${PROD_NAMESPACE}" --timeout=180s 2>/dev/null || true
fi

restore_daemon() {
  if [[ "${SKIP_DAEMON_SCALE:-0}" != "1" ]]; then
    kubectl scale deployment/daemon -n "${PROD_NAMESPACE}" --replicas=1 2>/dev/null || true
  fi
}

DUMP_FILE="$(mktemp -t prod-pg.XXXXXX.sql)"
REMOTE_DUMP="/var/lib/postgresql/data/bifrost-prod-migrate.sql"
trap 'rm -f "${DUMP_FILE}"; restore_daemon' EXIT

echo "==> pg_dump legacy ${LEGACY_PG_HOST}:${LEGACY_PG_PORT}/${LEGACY_PG_DB} (plain SQL, no --clean)"
PGPASSWORD="${LEGACY_PG_PASSWORD}" "${PG_DUMP}" \
  -h "${LEGACY_PG_HOST}" -p "${LEGACY_PG_PORT}" -U "${LEGACY_PG_USER}" -d "${LEGACY_PG_DB}" \
  --no-owner --no-acl --format=plain -f "${DUMP_FILE}.raw"

# Strip PG17+ GUCs not understood by CNPG PG16
sed -e '/^SET transaction_timeout/d' -e '/^SET idle_session_timeout/d' \
  "${DUMP_FILE}.raw" > "${DUMP_FILE}"
rm -f "${DUMP_FILE}.raw"

echo "==> Reset CNPG ${TARGET_DB} schema (DROP SCHEMA public CASCADE)"
kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- psql -U postgres -d "${TARGET_DB}" -v ON_ERROR_STOP=1 -c \
  "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO bifrost; GRANT ALL ON SCHEMA public TO public;"

dump_size="$(wc -c < "${DUMP_FILE}" | tr -d ' ')"
echo "   dump size: ${dump_size} bytes"
if [[ "${dump_size}" -lt 1000 ]]; then
  echo "pg_dump suspiciously small" >&2
  exit 1
fi

echo "==> psql restore → CNPG ${TARGET_DB}"
kubectl cp "${DUMP_FILE}" "${DATA_NAMESPACE}/${primary}:${REMOTE_DUMP}"
set +e
kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- \
  psql -U postgres -d "${TARGET_DB}" -v ON_ERROR_STOP=1 -f "${REMOTE_DUMP}"
migrate_rc=$?
kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- rm -f "${REMOTE_DUMP}" 2>/dev/null || true
set -e
if [[ "${migrate_rc}" -ne 0 ]]; then
  echo "psql restore failed (exit ${migrate_rc})" >&2
  exit "${migrate_rc}"
fi

echo "==> Grant bifrost on ${TARGET_DB}"
kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- psql -U postgres -d "${TARGET_DB}" -c \
  "GRANT ALL ON ALL TABLES IN SCHEMA public TO bifrost; GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO bifrost; ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO bifrost;" \
  >/dev/null

trap - EXIT
rm -f "${DUMP_FILE}"
restore_daemon

TABLES="$(kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- \
  psql -U postgres -d "${TARGET_DB}" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo 0)"
DC_ROWS="$(kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- \
  psql -U postgres -d "${TARGET_DB}" -tAc "SELECT count(*) FROM daemon_control" 2>/dev/null || echo -1)"
echo "OK CNPG ${TARGET_DB} public tables: ${TABLES} · daemon_control rows: ${DC_ROWS}"
if [[ "${DC_ROWS}" == "0" ]] && [[ "${dump_size}" -gt 1000000 ]]; then
  echo "WARN: large dump but daemon_control empty — verify legacy data copied" >&2
  exit 1
fi

echo "Migration complete. Run: make k3s-cutover-prod-data-layer-phase4"
