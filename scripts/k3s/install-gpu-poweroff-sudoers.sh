#!/usr/bin/env bash
# Allow vision to power off gpu-server without password (Platform API + power manager).
# Run on gpu-server (192.168.10.60) as a user with sudo:
#
#   scp scripts/k3s/install-gpu-poweroff-sudoers.sh vision@192.168.10.60:/tmp/
#   ssh vision@192.168.10.60 'sudo bash /tmp/install-gpu-poweroff-sudoers.sh'
set -euo pipefail

SUDOERS_FILE="/etc/sudoers.d/vision-poweroff"
LINE='vision ALL=(ALL) NOPASSWD: /usr/bin/systemctl poweroff, /usr/bin/systemctl halt, /usr/bin/systemctl reboot'

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root (sudo bash $0)" >&2
  exit 1
fi

echo "${LINE}" > "${SUDOERS_FILE}"
chmod 440 "${SUDOERS_FILE}"
visudo -cf "${SUDOERS_FILE}"
echo "OK: ${SUDOERS_FILE}"
echo "Test: sudo -u vision ssh vision@127.0.0.1 true 2>/dev/null || true"
echo "Test from Mac: ssh vision@192.168.10.60 'sudo -n systemctl poweroff --dry-run 2>&1 || systemctl --version | head -1'"
