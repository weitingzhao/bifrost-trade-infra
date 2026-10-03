# shellcheck shell=bash
# Shared by the release scripts (TD-84). Source it; it sets no shell options of its own.

RELEASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_ROOT="$(cd "${RELEASE_DIR}/../.." && pwd)"
RELEASE_TOOL=(python3 "${RELEASE_DIR}/release_tool.py")

export KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"
export CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"

# Local state: the release window lock and the record of passed checks. Small, no account content.
RELEASE_HOME="${BIFROST_RELEASE_HOME:-${HOME}/.bifrost-release}"
# Snapshots (they hold account content: keep them out of every repo).
RELEASE_SNAP_BASE="${BIFROST_RELEASE_DIR:-/tmp/claude-501/release}"
# A core checkout, to read the pyproject version of the SHA /health reports.
CORE_REPO="${BIFROST_CORE_REPO:-${INFRA_ROOT}/../bifrost-trade-core}"

rel_log() { printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
rel_die() { printf 'ERROR: %s\n' "$1" >&2; exit "${2:-2}"; }

rel_check_env() {
  case "$1" in
    dev|stg|prod) ;;
    *) rel_die "env must be dev, stg or prod (got '$1')" ;;
  esac
}

rel_require_kubeconfig() {
  [[ -f "${KUBECONFIG}" ]] || rel_die "kubeconfig not found: ${KUBECONFIG}"
}

# The core SHA a run's clone-core TaskRun cloned (40 hex), or exit.
rel_clone_core_sha() {
  local run="$1" sha
  sha="$({ "${RELEASE_TOOL[@]}" clone-commits "${run}" || true; } | awk '$1 == "clone-core" { print $2 }')"
  [[ "${sha}" =~ ^[0-9a-f]{40}$ ]] || rel_die "${run}: clone-core commit missing (got '${sha}')"
  printf '%s\n' "${sha}"
}
