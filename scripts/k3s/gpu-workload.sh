#!/usr/bin/env bash
# Scale / status for gpu-server workloads (Step 2 — scale-to-zero).
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"
export KUBECONFIG

cmd="${1:-status}"
replicas="${2:-1}"

scale_deploy() {
  local ns="$1" name="$2" n="$3"
  kubectl scale deployment/"${name}" -n "${ns}" --replicas="${n}"
  echo "OK ${ns}/${name} -> replicas=${n}"
}

case "${cmd}" in
  status)
    echo "== gpu-server node =="
    kubectl get node gpu-server -o wide 2>/dev/null || echo "gpu-server not found"
    echo ""
    echo "== compute workloads =="
    kubectl get deploy,pvc -n ai 2>/dev/null || true
    kubectl get deploy,pvc -n data-warehouse 2>/dev/null || true
    echo ""
    echo "== pods on gpu-server =="
    kubectl get pods -A --field-selector spec.nodeName=gpu-server -o wide 2>/dev/null || true
    ;;
  ollama-up)   scale_deploy ai ollama "${replicas}" ;;
  ollama-down) scale_deploy ai ollama 0 ;;
  warehouse-up)   scale_deploy data-warehouse minio "${replicas}" ;;
  warehouse-down) scale_deploy data-warehouse minio 0 ;;
  all-up)
    scale_deploy ai ollama "${replicas}"
    scale_deploy data-warehouse minio "${replicas}"
    ;;
  all-down)
    scale_deploy ai ollama 0
    scale_deploy data-warehouse minio 0
    ;;
  *)
    echo "Usage: $0 {status|ollama-up|ollama-down|warehouse-up|warehouse-down|all-up|all-down} [replicas]" >&2
    exit 1
    ;;
esac
