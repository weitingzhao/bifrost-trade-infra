#!/usr/bin/env bash
# Apply the cluster platform-api role tokens (viewer / operator / admin) from
# bifrost-trade-infra/.env into Kubernetes Secrets:
#
#   bifrost-platform-stg/bifrost-platform-role-tokens   PLATFORM_{VIEWER,OPERATOR,ADMIN}_TOKEN
#   bifrost-platform-prod/bifrost-platform-role-tokens  PLATFORM_PROD_{VIEWER,OPERATOR,ADMIN}_TOKEN
#   monitoring/alertmanager-webhook-auth                token (= PROD reporter)
#
# .env keys: PLATFORM_STG_{VIEWER,OPERATOR,ADMIN}_TOKEN, PLATFORM_PROD_{VIEWER,OPERATOR,ADMIN}_TOKEN.
# REMEDIATION_RUNNER_TOKEN was retired with the Mac mini runner (LANE-W33). Do not
# write that key into bifrost-platform-role-tokens.
# The overlay platform-auth.yaml carries no inline values, so a missing key here
# means that role cannot sign in — not that it falls back to a public default.
# Values go through a mode-600 temp file, never argv.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-${ROOT}/.env}"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "missing ${ENV_FILE}" >&2
  exit 1
fi

env_value() {
  local key="$1" line
  line="$(grep -E "^${key}=" "${ENV_FILE}" | tail -1 || true)"
  line="${line#*=}"
  line="${line%\"}"
  line="${line#\"}"
  if [[ -z "${line}" ]]; then
    echo "missing ${key} in ${ENV_FILE}" >&2
    exit 1
  fi
  printf '%s' "${line}"
}

for envname in STG PROD; do
  for role in VIEWER OPERATOR ADMIN; do
    env_value "PLATFORM_${envname}_${role}_TOKEN" >/dev/null
  done
done

TMP="$(mktemp)"
chmod 600 "${TMP}"
trap 'rm -f "${TMP}"' EXIT

apply_secret() {
  local ns="$1" name="$2" label="$3"
  kubectl -n "${ns}" create secret generic "${name}" --from-env-file="${TMP}" \
    --dry-run=client -o yaml \
    | kubectl label --local -f - "${label}" -o yaml \
    | kubectl apply -f -
}

# The audit webhook only writes diagnostics. It accepts reporter or above, so
# Alertmanager must not hold the operator token (LANE-B4).
# Prefer PLATFORM_PROD_REPORTER_TOKEN in this .env. When that key is absent,
# copy the key PROD platform-api already mounts (secret bifrost-platform-reporter-token).
# The value is written to a mode-600 file and never echoed.
webhook_token() {
  if grep -qE "^PLATFORM_PROD_REPORTER_TOKEN=." "${ENV_FILE}"; then
    env_value PLATFORM_PROD_REPORTER_TOKEN
    return
  fi
  local b64
  b64="$(kubectl -n bifrost-platform-prod get secret bifrost-platform-reporter-token \
    -o "jsonpath={.data.PLATFORM_PROD_REPORTER_TOKEN}")"
  if [[ -z "${b64}" ]]; then
    echo "missing PLATFORM_PROD_REPORTER_TOKEN in ${ENV_FILE} and in secret bifrost-platform-prod/bifrost-platform-reporter-token" >&2
    exit 1
  fi
  printf '%s' "${b64}" | base64 -d
}

write_webhook_auth() {
  printf 'token=%s\n' "$(webhook_token)" > "${TMP}"
  apply_secret monitoring alertmanager-webhook-auth app.kubernetes.io/component=alertmanager
}

# WEBHOOK_ONLY=1 updates monitoring/alertmanager-webhook-auth and leaves the
# role-token Secrets alone. The full run below still writes that same bearer.
if [[ "${WEBHOOK_ONLY:-}" == "1" ]]; then
  write_webhook_auth
  echo "alertmanager-webhook-auth set to the PROD reporter token."
  exit 0
fi

for role in VIEWER OPERATOR ADMIN; do
  printf 'PLATFORM_%s_TOKEN=%s\n' "${role}" "$(env_value "PLATFORM_STG_${role}_TOKEN")"
done > "${TMP}"
apply_secret bifrost-platform-stg bifrost-platform-role-tokens app.kubernetes.io/part-of=bifrost-platform

for role in VIEWER OPERATOR ADMIN; do
  printf 'PLATFORM_PROD_%s_TOKEN=%s\n' "${role}" "$(env_value "PLATFORM_PROD_${role}_TOKEN")"
done > "${TMP}"
apply_secret bifrost-platform-prod bifrost-platform-role-tokens app.kubernetes.io/part-of=bifrost-platform

# PROD platform-api authenticates this route at reporter or above
# (PLATFORM_PROD_REPORTER_TOKEN). The operator token would still be accepted,
# and that is the credential this webhook must stop holding.
write_webhook_auth

echo "Platform role tokens applied. platform-api picks them up on its next rollout."
