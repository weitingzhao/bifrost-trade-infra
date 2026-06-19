#!/usr/bin/env bash
# Runs ON bootstrap (192.168.10.73) — invoked via:
#   ssh -t vision@192.168.10.73 'bash ~/bifrost-k3s/install-gpu-power-manager-remote.sh'
set -euo pipefail

# Fixed path — do not use $HOME after sudo (becomes /root).
REMOTE_DIR="/home/vision/bifrost-k3s"
ENV_FILE="${REMOTE_DIR}/gpu-node-power.env"
SCRIPT_SRC="${REMOTE_DIR}/gpu-node-power-manager.sh"

if [[ "${EUID}" -ne 0 ]]; then
  echo "==> Elevating to root (enter sudo password)..."
  exec sudo bash "$0"
fi

if [[ ! -f "${SCRIPT_SRC}" ]] || [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: missing ${SCRIPT_SRC} or ${ENV_FILE}. Run make gpu-install-power-manager from Mac first." >&2
  exit 1
fi

echo "==> Installing bifrost gpu power manager files..."
install -d /etc/bifrost
cp "${ENV_FILE}" /etc/bifrost/gpu-node-power.env
chown vision:vision /etc/bifrost/gpu-node-power.env
chmod 600 /etc/bifrost/gpu-node-power.env
cp "${SCRIPT_SRC}" /usr/local/bin/bifrost-gpu-node-power-manager.sh
chmod 755 /usr/local/bin/bifrost-gpu-node-power-manager.sh

# Ensure vision user can kubectl (service runs as vision)
VISION_HOME="/home/vision"
if [[ -f /etc/rancher/k3s/k3s.yaml ]]; then
  install -d -o vision -g vision "${VISION_HOME}/.kube"
  cp /etc/rancher/k3s/k3s.yaml "${VISION_HOME}/.kube/config"
  chown vision:vision "${VISION_HOME}/.kube/config"
  chmod 600 "${VISION_HOME}/.kube/config"
  if ! grep -q '^KUBECONFIG=' /etc/bifrost/gpu-node-power.env; then
    echo 'KUBECONFIG=/home/vision/.kube/config' >> /etc/bifrost/gpu-node-power.env
  else
    sed -i 's|^KUBECONFIG=.*|KUBECONFIG=/home/vision/.kube/config|' /etc/bifrost/gpu-node-power.env
  fi
fi

cat > /etc/systemd/system/bifrost-gpu-power-manager.service <<'UNIT'
[Unit]
Description=Bifrost gpu-server WOL + idle poweroff
After=network-online.target k3s.service
Wants=network-online.target

[Service]
Type=simple
User=vision
Group=vision
Environment=HOME=/home/vision
Environment=PATH=/usr/local/bin:/usr/bin:/bin
Environment=GPU_POWER_ENV=/etc/bifrost/gpu-node-power.env
ExecStart=/usr/local/bin/bifrost-gpu-node-power-manager.sh
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT

if ! command -v wakeonlan >/dev/null 2>&1; then
  echo "==> Installing wakeonlan..."
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y wakeonlan
fi

systemctl daemon-reload
systemctl enable bifrost-gpu-power-manager.service
systemctl restart bifrost-gpu-power-manager.service

echo ""
systemctl status bifrost-gpu-power-manager.service --no-pager || true
echo ""
echo "PASS bifrost-gpu-power-manager.service is active"
echo "Logs: journalctl -u bifrost-gpu-power-manager -f"
