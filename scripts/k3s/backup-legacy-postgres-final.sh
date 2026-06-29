#!/usr/bin/env bash
# [ARCHIVED — COMPLETED 2026-06-29] One-time final backup of the legacy bare-metal
# PostgreSQL @ 192.168.10.80 before decommission. The .80 server has since been
# offlined (data lives in CNPG @ data NS); kept for audit / runbook history only.
# Do NOT expect .80 to be reachable — set LEGACY_PG_HOST explicitly to re-run.
#
# Databases:
#   options_db  — Bifrost Trade prod (authoritative until CNPG cutover)
#   stock       — separate project (user-owned; backup for archival)
#
# Usage:
#   cd bifrost-trade-infra && make k3s-backup-legacy-postgres-final
#   # or:
#   ./scripts/k3s/backup-legacy-postgres-final.sh
#
# Output: db-backups/final-legacy-YYYY-MM-DD/*.dump (+ MANIFEST.txt)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

DATE_STAMP="$(date +%Y-%m-%d)"
BACKUP_DIR="${BACKUP_DIR:-${ROOT}/../db-backups/final-legacy-${DATE_STAMP}}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"

LEGACY_PG_HOST="${LEGACY_PG_HOST:-192.168.10.80}"
LEGACY_PG_PORT="${LEGACY_PG_PORT:-5432}"
LEGACY_PG_USER="${LEGACY_PG_USER:-bifrost}"

if [[ -f "${ROOT}/.env" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "${ROOT}/.env"
  set +a
fi
LEGACY_PG_PASSWORD="${LEGACY_PG_PASSWORD:-${POSTGRES_PASSWORD:-}}"

if [[ -z "${LEGACY_PG_PASSWORD}" ]]; then
  echo "Set POSTGRES_PASSWORD in ${ROOT}/.env (or LEGACY_PG_PASSWORD)" >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"

POD="pg-backup-final-${RANDOM}"
REMOTE_DIR="/tmp/bifrost-legacy-backup"

cleanup() {
  kubectl delete pod "${POD}" -n "${DATA_NAMESPACE}" --ignore-not-found >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Backup directory: ${BACKUP_DIR}"
echo "==> Source: ${LEGACY_PG_USER}@${LEGACY_PG_HOST}:${LEGACY_PG_PORT}"
echo "==> Starting backup pod ${POD} in ${DATA_NAMESPACE}…"
kubectl run "${POD}" -n "${DATA_NAMESPACE}" --restart=Never \
  --image=postgres:17 \
  --env="PGPASSWORD=${LEGACY_PG_PASSWORD}" \
  --command -- sleep 7200 >/dev/null

kubectl wait -n "${DATA_NAMESPACE}" --for=condition=Ready "pod/${POD}" --timeout=120s

kubectl exec -n "${DATA_NAMESPACE}" "${POD}" -- mkdir -p "${REMOTE_DIR}"

backup_db() {
  local db=$1
  local remote="${REMOTE_DIR}/${db}.dump"
  local local="${BACKUP_DIR}/${db}.dump"
  echo ""
  echo "==> pg_dump -Fc ${db} @ ${LEGACY_PG_HOST}…"
  kubectl exec -n "${DATA_NAMESPACE}" "${POD}" -- \
    pg_dump -h "${LEGACY_PG_HOST}" -p "${LEGACY_PG_PORT}" -U "${LEGACY_PG_USER}" -d "${db}" \
    --format=custom --no-owner --no-acl -f "${remote}"
  echo "==> Copy ${db}.dump → ${local}"
  kubectl cp "${DATA_NAMESPACE}/${POD}:${remote}" "${local}"
  local size
  size="$(wc -c < "${local}" | tr -d ' ')"
  if [[ "${size}" -lt 1000 ]]; then
    echo "ERROR: ${db}.dump suspiciously small (${size} bytes)" >&2
    exit 1
  fi
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${local}" >> "${BACKUP_DIR}/SHA256SUMS"
  fi
  echo "   OK ${db}.dump — $(numfmt --to=iec-i --suffix=B "${size}" 2>/dev/null || echo "${size} bytes")"
}

backup_db options_db
backup_db stock

{
  echo "Bifrost legacy PostgreSQL final backup"
  echo "Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "Source host: ${LEGACY_PG_HOST}:${LEGACY_PG_PORT}"
  echo "User: ${LEGACY_PG_USER}"
  echo ""
  echo "Files:"
  ls -lh "${BACKUP_DIR}"/*.dump 2>/dev/null || true
  echo ""
  echo "Restore example (custom format):"
  echo "  pg_restore -h HOST -U USER -d TARGET_DB --no-owner --no-acl options_db.dump"
  echo ""
  echo "Notes:"
  echo "  - options_db = Bifrost Trade prod (maps to CNPG bifrost_prod)"
  echo "  - stock      = separate project database on same host"
} > "${BACKUP_DIR}/MANIFEST.txt"

echo ""
echo "==> Done. Backups in: ${BACKUP_DIR}"
cat "${BACKUP_DIR}/MANIFEST.txt"
