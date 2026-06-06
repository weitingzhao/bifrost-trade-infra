#!/bin/sh
# Editable-install monorepo siblings then exec the service command.
# Markers are per-container (HOSTNAME); pip cache volume is shared across containers.
set -e

CORE="/workspace/bifrost-trade-core"
WORKER="/workspace/bifrost-trade-worker"
SOCKET="/workspace/bifrost-trade-socket"
API="/workspace/bifrost-trade-api"
MARKER_DIR="${BIFROST_DEV_INSTALL_MARKER:-/var/lib/bifrost-dev}"
CONTAINER_TAG="${HOSTNAME:-local}"
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-120}"

mkdir -p "$MARKER_DIR" /root/.cache/pip

install_editable() {
  dir="$1"
  name="$2"
  no_deps="${3:-0}"
  if [ ! -d "$dir" ]; then
    return 0
  fi
  marker="${MARKER_DIR}/installed-${CONTAINER_TAG}-${name}"
  if [ -f "$marker" ]; then
    return 0
  fi
  echo "[bifrost-dev] pip install -e ${name} (container ${CONTAINER_TAG}) ..."
  if [ "$no_deps" = "1" ]; then
    pip install -e "$dir" --no-deps
  else
    pip install -e "$dir"
  fi
  touch "$marker"
}

install_editable "$CORE" "bifrost-core"

case "${BIFROST_DEV_STACK:-}" in
  worker|daemon|celery)
    install_editable "$WORKER" "bifrost-worker"
    ;;
  socket)
    install_editable "$SOCKET" "bifrost-socket"
    ;;
  api)
    install_editable "$WORKER" "bifrost-worker"
    install_editable "$SOCKET" "bifrost-socket"
    # api pyproject lists local siblings as PyPI names — install without re-resolving deps.
    install_editable "$API" "bifrost-api" 1
    pip install "fastapi>=0.100.0" "uvicorn[standard]>=0.22.0"
    ;;
esac

echo "[bifrost-dev] starting: $*"
exec "$@"
