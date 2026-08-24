#!/usr/bin/env bash
# Verify Wave 3 Track A: strategy_history is retired across environments.
#
# Checks (per env: dev, stg, prod):
#   1. to_regclass('public.strategy_history') IS NULL
#   2. GET /api/strategies/history returns 404 (or 405)
#
# Usage: ./scripts/verify_wave3_strategy_history_retired.sh [dev|stg|prod|all]
#
set -euo pipefail

ENVS="${1:-all}"
if [[ "$ENVS" == "all" ]]; then
  ENVS="dev stg prod"
fi

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"

PRIMARY="$(kubectl get cluster bifrost-postgres -n data -o jsonpath='{.status.currentPrimary}')"
if [[ -z "$PRIMARY" ]]; then
  echo "FATAL: cannot resolve CNPG primary pod" >&2
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

nginx_for() {
  case "$1" in
    dev)  echo "http://192.168.10.73:30882" ;;
    stg)  echo "http://192.168.10.73:30882" ;;
    prod) echo "http://192.168.10.73:30880" ;;
    *)    echo "" ;;
  esac
}

FAIL=0

for ENV in $ENVS; do
  DB="$(trade_db_for "$ENV")"
  URL="$(nginx_for "$ENV")"
  echo
  echo "==================== $ENV ===================="

  GONE="$(kubectl exec -n data "$PRIMARY" -c postgres -- \
    psql -U postgres -d "$DB" -tAc "SELECT to_regclass('public.strategy_history') IS NULL" \
    | tr -d '[:space:]')"
  echo "[$ENV] strategy_history gone: $GONE"
  if [[ "$GONE" != "t" ]]; then
    echo "[$ENV] FAIL: strategy_history still present"
    FAIL=1
  fi

  if [[ -n "$URL" ]]; then
    CODE="$(/usr/bin/curl -sS -o /dev/null -w '%{http_code}' --max-time 6 \
      "${URL}/api/strategies/history" 2>/dev/null || echo "000")"
    echo "[$ENV] GET /api/strategies/history → HTTP $CODE"
    if [[ "$CODE" == "404" || "$CODE" == "405" ]]; then
      echo "[$ENV] API history retired OK"
    elif [[ "$CODE" == "200" ]]; then
      echo "[$ENV] WARN: /history still served (api-account image not yet on v0.12.0 — expected pre-rollout)"
    else
      echo "[$ENV] FAIL: unexpected HTTP $CODE for /history"
      FAIL=1
    fi
  fi
done

echo
if [[ "$FAIL" -eq 0 ]]; then
  echo "wave3 strategy_history retired: PASS (API WARN above is OK until deliver-stg)"
  exit 0
else
  echo "wave3 strategy_history retired: FAIL"
  exit 1
fi
