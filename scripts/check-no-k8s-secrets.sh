#!/bin/bash
# TD-237 ratchet: no Secret manifest under k8s/ except *.example.yaml / *.example.
# Prints paths only, never file contents.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "${root}"

# k8s/agent-access/token-secret.yaml is an empty service-account token request
# (no data, no stringData). scripts/check_agent_access.py refuses a value there.
hits="$(git grep -l '^kind: Secret' -- k8s ':!*.example.yaml' ':!*.example' ':!k8s/agent-access/token-secret.yaml' || true)"
if [[ -n "${hits}" ]]; then
  echo "committed Secret manifests under k8s/:" >&2
  echo "${hits}" >&2
  exit 1
fi
echo "PASS no committed Secret manifests under k8s/"
