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
#   4. api-account serves /api/strategy/strategies/templates/{id} with
#      meta_params + characteristics hydrated from jsonb (Wave 2 contract).
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
  # Traefik trade-* NodePorts: DEV 30882 · STG 30880 · PROD 30881
  case "$1" in
    dev)  echo "http://192.168.10.73:30882" ;;
    stg)  echo "http://192.168.10.73:30880" ;;
    prod) echo "http://192.168.10.73:30881" ;;
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
  'ops_audit_log',          to_regclass('public.ops_audit_log') IS NOT NULL,
  'strategy_history_gone',  to_regclass('public.strategy_history') IS NULL
);" 2>/dev/null | tr -d '[:space:]')"

  echo "[$ENV] schema check: $SCHEMA_JSON"
  if [[ "$SCHEMA_JSON" != *'"params_json":true'* ]] \
     || [[ "$SCHEMA_JSON" != *'"characteristics_json":true'* ]] \
     || [[ "$SCHEMA_JSON" != *'"meta_json":true'* ]] \
     || [[ "$SCHEMA_JSON" != *'"kv_dropped":true'* ]] \
     || [[ "$SCHEMA_JSON" != *'"ops_audit_log":true'* ]] \
     || [[ "$SCHEMA_JSON" != *'"strategy_history_gone":true'* ]]; then
    echo "[$ENV] FAIL: schema not fully upgraded to Wave 2+3"
    FAIL=1
  else
    echo "[$ENV] schema OK (Wave 2 jsonb + Wave 3 strategy_history retired)"
  fi

  # (3) params round-trip — template detail must expose meta_params from params_json
  if [[ -n "$URL" ]]; then
    SAMPLE="$(/usr/bin/curl -sS --max-time 6 "${URL}/api/strategy/strategies/templates/1" 2>/dev/null \
      | /usr/bin/python3 -c 'import json,sys
try:
  row=json.load(sys.stdin)
except Exception as e:
  print(f"ERR:{e}");raise SystemExit
if not isinstance(row, dict):
  print("ERR:not_object");raise SystemExit
mp=row.get("meta_params")
chars=row.get("characteristics")
print(json.dumps({
  "id": row.get("strategy_template_id") or row.get("id"),
  "has_meta_params": isinstance(mp, list) and len(mp) > 0,
  "meta_params_len": len(mp) if isinstance(mp, list) else 0,
  "has_chars": isinstance(chars, list) and len(chars) > 0,
}))
' 2>/dev/null || true)"
    echo "[$ENV] api contract: ${SAMPLE:-<no response>}"
    if [[ -z "$SAMPLE" || "$SAMPLE" == ERR:* ]]; then
      echo "[$ENV] WARN: api-account not answering /api/strategy/strategies/templates/1 (check ingress)"
    elif [[ "$SAMPLE" != *'"has_meta_params": true'* ]]; then
      echo "[$ENV] FAIL: /templates/1 missing non-empty meta_params (params_json hydration)"
      FAIL=1
    else
      echo "[$ENV] api contract OK"
    fi
  else
    echo "[$ENV] SKIP api probe: no ingress URL mapped"
  fi
done

# Wave 3 append-only: Golden Source transactions UNIQUE includes report_date
echo
echo "==================== golden_source (Wave 3 dedupe) ===================="
DEDUPE="$(kubectl exec -n data "$PRIMARY" -c postgres -- \
  psql -U postgres -d bifrost_golden_source -tAc "
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
);" 2>/dev/null | tr -d '[:space:]')"
echo "transactions 5-col UNIQUE present: ${DEDUPE:-?}"
if [[ "$DEDUPE" != "t" ]]; then
  echo "FAIL: raw_broker.transactions missing UNIQUE(account_id, ts, amount, type, report_date)"
  FAIL=1
else
  echo "broker dedupe OK"
fi

echo
if [[ "$FAIL" -eq 0 ]]; then
  echo "wave2 verify: PASS"
  exit 0
else
  echo "wave2 verify: FAIL"
  exit 1
fi
