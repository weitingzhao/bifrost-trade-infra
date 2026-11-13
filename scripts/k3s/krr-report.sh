#!/usr/bin/env bash
# Weekly request-drift table: what every container asks for against what KRR
# says it used. Read-only: KRR lists workloads and queries Prometheus; nothing
# is installed in the cluster and nothing is changed.
#
#   KRR=~/agent-work/compute-s1/tools scripts/k3s/krr-report.sh <out-dir>
#
# Needs: KRR checked out at a release tag with its requirements in a venv
# ($KRR/krr-src, $KRR/krr-venv; v1.31.3 was used on 2026-11-13), and a
# Prometheus address (`bdev start prometheus-pf` gives http://127.0.0.1:9090).
#
# Read before acting on the table:
# - KRR does not see CloudNativePG instances (they are not Deployments or
#   StatefulSets). The two database pods are missing from the table.
# - Its CPU figure is the highest per-pod p95 in the window, deleted pods
#   included. A pod from an incident week lifts the figure for its workload.
set -euo pipefail

out="${1:?usage: krr-report.sh <out-dir>}"
krr="${KRR:?set KRR to the directory holding krr-src and krr-venv}"
prom="${PROMETHEUS_URL:-http://127.0.0.1:9090}"
kubeconfig="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"
hours="${KRR_HOURS:-168}"
here="$(cd "$(dirname "$0")" && pwd)"
day="$(date -u +%F)"

curl -fsS -m 5 "${prom}/-/healthy" >/dev/null || { echo "krr-report: no Prometheus at ${prom}" >&2; exit 1; }
mkdir -p "$out"

run() { # <name> [extra krr args]
  local name="$1"; shift
  NO_COLOR=1 "${krr}/krr-venv/bin/python" "${krr}/krr-src/krr.py" simple \
    -k "$kubeconfig" -p "$prom" --history-duration "$hours" "$@" \
    -f json --fileoutput "${out}/${name}.json" --logtostderr -q >/dev/null 2>"${out}/${name}.log"
  # The JSON carries each workload's last-applied manifest; drop it.
  python3 - "${out}/${name}.json" <<'PY'
import json, sys
path = sys.argv[1]
doc = json.load(open(path))
if not doc["scans"]:
    sys.exit(f"krr-report: {path} has no scans; not a result")
for scan in doc["scans"]:
    scan["object"].pop("annotations", None)
json.dump(doc, open(path, "w"), ensure_ascii=False)
PY
}

run "krr-${day}"
run "krr-${day}-kube-system" -n kube-system
python3 "${here}/krr_summarize.py" "${out}/krr-${day}.md" "${out}/krr-${day}.json" "${out}/krr-${day}-kube-system.json"
echo "krr-report: ${out}/krr-${day}.md"
