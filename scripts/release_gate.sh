#!/usr/bin/env bash
# Release gate — aggregate prod matrix + K3s stg smoke via Ops Platform API (Session S6).
# Prefer Console → Promote → Run release gate; this script is the bootstrap executor.
#
# Usage:
#   PLATFORM_ADMIN_TOKEN=platform-admin-dev ./scripts/release_gate.sh
#   make release-gate
set -euo pipefail

PLATFORM_API="${PLATFORM_API:-http://127.0.0.1:8780}"
TOKEN="${PLATFORM_ADMIN_TOKEN:-${PLATFORM_OPERATOR_TOKEN:-}}"

if [[ -z "${TOKEN}" ]]; then
  echo "Set PLATFORM_ADMIN_TOKEN (admin role required for POST /promote/release-gate)" >&2
  exit 1
fi

echo "==> POST ${PLATFORM_API}/api/v1/promote/release-gate"
resp="$(curl -sS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${PLATFORM_API}/api/v1/promote/release-gate")"

echo "${resp}" | python3 -m json.tool 2>/dev/null || echo "${resp}"

ok="$(echo "${resp}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok', False))" 2>/dev/null || echo false)"
if [[ "${ok}" != "True" && "${ok}" != "true" ]]; then
  echo "Release gate failed." >&2
  exit 1
fi
echo "Release gate complete."
