#!/usr/bin/env bash
# Clone CNPG bifrost_prod → bifrost_dev + bifrost_stg (first baseline seed).
#
# Use when legacy .80 had no separate dev/stg DBs and CNPG logical DBs are empty.
# WARNING: Overwrites all data in bifrost_dev and bifrost_stg with a copy of prod.
#
# Usage:
#   cd bifrost-trade-infra && make k3s-clone-cnpg-prod-to-dev-stg
#   SKIP_CONFIRM=1 ./scripts/k3s/clone-cnpg-prod-to-dev-stg.sh   # non-interactive
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
CLUSTER_NAME="${CLUSTER_NAME:-bifrost-postgres}"
SOURCE_DB="${SOURCE_DB:-bifrost_prod}"
TARGET_DBS=(bifrost_dev bifrost_stg)

primary="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.currentPrimary}' 2>/dev/null || true)"
if [[ -z "${primary}" ]]; then
  echo "CNPG cluster ${CLUSTER_NAME} not ready" >&2
  exit 1
fi

echo "==> Clone ${SOURCE_DB} → ${TARGET_DBS[*]} on ${primary}"

if [[ "${SKIP_CONFIRM:-0}" != "1" ]]; then
  echo ""
  echo "This will DROP and recreate public schema in bifrost_dev and bifrost_stg"
  echo "with a full copy of ${SOURCE_DB} (including all prod data)."
  read -r -p "Type YES to continue: " ans
  if [[ "${ans}" != "YES" ]]; then
    echo "Aborted."
    exit 1
  fi
fi

REMOTE_DUMP="/var/lib/postgresql/data/bifrost-clone-prod.sql"

echo "==> pg_dump ${SOURCE_DB} (plain SQL) on primary pod"
kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -c postgres -- \
  pg_dump -U postgres -d "${SOURCE_DB}" --no-owner --no-acl --format=plain -f "${REMOTE_DUMP}"

dump_size="$(kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -c postgres -- \
  sh -c "wc -c < '${REMOTE_DUMP}'" | tr -d ' \n')"
echo "   dump size: ${dump_size} bytes"
if [[ "${dump_size}" -lt 1000000 ]]; then
  echo "ERROR: dump suspiciously small" >&2
  exit 1
fi

reset_and_restore() {
  local target=$1
  echo ""
  echo "==> Reset + restore → ${target}"
  kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -c postgres -- \
    psql -U postgres -d "${target}" -v ON_ERROR_STOP=1 -c \
    "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO bifrost; GRANT ALL ON SCHEMA public TO public;"
  set +e
  kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -c postgres -- \
    psql -U postgres -d "${target}" -v ON_ERROR_STOP=1 -f "${REMOTE_DUMP}"
  local rc=$?
  set -e
  if [[ "${rc}" -ne 0 ]]; then
    echo "ERROR: restore to ${target} failed (exit ${rc})" >&2
    exit "${rc}"
  fi
  kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -c postgres -- \
    psql -U postgres -d "${target}" -c \
    "GRANT ALL ON ALL TABLES IN SCHEMA public TO bifrost; GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO bifrost; ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO bifrost;" \
    >/dev/null
  local tables dc
  tables="$(kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -c postgres -- \
    psql -U postgres -d "${target}" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")"
  dc="$(kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -c postgres -- \
    psql -U postgres -d "${target}" -tAc "SELECT count(*) FROM daemon_control" 2>/dev/null || echo -1)"
  echo "   OK ${target}: ${tables} public tables · daemon_control rows: ${dc}"
}

for db in "${TARGET_DBS[@]}"; do
  reset_and_restore "${db}"
done

kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -c postgres -- rm -f "${REMOTE_DUMP}" 2>/dev/null || true

echo ""
echo "==> Fix table ownership (bifrost app user)"
"${ROOT}/scripts/k3s/fix-cnpg-db-ownership.sh" "${TARGET_DBS[@]}"

echo ""
echo "Clone complete. Dev/Stg now mirror ${SOURCE_DB}."
echo "Reminder: apps must point postgres.database to bifrost_dev / bifrost_stg (not options_db)."
