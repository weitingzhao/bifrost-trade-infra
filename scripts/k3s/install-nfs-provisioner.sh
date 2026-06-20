#!/usr/bin/env bash
# Install nfs-subdir-external-provisioner StorageClasses for UGREEN NAS (nfs-hot / nfs-cold).
# Idempotent — safe to re-run (helm upgrade --install).
#
# Prerequisites:
#   - NAS NFS exports: ${NFS_SERVER}:${NFS_HOT_PATH}, ${NFS_COLD_PATH}
#   - nfs-common on all K3s nodes: ./install-nfs-common-nodes.sh
#   - helm + kubectl on this machine; KUBECONFIG pointing at bifrost-bootstrap
#
# Usage:
#   KUBECONFIG=~/.kube/bifrost-k3s.yaml ./scripts/k3s/install-nfs-provisioner.sh
#   make k3s-install-nfs-provisioner
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

NFS_SERVER="${NFS_SERVER:-192.168.10.20}"
NFS_HOT_PATH="${NFS_HOT_PATH:-/volume1/k3s-hot}"
NFS_COLD_PATH="${NFS_COLD_PATH:-/volume1/k3s-cold}"
NFS_CHART_REPO="${NFS_CHART_REPO:-https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/}"
NFS_CHART="${NFS_CHART:-nfs-subdir-external-provisioner/nfs-subdir-external-provisioner}"
NFS_NAMESPACE="${NFS_NAMESPACE:-kube-system}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl not found in PATH" >&2
  exit 1
fi

if ! command -v helm >/dev/null 2>&1; then
  echo "helm not found — install: brew install helm" >&2
  exit 1
fi

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  echo "Run: make k3s-fetch-kubeconfig" >&2
  exit 1
fi

if ! kubectl cluster-info >/dev/null 2>&1; then
  echo "Cannot reach cluster via ${KUBECONFIG}" >&2
  exit 1
fi

preflight_node="${K3S_NFS_PREFLIGHT_NODE:-vision@192.168.10.73}"
if ssh -o BatchMode=yes -o ConnectTimeout=5 "${preflight_node}" \
  "dpkg -s nfs-common >/dev/null 2>&1"; then
  echo "==> preflight: nfs-common present on ${preflight_node}"
else
  echo "ERROR: nfs-common not installed on ${preflight_node}" >&2
  echo "Run interactively (sudo password once per node):" >&2
  echo "  make k3s-install-nfs-common-nodes" >&2
  echo "  # or: ./scripts/k3s/install-nfs-common-nodes.sh" >&2
  exit 1
fi

echo "==> NFS provisioner (NAS ${NFS_SERVER}) KUBECONFIG=${KUBECONFIG}"
helm repo add nfs-subdir-external-provisioner "${NFS_CHART_REPO}" 2>/dev/null || true
helm repo update nfs-subdir-external-provisioner

install_release() {
  local release="$1"
  local sc_name="$2"
  local nfs_path="$3"
  local archive_on_delete="$4"

  echo "---- helm upgrade --install ${release} (storageClass=${sc_name}, path=${nfs_path})"
  helm upgrade --install "${release}" "${NFS_CHART}" \
    --namespace "${NFS_NAMESPACE}" \
    --set nfs.server="${NFS_SERVER}" \
    --set nfs.path="${nfs_path}" \
    --set storageClass.name="${sc_name}" \
    --set storageClass.defaultClass=false \
    --set storageClass.reclaimPolicy=Retain \
    --set storageClass.archiveOnDelete="${archive_on_delete}"
}

install_release nfs-provisioner-hot nfs-hot "${NFS_HOT_PATH}" false
install_release nfs-provisioner-cold nfs-cold "${NFS_COLD_PATH}" true

echo "==> Waiting for provisioner pods"
for deploy in \
  nfs-provisioner-hot-nfs-subdir-external-provisioner \
  nfs-provisioner-cold-nfs-subdir-external-provisioner; do
  if kubectl -n "${NFS_NAMESPACE}" get deployment "${deploy}" >/dev/null 2>&1; then
    kubectl -n "${NFS_NAMESPACE}" rollout status "deployment/${deploy}" --timeout=180s
  else
    echo "WARN: deployment ${deploy} not found — check helm release" >&2
  fi
done

echo "==> StorageClasses"
kubectl get storageclass

echo "==> Test PVC (nfs-hot)"
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-nfs-hot
  namespace: default
  labels:
    app.kubernetes.io/component: nfs-smoke-test
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: nfs-hot
  resources:
    requests:
      storage: 1Gi
EOF

for _ in $(seq 1 30); do
  phase="$(kubectl get pvc test-nfs-hot -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  if [[ "${phase}" == "Bound" ]]; then
    echo "test-nfs-hot Bound"
    kubectl delete pvc test-nfs-hot --wait=false
    echo "NFS provisioner ready (nfs-hot / nfs-cold on ${NFS_SERVER})"
    exit 0
  fi
  sleep 2
done

echo "ERROR: test-nfs-hot did not Bound — check provisioner logs:" >&2
kubectl -n "${NFS_NAMESPACE}" logs -l app=nfs-subdir-external-provisioner --tail=40 >&2 || true
exit 1
