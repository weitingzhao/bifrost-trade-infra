#!/usr/bin/env bash
# Strict single-variable Phase 2B: set ONE VITE_API_* to Legacy or New; others stay New.
# Usage:
#   ./scripts/switch_cutover_domain.sh docs legacy
#   ./scripts/switch_cutover_domain.sh monitor new
#   ./scripts/switch_cutover_domain.sh all-new
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${FRONTEND_DIR:-${ROOT}/../bifrost-trade-frontend}/.env.development"
EXAMPLE="${ROOT}/../bifrost-trade-frontend/.env.development.example"

usage() {
  echo "Usage: $0 <domain|all-new> [legacy|new]"
  echo "Domains: docs monitor market trading portfolio strategy ops massive research"
  exit 1
}

domain_var() {
  case "$1" in
    docs) echo "VITE_API_DOCS" ;;
    monitor) echo "VITE_API_MONITOR" ;;
    market) echo "VITE_API_MARKET" ;;
    trading) echo "VITE_API_TRADING" ;;
    portfolio) echo "VITE_API_PORTFOLIO" ;;
    strategy) echo "VITE_API_STRATEGY" ;;
    ops) echo "VITE_API_OPS" ;;
    massive) echo "VITE_API_MASSIVE" ;;
    research) echo "VITE_API_RESEARCH" ;;
    *) return 1 ;;
  esac
}

domain_legacy_port() {
  case "$1" in
    docs) echo 8719 ;;
    monitor) echo 8711 ;;
    market) echo 8733 ;;
    trading) echo 8721 ;;
    portfolio) echo 8723 ;;
    strategy) echo 8735 ;;
    ops) echo 8713 ;;
    massive) echo 8741 ;;
    research) echo 8731 ;;
    *) return 1 ;;
  esac
}

domain_new_port() {
  case "$1" in
    docs) echo 8767 ;;
    monitor) echo 8765 ;;
    market) echo 8772 ;;
    trading) echo 8769 ;;
    portfolio) echo 8771 ;;
    strategy) echo 8770 ;;
    ops) echo 8768 ;;
    massive) echo 8766 ;;
    research) echo 8773 ;;
    *) return 1 ;;
  esac
}

[[ $# -ge 1 ]] || usage

DOMAIN="$1"
MODE="${2:-}"

if [[ "$DOMAIN" == "all-new" ]]; then
  cp "$EXAMPLE" "$ENV_FILE"
  echo "Wrote ${ENV_FILE} from example (all New API ports)."
  echo "Restart Vite: cd bifrost-trade-frontend && npm run dev"
  exit 0
fi

key="$(domain_var "$DOMAIN")" || usage
[[ "$MODE" == "legacy" || "$MODE" == "new" ]] || usage

cp "$EXAMPLE" "$ENV_FILE"

if [[ "$MODE" == "legacy" ]]; then
  port="$(domain_legacy_port "$DOMAIN")"
else
  port="$(domain_new_port "$DOMAIN")"
fi

python3 - "$ENV_FILE" "$key" "$port" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
port = sys.argv[3]
lines = path.read_text(encoding="utf-8").splitlines()
out = []
done = False
for line in lines:
    if line.startswith(f"{key}="):
        out.append(f"{key}=http://localhost:{port}")
        done = True
    else:
        out.append(line)
if not done:
    out.append(f"{key}=http://localhost:{port}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY

echo "${key}=http://localhost:${port}  (${MODE})"
echo "Other VITE_API_* remain New (8765–8773)."
echo "Restart Vite: cd bifrost-trade-frontend && npm run dev"
