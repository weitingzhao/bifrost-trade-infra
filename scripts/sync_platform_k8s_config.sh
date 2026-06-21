#!/usr/bin/env bash
# Copy bifrost-platform config into k8s/overlays/platform-stg for ConfigMap generation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM_ROOT="${PLATFORM_ROOT:-$(cd "${ROOT}/../bifrost-platform" && pwd)}"
DEST="${ROOT}/k8s/overlays/platform-stg/config"

if [[ ! -d "${PLATFORM_ROOT}/config" ]]; then
  echo "bifrost-platform config not found: ${PLATFORM_ROOT}/config" >&2
  echo "Set PLATFORM_ROOT to your bifrost-platform clone." >&2
  exit 1
fi

mkdir -p "${DEST}"
for f in environments.yaml clusters.yaml topology.yaml ops-context.yaml platform-auth.yaml; do
  cp "${PLATFORM_ROOT}/config/${f}" "${DEST}/${f}"
done

# Ensure platform-stg namespace is registered for cluster probes.
if ! grep -q 'bifrost-platform-stg' "${DEST}/clusters.yaml"; then
  echo "WARN: add bifrost-platform-stg to clusters.yaml bifrost_namespaces after sync" >&2
fi

echo "Synced platform config → ${DEST}"
