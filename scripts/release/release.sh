#!/usr/bin/env bash
# One entry for a Trade release (TD-84): STG from main, PROD pinned to an STG run, DEV catch-up.
#
#   release.sh stg  [options]                    bifrost-deliver-stg (revision main)
#   release.sh prod --from-stg <run> [options]   bifrost-deliver-prod-pinned-* at that STG run's commits
#   release.sh dev  [options]                    make dev-sync-backend-images RESTART=1 (:stg -> :dev, backend + frontend)
#   release.sh window [--clear]                  show the release window (exit 1 while one is open)
#   release.sh db-steps [<env>]                  list one-off DB steps and their state
#   release.sh db-done <env> <step-id>           record that the Owner ran a step
#
# options: --dry-run         run the read-only checks, print every other command, change nothing
#          --allow <file>    expected changes for the after-check diff (repeatable; see expected.d/)
#          --probes <file>   extra probes for the after-check (repeatable)
#          --what <text>     what is being released (goes into the window lock)
#          --who <name>      who releases (default $BIFROST_RELEASE_WHO, else user@host)
#          --timeout <s>     how long to wait for the run (default 3600)
#
# Steps: open the release window (~/.bifrost-release/window.json; refuses if one is open) ->
# no bifrost-deliver-* run running or created in the last 2 minutes -> [prod: the STG run
# succeeded and its release-check passed; generate the pinned spec] -> pending one-off DB steps
# for this env stop the release (they are the Owner's, see db-steps.d/README.md) -> before
# snapshot -> create the run -> wait, with each TaskRun's duration -> after-check -> summary
# with timings and the next command. The window closes when the script exits, however it exits.
#
# Exit: 0 done, 1 a check or the run failed, 2 usage / refused before starting, 3 waiting on
# the Owner (DB steps) or the run outlived --timeout (it is still running).
set -euo pipefail
# shellcheck source=scripts/release/lib.sh
source "$(dirname "$0")/lib.sh"

release_usage() { sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; }

WINDOW="${RELEASE_HOME}/window.json"
DONE_FILE="${RELEASE_HOME}/db-steps.done"
DB_STEPS_DIR="${BIFROST_DB_STEPS_DIR:-${RELEASE_DIR}/db-steps.d}"
STG_TEMPLATE="${RELEASE_DIR}/pipelinerun-deliver-stg.json"

# ── window ───────────────────────────────────────────────────────────────────

window_show() {
  if [[ ! -f "${WINDOW}" ]]; then
    echo "no release window open (${WINDOW})"
    return 0
  fi
  echo "release window OPEN (${WINDOW}):"
  sed 's/^/  /' "${WINDOW}"
  local pid host
  pid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("pid", ""))' "${WINDOW}" 2>/dev/null || true)"
  host="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("host", ""))' "${WINDOW}" 2>/dev/null || true)"
  if [[ "${host}" == "$(hostname -s)" && -n "${pid}" ]] && ! kill -0 "${pid}" 2>/dev/null; then
    echo "  (pid ${pid} is no longer running on this host: a stale window; the Owner may clear it with: $0 window --clear)"
  fi
  return 1
}

window_clear() {
  [[ -f "${WINDOW}" ]] || { echo "no release window open"; return 0; }
  local pid host
  pid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("pid", ""))' "${WINDOW}")"
  host="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("host", ""))' "${WINDOW}")"
  if [[ "${host}" == "$(hostname -s)" && -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    rel_die "the release holding the window (pid ${pid}) is still running; let it finish" 1
  fi
  cat "${WINDOW}"
  rm -f "${WINDOW}"
  echo "cleared"
}

window_open() {
  mkdir -p "${RELEASE_HOME}"
  local body
  body="$(python3 - "${WHO}" "${WHAT}" "${ENV_NAME}" "$$" "$(hostname -s)" <<'PY'
import json, sys
from datetime import datetime, timezone
who, what, env, pid, host = sys.argv[1:6]
print(json.dumps({"who": who, "what": what, "env": env, "pid": int(pid), "host": host,
                  "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, indent=1))
PY
)"
  # noclobber makes the create atomic: two sessions cannot both open the window.
  if ! (set -o noclobber; printf '%s\n' "${body}" >"${WINDOW}") 2>/dev/null; then
    window_show || true
    rel_die "REFUSED: another release holds the window" 2
  fi
  WINDOW_OWNED=1
  trap window_close EXIT
}

window_close() {
  if [[ "${WINDOW_OWNED:-0}" -eq 1 ]]; then
    rm -f "${WINDOW}"
    WINDOW_OWNED=0
  fi
}

# ── helpers ──────────────────────────────────────────────────────────────────

REFUSALS=0
refuse() {
  # In a dry run a failed precondition is reported and the walk-through goes on.
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "WOULD REFUSE: $*"
    REFUSALS=$((REFUSALS + 1))
  else
    rel_die "REFUSED: $*" 2
  fi
}

STEP_NAMES=() STEP_SECS=()
STEP_T0=0
step() { STEP_T0=$(date +%s); echo; rel_log "── $*"; STEP_NAMES+=("$*"); }
step_end() { STEP_SECS+=($(($(date +%s) - STEP_T0))); }

would() {
  echo "[dry-run] would run:"
  printf '  '; printf ' %q' "$@"; echo
}

deliver_free() {
  if ! "${RELEASE_TOOL[@]}" deliver-busy; then
    refuse "a deliver run is running or just started (one release at a time)"
  fi
}

db_steps_gate() {
  local when="$1" out rc=0
  out="$("${RELEASE_TOOL[@]}" db-steps "${ENV_NAME}" --dir "${DB_STEPS_DIR}" --done-file "${DONE_FILE}" --when "${when}")" || rc=$?
  [[ "${rc}" -le 1 ]] || rel_die "could not read ${DB_STEPS_DIR}"
  if [[ "${rc}" -eq 0 ]]; then
    echo "no pending ${when}-deliver DB steps for ${ENV_NAME}"
    return 0
  fi
  echo "Pending one-off DB steps for ${ENV_NAME} (the Owner runs these in their own terminal):"
  echo
  printf '%s\n' "${out}"
  if [[ "${when}" == "after" ]]; then
    return 0
  fi
  echo "When each is done: $0 db-done ${ENV_NAME} <step-id>, then run this release again."
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "WOULD STOP here for the DB steps above."
    REFUSALS=$((REFUSALS + 1))
    return 0
  fi
  exit 3
}

summary() {
  local i total=0
  echo
  echo "── summary: ${ENV_NAME}${RUN_NAME:+ ${RUN_NAME}} ($([[ "${DRY_RUN}" -eq 1 ]] && echo dry-run || echo "${RESULT}"))"
  for i in "${!STEP_SECS[@]}"; do
    printf '  %-52s %4ss\n' "${STEP_NAMES[$i]}" "${STEP_SECS[$i]}"
    total=$((total + STEP_SECS[i]))
  done
  printf '  %-52s %4ss\n' "total" "${total}"
  echo "  snapshots and checks: ${OUT_DIR}"
}

# ── db-steps / db-done ───────────────────────────────────────────────────────

cmd_db_steps() {
  local envs=(dev stg prod)
  [[ $# -eq 0 ]] || { rel_check_env "$1"; envs=("$1"); }
  local e
  for e in "${envs[@]}"; do
    "${RELEASE_TOOL[@]}" db-steps "${e}" --dir "${DB_STEPS_DIR}" --done-file "${DONE_FILE}" --list
  done
}

cmd_db_done() {
  [[ $# -eq 2 ]] || rel_die "usage: $0 db-done <env> <step-id>"
  rel_check_env "$1"
  grep -rqs "^id: *$2\b" "${DB_STEPS_DIR}" || rel_die "no step with id '$2' in ${DB_STEPS_DIR}"
  mkdir -p "${RELEASE_HOME}"
  printf '%s %s %s %s\n' "$1" "$2" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${BIFROST_RELEASE_WHO:-${USER}@$(hostname -s)}" >>"${DONE_FILE}"
  echo "recorded: $1 $2 (also add '$1' to the step's done: line in the next infra commit)"
}

# ── the release ──────────────────────────────────────────────────────────────

case "${1:-}" in
  window)
    shift
    if [[ "${1:-}" == "--clear" ]]; then window_clear; exit $?; fi
    window_show; exit $? ;;
  db-steps) shift; cmd_db_steps "$@"; exit 0 ;;
  db-done) shift; cmd_db_done "$@"; exit 0 ;;
  dev|stg|prod) ENV_NAME="$1"; shift ;;
  -h|--help|"") release_usage; exit 0 ;;
  *) release_usage >&2; exit 2 ;;
esac

DRY_RUN=0 FROM_STG="" WHAT="" WHO="${BIFROST_RELEASE_WHO:-${USER}@$(hostname -s)}" TIMEOUT=3600
ALLOW=() PROBES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --from-stg) FROM_STG="${2:?--from-stg needs a run name}"; shift 2 ;;
    --allow) ALLOW+=(--allow "${2:?}"); shift 2 ;;
    --probes) PROBES+=(--probes "${2:?}"); shift 2 ;;
    --what) WHAT="${2:?}"; shift 2 ;;
    --who) WHO="${2:?}"; shift 2 ;;
    --timeout) TIMEOUT="${2:?}"; shift 2 ;;
    -h|--help) release_usage; exit 0 ;;
    *) rel_die "unknown argument: $1" ;;
  esac
done
if [[ "${ENV_NAME}" == "prod" && -z "${FROM_STG}" ]]; then
  rel_die "prod needs --from-stg <bifrost-deliver-stg run> (the STG run of this release that passed its check)"
fi
[[ "${ENV_NAME}" == "prod" || -z "${FROM_STG}" ]] || rel_die "--from-stg is for prod only"
WHAT="${WHAT:-${ENV_NAME} release${FROM_STG:+ from ${FROM_STG}}}"
rel_require_kubeconfig

OUT_DIR="${RELEASE_SNAP_BASE}/$(date +%F)/${ENV_NAME}-$(date +%H%M%S)"
mkdir -p "${OUT_DIR}"
RUN_NAME="" RESULT="failed"
CHECK_ARGS=(--dir "${OUT_DIR}" ${ALLOW[@]+"${ALLOW[@]}"} ${PROBES[@]+"${PROBES[@]}"})

echo "release ${ENV_NAME}: ${WHAT} — by ${WHO}$([[ "${DRY_RUN}" -eq 1 ]] && echo ' (DRY RUN: nothing will be created)')"

step "release window"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  window_show || refuse "another release holds the window"
  echo "[dry-run] would open ${WINDOW} (who/what/env/pid/host/started_at) and remove it on exit"
else
  window_open
  echo "opened ${WINDOW}"
fi
step_end

step "no deliver run in flight"
deliver_free
step_end

PINNED_SPEC="" STG_CORE=""
if [[ "${ENV_NAME}" == "prod" ]]; then
  step "STG run succeeded and passed its check"
  read -r st reason pipeline < <("${RELEASE_TOOL[@]}" run-state "${FROM_STG}")
  [[ "${pipeline}" == "bifrost-deliver-stg" ]] || refuse "${FROM_STG} is a run of ${pipeline}, not bifrost-deliver-stg"
  [[ "${st}" == "True" ]] || refuse "${FROM_STG} did not succeed (${st} ${reason})"
  ledger="${RELEASE_HOME}/checks/${FROM_STG}.json"
  if [[ ! -f "${ledger}" ]]; then
    refuse "no release-check record for ${FROM_STG} (${ledger}); run: scripts/release/release-check.sh stg after --run ${FROM_STG}"
  elif ! python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get("passed") and d.get("env")=="stg" else 1)' "${ledger}"; then
    refuse "the release-check of ${FROM_STG} did not pass ($(tr -d '\n' <"${ledger}"))"
  else
    echo "release-check of ${FROM_STG}: passed ($(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["checked_at"], "diff", d["diff"])' "${ledger}"))"
  fi
  step_end

  step "generate the PROD pinned spec"
  PINNED_SPEC="${OUT_DIR}/prod-pinned.json"
  if "${RELEASE_DIR}/prod-pinned-from-stg.sh" "${FROM_STG}" -o "${PINNED_SPEC}" 2>"${OUT_DIR}/pinned.log"; then
    grep '^clone-' "${OUT_DIR}/pinned.log" >"${OUT_DIR}/stg-commits.txt" || true
    sed 's/^/  /' "${OUT_DIR}/stg-commits.txt"
    echo "  -> ${PINNED_SPEC}"
    STG_CORE="$(awk '$1 == "clone-core" { print $2 }' "${OUT_DIR}/stg-commits.txt")"
  else
    cat "${OUT_DIR}/pinned.log" >&2
    refuse "could not generate the pinned spec from ${FROM_STG}"
  fi
  step_end
fi

step "one-off DB steps due before the ${ENV_NAME} deliver"
db_steps_gate before
step_end

step "before snapshot (${ENV_NAME})"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  would "${RELEASE_DIR}/release-check.sh" "${ENV_NAME}" before --dir "${OUT_DIR}"
else
  "${RELEASE_DIR}/release-check.sh" "${ENV_NAME}" before --dir "${OUT_DIR}"
fi
step_end

case "${ENV_NAME}" in
  stg)
    step "create the bifrost-deliver-stg run (revision main)"
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      would kubectl -n "${CICD_NAMESPACE}" create -f "${STG_TEMPLATE}" -o name
    else
      deliver_free
      RUN_NAME="$(kubectl -n "${CICD_NAMESPACE}" create -f "${STG_TEMPLATE}" -o name)"
      RUN_NAME="${RUN_NAME##*/}"
      echo "created ${RUN_NAME}"
    fi
    step_end ;;
  prod)
    step "create the PROD pinned run"
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      would kubectl -n "${CICD_NAMESPACE}" create --dry-run=server -f "${PINNED_SPEC}" -o name
      would kubectl -n "${CICD_NAMESPACE}" create -f "${PINNED_SPEC}" -o name
    else
      kubectl -n "${CICD_NAMESPACE}" create --dry-run=server -f "${PINNED_SPEC}" -o name >/dev/null
      deliver_free
      RUN_NAME="$(kubectl -n "${CICD_NAMESPACE}" create -f "${PINNED_SPEC}" -o name)"
      RUN_NAME="${RUN_NAME##*/}"
      echo "created ${RUN_NAME}"
    fi
    step_end ;;
  dev)
    step "DEV images :stg -> :dev (backend + frontend) and restart"
    STG_CORE="$("${RELEASE_TOOL[@]}" core-sha stg)"
    echo "STG runs core ${STG_CORE}; DEV should after the copy"
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      would make -C "${INFRA_ROOT}" dev-sync-backend-images RESTART=1
    else
      make -C "${INFRA_ROOT}" dev-sync-backend-images RESTART=1 | tee "${OUT_DIR}/dev-sync.out" || {
        step_end; summary; echo "dev-sync-backend-images failed (see above)" >&2; exit 1
      }
    fi
    step_end ;;
esac

if [[ "${ENV_NAME}" != "dev" ]]; then
  step "wait for the run"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    would "${RELEASE_TOOL[@]}" wait "<created run>" --timeout "${TIMEOUT}"
  else
    rc=0
    # pipefail: rc is wait's status (tee only copies the output)
    "${RELEASE_TOOL[@]}" wait "${RUN_NAME}" --timeout "${TIMEOUT}" | tee "${OUT_DIR}/timings.txt" || rc=$?
    if [[ "${rc}" -ne 0 ]]; then
      step_end
      summary
      [[ "${rc}" -eq 3 ]] && exit 3
      echo "the run failed: see kubectl -n ${CICD_NAMESPACE} describe pipelinerun ${RUN_NAME}" >&2
      exit 1
    fi
  fi
  step_end
fi

step "after-check (${ENV_NAME})"
if [[ "${ENV_NAME}" == "dev" ]]; then
  after=("${RELEASE_DIR}/release-check.sh" dev after --expect-core-sha "${STG_CORE}" "${CHECK_ARGS[@]}")
else
  after=("${RELEASE_DIR}/release-check.sh" "${ENV_NAME}" after --run "${RUN_NAME:-<created run>}" "${CHECK_ARGS[@]}")
fi
check_rc=0
if [[ "${DRY_RUN}" -eq 1 ]]; then
  would "${after[@]}"
else
  "${after[@]}" || check_rc=$?
  if [[ "${ENV_NAME}" == "prod" ]]; then
    # PROD must have cloned exactly what STG did.
    if ! diff <("${RELEASE_TOOL[@]}" clone-commits "${RUN_NAME}" | sort) <(sort "${OUT_DIR}/stg-commits.txt"); then
      echo "!! ${RUN_NAME} cloned other commits than ${FROM_STG}"
      check_rc=1
    fi
  fi
fi
step_end

if [[ "${check_rc}" -ne 0 ]]; then
  summary
  echo "after-check FAILED — read ${OUT_DIR}; the Owner decides between a fix-forward and a rollback" >&2
  exit 1
fi
RESULT="passed"

step "after-deliver DB steps and next steps"
db_steps_gate after
case "${ENV_NAME}" in
  stg)
    echo "next: $0 prod --from-stg ${RUN_NAME:-<this STG run>}$([[ ${#ALLOW[@]} -gt 0 ]] && printf ' %s' "${ALLOW[@]}")" ;;
  prod)
    core_sha="${STG_CORE}"
    if [[ "${DRY_RUN}" -eq 0 ]]; then core_sha="$(rel_clone_core_sha "${RUN_NAME}")"; fi
    echo "core tag (dry-run of scripts/release/tag_core_release.sh ${core_sha}):"
    "${RELEASE_DIR}/tag_core_release.sh" "${core_sha}" | sed 's/^/  /' || echo "  (tag dry-run failed: see above)"
    echo "next (unless it says nothing to do): bash ${RELEASE_DIR}/tag_core_release.sh --push ${core_sha}"
    echo "then: $0 dev     (DEV :dev images, backend and frontend, follow STG)" ;;
  dev)
    echo "after the copy DEV runs the :stg images (core ${STG_CORE}) and the :stg frontend." ;;
esac
step_end

summary
if [[ "${DRY_RUN}" -eq 1 && "${REFUSALS}" -gt 0 ]]; then
  echo "dry-run: ${REFUSALS} precondition(s) would stop this release"
  exit 2
fi
