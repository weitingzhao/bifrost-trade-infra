#!/usr/bin/env bash
# Stub curl. Does not call the cluster and does not run a real command.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${ROOT}/owner-run.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export HOME="${TMP}/home"
export PLATFORM_PROD_VIEWER_TOKEN="viewer-token"
export PLATFORM_API="http://platform.test"
export OWNER_KUBECONFIG="${TMP}/kubeconfig"
export OWNER_RUN_MAX_AGE_SECONDS=86400
touch "$OWNER_KUBECONFIG"
mkdir -p "${HOME}/bin"
cat > "${HOME}/bin/curl" <<'EOF'
#!/bin/sh
# The last argument is the URL. The body is $CURL_BODY.
printf '%s' "${CURL_BODY}"
EOF
chmod +x "${HOME}/bin/curl" "$SCRIPT"
export PATH="${HOME}/bin:${PATH}"

fail_if_runs() {
  local name="$1"
  if "$SCRIPT" "$name" </dev/null >"${TMP}/out" 2>"${TMP}/err"; then
    echo "FAIL ${name} was accepted" >&2
    cat "${TMP}/err" >&2
    exit 1
  fi
}

export CURL_BODY='{"action":"rolling_reboot","status":"executed","decided_at":"2026-10-09T00:00:00Z","params":{"command":"true"},"result":{"command_sha256":"b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b"}}'
fail_if_runs wrong-action
grep -q "want owner_run_command executed" "${TMP}/err"

export CURL_BODY='{"action":"owner_run_command","status":"pending","decided_at":"2026-10-09T00:00:00Z","params":{"command":"true"},"result":{"command_sha256":"x"}}'
fail_if_runs wrong-status
grep -q "status=pending" "${TMP}/err"

export CURL_BODY='{"action":"owner_run_command","status":"executed","decided_at":"2020-01-01T00:00:00Z","params":{"command":"true"},"result":{"command_sha256":"b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b"}}'
fail_if_runs expired
grep -q "older than" "${TMP}/err"

export CURL_BODY='{"action":"owner_run_command","status":"executed","decided_at":"2099-01-01T00:00:00Z","params":{"command":"true"},"result":{"command_sha256":"deadbeef"}}'
fail_if_runs bad-hash
grep -q "hash does not match" "${TMP}/err"

export CURL_BODY='{"action":"owner_run_command","status":"executed","decided_at":"2099-01-01T00:00:00Z","params":{"command":"true"},"result":{"command_sha256":"b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b"}}'
if printf 'yes\n' | "$SCRIPT" piped >"${TMP}/out" 2>"${TMP}/err"; then
  echo "FAIL piped yes was accepted" >&2
  exit 1
fi
grep -q "standard input must be a terminal" "${TMP}/err"

echo "ok: owner-run refuses wrong status, expired approvals, a hash mismatch, and a piped yes"
