#!/bin/sh
# gpu-server is the Kubernetes node name; ubt-ai-4090 is the Linux hostname.
set -eu
if [ "$(/usr/bin/id -u)" -ne 0 ] || [ "$(/usr/bin/hostname -s)" != ubt-ai-4090 ]; then
  printf '%s\n' 'GPU poweroff refused: wrong host or execution user.' >&2
  exit 1
fi

check_idle() {
  attempt=0
  while [ "$attempt" -lt 3 ]; do
    connections=$(/usr/bin/ss -Htn state established '( sport = :8080 or sport = :8082 )') || return 1
    if [ -n "$connections" ]; then
      printf '%s\n' 'GPU poweroff refused: inference has an established connection.' >&2
      return 1
    fi
    gpu=$(/usr/bin/nvidia-smi --query-gpu=name,utilization.gpu --format=csv,noheader,nounits) || return 1
    if [ "$gpu" != 'NVIDIA GeForce RTX 4090, 0' ]; then
      printf '%s\n' 'GPU poweroff refused: expected one idle RTX 4090.' >&2
      return 1
    fi
    attempt=$((attempt + 1))
    if [ "$attempt" -lt 3 ]; then sleep 1; fi
  done
}

case "${1:-}" in
  check)
    check_idle
    printf '%s\n' 'gpu-server: idle'
    ;;
  poweroff)
    check_idle
    /usr/bin/systemctl --no-block poweroff
    printf '%s\n' 'gpu-server: shutdown accepted'
    ;;
  *) exit 2 ;;
esac
