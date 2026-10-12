#!/usr/bin/env bash
# Owner deletes one freeze record. release.sh unfreeze calls this in a later slice.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: freeze_lift.sh <name> <uid>" >&2
  exit 2
fi

name="$1"
uid="$2"

if [[ -z "${BIFROST_OWNER_KUBECONFIG:-}" ]]; then
  echo "BIFROST_OWNER_KUBECONFIG is required" >&2
  exit 2
fi
if [[ ! "$name" =~ ^freeze-[0-9a-f]{32}$ ]]; then
  echo "name must match ^freeze-[0-9a-f]{32}$" >&2
  exit 2
fi
if [[ -z "$uid" ]]; then
  echo "uid is required" >&2
  exit 2
fi

printf '{"kind":"DeleteOptions","apiVersion":"v1","preconditions":{"uid":"%s"},"propagationPolicy":"Background"}' "$uid" \
  | kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" delete --raw "/apis/release.bifrost.io/v1/freezes/$name" -f -
