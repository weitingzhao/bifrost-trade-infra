#!/usr/bin/env bash
# Copy bifrost-platform config into k8s/overlays/platform-{stg,prod} for ConfigMap generation.
# Full config sync targets STG; PROD receives sessions-catalog.yaml only (other PROD
# config files are maintained in-overlay and must not be overwritten blindly).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM_ROOT="${PLATFORM_ROOT:-$(cd "${ROOT}/../bifrost-platform" && pwd)}"
DEST_STG="${ROOT}/k8s/overlays/platform-stg/config"
DEST_PROD="${ROOT}/k8s/overlays/platform-prod/config"

if [[ ! -d "${PLATFORM_ROOT}/config" ]]; then
  echo "bifrost-platform config not found: ${PLATFORM_ROOT}/config" >&2
  echo "Set PLATFORM_ROOT to your bifrost-platform clone." >&2
  exit 1
fi

mkdir -p "${DEST_STG}" "${DEST_STG}/programs" "${DEST_PROD}"
for f in environments.yaml clusters.yaml topology.yaml ops-context.yaml platform-auth.yaml sessions-catalog.yaml; do
  if [[ ! -f "${PLATFORM_ROOT}/config/${f}" ]]; then
    echo "WARN: missing ${PLATFORM_ROOT}/config/${f} — skip" >&2
    continue
  fi
  cp "${PLATFORM_ROOT}/config/${f}" "${DEST_STG}/${f}"
done
if [[ -d "${PLATFORM_ROOT}/config/programs" ]]; then
  cp "${PLATFORM_ROOT}/config/programs/"*.yaml "${DEST_STG}/programs/"
fi

# Sessions catalog is shared STG/PROD allowlist — keep overlays in lockstep.
if [[ -f "${PLATFORM_ROOT}/config/sessions-catalog.yaml" ]]; then
  cp "${PLATFORM_ROOT}/config/sessions-catalog.yaml" "${DEST_PROD}/sessions-catalog.yaml"
fi

# Ensure platform-stg namespace is registered for cluster probes.
if ! grep -q 'bifrost-platform-stg' "${DEST_STG}/clusters.yaml"; then
  echo "WARN: add bifrost-platform-stg to clusters.yaml bifrost_namespaces after sync" >&2
fi

echo "Synced platform config → ${DEST_STG}"
echo "Synced sessions-catalog.yaml → ${DEST_PROD}"
