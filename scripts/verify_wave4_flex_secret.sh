#!/usr/bin/env bash
# Wave 4 Item A + Husbandry closed-loop: Flex tokens Secret in plugin-flex-query.
#
# Checks:
#   1. Secret bifrost-flex-tokens exists in NS plugin-flex-query
#   2. Keys FLEX_HOST_TOKEN / FLEX_SECONDARY_TOKEN present and NON-EMPTY
#   3. flex-query-api pod has non-empty FLEX_HOST_TOKEN (or secondary)
#   4. GET /flex/config/summary reports source=secret
#
# Empty Secret / source=none → FAIL (no longer WARN-pass).
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
    raw="$(kubectl -n "$NS" get secret bifrost-flex-tokens -o jsonpath="{.data.$k}" 2>/dev/null || true)"
    if [[ -z "$raw" ]]; then
      echo "FAIL: secret key $k missing"
      FAIL=1
      continue
    fi
    val="$(printf '%s' "$raw" | base64 -d 2>/dev/null || true)"
    if [[ -z "${val// }" ]]; then
      echo "FAIL: secret key $k is empty (run: make sync-flex-tokens with non-empty IB_FLEX_*_TOKEN)"
      FAIL=1
    else
      echo "OK: secret key $k non-empty (len=${#val})"
    fi
  done
fi

POD="$(kubectl -n "$NS" get pods -l app.kubernetes.io/name=flex-query-api \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -z "$POD" ]]; then
  echo "FAIL: flex-query-api pod not found"
  FAIL=1
else
  HOST_LEN="$(kubectl -n "$NS" exec "$POD" -- sh -c 'printf %s "${FLEX_HOST_TOKEN:-}" | wc -c' 2>/dev/null | tr -d ' ' || echo 0)"
  SEC_LEN="$(kubectl -n "$NS" exec "$POD" -- sh -c 'printf %s "${FLEX_SECONDARY_TOKEN:-}" | wc -c' 2>/dev/null | tr -d ' ' || echo 0)"
  if [[ "${HOST_LEN:-0}" -gt 0 || "${SEC_LEN:-0}" -gt 0 ]]; then
    echo "OK: pod has non-empty Flex token env (host_len=$HOST_LEN sec_len=$SEC_LEN)"
  else
    echo "FAIL: pod Flex token env empty — Secret missing/optional or rollout pending"
    FAIL=1
  fi

  SUMMARY=""
  if SUMMARY="$(kubectl -n "$NS" exec "$POD" -- \
      python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8791/flex/config/summary', timeout=5).read().decode())" 2>/dev/null)"; then
    if echo "$SUMMARY" | grep -q '"source"[[:space:]]*:[[:space:]]*"secret"'; then
      echo "OK: /flex/config/summary source=secret"
    elif echo "$SUMMARY" | grep -q '"source"[[:space:]]*:[[:space:]]*"none"'; then
      echo "FAIL: /flex/config/summary source=none (enqueue fail-closed)"
      FAIL=1
    elif echo "$SUMMARY" | grep -q '"source"[[:space:]]*:[[:space:]]*"db"'; then
      echo "FAIL: source=db is retired (Wave 11) — sync K8s Secret"
      FAIL=1
    else
      echo "FAIL: summary missing usable source=secret"
      FAIL=1
    fi
  else
    echo "FAIL: could not fetch /flex/config/summary from api pod"
    FAIL=1
  fi
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "RESULT: FAIL"
  exit 1
fi
echo "RESULT: PASS"
exit 0
