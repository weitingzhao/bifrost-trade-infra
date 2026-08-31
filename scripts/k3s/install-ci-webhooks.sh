#!/usr/bin/env bash
# Point Gitea push webhooks at the CI EventListener.
#
# Without this the CI layer is installed but inert: pipelines exist, triggers
# resolve, and nothing ever fires. Installed-but-not-wired is the failure mode
# the code-health ratchet exists to catch, so it should not be left as a manual
# step nobody remembers.
#
# Idempotent: an existing webhook with the same URL is updated, not duplicated.
#
# Usage:
#   KUBECONFIG=~/.kube/bifrost-k3s.yaml ./scripts/k3s/install-ci-webhooks.sh
#   make k3s-install-ci-webhooks
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"
GITEA_ORG="${GITEA_ORG:-bifrost}"
GITEA_LOCAL_PORT="${GITEA_LOCAL_PORT:-3999}"
EL_URL="${EL_URL:-http://el-bifrost-ci.cicd.svc.cluster.local:8080}"

# Only repos an EventListener CEL filter actually routes. Adding a webhook for a
# repo no trigger matches would produce silent no-op deliveries that look wired.
REPOS="${REPOS:-bifrost-trade-core bifrost-trade-api bifrost-trade-worker bifrost-trade-socket bifrost-trade-frontend bifrost-ui bifrost-platform}"

export KUBECONFIG

GITEA_ADMIN_TOKEN="${GITEA_ADMIN_TOKEN:-}"
if [[ -z "${GITEA_ADMIN_TOKEN}" ]]; then
  GITEA_ADMIN_TOKEN="$(kubectl get secret gitea-bootstrap -n "${CICD_NAMESPACE}" \
    -o jsonpath='{.data.gitea_admin_token}' 2>/dev/null | base64 -d 2>/dev/null || true)"
fi
if [[ -z "${GITEA_ADMIN_TOKEN}" ]]; then
  echo "Set GITEA_ADMIN_TOKEN or apply secret gitea-bootstrap" >&2
  exit 1
fi

kubectl -n "${CICD_NAMESPACE}" port-forward svc/gitea "${GITEA_LOCAL_PORT}:3000" >/dev/null 2>&1 &
PF_PID=$!
trap 'kill "${PF_PID}" 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:${GITEA_LOCAL_PORT}/api/v1/version" >/dev/null 2>&1 && break
  sleep 1
done

API="http://127.0.0.1:${GITEA_LOCAL_PORT}/api/v1"
AUTH=(-H "Authorization: token ${GITEA_ADMIN_TOKEN}" -H "Content-Type: application/json")

payload="$(printf '{"type":"gitea","active":true,"events":["push"],"config":{"url":"%s","content_type":"json","http_method":"post"}}' "${EL_URL}")"

fail=0
for repo in ${REPOS}; do
  hooks="$(curl -sf "${AUTH[@]}" "${API}/repos/${GITEA_ORG}/${repo}/hooks" || echo '[]')"
  existing="$(printf '%s' "${hooks}" | python3 -c "
import sys, json
url = sys.argv[1]
try:
    for h in json.load(sys.stdin):
        if h.get('config', {}).get('url') == url:
            print(h['id']); break
except Exception:
    pass
" "${EL_URL}" 2>/dev/null || true)"

  if [[ -n "${existing}" ]]; then
    if curl -sf -X PATCH "${AUTH[@]}" -d "${payload}" \
        "${API}/repos/${GITEA_ORG}/${repo}/hooks/${existing}" >/dev/null; then
      echo "  ${repo}: webhook updated (id ${existing})"
    else
      echo "  ${repo}: FAILED to update webhook" >&2; fail=1
    fi
  else
    if curl -sf -X POST "${AUTH[@]}" -d "${payload}" \
        "${API}/repos/${GITEA_ORG}/${repo}/hooks" >/dev/null; then
      echo "  ${repo}: webhook created"
    else
      echo "  ${repo}: FAILED to create webhook" >&2; fail=1
    fi
  fi
done

if [[ "${fail}" -ne 0 ]]; then
  echo "One or more webhooks could not be configured — CI will not fire for those repos." >&2
  exit 1
fi

echo
echo "Push webhooks point at ${EL_URL}"
echo "Note: bifrost-research is deliberately absent — no CI trigger filter matches it."
