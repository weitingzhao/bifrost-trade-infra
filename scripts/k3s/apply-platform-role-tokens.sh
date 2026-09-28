#!/usr/bin/env bash
# Apply the cluster platform-api role tokens (viewer / operator / admin) from
# bifrost-trade-infra/.env into Kubernetes Secrets:
#
#   bifrost-platform-stg/bifrost-platform-role-tokens   PLATFORM_{VIEWER,OPERATOR,ADMIN}_TOKEN
#   bifrost-platform-prod/bifrost-platform-role-tokens  PLATFORM_PROD_{VIEWER,OPERATOR,ADMIN}_TOKEN
#   monitoring/alertmanager-webhook-auth                token (= STG operator)
#
# .env keys: PLATFORM_STG_{VIEWER,OPERATOR,ADMIN}_TOKEN, PLATFORM_PROD_{VIEWER,OPERATOR,ADMIN}_TOKEN.
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

for role in VIEWER OPERATOR ADMIN; do
  printf 'PLATFORM_%s_TOKEN=%s\n' "${role}" "$(env_value "PLATFORM_STG_${role}_TOKEN")"
done > "${TMP}"
apply_secret bifrost-platform-stg bifrost-platform-role-tokens app.kubernetes.io/part-of=bifrost-platform

for role in VIEWER OPERATOR ADMIN; do
  printf 'PLATFORM_PROD_%s_TOKEN=%s\n' "${role}" "$(env_value "PLATFORM_PROD_${role}_TOKEN")"
done > "${TMP}"
apply_secret bifrost-platform-prod bifrost-platform-role-tokens app.kubernetes.io/part-of=bifrost-platform

printf 'token=%s\n' "$(env_value PLATFORM_STG_OPERATOR_TOKEN)" > "${TMP}"
apply_secret monitoring alertmanager-webhook-auth app.kubernetes.io/component=alertmanager

echo "Platform role tokens applied. platform-api picks them up on its next rollout."
