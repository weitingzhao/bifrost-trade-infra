#!/usr/bin/env bash
# Before/after checks of a Trade release (TD-84). Read-only: HTTP GETs and `kubectl get`.
#
#   release-check.sh <env> before [--dir D] [--accounts a,b]
#   release-check.sh <env> after  (--run <pipelinerun> | --expect-core-sha <sha>) [--dir D]
#                                 [--allow F]... [--probes F]... [--accounts a,b] [--no-diff]
#   release-check.sh <env> probes [--probes F]...
#   release-check.sh diff <before.json> <after.json> [--allow F]...
#
# env is dev, stg or prod. `before` snapshots fills (contract_key, side, quantity per
# account_executions_id), /api/trading/performance and model-analysis for every account
# the API names, plus the core each /health reports, into <dir>/<env>-before.json.
# `after` takes the same snapshot and
#   - diffs it: "identical", "only added keys" or "changed values" per section; changed,
#     removed and length differences fail unless an --allow file lists them (glob per line,
#     `[*]` = a list row; see expected.d/). Added keys and new fills never fail.
#   - checks /health on monitor/trading/market/research: core_sha = the clone-core commit of
#     --run (or --expect-core-sha) and core_version = that commit's pyproject version
#     (read from BIFROST_CORE_REPO, default ../bifrost-trade-core; not cross-checked when the
#     commit is not there).
#   - runs probes.json plus every --probes file.
# It writes <dir>/<env>-check.json and, with --run, ~/.bifrost-release/checks/<run>.json,
# which `release.sh prod --from-stg <run>` requires to say passed.
#
# Default dir: ${BIFROST_RELEASE_DIR:-/tmp/claude-501/release}/<date>/<env>. Snapshots hold
# account content: never copy them into a repo.
# Exit: 0 pass, 1 unexpected change / health / probe failure, 2 usage or read error.
set -euo pipefail
# shellcheck source=scripts/release/lib.sh
source "$(dirname "$0")/lib.sh"

check_usage() { sed -n '2,29p' "$0" | sed 's/^# \{0,1\}//'; }

if [[ "${1:-}" == "diff" ]]; then
  shift
  [[ $# -ge 2 ]] || { check_usage >&2; exit 2; }
  before="$1" after="$2"; shift 2
  dargs=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --allow) dargs+=(--allow "${2:?--allow needs a file}"); shift 2 ;;
      *) rel_die "unknown argument for diff: $1" ;;
    esac
  done
  [[ ! -f "${RELEASE_DIR}/expected.d/always.allow" ]] || dargs+=(--allow "${RELEASE_DIR}/expected.d/always.allow")
  exec "${RELEASE_TOOL[@]}" diff "${before}" "${after}" ${dargs[@]+"${dargs[@]}"}
fi

[[ $# -ge 2 ]] || { check_usage >&2; exit 2; }
env="$1" phase="$2"; shift 2
rel_check_env "${env}"
case "${phase}" in before|after|probes) ;; *) check_usage >&2; exit 2 ;; esac

dir="" run="" expect_sha="" accounts="" no_diff=0
allow=() probes=()
[[ ! -f "${RELEASE_DIR}/expected.d/always.allow" ]] || allow+=(--allow "${RELEASE_DIR}/expected.d/always.allow")
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) dir="${2:?}"; shift 2 ;;
    --run) run="${2:?}"; shift 2 ;;
    --expect-core-sha) expect_sha="${2:?}"; shift 2 ;;
    --accounts) accounts="${2:?}"; shift 2 ;;
    --allow) allow+=(--allow "${2:?}"); shift 2 ;;
    --probes) probes+=(--file "${2:?}"); shift 2 ;;
    --no-diff) no_diff=1; shift ;;
    -h|--help) check_usage; exit 0 ;;
    *) rel_die "unknown argument: $1" ;;
  esac
done
dir="${dir:-${RELEASE_SNAP_BASE}/$(date +%F)/${env}}"
mkdir -p "${dir}"

snap_args=()
[[ -z "${accounts}" ]] || snap_args+=(--accounts "${accounts}")

if [[ "${phase}" == "probes" ]]; then
  exec "${RELEASE_TOOL[@]}" probes "${env}" --file "${RELEASE_DIR}/probes.json" ${probes[@]+"${probes[@]}"}
fi

if [[ "${phase}" == "before" ]]; then
  out="${dir}/${env}-before.json"
  [[ ! -f "${out}" ]] || mv "${out}" "${out%.json}.prev.json"
  rel_log "snapshot ${env} before"
  "${RELEASE_TOOL[@]}" snapshot "${env}" -o "${out}" ${snap_args[@]+"${snap_args[@]}"}
  exit 0
fi

# ── after ──
if [[ -n "${run}" ]]; then
  rel_require_kubeconfig
  sha="$(rel_clone_core_sha "${run}")"
  [[ -z "${expect_sha}" || "${expect_sha}" == "${sha}" ]] \
    || rel_die "--expect-core-sha ${expect_sha} differs from ${run}'s clone-core ${sha}"
  expect_sha="${sha}"
fi
[[ "${expect_sha}" =~ ^[0-9a-f]{40}$ ]] || rel_die "after needs --run <pipelinerun> or --expect-core-sha <40-hex sha>"

before="${dir}/${env}-before.json"
after="${dir}/${env}-after.json"
if [[ "${no_diff}" -eq 0 && ! -f "${before}" ]]; then
  rel_die "no ${before}: run '$0 ${env} before' first, or pass --no-diff to check health and probes only"
fi

rel_log "snapshot ${env} after"
"${RELEASE_TOOL[@]}" snapshot "${env}" -o "${after}" ${snap_args[@]+"${snap_args[@]}"}

diff_rc=0 health_rc=0 probes_rc=0
if [[ "${no_diff}" -eq 0 ]]; then
  rel_log "diff ${env} before -> after"
  "${RELEASE_TOOL[@]}" diff "${before}" "${after}" --json "${dir}/${env}-diff.json" ${allow[@]+"${allow[@]}"} || diff_rc=$?
fi
rel_log "health ${env}: core must be ${expect_sha}"
"${RELEASE_TOOL[@]}" health "${env}" --expect-sha "${expect_sha}" --core-repo "${CORE_REPO}" \
  --json "${dir}/${env}-health.json" || health_rc=$?
rel_log "probes ${env}"
"${RELEASE_TOOL[@]}" probes "${env}" --file "${RELEASE_DIR}/probes.json" ${probes[@]+"${probes[@]}"} || probes_rc=$?

passed=false
if [[ "${diff_rc}" -eq 0 && "${health_rc}" -eq 0 && "${probes_rc}" -eq 0 ]]; then passed=true; fi
diff_state="checked"
[[ "${no_diff}" -eq 0 ]] || diff_state="skipped"
check_json="${dir}/${env}-check.json"
python3 - "${check_json}" <<PY
import json, sys
from datetime import datetime, timezone
json.dump({
    "env": "${env}", "run": "${run}" or None, "core_sha": "${expect_sha}", "passed": "${passed}" == "true",
    "diff": "${diff_state}", "diff_rc": ${diff_rc}, "health_rc": ${health_rc}, "probes_rc": ${probes_rc},
    "dir": "${dir}", "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
}, open(sys.argv[1], "w"), indent=1)
PY
if [[ -n "${run}" ]]; then
  mkdir -p "${RELEASE_HOME}/checks"
  cp "${check_json}" "${RELEASE_HOME}/checks/${run}.json"
fi

echo
echo "release-check ${env} after: $([[ "${passed}" == true ]] && echo PASS || echo FAIL)" \
  "(diff ${diff_state}: rc ${diff_rc}, health rc ${health_rc}, probes rc ${probes_rc}) — ${check_json}"
[[ "${passed}" == true ]]
