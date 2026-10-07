#!/usr/bin/env bash
# After a research Secret changes, restart every Deployment that mounts it.
#
# The list is derived the same way as holder_deployments() in
# bifrost-password-rotate.sh: any Deployment whose pod spec names the Secret.
# A checksum annotation on the pod template rolls the pod. The checksum is a
# digest of the Secret's data map; the values are not printed.
#
#   scripts/research-secret-restart.sh
#   scripts/research-secret-restart.sh --dry-run
#   scripts/research-secret-restart.sh --namespace research --secret bifrost-research-secrets
#
# CronJobs read the Secret on their next run; this restarts Deployments only.
set -euo pipefail

NS="${RESEARCH_NS:-research}"
SECRET="${RESEARCH_SECRET_NAME:-bifrost-research-secrets}"
DRY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY=1; shift ;;
    --namespace) NS="${2:?}"; shift 2 ;;
    --secret) SECRET="${2:?}"; shift 2 ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")" && pwd)"
export KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"

deploys="$(kubectl get deploy -A -o json | python3 -c '
import json, sys
sys.path.insert(0, sys.argv[1])
import research_secret_holders as holders
doc = json.load(sys.stdin)
ns, secret = sys.argv[2], sys.argv[3]
for item_ns, name in holders.deployments_mounting(doc["items"], secret):
    if item_ns == ns:
        print(item_ns, name)
' "${ROOT}" "${NS}" "${SECRET}")"

if [[ -z "${deploys}" ]]; then
  echo "no Deployment in ${NS} mounts ${SECRET}"
  exit 0
fi

sum="$(kubectl -n "${NS}" get secret "${SECRET}" -o json | python3 -c '
import json, sys
sys.path.insert(0, sys.argv[1])
import research_secret_holders as holders
doc = json.load(sys.stdin)
print(holders.secret_checksum(doc.get("data") or {}))
' "${ROOT}")"

echo "Deployments in ${NS} mounting ${SECRET} (checksum ${sum}):"
while read -r item_ns name; do
  [[ -n "${name}" ]] || continue
  echo "  ${item_ns}/${name}"
  if [[ "${DRY}" -eq 1 ]]; then
    continue
  fi
  kubectl -n "${item_ns}" patch deploy "${name}" --type=merge -p \
    "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"bifrost.io/secret-checksum\":\"${sum}\"}}}}}"
done <<<"${deploys}"

if [[ "${DRY}" -eq 1 ]]; then
  echo "dry-run: no annotation written"
fi
