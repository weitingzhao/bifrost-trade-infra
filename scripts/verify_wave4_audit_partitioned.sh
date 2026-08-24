#!/usr/bin/env bash
# RETIRED Wave 6 — ops_audit_log partitioned table removed.
# Use scripts/verify_wave6_ops_audit_retired.sh instead.
echo "SKIP: verify_wave4_audit_partitioned.sh retired (Wave 6); use verify_wave6_ops_audit_retired.sh"
exit 0

# --- legacy script below (not executed) ---
# Wave 4 Item B: ops_audit_log is RANGE-partitioned with timestamptz.
#
# Per env (dev/stg/prod):
#   1. public.ops_audit_log exists and relkind = 'p' (partitioned)
#   2. column timestamp data_type = timestamp with time zone
#   3. at least one monthly child (ops_audit_log_yYYYYmMM) or _default exists
#
# Usage: ./scripts/verify_wave4_audit_partitioned.sh [dev|stg|prod|all]
#
set -euo pipefail

ENVS="${1:-all}"
if [[ "$ENVS" == "all" ]]; then
  ENVS="dev stg prod"
fi

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"

PRIMARY="$(kubectl get cluster bifrost-postgres -n data -o jsonpath='{.status.currentPrimary}')"
if [[ -z "$PRIMARY" ]]; then
  echo "FATAL: cannot resolve CNPG primary pod in data namespace" >&2
  exit 2
fi
echo "CNPG primary = $PRIMARY"

trade_db_for() {
  case "$1" in
    dev)  echo "bifrost_dev"  ;;
    stg)  echo "bifrost_stg"  ;;
    prod) echo "bifrost_prod" ;;
    *)    echo "" ;;
  esac
}

FAIL=0
for ENV in $ENVS; do
  DB="$(trade_db_for "$ENV")"
  echo
  echo "==================== $ENV ($DB) ===================="

  ROW="$(kubectl exec -n data "$PRIMARY" -c postgres -- \
    psql -U postgres -d "$DB" -tAc "
SELECT json_build_object(
  'exists', to_regclass('public.ops_audit_log') IS NOT NULL,
  'partitioned', EXISTS (
      SELECT 1 FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname='public' AND c.relname='ops_audit_log' AND c.relkind='p'
  ),
  'ts_type', (
      SELECT data_type FROM information_schema.columns
      WHERE table_schema='public' AND table_name='ops_audit_log' AND column_name='timestamp'
  ),
  'child_count', (
      SELECT COUNT(*) FROM pg_inherits i
      JOIN pg_class c ON c.oid = i.inhrelid
      JOIN pg_class p ON p.oid = i.inhparent
      JOIN pg_namespace pn ON pn.oid = p.relnamespace
      WHERE pn.nspname='public' AND p.relname='ops_audit_log'
  )
);
")"
  echo "[$ENV] $ROW"

  python3 - "$ENV" "$ROW" <<'PY' || FAIL=1
import json, sys
env, raw = sys.argv[1], sys.argv[2].strip()
try:
    d = json.loads(raw)
except Exception as e:
    print(f"[{env}] FAIL: cannot parse JSON: {e}")
    sys.exit(1)
ok = True
if not d.get("exists"):
    print(f"[{env}] FAIL: ops_audit_log missing"); ok = False
if not d.get("partitioned"):
    print(f"[{env}] FAIL: ops_audit_log is not PARTITION BY RANGE (relkind!=p)"); ok = False
else:
    print(f"[{env}] OK: partitioned")
if d.get("ts_type") != "timestamp with time zone":
    print(f"[{env}] FAIL: timestamp type={d.get('ts_type')!r} want timestamptz"); ok = False
else:
    print(f"[{env}] OK: timestamptz")
if int(d.get("child_count") or 0) < 1:
    print(f"[{env}] FAIL: no partition children"); ok = False
else:
    print(f"[{env}] OK: {d['child_count']} partition child(ren)")
sys.exit(0 if ok else 1)
PY
done

if [[ "$FAIL" -ne 0 ]]; then
  echo "RESULT: FAIL"
  exit 1
fi
echo "RESULT: PASS"
exit 0
