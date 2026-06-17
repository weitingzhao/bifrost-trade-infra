#!/usr/bin/env bash
# Bootstrap Gitea org + GitHub pull mirrors (Session S7).
# Primary Git for CI/CD = Gitea (LAN). GitHub = upstream backup only.
#
# Prerequisites:
#   - Gitea running in cicd (make k3s-install-cicd-stack)
#   - Gitea admin API token (write:repository, read:organization)
#   - Optional GITHUB_PAT for private upstream repos
#
# Usage:
#   GITEA_ADMIN_TOKEN=... GITHUB_PAT=... ./scripts/k3s/bootstrap-gitea-mirrors.sh
#   # or apply k8s/cicd/gitea/secret.yaml first (keys gitea_admin_token, github_pat)
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"
GITEA_ORG="${GITEA_ORG:-bifrost}"
GITEA_LOCAL_PORT="${GITEA_LOCAL_PORT:-13000}"
MIRROR_REPOS="${MIRROR_REPOS:-bifrost-trade-core bifrost-trade-worker bifrost-trade-socket bifrost-trade-api bifrost-trade-frontend bifrost-trade-infra bifrost-ui}"
GITHUB_OWNER="${GITHUB_OWNER:-weitingzhao}"

export KUBECONFIG

if ! kubectl get deploy gitea -n "${CICD_NAMESPACE}" >/dev/null 2>&1; then
  echo "Gitea not found in ${CICD_NAMESPACE}. Run: make k3s-install-cicd-stack" >&2
  exit 1
fi

GITEA_ADMIN_TOKEN="${GITEA_ADMIN_TOKEN:-}"
GITHUB_PAT="${GITHUB_PAT:-}"

if [[ -z "${GITEA_ADMIN_TOKEN}" ]] && kubectl get secret gitea-bootstrap -n "${CICD_NAMESPACE}" >/dev/null 2>&1; then
  GITEA_ADMIN_TOKEN="$(kubectl get secret gitea-bootstrap -n "${CICD_NAMESPACE}" -o jsonpath='{.data.gitea_admin_token}' 2>/dev/null | base64 -d 2>/dev/null || true)"
  GITHUB_PAT="$(kubectl get secret gitea-bootstrap -n "${CICD_NAMESPACE}" -o jsonpath='{.data.github_pat}' 2>/dev/null | base64 -d 2>/dev/null || true)"
fi

if [[ -z "${GITEA_ADMIN_TOKEN}" ]]; then
  echo "Set GITEA_ADMIN_TOKEN or apply secret gitea-bootstrap (see k8s/cicd/gitea/secret.yaml.example)" >&2
  echo "Create token: Gitea UI → Settings → Applications → Generate Token" >&2
  echo "Required scopes: read:user write:user read:organization write:organization read:repository write:repository" >&2
  exit 1
fi

if [[ "${GITEA_ADMIN_TOKEN}" == *"<"* ]] || [[ ${#GITEA_ADMIN_TOKEN} -lt 32 ]]; then
  echo "gitea_admin_token looks invalid (placeholder or too short)." >&2
  echo "Edit k8s/cicd/gitea/secret.yaml → stringData.gitea_admin_token, then:" >&2
  echo "  kubectl apply -f k8s/cicd/gitea/secret.yaml -n ${CICD_NAMESPACE}" >&2
  exit 1
fi

PF_PID=""
cleanup() {
  if [[ -n "${PF_PID}" ]] && kill -0 "${PF_PID}" 2>/dev/null; then
    kill "${PF_PID}" 2>/dev/null || true
    wait "${PF_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "==> Port-forward Gitea → localhost:${GITEA_LOCAL_PORT}"
kubectl port-forward -n "${CICD_NAMESPACE}" svc/gitea "${GITEA_LOCAL_PORT}:3000" >/dev/null 2>&1 &
PF_PID=$!
sleep 2

GITEA_API="http://127.0.0.1:${GITEA_LOCAL_PORT}/api/v1"
AUTH=(-H "Authorization: token ${GITEA_ADMIN_TOKEN}" -H "Content-Type: application/json")

echo "==> Gitea version"
curl -sf "${GITEA_API}/version" | head -c 200
echo ""

echo "==> Verify admin token"
whoami="$(curl -sf "${AUTH[@]}" "${GITEA_API}/user" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("login",""))' 2>/dev/null || true)"
if [[ -z "${whoami}" ]]; then
  echo "Gitea API rejected gitea_admin_token (HTTP 401)." >&2
  echo "Regenerate token with scopes: read:user write:user read:organization write:organization read:repository write:repository" >&2
  echo "Then update secret gitea-bootstrap + gitea-git-credentials (same token)." >&2
  curl -s "${AUTH[@]}" "${GITEA_API}/user" | head -c 300 >&2 || true
  echo "" >&2
  exit 1
fi
echo "  Authenticated as ${whoami}"

echo "==> Ensure organization ${GITEA_ORG}"
if ! curl -sf "${AUTH[@]}" "${GITEA_API}/orgs/${GITEA_ORG}" >/dev/null 2>&1; then
  curl -sf "${AUTH[@]}" -X POST "${GITEA_API}/orgs" \
    -d "{\"username\":\"${GITEA_ORG}\",\"visibility\":\"private\"}" >/dev/null
  echo "  Created org ${GITEA_ORG}"
else
  echo "  Org ${GITEA_ORG} exists"
fi

GITEA_ORG_ID="$(curl -sf "${AUTH[@]}" "${GITEA_API}/orgs/${GITEA_ORG}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')"
echo "  Org ${GITEA_ORG} id=${GITEA_ORG_ID}"

gitea_http_code() {
  curl -s -o /dev/null -w "%{http_code}" "${AUTH[@]}" "$@"
}

mirror_repo() {
  local name="$1"
  local clone_addr="https://github.com/${GITHUB_OWNER}/${name}.git"
  echo "==> Mirror ${GITEA_ORG}/${name} ← ${clone_addr}"

  local code
  code="$(gitea_http_code "${GITEA_API}/repos/${GITEA_ORG}/${name}")"
  if [[ "${code}" == "200" ]]; then
    echo "  Repo exists in org — mirror-sync"
    curl -sf "${AUTH[@]}" -X POST "${GITEA_API}/repos/${GITEA_ORG}/${name}/mirror-sync" -d '{}' >/dev/null || true
    return 0
  fi

  code="$(gitea_http_code "${GITEA_API}/repos/${whoami}/${name}")"
  if [[ "${code}" == "200" ]]; then
    echo "  Repo under ${whoami}/${name} — transfer to org ${GITEA_ORG}"
    curl -sf "${AUTH[@]}" -X POST "${GITEA_API}/repos/${whoami}/${name}/transfer" \
      -d "{\"new_owner\":\"${GITEA_ORG}\"}" >/dev/null
    echo "  Transferred ${name} → ${GITEA_ORG}/${name}"
    return 0
  fi

  local payload
  if [[ -n "${GITHUB_PAT}" ]]; then
    payload="$(python3 - <<PY
import json
print(json.dumps({
  "clone_addr": "${clone_addr}",
  "repo_name": "${name}",
  "mirror": True,
  "private": True,
  "service": "git",
  "uid": ${GITEA_ORG_ID},
  "auth_token": "${GITHUB_PAT}",
}))
PY
)"
  else
    payload="$(python3 - <<PY
import json
print(json.dumps({
  "clone_addr": "${clone_addr}",
  "repo_name": "${name}",
  "mirror": True,
  "private": True,
  "service": "git",
  "uid": ${GITEA_ORG_ID},
}))
PY
)"
  fi

  local body http_code
  body="$(curl -s -w "\n%{http_code}" "${AUTH[@]}" -X POST "${GITEA_API}/repos/migrate" -d "${payload}")"
  http_code="$(echo "${body}" | tail -1)"
  body="$(echo "${body}" | sed '$d')"

  if [[ "${http_code}" == "201" || "${http_code}" == "200" ]]; then
    echo "  Migrated mirror ${name} → ${GITEA_ORG}/${name}"
    return 0
  fi

  if [[ "${http_code}" == "409" ]] && [[ "$(gitea_http_code "${GITEA_API}/repos/${whoami}/${name}")" == "200" ]]; then
    echo "  Migrate conflict — transfer ${whoami}/${name} to org"
    curl -sf "${AUTH[@]}" -X POST "${GITEA_API}/repos/${whoami}/${name}/transfer" \
      -d "{\"new_owner\":\"${GITEA_ORG}\"}" >/dev/null
    echo "  Transferred ${name} → ${GITEA_ORG}/${name}"
    return 0
  fi

  echo "Migrate failed (HTTP ${http_code}): ${body}" >&2
  return 1
}

for repo in ${MIRROR_REPOS}; do
  mirror_repo "${repo}"
done

echo ""
echo "Gitea mirrors ready (primary Git for Tekton):"
for repo in ${MIRROR_REPOS}; do
  echo "  http://gitea.cicd.svc.cluster.local:3000/${GITEA_ORG}/${repo}.git"
done
echo ""
echo "GitHub remains upstream backup — CI clones from Gitea only."
