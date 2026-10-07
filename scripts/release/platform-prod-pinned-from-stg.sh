#!/usr/bin/env bash
# Generate the Ops Platform PROD PipelineRun from a bifrost-deliver-platform (STG) run that
# succeeded (TD-234). Generates only: it reads the cluster (`kubectl get`) and writes JSON.
#
# The run is bifrost-deliver-platform-prod with revision = the commit that STG run's
# clone-platform cloned and uiRevision = the commit its clone-ui cloned, so PROD gets the
# Console that was tested on STG instead of whatever bifrost-ui main is by then. Labels
# bifrost.io/purpose=platform-prod-pinned and bifrost.io/from-stg-run=<stg-run>; the
# taskRunSpecs / taskRunTemplate / timeouts / workspaces are the STG run's.
#
# Usage:
#   scripts/release/platform-prod-pinned-from-stg.sh <stg-run> [-o <file>]
#   kubectl create -f <file>        # Owner-approved PROD deliver only
#
# Refuses (exit 1) when the run is not a bifrost-deliver-platform run, did not succeed, or
# either clone commit is missing or not 40 hex. The two commits go to stderr.
set -euo pipefail
# shellcheck source=scripts/release/lib.sh
source "$(dirname "$0")/lib.sh"

pinned_usage() { sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; }

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

args=(platform-pinned-spec "${run}")
[[ -z "${out}" ]] || args+=(-o "${out}")
"${RELEASE_TOOL[@]}" "${args[@]}"
[[ -z "${out}" ]] || echo "wrote ${out} (not created)" >&2
