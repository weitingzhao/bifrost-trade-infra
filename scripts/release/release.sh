#!/usr/bin/env bash
# One entry for a Trade release (TD-84): STG from main, PROD pinned to an STG run, DEV catch-up.
#
#   release.sh stg  [options]                    bifrost-deliver-stg (revision main)
#   release.sh prod --from-stg <run> [options]   bifrost-deliver-prod-pinned-* at that STG run's commits
#   release.sh dev  [options]                    make dev-sync-backend-images RESTART=1 (:stg -> :dev, backend + frontend)
#   release.sh window [--clear]                  show the release window (exit 1 while one is open)
#   release.sh hold --what <repo>[,<repo>...]    hold that same window until this process exits
#   release.sh db-steps [<env>]                  list one-off DB steps and their state
#   release.sh db-done <env> <step-id>           record that the Owner ran a step
#   release.sh merge <repo> <sha> [options]      push <sha> to <repo> main: window, CI, policy (LANE-RP)
#   release.sh policy status                     the signed release policy in the cluster, and the freeze
#   release.sh policy sign [--days 7] [--key k]  Owner: sign a new policy, print the kubectl apply command
#   release.sh policy verify [--policy f --sig f] check a local policy.yaml + policy.sig
#   release.sh freeze --reason <r>               stop every new release (anyone may)
#   release.sh unfreeze [--key k]                Owner: lift the freeze with a signed text
#
# options: --dry-run         run the read-only checks, print every other command, change nothing
#          --allow <file>    expected changes for the after-check diff (repeatable; see expected.d/)
#          --probes <file>   extra probes for the after-check (repeatable)
#          --what <repos>    comma-separated repo names in the window (default: the Trade repos)
#          --allow-red <why> ship stg/prod even if a SHA's CI is red or missing (Owner)
#          --owner-approved <note>  the Owner approved this release outside the policy (not a freeze)
#          --who <name>      who releases (default $BIFROST_RELEASE_WHO, else user@host)
#          --timeout <s>     how long to wait for the run (default 3600)
#
# Release policy (LANE-RP): stg, prod, dev and merge read ConfigMaps cicd/bifrost-release-policy
# (policy.yaml + policy.sig, signed by the Owner) and cicd/bifrost-release-freeze before they
# create anything. A valid, unexpired policy that allows the release and whose path table no
# changed file hits auto-approves it ("auto-approved by <policy_id>" in the log). Otherwise the
# script exits 3 with the reasons and the sign command, unless --owner-approved is given.
# A freeze always exits 3. policy_check.py holds the rules; platform-api applies the same ones.
#
# Research and the plugins use this same window file. `what` is the repo list.
# `hold` publishes it to ConfigMap cicd/bifrost-release-window. deliver-research,
# the Dagster build, and the plugin build pipelines read that ConfigMap as their
# first task and refuse when it is missing or names another repo. platform-api
# start_pipeline_run also refuses unless the caller's `who` is the holder.
# stg/prod sync the Gitea mirrors, then refuse unless each shipped SHA has a
# Succeeded ci-* run (--allow-red <reason> overrides, and the reason is logged).
#
# Steps: open the release window (~/.bifrost-release/window.json; refuses if one is open) ->
# no bifrost-deliver-* run running or created in the last 2 minutes -> [prod: the STG run
# succeeded and its release-check passed; generate the pinned spec] -> the release policy and
# the freeze (exit 3 unless auto-approved or --owner-approved) -> pending one-off DB steps
# for this env stop the release (they are the Owner's, see db-steps.d/README.md) -> before
# snapshot -> create the run -> wait, with each TaskRun's duration -> after-check -> summary
# with timings and the next command. The window closes when the script exits, however it exits.
#
# Exit: 0 done, 1 a check or the run failed, 2 usage / refused before starting, 3 waiting on
# the Owner (DB steps, the release policy, a freeze) or the run outlived --timeout (it is still running).
set -euo pipefail
# shellcheck source=scripts/release/lib.sh
source "$(dirname "$0")/lib.sh"

release_usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; }

WINDOW="${RELEASE_HOME}/window.json"
WINDOW_CM="bifrost-release-window"
# `what` names the repos this window covers. Comma-separated, no spaces.
TRADE_WHAT="bifrost-trade-core,bifrost-trade-api,bifrost-trade-worker,bifrost-trade-frontend,bifrost-trade-infra"
DONE_FILE="${RELEASE_HOME}/db-steps.done"
DB_STEPS_DIR="${BIFROST_DB_STEPS_DIR:-${RELEASE_DIR}/db-steps.d}"
STG_TEMPLATE="${RELEASE_DIR}/pipelinerun-deliver-stg.json"
WORKSPACE_ROOT="${BIFROST_WORKSPACE_ROOT:-$(cd "${INFRA_ROOT}/.." && pwd)}"
POLICY_TOOL=(python3 "${RELEASE_DIR}/policy_check.py")
POLICY_CM="bifrost-release-policy"
FREEZE_CM="bifrost-release-freeze"
POLICY_DIR="${INFRA_ROOT}/agent-config/release-policy"
ALLOWED_SIGNERS="${BIFROST_RELEASE_ALLOWED_SIGNERS:-${POLICY_DIR}/allowed_signers}"
POLICY_PATHS="${POLICY_DIR}/paths.json"
POLICY_TEMPLATE="${INFRA_ROOT}/agent-config/work/release-approval/release-policy.draft.yaml"
POLICY_KEY="${BIFROST_RELEASE_KEY:-${HOME}/.ssh/bifrost_release_owner}"
FREEZE_SEEN="${RELEASE_HOME}/freeze-seen"
DEV_COMMITS="${RELEASE_HOME}/dev-commits.txt"
OWNER_APPROVED=""

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
  window_unpublish
  rm -f "${WINDOW}"
  echo "cleared"
}

window_publish() {
  # Mirror the local window into the cluster so Tekton and platform-api can see it.
  if [[ "${BIFROST_RELEASE_WINDOW_PUBLISH:-1}" != "1" ]]; then
    return 0
  fi
  if [[ ! -f "${KUBECONFIG:-}" ]]; then
    echo "window: no kubeconfig, not publishing ConfigMap ${WINDOW_CM}" >&2
    return 0
  fi
  kubectl -n "${CICD_NAMESPACE}" create configmap "${WINDOW_CM}" \
    --from-file=window.json="${WINDOW}" \
    --dry-run=client -o yaml | kubectl apply -f -
  echo "published ConfigMap ${CICD_NAMESPACE}/${WINDOW_CM}"
}

window_unpublish() {
  if [[ "${BIFROST_RELEASE_WINDOW_PUBLISH:-1}" != "1" ]]; then
    return 0
  fi
  if [[ ! -f "${KUBECONFIG:-}" ]]; then
    return 0
  fi
  kubectl -n "${CICD_NAMESPACE}" delete configmap "${WINDOW_CM}" --ignore-not-found >/dev/null || true
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
  trap 'window_close; exit 130' INT
  trap 'window_close; exit 143' TERM
  window_publish
}

window_close() {
  if [[ "${WINDOW_OWNED:-0}" -eq 1 ]]; then
    window_unpublish
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

# SHAs whose CI must be green before stg (origin/main) or prod (the STG clones).
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

# Reads repo=sha pairs on stdin. Syncs the Gitea mirrors, then waits until each
# SHA has a Succeeded ci-* run. --allow-red skips the refusal and logs the reason.
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
    "${INFRA_ROOT}/scripts/k3s/bootstrap-gitea-mirrors.sh"
  else
    echo "mirror sync skipped (BIFROST_RELEASE_MIRROR != 1)"
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

# ── release policy and freeze (LANE-RP) ──────────────────────────────────────

# kubectl get configmap -o json into $2. Missing or unreadable leaves an empty file,
# which policy_check.py reads as "no policy" / "frozen".
fetch_cm() {
  if ! kubectl -n "${CICD_NAMESPACE}" get configmap "$1" -o json >"$2" 2>"$2.err"; then
    grep -q NotFound "$2.err" || sed 's/^/  /' "$2.err" >&2
    : >"$2"
  fi
  rm -f "$2.err"
}

# repo=sha lines in $1 (deployed) and $2 (about to ship) -> repo=old..new, one per repo in $2.
# A repo with no deployed commit gets old=missing, which the check sends to the Owner.
policy_pairs() {
  python3 - "$1" "$2" <<'PY'
import sys

def load(path):
    out = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                repo, _, sha = line.strip().partition("=")
                if repo and sha:
                    out[repo] = sha
    except OSError:
        pass
    return out

old, new = load(sys.argv[1]), load(sys.argv[2])
for repo in sorted(new):
    print(f"{repo}={old.get(repo, 'missing')}..{new[repo]}")
PY
}

# $1 lane, $2 env, $3 run (optional), $4 output file: repo=sha of the newest matching release record.
deployed_commits() {
  local records="${OUT_DIR}/release-records.json"
  [[ -s "${records}" ]] || kubectl -n "${CICD_NAMESPACE}" get configmaps -l bifrost.io/release-record -o json >"${records}"
  "${POLICY_TOOL[@]}" deployed --records "${records}" --lane "$1" --env "$2" --run "${3:-}" >"$4" || : >"$4"
}

# repo=sha of origin/main for each repo named in $1, into $2.
origin_main_commits() {
  local repo sha
  : >"$2"
  while IFS='=' read -r repo _; do
    [[ -n "${repo}" ]] || continue
    sha="$(git -C "${WORKSPACE_ROOT}/${repo}" rev-parse origin/main 2>/dev/null || echo missing)"
    printf '%s=%s\n' "${repo}" "${sha}" >>"$2"
  done <"$1"
}

# policy_gate <allow name> <pairs file>: returns when the policy auto-approves (or the Owner
# approved outside it with --owner-approved); otherwise exits 3. A freeze always exits 3.
policy_gate() {
  local action="$1" pairs_file="$2" rc=0 p
  fetch_cm "${POLICY_CM}" "${OUT_DIR}/policy-cm.json"
  fetch_cm "${FREEZE_CM}" "${OUT_DIR}/freeze-cm.json"
  local -a args=(check --policy-cm "${OUT_DIR}/policy-cm.json" --freeze-cm "${OUT_DIR}/freeze-cm.json"
    --allowed-signers "${ALLOWED_SIGNERS}" --seen-file "${FREEZE_SEEN}" --action "${action}" --root "${WORKSPACE_ROOT}")
  while IFS= read -r p; do
    [[ -n "${p}" ]] && args+=(--pair "${p}")
  done <"${pairs_file}"
  [[ -n "${ALLOW_RED:-}" ]] && args+=(--block "--allow-red was used (${ALLOW_RED}); shipping a red or missing CI needs the Owner")
  [[ -n "${GATE_BLOCK:-}" ]] && args+=(--block "${GATE_BLOCK}")
  "${POLICY_TOOL[@]}" "${args[@]}" | tee "${OUT_DIR}/policy-check.txt" || rc=$?
  case "${rc}" in
    0) return 0 ;;
    3)
      if [[ -n "${OWNER_APPROVED}" ]]; then
        echo "Owner approved this release outside the policy: ${OWNER_APPROVED}"
        return 0
      fi ;;
    4) [[ -n "${OWNER_APPROVED}" ]] && echo "--owner-approved does not lift a freeze" ;;
    *) rel_die "policy check failed (exit ${rc}); see above" 2 ;;
  esac
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "WOULD WAIT ON THE OWNER (exit 3) for ${action}"
    REFUSALS=$((REFUSALS + 1))
    return 0
  fi
  exit 3
}

cmd_policy() {
  local sub="${1:-}" tmp rc=0
  shift || true
  case "${sub}" in
    status)
      rel_require_kubeconfig
      tmp="$(mktemp -d)"
      fetch_cm "${POLICY_CM}" "${tmp}/policy.json"
      fetch_cm "${FREEZE_CM}" "${tmp}/freeze.json"
      "${POLICY_TOOL[@]}" status --policy-cm "${tmp}/policy.json" --freeze-cm "${tmp}/freeze.json" \
        --allowed-signers "${ALLOWED_SIGNERS}" --seen-file "${FREEZE_SEEN}" || rc=$?
      rm -rf "${tmp}"
      return "${rc}" ;;
    verify)
      local policy="${RELEASE_HOME}/policy/current/policy.yaml" sig=""
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --policy) policy="${2:?}"; shift 2 ;;
          --sig) sig="${2:?}"; shift 2 ;;
          *) rel_die "unknown argument: $1" ;;
        esac
      done
      sig="${sig:-$(dirname "${policy}")/policy.sig}"
      [[ -f "${policy}" && -f "${sig}" ]] || rel_die "need ${policy} and ${sig} (release.sh policy sign writes them)"
      "${POLICY_TOOL[@]}" verify --policy "${policy}" --sig "${sig}" --allowed-signers "${ALLOWED_SIGNERS}" ;;
    sign)
      local days="" key="${POLICY_KEY}" id dir
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --days) days="${2:?}"; shift 2 ;;
          --key) key="${2:?}"; shift 2 ;;
          *) rel_die "unknown argument: $1" ;;
        esac
      done
      [[ -f "${key}" ]] || rel_die "no signing key at ${key} (generate it first: see the LANE-RP runbook)"
      mkdir -p "${RELEASE_HOME}/policy"
      tmp="$(mktemp -d "${RELEASE_HOME}/policy/new.XXXXXX")"
      "${POLICY_TOOL[@]}" render --template "${POLICY_TEMPLATE}" --paths "${POLICY_PATHS}" \
        ${days:+--days "${days}"} --out "${tmp}/policy.yaml" | tee "${tmp}/render.txt"
      id="$(awk '$1 == "policy_id" { print $2 }' "${tmp}/render.txt")"
      [[ -n "${id}" ]] || rel_die "render printed no policy_id"
      dir="${RELEASE_HOME}/policy/${id}"
      rm -rf "${dir}"
      mv "${tmp}" "${dir}"
      echo "signing ${dir}/policy.yaml with ${key} (ssh-keygen asks for the passphrase or Touch ID)"
      ssh-keygen -Y sign -f "${key}" -n bifrost-release-policy "${dir}/policy.yaml"
      mv "${dir}/policy.yaml.sig" "${dir}/policy.sig"
      "${POLICY_TOOL[@]}" verify --policy "${dir}/policy.yaml" --sig "${dir}/policy.sig" \
        --allowed-signers "${ALLOWED_SIGNERS}" || rel_die "the new signature does not verify against ${ALLOWED_SIGNERS}" 1
      ln -sfn "${dir}" "${RELEASE_HOME}/policy/current"
      echo
      echo "Apply it (Owner):"
      printf '  kubectl -n %s create configmap %s --from-file=policy.yaml=%q --from-file=policy.sig=%q --from-file=allowed_signers=%q --dry-run=client -o yaml | kubectl apply -f -\n' \
        "${CICD_NAMESPACE}" "${POLICY_CM}" "${dir}/policy.yaml" "${dir}/policy.sig" "${ALLOWED_SIGNERS}"
      echo "Then: $0 policy status" ;;
    *) rel_die "usage: $0 policy status | sign [--days N] [--key <path>] | verify [--policy f --sig f]" ;;
  esac
}

cmd_freeze() {
  local reason="" who="${BIFROST_RELEASE_WHO:-${USER}@$(hostname -s)}" at
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --reason) reason="${2:?--reason needs text}"; shift 2 ;;
      --who) who="${2:?}"; shift 2 ;;
      *) rel_die "unknown argument: $1" ;;
    esac
  done
  [[ -n "${reason}" ]] || rel_die "freeze needs --reason <text>"
  rel_require_kubeconfig
  at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  kubectl -n "${CICD_NAMESPACE}" create configmap "${FREEZE_CM}" \
    --from-literal=frozen=true --from-literal=reason="${reason}" \
    --from-literal=who="${who}" --from-literal=frozen_at="${at}" \
    --dry-run=client -o yaml | kubectl apply -f -
  mkdir -p "${RELEASE_HOME}"
  printf '%s\n' "${at}" >"${FREEZE_SEEN}"
  echo "frozen at ${at}: ${reason}. Lifting it needs the Owner: $0 unfreeze"
}

cmd_unfreeze() {
  local key="${POLICY_KEY}" who="${BIFROST_RELEASE_WHO:-${USER}@$(hostname -s)}" tmp state frozen_at reason
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --key) key="${2:?}"; shift 2 ;;
      --who) who="${2:?}"; shift 2 ;;
      *) rel_die "unknown argument: $1" ;;
    esac
  done
  rel_require_kubeconfig
  [[ -f "${key}" ]] || rel_die "no signing key at ${key}"
  tmp="$(mktemp -d)"
  fetch_cm "${FREEZE_CM}" "${tmp}/freeze.json"
  state="$(python3 -c 'import json,sys
t = open(sys.argv[1]).read()
d = (json.loads(t).get("data") or {}) if t.strip() else {}
print(d.get("frozen", ""), d.get("frozen_at", ""), sep="\t")' "${tmp}/freeze.json")"
  frozen_at="${state#*$'\t'}"
  if [[ "${state%%$'\t'*}" != "true" ]]; then
    rm -rf "${tmp}"
    echo "not frozen (ConfigMap ${CICD_NAMESPACE}/${FREEZE_CM} frozen='${state%%$'\t'*}')"
    return 0
  fi
  [[ -n "${frozen_at}" ]] || frozen_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  reason="$(python3 -c 'import json,sys; print((json.load(open(sys.argv[1])).get("data") or {}).get("reason", ""))' "${tmp}/freeze.json")"
  printf 'unfreeze frozen_at=%s at=%s by=%s\n' "${frozen_at}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${who}" >"${tmp}/unfreeze.txt"
  echo "signing the unfreeze with ${key} (ssh-keygen asks for the passphrase or Touch ID)"
  ssh-keygen -Y sign -f "${key}" -n bifrost-release-unfreeze "${tmp}/unfreeze.txt"
  ssh-keygen -Y verify -f "${ALLOWED_SIGNERS}" -I owner -n bifrost-release-unfreeze \
    -s "${tmp}/unfreeze.txt.sig" <"${tmp}/unfreeze.txt" >/dev/null \
    || rel_die "the unfreeze signature does not verify against ${ALLOWED_SIGNERS}" 1
  kubectl -n "${CICD_NAMESPACE}" create configmap "${FREEZE_CM}" \
    --from-literal=frozen=false --from-literal=frozen_at="${frozen_at}" \
    --from-literal=reason="${reason}" --from-literal=who="${who}" \
    --from-file=unfreeze.txt="${tmp}/unfreeze.txt" --from-file=unfreeze.sig="${tmp}/unfreeze.txt.sig" \
    --dry-run=client -o yaml | kubectl apply -f -
  rm -rf "${tmp}"
  echo "unfrozen (the freeze from ${frozen_at})"
}

cmd_merge() {
  [[ $# -ge 2 ]] || rel_die "usage: $0 merge <repo> <sha> [--owner-approved <note>] [--who <name>] [--dry-run]"
  local repo="$1" sha="$2" repo_dir base runs ci_rc=0
  shift 2
  DRY_RUN=0
  WHO="${BIFROST_RELEASE_WHO:-${USER}@$(hostname -s)}"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --owner-approved) OWNER_APPROVED="${2:?--owner-approved needs a note}"; shift 2 ;;
      --who) WHO="${2:?}"; shift 2 ;;
      --dry-run) DRY_RUN=1; shift ;;
      *) rel_die "unknown argument: $1" ;;
    esac
  done
  [[ "${repo}" =~ ^[a-z0-9-]+$ ]] || rel_die "repo must be a repo name (got '${repo}')"
  [[ "${sha}" =~ ^[0-9a-f]{40}$ ]] || rel_die "sha must be 40 lowercase hex chars (got '${sha}')"
  repo_dir="${WORKSPACE_ROOT}/${repo}"
  [[ -e "${repo_dir}/.git" ]] || rel_die "no checkout at ${repo_dir}"
  rel_require_kubeconfig
  git -C "${repo_dir}" fetch -q origin
  git -C "${repo_dir}" cat-file -e "${sha}^{commit}" 2>/dev/null || rel_die "${sha} is not in ${repo_dir}; push its branch and fetch first"
  base="$(git -C "${repo_dir}" rev-parse origin/main)"
  if [[ "${base}" == "${sha}" ]]; then
    echo "${repo} main is already ${sha}"
    return 0
  fi
  git -C "${repo_dir}" merge-base --is-ancestor "${base}" "${sha}" \
    || rel_die "${sha} is not a fast-forward of ${repo} origin/main (${base}); rebase it first"
  ENV_NAME="merge" WHAT="${repo}"
  OUT_DIR="${RELEASE_SNAP_BASE}/$(date +%F)/merge-${repo}-$(date +%H%M%S)"
  mkdir -p "${OUT_DIR}"
  echo "merge ${repo} ${base:0:12}..${sha:0:12} by ${WHO}$([[ "${DRY_RUN}" -eq 1 ]] && echo ' (DRY RUN: nothing will be pushed)')"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    window_show || refuse "another release holds the window"
  else
    window_open
  fi
  GATE_BLOCK=""
  if "${POLICY_TOOL[@]}" ci-repo --paths "${POLICY_PATHS}" "${repo}"; then
    runs="${OUT_DIR}/ci-runs"
    mkdir -p "${runs}"
    local p
    for p in bifrost-ci-python bifrost-ci-frontend bifrost-ci-platform; do
      kubectl -n "${CICD_NAMESPACE}" get pipelineruns -l "tekton.dev/pipeline=${p}" -o json >"${runs}/${p}.json"
    done
    python3 "${RELEASE_DIR}/ci_gate.py" --runs "${runs}/bifrost-ci-python.json" --runs "${runs}/bifrost-ci-frontend.json" \
      --runs "${runs}/bifrost-ci-platform.json" "${repo}=${sha}" || ci_rc=$?
    [[ "${ci_rc}" -eq 0 ]] || GATE_BLOCK="${repo} ${sha:0:12} has no Succeeded ci-* run (ci_gate exit ${ci_rc})"
  else
    echo "${repo} has no ci-* gate (not in ci_repos of ${POLICY_PATHS})"
  fi
  printf '%s=%s..%s\n' "${repo}" "${base}" "${sha}" >"${OUT_DIR}/pairs.txt"
  policy_gate merge-to-main "${OUT_DIR}/pairs.txt"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    would git -C "${repo_dir}" push origin "${sha}:refs/heads/main"
    [[ "${REFUSALS}" -eq 0 ]] || { echo "dry-run: ${REFUSALS} precondition(s) would stop this merge"; exit 2; }
    return 0
  fi
  git -C "${repo_dir}" push origin "${sha}:refs/heads/main"
  echo "pushed ${repo} main -> ${sha}"
}

# ── the release ──────────────────────────────────────────────────────────────

case "${1:-}" in
  window)
    shift
    if [[ "${1:-}" == "--clear" ]]; then window_clear; exit $?; fi
    window_show; exit $? ;;
  hold)
    shift
    WHAT=""
    WHO="${BIFROST_RELEASE_WHO:-${USER}@$(hostname -s)}"
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
    ENV_NAME="hold"
    rel_require_kubeconfig
    window_open
    echo "holding ${WINDOW} for ${WHAT} as ${WHO}"
    echo "start_pipeline_run for that repo must send who=${WHO}. Ctrl-C closes the window."
    while true; do sleep 3600; done
    ;;
  db-steps) shift; cmd_db_steps "$@"; exit 0 ;;
  db-done) shift; cmd_db_done "$@"; exit 0 ;;
  policy) shift; cmd_policy "$@"; exit $? ;;
  freeze) shift; cmd_freeze "$@"; exit 0 ;;
  unfreeze) shift; cmd_unfreeze "$@"; exit 0 ;;
  merge) shift; cmd_merge "$@"; exit 0 ;;
  dev|stg|prod) ENV_NAME="$1"; shift ;;
  -h|--help|"") release_usage; exit 0 ;;
  *) release_usage >&2; exit 2 ;;
esac

DRY_RUN=0 FROM_STG="" WHAT="" ALLOW_RED="" WHO="${BIFROST_RELEASE_WHO:-${USER}@$(hostname -s)}" TIMEOUT=3600
ALLOW=() PROBES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --from-stg) FROM_STG="${2:?--from-stg needs a run name}"; shift 2 ;;
    --allow) ALLOW+=(--allow "${2:?}"); shift 2 ;;
    --probes) PROBES+=(--probes "${2:?}"); shift 2 ;;
    --what) WHAT="${2:?}"; shift 2 ;;
    --allow-red) ALLOW_RED="${2:?--allow-red needs a reason}"; shift 2 ;;
    --owner-approved) OWNER_APPROVED="${2:?--owner-approved needs a note}"; shift 2 ;;
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

if [[ "${ENV_NAME}" == "stg" ]]; then
  step "Gitea mirror and CI for origin/main"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[dry-run] would sync Gitea mirrors and require a Succeeded ci-* run for origin/main of core, api, worker, frontend"
    [[ -n "${ALLOW_RED}" ]] && echo "[dry-run] --allow-red ${ALLOW_RED}"
  else
    wait_for_ci < <(ci_pairs_from_origin)
  fi
  step_end
fi

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

  step "Gitea mirror and CI for the STG SHAs"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[dry-run] would sync Gitea mirrors and require a Succeeded ci-* run for each SHA in ${OUT_DIR}/stg-commits.txt"
    [[ -n "${ALLOW_RED}" ]] && echo "[dry-run] --allow-red ${ALLOW_RED}"
  else
    wait_for_ci < <(ci_pairs_from_stg_commits)
  fi
  step_end
fi

step "release policy and freeze (${ENV_NAME})"
case "${ENV_NAME}" in
  stg)
    POLICY_ACTION="bifrost-deliver-stg"
    deployed_commits trade stg "" "${OUT_DIR}/deployed.txt"
    { tr ',' '\n' <<<"${TRADE_WHAT}"; cut -d= -f1 "${OUT_DIR}/deployed.txt"; } | sort -u | while read -r r; do
      [[ -n "${r}" ]] && printf '%s=\n' "${r}"
    done >"${OUT_DIR}/repos.txt"
    origin_main_commits "${OUT_DIR}/repos.txt" "${OUT_DIR}/shipping.txt" ;;
  prod)
    POLICY_ACTION="bifrost-deliver-prod-pinned"
    deployed_commits trade prod "" "${OUT_DIR}/deployed.txt"
    deployed_commits trade stg "${FROM_STG}" "${OUT_DIR}/shipping.txt" ;;
  dev)
    POLICY_ACTION="trade-dev-sync"
    if [[ -f "${DEV_COMMITS}" ]]; then cp "${DEV_COMMITS}" "${OUT_DIR}/deployed.txt"; else : >"${OUT_DIR}/deployed.txt"; fi
    deployed_commits trade stg "" "${OUT_DIR}/shipping.txt" ;;
esac
policy_pairs "${OUT_DIR}/deployed.txt" "${OUT_DIR}/shipping.txt" >"${OUT_DIR}/pairs.txt"
sed 's/^/  /' "${OUT_DIR}/pairs.txt"
policy_gate "${POLICY_ACTION}" "${OUT_DIR}/pairs.txt"
step_end

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
    if [[ "${DRY_RUN}" -eq 0 ]]; then
      cp "${OUT_DIR}/shipping.txt" "${DEV_COMMITS}"
      echo "recorded the commits DEV now runs in ${DEV_COMMITS} (the next dev release diffs against them)"
    fi
    echo "after the copy DEV runs the :stg images (core ${STG_CORE}) and the :stg frontend." ;;
esac
step_end

summary
if [[ "${DRY_RUN}" -eq 1 && "${REFUSALS}" -gt 0 ]]; then
  echo "dry-run: ${REFUSALS} precondition(s) would stop this release"
  exit 2
fi
