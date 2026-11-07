#!/bin/bash
# Owner only: helper arrives on stdin; no deploy-supplied configuration.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
[[ $EUID == 0 && $(hostname -s) == ubt-k3s-06 ]] || { echo 'run as root on ubt-k3s-06' >&2; exit 1; }
id deploy >/dev/null
# This installer adds only its own rule; account provisioning is separate.
install -d -o root -g root -m 0755 /usr/local/libexec/bifrost /etc/bifrost
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cat > "$work/agentd-update"
bash -n "$work/agentd-update"
printf '%s\n' 'deploy ALL=(root) NOPASSWD: /usr/local/sbin/agentd-update' > "$work/sudoers"
chmod 0440 "$work/sudoers"
visudo -cf "$work/sudoers"
visudo -c
install -o root -g root -m 0755 "$work/agentd-update" /usr/local/sbin/agentd-update
# Empty root-managed config supports public packages; Owner may add read-only auth.
if [[ ! -e /etc/bifrost/agentd-update.curl ]]; then
  install -o root -g root -m 0600 /dev/null /etc/bifrost/agentd-update.curl
fi
install -o root -g root -m 0440 "$work/sudoers" /etc/sudoers.d/bifrost-agentd-update
if ! visudo -c; then
  rm -f /etc/sudoers.d/bifrost-agentd-update
  exit 1
fi
