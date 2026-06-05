#!/bin/sh
# Editable-install monorepo siblings then exec the service command.
set -e

CORE="/workspace/bifrost-trade-core"
WORKER="/workspace/bifrost-trade-worker"
SOCKET="/workspace/bifrost-trade-socket"
API="/workspace/bifrost-trade-api"

if [ -d "$CORE" ]; then
  pip install -q -e "$CORE"
fi

case "${BIFROST_DEV_STACK:-}" in
  worker|daemon|celery)
    [ -d "$WORKER" ] && pip install -q -e "$WORKER"
    ;;
  socket)
    [ -d "$SOCKET" ] && pip install -q -e "$SOCKET"
    ;;
  api)
    [ -d "$WORKER" ] && pip install -q -e "$WORKER"
    [ -d "$SOCKET" ] && pip install -q -e "$SOCKET"
    [ -d "$API" ] && pip install -q -e "$API"
    ;;
esac

exec "$@"
