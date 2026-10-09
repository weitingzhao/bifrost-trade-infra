#!/usr/bin/env bash
# Print the six clone SHAs of a succeeded STG run, as JSON, for a pinned PROD run.
# It reads the cluster and writes JSON. Creating the run is release.sh's job,
# through the platform (POST /api/v1/approvals, action start_pipeline_run).
#
# Usage:
#   scripts/release/prod-pinned-from-stg.sh <stg-run> [-o <file>]
#
# Refuses (exit 1) when the run is not a bifrost-deliver-stg run, did not succeed,
# or any of the six clone commits is missing or not 40 hex. The clone lines go to
# stderr so a caller can keep them. Stdout (or -o) is only the six SHAs:
# coreRevision, workerRevision, apiRevision, frontendRevision, uiRevision, infraRevision.
set -euo pipefail
# shellcheck source=scripts/release/lib.sh
source "$(dirname "$0")/lib.sh"

pinned_usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; }

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

read -r st reason pipeline < <("${RELEASE_TOOL[@]}" run-state "${run}")
[[ "${pipeline}" == "bifrost-deliver-stg" ]] || rel_die "${run} is a run of ${pipeline}, not bifrost-deliver-stg"
[[ "${st}" == "True" ]] || rel_die "${run} did not succeed (${st} ${reason})"

commits="$(mktemp)"
trap 'rm -f "${commits}"' EXIT
"${RELEASE_TOOL[@]}" clone-commits "${run}" | tee "${commits}" >&2

python3 - "${commits}" "${out}" <<'PY'
import json, sys
src, dest = sys.argv[1], sys.argv[2]
want = {
    "clone-core": "coreRevision",
    "clone-worker": "workerRevision",
    "clone-api": "apiRevision",
    "clone-frontend": "frontendRevision",
    "clone-ui": "uiRevision",
    "clone-infra": "infraRevision",
}
found = {}
for line in open(src, encoding="utf-8"):
    parts = line.split()
    if len(parts) >= 2 and parts[0] in want:
        found[want[parts[0]]] = parts[1]
missing = [name for name in want.values() if len(found.get(name, "")) != 40 or any(c not in "0123456789abcdef" for c in found.get(name, ""))]
if missing:
    sys.stderr.write("missing or not 40 hex: %s\n" % ", ".join(missing))
    sys.exit(1)
body = json.dumps({name: found[name] for name in want.values()}, indent=2) + "\n"
if dest:
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(body)
    sys.stderr.write("wrote %s\n" % dest)
else:
    sys.stdout.write(body)
PY
