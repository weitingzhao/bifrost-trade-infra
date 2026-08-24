#!/usr/bin/env bash
# Wave 6: public.ops_audit_log must be absent in Trade DBs (retired → platform-api audit).
#
# Usage: ./scripts/verify_wave6_ops_audit_retired.sh [dev|stg|prod|all]
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
  echo "===== $ENV ($DB) ====="
  OUT="$(kubectl exec -n data "$PRIMARY" -c postgres -- \
    psql -U postgres -d "$DB" -tAc "
SELECT
  to_regclass('public.ops_audit_log') IS NULL AS retired,
  (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relname LIKE 'ops_audit_log%') AS rel_count;
" 2>/dev/null | tr -d '[:space:]')"
  echo "  ops_audit_log check: retired=${OUT}"
  if [[ "$OUT" != "t|0" ]]; then
    echo "  FAIL: ops_audit_log or partitions still present"
    FAIL=1
  else
    echo "  OK"
  fi
done

if [[ "$FAIL" -ne 0 ]]; then
  echo "verify_wave6_ops_audit_retired: FAIL" >&2
  exit 1
fi
echo "verify_wave6_ops_audit_retired: PASS"
