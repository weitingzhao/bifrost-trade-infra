#!/usr/bin/env bash
# Owner only. An Agent must not run this script.
#
# Runs an owner_run_command approval on this machine. Approving it leaves it
# approved with runner owner (the platform does not run it). This script reads
# it with the PROD viewer token, prints the command, and when the Owner types
# yes claims it (scripts/owner/lib-approval.sh: one start per approval), keeps
# the lease alive while the command runs, and posts the exit code, duration,
# output hash and the last 2 KB of output back to the approval. The full output
# is kept in ~/.bifrost-owner/run-output/<id>.log (mode 600).
# An approval recorded before that change (status executed, no execution
# block) still runs as before, without the write-back.
# It uses OWNER_KUBECONFIG (default ~/.bifrost-owner/kube/admin.yaml).
# Tokens and the command are not written to the run log.
set -euo pipefail

PLATFORM_API="${PLATFORM_API:-http://192.168.10.100:30876}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-${ROOT}/.env}"
LOG_FILE="${HOME}/.bifrost-owner/run-log.jsonl"
OUTPUT_DIR="${HOME}/.bifrost-owner/run-output"
OWNER_KUBECONFIG="${OWNER_KUBECONFIG:-${HOME}/.bifrost-owner/kube/admin.yaml}"
MAX_AGE_SECONDS="${OWNER_RUN_MAX_AGE_SECONDS:-86400}"
# shellcheck source=lib-approval.sh
. "${ROOT}/scripts/owner/lib-approval.sh"

if [ $# -ne 1 ] || [ -z "$1" ]; then
  echo "usage: owner-run.sh <approval-id | #n>" >&2
  exit 2
fi
REF="$(approval_ref "$1")" || exit 2

body="$(approval_get "$REF")" || exit 1

# Prints four parts: mode (claim | legacy), approval id, label, command.
plan="$(printf '%s' "$body" | python3 -c '
import hashlib, json, sys
from datetime import datetime, timezone

def when(value):
    text = (value or "").strip() if isinstance(value, str) else ""
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        out = datetime.fromisoformat(text)
    except ValueError:
        return None
    return out if out.tzinfo else out.replace(tzinfo=timezone.utc)

ref = sys.argv[1]
max_age = int(sys.argv[2])
doc = json.loads(sys.stdin.read())
action = doc.get("action")
status = doc.get("status")
execution = doc.get("execution") if isinstance(doc.get("execution"), dict) else None
now = datetime.now(timezone.utc)
if action == "owner_run_command" and status == "approved":
    runner = doc.get("runner") or "owner"
    if runner != "owner":
        sys.stderr.write("REFUSED: approval %s is runner=%s; the host executor runs it, not this script\n" % (ref, runner))
        sys.exit(1)
    deadline = when((execution or {}).get("deadline"))
    if deadline is None or now >= deadline:
        sys.stderr.write("REFUSED: approval %s is past its execution deadline\n" % ref)
        sys.exit(1)
    mode = "claim"
elif action == "owner_run_command" and status == "executed" and execution is None:
    decided = when(doc.get("decided_at") or doc.get("created_at"))
    if decided is None:
        sys.stderr.write("REFUSED: approval %s has no decision time\n" % ref)
        sys.exit(1)
    if (now - decided).total_seconds() > max_age:
        sys.stderr.write("REFUSED: approval %s is older than %ss\n" % (ref, max_age))
        sys.exit(1)
    mode = "legacy"
else:
    sys.stderr.write("REFUSED: approval %s is action=%s status=%s; want owner_run_command approved\n" % (ref, action, status))
    sys.exit(1)
approval_id = doc.get("id") or ref
if not isinstance(approval_id, str) or not approval_id.replace("_", "").replace("-", "").isalnum():
    sys.stderr.write("REFUSED: approval %s has no usable id\n" % ref)
    sys.exit(1)
params = doc.get("params") or {}
command = params.get("command")
if not isinstance(command, str) or command.strip() == "":
    sys.stderr.write("REFUSED: approval %s has no command\n" % ref)
    sys.exit(1)
digest = hashlib.sha256(command.encode()).hexdigest()
result = doc.get("result") or {}
recorded = result.get("command_sha256") if isinstance(result, dict) else None
if recorded != digest:
    sys.stderr.write("REFUSED: approval %s command hash does not match\n" % ref)
    sys.exit(1)
number = doc.get("number")
label = ("#%d" % number) if isinstance(number, int) and number > 0 else approval_id
sys.stdout.write("%s\n%s\n%s\n%s" % (mode, approval_id, label, command))
' "$REF" "$MAX_AGE_SECONDS")"

mode="${plan%%$'\n'*}"
rest="${plan#*$'\n'}"
APPROVAL_ID="${rest%%$'\n'*}"
rest="${rest#*$'\n'}"
label="${rest%%$'\n'*}"
command_text="${rest#*$'\n'}"

digest="$(printf '%s' "$command_text" | shasum -a 256 | awk '{print $1}')"
if [ ! -t 0 ]; then
  echo "REFUSED: standard input must be a terminal" >&2
  exit 1
fi
printf 'approval %s\ncommand:\n%s\nType yes to run it: ' "$label" "$command_text"
read -r answer
if [ "$answer" != "yes" ]; then
  echo "REFUSED: not confirmed" >&2
  exit 1
fi
if [ -z "${OWNER_KUBECONFIG:-}" ] || [ ! -f "${OWNER_KUBECONFIG}" ]; then
  echo "REFUSED: OWNER_KUBECONFIG must point at the Owner kubeconfig" >&2
  exit 1
fi
export KUBECONFIG="${OWNER_KUBECONFIG}"

lease=""
out_file=""
if [ "$mode" = "claim" ]; then
  approval_load_run_token || exit 1
  lease="$(approval_claim "$APPROVAL_ID" "owner-run:$(hostname -s 2>/dev/null || echo host)" owner)" || exit 1
  trap 'approval_heartbeat_stop' EXIT
  approval_heartbeat_start "$APPROVAL_ID" "$lease"
  mkdir -p "$OUTPUT_DIR"
  chmod 700 "$OUTPUT_DIR"
  out_file="${OUTPUT_DIR}/${APPROVAL_ID}.log"
  (umask 077 && : > "$out_file")
else
  echo "WARNING: approval ${label} predates the claim protocol; it runs without a result on the approval" >&2
fi

started_ms="$(approval_now_ms)"
# Ctrl-C stops the command, not this script: the result is still posted.
trap ':' INT
set +e
if [ -n "$out_file" ]; then
  bash -c "$command_text" 2>&1 | tee "$out_file"
  run_rc=${PIPESTATUS[0]}
else
  bash -c "$command_text"
  run_rc=$?
fi
set -e
trap - INT
duration_ms=$(( $(approval_now_ms) - started_ms ))

posted="false"
if [ "$mode" = "claim" ]; then
  approval_heartbeat_stop
  if approval_post_result "$APPROVAL_ID" "$lease" "$run_rc" "$duration_ms" "$out_file"; then
    posted="true"
  fi
fi

mkdir -p "$(dirname "$LOG_FILE")"
python3 -c '
import json, sys, time
row = {"id": sys.argv[1], "ref": sys.argv[5], "command_sha256": sys.argv[2], "exit": int(sys.argv[3]),
       "duration_ms": int(sys.argv[6]), "result_posted": sys.argv[7] == "true",
       "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
with open(sys.argv[4], "a") as fh:
    fh.write(json.dumps(row) + "\n")
' "$APPROVAL_ID" "$digest" "$run_rc" "$LOG_FILE" "$label" "$duration_ms" "$posted"
exit "$run_rc"
