#!/usr/bin/env bash
# TD-269 ratchet: SIGTERM on release.sh hold removes the window file within a few seconds.
set -euo pipefail

RELEASE_DIR="$(cd "$(dirname "$0")" && pwd)"

tmpdir="$(mktemp -d)"
holder=""

cleanup() {
  if [[ -n "${holder}" ]]; then
    kill -TERM "${holder}" 2>/dev/null || true
    wait "${holder}" 2>/dev/null || true
  fi
  rm -rf "${tmpdir}"
}
trap cleanup EXIT

export BIFROST_RELEASE_HOME="${tmpdir}/release-home"
export KUBECONFIG="${tmpdir}/kubeconfig"
export PATH="${tmpdir}/bin:${PATH}"
export BIFROST_RELEASE_WINDOW_PUBLISH=1
touch "${KUBECONFIG}"

mkdir -p "${tmpdir}/bin" "${BIFROST_RELEASE_HOME}"
cm_marker="${tmpdir}/cm-published"
export KUBECTL_CM_MARKER="${cm_marker}"

cat >"${tmpdir}/bin/kubectl" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
args="$*"
if [[ "${args}" == *delete*configmap* ]] || [[ "${args}" == *" delete "* ]]; then
  rm -f "${KUBECTL_CM_MARKER}"
  exit 0
fi
if [[ "${args}" == *configmap* ]] || [[ "${args}" == *" apply"* ]]; then
  touch "${KUBECTL_CM_MARKER}"
fi
exit 0
STUB
chmod +x "${tmpdir}/bin/kubectl"

release="${RELEASE_DIR}/release.sh"
window="${BIFROST_RELEASE_HOME}/window.json"

# Background hold must not write to stdout/stderr when this script runs under capture_output.
"${release}" hold --what bifrost-ui --who 'test@cursor-m2' >/dev/null 2>&1 &
holder=$!

deadline=$((SECONDS + 5))
ready=0
while [[ "${SECONDS}" -lt "${deadline}" ]]; do
  if [[ -f "${window}" ]] && [[ -f "${cm_marker}" ]]; then
    ready=1
    break
  fi
  sleep 0.05
done
[[ "${ready}" -eq 1 ]] || { echo "hold did not publish window + ConfigMap stub in time"; exit 1; }

kill -TERM "${holder}"

gone=0
deadline=$((SECONDS + 3))
while [[ "${SECONDS}" -lt "${deadline}" ]]; do
  if [[ ! -f "${window}" ]] && [[ ! -f "${cm_marker}" ]]; then
    gone=1
    break
  fi
  sleep 0.05
done

wait "${holder}" 2>/dev/null || true
holder=""

if [[ "${gone}" -ne 1 ]]; then
  echo "window file or ConfigMap marker still present after SIGTERM"
  ls -la "${BIFROST_RELEASE_HOME}" 2>/dev/null || true
  [[ -f "${cm_marker}" ]] && echo "cm marker still exists"
  exit 1
fi

echo "test_release_hold_interrupt: ok"
