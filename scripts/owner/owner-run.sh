#!/usr/bin/env bash
# Owner only. An Agent must not run this script.
#
# After an owner_run_command approval is executed (the platform only records
# it), this script checks the approval, prints the command, and runs it when
# the Owner types yes. It uses the PROD viewer token and OWNER_KUBECONFIG.
# The token and the command are not written to the run log.
set -euo pipefail

PLATFORM_API="${PLATFORM_API:-http://192.168.10.100:30876}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-${ROOT}/.env}"
LOG_FILE="${HOME}/.bifrost-owner/run-log.jsonl"
MAX_AGE_SECONDS="${OWNER_RUN_MAX_AGE_SECONDS:-86400}"

if [ $# -ne 1 ] || [ -z "$1" ]; then
  echo "usage: owner-run.sh <approval-id>" >&2
  exit 2
fi
APPROVAL_ID="$1"
case "$APPROVAL_ID" in
  *[!A-Za-z0-9_-]*)
    echo "REFUSED: approval id must be one token" >&2
    exit 2
    ;;
esac

viewer_token() {
  if [ -n "${PLATFORM_PROD_VIEWER_TOKEN:-}" ]; then
    printf '%s' "${PLATFORM_PROD_VIEWER_TOKEN}"
    return 0
  fi
  if [ ! -f "$ENV_FILE" ]; then
    echo "REFUSED: missing PLATFORM_PROD_VIEWER_TOKEN" >&2
    return 1
  fi
  local line
  line="$(grep -E '^PLATFORM_PROD_VIEWER_TOKEN=' "$ENV_FILE" | tail -1 || true)"
  line="${line#*=}"
  line="${line%\"}"
  line="${line#\"}"
  if [ -z "$line" ]; then
    echo "REFUSED: missing PLATFORM_PROD_VIEWER_TOKEN" >&2
    return 1
  fi
  printf '%s' "$line"
}

token="$(viewer_token)" || exit 1
case "$token" in
  *\"*|*$'\n'*|*$'\r'*)
    echo "REFUSED: viewer token cannot be passed to curl safely" >&2
    exit 1
    ;;
esac
cfg="$(mktemp)"
chmod 600 "$cfg"
printf 'header = "Authorization: Bearer %s"\n' "$token" > "$cfg"
set +e
body="$(curl -fsS --config "$cfg" --url "${PLATFORM_API%/}/api/v1/approvals/${APPROVAL_ID}")"
rc=$?
set -e
rm -f "$cfg"
if [ "$rc" -ne 0 ]; then
  echo "REFUSED: could not read approval ${APPROVAL_ID}" >&2
  exit 1
fi

command_text="$(printf '%s' "$body" | python3 -c '
import hashlib, json, sys
from datetime import datetime, timezone
approval_id = sys.argv[1]
max_age = int(sys.argv[2])
doc = json.loads(sys.stdin.read())
action = doc.get("action")
status = doc.get("status")
if action != "owner_run_command" or status != "executed":
    sys.stderr.write("REFUSED: approval %s is action=%s status=%s; want owner_run_command executed\n" % (approval_id, action, status))
    sys.exit(1)
stamp = doc.get("decided_at") or doc.get("created_at") or ""
text = stamp.strip()
if text.endswith("Z"):
    text = text[:-1] + "+00:00"
try:
    when = datetime.fromisoformat(text)
except ValueError:
    when = None
if when is None:
    sys.stderr.write("REFUSED: approval %s has no decision time\n" % approval_id)
    sys.exit(1)
if when.tzinfo is None:
    when = when.replace(tzinfo=timezone.utc)
age = (datetime.now(timezone.utc) - when).total_seconds()
if age > max_age:
    sys.stderr.write("REFUSED: approval %s is older than %ss\n" % (approval_id, max_age))
    sys.exit(1)
params = doc.get("params") or {}
command = params.get("command")
if not isinstance(command, str) or command.strip() == "":
    sys.stderr.write("REFUSED: approval %s has no command\n" % approval_id)
    sys.exit(1)
digest = hashlib.sha256(command.encode()).hexdigest()
result = doc.get("result") or {}
recorded = result.get("command_sha256") if isinstance(result, dict) else None
if recorded != digest:
    sys.stderr.write("REFUSED: approval %s command hash does not match\n" % approval_id)
    sys.exit(1)
sys.stdout.write(command)
' "$APPROVAL_ID" "$MAX_AGE_SECONDS")"

digest="$(printf '%s' "$command_text" | shasum -a 256 | awk '{print $1}')"
if [ ! -t 0 ]; then
  echo "REFUSED: standard input must be a terminal" >&2
  exit 1
fi
printf 'command:\n%s\nType yes to run it: ' "$command_text"
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
set +e
bash -c "$command_text"
run_rc=$?
set -e
mkdir -p "$(dirname "$LOG_FILE")"
python3 -c '
import json, sys, time
row = {"id": sys.argv[1], "command_sha256": sys.argv[2], "exit": int(sys.argv[3]), "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
with open(sys.argv[4], "a") as fh:
    fh.write(json.dumps(row) + "\n")
' "$APPROVAL_ID" "$digest" "$run_rc" "$LOG_FILE"
exit "$run_rc"
