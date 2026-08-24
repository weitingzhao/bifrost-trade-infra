#!/usr/bin/env bash
# RETIRED Wave 6 — ops_audit_log table removed.
echo "SKIP: verify_wave4_audit_retention.sh retired (Wave 6); use verify_wave6_ops_audit_retired.sh"
exit 0

# --- legacy script below (not executed) ---
# Wave 4 Item B retention: no monthly ops_audit_log partitions older than 3 months.
#
# Run AFTER db-init / api restart (ensure_tables drops stale partitions) or after
#   python scripts/db/drop_ops_audit_partitions.py --months 3
#
# Usage: ./scripts/verify_wave4_audit_retention.sh [dev|stg|prod|all]
#
set -euo pipefail

ENVS="${1:-all}"
if [[ "$ENVS" == "all" ]]; then
  ENVS="dev stg prod"
fi

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"

PRIMARY="$(kubectl get cluster bifrost-postgres -n data -o jsonpath='{.status.currentPrimary}')"
if [[ -z "$PRIMARY" ]]; then
  echo "FATAL: cannot resolve CNPG primary" >&2
  exit 2
fi

trade_db_for() {
  case "$1" in
    dev)  echo "bifrost_dev"  ;;
    stg)  echo "bifrost_stg"  ;;
    prod) echo "bifrost_prod" ;;
    *)    echo "" ;;
  esac
}

# Cutoff = first day of month, 3 months ago (same as Python helper).
CUTOFF="$(python3 - <<'PY'
from datetime import date
d = date.today().replace(day=1)
y = d.year + (d.month - 1 - 3) // 12
m = (d.month - 1 - 3) % 12 + 1
print(f"{y:04d}-{m:02d}-01")
PY
)"
echo "Retention cutoff (exclusive): partitions with month start < $CUTOFF must be absent"

FAIL=0
for ENV in $ENVS; do
  DB="$(trade_db_for "$ENV")"
  echo
  echo "==================== $ENV ($DB) ===================="
  PARTS="$(kubectl exec -n data "$PRIMARY" -c postgres -- \
    psql -U postgres -d "$DB" -tAc "
SELECT COALESCE(string_agg(c.relname, ',' ORDER BY c.relname), '')
FROM pg_inherits i
JOIN pg_class c ON c.oid = i.inhrelid
JOIN pg_class p ON p.oid = i.inhparent
JOIN pg_namespace pn ON pn.oid = p.relnamespace
WHERE pn.nspname='public' AND p.relname='ops_audit_log'
  AND c.relname ~ '^ops_audit_log_y[0-9]{4}m[0-9]{2}$';
")"
  echo "[$ENV] monthly partitions: ${PARTS:-<none>}"
  if [[ -z "$PARTS" ]]; then
    echo "[$ENV] WARN: no monthly partitions (table may still be heap — run verify_wave4_audit_partitioned.sh)"
    continue
  fi
  IFS=',' read -ra ARR <<< "$PARTS"
  for part in "${ARR[@]}"; do
    part="$(echo "$part" | tr -d '[:space:]')"
    [[ -z "$part" ]] && continue
    y="${part: -7:4}"
    m="${part: -2}"
    part_month="${y}-${m}-01"
    if [[ "$part_month" < "$CUTOFF" ]]; then
      echo "[$ENV] FAIL: stale partition $part (month $part_month < $CUTOFF)"
      FAIL=1
    else
      echo "[$ENV] OK: $part"
    fi
  done
done

if [[ "$FAIL" -ne 0 ]]; then
  echo "RESULT: FAIL"
  exit 1
fi
echo "RESULT: PASS"
exit 0
