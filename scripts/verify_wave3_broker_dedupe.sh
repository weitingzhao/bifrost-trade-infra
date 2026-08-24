#!/usr/bin/env bash
# Verify Wave 3 Track B: raw_broker.transactions UNIQUE includes report_date.
#
# Checks on bifrost_golden_source:
#   1. A UNIQUE constraint exists on (account_id, ts, amount, type, report_date)
#   2. Two synthetic rows with the same 4-col key but different report_date
#      can coexist (then cleaned up)
#   3. Row count is unchanged after the smoke insert/delete
#
# Usage: ./scripts/verify_wave3_broker_dedupe.sh
#
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"

PRIMARY="$(kubectl get cluster bifrost-postgres -n data -o jsonpath='{.status.currentPrimary}')"
if [[ -z "$PRIMARY" ]]; then
  echo "FATAL: cannot resolve CNPG primary pod" >&2
  exit 2
fi

psql_gs() {
  kubectl exec -n data "$PRIMARY" -c postgres -- \
    psql -U postgres -d bifrost_golden_source -tAc "$1"
}

echo "=== Wave 3 broker dedupe verify ==="

BEFORE="$(psql_gs "SELECT count(*) FROM raw_broker.transactions" | tr -d '[:space:]')"
echo "row_count_before=$BEFORE"

HAS_V2="$(psql_gs "
SELECT EXISTS (
  SELECT 1
  FROM pg_constraint c
  JOIN pg_class t ON t.oid = c.conrelid
  JOIN pg_namespace n ON n.oid = t.relnamespace
  JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS u(attnum, ord) ON true
  JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = u.attnum
  WHERE n.nspname = 'raw_broker'
    AND t.relname = 'transactions'
    AND c.contype = 'u'
  GROUP BY c.conname
  HAVING array_agg(a.attname ORDER BY u.ord)::text[]
       = ARRAY['account_id','ts','amount','type','report_date']::text[]
);" | tr -d '[:space:]')"

echo "5-col UNIQUE present: $HAS_V2"
if [[ "$HAS_V2" != "t" ]]; then
  echo "FAIL: missing UNIQUE(account_id, ts, amount, type, report_date)"
  exit 1
fi

# Synthetic coexistence smoke — same 4-col key, different report_date
TAG="wave3_dedupe_$(date -u +%Y%m%dT%H%M%SZ)"
TS='2020-01-01 00:00:00+00'
AMT='-0.01'
TYPE='other'
ACCT='WAVE3_VERIFY'

psql_gs "
INSERT INTO raw_broker.transactions
  (account_id, ts, amount, type, currency, description, report_date, flex_type, fx_rate_to_base, raw_extra)
VALUES
  ('$ACCT', '$TS', $AMT, '$TYPE', 'USD', '$TAG-a', '2020-01-01', 'other', 1.0, '{}'::jsonb),
  ('$ACCT', '$TS', $AMT, '$TYPE', 'USD', '$TAG-b', '2020-01-02', 'other', 1.0, '{}'::jsonb);
" >/dev/null

INSERTED="$(psql_gs "
SELECT count(*) FROM raw_broker.transactions
WHERE account_id='$ACCT' AND description LIKE '$TAG%'
" | tr -d '[:space:]')"
echo "synthetic_pair_count=$INSERTED"
if [[ "$INSERTED" != "2" ]]; then
  echo "FAIL: expected 2 coexisting rows with different report_date (got $INSERTED)"
  psql_gs "DELETE FROM raw_broker.transactions WHERE account_id='$ACCT' AND description LIKE '$TAG%'" >/dev/null || true
  exit 1
fi

psql_gs "DELETE FROM raw_broker.transactions WHERE account_id='$ACCT' AND description LIKE '$TAG%'" >/dev/null
AFTER="$(psql_gs "SELECT count(*) FROM raw_broker.transactions" | tr -d '[:space:]')"
echo "row_count_after=$AFTER"

if [[ "$AFTER" != "$BEFORE" ]]; then
  echo "FAIL: row count changed ($BEFORE → $AFTER) after cleanup"
  exit 1
fi

echo "wave3 broker dedupe: PASS"
exit 0
