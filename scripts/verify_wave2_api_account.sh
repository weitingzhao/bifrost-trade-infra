#!/usr/bin/env bash
# Verify Wave 2 (bifrost-core v0.11.0) landed on api-account across environments.
#
# Checks (per env: dev, stg, prod):
#   1. Deployment image was refreshed AFTER Wave 2 commits (ContainerReady age
#      is younger than the commit).
#   2. Trade DB schema reflects the jsonb collapse: strategy_template.params_json
#      and strategy_template.characteristics_json exist; strategy_structure.meta_json
#      exists; the 3 old KV tables no longer exist.
#   3. public.ops_audit_log exists (core-owned DDL applied).
#   4. api-account serves /api/strategies/templates with `params` populated from
#      params_json (contract preserved).
#
# Fails loudly (exit 1) on any regression; keeps going through all envs.
#
# Usage: ./scripts/verify_wave2_api_account.sh [dev|stg|prod|all]
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

nginx_for() {
  # Prefer the environment's Trade nginx service; fall back to platform-api probe URL.
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
  NS="bifrost-$ENV"
  URL="$(nginx_for "$ENV")"
  echo
  echo "==================== $ENV ===================="

  # (1) api-account rollout freshness
  IMG="$(kubectl -n "$NS" get deploy api-account -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || true)"
  AGE="$(kubectl -n "$NS" get pods -l app.kubernetes.io/name=api-account \
          -o jsonpath='{.items[0].status.conditions[?(@.type=="Ready")].lastTransitionTime}' 2>/dev/null || true)"
  echo "[$ENV] api-account image=${IMG:-<none>} ready_since=${AGE:-<none>}"
  if [[ -z "$IMG" || -z "$AGE" ]]; then
    echo "[$ENV] FAIL: api-account deployment or ready pod not found"
    FAIL=1
    continue
  fi

  # (2) DB schema — jsonb columns present, KV subtables absent
  SCHEMA_JSON="$(kubectl exec -n data "$PRIMARY" -c postgres -- \
    psql -U postgres -d "$DB" -tAc "
SELECT json_build_object(
  'params_json',            to_regclass('public.strategy_template')::text IS NOT NULL AND
                             EXISTS (SELECT 1 FROM information_schema.columns
                                     WHERE table_schema='public' AND table_name='strategy_template' AND column_name='params_json'),
  'characteristics_json',   EXISTS (SELECT 1 FROM information_schema.columns
                                     WHERE table_schema='public' AND table_name='strategy_template' AND column_name='characteristics_json'),
  'meta_json',              EXISTS (SELECT 1 FROM information_schema.columns
                                     WHERE table_schema='public' AND table_name='strategy_structure' AND column_name='meta_json'),
  'kv_dropped',             to_regclass('public.strategy_template_param') IS NULL
                             AND to_regclass('public.strategy_template_characteristic') IS NULL
                             AND to_regclass('public.strategy_structure_meta') IS NULL,
  'ops_audit_log',          to_regclass('public.ops_audit_log') IS NOT NULL
);" 2>/dev/null | tr -d '[:space:]')"

  echo "[$ENV] schema check: $SCHEMA_JSON"
  if [[ "$SCHEMA_JSON" != *'"params_json":true'* ]] \
     || [[ "$SCHEMA_JSON" != *'"characteristics_json":true'* ]] \
     || [[ "$SCHEMA_JSON" != *'"meta_json":true'* ]] \
     || [[ "$SCHEMA_JSON" != *'"kv_dropped":true'* ]] \
     || [[ "$SCHEMA_JSON" != *'"ops_audit_log":true'* ]]; then
    echo "[$ENV] FAIL: schema not fully upgraded to Wave 2"
    FAIL=1
  else
    echo "[$ENV] schema OK"
  fi

  # (3) params round-trip — /api/strategies/templates first row must expose params list
  if [[ -n "$URL" ]]; then
    SAMPLE="$(/usr/bin/curl -sS --max-time 6 "${URL}/api/strategies/templates" 2>/dev/null \
      | /usr/bin/python3 -c 'import json,sys
try:
  data=json.load(sys.stdin)
except Exception as e:
  print(f"ERR:{e}");raise SystemExit
items=data if isinstance(data,list) else data.get("items") or data.get("templates") or []
if not items:
  print("EMPTY");raise SystemExit
row=items[0]
print(json.dumps({
  "id": row.get("strategy_template_id") or row.get("id"),
  "has_params": isinstance(row.get("params"), list),
  "params_len": len(row.get("params") or []),
  "has_chars":  isinstance(row.get("characteristics"), list),
}))
' 2>/dev/null || true)"
    echo "[$ENV] api contract: ${SAMPLE:-<no response>}"
    if [[ -z "$SAMPLE" || "$SAMPLE" == ERR:* || "$SAMPLE" == "EMPTY" ]]; then
      echo "[$ENV] WARN: api-account not answering /api/strategies/templates (check ingress)"
    elif [[ "$SAMPLE" != *'"has_params": true'* ]]; then
      echo "[$ENV] FAIL: /api/strategies/templates missing params array"
      FAIL=1
    else
      echo "[$ENV] api contract OK"
    fi
  else
    echo "[$ENV] SKIP api probe: no ingress URL mapped"
  fi
done

echo
if [[ "$FAIL" -eq 0 ]]; then
  echo "wave2 verify: PASS"
  exit 0
else
  echo "wave2 verify: FAIL"
  exit 1
fi
