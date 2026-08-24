#!/usr/bin/env bash
# Delegate to bifrost-platform-plugin-flex-query/scripts/sync_flex_tokens.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN="${FLEX_QUERY_ROOT:-$ROOT/../bifrost-platform-plugin-flex-query}"
SCRIPT="$PLUGIN/scripts/sync_flex_tokens.sh"
if [[ ! -x "$SCRIPT" && ! -f "$SCRIPT" ]]; then
  echo "Missing $SCRIPT" >&2
  exit 1
fi
export BIFROST_TRADE_INFRA_ENV="${BIFROST_TRADE_INFRA_ENV:-$ROOT/.env}"
bash "$SCRIPT"
