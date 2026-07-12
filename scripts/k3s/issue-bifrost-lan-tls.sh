#!/usr/bin/env bash
# Issue mkcert leaf for Bifrost LAN Hosts and install as Traefik default TLS.
#
# Requires: mkcert, kubectl (cluster admin)
# Usage:
#   ./scripts/k3s/issue-bifrost-lan-tls.sh
#   ./scripts/k3s/issue-bifrost-lan-tls.sh --skip-install-ca   # do not mkcert -install on this Mac
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TLS_DIR="${ROOT}/k8s/system/tls"
SECRET_NS=kube-system
SECRET_NAME=bifrost-lan-tls
SKIP_INSTALL_CA=0

for arg in "$@"; do
  case "$arg" in
    --skip-install-ca) SKIP_INSTALL_CA=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
  esac
done

if ! command -v mkcert >/dev/null 2>&1; then
  echo "mkcert not found — brew install mkcert nss" >&2
  exit 1
fi
if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl not found" >&2
  exit 1
fi

mkdir -p "${TLS_DIR}"
cd "${TLS_DIR}"

if [[ "${SKIP_INSTALL_CA}" -eq 0 ]]; then
  echo "==> Installing local mkcert CA into this machine's trust store"
  mkcert -install
fi

CAROOT="$(mkcert -CAROOT)"
echo "==> CA root: ${CAROOT}"
cp -f "${CAROOT}/rootCA.pem" "${TLS_DIR}/bifrost-lan-rootCA.pem"
echo "    exported ${TLS_DIR}/bifrost-lan-rootCA.pem (safe to commit; install on client devices)"

echo "==> Minting leaf certificate (SANs for trader/ops Hosts + VIP)"
mkcert \
  -cert-file bifrost-lan.pem \
  -key-file bifrost-lan-key.pem \
  "*.bifrost.lan" \
  "*.trader.bifrost.lan" \
  "*.ops.bifrost.lan" \
  "trader.bifrost.lan" \
  "ops.bifrost.lan" \
  "stg.trader.bifrost.lan" \
  "dev.trader.bifrost.lan" \
  "stg.ops.bifrost.lan" \
  "192.168.10.100" \
  "192.168.10.70" \
  "192.168.10.73"

echo "==> Creating/updating Secret ${SECRET_NS}/${SECRET_NAME}"
kubectl -n "${SECRET_NS}" create secret tls "${SECRET_NAME}" \
  --cert=bifrost-lan.pem \
  --key=bifrost-lan-key.pem \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> Applying TLSStore default"
kubectl apply -f "${ROOT}/k8s/system/traefik-tlsstore.yaml"

echo "==> Done. Clients need the root CA once:"
echo "    Mac:  open ${TLS_DIR}/bifrost-lan-rootCA.pem → Keychain → Always Trust"
echo "    Win:  certutil -addstore -f Root ${TLS_DIR}/bifrost-lan-rootCA.pem"
echo "    Smoke: curl -v https://stg.trader.bifrost.lan/api/monitor/status"
