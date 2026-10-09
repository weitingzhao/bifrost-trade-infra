#!/usr/bin/env bash
# One entry for a Trade release (TD-84, LANE-W33C): STG from main, PROD pinned to an STG run, DEV catch-up.
#
#   release.sh stg  [options]                    bifrost-deliver-stg (revision main)
#   release.sh prod --from-stg <run> [options]   bifrost-deliver-prod at that STG run's six commits
#   release.sh dev  [options]                    make dev-sync-backend-images RESTART=1 (:stg -> :dev, backend + frontend)
#   release.sh window [--clear]                  show the release window (exit 1 while one is open)
#   release.sh hold --what <repo>[,<repo>...]    hold that same window until this process exits
#   release.sh db-steps [<env>]                  list one-off DB steps and their state
#   release.sh db-done <env> <step-id>           record that the Owner ran a step
#
# options: --dry-run         run the read-only checks, print every platform call, change nothing
#          --allow <file>    expected changes for the after-check diff (repeatable; see expected.d/)
#          --probes <file>   extra probes for the after-check (repeatable)
#          --what <repos>    comma-separated repo names in the window (default: the Trade repos)
#          --allow-red <why> ship stg/prod even if a SHA's CI is red or missing (Owner)
#          --who <name>      who releases (default $BIFROST_RELEASE_WHO, else user@host)
#          --timeout <s>     how long to wait for the run (default 3600)
#
# Research and the plugins use this same window. `what` is the repo list.
# `hold` writes ConfigMap cicd/bifrost-release-window through
# PUT /api/v1/delivery/release-window (ttl 5 minutes, renewed each minute).
# deliver-research, the Dagster build, and the plugin build pipelines read
# that ConfigMap as their first task. platform-api start_pipeline_run refuses
# unless the caller's `who` is the holder. stg/prod sync Gitea through
# POST /api/v1/delivery/mirrors/sync, then refuse unless each shipped SHA has
# a Succeeded ci-* run (--allow-red <reason> overrides, and the reason is logged).
#
# Steps: open the release window (refuses if one is open) -> no bifrost-deliver-*
# run running or created in the last 2 minutes -> [prod: the STG run succeeded
# and its release-check passed; read the six clone SHAs] -> pending one-off DB
# steps stop the release (Owner's; see db-steps.d/README.md) -> before snapshot
# -> start the run -> wait -> after-check -> summary. The window closes on exit.
#
# Exit: 0 done, 1 a check or the run failed, 2 usage / refused before starting, 3 waiting on
# the Owner (DB steps, or a PROD approval) or the run outlived --timeout (it is still running).
set -euo pipefail
# shellcheck source=scripts/release/lib.sh
source "$(dirname "$0")/lib.sh"

release_usage() { sed -n '2,36p' "$0" | sed 's/^# \{0,1\}//'; }

# The window lives in ConfigMap cicd/bifrost-release-window. The local file is only
# migrated once, then renamed. Pipelines read who and what from that ConfigMap.
WINDOW="${RELEASE_HOME}/window.json"
WINDOW_CM="bifrost-release-window"
TRADE_WHAT="bifrost-trade-core,bifrost-trade-api,bifrost-trade-worker,bifrost-trade-frontend,bifrost-trade-infra"
DONE_FILE="${RELEASE_HOME}/db-steps.done"
DB_STEPS_DIR="${BIFROST_DB_STEPS_DIR:-${RELEASE_DIR}/db-steps.d}"
PLATFORM_API="${PLATFORM_API:-http://192.168.10.100:30876}"
ENV_FILE="${ENV_FILE:-${INFRA_ROOT}/.env}"
WINDOW_TTL_MINUTES="${WINDOW_TTL_MINUTES:-5}"
WINDOW_RENEW_SECONDS="${WINDOW_RENEW_SECONDS:-60}"
WINDOW_OWNED=0
WINDOW_RENEW_PID=""
PLATFORM_HTTP=""
PLATFORM_BODY=""

# ── platform calls (token stays in a mode-600 curl config) ──────────────────

read_token() {
  local key="$1" value="${!key:-}" line
  if [[ -z "${value}" && -f "${ENV_FILE}" ]]; then
    line="$(grep -E "^${key}=" "${ENV_FILE}" | tail -1 || true)"
    line="${line#*=}"
    line="${line%\"}"
    line="${line#\"}"
    value="${line}"
  fi
  if [[ -z "${value}" ]]; then
    return 1
  fi
  case "${value}" in
    *\"*|*$'\n'*|*$'\r'*) return 2 ;;
  esac
  printf '%s' "${value}"
}

require_token() {
  local key="$1" token rc=0
  token="$(read_token "${key}")" || rc=$?
  if [[ "${rc}" -eq 1 ]]; then
    rel_die "missing ${key} (environment or ${ENV_FILE})" 2
  fi
  if [[ "${rc}" -ne 0 ]]; then
    rel_die "${key} cannot be passed to curl safely" 2
  fi
  printf '%s' "${token}"
}

platform_send() {
  local method="$1" path="$2" body="${3:-}" role="${4:-operator}"
  local key token cfg resp rc=0
  PLATFORM_HTTP=""
  PLATFORM_BODY=""
  if [[ "${role}" == "viewer" ]]; then
    key=PLATFORM_PROD_VIEWER_TOKEN
  else
    key=PLATFORM_OPERATOR_TOKEN
  fi
  token="$(require_token "${key}")"
  cfg="$(mktemp)"
  local out
  out="$(mktemp)"
  chmod 600 "${cfg}" "${out}"
  {
    printf 'header = "Authorization: Bearer %s"\n' "${token}"
    printf 'header = "X-Bifrost-Session: %s"\n' "${WHO:-release}"
    printf 'header = "Content-Type: application/json"\n'
    printf 'url = "%s%s"\n' "${PLATFORM_API%/}" "${path}"
    printf 'request = "%s"\n' "${method}"
    printf 'silent\nshow-error\n'
    printf 'output = "%s"\n' "${out}"
  } >"${cfg}"
  if [[ -n "${body}" ]]; then
    PLATFORM_HTTP="$(curl --config "${cfg}" --write-out '%{http_code}' --data-binary @- <<<"${body}")" || rc=$?
  else
    PLATFORM_HTTP="$(curl --config "${cfg}" --write-out '%{http_code}')" || rc=$?
  fi
  PLATFORM_BODY="$(cat "${out}" 2>/dev/null || true)"
  rm -f "${cfg}" "${out}"
  if [[ "${rc}" -ne 0 ]]; then
    echo "platform ${method} ${path} failed" >&2
    return 1
  fi
  if [[ ! "${PLATFORM_HTTP}" =~ ^2 ]]; then
    echo "platform ${method} ${path} -> HTTP ${PLATFORM_HTTP}" >&2
    printf '%s\n' "${PLATFORM_BODY}" | python3 -c 'import json,sys
raw=sys.stdin.read()
try:
    doc=json.loads(raw)
except Exception:
    sys.stderr.write(raw[:400]+"\n"); raise SystemExit
err=doc.get("error") or doc.get("message") or ""
if err:
    sys.stderr.write(str(err)+"\n")
' >&2 || true
    return 1
  fi
  printf '%s' "${PLATFORM_BODY}"
}

platform_preview() {
  echo "[dry-run] $1 $2"
  [[ -z "${3:-}" ]] || printf '%s\n' "$3"
}

json_field() {
  python3 -c 'import json,sys
doc=json.loads(sys.stdin.read() or "{}")
cur=doc
for part in sys.argv[1].split("."):
    if isinstance(cur, dict):
        cur=cur.get(part)
    else:
        cur=None
        break
if cur is None:
    cur=""
print(cur)
' "$1"
}

# ── window ───────────────────────────────────────────────────────────────────

window_show() {
  if [[ "${DRY_RUN:-0}" -eq 1 ]] && ! read_token PLATFORM_PROD_VIEWER_TOKEN >/dev/null; then
    platform_preview GET /api/v1/delivery/release-window
    return 0
  fi
  local body
  body="$(platform_send GET /api/v1/delivery/release-window "" viewer)" || return 1
  python3 -c 'import json,sys
doc=json.loads(sys.argv[1])
if not doc.get("open"):
    print("no release window open (ConfigMap cicd/bifrost-release-window)")
    sys.exit(0)
w=doc.get("window") or {}
print("release window OPEN (ConfigMap cicd/bifrost-release-window):")
print("  who=%s what=%s env=%s started_at=%s expires_at=%s" % (
    w.get("who",""), w.get("what",""), w.get("env",""), w.get("started_at",""), w.get("expires_at","")))
sys.exit(1)
' "${body}"
}

window_put() {
  local what="$1" who="$2" reason="$3" env="$4"
  local body
  body="$(python3 -c 'import json,sys; print(json.dumps({"what":sys.argv[1],"who":sys.argv[2],"reason":sys.argv[3],"env":sys.argv[4],"ttl_minutes":int(sys.argv[5])}))' \
    "${what}" "${who}" "${reason}" "${env}" "${WINDOW_TTL_MINUTES}")"
  if [[ "${DRY_RUN:-0}" -eq 1 ]]; then
    platform_preview PUT /api/v1/delivery/release-window "${body}"
    return 0
  fi
  platform_send PUT /api/v1/delivery/release-window "${body}" operator >/dev/null
}

window_delete() {
  local body
  body="$(python3 -c 'import json,sys; print(json.dumps({"who":sys.argv[1]}))' "${WHO}")"
  if [[ "${DRY_RUN:-0}" -eq 1 ]]; then
    platform_preview DELETE /api/v1/delivery/release-window "${body}"
    return 0
  fi
  platform_send DELETE /api/v1/delivery/release-window "${body}" operator >/dev/null
}

window_migrate_local() {
  [[ -f "${WINDOW}" ]] || return 0
  local pid host who what reason
  pid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("pid",""))' "${WINDOW}" 2>/dev/null || true)"
  host="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("host",""))' "${WINDOW}" 2>/dev/null || true)"
  if [[ "${host}" == "$(hostname -s)" && -n "${pid}" ]] && ! kill -0 "${pid}" 2>/dev/null; then
    mv "${WINDOW}" "${WINDOW}.migrated"
    echo "window: stale local file not republished (${WINDOW}.migrated)" >&2
    return 0
  fi
  if [[ "${DRY_RUN:-0}" -eq 0 ]] && window_show; then
    :
  else
    echo "window: local ${WINDOW} left in place; the cluster window is already open or could not be read" >&2
    return 0
  fi
  who="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("who",""))' "${WINDOW}")"
  what="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("what",""))' "${WINDOW}")"
  reason="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("reason") or json.load(open(sys.argv[1])).get("env") or "hold")' "${WINDOW}")"
  if [[ -z "${who}" || -z "${what}" ]]; then
    echo "window: local ${WINDOW} has no who/what; left in place" >&2
    return 0
  fi
  echo "window: one attempt to move the local file onto the platform"
  window_put "${what}" "${who}" "${reason}" "hold" || {
    echo "window: could not move ${WINDOW}; left in place" >&2
    return 0
  }
  mv "${WINDOW}" "${WINDOW}.migrated"
  echo "window: local file moved (${WINDOW}.migrated)"
}

window_renew_loop() {
  while true; do
    sleep "${WINDOW_RENEW_SECONDS}"
    window_put "${WHAT}" "${WHO}" "${WINDOW_REASON:-hold}" "${ENV_NAME}" || echo "window: renew failed" >&2
  done
}

window_close() {
  if [[ -n "${WINDOW_RENEW_PID}" ]]; then
    kill "${WINDOW_RENEW_PID}" 2>/dev/null || true
    wait "${WINDOW_RENEW_PID}" 2>/dev/null || true
    WINDOW_RENEW_PID=""
  fi
  if [[ "${WINDOW_OWNED}" -eq 1 ]]; then
    window_delete || echo "window: release failed" >&2
    WINDOW_OWNED=0
  fi
}

window_open() {
  mkdir -p "${RELEASE_HOME}"
  window_migrate_local
  window_put "${WHAT}" "${WHO}" "${WINDOW_REASON:-${ENV_NAME}}" "${ENV_NAME}" || rel_die "REFUSED: another release holds the window" 2
  if [[ "${DRY_RUN:-0}" -eq 1 ]]; then
    return 0
  fi
  WINDOW_OWNED=1
  trap window_close EXIT
  trap 'window_close; exit 130' INT
  trap 'window_close; exit 143' TERM
  window_renew_loop &
  WINDOW_RENEW_PID=$!
}

window_clear() {
  WHO="${BIFROST_RELEASE_WHO:-${USER}@$(hostname -s)}"
  local body
  body="$(python3 -c 'import json,sys; print(json.dumps({"action":"release_window_release","reason":"clear release window","params":{"who":sys.argv[1],"force":True}}))' "${WHO}")"
  if [[ "${DRY_RUN:-0}" -eq 1 ]]; then
    platform_preview POST /api/v1/approvals "${body}"
    return 0
  fi
  local resp id
  resp="$(platform_send POST /api/v1/approvals "${body}" operator)" || rel_die "could not ask to clear the window" 1
  id="$(printf '%s' "${resp}" | json_field id)"
  echo "approval ${id}: Owner approves release_window_release, then the window is cleared"
}

# ── helpers ──────────────────────────────────────────────────────────────────

REFUSALS=0
refuse() {
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

ci_pairs_from_origin() {
  local root repo sha
  root="$(cd "${INFRA_ROOT}/.." && pwd)"
  for repo in bifrost-trade-core bifrost-trade-api bifrost-trade-worker bifrost-trade-frontend; do
    sha="$(git -C "${root}/${repo}" rev-parse origin/main 2>/dev/null || true)"
    [[ "${sha}" =~ ^[0-9a-f]{40}$ ]] || rel_die "${repo}: origin/main is not a 40-char SHA (git fetch origin in that checkout first)" 2
    printf '%s=%s\n' "${repo}" "${sha}"
  done
}

ci_pairs_from_stg_commits() {
  local task sha repo
  [[ -f "${OUT_DIR}/stg-commits.txt" ]] || rel_die "STG clone SHAs are missing; cannot check CI" 2
  while read -r task sha _; do
    case "${task}" in
      clone-core) repo=bifrost-trade-core ;;
      clone-api) repo=bifrost-trade-api ;;
      clone-worker) repo=bifrost-trade-worker ;;
      clone-frontend) repo=bifrost-trade-frontend ;;
      *) continue ;;
    esac
    [[ "${sha}" =~ ^[0-9a-f]{40}$ ]] || rel_die "${task} SHA is not 40 hex chars (got '${sha}')" 2
    printf '%s=%s\n' "${repo}" "${sha}"
  done <"${OUT_DIR}/stg-commits.txt"
}

sync_mirrors() {
  local body
  body="$(python3 -c 'import json,sys
pairs=[]
for line in sys.stdin:
    line=line.strip()
    if not line or "=" not in line:
        continue
    repo, sha = line.split("=", 1)
    pairs.append((repo, sha))
print(json.dumps({"repos":[r for r,_ in pairs], "commits":{r:s for r,s in pairs}}))
' <<<"$(printf '%s\n' "$@")")"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    platform_preview POST /api/v1/delivery/mirrors/sync "${body}"
    return 0
  fi
  local resp
  resp="$(platform_send POST /api/v1/delivery/mirrors/sync "${body}" operator)" || rel_die "mirror sync failed" 1
  printf '%s' "${resp}" | python3 -c 'import json,sys
doc=json.loads(sys.stdin.read())
bad=[r.get("repo","?") for r in doc.get("repos") or [] if not r.get("present")]
if not doc.get("ok") or bad:
    sys.stderr.write("mirror sync missing: %s\n" % ", ".join(bad or ["unknown"]))
    sys.exit(1)
'
}

wait_for_ci() {
  local runs_py="${OUT_DIR}/ci-python.json" runs_fe="${OUT_DIR}/ci-frontend.json"
  local -a pairs=()
  local line deadline code
  while IFS= read -r line; do
    [[ -n "${line}" ]] && pairs+=("${line}")
  done
  [[ ${#pairs[@]} -gt 0 ]] || rel_die "no repo=sha pairs for the CI gate" 2
  if [[ "${BIFROST_RELEASE_MIRROR:-1}" == "1" ]]; then
    echo "syncing Gitea mirrors so CI can see these SHAs"
    sync_mirrors "${pairs[@]}"
  else
    echo "mirror sync skipped (BIFROST_RELEASE_MIRROR != 1)"
  fi
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[dry-run] would require a Succeeded ci-* run for each SHA"
    [[ -n "${ALLOW_RED}" ]] && echo "[dry-run] --allow-red ${ALLOW_RED}"
    return 0
  fi
  deadline=$((SECONDS + ${BIFROST_RELEASE_CI_WAIT:-900}))
  while true; do
    kubectl -n "${CICD_NAMESPACE}" get pipelineruns -l tekton.dev/pipeline=bifrost-ci-python -o json >"${runs_py}"
    kubectl -n "${CICD_NAMESPACE}" get pipelineruns -l tekton.dev/pipeline=bifrost-ci-frontend -o json >"${runs_fe}"
    code=0
    python3 "${RELEASE_DIR}/ci_gate.py" --runs "${runs_py}" --runs "${runs_fe}" \
      --allow-red "${ALLOW_RED:-}" "${pairs[@]}" || code=$?
    if [[ "${code}" -eq 0 ]]; then
      return 0
    fi
    if [[ "${code}" -eq 1 ]]; then
      refuse "CI failed for a SHA this release ships (see above). Re-run with --allow-red <reason> if the Owner accepts it"
      return 0
    fi
    if [[ "${SECONDS}" -ge "${deadline}" ]]; then
      refuse "CI did not succeed within ${BIFROST_RELEASE_CI_WAIT:-900}s. Re-run with --allow-red <reason> if the Owner accepts the gap"
      return 0
    fi
    echo "CI has not finished; waiting 20s"
    sleep 20
  done
}

post_owner_commands() {
  local posted=0 id cmd body resp
  id=""
  while IFS= read -r line || [[ -n "${line}" ]]; do
    if [[ "${line}" == "── "* ]]; then
      id="${line#── }"
      id="${id%% *}"
      continue
    fi
    if [[ "${line}" =~ ^commit:[[:space:]]*(.+)$ ]]; then
      cmd="${BASH_REMATCH[1]}"
      body="$(python3 -c 'import json,sys; print(json.dumps({"action":"owner_run_command","reason":sys.argv[1],"params":{"command":sys.argv[2],"reason":sys.argv[1]}}))' "${id}" "${cmd}")"
      if [[ "${DRY_RUN}" -eq 1 ]]; then
        platform_preview POST /api/v1/approvals "${body}"
        posted=1
        continue
      fi
      resp="$(platform_send POST /api/v1/approvals "${body}" operator)" || {
        echo "could not create the approval; run this yourself:" >&2
        printf '%s\n' "${cmd}" >&2
        exit 1
      }
      echo "approval $(printf '%s' "${resp}" | json_field id): Owner approves, then bash ${INFRA_ROOT}/scripts/owner/owner-run.sh <id>"
      posted=1
    fi
  done <<<"$1"
  if [[ "${posted}" -eq 0 ]]; then
    return 1
  fi
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "WOULD STOP here for the DB steps above."
    REFUSALS=$((REFUSALS + 1))
    return 0
  fi
  exit 3
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
  if [[ "${ENV_NAME}" == "prod" ]]; then
    post_owner_commands "${out}" && return 0
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

run_name_from() {
  python3 -c 'import json,sys
doc=json.loads(sys.stdin.read() or "{}")
run=(doc.get("run") or {}).get("name") or ""
if not run:
    target=str(doc.get("target") or "")
    run=target.rsplit("/",1)[-1] if "/" in target else ""
print(run)
'
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

start_stg_run() {
  local body resp
  body="$(python3 -c 'import json,sys; print(json.dumps({"revision":"main","who":sys.argv[1]}))' "${WHO}")"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    platform_preview POST /api/v1/delivery/pipelines/bifrost-deliver-stg/runs "${body}"
    return 0
  fi
  deliver_free
  resp="$(platform_send POST /api/v1/delivery/pipelines/bifrost-deliver-stg/runs "${body}" operator)" || rel_die "could not start the STG run" 1
  RUN_NAME="$(printf '%s' "${resp}" | run_name_from)"
  [[ -n "${RUN_NAME}" ]] || rel_die "STG run response has no run name" 1
  echo "created ${RUN_NAME}"
}

start_prod_run() {
  local sha_file="$1" body resp id status deadline core
  core="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["coreRevision"])' "${sha_file}")"
  body="$(python3 -c 'import json,sys
shas=json.load(open(sys.argv[1]))
shas["revision"]=shas["coreRevision"]
print(json.dumps({"action":"start_pipeline_run","reason":"prod pinned from "+sys.argv[2],"params":{"name":"bifrost-deliver-prod","revision":"main","who":sys.argv[3],"params":shas}}))' \
    "${sha_file}" "${FROM_STG}" "${WHO}")"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    platform_preview POST /api/v1/approvals "${body}"
    echo "[dry-run] would poll GET /api/v1/approvals/<id> until the Owner approves"
    return 0
  fi
  resp="$(platform_send POST /api/v1/approvals "${body}" operator)" || rel_die "could not ask to start the PROD run" 1
  id="$(printf '%s' "${resp}" | json_field id)"
  [[ -n "${id}" ]] || rel_die "PROD approval response has no id" 1
  echo "waiting for Owner to approve ${id} (start_pipeline_run bifrost-deliver-prod, core ${core})"
  deadline=$((SECONDS + TIMEOUT))
  while true; do
    resp="$(platform_send GET "/api/v1/approvals/${id}" "" viewer)" || rel_die "could not read approval ${id}" 1
    status="$(printf '%s' "${resp}" | json_field status)"
    case "${status}" in
      executed)
        RUN_NAME="$(printf '%s' "${resp}" | python3 -c 'import json,sys
doc=json.loads(sys.stdin.read())
result=doc.get("result") or {}
run=(result.get("run") or {}).get("name") or ""
if not run:
    target=str(result.get("target") or "")
    run=target.rsplit("/",1)[-1] if "/" in target else ""
print(run)
')"
        [[ -n "${RUN_NAME}" ]] || rel_die "approval ${id} executed without a run name" 1
        echo "created ${RUN_NAME}"
        return 0
        ;;
      failed|rejected|expired)
        rel_die "approval ${id} ${status}" 1
        ;;
    esac
    if [[ "${SECONDS}" -ge "${deadline}" ]]; then
      echo "still waiting on Owner approval ${id}" >&2
      exit 3
    fi
    sleep 15
  done
}

# ── the release ──────────────────────────────────────────────────────────────

case "${1:-}" in
  window)
    shift
    DRY_RUN=0
    if [[ "${1:-}" == "--clear" ]]; then window_clear; exit $?; fi
    window_show; exit $? ;;
  hold)
    shift
    WHAT=""
    WHO="${BIFROST_RELEASE_WHO:-${USER}@$(hostname -s)}"
    DRY_RUN=0
    ENV_NAME="hold"
    WINDOW_REASON="hold"
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --what) WHAT="${2:?--what needs a repo}"; shift 2 ;;
        --who) WHO="${2:?}"; shift 2 ;;
        *) rel_die "unknown argument: $1" ;;
      esac
    done
    [[ -n "${WHAT}" ]] || rel_die "hold needs --what <repo>[,<repo>...] (repo names, no spaces)"
    python3 -c 'import re,sys; sys.exit(0 if re.fullmatch(r"[a-z0-9-]+(,[a-z0-9-]+)*", sys.argv[1]) else 1)' "${WHAT}" \
      || rel_die "--what must be comma-separated repo names (got '${WHAT}')"
    window_open
    echo "holding ConfigMap ${CICD_NAMESPACE}/${WINDOW_CM} for ${WHAT} as ${WHO} (ttl ${WINDOW_TTL_MINUTES}m, renew every ${WINDOW_RENEW_SECONDS}s)"
    echo "start_pipeline_run for that repo must send who=${WHO}. Ctrl-C closes the window."
    while true; do sleep 3600; done
    ;;
  db-steps) shift; cmd_db_steps "$@"; exit 0 ;;
  db-done) shift; cmd_db_done "$@"; exit 0 ;;
  dev|stg|prod) ENV_NAME="$1"; shift ;;
  -h|--help|"") release_usage; exit 0 ;;
  *) release_usage >&2; exit 2 ;;
esac

DRY_RUN=0 FROM_STG="" WHAT="" ALLOW_RED="" WHO="${BIFROST_RELEASE_WHO:-${USER}@$(hostname -s)}" TIMEOUT=3600
ALLOW=() PROBES=()
WINDOW_REASON="${ENV_NAME}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --from-stg) FROM_STG="${2:?--from-stg needs a run name}"; shift 2 ;;
    --allow) ALLOW+=(--allow "${2:?}"); shift 2 ;;
    --probes) PROBES+=(--probes "${2:?}"); shift 2 ;;
    --what) WHAT="${2:?}"; shift 2 ;;
    --allow-red) ALLOW_RED="${2:?--allow-red needs a reason}"; shift 2 ;;
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
WHAT="${WHAT:-${TRADE_WHAT}}"
python3 -c 'import re,sys; sys.exit(0 if re.fullmatch(r"[a-z0-9-]+(,[a-z0-9-]+)*", sys.argv[1]) else 1)' "${WHAT}" \
  || rel_die "--what must be comma-separated repo names (got '${WHAT}')"
if [[ "${ENV_NAME}" != "dev" || "${DRY_RUN}" -eq 0 ]]; then
  rel_require_kubeconfig
fi

OUT_DIR="${RELEASE_SNAP_BASE}/$(date +%F)/${ENV_NAME}-$(date +%H%M%S)"
mkdir -p "${OUT_DIR}"
RUN_NAME="" RESULT="failed"
CHECK_ARGS=(--dir "${OUT_DIR}" ${ALLOW[@]+"${ALLOW[@]}"} ${PROBES[@]+"${PROBES[@]}"})

echo "release ${ENV_NAME}: ${WHAT} — by ${WHO}$([[ "${DRY_RUN}" -eq 1 ]] && echo ' (DRY RUN: nothing will be created)')"

step "release window"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  window_show || refuse "another release holds the window"
  window_put "${WHAT}" "${WHO}" "${WINDOW_REASON}" "${ENV_NAME}"
else
  window_open
  echo "opened ConfigMap ${CICD_NAMESPACE}/${WINDOW_CM}"
fi
step_end

if [[ "${ENV_NAME}" == "stg" ]]; then
  step "Gitea mirror and CI for origin/main"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[dry-run] would sync Gitea mirrors and require a Succeeded ci-* run for origin/main of core, api, worker, frontend"
    [[ -n "${ALLOW_RED}" ]] && echo "[dry-run] --allow-red ${ALLOW_RED}"
    platform_preview POST /api/v1/delivery/mirrors/sync
  else
    wait_for_ci < <(ci_pairs_from_origin)
  fi
  step_end
fi

step "no deliver run in flight"
deliver_free
step_end

PINNED_SHA="" STG_CORE=""
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

  step "read the six STG clone SHAs"
  PINNED_SHA="${OUT_DIR}/prod-shas.json"
  if "${RELEASE_DIR}/prod-pinned-from-stg.sh" "${FROM_STG}" -o "${PINNED_SHA}" 2>"${OUT_DIR}/pinned.log"; then
    grep '^clone-' "${OUT_DIR}/pinned.log" >"${OUT_DIR}/stg-commits.txt" || true
    sed 's/^/  /' "${OUT_DIR}/stg-commits.txt"
    echo "  -> ${PINNED_SHA}"
    STG_CORE="$(awk '$1 == "clone-core" { print $2 }' "${OUT_DIR}/stg-commits.txt")"
  else
    cat "${OUT_DIR}/pinned.log" >&2
    refuse "could not read the six SHAs from ${FROM_STG}"
  fi
  step_end

  step "Gitea mirror and CI for the STG SHAs"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[dry-run] would sync Gitea mirrors and require a Succeeded ci-* run for each SHA in ${OUT_DIR}/stg-commits.txt"
    [[ -n "${ALLOW_RED}" ]] && echo "[dry-run] --allow-red ${ALLOW_RED}"
    platform_preview POST /api/v1/delivery/mirrors/sync
  else
    wait_for_ci < <(ci_pairs_from_stg_commits)
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
    step "start bifrost-deliver-stg (revision main)"
    start_stg_run
    step_end ;;
  prod)
    step "ask for the PROD pinned run"
    if [[ -n "${PINNED_SHA}" && -f "${PINNED_SHA}" ]]; then
      start_prod_run "${PINNED_SHA}"
    else
      refuse "the six SHAs were not written"
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
