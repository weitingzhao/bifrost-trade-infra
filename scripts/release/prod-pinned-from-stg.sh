#!/usr/bin/env bash
# Generate the PROD pinned PipelineRun from an STG run that succeeded (TD-84). Generates only:
# it reads the cluster (`kubectl get`) and writes JSON; creating the run is release.sh's job
# (or `kubectl create -f <file>` by hand).
#
# The spec is the live `pipeline/bifrost-deliver-prod` spec inlined as pipelineSpec, with each
# clone-<repo> task's `revision` set to the commit that STG run's clone-<repo> TaskRun cloned
# (result `commit`), wrapped as a PipelineRun (generateName bifrost-deliver-prod-pinned-,
# label bifrost.io/purpose=prod-pinned, bifrost.io/from-stg-run=<stg-run>) with the
# taskRunSpecs / taskRunTemplate / timeouts / workspaces of pipelinerun-deliver-stg.json.
#
# Usage:
#   scripts/release/prod-pinned-from-stg.sh <stg-run> [-o <file>]
#
# Refuses (exit 1) when the run is not a bifrost-deliver-stg run, did not succeed, or any
# clone commit is missing or not 40 hex. The six commits go to stderr.
set -euo pipefail
# shellcheck source=scripts/release/lib.sh
source "$(dirname "$0")/lib.sh"

pinned_usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; }

run="" out=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output) out="${2:?-o needs a file}"; shift 2 ;;
    -h|--help) pinned_usage; exit 0 ;;
    -*) echo "unknown option: $1" >&2; pinned_usage >&2; exit 2 ;;
    *) [[ -z "${run}" ]] || rel_die "only one <stg-run> please"; run="$1"; shift ;;
  esac
done
[[ -n "${run}" ]] || { pinned_usage >&2; exit 2; }
rel_require_kubeconfig

args=(pinned-spec "${run}" --template "${RELEASE_DIR}/pipelinerun-deliver-stg.json")
[[ -z "${out}" ]] || args+=(-o "${out}")
"${RELEASE_TOOL[@]}" "${args[@]}"
[[ -z "${out}" ]] || echo "wrote ${out} (not created; release.sh prod --from-stg ${run} creates it)" >&2
