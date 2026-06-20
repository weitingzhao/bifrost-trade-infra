#!/usr/bin/env bash
# Verify NAS-backed NFS StorageClasses and a Bound test PVC.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

NFS_SERVER="${NFS_SERVER:-192.168.10.20}"

kubectl get storageclass nfs-hot nfs-cold
kubectl -n kube-system get deploy,pods -l app=nfs-subdir-external-provisioner

kubectl apply -f - <<'EOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: verify-nfs-hot
  namespace: default
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: nfs-hot
  resources:
    requests:
      storage: 1Gi
EOF

kubectl wait --for=jsonpath='{.status.phase}'=Bound pvc/verify-nfs-hot --timeout=60s
kubectl get pvc verify-nfs-hot
kubectl delete pvc verify-nfs-hot --wait=false

echo "NFS verify OK (server ${NFS_SERVER})"
