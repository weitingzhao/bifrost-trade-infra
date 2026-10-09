#!/usr/bin/env bash
# Temp directories and fake dotenv values. Output must not contain the values.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${ROOT}/move-owner-secrets.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ADMIN="sekrit-admin-value"
REDIS="sekrit-redis-value"
PREV="sekrit-prev-value"
NEXT="sekrit-next-value"
UNIFI="sekrit-unifi-value"
FILEVAL="sekrit-file-value"
mkdir -p "$TMP/secrets" "$TMP/workspace/bifrost-platform"
printf 'KEEP=stay\nOPS_ADMIN_TOKEN=%s\nREDIS_IB_PASSWORD=%s\nBIFROST_PG_PASSWORD_PREVIOUS=%s\nBIFROST_PG_PASSWORD_NEXT=%s\n' \
  "$ADMIN" "$REDIS" "$PREV" "$NEXT" >"$TMP/infra.env"
printf 'OTHER=1\nUNIFI_HOST=192.0.2.1\nUNIFI_USER=owner\nUNIFI_PASS=%s\nUNIFI_API_KEY=sekrit-api-value\n' \
  "$UNIFI" >"$TMP/platform.env"
printf 'kind: Secret\nstringData:\n  K: %s\n' "$FILEVAL" >"$TMP/secrets/bifrost-dev-secrets.yaml"
printf 'example: true\n' >"$TMP/secrets/bifrost-dev-secrets.example.yaml"
export BIFROST_INFRA_ENV="$TMP/infra.env"
export BIFROST_PLATFORM_ENV="$TMP/platform.env"
GWPASS="sekrit-gateway-value"
printf 'REDIS_IB_PLATFORM_PASS=keep-me\nREDIS_IB_GATEWAY_PASS=%s\nREDIS_IB_TRADE_PROD_PASS=sekrit-trade-prod\n' "$GWPASS" >"$TMP/plugin.env"
export BIFROST_PLUGIN_ENV="$TMP/plugin.env"
export BIFROST_SECRETS_SRC="$TMP/secrets"
export BIFROST_OWNER_DIR="$TMP/owner"
export BIFROST_WORKSPACE="$TMP/workspace"

run() {
  "$SCRIPT" "$@" >"$TMP/out" 2>"$TMP/err"
}

forbid() {
  if grep -q -e "$ADMIN" -e "$REDIS" -e "$PREV" -e "$NEXT" -e "$UNIFI" -e "$FILEVAL" -e "sekrit-api-value" -e "$GWPASS" -e "sekrit-trade-prod" "$TMP/out" "$TMP/err"; then
    echo "FAIL output contained a value" >&2
    exit 1
  fi
}

run
forbid
grep -q '^KEEP=stay$' "$TMP/infra.env"
if grep -q '^OPS_ADMIN_TOKEN=' "$TMP/infra.env"; then
  echo "FAIL infra env still has OPS_ADMIN_TOKEN" >&2
  exit 1
fi
if ! grep -q '^OPS_ADMIN_TOKEN=' "$TMP/owner/owner.env"; then
  echo "FAIL owner.env missing OPS_ADMIN_TOKEN" >&2
  exit 1
fi
if grep -q -e '^REDIS_IB_GATEWAY_PASS=' -e '^REDIS_IB_TRADE_PROD_PASS=' "$TMP/plugin.env"; then
  echo "FAIL plugin env still has a redis-ib write user" >&2
  exit 1
fi
if ! grep -q '^REDIS_IB_PLATFORM_PASS=' "$TMP/plugin.env"; then
  echo "FAIL plugin env lost REDIS_IB_PLATFORM_PASS (it must stay)" >&2
  exit 1
fi
if grep -q '^UNIFI_PASS=' "$TMP/platform.env"; then
  echo "FAIL platform env still has UNIFI_PASS" >&2
  exit 1
fi
if [ ! -f "$TMP/owner/secrets/bifrost-dev-secrets.yaml" ]; then
  echo "FAIL secret file was not moved" >&2
  exit 1
fi
if [ ! -f "$TMP/secrets/bifrost-dev-secrets.example.yaml" ]; then
  echo "FAIL example file was moved" >&2
  exit 1
fi
mode_dir="$(stat -f '%OLp' "$TMP/owner")"
mode_env="$(stat -f '%OLp' "$TMP/owner/owner.env")"
if [ "$mode_dir" != "700" ] || [ "$mode_env" != "600" ]; then
  echo "FAIL modes dir=$mode_dir env=$mode_env" >&2
  exit 1
fi

run
forbid

"$SCRIPT" --undo >"$TMP/out" 2>"$TMP/err"
forbid
grep -q '^OPS_ADMIN_TOKEN=' "$TMP/infra.env"
grep -q '^UNIFI_PASS=' "$TMP/platform.env"
grep -q '^REDIS_IB_GATEWAY_PASS=' "$TMP/plugin.env"
if [ ! -f "$TMP/secrets/bifrost-dev-secrets.yaml" ]; then
  echo "FAIL undo did not restore the secret file" >&2
  exit 1
fi
if [ -f "$TMP/owner/secrets/bifrost-dev-secrets.yaml" ]; then
  echo "FAIL undo left the secret file in the owner dir" >&2
  exit 1
fi

"$SCRIPT" --undo >"$TMP/out" 2>"$TMP/err"
forbid
echo "ok: move, repeat, undo, and undo again keep values out of the output"
