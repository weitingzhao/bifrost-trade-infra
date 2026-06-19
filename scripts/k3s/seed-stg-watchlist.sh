#!/usr/bin/env bash
# Copy watchlist rows from Dev PostgreSQL → bifrost-stg (K3s postgres).
# Massive WS requires: sec_type='STK' AND optionable=true.
#
# Usage (from bifrost-trade-infra):
#   ./scripts/k3s/seed-stg-watchlist.sh
# Optional: STG_NAMESPACE=bifrost-stg KUBECONFIG=~/.kube/bifrost-k3s.yaml
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${ROOT}/.env"
STG_NAMESPACE="${STG_NAMESPACE:-bifrost-stg}"
STG_DB="${STG_DB:-bifrost_stg}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing ${ENV_FILE}" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

: "${POSTGRES_HOST:?POSTGRES_HOST required in .env}"
: "${POSTGRES_USER:?POSTGRES_USER required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD required}"
: "${POSTGRES_DB:?POSTGRES_DB required (Dev source DB)}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl not found" >&2
  exit 1
fi

echo "Source: ${POSTGRES_USER}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
echo "Target: postgres.${STG_NAMESPACE}/${STG_DB}"

DEV_COUNT="$(PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
  "SELECT count(*) FROM watchlist")"
OPT_STK="$(PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
  "SELECT count(*) FROM watchlist WHERE sec_type='STK' AND optionable IS TRUE")"
echo "Dev watchlist: ${DEV_COUNT} rows (${OPT_STK} optionable STK for Massive WS)"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -tA <<'EOSQL' > "$TMP"
SELECT format(
  $q$INSERT INTO watchlist (contract_key, symbol, sec_type, expiry, strike, option_right, display_label, source, category_id, optionable)
VALUES (%L, %L, %L, %L, %L, %L, %L, %L, NULL, %L)
ON CONFLICT (contract_key) DO UPDATE SET
  symbol = EXCLUDED.symbol, sec_type = EXCLUDED.sec_type, expiry = EXCLUDED.expiry,
  strike = EXCLUDED.strike, option_right = EXCLUDED.option_right,
  display_label = EXCLUDED.display_label, source = EXCLUDED.source,
  optionable = EXCLUDED.optionable;$q$,
  contract_key, symbol, sec_type, expiry, strike, option_right, display_label, source, optionable
)
FROM watchlist
ORDER BY contract_key;
EOSQL

if [[ ! -s "$TMP" ]]; then
  echo "No watchlist rows exported from Dev — aborting." >&2
  exit 1
fi

{
  echo "BEGIN;"
  cat "$TMP"
  echo "COMMIT;"
} | kubectl exec -i -n "$STG_NAMESPACE" deploy/postgres -- psql -U bifrost -d "$STG_DB" -v ON_ERROR_STOP=1

STG_TOTAL="$(kubectl exec -n "$STG_NAMESPACE" deploy/postgres -- psql -U bifrost -d "$STG_DB" -tAc "SELECT count(*) FROM watchlist")"
STG_OPT="$(kubectl exec -n "$STG_NAMESPACE" deploy/postgres -- psql -U bifrost -d "$STG_DB" -tAc \
  "SELECT count(*) FROM watchlist WHERE sec_type='STK' AND optionable IS TRUE")"
echo "STG watchlist rows: ${STG_TOTAL} (${STG_OPT} optionable STK)"

echo "Restarting massive-ws so ingestor re-reads watchlist…"
kubectl rollout restart deployment/massive-ws -n "$STG_NAMESPACE"
kubectl rollout status deployment/massive-ws -n "$STG_NAMESPACE" --timeout=120s
echo "Done. Check Socket page Massive WS or: kubectl logs -n ${STG_NAMESPACE} deploy/massive-ws --tail=30"
