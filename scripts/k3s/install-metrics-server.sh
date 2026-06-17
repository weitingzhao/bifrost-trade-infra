#!/usr/bin/env bash
# Install metrics-server on K3s (Layer A). Idempotent — safe to re-run.
# Used by platform-api POST /cluster/addons/metrics-server/ensure (local KUBECONFIG)
# or: make k3s-install-metrics-remote
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

METRICS_MANIFEST="${METRICS_MANIFEST:-https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl not found in PATH" >&2
  exit 1
fi

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

echo "==> metrics-server (Layer A) using KUBECONFIG=${KUBECONFIG}"

if kubectl get deployment metrics-server -n kube-system >/dev/null 2>&1; then
  echo "    deployment metrics-server already exists"
else
  echo "    applying ${METRICS_MANIFEST}"
  kubectl apply -f "${METRICS_MANIFEST}"
fi

# K3s dev clusters often need insecure kubelet TLS (see standardsCatalog.ts observability / metrics-server notes).
if ! kubectl get deployment metrics-server -n kube-system -o jsonpath='{.spec.template.spec.containers[0].args}' \
  | grep -q 'kubelet-insecure-tls'; then
  echo "    patching metrics-server for K3s (--kubelet-insecure-tls)"
  kubectl patch deployment metrics-server -n kube-system --type='json' \
    -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]' \
    || kubectl patch deployment metrics-server -n kube-system --type='json' \
    -p='[{"op":"replace","path":"/spec/template/spec/containers/0/args","value":["--kubelet-insecure-tls","--kubelet-preferred-address-types=InternalIP,ExternalIP,Hostname"]}]'
fi

echo "==> waiting for metrics-server rollout"
kubectl rollout status deployment/metrics-server -n kube-system --timeout=180s

echo "metrics-server ready"
