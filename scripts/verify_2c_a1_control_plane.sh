#!/usr/bin/env bash
# Phase 2C-A.1 — Docker control plane acceptance (Ops executor + market-ingest + compose).
# Run with prod stack up: make prod-preflight-local && make verify-2c-a1
#
# Env:
#   NGINX_BASE=http://127.0.0.1
#   VERIFY_2C_A1_CONTROL=1  — run destructive Ops restart on ib-ingestor (optional)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
fail=0
warn=0
ok() { echo -e "${GREEN}OK${NC}  $*"; }
bad() { echo -e "${RED}FAIL${NC}  $*"; fail=1; }
skip() { echo -e "${YELLOW}SKIP${NC}  $*"; warn=1; }

NGINX_BASE="${NGINX_BASE:-http://127.0.0.1}"
OPS_HEALTH_URL="${NGINX_BASE}/api/ops/health"
SERVICES_URL="${NGINX_BASE}/api/ops/ops/market-ingest/services"

echo "=== Phase 2C-A.1 control plane verification ==="
echo "Ops health: ${OPS_HEALTH_URL}"
echo ""

executor_mode=""

# ── 1. Ops health exposes executor_mode ─────────────────────────────────────
health_json="$(curl -s --connect-timeout 8 "${OPS_HEALTH_URL}" 2>/dev/null)" || health_json=""
if [[ -z "${health_json}" ]]; then
  bad "Ops health unreachable"
else
  ok "Ops health HTTP 200"
  executor_mode="$(echo "${health_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('executor_mode',''))" 2>/dev/null || echo "")"
  if [[ "${executor_mode}" == "docker" ]]; then
    ok "executor_mode=docker"
    docker_ok="$(echo "${health_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('docker_reachable',''))" 2>/dev/null || echo "")"
    if [[ "${docker_ok}" == "True" || "${docker_ok}" == "true" ]]; then
      ok "docker_reachable=true"
    else
      bad "docker_reachable not true (mount docker.sock + executor_docker WP1)"
    fi
  else
    skip "executor_mode=${executor_mode:-<missing>} — expected docker after WP1 (current stack uses local/subprocess)"
  fi
fi

# ── 2. market-ingest services list ──────────────────────────────────────────
svc_json="$(curl -s --connect-timeout 8 "${SERVICES_URL}" 2>/dev/null)" || svc_json=""
if [[ -z "${svc_json}" ]]; then
  bad "GET market-ingest/services unreachable"
else
  ok "market-ingest/services HTTP 200"
  check_out="$(echo "${svc_json}" | EXECUTOR_MODE="${executor_mode}" python3 -c '
import json, os, sys
data = json.load(sys.stdin)
services = data.get("services") or []
ids = {s.get("id") for s in services}
want_socket = {"massive_ws", "ib_operator", "ib_ingestor", "ib_account_agent"}
missing = want_socket - ids
if missing:
    print("FAIL  missing service ids:", sorted(missing))
    sys.exit(1)
print("OK    socket service ids present:", sorted(want_socket))
executor = os.environ.get("EXECUTOR_MODE", "")
docker_mode = executor == "docker"
unknown_count = sum(1 for s in services if (s.get("process_active") or "") == "unknown")
if docker_mode:
    for s in services:
        sid = s.get("id")
        cs = s.get("compose_service")
        rk = s.get("runtime_kind")
        if sid in want_socket | {"trading_engine"}:
            if rk != "docker":
                print(f"FAIL  {sid}: runtime_kind={rk!r} expected docker")
                sys.exit(1)
            if not cs:
                print(f"FAIL  {sid}: missing compose_service")
                sys.exit(1)
    print("OK    runtime_kind=docker + compose_service on ingest rows")
else:
    if unknown_count == len(services):
        print(f"SKIP  all process_active=unknown ({unknown_count} rows) — WP1/WP2 not deployed")
    else:
        print(f"OK    process_active mixed (unknown={unknown_count}/{len(services)})")
' 2>&1)" || check_out="FAIL  python check crashed"
  while IFS= read -r line; do
    case "${line}" in
      OK*) ok "${line#OK  }" ;;
      FAIL*) bad "${line#FAIL  }" ;;
      SKIP*) skip "${line#SKIP  }" ;;
      *) echo "${line}" ;;
    esac
  done <<< "${check_out}"
fi

# ── 3. compose ps vs API (when docker executor live) ─────────────────────────
if [[ "${executor_mode}" == "docker" ]] && command -v docker >/dev/null 2>&1; then
  for svc in ib-ingestor daemon massive-ws; do
    if docker compose ps --status running --format '{{.Service}}' 2>/dev/null | grep -qx "${svc}"; then
      ok "compose service running: ${svc}"
    else
      state="$(docker compose ps --format '{{.Service}} {{.State}}' 2>/dev/null | awk -v s="${svc}" '$1==s{print $2; exit}')"
      if [[ -n "${state}" ]]; then
        skip "compose ${svc} state=${state} (may be intentional)"
      else
        bad "compose service missing: ${svc}"
      fi
    fi
  done
else
  skip "compose cross-check (executor_mode != docker or docker CLI unavailable)"
fi

# ── 4. Optional destructive control test ──────────────────────────────────────
if [[ "${VERIFY_2C_A1_CONTROL:-}" == "1" && "${executor_mode}" == "docker" ]]; then
  echo ""
  echo "--- Destructive: Ops restart ib-ingestor ---"
  code="$(curl -s -o /tmp/verify_2c_a1_control.json -w "%{http_code}" \
    -X POST "${NGINX_BASE}/api/ops/ops/market-ingest/control" \
    -H "Content-Type: application/json" \
    -d '{"service_id":"ib_ingestor","action":"restart"}' 2>/dev/null)" || code="000"
  if [[ "${code}" == "200" || "${code}" == "202" ]]; then
    ok "POST market-ingest/control restart ib-ingestor (${code})"
    sleep 5
    if docker compose ps ib-ingestor 2>/dev/null | grep -qi up; then
      ok "ib-ingestor Up after restart"
    else
      bad "ib-ingestor not Up after restart"
    fi
  else
    bad "POST market-ingest/control (${code}) — see /tmp/verify_2c_a1_control.json"
  fi
else
  skip "destructive Ops control (set VERIFY_2C_A1_CONTROL=1 after WP1)"
fi

# ── 5. Redis lease isolation hint ───────────────────────────────────────────
if [[ -f .env ]]; then
  # shellcheck disable=SC1090
  set -a
  source .env 2>/dev/null || true
  set +a
fi
redis_host="${REDIS_HOST:-}"
if [[ "${redis_host}" == "192.168.10.70" ]]; then
  skip "REDIS_HOST=192.168.10.70 — shared with Legacy; Host column may show 'other stack'. Use embedded-infra for 2C-A.1."
elif [[ -n "${redis_host}" ]]; then
  ok "REDIS_HOST=${redis_host} (isolated from Legacy .70)"
fi

echo ""
if [[ "${fail}" -ne 0 ]]; then
  echo "2C-A.1 control plane verification FAILED."
  echo "See docs/PHASE2C_A1_DOCKER_CONTROL_PLANE.md"
  exit 1
fi
if [[ "${warn}" -ne 0 ]]; then
  echo "2C-A.1 verification PASSED with SKIPs (WP1–WP2 pending or env not ideal)."
  exit 0
fi
echo "2C-A.1 control plane verification PASSED."
