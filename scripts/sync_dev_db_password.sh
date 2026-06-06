#!/usr/bin/env bash
# Back-compat alias — use sync_dev_config.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "${ROOT}/scripts/sync_dev_config.sh"
