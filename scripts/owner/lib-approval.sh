# Sourced by owner-run.sh and k3s/rolling-reboot.sh. Not run on its own.
#
# Approval reads use the PROD viewer token. A run claims the approval with the
# PROD admin token (PLATFORM_OWNER_RUN_TOKEN overrides it): the platform lets
# that token claim runner=owner work, and starts each approval at most once.
# While the command runs, a background loop renews the lease; at the end the
# exit code, duration, output hash and the last 2 KB of output go back to the
# approval. Tokens go to curl through a mode-600 config file, never argv.
#
# The caller sets PLATFORM_API and ENV_FILE. Bash 3.2 compatible.

APPROVAL_HEARTBEAT_SECONDS="${APPROVAL_HEARTBEAT_SECONDS:-20}"
APPROVAL_TAIL_BYTES=2048
APPROVAL_HB_PID=""
APPROVAL_HB_FILES=""
APPROVAL_RUN_TOKEN=""

# approval_ref prints the approval id or number to put in the URL: #57, 57 and
# appr_… are accepted.
approval_ref() {
  local ref="${1#\#}"
  case "$ref" in
    ""|*[!A-Za-z0-9_-]*)
      echo "REFUSED: approval must be one id or #n" >&2
      return 1
      ;;
  esac
  printf '%s' "$ref"
}

# approval_token KEY... prints the first key set in the environment, else in
# ENV_FILE. Never echo the value anywhere else.
approval_token() {
  local key value line
  for key in "$@"; do
    value="${!key:-}"
    if [ -n "$value" ]; then
      printf '%s' "$value"
      return 0
    fi
  done
  if [ -f "${ENV_FILE:-}" ]; then
    for key in "$@"; do
      line="$(grep -E "^${key}=" "$ENV_FILE" | tail -1 || true)"
      line="${line#*=}"
      line="${line%\"}"
      line="${line#\"}"
      if [ -n "$line" ]; then
        printf '%s' "$line"
        return 0
      fi
    done
  fi
  echo "REFUSED: missing $1" >&2
  return 1
}

# approval_curl_config TOKEN prints the path of a mode-600 curl config holding
# the bearer header. The caller removes it.
approval_curl_config() {
  local token="$1" cfg
  case "$token" in
    *\"*|*$'\n'*|*$'\r'*)
      echo "REFUSED: token cannot be passed to curl safely" >&2
      return 1
      ;;
  esac
  cfg="$(mktemp)"
  chmod 600 "$cfg"
  printf 'header = "Authorization: Bearer %s"\n' "$token" > "$cfg"
  printf '%s' "$cfg"
}

# approval_get REF prints the approval JSON.
approval_get() {
  local ref="$1" token cfg body rc
  token="$(approval_token PLATFORM_PROD_VIEWER_TOKEN)" || return 1
  cfg="$(approval_curl_config "$token")" || return 1
  set +e
  body="$(curl -fsS --config "$cfg" --url "${PLATFORM_API%/}/api/v1/approvals/${ref}")"
  rc=$?
  set -e
  rm -f "$cfg"
  if [ "$rc" -ne 0 ]; then
    echo "REFUSED: could not read approval ${ref}" >&2
    return 1
  fi
  printf '%s' "$body"
}

# approval_load_run_token reads the claim token once, before any POST.
approval_load_run_token() {
  APPROVAL_RUN_TOKEN="$(approval_token PLATFORM_OWNER_RUN_TOKEN PLATFORM_PROD_ADMIN_TOKEN)" || return 1
}

# approval_post PATH DATA_FILE OUT_FILE posts JSON with the run token and
# prints the HTTP status (000 when curl itself failed).
approval_post() {
  local path="$1" data="$2" out="$3" cfg code
  cfg="$(approval_curl_config "$APPROVAL_RUN_TOKEN")" || { printf '000'; return 0; }
  set +e
  code="$(curl -sS --config "$cfg" -H 'Content-Type: application/json' \
    --data-binary "@${data}" -o "$out" -w '%{http_code}' \
    --url "${PLATFORM_API%/}${path}" 2>/dev/null)"
  [ $? -eq 0 ] || code="000"
  set -e
  rm -f "$cfg"
  printf '%s' "${code:-000}"
}

# approval_claim ID EXECUTOR RUNNER prints the lease id. Refuses when another
# run holds it or the approval is no longer approved.
approval_claim() {
  local id="$1" executor="$2" runner="$3" data out code lease
  data="$(mktemp)"
  out="$(mktemp)"
  python3 -c '
import json, sys
json.dump({"executor_id": sys.argv[1], "id": sys.argv[2], "runners": [sys.argv[3]]}, sys.stdout)
' "$executor" "$id" "$runner" > "$data"
  code="$(approval_post /api/v1/approvals/claim "$data" "$out")"
  if [ "$code" != "200" ]; then
    echo "REFUSED: could not claim approval ${id} (HTTP ${code}): $(head -c 300 "$out" 2>/dev/null)" >&2
    rm -f "$data" "$out"
    return 1
  fi
  lease="$(python3 -c '
import json, sys
print(json.load(open(sys.argv[1])).get("lease_id") or "")
' "$out" 2>/dev/null || true)"
  rm -f "$data" "$out"
  # The platform's lease ids are "lease_" plus hex (approvals/execution.go claimLocked).
  # Letters, digits and "_" only: the id is written into JSON request bodies with printf.
  case "$lease" in
    ""|*[!A-Za-z0-9_]*)
      echo "REFUSED: claim of approval ${id} returned no lease" >&2
      return 1
      ;;
  esac
  printf '%s' "$lease"
}

# approval_heartbeat_start ID LEASE renews the lease in the background until
# approval_heartbeat_stop. A non-interactive shell starts it with SIGINT
# ignored, so Ctrl-C on the command does not stop the heartbeat.
approval_heartbeat_start() {
  local id="$1" lease="$2" data out
  data="$(mktemp)"
  out="$(mktemp)"
  printf '{"lease_id":"%s"}' "$lease" > "$data"
  APPROVAL_HB_FILES="${data} ${out}"
  (
    nap=""
    trap - EXIT
    trap '[ -z "$nap" ] || kill "$nap" 2>/dev/null; exit 0' TERM
    while :; do
      sleep "$APPROVAL_HEARTBEAT_SECONDS" &
      nap=$!
      wait "$nap" || true
      approval_post "/api/v1/approvals/${id}/heartbeat" "$data" "$out" >/dev/null || true
    done
  ) </dev/null >/dev/null 2>&1 &
  APPROVAL_HB_PID=$!
}

approval_heartbeat_stop() {
  if [ -n "$APPROVAL_HB_PID" ]; then
    kill "$APPROVAL_HB_PID" 2>/dev/null || true
    wait "$APPROVAL_HB_PID" 2>/dev/null || true
    APPROVAL_HB_PID=""
  fi
  if [ -n "${APPROVAL_HB_FILES:-}" ]; then
    # shellcheck disable=SC2086
    rm -f $APPROVAL_HB_FILES
    APPROVAL_HB_FILES=""
  fi
}

approval_now_ms() {
  python3 -c 'import time; print(int(time.time() * 1000))'
}

# approval_post_result ID LEASE EXIT_CODE DURATION_MS OUTPUT_FILE posts the
# outcome. Retries three times; a 409 (lease taken or result already posted)
# is final.
approval_post_result() {
  local id="$1" lease="$2" rc="$3" duration="$4" output="$5" data out code attempt
  data="$(mktemp)"
  out="$(mktemp)"
  chmod 600 "$data"
  python3 -c '
import hashlib, json, sys
lease, rc, duration, path, limit = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], int(sys.argv[5])
try:
    raw = open(path, "rb").read()
except OSError:
    raw = b""
tail = raw[-limit:].decode("utf-8", "replace")
while len(tail.encode("utf-8")) > limit:
    tail = tail[1:]
json.dump({
    "lease_id": lease,
    "started": True,
    "exit_code": rc,
    "duration_ms": duration,
    "output_sha256": hashlib.sha256(raw).hexdigest(),
    "output_tail": tail,
}, sys.stdout)
' "$lease" "$rc" "$duration" "$output" "$APPROVAL_TAIL_BYTES" > "$data"
  for attempt in 1 2 3; do
    code="$(approval_post "/api/v1/approvals/${id}/result" "$data" "$out")"
    case "$code" in
      2*)
        rm -f "$data" "$out"
        return 0
        ;;
      409)
        break
        ;;
    esac
    [ "$attempt" = "3" ] || sleep "${APPROVAL_RESULT_RETRY_SECONDS:-2}"
  done
  echo "WARNING: could not post the result of approval ${id} (HTTP ${code}): $(head -c 300 "$out" 2>/dev/null). The approval turns unknown when its lease lapses." >&2
  rm -f "$data" "$out"
  return 1
}
