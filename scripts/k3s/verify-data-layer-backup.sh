#!/usr/bin/env bash
# CNPG scheduled backup health — MinIO target + recent completed backup.
#
# Optional: RUN_BACKUP_PROBE=1 triggers an immediate Backup and waits (slow).
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
CLUSTER_NAME="${CLUSTER_NAME:-bifrost-postgres}"
LOOKBACK_HOURS="${BACKUP_LOOKBACK_HOURS:-72}"

export KUBECONFIG

fail=0
pass() { echo "OK $*"; }
die() { echo "FAIL $*" >&2; fail=1; }

echo "==> CNPG backup verify (cluster=${CLUSTER_NAME}, lookback=${LOOKBACK_HOURS}h)"

if ! kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" >/dev/null 2>&1; then
  die "cluster/${CLUSTER_NAME} missing"
  exit 1
fi

ready="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.readyInstances}' 2>/dev/null || echo 0)"
instances="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.spec.instances}' 2>/dev/null || echo 0)"
if [[ "${ready}" -ge 1 && "${ready}" -eq "${instances}" ]]; then
  pass "CNPG readyInstances=${ready}/${instances}"
else
  die "CNPG readyInstances=${ready}/${instances}"
fi

ep="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.spec.backup.barmanObjectStore.endpointURL}' 2>/dev/null || true)"
if [[ "${ep}" == *"minio"* ]]; then
  pass "barman endpoint ${ep}"
else
  die "barman endpoint missing (${ep:-empty})"
fi

if kubectl get scheduledbackup bifrost-postgres-daily -n "${DATA_NAMESPACE}" >/dev/null 2>&1; then
  pass "scheduledbackup/bifrost-postgres-daily"
else
  die "scheduledbackup/bifrost-postgres-daily missing"
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -x "${ROOT}/scripts/k3s/ensure-minio-backup-bucket.sh" ]]; then
  if "${ROOT}/scripts/k3s/ensure-minio-backup-bucket.sh"; then
    pass "minio backup bucket"
  else
    die "minio backup bucket ensure"
  fi
fi

# Recent completed backup within lookback window
recent_ok=0
while IFS= read -r line; do
  [[ -z "${line}" ]] && continue
  name="${line%% *}"
  phase="$(kubectl get backup "${name}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.phase}' 2>/dev/null || echo unknown)"
  if [[ "${phase}" == "completed" ]]; then
    stopped="$(kubectl get backup "${name}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.stoppedAt}' 2>/dev/null || true)"
    if [[ -n "${stopped}" ]]; then
      pass "recent completed backup ${name} @ ${stopped}"
      recent_ok=1
      break
    fi
  fi
done < <(kubectl get backup -n "${DATA_NAMESPACE}" --sort-by=.metadata.creationTimestamp -o name 2>/dev/null | tail -5 | sed 's|backup.postgresql.cnpg.io/||')

if [[ "${recent_ok}" -eq 0 ]]; then
  die "no completed backup in last 5 scheduled runs (check CNPG backup logs / MinIO)"
fi

if [[ "${RUN_BACKUP_PROBE:-0}" == "1" ]]; then
  echo "==> RUN_BACKUP_PROBE=1 — triggering immediate backup"
  probe="backup-probe-${RANDOM}"
  kubectl cnpg backup "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" --method barmanObjectStore --backup-name "${probe}" 2>/dev/null \
    || kubectl apply -f - <<EOF
apiVersion: postgresql.cnpg.io/v1
kind: Backup
metadata:
  name: ${probe}
  namespace: ${DATA_NAMESPACE}
spec:
  cluster:
    name: ${CLUSTER_NAME}
  method: barmanObjectStore
EOF
  deadline=$((SECONDS + 900))
  while [[ "${SECONDS}" -lt "${deadline}" ]]; do
    phase="$(kubectl get backup "${probe}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.phase}' 2>/dev/null || echo pending)"
    case "${phase}" in
      completed) pass "probe backup ${probe} completed"; break ;;
      failed)
        err="$(kubectl get backup "${probe}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.error}' 2>/dev/null || true)"
        die "probe backup failed: ${err}"
        break
        ;;
    esac
    sleep 10
  done
fi

if [[ "${fail}" -eq 0 ]]; then
  echo "verify PASS — CNPG backup chain healthy"
else
  echo "verify FAIL — CNPG backup issues" >&2
  exit 1
fi
