#!/usr/bin/env bash
# Copy bifrost-platform config into k8s/overlays/platform-{stg,prod} for ConfigMap generation.
# Full config sync targets STG. PROD receives sessions-catalog.yaml and
# ops-context.yaml (one spine, TD-109). Other PROD config files stay
# overlay-local and must not be overwritten blindly.
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

mkdir -p "${DEST_STG}" "${DEST_PROD}"
for f in environments.yaml clusters.yaml topology.yaml ops-context.yaml platform-auth.yaml sessions-catalog.yaml; do
  if [[ ! -f "${PLATFORM_ROOT}/config/${f}" ]]; then
    echo "WARN: missing ${PLATFORM_ROOT}/config/${f} — skip" >&2
    continue
  fi
  if [[ "${f}" == platform-auth.yaml ]]; then
    # The source carries local-dev defaults; the cluster reads every role from token_env.
    grep -vE '^[[:space:]]*token:[[:space:]]' "${PLATFORM_ROOT}/config/${f}" > "${DEST_STG}/${f}"
  else
    cp "${PLATFORM_ROOT}/config/${f}" "${DEST_STG}/${f}"
  fi
done

# Sessions catalog is shared STG/PROD allowlist — keep overlays in lockstep.
if [[ -f "${PLATFORM_ROOT}/config/sessions-catalog.yaml" ]]; then
  cp "${PLATFORM_ROOT}/config/sessions-catalog.yaml" "${DEST_PROD}/sessions-catalog.yaml"
fi

# The spine is one document. Argo applies these copies; a hand-kept PROD file
# drifted (TD-109). check_ops_context_parity.py fails when they diverge.
if [[ -f "${PLATFORM_ROOT}/config/ops-context.yaml" ]]; then
  cp "${PLATFORM_ROOT}/config/ops-context.yaml" "${DEST_STG}/ops-context.yaml"
  cp "${PLATFORM_ROOT}/config/ops-context.yaml" "${DEST_PROD}/ops-context.yaml"
fi

# Trust overrides are one Owner-approved document for both environments (W-32 B2).
# platform-api reads /app/config/trust-overrides.yaml on every request; when the
# file is missing the overrides silently vanish (a demotion such as L0 is lost).
if [[ -f "${PLATFORM_ROOT}/config/trust-overrides.yaml" ]]; then
  cp "${PLATFORM_ROOT}/config/trust-overrides.yaml" "${DEST_STG}/trust-overrides.yaml"
  cp "${PLATFORM_ROOT}/config/trust-overrides.yaml" "${DEST_PROD}/trust-overrides.yaml"
fi

# Which live workloads the Releases page reads (W-33). Same document in both
# environments; a missing file makes Research / plugin versions disappear.
if [[ -f "${PLATFORM_ROOT}/config/running-images.yaml" ]]; then
  cp "${PLATFORM_ROOT}/config/running-images.yaml" "${DEST_STG}/running-images.yaml"
  cp "${PLATFORM_ROOT}/config/running-images.yaml" "${DEST_PROD}/running-images.yaml"
fi

# Actuation allow-list (LANE-W33B). Platform code, both overlays, and the
# Tekton checker must read the same bytes.
if [[ -f "${PLATFORM_ROOT}/config/actuation-policy.yaml" ]]; then
  cp "${PLATFORM_ROOT}/config/actuation-policy.yaml" "${DEST_STG}/actuation-policy.yaml"
  cp "${PLATFORM_ROOT}/config/actuation-policy.yaml" "${DEST_PROD}/actuation-policy.yaml"
  tekton_copy="${ROOT}/k8s/cicd/tekton/apply-manifest/actuation-policy.yaml"
  mkdir -p "$(dirname "${tekton_copy}")"
  cp "${PLATFORM_ROOT}/config/actuation-policy.yaml" "${tekton_copy}"
fi

# Ensure platform-stg namespace is registered for cluster probes.
if ! grep -q 'bifrost-platform-stg' "${DEST_STG}/clusters.yaml"; then
  echo "WARN: add bifrost-platform-stg to clusters.yaml bifrost_namespaces after sync" >&2
fi

echo "Synced platform config → ${DEST_STG}"
echo "Synced sessions-catalog.yaml, ops-context.yaml, trust-overrides.yaml, and running-images.yaml → ${DEST_PROD}"
