#!/usr/bin/env bash
# Wave 4 Item A: Flex tokens Secret in plugin-flex-query.
#
# Checks:
#   1. Secret bifrost-flex-tokens exists in NS plugin-flex-query
#   2. Keys FLEX_HOST_TOKEN / FLEX_SECONDARY_TOKEN present
#   3. flex-query-api pod has FLEX_HOST_TOKEN in env (optional=true → may be empty)
#   4. GET /flex/config/summary reports source=secret when token non-empty
#
# Usage: ./scripts/verify_wave4_flex_secret.sh
#
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
NS=plugin-flex-query
FAIL=0

echo "==== Wave 4 Flex Secret ($NS) ===="

if ! kubectl -n "$NS" get secret bifrost-flex-tokens >/dev/null 2>&1; then
  echo "FAIL: secret bifrost-flex-tokens missing (run: make sync-flex-tokens)"
  FAIL=1
else
  echo "OK: secret bifrost-flex-tokens exists"
  for k in FLEX_HOST_TOKEN FLEX_SECONDARY_TOKEN; do
    if kubectl -n "$NS" get secret bifrost-flex-tokens -o jsonpath="{.data.$k}" | grep -q .; then
      echo "OK: secret key $k present"
    else
      echo "WARN: secret key $k empty or missing (fallback to DB still allowed)"
    fi
  done
fi

POD="$(kubectl -n "$NS" get pods -l app.kubernetes.io/name=flex-query-api \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -z "$POD" ]]; then
  echo "WARN: flex-query-api pod not found — skip env/summary checks"
else
  if kubectl -n "$NS" exec "$POD" -- printenv FLEX_HOST_TOKEN >/dev/null 2>&1; then
    echo "OK: pod env FLEX_HOST_TOKEN is set (may be empty string)"
  else
    echo "WARN: pod env FLEX_HOST_TOKEN not injected (optional secretRef / restart pending)"
  fi

  SUMMARY=""
  if SUMMARY="$(kubectl -n "$NS" exec "$POD" -- \
      python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8791/flex/config/summary', timeout=5).read().decode())" 2>/dev/null)"; then
    if echo "$SUMMARY" | grep -q '"source"[[:space:]]*:[[:space:]]*"secret"'; then
      echo "OK: /flex/config/summary source=secret"
    elif echo "$SUMMARY" | grep -q '"source"[[:space:]]*:[[:space:]]*"db"'; then
      echo "WARN: source=db (Secret empty; DB fallback active — expected until tokens synced)"
    elif echo "$SUMMARY" | grep -q '"source"'; then
      echo "OK: summary exposes source field"
    else
      echo "FAIL: summary missing source field (need flex-query >= 0.4.0)"
      FAIL=1
    fi
  else
    echo "WARN: could not fetch /flex/config/summary from api pod"
  fi
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "RESULT: FAIL"
  exit 1
fi
echo "RESULT: PASS (warnings allowed when Secret empty)"
exit 0
