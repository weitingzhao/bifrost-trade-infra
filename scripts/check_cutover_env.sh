#!/usr/bin/env bash
# Compare frontend .env.development against .env.development.example (new API ports).
set -euo pipefail

FRONTEND_DIR="${FRONTEND_DIR:-../bifrost-trade-frontend}"
DEV="${FRONTEND_DIR}/.env.development"
EXAMPLE="${FRONTEND_DIR}/.env.development.example"

if [[ ! -f "$DEV" ]]; then
  echo "Missing ${DEV}"
  exit 1
fi
if [[ ! -f "$EXAMPLE" ]]; then
  echo "Missing ${EXAMPLE}"
  exit 1
fi

LEGACY_PORTS="8711 8713 8719 8721 8723 8731 8733 8735 8741"
fail=0

echo "=== VITE_API_* in .env.development ==="
while IFS= read -r line; do
  [[ "$line" =~ ^VITE_API_ ]] || continue
  echo "  $line"
  for p in $LEGACY_PORTS; do
    if [[ "$line" == *":${p}"* ]] || [[ "$line" == *":${p}/"* ]]; then
      echo "  FAIL still on Legacy port ${p}"
      fail=1
    fi
  done
done < "$DEV"

echo ""
echo "=== Diff vs .env.development.example ==="
if diff -u "$EXAMPLE" "$DEV"; then
  echo "OK  .env.development matches example"
else
  echo "NOTE  diff above (may be OK if only ordering differs)"
fi

if [[ "$fail" -ne 0 ]]; then
  echo "Cutover env check failed: Legacy ports still in use."
  exit 1
fi
echo "Cutover env check passed (no Legacy ports)."
