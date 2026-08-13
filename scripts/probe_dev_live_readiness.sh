#!/usr/bin/env bash
# P10 — Read-only Live readiness probe for DEV inner loop (D-IL3).
# Colors: green / yellow / red. Never writes cluster state.
set -euo pipefail

DRY_RUN=0
DEV_BASE="${DEV_TRADE_BASE:-http://192.168.10.73:30882}"
PLATFORM_BASE="${PLATFORM_API_BASE:-http://127.0.0.1:8780}"
CONNECT_TIMEOUT="${CONNECT_TIMEOUT:-4}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --help|-h)
      echo "Usage: $0 [--dry-run]"
      echo "  Probes ${DEV_BASE}/api/market and optional platform IB Gateway status."
      exit 0
      ;;
  esac
done

echo "=== probe DEV Live readiness (dry_run=${DRY_RUN}) ==="
echo "DEV_BASE=${DEV_BASE}"
echo "PLATFORM_BASE=${PLATFORM_BASE}"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo -e "${GREEN}OK${NC}  dry-run: script executable; would probe:"
  echo "  - GET ${DEV_BASE}/api/market/health (or /health)"
  echo "  - GET ${DEV_BASE}/api/market/quotes (bounded)"
  echo "  - GET ${PLATFORM_BASE}/api/v1/plugins/ib-gateway/status (optional)"
  echo "  - classify: PG stale vs Gateway vs api-market (see TRADE_DEV_INNER_LOOP.md)"
  echo -e "${GREEN}GREEN${NC} dry-run complete (no network)"
  exit 0
fi

http_code() {
  local url="$1"
  curl -s -o /dev/null -w "%{http_code}" --connect-timeout "$CONNECT_TIMEOUT" "$url" 2>/dev/null || echo "000"
}

body_snip() {
  local url="$1"
  curl -sS --connect-timeout "$CONNECT_TIMEOUT" --max-time 8 "$url" 2>/dev/null | head -c 240 || true
}

market_code=$(http_code "${DEV_BASE}/api/market/health")
if [[ "$market_code" != "200" && "$market_code" != "503" ]]; then
  # fallback common paths
  alt=$(http_code "${DEV_BASE}/api/market/")
  if [[ "$alt" == "200" || "$alt" == "401" || "$alt" == "404" ]]; then
    market_code="$alt"
  fi
fi

gateway_code=$(http_code "${PLATFORM_BASE}/api/v1/plugins/ib-gateway/status")

echo "api-market health/probe HTTP ${market_code}"
echo "ib-gateway status HTTP ${gateway_code} (optional local platform-api)"

verdict="yellow"
reason=()

if [[ "$market_code" == "000" ]]; then
  verdict="red"
  reason+=("api-market unreachable at ${DEV_BASE} — check NodePort 30882 / ingress / DEV deploy")
elif [[ "$market_code" == "200" || "$market_code" == "503" ]]; then
  reason+=("api-market reachable (${market_code})")
else
  verdict="yellow"
  reason+=("api-market unexpected HTTP ${market_code}")
fi

if [[ "$gateway_code" == "200" ]]; then
  snip=$(body_snip "${PLATFORM_BASE}/api/v1/plugins/ib-gateway/status")
  reason+=("ib-gateway status HTTP 200: ${snip}")
  # Prefer JSON reachability when present (reachable:false → yellow, not green)
  if echo "$snip" | grep -qE '"reachable"[[:space:]]*:[[:space:]]*false|"reachability"[[:space:]]*:[[:space:]]*"fail"'; then
    if [[ "$verdict" != "red" ]]; then
      verdict="yellow"
    fi
    reason+=("Gateway/redis-ib path degraded (reachable=false or reachability=fail) — check TWS / IB Gateway manage")
  elif echo "$snip" | grep -qE '"reachable"[[:space:]]*:[[:space:]]*true|"reachability"[[:space:]]*:[[:space:]]*"ok"'; then
    if [[ "$verdict" != "red" && "$verdict" != "yellow" ]]; then
      verdict="green"
    fi
  else
    if [[ "$verdict" != "red" ]]; then
      verdict="yellow"
    fi
    reason+=("Gateway status body ambiguous — treat Live ticks as unverified")
  fi
elif [[ "$gateway_code" == "000" ]]; then
  reason+=("platform-api IB Gateway status skipped (not reachable on ${PLATFORM_BASE})")
  if [[ "$verdict" != "red" && "$market_code" == "200" ]]; then
    verdict="yellow"
    reason+=("cannot confirm Gateway — treat Live ticks as unverified")
  fi
else
  reason+=("ib-gateway status HTTP ${gateway_code}")
  if [[ "$verdict" != "red" ]]; then
    verdict="yellow"
  fi
fi

# Soft quotes probe — yellow if empty/error body
quotes_code=$(http_code "${DEV_BASE}/api/market/quotes")
if [[ "$quotes_code" == "200" ]]; then
  reason+=("quotes endpoint HTTP 200")
  # api-market + quotes OK and Gateway not degraded → green
  if [[ "$verdict" != "red" && "$verdict" != "yellow" && "$market_code" == "200" ]]; then
    verdict="green"
  fi
elif [[ "$market_code" == "200" ]]; then
  reason+=("quotes endpoint HTTP ${quotes_code} (may be empty watchlist — see on-demand bridge docs)")
  if [[ "$verdict" == "green" ]]; then
    verdict="yellow"
  fi
fi

# If only api-market is up and Gateway check did not set color, stay yellow unless green already
if [[ "$verdict" != "red" && "$verdict" != "green" && "$verdict" != "yellow" ]]; then
  verdict="yellow"
fi

case "$verdict" in
  green) echo -e "${GREEN}VERDICT green${NC} — Live path looks ready (confirm ticks in UI)" ;;
  yellow) echo -e "${YELLOW}VERDICT yellow${NC} — partial / diagnose before trusting Live" ;;
  red) echo -e "${RED}VERDICT red${NC} — api-market or entry broken" ;;
esac

for r in "${reason[@]}"; do
  echo "  - $r"
done

echo "Failure UX classes: PG stale | Gateway/redis-ib | api-market — see docs/TRADE_DEV_INNER_LOOP.md"
[[ "$verdict" == "red" ]] && exit 2
[[ "$verdict" == "yellow" ]] && exit 1
exit 0
