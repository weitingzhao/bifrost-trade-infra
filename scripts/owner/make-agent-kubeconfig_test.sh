#!/usr/bin/env bash
# Fake kubectl. Does not call the cluster. The token must not appear on stdout.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${ROOT}/make-agent-kubeconfig.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
TOKEN="agent-token-value"
mkdir -p "$TMP/bin" "$TMP/admin"
printf 'apiVersion: v1\nkind: Config\n' >"$TMP/admin/admin.yaml"
cat >"$TMP/bin/kubectl" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >>"${STUB_LOG}"
case "$*" in
  *jsonpath*)
    printf '%s' "https://example.test:6443"
    ;;
  *get\ secret\ bifrost-agent-token*)
    python3 - <<'PY'
import base64, json
print(json.dumps({"data": {
    "token": base64.b64encode(b"agent-token-value").decode(),
    "ca.crt": base64.b64encode(b"ca-bytes").decode(),
}}))
PY
    ;;
  *)
    echo "unexpected kubectl $*" >&2
    exit 1
    ;;
esac
EOF
chmod +x "$TMP/bin/kubectl" "$SCRIPT"
export PATH="$TMP/bin:$PATH"
export STUB_LOG="$TMP/kubectl.log"
out="$TMP/agent.yaml"
if ! "$SCRIPT" "$out" "$TMP/admin/admin.yaml" >"$TMP/stdout" 2>"$TMP/stderr"; then
  echo "FAIL script exited non-zero" >&2
  cat "$TMP/stderr" >&2
  exit 1
fi
mode="$(stat -f '%OLp' "$out")"
if [ "$mode" != "600" ]; then
  echo "FAIL mode is $mode" >&2
  exit 1
fi
if ! grep -q "$TOKEN" "$out"; then
  echo "FAIL kubeconfig has no token" >&2
  exit 1
fi
if grep -q "$TOKEN" "$TMP/stdout" "$TMP/stderr" "$STUB_LOG"; then
  echo "FAIL token appeared on stdout, stderr, or the kubectl command line" >&2
  exit 1
fi
if grep -q "https://example.test:6443" "$out"; then
  :
else
  echo "FAIL server was not copied" >&2
  exit 1
fi
if "$SCRIPT" "$TMP/missing.yaml" "$TMP/no-such-admin" >"$TMP/stdout2" 2>"$TMP/stderr2"; then
  echo "FAIL missing admin kubeconfig was accepted" >&2
  exit 1
fi
echo "ok: agent kubeconfig is mode 600 and the token stays off stdout"
