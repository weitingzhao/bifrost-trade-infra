#!/bin/bash
# TD-217: compare the scratch Cluster with the primary at TARGET_TIME.
# Read-only on both. Exit 0 when the three counts and the three max timestamps match.
# Exit 2 when the scratch Cluster has no Running pod yet.
#
# Append-only approximation of "PROD at the target time": rows with a timestamp
# at or before TARGET_TIME. In-place updates of older rows are not reconstructed
# on the primary side. The three tables are the ones the drill checks.
set -euo pipefail

TARGET_TIME="${1:-${TARGET_TIME:-}}"
if [[ ! "${TARGET_TIME}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]; then
  echo "usage: compare.sh YYYY-MM-DDTHH:MM:SSZ" >&2
  exit 2
fi

export KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"

drill_pod="$(kubectl -n pg-recovery-drill get pods -l cnpg.io/cluster=pg-recovery-drill \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -z "${drill_pod}" ]]; then
  echo "no Running pod for Cluster pg-recovery-drill" >&2
  exit 2
fi

sql="
SELECT 'stock_daily|' || count(*) || '|' || coalesce(max(bar_date)::text, '')
FROM raw_market.stock_daily
WHERE bar_date <= '${TARGET_TIME}'::timestamptz::date
UNION ALL
SELECT 'atm_iv|' || count(*) || '|' || coalesce(max(trade_date)::text, '')
FROM features.option_metric_atm_iv_daily
WHERE trade_date <= '${TARGET_TIME}'::timestamptz::date
UNION ALL
SELECT 'transactions|' || count(*) || '|' || coalesce(max(ts)::text, '')
FROM raw_broker.transactions
WHERE ts <= '${TARGET_TIME}'::timestamptz
ORDER BY 1;
"

run() {
  local ns="$1" pod="$2"
  kubectl -n "${ns}" exec -i "${pod}" -c postgres -- \
    env PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=120000' \
    psql -U postgres -d bifrost_golden_source -X -At -c "${sql}"
}

primary="$(run data bifrost-postgres-1)"
scratch="$(run pg-recovery-drill "${drill_pod}")"

echo "primary"
echo "${primary}"
echo "scratch"
echo "${scratch}"

if [[ "${primary}" == "${scratch}" ]]; then
  echo "PASS counts and max timestamps match at ${TARGET_TIME}"
  exit 0
fi
echo "FAIL primary and scratch differ at ${TARGET_TIME}" >&2
exit 1
