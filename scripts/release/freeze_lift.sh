#!/usr/bin/env bash
# Owner deletes one freeze record. release.sh unfreeze calls this in a later slice.
set -euo pipefail

name_re='^freeze-[0-9a-f]{32}$'
uid_re='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'

# encode_delete_body writes one JSON object. Keys come from the encoder, not concatenation.
encode_delete_body() {
  python3 - "$1" <<'PY'
import json, sys
uid = sys.argv[1]
sys.stdout.write(json.dumps(
    {
        "kind": "DeleteOptions",
        "apiVersion": "v1",
        "preconditions": {"uid": uid},
        "propagationPolicy": "Background",
    },
    separators=(",", ":"),
))
PY
}

freeze_lift_main() {
  if [[ $# -ne 2 ]]; then
    echo "usage: freeze_lift.sh <name> <uid>" >&2
    exit 2
  fi

  local name="$1"
  local uid="$2"

  if [[ -z "${BIFROST_OWNER_KUBECONFIG:-}" ]]; then
    echo "BIFROST_OWNER_KUBECONFIG is required" >&2
    exit 2
  fi
  if [[ ! "$name" =~ $name_re ]]; then
    echo "name must match ^freeze-[0-9a-f]{32}$" >&2
    exit 2
  fi
  if [[ ! "$uid" =~ $uid_re ]]; then
    echo "uid must match ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$" >&2
    exit 2
  fi

  local body
  body="$(encode_delete_body "$uid")"
  printf '%s' "$body" | kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" delete --raw "/apis/release.bifrost.io/v1/freezes/$name" -f -
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  freeze_lift_main "$@"
fi
